/**
 * AI Analyst — Track Record page.
 *
 * Shows the AI Analyst's BUY/SELL verdicts and how they actually played out
 * at 1d / 5d / 30d horizons. Honest hit rates build trust; hiding bad calls
 * only delays the moment users notice they're being misled.
 *
 * Data comes from /api/ai-analyst/backtest/{overall,recent,by-ticker} which
 * are populated by a daily backend scheduler (_ai_backtest_scheduler in
 * main.py). A verdict appears here only after its horizon has elapsed AND
 * the scheduler has caught up, so newly-issued BUY/SELLs won't show up for
 * at least a day.
 */
import React, { useEffect, useMemo, useState } from "react";
import { useCustomAuth } from "@/context/CustomAuthContext";
import { TrendingUp, TrendingDown, Activity, Target, ChevronRight, Loader2 } from "lucide-react";

type HorizonStats = {
  total:     number;
  correct:   number;
  hitRate:   number;
  avgReturn: number;
};

type OverallStats = {
  totalCalls: number;
  byHorizon:  Record<string, HorizonStats>;
  byVerdict:  Record<string, HorizonStats>;
  lastEvaluatedAt: number | null;
};

type Call = {
  ticker:           string;
  verdict:          string;
  confidence:       string | null;
  horizonDays:      number;
  verdictAtMs:      number;
  verdictPrice:     number | null;
  evaluatedAtMs:    number;
  actualPrice:      number | null;
  actualReturnPct:  number | null;
  wasCorrect:       boolean | null;
};

function pct(n: number, digits = 1): string {
  return (n * 100).toFixed(digits) + "%";
}

function signedPct(n: number | null, digits = 2): string {
  if (n === null || n === undefined || !isFinite(n)) return "—";
  const s = n >= 0 ? "+" : "";
  return `${s}${n.toFixed(digits)}%`;
}

function fmtIst(ms: number | null | undefined): string {
  if (!ms) return "—";
  return new Date(ms).toLocaleString("en-IN", {
    day: "numeric", month: "short", year: "numeric",
  });
}

function HitRateCard({ label, stats }: { label: React.ReactNode; stats: HorizonStats | undefined }) {
  if (!stats || stats.total === 0) {
    return (
      <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-gray-900 p-4">
        <div className="text-xs text-gray-500">{label}</div>
        <div className="text-2xl font-mono text-gray-300">—</div>
        <div className="text-xs text-gray-400 mt-1">no completed calls yet</div>
      </div>
    );
  }
  const hit = stats.hitRate;
  const ringColor =
    hit >= 0.6 ? "text-emerald-500"
    : hit >= 0.45 ? "text-amber-500"
    : "text-rose-500";
  const avgColor =
    stats.avgReturn >= 0 ? "text-emerald-500" : "text-rose-500";
  return (
    <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-gray-900 p-4">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-2xl font-mono font-semibold ${ringColor}`}>
        {pct(hit, 1)}
      </div>
      <div className="text-xs text-gray-400 mt-1">
        {stats.correct}/{stats.total} correct · avg return{" "}
        <span className={`font-mono ${avgColor}`}>{signedPct(stats.avgReturn)}</span>
      </div>
    </div>
  );
}

function CallRow({ call }: { call: Call }) {
  const isBuy = call.verdict.toUpperCase() === "BUY";
  const verdictColor = isBuy
    ? "text-emerald-600 bg-emerald-50 dark:bg-emerald-900/20 dark:text-emerald-300"
    : "text-rose-600 bg-rose-50 dark:bg-rose-900/20 dark:text-rose-300";
  const correctIcon =
    call.wasCorrect === true ? <span className="text-emerald-500">✓</span>
    : call.wasCorrect === false ? <span className="text-rose-500">✗</span>
    : <span className="text-gray-400">—</span>;
  const returnColor =
    call.actualReturnPct === null ? "text-gray-400"
    : call.actualReturnPct >= 0 ? "text-emerald-500"
    : "text-rose-500";

  return (
    <tr className="border-t border-gray-100 dark:border-white/5 hover:bg-gray-50 dark:hover:bg-gray-800/30">
      <td className="px-3 py-2 font-mono font-medium">{call.ticker}</td>
      <td className="px-3 py-2">
        <span className={`px-2 py-0.5 rounded text-xs font-medium ${verdictColor}`}>
          {call.verdict}
        </span>
      </td>
      <td className="px-3 py-2 text-xs text-gray-500">{call.confidence ?? "—"}</td>
      <td className="px-3 py-2 text-right text-xs">
        {call.verdictPrice != null ? `₹${call.verdictPrice.toFixed(2)}` : "—"}
      </td>
      <td className="px-3 py-2 text-xs text-gray-400">{fmtIst(call.verdictAtMs)}</td>
      <td className="px-3 py-2 text-right text-xs">{call.horizonDays}d</td>
      <td className="px-3 py-2 text-right text-xs">
        {call.actualPrice != null ? `₹${call.actualPrice.toFixed(2)}` : "—"}
      </td>
      <td className={`px-3 py-2 text-right font-mono text-xs ${returnColor}`}>
        {signedPct(call.actualReturnPct)}
      </td>
      <td className="px-3 py-2 text-center">{correctIcon}</td>
    </tr>
  );
}

export default function AIAnalystTrackRecord() {
  const { token, user } = useCustomAuth();
  const isAdmin = !!user?.isAdmin;
  const [overall, setOverall]   = useState<OverallStats | null>(null);
  const [recent,  setRecent]    = useState<Call[]>([]);
  const [loading, setLoading]   = useState(true);
  const [error,   setError]     = useState<string>("");
  // Non-admins can only see their own calls (the backend gates scope=all).
  // Forcing scope=me when !isAdmin avoids a 403 if the admin toggle leaks.
  const [scope,   setScope]     = useState<"me" | "all">("me");

  useEffect(() => {
    if (!token) return;
    let alive = true;
    setLoading(true);
    setError("");
    const headers = { Authorization: `Bearer ${token}` };

    Promise.all([
      fetch("/api/ai-analyst/backtest/overall", { headers })
        .then(r => r.ok ? r.json() : Promise.reject(new Error(`overall: ${r.status}`))),
      fetch(`/api/ai-analyst/backtest/recent?limit=100&scope=${scope}`, { headers })
        .then(r => r.ok ? r.json() : Promise.reject(new Error(`recent: ${r.status}`))),
    ])
      .then(([o, r]) => {
        if (!alive) return;
        setOverall(o);
        setRecent(Array.isArray(r) ? r : []);
      })
      .catch((e: Error) => {
        if (alive) setError(e.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => { alive = false; };
  }, [token, scope]);

  const horizons = useMemo(() => ["1", "5", "30"], []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-400 text-sm">
        <Loader2 className="w-4 h-4 animate-spin mr-2" /> Loading track record…
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-4 lg:p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold flex items-center gap-2">
          <Target className="w-6 h-6 text-indigo-500" />
          AI Analyst — Track Record
        </h1>
        <p className="text-xs text-gray-500 mt-1">
          How the AI Analyst's BUY/SELL verdicts have actually played out.
          Each verdict is checked at 1, 5, and 30 days after it was issued and
          marked correct if the price moved by more than 0.5% in the predicted
          direction. HOLD calls are excluded — there's no directional bet to
          score. Updated daily.
        </p>
        {overall?.lastEvaluatedAt && (
          <p className="text-xs text-gray-400 mt-1">
            Last evaluated: {fmtIst(overall.lastEvaluatedAt)}
          </p>
        )}
      </div>

      {error && (
        <div className="rounded border border-rose-300 bg-rose-50 dark:bg-rose-900/20 dark:border-rose-700 text-rose-700 dark:text-rose-300 text-xs px-3 py-2">
          {error}
        </div>
      )}

      {/* Hit rate by horizon */}
      <section>
        <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-1">
          <Activity className="w-4 h-4" /> Hit rate by horizon
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {horizons.map(h => (
            <HitRateCard key={h} label={`${h}-day window`} stats={overall?.byHorizon[h]} />
          ))}
        </div>
      </section>

      {/* Hit rate by verdict */}
      <section>
        <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-1">
          <ChevronRight className="w-4 h-4" /> Hit rate by verdict
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <HitRateCard
            label={<span className="flex items-center gap-1"><TrendingUp className="w-3.5 h-3.5 text-emerald-500" /> BUY calls</span>}
            stats={overall?.byVerdict.BUY}
          />
          <HitRateCard
            label={<span className="flex items-center gap-1"><TrendingDown className="w-3.5 h-3.5 text-rose-500" /> SELL calls</span>}
            stats={overall?.byVerdict.SELL}
          />
        </div>
      </section>

      {/* Recent calls */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Recent calls
          </h2>
          <div className="flex gap-1 text-xs">
            <button
              onClick={() => setScope("me")}
              className={`px-2 py-1 rounded border ${scope === "me"
                ? "bg-indigo-600 text-white border-indigo-600"
                : "bg-white dark:bg-gray-900 border-gray-200 dark:border-white/10"}`}
            >
              My calls
            </button>
            {isAdmin && (
              <button
                onClick={() => setScope("all")}
                className={`px-2 py-1 rounded border ${scope === "all"
                  ? "bg-indigo-600 text-white border-indigo-600"
                  : "bg-white dark:bg-gray-900 border-gray-200 dark:border-white/10"}`}
                title="App-wide stream — admin only"
              >
                All calls
              </button>
            )}
          </div>
        </div>
        <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-gray-900 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800/40 text-xs text-gray-500">
              <tr>
                <th className="px-3 py-2 text-left">Ticker</th>
                <th className="px-3 py-2 text-left">Verdict</th>
                <th className="px-3 py-2 text-left">Conf.</th>
                <th className="px-3 py-2 text-right">Verdict @</th>
                <th className="px-3 py-2 text-left">Issued</th>
                <th className="px-3 py-2 text-right">Horizon</th>
                <th className="px-3 py-2 text-right">Closed @</th>
                <th className="px-3 py-2 text-right">Return</th>
                <th className="px-3 py-2 text-center">✓/✗</th>
              </tr>
            </thead>
            <tbody>
              {recent.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-3 py-8 text-center text-xs text-gray-400">
                    No backtested verdicts yet. Run an AI analysis and check back tomorrow.
                  </td>
                </tr>
              )}
              {recent.map((c, i) => <CallRow key={i} call={c} />)}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
