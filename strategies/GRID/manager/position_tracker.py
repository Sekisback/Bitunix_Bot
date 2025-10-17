# strategies/GRID/manager/position_tracker.py
"""
PositionTracker - Verwaltet Position-Lifecycle

Zuständig für:
- Order-Fill Handling
- Position-Close Handling (TP/SL)
- Order-Cancel Handling
- Net-Position Tracking
- ReOrder-Logik mit Mindestabstand
"""

import logging
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass

import sys
from pathlib import Path
GRID_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(GRID_DIR))


@dataclass
class GridLevel:
    """Grid-Level Definition (sollte eigentlich zentral sein)"""
    index: int
    price: float
    side: str
    order_id: Optional[str] = None
    active: bool = False
    filled: bool = False
    position_open: bool = False
    position_id: Optional[str] = None
    tp: Optional[float] = None
    sl: Optional[float] = None


class PositionTracker:
    """
    Verwaltet Position-Status und Net-Exposure
    """

    def __init__(
        self,
        symbol: str,
        grid_config,
        risk_manager,
        order_executor,
        on_position_change: Optional[Callable] = None,
        logger: logging.Logger = None
    ):
        """
        Args:
            symbol: Trading Symbol
            grid_config: GridConfig (Pydantic)
            risk_manager: RiskManager-Instanz
            order_executor: OrderExecutor-Instanz
            on_position_change: Callback bei Position-Änderungen
            logger: Optional Logger
        """
        self.symbol = symbol
        self.grid_conf = grid_config
        self.risk_manager = risk_manager
        self.order_executor = order_executor
        self.on_position_change = on_position_change
        self.logger = logger or logging.getLogger("PositionTracker")
        
        # Net-Position Tracking
        self.net_position_size = 0.0
        self._levels: List[GridLevel] = []  # ✅ NEU: Levels-Storage
        
        # Stats
        self.total_fills = 0
        self.total_closes = 0
        self.total_cancels = 0

    def set_levels(self, levels: List[GridLevel]) -> None:
        """
        Setzt/Aktualisiert die Grid-Levels
        
        Args:
            levels: Liste von GridLevel-Objekten
        """
        self._levels = levels
        self.logger.debug(f"Levels aktualisiert: {len(levels)} Levels")

    # =========================================================================
    # Fill-Handling
    # =========================================================================

    def handle_order_fill(self, level: GridLevel) -> None:
        """
        Behandelt gefüllte Grid-Orders
        
        Args:
            level: GridLevel das gefüllt wurde
        """
        try:
            # Status updaten
            level.filled = True
            level.active = False
            level.position_open = True
            
            self.total_fills += 1
            
            self.logger.info(
                f"💰 {self.symbol} "
                f"🎯 Grid #{level.index} @ {level.price:.4f} FILLED "
                f"→ Position OPEN (warte auf TP/SL)"
            )
            
            # Net-Position updaten
            self.update_net_position()
            
            # Callback
            if self.on_position_change:
                try:
                    self.on_position_change("fill", level)
                except Exception as cb_err:
                    self.logger.exception(f"Callback error: {cb_err}")
            
        except Exception as e:
            self.logger.error(f"❌ Fill-Handler Fehler: {e}")

    # =========================================================================
    # Position-Close-Handling
    # =========================================================================

    def handle_position_close(
        self,
        position_data: Dict[str, Any],
        levels: List[GridLevel],
        current_price: Optional[float] = None
    ) -> None:
        """
        Behandelt geschlossene Positionen (TP/SL getriggert)
        
        Args:
            position_data: Position-Daten vom Exchange
            levels: Liste aller Grid-Levels
            current_price: Aktueller Marktpreis (für ReOrder-Check)
        """
        try:
            # Entry-Preis aus Position-Daten
            entry_value = float(position_data.get("entryValue", 0))
            
            # Finde passendes Level
            matched_level = None
            for lvl in levels:
                if lvl.position_open and abs(lvl.price - entry_value) < 0.001:
                    matched_level = lvl
                    break
            
            if not matched_level:
                self.logger.warning(
                    f"⚠️ Keine offene Grid-Position für Entry {entry_value:.4f}"
                )
                return
            
            # Status updaten
            matched_level.position_open = False
            matched_level.position_id = None
            matched_level.filled = False
            
            self.total_closes += 1
            
            self.logger.info(
                f"💰 {self.symbol} ✅ Grid #{matched_level.index} @ {matched_level.price:.4f} "
                f"→ Position geschlossen @ {current_price}"
            )
            
            # ✅ ReOrder wenn aktiviert UND Preis weit genug weg
            if self.grid_conf.active_reorder and not matched_level.position_open:
                # Prüfe ob Preis weit genug weg ist
                should_reorder = False
                required_price = None
                
                if current_price is not None:
                    # Mindestabstand = X Grid-Steps (berechnet aus levels)
                    if len(levels) > 1:
                        # Finde nächstes Level für Step-Berechnung
                        sorted_prices = sorted([l.price for l in levels])
                        if len(sorted_prices) >= 2:
                            min_distance = abs(sorted_prices[1] - sorted_prices[0])
                            
                            # ✅ SAFETY: reorder_distance_steps validieren
                            reorder_steps_raw = getattr(self.grid_conf, 'reorder_distance_steps', 2)
                            reorder_steps = max(1, min(10, int(reorder_steps_raw)))
                            
                            # Log bei ungültigen Werten
                            if reorder_steps != reorder_steps_raw:
                                self.logger.warning(
                                    f"⚠️ reorder_distance_steps={reorder_steps_raw} ungültig, "
                                    f"verwende {reorder_steps}"
                                )
                            
                            # BUY: ReOrder wenn Preis ÜBER Entry (folgt TP-Richtung nach oben)
                            if matched_level.side == "BUY":
                                required_price = matched_level.price + (min_distance * reorder_steps)
                                should_reorder = current_price > required_price

                            # SELL: ReOrder wenn Preis UNTER Entry (folgt TP-Richtung nach unten)
                            elif matched_level.side == "SELL":
                                required_price = matched_level.price - (min_distance * reorder_steps)
                                should_reorder = current_price < required_price


                            if required_price is not None:
                                self.logger.info(
                                    f"💰 {self.symbol} ✅ Grid #{matched_level.index} @ {matched_level.price:.4f} " 
                                    f"reopen @ {required_price:.4f}"
                                )
                            
                            # ✅ FIX: Nur loggen wenn required_price existiert
                            if not should_reorder and required_price is not None:
                                self.logger.debug(
                                    f"🔄 ReOrder @ {matched_level.price:.4f} wartet auf "
                                    f"{reorder_steps} Steps Abstand "
                                    f"(aktuell {current_price:.4f}, benötigt {required_price:.4f})"
                                )
                else:
                    # Kein Preis bekannt → Entry-on-Touch übernimmt
                    should_reorder = False
                    self.logger.debug(
                        f"🔄 ReOrder @ {matched_level.price:.4f} wird von Entry-on-Touch gehandelt"
                    )
                
                # Nur platzieren wenn Preis weit genug weg
                if should_reorder:
                    self.logger.debug(f"🔄 ReOrder @ {matched_level.price:.4f}")
                    
                    # Kurze Pause damit Position vollständig geschlossen ist
                    import time
                    time.sleep(0.1)
                    
                    try:
                        self.order_executor.place_entry_order(matched_level)
                    except Exception as reorder_err:
                        self.logger.error(f"❌ ReOrder failed: {reorder_err}")

            # Net-Position updaten
            self.update_net_position()
            
            # Callback
            if self.on_position_change:
                try:
                    self.on_position_change("close", matched_level)
                except Exception as cb_err:
                    self.logger.exception(f"Callback error: {cb_err}")
            
        except Exception as e:
            self.logger.error(f"❌ Position-Close Handler Fehler: {e}")

    # =========================================================================
    # Cancel-Handling
    # =========================================================================

    def handle_order_cancel(self, level: GridLevel) -> None:
        """
        Behandelt gecancelte Grid-Orders
        
        Args:
            level: GridLevel das gecancelt wurde
        """
        try:
            # Status updaten
            level.active = False
            level.order_id = None
            
            self.total_cancels += 1
            
            self.logger.info(f"🔴 Level #{level.index} cancelled @ {level.price}")
            
            # Net-Position updaten
            self.update_net_position()
            
            # Callback
            if self.on_position_change:
                try:
                    self.on_position_change("cancel", level)
                except Exception as cb_err:
                    self.logger.exception(f"Callback error: {cb_err}")
            
        except Exception as e:
            self.logger.error(f"❌ Cancel-Handler Fehler: {e}")

    # =========================================================================
    # Net-Position Tracking
    # =========================================================================

    def update_net_position(self, levels: Optional[List[GridLevel]] = None) -> float:
        """
        Berechnet und speichert Net-Position
        
        Args:
            levels: Optional Liste von Levels (wird gespeichert falls gegeben)
        
        Returns:
            Aktuelle Net-Position
        """
        if levels is not None:
            self._levels = levels
        
        if not self._levels:
            # ✅ FIX: Nur Debug statt Warning
            self.logger.debug("⚠️ Keine Levels für Net-Position-Berechnung")
            return 0.0
        
        # Zähle gefüllte Long/Short
        long_filled = sum(
            1 for lvl in self._levels 
            if lvl.filled and lvl.side == "BUY"
        )
        short_filled = sum(
            1 for lvl in self._levels 
            if lvl.filled and lvl.side == "SELL"
        )
        
        # Zähle aktive (pending) Long/Short
        long_pending = sum(
            1 for lvl in self._levels 
            if lvl.active and not lvl.filled and lvl.side == "BUY"
        )
        short_pending = sum(
            1 for lvl in self._levels 
            if lvl.active and not lvl.filled and lvl.side == "SELL"
        )
        
        # Berechne Net
        base_size = self.risk_manager.calculate_effective_size()
        
        self.net_position_size = (
            (long_filled - short_filled + long_pending - short_pending) * base_size
        )
        
        return self.net_position_size

    def get_net_position(self) -> float:
        """Returns aktuelle Net-Position ohne Neuberechnung"""
        return self.net_position_size

    # =========================================================================
    # Position-Risk-Berechnung (für Hedge)
    # =========================================================================

    def calculate_position_risk(
        self,
        levels: List[GridLevel],
        current_price: float,
        grid_direction: str
    ) -> int:
        """
        Berechnet Risiko = Offene Orders unter/über Preis + Gefüllte Positionen
        
        Args:
            levels: Liste aller Grid-Levels
            current_price: Aktueller Marktpreis
            grid_direction: "long", "short", "both"
        
        Returns:
            Anzahl risikobehafteter Levels
        """
        if grid_direction == "long":
            # LONG: Risiko = Orders UNTER Preis + Filled ohne TP
            active_below = sum(
                1 for lvl in levels 
                if lvl.active and lvl.price < current_price and lvl.side == "BUY"
            )
            
            filled_without_tp = sum(
                1 for lvl in levels 
                if lvl.position_open or lvl.filled
            )
            
            return active_below + filled_without_tp
        
        elif grid_direction == "short":
            # SHORT: Risiko = Orders ÜBER Preis + Filled ohne TP
            active_above = sum(
                1 for lvl in levels 
                if lvl.active and lvl.price > current_price and lvl.side == "SELL"
            )
            
            filled_without_tp = sum(
                1 for lvl in levels 
                if lvl.position_open or lvl.filled
            )
            
            return active_above + filled_without_tp
        
        else:  # both
            return 0

    # =========================================================================
    # Stats & Info
    # =========================================================================

    def get_stats(self) -> dict:
        """
        Gibt Position-Statistiken zurück
        
        Returns:
            Dict mit Stats
        """
        return {
            "net_position_size": self.net_position_size,
            "total_fills": self.total_fills,
            "total_closes": self.total_closes,
            "total_cancels": self.total_cancels,
        }

    def reset_stats(self):
        """Setzt Statistiken zurück"""
        self.total_fills = 0
        self.total_closes = 0
        self.total_cancels = 0
        self.logger.debug("Stats zurückgesetzt")