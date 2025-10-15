# -*- coding: utf-8 -*-
# strategies/GRID/manager/grid_manager.py (KORREKTE Grid-Logik)
"""
GridManager mit KORREKTER Grid-Order-Platzierung

KRITISCHER FIX:
- ✅ LONG: Orders nur UNTER aktuellem Preis
- ✅ SHORT: Orders nur ÜBER aktuellem Preis
- ✅ Keine Breakout-Orders mehr!
- ✅ Progressive Order-Platzierung
"""
from pathlib import Path
import sys

GRID_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(GRID_DIR))


import logging
import time
import asyncio
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from .grid_lifecycle import GridLifecycle, GridState
from .order_sync import OrderSync
from .grid_calculator import GridCalculator
from .risk_manager import RiskManager  
from .hedge_manager import HedgeManager
from utils.exceptions import (InvalidGridConfigError, OrderPlacementError, GridInitializationError)
from models.config_models import GridDirection 

@dataclass
class GridLevel:
    index: int
    price: float
    side: str
    order_id: Optional[str] = None
    active: bool = False           # Order platziert
    filled: bool = False           # Order gefüllt
    position_open: bool = False    # ← NEU: Position noch offen
    position_id: Optional[str] = None  # ← NEU: Position-ID
    tp: Optional[float] = None
    sl: Optional[float] = None

    def __repr__(self) -> str:
        status = "FILLED" if self.filled else ("ACTIVE" if self.active else "IDLE")
        return f"<GridLevel #{self.index} {self.side} @ {self.price} [{status}]>"


class GridManager:
    def __init__(self, client, config, client_pub=None):
        """Initialisiert den GridManager inklusive HedgeManager"""
        self.client = client
        self.config = config
        self.client_pub = client_pub
        self.symbol: str = config.symbol
        self.trading = config.trading
        self.grid_conf = config.grid
        self.risk_conf = config.risk
        self.strategy = config.strategy
        self.system = config.system

        # === Grid Direction ===
        raw_dir = self.trading.grid_direction
        if GridDirection and isinstance(raw_dir, GridDirection):
            self.grid_direction = raw_dir.value.lower()
        else:
            self.grid_direction = str(raw_dir).strip().lower()

        self.grid_mode: str = self.grid_direction
        self.levels: list = []
        self.last_rebalance: float = 0.0
        self._levels_lock = asyncio.Lock()
        self.margin_mode = config.margin.mode
        self.leverage = config.margin.leverage
        
        # Net-Position Tracking
        self.net_position_size = 0.0
        
        # Hedge-Trigger-Tracking
        self._last_hedge_check = 0.0
        self._hedge_check_interval = 10
        self._last_price_for_hedge = None
        
        # ✅ NEU: Letzter bekannter Preis für Grid-Placement
        self._last_known_price = None

        # === Logging ===
        self.logger = logging.getLogger("GridManager")
        level_name = self.system.log_level.upper()
        self.logger.setLevel(getattr(logging, level_name, logging.INFO))

        # === Lifecycle ===
        self.lifecycle = GridLifecycle(self.symbol, on_state_change=self._on_state_change)

        # === GridCalculator ===
        self.calculator = GridCalculator(self.grid_conf, self.logger)

        # === RiskManager ===
        self.risk_manager = RiskManager(self.grid_conf, self.risk_conf, self.calculator, self.logger)

        # === HedgeManager ===
        self.hedge_manager = HedgeManager(
            config.hedge, 
            self.client, 
            self.symbol, 
            self.logger, 
            dry_run=self.trading.dry_run,
            client_pub=self.client_pub
        )
        self.hedge_manager.grid_direction = self.grid_direction

        try:
            self.hedge_manager.config.dry_run = bool(self.trading.dry_run)
        except Exception:
            pass

        try:
            self.validate_config()
            self._create_grid_levels()
            self.last_rebalance = time.time()
            self.log_summary()

            self.lifecycle.set_state(GridState.ACTIVE)
            self.logger.info(f"[{self.symbol}] GridManager aktiv")

            price_list = self.calculator.calculate_price_list()
            for lvl in self.levels:
                lvl.tp = self.risk_manager.calculate_take_profit(lvl.price, lvl.index, lvl.side, price_list)
                lvl.sl = self.risk_manager.calculate_stop_loss(lvl.price, lvl.side)

            self.order_sync = OrderSync(
                symbol=self.symbol,
                levels=self.levels,
                logger=self.logger,
                client=self.client,
                size=self.risk_manager.calculate_effective_size(),
                grid_direction=self.grid_direction,
            )

            # === NEU: VirtualOrderManager (Dry-Run) ===
            if self.trading.dry_run:
                from .virtual_order_manager import VirtualOrderManager
                self.virtual_manager = VirtualOrderManager(self.symbol, self.logger)
                self.logger.info("[VIRTUAL] 🎮 Dry-Run Mode mit Virtual Orders aktiv")
            else:
                self.virtual_manager = None
            # Flag für initiale Order-Platzierung
            self._initial_orders_placed = False

            # Warte auf ersten Preis!
            self.logger.warning("[INIT] ⏳ Warte auf ersten Live-Preis vor Order-Platzierung...")

        except (InvalidGridConfigError, GridInitializationError) as e:
            self.lifecycle.set_state(GridState.ERROR, message=str(e))
            raise
        except Exception as e:
            self.lifecycle.set_state(GridState.ERROR, message=f"Init-Fehler: {e}")
            raise GridInitializationError(f"Grid-Initialisierung fehlgeschlagen: {e}")


    def _place_initial_grid_orders(self, current_price: float) -> None:
        """
        Platziert Grid-Orders basierend auf aktuellem Preis.
        
        ✅ KRITISCHER FIX:
        - LONG: Nur Orders UNTER aktuellem Preis
        - SHORT: Nur Orders ÜBER aktuellem Preis
        
        Args:
            current_price: Aktueller Live-Preis
        """
        # === NEU: Out-of-Range Check ===
        lower = self.grid_conf.lower_price
        upper = self.grid_conf.upper_price
        
        # Warnung wenn Preis außerhalb Grid
        if current_price < lower:
            self.logger.warning(
                f"⚠️ Preis {current_price:.4f} UNTER Grid ({lower:.4f} - {upper:.4f})"
            )
            if self.grid_direction == "short":
                self.logger.info("SHORT-Grid: Warte bis Preis in Range...")
                return  # Keine Orders bei SHORT wenn Preis zu niedrig
        
        elif current_price > upper:
            self.logger.warning(
                f"⚠️ Preis {current_price:.4f} ÜBER Grid ({lower:.4f} - {upper:.4f})"
            )
            if self.grid_direction == "long":
                self.logger.info("LONG-Grid: Warte bis Preis in Range...")
                return  # Keine Orders bei LONG wenn Preis zu hoch
        
        allow_long = self.grid_direction in ("long", "both")
        allow_short = self.grid_direction in ("short", "both")
        
        placed_count = 0
        skipped_count = 0
        
        for lvl in self.levels:
            # ✅ NEU: Auch position_open prüfen
            if lvl.active or lvl.filled or lvl.position_open:
                continue
            
            # ✅ LONG: Nur Orders UNTER aktuellem Preis
            if lvl.side == "BUY":
                if not allow_long:
                    continue
                
                # ❌ Order über Preis → Skip (wäre Breakout!)
                if lvl.price >= current_price:
                    skipped_count += 1
                    self.logger.debug(
                        f"[INIT] Skip BUY @ {lvl.price:.4f} "
                        f"(über Preis {current_price:.4f})"
                    )
                    continue
            
            # ✅ SHORT: Nur Orders ÜBER aktuellem Preis
            elif lvl.side == "SELL":
                if not allow_short:
                    continue
                
                # ❌ Order unter Preis → Skip (wäre Breakout!)
                if lvl.price <= current_price:
                    skipped_count += 1
                    self.logger.debug(
                        f"[INIT] Skip SELL @ {lvl.price:.4f} "
                        f"(unter Preis {current_price:.4f})"
                    )
                    continue
            
            # Platziere Order
            try:
                self._place_entry(lvl)
                placed_count += 1
            except Exception as e:
                self.logger.error(f"❌ Initial Order @ {lvl.price} fehlgeschlagen: {e}")
        
        mode = "Dry-Run" if self.trading.dry_run else "Real"
        self.logger.info(
            f"[ORDER] {placed_count}/{len(self.levels)} Grid-Orders platziert, "
            f"{skipped_count} übersprungen @ Preis {current_price:.4f} ({mode})"
        )

        # Hedge initial platzieren
        if placed_count > 0:
            self._update_and_hedge("initial_orders")


    def validate_config(self) -> None:
        """Config-Validierung mit spezifischen Exceptions"""
        lower = self.grid_conf.lower_price
        upper = self.grid_conf.upper_price
        n = self.grid_conf.grid_levels
        
        if upper <= lower:
            raise InvalidGridConfigError(
                f"upper_price ({upper}) muss größer als lower_price ({lower}) sein"
            )
        if n < 2:
            raise InvalidGridConfigError(
                f"grid_levels ({n}) muss mindestens 2 sein"
            )
        tick = float(self.grid_conf.min_price_step)
        if tick <= 0.0:
            raise InvalidGridConfigError(
                f"min_price_step ({tick}) muss > 0 sein"
            )

    def _create_grid_levels(self) -> None:
        """Erstellt GridLevel-Objekte basierend auf Preisraster"""
        price_list = self.calculator.calculate_price_list()
        
        lower = self.grid_conf.lower_price
        upper = self.grid_conf.upper_price
        mid = (lower + upper) / 2.0
        
        self.levels = []
        
        for i, p in enumerate(price_list):
            if self.grid_direction == "long":
                side = "BUY"
            elif self.grid_direction == "short":
                side = "SELL"
            else:
                side = "BUY" if p <= mid else "SELL"
            
            self.levels.append(GridLevel(index=i, price=p, side=side))
        
        self.logger.info(f"{len(self.levels)} GridLevel-Objekte erstellt ({self.grid_direction}).")

    def _maybe_rebalance(self) -> None:
        now = time.time()
        interval = int(self.grid_conf.rebalance_interval)
        if now - self.last_rebalance >= interval:
            self.logger.info("Rebalancing...")
            self.calculator.invalidate_cache()
            self._create_grid_levels()
            self.last_rebalance = now

    def update(self, current_price: float) -> None:
        """
        Hauptupdate pro Tick – prüft Orders, Entry-Trigger und Hedge-Möglichkeit.
        
        ✅ NEU: Platziert initiale Orders beim ersten Preis
        """
        try:
            if not self.lifecycle.is_active():
                return

            # Letzten Preis speichern
            self.hedge_manager.live_price = current_price
            self._last_known_price = current_price
            
            # === NEU: VIRTUAL ORDER CHECKS (Dry-Run) ===
            if self.trading.dry_run and self.virtual_manager:
                # Fill-Detection
                filled_orders = self.virtual_manager.check_fills(current_price)
                for order in filled_orders:
                    # Finde entsprechendes Level
                    for lvl in self.levels:
                        if lvl.order_id == order.order_id:
                            self.handle_order_fill(lvl)
                            break
                
                # TP/SL Trigger
                closed_positions = self.virtual_manager.check_tp_sl(current_price)
                if closed_positions:
                    self.logger.debug(
                        f"[VIRTUAL] TP/SL getriggert: {len(closed_positions)} Positionen geschlossen"
                    )

            
            # ✅ NEU: Initiale Order-Platzierung beim ersten Preis
            if not self._initial_orders_placed:
                self.logger.info(
                    f"[INIT] ✅ Erster Preis empfangen: {current_price:.4f} "
                    f"→ Platziere Grid-Orders"
                )
                self._place_initial_grid_orders(current_price)
                self._initial_orders_placed = True  # ✅ Flag setzen
                return
            
            # Rebalancing ggf. ausführen
            self._maybe_rebalance()

            # Entry-Orders prüfen (neue Orders wenn Preis sich bewegt)
            entry_on_touch = bool(self.strategy.entry_on_touch)
            if entry_on_touch:
                self._check_new_grid_orders(current_price)

            # Smart Hedge-Trigger
            self._check_hedge_opportunity(current_price)

        except Exception as e:
            self.logger.error(f"Update-Fehler: {e}")
            self.lifecycle.set_state(GridState.ERROR, str(e))

    def _check_new_grid_orders(self, current_price: float) -> None:
        """
        ✅ NEU: Prüft ob neue Grid-Orders platziert werden können.
        
        LONG: Wenn Preis steigt → neue Orders UNTER dem Preis
        SHORT: Wenn Preis fällt → neue Orders ÜBER dem Preis
        """
        allow_long = self.grid_direction in ("long", "both")
        allow_short = self.grid_direction in ("short", "both")

        for lvl in self.levels:
            # ✅ NEU: Auch position_open prüfen
            if lvl.active or lvl.filled or lvl.position_open:
                continue

            # LONG: Platziere BUY wenn Preis ÜBER Level ist
            if lvl.side == "BUY" and allow_long:
                if current_price > lvl.price:
                    self._place_entry(lvl)
            
            # SHORT: Platziere SELL wenn Preis UNTER Level ist
            elif lvl.side == "SELL" and allow_short:
                if current_price < lvl.price:
                    self._place_entry(lvl)

    def _check_hedge_opportunity(self, current_price: float) -> None:
        """Prüft ob Hedge jetzt platzierbar ist (Smart Throttling)"""
        now = time.time()
        
        # Throttling: Nur alle X Sekunden prüfen
        if now - self._last_hedge_check < self._hedge_check_interval:
            return
        
        # Preis-Änderungs-Check: Nur bei signifikanten Bewegungen
        if self._last_price_for_hedge:
            price_change_pct = abs(current_price - self._last_price_for_hedge) / self._last_price_for_hedge
            if price_change_pct < 0.01:  # < 1% Bewegung → Skip
                return
        
        self._last_hedge_check = now
        self._last_price_for_hedge = current_price
        
        # Prüfe ob Hedge aktiv ist
        if getattr(self.hedge_manager, "active", False):
            self.logger.debug("[HEDGE] Hedge bereits aktiv → Skip Check")
            return
        
        # Prüfe ob Net-Position vorhanden
        if abs(self.net_position_size) < 0.001:
            return
        
        # Grid-Bounds holen
        price_list = self.calculator.calculate_price_list()
        lower_bound = price_list[0]
        upper_bound = price_list[-1]
        step = abs(price_list[1] - price_list[0]) if len(price_list) > 1 else 0
        
        # Hedge-Preis berechnen
        if self.grid_direction == "long":
            hedge_price = lower_bound - step
        elif self.grid_direction == "short":
            hedge_price = upper_bound + step
        else:
            return
        
        # PriceProtectScope prüfen
        scope = self.hedge_manager.price_protect_scope or 0.05
        min_price = current_price * (1 - scope)
        max_price = current_price * (1 + scope)
        
        # Prüfe ob Hedge JETZT platzierbar ist
        is_within_scope = False
        
        if self.grid_direction == "long":
            is_within_scope = hedge_price >= min_price
        elif self.grid_direction == "short":
            is_within_scope = hedge_price <= max_price
        
        if is_within_scope:
            self.logger.info(
                f"[HEDGE] 🎯 Preis jetzt in Range für Hedge! "
                f"Live={current_price:.4f} | Hedge={hedge_price:.4f}"
            )
            
            self._update_and_hedge("price_in_range")


    def _place_entry(self, level: GridLevel) -> None:
        """Order platzieren mit RiskManager"""
        size = self.risk_manager.calculate_effective_size()
        if size <= 0:
            self.logger.warning("Effektive Ordergröße 0")
            return

        tp, sl = level.tp, level.sl
        if not self.risk_manager.validate_tp_sl(level.price, tp, sl, level.side):
            self.logger.error(f"TP/SL-Validierung fehlgeschlagen @ {level.price}")
            return

        # === VIRTUAL ORDER (Dry-Run) ===
        if self.trading.dry_run and self.virtual_manager:
            order_id = self.virtual_manager.place_order(
                side=level.side,
                order_type="LIMIT",
                qty=size,
                price=level.price,
                tp_price=tp,
                sl_price=sl,
                client_id=f"{self.trading.client_id_prefix}_{self.symbol}_{level.index}"
            )
            
            level.order_id = order_id
            level.active = True
            level.tp, level.sl = tp, sl
            
            # ✅ Formatierung außerhalb des f-strings
            tp_str = f"{tp:.4f}" if tp else "None"
            sl_str = f"{sl:.4f}" if sl else "None"

            
            self.logger.info(
                f"[VIRTUAL] 🟢 {level.side} @ {level.price:.4f} | "
                f"size={size} | TP={tp_str} | SL={sl_str}"
            )
            
            # Hedge updaten
            self._update_and_hedge("virtual_order_placed")
            return

        # === ECHTE ORDER (Live Mode) ===
        try:
            order_id = self.client.place_order(
                symbol=self.symbol,
                side=level.side,
                order_type="LIMIT",
                qty=size,
                price=level.price,
                trade_side="OPEN",
                tp_price=tp,
                sl_price=sl,
                tp_stop_type="MARK_PRICE",
                sl_stop_type="MARK_PRICE",
                client_id=f"{self.trading.client_id_prefix}_{self.symbol}_{level.index}"
            )

            level.order_id, level.active, level.tp, level.sl = order_id, True, tp, sl
            self.logger.info(f"[{self.symbol}] {level.side} Order @ {level.price:.4f} → ID={order_id}")
            
            self._update_and_hedge("order_placed")

        except Exception as e:
            raise OrderPlacementError(f"Order @ {level.price} fehlgeschlagen: {e}")
            
    def _update_net_position(self):
        """Summiert GEFÜLLTE Positionen + AKTIVE Orders für Hedge-Berechnung."""
        long_filled = sum(1 for lvl in self.levels if lvl.filled and lvl.side == "BUY")
        short_filled = sum(1 for lvl in self.levels if lvl.filled and lvl.side == "SELL")
        
        long_pending = sum(1 for lvl in self.levels if lvl.active and not lvl.filled and lvl.side == "BUY")
        short_pending = sum(1 for lvl in self.levels if lvl.active and not lvl.filled and lvl.side == "SELL")
        
        base_size = self.risk_manager.calculate_effective_size()
        
        self.net_position_size = (long_filled - short_filled + long_pending - short_pending) * base_size
        
        self.logger.debug(
            f"[HEDGE] Position-Status: "
            f"Filled(Long={long_filled} Short={short_filled}) "
            f"Pending(Long={long_pending} Short={short_pending}) "
            f"→ Net={self.net_position_size:.2f} (Base={base_size:.2f})"
        )

    def _update_and_hedge(self, trigger: str = "unknown"):
        """Zentrale Funktion für Net-Position + Hedge Update"""
        self._update_net_position()
        
        if abs(self.net_position_size) < 0.001:
            return
        
        # Grid-Bounds holen
        price_list = self.calculator.calculate_price_list()
        lower_bound = price_list[0]
        upper_bound = price_list[-1]
        step = abs(price_list[1] - price_list[0]) if len(price_list) > 1 else 0

        # Hedge-Preis berechnen
        if self.grid_direction == "long":
            hedge_price = lower_bound - step
        elif self.grid_direction == "short":
            hedge_price = upper_bound + step
        else:
            return

        # PriceProtectScope validieren
        live_price = getattr(self.hedge_manager, "live_price", None)
        if live_price:
            scope = self.hedge_manager.price_protect_scope or 0.05
            min_price = live_price * (1 - scope)
            max_price = live_price * (1 + scope)
            
            # ✅ NEU: Nur 1x warnen
            out_of_scope = False
            if self.grid_direction == "long" and hedge_price < min_price:
                out_of_scope = True
            elif self.grid_direction == "short" and hedge_price > max_price:
                out_of_scope = True
            
            if out_of_scope:
                # Nur loggen wenn noch nicht geloggt
                last_warning = getattr(self, "_last_hedge_warning", None)
                if last_warning != (hedge_price, trigger):
                    self.logger.warning(
                        f"[HEDGE] Preis {hedge_price:.4f} außerhalb PriceProtectScope "
                        f"({min_price:.4f} - {max_price:.4f}) → Warte ({trigger})"
                    )
                    self._last_hedge_warning = (hedge_price, trigger)
                return

        # Hedge platzieren
        self.hedge_manager.update_preemptive_hedge(
            net_position_size=self.net_position_size,
            dry_run=self.trading.dry_run,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            step=step
        )


    def handle_order_fill(self, level: GridLevel):
        """
        Behandelt gefüllte Grid-Order
        ✅ Markiert Position als OFFEN
        ✅ Updated Hedge
        ❌ Macht KEIN Rebuy (erst nach TP/SL-Close)
        """
        try:
            # Position als offen markieren
            level.filled = True
            level.active = False
            level.position_open = True  # ← NEU!
            
            self.logger.info(
                f"🎯 Grid #{level.index} @ {level.price:.4f} FILLED "
                f"→ Position OPEN (warte auf TP/SL)"
            )
            
            # Hedge aktualisieren
            self._update_and_hedge("order_filled")
            
        except Exception as e:
            self.logger.error(f"❌ Fill-Handler Fehler: {e}")

    def handle_position_close(self, position_data: Dict[str, Any]):
        """
        Behandelt geschlossene Position (TP/SL getriggert)
        ✅ Gibt Level für Rebuy frei
        ✅ Platziert neue Order wenn active_rebuy=true
        """
        try:
            entry_value = float(position_data.get("entryValue", 0))
            
            # Finde zugehöriges Level
            matched_level = None
            for lvl in self.levels:
                if lvl.position_open and abs(lvl.price - entry_value) < 0.001:
                    matched_level = lvl
                    break
            
            if not matched_level:
                self.logger.warning(
                    f"⚠️ Keine offene Grid-Position für Entry {entry_value:.4f}"
                )
                return
            
            # Level freigeben
            matched_level.position_open = False
            matched_level.position_id = None
            matched_level.filled = False
            
            self.logger.info(
                f"✅ Grid #{matched_level.index} @ {matched_level.price:.4f} "
                f"→ Position geschlossen, Level FREI"
            )
            
            # Rebuy nur wenn aktiviert UND Level jetzt frei
            if self.grid_conf.active_rebuy and not matched_level.position_open:
                self.logger.info(f"🔄 Rebuy @ {matched_level.price:.4f}")
                time.sleep(0.1)  # Kurze Pause
                self._place_entry(matched_level)
            
            # Hedge aktualisieren
            self._update_and_hedge("position_closed")
            
        except Exception as e:
            self.logger.error(f"❌ Position-Close Handler Fehler: {e}")

    def handle_order_cancel(self, level: GridLevel):
        """Wird von AccountSync aufgerufen wenn Order cancelled wird"""
        level.active = False
        level.order_id = None
        
        self.logger.info(f"🔴 Level #{level.index} cancelled @ {level.price}")
        
        self._update_and_hedge("order_cancelled")


    def handle_error(self, error: Exception):
        msg = f"{type(error).__name__}: {error}"
        self.logger.exception(f"[{self.symbol}] Fehler: {msg}")
        self.lifecycle.set_state(GridState.ERROR, message=msg)

    def pause(self, reason: str = None):
        self.logger.warning(f"[{self.symbol}] Grid pausiert: {reason or ''}")
        try:
            self.lifecycle.set_state(GridState.PAUSED, message=reason)
        except ValueError as e:
            self.logger.error(f"Pause-Fehler: {e}")

    def resume(self):
        try:
            self.lifecycle.set_state(GridState.ACTIVE)
            self.logger.info(f"[{self.symbol}] Grid aktiv")
        except ValueError as e:
            self.logger.error(f"Resume-Fehler: {e}")

    def stop(self):
        """Grid stoppen"""
        try:
            # === NEU: Virtual Stats ausgeben ===
            if self.trading.dry_run and self.virtual_manager:
                self.logger.info("")  # Leerzeile
                self.virtual_manager.print_stats()
            
            self.lifecycle.set_state(GridState.CLOSED)
            self.logger.info(f"[{self.symbol}] Grid geschlossen")
        except ValueError as e:
            self.logger.error(f"Stop-Fehler: {e}")

    def _on_state_change(self, old_state: GridState, new_state: GridState, message: str = None):
        self.logger.info(f"[{self.symbol}] {old_state.value} → {new_state.value}")
        if new_state == GridState.ERROR:
            self._handle_critical_error(message)
        elif new_state == GridState.CLOSED:
            self._cleanup()

    def _handle_critical_error(self, message: str):
        self.logger.error(f"[{self.symbol}] Kritischer Fehler: {message}")

    def _cleanup(self):
        self.logger.debug(f"[{self.symbol}] Cleanup")

    def print_grid_status(self):
        """Loggt Grid-Status nur bei Änderungen"""
        total = len(self.levels)
        active = sum(1 for l in self.levels if l.active)
        filled = sum(1 for l in self.levels if l.filled)
        hedge_status = "✅" if getattr(self.hedge_manager, "active", False) else "⏸️"
        
        # ✅ NEU: Nur bei Änderung loggen
        current_state = (active, filled, self.net_position_size, hedge_status)
        last_state = getattr(self, "_last_status_log", None)
        
        if current_state == last_state:
            return  # Keine Änderung → Skip
        
        self._last_status_log = current_state
        
        # Virtual Stats
        if self.trading.dry_run and self.virtual_manager:
            stats = self.virtual_manager.get_stats()
            self.logger.info(
                f"📊 {self.symbol} | Active: {active}/{total} | Filled: {filled} | "
                f"Net: {self.net_position_size:.2f} | Hedge: {hedge_status} | "
                f"PnL: {stats['total_pnl']:+.2f} USDT ({stats['win_rate']:.0f}% WR)"
            )
        else:
            self.logger.info(
                f"📊 {self.symbol} | Active: {active}/{total} | Filled: {filled} | "
                f"Net: {self.net_position_size:.2f} | Hedge: {hedge_status}"
            )


    def log_summary(self) -> None:
        """Erweiterte Summary mit Risk-Info"""
        self.logger.info("=" * 60)
        self.logger.info(
            f"GRID SUMMARY ({self.symbol}) "
            f"{'🛡️  === DRY-RUN === 🛡️' if self.trading.dry_run else '⚠️ === REAL MODE === ⚠️'}"
        )
        self.logger.info("=" * 60)
        self.logger.info(f"Direction  : {self.grid_direction.upper()}")
        self.logger.info(f"Margin Mode: {self.margin_mode.upper()}")
        self.logger.info(f"Leverage   : {self.leverage}")
        self.logger.info(f"Mode       : {self.grid_conf.grid_mode.value}")
        self.logger.info(
            f"Levels     : {len(self.levels)} "
            f"({self.grid_conf.lower_price} → {self.grid_conf.upper_price})"
        )
        self.logger.info(f"Base Size  : {self.grid_conf.base_order_size}")
        self.logger.info(f"Active Rebuy: {self.grid_conf.active_rebuy}")
        
        # Risk-Summary
        try:
            risk_info = self.risk_manager.get_risk_summary()
            self.logger.info(f"Take Profit: {risk_info['tp_mode']}")
            if risk_info.get('tp_pct'):
                self.logger.info(f"TP %       : {risk_info['tp_pct']*100:.2f}%")
            self.logger.info(f"Stop Loss  : {risk_info['sl_mode']}")
            if risk_info.get('sl_pct'):
                self.logger.info(f"SL %       : {risk_info['sl_pct']*100:.2f}%")
            if risk_info.get('sl_price'):
                self.logger.info(f"SL Price   : {risk_info['sl_price']}")
            
            fee_info = self.risk_manager.get_fee_info()
            self.logger.info(
                f"Fees       : {'Included' if fee_info['include_fees'] else 'Ignored'} "
                f"({fee_info['fee_side']})"
            )
        except Exception as e:
            self.logger.warning(f"⚠️ Risk-Summary fehlt: {e}")
        
        self.logger.info("=" * 60)

    async def sync_orders(self, dry_run=None):
        if dry_run is None:
            dry_run = self.trading.dry_run
        self.logger.info(f"[{self.symbol}] OrderSync {'Dry-Run' if dry_run else 'Real'}")
        async with self._levels_lock:
            result = await self.order_sync.sync_orders(dry_run=dry_run)
        self.logger.info(f"[{self.symbol}] Sync: {result}")
        return result

    def attach_account_sync(self, account_sync):
        self.account_sync = account_sync
        account_sync.grid_manager = self
        self.order_sync.fetch_orders_callback = lambda: list(account_sync.orders.values())
        self.logger.info(f"[{self.symbol}] OrderSync ↔ AccountSync")

    def setup_margin(self):
        if self.trading.dry_run:
            return
        try:
            self.client.change_margin_mode(symbol=self.symbol, margin_mode=self.margin_mode.upper())
            self.client.change_leverage(symbol=self.symbol, leverage=self.leverage)
        except Exception as e:
            self.logger.warning(f"[{self.symbol}] ⚠️ Margin-Setup fehlgeschlagen: {e}")