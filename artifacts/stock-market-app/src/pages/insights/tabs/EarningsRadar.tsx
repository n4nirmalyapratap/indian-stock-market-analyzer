import { useState, useMemo } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { useCustomAuth } from "@/context/CustomAuthContext";
import { PageHeader, Card, Loading, EmptyState, ErrorState, PillTabs } from "../_shared";
import {
  Zap, RefreshCw, TrendingUp, TrendingDown, Minus,
  Play, ChevronLeft, ChevronRight,
} from "lucide-react";
import ChartButton from "@/components/ChartButton";

// ── Types ─────────────────────────────────────────────────────────────────────

interface ScoreBreakdown {
  revYoY?:  { pct?: number | null; pts: number };
  patYoY?:  { pct?: number | null; pts: number };
  qoq?:     { revPct?: number | null; patPct?: number | null; bothUp: boolean; pts: number };
  opm?:     { cur?: number | null; yoy?: number | null; expanded: boolean; pts: number };
  quality?: { exceptionalOk: boolean; finCostChgPct?: number | null; finCostDown: boolean; pts: number };
}

interface KeyMetrics {
  revenueYoYPct?:  number | null;
  patYoYPct?:      number | null;
  revenueQoQPct?:  number | null;
  patQoQPct?:      number | null;
  opmCurPct?:      number | null;
  opmYoYPct?:      number | null;
  finCostChgPct?:  number | null;
  revenueCrores?:  number | null;
  patCrores?:      number | null;
}

interface EarningsAlert {
  symbol:         string;
  company:        string;
  periodEnd:      string;
  basis:          string;
  score:          number;
  scoreBreakdown: ScoreBreakdown;
  keyMetrics:     KeyMetrics;
  alerted:        boolean;
  createdAt:      number;
  scannedAt:      number;
}

interface AlertsResponse {
  available:      boolean;
  alerts:         EarningsAlert[];
  total:          number;
  limit:          number;
  offset:         number;
  hasMore:        boolean;
  alertThreshold: number;
  error?:         string;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const PAGE_SIZE = 50;

const SCORE_FILTERS = [
  { value: "all",    label: "All" },
  { value: "high",   label: "🔥 Score ≥ 6" },
  { value: "medium", label: "Score 4–5" },
  { value: "low",    label: "Score < 4" },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function scoreColor(score: number) {
  if (score >= 8) return "text-emerald-600 dark:text-emerald-400";
  if (score >= 6) return "text-green-600 dark:text-green-400";
  if (score >= 4) return "text-amber-600 dark:text-amber-400";
  return "text-gray-400 dark:text-gray-500";
}

function scoreBadgeCls(score: number) {
  if (score >= 8) return "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/30";
  if (score >= 6) return "bg-green-500/15 text-green-700 dark:text-green-300 border border-green-200 dark:border-green-500/30";
  if (score >= 4) return "bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-500/30";
  return "bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-gray-600";
}

function minScoreFromFilter(f: string): number {
  if (f === "high")   return 6;
  if (f === "medium") return 4;
  return 0;
}

function maxScoreForFilter(f: string, score: number): boolean {
  if (f === "medium") return score < 6;
  if (f === "low")    return score < 4;
  return true;
}

function ScoreBar({ score }: { score: number }) {
  const color = score >= 6 ? "bg-emerald-500" : score >= 4 ? "bg-amber-500" : "bg-gray-400 dark:bg-gray-600";
  return (
    <div className="flex items-center gap-1.5 min-w-[72px]">
      <div className="flex-1 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${(score / 10) * 100}%` }} />
      </div>
      <span className={`text-[11px] font-bold tabular-nums ${scoreColor(score)}`}>{score}/10</span>
    </div>
  );
}

function PctCell({ val, label }: { val?: number | null; label: string }) {
  if (val === null || val === undefined) {
    return <span className="text-[11px] text-gray-400 dark:text-gray-600">{label}: N/A</span>;
  }
  const pos = val > 0;
  const neg = val < 0;
  return (
    <span className="inline-flex items-center gap-0.5 text-[11px]">
      <span className="text-gray-500 dark:text-gray-400">{label}:</span>
      <span className={pos ? "text-emerald-600 dark:text-emerald-400 font-medium" : neg ? "text-red-500 dark:text-red-400 font-medium" : "text-gray-500"}>
        {pos ? <TrendingUp className="inline w-2.5 h-2.5 mr-0.5" /> : neg ? <TrendingDown className="inline w-2.5 h-2.5 mr-0.5" /> : <Minus className="inline w-2.5 h-2.5 mr-0.5" />}
        {val > 0 ? "+" : ""}{val.toFixed(1)}%
      </span>
    </span>
  );
}

function CheckBullet({ ok, label, pts }: { ok?: boolean; label: string; pts?: number }) {
  return (
    <span className={`inline-flex items-center gap-0.5 text-[10px] ${ok ? "text-emerald-600 dark:text-emerald-400" : "text-gray-400 dark:text-gray-600"}`}>
      <span>{ok ? "✅" : "○"}</span>
      <span>{label}</span>
      {pts !== undefined && <span className="opacity-60">({pts}pts)</span>}
    </span>
  );
}

function fmtDate(ms: number) {
  if (!ms) return "—";
  return new Date(ms).toLocaleString("en-IN", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
    timeZone: "Asia/Kolkata",
  }) + " IST";
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function EarningsRadar() {
  const { user } = useCustomAuth();
  const isAdmin = !!user?.isAdmin;

  const [scoreFilter, setScoreFilter] = useState("all");
  const [search,      setSearch]      = useState("");
  const [page,        setPage]        = useState(1);
  const qc = useQueryClient();

  const minScore = minScoreFromFilter(scoreFilter);
  const offset   = (page - 1) * PAGE_SIZE;

  const { data, isLoading, isFetching, error, refetch } = useQuery<AlertsResponse>({
    queryKey: ["earnings-radar/alerts", minScore, page],
    queryFn:  () =>
      fetchApi(`/earnings-scanner/alerts?limit=${PAGE_SIZE}&offset=${offset}&min_score=${minScore}`),
    staleTime: 2 * 60_000,
    refetchInterval: 2 * 60_000,   // auto-refresh every 2 minutes
    placeholderData: (prev) => prev,
  });

  const scanMutation = useMutation({
    mutationFn: () =>
      fetchApi("/earnings-scanner/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["earnings-radar/alerts"] });
    },
  });

  const alerts: EarningsAlert[] = data?.alerts || [];

  // Client-side search filter on top of server score filter
  const filtered = useMemo(() => {
    if (!search.trim()) return alerts;
    const q = search.trim().toLowerCase();
    return alerts.filter(a =>
      a.symbol.toLowerCase().includes(q) || a.company.toLowerCase().includes(q),
    );
  }, [alerts, search]);

  // Further client-side filter for medium (score 4–5) / low (<4)
  const displayed = useMemo(() => {
    if (scoreFilter === "all" || scoreFilter === "high") return filtered;
    return filtered.filter(a => maxScoreForFilter(scoreFilter, a.score));
  }, [filtered, scoreFilter]);

  const total      = data?.total ?? 0;
  const hasMore    = !!data?.hasMore;
  const highCount  = alerts.filter(a => a.score >= 6).length;
  const alertedCnt = alerts.filter(a => a.alerted).length;

  function handleRefresh() {
    qc.invalidateQueries({ queryKey: ["earnings-radar/alerts"] });
    refetch();
  }

  return (
    <div>
      <PageHeader
        title="Earnings Radar"
        subtitle="Live earnings beat/miss scanner — NSE + BSE financial results scored every 3 minutes"
        info="Scores each quarterly filing on Revenue YoY/QoQ, PAT YoY/QoQ, OPM expansion, and balance-sheet quality. Alert threshold = 6/10. Runs Mon–Fri 09:00–17:30 IST."
        right={
          <div className="flex items-center gap-2 flex-wrap">
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search symbol / company…"
              className="text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white rounded-lg px-3 py-2 w-48 outline-none focus:border-indigo-600 dark:focus:border-indigo-500 placeholder:text-gray-500 dark:placeholder:text-gray-400"
            />
            {isAdmin && (
              <button
                onClick={() => scanMutation.mutate()}
                disabled={scanMutation.isPending}
                title="Trigger an immediate scan (admin only)"
                className="inline-flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg border bg-indigo-600 dark:bg-indigo-500 text-white border-indigo-600 dark:border-indigo-500 hover:bg-indigo-700 dark:hover:bg-indigo-600 transition disabled:opacity-50 font-medium"
              >
                <Play className={`w-3 h-3 ${scanMutation.isPending ? "animate-pulse" : ""}`} />
                {scanMutation.isPending ? "Scanning…" : "Scan Now"}
              </button>
            )}
            <button
              onClick={handleRefresh}
              disabled={isFetching}
              title="Refresh"
              className="text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white rounded-lg p-2 transition disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? "animate-spin" : ""}`} />
            </button>
          </div>
        }
      />

      {scanMutation.isSuccess && (
        <div className="mb-3 text-xs text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30 rounded-lg px-3 py-2">
          ✅ Scan triggered — results will appear in a moment.
        </div>
      )}

      {/* Stats pills */}
      {!isLoading && !error && total > 0 && (
        <div className="flex flex-wrap gap-3 mb-4">
          <div className="flex items-center gap-2 px-3 py-2 bg-emerald-50 dark:bg-emerald-500/10 rounded-xl border border-emerald-200 dark:border-emerald-500/30">
            <Zap className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            <span className="text-sm font-bold text-emerald-700 dark:text-emerald-300">{highCount}</span>
            <span className="text-xs text-emerald-600 dark:text-emerald-400">High score (≥6)</span>
          </div>
          <div className="flex items-center gap-2 px-3 py-2 bg-indigo-50 dark:bg-indigo-500/10 rounded-xl border border-indigo-200 dark:border-indigo-500/30">
            <span className="text-sm font-bold text-indigo-700 dark:text-indigo-300">{alertedCnt}</span>
            <span className="text-xs text-indigo-600 dark:text-indigo-400">Telegram alerts sent</span>
          </div>
          <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
            <span className="text-sm font-bold text-gray-700 dark:text-gray-300">{total}</span>
            <span className="text-xs text-gray-500 dark:text-gray-400">total scanned</span>
          </div>
        </div>
      )}

      {/* Filter row */}
      <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
        <PillTabs value={scoreFilter} onChange={v => { setScoreFilter(v); setPage(1); }} options={SCORE_FILTERS} />
        <p className="text-[11px] text-gray-500 dark:text-gray-400">
          Auto-refreshes every 2 min · Scans Mon–Fri 09:00–17:30 IST
        </p>
      </div>

      {/* Loading / error / empty states */}
      {isLoading && <Loading label="Fetching earnings alerts…" />}

      {error && !isLoading && (
        <ErrorState message={(error as Error)?.message || "Failed to load earnings alerts"} />
      )}

      {!isLoading && !error && data?.available === false && (
        <EmptyState
          icon={<Zap className="w-10 h-10" />}
          title="Scanner unavailable"
          message={data?.error || "Earnings scanner temporarily unavailable."}
        />
      )}

      {!isLoading && !error && displayed.length === 0 && data?.available !== false && (
        <EmptyState
          icon={<Zap className="w-10 h-10" />}
          title="No results yet"
          message={
            total > 0
              ? "No results match the current filter."
              : "The scanner runs every 3 minutes during market hours (Mon–Fri 09:00–17:30 IST). Results appear after the first scan cycle."
          }
        />
      )}

      {/* Results table */}
      {displayed.length > 0 && (
        <>
          <Card className="overflow-x-auto">
            <table className="w-full text-sm min-w-[900px]">
              <thead className="text-xs uppercase text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-900/40 border-b border-gray-100 dark:border-gray-700">
                <tr>
                  <th className="px-4 py-3 text-left">Company</th>
                  <th className="px-4 py-3 text-left">Quarter / Basis</th>
                  <th className="px-4 py-3 text-left">Score</th>
                  <th className="px-4 py-3 text-left">Revenue / PAT (YoY)</th>
                  <th className="px-4 py-3 text-left">QoQ</th>
                  <th className="px-4 py-3 text-left">OPM &amp; Quality</th>
                  <th className="px-4 py-3 text-left">Alert</th>
                  <th className="px-4 py-3 text-right text-[10px]">Scanned</th>
                </tr>
              </thead>
              <tbody>
                {displayed.map((a) => {
                  const km = a.keyMetrics || {};
                  const bd = a.scoreBreakdown || {};
                  return (
                    <tr
                      key={`${a.symbol}-${a.periodEnd}-${a.basis}`}
                      className="border-t border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/30 transition"
                    >
                      {/* Company */}
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          <span className="font-mono font-bold text-indigo-600 dark:text-indigo-400">{a.symbol}</span>
                          <ChartButton symbol={a.symbol} />
                        </div>
                        <div className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5 max-w-[160px] truncate">{a.company}</div>
                      </td>

                      {/* Quarter / Basis */}
                      <td className="px-4 py-3 whitespace-nowrap">
                        <div className="text-xs font-mono text-gray-800 dark:text-gray-200">{a.periodEnd}</div>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium mt-0.5 inline-block
                          ${a.basis === "consolidated"
                            ? "bg-blue-500/10 text-blue-700 dark:text-blue-300"
                            : "bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400"}`}>
                          {a.basis}
                        </span>
                      </td>

                      {/* Score */}
                      <td className="px-4 py-3">
                        <div className="flex flex-col gap-1.5">
                          <span className={`inline-flex items-center justify-center w-10 h-7 rounded-lg text-sm font-bold ${scoreBadgeCls(a.score)}`}>
                            {a.score}
                          </span>
                          <ScoreBar score={a.score} />
                        </div>
                      </td>

                      {/* Revenue / PAT YoY */}
                      <td className="px-4 py-3">
                        <div className="flex flex-col gap-1">
                          <PctCell val={km.revenueYoYPct} label="Rev" />
                          <PctCell val={km.patYoYPct}     label="PAT" />
                          {km.revenueCrores != null && (
                            <span className="text-[10px] text-gray-400 dark:text-gray-600">
                              Rev: ₹{km.revenueCrores.toLocaleString("en-IN")} Cr
                            </span>
                          )}
                        </div>
                      </td>

                      {/* QoQ */}
                      <td className="px-4 py-3">
                        <div className="flex flex-col gap-1">
                          <PctCell val={km.revenueQoQPct} label="Rev" />
                          <PctCell val={km.patQoQPct}     label="PAT" />
                          <CheckBullet ok={bd.qoq?.bothUp} label="both up" pts={bd.qoq?.pts} />
                        </div>
                      </td>

                      {/* OPM + Quality */}
                      <td className="px-4 py-3">
                        <div className="flex flex-col gap-1">
                          <CheckBullet ok={bd.opm?.expanded} label={
                            (bd.opm?.yoy != null && bd.opm?.cur != null)
                              ? `OPM ${bd.opm.yoy.toFixed(1)}%→${bd.opm.cur.toFixed(1)}%`
                              : "OPM ↑ YoY"
                          } pts={bd.opm?.pts} />
                          <CheckBullet ok={bd.quality?.finCostDown} label={
                            bd.quality?.finCostChgPct != null
                              ? `Fin cost ${bd.quality.finCostChgPct > 0 ? "+" : ""}${bd.quality.finCostChgPct.toFixed(1)}%`
                              : "Fin cost ↓"
                          } pts={bd.quality?.pts} />
                          <CheckBullet ok={bd.quality?.exceptionalOk} label="No neg exceptional" />
                        </div>
                      </td>

                      {/* Alert status */}
                      <td className="px-4 py-3">
                        {a.score >= 6 ? (
                          <span className={`text-xs px-2 py-1 rounded-md font-medium whitespace-nowrap ${
                            a.alerted
                              ? "bg-indigo-500/15 text-indigo-700 dark:text-indigo-300"
                              : "bg-amber-500/15 text-amber-700 dark:text-amber-300"
                          }`}>
                            {a.alerted ? "✓ Sent" : "⏳ Pending"}
                          </span>
                        ) : (
                          <span className="text-xs text-gray-400 dark:text-gray-600">—</span>
                        )}
                      </td>

                      {/* Scanned at */}
                      <td className="px-4 py-3 text-right text-[10px] text-gray-400 dark:text-gray-500 whitespace-nowrap">
                        {fmtDate(a.scannedAt)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>

          {/* Pagination */}
          {(page > 1 || hasMore) && (
            <div className="flex items-center justify-center gap-3 mt-4">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={isFetching || page <= 1}
                className="inline-flex items-center gap-1 text-xs px-3 py-2 rounded-lg border bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white hover:bg-gray-100 dark:hover:bg-gray-700 transition disabled:opacity-40 font-medium"
              >
                <ChevronLeft className="w-3.5 h-3.5" /> Prev
              </button>
              <span className="text-xs text-gray-500 dark:text-gray-400">
                Page {page} · {total.toLocaleString("en-IN")} total
              </span>
              <button
                onClick={() => setPage(p => p + 1)}
                disabled={isFetching || !hasMore}
                className="inline-flex items-center gap-1 text-xs px-3 py-2 rounded-lg border bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white hover:bg-gray-100 dark:hover:bg-gray-700 transition disabled:opacity-40 font-medium"
              >
                Next <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </>
      )}

      {/* Scoring legend */}
      {!isLoading && (
        <div className="mt-5 p-4 bg-gray-50 dark:bg-gray-800/50 rounded-xl border border-gray-200 dark:border-gray-700">
          <p className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
            How the score is calculated (max 10 pts):
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-[11px] text-gray-600 dark:text-gray-400">
            <span>📈 Revenue YoY &gt;15% → 2 pts | 5–15% → 1 pt</span>
            <span>💰 PAT YoY &gt;20% → 2 pts | 10–20% → 1 pt</span>
            <span>🔄 QoQ: Revenue AND PAT both up → 2 pts</span>
            <span>📊 OPM expands YoY → 2 pts</span>
            <span>✅ No negative exceptional + finance costs ↓ YoY → 2 pts</span>
            <span>🚨 Telegram alert fires when score ≥ 6</span>
          </div>
        </div>
      )}
    </div>
  );
}
