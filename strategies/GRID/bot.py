#!/usr/bin/env python3
"""
GRID Trading Bot – Pydantic-kompatible Version
"""

import argparse
import asyncio
import logging
import time
import os
import sys
from pathlib import Path

# === Root-Verzeichnis auf Projektroot setzen ===
root_dir = Path(__file__).parent.parent.parent
os.chdir(root_dir)

sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(Path(__file__).parent))

# === Core Imports ===
from core.config import Config
from core.open_api_http_future_private import OpenApiHttpFuturePrivate
from core.open_api_http_future_public import OpenApiHttpFuturePublic
from core.open_api_ws_future_public import OpenApiWsFuturePublic
from core.open_api_ws_future_private import OpenApiWsFuturePrivate

# === Strategie-Komponenten ===
from manager.grid_manager import GridManager
from manager.grid_lifecycle import GridState
from manager.account_sync import AccountSync

from utils.config_loader import load_config
from utils.logging_setup import setup_logging


# ============================================================
# Logging-Tuning – Core-Module leiser, Bot sichtbar
# ============================================================

for name in [
    "core.open_api_ws_future_public",
    "core.open_api_ws_future_private",
    "core.open_api_http_future_public",
    "core.open_api_http_future_private",
    "websockets",
    "asyncio",
]:
    logging.getLogger(name).setLevel(logging.ERROR)

# Bot-Logger
logger = logging.getLogger("GRID-BOT")
logger.setLevel(logging.INFO)


# ============================================================
# GRID BOT
# ============================================================
class GridBot:
    """GRID Bot Wrapper für Bitunix mit Websocket-Integration"""

    def __init__(self, config, client_pri, client_pub):
        """
        Initialisiert GridBot
        
        Args:
            config: GridBotConfig (Pydantic-Objekt)
            client_pri: Private HTTP Client
            client_pub: Public HTTP Client
        """
        self.config = config
        self.client_pri = client_pri
        self.client_pub = client_pub
        
        # === Objekt-Zugriff statt Dict ===
        self.symbol = config.symbol
        self.dry_run = config.trading.dry_run
        self.update_interval = config.system.update_interval
        self._stop = False

        # === API Instanzen ===
        self.exchange = client_pri if not self.dry_run else client_pub
        self.grid = GridManager(self.exchange, config)

        # === Core Config laden ===
        self.api_config = Config()

        # === WebSocket-Clients ===
        self.ws_public = OpenApiWsFuturePublic(self.api_config)
        self.ws_public.on_message_callback = self._on_public_ws

        self.ws_private = OpenApiWsFuturePrivate(self.api_config)
        self.ws_private.on_message_callback = self._on_private_ws

        # === Account-Information ===
        self.account_sync = AccountSync(client_pri, self.symbol)

        # Pending Orders einmalig laden (HTTP)
        self.account_sync.preload_pending_orders()

        # OrderSync mit AccountSync verbinden
        self.grid.attach_account_sync(self.account_sync)


    # ---------------------------------------------------------------------
    # WebSocket-Callbacks
    # ---------------------------------------------------------------------
    async def _on_public_ws(self, channel, data):
        """Callback für Public WS (Preisupdates)"""
        if channel == "ticker":
            price_data = data.get("data", {})
            if not price_data:
                return

            last_price = float(price_data.get("la", price_data.get("c", 0)))
            if last_price != getattr(self, "_last_price", None):
                self._last_price = last_price
                logger.info(f"💰 {self.symbol} @ {last_price:.4f}")
                self.grid.update(last_price)
    
    async def _on_private_ws(self, channel, data):
        """Callback für Private WebSocket"""
        await self.account_sync.on_ws_event(channel, data)

    # ---------------------------------------------------------------------
    # Hauptloop mit Auto-Recovery
    # ---------------------------------------------------------------------
    async def run(self):
        """Startet den GRID-Bot"""
        logger.info("=" * 60)
        logger.info(f"🤖 Starte GRID Bot für {self.symbol}")
        logger.info("=" * 60)

        # === WebSocket vorbereiten ===
        channels = [{"symbol": self.symbol, "ch": "ticker"}]

        # Public WS starten (Preisfeed)
        ws_public_task = asyncio.create_task(self.ws_public.start())
        await asyncio.sleep(2)
        await self.ws_public.subscribe(channels)

        # Private WS starten (Orders, Positionen, Balances)
        ws_private_task = asyncio.create_task(self.ws_private.start())
        await asyncio.sleep(2)
        await self.ws_private.subscribe([
            {"ch": "order"},
            {"ch": "position"},
            {"ch": "balance"},
        ])

        try:
            # === Hauptloop ===
            while not self._stop:
                state = self.grid.lifecycle.state

                # Auto-OrderSync alle 10 Minuten
                if not hasattr(self, "_last_sync_check"):
                    self._last_sync_check = 0

                now = time.time()
                if now - self._last_sync_check >= 600:
                    self._last_sync_check = now
                    asyncio.create_task(self._auto_sync_check())

                # Fehlerzustand → Retry prüfen
                if state == GridState.ERROR:
                    if self.grid.lifecycle.can_retry():
                        logger.warning(f"[{self.symbol}] ⚠️  Fehler erkannt – starte Auto-Recovery ...")
                        try:
                            await self.ws_public.subscribe(channels)
                            await self.ws_private.subscribe([
                                {"ch": "order"},
                                {"ch": "position"},
                                {"ch": "balance"},
                            ])
                            self.grid.lifecycle.set_state(GridState.ACTIVE)
                            logger.info(f"[{self.symbol}] ✅ Auto-Recovery erfolgreich.")
                        except Exception as e:
                            logger.error(f"[{self.symbol}] ❌ Auto-Recovery fehlgeschlagen: {e}")
                            await asyncio.sleep(self.grid.lifecycle.retry_interval)
                    else:
                        await asyncio.sleep(5)
                        continue

                # Pausiert → Warten
                elif state == GridState.PAUSED:
                    logger.warning(f"[{self.symbol}] ⏸️  Grid pausiert – warte auf Wiederaufnahme ...")
                    await asyncio.sleep(5)
                    continue

                # Aktiv → normaler Betrieb
                elif state == GridState.ACTIVE:
                    self.grid.print_grid_status()
                    self.account_sync.sync(ws_enabled=True)
                    await asyncio.sleep(self.update_interval)

                # Geschlossen oder Init
                elif state in (GridState.CLOSED, GridState.INIT):
                    await asyncio.sleep(2)

        except asyncio.CancelledError:
            logger.info("GridBot gestoppt (cancelled)")

        except Exception as e:
            logger.error(f"Fehler im GridBot: {e}")
            self.grid.handle_error(e)

        finally:
            self._stop = True
            self.grid.stop()
            for task in [ws_public_task, ws_private_task]:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            logger.info("✅ Bot sauber beendet.")

    # ---------------------------------------------------------------------
    # Automatischer OrderSync-DryRun
    # ---------------------------------------------------------------------
    async def _auto_sync_check(self):
        """Periodischer Dry-Run-OrderSync"""
        try:
            result = await self.grid.sync_orders()
            logger.info(
                f"[{self.symbol}] 🔍 Auto-OrderSync: "
                f"MATCHED={result['matched']} | MISSING={result['missing']} | "
                f"OBSOLETE={result['obsolete']}"
            )
        except Exception as e:
            logger.error(f"[{self.symbol}] Fehler beim Auto-OrderSync: {e}")


# ============================================================
# MAIN ENTRY
# ============================================================
async def main():
    parser = argparse.ArgumentParser(
        description="Bitunix GRID Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Beispiel: python strategies/GRID/bot.py --config ONDOUSDT",
    )
    parser.add_argument("--config", required=True, help="Coin Config (z. B. ONDOUSDT)")
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Führe OrderSync im Dry-Run-Modus aus"
    )
    args = parser.parse_args()

    # === Config laden ===
    strategy_dir = Path(__file__).parent
    os.chdir(strategy_dir)
    config = load_config(args.config)  # Gibt jetzt GridBotConfig zurück
    os.chdir(root_dir)

    # === Objekt-Zugriff statt Dict ===
    symbol = config.symbol

    # === Logging einrichten ===
    setup_logging(symbol=symbol, strategy="GRID", debug=config.system.debug)

    # === API-Clients ===
    cfg = Config()
    client_pri = OpenApiHttpFuturePrivate(cfg)
    client_pub = OpenApiHttpFuturePublic(cfg)

    # === Bot starten ===
    bot = GridBot(config, client_pri, client_pub)

    # === Optionaler OrderSync-DryRun (Standalone) ===
    if args.sync:
        print("\n🔍 Starte OrderSync-DryRun...")
        result = await bot.grid.sync_orders()
        print(f"✅ OrderSync abgeschlossen: {result}")
        return
    
    # === Normaler Betrieb ===
    await bot.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot gestoppt durch Benutzer")
