"""
Backtest Diagnostic: Debug why strategy is losing money
Shows detailed trade analysis, signal detection, and TP/SL execution
"""

import ccxt
import time
import math
from datetime import datetime, timedelta
from decimal import Decimal

# ── Fisher Transform (HL2 formula) ──────────────────────────────────────────
def compute_fisher_hl2(candles, lookback=9):
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

        v = max(min(v, 0.999), -0.999)
        f = 0.5 * math.log((1 + v)/(1 - v))

        out.append({
            "time": candles[i]["time"],
            "close": candles[i]["close"],
            "high": candles[i]["high"],
            "low": candles[i]["low"],
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

def fetch_data(symbol="ETH/USDT", timeframe="1h", days=180):
    exchange = ccxt.binance()
    end_ms = int(datetime.now().timestamp() * 1000)
    start_ms = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)

    print(f"Fetching {symbol} {timeframe}...")
    all_bars = []
    since = start_ms

    while since < end_ms:
        bars = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not bars: break
        all_bars.extend(bars)
        since = bars[-1][0] + 1
        time.sleep(0.2)
        if bars[-1][0] >= end_ms: break

    candles = [
        {"time": b[0], "open": b[1], "high": b[2], "low": b[3], "close": b[4]}
        for b in all_bars
    ]
    print(f"Fetched {len(candles):,} candles")
    return candles

# ── Backtest with detailed trade logging ────────────────────────────────────
def backtest_detailed(candles, leverage=10, tp_pct=0.60, sl_pct=0.15):
    fisher_data = compute_fisher_hl2(candles, 9)

    trades = []
    position = None
    min_spread = 0.05
    cooldown = 0
    sl_cd_bars = 5
    signal_count = 0

    print("\nStarting backtest...")
    print(f"  Leverage: {leverage}x")
    print(f"  TP: {tp_pct*100:.0f}% | SL: {sl_pct*100:.0f}%")
    print(f"  Min Spread: {min_spread}")
    print()

    for i in range(1, len(fisher_data)):
        cf = fisher_data[i]["fisher"]
        ct = fisher_data[i]["trigger"]
        pf = fisher_data[i-1]["fisher"]
        pt = fisher_data[i-1]["trigger"]
        px = fisher_data[i]["close"]
        h = fisher_data[i]["high"]
        l = fisher_data[i]["low"]

        # Cooldown
        if cooldown > 0:
            cooldown -= 1

        # Check TP/SL
        if position:
            s, tp, sl, ep, entry_idx = (position["side"], position["tp"], position["sl"],
                                         position["entry"], position["entry_idx"])
            hit_tp = (s=="buy" and h>=tp) or (s=="sell" and l<=tp)
            hit_sl = (s=="buy" and l<=sl) or (s=="sell" and h>=sl)

            if hit_tp or hit_sl:
                reason = "TP" if hit_tp else "SL"
                exit_px = tp if hit_tp else sl
                raw_pct = (exit_px - ep) / ep
                pnl_pct = raw_pct * leverage * 100

                trade = {
                    "no": len(trades) + 1,
                    "entry_idx": entry_idx,
                    "exit_idx": i,
                    "candles_held": i - entry_idx,
                    "side": s,
                    "entry": round(ep, 2),
                    "exit": round(exit_px, 2),
                    "tp": round(tp, 2),
                    "sl": round(sl, 2),
                    "reason": reason,
                    "pnl_pct": round(pnl_pct, 2)
                }
                trades.append(trade)

                print(f"Trade {len(trades):3d} | {s.upper():4s} {entry_idx}->{i} | "
                      f"Entry: ${ep:.2f} | Exit: ${exit_px:.2f} ({reason}) | "
                      f"P&L: {pnl_pct:+7.2f}%")

                position = None
                if reason == "SL":
                    cooldown = sl_cd_bars

        # Check signal
        if position is None and cooldown == 0 and abs(cf-ct) >= min_spread:
            co = detect_crossover(cf, ct, pf, pt)
            if co:
                signal_count += 1
                fisher_zone = "negative" if cf < 0 else "positive"
                trigger_zone = "negative" if ct < 0 else "positive"

                if co == "above" and cf<0 and ct<0:
                    tp, sl = tp_sl(px, "buy", leverage, tp_pct, sl_pct)
                    position = {"side": "buy", "entry": px, "tp": tp, "sl": sl, "entry_idx": i}
                    print(f"  >>> SIGNAL {signal_count}: BUY (Fisher crosses above, both negative)")
                    print(f"      Fisher: {pf:.4f}->{cf:.4f} | Trigger: {pt:.4f}->{ct:.4f}")
                    print(f"      Entry: ${px:.2f} | TP: ${tp:.2f} | SL: ${sl:.2f}")

                elif co == "below" and cf>0 and ct>0:
                    tp, sl = tp_sl(px, "sell", leverage, tp_pct, sl_pct)
                    position = {"side": "sell", "entry": px, "tp": tp, "sl": sl, "entry_idx": i}
                    print(f"  >>> SIGNAL {signal_count}: SELL (Fisher crosses below, both positive)")
                    print(f"      Fisher: {pf:.4f}->{cf:.4f} | Trigger: {pt:.4f}->{ct:.4f}")
                    print(f"      Entry: ${px:.2f} | TP: ${tp:.2f} | SL: ${sl:.2f}")

    return trades, signal_count

if __name__ == "__main__":
    print("="*80)
    print("BACKTEST DIAGNOSTIC: Strategy Performance Analysis")
    print("="*80)

    candles = fetch_data(days=180)

    print("\n" + "="*80)
    print("RUNNING DETAILED BACKTEST (showing first 20 signals/trades)...")
    print("="*80)

    trades, signal_count = backtest_detailed(candles, leverage=10, tp_pct=0.60, sl_pct=0.15)

    # Analysis
    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] < 0]
    total_pnl = sum(t["pnl_pct"] for t in trades)

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Signals Generated:   {signal_count}")
    print(f"Total Trades:        {len(trades)}")
    print(f"  Wins (TP):         {len([t for t in trades if t['reason']=='TP'])}")
    print(f"  Losses (SL):       {len([t for t in trades if t['reason']=='SL'])}")
    print(f"Win Rate:            {len(wins)/len(trades)*100:.1f}% ({len(wins)}/{len(trades)})")
    print(f"Avg Win:             {sum(t['pnl_pct'] for t in wins)/len(wins):+.2f}%" if wins else "Avg Win:             N/A")
    print(f"Avg Loss:            {sum(t['pnl_pct'] for t in losses)/len(losses):+.2f}%" if losses else "Avg Loss:            N/A")
    print(f"Best Trade:          {max(t['pnl_pct'] for t in trades):+.2f}%")
    print(f"Worst Trade:         {min(t['pnl_pct'] for t in trades):+.2f}%")
    print(f"Total P&L:           {total_pnl:+.2f}%")

    print("\n" + "="*80)
    print("DIAGNOSIS")
    print("="*80)

    if len(losses) > len(wins):
        print(f"WARNING: More losses ({len(losses)}) than wins ({len(wins)})")
        print(f"  - Win rate is only {len(wins)/len(trades)*100:.1f}%")
        print(f"  - Average loss ({sum(t['pnl_pct'] for t in losses)/len(losses):+.2f}%) is worse than avg win")
        print(f"\n  Possible causes:")
        print(f"    1. Signals are being generated at bad times (trend exhaustion)")
        print(f"    2. TP is too small ({0.60*100:.0f}% at {10}x = {0.60/10*100:.1f}% move)")
        print(f"    3. SL is getting hit too easily ({0.15*100:.0f}% at {10}x = {0.15/10*100:.1f}% move)")
        print(f"    4. Market conditions changed (backtest from 6 months ago, conditions now different)")

    avg_hold = sum(t["candles_held"] for t in trades) / len(trades) if trades else 0
    print(f"\nAverage candles held per trade: {avg_hold:.1f}")
    if avg_hold < 2:
        print(f"  -> Trades closing very quickly (whipsaws?)")

    print("\n" + "="*80)