"""
Backtest: Fisher Transform Crossover + Zone Filter
Strategy matches run_bot.py exactly.
Data: ETH/USDT 15m candles from Binance (last 6 months)
"""

import ccxt
import time
import math
from datetime import datetime, timedelta
from decimal import Decimal
from collections import defaultdict


# ── Fisher Transform (pure Python, matches bot/fisher.py) ──────────────────
def compute_fisher_series(candles, lookback=9):
    out = []
    v_prev = 0.0
    fisher_prev = 0.0

    for i in range(len(candles)):
        start = max(0, i - lookback + 1)
        window = candles[start : i + 1]
        highs = [c["high"] for c in window]
        lows = [c["low"] for c in window]
        HH = max(highs)
        LL = min(lows)
        close = candles[i]["close"]

        if HH != LL:
            x = (close - LL) / (HH - LL)
            value = 0.33 * 2.0 * (x - 0.5) + 0.67 * v_prev
        else:
            value = v_prev

        value = max(min(value, 0.999), -0.999)
        fisher = 0.5 * math.log((1 + value) / (1 - value))
        trigger = fisher_prev

        out.append({"time": candles[i]["time"], "close": close, "fisher": fisher, "trigger": trigger})

        v_prev = value
        fisher_prev = fisher

    return out


# ── Crossover detection (exact copy of run_bot.py logic) ───────────────────
FLOAT_TOLERANCE = 0.001

def detect_crossover(current_fisher, current_trigger, prev_fisher, prev_trigger):
    if prev_fisher <= prev_trigger and current_fisher > current_trigger:
        return "fisher_above"
    elif prev_fisher >= prev_trigger and current_fisher < current_trigger:
        return "fisher_below"
    elif (
        abs(current_fisher - current_trigger) <= FLOAT_TOLERANCE
        and abs(prev_fisher - prev_trigger) > FLOAT_TOLERANCE
    ):
        return "fisher_above" if current_fisher > current_trigger else "fisher_below"
    return None


# ── TP/SL calculation (exact copy of run_bot.py) ───────────────────────────
def calculate_tp_sl(entry_price, side, leverage=30, tp_pct=0.1375, sl_pct=0.15):
    price = Decimal(str(entry_price))
    tp_offset = price * Decimal(str(tp_pct)) / Decimal(str(leverage))
    sl_offset = price * Decimal(str(sl_pct)) / Decimal(str(leverage))
    if side == "buy":
        tp = price + tp_offset
        sl = price - sl_offset
    else:
        tp = price - tp_offset
        sl = price + sl_offset
    return round(float(tp), 4), round(float(sl), 4)


# ── Fetch 6 months of 15m Binance candles ──────────────────────────────────
def fetch_historical_data(symbol="ETH/USDT", timeframe="15m", days=180):
    exchange = ccxt.binance()
    end_ms = int(datetime.now().timestamp() * 1000)
    start_ms = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)

    print(f"\nFetching {symbol} {timeframe} data ...")
    print(f"  From : {datetime.fromtimestamp(start_ms/1000).strftime('%Y-%m-%d')}")
    print(f"  To   : {datetime.fromtimestamp(end_ms/1000).strftime('%Y-%m-%d')}")

    all_bars = []
    since = start_ms

    while since < end_ms:
        bars = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not bars:
            break
        all_bars.extend(bars)
        since = bars[-1][0] + 1
        print(f"  Fetched {len(all_bars):,} candles...", end="\r")
        time.sleep(0.25)
        if bars[-1][0] >= end_ms:
            break

    candles = [
        {"time": b[0], "open": b[1], "high": b[2], "low": b[3], "close": b[4], "volume": b[5]}
        for b in all_bars
        if b[0] <= end_ms
    ]
    print(f"\n  Total candles fetched: {len(candles):,}")
    return candles


# ── Backtest engine ─────────────────────────────────────────────────────────
def backtest(candles, lookback=9, leverage=30, tp_pct=0.1375, sl_pct=0.15):
    print(f"\nComputing Fisher Transform (lookback={lookback})...")
    series = compute_fisher_series(candles, lookback)

    trades = []
    open_pos = None
    last_signal = None

    for i in range(1, len(series)):
        curr = series[i]
        prev = series[i - 1]

        c_fisher  = round(curr["fisher"],  6)
        c_trigger = round(curr["trigger"], 6)
        p_fisher  = round(prev["fisher"],  6)
        p_trigger = round(prev["trigger"], 6)
        price = curr["close"]

        # ── Check TP/SL on open position ───────────────────────────────────
        if open_pos:
            side = open_pos["side"]
            tp   = open_pos["tp"]
            sl   = open_pos["sl"]
            ep   = open_pos["entry_price"]

            hit_tp = (side == "buy"  and price >= tp) or (side == "sell" and price <= tp)
            hit_sl = (side == "buy"  and price <= sl) or (side == "sell" and price >= sl)

            if hit_tp or hit_sl:
                exit_px = tp if hit_tp else sl
                reason  = "TP" if hit_tp else "SL"
                # P&L as % of margin (leverage applied)
                raw_pct = (exit_px - ep) / ep * (1 if side == "buy" else -1)
                pnl_pct = raw_pct * leverage  # e.g. 0.004583 * 30 = 0.1375

                trades.append({
                    "side":        side,
                    "entry_price": ep,
                    "exit_price":  exit_px,
                    "reason":      reason,
                    "pnl_pct":     pnl_pct,      # fraction (0.1375 = 13.75%)
                    "entry_time":  datetime.fromtimestamp(open_pos["time"] / 1000),
                    "exit_time":   datetime.fromtimestamp(curr["time"] / 1000),
                })
                open_pos   = None
                last_signal = None

        # ── Detect signal ───────────────────────────────────────────────────
        signal = None
        crossover = detect_crossover(c_fisher, c_trigger, p_fisher, p_trigger)
        if crossover:
            if crossover == "fisher_above" and c_fisher < 0 and c_trigger < 0:
                signal = "buy"
            elif crossover == "fisher_below" and c_fisher > 0 and c_trigger > 0:
                signal = "sell"

        # ── Open position ───────────────────────────────────────────────────
        if signal and not open_pos and signal != last_signal:
            tp, sl = calculate_tp_sl(price, signal, leverage, tp_pct, sl_pct)
            open_pos = {
                "side":        signal,
                "entry_price": price,
                "tp":          tp,
                "sl":          sl,
                "time":        curr["time"],
            }
            last_signal = signal

    return trades


# ── Report ──────────────────────────────────────────────────────────────────
def report(trades, capital_rs=10000, leverage=30, tp_pct=0.1375, sl_pct=0.15):
    SEP = "=" * 65

    if not trades:
        print("No trades found — strategy never triggered.")
        return

    wins   = [t for t in trades if t["reason"] == "TP"]
    losses = [t for t in trades if t["reason"] == "SL"]

    win_rate  = len(wins) / len(trades) * 100
    avg_win   = sum(t["pnl_pct"] for t in wins)   / len(wins)   if wins   else 0
    avg_loss  = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0
    total_pnl = sum(t["pnl_pct"] for t in trades)   # sum of fractional P&L per trade

    # Breakeven win rate: wins × avg_win + losses × avg_loss = 0
    # w * avg_win - (1-w) * |avg_loss| = 0  => w = |avg_loss| / (avg_win + |avg_loss|)
    breakeven_wr = abs(avg_loss) / (avg_win + abs(avg_loss)) * 100 if (avg_win + abs(avg_loss)) else 50

    # Compound capital simulation (each trade risks a fixed % of capital)
    # We treat each trade as risking the full "1 contract margin" sized at ~7000 Rs
    # (ETH ~2500 USDT ≈ 210000 Rs, 1 contract on Delta India = 1 USD notional ≈ 85 Rs,
    #  but user's code uses size=1 so we simulate P&L as pnl_pct × margin_per_trade)
    # Conservative: assume margin per trade = capital_rs (all-in on 1 trade at a time)
    # This shows the % curve on capital.
    equity = capital_rs
    equity_curve = [equity]
    for t in trades:
        equity += equity * t["pnl_pct"]  # compound
        equity_curve.append(equity)

    max_equity = max(equity_curve)
    min_equity = min(equity_curve)
    max_dd = (max_equity - min(equity_curve[equity_curve.index(max_equity):])) / max_equity * 100

    # Days in backtest
    total_days = (trades[-1]["exit_time"] - trades[0]["entry_time"]).days or 1
    avg_trades_per_day = len(trades) / total_days
    avg_pnl_per_trade_rs = (equity - capital_rs) / len(trades)

    print("\n" + SEP)
    print("  BACKTEST RESULTS - ETH/USDT 15m  |  Fisher Transform Crossover")
    print(SEP)
    print(f"  Period          : {trades[0]['entry_time'].strftime('%Y-%m-%d')} to {trades[-1]['exit_time'].strftime('%Y-%m-%d')}")
    print(f"  Total days      : {total_days}")
    print(SEP)
    print(f"  Total Trades    : {len(trades)}")
    print(f"  Wins  (TP hit)  : {len(wins)}   ({win_rate:.1f}%)")
    print(f"  Losses (SL hit) : {len(losses)}  ({100-win_rate:.1f}%)")
    print(f"  Avg trades/day  : {avg_trades_per_day:.2f}")
    print(SEP)
    print(f"  Avg Win         : +{avg_win*100:.2f}% on margin  (target {tp_pct/leverage*leverage*100:.2f}%)")
    print(f"  Avg Loss        :  {avg_loss*100:.2f}% on margin  (target -{sl_pct/leverage*leverage*100:.2f}%)")
    print(f"  Risk/Reward     : {abs(avg_win/avg_loss):.2f}x")
    print(SEP)
    print(f"  Breakeven WR    : {breakeven_wr:.1f}%  (need WR > this to profit)")
    print(f"  Your WR         : {win_rate:.1f}%")
    if win_rate > breakeven_wr:
        print(f"  Verdict         : [EDGE EXISTS]  (+{win_rate-breakeven_wr:.1f}% above breakeven)")
    else:
        print(f"  Verdict         : [NO EDGE]  ({win_rate-breakeven_wr:.1f}% below breakeven)")
    print(SEP)
    print(f"  Starting capital: Rs{capital_rs:,.0f}")
    print(f"  Final capital   : Rs{equity:,.0f}  ({(equity/capital_rs-1)*100:+.1f}% over {total_days} days)")
    print(f"  Max drawdown    : {max_dd:.1f}%")
    print(f"  Avg P&L/trade   : Rs{avg_pnl_per_trade_rs:+.1f}")
    print(SEP)
    print(f"\n  [!] Target was Rs500/day from Rs10,000 = 5%/day")
    actual_daily = (equity / capital_rs) ** (1 / total_days) - 1
    print(f"  Actual daily return (CAGR basis): {actual_daily*100:+.4f}%/day")
    print(f"  Actual annual return (CAGR):      {((1+actual_daily)**365 - 1)*100:+.1f}%")

    # ── Monthly breakdown ───────────────────────────────────────────────────
    print(f"\n  Monthly P&L Breakdown:")
    print(f"  {'Month':<10} {'Trades':>7} {'Wins':>6} {'WR%':>7} {'P&L% margin':>13}")
    monthly = defaultdict(list)
    for t in trades:
        monthly[t["exit_time"].strftime("%Y-%m")].append(t)

    for month, mt in sorted(monthly.items()):
        mw  = sum(1 for t in mt if t["reason"] == "TP")
        mwr = mw / len(mt) * 100
        mpnl = sum(t["pnl_pct"] for t in mt) * 100
        flag = "[+]" if mpnl > 0 else "[-]"
        print(f"  {month:<10} {len(mt):>7} {mw:>6} {mwr:>6.1f}%  {mpnl:>+10.2f}%  {flag}")

    # ── Signal frequency note ───────────────────────────────────────────────
    print(f"\n  Note: Zone filter (both negative / both positive) restricts signals.")
    print(f"  Without filter: any Fisher-Trigger crossover would fire.")

    # ── 500 Rs/day feasibility ──────────────────────────────────────────────
    print(f"\n  Rs500/day feasibility check:")
    profitable_days = 0
    pnl_by_day = defaultdict(float)
    for t in trades:
        day = t["exit_time"].date()
        pnl_by_day[day] += t["pnl_pct"] * capital_rs
    days_over_500 = sum(1 for v in pnl_by_day.values() if v >= 500)
    days_total    = len(pnl_by_day)
    print(f"  Days with >=Rs500 profit : {days_over_500} out of {days_total} trading days ({days_over_500/days_total*100:.1f}%)")
    print(f"  Days with any profit   : {sum(1 for v in pnl_by_day.values() if v > 0)} / {days_total}")
    print(f"  Days with loss         : {sum(1 for v in pnl_by_day.values() if v < 0)} / {days_total}")
    print(f"  Days with no trades    : {total_days - days_total} / {total_days}")
    print(SEP)


# ── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    candles = fetch_historical_data(symbol="ETH/USDT", timeframe="15m", days=180)
    trades  = backtest(candles, lookback=9, leverage=30, tp_pct=0.1375, sl_pct=0.15)
    report(trades, capital_rs=10000)