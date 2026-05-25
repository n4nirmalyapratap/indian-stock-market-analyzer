import { useState, useEffect, useRef, useCallback } from "react";
import { fetchApi } from "@/lib/api";
import { useTheme } from "@/context/ThemeContext";
import { Play, RefreshCw, Activity, AlertTriangle, RotateCcw } from "lucide-react";
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
  legs,
  spotInfo,
  T,
  sigma,
}: {
  legs: Leg[];
  spotInfo: SpotInfo | null;
  T: number;
  sigma: number;
}) {
  const { theme } = useTheme();
  const isDark = theme === "dark";

  const [simResult, setSimResult] = useState<SimResult | null>(null);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState("");
  const [sliceIdx, setSliceIdx]   = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [ivShift, setIvShift]     = useState(0);
  const [playSpeed, setPlaySpeed] = useState(100);
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

  // Auto-run whenever legs change
  useEffect(() => {
    const key = JSON.stringify(legs.map(l => [l.action, l.option_type, l.strike, l.lots, l.iv]));
    if (key !== prevKey.current && legs.length > 0 && spotInfo) {
      prevKey.current = key;
      runSim(ivShift);
    }
  }, [legs, spotInfo]); // eslint-disable-line

  // Play animation
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

  // Derived
  const spots        = simResult?.spots ?? [];
  const expirySlice  = simResult?.slices[simResult.slices.length - 1];
  const currentSlice = simResult?.slices[sliceIdx];
  const totalSlices  = simResult?.slices.length ?? 0;
  const currentDte   = currentSlice?.dte ?? T;

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
  const nextSlice  = simResult?.slices[Math.min(sliceIdx + 1, totalSlices - 1)];
  const thetaDay   = nextSlice ? (nextSlice.payoffs[nearestIdx] - pnlAtSpot) : 0;

  // Styling
  const card       = isDark ? "bg-slate-800 border-slate-700" : "bg-white border-gray-200";
  const text       = isDark ? "text-slate-200" : "text-gray-800";
  const muted      = isDark ? "text-slate-400" : "text-gray-500";
  const chartGrid  = isDark ? "#1e293b" : "#f0f0f0";
  const chartTick  = { fontSize: 10, fill: isDark ? "#64748b" : "#6b7280" };
  const tipStyle   = {
    fontSize: 11, borderRadius: 8,
    backgroundColor: isDark ? "#1e293b" : "#fff",
    border: `1px solid ${isDark ? "#334155" : "#e5e7eb"}`,
    color: isDark ? "#e2e8f0" : "#111827",
  };

  if (!legs.length) {
    return (
      <div className={`flex flex-col items-center justify-center h-[480px] gap-4 ${muted}`}>
        <Activity className="w-14 h-14 opacity-20" />
        <div className="text-center">
          <p className={`font-semibold text-sm ${text}`}>No strategy loaded</p>
          <p className="text-xs mt-1 opacity-70">Build a strategy in the Strategy &amp; Payoff tab, then come back here</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">

      {/* ── Controls bar ──────────────────────────────────────────────────────── */}
      <div className={`rounded-2xl border ${card} p-4`}>
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex-1 min-w-[220px]">
            <div className="flex items-center justify-between mb-1">
              <label className={`text-xs font-semibold ${muted} uppercase tracking-wide`}>IV Shift</label>
              <span className={`text-xs font-bold font-mono px-2 py-0.5 rounded transition
                ${ivShift > 0 ? "bg-rose-100 text-rose-700" : ivShift < 0 ? "bg-emerald-100 text-emerald-700" : isDark ? "bg-slate-700 text-slate-300" : "bg-gray-100 text-gray-600"}`}>
                {ivShift > 0 ? "+" : ""}{ivShift}%
              </span>
            </div>
            <input
              type="range" min={-40} max={40} step={2} value={ivShift}
              onChange={e => setIvShift(Number(e.target.value))}
              onMouseUp={() => runSim(ivShift)}
              onTouchEnd={() => runSim(ivShift)}
              className="w-full accent-indigo-600 cursor-pointer"
            />
            <div className={`flex justify-between text-[10px] mt-0.5 ${muted}`}>
              <span>−40% (crush)</span><span>Flat</span><span>+40% (spike)</span>
            </div>
          </div>
          <button
            onClick={() => runSim(ivShift)}
            disabled={loading || !spotInfo}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 transition shadow-sm shrink-0"
          >
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Activity className="w-4 h-4" />}
            {loading ? "Computing…" : "Run Simulation"}
          </button>
        </div>
        {error && (
          <p className="mt-2 text-sm text-red-500 flex items-center gap-1.5">
            <AlertTriangle className="w-4 h-4" /> {error}
          </p>
        )}
      </div>

      {/* ── Stats strip ──────────────────────────────────────────────────────── */}
      {simResult && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {[
            { label: "T+0 P&L at Spot", value: fmtINR(pnlAtSpot),    color: pnlAtSpot    >= 0 ? "text-emerald-600" : "text-rose-600" },
            { label: "Expiry P&L",       value: fmtINR(expiryAtSpot), color: expiryAtSpot >= 0 ? "text-emerald-600" : "text-rose-600" },
            { label: "Max Profit",       value: maxProfit > 1e8 ? "Unlimited" : fmtINR(maxProfit), color: "text-emerald-600" },
            { label: "Max Loss",         value: maxLoss < -1e8 ? "Unlimited" : fmtINR(maxLoss),    color: "text-rose-600" },
            { label: "Prob. of Profit",  value: `${pop}%`, color: pop >= 50 ? "text-indigo-600" : "text-amber-600" },
          ].map(s => (
            <div key={s.label} className={`rounded-xl border ${card} p-3`}>
              <p className={`text-[10px] font-semibold uppercase tracking-wide ${muted} mb-0.5`}>{s.label}</p>
              <p className={`text-base font-bold ${s.color}`}>{s.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* ── Payoff chart ─────────────────────────────────────────────────────── */}
      {simResult && (
        <div className={`rounded-2xl border ${card} p-4`}>
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <div>
              <p className={`text-sm font-bold ${text}`}>Payoff Diagram</p>
              <p className={`text-xs ${muted}`}>
                Orange curve = DTE <span className="font-semibold text-orange-500">{currentDte}d</span>
                {" · "}
                Indigo dashed = At expiry
                {ivShift !== 0 && (
                  <span className={`ml-2 font-semibold ${ivShift > 0 ? "text-rose-500" : "text-emerald-500"}`}>
                    · IV {ivShift > 0 ? "+" : ""}{ivShift}%
                  </span>
                )}
              </p>
            </div>
            <div className={`flex items-center gap-4 text-[10px] font-semibold ${muted}`}>
              <span className="flex items-center gap-1.5">
                <span className="w-6 h-0.5 bg-orange-400 inline-block rounded" /> Today (T+0)
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-5 h-0.5 bg-indigo-500 inline-block" style={{ borderTop: "2px dashed #6366f1", background: "none" }} />
                <span className="w-5 h-px border-t-2 border-dashed border-indigo-500 inline-block" /> Expiry
              </span>
            </div>
          </div>

          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData} margin={{ top: 5, right: 20, left: 8, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={chartGrid} />
              <XAxis
                dataKey="spot"
                tickFormatter={(v: number) => `₹${(v / 1000).toFixed(0)}k`}
                tick={chartTick}
              />
              <YAxis
                tickFormatter={(v: number) =>
                  Math.abs(v) >= 1e5 ? `${(v / 1e5).toFixed(1)}L` : `${(v / 1000).toFixed(0)}k`
                }
                tick={chartTick}
                width={54}
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
      )}

      {/* ── Time scrubber / animation ─────────────────────────────────────────── */}
      {simResult && (
        <div className={`rounded-2xl border ${card} p-4`}>
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <div>
              <p className={`text-sm font-bold ${text}`}>Time Scrubber — Theta Decay</p>
              <p className={`text-xs ${muted}`}>
                DTE: <span className="font-mono font-bold text-indigo-500">{currentDte}d</span>
                {" · "}
                Daily Theta: <span className={`font-mono font-bold ${thetaDay >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
                  {fmtINR(thetaDay)}/day
                </span>
              </p>
            </div>
            <div className="flex items-center gap-1.5">
              <span className={`text-[10px] ${muted} font-semibold mr-1`}>Speed</span>
              {[{ label: "0.5×", ms: 200 }, { label: "1×", ms: 100 }, { label: "2×", ms: 50 }, { label: "4×", ms: 25 }].map(s => (
                <button key={s.ms} onClick={() => setPlaySpeed(s.ms)}
                  className={`text-[10px] font-bold px-2 py-0.5 rounded border transition
                    ${playSpeed === s.ms
                      ? "bg-indigo-600 text-white border-indigo-600"
                      : isDark ? "border-slate-600 text-slate-400 hover:border-indigo-400" : "border-gray-200 text-gray-500 hover:border-indigo-400"}`}>
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                if (sliceIdx >= totalSlices - 1) { setSliceIdx(0); setIsPlaying(true); return; }
                setIsPlaying(p => !p);
              }}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-700 transition shadow-sm shrink-0"
            >
              {isPlaying
                ? <><span className="flex gap-0.5 items-center"><span className="w-1 h-3.5 bg-white rounded-sm inline-block" /><span className="w-1 h-3.5 bg-white rounded-sm inline-block" /></span>Pause</>
                : <><Play className="w-3.5 h-3.5" />{sliceIdx >= totalSlices - 1 ? "Replay" : "Play"}</>
              }
            </button>

            <button
              onClick={() => { setIsPlaying(false); setSliceIdx(0); }}
              className={`p-2 rounded-xl border transition ${isDark ? "border-slate-600 text-slate-400 hover:text-white" : "border-gray-200 text-gray-400 hover:text-gray-700"}`}
              title="Reset to start"
            >
              <RotateCcw className="w-4 h-4" />
            </button>

            <div className="flex-1 flex flex-col gap-1">
              <input
                type="range" min={0} max={Math.max(0, totalSlices - 1)} value={sliceIdx}
                onChange={e => { setIsPlaying(false); setSliceIdx(Number(e.target.value)); }}
                className="w-full accent-indigo-600 cursor-pointer"
              />
              <div className={`flex justify-between text-[10px] ${muted}`}>
                <span>Now (DTE {simResult.slices[0]?.dte ?? T}d)</span>
                <span>Expiry (DTE 0)</span>
              </div>
            </div>
          </div>

          <div className={`mt-3 h-2 rounded-full overflow-hidden ${isDark ? "bg-slate-700" : "bg-gray-100"}`}>
            <div
              className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-orange-400 transition-all duration-75"
              style={{ width: `${totalSlices > 1 ? (sliceIdx / (totalSlices - 1)) * 100 : 0}%` }}
            />
          </div>
        </div>
      )}

      {/* ── Breakevens ─────────────────────────────────────────────────────────── */}
      {simResult && simResult.breakevens.length > 0 && (
        <div className={`rounded-xl border ${card} px-4 py-3 flex flex-wrap gap-4 items-center`}>
          <span className={`text-xs font-semibold ${muted} uppercase tracking-wide`}>Breakevens</span>
          {simResult.breakevens.map((be, i) => (
            <span key={i} className="text-sm font-bold font-mono text-emerald-600">
              ₹{be.toLocaleString("en-IN")}
            </span>
          ))}
          <span className={`ml-auto text-xs ${muted}`}>
            {legs.length} leg{legs.length !== 1 ? "s" : ""} · IV {ivShift > 0 ? "+" : ""}{ivShift}% · DTE {currentDte}d
          </span>
        </div>
      )}

      {!simResult && !loading && (
        <div className={`flex flex-col items-center justify-center h-[320px] gap-3 ${muted}`}>
          <Activity className="w-10 h-10 opacity-20" />
          <p className="text-sm font-medium">Click "Run Simulation" to animate the payoff</p>
          <p className="text-xs opacity-70">Day-by-day Theta decay with live IV shock analysis</p>
        </div>
      )}
    </div>
  );
}
