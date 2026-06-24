import { useState, useCallback, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import {
  RefreshCw, AlertTriangle,
  BarChart2, Info, Gauge,
} from "lucide-react";
import DataFreshness from "@/components/DataFreshness";
import { pickMeta, marketDataQueryOptions } from "@/lib/marketData";
import { useTheme } from "@/context/ThemeContext";

// ── Types ─────────────────────────────────────────────────────────────────────
// Every numeric reading can be null when its upstream feed is unavailable.
// The page must render "—" / a "Data unavailable" panel in that case rather
// than substituting a synthetic 0 (which would look like a real flat reading).
interface Component { name: string; score: number | null; weight: number;
                      detail: string; available?: boolean }
interface VixData    { available?: boolean; current: number | null;
                       change5d_pct: number | null; score: number | null;
                       interpretation: { level: string; emoji: string; color: string; text: string } | null }
interface PcrData    { available?: boolean; proxy_value: number | null;
                       score: number | null; note: string;
                       interpretation: { level: string; emoji: string; color: string; text: string } | null }
interface NewsData   { available?: boolean; total_articles: number;
                       bullish: number; bearish: number; neutral: number;
                       mood: string; score: number | null }
interface PriceAction{ available?: boolean; score: number | null;
                       compound: number | null; label: string;
                       indicators: { momentum5d?: number; momentum20d?: number; rsi14?: number } }
interface Signal     { type: string; title: string; description: string;
                       signal: string; direction: string; emoji: string; color: string }
interface Strategy   { strategy: string; outlook: string; vol: string; risk: string }
interface Availability { news: boolean; price_action: boolean; vix: boolean; pcr: boolean }
interface Sentiment  {
  composite: number | null; label: string; timestamp: string;
  availability?: Availability;
  components: Component[]; vix: VixData; pcr: PcrData;
  news: NewsData; price_action: PriceAction;
  contrarian_signals: Signal[]; strategy_recommendations: Strategy[];
}
interface SectorItem { sector: string; score: number | null; label: string;
                       compound: number | null; available?: boolean;
                       momentum5d?: number | null; rsi14?: number | null }
interface SectorsResp{ sectors: SectorItem[]; count: number }

// ── Helpers ───────────────────────────────────────────────────────────────────
function scoreColor(score: number, dark = false): string {
  if (score >= 50)  return dark ? "text-emerald-400" : "text-emerald-600";
  if (score >= 20)  return dark ? "text-green-400"   : "text-green-600";
  if (score > -20)  return dark ? "text-gray-300"    : "text-gray-600";
  if (score > -50)  return dark ? "text-orange-400"  : "text-orange-600";
  return dark ? "text-red-400" : "text-red-600";
}

function scoreBg(score: number): string {
  if (score >= 50)  return "bg-emerald-500";
  if (score >= 20)  return "bg-green-500";
  if (score > -20)  return "bg-gray-400";
  if (score > -50)  return "bg-orange-500";
  return "bg-red-500";
}

function sectorBg(score: number): string {
  if (score >= 40)  return "bg-emerald-500";
  if (score >= 15)  return "bg-green-400";
  if (score > -15)  return "bg-gray-300 dark:bg-gray-600";
  if (score > -40)  return "bg-orange-400";
  return "bg-red-500";
}

function sectorText(score: number): string {
  if (score > -15)  return "text-gray-800 dark:text-white";
  return "text-white";
}

function signalBorderColor(color: string): string {
  return color === "amber" ? "border-amber-400 bg-amber-50 dark:bg-amber-900/20"
       : color === "red"   ? "border-red-400 bg-red-50 dark:bg-red-900/20"
       : color === "green" ? "border-green-400 bg-green-50 dark:bg-green-900/20"
       : color === "blue"  ? "border-blue-400 bg-blue-50 dark:bg-blue-900/20"
       : "border-orange-400 bg-orange-50 dark:bg-orange-900/20";
}

// ── Aesthetic flow diagram (matches Dashboard SentimentFlow) ─────────────────
function SentimentFlow({ score, label, components }: {
  score: number | null; label: string; components: Component[];
}) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(false);
    const t = setTimeout(() => setMounted(true), 100);
    return () => clearTimeout(t);
  }, [score]);

  const hubColor =
    score == null ? "#64748b"
    : score >= 20  ? "#22c55e"
    : score >= 5   ? "#4ade80"
    : score > -5   ? "#94a3b8"
    : score > -20  ? "#fb923c"
    : "#f87171";

  function compAccent(sc: number | null): string {
    if (sc == null) return "#64748b";
    if (sc >= 10) return "#22c55e";
    if (sc >= 0)  return "#4ade80";
    if (sc > -10) return "#94a3b8";
    return "#f87171";
  }

  function compScore(key: string) {
    const c = components.find((c: Component) =>
      (c.name ?? "").toLowerCase().includes(key.toLowerCase().split(" ")[0])
    );
    return c?.score ?? null;
  }

  const W = 380, H = 224, HX = 190, HY = 122, HR = 48;
  const hubFill = isDark ? "#0f172a" : "#ffffff";

  const nodes = [
    { cx: 190, cy: 22,  hw: 76, hh: 16, key: "News Sentiment", short: "NEWS SENTIMENT", curveBias: 0   },
    { cx: 48,  cy: 196, hw: 58, hh: 16, key: "Price Action",   short: "PRICE ACTION",   curveBias: 28  },
    { cx: 332, cy: 196, hw: 52, hh: 16, key: "India VIX",      short: "INDIA VIX",      curveBias: -28 },
  ] as const;

  function makePath(n: typeof nodes[number]): string {
    const dx = HX - n.cx, dy = HY - n.cy;
    const dist = Math.sqrt(dx * dx + dy * dy);
    const ux = dx / dist, uy = dy / dist;
    const sy = n.cy < HY ? n.cy + n.hh : n.cy - n.hh;
    const ex = HX - ux * HR, ey = HY - uy * HR;
    const mx = (n.cx + ex) / 2, my = (sy + ey) / 2;
    return `M ${n.cx} ${sy} Q ${mx + (-uy * n.curveBias)} ${my + (ux * n.curveBias)} ${ex} ${ey}`;
  }

  const paths = nodes.map((n, i) => ({ d: makePath(n), id: `sdf-${i}` }));
  const scoreStr = score != null ? (score > 0 ? `+${score}` : `${score}`) : "—";

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: H }}>
      <defs>
        <style>{`
          @keyframes sdf-dash { from { stroke-dashoffset: 10; } to { stroke-dashoffset: 0; } }
          @keyframes sdf-r1 { 0%,100% { r:${HR+3}px; opacity:.35; } 50% { r:${HR+11}px; opacity:.08; } }
          @keyframes sdf-r2 { 0%,100% { r:${HR+7}px; opacity:.18; } 50% { r:${HR+17}px; opacity:.04; } }
          @keyframes sdf-cd { 0%,100% { r:3px; opacity:1; } 50% { r:2px; opacity:.4; } }
          .sdf-r1 { animation: sdf-r1 2.6s ease-in-out infinite; }
          .sdf-r2 { animation: sdf-r2 2.6s ease-in-out infinite .9s; }
          .sdf-cd { animation: sdf-cd 1.6s ease-in-out infinite; }
        `}</style>
        <filter id="sdf-glow" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="3.5" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <filter id="sdf-hub-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="10" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <radialGradient id="sdf-aura" cx="50%" cy="50%" r="50%">
          <stop offset="0%"   stopColor={hubColor} stopOpacity="0.22" />
          <stop offset="55%"  stopColor={hubColor} stopOpacity="0.07" />
          <stop offset="100%" stopColor={hubColor} stopOpacity="0"    />
        </radialGradient>
        <radialGradient id="sdf-hub-fill" cx="40%" cy="35%" r="65%">
          <stop offset="0%"   stopColor={hubColor} stopOpacity={isDark ? "0.18" : "0.10"} />
          <stop offset="100%" stopColor={hubColor} stopOpacity="0" />
        </radialGradient>
        {nodes.map((n, i) => {
          const col = compAccent(compScore(n.key));
          return (
            <linearGradient key={i} id={`sdf-lg-${i}`} gradientUnits="userSpaceOnUse"
              x1={n.cx} y1={n.cy < HY ? n.cy + n.hh : n.cy - n.hh} x2={HX} y2={HY}>
              <stop offset="0%"   stopColor={col}     stopOpacity="1"   />
              <stop offset="100%" stopColor={hubColor} stopOpacity="0.7" />
            </linearGradient>
          );
        })}
      </defs>

      <ellipse cx={HX} cy={HY} rx={105} ry={82} fill="url(#sdf-aura)"
        style={{ opacity: mounted ? 1 : 0, transition: "opacity 1s" }} />
      <circle className="sdf-r1" cx={HX} cy={HY} r={HR + 3}
        fill="none" stroke={hubColor} strokeWidth="1"
        style={{ opacity: mounted ? undefined : 0 }} />
      <circle className="sdf-r2" cx={HX} cy={HY} r={HR + 7}
        fill="none" stroke={hubColor} strokeWidth="0.5"
        style={{ opacity: mounted ? undefined : 0 }} />

      {paths.map(({ d, id }, i) => {
        const col = compAccent(compScore(nodes[i].key));
        return (
          <g key={i}>
            <path d={d} fill="none" stroke={col} strokeWidth="4" strokeOpacity="0.28"
              filter="url(#sdf-glow)"
              style={{ opacity: mounted ? 1 : 0, transition: `opacity .6s ${i * .15}s` }} />
            <path id={id} d={d} fill="none"
              stroke={`url(#sdf-lg-${i})`} strokeWidth="1.6" strokeDasharray="5 5"
              style={{
                opacity: mounted ? 0.9 : 0,
                transition: `opacity .5s ${i * .15}s`,
                animation: mounted ? `sdf-dash .9s linear infinite ${i * .25}s` : undefined,
              }} />
            {mounted && ([0, 0.45, 0.78] as number[]).map((delay, pi) => (
              <circle key={pi} r="3.2" fill={col}>
                <animateMotion dur="1.9s" repeatCount="indefinite" begin={`${delay}s`}
                  keyPoints="0;1" keyTimes="0;1" calcMode="linear">
                  <mpath href={`#${id}`} />
                </animateMotion>
                <animate attributeName="opacity" dur="1.9s" repeatCount="indefinite" begin={`${delay}s`}
                  values="0;1;1;0" keyTimes="0;0.07;0.9;1" />
                <animate attributeName="r" dur="1.9s" repeatCount="indefinite" begin={`${delay}s`}
                  values="0;3.2;2.8;0" keyTimes="0;0.07;0.9;1" />
              </circle>
            ))}
          </g>
        );
      })}

      <circle cx={HX} cy={HY} r={HR + 8} fill={hubColor} opacity="0.12"
        filter="url(#sdf-hub-glow)"
        style={{ opacity: mounted ? 0.12 : 0, transition: "opacity .8s" }} />
      <circle cx={HX} cy={HY} r={HR} fill={hubFill} stroke={hubColor} strokeWidth="1.8"
        style={{ filter: `drop-shadow(0 0 8px ${hubColor}55)` }} />
      <circle cx={HX} cy={HY} r={HR} fill="url(#sdf-hub-fill)" />
      <circle cx={HX} cy={HY} r={HR - 8} fill="none" stroke={hubColor}
        strokeWidth="0.5" strokeOpacity="0.3" />

      <text x={HX} y={HY - 7} textAnchor="middle"
        fontSize="20" fontWeight="900" letterSpacing="-0.5"
        fill={hubColor} style={{ fontFamily: "system-ui,sans-serif" }}>{scoreStr}</text>
      <text x={HX} y={HY + 11} textAnchor="middle"
        fontSize="7" fontWeight="700" letterSpacing="1.5"
        fill={hubColor} fillOpacity="0.75"
        style={{ fontFamily: "system-ui,sans-serif" }}>{label.toUpperCase()}</text>

      <circle className="sdf-cd" cx={HX} cy={HY} r={3} fill={hubColor}
        style={{ opacity: mounted ? undefined : 0 }} />

      {nodes.map((n, i) => {
        const sc  = compScore(n.key);
        const col = compAccent(sc);
        const comp = components.find((c: Component) =>
          (c.name ?? "").toLowerCase().includes(n.key.toLowerCase().split(" ")[0])
        );
        const weight = comp?.weight;
        return (
          <g key={i} style={{ opacity: mounted ? 1 : 0, transition: `opacity .55s ${i * .13}s` }}>
            <rect x={n.cx - n.hw - 1} y={n.cy - n.hh - 1}
              width={n.hw * 2 + 2} height={n.hh * 2 + 2}
              rx="10" fill={col} opacity="0.12" filter="url(#sdf-glow)" />
            <rect x={n.cx - n.hw} y={n.cy - n.hh}
              width={n.hw * 2} height={n.hh * 2}
              rx="9" ry="9" fill={col} fillOpacity="0.11"
              stroke={col} strokeWidth="1.1" strokeOpacity="0.75" />
            <text x={n.cx} y={n.cy - 2} textAnchor="middle" dominantBaseline="middle"
              fontSize="6.8" fontWeight="800" letterSpacing="0.7"
              fill={col} style={{ fontFamily: "system-ui,sans-serif" }}>
              {n.short}{weight != null ? ` · ${weight}%` : ""}
            </text>
            {sc != null && (
              <text x={n.cx} y={n.cy + 8} textAnchor="middle"
                fontSize="6.2" fontWeight="600" fill={col} fillOpacity="0.7"
                style={{ fontFamily: "system-ui,sans-serif" }}>
                {sc > 0 ? `+${sc}` : sc}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

// ── Component bar ─────────────────────────────────────────────────────────────
function ComponentBar({ comp, index = 0 }: { comp: Component; index?: number }) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const [barWidth, setBarWidth] = useState(0);
  const isUnavailable = comp.score == null || comp.available === false;
  const isInformational = comp.weight === 0;
  const weightLabel = isInformational ? "info" : `${comp.weight}%`;

  useEffect(() => {
    if (comp.score == null) return;
    const t = setTimeout(
      () => setBarWidth(Math.min(100, Math.abs(comp.score as number))),
      100 + index * 70,
    );
    return () => clearTimeout(t);
  }, [comp.score, index]);

  const trackBg  = isDark ? "#1e293b" : "#f1f5f9";
  const nameTxt  = isDark ? "#94a3b8" : "#475569";
  const detailTxt = isDark ? "#475569" : "#94a3b8";
  const unavailBadgeBg = isDark ? "#0f172a" : "#f1f5f9";
  const unavailBadgeTxt = isDark ? "#475569" : "#94a3b8";
  const unavailBadgeBorder = isDark ? "#1e293b" : "#e2e8f0";
  const unavailBar = isDark ? "#334155" : "#cbd5e1";
  const badgeBg = isDark ? "rgba(99,102,241,0.1)" : "#eef2ff";
  const badgeBorder = isDark ? "rgba(99,102,241,0.2)" : "#c7d2fe";

  if (isUnavailable) {
    return (
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium" style={{ color: nameTxt }}>{comp.name}</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded"
            style={{ background: unavailBadgeBg, color: unavailBadgeTxt, border: `1px solid ${unavailBadgeBorder}` }}>
            —
          </span>
        </div>
        <div className="h-2 rounded-full overflow-hidden" style={{ background: trackBg }}>
          <div className="h-full rounded-full opacity-40" style={{ width: "100%", background: unavailBar }} />
        </div>
        <p className="text-[10px] italic truncate" style={{ color: detailTxt }}>{comp.detail || "Unavailable"}</p>
      </div>
    );
  }

  const score = comp.score as number;
  const positive = score >= 0;
  const fillGradient = positive
    ? "linear-gradient(90deg, #15803d, #4ade80)"
    : "linear-gradient(90deg, #b91c1c, #f87171)";
  const glowColor  = positive ? "rgba(74,222,128,0.35)" : "rgba(248,113,113,0.35)";
  const scoreColor = positive
    ? (isDark ? "#4ade80" : "#16a34a")
    : (isDark ? "#f87171" : "#dc2626");

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium truncate" style={{ color: nameTxt }}>{comp.name}</span>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="text-xs font-bold" style={{ color: scoreColor }}>
            {score > 0 ? "+" : ""}{score}
          </span>
          <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded"
            style={{ background: badgeBg, color: "#6366f1", border: `1px solid ${badgeBorder}` }}>
            {weightLabel}
          </span>
        </div>
      </div>

      <div className="h-2.5 rounded-full overflow-hidden" style={{ background: trackBg }}>
        <div
          className="h-full rounded-full"
          style={{
            width: `${barWidth}%`,
            background: fillGradient,
            boxShadow: `0 0 8px ${glowColor}`,
            transition: "width 0.9s cubic-bezier(0.34,1.56,0.64,1)",
          }}
        />
      </div>

      <p className="text-[10px] truncate" style={{ color: detailTxt }}>{comp.detail}</p>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function SentimentDashboard() {
  const [refreshing, setRefreshing] = useState(false);

  // Stable query keys — never changed. We use refetch() to re-run the query
  // so keepPreviousData keeps the old values visible while the new fetch is
  // in flight. Changing the key (old refreshKey pattern) caused isLoading=true
  // → all data vanished for a blink.
  const { data: sentiment, isLoading, isFetching: sentimentFetching, error, refetch: refetchSentiment } = useQuery<Sentiment>(
    marketDataQueryOptions<Sentiment, { retry: number }>(
      ["sentiment-market"],
      () => fetchApi<Sentiment>("/sentiment/market"),
      { retry: 1 },
    ),
  );

  const { data: sectorsData, isFetching: sectorsFetching, refetch: refetchSectors } = useQuery<SectorsResp>(
    marketDataQueryOptions<SectorsResp, { retry: number }>(
      ["sentiment-sectors"],
      () => fetchApi<SectorsResp>("/sentiment/sectors"),
      { retry: 1 },
    ),
  );

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      // Tell the backend to bust its sentiment + news caches first,
      // then re-fetch the updated data in the background.
      // refetch() uses keepPreviousData so the existing cards stay
      // visible — no flash to empty state.
      await fetchApi("/sentiment/refresh");
      await Promise.all([refetchSentiment(), refetchSectors()]);
    } finally {
      setRefreshing(false);
    }
  }, [refetchSentiment, refetchSectors]);

  const score    = sentiment?.composite ?? null;
  const sectors  = sectorsData?.sectors ?? [];
  const meta     = pickMeta(sentiment) ?? pickMeta(sectorsData);

  // ── Format timestamp (force IST so users abroad see Indian market time) ─────
  const updatedAt = sentiment?.timestamp
    ? new Date(sentiment.timestamp).toLocaleTimeString("en-IN", {
        hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata",
      }) + " IST"
    : null;

  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-10">

      {/* ── Header ───────────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Gauge className="w-6 h-6 text-indigo-500" /> Market Sentiment
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
            Centralized composite analysis — News · Price Action · VIX · PCR Proxy
            {updatedAt && <span className="ml-2 text-xs">· Updated {updatedAt}</span>}
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <DataFreshness meta={meta} hideRefresh />
          <button
            onClick={handleRefresh}
            disabled={refreshing || isLoading}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-semibold px-4 py-2 rounded-lg transition"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-20 text-gray-400 gap-3">
          <RefreshCw className="w-5 h-5 animate-spin" /> Computing sentiment…
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4 text-red-600 dark:text-red-400 text-sm">
          <AlertTriangle className="w-4 h-4 shrink-0" /> Failed to load sentiment data. Check that the API server is running.
        </div>
      )}

      {sentiment && (
        <>
          {/* ── Contrarian signals ─────────────────────────────────────────── */}
          {sentiment.contrarian_signals.length > 0 && (
            <div className="space-y-2">
              {sentiment.contrarian_signals.map((sig, i) => (
                <div key={i} className={`border rounded-xl p-4 ${signalBorderColor(sig.color)}`}>
                  <div className="flex items-start gap-3">
                    <span className="text-2xl">{sig.emoji}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2 mb-1">
                        <span className="font-bold text-sm text-gray-900 dark:text-white">{sig.title}</span>
                        <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full
                          ${sig.color === "amber" ? "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300"
                            : sig.color === "red" ? "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300"
                            : "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300"}`}>
                          {sig.signal}
                        </span>
                      </div>
                      <p className="text-xs text-gray-600 dark:text-gray-400">{sig.description}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* ── Main cards row ─────────────────────────────────────────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

            {/* Gauge card */}
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-6 flex flex-col items-center gap-4 lg:col-span-1">
              <h2 className="text-sm font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest self-start">
                Composite Score
              </h2>
              <SentimentFlow score={score} label={sentiment.label} components={sentiment.components} />

              {/* Weight breakdown */}
              <div className="w-full space-y-3 pt-2 border-t border-gray-100 dark:border-gray-800">
                {sentiment.components.map((c, i) => (
                  <ComponentBar key={i} comp={c} index={i} />
                ))}
              </div>
            </div>

            {/* VIX + PCR panel */}
            <div className="space-y-4 lg:col-span-1">

              {/* VIX card */}
              <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-5">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest">
                    India VIX
                  </h2>
                  <span className="text-xs text-gray-400">Fear Gauge</span>
                </div>
                {sentiment.vix.current == null || sentiment.vix.interpretation == null ? (
                  <div className="rounded-lg p-3 text-xs border bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400">
                    VIX feed unavailable. The VIX leg is excluded from the composite until the next refresh succeeds.
                  </div>
                ) : (
                  <>
                    <div className="flex items-end gap-3 mb-3">
                      <span className="text-4xl font-black text-gray-900 dark:text-white">
                        {sentiment.vix.current.toFixed(1)}
                      </span>
                      {sentiment.vix.change5d_pct != null && (
                        <span className={`text-sm font-medium mb-1 ${sentiment.vix.change5d_pct >= 0 ? "text-red-500" : "text-emerald-500"}`}>
                          {sentiment.vix.change5d_pct > 0 ? "▲" : "▼"} {Math.abs(sentiment.vix.change5d_pct).toFixed(1)}% (5d)
                        </span>
                      )}
                    </div>

                    {/* VIX level bar */}
                    <div className="relative h-3 bg-gradient-to-r from-emerald-400 via-yellow-400 to-red-500 rounded-full mb-3">
                      <div
                        className="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-white border-2 border-gray-800 dark:border-white rounded-full shadow-sm"
                        style={{ left: `${Math.min(95, Math.max(5, (sentiment.vix.current / 40) * 100))}%` }}
                      />
                    </div>
                    <div className="flex justify-between text-[10px] text-gray-400 mb-3">
                      <span>0 (Calm)</span><span>20</span><span>40+ (Panic)</span>
                    </div>

                    <div className={`rounded-lg p-3 text-xs border
                      ${sentiment.vix.current < 15 ? "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800"
                      : sentiment.vix.current < 22 ? "bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800"
                      : "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800"}`}>
                      <p className="font-semibold text-gray-800 dark:text-gray-200 mb-0.5">
                        {sentiment.vix.interpretation.emoji} {sentiment.vix.interpretation.level}
                      </p>
                      <p className="text-gray-600 dark:text-gray-400">{sentiment.vix.interpretation.text}</p>
                    </div>
                  </>
                )}
              </div>

              {/* PCR card — display only, derived from VIX, not in composite */}
              <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-5">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest">
                    PCR Proxy
                  </h2>
                  <span className="text-[10px] text-gray-400 uppercase tracking-wider">Informational</span>
                </div>
                {sentiment.pcr.proxy_value == null || sentiment.pcr.interpretation == null ? (
                  <div className="rounded-lg p-3 text-xs border bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400">
                    PCR proxy requires VIX — currently unavailable.
                  </div>
                ) : (
                  <>
                    <div className="flex items-end gap-3 mb-3">
                      <span className="text-4xl font-black text-gray-900 dark:text-white">
                        {sentiment.pcr.proxy_value.toFixed(2)}
                      </span>
                      <span className={`text-xs mb-1.5 font-medium ${sentiment.pcr.proxy_value > 1.0 ? "text-red-500" : "text-emerald-500"}`}>
                        {sentiment.pcr.interpretation.level}
                      </span>
                    </div>

                    {/* PCR zones bar */}
                    <div className="relative h-3 rounded-full mb-1 overflow-hidden">
                      <div className="absolute inset-0 flex">
                        <div className="flex-1 bg-emerald-500" title="< 0.5 Extreme Bull" />
                        <div className="flex-1 bg-green-400"   title="0.5–0.7 Bullish" />
                        <div className="flex-1 bg-gray-400"    title="0.7–1.0 Neutral" />
                        <div className="flex-1 bg-orange-400"  title="1.0–1.4 Bearish" />
                        <div className="flex-1 bg-red-500"     title="> 1.4 Extreme Bear" />
                      </div>
                      <div
                        className="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-white border-2 border-gray-800 dark:border-white rounded-full shadow-sm"
                        style={{ left: `${Math.min(95, Math.max(5, ((sentiment.pcr.proxy_value - 0.3) / 1.5) * 100))}%` }}
                      />
                    </div>
                    <div className="flex justify-between text-[10px] text-gray-400 mb-3">
                      <span>0.3</span><span>0.7</span><span>1.0</span><span>1.4</span><span>1.8</span>
                    </div>

                    <div className={`rounded-lg p-3 text-xs border
                      ${sentiment.pcr.proxy_value < 0.7 ? "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800"
                      : sentiment.pcr.proxy_value < 1.0 ? "bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700"
                      : "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800"}`}>
                      <p className="font-semibold text-gray-800 dark:text-gray-200 mb-0.5">
                        {sentiment.pcr.interpretation.emoji} {sentiment.pcr.interpretation.level}
                      </p>
                      <p className="text-gray-600 dark:text-gray-400">{sentiment.pcr.interpretation.text}</p>
                    </div>
                  </>
                )}
                <p className="text-[10px] text-gray-400 mt-2 flex items-start gap-1">
                  <Info className="w-3 h-3 shrink-0 mt-0.5" /> {sentiment.pcr.note}
                </p>
              </div>
            </div>

            {/* News + Price Action */}
            <div className="space-y-4 lg:col-span-1">

              {/* News card */}
              <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-5">
                <h2 className="text-sm font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest mb-4">
                  News Sentiment
                </h2>
                {sentiment.news.available === false ? (
                  <div className="rounded-lg p-3 text-xs border bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400">
                    Insufficient article sample to score the news leg
                    ({sentiment.news.total_articles} articles, need ≥5).
                    Excluded from composite.
                  </div>
                ) : (
                <>
                <div className="flex items-center gap-3 mb-4">
                  <div className={`text-3xl font-black ${sentiment.news.mood === "bullish" ? "text-emerald-500" : sentiment.news.mood === "bearish" ? "text-red-500" : "text-gray-500"}`}>
                    {sentiment.news.mood === "bullish" ? "Bullish" : sentiment.news.mood === "bearish" ? "Bearish" : "Neutral"}
                  </div>
                  <div className="text-xs text-gray-400">{sentiment.news.total_articles} articles</div>
                </div>
                {/* Article ratio bar */}
                <div className="space-y-2 text-xs">
                  {(["bullish", "bearish", "neutral"] as const).map(type => {
                    const count = sentiment.news[type];
                    const total = sentiment.news.total_articles || 1;
                    const pct   = Math.round((count / total) * 100);
                    const color = type === "bullish" ? "bg-emerald-500" : type === "bearish" ? "bg-red-500" : "bg-gray-400";
                    return (
                      <div key={type}>
                        <div className="flex justify-between mb-0.5 capitalize">
                          <span className="text-gray-500 dark:text-gray-400">{type}</span>
                          <span className="text-gray-700 dark:text-gray-300">{count} ({pct}%)</span>
                        </div>
                        <div className="h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full">
                          <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
                </>
                )}
              </div>

              {/* Price Action card */}
              <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-5">
                <h2 className="text-sm font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest mb-4">
                  Nifty 50 Price Action
                </h2>
                {sentiment.price_action.available === false || sentiment.price_action.score == null ? (
                  <div className="rounded-lg p-3 text-xs border bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400">
                    Nifty price feed unavailable. Price-action leg excluded from the composite.
                  </div>
                ) : (
                  <>
                    <div className="grid grid-cols-3 gap-3">
                      {[
                        { label: "5d Momentum",  raw: sentiment.price_action.indicators.momentum5d,
                          fmt: (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)}%`,
                          positive: (v: number) => v >= 0 },
                        { label: "20d Momentum", raw: sentiment.price_action.indicators.momentum20d,
                          fmt: (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)}%`,
                          positive: (v: number) => v >= 0 },
                        { label: "RSI 14",       raw: sentiment.price_action.indicators.rsi14,
                          fmt: (v: number) => v.toFixed(0),
                          positive: (v: number) => v >= 50 },
                      ].map((kpi, i) => {
                        const has = kpi.raw != null;
                        return (
                          <div key={i} className="bg-gray-50 dark:bg-gray-800 rounded-xl p-3 text-center">
                            <p className="text-[10px] text-gray-400 mb-1">{kpi.label}</p>
                            <p className={`text-sm font-bold ${!has ? "text-gray-400" : kpi.positive(kpi.raw as number) ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
                              {has ? kpi.fmt(kpi.raw as number) : "—"}
                            </p>
                          </div>
                        );
                      })}
                    </div>
                    <p className={`text-center text-sm font-semibold mt-3 ${sentiment.price_action.score >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
                      {sentiment.price_action.label.replace("_", " ")}
                    </p>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* ── Sector heatmap ─────────────────────────────────────────────── */}
          {sectors.length > 0 && (
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-6">
              <h2 className="text-sm font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest mb-4 flex items-center gap-2">
                <BarChart2 className="w-4 h-4" /> Sector Sentiment Heatmap
              </h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
                {sectors.map((s, i) => {
                  // Render unavailable sectors as a distinct grey card so a
                  // failed fetch isn't shown as a synthetic "Neutral 0".
                  if (s.available === false || s.score == null) {
                    return (
                      <div key={i} className="bg-gray-100 dark:bg-gray-800 rounded-xl p-3 flex flex-col gap-1 opacity-70">
                        <p className="text-[10px] font-bold text-gray-500 dark:text-gray-400 leading-tight">{s.sector}</p>
                        <p className="text-lg font-black text-gray-400">—</p>
                        <p className="text-[10px] text-gray-400">Unavailable</p>
                      </div>
                    );
                  }
                  return (
                    <div key={i} className={`${sectorBg(s.score)} rounded-xl p-3 flex flex-col gap-1`}>
                      <p className={`text-[10px] font-bold ${sectorText(s.score)} leading-tight`}>
                        {s.sector}
                      </p>
                      <p className={`text-lg font-black ${sectorText(s.score)}`}>
                        {s.score > 0 ? "+" : ""}{s.score}
                      </p>
                      <p className={`text-[10px] ${sectorText(s.score)} opacity-80`}>
                        {s.label}
                      </p>
                      {s.rsi14 != null && (
                        <p className={`text-[9px] ${sectorText(s.score)} opacity-70`}>
                          RSI {s.rsi14.toFixed(0)}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
              {/* Legend — ranges are half-open at the upper edge to match
                  sectorBg() thresholds (≥40 emerald, ≥15 green-400, …). */}
              <div className="flex flex-wrap gap-3 mt-4 text-[10px] text-gray-500 dark:text-gray-400">
                {[
                  { color: "bg-emerald-500", label: "Extremely Bullish (≥40)" },
                  { color: "bg-green-400",   label: "Bullish (15–<40)" },
                  { color: "bg-gray-300 dark:bg-gray-600", label: "Neutral (-15–<15)" },
                  { color: "bg-orange-400",  label: "Bearish (-40–<-15)" },
                  { color: "bg-red-500",     label: "Extremely Bearish (≤-40)" },
                ].map((l, i) => (
                  <div key={i} className="flex items-center gap-1">
                    <div className={`w-2.5 h-2.5 rounded-sm ${l.color}`} />
                    {l.label}
                  </div>
                ))}
              </div>
            </div>
          )}

        </>
      )}
    </div>
  );
}
