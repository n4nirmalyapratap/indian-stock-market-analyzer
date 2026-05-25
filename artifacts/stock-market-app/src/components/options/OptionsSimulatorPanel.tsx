import { useState, useEffect, useRef, useCallback } from "react";
import { fetchApi } from "@/lib/api";
import { useTheme } from "@/context/ThemeContext";
import {
  Play, Pause, RefreshCw, Activity, AlertTriangle,
  RotateCcw, TrendingUp, TrendingDown,
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer,
} from "recharts";

interface Leg {
  id: string;
  action: "buy" | "sell";
  option_type: "call" | "put";
  strike: number;
  premium: number;
  lots: number;
  lot_size: number;
  iv: number;
}
interface SpotInfo { spot: number; hv30: number; hv30_pct: number; lot_size: number; atm: number; }
interface SimSlice { dte: number; T: number; payoffs: number[]; }
interface SimResult {
  spots: number[];
  slices: SimSlice[];
  breakevens: number[];
  S: number;
  T_current: number;
  iv_shift: number;
}

function post<T = any>(path: string, body: unknown): Promise<T> {
  return fetchApi<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function fmtINR(v: number | undefined): string {
  if (v === undefined || !isFinite(v)) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "−" : v > 0 ? "+" : "";
  if (abs >= 1e7) return `${sign}₹${(abs / 1e7).toFixed(2)}Cr`;
  if (abs >= 1e5) return `${sign}₹${(abs / 1e5).toFixed(2)}L`;
  return `${sign}₹${abs.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

export default function OptionsSimulatorPanel({
  legs, spotInfo, T, sigma,
}: {
  legs: Leg[];
  spotInfo: SpotInfo | null;
  T: number;
  sigma: number;
}) {
  const { theme } = useTheme();
  const isDark = theme === "dark";

  const [simResult, setSimResult]   = useState<SimResult | null>(null);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState("");
  const [sliceIdx, setSliceIdx]     = useState(0);
  const [isPlaying, setIsPlaying]   = useState(false);
  const [ivShift, setIvShift]       = useState(0);
  const [playSpeed, setPlaySpeed]   = useState(100);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const prevKey     = useRef("");

  const runSim = useCallback(async (shift: number) => {
    if (!legs.length || !spotInfo) return;
    setLoading(true);
    setError("");
    setIsPlaying(false);
    setSliceIdx(0);
    try {
      const result = await post<SimResult>("/options/simulate", {
        legs: legs.map(l => ({
          action: l.action, option_type: l.option_type,
          strike: l.strike, premium: l.premium,
          lots: l.lots, lot_size: l.lot_size, iv: l.iv,
        })),
        S: spotInfo.spot,
        T_current: Math.max(T, 1) / 365,
        sigma,
        r: 0.07,
        iv_shift: shift / 100,
        time_steps: 40,
        spot_range_pct: 0.22,
      });
      setSimResult(result);
      setSliceIdx(0);
    } catch (e: any) {
      setError(e?.message || "Simulation failed");
    } finally {
      setLoading(false);
    }
  }, [legs, spotInfo, T, sigma]);

  useEffect(() => {
    const key = JSON.stringify(legs.map(l => [l.action, l.option_type, l.strike, l.lots, l.iv]));
    if (key !== prevKey.current && legs.length > 0 && spotInfo) {
      prevKey.current = key;
      runSim(ivShift);
    }
  }, [legs, spotInfo]); // eslint-disable-line

  useEffect(() => {
    if (!isPlaying || !simResult) return;
    const total = simResult.slices.length;
    intervalRef.current = setInterval(() => {
      setSliceIdx(prev => {
        if (prev >= total - 1) { setIsPlaying(false); return prev; }
        return prev + 1;
      });
    }, playSpeed);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [isPlaying, simResult, playSpeed]);

  const spots        = simResult?.spots ?? [];
  const expirySlice  = simResult?.slices[simResult.slices.length - 1];
  const currentSlice = simResult?.slices[sliceIdx];
  const totalSlices  = simResult?.slices.length ?? 0;
  const currentDte   = currentSlice?.dte ?? T;
  const dteProgress  = totalSlices > 1 ? (sliceIdx / (totalSlices - 1)) * 100 : 0;

  const chartData = spots.map((s, i) => ({
    spot: s,
    expiry:  expirySlice?.payoffs[i]  ?? 0,
    current: currentSlice?.payoffs[i] ?? 0,
  }));

  const nearestIdx = spots.length
    ? spots.reduce((best, s, i) =>
        Math.abs(s - (spotInfo?.spot ?? 0)) < Math.abs(spots[best] - (spotInfo?.spot ?? 0)) ? i : best, 0)
    : 0;

  const pnlAtSpot    = currentSlice?.payoffs[nearestIdx] ?? 0;
  const expiryAtSpot = expirySlice?.payoffs[nearestIdx]  ?? 0;
  const maxProfit    = expirySlice ? Math.max(...expirySlice.payoffs) : 0;
  const maxLoss      = expirySlice ? Math.min(...expirySlice.payoffs) : 0;
  const pop          = expirySlice
    ? Math.round((expirySlice.payoffs.filter(p => p > 0).length / expirySlice.payoffs.length) * 100)
    : 0;
  const nextSlice    = simResult?.slices[Math.min(sliceIdx + 1, totalSlices - 1)];
  const thetaDay     = nextSlice ? (nextSlice.payoffs[nearestIdx] - pnlAtSpot) : 0;

  const bg      = isDark ? "bg-slate-800"      : "bg-white";
  const border  = isDark ? "border-slate-700"  : "border-gray-200";
  const text    = isDark ? "text-slate-200"    : "text-gray-800";
  const muted   = isDark ? "text-slate-500"    : "text-gray-400";
  const subtext = isDark ? "text-slate-400"    : "text-gray-500";
  const chartGrid = isDark ? "#1e293b"         : "#f0f0f0";
  const chartTick = { fontSize: 10, fill: isDark ? "#64748b" : "#6b7280" };
  const tipStyle  = {
    fontSize: 11, borderRadius: 6,
    backgroundColor: isDark ? "#1e293b" : "#fff",
    border: `1px solid ${isDark ? "#334155" : "#e5e7eb"}`,
    color: isDark ? "#e2e8f0" : "#111827",
  };

  if (!legs.length) {
    return (
      <div className={`flex flex-col items-center justify-center h-full gap-3 ${muted}`}>
        <Activity className="w-10 h-10 opacity-20" />
        <p className={`text-sm font-medium ${subtext}`}>No strategy loaded</p>
        <p className="text-xs opacity-60 text-center px-8">Build a strategy and run analysis, then the time simulator will auto-load</p>
      </div>
    );
  }

  return (
    <div className={`flex flex-col h-full overflow-hidden`}>

      {/* ── Controls bar ───────────────────────────────────────────────────────── */}
      <div className={`shrink-0 flex items-center gap-3 px-3 py-2 border-b ${border} ${isDark ? "bg-slate-900/30" : "bg-gray-50/60"}`}>
        {/* IV shift */}
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className={`text-[9px] font-bold uppercase tracking-widest shrink-0 ${muted}`}>IV</span>
          <input
            type="range" min={-40} max={40} step={2} value={ivShift}
            onChange={e => setIvShift(Number(e.target.value))}
            onMouseUp={() => runSim(ivShift)}
            onTouchEnd={() => runSim(ivShift)}
            className="flex-1 accent-indigo-500 cursor-pointer h-1"
          />
          <span className={`text-[10px] font-mono font-bold w-10 text-right shrink-0
            ${ivShift > 0 ? "text-rose-400" : ivShift < 0 ? "text-emerald-400" : subtext}`}>
            {ivShift > 0 ? "+" : ""}{ivShift}%
          </span>
        </div>
        {/* Speed */}
        <div className={`flex items-center gap-0.5 shrink-0`}>
          {[{ l: "0.5×", ms: 200 }, { l: "1×", ms: 100 }, { l: "2×", ms: 50 }, { l: "4×", ms: 25 }].map(s => (
            <button key={s.ms} onClick={() => setPlaySpeed(s.ms)}
              className={`text-[9px] font-bold px-1.5 py-0.5 rounded transition
                ${playSpeed === s.ms
                  ? "bg-indigo-600 text-white"
                  : isDark ? "text-slate-500 hover:text-slate-300" : "text-gray-400 hover:text-gray-600"}`}>
              {s.l}
            </button>
          ))}
        </div>
        {/* Run */}
        <button
          onClick={() => runSim(ivShift)}
          disabled={loading || !spotInfo}
          className="flex items-center gap-1.5 px-3 py-1 rounded-lg text-[11px] font-bold text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 transition shrink-0"
        >
          {loading
            ? <RefreshCw className="w-3 h-3 animate-spin" />
            : <Activity className="w-3 h-3" />}
          {loading ? "Computing…" : "Run"}
        </button>
        {error && <span className="text-rose-400 text-[10px] flex items-center gap-1 shrink-0"><AlertTriangle className="w-3 h-3" />{error}</span>}
      </div>

      {/* ── Stats strip — only when result available ────────────────────────── */}
      {simResult && (
        <div className={`shrink-0 flex items-center gap-0 border-b ${border} ${isDark ? "bg-slate-900/20" : "bg-gray-50/40"}`}>
          {[
            { label: "T+0 at Spot", value: fmtINR(pnlAtSpot),    color: pnlAtSpot    >= 0 ? "text-emerald-400" : "text-rose-400" },
            { label: "Expiry P&L",   value: fmtINR(expiryAtSpot), color: expiryAtSpot >= 0 ? "text-emerald-400" : "text-rose-400" },
            { label: "Max Profit",   value: maxProfit > 1e8 ? "∞" : fmtINR(maxProfit), color: "text-emerald-400" },
            { label: "Max Loss",     value: maxLoss < -1e8 ? "−∞" : fmtINR(maxLoss),   color: "text-rose-400" },
            { label: "PoP",          value: `${pop}%`, color: pop >= 50 ? "text-indigo-400" : "text-amber-400" },
            { label: "Theta/day",    value: fmtINR(thetaDay),     color: thetaDay >= 0 ? "text-emerald-400" : "text-rose-400" },
          ].map((s, i, arr) => (
            <div key={s.label}
              className={`flex-1 flex flex-col items-center justify-center py-1.5 ${i < arr.length - 1 ? `border-r ${border}` : ""}`}>
              <span className={`text-[8px] font-semibold uppercase tracking-wide ${muted}`}>{s.label}</span>
              <span className={`text-[11px] font-bold font-mono ${s.color}`}>{s.value}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Chart — flex-1, fills all remaining space ──────────────────────── */}
      {simResult ? (
        <div className="flex-1 min-h-0 flex flex-col">
          {/* Chart title row */}
          <div className={`shrink-0 flex items-center justify-between px-3 pt-2 pb-0`}>
            <div className={`text-[10px] font-semibold flex items-center gap-2 ${subtext}`}>
              <span className="flex items-center gap-1">
                <span className="inline-block w-5 h-0.5 bg-orange-400 rounded" />
                <span>Today (DTE <span className={`font-mono font-bold text-orange-400`}>{currentDte}d</span>)</span>
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block w-5 border-t-2 border-dashed border-indigo-500" />
                <span className={isDark ? "text-slate-500" : "text-gray-400"}>At Expiry</span>
              </span>
              {ivShift !== 0 && (
                <span className={`font-bold ${ivShift > 0 ? "text-rose-400" : "text-emerald-400"}`}>
                  IV {ivShift > 0 ? "+" : ""}{ivShift}%
                </span>
              )}
            </div>
            <div className={`flex items-center gap-1 ${muted} text-[9px]`}>
              {simResult.breakevens.map((be, i) => (
                <span key={i} className="font-mono text-emerald-500 font-bold">
                  BE ₹{be.toLocaleString("en-IN")}
                </span>
              ))}
            </div>
          </div>
          {/* Recharts */}
          <div className="flex-1 min-h-0">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 4, right: 16, left: 4, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={chartGrid} />
                <XAxis
                  dataKey="spot"
                  tickFormatter={(v: number) => `₹${(v / 1000).toFixed(0)}k`}
                  tick={chartTick}
                />
                <YAxis
                  tickFormatter={(v: number) =>
                    Math.abs(v) >= 1e5 ? `${(v / 1e5).toFixed(1)}L` : `${(v / 1000).toFixed(0)}k`}
                  tick={chartTick}
                  width={46}
                />
                <Tooltip
                  formatter={(v: number, name: string) => [
                    fmtINR(v),
                    name === "expiry" ? "At Expiry" : `DTE ${currentDte}d`,
                  ]}
                  labelFormatter={(l: number) => `Spot: ₹${Number(l).toLocaleString("en-IN")}`}
                  contentStyle={tipStyle}
                />
                <ReferenceLine y={0} stroke={isDark ? "#475569" : "#d1d5db"} strokeWidth={1.5} />
                {spotInfo && (
                  <ReferenceLine x={spotInfo.spot} stroke="#f97316" strokeDasharray="4 2"
                    label={{ value: "Spot", fill: "#f97316", fontSize: 9, position: "top" }} />
                )}
                {(simResult.breakevens || []).map((be, i) => (
                  <ReferenceLine key={i} x={be} stroke="#10b981" strokeDasharray="3 3"
                    label={{ value: "BE", fill: "#059669", fontSize: 9 }} />
                ))}
                <Line type="monotone" dataKey="expiry" stroke="#6366f1" strokeWidth={1.5}
                  dot={false} strokeDasharray="6 3" activeDot={{ r: 3 }} />
                <Line type="monotone" dataKey="current" stroke="#f97316" strokeWidth={2.5}
                  dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : !loading ? (
        <div className={`flex-1 flex flex-col items-center justify-center gap-2 ${muted}`}>
          <Activity className="w-8 h-8 opacity-20" />
          <p className={`text-xs font-medium ${subtext}`}>Click "Run" to animate Theta decay</p>
          <p className="text-[10px] opacity-60">Day-by-day P&amp;L with live IV shock analysis</p>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <RefreshCw className="w-6 h-6 text-indigo-400 animate-spin" />
        </div>
      )}

      {/* ── Time scrubber — compact bottom strip ───────────────────────────── */}
      {simResult && (
        <div className={`shrink-0 border-t ${border} px-3 py-2 ${isDark ? "bg-slate-900/30" : "bg-gray-50/60"}`}>
          <div className="flex items-center gap-2">
            {/* Play/Pause */}
            <button
              onClick={() => {
                if (sliceIdx >= totalSlices - 1) { setSliceIdx(0); setIsPlaying(true); return; }
                setIsPlaying(p => !p);
              }}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-bold text-white bg-indigo-600 hover:bg-indigo-700 transition shrink-0"
            >
              {isPlaying
                ? <><Pause className="w-3 h-3" />Pause</>
                : <><Play className="w-3 h-3" />{sliceIdx >= totalSlices - 1 ? "Replay" : "Play"}</>
              }
            </button>
            {/* Reset */}
            <button
              onClick={() => { setIsPlaying(false); setSliceIdx(0); }}
              className={`p-1 rounded transition ${isDark ? "text-slate-500 hover:text-slate-300" : "text-gray-400 hover:text-gray-600"}`}
              title="Reset"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
            {/* Slider + labels */}
            <div className="flex-1 flex flex-col gap-0.5">
              <div className={`h-1.5 rounded-full overflow-hidden ${isDark ? "bg-slate-700" : "bg-gray-200"} cursor-pointer relative`}
                onClick={e => {
                  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                  const pct = (e.clientX - rect.left) / rect.width;
                  setIsPlaying(false);
                  setSliceIdx(Math.round(pct * (totalSlices - 1)));
                }}>
                <div className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-orange-400 transition-all duration-75"
                  style={{ width: `${dteProgress}%` }} />
              </div>
              <div className={`flex justify-between text-[9px] font-mono ${muted}`}>
                <span className="text-indigo-400">DTE {simResult.slices[0]?.dte ?? T}d</span>
                <span className={`font-bold text-[10px] ${pnlAtSpot >= 0 ? "text-emerald-400" : "text-rose-400"} flex items-center gap-0.5`}>
                  {pnlAtSpot >= 0
                    ? <TrendingUp className="w-3 h-3" />
                    : <TrendingDown className="w-3 h-3" />}
                  {fmtINR(pnlAtSpot)} at spot
                </span>
                <span className="text-orange-400">Expiry</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
