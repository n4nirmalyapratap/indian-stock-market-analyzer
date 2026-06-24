import { useMemo, useState, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "wouter";
import { api, fetchApi } from "@/lib/api";
import { marketDataQueryOptions } from "@/lib/marketData";
import { useTheme } from "@/context/ThemeContext";
import {
  RefreshCw, Activity, Loader2, Newspaper, Rocket,
  TrendingUp, TrendingDown, ArrowRight, ShieldAlert,
  BarChart2, Zap,
} from "lucide-react";
import GlobalIndicesPanel from "@/components/GlobalIndicesPanel";
import TopMoversPanel from "@/components/TopMoversPanel";

// ── Skeleton ──────────────────────────────────────────────────────────────────
function Skel({ h = "h-4", w = "w-full", r = "rounded" }: { h?: string; w?: string; r?: string }) {
  return <div className={`${h} ${w} ${r} bg-gray-100 dark:bg-gray-700 animate-pulse`} />;
}

// ── Formatters ────────────────────────────────────────────────────────────────
function fmtCr(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return "—";
  const sign = v >= 0 ? "+" : "−";
  const abs  = Math.abs(v);
  if (abs >= 10_000) return `${sign}₹${(abs / 10_000).toFixed(1)}K Cr`;
  if (abs >= 100)    return `${sign}₹${(abs / 100).toFixed(1)}K`;
  return `${sign}₹${abs.toFixed(0)}`;
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

// ── Score helpers ─────────────────────────────────────────────────────────────
function dot(score: number, hi = 65, lo = 40): string {
  return score >= hi ? "bg-emerald-500"
       : score >= lo ? "bg-amber-500"
       : "bg-red-500";
}
function dotLabel(score: number, hi = 65, lo = 40): string {
  return score >= hi ? "text-emerald-600 dark:text-emerald-400"
       : score >= lo ? "text-amber-600 dark:text-amber-400"
       : "text-red-600 dark:text-red-400";
}

// ── NavCard ────────────────────────────────────────────────────────────────────
// Each top-row card: title + coloured dot + big value + subtitle + detail.
// Wraps in a <Link> when href provided.
interface NavCardProps {
  title:   string;
  dotCls?: string;
  value:   string;
  valueCls?: string;
  sub?:    React.ReactNode;
  detail?: React.ReactNode;
  loading?: boolean;
  href?:   string;
  icon?:   React.ReactNode;
}
function NavCard({ title, dotCls, value, valueCls, sub, detail, loading, href, icon }: NavCardProps) {
  const inner = (
    <div className="h-full bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 shadow-sm p-4 flex flex-col gap-1.5 group hover:border-indigo-200 dark:hover:border-indigo-700 transition-all cursor-pointer">
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-widest">{title}</p>
        <span className="text-gray-300 dark:text-gray-600">{icon}</span>
      </div>
      {loading ? (
        <>
          <Skel h="h-7" w="w-24" r="rounded-md" />
          <Skel h="h-3" w="w-14" />
        </>
      ) : (
        <>
          <div className="flex items-center gap-2">
            {dotCls && <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${dotCls}`} />}
            <span className={`text-xl font-black leading-tight ${valueCls ?? "text-gray-900 dark:text-white"}`}>
              {value}
            </span>
          </div>
          {sub    && <div className="text-xs text-gray-500 dark:text-gray-400 leading-snug">{sub}</div>}
          {detail && <div className="text-[11px] text-gray-400 dark:text-gray-500 mt-auto leading-snug">{detail}</div>}
        </>
      )}
      {href && !loading && (
        <div className="flex items-center gap-0.5 text-[10px] text-indigo-400 dark:text-indigo-500 mt-auto opacity-0 group-hover:opacity-100 transition-opacity">
          View details <ArrowRight className="w-2.5 h-2.5" />
        </div>
      )}
    </div>
  );
  if (!href) return inner;
  return <Link href={href} className="block h-full rounded-xl">{inner}</Link>;
}

// ── Mini Sentiment Gauge ──────────────────────────────────────────────────────
// Compact SVG speedometer (200×136) for the dashboard sentiment card.
function MiniGauge({ score }: { score: number | null }) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const [fired, setFired] = useState(false);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    setFired(false);
    const t = setTimeout(() => setFired(true), 150);
    return () => { clearTimeout(t); cancelAnimationFrame(rafRef.current); };
  }, [score]);

  const cx = 100, cy = 90, r = 72;
  const targetAngle = score != null ? score * 0.9 : -90;
  const zoneColor = score == null
    ? (isDark ? "#475569" : "#94a3b8")
    : score >= 50  ? "#10b981"
    : score >= 20  ? "#22c55e"
    : score > -20  ? (isDark ? "#64748b" : "#94a3b8")
    : score > -50  ? "#f97316"
    : "#ef4444";

  const arcLen = Math.PI * r;
  const normalized = score != null ? (score + 100) / 200 : 0;
  const trackColor = isDark ? "#1e293b" : "#e2e8f0";
  const hubFill    = isDark ? "#0f172a" : "#ffffff";
  const neutralZone = isDark ? "#475569" : "#94a3b8";

  function ap(deg: number, radius = r) {
    const rad = (deg * Math.PI) / 180;
    return { x: cx + radius * Math.sin(rad), y: cy - radius * Math.cos(rad) };
  }
  function arcD(from: number, to: number, radius = r) {
    const { x: x1, y: y1 } = ap(from, radius);
    const { x: x2, y: y2 } = ap(to, radius);
    const large = Math.abs(to - from) > 180 ? 1 : 0;
    return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${radius} ${radius} 0 ${large} 0 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
  }

  const zones = [
    { from: -90, to: -54, color: "#ef4444" },
    { from: -54, to: -18, color: "#f97316" },
    { from: -18, to:  18, color: neutralZone },
    { from:  18, to:  54, color: "#22c55e" },
    { from:  54, to:  90, color: "#10b981" },
  ];

  return (
    <svg width="200" height="136" viewBox="0 0 200 136" className="mx-auto">
      <path d={arcD(-90, 90)} fill="none" stroke={trackColor} strokeWidth="10" strokeLinecap="round" />
      {zones.map((z, i) => {
        const active = fired && targetAngle >= z.from && targetAngle <= z.to;
        return (
          <path key={i} d={arcD(z.from, z.to)} fill="none" stroke={z.color}
            strokeWidth="7" strokeLinecap="butt"
            style={{ opacity: active ? 1 : 0.22, transition: "opacity 0.5s ease",
                     filter: active ? `drop-shadow(0 0 3px ${z.color})` : "none" }}
          />
        );
      })}
      <path d={arcD(-90, 90)} fill="none" stroke={zoneColor} strokeWidth="1.5"
        strokeLinecap="butt"
        strokeDasharray={`${arcLen} ${arcLen}`}
        strokeDashoffset={fired ? arcLen * (1 - normalized) : arcLen}
        opacity={0.5}
        style={{ transition: "stroke-dashoffset 1.1s cubic-bezier(0.34,1.56,0.64,1)" }}
      />
      <g style={{
        transform: `rotate(${fired ? targetAngle : -90}deg)`,
        transformOrigin: `${cx}px ${cy}px`,
        transition: "transform 1.1s cubic-bezier(0.34,1.56,0.64,1)",
      }}>
        <line x1={cx} y1={cy + 8} x2={cx} y2={cy - r + 13}
          stroke={zoneColor} strokeWidth="1.5" strokeLinecap="round" />
        <circle cx={cx} cy={cy - r + 13} r={3} fill={zoneColor} opacity={0.35} />
        <circle cx={cx} cy={cy - r + 13} r={1.5} fill={isDark ? "#fff" : "#1e293b"} />
      </g>
      <circle cx={cx} cy={cy} r={8} fill={hubFill} stroke={zoneColor} strokeWidth="1.5" />
      <circle cx={cx} cy={cy} r={3.5} fill={zoneColor} />
      {score != null
        ? <text x={cx} y={cy + 30} textAnchor="middle" fontSize="22" fontWeight="900" fill={zoneColor}>
            {score > 0 ? `+${score}` : score}
          </text>
        : <text x={cx} y={cy + 22} textAnchor="middle" fontSize="14" fill={isDark ? "#334155" : "#cbd5e1"} fontWeight="700">—</text>
      }
      <text x="6"   y="130" fontSize="8" fill="#ef4444" fontWeight="700">BEAR</text>
      <text x={cx}  y="10"  textAnchor="middle" fontSize="8" fill={neutralZone} fontWeight="700">NEUTRAL</text>
      <text x="194" y="130" textAnchor="end" fontSize="8" fill="#10b981" fontWeight="700">BULL</text>
    </svg>
  );
}

// ── Sentiment Card (dashboard compact version) ────────────────────────────────
function SentimentCard({ sentiment, loading }: { sentiment: any; loading: boolean }) {
  const composite: number | null = sentiment?.composite ?? null;
  const label: string = sentiment?.label ?? "—";
  const vixVal: number | null = sentiment?.vix?.current ?? null;
  const newsMood: string | null = sentiment?.news?.mood ?? null;
  const components: any[] = sentiment?.components ?? [];

  const labelColor = composite == null ? "text-gray-400"
    : composite >= 50  ? "text-emerald-600 dark:text-emerald-400"
    : composite >= 20  ? "text-green-600 dark:text-green-400"
    : composite > -20  ? "text-gray-600 dark:text-gray-400"
    : composite > -50  ? "text-orange-600 dark:text-orange-400"
    : "text-red-600 dark:text-red-400";

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 shadow-sm p-5 flex flex-col">
      <div className="flex items-center justify-between mb-1">
        <p className="text-[10px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-widest">
          Market Sentiment
        </p>
        <Link href="/sentiment"
          className="text-[10px] text-indigo-400 hover:text-indigo-600 dark:hover:text-indigo-300 flex items-center gap-0.5 transition">
          Full Analysis <ArrowRight className="w-2.5 h-2.5" />
        </Link>
      </div>

      {loading ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 py-4">
          <div className="w-[200px] h-[136px] bg-gray-100 dark:bg-gray-700 animate-pulse rounded-xl" />
          <Skel h="h-4" w="w-24" r="rounded" />
        </div>
      ) : (
        <>
          <MiniGauge score={composite} />
          <p className={`text-sm font-bold text-center mb-3 ${labelColor}`}>{label}</p>

          {/* Component bars */}
          <div className="space-y-2">
            {components.filter(c => c.weight > 0).map((c, i) => {
              const sc = c.score ?? 0;
              const barW = `${Math.min(100, Math.max(0, (sc + 100) / 2))}%`;
              const barCls = sc >= 20 ? "bg-emerald-500" : sc > -20 ? "bg-gray-400 dark:bg-gray-500" : "bg-red-500";
              return (
                <div key={i}>
                  <div className="flex justify-between items-center text-[10px] text-gray-500 dark:text-gray-400 mb-0.5">
                    <span>{c.name}</span>
                    <span className="font-semibold">{c.weight}%</span>
                  </div>
                  <div className="h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full transition-all duration-700 ${barCls}`}
                      style={{ width: barW }} />
                  </div>
                </div>
              );
            })}
          </div>

          {/* VIX + News pill row */}
          <div className="flex gap-2 mt-3 flex-wrap">
            {vixVal != null && (
              <span className={`inline-flex items-center gap-1 text-[10px] rounded-full px-2 py-0.5 border font-medium
                ${vixVal < 15  ? "bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-700 text-emerald-700 dark:text-emerald-400"
                : vixVal < 22  ? "bg-amber-50   dark:bg-amber-900/20   border-amber-200   dark:border-amber-700   text-amber-700   dark:text-amber-400"
                :                "bg-red-50     dark:bg-red-900/20     border-red-200     dark:border-red-700     text-red-700     dark:text-red-400"}`}>
                VIX {vixVal.toFixed(1)}
              </span>
            )}
            {newsMood && (
              <span className={`inline-flex items-center text-[10px] rounded-full px-2 py-0.5 border font-medium
                ${newsMood === "bullish" ? "bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-700 text-emerald-700 dark:text-emerald-400"
                : newsMood === "bearish" ? "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-700 text-red-700 dark:text-red-400"
                :                         "bg-gray-50 dark:bg-gray-700 border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300"}`}>
                News: {newsMood.charAt(0).toUpperCase() + newsMood.slice(1)}
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ── Macro Environment Card ─────────────────────────────────────────────────────
function MacroEnvironmentCard({ macroData, loading }: { macroData: any; loading: boolean }) {
  const tiles: any[] = macroData?.tiles ?? [];

  const findTile = (...ids: string[]) =>
    tiles.find(t => ids.some(id => (t.id ?? "").toLowerCase() === id));

  const cpiTile    = findTile("cpi");
  const gdpTile    = findTile("gdp");
  const repoTile   = findTile("repo");
  const usdinrTile = findTile("usdinr", "usd_inr", "usd-inr");
  const ind10yTile = findTile("india_10y", "ind10y", "10y", "bond_10y", "gsec10y");
  const brentTile  = findTile("brent", "crude", "oil");

  // Derive macro environment label
  let envTag = "Neutral";
  let envDotCls = "bg-gray-400";
  let envTextCls = "text-gray-600 dark:text-gray-400";

  if (tiles.length > 0) {
    const cpiVal   = cpiTile?.value   ?? null;
    const cpiDelta = cpiTile?.delta   ?? null;
    const gdpVal   = gdpTile?.value   ?? null;

    if (cpiDelta != null && cpiDelta > 0.2 && (cpiVal ?? 0) > 5) {
      if (gdpVal != null && gdpVal >= 6.5) {
        envTag = "Inflationary Growth";
        envDotCls = "bg-amber-500";
        envTextCls = "text-amber-600 dark:text-amber-400";
      } else {
        envTag = "Inflationary";
        envDotCls = "bg-red-400";
        envTextCls = "text-red-500 dark:text-red-400";
      }
    } else if ((cpiDelta ?? 0) <= 0 && (gdpVal ?? 0) >= 6.5) {
      envTag = "Stable Growth";
      envDotCls = "bg-emerald-500";
      envTextCls = "text-emerald-600 dark:text-emerald-400";
    } else if ((gdpVal ?? 99) < 5.5 && gdpVal != null) {
      envTag = "Growth Slowdown";
      envDotCls = "bg-orange-400";
      envTextCls = "text-orange-600 dark:text-orange-400";
    } else if (cpiDelta != null && cpiDelta < -0.2) {
      envTag = "Disinflationary";
      envDotCls = "bg-blue-400";
      envTextCls = "text-blue-600 dark:text-blue-400";
    }
  }

  const pillTiles = [repoTile, cpiTile, usdinrTile, ind10yTile, brentTile].filter(Boolean);

  function fmtTileVal(t: any): string {
    if (t?.value == null) return "—";
    const v = t.value as number;
    const u = (t.unit ?? "").toLowerCase();
    if (u.includes("inr") || u === "₹") return `₹${v.toFixed(1)}`;
    if (u === "$" || t.id === "brent" || t.id === "crude") return `$${Math.round(v)}`;
    if (u === "%" || u.includes("pct") || u.includes("percent")) return `${v.toFixed(2)}%`;
    return v.toFixed(2);
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 shadow-sm p-5 flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[10px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-widest">
          Macro Environment
        </p>
        <Link href="/insights/macro"
          className="text-[10px] text-indigo-400 hover:text-indigo-600 dark:hover:text-indigo-300 flex items-center gap-0.5 transition">
          Macro Pulse <ArrowRight className="w-2.5 h-2.5" />
        </Link>
      </div>

      {loading ? (
        <div className="space-y-3">
          <Skel h="h-5" w="w-36" r="rounded" />
          <div className="flex gap-2 flex-wrap">
            {[1,2,3,4,5].map(i => <Skel key={i} h="h-7" w="w-20" r="rounded-full" />)}
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2 mb-4">
            <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${envDotCls}`} />
            <span className={`text-base font-bold ${envTextCls}`}>{envTag}</span>
          </div>

          {pillTiles.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {pillTiles.map((t: any) => (
                <div key={t.id}
                  className="inline-flex items-center gap-1.5 bg-gray-50 dark:bg-gray-700/60 border border-gray-100 dark:border-gray-600 rounded-full px-3 py-1 text-xs">
                  <span className="text-gray-500 dark:text-gray-400">{t.label}</span>
                  <span className="font-bold text-gray-900 dark:text-white">{fmtTileVal(t)}</span>
                  {t.delta != null && (
                    <span className={t.id === "cpi" || t.id === "brent" || t.id === "usdinr"
                      ? (t.delta > 0 ? "text-red-400" : "text-emerald-400")
                      : (t.delta > 0 ? "text-emerald-400" : "text-red-400")}>
                      {t.delta > 0 ? "↑" : "↓"}
                    </span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400 dark:text-gray-500 flex-1 flex items-center">
              Macro data unavailable
            </p>
          )}

          <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-3">
            GDP, CPI, IIP, WPI, Repo — updated monthly from official sources
          </p>
        </>
      )}
    </div>
  );
}

// ── News feed ─────────────────────────────────────────────────────────────────
function NewsPanel({ loading, items }: { loading: boolean; items: any[] }) {
  if (loading) {
    return (
      <div className="space-y-3">
        {[1,2,3,4,5].map(i => (
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
          <a key={i} href={item.url} target="_blank" rel="noopener noreferrer"
            className="flex items-start gap-2.5 p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 group transition">
            <span className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${dot}`} />
            <div className="min-w-0">
              <p className="text-sm text-gray-800 dark:text-gray-200 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 line-clamp-2 leading-snug">
                {item.title}
              </p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{item.source}</p>
            </div>
          </a>
        );
      })}
    </div>
  );
}

// ── Sector emoji helper ───────────────────────────────────────────────────────
const SECTOR_EMOJI: Record<string, string> = {
  "Financial Services": "🏦", "Bank": "🏦", "Banking": "🏦",
  "IT": "💻", "Technology": "💻", "Information Technology": "💻",
  "Healthcare": "💊", "Pharma": "💊", "Pharmaceutical": "💊",
  "Energy": "⚡", "Oil": "🛢️", "Gas": "🛢️",
  "Auto": "🚗", "Automobile": "🚗",
  "FMCG": "🛒", "Consumer": "🛒",
  "Metal": "⚙️", "Metals": "⚙️",
  "Realty": "🏗️", "Real Estate": "🏗️", "Infrastructure": "🏗️",
  "Telecom": "📡", "Communication": "📡",
  "Defence": "🛡️", "Defense": "🛡️",
  "PSU": "🏛️", "Public Sector": "🏛️",
  "Media": "📺", "Entertainment": "📺",
  "Chemical": "🧪", "Chemicals": "🧪",
  "Cement": "🏭", "Capital Goods": "🏭",
};
function sectorEmoji(name: string): string {
  for (const [key, emoji] of Object.entries(SECTOR_EMOJI)) {
    if (name.toLowerCase().includes(key.toLowerCase())) return emoji;
  }
  return "📊";
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
export default function Dashboard() {
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);

  const { data: patterns, isLoading: patLoading, isFetching: patFetching } = useQuery<any>({
    queryKey: ["patterns-overview"],
    queryFn:  () => api.patterns(),
    staleTime: 10 * 60_000,
    refetchInterval: (query) => {
      const d = (query as any).state?.data;
      return d?.scanInProgress ? 3000 : false;
    },
  });

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

  // Macro strip — same query key as MacroStrip component → deduplicates via cache
  const { data: macroData, isLoading: macroLoading } = useQuery<any>({
    queryKey: ["macro-strip"],
    queryFn:  api.macroStrip,
    staleTime: 15 * 60_000,
  });

  // Sentiment — 15-min cache, same data as /sentiment page
  const { data: sentimentData, isLoading: sentLoading } = useQuery<any>({
    queryKey: ["sentiment-market"],
    queryFn:  () => fetchApi("/sentiment/market"),
    staleTime: 15 * 60_000,
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
        queryClient.invalidateQueries({ queryKey: ["macro-strip"] }),
        queryClient.invalidateQueries({ queryKey: ["sentiment-market"] }),
      ]);
    } finally {
      setRefreshing(false);
    }
  }

  const isRefreshing = refreshing || patFetching;

  // ── Derived values ────────────────────────────────────────────────────────
  const latestFiiRow = useMemo(() => {
    const rows: any[] = fiiData?.rows ?? [];
    return rows.length > 0 ? rows[0] : null;
  }, [fiiData]);

  const fiiNet  = latestFiiRow?.fiiNet  ?? null;
  const diiNet  = latestFiiRow?.diiNet  ?? null;
  const fiiDate = latestFiiRow?.date    ?? null;
  const todayIso     = new Date().toISOString().slice(0, 10);
  const yesterdayIso = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
  const fiiSuffix    = fiiDate === todayIso ? " · Today"
                     : fiiDate === yesterdayIso ? " · Yesterday" : "";

  const adRatio   = (rotation as any)?.adRatio       ?? null;
  const breadth   = (rotation as any)?.marketBreadth ?? {};
  const rotPhase  = (rotation as any)?.rotationPhase ?? null;
  const sectors   = (rotation as any)?.sectors ?? [];

  // Market Health Score (0–100)
  const healthScore = useMemo(() => {
    const adPts   = adRatio != null ? Math.min((adRatio / 2.5) * 40, 40) : 20;
    const bPts    = (breadth.breadthScore ?? 50) / 100 * 35;
    const total   = (patterns?.callSignals ?? 0) + (patterns?.putSignals ?? 0);
    const sigPts  = total > 0 ? (patterns!.callSignals / total) * 25 : 12;
    return Math.round(adPts + bPts + sigPts);
  }, [adRatio, breadth.breadthScore, patterns]);

  // Money flow label
  const { flowLabel, flowDot } = useMemo(() => {
    const net = (fiiNet ?? 0) + (diiNet ?? 0);
    if (fiiNet == null && diiNet == null) return { flowLabel: "—", flowDot: "bg-gray-400" };
    if (net > 2000)   return { flowLabel: "Strong Risk-On",  flowDot: "bg-emerald-500" };
    if (net > 0)      return { flowLabel: "Risk-On",         flowDot: "bg-green-500"   };
    if (net > -2000)  return { flowLabel: "Cautious",        flowDot: "bg-amber-500"   };
    return              { flowLabel: "Risk-Off",        flowDot: "bg-red-500"     };
  }, [fiiNet, diiNet]);

  // Leading sector
  const leadingSector = useMemo(() => {
    if (!sectors.length) return null;
    const sorted = [...sectors].sort((a: any, b: any) => (b.pChange ?? -99) - (a.pChange ?? -99));
    return sorted[0] ?? null;
  }, [sectors]);

  const sectorStrength = (pc: number | null) =>
    pc == null ? "—" : pc > 2 ? "High" : pc > 1 ? "Moderate" : pc > 0 ? "Mild" : "Negative";

  // Risk Appetite Score (0–100) — VIX + FII + breadth + phase
  const { riskScore, riskLabel, riskDot } = useMemo(() => {
    const vix = sentimentData?.vix?.current ?? null;
    const vixPts = vix == null ? 15
      : vix < 13 ? 30 : vix < 18 ? 22 : vix < 22 ? 13 : vix < 28 ? 5 : 0;
    const fiiPts = fiiNet == null ? 14
      : fiiNet > 0 ? 30 : fiiNet > -500 ? 18 : fiiNet > -2000 ? 8 : 0;
    const bPts = (breadth.breadthScore ?? 50) / 100 * 25;
    const phase = (rotPhase ?? "").toLowerCase();
    const phasePts = phase.includes("full") || phase.includes("early") ? 15
      : phase.includes("bear") || phase.includes("recession") ? 0
      : phase.includes("slow") || phase.includes("late") ? 4 : 8;
    const score = Math.round(vixPts + fiiPts + bPts + phasePts);
    const label = score >= 70 ? "High Risk Appetite"
                : score >= 50 ? "Moderate"
                : score >= 30 ? "Cautious"
                : "Risk-Off";
    const dotCls = score >= 70 ? "bg-emerald-500"
                 : score >= 50 ? "bg-amber-500"
                 : "bg-red-500";
    return { riskScore: score, riskLabel: label, riskDot: dotCls };
  }, [sentimentData, fiiNet, breadth.breadthScore, rotPhase]);

  const newsItems = useMemo(() => {
    const articles: any[] = (newsData as any)?.articles ?? [];
    return articles.slice(0, 5);
  }, [newsData]);

  const anyLoading = fiiLoading || rotLoading || patLoading || sentLoading || macroLoading;

  // ── IPO helpers ──────────────────────────────────────────────────────────
  const fmtDate = (iso: string | null) => {
    if (!iso) return "—";
    return new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
  };
  const daysUntil = (iso: string | null) => {
    if (!iso) return null;
    const today = new Date(); today.setHours(0,0,0,0);
    return Math.round((new Date(iso + "T00:00:00").getTime() - today.getTime()) / 86_400_000);
  };

  return (
    <div className="space-y-6">

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Market Dashboard</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">Indian Stock Market · Live Overview</p>
        </div>
        <button onClick={handleRefresh} disabled={isRefreshing}
          className="flex items-center gap-2 text-sm text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 border border-indigo-200 dark:border-indigo-700 rounded-lg px-3 py-1.5 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 transition disabled:opacity-60">
          <RefreshCw className={`w-4 h-4 ${isRefreshing ? "animate-spin" : ""}`} />
          {isRefreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {/* ── 5 Navigation Cards ───────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">

        {/* 1. Market Health */}
        <NavCard
          href="/rotation"
          title="Market Health"
          loading={rotLoading || patLoading}
          dotCls={dot(healthScore)}
          value={`${healthScore}/100`}
          valueCls={dotLabel(healthScore)}
          sub={
            breadth.advancing != null
              ? <span>
                  <span className="text-emerald-500">↑{breadth.advancing} adv</span>
                  {"  "}
                  <span className="text-red-500">↓{breadth.declining ?? 0} dec</span>
                </span>
              : rotPhase ?? "—"
          }
          detail={rotPhase}
          icon={<BarChart2 className="w-4 h-4" />}
        />

        {/* 2. Money Flow */}
        <NavCard
          href="/insights/fii-dii"
          title={`Money Flow${fiiSuffix}`}
          loading={fiiLoading}
          dotCls={flowDot}
          value={flowLabel}
          sub={
            fiiNet != null
              ? <span>
                  <span className={fiiNet >= 0 ? "text-emerald-500" : "text-red-500"}>
                    FII {fmtCr(fiiNet)}
                  </span>
                  {"  ·  "}
                  <span className={diiNet != null && diiNet >= 0 ? "text-emerald-500" : "text-red-500"}>
                    DII {fmtCr(diiNet)}
                  </span>
                </span>
              : undefined
          }
          icon={<TrendingUp className="w-4 h-4" />}
        />

        {/* 3. Sector Leadership */}
        <NavCard
          href="/rotation"
          title="Sector Leadership"
          loading={rotLoading}
          dotCls={leadingSector ? (leadingSector.pChange >= 0 ? "bg-emerald-500" : "bg-red-500") : "bg-gray-400"}
          value={leadingSector
            ? `${sectorEmoji(leadingSector.name)} ${leadingSector.name}`
            : "—"}
          valueCls="text-gray-900 dark:text-white text-base font-black"
          sub={leadingSector
            ? <span>
                <span className={leadingSector.pChange >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-500"}>
                  {fmtPct(leadingSector.pChange)}
                </span>
                {"  ·  Strength: "}
                <span className="font-semibold">{sectorStrength(leadingSector.pChange)}</span>
              </span>
            : "No sector data"}
          icon={<Zap className="w-4 h-4" />}
        />

        {/* 4. Risk Appetite */}
        <NavCard
          href="/sentiment"
          title="Risk Appetite"
          loading={sentLoading || fiiLoading || rotLoading}
          dotCls={riskDot}
          value={riskLabel}
          valueCls={dotLabel(riskScore)}
          sub={`Score: ${riskScore}/100`}
          detail={
            sentimentData?.vix?.current != null
              ? `VIX ${(sentimentData.vix.current as number).toFixed(1)}`
              : undefined
          }
          icon={<ShieldAlert className="w-4 h-4" />}
        />

        {/* 5. Opportunity Scanner */}
        <Link href="/patterns" className="col-span-2 md:col-span-1 block h-full rounded-xl">
          <NavCard
            title="Opportunity Scanner"
            loading={patLoading}
            dotCls={
              !patterns ? "bg-gray-400"
              : patterns.callSignals > patterns.putSignals ? "bg-emerald-500"
              : patterns.callSignals < patterns.putSignals ? "bg-red-500"
              : "bg-amber-500"
            }
            value={
              scanInProgress
                ? "Scanning…"
                : patterns ? String(patterns.totalPatterns ?? 0) : "—"
            }
            valueCls="text-gray-900 dark:text-white"
            sub={
              scanInProgress
                ? <span className="flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" /> In progress…</span>
                : patterns && (patterns.totalPatterns ?? 0) > 0
                  ? <span>
                      <span className="text-emerald-500">↑{patterns.callSignals} bullish</span>
                      {"  "}
                      <span className="text-red-500">↓{patterns.putSignals} bearish</span>
                    </span>
                  : "Run a scan to detect"
            }
            detail="Active signals"
            icon={<Activity className="w-4 h-4" />}
          />
        </Link>

      </div>

      {/* ── Sentiment + Macro Environment ─────────────────────────────────────── */}
      <div className="grid md:grid-cols-2 gap-6">
        <SentimentCard sentiment={sentimentData} loading={sentLoading} />
        <MacroEnvironmentCard macroData={macroData} loading={macroLoading} />
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
              {[1,2,3,4,5].map(i => <div key={i} className="h-14 bg-gray-100 dark:bg-gray-700 animate-pulse rounded-lg" />)}
            </div>
          ) : (() => {
            const combined = [
              ...(ipoData?.open ?? []),
              ...(ipoData?.upcoming ?? []),
            ];
            // Sort by GMP premium descending; nulls/no-GMP go to the bottom
            const all = combined
              .slice()
              .sort((a: any, b: any) => {
                const ga = a.gmp?.premium ?? -Infinity;
                const gb = b.gmp?.premium ?? -Infinity;
                return gb - ga;
              })
              .slice(0, 6);

            if (!all.length) {
              return (
                <div className="flex flex-col items-center justify-center py-6 gap-2 text-center">
                  <Rocket className="w-8 h-8 text-gray-300 dark:text-gray-600" />
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {ipoData?.message ?? "No active IPOs right now"}
                  </p>
                </div>
              );
            }

            return (
              <div className="space-y-2.5">
                {all.map((ipo: any, i: number) => {
                  const isOpen   = ipo.status === "open";
                  const closesIn = daysUntil(ipo.closeDate);
                  const opensIn  = daysUntil(ipo.openDate);
                  const gmp      = ipo.gmp;
                  const hasGmp   = gmp && gmp.premium != null;
                  const gmpUp    = hasGmp && gmp.premium > 0;
                  const priceStr = ipo.priceHigh != null
                    ? (ipo.priceLow && ipo.priceLow !== ipo.priceHigh
                        ? `₹${ipo.priceLow}–${ipo.priceHigh}`
                        : `₹${ipo.priceHigh}`)
                    : null;

                  return (
                    <div key={i} className="flex items-start gap-3 p-3 rounded-lg border border-gray-100 dark:border-gray-700 hover:border-indigo-200 dark:hover:border-indigo-700 transition">
                      <div className={`mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${isOpen ? "bg-green-400 animate-pulse" : "bg-gray-300 dark:bg-gray-600"}`} />
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
                      {hasGmp ? (
                        <div className={`flex-shrink-0 text-right rounded-md px-2 py-1 ${
                          gmpUp ? "bg-emerald-50 dark:bg-emerald-500/10" : "bg-rose-50 dark:bg-rose-500/10"
                        }`}>
                          <p className="text-[9px] uppercase tracking-wide font-bold text-gray-400 leading-tight">GMP</p>
                          <p className={`text-xs font-bold tabular-nums leading-tight ${
                            gmpUp ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"
                          }`}>
                            {gmp.premium >= 0 ? "+" : ""}₹{gmp.premium}
                          </p>
                          {gmp.estGainPct != null && (
                            <p className={`text-[9px] font-semibold tabular-nums leading-tight ${gmpUp ? "text-emerald-500" : "text-rose-500"}`}>
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
