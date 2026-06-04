import time
import hmac
import json
import hashlib
import requests
from urllib.parse import urlencode
from typing import Any, Dict, List, Optional

from .config import DELTA_API_KEY, DELTA_API_SECRET

BASE_URL = "https://api.delta.exchange"

def _sign(method: str, path: str, body: str = ""):
    ts = str(int(time.time()))
    payload = f"{ts}{method.upper()}{path}{body}"
    sig = hmac.new(DELTA_API_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return ts, sig

def _headers(ts: str, sig: str):
    return {"api-key": DELTA_API_KEY, "timestamp": ts, "signature": sig, "Content-Type": "application/json"}

def delta_get(path: str, params: Optional[dict] = None):
    qs = ""
    if params:
        qs = "?" + urlencode(params)
    ts, sig = _sign("GET", path + qs, "")
    url = f"{BASE_URL}{path}{qs}"
    r = requests.get(url, headers=_headers(ts, sig), timeout=15)
    r.raise_for_status()
    return r.json()

def delta_post(path: str, data: dict):
    body = json.dumps(data)
    ts, sig = _sign("POST", path, body)
    url = f"{BASE_URL}{path}"
    r = requests.post(url, headers=_headers(ts, sig), data=body, timeout=15)
    r.raise_for_status()
    return r.json()

def delta_get_public(path: str, params: Optional[dict] = None):
    """Make unauthenticated GET request for public endpoints"""
    qs = ""
    if params:
        qs = "?" + urlencode(params)
    url = f"{BASE_URL}{path}{qs}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json()

def get_candles(product_id: int, resolution: str, limit: int = 300):
    """Get candles using public API endpoint (no authentication required)"""
    
    symbol_map = {
        27: "BTCUSD",    # Bitcoin perpetual
        3136: "ETHUSD",  # Ethereum perpetual
    }
    
    if product_id in symbol_map:
        symbol = symbol_map[product_id]
        print(f"[v0] Using mapped symbol: {symbol} for product_id {product_id}")
    else:
        # Fallback to API lookup for unknown products
        product_data = delta_get_public("/v2/products", {"ids": str(product_id)})
        products = product_data.get("result", [])
        if not products:
            raise RuntimeError(f"Product {product_id} not found")
        symbol = products[0]["symbol"]
        print(f"[v0] Retrieved symbol from API: {symbol} for product_id {product_id}")
    
    # Calculate time range based on limit and resolution
    now = int(time.time())
    
    # Convert resolution to seconds for calculation
    resolution_seconds = {
        "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
        "1h": 3600, "4h": 14400, "1d": 86400
    }
    
    interval_seconds = resolution_seconds.get(resolution, 900)  # default to 15m
    start_time = now - (limit * interval_seconds)
    
    params = {
        "symbol": symbol,
        "resolution": resolution,
        "start": start_time,
        "end": now
    }
    
    from datetime import datetime
    start_readable = datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')
    end_readable = datetime.fromtimestamp(now).strftime('%Y-%m-%d %H:%M:%S')
    print(f"[v0] Requesting {symbol} candles from {start_readable} to {end_readable}")
    print(f"[v0] API params: {params}")
    
    data = delta_get_public("/v2/history/candles", params)
    result = data.get("result") or []
    
    for candle in result:
        if candle.get("time"):
            # Ensure timestamp is in seconds (Unix timestamp should be ~10 digits)
            if candle["time"] > 2000000000:  # If timestamp looks like milliseconds
                candle["time"] = candle["time"] // 1000
    
    print(f"[v0] Received {len(result)} {symbol} candles")
    return result

def get_ticker(product_id: int) -> Dict[str, Any]:
    data = delta_get("/v2/tickers", {"product_ids": str(product_id)})
    arr = data.get("result") or []
    if not arr:
        raise RuntimeError("No ticker data returned")
    return arr[0]

def place_market_order(product_id: int, side: str, size: float) -> Dict[str, Any]:
    payload = {"product_id": product_id, "side": side.lower(), "order_type": "market", "size": size, "time_in_force": "ioc", "reduce_only": False}
    return delta_post("/v2/orders", payload)

def close_with_market_order(product_id: int, side: str, size: float) -> Dict[str, Any]:
    opp = "sell" if side.lower() == "buy" else "buy"
    return place_market_order(product_id, opp, size)
