"""
Pure Python Fisher Transform — uses Delta Exchange API for exact data match.
"""
import math
import requests
import time
import ccxt
from bot.config import RESOLUTION


def _compute_fisher(candles, lookback=9):
    out, v_prev, f_prev = [], 0.0, 0.0
    for i in range(len(candles)):
        window = candles[max(0, i - lookback + 1): i + 1]
        HH = max(c["high"]  for c in window)
        LL = min(c["low"]   for c in window)
        cl = candles[i]["close"]
        if HH != LL:
            x = (cl - LL) / (HH - LL)
            v = 0.33 * 2.0 * (x - 0.5) + 0.67 * v_prev
        else:
            v = v_prev
        v = max(min(v, 0.999), -0.999)
        f = 0.5 * math.log((1 + v) / (1 - v))
        out.append({
            "fisher":  f,
            "trigger": f_prev,
            "close":   cl,
            "time":    candles[i]["time"],
        })
        v_prev, f_prev = v, f
    return out


def _from_delta(lookback):
    """Fetch candles from Delta Exchange India API."""
    try:
        now = int(time.time())
        # Fetch 300 candles for proper warm-up and history
        start = now - 300 * 3600
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
    """Fetch Fisher from Delta Exchange API (exact match with chart), fallback to other exchanges."""
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
            series = _compute_fisher(candles, lookback_periods)
            latest = series[-1]
            print(f"[v0] Fisher from {name}")
            return {
                "fisher":  latest["fisher"],
                "trigger": latest["trigger"],
                "close":   latest["close"],
                "time":    latest["time"],
            }
        except Exception as e:
            print(f"[v0] {name} failed: {e}")
            continue

    print("[v0] All sources failed")
    return None
