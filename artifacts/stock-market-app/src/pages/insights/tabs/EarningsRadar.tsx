import { useState, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, Card, Loading, EmptyState, ErrorState, PillTabs } from "../_shared";
import { Zap, RefreshCw, TrendingUp, TrendingDown, Minus } from "lucide-react";
import ChartButton from "@/components/ChartButton";

interface AlertDetail {
  revYoY?: number | null;
  patYoY?: number | null;
  revQoQ?: number | null;
  patQoQ?: number | null;
  opmCur?: number | null;
  opmYoY?: number | null;
  finCostChg?: number | null;
  exceptionalItems?: number | null;
  qoqBothUp?: boolean;
  opmExpanded?: boolean;
  qualityBonus?: boolean;
  score?: number;
}

interface EarningsAlert {
  symbol: string;
  company: string;
  periodEnd: string;
  score: number;
  detail: AlertDetail;
  telegramSent: boolean;
  scannedAt: number;
}

interface AlertsResponse {
  available: boolean;
  alerts: EarningsAlert[];
  total: number;
  alertThreshold: number;
  error?: string;
}

const SCORE_FILTERS = [
  { value: "all",    label: "All" },
  { value: "high",   label: "Score ≥ 6 🔥" },
  { value: "medium", label: "Score 4–5" },
  { value: "low",    label: "Score < 4" },
];

function scoreColor(score: number) {
  if (score >= 8) return "text-emerald-600 dark:text-emerald-400";
  if (score >= 6) return "text-green-600 dark:text-green-400";
  if (score >= 4) return "text-amber-600 dark:text-amber-400";
  return "text-gray-500 dark:text-gray-400";
}

function scoreBadge(score: number) {
  if (score >= 8) return "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/30";
  if (score >= 6) return "bg-green-500/15 text-green-700 dark:text-green-300 border border-green-200 dark:border-green-500/30";
  if (score >= 4) return "bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-500/30";
  return "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-600";
}

function ScoreBar({ score }: { score: number }) {
  const pct = (score / 10) * 100;
  const color = score >= 6 ? "bg-emerald-500" : score >= 4 ? "bg-amber-500" : "bg-gray-400";
  return (
    <div className="flex items-center gap-2 min-w-[80px]">
      <div className="flex-1 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`text-xs font-bold ${scoreColor(score)}`}>{score}/10</span>
    </div>
  );
}

function PctBadge({ val, label }: { val?: number | null; label: string }) {
  if (val === null || val === undefined) return null;
  const pos = val > 0;
  const neg = val < 0;
  return (
    <span className="inline-flex items-center gap-0.5 text-[10px] font-medium">
      <span className="text-gray-500 dark:text-gray-400">{label}:</span>
      <span className={pos ? "text-emerald-600 dark:text-emerald-400" : neg ? "text-red-500 dark:text-red-400" : "text-gray-500"}>
        {pos && <TrendingUp className="inline w-2.5 h-2.5 mr-0.5" />}
        {neg && <TrendingDown className="inline w-2.5 h-2.5 mr-0.5" />}
        {!pos && !neg && <Minus className="inline w-2.5 h-2.5 mr-0.5" />}
        {val > 0 ? "+" : ""}{val.toFixed(1)}%
      </span>
    </span>
  );
}

function CheckBullet({ ok, label }: { ok?: boolean; label: string }) {
  return (
    <span className={`inline-flex items-center gap-0.5 text-[10px] font-medium ${ok ? "text-emerald-600 dark:text-emerald-400" : "text-gray-400 dark:text-gray-600"}`}>
      {ok ? "✅" : "○"} {label}
    </span>
  );
}

function fmtDate(ms: number) {
  if (!ms) return "—";
  const d = new Date(ms);
  return d.toLocaleString("en-IN", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
    timeZone: "Asia/Kolkata",
  }) + " IST";
}

export default function EarningsRadar() {
  const [scoreFilter, setScoreFilter] = useState("all");
  const [search, setSearch] = useState("");
  const qc = useQueryClient();

  const { data, isLoading, isFetching, error, refetch } = useQuery<AlertsResponse>({
    queryKey: ["earnings-radar/alerts"],
    queryFn: () => fetchApi("/earnings-scanner/alerts?limit=200"),
    staleTime: 10 * 60_000,
  });

  const alerts = data?.alerts || [];

  const filtered = useMemo(() => {
    let r = alerts;
    if (scoreFilter === "high")   r = r.filter(a => a.score >= 6);
    if (scoreFilter === "medium") r = r.filter(a => a.score >= 4 && a.score < 6);
    if (scoreFilter === "low")    r = r.filter(a => a.score < 4);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      r = r.filter(a =>
        a.symbol.toLowerCase().includes(q) ||
        a.company.toLowerCase().includes(q),
      );
    }
    return r;
  }, [alerts, scoreFilter, search]);

  const highCount   = alerts.filter(a => a.score >= 6).length;
  const mediumCount = alerts.filter(a => a.score >= 4 && a.score < 6).length;

  function handleRefresh() {
    qc.invalidateQueries({ queryKey: ["earnings-radar/alerts"] });
    refetch();
  }

  return (
    <div>
      <PageHeader
        title="Earnings Radar"
        subtitle="Real-time earnings beat/miss scanner for NSE/BSE financial results"
        info="Scores each company's latest quarterly filing on Revenue YoY/QoQ, PAT YoY/QoQ, OPM expansion, and balance-sheet quality. Alert threshold = 6/10."
        right={
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search symbol / company…"
              className="text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white rounded-lg px-3 py-2 w-52 outline-none focus:border-indigo-600 dark:focus:border-indigo-500 placeholder:text-gray-500 dark:placeholder:text-gray-400"
            />
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

      {/* Stats pills */}
      {!isLoading && !error && alerts.length > 0 && (
        <div className="flex flex-wrap gap-3 mb-4">
          <div className="flex items-center gap-2 px-3 py-2 bg-emerald-50 dark:bg-emerald-500/10 rounded-xl border border-emerald-200 dark:border-emerald-500/30">
            <Zap className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            <span className="text-sm font-bold text-emerald-700 dark:text-emerald-300">{highCount}</span>
            <span className="text-xs text-emerald-600 dark:text-emerald-400">High score (≥6)</span>
          </div>
          <div className="flex items-center gap-2 px-3 py-2 bg-amber-50 dark:bg-amber-500/10 rounded-xl border border-amber-200 dark:border-amber-500/30">
            <span className="text-sm font-bold text-amber-700 dark:text-amber-300">{mediumCount}</span>
            <span className="text-xs text-amber-600 dark:text-amber-400">Medium (4–5)</span>
          </div>
          <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
            <span className="text-sm font-bold text-gray-700 dark:text-gray-300">{alerts.length}</span>
            <span className="text-xs text-gray-500 dark:text-gray-400">total scanned</span>
          </div>
        </div>
      )}

      {/* Filter row */}
      <div className="mb-3">
        <PillTabs value={scoreFilter} onChange={setScoreFilter} options={SCORE_FILTERS} />
      </div>

      {/* Score legend */}
      <div className="mb-4 text-[11px] text-gray-500 dark:text-gray-400 flex flex-wrap gap-x-4 gap-y-1">
        <span><span className="font-semibold text-emerald-600 dark:text-emerald-400">Score 8–10</span>: strong beat across all metrics</span>
        <span><span className="font-semibold text-green-600 dark:text-green-400">Score 6–7</span>: Telegram alert threshold</span>
        <span><span className="font-semibold text-amber-600 dark:text-amber-400">Score 4–5</span>: partial beat, worth watching</span>
        <span>Scans run every 30 min during market hours</span>
      </div>

      {isLoading && <Loading label="Scanning earnings…" />}

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

      {!isLoading && !error && filtered.length === 0 && data?.available !== false && (
        <EmptyState
          icon={<Zap className="w-10 h-10" />}
          title="No results yet"
          message={
            alerts.length > 0
              ? "No results match the current filter."
              : "The scanner runs every 30 minutes. Results will appear after the first scan cycle completes."
          }
        />
      )}

      {filtered.length > 0 && (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm min-w-[820px]">
            <thead className="text-xs uppercase text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-900/40">
              <tr>
                <th className="px-4 py-3 text-left">Company</th>
                <th className="px-4 py-3 text-left">Quarter End</th>
                <th className="px-4 py-3 text-left">Score</th>
                <th className="px-4 py-3 text-left">Key Metrics</th>
                <th className="px-4 py-3 text-left">Quality Checks</th>
                <th className="px-4 py-3 text-left">Alert</th>
                <th className="px-4 py-3 text-right">Scanned</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((a) => (
                <tr
                  key={`${a.symbol}-${a.periodEnd}`}
                  className="border-t border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/30 transition"
                >
                  {/* Company */}
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <span className="font-mono font-bold text-indigo-600 dark:text-indigo-400">{a.symbol}</span>
                      <ChartButton symbol={a.symbol} />
                    </div>
                    <div className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5 max-w-[180px] truncate">{a.company}</div>
                  </td>

                  {/* Quarter */}
                  <td className="px-4 py-3 text-xs text-gray-600 dark:text-gray-300 whitespace-nowrap font-mono">
                    {a.periodEnd}
                  </td>

                  {/* Score */}
                  <td className="px-4 py-3">
                    <div className="flex flex-col gap-1.5">
                      <span className={`inline-flex items-center justify-center w-10 h-7 rounded-lg text-sm font-bold ${scoreBadge(a.score)}`}>
                        {a.score}
                      </span>
                      <ScoreBar score={a.score} />
                    </div>
                  </td>

                  {/* Key metrics */}
                  <td className="px-4 py-3">
                    <div className="flex flex-col gap-1">
                      <PctBadge val={a.detail.revYoY} label="Rev YoY" />
                      <PctBadge val={a.detail.patYoY} label="PAT YoY" />
                      <PctBadge val={a.detail.revQoQ} label="Rev QoQ" />
                      <PctBadge val={a.detail.patQoQ} label="PAT QoQ" />
                    </div>
                  </td>

                  {/* Quality */}
                  <td className="px-4 py-3">
                    <div className="flex flex-col gap-1">
                      <CheckBullet ok={a.detail.qoqBothUp} label="QoQ both up" />
                      <CheckBullet ok={a.detail.opmExpanded} label="OPM ↑ YoY" />
                      <CheckBullet ok={a.detail.qualityBonus} label="Fin cost ↓" />
                      {a.detail.opmCur !== null && a.detail.opmCur !== undefined && (
                        <span className="text-[10px] text-gray-500 dark:text-gray-400">
                          OPM: {a.detail.opmCur.toFixed(1)}%
                          {a.detail.opmYoY !== null && a.detail.opmYoY !== undefined
                            ? ` (was ${a.detail.opmYoY.toFixed(1)}%)`
                            : ""}
                        </span>
                      )}
                    </div>
                  </td>

                  {/* Telegram */}
                  <td className="px-4 py-3">
                    {a.score >= 6 ? (
                      <span
                        title={a.telegramSent ? "Telegram alert sent" : "Alert threshold met — pending dispatch"}
                        className={`text-xs px-2 py-1 rounded-md font-medium whitespace-nowrap ${
                          a.telegramSent
                            ? "bg-indigo-500/15 text-indigo-700 dark:text-indigo-300"
                            : "bg-amber-500/15 text-amber-700 dark:text-amber-300"
                        }`}
                      >
                        {a.telegramSent ? "✓ Sent" : "⏳ Pending"}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-400 dark:text-gray-600">—</span>
                    )}
                  </td>

                  {/* Scanned at */}
                  <td className="px-4 py-3 text-right text-[11px] text-gray-400 dark:text-gray-500 whitespace-nowrap">
                    {fmtDate(a.scannedAt)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {/* Scoring legend */}
      {!isLoading && (
        <div className="mt-5 p-4 bg-gray-50 dark:bg-gray-800/50 rounded-xl border border-gray-200 dark:border-gray-700">
          <p className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">How the score is calculated (max 10 pts):</p>
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
