import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "wouter";
import { api, fetchApi } from "@/lib/api";
import {
  RefreshCw, Activity, Loader2,
  Newspaper, TrendingUp, TrendingDown, Rocket, BarChart2, Layers,
} from "lucide-react";
import MacroStrip from "@/components/macro/MacroStrip";
import GlobalIndicesPanel from "@/components/GlobalIndicesPanel";
import TopMoversPanel from "@/components/TopMoversPanel";
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
    <div className="h-full bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 shadow-sm p-4 flex flex-col gap-2">
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
  const [refreshing, setRefreshing] = useState(false);

  const { data: patterns, isLoading: patLoading, isFetching: patFetching } = useQuery(
    marketDataQueryOptions(["patterns-overview"], () => api.patterns(), {
      staleTime: 10 * 60_000,
      refetchInterval: (query) => {
        const d = query.state.data as any;
        return d?.scanInProgress ? 3000 : false;
      },
    }),
  );

  const { data: fiiData, isLoading: fiiLoading } = useQuery<any>({
    queryKey: ["fii-dash-equity"],
    queryFn:  () => fetchApi("/insights/fii-dii?segment=equity&days=30"),
    staleTime: 10 * 60_000,
  });

  const { data: rotation, isLoading: rotLoading } = useQuery(
    marketDataQueryOptions(["sector-rotation-dash"], api.sectorRotation, { staleTime: 5 * 60_000 }),
  );

  const { data: newsData, isLoading: newsLoading } = useQuery({
    queryKey: ["news-dash"],
    queryFn:  () => api.newsFeed({ limit: 5 }),
    staleTime: 5 * 60_000,
  });

  const { data: ipoData, isLoading: ipoLoading } = useQuery<any>({
    queryKey: ["ipo-dash"],
    queryFn:  () => fetchApi("/insights/ipos"),
    staleTime: 10 * 60_000,
  });

  const scanInProgress = patterns?.scanInProgress ?? false;

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["patterns-overview"] }),
        queryClient.invalidateQueries({ queryKey: ["sector-rotation-dash"] }),
        queryClient.invalidateQueries({ queryKey: ["fii-dash-equity"] }),
        queryClient.invalidateQueries({ queryKey: ["news-dash"] }),
        queryClient.invalidateQueries({ queryKey: ["global-indices"] }),
        queryClient.invalidateQueries({ queryKey: ["ipo-dash"] }),
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

  const fiiNet  = latestFiiRow?.fiiNet  ?? null;
  const diiNet  = latestFiiRow?.diiNet  ?? null;
  const fiiDate = latestFiiRow?.date    ?? null;

  // Smart FII/DII card title — show "· Today" / "· Yesterday" only when it matches
  const todayIso     = new Date().toISOString().slice(0, 10);
  const yesterdayIso = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
  const fiiSuffix = fiiDate === todayIso ? " · Today" : fiiDate === yesterdayIso ? " · Yesterday" : "";

  // A/D Ratio & Market Phase from sector rotation
  const adRatio    = (rotation as any)?.adRatio     ?? null;
  const breadth    = (rotation as any)?.marketBreadth ?? {};
  const rotPhase   = (rotation as any)?.rotationPhase ?? null;

  // Colour helpers
  const adCls = adRatio == null ? "text-gray-400 dark:text-gray-500"
    : adRatio >= 1.5 ? "text-emerald-600 dark:text-emerald-400"
    : adRatio >= 0.8 ? "text-amber-600 dark:text-amber-400"
    : "text-red-600 dark:text-red-400";

  const phaseLower  = (rotPhase ?? "").toLowerCase();
  const phaseCls    = phaseLower.includes("bear") || phaseLower.includes("recession")
    ? "text-red-600 dark:text-red-400"
    : phaseLower.includes("slow") || phaseLower.includes("late")
    ? "text-amber-600 dark:text-amber-400"
    : phaseLower.includes("full") || phaseLower.includes("early")
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-blue-600 dark:text-blue-400";

  const newsItems = useMemo(() => {
    const articles: any[] = (newsData as any)?.articles ?? [];
    return articles.slice(0, 5);
  }, [newsData]);

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

      {/* ── 5 quick-glance cards ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">

        {/* FII Net */}
        <Link href="/insights/fii-dii" className="block rounded-xl hover:ring-2 hover:ring-indigo-300 dark:hover:ring-indigo-600 transition-all">
          <StatCard
            loading={fiiLoading}
            title={`FII Net${fiiSuffix}`}
            value={fmtCr(fiiNet)}
            sub={fiiDate ? fiiDate : undefined}
            subCls={fiiNet != null ? (fiiNet >= 0 ? "text-green-500" : "text-red-500") : "text-gray-400 dark:text-gray-500"}
            icon={<TrendingUp className="w-4 h-4" />}
          />
        </Link>

        {/* DII Net */}
        <Link href="/insights/fii-dii" className="block rounded-xl hover:ring-2 hover:ring-indigo-300 dark:hover:ring-indigo-600 transition-all">
          <StatCard
            loading={fiiLoading}
            title={`DII Net${fiiSuffix}`}
            value={fmtCr(diiNet)}
            sub={fiiDate ? fiiDate : undefined}
            subCls={diiNet != null ? (diiNet >= 0 ? "text-green-500" : "text-red-500") : "text-gray-400 dark:text-gray-500"}
            icon={<TrendingDown className="w-4 h-4" />}
          />
        </Link>

        {/* A/D Ratio */}
        <Link href="/rotation" className="block rounded-xl hover:ring-2 hover:ring-indigo-300 dark:hover:ring-indigo-600 transition-all">
          <StatCard
            loading={rotLoading}
            title="A/D Ratio"
            value={adRatio == null ? "∞" : adRatio.toFixed(2)}
            sub={
              breadth.advancing != null
                ? `↑${breadth.advancing} adv  ↓${breadth.declining ?? 0} dec`
                : undefined
            }
            subCls={adCls}
            icon={<BarChart2 className="w-4 h-4" />}
          />
        </Link>

        {/* Market Phase */}
        <Link href="/rotation" className="block rounded-xl hover:ring-2 hover:ring-indigo-300 dark:hover:ring-indigo-600 transition-all">
          <StatCard
            loading={rotLoading}
            title="Market Phase"
            value={rotPhase ?? "—"}
            sub={breadth.breadthScore != null ? `Breadth ${breadth.breadthScore > 0 ? "+" : ""}${breadth.breadthScore}` : undefined}
            subCls={phaseCls}
            icon={<Layers className="w-4 h-4" />}
          />
        </Link>

        {/* Pattern Signals (clickable) */}
        <Link href="/patterns" className="block rounded-xl hover:ring-2 hover:ring-indigo-300 dark:hover:ring-indigo-600 transition-all">
          <StatCard
            loading={patLoading}
            title="Pattern Signals"
            value={patterns ? String(patterns.totalPatterns ?? 0) : "—"}
            sub={
              scanInProgress
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

      {/* ── IPO Center  +  News ──────────────────────────────────────────────── */}
      <div className="grid md:grid-cols-2 gap-6">

        {/* IPO Center */}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 shadow-sm p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-gray-800 dark:text-gray-100 flex items-center gap-2">
              <Rocket className="w-4 h-4 text-indigo-500" /> IPO Center
            </h2>
            <Link href="/insights/ipo" className="text-xs text-indigo-500 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300">
              View all →
            </Link>
          </div>

          {ipoLoading ? (
            <div className="space-y-3">
              {[1,2,3].map(i => <div key={i} className="h-14 bg-gray-100 dark:bg-gray-700 animate-pulse rounded-lg" />)}
            </div>
          ) : (() => {
            const open     = (ipoData?.open     ?? []).slice(0, 2);
            const upcoming = (ipoData?.upcoming  ?? []).slice(0, 3 - open.length);
            const all      = [...open, ...upcoming];

            if (!ipoData?.available && !all.length) {
              return (
                <div className="flex flex-col items-center justify-center py-6 gap-2 text-center">
                  <Rocket className="w-8 h-8 text-gray-300 dark:text-gray-600" />
                  <p className="text-sm text-gray-500 dark:text-gray-400">{ipoData?.message ?? "No active IPOs right now"}</p>
                </div>
              );
            }

            if (!all.length) {
              return (
                <div className="flex flex-col items-center justify-center py-6 gap-2 text-center">
                  <Rocket className="w-8 h-8 text-gray-300 dark:text-gray-600" />
                  <p className="text-sm text-gray-500 dark:text-gray-400">No active or upcoming IPOs right now</p>
                </div>
              );
            }

            const fmtDate = (iso: string | null) => {
              if (!iso) return "—";
              const d = new Date(iso + "T00:00:00");
              return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
            };

            const daysUntil = (iso: string | null) => {
              if (!iso) return null;
              const today = new Date(); today.setHours(0,0,0,0);
              return Math.round((new Date(iso + "T00:00:00").getTime() - today.getTime()) / 86_400_000);
            };

            return (
              <div className="space-y-2.5">
                {all.map((ipo: any, i: number) => {
                  const isOpen    = ipo.status === "open";
                  const closesIn  = daysUntil(ipo.closeDate);
                  const opensIn   = daysUntil(ipo.openDate);
                  const gmp       = ipo.gmp;
                  const hasGmp    = gmp && gmp.premium != null;
                  const gmpUp     = hasGmp && gmp.premium > 0;
                  const gmpDown   = hasGmp && gmp.premium < 0;
                  const priceStr  = ipo.priceHigh != null
                    ? (ipo.priceLow && ipo.priceLow !== ipo.priceHigh ? `₹${ipo.priceLow}–${ipo.priceHigh}` : `₹${ipo.priceHigh}`)
                    : null;

                  return (
                    <div key={i} className="flex items-start gap-3 p-3 rounded-lg border border-gray-100 dark:border-gray-700 hover:border-indigo-200 dark:hover:border-indigo-700 transition">
                      {/* Status dot */}
                      <div className={`mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${isOpen ? "bg-green-400 animate-pulse" : "bg-gray-300 dark:bg-gray-600"}`} />

                      {/* Main info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="text-sm font-semibold text-gray-900 dark:text-white truncate max-w-[140px]" title={ipo.companyName}>
                            {ipo.companyName}
                          </span>
                          {ipo.isSme && (
                            <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300 flex-shrink-0">SME</span>
                          )}
                          {isOpen ? (
                            <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded flex-shrink-0 ${
                              closesIn === 0 ? "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300"
                              : closesIn === 1 ? "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300"
                              : "bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-300"
                            }`}>
                              {closesIn != null ? (closesIn === 0 ? "Closes today" : closesIn === 1 ? "1d left" : `${closesIn}d left`) : "Open"}
                            </span>
                          ) : (
                            <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300 flex-shrink-0">
                              {opensIn != null && opensIn > 0 ? `Opens in ${opensIn}d` : "Upcoming"}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          {priceStr && <span className="text-xs text-gray-500 dark:text-gray-400">{priceStr}</span>}
                          {ipo.openDate && <span className="text-xs text-gray-400 dark:text-gray-500">{fmtDate(ipo.openDate)}–{fmtDate(ipo.closeDate)}</span>}
                        </div>
                      </div>

                      {/* GMP badge */}
                      {hasGmp ? (
                        <div className={`flex-shrink-0 text-right rounded-md px-2 py-1 ${
                          gmpUp   ? "bg-emerald-50 dark:bg-emerald-500/10"
                          : gmpDown ? "bg-rose-50 dark:bg-rose-500/10"
                          : "bg-gray-50 dark:bg-gray-700/40"
                        }`}>
                          <p className="text-[9px] uppercase tracking-wide font-bold text-gray-400 leading-tight">GMP</p>
                          <p className={`text-xs font-bold tabular-nums leading-tight ${
                            gmpUp ? "text-emerald-600 dark:text-emerald-400"
                            : gmpDown ? "text-rose-600 dark:text-rose-400"
                            : "text-gray-600 dark:text-gray-300"
                          }`}>
                            {gmp.premium >= 0 ? "+" : ""}₹{gmp.premium}
                          </p>
                          {gmp.estGainPct != null && (
                            <p className={`text-[9px] font-semibold tabular-nums leading-tight ${
                              gmpUp ? "text-emerald-500" : gmpDown ? "text-rose-500" : "text-gray-500"
                            }`}>
                              {gmp.estGainPct >= 0 ? "+" : ""}{gmp.estGainPct.toFixed(1)}%
                            </p>
                          )}
                        </div>
                      ) : (
                        <div className="flex-shrink-0 text-right rounded-md px-2 py-1 bg-gray-50 dark:bg-gray-700/40">
                          <p className="text-[9px] uppercase tracking-wide font-bold text-gray-400 leading-tight">GMP</p>
                          <p className="text-xs text-gray-400 dark:text-gray-500">—</p>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })()}
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
