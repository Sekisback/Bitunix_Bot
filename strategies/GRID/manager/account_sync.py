# strategies/GRID/manager/account_sync.py (FINAL FIX)
"""
AccountSync - Verwaltung und Synchronisierung von Account-Daten

NEUE FIXES:
- ✅ Nutzt grid_manager.handle_order_fill() statt direkte Hedge-Calls
- ✅ Nutzt grid_manager.handle_order_cancel() statt direkte Hedge-Calls
- ✅ Vereinfachte Logik
"""
import logging
import time
import sys
from pathlib import Path
from typing import Dict, Any

GRID_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(GRID_DIR))

from utils.constants import BALANCE_SYNC_INTERVAL
from utils.exceptions import InsufficientBalanceError


class AccountSync:
    """Verwaltung und Synchronisierung von Account-Daten"""

    def __init__(self, client_pri, symbol: str):
        self.client = client_pri
        self.symbol = symbol
        self.logger = logging.getLogger("AccountSync")
        self.last_sync = 0
        self.balance = 0.0
        self.balance_coin = "USDT"
        self.orders: Dict[str, Dict[str, Any]] = {}
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.ws_connected = False
        self.grid_manager = None 

    def _update_balance_http(self):
        """Fallback: Balance über HTTP abrufen"""
        try:
            res = self.client.get_account()
            if isinstance(res, list):
                res = next((r for r in res if r.get("marginCoin") == "USDT"), res[0])

            new_balance = float(res.get("available", 0.0))
            
            # 💡 Nur loggen wenn sich Balance geändert hat (Toleranz 0.01 USDT)
            if abs(new_balance - self.balance) > 0.01:
                self.logger.info(f"💰 HTTP Balance: {new_balance:.2f} {self.balance_coin}")
            
            self.balance = new_balance
            self.balance_coin = res.get("marginCoin", "USDT")
            self.last_sync = time.time()
        except Exception as e:
            self.logger.error(f"HTTP Balance error: {e}")

    def _update_balance_ws(self, data: Dict[str, Any]):
        """Balance-Update über WebSocket-Event"""
        try:
            bal = float(data.get("available", 0))
            coin = data.get("coin", self.balance_coin)
            self.balance = bal
            self.balance_coin = coin
            self.ws_connected = True
            self.logger.info(f"💰 WS Balance: {bal:.2f} {coin}")
        except Exception as e:
            self.logger.error(f"WS Balance error: {e}")

    def _update_order_ws(self, data: Dict[str, Any]):
        """Order-Update über WebSocket"""
        try:
            order_id = data.get("orderId") or data.get("id")
            status = data.get("status") or data.get("state") or "unknown"
            self.orders[order_id] = data

            side = data.get("side", "N/A")
            qty = data.get("qty", "N/A")
            price = data.get("price", "N/A")

            if status in ("open", "new", "working"):
                self.logger.info(f"🟢 Order: {side} {qty}@{price}")
            
            elif status in ("filled", "partially_filled"):
                self.logger.info(f"✅ Filled: {side} {qty}@{price}")
                
                # ✅ NEU: Rufe GridManager-Handler auf
                if self.grid_manager:
                    self._handle_order_fill(order_id, data)
                else:
                    self.logger.warning("⚠️ Fill-Event: GridManager nicht verfügbar")
            
            elif status in ("cancelled", "rejected"):
                self.logger.warning(f"⚠️ Cancelled: {side} {qty}@{price}")
                
                # ✅ NEU: Rufe GridManager-Handler auf
                if self.grid_manager:
                    self._handle_order_cancel(order_id, data)
                else:
                    self.logger.warning("⚠️ Cancel-Event: GridManager nicht verfügbar")

        except Exception as e:
            self.logger.error(f"Order update error: {e}")


    def _update_position_ws(self, data: Dict[str, Any]):
        """Positions-Update über WebSocket"""
        try:
            pos_id = data.get("positionId") or data.get("symbol")
            event = data.get("event", "")
            
            # ✅ NEU: Position-Close erkennen
            if event in ("close", "liquidate"):
                self.logger.info(f"🔔 Position {pos_id} geschlossen → Event={event}")
                if self.grid_manager:
                    self._handle_position_close(data)
                return
            
            # Normal Update
            self.positions[pos_id] = data
            side = data.get("side", "N/A")
            qty = data.get("qty", "N/A")
            entry = data.get("entryValue", "N/A")
            self.ws_connected = True
            self.logger.info(f"📈 Position: {side} {qty} @ {entry}")
            
        except Exception as e:
            self.logger.error(f"Position update error: {e}")


    def _handle_order_fill(self, order_id: str, order_data: Dict[str, Any]):
        """
        Behandelt gefüllte Grid-Orders.
        
        ✅ NEU: Nutzt grid_manager.handle_order_fill()
        """
        try:
            if not self.grid_manager:
                self.logger.warning("⚠️ Fill-Handler: GridManager=None")
                return
            
            price = float(order_data.get("price", 0))
            
            # Finde entsprechendes Grid-Level
            matched_level = None
            for lvl in self.grid_manager.levels:
                if abs(lvl.price - price) < 0.0001:  # Toleranz
                    matched_level = lvl
                    break
            
            if not matched_level:
                self.logger.warning(f"⚠️ Kein Grid-Level für gefüllte Order @ {price}")
                return
            
            # ✅ NEU: GridManager übernimmt alles (Fill-Markierung + Hedge + Rebuy)
            self.grid_manager.handle_order_fill(matched_level)
            
        except Exception as e:
            self.logger.error(f"❌ Fill-Handler Fehler: {e}")
            

    def _handle_position_close(self, position_data: Dict[str, Any]):
        """
        Behandelt geschlossene Positionen (TP/SL getriggert).
        Ruft GridManager auf um Level freizugeben.
        """
        try:
            if not self.grid_manager:
                self.logger.warning("⚠️ Position-Close: GridManager=None")
                return
            
            # GridManager übernimmt die Logik
            self.grid_manager.handle_position_close(position_data)
            
        except Exception as e:
            self.logger.error(f"❌ Position-Close Handler Fehler: {e}")


    def _handle_order_cancel(self, order_id: str, order_data: Dict[str, Any]):
        """
        Behandelt gecancelte Grid-Orders.
        
        ✅ NEU: Nutzt grid_manager.handle_order_cancel()
        """
        try:
            if not self.grid_manager:
                self.logger.warning("⚠️ Cancel-Handler: GridManager=None")
                return
            
            price = float(order_data.get("price", 0))
            
            # Finde entsprechendes Grid-Level
            matched_level = None
            for lvl in self.grid_manager.levels:
                if abs(lvl.price - price) < 0.0001:
                    matched_level = lvl
                    break
            
            if not matched_level:
                return
            
            # ✅ NEU: GridManager übernimmt alles (Cancel-Markierung + Hedge)
            self.grid_manager.handle_order_cancel(matched_level)
            
        except Exception as e:
            self.logger.error(f"❌ Cancel-Handler Fehler: {e}")

    async def on_ws_event(self, channel: str, data: Dict[str, Any]):
        """Dispatcher für WS-Events"""
        if channel == "balance":
            self._update_balance_ws(data.get("data", {}))
        elif channel == "order":
            self._update_order_ws(data.get("data", {}))
        elif channel == "position":
            self._update_position_ws(data.get("data", {}))

    def sync(self, ws_enabled: bool = True):
        """Periodischer Abgleich mit Balance-Doppelabfrage-Fix"""
        if ws_enabled and self.ws_connected:
            self.logger.debug(f"Balance: {self.balance:.2f} {self.balance_coin}")
            return self.balance

        now = time.time()
        if not self.ws_connected and (now - self.last_sync >= BALANCE_SYNC_INTERVAL):
            self.logger.debug("WS nicht verbunden → HTTP Balance")
            self._update_balance_http()
        
        return self.balance

    def check_balance(self, required: float) -> bool:
        """Prüft ob genug Balance vorhanden"""
        if self.balance < required:
            raise InsufficientBalanceError(required, self.balance)
        return True

    def preload_pending_orders(self):
        """Lädt offene Orders über HTTP"""
        try:
            if not hasattr(self.client, "get_pending_orders"):
                self.logger.warning("get_pending_orders() nicht verfügbar")
                return

            res = self.client.get_pending_orders(symbol=self.symbol)
            if not res:
                return

            order_list = []
            if isinstance(res, dict):
                order_list = res.get("orderList", [])
            elif isinstance(res, list):
                order_list = res

            if not order_list:
                return

            for o in order_list:
                order_id = o.get("orderId") or o.get("id")
                if not order_id:
                    continue
                self.orders[order_id] = o

            self.logger.info(f"🔄 {len(order_list)} Orders geladen")
        except Exception as e:
            self.logger.error(f"Pending Orders error: {e}")