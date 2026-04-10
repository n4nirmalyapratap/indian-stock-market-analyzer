import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { TechSignal, TechAction, TechSection, TechnicalSummary as TSummary } from "@/lib/api";

// ── Palette ───────────────────────────────────────────────────────────────────
const BG_PAGE  = "#131722";
const BG_CARD  = "#1e222d";
const BG_ROW   = "#1e222d";
const BG_HOVER = "#252933";
const BORDER   = "#2a2e39";
const TXT_DIM  = "#787b86";
const TXT_SELL = "#ef5350";
const TXT_BUY  = "#4b9fe1";
const TXT_NEU  = "#787b86";
const TXT_WHITE = "#d1d4dc";

// ── Signal helpers ────────────────────────────────────────────────────────────

function signalLabel(s: TechSignal): string {
  return s === "STRONG_BUY" ? "Strong buy"
    : s === "BUY" ? "Buy"
    : s === "STRONG_SELL" ? "Strong sell"
    : s === "SELL" ? "Sell"
    : "Neutral";
}

function signalColor(s: TechSignal): string {
  return s === "STRONG_BUY" || s === "BUY" ? TXT_BUY
    : s === "STRONG_SELL" || s === "SELL" ? TXT_SELL
    : TXT_NEU;
}

function actionColor(a: TechAction): string {
  return a === "BUY" ? TXT_BUY : a === "SELL" ? TXT_SELL : TXT_NEU;
}

function signalScore(buy: number, sell: number, neutral: number): number {
  const total = buy + sell + neutral;
  if (total === 0) return 0;
  return Math.min(1, Math.max(-1, (buy - sell) / total));
}

// ── Gauge SVG ─────────────────────────────────────────────────────────────────

function Gauge({ signal, buy, sell, neutral, size = 220 }: {
  signal: TechSignal; buy: number; sell: number; neutral: number; size?: number;
}) {
  const score = signalScore(buy, sell, neutral);
  // Map score -1..+1 → angle 180°..0° (sweeping through top at 90°)
  const angleDeg = 90 - score * 90;
  const angleRad = (angleDeg * Math.PI) / 180;

  const cx = 110; const cy = 110; const r = 80;
  const nLen = 60;
  const nx = cx + nLen * Math.cos(angleRad);
  const ny = cy - nLen * Math.sin(angleRad);

  const color = signalColor(signal);

  return (
    <svg viewBox="0 0 220 130" width={size} height={size * 130 / 220} aria-label={`Gauge: ${signalLabel(signal)}`}>
      <defs>
        <linearGradient id={`g-sell-${size}`} x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#ef4444" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#ef4444" stopOpacity="0.4" />
        </linearGradient>
        <linearGradient id={`g-buy-${size}`} x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#4b9fe1" stopOpacity="0.3" />
          <stop offset="100%" stopColor="#4b9fe1" stopOpacity="0.8" />
        </linearGradient>
      </defs>

      {/* Full arc background */}
      <path
        d="M 30 110 A 80 80 0 0 1 190 110"
        fill="none" stroke={BORDER} strokeWidth="18" strokeLinecap="round"
      />
      {/* Sell arc (left half: 180°→90°) */}
      <path
        d="M 30 110 A 80 80 0 0 1 110 30"
        fill="none" stroke="#ef4444" strokeWidth="18" strokeLinecap="round" strokeOpacity="0.6"
      />
      {/* Buy arc (right half: 90°→0°) */}
      <path
        d="M 110 30 A 80 80 0 0 1 190 110"
        fill="none" stroke="#4b9fe1" strokeWidth="18" strokeLinecap="round" strokeOpacity="0.3"
      />

      {/* Zone labels */}
      <text x="14" y="128" fontSize="9" fill={TXT_SELL} textAnchor="middle" fontFamily="sans-serif">Strong</text>
      <text x="14" y="138" fontSize="9" fill={TXT_SELL} textAnchor="middle" fontFamily="sans-serif">sell</text>
      <text x="57" y="76" fontSize="9" fill={TXT_SELL} textAnchor="middle" fontFamily="sans-serif">Sell</text>
      <text x="110" y="22" fontSize="9" fill={TXT_NEU} textAnchor="middle" fontFamily="sans-serif">Neutral</text>
      <text x="163" y="76" fontSize="9" fill={TXT_DIM} textAnchor="middle" fontFamily="sans-serif">Buy</text>
      <text x="206" y="128" fontSize="9" fill={TXT_DIM} textAnchor="middle" fontFamily="sans-serif">Strong</text>
      <text x="206" y="138" fontSize="9" fill={TXT_DIM} textAnchor="middle" fontFamily="sans-serif">buy</text>

      {/* Needle */}
      <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="white" strokeWidth="2.5" strokeLinecap="round" />
      <circle cx={cx} cy={cy} r="5" fill="white" />
    </svg>
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

function IndicatorTable({ section, title }: { section: TechSection; title: string }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? section.indicators : section.indicators.slice(0, 4);

  return (
    <div style={{ background: BG_CARD, border: `1px solid ${BORDER}` }}
         className="rounded-xl overflow-hidden">
      <button
        className="w-full flex items-center gap-2 px-4 py-3 text-left hover:opacity-80 transition-opacity"
        onClick={() => setExpanded(e => !e)}
      >
        <span style={{ color: TXT_WHITE }} className="text-sm font-semibold">{title}</span>
        <span style={{ color: TXT_DIM }} className="text-xs">›</span>
      </button>
      <table className="w-full text-xs">
        <thead>
          <tr style={{ borderTop: `1px solid ${BORDER}` }}>
            <th style={{ color: TXT_DIM }} className="text-left px-4 py-2 font-medium">Name</th>
            <th style={{ color: TXT_DIM }} className="text-right px-4 py-2 font-medium">Value</th>
            <th style={{ color: TXT_DIM }} className="text-right px-4 py-2 font-medium">Action</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((row, i) => (
            <tr
              key={row.name}
              style={{
                borderTop: `1px solid ${BORDER}`,
                background: i % 2 === 0 ? "transparent" : BG_HOVER,
              }}
              className="transition-colors"
            >
              <td style={{ color: TXT_WHITE }} className="px-4 py-2.5">{row.name}</td>
              <td style={{ color: TXT_DIM }} className="px-4 py-2.5 text-right tabular-nums">
                {row.value != null ? row.value.toFixed(2) : "—"}
              </td>
              <td className="px-4 py-2.5 text-right font-semibold"
                  style={{ color: actionColor(row.action) }}>
                {row.action === "NEUTRAL" ? "Neutral" : row.action === "BUY" ? "Buy" : "Sell"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {section.indicators.length > 4 && (
        <button
          onClick={() => setExpanded(e => !e)}
          style={{ color: TXT_DIM, borderTop: `1px solid ${BORDER}` }}
          className="w-full text-xs py-2 hover:opacity-80 transition-opacity"
        >
          {expanded ? "Show less ▲" : `Show all ${section.indicators.length} indicators ▼`}
        </button>
      )}
    </div>
  );
}

// ── Section panel (gauge + counts + table) ────────────────────────────────────

function SectionPanel({ section, title }: { section: TechSection; title: string }) {
  return (
    <div className="space-y-3">
      {/* Sub-gauge */}
      <div style={{ background: BG_CARD, border: `1px solid ${BORDER}` }}
           className="rounded-xl p-4 flex flex-col items-center gap-1">
        <span style={{ color: TXT_WHITE }} className="text-sm font-semibold mb-1">{title}</span>
        <Gauge signal={section.signal} buy={section.buy} sell={section.sell} neutral={section.neutral} size={180} />
        <span className="text-base font-bold mt-1" style={{ color: signalColor(section.signal) }}>
          {signalLabel(section.signal)}
        </span>
        <div className="flex gap-6 mt-2">
          {[["Sell", section.sell, TXT_SELL], ["Neutral", section.neutral, TXT_NEU], ["Buy", section.buy, TXT_BUY]].map(([l, v, c]) => (
            <div key={l as string} className="text-center">
              <div style={{ color: c as string }} className="text-xs font-medium">{l as string}</div>
              <div style={{ color: TXT_WHITE }} className="text-lg font-bold">{v as number}</div>
            </div>
          ))}
        </div>
      </div>
      {/* Table */}
      <IndicatorTable section={section} title={title} />
    </div>
  );
}

// ── Pivot table ───────────────────────────────────────────────────────────────

type PivotType = "classic" | "fibonacci" | "camarilla" | "woodie" | "dm";

function PivotTable({ pivots }: { pivots: TSummary["pivots"] }) {
  const [active, setActive] = useState<PivotType>("classic");

  const data = pivots[active];
  const fullLevels = "r3" in data
    ? [
        { label: "R3", val: (data as any).r3 },
        { label: "R2", val: (data as any).r2 },
        { label: "R1", val: (data as any).r1 },
        { label: "P",  val: data.p },
        { label: "S1", val: (data as any).s1 },
        { label: "S2", val: (data as any).s2 },
        { label: "S3", val: (data as any).s3 },
      ]
    : [
        { label: "R1", val: (data as any).r1 },
        { label: "P",  val: data.p },
        { label: "S1", val: (data as any).s1 },
      ];

  const pivotTabs: PivotType[] = ["classic", "fibonacci", "camarilla", "woodie", "dm"];

  return (
    <div style={{ background: BG_CARD, border: `1px solid ${BORDER}` }}
         className="rounded-xl overflow-hidden">
      <div style={{ borderBottom: `1px solid ${BORDER}` }} className="px-4 py-3 flex items-center gap-2">
        <span style={{ color: TXT_WHITE }} className="text-sm font-semibold">Pivots</span>
        <span style={{ color: TXT_DIM }} className="text-xs">›</span>
      </div>

      {/* Tab row */}
      <div style={{ borderBottom: `1px solid ${BORDER}` }} className="flex">
        {pivotTabs.map(t => (
          <button
            key={t}
            onClick={() => setActive(t)}
            className="flex-1 py-2 text-xs font-medium capitalize transition-colors"
            style={{
              color: active === t ? TXT_WHITE : TXT_DIM,
              borderBottom: active === t ? `2px solid ${TXT_BUY}` : "2px solid transparent",
              background: "transparent",
            }}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      <table className="w-full text-xs">
        <thead>
          <tr>
            <th style={{ color: TXT_DIM }} className="text-left px-4 py-2 font-medium">Pivot</th>
            <th style={{ color: TXT_DIM }} className="text-right px-4 py-2 font-medium">Level</th>
          </tr>
        </thead>
        <tbody>
          {fullLevels.map(({ label, val }, i) => {
            const isP       = label === "P";
            const isSupport = label.startsWith("S");
            const isResist  = label.startsWith("R");
            return (
              <tr
                key={label}
                style={{
                  borderTop: `1px solid ${BORDER}`,
                  background: isP ? BG_HOVER : "transparent",
                }}
              >
                <td className="px-4 py-2.5 font-semibold"
                    style={{ color: isResist ? TXT_SELL : isSupport ? TXT_BUY : TXT_WHITE }}>
                  {label}
                </td>
                <td style={{ color: TXT_WHITE }} className="px-4 py-2.5 text-right tabular-nums">
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
  const [interval, setInterval] = useState<Interval>("1d");

  const { data, isLoading, error } = useQuery({
    queryKey: ["tech-summary", symbol, interval],
    queryFn: () => api.stockTechnicalSummary(symbol, interval),
    enabled: !!symbol,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  if (isLoading) {
    return (
      <div style={{ background: BG_PAGE }} className="rounded-xl p-6 space-y-4">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-24 rounded-xl animate-pulse" style={{ background: BG_CARD }} />
        ))}
      </div>
    );
  }

  if (error || !data || (data as any).error) {
    return (
      <div style={{ background: BG_PAGE, color: TXT_DIM }} className="rounded-xl p-6 text-center text-sm">
        Technical summary unavailable for {symbol}.
      </div>
    );
  }

  const { summary, oscillators, movingAverages, pivots } = data;

  return (
    <div style={{ background: BG_PAGE }} className="rounded-xl p-4 space-y-5" data-testid="technical-summary">

      {/* Description */}
      <div>
        <h3 style={{ color: TXT_WHITE }} className="font-semibold text-sm mb-1">Indicators' summary</h3>
        <p style={{ color: TXT_DIM }} className="text-xs leading-relaxed">
          Technical analysis overview for the selected timeframe. Includes key data from
          moving averages, oscillators, and pivots — all summed up in the Summary gauge.
        </p>
      </div>

      {/* Timeframe selector */}
      <div className="flex flex-wrap gap-px" style={{ borderBottom: `1px solid ${BORDER}`, paddingBottom: "2px" }}>
        {TIMEFRAMES.map(tf => (
          <button
            key={tf.key}
            onClick={() => setInterval(tf.key)}
            className="px-3 py-1.5 text-xs font-medium rounded transition-colors"
            style={{
              background:   interval === tf.key ? "#2a2e39" : "transparent",
              color:        interval === tf.key ? TXT_WHITE  : TXT_DIM,
              border: "none",
            }}
          >
            {tf.label}
          </button>
        ))}
      </div>

      {/* Summary gauge */}
      <div style={{ background: BG_CARD, border: `1px solid ${BORDER}` }}
           className="rounded-xl p-6 flex flex-col items-center gap-2">
        <span style={{ color: TXT_WHITE }} className="text-sm font-semibold">Summary</span>
        <Gauge signal={summary.signal} buy={summary.buy} sell={summary.sell} neutral={summary.neutral} size={240} />
        <span className="text-xl font-bold" style={{ color: signalColor(summary.signal) }}>
          {signalLabel(summary.signal)}
        </span>
        <div className="flex gap-8 mt-1">
          {[["Sell", summary.sell, TXT_SELL], ["Neutral", summary.neutral, TXT_NEU], ["Buy", summary.buy, TXT_BUY]].map(([l, v, c]) => (
            <div key={l as string} className="text-center">
              <div style={{ color: c as string }} className="text-xs font-medium">{l as string}</div>
              <div style={{ color: TXT_WHITE }} className="text-xl font-bold">{v as number}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Oscillators + Moving Averages side by side */}
      <div className="grid md:grid-cols-2 gap-4">
        <SectionPanel section={oscillators}    title="Oscillators" />
        <SectionPanel section={movingAverages} title="Moving Averages" />
      </div>

      {/* Pivots */}
      <PivotTable pivots={pivots} />
    </div>
  );
}
