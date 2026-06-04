"""
Fisher Transform Debug: Why are values hitting -3.8002 / +3.8002 constantly?
Compare our calculation with Delta Exchange's actual values
"""

import ccxt
import time
import math
from datetime import datetime, timedelta
from bot.fisher_transform import get_live_fisher_data

# Fetch last 100 candles and compute Fisher step-by-step
exchange = ccxt.binance()
now = int(datetime.now().timestamp() * 1000)
since = now - (100 * 3600 * 1000)  # 100 hours back

print("Fetching 100 hours of 1h ETH data...")
bars = []
temp_since = since
while temp_since < now:
    b = exchange.fetch_ohlcv("ETH/USDT", "1h", since=temp_since, limit=100)
    if not b:
        break
    bars.extend(b)
    temp_since = b[-1][0] + 1000
    time.sleep(0.2)

candles = [
    {"time": b[0], "open": b[1], "high": b[2], "low": b[3], "close": b[4]}
    for b in bars
]
print(f"Fetched {len(candles)} candles")

# Compute Fisher with DETAILED STEP-BY-STEP
print("\n" + "="*80)
print("FISHER CALCULATION DEBUG (Last 20 candles)")
print("="*80)

# Use our exact HL2 formula
def compute_fisher_debug(candles, lookback=9):
    out = []
    v_prev = 0.0
    fisher_prev = 0.0

    for i in range(len(candles)):
        start = max(0, i - lookback + 1)
        window = candles[start:i+1]

        # HL2 formula
        hl2_vals = [(c["high"] + c["low"])/2 for c in window]
        HH = max(hl2_vals)
        LL = min(hl2_vals)
        hl2 = (candles[i]["high"] + candles[i]["low"]) / 2

        if HH != LL:
            v = 0.66 * (2 * ((hl2 - LL)/(HH - LL) - 0.5)) + 0.67 * v_prev
        else:
            v = v_prev

        v_raw = v  # save before clipping
        v = max(min(v, 0.999), -0.999)  # CLIPPING

        # Log calculation
        f = 0.5 * math.log((1 + v) / (1 - v))

        out.append({
            "time": candles[i]["time"],
            "close": candles[i]["close"],
            "hl2": hl2,
            "HH": HH,
            "LL": LL,
            "v_raw": v_raw,
            "v_clipped": v,
            "fisher": f,
            "trigger": fisher_prev
        })

        v_prev = v
        fisher_prev = f

    return out

series = compute_fisher_debug(candles, 9)

# Show last 20 candles with details
print(f"\n{'Idx':<4} {'Close':<10} {'HL2':<10} {'HH-LL':<10} {'v_raw':<8} {'v_clipped':<10} {'Fisher':<10} {'Trigger':<10}")
print("-" * 82)

for i in range(max(0, len(series)-20), len(series)):
    s = series[i]
    print(f"{i:<4} {s['close']:<10.2f} {s['hl2']:<10.2f} {s['HH']-s['LL']:<10.2f} "
          f"{s['v_raw']:<8.4f} {s['v_clipped']:<10.4f} {s['fisher']:<10.4f} {s['trigger']:<10.4f}")

# Check how many times v gets clipped
clipped_count = sum(1 for s in series if abs(s['v_raw']) > 0.999)
print(f"\nV clipping analysis:")
print(f"  Total candles: {len(series)}")
print(f"  Clipped to ±0.999: {clipped_count} times ({clipped_count/len(series)*100:.1f}%)")

# Check how many extreme Fisher values
extreme_count = sum(1 for s in series if abs(s['fisher']) > 3.0)
print(f"  Fisher > 3.0 or < -3.0: {extreme_count} times")

# Compare with live data
print(f"\n" + "="*80)
print("COMPARING WITH LIVE DATA")
print("="*80)

live_data = get_live_fisher_data(9)
if live_data:
    print(f"Live Fisher:  {live_data['fisher']:.4f}")
    print(f"Live Trigger: {live_data['trigger']:.4f}")
    print(f"Live Close:   ${live_data['close']:.2f}")
    print(f"Spread:       {abs(live_data['fisher']-live_data['trigger']):.4f}")

    # Show what Delta Exchange shows
    print(f"\nExpected (from Delta chart):")
    print(f"  Fisher should be in range: -2.0 to +2.0")
    print(f"  Trigger should be different from Fisher")
    print(f"  Spread should be > 0.05")

    if abs(live_data['fisher']) > 3.0:
        print(f"\n!!! PROBLEM: Fisher is at extreme ({live_data['fisher']:.4f})")
        print(f"    This causes spread = {abs(live_data['fisher']-live_data['trigger']):.4f}")
        print(f"    Min spread filter = 0.05, so NO TRADES WILL FIRE")

# Analysis
print(f"\n" + "="*80)
print("DIAGNOSIS")
print("="*80)
if clipped_count > len(series) * 0.5:
    print(f"ISSUE FOUND: v values are being clipped {clipped_count/len(series)*100:.0f}% of the time")
    print(f"  This means the normalization formula is producing extreme values")
    print(f"  When v is clipped to ±0.999:")
    print(f"    log((1+0.999)/(1-0.999)) = log(1.999/0.001) = log(1999) ≈ 3.8")
    print(f"  This is why Fisher constantly hits -3.8 to +3.8")
    print()
    print(f"POSSIBLE FIXES:")
    print(f"  1. Use a different formula that doesn't clip as much")
    print(f"  2. Use close price instead of HL2 (what old backtest used)")
    print(f"  3. Adjust the 0.66 multiplier in the v formula")
else:
    print(f"No excessive clipping. The formula seems OK.")
    print(f"Check if trigger is being calculated correctly.")