import json
from typing import Dict, Optional, Any, List
import requests
from core.config import Config
from core.error_codes import ErrorCode
from core.open_api_http_sign import get_auth_headers, sort_params
import logging


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

    def modify_order(self,
                 symbol: str,
                 order_id: Optional[str] = None,
                 client_id: Optional[str] = None,
                 price: Optional[str] = None,
                 qty: Optional[str] = None,
                 trigger_price: Optional[str] = None,
                 # TP/SL Parameters
                 tp_price: Optional[str] = None,
                 tp_stop_type: Optional[str] = None,
                 tp_order_type: Optional[str] = None,
                 tp_order_price: Optional[str] = None,
                 sl_price: Optional[str] = None,
                 sl_stop_type: Optional[str] = None,
                 sl_order_type: Optional[str] = None,
                 sl_order_price: Optional[str] = None
                 ) -> Dict[str, Any]:
        """
        Modify an existing order
        Note: Must provide either orderId OR clientId
        """
        url = f"{self.base_url}/api/v1/futures/trade/modify_order"
        
        # Symbol ist Pflicht
        data = {"symbol": symbol}
        
        # Optional fields - nur hinzufügen wenn gesetzt
        optional = {
            "orderId": order_id,
            "clientId": client_id,
            "price": price,
            "qty": qty,
            "triggerPrice": trigger_price,
            "tpPrice": tp_price,
            "tpStopType": tp_stop_type,
            "tpOrderType": tp_order_type,
            "tpOrderPrice": tp_order_price,
            "slPrice": sl_price,
            "slStopType": sl_stop_type,
            "slOrderType": sl_order_type,
            "slOrderPrice": sl_order_price
        }
        
        for k, v in optional.items():
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

