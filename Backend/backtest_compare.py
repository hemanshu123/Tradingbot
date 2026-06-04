"""
Deep Comparison: 15m vs 1h  |  4:1 R/R  |  2 Years ETH/USDT
Plus: 4 anti-whipsaw improvements tested

WHIPSAW = Fisher barely crosses Trigger, price reverses immediately,
          hits SL, then crosses again. Causes many consecutive losses.

Improvements tested:
  1. BASE          : Plain 4:1 R/R (best from last test)
  2. +COOLDOWN     : After SL hit, skip next N bars (no re-entry in same chop)
  3. +SPREAD FILTER: Only enter if |fisher - trigger| >= 0.05 (ignore weak crosses)
  4. +BOTH         : Cooldown + Spread filter together
"""

import ccxt, time, math
from datetime import datetime, timedelta
from decimal import Decimal
from collections import defaultdict


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXPLANATION  (for new traders)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WHIPSAW: Imagine Fisher just barely crosses Trigger.
#   -> Bot enters BUY at Rs 100
#   -> Price dips to Rs 99.5 (hits SL)  -> Loss
#   -> Price bounces back, Fisher crosses again
#   -> Bot enters BUY AGAIN at Rs 100
#   -> Same thing happens 3-4 times in a row
# This kills profitability even with a good strategy.
#
# FIX 1 - COOLDOWN:
#   After SL hit, wait 5 bars before entering again.
#   Gives market time to stop being choppy.
#
# FIX 2 - SPREAD FILTER:
#   Only enter when Fisher is CLEARLY above/below Trigger (not barely touching).
#   Weak crossovers = likely fake. Strong crossovers = more reliable.
#
# FIX 3 - BOTH TOGETHER: Maximum protection against whipsaws.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


# ── Fisher Transform ────────────────────────────────────────────────────────
def fisher_series(candles, lookback=9):
    out, v_prev, f_prev = [], 0.0, 0.0
    for i in range(len(candles)):
        window = candles[max(0, i - lookback + 1): i + 1]
        HH = max(c["h"] for c in window)
        LL = min(c["l"] for c in window)
        cl = candles[i]["c"]
        if HH != LL:
            x = (cl - LL) / (HH - LL)
            v = 0.33 * 2.0 * (x - 0.5) + 0.67 * v_prev
        else:
            v = v_prev
        v = max(min(v, 0.999), -0.999)
        f = 0.5 * math.log((1 + v) / (1 - v))
        out.append({"t": candles[i]["t"], "c": cl, "f": f, "tr": f_prev})
        v_prev, f_prev = v, f
    return out


# ── Crossover ────────────────────────────────────────────────────────────────
def crossover(cf, ct, pf, pt, tol=0.001):
    if pf <= pt and cf > ct: return "above"
    if pf >= pt and cf < ct: return "below"
    if abs(cf - ct) <= tol and abs(pf - pt) > tol:
        return "above" if cf > ct else "below"
    return None


# ── TP/SL ─────────────────────────────────────────────────────────────────────
def tp_sl(entry, side, lev, tp_pct, sl_pct):
    p = Decimal(str(entry))
    if side == "buy":
        return float(p + p * Decimal(str(tp_pct)) / Decimal(str(lev))), \
               float(p - p * Decimal(str(sl_pct)) / Decimal(str(lev)))
    return float(p - p * Decimal(str(tp_pct)) / Decimal(str(lev))), \
           float(p + p * Decimal(str(sl_pct)) / Decimal(str(lev)))


# ── Fetch ────────────────────────────────────────────────────────────────────
def fetch(symbol, tf, years=2):
    ex     = ccxt.binance()
    end_ms = int(datetime.now().timestamp() * 1000)
    st_ms  = int((datetime.now() - timedelta(days=365 * years)).timestamp() * 1000)
    print(f"  Fetching {symbol} {tf} ({years}yr) ...", end=" ")
    bars, since = [], st_ms
    while since < end_ms:
        chunk = ex.fetch_ohlcv(symbol, tf, since=since, limit=1000)
        if not chunk: break
        bars.extend(chunk)
        since = chunk[-1][0] + 1
        time.sleep(0.2)
        if chunk[-1][0] >= end_ms: break
    candles = [{"t":b[0],"o":b[1],"h":b[2],"l":b[3],"c":b[4],"v":b[5]}
               for b in bars if b[0] <= end_ms]
    print(f"{len(candles):,} candles")
    return candles


# ── Backtest Engine (with whipsaw fixes) ────────────────────────────────────
def backtest(candles, lookback=9, leverage=30, tp_pct=0.60, sl_pct=0.15,
             cooldown_bars=0, min_spread=0.0):
    """
    cooldown_bars : bars to skip after SL hit (0 = no cooldown)
    min_spread    : minimum |fisher - trigger| to enter (0 = any crossover)
    """
    series = fisher_series(candles, lookback)
    trades, pos, last_sig = [], None, None
    cooldown_remaining = 0

    for i in range(1, len(series)):
        cur = series[i];  prv = series[i - 1]
        cf  = round(cur["f"],  6);  ct = round(cur["tr"], 6)
        pf  = round(prv["f"],  6);  pt = round(prv["tr"], 6)
        px  = cur["c"]

        # ── cooldown tick ────────────────────────────────────────────────
        if cooldown_remaining > 0:
            cooldown_remaining -= 1

        # ── check open position ──────────────────────────────────────────
        if pos:
            s, tp, sl, ep = pos["s"], pos["tp"], pos["sl"], pos["ep"]
            hit_tp = (s == "buy"  and px >= tp) or (s == "sell" and px <= tp)
            hit_sl = (s == "buy"  and px <= sl) or (s == "sell" and px >= sl)
            if hit_tp or hit_sl:
                exit_px = tp if hit_tp else sl
                raw     = (exit_px - ep) / ep * (1 if s == "buy" else -1)
                trades.append({
                    "side":    s, "ep": ep, "ex": exit_px,
                    "why":     "TP" if hit_tp else "SL",
                    "pnl":     raw * leverage,
                    "entry_t": datetime.fromtimestamp(pos["t"] / 1000),
                    "exit_t":  datetime.fromtimestamp(cur["t"] / 1000),
                    "hold_bars": i - pos["bar_i"],
                })
                if hit_sl:
                    cooldown_remaining = cooldown_bars   # start cooldown
                pos, last_sig = None, None

        # ── detect signal ────────────────────────────────────────────────
        if cooldown_remaining > 0:
            continue                                     # in cooldown, skip

        sig = None
        co  = crossover(cf, ct, pf, pt)
        if co:
            if co == "above" and cf < 0 and ct < 0: sig = "buy"
            if co == "below" and cf > 0 and ct > 0: sig = "sell"

        # ── spread filter ────────────────────────────────────────────────
        if sig and min_spread > 0:
            if abs(cf - ct) < min_spread:
                sig = None                               # crossover too weak, skip

        if sig and not pos and sig != last_sig:
            tpp, slp = tp_sl(px, sig, leverage, tp_pct, sl_pct)
            pos = {"s": sig, "ep": px, "tp": tpp, "sl": slp,
                   "t": cur["t"], "bar_i": i}
            last_sig = sig

    return trades


# ── Statistics ────────────────────────────────────────────────────────────────
def stats(trades, capital=100_000, risk_frac=0.05):
    if not trades:
        return None
    wins   = [t for t in trades if t["why"] == "TP"]
    losses = [t for t in trades if t["why"] == "SL"]
    wr     = len(wins) / len(trades)
    avg_w  = sum(t["pnl"] for t in wins)   / len(wins)   if wins   else 0
    avg_l  = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    be_wr  = abs(avg_l) / (avg_w + abs(avg_l)) if (avg_w + abs(avg_l)) else 0.5

    equity = capital
    eq_curve, daily = [equity], defaultdict(float)
    for t in trades:
        m   = equity * risk_frac
        pnl = m * t["pnl"]
        equity += pnl
        eq_curve.append(equity)
        daily[t["exit_t"].date()] += pnl

    peak, max_dd = eq_curve[0], 0
    for v in eq_curve:
        peak   = max(peak, v)
        max_dd = max(max_dd, (peak - v) / peak)

    max_streak = streak = 0
    for t in trades:
        streak = streak + 1 if t["why"] == "SL" else 0
        max_streak = max(max_streak, streak)

    total_days = (trades[-1]["exit_t"] - trades[0]["entry_t"]).days or 1

    # monthly
    monthly = defaultdict(lambda: {"rs": 0, "cnt": 0, "wins": 0})
    eq2 = capital
    for t in trades:
        m  = eq2 * risk_frac
        pr = m * t["pnl"]
        eq2 += pr
        k   = t["exit_t"].strftime("%Y-%m")
        monthly[k]["rs"]   += pr
        monthly[k]["cnt"]  += 1
        monthly[k]["wins"] += 1 if t["why"] == "TP" else 0

    all_daily = list(daily.values())
    avg_hold  = sum(t["hold_bars"] for t in trades) / len(trades)

    # count how many times 3+ consecutive SL happened (whipsaw clusters)
    whipsaw_clusters = 0
    run = 0
    for t in trades:
        run = run + 1 if t["why"] == "SL" else 0
        if run == 3:
            whipsaw_clusters += 1

    return {
        "total":       len(trades),
        "wins":        len(wins),
        "losses":      len(losses),
        "wr":          wr,
        "avg_w_pct":   avg_w * 100,
        "avg_l_pct":   abs(avg_l) * 100,
        "be_wr":       be_wr,
        "has_edge":    wr > be_wr,
        "trades_day":  len(trades) / total_days,
        "final_eq":    equity,
        "growth_pct":  (equity / capital - 1) * 100,
        "max_dd":      max_dd * 100,
        "avg_day":     (equity - capital) / total_days,
        "days_500":    sum(1 for v in all_daily if v >= 500),
        "days_profit": sum(1 for v in all_daily if v > 0),
        "days_loss":   sum(1 for v in all_daily if v < 0),
        "total_day_obs": len(all_daily),
        "total_days":  total_days,
        "max_streak":  max_streak,
        "whipsaw_clusters": whipsaw_clusters,
        "green_months": sum(1 for d in monthly.values() if d["rs"] > 0),
        "red_months":   sum(1 for d in monthly.values() if d["rs"] <= 0),
        "monthly":     monthly,
        "best_day":    max(all_daily) if all_daily else 0,
        "worst_day":   min(all_daily) if all_daily else 0,
        "median_day":  sorted(all_daily)[len(all_daily) // 2] if all_daily else 0,
        "avg_hold":    avg_hold,
        "capital":     capital,
    }


# ── Print single result ──────────────────────────────────────────────────────
def show(label, s):
    W = "=" * 70
    edge = "EDGE EXISTS" if s["has_edge"] else "NO EDGE - AVOID"
    gm, rm = s["green_months"], s["red_months"]
    td = s["total_day_obs"]
    print(f"\n{W}")
    print(f"  {label}")
    print(f"  {edge}  |  WR: {s['wr']*100:.1f}%  (need >{s['be_wr']*100:.0f}%)")
    print(f"{W}")
    print(f"  Trades      : {s['total']:,}  ({s['trades_day']:.1f}/day)  |  Avg hold: {s['avg_hold']:.0f} bars")
    print(f"  Win/Loss    : {s['wins']} wins / {s['losses']} losses")
    print(f"  Whipsaw clusters (3+ SL in a row): {s['whipsaw_clusters']}")
    print(f"  Max consec SL streak: {s['max_streak']} trades")
    print(f"  {'-'*66}")
    print(f"  MONEY  (Rs1,00,000 start | 5% risk/trade)")
    print(f"  Final equity : Rs{s['final_eq']:>14,.0f}  ({s['growth_pct']:+.0f}% in {s['total_days']}d)")
    print(f"  Max drawdown : {s['max_dd']:.1f}%  (max loss from a peak)")
    print(f"  Avg/day      : Rs{s['avg_day']:+,.0f}")
    print(f"  Median day   : Rs{s['median_day']:+,.0f}  |  Best: Rs{s['best_day']:+,.0f}  |  Worst: Rs{s['worst_day']:+,.0f}")
    print(f"  {'-'*66}")
    print(f"  Rs500/day    : {s['days_500']}/{td} days ({s['days_500']/td*100:.0f}%)")
    print(f"  Profit days  : {s['days_profit']}/{td} ({s['days_profit']/td*100:.0f}%)")
    print(f"  Loss days    : {s['days_loss']}/{td} ({s['days_loss']/td*100:.0f}%)")
    print(f"  Green months : {gm}/{gm+rm}  |  Red months: {rm}/{gm+rm}")
    print(f"  {'-'*66}")
    print(f"  Monthly P&L:")
    print(f"  {'Month':<10} {'Trades':>7} {'WR%':>7} {'P&L':>14}  ")
    for mo, d in sorted(s["monthly"].items()):
        wr_m = d["wins"] / d["cnt"] * 100 if d["cnt"] else 0
        tag  = "[+]" if d["rs"] >= 0 else "[-]"
        print(f"  {mo:<10} {d['cnt']:>7} {wr_m:>6.1f}%  Rs{d['rs']:>+12,.0f}  {tag}")
    print(f"{W}")


# ── Side-by-side comparison table ───────────────────────────────────────────
def compare_table(results_15m, results_1h):
    W = "=" * 80
    print(f"\n\n{W}")
    print("  HEAD-TO-HEAD: 15m vs 1h  |  4:1 R/R  |  2-Year Backtest")
    print(f"{W}")
    labels = ["Base (no fix)", "+Cooldown 5bars", "+Spread filter", "+Both fixes"]
    metrics = [
        ("Win Rate",       lambda s: f"{s['wr']*100:.1f}%"),
        ("Trades/day",     lambda s: f"{s['trades_day']:.1f}"),
        ("Whipsaw clust.", lambda s: f"{s['whipsaw_clusters']}"),
        ("Max SL streak",  lambda s: f"{s['max_streak']}"),
        ("Avg daily P&L",  lambda s: f"Rs{s['avg_day']:+,.0f}"),
        ("Max drawdown",   lambda s: f"{s['max_dd']:.1f}%"),
        ("Green months",   lambda s: f"{s['green_months']}/{s['green_months']+s['red_months']}"),
        ("Days >= Rs500",  lambda s: f"{s['days_500']}/{s['total_day_obs']}"),
        ("Median day",     lambda s: f"Rs{s['median_day']:+,.0f}"),
        ("Total growth",   lambda s: f"{s['growth_pct']:+.0f}%"),
    ]

    # Header
    print(f"\n  {'Metric':<20} ", end="")
    for l in labels:
        print(f"  {'15m':>12}  {'1h':>10}", end="")
    print()
    print(f"  {'-'*78}")

    # Sub-header
    print(f"  {'':20} ", end="")
    for l in labels:
        print(f"  {l[:12]:>12}  {l[:10]:>10}", end="")
    print()
    print(f"  {'-'*78}")

    for mname, mfn in metrics:
        print(f"  {mname:<20} ", end="")
        for s15, s1h in zip(results_15m, results_1h):
            v15 = mfn(s15) if s15 else "N/A"
            v1h = mfn(s1h) if s1h else "N/A"
            print(f"  {v15:>12}  {v1h:>10}", end="")
        print()

    print(f"\n{W}")


# ── Recommendation ────────────────────────────────────────────────────────────
def recommend(results_15m, results_1h, labels):
    W = "=" * 70

    # Score each: (green_months * 100) + (days_500/total_day_obs * 50) - max_dd
    def score(s):
        if not s: return -999
        return (s["green_months"] * 100
                + (s["days_500"] / s["total_day_obs"]) * 50
                - s["max_dd"]
                - s["whipsaw_clusters"] * 0.5)

    all_res = [(f"15m {l}", s15) for l, s15 in zip(labels, results_15m) if s15] + \
              [(f"1h  {l}", s1h) for l, s1h in zip(labels, results_1h) if s1h]

    ranked = sorted(all_res, key=lambda x: score(x[1]), reverse=True)

    print(f"\n{W}")
    print("  VERDICT: WHICH CONFIG IS BEST FOR YOU?")
    print(f"{W}")
    print(f"  Ranked by: green months + Rs500 days - drawdown - whipsaws\n")
    for rank, (lbl, s) in enumerate(ranked[:5], 1):
        gm = s["green_months"]; rm = s["red_months"]
        print(f"  #{rank}  {lbl:<30}  "
              f"GM:{gm}/{gm+rm}  DD:{s['max_dd']:.1f}%  "
              f"Avg:Rs{s['avg_day']:+,.0f}/day  WS:{s['whipsaw_clusters']}")

    best_lbl, best = ranked[0]
    print(f"\n{W}")
    print(f"  WINNER: {best_lbl}")
    print(f"{W}")

    # Explain what to change in config
    is_1h   = best_lbl.startswith("1h")
    has_cd  = "Cooldown" in best_lbl
    has_sp  = "Spread"   in best_lbl

    tf_val = "1h" if is_1h else "15m"

    print(f"""
  WHAT TO CHANGE IN YOUR BOT:
  -----------------------------------------------
  In bot/config.py (or your .env file):
    TP_PCT     = 0.60   (4:1 R/R)
    SL_PCT     = 0.15
    RESOLUTION = {tf_val}

  In run_bot.py — add these 2 improvements:
""")

    if has_cd or has_sp:
        print("""  IMPROVEMENT 1 — COOLDOWN after Stop Loss:
    After every SL hit, skip the next 5 bars before entering again.
    This stops the bot from re-entering the same choppy market.

    Add this near the top of run_bot.py main():
      cooldown = 0

    In the TP/SL check section (after hit_sl):
      if hit_sl:
          cooldown = 5   # skip next 5 bars
          print("[v0] SL hit - entering 5-bar cooldown")

    In the signal execution section (before executing new trade):
      if cooldown > 0:
          cooldown -= 1
          prev_fisher, prev_trigger = current_fisher, current_trigger
          time.sleep(POLL_SEC)
          continue
""")

    if has_sp:
        print("""  IMPROVEMENT 2 — SPREAD FILTER (ignore weak crossovers):
    Only enter a trade if Fisher is clearly above/below Trigger.
    A very small gap means the crossover is weak and likely to reverse.

    Add this check before executing any trade:
      MIN_SPREAD = 0.05
      if abs(current_fisher - current_trigger) < MIN_SPREAD:
          print("[v0] Crossover too weak - skipping")
          prev_fisher, prev_trigger = current_fisher, current_trigger
          time.sleep(POLL_SEC)
          continue
""")

    print(f"""  WHY THIS MATTERS (Simple Example):
  Without fix: Fisher barely crosses at 0.001 difference
    -> Bot enters -> Price chops -> SL hit -> immediate re-entry -> SL hit again
    -> 5 losses in a row from one bad 15-minute period

  With fix: Cooldown = skip 5 bars (= {5 if not is_1h else 5} hours on {tf_val})
    -> SL hit -> bot waits -> market settles -> next entry is cleaner
  {W}""")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    CAPITAL   = 100_000
    RISK_FRAC = 0.05
    TP        = 0.60
    SL        = 0.15
    LEVERAGE  = 30

    print("\n" + "="*70)
    print("  15m vs 1h Comparison  |  4:1 R/R  |  Anti-Whipsaw Fixes")
    print("="*70)

    print("\nFetching data...")
    c15 = fetch("ETH/USDT", "15m", years=2)
    c1h = fetch("ETH/USDT", "1h",  years=2)

    configs = [
        # label,             cooldown, min_spread
        ("Base (no fix)",        0,    0.00),
        ("+Cooldown 5bars",      5,    0.00),
        ("+Spread filter 0.05",  0,    0.05),
        ("+Both fixes",          5,    0.05),
    ]

    results_15m, results_1h = [], []
    labels = []

    for label, cd, sp in configs:
        labels.append(label)
        print(f"\nRunning 15m | {label} ...")
        t15 = backtest(c15, leverage=LEVERAGE, tp_pct=TP, sl_pct=SL,
                       cooldown_bars=cd, min_spread=sp)
        s15 = stats(t15, CAPITAL, RISK_FRAC)
        results_15m.append(s15)
        show(f"15m | {label}", s15)

        print(f"Running  1h | {label} ...")
        t1h = backtest(c1h, leverage=LEVERAGE, tp_pct=TP, sl_pct=SL,
                       cooldown_bars=cd, min_spread=sp)
        s1h = stats(t1h, CAPITAL, RISK_FRAC)
        results_1h.append(s1h)
        show(f"1h  | {label}", s1h)

    compare_table(results_15m, results_1h)
    recommend(results_15m, results_1h, labels)