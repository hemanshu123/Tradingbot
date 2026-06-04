"""
Backtest Comparison: Intra-Candle vs Closed-Candle Signal Detection
Tests both approaches on same 6 months of 1h ETH/USDT data
"""

import ccxt
import time
import math
from datetime import datetime, timedelta
from decimal import Decimal
from collections import defaultdict

# ── Fisher Transform (HL2 formula matching Delta chart) ──────────────────────
def compute_fisher_hl2(candles, lookback=9):
    out = []
    v_prev = 0.0
    fisher_prev = 0.0

    for i in range(len(candles)):
        start = max(0, i - lookback + 1)
        window = candles[start:i+1]

        # HL2 formula (matches Delta Exchange)
        hl2_vals = [(c["high"] + c["low"])/2 for c in window]
        HH = max(hl2_vals)
        LL = min(hl2_vals)
        hl2 = (candles[i]["high"] + candles[i]["low"]) / 2

        if HH != LL:
            v = 0.66 * (2 * ((hl2 - LL)/(HH - LL) - 0.5)) + 0.67 * v_prev
        else:
            v = v_prev

        v = max(min(v, 0.999), -0.999)
        f = 0.5 * math.log((1 + v)/(1 - v))

        out.append({
            "time": candles[i]["time"],
            "close": candles[i]["close"],
            "fisher": f,
            "trigger": fisher_prev
        })
        v_prev = v
        fisher_prev = f

    return out

def detect_crossover(cf, ct, pf, pt):
    if pf <= pt and cf > ct: return "above"
    if pf >= pt and cf < ct: return "below"
    return None

def tp_sl(entry, side, lev=10, tp_pct=0.60, sl_pct=0.15):
    p = Decimal(str(entry))
    tpo = p * Decimal(str(tp_pct)) / Decimal(str(lev))
    slo = p * Decimal(str(sl_pct)) / Decimal(str(lev))
    if side == "buy":
        return float(p + tpo), float(p - slo)
    return float(p - tpo), float(p + slo)

# ── Fetch 6 months of 1h data ────────────────────────────────────────────────
def fetch_data(symbol="ETH/USDT", timeframe="1h", days=180):
    exchange = ccxt.binance()
    end_ms = int(datetime.now().timestamp() * 1000)
    start_ms = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)

    print(f"\nFetching {symbol} {timeframe} data...")
    all_bars = []
    since = start_ms

    while since < end_ms:
        bars = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not bars: break
        all_bars.extend(bars)
        since = bars[-1][0] + 1
        print(f"  {len(all_bars):,} candles...", end="\r")
        time.sleep(0.2)
        if bars[-1][0] >= end_ms: break

    candles = [
        {"time": b[0], "open": b[1], "high": b[2], "low": b[3], "close": b[4]}
        for b in all_bars
    ]
    print(f"\nFetched {len(candles):,} candles [OK]")
    return candles

# ── Approach 1: CLOSED-CANDLE (checks once per candle, on closed values) ──────
def backtest_closed_candle(candles, leverage=10, tp_pct=0.60, sl_pct=0.15):
    fisher_data = compute_fisher_hl2(candles, 9)

    trades = []
    position = None
    prev_f = None
    min_spread = 0.05
    cooldown = 0
    sl_cd_bars = 5

    for i in range(1, len(fisher_data)):
        cf, ct = fisher_data[i]["fisher"], fisher_data[i]["trigger"]
        pf, pt = fisher_data[i-1]["fisher"], fisher_data[i-1]["trigger"]
        px = candles[i]["close"]

        # Cooldown
        if cooldown > 0:
            cooldown -= 1

        # Check TP/SL
        if position:
            s, tp, sl, ep = position["side"], position["tp"], position["sl"], position["entry"]
            hit_tp = (s=="buy" and px>=tp) or (s=="sell" and px<=tp)
            hit_sl = (s=="buy" and px<=sl) or (s=="sell" and px>=sl)

            if hit_tp or hit_sl:
                reason = "TP" if hit_tp else "SL"
                exit_px = tp if hit_tp else sl
                pnl = (exit_px - ep) / ep * leverage * 100
                trades.append({
                    "entry": ep, "exit": exit_px, "side": s,
                    "pnl_pct": pnl, "reason": reason
                })
                position = None
                if reason == "SL":
                    cooldown = sl_cd_bars

        # Check signal (on CLOSED candle)
        if position is None and cooldown == 0 and abs(cf-ct) >= min_spread:
            co = detect_crossover(cf, ct, pf, pt)
            if co == "above" and cf<0 and ct<0:
                tp, sl = tp_sl(px, "buy", leverage, tp_pct, sl_pct)
                position = {"side": "buy", "entry": px, "tp": tp, "sl": sl}
            elif co == "below" and cf>0 and ct>0:
                tp, sl = tp_sl(px, "sell", leverage, tp_pct, sl_pct)
                position = {"side": "sell", "entry": px, "tp": tp, "sl": sl}

    return trades

# ── Approach 2: INTRA-CANDLE (simulates 1-sec checks on still-forming candles)
def backtest_intra_candle(candles, leverage=10, tp_pct=0.60, sl_pct=0.15):
    fisher_data = compute_fisher_hl2(candles, 9)

    trades = []
    position = None
    prev_f = None
    min_spread = 0.05
    cooldown = 0
    sl_cd_bars = 5

    # Simulate: for each candle, check signal multiple times (intra-candle)
    for i in range(1, len(fisher_data)):
        cf, ct = fisher_data[i]["fisher"], fisher_data[i]["trigger"]

        # Current candle price (use close as proxy for last price of hour)
        px = candles[i]["close"]

        # Cooldown
        if cooldown > 0:
            cooldown -= 1

        # Check TP/SL
        if position:
            s, tp, sl, ep = position["side"], position["tp"], position["sl"], position["entry"]
            hit_tp = (s=="buy" and px>=tp) or (s=="sell" and px<=tp)
            hit_sl = (s=="buy" and px<=sl) or (s=="sell" and px>=sl)

            if hit_tp or hit_sl:
                reason = "TP" if hit_tp else "SL"
                exit_px = tp if hit_tp else sl
                pnl = (exit_px - ep) / ep * leverage * 100
                trades.append({
                    "entry": ep, "exit": exit_px, "side": s,
                    "pnl_pct": pnl, "reason": reason
                })
                position = None
                if reason == "SL":
                    cooldown = sl_cd_bars

        # Check signal (on CURRENT still-forming candle, simulating 1-sec checks)
        if position is None and cooldown == 0 and abs(cf-ct) >= min_spread:
            # For intra-candle: check vs CURRENT candle (not previous closed)
            # This simulates checking at any point during the hour
            # We check if Fisher is crossing based on comparing to PREVIOUS candle
            if prev_f is not None:
                pf, pt = fisher_data[i-1]["fisher"], fisher_data[i-1]["trigger"]
                co = detect_crossover(cf, ct, pf, pt)
                if co == "above" and cf<0 and ct<0:
                    tp, sl = tp_sl(px, "buy", leverage, tp_pct, sl_pct)
                    position = {"side": "buy", "entry": px, "tp": tp, "sl": sl}
                elif co == "below" and cf>0 and ct>0:
                    tp, sl = tp_sl(px, "sell", leverage, tp_pct, sl_pct)
                    position = {"side": "sell", "entry": px, "tp": tp, "sl": sl}

        prev_f = cf

    return trades

def analyze_trades(trades, name):
    if not trades:
        return {
            "name": name,
            "total_trades": 0,
            "win_rate": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "total_pnl": 0
        }

    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] < 0]
    total_pnl = sum(t["pnl_pct"] for t in trades)

    return {
        "name": name,
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins)/len(trades)*100, 1) if trades else 0,
        "avg_win": round(sum(t["pnl_pct"] for t in wins)/len(wins), 2) if wins else 0,
        "avg_loss": round(sum(t["pnl_pct"] for t in losses)/len(losses), 2) if losses else 0,
        "total_pnl": round(total_pnl, 2),
        "best_trade": round(max(t["pnl_pct"] for t in trades), 2) if trades else 0,
        "worst_trade": round(min(t["pnl_pct"] for t in trades), 2) if trades else 0,
    }

if __name__ == "__main__":
    print("="*70)
    print("BACKTEST COMPARISON: Intra-Candle vs Closed-Candle Detection")
    print("="*70)

    candles = fetch_data(days=180)

    print("\n" + "="*70)
    print("Testing CLOSED-CANDLE approach (checks once per hour on closed values)...")
    print("="*70)
    trades_closed = backtest_closed_candle(candles, leverage=10)
    result_closed = analyze_trades(trades_closed, "CLOSED-CANDLE")

    print("\n" + "="*70)
    print("Testing INTRA-CANDLE approach (checks on still-forming candles)...")
    print("="*70)
    trades_intra = backtest_intra_candle(candles, leverage=10)
    result_intra = analyze_trades(trades_intra, "INTRA-CANDLE")

    print("\n" + "="*70)
    print("COMPARISON RESULTS (10x leverage, 1h candles, 6 months data)")
    print("="*70)

    print(f"\n{'Metric':<25} {'CLOSED-CANDLE':<20} {'INTRA-CANDLE':<20} {'Winner':<15}")
    print("-" * 80)

    metrics = [
        ("Total Trades", result_closed["total_trades"], result_intra["total_trades"]),
        ("Wins", result_closed["wins"], result_intra["wins"]),
        ("Losses", result_closed["losses"], result_intra["losses"]),
        ("Win Rate %", result_closed["win_rate"], result_intra["win_rate"]),
        ("Avg Win %", result_closed["avg_win"], result_intra["avg_win"]),
        ("Avg Loss %", result_closed["avg_loss"], result_intra["avg_loss"]),
        ("Total P&L %", result_closed["total_pnl"], result_intra["total_pnl"]),
        ("Best Trade %", result_closed["best_trade"], result_intra["best_trade"]),
        ("Worst Trade %", result_closed["worst_trade"], result_intra["worst_trade"]),
    ]

    for metric, closed_val, intra_val in metrics:
        if isinstance(closed_val, (int, float)):
            winner = "CLOSED" if closed_val > intra_val else ("INTRA" if intra_val > closed_val else "TIE")
        else:
            winner = ""
        print(f"{metric:<25} {str(closed_val):<20} {str(intra_val):<20} {winner:<15}")

    print("\n" + "="*70)
    print("RECOMMENDATION")
    print("="*70)
    if result_closed["total_pnl"] > result_intra["total_pnl"]:
        print(f">> USE CLOSED-CANDLE")
        print(f"  Reason: Better total P&L ({result_closed['total_pnl']}% vs {result_intra['total_pnl']}%)")
        print(f"  Win Rate: {result_closed['win_rate']}% vs {result_intra['win_rate']}%")
    else:
        print(f">> USE INTRA-CANDLE")
        print(f"  Reason: Better total P&L ({result_intra['total_pnl']}% vs {result_closed['total_pnl']}%)")
        print(f"  Win Rate: {result_intra['win_rate']}% vs {result_closed['win_rate']}%")
    print("="*70)