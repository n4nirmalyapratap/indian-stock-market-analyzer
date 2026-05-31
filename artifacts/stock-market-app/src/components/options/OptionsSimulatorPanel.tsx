import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { fetchApi } from "@/lib/api";
import { useTheme } from "@/context/ThemeContext";
import {
  Play, Pause, RefreshCw, Activity, AlertTriangle,
  RotateCcw, TrendingUp, TrendingDown, Trash2, Plus, X
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

interface SpotInfo {
  spot: number;
  hv30: number;
  hv30_pct: number;
  lot_size: number;
  atm: number;
}

interface ChainRow {
  strike: number;
  lastPrice: number;
  bid: number;
  ask: number;
  iv: number;
  oi: number;
  volume: number;
  inTheMoney: boolean;
  change?: number;
  pChange?: number;
}

interface SimSlice {
  dte: number;
  T: number;
  payoffs: number[];
}

interface SimResult {
  spots: number[];
  slices: SimSlice[];
  breakevens: number[];
  S: number;
  T_current: number;
  iv_shift: number;
}

// ── Client-side Black-Scholes Greeks ──────────────────────────────────────────
function ncdf(x: number): number {
  const a = [0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429];
  const sign = x >= 0 ? 1 : -1;
  const t = 1 / (1 + 0.2316419 * Math.abs(x));
  const poly = t * (a[0] + t * (a[1] + t * (a[2] + t * (a[3] + t * a[4]))));
  const val = 1 - poly * Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
  return sign === 1 ? val : 1 - val;
}

function bsPrice(S: number, K: number, T: number, r: number, sigma: number, type: "call" | "put"): number {
  if (T <= 0) return Math.max(0, type === "call" ? S - K : K - S);
  const sqrtT = Math.sqrt(T);
  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrtT);
  const d2 = d1 - sigma * sqrtT;
  if (type === "call") return S * ncdf(d1) - K * Math.exp(-r * T) * ncdf(d2);
  return K * Math.exp(-r * T) * ncdf(-d2) - S * ncdf(-d1);
}

function strikeStep(spot: number): number {
  if (spot < 500) return 5;
  if (spot < 2000) return 10;
  if (spot < 5000) return 25;
  if (spot < 15000) return 50;
  if (spot < 50000) return 100;
  return 500;
}

function generateSyntheticChain(
  spot: number, hv: number, T_years: number, halfDepth = 22
): { calls: ChainRow[]; puts: ChainRow[] } {
  const step = strikeStep(spot);
  const atm = Math.round(spot / step) * step;
  const r = 0.07;
  const rnd = (v: number) => Math.round(v * 20) / 20;
  const calls: ChainRow[] = [];
  const puts: ChainRow[] = [];
  for (let i = -halfDepth; i <= halfDepth; i++) {
    const K = atm + i * step;
    if (K <= 0) continue;
    const mono = Math.abs(K - atm) / spot;
    const iv_c = Math.max(0.05, hv + 0.60 * mono);
    const iv_p = Math.max(0.05, hv + 0.15 * mono);
    const cp = bsPrice(spot, K, T_years, r, iv_c, "call");
    const pp = bsPrice(spot, K, T_years, r, iv_p, "put");
    const sp = (v: number) => Math.max(0.05, v * 0.004);
    const oi = Math.max(0, Math.round(900_000 * Math.exp(-5 * mono)));
    calls.push({ strike: K, lastPrice: rnd(cp), bid: rnd(cp - sp(cp)), ask: rnd(cp + sp(cp)), iv: iv_c, oi, volume: Math.round(oi * 0.12), inTheMoney: K < spot });
    puts.push({ strike: K, lastPrice: rnd(pp), bid: rnd(pp - sp(pp)), ask: rnd(pp + sp(pp)), iv: iv_p, oi, volume: Math.round(oi * 0.12), inTheMoney: K > spot });
  }
  return { calls, puts };
}

// ── Client-side Debounce Helper ────────────────────────────────────────────────
function debounce<T extends (...args: any[]) => void>(func: T, wait: number): T {
  let timeout: any = null;
  return function(this: any, ...args: any[]) {
    if (timeout) clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  } as any;
}

// ── VirtualList Component ──────────────────────────────────────────────────────
function VirtualList<T>({
  items,
  height,
  itemHeight,
  renderItem,
}: {
  items: T[];
  height: number;
  itemHeight: number;
  renderItem: (item: T, index: number) => React.ReactNode;
}) {
  const [scrollTop, setScrollTop] = useState(0);

  const totalHeight = items.length * itemHeight;
  const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - 2);
  const endIndex = Math.min(items.length - 1, Math.floor((scrollTop + height) / itemHeight) + 2);

  const visibleItems = items.slice(startIndex, endIndex + 1);
  const offsetY = startIndex * itemHeight;

  return (
    <div
      onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
      className="overflow-y-auto relative h-full w-full"
      style={{ height }}
    >
      <div style={{ height: totalHeight, width: "100%", position: "relative" }}>
        <div style={{ transform: `translateY(${offsetY}px)`, position: "absolute", left: 0, right: 0, top: 0 }}>
          {visibleItems.map((item, index) => renderItem(item, startIndex + index))}
        </div>
      </div>
    </div>
  );
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

function fmtPx(n: number | undefined): string {
  if (n === undefined || isNaN(n)) return "—";
  return n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function OptionsSimulatorPanel({
  legs,
  setLegs,
  spotInfo,
  T,
  sigma,
  symbol,
  setSymbol,
  expiryDate,
  setExpiryDate,
  NSE_EXPIRIES,
  rightTab,
  setRightTab,
}: {
  legs: Leg[];
  setLegs: React.Dispatch<React.SetStateAction<Leg[]>>;
  spotInfo: SpotInfo | null;
  T: number;
  sigma: number;
  symbol: string;
  setSymbol: (s: string) => void;
  expiryDate: string;
  setExpiryDate: (e: string) => void;
  NSE_EXPIRIES: Array<{ date: string; label: string; monthly: boolean }>;
  rightTab: "payoff" | "simulator";
  setRightTab: (t: "payoff" | "simulator") => void;
}) {
  const { theme } = useTheme();
  const isDark = theme === "dark";

  const [simResult, setSimResult] = useState<SimResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [ivShift, setIvShift] = useState(0);
  const [playSpeed, setPlaySpeed] = useState(100);
  const [isPlaying, setIsPlaying] = useState(false);
  const intervalRef = useRef<any>(null);

  // Simulated Time global state (UNIX timestamp in seconds)
  const [simulatedTime, setSimulatedTime] = useState<number>(0);

  // Option Chain local state
  const [chainLoading, setChainLoading] = useState(false);
  const [calls, setCalls] = useState<ChainRow[]>([]);
  const [puts, setPuts] = useState<ChainRow[]>([]);
  const [chainSource, setChainSource] = useState("");

  const getSimRange = useCallback(() => {
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 9, 15, 0);
    const [y, m, d] = expiryDate.split("-").map(Number);
    const exp = new Date(y, m - 1, d, 15, 30, 0);
    if (start.getTime() >= exp.getTime()) {
      start.setTime(exp.getTime() - 24 * 60 * 60 * 1000);
    }
    return {
      start: Math.floor(start.getTime() / 1000),
      expiry: Math.floor(exp.getTime() / 1000),
    };
  }, [expiryDate]);

  const { start, expiry } = useMemo(() => getSimRange(), [getSimRange]);

  // Reset simulatedTime when range changes
  useEffect(() => {
    setSimulatedTime(start);
  }, [start]);

  // Handle Play / Pause animation
  useEffect(() => {
    if (!isPlaying) return;
    intervalRef.current = setInterval(() => {
      setSimulatedTime(prev => {
        const next = prev + 15 * 60; // Step by 15 minutes
        if (next >= expiry) {
          setIsPlaying(false);
          return expiry;
        }
        return next;
      });
    }, playSpeed);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [isPlaying, playSpeed, expiry]);

  // DTE Left calculation (simulatedTime -> DTE)
  const dteRemaining = useMemo(() => {
    if (!simulatedTime) return T;
    return Math.max(0, (expiry - simulatedTime) / 86400);
  }, [simulatedTime, expiry, T]);

  // Fetch Option Chain data
  const fetchChainData = useCallback(async (sym: string, exp: string) => {
    if (!sym || !spotInfo) return;
    setChainLoading(true);
    try {
      const url = exp
        ? `/options/chain/${sym}?expiry=${encodeURIComponent(exp)}`
        : `/options/chain/${sym}`;
      const data = await fetchApi<any>(url);
      const chainData = data.chain || {};
      const firstKey = exp && chainData[exp] ? exp : (data.expiries?.[0] || "");
      const entry = chainData[firstKey] || { calls: [], puts: [] };
      setCalls(entry.calls || []);
      setPuts(entry.puts || []);
      setChainSource(data.source || "Live");
    } catch (err) {
      const T_y = Math.max(T, 1) / 365;
      const { calls: sc, puts: sp } = generateSyntheticChain(spotInfo.spot, spotInfo.hv30, T_y);
      setCalls(sc);
      setPuts(sp);
      setChainSource("Synthetic · BS");
    } finally {
      setChainLoading(false);
    }
  }, [spotInfo, T]);

  useEffect(() => {
    fetchChainData(symbol, expiryDate);
  }, [symbol, expiryDate, spotInfo]);

  // Debounced backend simulation recalculation
  const runSimDebounced = useCallback(
    debounce(async (currentDte: number, currentIvShift: number) => {
      if (!legs.length || !spotInfo) return;
      setLoading(true);
      try {
        const result = await post<SimResult>("/options/simulate", {
          legs: legs.map(l => ({
            action: l.action,
            option_type: l.option_type,
            strike: l.strike,
            premium: l.premium,
            lots: l.lots,
            lot_size: l.lot_size,
            iv: l.iv,
          })),
          S: spotInfo.spot,
          T_current: Math.max(currentDte, 0.001) / 365,
          sigma,
          r: 0.07,
          iv_shift: currentIvShift / 100,
          time_steps: 40,
          spot_range_pct: 0.22,
        });
        setSimResult(result);
      } catch (e: any) {
        console.error("Simulation sync failed", e);
      } finally {
        setLoading(false);
      }
    }, 200),
    [legs, spotInfo, sigma]
  );

  useEffect(() => {
    if (legs.length > 0 && spotInfo) {
      runSimDebounced(dteRemaining, ivShift);
    }
  }, [legs, dteRemaining, ivShift, spotInfo]);

  // Client-side instant curves for smooth animations
  const chartData = useMemo(() => {
    if (!spotInfo || !legs.length) return [];
    const spots = [];
    const allStrikes = legs.map(l => l.strike);
    const baseMin = spotInfo.spot * (1.0 - 0.22);
    const baseMax = spotInfo.spot * (1.0 + 0.22);
    const spotMin = Math.min(baseMin, Math.min(...allStrikes) * 0.94);
    const spotMax = Math.max(baseMax, Math.max(...allStrikes) * 1.06);

    for (let i = 0; i < 100; i++) {
      spots.push(spotMin + (i * (spotMax - spotMin)) / 99);
    }

    const Tf = dteRemaining / 365.0;
    const r = 0.07;

    return spots.map(s => {
      let t0 = 0.0;
      let exp = 0.0;
      for (const leg of legs) {
        const iv = Math.max(0.01, leg.iv + ivShift / 100);
        const qty = leg.lots * leg.lot_size;
        const mult = leg.action === "buy" ? 1 : -1;

        const price = bsPrice(s, leg.strike, Tf, r, iv, leg.option_type);
        t0 += (price - leg.premium) * qty * mult;

        const expPrice = Math.max(0, leg.option_type === "call" ? s - leg.strike : leg.strike - s);
        exp += (expPrice - leg.premium) * qty * mult;
      }
      return {
        spot: s,
        current: t0,
        expiry: exp,
      };
    });
  }, [legs, spotInfo, dteRemaining, ivShift]);

  // Metrics calculations
  const nearestIdx = useMemo(() => {
    if (!spotInfo || !chartData.length) return 0;
    let best = 0;
    let minDiff = Infinity;
    chartData.forEach((d, i) => {
      const diff = Math.abs(d.spot - spotInfo.spot);
      if (diff < minDiff) {
        minDiff = diff;
        best = i;
      }
    });
    return best;
  }, [chartData, spotInfo]);

  const pnlAtSpot = chartData[nearestIdx]?.current ?? 0;
  const expiryAtSpot = chartData[nearestIdx]?.expiry ?? 0;

  const { maxProfit, maxLoss } = useMemo(() => {
    if (chartData.length === 0) return { maxProfit: 0, maxLoss: 0 };
    const payoffs = chartData.map(d => d.expiry);
    const rawMax = Math.max(...payoffs);
    const rawMin = Math.min(...payoffs);
    const UNLIMITED = 1e8;
    return {
      maxProfit: rawMax > UNLIMITED ? null : rawMax,
      maxLoss: rawMin < -UNLIMITED ? null : rawMin,
    };
  }, [chartData]);

  const pop = useMemo(() => {
    if (chartData.length === 0) return 0;
    const positive = chartData.filter(d => d.expiry > 0).length;
    return Math.round((positive / chartData.length) * 100);
  }, [chartData]);

  const thetaDay = useMemo(() => {
    if (!spotInfo || !legs.length) return 0;
    const currentSpot = spotInfo.spot;
    const TfCurrent = dteRemaining / 365.0;
    const TfNext = Math.max(0, dteRemaining - 1) / 365.0;
    const r = 0.07;

    let currentPnl = 0.0;
    let nextPnl = 0.0;

    for (const leg of legs) {
      const iv = Math.max(0.01, leg.iv + ivShift / 100);
      const qty = leg.lots * leg.lot_size;
      const mult = leg.action === "buy" ? 1 : -1;

      const pCurrent = bsPrice(currentSpot, leg.strike, TfCurrent, r, iv, leg.option_type);
      const pNext = bsPrice(currentSpot, leg.strike, TfNext, r, iv, leg.option_type);

      currentPnl += (pCurrent - leg.premium) * qty * mult;
      nextPnl += (pNext - leg.premium) * qty * mult;
    }
    return nextPnl - currentPnl;
  }, [legs, spotInfo, dteRemaining, ivShift]);

  const localBreakevens = useMemo(() => {
    if (chartData.length < 2) return [];
    const bes = [];
    for (let i = 0; i < chartData.length - 1; i++) {
      const p1 = chartData[i].expiry;
      const p2 = chartData[i + 1].expiry;
      if ((p1 >= 0) !== (p2 >= 0)) {
        const s1 = chartData[i].spot;
        const s2 = chartData[i + 1].spot;
        const denom = p2 - p1;
        if (denom !== 0) {
          bes.push(s1 + (-p1) * (s2 - s1) / denom);
        }
      }
    }
    return bes;
  }, [chartData]);

  const breakevens = simResult?.breakevens || localBreakevens;

  // Add leg helper
  const handleAddLeg = (l: { action: "buy" | "sell"; option_type: "call" | "put"; strike: number; premium: number; iv: number }) => {
    const newLeg: Leg = {
      id: crypto.randomUUID(),
      action: l.action,
      option_type: l.option_type,
      strike: l.strike,
      premium: l.premium || 0,
      lots: 1,
      lot_size: spotInfo?.lot_size ?? 75,
      iv: l.iv || (spotInfo?.hv30 ?? 0.20),
    };
    setLegs(prev => [...prev, newLeg]);
  };

  const updateLeg = (id: string, field: keyof Leg, val: any) => {
    setLegs(prev => prev.map(l => l.id === id ? { ...l, [field]: val } : l));
  };

  const removeLeg = (id: string) => {
    setLegs(prev => prev.filter(l => l.id !== id));
  };

  const formatSimulatedTime = (ts: number) => {
    if (!ts) return "—";
    const d = new Date(ts * 1000);
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const dateStr = `${d.getDate()}-${months[d.getMonth()]}-${d.getFullYear()}`;
    let hrs = d.getHours();
    const mins = String(d.getMinutes()).padStart(2, "0");
    const ampm = hrs >= 12 ? "PM" : "AM";
    hrs = hrs % 12;
    hrs = hrs ? hrs : 12; // 0 -> 12
    return `${dateStr} ${hrs}:${mins} ${ampm}`;
  };

  // Option Chain List generator
  const allStrikes = useMemo(() => {
    return Array.from(new Set([...calls.map(c => c.strike), ...puts.map(p => p.strike)])).sort((a, b) => a - b);
  }, [calls, puts]);

  const callMap = useMemo(() => Object.fromEntries(calls.map(c => [c.strike, c])), [calls]);
  const putMap = useMemo(() => Object.fromEntries(puts.map(p => [p.strike, p])), [puts]);

  const renderChainRow = useCallback((strike: number, index: number) => {
    const call = callMap[strike];
    const put = putMap[strike];
    const isAtm = strike === spotInfo?.atm;
    const isCallItm = strike < (spotInfo?.spot ?? 0);
    const isPutItm = strike > (spotInfo?.spot ?? 0);

    return (
      <div
        key={strike}
        className="grid border-b border-[#2a2e39]/50 hover:bg-[#1e222d] items-center text-xs animate-fade-in"
        style={{
          gridTemplateColumns: "60px 100px 1fr 100px 60px",
          height: 36,
        }}
      >
        {/* Call IV */}
        <div className={`text-right px-3 font-mono text-[10px] text-amber-500/80 h-full flex items-center justify-end ${isCallItm ? "bg-[#1e222d]/30" : ""}`}>
          {call?.iv ? `${(call.iv * 100).toFixed(0)}%` : "—"}
        </div>

        {/* Call LTP with hover action */}
        <div className={`relative flex items-center justify-end w-full h-full group px-3 border-r border-[#2a2e39]/30 ${isCallItm ? "bg-[#1e222d]/30" : ""}`}>
          <span className="group-hover:invisible font-mono text-[11px] font-semibold text-slate-200">
            {call ? fmtPx(call.lastPrice) : "—"}
          </span>
          {call && (
            <div className="hidden group-hover:flex absolute inset-0 items-center justify-center gap-1 bg-[#1c2030]/90 z-10">
              <button
                onClick={() => handleAddLeg({ action: "buy", option_type: "call", strike, premium: call.lastPrice, iv: call.iv })}
                className="bg-[#089981] hover:bg-[#089981]/80 text-white font-bold text-[9px] px-1.5 py-0.5 rounded shadow-sm"
              >
                B
              </button>
              <button
                onClick={() => handleAddLeg({ action: "sell", option_type: "call", strike, premium: call.lastPrice, iv: call.iv })}
                className="bg-[#f23645] hover:bg-[#f23645]/80 text-white font-bold text-[9px] px-1.5 py-0.5 rounded shadow-sm"
              >
                S
              </button>
            </div>
          )}
        </div>

        {/* Strike */}
        <div className={`text-center font-bold font-mono text-[11px] h-full flex items-center justify-center ${isAtm ? "bg-indigo-600 text-white" : "text-slate-300 bg-[#1c2030]/50"}`}>
          {strike.toLocaleString("en-IN")}
        </div>

        {/* Put LTP with hover action */}
        <div className={`relative flex items-center justify-start w-full h-full group px-3 border-l border-[#2a2e39]/30 ${isPutItm ? "bg-[#1e222d]/30" : ""}`}>
          <span className="group-hover:invisible font-mono text-[11px] font-semibold text-slate-200">
            {put ? fmtPx(put.lastPrice) : "—"}
          </span>
          {put && (
            <div className="hidden group-hover:flex absolute inset-0 items-center justify-center gap-1 bg-[#1c2030]/90 z-10">
              <button
                onClick={() => handleAddLeg({ action: "buy", option_type: "put", strike, premium: put.lastPrice, iv: put.iv })}
                className="bg-[#089981] hover:bg-[#089981]/80 text-white font-bold text-[9px] px-1.5 py-0.5 rounded shadow-sm"
              >
                B
              </button>
              <button
                onClick={() => handleAddLeg({ action: "sell", option_type: "put", strike, premium: put.lastPrice, iv: put.iv })}
                className="bg-[#f23645] hover:bg-[#f23645]/80 text-white font-bold text-[9px] px-1.5 py-0.5 rounded shadow-sm"
              >
                S
              </button>
            </div>
          )}
        </div>

        {/* Put IV */}
        <div className={`text-left px-3 font-mono text-[10px] text-amber-500/80 h-full flex items-center justify-start ${isPutItm ? "bg-[#1e222d]/30" : ""}`}>
          {put?.iv ? `${(put.iv * 100).toFixed(0)}%` : "—"}
        </div>
      </div>
    );
  }, [callMap, putMap, spotInfo]);

  const isIndex = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"].includes(symbol);
  const chartGrid = "#1e293b";
  const chartTick = { fontSize: 10, fill: "#64748b" };
  const tipStyle = {
    fontSize: 11,
    borderRadius: 6,
    backgroundColor: "#1e293b",
    border: "1px solid #334155",
    color: "#e2e8f0",
  };

  return (
    <div className="flex flex-col h-full overflow-hidden bg-[#131722] text-[#d1d4dc] font-sans">
      {/* ── Global Simulator Top Bar ─────────────────────────────────────────── */}
      <div className="shrink-0 flex items-center justify-between px-4 py-2 bg-[#1c2030] border-b border-[#2a2e39] gap-4">
        {/* Left Section: Tab switcher & Selectors */}
        <div className="flex items-center gap-3">
          <div className="flex bg-[#131722] p-1 rounded-lg border border-[#2a2e39] gap-0.5 shrink-0">
            <button
              onClick={() => setRightTab("payoff")}
              className="px-2.5 py-1 text-[10px] font-semibold transition-all rounded text-slate-400 hover:text-slate-200"
            >
              Payoff
            </button>
            <button
              className="px-2.5 py-1 text-[10px] font-semibold transition-all rounded bg-indigo-600 text-white"
            >
              Simulator
            </button>
          </div>

          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="bg-[#131722] border border-[#2a2e39] text-[#d1d4dc] text-xs font-semibold rounded px-2.5 py-1 outline-none cursor-pointer hover:border-slate-500 transition shrink-0"
          >
            <option value="NIFTY">NIFTY 50</option>
            <option value="BANKNIFTY">BANK NIFTY</option>
            <option value="FINNIFTY">FIN NIFTY</option>
            <option value="MIDCPNIFTY">MIDCAP NIFTY</option>
            <option value="SENSEX">SENSEX</option>
            <option value="BANKEX">BANKEX</option>
            {!isIndex && <option value={symbol}>{symbol}</option>}
          </select>

          <select
            value={expiryDate}
            onChange={(e) => setExpiryDate(e.target.value)}
            className="bg-[#131722] border border-[#2a2e39] text-[#d1d4dc] text-xs font-semibold rounded px-2.5 py-1 outline-none cursor-pointer hover:border-slate-500 transition shrink-0"
          >
            {NSE_EXPIRIES.map(ex => (
              <option key={ex.date} value={ex.date}>{ex.label}</option>
            ))}
          </select>
        </div>

        {/* Middle Section: Time Scrubbing Controls */}
        <div className="flex items-center gap-2 flex-1 max-w-xl">
          <button
            onClick={() => setSimulatedTime(prev => Math.max(start, prev - 30 * 60))}
            className="bg-[#2a2e39] hover:bg-[#363a45] text-[#d1d4dc] text-[10px] font-bold px-2 py-1 rounded transition"
            title="Minus 30m"
          >
            -30m
          </button>
          <button
            onClick={() => setSimulatedTime(prev => Math.max(start, prev - 5 * 60))}
            className="bg-[#2a2e39] hover:bg-[#363a45] text-[#d1d4dc] text-[10px] font-bold px-2 py-1 rounded transition"
            title="Minus 5m"
          >
            -5m
          </button>

          <div className="flex-1 flex items-center gap-2 bg-[#131722] border border-[#2a2e39] rounded px-3 py-0.5">
            <input
              type="range"
              min={start}
              max={expiry}
              step={60}
              value={simulatedTime}
              onChange={(e) => setSimulatedTime(Number(e.target.value))}
              className="flex-1 accent-indigo-500 cursor-pointer h-1.5"
            />
            <span className="text-[10px] font-mono font-bold text-slate-300 shrink-0">
              {formatSimulatedTime(simulatedTime)} ({dteRemaining.toFixed(2)} DTE)
            </span>
          </div>

          <button
            onClick={() => setSimulatedTime(prev => Math.min(expiry, prev + 5 * 60))}
            className="bg-[#2a2e39] hover:bg-[#363a45] text-[#d1d4dc] text-[10px] font-bold px-2 py-1 rounded transition"
            title="Plus 5m"
          >
            +5m
          </button>
          <button
            onClick={() => setSimulatedTime(prev => Math.min(expiry, prev + 30 * 60))}
            className="bg-[#2a2e39] hover:bg-[#363a45] text-[#d1d4dc] text-[10px] font-bold px-2 py-1 rounded transition"
            title="Plus 30m"
          >
            +30m
          </button>
          <button
            onClick={() => setSimulatedTime(prev => Math.min(expiry, prev + 24 * 60 * 60))}
            className="bg-[#2a2e39] hover:bg-[#363a45] text-[#d1d4dc] text-[10px] font-bold px-2 py-1 rounded transition"
            title="Plus 1 Day"
          >
            +1 Day
          </button>
        </div>

        {/* Right Section: Play Speed & Reset */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="flex items-center gap-1">
            <button
              onClick={() => {
                if (simulatedTime >= expiry) setSimulatedTime(start);
                setIsPlaying(p => !p);
              }}
              className="bg-indigo-600 hover:bg-indigo-700 text-white text-[10px] font-bold px-2.5 py-1 rounded flex items-center gap-1 transition"
            >
              {isPlaying ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
              {isPlaying ? "Pause" : "Play"}
            </button>
            <button
              onClick={() => { setIsPlaying(false); setSimulatedTime(start); }}
              className="p-1 text-slate-400 hover:text-slate-200 transition"
              title="Reset"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="flex items-center gap-0.5">
            {[{ l: "1×", ms: 100 }, { l: "2×", ms: 50 }, { l: "4×", ms: 25 }].map(s => (
              <button
                key={s.ms}
                onClick={() => setPlaySpeed(s.ms)}
                className={`text-[9px] font-bold px-1.5 py-0.5 rounded transition ${
                  playSpeed === s.ms ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {s.l}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── 3-Pane Workspace Split Grid ────────────────────────────────────────── */}
      <div className="flex-1 grid grid-cols-10 overflow-hidden">
        {/* ── Left Pane: Option Chain (40% / col-span-4) ────────────────────── */}
        <div className="col-span-4 flex flex-col h-full border-r border-[#2a2e39] bg-[#171b26] overflow-hidden">
          {/* Section Header */}
          <div className="shrink-0 flex items-center justify-between px-3 py-1.5 bg-[#1c2030] border-b border-[#2a2e39]">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-300">Option Chain</span>
            {chainLoading && <RefreshCw className="w-3 h-3 animate-spin text-indigo-400" />}
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-amber-500/90 font-mono">
              {chainSource}
            </span>
          </div>

          {/* Table Column Headers */}
          <div
            className="shrink-0 grid text-center text-[10px] font-bold text-[#787b86] uppercase border-b border-[#2a2e39] py-1.5 bg-[#1c2030]/50"
            style={{ gridTemplateColumns: "60px 100px 1fr 100px 60px" }}
          >
            <div className="text-right px-3">IV%</div>
            <div className="text-right px-3">CALL LTP</div>
            <div className="text-center">STRIKE</div>
            <div className="text-left px-3">PUT LTP</div>
            <div className="text-left px-3">IV%</div>
          </div>

          {/* Virtualized option chain list */}
          <div className="flex-1 overflow-hidden">
            {allStrikes.length > 0 ? (
              <VirtualList
                items={allStrikes}
                height={600}
                itemHeight={36}
                renderItem={renderChainRow}
              />
            ) : (
              <div className="flex flex-col items-center justify-center py-20 text-slate-500">
                <RefreshCw className="w-5 h-5 animate-spin mb-2" />
                <span className="text-xs">Loading chain strikes...</span>
              </div>
            )}
          </div>
        </div>

        {/* ── Right Pane: Positions + Payoff (60% / col-span-6) ─────────────── */}
        <div className="col-span-6 flex flex-col h-full bg-[#131722] overflow-hidden">
          {/* Right Top Pane: Positions Manager (40% height) */}
          <div className="h-[40%] border-b border-[#2a2e39] flex flex-col overflow-hidden bg-[#1c2030]">
            <div className="shrink-0 flex items-center justify-between px-3 py-1.5 border-b border-[#2a2e39]">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-300">
                Active Positions ({legs.length})
              </span>
              {legs.length > 0 && (
                <button
                  onClick={() => setLegs([])}
                  className="text-[9px] text-[#f23645] hover:underline flex items-center gap-0.5"
                >
                  <Trash2 className="w-2.5 h-2.5" /> Clear All
                </button>
              )}
            </div>

            <div className="flex-1 overflow-y-auto">
              {legs.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-slate-500">
                  <Plus className="w-6 h-6 mb-1 opacity-30" />
                  <span className="text-xs">No active legs in strategy</span>
                  <span className="text-[10px] opacity-60 mt-0.5">Hover Option Chain LTP cells to Buy (B) or Sell (S)</span>
                </div>
              ) : (
                <table className="w-full text-xs text-left border-collapse">
                  <thead>
                    <tr className="border-b border-[#2a2e39]/50 text-[#787b86] text-[10px] font-bold uppercase">
                      <th className="px-3 py-2">Side</th>
                      <th className="px-2 py-2">Type</th>
                      <th className="px-2 py-2 text-right">Strike</th>
                      <th className="px-4 py-2 text-center">Entry Price</th>
                      <th className="px-4 py-2 text-center">Lots</th>
                      <th className="px-2 py-2 text-right">Sim Price</th>
                      <th className="px-3 py-2 text-right">Real-Time P&L</th>
                      <th className="px-3 py-2 text-center"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#2a2e39]/30 font-mono">
                    {legs.map((leg) => {
                      const iv = Math.max(0.01, leg.iv + ivShift / 100);
                      const Tf = dteRemaining / 365.0;
                      const r = 0.07;
                      const simPrice = bsPrice(spotInfo?.spot ?? 0, leg.strike, Tf, r, iv, leg.option_type);
                      const legPnl = (simPrice - leg.premium) * leg.lots * leg.lot_size * (leg.action === "buy" ? 1 : -1);

                      return (
                        <tr key={leg.id} className="hover:bg-[#1e222d] border-b border-[#2a2e39]/20">
                          {/* Side */}
                          <td className="px-3 py-2">
                            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded font-sans ${
                              leg.action === "buy" ? "bg-emerald-950/40 text-emerald-400" : "bg-rose-950/40 text-rose-400"
                            }`}>
                              {leg.action.toUpperCase()}
                            </span>
                          </td>
                          {/* Type */}
                          <td className="px-2 py-2 font-semibold font-sans">
                            {leg.option_type.toUpperCase()}
                          </td>
                          {/* Strike */}
                          <td className="px-2 py-2 text-right font-semibold">
                            {leg.strike.toLocaleString("en-IN")}
                          </td>
                          {/* Entry Premium (Editable) */}
                          <td className="px-4 py-2 text-center">
                            <input
                              type="number"
                              value={leg.premium}
                              onChange={(e) => updateLeg(leg.id, "premium", Number(e.target.value))}
                              className="w-16 bg-[#131722] border border-[#2a2e39] text-[#d1d4dc] text-center text-xs rounded px-1 py-0.5 outline-none focus:border-slate-500"
                              step="0.05"
                            />
                          </td>
                          {/* Lots (Editable controls) */}
                          <td className="px-4 py-2 text-center">
                            <div className="flex items-center justify-center gap-1 font-sans">
                              <button
                                onClick={() => updateLeg(leg.id, "lots", Math.max(1, leg.lots - 1))}
                                className="w-5 h-5 flex items-center justify-center bg-[#2a2e39] hover:bg-[#363a45] text-[#d1d4dc] rounded text-xs transition"
                              >
                                -
                              </button>
                              <input
                                type="number"
                                value={leg.lots}
                                onChange={(e) => updateLeg(leg.id, "lots", Math.max(1, Number(e.target.value)))}
                                className="w-10 bg-[#131722] border border-[#2a2e39] text-[#d1d4dc] font-mono text-center text-xs rounded py-0.5 outline-none"
                              />
                              <button
                                onClick={() => updateLeg(leg.id, "lots", leg.lots + 1)}
                                className="w-5 h-5 flex items-center justify-center bg-[#2a2e39] hover:bg-[#363a45] text-[#d1d4dc] rounded text-xs transition"
                              >
                                +
                              </button>
                            </div>
                          </td>
                          {/* Sim Price */}
                          <td className="px-2 py-2 text-right text-slate-300">
                            {fmtPx(simPrice)}
                          </td>
                          {/* Real-time P&L */}
                          <td className={`px-3 py-2 text-right font-bold ${
                            legPnl >= 0 ? "text-[#089981]" : "text-[#f23645]"
                          }`}>
                            {fmtINR(legPnl)}
                          </td>
                          {/* Delete leg */}
                          <td className="px-3 py-2 text-center font-sans">
                            <button
                              onClick={() => removeLeg(leg.id)}
                              className="text-slate-500 hover:text-red-400 transition"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* Right Bottom Pane: Payoff Chart (60% height) */}
          <div className="h-[60%] flex flex-col overflow-hidden bg-[#131722]">
            {/* Stats strip */}
            <div className="shrink-0 grid grid-cols-6 border-b border-[#2a2e39] bg-[#1c2030]/20 text-center">
              {[
                { label: "T+0 at Spot", value: fmtINR(pnlAtSpot), color: pnlAtSpot >= 0 ? "text-[#089981]" : "text-[#f23645]" },
                { label: "Expiry P&L", value: fmtINR(expiryAtSpot), color: expiryAtSpot >= 0 ? "text-[#089981]" : "text-[#f23645]" },
                { label: "Max Profit", value: maxProfit === null ? "∞" : fmtINR(maxProfit), color: "text-[#089981]" },
                { label: "Max Loss", value: maxLoss === null ? "−∞" : fmtINR(maxLoss), color: "text-[#f23645]" },
                { label: "PoP", value: `${pop}%`, color: pop >= 50 ? "text-indigo-400" : "text-amber-400" },
                { label: "Theta/day", value: fmtINR(thetaDay), color: thetaDay >= 0 ? "text-[#089981]" : "text-[#f23645]" },
              ].map((s, i, arr) => (
                <div key={s.label} className={`py-1.5 flex flex-col justify-center ${i < arr.length - 1 ? "border-r border-[#2a2e39]" : ""}`}>
                  <span className="text-[8px] font-semibold uppercase text-slate-500 tracking-wider">{s.label}</span>
                  <span className={`text-[11px] font-bold font-mono ${s.color} mt-0.5`}>{s.value}</span>
                </div>
              ))}
            </div>

            {/* Interactive IV shift & Debounced Sync State */}
            <div className="shrink-0 flex items-center justify-between px-4 py-1.5 border-b border-[#2a2e39]/60 bg-[#1c2030]/10 text-xs">
              <div className="flex items-center gap-2 flex-1 max-w-sm">
                <span className="text-[9px] font-bold uppercase tracking-wider text-slate-500">IV Shk</span>
                <input
                  type="range"
                  min={-40}
                  max={40}
                  step={2}
                  value={ivShift}
                  onChange={(e) => setIvShift(Number(e.target.value))}
                  className="flex-1 accent-indigo-500 cursor-pointer h-1"
                />
                <span className={`font-mono text-[10px] font-bold w-10 text-right ${
                  ivShift > 0 ? "text-[#f23645]" : ivShift < 0 ? "text-[#089981]" : "text-slate-400"
                }`}>
                  {ivShift > 0 ? "+" : ""}{ivShift}%
                </span>
              </div>

              <div className="flex items-center gap-2 text-[10px] text-slate-400">
                {loading && <span className="flex items-center gap-1 text-indigo-400 animate-pulse"><RefreshCw className="w-2.5 h-2.5 animate-spin" />Syncing...</span>}
                {breakevens.length > 0 && (
                  <span className="font-mono flex gap-1">
                    BE: {breakevens.map((be, i) => <span key={i} className="text-emerald-500 font-bold">₹{Math.round(be).toLocaleString("en-IN")}</span>)}
                  </span>
                )}
              </div>
            </div>

            {/* Recharts Container */}
            <div className="flex-1 min-h-0 p-2 relative">
              {legs.length > 0 && spotInfo ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData} margin={{ top: 12, right: 16, left: 4, bottom: 4 }}>
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
                      width={46}
                    />
                    <Tooltip
                      formatter={(v: number, name: string) => [
                        fmtINR(v),
                        name === "expiry" ? "At Expiry" : "T+0 Simulated",
                      ]}
                      labelFormatter={(l: number) => `Spot: ₹${Number(l).toLocaleString("en-IN")}`}
                      contentStyle={tipStyle}
                    />
                    <ReferenceLine y={0} stroke="#475569" strokeWidth={1.5} />
                    {spotInfo && (
                      <ReferenceLine
                        x={spotInfo.spot}
                        stroke="#f97316"
                        strokeDasharray="4 2"
                        label={{ value: "Spot", fill: "#f97316", fontSize: 9, position: "top" }}
                      />
                    )}
                    {breakevens.map((be, i) => (
                      <ReferenceLine
                        key={i}
                        x={be}
                        stroke="#10b981"
                        strokeDasharray="3 3"
                        label={{ value: "BE", fill: "#059669", fontSize: 9 }}
                      />
                    ))}
                    {/* Expiry payoff (sharp dotted blue) */}
                    <Line
                      type="monotone"
                      dataKey="expiry"
                      stroke="#6366f1"
                      strokeWidth={1.5}
                      dot={false}
                      strokeDasharray="6 3"
                      activeDot={{ r: 3 }}
                    />
                    {/* T+0 simulated payoff (smooth solid orange) */}
                    <Line
                      type="monotone"
                      dataKey="current"
                      stroke="#f97316"
                      strokeWidth={2.5}
                      dot={false}
                      activeDot={{ r: 4 }}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-500 gap-2">
                  <Activity className="w-8 h-8 opacity-20" />
                  <span className="text-xs font-sans">Build a strategy to display payoff simulation</span>
                  <span className="text-[10px] opacity-60 font-sans">Add legs from the Option Chain on the left</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
