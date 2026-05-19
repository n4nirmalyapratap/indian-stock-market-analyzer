import { useState, useCallback, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import {
  RefreshCw, AlertTriangle,
  BarChart2, Info, Gauge,
} from "lucide-react";
import DataFreshness from "@/components/DataFreshness";
import { pickMeta, marketDataQueryOptions } from "@/lib/marketData";

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

// ── Speedometer gauge ────────────────────────────────────────────────────────
function Speedometer({ score, label }: { score: number | null; label: string }) {
  const [fired, setFired] = useState(false);
  const [countedScore, setCountedScore] = useState(0);
  const rafRef = useRef<number>(0);

  const cx = 160, cy = 148, r = 112;
  // Map score (-100..+100) to CSS rotation angle (-90..+90 deg, 0=up)
  const targetAngle = score != null ? score * 0.9 : -90;

  const zoneColor = score == null ? "#475569"
    : score >= 50  ? "#10b981"
    : score >= 20  ? "#22c55e"
    : score > -20  ? "#64748b"
    : score > -50  ? "#f97316"
    : "#ef4444";

  useEffect(() => {
    const t = setTimeout(() => setFired(true), 120);
    if (score == null) return () => clearTimeout(t);
    const start = performance.now();
    const dur = 1100;
    const to = score;
    const tick = () => {
      const elapsed = performance.now() - start;
      const p = Math.min(elapsed / dur, 1);
      const ease = 1 - Math.pow(1 - p, 3);
      setCountedScore(Math.round(to * ease));
      if (p < 1) rafRef.current = requestAnimationFrame(tick);
    };
    const t2 = setTimeout(() => { rafRef.current = requestAnimationFrame(tick); }, 120);
    return () => { clearTimeout(t); clearTimeout(t2); cancelAnimationFrame(rafRef.current); };
  }, [score]);

  // Arc helpers — angle 0° = top (12-o'clock), +90° = right, -90° = left
  function ap(deg: number, radius = r) {
    const rad = (deg * Math.PI) / 180;
    return { x: cx + radius * Math.sin(rad), y: cy - radius * Math.cos(rad) };
  }
  function arcD(from: number, to: number, radius = r) {
    const p1 = ap(from, radius), p2 = ap(to, radius);
    const large = Math.abs(to - from) > 180 ? 1 : 0;
    return `M ${p1.x.toFixed(2)} ${p1.y.toFixed(2)} A ${radius} ${radius} 0 ${large} 0 ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`;
  }

  // Full semicircle perimeter (for dasharray trick on the glow arc)
  const arcLen = Math.PI * r; // ≈351 px
  const normalized = score != null ? (score + 100) / 200 : 0;

  const zones = [
    { from: -90, to: -54, color: "#ef4444" },
    { from: -54, to: -18, color: "#f97316" },
    { from: -18, to:  18, color: "#64748b" },
    { from:  18, to:  54, color: "#22c55e" },
    { from:  54, to:  90, color: "#10b981" },
  ];

  if (score == null) {
    return (
      <div className="flex flex-col items-center">
        <svg width="320" height="185" viewBox="0 0 320 185">
          <path d={arcD(-90, 90)} fill="none" stroke="#0f1c35" strokeWidth="16" strokeLinecap="round" />
          <text x={cx} y={cy + 14} textAnchor="middle" fontSize="30" fontWeight="900" fill="#334155">—</text>
          <text x={cx} y={cy + 34} textAnchor="middle" fontSize="10" fill="#334155" letterSpacing="2">UNAVAILABLE</text>
        </svg>
      </div>
    );
  }

  const leftPt  = ap(-90, r + 14);
  const topPt   = ap(0,   r + 16);
  const rightPt = ap(90,  r + 14);

  return (
    <div className="flex flex-col items-center w-full">
      <style>{`
        @keyframes gaugePulse {
          0%,100% { opacity: 0.6; }
          50%      { opacity: 1; }
        }
        @keyframes hubSpin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
      `}</style>

      <svg width="320" height="210" viewBox="0 0 320 210" style={{ overflow: "visible" }}>
        <defs>
          <filter id="glow-tip" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <filter id="glow-hub" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* ── Track background ─────────────────────────────── */}
        <path d={arcD(-90, 90)} fill="none" stroke="#0a1520" strokeWidth="20" strokeLinecap="round" />
        <path d={arcD(-90, 90)} fill="none" stroke="#162244" strokeWidth="16" strokeLinecap="round" />

        {/* ── Zone segments ────────────────────────────────── */}
        {zones.map((z, i) => {
          const inZone = score != null && targetAngle >= z.from && targetAngle <= z.to;
          return (
            <path
              key={i}
              d={arcD(z.from, z.to)}
              fill="none"
              stroke={z.color}
              strokeWidth="12"
              strokeLinecap="butt"
              style={{
                opacity: inZone ? 1 : 0.3,
                transition: "opacity 0.6s ease",
                filter: inZone ? `drop-shadow(0 0 6px ${z.color})` : "none",
              }}
            />
          );
        })}

        {/* ── Animated glow arc (stroke-dashoffset trick) ──── */}
        <path
          d={arcD(-90, 90)}
          fill="none"
          stroke={zoneColor}
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray={`${arcLen} ${arcLen}`}
          strokeDashoffset={fired ? arcLen * (1 - normalized) : arcLen}
          opacity={0.45}
          style={{ transition: "stroke-dashoffset 1.2s cubic-bezier(0.34,1.56,0.64,1)" }}
        />

        {/* ── Needle ───────────────────────────────────────── */}
        <g
          style={{
            transform: `rotate(${fired ? targetAngle : -90}deg)`,
            transformOrigin: `${cx}px ${cy}px`,
            transition: "transform 1.2s cubic-bezier(0.34,1.56,0.64,1)",
          }}
        >
          {/* Needle shaft */}
          <line
            x1={cx} y1={cy + 14}
            x2={cx} y2={cy - r + 24}
            stroke={zoneColor}
            strokeWidth="2"
            strokeLinecap="round"
            opacity={0.9}
          />
          {/* Glow at tip */}
          <circle cx={cx} cy={cy - r + 24} r={7} fill={zoneColor} opacity={0.25} filter="url(#glow-tip)" />
          {/* Bright tip dot */}
          <circle cx={cx} cy={cy - r + 24} r={3} fill="white" />
        </g>

        {/* ── Hub ──────────────────────────────────────────── */}
        <circle cx={cx} cy={cy} r={13} fill={zoneColor} opacity={0.15} filter="url(#glow-hub)" />
        <circle cx={cx} cy={cy} r={10} fill="#060e1c" stroke={zoneColor} strokeWidth="2" />
        <circle cx={cx} cy={cy} r={4}  fill={zoneColor} />

        {/* ── Score number ─────────────────────────────────── */}
        <text
          x={cx} y={cy + 44}
          textAnchor="middle"
          fontSize="36"
          fontWeight="900"
          fill={zoneColor}
          style={{ fontFamily: "system-ui, sans-serif", letterSpacing: "-1px" }}
        >
          {countedScore > 0 ? `+${countedScore}` : countedScore}
        </text>

        {/* ── Axis labels ──────────────────────────────────── */}
        <text x={leftPt.x - 2} y={leftPt.y + 4} textAnchor="end"    fontSize="8.5" fill="#ef4444" fontWeight="700" letterSpacing="1">BEAR</text>
        <text x={topPt.x}      y={topPt.y - 2}   textAnchor="middle" fontSize="8.5" fill="#64748b" fontWeight="700" letterSpacing="1">NEUTRAL</text>
        <text x={rightPt.x + 2} y={rightPt.y + 4} textAnchor="start" fontSize="8.5" fill="#10b981" fontWeight="700" letterSpacing="1">BULL</text>

        {/* ── Zone legend dots ─────────────────────────────── */}
        {[
          { color: "#ef4444", label: "Ex. Bearish", x: 14 },
          { color: "#f97316", label: "Bearish",     x: 72 },
          { color: "#64748b", label: "Neutral",     x: 130 },
          { color: "#22c55e", label: "Bullish",     x: 188 },
          { color: "#10b981", label: "Ex. Bullish", x: 246 },
        ].map((d, i) => (
          <g key={i}>
            <circle cx={d.x + 4} cy={196} r={3} fill={d.color} />
            <text x={d.x + 11} y={200} fontSize="7.5" fill="#334155" fontWeight="600">{d.label}</text>
          </g>
        ))}
      </svg>

      {/* Label */}
      <p
        className="text-base font-black tracking-tight -mt-1"
        style={{ color: zoneColor, letterSpacing: "-0.5px" }}
      >
        {label}
      </p>
    </div>
  );
}

// ── Component bar ─────────────────────────────────────────────────────────────
function ComponentBar({ comp, index = 0 }: { comp: Component; index?: number }) {
  const [barWidth, setBarWidth] = useState(0);
  const isUnavailable = comp.score == null || comp.available === false;
  const isInformational = comp.weight === 0;
  const weightLabel = isInformational ? "info" : `${comp.weight}%`;

  useEffect(() => {
    if (comp.score == null) return;
    const t = setTimeout(
      () => setBarWidth(Math.min(100, Math.abs(comp.score as number))),
      120 + index * 80,
    );
    return () => clearTimeout(t);
  }, [comp.score, index]);

  if (isUnavailable) {
    return (
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium" style={{ color: "#475569" }}>{comp.name}</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-md" style={{ background: "#0f1c35", color: "#334155" }}>—</span>
        </div>
        <div className="h-2 rounded-full overflow-hidden" style={{ background: "#0a1520" }}>
          <div className="h-full rounded-full" style={{ width: "100%", background: "#162244" }} />
        </div>
        <p className="text-[10px] italic truncate" style={{ color: "#1e3a5f" }}>{comp.detail || "Unavailable"}</p>
      </div>
    );
  }

  const score = comp.score as number;
  const positive = score >= 0;
  const fillGradient = positive
    ? "linear-gradient(90deg, #15803d, #4ade80)"
    : "linear-gradient(90deg, #b91c1c, #f87171)";
  const glowColor = positive ? "rgba(74,222,128,0.35)" : "rgba(248,113,113,0.35)";
  const textColor = positive ? "#4ade80" : "#f87171";

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium truncate" style={{ color: "#94a3b8" }}>{comp.name}</span>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="text-xs font-bold" style={{ color: textColor }}>
            {score > 0 ? "+" : ""}{score}
          </span>
          <span
            className="text-[9px] font-semibold px-1.5 py-0.5 rounded-md"
            style={{ background: "rgba(99,102,241,0.1)", color: "#6366f1", border: "1px solid rgba(99,102,241,0.15)" }}
          >
            {weightLabel}
          </span>
        </div>
      </div>

      {/* Bar track */}
      <div className="h-2.5 rounded-full overflow-hidden relative" style={{ background: "#0a1520" }}>
        <div
          className="h-full rounded-full"
          style={{
            width: `${barWidth}%`,
            background: fillGradient,
            boxShadow: `0 0 10px ${glowColor}`,
            transition: "width 0.9s cubic-bezier(0.34,1.56,0.64,1)",
          }}
        />
      </div>

      <p className="text-[10px] truncate" style={{ color: "#1e3a5f" }}>{comp.detail}</p>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function SentimentDashboard() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  const { data: sentiment, isLoading, error, refetch: refetchSentiment } = useQuery<Sentiment>(
    marketDataQueryOptions<Sentiment, { retry: number }>(
      ["sentiment-market", refreshKey],
      () => fetchApi<Sentiment>("/sentiment/market"),
      { retry: 1 },
    ),
  );

  const { data: sectorsData, refetch: refetchSectors } = useQuery<SectorsResp>(
    marketDataQueryOptions<SectorsResp, { retry: number }>(
      ["sentiment-sectors", refreshKey],
      () => fetchApi<SectorsResp>("/sentiment/sectors"),
      { retry: 1 },
    ),
  );

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await fetchApi("/sentiment/refresh");
      setRefreshKey(k => k + 1);
    } finally {
      setRefreshing(false);
    }
  }, []);

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
              <Speedometer score={score} label={sentiment.label} />

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
