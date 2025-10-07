# strategies/strategy_ema21touch.py
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import time
import pandas as pd
import numpy as np
from datetime import timedelta, datetime

# Pfad zum Hauptverzeichnis hinzufügen
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.config import Config
from core.open_api_http_future_private import OpenApiHttpFuturePrivate
from core.open_api_http_future_public import OpenApiHttpFuturePublic

# ==================================================
# === PARAMETER ====================================
# ==================================================

DRY_RUN                 = True

SYMBOL                  = "ONDOUSDT"    # Coin
INTERVAL                = "1m"          # Timeframe
LEVERAGE                = 3             # Leverage

TP_PCT                  = 0.01          # Take-Profit-Ziel (1 %)
SL_PCT                  = 0.005         # Stop-Loss (0.5 %)
FEE_PCT                 = 0.00042       # 0.042 % pro Seite
TOTAL_FEES              = FEE_PCT * 2   # Entry + Exit

TIMEZONE_OFFSET         = 2             # UTC+2 für deutsche Zeit

# EMA Parameter
EMA_FAST                = 21            # Schnelle EMA (Entry Trigger)
EMA_SLOW                = 50            # Mittlere EMA (Stop Loss)
EMA_TREND               = 200           # Langsame EMA (Trendfilter)

# Trendfilter Parameter (zum Testen variabel!)
ADX_THRESHOLD           = 23.0          # Min ADX für Trend (20-30 testen)
EMA_DISTANCE_THRESHOLD  = 0.2           # Min EMA Abstand in % (0.3-1.0 testen)
USE_TREND_FILTER        = True          # Filter ein/aus zum Testen

# Entry Parameter
TOUCH_THRESHOLD_PCT     = 0.05          # Max Abstand zu EMA21 für Entry (0.05%)

# Gebug Mode
DEBUG                   = False         # Schaltet Protokol im Log ein

# ==================================================
# === LOGGING SETUP ================================
# ==================================================
def setup_logging():
    """
    Richtet Logging ein: Console + Datei
    """
    # Log Ordner erstellen
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Dateiname mit Datum
    log_file = os.path.join(log_dir, f"bot_{datetime.now().strftime('%Y%m%d')}.log")
    
    # Root Logger konfigurieren
    logger = logging.getLogger()
    
    # Level abhängig von DEBUG
    if DEBUG:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    
    # Alle bestehenden Handler entfernen
    logger.handlers.clear()
    
    # Format für beide Handler
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
    
    # Console Handler - nur für wichtige Meldungen (immer aus)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.CRITICAL)  # Praktisch immer aus
    console_handler.setFormatter(formatter)
    
    # File Handler (rotiert bei 10MB, hält 5 Dateien)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    
    # Level abhängig von DEBUG
    if DEBUG:
        file_handler.setLevel(logging.DEBUG)
    else:
        file_handler.setLevel(logging.INFO)
    
    file_handler.setFormatter(formatter)
    
    # Handler hinzufügen
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    # Start-Meldung
    if DEBUG:
        logging.info(f"🔍 DEBUG MODE - Vollständiges Logging: {log_file}")
    else:
        logging.info(f"🔍 Logging eingerichtet: {log_file} (nur Orders + Errors)")



# ==================================================
# === SYMBOL INFO ==================================
# ==================================================
def get_symbol_info(client_pub, symbol: str) -> dict:
    """
    Holt Trading Pair Informationen für ein Symbol
    
    Args:
        client_pub: Public API Client
        symbol: Trading Symbol (z.B. "BTCUSDT")
    
    Returns:
        Dict mit Symbol-Infos (basePrecision, minTradeVolume, etc.)
    """
    try:
        # Trading Pair Info abrufen
        pair_info = client_pub.get_trading_pairs(symbols=symbol)
        
        # Prüfe ob Daten vorhanden
        if not pair_info or len(pair_info) == 0:
            raise ValueError(f"Keine Trading Pair Info für {symbol} gefunden")
        
        # Erste (und einzige) Position
        info = pair_info[0]
        
        # Extrahiere relevante Infos
        base_precision = int(info['basePrecision'])
        min_trade_volume = float(info['minTradeVolume'])
        
        if DEBUG:
            logging.info(f"📊 Symbol Info: Precision={base_precision}, Min Volume={min_trade_volume}")
        
        return {
            'base_precision': base_precision,
            'quote_precision': int(info['quotePrecision']),
            'min_trade_volume': min_trade_volume,
            'max_leverage': int(info['maxLeverage']),
            'min_leverage': int(info['minLeverage'])
        }
        
    except Exception as e:
        logging.error(f"❌ Fehler beim Abrufen der Symbol Info: {e}")
        raise


# ==================================================
# === TRENDFILTER ==================================
# ==================================================
def calculate_adx(df: pd.DataFrame, dilen: int = 14, adxlen: int = 14) -> float:
    """
    Berechnet ADX exakt wie TradingView (mit RMA = Wilder's Smoothing)
    
    Args:
        df: DataFrame mit high, low, close
        dilen: DI Length (Standard 14)
        adxlen: ADX Smoothing (Standard 14)
    
    Returns:
        ADX Wert
    """
    # Mindestens benötigte Kerzen
    min_bars = max(dilen, adxlen) * 3
    if len(df) < min_bars:
        logging.warning(f"Zu wenig Daten für ADX: {len(df)} < {min_bars}")
        return 0.0
    
    # Kopie erstellen
    df_adx = df.copy()
    
    # +DM und -DM wie TradingView
    df_adx['up'] = df_adx['high'].diff()
    # Low Änderung negativ
    df_adx['down'] = -df_adx['low'].diff()
    
    # +DM: up > down AND up > 0
    df_adx['plus_dm'] = np.where(
        (df_adx['up'] > df_adx['down']) & (df_adx['up'] > 0),
        df_adx['up'],
        0
    )
    
    # -DM: down > up AND down > 0
    df_adx['minus_dm'] = np.where(
        (df_adx['down'] > df_adx['up']) & (df_adx['down'] > 0),
        df_adx['down'],
        0
    )
    
    # True Range (wie TradingView ta.tr)
    df_adx['tr1'] = df_adx['high'] - df_adx['low']
    # TR mit vorherigem Close
    df_adx['tr2'] = abs(df_adx['high'] - df_adx['close'].shift(1))
    # TR mit vorherigem Close
    df_adx['tr3'] = abs(df_adx['low'] - df_adx['close'].shift(1))
    # Max der drei Werte
    df_adx['tr'] = df_adx[['tr1', 'tr2', 'tr3']].max(axis=1)
    
    # NaN entfernen
    df_adx = df_adx.dropna()
    
    if len(df_adx) < max(dilen, adxlen) * 2:
        return 0.0
    
    # === RMA (Wilder's Smoothing) für TR ===
    alpha = 1.0 / dilen
    # Initialer Wert (SMA der ersten dilen Werte)
    tr_rma = df_adx['tr'].iloc[:dilen].mean()
    tr_rma_values = []
    
    # RMA für alle Werte berechnen
    for i in range(len(df_adx)):
        if i < dilen:
            # Ersten dilen Werte: nehme SMA
            tr_rma_values.append(df_adx['tr'].iloc[:i+1].mean())
        else:
            # RMA: alpha * current + (1 - alpha) * previous
            tr_rma = alpha * df_adx['tr'].iloc[i] + (1 - alpha) * tr_rma
            tr_rma_values.append(tr_rma)
    
    # === RMA für +DM ===
    plus_dm_rma = df_adx['plus_dm'].iloc[:dilen].mean()
    plus_dm_rma_values = []
    
    for i in range(len(df_adx)):
        if i < dilen:
            plus_dm_rma_values.append(df_adx['plus_dm'].iloc[:i+1].mean())
        else:
            plus_dm_rma = alpha * df_adx['plus_dm'].iloc[i] + (1 - alpha) * plus_dm_rma
            plus_dm_rma_values.append(plus_dm_rma)
    
    # === RMA für -DM ===
    minus_dm_rma = df_adx['minus_dm'].iloc[:dilen].mean()
    minus_dm_rma_values = []
    
    for i in range(len(df_adx)):
        if i < dilen:
            minus_dm_rma_values.append(df_adx['minus_dm'].iloc[:i+1].mean())
        else:
            minus_dm_rma = alpha * df_adx['minus_dm'].iloc[i] + (1 - alpha) * minus_dm_rma
            minus_dm_rma_values.append(minus_dm_rma)
    
    # +DI und -DI berechnen (in Prozent)
    plus_di_values = []
    minus_di_values = []
    
    for i in range(len(tr_rma_values)):
        if tr_rma_values[i] > 0:
            # +DI in Prozent
            plus_di = 100 * plus_dm_rma_values[i] / tr_rma_values[i]
            # -DI in Prozent
            minus_di = 100 * minus_dm_rma_values[i] / tr_rma_values[i]
        else:
            plus_di = 0
            minus_di = 0
        
        plus_di_values.append(plus_di)
        minus_di_values.append(minus_di)
    
    # DX berechnen
    dx_values = []
    for i in range(len(plus_di_values)):
        # Summe der DIs
        di_sum = plus_di_values[i] + minus_di_values[i]
        if di_sum > 0:
            # DX = 100 * |+DI - -DI| / (+DI + -DI)
            dx = 100 * abs(plus_di_values[i] - minus_di_values[i]) / di_sum
        else:
            dx = 0
        dx_values.append(dx)
    
    # === RMA für ADX (mit adxlen) ===
    if len(dx_values) < adxlen:
        return 0.0
    
    # Alpha für ADX Glättung
    alpha_adx = 1.0 / adxlen
    # Initialer ADX (SMA der ersten adxlen DX Werte)
    adx = sum(dx_values[:adxlen]) / adxlen
    
    # RMA für restliche DX Werte
    for i in range(adxlen, len(dx_values)):
        # RMA: alpha * current + (1 - alpha) * previous
        adx = alpha_adx * dx_values[i] + (1 - alpha_adx) * adx
    
    return round(float(adx), 2)


def calculate_ema_distance(df: pd.DataFrame, fast: int = 21, slow: int = 50) -> float:
    """
    Berechnet prozentualen Abstand zwischen EMAs
    
    Args:
        df: DataFrame mit EMAs
        fast: Schnelle EMA
        slow: Langsame EMA
    
    Returns:
        Abstand in Prozent
    """
    # EMA Spalten Namen
    ema_fast_col = f'ema_{fast}'
    ema_slow_col = f'ema_{slow}'
    
    # Prüfe ob Spalten existieren
    if ema_fast_col not in df.columns or ema_slow_col not in df.columns:
        logging.error(f"EMA Spalten fehlen: {ema_fast_col}, {ema_slow_col}")
        return 0.0
    
    # Letzte Werte
    ema_fast_val = df[ema_fast_col].iloc[-1]
    ema_slow_val = df[ema_slow_col].iloc[-1]
    # Aktueller Preis
    current_price = df['close'].iloc[-1]
    
    # Prüfe auf gültige Werte
    if pd.isna(ema_fast_val) or pd.isna(ema_slow_val) or current_price <= 0:
        return 0.0
    
    # Prozentualer Abstand zum aktuellen Preis
    distance = abs(ema_fast_val - ema_slow_val) / current_price * 100
    
    return round(float(distance), 3)


def check_trend_strength(df: pd.DataFrame, 
                        adx_threshold: float = 25.0,
                        ema_distance_threshold: float = 0.5) -> dict:
    """
    Prüft ob Trend stark genug für Trading
    
    Args:
        df: DataFrame mit Preisdaten und EMAs
        adx_threshold: Minimaler ADX Wert
        ema_distance_threshold: Minimaler EMA Abstand in %
    
    Returns:
        Dict mit is_trending, adx, ema_distance, reason
    """
    # ADX berechnen (beide Perioden auf 14)
    adx = calculate_adx(df, dilen=14, adxlen=14)
    # EMA Abstand berechnen
    ema_dist = calculate_ema_distance(df, fast=EMA_FAST, slow=EMA_SLOW)
    
    # Beide Bedingungen müssen erfüllt sein
    adx_ok = adx >= adx_threshold
    ema_ok = ema_dist >= ema_distance_threshold
    is_trending = adx_ok and ema_ok
    
    # Grund bei fehlendem Trend
    reason = ""
    if not is_trending:
        if not adx_ok:
            reason = f"ADX zu niedrig ({adx} < {adx_threshold})"
        if not ema_ok:
            if reason:
                reason += " | "
            reason += f"EMA-Abstand zu klein ({ema_dist}% < {ema_distance_threshold}%)"
    
    return {
        "is_trending": is_trending,
        "adx": adx,
        "ema_distance": ema_dist,
        "reason": reason if reason else "Trend OK"
    }


# ==================================================
# === EMA BERECHNUNGEN =============================
# ==================================================
def calculate_ema_series(data: pd.Series, period: int) -> pd.Series:
    """
    Berechnet Standard-EMA wie TradingView/Bitunix
    """
    # EMA mit Pandas
    ema = data.ewm(span=period, adjust=False).mean()
    return ema


def add_emas(df: pd.DataFrame, periods: list = [21, 50, 200]) -> pd.DataFrame:
    """
    Fügt EMA-Spalten zum DataFrame hinzu
    """
    # Prüfe ob Close Spalte existiert
    if 'close' not in df.columns:
        raise ValueError("DataFrame muss 'close' Spalte enthalten")
    
    # Berechne jede EMA
    for period in periods:
        column_name = f'ema_{period}'
        df[column_name] = calculate_ema_series(df['close'], period)
    
    return df


# ==================================================
# === EMA HIERARCHIE PRÜFEN ========================
# ==================================================
def check_ema_hierarchy(df: pd.DataFrame) -> dict:
    """
    Prüft EMA-Hierarchie für Trendrichtung
    
    Long: EMA21 > EMA50 > EMA200
    Short: EMA21 < EMA50 < EMA200
    
    Args:
        df: DataFrame mit EMAs
    
    Returns:
        Dict mit long_ok, short_ok, reason
    """
    # Letzte EMA Werte
    ema21 = df[f'ema_{EMA_FAST}'].iloc[-1]
    ema50 = df[f'ema_{EMA_SLOW}'].iloc[-1]
    ema200 = df[f'ema_{EMA_TREND}'].iloc[-1]
    
    # Prüfe auf gültige Werte
    if pd.isna(ema21) or pd.isna(ema50) or pd.isna(ema200):
        return {
            "long_ok": False,
            "short_ok": False,
            "reason": "EMAs nicht berechnet"
        }
    
    # Long: 21 > 50 > 200
    long_ok = ema21 > ema50 and ema50 > ema200
    
    # Short: 21 < 50 < 200
    short_ok = ema21 < ema50 and ema50 < ema200
    
    # Reason erstellen
    reason = ""
    if long_ok:
        reason = "Long OK (21>50>200)"
    elif short_ok:
        reason = "Short OK (21<50<200)"
    else:
        reason = "Keine klare Hierarchie"
    
    if DEBUG:
        logging.info(f"EMA Hierarchie: 21={ema21:.5f}, 50={ema50:.5f}, 200={ema200:.5f}")
        logging.info(f"Hierarchie Check: {reason}")
    
    return {
        "long_ok": long_ok,
        "short_ok": short_ok,
        "reason": reason,
        "ema21": ema21,
        "ema50": ema50,
        "ema200": ema200
    }


# ==================================================
# === EMA21 TOUCH PRÜFEN ===========================
# ==================================================
def check_ema21_touch(df: pd.DataFrame, threshold_pct: float = 0.05) -> dict:
    """
    Prüft ob Preis nahe an EMA21 ist (Touch)
    
    Args:
        df: DataFrame mit Preisen und EMAs
        threshold_pct: Max Abstand in % (0.05 = 0.05%)
    
    Returns:
        Dict mit is_touch, distance_pct, side
    """
    # Aktueller Preis
    current_price = df['close'].iloc[-1]
    # EMA21 Wert
    ema21 = df[f'ema_{EMA_FAST}'].iloc[-1]
    
    # Prüfe auf gültige Werte
    if pd.isna(current_price) or pd.isna(ema21) or ema21 <= 0:
        return {
            "is_touch": False,
            "distance_pct": 999.0,
            "side": None
        }
    
    # Abstand in Prozent
    distance_pct = abs((current_price - ema21) / ema21 * 100)
    
    # Touch wenn innerhalb threshold
    is_touch = distance_pct <= threshold_pct
    
    # Seite bestimmen (von welcher Seite nähert sich Preis?)
    if current_price >= ema21:
        side = "from_above"  # Preis kommt von oben
    else:
        side = "from_below"  # Preis kommt von unten
    
    if DEBUG:
        logging.info(f"EMA21 Touch Check: Preis={current_price:.5f}, EMA21={ema21:.5f}, Abstand={distance_pct:.3f}%, Touch={is_touch}")
    
    return {
        "is_touch": is_touch,
        "distance_pct": distance_pct,
        "side": side
    }


# ==================================================
# === TRADE SIGNAL GENERIEREN ======================
# ==================================================
def generate_trade_signal(df: pd.DataFrame) -> dict:
    """
    Generiert Trade Signal basierend auf allen Bedingungen
    
    Returns:
        Dict mit signal ("LONG", "SHORT", None), reason, tp, sl
    """
    # 1. Trendfilter prüfen
    if USE_TREND_FILTER:
        trend_check = check_trend_strength(
            df,
            adx_threshold=ADX_THRESHOLD,
            ema_distance_threshold=EMA_DISTANCE_THRESHOLD
        )
        
        if not trend_check["is_trending"]:
            return {
                "signal": None,
                "reason": f"Kein Trend: {trend_check['reason']}",
                "tp": None,
                "sl": None
            }
    
    # 2. EMA Hierarchie prüfen
    hierarchy = check_ema_hierarchy(df)
    
    # 3. EMA21 Touch prüfen
    touch = check_ema21_touch(df, threshold_pct=TOUCH_THRESHOLD_PCT)

    if touch["is_touch"]:
        logging.info("=" * 60)
        logging.info("👆 EMA21 TOUCH ERKANNT!")
        logging.info("=" * 60)
        logging.info(f"Touch Side:     {touch['side']}")
        logging.info(f"Distanz:        {touch['distance_pct']:.3f}%")
        logging.info(f"Long möglich:   {'✅ JA' if hierarchy['long_ok'] else '❌ NEIN'}")
        logging.info(f"Short möglich:  {'✅ JA' if hierarchy['short_ok'] else '❌ NEIN'}")
        logging.info(f"EMA21:          {hierarchy['ema21']:.5f}")
        logging.info(f"EMA50:          {hierarchy['ema50']:.5f}")
        logging.info(f"EMA200:         {hierarchy['ema200']:.5f}")
        logging.info(f"Hierarchie:     {hierarchy['reason']}")
        
        # Prüfe ob Signal kommt
        will_trade = False
        if hierarchy["long_ok"] and touch["side"] == "from_above":
            will_trade = True
            logging.info("➡️ LONG Signal wird generiert!")
        elif hierarchy["short_ok"] and touch["side"] == "from_below":
            will_trade = True
            logging.info("➡️ SHORT Signal wird generiert!")
        else:
            logging.info("❌ KEIN Signal - Bedingungen:")
            if not hierarchy["long_ok"] and not hierarchy["short_ok"]:
                logging.info("   • EMA Hierarchie nicht erfüllt")
            if hierarchy["long_ok"] and touch["side"] != "from_above":
                logging.info(f"   • Long Setup, aber Touch {touch['side']} (braucht from_above)")
            if hierarchy["short_ok"] and touch["side"] != "from_below":
                logging.info(f"   • Short Setup, aber Touch {touch['side']} (braucht from_below)")
        
        logging.info("=" * 60)
    
    # Aktueller Preis
    current_price = df['close'].iloc[-1]
    # EMA50 für Stop Loss
    ema50 = df[f'ema_{EMA_SLOW}'].iloc[-1]
    
    # TP/SL auf Margin-Basis berechnen (Hebel UND Gebühren berücksichtigen)
    # Gebühren in Prozent auf Positionsgröße
    fee_impact = TOTAL_FEES  # 0.00084 = 0.084%
    
    # TP: Gewünschter Gewinn auf Margin + Gebühren
    # z.B. 1% auf Margin = 1% / Hebel Preisänderung + Gebühren
    tp_price_pct = (TP_PCT / LEVERAGE) + fee_impact
    
    # SL: Gewünschter Verlust auf Margin + Gebühren
    # z.B. 0.5% auf Margin = 0.5% / Hebel Preisänderung + Gebühren
    sl_price_pct = (SL_PCT / LEVERAGE) + fee_impact
    
    # === LONG SIGNAL ===
    if hierarchy["long_ok"] and touch["is_touch"] and touch["side"] == "from_above":
        # TP: Preisänderung inkl. Gebühren
        tp_price = current_price * (1 + tp_price_pct)
        
        # SL: Preisänderung inkl. Gebühren
        sl_calculated = current_price * (1 - sl_price_pct)
        # Nutze EMA50 wenn es einen besseren (höheren) SL ergibt
        sl_price = max(ema50, sl_calculated)
        
        return {
            "signal": "LONG",
            "reason": "EMA Hierarchie OK + Touch EMA21 von oben",
            "tp": tp_price,
            "sl": sl_price,
            "entry_price": current_price
        }
    
    # === SHORT SIGNAL ===
    elif hierarchy["short_ok"] and touch["is_touch"] and touch["side"] == "from_below":
        # TP: Preisänderung inkl. Gebühren
        tp_price = current_price * (1 - tp_price_pct)
        
        # SL: Preisänderung inkl. Gebühren
        sl_calculated = current_price * (1 + sl_price_pct)
        # Nutze EMA50 wenn es einen besseren (niedrigeren) SL ergibt
        sl_price = min(ema50, sl_calculated)
        
        return {
            "signal": "SHORT",
            "reason": "EMA Hierarchie OK + Touch EMA21 von unten",
            "tp": tp_price,
            "sl": sl_price,
            "entry_price": current_price
        }
    
    # === KEIN SIGNAL ===
    else:
        reasons = []
        if not hierarchy["long_ok"] and not hierarchy["short_ok"]:
            reasons.append("Keine EMA Hierarchie")
        if not touch["is_touch"]:
            reasons.append(f"Kein EMA21 Touch (Abstand: {touch['distance_pct']:.3f}%)")
        
        return {
            "signal": None,
            "reason": " | ".join(reasons) if reasons else "Keine Bedingung erfüllt",
            "tp": None,
            "sl": None
        }

# ==================================================
# === KERZENDATEN LADEN ============================
# ==================================================
def fetch_historical_klines(client: OpenApiHttpFuturePublic, 
                           symbol: str, 
                           interval: str, 
                           limit: int = 200) -> pd.DataFrame:
    """
    Lädt historische Kerzendaten von Bitunix
    """
    try:
        # Zeitfenster berechnen
        interval_minutes = {
            "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
            "1h": 60, "2h": 120, "4h": 240, "1d": 1440
        }
        
        # Minuten pro Kerze
        minutes = interval_minutes.get(interval, 5)
        
        # Start- und Endzeit in Millisekunden
        current_time = int(time.time() * 1000)
        # Zeit zurückrechnen
        time_back_ms = minutes * limit * 60 * 1000
        start_time = current_time - time_back_ms
        
        # Kerzendaten abrufen
        response = client.get_kline(
            symbol=symbol,
            interval=interval,
            limit=limit,
            start_time=start_time,
            end_time=current_time,
            type="LAST_PRICE"
        )
        
        # Prüfe Response
        if not response or len(response) == 0:
            raise ValueError("Keine Kerzendaten erhalten")
        
        # DataFrame erstellen
        df = pd.DataFrame(response)
        
        # Timestamp-Feld finden und konvertieren
        time_field = 'time' if 'time' in df.columns else 'timestamp'
        # Konvertiere zu numerisch
        df[time_field] = pd.to_numeric(df[time_field], errors='coerce')
        # Konvertiere zu Datetime
        df['timestamp'] = pd.to_datetime(df[time_field], unit='ms')
        
        # Zeitzone anpassen (UTC -> UTC+2)
        df['timestamp'] = df['timestamp'] + timedelta(hours=TIMEZONE_OFFSET)
        
        # Spalten umbenennen
        df.rename(columns={'quoteVol': 'volume', 'baseVol': 'turnover'}, inplace=True)
        
        # Datentypen konvertieren
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Index setzen und sortieren
        df.set_index('timestamp', inplace=True)
        # Sortiere chronologisch
        df.sort_index(inplace=True)
        # Entferne ungültige Timestamps
        df = df[df.index.notna()]
        
        # Prüfe ob Daten vorhanden
        if len(df) == 0:
            raise ValueError("Keine gültigen Timestamps!")
        
        if DEBUG:
            logging.info(f"✅ {len(df)} Kerzen geladen: {df.index[0].strftime('%H:%M')} - {df.index[-1].strftime('%H:%M')}")
        
        return df
        
    except Exception as e:
        logging.error(f"❌ Fehler beim Laden der Kerzendaten: {e}")
        raise


# ==================================================
# === KONTOINFORMATIONEN ============================
# ==================================================
async def fetch_account_info(client: OpenApiHttpFuturePrivate) -> float:
    """
    Liest verfügbares Guthaben
    """
    try:
        # Account Daten abrufen
        account = client.get_account(margin_coin="USDT")
        # Verfügbarer Betrag
        balance = float(account.get("available", 0.0))
        if DEBUG:
            logging.info(f"💰 Guthaben: {balance:.2f} USDT")
        return balance
    except Exception as e:
        logging.error(f"❌ Fehler beim Account-Abruf: {e}")
        return 0.0


# ==================================================
# === TRADE PARAMETER BERECHNUNG ===================
# ==================================================
def calc_trade_parameters(client_pub, symbol: str, balance: float, current_price: float, 
                         leverage: int, tp_pct: float, sl_pct: float, total_fees: float):
    """
    Berechnet Trade-Parameter (qty in Coins, TP, SL) mit automatischer Precision
    
    TP: 1% Gewinn NACH Abzug der Gebühren
    SL: 0.5% Verlust INKLUSIVE Gebühren
    
    Args:
        client_pub: Public API Client für Symbol Info
        symbol: Trading Symbol
        balance: Verfügbares Guthaben
        current_price: Aktueller Preis
        leverage: Hebel
        tp_pct: Take Profit Prozent
        sl_pct: Stop Loss Prozent
        total_fees: Gesamte Gebühren
    
    Returns:
        qty_coins, tp_price, sl_price
    """
    # Prüfe Preis
    if current_price <= 0:
        raise ValueError("current_price must be > 0")

    # Symbol Info abrufen (für Precision)
    symbol_info = get_symbol_info(client_pub, symbol)
    base_precision = symbol_info['base_precision']
    min_trade_volume = symbol_info['min_trade_volume']

    # Kaufkraft berechnen
    buying_power = balance * leverage
    
    # Positionsgröße in Coins (ungerundet)
    qty_coins_raw = buying_power / current_price
    
    # Mit korrekter Precision runden
    qty_coins = round(qty_coins_raw, base_precision)
    
    # Mindestmenge prüfen
    if qty_coins < min_trade_volume:
        logging.warning(f"⚠️ Berechnete Menge {qty_coins} < minTradeVolume {min_trade_volume}")
        qty_coins = min_trade_volume
        logging.info(f"📊 Menge auf Minimum angepasst: {qty_coins}")
    
    # Tatsächliche Positionsgröße in USDT
    position_size_usdt = qty_coins * current_price
    
    # Tatsächlich verwendete Margin
    margin_to_use = position_size_usdt / leverage

    # Gebühren auf Positionswert (Entry + Exit)
    fee_usdt = position_size_usdt * total_fees
    
    # TP: Zielgewinn + Gebühren (damit nach Gebühren 1% übrig bleibt)
    target_usdt = balance * tp_pct
    # Brutto-Gewinn inkl. Gebühren
    tp_gross = target_usdt + fee_usdt
    
    # SL: Verlust bereits inklusive Gebühren
    risk_usdt = balance * sl_pct

    # Preisdifferenzen für TP/SL
    delta_tp = tp_gross / qty_coins
    delta_sl = risk_usdt / qty_coins
    
    # TP und SL Preise
    tp_price = current_price + delta_tp
    sl_price = current_price - delta_sl

    if DEBUG:
        logging.info("=" * 60)
        logging.info(f"📊 Trade-Berechnung:")
        logging.info("=" * 60)
        logging.info(f"Guthaben:       {balance:.2f} USDT")
        logging.info(f"Hebel:          {leverage}x")
        logging.info(f"Kaufkraft:      {buying_power:.2f} USDT")
        logging.info(f"Preis:          {current_price:.5f} USDT")
        logging.info(f"Precision:      {base_precision} Nachkommastellen")
        logging.info(f"Min Volume:     {min_trade_volume}")
        logging.info(f"Menge:          {qty_coins} Coins")
        logging.info(f"Position:       {position_size_usdt:.2f} USDT")
        logging.info(f"Margin:         {margin_to_use:.2f} USDT")
        logging.info(f"Gebühren:       {fee_usdt:.2f} USDT")
        logging.info(f"TP:             {tp_price:.5f} (Netto-Gewinn: +{target_usdt:.2f} USDT)")
        logging.info(f"SL:             {sl_price:.5f} (Gesamt-Verlust: -{risk_usdt:.2f} USDT)")

    return qty_coins, tp_price, sl_price


# ==================================================
# === DRY RUN ORDER ================================
# ==================================================
def place_order_dryrun(signal: dict, qty: float, balance: float):
    """
    Simuliert Order-Platzierung (DRY RUN)
    
    Args:
        signal: Trade Signal Dict
        qty: Order Menge in Coins
        balance: Verfügbares Guthaben
    """
    if not signal or signal["signal"] is None:
        if DEBUG:
            logging.info("❌ Kein Trade Signal")
        return
    
    # Order Details
    side = signal["signal"]  # "LONG" oder "SHORT"
    entry = signal["entry_price"]
    tp = signal["tp"]
    sl = signal["sl"]
    
    # Position Size
    position_size = qty * entry
    # Margin benötigt (= Kontogröße für diese Position)
    margin_used = position_size / LEVERAGE
    
    # Ausgabe nur in Console UND Log
    print("\n" + "=" * 60)
    print("🎯 DRY RUN - ORDER SIMULATION")
    print("=" * 60)
    print(f"Signal:         {side}")
    print(f"Grund:          {signal['reason']}")
    print(f"Entry Preis:    {entry:.5f} USDT")
    print(f"Menge:          {qty} Coins")
    print(f"Position Größe: {position_size:.2f} USDT")
    print(f"Hebel:          {LEVERAGE}x")
    print(f"Margin:         {margin_used:.2f} USDT")
    print(f"Take Profit:    {tp:.5f} USDT")
    print(f"Stop Loss:      {sl:.5f} USDT")
    
    # Berechne Gewinn/Verlust auf MARGIN-Basis (nicht Position)
    if side == "LONG":
        # Preisdifferenz zu TP/SL
        tp_diff = tp - entry
        sl_diff = entry - sl
        
        # Gewinn/Verlust in USDT (auf gesamte Menge)
        profit_usdt = tp_diff * qty
        loss_usdt = sl_diff * qty
        
        # Prozent bezogen auf MARGIN
        profit_pct = (profit_usdt / margin_used) * 100
        loss_pct = (loss_usdt / margin_used) * 100
        
    else:  # SHORT
        # Preisdifferenz zu TP/SL
        tp_diff = entry - tp
        sl_diff = sl - entry
        
        # Gewinn/Verlust in USDT (auf gesamte Menge)
        profit_usdt = tp_diff * qty
        loss_usdt = sl_diff * qty
        
        # Prozent bezogen auf MARGIN
        profit_pct = (profit_usdt / margin_used) * 100
        loss_pct = (loss_usdt / margin_used) * 100
    
    print(f"Potentieller Gewinn: +{profit_usdt:.2f} USDT ({profit_pct:.2f}% auf Margin)")
    print(f"Potentieller Verlust: -{loss_usdt:.2f} USDT ({loss_pct:.2f}% auf Margin)")
    print(f"Risk/Reward Ratio: 1:{(profit_usdt/loss_usdt):.2f}")
    print("=" * 60)
    print("⚠️ DRY RUN MODE - Keine echte Order platziert!")
    print("=" * 60 + "\n")
    
    # Auch ins Log schreiben    
    logging.info("=" * 60)
    logging.info("🎯 DRY RUN - ORDER SIMULATION")
    logging.info("=" * 60)
    logging.info(f"Signal:         {side}")
    logging.info(f"Grund:          {signal['reason']}")
    logging.info(f"Entry Preis:    {entry:.5f} USDT")
    logging.info(f"Menge:          {qty} Coins")
    logging.info(f"Position Größe: {position_size:.2f} USDT")
    logging.info(f"Hebel:          {LEVERAGE}x")
    logging.info(f"Margin:         {margin_used:.2f} USDT")
    logging.info(f"Take Profit:    {tp:.5f} USDT")
    logging.info(f"Stop Loss:      {sl:.5f} USDT")
    logging.info(f"Potentieller Gewinn: +{profit_usdt:.2f} USDT ({profit_pct:.2f}% auf Margin)")
    logging.info(f"Potentieller Verlust: -{loss_usdt:.2f} USDT ({loss_pct:.2f}% auf Margin)")
    logging.info(f"Risk/Reward Ratio: 1:{(profit_usdt/loss_usdt):.2f}")
    logging.info("=" * 60)
    logging.info("⚠️ DRY RUN MODE - Keine echte Order platziert!")
    logging.info("=" * 60)

# ==================================================
# === BOT LOOP =====================================
# ==================================================
async def bot_loop(client_pri, client_pub):
    """
    Hauptschleife - läuft kontinuierlich
    """
    logging.info("=" * 60)
    logging.info("🤖 Bot gestartet - Endlos-Modus")
    logging.info(f"Symbol: {SYMBOL} | Interval: {INTERVAL} | Leverage: {LEVERAGE}x")
    logging.info(f"DRY RUN: {'✅ AN' if DRY_RUN else '❌ AUS (LIVE MODE!)'}")
    logging.info(f"DEBUG: {'✅ AN' if DEBUG else '❌ AUS'}")
    logging.info("=" * 60)
    
    active_position = False
    
    try:
        while True:
            try:
                if DEBUG:
                    logging.info("\n" + "=" * 60)
                    logging.info(f"🔄 Iteration: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    logging.info("=" * 60)
                
                # Position Check
                try:
                    if DRY_RUN:
                        active_position = False
                    else:
                        positions = client_pri.get_positions(symbol=SYMBOL, margin_coin="USDT")
                        
                        if positions and len(positions) > 0:
                            has_position = any(
                                float(pos.get('qty', 0)) > 0 
                                for pos in positions
                            )
                            
                            if has_position:
                                if not active_position:
                                    logging.info("🔒 Aktive Position erkannt!")
                                    print("🔒 Aktive Position erkannt - warte auf Schließung...")
                                    active_position = True
                                else:
                                    if DEBUG:
                                        logging.info("⏳ Position noch aktiv - warte...")
                                
                                await asyncio.sleep(10)
                                continue
                            else:
                                if active_position:
                                    logging.info("✅ Position geschlossen!")
                                    print("✅ Position geschlossen - suche neue Signale...")
                                active_position = False
                        else:
                            active_position = False
                            
                except Exception as e:
                    logging.error(f"❌ Fehler beim Position-Check: {e}")
                    if DRY_RUN:
                        active_position = False
                    else:
                        await asyncio.sleep(30)
                        continue
                
                if DEBUG:
                    logging.info("🔍 Keine aktive Position - suche Signal...")
                
                # Daten laden
                BACKTEST_BARS = 200
                df = fetch_historical_klines(client_pub, SYMBOL, INTERVAL, BACKTEST_BARS)
                
                ticker_data = client_pub.get_tickers(SYMBOL)
                if isinstance(ticker_data, list) and ticker_data:
                    current_price = float(ticker_data[0].get("last", 0.0))
                elif isinstance(ticker_data, dict):
                    current_price = float(ticker_data.get("last", 0.0))
                else:
                    raise ValueError("Keine Preisdaten erhalten")
                
                last_timestamp = df.index[-1]
                
                if INTERVAL == "1m":
                    delta = timedelta(minutes=1)
                elif INTERVAL == "3m":
                    delta = timedelta(minutes=3)
                elif INTERVAL == "5m":
                    delta = timedelta(minutes=5)
                elif INTERVAL == "15m":
                    delta = timedelta(minutes=15)
                elif INTERVAL == "30m":
                    delta = timedelta(minutes=30)
                elif INTERVAL == "1h":
                    delta = timedelta(hours=1)
                elif INTERVAL == "2h":
                    delta = timedelta(hours=2)
                elif INTERVAL == "4h":
                    delta = timedelta(hours=4)
                elif INTERVAL == "1d":
                    delta = timedelta(days=1)
                else:
                    delta = timedelta(minutes=1)
                
                current_time = last_timestamp + delta
                new_row = pd.DataFrame({
                    'open': [df['close'].iloc[-1]],
                    'high': [max(df['close'].iloc[-1], current_price)],
                    'low': [min(df['close'].iloc[-1], current_price)],
                    'close': [current_price],
                    'volume': [0.0],
                    'turnover': [0.0]
                }, index=[current_time])
                
                df = pd.concat([df, new_row])
                df = add_emas(df, periods=[EMA_FAST, EMA_SLOW, EMA_TREND])
                
                balance = await fetch_account_info(client_pri)
                if balance <= 0:
                    logging.error("❌ Kein Guthaben!")
                    await asyncio.sleep(60)
                    continue
                
                # NEU: calc_trade_parameters mit client_pub aufrufen
                qty, tp_price, sl_price = calc_trade_parameters(
                    client_pub=client_pub,
                    symbol=SYMBOL,
                    balance=balance,
                    current_price=current_price,
                    leverage=LEVERAGE,
                    tp_pct=TP_PCT,
                    sl_pct=SL_PCT,
                    total_fees=TOTAL_FEES
                )
                
                signal = generate_trade_signal(df)
                
                if signal["signal"]:
                    # IMMER loggen bei Signal!
                    logging.info(f"✅ Signal gefunden: {signal['signal']}")
                    
                    if DRY_RUN:
                        place_order_dryrun(signal, qty, balance)
                    else:
                        logging.info("🚀 LIVE MODE - Platziere Order...")
                        print(f"🚀 LIVE MODE - Platziere {signal['signal']} Order...")
                        # place_order_live(client_pri, signal, qty)
                        pass
                    
                    await asyncio.sleep(60)
                else:
                    if DEBUG:
                        logging.info(f"⏸️ Kein Signal: {signal['reason']}")
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

# ==================================================
# === HAUPTPROGRAMM ================================
# ==================================================
async def main():

    # Clients einmal initialisieren
    cfg = Config()
    client_pri = OpenApiHttpFuturePrivate(cfg)
    client_pub = OpenApiHttpFuturePublic(cfg)

    # Initial Margin Mode und Leverage festlegen
    if not DRY_RUN:
        client_pri.change_leverage(symbol=SYMBOL, leverage=LEVERAGE, margin_coin="USDT")
        client_pri.change_margin_mode(symbol=SYMBOL, margin_mode="ISOLATION", margin_coin="USDT")

    """
    Startet Bot im Endlos-Modus
    """
    try:
        await bot_loop(client_pri, client_pub)
    except KeyboardInterrupt:
        pass  # Wird bereits in bot_loop() behandelt


if __name__ == "__main__":
    # Logging einrichten
    setup_logging()
    
    print("\n" + "=" * 60)
    print("🤖 EMA21 Touch Trading Bot")
    print("=" * 60)
    print(f"Symbol:       {SYMBOL}")
    print(f"Interval:     {INTERVAL}")
    print(f"Leverage:     {LEVERAGE}x")
    print(f"Mode:         {'DRY RUN ✅' if DRY_RUN else 'LIVE MODE ⚠️'}")
    print(f"ADX Filter:   {ADX_THRESHOLD}")
    print(f"EMA Distance: {EMA_DISTANCE_THRESHOLD}%")
    print("=" * 60)
    print("Bot startet... Drücke CTRL+C zum Beenden\n")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Sauberer Exit ohne Traceback
        print("\n" + "=" * 60)
        print("🛑 Bot gestoppt durch Benutzer")
        print("=" * 60)