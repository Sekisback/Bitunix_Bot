import pandas as pd
import numpy as np
import logging


def calculate_adx(df: pd.DataFrame, dilen: int = 14, adxlen: int = 14) -> float:
    """
    Berechnet ADX exakt wie TradingView (mit RMA = Wilder's Smoothing)
    
    Args:
        df: DataFrame mit high, low, close Spalten
        dilen: DI Length (Standard 14)
        adxlen: ADX Smoothing (Standard 14)
    
    Returns:
        ADX Wert (0.0 wenn nicht genug Daten)
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