"""
Fisher Transform using stock-indicators library (TradingView exact match).
Now that .NET 8.0 is installed, we can use the professional Fisher implementation.
"""
from datetime import datetime
from stock_indicators.indicators.common.quote import Quote
from stock_indicators import indicators
import requests
import time
import ccxt
from bot.config import RESOLUTION


def _get_fisher_transform(quotes, lookback_periods=9):
    """Use stock-indicators GetFisherTransform (TradingView exact formula)."""
    results = indicators.get_fisher_transform(quotes, lookback_periods)
    return results


def _from_delta(lookback):
    """Fetch candles from Delta Exchange India API."""
    try:
        now = int(time.time())
        start = now - 300 * 3600  # 300 candles for warm-up
        url = "https://api.india.delta.exchange/v2/history/candles"
        params = {"symbol": "ETHUSD", "resolution": RESOLUTION, "start": start, "end": now}

        r = requests.get(url, params=params, timeout=10)
        raw = (r.json().get("result") or []) if r.status_code == 200 else []

        if not raw or len(raw) < lookback + 2:
            return None

        candles = sorted([
            {
                "time":  int(c["time"]) * 1000,
                "open":  float(c["open"]),
                "high":  float(c["high"]),
                "low":   float(c["low"]),
                "close": float(c["close"]),
            }
            for c in raw
        ], key=lambda x: x["time"])
        return candles
    except Exception as e:
        print(f"[v0] Delta API error: {e}")
        return None


def _from_ccxt(exchange_id, symbol, lookback):
    """Fallback: fetch from ccxt exchange."""
    try:
        exchange = getattr(ccxt, exchange_id)()
        bars = exchange.fetch_ohlcv(symbol, timeframe=RESOLUTION, limit=200)
        if not bars or len(bars) < lookback + 2:
            return None
        return [
            {"time": b[0], "open": b[1], "high": b[2], "low": b[3], "close": b[4]}
            for b in bars
        ]
    except Exception as e:
        print(f"[v0] {exchange_id} error: {e}")
        return None


def get_live_fisher_data(lookback_periods=9):
    """Fetch Fisher using TradingView formula (stock-indicators library)."""
    sources = [
        ("Delta Exchange", _from_delta,  None),
        ("Binance",        _from_ccxt,   ("binance",  "ETH/USDT")),
        ("KuCoin",         _from_ccxt,   ("kucoin",   "ETH/USDT")),
        ("Bybit",          _from_ccxt,   ("bybit",    "ETH/USDT")),
        ("OKX",            _from_ccxt,   ("okx",      "ETH/USDT")),
    ]

    for name, fn, args in sources:
        try:
            candles = fn(lookback_periods) if args is None else fn(*args, lookback_periods)
            if not candles:
                continue

            # Convert to Quote objects for stock-indicators
            quotes = [
                Quote(date=datetime.utcfromtimestamp(c["time"] / 1000),
                      open=c["open"], high=c["high"], low=c["low"],
                      close=c["close"], volume=0)
                for c in candles
            ]

            # Calculate Fisher using TradingView formula
            results = _get_fisher_transform(quotes, lookback_periods)
            latest = results[-1]

            print(f"[v0] Fisher from {name} (TradingView formula)")
            return {
                "fisher":  latest.fisher if latest.fisher else 0,
                "trigger": latest.trigger if latest.trigger else 0,
                "close":   quotes[-1].close,
                "time":    candles[-1]["time"],
            }
        except Exception as e:
            print(f"[v0] {name} failed: {e}")
            continue

    print("[v0] All sources failed")
    return None
