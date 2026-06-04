"""
Pure Python Fisher Transform — no .NET / stock_indicators dependency.
Same algorithm used in all backtests, so live results will match.

Data source priority:
  1. Delta Exchange India (matches exactly what Delta's chart shows)
  2. KuCoin  (fallback — works from US servers like Render)
  3. Bybit   (fallback)
  4. Binance (fallback — may be blocked on US servers)
"""
import math
import ccxt
from bot.config import RESOLUTION, DELTA_PRODUCT_ID


def _compute_fisher(candles, lookback=9):
    # TradingView / Delta Exchange formula: uses HL2 = (high+low)/2
    out, v_prev, f_prev = [], 0.0, 0.0
    for i in range(len(candles)):
        window = candles[max(0, i - lookback + 1): i + 1]
        hl2_vals = [(c["high"] + c["low"]) / 2 for c in window]
        HH = max(hl2_vals)
        LL = min(hl2_vals)
        hl2 = (candles[i]["high"] + candles[i]["low"]) / 2
        if HH != LL:
            v = 0.66 * (2 * ((hl2 - LL) / (HH - LL) - 0.5)) + 0.67 * v_prev
        else:
            v = v_prev
        v = max(min(v, 0.999), -0.999)
        f = 0.5 * math.log((1 + v) / (1 - v))
        out.append({
            "fisher":  f,
            "trigger": f_prev,
            "close":   candles[i]["close"],
            "time":    candles[i]["time"],
        })
        v_prev, f_prev = v, f
    return out


def _from_delta(lookback):
    """Fetch candles from Delta Exchange India — matches the chart exactly.
    Uses India API directly (api.india.delta.exchange) with resolution as-is (e.g. '1h').
    """
    import requests, time as _time
    now   = int(_time.time())
    start = now - 2000 * 3600  # 2000 candles for Fisher warm-up to match Delta chart
    url   = "https://api.india.delta.exchange/v2/history/candles"
    params = {"symbol": "ETHUSD", "resolution": RESOLUTION, "start": start, "end": now}
    # Fetch 2000 candles for proper Fisher warm-up (matches Delta Exchange chart values)
    r   = requests.get(url, params=params, timeout=10)
    raw = (r.json().get("result") or []) if r.status_code == 200 else []
    if not raw or len(raw) < lookback + 2:
        return None
    candles = sorted([
        {
            "time":  int(c["time"]) * 1000,   # seconds → milliseconds
            "open":  float(c["open"]),
            "high":  float(c["high"]),
            "low":   float(c["low"]),
            "close": float(c["close"]),
        }
        for c in raw
    ], key=lambda x: x["time"])
    return candles


def _from_ccxt(exchange_id, symbol, lookback):
    """Fetch candles from a ccxt exchange (fallback)."""
    exchange = getattr(ccxt, exchange_id)()
    bars = exchange.fetch_ohlcv(symbol, timeframe=RESOLUTION, limit=200)
    if not bars or len(bars) < lookback + 2:
        return None
    return [
        {"time": b[0], "open": b[1], "high": b[2], "low": b[3], "close": b[4]}
        for b in bars
    ]


def get_live_fisher_data(lookback_periods=9):
    """Return latest Fisher + Trigger from Delta Exchange price data.
    Falls back to other exchanges if Delta API is unavailable.
    """
    sources = [
        ("Delta Exchange", _from_delta,  None),
        ("KuCoin",         _from_ccxt,   ("kucoin",   "ETH/USDT")),
        ("Bybit",          _from_ccxt,   ("bybit",    "ETH/USDT")),
        ("OKX",            _from_ccxt,   ("okx",      "ETH/USDT")),
        ("Binance",        _from_ccxt,   ("binance",  "ETH/USDT")),
    ]

    for name, fn, args in sources:
        try:
            candles = fn(lookback_periods) if args is None else fn(*args, lookback_periods)
            if not candles:
                continue
            series = _compute_fisher(candles, lookback_periods)
            latest = series[-1]
            print(f"[v0] Fisher data source: {name}")
            return {
                "fisher":  latest["fisher"],
                "trigger": latest["trigger"],
                "close":   latest["close"],
                "time":    latest["time"],
            }
        except Exception as e:
            print(f"[v0] {name} failed: {e} — trying next source")
            continue

    print("[v0] All data sources failed")
    return None