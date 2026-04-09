import { useEffect, useRef, useState, useCallback } from "react";
import { useParams, useLocation } from "wouter";
import { ArrowLeft, RefreshCw, AlertCircle } from "lucide-react";
import * as echarts from "echarts";
import { calcEMA, calcBollingerBands } from "@/lib/indicators";

interface Candle { time: number; open: number; high: number; low: number; close: number; volume: number; }

const PERIODS = [
  { label: "1D",  p: "5d",  i: "5m"   },
  { label: "1W",  p: "1mo", i: "1d"   },
  { label: "1M",  p: "1mo", i: "1d"   },
  { label: "3M",  p: "3mo", i: "1d"   },
  { label: "6M",  p: "6mo", i: "1d"   },
  { label: "1Y",  p: "1y",  i: "1wk"  },
  { label: "2Y",  p: "2y",  i: "1wk"  },
];

const EMA_OPTS = [
  { period: 9,   color: "#f59e0b", label: "EMA 9"   },
  { period: 21,  color: "#6366f1", label: "EMA 21"  },
  { period: 50,  color: "#10b981", label: "EMA 50"  },
  { period: 200, color: "#ef4444", label: "EMA 200" },
];

const DARK = "#131722";
const GRID_COLOR = "rgba(255,255,255,0.06)";
const TEXT_COLOR = "#c4cfd8";

function toDateStr(ts: number) {
  const d = new Date(ts * 1000);
  const date = d.toISOString().slice(0, 10);
  const hh = d.getUTCHours();
  const mm = d.getUTCMinutes();
  return hh === 0 && mm === 0 ? date : `${date} ${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

export default function ChartView() {
  const { symbol } = useParams<{ symbol: string }>();
  const [, navigate] = useLocation();

  const containerRef  = useRef<HTMLDivElement>(null);
  const chartRef      = useRef<echarts.ECharts | null>(null);
  const candles       = useRef<Candle[]>([]);

  const [periodIdx, setPeriodIdx]       = useState(2);
  const [activeEMAs, setActiveEMAs]     = useState<Set<number>>(new Set([21]));
  const [showBB, setShowBB]             = useState(false);
  const [loading, setLoading]           = useState(true);
  const [error, setError]               = useState<string | null>(null);
  const [companyName, setCompanyName]   = useState("");
  const [lastPrice, setLastPrice]       = useState<number | null>(null);
  const [pct, setPct]                   = useState<number | null>(null);

  const renderChart = useCallback(() => {
    const chart = chartRef.current;
    if (!chart || !candles.current.length) return;

    const cs = candles.current;
    const dates = cs.map(c => toDateStr(c.time));
    const closes = cs.map(c => c.close);
    const ohlc = cs.map(c => [c.open, c.close, c.low, c.high]);
    const volumes = cs.map(c => c.volume);

    const series: object[] = [
      {
        name: "Price", type: "candlestick",
        xAxisIndex: 0, yAxisIndex: 0,
        data: ohlc,
        itemStyle: {
          color: "#22c55e", color0: "#ef4444",
          borderColor: "#22c55e", borderColor0: "#ef4444",
          borderWidth: 1,
        },
      },
      {
        name: "Volume", type: "bar",
        xAxisIndex: 1, yAxisIndex: 1,
        data: volumes.map((v, i) => ({
          value: v,
          itemStyle: { color: cs[i].close >= cs[i].open ? "rgba(34,197,94,0.45)" : "rgba(239,68,68,0.45)" },
        })),
        barMaxWidth: 12,
      },
    ];

    for (const opt of EMA_OPTS) {
      if (!activeEMAs.has(opt.period)) continue;
      const vals = calcEMA(closes, opt.period);
      series.push({
        name: opt.label, type: "line",
        xAxisIndex: 0, yAxisIndex: 0,
        data: vals.map(v => v ?? null),
        lineStyle: { color: opt.color, width: 1.5 },
        showSymbol: false, connectNulls: false,
      });
    }

    if (showBB) {
      const bb = calcBollingerBands(closes);
      series.push(
        { name: "BB Upper", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: bb.upper.map(v => v ?? null), lineStyle: { color: "#3b82f6", width: 1, type: "dashed" }, showSymbol: false, connectNulls: false },
        { name: "BB Mid",   type: "line", xAxisIndex: 0, yAxisIndex: 0, data: bb.middle.map(v => v ?? null), lineStyle: { color: "#64748b", width: 1, type: "dashed" }, showSymbol: false, connectNulls: false },
        { name: "BB Lower", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: bb.lower.map(v => v ?? null), lineStyle: { color: "#3b82f6", width: 1, type: "dashed" }, showSymbol: false, connectNulls: false },
      );
    }

    chart.setOption({
      backgroundColor: DARK,
      animation: false,
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross", crossStyle: { color: "rgba(255,255,255,0.3)" } },
        backgroundColor: "#1e2131",
        borderColor: "#374151",
        textStyle: { color: TEXT_COLOR, fontSize: 11 },
        formatter: (params: any) => {
          const candle = Array.isArray(params) ? params.find((p: any) => p.seriesName === "Price") : null;
          if (!candle) return "";
          const [o, c, l, h] = candle.data as number[];
          const pctVal = (((c - o) / o) * 100).toFixed(2);
          const color = c >= o ? "#22c55e" : "#ef4444";
          return `<div style="font-size:11px;line-height:1.7">
            <b style="color:#fff">${candle.name}</b><br/>
            O <b>${o.toFixed(2)}</b> &nbsp; H <b style="color:#22c55e">${h.toFixed(2)}</b> &nbsp;
            L <b style="color:#ef4444">${l.toFixed(2)}</b> &nbsp; C <b>${c.toFixed(2)}</b> &nbsp;
            <span style="color:${color}">${Number(pctVal) >= 0 ? "+" : ""}${pctVal}%</span>
          </div>`;
        },
      },
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      dataZoom: [
        { type: "inside", xAxisIndex: [0, 1], start: 0, end: 100 },
        { type: "slider", xAxisIndex: [0, 1], bottom: 4, height: 16, borderColor: "transparent", dataBackground: { lineStyle: { color: GRID_COLOR }, areaStyle: { color: GRID_COLOR } } },
      ],
      grid: [
        { top: "8%", left: 55, right: 8, height: "65%" },
        { top: "78%", left: 55, right: 8, height: "10%" },
      ],
      xAxis: [
        { gridIndex: 0, data: dates, axisLine: { lineStyle: { color: GRID_COLOR } }, axisLabel: { color: TEXT_COLOR, fontSize: 10 }, axisTick: { show: false }, splitLine: { lineStyle: { color: GRID_COLOR } } },
        { gridIndex: 1, data: dates, axisLine: { lineStyle: { color: GRID_COLOR } }, axisLabel: { color: TEXT_COLOR, fontSize: 10 }, axisTick: { show: false }, splitLine: { show: false } },
      ],
      yAxis: [
        { gridIndex: 0, scale: true, axisLine: { lineStyle: { color: GRID_COLOR } }, axisLabel: { color: TEXT_COLOR, fontSize: 10 }, splitLine: { lineStyle: { color: GRID_COLOR } } },
        { gridIndex: 1, scale: true, axisLine: { lineStyle: { color: GRID_COLOR } }, axisLabel: { show: false }, splitLine: { show: false } },
      ],
      series,
    }, true);
  }, [activeEMAs, showBB]);

  const fetchData = useCallback(async () => {
    if (!symbol) return;
    setLoading(true); setError(null);
    const { p, i } = PERIODS[periodIdx];
    const sym = symbol.replace("^", "%5E");
    try {
      const res = await fetch(`/api/stocks/${sym}/history?period=${p}&interval=${i}`);
      if (!res.ok) throw new Error("Failed to load data");
      const data = await res.json();
      candles.current = data.candles ?? [];
      if (data.companyName) setCompanyName(data.companyName);
      if (candles.current.length > 0) {
        const last = candles.current[candles.current.length - 1];
        const first = candles.current[0];
        setLastPrice(last.close);
        setPct(((last.close - first.open) / first.open) * 100);
      }
    } catch (e: any) {
      setError(e.message);
    } finally { setLoading(false); }
    renderChart();
  }, [symbol, periodIdx, renderChart]);

  useEffect(() => {
    const div = containerRef.current;
    if (!div) return;
    const chart = echarts.init(div, null, { renderer: "canvas" });
    chartRef.current = chart;
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(div);
    fetchData();
    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => { fetchData(); }, [symbol, periodIdx]);
  useEffect(() => { renderChart(); }, [activeEMAs, showBB]);

  const isUp = (pct ?? 0) >= 0;

  return (
    <div className="flex flex-col h-full" style={{ background: DARK, color: TEXT_COLOR }}>
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-gray-800 shrink-0">
        <button onClick={() => navigate("/")} className="text-gray-400 hover:text-white">
          <ArrowLeft size={18} />
        </button>
        <div className="flex flex-col">
          <span className="font-bold text-white text-sm">{symbol}</span>
          {companyName && <span className="text-xs text-gray-500">{companyName}</span>}
        </div>
        {lastPrice !== null && (
          <div className="flex items-baseline gap-1.5">
            <span className="font-mono text-lg font-bold text-white">{lastPrice.toFixed(2)}</span>
            <span className={`text-sm font-medium ${isUp ? "text-green-400" : "text-red-400"}`}>
              {isUp ? "+" : ""}{pct?.toFixed(2)}%
            </span>
          </div>
        )}
        <div className="ml-auto flex items-center gap-1">
          <button onClick={() => fetchData()} className="text-gray-400 hover:text-white">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {/* Period selector */}
      <div className="flex items-center gap-0.5 px-3 py-1 border-b border-gray-800 shrink-0">
        {PERIODS.map((p, i) => (
          <button
            key={p.label}
            onClick={() => setPeriodIdx(i)}
            className={`px-2 py-0.5 text-xs rounded ${i === periodIdx ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-white"}`}
          >
            {p.label}
          </button>
        ))}
        <div className="ml-3 flex items-center gap-1">
          {EMA_OPTS.map(opt => (
            <button
              key={opt.period}
              onClick={() => setActiveEMAs(prev => {
                const next = new Set(prev);
                if (next.has(opt.period)) next.delete(opt.period); else next.add(opt.period);
                return next;
              })}
              className="px-2 py-0.5 text-xs rounded"
              style={{
                background: activeEMAs.has(opt.period) ? opt.color + "33" : "transparent",
                color: activeEMAs.has(opt.period) ? opt.color : "#6b7280",
                border: `1px solid ${activeEMAs.has(opt.period) ? opt.color : "#374151"}`,
              }}
            >
              {opt.label}
            </button>
          ))}
          <button
            onClick={() => setShowBB(v => !v)}
            className="px-2 py-0.5 text-xs rounded"
            style={{
              background: showBB ? "#3b82f633" : "transparent",
              color: showBB ? "#3b82f6" : "#6b7280",
              border: `1px solid ${showBB ? "#3b82f6" : "#374151"}`,
            }}
          >
            BB
          </button>
        </div>
      </div>

      {/* Chart */}
      <div className="flex-1 relative min-h-0">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <div className="animate-spin rounded-full border-2 border-indigo-500 border-t-transparent w-8 h-8" />
          </div>
        )}
        {error && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 z-10">
            <AlertCircle className="text-red-400" size={24} />
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}
        <div ref={containerRef} className="absolute inset-0" />
      </div>
    </div>
  );
}
