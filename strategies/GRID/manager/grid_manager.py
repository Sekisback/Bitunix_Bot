# -*- coding: utf-8 -*-
import logging
import time
from dataclasses import dataclass
from typing import List, Optional, Dict
from datetime import datetime
from .grid_lifecycle import GridLifecycle, GridState
from .order_sync import OrderSync


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

    def __init__(self, client, config: Dict):
        self.client = client
        self.config = config

        # Kurzreferenzen
        self.symbol: str = config["symbol"]
        self.trading: Dict = config["trading"]
        self.grid_conf: Dict = config["grid"]
        self.risk_conf: Dict = config["risk"]
        self.strategy: Dict = config.get("strategy", {})
        self.system: Dict = config.get("system", {})

        # Richtung (Kompatibilität zu älteren Versionen)
        self.grid_direction: str = self.trading.get("grid_direction", "both")
        self.grid_mode: str = self.grid_direction

        # Laufzeit-Daten
        self.levels: List[GridLevel] = []
        self._price_list: List[float] = []
        self.last_rebalance: float = 0.0

        # Logging
        self.logger = logging.getLogger(f"GridManager-{self.symbol}")
        level_name = self.system.get("log_level", "INFO").upper()
        self.logger.setLevel(getattr(logging, level_name, logging.INFO))

        # === Lifecycle ===
        self.lifecycle = GridLifecycle(self.symbol, on_state_change=self._on_state_change)


        # Debug-Ausgabe für Dry-Run prüfen
        raw_dry = self.trading.get("dry_run", None)
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

            # === Order-Sync vorbereiten ===
            # TP/SL vorher berechnen und in die Level schreiben
            for lvl in self.levels:
                lvl.tp = self._take_profit_for(lvl.price, lvl.index, lvl.side)
                lvl.sl = self._stop_loss_for(lvl.price, lvl.side)


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
        lower = self.grid_conf.get("lower_price")
        upper = self.grid_conf.get("upper_price")
        n = int(self.grid_conf.get("grid_levels", 0))

        if lower is None or upper is None or (lower == 0.0 and upper == 0.0):
            self.logger.warning("Ungültige Price Range – Fallback 1.0 - 2.0")
            lower, upper = 1.0, 2.0
            self.grid_conf["lower_price"], self.grid_conf["upper_price"] = lower, upper

        if upper <= lower:
            self.logger.warning(f"Upper <= Lower – Fallback 1.0 - 2.0")
            lower, upper = 1.0, 2.0
            self.grid_conf["lower_price"], self.grid_conf["upper_price"] = lower, upper

        if n < 2:
            self.logger.warning("grid_levels < 2 – setze auf 10")
            self.grid_conf["grid_levels"] = 10

        tick = float(self.grid_conf.get("min_price_step", 0.0))
        if tick <= 0.0:
            self.logger.warning("min_price_step <= 0! Setze 1e-8")
            self.grid_conf["min_price_step"] = 1e-8

    # -------------------------------------------------------------------------
    # Preisraster
    # -------------------------------------------------------------------------
    def _build_price_list(self) -> None:
        lower = float(self.grid_conf["lower_price"])
        upper = float(self.grid_conf["upper_price"])
        n = int(self.grid_conf["grid_levels"])
        mode = self.grid_conf.get("grid_mode", "arithmetic")

        if mode == "arithmetic":
            step = (upper - lower) / n
            prices = [lower + i * step for i in range(n + 1)]
        elif mode == "geometric":
            ratio = (upper / lower) ** (1.0 / n)
            prices = [lower * (ratio ** i) for i in range(n + 1)]
        else:
            raise ValueError(f"Unbekannter grid_mode: {mode}")

        prices = [self._round_to_tick(p) for p in prices]
        self._price_list = prices
        self.logger.info(f"Preisraster erstellt: {prices}")

    # -------------------------------------------------------------------------
    # GridLevel erzeugen
    # -------------------------------------------------------------------------
    def _create_grid_levels(self) -> None:
        lower = self.grid_conf["lower_price"]
        upper = self.grid_conf["upper_price"]
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
        tick = float(self.grid_conf.get("min_price_step", 1e-8))
        return round(round(price / tick) * tick, 12)

    def _effective_order_size(self) -> float:
        """
        Berechnet die effektive Ordergröße unter Berücksichtigung der Gebühren.
        Wenn include_fees=True, wird automatisch die doppelte Gebühr (Entry + Exit)
        einbezogen, um den real verfügbaren Netto-Tradebetrag sicherzustellen.
        """
        base_size = float(self.grid_conf.get("base_order_size", 0.0))
        if base_size <= 0.0:
            self.logger.error("base_order_size <= 0 – keine Order möglich.")
            return 0.0

        if self.risk_conf.get("include_fees", True):
            fee_side = self.risk_conf.get("fee_side", "taker").lower()
            fee_pct = float(
                self.risk_conf.get(
                    "maker_fee_pct" if fee_side == "maker" else "taker_fee_pct",
                    0.0006,
                )
            )
            # doppelte Gebühr (Entry + Exit)
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
        now = time.time()
        interval = int(self.grid_conf.get("rebalance_interval", 300))
        if now - self.last_rebalance >= interval:
            self.logger.info("Rebalancing: Preisraster neu erstellt.")
            self._build_price_list()
            self._create_grid_levels()
            self.last_rebalance = now

    # -------------------------------------------------------------------------
    # Haupt-Update
    # -------------------------------------------------------------------------
    def update(self, current_price: float) -> None:
        """Zyklischer Update-Call pro Candle."""
        try:
            if not self.lifecycle.is_active():
                self.logger.debug("Grid pausiert – update() übersprungen.")
                return

            # ---------------------------------------------------------
            # TEST: künstlicher Fehler, um Auto-Recovery zu prüfen
            # ---------------------------------------------------------
            # import random
            # if random.random() < 0.02:
            #     raise RuntimeError("💥 Simulierter Testfehler im GridManager.update()")

            # === Standard-Grid-Logik ===
            self._maybe_rebalance()
            entry_on_touch = bool(self.strategy.get("entry_on_touch", True))
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
            self.logger.error(f"Callback error: {e}")
            # 🧩 NEU: Fehler an Lifecycle weitergeben
            self.lifecycle.set_state(GridState.ERROR, str(e))


    # -------------------------------------------------------------------------
    # TP / SL Berechnung
    # -------------------------------------------------------------------------
    def _take_profit_for(self, entry_price: float, level_index: int, side: str = "BUY") -> Optional[float]:
        """
        Berechnet den Take-Profit für ein Entry-Level abhängig von der Order-Richtung.
        - BUY → TP oberhalb des Entry-Preises (nächstes Grid-Level oder Prozent)
        - SELL → TP unterhalb des Entry-Preises (vorheriges Grid-Level oder Prozent)
        """
        mode = self.grid_conf.get("tp_mode", "percent")

        # === LONG / BUY ===
        if side.upper() == "BUY":
            if mode == "next_grid":
                # Nächstes Preislevel oder extrapolierter Grid-Schritt
                if level_index < len(self._price_list) - 1:
                    tp = self._price_list[level_index + 1]
                else:
                    step = self._price_list[-1] - self._price_list[-2]
                    tp = entry_price + step
            elif mode == "percent":
                pct = float(self.grid_conf.get("take_profit_pct", 0.003))
                tp = entry_price * (1.0 + pct)
            else:
                return None

        # === SHORT / SELL ===
        else:
            if mode == "next_grid":
                # Vorheriges Preislevel oder extrapolierter Grid-Schritt
                if level_index > 0:
                    tp = self._price_list[level_index - 1]
                else:
                    step = self._price_list[1] - self._price_list[0]
                    tp = entry_price - step
            elif mode == "percent":
                pct = float(self.grid_conf.get("take_profit_pct", 0.003))
                tp = entry_price * (1.0 - pct)
            else:
                return None

        return self._round_to_tick(tp)


    def _stop_loss_for(self, entry_price: float, side: str = "BUY") -> Optional[float]:
        """
        Berechnet den Stop-Loss abhängig von Entry-Richtung.
        - BUY → SL unterhalb des Entry-Preises
        - SELL → SL oberhalb des Entry-Preises
        """
        mode = self.grid_conf.get("sl_mode", "percent")
        if mode == "none":
            return None

        elif mode == "fixed":
            fixed = self.grid_conf.get("stop_loss_price")
            return self._round_to_tick(float(fixed)) if fixed is not None else None

        elif mode == "percent":
            pct = float(self.grid_conf.get("stop_loss_pct", 0.01))
            sl = entry_price * (1.0 - pct) if side.upper() == "BUY" else entry_price * (1.0 + pct)
            return self._round_to_tick(sl)

        else:
            return None


    # -------------------------------------------------------------------------
    # Order-Logik
    # -------------------------------------------------------------------------
    def _place_entry(self, level: GridLevel) -> None:
        size = self._effective_order_size()
        if size <= 0:
            self.logger.warning("Effektive Ordergröße 0 – keine Order.")
            return

        tp = self._take_profit_for(level.price, level.index)
        sl = self._stop_loss_for(level.price)

        if self.trading.get("dry_run", True):
            self.logger.info(
                f"[SIM] {level.side} {self.symbol} @ {level.price} | size={size} | TP={tp} | SL={sl}"
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
                client_id_prefix=self.trading.get("client_id_prefix", "GRID"),
                reduce_only=self.config.get("margin", {}).get("auto_reduce_only", False),
                leverage=self.config.get("margin", {}).get("leverage", self.trading.get("leverage", 1)),
                margin_mode=self.config.get("margin", {}).get("mode", "isolated"),
            )
            level.order_id, level.active, level.tp, level.sl = order_id, True, tp, sl
            self.logger.info(f"{level.side} Order platziert: id={order_id} @ {level.price}")
        except Exception as e:
            self.handle_error(e)

    # -------------------------------------------------------------------------
    # Lifecycle Handling
    # -------------------------------------------------------------------------
    def handle_error(self, error: Exception):
        msg = f"{type(error).__name__}: {error}"
        self.logger.exception(f"[{self.symbol}] Fehler im Grid: {msg}")
        self.lifecycle.set_state(GridState.ERROR, message=msg)

    def pause(self, reason: str = None):
        self.logger.warning(f"[{self.symbol}] Grid pausiert: {reason or 'kein Grund angegeben'}")
        try:
            self.lifecycle.set_state(GridState.PAUSED, message=reason)
        except ValueError as e:
            self.logger.error(f"[{self.symbol}] Pause-Fehler: {e}")

    def resume(self):
        try:
            self.lifecycle.set_state(GridState.ACTIVE)
            self.logger.info(f"[{self.symbol}] Grid wieder aktiv.")
        except ValueError as e:
            self.logger.error(f"[{self.symbol}] Resume-Fehler: {e}")

    def stop(self):
        try:
            self.lifecycle.set_state(GridState.CLOSED)
            self.logger.info(f"[{self.symbol}] Grid geschlossen.")
        except ValueError as e:
            self.logger.error(f"[{self.symbol}] Stop-Fehler: {e}")

    def _on_state_change(self, old_state: GridState, new_state: GridState, message: str = None):
        self.logger.info(f"[{self.symbol}] Lifecycle: {old_state.value} → {new_state.value} ({message or ''})")
        if new_state == GridState.ERROR:
            self._handle_critical_error(message)
        elif new_state == GridState.CLOSED:
            self._cleanup()

    def _handle_critical_error(self, message: str):
        self.logger.error(f"[{self.symbol}] Kritischer Fehler: {message}")

    def _cleanup(self):
        self.logger.debug(f"[{self.symbol}] Grid Cleanup abgeschlossen")

    # -------------------------------------------------------------------------
    # Status / Debug
    # -------------------------------------------------------------------------
    def print_grid_status(self):
        """Kompakte Übersicht aller Grid-Level."""
        total = len(self.levels)
        active = sum(1 for l in self.levels if l.active)
        filled = sum(1 for l in self.levels if l.filled)

        self.logger.info(f"📊 {self.symbol} | Active: {active}/{total} | Filled: {filled}")

    # -------------------------------------------------------------------------
    # Info & Debug
    # -------------------------------------------------------------------------
    def log_summary(self) -> None:
        self.logger.info("=" * 60)
        self.logger.info(f"=== GRID SUMMARY ({self.symbol}) ===")
        self.logger.info("=" * 60)
        self.logger.info(f"Grid Direction: {self.grid_direction}")
        self.logger.info(f"Grid Mode: {self.grid_conf.get('grid_mode')}")
        self.logger.info(f"Levels: {len(self.levels)} ({self.grid_conf['lower_price']} → {self.grid_conf['upper_price']})")
        self.logger.info(f"Base Size: {self.grid_conf.get('base_order_size')}")
        self.logger.info(f"TP: {self.grid_conf.get('tp_mode')} | SL: {self.grid_conf.get('sl_mode')}")
        self.logger.info(f"Fees: include={self.risk_conf.get('include_fees', True)} side={self.risk_conf.get('fee_side', 'taker')}")
        self.logger.info(f"Rebalance Interval: {self.grid_conf.get('rebalance_interval', 300)}s")

    # -------------------------------------------------------------------------
    # Order-Sync / WS-Abgleich
    # -------------------------------------------------------------------------
    async def sync_orders(self, dry_run=None):
        """
        Führt einen Order-Sync durch.
        dry_run=True -> Nur prüfen und loggen.
        dry_run=False -> Reale Order-Aktionen.
        """
        # Wenn kein Wert übergeben wird, nimm den aus der Trading-Config
        if dry_run is None:
            raw = self.trading.get("dry_run", True)
            # Robust casten (egal ob bool oder string)
            dry_run = str(raw).lower() in ("true", "1", "yes")

        self.logger.info(
            f"[{self.symbol}] Starte OrderSync — Modus: {'Dry-Run' if dry_run else 'Real'} "
            f"(raw={self.trading.get('dry_run')!r})"
        )

        result = await self.order_sync.sync_orders(dry_run=dry_run)
        self.logger.info(f"[{self.symbol}] OrderSync-Ergebnis: {result}")
        return result

    
    # -------------------------------------------------------------------------
    # AccountSync-Verknüpfung
    # -------------------------------------------------------------------------
    def attach_account_sync(self, account_sync):
        """
        Verknüpft den GridManager mit dem AccountSync, sodass OrderSync
        offene Orders über den WS-Cache abrufen kann.
        """
        self.account_sync = account_sync
        self.order_sync.fetch_orders_callback = lambda: list(account_sync.orders.values())
        self.logger.info(f"[{self.symbol}] OrderSync mit AccountSync verbunden.")
