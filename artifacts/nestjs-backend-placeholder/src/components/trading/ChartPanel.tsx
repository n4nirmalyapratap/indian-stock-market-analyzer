import { useEffect, useRef, useState, useCallback } from "react";
import * as echarts from "echarts";
import { calcEMA, calcSMA, calcRSI, calcMACD, calcBollingerBands } from "@/lib/indicators";

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
  showRSI: boolean;
  showMACD: boolean;
  isActive: boolean;
  drawings: Drawing[];
  onDrawingAdd: (d: Drawing) => void;
  onDrawingErase: (id: string) => void;
  onClearDrawings?: () => void;
  onActivate: () => void;
  theme: "dark" | "light";
}

const DRAW_CLR = "#6366f1";

function getThemeColors(theme: "dark" | "light") {
  const d = theme === "dark";
  return {
    bg:      d ? "#131722"                : "#ffffff",
    grid:    d ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.07)",
    text:    d ? "#787b86"                : "#9ca3af",
    cross:   d ? "rgba(255,255,255,0.2)"  : "rgba(0,0,0,0.25)",
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

interface SvgLine    { type: "line";    x1: number; y1: number; x2: number; y2: number; dash?: boolean; color?: string }
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
function extendRay(px: number, py: number, nx: number, ny: number, x0: number, y0: number, x1: number, y1: number): [number, number] {
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
    const [, py] = chart.convertToPixel({ gridIndex: 0 }, [0, s.y]);
    return [{ type: "line", x1: b.leftX, y1: py, x2: b.rightX, y2: py }];
  }
  if (s.type === "hray") {
    const [startX, py] = chart.convertToPixel({ gridIndex: 0 }, [s.xIdx, s.y]);
    return [{ type: "line", x1: startX, y1: py, x2: b.rightX, y2: py }];
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
    const [ex, ey] = extendRay(px0, py0, dx / len, dy / len, 0, 0, W, H);
    return [{ type: "line", x1: px0, y1: py0, x2: ex, y2: ey }];
  }
  if (s.type === "extendedline") {
    const [px0, py0] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [px1, py1] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    const dx = px1 - px0, dy = py1 - py0;
    const len = Math.hypot(dx, dy);
    if (len < 1) return [{ type: "line", x1: px0, y1: py0, x2: px1, y2: py1 }];
    const nx = dx / len, ny = dy / len;
    const [ex1, ey1] = extendRay(px0, py0,  nx,  ny, 0, 0, W, H);
    const [ex2, ey2] = extendRay(px0, py0, -nx, -ny, 0, 0, W, H);
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
    const dx = px1 - px0, dy = py1 - py0;
    const len = Math.hypot(dx, dy);
    if (len < 1) return null;
    const nx = dx / len, ny = dy / len;
    const off = py2 - py0;
    const [e1x, e1y] = extendRay(px0, py0,  nx,  ny, 0, 0, W, H);
    const [e2x, e2y] = extendRay(px0, py0, -nx, -ny, 0, 0, W, H);
    const [e3x, e3y] = extendRay(px0, py0 + off,  nx,  ny, 0, 0, W, H);
    const [e4x, e4y] = extendRay(px0, py0 + off, -nx, -ny, 0, 0, W, H);
    const [e5x, e5y] = extendRay(px0, py0 + off / 2,  nx,  ny, 0, 0, W, H);
    const [e6x, e6y] = extendRay(px0, py0 + off / 2, -nx, -ny, 0, 0, W, H);
    return [
      { type: "line", x1: e2x, y1: e2y, x2: e1x, y2: e1y },
      { type: "line", x1: e4x, y1: e4y, x2: e3x, y2: e3y },
      { type: "line", x1: e6x, y1: e6y, x2: e5x, y2: e5y, dash: true, color: DRAW_CLR + "88" },
    ];
  }
  if (s.type === "pitchfork") {
    const [px0, py0] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [px1, py1] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    const dx = px1 - px0, dy = py1 - py0;
    const len = Math.hypot(dx, dy);
    if (len < 1) return null;
    const nx = dx / len, ny = dy / len;
    const spread = len * 0.3;
    const perpX = -ny, perpY = nx;
    const [me1x, me1y] = extendRay(px0, py0,  nx,  ny, 0, 0, W, H);
    const [me2x, me2y] = extendRay(px0, py0, -nx, -ny, 0, 0, W, H);
    const f1x = px1 + perpX * spread, f1y = py1 + perpY * spread;
    const f2x = px1 - perpX * spread, f2y = py1 - perpY * spread;
    const [f1ex, f1ey] = extendRay(f1x, f1y, nx, ny, 0, 0, W, H);
    const [f2ex, f2ey] = extendRay(f2x, f2y, nx, ny, 0, 0, W, H);
    return [
      { type: "line", x1: me2x, y1: me2y, x2: me1x, y2: me1y },
      { type: "line", x1: f1x, y1: f1y, x2: f1ex, y2: f1ey },
      { type: "line", x1: f2x, y1: f2y, x2: f2ex, y2: f2ey },
      { type: "line", x1: f1x, y1: f1y, x2: f2x, y2: f2y, dash: true, color: DRAW_CLR + "88" },
    ];
  }

  // ── Fibonacci ──────────────────────────────────────────────────────────────
  if (s.type === "fibretracement" || s.type === "fibextension") {
    const [px0, py0] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [px1, py1] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
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
      els.push({ type: "line", x1: b.leftX, y1: py, x2: b.rightX, y2: py, color: col });
      els.push({ type: "text", x: b.rightX + 4, y: py - 3, text: `${(ratio * 100).toFixed(1)}%  ₹${fmtPrice(s.y0 + (s.y1 - s.y0) * ratio)}`, anchor: "start", size: 9, color: col });
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
    const dx = px1 - px0, dy = py1 - py0;
    const ratios = [0.236, 0.382, 0.5, 0.618, 0.786];
    const colors = ["#f97316","#eab308","#22c55e","#3b82f6","#8b5cf6"];
    const els: SvgEl[] = [];
    for (let i = 0; i < ratios.length; i++) {
      const fanDy = dy * ratios[i];
      const fanLen = Math.hypot(dx, fanDy);
      if (fanLen < 1) continue;
      const [ex, ey] = extendRay(px0, py0, dx / fanLen, fanDy / fanLen, 0, 0, W, H);
      els.push({ type: "line", x1: px0, y1: py0, x2: ex, y2: ey, dash: true, color: colors[i] });
      if (ey >= 0 && ey <= H) {
        els.push({ type: "text", x: ex - 28, y: ey, text: `${(ratios[i] * 100).toFixed(0)}%`, size: 9, color: colors[i] });
      }
    }
    return els.length ? els : null;
  }

  // ── Gann ───────────────────────────────────────────────────────────────────
  if (s.type === "gannfan") {
    const [px0, py0] = chart.convertToPixel({ gridIndex: 0 }, [s.x0Idx, s.y0]);
    const [px1, py1] = chart.convertToPixel({ gridIndex: 0 }, [s.x1Idx, s.y1]);
    const dx = px1 - px0, dy = py1 - py0;
    const RATIOS = [
      { r: 1/4, label: "1×4" }, { r: 1/3, label: "1×3" }, { r: 1/2, label: "1×2" },
      { r: 1,   label: "1×1" },
      { r: 2,   label: "2×1" }, { r: 3,   label: "3×1" }, { r: 4,   label: "4×1" },
    ];
    const els: SvgEl[] = [];
    for (const { r, label } of RATIOS) {
      const fanDy = dy * r;
      const fanLen = Math.hypot(dx, fanDy);
      if (fanLen < 1) continue;
      const [ex, ey] = extendRay(px0, py0, dx / fanLen, fanDy / fanLen, 0, 0, W, H);
      const isMain = r === 1;
      els.push({ type: "line", x1: px0, y1: py0, x2: ex, y2: ey, dash: !isMain, color: isMain ? DRAW_CLR : DRAW_CLR + "99" });
      if (ey >= 0 && ey <= H && ex >= 0 && ex <= W) {
        els.push({ type: "text", x: ex - 20, y: ey - 3, text: label, anchor: "end", size: 8 });
      }
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

// ── SVG renderer ──────────────────────────────────────────────────────────────

function renderSvg(
  svgEl: SVGSVGElement | null,
  pixels: SvgPixels[],
  preview: SvgEl | SvgEl[] | null,
  eraserPixel: { x: number; y: number } | null,
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
      line.setAttribute("stroke-width", "1.5");
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
}

// ── Component ──────────────────────────────────────────────────────────────────

interface HoverCandle {
  date: string; o: number; h: number; l: number; c: number; v: number;
}

export default function ChartPanel({
  symbol, symbolName, periodCfg, drawingTool, chartType, indicators,
  showRSI, showMACD, isActive, drawings, onDrawingAdd, onDrawingErase, onClearDrawings, onActivate,
  theme,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef       = useRef<SVGSVGElement>(null);
  const chartRef     = useRef<echarts.ECharts | null>(null);
  const candles      = useRef<Candle[]>([]);
  const dragStart    = useRef<{ px: number; py: number; xIdx: number; y: number } | null>(null);
  const eraserPos    = useRef<{ x: number; y: number } | null>(null);
  const paintSvgRef  = useRef<((preview?: SvgEl | SvgEl[] | null, eraser?: { x: number; y: number } | null) => void) | null>(null);
  const indicatorDataRef = useRef<Record<string, (number | null)[]>>({});
  const drawingToolRef = useRef<DrawingTool>(drawingTool);
  const intervalRef    = useRef<string>(periodCfg.i);
  const chartTypeRef   = useRef<ChartType>(chartType);
  const themeRef       = useRef<"dark" | "light">(theme);
  useEffect(() => { drawingToolRef.current = drawingTool; }, [drawingTool]);
  useEffect(() => { intervalRef.current = periodCfg.i; }, [periodCfg.i]);
  useEffect(() => { themeRef.current = theme; }, [theme]);
  useEffect(() => { chartTypeRef.current = chartType; }, [chartType]);

  const [loading, setLoading]           = useState(true);
  const [hoverCandle, setHoverCandle]   = useState<HoverCandle | null>(null);
  const [hoverIdx, setHoverIdx]         = useState(-1);
  const [lastCandle, setLastCandle]     = useState<{ c: number; pct: number } | null>(null);
  const [ctxMenu, setCtxMenu]           = useState<{ x: number; y: number } | null>(null);

  // ── Repaint SVG ────────────────────────────────────────────────────────────
  const paintSvg = useCallback((
    preview: SvgEl | SvgEl[] | null = null,
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
        const els = shapeToPixels(d.shape, chart, candles.current);
        return els ? { id: d.id, els } : null;
      })
      .filter(Boolean) as SvgPixels[];

    renderSvg(svg, pixels, preview, eraser);
  }, [drawings]);

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
    const xBase = { axisLine: { lineStyle: { color: T.grid } }, axisTick: { show: false } };
    const xAxes: object[] = [
      { ...xBase, gridIndex: 0, data: dates, axisLabel: { show: false }, splitLine: { lineStyle: { color: T.grid } }, axisPointer: { label: { show: false } } },
      { ...xBase, gridIndex: 1, data: dates, axisLabel: hasSub ? { show: false } : { color: T.text, fontSize: 9, margin: 6, formatter: (v: string) => fmtXLabel(v, showTime) }, splitLine: { show: false }, axisPointer: hasSub ? { label: { show: false } } : {} },
    ];
    if (hasSub) {
      xAxes.push({ ...xBase, gridIndex: 2, data: dates, axisLabel: { color: T.text, fontSize: 9, margin: 6, formatter: (v: string) => fmtXLabel(v, showTime) }, splitLine: { lineStyle: { color: T.grid } } });
    }

    // y-axis — all positioned on the RIGHT side
    const yBase = { axisLine: { show: false }, axisTick: { show: false }, position: "right" };
    const yAxes: object[] = [
      {
        ...yBase, gridIndex: 0, scale: true,
        axisLabel: { color: T.text, fontSize: 10, margin: 6 },
        splitLine: { lineStyle: { color: T.grid } },
      },
      {
        ...yBase, gridIndex: 1, scale: true,
        axisLabel: { show: true, color: T.text, fontSize: 9, margin: 6, formatter: (v: number) => fmtVol(v) },
        splitLine: { show: false },
        splitNumber: 2,
      },
    ];
    if (hasSub) {
      yAxes.push({
        ...yBase, gridIndex: 2, scale: true,
        axisLabel: { color: T.text, fontSize: 9, margin: 6 },
        splitLine: { lineStyle: { color: T.grid } },
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
      backgroundColor: T.bg, animation: false,
      tooltip: {
        trigger: "axis",
        axisPointer: {
          type: "cross",
          crossStyle: { color: T.cross, width: 1 },
          lineStyle: { color: T.cross, width: 1, type: "solid" },
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

    chart.on("dataZoom", () => { requestAnimationFrame(() => paintSvgRef.current?.()); });
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

    fetchData();
    return () => { ro.disconnect(); chart.dispose(); chartRef.current = null; };
  }, []);

  useEffect(() => { fetchData(); }, [symbol, periodCfg]);
  useEffect(() => { renderChart(); }, [indicators, showRSI, showMACD, chartType]);
  useEffect(() => { if (candles.current.length) renderChart(); }, [theme]);
  useEffect(() => { paintSvg(); }, [drawings]);
  // Keep paintSvgRef pointing at the latest closure so echarts event handlers
  // (registered once at init) always repaint with up-to-date drawings/state.
  useEffect(() => { paintSvgRef.current = paintSvg; }, [paintSvg]);

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
      if (hitId) onDrawingErase(hitId);
      return;
    }

    const data = pixelToData(pos.px, pos.py);
    if (!data) return;

    // Click-only tools — create shape immediately, no drag needed
    if (drawingTool === "arrowmarker")
      { onDrawingAdd({ id: uid(), shape: { type: "arrowmarker", xIdx: data.xIdx, y: data.y } }); return; }
    if (drawingTool === "arrowmarkup")
      { onDrawingAdd({ id: uid(), shape: { type: "arrowmarkup", xIdx: data.xIdx, y: data.y } }); return; }
    if (drawingTool === "arrowmarkdown")
      { onDrawingAdd({ id: uid(), shape: { type: "arrowmarkdown", xIdx: data.xIdx, y: data.y } }); return; }
    if (drawingTool === "flag")
      { onDrawingAdd({ id: uid(), shape: { type: "flag", xIdx: data.xIdx, y: data.y } }); return; }
    if (drawingTool === "note") {
      const text = window.prompt("Enter note text:") ?? "";
      if (text.trim()) onDrawingAdd({ id: uid(), shape: { type: "note", xIdx: data.xIdx, y: data.y, text: text.trim() } });
      return;
    }

    dragStart.current = { px: pos.px, py: pos.py, xIdx: data.xIdx, y: data.y };
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const pos = getXY(e);
    if (!pos) return;

    if (drawingTool === "eraser") {
      eraserPos.current = { x: pos.px, y: pos.py };
      paintSvg(null, eraserPos.current);
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
    else if (drawingTool === "parallelch") {
      const dx = pos.px - s.px, dy = pos.py - s.py;
      const len = Math.hypot(dx, dy);
      if (len > 1) {
        const nx = dx / len, ny = dy / len;
        const off = len * 0.22;
        const perpX = -ny, perpY = nx;
        const [e1x, e1y] = extendRay(s.px, s.py,  nx,  ny, 0, 0, W, H);
        const [e2x, e2y] = extendRay(s.px, s.py, -nx, -ny, 0, 0, W, H);
        const [e3x, e3y] = extendRay(s.px + perpX * off, s.py + perpY * off,  nx,  ny, 0, 0, W, H);
        const [e4x, e4y] = extendRay(s.px + perpX * off, s.py + perpY * off, -nx, -ny, 0, 0, W, H);
        preview = [
          { type: "line", x1: e2x, y1: e2y, x2: e1x, y2: e1y },
          { type: "line", x1: e4x, y1: e4y, x2: e3x, y2: e3y, dash: true },
        ];
      }
    }
    else if (drawingTool === "pitchfork") {
      const dx = pos.px - s.px, dy = pos.py - s.py;
      const len = Math.hypot(dx, dy);
      if (len > 1) {
        const nx = dx / len, ny = dy / len;
        const spread = len * 0.3;
        const perpX = -ny, perpY = nx;
        const [me1x, me1y] = extendRay(s.px, s.py,  nx,  ny, 0, 0, W, H);
        const [me2x, me2y] = extendRay(s.px, s.py, -nx, -ny, 0, 0, W, H);
        const [f1ex, f1ey] = extendRay(pos.px + perpX * spread, pos.py + perpY * spread, nx, ny, 0, 0, W, H);
        const [f2ex, f2ey] = extendRay(pos.px - perpX * spread, pos.py - perpY * spread, nx, ny, 0, 0, W, H);
        preview = [
          { type: "line", x1: me2x, y1: me2y, x2: me1x, y2: me1y },
          { type: "line", x1: pos.px + perpX * spread, y1: pos.py + perpY * spread, x2: f1ex, y2: f1ey },
          { type: "line", x1: pos.px - perpX * spread, y1: pos.py - perpY * spread, x2: f2ex, y2: f2ey },
        ];
      }
    }
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
    if (!dragStart.current) return;
    const pos = getXY(e);
    const s = dragStart.current;
    dragStart.current = null;

    // For tools that only need mousedown data (hline, vline, crossline, hray),
    // save the shape immediately — don't require mouseup to be inside the grid.
    let shape: Record<string, unknown> | null = null;
    if (drawingTool === "hline")
      shape = { type: "hline", y: s.y };
    else if (drawingTool === "hray")
      shape = { type: "hray", xIdx: s.xIdx, y: s.y };
    else if (drawingTool === "vline")
      shape = { type: "vline", xIdx: s.xIdx };
    else if (drawingTool === "crossline")
      shape = { type: "crossline", xIdx: s.xIdx, y: s.y };

    if (shape) { onDrawingAdd({ id: uid(), shape }); paintSvg(); return; }

    // Tools that need both endpoints — require valid mouseup position
    const data = pos ? pixelToData(pos.px, pos.py) : null;
    if (!data || !pos) { paintSvg(); return; }

    const two = { x0Idx: s.xIdx, y0: s.y, x1Idx: data.xIdx, y1: data.y };
    if      (drawingTool === "trendline")     shape = { type: "trendline",     ...two };
    else if (drawingTool === "ray")           shape = { type: "ray",           ...two };
    else if (drawingTool === "extendedline")  shape = { type: "extendedline",  ...two };
    else if (drawingTool === "rectangle")     shape = { type: "rectangle",     ...two };
    else if (drawingTool === "circle")        shape = { type: "circle",        ...two };
    else if (drawingTool === "ellipse")       shape = { type: "ellipse",       ...two };
    else if (drawingTool === "parallelch")    shape = { type: "parallelch",    ...two, y2: s.y + (data.y - s.y) * 0.35 };
    else if (drawingTool === "pitchfork")     shape = { type: "pitchfork",     ...two };
    else if (drawingTool === "fibretracement") shape = { type: "fibretracement", ...two };
    else if (drawingTool === "fibextension")  shape = { type: "fibextension",  ...two };
    else if (drawingTool === "fibtimezone")   shape = { type: "fibtimezone",   ...two };
    else if (drawingTool === "fibfan")        shape = { type: "fibfan",        ...two };
    else if (drawingTool === "gannfan")       shape = { type: "gannfan",       ...two };
    else if (drawingTool === "gannbox")       shape = { type: "gannbox",       ...two };
    else if (drawingTool === "longposition")  shape = { type: "longposition",  ...two };
    else if (drawingTool === "shortposition") shape = { type: "shortposition", ...two };
    else if (drawingTool === "cycliclines")   shape = { type: "cycliclines",   ...two };
    else if (drawingTool === "measure")       shape = { type: "measure",       ...two };

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
          onActivate();
          const r = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
          setCtxMenu({ x: e.clientX - r.left, y: e.clientY - r.top });
        }}
      >
        <div ref={containerRef} className="absolute inset-0" />
        {loading && (
          <div className="absolute inset-0 z-30 pointer-events-none transition-opacity" style={{ background: TC.dimBg }} />
        )}
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
