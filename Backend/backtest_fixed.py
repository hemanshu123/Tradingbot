"""
Backtest with FIXED Fisher (using close-price formula)
Compare: HL2 formula (-630% P&L) vs Original formula (expected: positive)
"""

import ccxt
import time
import math
from datetime import datetime, timedelta
from decimal import Decimal

# FIXED Fisher (original, using close price)
def compute_fisher_fixed(candles, lookback=9):
    out = []
    v_prev = 0.0
    fisher_prev = 0.0

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

def backtest(candles, leverage=10, tp_pct=0.60, sl_pct=0.15):
    fisher_data = compute_fisher_fixed(candles, 9)

    trades = []
    position = None
    min_spread = 0.05
    cooldown = 0
    sl_cd_bars = 5

    for i in range(1, len(fisher_data)):
        cf = fisher_data[i]["fisher"]
        ct = fisher_data[i]["trigger"]
        pf = fisher_data[i-1]["fisher"]
        pt = fisher_data[i-1]["trigger"]
        px = fisher_data[i]["close"]
        h = fisher_data[i]["high"]
        l = fisher_data[i]["low"]

        if cooldown > 0:
            cooldown -= 1

        # Check TP/SL
        if position:
            s, tp, sl, ep = position["side"], position["tp"], position["sl"], position["entry"]
            hit_tp = (s=="buy" and h>=tp) or (s=="sell" and l<=tp)
            hit_sl = (s=="buy" and l<=sl) or (s=="sell" and h>=sl)

            if hit_tp or hit_sl:
                reason = "TP" if hit_tp else "SL"
                exit_px = tp if hit_tp else sl
                raw_pct = (exit_px - ep) / ep
                pnl_pct = raw_pct * leverage * 100
                trades.append({
                    "side": s, "entry": ep, "exit": exit_px,
                    "pnl_pct": pnl_pct, "reason": reason
                })
                position = None
                if reason == "SL":
                    cooldown = sl_cd_bars

        # Check signal
        if position is None and cooldown == 0 and abs(cf-ct) >= min_spread:
            co = detect_crossover(cf, ct, pf, pt)
            if co == "above" and cf<0 and ct<0:
                tp, sl = tp_sl(px, "buy", leverage, tp_pct, sl_pct)
                position = {"side": "buy", "entry": px, "tp": tp, "sl": sl}
            elif co == "below" and cf>0 and ct>0:
                tp, sl = tp_sl(px, "sell", leverage, tp_pct, sl_pct)
                position = {"side": "sell", "entry": px, "tp": tp, "sl": sl}

    return trades

if __name__ == "__main__":
    print("="*70)
    print("BACKTEST: Fixed Fisher Transform (using close-price formula)")
    print("="*70)

    candles = fetch_data(days=180)
    trades = backtest(candles, leverage=10)

    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] < 0]
    total_pnl = sum(t["pnl_pct"] for t in trades)

    print(f"\nResults (10x leverage, 1h candles, 6 months):")
    print(f"  Total Trades:    {len(trades)}")
    print(f"  Wins:            {len(wins)}")
    print(f"  Losses:          {len(losses)}")
    print(f"  Win Rate:        {len(wins)/len(trades)*100:.1f}% ({len(wins)}/{len(trades)})" if trades else "Win Rate:        N/A")
    print(f"  Avg Win:         {sum(t['pnl_pct'] for t in wins)/len(wins):+.2f}%" if wins else "Avg Win:         N/A")
    print(f"  Avg Loss:        {sum(t['pnl_pct'] for t in losses)/len(losses):+.2f}%" if losses else "Avg Loss:        N/A")
    print(f"  Best Trade:      {max(t['pnl_pct'] for t in trades):+.2f}%" if trades else "Best Trade:      N/A")
    print(f"  Worst Trade:     {min(t['pnl_pct'] for t in trades):+.2f}%" if trades else "Worst Trade:     N/A")
    print(f"  Total P&L:       {total_pnl:+.2f}%")

    print(f"\n{'='*70}")
    if total_pnl > 0:
        print(f"SUCCESS: Strategy is profitable with fixed formula!")
        print(f"  Previous (HL2): -630.00%")
        print(f"  Fixed (close):  {total_pnl:+.2f}%")
    elif total_pnl < -200:
        print(f"STILL NEGATIVE: Strategy still not working. Need further investigation.")
    else:
        print(f"MIXED: Some improvement but not fully profitable yet.")
    print(f"{'='*70}")