import pandas as pd
import logging
from typing import Dict, Optional

# Absolute Imports
from indicators import check_ema_hierarchy, check_trend_strength


def check_ema21_touch(df: pd.DataFrame, 
                     ema_fast: int = 21,
                     threshold_pct: float = 0.05) -> dict:
    """
    Prüft ob Preis nahe an EMA21 ist (Touch)
    
    Args:
        df: DataFrame mit Preisen und EMAs
        ema_fast: Schnelle EMA Periode
        threshold_pct: Max Abstand in % (0.05 = 0.05%)
    
    Returns:
        Dict mit is_touch, distance_pct, side
    """
    # Aktueller Preis
    current_price = df['close'].iloc[-1]
    # EMA21 Wert
    ema_val = df[f'ema_{ema_fast}'].iloc[-1]
    
    # Prüfe auf gültige Werte
    if pd.isna(current_price) or pd.isna(ema_val) or ema_val <= 0:
        return {
            "is_touch": False,
            "distance_pct": 999.0,
            "side": None
        }
    
    # Abstand in Prozent
    distance_pct = abs((current_price - ema_val) / ema_val * 100)
    
    # Touch wenn innerhalb threshold
    is_touch = distance_pct <= threshold_pct
    
    # Seite bestimmen (von welcher Seite nähert sich Preis?)
    if current_price >= ema_val:
        side = "from_above"  # Preis über/von oben
    else:
        side = "from_below"  # Preis unter/von unten
    
    return {
        "is_touch": is_touch,
        "distance_pct": distance_pct,
        "side": side
    }


def generate_trade_signal(df: pd.DataFrame, config: dict) -> dict:
    """
    Generiert Trade Signal basierend auf allen Bedingungen
    
    Args:
        df: DataFrame mit Preisen und Indikatoren
        config: Config Dictionary mit allen Parametern
    
    Returns:
        Dict mit signal ("LONG", "SHORT", None), reason, tp, sl, entry_price
    """
    # Config Werte extrahieren
    use_filter = config['trend_filter']['use_filter']
    adx_threshold = config['trend_filter']['adx_threshold']
    ema_distance_threshold = config['trend_filter']['ema_distance_threshold']
    ema_fast = config['indicators']['ema_fast']
    ema_slow = config['indicators']['ema_slow']
    ema_trend = config['indicators']['ema_trend']
    touch_threshold = config['entry']['touch_threshold_pct']
    leverage = config['trading']['leverage']
    tp_pct = config['risk']['tp_pct']
    sl_pct = config['risk']['sl_pct']
    fee_pct = config['risk']['fee_pct']
    
    # Gesamte Gebühren
    total_fees = fee_pct * 2
    
    # Aktueller Preis für Logs
    current_price = df['close'].iloc[-1]
    
    # EMA Touch prüfen (ZUERST!)
    touch = check_ema21_touch(df, ema_fast=ema_fast, threshold_pct=touch_threshold)
    
    # Wenn KEIN Touch → direkt abbrechen (kein Log nötig)
    if not touch["is_touch"]:
        return {
            "signal": None,
            "reason": "Kein EMA Touch",
            "tp": None,
            "sl": None,
            "entry_price": None
        }
    
    # === AB HIER: Touch wurde erkannt! ===
    
    # EMA Hierarchie prüfen
    hierarchy = check_ema_hierarchy(df, fast=ema_fast, slow=ema_slow, trend=ema_trend, debug=False)
    
    # Trendfilter prüfen (wenn aktiviert)
    if use_filter:
        trend_check = check_trend_strength(
            df,
            adx_threshold=adx_threshold,
            ema_distance_threshold=ema_distance_threshold,
            ema_fast=ema_fast,
            ema_slow=ema_slow
        )
        
        # Trend zu schwach → Return (Logging passiert in bot.py)
        if not trend_check["is_trending"]:
            return {
                "signal": None,
                "reason": f"Trend zu schwach",
                "tp": None,
                "sl": None,
                "entry_price": None
            }
    
    # === Hierarchie OK? ===
    
    # Long möglich?
    if hierarchy["long_ok"] and touch["side"] == "from_above":
        # LONG SIGNAL!
        ema_slow_val = df[f'ema_{ema_slow}'].iloc[-1]
        
        fee_impact = total_fees
        tp_price_pct = (tp_pct / leverage) + fee_impact
        sl_price_pct = (sl_pct / leverage) + fee_impact
        
        tp_price = current_price * (1 + tp_price_pct)
        sl_calculated = current_price * (1 - sl_price_pct)
        sl_price = max(ema_slow_val, sl_calculated)
        
        return {
            "signal": "LONG",
            "reason": f"EMA Hierarchie OK + Touch EMA{ema_fast} von oben",
            "tp": tp_price,
            "sl": sl_price,
            "entry_price": current_price
        }
    
    # Short möglich?
    elif hierarchy["short_ok"] and touch["side"] == "from_below":
        # SHORT SIGNAL!
        ema_slow_val = df[f'ema_{ema_slow}'].iloc[-1]
        
        fee_impact = total_fees
        tp_price_pct = (tp_pct / leverage) + fee_impact
        sl_price_pct = (sl_pct / leverage) + fee_impact
        
        tp_price = current_price * (1 - tp_price_pct)
        sl_calculated = current_price * (1 + sl_price_pct)
        sl_price = min(ema_slow_val, sl_calculated)
        
        return {
            "signal": "SHORT",
            "reason": f"EMA Hierarchie OK + Touch EMA{ema_fast} von unten",
            "tp": tp_price,
            "sl": sl_price,
            "entry_price": current_price
        }
    
    # === Touch erkannt, aber falsche Richtung für Setup ===
    else:
        # Warum kein Trade?
        if hierarchy["long_ok"] and touch["side"] == "from_below":
            reason = "Long-Setup, aber Touch von unten"
        elif hierarchy["short_ok"] and touch["side"] == "from_above":
            reason = "Short-Setup, aber Touch von oben"
        else:
            reason = "Keine EMA-Hierarchie"
        
        return {
            "signal": None,
            "reason": reason,
            "tp": None,
            "sl": None,
            "entry_price": None
        }