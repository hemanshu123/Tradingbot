"""
Reverse-engineer Delta Exchange's exact Fisher Transform calculation
Test different formulas against Delta's chart values
"""

import requests
import time
import math
from datetime import datetime, timedelta

def fetch_delta_candles(limit=50):
    """Fetch candles from Delta Exchange"""
    now = int(time.time())
    start = now - limit * 3600
    url = "https://api.india.delta.exchange/v2/history/candles"
    params = {"symbol": "ETHUSD", "resolution": "1h", "start": start, "end": now}

    print(f"Fetching Delta candles...")
    r = requests.get(url, params=params, timeout=10)
    if r.status_code != 200:
        print(f"ERROR: {r.status_code}")
        return None

    raw = r.json().get("result") or []
    candles = sorted([
        {
            "time": int(c["time"]),
            "open": float(c["open"]),
            "high": float(c["high"]),
            "low": float(c["low"]),
            "close": float(c["close"]),
            "volume": float(c.get("volume", 0))
        }
        for c in raw
    ], key=lambda x: x["time"])

    print(f"Fetched {len(candles)} candles")
    return candles

# Test different Fisher formulas
def test_formula_1(candles, lookback=9):
    """Original: close price with 0.33 multiplier"""
    out = []
    v_prev = 0.0
    f_prev = 0.0
    for i in range(len(candles)):
        start = max(0, i - lookback + 1)
        window = candles[start:i+1]
        closes = [c["close"] for c in window]
        HH = max(closes)
        LL = min(closes)
        cl = candles[i]["close"]
        if HH != LL:
            x = (cl - LL) / (HH - LL)
            v = 0.33 * 2.0 * (x - 0.5) + 0.67 * v_prev
        else:
            v = v_prev
        v = max(min(v, 0.999), -0.999)
        f = 0.5 * math.log((1 + v) / (1 - v))
        out.append(f)
        v_prev = v
        f_prev = f
    return out

def test_formula_2(candles, lookback=9):
    """HL2 with 0.66 multiplier (what we tried before)"""
    out = []
    v_prev = 0.0
    f_prev = 0.0
    for i in range(len(candles)):
        start = max(0, i - lookback + 1)
        window = candles[start:i+1]
        hl2_vals = [(c["high"] + c["low"])/2 for c in window]
        HH = max(hl2_vals)
        LL = min(hl2_vals)
        hl2 = (candles[i]["high"] + candles[i]["low"]) / 2
        if HH != LL:
            v = 0.66 * (2 * ((hl2 - LL) / (HH - LL) - 0.5)) + 0.67 * v_prev
        else:
            v = v_prev
        v = max(min(v, 0.999), -0.999)
        f = 0.5 * math.log((1 + v) / (1 - v))
        out.append(f)
        v_prev = v
        f_prev = f
    return out

def test_formula_3(candles, lookback=14):
    """High + Low average with different lookback"""
    out = []
    v_prev = 0.0
    f_prev = 0.0
    for i in range(len(candles)):
        start = max(0, i - lookback + 1)
        window = candles[start:i+1]
        hl2_vals = [(c["high"] + c["low"])/2 for c in window]
        HH = max(hl2_vals)
        LL = min(hl2_vals)
        hl2 = (candles[i]["high"] + candles[i]["low"]) / 2
        if HH != LL:
            x = (hl2 - LL) / (HH - LL)
            v = 0.33 * 2.0 * (x - 0.5) + 0.67 * v_prev
        else:
            v = v_prev
        v = max(min(v, 0.999), -0.999)
        f = 0.5 * math.log((1 + v) / (1 - v))
        out.append(f)
        v_prev = v
        f_prev = f
    return out

def test_formula_4(candles, lookback=9):
    """Close price, different alpha (0.5 instead of 0.33)"""
    out = []
    v_prev = 0.0
    f_prev = 0.0
    for i in range(len(candles)):
        start = max(0, i - lookback + 1)
        window = candles[start:i+1]
        closes = [c["close"] for c in window]
        HH = max(closes)
        LL = min(closes)
        cl = candles[i]["close"]
        if HH != LL:
            x = (cl - LL) / (HH - LL)
            v = 0.5 * 2.0 * (x - 0.5) + 0.67 * v_prev
        else:
            v = v_prev
        v = max(min(v, 0.999), -0.999)
        f = 0.5 * math.log((1 + v) / (1 - v))
        out.append(f)
        v_prev = v
        f_prev = f
    return out

# Fetch data
candles = fetch_delta_candles(100)
if not candles:
    print("Failed to fetch candles")
    exit(1)

# Test all formulas
print("\n" + "="*80)
print("LAST 10 CANDLES - FISHER VALUES FROM EACH FORMULA")
print("="*80)

formula_1 = test_formula_1(candles, 9)
formula_2 = test_formula_2(candles, 9)
formula_3 = test_formula_3(candles, 14)
formula_4 = test_formula_4(candles, 9)

print(f"\n{'Idx':<4} {'Close':<10} {'Formula 1':<12} {'Formula 2':<12} {'Formula 3':<12} {'Formula 4':<12}")
print(f"{'':4} {'':10} {'Close+0.33':<12} {'HL2+0.66':<12} {'HL2(L=14)':<12} {'Close+0.5':<12}")
print("-" * 86)

for i in range(max(0, len(candles)-10), len(candles)):
    idx = i - max(0, len(candles)-10)
    print(f"{i:<4} {candles[i]['close']:<10.2f} {formula_1[i]:<12.4f} {formula_2[i]:<12.4f} {formula_3[i]:<12.4f} {formula_4[i]:<12.4f}")

# Check Delta's API directly for Fisher
print("\n" + "="*80)
print("CHECKING DELTA'S API FOR TECHNICAL INDICATORS")
print("="*80)

# Try to fetch indicators directly
try:
    url = "https://api.india.delta.exchange/v2/indicators"
    params = {"symbol": "ETHUSD", "resolution": "1h"}
    r = requests.get(url, params=params, timeout=10)
    if r.status_code == 200:
        data = r.json()
        print("Delta API provides technical indicators:")
        print(data)
    else:
        print(f"Indicators endpoint: {r.status_code} (not available)")
except Exception as e:
    print(f"Indicators endpoint error: {e}")

# Check market data endpoint
try:
    url = "https://api.india.delta.exchange/v2/products"
    params = {"ids": "3136"}  # ETHUSD
    r = requests.get(url, params=params, timeout=10)
    if r.status_code == 200:
        data = r.json()
        print("\nDelta product details:")
        print(data)
    else:
        print(f"Products endpoint: {r.status_code}")
except Exception as e:
    print(f"Products endpoint error: {e}")

print("\n" + "="*80)
print("RECOMMENDATION")
print("="*80)
print("If Delta's API doesn't provide Fisher directly:")
print("1. The chart likely uses TradingView's Fisher Transform")
print("2. TradingView uses close price with specific parameters")
print("3. We should test against recent chart screenshots to reverse-engineer exact params")
print("\nTo verify: Screenshot Delta chart showing Fisher values, note exact numbers,")
print("then match one of the formulas above to those exact values.")