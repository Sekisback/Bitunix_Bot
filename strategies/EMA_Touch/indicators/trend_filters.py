import pandas as pd
import logging
from .adx import calculate_adx
from .ema import calculate_ema_distance


def check_trend_strength(df: pd.DataFrame, 
                        adx_threshold: float = 25.0,
                        ema_distance_threshold: float = 0.5,
                        ema_fast: int = 21,
                        ema_slow: int = 50) -> dict:
    """
    Prüft ob Trend stark genug für Trading
    
    Args:
        df: DataFrame mit Preisdaten und EMAs
        adx_threshold: Minimaler ADX Wert
        ema_distance_threshold: Minimaler EMA Abstand in %
        ema_fast: Schnelle EMA Periode
        ema_slow: Langsame EMA Periode
    
    Returns:
        Dict mit is_trending, adx, ema_distance, reason
    """
    # ADX berechnen (beide Perioden auf 14)
    adx = calculate_adx(df, dilen=14, adxlen=14)
    
    # EMA Abstand berechnen
    ema_dist = calculate_ema_distance(df, fast=ema_fast, slow=ema_slow)
    
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
    else:
        reason = "Trend OK"
    
    return {
        "is_trending": is_trending,
        "adx": adx,
        "ema_distance": ema_dist,
        "reason": reason
    }