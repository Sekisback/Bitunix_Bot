import asyncio
import logging
import pandas as pd
from datetime import timedelta
from typing import Callable, Optional, Dict, Any
from collections import deque

# Imports (angepasst an deine Struktur)
from core.open_api_ws_future_public import OpenApiWsFuturePublic
from core.config import Config


class WebSocketKlineManager:
    """
    Kline-Manager für Bitunix WebSocket API
    Buffert Kerzen und triggert Callback bei neuen Daten
    """
    
    # Interval-Mapping: Bot-Format → Bitunix-Format
    INTERVAL_MAP = {
        "1m": "1min",
        "3m": "3min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "60min",
        "2h": "2h",
        "4h": "4h",
        "6h": "6h",
        "8h": "8h",
        "12h": "12h",
        "1d": "1day",
        "3d": "3day",
        "1w": "1week",
        "1M": "1month"
    }
    
    def __init__(self, 
                 symbol: str,
                 interval: str,
                 buffer_size: int = 200,
                 timezone_offset: int = 2,
                 price_type: str = "market",
                 on_kline_callback: Optional[Callable] = None):
        """
        Args:
            symbol: Trading Symbol (z.B. "ONDOUSDT")
            interval: Bot Interval (z.B. "1m", "5m", "1h")
            buffer_size: Anzahl zu speichernder Kerzen
            timezone_offset: Timezone Offset in Stunden
            price_type: "market" für Last Price, "mark" für Mark Price
            on_kline_callback: Callback bei neuer Kerze
        """
        self.symbol = symbol
        self.interval = interval
        self.buffer_size = buffer_size
        self.timezone_offset = timezone_offset
        self.price_type = price_type
        self.on_kline_callback = on_kline_callback
        
        # Kerzen-Buffer
        self.kline_buffer = deque(maxlen=buffer_size)
        
        # WebSocket Client
        self.config = Config()
        self.ws_client = OpenApiWsFuturePublic(self.config)
        
        # Bitunix-Channel-Namen bilden
        bitunix_interval = self.INTERVAL_MAP.get(interval, "1min")
        self.channel_name = f"{price_type}_kline_{bitunix_interval}"
        
        # Stats
        self.klines_received = 0
        self.last_kline_time = None
        
        logging.info(f"📊 Kline-Manager initialisiert:")
        logging.info(f"   Interval:    {interval} → {bitunix_interval}")
        logging.info(f"   Channel:     {self.channel_name}")
        
    def get_dataframe(self) -> pd.DataFrame:
        """
        Gibt gepufferte Kerzen als DataFrame zurück
        
        Returns:
            DataFrame mit OHLCV Daten + Timestamp als Index
        """
        if not self.kline_buffer:
            return pd.DataFrame()
        
        df = pd.DataFrame(list(self.kline_buffer))
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        
        return df
    
    def _parse_kline(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parsed Kline-Daten aus Bitunix WebSocket
        
        Args:
            message: Komplette WebSocket-Message
            
        Returns:
            Dict mit OHLCV-Daten
        """
        # Timestamp ist auf Root-Level
        timestamp_ms = int(message['ts'])
        dt = pd.to_datetime(timestamp_ms, unit='ms')
        dt = dt + timedelta(hours=self.timezone_offset)
        
        # Data-Object mit Kurzformen
        data = message['data']
        
        return {
            'timestamp': dt,
            'open': float(data['o']),
            'high': float(data['h']),
            'low': float(data['l']),
            'close': float(data['c']),
            'volume': float(data['q']),
            'turnover': float(data['b'])
        }
    
    async def _on_kline_data(self, message: Dict[str, Any]):
        """
        Callback für eingehende Kline-Daten
        
        Args:
            message: Komplette WebSocket-Message
        """
        try:
            # Parse Kline
            parsed_kline = self._parse_kline(message)
            
            # === FIX: Kerze updaten statt append ===
            # Timestamp auf Minute runden (entferne Sekunden)
            kline_minute = parsed_kline['timestamp'].replace(second=0, microsecond=0)
            
            # Prüfe ob diese Minute schon im Buffer ist
            if len(self.kline_buffer) > 0:
                last_kline = self.kline_buffer[-1]
                last_minute = last_kline['timestamp'].replace(second=0, microsecond=0)
                
                if kline_minute == last_minute:
                    # UPDATE: Gleiche Minute → ersetze letzte Kerze
                    parsed_kline['timestamp'] = kline_minute  # Timestamp auf :00 setzen
                    self.kline_buffer[-1] = parsed_kline
                    logging.debug(f"🔄 Update: {kline_minute.strftime('%H:%M')} | C: {parsed_kline['close']:.5f}")
                else:
                    # NEUE Kerze: Andere Minute → append
                    parsed_kline['timestamp'] = kline_minute
                    self.kline_buffer.append(parsed_kline)
                    logging.info(f"✨ Neue Kerze: {kline_minute.strftime('%H:%M')} | C: {parsed_kline['close']:.5f}")
            else:
                # Buffer leer → erste Kerze
                parsed_kline['timestamp'] = kline_minute
                self.kline_buffer.append(parsed_kline)
            
            # Stats
            self.klines_received += 1
            self.last_kline_time = parsed_kline['timestamp']
            
            # User-Callback triggern (bei jeder Änderung)
            if self.on_kline_callback:
                try:
                    await self.on_kline_callback(parsed_kline, self.get_dataframe())
                except Exception as e:
                    logging.error(f"❌ Callback-Fehler: {e}")
                    
        except Exception as e:
            logging.error(f"❌ Kline-Parse-Fehler: {e}")
            logging.exception("Details:")
    
    async def start(self):
        """Startet den Kline-Manager"""
        logging.info("🚀 WebSocket Kline-Manager gestartet")
        logging.info(f"   Symbol:   {self.symbol}")
        logging.info(f"   Interval: {self.interval} ({self.channel_name})")
        logging.info(f"   Buffer:   {self.buffer_size} Kerzen")
        
        try:
            # Channel-Callback registrieren
            self.ws_client.set_channel_callback(
                self.channel_name,
                self._on_kline_data
            )
            
            # WebSocket-Client starten
            client_task = asyncio.create_task(self.ws_client.start())
            
            # Warte auf Verbindung
            await asyncio.sleep(2)
            
            # Abonniere Kline-Channel
            logging.info(f"📡 Abonniere Channel: {self.channel_name}")
            await self.ws_client.subscribe([
                {
                    "symbol": self.symbol,
                    "ch": self.channel_name
                }
            ])
            
            # Warte auf Client
            await client_task
            
        except asyncio.CancelledError:
            logging.info("🛑 Manager gestoppt")
        except KeyboardInterrupt:
            logging.info("🛑 Manager durch Benutzer gestoppt")
        finally:
            self.stop()
    
    def stop(self):
        """Stoppt den Manager"""
        self.ws_client.stop_ping = True
        logging.info("👋 WebSocket Kline-Manager beendet")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Gibt Manager-Statistiken zurück
        
        Returns:
            Dict mit Stats
        """
        return {
            "connected": self.ws_client.is_connected,
            "klines_received": self.klines_received,
            "buffer_size": len(self.kline_buffer),
            "last_kline_time": self.last_kline_time.strftime('%Y-%m-%d %H:%M:%S') if self.last_kline_time else None,
            "channel": self.channel_name
        }