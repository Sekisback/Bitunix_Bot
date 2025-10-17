# strategies/GRID/manager/virtual_order_manager.py
"""
VirtualOrderManager - Simuliert Orders im Dry-Run Mode

Features:
- Fill-Detection bei Preis-Touch
- TP/SL-Trigger
- PnL-Tracking
- Performance-Statistiken
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


@dataclass
class VirtualOrder:
    """Virtuelle Order"""
    order_id: str
    symbol: str
    side: str  # BUY, SELL
    order_type: str  # LIMIT, MARKET
    qty: float
    price: float
    status: str = "OPEN"  # OPEN, FILLED, CANCELLED
    filled_price: Optional[float] = None
    filled_time: Optional[float] = None
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    client_id: Optional[str] = None
    
    def to_dict(self):
        """Konvertiert zu Dict (wie echte API-Response)"""
        return {
            "orderId": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "type": self.order_type,
            "qty": self.qty,
            "price": self.price,
            "status": self.status,
            "clientId": self.client_id,
        }


@dataclass
class VirtualPosition:
    """Virtuelle Position"""
    position_id: str
    symbol: str
    side: str  # LONG, SHORT
    entry_price: float  # Grid-Preis (für Level-Matching)
    qty: float
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None
    opened_at: float = field(default_factory=time.time)
    closed_at: Optional[float] = None
    close_price: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    fill_price: Optional[float] = None  # ← NEU: Tatsächlicher Fill-Preis für PnL
    
    def calculate_pnl(self, close_price: float):
        """Berechnet PnL basierend auf Fill-Preis"""
        # ✅ FIX: PnL mit Fill-Preis berechnen, nicht Grid-Preis
        actual_entry = self.fill_price if self.fill_price else self.entry_price
        
        if self.side == "LONG":
            self.pnl = (close_price - actual_entry) * self.qty
            self.pnl_pct = ((close_price - actual_entry) / actual_entry) * 100
        else:  # SHORT
            self.pnl = (actual_entry - close_price) * self.qty
            self.pnl_pct = ((actual_entry - close_price) / actual_entry) * 100
        
        self.close_price = close_price
        self.closed_at = time.time()

class VirtualOrderManager:
    """Verwaltet virtuelle Orders und Positionen im Dry-Run"""
    
    def __init__(self, symbol: str, logger: logging.Logger = None):
        self.symbol = symbol
        self.logger = logger or logging.getLogger("VirtualOrderManager")
        
        # Order & Position Storage
        self.orders: Dict[str, VirtualOrder] = {}
        self.positions: Dict[str, VirtualPosition] = {}
        
        # Performance Stats
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0.0
        self.total_pnl_pct = 0.0
        self.best_trade = 0.0
        self.worst_trade = 0.0
        
        self.logger.info(f"[VIRTUAL]  VirtualOrderManager für {symbol} initialisiert")
    
    def place_order(self, side: str, order_type: str, qty: float, price: float, tp_price: Optional[float] = None, sl_price: Optional[float] = None, client_id: Optional[str] = None) -> str:
        """
        Platziert virtuelle Order
        
        Returns:
            order_id: Unique Order ID
        """
        order_id = str(uuid.uuid4())[:8]
        
        order = VirtualOrder(
            order_id=order_id,
            symbol=self.symbol,
            side=side,
            order_type=order_type,
            qty=qty,
            price=price,
            tp_price=tp_price,
            sl_price=sl_price,
            client_id=client_id
        )
        
        self.orders[order_id] = order
        
        # ✅ FIX: Formatierung außerhalb
        tp_str = f"{tp_price:.4f}" if tp_price else "None"
        sl_str = f"{sl_price:.4f}" if sl_price else "None"
        
        self.logger.debug(
            f"[VIRTUAL] 🟢 Order platziert: {side} {qty}@{price:.4f} "
            f"| TP={tp_str} | SL={sl_str}"
        )
    
        return order_id
    
    def check_fills(self, current_price: float) -> List[VirtualOrder]:
        """
        Prüft ob Orders bei aktuellem Preis gefüllt werden
        
        Args:
            current_price: Aktueller Marktpreis
        
        Returns:
            Liste gefüllter Orders
        """
        filled_orders = []
        
        for order in list(self.orders.values()):
            if order.status != "OPEN":
                continue
            
            # MARKET Orders werden sofort gefüllt
            if order.order_type == "MARKET":
                self._fill_order(order, current_price)
                filled_orders.append(order)
                continue
            
            # LIMIT Orders: Check ob Preis erreicht
            should_fill = False
            
            if order.side == "BUY":
                # BUY Limit: Fill wenn Preis <= Order-Preis
                if current_price <= order.price:
                    should_fill = True
            
            elif order.side == "SELL":
                # SELL Limit: Fill wenn Preis >= Order-Preis
                if current_price >= order.price:
                    should_fill = True
            
            if should_fill:
                self._fill_order(order, current_price)
                filled_orders.append(order)
        
        return filled_orders
    
    def _fill_order(self, order: VirtualOrder, fill_price: float, tp_price: Optional[float] = None, sl_price: Optional[float] = None,):
        """Füllt Order"""
        order.status = "FILLED"
        order.filled_price = fill_price
        order.filled_time = time.time()

        # ✅ FIX: Formatierung außerhalb
        tp_str = f"{tp_price:.4f}" if tp_price else "None"
        sl_str = f"{sl_price:.4f}" if sl_price else "None"
        
        self.logger.info(
            f"💰 {self.symbol} "
            f"✅ FILL {order.side} {order.qty}@{fill_price:.4f} "
            f"(Order @ {order.price:.4f} TP @ {tp_str}  SL @ {sl_str})"
        )
        
        # Erstelle Position
        self._create_position(order, fill_price)
    
    def _create_position(self, order: VirtualOrder, fill_price: float):
        """Erstellt Position aus gefüllter Order"""
        position_id = f"pos_{order.order_id}"
        
        # ✅ FIX: Grid-Preis speichern für korrektes Level-Matching
        position = VirtualPosition(
            position_id=position_id,
            symbol=self.symbol,
            side="LONG" if order.side == "BUY" else "SHORT",
            entry_price=order.price,  # ← Grid-Preis (Original Order-Preis)
            qty=order.qty,
            tp_price=order.tp_price,
            sl_price=order.sl_price
        )
        
        # Fill-Preis für PnL-Berechnung merken
        position.fill_price = fill_price
        
        self.positions[position_id] = position
        
        self.logger.debug(
            f"[VIRTUAL] 📍 Position eröffnet: {position.side} {position.qty} @ Grid={order.price:.4f} Fill={fill_price:.4f}"
        )
    
    def check_tp_sl(self, current_price: float) -> List[VirtualPosition]:
        """
        Prüft ob TP/SL getriggert werden
        
        Args:
            current_price: Aktueller Marktpreis
        
        Returns:
            Liste geschlossener Positionen
        """
        closed_positions = []
        
        for position in list(self.positions.values()):
            if position.closed_at:
                continue
            
            should_close = False
            close_reason = ""
            close_price = current_price
            
            # TP Check
            if position.tp_price:
                if position.side == "LONG" and current_price >= position.tp_price:
                    should_close = True
                    close_reason = "TP"
                    close_price = position.tp_price
                
                elif position.side == "SHORT" and current_price <= position.tp_price:
                    should_close = True
                    close_reason = "TP"
                    close_price = position.tp_price
            
            # SL Check (nur wenn nicht schon TP)
            if not should_close and position.sl_price:
                if position.side == "LONG" and current_price <= position.sl_price:
                    should_close = True
                    close_reason = "SL"
                    close_price = position.sl_price
                
                elif position.side == "SHORT" and current_price >= position.sl_price:
                    should_close = True
                    close_reason = "SL"
                    close_price = position.sl_price
            
            if should_close:
                self._close_position(position, close_price, close_reason)
                closed_positions.append(position)
        
        return closed_positions
    
    def _close_position(self, position: VirtualPosition, close_price: float, reason: str):
        """Schließt Position"""
        position.calculate_pnl(close_price)
        
        # Stats updaten
        self.total_trades += 1
        self.total_pnl += position.pnl
        self.total_pnl_pct += position.pnl_pct
        
        if position.pnl > 0:
            self.winning_trades += 1
            if position.pnl > self.best_trade:
                self.best_trade = position.pnl
        else:
            self.losing_trades += 1
            if position.pnl < self.worst_trade:
                self.worst_trade = position.pnl
              
        # Log mit Emoji
        emoji = "🎯" if reason == "TP" else "🛑"
        profit_emoji = "💰" if position.pnl > 0 else "📉"
        
        # self.logger.info(
        #     f"[VIRTUAL] {emoji} {reason} @ {close_price:.4f} | "
        #     f"{position.side} {position.qty} Entry={position.entry_price:.4f} | "
        #     f"{profit_emoji} PnL: {position.pnl:+.2f} USDT ({position.pnl_pct:+.2f}%)"
        # )
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancelt Order"""
        if order_id not in self.orders:
            return False
        
        order = self.orders[order_id]
        if order.status != "OPEN":
            return False
        
        order.status = "CANCELLED"
        self.logger.debug(f"[VIRTUAL] ❌ Order cancelled: {order_id}")
        return True
    
    def get_open_orders(self) -> List[VirtualOrder]:
        """Gibt alle offenen Orders zurück"""
        return [o for o in self.orders.values() if o.status == "OPEN"]
    
    def get_open_positions(self) -> List[VirtualPosition]:
        """Gibt alle offenen Positionen zurück"""
        return [p for p in self.positions.values() if p.closed_at is None]
    
    def get_stats(self) -> dict:
        """Gibt Performance-Statistiken zurück"""
        win_rate = (
            (self.winning_trades / self.total_trades * 100)
            if self.total_trades > 0
            else 0.0
        )
        
        avg_pnl = (
            self.total_pnl / self.total_trades
            if self.total_trades > 0
            else 0.0
        )
        
        avg_pnl_pct = (
            self.total_pnl_pct / self.total_trades
            if self.total_trades > 0
            else 0.0
        )
        
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": win_rate,
            "total_pnl": self.total_pnl,
            "avg_pnl": avg_pnl,
            "avg_pnl_pct": avg_pnl_pct,
            "best_trade": self.best_trade,
            "worst_trade": self.worst_trade,
            "open_orders": len(self.get_open_orders()),
            "open_positions": len(self.get_open_positions()),
        }
    
    def print_stats(self):
        """Gibt Stats formatiert aus"""
        stats = self.get_stats()
        
        self.logger.info("=" * 60)
        self.logger.info("📊 VIRTUAL TRADING PERFORMANCE")
        self.logger.info("=" * 60)
        self.logger.info(f"Total Trades   : {stats['total_trades']}")
        self.logger.info(
            f"Win/Loss       : {stats['winning_trades']}W / {stats['losing_trades']}L "
            f"({stats['win_rate']:.1f}%)"
        )
        self.logger.info(f"Total PnL      : {stats['total_pnl']:+.2f} USDT")
        self.logger.info(f"Avg PnL/Trade  : {stats['avg_pnl']:+.2f} USDT ({stats['avg_pnl_pct']:+.2f}%)")
        self.logger.info(f"Best Trade     : {stats['best_trade']:+.2f} USDT")
        self.logger.info(f"Worst Trade    : {stats['worst_trade']:+.2f} USDT")
        self.logger.info(f"Open Orders    : {stats['open_orders']}")
        self.logger.info(f"Open Positions : {stats['open_positions']}")
        self.logger.info("=" * 60)