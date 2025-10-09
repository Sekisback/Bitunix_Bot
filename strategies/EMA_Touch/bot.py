#!/usr/bin/env python3
"""
EMA21 Touch Trading Bot - WebSocket Version
Event-basiert statt Polling
"""

import asyncio
import argparse
import sys
import os
from pathlib import Path
import pandas as pd
import logging

# WebSocket-Library auf WARNING setzen
logging.getLogger('websockets').setLevel(logging.WARNING)

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
    generate_client_id,
    WebSocketKlineManager
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


class TradingBot:
    """
    Trading Bot mit WebSocket-Integration
    """
    
    def __init__(self, config: dict, client_pri, client_pub):
        """
        Args:
            config: Config Dictionary
            client_pri: Private API Client
            client_pub: Public API Client
        """
        self.config = config
        self.client_pri = client_pri
        self.client_pub = client_pub
        
        # Bot State
        self.active_position = False
        self.ws_manager = None
        
        # NEU: Simulierte Position für DRY RUN
        self.sim_position = {
            'active': False,
            'side': None,      # "LONG" oder "SHORT"
            'entry': None,     # Entry Preis
            'tp': None,        # Take Profit
            'sl': None,        # Stop Loss
            'qty': None        # Menge
        }
        
        # Config auslesen
        self.symbol = config['symbol']
        self.interval = config['trading']['interval']
        self.leverage = config['trading']['leverage']
        self.dry_run = config['trading']['dry_run']
        self.debug = config['system']['debug']
        
    async def on_new_kline(self, kline: dict, df: pd.DataFrame):
        """
        Callback bei neuer Kerze vom WebSocket
        
        Args:
            kline: Dict mit aktueller Kerze
            df: DataFrame mit allen gepufferten Kerzen
        """
        try:
            if self.debug:
                logging.info("=" * 60)
                logging.info(f"🕯️  Neue Kerze: {kline['timestamp'].strftime('%H:%M:%S')} | C: {kline['close']:.5f}")
            
            # === Position Check ===
            if self.dry_run:
                # DRY RUN: Simulierte Position mit TP/SL Check
                if self.sim_position['active']:
                    current_price = kline['close']
                    
                    position_closed = False
                    
                    if self.sim_position['side'] == "LONG":
                        # LONG: TP erreicht?
                        if current_price >= self.sim_position['tp']:
                            profit = (current_price - self.sim_position['entry']) * self.sim_position['qty']
                            logging.info("=" * 60)
                            logging.info(f"✅ [SIMULATION] TP erreicht!")
                            logging.info(f"Entry: {self.sim_position['entry']:.5f} → Exit: {current_price:.5f}")
                            logging.info(f"Gewinn: +{profit:.2f} USDT")
                            logging.info("=" * 60)
                            print(f"✅ [DRY RUN] TP erreicht! Gewinn: +{profit:.2f} USDT")
                            position_closed = True
                        
                        # LONG: SL erreicht?
                        elif current_price <= self.sim_position['sl']:
                            loss = (self.sim_position['entry'] - current_price) * self.sim_position['qty']
                            logging.info("=" * 60)
                            logging.info(f"❌ [SIMULATION] SL erreicht!")
                            logging.info(f"Entry: {self.sim_position['entry']:.5f} → Exit: {current_price:.5f}")
                            logging.info(f"Verlust: -{loss:.2f} USDT")
                            logging.info("=" * 60)
                            print(f"❌ [DRY RUN] SL erreicht! Verlust: -{loss:.2f} USDT")
                            position_closed = True
                    
                    else:  # SHORT
                        # SHORT: TP erreicht?
                        if current_price <= self.sim_position['tp']:
                            profit = (self.sim_position['entry'] - current_price) * self.sim_position['qty']
                            logging.info("=" * 60)
                            logging.info(f"✅ [SIMULATION] TP erreicht!")
                            logging.info(f"Entry: {self.sim_position['entry']:.5f} → Exit: {current_price:.5f}")
                            logging.info(f"Gewinn: +{profit:.2f} USDT")
                            logging.info("=" * 60)
                            print(f"✅ [DRY RUN] TP erreicht! Gewinn: +{profit:.2f} USDT")
                            position_closed = True
                        
                        # SHORT: SL erreicht?
                        elif current_price >= self.sim_position['sl']:
                            loss = (current_price - self.sim_position['entry']) * self.sim_position['qty']
                            logging.info("=" * 60)
                            logging.info(f"❌ [SIMULATION] SL erreicht!")
                            logging.info(f"Entry: {self.sim_position['entry']:.5f} → Exit: {current_price:.5f}")
                            logging.info(f"Verlust: -{loss:.2f} USDT")
                            logging.info("=" * 60)
                            print(f"❌ [DRY RUN] SL erreicht! Verlust: -{loss:.2f} USDT")
                            position_closed = True
                    
                    if position_closed:
                        # Position zurücksetzen
                        self.sim_position['active'] = False
                        print("✅ Simulierte Position geschlossen - suche neue Signale...")
                    else:
                        # Position noch aktiv - überspringe Rest
                        if self.debug:
                            logging.info(f"⏳ Simulierte Position läuft: Preis={current_price:.5f}, TP={self.sim_position['tp']:.5f}, SL={self.sim_position['sl']:.5f}")
                        return
            
            else:
                # LIVE MODE: Echte Position checken
                has_position = check_active_position(
                    self.client_pri,
                    symbol=self.symbol,
                    margin_coin="USDT"
                )
                
                if has_position:
                    if not self.active_position:
                        logging.info("🔒 Aktive Position erkannt!")
                        self.active_position = True
                    else:
                        if self.debug:
                            logging.info("⏳ Position noch aktiv - überspringe")
                    return
                else:
                    if self.active_position:
                        logging.info("✅ Position geschlossen!")
                        self.active_position = False
            
            # === Genug Daten vorhanden? ===
            if len(df) < self.config['system']['backtest_bars']:
                if self.debug:
                    logging.info(f"⏳ Warte auf genug Kerzen: {len(df)}/{self.config['system']['backtest_bars']}")
                    logging.info("=" * 60)
                return
            
            # DataFrame kopieren für Berechnungen
            df_analysis = df.copy()
            
            # === EMAs berechnen ===
            df_analysis = add_emas(df_analysis, periods=[
                self.config['indicators']['ema_fast'],
                self.config['indicators']['ema_slow'],
                self.config['indicators']['ema_trend']
            ])

            # === DEBUG: EMA-Werte anzeigen ===
            if self.debug:
                current_price = kline['close']
                ema21 = df_analysis[f"ema_{self.config['indicators']['ema_fast']}"].iloc[-1]
                ema50 = df_analysis[f"ema_{self.config['indicators']['ema_slow']}"].iloc[-1]
                ema200 = df_analysis[f"ema_{self.config['indicators']['ema_trend']}"].iloc[-1]
                
                # Abstand zu EMA21
                distance_to_ema21 = abs((current_price - ema21) / ema21 * 100)
                touch_threshold = self.config['entry']['touch_threshold_pct']
                
                # Abstand in USDT
                distance_usdt = abs(current_price - ema21)
                
                # Richtung bestimmen
                if current_price > ema21:
                    direction = "⬆️"  # Preis über EMA
                else:
                    direction = "⬇️"  # Preis unter EMA
                
                # Touch-Zone berechnen
                touch_range_percent = touch_threshold  # z.B. 0.05
                touch_lower = ema21 * (1 - touch_range_percent / 100)
                touch_upper = ema21 * (1 + touch_range_percent / 100)
                
                logging.info(f"💹 Preis:       {current_price:.5f}")
                logging.info(
                    f"📈 EMA21:       {ema21:.5f} | "
                    f"Abstand: {direction} {distance_usdt:.5f} USDT | "
                    f"Touch-Zone: {touch_lower:.5f}-{touch_upper:.5f}"
                )
                logging.info(f"📊 EMA50:       {ema50:.5f}")
                logging.info(f"📉 EMA200:      {ema200:.5f}")
                
                # Hierarchie prüfen
                if ema21 > ema50 > ema200:
                    logging.info(f"🟢 Hierarchie:  LONG (21 > 50 > 200)")
                elif ema21 < ema50 < ema200:
                    logging.info(f"🔴 Hierarchie:  SHORT (21 < 50 < 200)")
                else:
                    logging.info(f"⚪ Hierarchie:  Keine klare Richtung")
            
            # === Account Balance (nur einmal pro Minute cachen) ===
            current_minute = kline['timestamp'].replace(second=0, microsecond=0)
            
            if not hasattr(self, '_cached_balance') or \
            not hasattr(self, '_cache_time') or \
            self._cache_time != current_minute:
                
                # Neu abrufen
                self._cached_balance = get_account_balance(self.client_pri, margin_coin="USDT")
                self._cache_time = current_minute
                
                if self.debug:
                    logging.info(f"💰 Guthaben:    {self._cached_balance:.2f} USDT (aktualisiert)")
            
            balance = self._cached_balance
            
            if balance <= 0:
                logging.error("❌ Kein Guthaben!")
                if self.debug:
                    logging.info("=" * 60)
                return
            
            # === Trade Parameter berechnen (nur einmal cachen) ===
            current_price = kline['close']
            fixed_qty = self.config['trading'].get('fixed_qty', None)
            
            if not hasattr(self, '_cached_qty') or \
            not hasattr(self, '_qty_cache_time') or \
            self._qty_cache_time != current_minute:
                
                # Neu berechnen
                self._cached_qty = calc_trade_parameters(
                    client_pub=self.client_pub,
                    symbol=self.symbol,
                    balance=balance,
                    current_price=current_price,
                    leverage=self.leverage,
                    tp_pct=self.config['risk']['tp_pct'],
                    sl_pct=self.config['risk']['sl_pct'],
                    total_fees=self.config['risk']['fee_pct'] * 2,
                    fixed_qty=fixed_qty
                )
                self._qty_cache_time = current_minute
            
            qty = self._cached_qty
            
            # === Signal generieren ===
            signal = generate_trade_signal(df_analysis, self.config)

            # === WICHTIG: Touch-Status immer loggen ===
            if self.debug:
                # Touch-Check durchführen (auch wenn kein Signal)
                from signals.ema21_touch import check_ema21_touch
                
                touch = check_ema21_touch(
                    df_analysis,
                    ema_fast=self.config['indicators']['ema_fast'],
                    threshold_pct=self.config['entry']['touch_threshold_pct']
                )
                
                if touch["is_touch"]:
                    logging.info("=" * 60)
                    logging.info(f"👆 EMA21 TOUCH ERKANNT!")
                    logging.info(f"📏 Abstand:     {touch['distance_pct']:.3f}%")
                    logging.info(f"📍 Touch Side:  {touch['side']}")
                    
                    # Prüfe warum kein Trade
                    if not signal["signal"]:
                        # Mehrzeilig formatieren für bessere Lesbarkeit
                        reason_parts = signal['reason'].split(': ', 1)  # Split am ersten ":"
                        
                        if len(reason_parts) == 2:
                            # Hat Format "Setup Status: Details"
                            logging.info(f"⛔ BLOCKIERT:   {reason_parts[0]}:")
                            
                            # Details aufsplitten am " | "
                            details = reason_parts[1].split(' | ')
                            for detail in details:
                                logging.info(f"               • {detail}")
                        else:
                            # Fallback: normal ausgeben
                            logging.info(f"⛔ BLOCKIERT:   {signal['reason']}")
                    else:
                        logging.info(f"✅ SIGNAL:      {signal['signal']}")
                    
                    logging.info("=" * 60)
                            
            # === Order platzieren ===
            if signal["signal"]:
                logging.info("=" * 60)
                logging.info(f"✅ SIGNAL GEFUNDEN: {signal['signal']}")
                logging.info(f"📋 Grund: {signal['reason']}")
                logging.info("=" * 60)
                
                if self.dry_run:
                    # DRY RUN Mode
                    place_order_dryrun(
                        signal=signal,
                        qty=qty,
                        balance=balance,
                        leverage=self.leverage,
                        fee_pct=self.config['risk']['fee_pct']
                    )
                    
                    # NEU: Simulierte Position speichern
                    self.sim_position['active'] = True
                    self.sim_position['side'] = signal['signal']
                    self.sim_position['entry'] = signal['entry_price']
                    self.sim_position['tp'] = signal['tp']
                    self.sim_position['sl'] = signal['sl']
                    self.sim_position['qty'] = qty
                    
                    print(f"🔒 [DRY RUN] Simulierte {signal['signal']} Position eröffnet - tracke TP/SL...")
                    
                else:
                    # LIVE Mode
                    logging.info("🚀 LIVE MODE - Platziere Order...")
                    print(f"🚀 LIVE MODE - Platziere {signal['signal']} Order...")
                    
                    client_id = generate_client_id(
                        self.config['trading']['client_id_prefix']
                    )
                    
                    try:
                        place_order_live(
                            client_pri=self.client_pri,
                            signal=signal,
                            qty=qty,
                            client_id=client_id,
                            symbol=self.symbol
                        )
                        print("✅ Order erfolgreich platziert!")
                        
                        # Nach Order: Position als aktiv markieren
                        self.active_position = True
                        
                    except Exception as e:
                        logging.error(f"❌ Order fehlgeschlagen: {e}")
                        print(f"❌ Order fehlgeschlagen: {e}")
                    
        except Exception as e:
            logging.error(f"❌ Fehler in Kline-Handler: {e}")
            logging.exception("Traceback:")


    async def initialize_historical_data(self):
        """
        Lädt initiale historische Daten via REST
        Füllt damit den WebSocket-Buffer vor
        """
        logging.info("📊 Lade historische Daten...")
        
        try:
            df_historical = fetch_historical_klines(
                self.client_pub,
                self.symbol,
                self.interval,
                limit=self.config['system']['backtest_bars'],
                timezone_offset=self.config['system']['timezone_offset']
            )
            
            logging.info(f"✅ {len(df_historical)} historische Kerzen geladen")
            
            # Historische Kerzen in WebSocket-Buffer einfügen
            for idx, row in df_historical.iterrows():
                kline_dict = {
                    'timestamp': idx,
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'close': row['close'],
                    'volume': row['volume'],
                    'turnover': row.get('turnover', 0.0)
                }
                self.ws_manager.kline_buffer.append(kline_dict)
            
            logging.info(f"✅ Buffer initialisiert mit {len(self.ws_manager.kline_buffer)} Kerzen")
            
        except Exception as e:
            logging.error(f"❌ Fehler beim Laden historischer Daten: {e}")
            raise
    
    async def start(self):
        """
        Startet den Bot
        """
        logging.info("🤖 Bot startet...")
        
        try:
            # 1. WebSocket-Manager erstellen (noch nicht starten!)
            self.ws_manager = WebSocketKlineManager(
                symbol=self.symbol,
                interval=self.interval,
                buffer_size=self.config['system']['backtest_bars'],
                timezone_offset=self.config['system']['timezone_offset'],
                price_type="market",
                on_kline_callback=self.on_new_kline
            )
            
            # 2. Historische Daten laden und Buffer füllen
            await self.initialize_historical_data()
            
            # 3. WebSocket starten (jetzt mit gefülltem Buffer)
            logging.info("🔌 Starte WebSocket-Verbindung...")
            await self.ws_manager.start()
            
        except asyncio.CancelledError:
            logging.info("\n" + "=" * 60)
            logging.info("🛑 Bot wird gestoppt...")
            logging.info("=" * 60)
        except KeyboardInterrupt:
            logging.info("\n" + "=" * 60)
            logging.info("🛑 Bot gestoppt durch Benutzer (CTRL+C)")
            logging.info("=" * 60)
        finally:
            if self.ws_manager:
                self.ws_manager.stop()
            logging.info("👋 Bot beendet - Auf Wiedersehen!")
            logging.info("=" * 60)


async def main():
    """Hauptfunktion"""
    
    # === Command Line Arguments ===
    parser = argparse.ArgumentParser(
        description='EMA21 Touch Trading Bot - WebSocket Version',
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
    print("🤖 EMA21 Touch Trading Bot - WebSocket Version")
    print("=" * 60)
    
    try:
        strategy_dir = Path(__file__).parent
        os.chdir(strategy_dir)
        config = load_config(args.config)
        os.chdir(root_dir)
    except Exception as e:
        print(f"❌ Fehler beim Laden der Config: {e}")
        sys.exit(1)
    
    symbol = config['symbol']
    fixed_qty = config['trading'].get('fixed_qty', None)
    
    qty_display = f"Fix: {fixed_qty} Coins" if fixed_qty else "Automatisch berechnet"
    
    print(f"Symbol:       {symbol}")
    print(f"Interval:     {config['trading']['interval']}")
    print(f"Leverage:     {config['trading']['leverage']}x")
    print(f"Menge:        {qty_display}")
    print(f"ADX Filter:   {config['trend_filter']['adx_threshold']}")
    print(f"EMA Distance: {config['trend_filter']['ema_distance_threshold']}%")
    print(f"TP / SL:      {config['risk']['tp_pct']*100}% / {config['risk']['sl_pct']*100}%")
    print(f"Mode:         {'DRY RUN' if config['trading']['dry_run'] else 'LIVE MODE ⚠️'}")
    print(f"Debug:        {'AN' if config['system']['debug'] else 'AUS'}")
    print(f"Data Source:  WebSocket (Echtzeit)")
    print("=" * 60)
    
    # === Logging Setup ===
    setup_logging(
        symbol=symbol,
        strategy="EMA_Touch",
        debug=config['system']['debug']
    )
    
    # Core-Module auf WARNING setzen (keine Debug-Spam)
    logging.getLogger('core.open_api_ws_future_public').setLevel(logging.WARNING)
    logging.getLogger('websockets').setLevel(logging.WARNING)


    # === Log Config Settings ===
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
    logging.info(f"Data Source:    WebSocket")
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
    
    # === Bot erstellen und starten ===
    bot = TradingBot(config, client_pri, client_pub)
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print("🛑 Bot gestoppt durch Benutzer")
        print("=" * 60)