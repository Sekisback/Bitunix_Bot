import pandas as pd
import time
import logging
from datetime import timedelta
from typing import Optional


def fetch_historical_klines(client_pub, 
                           symbol: str, 
                           interval: str, 
                           limit: int = 200,
                           timezone_offset: int = 2) -> pd.DataFrame:
    """
    Lädt historische Kerzendaten von Bitunix
    
    Args:
        client_pub: OpenApiHttpFuturePublic Client
        symbol: Trading Symbol (z.B. "ONDOUSDT")
        interval: Timeframe (z.B. "1m", "5m", "1h")
        limit: Anzahl Kerzen
        timezone_offset: Zeitzone Offset (2 = UTC+2)
    
    Returns:
        DataFrame mit OHLCV Daten
    
    Raises:
        ValueError: Wenn keine Daten geladen werden konnten
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
        response = client_pub.get_kline(
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
        
        # Zeitzone anpassen
        df['timestamp'] = df['timestamp'] + timedelta(hours=timezone_offset)
        
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
        
        logging.debug(f"{len(df)} Kerzen geladen: {df.index[0].strftime('%H:%M')} - {df.index[-1].strftime('%H:%M')}")
        
        return df
        
    except Exception as e:
        logging.error(f"❌ Fehler beim Laden der Kerzendaten: {e}")
        raise