# strategies/GRID/manager/order_executor.py
"""
OrderExecutor - Zentrale Order-Platzierungs-Logik

Zuständig für:
- Grid-Order Placement (Initial + Entry-on-Touch)
- Order-Parameter-Validierung
- Dry-Run vs Real-Mode
- Integration mit VirtualOrderManager
"""

import logging
import time
from typing import List, Optional
from dataclasses import dataclass

import sys
from pathlib import Path
GRID_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(GRID_DIR))

from utils.exceptions import OrderPlacementError
from utils.constants import GRID_ORDER_MIN_DISTANCE_STEPS


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


class OrderExecutor:
    """
    Verwaltet Order-Platzierung für Grid-Trading
    """

    def __init__(
        self,
        client,
        symbol: str,
        grid_direction: str,
        risk_manager,
        calculator,
        trading_config,
        virtual_manager=None,
        logger: logging.Logger = None
    ):
        """
        Args:
            client: API Client (Private)
            symbol: Trading Symbol
            grid_direction: "long", "short", "both"
            risk_manager: RiskManager-Instanz
            calculator: GridCalculator-Instanz
            trading_config: TradingConfig (Pydantic)
            virtual_manager: Optional VirtualOrderManager für Dry-Run
            logger: Optional Logger
        """
        self.client = client
        self.symbol = symbol
        self.grid_direction = grid_direction
        self.risk_manager = risk_manager
        self.calculator = calculator
        self.trading = trading_config
        self.virtual_manager = virtual_manager
        # ✅ FIX: Nutze GridManager-Logger statt eigenen
        self.logger = logger or logging.getLogger("GridManager")
        
        # Tracking
        self._initial_orders_placed = False

    # =========================================================================
    # Initial Order Placement
    # =========================================================================

    def place_initial_grid_orders(
        self,
        levels: List[GridLevel],
        current_price: Optional[float] = None
    ) -> int:
        """
        Platziert alle Grid-Orders initial
        
        Args:
            levels: Liste von GridLevel-Objekten
            current_price: Aktueller Marktpreis (optional)
        
        Returns:
            Anzahl platzierter Orders
        """
        if self._initial_orders_placed:
            self.logger.warning("Initial Orders bereits platziert")
            return 0
        
        allow_long = self.grid_direction in ("long", "both")
        allow_short = self.grid_direction in ("short", "both")
        
        placed_count = 0
        skipped_count = 0
        
        for lvl in levels:
            if lvl.active or lvl.filled:
                continue
            
            # === Richtung prüfen ===
            if lvl.side == "BUY" and not allow_long:
                continue
            if lvl.side == "SELL" and not allow_short:
                continue
            
            # === Preis-Validierung (nur wenn Preis bekannt) ===
            if current_price is not None:
                if lvl.side == "BUY" and lvl.price >= current_price:
                    skipped_count += 1
                    continue
                if lvl.side == "SELL" and lvl.price <= current_price:
                    skipped_count += 1
                    continue
            
            try:
                self.place_entry_order(lvl)
                placed_count += 1
                
            except Exception as e:
                self.logger.error(f"❌ Initial Order @ {lvl.price} fehlgeschlagen: {e}")
        
        mode = "Dry-Run" if self.trading.dry_run else "Real"
        price_str = f"@ Preis {current_price:.4f}" if current_price else "(kein Preis)"
        
        self.logger.info(
            f"[ORDER]   {placed_count}/{len(levels)} Grid-Orders platziert, "
            f"{skipped_count} übersprungen {price_str} ({mode})"
        )
        
        self._initial_orders_placed = True
        return placed_count

    # =========================================================================
    # Entry-on-Touch Logic
    # =========================================================================

    def check_new_grid_orders(
        self,
        levels: List[GridLevel],
        current_price: float
    ) -> int:
        """
        Platziert Orders bei Preis-Touch (Entry-on-Touch)
        
        Args:
            levels: Liste von GridLevel-Objekten
            current_price: Aktueller Marktpreis
        
        Returns:
            Anzahl neu platzierter Orders
        """
        allow_long = self.grid_direction in ("long", "both")
        allow_short = self.grid_direction in ("short", "both")
        
        # Mindestabstand berechnen
        price_list = self.calculator.calculate_price_list()
        if len(price_list) < 2:
            return 0
        
        min_distance = abs(price_list[1] - price_list[0]) * GRID_ORDER_MIN_DISTANCE_STEPS
        
        placed_count = 0
        
        for lvl in levels:
            if lvl.active or lvl.filled or lvl.position_open:
                continue

            if lvl.side == "BUY" and allow_long:
                # BUY: Order platzieren wenn Preis genug ÜBER Level
                if current_price >= (lvl.price + min_distance):
                    try:
                        self.place_entry_order(lvl)
                        placed_count += 1
                    except Exception as e:
                        self.logger.error(f"❌ Entry-Order @ {lvl.price} failed: {e}")
            
            elif lvl.side == "SELL" and allow_short:
                # SELL: Order platzieren wenn Preis genug UNTER Level
                if current_price <= (lvl.price - min_distance):
                    try:
                        self.place_entry_order(lvl)
                        placed_count += 1
                    except Exception as e:
                        self.logger.error(f"❌ Entry-Order @ {lvl.price} failed: {e}")
                
        return placed_count

    # =========================================================================
    # Order Placement (Core)
    # =========================================================================

    def place_entry_order(self, level: GridLevel) -> None:
        """
        Platziert eine Grid-Entry-Order
        
        Args:
            level: GridLevel-Objekt
        
        Raises:
            OrderPlacementError: Bei Fehler
        """
        # Ordergröße berechnen
        size = self.risk_manager.calculate_effective_size()
        if size <= 0:
            self.logger.warning("❌ Effektive Ordergröße 0 → Skip")
            return

        # TP/SL holen
        tp, sl = level.tp, level.sl
        
        # Validierung
        if not self.risk_manager.validate_tp_sl(level.price, tp, sl, level.side):
            self.logger.error(f"❌ TP/SL-Validierung fehlgeschlagen @ {level.price}")
            return

        # === Virtual Order (Dry-Run) ===
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
            
            # Log mit Formatierung
            tp_str = f"{tp:.4f}" if tp else "None"
            sl_str = f"{sl:.4f}" if sl else "None"
            
            self.logger.info(
                f"[VIRTUAL] 🟢 Limit Order {level.side} @ {level.price:.4f} | "
                f"size={size} | TP={tp_str} | SL={sl_str} aktiviert"
            )
            return

        # === Echte Order ===
        try:
            result = self.client.place_order(
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

            # Order-ID extrahieren
            if isinstance(result, dict):
                order_id = result.get("orderId")
            else:
                order_id = str(result)
            
            level.order_id = order_id
            level.active = True
            level.tp = tp
            level.sl = sl
            
            tp_str = f"{tp:.4f}" if tp else "None"
            sl_str = f"{sl:.4f}" if sl else "None"
            
            self.logger.info(
                f"[REAL] 🟢 {level.side} @ {level.price:.4f} → ID={order_id} | "
                f"TP={tp_str} | SL={sl_str}"
            )

        except Exception as e:
            raise OrderPlacementError(f"Order @ {level.price} fehlgeschlagen: {e}")

    # =========================================================================
    # Validation & Helpers
    # =========================================================================

    def validate_order_params(
        self,
        level: GridLevel,
        size: float,
        tp: Optional[float],
        sl: Optional[float]
    ) -> bool:
        """
        Prüft ob Order-Parameter valide sind
        
        Args:
            level: GridLevel
            size: Ordergröße
            tp: Take-Profit (optional)
            sl: Stop-Loss (optional)
        
        Returns:
            True wenn valide, False bei Fehler
        """
        # Size-Check
        if size <= 0:
            self.logger.error(f"❌ Ungültige Ordergröße: {size}")
            return False
        
        # TP/SL-Check
        if not self.risk_manager.validate_tp_sl(level.price, tp, sl, level.side):
            return False
        
        # Preis-Check
        if level.price <= 0:
            self.logger.error(f"❌ Ungültiger Preis: {level.price}")
            return False
        
        return True

    def get_placement_summary(self) -> dict:
        """
        Gibt Statistik über platzierte Orders zurück
        
        Returns:
            Dict mit Stats
        """
        return {
            "initial_placed": self._initial_orders_placed,
            "mode": "dry_run" if self.trading.dry_run else "real",
        }
