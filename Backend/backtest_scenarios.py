"""
Enhanced Backtest: 4 Scenarios compared side-by-side
Capital: Rs 1,00,000  |  ETH/USDT 15m  |  6 months

Scenario A: Current bot (TP=13.75%, SL=15%, no filter)
Scenario B: Better R/R  (TP=30%,    SL=15%, no filter)  2:1 ratio
Scenario C: Current R/R + EMA50 trend filter
Scenario D: Better R/R  + EMA50 trend filter  <-- likely best
"""

import ccxt, time, math
from datetime import datetime, timedelta
from decimal import Decimal
from collections import defaultdict


# ── Fisher Transform ────────────────────────────────────────────────────────
def compute_fisher_series(candles, lookback=9):
    out, v_prev, fisher_prev = [], 0.0, 0.0
    for i in range(len(candles)):
        window = candles[max(0, i - lookback + 1): i + 1]
        HH = max(c["high"]  for c in window)
        LL = min(c["low"]   for c in window)
        close = candles[i]["close"]
        if HH != LL:
            x = (close - LL) / (HH - LL)
            value = 0.33 * 2.0 * (x - 0.5) + 0.67 * v_prev
        else:
            value = v_prev
        value = max(min(value, 0.999), -0.999)
        fisher = 0.5 * math.log((1 + value) / (1 - value))
        out.append({"time": candles[i]["time"], "close": close,
                    "fisher": fisher, "trigger": fisher_prev})
        v_prev, fisher_prev = value, fisher
    return out


# ── EMA ─────────────────────────────────────────────────────────────────────
def compute_ema(candles, period=50):
    """Returns list of EMA values, aligned with candles list."""
    k = 2 / (period + 1)
    ema_vals = []
    ema = None
    for c in candles:
        if ema is None:
            ema = c["close"]
        else:
            ema = c["close"] * k + ema * (1 - k)
        ema_vals.append(ema)
    return ema_vals


# ── Crossover (exact run_bot.py logic) ─────────────────────────────────────
FLOAT_TOL = 0.001

def detect_crossover(cf, ct, pf, pt):
    if pf <= pt and cf > ct:
        return "fisher_above"
    if pf >= pt and cf < ct:
        return "fisher_below"
    if abs(cf - ct) <= FLOAT_TOL and abs(pf - pt) > FLOAT_TOL:
        return "fisher_above" if cf > ct else "fisher_below"
    return None


# ── TP/SL ───────────────────────────────────────────────────────────────────
def calc_tp_sl(entry, side, leverage, tp_pct, sl_pct):
    p = Decimal(str(entry))
    lev = Decimal(str(leverage))
    tp_off = p * Decimal(str(tp_pct)) / lev
    sl_off = p * Decimal(str(sl_pct)) / lev
    if side == "buy":
        return float(p + tp_off), float(p - sl_off)
    return float(p - tp_off), float(p + sl_off)


# ── Fetch data ───────────────────────────────────────────────────────────────
def fetch_data(symbol="ETH/USDT", timeframe="15m", days=180):
    exchange = ccxt.binance()
    end_ms   = int(datetime.now().timestamp() * 1000)
    start_ms = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
    print(f"Fetching {symbol} {timeframe} | {days} days ...")
    all_bars, since = [], start_ms
    while since < end_ms:
        bars = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not bars: break
        all_bars.extend(bars)
        since = bars[-1][0] + 1
        print(f"  {len(all_bars):,} candles...", end="\r")
        time.sleep(0.25)
        if bars[-1][0] >= end_ms: break
    candles = [{"time":b[0],"open":b[1],"high":b[2],"low":b[3],"close":b[4],"volume":b[5]}
               for b in all_bars if b[0] <= end_ms]
    print(f"\n  Done: {len(candles):,} candles\n")
    return candles


# ── Core backtest engine ─────────────────────────────────────────────────────
def run_backtest(candles, lookback=9, leverage=30,
                 tp_pct=0.1375, sl_pct=0.15, use_ema=False, ema_period=50):
    series   = compute_fisher_series(candles, lookback)
    ema_vals = compute_ema(candles, ema_period) if use_ema else [None] * len(candles)

    trades, open_pos, last_sig = [], None, None

    for i in range(1, len(series)):
        curr  = series[i];  prev  = series[i-1]
        cf    = round(curr["fisher"],  6)
        ct    = round(curr["trigger"], 6)
        pf    = round(prev["fisher"],  6)
        pt    = round(prev["trigger"], 6)
        price = curr["close"]
        ema   = ema_vals[i]

        # ── TP/SL check ────────────────────────────────────────────────────
        if open_pos:
            side, tp, sl, ep = open_pos["side"], open_pos["tp"], open_pos["sl"], open_pos["ep"]
            hit_tp = (side=="buy" and price>=tp) or (side=="sell" and price<=tp)
            hit_sl = (side=="buy" and price<=sl) or (side=="sell" and price>=sl)
            if hit_tp or hit_sl:
                exit_px = tp if hit_tp else sl
                raw     = (exit_px - ep) / ep * (1 if side=="buy" else -1)
                trades.append({
                    "side":     side,
                    "ep":       ep,
                    "exit_px":  exit_px,
                    "reason":   "TP" if hit_tp else "SL",
                    "pnl_frac": raw * leverage,
                    "entry_t":  datetime.fromtimestamp(open_pos["t"]/1000),
                    "exit_t":   datetime.fromtimestamp(curr["time"]/1000),
                })
                open_pos, last_sig = None, None

        # ── Signal detection ────────────────────────────────────────────────
        signal = None
        co = detect_crossover(cf, ct, pf, pt)
        if co:
            if co == "fisher_above" and cf < 0 and ct < 0:
                signal = "buy"
            elif co == "fisher_below" and cf > 0 and ct > 0:
                signal = "sell"

        # ── EMA trend filter ────────────────────────────────────────────────
        if signal and use_ema and ema is not None:
            if signal == "buy"  and price < ema: signal = None   # only buy above EMA
            if signal == "sell" and price > ema: signal = None   # only sell below EMA

        # ── Open position ───────────────────────────────────────────────────
        if signal and not open_pos and signal != last_sig:
            tp, sl = calc_tp_sl(price, signal, leverage, tp_pct, sl_pct)
            open_pos  = {"side": signal, "ep": price, "tp": tp, "sl": sl, "t": curr["time"]}
            last_sig  = signal

    return trades


# ── Stats for one scenario ───────────────────────────────────────────────────
def stats(trades, capital, kelly_frac):
    if not trades:
        return None
    wins   = [t for t in trades if t["reason"] == "TP"]
    losses = [t for t in trades if t["reason"] == "SL"]
    wr     = len(wins) / len(trades)
    avg_w  = sum(t["pnl_frac"] for t in wins)   / len(wins)   if wins   else 0
    avg_l  = sum(t["pnl_frac"] for t in losses) / len(losses) if losses else 0
    be_wr  = abs(avg_l) / (avg_w + abs(avg_l)) if (avg_w + abs(avg_l)) else 0.5

    # Kelly fraction: f = (p*b - q) / b  where b = avg_w / |avg_l|
    b      = avg_w / abs(avg_l) if avg_l else 0
    kelly  = (wr * b - (1 - wr)) / b if b > 0 else 0
    kelly  = max(kelly, 0)

    # Fixed-fraction simulation: risk kelly_frac of equity per trade
    equity = capital
    eq_curve = [equity]
    margin_used = []
    for t in trades:
        m   = equity * kelly_frac           # margin per trade (Rs)
        pnl = m * t["pnl_frac"]
        equity += pnl
        eq_curve.append(equity)
        margin_used.append(m)

    peak   = eq_curve[0]
    max_dd = 0
    for v in eq_curve:
        peak   = max(peak, v)
        max_dd = max(max_dd, (peak - v) / peak)

    # Daily P&L
    pnl_by_day = defaultdict(float)
    for t, m in zip(trades, margin_used):
        pnl_by_day[t["exit_t"].date()] += m * t["pnl_frac"]

    total_days  = (trades[-1]["exit_t"] - trades[0]["entry_t"]).days or 1
    avg_per_day = (eq_curve[-1] - capital) / total_days

    # Max consecutive losses
    max_consec_loss = streak = 0
    for t in trades:
        streak = streak + 1 if t["reason"] == "SL" else 0
        max_consec_loss = max(max_consec_loss, streak)

    return {
        "total":       len(trades),
        "wins":        len(wins),
        "losses":      len(losses),
        "wr":          wr,
        "avg_w":       avg_w,
        "avg_l":       avg_l,
        "be_wr":       be_wr,
        "kelly":       kelly,
        "trades_day":  len(trades) / total_days,
        "final_eq":    eq_curve[-1],
        "max_dd":      max_dd,
        "avg_day_pnl": avg_per_day,
        "days_500":    sum(1 for v in pnl_by_day.values() if v >= 500),
        "days_loss":   sum(1 for v in pnl_by_day.values() if v <  0),
        "days_profit": sum(1 for v in pnl_by_day.values() if v >  0),
        "total_days":  total_days,
        "pnl_by_day":  pnl_by_day,
        "max_consec_loss": max_consec_loss,
        "kelly_frac":  kelly_frac,
        "capital":     capital,
        "monthly":     _monthly(trades, margin_used),
    }


def _monthly(trades, margins):
    m = defaultdict(lambda: {"pnl": 0, "cnt": 0, "wins": 0})
    for t, mg in zip(trades, margins):
        k = t["exit_t"].strftime("%Y-%m")
        m[k]["pnl"]  += mg * t["pnl_frac"]
        m[k]["cnt"]  += 1
        m[k]["wins"] += 1 if t["reason"] == "TP" else 0
    return m


# ── Print one scenario ───────────────────────────────────────────────────────
def print_scenario(name, s, tp_pct, sl_pct):
    SEP = "-" * 65
    rr  = tp_pct / sl_pct
    print(f"\n{'='*65}")
    print(f"  {name}")
    print(f"  R/R = {rr:.2f}  |  TP={tp_pct*100:.1f}%  SL={sl_pct*100:.1f}%  |  Kelly={s['kelly']*100:.1f}%")
    print(f"{'='*65}")
    has_edge = s["wr"] > s["be_wr"]
    verdict  = "[EDGE EXISTS]" if has_edge else "[NO EDGE]"
    margin_k = s["capital"] * s["kelly_frac"]

    print(f"  Trades total      : {s['total']:,}  ({s['trades_day']:.1f}/day)")
    print(f"  Win Rate          : {s['wr']*100:.1f}%  (need >{s['be_wr']*100:.1f}%)  {verdict}")
    print(f"  Avg Win           : +{s['avg_w']*100:.2f}%  on margin")
    print(f"  Avg Loss          :  {s['avg_l']*100:.2f}%  on margin")
    print(f"  Max consec losses : {s['max_consec_loss']}")
    print(SEP)
    print(f"  Capital           : Rs{s['capital']:,.0f}")
    print(f"  Kelly fraction    : {s['kelly_frac']*100:.0f}%  (Rs{margin_k:,.0f} margin/trade)")
    print(f"  Final equity      : Rs{s['final_eq']:,.0f}  ({(s['final_eq']/s['capital']-1)*100:+.1f}% in {s['total_days']} days)")
    print(f"  Max drawdown      : {s['max_dd']*100:.1f}%")
    print(f"  Avg daily P&L     : Rs{s['avg_day_pnl']:+,.0f}")
    print(SEP)
    td = len(s["pnl_by_day"])
    print(f"  Days with >= Rs500 profit : {s['days_500']} / {td}  ({s['days_500']/td*100:.0f}%)")
    print(f"  Days with profit          : {s['days_profit']} / {td}")
    print(f"  Days with loss            : {s['days_loss']} / {td}")
    print(SEP)
    print(f"  Monthly breakdown:")
    print(f"  {'Month':<10} {'Trades':>7} {'WR%':>7} {'P&L (Rs)':>12}")
    for month, d in sorted(s["monthly"].items()):
        wr_m  = d["wins"] / d["cnt"] * 100 if d["cnt"] else 0
        flag  = "[+]" if d["pnl"] > 0 else "[-]"
        print(f"  {month:<10} {d['cnt']:>7} {wr_m:>6.1f}%  Rs{d['pnl']:>+10,.0f}  {flag}")


# ── Summary comparison table ─────────────────────────────────────────────────
def print_summary(scenarios):
    print(f"\n\n{'='*65}")
    print("  SCENARIO COMPARISON SUMMARY  (Capital = Rs 1,00,000)")
    print(f"{'='*65}")
    hdr = f"  {'Scenario':<28} {'WR%':>6} {'Trades/d':>9} {'AvgDay':>9} {'MaxDD':>7} {'Days>=500':>10}"
    print(hdr)
    print(f"  {'-'*62}")
    for name, s, _, _ in scenarios:
        td = len(s["pnl_by_day"])
        print(f"  {name:<28} {s['wr']*100:>5.1f}% {s['trades_day']:>9.1f} "
              f"Rs{s['avg_day_pnl']:>+7,.0f} {s['max_dd']*100:>6.1f}% "
              f"{s['days_500']:>5}/{td}")
    print(f"{'='*65}")
    print("""
  READING THE TABLE:
  WR%       = Win rate (higher is better)
  Trades/d  = Average trades per day
  AvgDay    = Average daily P&L in Rs
  MaxDD     = Max drawdown seen in 6 months (lower is better)
  Days>=500 = How many days had >= Rs500 profit / total trading days
""")


# ── Rs 500/day feasibility analysis ─────────────────────────────────────────
def print_feasibility(best_name, best_s):
    print(f"{'='*65}")
    print(f"  Rs 500/DAY FEASIBILITY ANALYSIS  (Best: {best_name})")
    print(f"{'='*65}")
    cap = best_s["capital"]
    td  = len(best_s["pnl_by_day"])
    all_daily = sorted(best_s["pnl_by_day"].values())

    pct_days_500 = best_s["days_500"] / td * 100

    print(f"  Days hitting Rs500+ : {best_s['days_500']}/{td} ({pct_days_500:.0f}% of days)")
    print(f"  Avg daily P&L       : Rs{best_s['avg_day_pnl']:+,.0f}")
    print(f"  Best day            : Rs{max(all_daily):+,.0f}")
    print(f"  Worst day           : Rs{min(all_daily):+,.0f}")
    print(f"  Max drawdown        : {best_s['max_dd']*100:.1f}%  (Rs{cap*best_s['max_dd']:,.0f})")
    print(f"  Max consec losses   : {best_s['max_consec_loss']} trades in a row")

    # Percentile daily returns
    n = len(all_daily)
    p25 = all_daily[int(n*0.25)]
    p50 = all_daily[int(n*0.50)]
    p75 = all_daily[int(n*0.75)]
    print(f"\n  Daily P&L distribution (over {td} trading days):")
    print(f"  Bottom 25% days : Rs{p25:+,.0f}  or worse")
    print(f"  Median day      : Rs{p50:+,.0f}")
    print(f"  Top 25% days    : Rs{p75:+,.0f}  or better")
    print()
    print(f"  Honest verdict:")
    if best_s["avg_day_pnl"] >= 500:
        print(f"  [YES] Average daily P&L = Rs{best_s['avg_day_pnl']:,.0f}")
        print(f"  But 'average' hides variance — expect many days below Rs500")
        print(f"  and some days with significant losses.")
    elif best_s["avg_day_pnl"] >= 300:
        print(f"  [CLOSE] Average = Rs{best_s['avg_day_pnl']:,.0f}/day — not quite Rs500")
        print(f"  Good days hit Rs500+, bad days pull the average down.")
    else:
        print(f"  [NO] Average = Rs{best_s['avg_day_pnl']:,.0f}/day — well below Rs500")
    print(f"{'='*65}")


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    CAPITAL    = 100_000          # Rs 1,00,000
    KELLY_FRAC = 0.05             # Risk 5% of equity per trade (half-Kelly, safer)

    candles = fetch_data("ETH/USDT", "15m", days=180)

    configs = [
        # (label,                                      tp,     sl,    ema)
        ("A: Current  (TP=13.75% SL=15% no EMA)",   0.1375, 0.15,  False),
        ("B: Better RR (TP=30%   SL=15% no EMA)",   0.30,   0.15,  False),
        ("C: Current  (TP=13.75% SL=15% + EMA50)",  0.1375, 0.15,  True ),
        ("D: Better RR (TP=30%   SL=15% + EMA50)",  0.30,   0.15,  True ),
    ]

    results = []
    for label, tp, sl, use_ema in configs:
        print(f"Running: {label} ...")
        trades = run_backtest(candles, lookback=9, leverage=30,
                              tp_pct=tp, sl_pct=sl, use_ema=use_ema)
        s = stats(trades, CAPITAL, KELLY_FRAC)
        results.append((label, s, tp, sl))
        print_scenario(label, s, tp, sl)

    print_summary(results)

    # Find best scenario by avg daily P&L
    best = max(results, key=lambda x: x[1]["avg_day_pnl"])
    print_feasibility(best[0], best[1])