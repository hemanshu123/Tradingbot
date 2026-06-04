"""
Pure Python Fisher Transform — matches Delta Exchange chart exactly.
Original working formula from initial commit.
"""
import math
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


def get_live_fisher_data(lookback_periods=9):
    """Fetch latest candles from Binance and return current Fisher + Trigger values."""
    try:
        exchange = ccxt.binance()
        bars     = exchange.fetch_ohlcv("ETH/USDT", timeframe=RESOLUTION, limit=200)
        candles  = [
            {"time": b[0], "open": b[1], "high": b[2],
             "low":  b[3], "close": b[4], "volume": b[5]}
            for b in bars
        ]
        series = _compute_fisher(candles, lookback_periods)
        latest = series[-1]
        return {
            "fisher":  latest["fisher"],
            "trigger": latest["trigger"],
            "close":   latest["close"],
            "time":    latest["time"],
        }
    except Exception as e:
        print(f"[v0] Error fetching Fisher data: {e}")
        return None
