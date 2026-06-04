"""
2-Year Backtest | ETH/USDT | Fisher Transform
Goal: Find config where profit is ALWAYS greater than loss per trade
      and monthly results are consistently green.

Tests:
  15-minute candles  (more trades, shorter holds)
  1-hour   candles   (fewer trades, cleaner signals)

R/R configs tested:
  Current : TP=13.75%  SL=15%   -> win gives LESS than loss (bad)
  2:1     : TP=30%     SL=15%   -> win gives 2x the loss    (good)
  3:1     : TP=45%     SL=15%   -> win gives 3x the loss    (better)
  4:1     : TP=60%     SL=15%   -> win gives 4x the loss    (strongest)
"""

import ccxt, time, math
from datetime import datetime, timedelta
from decimal import Decimal
from collections import defaultdict


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SIMPLE EXPLANATION FOR NEW TRADERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# TRADE = You enter (buy/sell), price moves, you exit at TP or SL
#
# TP (Take Profit) = price level where bot auto-exits with PROFIT
# SL (Stop Loss)   = price level where bot auto-exits with LOSS
#
# R/R (Risk to Reward) = how much you WIN vs how much you RISK
#   R/R = 1:1  ->  win Rs100, risk Rs100  (need >50% win rate to profit)
#   R/R = 2:1  ->  win Rs200, risk Rs100  (need >33% win rate to profit)
#   R/R = 3:1  ->  win Rs300, risk Rs100  (need >25% win rate to profit)
#   R/R = 4:1  ->  win Rs400, risk Rs100  (need >20% win rate to profit)
#
# KEY INSIGHT: Higher R/R = you can be WRONG more often and still profit
#
# Win Rate = what % of trades reach TP before SL
# Breakeven Win Rate = minimum win rate needed to not lose money
#   Formula: SL / (TP + SL) -> e.g. for 2:1: 15/(30+15) = 33.3%
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


# ── Fisher Transform (pure Python) ─────────────────────────────────────────
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


# ── Crossover detection ──────────────────────────────────────────────────────
def crossover(cf, ct, pf, pt, tol=0.001):
    if pf <= pt and cf > ct: return "above"
    if pf >= pt and cf < ct: return "below"
    if abs(cf - ct) <= tol and abs(pf - pt) > tol:
        return "above" if cf > ct else "below"
    return None


# ── TP / SL prices ──────────────────────────────────────────────────────────
def tp_sl(entry, side, lev, tp_pct, sl_pct):
    p   = Decimal(str(entry))
    tp  = p + p * Decimal(str(tp_pct)) / Decimal(str(lev))
    sl  = p - p * Decimal(str(sl_pct)) / Decimal(str(lev))
    if side == "sell":
        tp = p - p * Decimal(str(tp_pct)) / Decimal(str(lev))
        sl = p + p * Decimal(str(sl_pct)) / Decimal(str(lev))
    return float(tp), float(sl)


# ── Fetch candles from Binance ───────────────────────────────────────────────
def fetch(symbol, tf, years=2):
    ex     = ccxt.binance()
    end_ms = int(datetime.now().timestamp() * 1000)
    st_ms  = int((datetime.now() - timedelta(days=365 * years)).timestamp() * 1000)
    print(f"\nFetching {symbol} {tf} | {years} years ...")
    print(f"  From : {datetime.fromtimestamp(st_ms/1000).strftime('%Y-%m-%d')}")
    print(f"  To   : {datetime.fromtimestamp(end_ms/1000).strftime('%Y-%m-%d')}")
    bars, since = [], st_ms
    while since < end_ms:
        chunk = ex.fetch_ohlcv(symbol, tf, since=since, limit=1000)
        if not chunk: break
        bars.extend(chunk)
        since = chunk[-1][0] + 1
        print(f"  {len(bars):,} candles...", end="\r")
        time.sleep(0.25)
        if chunk[-1][0] >= end_ms: break
    candles = [{"t": b[0], "o": b[1], "h": b[2], "l": b[3], "c": b[4], "v": b[5]}
               for b in bars if b[0] <= end_ms]
    print(f"\n  Done: {len(candles):,} candles total\n")
    return candles


# ── Backtest engine ──────────────────────────────────────────────────────────
def backtest(candles, lookback=9, leverage=30, tp_pct=0.30, sl_pct=0.15):
    series = fisher_series(candles, lookback)
    trades, pos, last_sig = [], None, None

    for i in range(1, len(series)):
        cur = series[i];  prv = series[i - 1]
        cf  = round(cur["f"],  6);  ct = round(cur["tr"], 6)
        pf  = round(prv["f"],  6);  pt = round(prv["tr"], 6)
        px  = cur["c"]

        # ── check open position ──────────────────────────────────────────
        if pos:
            s, tp, sl, ep = pos["s"], pos["tp"], pos["sl"], pos["ep"]
            hit_tp = (s == "buy"  and px >= tp) or (s == "sell" and px <= tp)
            hit_sl = (s == "buy"  and px <= sl) or (s == "sell" and px >= sl)
            if hit_tp or hit_sl:
                exit_px = tp if hit_tp else sl
                raw     = (exit_px - ep) / ep * (1 if s == "buy" else -1)
                pnl_on_margin = raw * leverage
                trades.append({
                    "side":   s,
                    "ep":     ep,
                    "ex":     exit_px,
                    "why":    "TP" if hit_tp else "SL",
                    "pnl":    pnl_on_margin,
                    "entry_t": datetime.fromtimestamp(pos["t"] / 1000),
                    "exit_t":  datetime.fromtimestamp(cur["t"] / 1000),
                })
                pos, last_sig = None, None

        # ── detect signal ────────────────────────────────────────────────
        sig = None
        co  = crossover(cf, ct, pf, pt)
        if co:
            # Zone filter: buy only when both fisher & trigger negative,
            #              sell only when both positive
            if co == "above" and cf < 0 and ct < 0: sig = "buy"
            if co == "below" and cf > 0 and ct > 0: sig = "sell"

        if sig and not pos and sig != last_sig:
            tpp, slp = tp_sl(px, sig, leverage, tp_pct, sl_pct)
            pos = {"s": sig, "ep": px, "tp": tpp, "sl": slp, "t": cur["t"]}
            last_sig = sig

    return trades


# ── Statistics ───────────────────────────────────────────────────────────────
def calc_stats(trades, capital, risk_frac=0.05):
    """
    risk_frac = fraction of equity risked per trade (5% = safe)
    Each trade: margin = equity * risk_frac
    P&L = margin * pnl_on_margin
    """
    if not trades:
        return None

    wins   = [t for t in trades if t["why"] == "TP"]
    losses = [t for t in trades if t["why"] == "SL"]
    wr     = len(wins) / len(trades)
    avg_w  = sum(t["pnl"] for t in wins)   / len(wins)   if wins   else 0
    avg_l  = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    be_wr  = abs(avg_l) / (avg_w + abs(avg_l))

    # ── simulate compounding equity ───────────────────────────
    equity = capital
    eq_curve = [equity]
    daily_pnl = defaultdict(float)

    for t in trades:
        margin = equity * risk_frac
        pnl_rs = margin * t["pnl"]
        equity += pnl_rs
        eq_curve.append(equity)
        daily_pnl[t["exit_t"].date()] += pnl_rs

    # max drawdown
    peak, max_dd = eq_curve[0], 0
    for v in eq_curve:
        peak   = max(peak, v)
        max_dd = max(max_dd, (peak - v) / peak)

    # consecutive losses
    max_streak = streak = 0
    for t in trades:
        streak = streak + 1 if t["why"] == "SL" else 0
        max_streak = max(max_streak, streak)

    total_days = (trades[-1]["exit_t"] - trades[0]["entry_t"]).days or 1

    # monthly P&L
    monthly = defaultdict(lambda: {"rs": 0, "cnt": 0, "wins": 0})
    margin_tracker = capital  # re-simulate for per-trade margin tracking
    m_eq = capital
    for t in trades:
        m       = m_eq * risk_frac
        pnl_rs  = m * t["pnl"]
        m_eq   += pnl_rs
        k       = t["exit_t"].strftime("%Y-%m")
        monthly[k]["rs"]   += pnl_rs
        monthly[k]["cnt"]  += 1
        monthly[k]["wins"] += 1 if t["why"] == "TP" else 0

    green_months = sum(1 for d in monthly.values() if d["rs"] > 0)
    red_months   = sum(1 for d in monthly.values() if d["rs"] <= 0)

    all_daily = list(daily_pnl.values())

    return {
        "total":       len(trades),
        "wins":        len(wins),
        "losses":      len(losses),
        "wr":          wr,
        "avg_w":       avg_w,
        "avg_l":       avg_l,
        "be_wr":       be_wr,
        "has_edge":    wr > be_wr,
        "trades_day":  len(trades) / total_days,
        "final_eq":    equity,
        "max_dd":      max_dd,
        "max_dd_rs":   capital * max_dd,
        "avg_day":     (equity - capital) / total_days,
        "days_500p":   sum(1 for v in all_daily if v >= 500),
        "days_profit": sum(1 for v in all_daily if v > 0),
        "days_loss":   sum(1 for v in all_daily if v < 0),
        "total_day_obs": len(all_daily),
        "total_days":  total_days,
        "max_streak":  max_streak,
        "green_months": green_months,
        "red_months":  red_months,
        "monthly":     monthly,
        "best_day":    max(all_daily) if all_daily else 0,
        "worst_day":   min(all_daily) if all_daily else 0,
        "median_day":  sorted(all_daily)[len(all_daily)//2] if all_daily else 0,
        "capital":     capital,
        "risk_frac":   risk_frac,
    }


# ── Print one result block ───────────────────────────────────────────────────
def show(label, s, tp_pct, sl_pct, tf_label):
    rr = tp_pct / sl_pct
    be = sl_pct / (tp_pct + sl_pct) * 100
    W = "="*68

    # Edge explanation
    if s["has_edge"]:
        verdict = f"PROFITABLE  (+{(s['wr'] - s['be_wr'])*100:.1f}% above breakeven)"
    else:
        verdict = f"LOSING  ({(s['wr'] - s['be_wr'])*100:.1f}% below breakeven — avoid)"

    win_rs  =  s["avg_w"] * (s["capital"] * s["risk_frac"])
    loss_rs =  abs(s["avg_l"]) * (s["capital"] * s["risk_frac"])

    print(f"\n{W}")
    print(f"  [{tf_label}]  {label}")
    print(f"  R/R = {rr:.0f}:1  |  Each WIN = +Rs{win_rs:,.0f}  |  Each LOSS = -Rs{loss_rs:,.0f}")
    print(f"  Breakeven win rate = {be:.0f}%  (need to win at least {be:.0f}% of trades)")
    print(f"{W}")
    print(f"  VERDICT  : {verdict}")
    print(f"  Win Rate : {s['wr']*100:.1f}%  ({s['wins']} wins / {s['total']} trades)")
    print(f"  Trades   : {s['total']:,} total  ({s['trades_day']:.1f}/day)")
    print(f"  Max losing streak: {s['max_streak']} trades in a row")
    print(f"  {'-'*64}")
    print(f"  CAPITAL GROWTH  (starting Rs{s['capital']:,.0f}, risking {s['risk_frac']*100:.0f}%/trade)")
    print(f"  Final capital  : Rs{s['final_eq']:,.0f}  ({(s['final_eq']/s['capital']-1)*100:+.0f}% over {s['total_days']} days)")
    print(f"  Max drawdown   : Rs{s['max_dd_rs']:,.0f}  ({s['max_dd']*100:.1f}%)")
    print(f"  Avg daily P&L  : Rs{s['avg_day']:+,.0f}")
    print(f"  Median day     : Rs{s['median_day']:+,.0f}  |  Best: Rs{s['best_day']:+,.0f}  |  Worst: Rs{s['worst_day']:+,.0f}")
    print(f"  {'-'*64}")
    td = s["total_day_obs"]
    print(f"  DAILY Rs500 TARGET")
    print(f"  Days >= Rs500   : {s['days_500p']}/{td}  ({s['days_500p']/td*100:.0f}% of days)")
    print(f"  Profitable days : {s['days_profit']}/{td}  ({s['days_profit']/td*100:.0f}%)")
    print(f"  Loss days       : {s['days_loss']}/{td}  ({s['days_loss']/td*100:.0f}%)")
    print(f"  {'-'*64}")
    gm = s["green_months"]; rm = s["red_months"]; tm = gm + rm
    print(f"  MONTHLY CONSISTENCY")
    print(f"  Green months : {gm}/{tm}  |  Red months : {rm}/{tm}")
    print(f"")
    print(f"  {'Month':<10} {'Trades':>7} {'WR%':>7} {'P&L (Rs)':>12}  {'':>4}")
    for mo, d in sorted(s["monthly"].items()):
        wr_m = d["wins"] / d["cnt"] * 100 if d["cnt"] else 0
        bar  = "[+]" if d["rs"] >= 0 else "[-]"
        print(f"  {mo:<10} {d['cnt']:>7} {wr_m:>6.1f}%  Rs{d['rs']:>+10,.0f}  {bar}")
    print(f"{W}")


# ── Summary table ────────────────────────────────────────────────────────────
def summary(all_results):
    W = "="*80
    print(f"\n\n{W}")
    print("  FINAL COMPARISON  |  2-Year Backtest  |  Rs 1,00,000 capital  |  5% risk/trade")
    print(f"{W}")
    print(f"  {'Config':<36} {'WR%':>6} {'R/R':>5} {'AvgDay':>10} {'MaxDD':>8} {'GreenMo':>8} {'Rs500d':>8}")
    print(f"  {'-'*76}")
    for label, s, tp, sl, tf in all_results:
        gm = s["green_months"]; tm = gm + s["red_months"]
        td = s["total_day_obs"]
        rr = f"{tp/sl:.0f}:1"
        print(f"  {label:<36} {s['wr']*100:>5.1f}% {rr:>5} Rs{s['avg_day']:>+7,.0f} "
              f"{s['max_dd']*100:>7.1f}% {gm:>4}/{tm:<4} {s['days_500p']:>4}/{td}")
    print(f"{W}")

    # Pick best by: green months first, then avg daily P&L, then drawdown
    def score(r):
        _, s, _, _, _ = r
        return (s["green_months"], s["avg_day"], -s["max_dd"])

    best = max(all_results, key=score)
    blabel, bs, btp, bsl, btf = best

    print(f"\n  RECOMMENDED CONFIG : {blabel}")
    print(f"  Why: Most consistent ({bs['green_months']}/{bs['green_months']+bs['red_months']} green months),")
    print(f"       avg Rs{bs['avg_day']:,.0f}/day, max drawdown {bs['max_dd']*100:.1f}%")
    print(f"\n  TO USE THIS IN YOUR BOT:")
    print(f"  Set in .env or config.py:")
    print(f"    TP_PCT = {btp}")
    print(f"    SL_PCT = {bsl}")
    print(f"    RESOLUTION = {btf.replace('m','').replace('h','')+'m' if 'h' not in btf else btf}")
    print(f"{W}")


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    CAPITAL   = 100_000   # Rs 1,00,000
    RISK_FRAC = 0.05      # risk 5% of equity per trade (safe, half-Kelly)
    LEVERAGE  = 30

    # --- EXPLANATION printed first ----------------------------------------
    print("\n" + "="*68)
    print("  WHAT WE ARE TESTING  (Simple Explanation)")
    print("="*68)
    print("""
  The bot buys or sells ETH when Fisher Transform crosses its Trigger line.
  It exits when price hits Take Profit (TP) or Stop Loss (SL).

  CURRENT PROBLEM:
    TP = 13.75%  SL = 15%
    Each WIN gives Rs 688  |  Each LOSS costs Rs 750
    -> Loss is BIGGER than Win. That is BAD.

  WHAT WE FIX:
    We test configs where TP is 2x, 3x, 4x bigger than SL.
    This way even if we win only 30-35% of trades, we profit.

  TIMEFRAMES:
    15m candles = more trades, faster signals (noisier)
    1h  candles = fewer trades, cleaner signals (recommended)
""")
    print("="*68)

    # ------------------------------------------------------------------
    # Fetch data for both timeframes
    # ------------------------------------------------------------------
    candles_15m = fetch("ETH/USDT", "15m", years=2)
    candles_1h  = fetch("ETH/USDT", "1h",  years=2)

    # ------------------------------------------------------------------
    # Define configs to test
    # Label, tp_pct, sl_pct, candles, tf_label
    # ------------------------------------------------------------------
    configs = [
        # 15-minute
        ("15m | Current   TP=13.75% SL=15% (R/R 0.9:1)", 0.1375, 0.15, candles_15m, "15m"),
        ("15m | 2:1 ratio TP=30%    SL=15%",              0.30,   0.15, candles_15m, "15m"),
        ("15m | 3:1 ratio TP=45%    SL=15%",              0.45,   0.15, candles_15m, "15m"),
        ("15m | 4:1 ratio TP=60%    SL=15%",              0.60,   0.15, candles_15m, "15m"),
        # 1-hour
        ("1h  | Current   TP=13.75% SL=15% (R/R 0.9:1)", 0.1375, 0.15, candles_1h,  "1h"),
        ("1h  | 2:1 ratio TP=30%    SL=15%",              0.30,   0.15, candles_1h,  "1h"),
        ("1h  | 3:1 ratio TP=45%    SL=15%",              0.45,   0.15, candles_1h,  "1h"),
        ("1h  | 4:1 ratio TP=60%    SL=15%",              0.60,   0.15, candles_1h,  "1h"),
    ]

    all_results = []
    for label, tp, sl, candles, tf_label in configs:
        print(f"Testing: {label} ...")
        trades = backtest(candles, lookback=9, leverage=LEVERAGE, tp_pct=tp, sl_pct=sl)
        s = calc_stats(trades, CAPITAL, RISK_FRAC)
        if s:
            show(label, s, tp, sl, tf_label)
            all_results.append((label, s, tp, sl, tf_label))
        else:
            print(f"  [!] No trades generated for {label}")

    summary(all_results)