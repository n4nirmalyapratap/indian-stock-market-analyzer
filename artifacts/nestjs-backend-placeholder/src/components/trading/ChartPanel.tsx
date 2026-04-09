import { useEffect, useRef, useState, useCallback } from "react";
import * as echarts from "echarts";
import { calcEMA, calcSMA, calcRSI, calcMACD, calcBollingerBands } from "@/lib/indicators";

export type DrawingTool = "none" | "trendline" | "hline" | "vline" | "rectangle" | "eraser";

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
  periodCfg: { p: string; i: string };
  drawingTool: DrawingTool;
  indicators: Set<string>;
  showRSI: boolean;
  showMACD: boolean;
  isActive: boolean;
  drawings: Drawing[];
  onDrawingAdd: (d: Drawing) => void;
  onDrawingErase: (id: string) => void;
  onActivate: () => void;
}

const DARK      = "#131722";
const GRID_CLR  = "rgba(255,255,255,0.06)";
const TEXT_CLR  = "#c4cfd8";
const DRAW_CLR  = "#6366f1";

function uid() { return Math.random().toString(36).slice(2, 9); }

function toDateStr(ts: number) {
  const d = new Date(ts * 1000);
  const date = d.toISOString().slice(0, 10);
  const hh = d.getUTCHours();
  const mm = d.getUTCMinutes();
  return hh === 0 && mm === 0 ? date : `${date} ${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

// ── SVG overlay helpers ────────────────────────────────────────────────────────

interface SvgLine   { type: "line";   x1: number; y1: number; x2: number; y2: number }
interface SvgRect   { type: "rect";   x: number;  y: number;  w: number;  h: number  }
interface SvgPixels { id: string; el: SvgLine | SvgRect }

function getGridBounds(chart: echarts.ECharts, n: number, candles: Candle[]) {
  // Derive actual pixel bounds from the chart's own coordinate system
  const [leftX] = chart.convertToPixel({ gridIndex: 0 }, [0, 0]);
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

function renderSvg(
  svgEl: SVGSVGElement | null,
  pixels: SvgPixels[],
  preview: SvgLine | SvgRect | null,
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

  for (const p of pixels) add(p.el, p.el.type === "line");
  if (preview) add(preview, preview.type === "line", 0.7);
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function ChartPanel({
  symbol, periodCfg, drawingTool, indicators,
  showRSI, showMACD, isActive, drawings, onDrawingAdd, onDrawingErase, onActivate,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef       = useRef<SVGSVGElement>(null);
  const chartRef     = useRef<echarts.ECharts | null>(null);
  const candles      = useRef<Candle[]>([]);
  const dragStart       = useRef<{ px: number; py: number; xIdx: number; y: number } | null>(null);
  const drawingToolRef  = useRef<DrawingTool>(drawingTool);
  useEffect(() => { drawingToolRef.current = drawingTool; }, [drawingTool]);

  const [loading, setLoading] = useState(true);

  // ── Repaint SVG (called after chart render or drawings change) ─────────────
  const paintSvg = useCallback((preview: SvgLine | SvgRect | null = null) => {
    const chart = chartRef.current;
    const svg   = svgRef.current;
    const div   = containerRef.current;
    if (!chart || !svg || !div || !candles.current.length) return;
    svg.setAttribute("width", String(div.offsetWidth));
    svg.setAttribute("height", String(div.offsetHeight));

    const pixels: SvgPixels[] = drawings
      .map(d => {
        const el = shapeToPixels(d.shape, chart, candles.current);
        return el ? { id: d.id, el } : null;
      })
      .filter(Boolean) as SvgPixels[];

    renderSvg(svg, pixels, preview);
  }, [drawings]);

  // ── Render ECharts (chart data only, NO graphic component) ────────────────
  const renderChart = useCallback(() => {
    const chart = chartRef.current;
    if (!chart || !candles.current.length) return;

    const cs     = candles.current;
    const dates  = cs.map(c => toDateStr(c.time));
    const closes = cs.map(c => c.close);
    const ohlc   = cs.map(c => [c.open, c.close, c.low, c.high]);

    const hasSub = showRSI || showMACD;
    const grids: object[] = [
      { top: "6%", left: 50, right: 8, height: hasSub ? "55%" : "75%" },
      { top: hasSub ? "57%" : "77%", left: 50, right: 8, height: "8%" },
    ];
    if (hasSub) grids.push({ top: "70%", left: 50, right: 8, height: "18%" });

    const xBase = { axisLine: { lineStyle: { color: GRID_CLR } }, axisTick: { show: false } };
    const xAxes: object[] = [
      { ...xBase, gridIndex: 0, data: dates, axisLabel: { color: TEXT_CLR, fontSize: 10 }, splitLine: { lineStyle: { color: GRID_CLR } } },
      { ...xBase, gridIndex: 1, data: dates, axisLabel: { show: false }, splitLine: { show: false } },
    ];
    if (hasSub) xAxes.push({ ...xBase, gridIndex: 2, data: dates, axisLabel: { color: TEXT_CLR, fontSize: 9 }, splitLine: { lineStyle: { color: GRID_CLR } } });

    const yBase = { axisLine: { lineStyle: { color: GRID_CLR } } };
    const yAxes: object[] = [
      { ...yBase, gridIndex: 0, scale: true, axisLabel: { color: TEXT_CLR, fontSize: 10 }, splitLine: { lineStyle: { color: GRID_CLR } } },
      { ...yBase, gridIndex: 1, scale: true, axisLabel: { show: false }, splitLine: { show: false } },
    ];
    if (hasSub) yAxes.push({ ...yBase, gridIndex: 2, scale: true, axisLabel: { color: TEXT_CLR, fontSize: 9 }, splitLine: { lineStyle: { color: GRID_CLR } } });

    const series: object[] = [
      {
        name: "Price", type: "candlestick", xAxisIndex: 0, yAxisIndex: 0, data: ohlc,
        itemStyle: { color: "#22c55e", color0: "#ef4444", borderColor: "#22c55e", borderColor0: "#ef4444", borderWidth: 1 },
      },
      {
        name: "Volume", type: "bar", xAxisIndex: 1, yAxisIndex: 1, barMaxWidth: 12,
        data: cs.map(c => ({ value: c.volume, itemStyle: { color: c.close >= c.open ? "rgba(34,197,94,0.45)" : "rgba(239,68,68,0.45)" } })),
      },
    ];

    const MA = [
      { key: "ema9",   label: "EMA 9",   color: "#f59e0b", fn: () => calcEMA(closes, 9)   },
      { key: "ema21",  label: "EMA 21",  color: "#6366f1", fn: () => calcEMA(closes, 21)  },
      { key: "ema50",  label: "EMA 50",  color: "#10b981", fn: () => calcEMA(closes, 50)  },
      { key: "ema200", label: "EMA 200", color: "#ef4444", fn: () => calcEMA(closes, 200) },
      { key: "sma50",  label: "SMA 50",  color: "#a78bfa", fn: () => calcSMA(closes, 50)  },
    ];
    for (const m of MA) {
      if (!indicators.has(m.key)) continue;
      series.push({ name: m.label, type: "line", xAxisIndex: 0, yAxisIndex: 0, data: m.fn().map(v => v ?? null), lineStyle: { color: m.color, width: 1.5 }, showSymbol: false, connectNulls: false });
    }
    if (indicators.has("bb")) {
      const bb = calcBollingerBands(closes);
      series.push(
        { name: "BB+", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: bb.upper.map(v => v ?? null), lineStyle: { color: "#3b82f6", width: 1, type: "dashed" }, showSymbol: false, connectNulls: false },
        { name: "BBm", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: bb.middle.map(v => v ?? null), lineStyle: { color: "#64748b", width: 1, type: "dashed" }, showSymbol: false, connectNulls: false },
        { name: "BB-", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: bb.lower.map(v => v ?? null), lineStyle: { color: "#3b82f6", width: 1, type: "dashed" }, showSymbol: false, connectNulls: false },
      );
    }
    if (showRSI && !showMACD) {
      const rv = calcRSI(closes);
      series.push(
        { name: "RSI", type: "line", xAxisIndex: 2, yAxisIndex: 2, data: rv.map(v => v !== null ? +(v as number).toFixed(2) : null), lineStyle: { color: "#f59e0b", width: 1.5 }, showSymbol: false, connectNulls: false },
        { name: "OB",  type: "line", xAxisIndex: 2, yAxisIndex: 2, data: dates.map(() => 70), lineStyle: { color: "rgba(239,68,68,0.4)", width: 1, type: "dashed" }, showSymbol: false },
        { name: "OS",  type: "line", xAxisIndex: 2, yAxisIndex: 2, data: dates.map(() => 30), lineStyle: { color: "rgba(34,197,94,0.4)", width: 1, type: "dashed" }, showSymbol: false },
      );
    }
    if (showMACD) {
      const mac = calcMACD(closes);
      series.push(
        { name: "MACD",   type: "line", xAxisIndex: 2, yAxisIndex: 2, data: mac.macd.map(v => v !== null ? +(v as number).toFixed(4) : null), lineStyle: { color: "#3b82f6", width: 1.2 }, showSymbol: false, connectNulls: false },
        { name: "Signal", type: "line", xAxisIndex: 2, yAxisIndex: 2, data: mac.signal.map(v => v !== null ? +(v as number).toFixed(4) : null), lineStyle: { color: "#f97316", width: 1.2 }, showSymbol: false, connectNulls: false },
        { name: "Hist",   type: "bar",  xAxisIndex: 2, yAxisIndex: 2, barMaxWidth: 6, data: mac.histogram.map(v => ({ value: v !== null ? +(v as number).toFixed(4) : null, itemStyle: { color: (v ?? 0) >= 0 ? "rgba(34,197,94,0.7)" : "rgba(239,68,68,0.7)" } })) },
      );
    }

    chart.setOption({
      backgroundColor: DARK, animation: false,
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross", crossStyle: { color: "rgba(255,255,255,0.25)" } },
        backgroundColor: "#1e2131", borderColor: "#374151",
        textStyle: { color: TEXT_CLR, fontSize: 10 },
        formatter: (params: any) => {
          const c = Array.isArray(params) ? params.find((p: any) => p.seriesName === "Price") : null;
          if (!c || !c.data) return "";
          const [o, cl, l, h] = c.data as number[];
          const p = (((cl - o) / o) * 100).toFixed(2);
          const col = cl >= o ? "#22c55e" : "#ef4444";
          return `<div style="font-size:10px;line-height:1.6"><b style="color:#fff">${c.name}</b><br/>O<b>${o.toFixed(2)}</b> H<b style="color:#22c55e">${h.toFixed(2)}</b> L<b style="color:#ef4444">${l.toFixed(2)}</b> C<b>${cl.toFixed(2)}</b> <span style="color:${col}">${Number(p)>=0?"+":""}${p}%</span></div>`;
        },
      },
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      dataZoom: [{ type: "inside", xAxisIndex: hasSub ? [0, 1, 2] : [0, 1], start: 0, end: 100 }],
      grid: grids, xAxis: xAxes, yAxis: yAxes, series,
    }, true);

    // repaint SVG after chart re-renders
    requestAnimationFrame(() => paintSvg());
  }, [indicators, showRSI, showMACD, paintSvg]);

  // ── Fetch ──────────────────────────────────────────────────────────────────
  const fetchData = useCallback(async () => {
    if (!symbol) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/stocks/${encodeURIComponent(symbol)}/history?period=${periodCfg.p}&interval=${periodCfg.i}`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      candles.current = data.candles ?? [];
    } catch {} finally { setLoading(false); }
    renderChart();
  }, [symbol, periodCfg, renderChart]);

  // ── Init ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    const div = containerRef.current;
    if (!div) return;
    const chart = echarts.init(div, null, { renderer: "canvas" });
    chartRef.current = chart;

    // Repaint SVG after any zoom/pan (only resize chart, never re-render full setOption)
    chart.on("dataZoom", () => requestAnimationFrame(() => paintSvg()));
    chart.on("rendered", () => requestAnimationFrame(() => paintSvg()));

    // ResizeObserver: ONLY resize chart, do NOT call renderChart (avoids layout loop)
    const ro = new ResizeObserver(() => { chart.resize(); requestAnimationFrame(() => paintSvg()); });
    ro.observe(div);

    fetchData();
    return () => { ro.disconnect(); chart.dispose(); chartRef.current = null; };
  }, []);

  useEffect(() => { fetchData(); }, [symbol, periodCfg]);
  useEffect(() => { renderChart(); }, [indicators, showRSI, showMACD]);
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
    const dates = candles.current.map(c => toDateStr(c.time));
    const xIdx = Math.max(0, Math.min(Math.round(pt[0] as number), dates.length - 1));
    return { xIdx, y: pt[1] as number };
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (drawingTool === "none") return;
    e.preventDefault();
    onActivate();
    if (drawingTool === "eraser") {
      if (drawings.length > 0) onDrawingErase(drawings[drawings.length - 1].id);
      return;
    }
    const pos = getXY(e);
    if (!pos) return;
    const data = pixelToData(pos.px, pos.py);
    if (!data) return;
    dragStart.current = { px: pos.px, py: pos.py, xIdx: data.xIdx, y: data.y };
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!dragStart.current) return;
    const pos = getXY(e);
    if (!pos) return;
    const data = pixelToData(pos.px, pos.py);
    if (!data) return;
    const chart = chartRef.current;
    const div = containerRef.current;
    if (!chart || !div) return;

    // Build preview pixel shape directly — NO ECharts re-render
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
    if (drawingTool === "hline")     shape = { type: "hline", y: s.y };
    else if (drawingTool === "vline") shape = { type: "vline", xIdx: s.xIdx };
    else if (drawingTool === "trendline") shape = { type: "trendline", x0Idx: s.xIdx, y0: s.y, x1Idx: data.xIdx, y1: data.y };
    else if (drawingTool === "rectangle") shape = { type: "rectangle", x0Idx: s.xIdx, y0: s.y, x1Idx: data.xIdx, y1: data.y };

    if (shape) onDrawingAdd({ id: uid(), shape });
    paintSvg();
  };

  return (
    <div
      className={`flex flex-col h-full rounded border transition-colors ${isActive ? "border-indigo-500" : "border-gray-800"}`}
      style={{ background: DARK }}
      onClick={onActivate}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-1 border-b border-gray-800 min-h-[32px] shrink-0">
        <span className="font-bold text-white text-sm tracking-wide">{symbol}</span>
        {loading && <span className="ml-auto text-[11px] text-gray-600 animate-pulse">Loading…</span>}
      </div>

      {/* Chart + SVG overlay + drawing capture overlay */}
      <div className="flex-1 relative min-h-0">
        {/* ECharts canvas */}
        <div ref={containerRef} className="absolute inset-0" />
        {/* SVG drawing layer — always present, pointer-events: none so ECharts works normally */}
        <svg
          ref={svgRef}
          className="absolute inset-0"
          style={{ pointerEvents: "none", zIndex: 10 }}
        />
        {/* Mouse capture layer — only active when a drawing tool is selected */}
        {drawingTool !== "none" && (
          <div
            className="absolute inset-0"
            style={{ zIndex: 20, cursor: drawingTool === "eraser" ? "cell" : "crosshair" }}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={() => { if (dragStart.current) { dragStart.current = null; paintSvg(); } }}
          />
        )}
      </div>
    </div>
  );
}
