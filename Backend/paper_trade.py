"""
Paper Trading — zero real orders, full simulation
Runs TWO virtual accounts simultaneously:
  Account A : 10x leverage  (safe starter config)
  Account B : 20x leverage  (future config once profitable)

Both use: TP=0.60  SL=0.15  1h  cooldown=5  spread>=0.05
Virtual capital: Rs 1,00,000 each  |  Risk: 5% per trade
"""

import time, json, os, sys, math
from datetime import datetime
from decimal import Decimal
from collections import defaultdict

from bot.config import (LOOKBACK, POLL_SEC, TP_PCT, SL_PCT,
                        SL_COOLDOWN_BARS, MIN_FISHER_SPREAD, RESOLUTION)
from bot.fisher_transform import get_live_fisher_data

if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

VIRTUAL_CAPITAL = 100_000   # Rs 1,00,000 virtual money per account
RISK_FRAC       = 0.05      # risk 5% of equity per trade
FLOAT_TOL       = 0.001

RUNTIME = "runtime"
os.makedirs(RUNTIME, exist_ok=True)

# ── helpers ──────────────────────────────────────────────────────────────────
def rjson(path, default=None):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except: return default

def wjson(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def tp_sl_calc(entry, side, lev):
    p   = Decimal(str(entry))
    tpo = p * Decimal(str(TP_PCT)) / Decimal(str(lev))
    slo = p * Decimal(str(SL_PCT)) / Decimal(str(lev))
    if side == "buy":
        return float(p + tpo), float(p - slo)
    return float(p - tpo), float(p + slo)

def detect_co(cf, ct, pf, pt):
    if pf <= pt and cf > ct: return "above"
    if pf >= pt and cf < ct: return "below"
    if abs(cf-ct) <= FLOAT_TOL and abs(pf-pt) > FLOAT_TOL:
        return "above" if cf > ct else "below"
    return None


# ── Virtual account ───────────────────────────────────────────────────────────
class VirtualAccount:
    def __init__(self, leverage):
        self.lev       = leverage
        self.f_pos     = os.path.join(RUNTIME, f"paper_{leverage}x_position.json")
        self.f_trades  = os.path.join(RUNTIME, f"paper_{leverage}x_trades.json")
        self.f_log     = os.path.join(RUNTIME, f"paper_{leverage}x_log.jsonl")

        saved          = rjson(self.f_trades, {})
        self.equity    = float(saved.get("equity", VIRTUAL_CAPITAL))
        self.trades    = saved.get("trades",  [])
        self.position  = rjson(self.f_pos) or None
        self.last_sig  = None
        self.cooldown  = 0
        self.last_ct   = None          # last candle time seen

    # ── candle tick ───────────────────────────────────────────────────────────
    def on_candle(self, ct):
        if ct != self.last_ct:
            self.last_ct = ct
            if self.cooldown > 0:
                self.cooldown -= 1

    # ── TP/SL check ───────────────────────────────────────────────────────────
    def check_exit(self, price, ct):
        if not self.position:
            return None
        s, tp, sl, ep = (self.position["side"], self.position["tp"],
                         self.position["sl"],   self.position["entry_price"])
        hit_tp = (s=="buy"  and price>=tp) or (s=="sell" and price<=tp)
        hit_sl = (s=="buy"  and price<=sl) or (s=="sell" and price>=sl)
        if not (hit_tp or hit_sl):
            return None

        reason  = "TP" if hit_tp else "SL"
        exit_px = tp if hit_tp else sl
        margin  = self.equity * RISK_FRAC
        raw_pct = (exit_px - ep) / ep * (1 if s=="buy" else -1)
        pnl_frac= raw_pct * self.lev          # fraction on margin (e.g. 0.60 or -0.15)
        pnl_rs  = round(margin * pnl_frac, 2) # actual Rs P&L

        self.equity = round(self.equity + pnl_rs, 2)

        trade = {
            "no":          len(self.trades) + 1,
            "leverage":    self.lev,
            "side":        s,
            "entry_price": round(ep, 2),
            "exit_price":  round(exit_px, 2),
            "reason":      reason,
            "margin_rs":   round(margin, 2),
            "pnl_rs":      pnl_rs,
            "pnl_pct_margin": round(pnl_frac * 100, 2),
            "equity_after":self.equity,
            "opened_at":   self.position.get("opened_at"),
            "closed_at":   datetime.now().isoformat(),
        }
        self.trades.append(trade)
        wjson(self.f_trades, {"equity": self.equity, "trades": self.trades})

        # log line
        with open(self.f_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(trade) + "\n")

        self.position = None
        wjson(self.f_pos, {})
        self.last_sig = None

        if reason == "SL":
            self.cooldown = SL_COOLDOWN_BARS

        return trade

    # ── open new position ─────────────────────────────────────────────────────
    def try_enter(self, signal, price, spread):
        if (not signal or self.position
                or self.cooldown > 0
                or spread < MIN_FISHER_SPREAD
                or signal == self.last_sig):
            return False

        tp, sl    = tp_sl_calc(price, signal, self.lev)
        margin_rs = round(self.equity * RISK_FRAC, 2)
        self.position = {
            "leverage":    self.lev,
            "side":        signal,
            "entry_price": float(price),
            "tp":          tp,
            "sl":          sl,
            "margin_rs":   margin_rs,
            "tp_move_pct": round(TP_PCT / self.lev * 100, 2),
            "sl_move_pct": round(SL_PCT / self.lev * 100, 2),
            "opened_at":   datetime.now().isoformat(),
        }
        wjson(self.f_pos, self.position)
        self.last_sig = signal
        return True

    # ── live unrealized P&L ───────────────────────────────────────────────────
    def unrealized(self, price):
        if not self.position:
            return 0.0, 0.0
        ep     = self.position["entry_price"]
        s      = self.position["side"]
        margin = self.position["margin_rs"]
        raw    = (price - ep) / ep * (1 if s=="buy" else -1)
        pct    = raw * self.lev * 100
        rs     = round(margin * raw * self.lev, 2)
        return round(pct, 2), rs

    # ── full summary for API ──────────────────────────────────────────────────
    def summary(self, current_price):
        wins   = [t for t in self.trades if t["reason"] == "TP"]
        losses = [t for t in self.trades if t["reason"] == "SL"]
        u_pct, u_rs = self.unrealized(current_price)
        total_pnl_rs = sum(t["pnl_rs"] for t in self.trades)

        # daily P&L
        daily = defaultdict(float)
        for t in self.trades:
            day = t["closed_at"][:10]
            daily[day] += t["pnl_rs"]

        last5 = self.trades[-5:] if self.trades else []

        return {
            "leverage":            self.lev,
            "virtual_capital":     VIRTUAL_CAPITAL,
            "current_equity":      round(self.equity, 2),
            "total_profit_rs":     round(total_pnl_rs, 2),
            "growth_pct":          round((self.equity / VIRTUAL_CAPITAL - 1) * 100, 2),
            "open_position":       self.position,
            "unrealized_pnl_pct":  u_pct,
            "unrealized_pnl_rs":   u_rs,
            "total_trades":        len(self.trades),
            "wins":                len(wins),
            "losses":              len(losses),
            "win_rate_pct":        round(len(wins) / len(self.trades) * 100, 1) if self.trades else 0,
            "avg_win_rs":          round(sum(t["pnl_rs"] for t in wins)   / len(wins),   2) if wins   else 0,
            "avg_loss_rs":         round(sum(t["pnl_rs"] for t in losses) / len(losses), 2) if losses else 0,
            "cooldown_remaining":  self.cooldown,
            "daily_pnl":           dict(sorted(daily.items())),
            "last_5_trades":       last5,
            "all_trades":          self.trades,
        }


# ── main loop ─────────────────────────────────────────────────────────────────
def main():
    acc = {10: VirtualAccount(10), 20: VirtualAccount(20)}
    prev_f = prev_t = None

    print(f"[{datetime.now().isoformat()}] Paper trading started")
    print(f"[paper] Virtual capital: Rs{VIRTUAL_CAPITAL:,} each account | Risk: {RISK_FRAC*100:.0f}%/trade")
    print(f"[paper] TP={TP_PCT} ({TP_PCT/10*100:.0f}% move at 10x / {TP_PCT/20*100:.0f}% at 20x)")
    print(f"[paper] SL={SL_PCT} ({SL_PCT/10*100:.0f}% move at 10x / {SL_PCT/20*100:.0f}% at 20x)")
    print(f"[paper] Resolution={RESOLUTION}  Cooldown={SL_COOLDOWN_BARS}  MinSpread={MIN_FISHER_SPREAD}")
    print()

    while True:
        try:
            data = get_live_fisher_data(LOOKBACK)
            if not data:
                time.sleep(POLL_SEC)
                continue

            cf  = round(data["fisher"],  6)
            ct  = round(data["trigger"], 6)
            px  = float(data["close"])
            clt = data.get("time")
            sp  = round(abs(cf - ct), 6)

            for a in acc.values():
                a.on_candle(clt)

            # check exits
            for lev, a in acc.items():
                t = a.check_exit(px, clt)
                if t:
                    print(f"[paper {lev}x] {t['reason']} | {t['side'].upper()} "
                          f"entry={t['entry_price']} exit={t['exit_price']} "
                          f"PnL=Rs{t['pnl_rs']:+,.2f} ({t['pnl_pct_margin']:+.1f}% on margin) "
                          f"Equity=Rs{t['equity_after']:,.2f}")

            # detect signal
            signal = None
            if prev_f is not None:
                co = detect_co(cf, ct, prev_f, prev_t)
                if co:
                    if co=="above" and cf<0 and ct<0: signal="buy"
                    if co=="below" and cf>0 and ct>0: signal="sell"

            # try enter both accounts
            for lev, a in acc.items():
                if a.try_enter(signal, px, sp):
                    tp, sl = tp_sl_calc(px, signal, lev)
                    print(f"[paper {lev}x] OPENED {signal.upper()} | "
                          f"entry={px:.2f} TP={tp:.2f} SL={sl:.2f} "
                          f"margin=Rs{a.position['margin_rs']:,.2f}")

            # print live status
            u10_pct, u10_rs = acc[10].unrealized(px)
            u20_pct, u20_rs = acc[20].unrealized(px)
            p10 = acc[10].position
            p20 = acc[20].position
            print(f"[paper] {datetime.now().strftime('%H:%M:%S')} "
                  f"ETH=${px:.2f} | "
                  f"10x: eq=Rs{acc[10].equity:,.0f} "
                  f"{'['+p10['side'].upper()+' unreal=Rs'+str(u10_rs)+']' if p10 else '[flat]'} | "
                  f"20x: eq=Rs{acc[20].equity:,.0f} "
                  f"{'['+p20['side'].upper()+' unreal=Rs'+str(u20_rs)+']' if p20 else '[flat]'}")

            # save full snapshot for API
            snap = {
                "time":    datetime.now().isoformat(),
                "price":   px,
                "fisher":  cf,
                "trigger": ct,
                "spread":  sp,
                "10x":     acc[10].summary(px),
                "20x":     acc[20].summary(px),
            }
            wjson(os.path.join(RUNTIME, "paper_snapshot.json"), snap)

            prev_f, prev_t = cf, ct
            time.sleep(POLL_SEC)

        except Exception as e:
            print(f"[paper] ERROR: {e}")
            time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()