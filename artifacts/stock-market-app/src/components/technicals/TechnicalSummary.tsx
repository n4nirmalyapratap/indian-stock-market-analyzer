import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useTheme } from "@/context/ThemeContext";
import type { TechSignal, TechAction, TechSection, TechnicalSummary as TSummary } from "@/lib/api";

// ── Theme-aware palette ───────────────────────────────────────────────────────

function usePalette() {
  const { theme } = useTheme();
  const d = theme === "dark";
  return {
    isDark:   d,
    bgPage:   d ? "#131722" : "#f8fafc",
    bgCard:   d ? "#1e222d" : "#ffffff",
    bgHover:  d ? "#252933" : "#f1f5f9",
    border:   d ? "#2a2e39" : "#e2e8f0",
    txtMain:  d ? "#d1d4dc" : "#1e293b",
    txtDim:   d ? "#787b86" : "#64748b",
    txtSell:  "#ef5350",
    txtBuy:   "#4b9fe1",
    txtNeu:   d ? "#787b86" : "#94a3b8",
    arcSell:  "#ef5350",
    arcBuy:   "#4b9fe1",
    arcBg:    d ? "#2a2e3980" : "#e2e8f080",
  };
}

// ── Signal helpers ────────────────────────────────────────────────────────────

function signalLabel(s: TechSignal) {
  return s === "STRONG_BUY" ? "Strong buy"
    : s === "BUY" ? "Buy"
    : s === "STRONG_SELL" ? "Strong sell"
    : s === "SELL" ? "Sell"
    : "Neutral";
}

function signalAngle(buy: number, sell: number, neutral: number): number {
  const total = buy + sell + neutral;
  if (total === 0) return 90;
  const score = Math.min(1, Math.max(-1, (buy - sell) / total));
  // score -1 → 180° (strong sell / left), 0 → 90° (neutral / top), +1 → 0° (strong buy / right)
  return 90 - score * 90;
}

function signalColor(s: TechSignal, p: ReturnType<typeof usePalette>) {
  return (s === "STRONG_BUY" || s === "BUY") ? p.txtBuy
    : (s === "STRONG_SELL" || s === "SELL") ? p.txtSell
    : p.txtNeu;
}

function actionColor(a: TechAction, p: ReturnType<typeof usePalette>) {
  return a === "BUY" ? p.txtBuy : a === "SELL" ? p.txtSell : p.txtNeu;
}

// ── Elegant Gauge ─────────────────────────────────────────────────────────────
// viewBox 0 0 260 150 | center (130, 130) | r=100

const CX = 130; const CY = 130; const R = 100;

function ptOnArc(angleDeg: number): [number, number] {
  const rad = (angleDeg * Math.PI) / 180;
  return [
    Math.round((CX + R * Math.cos(rad)) * 1000) / 1000,
    Math.round((CY - R * Math.sin(rad)) * 1000) / 1000,
  ];
}

// Generates an SVG arc path string that draws from angle a1 to a2 (degrees, CCW in math = SVG sweep=0)
function arcPath(a1: number, a2: number): string {
  const [x1, y1] = ptOnArc(a1);
  const [x2, y2] = ptOnArc(a2);
  const large = Math.abs(a2 - a1) > 180 ? 1 : 0;
  return `M ${x1} ${y1} A ${R} ${R} 0 ${large} 0 ${x2} ${y2}`;
}

// Tick marks at Strong Sell (180°), Sell (135°), Neutral (90°), Buy (45°), Strong Buy (0°)
const TICKS = [
  { angle: 180, label: "Strong sell", color: "#ef5350" },
  { angle: 135, label: "Sell",        color: "#ef5350" },
  { angle:  90, label: "Neutral",     color: "#94a3b8" },
  { angle:  45, label: "Buy",         color: "#4b9fe1" },
  { angle:   0, label: "Strong buy",  color: "#4b9fe1" },
];

interface GaugeProps {
  signal:  TechSignal;
  buy:     number;
  sell:    number;
  neutral: number;
  size?:   number;
  id:      string;
}

function Gauge({ signal, buy, sell, neutral, size = 220, id }: GaugeProps) {
  const p = usePalette();
  const angleDeg = signalAngle(buy, sell, neutral);
  // SVG positive rotation is clockwise. Needle starts pointing up (90°).
  // STRONG_BUY → angleDeg=0 → rotate +90 clockwise (point right)
  // STRONG_SELL → angleDeg=180 → rotate -90 counterclockwise (point left)
  const rotateDeg = 90 - angleDeg;

  const sellId  = `sell-${id}`;
  const buyId   = `buy-${id}`;
  const glowId  = `glow-${id}`;
  const height  = size * 150 / 260;

  // Arc segments: background, sell half, buy half
  const bgArc   = arcPath(180, 0);        // full half-circle background
  const sellArc = arcPath(180, 90);       // sell zone (left half)
  const buyArc  = arcPath(90, 0);         // buy zone (right half)

  const [nx, ny] = ptOnArc(90);           // needle start = top of arc (will be rotated)

  return (
    <svg viewBox="0 0 260 150" width={size} height={height} role="img" aria-label={signalLabel(signal)}>
      <defs>
        {/* Sell gradient: red at left end → transparent at center-top */}
        <linearGradient id={sellId} gradientUnits="userSpaceOnUse" x1="30" y1="130" x2="130" y2="30">
          <stop offset="0%"   stopColor="#ef5350" stopOpacity="0.95" />
          <stop offset="100%" stopColor="#ef5350" stopOpacity="0.20" />
        </linearGradient>
        {/* Buy gradient: transparent at center-top → blue at right end */}
        <linearGradient id={buyId} gradientUnits="userSpaceOnUse" x1="130" y1="30" x2="230" y2="130">
          <stop offset="0%"   stopColor="#4b9fe1" stopOpacity="0.20" />
          <stop offset="100%" stopColor="#4b9fe1" stopOpacity="0.95" />
        </linearGradient>
        {/* Glow filter for the active arc segment */}
        <filter id={glowId} x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="2.5" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>

      {/* ── Track (full bg arc) */}
      <path d={bgArc} fill="none" stroke={p.arcBg} strokeWidth="18" strokeLinecap="round" />

      {/* ── Sell arc — red zone */}
      <path d={sellArc} fill="none" stroke={`url(#${sellId})`} strokeWidth="18" strokeLinecap="round" />

      {/* ── Buy arc — blue zone */}
      <path d={buyArc}  fill="none" stroke={`url(#${buyId})`}  strokeWidth="18" strokeLinecap="round" />

      {/* ── Tick marks */}
      {TICKS.map(({ angle, color }) => {
        const [ox, oy] = ptOnArc(angle);
        const rad = (angle * Math.PI) / 180;
        const innerR = R - 26;
        const ix = CX + innerR * Math.cos(rad);
        const iy = CY - innerR * Math.sin(rad);
        return (
          <line key={angle} x1={ox} y1={oy} x2={ix} y2={iy}
            stroke={color} strokeWidth="2" strokeOpacity="0.6" strokeLinecap="round" />
        );
      })}

      {/* ── Label positions */}
      {[
        { angle: 180, text: "Strong sell", color: "#ef5350", anchor: "middle" },
        { angle:  90, text: "Neutral",     color: "#94a3b8", anchor: "middle" },
        { angle:   0, text: "Strong buy",  color: "#4b9fe1", anchor: "middle" },
      ].map(({ angle, text, color, anchor }) => {
        const [ox, oy] = ptOnArc(angle);
        const rad = (angle * Math.PI) / 180;
        const labelR = R + 16;
        const lx = CX + labelR * Math.cos(rad);
        const ly = CY - labelR * Math.sin(rad);
        return (
          <text key={angle} x={lx} y={ly} fontSize="8.5" fill={color}
            textAnchor={anchor as any} dominantBaseline="middle" fontFamily="system-ui,sans-serif"
            fontWeight="500">
            {text}
          </text>
        );
      })}
      {/* Sell and Buy labels at mid-points */}
      {[
        { angle: 135, text: "Sell", color: "#ef5350" },
        { angle:  45, text: "Buy",  color: "#4b9fe1" },
      ].map(({ angle, text, color }) => {
        const rad = (angle * Math.PI) / 180;
        const labelR = R + 14;
        const lx = CX + labelR * Math.cos(rad);
        const ly = CY - labelR * Math.sin(rad);
        return (
          <text key={angle} x={lx} y={ly} fontSize="9" fill={color}
            textAnchor="middle" dominantBaseline="middle" fontFamily="system-ui,sans-serif" fontWeight="600">
            {text}
          </text>
        );
      })}

      {/* ── Animated needle */}
      <g style={{
        transformOrigin: `${CX}px ${CY}px`,
        transform: `rotate(${rotateDeg}deg)`,
        transition: "transform 0.9s cubic-bezier(0.34, 1.56, 0.64, 1)",
      }}>
        {/* Needle shadow */}
        <line x1={CX} y1={CY - 6} x2={CX} y2={CY - 86}
          stroke="black" strokeOpacity="0.15" strokeWidth="4" strokeLinecap="round" />
        {/* Needle body */}
        <line x1={CX} y1={CY - 6} x2={CX} y2={CY - 84}
          stroke="white" strokeWidth="2.5" strokeLinecap="round" />
        {/* Needle tip highlight */}
        <circle cx={CX} cy={CY - 84} r="2" fill="white" fillOpacity="0.8" />
      </g>

      {/* ── Center hub */}
      <circle cx={CX} cy={CY} r="8" fill={p.bgCard} stroke={p.border} strokeWidth="2" />
      <circle cx={CX} cy={CY} r="4" fill={signalColor(signal, p)} />
    </svg>
  );
}

// ── Thin loading bar ──────────────────────────────────────────────────────────

function FetchBar({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <div className="absolute top-0 left-0 right-0 h-0.5 overflow-hidden rounded-t-xl z-10">
      <div
        className="h-full bg-indigo-500"
        style={{
          width: "40%",
          animation: "fetchSlide 1.2s ease-in-out infinite",
        }}
      />
      <style>{`
        @keyframes fetchSlide {
          0%   { transform: translateX(-100%); }
          100% { transform: translateX(350%); }
        }
      `}</style>
    </div>
  );
}

// ── Timeframe selector ────────────────────────────────────────────────────────

const TIMEFRAMES = [
  { key: "1m",  label: "1 minute" },
  { key: "5m",  label: "5 minutes" },
  { key: "15m", label: "15 minutes" },
  { key: "30m", label: "30 minutes" },
  { key: "1h",  label: "1 hour" },
  { key: "2h",  label: "2 hours" },
  { key: "4h",  label: "4 hours" },
  { key: "1d",  label: "1 day" },
  { key: "1w",  label: "1 week" },
  { key: "1mo", label: "1 month" },
] as const;

type Interval = typeof TIMEFRAMES[number]["key"];

// ── Indicator table ───────────────────────────────────────────────────────────

function IndicatorTable({ section, title, isFetching }: { section: TechSection; title: string; isFetching: boolean }) {
  const p = usePalette();
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? section.indicators : section.indicators.slice(0, 4);

  return (
    <div className="relative overflow-hidden rounded-xl" style={{ background: p.bgCard, border: `1px solid ${p.border}` }}>
      <FetchBar visible={isFetching} />
      <button
        className="w-full flex items-center gap-2 px-4 py-3 text-left transition-opacity hover:opacity-70"
        onClick={() => setExpanded(e => !e)}
      >
        <span className="text-sm font-semibold" style={{ color: p.txtMain }}>{title}</span>
        <span className="text-xs" style={{ color: p.txtDim }}>›</span>
      </button>
      <table className="w-full text-xs">
        <thead>
          <tr style={{ borderTop: `1px solid ${p.border}` }}>
            <th className="text-left px-4 py-2 font-medium" style={{ color: p.txtDim }}>Name</th>
            <th className="text-right px-4 py-2 font-medium" style={{ color: p.txtDim }}>Value</th>
            <th className="text-right px-4 py-2 font-medium" style={{ color: p.txtDim }}>Action</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((row, i) => (
            <tr
              key={row.name}
              style={{ borderTop: `1px solid ${p.border}`, background: i % 2 === 0 ? "transparent" : p.bgHover }}
              className="transition-colors"
            >
              <td className="px-4 py-2.5" style={{ color: p.txtMain }}>{row.name}</td>
              <td className="px-4 py-2.5 text-right tabular-nums" style={{ color: p.txtDim }}>
                {row.value != null ? row.value.toFixed(2) : "—"}
              </td>
              <td className="px-4 py-2.5 text-right font-semibold" style={{ color: actionColor(row.action, p) }}>
                {row.action === "BUY" ? "Buy" : row.action === "SELL" ? "Sell" : "Neutral"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {section.indicators.length > 4 && (
        <button
          onClick={() => setExpanded(e => !e)}
          className="w-full text-xs py-2 transition-opacity hover:opacity-70"
          style={{ color: p.txtDim, borderTop: `1px solid ${p.border}` }}
        >
          {expanded ? "Show less ▲" : `Show all ${section.indicators.length} indicators ▼`}
        </button>
      )}
    </div>
  );
}

// ── Section panel ─────────────────────────────────────────────────────────────

function SectionPanel({ section, title, isFetching }: { section: TechSection; title: string; isFetching: boolean }) {
  const p = usePalette();
  const id = title.toLowerCase().replace(/\s/g, "-");

  return (
    <div className="space-y-3">
      <div className="relative overflow-hidden rounded-xl p-5 flex flex-col items-center gap-2"
           style={{ background: p.bgCard, border: `1px solid ${p.border}` }}>
        <FetchBar visible={isFetching} />
        <span className="text-sm font-semibold" style={{ color: p.txtMain }}>{title}</span>
        <Gauge signal={section.signal} buy={section.buy} sell={section.sell} neutral={section.neutral} size={190} id={id} />
        <span className="text-base font-bold" style={{ color: signalColor(section.signal, p) }}>
          {signalLabel(section.signal)}
        </span>
        <div className="flex gap-6 mt-1">
          {[["Sell", section.sell, p.txtSell], ["Neutral", section.neutral, p.txtNeu], ["Buy", section.buy, p.txtBuy]].map(([l, v, c]) => (
            <div key={l as string} className="text-center">
              <div className="text-xs font-medium" style={{ color: c as string }}>{l as string}</div>
              <div className="text-xl font-bold" style={{ color: p.txtMain }}>{v as number}</div>
            </div>
          ))}
        </div>
      </div>
      <IndicatorTable section={section} title={title} isFetching={isFetching} />
    </div>
  );
}

// ── Pivot table ───────────────────────────────────────────────────────────────

type PivotType = "classic" | "fibonacci" | "camarilla" | "woodie" | "dm";

function PivotTable({ pivots, isFetching }: { pivots: TSummary["pivots"]; isFetching: boolean }) {
  const p = usePalette();
  const [active, setActive] = useState<PivotType>("classic");

  const data = pivots[active];
  const levels = "r3" in data
    ? ["R3","R2","R1","P","S1","S2","S3"].map(l => ({ label: l, val: (data as any)[l.toLowerCase()] }))
    : ["R1","P","S1"].map(l => ({ label: l, val: (data as any)[l.toLowerCase()] }));

  return (
    <div className="relative overflow-hidden rounded-xl" style={{ background: p.bgCard, border: `1px solid ${p.border}` }}>
      <FetchBar visible={isFetching} />
      <div className="px-4 py-3 flex items-center gap-2" style={{ borderBottom: `1px solid ${p.border}` }}>
        <span className="text-sm font-semibold" style={{ color: p.txtMain }}>Pivots</span>
        <span className="text-xs" style={{ color: p.txtDim }}>›</span>
      </div>
      <div className="flex" style={{ borderBottom: `1px solid ${p.border}` }}>
        {(["classic","fibonacci","camarilla","woodie","dm"] as PivotType[]).map(t => (
          <button key={t} onClick={() => setActive(t)}
            className="flex-1 py-2 text-xs font-medium capitalize transition-all"
            style={{
              color: active === t ? p.txtMain : p.txtDim,
              borderBottom: active === t ? `2px solid #4b9fe1` : "2px solid transparent",
              background: "transparent",
            }}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr>
            <th className="text-left px-4 py-2 font-medium" style={{ color: p.txtDim }}>Pivot</th>
            <th className="text-right px-4 py-2 font-medium" style={{ color: p.txtDim }}>Level</th>
          </tr>
        </thead>
        <tbody>
          {levels.map(({ label, val }) => {
            const isP = label === "P";
            const isR = label.startsWith("R");
            const isS = label.startsWith("S");
            return (
              <tr key={label} style={{ borderTop: `1px solid ${p.border}`, background: isP ? p.bgHover : "transparent" }}>
                <td className="px-4 py-2.5 font-semibold"
                    style={{ color: isR ? p.txtSell : isS ? p.txtBuy : p.txtMain }}>{label}</td>
                <td className="px-4 py-2.5 text-right tabular-nums" style={{ color: p.txtMain }}>
                  {val != null ? val.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function TechnicalSummary({ symbol }: { symbol: string }) {
  const p = usePalette();
  const [interval, setInterval] = useState<Interval>("1d");

  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ["tech-summary", symbol, interval],
    queryFn: () => api.stockTechnicalSummary(symbol, interval),
    enabled: !!symbol,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  if (isLoading) {
    return (
      <div className="rounded-xl p-6 space-y-4" style={{ background: p.bgPage }}>
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-24 rounded-xl animate-pulse" style={{ background: p.bgCard }} />
        ))}
      </div>
    );
  }

  if (error || !data || (data as any).error) {
    return (
      <div className="rounded-xl p-6 text-center text-sm" style={{ background: p.bgPage, color: p.txtDim }}>
        Technical summary unavailable for {symbol}.
      </div>
    );
  }

  const { summary, oscillators, movingAverages, pivots } = data;

  return (
    <div className="rounded-xl p-4 space-y-5 transition-colors duration-300" style={{ background: p.bgPage }} data-testid="technical-summary">

      {/* Header */}
      <div>
        <h3 className="font-semibold text-sm mb-1" style={{ color: p.txtMain }}>Indicators' summary</h3>
        <p className="text-xs leading-relaxed" style={{ color: p.txtDim }}>
          Technical analysis overview for the selected timeframe. Includes key data from
          moving averages, oscillators, and pivots — all summed up in the Summary gauge.
        </p>
      </div>

      {/* Timeframe selector */}
      <div className="flex flex-wrap gap-0.5 pb-0.5" style={{ borderBottom: `1px solid ${p.border}` }}>
        {TIMEFRAMES.map(tf => (
          <button key={tf.key} onClick={() => setInterval(tf.key)}
            className="px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-200"
            style={{
              background: interval === tf.key ? (p.isDark ? "#2a2e39" : "#e2e8f0") : "transparent",
              color:      interval === tf.key ? p.txtMain : p.txtDim,
              border: "none",
              transform: interval === tf.key ? "scale(1.0)" : "scale(0.97)",
            }}>
            {tf.label}
          </button>
        ))}
      </div>

      {/* ── Large summary gauge ── */}
      <div className="relative overflow-hidden rounded-xl p-6 flex flex-col items-center gap-3 transition-colors duration-300"
           style={{ background: p.bgCard, border: `1px solid ${p.border}` }}>
        <FetchBar visible={isFetching} />
        <span className="text-sm font-semibold tracking-wide" style={{ color: p.txtMain }}>Summary</span>
        <Gauge
          signal={summary.signal} buy={summary.buy} sell={summary.sell} neutral={summary.neutral}
          size={260} id="summary"
        />
        <span className="text-2xl font-bold tracking-tight transition-all duration-500"
              style={{ color: signalColor(summary.signal, p) }}>
          {signalLabel(summary.signal)}
        </span>
        <div className="flex gap-10 mt-1">
          {[["Sell", summary.sell, p.txtSell], ["Neutral", summary.neutral, p.txtNeu], ["Buy", summary.buy, p.txtBuy]].map(([l, v, c]) => (
            <div key={l as string} className="text-center">
              <div className="text-xs font-medium uppercase tracking-wider" style={{ color: c as string }}>{l as string}</div>
              <div className="text-2xl font-bold transition-all duration-500" style={{ color: p.txtMain }}>{v as number}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Oscillators + Moving Averages ── */}
      <div className="grid md:grid-cols-2 gap-4">
        <SectionPanel section={oscillators}    title="Oscillators"     isFetching={isFetching} />
        <SectionPanel section={movingAverages} title="Moving Averages" isFetching={isFetching} />
      </div>

      {/* ── Pivots ── */}
      <PivotTable pivots={pivots} isFetching={isFetching} />
    </div>
  );
}
