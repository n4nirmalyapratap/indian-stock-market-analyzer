import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import {
  RefreshCw, AlertTriangle,
  BarChart2, Info, Gauge, Zap,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────
interface Component { name: string; score: number; weight: number; detail: string }
interface VixData    { current: number; change5d_pct: number; score: number;
                       interpretation: { level: string; emoji: string; color: string; text: string } }
interface PcrData    { proxy_value: number; score: number; note: string;
                       interpretation: { level: string; emoji: string; color: string; text: string } }
interface NewsData   { total_articles: number; bullish: number; bearish: number; neutral: number;
                       mood: string; score: number }
interface PriceAction{ score: number; compound: number; label: string;
                       indicators: { momentum5d?: number; momentum20d?: number; rsi14?: number } }
interface Signal     { type: string; title: string; description: string;
                       signal: string; direction: string; emoji: string; color: string }
interface Strategy   { strategy: string; outlook: string; vol: string; risk: string }
interface Sentiment  {
  composite: number; label: string; timestamp: string;
  components: Component[]; vix: VixData; pcr: PcrData;
  news: NewsData; price_action: PriceAction;
  contrarian_signals: Signal[]; strategy_recommendations: Strategy[];
}
interface SectorItem { sector: string; score: number; label: string; compound: number;
                       momentum5d?: number; rsi14?: number }
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

// ── Speedometer gauge ────────────────────────────────────────────────────────
function Speedometer({ score, label }: { score: number; label: string }) {
  const r = 90;
  const cx = 110;
  const cy = 110;
  const startAngle = 210;
  const totalDeg   = 120;

  function polarToXY(angleDeg: number, radius: number) {
    const rad = ((angleDeg - 90) * Math.PI) / 180;
    return { x: cx + radius * Math.cos(rad), y: cy + radius * Math.sin(rad) };
  }

  function arcPath(startDeg: number, endDeg: number, radius: number) {
    const s = polarToXY(startDeg, radius);
    const e = polarToXY(endDeg, radius);
    const large = endDeg - startDeg > 180 ? 1 : 0;
    return `M ${s.x} ${s.y} A ${radius} ${radius} 0 ${large} 1 ${e.x} ${e.y}`;
  }

  // Score is -100 to +100; map to 0–120 degrees from start
  const normalized = (score + 100) / 200;          // 0 → 1
  const needleDeg  = startAngle + normalized * totalDeg;
  const needle     = polarToXY(needleDeg, r - 10);
  const needleBase1 = polarToXY(needleDeg - 90, 8);
  const needleBase2 = polarToXY(needleDeg + 90, 8);

  const zones = [
    { start: startAngle,       end: startAngle + 24,  color: "#ef4444" },  // Extremely Bearish
    { start: startAngle + 24,  end: startAngle + 48,  color: "#f97316" },  // Bearish
    { start: startAngle + 48,  end: startAngle + 72,  color: "#9ca3af" },  // Neutral
    { start: startAngle + 72,  end: startAngle + 96,  color: "#22c55e" },  // Bullish
    { start: startAngle + 96,  end: startAngle + 120, color: "#10b981" },  // Extremely Bullish
  ];

  return (
    <div className="flex flex-col items-center">
      <svg width="220" height="140" viewBox="0 0 220 140">
        {/* Background arc */}
        <path d={arcPath(startAngle, startAngle + totalDeg, r)}
          fill="none" stroke="#e5e7eb" strokeWidth="18" strokeLinecap="round" />
        {/* Zone arcs */}
        {zones.map((z, i) => (
          <path key={i} d={arcPath(z.start, z.end, r)}
            fill="none" stroke={z.color} strokeWidth="18" strokeLinecap="butt" opacity="0.85" />
        ))}
        {/* Active needle indicator ring */}
        <path d={arcPath(startAngle, needleDeg, r - 1)}
          fill="none" stroke="white" strokeWidth="4" strokeLinecap="round" opacity="0.3" />
        {/* Needle */}
        <polygon
          points={`${needle.x},${needle.y} ${needleBase1.x},${needleBase1.y} ${needleBase2.x},${needleBase2.y}`}
          fill="#1f2937" className="dark:fill-white"
        />
        {/* Center dot */}
        <circle cx={cx} cy={cy} r="6" fill="#1f2937" className="dark:fill-white" />
        {/* Score text */}
        <text x={cx} y={cy + 30} textAnchor="middle" fontSize="24" fontWeight="bold"
          fill={score >= 25 ? "#10b981" : score <= -25 ? "#ef4444" : "#6b7280"}>
          {score > 0 ? `+${score}` : score}
        </text>
        {/* Zone labels */}
        <text x="15"  y="128" fontSize="8" fill="#ef4444" textAnchor="middle">Bearish</text>
        <text x="110" y="32"  fontSize="8" fill="#6b7280" textAnchor="middle">Neutral</text>
        <text x="200" y="128" fontSize="8" fill="#10b981" textAnchor="middle">Bullish</text>
      </svg>
      <p className={`text-lg font-bold mt-1 ${score >= 25 ? "text-emerald-600 dark:text-emerald-400" : score <= -25 ? "text-red-600 dark:text-red-400" : "text-gray-600 dark:text-gray-300"}`}>
        {label}
      </p>
    </div>
  );
}

// ── Component bar ─────────────────────────────────────────────────────────────
function ComponentBar({ comp }: { comp: Component }) {
  const pct = Math.abs(comp.score) / 100 * comp.weight;
  const positive = comp.score >= 0;
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-gray-600 dark:text-gray-400 font-medium">{comp.name}</span>
        <span className={comp.score >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-500"}>
          {comp.score > 0 ? "+" : ""}{comp.score}  <span className="text-gray-400">({comp.weight}% weight)</span>
        </span>
      </div>
      <div className="h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${positive ? "bg-emerald-500" : "bg-red-500"}`}
          style={{ width: `${Math.min(100, Math.abs(comp.score))}%`, opacity: 0.8 }}
        />
      </div>
      <p className="text-[10px] text-gray-400 mt-0.5 truncate">{comp.detail}</p>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function SentimentDashboard() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  const { data: sentiment, isLoading, error, refetch: refetchSentiment } = useQuery<Sentiment>({
    queryKey: ["sentiment-market", refreshKey],
    queryFn:  () => fetchApi<Sentiment>("/sentiment/market"),
    staleTime: 900_000,
    retry: 1,
  });

  const { data: sectorsData, refetch: refetchSectors } = useQuery<SectorsResp>({
    queryKey: ["sentiment-sectors", refreshKey],
    queryFn:  () => fetchApi<SectorsResp>("/sentiment/sectors"),
    staleTime: 900_000,
    retry: 1,
  });

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await fetchApi("/sentiment/refresh");
      setRefreshKey(k => k + 1);
    } finally {
      setRefreshing(false);
    }
  }, []);

  const score    = sentiment?.composite ?? 0;
  const sectors  = sectorsData?.sectors ?? [];

  // ── Format timestamp ────────────────────────────────────────────────────────
  const updatedAt = sentiment?.timestamp
    ? new Date(sentiment.timestamp).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })
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
        <button
          onClick={handleRefresh}
          disabled={refreshing || isLoading}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-semibold px-4 py-2 rounded-lg transition"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
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
              <Speedometer score={score} label={sentiment.label} />

              {/* Weight breakdown */}
              <div className="w-full space-y-3 pt-2 border-t border-gray-100 dark:border-gray-800">
                {sentiment.components.map((c, i) => (
                  <ComponentBar key={i} comp={c} />
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
                <div className="flex items-end gap-3 mb-3">
                  <span className="text-4xl font-black text-gray-900 dark:text-white">
                    {sentiment.vix.current.toFixed(1)}
                  </span>
                  <span className={`text-sm font-medium mb-1 ${sentiment.vix.change5d_pct >= 0 ? "text-red-500" : "text-emerald-500"}`}>
                    {sentiment.vix.change5d_pct > 0 ? "▲" : "▼"} {Math.abs(sentiment.vix.change5d_pct).toFixed(1)}% (5d)
                  </span>
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
              </div>

              {/* PCR card */}
              <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-5">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest">
                    PCR Proxy
                  </h2>
                  <span className="text-xs text-gray-400">Put/Call Ratio Est.</span>
                </div>
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
              </div>

              {/* Price Action card */}
              <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-5">
                <h2 className="text-sm font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest mb-4">
                  Nifty 50 Price Action
                </h2>
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { label: "5d Momentum", value: `${(sentiment.price_action.indicators.momentum5d ?? 0) > 0 ? "+" : ""}${(sentiment.price_action.indicators.momentum5d ?? 0).toFixed(1)}%`,
                      positive: (sentiment.price_action.indicators.momentum5d ?? 0) >= 0 },
                    { label: "20d Momentum", value: `${(sentiment.price_action.indicators.momentum20d ?? 0) > 0 ? "+" : ""}${(sentiment.price_action.indicators.momentum20d ?? 0).toFixed(1)}%`,
                      positive: (sentiment.price_action.indicators.momentum20d ?? 0) >= 0 },
                    { label: "RSI 14", value: `${(sentiment.price_action.indicators.rsi14 ?? 50).toFixed(0)}`,
                      positive: (sentiment.price_action.indicators.rsi14 ?? 50) >= 50 },
                  ].map((kpi, i) => (
                    <div key={i} className="bg-gray-50 dark:bg-gray-800 rounded-xl p-3 text-center">
                      <p className="text-[10px] text-gray-400 mb-1">{kpi.label}</p>
                      <p className={`text-sm font-bold ${kpi.positive ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
                        {kpi.value}
                      </p>
                    </div>
                  ))}
                </div>
                <p className={`text-center text-sm font-semibold mt-3 ${sentiment.price_action.score >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
                  {sentiment.price_action.label.replace("_", " ")}
                </p>
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
                {sectors.map((s, i) => (
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
                    {s.rsi14 && (
                      <p className={`text-[9px] ${sectorText(s.score)} opacity-70`}>
                        RSI {s.rsi14.toFixed(0)}
                      </p>
                    )}
                  </div>
                ))}
              </div>
              {/* Legend */}
              <div className="flex flex-wrap gap-3 mt-4 text-[10px] text-gray-500 dark:text-gray-400">
                {[
                  { color: "bg-emerald-500", label: "Extremely Bullish (≥40)" },
                  { color: "bg-green-400",   label: "Bullish (15–40)" },
                  { color: "bg-gray-300 dark:bg-gray-600", label: "Neutral (-15–15)" },
                  { color: "bg-orange-400",  label: "Bearish (-40–-15)" },
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

          {/* ── Strategy recommendations ────────────────────────────────────── */}
          <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-6">
            <h2 className="text-sm font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest mb-1 flex items-center gap-2">
              <Zap className="w-4 h-4 text-amber-500" /> Suggested Option Strategies
            </h2>
            <p className="text-xs text-gray-400 dark:text-gray-500 mb-4">
              Based on current sentiment ({sentiment.label}) and India VIX ({sentiment.vix.current.toFixed(1)})
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {sentiment.strategy_recommendations.map((s, i) => (
                <div key={i} className="bg-gray-50 dark:bg-gray-800 rounded-xl p-4 border border-gray-100 dark:border-gray-700">
                  <p className="font-bold text-sm text-gray-900 dark:text-white mb-2">{s.strategy}</p>
                  <div className="space-y-1 text-xs text-gray-600 dark:text-gray-400">
                    <div className="flex items-center gap-1">
                      <span className="text-gray-400">Outlook:</span>
                      <span className={`font-medium ${s.outlook.toLowerCase().includes("bullish") ? "text-emerald-600 dark:text-emerald-400" : s.outlook.toLowerCase().includes("bearish") ? "text-red-600 dark:text-red-400" : "text-gray-600 dark:text-gray-300"}`}>
                        {s.outlook}
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      <span className="text-gray-400">Volatility:</span>
                      <span className="font-medium text-gray-700 dark:text-gray-300">{s.vol}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <span className="text-gray-400">Max Loss:</span>
                      <span className={`font-medium ${s.risk === "Limited" ? "text-green-600 dark:text-green-400" : "text-orange-600 dark:text-orange-400"}`}>
                        {s.risk}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-400 mt-3 flex items-center gap-1">
              <Info className="w-3 h-3" /> Use the Options Strategy Tester for full analysis with Greeks and payoff diagrams.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
