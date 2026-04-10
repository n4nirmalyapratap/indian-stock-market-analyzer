import { useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useTheme } from "@/context/ThemeContext";
import type { TechSignal, TechAction, TechSection, TechnicalSummary as TSummary } from "@/lib/api";

// ── Theme palette ──────────────────────────────────────────────────────────────

function usePalette() {
  const { theme } = useTheme();
  const d = theme === "dark";
  return {
    isDark:   d,
    bgPage:   d ? "#131722" : "#f8fafc",
    bgCard:   d ? "#1e222d" : "#ffffff",
    bgGauge:  d ? "#181c27" : "#f1f5f9",
    bgHover:  d ? "#252933" : "#f1f5f9",
    border:   d ? "#2a2e39" : "#e2e8f0",
    txtMain:  d ? "#d1d4dc" : "#1e293b",
    txtDim:   d ? "#787b86" : "#64748b",
    txtSell:  "#ef5350",
    txtBuy:   "#4b9fe1",
    txtNeu:   d ? "#78909c" : "#64748b",
    needleFg: d ? "#e2e8f0" : "#1e293b",
    capBg:    d ? "#1e222d" : "#ffffff",
  };
}

// ── Signal helpers ─────────────────────────────────────────────────────────────

function signalLabel(s: TechSignal) {
  return s === "STRONG_BUY" ? "Strong Buy"
    : s === "BUY"           ? "Buy"
    : s === "STRONG_SELL"   ? "Strong Sell"
    : s === "SELL"          ? "Sell"
    : "Neutral";
}

function signalColor(s: TechSignal, p: ReturnType<typeof usePalette>) {
  return (s === "STRONG_BUY" || s === "BUY")     ? p.txtBuy
    : (s === "STRONG_SELL" || s === "SELL") ? p.txtSell
    : p.txtNeu;
}

function actionColor(a: TechAction, p: ReturnType<typeof usePalette>) {
  return a === "BUY" ? p.txtBuy : a === "SELL" ? p.txtSell : p.txtNeu;
}

// score: -1 (strong sell) → +1 (strong buy)
function getScore(buy: number, sell: number, neutral: number): number {
  const total = buy + sell + neutral;
  return total === 0 ? 0 : Math.min(1, Math.max(-1, (buy - sell) / total));
}

// score → needle rotation in SVG degrees (positive = clockwise on screen)
// score -1 → needle far left (-90° from up, i.e. 90° counterclockwise of up)
// score  0 → needle straight up
// score +1 → needle far right (90° clockwise of up)
function scoreToRotate(score: number): number {
  return score * 90; // SVG positive = clockwise
}

// Which zone index is active: 0=StrongSell, 1=Sell, 2=Neutral, 3=Buy, 4=StrongBuy
function activeZone(s: TechSignal): number {
  return s === "STRONG_SELL" ? 0 : s === "SELL" ? 1 : s === "NEUTRAL" ? 2 : s === "BUY" ? 3 : 4;
}

// ── Gauge geometry constants ───────────────────────────────────────────────────

const VW = 280;        // viewBox width
const VH = 168;        // viewBox height
const GCX = 140;       // gauge center X
const GCY = 152;       // gauge center Y  (near bottom, gives room for gauge + labels above)
const R_OUT = 114;     // outer radius of zone band
const R_IN  = 76;      // inner radius of zone band  (band width = 38px)
const R_TIC = 70;      // inner end of tick marks
const R_TIC_OUT = 118; // outer end of tick marks (slightly outside R_OUT)
const NEEDLE_LEN = R_IN - 8;  // needle tip stops just inside inner ring

function ptAt(r: number, angleDeg: number): [number, number] {
  const rad = (angleDeg * Math.PI) / 180;
  return [
    +(GCX + r * Math.cos(rad)).toFixed(3),
    +(GCY - r * Math.sin(rad)).toFixed(3),
  ];
}

// Donut sector path from angle a1 to a2 (a1 > a2, both in math degrees, sweep decreasing)
function sectorPath(a1: number, a2: number, rOut = R_OUT, rIn = R_IN): string {
  const [ox1, oy1] = ptAt(rOut, a1);
  const [ox2, oy2] = ptAt(rOut, a2);
  const [ix1, iy1] = ptAt(rIn, a1);
  const [ix2, iy2] = ptAt(rIn, a2);
  const span = a1 - a2;
  const large = span > 180 ? 1 : 0;
  return [
    `M ${ox1} ${oy1}`,
    `A ${rOut} ${rOut} 0 ${large} 0 ${ox2} ${oy2}`,
    `L ${ix2} ${iy2}`,
    `A ${rIn} ${rIn} 0 ${large} 1 ${ix1} ${iy1}`,
    "Z",
  ].join(" ");
}

// Zone definitions — 5 equal sectors of 36° each
const ZONES = [
  { a1: 180, a2: 144, label: "S.Sell",  color: "#c62828", dimColor: "#7f1d1d" }, // Strong Sell
  { a1: 144, a2: 108, label: "Sell",    color: "#ef5350", dimColor: "#7f1d1d" }, // Sell
  { a1: 108, a2:  72, label: "Neutral", color: "#607d8b", dimColor: "#334155" }, // Neutral
  { a1:  72, a2:  36, label: "Buy",     color: "#42a5f5", dimColor: "#1e3a5f" }, // Buy
  { a1:  36, a2:   0, label: "S.Buy",   color: "#1976d2", dimColor: "#1e3a5f" }, // Strong Buy
] as const;

// Tick positions: zone boundaries + midpoints
const TICK_ANGLES = [180, 162, 144, 126, 108, 90, 72, 54, 36, 18, 0];

// Zone boundary labels
const BOUNDARY_LABELS = [
  { angle: 180, text: "−",  side: "left"   },
  { angle: 90,  text: "◆",  side: "center" },
  { angle: 0,   text: "+",  side: "right"  },
] as const;

// ── Elegant Gauge Component ───────────────────────────────────────────────────

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
  const score    = getScore(buy, sell, neutral);
  const rotateDeg = scoreToRotate(score);
  const active   = activeZone(signal);

  const height = size * VH / VW;

  // Unique gradient/filter IDs per gauge instance
  const shadowId  = `shadow-${id}`;
  const bevelId   = `bevel-${id}`;

  const needleTip = `${GCX},${GCY - NEEDLE_LEN}`;
  const needleR   = `${GCX + 4},${GCY}`;
  const needleL   = `${GCX - 4},${GCY}`;
  const cwR       = `${GCX + 3},${GCY + 16}`;
  const cwL       = `${GCX - 3},${GCY + 16}`;

  return (
    <svg viewBox={`0 0 ${VW} ${VH}`} width={size} height={height}
         role="img" aria-label={signalLabel(signal)} style={{ overflow: "visible" }}>
      <defs>
        {/* Needle drop-shadow */}
        <filter id={shadowId} x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0" dy="1" stdDeviation="2" floodColor="rgba(0,0,0,0.5)" />
        </filter>
        {/* Bevel for outer ring */}
        <filter id={bevelId} x="-5%" y="-5%" width="110%" height="110%">
          <feGaussianBlur in="SourceAlpha" stdDeviation="1.5" result="blur" />
          <feOffset dx="0" dy="1" in="blur" result="offset" />
          <feComposite in="SourceGraphic" in2="offset" operator="over" />
        </filter>
      </defs>

      {/* ── Outer decorative ring */}
      <path d={sectorPath(180, 0, R_OUT + 10, R_OUT + 5)}
        fill={p.isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)"}
        stroke={p.isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.10)"}
        strokeWidth="0.5" />

      {/* ── Zone sectors */}
      {ZONES.map((z, i) => {
        const isActive = i === active;
        return (
          <path
            key={z.label}
            d={sectorPath(z.a1, z.a2)}
            fill={isActive ? z.color : z.dimColor}
            opacity={isActive ? 1 : 0.45}
            style={{ transition: "fill 0.4s ease, opacity 0.4s ease" }}
          />
        );
      })}

      {/* ── Gauge face (inner circle fill) */}
      <path d={sectorPath(180, 0, R_IN - 1, 8)}
        fill={p.bgGauge}
      />

      {/* ── Tick marks at zone boundaries & midpoints */}
      {TICK_ANGLES.map(angle => {
        const isBoundary = angle % 36 === 0;
        const [x1, y1] = ptAt(isBoundary ? R_TIC - 4 : R_TIC + 6, angle);
        const [x2, y2] = ptAt(R_TIC_OUT, angle);
        return (
          <line key={angle} x1={x1} y1={y1} x2={x2} y2={y2}
            stroke={p.isDark ? "rgba(255,255,255,0.25)" : "rgba(0,0,0,0.20)"}
            strokeWidth={isBoundary ? 1.5 : 0.8}
            strokeLinecap="round" />
        );
      })}

      {/* ── Zone labels inside the band */}
      {ZONES.map((z, i) => {
        const midAngle = (z.a1 + z.a2) / 2;
        const labelR = (R_OUT + R_IN) / 2;
        const [lx, ly] = ptAt(labelR, midAngle);
        const isActive = i === active;
        return (
          <text key={z.label} x={lx} y={ly}
            fontSize="8.5" fontWeight={isActive ? "700" : "500"}
            fill={isActive ? "#fff" : "rgba(255,255,255,0.55)"}
            textAnchor="middle" dominantBaseline="middle"
            fontFamily="system-ui,sans-serif"
            style={{ transition: "font-weight 0.3s" }}>
            {z.label}
          </text>
        );
      })}

      {/* ── Score label inside the face */}
      <text x={GCX} y={GCY - NEEDLE_LEN * 0.38}
        fontSize="10" fill={p.txtDim}
        textAnchor="middle" dominantBaseline="middle"
        fontFamily="system-ui,sans-serif">
        {score >= 0
          ? `+${(score * 100).toFixed(0)}%`
          : `${(score * 100).toFixed(0)}%`}
      </text>

      {/* ── Animated needle */}
      <g
        style={{
          transformOrigin: `${GCX}px ${GCY}px`,
          transform: `rotate(${rotateDeg}deg)`,
          transition: "transform 0.85s cubic-bezier(0.34, 1.4, 0.64, 1)",
        }}
        filter={`url(#${shadowId})`}
      >
        {/* Main needle body */}
        <polygon
          points={`${needleTip} ${needleR} ${needleL}`}
          fill={p.needleFg}
          strokeWidth="0"
        />
        {/* Counterweight */}
        <polygon
          points={`${needleL} ${needleR} ${cwR} ${cwL}`}
          fill={signalColor(signal, p)}
          strokeWidth="0"
        />
      </g>

      {/* ── Center cap (sits on top of needle base) */}
      <circle cx={GCX} cy={GCY} r="10" fill={p.capBg}
        stroke={p.border} strokeWidth="1.5" />
      <circle cx={GCX} cy={GCY} r="4.5" fill={signalColor(signal, p)} />
    </svg>
  );
}

// ── Thin loading bar ───────────────────────────────────────────────────────────

function FetchBar({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <div className="absolute top-0 left-0 right-0 h-0.5 overflow-hidden z-10">
      <div className="h-full bg-indigo-500"
        style={{ width: "45%", animation: "fetchSlide 1.1s ease-in-out infinite" }} />
      <style>{`@keyframes fetchSlide{0%{transform:translateX(-110%)}100%{transform:translateX(350%)}}`}</style>
    </div>
  );
}

// ── Timeframe selector ─────────────────────────────────────────────────────────

const TIMEFRAMES = [
  { key: "1m",  label: "1m"  },
  { key: "5m",  label: "5m"  },
  { key: "15m", label: "15m" },
  { key: "30m", label: "30m" },
  { key: "1h",  label: "1h"  },
  { key: "2h",  label: "2h"  },
  { key: "4h",  label: "4h"  },
  { key: "1d",  label: "1D"  },
  { key: "1w",  label: "1W"  },
  { key: "1mo", label: "1M"  },
] as const;
type Interval = typeof TIMEFRAMES[number]["key"];

// ── Indicator table ────────────────────────────────────────────────────────────

function IndicatorTable({ section, title, isFetching }: {
  section: TechSection; title: string; isFetching: boolean;
}) {
  const p = usePalette();
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? section.indicators : section.indicators.slice(0, 4);

  return (
    <div className="relative overflow-hidden rounded-xl"
         style={{ background: p.bgCard, border: `1px solid ${p.border}` }}>
      <FetchBar visible={isFetching} />
      <button className="w-full flex items-center justify-between px-4 py-3"
              onClick={() => setExpanded(e => !e)}>
        <span className="text-xs font-semibold" style={{ color: p.txtMain }}>{title}</span>
        <span className="text-xs" style={{ color: p.txtDim }}>{expanded ? "▲" : "▼"}</span>
      </button>
      <table className="w-full text-xs">
        <thead>
          <tr style={{ borderTop: `1px solid ${p.border}` }}>
            {["Name", "Value", "Action"].map((h, i) => (
              <th key={h} className={`px-3 py-1.5 font-medium ${i > 0 ? "text-right" : "text-left"}`}
                  style={{ color: p.txtDim }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shown.map((row, i) => (
            <tr key={row.name}
                style={{ borderTop: `1px solid ${p.border}`, background: i % 2 ? p.bgHover : "transparent" }}>
              <td className="px-3 py-2" style={{ color: p.txtMain }}>{row.name}</td>
              <td className="px-3 py-2 text-right tabular-nums" style={{ color: p.txtDim }}>
                {row.value != null ? row.value.toFixed(2) : "—"}
              </td>
              <td className="px-3 py-2 text-right font-semibold" style={{ color: actionColor(row.action, p) }}>
                {row.action === "BUY" ? "Buy" : row.action === "SELL" ? "Sell" : "Neutral"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {section.indicators.length > 4 && (
        <button onClick={() => setExpanded(e => !e)}
                className="w-full text-xs py-2"
                style={{ color: p.txtDim, borderTop: `1px solid ${p.border}` }}>
          {expanded ? "Show less" : `Show all ${section.indicators.length}`}
        </button>
      )}
    </div>
  );
}

// ── Section panel (gauge + table) ─────────────────────────────────────────────

function SectionPanel({ section, title, isFetching }: {
  section: TechSection; title: string; isFetching: boolean;
}) {
  const p = usePalette();
  const id = title.toLowerCase().replace(/\s/g, "-");

  return (
    <div className="space-y-3">
      <div className="relative overflow-hidden rounded-xl p-5 flex flex-col items-center gap-2"
           style={{ background: p.bgCard, border: `1px solid ${p.border}` }}>
        <FetchBar visible={isFetching} />
        <span className="text-xs font-semibold tracking-wide" style={{ color: p.txtMain }}>{title}</span>
        <Gauge signal={section.signal} buy={section.buy} sell={section.sell} neutral={section.neutral}
               size={186} id={id} />
        <span className="text-sm font-bold" style={{ color: signalColor(section.signal, p) }}>
          {signalLabel(section.signal)}
        </span>
        <div className="flex gap-5 mt-0.5">
          {([ ["Sell", section.sell, p.txtSell], ["Neutral", section.neutral, p.txtNeu], ["Buy", section.buy, p.txtBuy] ] as const).map(([l, v, c]) => (
            <div key={l} className="text-center">
              <div className="text-[10px] font-medium uppercase tracking-wider" style={{ color: c }}>{l}</div>
              <div className="text-lg font-bold" style={{ color: p.txtMain }}>{v}</div>
            </div>
          ))}
        </div>
      </div>
      <IndicatorTable section={section} title={title} isFetching={isFetching} />
    </div>
  );
}

// ── Pivot table ────────────────────────────────────────────────────────────────

type PivotType = "classic" | "fibonacci" | "camarilla" | "woodie" | "dm";

function PivotTable({ pivots, isFetching }: { pivots: TSummary["pivots"]; isFetching: boolean }) {
  const p = usePalette();
  const [active, setActive] = useState<PivotType>("classic");
  const data = pivots[active];
  const levels = "r3" in data
    ? (["R3","R2","R1","P","S1","S2","S3"] as string[]).map(l => ({ label: l, val: (data as Record<string,number>)[l.toLowerCase()] }))
    : (["R1","P","S1"] as string[]).map(l => ({ label: l, val: (data as Record<string,number>)[l.toLowerCase()] }));

  return (
    <div className="relative overflow-hidden rounded-xl"
         style={{ background: p.bgCard, border: `1px solid ${p.border}` }}>
      <FetchBar visible={isFetching} />
      <div className="px-4 py-3" style={{ borderBottom: `1px solid ${p.border}` }}>
        <span className="text-xs font-semibold" style={{ color: p.txtMain }}>Pivots</span>
      </div>
      <div className="flex" style={{ borderBottom: `1px solid ${p.border}` }}>
        {(["classic","fibonacci","camarilla","woodie","dm"] as PivotType[]).map(t => (
          <button key={t} onClick={() => setActive(t)}
            className="flex-1 py-2 text-[11px] font-medium capitalize transition-colors"
            style={{
              color: active === t ? p.txtMain : p.txtDim,
              borderBottom: active === t ? "2px solid #4b9fe1" : "2px solid transparent",
            }}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr>
            {["Pivot","Level"].map((h, i) => (
              <th key={h} className={`px-4 py-2 font-medium ${i > 0 ? "text-right" : "text-left"}`}
                  style={{ color: p.txtDim }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {levels.map(({ label, val }) => {
            const isP = label === "P";
            const isR = label.startsWith("R");
            return (
              <tr key={label}
                  style={{ borderTop: `1px solid ${p.border}`, background: isP ? p.bgHover : "transparent" }}>
                <td className="px-4 py-2 font-semibold"
                    style={{ color: isR ? p.txtSell : label.startsWith("S") ? p.txtBuy : p.txtMain }}>
                  {label}
                </td>
                <td className="px-4 py-2 text-right tabular-nums" style={{ color: p.txtMain }}>
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

// ── Main component ─────────────────────────────────────────────────────────────

export default function TechnicalSummary({ symbol }: { symbol: string }) {
  const p = usePalette();
  const [interval, setInterval] = useState<Interval>("1d");

  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ["tech-summary", symbol, interval],
    queryFn:  () => api.stockTechnicalSummary(symbol, interval),
    enabled:  !!symbol,
    staleTime: 5 * 60 * 1000,
    retry: 1,
    // Keep showing previous data while new interval loads — prevents page-reload flash
    placeholderData: keepPreviousData,
  });

  if (isLoading) {
    return (
      <div className="rounded-xl p-6 space-y-4" style={{ background: p.bgPage }}>
        {[1,2,3].map(i => (
          <div key={i} className="h-28 rounded-xl animate-pulse" style={{ background: p.bgCard }} />
        ))}
      </div>
    );
  }

  if (error || !data || (data as { error?: string }).error) {
    return (
      <div className="rounded-xl p-6 text-center text-sm" style={{ background: p.bgPage, color: p.txtDim }}>
        Technical summary unavailable for {symbol}.
      </div>
    );
  }

  const { summary, oscillators, movingAverages, pivots } = data;

  return (
    <div className="rounded-xl p-4 space-y-4" style={{ background: p.bgPage }}
         data-testid="technical-summary">

      {/* Timeframe selector */}
      <div className="flex flex-wrap gap-1">
        {TIMEFRAMES.map(tf => {
          const isActive = interval === tf.key;
          return (
            <button key={tf.key} onClick={() => setInterval(tf.key)}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg transition-all duration-200"
              style={{
                background: isActive
                  ? (p.isDark ? "#2a2e39" : "#e2e8f0")
                  : "transparent",
                color:      isActive ? p.txtMain : p.txtDim,
                border:     isActive
                  ? `1px solid ${p.isDark ? "#3a3f50" : "#cbd5e1"}`
                  : "1px solid transparent",
              }}>
              {tf.label}
            </button>
          );
        })}
      </div>

      {/* ── Large summary gauge ── */}
      <div className="relative overflow-hidden rounded-xl p-5 flex flex-col items-center gap-3"
           style={{ background: p.bgCard, border: `1px solid ${p.border}` }}>
        <FetchBar visible={isFetching} />
        <span className="text-sm font-semibold tracking-wide" style={{ color: p.txtMain }}>
          Indicators' Summary
        </span>
        <Gauge signal={summary.signal} buy={summary.buy} sell={summary.sell} neutral={summary.neutral}
               size={256} id="summary" />
        <span className="text-xl font-bold tracking-tight"
              style={{ color: signalColor(summary.signal, p) }}>
          {signalLabel(summary.signal)}
        </span>
        <div className="flex gap-10">
          {([ ["Sell", summary.sell, p.txtSell], ["Neutral", summary.neutral, p.txtNeu], ["Buy", summary.buy, p.txtBuy] ] as const).map(([l, v, c]) => (
            <div key={l} className="text-center">
              <div className="text-xs font-medium uppercase tracking-wider" style={{ color: c }}>{l}</div>
              <div className="text-2xl font-bold" style={{ color: p.txtMain }}>{v}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Oscillators + Moving Averages ── */}
      <div className="grid md:grid-cols-2 gap-4">
        <SectionPanel section={oscillators}    title="Oscillators"      isFetching={isFetching} />
        <SectionPanel section={movingAverages} title="Moving Averages"  isFetching={isFetching} />
      </div>

      {/* ── Pivots ── */}
      <PivotTable pivots={pivots} isFetching={isFetching} />
    </div>
  );
}
