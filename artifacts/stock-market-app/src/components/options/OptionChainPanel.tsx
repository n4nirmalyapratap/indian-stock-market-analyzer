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

  const fetchChain = useCallback(async (sym: string, exp: string) => {
    if (!sym) return;
    setLoading(true);
    setError("");
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
    } catch (e: any) {
      setError(e?.message || "Failed to load option chain");
    } finally {
      setLoading(false);
    }
  }, []); // eslint-disable-line

  useEffect(() => {
    if (symbol) {
      setCalls([]); setPuts([]);
      setSelExpiry("");
      fetchChain(symbol, "");
    }
  }, [symbol]); // eslint-disable-line

  // Re-fetch on expiry change
  useEffect(() => {
    if (selExpiry && symbol) fetchChain(symbol, selExpiry);
  }, [selExpiry]); // eslint-disable-line

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
    <div className="flex flex-col gap-3">

      {/* ── Toolbar ──────────────────────────────────────────────────────────── */}
      <div className={`rounded-xl border ${card} px-4 py-3 flex flex-wrap items-center gap-3`}>
        <div className="flex items-center gap-2">
          <span className={`text-xs font-semibold ${muted} uppercase tracking-wide`}>Expiry</span>
          <select
            value={selExpiry}
            onChange={e => setSelExpiry(e.target.value)}
            className={`border rounded-lg px-3 py-1.5 text-sm font-medium transition
              ${isDark ? "bg-slate-700 border-slate-600 text-slate-200" : "border-gray-200 text-gray-700 bg-white"}`}
          >
            {expiries.map(e => <option key={e} value={e}>{e}</option>)}
            {!expiries.length && <option value="">Loading…</option>}
          </select>
        </div>

        <div className="flex items-center gap-1.5">
          <span className={`text-xs font-semibold ${muted} uppercase tracking-wide`}>Depth</span>
          {[8, 12, 16, 20].map(n => (
            <button key={n} onClick={() => setDepth(n)}
              className={`text-xs px-2 py-1 rounded border font-semibold transition
                ${depth === n
                  ? "bg-indigo-600 text-white border-indigo-600"
                  : isDark ? "border-slate-600 text-slate-400 hover:border-indigo-400" : "border-gray-200 text-gray-500 hover:border-indigo-300"}`}>
              ±{n}
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          {source && (
            <span className={`text-[10px] ${muted} px-2 py-0.5 rounded-full border ${isDark ? "border-slate-700" : "border-gray-200"}`}>
              via {source}
            </span>
          )}
          <button
            onClick={() => fetchChain(symbol, selExpiry)}
            disabled={loading}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition
              ${isDark ? "bg-slate-700 text-slate-300 hover:bg-slate-600" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
          >
            <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className={`flex items-center gap-2 text-sm rounded-xl px-4 py-3 border
          ${isDark ? "bg-rose-950/30 border-rose-800 text-rose-300" : "bg-red-50 border-red-200 text-red-700"}`}>
          <AlertTriangle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}

      {loading && !calls.length ? (
        <div className={`flex items-center justify-center h-48 gap-2 ${muted}`}>
          <RefreshCw className="w-5 h-5 animate-spin" />
          <span className="text-sm">Loading option chain…</span>
        </div>
      ) : (
        <div className={`rounded-2xl border overflow-hidden ${isDark ? "border-slate-700" : "border-gray-200"}`}>

          {/* ATM banner */}
          {atm > 0 && (
            <div className={`px-4 py-1.5 text-xs font-semibold flex items-center gap-3
              ${isDark ? "bg-indigo-900/40 text-indigo-300 border-b border-indigo-800/40" : "bg-indigo-50 text-indigo-700 border-b border-indigo-100"}`}>
              <span className="w-2 h-2 rounded-full bg-indigo-500 shrink-0" />
              ATM ₹{atm.toLocaleString("en-IN")}
              {spotInfo && <span className="opacity-60">· Spot ₹{spotInfo.spot.toLocaleString("en-IN")} · DTE {T}d</span>}
            </div>
          )}

          {/* Column headers */}
          <div className={`grid text-[9px] font-bold uppercase tracking-wide px-2 py-1.5 ${head}`}
            style={{ gridTemplateColumns: "1fr 68px 58px 42px 38px 38px 80px 38px 38px 42px 58px 68px 1fr" }}>
            <div className="text-right pr-1">Actions</div>
            <div className="text-right pr-1">LTP</div>
            <div className="text-right pr-1">OI</div>
            <div className="text-right pr-1">IV%</div>
            <div className="text-right pr-1">Δ</div>
            <div className="text-right pr-1">Θ</div>
            <div className="text-center text-indigo-500">CALL ↔ STRIKE ↔ PUT</div>
            <div className="text-left pl-1">Δ</div>
            <div className="text-left pl-1">Θ</div>
            <div className="text-left pl-1">IV%</div>
            <div className="text-left pl-1">OI</div>
            <div className="text-left pl-1">LTP</div>
            <div className="text-left pl-1">Actions</div>
          </div>

          {/* Strike rows */}
          <div className={`divide-y ${divBorder}`}>
            {visStrikes.map(strike => {
              const call = callMap[strike];
              const put  = putMap[strike];
              const isAtm = strike === allStrikes[atmIdx];
              const S = spotInfo?.spot ?? 0;
              const hv = spotInfo?.hv30 ?? 0.20;
              const cG = call && S > 0 ? bsGreeks(S, strike, T_years, r, call.iv || hv, "call") : null;
              const pG = put  && S > 0 ? bsGreeks(S, strike, T_years, r, put.iv  || hv, "put")  : null;

              const rowBg = isAtm
                ? atmRowBg
                : call?.inTheMoney
                  ? isDark ? "bg-slate-800/60" : "bg-blue-50/20"
                  : "";

              return (
                <div
                  key={strike}
                  style={{ gridTemplateColumns: "1fr 68px 58px 42px 38px 38px 80px 38px 38px 42px 58px 68px 1fr" }}
                  className={`grid px-2 py-1 text-xs items-center ${rowBg}`}
                >
                  {/* CALL: Actions (B/S) */}
                  <div className="flex items-center justify-end gap-1 pr-1">
                    {call ? (
                      <>
                        <AddBtn action="sell" type="call" row={call} spotInfo={spotInfo} onAddLeg={onAddLeg} />
                        <AddBtn action="buy"  type="call" row={call} spotInfo={spotInfo} onAddLeg={onAddLeg} />
                      </>
                    ) : <span className={muted}>—</span>}
                  </div>

                  {/* CALL: LTP */}
                  <div className={`text-right pr-1 font-mono font-semibold text-[11px] ${isDark ? "text-slate-200" : "text-gray-800"}`}>
                    {call ? fmtPx(call.lastPrice) : "—"}
                  </div>

                  {/* CALL: OI */}
                  <div className={`text-right pr-1 font-mono text-[10px] ${muted}`}>{call ? fmtOI(call.oi) : "—"}</div>

                  {/* CALL: IV */}
                  <div className={`text-right pr-1 font-mono text-[10px] ${call?.iv ? "text-amber-600 dark:text-amber-400" : muted}`}>
                    {call?.iv ? `${(call.iv * 100).toFixed(1)}` : "—"}
                  </div>

                  {/* CALL: Delta */}
                  <div className={`text-right pr-1 font-mono text-[10px] ${cG && cG.delta > 0.5 ? "text-indigo-500" : muted}`}>
                    {cG ? cG.delta.toFixed(2) : "—"}
                  </div>

                  {/* CALL: Theta */}
                  <div className={`text-right pr-1 font-mono text-[10px] ${muted}`}>
                    {cG ? cG.theta.toFixed(1) : "—"}
                  </div>

                  {/* STRIKE (centre) */}
                  <div className={`text-center font-bold py-0.5 px-1 rounded text-xs
                    ${isAtm ? "bg-indigo-600 text-white" : isDark ? "text-slate-200" : "text-gray-700"}`}>
                    {strike.toLocaleString("en-IN")}
                  </div>

                  {/* PUT: Delta */}
                  <div className={`text-left pl-1 font-mono text-[10px] ${pG && Math.abs(pG.delta) > 0.5 ? "text-rose-500" : muted}`}>
                    {pG ? pG.delta.toFixed(2) : "—"}
                  </div>

                  {/* PUT: Theta */}
                  <div className={`text-left pl-1 font-mono text-[10px] ${muted}`}>
                    {pG ? pG.theta.toFixed(1) : "—"}
                  </div>

                  {/* PUT: IV */}
                  <div className={`text-left pl-1 font-mono text-[10px] ${put?.iv ? "text-amber-600 dark:text-amber-400" : muted}`}>
                    {put?.iv ? `${(put.iv * 100).toFixed(1)}` : "—"}
                  </div>

                  {/* PUT: OI */}
                  <div className={`text-left pl-1 font-mono text-[10px] ${muted}`}>{put ? fmtOI(put.oi) : "—"}</div>

                  {/* PUT: LTP */}
                  <div className={`text-left pl-1 font-mono font-semibold text-[11px] ${isDark ? "text-slate-200" : "text-gray-800"}`}>
                    {put ? fmtPx(put.lastPrice) : "—"}
                  </div>

                  {/* PUT: Actions (B/S) */}
                  <div className="flex items-center gap-1 pl-1">
                    {put ? (
                      <>
                        <AddBtn action="buy"  type="put" row={put} spotInfo={spotInfo} onAddLeg={onAddLeg} />
                        <AddBtn action="sell" type="put" row={put} spotInfo={spotInfo} onAddLeg={onAddLeg} />
                      </>
                    ) : <span className={muted}>—</span>}
                  </div>
                </div>
              );
            })}
          </div>

        </div>
      )}

      {!loading && !calls.length && !puts.length && !error && (
        <div className={`flex flex-col items-center justify-center h-32 gap-2 ${muted}`}>
          <Activity className="w-8 h-8 opacity-20" />
          <p className="text-sm">No option chain data available for {symbol}</p>
        </div>
      )}

      <p className={`text-[10px] ${muted} text-center`}>
        B = Buy · S = Sell · Click any button to add leg to strategy basket · Δ = Delta · Θ = Theta/day
      </p>
    </div>
  );
}
