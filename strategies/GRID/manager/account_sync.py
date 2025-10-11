import logging
import time
import sys
from pathlib import Path
from typing import Dict, Any

GRID_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(GRID_DIR))
from utils.constants import BALANCE_SYNC_INTERVAL


class AccountSync:
    """
    Verwaltung und Synchronisierung von Account-Daten:
    - Echtzeit-Updates über private WebSocket (balance/order/position)
    - Fallback-HTTP-Abfrage für Balance, wenn WS nicht aktiv
    """

    def __init__(self, client_pri, symbol: str):
        self.client = client_pri
        self.symbol = symbol
        self.logger = logging.getLogger(f"AccountSync-{symbol}")

        # Letzter HTTP-Sync (für Fallback)
        self.last_sync = 0

        # Interne Speicher
        self.balance = 0.0
        self.balance_coin = "USDT"
        self.orders: Dict[str, Dict[str, Any]] = {}
        self.positions: Dict[str, Dict[str, Any]] = {}

        # Flags
        self.ws_connected = False

    def _update_balance_http(self):
        """Fallback: Balance über HTTP abrufen"""
        try:
            res = self.client.get_account()
            if isinstance(res, list):
                res = next((r for r in res if r.get("marginCoin") == "USDT"), res[0])

            self.balance = float(res.get("available", 0.0))
            self.balance_coin = res.get("marginCoin", "USDT")
            self.last_sync = time.time()
            self.logger.info(
                f"[{self.symbol}] 💰 HTTP Balance: {self.balance:.2f} {self.balance_coin}"
            )
        except Exception as e:
            self.logger.error(f"Fehler beim HTTP-Balance-Abruf: {e}")

    def _update_balance_ws(self, data: Dict[str, Any]):
        """Balance-Update über WebSocket-Event"""
        try:
            bal = float(data.get("available", 0))
            coin = data.get("coin", self.balance_coin)
            self.balance = bal
            self.balance_coin = coin
            self.ws_connected = True
            self.logger.info(f"[{self.symbol}] 💰 WS Balance Update: {bal:.2f} {coin}")
        except Exception as e:
            self.logger.error(f"Fehler beim WS-Balance-Update: {e}")

    def _update_order_ws(self, data: Dict[str, Any]):
        """Order-Update über WebSocket"""
        try:
            order_id = data.get("orderId") or data.get("id")
            status = (
                data.get("status")
                or data.get("state")
                or data.get("orderStatus")
                or "unknown"
            )
            self.orders[order_id] = data

            side = data.get("side", "N/A")
            qty = data.get("qty", "N/A")
            price = data.get("price", "N/A")

            if status in ("open", "new", "working"):
                self.logger.info(f"[{self.symbol}] 🟢 Order aktiv: {side} {qty}@{price}")
            elif status in ("filled", "partially_filled"):
                self.logger.info(f"[{self.symbol}] ✅ Order gefüllt: {side} {qty}@{price}")
            elif status in ("cancelled", "rejected"):
                self.logger.warning(
                    f"[{self.symbol}] ⚠️ Order storniert/abgelehnt: {side} {qty}@{price}"
                )
            else:
                self.logger.debug(
                    f"[{self.symbol}] ℹ️ Orderstatus: {status} ({side} {qty}@{price})"
                )

        except Exception as e:
            self.logger.error(f"Fehler beim Order-Update: {e}")

    def _update_position_ws(self, data: Dict[str, Any]):
        """Positions-Update über WebSocket"""
        try:
            pos_id = data.get("positionId") or data.get("symbol")
            self.positions[pos_id] = data
            side = data.get("side", "N/A")
            qty = data.get("qty", "N/A")
            entry = data.get("entryValue", "N/A")
            self.ws_connected = True
            self.logger.info(
                f"[{self.symbol}] 📈 Position Update: {side} {qty} @ {entry}"
            )
        except Exception as e:
            self.logger.error(f"Fehler beim Position-Update: {e}")

    async def on_ws_event(self, channel: str, data: Dict[str, Any]):
        """Dispatcher für WS-Events"""
        if channel == "balance":
            self._update_balance_ws(data.get("data", {}))
        elif channel == "order":
            self._update_order_ws(data.get("data", {}))
        elif channel == "position":
            self._update_position_ws(data.get("data", {}))
        else:
            self.logger.debug(f"[{self.symbol}] Unbekannter WS-Kanal: {channel}")

    def sync(self, ws_enabled: bool = True):
        """
        Periodischer Abgleich mit Balance-Doppelabfrage-Fix
        
        Wenn WS aktiv UND verbunden → Balance aus WS nutzen
        Wenn kein WS → Fallback via HTTP (max. alle BALANCE_SYNC_INTERVAL Sekunden)
        """
        # Wenn WS aktiv und verbunden, nutze WS-Balance
        if ws_enabled and self.ws_connected:
            self.logger.debug(
                f"[{self.symbol}] Echtzeit-Balance aktiv: {self.balance:.2f} {self.balance_coin}"
            )
            return self.balance

        # Fallback: HTTP nur wenn WS NICHT verbunden UND genug Zeit vergangen
        now = time.time()
        if not self.ws_connected and (now - self.last_sync >= BALANCE_SYNC_INTERVAL):
            self.logger.debug(f"[{self.symbol}] WS nicht verbunden → HTTP-Balance-Abfrage")
            self._update_balance_http()
        
        return self.balance

    def preload_pending_orders(self):
        """
        Lädt alle offenen (Pending) Orders über die HTTP-API
        Wird beim Start einmalig aufgerufen, um den WS-Cache zu initialisieren
        """
        try:
            if not hasattr(self.client, "get_pending_orders"):
                self.logger.warning(f"[{self.symbol}] ⚠️ Client unterstützt get_pending_orders() nicht.")
                return

            res = self.client.get_pending_orders(symbol=self.symbol)

            if not res:
                self.logger.info(f"[{self.symbol}] Keine Pending Orders gefunden (leere Antwort).")
                return

            order_list = []
            if isinstance(res, dict):
                order_list = res.get("orderList", [])
            elif isinstance(res, list):
                order_list = res

            if not order_list:
                self.logger.info(f"[{self.symbol}] Keine Pending Orders vorhanden.")
                return

            for o in order_list:
                order_id = o.get("orderId") or o.get("id")
                if not order_id:
                    continue
                self.orders[order_id] = o

            self.logger.info(f"[{self.symbol}] 🔄 {len(order_list)} Pending Orders in Cache geladen.")
        except Exception as e:
            self.logger.error(f"[{self.symbol}] Fehler beim Laden der Pending Orders: {e}")
