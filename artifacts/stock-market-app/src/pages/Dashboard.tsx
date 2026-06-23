import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "wouter";
import { api, fetchApi } from "@/lib/api";
import {
  RefreshCw, Activity, ScanSearch, Loader2,
  Newspaper, TrendingUp, TrendingDown, Zap,
} from "lucide-react";
import MacroStrip from "@/components/macro/MacroStrip";
import GlobalIndicesPanel from "@/components/GlobalIndicesPanel";
import TopMoversPanel from "@/components/TopMoversPanel";
import ChartButton from "@/components/ChartButton";
import { marketDataQueryOptions } from "@/lib/marketData";

// ── formatters ────────────────────────────────────────────────────────────────

function fmtCr(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return "—";
  const sign = v >= 0 ? "+" : "−";
  const abs  = Math.abs(v);
  if (abs >= 10_000) return `${sign}₹${(abs / 10_000).toFixed(2)} Cr`;
  if (abs >= 100)    return `${sign}₹${(abs / 100).toFixed(2)}K`;
  return `${sign}₹${abs.toFixed(2)}`;
}

function vixMeta(v: number | null | undefined): { label: string; cls: string; bg: string } {
  if (v == null) return { label: "—",        cls: "text-gray-400 dark:text-gray-500",                   bg: "bg-gray-100 dark:bg-gray-700/40" };
  if (v < 12)    return { label: "Very Low",  cls: "text-emerald-600 dark:text-emerald-400",             bg: "bg-emerald-50 dark:bg-emerald-900/20" };
  if (v < 15)    return { label: "Low",       cls: "text-green-600 dark:text-green-400",                 bg: "bg-green-50 dark:bg-green-900/20" };
  if (v < 20)    return { label: "Moderate",  cls: "text-amber-600 dark:text-amber-400",                 bg: "bg-amber-50 dark:bg-amber-900/20" };
  if (v < 25)    return { label: "Elevated",  cls: "text-orange-600 dark:text-orange-400",               bg: "bg-orange-50 dark:bg-orange-900/20" };
  return               { label: "High Fear",  cls: "text-red-600 dark:text-red-400",                     bg: "bg-red-50 dark:bg-red-900/20" };
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function Skel({ h = "h-4", w = "w-full", rounded = "rounded" }: { h?: string; w?: string; rounded?: string }) {
  return <div className={`${h} ${w} ${rounded} bg-gray-100 dark:bg-gray-700 animate-pulse`} />;
}

// ── Mini stat card ────────────────────────────────────────────────────────────

interface StatProps {
  title: string;
  value: string;
  sub?: React.ReactNode;
  subCls?: string;
  loading?: boolean;
  accent?: string;
  icon: React.ReactNode;
}
function StatCard({ title, value, sub, subCls, loading, icon }: StatProps) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 shadow-sm p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{title}</p>
        <span className="text-gray-400 dark:text-gray-500">{icon}</span>
      </div>
      {loading
        ? <Skel h="h-7" w="w-24" rounded="rounded-md" />
        : <p className="text-xl font-bold text-gray-900 dark:text-white leading-tight">{value}</p>
      }
      {loading
        ? <Skel h="h-3" w="w-16" />
        : sub && <p className={`text-xs ${subCls ?? "text-gray-500 dark:text-gray-400"}`}>{sub}</p>
      }
    </div>
  );
}

// ── VIX card (slightly richer) ────────────────────────────────────────────────

function VixCard({ vix, loading }: { vix: any; loading: boolean }) {
  const { label, cls, bg } = vixMeta(vix?.price);
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 shadow-sm p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">India VIX</p>
        <Zap className="w-4 h-4 text-amber-400" />
      </div>
      {loading
        ? <Skel h="h-7" w="w-20" rounded="rounded-md" />
        : <p className="text-xl font-bold text-gray-900 dark:text-white leading-tight">
            {vix?.price != null ? vix.price.toFixed(2) : "—"}
          </p>
      }
      {loading
        ? <Skel h="h-5" w="w-20" rounded="rounded-full" />
        : <span className={`self-start text-xs font-semibold px-2 py-0.5 rounded-full ${bg} ${cls}`}>{label}</span>
      }
    </div>
  );
}

// ── News feed ─────────────────────────────────────────────────────────────────

function NewsPanel({ loading, items }: { loading: boolean; items: any[] }) {
  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3, 4, 5].map(i => (
          <div key={i} className="flex gap-2 items-start">
            <div className="mt-1.5 w-2 h-2 rounded-full bg-gray-200 dark:bg-gray-600 flex-shrink-0" />
            <div className="flex-1 space-y-1">
              <Skel h="h-3" />
              <Skel h="h-3" w="w-2/3" />
            </div>
          </div>
        ))}
      </div>
    );
  }
  if (!items.length) {
    return <p className="text-sm text-gray-400 dark:text-gray-500 py-6 text-center">No headlines available</p>;
  }
  return (
    <div className="space-y-1">
      {items.map((item: any, i: number) => {
        const dot = item.sentiment === "positive" ? "bg-green-400"
                  : item.sentiment === "negative" ? "bg-red-400"
                  : "bg-gray-300 dark:bg-gray-600";
        return (
          <a
            key={i}
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-start gap-2.5 p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 group transition"
          >
            <span className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${dot}`} />
            <div className="min-w-0">
              <p className="text-sm text-gray-800 dark:text-gray-200 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 line-clamp-2 leading-snug">{item.title}</p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{item.source}</p>
            </div>
          </a>
        );
      })}
    </div>
  );
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing]     = useState(false);
  const [scanTriggered, setScanTriggered] = useState(false);

  const { data: patterns, isLoading: patLoading, isFetching: patFetching } = useQuery(
    marketDataQueryOptions(["patterns-overview"], () => api.patterns(), {
      staleTime: 10 * 60_000,
      refetchInterval: (query) => {
        const d = query.state.data as any;
        return d?.scanInProgress ? 3000 : false;
      },
    }),
  );

  const { data: macro, isLoading: macroLoading } = useQuery(
    marketDataQueryOptions(["macro-dash"], api.macroDashboard, { staleTime: 5 * 60_000 }),
  );

  const { data: fiiData, isLoading: fiiLoading } = useQuery<any>({
    queryKey: ["fii-dash-equity"],
    queryFn:  () => fetchApi("/insights/fii-dii?segment=equity&days=10"),
    staleTime: 10 * 60_000,
  });

  const { data: newsData, isLoading: newsLoading } = useQuery({
    queryKey: ["news-dash"],
    queryFn:  () => api.newsFeed({ limit: 5 }),
    staleTime: 5 * 60_000,
  });

  const scanInProgress = patterns?.scanInProgress ?? false;
  const scanProgress   = patterns?.scanProgress   ?? null;

  async function handleRunScan() {
    setScanTriggered(true);
    try {
      await api.triggerScan();
      await queryClient.invalidateQueries({ queryKey: ["patterns-overview"] });
    } finally {
      setScanTriggered(false);
    }
  }

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["patterns-overview"] }),
        queryClient.invalidateQueries({ queryKey: ["macro-dash"] }),
        queryClient.invalidateQueries({ queryKey: ["fii-dash-equity"] }),
        queryClient.invalidateQueries({ queryKey: ["news-dash"] }),
        queryClient.invalidateQueries({ queryKey: ["global-indices"] }),
      ]);
    } finally {
      setRefreshing(false);
    }
  }

  const isRefreshing = refreshing || patFetching;

  const latestFiiRow = useMemo(() => {
    const rows: any[] = fiiData?.rows ?? [];
    return rows.length > 0 ? rows[0] : null;
  }, [fiiData]);

  const fiiNet = latestFiiRow?.fiiNet ?? null;
  const diiNet = latestFiiRow?.diiNet ?? null;
  const fiiDate = latestFiiRow?.date ?? null;

  const newsItems = useMemo(() => {
    const articles: any[] = (newsData as any)?.articles ?? [];
    return articles.slice(0, 5);
  }, [newsData]);

  const vix = macro?.currencyStrip?.vix;

  return (
    <div className="space-y-6">

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Market Dashboard</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">Indian Stock Market · Live Overview</p>
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

      {/* ── Macro strip ─────────────────────────────────────────────────────── */}
      <MacroStrip />

      {/* ── 4 quick-glance cards ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <VixCard vix={vix} loading={macroLoading} />

        <StatCard
          loading={fiiLoading}
          title="FII Net · Today"
          value={fmtCr(fiiNet)}
          sub={fiiDate ?? undefined}
          subCls={fiiNet != null ? (fiiNet >= 0 ? "text-green-500" : "text-red-500") : "text-gray-400 dark:text-gray-500"}
          icon={<TrendingUp className="w-4 h-4" />}
        />

        <StatCard
          loading={fiiLoading}
          title="DII Net · Today"
          value={fmtCr(diiNet)}
          sub={fiiDate ?? undefined}
          subCls={diiNet != null ? (diiNet >= 0 ? "text-green-500" : "text-red-500") : "text-gray-400 dark:text-gray-500"}
          icon={<TrendingDown className="w-4 h-4" />}
        />

        <Link href="/patterns" className="block rounded-xl hover:ring-2 hover:ring-indigo-300 dark:hover:ring-indigo-600 transition-all">
          <StatCard
            loading={patLoading}
            title="Pattern Signals"
            value={patterns ? String(patterns.totalPatterns ?? 0) : "—"}
            sub={
              (scanInProgress || scanTriggered)
                ? <span className="flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" /> Scanning…</span>
                : patterns && (patterns.totalPatterns ?? 0) > 0
                  ? `↑${patterns.callSignals} bullish  ↓${patterns.putSignals} bearish`
                  : "Run a scan to detect"
            }
            icon={<Activity className="w-4 h-4" />}
          />
        </Link>
      </div>

      {/* ── Top Movers ──────────────────────────────────────────────────────── */}
      <TopMoversPanel />

      {/* ── Pattern Signals detail  +  News ──────────────────────────────────── */}
      <div className="grid md:grid-cols-2 gap-6">

        {/* Pattern Signals */}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 shadow-sm p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-gray-800 dark:text-gray-100 flex items-center gap-2">
              <Activity className="w-4 h-4 text-indigo-500" /> Pattern Signals
            </h2>
            {(patterns?.totalPatterns ?? 0) > 0 && (
              <Link href="/patterns" className="text-xs text-indigo-500 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300">
                View all →
              </Link>
            )}
          </div>

          {patLoading ? (
            <div className="space-y-3">
              <div className="flex gap-3">
                {[1,2,3].map(i => <div key={i} className="flex-1 h-16 bg-gray-100 dark:bg-gray-700 animate-pulse rounded-lg" />)}
              </div>
              {[1,2,3].map(i => <div key={i} className="h-5 bg-gray-100 dark:bg-gray-700 animate-pulse rounded" />)}
            </div>
          ) : patterns && (patterns.totalPatterns ?? 0) > 0 ? (
            <div className="space-y-3">
              {/* Slim scanning banner — shown while scan is running, data stays visible */}
              {(scanInProgress || scanTriggered) && (
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-100 dark:border-indigo-800">
                  <Loader2 className="w-3 h-3 text-indigo-500 animate-spin flex-shrink-0" />
                  <span className="text-xs text-indigo-700 dark:text-indigo-300 flex-1">
                    {scanProgress
                      ? `Updating… ${scanProgress.done.toLocaleString()} / ${scanProgress.total.toLocaleString()} symbols`
                      : "Scan in progress…"}
                  </span>
                  {scanProgress && scanProgress.total > 0 && (
                    <div className="w-16 bg-indigo-200 dark:bg-indigo-800 rounded-full h-1 overflow-hidden flex-shrink-0">
                      <div
                        className="h-full bg-indigo-500 transition-all duration-500 rounded-full"
                        style={{ width: `${Math.min(100, (scanProgress.done / scanProgress.total) * 100)}%` }}
                      />
                    </div>
                  )}
                </div>
              )}
              <div className="flex gap-3">
                <div className="flex-1 bg-green-50 dark:bg-green-900/25 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-green-600">{patterns.callSignals}</p>
                  <p className="text-xs text-green-700 dark:text-green-400 font-medium">Bullish</p>
                </div>
                <div className="flex-1 bg-red-50 dark:bg-red-900/25 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-red-600">{patterns.putSignals}</p>
                  <p className="text-xs text-red-700 dark:text-red-400 font-medium">Bearish</p>
                </div>
                <div className="flex-1 bg-blue-50 dark:bg-blue-900/25 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-blue-600">{patterns.totalPatterns}</p>
                  <p className="text-xs text-blue-700 dark:text-blue-400 font-medium">Total</p>
                </div>
              </div>
              <div className="space-y-1.5 pt-1">
                {patterns.topCalls?.slice(0, 3).map((p: any, i: number) => (
                  <div key={i} className="flex justify-between items-center text-sm py-0.5">
                    <span className="text-gray-700 dark:text-gray-300 flex items-center gap-1">
                      <span className="font-medium">{p.symbol}</span>
                      <ChartButton symbol={p.symbol} />
                      <span className="text-gray-400 dark:text-gray-500">{p.pattern}</span>
                    </span>
                    <span className="text-green-600 font-semibold">{p.confidence}%</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (scanInProgress || scanTriggered) ? (
            /* No existing data yet — show full scanning state */
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
          ) : (
            <div className="flex flex-col items-center justify-center py-5 gap-3">
              <div className="w-12 h-12 rounded-full bg-indigo-50 dark:bg-indigo-900/30 flex items-center justify-center">
                <ScanSearch className="w-6 h-6 text-indigo-400" />
              </div>
              <div className="text-center">
                <p className="text-sm font-medium text-gray-700 dark:text-gray-200">No scan data yet</p>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                  Detect bullish &amp; bearish chart patterns across all NSE stocks
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
        </div>

        {/* Market News */}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 shadow-sm p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-gray-800 dark:text-gray-100 flex items-center gap-2">
              <Newspaper className="w-4 h-4 text-blue-500" /> Market News
            </h2>
            <Link href="/news" className="text-xs text-indigo-500 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300">
              View all →
            </Link>
          </div>
          <NewsPanel loading={newsLoading} items={newsItems} />
        </div>

      </div>

      {/* ── Global Indices ───────────────────────────────────────────────────── */}
      <GlobalIndicesPanel />

    </div>
  );
}
