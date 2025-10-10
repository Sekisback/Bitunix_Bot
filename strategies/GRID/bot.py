#!/usr/bin/env python3
"""
GRID Trading Bot – aktualisierte Version
Kompatibel mit GridManager v2 und neuer YAML-Struktur
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

# === Account- Informationen ===
from manager.account_sync import AccountSync

from utils.config_loader import load_config
from utils.logging_setup import setup_logging


# ============================================================
# Logging-Tuning – Core-Module leiser, Bot sichtbar
# ============================================================

# Core-Module und Async-Libraries leise schalten
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

    def __init__(self, config: dict, client_pri, client_pub):
        self.config = config
        self.client_pri = client_pri
        self.client_pub = client_pub
        self.symbol = config["symbol"]
        self.dry_run = config["trading"].get("dry_run", True)
        self.update_interval = config["system"].get("update_interval", 5)
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

        # 🧩 Pending Orders einmalig laden (HTTP)
        self.account_sync.preload_pending_orders()

        # 🔗 OrderSync mit AccountSync verbinden
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
        """Callback für Private WebSocket (Order-, Position-, Balance-Events)."""
        await self.account_sync.on_ws_event(channel, data)

    # ---------------------------------------------------------------------
    # Hauptloop mit Auto-Recovery
    # ---------------------------------------------------------------------
    async def run(self):
        """Startet den GRID-Bot inklusive WebSocket-Clients, Lifecycle und Auto-Recovery."""
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
            # === Hauptloop: Statusanzeige, Fehlerüberwachung und Recovery ===
            while not self._stop:
                state = self.grid.lifecycle.state

                # 🧩 Automatischer OrderSync-Check alle 10 Minuten
                if not hasattr(self, "_last_sync_check"):
                    self._last_sync_check = 0

                now = time.time()
                if now - self._last_sync_check >= 60:  # 600 Sekunden = 10 Minuten
                    self._last_sync_check = now
                    asyncio.create_task(self._auto_sync_check())

                # 🔴 Fehlerzustand → Retry prüfen
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

                # 🟡 Pausiert → Warten
                elif state == GridState.PAUSED:
                    logger.warning(f"[{self.symbol}] ⏸️  Grid pausiert – warte auf Wiederaufnahme ...")
                    await asyncio.sleep(5)
                    continue

                # 🟢 Aktiv → normaler Betrieb
                elif state == GridState.ACTIVE:
                    self.grid.print_grid_status()
                    self.account_sync.sync(ws_enabled=True)
                    await asyncio.sleep(self.update_interval)

                # 🔚 Geschlossen oder Init → kurz warten
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
    # Automatischer OrderSync-DryRun (Hintergrund)
    # ---------------------------------------------------------------------
    async def _auto_sync_check(self):
        """
        Führt periodisch einen Dry-Run-OrderSync durch,
        um Abweichungen zwischen Grid-Levels und offenen Orders zu erkennen.
        """
        try:
            result = await self.grid.sync_orders()
            logger.info(
                f"[{self.symbol}] 🔍 Auto-OrderSync: "
                f"MATCHED={result['matched']} | MISSING={result['missing']} | OBSOLETE={result['obsolete']}"
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
        help="Führe OrderSync im Dry-Run-Modus aus (prüft Orders, keine Trades)"
    )
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
