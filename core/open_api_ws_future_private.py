import asyncio
import json
import logging
import time
import websockets
import ssl
from typing import Dict, Any, List
from core.open_api_ws_sign import get_auth_ws_future
from core.config import Config

# Configure logging
#logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')


class OpenApiWsFuturePrivate:
    def __init__(self, config: Config):
        """
        Initialize private WebSocket client
        """
        self.config = config
        self.base_url = config.private_ws_uri
        self.reconnect_interval = config.reconnect_interval
        self.message_queue = asyncio.Queue()
        self.websocket = None
        self.ping_task = None
        self.is_connected = False
        self.api_key = config.api_key
        self.secret_key = config.secret_key
        self.reconnect_count = 0
        self.max_reconnect_attempts = 5
        self.heartbeat_interval = 3  # Heartbeat interval, in seconds
        self.stop_ping = False
        
    async def _send_ping(self):
        """Send heartbeat message"""
        while not self.stop_ping:
            try:
                if self.websocket and self.is_connected:
                    msg = json.dumps({"op": "ping", "ping": int(round(time.time()))})
                    await self.websocket.send(msg)
                    logging.debug("Sent ping message")
                await asyncio.sleep(self.heartbeat_interval)
            except websockets.exceptions.ConnectionClosedError:
                logging.debug("WebSocket connection closed by remote server")
                self.is_connected = False
                break
            except Exception as e:
                logging.error(f"Ping task failed: {e}")
                self.is_connected = False
                break
                
    async def _authenticate(self):
        """ Authenticate with the server """
        try:
            if not self.websocket or not self.is_connected:
                raise Exception("WebSocket not connected")
                
            auth_data = get_auth_ws_future(self.api_key, self.secret_key)
            await self.websocket.send(json.dumps({
                "op": "login",
                "args": [auth_data]
            }))
            logging.debug("WebSocket authentication successful")
        except Exception as e:
            logging.error(f"Authentication failed: {e}")
            raise
            
    async def subscribe(self, channels: List[Dict[str, str]]):
        """
        Subscribe to private channels
        
        Args:
            channels: List of channels to subscribe to, e.g.:
                [
                    {"ch": "balance"},
                    {"ch": "position"},
                    {"ch": "order"}
                ]
        """
        try:
            if not self.websocket or not self.is_connected:
                raise Exception("WebSocket not connected")
                
            await self.websocket.send(json.dumps({
                "op": "subscribe",
                "args": channels
            }))
            logging.debug("Private channel subscription successful")
        except Exception as e:
            logging.error(f"Private subscription failed: {e}")
            raise
            
    async def _handle_message(self, message: str):
        """Handle received messages"""
        try:
            data = json.loads(message)
            logging.debug(f"Received message: {data}")

            # Handle heartbeat response
            if data.get('op') == 'ping':
                logging.debug("Received pong response")
                return

            # Define allowed private channels
            allowed_channels = ['balance', 'position', 'order', 'tpsl']
            
            if 'ch' in data and data['ch'] in allowed_channels:
                await self.message_queue.put(data)
        except json.JSONDecodeError:
            logging.error("Failed to parse message")
        except Exception as e:
            logging.error(f"Error handling message: {e}")
            
    async def _process_message(self, message: Dict[str, Any]):
        """Process messages in the message queue"""
        try:
            logger = logging.getLogger("WS-PRIVATE")

            if message['ch'] == 'balance':
                # Handle balance data
                balance_data = message['data']
                logger.info("=" * 60)
                logger.info("=== Balance Update ===")
                logger.info("=" * 60)
                logger.info(f"Coin             : {balance_data.get('coin', 'N/A')}")
                logger.info(f"Available Balance: {balance_data.get('available', 'N/A')}")
                logger.info(f"Frozen Amount    : {balance_data.get('frozen', 'N/A')}")
                logger.info(f"Isolation Frozen : {balance_data.get('isolationFrozen', 'N/A')}")
                logger.info(f"Cross Frozen     : {balance_data.get('crossFrozen', 'N/A')}")
                logger.info(f"Margin           : {balance_data.get('margin', 'N/A')}")
                logger.info(f"Isolation Margin : {balance_data.get('isolationMargin', 'N/A')}")
                logger.info(f"Cross Margin     : {balance_data.get('crossMargin', 'N/A')}")
                logger.info(f"Experience Money : {balance_data.get('expMoney', 'N/A')}")

                    
            elif message['ch'] == 'position':
                # Handle position data
                position_data = message['data']
                logger.info("=" * 60)
                logger.info("=== Position Update ===")
                logger.info("=" * 60)
                logger.info(f"Event            : {position_data.get('event', 'N/A')}")
                logger.info(f"Position ID      : {position_data.get('positionId', 'N/A')}")
                logger.info(f"Margin Mode      : {position_data.get('marginMode', 'N/A')}")
                logger.info(f"Position Mode    : {position_data.get('positionMode', 'N/A')}")
                logger.info(f"Side             : {position_data.get('side', 'N/A')}")
                logger.info(f"Leverage         : {position_data.get('leverage', 'N/A')}")
                logger.info(f"Margin           : {position_data.get('margin', 'N/A')}")
                logger.info(f"Create Time      : {position_data.get('ctime', 'N/A')}")
                logger.info(f"Quantity         : {position_data.get('qty', 'N/A')}")
                logger.info(f"Entry Value      : {position_data.get('entryValue', 'N/A')}")
                logger.info(f"Symbol           : {position_data.get('symbol', 'N/A')}")
                logger.info(f"Realized PnL     : {position_data.get('realizedPNL', 'N/A')}")
                logger.info(f"Unrealized PnL   : {position_data.get('unrealizedPNL', 'N/A')}")
                logger.info(f"Funding          : {position_data.get('funding', 'N/A')}")
                logger.info(f"Fee              : {position_data.get('fee', 'N/A')}")

            
            elif message['ch'] == 'order':
                # Handle order data
                order_data = message['data']
                logger.info("=" * 60)
                logger.info("=== Order Update ===")
                logger.info("=" * 60)
                logger.info(f"Order ID         : {order_data.get('orderId', 'N/A')}")
                logger.info(f"Symbol           : {order_data.get('symbol', 'N/A')}")
                logger.info(f"Type             : {order_data.get('type', 'N/A')}")
                logger.info(f"Status           : {order_data.get('status', 'N/A')}")
                logger.info(f"Price            : {order_data.get('price', 'N/A')}")
                logger.info(f"Quantity         : {order_data.get('qty', 'N/A')}")

            
            elif message['ch'] == 'tpsl':
                # Handle tpsl data
                tpsl_data = message['data']
                logger.info("=" * 60)
                logger.info("=== TPSL Update ===")
                logger.info("=" * 60)
                logger.info(f"Symbol           : {tpsl_data.get('symbol', 'N/A')}")
                logger.info(f"Order ID         : {tpsl_data.get('orderId', 'N/A')}")
                logger.info(f"Position ID      : {tpsl_data.get('positionId', 'N/A')}")
                logger.info(f"Leverage         : {tpsl_data.get('leverage', 'N/A')}")
                logger.info(f"Side             : {tpsl_data.get('side', 'N/A')}")
                logger.info(f"Position Mode    : {tpsl_data.get('positionMode', 'N/A')}")
                logger.info(f"Status           : {tpsl_data.get('status', 'N/A')}")
                logger.info(f"Type             : {tpsl_data.get('type', 'N/A')}")
                logger.info(f"SL Quantity      : {tpsl_data.get('slQty', 'N/A')}")
                logger.info(f"TP Order Type    : {tpsl_data.get('tpOrderType', 'N/A')}")
                logger.info(f"SL Stop Type     : {tpsl_data.get('slStopType', 'N/A')}")
                logger.info(f"SL Price         : {tpsl_data.get('slPrice', 'N/A')}")
                logger.info(f"SL Order Price   : {tpsl_data.get('slOrderPrice', 'N/A')}")

                
        except Exception as e:
            logging.error(f"Error processing message: {e}")
            
    async def _consume_messages(self):
        """Consume message queue"""
        while True:
            message = await self.message_queue.get()
            await self._process_message(message)
            
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
            
    async def connect(self):
        """Establish WebSocket connection"""
        reconnect_attempts = 0
        
        while reconnect_attempts < self.max_reconnect_attempts:
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
                    logging.debug("WebSocket connection successful - private")
                    
                    # Authenticate with the server
                    await self._authenticate()
                    
                    # Start heartbeat task
                    await self._start_ping()
                    
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
        """Start WebSocket client"""
        # Start message consumption task
        consume_task = asyncio.create_task(self._consume_messages())
        
        try:
            # Start connection task
            await self.connect()
        except KeyboardInterrupt:
            logging.debug("Program interrupted by user")
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

async def main():
    """Main function example"""
    # Load configuration
    config = Config()
    
    # Create client
    client = OpenApiWsFuturePrivate(config)
    
    # Start client
    client_task = asyncio.create_task(client.start())
    
    # Wait for connection to be established
    await asyncio.sleep(2)
    
    # Subscribe to channels
    await client.subscribe([
        {"ch": "balance"},
        {"ch": "position"},
        {"ch": "order"}
    ])
    
    try:
        await client_task
    except KeyboardInterrupt:
        logging.debug("Program interrupted by user")

if __name__ == "__main__":
    asyncio.run(main()) 