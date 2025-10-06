import json
from typing import Dict, Optional, Any, List
import requests
from core.config import Config
from core.error_codes import ErrorCode
from core.open_api_http_sign import get_auth_headers, sort_params
import logging
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

class OpenApiHttpFuturePrivate:
    """
    Bitunix Futures HTTP Private API Wrapper
    Dokumentation: https://openapidoc.bitunix.com/doc/trade/place_order.html
    """

    def __init__(self, config: Config):
        self.api_key = config.api_key
        self.secret_key = config.secret_key
        self.base_url = config.uri_prefix
        self.session = requests.Session()
        self.session.headers.update({
            "language": "en-US",
            "Content-Type": "application/json"
        })

    # ----------------------------- Utility -----------------------------
    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        if response.status_code != 200:
            raise Exception(f"HTTP Error: {response.status_code}")
        data = response.json()
        if data.get("code") != 0:
            err = ErrorCode.get_by_code(data["code"])
            if err:
                raise Exception(str(err))
            raise Exception(f"Unknown Error {data['code']}: {data.get('msg')}")
        return data.get("data", {})

    # ----------------------------- Account -----------------------------
    def get_account(self, margin_coin: str = "USDT") -> Dict[str, Any]:
        """Get account balance and margin info"""
        url = f"{self.base_url}/api/v1/futures/account"
        params = {"marginCoin": margin_coin}
        query = sort_params(params)
        headers = get_auth_headers(self.api_key, self.secret_key, query)
        r = self.session.get(url, params=params, headers=headers)
        return self._handle_response(r)

    def change_leverage(self, symbol: str, leverage: int, margin_coin: str = "USDT") -> Dict[str, Any]:
        """Change leverage"""
        url = f"{self.base_url}/api/v1/futures/account/change_leverage"
        data = {"symbol": symbol, "marginCoin": margin_coin, "leverage": str(leverage)}
        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)
        r = self.session.post(url, json=data, headers=headers)
        return self._handle_response(r)

    def change_margin_mode(self, symbol: str, margin_mode: str = "ISOLATION", margin_coin: str = "USDT") -> Dict[str, Any]:
        """Change margin mode: ISOLATION / CROSS"""
        url = f"{self.base_url}/api/v1/futures/account/change_margin_mode"
        data = {"symbol": symbol, "marginMode": margin_mode, "marginCoin": margin_coin}
        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)
        r = self.session.post(url, json=data, headers=headers)
        return self._handle_response(r)

    def change_position_mode(self, mode: str = "HEDGE") -> Dict[str, Any]:
        """Change position mode: HEDGE / ONE_WAY"""
        url = f"{self.base_url}/api/v1/futures/account/change_position_mode"
        data = {"positionMode": mode}
        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)
        r = self.session.post(url, json=data, headers=headers)
        return self._handle_response(r)

    # ----------------------------- Orders -----------------------------
    def place_order(self,
                    symbol: str,
                    side: str,
                    order_type: str,
                    qty: str,
                    price: Optional[str] = None,
                    trade_side: str = "OPEN",
                    effect: str = "GTC",
                    client_id: Optional[str] = None,
                    reduce_only: bool = False,
                    position_id: Optional[str] = None,
                    # TP/SL
                    tp_price: Optional[str] = None,
                    tp_stop_type: Optional[str] = None,
                    tp_order_type: Optional[str] = None,
                    tp_order_price: Optional[str] = None,
                    sl_price: Optional[str] = None,
                    sl_stop_type: Optional[str] = None,
                    sl_order_type: Optional[str] = None,
                    sl_order_price: Optional[str] = None,
                    # Trigger / Conditional
                    trigger_price: Optional[str] = None,
                    trigger_type: Optional[str] = None,
                    order_from: Optional[str] = None,
                    position_mode: Optional[str] = None,
                    reduce_mode: Optional[str] = None
                    ) -> Dict[str, Any]:
        """
        Place an order (supports SL/TP, trigger, trailing etc.)
        """
        url = f"{self.base_url}/api/v1/futures/trade/place_order"
        data = {
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": qty,
            "tradeSide": trade_side,
            "effect": effect,
            "reduceOnly": reduce_only
        }

        # Optional fields
        optional = {
            "price": price,
            "clientId": client_id,
            "positionId": position_id,
            "tpPrice": tp_price,
            "tpStopType": tp_stop_type,
            "tpOrderType": tp_order_type,
            "tpOrderPrice": tp_order_price,
            "slPrice": sl_price,
            "slStopType": sl_stop_type,
            "slOrderType": sl_order_type,
            "slOrderPrice": sl_order_price,
            "triggerPrice": trigger_price,
            "triggerType": trigger_type,
            "orderFrom": order_from,
            "positionMode": position_mode,
            "reduceMode": reduce_mode
        }
        for k, v in optional.items():
            if v is not None:
                data[k] = v

        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)
        r = self.session.post(url, json=data, headers=headers)
        return self._handle_response(r)

    def modify_order(self, symbol: str, order_id: str, **kwargs) -> Dict[str, Any]:
        """Modify an existing order"""
        url = f"{self.base_url}/api/v1/futures/trade/modify_order"
        data = {"symbol": symbol, "orderId": order_id}
        for k, v in kwargs.items():
            if v is not None:
                data[k] = v
        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)
        r = self.session.post(url, json=data, headers=headers)
        return self._handle_response(r)

    def cancel_orders(self, symbol: str, orders: List[Dict[str, str]]) -> Dict[str, Any]:
        """Cancel one or multiple orders"""
        url = f"{self.base_url}/api/v1/futures/trade/cancel_orders"
        data = {"symbol": symbol, "orderList": orders}
        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)
        r = self.session.post(url, json=data, headers=headers)
        return self._handle_response(r)

    def get_open_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Get all current (unfilled) orders"""
        url = f"{self.base_url}/api/v1/futures/trade/get_orders"
        params = {"symbol": symbol} if symbol else {}
        query = sort_params(params)
        headers = get_auth_headers(self.api_key, self.secret_key, query)
        r = self.session.get(url, params=params, headers=headers)
        return self._handle_response(r)

    def get_history_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Get historical orders"""
        url = f"{self.base_url}/api/v1/futures/trade/get_history_orders"
        params = {"symbol": symbol} if symbol else {}
        query = sort_params(params)
        headers = get_auth_headers(self.api_key, self.secret_key, query)
        r = self.session.get(url, params=params, headers=headers)
        return self._handle_response(r)

    # ----------------------------- Positions -----------------------------
    def get_positions(self, symbol: Optional[str] = None, margin_coin: str = "USDT") -> Dict[str, Any]:
        """Get all current positions"""
        url = f"{self.base_url}/api/v1/futures/position/get_positions"
        params = {"marginCoin": margin_coin}
        if symbol:
            params["symbol"] = symbol
        query = sort_params(params)
        headers = get_auth_headers(self.api_key, self.secret_key, query)
        r = self.session.get(url, params=params, headers=headers)
        return self._handle_response(r)

    def get_history_positions(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Get historical positions"""
        url = f"{self.base_url}/api/v1/futures/position/get_history_positions"
        params = {"symbol": symbol} if symbol else {}
        query = sort_params(params)
        headers = get_auth_headers(self.api_key, self.secret_key, query)
        r = self.session.get(url, params=params, headers=headers)
        return self._handle_response(r)

async def main():
    """Main function example"""
    # Load configuration
    config = Config()
    
    # Create client
    client = OpenApiHttpFuturePrivate(config)
    
    try:
        # Get account information
        account = client.get_account()
        logging.info(f"Account info: {account}")
        
        # Get historical position information
        #history_positions = client.get_history_positions("BTCUSDT")
        #logging.info(f"History positions: {history_positions}")
        
        # Get historical orders
        #history_orders = client.get_history_orders("BTCUSDT")
        #logging.info(f"History orders: {history_orders}")

        """
        WARNING!!! This is example code for placing and canceling orders. If you are using a real account,
        please be cautious when uncommenting for testing, as any financial losses will be your responsibility.
        """
        # # Example order placement (limit order)
        # order = client.place_order(
        #     symbol="BTCUSDT",
        #     side="BUY",
        #     order_type="LIMIT",
        #     qty="0.5",
        #     price="60000",
        #     trade_side="OPEN",
        #     effect="GTC",
        #     reduce_only=False,
        #     client_id=time.strftime("%Y%m%d%H%M%S", time.localtime()),
        #     tp_price="61000",
        #     tp_stop_type="MARK",
        #     tp_order_type="LIMIT",
        #     tp_order_price="61000.1"
        # )
        # logging.info(f"Place order result: {order}")
        #
        # # Example order cancellation
        # if order and "orderId" in order:
        #     cancel_result = client.cancel_orders("BTCUSDT", [
        #         {"orderId": order["orderId"]},
        #         {"clientId": order["clientId"]}
        #     ])
        #     logging.info(f"Cancel orders result: {cancel_result}")
        
    except Exception as e:
        logging.error(f"Error in main: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 