import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchAdmin } from "@/lib/api";
import {
  Brain, RefreshCw, Trash2, Loader2, Activity,
  CalendarDays, Timer, TrendingUp, Save,
} from "lucide-react";

function errMsg(e: unknown): string {
  if (e instanceof Error) return e.message;
  if (typeof e === "string") return e;
  return "unknown error";
}

type AdminStats = {
  todayRuns: number;
  weekRuns: number;
  avgWallClockMs: number;
  topTickers: Array<{ ticker: string; runs: number }>;
  quotaPerUserDay: number;
  quotaDefault?: number;
};

function StatCard({
  icon: Icon, label, value, sub, color,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  sub?: string;
  color: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
      <div className="flex items-center gap-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div className="min-w-0">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
          <p className="text-2xl font-black text-gray-900 mt-0.5 leading-none">{value}</p>
          {sub && <p className="text-[11px] text-gray-400 mt-1">{sub}</p>}
        </div>
      </div>
    </div>
  );
}

function fmtMs(ms: number): string {
  if (!ms) return "—";
  const s = ms / 1000;
  if (s < 10) return `${s.toFixed(2)}s`;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s - m * 60);
  return `${m}m ${rem}s`;
}

export default function AiAnalystPage() {
  const qc = useQueryClient();

  const { data, isLoading, isError, error, refetch, isFetching } =
    useQuery<AdminStats>({
      queryKey: ["ai-analyst-admin-stats"],
      queryFn: () => fetchAdmin("/ai-analyst/admin/stats"),
      refetchInterval: 15000,
    });

  const [quotaDraft, setQuotaDraft] = useState<string>("");
  useEffect(() => {
    if (data?.quotaPerUserDay != null) {
      setQuotaDraft(String(data.quotaPerUserDay));
    }
  }, [data?.quotaPerUserDay]);

  const quotaMut = useMutation({
    mutationFn: (limit: number) =>
      fetchAdmin<AdminStats>("/ai-analyst/admin/quota", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit }),
      }),
    onSuccess: (res) => {
      qc.setQueryData(["ai-analyst-admin-stats"], res);
      qc.invalidateQueries({ queryKey: ["ai-analyst-admin-stats"] });
    },
    onError: (e: unknown) => {
      alert(`Failed to update quota: ${errMsg(e)}`);
    },
  });

  const saveQuota = () => {
    const n = Number.parseInt(quotaDraft, 10);
    if (!Number.isFinite(n) || n < 1 || n > 1000) {
      alert("Quota must be a whole number between 1 and 1000.");
      return;
    }
    quotaMut.mutate(n);
  };

  const flushMut = useMutation({
    mutationFn: () =>
      fetchAdmin<{ flushed: number }>("/ai-analyst/admin/flush", { method: "POST" }),
    onSuccess: (res) => {
      alert(`Flushed ${res.flushed} cached report${res.flushed === 1 ? "" : "s"}.`);
      qc.invalidateQueries({ queryKey: ["ai-analyst-admin-stats"] });
    },
    onError: (e: unknown) => {
      alert(`Flush failed: ${errMsg(e)}`);
    },
  });

  const stats = data;
  const top = stats?.topTickers ?? [];
  const maxRuns = top.reduce((m, t) => Math.max(m, t.runs), 0) || 1;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Brain className="w-6 h-6 text-indigo-600" /> AI Analyst
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Usage, latency, and top tickers for the Deep AI Analyst pipeline
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-2 text-sm font-medium text-gray-600 hover:text-gray-900 bg-white border border-gray-200 rounded-lg px-3 py-2 hover:bg-gray-50 transition-all"
          >
            <RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} /> Refresh
          </button>
          <button
            onClick={() => {
              if (confirm("Flush today's AI Analyst cache? Users will need to re-run analyses.")) {
                flushMut.mutate();
              }
            }}
            disabled={flushMut.isPending}
            className="flex items-center gap-2 text-sm font-semibold bg-rose-600 hover:bg-rose-500 disabled:bg-gray-200 disabled:text-gray-400 text-white rounded-lg px-3 py-2 transition-all"
          >
            {flushMut.isPending
              ? <><Loader2 className="w-4 h-4 animate-spin" /> Flushing…</>
              : <><Trash2 className="w-4 h-4" /> Flush today's cache</>}
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-16 text-gray-400">
          <Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading stats…
        </div>
      )}

      {isError && (
        <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl p-4 text-sm">
          Failed to load AI Analyst stats: {errMsg(error)}
        </div>
      )}

      {stats && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            <StatCard
              icon={Activity}
              label="Runs today"
              value={String(stats.todayRuns)}
              color="bg-indigo-50 text-indigo-700"
            />
            <StatCard
              icon={CalendarDays}
              label="Runs (last 7 days)"
              value={String(stats.weekRuns)}
              color="bg-blue-50 text-blue-700"
            />
            <StatCard
              icon={Timer}
              label="Avg wall-clock"
              value={fmtMs(stats.avgWallClockMs)}
              sub="across last 7 days"
              color="bg-amber-50 text-amber-700"
            />
            <StatCard
              icon={TrendingUp}
              label="Quota / user / day"
              value={String(stats.quotaPerUserDay)}
              color="bg-green-50 text-green-700"
            />
          </div>

          <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div className="min-w-0">
                <h2 className="font-semibold text-gray-900 flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-green-600" />
                  Daily quota per user
                </h2>
                <p className="text-xs text-gray-500 mt-1 max-w-xl">
                  Maximum fresh AI analyses each user may run per IST day.
                  Cached reports don't count. Resets at midnight IST.
                  Default is <span className="font-mono">{stats.quotaDefault ?? 3}</span>.
                  Higher values may hit free-tier rate limits.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min={1}
                  max={1000}
                  value={quotaDraft}
                  onChange={(e) => setQuotaDraft(e.target.value)}
                  disabled={quotaMut.isPending}
                  className="w-24 px-3 py-2 text-sm font-mono font-semibold text-gray-900 bg-white border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-400 disabled:opacity-50"
                />
                <button
                  onClick={saveQuota}
                  disabled={
                    quotaMut.isPending ||
                    quotaDraft === String(stats.quotaPerUserDay)
                  }
                  className="flex items-center gap-2 text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-200 disabled:text-gray-400 text-white rounded-lg px-3 py-2 transition-all"
                >
                  {quotaMut.isPending
                    ? <><Loader2 className="w-4 h-4 animate-spin" /> Saving…</>
                    : <><Save className="w-4 h-4" /> Save</>}
                </button>
              </div>
            </div>
            <p className="text-[11px] text-gray-400 mt-3">
              Suggested: <span className="font-mono">3</span> (free tier safe) ·
              <span className="font-mono"> 10</span> (power users) ·
              <span className="font-mono"> 25+</span> (requires paid OpenRouter key).
              Applies immediately to new runs — already-used quota for today is preserved.
            </p>
          </div>

          <div className="bg-white rounded-xl border border-gray-100 shadow-sm">
            <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
              <div>
                <h2 className="font-semibold text-gray-900">Top tickers (last 7 days)</h2>
                <p className="text-xs text-gray-400 mt-0.5">
                  Most-analysed symbols, ranked by number of runs
                </p>
              </div>
              <span className="text-xs text-gray-400">{top.length} of 10</span>
            </div>
            {top.length === 0 ? (
              <div className="px-5 py-10 text-sm text-gray-400 text-center">
                No analyses recorded in the last 7 days.
              </div>
            ) : (
              <ul className="divide-y divide-gray-50">
                {top.map((t, i) => (
                  <li key={t.ticker} className="px-5 py-3 flex items-center gap-4">
                    <span className="text-xs font-mono text-gray-400 w-6">#{i + 1}</span>
                    <span className="font-mono font-semibold text-sm text-gray-900 w-32 truncate">
                      {t.ticker}
                    </span>
                    <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-indigo-500 rounded-full transition-all"
                        style={{ width: `${(t.runs / maxRuns) * 100}%` }}
                      />
                    </div>
                    <span className="text-sm font-semibold text-gray-700 w-20 text-right tabular-nums">
                      {t.runs} run{t.runs === 1 ? "" : "s"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <p className="text-[11px] text-gray-400 text-center">
            Auto-refreshes every 15s · Flushing today's cache forces fresh runs for all users
          </p>
        </>
      )}
    </div>
  );
}
