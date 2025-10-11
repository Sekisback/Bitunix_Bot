from typing import Dict, Optional, Any
import requests
import sys
from pathlib import Path
from core.config import Config
from core.error_codes import ErrorCode
from core.open_api_http_sign import get_auth_headers, sort_params
import logging
import asyncio

# HTTP Timeout als Konstante (core-spezifisch)
HTTP_TIMEOUT_SECONDS = 30

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

class OpenApiHttpFuturePublic:
    def __init__(self, config: Config):
        self.config = config
        self.base_url = config.uri_prefix
        self.session = requests.Session()
        self.timeout = HTTP_TIMEOUT_SECONDS
        
    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        if response.status_code != 200:
            raise Exception(f"HTTP Error: {response.status_code}")
        data = response.json()
        if data["code"] != 0:
            error = ErrorCode.get_by_code(data["code"])
            if error:
                raise Exception(str(error))
            raise Exception(f"Unknown Error: {data['code']} - {data['msg']}")
        return data["data"]
    
    def get_tickers(self, symbols: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/futures/market/tickers"
        params = {}
        if symbols:
            params["symbols"] = symbols
        query_string = sort_params(params)
        headers = get_auth_headers(self.config.api_key, self.config.secret_key, query_string)
        response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        return self._handle_response(response)

    def get_depth(self, symbol: str, limit: Any = max) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/futures/market/depth"
        params = {"symbol": symbol, "limit": limit}
        query_string = sort_params(params)
        headers = get_auth_headers(self.config.api_key, self.config.secret_key, query_string)
        response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        return self._handle_response(response)
    
    def get_kline(self, symbol: str, interval: str, limit: int = 100, start_time: Optional[int] = None, end_time: Optional[int] = None, type: str = "LAST_PRICE") -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/futures/market/kline"
        params = {"symbol": symbol, "interval": interval, "limit": limit, "type": type}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        query_string = sort_params(params)
        headers = get_auth_headers(self.config.api_key, self.config.secret_key, query_string)
        response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        return self._handle_response(response)
    
    def get_funding_rate(self, symbol: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/futures/market/funding_rate"
        params = {"symbol": symbol}
        query_string = sort_params(params)
        headers = get_auth_headers(self.config.api_key, self.config.secret_key, query_string)
        response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        return self._handle_response(response)

    def get_batch_funding_rate(self) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/futures/market/funding_rate/batch"
        params = {}
        query_string = sort_params(params)
        headers = get_auth_headers(self.config.api_key, self.config.secret_key, query_string)
        response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        return self._handle_response(response)
    
    def get_trading_pairs(self, symbols: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/futures/market/trading_pairs"
        params = {}
        if symbols:
            params["symbols"] = symbols
        query_string = sort_params(params)
        headers = get_auth_headers(self.config.api_key, self.config.secret_key, query_string)
        response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        return self._handle_response(response)

async def main():
    config = Config()
    client = OpenApiHttpFuturePublic(config)
    try:
        tickers = client.get_tickers("BTCUSDT,ETHUSDT")
        logging.info(f"Tickers data: {tickers}")
    except Exception as e:
        logging.error(f"Error in main: {e}")

if __name__ == "__main__":
    asyncio.run(main())
