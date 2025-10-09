import asyncio
import json
import logging
import ssl
import time
import websockets
from typing import Dict, Any, List, Callable, Optional
from core.config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

class OpenApiWsFuturePublic:
    def __init__(self, config: Config, on_message_callback: Optional[Callable] = None):
        """
        Initialize OpenApiWsFuturePublic class
        
        Args:
            config: Config object
            on_message_callback: Optional callback function for all messages
                                 Signature: async def callback(channel, data)
        """
        self.config = config
        self.base_url = config.public_ws_uri
        self.reconnect_interval = config.reconnect_interval
        self.message_queue = asyncio.Queue()
        self.websocket = None
        self.ping_task = None
        self.is_connected = False
        self.stop_ping = False
        self.heartbeat_interval = 3  # Heartbeat interval, in seconds
        
        # Callback system
        self.on_message_callback = on_message_callback
        self.channel_callbacks = {}  # Channel-specific callbacks
        
        # NEU: Speichere Subscriptions für Re-Subscribe nach Reconnect
        self.subscribed_channels = []
        
    def set_channel_callback(self, channel: str, callback: Callable):
        """
        Register a callback for a specific channel
        
        Args:
            channel: Channel name (e.g., "market_kline_1min", "trade", "ticker")
            callback: Async callback function(data)
        """
        self.channel_callbacks[channel] = callback
        
    async def _send_ping(self):
        """Send heartbeat message"""
        while not self.stop_ping:
            try:
                if self.websocket and self.is_connected:
                    msg = json.dumps({"op": "ping", "ping": int(round(time.time()))})
                    await self.websocket.send(msg)
                    #logging.debug("Sent ping message")
                await asyncio.sleep(self.heartbeat_interval)
            except websockets.exceptions.ConnectionClosedError:
                logging.info("WebSocket connection closed by remote server")
                self.is_connected = False
                break
            except Exception as e:
                logging.error(f"Ping task failed: {e}")
                self.is_connected = False
                break
                
    async def _start_ping(self):
        """Start heartbeat task"""
        if self.ping_task:
            self.ping_task.cancel()
            try:
                await self.ping_task
            except asyncio.CancelledError:
                pass
        self.stop_ping = False
        self.ping_task = asyncio.create_task(self._send_ping())
        
    async def subscribe(self, channels: List[Dict[str, str]]):
        """
        Subscribe to public channels
        
        Args:
            channels: List of channels to subscribe to, e.g.:
                [
                    {"symbol": "BTCUSDT", "ch": "trade"},
                    {"symbol": "BTCUSDT", "ch": "ticker"},
                    {"symbol": "BTCUSDT", "ch": "depth_book1"},
                    {"symbol": "BTCUSDT", "ch": "market_kline_1min"},
                    {"symbol": "BTCUSDT", "ch": "mark_kline_5min"}
                ]
        """
        try:
            if not self.websocket or not self.is_connected:
                raise Exception("WebSocket not connected")
            
            # NEU: Speichere Channels für Re-Subscribe
            self.subscribed_channels = channels
                
            await self.websocket.send(json.dumps({
                "op": "subscribe",
                "args": channels
            }))
            logging.info("Public channel subscription successful")
        except Exception as e:
            logging.error(f"Public subscription failed: {e}")
            raise
    
    async def _resubscribe(self):
        """
        NEU: Re-Subscribe zu gespeicherten Channels nach Reconnect
        """
        if self.subscribed_channels:
            logging.info("🔄 Re-Subscribe nach Reconnect...")
            await asyncio.sleep(1)  # Kurz warten nach Verbindung
            try:
                await self.websocket.send(json.dumps({
                    "op": "subscribe",
                    "args": self.subscribed_channels
                }))
                logging.info(f"✅ Re-Subscribe erfolgreich: {[c.get('ch') for c in self.subscribed_channels]}")
            except Exception as e:
                logging.error(f"❌ Re-Subscribe fehlgeschlagen: {e}")
            
    async def _handle_message(self, message: str):
        """Handle received messages"""
        try:
            data = json.loads(message)

            # Handle heartbeat response
            if data.get('op') == 'pong':
                logging.debug("Received pong response")
                return

            # Handle subscription confirmation
            if data.get('op') == 'subscribe':
                logging.debug(f"Subscription confirmed: {data}")
                return

            # Get channel name
            channel = data.get('ch', '')
            
            # Define allowed public channels (inkl. kline patterns)
            allowed_channels = ['depth_book1', 'trade', 'ticker']
            
            # Check if kline channel (market_kline_* or mark_kline_*)
            is_kline = channel.startswith('market_kline_') or channel.startswith('mark_kline_')
            
            if channel in allowed_channels or is_kline:
                await self.message_queue.put(data)
                
                # Trigger general callback if registered
                if self.on_message_callback:
                    try:
                        # Pass entire message (includes ts, symbol, data)
                        await self.on_message_callback(channel, data)
                    except Exception as e:
                        logging.error(f"Callback error: {e}")
                
                # Trigger channel-specific callback if registered
                if channel in self.channel_callbacks:
                    try:
                        # Pass entire message for klines (needs ts)
                        await self.channel_callbacks[channel](data)
                    except Exception as e:
                        logging.error(f"Channel callback error for {channel}: {e}")
                        
        except json.JSONDecodeError:
            logging.error("Failed to parse message")
        except Exception as e:
            logging.error(f"Error handling message: {e}")
            
    async def _process_message(self, message: Dict[str, Any]):
        """Process messages in the message queue (default handler)"""
        try:
            channel = message.get('ch', '')
            
            if channel == 'trade':
                # Handle real-time trade data
                trade_data = message['data']
                logging.info(f"Received trade data: {trade_data}")
                
            elif channel == 'ticker':
                # Handle 24-hour market data
                ticker_data = message['data']
                logging.info(f"Received 24h ticker: {ticker_data}")
                
            elif channel == 'depth_book1':
                # Handle order book depth data
                depth_data = message['data']
                logging.info(f"Received order book depth: {depth_data}")
                
            elif channel.startswith('market_kline_') or channel.startswith('mark_kline_'):
                # Handle kline/candlestick data
                kline_data = message.get('data', {})
                symbol = message.get('symbol', 'N/A')
                ts = message.get('ts', 0)
                
                # logging.debug(  # ← DEBUG = nur wenn Debug-Mode AN
                #     f"Received kline ({channel}): "
                #     f"{symbol} @ {ts} | "
                #     f"O:{kline_data.get('o')} H:{kline_data.get('h')} "
                #     f"L:{kline_data.get('l')} C:{kline_data.get('c')}"
                # )
                
        except Exception as e:
            logging.error(f"Error processing message: {e}")
            
    async def _consume_messages(self):
        """Consume message queue"""
        while True:
            message = await self.message_queue.get()
            await self._process_message(message)
            
    async def connect(self):
        """Establish WebSocket connection"""
        reconnect_attempts = 0
        
        while True:
            try:
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                async with websockets.connect(
                        self.base_url,
                        ssl=ssl_context,
                        ping_interval=None,  # Disable automatic heartbeat at WebSocket protocol layer
                        ping_timeout=5,  # Set ping timeout
                        close_timeout=5  # Set close timeout
                ) as websocket:
                    self.websocket = websocket
                    self.is_connected = True
                    logging.info("WebSocket connection successful - public")
                    
                    # Start heartbeat task
                    await self._start_ping()
                    
                    # NEU: Re-Subscribe nach Reconnect
                    if reconnect_attempts > 0:
                        await self._resubscribe()
                    
                    try:
                        async for message in websocket:
                            await self._handle_message(message)
                    except websockets.exceptions.ConnectionClosedError:
                        logging.info("WebSocket connection closed by remote server, attempting to reconnect...")
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
                    logging.info(f"Attempting to reconnect... ({reconnect_attempts})")
                    
            except Exception as e:
                logging.error(f"WebSocket connection failed: {e}")
                self.is_connected = False
                await asyncio.sleep(self.reconnect_interval)
                reconnect_attempts += 1
                
    async def start(self):
        """Start WebSocket client"""
        # Start message consumption task
        consume_task = asyncio.create_task(self._consume_messages())
        
        try:
            # Start connection task
            await self.connect()
        except KeyboardInterrupt:
            logging.info("Program interrupted by user")
        except Exception as e:
            logging.error(f"Program error: {e}")
        finally:
            # Cancel all tasks
            self.stop_ping = True
            if self.ping_task:
                self.ping_task.cancel()
            consume_task.cancel()
            
            # Wait for tasks to be cancelled
            await asyncio.gather(self.ping_task, consume_task, return_exceptions=True)