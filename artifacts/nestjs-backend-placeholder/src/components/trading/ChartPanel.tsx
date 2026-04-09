import { useEffect, useRef, useState, useCallback } from "react";
import * as echarts from "echarts";
import { calcEMA, calcSMA, calcRSI, calcMACD, calcBollingerBands } from "@/lib/indicators";

export type DrawingTool = "none" | "trendline" | "hline" | "vline" | "rectangle" | "eraser";
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
  showRSI: boolean;
  showMACD: boolean;
  isActive: boolean;
  drawings: Drawing[];
  onDrawingAdd: (d: Drawing) => void;
  onDrawingErase: (id: string) => void;
  onClearDrawings?: () => void;
  onActivate: () => void;
}

const DARK     = "#131722";
const GRID_CLR = "rgba(255,255,255,0.06)";
const TEXT_CLR = "#787b86";
const DRAW_CLR = "#6366f1";

const IND_META: Record<string, { label: string; color: string }> = {
  ema9:   { label: "EMA 9",   color: "#f59e0b" },
  ema21:  { label: "EMA 21",  color: "#6366f1" },
  ema50:  { label: "EMA 50",  color: "#10b981" },
  ema200: { label: "EMA 200", color: "#ef4444" },
  sma50:  { label: "SMA 50",  color: "#a78bfa" },
  bb:     { label: "BB (20)", color: "#3b82f6" },
};

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
function computeHA(cs: Candle[]): Candle[] {
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

interface SvgLine   { type: "line"; x1: number; y1: number; x2: number; y2: number }
interface SvgRect   { type: "rect"; x: number;  y: number;  w: number;  h: number  }
interface SvgPixels { id: string; el: SvgLine | SvgRect }

function getGridBounds(chart: echarts.ECharts, n: number, candles: Candle[]) {
  const [leftX]  = chart.convertToPixel({ gridIndex: 0 }, [0, 0]);
  const [rightX] = chart.convertToPixel({ gridIndex: 0 }, [Math.max(0, n - 1), 0]);
  const highs = candles.map(c => c.high);
  const lows  = candles.map(c => c.low);
  const maxH  = highs.length ? Math.max(...highs) : 0;
  const minL  = lows.length  ? Math.min(...lows)  : 0;
  const [, topY] = chart.convertToPixel({ gridIndex: 0 }, [0, maxH]);
  const [, botY] = chart.convertToPixel({ gridIndex: 0 }, [0, minL]);
  return { leftX, rightX, topY: Math.min(topY, botY), botY: Math.max(topY, botY) };
}

function shapeToPixels(
  shape: Record<string, unknown>,
  chart: echarts.ECharts,
  candles: Candle[],
): SvgLine | SvgRect | null {
  const s = shape as any;
  const n = candles.length;
  const b = getGridBounds(chart, n, candles);

  if (s.type === "hline") {
    const [, py] = chart.convertToPixel({ gridIndex: 0 }, [0, s.y]);
    if (py < b.topY - 4 || py > b.botY + 4) return null;
    return { type: "line", x1: b.leftX, y1: py, x2: b.rightX, y2: py };
  }
  if (s.type === "vline") {
    const [px] = chart.convertToPixel({ gridIndex: 0 }, [s.xIdx, 0]);
    if (px < b.leftX - 4 || px > b.rightX + 4) return null;
    return { type: "line", x1: px, y1: b.topY, x2: px, y2: b.botY };
  }
  if (s.type === "trendline") {
    const [px0, py0] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [px1, py1] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    return { type: "line", x1: px0, y1: py0, x2: px1, y2: py1 };
  }
  if (s.type === "rectangle") {
    const [px0, py0] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [px1, py1] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    return { type: "rect", x: Math.min(px0, px1), y: Math.min(py0, py1), w: Math.abs(px1 - px0), h: Math.abs(py1 - py0) };
  }
  return null;
}

// ── Eraser hit-testing ────────────────────────────────────────────────────────

function distToSegment(px: number, py: number, x1: number, y1: number, x2: number, y2: number): number {
  const dx = x2 - x1, dy = y2 - y1;
  const len2 = dx * dx + dy * dy;
  if (len2 === 0) return Math.hypot(px - x1, py - y1);
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / len2));
  return Math.hypot(px - x1 - t * dx, py - y1 - t * dy);
}

function distToRect(px: number, py: number, rx: number, ry: number, rw: number, rh: number): number {
  const insideX = px >= rx && px <= rx + rw;
  const insideY = py >= ry && py <= ry + rh;
  if (insideX && insideY) return Math.min(px - rx, rx + rw - px, py - ry, ry + rh - py);
  const cx = Math.max(rx, Math.min(px, rx + rw));
  const cy = Math.max(ry, Math.min(py, ry + rh));
  return Math.hypot(px - cx, py - cy);
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
    const el = shapeToPixels(d.shape, chart, candles);
    if (!el) continue;
    const dist = el.type === "line"
      ? distToSegment(px, py, el.x1, el.y1, el.x2, el.y2)
      : distToRect(px, py, el.x, el.y, el.w, el.h);
    if (dist < THRESHOLD && (!best || dist < best.dist)) {
      best = { id: d.id, dist };
    }
  }
  return best?.id ?? null;
}

// ── SVG renderer ──────────────────────────────────────────────────────────────

function renderSvg(
  svgEl: SVGSVGElement | null,
  pixels: SvgPixels[],
  preview: SvgLine | SvgRect | null,
  eraserPixel: { x: number; y: number } | null,
) {
  if (!svgEl) return;
  while (svgEl.firstChild) svgEl.removeChild(svgEl.firstChild);

  const add = (el: SvgLine | SvgRect, dash = false, alpha = 1) => {
    const color = DRAW_CLR + (alpha < 1 ? "bb" : "");
    if (el.type === "line") {
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", String(el.x1)); line.setAttribute("y1", String(el.y1));
      line.setAttribute("x2", String(el.x2)); line.setAttribute("y2", String(el.y2));
      line.setAttribute("stroke", color);
      line.setAttribute("stroke-width", "1.5");
      if (dash) line.setAttribute("stroke-dasharray", "5 4");
      svgEl.appendChild(line);
    } else {
      const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      rect.setAttribute("x", String(el.x)); rect.setAttribute("y", String(el.y));
      rect.setAttribute("width", String(el.w)); rect.setAttribute("height", String(el.h));
      rect.setAttribute("stroke", color);
      rect.setAttribute("stroke-width", "1.5");
      rect.setAttribute("fill", "rgba(99,102,241,0.08)");
      svgEl.appendChild(rect);
    }
  };

  for (const p of pixels) add(p.el);
  if (preview) add(preview, preview.type === "line", 0.7);

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
}

// ── Component ──────────────────────────────────────────────────────────────────

interface HoverCandle {
  date: string; o: number; h: number; l: number; c: number; v: number;
}

export default function ChartPanel({
  symbol, symbolName, periodCfg, drawingTool, chartType, indicators,
  showRSI, showMACD, isActive, drawings, onDrawingAdd, onDrawingErase, onClearDrawings, onActivate,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef       = useRef<SVGSVGElement>(null);
  const chartRef     = useRef<echarts.ECharts | null>(null);
  const candles      = useRef<Candle[]>([]);
  const dragStart    = useRef<{ px: number; py: number; xIdx: number; y: number } | null>(null);
  const eraserPos    = useRef<{ x: number; y: number } | null>(null);
  const indicatorDataRef = useRef<Record<string, (number | null)[]>>({});
  const drawingToolRef = useRef<DrawingTool>(drawingTool);
  const intervalRef    = useRef<string>(periodCfg.i);
  const chartTypeRef   = useRef<ChartType>(chartType);
  useEffect(() => { drawingToolRef.current = drawingTool; }, [drawingTool]);
  useEffect(() => { intervalRef.current = periodCfg.i; }, [periodCfg.i]);
  useEffect(() => { chartTypeRef.current = chartType; }, [chartType]);

  const [loading, setLoading]           = useState(true);
  const [hoverCandle, setHoverCandle]   = useState<HoverCandle | null>(null);
  const [hoverIdx, setHoverIdx]         = useState(-1);
  const [lastCandle, setLastCandle]     = useState<{ c: number; pct: number } | null>(null);
  const [ctxMenu, setCtxMenu]           = useState<{ x: number; y: number } | null>(null);

  // ── Repaint SVG ────────────────────────────────────────────────────────────
  const paintSvg = useCallback((
    preview: SvgLine | SvgRect | null = null,
    eraser: { x: number; y: number } | null = null,
  ) => {
    const chart = chartRef.current;
    const svg   = svgRef.current;
    const div   = containerRef.current;
    if (!chart || !svg || !div || !candles.current.length) return;
    svg.setAttribute("width",  String(div.offsetWidth));
    svg.setAttribute("height", String(div.offsetHeight));

    const pixels: SvgPixels[] = drawings
      .map(d => {
        const el = shapeToPixels(d.shape, chart, candles.current);
        return el ? { id: d.id, el } : null;
      })
      .filter(Boolean) as SvgPixels[];

    renderSvg(svg, pixels, preview, eraser);
  }, [drawings]);

  // ── Render ECharts ─────────────────────────────────────────────────────────
  const renderChart = useCallback(() => {
    const chart = chartRef.current;
    if (!chart || !candles.current.length) return;

    const cs       = candles.current;
    const showTime = INTRADAY_INTERVALS.has(intervalRef.current);
    const dates    = cs.map(c => toDateStr(c.time, showTime));
    const ct       = chartTypeRef.current;
    // For Heikin Ashi, transform the raw candles
    const wcs      = ct === "ha" ? computeHA(cs) : cs;
    const closes   = wcs.map(c => c.close);
    const ohlc     = wcs.map(c => [c.open, c.close, c.low, c.high]);

    const hasSub = showRSI || showMACD;

    // ── Grid layout: main chart / volume / sub-panel ──────────────────────
    // Main chart — ends well above volume so x-axis labels don't overlap bars
    // Volume — dates shown only here when no sub-panel, hidden otherwise
    const mainHeight = hasSub ? "48%" : "68%";
    const mainBottom = hasSub ? "44%" : "24%";
    const volTop     = hasSub ? "54%" : "76%";
    const volHeight  = hasSub ? "8%"  : "16%";
    const subTop     = "68%";
    const subHeight  = "26%";

    // Prices on right side — narrow left margin, wider right margin for labels
    const GL = 8, GR = 70;
    const grids: object[] = [
      { top: "4%",  left: GL, right: GR, height: mainHeight },
      { top: volTop, left: GL, right: GR, height: volHeight  },
    ];
    if (hasSub) grids.push({ top: subTop, left: GL, right: GR, height: subHeight });

    // x-axis: labels ONLY on the bottom-most grid
    const xBase = { axisLine: { lineStyle: { color: GRID_CLR } }, axisTick: { show: false } };
    const xAxes: object[] = [
      { ...xBase, gridIndex: 0, data: dates, axisLabel: { show: false }, splitLine: { lineStyle: { color: GRID_CLR } } },
      { ...xBase, gridIndex: 1, data: dates, axisLabel: hasSub ? { show: false } : { color: TEXT_CLR, fontSize: 9, margin: 6, formatter: (v: string) => fmtXLabel(v, showTime) }, splitLine: { show: false } },
    ];
    if (hasSub) {
      xAxes.push({ ...xBase, gridIndex: 2, data: dates, axisLabel: { color: TEXT_CLR, fontSize: 9, margin: 6, formatter: (v: string) => fmtXLabel(v, showTime) }, splitLine: { lineStyle: { color: GRID_CLR } } });
    }

    // y-axis — all positioned on the RIGHT side
    const yBase = { axisLine: { show: false }, axisTick: { show: false }, position: "right" };
    const yAxes: object[] = [
      {
        ...yBase, gridIndex: 0, scale: true,
        axisLabel: { color: TEXT_CLR, fontSize: 10, margin: 6 },
        splitLine: { lineStyle: { color: GRID_CLR } },
      },
      {
        ...yBase, gridIndex: 1, scale: true,
        axisLabel: { show: true, color: TEXT_CLR, fontSize: 9, margin: 6, formatter: (v: number) => fmtVol(v) },
        splitLine: { show: false },
        splitNumber: 2,
      },
    ];
    if (hasSub) {
      yAxes.push({
        ...yBase, gridIndex: 2, scale: true,
        axisLabel: { color: TEXT_CLR, fontSize: 9, margin: 6 },
        splitLine: { lineStyle: { color: GRID_CLR } },
        splitNumber: 3,
      });
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

    const MA = [
      { key: "ema9",   label: "EMA 9",   color: "#f59e0b", fn: () => calcEMA(closes, 9)   },
      { key: "ema21",  label: "EMA 21",  color: "#6366f1", fn: () => calcEMA(closes, 21)  },
      { key: "ema50",  label: "EMA 50",  color: "#10b981", fn: () => calcEMA(closes, 50)  },
      { key: "ema200", label: "EMA 200", color: "#ef4444", fn: () => calcEMA(closes, 200) },
      { key: "sma50",  label: "SMA 50",  color: "#a78bfa", fn: () => calcSMA(closes, 50)  },
    ];
    for (const m of MA) {
      if (!indicators.has(m.key)) continue;
      const vals = m.fn().map(v => v ?? null);
      indicatorDataRef.current[m.key] = vals;
      series.push({ name: m.label, type: "line", xAxisIndex: 0, yAxisIndex: 0, data: vals, lineStyle: { color: m.color, width: 1.5 }, showSymbol: false, connectNulls: false });
    }
    if (indicators.has("bb")) {
      const bb = calcBollingerBands(closes);
      indicatorDataRef.current["bb_upper"]  = bb.upper.map(v => v ?? null);
      indicatorDataRef.current["bb_middle"] = bb.middle.map(v => v ?? null);
      indicatorDataRef.current["bb_lower"]  = bb.lower.map(v => v ?? null);
      series.push(
        { name: "BB+", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: indicatorDataRef.current["bb_upper"],  lineStyle: { color: "#3b82f6", width: 1, type: "dashed" }, showSymbol: false },
        { name: "BBm", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: indicatorDataRef.current["bb_middle"], lineStyle: { color: "#64748b", width: 1, type: "dashed" }, showSymbol: false },
        { name: "BB-", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: indicatorDataRef.current["bb_lower"],  lineStyle: { color: "#3b82f6", width: 1, type: "dashed" }, showSymbol: false },
      );
    }
    if (showRSI && !showMACD) {
      const rv = calcRSI(closes);
      indicatorDataRef.current["rsi"] = rv.map(v => v !== null ? +(v as number).toFixed(2) as any : null);
      series.push(
        { name: "RSI",  type: "line", xAxisIndex: 2, yAxisIndex: 2, data: indicatorDataRef.current["rsi"], lineStyle: { color: "#f59e0b", width: 1.5 }, showSymbol: false },
        { name: "OB",   type: "line", xAxisIndex: 2, yAxisIndex: 2, data: dates.map(() => 70), lineStyle: { color: "rgba(239,68,68,0.35)", width: 1, type: "dashed" }, showSymbol: false },
        { name: "OS",   type: "line", xAxisIndex: 2, yAxisIndex: 2, data: dates.map(() => 30), lineStyle: { color: "rgba(38,166,154,0.35)", width: 1, type: "dashed" }, showSymbol: false },
      );
    }
    if (showMACD) {
      const mac = calcMACD(closes);
      indicatorDataRef.current["macd"]   = mac.macd.map(v => v !== null ? +(v as number).toFixed(4) as any : null);
      indicatorDataRef.current["signal"] = mac.signal.map(v => v !== null ? +(v as number).toFixed(4) as any : null);
      series.push(
        { name: "MACD",   type: "line", xAxisIndex: 2, yAxisIndex: 2, data: indicatorDataRef.current["macd"],   lineStyle: { color: "#2962ff", width: 1.3 }, showSymbol: false },
        { name: "Signal", type: "line", xAxisIndex: 2, yAxisIndex: 2, data: indicatorDataRef.current["signal"], lineStyle: { color: "#ff6d00", width: 1.3 }, showSymbol: false },
        { name: "Hist",   type: "bar",  xAxisIndex: 2, yAxisIndex: 2, barMaxWidth: 5,
          data: mac.histogram.map(v => ({ value: v !== null ? +(v as number).toFixed(4) : null, itemStyle: { color: (v ?? 0) >= 0 ? "rgba(38,166,154,0.7)" : "rgba(239,83,80,0.7)" } })) },
      );
    }

    chart.setOption({
      backgroundColor: DARK, animation: false,
      tooltip: {
        trigger: "axis",
        axisPointer: {
          type: "cross",
          crossStyle: { color: "rgba(255,255,255,0.2)", width: 1 },
          lineStyle: { color: "rgba(255,255,255,0.2)", width: 1, type: "solid" },
          label: {
            backgroundColor: "#2a2e39",
            color: "#d1d4dc",
            fontSize: 10,
            formatter: ({ value }: any) => typeof value === "number" ? fmtPrice(value) : fmtCrosshairLabel(String(value)),
          },
        },
        backgroundColor: "#1e2130",
        borderColor: "#2a2e39",
        borderWidth: 1,
        padding: [6, 10],
        textStyle: { color: "#d1d4dc", fontSize: 11 },
        // Suppress default tooltip — we show OHLCV in the header instead
        formatter: () => "",
      },
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      dataZoom: [
        { type: "inside", xAxisIndex: hasSub ? [0, 1, 2] : [0, 1], start: 60, end: 100, zoomOnMouseWheel: true, moveOnMouseMove: true },
      ],
      grid: grids, xAxis: xAxes, yAxis: yAxes, series,
    }, true);

    requestAnimationFrame(() => paintSvg());
  }, [indicators, showRSI, showMACD, paintSvg]);

  // ── Fetch ──────────────────────────────────────────────────────────────────
  const fetchData = useCallback(async () => {
    if (!symbol) return;
    setLoading(true);
    try {
      const qs = periodCfg.start && periodCfg.end
        ? `start=${periodCfg.start}&end=${periodCfg.end}&interval=${periodCfg.i}`
        : `period=${periodCfg.p}&interval=${periodCfg.i}`;
      const res = await fetch(`/api/stocks/${encodeURIComponent(symbol)}/history?${qs}`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      candles.current = data.candles ?? [];
      // Compute last close + daily change
      const cs = candles.current;
      if (cs.length >= 2) {
        const last = cs[cs.length - 1];
        const prev = cs[cs.length - 2];
        setLastCandle({ c: last.close, pct: ((last.close - prev.close) / prev.close) * 100 });
      } else if (cs.length === 1) {
        setLastCandle({ c: cs[0].close, pct: 0 });
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
    renderChart();
  }, [symbol, periodCfg, renderChart]);

  // ── Init ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    const div = containerRef.current;
    if (!div) return;
    const chart = echarts.init(div, null, { renderer: "canvas" });
    chartRef.current = chart;

    chart.on("dataZoom", () => requestAnimationFrame(() => paintSvg()));
    chart.on("rendered",  () => requestAnimationFrame(() => paintSvg()));

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

    fetchData();
    return () => { ro.disconnect(); chart.dispose(); chartRef.current = null; };
  }, []);

  useEffect(() => { fetchData(); }, [symbol, periodCfg]);
  useEffect(() => { renderChart(); }, [indicators, showRSI, showMACD, chartType]);
  useEffect(() => { paintSvg(); }, [drawings]);

  // ── Drawing helpers ────────────────────────────────────────────────────────
  const getXY = (e: React.MouseEvent<HTMLDivElement>) => {
    const div = containerRef.current;
    if (!div) return null;
    const r = div.getBoundingClientRect();
    return { px: e.clientX - r.left, py: e.clientY - r.top };
  };

  const pixelToData = (px: number, py: number) => {
    const chart = chartRef.current;
    if (!chart) return null;
    const pt = chart.convertFromPixel({ gridIndex: 0 }, [px, py]);
    if (!pt) return null;
    const xIdx = Math.max(0, Math.min(Math.round(pt[0] as number), candles.current.length - 1));
    return { xIdx, y: pt[1] as number };
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (drawingTool === "none") return;
    e.preventDefault();
    onActivate();

    const pos = getXY(e);
    if (!pos) return;

    if (drawingTool === "eraser") {
      const chart = chartRef.current;
      if (!chart || !candles.current.length) return;
      const hitId = hitTestDrawings(pos.px, pos.py, drawings, chart, candles.current);
      if (hitId) {
        onDrawingErase(hitId);
      }
      return;
    }

    const data = pixelToData(pos.px, pos.py);
    if (!data) return;
    dragStart.current = { px: pos.px, py: pos.py, xIdx: data.xIdx, y: data.y };
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const pos = getXY(e);
    if (!pos) return;

    // Eraser hover: show circle cursor
    if (drawingTool === "eraser") {
      eraserPos.current = { x: pos.px, y: pos.py };
      paintSvg(null, eraserPos.current);
      return;
    }

    if (!dragStart.current) return;
    const data = pixelToData(pos.px, pos.py);
    if (!data) return;
    const chart = chartRef.current;
    if (!chart) return;

    let preview: SvgLine | SvgRect | null = null;
    const s = dragStart.current;
    const b = getGridBounds(chart, candles.current.length, candles.current);
    if (drawingTool === "hline")
      preview = { type: "line", x1: b.leftX, y1: s.py, x2: b.rightX, y2: s.py };
    else if (drawingTool === "vline")
      preview = { type: "line", x1: s.px, y1: b.topY, x2: s.px, y2: b.botY };
    else if (drawingTool === "trendline")
      preview = { type: "line", x1: s.px, y1: s.py, x2: pos.px, y2: pos.py };
    else if (drawingTool === "rectangle")
      preview = { type: "rect", x: Math.min(s.px, pos.px), y: Math.min(s.py, pos.py), w: Math.abs(pos.px - s.px), h: Math.abs(pos.py - s.py) };

    paintSvg(preview);
  };

  const handleMouseUp = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!dragStart.current) return;
    const pos = getXY(e);
    const data = pos ? pixelToData(pos.px, pos.py) : null;
    const s = dragStart.current;
    dragStart.current = null;

    if (!data || !pos) { paintSvg(); return; }

    let shape: Record<string, unknown> | null = null;
    if (drawingTool === "hline")        shape = { type: "hline", y: s.y };
    else if (drawingTool === "vline")   shape = { type: "vline", xIdx: s.xIdx };
    else if (drawingTool === "trendline") shape = { type: "trendline", x0Idx: s.xIdx, y0: s.y, x1Idx: data.xIdx, y1: data.y };
    else if (drawingTool === "rectangle") shape = { type: "rectangle", x0Idx: s.xIdx, y0: s.y, x1Idx: data.xIdx, y1: data.y };

    if (shape) onDrawingAdd({ id: uid(), shape });
    paintSvg();
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

  const hasAnyInd = indicators.size > 0 || showRSI || showMACD;

  return (
    <div
      className={`flex flex-col h-full rounded overflow-hidden border transition-colors ${isActive ? "border-indigo-500/60" : "border-transparent"}`}
      style={{ background: DARK }}
      onClick={() => { setCtxMenu(null); onActivate(); }}
    >
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex items-start gap-3 px-3 py-1.5 border-b border-white/[0.06] shrink-0">
        {/* Symbol + price + OHLCV */}
        <div className="flex flex-col justify-center min-w-0">
          {/* Row 1: symbol name + OHLCV on hover */}
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="font-bold text-white text-sm tracking-wide leading-tight">{symbol}</span>
            {symbolName && !hoverCandle && <span className="text-[11px] text-gray-500 truncate max-w-[130px] leading-tight">{symbolName}</span>}
            {hoverCandle && (
              <>
                <span className="text-[11px] text-gray-500">{hoverCandle.date}</span>
                <span className="text-[11px]"><span className="text-gray-500">O</span> <span className="text-white">{fmtPrice(hoverCandle.o)}</span></span>
                <span className="text-[11px]"><span className="text-[#26a69a]">H</span> <span className="text-white">{fmtPrice(hoverCandle.h)}</span></span>
                <span className="text-[11px]"><span className="text-[#ef5350]">L</span> <span className="text-white">{fmtPrice(hoverCandle.l)}</span></span>
                <span className="text-[11px]"><span className="text-gray-500">C</span> <span className="text-white">{fmtPrice(hoverCandle.c)}</span></span>
                <span className="text-[11px]"><span className="text-gray-500">V</span> <span className="text-white">{fmtVol(hoverCandle.v)}</span></span>
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
          {/* Row 3: active indicator pills (TradingView-style) */}
          {hasAnyInd && (
            <div className="flex items-center gap-2.5 mt-0.5 flex-wrap">
              {[...indicators].map(key => {
                const meta = IND_META[key];
                if (!meta) return null;
                if (key === "bb") {
                  const mid = indVal("bb_middle");
                  return (
                    <span key={key} className="flex items-center gap-1 text-[10px]">
                      <span style={{ color: meta.color }} className="font-medium">{meta.label}</span>
                      {mid !== null && <span className="text-gray-400">{fmtPrice(mid)}</span>}
                    </span>
                  );
                }
                const val = indVal(key);
                return (
                  <span key={key} className="flex items-center gap-1 text-[10px]">
                    <span style={{ color: meta.color }} className="font-medium">{meta.label}</span>
                    {val !== null && <span className="text-gray-400">{fmtPrice(val)}</span>}
                  </span>
                );
              })}
              {showRSI && !showMACD && (() => {
                const val = indVal("rsi");
                return (
                  <span className="flex items-center gap-1 text-[10px]">
                    <span style={{ color: "#f59e0b" }} className="font-medium">RSI</span>
                    {val !== null && <span className="text-gray-400">{(val as number).toFixed(2)}</span>}
                  </span>
                );
              })()}
              {showMACD && (() => {
                const m = indVal("macd"), s = indVal("signal");
                return (
                  <span className="flex items-center gap-1.5 text-[10px]">
                    <span style={{ color: "#2962ff" }} className="font-medium">MACD</span>
                    {m !== null && <span className="text-gray-400">{(m as number).toFixed(2)}</span>}
                    {s !== null && <span style={{ color: "#ff6d00" }}>{(s as number).toFixed(2)}</span>}
                  </span>
                );
              })()}
            </div>
          )}
        </div>
        {loading && <span className="ml-auto text-[10px] text-gray-600 animate-pulse self-center">Loading…</span>}
      </div>

      {/* ── Chart + SVG overlay ──────────────────────────────────────────── */}
      <div
        className="flex-1 relative min-h-0"
        onContextMenu={e => {
          e.preventDefault();
          const r = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
          setCtxMenu({ x: e.clientX - r.left, y: e.clientY - r.top });
        }}
      >
        <div ref={containerRef} className="absolute inset-0" />
        <svg ref={svgRef} className="absolute inset-0" style={{ pointerEvents: "none", zIndex: 10 }} />
        {drawingTool !== "none" && (
          <div
            className="absolute inset-0"
            style={{ zIndex: 20, cursor: drawingTool === "eraser" ? "none" : "crosshair" }}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={() => {
              eraserPos.current = null;
              if (dragStart.current) { dragStart.current = null; }
              paintSvg();
            }}
          />
        )}

        {/* ── Right-click context menu ──────────────────────────────── */}
        {ctxMenu && (
          <div
            className="absolute z-50 rounded-lg shadow-2xl border border-gray-700 py-1 min-w-[160px]"
            style={{ left: Math.min(ctxMenu.x, (containerRef.current?.offsetWidth ?? 300) - 170), top: ctxMenu.y, background: "#1e2130" }}
            onMouseDown={e => e.stopPropagation()}
          >
            <button
              className="w-full text-left px-4 py-1.5 text-xs text-gray-200 hover:bg-gray-700 hover:text-white"
              onClick={() => {
                chartRef.current?.dispatchAction({ type: "dataZoom", start: 60, end: 100 });
                setCtxMenu(null);
              }}
            >Reset zoom</button>
            <button
              className="w-full text-left px-4 py-1.5 text-xs text-gray-200 hover:bg-gray-700 hover:text-white"
              onClick={() => { onClearDrawings?.(); setCtxMenu(null); }}
            >Clear drawings</button>
            <div className="h-px bg-gray-700 my-1" />
            <button
              className="w-full text-left px-4 py-1.5 text-xs text-gray-200 hover:bg-gray-700 hover:text-white"
              onClick={() => { fetchData(); setCtxMenu(null); }}
            >Reload data</button>
          </div>
        )}
      </div>
    </div>
  );
}
