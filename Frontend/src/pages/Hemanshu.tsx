import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  BarChart3,
  Play,
  Square,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Terminal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import Navigation from "@/components/Navigation";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function Trading() {
  const [running, setRunning] = useState(false);
  const [snapshot, setSnapshot] = useState(null);
  const [position, setPosition] = useState(null);
  const [trades, setTrades] = useState([]);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const logBoxRef = useRef(null);

  const totalPnL = useMemo(
    () => trades.reduce((sum, t) => sum + (Number(t.pnl) || 0), 0),
    [trades]
  );

  const fetchAll = async () => {
    try {
      const [st, fi, po, tr, lg] = await Promise.all([
        fetch(`${API}/status`).then((r) => r.json()),
        fetch(`${API}/fisher`).then((r) => r.json()),
        fetch(`${API}/position`).then((r) => r.json()),
        fetch(`${API}/trades`).then((r) => r.json()),
        fetch(`${API}/logs?n=300`).then((r) => r.json()),
      ]);
      setRunning(Boolean(st?.running));
      setSnapshot(Object.keys(fi || {}).length ? fi : null);
      setPosition(Object.keys(po || {}).length ? po : null);
      setTrades(Array.isArray(tr) ? tr.reverse() : []);
      setLogs(Array.isArray(lg) ? lg : []);
      console.log("lg", lg);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, 4000); // poll
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (logBoxRef.current) {
      logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight;
    }
  }, [logs]);

  const handleStart = async () => {
    setLoading(true);
    try {
      let res = await fetch(`${API}/start-bot`, { method: "POST" }).then((r) =>
        r.json()
      );
      console.log(res, "Bot started response");
      await fetchAll();
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    try {
      await fetch(`${API}/stop-bot`, { method: "POST" }).then((r) => r.json());
      await fetchAll();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-black text-foreground">
      <Navigation />

      <div className="container px-4 pt-28 pb-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mb-8 flex items-center justify-between"
        >
          <div>
            <h1 className="text-4xl md:text-5xl font-bold mb-2">
              Hemanshu Trading <span className="text-gradient">Dashboard</span>
            </h1>
            <p className="text-lg text-muted-foreground">
              Fisher Transform strategy • TP/SL automation • Live logs
            </p>
          </div>

          <div className="flex gap-3">
            <Button
              disabled={loading || running}
              onClick={handleStart}
              className="button-gradient"
            >
              <Play className="w-4 h-4 mr-2" />
              Start Bot
            </Button>
            <Button
              disabled={loading || !running}
              onClick={handleStop}
              variant="destructive"
            >
              <Square className="w-4 h-4 mr-2" />
              Stop Bot
            </Button>
          </div>
        </motion.div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left column: Live Snapshot & Position */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.4, delay: 0.1 }}
            className="lg:col-span-1 space-y-6"
          >
            {/* Live Fisher Snapshot */}
            <Card className="glass">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Activity className="w-5 h-5 text-primary" />
                  Live Fisher Snapshot
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {snapshot ? (
                  <>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Time</span>
                      <span>{snapshot.time}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Price</span>
                      <span>${Number(snapshot.price).toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Fisher</span>
                      <span>{snapshot.fisher?.toFixed(6)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Trigger</span>
                      <span>{snapshot.trigger?.toFixed(6)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Diff</span>
                      <span>{snapshot.difference?.toFixed(6)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Crossover</span>
                      <span className="uppercase">
                        {snapshot.crossover || "no crossover"}
                      </span>
                    </div>
                    <div className="pt-3">
                      <Tabs defaultValue="buy">
                        <TabsList className="grid grid-cols-2 glass">
                          <TabsTrigger
                            value="buy"
                            className="data-[state=active]:bg-primary/20"
                          >
                            Buy
                          </TabsTrigger>
                          <TabsTrigger
                            value="sell"
                            className="data-[state=active]:bg-destructive/20"
                          >
                            Sell
                          </TabsTrigger>
                        </TabsList>
                        <TabsContent value="buy" className="mt-4">
                          <Button className="w-full button-gradient" disabled>
                            <TrendingUp className="w-4 h-4 mr-2" />
                            Manual Buy (wire later)
                          </Button>
                        </TabsContent>
                        <TabsContent value="sell" className="mt-4">
                          <Button
                            className="w-full bg-destructive hover:bg-destructive/90"
                            disabled
                          >
                            <TrendingDown className="w-4 h-4 mr-2" />
                            Manual Sell (wire later)
                          </Button>
                        </TabsContent>
                      </Tabs>
                    </div>
                  </>
                ) : (
                  <div className="text-muted-foreground">No data yet…</div>
                )}
              </CardContent>
            </Card>

            {/* Open Position */}
            <Card className="glass">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BarChart3 className="w-5 h-5 text-primary" />
                  Open Position
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {position && position.entry_price ? (
                  <>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Side</span>
                      <span className="uppercase">{position.side}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Entry</span>
                      <span>${Number(position.entry_price).toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">TP / SL</span>
                      <span>
                        ${Number(position.tp).toFixed(2)} / $
                        {Number(position.sl).toFixed(2)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Size</span>
                      <span>{position.size || 15}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Opened</span>
                      <span>
                        {new Date(position.opened_at).toLocaleString()}
                      </span>
                    </div>
                  </>
                ) : (
                  <div className="text-muted-foreground">No open position</div>
                )}
              </CardContent>
            </Card>

            {/* PnL Summary */}
            <Card className="glass">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <DollarSign className="w-5 h-5 text-primary" />
                  PnL Summary
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Closed Trades</span>
                  <span>{trades.length}</span>
                </div>
                <div className="flex justify-between mt-2">
                  <span className="text-muted-foreground">Total PnL</span>
                  <span
                    className={
                      totalPnL >= 0 ? "text-primary" : "text-destructive"
                    }
                  >
                    {totalPnL.toFixed(4)}
                  </span>
                </div>
              </CardContent>
            </Card>
          </motion.div>

          {/* Right column: Logs + Trades */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.15 }}
            className="lg:col-span-2 space-y-6"
          >
            {/* Logs */}
            <Card className="glass">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Terminal className="w-5 h-5 text-primary" />
                  Live Logs
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div
                  ref={logBoxRef}
                  className="h-64 overflow-y-auto rounded-lg p-3 bg-black/50 border border-white/10 font-mono text-sm"
                >
                  {logs.length ? (
                    logs.map((l, i) => (
                      <div key={i} className="mb-1">
                        <span className="text-muted-foreground mr-2">
                          [{l.ts}]
                        </span>
                        <span className="uppercase mr-2">{l.type}</span>
                        {"price" in l && (
                          <span className="mr-2">
                            💰 {Number(l.price).toFixed(2)}
                          </span>
                        )}
                        {"fisher" in l && (
                          <span className="mr-2">
                            🎣 {Number(l.fisher).toFixed(6)}
                          </span>
                        )}
                        {"trigger" in l && (
                          <span className="mr-2">
                            🎯 {Number(l.trigger).toFixed(6)}
                          </span>
                        )}
                        {"diff" in l && (
                          <span className="mr-2">
                            📈 {Number(l.diff).toFixed(6)}
                          </span>
                        )}
                        {"crossover" in l && (
                          <span className="mr-2">🔍 {l.crossover}</span>
                        )}
                        {"side" in l && (
                          <span className="mr-2">
                            SIDE: {String(l.side).toUpperCase()}
                          </span>
                        )}
                        {"pnl" in l && (
                          <span
                            className={`mr-2 ${
                              Number(l.pnl) >= 0
                                ? "text-primary"
                                : "text-destructive"
                            }`}
                          >
                            PnL: {Number(l.pnl).toFixed(4)}
                          </span>
                        )}
                        {"reason" in l && (
                          <span className="mr-2">({l.reason})</span>
                        )}
                      </div>
                    ))
                  ) : (
                    <div className="text-muted-foreground">No logs yet…</div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Trades */}
            <Card className="glass">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <DollarSign className="w-5 h-5 text-primary" />
                  Trade History
                </CardTitle>
              </CardHeader>
              <CardContent>
                {trades.length ? (
                  <div className="w-full overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="text-left text-muted-foreground">
                        <tr>
                          <th className="py-2">Closed</th>
                          <th className="py-2">Side</th>
                          <th className="py-2">Entry</th>
                          <th className="py-2">Exit</th>
                          <th className="py-2">Size</th>
                          <th className="py-2">Reason</th>
                          <th className="py-2">PnL</th>
                        </tr>
                      </thead>
                      <tbody>
                        {trades.map((t, i) => (
                          <tr key={i} className="border-t border-white/5">
                            <td className="py-2">
                              {new Date(t.closed_at).toLocaleString()}
                            </td>
                            <td className="py-2 uppercase">{t.side}</td>
                            <td className="py-2">
                              ${Number(t.entry_price).toFixed(2)}
                            </td>
                            <td className="py-2">
                              ${Number(t.exit_price).toFixed(2)}
                            </td>
                            <td className="py-2">{t.size}</td>
                            <td className="py-2">{t.reason}</td>
                            <td
                              className={`py-2 ${
                                Number(t.pnl) >= 0
                                  ? "text-primary"
                                  : "text-destructive"
                              }`}
                            >
                              {Number(t.pnl).toFixed(4)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="text-muted-foreground">
                    No closed trades yet…
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
