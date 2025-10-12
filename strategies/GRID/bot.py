#!/usr/bin/env python3
"""GRID Trading Bot mit Error Handling"""

import argparse
import asyncio
import logging
import time
import os
import sys
from pathlib import Path

root_dir = Path(__file__).parent.parent.parent
os.chdir(root_dir)
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(Path(__file__).parent))

from utils.constants import AUTO_SYNC_CHECK_INTERVAL, WS_STARTUP_DELAY, MAIN_LOOP_SLEEP_SECONDS
from utils.exceptions import (
    ConfigValidationError, GridInitializationError, 
    OrderSyncError, WebSocketConnectionError
)

from core.config import Config
from core.open_api_http_future_private import OpenApiHttpFuturePrivate
from core.open_api_http_future_public import OpenApiHttpFuturePublic
from core.open_api_ws_future_public import OpenApiWsFuturePublic
from core.open_api_ws_future_private import OpenApiWsFuturePrivate

from manager.grid_manager import GridManager
from manager.grid_lifecycle import GridState
from manager.account_sync import AccountSync

from utils.config_loader import load_config
from utils.logging_setup import setup_logging

for name in ["core.open_api_ws_future_public", "core.open_api_ws_future_private",
             "core.open_api_http_future_public", "core.open_api_http_future_private",
             "websockets", "asyncio"]:
    logging.getLogger(name).setLevel(logging.ERROR)

logger = logging.getLogger("GRID-BOT")


class GridBot:
    """GRID Bot mit Exception Handling"""

    def __init__(self, config, client_pri, client_pub):
        self.config = config
        self.client_pri = client_pri
        self.client_pub = client_pub
        self.symbol = config.symbol
        self.dry_run = config.trading.dry_run
        self.update_interval = config.system.update_interval
        self._stop = False

        # self.exchange = client_pri if not self.dry_run else client_pub
        # self.grid = GridManager(self.exchange, config)
        self.grid = GridManager(client_pri, config)

        self.api_config = Config()

        self.ws_public = OpenApiWsFuturePublic(self.api_config)
        self.ws_public.on_message_callback = self._on_public_ws

        self.ws_private = OpenApiWsFuturePrivate(self.api_config)
        self.ws_private.on_message_callback = self._on_private_ws

        self.account_sync = AccountSync(client_pri, self.symbol)
        self.account_sync.preload_pending_orders()
        self.grid.attach_account_sync(self.account_sync)

    async def _on_public_ws(self, channel, data):
        """Callback für Public WS"""
        try:
            if channel == "ticker":
                price_data = data.get("data", {})
                if not price_data:
                    return
                last_price = float(price_data.get("la", price_data.get("c", 0)))
                if last_price != getattr(self, "_last_price", None):
                    self._last_price = last_price
                    logger.info(f"💰 {self.symbol} @ {last_price:.4f}")
                    self.grid.update(last_price)
        except Exception as e:
            logger.error(f"Public WS error: {e}")
    
    async def _on_private_ws(self, channel, data):
        """Callback für Private WS"""
        try:
            await self.account_sync.on_ws_event(channel, data)
        except Exception as e:
            logger.error(f"Private WS error: {e}")

    async def run(self):
        """Startet den Bot"""
        logger.info("=" * 60)
        logger.info(f"🤖 Starte GRID Bot für {self.symbol}")
        logger.info("=" * 60)

        channels = [{"symbol": self.symbol, "ch": "ticker"}]

        try:
            ws_public_task = asyncio.create_task(self.ws_public.start())
            await asyncio.sleep(WS_STARTUP_DELAY)
            await self.ws_public.subscribe(channels)

            ws_private_task = asyncio.create_task(self.ws_private.start())
            await asyncio.sleep(WS_STARTUP_DELAY)
            await self.ws_private.subscribe([
                {"ch": "order"},
                {"ch": "position"},
                {"ch": "balance"},
            ])

        except Exception as e:
            raise WebSocketConnectionError(f"WS-Verbindung fehlgeschlagen: {e}")

        try:
            while not self._stop:
                state = self.grid.lifecycle.state

                if not hasattr(self, "_last_sync_check"):
                    self._last_sync_check = 0

                now = time.time()
                if now - self._last_sync_check >= AUTO_SYNC_CHECK_INTERVAL:
                    self._last_sync_check = now
                    asyncio.create_task(self._auto_sync_check())

                if state == GridState.ERROR:
                    if self.grid.lifecycle.can_retry():
                        logger.warning(f"⚠️  Auto-Recovery...")
                        try:
                            await self.ws_public.subscribe(channels)
                            await self.ws_private.subscribe([
                                {"ch": "order"},
                                {"ch": "position"},
                                {"ch": "balance"},
                            ])
                            self.grid.lifecycle.set_state(GridState.ACTIVE)
                            logger.info(f"✅ Recovery erfolgreich")
                        except Exception as e:
                            logger.error(f"❌ Recovery failed: {e}")
                            await asyncio.sleep(self.grid.lifecycle.retry_interval)
                    else:
                        await asyncio.sleep(MAIN_LOOP_SLEEP_SECONDS + 3)
                        continue

                elif state == GridState.PAUSED:
                    await asyncio.sleep(MAIN_LOOP_SLEEP_SECONDS + 3)
                    continue

                elif state == GridState.ACTIVE:
                    self.grid.print_grid_status()
                    self.account_sync.sync(ws_enabled=True)
                    await asyncio.sleep(self.update_interval)

                elif state in (GridState.CLOSED, GridState.INIT):
                    await asyncio.sleep(MAIN_LOOP_SLEEP_SECONDS)

        except asyncio.CancelledError:
            logger.info("Bot cancelled")
        except Exception as e:
            logger.exception(f"Bot error: {e}")
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
            logger.info("✅ Bot beendet")

    async def _auto_sync_check(self):
        """Periodischer OrderSync"""
        try:
            result = await self.grid.sync_orders()
            logger.info(
                f"🔍 Auto-Sync: MATCHED={result['matched']} | "
                f"MISSING={result['missing']} | OBSOLETE={result['obsolete']}"
            )
            
            # === Hedge nach Sync aktualisieren (falls Orders nachträglich platziert wurden) ===
            if result['placed'] > 0:
                self.grid._update_net_position()
                price_list = self.grid.calculator.calculate_price_list()
                lower_bound = price_list[0]
                upper_bound = price_list[-1]
                step = abs(price_list[1] - price_list[0]) if len(price_list) > 1 else 0
                
                self.grid.hedge_manager.update_preemptive_hedge(
                    net_position_size=self.grid.net_position_size,
                    dry_run=self.grid.trading.dry_run,
                    lower_bound=lower_bound,
                    upper_bound=upper_bound,
                    step=step
                )
            
        except OrderSyncError as e:
            logger.error(f"OrderSync error: {e}")


async def main():
    parser = argparse.ArgumentParser(
        description="Bitunix GRID Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Beispiel: python strategies/GRID/bot.py --config ONDOUSDT",
    )
    parser.add_argument("--config", required=True, help="Coin Config")
    parser.add_argument("--sync", action="store_true", help="OrderSync Dry-Run")
    args = parser.parse_args()

    try:
        strategy_dir = Path(__file__).parent
        os.chdir(strategy_dir)
        config = load_config(args.config)
        os.chdir(root_dir)
    except ConfigValidationError as e:
        sys.exit(1)

    symbol = config.symbol

    try:
        setup_logging(symbol=symbol, strategy="GRID", debug=config.system.debug)
    except Exception as e:
        print(f"⚠️ Logging-Setup error: {e}")

    cfg = Config()
    client_pri = OpenApiHttpFuturePrivate(cfg)
    client_pub = OpenApiHttpFuturePublic(cfg)

    try:
        bot = GridBot(config, client_pri, client_pub)
    except GridInitializationError as e:
        logger.error(f"❌ Grid-Init fehlgeschlagen: {e}")
        sys.exit(1)

    # Margin Mode & Leverage Setup
    bot.grid.setup_margin()
    
    if args.sync:
        print("\n🔍 OrderSync-DryRun...")
        try:
            result = await bot.grid.sync_orders()
            print(f"✅ Sync: {result}")
        except OrderSyncError as e:
            print(f"❌ Sync error: {e}")
        return
    
    await bot.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot gestoppt")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
