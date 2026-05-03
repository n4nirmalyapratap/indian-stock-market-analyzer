import { useEffect, useRef, useState, useCallback } from "react";
import * as echarts from "echarts";
import {
  calcEMA, calcSMA, calcWMA, calcHMA, calcVWMA, calcDEMA, calcTEMA,
  calcRSI, calcMACD, calcBollingerBands, calcDonchian, calcKeltner,
  calcATR, calcPSAR, calcSupertrend,
  calcStochastic, calcStochRSI, calcCCI, calcWilliamsR, calcMFI,
  calcOBV, calcROC, calcAO, calcCMF, calcTRIX, calcADX,
} from "@/lib/indicators";
import { fetchApi } from "@/lib/api";

export type DrawingTool =
  "none" |
  "trendline" | "ray" | "extendedline" |
  "hline" | "hray" | "vline" | "crossline" |
  "rectangle" | "circle" | "ellipse" |
  "parallelch" | "pitchfork" |
  "fibretracement" | "fibextension" | "fibtimezone" | "fibfan" |
  "gannfan" | "gannbox" |
  "longposition" | "shortposition" |
  "cycliclines" |
  "arrowmarker" | "arrowmarkup" | "arrowmarkdown" |
  "flag" | "measure" | "note" |
  "eraser";
export type ChartType = "candles" | "bars" | "hollow" | "line" | "line_markers" | "step" | "area" | "baseline" | "columns" | "ha";

export interface Drawing {
  id: string;
  shape: Record<string, unknown>;
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface Props {
  panelId: string;
  symbol: string;
  symbolName?: string;
  periodCfg: { p: string; i: string; start?: string; end?: string };
  drawingTool: DrawingTool;
  chartType: ChartType;
  indicators: Set<string>;
  isActive: boolean;
  onIndicatorRemove?: (key: string) => void;
  drawings: Drawing[];
  onDrawingAdd: (d: Drawing) => void;
  onDrawingErase: (id: string) => void;
  onClearDrawings?: () => void;
  onActivate: () => void;
  onDrawingDone?: () => void;
  onDrawingUpdate?: (id: string, shape: Record<string, unknown>) => void;
  theme: "dark" | "light";
}

const DRAW_CLR = "#6366f1";

function getThemeColors(theme: "dark" | "light") {
  const d = theme === "dark";
  return {
    bg:      d ? "#131722"                : "#ffffff",
    grid:    d ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.07)",
    text:    d ? "#787b86"                : "#9ca3af",
    cross:   d ? "rgba(255,255,255,0.55)" : "rgba(0,0,0,0.5)",
    labBg:   d ? "#2a2e39"                : "#e0e4ef",
    labText: d ? "#d1d4dc"                : "#131722",
    tipBg:   d ? "#1e2130"                : "#f5f7fc",
    tipBor:  d ? "#2a2e39"                : "#d0d4e0",
    tipText: d ? "#d1d4dc"                : "#131722",
    dimBg:   d ? "rgba(19,23,34,0.65)"    : "rgba(240,243,250,0.7)",
    ctxBg:   d ? "#1e2130"                : "#f0f2f8",
    ctxBor:  d ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.12)",
    headBor: d ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.08)",
    symTxt:  d ? "#ffffff"                : "#131722",
    muTxt:   d ? "#9ca3af"                : "#6b7280",
    ohlcVal: d ? "#ffffff"                : "#1e293b",
  };
}

// ─── Indicator catalog ──────────────────────────────────────────────────────
// One entry per supported indicator. `compute()` returns ECharts series specs
// (without xAxis/yAxisIndex — those are assigned dynamically by the chart
// renderer) plus a `cache` map of named series for pill-value lookup.

export interface IndicatorInput {
  highs: number[]; lows: number[]; closes: number[]; volumes: number[];
}

export interface IndicatorComputed {
  // ECharts series specs minus xAxis/yAxisIndex (added by renderer)
  series: Record<string, any>[];
  // Named cached series for pill value display (key -> array)
  cache: Record<string, (number | null)[]>;
}

export interface IndicatorDef {
  key: string;
  label: string;
  pillColor: string;
  group: "Moving Averages" | "Channels & Bands" | "Trend / Volatility" | "Oscillators" | "Volume";
  paneOwn: boolean;        // true = own sub-pane (oscillator); false = overlay on price
  needsVolume?: boolean;   // skip if symbol has zero volume (e.g. some indices)
  yMin?: number; yMax?: number;
  guides?: { value: number; color: string }[];
  pillSeries?: string;     // cache key to display in pill (default "main")
  pillDigits?: number;     // decimals for pill (default 2 for oscillators, price-aware otherwise)
  compute(in_: IndicatorInput): IndicatorComputed;
}

// Helper for a simple single-line overlay
function lineSeries(name: string, data: (number | null)[], color: string, width = 1.5, dashed = false) {
  return {
    name, type: "line", data, showSymbol: false, connectNulls: false,
    lineStyle: { color, width, ...(dashed ? { type: "dashed" } : {}) },
  };
}

const IND_CATALOG: IndicatorDef[] = [
  // ─── Moving Averages ─────────────────────────────────────────────────────
  { key: "ema9",   label: "EMA 9",   pillColor: "#f59e0b", group: "Moving Averages", paneOwn: false,
    compute: ({ closes }) => { const v = calcEMA(closes, 9);   return { series: [lineSeries("EMA 9",   v, "#f59e0b")], cache: { main: v } }; } },
  { key: "ema21",  label: "EMA 21",  pillColor: "#6366f1", group: "Moving Averages", paneOwn: false,
    compute: ({ closes }) => { const v = calcEMA(closes, 21);  return { series: [lineSeries("EMA 21",  v, "#6366f1")], cache: { main: v } }; } },
  { key: "ema50",  label: "EMA 50",  pillColor: "#10b981", group: "Moving Averages", paneOwn: false,
    compute: ({ closes }) => { const v = calcEMA(closes, 50);  return { series: [lineSeries("EMA 50",  v, "#10b981")], cache: { main: v } }; } },
  { key: "ema200", label: "EMA 200", pillColor: "#ef4444", group: "Moving Averages", paneOwn: false,
    compute: ({ closes }) => { const v = calcEMA(closes, 200); return { series: [lineSeries("EMA 200", v, "#ef4444")], cache: { main: v } }; } },
  { key: "sma20",  label: "SMA 20",  pillColor: "#22d3ee", group: "Moving Averages", paneOwn: false,
    compute: ({ closes }) => { const v = calcSMA(closes, 20);  return { series: [lineSeries("SMA 20",  v, "#22d3ee")], cache: { main: v } }; } },
  { key: "sma50",  label: "SMA 50",  pillColor: "#a78bfa", group: "Moving Averages", paneOwn: false,
    compute: ({ closes }) => { const v = calcSMA(closes, 50);  return { series: [lineSeries("SMA 50",  v, "#a78bfa")], cache: { main: v } }; } },
  { key: "wma20",  label: "WMA 20",  pillColor: "#facc15", group: "Moving Averages", paneOwn: false,
    compute: ({ closes }) => { const v = calcWMA(closes, 20);  return { series: [lineSeries("WMA 20",  v, "#facc15")], cache: { main: v } }; } },
  { key: "hma20",  label: "HMA 20",  pillColor: "#a3e635", group: "Moving Averages", paneOwn: false,
    compute: ({ closes }) => { const v = calcHMA(closes, 20);  return { series: [lineSeries("HMA 20",  v, "#a3e635")], cache: { main: v } }; } },
  { key: "vwma20", label: "VWMA 20", pillColor: "#fb7185", group: "Moving Averages", paneOwn: false, needsVolume: true,
    compute: ({ closes, volumes }) => { const v = calcVWMA(closes, volumes, 20); return { series: [lineSeries("VWMA 20", v, "#fb7185")], cache: { main: v } }; } },
  { key: "dema21", label: "DEMA 21", pillColor: "#f472b6", group: "Moving Averages", paneOwn: false,
    compute: ({ closes }) => { const v = calcDEMA(closes, 21); return { series: [lineSeries("DEMA 21", v, "#f472b6")], cache: { main: v } }; } },
  { key: "tema21", label: "TEMA 21", pillColor: "#fdba74", group: "Moving Averages", paneOwn: false,
    compute: ({ closes }) => { const v = calcTEMA(closes, 21); return { series: [lineSeries("TEMA 21", v, "#fdba74")], cache: { main: v } }; } },

  // ─── Channels & Bands ────────────────────────────────────────────────────
  { key: "bb", label: "BB (20,2)", pillColor: "#3b82f6", group: "Channels & Bands", paneOwn: false, pillSeries: "middle",
    compute: ({ closes }) => {
      const b = calcBollingerBands(closes);
      return {
        series: [
          lineSeries("BB+", b.upper,  "#3b82f6", 1, true),
          lineSeries("BBm", b.middle, "#64748b", 1, true),
          lineSeries("BB-", b.lower,  "#3b82f6", 1, true),
        ],
        cache: { upper: b.upper, middle: b.middle, lower: b.lower },
      };
    } },
  { key: "donchian", label: "Donchian (20)", pillColor: "#0ea5e9", group: "Channels & Bands", paneOwn: false, pillSeries: "middle",
    compute: ({ highs, lows }) => {
      const d = calcDonchian(highs, lows);
      return {
        series: [
          lineSeries("DC+", d.upper,  "#0ea5e9", 1, true),
          lineSeries("DCm", d.middle, "#64748b", 1, true),
          lineSeries("DC-", d.lower,  "#0ea5e9", 1, true),
        ],
        cache: { upper: d.upper, middle: d.middle, lower: d.lower },
      };
    } },
  { key: "keltner", label: "Keltner (20)", pillColor: "#22c55e", group: "Channels & Bands", paneOwn: false, pillSeries: "middle",
    compute: ({ highs, lows, closes }) => {
      const k = calcKeltner(highs, lows, closes);
      return {
        series: [
          lineSeries("KC+", k.upper,  "#22c55e", 1, true),
          lineSeries("KCm", k.middle, "#64748b", 1, true),
          lineSeries("KC-", k.lower,  "#22c55e", 1, true),
        ],
        cache: { upper: k.upper, middle: k.middle, lower: k.lower },
      };
    } },

  // ─── Trend overlays ──────────────────────────────────────────────────────
  { key: "psar", label: "PSAR", pillColor: "#eab308", group: "Trend / Volatility", paneOwn: false,
    compute: ({ highs, lows }) => {
      const v = calcPSAR(highs, lows);
      return {
        // Plot SAR dots — small scatter via "line" with symbols only
        series: [{
          name: "PSAR", type: "scatter", data: v.map(p => p === null ? "-" : p),
          symbolSize: 3, itemStyle: { color: "#eab308" },
        }],
        cache: { main: v },
      };
    } },
  { key: "supertrend", label: "Supertrend (10,3)", pillColor: "#a855f7", group: "Trend / Volatility", paneOwn: false,
    compute: ({ highs, lows, closes }) => {
      const st = calcSupertrend(highs, lows, closes, 10, 3);
      // Split into up/down line segments so trend reversal isn't a single zig-zag
      const upArr:   (number | null)[] = st.trend.map((v, i) => st.isUp[i] === true  ? v : null);
      const downArr: (number | null)[] = st.trend.map((v, i) => st.isUp[i] === false ? v : null);
      return {
        series: [
          lineSeries("ST↑", upArr,   "#22c55e", 1.8),
          lineSeries("ST↓", downArr, "#ef4444", 1.8),
        ],
        cache: { main: st.trend },
      };
    } },

  // ─── Oscillators (each gets own sub-pane) ────────────────────────────────
  { key: "rsi", label: "RSI (14)", pillColor: "#f59e0b", group: "Oscillators", paneOwn: true,
    yMin: 0, yMax: 100, guides: [{ value: 70, color: "rgba(239,68,68,0.35)" }, { value: 30, color: "rgba(38,166,154,0.35)" }],
    compute: ({ closes }) => { const v = calcRSI(closes); return { series: [lineSeries("RSI", v, "#f59e0b")], cache: { main: v } }; } },
  { key: "macd", label: "MACD (12,26,9)", pillColor: "#2962ff", group: "Oscillators", paneOwn: true, pillSeries: "macd",
    compute: ({ closes }) => {
      const m = calcMACD(closes);
      return {
        series: [
          lineSeries("MACD",   m.macd,   "#2962ff", 1.3),
          lineSeries("Signal", m.signal, "#ff6d00", 1.3),
          { name: "Hist", type: "bar", barMaxWidth: 5,
            data: m.histogram.map(v => ({ value: v, itemStyle: { color: (v ?? 0) >= 0 ? "rgba(38,166,154,0.7)" : "rgba(239,83,80,0.7)" } })) },
        ],
        cache: { macd: m.macd, signal: m.signal, hist: m.histogram },
      };
    } },
  { key: "stoch", label: "Stoch (14,3)", pillColor: "#06b6d4", group: "Oscillators", paneOwn: true,
    yMin: 0, yMax: 100, guides: [{ value: 80, color: "rgba(239,68,68,0.35)" }, { value: 20, color: "rgba(38,166,154,0.35)" }],
    pillSeries: "k",
    compute: ({ highs, lows, closes }) => {
      const s = calcStochastic(highs, lows, closes);
      return {
        series: [lineSeries("%K", s.k, "#06b6d4", 1.4), lineSeries("%D", s.d, "#f97316", 1.2)],
        cache: { k: s.k, d: s.d },
      };
    } },
  { key: "stochrsi", label: "Stoch RSI", pillColor: "#84cc16", group: "Oscillators", paneOwn: true,
    yMin: 0, yMax: 100, guides: [{ value: 80, color: "rgba(239,68,68,0.35)" }, { value: 20, color: "rgba(38,166,154,0.35)" }],
    pillSeries: "k",
    compute: ({ closes }) => {
      const s = calcStochRSI(closes);
      return {
        series: [lineSeries("%K", s.k, "#84cc16", 1.4), lineSeries("%D", s.d, "#f97316", 1.2)],
        cache: { k: s.k, d: s.d },
      };
    } },
  { key: "cci", label: "CCI (20)", pillColor: "#c084fc", group: "Oscillators", paneOwn: true,
    guides: [{ value: 100, color: "rgba(239,68,68,0.35)" }, { value: -100, color: "rgba(38,166,154,0.35)" }, { value: 0, color: "rgba(120,123,134,0.35)" }],
    compute: ({ highs, lows, closes }) => { const v = calcCCI(highs, lows, closes); return { series: [lineSeries("CCI", v, "#c084fc")], cache: { main: v } }; } },
  { key: "willr", label: "Williams %R", pillColor: "#fb923c", group: "Oscillators", paneOwn: true,
    yMin: -100, yMax: 0, guides: [{ value: -20, color: "rgba(239,68,68,0.35)" }, { value: -80, color: "rgba(38,166,154,0.35)" }],
    compute: ({ highs, lows, closes }) => { const v = calcWilliamsR(highs, lows, closes); return { series: [lineSeries("Wm%R", v, "#fb923c")], cache: { main: v } }; } },
  { key: "atr", label: "ATR (14)", pillColor: "#94a3b8", group: "Oscillators", paneOwn: true,
    compute: ({ highs, lows, closes }) => { const v = calcATR(highs, lows, closes); return { series: [lineSeries("ATR", v, "#94a3b8")], cache: { main: v } }; } },
  { key: "adx", label: "ADX (14)", pillColor: "#f43f5e", group: "Oscillators", paneOwn: true,
    yMin: 0, yMax: 100, guides: [{ value: 25, color: "rgba(120,123,134,0.35)" }],
    pillSeries: "adx",
    compute: ({ highs, lows, closes }) => {
      const a = calcADX(highs, lows, closes);
      return {
        series: [
          lineSeries("ADX", a.adx, "#f43f5e", 1.5),
          lineSeries("+DI", a.plusDI,  "#22c55e", 1.1),
          lineSeries("-DI", a.minusDI, "#ef4444", 1.1),
        ],
        cache: { adx: a.adx, plusDI: a.plusDI, minusDI: a.minusDI },
      };
    } },
  { key: "mfi", label: "MFI (14)", pillColor: "#14b8a6", group: "Oscillators", paneOwn: true, needsVolume: true,
    yMin: 0, yMax: 100, guides: [{ value: 80, color: "rgba(239,68,68,0.35)" }, { value: 20, color: "rgba(38,166,154,0.35)" }],
    compute: ({ highs, lows, closes, volumes }) => { const v = calcMFI(highs, lows, closes, volumes); return { series: [lineSeries("MFI", v, "#14b8a6")], cache: { main: v } }; } },
  { key: "roc", label: "ROC (12)", pillColor: "#7dd3fc", group: "Oscillators", paneOwn: true,
    guides: [{ value: 0, color: "rgba(120,123,134,0.35)" }],
    compute: ({ closes }) => { const v = calcROC(closes); return { series: [lineSeries("ROC", v, "#7dd3fc")], cache: { main: v } }; } },
  { key: "trix", label: "TRIX (14)", pillColor: "#bef264", group: "Oscillators", paneOwn: true,
    guides: [{ value: 0, color: "rgba(120,123,134,0.35)" }],
    compute: ({ closes }) => { const v = calcTRIX(closes); return { series: [lineSeries("TRIX", v, "#bef264")], cache: { main: v } }; } },
  { key: "ao", label: "Awesome Osc.", pillColor: "#e879f9", group: "Oscillators", paneOwn: true,
    compute: ({ highs, lows }) => {
      const v = calcAO(highs, lows);
      // Bar chart, green when rising vs prev, red when falling
      const data = v.map((cur, i) => {
        const prev = i > 0 ? v[i - 1] : null;
        const up = cur !== null && prev !== null ? cur >= prev : (cur ?? 0) >= 0;
        return { value: cur, itemStyle: { color: up ? "rgba(38,166,154,0.7)" : "rgba(239,83,80,0.7)" } };
      });
      return {
        series: [{ name: "AO", type: "bar", data, barMaxWidth: 5 }],
        cache: { main: v },
      };
    } },
  { key: "cmf", label: "CMF (20)", pillColor: "#fcd34d", group: "Oscillators", paneOwn: true, needsVolume: true,
    guides: [{ value: 0, color: "rgba(120,123,134,0.35)" }],
    compute: ({ highs, lows, closes, volumes }) => { const v = calcCMF(highs, lows, closes, volumes); return { series: [lineSeries("CMF", v, "#fcd34d")], cache: { main: v } }; } },
  { key: "obv", label: "OBV", pillColor: "#fda4af", group: "Volume", paneOwn: true,
    compute: ({ closes, volumes }) => { const v = calcOBV(closes, volumes); return { series: [lineSeries("OBV", v, "#fda4af")], cache: { main: v } }; } },
];

const IND_BY_KEY: Record<string, IndicatorDef> = Object.fromEntries(IND_CATALOG.map(d => [d.key, d]));

// Public catalog for menu rendering in TradingPlatform (typed metadata only)
export const INDICATOR_CATALOG = IND_CATALOG.map(d => ({
  key: d.key, label: d.label, pillColor: d.pillColor, group: d.group, paneOwn: d.paneOwn, needsVolume: !!d.needsVolume,
}));

function uid() { return Math.random().toString(36).slice(2, 9); }

const INTRADAY_INTERVALS = new Set(["1m", "2m", "5m", "15m", "30m", "60m", "90m"]);

const IST_OFFSET_SEC = 5.5 * 3600; // UTC+5:30
const MONTHS_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const DAYS_SHORT   = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];

// Convert Unix timestamp to IST date string: "2026-04-02" or "2026-04-02 09:15"
function toDateStr(ts: number, showTime = true): string {
  const d = new Date((ts + IST_OFFSET_SEC) * 1000);
  const dateISO = d.toISOString().slice(0, 10);
  if (!showTime) return dateISO;
  const hh = d.getUTCHours();
  const mm = d.getUTCMinutes();
  return (hh === 0 && mm === 0)
    ? dateISO
    : `${dateISO} ${String(hh).padStart(2,"0")}:${String(mm).padStart(2,"0")}`;
}

// Short label for x-axis ticks: "09:15" for intraday, "02 Apr" for daily
function fmtXLabel(dateStr: string, showTime: boolean): string {
  const [datePart, timePart] = dateStr.split(" ");
  if (showTime && timePart) return timePart;
  const parts = datePart.split("-");
  const mo = Number(parts[1]);
  const dd = parts[2];
  return `${dd} ${MONTHS_SHORT[mo - 1]}`;
}

// Full label for the crosshair bubble on x-axis: "Thu 02 Apr '26  09:15"
function fmtCrosshairLabel(dateStr: string): string {
  const [datePart, timePart] = dateStr.split(" ");
  const parts = datePart.split("-").map(Number);
  const [year, mo, dd] = parts;
  const d = new Date(`${datePart}T12:00:00Z`);
  const dayName = DAYS_SHORT[d.getUTCDay()];
  const monthName = MONTHS_SHORT[mo - 1];
  const yr = String(year).slice(2);
  const dayStr = String(dd).padStart(2,"0");
  return timePart
    ? `${dayName} ${dayStr} ${monthName} '${yr}  ${timePart}`
    : `${dayName} ${dayStr} ${monthName} '${yr}`;
}

function fmtVol(v: number): string {
  if (v >= 1e9) return (v / 1e9).toFixed(2) + "B";
  if (v >= 1e6) return (v / 1e6).toFixed(2) + "M";
  if (v >= 1e3) return (v / 1e3).toFixed(1) + "K";
  return String(v);
}

function fmtPrice(v: number): string {
  return v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ── Heikin Ashi transform ─────────────────────────────────────────────────────
export function computeHA(cs: Candle[]): Candle[] {
  const out: Candle[] = [];
  for (let i = 0; i < cs.length; i++) {
    const c = cs[i];
    const haClose = (c.open + c.high + c.low + c.close) / 4;
    const haOpen = i === 0
      ? (c.open + c.close) / 2
      : (out[i - 1].open + out[i - 1].close) / 2;
    out.push({ ...c, open: haOpen, close: haClose, high: Math.max(c.high, haOpen, haClose), low: Math.min(c.low, haOpen, haClose) });
  }
  return out;
}

// ── SVG overlay helpers ────────────────────────────────────────────────────────

interface SvgLine    { type: "line";    x1: number; y1: number; x2: number; y2: number; dash?: boolean; color?: string; width?: number }
interface SvgRect    { type: "rect";    x: number;  y: number;  w: number;  h: number;  fill?: string; stroke?: string }
interface SvgCircle  { type: "circle";  cx: number; cy: number; r: number;  fill?: string }
interface SvgEllipse { type: "ellipse"; cx: number; cy: number; rx: number; ry: number; fill?: string }
interface SvgText    { type: "text";    x: number;  y: number;  text: string; anchor?: "start"|"middle"|"end"; size?: number; color?: string }
interface SvgPath    { type: "path";    d: string;  fill?: string; stroke?: string }
type SvgEl = SvgLine | SvgRect | SvgCircle | SvgEllipse | SvgText | SvgPath;
interface SvgPixels { id: string; els: SvgEl[] }

// GL / GR must stay in sync with the grid config in renderChart below
const CHART_GL = 8, CHART_GR = 70;

function getGridBounds(chart: echarts.ECharts, candles: Candle[]) {
  // Use chart.getWidth() for reliable x bounds — avoids off-screen pixels after dataZoom
  const W = chart.getWidth();
  const leftX  = CHART_GL;
  const rightX = W - CHART_GR;
  // Derive y bounds from the full data range; convertToPixel respects current zoom scale
  const highs = candles.map(c => c.high);
  const lows  = candles.map(c => c.low);
  const maxH  = highs.length ? Math.max(...highs) : 0;
  const minL  = lows.length  ? Math.min(...lows)  : 0;
  const [, topY] = chart.convertToPixel({ gridIndex: 0 }, [0, maxH]);
  const [, botY] = chart.convertToPixel({ gridIndex: 0 }, [0, minL]);
  return { leftX, rightX, topY: Math.min(topY, botY), botY: Math.max(topY, botY) };
}

// Extend a ray (px,py) in direction (nx,ny) until it hits the box boundary [x0,y0,x1,y1]
export function extendRay(px: number, py: number, nx: number, ny: number, x0: number, y0: number, x1: number, y1: number): [number, number] {
  let tMin = 1e9;
  if (nx > 0)  tMin = Math.min(tMin, (x1 - px) / nx);
  if (nx < 0)  tMin = Math.min(tMin, (x0 - px) / nx);
  if (ny > 0)  tMin = Math.min(tMin, (y1 - py) / ny);
  if (ny < 0)  tMin = Math.min(tMin, (y0 - py) / ny);
  return [px + nx * tMin, py + ny * tMin];
}

function shapeToPixels(
  shape: Record<string, unknown>,
  chart: echarts.ECharts,
  candles: Candle[],
): SvgEl[] | null {
  const s = shape as any;
  const b = getGridBounds(chart, candles);
  const W = chart.getWidth(), H = chart.getHeight();

  // ── Lines ──────────────────────────────────────────────────────────────────
  if (s.type === "hline") {
    const [, py0] = chart.convertToPixel({ gridIndex: 0 }, [0, s.y]);
    // y1 is set when user rotates the line by dragging the right handle
    const py1 = typeof s.y1 === "number"
      ? (chart.convertToPixel({ gridIndex: 0 }, [0, s.y1]) as [number, number])[1]
      : py0;
    const lw = typeof s.width === "number" ? s.width : 1.5;
    return [{ type: "line", x1: b.leftX, y1: py0, x2: b.rightX, y2: py1, width: lw }];
  }
  if (s.type === "hray") {
    const [startX, py0] = chart.convertToPixel({ gridIndex: 0 }, [s.xIdx, s.y]);
    // Clip start to grid left edge so the ray doesn't bleed into the axis
    const x1 = Math.max(startX, b.leftX);
    // y1 is set when user rotates: the y at the right edge
    const py1 = typeof s.y1 === "number"
      ? (chart.convertToPixel({ gridIndex: 0 }, [0, s.y1]) as [number, number])[1]
      : py0;
    const lw = typeof s.width === "number" ? s.width : 1.5;
    return [{ type: "line", x1, y1: py0, x2: b.rightX, y2: py1, width: lw }];
  }
  if (s.type === "vline") {
    const [px] = chart.convertToPixel({ gridIndex: 0 }, [s.xIdx, 0]);
    return [{ type: "line", x1: px, y1: b.topY, x2: px, y2: b.botY }];
  }
  if (s.type === "crossline") {
    const [px, py] = chart.convertToPixel({ gridIndex: 0 }, [s.xIdx, s.y]);
    return [
      { type: "line", x1: b.leftX, y1: py, x2: b.rightX, y2: py },
      { type: "line", x1: px, y1: b.topY, x2: px, y2: b.botY },
    ];
  }
  if (s.type === "trendline") {
    const [px0, py0] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [px1, py1] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    return [{ type: "line", x1: px0, y1: py0, x2: px1, y2: py1 }];
  }
  if (s.type === "ray") {
    const [px0, py0] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [px1, py1] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    const dx = px1 - px0, dy = py1 - py0;
    const len = Math.hypot(dx, dy);
    if (len < 1) return [{ type: "line", x1: px0, y1: py0, x2: px1, y2: py1 }];
    // Clip to grid bounds (not full SVG) so ray doesn't extend into axis areas
    const [ex, ey] = extendRay(px0, py0, dx / len, dy / len, b.leftX, b.topY, b.rightX, b.botY);
    return [{ type: "line", x1: px0, y1: py0, x2: ex, y2: ey }];
  }
  if (s.type === "extendedline") {
    const [px0, py0] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [px1, py1] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    const dx = px1 - px0, dy = py1 - py0;
    const len = Math.hypot(dx, dy);
    if (len < 1) return [{ type: "line", x1: px0, y1: py0, x2: px1, y2: py1 }];
    const nx = dx / len, ny = dy / len;
    const [ex1, ey1] = extendRay(px0, py0,  nx,  ny, b.leftX, b.topY, b.rightX, b.botY);
    const [ex2, ey2] = extendRay(px0, py0, -nx, -ny, b.leftX, b.topY, b.rightX, b.botY);
    return [{ type: "line", x1: ex2, y1: ey2, x2: ex1, y2: ey1 }];
  }

  // ── Shapes ─────────────────────────────────────────────────────────────────
  if (s.type === "rectangle") {
    const [px0, py0] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [px1, py1] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    return [{ type: "rect", x: Math.min(px0, px1), y: Math.min(py0, py1), w: Math.abs(px1 - px0), h: Math.abs(py1 - py0) }];
  }
  if (s.type === "circle") {
    const [cx, cy] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [ex, ey] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    const r = Math.hypot(ex - cx, ey - cy);
    return [{ type: "circle", cx, cy, r, fill: "rgba(99,102,241,0.08)" }];
  }
  if (s.type === "ellipse") {
    const [px0, py0] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [px1, py1] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    const cx = (px0 + px1) / 2, cy = (py0 + py1) / 2;
    return [{ type: "ellipse", cx, cy, rx: Math.abs(px1 - px0) / 2, ry: Math.abs(py1 - py0) / 2, fill: "rgba(99,102,241,0.08)" }];
  }

  // ── Channels ───────────────────────────────────────────────────────────────
  if (s.type === "parallelch") {
    const [px0, py0] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [px1, py1] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    const [, py2] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y2 ?? s.y0]);
    if (Math.hypot(px1 - px0, py1 - py0) < 1) return null;
    const off = py2 - py0;
    return [
      { type: "line", x1: px0, y1: py0,         x2: px1, y2: py1 },
      { type: "line", x1: px0, y1: py0 + off,   x2: px1, y2: py1 + off },
      { type: "line", x1: px0, y1: py0 + off/2, x2: px1, y2: py1 + off/2, dash: true, color: DRAW_CLR + "88" },
    ];
  }
  if (s.type === "pitchfork") {
    const [px0, py0] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [px1, py1] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    const dx = px1 - px0, dy = py1 - py0;
    const len = Math.hypot(dx, dy);
    if (len < 1) return null;
    const nx = dx / len, ny = dy / len;
    const frac = typeof s.spreadFrac === "number" ? s.spreadFrac : 0.3;
    const spread = len * frac;
    const perpX = -ny, perpY = nx;
    // Handle: from start to end (not extended); prongs extend only forward
    const [f1ex, f1ey] = extendRay(px1 + perpX * spread, py1 + perpY * spread, nx, ny, 0, 0, W, H);
    const [f2ex, f2ey] = extendRay(px1 - perpX * spread, py1 - perpY * spread, nx, ny, 0, 0, W, H);
    return [
      { type: "line", x1: px0, y1: py0, x2: px1, y2: py1 },
      { type: "line", x1: px1 + perpX * spread, y1: py1 + perpY * spread, x2: f1ex, y2: f1ey },
      { type: "line", x1: px1 - perpX * spread, y1: py1 - perpY * spread, x2: f2ex, y2: f2ey },
      { type: "line", x1: px1 + perpX * spread, y1: py1 + perpY * spread,
                      x2: px1 - perpX * spread, y2: py1 - perpY * spread, dash: true, color: DRAW_CLR + "88" },
    ];
  }

  // ── Fibonacci ──────────────────────────────────────────────────────────────
  if (s.type === "fibretracement" || s.type === "fibextension") {
    const [px0, py0] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [px1, py1] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    const xLeft = Math.min(px0, px1), xRight = Math.max(px0, px1);
    const levels = s.type === "fibextension"
      ? [0, 0.236, 0.382, 0.618, 1, 1.272, 1.618, 2.618]
      : [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];
    const colors = ["#ef4444","#f97316","#eab308","#22c55e","#3b82f6","#8b5cf6","#ef4444","#f97316"];
    const els: SvgEl[] = [
      { type: "line", x1: px0, y1: py0, x2: px1, y2: py1, dash: true, color: DRAW_CLR + "66" },
    ];
    for (let i = 0; i < levels.length; i++) {
      const ratio = levels[i];
      const py = py0 + (py1 - py0) * ratio;
      const col = colors[i % colors.length];
      els.push({ type: "line", x1: xLeft, y1: py, x2: xRight, y2: py, color: col });
      els.push({ type: "text", x: xRight + 4, y: py - 3, text: `${(ratio * 100).toFixed(1)}%  ₹${fmtPrice(s.y0 + (s.y1 - s.y0) * ratio)}`, anchor: "start", size: 9, color: col });
    }
    return els;
  }
  if (s.type === "fibtimezone") {
    const [startX] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [endX]   = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    const interval = endX - startX;
    if (Math.abs(interval) < 2) return null;
    const fibNums = [1, 2, 3, 5, 8, 13, 21, 34, 55];
    const els: SvgEl[] = [{ type: "line", x1: startX, y1: b.topY, x2: startX, y2: b.botY }];
    for (const n of fibNums) {
      const x = startX + n * interval;
      if (x > W + 50 || x < -50) continue;
      els.push({ type: "line", x1: x, y1: b.topY, x2: x, y2: b.botY, dash: true });
      els.push({ type: "text", x: x + 3, y: b.topY + 14, text: String(n), anchor: "start", size: 9 });
    }
    return els;
  }
  if (s.type === "fibfan") {
    const [px0, py0] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [px1, py1] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    const dy = py1 - py0;
    const ratios = [0.236, 0.382, 0.5, 0.618, 0.786];
    const colors = ["#f97316","#eab308","#22c55e","#3b82f6","#8b5cf6"];
    const els: SvgEl[] = [];
    for (let i = 0; i < ratios.length; i++) {
      const ey = py0 + dy * ratios[i];
      els.push({ type: "line", x1: px0, y1: py0, x2: px1, y2: ey, dash: true, color: colors[i] });
      els.push({ type: "text", x: px1 + 4, y: ey, text: `${(ratios[i] * 100).toFixed(0)}%`, anchor: "start", size: 9, color: colors[i] });
    }
    return els.length ? els : null;
  }

  // ── Gann ───────────────────────────────────────────────────────────────────
  if (s.type === "gannfan") {
    const [px0, py0] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [px1, py1] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    const dy = py1 - py0;
    const RATIOS = [
      { r: 1/4, label: "1×4" }, { r: 1/3, label: "1×3" }, { r: 1/2, label: "1×2" },
      { r: 1,   label: "1×1" },
      { r: 2,   label: "2×1" }, { r: 3,   label: "3×1" }, { r: 4,   label: "4×1" },
    ];
    const els: SvgEl[] = [];
    for (const { r, label } of RATIOS) {
      const ey = py0 + dy * r;
      const isMain = r === 1;
      els.push({ type: "line", x1: px0, y1: py0, x2: px1, y2: ey,
        dash: !isMain, color: isMain ? DRAW_CLR : DRAW_CLR + "99" });
      els.push({ type: "text", x: px1 + 4, y: ey, text: label, anchor: "start", size: 8 });
    }
    return els;
  }
  if (s.type === "gannbox") {
    const [px0, py0] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [px1, py1] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    const minX = Math.min(px0, px1), maxX = Math.max(px0, px1);
    const minY = Math.min(py0, py1), maxY = Math.max(py0, py1);
    const w = maxX - minX, h = maxY - minY;
    return [
      { type: "rect", x: minX, y: minY, w, h, fill: "rgba(99,102,241,0.05)" },
      { type: "line", x1: minX, y1: minY, x2: maxX, y2: maxY, dash: true },
      { type: "line", x1: minX, y1: maxY, x2: maxX, y2: minY, dash: true },
      { type: "line", x1: minX, y1: (minY + maxY) / 2, x2: maxX, y2: (minY + maxY) / 2, dash: true, color: DRAW_CLR + "66" },
      { type: "line", x1: (minX + maxX) / 2, y1: minY, x2: (minX + maxX) / 2, y2: maxY, dash: true, color: DRAW_CLR + "66" },
    ];
  }

  // ── Forecasting ────────────────────────────────────────────────────────────
  if (s.type === "longposition" || s.type === "shortposition") {
    const isLong = s.type === "longposition";
    const [px0, py0] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [px1, py1] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    const stopPrice = s.y0 - (s.y1 - s.y0) * 0.5;
    const [, pyStop] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, stopPrice]);
    const left = Math.min(px0, px1), right = Math.max(px0, px1);
    const entryY = py0, targetY = py1, stopY = pyStop;
    return [
      { type: "rect", x: left, y: Math.min(entryY, targetY), w: right - left, h: Math.abs(targetY - entryY), fill: isLong ? "rgba(38,166,154,0.18)" : "rgba(239,83,80,0.18)", stroke: "none" },
      { type: "rect", x: left, y: Math.min(entryY, stopY),   w: right - left, h: Math.abs(stopY - entryY),   fill: isLong ? "rgba(239,83,80,0.18)" : "rgba(38,166,154,0.18)", stroke: "none" },
      { type: "line", x1: left, y1: entryY,  x2: right, y2: entryY, color: "#aaa" },
      { type: "line", x1: left, y1: targetY, x2: right, y2: targetY, color: isLong ? "#26a69a" : "#ef5350" },
      { type: "line", x1: left, y1: stopY,   x2: right, y2: stopY,   color: isLong ? "#ef5350" : "#26a69a", dash: true },
      { type: "text", x: left + 4, y: targetY - 4,  text: `T ₹${fmtPrice(s.y1 as number)}`, size: 9, color: isLong ? "#26a69a" : "#ef5350" },
      { type: "text", x: left + 4, y: entryY  + 11, text: `E ₹${fmtPrice(s.y0 as number)}`, size: 9, color: "#ccc" },
      { type: "text", x: left + 4, y: stopY   + 11, text: `S ₹${fmtPrice(stopPrice)}`,       size: 9, color: isLong ? "#ef5350" : "#26a69a" },
    ];
  }

  // ── Cycles ─────────────────────────────────────────────────────────────────
  if (s.type === "cycliclines") {
    const [px0] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [px1] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    const interval = Math.abs(px1 - px0);
    if (interval < 2) return null;
    const els: SvgEl[] = [{ type: "line", x1: px0, y1: b.topY, x2: px0, y2: b.botY }];
    for (let x = px0 + interval; x <= W + 10; x += interval) {
      els.push({ type: "line", x1: x, y1: b.topY, x2: x, y2: b.botY, dash: true });
    }
    for (let x = px0 - interval; x >= -10; x -= interval) {
      els.push({ type: "line", x1: x, y1: b.topY, x2: x, y2: b.botY, dash: true });
    }
    return els;
  }

  // ── Arrows ─────────────────────────────────────────────────────────────────
  if (s.type === "arrowmarker") {
    const [px, py] = chart.convertToPixel({ gridIndex: 0 }, [s.xIdx, s.y]);
    return [{ type: "path", d: `M${px - 12},${py} L${px + 12},${py} M${px + 6},${py - 6} L${px + 12},${py} L${px + 6},${py + 6}` }];
  }
  if (s.type === "arrowmarkup") {
    const [px, py] = chart.convertToPixel({ gridIndex: 0 }, [s.xIdx, s.y]);
    return [
      { type: "path", d: `M${px},${py + 12} L${px},${py - 12} M${px - 6},${py - 6} L${px},${py - 12} L${px + 6},${py - 6}` },
      { type: "path", d: `M${px - 6},${py + 16} L${px + 6},${py + 16}`, stroke: DRAW_CLR + "88" },
    ];
  }
  if (s.type === "arrowmarkdown") {
    const [px, py] = chart.convertToPixel({ gridIndex: 0 }, [s.xIdx, s.y]);
    return [
      { type: "path", d: `M${px},${py - 12} L${px},${py + 12} M${px - 6},${py + 6} L${px},${py + 12} L${px + 6},${py + 6}` },
      { type: "path", d: `M${px - 6},${py - 16} L${px + 6},${py - 16}`, stroke: DRAW_CLR + "88" },
    ];
  }

  // ── Misc ───────────────────────────────────────────────────────────────────
  if (s.type === "flag") {
    const [px, py] = chart.convertToPixel({ gridIndex: 0 }, [s.xIdx, s.y]);
    return [
      { type: "line", x1: px, y1: py, x2: px, y2: b.botY },
      { type: "path", d: `M${px},${py} L${px + 18},${py + 6} L${px},${py + 12} Z`, fill: DRAW_CLR + "88" },
    ];
  }
  if (s.type === "measure") {
    const [px0, py0] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [px1, py1] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    const minX = Math.min(px0, px1), maxX = Math.max(px0, px1);
    const minY = Math.min(py0, py1), maxY = Math.max(py0, py1);
    const w = maxX - minX, h = maxY - minY;
    const priceDiff = Math.abs((s.y1 as number) - (s.y0 as number));
    const barCount = Math.abs((s.x1Idx as number) - (s.x0Idx as number));
    const pricePct = (priceDiff / Math.max(s.y0 as number, s.y1 as number)) * 100;
    const isUp = (s.y1 as number) > (s.y0 as number);
    return [
      { type: "rect", x: minX, y: minY, w, h, fill: isUp ? "rgba(38,166,154,0.12)" : "rgba(239,83,80,0.12)" },
      { type: "text", x: minX + w / 2, y: minY + h / 2 - 8, text: `${isUp ? "+" : ""}${pricePct.toFixed(2)}%`, anchor: "middle", size: 10, color: isUp ? "#26a69a" : "#ef5350" },
      { type: "text", x: minX + w / 2, y: minY + h / 2 + 8, text: `${barCount} bars`, anchor: "middle", size: 9 },
    ];
  }
  if (s.type === "note") {
    const [px, py] = chart.convertToPixel({ gridIndex: 0 }, [s.xIdx, s.y]);
    const txt = String(s.text ?? "Note");
    const tw = Math.max(60, txt.length * 6.5 + 12);
    return [
      { type: "path", d: `M${px},${py} L${px + 8},${py - 10} L${px + tw},${py - 10} L${px + tw},${py - 28} L${px},${py - 28} Z`, fill: "rgba(30,33,48,0.9)", stroke: DRAW_CLR },
      { type: "text", x: px + 6, y: py - 15, text: txt, anchor: "start", size: 10 },
    ];
  }
  return null;
}

// ── Eraser hit-testing ────────────────────────────────────────────────────────

export function distToSegment(px: number, py: number, x1: number, y1: number, x2: number, y2: number): number {
  const dx = x2 - x1, dy = y2 - y1;
  const len2 = dx * dx + dy * dy;
  if (len2 === 0) return Math.hypot(px - x1, py - y1);
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / len2));
  return Math.hypot(px - x1 - t * dx, py - y1 - t * dy);
}

export function distToRect(px: number, py: number, rx: number, ry: number, rw: number, rh: number): number {
  const insideX = px >= rx && px <= rx + rw;
  const insideY = py >= ry && py <= ry + rh;
  if (insideX && insideY) return Math.min(px - rx, rx + rw - px, py - ry, ry + rh - py);
  const cx = Math.max(rx, Math.min(px, rx + rw));
  const cy = Math.max(ry, Math.min(py, ry + rh));
  return Math.hypot(px - cx, py - cy);
}

function hitTestEl(px: number, py: number, el: SvgEl): number {
  if (el.type === "line") return distToSegment(px, py, el.x1, el.y1, el.x2, el.y2);
  if (el.type === "rect") return distToRect(px, py, el.x, el.y, el.w, el.h);
  if (el.type === "circle") return Math.abs(Math.hypot(px - el.cx, py - el.cy) - el.r);
  if (el.type === "ellipse") {
    const a = el.rx, b = el.ry;
    if (a < 1 || b < 1) return 999;
    const nx = (px - el.cx) / a, ny = (py - el.cy) / b;
    return Math.abs(Math.hypot(nx, ny) - 1) * Math.min(a, b);
  }
  if (el.type === "text") return distToRect(px, py, el.x, el.y - 14, (el.text?.length ?? 4) * 7, 16);
  if (el.type === "path") return 20; // not easily hittable; just use a fixed threshold
  return 999;
}

function hitTestDrawings(
  px: number, py: number,
  drawings: Drawing[],
  chart: echarts.ECharts,
  candles: Candle[],
): string | null {
  const THRESHOLD = 14;
  let best: { id: string; dist: number } | null = null;
  for (const d of drawings) {
    const els = shapeToPixels(d.shape, chart, candles);
    if (!els) continue;
    for (const el of els) {
      const dist = hitTestEl(px, py, el);
      if (dist < THRESHOLD && (!best || dist < best.dist)) {
        best = { id: d.id, dist };
      }
    }
  }
  return best?.id ?? null;
}

// ── Shape control handles ──────────────────────────────────────────────────────

type HandleInfo = { px: number; py: number; kind: "move"|"p0"|"p1"|"p2"; cursor: string };

function getShapeHandles(shape: Record<string, unknown>, chart: echarts.ECharts): HandleInfo[] | null {
  const type = shape.type as string;
  const toPx = (xIdx: number, y: number) => {
    const r = chart.convertToPixel({ gridIndex: 0 }, [xIdx, y]) as [number, number];
    return { px: r[0], py: r[1] };
  };
  if (["arrowmarker","arrowmarkup","arrowmarkdown","flag","note"].includes(type)) {
    const p = toPx(shape.xIdx as number, shape.y as number);
    return [{ ...p, kind: "p0", cursor: "move" }];
  }
  if (type === "crossline") {
    const mid = chart.getWidth() / 2;
    const [, py] = chart.convertToPixel({ gridIndex: 0 }, [0, shape.y as number]) as [number, number];
    return [{ px: mid, py, kind: "p0", cursor: "move" }];
  }
  if (type === "hline") {
    const [, py0] = chart.convertToPixel({ gridIndex: 0 }, [0, shape.y as number]) as [number, number];
    const py1 = typeof shape.y1 === "number"
      ? (chart.convertToPixel({ gridIndex: 0 }, [0, shape.y1 as number]) as [number, number])[1]
      : py0;
    // Left handle moves the left y; right handle can create slope (rotate)
    return [
      { px: CHART_GL + 16, py: py0, kind: "p0", cursor: "crosshair" },
      { px: chart.getWidth() - CHART_GR - 16, py: py1, kind: "p1", cursor: "crosshair" },
    ];
  }
  if (type === "hray") {
    const [startX, py0] = chart.convertToPixel({ gridIndex: 0 }, [shape.xIdx as number, shape.y as number]) as [number, number];
    const py1 = typeof shape.y1 === "number"
      ? (chart.convertToPixel({ gridIndex: 0 }, [0, shape.y1 as number]) as [number, number])[1]
      : py0;
    return [
      { px: Math.max(startX, CHART_GL + 4), py: py0, kind: "p0", cursor: "crosshair" },
      { px: chart.getWidth() - CHART_GR - 16, py: py1, kind: "p1", cursor: "crosshair" },
    ];
  }
  if (type === "vline") {
    const mid = chart.getHeight() / 2;
    const [px] = chart.convertToPixel({ gridIndex: 0 }, [shape.xIdx as number, 0]) as [number, number];
    return [{ px, py: mid, kind: "p0", cursor: "ew-resize" }];
  }
  if (typeof shape.x0Idx === "number" && typeof shape.x1Idx === "number") {
    const p0 = toPx(shape.x0Idx as number, shape.y0 as number);
    const p1 = toPx(shape.x1Idx as number, shape.y1 as number);
    const handles: HandleInfo[] = [
      { ...p0, kind: "p0", cursor: "crosshair" },
      { ...p1, kind: "p1", cursor: "crosshair" },
    ];
    if (type === "parallelch" && typeof shape.y2 === "number") {
      const [, py2] = chart.convertToPixel({ gridIndex: 0 }, [shape.x0Idx as number, shape.y2 as number]) as [number, number];
      handles.push({ px: (p0.px + p1.px) / 2, py: (p0.py + p1.py) / 2 + (py2 - p0.py), kind: "p2", cursor: "ns-resize" });
    }
    return handles;
  }
  return null;
}

function applyShapeDelta(
  shape: Record<string, unknown>,
  chart: echarts.ECharts,
  startPx: number, startPy: number,
  curPx: number, curPy: number,
  kind: "move"|"p0"|"p1"|"p2",
): Record<string, unknown> {
  const from = chart.convertFromPixel({ gridIndex: 0 }, [startPx, startPy]) as [number, number] | null;
  const to   = chart.convertFromPixel({ gridIndex: 0 }, [curPx,   curPy  ]) as [number, number] | null;
  if (!from || !to) return shape;
  const dIdx = Math.round(to[0] - from[0]);
  const dY   = to[1] - from[1];
  const s = { ...shape };
  const shiftIdx = (k: string) => { if (typeof s[k] === "number") s[k] = Math.max(0, (s[k] as number) + dIdx); };
  const shiftY   = (k: string) => { if (typeof s[k] === "number") s[k] = (s[k] as number) + dY; };
  if (kind === "move") {
    // hline / hray: shift y (and y1 if slope was set) together
    if (s.type === "hline" || s.type === "hray") {
      shiftIdx("xIdx"); shiftY("y"); shiftY("y1");
    } else {
      shiftIdx("xIdx"); shiftY("y");
      shiftIdx("x0Idx"); shiftY("y0");
      shiftIdx("x1Idx"); shiftY("y1"); shiftY("y2");
    }
  } else if (s.type === "hline") {
    // p0 = left endpoint → only shift y (left price level)
    // p1 = right endpoint → shift y1 to create/adjust slope
    if (kind === "p0") { shiftY("y"); }
    else if (kind === "p1") {
      if (typeof s.y1 !== "number") s.y1 = s.y; // initialise slope from current y
      shiftY("y1");
    }
  } else if (s.type === "hray") {
    // p0 = origin → shift xIdx and y
    // p1 = tip    → shift y1 to create/adjust slope
    if (kind === "p0") { shiftIdx("xIdx"); shiftY("y"); }
    else if (kind === "p1") {
      if (typeof s.y1 !== "number") s.y1 = s.y; // initialise slope from current y
      shiftY("y1");
    }
  } else if (kind === "p0") {
    shiftIdx("xIdx"); shiftY("y");
    shiftIdx("x0Idx"); shiftY("y0");
  } else if (kind === "p1") {
    shiftIdx("x1Idx"); shiftY("y1");
  } else if (kind === "p2") {
    shiftY("y2");
  }
  return s;
}

// ── SVG renderer ──────────────────────────────────────────────────────────────

function renderSvg(
  svgEl: SVGSVGElement | null,
  pixels: SvgPixels[],
  preview: SvgEl | SvgEl[] | null,
  eraserPixel: { x: number; y: number } | null,
  handles?: HandleInfo[] | null,
) {
  if (!svgEl) return;
  while (svgEl.firstChild) svgEl.removeChild(svgEl.firstChild);

  const add = (el: SvgEl, isPreview = false) => {
    const baseColor = DRAW_CLR + (isPreview ? "bb" : "");
    const opacity = isPreview ? "0.75" : "1";
    if (el.type === "line") {
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", String(el.x1)); line.setAttribute("y1", String(el.y1));
      line.setAttribute("x2", String(el.x2)); line.setAttribute("y2", String(el.y2));
      line.setAttribute("stroke", el.color ?? baseColor);
      line.setAttribute("stroke-width", String(el.width ?? 1.5));
      line.setAttribute("opacity", opacity);
      if (el.dash) line.setAttribute("stroke-dasharray", "5 4");
      svgEl.appendChild(line);
    } else if (el.type === "rect") {
      const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      rect.setAttribute("x", String(el.x)); rect.setAttribute("y", String(el.y));
      rect.setAttribute("width", String(el.w)); rect.setAttribute("height", String(el.h));
      if (el.stroke !== "none") {
        rect.setAttribute("stroke", el.stroke ?? baseColor);
        rect.setAttribute("stroke-width", "1.5");
      } else {
        rect.setAttribute("stroke", "none");
      }
      rect.setAttribute("fill", el.fill ?? "rgba(99,102,241,0.08)");
      rect.setAttribute("opacity", opacity);
      svgEl.appendChild(rect);
    } else if (el.type === "circle") {
      const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("cx", String(el.cx)); c.setAttribute("cy", String(el.cy));
      c.setAttribute("r", String(Math.max(0, el.r)));
      c.setAttribute("stroke", baseColor); c.setAttribute("stroke-width", "1.5");
      c.setAttribute("fill", el.fill ?? "rgba(99,102,241,0.08)");
      c.setAttribute("opacity", opacity);
      svgEl.appendChild(c);
    } else if (el.type === "ellipse") {
      const e = document.createElementNS("http://www.w3.org/2000/svg", "ellipse");
      e.setAttribute("cx", String(el.cx)); e.setAttribute("cy", String(el.cy));
      e.setAttribute("rx", String(Math.max(0, el.rx))); e.setAttribute("ry", String(Math.max(0, el.ry)));
      e.setAttribute("stroke", baseColor); e.setAttribute("stroke-width", "1.5");
      e.setAttribute("fill", el.fill ?? "rgba(99,102,241,0.08)");
      e.setAttribute("opacity", opacity);
      svgEl.appendChild(e);
    } else if (el.type === "text") {
      const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
      t.setAttribute("x", String(el.x)); t.setAttribute("y", String(el.y));
      t.setAttribute("text-anchor", el.anchor ?? "start");
      t.setAttribute("font-size", String(el.size ?? 10));
      t.setAttribute("fill", el.color ?? baseColor);
      t.setAttribute("font-family", "monospace");
      t.setAttribute("pointer-events", "none");
      t.setAttribute("opacity", opacity);
      t.textContent = el.text;
      svgEl.appendChild(t);
    } else if (el.type === "path") {
      const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
      p.setAttribute("d", el.d);
      p.setAttribute("stroke", el.stroke ?? baseColor);
      p.setAttribute("stroke-width", "1.5");
      p.setAttribute("fill", el.fill ?? "none");
      p.setAttribute("stroke-linecap", "round");
      p.setAttribute("stroke-linejoin", "round");
      p.setAttribute("opacity", opacity);
      svgEl.appendChild(p);
    }
  };

  for (const p of pixels) for (const el of p.els) add(el, false);
  if (preview) {
    const arr = Array.isArray(preview) ? preview : [preview];
    for (const el of arr) add(el, true);
  }

  // Eraser cursor circle
  if (eraserPixel) {
    const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    c.setAttribute("cx", String(eraserPixel.x));
    c.setAttribute("cy", String(eraserPixel.y));
    c.setAttribute("r", "12");
    c.setAttribute("stroke", "rgba(239,68,68,0.7)");
    c.setAttribute("stroke-width", "1.5");
    c.setAttribute("fill", "rgba(239,68,68,0.08)");
    svgEl.appendChild(c);
  }

  // Hover/selected drawing handles (small circles at control points)
  if (handles) {
    for (const h of handles) {
      const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("cx", String(Math.round(h.px)));
      c.setAttribute("cy", String(Math.round(h.py)));
      c.setAttribute("r", "5");
      c.setAttribute("fill", "white");
      c.setAttribute("stroke", DRAW_CLR);
      c.setAttribute("stroke-width", "1.5");
      c.setAttribute("opacity", "0.92");
      c.setAttribute("pointer-events", "none");
      svgEl.appendChild(c);
    }
  }
}

// ── Component ──────────────────────────────────────────────────────────────────

interface HoverCandle {
  date: string; o: number; h: number; l: number; c: number; v: number;
}

export default function ChartPanel({
  symbol, symbolName, periodCfg, drawingTool, chartType, indicators,
  isActive, drawings, onDrawingAdd, onDrawingErase, onClearDrawings, onActivate,
  onDrawingDone, onDrawingUpdate, theme, onIndicatorRemove,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef       = useRef<SVGSVGElement>(null);
  const chartRef     = useRef<echarts.ECharts | null>(null);
  const candles      = useRef<Candle[]>([]);
  const dragStart    = useRef<{ px: number; py: number; xIdx: number; y: number } | null>(null);
  const eraserPos    = useRef<{ x: number; y: number } | null>(null);
  const paintSvgRef  = useRef<((preview?: SvgEl | SvgEl[] | null, eraser?: { x: number; y: number } | null, skipId?: string | null, handles?: HandleInfo[] | null) => void) | null>(null);
  const dragDrawingState = useRef<{ id: string; kind: "move"|"p0"|"p1"|"p2"; startPx: number; startPy: number; origShape: Record<string, unknown> } | null>(null);
  const phase2State  = useRef<{
    tool: "parallelch" | "pitchfork";
    x0Idx: number; y0: number; x1Idx: number; y1: number;
    px0: number; py0: number; px1: number; py1: number;
  } | null>(null);
  const indicatorDataRef = useRef<Record<string, (number | null)[]>>({});
  const renderChartRef   = useRef<(() => void) | null>(null);
  const fetchDataRef     = useRef<(() => void) | null>(null);
  const drawingToolRef = useRef<DrawingTool>(drawingTool);
  const intervalRef    = useRef<string>(periodCfg.i);
  const chartTypeRef   = useRef<ChartType>(chartType);
  const themeRef       = useRef<"dark" | "light">(theme);
  useEffect(() => { drawingToolRef.current = drawingTool; }, [drawingTool]);
  useEffect(() => { intervalRef.current = periodCfg.i; }, [periodCfg.i]);
  useEffect(() => { themeRef.current = theme; }, [theme]);
  useEffect(() => { chartTypeRef.current = chartType; }, [chartType]);

  const [loading, setLoading]           = useState(true);
  const [loadError, setLoadError]       = useState<string | null>(null);
  const [loadingMore, setLoadingMore]   = useState(false);
  const loadingMoreRef                  = useRef(false);
  const noMoreHistoryRef                = useRef(false);
  // Monotonic request epoch — incremented whenever the symbol or window
  // changes. In-flight fetches compare against this on completion and
  // discard their result if a newer request has been issued, preventing
  // stale data from overwriting the current chart.
  const requestEpochRef                 = useRef(0);
  const [hoverCandle, setHoverCandle]   = useState<HoverCandle | null>(null);
  const [hoverIdx, setHoverIdx]         = useState(-1);
  const [lastCandle, setLastCandle]     = useState<{ c: number; pct: number } | null>(null);
  const [ctxMenu, setCtxMenu]           = useState<{ x: number; y: number } | null>(null);
  const [hoveredDrawingId, setHoveredDrawingId] = useState<string | null>(null);
  const [isDraggingDrawing, setIsDraggingDrawing] = useState(false);
  const [drawingCtxMenu, setDrawingCtxMenu] = useState<{ id: string; x: number; y: number } | null>(null);
  // Refs so native (non-React) event listeners always see latest values
  const drawingsRef          = useRef(drawings);
  useEffect(() => { drawingsRef.current = drawings; }, [drawings]);
  const hoveredDrawingIdRef  = useRef<string | null>(null);
  const hoverRafRef          = useRef<number | null>(null);

  // ── Repaint SVG ────────────────────────────────────────────────────────────
  const paintSvg = useCallback((
    preview: SvgEl | SvgEl[] | null = null,
    eraser: { x: number; y: number } | null = null,
    skipId: string | null = null,
    handles: HandleInfo[] | null = null,
  ) => {
    const chart = chartRef.current;
    const svg   = svgRef.current;
    const div   = containerRef.current;
    if (!chart || !svg || !div || !candles.current.length) return;
    svg.setAttribute("width",  String(div.offsetWidth));
    svg.setAttribute("height", String(div.offsetHeight));

    const pixels: SvgPixels[] = drawings
      .filter(d => d.id !== skipId)
      .map(d => {
        const els = shapeToPixels(d.shape, chart, candles.current);
        return els ? { id: d.id, els } : null;
      })
      .filter(Boolean) as SvgPixels[];

    renderSvg(svg, pixels, preview, eraser, handles);
  }, [drawings]);

  // Repaint SVG when hover changes (show/hide handles)
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !candles.current.length) return;
    if (hoveredDrawingId) {
      const hd = drawings.find(d => d.id === hoveredDrawingId);
      const handles = hd ? getShapeHandles(hd.shape, chart) : null;
      paintSvg(null, null, null, handles);
    } else {
      paintSvg();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hoveredDrawingId]);

  // Dismiss drawing context menu when clicking outside it
  useEffect(() => {
    if (!drawingCtxMenu) return;
    const close = () => setDrawingCtxMenu(null);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [drawingCtxMenu]);

  // Change canvas cursor when hovering a drawing (pointer mode only, no overlay)
  useEffect(() => {
    if (drawingTool !== "none") return;
    const canvas = containerRef.current?.querySelector("canvas") as HTMLElement | null;
    if (canvas) canvas.style.cursor = hoveredDrawingId ? "grab" : "";
  }, [hoveredDrawingId, drawingTool]);

  // ── Native capture listeners for pointer-mode hover + drag start ────────────
  // These run WITHOUT the overlay div, so ECharts handles the mouse natively
  // (smooth crosshair). We intercept only when the user actually hits a drawing.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const onNativeMove = (e: MouseEvent) => {
      if (drawingToolRef.current !== "none") return;
      if (dragDrawingState.current) return;           // overlay handles drag
      if (!drawingsRef.current.length) return;

      const chart = chartRef.current;
      if (!chart || !candles.current.length) return;
      const rect = container.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;

      // One RAF per frame — skip if one is already queued
      if (hoverRafRef.current !== null) return;
      hoverRafRef.current = requestAnimationFrame(() => {
        hoverRafRef.current = null;
        const ch = chartRef.current;
        if (!ch || !candles.current.length) return;
        const hitId = hitTestDrawings(px, py, drawingsRef.current, ch, candles.current);
        if (hitId !== hoveredDrawingIdRef.current) {
          hoveredDrawingIdRef.current = hitId;
          setHoveredDrawingId(hitId);
        }
      });
    };

    const onNativeDown = (e: MouseEvent) => {
      if (drawingToolRef.current !== "none") return;
      if (!drawingsRef.current.length) return;
      // Right-click → show drawing context menu if over a drawing
      if (e.button === 2) {
        const chart = chartRef.current;
        if (!chart || !candles.current.length) return;
        const rect = container.getBoundingClientRect();
        const px = e.clientX - rect.left;
        const py = e.clientY - rect.top;
        const hitId = hitTestDrawings(px, py, drawingsRef.current, chart, candles.current);
        if (hitId) {
          e.stopPropagation(); e.preventDefault();
          setDrawingCtxMenu({ id: hitId, x: e.clientX, y: e.clientY });
        }
        return;
      }

      const chart = chartRef.current;
      if (!chart || !candles.current.length) return;
      const rect = container.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;
      const HANDLE_R = 10;

      // Handle-point check on current hover target
      if (hoveredDrawingIdRef.current) {
        const hd = drawingsRef.current.find(d => d.id === hoveredDrawingIdRef.current);
        if (hd) {
          const hls = getShapeHandles(hd.shape, chart);
          const near = hls?.find(h => Math.hypot(h.px - px, h.py - py) < HANDLE_R);
          if (near) {
            e.stopPropagation(); e.preventDefault();
            dragDrawingState.current = { id: hoveredDrawingIdRef.current!, kind: near.kind, startPx: px, startPy: py, origShape: { ...hd.shape } };
            setIsDraggingDrawing(true);
            return;
          }
        }
      }

      // Body hit check
      const hitId = hitTestDrawings(px, py, drawingsRef.current, chart, candles.current);
      if (hitId) {
        e.stopPropagation(); e.preventDefault();
        const hd = drawingsRef.current.find(d => d.id === hitId)!;
        dragDrawingState.current = { id: hitId, kind: "move", startPx: px, startPy: py, origShape: { ...hd.shape } };
        hoveredDrawingIdRef.current = hitId;
        setHoveredDrawingId(hitId);
        setIsDraggingDrawing(true);
      }
      // else: let ECharts handle pan/zoom naturally
    };

    const onContextMenu = (e: MouseEvent) => {
      // Prevent browser default menu when right-clicking over a drawing
      if (!drawingsRef.current.length) return;
      const chart = chartRef.current;
      if (!chart || !candles.current.length) return;
      const rect = container.getBoundingClientRect();
      const hitId = hitTestDrawings(e.clientX - rect.left, e.clientY - rect.top, drawingsRef.current, chart, candles.current);
      if (hitId) e.preventDefault();
    };

    // capture: true for mousedown so we intercept before ECharts' ZRender
    container.addEventListener("mousemove", onNativeMove);
    container.addEventListener("mousedown", onNativeDown, { capture: true });
    container.addEventListener("contextmenu", onContextMenu);
    return () => {
      container.removeEventListener("mousemove", onNativeMove);
      container.removeEventListener("mousedown", onNativeDown, { capture: true });
      container.removeEventListener("contextmenu", onContextMenu);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Render ECharts ─────────────────────────────────────────────────────────
  const renderChart = useCallback(() => {
    const chart = chartRef.current;
    if (!chart || !candles.current.length) return;
    const T = getThemeColors(themeRef.current);

    const cs       = candles.current;
    const showTime = INTRADAY_INTERVALS.has(intervalRef.current);
    const dates    = cs.map(c => toDateStr(c.time, showTime));
    const ct       = chartTypeRef.current;
    // For Heikin Ashi, transform the raw candles
    const wcs      = ct === "ha" ? computeHA(cs) : cs;
    const closes   = wcs.map(c => c.close);
    const ohlc     = wcs.map(c => [c.open, c.close, c.low, c.high]);

    // ── Identify selected overlays vs oscillators (each oscillator gets own pane) ──
    const hasVol = cs.some(c => (c.volume ?? 0) > 0);
    const selectedDefs = [...indicators]
      .map(k => IND_BY_KEY[k])
      .filter((d): d is IndicatorDef => !!d && (!d.needsVolume || hasVol));
    const overlayDefs    = selectedDefs.filter(d => !d.paneOwn);
    const oscillatorDefs = selectedDefs.filter(d =>  d.paneOwn);
    const N_OSC = oscillatorDefs.length;

    // ── Grid layout: FIXED slot count, dynamic heights ─────────────────────
    // We always emit (2 + MAX_OSC_SLOTS) grids/axes so that ECharts can tween
    // grid coordinates between renders — adding the first oscillator pane or
    // removing the last one only resizes existing components rather than
    // creating/destroying them, which preserves the animation.
    const MAX_OSC_SLOTS = 5;
    const TOP_PCT = 4;
    const BOT_PCT = 4;
    const AVAIL   = 100 - TOP_PCT - BOT_PCT;
    const PRICE_W = 4;
    const VOL_W   = 1;
    const OSC_W   = 1.6;
    const totalW  = PRICE_W + VOL_W + N_OSC * OSC_W;
    const usedHeights = [
      PRICE_W * AVAIL / totalW,
      VOL_W   * AVAIL / totalW,
      ...Array(N_OSC).fill(OSC_W * AVAIL / totalW),
    ];
    // Pad remaining oscillator slots with zero-height (collapsed) grids.
    const heights = [...usedHeights, ...Array(MAX_OSC_SLOTS - N_OSC).fill(0)];
    const tops: number[] = []; { let acc = TOP_PCT; for (const h of heights) { tops.push(acc); acc += h; } }
    const totalGrids = 2 + MAX_OSC_SLOTS;
    const lastUsedIdx = 1 + N_OSC; // bottom-most VISIBLE pane (vol when no osc, else last osc)

    // Prices on right side — narrow left margin, wider right margin for labels
    const GL = 8, GR = 70;
    const grids: object[] = heights.map((h, i) => ({
      top: `${tops[i].toFixed(2)}%`, left: GL, right: GR, height: `${h.toFixed(2)}%`,
      // No `show: true` — ECharts would draw a visible border around the pane.
      // Zero-height padding slots are already invisible.
    }));

    // x-axis: labels ONLY on the bottom-most VISIBLE grid
    const xBase = { axisLine: { lineStyle: { color: T.grid } }, axisTick: { show: false } };
    const xAxes: object[] = grids.map((_, i) => {
      const used = i <= lastUsedIdx;
      return {
        ...xBase, gridIndex: i, data: dates,
        show: used,
        axisLabel: used && i === lastUsedIdx
          ? { color: T.text, fontSize: 9, margin: 6, formatter: (v: string) => fmtXLabel(v, showTime) }
          : { show: false },
        splitLine: used && (i === 0 || i > 1) ? { lineStyle: { color: T.grid } } : { show: false },
        axisPointer: used && i === lastUsedIdx ? {} : { label: { show: false } },
      };
    });

    // y-axis — all positioned on the RIGHT side
    const yBase = { axisLine: { show: false }, axisTick: { show: false }, position: "right" };
    const yAxes: object[] = [];
    for (let i = 0; i < totalGrids; i++) {
      if (i === 0) {
        yAxes.push({ ...yBase, gridIndex: 0, scale: true,
          axisLabel: { color: T.text, fontSize: 10, margin: 6 },
          splitLine: { lineStyle: { color: T.grid } } });
      } else if (i === 1) {
        yAxes.push({ ...yBase, gridIndex: 1, scale: true,
          axisLabel: { show: true, color: T.text, fontSize: 9, margin: 6, formatter: (v: number) => fmtVol(v) },
          splitLine: { show: false }, splitNumber: 2 });
      } else {
        const oscIdx = i - 2;
        const d = oscIdx < N_OSC ? oscillatorDefs[oscIdx] : null;
        const used = !!d;
        yAxes.push({
          ...yBase, gridIndex: i, scale: true,
          show: used,
          ...(d?.yMin !== undefined ? { min: d.yMin } : {}),
          ...(d?.yMax !== undefined ? { max: d.yMax } : {}),
          axisLabel: used ? { color: T.text, fontSize: 9, margin: 6 } : { show: false },
          splitLine: used ? { lineStyle: { color: T.grid } } : { show: false },
          splitNumber: 3,
        });
      }
    }

    // ── Price series — varies by chart type ──────────────────────────────────
    let priceSeries: object;
    if (ct === "candles" || ct === "ha") {
      priceSeries = {
        name: "Price", type: "candlestick", xAxisIndex: 0, yAxisIndex: 0, data: ohlc,
        itemStyle: { color: "#26a69a", color0: "#ef5350", borderColor: "#26a69a", borderColor0: "#ef5350", borderWidth: 1 },
      };
    } else if (ct === "bars") {
      priceSeries = {
        name: "Price", type: "candlestick", xAxisIndex: 0, yAxisIndex: 0, data: ohlc,
        itemStyle: { color: "transparent", color0: "transparent", borderColor: "#26a69a", borderColor0: "#ef5350", borderWidth: 1.5 },
      };
    } else if (ct === "hollow") {
      priceSeries = {
        name: "Price", type: "candlestick", xAxisIndex: 0, yAxisIndex: 0, data: ohlc,
        itemStyle: { color: "transparent", color0: "#ef5350", borderColor: "#26a69a", borderColor0: "#ef5350", borderWidth: 1.5 },
      };
    } else if (ct === "line") {
      priceSeries = { name: "Price", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: closes, lineStyle: { color: "#2196F3", width: 1.5 }, showSymbol: false };
    } else if (ct === "line_markers") {
      priceSeries = { name: "Price", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: closes, lineStyle: { color: "#2196F3", width: 1.5 }, showSymbol: true, symbolSize: 4, symbol: "circle", itemStyle: { color: "#2196F3" } };
    } else if (ct === "step") {
      priceSeries = { name: "Price", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: closes, lineStyle: { color: "#2196F3", width: 1.5 }, step: "middle", showSymbol: false };
    } else if (ct === "area") {
      priceSeries = {
        name: "Price", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: closes, lineStyle: { color: "#2196F3", width: 1.5 }, showSymbol: false,
        areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: "rgba(33,150,243,0.3)" }, { offset: 1, color: "rgba(33,150,243,0.01)" }] } },
      };
    } else if (ct === "baseline") {
      const mid = closes.length ? (Math.max(...closes) + Math.min(...closes)) / 2 : 0;
      priceSeries = {
        name: "Price", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: closes, lineStyle: { color: "#6366f1", width: 1.5 }, showSymbol: false,
        markLine: { silent: true, symbol: "none", lineStyle: { color: "rgba(99,102,241,0.5)", type: "dashed", width: 1 }, data: [{ yAxis: mid }] },
        areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: "rgba(99,102,241,0.25)" }, { offset: 1, color: "rgba(239,83,80,0.1)" }] } },
      };
    } else {
      // columns
      priceSeries = {
        name: "Price", type: "bar", xAxisIndex: 0, yAxisIndex: 0, barMaxWidth: 8,
        data: cs.map(c => ({ value: c.close, itemStyle: { color: c.close >= c.open ? "rgba(38,166,154,0.7)" : "rgba(239,83,80,0.7)" } })),
      };
    }

    const series: object[] = [
      priceSeries,
      {
        name: "Volume", type: "bar", xAxisIndex: 1, yAxisIndex: 1, barMaxWidth: 10,
        data: cs.map(c => ({
          value: c.volume,
          itemStyle: { color: c.close >= c.open ? "rgba(38,166,154,0.5)" : "rgba(239,83,80,0.5)" },
        })),
      },
    ];

    // Reset indicator cache for this render
    indicatorDataRef.current = {};

    // ── Compute & emit catalog-driven series ────────────────────────────────
    const highs   = wcs.map(c => c.high);
    const lows    = wcs.map(c => c.low);
    const volumes = cs.map(c => c.volume ?? 0);
    const indInput = { highs, lows, closes, volumes };

    // Overlays attach to the price pane (xAxisIndex 0 / yAxisIndex 0).
    for (const def of overlayDefs) {
      const { series: specs, cache } = def.compute(indInput);
      for (const k in cache) indicatorDataRef.current[`${def.key}.${k}`] = cache[k];
      for (const s of specs) series.push({ ...s, xAxisIndex: 0, yAxisIndex: 0 });
    }

    // Each oscillator gets its own pane. Pane index = 2 + position in oscillatorDefs.
    for (let i = 0; i < oscillatorDefs.length; i++) {
      const def = oscillatorDefs[i];
      const paneIdx = 2 + i;
      const { series: specs, cache } = def.compute(indInput);
      for (const k in cache) indicatorDataRef.current[`${def.key}.${k}`] = cache[k];
      for (const s of specs) series.push({ ...s, xAxisIndex: paneIdx, yAxisIndex: paneIdx });
      // Reference guides (e.g. RSI 70/30, ADX 25, Stoch 80/20)
      if (def.guides) {
        for (const g of def.guides) {
          series.push({
            name: `${def.key}_g_${g.value}`, type: "line", xAxisIndex: paneIdx, yAxisIndex: paneIdx,
            data: dates.map(() => g.value), showSymbol: false,
            lineStyle: { color: g.color, width: 1, type: "dashed" }, silent: true,
          });
        }
      }
    }

    // Preserve current zoom range so toggling indicators doesn't snap the chart back
    const prevOpt = chart.getOption() as any;
    const prevZoom = Array.isArray(prevOpt?.dataZoom) && prevOpt.dataZoom[0]
      ? { start: prevOpt.dataZoom[0].start, end: prevOpt.dataZoom[0].end }
      : null;

    chart.setOption({
      backgroundColor: T.bg,
      // Smooth in/out as panes appear/disappear and series add/remove
      animation: true,
      animationDuration: 220,
      animationDurationUpdate: 220,
      animationEasing: "cubicOut",
      animationEasingUpdate: "cubicOut",
      tooltip: {
        trigger: "axis",
        axisPointer: {
          type: "cross",
          crossStyle: { color: T.cross, width: 1 },
          lineStyle: { color: T.cross, width: 1, type: "dashed" },
          label: {
            backgroundColor: T.labBg,
            color: T.labText,
            fontSize: 10,
            formatter: ({ value }: any) => typeof value === "number" ? fmtPrice(value) : fmtCrosshairLabel(String(value)),
          },
        },
        backgroundColor: T.tipBg,
        borderColor: T.tipBor,
        borderWidth: 1,
        padding: [6, 10],
        textStyle: { color: T.tipText, fontSize: 11 },
        // Suppress default tooltip — we show OHLCV in the header instead
        formatter: () => "",
      },
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      dataZoom: [
        {
          type: "inside",
          xAxisIndex: grids.map((_, i) => i),
          // Preserve user's current zoom range across indicator toggles
          start: prevZoom?.start ?? 60,
          end:   prevZoom?.end   ?? 100,
          zoomOnMouseWheel: true,
          moveOnMouseMove: true,
        },
      ],
      grid: grids, xAxis: xAxes, yAxis: yAxes, series,
    }, { replaceMerge: ["grid", "xAxis", "yAxis", "series", "dataZoom"] });

    // Repaint via ref so renderChart's identity doesn't depend on paintSvg
    // (which itself depends on `drawings`) — otherwise drawing on the chart
    // would cascade back through fetchData and trigger a re-fetch.
    requestAnimationFrame(() => paintSvgRef.current?.());
  }, [indicators]);

  // ── Fetch ──────────────────────────────────────────────────────────────────
  const fetchData = useCallback(async () => {
    if (!symbol) return;
    // Bump epoch — any in-flight prepend or base fetch from a previous
    // symbol/window will see the mismatch on completion and bail out.
    const epoch = ++requestEpochRef.current;
    setLoading(true);
    setLoadError(null);
    try {
      const qs = periodCfg.start && periodCfg.end
        ? `start=${periodCfg.start}&end=${periodCfg.end}&interval=${periodCfg.i}`
        : `period=${periodCfg.p}&interval=${periodCfg.i}`;
      const data = await fetchApi<{ candles: unknown[] }>(`/stocks/${encodeURIComponent(symbol)}/history?${qs}`);
      if (epoch !== requestEpochRef.current) return;  // superseded
      // Runtime-validate the candle shape — backend changes shouldn't silently
      // corrupt the chart with NaN OHLC values.
      const raw = Array.isArray(data?.candles) ? data.candles : [];
      const validated: Candle[] = [];
      for (const c of raw) {
        if (!c || typeof c !== "object") continue;
        const o = (c as Candle).open, h = (c as Candle).high, l = (c as Candle).low,
              cl = (c as Candle).close, t = (c as Candle).time, v = (c as Candle).volume;
        if (
          typeof t === "number" && Number.isFinite(t) &&
          typeof o === "number" && Number.isFinite(o) &&
          typeof h === "number" && Number.isFinite(h) &&
          typeof l === "number" && Number.isFinite(l) &&
          typeof cl === "number" && Number.isFinite(cl)
        ) {
          validated.push({ time: t, open: o, high: h, low: l, close: cl, volume: typeof v === "number" ? v : 0 });
        }
      }
      candles.current = validated;
      if (validated.length === 0) {
        setLoadError(raw.length > 0 ? "Received malformed price data." : "No price data available for this symbol.");
      }
      // Compute last close + daily change
      const cs = candles.current;
      if (cs.length >= 2) {
        const last = cs[cs.length - 1];
        const prev = cs[cs.length - 2];
        setLastCandle({ c: last.close, pct: prev.close !== 0 ? ((last.close - prev.close) / prev.close) * 100 : 0 });
      } else if (cs.length === 1) {
        setLastCandle({ c: cs[0].close, pct: 0 });
      } else {
        setLastCandle(null);
      }
    } catch (err) {
      if (epoch !== requestEpochRef.current) return;  // superseded
      candles.current = [];
      setLastCandle(null);
      setLoadError(err instanceof Error ? err.message : "Failed to load price data.");
    } finally {
      if (epoch === requestEpochRef.current) setLoading(false);
    }
    // Render via ref so fetchData's identity doesn't track renderChart —
    // keeps the [symbol, periodCfg] effect from re-firing on indicator
    // toggles or drawing edits.
    // Reset infinite-scroll state when the symbol or window changes —
    // the new fetch is the new baseline.
    noMoreHistoryRef.current = false;
    renderChartRef.current?.();
  }, [symbol, periodCfg]);

  // ── Pan-to-load-more (infinite scroll left) ────────────────────────────────
  // Fetches an older chunk of daily/weekly/monthly history when the user
  // pans to the leftmost edge, prepends it to candles.current, and shifts
  // the dataZoom window to keep the visible candles visually anchored.
  const loadMoreHistory = useCallback(async () => {
    if (loadingMoreRef.current || noMoreHistoryRef.current) return;
    if (!symbol) return;
    const cur = candles.current;
    if (cur.length < 2) return;
    // Only meaningful for daily-or-larger candles — intraday range is capped
    // by Yahoo to the last few days, so paging back doesn't help there.
    const intvl = intervalRef.current;
    if (!["1d", "1wk", "1mo"].includes(intvl)) return;

    const oldestSec = cur[0].time;
    const endStr = new Date(oldestSec * 1000).toISOString().slice(0, 10);
    // Chunk size: ~2y for 1d, ~10y for 1wk/1mo (Yahoo serves whatever exists
    // in that window — possibly less, which signals "no older data").
    const daysBack = intvl === "1d" ? 730 : 3650;
    const startStr = new Date((oldestSec - daysBack * 86400) * 1000)
      .toISOString().slice(0, 10);

    // Snapshot baseline so we can verify nothing changed under us during
    // the await. If the user switches symbol/range mid-fetch, we discard.
    const baselineEpoch    = requestEpochRef.current;
    const baselineSymbol   = symbol;
    const baselineInterval = intvl;
    const baselineOldest   = oldestSec;

    loadingMoreRef.current = true;
    setLoadingMore(true);
    try {
      const qs = `start=${startStr}&end=${endStr}&interval=${intvl}`;
      const data = await fetchApi<{ candles: unknown[] }>(
        `/stocks/${encodeURIComponent(symbol)}/history?${qs}`
      );
      // Bail if a newer request superseded us, or the chart's baseline
      // shifted (different symbol/interval/oldest) — committing now would
      // corrupt the current chart with data from a stale context.
      if (
        baselineEpoch    !== requestEpochRef.current ||
        baselineSymbol   !== symbol ||
        baselineInterval !== intervalRef.current ||
        candles.current.length === 0 ||
        candles.current[0].time !== baselineOldest
      ) {
        return;
      }
      const raw = Array.isArray(data?.candles) ? data.candles : [];
      const olderValidated: Candle[] = [];
      for (const c of raw) {
        if (!c || typeof c !== "object") continue;
        const o = (c as Candle).open, h = (c as Candle).high, l = (c as Candle).low,
              cl = (c as Candle).close, t = (c as Candle).time, v = (c as Candle).volume;
        if (
          typeof t === "number" && Number.isFinite(t) &&
          typeof o === "number" && Number.isFinite(o) &&
          typeof h === "number" && Number.isFinite(h) &&
          typeof l === "number" && Number.isFinite(l) &&
          typeof cl === "number" && Number.isFinite(cl) &&
          t < oldestSec   // strictly older than what we already have
        ) {
          olderValidated.push({ time: t, open: o, high: h, low: l, close: cl, volume: typeof v === "number" ? v : 0 });
        }
      }
      olderValidated.sort((a, b) => a.time - b.time);
      if (olderValidated.length === 0) {
        noMoreHistoryRef.current = true;
        return;
      }
      const addedCount = olderValidated.length;
      const prevTotal  = cur.length;
      candles.current  = [...olderValidated, ...cur];
      const newTotal   = candles.current.length;

      // Re-render with the larger dataset, then shift the dataZoom window
      // so the same candles remain on screen (no visual jump).
      const chart = chartRef.current;
      let prevStartPct = 0, prevEndPct = 100;
      if (chart) {
        const opt = chart.getOption() as { dataZoom?: { start?: number; end?: number }[] };
        const dz0 = (opt.dataZoom || [])[0];
        if (dz0) {
          prevStartPct = dz0.start ?? 0;
          prevEndPct   = dz0.end   ?? 100;
        }
      }
      // Map the previously-visible window (in old indices) to new indices.
      const oldStartIdx = (prevStartPct / 100) * (prevTotal - 1);
      const oldEndIdx   = (prevEndPct   / 100) * (prevTotal - 1);
      const newStartIdx = oldStartIdx + addedCount;
      const newEndIdx   = oldEndIdx   + addedCount;
      const newStartPct = (newStartIdx / (newTotal - 1)) * 100;
      const newEndPct   = (newEndIdx   / (newTotal - 1)) * 100;

      renderChartRef.current?.();
      // Apply the shifted window after the re-render so the user sees the
      // same candles in the same positions, just with more room to pan left.
      requestAnimationFrame(() => {
        chartRef.current?.dispatchAction({
          type: "dataZoom",
          start: newStartPct,
          end:   newEndPct,
        });
      });
    } catch {
      // Network failure or 404 — don't lock out future attempts permanently;
      // the user can scroll right and try again.
    } finally {
      loadingMoreRef.current = false;
      setLoadingMore(false);
    }
  }, [symbol]);

  const loadMoreHistoryRef = useRef<(() => void) | null>(null);
  useEffect(() => { loadMoreHistoryRef.current = loadMoreHistory; }, [loadMoreHistory]);

  // ── Init ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    const div = containerRef.current;
    if (!div) return;
    const chart = echarts.init(div, null, { renderer: "canvas" });
    chartRef.current = chart;

    chart.on("dataZoom", () => {
      requestAnimationFrame(() => paintSvgRef.current?.());
      // Pan-to-load-more: when the visible window reaches the very left edge,
      // ask for an older chunk. Throttled by loadingMoreRef inside the
      // callback so rapid drag events don't trigger parallel fetches.
      try {
        const opt = chart.getOption() as { dataZoom?: { start?: number; end?: number }[] };
        const dz0 = (opt.dataZoom || [])[0];
        if (dz0 && (dz0.start ?? 0) <= 1.5) {
          loadMoreHistoryRef.current?.();
        }
      } catch { /* defensive */ }
    });
    chart.on("rendered",  () => { requestAnimationFrame(() => paintSvgRef.current?.()); });

    // Update OHLCV header on crosshair move
    chart.on("updateAxisPointer", (e: any) => {
      const axesInfo = e?.axesInfo;
      if (!axesInfo?.length) { setHoverCandle(null); setHoverIdx(-1); return; }
      const info = axesInfo.find((a: any) => a.axisDim === "x" && a.axisIndex === 0);
      if (!info) { setHoverCandle(null); setHoverIdx(-1); return; }
      const idx = typeof info.value === "number" ? info.value : parseInt(String(info.value));
      if (idx >= 0 && idx < candles.current.length) {
        const c = candles.current[idx];
        const showTime = INTRADAY_INTERVALS.has(intervalRef.current);
        setHoverCandle({ date: toDateStr(c.time, showTime), o: c.open, h: c.high, l: c.low, c: c.close, v: c.volume });
        setHoverIdx(idx);
      } else {
        setHoverCandle(null);
        setHoverIdx(-1);
      }
    });

    const ro = new ResizeObserver(() => {
      chart.resize();
      requestAnimationFrame(() => paintSvg());
    });
    ro.observe(div);

    // Initial fetch is driven by the [symbol, periodCfg] effect below, which
    // fires on mount via fetchDataRef. Avoids a double fetch on first render.
    return () => { ro.disconnect(); chart.dispose(); chartRef.current = null; };
  }, []);

  // Sync stable refs so long-lived listeners and cross-callback calls always
  // see the latest closures, without bloating effect dep arrays into cascades.
  useEffect(() => { paintSvgRef.current   = paintSvg;   }, [paintSvg]);
  useEffect(() => { renderChartRef.current = renderChart; }, [renderChart]);
  useEffect(() => { fetchDataRef.current  = fetchData;  }, [fetchData]);

  useEffect(() => { fetchDataRef.current?.();  }, [symbol, periodCfg]);
  useEffect(() => { renderChartRef.current?.(); }, [indicators, chartType]);
  useEffect(() => { if (candles.current.length) renderChartRef.current?.(); }, [theme]);
  useEffect(() => { paintSvgRef.current?.(); }, [drawings]);

  // ── Drawing helpers ────────────────────────────────────────────────────────
  const getXY = (e: React.MouseEvent<HTMLDivElement>) => {
    const div = containerRef.current;
    if (!div) return null;
    const r = div.getBoundingClientRect();
    return { px: e.clientX - r.left, py: e.clientY - r.top };
  };

  // Convert pixel to data coords; clamps to grid boundary if cursor is in margins
  const pixelToData = (px: number, py: number) => {
    const chart = chartRef.current;
    if (!chart) return null;
    let pt = chart.convertFromPixel({ gridIndex: 0 }, [px, py]);
    if (!pt) {
      // Cursor is in a chart margin — clamp to the nearest grid edge and retry
      const W = chart.getWidth(), H = chart.getHeight();
      const cx = Math.max(CHART_GL + 1, Math.min(W - CHART_GR - 1, px));
      const cy = Math.max(2, Math.min(H * 0.95, py));
      pt = chart.convertFromPixel({ gridIndex: 0 }, [cx, cy]);
    }
    if (!pt) return null;
    const xIdx = Math.max(0, Math.min(Math.round(pt[0] as number), candles.current.length - 1));
    return { xIdx, y: pt[1] as number };
  };

  const saveDrawing = (shape: Record<string, unknown>) => {
    onDrawingAdd({ id: uid(), shape });
    onDrawingDone?.();
    paintSvg();
  };

  const forwardToChart = (e: React.MouseEvent, type?: string) => {
    const canvas = containerRef.current?.querySelector("canvas");
    if (!canvas) return;
    canvas.dispatchEvent(new MouseEvent(type ?? e.type, {
      bubbles: false, cancelable: true,
      clientX: e.clientX, clientY: e.clientY,
      button: e.button, buttons: e.buttons ?? 0,
      shiftKey: e.shiftKey, ctrlKey: e.ctrlKey,
    }));
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    // Pointer-mode drag is now initiated by the native capture listener.
    // The overlay is only mounted when isDraggingDrawing || drawingTool!=="none".
    if (drawingTool === "none") return;

    e.preventDefault();
    onActivate();

    const pos = getXY(e);
    if (!pos) return;

    // ── Phase-2 finalise (parallel channel / pitchfork) ──────────────────
    if (phase2State.current) {
      const p2 = phase2State.current;
      const d2 = pixelToData(pos.px, pos.py);
      phase2State.current = null;
      if (d2) {
        if (p2.tool === "parallelch") {
          saveDrawing({ type: "parallelch",
            x0Idx: p2.x0Idx, y0: p2.y0, x1Idx: p2.x1Idx, y1: p2.y1, y2: d2.y });
        } else {
          const spread = Math.abs(pos.py - p2.py1);
          const dx = p2.px1 - p2.px0, dy = p2.py1 - p2.py0;
          const len = Math.hypot(dx, dy);
          const spreadFrac = len > 0 ? spread / len : 0;
          saveDrawing({ type: "pitchfork",
            x0Idx: p2.x0Idx, y0: p2.y0, x1Idx: p2.x1Idx, y1: p2.y1, spreadFrac });
        }
      } else {
        paintSvg();
      }
      return;
    }

    if (drawingTool === "eraser") {
      const chart = chartRef.current;
      if (!chart || !candles.current.length) return;
      const hitId = hitTestDrawings(pos.px, pos.py, drawings, chart, candles.current);
      if (hitId) onDrawingErase(hitId);
      return;
    }

    const data = pixelToData(pos.px, pos.py);
    if (!data) return;

    // Click-only tools — create shape immediately, no drag needed
    if (drawingTool === "arrowmarker")
      { saveDrawing({ type: "arrowmarker", xIdx: data.xIdx, y: data.y }); return; }
    if (drawingTool === "arrowmarkup")
      { saveDrawing({ type: "arrowmarkup", xIdx: data.xIdx, y: data.y }); return; }
    if (drawingTool === "arrowmarkdown")
      { saveDrawing({ type: "arrowmarkdown", xIdx: data.xIdx, y: data.y }); return; }
    if (drawingTool === "flag")
      { saveDrawing({ type: "flag", xIdx: data.xIdx, y: data.y }); return; }
    if (drawingTool === "note") {
      const text = window.prompt("Enter note text:") ?? "";
      if (text.trim()) saveDrawing({ type: "note", xIdx: data.xIdx, y: data.y, text: text.trim() });
      return;
    }

    dragStart.current = { px: pos.px, py: pos.py, xIdx: data.xIdx, y: data.y };
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const pos = getXY(e);
    if (!pos) return;

    // ── Pointer-mode: only drag preview (overlay is shown only during drag) ────
    if (drawingTool === "none") {
      const chart = chartRef.current;
      if (!chart || !candles.current.length) return;
      if (dragDrawingState.current) {
        const ds = dragDrawingState.current;
        const newShape = applyShapeDelta(ds.origShape, chart, ds.startPx, ds.startPy, pos.px, pos.py, ds.kind);
        const previewEls = shapeToPixels(newShape as any, chart, candles.current);
        paintSvgRef.current?.(previewEls ?? null, null, ds.id, null);
      }
      return;
    }

    if (drawingTool === "eraser") {
      eraserPos.current = { x: pos.px, y: pos.py };
      paintSvg(null, eraserPos.current);
      return;
    }

    // ── Phase-2 preview (parallel channel / pitchfork offset) ────────────
    if (phase2State.current) {
      const p2 = phase2State.current;
      const chart = chartRef.current;
      if (!chart) return;
      const W = chart.getWidth(), H = chart.getHeight();
      const dx = p2.px1 - p2.px0, dy = p2.py1 - p2.py0;
      const len = Math.hypot(dx, dy);
      if (len < 1) return;
      const nx = dx / len, ny = dy / len;
      const perpX = -ny, perpY = nx;

      if (p2.tool === "parallelch") {
        const off = pos.py - p2.py0;
        paintSvg([
          { type: "line", x1: p2.px0, y1: p2.py0,         x2: p2.px1, y2: p2.py1 },
          { type: "line", x1: p2.px0, y1: p2.py0 + off,   x2: p2.px1, y2: p2.py1 + off },
          { type: "line", x1: p2.px0, y1: p2.py0 + off/2, x2: p2.px1, y2: p2.py1 + off/2, dash: true, color: DRAW_CLR + "88" },
        ]);
      } else {
        const spread = Math.abs(pos.py - p2.py1);
        const f1x = p2.px1 + perpX * spread, f1y = p2.py1 + perpY * spread;
        const f2x = p2.px1 - perpX * spread, f2y = p2.py1 - perpY * spread;
        const [f1ex, f1ey] = extendRay(f1x, f1y, nx, ny, 0, 0, W, H);
        const [f2ex, f2ey] = extendRay(f2x, f2y, nx, ny, 0, 0, W, H);
        paintSvg([
          { type: "line", x1: p2.px0, y1: p2.py0, x2: p2.px1, y2: p2.py1 },
          { type: "line", x1: f1x, y1: f1y, x2: f1ex, y2: f1ey },
          { type: "line", x1: f2x, y1: f2y, x2: f2ex, y2: f2ey },
          { type: "line", x1: f1x, y1: f1y, x2: f2x, y2: f2y, dash: true, color: DRAW_CLR + "88" },
        ]);
      }
      return;
    }

    if (!dragStart.current) return;
    const chart = chartRef.current;
    if (!chart) return;

    const s = dragStart.current;
    const b = getGridBounds(chart, candles.current);
    const W = chart.getWidth(), H = chart.getHeight();

    let preview: SvgEl | SvgEl[] | null = null;

    if (drawingTool === "hline")
      preview = { type: "line", x1: b.leftX, y1: s.py, x2: b.rightX, y2: s.py };
    else if (drawingTool === "hray")
      preview = { type: "line", x1: s.px, y1: s.py, x2: b.rightX, y2: s.py };
    else if (drawingTool === "vline")
      preview = { type: "line", x1: s.px, y1: b.topY, x2: s.px, y2: b.botY };
    else if (drawingTool === "crossline")
      preview = [
        { type: "line", x1: b.leftX, y1: s.py, x2: b.rightX, y2: s.py },
        { type: "line", x1: s.px, y1: b.topY, x2: s.px, y2: b.botY },
      ];
    else if (drawingTool === "trendline" || drawingTool === "ray" || drawingTool === "extendedline") {
      const dx = pos.px - s.px, dy = pos.py - s.py;
      const len = Math.hypot(dx, dy);
      if (drawingTool === "trendline" || len < 1)
        preview = { type: "line", x1: s.px, y1: s.py, x2: pos.px, y2: pos.py };
      else if (drawingTool === "ray") {
        const [ex, ey] = extendRay(s.px, s.py, dx / len, dy / len, 0, 0, W, H);
        preview = { type: "line", x1: s.px, y1: s.py, x2: ex, y2: ey };
      } else {
        const nx = dx / len, ny = dy / len;
        const [ex1, ey1] = extendRay(s.px, s.py,  nx,  ny, 0, 0, W, H);
        const [ex2, ey2] = extendRay(s.px, s.py, -nx, -ny, 0, 0, W, H);
        preview = { type: "line", x1: ex2, y1: ey2, x2: ex1, y2: ey1 };
      }
    }
    else if (drawingTool === "rectangle" || drawingTool === "gannbox" || drawingTool === "measure" || drawingTool === "longposition" || drawingTool === "shortposition")
      preview = { type: "rect", x: Math.min(s.px, pos.px), y: Math.min(s.py, pos.py), w: Math.abs(pos.px - s.px), h: Math.abs(pos.py - s.py) };
    else if (drawingTool === "circle") {
      const r = Math.hypot(pos.px - s.px, pos.py - s.py);
      preview = [{ type: "circle", cx: s.px, cy: s.py, r }];
    }
    else if (drawingTool === "ellipse") {
      const rx = Math.abs(pos.px - s.px) / 2, ry = Math.abs(pos.py - s.py) / 2;
      preview = [{ type: "ellipse", cx: (s.px + pos.px) / 2, cy: (s.py + pos.py) / 2, rx, ry }];
    }
    // Phase-1 for channel/fork: just show the base trendline during drag
    else if (drawingTool === "parallelch" || drawingTool === "pitchfork")
      preview = { type: "line", x1: s.px, y1: s.py, x2: pos.px, y2: pos.py };
    else if (drawingTool === "fibretracement" || drawingTool === "fibextension") {
      const levels = drawingTool === "fibextension"
        ? [0, 0.236, 0.382, 0.618, 1, 1.272, 1.618, 2.618]
        : [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];
      const colors = ["#ef4444","#f97316","#eab308","#22c55e","#3b82f6","#8b5cf6","#ef4444","#f97316"];
      preview = [
        { type: "line", x1: s.px, y1: s.py, x2: pos.px, y2: pos.py, dash: true, color: DRAW_CLR + "66" },
        ...levels.map((r, i) => ({
          type: "line" as const,
          x1: b.leftX, y1: s.py + (pos.py - s.py) * r,
          x2: b.rightX, y2: s.py + (pos.py - s.py) * r,
          color: colors[i % colors.length],
        } as SvgEl)),
      ];
    }
    else if (drawingTool === "fibtimezone") {
      const interval = Math.abs(pos.px - s.px);
      if (interval > 2) {
        const fibNums = [1, 2, 3, 5, 8, 13, 21, 34];
        preview = [
          { type: "line", x1: s.px, y1: b.topY, x2: s.px, y2: b.botY },
          ...fibNums.map(n => {
            const x = s.px + n * Math.sign(pos.px - s.px) * interval;
            return { type: "line" as const, x1: x, y1: b.topY, x2: x, y2: b.botY, dash: true } as SvgEl;
          }).filter(l => l.type === "line" && l.x1 >= 0 && l.x1 <= W),
        ];
      }
    }
    else if (drawingTool === "fibfan") {
      const dx = pos.px - s.px, dy = pos.py - s.py;
      const ratios = [0.236, 0.382, 0.5, 0.618, 0.786];
      const colors = ["#f97316","#eab308","#22c55e","#3b82f6","#8b5cf6"];
      const els: SvgEl[] = [];
      for (let i = 0; i < ratios.length; i++) {
        const fanDy = dy * ratios[i];
        const fanLen = Math.hypot(dx, fanDy);
        if (fanLen < 1) continue;
        const [ex, ey] = extendRay(s.px, s.py, dx / fanLen, fanDy / fanLen, 0, 0, W, H);
        els.push({ type: "line", x1: s.px, y1: s.py, x2: ex, y2: ey, dash: true, color: colors[i] });
      }
      preview = els;
    }
    else if (drawingTool === "gannfan") {
      const dx = pos.px - s.px, dy = pos.py - s.py;
      const ratios = [1/4, 1/3, 1/2, 1, 2, 3, 4];
      const els: SvgEl[] = [];
      for (const r of ratios) {
        const fanDy = dy * r;
        const fanLen = Math.hypot(dx, fanDy);
        if (fanLen < 1) continue;
        const [ex, ey] = extendRay(s.px, s.py, dx / fanLen, fanDy / fanLen, 0, 0, W, H);
        els.push({ type: "line", x1: s.px, y1: s.py, x2: ex, y2: ey, dash: r !== 1, color: r === 1 ? DRAW_CLR : DRAW_CLR + "99" });
      }
      preview = els;
    }
    else if (drawingTool === "cycliclines") {
      const interval = Math.abs(pos.px - s.px);
      if (interval > 2) {
        const els: SvgEl[] = [{ type: "line", x1: s.px, y1: b.topY, x2: s.px, y2: b.botY }];
        for (let x = s.px + interval; x <= W + 10; x += interval) {
          els.push({ type: "line", x1: x, y1: b.topY, x2: x, y2: b.botY, dash: true });
        }
        for (let x = s.px - interval; x >= -10; x -= interval) {
          els.push({ type: "line", x1: x, y1: b.topY, x2: x, y2: b.botY, dash: true });
        }
        preview = els;
      }
    }

    paintSvg(preview);
  };

  const handleMouseUp = (e: React.MouseEvent<HTMLDivElement>) => {
    // ── Pointer-mode: finalize drag ──────────────────────────────────────────
    if (drawingTool === "none") {
      if (dragDrawingState.current) {
        const ds = dragDrawingState.current;
        const chart = chartRef.current;
        const pos = getXY(e);
        if (chart && pos) {
          const newShape = applyShapeDelta(ds.origShape, chart, ds.startPx, ds.startPy, pos.px, pos.py, ds.kind);
          onDrawingUpdate?.(ds.id, newShape);
        }
        dragDrawingState.current = null;
        setIsDraggingDrawing(false); // hide drag overlay → ECharts resumes native handling
        // Repaint with handles still shown if still hovering
        const chart2 = chartRef.current;
        if (chart2 && hoveredDrawingId) {
          const hd = drawings.find(d => d.id === hoveredDrawingId);
          const handles = hd ? getShapeHandles(hd.shape, chart2) : null;
          paintSvgRef.current?.(null, null, null, handles);
        } else {
          paintSvgRef.current?.();
        }
      }
      return;
    }

    if (!dragStart.current) return;
    const pos = getXY(e);
    const s = dragStart.current;
    dragStart.current = null;

    // Single-click tools (use start-point data only)
    let shape: Record<string, unknown> | null = null;
    if (drawingTool === "hline")      shape = { type: "hline",      y: s.y };
    else if (drawingTool === "hray")  shape = { type: "hray",      xIdx: s.xIdx, y: s.y };
    else if (drawingTool === "vline") shape = { type: "vline",     xIdx: s.xIdx };
    else if (drawingTool === "crossline") shape = { type: "crossline", xIdx: s.xIdx, y: s.y };

    if (shape) { saveDrawing(shape); return; }

    // Two-endpoint tools
    const data = pos ? pixelToData(pos.px, pos.py) : null;
    if (!data || !pos) { paintSvg(); return; }

    // ── Two-phase tools: enter phase-2 instead of saving immediately ─────
    if (drawingTool === "parallelch" || drawingTool === "pitchfork") {
      phase2State.current = {
        tool: drawingTool,
        x0Idx: s.xIdx, y0: s.y, x1Idx: data.xIdx, y1: data.y,
        px0: s.px, py0: s.py, px1: pos.px, py1: pos.py,
      };
      paintSvg([{ type: "line", x1: s.px, y1: s.py, x2: pos.px, y2: pos.py }]);
      return;
    }

    const two = { x0Idx: s.xIdx, y0: s.y, x1Idx: data.xIdx, y1: data.y };
    if      (drawingTool === "trendline")      shape = { type: "trendline",     ...two };
    else if (drawingTool === "ray")            shape = { type: "ray",           ...two };
    else if (drawingTool === "extendedline")   shape = { type: "extendedline",  ...two };
    else if (drawingTool === "rectangle")      shape = { type: "rectangle",     ...two };
    else if (drawingTool === "circle")         shape = { type: "circle",        ...two };
    else if (drawingTool === "ellipse")        shape = { type: "ellipse",       ...two };
    else if (drawingTool === "fibretracement") shape = { type: "fibretracement",...two };
    else if (drawingTool === "fibextension")   shape = { type: "fibextension",  ...two };
    else if (drawingTool === "fibtimezone")    shape = { type: "fibtimezone",   ...two };
    else if (drawingTool === "fibfan")         shape = { type: "fibfan",        ...two };
    else if (drawingTool === "gannfan")        shape = { type: "gannfan",       ...two };
    else if (drawingTool === "gannbox")        shape = { type: "gannbox",       ...two };
    else if (drawingTool === "longposition")   shape = { type: "longposition",  ...two };
    else if (drawingTool === "shortposition")  shape = { type: "shortposition", ...two };
    else if (drawingTool === "cycliclines")    shape = { type: "cycliclines",   ...two };
    else if (drawingTool === "measure")        shape = { type: "measure",       ...two };

    if (shape) saveDrawing(shape); else paintSvg();
  };

  // ── Derived display values ─────────────────────────────────────────────────
  const display = hoverCandle ?? (lastCandle ? {
    date: "", o: 0, h: 0, l: 0, c: lastCandle.c, v: 0,
  } : null);

  const priceColor = lastCandle
    ? (lastCandle.pct >= 0 ? "#26a69a" : "#ef5350")
    : "#d1d4dc";

  // ── Indicator pill value at hover (or last candle) ──────────────────────────
  const indVal = (key: string): number | null => {
    const arr = indicatorDataRef.current[key];
    if (!arr) return null;
    const i = hoverIdx >= 0 ? hoverIdx : candles.current.length - 1;
    return i >= 0 && i < arr.length ? arr[i] : null;
  };

  const hasAnyInd = indicators.size > 0;
  const TC = getThemeColors(theme);

  return (
    <div
      className={`flex flex-col h-full rounded overflow-hidden border transition-colors ${isActive ? "border-indigo-500/60" : "border-transparent"}`}
      style={{ background: TC.bg }}
      onClick={() => { setCtxMenu(null); onActivate(); }}
    >
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex items-start gap-3 px-3 py-1.5 shrink-0" style={{ borderBottom: `1px solid ${TC.headBor}` }}>
        {/* Symbol + price + OHLCV */}
        <div className="flex flex-col justify-center min-w-0">
          {/* Row 1: symbol name + OHLCV on hover */}
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="font-bold text-sm tracking-wide leading-tight" style={{ color: TC.symTxt }}>{symbol}</span>
            {symbolName && !hoverCandle && <span className="text-[11px] truncate max-w-[130px] leading-tight" style={{ color: TC.muTxt }}>{symbolName}</span>}
            {hoverCandle && (
              <>
                <span className="text-[11px]" style={{ color: TC.muTxt }}>{hoverCandle.date}</span>
                <span className="text-[11px]"><span style={{ color: TC.muTxt }}>O</span> <span style={{ color: TC.ohlcVal }}>{fmtPrice(hoverCandle.o)}</span></span>
                <span className="text-[11px]"><span style={{ color: "#26a69a" }}>H</span> <span style={{ color: TC.ohlcVal }}>{fmtPrice(hoverCandle.h)}</span></span>
                <span className="text-[11px]"><span style={{ color: "#ef5350" }}>L</span> <span style={{ color: TC.ohlcVal }}>{fmtPrice(hoverCandle.l)}</span></span>
                <span className="text-[11px]"><span style={{ color: TC.muTxt }}>C</span> <span style={{ color: TC.ohlcVal }}>{fmtPrice(hoverCandle.c)}</span></span>
                <span className="text-[11px]"><span style={{ color: TC.muTxt }}>V</span> <span style={{ color: TC.ohlcVal }}>{fmtVol(hoverCandle.v)}</span></span>
              </>
            )}
          </div>
          {/* Row 2: price + pct */}
          {lastCandle && (
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="text-[13px] font-semibold" style={{ color: priceColor }}>₹{fmtPrice(lastCandle.c)}</span>
              <span className="text-[11px]" style={{ color: priceColor }}>{lastCandle.pct >= 0 ? "+" : ""}{lastCandle.pct.toFixed(2)}%</span>
            </div>
          )}
          {/* Row 3: active indicator pills (TradingView-style) — click X to remove */}
          {hasAnyInd && (
            <div className="flex items-center gap-2 mt-0.5 flex-wrap">
              {[...indicators].map(key => {
                const def = IND_BY_KEY[key];
                if (!def) return null;
                const seriesKey = def.pillSeries ?? "main";
                const val = indVal(`${def.key}.${seriesKey}`);
                const digits = def.pillDigits ?? (def.paneOwn ? 2 : undefined);
                const display = val === null
                  ? null
                  : digits !== undefined
                    ? (val as number).toFixed(digits)
                    : fmtPrice(val as number);
                return (
                  <span key={key} className="group flex items-center gap-1 text-[10px] rounded px-1.5 py-0.5 hover:bg-white/5">
                    <span style={{ color: def.pillColor }} className="font-medium">{def.label}</span>
                    {display !== null && <span className="text-gray-400">{display}</span>}
                    <button
                      type="button"
                      title={`Remove ${def.label}`}
                      onClick={(e) => { e.stopPropagation(); onIndicatorRemove?.(key); }}
                      className="ml-0.5 w-3.5 h-3.5 flex items-center justify-center rounded-sm text-gray-500 hover:text-red-400 hover:bg-red-500/15 opacity-60 group-hover:opacity-100 transition-opacity"
                    >
                      <svg viewBox="0 0 10 10" width="8" height="8" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                        <path d="M2 2 L8 8 M8 2 L2 8" />
                      </svg>
                    </button>
                  </span>
                );
              })}
            </div>
          )}
        </div>
        {loading && <span className="ml-auto text-[10px] text-gray-600 animate-pulse self-center">Loading…</span>}
        {!loading && loadingMore && <span className="ml-auto text-[10px] text-gray-500 animate-pulse self-center">Loading older candles…</span>}
      </div>

      {/* ── Chart + SVG overlay ──────────────────────────────────────────── */}
      <div
        className="flex-1 relative min-h-0"
        onContextMenu={e => {
          e.preventDefault();
          onActivate();
          const r = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
          setCtxMenu({ x: e.clientX - r.left, y: e.clientY - r.top });
        }}
      >
        <div ref={containerRef} className="absolute inset-0" />
        {loading && (
          <div className="absolute inset-0 z-30 pointer-events-none transition-opacity" style={{ background: TC.dimBg }} />
        )}
        {!loading && loadError && (
          <div className="absolute inset-0 z-30 flex items-center justify-center pointer-events-none">
            <div
              className="px-4 py-2 rounded-md text-xs font-medium border"
              style={{
                background: theme === "dark" ? "rgba(127,29,29,0.85)" : "rgba(254,226,226,0.95)",
                color: theme === "dark" ? "#fecaca" : "#991b1b",
                borderColor: theme === "dark" ? "rgba(248,113,113,0.4)" : "rgba(248,113,113,0.5)",
              }}
            >
              {loadError}
            </div>
          </div>
        )}
        <svg ref={svgRef} className="absolute inset-0" style={{ pointerEvents: "none", zIndex: 10 }} />
        {/* Overlay: only shown while actively drawing or dragging a drawing.
            ECharts handles the mouse natively at all other times → smooth crosshair. */}
        {(drawingTool !== "none" || isDraggingDrawing) && (
          <div
            className="absolute inset-0"
            style={{
              zIndex: 20,
              cursor: drawingTool === "eraser" ? "none"
                : isDraggingDrawing ? "grabbing"
                : "crosshair",
            }}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={(e) => {
              eraserPos.current = null;
              if (dragStart.current) { dragStart.current = null; }
              if (dragDrawingState.current) { dragDrawingState.current = null; setIsDraggingDrawing(false); }
              if (hoveredDrawingId) { hoveredDrawingIdRef.current = null; setHoveredDrawingId(null); }
              paintSvg();
              const canvas = containerRef.current?.querySelector("canvas");
              if (canvas) canvas.dispatchEvent(new MouseEvent("mouseout", { bubbles: true, clientX: e.clientX, clientY: e.clientY }));
            }}
          />
        )}

        {/* ── Drawing right-click context menu ─────────────────────── */}
        {drawingCtxMenu && (() => {
          const dm = drawingCtxMenu;
          const dShape = drawings.find(d => d.id === dm.id);
          const curW   = typeof dShape?.shape?.width === "number" ? dShape.shape.width : 1.5;
          const widths = [1, 1.5, 2, 3, 4];
          const containerRect = containerRef.current?.getBoundingClientRect();
          const menuLeft = containerRect ? Math.min(dm.x - containerRect.left, containerRect.width - 170) : dm.x;
          const menuTop  = containerRect ? Math.min(dm.y - containerRect.top,  containerRect.height - 140) : dm.y;
          return (
            <div
              className="absolute z-50 rounded-lg shadow-2xl py-2 min-w-[160px]"
              style={{ left: menuLeft, top: menuTop, background: TC.ctxBg, border: `1px solid ${TC.ctxBor}` }}
              onMouseDown={e => e.stopPropagation()}
            >
              <div className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider" style={{ color: TC.text }}>Line Width</div>
              <div className="flex items-center gap-1 px-3 pb-2">
                {widths.map(w => (
                  <button
                    key={w}
                    title={`${w}px`}
                    className="flex-1 rounded flex items-center justify-center py-1.5 transition-colors"
                    style={{ background: Math.abs(curW - w) < 0.1 ? TC.grid : "transparent", border: `1px solid ${TC.ctxBor}` }}
                    onClick={() => {
                      if (dShape) onDrawingUpdate?.(dm.id, { ...dShape.shape, width: w });
                      setDrawingCtxMenu(null);
                    }}
                  >
                    <svg width="20" height={w === 1 ? 4 : w * 2} viewBox={`0 0 20 ${w * 2}`}>
                      <line x1="2" y1={w} x2="18" y2={w} stroke={TC.tipText} strokeWidth={w} />
                    </svg>
                  </button>
                ))}
              </div>
              <div style={{ borderTop: `1px solid ${TC.ctxBor}` }} />
              <button
                className="w-full text-left px-3 py-1.5 text-xs transition-colors mt-1"
                style={{ color: "#ef4444" }}
                onMouseEnter={e => (e.currentTarget.style.background = TC.grid)}
                onMouseLeave={e => (e.currentTarget.style.background = "")}
                onClick={() => { onDrawingErase(dm.id); setDrawingCtxMenu(null); }}
              >Delete drawing</button>
            </div>
          );
        })()}

        {/* ── Right-click context menu ──────────────────────────────── */}
        {ctxMenu && (
          <div
            className="absolute z-50 rounded-lg shadow-2xl py-1 min-w-[160px]"
            style={{ left: Math.min(ctxMenu.x, (containerRef.current?.offsetWidth ?? 300) - 170), top: ctxMenu.y, background: TC.ctxBg, border: `1px solid ${TC.ctxBor}` }}
            onMouseDown={e => e.stopPropagation()}
          >
            {[
              { label: "Reset zoom",    action: () => { chartRef.current?.dispatchAction({ type: "dataZoom", start: 60, end: 100 }); setCtxMenu(null); } },
              { label: "Clear drawings",action: () => { onClearDrawings?.(); setCtxMenu(null); } },
              { label: "Reload data",   action: () => { fetchData(); setCtxMenu(null); } },
            ].map((item, i) => (
              <button
                key={item.label}
                className="w-full text-left px-4 py-1.5 text-xs transition-colors"
                style={{ color: TC.tipText, ...(i === 1 ? { borderTop: `1px solid ${TC.ctxBor}`, borderBottom: `1px solid ${TC.ctxBor}` } : {}) }}
                onMouseEnter={e => (e.currentTarget.style.background = TC.grid)}
                onMouseLeave={e => (e.currentTarget.style.background = "")}
                onClick={item.action}
              >{item.label}</button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
