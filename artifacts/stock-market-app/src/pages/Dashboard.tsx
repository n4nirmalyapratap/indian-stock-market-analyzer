import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { TrendingUp, TrendingDown, Activity, AlertCircle, RefreshCw, ScanSearch, Loader2 } from "lucide-react";
import ChartButton from "@/components/ChartButton";
import DataFreshness from "@/components/DataFreshness";
import MacroStrip from "@/components/macro/MacroStrip";
import GlobalIndicesPanel from "@/components/GlobalIndicesPanel";
import TopMoversPanel from "@/components/TopMoversPanel";
import { marketDataQueryOptions, pickMeta } from "@/lib/marketData";
import { formatAdRatio, shortSectorName, formatPctChange } from "@/lib/dashboard-helpers";

function CardLoader() {
  return (
    <span className="w-3 h-3 rounded-full border-2 border-indigo-400 border-t-transparent animate-spin inline-block" />
  );
}

interface StatCardProps {
  title:    string;
  value:    string | number;
  sub?:     string | number | null;
  trend?:   "up" | "down";
  loading?: boolean;
}
function StatCard({ title, value, sub, trend, loading }: StatCardProps) {
  const isUp = trend === "up";
  const isDown = trend === "down";
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 shadow-sm p-5 relative overflow-hidden">
      <div className="flex items-center justify-between mb-1">
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{title}</p>
        {loading && <CardLoader />}
      </div>
      <p className="text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
      {sub && (
        <p className={`mt-1 text-sm flex items-center gap-1 ${isUp ? "text-green-600" : isDown ? "text-red-500" : "text-gray-500 dark:text-gray-400"}`}>
          {isUp && <TrendingUp className="w-3 h-3" />}
          {isDown && <TrendingDown className="w-3 h-3" />}
          {sub}
        </p>
      )}
      {loading && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-100 dark:bg-indigo-900"><div className="h-full bg-indigo-400 animate-pulse" /></div>}
    </div>
  );
}

export default function Dashboard() {
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);

  const { data: rotation, isLoading: rotLoading, isFetching: rotFetching, error: rotErr } = useQuery(
    marketDataQueryOptions(["rotation"], api.sectorRotation),
  );
  const [scanTriggered, setScanTriggered] = useState(false);
  const { data: patterns, isLoading: patLoading, isFetching: patFetching } = useQuery(
    marketDataQueryOptions(["patterns-overview"], () => api.patterns(), {
      staleTime: 10 * 60 * 1000,
      refetchInterval: (query) => {
        const d = query.state.data as any;
        return d?.scanInProgress ? 3000 : false;
      },
    }),
  );

  const scanInProgress = patterns?.scanInProgress ?? false;
  const scanProgress   = patterns?.scanProgress ?? null;

  async function handleRunScan() {
    setScanTriggered(true);
    try {
      await api.triggerScan();
      await queryClient.invalidateQueries({ queryKey: ["patterns-overview"] });
    } finally {
      setScanTriggered(false);
    }
  }

  // Show per-card loaders ONLY on the initial fetch (when there's no
  // cached data yet). Background refetches (every 60s while market is
  // open) keep the previous values rendered — flashing a spinner on
  // each refetch made the dashboard FEEL slow even when it wasn't.
  // The top-bar refresh button still tracks isFetching via
  // `isRefreshing` below so the manual refresh action stays visible.
  const rotBusy = rotLoading;
  const patBusy = patLoading;
  const isRefreshing = refreshing || rotFetching || patFetching;

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["rotation"] }),
        queryClient.invalidateQueries({ queryKey: ["patterns-overview"] }),
        queryClient.invalidateQueries({ queryKey: ["global-indices"] }),
      ]);
    } finally {
      setRefreshing(false);
    }
  }

  const breadth = rotation?.marketBreadth;
  // Memoise so the rapid spinner re-renders during refresh don't recompute
  // these on every paint.
  const adRatio = useMemo(
    () => (breadth ? formatAdRatio(breadth.advancing, breadth.declining) : "-"),
    [breadth?.advancing, breadth?.declining],
  );
  const breadthLabel = breadth?.breadthScore ?? null;
  const buyNow = useMemo(() => rotation?.whereToBuyNow?.slice(0, 5) ?? [], [rotation?.whereToBuyNow]);
  const sectorsTop = useMemo(() => rotation?.sectors?.slice(0, 8) ?? [], [rotation?.sectors]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Market Dashboard</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">Indian Stock Market Analysis Platform</p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={isRefreshing}
          className="flex items-center gap-2 text-sm text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 border border-indigo-200 dark:border-indigo-700 rounded-lg px-3 py-1.5 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 transition disabled:opacity-60"
        >
          <RefreshCw className={`w-4 h-4 ${isRefreshing ? "animate-spin" : ""}`} />
          {isRefreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <DataFreshness
        meta={pickMeta(rotation) ?? (rotation ? { source: "NSE", asOf: rotation.timestamp } : null)}
        refreshKeys={[["rotation"], ["patterns-overview"]]}
      />

      <MacroStrip />

      {rotErr && (
        <div className="flex items-center gap-2 text-red-600 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg p-3 text-sm">
          <AlertCircle className="w-4 h-4" /> Unable to connect to API server. Make sure it's running.
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard loading={rotBusy} title="Market Phase" value={rotLoading ? "…" : (rotation?.rotationPhase?.split(" -")[0] || "N/A")} sub={rotation?.rotationPhase?.split(" - ")[1]} />
        <StatCard loading={rotBusy} title="Advancing" value={rotLoading ? "…" : breadth?.advancing ?? "-"} trend="up" sub="sectors gaining" />
        <StatCard loading={rotBusy} title="Declining" value={rotLoading ? "…" : breadth?.declining ?? "-"} trend="down" sub="sectors falling" />
        <StatCard loading={rotBusy} title="A/D Ratio" value={rotLoading ? "…" : adRatio} sub={`Breadth: ${breadthLabel ?? "-"}%`} />
      </div>

      <GlobalIndicesPanel />

      {/* Top Movers — per cap-segment gainers/losers, refreshes on its own
          cadence via marketDataQueryOptions. */}
      <TopMoversPanel />

      <div className="grid md:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 shadow-sm p-5 relative overflow-hidden">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-gray-800 dark:text-gray-100 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-green-500" /> Where to Buy Now
            </h2>
            {rotBusy && <CardLoader />}
          </div>
          {rotLoading ? (
            <div className="space-y-2">
              {[1,2,3].map(i => <div key={i} className="h-8 bg-gray-100 dark:bg-gray-700 animate-pulse rounded" />)}
            </div>
          ) : buyNow.length > 0 ? (
            <div className="space-y-2">
              {buyNow.map((s: any, i: number) => (
                <div key={s.symbol ?? i} className="flex items-center justify-between p-2 rounded-lg bg-green-50 dark:bg-green-900/25">
                  <span className="text-sm font-medium text-gray-800 dark:text-gray-200 flex items-center gap-1">
                    {s.name}
                    {s.symbol && <ChartButton symbol={s.symbol} />}
                  </span>
                  <span className={`text-sm font-semibold ${(s.pChange ?? 0) >= 0 ? "text-green-600" : "text-red-500"}`}>
                    {formatPctChange(s.pChange)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-500 dark:text-gray-400">No data available</p>
          )}
          {rotBusy && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-green-100 dark:bg-green-900"><div className="h-full bg-green-400 animate-pulse" /></div>}
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 shadow-sm p-5 relative overflow-hidden">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-gray-800 dark:text-gray-100 flex items-center gap-2">
              <Activity className="w-4 h-4 text-indigo-500" /> Pattern Signals
            </h2>
            {patBusy && <CardLoader />}
          </div>
          {patLoading ? (
            <div className="space-y-3">
              <div className="flex gap-4">
                {[1,2,3].map(i => <div key={i} className="flex-1 h-16 bg-gray-100 dark:bg-gray-700 animate-pulse rounded-lg" />)}
              </div>
              {[1,2,3].map(i => <div key={i} className="h-6 bg-gray-100 dark:bg-gray-700 animate-pulse rounded" />)}
            </div>
          ) : (scanInProgress || scanTriggered) ? (
            /* ── Scan in progress ── */
            <div className="flex flex-col items-center justify-center py-6 gap-4">
              <div className="relative">
                <ScanSearch className="w-10 h-10 text-indigo-300 dark:text-indigo-700" />
                <Loader2 className="w-5 h-5 text-indigo-500 animate-spin absolute -bottom-1 -right-1" />
              </div>
              <div className="text-center">
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Scanning universe…</p>
                {scanProgress ? (
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    {scanProgress.done.toLocaleString()} / {scanProgress.total.toLocaleString()} symbols
                  </p>
                ) : (
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Checking chart patterns across all NSE stocks</p>
                )}
              </div>
              {scanProgress && scanProgress.total > 0 && (
                <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-1.5 overflow-hidden">
                  <div
                    className="h-full bg-indigo-500 transition-all duration-500 rounded-full"
                    style={{ width: `${Math.min(100, (scanProgress.done / scanProgress.total) * 100)}%` }}
                  />
                </div>
              )}
            </div>
          ) : patterns && (patterns.totalPatterns ?? 0) > 0 ? (
            /* ── Has results ── */
            <div className="space-y-3">
              <div className="flex gap-4">
                <div className="flex-1 bg-green-50 dark:bg-green-900/25 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-green-600">{patterns.callSignals}</p>
                  <p className="text-xs text-green-700 dark:text-green-400 font-medium">CALL Signals</p>
                </div>
                <div className="flex-1 bg-red-50 dark:bg-red-900/25 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-red-600">{patterns.putSignals}</p>
                  <p className="text-xs text-red-700 dark:text-red-400 font-medium">PUT Signals</p>
                </div>
                <div className="flex-1 bg-blue-50 dark:bg-blue-900/25 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-blue-600">{patterns.totalPatterns}</p>
                  <p className="text-xs text-blue-700 dark:text-blue-400 font-medium">Total</p>
                </div>
              </div>
              <div className="space-y-1.5">
                {patterns.topCalls?.slice(0, 3).map((p: any, i: number) => (
                  <div key={i} className="flex justify-between items-center text-sm">
                    <span className="text-gray-700 dark:text-gray-300 flex items-center gap-1">
                      {p.symbol}
                      <ChartButton symbol={p.symbol} />
                      — <span className="text-gray-500 dark:text-gray-400">{p.pattern}</span>
                    </span>
                    <span className="text-green-600 font-medium">{p.confidence}%</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            /* ── No scan yet / empty ── */
            <div className="flex flex-col items-center justify-center py-5 gap-3">
              <div className="w-12 h-12 rounded-full bg-indigo-50 dark:bg-indigo-900/30 flex items-center justify-center">
                <ScanSearch className="w-6 h-6 text-indigo-400" />
              </div>
              <div className="text-center">
                <p className="text-sm font-medium text-gray-700 dark:text-gray-200">No scan data yet</p>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                  Detect bullish & bearish chart patterns across all NSE stocks
                </p>
              </div>
              <button
                onClick={handleRunScan}
                disabled={scanTriggered}
                className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white transition disabled:opacity-60"
              >
                {scanTriggered
                  ? <><Loader2 className="w-3 h-3 animate-spin" /> Starting…</>
                  : <><ScanSearch className="w-3 h-3" /> Run Pattern Scan</>
                }
              </button>
            </div>
          )}
          {patBusy && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-100 dark:bg-indigo-900"><div className="h-full bg-indigo-400 animate-pulse" /></div>}
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 shadow-sm p-5 relative overflow-hidden">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-gray-800 dark:text-gray-100">Sector Rotation Analysis</h2>
          {rotBusy && <CardLoader />}
        </div>
        {rotLoading ? (
          <div className="h-16 bg-gray-100 dark:bg-gray-700 animate-pulse rounded-lg" />
        ) : rotation ? (
          <div>
            <div className="mb-3 p-3 bg-indigo-50 dark:bg-indigo-900/30 rounded-lg">
              <p className="text-sm font-medium text-indigo-800 dark:text-indigo-300">{rotation.rotationPhase}</p>
              <p className="text-xs text-indigo-600 dark:text-indigo-400 mt-1">{rotation.recommendation}</p>
            </div>
            <div className="grid grid-cols-4 gap-2">
              {sectorsTop.map((s: any, i: number) => (
                <div key={s.symbol ?? i} className={`rounded-lg p-2.5 text-center ${(s.pChange ?? 0) >= 0 ? "bg-green-50 dark:bg-green-900/25 border border-green-100 dark:border-green-800" : "bg-red-50 dark:bg-red-900/25 border border-red-100 dark:border-red-800"}`}>
                  <p className="text-xs font-medium text-gray-700 dark:text-gray-300 truncate">{shortSectorName(s.name)}</p>
                  <p className={`text-sm font-bold ${(s.pChange ?? 0) >= 0 ? "text-green-600" : "text-red-500"}`}>
                    {formatPctChange(s.pChange)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-500 dark:text-gray-400">No rotation data</p>
        )}
        {rotBusy && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-100 dark:bg-indigo-900"><div className="h-full bg-indigo-400 animate-pulse" /></div>}
      </div>
    </div>
  );
}
