import { useEffect, useRef, useState, useCallback, useId } from "react";
import {
  createChart, CandlestickSeries, LineSeries, HistogramSeries,
  ColorType, CrosshairMode, LineStyle,
  type IChartApi, type ISeriesApi, type Time,
} from "lightweight-charts";
import { calcEMA, calcSMA, calcRSI, calcMACD, calcBollingerBands } from "@/lib/indicators";

export type DrawingTool = "none" | "trendline" | "hline" | "vline" | "rectangle" | "eraser";

export interface Drawing {
  id: string;
  type: DrawingTool;
  startTime: number;
  startPrice: number;
  endTime: number;
  endPrice: number;
  color: string;
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

const COLORS = {
  bg: "#131722",
  gridLine: "#1e2433",
  text: "#c4cfd8",
  ema9: "#f59e0b",
  ema21: "#6366f1",
  ema50: "#10b981",
  ema200: "#ef4444",
  sma50: "#a78bfa",
  bbUpper: "#3b82f6",
  bbLower: "#3b82f6",
  bbMiddle: "#64748b",
  rsiLine: "#f59e0b",
  macdLine: "#6366f1",
  macdSignal: "#f59e0b",
};

function uid() { return Math.random().toString(36).slice(2, 9); }

export default function ChartPanel({
  panelId, symbol, periodCfg, drawingTool, indicators,
  showRSI, showMACD, isActive, drawings, onDrawingAdd, onDrawingErase, onActivate
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rsiContainerRef = useRef<HTMLDivElement>(null);
  const macdContainerRef = useRef<HTMLDivElement>(null);

  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const rsiChartRef = useRef<IChartApi | null>(null);
  const macdChartRef = useRef<IChartApi | null>(null);

  const indicatorSeriesRefs = useRef<Record<string, ISeriesApi<any>>>({});
  const candlesRef = useRef<Candle[]>([]);

  const [loading, setLoading] = useState(false);
  const [crosshair, setCrosshair] = useState<{ o: number; h: number; l: number; c: number; v: number; t: number } | null>(null);

  const drawingStateRef = useRef<{
    active: boolean;
    startX: number; startY: number;
    startTime: number | null;
    startPrice: number | null;
  } | null>(null);

  const drawCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    const chart = chartRef.current;
    const series = candleSeriesRef.current;
    if (!canvas || !chart || !series) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const allDrawings = [...drawings];
    if (drawingStateRef.current?.active && drawingStateRef.current.startTime != null && drawingStateRef.current.startPrice != null) {
      allDrawings.push({
        id: "preview",
        type: drawingTool === "none" ? "trendline" : drawingTool,
        startTime: drawingStateRef.current.startTime,
        startPrice: drawingStateRef.current.startPrice,
        endTime: drawingStateRef.current.startTime,
        endPrice: drawingStateRef.current.startPrice,
        color: "#6366f1",
      });
    }

    for (const d of allDrawings) {
      if (d.type === "none" || d.type === "eraser") continue;
      const x1 = chart.timeScale().timeToCoordinate(d.startTime as Time);
      const y1 = series.priceToCoordinate(d.startPrice);
      const x2 = chart.timeScale().timeToCoordinate(d.endTime as Time);
      const y2 = series.priceToCoordinate(d.endPrice);
      if (x1 == null || y1 == null) continue;

      ctx.save();
      ctx.strokeStyle = d.id === "preview" ? "rgba(99,102,241,0.7)" : d.color;
      ctx.lineWidth = 1.5;
      ctx.setLineDash(d.id === "preview" ? [4, 3] : []);
      ctx.beginPath();

      if (d.type === "hline") {
        ctx.moveTo(0, y1);
        ctx.lineTo(canvas.width, y1);
        ctx.stroke();
        ctx.fillStyle = d.color;
        ctx.font = "11px sans-serif";
        ctx.fillText(`₹${d.startPrice.toFixed(2)}`, 4, y1 - 3);
      } else if (d.type === "vline") {
        if (x1 == null) continue;
        ctx.moveTo(x1, 0);
        ctx.lineTo(x1, canvas.height);
        ctx.stroke();
      } else if (d.type === "trendline") {
        if (x2 == null || y2 == null) continue;
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
        ctx.fillStyle = "rgba(99,102,241,0.2)";
        ctx.beginPath();
        ctx.arc(x1, y1, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.arc(x2, y2, 4, 0, Math.PI * 2);
        ctx.fill();
      } else if (d.type === "rectangle") {
        if (x2 == null || y2 == null) continue;
        ctx.fillStyle = "rgba(99,102,241,0.08)";
        ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
        ctx.rect(x1, y1, x2 - x1, y2 - y1);
        ctx.stroke();
      }
      ctx.restore();
    }
  }, [drawings, drawingTool]);

  const applyIndicators = useCallback(() => {
    const chart = chartRef.current;
    if (!chart || !candlesRef.current.length) return;
    const candles = candlesRef.current;
    const closes = candles.map(c => c.close);
    const times = candles.map(c => c.time as Time);

    const removeOld = (key: string) => {
      if (indicatorSeriesRefs.current[key]) {
        try { chart.removeSeries(indicatorSeriesRefs.current[key]); } catch {}
        delete indicatorSeriesRefs.current[key];
      }
    };

    const addLine = (key: string, values: (number | null)[], color: string, width = 1, paneId?: string) => {
      removeOld(key);
      if (!indicators.has(key) && !["rsi", "macd"].includes(key)) return;
      const s = chart.addSeries(LineSeries, {
        color, lineWidth: width as 1, priceScaleId: paneId ?? "right",
        priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
      });
      const data = values.map((v, i) => v !== null ? { time: times[i], value: v } : null).filter(Boolean) as { time: Time; value: number }[];
      s.setData(data);
      indicatorSeriesRefs.current[key] = s;
    };

    const IND_MAP: Record<string, { fn: () => (number | null)[]; color: string }> = {
      ema9:   { fn: () => calcEMA(closes, 9),   color: COLORS.ema9 },
      ema21:  { fn: () => calcEMA(closes, 21),  color: COLORS.ema21 },
      ema50:  { fn: () => calcEMA(closes, 50),  color: COLORS.ema50 },
      ema200: { fn: () => calcEMA(closes, 200), color: COLORS.ema200 },
      sma50:  { fn: () => calcSMA(closes, 50),  color: COLORS.sma50 },
    };

    for (const [key, cfg] of Object.entries(IND_MAP)) {
      if (indicators.has(key)) addLine(key, cfg.fn(), cfg.color);
      else removeOld(key);
    }

    if (indicators.has("bb")) {
      const bb = calcBollingerBands(closes);
      addLine("bbUpper",  bb.upper,  COLORS.bbUpper,  1);
      addLine("bbMiddle", bb.middle, COLORS.bbMiddle, 1);
      addLine("bbLower",  bb.lower,  COLORS.bbLower,  1);
    } else {
      ["bbUpper", "bbMiddle", "bbLower"].forEach(removeOld);
    }
  }, [indicators]);

  const applyRSI = useCallback((candles: Candle[]) => {
    const rc = rsiChartRef.current;
    if (!rc) return;
    try {
      const closes = candles.map(c => c.close);
      const rsiVals = calcRSI(closes);
      const s = rc.addSeries(LineSeries, { color: COLORS.rsiLine, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      const data = rsiVals.map((v, i) => v !== null ? { time: candles[i].time as Time, value: v } : null).filter(Boolean) as { time: Time; value: number }[];
      s.setData(data);
      const ob = rc.addSeries(LineSeries, { color: "#ef444466", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      ob.setData(candles.map(c => ({ time: c.time as Time, value: 70 })));
      const os = rc.addSeries(LineSeries, { color: "#22c55e66", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      os.setData(candles.map(c => ({ time: c.time as Time, value: 30 })));
    } catch {}
  }, []);

  const applyMACD = useCallback((candles: Candle[]) => {
    const mc = macdChartRef.current;
    if (!mc) return;
    try {
      const closes = candles.map(c => c.close);
      const { macd, signal, histogram } = calcMACD(closes);
      const times = candles.map(c => c.time as Time);

      const histSeries = mc.addSeries(HistogramSeries, {
        priceScaleId: "right",
        priceLineVisible: false, lastValueVisible: false,
      });
      const histData = histogram.map((v, i) => v !== null
        ? { time: times[i], value: v, color: v >= 0 ? "#22c55e" : "#ef4444" }
        : null
      ).filter(Boolean) as { time: Time; value: number; color: string }[];
      histSeries.setData(histData);

      const macdSeries = mc.addSeries(LineSeries, { color: COLORS.macdLine, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      macdSeries.setData(macd.map((v, i) => v !== null ? { time: times[i], value: v } : null).filter(Boolean) as any);

      const sigSeries = mc.addSeries(LineSeries, { color: COLORS.macdSignal, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      sigSeries.setData(signal.map((v, i) => v !== null ? { time: times[i], value: v } : null).filter(Boolean) as any);
    } catch {}
  }, []);

  const fetchData = useCallback(async () => {
    if (!symbol) return;
    setLoading(true);
    const sym = symbol === "NIFTY 50" ? "%5ENSEI" : symbol === "BANKNIFTY" ? "%5ENSEBANK" : symbol;
    try {
      const res = await fetch(`/api/stocks/${sym}/history?period=${periodCfg.p}&interval=${periodCfg.i}`);
      if (!res.ok) throw new Error("fetch failed");
      const data = await res.json();
      const candles: Candle[] = data.candles ?? [];
      candlesRef.current = candles;

      if (candleSeriesRef.current && candles.length) {
        candleSeriesRef.current.setData(candles.map(c => ({
          time: c.time as Time, open: c.open, high: c.high, low: c.low, close: c.close,
        })));
        volSeriesRef.current?.setData(candles.map(c => ({
          time: c.time as Time, value: c.volume,
          color: c.close >= c.open ? "rgba(34,197,94,0.5)" : "rgba(239,68,68,0.5)",
        })));
        applyIndicators();
        if (showRSI) applyRSI(candles);
        if (showMACD) applyMACD(candles);
        chartRef.current?.timeScale().fitContent();
      }
    } catch {
    } finally { setLoading(false); }
  }, [symbol, periodCfg, applyIndicators, showRSI, showMACD, applyRSI, applyMACD]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      layout: { background: { type: ColorType.Solid, color: COLORS.bg }, textColor: COLORS.text },
      grid: { vertLines: { color: COLORS.gridLine }, horzLines: { color: COLORS.gridLine } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: COLORS.gridLine },
      timeScale: { borderColor: COLORS.gridLine, timeVisible: true },
      handleScroll: true, handleScale: true,
    });
    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e", downColor: "#ef4444",
      borderUpColor: "#22c55e", borderDownColor: "#ef4444",
      wickUpColor: "#22c55e", wickDownColor: "#ef4444",
      priceScaleId: "right",
    });
    candleSeriesRef.current = candleSeries;

    const volSeries = chart.addSeries(HistogramSeries, {
      priceScaleId: "vol",
      priceLineVisible: false, lastValueVisible: false,
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    volSeriesRef.current = volSeries;

    chart.subscribeCrosshairMove((p) => {
      if (p.seriesData.has(candleSeries)) {
        const bar = p.seriesData.get(candleSeries) as any;
        if (bar) setCrosshair({ o: bar.open, h: bar.high, l: bar.low, c: bar.close, v: bar.customValues?.volume ?? 0, t: bar.time });
      }
      if (!p.time) setCrosshair(null);
    });

    chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
      requestAnimationFrame(drawCanvas);
    });

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth, height: el.clientHeight });
      const canvas = canvasRef.current;
      if (canvas) { canvas.width = el.clientWidth; canvas.height = el.clientHeight; }
      requestAnimationFrame(drawCanvas);
    });
    ro.observe(el);

    return () => { ro.disconnect(); chart.remove(); chartRef.current = null; };
  }, []);

  useEffect(() => {
    const rsiEl = rsiContainerRef.current;
    if (!rsiEl || !showRSI) return;
    const chart = createChart(rsiEl, {
      layout: { background: { type: ColorType.Solid, color: COLORS.bg }, textColor: COLORS.text },
      grid: { vertLines: { color: COLORS.gridLine }, horzLines: { color: COLORS.gridLine } },
      rightPriceScale: { borderColor: COLORS.gridLine, scaleMargins: { top: 0.1, bottom: 0.1 } },
      timeScale: { borderColor: COLORS.gridLine, visible: false },
      handleScroll: false, handleScale: false,
    });
    rsiChartRef.current = chart;
    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: rsiEl.clientWidth, height: rsiEl.clientHeight });
    });
    ro.observe(rsiEl);
    if (candlesRef.current.length) applyRSI(candlesRef.current);
    return () => { ro.disconnect(); chart.remove(); rsiChartRef.current = null; };
  }, [showRSI]);

  useEffect(() => {
    const macdEl = macdContainerRef.current;
    if (!macdEl || !showMACD) return;
    const chart = createChart(macdEl, {
      layout: { background: { type: ColorType.Solid, color: COLORS.bg }, textColor: COLORS.text },
      grid: { vertLines: { color: COLORS.gridLine }, horzLines: { color: COLORS.gridLine } },
      rightPriceScale: { borderColor: COLORS.gridLine, scaleMargins: { top: 0.1, bottom: 0.1 } },
      timeScale: { borderColor: COLORS.gridLine, visible: false },
      handleScroll: false, handleScale: false,
    });
    macdChartRef.current = chart;
    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: macdEl.clientWidth, height: macdEl.clientHeight });
    });
    ro.observe(macdEl);
    if (candlesRef.current.length) applyMACD(candlesRef.current);
    return () => { ro.disconnect(); chart.remove(); macdChartRef.current = null; };
  }, [showMACD]);

  useEffect(() => { fetchData(); }, [symbol, periodCfg]);
  useEffect(() => { applyIndicators(); }, [indicators]);
  useEffect(() => { requestAnimationFrame(drawCanvas); }, [drawings, drawingTool, drawCanvas]);

  function getCanvasCoords(e: React.MouseEvent<HTMLCanvasElement>) {
    const rect = canvasRef.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  function handleCanvasMouseDown(e: React.MouseEvent<HTMLCanvasElement>) {
    if (drawingTool === "none") return;
    onActivate();
    const { x, y } = getCanvasCoords(e);
    const time = chartRef.current?.timeScale().coordinateToTime(x);
    const price = candleSeriesRef.current?.coordinateToPrice(y);
    if (time == null || price == null) return;

    if (drawingTool === "hline" || drawingTool === "vline") {
      onDrawingAdd({ id: uid(), type: drawingTool, startTime: time as number, startPrice: price, endTime: time as number, endPrice: price, color: "#6366f1" });
      return;
    }
    drawingStateRef.current = { active: true, startX: x, startY: y, startTime: time as number, startPrice: price };
  }

  function handleCanvasMouseMove(e: React.MouseEvent<HTMLCanvasElement>) {
    if (!drawingStateRef.current?.active) return;
    const { x, y } = getCanvasCoords(e);
    const time = chartRef.current?.timeScale().coordinateToTime(x);
    const price = candleSeriesRef.current?.coordinateToPrice(y);
    if (!time || !price) return;
    drawingStateRef.current = { ...drawingStateRef.current, startTime: drawingStateRef.current.startTime!, startPrice: drawingStateRef.current.startPrice! };

    const preview: Drawing = {
      id: "preview", type: drawingTool,
      startTime: drawingStateRef.current.startTime!,
      startPrice: drawingStateRef.current.startPrice!,
      endTime: time as number, endPrice: price, color: "#6366f1",
    };
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx || !chartRef.current || !candleSeriesRef.current) return;
    const canvas = canvasRef.current!;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const d of drawings) drawSingleDrawing(ctx, d, canvas);
    drawSingleDrawing(ctx, preview, canvas);
  }

  function drawSingleDrawing(ctx: CanvasRenderingContext2D, d: Drawing, canvas: HTMLCanvasElement) {
    const chart = chartRef.current!;
    const series = candleSeriesRef.current!;
    const x1 = chart.timeScale().timeToCoordinate(d.startTime as Time);
    const y1 = series.priceToCoordinate(d.startPrice);
    if (x1 == null || y1 == null) return;
    ctx.save();
    ctx.strokeStyle = d.id === "preview" ? "rgba(99,102,241,0.8)" : d.color;
    ctx.lineWidth = 1.5;
    ctx.setLineDash(d.id === "preview" ? [4, 3] : []);
    ctx.beginPath();
    if (d.type === "hline") {
      ctx.moveTo(0, y1); ctx.lineTo(canvas.width, y1);
    } else if (d.type === "vline") {
      ctx.moveTo(x1, 0); ctx.lineTo(x1, canvas.height);
    } else {
      const x2 = chart.timeScale().timeToCoordinate(d.endTime as Time);
      const y2 = series.priceToCoordinate(d.endPrice);
      if (x2 == null || y2 == null) { ctx.restore(); return; }
      if (d.type === "trendline") { ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); }
      else if (d.type === "rectangle") {
        ctx.fillStyle = "rgba(99,102,241,0.08)";
        ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
        ctx.rect(x1, y1, x2 - x1, y2 - y1);
      }
    }
    ctx.stroke();
    ctx.restore();
  }

  function handleCanvasMouseUp(e: React.MouseEvent<HTMLCanvasElement>) {
    const state = drawingStateRef.current;
    if (!state?.active) return;
    const { x, y } = getCanvasCoords(e);
    const time = chartRef.current?.timeScale().coordinateToTime(x);
    const price = candleSeriesRef.current?.coordinateToPrice(y);
    drawingStateRef.current = null;
    if (time == null || price == null) return;

    if (drawingTool === "eraser") return;
    onDrawingAdd({
      id: uid(), type: drawingTool,
      startTime: state.startTime!, startPrice: state.startPrice!,
      endTime: time as number, endPrice: price, color: "#6366f1",
    });
  }

  const pct = crosshair ? ((crosshair.c - crosshair.o) / crosshair.o * 100) : 0;
  const isUp = pct >= 0;

  return (
    <div
      className={`flex flex-col h-full rounded border ${isActive ? "border-indigo-500" : "border-gray-800"}`}
      style={{ background: COLORS.bg }}
      onClick={onActivate}
    >
      <div className="flex items-center gap-3 px-3 py-1.5 border-b border-gray-800 min-h-[36px]">
        <span className="font-semibold text-white text-sm">{symbol}</span>
        {crosshair ? (
          <span className="flex gap-2 text-xs text-gray-400">
            <span>O <span className="text-white">{crosshair.o.toFixed(2)}</span></span>
            <span>H <span className="text-white">{crosshair.h.toFixed(2)}</span></span>
            <span>L <span className="text-white">{crosshair.l.toFixed(2)}</span></span>
            <span>C <span className={isUp ? "text-green-400" : "text-red-400"}>{crosshair.c.toFixed(2)}</span></span>
            <span className={isUp ? "text-green-400" : "text-red-400"}>{isUp ? "+" : ""}{pct.toFixed(2)}%</span>
          </span>
        ) : null}
        {loading && <span className="text-xs text-gray-500 ml-auto animate-pulse">Loading…</span>}
      </div>

      <div className="flex-1 relative min-h-0">
        <div ref={containerRef} className="absolute inset-0" />
        <canvas
          ref={canvasRef}
          className="absolute inset-0"
          style={{
            pointerEvents: drawingTool !== "none" ? "all" : "none",
            cursor: drawingTool === "eraser" ? "cell" : drawingTool !== "none" ? "crosshair" : "default",
            zIndex: 10,
          }}
          onMouseDown={handleCanvasMouseDown}
          onMouseMove={handleCanvasMouseMove}
          onMouseUp={handleCanvasMouseUp}
        />
      </div>

      {showRSI && (
        <div className="border-t border-gray-800" style={{ height: 90 }}>
          <div className="text-[10px] text-gray-500 px-2 pt-1">RSI (14)</div>
          <div ref={rsiContainerRef} style={{ height: 70 }} />
        </div>
      )}
      {showMACD && (
        <div className="border-t border-gray-800" style={{ height: 100 }}>
          <div className="text-[10px] text-gray-500 px-2 pt-1">MACD (12,26,9)</div>
          <div ref={macdContainerRef} style={{ height: 78 }} />
        </div>
      )}
    </div>
  );
}
