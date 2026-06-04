"""
5-Year Backtest: Current Code vs Improved Code
Capital: Rs 1,00,000  |  Risk: 5% per trade

CURRENT CODE (as it runs today):
  TP=0.1375, SL=0.15, Leverage=30x, 15m, no fixes
  -> Win gives 13.75% on margin, Loss takes 15% on margin (BAD R/R)

IMPROVED CODE (with all suggested changes):
  TP=0.60,   SL=0.15, Leverage=10x, 1h,  cooldown=5, spread=0.05
  -> Win gives 60% on margin, Loss takes 15% on margin (4:1 R/R)
  -> TP at 6% price move, SL at 1.5% price move (much safer)
"""

import ccxt, time, math
from datetime import datetime, timedelta
from decimal import Decimal
from collections import defaultdict


# ── Fisher Transform ────────────────────────────────────────────────────────
def fisher_series(candles, lookback=9):
    out, v_prev, f_prev = [], 0.0, 0.0
    for i in range(len(candles)):
        window = candles[max(0, i - lookback + 1): i + 1]
        HH = max(c["h"] for c in window)
        LL = min(c["l"] for c in window)
        cl  = candles[i]["c"]
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


# ── TP / SL prices ───────────────────────────────────────────────────────────
def tp_sl_prices(entry, side, lev, tp_pct, sl_pct):
    p = Decimal(str(entry))
    if side == "buy":
        tp = float(p + p * Decimal(str(tp_pct)) / Decimal(str(lev)))
        sl = float(p - p * Decimal(str(sl_pct)) / Decimal(str(lev)))
    else:
        tp = float(p - p * Decimal(str(tp_pct)) / Decimal(str(lev)))
        sl = float(p + p * Decimal(str(sl_pct)) / Decimal(str(lev)))
    return tp, sl


# ── Fetch data ───────────────────────────────────────────────────────────────
def fetch(symbol, tf, years=5):
    ex     = ccxt.binance()
    end_ms = int(datetime.now().timestamp() * 1000)
    st_ms  = int((datetime.now() - timedelta(days=365 * years)).timestamp() * 1000)
    print(f"  Fetching {symbol} {tf} ({years}yr) ... ", end="", flush=True)
    bars, since = [], st_ms
    while since < end_ms:
        chunk = ex.fetch_ohlcv(symbol, tf, since=since, limit=1000)
        if not chunk: break
        bars.extend(chunk)
        since = chunk[-1][0] + 1
        time.sleep(0.2)
        if chunk[-1][0] >= end_ms: break
    candles = [{"t":b[0],"h":b[2],"l":b[3],"c":b[4]} for b in bars if b[0] <= end_ms]
    print(f"{len(candles):,} candles  "
          f"({datetime.fromtimestamp(candles[0]['t']/1000).strftime('%Y-%m-%d')} to "
          f"{datetime.fromtimestamp(candles[-1]['t']/1000).strftime('%Y-%m-%d')})")
    return candles


# ── Backtest engine ──────────────────────────────────────────────────────────
def backtest(candles, lev, tp_pct, sl_pct, lookback=9,
             cooldown_bars=0, min_spread=0.0):
    series = fisher_series(candles, lookback)
    trades, pos, last_sig = [], None, None
    cooldown = 0

    for i in range(1, len(series)):
        cur = series[i];  prv = series[i - 1]
        cf  = round(cur["f"],  6);  ct = round(cur["tr"], 6)
        pf  = round(prv["f"],  6);  pt = round(prv["tr"], 6)
        px  = cur["c"]

        if cooldown > 0:
            cooldown -= 1

        # ── TP/SL check ─────────────────────────────────────────────────
        if pos:
            s, tp, sl, ep = pos["s"], pos["tp"], pos["sl"], pos["ep"]
            hit_tp = (s=="buy"  and px>=tp) or (s=="sell" and px<=tp)
            hit_sl = (s=="buy"  and px<=sl) or (s=="sell" and px>=sl)
            if hit_tp or hit_sl:
                exit_px = tp if hit_tp else sl
                raw     = (exit_px - ep) / ep * (1 if s=="buy" else -1)
                trades.append({
                    "side":    s,
                    "ep":      ep,
                    "ex":      exit_px,
                    "why":     "TP" if hit_tp else "SL",
                    "pnl":     raw * lev,
                    "entry_t": datetime.fromtimestamp(pos["t"] / 1000),
                    "exit_t":  datetime.fromtimestamp(cur["t"] / 1000),
                })
                if hit_sl:
                    cooldown = cooldown_bars
                pos, last_sig = None, None

        if cooldown > 0:
            continue

        # ── Signal ──────────────────────────────────────────────────────
        sig = None
        co  = crossover(cf, ct, pf, pt)
        if co:
            if co == "above" and cf < 0 and ct < 0: sig = "buy"
            if co == "below" and cf > 0 and ct > 0: sig = "sell"

        if sig and min_spread > 0 and abs(cf - ct) < min_spread:
            sig = None

        if sig and not pos and sig != last_sig:
            tp, sl = tp_sl_prices(px, sig, lev, tp_pct, sl_pct)
            pos = {"s": sig, "ep": px, "tp": tp, "sl": sl, "t": cur["t"]}
            last_sig = sig

    return trades


# ── Statistics ───────────────────────────────────────────────────────────────
def calc_stats(trades, capital=100_000, risk_frac=0.05):
    if not trades:
        return None

    wins   = [t for t in trades if t["why"] == "TP"]
    losses = [t for t in trades if t["why"] == "SL"]
    wr     = len(wins) / len(trades)
    avg_w  = sum(t["pnl"] for t in wins)   / len(wins)   if wins   else 0
    avg_l  = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    be_wr  = abs(avg_l) / (avg_w + abs(avg_l)) if (avg_w + abs(avg_l)) else 0.5

    # Simulate compounding equity
    equity = capital
    eq_curve = [equity]
    daily = defaultdict(float)
    for t in trades:
        m   = equity * risk_frac
        pnl = m * t["pnl"]
        equity += pnl
        eq_curve.append(equity)
        daily[t["exit_t"].date()] += pnl

    # Max drawdown
    peak, max_dd = eq_curve[0], 0.0
    for v in eq_curve:
        peak   = max(peak, v)
        max_dd = max(max_dd, (peak - v) / peak)

    # Consecutive SL streak
    max_streak = streak = 0
    for t in trades:
        streak = streak + 1 if t["why"] == "SL" else 0
        max_streak = max(max_streak, streak)

    # Whipsaw clusters (3+ SL in a row)
    ws = run = 0
    for t in trades:
        run = run + 1 if t["why"] == "SL" else 0
        if run == 3: ws += 1

    total_days = (trades[-1]["exit_t"] - trades[0]["entry_t"]).days or 1

    # Monthly breakdown
    monthly = defaultdict(lambda: {"pnl": 0, "cnt": 0, "wins": 0})
    eq2 = capital
    for t in trades:
        m  = eq2 * risk_frac
        pr = m * t["pnl"]
        eq2 += pr
        k   = t["exit_t"].strftime("%Y-%m")
        monthly[k]["pnl"]  += pr
        monthly[k]["cnt"]  += 1
        monthly[k]["wins"] += 1 if t["why"] == "TP" else 0

    all_d = list(daily.values())

    return {
        "total":        len(trades),
        "wins":         len(wins),
        "losses":       len(losses),
        "wr":           wr,
        "avg_w_pct":    avg_w  * 100,
        "avg_l_pct":    abs(avg_l) * 100,
        "be_wr":        be_wr  * 100,
        "has_edge":     wr > be_wr,
        "trades_day":   len(trades) / total_days,
        "final_eq":     equity,
        "growth_pct":   (equity / capital - 1) * 100,
        "max_dd_pct":   max_dd * 100,
        "max_dd_rs":    capital * max_dd,
        "avg_day":      (equity - capital) / total_days,
        "days_500":     sum(1 for v in all_d if v >= 500),
        "days_profit":  sum(1 for v in all_d if v > 0),
        "days_loss":    sum(1 for v in all_d if v < 0),
        "total_day_obs":len(all_d),
        "total_days":   total_days,
        "max_streak":   max_streak,
        "whipsaws":     ws,
        "green_m":      sum(1 for d in monthly.values() if d["pnl"] > 0),
        "red_m":        sum(1 for d in monthly.values() if d["pnl"] <= 0),
        "monthly":      monthly,
        "best_day":     max(all_d) if all_d else 0,
        "worst_day":    min(all_d) if all_d else 0,
        "median_day":   sorted(all_d)[len(all_d)//2] if all_d else 0,
        "capital":      capital,
    }


# ── Print full result ─────────────────────────────────────────────────────────
def show_full(label, s, lev, tp_pct, sl_pct, tf):
    W  = "=" * 72
    rr = tp_pct / sl_pct
    tp_move = tp_pct / lev * 100
    sl_move = sl_pct / lev * 100
    win_rs  = s["capital"] * 0.05 * tp_pct
    loss_rs = s["capital"] * 0.05 * sl_pct
    gm, rm  = s["green_m"], s["red_m"]
    td      = s["total_day_obs"]

    print(f"\n{W}")
    print(f"  {label}")
    print(f"{W}")
    print(f"  Settings  : Leverage={lev}x | TP={tp_pct} | SL={sl_pct} | TF={tf}")
    print(f"  Per Trade : Price must move {tp_move:.2f}% for TP  |  {sl_move:.2f}% for SL")
    print(f"  Per Trade : Each WIN = +Rs{win_rs:,.0f}  |  Each LOSS = -Rs{loss_rs:,.0f}  (on Rs5,000 margin)")
    print(f"  R/R Ratio : {rr:.0f}:1  (need >{s['be_wr']:.0f}% win rate to profit)")
    print(f"{'-'*72}")

    verdict = "PROFITABLE - EDGE EXISTS" if s["has_edge"] else "LOSING - NO EDGE"
    print(f"  VERDICT   : {verdict}")
    print(f"  Win Rate  : {s['wr']*100:.1f}%  (breakeven = {s['be_wr']:.0f}%)")
    print(f"  Trades    : {s['total']:,} total  |  {s['trades_day']:.1f} per day")
    print(f"  Whipsaws  : {s['whipsaws']} clusters  |  Max SL streak: {s['max_streak']} in a row")
    print(f"{'-'*72}")
    print(f"  CAPITAL (Rs1,00,000 start | 5% risked per trade)")
    print(f"  Final     : Rs{s['final_eq']:>16,.0f}   ({s['growth_pct']:+.0f}% over {s['total_days']} days)")
    print(f"  Drawdown  : Rs{s['max_dd_rs']:>16,.0f}   ({s['max_dd_pct']:.1f}% max loss from peak)")
    print(f"  Avg/day   : Rs{s['avg_day']:>+16,.0f}")
    print(f"  Median day: Rs{s['median_day']:>+16,.0f}")
    print(f"  Best day  : Rs{s['best_day']:>+16,.0f}")
    print(f"  Worst day : Rs{s['worst_day']:>+16,.0f}")
    print(f"{'-'*72}")
    print(f"  Rs 500/day TARGET")
    print(f"  Days >= Rs500  : {s['days_500']}/{td}  ({s['days_500']/td*100:.0f}% of trading days)")
    print(f"  Profit days    : {s['days_profit']}/{td}  ({s['days_profit']/td*100:.0f}%)")
    print(f"  Loss days      : {s['days_loss']}/{td}  ({s['days_loss']/td*100:.0f}%)")
    print(f"  Green months   : {gm}/{gm+rm}  |  Red months: {rm}/{gm+rm}")
    print(f"{'-'*72}")
    print(f"  MONTHLY P&L BREAKDOWN:")
    print(f"  {'Month':<10} {'Trades':>7} {'WR%':>7} {'P&L (Rs)':>14}  {'Yr Total':>14}")

    yr_totals = defaultdict(float)
    for mo, d in sorted(s["monthly"].items()):
        yr = mo[:4]
        yr_totals[yr] += d["pnl"]

    prev_yr = None
    for mo, d in sorted(s["monthly"].items()):
        yr = mo[:4]
        wr_m = d["wins"] / d["cnt"] * 100 if d["cnt"] else 0
        tag  = "[+]" if d["pnl"] >= 0 else "[-]"
        # Print yearly subtotal before new year
        if prev_yr and yr != prev_yr:
            print(f"  {'  YEAR '+prev_yr+' TOTAL':<10} {'':>7} {'':>7}  Rs{yr_totals[prev_yr]:>+12,.0f}  <--")
            print(f"  {'-'*68}")
        print(f"  {mo:<10} {d['cnt']:>7} {wr_m:>6.1f}%  Rs{d['pnl']:>+12,.0f}  {tag}")
        prev_yr = yr

    # Last year total
    if prev_yr:
        print(f"  {'  YEAR '+prev_yr+' TOTAL':<10} {'':>7} {'':>7}  Rs{yr_totals[prev_yr]:>+12,.0f}  <--")
    print(f"{W}")


# ── 3-way comparison table ───────────────────────────────────────────────────
def three_way(cur, imp_1h, imp_15m):
    W = "=" * 85
    print(f"\n\n{W}")
    print(f"  3-WAY COMPARISON  (5 Years | Rs 1,00,000 | 5% risk/trade)")
    print(f"{W}")
    print(f"  {'Metric':<28} {'CURRENT':>16}  {'IMPROVED 1h':>16}  {'IMPROVED 15m':>16}")
    print(f"  {'-'*80}")

    def row(name, v1, v2, v3):
        print(f"  {name:<28} {v1:>16}  {v2:>16}  {v3:>16}")

    def sep(label=""):
        print(f"  {'-'*80}")
        if label:
            print(f"  {label}")
            print(f"  {'-'*80}")

    row("Timeframe",         "15m",           "1h",            "15m")
    row("Leverage",          "30x",           "10x",           "10x")
    row("TP per win",        f"+{cur['avg_w_pct']:.1f}% margin", f"+{imp_1h['avg_w_pct']:.1f}% margin", f"+{imp_15m['avg_w_pct']:.1f}% margin")
    row("SL per loss",       f"-{cur['avg_l_pct']:.1f}% margin", f"-{imp_1h['avg_l_pct']:.1f}% margin", f"-{imp_15m['avg_l_pct']:.1f}% margin")
    row("R/R Ratio",         "0.9:1 (BAD)",   "4:1 (GOOD)",    "4:1 (GOOD)")
    row("Win Rate",          f"{cur['wr']*100:.1f}%", f"{imp_1h['wr']*100:.1f}%", f"{imp_15m['wr']*100:.1f}%")
    row("Breakeven WR",      f"{cur['be_wr']:.0f}%", f"{imp_1h['be_wr']:.0f}%", f"{imp_15m['be_wr']:.0f}%")
    row("Has Edge?",         "YES" if cur["has_edge"] else "NO", "YES" if imp_1h["has_edge"] else "NO", "YES" if imp_15m["has_edge"] else "NO")
    row("Trades/day",        f"{cur['trades_day']:.1f}", f"{imp_1h['trades_day']:.1f}", f"{imp_15m['trades_day']:.1f}")
    row("Whipsaws",          f"{cur['whipsaws']}", f"{imp_1h['whipsaws']}", f"{imp_15m['whipsaws']}")
    row("Max SL streak",     f"{cur['max_streak']}", f"{imp_1h['max_streak']}", f"{imp_15m['max_streak']}")
    sep("MONEY")
    row("Starting capital",  "Rs 1,00,000",   "Rs 1,00,000",   "Rs 1,00,000")
    row("Final capital",     f"Rs{cur['final_eq']:,.0f}", f"Rs{imp_1h['final_eq']:,.0f}", f"Rs{imp_15m['final_eq']:,.0f}")
    row("Total growth",      f"{cur['growth_pct']:+.0f}%", f"{imp_1h['growth_pct']:+.0f}%", f"{imp_15m['growth_pct']:+.0f}%")
    row("Max drawdown",      f"{cur['max_dd_pct']:.1f}%", f"{imp_1h['max_dd_pct']:.1f}%", f"{imp_15m['max_dd_pct']:.1f}%")
    row("Max DD in Rs",      f"Rs{cur['max_dd_rs']:,.0f}", f"Rs{imp_1h['max_dd_rs']:,.0f}", f"Rs{imp_15m['max_dd_rs']:,.0f}")
    row("Avg P&L/day",       f"Rs{cur['avg_day']:+,.0f}", f"Rs{imp_1h['avg_day']:+,.0f}", f"Rs{imp_15m['avg_day']:+,.0f}")
    row("Median day",        f"Rs{cur['median_day']:+,.0f}", f"Rs{imp_1h['median_day']:+,.0f}", f"Rs{imp_15m['median_day']:+,.0f}")
    row("Best day",          f"Rs{cur['best_day']:+,.0f}", f"Rs{imp_1h['best_day']:+,.0f}", f"Rs{imp_15m['best_day']:+,.0f}")
    row("Worst day",         f"Rs{cur['worst_day']:+,.0f}", f"Rs{imp_1h['worst_day']:+,.0f}", f"Rs{imp_15m['worst_day']:+,.0f}")
    sep("CONSISTENCY")
    gm1,rm1 = cur['green_m'],  cur['red_m']
    gm2,rm2 = imp_1h['green_m'],  imp_1h['red_m']
    gm3,rm3 = imp_15m['green_m'], imp_15m['red_m']
    row("Green months",      f"{gm1}/{gm1+rm1}", f"{gm2}/{gm2+rm2}", f"{gm3}/{gm3+rm3}")
    row("Red months",        f"{rm1}", f"{rm2}", f"{rm3}")
    row("Days >= Rs500",     f"{cur['days_500']}/{cur['total_day_obs']}", f"{imp_1h['days_500']}/{imp_1h['total_day_obs']}", f"{imp_15m['days_500']}/{imp_15m['total_day_obs']}")
    row("Profit days %",     f"{cur['days_profit']/cur['total_day_obs']*100:.0f}%", f"{imp_1h['days_profit']/imp_1h['total_day_obs']*100:.0f}%", f"{imp_15m['days_profit']/imp_15m['total_day_obs']*100:.0f}%")
    row("Loss days %",       f"{cur['days_loss']/cur['total_day_obs']*100:.0f}%", f"{imp_1h['days_loss']/imp_1h['total_day_obs']*100:.0f}%", f"{imp_15m['days_loss']/imp_15m['total_day_obs']*100:.0f}%")

    print(f"\n{W}")
    print(f"  YEAR-BY-YEAR  P&L  (Rs)")
    print(f"  {'Year':<8} {'CURRENT':>16}  {'IMPROVED 1h':>16}  {'IMPROVED 15m':>16}")
    print(f"  {'-'*60}")

    years_cur  = defaultdict(float)
    years_1h   = defaultdict(float)
    years_15m  = defaultdict(float)
    eq_c, eq_1, eq_15 = cur["capital"], imp_1h["capital"], imp_15m["capital"]

    def yr_pnl(s):
        d = defaultdict(float)
        eq = s["capital"]
        for mo, m in sorted(s["monthly"].items()):
            d[mo[:4]] += m["pnl"]
        return d

    yc  = yr_pnl(cur)
    y1h = yr_pnl(imp_1h)
    y15 = yr_pnl(imp_15m)

    all_years = sorted(set(list(yc.keys()) + list(y1h.keys()) + list(y15.keys())))
    for yr in all_years:
        vc  = yc.get(yr, 0)
        v1h = y1h.get(yr, 0)
        v15 = y15.get(yr, 0)
        tc  = "[+]" if vc  >= 0 else "[-]"
        t1h = "[+]" if v1h >= 0 else "[-]"
        t15 = "[+]" if v15 >= 0 else "[-]"
        print(f"  {yr:<8} Rs{vc:>+12,.0f}{tc}  Rs{v1h:>+12,.0f}{t1h}  Rs{v15:>+12,.0f}{t15}")

    print(f"  {'-'*60}")
    print(f"  {'TOTAL':<8} Rs{cur['final_eq']-cur['capital']:>+12,.0f}     Rs{imp_1h['final_eq']-imp_1h['capital']:>+12,.0f}     Rs{imp_15m['final_eq']-imp_15m['capital']:>+12,.0f}")
    print(f"\n{W}")
    print(f"  FINAL VERDICT (Plain English):")
    print(f"  Current  15m 30x : Rs 1,00,000 -> Rs{cur['final_eq']:,.0f}   ({cur['growth_pct']:+.0f}%)  DD={cur['max_dd_pct']:.0f}%")
    print(f"  Improved 1h  10x : Rs 1,00,000 -> Rs{imp_1h['final_eq']:,.0f}   ({imp_1h['growth_pct']:+.0f}%)  DD={imp_1h['max_dd_pct']:.0f}%")
    print(f"  Improved 15m 10x : Rs 1,00,000 -> Rs{imp_15m['final_eq']:,.0f}   ({imp_15m['growth_pct']:+.0f}%)  DD={imp_15m['max_dd_pct']:.0f}%")

    # Pick winner
    scores = [
        ("Current  15m 30x", cur,     cur['green_m'],     cur['max_dd_pct'],     cur['final_eq']),
        ("Improved 1h  10x", imp_1h,  imp_1h['green_m'],  imp_1h['max_dd_pct'],  imp_1h['final_eq']),
        ("Improved 15m 10x", imp_15m, imp_15m['green_m'], imp_15m['max_dd_pct'], imp_15m['final_eq']),
    ]
    winner = max(scores, key=lambda x: (x[2], -x[3], x[4]))
    print(f"\n  WINNER -> {winner[0]}")
    print(f"  Reason : Most green months ({winner[2]}), drawdown {winner[3]:.0f}%, final Rs{winner[4]:,.0f}")
    print(f"{W}")


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    CAPITAL   = 100_000
    RISK_FRAC = 0.05

    print("\n" + "="*72)
    print("  5-YEAR BACKTEST: Current Code vs All Improvements")
    print("  Capital: Rs 1,00,000  |  Risk: 5% per trade")
    print("="*72)
    print("\nFetching data...")

    c15 = fetch("ETH/USDT", "15m", years=5)
    c1h = fetch("ETH/USDT", "1h",  years=5)

    print("\nRunning backtests...")

    # ── CURRENT CODE (exact as-is) ─────────────────────────────────────────
    print("  [1/3] Current code  (TP=0.1375, SL=0.15, 30x, 15m, no fixes)...")
    t_cur  = backtest(c15, lev=30, tp_pct=0.1375, sl_pct=0.15,
                      cooldown_bars=0, min_spread=0.0)
    s_cur  = calc_stats(t_cur, CAPITAL, RISK_FRAC)

    # ── IMPROVED 1h ────────────────────────────────────────────────────────
    print("  [2/3] Improved 1h   (TP=0.60, SL=0.15, 10x, 1h,  cooldown=5, spread=0.05)...")
    t_1h   = backtest(c1h, lev=10, tp_pct=0.60, sl_pct=0.15,
                      cooldown_bars=5, min_spread=0.05)
    s_1h   = calc_stats(t_1h, CAPITAL, RISK_FRAC)

    # ── IMPROVED 15m ───────────────────────────────────────────────────────
    print("  [3/3] Improved 15m  (TP=0.60, SL=0.15, 10x, 15m, cooldown=5, spread=0.05)...")
    t_15m  = backtest(c15, lev=10, tp_pct=0.60, sl_pct=0.15,
                      cooldown_bars=5, min_spread=0.05)
    s_15m  = calc_stats(t_15m, CAPITAL, RISK_FRAC)

    # ── Print full detail for each ─────────────────────────────────────────
    show_full("CURRENT CODE  (as it runs today - no changes)",
              s_cur,  30, 0.1375, 0.15, "15m")
    show_full("IMPROVED 1h   (TP=0.60, SL=0.15, 10x, cooldown=5, spread=0.05)",
              s_1h,   10, 0.60,   0.15, "1h")
    show_full("IMPROVED 15m  (TP=0.60, SL=0.15, 10x, cooldown=5, spread=0.05)",
              s_15m,  10, 0.60,   0.15, "15m")

    three_way(s_cur, s_1h, s_15m)