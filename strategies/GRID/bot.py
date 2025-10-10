#!/usr/bin/env python3
"""
GRID Trading Bot – aktualisierte Version
Kompatibel mit GridManager v2 und neuer YAML-Struktur
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
import time

# === Root-Verzeichnis auf Projektroot setzen ===
root_dir = Path(__file__).parent.parent.parent
os.chdir(root_dir)

sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(Path(__file__).parent))

# === Core Imports ===
from core.config import Config
from core.open_api_http_future_private import OpenApiHttpFuturePrivate
from core.open_api_http_future_public import OpenApiHttpFuturePublic

# === Strategie-Komponenten ===
from manager.grid_manager import GridManager
from utils.config_loader import load_config
from utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)


class GridBot:
    """GRID Bot Wrapper für Bitunix."""

    def __init__(self, config: dict, client_pri, client_pub):
        self.config = config
        self.client_pri = client_pri
        self.client_pub = client_pub
        self.symbol = config["symbol"]
        self.dry_run = config["trading"].get("dry_run", True)
        self.update_interval = config["system"].get("update_interval", 5)
        self._stop = False

        # API / Mock
        if self.dry_run:
            class MockExchange:
                """Minimaler Fake-Client zum Testen ohne API-Zugriff."""
                def place_order(self, **kwargs):
                    print(f"[MOCK] Order: {kwargs}")
                    return f"MOCK-{int(time.time())}"

                def cancel_all(self, symbol: str):
                    print(f"[MOCK] Cancel all orders for {symbol}")
                    return True

            self.exchange = MockExchange()
        else:
            self.exchange = client_pri

        # Grid initialisieren
        self.grid = GridManager(self.exchange, config)

    async def run(self):
        """Hauptloop des Grid-Bots."""
        logger.info("=" * 60)
        logger.info(f"🤖 Starte GRID Bot für {self.symbol}")
        logger.info("=" * 60)
        start_price = self.config.get("start_price", self.grid.grid_conf["lower_price"])

        while not self._stop:
            try:
                # Simulierter Marktpreis (Backtest-Modus)
                if self.dry_run:
                    start_price *= 1.001

                # Grid aktualisieren
                self.grid.update(start_price)

                # Kurze Übersicht
                self.grid.print_grid_status()

                await asyncio.sleep(self.update_interval)

            except KeyboardInterrupt:
                self._stop = True
                break
            except Exception as e:
                logger.error(f"Fehler im Grid-Loop: {e}", exc_info=True)
                await asyncio.sleep(3)

        logger.info("🛑 Grid-Bot beendet.")


async def main():
    parser = argparse.ArgumentParser(
        description="Bitunix GRID Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Beispiel: python strategies/GRID/bot.py --config ONDOUSDT"
    )
    parser.add_argument("--config", required=True, help="Coin Config (z. B. ONDOUSDT)")
    args = parser.parse_args()

    # === Config laden ===
    strategy_dir = Path(__file__).parent
    os.chdir(strategy_dir)
    config = load_config(args.config)
    os.chdir(root_dir)

    symbol = config["symbol"]

    # === Logging einrichten ===
    setup_logging(symbol=symbol, strategy="GRID", debug=config["system"]["debug"])

    # === API-Clients ===
    cfg = Config()
    client_pri = OpenApiHttpFuturePrivate(cfg)
    client_pub = OpenApiHttpFuturePublic(cfg)

    # === Bot starten ===
    bot = GridBot(config, client_pri, client_pub)
    await bot.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot gestoppt durch Benutzer")
