import { motion } from "framer-motion";
import { useState, useEffect, useMemo } from "react";
import {
  History,
  Filter,
  Download,
  TrendingUp,
  TrendingDown,
  Calendar,
  DollarSign,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
// Custom table components since @/components/ui/table is not available
const Table = ({ children, ...props }) => (
  <table className="w-full text-sm" {...props}>
    {children}
  </table>
);

const TableHeader = ({ children, ...props }) => (
  <thead {...props}>{children}</thead>
);

const TableBody = ({ children, ...props }) => (
  <tbody {...props}>{children}</tbody>
);

const TableRow = ({ children, className, ...props }) => (
  <tr className={className} {...props}>
    {children}
  </tr>
);

const TableHead = ({ children, ...props }) => (
  <th
    className="text-left py-3 px-4 text-muted-foreground font-medium"
    {...props}
  >
    {children}
  </th>
);

const TableCell = ({ children, className = "", ...props }) => (
  <td className={`py-3 px-4 ${className}`} {...props}>
    {children}
  </td>
);
import { Badge } from "@/components/ui/badge";
import Navigation from "@/components/Navigation";

const API = "http://45.117.72.244:8001";

const TradeHistory = () => {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  // Filter states
  const [filterType, setFilterType] = useState("all");
  const [searchTerm, setSearchTerm] = useState("");
  const [dateFilter, setDateFilter] = useState("all");

  // Fetch trades from API
  const fetchTrades = async (showRefresh = false) => {
    if (showRefresh) setRefreshing(true);
    else setLoading(true);

    try {
      const response = await fetch(`${API}/trades`);
      if (!response.ok) throw new Error("Failed to fetch trades");

      const data = await response.json();
      // Reverse to show newest first (API returns oldest first)
      setTrades(Array.isArray(data) ? data.reverse() : []);
      setError(null);
    } catch (err) {
      console.error("Error fetching trades:", err);
      setError(err.message);
      setTrades([]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchTrades();
    // Auto refresh every 30 seconds
    const interval = setInterval(() => fetchTrades(true), 30000);
    return () => clearInterval(interval);
  }, []);

  // Calculate statistics
  const stats = useMemo(() => {
    const totalTrades = trades.length;
    const totalPnL = trades.reduce(
      (sum, trade) => sum + (Number(trade.pnl) || 0),
      0
    );
    const winningTrades = trades.filter(
      (trade) => (Number(trade.pnl) || 0) > 0
    ).length;
    const winRate = totalTrades > 0 ? (winningTrades / totalTrades) * 100 : 0;

    // Calculate total volume (approximate based on position size)
    const totalVolume = trades.reduce((sum, trade) => {
      const entryPrice = Number(trade.entry_price) || 0;
      const size = Number(trade.size) || 0;
      return sum + entryPrice * size;
    }, 0);

    return [
      {
        label: "Total Trades",
        value: totalTrades.toString(),
        icon: History,
      },
      {
        label: "Total Volume",
        value: `$${totalVolume.toLocaleString("en-US", {
          maximumFractionDigits: 0,
        })}`,
        icon: DollarSign,
      },
      {
        label: "Total P&L",
        value: `${totalPnL >= 0 ? "+" : ""}$${totalPnL.toFixed(2)}`,
        icon: totalPnL >= 0 ? TrendingUp : TrendingDown,
        positive: totalPnL >= 0,
      },
      {
        label: "Win Rate",
        value: `${winRate.toFixed(1)}%`,
        icon: TrendingUp,
      },
    ];
  }, [trades]);

  // Filter trades based on current filters
  const filteredTrades = useMemo(() => {
    return trades.filter((trade) => {
      // Type filter
      const matchesType =
        filterType === "all" ||
        (filterType === "buy" && trade.side?.toLowerCase() === "buy") ||
        (filterType === "sell" && trade.side?.toLowerCase() === "sell");

      // Search filter
      const matchesSearch =
        searchTerm === "" ||
        trade.side?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        trade.reason?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        trade.entry_price?.toString().includes(searchTerm) ||
        trade.exit_price?.toString().includes(searchTerm);

      // Date filter
      let matchesDate = true;
      if (dateFilter !== "all" && trade.closed_at) {
        const tradeDate = new Date(trade.closed_at);
        const now = new Date();

        switch (dateFilter) {
          case "today":
            matchesDate = tradeDate.toDateString() === now.toDateString();
            break;
          case "week":
            const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
            matchesDate = tradeDate >= weekAgo;
            break;
          case "month":
            const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
            matchesDate = tradeDate >= monthAgo;
            break;
        }
      }

      return matchesType && matchesSearch && matchesDate;
    });
  }, [trades, filterType, searchTerm, dateFilter]);

  // Export to CSV function
  const exportToCSV = () => {
    const csvHeaders = [
      "Closed At",
      "Side",
      "Entry Price",
      "Exit Price",
      "Size",
      "Reason",
      "PnL",
      "Opened At",
    ];

    const csvData = filteredTrades.map((trade) => [
      new Date(trade.closed_at).toLocaleString(),
      trade.side?.toUpperCase() || "",
      trade.entry_price || "",
      trade.exit_price || "",
      trade.size || "",
      trade.reason || "",
      trade.pnl || "",
      new Date(trade.opened_at).toLocaleString(),
    ]);

    const csvContent = [csvHeaders, ...csvData]
      .map((row) => row.map((cell) => `"${cell}"`).join(","))
      .join("\n");

    const blob = new Blob([csvContent], { type: "text/csv" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `trade_history_${new Date().toISOString().split("T")[0]}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-black text-foreground">
        <Navigation />
        <div className="container px-4 pt-28 pb-8">
          <div className="flex items-center justify-center h-64">
            <RefreshCw className="w-8 h-8 animate-spin text-primary" />
            <span className="ml-2 text-lg">Loading trade history...</span>
          </div>
        </div>
      </div>
    );
  }

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
            <h1 className="text-4xl md:text-5xl font-bold mb-4">
              Trade <span className="text-gradient">History</span>
            </h1>
            <p className="text-lg text-muted-foreground">
              Comprehensive overview of your trading performance and history
            </p>
          </div>

          <Button
            onClick={() => fetchTrades(true)}
            disabled={refreshing}
            className="button-gradient"
          >
            <RefreshCw
              className={`w-4 h-4 mr-2 ${refreshing ? "animate-spin" : ""}`}
            />
            {refreshing ? "Refreshing..." : "Refresh"}
          </Button>
        </motion.div>

        {error && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-6"
          >
            <Card className="glass border-destructive/20">
              <CardContent className="p-4">
                <div className="text-destructive">
                  Error loading trades: {error}
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* Stats Cards */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8"
        >
          {stats.map((stat, index) => (
            <Card key={stat.label} className="glass">
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">
                      {stat.label}
                    </p>
                    <p
                      className={`text-2xl font-bold ${
                        stat.label === "Total P&L"
                          ? stat.positive
                            ? "text-primary"
                            : "text-destructive"
                          : ""
                      }`}
                    >
                      {stat.value}
                    </p>
                  </div>
                  <div className="p-3 bg-primary/10 rounded-lg">
                    <stat.icon className="w-6 h-6 text-primary" />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </motion.div>

        {/* Filters and Search */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="mb-6"
        >
          <Card className="glass">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Filter className="w-5 h-5 text-primary" />
                Filter Trades
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
                <div>
                  <label className="text-sm font-medium mb-2 block">
                    Search
                  </label>
                  <Input
                    placeholder="Search by side, reason, price..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="glass"
                  />
                </div>

                <div>
                  <label className="text-sm font-medium mb-2 block">
                    Trade Type
                  </label>
                  <Select value={filterType} onValueChange={setFilterType}>
                    <SelectTrigger className="glass">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-[#1B1B1B] border-white/10">
                      <SelectItem value="all">All Types</SelectItem>
                      <SelectItem value="buy">Buy Only</SelectItem>
                      <SelectItem value="sell">Sell Only</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <label className="text-sm font-medium mb-2 block">
                    Time Period
                  </label>
                  <Select value={dateFilter} onValueChange={setDateFilter}>
                    <SelectTrigger className="glass">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-[#1B1B1B] border-white/10">
                      <SelectItem value="all">All Time</SelectItem>
                      <SelectItem value="today">Today</SelectItem>
                      <SelectItem value="week">Last Week</SelectItem>
                      <SelectItem value="month">Last Month</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex items-end">
                  <Button
                    onClick={exportToCSV}
                    className="w-full button-gradient"
                    disabled={filteredTrades.length === 0}
                  >
                    <Download className="w-4 h-4 mr-2" />
                    Export CSV
                  </Button>
                </div>

                <div className="flex items-end">
                  <div className="w-full text-sm text-muted-foreground">
                    Showing {filteredTrades.length} of {trades.length} trades
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* Trade History Table */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.3 }}
        >
          <Card className="glass">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <History className="w-5 h-5 text-primary" />
                Trading History ({filteredTrades.length} trades)
              </CardTitle>
            </CardHeader>
            <CardContent>
              {filteredTrades.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  {trades.length === 0
                    ? "No trades found. Start trading to see your history here."
                    : "No trades match your current filters. Try adjusting the filters above."}
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-white/10">
                        <TableHead>Closed At</TableHead>
                        <TableHead>Side</TableHead>
                        <TableHead>Entry Price</TableHead>
                        <TableHead>Exit Price</TableHead>
                        <TableHead>Size</TableHead>
                        <TableHead>Reason</TableHead>
                        <TableHead>P&L</TableHead>
                        <TableHead>Duration</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredTrades.map((trade, index) => {
                        const pnlValue = Number(trade.pnl) || 0;
                        const isProfit = pnlValue > 0;

                        // Calculate trade duration
                        let duration = "N/A";
                        if (trade.opened_at && trade.closed_at) {
                          const openTime = new Date(trade.opened_at);
                          const closeTime = new Date(trade.closed_at);
                          const diffMs =
                            closeTime.getTime() - openTime.getTime();
                          const diffMins = Math.floor(diffMs / 60000);
                          const diffHours = Math.floor(diffMins / 60);
                          const diffDays = Math.floor(diffHours / 24);

                          if (diffDays > 0) {
                            duration = `${diffDays}d ${diffHours % 24}h`;
                          } else if (diffHours > 0) {
                            duration = `${diffHours}h ${diffMins % 60}m`;
                          } else {
                            duration = `${diffMins}m`;
                          }
                        }

                        return (
                          <TableRow
                            key={index}
                            className="border-white/10 hover:bg-white/5"
                          >
                            <TableCell className="text-sm">
                              {trade.closed_at
                                ? new Date(trade.closed_at).toLocaleString()
                                : "N/A"}
                            </TableCell>
                            <TableCell>
                              <Badge
                                variant={
                                  trade.side?.toLowerCase() === "buy"
                                    ? "default"
                                    : "destructive"
                                }
                                className={
                                  trade.side?.toLowerCase() === "buy"
                                    ? "bg-primary/20 text-primary"
                                    : "bg-destructive/20 text-destructive"
                                }
                              >
                                {trade.side?.toLowerCase() === "buy" ? (
                                  <TrendingUp className="w-3 h-3 mr-1" />
                                ) : (
                                  <TrendingDown className="w-3 h-3 mr-1" />
                                )}
                                {trade.side?.toUpperCase() || "N/A"}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              ${Number(trade.entry_price || 0).toFixed(2)}
                            </TableCell>
                            <TableCell>
                              ${Number(trade.exit_price || 0).toFixed(2)}
                            </TableCell>
                            <TableCell>{trade.size || "N/A"}</TableCell>
                            <TableCell>
                              <Badge variant="outline" className="text-xs">
                                {trade.reason || "N/A"}
                              </Badge>
                            </TableCell>
                            <TableCell
                              className={
                                isProfit ? "text-primary" : "text-destructive"
                              }
                            >
                              {isProfit ? "+" : ""}${pnlValue.toFixed(4)}
                            </TableCell>
                            <TableCell className="text-sm text-muted-foreground">
                              {duration}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
};

export default TradeHistory;
