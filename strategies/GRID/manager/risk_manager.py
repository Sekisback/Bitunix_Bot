# strategies/GRID/manager/risk_manager.py
"""
RiskManager - Fee/TP/SL-Logik isoliert
Zuständig für:
- Effektive Ordergrößen-Berechnung (mit Fees)
- Take-Profit-Berechnung (next_grid/percent)
- Stop-Loss-Berechnung (fixed/percent/none)
"""

import logging
from typing import Optional, List
from models.config_models import TPMode, SLMode, GridDirection


class RiskManager:
    """
    Verwaltet Risk-Parameter für Grid-Trading
    """

    def __init__(self, grid_config, risk_config, grid_calculator, logger: logging.Logger = None):
        """
        Args:
            grid_config: GridConfig-Objekt (Pydantic)
            risk_config: RiskConfig-Objekt (Pydantic)
            grid_calculator: GridCalculator-Instanz (für Tick-Rundung)
            logger: Optional Logger
        """
        self.grid_conf = grid_config
        self.risk_conf = risk_config
        self.calculator = grid_calculator
        self.logger = logger or logging.getLogger("RiskManager")

    # =========================================================================
    # Fee-Berechnung
    # =========================================================================

    def calculate_effective_size(self, base_size: Optional[float] = None) -> float:
        """
        Berechnet effektive Ordergröße unter Berücksichtigung von Gebühren
        
        Args:
            base_size: Basis-Ordergröße (default: aus Config)
        
        Returns:
            Effektive Größe nach Abzug doppelter Gebühr (Entry + Exit)
        """
        if base_size is None:
            base_size = float(self.grid_conf.base_order_size)
        
        if base_size <= 0.0:
            self.logger.error("base_order_size <= 0")
            return 0.0
        
        # === Gebühren berücksichtigen? ===
        if not self.risk_conf.include_fees:
            return base_size
        
        # Fee-Prozentsatz holen
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
            f"[FeeCalc] base={base_size:.4f} | "
            f"fee_side={fee_side} | "
            f"fee={fee_pct:.6f} × 2 = {effective_fee:.6f} | "
            f"effective={size:.8f}"
        )
        
        return max(0.0, round(size, 8))

    def get_fee_info(self) -> dict:
        """
        Gibt Fee-Informationen zurück
        
        Returns:
            Dict mit Fee-Details
        """
        return {
            "include_fees": self.risk_conf.include_fees,
            "fee_side": self.risk_conf.fee_side,
            "maker_fee_pct": self.risk_conf.maker_fee_pct,
            "taker_fee_pct": self.risk_conf.taker_fee_pct,
        }

    # =========================================================================
    # Take-Profit Berechnung
    # =========================================================================

    def calculate_take_profit(
        self,
        entry_price: float,
        level_index: int,
        side: str,
        price_list: Optional[List[float]] = None
    ) -> Optional[float]:
        """
        Berechnet Take-Profit-Preis abhängig von Richtung und Modus
        
        Args:
            entry_price: Entry-Preis
            level_index: Index im Preisgrid
            side: "BUY" oder "SELL"
            price_list: Preisgrid (optional, wird geholt falls None)
        
        Returns:
            TP-Preis (gerundet) oder None wenn deaktiviert
        """
        mode = self.grid_conf.tp_mode
        
        # === Preisgrid holen falls nicht übergeben ===
        if price_list is None:
            price_list = self.calculator.calculate_price_list()
        
        # === MODUS: next_grid ===
        if mode == TPMode.NEXT_GRID:
            tp = self._tp_next_grid(entry_price, level_index, side, price_list)
        
        # === MODUS: percent ===
        elif mode == TPMode.PERCENT:
            tp = self._tp_percent(entry_price, side)
        
        else:
            self.logger.warning(f"Unbekannter TP-Modus: {mode}")
            return None
        
        if tp is None:
            return None
        
        # Tick-Rundung
        rounded = self.calculator.round_to_tick(tp)
        
        self.logger.debug(
            f"[TP] entry={entry_price:.6f} | side={side} | "
            f"mode={mode.value} | tp={rounded:.6f}"
        )
        
        return rounded

    def _tp_next_grid(
        self,
        entry_price: float,
        level_index: int,
        side: str,
        price_list: List[float]
    ) -> Optional[float]:
        """
        TP = Nächstes Grid-Level
        
        BUY  → TP oberhalb (level_index + 1)
        SELL → TP unterhalb (level_index - 1)
        """
        if side.upper() == "BUY":
            # Nächstes Level oder extrapolieren
            if level_index < len(price_list) - 1:
                return price_list[level_index + 1]
            else:
                # Über oberster Grenze → extrapolieren
                step = price_list[-1] - price_list[-2]
                return entry_price + step
        
        else:  # SELL
            # Vorheriges Level oder extrapolieren
            if level_index > 0:
                return price_list[level_index - 1]
            else:
                # Unter unterster Grenze → extrapolieren
                step = price_list[1] - price_list[0]
                return entry_price - step

    def _tp_percent(self, entry_price: float, side: str) -> Optional[float]:
        """
        TP = Entry-Preis ± Prozent
        
        BUY  → TP = entry × (1 + pct)
        SELL → TP = entry × (1 - pct)
        """
        pct = float(self.grid_conf.take_profit_pct)
        
        if side.upper() == "BUY":
            return entry_price * (1.0 + pct)
        else:
            return entry_price * (1.0 - pct)

    # =========================================================================
    # Stop-Loss Berechnung
    # =========================================================================

    def calculate_stop_loss(
        self,
        entry_price: float,
        side: str
    ) -> Optional[float]:
        """
        Berechnet Stop-Loss-Preis abhängig von Richtung und Modus
        
        Args:
            entry_price: Entry-Preis
            side: "BUY" oder "SELL"
        
        Returns:
            SL-Preis (gerundet) oder None wenn deaktiviert
        """
        mode = self.grid_conf.sl_mode
        
        # === MODUS: none ===
        if mode == SLMode.NONE:
            return None
        
        # === MODUS: fixed ===
        elif mode == SLMode.FIXED:
            fixed = self.grid_conf.stop_loss_price
            if fixed is None:
                self.logger.warning("sl_mode='fixed', aber stop_loss_price fehlt")
                return None
            sl = float(fixed)
        
        # === MODUS: percent ===
        elif mode == SLMode.PERCENT:
            sl = self._sl_percent(entry_price, side)
        
        else:
            self.logger.warning(f"Unbekannter SL-Modus: {mode}")
            return None
        
        if sl is None:
            return None
        
        # Tick-Rundung
        rounded = self.calculator.round_to_tick(sl)
        
        self.logger.debug(
            f"[SL] entry={entry_price:.6f} | side={side} | "
            f"mode={mode.value} | sl={rounded:.6f}"
        )
        
        return rounded

    def _sl_percent(self, entry_price: float, side: str) -> Optional[float]:
        """
        SL = Entry-Preis ± Prozent
        
        BUY  → SL unterhalb = entry × (1 - pct)
        SELL → SL oberhalb  = entry × (1 + pct)
        """
        pct = float(self.grid_conf.stop_loss_pct)
        
        if side.upper() == "BUY":
            return entry_price * (1.0 - pct)
        else:
            return entry_price * (1.0 + pct)

    # =========================================================================
    # Validation & Info
    # =========================================================================

    def validate_tp_sl(
        self,
        entry_price: float,
        tp_price: Optional[float],
        sl_price: Optional[float],
        side: str
    ) -> bool:
        """
        Prüft ob TP/SL sinnvoll sind
        
        BUY:  TP > entry > SL  (Gewinn oben, Stop unten)
        SELL: SL > entry > TP  (Stop oben, Gewinn unten)
        
        Args:
            entry_price: Entry-Preis
            tp_price: Take-Profit (optional)
            sl_price: Stop-Loss (optional)
            side: "BUY" oder "SELL"
        
        Returns:
            True wenn valide, False bei Fehler
        """
        side_upper = side.upper()
        
        if side_upper == "BUY":
            # BUY: Kaufen → Gewinn bei steigendem Preis
            # TP muss OBERHALB Entry sein
            if tp_price is not None and tp_price <= entry_price:
                self.logger.error(
                    f"❌ BUY invalid: TP ({tp_price:.6f}) muss > entry ({entry_price:.6f})"
                )
                return False
            
            # SL muss UNTERHALB Entry sein
            if sl_price is not None and sl_price >= entry_price:
                self.logger.error(
                    f"❌ BUY invalid: SL ({sl_price:.6f}) muss < entry ({entry_price:.6f})"
                )
                return False
        
        elif side_upper == "SELL":
            # SELL: Verkaufen → Gewinn bei fallendem Preis
            # TP muss UNTERHALB Entry sein
            if tp_price is not None and tp_price >= entry_price:
                self.logger.error(
                    f"❌ SELL invalid: TP ({tp_price:.6f}) muss < entry ({entry_price:.6f})"
                )
                return False
            
            # SL muss OBERHALB Entry sein
            if sl_price is not None and sl_price <= entry_price:
                self.logger.error(
                    f"❌ SELL invalid: SL ({sl_price:.6f}) muss > entry ({entry_price:.6f})"
                )
                return False
        
        else:
            self.logger.error(f"❌ Unbekannte Side: {side}")
            return False
        
        return True

    def get_risk_summary(self) -> dict:
        """
        Gibt Risk-Parameter als Dict zurück
        
        Returns:
            Dict mit allen Risk-Einstellungen
        """
        return {
            "tp_mode": self.grid_conf.tp_mode.value,
            "tp_pct": self.grid_conf.take_profit_pct if self.grid_conf.tp_mode == TPMode.PERCENT else None,
            "sl_mode": self.grid_conf.sl_mode.value,
            "sl_pct": self.grid_conf.stop_loss_pct if self.grid_conf.sl_mode == SLMode.PERCENT else None,
            "sl_price": self.grid_conf.stop_loss_price if self.grid_conf.sl_mode == SLMode.FIXED else None,
            "base_order_size": self.grid_conf.base_order_size,
            "include_fees": self.risk_conf.include_fees,
            "fee_side": self.risk_conf.fee_side,
        }
