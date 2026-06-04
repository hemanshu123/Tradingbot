import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Activity, BarChart3, Play, Square, TrendingUp,
  TrendingDown, DollarSign, Clock, Target, AlertCircle,
  CheckCircle2, XCircle, Layers,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import Navigation from "@/components/Navigation";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ── types ──────────────────────────────────────────────────────────────────
interface PaperPosition {
  side: string;
  entry_price: number;
  tp: number;
  sl: number;
  margin_rs: number;
  tp_move_pct: number;
  sl_move_pct: number;
  leverage: number;
  opened_at: string;
}

interface PaperTrade {
  no: number;
  side: string;
  entry_price: number;
  exit_price: number;
  reason: string;
  margin_rs: number;
  pnl_rs: number;
  pnl_pct_margin: number;
  equity_after: number;
  opened_at: string;
  closed_at: string;
}

interface AccountData {
  leverage: number;
  virtual_capital: number;
  current_equity: number;
  total_profit_rs: number;
  growth_pct: number;
  open_position: PaperPosition | null;
  unrealized_pnl_pct: number;
  unrealized_pnl_rs: number;
  total_trades: number;
  wins: number;
  losses: number;
  win_rate_pct: number;
  avg_win_rs: number;
  avg_loss_rs: number;
  cooldown_remaining: number;
  last_5_trades: PaperTrade[];
  all_trades: PaperTrade[];
}

// ── small helpers ──────────────────────────────────────────────────────────
const rs = (n: number) =>
  `Rs ${Math.abs(n).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

const pnlClass = (n: number) =>
  n >= 0 ? "text-emerald-400" : "text-red-400";

const pnlSign = (n: number) => (n >= 0 ? "+" : "-");

// ── Account card ───────────────────────────────────────────────────────────
function AccountCard({ acc, price }: { acc: AccountData; price: number }) {
  const profit   = acc.total_profit_rs;
  const isLong   = acc.open_position?.side === "buy";
  const hasPos   = !!acc.open_position?.entry_price;

  return (
    <div className="space-y-4">
      {/* Equity + Growth */}
      <Card className="glass border-white/10">
        <CardContent className="pt-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground text-sm">Virtual Capital</span>
            <span className="font-mono text-sm">{rs(acc.virtual_capital)}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground text-sm">Current Equity</span>
            <span className="font-mono font-bold text-lg">{rs(acc.current_equity)}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground text-sm">Total P&L</span>
            <span className={`font-mono font-semibold ${pnlClass(profit)}`}>
              {pnlSign(profit)}{rs(profit)}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground text-sm">Growth</span>
            <Badge
              variant={acc.growth_pct >= 0 ? "default" : "destructive"}
              className={acc.growth_pct >= 0 ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" : ""}
            >
              {pnlSign(acc.growth_pct)}{Math.abs(acc.growth_pct).toFixed(2)}%
            </Badge>
          </div>
          <div className="h-px bg-white/10" />
          <div className="grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-xs text-muted-foreground">Trades</div>
              <div className="font-bold">{acc.total_trades}</div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Win Rate</div>
              <div className={`font-bold ${acc.win_rate_pct >= 25 ? "text-emerald-400" : "text-red-400"}`}>
                {acc.win_rate_pct}%
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">W / L</div>
              <div className="font-bold">
                <span className="text-emerald-400">{acc.wins}</span>
                <span className="text-muted-foreground mx-1">/</span>
                <span className="text-red-400">{acc.losses}</span>
              </div>
            </div>
          </div>
          {acc.avg_win_rs !== 0 && (
            <div className="grid grid-cols-2 gap-2 text-center text-xs pt-1">
              <div>
                <div className="text-muted-foreground">Avg Win</div>
                <div className="text-emerald-400 font-semibold">+{rs(acc.avg_win_rs)}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Avg Loss</div>
                <div className="text-red-400 font-semibold">-{rs(Math.abs(acc.avg_loss_rs))}</div>
              </div>
            </div>
          )}
          {acc.cooldown_remaining > 0 && (
            <div className="flex items-center gap-2 text-xs text-yellow-400 bg-yellow-400/10 rounded-lg px-3 py-2">
              <Clock className="w-3 h-3" />
              Cooldown: {acc.cooldown_remaining} candles remaining
            </div>
          )}
        </CardContent>
      </Card>

      {/* Open Position */}
      <Card className={`glass border ${hasPos ? (isLong ? "border-emerald-500/30" : "border-red-500/30") : "border-white/10"}`}>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Target className="w-4 h-4" />
            Open Position
            {hasPos && (
              <Badge className={isLong ? "bg-emerald-500/20 text-emerald-400" : "bg-red-500/20 text-red-400"}>
                {acc.open_position!.side.toUpperCase()}
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {hasPos ? (
            <>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Entry Price</span>
                <span className="font-mono">${acc.open_position!.entry_price.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Current Price</span>
                <span className="font-mono">${price.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-emerald-400">Take Profit</span>
                <span className="font-mono text-emerald-400">${acc.open_position!.tp.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-red-400">Stop Loss</span>
                <span className="font-mono text-red-400">${acc.open_position!.sl.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Margin Used</span>
                <span className="font-mono">{rs(acc.open_position!.margin_rs)}</span>
              </div>
              <div className="h-px bg-white/10" />
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">Unrealized P&L</span>
                <div className="text-right">
                  <div className={`font-bold font-mono ${pnlClass(acc.unrealized_pnl_rs)}`}>
                    {pnlSign(acc.unrealized_pnl_rs)}{rs(Math.abs(acc.unrealized_pnl_rs))}
                  </div>
                  <div className={`text-xs ${pnlClass(acc.unrealized_pnl_pct)}`}>
                    {pnlSign(acc.unrealized_pnl_pct)}{Math.abs(acc.unrealized_pnl_pct).toFixed(2)}% on margin
                  </div>
                </div>
              </div>
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>Opened</span>
                <span>{new Date(acc.open_position!.opened_at).toLocaleString()}</span>
              </div>
            </>
          ) : (
            <div className="text-muted-foreground text-center py-4">No open position</div>
          )}
        </CardContent>
      </Card>

      {/* Last 5 Trades */}
      <Card className="glass border-white/10">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <BarChart3 className="w-4 h-4" />
            Last 5 Trades
          </CardTitle>
        </CardHeader>
        <CardContent>
          {acc.last_5_trades.length ? (
            <div className="space-y-2">
              {[...acc.last_5_trades].reverse().map((t, i) => (
                <div key={i} className="flex items-center justify-between text-xs py-1 border-b border-white/5 last:border-0">
                  <div className="flex items-center gap-2">
                    {t.reason === "TP"
                      ? <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                      : <XCircle className="w-3 h-3 text-red-400" />}
                    <span className={t.side === "buy" ? "text-emerald-400" : "text-red-400"}>
                      {t.side.toUpperCase()}
                    </span>
                    <span className="text-muted-foreground">#{t.no}</span>
                  </div>
                  <div className="text-muted-foreground">
                    ${t.entry_price.toFixed(0)} → ${t.exit_price.toFixed(0)}
                  </div>
                  <div className={`font-mono font-semibold ${pnlClass(t.pnl_rs)}`}>
                    {pnlSign(t.pnl_rs)}{rs(Math.abs(t.pnl_rs))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-muted-foreground text-center py-3 text-xs">No trades yet</div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── Full trade history table ────────────────────────────────────────────────
function TradeTable({ trades }: { trades: PaperTrade[] }) {
  if (!trades.length)
    return <div className="text-muted-foreground text-center py-6">No trades yet</div>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-muted-foreground border-b border-white/10">
            <th className="py-2 pr-3">#</th>
            <th className="py-2 pr-3">Side</th>
            <th className="py-2 pr-3">Entry</th>
            <th className="py-2 pr-3">Exit</th>
            <th className="py-2 pr-3">Result</th>
            <th className="py-2 pr-3">Margin</th>
            <th className="py-2 pr-3">P&L (Rs)</th>
            <th className="py-2 pr-3">P&L %</th>
            <th className="py-2">Equity After</th>
          </tr>
        </thead>
        <tbody>
          {[...trades].reverse().map((t, i) => (
            <tr key={i} className="border-b border-white/5 hover:bg-white/5">
              <td className="py-2 pr-3 text-muted-foreground">{t.no}</td>
              <td className={`py-2 pr-3 font-semibold ${t.side === "buy" ? "text-emerald-400" : "text-red-400"}`}>
                {t.side.toUpperCase()}
              </td>
              <td className="py-2 pr-3 font-mono">${t.entry_price.toFixed(2)}</td>
              <td className="py-2 pr-3 font-mono">${t.exit_price.toFixed(2)}</td>
              <td className="py-2 pr-3">
                <Badge className={t.reason === "TP"
                  ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                  : "bg-red-500/20 text-red-400 border-red-500/30"}>
                  {t.reason}
                </Badge>
              </td>
              <td className="py-2 pr-3 font-mono">{rs(t.margin_rs)}</td>
              <td className={`py-2 pr-3 font-mono font-bold ${pnlClass(t.pnl_rs)}`}>
                {pnlSign(t.pnl_rs)}{rs(Math.abs(t.pnl_rs))}
              </td>
              <td className={`py-2 pr-3 ${pnlClass(t.pnl_pct_margin)}`}>
                {pnlSign(t.pnl_pct_margin)}{Math.abs(t.pnl_pct_margin).toFixed(1)}%
              </td>
              <td className="py-2 font-mono">{rs(t.equity_after)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Main page ───────────────────────────────────────────────────────────────
export default function PaperTrade() {
  const [running, setRunning]   = useState(false);
  const [loading, setLoading]   = useState(false);
  const [price, setPrice]       = useState(0);
  const [fisher, setFisher]     = useState<number | null>(null);
  const [trigger, setTrigger]   = useState<number | null>(null);
  const [spread, setSpread]     = useState<number | null>(null);
  const [lastUpdate, setLast]   = useState<string>("");
  const [acc10, setAcc10]       = useState<AccountData | null>(null);
  const [acc20, setAcc20]       = useState<AccountData | null>(null);

  const fetchAll = async () => {
    try {
      const res = await fetch(`${API}/paper/status`).then(r => r.json());
      setRunning(Boolean(res?.running));
      const snap = res?.snapshot || {};
      if (snap.price)   setPrice(snap.price);
      if (snap.fisher !== undefined) setFisher(snap.fisher);
      if (snap.trigger !== undefined) setTrigger(snap.trigger);
      if (snap.spread !== undefined) setSpread(snap.spread);
      if (snap.time)    setLast(new Date(snap.time).toLocaleTimeString());
      if (snap["10x"])  setAcc10(snap["10x"]);
      if (snap["20x"])  setAcc20(snap["20x"]);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, 4000);
    return () => clearInterval(id);
  }, []);

  const startPaper = async () => {
    setLoading(true);
    try {
      await fetch(`${API}/start-paper`, { method: "POST" });
      await fetchAll();
    } finally { setLoading(false); }
  };

  const stopPaper = async () => {
    setLoading(true);
    try {
      await fetch(`${API}/stop-paper`, { method: "POST" });
      await fetchAll();
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-black text-foreground">
      <Navigation />

      <div className="container px-4 pt-28 pb-10">

        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8 flex flex-wrap items-center justify-between gap-4"
        >
          <div>
            <h1 className="text-4xl md:text-5xl font-bold mb-2">
              Paper <span className="text-gradient">Trading</span>
            </h1>
            <p className="text-muted-foreground text-sm">
              Virtual Rs 1,00,000 × 2 accounts &nbsp;·&nbsp;
              No real money &nbsp;·&nbsp;
              10x vs 20x leverage comparison
            </p>
          </div>

          <div className="flex gap-3">
            <Button
              onClick={startPaper}
              disabled={loading || running}
              className="button-gradient"
            >
              <Play className="w-4 h-4 mr-2" />
              Start Paper Trade
            </Button>
            <Button
              onClick={stopPaper}
              disabled={loading || !running}
              variant="destructive"
            >
              <Square className="w-4 h-4 mr-2" />
              Stop Paper Trade
            </Button>
          </div>
        </motion.div>

        {/* Status bar */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.1 }}
          className="flex flex-wrap gap-3 mb-8"
        >
          <Badge className={running
            ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30 px-4 py-1.5"
            : "bg-zinc-800 text-zinc-400 border-zinc-700 px-4 py-1.5"}>
            {running ? "● Running" : "○ Stopped"}
          </Badge>
          {price > 0 && (
            <Badge className="bg-zinc-800 text-zinc-300 border-zinc-700 px-4 py-1.5 font-mono">
              ETH ${price.toFixed(2)}
            </Badge>
          )}
          {fisher !== null && (
            <Badge className="bg-zinc-800 text-zinc-300 border-zinc-700 px-4 py-1.5 font-mono">
              Fisher {fisher.toFixed(4)} · Trigger {trigger?.toFixed(4)}
            </Badge>
          )}
          {spread !== null && (
            <Badge className={`px-4 py-1.5 font-mono ${
              spread >= 0.05
                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                : "bg-yellow-500/10 text-yellow-400 border-yellow-500/20"}`}>
              Spread {spread.toFixed(4)} {spread >= 0.05 ? "✓" : "⚠ weak"}
            </Badge>
          )}
          {lastUpdate && (
            <Badge className="bg-zinc-800 text-zinc-500 border-zinc-700 px-4 py-1.5 text-xs">
              Updated {lastUpdate}
            </Badge>
          )}
        </motion.div>

        {/* Not running notice */}
        {!running && !acc10 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex items-center gap-3 bg-yellow-500/10 border border-yellow-500/20 rounded-xl px-5 py-4 mb-8 text-yellow-300 text-sm"
          >
            <AlertCircle className="w-5 h-5 shrink-0" />
            Paper trading is not running. Click <strong className="mx-1">Start Paper Trade</strong> to begin simulating trades with virtual money.
          </motion.div>
        )}

        {/* Two account panels */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8"
        >
          {/* 10x account */}
          <div>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-3 h-3 rounded-full bg-blue-400" />
              <h2 className="text-xl font-bold">Account A — 10x Leverage</h2>
              <Badge className="bg-blue-500/20 text-blue-300 border-blue-500/30">Starter</Badge>
            </div>
            <div className="text-xs text-muted-foreground mb-4 space-y-0.5">
              <div>TP at +6% price move &nbsp;·&nbsp; SL at -1.5% price move</div>
              <div>Win = +Rs 3,000 per trade &nbsp;·&nbsp; Loss = -Rs 750 per trade</div>
            </div>
            {acc10
              ? <AccountCard acc={acc10} price={price} />
              : <Card className="glass border-white/10"><CardContent className="py-12 text-center text-muted-foreground">Start paper trading to see data</CardContent></Card>
            }
          </div>

          {/* 20x account */}
          <div>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-3 h-3 rounded-full bg-purple-400" />
              <h2 className="text-xl font-bold">Account B — 20x Leverage</h2>
              <Badge className="bg-purple-500/20 text-purple-300 border-purple-500/30">Future</Badge>
            </div>
            <div className="text-xs text-muted-foreground mb-4 space-y-0.5">
              <div>TP at +3% price move &nbsp;·&nbsp; SL at -0.75% price move</div>
              <div>Win = +Rs 3,000 per trade &nbsp;·&nbsp; Loss = -Rs 750 per trade</div>
            </div>
            {acc20
              ? <AccountCard acc={acc20} price={price} />
              : <Card className="glass border-white/10"><CardContent className="py-12 text-center text-muted-foreground">Start paper trading to see data</CardContent></Card>
            }
          </div>
        </motion.div>

        {/* Side by side equity comparison */}
        {acc10 && acc20 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="mb-8"
          >
            <Card className="glass border-white/10">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Layers className="w-4 h-4 text-primary" />
                  Side by Side Comparison
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
                  {[
                    { label: "Equity",     v10: rs(acc10.current_equity),    v20: rs(acc20.current_equity) },
                    { label: "Total P&L",  v10: `${pnlSign(acc10.total_profit_rs)}${rs(Math.abs(acc10.total_profit_rs))}`, v20: `${pnlSign(acc20.total_profit_rs)}${rs(Math.abs(acc20.total_profit_rs))}`,
                      c10: pnlClass(acc10.total_profit_rs), c20: pnlClass(acc20.total_profit_rs) },
                    { label: "Growth",     v10: `${pnlSign(acc10.growth_pct)}${Math.abs(acc10.growth_pct).toFixed(2)}%`, v20: `${pnlSign(acc20.growth_pct)}${Math.abs(acc20.growth_pct).toFixed(2)}%`,
                      c10: pnlClass(acc10.growth_pct), c20: pnlClass(acc20.growth_pct) },
                    { label: "Win Rate",   v10: `${acc10.win_rate_pct}%`, v20: `${acc20.win_rate_pct}%` },
                  ].map(({ label, v10, v20, c10, c20 }) => (
                    <div key={label}>
                      <div className="text-xs text-muted-foreground mb-2">{label}</div>
                      <div className="flex gap-2 justify-center items-center">
                        <div className="text-center">
                          <div className="text-[10px] text-blue-400 mb-1">10x</div>
                          <div className={`font-mono text-sm font-bold ${c10 || ""}`}>{v10}</div>
                        </div>
                        <div className="text-muted-foreground text-xs">vs</div>
                        <div className="text-center">
                          <div className="text-[10px] text-purple-400 mb-1">20x</div>
                          <div className={`font-mono text-sm font-bold ${c20 || ""}`}>{v20}</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* Full trade history */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35 }}
        >
          <Card className="glass border-white/10">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <DollarSign className="w-5 h-5 text-primary" />
                Full Trade History
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Tabs defaultValue="10x">
                <TabsList className="glass mb-4">
                  <TabsTrigger value="10x" className="data-[state=active]:bg-blue-500/20">
                    10x Account ({acc10?.total_trades ?? 0} trades)
                  </TabsTrigger>
                  <TabsTrigger value="20x" className="data-[state=active]:bg-purple-500/20">
                    20x Account ({acc20?.total_trades ?? 0} trades)
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="10x">
                  <TradeTable trades={acc10?.all_trades ?? []} />
                </TabsContent>
                <TabsContent value="20x">
                  <TradeTable trades={acc20?.all_trades ?? []} />
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>
        </motion.div>

      </div>
    </div>
  );
}