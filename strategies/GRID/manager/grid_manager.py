# -*- coding: utf-8 -*-
# strategies/GRID/manager/grid_manager.py (Paket 4b)
"""
GridManager mit RiskManager-Integration
"""
from pathlib import Path
import sys

GRID_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(GRID_DIR))


import logging
import time
import asyncio
from dataclasses import dataclass
from typing import List, Optional
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
    active: bool = False
    filled: bool = False
    tp: Optional[float] = None
    sl: Optional[float] = None

    def __repr__(self) -> str:
        status = "FILLED" if self.filled else ("ACTIVE" if self.active else "IDLE")
        return f"<GridLevel #{self.index} {self.side} @ {self.price} [{status}]>"


class GridManager:
    def __init__(self, client, config, client_pub=None):
        """Initialisiert den GridManager inklusive HedgeManager"""
        self.client = client                     # immer private client
        self.config = config
        self.client_pub = client_pub
        self.symbol: str = config.symbol
        self.trading = config.trading
        self.grid_conf = config.grid
        self.risk_conf = config.risk
        self.strategy = config.strategy
        self.system = config.system

        # === Grid Direction (Enum oder String) ===
        raw_dir = self.trading.grid_direction
        if GridDirection and isinstance(raw_dir, GridDirection):
            self.grid_direction = raw_dir.value.lower()  # Enum → String ("long", "short", "both")
        else:
            self.grid_direction = str(raw_dir).strip().lower()

        self.grid_mode: str = self.grid_direction
        self.levels: list = []
        self.last_rebalance: float = 0.0
        self._levels_lock = asyncio.Lock()
        self.margin_mode = config.margin.mode
        self.leverage = config.margin.leverage

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

        # Dry-Run-Status an Hedge übergeben
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

            # ========== Initiale Grid-Orders platzieren ==========
            self._place_initial_grid_orders()

        except (InvalidGridConfigError, GridInitializationError) as e:
            self.lifecycle.set_state(GridState.ERROR, message=str(e))
            raise
        except Exception as e:
            self.lifecycle.set_state(GridState.ERROR, message=f"Init-Fehler: {e}")
            raise GridInitializationError(f"Grid-Initialisierung fehlgeschlagen: {e}")


    def _place_initial_grid_orders(self) -> None:
        """Platziert alle Grid-Orders initial (Real oder Dry-Run)"""
        allow_long = self.grid_direction in ("long", "both")
        allow_short = self.grid_direction in ("short", "both")
        
        placed_count = 0
        
        for lvl in self.levels:
            if lvl.active or lvl.filled:
                continue
            
            if lvl.side == "BUY" and not allow_long:
                continue
            if lvl.side == "SELL" and not allow_short:
                continue
            
            try:
                self._place_entry(lvl)
                placed_count += 1
            except Exception as e:
                self.logger.error(f"❌ Initial Order @ {lvl.price} fehlgeschlagen: {e}")
        
        mode = "Dry-Run" if self.trading.dry_run else "Real"
        self.logger.info(f"[ORDER] {placed_count}/{len(self.levels)} Grid-Orders platziert ({mode})")

        # === Debug-Log hinzufügen ===
        self.logger.info(f"[DEBUG] Rufe _update_net_position() auf...")
        
        # === Hedge mit Grid-Bounds aktualisieren ===
        self._update_net_position()
        price_list = self.calculator.calculate_price_list()
        lower_bound = price_list[0]
        upper_bound = price_list[-1]
        step = abs(price_list[1] - price_list[0]) if len(price_list) > 1 else 0

        self.hedge_manager.update_preemptive_hedge(
            net_position_size=self.net_position_size,
            dry_run=self.trading.dry_run,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            step=step
        )

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
        """Hauptupdate pro Tick – prüft Orders und Entry-Trigger (ohne Hedge/Config.grid_step)."""
        try:
            if not self.lifecycle.is_active():
                return

            # Letzten Preis speichern (für Hedge-Module)
            self.hedge_manager.live_price = current_price
            # Rebalancing ggf. ausführen
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

            # === 🛡️ Hedge-Check am Ende ===
            price_list = self.calculator.calculate_price_list()
            if len(price_list) < 2:
                step = 0.0
            else:
                step = abs(price_list[1] - price_list[0])

            lower_bound = price_list[0]
            upper_bound = price_list[-1]

            self.hedge_manager.check_trigger(current_price, lower_bound, upper_bound, step)

            # 🔹 Falls beim Start kein Hedge platziert wurde (z. B. kein Live-Preis verfügbar)
            if not getattr(self.hedge_manager, "active", False):
                self.hedge_manager.update_preemptive_hedge(
                    net_position_size=getattr(self, "net_position_size", 0),
                    dry_run=self.trading.dry_run,
                    lower_bound=lower_bound,
                    upper_bound=upper_bound,
                    step=step,
                )


        except Exception as e:
            self.logger.error(f"Update-Fehler: {e}")
            self.lifecycle.set_state(GridState.ERROR, str(e))


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

        if self.trading.dry_run:
            self.logger.info(f"[ORDER] {level.side} @ {level.price:.4f} | size={size} | TP={tp:.4f} | SL={f'{sl:.4f}' if isinstance(sl, float) else sl}")
            level.active, level.tp, level.sl = True, tp, sl
            return

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

        except Exception as e:
            raise OrderPlacementError(f"Order @ {level.price} fehlgeschlagen: {e}")
        

    def _update_net_position(self):
        """Summiert alle AKTIVEN (nicht gefüllten) Long/Short-Level für Hedge."""
        # Nur AKTIVE Orders zählen (nicht gefüllte!)
        long_pos = sum(1 for lvl in self.levels if lvl.active and not lvl.filled and lvl.side == "BUY")
        short_pos = sum(1 for lvl in self.levels if lvl.active and not lvl.filled and lvl.side == "SELL")
        base_size = self.risk_manager.calculate_effective_size()
        self.net_position_size = (long_pos - short_pos) * base_size
        
        # === Debug-Log ===
        self.logger.info(
            f"[HEDGE] Aktive Orders: Long={long_pos} Short={short_pos} "
            f"→ Net={self.net_position_size:.2f}"
        )


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
        try:
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
        total = len(self.levels)
        active = sum(1 for l in self.levels if l.active)
        filled = sum(1 for l in self.levels if l.filled)
        self.logger.info(f"📊 {self.symbol} | Active: {active}/{total} | Filled: {filled}")

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
        
        # === NEU: Risk-Summary ===
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
