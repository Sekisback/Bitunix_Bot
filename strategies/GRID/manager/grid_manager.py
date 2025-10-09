# -*- coding: utf-8 -*-
import logging
import time
from dataclasses import dataclass
from typing import List, Optional, Dict


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
    side: str                    # "BUY" oder "SELL" (Richtung der Entry-Order)
    order_id: Optional[str] = None
    active: bool = False         # Order ist aktiv/platziert
    filled: bool = False         # Order wurde gefüllt
    tp: Optional[float] = None   # Take-Profit-Preis
    sl: Optional[float] = None   # Stop-Loss-Preis

    def __repr__(self) -> str:
        status = "FILLED" if self.filled else ("ACTIVE" if self.active else "IDLE")
        return f"<GridLevel #{self.index} {self.side} @ {self.price} [{status}]>"


# =============================================================================
# Class: GridManager
# =============================================================================
class GridManager:
    """
    GridManager – zentrale Logik für Grid-Handel.
    Verwaltet Grid-Level, Platzierung von Orders, TP-/SL-Management
    und Rebalancing auf Basis der geladenen YAML-Konfiguration.
    """

    # -------------------------------------------------------------------------
    # Init
    # -------------------------------------------------------------------------
    def __init__(self, client, config: Dict):
        """
        Args:
            client: API-Client (dein Bitunix-Wrapper mit place_order(...))
            config: Gemergte Config aus base.yaml + <COIN>.yaml
        """
        self.client = client
        self.config = config

        # Kurzreferenzen
        self.symbol: str = config["symbol"]
        self.trading: Dict = config["trading"]
        self.grid_conf: Dict = config["grid"]
        self.risk_conf: Dict = config["risk"]
        self.strategy: Dict = config.get("strategy", {})
        self.system: Dict = config.get("system", {})

        # Backwards-Compat: einige ältere Codes erwarten self.grid_mode
        # (z. B. für "long"/"short"). In v2 nutzen wir trading.grid_direction.
        self.grid_direction: str = self.trading.get("grid_direction", "both")
        self.grid_mode: str = self.grid_direction  # Alias für Altcode

        # Laufzeit-Attribute
        self.levels: List[GridLevel] = []
        self._price_list: List[float] = []  # reine Liste der Level-Preise
        self.last_rebalance: float = 0.0

        # Logging
        self.logger = logging.getLogger(f"GridManager-{self.symbol}")
        level_name = self.system.get("log_level", "INFO").upper()
        self.logger.setLevel(getattr(logging, level_name, logging.INFO))
        #self.logger.debug("GridManager __init__ gestartet")

        # Validierung & Aufbau
        self.validate_config()
        self._build_price_list()
        self._create_grid_levels()
        self.last_rebalance = time.time()
        self.log_summary()

    # -------------------------------------------------------------------------
    # Config-Validierung
    # -------------------------------------------------------------------------
    def validate_config(self) -> None:
        lower = self.grid_conf.get("lower_price")
        upper = self.grid_conf.get("upper_price")
        n = int(self.grid_conf.get("grid_levels", 0))

        if lower is None or upper is None:
            raise ValueError("grid.lower_price und grid.upper_price müssen gesetzt sein.")
        if upper <= lower:
            raise ValueError("grid.upper_price muss größer als grid.lower_price sein.")
        if n < 2:
            raise ValueError("grid.grid_levels muss mindestens 2 sein.")

        tick = float(self.grid_conf.get("min_price_step", 0.0))
        if tick <= 0.0:
            self.logger.warning("min_price_step <= 0! Setze auf 0.00000001 (Failsafe).")
            self.grid_conf["min_price_step"] = 1e-8

    # -------------------------------------------------------------------------
    # Preisraster erstellen (Liste reiner Preise)
    # -------------------------------------------------------------------------
    def _build_price_list(self) -> None:
        lower = float(self.grid_conf["lower_price"])
        upper = float(self.grid_conf["upper_price"])
        n = int(self.grid_conf["grid_levels"])
        mode = self.grid_conf.get("grid_mode", "arithmetic")

        prices: List[float] = []
        if mode == "arithmetic":
            step = (upper - lower) / n
            prices = [lower + i * step for i in range(n + 1)]
        elif mode == "geometric":
            ratio = (upper / lower) ** (1.0 / n)
            prices = [lower * (ratio ** i) for i in range(n + 1)]
        else:
            raise ValueError(f"Unbekannter grid_mode: {mode}")

        # Tick-Rundung
        prices = [self._round_to_tick(p) for p in prices]
        self._price_list = prices
        self.logger.info(f"Preisraster erstellt: {prices}")

    # -------------------------------------------------------------------------
    # GridLevel-Objekte erzeugen
    # -------------------------------------------------------------------------
    def _create_grid_levels(self) -> None:
        """
        Erzeuge GridLevel-Objekte aus self._price_list.
        Seitenlogik (BUY/SELL):
          - Unterhalb der Mitte: BUY
          - Oberhalb der Mitte: SELL
          - Mitte: neutrales Level => wir geben BUY (long) den Vorzug,
            kann je nach Strategie angepasst werden.
        """
        mid = (self.grid_conf["lower_price"] + self.grid_conf["upper_price"]) / 2.0
        levels: List[GridLevel] = []
        for i, p in enumerate(self._price_list):
            side = "BUY" if p <= mid else "SELL"
            levels.append(GridLevel(index=i, price=p, side=side))
        self.levels = levels
        self.logger.info(f"{len(self.levels)} GridLevel-Objekte erstellt.")

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _round_to_tick(self, price: float) -> float:
        tick = float(self.grid_conf.get("min_price_step", 0.00000001))
        if tick <= 0:
            return price
        # Rundung auf Tick (vermeidet Floating-Fehler)
        rounded = round(round(price / tick) * tick, 12)
        return rounded

    def _effective_order_size(self) -> float:
        """
        Ordergröße inkl. Gebühren-Handling (wenn aktiviert).
        In base.yaml: risk.include_fees, maker_fee_pct, taker_fee_pct, fee_side
        """
        base_size = float(self.grid_conf.get("base_order_size", 0.0))
        if base_size <= 0:
            return 0.0

        if self.risk_conf.get("include_fees", True):
            fee_side = self.risk_conf.get("fee_side", "taker").lower()
            if fee_side == "maker":
                fee_pct = float(self.risk_conf.get("maker_fee_pct", 0.0002))
            else:
                fee_pct = float(self.risk_conf.get("taker_fee_pct", 0.0006))
            size = base_size * (1.0 - fee_pct)
        else:
            size = base_size

        return max(0.0, round(size, 8))

    # -------------------------------------------------------------------------
    # TP / SL
    # -------------------------------------------------------------------------
    def _take_profit_for(self, entry_price: float, level_index: int) -> Optional[float]:
        mode = self.grid_conf.get("tp_mode", "percent")
        if mode == "next_grid":
            if level_index < len(self._price_list) - 1:
                return self._round_to_tick(self._price_list[level_index + 1])
            # Fallback, falls oberstes Level: kleiner Aufschlag
            return self._round_to_tick(entry_price * 1.01)
        elif mode == "percent":
            pct = float(self.grid_conf.get("take_profit_pct", 0.003))
            return self._round_to_tick(entry_price * (1.0 + pct))
        else:
            # Kein TP
            return None

    def _stop_loss_for(self, entry_price: float) -> Optional[float]:
        mode = self.grid_conf.get("sl_mode", "percent")
        if mode == "none":
            return None
        elif mode == "fixed":
            fixed = self.grid_conf.get("stop_loss_price", None)
            return self._round_to_tick(float(fixed)) if fixed is not None else None
        elif mode == "percent":
            pct = float(self.grid_conf.get("stop_loss_pct", 0.01))
            return self._round_to_tick(entry_price * (1.0 - pct))
        else:
            return None

    # -------------------------------------------------------------------------
    # Rebalancing
    # -------------------------------------------------------------------------
    def _maybe_rebalance(self) -> None:
        now = time.time()
        interval = int(self.grid_conf.get("rebalance_interval", 300))
        if now - self.last_rebalance >= interval:
            self.logger.info("Rebalancing: Raster wird neu berechnet.")
            # Wir behalten aktive/gefüllte Flags NICHT über das Rebuild bei,
            # da das i. d. R. ein expliziter Reset ist. Bei Bedarf hier mappen.
            self._build_price_list()
            self._create_grid_levels()
            self.last_rebalance = now

    # -------------------------------------------------------------------------
    # Öffentliche API
    # -------------------------------------------------------------------------
    def update(self, current_price: float) -> None:
        """
        Haupt-Update. Wird vom Bot zyklisch aufgerufen (z. B. pro Candle).
        Platziert neue Pending-Orders auf relevanten Levels (touch-Logik),
        respektiert grid_direction (long/short/both) und dry_run.
        """
        self._maybe_rebalance()

        entry_on_touch = bool(self.strategy.get("entry_on_touch", True))
        if not entry_on_touch:
            return

        # Direction-Filter
        allow_long = self.grid_direction in ("long", "both")
        allow_short = self.grid_direction in ("short", "both")

        # Für jede Level: prüfen, ob wir eine Order platzieren sollten
        for lvl in self.levels:
            if lvl.active or lvl.filled:
                continue  # bereits platziert/gefüllt

            # Touch-Logik: BUY, wenn Preis <= Level; SELL, wenn Preis >= Level
            if lvl.side == "BUY" and allow_long and current_price <= lvl.price:
                self._place_entry(lvl)
            elif lvl.side == "SELL" and allow_short and current_price >= lvl.price:
                self._place_entry(lvl)

    def get_state(self) -> Dict:
        """Für Debug/UI: kompakte Zustandsrückgabe."""
        n_active = sum(1 for l in self.levels if l.active)
        n_filled = sum(1 for l in self.levels if l.filled)
        return {
            "symbol": self.symbol,
            "levels_total": len(self.levels),
            "levels_active": n_active,
            "levels_filled": n_filled,
            "grid_direction": self.grid_direction,
            "tp_mode": self.grid_conf.get("tp_mode"),
            "sl_mode": self.grid_conf.get("sl_mode"),
        }

    def log_summary(self) -> None:
        """Einmalige, kurze Zusammenfassung zum Start (und nach Rebalance)."""
        self.logger.info("=" * 60)
        self.logger.info(f"=== GRID SUMMARY ({self.symbol}) ===")
        self.logger.info("=" * 60)
        self.logger.info(f"Grid Direction    : {self.grid_direction}")
        self.logger.info(f"Grid Mode         : {self.grid_conf.get('grid_mode')}")
        self.logger.info(f"Levels            : {len(self.levels)} (lower={self.grid_conf['lower_price']}, upper={self.grid_conf['upper_price']})")
        self.logger.info(f"Base Order Size   : {self.grid_conf.get('base_order_size')}")
        self.logger.info(f"TP Mode           : {self.grid_conf.get('tp_mode')} | SL Mode: {self.grid_conf.get('sl_mode')}")
        self.logger.info(f"Include Fees      : {self.risk_conf.get('include_fees', True)} | Fee Side: {self.risk_conf.get('fee_side', 'taker')}")
        self.logger.info(f"Rebalance Interval: {self.grid_conf.get('rebalance_interval', 300)}s")

        

    # -------------------------------------------------------------------------
    # Order-Placement
    # -------------------------------------------------------------------------
    def _place_entry(self, level: GridLevel) -> None:
        """
        Platziert (oder simuliert) eine Entry-Order auf dem gegebenen Level.
        Setzt TP/SL entsprechend der Konfiguration.
        """
        size = self._effective_order_size()
        if size <= 0:
            self.logger.warning("base_order_size <= 0 (effektiv). Keine Order platziert.")
            return

        tp = self._take_profit_for(entry_price=level.price, level_index=level.index)
        sl = self._stop_loss_for(entry_price=level.price)

        # Dry-Run?
        if self.trading.get("dry_run", True):
            self.logger.info(
                f"[SIM] {level.side} {self.symbol} @ {level.price} "
                f"| size={size} | TP={tp} | SL={sl}"
            )
            level.active = True
            level.tp = tp
            level.sl = sl
            return

        # Live-Order via Client
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
            level.order_id = order_id
            level.active = True
            level.tp = tp
            level.sl = sl
            self.logger.info(f"{level.side} Order platziert: id={order_id} @ {level.price} | TP={tp} | SL={sl}")
        except Exception as e:
            self.logger.error(f"Fehler beim Platzieren der Order: {e}", exc_info=True)

    # -------------------------------------------------------------------------
    # Fills & Lifecycle (kann vom Bot/Handler aufgerufen werden)
    # -------------------------------------------------------------------------
    def on_order_filled(self, order_id: str, fill_price: float) -> None:
        """
        Markiert ein Level als gefüllt, setzt je nach active_rebuy neues Pending.
        Diese Methode solltest du aus deinem Fill-Event-Handler im Bot aufrufen.
        """
        level = next((l for l in self.levels if l.order_id == order_id), None)
        if not level:
            self.logger.debug(f"Fill für unbekannte Order-ID: {order_id}")
            return

        level.filled = True
        level.active = False
        self.logger.info(f"Order gefüllt: {order_id} @ {fill_price} (Level #{level.index})")

        # Nach TP erneut BUY/SELL auf ursprünglichem Level?
        if bool(self.grid_conf.get("active_rebuy", True)):
            # Wir platzieren wieder dieselbe Richtung am selben Level.
            # (Alternativ: Richtung invertieren, falls Hedge-Grid – hier nicht.)
            level.order_id = None
            level.filled = False
            # Re-Entry erst wieder beim nächsten Touch – also aktiv=False lassen.
            self.logger.debug(f"active_rebuy=True → Reentry am selben Level #{level.index} vorbereitet.")

    def cancel_all(self) -> None:
        """
        Optionale Komfortfunktion zum Abbruch aller offenen Orders (falls Client das unterstützt).
        """
        if self.trading.get("dry_run", True):
            for l in self.levels:
                if l.active and not l.filled:
                    l.active = False
                    l.order_id = None
            self.logger.info("[SIM] Alle aktiven Orders verworfen.")
            return

        try:
            self.client.cancel_all(symbol=self.symbol)
            for l in self.levels:
                if l.active and not l.filled:
                    l.active = False
                    l.order_id = None
            self.logger.info("Alle aktiven Orders abgebrochen.")
        except Exception as e:
            self.logger.error(f"Fehler beim Abbrechen aller Orders: {e}", exc_info=True)

    # -------------------------------------------------------------------------
    # Rückwärtskompatibilität für ältere Bots
    # -------------------------------------------------------------------------
    def initialize_grid(self, *args, **kwargs):
        """Legacy-Kompatibilität: Wird nicht mehr benötigt."""
        self.logger.debug("initialize_grid() → ignoriert (bereits initialisiert)")

    def place_orders(self, start_price: float):
        """Legacy-Kompatibilität: nutzt intern update()."""
        self.logger.debug("place_orders() → ersetzt durch update()")
        self.update(start_price)

    def print_grid_status(self):
        """Kompakte Übersicht aller Levels."""
        actives = sum(1 for l in self.levels if l.active)
        filled = sum(1 for l in self.levels if l.filled)
        self.logger.info(
            f"📊 GRID STATUS {self.symbol}: total={len(self.levels)} | active={actives} | filled={filled}"
        )
