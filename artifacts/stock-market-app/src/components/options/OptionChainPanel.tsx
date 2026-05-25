import { useState, useEffect, useCallback } from "react";
import { fetchApi } from "@/lib/api";
import { useTheme } from "@/context/ThemeContext";
import { RefreshCw, AlertTriangle, Activity } from "lucide-react";

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

interface SpotInfo { spot: number; hv30: number; hv30_pct: number; lot_size: number; atm: number; }

// ── Client-side Black-Scholes Greeks ──────────────────────────────────────────
function ncdf(x: number): number {
  const a = [0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429];
  const sign = x >= 0 ? 1 : -1;
  const t = 1 / (1 + 0.2316419 * Math.abs(x));
  const poly = t * (a[0] + t * (a[1] + t * (a[2] + t * (a[3] + t * a[4]))));
  const val = 1 - poly * Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
  return sign === 1 ? val : 1 - val;
}
function npdf(x: number): number {
  return Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
}
function bsGreeks(S: number, K: number, T: number, r: number, sigma: number, type: "call" | "put") {
  if (T <= 0 || sigma <= 0 || S <= 0 || K <= 0) {
    return { delta: 0, gamma: 0, theta: 0, vega: 0 };
  }
  const sqrtT = Math.sqrt(T);
  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrtT);
  const d2 = d1 - sigma * sqrtT;
  const nd1 = ncdf(type === "call" ? d1 : -d1);
  const pd1 = npdf(d1);
  const delta = type === "call" ? nd1 : nd1 - 1;
  const gamma = pd1 / (S * sigma * sqrtT);
  const theta = (-(S * pd1 * sigma) / (2 * sqrtT) - r * K * Math.exp(-r * T) * ncdf(type === "call" ? d2 : -d2)) / 365;
  const vega  = S * pd1 * sqrtT / 100;
  return { delta, gamma, theta, vega };
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
  if (spot <    500) return 5;
  if (spot <   2000) return 10;
  if (spot <   5000) return 25;
  if (spot <  15000) return 50;
  if (spot <  50000) return 100;
  return 500;
}

// BANKNIFTY → Wednesday (3), FINNIFTY → Tuesday (2), everything else → Thursday (4)
function nextExpiries(symbol: string, count = 4): string[] {
  const sym = symbol.toUpperCase();
  const targetDay = sym === "BANKNIFTY" ? 3 : sym === "FINNIFTY" ? 2 : 4;
  const result: string[] = [];
  const d = new Date();
  const daysUntil = ((targetDay - d.getDay()) + 7) % 7 || 7;
  d.setDate(d.getDate() + daysUntil);
  const MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  for (let i = 0; i < count; i++) {
    result.push(`${String(d.getDate()).padStart(2,"0")}-${MON[d.getMonth()]}-${d.getFullYear()}`);
    d.setDate(d.getDate() + 7);
  }
  return result;
}

function generateSyntheticChain(
  spot: number, hv: number, T_years: number, halfDepth = 22
): { calls: ChainRow[]; puts: ChainRow[] } {
  const step  = strikeStep(spot);
  const atm   = Math.round(spot / step) * step;
  const r     = 0.07;
  // Round to nearest ₹0.05 tick (NSE convention)
  const rnd   = (v: number) => Math.round(v * 20) / 20;
  const calls: ChainRow[] = [];
  const puts:  ChainRow[] = [];
  for (let i = -halfDepth; i <= halfDepth; i++) {
    const K    = atm + i * step;
    if (K <= 0) continue;
    const mono = Math.abs(K - atm) / spot;
    // Indian market skew: OTM calls retain more value than OTM puts (reverse of US markets).
    // We apply a mild positive skew to calls and a flat/minimal skew to puts.
    const iv_c = Math.max(0.05, hv + 0.60 * mono);   // OTM calls: slight IV lift
    const iv_p = Math.max(0.05, hv + 0.15 * mono);   // OTM puts:  near-flat IV
    const cp   = bsPrice(spot, K, T_years, r, iv_c, "call");
    const pp   = bsPrice(spot, K, T_years, r, iv_p, "put");
    const sp   = (v: number) => Math.max(0.05, v * 0.004);
    const oi   = Math.max(0, Math.round(900_000 * Math.exp(-5 * mono)));
    calls.push({ strike: K, lastPrice: rnd(cp), bid: rnd(cp - sp(cp)), ask: rnd(cp + sp(cp)), iv: iv_c, oi, volume: Math.round(oi * 0.12), inTheMoney: K < spot });
    puts.push({  strike: K, lastPrice: rnd(pp), bid: rnd(pp - sp(pp)), ask: rnd(pp + sp(pp)), iv: iv_p, oi, volume: Math.round(oi * 0.12), inTheMoney: K > spot });
  }
  return { calls, puts };
}

// ── Add-leg button ────────────────────────────────────────────────────────────
type LegAction = "buy" | "sell";
type OptionType = "call" | "put";

interface AddLegArg {
  action: LegAction;
  option_type: OptionType;
  strike: number;
  premium: number;
  iv: number;
  lots: number;
  lot_size: number;
}

function AddBtn({
  action, type: optType, row, spotInfo, onAddLeg,
}: {
  action: LegAction; type: OptionType; row: ChainRow; spotInfo: SpotInfo | null; onAddLeg: (l: AddLegArg) => void;
}) {
  return (
    <button
      onClick={() => onAddLeg({
        action, option_type: optType, strike: row.strike,
        premium: row.lastPrice || (row.bid + row.ask) / 2 || 0,
        iv: row.iv || (spotInfo?.hv30 ?? 0.20),
        lots: 1, lot_size: spotInfo?.lot_size ?? 100,
      })}
      className={`px-1.5 py-0.5 text-[9px] font-black rounded border transition whitespace-nowrap
        ${action === "buy"
          ? "border-emerald-400 text-emerald-700 bg-emerald-50 hover:bg-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300"
          : "border-rose-400 text-rose-700 bg-rose-50 hover:bg-rose-200 dark:bg-rose-900/30 dark:text-rose-300"}`}
      title={`${action.toUpperCase()} ${optType.toUpperCase()} @ ${row.strike}`}
    >
      {action === "buy" ? "B" : "S"}
    </button>
  );
}

function fmtOI(n: number | undefined): string {
  if (!n) return "—";
  if (n >= 1e7) return `${(n / 1e7).toFixed(1)}Cr`;
  if (n >= 1e5) return `${(n / 1e5).toFixed(1)}L`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return String(n);
}
function fmtPx(n: number | undefined): string {
  if (!n) return "—";
  return n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ── Main Component ─────────────────────────────────────────────────────────────
export default function OptionChainPanel({
  symbol,
  spotInfo,
  T,
  onAddLeg,
}: {
  symbol: string;
  spotInfo: SpotInfo | null;
  T: number;
  onAddLeg: (leg: AddLegArg) => void;
}) {
  const { theme } = useTheme();
  const isDark = theme === "dark";

  const [expiries, setExpiries]     = useState<string[]>([]);
  const [selExpiry, setSelExpiry]   = useState<string>("");
  const [calls, setCalls]           = useState<ChainRow[]>([]);
  const [puts, setPuts]             = useState<ChainRow[]>([]);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState("");
  const [source, setSource]         = useState("");
  const [depth, setDepth]           = useState(12);
  const [isSynthetic, setIsSynthetic] = useState(false);

  const fetchChain = useCallback(async (sym: string, exp: string) => {
    if (!sym) return;
    setLoading(true);
    setError("");
    setIsSynthetic(false);
    try {
      const url = exp
        ? `/options/chain/${sym}?expiry=${encodeURIComponent(exp)}`
        : `/options/chain/${sym}`;
      const data = await fetchApi<any>(url);
      const chainData = data.chain || {};
      const newExpiries: string[] = data.expiries || [];
      setExpiries(newExpiries);
      setSource(data.source || "");

      const firstKey = exp && chainData[exp] ? exp : (newExpiries[0] || Object.keys(chainData)[0] || "");
      if (!exp && firstKey) setSelExpiry(firstKey);

      const entry = chainData[firstKey] || { calls: [], puts: [] };
      setCalls(entry.calls || []);
      setPuts(entry.puts || []);
    } catch (_e: any) {
      // Live chain unavailable (NSE blocked, Yahoo fallback failed).
      // Fall back to a theoretical Black-Scholes chain if spot data is present.
      if (spotInfo && spotInfo.spot > 0) {
        setIsSynthetic(true);
        setError("");
        const T_y = Math.max(T, 1) / 365;
        const synExp = nextExpiries(sym, 4);
        setExpiries(synExp);
        if (!exp) setSelExpiry(synExp[0]);
        const { calls: sc, puts: sp } = generateSyntheticChain(spotInfo.spot, spotInfo.hv30, T_y);
        setCalls(sc);
        setPuts(sp);
        setSource("Synthetic · BS");
      } else {
        // spotInfo not yet available — show a brief notice; the useEffect below will
        // regenerate once spotInfo arrives
        setError("Waiting for spot data — theoretical chain will appear shortly");
      }
    } finally {
      setLoading(false);
    }
  }, [spotInfo, T]); // eslint-disable-line

  useEffect(() => {
    if (symbol) {
      setCalls([]); setPuts([]);
      setSelExpiry("");
      setIsSynthetic(false);
      fetchChain(symbol, "");
    }
  }, [symbol]); // eslint-disable-line

  // Re-fetch on expiry change (for live chain); for synthetic, just regenerate locally
  useEffect(() => {
    if (selExpiry && symbol) {
      if (isSynthetic && spotInfo) {
        const T_y = Math.max(T, 1) / 365;
        const { calls: sc, puts: sp } = generateSyntheticChain(spotInfo.spot, spotInfo.hv30, T_y);
        setCalls(sc); setPuts(sp);
      } else {
        fetchChain(symbol, selExpiry);
      }
    }
  }, [selExpiry]); // eslint-disable-line

  // When spotInfo arrives late (symbol switched before spot loaded), regenerate or create synthetic
  useEffect(() => {
    if (!spotInfo || spotInfo.spot <= 0) return;
    const T_y = Math.max(T, 1) / 365;
    if (isSynthetic) {
      // Already synthetic — just update prices for new spot
      const { calls: sc, puts: sp } = generateSyntheticChain(spotInfo.spot, spotInfo.hv30, T_y);
      setCalls(sc); setPuts(sp);
    } else if (!calls.length && !puts.length) {
      // Had no data (live chain failed before spot arrived) — generate synthetic now
      setError("");
      setIsSynthetic(true);
      const synExp = nextExpiries(symbol, 4);
      setExpiries(synExp);
      setSelExpiry(synExp[0]);
      const { calls: sc, puts: sp } = generateSyntheticChain(spotInfo.spot, spotInfo.hv30, T_y);
      setCalls(sc); setPuts(sp);
      setSource("Synthetic · BS");
    } else if (error) {
      // spotInfo arrived after an error — generate synthetic and clear error
      setError("");
      setIsSynthetic(true);
      const synExp = nextExpiries(symbol, 4);
      setExpiries(synExp);
      if (!selExpiry) setSelExpiry(synExp[0]);
      const { calls: sc, puts: sp } = generateSyntheticChain(spotInfo.spot, spotInfo.hv30, T_y);
      setCalls(sc); setPuts(sp);
      setSource("Synthetic · BS");
    }
  }, [spotInfo?.spot]); // eslint-disable-line

  // Strike grid
  const atm = spotInfo?.atm ?? 0;
  const allStrikes = Array.from(new Set([...calls.map(c => c.strike), ...puts.map(p => p.strike)])).sort((a, b) => a - b);
  const atmIdx = atm > 0
    ? allStrikes.reduce((best, s, i) => Math.abs(s - atm) < Math.abs(allStrikes[best] - atm) ? i : best, 0)
    : Math.floor(allStrikes.length / 2);
  const lo = Math.max(0, atmIdx - depth);
  const hi = Math.min(allStrikes.length - 1, atmIdx + depth);
  const visStrikes = allStrikes.slice(lo, hi + 1);

  const callMap = Object.fromEntries(calls.map(c => [c.strike, c]));
  const putMap  = Object.fromEntries(puts.map(p => [p.strike, p]));

  const r       = 0.07;
  const T_years = Math.max(T, 1) / 365;

  // Styles
  const card  = isDark ? "bg-slate-800 border-slate-700"  : "bg-white border-gray-200";
  const head  = isDark ? "bg-slate-900/60 text-slate-400" : "bg-gray-50 text-gray-500";
  const muted = isDark ? "text-slate-500" : "text-gray-400";
  const divBorder = isDark ? "divide-slate-800/80" : "divide-gray-100";
  const atmRowBg  = isDark ? "bg-indigo-900/25" : "bg-indigo-50";

  return (
    <div className="flex flex-col h-full">

      {/* ── Compact toolbar (pinned) ─────────────────────────────────────────── */}
      <div className={`shrink-0 px-3 py-2 border-b flex flex-wrap items-center gap-2
        ${isDark ? "border-slate-700 bg-slate-900/30" : "border-gray-100 bg-gray-50/70"}`}>

        <div className="flex items-center gap-1.5">
          <span className={`text-[10px] font-bold uppercase tracking-widest ${muted}`}>Expiry</span>
          <select value={selExpiry} onChange={e => setSelExpiry(e.target.value)}
            className={`border rounded px-2 py-1 text-[11px] font-medium
              ${isDark ? "bg-slate-700 border-slate-600 text-slate-200" : "border-gray-200 text-gray-700 bg-white"}`}>
            {expiries.map(e => <option key={e} value={e}>{e}</option>)}
            {!expiries.length && <option value="">Loading…</option>}
          </select>
        </div>

        <div className="flex items-center gap-1">
          <span className={`text-[10px] font-bold uppercase tracking-widest ${muted}`}>Depth</span>
          {[8, 12, 16, 20].map(n => (
            <button key={n} onClick={() => setDepth(n)}
              className={`text-[10px] px-1.5 py-0.5 rounded border font-bold transition
                ${depth === n
                  ? "bg-indigo-600 text-white border-indigo-600"
                  : isDark ? "border-slate-600 text-slate-400 hover:border-indigo-400" : "border-gray-200 text-gray-500 hover:border-indigo-300"}`}>
              ±{n}
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-1.5">
          {source && (
            <span className={`text-[9px] px-1.5 py-0.5 rounded border font-medium ${
              isSynthetic
                ? isDark ? "border-amber-700/40 text-amber-400 bg-amber-900/20" : "border-amber-300 text-amber-700 bg-amber-50"
                : `${muted} ${isDark ? "border-slate-700" : "border-gray-200"}`
            }`}>
              {isSynthetic ? "⚡ " : ""}{source}
            </span>
          )}
          <button onClick={() => fetchChain(symbol, selExpiry)} disabled={loading}
            className={`flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold rounded border transition
              ${isDark ? "bg-slate-700 border-slate-600 text-slate-300 hover:bg-slate-600" : "bg-white border-gray-200 text-gray-500 hover:bg-gray-100"}`}>
            <RefreshCw className={`w-2.5 h-2.5 ${loading ? "animate-spin" : ""}`} /> Refresh
          </button>
        </div>
      </div>

      {/* ── Scrollable chain content ─────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">

        {/* Synthetic notice */}
        {isSynthetic && (
          <div className={`flex items-start gap-2 text-[10px] px-3 py-2 border-b
            ${isDark ? "bg-amber-950/20 border-amber-800/30 text-amber-400" : "bg-amber-50 border-amber-100 text-amber-700"}`}>
            <AlertTriangle className="w-3 h-3 shrink-0 mt-0.5" />
            <span><strong>Theoretical chain</strong> — NSE data unavailable. Prices via Black-Scholes (spot + HV30). B/S buttons work normally.</span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className={`flex items-center gap-2 text-xs px-3 py-2 border-b
            ${isDark ? "bg-rose-950/20 border-rose-800/30 text-rose-300" : "bg-red-50 border-red-100 text-red-700"}`}>
            <AlertTriangle className="w-3.5 h-3.5 shrink-0" /> {error}
          </div>
        )}

        {/* Loading skeleton */}
        {loading && !calls.length ? (
          <div className={`flex items-center justify-center h-40 gap-2 ${muted}`}>
            <RefreshCw className="w-4 h-4 animate-spin" />
            <span className="text-xs">Loading chain…</span>
          </div>
        ) : calls.length > 0 || puts.length > 0 ? (
          <>
            {/* ATM banner */}
            {atm > 0 && (
              <div className={`px-3 py-1 text-[10px] font-semibold flex items-center gap-2 sticky top-0 z-10
                ${isDark ? "bg-indigo-900/40 text-indigo-300 border-b border-indigo-800/40" : "bg-indigo-50 text-indigo-600 border-b border-indigo-100"}`}>
                <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 shrink-0" />
                ATM ₹{atm.toLocaleString("en-IN")}
                {spotInfo && <span className="opacity-60">· Spot ₹{spotInfo.spot.toLocaleString("en-IN")} · DTE {T}d</span>}
              </div>
            )}

            {/* 7-column headers: [BS] LTP IV | STRIKE | IV LTP [BS] */}
            <div className={`grid text-[8px] font-bold uppercase tracking-wide px-2 py-1 sticky ${atm > 0 ? "top-[26px]" : "top-0"} z-10 ${head}`}
              style={{ gridTemplateColumns: "56px 52px 36px 1fr 36px 52px 56px" }}>
              <div className={`text-center text-[8px] font-black col-span-3 ${isDark ? "text-blue-400" : "text-blue-600"}`}>── CALL ──</div>
              <div className={`text-center font-black ${isDark ? "text-indigo-400" : "text-indigo-600"}`}>STRIKE</div>
              <div className={`text-center text-[8px] font-black col-span-3 ${isDark ? "text-rose-400" : "text-rose-500"}`}>── PUT ──</div>
            </div>
            <div className={`grid text-[8px] font-bold uppercase tracking-wide px-2 pb-1 sticky ${atm > 0 ? "top-[38px]" : "top-[14px]"} z-10 ${head}`}
              style={{ gridTemplateColumns: "56px 52px 36px 1fr 36px 52px 56px" }}>
              <div className="text-center">B / S</div>
              <div className="text-right">LTP</div>
              <div className="text-right">IV%</div>
              <div />
              <div className="text-left">IV%</div>
              <div className="text-left pl-1">LTP</div>
              <div className="text-center">B / S</div>
            </div>

            {/* Strike rows */}
            <div className={`divide-y ${divBorder}`}>
              {visStrikes.map(strike => {
                const call = callMap[strike];
                const put  = putMap[strike];
                const isAtm = strike === allStrikes[atmIdx];
                const rowBg = isAtm
                  ? atmRowBg
                  : call?.inTheMoney
                    ? isDark ? "bg-slate-800/40" : "bg-blue-50/30"
                    : "";

                return (
                  <div key={strike}
                    style={{ gridTemplateColumns: "56px 52px 36px 1fr 36px 52px 56px" }}
                    className={`grid px-2 py-[3px] items-center ${rowBg}`}>

                    {/* CALL: B/S */}
                    <div className="flex items-center justify-center gap-0.5">
                      {call ? (
                        <><AddBtn action="sell" type="call" row={call} spotInfo={spotInfo} onAddLeg={onAddLeg} />
                          <AddBtn action="buy"  type="call" row={call} spotInfo={spotInfo} onAddLeg={onAddLeg} /></>
                      ) : <span className={`text-[9px] ${muted}`}>—</span>}
                    </div>
                    {/* CALL: LTP */}
                    <div className={`text-right font-mono font-semibold text-[11px] ${isDark ? "text-slate-200" : "text-gray-800"}`}>
                      {call ? fmtPx(call.lastPrice) : <span className={muted}>—</span>}
                    </div>
                    {/* CALL: IV% */}
                    <div className={`text-right font-mono text-[10px] ${call?.iv ? isDark ? "text-amber-400" : "text-amber-600" : muted}`}>
                      {call?.iv ? `${(call.iv * 100).toFixed(0)}` : "—"}
                    </div>
                    {/* STRIKE (centre) */}
                    <div className={`text-center mx-1 font-bold rounded text-[11px] py-0.5
                      ${isAtm ? "bg-indigo-600 text-white" : isDark ? "text-slate-300" : "text-gray-700"}`}>
                      {strike.toLocaleString("en-IN")}
                    </div>
                    {/* PUT: IV% */}
                    <div className={`text-left font-mono text-[10px] ${put?.iv ? isDark ? "text-amber-400" : "text-amber-600" : muted}`}>
                      {put?.iv ? `${(put.iv * 100).toFixed(0)}` : "—"}
                    </div>
                    {/* PUT: LTP */}
                    <div className={`text-left pl-1 font-mono font-semibold text-[11px] ${isDark ? "text-slate-200" : "text-gray-800"}`}>
                      {put ? fmtPx(put.lastPrice) : <span className={muted}>—</span>}
                    </div>
                    {/* PUT: B/S */}
                    <div className="flex items-center justify-center gap-0.5">
                      {put ? (
                        <><AddBtn action="buy"  type="put" row={put} spotInfo={spotInfo} onAddLeg={onAddLeg} />
                          <AddBtn action="sell" type="put" row={put} spotInfo={spotInfo} onAddLeg={onAddLeg} /></>
                      ) : <span className={`text-[9px] ${muted}`}>—</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        ) : !loading && !error ? (
          <div className={`flex flex-col items-center justify-center h-32 gap-2 ${muted}`}>
            <Activity className="w-7 h-7 opacity-20" />
            <p className="text-xs">No chain data for {symbol}</p>
          </div>
        ) : null}

        <p className={`text-[9px] ${muted} text-center py-2 px-2`}>
          B = Buy · S = Sell · Δ = Delta · Θ = Theta/day
        </p>
      </div>
    </div>
  );
}
