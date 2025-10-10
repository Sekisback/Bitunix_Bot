import logging
import time

class AccountSync:
    """Synchronisiert Account-Daten über Bitunix HTTP API."""
    def __init__(self, client_pri, symbol: str):
        self.client = client_pri
        self.symbol = symbol
        self.logger = logging.getLogger(f"AccountSync-{symbol}")
        self.last_sync = 0

    def get_balance(self):
        """Hole verfügbare USDT-Balance."""
        try:
            res = self.client.get_balance()
            balance = float(res.get("USDT", {}).get("available", 0))
            self.logger.info(f"[{self.symbol}] Balance: {balance:.2f} USDT")
            return balance
        except Exception as e:
            self.logger.error(f"Fehler beim Abrufen der Balance: {e}")
            return None

    def get_open_orders(self):
        """Hole offene Orders für das Symbol."""
        try:
            res = self.client.get_open_orders(self.symbol)
            orders = res.get("data", [])
            self.logger.info(f"[{self.symbol}] {len(orders)} offene Orders aktiv.")
            return orders
        except Exception as e:
            self.logger.error(f"Fehler beim Abrufen offener Orders: {e}")
            return []

    def sync(self):
        """Führe periodischen Sync durch (z. B. alle 60 s)."""
        if time.time() - self.last_sync < 60:
            return  # nur alle 60s
        self.last_sync = time.time()

        balance = self.get_balance()
        orders = self.get_open_orders()
        return {"balance": balance, "orders": orders}
