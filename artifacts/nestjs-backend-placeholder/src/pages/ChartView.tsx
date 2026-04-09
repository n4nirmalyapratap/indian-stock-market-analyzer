import { useEffect, useRef, useState, useCallback } from "react";
import { useParams, useLocation } from "wouter";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  type LineData,
  type Time,
} from "lightweight-charts";
import { ArrowLeft, RefreshCw, TrendingUp, TrendingDown, AlertCircle } from "lucide-react";

interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface HistoryResponse {
  symbol: string;
  companyName: string;
  currency: string;
  period: string;
  interval: string;
  candles: Candle[];
}

const PERIODS: { label: string; period: string; interval: string }[] = [
  { label: "1W",  period: "5d",  interval: "15m" },
  { label: "1M",  period: "1mo", interval: "1d"  },
  { label: "3M",  period: "3mo", interval: "1d"  },
  { label: "6M",  period: "6mo", interval: "1d"  },
  { label: "1Y",  period: "1y",  interval: "1wk" },
  { label: "2Y",  period: "2y",  interval: "1wk" },
];

const EMA_CONFIGS = [
  { period: 9,   color: "#f59e0b", label: "EMA 9"   },
  { period: 21,  color: "#6366f1", label: "EMA 21"  },
  { period: 50,  color: "#10b981", label: "EMA 50"  },
  { period: 200, color: "#ef4444", label: "EMA 200" },
];

function calcEMA(candles: Candle[], period: number): LineData<Time>[] {
  if (candles.length < period) return [];
  const k = 2 / (period + 1);
  const result: LineData<Time>[] = [];
  let ema = candles.slice(0, period).reduce((s, c) => s + c.close, 0) / period;
  result.push({ time: candles[period - 1].time as Time, value: parseFloat(ema.toFixed(2)) });
  for (let i = period; i < candles.length; i++) {
    ema = candles[i].close * k + ema * (1 - k);
    result.push({ time: candles[i].time as Time, value: parseFloat(ema.toFixed(2)) });
  }
  return result;
}

function fmtPrice(n: number) {
  return n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function ChartView() {
  const params = useParams<{ symbol: string }>();
  const [, navigate] = useLocation();
  const symbol = (params.symbol || "").toUpperCase();

  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef          = useRef<IChartApi | null>(null);
  const candleSeriesRef   = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef   = useRef<ISeriesApi<"Histogram"> | null>(null);
  const emaSeriesRefs     = useRef<Map<number, ISeriesApi<"Line">>>(new Map());

  const [data, setData]           = useState<HistoryResponse | null>(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);
  const [periodIdx, setPeriodIdx] = useState(1);
  const [activeEMAs, setActiveEMAs] = useState<Set<number>>(new Set([21]));
  const [hovered, setHovered]     = useState<Candle | null>(null);

  const fetchData = useCallback(async (pIdx: number) => {
    if (!symbol) return;
    const { period, interval } = PERIODS[pIdx];
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/stocks/${encodeURIComponent(symbol)}/history?period=${period}&interval=${interval}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `API error ${res.status}`);
      }
      const json: HistoryResponse = await res.json();
      setData(json);
    } catch (e: any) {
      setError(e.message || "Failed to load chart data");
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => { fetchData(periodIdx); }, [fetchData, periodIdx]);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#374151",
        fontSize: 12,
      },
      grid: {
        vertLines: { color: "#f3f4f6" },
        horzLines: { color: "#f3f4f6" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#e5e7eb", scaleMargins: { top: 0.05, bottom: 0.25 } },
      timeScale: {
        borderColor: "#e5e7eb",
        timeVisible: true,
        secondsVisible: false,
      },
      width:  chartContainerRef.current.clientWidth,
      height: chartContainerRef.current.clientHeight,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor:        "#22c55e",
      downColor:      "#ef4444",
      borderVisible:  false,
      wickUpColor:    "#22c55e",
      wickDownColor:  "#ef4444",
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      color:       "#93c5fd",
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    chartRef.current        = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    const resizeObserver = new ResizeObserver(() => {
      if (chartContainerRef.current) {
        chart.applyOptions({
          width:  chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        });
      }
    });
    resizeObserver.observe(chartContainerRef.current);

    chart.subscribeCrosshairMove((param) => {
      if (!param.point || !param.time) { setHovered(null); return; }
      const d = param.seriesData.get(candleSeries);
      if (d) setHovered(d as unknown as Candle);
    });

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current        = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      emaSeriesRefs.current.clear();
    };
  }, []);

  useEffect(() => {
    if (!data || !candleSeriesRef.current || !volumeSeriesRef.current || !chartRef.current) return;

    const candles = data.candles;

    const candleData: CandlestickData<Time>[] = candles.map(c => ({
      time:  c.time as Time,
      open:  c.open,
      high:  c.high,
      low:   c.low,
      close: c.close,
    }));
    candleSeriesRef.current.setData(candleData);

    const volumeData: HistogramData<Time>[] = candles.map(c => ({
      time:  c.time as Time,
      value: c.volume,
      color: c.close >= c.open ? "#bbf7d0" : "#fecaca",
    }));
    volumeSeriesRef.current.setData(volumeData);

    emaSeriesRefs.current.forEach(s => chartRef.current?.removeSeries(s));
    emaSeriesRefs.current.clear();

    activeEMAs.forEach(period => {
      const cfg = EMA_CONFIGS.find(e => e.period === period);
      if (!cfg || !chartRef.current) return;
      const emaData = calcEMA(candles, period);
      if (emaData.length === 0) return;
      const series = chartRef.current.addSeries(LineSeries, {
        color:     cfg.color,
        lineWidth: 1,
        crosshairMarkerVisible: false,
        lastValueVisible: true,
        priceLineVisible: false,
      });
      series.setData(emaData);
      emaSeriesRefs.current.set(period, series);
    });

    chartRef.current.timeScale().fitContent();
  }, [data, activeEMAs]);

  function toggleEMA(period: number) {
    setActiveEMAs(prev => {
      const next = new Set(prev);
      if (next.has(period)) next.delete(period);
      else next.add(period);
      return next;
    });
  }

  const last    = data?.candles?.at(-1);
  const prev    = data?.candles?.at(-2);
  const display = hovered ?? last;
  const change  = display && prev ? display.close - prev.close : (last && data?.candles?.at(-2) ? last.close - data.candles.at(-2)!.close : 0);
  const changePct = prev && prev.close ? (change / prev.close) * 100 : 0;

  return (
    <div className="flex flex-col h-full min-h-0">

      {/* ── Top bar ─────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-100 bg-white flex-shrink-0 flex-wrap gap-y-2">
        <button
          onClick={() => navigate(-1 as any)}
          className="p-1.5 rounded-lg text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 transition flex-shrink-0"
          title="Go back"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-gray-900 text-lg leading-tight">{symbol}</span>
            {data?.companyName && data.companyName !== symbol && (
              <span className="text-sm text-gray-500 truncate">{data.companyName}</span>
            )}
            {display && (
              <span className="text-base font-semibold text-gray-800">₹{fmtPrice(display.close)}</span>
            )}
            {display && (
              <span className={`text-sm font-medium flex items-center gap-0.5 ${changePct >= 0 ? "text-green-600" : "text-red-500"}`}>
                {changePct >= 0 ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
              </span>
            )}
          </div>
          {display && (
            <p className="text-xs text-gray-400 mt-0.5 flex gap-3">
              <span>O: ₹{fmtPrice(display.open)}</span>
              <span>H: ₹{fmtPrice(display.high)}</span>
              <span>L: ₹{fmtPrice(display.low)}</span>
              <span>C: ₹{fmtPrice(display.close)}</span>
              {display.volume ? <span>Vol: {display.volume.toLocaleString("en-IN")}</span> : null}
            </p>
          )}
        </div>

        <button
          onClick={() => fetchData(periodIdx)}
          disabled={loading}
          className="p-1.5 rounded-lg text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 transition flex-shrink-0"
          title="Refresh"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin text-indigo-500" : ""}`} />
        </button>
      </div>

      {/* ── Controls ────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-4 py-2 bg-gray-50 border-b border-gray-100 flex-shrink-0 flex-wrap gap-y-2">

        {/* Period selector */}
        <div className="flex items-center gap-1 bg-white rounded-lg border border-gray-200 p-0.5">
          {PERIODS.map((p, i) => (
            <button
              key={p.label}
              onClick={() => setPeriodIdx(i)}
              className={`px-2.5 py-1 text-xs font-semibold rounded-md transition ${
                periodIdx === i
                  ? "bg-indigo-600 text-white"
                  : "text-gray-500 hover:text-indigo-600 hover:bg-indigo-50"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="w-px h-5 bg-gray-200 hidden sm:block" />

        {/* EMA toggles */}
        <div className="flex items-center gap-1 flex-wrap">
          <span className="text-xs text-gray-400 font-medium mr-0.5">EMA:</span>
          {EMA_CONFIGS.map(cfg => (
            <button
              key={cfg.period}
              onClick={() => toggleEMA(cfg.period)}
              className={`text-xs px-2 py-0.5 rounded-full border transition font-medium ${
                activeEMAs.has(cfg.period)
                  ? "text-white border-transparent"
                  : "bg-white text-gray-400 border-gray-200 hover:border-gray-300"
              }`}
              style={activeEMAs.has(cfg.period) ? { backgroundColor: cfg.color, borderColor: cfg.color } : {}}
            >
              {cfg.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Chart area ─────────────────────────────────────────────────── */}
      <div className="relative" style={{ height: "calc(100vh - 180px)", minHeight: "400px" }}>
        {error && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <div className="flex flex-col items-center gap-3 text-center p-6">
              <AlertCircle className="w-10 h-10 text-red-300" />
              <p className="font-semibold text-gray-700">{error}</p>
              <button
                onClick={() => fetchData(periodIdx)}
                className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition"
              >
                Retry
              </button>
            </div>
          </div>
        )}

        {loading && (
          <div className="absolute inset-0 flex items-center justify-center z-10 bg-white bg-opacity-80">
            <div className="flex flex-col items-center gap-3">
              <div className="w-8 h-8 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm text-gray-500">Loading chart data…</p>
            </div>
          </div>
        )}

        <div ref={chartContainerRef} className="w-full h-full" />
      </div>
    </div>
  );
}
