import pandas as pd
import logging


def calculate_ema_series(data: pd.Series, period: int) -> pd.Series:
    """
    Berechnet Standard-EMA wie TradingView/Bitunix
    
    Args:
        data: Pandas Series mit Preisdaten
        period: EMA Periode
    
    Returns:
        EMA als Pandas Series
    """
    ema = data.ewm(span=period, adjust=False).mean()
    return ema


def add_emas(df: pd.DataFrame, periods: list = [21, 50, 200]) -> pd.DataFrame:
    """
    Fügt EMA-Spalten zum DataFrame hinzu
    
    Args:
        df: DataFrame mit Preisdaten
        periods: Liste der EMA-Perioden
    
    Returns:
        DataFrame mit EMA-Spalten (ema_21, ema_50, etc.)
    
    Raises:
        ValueError: Wenn 'close' Spalte fehlt
    """
    # Prüfe ob Close Spalte existiert
    if 'close' not in df.columns:
        raise ValueError("DataFrame muss 'close' Spalte enthalten")
    
    # Berechne jede EMA
    for period in periods:
        column_name = f'ema_{period}'
        df[column_name] = calculate_ema_series(df['close'], period)
    
    return df


def calculate_ema_distance(df: pd.DataFrame, fast: int = 21, slow: int = 50) -> float:
    """
    Berechnet prozentualen Abstand zwischen zwei EMAs
    
    Args:
        df: DataFrame mit EMA-Spalten
        fast: Schnelle EMA Periode
        slow: Langsame EMA Periode
    
    Returns:
        Abstand in Prozent (relativ zum aktuellen Preis)
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


def check_ema_hierarchy(df: pd.DataFrame, fast: int = 21, slow: int = 50, trend: int = 200, debug: bool = False) -> dict:
    """
    Prüft EMA-Hierarchie für Trendrichtung
    
    Long: EMA_fast > EMA_slow > EMA_trend
    Short: EMA_fast < EMA_slow < EMA_trend
    
    Args:
        df: DataFrame mit EMAs
        fast: Schnelle EMA Periode
        slow: Mittlere EMA Periode
        trend: Langsame EMA Periode (Trendfilter)
        debug: Debug-Modus
    
    Returns:
        Dict mit long_ok, short_ok, reason, ema-Werten
    """
    # Letzte EMA Werte
    ema_fast_val = df[f'ema_{fast}'].iloc[-1]
    ema_slow_val = df[f'ema_{slow}'].iloc[-1]
    ema_trend_val = df[f'ema_{trend}'].iloc[-1]
    
    # Prüfe auf gültige Werte
    if pd.isna(ema_fast_val) or pd.isna(ema_slow_val) or pd.isna(ema_trend_val):
        return {
            "long_ok": False,
            "short_ok": False,
            "reason": "EMAs nicht berechnet",
            f"ema{fast}": None,
            f"ema{slow}": None,
            f"ema{trend}": None
        }
    
    # Long: fast > slow > trend
    long_ok = ema_fast_val > ema_slow_val and ema_slow_val > ema_trend_val
    
    # Short: fast < slow < trend
    short_ok = ema_fast_val < ema_slow_val and ema_slow_val < ema_trend_val
    
    # Reason erstellen
    reason = ""
    if long_ok:
        reason = f"Long OK ({fast}>{slow}>{trend})"
    elif short_ok:
        reason = f"Short OK ({fast}<{slow}<{trend})"
    else:
        reason = "Keine klare Hierarchie"
    
    if debug:
        logging.info(f"EMA Hierarchie: {fast}={ema_fast_val:.5f}, {slow}={ema_slow_val:.5f}, {trend}={ema_trend_val:.5f}")
        logging.info(f"Hierarchie Check: {reason}")
    
    return {
        "long_ok": long_ok,
        "short_ok": short_ok,
        "reason": reason,
        f"ema{fast}": ema_fast_val,
        f"ema{slow}": ema_slow_val,
        f"ema{trend}": ema_trend_val
    }