import json
from typing import Dict, Optional, Any, List
import requests
from core.config import Config
from core.error_codes import ErrorCode
from core.open_api_http_sign import get_auth_headers, sort_params
import logging
import time
import uuid


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
    # === ACCOUNT INFO ===
    def get_account(self, margin_coin: str="USDT") -> Dict[str, Any]:
        """
        Get account balance and margin info
        
        Args:
            margin_coin: Margin coin symbol (e.g., "USDT")
        
        Returns:
            Account information including balance, available margin, etc.
        """
        url = f"{self.base_url}/api/v1/futures/account"
        params = {"marginCoin": margin_coin}
        query = sort_params(params)
        headers = get_auth_headers(self.api_key, self.secret_key, query)
        r = self.session.get(url, params=params, headers=headers)
        return self._handle_response(r)

    # === HEBEL (Leverage) ÄNDERN ===
    def change_leverage(self, symbol: str, leverage: int = 5, margin_coin: str = "USDT") -> Dict[str, Any]:
        """
        Change leverage for a specific symbol
        
        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            leverage: Leverage value (default: 5)
            margin_coin: Margin coin (default: "USDT")
        
        Returns:
            Result of leverage change operation
        """
        url = f"{self.base_url}/api/v1/futures/account/change_leverage"
        data = {
            "symbol": symbol,
            "marginCoin": margin_coin,
            "leverage": str(leverage)
        }
        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)
        r = self.session.post(url, json=data, headers=headers)
        return self._handle_response(r)
    
    # === MARGIN MODE ÄNDERN ===
    def change_margin_mode(self, symbol: str, margin_mode: str = "ISOLATION", margin_coin: str = "USDT") -> Dict[str, Any]:
        """
        Change margin mode for a specific symbol
        
        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            margin_mode: Margin mode - "ISOLATION" or "CROSS" (default: "ISOLATION")
            margin_coin: Margin coin (default: "USDT")
        
        Returns:
            Result of margin mode change operation
        """
        url = f"{self.base_url}/api/v1/futures/account/change_margin_mode"
        data = {
            "symbol": symbol,
            "marginMode": margin_mode,
            "marginCoin": margin_coin
        }
        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)
        r = self.session.post(url, json=data, headers=headers)
        return self._handle_response(r)

    # === POSITIONSMODUS ÄNDERN ===
    def change_position_mode(self, mode: str = "HEDGE") -> Dict[str, Any]:
        """
        Change position mode
        
        Args:
            mode: Position mode - "HEDGE" or "ONE_WAY" (default: "HEDGE")
        
        Returns:
            Result of position mode change operation
        """
        url = f"{self.base_url}/api/v1/futures/account/change_position_mode"
        data = {"positionMode": mode}
        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)
        r = self.session.post(url, json=data, headers=headers)
        return self._handle_response(r)
    
    # === HEBEL UND MARGIN MODE ABFRAGEN ===
    def get_leverage_margin_mode(self, symbol: str, margin_coin: str = "USDT") -> Dict[str, Any]:
        """
        get Leverage and Margin Mode
        
        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            margin_coin: Margin coin (default: "USDT")
        
        Returns:
            Result margin mode and leverage
        """
        url = f"{self.base_url}/api/v1/futures/account/get_leverage_margin_mode"
        data = {
            "symbol": symbol,
            "marginCoin": margin_coin
        }
        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)
        r = self.session.post(url, json=data, headers=headers)
        return self._handle_response(r)
    
    # ----------------------------- Orders -----------------------------
    # === ORDER SETZEN ===
    def place_order(self, symbol: str, side: str, order_type: str, qty: str, price: Optional[str] = None, trade_side: str = "OPEN",
                    effect: str = "GTC", client_id: Optional[str] = None, reduce_only: bool = False, position_id: Optional[str] = None,
                    tp_price: Optional[str] = None, tp_stop_type: Optional[str] = None, tp_order_type: Optional[str] = None, tp_order_price: Optional[str] = None,
                    sl_price: Optional[str] = None, sl_stop_type: Optional[str] = None, sl_order_type: Optional[str] = None, sl_order_price: Optional[str] = None) -> Dict[str, Any]:
        """
        Place a futures order (supports MARKET/LIMIT + TP/SL fields)

        Endpoint:
            POST /api/v1/futures/trade/place_order

        Required args:
            symbol (str): Futures symbol, e.g. "BTCUSDT"
            side (str): "BUY" or "SELL"
            order_type (str): "LIMIT" or "MARKET"
            qty (str): Order quantity

        Optional args:
            price (str): Limit price (REQUIRED if order_type == "LIMIT")
            trade_side (str): "OPEN" (default) or "CLOSE"
            effect (str): "GTC" (default), "IOC", "FOK"
            client_id (str): Custom client order ID. If None, a random ID is generated.
            reduce_only (bool): Only reduce existing position (default False)
            position_id (str): Position ID when targeting a specific position

            # Take-Profit / Stop-Loss trigger fields (optional)
            tp_price (str): TP trigger price
            tp_stop_type (str): "MARK_PRICE" or "LAST_PRICE"
            tp_order_type (str): "MARKET" or "LIMIT"
            tp_order_price (str): Required if tp_order_type == "LIMIT"

            sl_price (str): SL trigger price
            sl_stop_type (str): "MARK_PRICE" or "LAST_PRICE"
            sl_order_type (str): "MARKET" or "LIMIT"
            sl_order_price (str): Required if sl_order_type == "LIMIT"

        Returns:
            Dict[str, Any]: API response (e.g. contains orderId, clientId, status)

        Notes:
            - Leverage and margin mode are NOT parameters of this endpoint.
            Use /account/change_leverage and /account/change_margin_mode instead.
        """
        url = f"{self.base_url}/api/v1/futures/trade/place_order"

        # --- Basic validation ---
        ot = order_type.upper()
        if ot not in ("LIMIT", "MARKET"):
            raise ValueError("order_type must be 'LIMIT' or 'MARKET'.")
        if ot == "LIMIT" and not price:
            raise ValueError("price is required for LIMIT orders.")
        if tp_order_type and tp_order_type.upper() == "LIMIT" and not tp_order_price:
            raise ValueError("tp_order_price is required when tp_order_type='LIMIT'.")
        if sl_order_type and sl_order_type.upper() == "LIMIT" and not sl_order_price:
            raise ValueError("sl_order_price is required when sl_order_type='LIMIT'.")

        # --- Ensure clientId ---
        if not client_id:
            client_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"

        # --- Payload ---
        data: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": qty,
            "tradeSide": trade_side,
            "effect": effect,
            "reduceOnly": reduce_only,
            "clientId": client_id
        }

        # Optional fields only when present
        optional = {
            "price": price,
            "positionId": position_id,
            "tpPrice": tp_price,
            "tpStopType": tp_stop_type,
            "tpOrderType": tp_order_type,
            "tpOrderPrice": tp_order_price,
            "slPrice": sl_price,
            "slStopType": sl_stop_type,
            "slOrderType": sl_order_type,
            "slOrderPrice": sl_order_price,
        }

        # Filter out None values
        for k, v in optional.items():
            if v is not None:
                data[k] = v

        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)

        r = self.session.post(url, json=data, headers=headers)
        return self._handle_response(r)


    # === ORDER MODIFIZIEREN ===
    def modify_order(self, order_id: Optional[str] = None, client_id: Optional[str] = None, 
                    price: Optional[str] = None, qty: Optional[str] = None,
                    tp_price: Optional[str] = None, tp_order_price: Optional[str] = None, 
                    sl_price: Optional[str] = None, sl_order_price: Optional[str] = None) -> Dict[str, Any]:
        """
        Modify an existing futures order.

        Endpoint:
            POST /api/v1/futures/trade/modify_order

        Args:
            order_id (str): Bitunix order ID (required if client_id not provided)
            client_id (str): Client order ID (required if order_id not provided)
            price (str): New limit price (required for LIMIT orders)
            qty (str): New quantity (required)
            tp_price (str, optional): Take-profit trigger price
            tp_order_price (str, optional): Take-profit limit order price
            sl_price (str, optional): Stop-loss trigger price
            sl_order_price (str, optional): Stop-loss limit order price

        Returns:
            Dict[str, Any]: Bitunix API response (updated order info)

        Raises:
            ValueError: If neither order_id nor client_id is provided
            Exception: If the API returns an error
        """
        url = f"{self.base_url}/api/v1/futures/trade/modify_order"

        # === Validation ===
        if not order_id and not client_id:
            raise ValueError("Either 'order_id' or 'client_id' must be provided")

        # === Build payload ===
        data = {}
        if order_id:
            data["orderId"] = order_id
        if client_id:
            data["clientId"] = client_id              # ← KORRIGIERT

        # Optional parameters
        optional = {
            "price": price,
            "qty": qty,
            "tpPrice": tp_price,                      # ← KORRIGIERT
            "tpOrderPrice": tp_order_price,
            "slPrice": sl_price,                      # ← KORRIGIERT
            "slOrderPrice": sl_order_price
        }
        for k, v in optional.items():
            if v is not None:
                data[k] = v
        
        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)
        r = self.session.post(url, json=data, headers=headers)
        return self._handle_response(r)


    # === ORDERS STORNIEREN (MEHRERE) ===
    def cancel_orders(self, symbol: str, order_list: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Cancel one or multiple futures orders.

        Endpoint:
            POST /api/v1/futures/trade/cancel_orders

        Args:
            symbol (str): Trading pair (e.g., "BTCUSDT")
            order_list (List[Dict[str, str]]): List of orders to cancel
                Each dict must contain either:
                - {"orderId": "123456"} or
                - {"clientId": "my_order_id"}

        Returns:
            Dict[str, Any]: Response with successList and failureList
                {
                    "successList": [{"orderId": "...", "clientId": "..."}],
                    "failureList": [{"orderId": "...", "clientId": "...", "errorMsg": "...", "errorCode": ...}]
                }

        Raises:
            ValueError: If order_list is empty or invalid
            Exception: If the API returns an error

        Example:
            cancel_orders(
                symbol="BTCUSDT",
                order_list=[
                    {"orderId": "123456"},
                    {"clientId": "my_order_1"}
                ]
            )
        """
        url = f"{self.base_url}/api/v1/futures/trade/cancel_orders"

        # === Validation ===
        if not order_list:
            raise ValueError("order_list cannot be empty")
        
        for order in order_list:
            if "orderId" not in order and "clientId" not in order:
                raise ValueError("Each order must contain either 'orderId' or 'clientId'")

        # === Build payload ===
        data = {
            "symbol": symbol,
            "orderList": order_list
        }
        
        body = json.dumps(data)
        headers = get_auth_headers(self.api_key, self.secret_key, body=body)
        r = self.session.post(url, json=data, headers=headers)
        return self._handle_response(r)


    # === OFFENE ORDERN ===
    def get_order_detail(self, order_id: Optional[str] = None, client_order_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get detailed information for a specific order.
        POST /api/v1/futures/trade/get_order_detail

        Args:
            order_id: The unique order ID returned by Bitunix.
            client_order_id: The custom client ID (if you set one).

        Returns:
            Dict[str, Any]: Detailed order info.
        """
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
        response = self.session.post(url, json=data, headers=headers)
        return self._handle_response(response)


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

