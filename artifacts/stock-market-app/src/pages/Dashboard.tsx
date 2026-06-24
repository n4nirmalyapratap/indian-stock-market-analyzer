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
// Valley-inspired SVG arc gauge — color-reactive, animated needle + fill.
function MiniGauge({ score }: { score: number | null }) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const [fired, setFired] = useState(false);

  useEffect(() => {
    setFired(false);
    const t = setTimeout(() => setFired(true), 120);
    return () => clearTimeout(t);
  }, [score]);

  const cx = 110, cy = 96, r = 76;

  // Accent color tracks the sentiment zone
  const accent =
    score == null       ? (isDark ? "#475569" : "#94a3b8")
    : score >= 30       ? "#16a34a"   // bullish — green-700
    : score >= 10       ? "#22c55e"   // mildly bullish — green-500
    : score > -10       ? (isDark ? "#64748b" : "#94a3b8")  // neutral — slate
    : score > -30       ? "#f97316"   // mildly bearish — orange
    : "#dc2626";                      // bearish — red-600

  const trackColor  = isDark ? "#1e293b" : "#f1f5f9";
  const hubFill     = isDark ? "#0f172a" : "#ffffff";
  const neutralTick = isDark ? "#334155" : "#cbd5e1";

  // Angle: score −100→+100 maps to −90°→+90°
  const needleAngle = score != null ? score * 0.9 : -90;

  // Arc helpers — 0° = top, clockwise
  function pt(deg: number, radius = r) {
    const rad = ((deg - 90) * Math.PI) / 180;
    return { x: cx + radius * Math.cos(rad), y: cy + radius * Math.sin(rad) };
  }
  function arc(from: number, to: number, radius = r) {
    const s = pt(from, radius), e = pt(to, radius);
    const large = Math.abs(to - from) > 180 ? 1 : 0;
    return `M ${s.x.toFixed(2)} ${s.y.toFixed(2)} A ${radius} ${radius} 0 ${large} 1 ${e.x.toFixed(2)} ${e.y.toFixed(2)}`;
  }

  // Five equal segments (−90°..+90° split into 5×36°)
  const segColors = ["#dc2626", "#f97316", neutralTick, "#22c55e", "#16a34a"];
  const segs = segColors.map((color, i) => ({
    from: i * 36,
    to:   (i + 1) * 36,
    color,
  }));

  // Tick marks at each segment boundary (6 ticks)
  const ticks = [0, 36, 72, 108, 144, 180].map(deg => {
    const inner = pt(deg, r - 9);
    const outer = pt(deg, r + 1);
    return { inner, outer };
  });

  // Fill arc: from leftmost (0°) to needle position
  const needleDeg = needleAngle + 90; // convert to 0°=left convention
  const arcLen = Math.PI * r;
  const normalized = score != null ? (score + 100) / 200 : 0;

  return (
    <svg width="220" height="130" viewBox="0 0 220 130" className="mx-auto overflow-visible">
      {/* Track */}
      <path d={arc(0, 180)} fill="none" stroke={trackColor} strokeWidth="12" strokeLinecap="round" />

      {/* Segment zones — dim all, highlight the active one */}
      {segs.map((s, i) => {
        const midDeg = (s.from + s.to) / 2;
        const active = fired && needleDeg >= s.from && needleDeg < s.to;
        return (
          <path key={i} d={arc(s.from, s.to)} fill="none" stroke={s.color}
            strokeWidth="10" strokeLinecap="butt"
            style={{
              opacity: active ? 1 : 0.18,
              filter: active ? `drop-shadow(0 0 4px ${s.color}90)` : "none",
              transition: "opacity 0.55s ease, filter 0.55s ease",
            }}
          />
        );
      })}

      {/* Tick lines between segments */}
      {ticks.map((tk, i) => (
        <line key={i}
          x1={tk.inner.x} y1={tk.inner.y}
          x2={tk.outer.x} y2={tk.outer.y}
          stroke={isDark ? "#1e293b" : "#ffffff"} strokeWidth="2"
        />
      ))}

      {/* Fill sweep — animated */}
      <path d={arc(0, 180)} fill="none" stroke={accent} strokeWidth="3"
        strokeLinecap="round" strokeDasharray={`${arcLen} ${arcLen}`}
        strokeDashoffset={fired ? arcLen * (1 - normalized) : arcLen}
        style={{ transition: "stroke-dashoffset 1.1s cubic-bezier(0.34,1.56,0.64,1)", opacity: 0.6 }}
      />

      {/* Needle */}
      <g style={{
        transform: `rotate(${fired ? needleAngle : -90}deg)`,
        transformOrigin: `${cx}px ${cy}px`,
        transition: "transform 1.15s cubic-bezier(0.34,1.56,0.64,1)",
      }}>
        <line x1={cx} y1={cy + 6} x2={cx} y2={cy - r + 16}
          stroke={accent} strokeWidth="2" strokeLinecap="round" />
        <circle cx={cx} cy={cy - r + 16} r={3} fill={accent} opacity={0.3} />
        <circle cx={cx} cy={cy - r + 16} r={1.5} fill={accent} />
      </g>

      {/* Hub */}
      <circle cx={cx} cy={cy} r={9} fill={hubFill} stroke={accent} strokeWidth="1.5" />
      <circle cx={cx} cy={cy} r={4} fill={accent} />

      {/* Score */}
      {score != null
        ? <text x={cx} y={cy + 28} textAnchor="middle" fontSize="20" fontWeight="800"
            fill={accent} style={{ letterSpacing: "-0.5px", fontFamily: "system-ui,sans-serif" }}>
            {score > 0 ? `+${score}` : `${score}`}
          </text>
        : <text x={cx} y={cy + 22} textAnchor="middle" fontSize="14" fill={neutralTick} fontWeight="600">—</text>
      }

      {/* Labels */}
      <text x="8"   y="118" fontSize="7.5" fill="#dc2626" fontWeight="700" letterSpacing="0.5">BEAR</text>
      <text x={cx}  y="14"  textAnchor="middle" fontSize="7.5" fill={neutralTick} fontWeight="700" letterSpacing="0.5">NEUTRAL</text>
      <text x="212" y="118" textAnchor="end" fontSize="7.5" fill="#16a34a" fontWeight="700" letterSpacing="0.5">BULL</text>
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

  // Color scheme reactive to score — green/grey/red
  const isBullish  = composite != null && composite >= 10;
  const isBearish  = composite != null && composite <= -10;
  const accentCls  = isBullish  ? "text-green-600 dark:text-green-400"
                   : isBearish  ? "text-red-600 dark:text-red-400"
                   : "text-slate-500 dark:text-slate-400";
  const accentBg   = isBullish  ? "bg-green-600 dark:bg-green-500"
                   : isBearish  ? "bg-red-600 dark:bg-red-500"
                   : "bg-slate-400 dark:bg-slate-500";
  const borderGlow = isBullish  ? "border-green-200 dark:border-green-800/60"
                   : isBearish  ? "border-red-200 dark:border-red-800/60"
                   : "border-gray-100 dark:border-gray-700";

  return (
    <div className={`bg-white dark:bg-gray-800 rounded-xl border shadow-sm p-5 flex flex-col transition-colors duration-700 ${borderGlow}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <p className="text-[9px] font-bold text-gray-400 dark:text-gray-500 uppercase tracking-[0.18em]">
          Market Sentiment
        </p>
        <Link href="/sentiment"
          className="text-[9px] font-semibold text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 flex items-center gap-0.5 tracking-wide transition uppercase">
          Full Analysis <ArrowRight className="w-2.5 h-2.5" />
        </Link>
      </div>

      {loading ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 py-4">
          <div className="w-[220px] h-[130px] bg-gray-100 dark:bg-gray-700 animate-pulse rounded-xl" />
          <Skel h="h-4" w="w-24" r="rounded" />
        </div>
      ) : (
        <>
          {/* Gauge */}
          <MiniGauge score={composite} />

          {/* Label — large, weighted, color-reactive */}
          <p className={`text-base font-black text-center tracking-tight mb-4 transition-colors duration-700 ${accentCls}`}>
            {label}
          </p>

          {/* Divider */}
          <div className="border-t border-gray-100 dark:border-gray-700/60 mb-3" />

          {/* Component bars — Valley-style: label + dot-bar + weight */}
          <div className="space-y-2.5">
            {components.filter(c => c.weight > 0).map((c, i) => {
              const sc: number = c.score ?? 0;
              const pct = Math.min(100, Math.max(0, (sc + 100) / 2));
              const barBull = sc >= 10;
              const barBear = sc <= -10;
              const barCls  = barBull ? "bg-green-500 dark:bg-green-400"
                            : barBear ? "bg-red-500 dark:bg-red-400"
                            : "bg-slate-300 dark:bg-slate-600";
              return (
                <div key={i}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[9px] font-semibold uppercase tracking-[0.12em] text-gray-400 dark:text-gray-500">
                      {c.name}
                    </span>
                    <span className="text-[9px] font-bold text-gray-500 dark:text-gray-400">{c.weight}%</span>
                  </div>
                  <div className="h-[3px] bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${barCls}`}
                      style={{ width: `${pct}%`, transition: "width 1s cubic-bezier(0.34,1.56,0.64,1)" }} />
                  </div>
                </div>
              );
            })}
          </div>

          {/* VIX + News chips — Valley square-pill style */}
          <div className="flex gap-1.5 mt-3.5 flex-wrap">
            {vixVal != null && (
              <span className={`inline-flex items-center gap-1 text-[9px] rounded px-2 py-1 border font-bold tracking-wide uppercase
                ${vixVal < 15
                  ? "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800 text-green-700 dark:text-green-400"
                  : vixVal < 22
                  ? "bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-400"
                  : "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-700 dark:text-red-400"}`}>
                VIX {vixVal.toFixed(1)}
              </span>
            )}
            {newsMood && (
              <span className={`inline-flex items-center gap-1.5 text-[9px] rounded px-2 py-1 border font-bold tracking-wide uppercase
                ${newsMood === "bullish"
                  ? "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800 text-green-700 dark:text-green-400"
                  : newsMood === "bearish"
                  ? "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-700 dark:text-red-400"
                  : "bg-gray-50 dark:bg-gray-700/60 border-gray-200 dark:border-gray-600 text-gray-500 dark:text-gray-400"}`}>
                <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                  newsMood === "bullish" ? "bg-green-500" : newsMood === "bearish" ? "bg-red-500" : "bg-gray-400"
                }`} />
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
            const hasGmpValue = (ipo: any) => ipo.gmp?.premium != null && ipo.gmp.premium !== 0;
            // 1. Open IPOs first (fewest days left to close → closing soonest first)
            const open = (ipoData?.open ?? [])
              .filter(hasGmpValue)
              .slice()
              .sort((a: any, b: any) => {
                const da = daysUntil(a.closeDate) ?? Infinity;
                const db = daysUntil(b.closeDate) ?? Infinity;
                return da - db;
              });
            // 2. Upcoming IPOs — soonest to open first
            const upcoming = (ipoData?.upcoming ?? [])
              .filter(hasGmpValue)
              .slice()
              .sort((a: any, b: any) => {
                const da = daysUntil(a.openDate) ?? Infinity;
                const db = daysUntil(b.openDate) ?? Infinity;
                return da - db;
              });
            const all = [...open, ...upcoming].slice(0, 6);

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
