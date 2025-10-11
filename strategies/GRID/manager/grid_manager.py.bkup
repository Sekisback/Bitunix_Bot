# -*- coding: utf-8 -*-
import logging
import time
from dataclasses import dataclass
from typing import List, Optional, Dict
from datetime import datetime
from .grid_lifecycle import GridLifecycle, GridState
from .order_sync import OrderSync

# === NEU: Enum-Imports für Config-Validierung ===
import sys
from pathlib import Path
GRID_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(GRID_DIR))
from models.config_models import GridMode, TPMode, SLMode


# =============================================================================
# Dataclass: GridLevel
# =============================================================================
@dataclass
class GridLevel:
    """
    Datenstruktur für ein einzelnes Grid-Level.
    """
    index: int
    price: float
    side: str                    # "BUY" oder "SELL"
    order_id: Optional[str] = None
    active: bool = False
    filled: bool = False
    tp: Optional[float] = None
    sl: Optional[float] = None

    def __repr__(self) -> str:
        status = "FILLED" if self.filled else ("ACTIVE" if self.active else "IDLE")
        return f"<GridLevel #{self.index} {self.side} @ {self.price} [{status}]>"


# =============================================================================
# Class: GridManager
# =============================================================================
class GridManager:
    """
    Zentrale Logik für Grid-Trading auf Bitunix.
    Verwaltet Grid-Level, Orderplatzierung, TP/SL und Lifecycle.
    """

    def __init__(self, client, config):
        """
        Initialisiert GridManager mit Pydantic-Config
        
        Args:
            client: HTTP-Client für Order-Platzierung
            config: GridBotConfig (Pydantic-Objekt)
        """
        self.client = client
        self.config = config

        # === Kurzreferenzen (jetzt Pydantic-Objekte) ===
        self.symbol: str = config.symbol
        self.trading = config.trading      # TradingConfig
        self.grid_conf = config.grid       # GridConfig
        self.risk_conf = config.risk       # RiskConfig
        self.strategy = config.strategy    # StrategyConfig
        self.system = config.system        # SystemConfig

        # Richtung (direkter Zugriff auf Enum)
        self.grid_direction: str = self.trading.grid_direction.value
        self.grid_mode: str = self.grid_direction

        # Laufzeit-Daten
        self.levels: List[GridLevel] = []
        self._price_list: List[float] = []
        self.last_rebalance: float = 0.0

        # Logging
        self.logger = logging.getLogger(f"GridManager-{self.symbol}")
        level_name = self.system.log_level.upper()
        self.logger.setLevel(getattr(logging, level_name, logging.INFO))

        # === Lifecycle ===
        self.lifecycle = GridLifecycle(self.symbol, on_state_change=self._on_state_change)

        # Debug-Ausgabe
        raw_dry = self.trading.dry_run
        self.logger.info(f"[{self.symbol}] ⚙️ Trading-Block geladen: {self.trading}")
        self.logger.info(f"[{self.symbol}] ⚙️ Dry-Run Wert: {raw_dry!r} (Typ: {type(raw_dry).__name__})")

        try:
            # Initialer Aufbau
            self.validate_config()
            self._build_price_list()
            self._create_grid_levels()
            self.last_rebalance = time.time()
            self.log_summary()

            # Aktivieren
            self.lifecycle.set_state(GridState.ACTIVE)
            self.logger.info(f"[{self.symbol}] GridManager aktiv")

            # === TP/SL vorberechnen ===
            for lvl in self.levels:
                lvl.tp = self._take_profit_for(lvl.price, lvl.index, lvl.side)
                lvl.sl = self._stop_loss_for(lvl.price, lvl.side)

            # === Order-Sync vorbereiten ===
            self.order_sync = OrderSync(
                symbol=self.symbol,
                levels=self.levels,
                logger=self.logger,
                client=self.client,
                size=self._effective_order_size(),
                grid_direction=self.grid_direction,
            )

        except Exception as e:
            self.lifecycle.set_state(GridState.ERROR, message=f"Init-Fehler: {e}")
            raise

    # -------------------------------------------------------------------------
    # Config-Validierung
    # -------------------------------------------------------------------------
    def validate_config(self) -> None:
        """
        Prüft Config-Plausibilität
        Pydantic hat bereits die meisten Checks gemacht, 
        hier nur noch Business-Logic
        """
        lower = self.grid_conf.lower_price
        upper = self.grid_conf.upper_price
        n = self.grid_conf.grid_levels

        # Preisbereich bereits von Pydantic geprüft
        if upper <= lower:
            raise ValueError(
                f"upper_price ({upper}) muss größer als lower_price ({lower}) sein"
            )

        if n < 2:
            raise ValueError(f"grid_levels ({n}) muss mindestens 2 sein")

        tick = float(self.grid_conf.min_price_step)
        if tick <= 0.0:
            raise ValueError(f"min_price_step ({tick}) muss > 0 sein")

    # -------------------------------------------------------------------------
    # Preisraster
    # -------------------------------------------------------------------------
    def _build_price_list(self) -> None:
        """Baut Preisraster basierend auf grid_mode"""
        lower = float(self.grid_conf.lower_price)
        upper = float(self.grid_conf.upper_price)
        n = int(self.grid_conf.grid_levels)

        # Enum-Vergleich statt String
        if self.grid_conf.grid_mode == GridMode.ARITHMETIC:
            step = (upper - lower) / n
            prices = [lower + i * step for i in range(n + 1)]
        elif self.grid_conf.grid_mode == GridMode.GEOMETRIC:
            ratio = (upper / lower) ** (1.0 / n)
            prices = [lower * (ratio ** i) for i in range(n + 1)]
        else:
            raise ValueError(f"Unbekannter grid_mode: {self.grid_conf.grid_mode}")

        prices = [self._round_to_tick(p) for p in prices]
        self._price_list = prices
        self.logger.info(f"Preisraster erstellt: {len(prices)} Levels")

    # -------------------------------------------------------------------------
    # GridLevel erzeugen
    # -------------------------------------------------------------------------
    def _create_grid_levels(self) -> None:
        """Erstellt GridLevel-Objekte basierend auf grid_direction"""
        lower = self.grid_conf.lower_price
        upper = self.grid_conf.upper_price
        mid = (lower + upper) / 2.0

        self.levels = []

        for i, p in enumerate(self._price_list):
            if self.grid_direction == "long":
                side = "BUY"
            elif self.grid_direction == "short":
                side = "SELL"
            else:  # both
                side = "BUY" if p <= mid else "SELL"

            self.levels.append(GridLevel(index=i, price=p, side=side))

        self.logger.info(f"{len(self.levels)} GridLevel-Objekte erstellt ({self.grid_direction}).")

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _round_to_tick(self, price: float) -> float:
        """Rundet Preis auf min_price_step"""
        tick = float(self.grid_conf.min_price_step)
        return round(round(price / tick) * tick, 12)

    def _effective_order_size(self) -> float:
        """
        Berechnet effektive Ordergröße inkl. Gebühren
        """
        base_size = float(self.grid_conf.base_order_size)
        if base_size <= 0.0:
            self.logger.error("base_order_size <= 0 – keine Order möglich.")
            return 0.0

        if self.risk_conf.include_fees:
            # fee_side ist jetzt ein String (kein Enum)
            fee_side = self.risk_conf.fee_side.lower()
            fee_pct = (
                self.risk_conf.maker_fee_pct 
                if fee_side == "maker" 
                else self.risk_conf.taker_fee_pct
            )
            # Doppelte Gebühr (Entry + Exit)
            effective_fee = fee_pct * 2.0
            size = base_size * (1.0 - effective_fee)
            self.logger.debug(
                f"[FeeCalc] base={base_size} fee_side={fee_side} fee_pct={fee_pct} "
                f"x2={effective_fee:.6f} → effective_size={size:.8f}"
            )
        else:
            size = base_size

        return max(0.0, round(size, 8))

    # -------------------------------------------------------------------------
    # Rebalancing
    # -------------------------------------------------------------------------
    def _maybe_rebalance(self) -> None:
        """Prüft ob Rebalancing fällig ist"""
        now = time.time()
        interval = int(self.grid_conf.rebalance_interval)
        if now - self.last_rebalance >= interval:
            self.logger.info("Rebalancing: Preisraster neu erstellt.")
            self._build_price_list()
            self._create_grid_levels()
            self.last_rebalance = now

    # -------------------------------------------------------------------------
    # Haupt-Update
    # -------------------------------------------------------------------------
    def update(self, current_price: float) -> None:
        """Zyklischer Update-Call pro Candle"""
        try:
            if not self.lifecycle.is_active():
                self.logger.debug("Grid pausiert – update() übersprungen.")
                return

            # Standard-Grid-Logik
            self._maybe_rebalance()
            entry_on_touch = bool(self.strategy.entry_on_touch)
            if not entry_on_touch:
                return

            allow_long = self.grid_direction in ("long", "both")
            allow_short = self.grid_direction in ("short", "both")

            for lvl in self.levels:
                if lvl.active or lvl.filled:
                    continue
                if lvl.side == "BUY" and allow_long and current_price <= lvl.price:
                    self._place_entry(lvl)
                elif lvl.side == "SELL" and allow_short and current_price >= lvl.price:
                    self._place_entry(lvl)

        except Exception as e:
            self.logger.error(f"Update-Fehler: {e}")
            self.lifecycle.set_state(GridState.ERROR, str(e))

    # -------------------------------------------------------------------------
    # TP / SL Berechnung
    # -------------------------------------------------------------------------
    def _take_profit_for(self, entry_price: float, level_index: int, side: str = "BUY") -> Optional[float]:
        """
        Berechnet Take-Profit basierend auf tp_mode
        """
        # Enum-Vergleich statt String
        if self.grid_conf.tp_mode == TPMode.NEXT_GRID:
            # === LONG / BUY ===
            if side.upper() == "BUY":
                if level_index < len(self._price_list) - 1:
                    tp = self._price_list[level_index + 1]
                else:
                    step = self._price_list[-1] - self._price_list[-2]
                    tp = entry_price + step
            
            # === SHORT / SELL ===
            else:
                if level_index > 0:
                    tp = self._price_list[level_index - 1]
                else:
                    step = self._price_list[1] - self._price_list[0]
                    tp = entry_price - step
        
        elif self.grid_conf.tp_mode == TPMode.PERCENT:
            pct = float(self.grid_conf.take_profit_pct)
            if side.upper() == "BUY":
                tp = entry_price * (1.0 + pct)
            else:
                tp = entry_price * (1.0 - pct)
        else:
            return None

        return self._round_to_tick(tp)

    def _stop_loss_for(self, entry_price: float, side: str = "BUY") -> Optional[float]:
        """
        Berechnet Stop-Loss basierend auf sl_mode
        """
        # Enum-Vergleich statt String
        if self.grid_conf.sl_mode == SLMode.NONE:
            return None

        elif self.grid_conf.sl_mode == SLMode.FIXED:
            fixed = self.grid_conf.stop_loss_price
            return self._round_to_tick(float(fixed)) if fixed is not None else None

        elif self.grid_conf.sl_mode == SLMode.PERCENT:
            pct = float(self.grid_conf.stop_loss_pct)
            sl = entry_price * (1.0 - pct) if side.upper() == "BUY" else entry_price * (1.0 + pct)
            return self._round_to_tick(sl)
        
        else:
            return None

    # -------------------------------------------------------------------------
    # Order-Logik
    # -------------------------------------------------------------------------
    def _place_entry(self, level: GridLevel) -> None:
        """Platziert Entry-Order für ein Grid-Level"""
        size = self._effective_order_size()
        if size <= 0:
            self.logger.warning("Effektive Ordergröße 0 – keine Order.")
            return

        tp = level.tp
        sl = level.sl

        # Dry-Run Check (direkter bool-Zugriff)
        if self.trading.dry_run:
            self.logger.info(
                f"[SIM] {level.side} {self.symbol} @ {level.price} | "
                f"size={size} | TP={tp} | SL={sl}"
            )
            level.active, level.tp, level.sl = True, tp, sl
            return

        try:
            order_id = self.client.place_order(
                symbol=self.symbol,
                side=level.side,
                price=level.price,
                size=size,
                take_profit=tp,
                stop_loss=sl,
                client_id_prefix=self.trading.client_id_prefix,
                reduce_only=self.config.margin.auto_reduce_only,
                leverage=self.config.margin.leverage,
                margin_mode=self.config.margin.mode,
            )
            level.order_id, level.active, level.tp, level.sl = order_id, True, tp, sl
            self.logger.info(f"{level.side} Order platziert: id={order_id} @ {level.price}")
        except Exception as e:
            self.handle_error(e)

    # -------------------------------------------------------------------------
    # Lifecycle Handling
    # -------------------------------------------------------------------------
    def handle_error(self, error: Exception):
        """Fehlerbehandlung"""
        msg = f"{type(error).__name__}: {error}"
        self.logger.exception(f"[{self.symbol}] Fehler im Grid: {msg}")
        self.lifecycle.set_state(GridState.ERROR, message=msg)

    def pause(self, reason: str = None):
        """Pausiert das Grid"""
        self.logger.warning(f"[{self.symbol}] Grid pausiert: {reason or 'kein Grund angegeben'}")
        try:
            self.lifecycle.set_state(GridState.PAUSED, message=reason)
        except ValueError as e:
            self.logger.error(f"[{self.symbol}] Pause-Fehler: {e}")

    def resume(self):
        """Aktiviert das Grid wieder"""
        try:
            self.lifecycle.set_state(GridState.ACTIVE)
            self.logger.info(f"[{self.symbol}] Grid wieder aktiv.")
        except ValueError as e:
            self.logger.error(f"[{self.symbol}] Resume-Fehler: {e}")

    def stop(self):
        """Beendet das Grid"""
        try:
            self.lifecycle.set_state(GridState.CLOSED)
            self.logger.info(f"[{self.symbol}] Grid geschlossen.")
        except ValueError as e:
            self.logger.error(f"[{self.symbol}] Stop-Fehler: {e}")

    def _on_state_change(self, old_state: GridState, new_state: GridState, message: str = None):
        """Callback bei State-Änderung"""
        self.logger.info(f"[{self.symbol}] Lifecycle: {old_state.value} → {new_state.value} ({message or ''})")
        if new_state == GridState.ERROR:
            self._handle_critical_error(message)
        elif new_state == GridState.CLOSED:
            self._cleanup()

    def _handle_critical_error(self, message: str):
        """Behandelt kritische Fehler"""
        self.logger.error(f"[{self.symbol}] Kritischer Fehler: {message}")

    def _cleanup(self):
        """Cleanup beim Beenden"""
        self.logger.debug(f"[{self.symbol}] Grid Cleanup abgeschlossen")

    # -------------------------------------------------------------------------
    # Status / Debug
    # -------------------------------------------------------------------------
    def print_grid_status(self):
        """Kompakte Übersicht aller Grid-Level"""
        total = len(self.levels)
        active = sum(1 for l in self.levels if l.active)
        filled = sum(1 for l in self.levels if l.filled)

        self.logger.info(f"📊 {self.symbol} | Active: {active}/{total} | Filled: {filled}")

    # -------------------------------------------------------------------------
    # Info & Debug
    # -------------------------------------------------------------------------
    def log_summary(self) -> None:
        """Loggt Grid-Zusammenfassung"""
        self.logger.info("=" * 60)
        self.logger.info(f"=== GRID SUMMARY ({self.symbol}) ===")
        self.logger.info("=" * 60)
        self.logger.info(f"Grid Direction: {self.grid_direction}")
        
        # Bei Logging: .value verwenden für String-Ausgabe
        self.logger.info(f"Grid Mode: {self.grid_conf.grid_mode.value}")
        
        self.logger.info(
            f"Levels: {len(self.levels)} "
            f"({self.grid_conf.lower_price} → {self.grid_conf.upper_price})"
        )
        self.logger.info(f"Base Size: {self.grid_conf.base_order_size}")
        
        # Bei Logging: .value verwenden
        self.logger.info(
            f"TP: {self.grid_conf.tp_mode.value} | "
            f"SL: {self.grid_conf.sl_mode.value}"
        )
        
        self.logger.info(
            f"Fees: include={self.risk_conf.include_fees} "
            f"side={self.risk_conf.fee_side}"
        )
        self.logger.info(f"Rebalance Interval: {self.grid_conf.rebalance_interval}s")

    # -------------------------------------------------------------------------
    # Order-Sync / WS-Abgleich
    # -------------------------------------------------------------------------
    async def sync_orders(self, dry_run=None):
        """
        Führt Order-Sync durch
        
        Args:
            dry_run: True = nur prüfen, False = echte Aktionen
        """
        # Wenn kein Wert übergeben wird, nimm aus Config
        if dry_run is None:
            dry_run = self.trading.dry_run

        self.logger.info(
            f"[{self.symbol}] Starte OrderSync — "
            f"Modus: {'Dry-Run' if dry_run else 'Real'}"
        )

        result = await self.order_sync.sync_orders(dry_run=dry_run)
        self.logger.info(f"[{self.symbol}] OrderSync-Ergebnis: {result}")
        return result

    # -------------------------------------------------------------------------
    # AccountSync-Verknüpfung
    # -------------------------------------------------------------------------
    def attach_account_sync(self, account_sync):
        """
        Verknüpft GridManager mit AccountSync für Order-Caching
        """
        self.account_sync = account_sync
        self.order_sync.fetch_orders_callback = lambda: list(account_sync.orders.values())
        self.logger.info(f"[{self.symbol}] OrderSync mit AccountSync verbunden.")
