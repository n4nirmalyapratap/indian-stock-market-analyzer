/**
 * RiskVisuals — visual analytics that sit below the headline KPI tiles
 * and per-position table on the Portfolio → Risk tab.
 *
 * What it shows
 * -------------
 *  1. Beta vs Nifty (new headline tile) — single number summarising
 *     market sensitivity. β=1 moves with the market, β>1 amplifies,
 *     β<1 dampens.
 *  2. Drawdown curve — the visual centerpiece. Most retail apps show
 *     a flat "max DD: -12.3%" number; the curve tells the user *when*
 *     the bleed happened and how long it took to recover.
 *  3. Correlation heatmap — pairwise Pearson correlation between
 *     holdings. Two stocks correlated ≥ 0.85 are "the same bet" even
 *     if they look diversified by name (e.g. HDFC Bank + ICICI Bank).
 *
 * Data flow
 * ---------
 *  * Beta + matrix come from GET /api/portfolio/{pid}/correlation.
 *  * Drawdown series comes from GET /api/portfolio/{pid}/drawdown.
 *  * Both endpoints reuse PriceService internally so the same data
 *    that powers the Sharpe/Sortino numbers powers these views.
 */
import { useQuery } from "@tanstack/react-query";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid,
} from "recharts";
import { Loader2, AlertCircle, Activity } from "lucide-react";

import { api } from "@/lib/api";
import type {
  PortfolioCorrelationResult, PortfolioDrawdownResult,
} from "@/lib/api";


// ── Helpers ─────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined, dp = 2): string {
  if (n == null || isNaN(n)) return "—";
  return n.toFixed(dp);
}

function shortDate(d: string): string {
  // d is "YYYY-MM-DD"
  if (!d || d.length < 7) return d;
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const [y, m] = d.split("-");
  const mi = parseInt(m, 10) - 1;
  return `${months[mi] ?? m} ${y.slice(2)}`;
}

/** Color for a correlation cell. 1 = deep red (high concentration risk),
 *  0 = neutral grey, -1 = deep blue (inversely correlated, diversifying). */
function corrColor(c: number): string {
  // Clamp
  const v = Math.max(-1, Math.min(1, c));
  if (v > 0) {
    const intensity = Math.round(v * 255);
    // red gradient: rgb(255, 255-intensity, 255-intensity)
    return `rgb(255, ${255 - intensity}, ${255 - intensity})`;
  } else if (v < 0) {
    const intensity = Math.round(-v * 255);
    // blue gradient: rgb(255-intensity, 255-intensity, 255)
    return `rgb(${255 - intensity}, ${255 - intensity}, 255)`;
  }
  return "rgb(245, 245, 245)";
}


// ── Beta + correlation heatmap card ─────────────────────────────────────────

function CorrelationCard({ data }: { data: PortfolioCorrelationResult }) {
  const { symbols, matrix, beta, benchmarkSymbol, observationDays } = data;

  const hasMatrix = matrix.length > 0 && symbols.length === matrix.length;
  const dimension = symbols.length;
  // We cap the rendered grid to 12 symbols so the heatmap stays readable.
  // For larger portfolios we show the first 12 and a "+N more" badge —
  // the heatmap's value is in pattern-spotting, not exhaustive listing.
  const cap = 12;
  const shownSymbols = symbols.slice(0, cap);
  const shownMatrix = matrix.slice(0, cap).map(row => row.slice(0, cap));
  const truncatedBy = Math.max(0, dimension - cap);

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl p-4">
      <div className="flex items-baseline justify-between mb-3 flex-wrap gap-2">
        <div>
          <h4 className="text-sm font-bold text-gray-900 dark:text-white flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5 text-indigo-500" />
            Correlation &amp; Beta
          </h4>
          <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
            Beta vs {benchmarkSymbol}; heatmap from {observationDays} overlapping trading days.
          </p>
        </div>
        <div className="flex items-baseline gap-2 px-3 py-1.5 rounded-md bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-200 dark:border-indigo-500/20">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-indigo-600 dark:text-indigo-300">β</span>
          <span className="text-lg font-bold text-indigo-700 dark:text-indigo-200 tabular-nums">
            {fmt(beta, 2)}
          </span>
          {beta != null && (
            <span className="text-[10px] text-indigo-500 dark:text-indigo-300/80">
              {beta > 1.1 ? "amplifies market" : beta < 0.9 ? "dampens market" : "tracks market"}
            </span>
          )}
        </div>
      </div>

      {!hasMatrix ? (
        <div className="py-6 text-center text-sm text-gray-400 dark:text-gray-500">
          <AlertCircle className="inline w-4 h-4 mr-1.5" />
          Need at least 2 holdings with 30+ overlapping trading days.
        </div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="border-separate" style={{ borderSpacing: "2px" }}>
              <thead>
                <tr>
                  <th></th>
                  {shownSymbols.map(s => (
                    <th key={s}
                        className="text-[9px] font-semibold text-gray-500 dark:text-gray-400 align-bottom pb-1 pr-0.5"
                        style={{ writingMode: "vertical-rl", transform: "rotate(180deg)", height: 60 }}>
                      {s}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shownMatrix.map((row, i) => (
                  <tr key={shownSymbols[i]}>
                    <td className="text-[10px] font-semibold text-gray-600 dark:text-gray-300 pr-1.5 whitespace-nowrap">
                      {shownSymbols[i]}
                    </td>
                    {row.map((c, j) => (
                      <td key={j}
                          className="w-7 h-7 text-center text-[9px] font-medium text-gray-900"
                          style={{
                            background: corrColor(c),
                            color: Math.abs(c) > 0.6 ? "#fff" : "#1f2937",
                            opacity: i === j ? 0.4 : 1,
                          }}
                          title={`${shownSymbols[i]} ↔ ${shownSymbols[j]}: ${c.toFixed(2)}`}>
                        {c.toFixed(1).replace("0.", ".").replace("-0.", "-.")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {/* Legend */}
          <div className="flex items-center gap-2 mt-3 text-[10px] text-gray-500 dark:text-gray-400">
            <span>−1</span>
            <div className="flex h-2 w-32 rounded overflow-hidden">
              {[-1, -0.5, 0, 0.5, 1].map(v => (
                <div key={v} className="flex-1" style={{ background: corrColor(v) }} />
              ))}
            </div>
            <span>+1</span>
            <span className="ml-3">
              Red = same direction (concentrated). Blue = opposite (diversifying).
            </span>
            {truncatedBy > 0 && (
              <span className="ml-auto px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-500">
                +{truncatedBy} more not shown
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}


// ── Drawdown curve card ─────────────────────────────────────────────────────

function DrawdownCard({ data }: { data: PortfolioDrawdownResult }) {
  const { series, maxDrawdownPct, maxDrawdownDate, observationDays } = data;
  const hasData = series.length >= 5;

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl p-4">
      <div className="flex items-baseline justify-between mb-3 flex-wrap gap-2">
        <div>
          <h4 className="text-sm font-bold text-gray-900 dark:text-white">
            Drawdown over time
          </h4>
          <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
            Equity below running peak. Deepest:&nbsp;
            <span className="font-semibold text-rose-600 dark:text-rose-400">
              {fmt(maxDrawdownPct, 2)}%
            </span>
            {maxDrawdownDate && (
              <> on <span className="font-medium">{maxDrawdownDate}</span></>
            )}
            &nbsp;· {observationDays} days observed
          </p>
        </div>
      </div>

      {!hasData ? (
        <div className="py-8 text-center text-sm text-gray-400 dark:text-gray-500">
          <AlertCircle className="inline w-4 h-4 mr-1.5" />
          Not enough portfolio history yet.
        </div>
      ) : (
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={series} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
              <defs>
                <linearGradient id="dd-grad" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%"   stopColor="#f43f5e" stopOpacity={0.4}/>
                  <stop offset="100%" stopColor="#f43f5e" stopOpacity={0.05}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" strokeOpacity={0.3}/>
              <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 10 }} minTickGap={40}/>
              <YAxis tick={{ fontSize: 10 }} unit="%" width={45}
                     domain={[(dataMin: number) => Math.min(dataMin, -1), 0]} />
              <Tooltip
                contentStyle={{
                  background: "rgba(17,24,39,0.96)", border: "none",
                  borderRadius: 6, color: "#fff", fontSize: 12,
                }}
                formatter={(v: number) => [`${v.toFixed(2)}%`, "Drawdown"]}
                labelFormatter={(l) => shortDate(l as string)}
              />
              <Area
                type="monotone" dataKey="drawdown"
                stroke="#f43f5e" strokeWidth={1.5}
                fill="url(#dd-grad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}


// ── Public API ──────────────────────────────────────────────────────────────

export default function RiskVisuals({ pid }: { pid: string }) {
  const corr = useQuery({
    queryKey: ["portfolio", pid, "correlation"],
    queryFn:  () => api.portfolioCorrelation(pid, 365),
    staleTime: 60 * 60 * 1000,
    refetchOnWindowFocus: false,
  });

  const dd = useQuery({
    queryKey: ["portfolio", pid, "drawdown"],
    queryFn:  () => api.portfolioDrawdown(pid, 365),
    staleTime: 60 * 60 * 1000,
    refetchOnWindowFocus: false,
  });

  if (corr.isLoading || dd.isLoading) {
    return (
      <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl p-6 flex items-center justify-center gap-2 text-sm text-gray-500">
        <Loader2 className="w-4 h-4 animate-spin"/>
        Computing risk visuals…
      </div>
    );
  }
  if (corr.isError && dd.isError) {
    return (
      <div className="bg-white dark:bg-gray-900 border border-gray-100 dark:border-white/10 rounded-xl p-4 text-sm text-rose-500">
        <AlertCircle className="inline w-4 h-4 mr-1.5" />
        Could not load risk visuals.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {dd.data && <DrawdownCard data={dd.data} />}
      {corr.data && <CorrelationCard data={corr.data} />}
    </div>
  );
}
