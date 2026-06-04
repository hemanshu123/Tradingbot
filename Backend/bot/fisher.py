from typing import List, Dict
import math

def compute_fisher_series(candles: List[Dict], lookback: int):
    if len(candles) < lookback + 2:
        return []

    out = []
    v_prev = 0.0
    fisher_prev = 0.0

    for i in range(len(candles)):
        start = max(0, i - lookback + 1)
        window = candles[start:i+1]
        highs = [float(c["high"]) for c in window]
        lows  = [float(c["low"]) for c in window]
        HH = max(highs)
        LL = min(lows)
        close = float(candles[i]["close"])

        if HH != LL:
            x = (close - LL) / (HH - LL)
            value = 0.33 * 2.0 * (x - 0.5) + 0.67 * v_prev
        else:
            value = v_prev

        value = max(min(value, 0.999), -0.999)

        fisher = 0.5 * math.log((1 + value) / (1 - value))
        trigger = fisher_prev

        out.append({"time": candles[i].get("time"), "close": close, "fisher": fisher, "trigger": trigger})

        v_prev = value
        fisher_prev = fisher

    return out
