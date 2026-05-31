/**
 * FOAnalyticsPanel — six derivative analytics that drop in next to
 * the options chain table on the OptionsStrategyTester page.
 *
 *   1. Max Pain        — bar chart of total pain per strike + the
 *                        "magnet" strike highlighted
 *   2. OI Buildup      — classification table (Long buildup / Short
 *                        buildup / Long unwinding / Short covering)
 *   3. PCR history     — multi-day intraday PCR line chart
 *   4. IV Smile        — call IV / put IV curves across strikes
 *   5. Unusual Activity — strikes flagged by volume / OI-change
 *                        z-score
 *   6. Strategy Heatmap — best 1- or 2-leg setup per strike, colored
 *                        by reward/risk ratio
 *
 * The panel fetches `/api/options/analytics/{symbol}?expiry=...` once,
 * and the PCR history endpoint separately (different cadence — the
 * scheduler writes a snapshot every 15 min during market hours). All
 * computations live server-side; this file is rendering only.
 */
import { useQuery } from "@tanstack/react-query";
import {
  ResponsiveContainer, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine, Cell,
} from "recharts";
import {
  Loader2, AlertCircle, TrendingUp, TrendingDown, Activity, Zap, Target, Layers,
} from "lucide-react";

import { fetchApi } from "@/lib/api";


// ── Types (kept inline since they're internal to this panel) ────────────────


interface MaxPainBar  { strike: number; callPain: number; putPain: number; totalPain: number; }
interface SmilePoint  { strike: number; callIV: number | null; putIV: number | null; isATM: boolean; }
interface BuildupRow  {
  strike: number; price: number; priceChange: number;
  oi: number; oiChange: number; classification: string;
}
interface UnusualRow  {
  strike: number; type: "CE" | "PE"; volume: number; volumeZ: number;
  oiChange: number; oiChangeZ: number; lastPrice: number | null; iv: number;
  reason: string;
}
interface StrategyRow {
  strike: number; best: string | null; rr: number;
  maxProfit: number | null; maxLoss: number | null;
  moneyness: "ITM" | "ATM" | "OTM";
}

interface AnalyticsResponse {
  symbol:    string;
  spot:      number;
  expiry:    string;
  expiries:  string[];
  source:    string | null;
  analytics: {
    maxPain:   { maxPainStrike: number | null; byStrike: MaxPainBar[] };
    oiBuildup: { calls: BuildupRow[]; puts: BuildupRow[] };
    smile:     SmilePoint[];
    unusual:   UnusualRow[];
    strategy:  StrategyRow[];
  };
}

interface PcrHistoryResponse {
  symbol:        string;
  expiry_index:  number;
  hours:         number;
  count:         number;
  series:        Array<{
    fetchedAtMs: number;
    pcrOi:       number | null;
    pcrVolume:   number | null;
    spot:        number | null;
    expiry:      string | null;
  }>;
}


// ── Helpers ─────────────────────────────────────────────────────────────────


const fmtCompact = (n: number) =>
  n == null || isNaN(n) ? "—" :
  Math.abs(n) >= 1e7 ? `${(n / 1e7).toFixed(1)}Cr` :
  Math.abs(n) >= 1e5 ? `${(n / 1e5).toFixed(1)}L` :
  Math.abs(n) >= 1e3 ? `${(n / 1e3).toFixed(1)}K` :
  n.toFixed(0);

function fmtTime(ms: number): string {
  const d = new Date(ms);
  // IST display: hh:mm dd-MMM
  return d.toLocaleString("en-IN", {
    hour: "2-digit", minute: "2-digit", day: "2-digit", month: "short",
    timeZone: "Asia/Kolkata",
  });
}

function classificationStyle(c: string): { bg: string; fg: string; bias: string } {
  switch (c) {
    case "Long Buildup":   return { bg: "bg-emerald-50 dark:bg-emerald-900/20", fg: "text-emerald-700 dark:text-emerald-300", bias: "Bullish" };
    case "Short Buildup":  return { bg: "bg-rose-50 dark:bg-rose-900/20",       fg: "text-rose-700 dark:text-rose-300",       bias: "Bearish" };
    case "Long Unwinding": return { bg: "bg-amber-50 dark:bg-amber-900/20",     fg: "text-amber-700 dark:text-amber-300",     bias: "Bearish" };
    case "Short Covering": return { bg: "bg-sky-50 dark:bg-sky-900/20",         fg: "text-sky-700 dark:text-sky-300",         bias: "Bullish" };
    default:               return { bg: "bg-gray-50 dark:bg-gray-800",          fg: "text-gray-500",                          bias: "Neutral" };
  }
}

function rrColor(rr: number): string {
  if (rr >= 3)   return "#059669"; // strong
  if (rr >= 1.5) return "#10b981"; // good
  if (rr >= 1)   return "#fbbf24"; // neutral
  if (rr > 0)    return "#f97316"; // poor
  return "#9ca3af";                // no data
}


// ── Section: Max Pain ───────────────────────────────────────────────────────


function MaxPainSection({ data, spot }: {
  data: AnalyticsResponse["analytics"]["maxPain"]; spot: number;
}) {
  const { maxPainStrike, byStrike } = data;
  if (!byStrike.length) return null;

  // For the bar chart, plot total pain. The max-pain strike is the trough.
  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl p-4">
      <div className="flex items-baseline justify-between mb-3 flex-wrap gap-2">
        <div>
          <h4 className="text-sm font-bold text-gray-900 dark:text-white flex items-center gap-1.5">
            <Target className="w-3.5 h-3.5 text-indigo-500" />
            Max Pain
          </h4>
          <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
            Strike where option writers lose the least if spot settles there.
            Market often "magnetises" to this on expiry day.
          </p>
        </div>
        <div className="flex items-baseline gap-2 px-3 py-1.5 rounded-md bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-200 dark:border-indigo-500/20">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-indigo-600 dark:text-indigo-300">Max pain</span>
          <span className="text-lg font-bold text-indigo-700 dark:text-indigo-200 tabular-nums">
            {maxPainStrike ?? "—"}
          </span>
          {maxPainStrike && spot && (
            <span className={`text-[10px] ${
              maxPainStrike > spot ? "text-emerald-600 dark:text-emerald-400"
              : maxPainStrike < spot ? "text-rose-600 dark:text-rose-400"
              : "text-gray-400"
            }`}>
              {maxPainStrike > spot ? `▲ ${(maxPainStrike - spot).toFixed(1)} above`
               : maxPainStrike < spot ? `▼ ${(spot - maxPainStrike).toFixed(1)} below`
               : "= spot"}
            </span>
          )}
        </div>
      </div>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={byStrike} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" strokeOpacity={0.3} />
            <XAxis dataKey="strike" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 10 }} tickFormatter={fmtCompact} width={50} />
            <Tooltip
              contentStyle={{ background: "rgba(17,24,39,0.96)", border: "none", borderRadius: 6, color: "#fff", fontSize: 12 }}
              formatter={(v: number, k: string) => [fmtCompact(v), k === "totalPain" ? "Total" : k]}
              labelFormatter={(l) => `Strike ${l}`}
            />
            <ReferenceLine x={spot} stroke="#6366f1" strokeDasharray="3 3" label={{ value: "Spot", fill: "#6366f1", fontSize: 10 }} />
            {maxPainStrike != null && (
              <ReferenceLine x={maxPainStrike} stroke="#10b981" strokeDasharray="3 3" label={{ value: "Max Pain", fill: "#10b981", fontSize: 10, position: "insideTopRight" }} />
            )}
            <Bar dataKey="totalPain">
              {byStrike.map((row) => (
                <Cell key={row.strike} fill={row.strike === maxPainStrike ? "#10b981" : "#a3a3a3"} fillOpacity={row.strike === maxPainStrike ? 1 : 0.6} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}


// ── Section: PCR History ────────────────────────────────────────────────────


function PcrHistorySection({ symbol }: { symbol: string }) {
  const { data, isLoading } = useQuery<PcrHistoryResponse>({
    queryKey: ["options-pcr-history", symbol],
    queryFn:  () => fetchApi(`/options/pcr-history/${encodeURIComponent(symbol)}?hours=72`),
    staleTime: 5 * 60 * 1000,
  });

  const series = (data?.series ?? []).filter(p => p.pcrOi != null);
  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl p-4">
      <div className="flex items-baseline justify-between mb-3 flex-wrap gap-2">
        <div>
          <h4 className="text-sm font-bold text-gray-900 dark:text-white flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5 text-indigo-500" />
            PCR Time-Series (72h)
          </h4>
          <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
            PCR crossing 1.0 from below often coincides with intraday capitulation;
            crossing from above suggests rally exhaustion.
          </p>
        </div>
        {series.length > 0 && (
          <div className="flex items-baseline gap-2 px-3 py-1.5 rounded-md bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-200 dark:border-indigo-500/20">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-indigo-600 dark:text-indigo-300">Now</span>
            <span className="text-lg font-bold text-indigo-700 dark:text-indigo-200 tabular-nums">
              {series[series.length - 1].pcrOi?.toFixed(2)}
            </span>
          </div>
        )}
      </div>
      {isLoading ? (
        <div className="py-8 text-center text-gray-400 dark:text-gray-500 text-sm">
          <Loader2 className="inline w-3.5 h-3.5 animate-spin mr-1.5" /> Loading…
        </div>
      ) : series.length < 2 ? (
        <div className="py-8 text-center text-gray-400 dark:text-gray-500 text-sm">
          <AlertCircle className="inline w-3.5 h-3.5 mr-1.5" />
          Scheduler builds history every 15 min during market hours. Check back after a session.
        </div>
      ) : (
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={series} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" strokeOpacity={0.3} />
              <XAxis dataKey="fetchedAtMs" tick={{ fontSize: 10 }} tickFormatter={fmtTime} minTickGap={40} />
              <YAxis tick={{ fontSize: 10 }} width={45} domain={["auto", "auto"]} />
              <ReferenceLine y={1} stroke="#9ca3af" strokeDasharray="3 3" label={{ value: "1.0", fontSize: 9, fill: "#9ca3af" }} />
              <Tooltip
                contentStyle={{ background: "rgba(17,24,39,0.96)", border: "none", borderRadius: 6, color: "#fff", fontSize: 12 }}
                labelFormatter={(l) => fmtTime(l as number)}
                formatter={(v: number) => [v?.toFixed(2), "PCR (OI)"]}
              />
              <Line type="monotone" dataKey="pcrOi" stroke="#6366f1" strokeWidth={1.75} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}


// ── Section: IV Smile ───────────────────────────────────────────────────────


function IVSmileSection({ smile, spot }: { smile: SmilePoint[]; spot: number }) {
  const data = smile.filter(p => p.callIV != null || p.putIV != null);
  if (data.length < 3) return null;
  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl p-4">
      <div className="mb-3">
        <h4 className="text-sm font-bold text-gray-900 dark:text-white flex items-center gap-1.5">
          <TrendingUp className="w-3.5 h-3.5 text-indigo-500" />
          IV Smile / Skew
        </h4>
        <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
          Flat = boring. Smile = tail-risk priced in. Skew = directional bias.
        </p>
      </div>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" strokeOpacity={0.3} />
            <XAxis dataKey="strike" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 10 }} width={45} unit="%" />
            <ReferenceLine x={spot} stroke="#6366f1" strokeDasharray="3 3" label={{ value: "Spot", fill: "#6366f1", fontSize: 10 }} />
            <Tooltip
              contentStyle={{ background: "rgba(17,24,39,0.96)", border: "none", borderRadius: 6, color: "#fff", fontSize: 12 }}
              formatter={(v: number, n: string) => [v != null ? `${v.toFixed(2)}%` : "—", n === "callIV" ? "Call IV" : "Put IV"]}
              labelFormatter={(l) => `Strike ${l}`}
            />
            <Line type="monotone" dataKey="callIV" stroke="#10b981" strokeWidth={1.75} dot={false} connectNulls />
            <Line type="monotone" dataKey="putIV"  stroke="#f43f5e" strokeWidth={1.75} dot={false} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="flex items-center gap-4 mt-1 text-[10px] text-gray-500 dark:text-gray-400">
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500" /> Call IV</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-rose-500" /> Put IV</span>
      </div>
    </div>
  );
}


// ── Section: OI Buildup ─────────────────────────────────────────────────────


function OIBuildupSection({ data, spot }: {
  data: AnalyticsResponse["analytics"]["oiBuildup"]; spot: number;
}) {
  // Only show strikes within ±10% of spot — closer strikes are where
  // the real positioning happens; the tails just dilute the signal.
  const filter = (rows: BuildupRow[]) =>
    rows.filter(r => spot && Math.abs(r.strike - spot) / spot < 0.10)
        .filter(r => r.oiChange !== 0)
        .sort((a, b) => Math.abs(b.oiChange) - Math.abs(a.oiChange))
        .slice(0, 10);
  const calls = filter(data.calls);
  const puts  = filter(data.puts);
  if (!calls.length && !puts.length) return null;

  const Row = ({ r }: { r: BuildupRow }) => {
    const s = classificationStyle(r.classification);
    return (
      <tr className="border-t border-gray-100 dark:border-white/5">
        <td className="px-3 py-1.5 font-semibold tabular-nums">{r.strike}</td>
        <td className="px-3 py-1.5 tabular-nums text-right">{r.price?.toFixed(2)}</td>
        <td className={`px-3 py-1.5 tabular-nums text-right ${r.priceChange >= 0 ? "text-emerald-600" : "text-rose-600"}`}>
          {r.priceChange >= 0 ? "+" : ""}{r.priceChange?.toFixed(2)}
        </td>
        <td className="px-3 py-1.5 tabular-nums text-right">{fmtCompact(r.oi)}</td>
        <td className={`px-3 py-1.5 tabular-nums text-right ${r.oiChange >= 0 ? "text-emerald-600" : "text-rose-600"}`}>
          {r.oiChange >= 0 ? "+" : ""}{fmtCompact(r.oiChange)}
        </td>
        <td className={`px-3 py-1.5 text-[11px] font-medium ${s.fg}`}>
          <span className={`px-1.5 py-0.5 rounded ${s.bg}`}>{r.classification}</span>
          <span className="ml-1.5 text-[10px] text-gray-400">{s.bias}</span>
        </td>
      </tr>
    );
  };

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl">
      <div className="px-4 py-3 border-b border-gray-100 dark:border-white/[0.06]">
        <h4 className="text-sm font-bold text-gray-900 dark:text-white flex items-center gap-1.5">
          <Layers className="w-3.5 h-3.5 text-indigo-500" />
          OI Buildup (top movers near spot)
        </h4>
        <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
          Price↑+OI↑ = Long buildup · Price↓+OI↑ = Short buildup · Price↑+OI↓ = Short covering · Price↓+OI↓ = Long unwinding
        </p>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-px bg-gray-100 dark:bg-white/5">
        {[{ label: "Calls", rows: calls }, { label: "Puts", rows: puts }].map(({ label, rows }) => (
          <div key={label} className="bg-white dark:bg-gray-900">
            <p className="px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-gray-500 dark:text-gray-400">{label}</p>
            <table className="w-full text-xs">
              <thead className="bg-gray-50 dark:bg-gray-800/40 text-gray-500 text-[10px]">
                <tr>
                  <th className="px-3 py-1.5 text-left">Strike</th>
                  <th className="px-3 py-1.5 text-right">Price</th>
                  <th className="px-3 py-1.5 text-right">ΔPrice</th>
                  <th className="px-3 py-1.5 text-right">OI</th>
                  <th className="px-3 py-1.5 text-right">ΔOI</th>
                  <th className="px-3 py-1.5 text-left">Signal</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0
                  ? <tr><td colSpan={6} className="px-3 py-3 text-center text-gray-400 text-[11px]">No OI changes near spot</td></tr>
                  : rows.map(r => <Row key={r.strike} r={r} />)}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </div>
  );
}


// ── Section: Unusual Activity ───────────────────────────────────────────────


function UnusualSection({ rows }: { rows: UnusualRow[] }) {
  if (!rows.length) return null;
  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl">
      <div className="px-4 py-3 border-b border-gray-100 dark:border-white/[0.06]">
        <h4 className="text-sm font-bold text-gray-900 dark:text-white flex items-center gap-1.5">
          <Zap className="w-3.5 h-3.5 text-amber-500" />
          Unusual Options Activity
        </h4>
        <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
          Strikes where today's volume or OI-change is ≥ 2σ above the chain mean — directional bets being entered.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-gray-50 dark:bg-gray-800/40 text-gray-500 text-[10px]">
            <tr>
              <th className="px-3 py-2 text-left">Strike</th>
              <th className="px-3 py-2 text-left">Type</th>
              <th className="px-3 py-2 text-right">Volume</th>
              <th className="px-3 py-2 text-right">Vol-z</th>
              <th className="px-3 py-2 text-right">ΔOI</th>
              <th className="px-3 py-2 text-right">OI-z</th>
              <th className="px-3 py-2 text-right">LTP</th>
              <th className="px-3 py-2 text-right">IV</th>
              <th className="px-3 py-2 text-left">Reason</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-gray-100 dark:border-white/5">
                <td className="px-3 py-1.5 font-semibold tabular-nums">{r.strike}</td>
                <td className="px-3 py-1.5">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${r.type === "CE" ? "bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300" : "bg-rose-50 dark:bg-rose-900/30 text-rose-700 dark:text-rose-300"}`}>
                    {r.type}
                  </span>
                </td>
                <td className="px-3 py-1.5 tabular-nums text-right">{fmtCompact(r.volume)}</td>
                <td className="px-3 py-1.5 tabular-nums text-right font-semibold text-amber-600">{r.volumeZ.toFixed(1)}σ</td>
                <td className="px-3 py-1.5 tabular-nums text-right">{fmtCompact(r.oiChange)}</td>
                <td className="px-3 py-1.5 tabular-nums text-right text-amber-600">{r.oiChangeZ.toFixed(1)}σ</td>
                <td className="px-3 py-1.5 tabular-nums text-right">{r.lastPrice?.toFixed(2) ?? "—"}</td>
                <td className="px-3 py-1.5 tabular-nums text-right">{r.iv ? `${r.iv.toFixed(1)}%` : "—"}</td>
                <td className="px-3 py-1.5 text-gray-500">{r.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


// ── Section: Strategy Heatmap ───────────────────────────────────────────────


function StrategyHeatmapSection({ rows, spot }: { rows: StrategyRow[]; spot: number }) {
  if (!rows.length) return null;
  // Keep ±15% around spot — strategy rr is meaningless at deep OTM where
  // the chain only has a stale stub price.
  const focused = rows.filter(r => spot && Math.abs(r.strike - spot) / spot < 0.15);
  if (focused.length === 0) return null;

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl">
      <div className="px-4 py-3 border-b border-gray-100 dark:border-white/[0.06]">
        <h4 className="text-sm font-bold text-gray-900 dark:text-white flex items-center gap-1.5">
          <Target className="w-3.5 h-3.5 text-indigo-500" />
          Strategy Heatmap (best 1- or 2-leg per strike)
        </h4>
        <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
          For each strike near spot, the strategy with the best reward/risk right now. Color = R/R intensity.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-gray-50 dark:bg-gray-800/40 text-gray-500 text-[10px]">
            <tr>
              <th className="px-3 py-2 text-left">Strike</th>
              <th className="px-3 py-2 text-left">M</th>
              <th className="px-3 py-2 text-left">Best strategy</th>
              <th className="px-3 py-2 text-right">R/R</th>
              <th className="px-3 py-2 text-right">Max profit</th>
              <th className="px-3 py-2 text-right">Max loss</th>
            </tr>
          </thead>
          <tbody>
            {focused.map((r) => (
              <tr key={r.strike} className="border-t border-gray-100 dark:border-white/5">
                <td className="px-3 py-1.5 font-semibold tabular-nums">{r.strike}</td>
                <td className="px-3 py-1.5">
                  <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${r.moneyness === "ATM" ? "bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300" : "bg-gray-100 dark:bg-gray-800 text-gray-500"}`}>
                    {r.moneyness}
                  </span>
                </td>
                <td className="px-3 py-1.5 font-medium">{r.best ?? "—"}</td>
                <td className="px-3 py-1.5 tabular-nums text-right">
                  <span className="px-2 py-0.5 rounded text-white font-bold" style={{ background: rrColor(r.rr) }}>
                    {r.rr > 0 ? r.rr.toFixed(2) : "—"}
                  </span>
                </td>
                <td className="px-3 py-1.5 tabular-nums text-right text-emerald-600">{r.maxProfit?.toFixed(2) ?? "—"}</td>
                <td className="px-3 py-1.5 tabular-nums text-right text-rose-600">{r.maxLoss?.toFixed(2) ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


// ── Top-level panel ─────────────────────────────────────────────────────────


export default function FOAnalyticsPanel({
  symbol, expiry,
}: { symbol: string; expiry?: string }) {
  const url = `/options/analytics/${encodeURIComponent(symbol)}` +
              (expiry ? `?expiry=${encodeURIComponent(expiry)}` : "");

  const { data, isLoading, error } = useQuery<AnalyticsResponse>({
    queryKey: ["options-analytics", symbol, expiry ?? ""],
    queryFn:  () => fetchApi(url),
    staleTime: 60 * 1000,
    refetchOnWindowFocus: false,
  });

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl p-6 flex items-center justify-center gap-2 text-sm text-gray-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Computing F&O analytics for {symbol}…
      </div>
    );
  }
  if (error) {
    return (
      <div className="bg-white dark:bg-gray-900 border border-rose-200 dark:border-rose-500/30 rounded-xl p-4 text-sm text-rose-500">
        <AlertCircle className="inline w-4 h-4 mr-1.5" />
        F&O analytics unavailable: {(error as Error).message}
      </div>
    );
  }
  if (!data) return null;

  const { spot, analytics } = data;
  return (
    <div className="space-y-4">
      <div className="text-[11px] text-gray-500 dark:text-gray-400">
        Spot: <span className="font-semibold text-gray-700 dark:text-gray-300">{spot?.toFixed(2)}</span>
        {" · "}Expiry: <span className="font-semibold text-gray-700 dark:text-gray-300">{data.expiry}</span>
        {" · "}Source: <span className="font-semibold">{data.source}</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <MaxPainSection data={analytics.maxPain} spot={spot} />
        <PcrHistorySection symbol={symbol} />
        <IVSmileSection smile={analytics.smile} spot={spot} />
      </div>

      <OIBuildupSection data={analytics.oiBuildup} spot={spot} />
      <UnusualSection rows={analytics.unusual} />
      <StrategyHeatmapSection rows={analytics.strategy} spot={spot} />
    </div>
  );
}
