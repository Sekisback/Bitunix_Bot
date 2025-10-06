# strategies/test_account_functions.py

import asyncio
import logging
import time
import datetime
import sys
import os

# WICHTIG: Pfad zum Hauptverzeichnis hinzufügen (VOR den anderen Imports!)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.config import Config
from core.open_api_http_future_private import OpenApiHttpFuturePrivate
from core.open_api_http_future_public import OpenApiHttpFuturePublic

# Logging-Konfiguration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


async def main():
    # === Test-Parameter ===
    SYMBOL = "BTCUSDT"
    SYMBOLS = ("BTCUSDT", "ETHUSDT")
    MARGIN_COIN = "USDT"
    
    logging.info("🚀 Starte Account-Funktionen Test")

    # === 🔑 API-Client laden ===
    cfg = Config()
    client = OpenApiHttpFuturePrivate(cfg)
    market = OpenApiHttpFuturePublic(cfg)

    try:
        # === Account-Info abrufen ===
        logging.info(f"📊 Rufe Account-Info ab...")
        account = client.get_account()
        logging.info(f"✅ Account-Info: {account}")        

        # === Marktdaten abrufen ===
        # logging.info(f"📊 Rufe Marktdaten ab...")
        # tickers = market.get_tickers(
        #     symbols=SYMBOLS
        # )
        # logging.info(f"Tickers data: {tickers}")

        # === Orderbuch abrufen ===
        # logging.info(f"📊 Rufe future order book ab...")
        # depth = market.get_depth(
        #     symbol=SYMBOL,
        #     limit="50"           # Fixed gear enumeration value: 1/5/15/50/max
        # )
        # logging.info(f"Order Book: {depth}")

        # === Fundingrate abrufen ===
        # logging.info(f"📊 Rufe Funding Rate ab...")
        # funding_rate = market.get_funding_rate(
        #     symbol=SYMBOL
        # )
        # logging.info(f"Funding Rate: {funding_rate}")

        # === Fundingraten abrufen ===
        # logging.info(f"📊 Rufe Funding Rate Batch ab...")
        # funding_rate = market.get_batch_funding_rate()
        # logging.info(f"Funding Rate Batch: {funding_rate}")

        # === K-Line (Candlestick) abrufen ===
        # current_time = int(time.time() * 1000)          # Current timestamp (milliseconds)
        # one_hour_ago = current_time - (60 * 60 * 1000)  # One hour ago timestamp
        # end_time_UTC = datetime.datetime.fromtimestamp(current_time / 1000).strftime('%H:%M:%S')
        # start_time_UTC = datetime.datetime.fromtimestamp(one_hour_ago / 1000).strftime('%H:%M:%S')

        # klines = market.get_kline(
        #     symbol=SYMBOL, 
        #     interval="1m",              # kline interval such as 1m 5m 15m 30m 1h 2h 4h 6h 8h 12h 1d 3d 1w 1M
        #     limit=5,                    # Default: 100, maximum: 200
        #     start_time=one_hour_ago,    # Unix timestamp, such as 1672410780000
        #     end_time=current_time,      # Unix timestamp, such as 1672410780000
        #     type="LAST_PRICE"           # values: LAST_PRICE, MARK_PRICE
        #     )
        # logging.info(f"Klines data: {start_time_UTC} - {end_time_UTC}, {klines}")

        # === Coin Details abrufen ===
        logging.info(f"📊 Rufe Coin Detail ab...")
        trading_pairs = market.get_trading_pairs(
            symbols=None                  # values: None, SYMBOLS
        )
        logging.info(f"Coin Detail: {trading_pairs}")
        
        # === Margin Mode ändern ===
        # logging.info(f"⚙️ Ändere Margin Mode für {SYMBOL} auf ISOLATION...")
        # margin_mode_result = client.change_margin_mode(
        #     symbol=SYMBOL,
        #     margin_mode="ISOLATION",
        #     margin_coin=MARGIN_COIN
        # )
        # logging.info(f"✅ Margin Mode geändert: {margin_mode_result}")

        
        # === Position Mode ändern ===
        # logging.info(f"⚙️ Ändere Position Mode auf HEDGE...")
        # position_mode_result = client.change_position_mode(mode="HEDGE")
        # logging.info(f"✅ Position Mode geändert: {position_mode_result}")
        
        # logging.info("🎉 Alle Tests erfolgreich abgeschlossen!")


        # === Leverage ändern ===
        # logging.info(f"⚙️ Ändere Leverage für {SYMBOL} auf 5x...")
        # leverage_result = client.change_leverage(
        #     symbol=SYMBOL,
        #     leverage=5,
        #     margin_coin=MARGIN_COIN
        # )
        # logging.info(f"✅ Leverage geändert: {leverage_result}")
        
        # === Leverage- und Margin Mode-Info abrufen ===
        # logging.info(f"📊 Rufe Leverage- und Margin Mode-Info ab...")
        # leverage_margin_result = client.get_leverage_margin_mode(
        #     symbol=SYMBOL
        # )
        # logging.info(f"✅ Leverage- und Margin: {leverage_margin_result}")      


    except Exception as e:
        logging.error(f"❌ Fehler beim Testen: {e}")


if __name__ == "__main__":
    asyncio.run(main())