import { useState, useCallback, useRef, useEffect } from "react";
import { fetchApi } from "@/lib/api";
import {
  TrendingUp, TrendingDown, Plus, Trash2, Play, BarChart2,
  AlertTriangle, RefreshCw, ChevronDown, Target, Activity,
  Shield, Zap, Info, MessageSquare, Send, X, Bot
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer, BarChart, Bar, Cell
} from "recharts";

// ── API helpers ───────────────────────────────────────────────────────────────
const J = { "Content-Type": "application/json" };
function post<T = any>(path: string, body: unknown) {
  return fetchApi<T>(path, { method: "POST", headers: J, body: JSON.stringify(body) });
}
function get<T = any>(path: string) { return fetchApi<T>(path); }

// ── Types ─────────────────────────────────────────────────────────────────────
interface Leg {
  id:          string;
  action:      "buy" | "sell";
  option_type: "call" | "put";
  strike:      number;
  premium:     number;
  lots:        number;
  lot_size:    number;
  iv:          number;
}

interface SpotInfo { spot: number; hv30: number; hv30_pct: number; lot_size: number; atm: number; }
interface Greeks   { delta: number; gamma: number; theta: number; vega: number; rho: number; }

// ── Formatting helpers ────────────────────────────────────────────────────────
function fmtINR(n: number | null | undefined) {
  if (n == null) return "—";
  const sign = n < 0 ? "-" : "";
  const v = Math.abs(n);
  if (v >= 1e7) return `${sign}₹${(v / 1e7).toFixed(2)}Cr`;
  if (v >= 1e5) return `${sign}₹${(v / 1e5).toFixed(2)}L`;
  return `${sign}₹${v.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}
function pct(n: number | null | undefined, d = 2) {
  return n == null ? "—" : `${Number(n).toFixed(d)}%`;
}
function fmt(n: number | null | undefined, d = 2) {
  return n == null ? "—" : Number(n).toFixed(d);
}
function clr(v: number) { return v >= 0 ? "text-green-600" : "text-red-500"; }
function bg(v: number)  { return v >= 0 ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600"; }

// ── Preset strategies ─────────────────────────────────────────────────────────
const PRESETS = [
  "long_call","long_put","short_call","short_put",
  "straddle","short_straddle","strangle","short_strangle",
  "bull_call_spread","bear_put_spread","iron_condor","butterfly",
];

const PRESET_LABELS: Record<string, string> = {
  long_call: "Long Call", long_put: "Long Put",
  short_call: "Short Call", short_put: "Short Put",
  straddle: "Long Straddle", short_straddle: "Short Straddle",
  strangle: "Long Strangle", short_strangle: "Short Strangle",
  bull_call_spread: "Bull Call Spread", bear_put_spread: "Bear Put Spread",
  iron_condor: "Iron Condor", butterfly: "Butterfly",
};

// otmMult: how many OTM steps away from ATM this leg sits (0 = ATM).
// For iron condor the sell legs are 1× OTM and the buy (protection) legs are 2× OTM.
type QuickLeg = Partial<Leg> & { otmMult?: number };

const QUICK_STRATEGIES: { label: string; legs: QuickLeg[] }[] = [
  {
    label: "Long Straddle",
    legs: [
      { action: "buy", option_type: "call", lots: 1, otmMult: 0 },
      { action: "buy", option_type: "put",  lots: 1, otmMult: 0 },
    ],
  },
  {
    label: "Short Strangle",
    legs: [
      { action: "sell", option_type: "call", lots: 1, otmMult: 1 },
      { action: "sell", option_type: "put",  lots: 1, otmMult: 1 },
    ],
  },
  {
    label: "Iron Condor",
    legs: [
      { action: "sell", option_type: "call", lots: 1, otmMult: 1 }, // near OTM call (sold)
      { action: "buy",  option_type: "call", lots: 1, otmMult: 2 }, // far  OTM call (protection)
      { action: "sell", option_type: "put",  lots: 1, otmMult: 1 }, // near OTM put  (sold)
      { action: "buy",  option_type: "put",  lots: 1, otmMult: 2 }, // far  OTM put  (protection)
    ],
  },
];

// ── Components ────────────────────────────────────────────────────────────────
function Loader() {
  return (
    <div className="flex items-center gap-2 text-indigo-500 text-sm">
      <RefreshCw className="w-4 h-4 animate-spin" />
      <span>Loading…</span>
    </div>
  );
}

function Pill({ label, value, color = "gray" }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-sm">
      <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">{label}</p>
      <p className={`text-lg font-bold text-${color}-700`}>{value}</p>
    </div>
  );
}

// ── Minimal markdown renderer for chat messages ───────────────────────────────
function renderMd(text: string) {
  return text.split("\n").map((line, i) => {
    // Blank line → spacer
    if (!line.trim()) return <div key={i} className="h-1" />;

    // Parse inline **bold** and `code`
    function parseInline(s: string) {
      const result: React.ReactNode[] = [];
      const re = /\*\*(.*?)\*\*|`([^`]+)`/g;
      let last = 0; let m: RegExpExecArray | null;
      while ((m = re.exec(s)) !== null) {
        if (m.index > last) result.push(s.slice(last, m.index));
        if (m[1] !== undefined) result.push(<strong key={m.index} className="font-semibold text-gray-900">{m[1]}</strong>);
        if (m[2] !== undefined) result.push(<code key={m.index} className="bg-gray-100 text-indigo-700 px-1 py-0.5 rounded text-[11px] font-mono">{m[2]}</code>);
        last = re.lastIndex;
      }
      if (last < s.length) result.push(s.slice(last));
      return result;
    }

    // Header
    if (/^#{1,3}\s/.test(line)) {
      const t = line.replace(/^#+\s/, "");
      return <p key={i} className="font-bold text-gray-800 mt-2 text-sm">{parseInline(t)}</p>;
    }
    // Bullet or dash list
    if (/^[•\-\*]\s/.test(line)) {
      const t = line.replace(/^[•\-\*]\s/, "");
      return (
        <div key={i} className="flex gap-2 items-start">
          <span className="text-indigo-400 mt-0.5 flex-shrink-0 text-xs">•</span>
          <span className="text-sm leading-snug text-gray-700">{parseInline(t)}</span>
        </div>
      );
    }
    // Numbered list
    if (/^\d+\.\s/.test(line)) {
      const num = line.match(/^(\d+)\./)?.[1];
      const t   = line.replace(/^\d+\.\s/, "");
      return (
        <div key={i} className="flex gap-2 items-start">
          <span className="text-indigo-500 font-semibold flex-shrink-0 text-xs w-4 text-right mt-0.5">{num}.</span>
          <span className="text-sm leading-snug text-gray-700">{parseInline(t)}</span>
        </div>
      );
    }
    // Table row (skip — render as plain)
    if (/^\|/.test(line)) {
      return <p key={i} className="text-xs font-mono text-gray-500 leading-relaxed">{line}</p>;
    }
    // Default paragraph
    return <p key={i} className="text-sm leading-snug text-gray-700">{parseInline(line)}</p>;
  });
}

function GreeksBar({ g }: { g: Greeks }) {
  const items = [
    { sym: "Δ", label: "Delta", val: g.delta, tip: "Price sensitivity per ₹1 move" },
    { sym: "Γ", label: "Gamma", val: g.gamma, tip: "Rate of change of Delta" },
    { sym: "Θ", label: "Theta", val: g.theta, tip: "Daily time decay (₹)" },
    { sym: "ν", label: "Vega",  val: g.vega,  tip: "Sensitivity to 1% IV change" },
    { sym: "ρ", label: "Rho",   val: g.rho,   tip: "Sensitivity to 1% rate change" },
  ];
  return (
    <div className="grid grid-cols-2 gap-1.5">
      {items.map(({ sym, label, val, tip }) => (
        <div key={label} title={tip}
             className="flex items-center justify-between bg-white rounded-lg px-2.5 py-1.5 border border-gray-100 cursor-help">
          <span className="text-[10px] text-gray-500">
            <span className="font-bold">{sym}</span>
            <span className="ml-1 text-gray-400">{label}</span>
          </span>
          <span className={`text-xs font-bold font-mono ml-2 ${clr(val)}`}>{fmt(val, 3)}</span>
        </div>
      ))}
    </div>
  );
}

// ── P&L Heatmap ───────────────────────────────────────────────────────────────
function PnlHeatmap({ spots, payoffs, currentSpot }: {
  spots: number[]; payoffs: number[]; currentSpot?: number;
}) {
  const maxAbs = Math.max(...payoffs.map(Math.abs), 1);
  // Downsample to ~80 bars for performance
  const step = Math.max(1, Math.floor(spots.length / 80));
  const bars = spots
    .filter((_, i) => i % step === 0)
    .map((s, i) => {
      const pnl = payoffs[i * step] ?? 0;
      const norm = Math.min(Math.abs(pnl) / maxAbs, 1);
      const alpha = 0.12 + norm * 0.88;
      const color = pnl > 0
        ? `rgba(22,163,74,${alpha})`
        : pnl < 0
          ? `rgba(220,38,38,${alpha})`
          : "rgba(200,200,200,0.2)";
      return { s, pnl, color };
    });

  // Find spot bar nearest to currentSpot
  const nearestIdx = currentSpot
    ? bars.reduce((best, b, i) =>
        Math.abs(b.s - currentSpot) < Math.abs(bars[best].s - currentSpot) ? i : best, 0)
    : -1;

  return (
    <div className="mt-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] text-gray-400 font-medium uppercase tracking-wide">P&L Heatmap at Expiry</span>
        <div className="flex items-center gap-3 text-[10px] text-gray-400">
          <span className="flex items-center gap-1"><span className="w-3 h-2 rounded-sm inline-block bg-red-500 opacity-70" /> Loss</span>
          <span className="flex items-center gap-1"><span className="w-3 h-2 rounded-sm inline-block bg-green-600 opacity-70" /> Profit</span>
        </div>
      </div>
      <div className="flex h-8 rounded-lg overflow-hidden border border-gray-100">
        {bars.map((b, i) => (
          <div
            key={i}
            className="flex-1 relative group cursor-default transition-opacity"
            style={{ background: b.color }}
            title={`₹${b.s.toLocaleString("en-IN")} → ${b.pnl >= 0 ? "+" : ""}${b.pnl.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`}
          >
            {i === nearestIdx && (
              <div className="absolute inset-y-0 left-1/2 w-0.5 bg-orange-500 opacity-90" />
            )}
          </div>
        ))}
      </div>
      <div className="flex justify-between text-[9px] text-gray-400 mt-0.5 font-mono">
        <span>₹{bars[0]?.s.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</span>
        {currentSpot && <span className="text-orange-500">↑ Spot</span>}
        <span>₹{bars[bars.length - 1]?.s.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</span>
      </div>
    </div>
  );
}

// ── TABS ──────────────────────────────────────────────────────────────────────
type Tab = "strategy" | "backtest" | "risk";

export default function OptionsStrategyTester() {
  const [tab, setTab] = useState<Tab>("strategy");

  // Symbol / spot state
  const [symbol, setSymbol] = useState("NIFTY");
  const [spotInfo, setSpotInfo] = useState<SpotInfo | null>(null);
  const [loadingSpot, setLoadingSpot] = useState(false);
  const [spotErr, setSpotErr] = useState("");

  // Strategy builder state
  const [legs, setLegs]   = useState<Leg[]>([]);
  const [T, setT]         = useState(30);     // days to expiry
  const [analysis, setAnalysis] = useState<any>(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [analysisErr, setAnalysisErr] = useState("");

  // Backtest state
  const [btStrategy, setBtStrategy] = useState("short_straddle");
  const [btStart, setBtStart]       = useState("2020-01-01");
  const [btEnd, setBtEnd]           = useState(new Date().toISOString().slice(0, 10));
  const [btLots, setBtLots]         = useState(1);
  const [btEntryDte, setBtEntryDte] = useState(30);
  const [btRollDte, setBtRollDte]   = useState(0);
  const [btOtmPct, setBtOtmPct]     = useState(5);
  const [btResult, setBtResult]     = useState<any>(null);
  const [loadingBt, setLoadingBt]   = useState(false);
  const [btErr, setBtErr]           = useState("");

  // Risk state
  const [varResult, setVarResult]       = useState<any>(null);
  const [scResult, setScResult]         = useState<any>(null);
  const [loadingRisk, setLoadingRisk]   = useState(false);
  const [riskErr, setRiskErr]           = useState("");
  const [varHorizon, setVarHorizon]     = useState(5);
  const [varSims, setVarSims]           = useState(10000);
  const [varConf, setVarConf]           = useState(0.95);

  // AI Chat state
  type ChatMsg = { role: "user" | "assistant"; content: string };
  const [chatOpen, setChatOpen]       = useState(false);
  const [chatMsgs, setChatMsgs]       = useState<ChatMsg[]>([]);
  const [chatInput, setChatInput]     = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMsgs]);

  async function sendChat() {
    const text = chatInput.trim();
    if (!text || chatLoading) return;
    const userMsg: ChatMsg = { role: "user", content: text };
    setChatMsgs(prev => [...prev, userMsg]);
    setChatInput("");
    setChatLoading(true);
    try {
      const context = spotInfo ? {
        symbol,
        spot:     spotInfo.spot,
        hv30_pct: spotInfo.hv30_pct,
        T:        T / 365,
        legs,
        analysis,
      } : undefined;
      const res = await post<{ reply: string }>("/options/chat", {
        messages: [...chatMsgs, userMsg],
        context,
      });
      setChatMsgs(prev => [...prev, { role: "assistant", content: res.reply }]);
    } catch {
      setChatMsgs(prev => [...prev, {
        role: "assistant",
        content: "Sorry, I couldn't reach the AI right now. Please try again.",
      }]);
    } finally {
      setChatLoading(false);
    }
  }

  // ── Fetch spot ──────────────────────────────────────────────────────────────
  // Returns the SpotInfo so callers (e.g. quick-add) can use it immediately
  const doFetchSpot = useCallback(async (): Promise<SpotInfo | null> => {
    if (!symbol.trim()) return null;
    setLoadingSpot(true);
    setSpotErr("");
    try {
      const info = await get<SpotInfo>(`/options/spot/${symbol.trim().toUpperCase()}`);
      setSpotInfo(info);
      setLegs(prev => prev.map(l => ({
        ...l,
        lot_size: info.lot_size,
        strike: l.strike === 0 ? info.atm : l.strike,
        iv: l.iv === 0 ? info.hv30 : l.iv,
      })));
      return info;
    } catch (e: any) {
      setSpotErr(e?.message || "Failed to fetch spot price");
      return null;
    } finally {
      setLoadingSpot(false);
    }
  }, [symbol]);

  const fetchSpot = useCallback(() => doFetchSpot(), [doFetchSpot]);

  // ── Add leg ─────────────────────────────────────────────────────────────────
  function addLeg(partial?: Partial<Leg>) {
    const spot = spotInfo?.spot ?? 0;
    const atm  = spotInfo?.atm  ?? 0;
    const ls   = spotInfo?.lot_size ?? 75;
    const hv   = spotInfo?.hv30 ?? 0.20;
    const newLeg: Leg = {
      id:          crypto.randomUUID(),
      action:      partial?.action      ?? "buy",
      option_type: partial?.option_type ?? "call",
      strike:      partial?.strike      ?? atm,
      premium:     0,
      lots:        partial?.lots        ?? 1,
      lot_size:    ls,
      iv:          hv,
    };
    setLegs(prev => [...prev, newLeg]);
  }

  function removeLeg(id: string) {
    setLegs(prev => prev.filter(l => l.id !== id));
  }

  function updateLeg(id: string, field: keyof Leg, val: any) {
    setLegs(prev => prev.map(l => l.id === id ? { ...l, [field]: val } : l));
  }

  // ── Analyse strategy ─────────────────────────────────────────────────────────
  async function analyseStrategy() {
    if (!legs.length) { setAnalysisErr("Add at least one leg"); return; }
    if (!spotInfo)    { setAnalysisErr("Fetch spot price first"); return; }
    setLoadingAnalysis(true);
    setAnalysisErr("");
    try {
      const res = await post("/options/strategy", {
        legs:    legs.map(l => ({ ...l, iv: l.iv || spotInfo.hv30 })),
        S:       spotInfo.spot,
        T:       T / 365,
        sigma:   spotInfo.hv30,
        r:       0.07,
        spot_range_pct: 0.20,
      });
      setAnalysis(res);
      // Update premiums from API
      setLegs(prev => prev.map((l, i) => ({
        ...l,
        premium: res.legs?.[i]?.premium ?? l.premium,
      })));
    } catch (e: any) {
      setAnalysisErr(e?.message || "Analysis failed");
    } finally {
      setLoadingAnalysis(false);
    }
  }

  // ── Run backtest ─────────────────────────────────────────────────────────────
  async function runBacktest() {
    if (!symbol.trim()) { setBtErr("Enter a symbol"); return; }
    setLoadingBt(true);
    setBtErr("");
    setBtResult(null);
    try {
      const res = await post("/options/backtest", {
        symbol:    symbol.trim().toUpperCase(),
        strategy:  btStrategy,
        start_date: btStart,
        end_date:   btEnd,
        lots:       btLots,
        lot_size:   spotInfo?.lot_size,
        entry_dte:  btEntryDte,
        roll_dte:   btRollDte,
        otm_pct:    btOtmPct / 100,
      });
      setBtResult(res);
    } catch (e: any) {
      setBtErr(e?.message || "Backtest failed");
    } finally {
      setLoadingBt(false);
    }
  }

  // ── Risk analysis ─────────────────────────────────────────────────────────────
  async function runRisk() {
    if (!legs.length || !spotInfo) { setRiskErr("Build strategy and fetch spot first"); return; }
    if (!analysis)                 { setRiskErr("Run Analyse Strategy first"); return; }
    setLoadingRisk(true);
    setRiskErr("");
    try {
      const legPayload = legs.map(l => ({
        ...l, iv: l.iv || spotInfo.hv30,
        premium: l.premium || 0,
      }));
      const [varRes, scRes] = await Promise.all([
        post("/options/var", {
          legs: legPayload, S: spotInfo.spot, T: T / 365,
          sigma: spotInfo.hv30, r: 0.07,
          horizon_days: varHorizon, num_simulations: varSims,
          confidence: varConf,
        }),
        post("/options/scenario", {
          legs: legPayload, S: spotInfo.spot, T: T / 365, r: 0.07,
        }),
      ]);
      setVarResult(varRes);
      setScResult(scRes);
    } catch (e: any) {
      setRiskErr(e?.message || "Risk analysis failed");
    } finally {
      setLoadingRisk(false);
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────────
  const tabCls = (t: Tab) =>
    `px-5 py-2.5 text-sm font-medium rounded-t-lg border-b-2 transition-colors ${
      tab === t
        ? "border-indigo-600 text-indigo-700 bg-white"
        : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
    }`;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Options Strategy Tester</h1>
          <p className="text-sm text-gray-500">
            NSE options — Black-Scholes pricing · event-driven backtesting · Monte Carlo VaR
          </p>
        </div>
        <button
          onClick={() => setChatOpen(o => !o)}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all border
            ${chatOpen
              ? "bg-indigo-600 text-white border-indigo-600"
              : "bg-white text-indigo-700 border-indigo-200 hover:bg-indigo-50"}`}
        >
          <Bot className="w-4 h-4" />
          AI Assistant
          {chatMsgs.length > 0 && (
            <span className={`text-xs font-bold rounded-full px-1.5 py-0.5 ${chatOpen ? "bg-white/20 text-white" : "bg-indigo-100 text-indigo-600"}`}>
              {chatMsgs.length}
            </span>
          )}
        </button>
      </div>

      {/* Symbol bar */}
      {(() => {
        const INDICES = [
          { sym: "NIFTY",      label: "NIFTY 50",     lot: 75, exch: "NSE" },
          { sym: "BANKNIFTY",  label: "BANK NIFTY",   lot: 30, exch: "NSE" },
          { sym: "FINNIFTY",   label: "FIN NIFTY",    lot: 40, exch: "NSE" },
          { sym: "MIDCPNIFTY", label: "MIDCAP NIFTY", lot: 75, exch: "NSE" },
          { sym: "SENSEX",     label: "SENSEX",        lot: 10, exch: "BSE" },
          { sym: "BANKEX",     label: "BANKEX",        lot: 15, exch: "BSE" },
        ];
        const switchIndex = async (sym: string) => {
          if (sym === symbol && spotInfo) return;
          setSymbol(sym);
          setSpotInfo(null);
          setLegs([]);
          setAnalysis(null);
          setLoadingSpot(true);
          setSpotErr("");
          try {
            const info = await get<SpotInfo>(`/options/spot/${sym}`);
            setSpotInfo(info);
          } catch (e: any) {
            setSpotErr(e?.message || `Failed to fetch ${sym}`);
          } finally {
            setLoadingSpot(false);
          }
        };
        return (
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            {/* Segmented control */}
            <div className="bg-gray-50 border-b border-gray-100 p-2">
              <div className="bg-gray-100 rounded-xl p-1 flex gap-0.5">
                {INDICES.map(({ sym, label, lot, exch }) => {
                  const active = symbol === sym;
                  const fetching = active && loadingSpot;
                  return (
                    <button
                      key={sym}
                      onClick={() => switchIndex(sym)}
                      disabled={loadingSpot}
                      className={`flex-1 flex flex-col items-center py-2 px-1 rounded-lg transition-all duration-150 disabled:opacity-60
                        ${active
                          ? "bg-white shadow-sm text-gray-900"
                          : "text-gray-500 hover:text-gray-700 hover:bg-gray-50"
                        }`}
                    >
                      <span className="text-xs font-bold tracking-tight leading-tight whitespace-nowrap">
                        {fetching
                          ? <span className="flex items-center gap-1"><RefreshCw className="w-3 h-3 animate-spin" />{label}</span>
                          : label}
                      </span>
                      <span className={`text-[10px] leading-tight mt-0.5 font-medium
                        ${active ? "text-indigo-500" : "text-gray-400"}`}>
                        {exch} · {lot}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Live market data strip */}
            {spotInfo && (
              <div className="flex items-center divide-x divide-gray-100 px-1">
                <div className="flex items-baseline gap-1.5 px-4 py-3">
                  <span className="text-xl font-bold text-gray-900">
                    ₹{spotInfo.spot.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                  <span className="text-xs text-gray-400 font-medium">SPOT</span>
                </div>
                <div className="flex items-center gap-5 px-5 py-3 flex-1">
                  <div className="text-center">
                    <p className="text-xs text-gray-400 font-medium mb-0.5">ATM Strike</p>
                    <p className="text-sm font-bold text-gray-800">₹{spotInfo.atm.toLocaleString("en-IN")}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-gray-400 font-medium mb-0.5">HV 30d</p>
                    <p className="text-sm font-bold text-orange-600">{pct(spotInfo.hv30_pct)}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-gray-400 font-medium mb-0.5">Lot Size</p>
                    <p className="text-sm font-bold text-gray-800">{spotInfo.lot_size} units</p>
                  </div>
                </div>
                <button
                  onClick={fetchSpot}
                  disabled={loadingSpot}
                  className="px-4 py-3 text-gray-400 hover:text-indigo-600 transition disabled:opacity-40"
                  title="Refresh"
                >
                  <RefreshCw className={`w-4 h-4 ${loadingSpot ? "animate-spin" : ""}`} />
                </button>
              </div>
            )}

            {!spotInfo && !loadingSpot && !spotErr && (
              <div className="px-4 py-3 text-sm text-gray-400 flex items-center gap-2">
                <Zap className="w-4 h-4 text-indigo-300" />
                Select an index above to load live market data
              </div>
            )}

            {loadingSpot && !spotInfo && (
              <div className="px-4 py-3 text-sm text-gray-400 flex items-center gap-2">
                <RefreshCw className="w-4 h-4 animate-spin text-indigo-400" />
                Fetching {symbol} live data…
              </div>
            )}

            {spotErr && (
              <div className="px-4 py-3">
                <p className="text-red-500 text-sm flex items-center gap-1">
                  <AlertTriangle className="w-4 h-4" /> {spotErr}
                </p>
              </div>
            )}
          </div>
        );
      })()}

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-1">
          <button className={tabCls("strategy")} onClick={() => setTab("strategy")}>Strategy &amp; Payoff</button>
          <button className={tabCls("backtest")} onClick={() => setTab("backtest")}>Backtest</button>
          <button className={tabCls("risk")}     onClick={() => setTab("risk")}>Risk Analysis</button>
        </nav>
      </div>

      {/* ── TAB: Strategy Builder ────────────────────────────────────────── */}
      {tab === "strategy" && (
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm flex overflow-hidden" style={{ minHeight: 540 }}>

          {/* ── LEFT: Builder ───────────────────────────────────────────── */}
          <div className="w-[44%] flex-shrink-0 flex flex-col border-r border-gray-100">

            {/* Quick presets */}
            <div className="px-4 py-3 border-b border-gray-100">
              <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-2">Quick Add Strategy</p>
              <div className="flex flex-wrap gap-1.5">
                {QUICK_STRATEGIES.map(qs => (
                  <button
                    key={qs.label}
                    onClick={async () => {
                      const info = spotInfo ?? await doFetchSpot();
                      if (!info) return;
                      const atm  = info.atm;
                      const step = atm >= 10000 ? 100 : atm >= 2000 ? 50 : 10;
                      const otm  = step * 3;
                      const newLegs = qs.legs.map((l) => {
                        const mult   = l.otmMult ?? 0;
                        const offset = otm * mult;
                        const strike = l.option_type === "call" ? atm + offset : atm - offset;
                        return {
                          id:          crypto.randomUUID(),
                          action:      l.action      ?? ("buy" as const),
                          option_type: l.option_type ?? ("call" as const),
                          strike,
                          premium:     0,
                          lots:        l.lots ?? 1,
                          lot_size:    info.lot_size,
                          iv:          info.hv30,
                        };
                      });
                      setLegs(prev => [...prev, ...newLegs]);
                    }}
                    className="px-2.5 py-1 text-xs rounded-lg border border-indigo-200 text-indigo-700 hover:bg-indigo-50 transition font-medium"
                  >
                    {qs.label}
                  </button>
                ))}
                <button
                  onClick={() => addLeg()}
                  className="flex items-center gap-1 px-2.5 py-1 text-xs rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 transition"
                >
                  <Plus className="w-3 h-3" /> Custom
                </button>
              </div>
            </div>

            {/* Legs header */}
            <div className="px-4 py-2 border-b border-gray-100 flex items-center justify-between bg-gray-50/60">
              <span className="text-xs font-semibold text-gray-600">Legs</span>
              <div className="flex items-center gap-2">
                <label className="text-[10px] text-gray-400 font-medium">DTE</label>
                <input
                  type="number" min={1} max={365}
                  value={T}
                  onChange={e => setT(Number(e.target.value))}
                  className="w-14 border border-gray-200 rounded px-2 py-0.5 text-xs text-center"
                />
              </div>
            </div>

            {/* Legs body */}
            <div className="flex-1 overflow-y-auto">
              {legs.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full py-10 text-gray-400">
                  <Plus className="w-8 h-8 mb-2 opacity-30" />
                  <p className="text-sm">No legs yet</p>
                  <p className="text-xs mt-0.5">Pick a strategy or add a custom leg above</p>
                </div>
              ) : (
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 text-[10px] text-gray-400 uppercase tracking-wide sticky top-0">
                    <tr>
                      <th className="px-3 py-2 text-left">Action</th>
                      <th className="px-3 py-2 text-left">Type</th>
                      <th className="px-3 py-2 text-left">Strike</th>
                      <th className="px-3 py-2 text-left">IV%</th>
                      <th className="px-3 py-2 text-left">Lots</th>
                      <th className="px-3 py-2 text-left">Sz</th>
                      <th className="px-3 py-2 text-left">Prem</th>
                      <th className="px-3 py-2" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {legs.map(leg => (
                      <tr key={leg.id} className="hover:bg-gray-50/70">
                        <td className="px-3 py-1.5">
                          <select
                            value={leg.action}
                            onChange={e => updateLeg(leg.id, "action", e.target.value)}
                            className={`rounded px-1.5 py-0.5 text-[10px] font-bold border-0 cursor-pointer ${
                              leg.action === "buy" ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"
                            }`}
                          >
                            <option value="buy">BUY</option>
                            <option value="sell">SELL</option>
                          </select>
                        </td>
                        <td className="px-3 py-1.5">
                          <select
                            value={leg.option_type}
                            onChange={e => updateLeg(leg.id, "option_type", e.target.value)}
                            className="border border-gray-200 rounded px-1.5 py-0.5 text-[10px]"
                          >
                            <option value="call">CE</option>
                            <option value="put">PE</option>
                          </select>
                        </td>
                        <td className="px-3 py-1.5">
                          <input
                            type="number" step={50} min={0}
                            value={leg.strike}
                            onChange={e => updateLeg(leg.id, "strike", Number(e.target.value))}
                            className="border border-gray-200 rounded px-1.5 py-0.5 text-xs w-20 font-mono"
                          />
                        </td>
                        <td className="px-3 py-1.5">
                          <input
                            type="number" step={0.5} min={1} max={300}
                            value={parseFloat((leg.iv * 100).toFixed(1))}
                            onChange={e => updateLeg(leg.id, "iv", Number(e.target.value) / 100)}
                            className="border border-gray-200 rounded px-1.5 py-0.5 text-xs w-14 font-mono"
                          />
                        </td>
                        <td className="px-3 py-1.5">
                          <input
                            type="number" min={1} max={50}
                            value={leg.lots}
                            onChange={e => updateLeg(leg.id, "lots", Number(e.target.value))}
                            className="border border-gray-200 rounded px-1.5 py-0.5 text-xs w-12"
                          />
                        </td>
                        <td className="px-3 py-1.5">
                          <input
                            type="number" min={1}
                            value={leg.lot_size}
                            onChange={e => updateLeg(leg.id, "lot_size", Number(e.target.value))}
                            className="border border-gray-200 rounded px-1.5 py-0.5 text-xs w-14"
                          />
                        </td>
                        <td className="px-3 py-1.5 font-mono text-gray-400">
                          {leg.premium > 0 ? `₹${leg.premium.toFixed(1)}` : "—"}
                        </td>
                        <td className="px-3 py-1.5">
                          <button onClick={() => removeLeg(leg.id)} className="text-red-300 hover:text-red-500 transition">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Greeks (when available) */}
            {analysis && (
              <div className="px-4 py-3 border-t border-gray-100 bg-gray-50/40">
                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-2">Portfolio Greeks</p>
                <GreeksBar g={analysis.greeks} />
              </div>
            )}

            {/* Footer: error + actions */}
            {analysisErr && (
              <div className="px-4 py-2 bg-red-50 border-t border-red-100 text-red-600 text-xs">
                {analysisErr}
              </div>
            )}
            <div className="px-4 py-3 border-t border-gray-100 flex items-center justify-between">
              <button
                onClick={() => setLegs([])}
                className="text-xs text-gray-400 hover:text-red-500 transition"
              >
                Clear all
              </button>
              <button
                onClick={analyseStrategy}
                disabled={loadingAnalysis || !legs.length}
                className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-lg text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50 transition"
              >
                {loadingAnalysis ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                Analyse Strategy
              </button>
            </div>
          </div>

          {/* ── RIGHT: Payoff ────────────────────────────────────────── */}
          <div className="flex-1 flex flex-col min-w-0 p-5">
            {!analysis ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-300">
                <BarChart2 className="w-14 h-14 mb-3" />
                <p className="text-sm font-semibold text-gray-400">No strategy yet</p>
                <p className="text-xs text-gray-300 mt-1">Add legs on the left and click Analyse Strategy</p>
              </div>
            ) : (
              <div className="flex flex-col gap-3 h-full">

                {/* Summary strip */}
                <div className="grid grid-cols-3 gap-2.5">
                  {(() => {
                    const np = analysis.payoff?.net_premium ?? 0;
                    const isCredit = np >= 0;
                    return (
                      <div className={`rounded-xl border p-3 ${isCredit ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200"}`}>
                        <div className="flex items-center justify-between mb-0.5">
                          <p className="text-[10px] font-semibold text-gray-500 uppercase">Net Premium</p>
                          <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full ${isCredit ? "bg-green-200 text-green-800" : "bg-red-200 text-red-700"}`}>
                            {isCredit ? "CREDIT" : "DEBIT"}
                          </span>
                        </div>
                        <p className={`text-base font-bold ${isCredit ? "text-green-700" : "text-red-600"}`}>{fmtINR(Math.abs(np))}</p>
                      </div>
                    );
                  })()}
                  <div className="bg-gray-50 rounded-xl border border-gray-100 p-3">
                    <p className="text-[10px] text-gray-400 uppercase mb-0.5">Max Profit</p>
                    <p className="text-base font-bold text-green-600">
                      {analysis.payoff?.max_profit != null ? fmtINR(analysis.payoff.max_profit) : "∞"}
                    </p>
                  </div>
                  <div className="bg-gray-50 rounded-xl border border-gray-100 p-3">
                    <p className="text-[10px] text-gray-400 uppercase mb-0.5">Max Loss</p>
                    <p className="text-base font-bold text-red-500">
                      {analysis.payoff?.max_loss != null ? fmtINR(analysis.payoff.max_loss) : "∞"}
                    </p>
                  </div>
                </div>

                {/* Breakevens */}
                {analysis.payoff?.breakevens?.length > 0 && (
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[10px] text-gray-400 uppercase font-semibold tracking-wide">Breakevens</span>
                    {analysis.payoff.breakevens.map((b: number, i: number) => (
                      <span key={i} className="text-xs font-mono bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-full">
                        ₹{b.toLocaleString("en-IN")}
                      </span>
                    ))}
                  </div>
                )}

                {/* P&L Chart */}
                <div className="flex-1 flex flex-col min-h-0">
                  <div className="flex items-center justify-between mb-1.5">
                    <p className="text-xs font-semibold text-gray-600">P&amp;L at Expiry</p>
                    <div className="flex gap-3 text-[10px] text-gray-400">
                      <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-indigo-500 inline-block rounded" /> P&amp;L</span>
                      <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-orange-400 inline-block" /> Spot</span>
                    </div>
                  </div>
                  <ResponsiveContainer width="100%" height={230}>
                    <LineChart data={analysis.payoff.spots.map((s: number, i: number) => ({
                      spot: s, pnl: analysis.payoff.payoffs[i],
                    }))}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" />
                      <XAxis dataKey="spot" tickFormatter={(v: number) => `₹${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 10 }} />
                      <YAxis tickFormatter={(v: number) => v >= 1e5 ? `${(v / 1e5).toFixed(1)}L` : v.toLocaleString("en-IN")} tick={{ fontSize: 10 }} width={55} />
                      <Tooltip
                        formatter={(v: number) => [fmtINR(v), "P&L"]}
                        labelFormatter={(l: number) => `Spot: ₹${Number(l).toLocaleString("en-IN")}`}
                        contentStyle={{ fontSize: 11, borderRadius: 8 }}
                      />
                      <ReferenceLine y={0} stroke="#d1d5db" strokeWidth={1} />
                      {spotInfo && (
                        <ReferenceLine x={spotInfo.spot} stroke="#f97316" strokeDasharray="4 2"
                          label={{ value: "Spot", fill: "#f97316", fontSize: 9 }} />
                      )}
                      {analysis.payoff.breakevens?.map((be: number, i: number) => (
                        <ReferenceLine key={i} x={be} stroke="#10b981" strokeDasharray="3 3"
                          label={{ value: "BE", fill: "#059669", fontSize: 9 }} />
                      ))}
                      <Line type="monotone" dataKey="pnl" stroke="#6366f1" strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} />
                    </LineChart>
                  </ResponsiveContainer>

                  {/* Heatmap */}
                  <PnlHeatmap
                    spots={analysis.payoff.spots}
                    payoffs={analysis.payoff.payoffs}
                    currentSpot={spotInfo?.spot}
                  />
                </div>
              </div>
            )}
          </div>

        </div>
      )}

      {/* ── TAB: Backtest ───────────────────────────────────────────────── */}
      {tab === "backtest" && (
        <div className="space-y-4">
          {/* Config */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <h3 className="font-semibold text-gray-800 mb-4">Backtest Configuration</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">Strategy</label>
                <select
                  value={btStrategy}
                  onChange={e => setBtStrategy(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                >
                  {PRESETS.map(s => (
                    <option key={s} value={s}>{PRESET_LABELS[s] ?? s}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">Start Date</label>
                <input type="date" value={btStart} onChange={e => setBtStart(e.target.value)}
                       className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">End Date</label>
                <input type="date" value={btEnd} onChange={e => setBtEnd(e.target.value)}
                       className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">Lots</label>
                <input type="number" min={1} max={50} value={btLots}
                       onChange={e => setBtLots(Number(e.target.value))}
                       className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">Entry DTE (days)</label>
                <input type="number" min={1} max={90} value={btEntryDte}
                       onChange={e => setBtEntryDte(Number(e.target.value))}
                       className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">Roll DTE (0 = hold)</label>
                <input type="number" min={0} max={30} value={btRollDte}
                       onChange={e => setBtRollDte(Number(e.target.value))}
                       className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">OTM Wing %</label>
                <input type="number" min={1} max={30} value={btOtmPct} step={0.5}
                       onChange={e => setBtOtmPct(Number(e.target.value))}
                       className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
            </div>

            <div className="mt-4 flex items-center gap-3">
              <button
                onClick={runBacktest}
                disabled={loadingBt}
                className="flex items-center gap-2 bg-indigo-600 text-white px-6 py-2 rounded-lg text-sm hover:bg-indigo-700 disabled:opacity-60 transition"
              >
                {loadingBt ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                {loadingBt ? "Running backtest…" : "Run Backtest"}
              </button>
              {loadingBt && (
                <span className="text-xs text-gray-400">
                  Fetching {symbol} history and simulating trades…
                </span>
              )}
            </div>
          </div>

          {btErr && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3">
              <AlertTriangle className="w-4 h-4 inline mr-2" />{btErr}
            </div>
          )}

          {/* Results */}
          {btResult && (
            <div className="space-y-4">
              {/* Metrics */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: "Total P&L",      val: fmtINR(btResult.metrics.total_pnl),         clrFn: clr(btResult.metrics.total_pnl) },
                  { label: "Win Rate",       val: pct(btResult.metrics.win_rate),              clrFn: "text-gray-900" },
                  { label: "Sharpe Ratio",   val: fmt(btResult.metrics.sharpe_ratio),          clrFn: clr(btResult.metrics.sharpe_ratio) },
                  { label: "Sortino Ratio",  val: fmt(btResult.metrics.sortino_ratio),         clrFn: clr(btResult.metrics.sortino_ratio) },
                  { label: "Profit Factor",  val: btResult.metrics.profit_factor != null ? fmt(btResult.metrics.profit_factor) : "∞",  clrFn: "text-gray-900" },
                  { label: "Max Drawdown",   val: fmtINR(btResult.metrics.max_drawdown),      clrFn: "text-red-600" },
                  { label: "Avg Win",        val: fmtINR(btResult.metrics.avg_win),            clrFn: "text-green-600" },
                  { label: "Avg Loss",       val: fmtINR(btResult.metrics.avg_loss),           clrFn: "text-red-600" },
                  { label: "Total Trades",   val: String(btResult.metrics.total_trades),       clrFn: "text-gray-900" },
                  { label: "Best Trade",     val: fmtINR(btResult.metrics.best_trade),         clrFn: "text-green-600" },
                  { label: "Worst Trade",    val: fmtINR(btResult.metrics.worst_trade),        clrFn: "text-red-600" },
                  { label: "Avg Trade",      val: fmtINR(btResult.metrics.avg_trade_pnl),      clrFn: clr(btResult.metrics.avg_trade_pnl) },
                ].map(m => (
                  <div key={m.label} className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
                    <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">{m.label}</p>
                    <p className={`text-lg font-bold ${m.clrFn}`}>{m.val}</p>
                  </div>
                ))}
              </div>

              {/* Equity curve */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
                <h3 className="font-semibold text-gray-800 mb-3">Equity Curve (Cumulative P&L)</h3>
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={btResult.equity_curve}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="date" tick={{ fontSize: 10 }}
                           tickFormatter={(d: string) => d.slice(0, 7)} />
                    <YAxis tickFormatter={(v: number) => fmtINR(v)} tick={{ fontSize: 10 }} />
                    <Tooltip
                      formatter={(v: number) => [fmtINR(v), "Cum P&L"]}
                      contentStyle={{ fontSize: 11, borderRadius: 8 }}
                    />
                    <ReferenceLine y={0} stroke="#9ca3af" />
                    <Line type="monotone" dataKey="cumulative_pnl"
                          stroke="#6366f1" strokeWidth={2} dot={false}
                          activeDot={{ r: 3 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* Trade log */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <div className="px-4 py-3 border-b border-gray-100">
                  <h3 className="font-semibold text-gray-800">Trade Log</h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full text-xs">
                    <thead className="bg-gray-50 text-gray-500 uppercase tracking-wide">
                      <tr>
                        {["Entry","Exit","Expiry","Spot In","Spot Out","IV%","Credit","Debit","Comm","P&L","Cum P&L"].map(h => (
                          <th key={h} className="px-3 py-2 text-left font-medium">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {btResult.trades.map((t: any, i: number) => (
                        <tr key={i} className="hover:bg-gray-50">
                          <td className="px-3 py-2 font-mono">{t.entry_date}</td>
                          <td className="px-3 py-2 font-mono">{t.exit_date}</td>
                          <td className="px-3 py-2 font-mono">{t.expiry}</td>
                          <td className="px-3 py-2 font-mono">{t.spot_entry?.toLocaleString("en-IN")}</td>
                          <td className="px-3 py-2 font-mono">{t.spot_exit?.toLocaleString("en-IN")}</td>
                          <td className="px-3 py-2">{t.iv_entry_pct?.toFixed(1)}%</td>
                          <td className="px-3 py-2 text-green-700">₹{t.entry_credit?.toFixed(0)}</td>
                          <td className="px-3 py-2 text-red-600">₹{t.exit_debit?.toFixed(0)}</td>
                          <td className="px-3 py-2 text-gray-400">₹{t.commission?.toFixed(0)}</td>
                          <td className={`px-3 py-2 font-bold ${clr(t.trade_pnl)}`}>
                            {fmtINR(t.trade_pnl)}
                          </td>
                          <td className={`px-3 py-2 font-bold ${clr(t.cumulative_pnl)}`}>
                            {fmtINR(t.cumulative_pnl)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── TAB: Risk Analysis ──────────────────────────────────────────── */}
      {tab === "risk" && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <h3 className="font-semibold text-gray-800 mb-4">Risk Analysis Parameters</h3>
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">VaR Horizon (trading days)</label>
                <input type="number" min={1} max={252} value={varHorizon}
                       onChange={e => setVarHorizon(Number(e.target.value))}
                       className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">Simulations</label>
                <select value={varSims} onChange={e => setVarSims(Number(e.target.value))}
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
                  {[1000, 5000, 10000, 20000].map(n => (
                    <option key={n} value={n}>{n.toLocaleString()}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">Confidence Level</label>
                <select value={varConf} onChange={e => setVarConf(Number(e.target.value))}
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
                  {[0.90, 0.95, 0.99].map(c => (
                    <option key={c} value={c}>{(c * 100).toFixed(0)}%</option>
                  ))}
                </select>
              </div>
            </div>
            <button
              onClick={runRisk}
              disabled={loadingRisk || !legs.length || !spotInfo || !analysis}
              className="flex items-center gap-2 bg-indigo-600 text-white px-6 py-2 rounded-lg text-sm hover:bg-indigo-700 disabled:opacity-60 transition"
            >
              {loadingRisk ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Shield className="w-4 h-4" />}
              {loadingRisk ? "Running…" : "Run Risk Analysis"}
            </button>
            {!legs.length && (
              <p className="text-xs text-amber-600 mt-2">
                Build a strategy and click Analyse Strategy first
              </p>
            )}
          </div>

          {riskErr && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3">
              <AlertTriangle className="w-4 h-4 inline mr-2" />{riskErr}
            </div>
          )}

          {varResult && (
            <div className="space-y-4">
              {/* VaR summary */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: `VaR (${(varConf * 100).toFixed(0)}%)`, val: fmtINR(varResult.var), color: "text-red-600" },
                  { label: "CVaR (Exp. Shortfall)", val: fmtINR(varResult.cvar), color: "text-red-700" },
                  { label: "Mean P&L", val: fmtINR(varResult.mean_pnl), color: clr(varResult.mean_pnl) },
                  { label: "Std Dev", val: fmtINR(varResult.std_pnl), color: "text-gray-700" },
                  { label: "Best Case (p99)", val: fmtINR(varResult.percentiles?.p99), color: "text-green-600" },
                  { label: "p75",              val: fmtINR(varResult.percentiles?.p75), color: "text-green-500" },
                  { label: "Median (p50)",     val: fmtINR(varResult.percentiles?.p50), color: clr(varResult.percentiles?.p50 ?? 0) },
                  { label: "Worst Case (p1)",  val: fmtINR(varResult.percentiles?.p1),  color: "text-red-600" },
                ].map(m => (
                  <div key={m.label} className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
                    <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">{m.label}</p>
                    <p className={`text-lg font-bold ${m.color}`}>{m.val}</p>
                  </div>
                ))}
              </div>

              {/* P&L Histogram */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
                <h3 className="font-semibold text-gray-800 mb-3">
                  P&L Distribution ({varResult.num_simulations.toLocaleString()} simulations)
                </h3>
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={varResult.histogram}
                            margin={{ top: 5, right: 20, left: 20, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="midpoint"
                           tickFormatter={(v: number) => v >= 1e5 ? `${(v / 1e5).toFixed(0)}L` : String(Math.round(v))}
                           tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 10 }} />
                    <Tooltip
                      formatter={(v: number, n: string) => [v, "Scenarios"]}
                      labelFormatter={(l: number) => `P&L: ${fmtINR(l)}`}
                      contentStyle={{ fontSize: 11, borderRadius: 8 }}
                    />
                    <ReferenceLine x={0} stroke="#9ca3af" />
                    <ReferenceLine x={-varResult.var} stroke="#ef4444" strokeDasharray="4 2"
                                   label={{ value: "VaR", fill: "#ef4444", fontSize: 10 }} />
                    <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                      {varResult.histogram.map((entry: any, i: number) => (
                        <Cell key={i}
                              fill={entry.midpoint >= 0 ? "#6366f1" : "#f87171"}
                              fillOpacity={0.8} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Scenario analysis matrix */}
          {scResult && (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
              <div className="flex items-center gap-2 mb-4">
                <h3 className="font-semibold text-gray-800">Scenario Analysis Matrix</h3>
                <span className="text-xs text-gray-400">(estimated P&L today — not at expiry)</span>
              </div>
              <div className="overflow-x-auto">
                <table className="text-xs border-collapse min-w-full">
                  <thead>
                    <tr>
                      <th className="border border-gray-200 bg-gray-50 px-3 py-2 text-gray-500">
                        Price ↓ / Vol →
                      </th>
                      {scResult.vol_shocks.map((v: number) => (
                        <th key={v}
                            className="border border-gray-200 bg-gray-50 px-3 py-2 text-gray-600 font-medium">
                          Vol {v > 0 ? "+" : ""}{v}%
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {scResult.matrix.map((row: any[], ri: number) => (
                      <tr key={ri}>
                        <td className="border border-gray-200 bg-gray-50 px-3 py-2 text-gray-600 font-medium">
                          Price {scResult.price_shocks[ri] > 0 ? "+" : ""}
                          {scResult.price_shocks[ri]}%
                        </td>
                        {row.map((cell: any, ci: number) => {
                          const v    = cell.pnl;
                          const abs  = Math.abs(v);
                          const norm = Math.min(abs / (Math.abs(scResult.matrix.flat().reduce((mx: number, c: any) => Math.max(mx, Math.abs(c.pnl)), 0)) || 1), 1);
                          const alpha = 0.15 + norm * 0.6;
                          const bg_c  = v > 0 ? `rgba(34,197,94,${alpha})` : v < 0 ? `rgba(239,68,68,${alpha})` : "rgb(249,250,251)";
                          return (
                            <td key={ci}
                                className="border border-gray-200 px-3 py-2 text-center font-mono"
                                style={{ background: bg_c }}>
                              {fmtINR(v)}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-gray-400 mt-2">
                Green = profit · Red = loss · Assumes no change in time to expiry
              </p>
            </div>
          )}
        </div>
      )}

      {/* ── AI Strategy Chat — right-side slide-in drawer ─────────────── */}

      {/* Backdrop — click outside to close */}
      {chatOpen && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => setChatOpen(false)}
        />
      )}

      {/* Drawer */}
      <div
        className={`fixed top-0 right-0 z-50 h-screen w-[380px] flex flex-col bg-white border-l border-gray-200 shadow-2xl
          transition-transform duration-300 ease-in-out
          ${chatOpen ? "translate-x-0" : "translate-x-full"}`}
      >
        {/* Drawer header */}
        <div className="flex items-center gap-2.5 px-4 py-3.5 border-b border-gray-100 bg-white">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-indigo-100">
            <Bot className="w-4.5 h-4.5 text-indigo-600" style={{ width: 18, height: 18 }} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-semibold text-sm text-gray-900 leading-tight">Options AI Assistant</p>
            <p className="text-xs text-gray-400 truncate">
              {spotInfo ? `${symbol} · ₹${spotInfo.spot.toLocaleString("en-IN")}` : "Ask me anything about options"}
            </p>
          </div>
          <button
            onClick={() => setChatOpen(false)}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0">
          {chatMsgs.length === 0 && (
            <div className="flex flex-col items-center pt-8 pb-4 px-2">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-md mb-4">
                <Bot className="w-8 h-8 text-white" />
              </div>
              <p className="text-base font-bold text-gray-800">Options AI Assistant</p>
              <p className="text-xs text-gray-400 mt-1 text-center leading-relaxed max-w-[260px]">
                Ask about Greeks, strategies, IV, or your current position
              </p>

              <div className="mt-5 w-full space-y-2">
                <p className="text-[10px] font-bold text-gray-300 uppercase tracking-widest text-center mb-2">Try asking</p>
                {[
                  { q: "What is an Iron Condor?",                        icon: "📐" },
                  { q: "Explain my strategy Greeks",                     icon: "🔢" },
                  { q: "Best NIFTY strategy for range-bound market?",    icon: "📊" },
                  { q: "Why is my net premium negative?",                icon: "❓" },
                ].map(({ q, icon }) => (
                  <button key={q} onClick={() => setChatInput(q)}
                    className="w-full flex items-center gap-2.5 text-left bg-gray-50 hover:bg-indigo-50 border border-gray-100 hover:border-indigo-200 rounded-xl px-3.5 py-2.5 transition group">
                    <span className="text-base">{icon}</span>
                    <span className="text-xs text-gray-600 group-hover:text-indigo-700 leading-snug">{q}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {chatMsgs.map((m, i) => (
            <div key={i} className={`flex gap-2.5 ${m.role === "user" ? "justify-end" : "justify-start"}`}>

              {/* AI avatar */}
              {m.role === "assistant" && (
                <div className="flex-shrink-0 w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-sm mt-0.5">
                  <Bot style={{ width: 14, height: 14 }} className="text-white" />
                </div>
              )}

              {m.role === "user" ? (
                /* User bubble */
                <div className="max-w-[80%] bg-indigo-600 text-white rounded-2xl rounded-tr-none px-3.5 py-2.5 shadow-sm">
                  <p className="text-sm leading-relaxed">{m.content}</p>
                </div>
              ) : (
                /* AI message — clean card with markdown */
                <div className="flex-1 min-w-0 bg-white border border-gray-100 rounded-2xl rounded-tl-none px-4 py-3 shadow-sm space-y-1">
                  {renderMd(m.content)}
                </div>
              )}

              {/* User avatar */}
              {m.role === "user" && (
                <div className="flex-shrink-0 w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center mt-0.5">
                  <span className="text-[10px] font-bold text-gray-500">YOU</span>
                </div>
              )}
            </div>
          ))}

          {chatLoading && (
            <div className="flex gap-2.5 justify-start">
              <div className="flex-shrink-0 w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-sm mt-0.5">
                <Bot style={{ width: 14, height: 14 }} className="text-white" />
              </div>
              <div className="bg-white border border-gray-100 rounded-2xl rounded-tl-none px-4 py-3 shadow-sm">
                <div className="flex gap-1.5 items-center">
                  <span className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Input */}
        <div className="border-t border-gray-100 p-3 flex gap-2 bg-white">
          <input
            type="text"
            value={chatInput}
            onChange={e => setChatInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), sendChat())}
            placeholder="Ask about options, Greeks, strategies…"
            className="flex-1 text-sm border border-gray-200 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
          <button
            onClick={sendChat}
            disabled={!chatInput.trim() || chatLoading}
            className="bg-indigo-600 text-white rounded-xl px-3 py-2 hover:bg-indigo-700 disabled:opacity-40 transition flex-shrink-0"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
