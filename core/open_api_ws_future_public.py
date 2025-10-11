import asyncio
import json
import logging
import ssl
import time
import websockets
from typing import Dict, Any, List, Callable, Optional
from core.config import Config

logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

class OpenApiWsFuturePublic:
    def __init__(self, config: Config, on_message_callback: Optional[Callable] = None):
        self.config = config
        self.base_url = config.public_ws_uri
        self.reconnect_interval = config.reconnect_interval
        self.message_queue = asyncio.Queue()
        self.websocket = None
        self.ping_task = None
        self.is_connected = False
        self.stop_ping = False
        self.heartbeat_interval = 3
        self.on_message_callback = on_message_callback
        self.channel_callbacks = {}
        self.subscribed_channels = []  # Memory Leak Fix: Liste für Re-Subscribe
        
    def set_channel_callback(self, channel: str, callback: Callable):
        self.channel_callbacks[channel] = callback
        
    async def _send_ping(self):
        while not self.stop_ping:
            try:
                if self.websocket and self.is_connected:
                    msg = json.dumps({"op": "ping", "ping": int(round(time.time()))})
                    await self.websocket.send(msg)
                await asyncio.sleep(self.heartbeat_interval)
            except websockets.exceptions.ConnectionClosedError:
                logging.debug("WebSocket connection closed by remote server")
                self.is_connected = False
                break
            except Exception as e:
                logging.error(f"Ping task failed: {e}")
                self.is_connected = False
                break
                
    async def _start_ping(self):
        if self.ping_task:
            self.ping_task.cancel()
            try:
                await self.ping_task
            except asyncio.CancelledError:
                pass
        self.stop_ping = False
        self.ping_task = asyncio.create_task(self._send_ping())
        
    async def subscribe(self, channels: List[Dict[str, str]]):
        try:
            if not self.websocket or not self.is_connected:
                raise Exception("WebSocket not connected")
            
            # Memory Leak Fix: Merge statt überschreiben
            for ch in channels:
                if ch not in self.subscribed_channels:
                    self.subscribed_channels.append(ch)
                
            await self.websocket.send(json.dumps({"op": "subscribe", "args": channels}))
            logging.debug("Public channel subscription successful")
        except Exception as e:
            logging.error(f"Public subscription failed: {e}")
            raise
    
    async def _resubscribe(self):
        if self.subscribed_channels:
            logging.debug("🔄 Re-Subscribe nach Reconnect...")
            await asyncio.sleep(1)
            try:
                await self.websocket.send(json.dumps({
                    "op": "subscribe",
                    "args": self.subscribed_channels
                }))
                logging.debug(f"✅ Re-Subscribe erfolgreich: {[c.get('ch') for c in self.subscribed_channels]}")
            except Exception as e:
                logging.error(f"❌ Re-Subscribe fehlgeschlagen: {e}")
            
    async def _handle_message(self, message: str):
        try:
            data = json.loads(message)
            if data.get('op') == 'pong':
                logging.debug("Received pong response")
                return
            if data.get('op') == 'subscribe':
                logging.debug(f"Subscription confirmed: {data}")
                return
            channel = data.get('ch', '')
            allowed_channels = ['depth_book1', 'trade', 'ticker']
            is_kline = channel.startswith('market_kline_') or channel.startswith('mark_kline_')
            if channel in allowed_channels or is_kline:
                await self.message_queue.put(data)
                if self.on_message_callback:
                    try:
                        await self.on_message_callback(channel, data)
                    except Exception as e:
                        logging.error(f"Callback error: {e}")
                if channel in self.channel_callbacks:
                    try:
                        await self.channel_callbacks[channel](data)
                    except Exception as e:
                        logging.error(f"Channel callback error for {channel}: {e}")
        except json.JSONDecodeError:
            logging.error("Failed to parse message")
        except Exception as e:
            logging.error(f"Error handling message: {e}")
            
    async def _process_message(self, message: Dict[str, Any]):
        try:
            channel = message.get('ch', '')
            if channel == 'trade':
                trade_data = message['data']
                logging.debug(f"Received trade data: {trade_data}")
            elif channel == 'ticker':
                ticker_data = message['data']
                logging.debug(f"Received 24h ticker: {ticker_data}")
            elif channel == 'depth_book1':
                depth_data = message['data']
                logging.debug(f"Received order book depth: {depth_data}")
            elif channel.startswith('market_kline_') or channel.startswith('mark_kline_'):
                kline_data = message.get('data', {})
                symbol = message.get('symbol', 'N/A')
                ts = message.get('ts', 0)
        except Exception as e:
            logging.error(f"Error processing message: {e}")
            
    async def _consume_messages(self):
        while True:
            message = await self.message_queue.get()
            await self._process_message(message)
            
    async def connect(self):
        reconnect_attempts = 0
        while True:
            try:
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                async with websockets.connect(
                        self.base_url, ssl=ssl_context,
                        ping_interval=None, ping_timeout=5, close_timeout=5
                ) as websocket:
                    self.websocket = websocket
                    self.is_connected = True
                    logging.debug("WebSocket connection successful - public")
                    await self._start_ping()
                    if reconnect_attempts > 0:
                        await self._resubscribe()
                    try:
                        async for message in websocket:
                            await self._handle_message(message)
                    except websockets.exceptions.ConnectionClosedError:
                        logging.debug("WebSocket connection closed by remote server, attempting to reconnect...")
                    except Exception as e:
                        logging.error(f"Error processing message: {e}")
                    finally:
                        self.stop_ping = True
                        if self.ping_task:
                            self.ping_task.cancel()
                            try:
                                await self.ping_task
                            except asyncio.CancelledError:
                                pass
                    self.is_connected = False
                    await asyncio.sleep(self.reconnect_interval)
                    reconnect_attempts += 1
                    logging.debug(f"Attempting to reconnect... ({reconnect_attempts})")
            except Exception as e:
                logging.error(f"WebSocket connection failed: {e}")
                self.is_connected = False
                await asyncio.sleep(self.reconnect_interval)
                reconnect_attempts += 1
                
    async def start(self):
        consume_task = asyncio.create_task(self._consume_messages())
        try:
            await self.connect()
        except KeyboardInterrupt:
            logging.debug("Program interrupted by user")
        except Exception as e:
            logging.error(f"Program error: {e}")
        finally:
            self.stop_ping = True
            if self.ping_task:
                self.ping_task.cancel()
            consume_task.cancel()
            await asyncio.gather(self.ping_task, consume_task, return_exceptions=True)
