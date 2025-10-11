import json
from typing import Dict, Optional, Any, List
import requests
from core.config import Config
from core.error_codes import ErrorCode
from core.open_api_http_sign import get_auth_headers, sort_params
import logging
import time
import uuid

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

class OpenApiHttpFuturePrivate:
    """Bitunix Futures HTTP Private API Wrapper"""

    def __init__(self, config: Config):
        self.api_key = config.api_key
        self.secret_key = config.secret_key
        self.base_url = config.uri_prefix
        self.session = requests.Session()
        self.session.headers.update({
            "language": "en-US",
            "Content-Type": "application/json"
        })
        self.timeout = 30  # Global timeout

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

    def get_account(self, margin_coin: str="USDT") -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/futures/account"
        params = {"marginCoin": margin_coin}
        query = sort_params(params)
        headers = get_auth_headers(self.api_key, self.secret_key, query)
        r = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        return self._handle_response(r)

    def change_leverage(self, symbol: str, leverage: int = 5, margin_coin: str = "USDT") -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/futures/account/change_leverage"
        data = {"symbol": symbol, "marginCoin": margin_coin, "leverage": str(leverage)}
        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)
        r = self.session.post(url, json=data, headers=headers, timeout=self.timeout)
        return self._handle_response(r)
    
    def change_margin_mode(self, symbol: str, margin_mode: str = "ISOLATION", margin_coin: str = "USDT") -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/futures/account/change_margin_mode"
        data = {"symbol": symbol, "marginMode": margin_mode, "marginCoin": margin_coin}
        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)
        r = self.session.post(url, json=data, headers=headers, timeout=self.timeout)
        return self._handle_response(r)

    def change_position_mode(self, mode: str = "HEDGE") -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/futures/account/change_position_mode"
        data = {"positionMode": mode}
        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)
        r = self.session.post(url, json=data, headers=headers, timeout=self.timeout)
        return self._handle_response(r)
    
    def get_leverage_margin_mode(self, symbol: str, margin_coin: str = "USDT") -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/futures/account/get_leverage_margin_mode"
        data = {"symbol": symbol, "marginCoin": margin_coin}
        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)
        r = self.session.post(url, json=data, headers=headers, timeout=self.timeout)
        return self._handle_response(r)
    
    def place_order(self, symbol: str, side: str, order_type: str, qty: str, price: Optional[str] = None, trade_side: str = "OPEN",
                    effect: str = "GTC", client_id: Optional[str] = None, reduce_only: bool = False, position_id: Optional[str] = None,
                    tp_price: Optional[str] = None, tp_stop_type: Optional[str] = None, tp_order_type: Optional[str] = None, tp_order_price: Optional[str] = None,
                    sl_price: Optional[str] = None, sl_stop_type: Optional[str] = None, sl_order_type: Optional[str] = None, sl_order_price: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/futures/trade/place_order"
        ot = order_type.upper()
        if ot not in ("LIMIT", "MARKET"):
            raise ValueError("order_type must be 'LIMIT' or 'MARKET'.")
        if ot == "LIMIT" and not price:
            raise ValueError("price is required for LIMIT orders.")
        if tp_order_type and tp_order_type.upper() == "LIMIT" and not tp_order_price:
            raise ValueError("tp_order_price is required when tp_order_type='LIMIT'.")
        if sl_order_type and sl_order_type.upper() == "LIMIT" and not sl_order_price:
            raise ValueError("sl_order_price is required when sl_order_type='LIMIT'.")
        if not client_id:
            client_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"

        data: Dict[str, Any] = {
            "symbol": symbol, "side": side, "orderType": order_type, "qty": qty,
            "tradeSide": trade_side, "effect": effect, "reduceOnly": reduce_only, "clientId": client_id
        }
        optional = {
            "price": price, "positionId": position_id, "tpPrice": tp_price, "tpStopType": tp_stop_type,
            "tpOrderType": tp_order_type, "tpOrderPrice": tp_order_price, "slPrice": sl_price,
            "slStopType": sl_stop_type, "slOrderType": sl_order_type, "slOrderPrice": sl_order_price,
        }
        for k, v in optional.items():
            if v is not None:
                data[k] = v

        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)
        r = self.session.post(url, json=data, headers=headers, timeout=self.timeout)
        return self._handle_response(r)

    def modify_order(self, order_id: Optional[str] = None, client_id: Optional[str] = None, 
                    price: Optional[str] = None, qty: Optional[str] = None,
                    tp_price: Optional[str] = None, tp_order_price: Optional[str] = None, 
                    sl_price: Optional[str] = None, sl_order_price: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/futures/trade/modify_order"
        if not order_id and not client_id:
            raise ValueError("Either 'order_id' or 'client_id' must be provided")
        data = {}
        if order_id:
            data["orderId"] = order_id
        if client_id:
            data["clientId"] = client_id
        optional = {
            "price": price, "qty": qty, "tpPrice": tp_price,
            "tpOrderPrice": tp_order_price, "slPrice": sl_price, "slOrderPrice": sl_order_price
        }
        for k, v in optional.items():
            if v is not None:
                data[k] = v
        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)
        r = self.session.post(url, json=data, headers=headers, timeout=self.timeout)
        return self._handle_response(r)

    def cancel_orders(self, symbol: str, order_list: List[Dict[str, str]]) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/futures/trade/cancel_orders"
        if not order_list:
            raise ValueError("order_list cannot be empty")
        for order in order_list:
            if "orderId" not in order and "clientId" not in order:
                raise ValueError("Each order must contain either 'orderId' or 'clientId'")
        data = {"symbol": symbol, "orderList": order_list}
        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)
        r = self.session.post(url, json=data, headers=headers, timeout=self.timeout)
        return self._handle_response(r)

    def get_order_detail(self, order_id: Optional[str] = None, client_order_id: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/futures/trade/get_order_detail"
        if not order_id and not client_order_id:
            raise ValueError("Either 'order_id' or 'client_order_id' must be provided")
        data = {}
        if order_id:
            data["orderId"] = order_id
        if client_order_id:
            data["clientOrderId"] = client_order_id
        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)
        response = self.session.post(url, json=data, headers=headers, timeout=self.timeout)
        return self._handle_response(response)

    def get_pending_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/futures/trade/get_pending_orders"
        params = {"symbol": symbol} if symbol else {}
        query = sort_params(params)
        headers = get_auth_headers(self.api_key, self.secret_key, query)
        r = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        return self._handle_response(r)

    def get_history_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/futures/trade/get_history_orders"
        params = {"symbol": symbol} if symbol else {}
        query = sort_params(params)
        headers = get_auth_headers(self.api_key, self.secret_key, query)
        r = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        return self._handle_response(r)

    def get_positions(self, symbol: Optional[str] = None, margin_coin: str = "USDT") -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/futures/position/get_positions"
        params = {"marginCoin": margin_coin}
        if symbol:
            params["symbol"] = symbol
        query = sort_params(params)
        headers = get_auth_headers(self.api_key, self.secret_key, query)
        r = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        return self._handle_response(r)

    def get_history_positions(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/futures/position/get_history_positions"
        params = {"symbol": symbol} if symbol else {}
        query = sort_params(params)
        headers = get_auth_headers(self.api_key, self.secret_key, query)
        r = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        return self._handle_response(r)
