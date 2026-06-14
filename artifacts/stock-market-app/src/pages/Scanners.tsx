import { useState, useCallback, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type ConditionSide, type Condition, type Scanner, type ScanResult, type ScannerCreateInput } from "@/lib/api";
import {
  Play, Plus, Trash2, Save, TrendingUp, TrendingDown,
  Zap, AlertCircle, CheckCircle2, X, Copy, Edit2,
  Filter, BarChart2, Loader2, Target,
} from "lucide-react";
import ChartButton from "@/components/ChartButton";
import DataFreshness from "@/components/DataFreshness";
import { pickMeta, marketDataQueryOptions } from "@/lib/marketData";
import { HiddenGemScoreBadge, ExitPlanButton } from "@/components/scanners/HiddenGemsBits";
import { useScanJob, type ScanJobProgress } from "@/hooks/useScanJob";

// ─── Indicator Definitions ───────────────────────────────────────────────────
//
// CategoryColor is the SINGLE source of truth for which colors the
// indicator-picker recognises. Adding a new color requires three
// coordinated touch-points and the compiler enforces all three:
//   1. Add the literal here     → forces step 2 (record exhaustiveness)
//   2. Add the row in CAT_COLORS → forces nothing missed at runtime
//   3. Use it in INDICATOR_GROUPS color field → still typesafe
// Without this union, a typo like `color: "pink"` silently produced an
// undefined CAT_COLORS lookup and crashed render with "Cannot read
// properties of undefined (reading 'bg')".
type CategoryColor =
  | "blue" | "cyan" | "green" | "purple" | "orange" | "red"
  | "teal" | "pink" | "gray";

interface IndicatorPickerItem {
  value:         string;
  label:         string;
  hasPeriod:     boolean;
  defaultPeriod?: number;
  isNumber?:     boolean;
}

interface IndicatorGroup {
  label:  string;
  color:  CategoryColor;
  items:  IndicatorPickerItem[];
}

const INDICATOR_GROUPS: IndicatorGroup[] = [
  { label: "Price",           color: "blue",   items: [
    { value: "CLOSE",       label: "Close",          hasPeriod: false },
    { value: "OPEN",        label: "Open",           hasPeriod: false },
    { value: "HIGH",        label: "High",           hasPeriod: false },
    { value: "LOW",         label: "Low",            hasPeriod: false },
    { value: "PREV_CLOSE",  label: "Prev Close",     hasPeriod: false },
    { value: "CHANGE_PCT",  label: "Change %",       hasPeriod: false },
  ]},
  { label: "Volume",          color: "cyan",   items: [
    { value: "VOLUME",            label: "Volume",                hasPeriod: false },
    { value: "AVG_VOLUME",        label: "Avg Volume",            hasPeriod: true,  defaultPeriod: 20 },
    { value: "VOLUME_RATIO",      label: "Volume Ratio %",        hasPeriod: false },
    // New Volume-category helpers — pair with VOLUME or CLOSE on the
    // other side of the condition. e.g.
    //   VOLUME > HIGHEST_VOLUME(10)   → today is heaviest of 10 days
    //   VOLUME_ZSCORE(20) gte 2       → ≥ 2σ above 20-day mean
    //   CLOSE > HIGHEST_HIGH(20)      → 20-day price breakout
    //   WICK_RATIO gt 50              → long-wick candle (climax / reversal)
    //   HIGHER_LOWS_COUNT(5) gte 4    → 4 of last 5 bars made higher lows
    //   VOLUME_TREND_UP(5) eq 1       → 5-bar volume trend is rising
    { value: "HIGHEST_VOLUME",    label: "Highest Volume (N)",    hasPeriod: true,  defaultPeriod: 10 },
    { value: "HIGHEST_HIGH",      label: "Highest High (N)",      hasPeriod: true,  defaultPeriod: 20 },
    { value: "LOWEST_LOW",        label: "Lowest Low (N)",        hasPeriod: true,  defaultPeriod: 20 },
    { value: "VOLUME_ZSCORE",     label: "Volume Z-Score (N)",    hasPeriod: true,  defaultPeriod: 20 },
    { value: "WICK_RATIO",        label: "Wick Ratio %",          hasPeriod: false },
    { value: "HIGHER_LOWS_COUNT", label: "Higher Lows Count (N)", hasPeriod: true,  defaultPeriod: 5 },
    { value: "VOLUME_TREND_UP",   label: "Volume Trend Up (N)",   hasPeriod: true,  defaultPeriod: 5 },
  ]},
  { label: "Moving Averages", color: "green",  items: [
    { value: "EMA", label: "EMA", hasPeriod: true, defaultPeriod: 20 },
    { value: "SMA", label: "SMA", hasPeriod: true, defaultPeriod: 20 },
  ]},
  { label: "Oscillators",     color: "purple", items: [
    { value: "RSI",         label: "RSI",         hasPeriod: true, defaultPeriod: 14 },
    { value: "MACD",        label: "MACD Line",   hasPeriod: false },
    { value: "MACD_SIGNAL", label: "MACD Signal", hasPeriod: false },
    { value: "MACD_HIST",   label: "MACD Hist",   hasPeriod: false },
  ]},
  { label: "Bollinger Bands", color: "orange", items: [
    { value: "BB_UPPER", label: "BB Upper",  hasPeriod: true, defaultPeriod: 20 },
    { value: "BB_MID",   label: "BB Middle", hasPeriod: true, defaultPeriod: 20 },
    { value: "BB_LOWER", label: "BB Lower",  hasPeriod: true, defaultPeriod: 20 },
  ]},
  { label: "Volatility",      color: "red",    items: [
    { value: "ATR", label: "ATR", hasPeriod: true, defaultPeriod: 14 },
  ]},
  { label: "Market",          color: "teal",   items: [
    { value: "HIGH_52W",     label: "52W High",        hasPeriod: false },
    { value: "LOW_52W",      label: "52W Low",         hasPeriod: false },
    { value: "PCT_52W_HIGH", label: "% from 52W High", hasPeriod: false },
    { value: "PCT_52W_LOW",  label: "% from 52W Low",  hasPeriod: false },
  ]},
  // Candle-pattern boolean indicators — return 1 if today's bar
  // (and the prior bar for two-bar patterns) matches the shape, else 0.
  // Use with operator `eq` and value 1 — e.g.
  //   BULLISH_ENGULFING eq 1 AND VOLUME_RATIO > 150
  // Fundamental indicators — sourced from Yahoo Finance `info` dict,
  // cached 12h on the backend. First scan of any universe that uses
  // these is slow (~30-90s for NIFTY100) while the cache warms;
  // subsequent scans are instant.
  { label: "Fundamentals",    color: "purple", items: [
    { value: "PE_RATIO",            label: "P/E Ratio",              hasPeriod: false },
    { value: "PB_RATIO",            label: "P/B Ratio",              hasPeriod: false },
    { value: "PEG_RATIO",           label: "PEG Ratio",              hasPeriod: false },
    { value: "ROE",                 label: "Return on Equity (%)",   hasPeriod: false },
    { value: "ROCE",                label: "Return on Capital (%)",  hasPeriod: false },
    { value: "DEBT_TO_EQUITY",      label: "Debt-to-Equity",         hasPeriod: false },
    { value: "MARKET_CAP_CR",       label: "Market Cap (₹ Cr)",      hasPeriod: false },
    { value: "PROFIT_MARGIN",       label: "Net Profit Margin (%)",  hasPeriod: false },
    { value: "REVENUE_GROWTH_YOY",  label: "Revenue Growth YoY (%)", hasPeriod: false },
    { value: "EARNINGS_GROWTH_YOY", label: "EPS Growth YoY (%)",     hasPeriod: false },
    { value: "FCF_YIELD",           label: "FCF Yield (%)",          hasPeriod: false },
  ]},
  { label: "Patterns",        color: "pink",   items: [
    { value: "BULLISH_ENGULFING", label: "Bullish Engulfing",  hasPeriod: false },
    { value: "BEARISH_ENGULFING", label: "Bearish Engulfing",  hasPeriod: false },
    { value: "BULLISH_HARAMI",    label: "Bullish Harami",     hasPeriod: false },
    { value: "BEARISH_HARAMI",    label: "Bearish Harami",     hasPeriod: false },
    { value: "HAMMER",            label: "Hammer",             hasPeriod: false },
    { value: "INVERTED_HAMMER",   label: "Inverted Hammer",    hasPeriod: false },
    { value: "SHOOTING_STAR",     label: "Shooting Star",      hasPeriod: false },
    { value: "HANGING_MAN",       label: "Hanging Man",        hasPeriod: false },
    { value: "DOJI",              label: "Doji",               hasPeriod: false },
    { value: "DRAGONFLY_DOJI",    label: "Dragonfly Doji",     hasPeriod: false },
    { value: "GRAVESTONE_DOJI",   label: "Gravestone Doji",    hasPeriod: false },
    { value: "BULLISH_MARUBOZU",  label: "Bullish Marubozu",   hasPeriod: false },
    { value: "BEARISH_MARUBOZU",  label: "Bearish Marubozu",   hasPeriod: false },
    { value: "SPINNING_TOP",      label: "Spinning Top",       hasPeriod: false },
    { value: "INSIDE_BAR",        label: "Inside Bar",         hasPeriod: false },
    { value: "OUTSIDE_BAR",       label: "Outside Bar",        hasPeriod: false },
    { value: "PIERCING_LINE",     label: "Piercing Line",      hasPeriod: false },
    { value: "DARK_CLOUD_COVER",  label: "Dark Cloud Cover",   hasPeriod: false },
    { value: "TWEEZER_BOTTOM",    label: "Tweezer Bottom",     hasPeriod: false },
    { value: "TWEEZER_TOP",       label: "Tweezer Top",        hasPeriod: false },
  ]},
  { label: "Constant Value",  color: "gray",   items: [
    { value: "NUMBER", label: "Number", hasPeriod: false, isNumber: true },
  ]},
];

interface IndicatorItem {
  value: string; label: string; hasPeriod: boolean;
  defaultPeriod?: number; isNumber?: boolean;
  group: string; color: string;
}
const ALL_INDICATORS: IndicatorItem[] = INDICATOR_GROUPS.flatMap(g =>
  g.items.map(i => ({ ...i, group: g.label, color: g.color }))
);

// Color map for indicator categories. Typed as `Record<CategoryColor, …>`
// so the compiler refuses both directions of drift:
//   • Missing a key (e.g. forget to add the "pink" row here after
//     widening CategoryColor)  → TS2741 compile error
//   • Adding an extra key not in CategoryColor                       → TS2353 compile error
// Crashes like "Cannot read properties of undefined (reading 'bg')"
// are now impossible to ship as a single-file change.
interface ColorClasses { bg: string; text: string; border: string }
const CAT_COLORS: Record<CategoryColor, ColorClasses> = {
  blue:   { bg: "bg-blue-50",   text: "text-blue-700",   border: "border-blue-200"   },
  cyan:   { bg: "bg-cyan-50",   text: "text-cyan-700",   border: "border-cyan-200"   },
  green:  { bg: "bg-green-50",  text: "text-green-700",  border: "border-green-200"  },
  purple: { bg: "bg-purple-50", text: "text-purple-700", border: "border-purple-200" },
  orange: { bg: "bg-orange-50", text: "text-orange-700", border: "border-orange-200" },
  red:    { bg: "bg-red-50",    text: "text-red-700",    border: "border-red-200"    },
  teal:   { bg: "bg-teal-50",   text: "text-teal-700",   border: "border-teal-200"   },
  pink:   { bg: "bg-pink-50",   text: "text-pink-700",   border: "border-pink-200"   },
  gray:   { bg: "bg-gray-50",   text: "text-gray-700",   border: "border-gray-200"   },
};

// Defensive runtime helper — paranoid backstop in case data flowing in
// from the server (saved scanners, custom indicator groups) ever ships
// a color string that isn't in CategoryColor. Compile-time is the real
// safety net; this just prevents a single bad row crashing the page.
const FALLBACK_COLOR = CAT_COLORS.gray;
function catColor(name: string | undefined): ColorClasses {
  if (!name) return FALLBACK_COLOR;
  return CAT_COLORS[name as CategoryColor] || FALLBACK_COLOR;
}

const OPERATORS = [
  { value: "gt",            label: "Greater than",    short: ">"  },
  { value: "gte",           label: "Greater or equal",short: "≥"  },
  { value: "lt",            label: "Less than",       short: "<"  },
  { value: "lte",           label: "Less or equal",   short: "≤"  },
  { value: "eq",            label: "Equal to",        short: "="  },
  { value: "crosses_above", label: "Crosses above",   short: "↗"  },
  { value: "crosses_below", label: "Crosses below",   short: "↘"  },
];

// Quick-add condition templates
const TEMPLATES = [
  { label: "RSI Oversold",       conditions: [{ left: { type:"indicator", indicator:"RSI", period:14 }, operator:"lt", right: { type:"number", value:35 } }] },
  { label: "RSI Overbought",     conditions: [{ left: { type:"indicator", indicator:"RSI", period:14 }, operator:"gt", right: { type:"number", value:70 } }] },
  { label: "Above EMA 50",       conditions: [{ left: { type:"indicator", indicator:"CLOSE" }, operator:"gt", right: { type:"indicator", indicator:"EMA", period:50 } }] },
  { label: "EMA Cross 20/50",    conditions: [{ left: { type:"indicator", indicator:"EMA", period:20 }, operator:"crosses_above", right: { type:"indicator", indicator:"EMA", period:50 } }] },
  { label: "MACD Bullish",       conditions: [{ left: { type:"indicator", indicator:"MACD" }, operator:"crosses_above", right: { type:"indicator", indicator:"MACD_SIGNAL" } }] },
  { label: "Volume Spike 2×",    conditions: [{ left: { type:"indicator", indicator:"VOLUME_RATIO" }, operator:"gte", right: { type:"number", value:200 } }] },
  { label: "Near 52W High",      conditions: [{ left: { type:"indicator", indicator:"PCT_52W_HIGH" }, operator:"gte", right: { type:"number", value:-5 } }] },
  { label: "BB Lower Bounce",    conditions: [{ left: { type:"indicator", indicator:"CLOSE" }, operator:"lte", right: { type:"indicator", indicator:"BB_LOWER", period:20 } }] },
];

// ─── Types ───────────────────────────────────────────────────────────────────

/** Local draft type for the builder form — mirrors ScannerCreateInput + required description */
type ScannerDraft = ScannerCreateInput & { description: string };

// ─── Helpers ─────────────────────────────────────────────────────────────────

const uid = () => Math.random().toString(36).slice(2, 9);

function indInfo(name?: string): IndicatorItem | undefined {
  return ALL_INDICATORS.find(i => i.value === name);
}

function defaultSide(indicator = "CLOSE"): ConditionSide {
  const info = indInfo(indicator);
  if (info?.isNumber) return { type: "number", indicator, value: 0 };
  return { type: "indicator", indicator, period: info?.hasPeriod ? (info.defaultPeriod ?? 20) : undefined };
}

/** Honest rendering of a single backend `scanErrors` row.
 *
 *   reason === "insufficient-history" with got=0
 *     → the OHLCV chain (broker → NSE → BSE → Yahoo → Twelve Data →
 *       Stooq → history-derived) returned ZERO bars. That's almost
 *       never "new listing" — it's a symbol-mapping miss, an NSE
 *       Akamai block, or a Yahoo rate-limit. The old "new listing"
 *       label here lied to the user every time.
 *
 *   reason === "insufficient-history" with 0 < got < 30
 *     → genuinely thin history. New listing is plausible.
 *
 *   reason === "insufficient-history" with 30 ≤ got < needed
 *     → close call. Probably a recently-listed name; show counts.
 */
function formatScanError(e: { reason?: string; got?: number; needed?: number; error?: string; message?: string }): string {
  if (e.reason === "insufficient-history") {
    const got    = e.got ?? 0;
    const needed = e.needed ?? "?";
    if (got === 0)  return `data unavailable — 0 bars returned (likely symbol-mapping miss or upstream rate-limit)`;
    if (got < 30)  return `limited history — ${got} bars available (need ${needed}). Possibly new listing.`;
    return `insufficient history — ${got}/${needed} bars`;
  }
  if (e.reason === "insufficient-closes") return "insufficient data";
  if (e.reason === "fetch-failed")        return `fetch failed — ${e.error || "unknown error"}`;
  return e.error ?? e.message ?? e.reason ?? "unknown";
}


function blankCondition(): Condition {
  return { id: uid(), left: defaultSide("CLOSE"), operator: "gt", right: defaultSide("EMA") };
}

function blankDraft(): ScannerDraft {
  return { name: "", description: "", category: "", universe: ["NIFTY100"], logic: "AND", conditions: [blankCondition()] };
}

function condSummary(c: Condition): string {
  function side(s: ConditionSide) {
    if (!s) return "?";
    if (s.type === "number") return `${s.value ?? 0}`;
    const info = indInfo(s.indicator);
    return s.period ? `${info?.label ?? s.indicator}(${s.period})` : (info?.label ?? s.indicator ?? "?");
  }
  const op = OPERATORS.find(o => o.value === c.operator);
  return `${side(c.left)} ${op?.short ?? c.operator} ${side(c.right)}`;
}

// ─── Indicator Picker Component ───────────────────────────────────────────────

function IndicatorPicker({ side, onChange, label }: {
  side: ConditionSide;
  onChange: (s: ConditionSide) => void;
  label: string;
}) {
  const info  = indInfo(side.indicator);
  // Route through catColor() so an INDICATOR_GROUPS entry with a color
  // missing from CAT_COLORS falls back to gray instead of throwing
  // "Cannot read properties of undefined (reading 'bg')".
  const color = catColor(info?.color);

  function handleChange(v: string) {
    const newInfo = indInfo(v);
    if (newInfo?.isNumber) return onChange({ type: "number", indicator: v, value: 0 });
    onChange({ type: "indicator", indicator: v, period: newInfo?.hasPeriod ? (newInfo.defaultPeriod ?? 20) : undefined });
  }

  return (
    <div className="flex-1 min-w-0">
      <p className="text-xs font-medium text-gray-400 mb-1">{label}</p>
      <div className={`flex items-center gap-2 rounded-lg border-2 px-3 py-2 ${color.border} ${color.bg}`}>
        {/* Category dot */}
        <div className={`w-2 h-2 rounded-full flex-shrink-0 ${color.text.replace("text-", "bg-").replace("-700", "-500")}`} />

        <select
          value={side.indicator ?? "CLOSE"}
          onChange={e => handleChange(e.target.value)}
          className={`flex-1 min-w-0 bg-transparent text-sm font-medium ${color.text} focus:outline-none cursor-pointer`}
        >
          {INDICATOR_GROUPS.map(g => (
            <optgroup key={g.label} label={g.label}>
              {g.items.map(i => <option key={i.value} value={i.value}>{i.label}</option>)}
            </optgroup>
          ))}
        </select>

        {/* Period */}
        {info?.hasPeriod && side.type === "indicator" && (
          <input
            type="number" min={1} max={500}
            value={side.period ?? info?.defaultPeriod ?? 20}
            onChange={e => onChange({ ...side, period: Math.max(1, parseInt(e.target.value) || 1) })}
            className={`w-12 text-center bg-white border ${color.border} rounded text-xs font-mono font-bold ${color.text} focus:outline-none focus:ring-1`}
            title="Period"
          />
        )}

        {/* Number value */}
        {info?.isNumber && (
          <input
            type="number" step="any"
            value={side.value ?? 0}
            onChange={e => onChange({ ...side, value: parseFloat(e.target.value) || 0 })}
            className="w-20 text-center bg-white border border-gray-200 rounded text-xs font-mono font-bold text-gray-700 focus:outline-none focus:ring-1 focus:ring-indigo-400"
            placeholder="Value"
          />
        )}
      </div>

      {/* Show current value label */}
      <p className={`text-xs mt-0.5 ${color.text} opacity-70`}>
        {info?.group ?? "Value"}
        {side.period ? ` · period ${side.period}` : ""}
      </p>
    </div>
  );
}

// ─── Single Condition Row ─────────────────────────────────────────────────────

function ConditionRow({ condition, index, logic, onChange, onDelete, total }: {
  condition: Condition; index: number; logic: "AND"|"OR";
  onChange: (c: Condition) => void; onDelete: () => void; total: number;
}) {
  const op = OPERATORS.find(o => o.value === condition.operator);

  return (
    <div className="relative bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
      {/* Logic badge */}
      <div className="absolute -left-3 top-1/2 -translate-y-1/2">
        {index === 0 ? (
          <span className="text-xs font-bold text-gray-500 bg-gray-100 border border-gray-200 rounded-full px-2 py-0.5">IF</span>
        ) : (
          <span className={`text-xs font-bold rounded-full px-2 py-0.5 ${
            logic === "AND"
              ? "bg-indigo-100 text-indigo-700 border border-indigo-200"
              : "bg-amber-100 text-amber-700 border border-amber-200"
          }`}>{logic}</span>
        )}
      </div>

      <div className="flex items-start gap-3 pl-2">
        {/* Left indicator */}
        <IndicatorPicker side={condition.left} label="Indicator" onChange={left => onChange({ ...condition, left })} />

        {/* Operator */}
        <div className="flex-shrink-0 pt-1">
          <p className="text-xs font-medium text-gray-400 mb-1 text-center">Condition</p>
          <select
            value={condition.operator}
            onChange={e => onChange({ ...condition, operator: e.target.value })}
            className="block w-full text-center text-sm font-bold text-purple-700 bg-purple-50 border-2 border-purple-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-purple-300 cursor-pointer"
          >
            {OPERATORS.map(o => <option key={o.value} value={o.value}>{o.short} {o.label}</option>)}
          </select>
          <p className="text-xs mt-0.5 text-purple-500 text-center opacity-70">{op?.short} {op?.label}</p>
        </div>

        {/* Right indicator */}
        <IndicatorPicker side={condition.right} label="Compare to" onChange={right => onChange({ ...condition, right })} />

        {/* Delete */}
        <button
          onClick={onDelete}
          disabled={total <= 1}
          className="mt-6 p-1.5 rounded-lg text-gray-300 hover:text-red-400 hover:bg-red-50 disabled:opacity-20 transition flex-shrink-0"
          title="Remove condition"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

// ─── Scanner Card (left panel) ────────────────────────────────────────────────

function ScannerCard({
  scanner, isRunning, isSelected, onRun, onEdit, onDuplicate, onDelete, onSelect,
  progress, starting,
}: {
  scanner: Scanner; isRunning: boolean; isSelected: boolean;
  onRun: () => void; onEdit: () => void; onDuplicate: () => void; onDelete: () => void; onSelect: () => void;
  /** Live progress snapshot from the async scan job. Null when no scan
   *  is running for THIS scanner (the parent passes null for any card
   *  other than the active one). When non-null, the run button morphs
   *  into a progress bar. */
  progress?: ScanJobProgress | null;
  /** True during the POST round-trip immediately after the user clicks
   *  Run, BEFORE the background job's first poll arrives. Without this,
   *  the user clicks and sees no visual change for 1-3 seconds. */
  starting?: boolean;
}) {
  return (
    <div
      onClick={onSelect}
      className={`group cursor-pointer rounded-xl border-2 p-4 transition-all ${
        isSelected ? "border-indigo-400 bg-indigo-50 shadow-md" : "border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-semibold text-gray-900 text-sm truncate">{scanner.name}</h3>
            <span className={`text-xs px-1.5 py-0.5 rounded-md font-bold ${
              scanner.logic === "AND" ? "bg-indigo-100 text-indigo-600" : "bg-amber-100 text-amber-600"
            }`}>{scanner.logic}</span>
          </div>
          {scanner.description && <p className="text-xs text-gray-500 mt-0.5 truncate">{scanner.description}</p>}

          {/* Universe badges */}
          <div className="flex gap-1 mt-1.5 flex-wrap">
            {scanner.universe?.map((u: string) => {
              const LABELS: Record<string, string> = { NIFTY100: "Large Cap", MIDCAP: "Mid Cap", SMALLCAP: "Small Cap", MICROCAP: "Micro Cap", ALL: "All" };
              return <span key={u} className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded-md">{LABELS[u] ?? u}</span>;
            })}
            <span className="text-xs text-gray-400">{scanner.conditions?.length} condition{scanner.conditions?.length !== 1 ? "s" : ""}</span>
          </div>

          {/* Condition chips */}
          <div className="mt-2 space-y-1">
            {scanner.conditions?.slice(0, 3).map((c: any, i: number) => {
              const info = indInfo(c.left?.indicator);
              const col  = catColor(info?.color);
              return (
                <span key={i} className={`inline-block text-xs px-2 py-0.5 rounded-full font-mono mr-1 ${col.bg} ${col.text} border ${col.border}`}>
                  {condSummary(c)}
                </span>
              );
            })}
            {scanner.conditions?.length > 3 && (
              <span className="text-xs text-gray-400">+{scanner.conditions.length - 3} more</span>
            )}
          </div>

          {scanner.lastRunAt && (
            <p className="text-xs text-gray-400 mt-2">
              Last: {new Date(scanner.lastRunAt).toLocaleDateString("en-IN", { day:"2-digit", month:"short", hour:"2-digit", minute:"2-digit" })}
              {scanner.lastResultCount !== undefined && ` · ${scanner.lastResultCount} matched`}
            </p>
          )}
        </div>
      </div>

      {/* Live progress (only while a scan is running for THIS scanner).
          Replaces the Run button entirely so the user sees scanned /
          matched / failed counts updating in real time. The bar fills
          as `scanned` approaches `total`. Stage label distinguishes
          the slow Yahoo prefetch (which has no per-symbol counter) from
          the actual scanning phase. */}
      {/* `starting` covers the ~1-3s window between Run click and the
          first job-poll arriving (before isRunning/progress exist).
          Without this branch the card stays in its idle state during
          that window and the user assumes the click didn't register. */}
      {starting && !isRunning ? (
        <div className="mt-3" onClick={e => e.stopPropagation()}>
          <div className="flex items-center gap-2 text-[11px] font-semibold text-indigo-700 dark:text-indigo-300">
            <Loader2 className="w-3 h-3 animate-spin" />
            Starting scan…
          </div>
          <div className="h-1.5 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden mt-1">
            <div className="h-full bg-indigo-500 animate-pulse" style={{ width: "100%" }} />
          </div>
        </div>
      ) : isRunning && progress ? (
        <div className="mt-3" onClick={e => e.stopPropagation()}>
          <div className="flex items-center justify-between text-[11px] mb-1">
            <span className="font-semibold text-indigo-700 dark:text-indigo-300 flex items-center gap-1.5">
              <Loader2 className="w-3 h-3 animate-spin" />
              {progress.stage === "prefetch_fundamentals"
                ? "Loading fundamentals…"
                : progress.stage === "starting"
                ? "Starting…"
                : `Scanning ${progress.scanned}/${progress.total}`}
            </span>
            <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
              {progress.matched} matched
            </span>
          </div>
          {/* Bar fills based on `scanned / total`. During prefetch
              (where scanned is still 0) we render an indeterminate
              striped bar so the user knows something IS happening. */}
          <div className="h-1.5 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
            {progress.stage === "prefetch_fundamentals" || progress.total === 0 ? (
              <div
                className="h-full bg-indigo-500 animate-pulse"
                style={{ width: "100%" }}
              />
            ) : (
              <div
                className="h-full bg-indigo-500 transition-all duration-300"
                style={{ width: `${Math.min(100, (progress.scanned / Math.max(progress.total, 1)) * 100)}%` }}
              />
            )}
          </div>
          {/* Detail row — only meaningful during the scanning phase
              when failed/errors > 0. Hidden during prefetch to avoid
              showing "0 failed" prematurely. */}
          {progress.stage === "scanning" && (
            <div className="flex items-center justify-between text-[10px] text-gray-500 dark:text-gray-400 mt-1">
              <span>{progress.failed} didn't pass</span>
              {progress.errors > 0 && <span className="text-rose-500">{progress.errors} errors</span>}
              <span>{Math.max(0, progress.total - progress.scanned)} left</span>
            </div>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-1.5 mt-3">
          <button
            onClick={e => { e.stopPropagation(); onRun(); }}
            disabled={isRunning}
            className="flex items-center gap-1.5 flex-1 justify-center py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold transition disabled:opacity-60"
          >
            {isRunning ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
            {isRunning ? "Running…" : "Run Scan"}
          </button>
          <button onClick={e => { e.stopPropagation(); onEdit(); }}    title="Edit"      className="p-1.5 rounded-lg text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 border border-gray-200 transition"><Edit2  className="w-3.5 h-3.5" /></button>
          <button onClick={e => { e.stopPropagation(); onDuplicate();}} title="Duplicate" className="p-1.5 rounded-lg text-gray-400 hover:text-amber-600 hover:bg-amber-50  border border-gray-200 transition"><Copy   className="w-3.5 h-3.5" /></button>
          <button onClick={e => { e.stopPropagation(); onDelete(); }}   title="Delete"    className="p-1.5 rounded-lg text-gray-400 hover:text-red-500   hover:bg-red-50    border border-gray-200 transition"><Trash2 className="w-3.5 h-3.5" /></button>
        </div>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

type RightPanel = "empty" | "builder" | "results";

export default function Scanners() {
  const qc = useQueryClient();

  // State
  const [rightPanel, setRightPanel] = useState<RightPanel>("empty");
  const [draft, setDraft]           = useState<ScannerDraft>(blankDraft());
  const [editingId, setEditingId]   = useState<string | null>(null);
  const [runningId, setRunningId]   = useState<string | null>(null);
  const [result, setResult]         = useState<ScanResult | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Active category filter. "All" → grouped view with sticky headers.
  // A specific category → flat filtered list.
  const [categoryFilter, setCategoryFilter] = useState<string>("All");

  const { data: scannersResp, isLoading } = useQuery(
    marketDataQueryOptions(["scanners"], api.scannersWithMeta),
  );
  const scanners: Scanner[] = scannersResp?.scanners ?? [];
  const scannersMeta = pickMeta(scannersResp);

  // ── Category grouping ──────────────────────────────────────────────────
  // Bucket scanners by their `category` field. Legacy scanners that pre-
  // date the field land in "Uncategorized". `groupedScanners` is the
  // source of truth for both the filter-pill counts and the rendered
  // sections so the two can't drift.
  const groupedScanners: Record<string, Scanner[]> = {};
  for (const s of scanners) {
    const cat = (s.category || "Uncategorized").trim() || "Uncategorized";
    (groupedScanners[cat] ||= []).push(s);
  }
  // Stable display order. Anything not in this list appears alphabetically
  // after the explicit entries. Order matches typical retail workflow:
  // trend → momentum → mean-reversion → oscillators → volume → patterns.
  const CATEGORY_ORDER = [
    "Hidden Gems",      // fundamentals-driven — surfaced first
    "Trend", "Momentum", "Mean Reversion", "Oscillators",
    "Volume", "Pattern + Volume", "Uncategorized",
  ];
  const orderedCategories: string[] = [
    ...CATEGORY_ORDER.filter(c => groupedScanners[c]?.length),
    ...Object.keys(groupedScanners)
        .filter(c => !CATEGORY_ORDER.includes(c))
        .sort(),
  ];
  // Pill list — "All" first with total count, then each category with its count.
  const categoryPills: { key: string; label: string; count: number }[] = [
    { key: "All", label: "All", count: scanners.length },
    ...orderedCategories.map(c => ({
      key: c, label: c, count: groupedScanners[c].length,
    })),
  ];
  // When a specific category is active, only that bucket renders. When
  // "All" is active, render every bucket with a sticky header.
  const visibleCategories = categoryFilter === "All"
    ? orderedCategories
    : orderedCategories.filter(c => c === categoryFilter);

  const saveMut = useMutation({
    mutationFn: (d: ScannerDraft & { id?: string }) =>
      d.id ? api.updateScanner(d.id, d) : api.createScanner(d),
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["scanners"] });
      setEditingId(null); setDraft(blankDraft());
      setRightPanel("empty");
    },
  });

  const deleteMut = useMutation({
    mutationFn: api.deleteScanner,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scanners"] });
      setRightPanel("empty"); setSelectedId(null);
    },
  });

  // Job-based scan: fires the run-job endpoint, persists the jobId,
  // polls until terminal state. Survives navigation — if the user
  // refreshes or visits another page mid-scan, returning here resumes
  // polling automatically. See src/hooks/useScanJob.ts for details.
  const scanJob = useScanJob({
    onComplete: (data) => {
      setResult(data);
      setRightPanel("results");
      setRunningId(null);
    },
    onFailed: (err) => {
      // eslint-disable-next-line no-console
      console.warn("Scan failed:", err);
      setRunningId(null);
    },
  });

  // Mirror the hook's activeScannerId onto the legacy `runningId`
  // state so the existing UI (which uses runningId to grey out the
  // Run button, etc.) keeps working unchanged.
  useEffect(() => {
    setRunningId(scanJob.activeScannerId);
  }, [scanJob.activeScannerId]);

  const testMut = useMutation({
    mutationFn: api.runAdHoc,
    onMutate:   () => { setRunningId("adhoc"); },
    onSuccess:  (data) => { setResult(data); setRightPanel("results"); setRunningId(null); },
    onError:    () => setRunningId(null),
  });

  // Condition helpers
  const updateCondition = useCallback((idx: number, c: Condition) =>
    setDraft(d => ({ ...d, conditions: d.conditions.map((x, i) => i === idx ? c : x) })), []);
  const deleteCondition = useCallback((idx: number) =>
    setDraft(d => ({ ...d, conditions: d.conditions.filter((_, i) => i !== idx) })), []);
  const addCondition    = useCallback(() =>
    setDraft(d => ({ ...d, conditions: [...d.conditions, blankCondition()] })), []);

  function addTemplate(tpl: typeof TEMPLATES[0]) {
    const newConds: Condition[] = tpl.conditions.map(c => ({ ...c, id: uid() } as Condition));
    setDraft(d => ({ ...d, conditions: [...d.conditions, ...newConds] }));
  }

  function startNew() {
    setDraft(blankDraft()); setEditingId(null); setRightPanel("builder");
  }

  function startEdit(scanner: any) {
    setDraft({
      name: scanner.name, description: scanner.description ?? "",
      category: scanner.category ?? "",
      universe: scanner.universe ?? ["NIFTY100"], logic: scanner.logic ?? "AND",
      conditions: scanner.conditions?.map((c: any) => ({ ...c, id: c.id || uid() })) ?? [],
    });
    setEditingId(scanner.id); setSelectedId(scanner.id); setRightPanel("builder");
  }

  function duplicate(scanner: any) {
    setDraft({
      name: `${scanner.name} (copy)`, description: scanner.description ?? "",
      category: scanner.category ?? "",
      universe: scanner.universe ?? ["NIFTY100"], logic: scanner.logic ?? "AND",
      conditions: scanner.conditions?.map((c: any) => ({ ...c, id: uid() })) ?? [],
    });
    setEditingId(null); setRightPanel("builder");
  }

  const canSave = draft.name.trim().length > 0 && draft.conditions.length > 0 && draft.universe.length > 0;

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="h-full flex flex-col">
      {/* Page Header */}
      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Stock Scanners</h1>
          <p className="text-sm text-gray-500">Build, save & run custom condition-based scans across any universe</p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <DataFreshness meta={scannersMeta} refreshKeys={["scanners"]} />
          <button onClick={startNew}
            className="flex items-center gap-2 px-4 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition shadow-sm">
            <Plus className="w-4 h-4" /> New Scanner
          </button>
        </div>
      </div>

      {/* Universe freshness banner — surfaces honestly. Two distinct states:
          (1) hardcoded fallback (cache never loaded) → hard warning;
          (2) live cache present but stale (>2 days old) → mild "last refreshed"
          note. Silent fallback is exactly the kind of thing users rightly hate. */}
      {scannersMeta?.universe && scannersMeta.universe.isLiveUniverse === false && (
        <div className="mb-4 flex items-start gap-2 bg-amber-50 border border-amber-200 text-amber-800 rounded-lg px-3 py-2 text-xs">
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold">Scanning fallback universe ({scannersMeta.universe.totalSymbols} symbols)</p>
            <p className="opacity-80">Live NSE/AMFI membership cache is unavailable — recently listed or delisted stocks may be missing. Re-running the universe builder will refresh this list.</p>
          </div>
        </div>
      )}
      {scannersMeta?.universe
        && scannersMeta.universe.isLiveUniverse !== false
        && (scannersMeta.universe.ageSeconds ?? 0) > 2 * 86400 && (
        <div className="mb-4 flex items-start gap-2 bg-amber-50/60 border border-amber-200/70 text-amber-700 rounded-lg px-3 py-2 text-xs">
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold">
              Live universe ({scannersMeta.universe.totalSymbols} symbols) · last refreshed {Math.round(scannersMeta.universe.ageSeconds! / 86400)} days ago
            </p>
            <p className="opacity-80">Membership hasn't refreshed in a while — very recently listed/delisted stocks may be missing.</p>
          </div>
        </div>
      )}

      {/* Split layout */}
      <div className="flex gap-5 flex-1 min-h-0">

        {/* ── LEFT: Scanner List ────────────────────────────────────────────── */}
        <div className="w-80 flex-shrink-0 flex flex-col overflow-hidden">
          {/* Category filter pills — sticky at the top of the column.
              Shows All / each category with the scanner count per group.
              Clicking a pill switches between "All grouped" and "single
              category flat" modes. */}
          {!isLoading && scanners.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pb-3 sticky top-0 bg-inherit z-10">
              {categoryPills.map(p => {
                const active = categoryFilter === p.key;
                return (
                  <button
                    key={p.key}
                    onClick={() => setCategoryFilter(p.key)}
                    className={`px-2.5 py-1 rounded-full text-[11px] font-semibold transition border ${
                      active
                        ? "bg-indigo-600 text-white border-indigo-600 shadow-sm"
                        : "bg-gray-50 text-gray-600 border-gray-200 hover:bg-gray-100 dark:bg-gray-800/60 dark:text-gray-300 dark:border-gray-700 dark:hover:bg-gray-700"
                    }`}
                  >
                    {p.label}
                    <span className={`ml-1 ${active ? "opacity-80" : "opacity-60"}`}>
                      {p.count}
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          <div className="flex-1 flex flex-col gap-3 overflow-y-auto pb-4 pr-1">
            {isLoading ? (
              [...Array(3)].map((_, i) => <div key={i} className="h-36 bg-gray-100 animate-pulse rounded-xl" />)
            ) : scanners.length === 0 ? (
              <div className="text-center py-12 text-gray-400 border-2 border-dashed border-gray-200 rounded-xl">
                <Filter className="w-8 h-8 mx-auto mb-2 opacity-30" />
                <p className="font-medium text-sm">No scanners yet</p>
                <p className="text-xs mt-1">Click "New Scanner" to start</p>
              </div>
            ) : (
              visibleCategories.map(cat => (
                <div key={cat} className="flex flex-col gap-3">
                  {/* Section header — visible whenever multiple categories
                      are being rendered (i.e. "All" mode). Hidden when a
                      single category is selected since the active pill
                      already shows what's being viewed. */}
                  {categoryFilter === "All" && (
                    <div className="flex items-baseline justify-between px-1 pt-1 pb-0.5">
                      <h3 className="text-[10px] font-bold uppercase tracking-widest text-gray-500 dark:text-gray-400">
                        {cat}
                      </h3>
                      <span className="text-[10px] text-gray-400">
                        {groupedScanners[cat].length}
                      </span>
                    </div>
                  )}
                  {groupedScanners[cat].map((s: Scanner) => (
                    <ScannerCard
                      key={s.id} scanner={s}
                      isRunning={runningId === s.id}
                      isSelected={selectedId === s.id}
                      onRun={() => {
                        // Clear the previous scan's result FIRST so the
                        // live-scanning render block (gated on !result)
                        // can take over the right panel. Without this,
                        // clicking Run on a second scanner shows the
                        // FIRST scanner's stale results until the second
                        // completes, which feels broken.
                        setResult(null);
                        setSelectedId(s.id);
                        scanJob.startScan(s.id);
                        // Open the results panel immediately so the user
                        // sees live progress + matches streaming in,
                        // instead of an empty "Select a scanner to run"
                        // pane until the scan completes.
                        setRightPanel("results");
                      }}
                      progress={runningId === s.id ? scanJob.progress : null}
                      starting={scanJob.starting && selectedId === s.id}
                      onEdit={() => startEdit(s)}
                      onDuplicate={() => duplicate(s)}
                      onDelete={() => { if (confirm(`Delete "${s.name}"?`)) deleteMut.mutate(s.id); }}
                      onSelect={() => setSelectedId(s.id)}
                    />
                  ))}
                </div>
              ))
            )}
          </div>
        </div>

        {/* ── RIGHT: Builder or Results ─────────────────────────────────────── */}
        <div className="flex-1 min-w-0 overflow-y-auto pb-4">

          {/* ── BUILDER ──────────────────────────────────────────────────────── */}
          {rightPanel === "builder" && (
            <div className="space-y-5">
              {/* Name + Description */}
              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <h2 className="text-sm font-bold text-gray-700 uppercase tracking-wide mb-4">Scanner Details</h2>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-semibold text-gray-600 mb-1">Scanner Name *</label>
                    <input
                      value={draft.name}
                      onChange={e => setDraft(d => ({ ...d, name: e.target.value }))}
                      placeholder='e.g. "RSI Oversold + Volume Spike"'
                      className="w-full border-2 border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-indigo-400 transition"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-600 mb-1">Description (optional)</label>
                    <input
                      value={draft.description}
                      onChange={e => setDraft(d => ({ ...d, description: e.target.value }))}
                      placeholder="Describe what this scanner finds…"
                      className="w-full border-2 border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-indigo-400 transition"
                    />
                  </div>
                  {/* Category — determines which filter-pill group the
                      scanner shows up under on the left column. Free-text
                      so power users can introduce new buckets (e.g.
                      "Mean Reversion (Custom)") without a code change. */}
                  <div>
                    <label className="block text-xs font-semibold text-gray-600 mb-1">Category (optional)</label>
                    <input
                      list="scanner-category-options"
                      value={draft.category ?? ""}
                      onChange={e => setDraft(d => ({ ...d, category: e.target.value }))}
                      placeholder='e.g. "Volume" or "Trend"'
                      className="w-full border-2 border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-indigo-400 transition"
                    />
                    <datalist id="scanner-category-options">
                      {orderedCategories.filter(c => c !== "Uncategorized").map(c => (
                        <option key={c} value={c} />
                      ))}
                    </datalist>
                  </div>
                </div>
              </div>

              {/* Universe + Logic */}
              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <h2 className="text-sm font-bold text-gray-700 uppercase tracking-wide mb-4">Scan Settings</h2>
                <div className="flex flex-wrap gap-6">
                  <div>
                    <p className="text-xs font-semibold text-gray-600 mb-2">Stock Universe *</p>
                    <div className="flex gap-2 flex-wrap">
                      {([
                        { key: "NIFTY100", label: "Large Cap" },
                        { key: "MIDCAP",   label: "Mid Cap"   },
                        { key: "SMALLCAP", label: "Small Cap" },
                        { key: "MICROCAP", label: "Micro Cap" },
                        { key: "ALL",      label: "All Stocks (full market)" },
                      ] as const).map(({ key: u, label }) => {
                        const active = draft.universe.includes(u);
                        return (
                          <button key={u} onClick={() => setDraft(d => ({
                            ...d,
                            // "All Stocks" is the whole tradeable universe, so it's
                            // exclusive: picking it clears the cap selections and
                            // vice-versa.
                            universe: u === "ALL"
                              ? (active ? [] : ["ALL"])
                              : (active
                                  ? d.universe.filter(x => x !== u)
                                  : [...d.universe.filter(x => x !== "ALL"), u])
                          }))}
                            className={`px-3 py-1.5 rounded-lg text-sm font-semibold border-2 transition ${
                              active
                                ? "bg-indigo-600 text-white border-indigo-600"
                                : "bg-white text-gray-600 border-gray-200 hover:border-indigo-300"
                            }`}
                          >{label}</button>
                        );
                      })}
                    </div>
                  </div>

                  <div>
                    <p className="text-xs font-semibold text-gray-600 mb-2">Condition Logic</p>
                    <div className="flex rounded-xl overflow-hidden border-2 border-gray-200">
                      {(["AND", "OR"] as const).map(l => (
                        <button key={l} onClick={() => setDraft(d => ({ ...d, logic: l }))}
                          className={`px-5 py-1.5 text-sm font-bold transition ${
                            draft.logic === l
                              ? l === "AND" ? "bg-indigo-600 text-white" : "bg-amber-500 text-white"
                              : "bg-white dark:bg-slate-700 text-gray-500 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-600"
                          }`}>{l}</button>
                      ))}
                    </div>
                    <p className="text-xs text-gray-400 mt-1.5">
                      {draft.logic === "AND" ? "✓ All conditions must pass" : "✓ Any condition can pass"}
                    </p>
                  </div>
                </div>
              </div>

              {/* Conditions */}
              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h2 className="text-sm font-bold text-gray-700 uppercase tracking-wide">Conditions</h2>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {draft.conditions.length} condition{draft.conditions.length !== 1 ? "s" : ""}
                      {" · "}{draft.logic === "AND" ? "All must pass" : "Any can pass"}
                    </p>
                  </div>
                </div>

                {/* Condition rows */}
                <div className="space-y-3 pl-4">
                  {draft.conditions.map((c, i) => (
                    <ConditionRow
                      key={c.id} condition={c} index={i} logic={draft.logic} total={draft.conditions.length}
                      onChange={nc => updateCondition(i, nc)}
                      onDelete={() => deleteCondition(i)}
                    />
                  ))}
                </div>

                {/* Add condition */}
                <button onClick={addCondition}
                  className="mt-4 w-full flex items-center justify-center gap-2 py-2.5 border-2 border-dashed border-gray-200 rounded-xl text-sm text-gray-500 hover:border-indigo-300 hover:text-indigo-600 hover:bg-indigo-50 transition">
                  <Plus className="w-4 h-4" /> Add Condition
                </button>
              </div>

              {/* Quick templates */}
              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <h2 className="text-sm font-bold text-gray-700 uppercase tracking-wide mb-3">Quick Add from Templates</h2>
                <div className="flex flex-wrap gap-2">
                  {TEMPLATES.map(t => (
                    <button key={t.label} onClick={() => addTemplate(t)}
                      className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-gray-50 hover:bg-indigo-50 border border-gray-200 hover:border-indigo-300 text-gray-700 hover:text-indigo-700 rounded-full transition">
                      <Plus className="w-3 h-3" /> {t.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex items-center gap-3 flex-wrap">
                <button
                  onClick={() => testMut.mutate(draft)}
                  disabled={!canSave || !!runningId}
                  className="flex items-center gap-2 px-5 py-2.5 bg-amber-500 hover:bg-amber-600 text-white rounded-xl text-sm font-semibold transition disabled:opacity-60 shadow-sm"
                >
                  {runningId === "adhoc" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                  {runningId === "adhoc" ? "Scanning…" : "Test Run (don't save)"}
                </button>

                <button
                  onClick={() => saveMut.mutate({ ...draft, ...(editingId ? { id: editingId } : {}) })}
                  disabled={!canSave || saveMut.isPending}
                  className="flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-semibold transition disabled:opacity-60 shadow-sm"
                >
                  {saveMut.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  {saveMut.isPending ? "Saving…" : editingId ? "Update Scanner" : "Save Scanner"}
                </button>

                <button onClick={() => { setRightPanel("empty"); setEditingId(null); setDraft(blankDraft()); }}
                  className="px-4 py-2.5 text-sm text-gray-500 hover:text-gray-700 transition">
                  Cancel
                </button>

                {!canSave && draft.name.trim() === "" && (
                  <span className="text-xs text-red-500 flex items-center gap-1">
                    <AlertCircle className="w-3.5 h-3.5" /> Name required
                  </span>
                )}
              </div>
            </div>
          )}

          {/* ── LIVE SCANNING ────────────────────────────────────────────────
              Renders while a scan is in flight. Each match streams in
              as the backend finds it (arrival order). When the scan
              completes, the `useScanJob` onComplete sets `result` and
              the block below takes over with the final sorted view. */}
          {rightPanel === "results" && !result && (scanJob.starting || (scanJob.activeScannerId && scanJob.status !== "completed" && scanJob.status !== "failed")) && (
            <div className="space-y-4">
              <div className="bg-white dark:bg-gray-900 rounded-xl border border-indigo-200 dark:border-indigo-700/40 p-5 shadow-sm">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h2 className="font-bold text-gray-900 dark:text-white text-lg flex items-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin text-indigo-500" />
                      {/* Title resolution order:
                           1. Active job's scanner (once polling has begun)
                           2. Selected scanner (during the POST round-trip
                              before activeScannerId updates)
                           3. Generic fallback */}
                      {scanners.find(s => s.id === (scanJob.activeScannerId ?? selectedId))?.name ?? "Scanning"}
                    </h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                      {scanJob.starting && !scanJob.activeScannerId
                        ? "Starting scan…"
                        : scanJob.progress?.stage === "prefetch_fundamentals"
                        ? "Loading fundamentals across the universe…"
                        : scanJob.progress?.stage === "scanning"
                        ? `Scanning ${scanJob.progress.scanned}/${scanJob.progress.total} stocks · ${scanJob.partialMatches.length} matched so far · ${scanJob.progress.failed} didn't pass`
                        : "Starting scan…"}
                    </p>
                  </div>
                  <button onClick={() => setRightPanel("empty")}
                    className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition">
                    <X className="w-4 h-4" />
                  </button>
                </div>

                {/* Progress bar — wider than the card-level one. Same
                    indeterminate-pulse during prefetch_fundamentals
                    where per-symbol counters aren't ticking yet. */}
                <div className="mt-4 h-1.5 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
                  {scanJob.progress?.stage === "prefetch_fundamentals" || !scanJob.progress?.total ? (
                    <div className="h-full bg-indigo-500 animate-pulse" style={{ width: "100%" }} />
                  ) : (
                    <div
                      className="h-full bg-indigo-500 transition-all duration-300"
                      style={{ width: `${Math.min(100, (scanJob.progress.scanned / Math.max(scanJob.progress.total, 1)) * 100)}%` }}
                    />
                  )}
                </div>
              </div>

              {/* Live matches list. Empty until the first match arrives —
                  shows a friendly hint then so the user knows the scan
                  is running but the conditions are strict. */}
              {scanJob.partialMatches.length === 0 ? (
                <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-white/10 p-6 text-center">
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    No matches yet — the scan is still working through your universe.
                  </p>
                  <p className="text-[11px] text-gray-400 mt-1">
                    Matches will appear here in the order they're found.
                  </p>
                </div>
              ) : (
                <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-white/10 shadow-sm overflow-hidden">
                  <div className="px-5 py-3 bg-emerald-50 dark:bg-emerald-900/20 border-b border-emerald-100 dark:border-emerald-700/30 flex items-center justify-between">
                    <span className="text-sm font-semibold text-emerald-700 dark:text-emerald-300">
                      🔥 {scanJob.partialMatches.length} match{scanJob.partialMatches.length === 1 ? "" : "es"} so far (live)
                    </span>
                    <span className="text-xs text-emerald-600 dark:text-emerald-400">
                      sorted on completion
                    </span>
                  </div>
                  <div className="divide-y divide-gray-50 dark:divide-slate-800/80">
                    {scanJob.partialMatches.map((r: any, i: number) => (
                      <div key={`${r.symbol}-${i}`} className="px-5 py-4 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition">
                        <div className="flex items-center justify-between gap-4">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-3 flex-wrap">
                              <span className="font-bold text-gray-900 dark:text-white text-base">{r.symbol}</span>
                              <ChartButton symbol={r.symbol} />
                              <span className={`flex items-center gap-1 text-sm font-semibold ${r.pChange >= 0 ? "text-green-600" : "text-red-500"}`}>
                                {r.pChange >= 0 ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                                {r.pChange >= 0 ? "+" : ""}{r.pChange?.toFixed(2)}%
                              </span>
                              {r.hiddenGemScore != null && (
                                <HiddenGemScoreBadge
                                  score={r.hiddenGemScore}
                                  breakdown={r.hiddenGemBreakdown}
                                />
                              )}
                              <ExitPlanButton symbol={r.symbol} currentPrice={r.lastPrice} />
                            </div>
                            <div className="flex flex-wrap gap-1 mt-2">
                              {r.matchedConditions?.slice(0, 3).map((mc: string, j: number) => (
                                <span key={j} className="inline-flex items-center gap-1 text-xs bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300 border border-green-100 dark:border-green-700/40 px-2 py-0.5 rounded-full">
                                  <CheckCircle2 className="w-3 h-3 flex-shrink-0" /> {mc}
                                </span>
                              ))}
                              {r.matchedConditions?.length > 3 && (
                                <span className="text-xs text-gray-400">+{r.matchedConditions.length - 3} more</span>
                              )}
                            </div>
                          </div>
                          <div className="text-right flex-shrink-0">
                            <p className="font-bold text-gray-900 dark:text-white text-lg">₹{r.lastPrice?.toFixed(2)}</p>
                            <p className="text-xs text-indigo-600 dark:text-indigo-400 mt-0.5 font-medium">{r.score}% match</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── RESULTS ──────────────────────────────────────────────────────── */}
          {rightPanel === "results" && result && (
            <div className="space-y-4">
              {/* Results header */}
              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h2 className="font-bold text-gray-900 text-lg">{result.scannerName ?? "Test Results"}</h2>
                    <p className="text-sm text-gray-500 mt-0.5">
                      {new Date(result.runAt).toLocaleString("en-IN", { day:"2-digit", month:"short", hour:"2-digit", minute:"2-digit" })}
                      {" · "}{result.totalScanned} stocks scanned
                    </p>
                  </div>
                  <button onClick={() => setRightPanel("empty")}
                    className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition">
                    <X className="w-4 h-4" />
                  </button>
                </div>

                {/* Summary stats */}
                <div className="grid grid-cols-3 gap-3 mt-4">
                  <div className="bg-indigo-50 rounded-lg p-3 text-center border border-indigo-100">
                    <p className="text-2xl font-bold text-indigo-600">{result.totalScanned}</p>
                    <p className="text-xs text-indigo-700 font-medium mt-0.5">Scanned</p>
                  </div>
                  <div className={`rounded-lg p-3 text-center border ${result.totalMatched > 0 ? "bg-green-50 border-green-100" : "bg-gray-50 border-gray-200"}`}>
                    <p className={`text-2xl font-bold ${result.totalMatched > 0 ? "text-green-600" : "text-gray-400"}`}>{result.totalMatched}</p>
                    <p className={`text-xs font-medium mt-0.5 ${result.totalMatched > 0 ? "text-green-700" : "text-gray-500"}`}>Matched</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3 text-center border border-gray-200">
                    <p className="text-2xl font-bold text-gray-600">
                      {result.totalScanned ? Math.round((result.totalMatched / result.totalScanned) * 100) : 0}%
                    </p>
                    <p className="text-xs text-gray-500 font-medium mt-0.5">Hit Rate</p>
                  </div>
                </div>
              </div>

              {/* Auto-quarantined — symbols the system has empirically
                  learned have no usable data anywhere (delisted, SME-only,
                  suspended). Shown as a quiet info banner, distinct from
                  the amber "errors" banner below, because these are
                  intentional skips rather than failures. */}
              {((result as any).quarantinedCount ?? 0) > 0 && (
                <div className="bg-gray-50 dark:bg-gray-800/40 border border-gray-200 dark:border-gray-700 rounded-xl p-3">
                  <div className="flex items-center gap-2 text-gray-600 dark:text-gray-300">
                    <AlertCircle className="w-3.5 h-3.5" />
                    <p className="text-xs">
                      <span className="font-medium">{(result as any).quarantinedCount}</span> symbol
                      {(result as any).quarantinedCount !== 1 ? "s" : ""} auto-skipped — no usable data across NSE / BSE / Yahoo (delisted, SME-only, or suspended)
                    </p>
                  </div>
                  {Array.isArray((result as any).quarantinedSymbols) && (result as any).quarantinedSymbols.length > 0 && (
                    <details className="mt-1.5">
                      <summary className="text-[11px] text-gray-500 cursor-pointer">Show symbols</summary>
                      <p className="mt-1 text-[11px] text-gray-500 font-mono break-all">
                        {(result as any).quarantinedSymbols.slice(0, 200).join(", ")}
                        {(result as any).quarantinedSymbols.length > 200 && ` …and ${(result as any).quarantinedSymbols.length - 200} more`}
                      </p>
                    </details>
                  )}
                </div>
              )}

              {/* Scan errors — surface per-symbol failures so a 0-match result
                  can be distinguished from a failed scan. Honest data labels
                  trump quietly hiding broken provider responses. */}
              {Array.isArray((result as any).scanErrors) && (result as any).scanErrors.length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
                  <div className="flex items-center gap-2 text-amber-800">
                    <AlertCircle className="w-4 h-4" />
                    <p className="text-sm font-semibold">
                      {(result as any).scanErrors.length} symbol{(result as any).scanErrors.length !== 1 ? "s" : ""} skipped due to data errors
                    </p>
                  </div>
                  <details className="mt-2">
                    <summary className="text-xs text-amber-700 cursor-pointer">Show details</summary>
                    <ul className="mt-2 text-xs text-amber-700 space-y-0.5 max-h-40 overflow-y-auto font-mono">
                      {(result as any).scanErrors.slice(0, 50).map((e: any, i: number) => (
                        <li key={i}>{e.symbol ?? "?"}: {formatScanError(e)}</li>
                      ))}
                      {(result as any).scanErrors.length > 50 && (
                        <li className="opacity-70">…and {(result as any).scanErrors.length - 50} more</li>
                      )}
                    </ul>
                  </details>
                </div>
              )}

              {/* No results */}
              {result.results?.length === 0 && (
                <div className="bg-white rounded-xl border border-gray-200 p-10 text-center shadow-sm">
                  <Target className="w-10 h-10 mx-auto mb-3 text-gray-300" />
                  <p className="font-semibold text-gray-600">No stocks matched</p>
                  <p className="text-sm text-gray-400 mt-1">Try relaxing conditions or expanding the universe</p>
                  <button onClick={() => setRightPanel("builder")}
                    className="mt-4 px-4 py-2 bg-indigo-50 text-indigo-600 rounded-lg text-sm font-medium hover:bg-indigo-100 transition">
                    Edit Conditions
                  </button>
                </div>
              )}

              {/* Result rows */}
              {result.results?.length > 0 && (
                <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                  <div className="px-5 py-3 bg-gray-50 border-b border-gray-100 flex items-center justify-between">
                    <span className="text-sm font-semibold text-gray-700">{result.results.length} matching stocks</span>
                    <span className="text-xs text-gray-400">Logic: {result.logic}</span>
                  </div>
                  <div className="divide-y divide-gray-50 dark:divide-slate-800/80">
                    {result.results.map((r: any, i: number) => (
                      <div key={i} className="px-5 py-4 hover:bg-gray-50 transition">
                        <div className="flex items-center justify-between gap-4">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-3 flex-wrap">
                              <span className="font-bold text-gray-900 text-base">{r.symbol}</span>
                              <ChartButton symbol={r.symbol} />
                              <span className={`flex items-center gap-1 text-sm font-semibold ${r.pChange >= 0 ? "text-green-600" : "text-red-500"}`}>
                                {r.pChange >= 0 ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                                {r.pChange >= 0 ? "+" : ""}{r.pChange?.toFixed(2)}%
                              </span>
                              <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">
                                {r.conditionsMatched}/{r.totalConditions} met
                              </span>
                              {/* Hidden Gem Score — only present on results
                                  from a "Hidden Gems" category scanner (backend
                                  attaches the field selectively, so absence
                                  means "this scanner doesn't compute it"). */}
                              {r.hiddenGemScore != null && (
                                <HiddenGemScoreBadge
                                  score={r.hiddenGemScore}
                                  breakdown={r.hiddenGemBreakdown}
                                />
                              )}
                              {/* Exit Plan — universally useful, shown on
                                  every result row regardless of category. */}
                              <ExitPlanButton symbol={r.symbol} currentPrice={r.lastPrice} />
                            </div>

                            {/* Matched condition chips */}
                            <div className="flex flex-wrap gap-1 mt-2">
                              {r.matchedConditions?.map((mc: string, j: number) => (
                                <span key={j} className="inline-flex items-center gap-1 text-xs bg-green-50 text-green-700 border border-green-100 px-2 py-0.5 rounded-full">
                                  <CheckCircle2 className="w-3 h-3 flex-shrink-0" /> {mc}
                                </span>
                              ))}
                            </div>
                          </div>

                          <div className="text-right flex-shrink-0">
                            <p className="font-bold text-gray-900 text-lg">₹{r.lastPrice?.toFixed(2)}</p>
                            <div className="mt-1">
                              <div className="w-20 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                                <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${r.score}%` }} />
                              </div>
                              <p className="text-xs text-indigo-600 mt-0.5 font-medium">{r.score}% match</p>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── EMPTY STATE ────────────────────────────────────────────────── */}
          {rightPanel === "empty" && (
            <div className="h-full flex items-center justify-center min-h-64">
              <div className="text-center text-gray-400 max-w-xs">
                <BarChart2 className="w-14 h-14 mx-auto mb-4 opacity-20" />
                <h3 className="font-semibold text-gray-500 text-base">Select a scanner to run</h3>
                <p className="text-sm mt-1">Click "Run Scan" on any scanner to see results here, or build a new one</p>
                <button onClick={startNew}
                  className="mt-4 flex items-center gap-2 mx-auto px-4 py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-600 rounded-lg text-sm font-medium transition">
                  <Plus className="w-4 h-4" /> Build a Scanner
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
