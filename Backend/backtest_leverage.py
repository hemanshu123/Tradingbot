"""
5-Year Backtest: 1h timeframe, all improvements, different leverage
Testing: 5x  10x  20x  30x
Fixed:   TP=0.60  SL=0.15  cooldown=5bars  spread=0.05  lookback=9
Capital: Rs 1,00,000  |  Risk 5% per trade
"""

import ccxt, time, math
from datetime import datetime, timedelta
from decimal import Decimal
from collections import defaultdict


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


def crossover(cf, ct, pf, pt, tol=0.001):
    if pf <= pt and cf > ct: return "above"
    if pf >= pt and cf < ct: return "below"
    if abs(cf - ct) <= tol and abs(pf - pt) > tol:
        return "above" if cf > ct else "below"
    return None


def tp_sl_prices(entry, side, lev, tp_pct, sl_pct):
    p = Decimal(str(entry))
    if side == "buy":
        return (float(p + p * Decimal(str(tp_pct)) / Decimal(str(lev))),
                float(p - p * Decimal(str(sl_pct)) / Decimal(str(lev))))
    return (float(p - p * Decimal(str(tp_pct)) / Decimal(str(lev))),
            float(p + p * Decimal(str(sl_pct)) / Decimal(str(lev))))


def fetch(symbol, tf, years=5):
    ex     = ccxt.binance()
    end_ms = int(datetime.now().timestamp() * 1000)
    st_ms  = int((datetime.now() - timedelta(days=365 * years)).timestamp() * 1000)
    print(f"  Fetching {symbol} {tf} ({years}yr)...", end=" ", flush=True)
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
          f"({datetime.fromtimestamp(candles[0]['t']/1000).strftime('%Y-%m-%d')} "
          f"to {datetime.fromtimestamp(candles[-1]['t']/1000).strftime('%Y-%m-%d')})")
    return candles


def backtest(candles, lev, tp_pct=0.60, sl_pct=0.15,
             cooldown_bars=5, min_spread=0.05, lookback=9):
    series = fisher_series(candles, lookback)
    trades, pos, last_sig, cooldown = [], None, None, 0

    for i in range(1, len(series)):
        cur = series[i];  prv = series[i - 1]
        cf  = round(cur["f"],  6);  ct = round(cur["tr"], 6)
        pf  = round(prv["f"],  6);  pt = round(prv["tr"], 6)
        px  = cur["c"]

        if cooldown > 0:
            cooldown -= 1

        if pos:
            s, tp, sl, ep = pos["s"], pos["tp"], pos["sl"], pos["ep"]
            hit_tp = (s=="buy" and px>=tp) or (s=="sell" and px<=tp)
            hit_sl = (s=="buy" and px<=sl) or (s=="sell" and px>=sl)
            if hit_tp or hit_sl:
                exit_px = tp if hit_tp else sl
                raw = (exit_px - ep) / ep * (1 if s=="buy" else -1)
                trades.append({
                    "side":    s,
                    "ep": ep, "ex": exit_px,
                    "why":     "TP" if hit_tp else "SL",
                    "pnl":     raw * lev,
                    "entry_t": datetime.fromtimestamp(pos["t"] / 1000),
                    "exit_t":  datetime.fromtimestamp(cur["t"] / 1000),
                })
                if hit_sl: cooldown = cooldown_bars
                pos, last_sig = None, None

        if cooldown > 0: continue

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


def calc_stats(trades, capital=100_000, risk_frac=0.05):
    if not trades: return None
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

    peak, max_dd = eq_curve[0], 0.0
    for v in eq_curve:
        peak   = max(peak, v)
        max_dd = max(max_dd, (peak - v) / peak)

    max_streak = streak = 0
    for t in trades:
        streak = streak + 1 if t["why"] == "SL" else 0
        max_streak = max(max_streak, streak)

    ws = run = 0
    for t in trades:
        run = run + 1 if t["why"] == "SL" else 0
        if run == 3: ws += 1

    total_days = (trades[-1]["exit_t"] - trades[0]["entry_t"]).days or 1

    monthly = defaultdict(lambda: {"pnl": 0, "cnt": 0, "wins": 0})
    eq2 = capital
    for t in trades:
        m  = eq2 * risk_frac; pr = m * t["pnl"]; eq2 += pr
        k  = t["exit_t"].strftime("%Y-%m")
        monthly[k]["pnl"]  += pr
        monthly[k]["cnt"]  += 1
        monthly[k]["wins"] += 1 if t["why"] == "TP" else 0

    all_d = list(daily.values())
    return {
        "total": len(trades), "wins": len(wins), "losses": len(losses),
        "wr": wr, "avg_w": avg_w*100, "avg_l": abs(avg_l)*100,
        "be_wr": be_wr*100, "has_edge": wr > be_wr,
        "trades_day": len(trades)/total_days,
        "final_eq": equity, "growth_pct": (equity/capital-1)*100,
        "max_dd_pct": max_dd*100, "max_dd_rs": max_dd * equity,
        "avg_day": (equity-capital)/total_days,
        "days_500": sum(1 for v in all_d if v>=500),
        "days_profit": sum(1 for v in all_d if v>0),
        "days_loss": sum(1 for v in all_d if v<0),
        "total_day_obs": len(all_d), "total_days": total_days,
        "max_streak": max_streak, "whipsaws": ws,
        "green_m": sum(1 for d in monthly.values() if d["pnl"]>0),
        "red_m":   sum(1 for d in monthly.values() if d["pnl"]<=0),
        "monthly": monthly,
        "best_day": max(all_d) if all_d else 0,
        "worst_day": min(all_d) if all_d else 0,
        "median_day": sorted(all_d)[len(all_d)//2] if all_d else 0,
        "capital": capital,
    }


def show_detail(label, s, lev, tp_pct, sl_pct):
    tp_move  = tp_pct / lev * 100
    sl_move  = sl_pct / lev * 100
    liq_move = 100 / lev           # approx liquidation distance
    win_rs   = s["capital"] * 0.05 * tp_pct
    loss_rs  = s["capital"] * 0.05 * sl_pct
    gm, rm   = s["green_m"], s["red_m"]
    td       = s["total_day_obs"]
    W        = "=" * 72

    print(f"\n{W}")
    print(f"  {label}")
    print(f"{W}")
    print(f"  Leverage  : {lev}x")
    print(f"  Per trade : TP at +{tp_move:.1f}% price move  |  SL at -{sl_move:.1f}% price move")
    print(f"  Per trade : WIN = +Rs{win_rs:,.0f}  |  LOSS = -Rs{loss_rs:,.0f}  (on Rs5k margin)")
    print(f"  Liquidation distance: ~{liq_move:.1f}% adverse move")
    print(f"  R/R : {tp_pct/sl_pct:.0f}:1  |  Need >{s['be_wr']:.0f}% win rate to profit")
    print(f"{'-'*72}")
    e = "EDGE EXISTS" if s["has_edge"] else "NO EDGE"
    print(f"  VERDICT     : {e}")
    print(f"  Win Rate    : {s['wr']*100:.1f}%  (breakeven={s['be_wr']:.0f}%)")
    print(f"  Trades      : {s['total']:,} total  |  {s['trades_day']:.1f}/day")
    print(f"  Whipsaws    : {s['whipsaws']} clusters  |  Max SL streak: {s['max_streak']}")
    print(f"{'-'*72}")
    print(f"  MONEY  (Rs1,00,000 start | 5% risk/trade)")
    print(f"  Final       : Rs{s['final_eq']:>14,.0f}   ({s['growth_pct']:+.0f}% in {s['total_days']}d)")
    print(f"  Max DD      : {s['max_dd_pct']:.1f}%   (Rs{s['max_dd_rs']:,.0f} worst peak-to-trough)")
    print(f"  Avg/day     : Rs{s['avg_day']:>+14,.0f}")
    print(f"  Median day  : Rs{s['median_day']:>+14,.0f}")
    print(f"  Best day    : Rs{s['best_day']:>+14,.0f}")
    print(f"  Worst day   : Rs{s['worst_day']:>+14,.0f}")
    print(f"{'-'*72}")
    print(f"  Rs500/day   : {s['days_500']}/{td}  ({s['days_500']/td*100:.0f}%)")
    print(f"  Profit days : {s['days_profit']}/{td}  ({s['days_profit']/td*100:.0f}%)")
    print(f"  Green months: {gm}/{gm+rm}  |  Red months: {rm}/{gm+rm}")
    print(f"{'-'*72}")
    print(f"  YEAR-BY-YEAR P&L:")

    yrs = defaultdict(float)
    eq2 = s["capital"]
    for mo, d in sorted(s["monthly"].items()):
        yrs[mo[:4]] += d["pnl"]
    for yr, v in sorted(yrs.items()):
        tag = "[+]" if v >= 0 else "[-]"
        print(f"    {yr}  Rs{v:>+12,.0f}  {tag}")
    print(f"{W}")


def summary_table(results):
    W = "=" * 88
    print(f"\n\n{W}")
    print(f"  LEVERAGE COMPARISON  |  1h  TP=0.60  SL=0.15  |  5yr  Rs1,00,000  5%/trade")
    print(f"{W}")

    levcols = [r["lev"] for r in results]
    header  = f"  {'Metric':<30}"
    for r in results:
        header += f"  {'LEV '+str(r['lev'])+'x':>14}"
    print(header)
    print(f"  {'-'*84}")

    def row(name, fn):
        line = f"  {name:<30}"
        for r in results:
            line += f"  {fn(r['s'], r['lev']):>14}"
        print(line)

    def sep():
        print(f"  {'-'*84}")

    row("TP price move",   lambda s,l: f"+{0.60/l*100:.1f}%")
    row("SL price move",   lambda s,l: f"-{0.15/l*100:.2f}%")
    row("Liq. distance",   lambda s,l: f"~{100/l:.1f}% move")
    row("Win/trade (Rs)",  lambda s,l: f"Rs{s['capital']*0.05*0.60:,.0f}")
    row("Loss/trade (Rs)", lambda s,l: f"Rs{s['capital']*0.05*0.15:,.0f}")
    sep()
    row("Win Rate",        lambda s,l: f"{s['wr']*100:.1f}%")
    row("Breakeven WR",    lambda s,l: f"{s['be_wr']:.0f}%")
    row("Has Edge?",       lambda s,l: "YES" if s["has_edge"] else "NO")
    row("Trades / day",    lambda s,l: f"{s['trades_day']:.1f}")
    row("Whipsaws",        lambda s,l: f"{s['whipsaws']}")
    row("Max SL streak",   lambda s,l: f"{s['max_streak']}")
    sep()
    row("Final capital",   lambda s,l: f"Rs{s['final_eq']:,.0f}")
    row("Total growth",    lambda s,l: f"{s['growth_pct']:+.0f}%")
    row("Max drawdown",    lambda s,l: f"{s['max_dd_pct']:.1f}%")
    row("Max DD Rs",       lambda s,l: f"Rs{s['max_dd_rs']:,.0f}")
    row("Avg day P&L",     lambda s,l: f"Rs{s['avg_day']:+,.0f}")
    row("Median day",      lambda s,l: f"Rs{s['median_day']:+,.0f}")
    row("Best day",        lambda s,l: f"Rs{s['best_day']:+,.0f}")
    row("Worst day",       lambda s,l: f"Rs{s['worst_day']:+,.0f}")
    sep()
    row("Green months",    lambda s,l: f"{s['green_m']}/{s['green_m']+s['red_m']}")
    row("Red months",      lambda s,l: f"{s['red_m']}")
    row("Days >= Rs500",   lambda s,l: f"{s['days_500']}/{s['total_day_obs']}")
    row("Profit days %",   lambda s,l: f"{s['days_profit']/s['total_day_obs']*100:.0f}%")
    row("Loss days %",     lambda s,l: f"{s['days_loss']/s['total_day_obs']*100:.0f}%")

    print(f"\n{W}")

    # Year-by-year grid
    print(f"  YEAR-BY-YEAR P&L (Rs)")
    hdr = f"  {'Year':<8}"
    for r in results: hdr += f"  {'LEV '+str(r['lev'])+'x':>18}"
    print(hdr)
    print(f"  {'-'*84}")

    # collect years
    all_yrs = set()
    for r in results:
        for mo in r["s"]["monthly"]: all_yrs.add(mo[:4])

    for yr in sorted(all_yrs):
        line = f"  {yr:<8}"
        for r in results:
            yv = sum(d["pnl"] for mo, d in r["s"]["monthly"].items() if mo[:4]==yr)
            tag = "[+]" if yv >= 0 else "[-]"
            line += f"  Rs{yv:>+12,.0f}{tag}"
        print(line)

    print(f"  {'-'*84}")
    totline = f"  {'TOTAL':<8}"
    for r in results:
        totline += f"  Rs{r['s']['final_eq']-r['s']['capital']:>+12,.0f}   "
    print(totline)

    print(f"\n{W}")

    # Winner
    def score(r):
        s = r["s"]
        return (s["green_m"], s["final_eq"], -s["max_dd_pct"])

    ranked = sorted(results, key=score, reverse=True)
    print(f"  RANKED BY: green months > final capital > lowest drawdown")
    print(f"  {'-'*84}")
    for i, r in enumerate(ranked, 1):
        s = r["s"]
        print(f"  #{i}  Leverage {r['lev']:2}x  |  "
              f"Final Rs{s['final_eq']:>10,.0f}  |  "
              f"DD {s['max_dd_pct']:5.1f}%  |  "
              f"Green {s['green_m']}/{s['green_m']+s['red_m']} months  |  "
              f"Avg Rs{s['avg_day']:+,.0f}/day")

    best = ranked[0]
    bs   = best["s"]
    print(f"\n  BEST LEVERAGE: {best['lev']}x")
    print(f"  Rs1,00,000 -> Rs{bs['final_eq']:,.0f}  ({bs['growth_pct']:+.0f}%)")
    print(f"  Max drawdown {bs['max_dd_pct']:.1f}%  |  {bs['green_m']}/{bs['green_m']+bs['red_m']} green months")
    print(f"  Liquidation at ~{100/best['lev']:.0f}% adverse move  (safe for crypto)")
    print(f"{W}")


if __name__ == "__main__":
    CAPITAL   = 100_000
    RISK_FRAC = 0.05
    TP        = 0.60
    SL        = 0.15

    print("\n" + "="*72)
    print("  LEVERAGE TEST  |  1h  TP=0.60  SL=0.15  cooldown=5  spread=0.05")
    print("  5-Year ETH/USDT  |  Rs1,00,000  |  5% risk per trade")
    print("="*72)

    print("\nFetching 5yr 1h data...")
    c1h = fetch("ETH/USDT", "1h", years=5)

    leverages = [5, 10, 20, 30]
    results   = []

    for lev in leverages:
        print(f"\n  Running leverage {lev}x ...", end=" ", flush=True)
        trades = backtest(c1h, lev=lev, tp_pct=TP, sl_pct=SL,
                          cooldown_bars=5, min_spread=0.05)
        s = calc_stats(trades, CAPITAL, RISK_FRAC)
        results.append({"lev": lev, "s": s})
        print(f"done  ({len(trades)} trades  WR={s['wr']*100:.1f}%  Final=Rs{s['final_eq']:,.0f})")

    print("\n")
    for r in results:
        show_detail(f"LEVERAGE {r['lev']}x  |  1h  TP=0.60  SL=0.15  +fixes",
                    r["s"], r["lev"], TP, SL)

    summary_table(results)