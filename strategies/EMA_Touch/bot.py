#!/usr/bin/env python3
"""
EMA21 Touch Trading Bot
Nutzt modulare Komponenten für saubere Struktur
"""

import asyncio
import argparse
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

# Working Directory auf Root setzen
root_dir = Path(__file__).parent.parent.parent
os.chdir(root_dir)

# Import Paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(root_dir))

# Core API Clients
from core.config import Config
from core.open_api_http_future_private import OpenApiHttpFuturePrivate
from core.open_api_http_future_public import OpenApiHttpFuturePublic

# Strategy Module
from utils import (
    load_config,
    setup_logging,
    fetch_historical_klines,
    calc_trade_parameters,
    generate_client_id
)
from indicators import add_emas
from signals import generate_trade_signal
from trading import (
    place_order_dryrun,
    place_order_live,
    get_account_balance,
    check_active_position,
    setup_account
)

import logging


async def bot_loop(config: dict, client_pri, client_pub):
    """
    Hauptschleife - läuft kontinuierlich
    
    Args:
        config: Config Dictionary
        client_pri: Private API Client
        client_pub: Public API Client
    """
    symbol = config['symbol']
    interval = config['trading']['interval']
    leverage = config['trading']['leverage']
    dry_run = config['trading']['dry_run']
    debug = config['system']['debug']
    backtest_bars = config['system']['backtest_bars']
    
    logging.info("🤖 Bot Loop gestartet - Endlos-Modus")
    
    active_position = False
    
    try:
        while True:
            try:
                if debug:
                    logging.debug("=" * 60)
                    logging.debug(f"Iteration: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    logging.debug("=" * 60)
                
                # === Position Check ===
                try:
                    if dry_run:
                        # Im DRY RUN keine Position Check
                        active_position = False
                    else:
                        has_position = check_active_position(
                            client_pri,
                            symbol=symbol,
                            margin_coin="USDT"
                        )
                        
                        if has_position:
                            if not active_position:
                                logging.info("🔒 Aktive Position erkannt!")
                                print("🔒 Aktive Position erkannt - warte auf Schließung...")
                                active_position = True
                            else:
                                if debug:
                                    logging.info("⏳ Position noch aktiv - warte...")
                            
                            await asyncio.sleep(10)
                            continue
                        else:
                            if active_position:
                                logging.info("✅ Position geschlossen!")
                                print("✅ Position geschlossen - suche neue Signale...")
                            active_position = False
                            
                except Exception as e:
                    logging.error(f"❌ Fehler beim Position-Check: {e}")
                    if dry_run:
                        active_position = False
                    else:
                        await asyncio.sleep(30)
                        continue
                
                if debug:
                    logging.debug("Keine aktive Position - suche Signal...")
                
                # === Kerzendaten laden ===
                df = fetch_historical_klines(
                    client_pub,
                    symbol,
                    interval,
                    limit=backtest_bars,
                    timezone_offset=config['system']['timezone_offset']
                )
                
                # === Aktuellen Preis holen ===
                ticker_data = client_pub.get_tickers(symbol)
                if isinstance(ticker_data, list) and ticker_data:
                    current_price = float(ticker_data[0].get("last", 0.0))
                elif isinstance(ticker_data, dict):
                    current_price = float(ticker_data.get("last", 0.0))
                else:
                    raise ValueError("Keine Preisdaten erhalten")
                
                # === Aktuelle Kerze simulieren ===
                last_timestamp = df.index[-1]
                
                # Interval zu Timedelta
                interval_map = {
                    "1m": timedelta(minutes=1),
                    "3m": timedelta(minutes=3),
                    "5m": timedelta(minutes=5),
                    "15m": timedelta(minutes=15),
                    "30m": timedelta(minutes=30),
                    "1h": timedelta(hours=1),
                    "2h": timedelta(hours=2),
                    "4h": timedelta(hours=4),
                    "1d": timedelta(days=1)
                }
                
                delta = interval_map.get(interval, timedelta(minutes=1))
                current_time = last_timestamp + delta
                
                # Neue Kerze mit aktuellem Preis
                new_row = pd.DataFrame({
                    'open': [df['close'].iloc[-1]],
                    'high': [max(df['close'].iloc[-1], current_price)],
                    'low': [min(df['close'].iloc[-1], current_price)],
                    'close': [current_price],
                    'volume': [0.0],
                    'turnover': [0.0]
                }, index=[current_time])
                
                df = pd.concat([df, new_row])
                
                # === EMAs berechnen ===
                df = add_emas(df, periods=[
                    config['indicators']['ema_fast'],
                    config['indicators']['ema_slow'],
                    config['indicators']['ema_trend']
                ])
                
                # === Account Balance ===
                balance = get_account_balance(client_pri, margin_coin="USDT")
                if balance <= 0:
                    logging.error("❌ Kein Guthaben!")
                    await asyncio.sleep(60)
                    continue
                
                # === Trade Parameter berechnen ===
                fixed_qty = config['trading'].get('fixed_qty', None)
                qty = calc_trade_parameters(  # ← Nur noch qty
                    client_pub=client_pub,
                    symbol=symbol,
                    balance=balance,
                    current_price=current_price,
                    leverage=leverage,
                    tp_pct=config['risk']['tp_pct'],
                    sl_pct=config['risk']['sl_pct'],
                    total_fees=config['risk']['fee_pct'] * 2,
                    fixed_qty=fixed_qty
                )
                
                # === Signal generieren ===
                signal = generate_trade_signal(df, config)
                
                # === Order platzieren ===
                if signal["signal"]:
                    # IMMER loggen bei Signal!
                    logging.info(f"✅ Signal gefunden: {signal['signal']}")
                    
                    if dry_run:
                        # DRY RUN Mode
                        place_order_dryrun(
                            signal=signal,
                            qty=qty,
                            balance=balance,
                            leverage=leverage,
                            fee_pct=config['risk']['fee_pct']
                        )
                    else:
                        # LIVE Mode
                        logging.info("🚀 LIVE MODE - Platziere Order...")
                        print(f"🚀 LIVE MODE - Platziere {signal['signal']} Order...")
                        
                        # Client ID generieren
                        client_id = generate_client_id(
                            config['trading']['client_id_prefix']
                        )
                        
                        try:
                            place_order_live(
                                client_pri=client_pri,
                                signal=signal,
                                qty=qty,
                                client_id=client_id,
                                symbol=symbol
                            )
                            print("✅ Order erfolgreich platziert!")
                        except Exception as e:
                            logging.error(f"❌ Order fehlgeschlagen: {e}")
                            print(f"❌ Order fehlgeschlagen: {e}")
                    
                    # Nach Signal warten
                    await asyncio.sleep(60)
                else:
                    if debug:
                        logging.info(f"Kein Signal: {signal['reason']}")
                    await asyncio.sleep(10)
                
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logging.error(f"❌ Fehler in Iteration: {e}")
                logging.exception("Traceback:")
                await asyncio.sleep(30)
    
    except asyncio.CancelledError:
        logging.info("\n" + "=" * 60)
        logging.info("🛑 Bot wird gestoppt...")
        logging.info("=" * 60)
    except KeyboardInterrupt:
        logging.info("\n" + "=" * 60)
        logging.info("🛑 Bot gestoppt durch Benutzer (CTRL+C)")
        logging.info("=" * 60)
    finally:
        logging.info("👋 Bot beendet - Auf Wiedersehen!")
        logging.info("=" * 60)


async def main():
    """Hauptfunktion"""
    
    # === Command Line Arguments ===
    parser = argparse.ArgumentParser(
        description='EMA21 Touch Trading Bot',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
                Beispiele:
                python bot.py --config ONDOUSDT
                python bot.py --config XRPUSDT
                python bot.py --config BTCUSDT
        """
    )
    parser.add_argument(
        '--config',
        required=True,
        help='Coin Config Name (z.B. ONDOUSDT, XRPUSDT, BTCUSDT)'
    )
    
    args = parser.parse_args()
    
    # === Config laden ===
    print("\n" + "=" * 60)
    print("🤖 EMA21 Touch Trading Bot")
    print("=" * 60)
    
    try:
        # Wechsel zu Strategy Ordner für Config Load
        strategy_dir = Path(__file__).parent
        os.chdir(strategy_dir)
        config = load_config(args.config)
        os.chdir(root_dir)
    except Exception as e:
        print(f"❌ Fehler beim Laden der Config: {e}")
        sys.exit(1)
    
    symbol = config['symbol']
    fixed_qty = config['trading'].get('fixed_qty', None)
    
    # Qty Anzeige
    if fixed_qty is not None:
        qty_display = f"Fix: {fixed_qty} Coins"
    else:
        qty_display = "Automatisch berechnet"
    
    print(f"Symbol:       {symbol}")
    print(f"Interval:     {config['trading']['interval']}")
    print(f"Leverage:     {config['trading']['leverage']}x")
    print(f"Menge:        {qty_display}")
    
    print(f"ADX Filter:   {config['trend_filter']['adx_threshold']}")
    print(f"EMA Distance: {config['trend_filter']['ema_distance_threshold']}%")
    print(f"TP / SL:      {config['risk']['tp_pct']*100}% / {config['risk']['sl_pct']*100}%")
    print(f"Mode:         {'DRY RUN' if config['trading']['dry_run'] else 'LIVE MODE ⚠️'}")
    print(f"Debug:        {'AN' if config['system']['debug'] else 'AUS'}")
    print("=" * 60)
    
    # === Logging Setup ===
    setup_logging(
        symbol=symbol,
        strategy="EMA_Touch",
        debug=config['system']['debug']
    )
    
    # === Log Config Settings auch ins Log ===
    logging.info("=" * 60)
    logging.info("⚙️ Bot Konfiguration")
    logging.info("=" * 60)
    logging.info(f"Symbol:         {symbol}")
    logging.info(f"Interval:       {config['trading']['interval']}")
    logging.info(f"Leverage:       {config['trading']['leverage']}x")
    logging.info(f"Menge:          {qty_display}")
    logging.info(f"TP / SL:        {config['risk']['tp_pct']*100}% / {config['risk']['sl_pct']*100}%")
    logging.info(f"ADX Threshold:  {config['trend_filter']['adx_threshold']}")
    logging.info(f"EMA Distance:   {config['trend_filter']['ema_distance_threshold']}%")
    logging.info(f"Touch Threshold: {config['entry']['touch_threshold_pct']}%")
    logging.info(f"Trendfilter:    {'AN' if config['trend_filter']['use_filter'] else 'AUS'}")
    logging.info(f"Debug Mode:     {'AN' if config['system']['debug'] else 'AUS'}")
    logging.info(f"Mode:           {'DRY RUN' if config['trading']['dry_run'] else 'LIVE MODE ⚠️'}")
    logging.info("=" * 60)
    
    # === API Clients ===
    cfg = Config()
    client_pri = OpenApiHttpFuturePrivate(cfg)
    client_pub = OpenApiHttpFuturePublic(cfg)
    
    # === Account Setup (nur LIVE Mode) ===
    if not config['trading']['dry_run']:
        try:
            setup_account(
                client_pri,
                symbol=symbol,
                leverage=config['trading']['leverage'],
                margin_coin="USDT"
            )
        except Exception as e:
            logging.error(f"❌ Account Setup fehlgeschlagen: {e}")
            print(f"❌ Account Setup fehlgeschlagen: {e}")
            sys.exit(1)
    
    print("Bot startet... Drücke CTRL+C zum Beenden\n")
    
    # === Bot starten ===
    try:
        await bot_loop(config, client_pri, client_pub)
    except KeyboardInterrupt:
        pass  # Wird bereits in bot_loop() behandelt


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Sauberer Exit ohne Traceback
        print("\n" + "=" * 60)
        print("🛑 Bot gestoppt durch Benutzer")
        print("=" * 60)