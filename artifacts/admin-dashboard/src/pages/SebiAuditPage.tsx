import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchAdmin } from "@/lib/api";
import {
  ShieldCheck, RefreshCw, Play, AlertTriangle, CheckCircle2,
  Clock, FileText, ChevronDown, ChevronUp, Database, ChevronRight,
  Info,
} from "lucide-react";

type ReportMeta = {
  filename: string;
  generated: string;
  n_issues: number;
  n_lines: number;
  report?: string;
};

type ReportsListResponse = {
  reports: ReportMeta[];
  total: number;
};

type FullReport = ReportMeta & { report: string };

type AuditResult = {
  status: "ok" | "error";
  log: string;
  report: string;
  n_issues: number;
};

function MarkdownBlock({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <div className="space-y-0.5 text-sm text-gray-800 font-mono leading-relaxed whitespace-pre-wrap break-words">
      {lines.map((line, i) => {
        if (line.startsWith("## "))
          return <p key={i} className="font-bold text-gray-900 text-base mt-4 mb-1">{line.slice(3)}</p>;
        if (line.startsWith("# "))
          return <p key={i} className="font-extrabold text-gray-900 text-lg mt-2 mb-1">{line.slice(2)}</p>;
        if (line.startsWith("### "))
          return <p key={i} className="font-semibold text-indigo-700 mt-3 mb-0.5">{line.slice(4)}</p>;
        if (line.startsWith("- ") || line.startsWith("* "))
          return <p key={i} className="pl-4">• {line.slice(2)}</p>;
        if (line.startsWith("---"))
          return <hr key={i} className="border-gray-200 my-3" />;
        if (line.startsWith("> "))
          return <p key={i} className="pl-3 border-l-2 border-indigo-300 text-gray-600 italic">{line.slice(2)}</p>;
        if (line.startsWith("**") && line.endsWith("**"))
          return <p key={i} className="font-semibold text-gray-900">{line.slice(2, -2)}</p>;
        if (line === "")
          return <div key={i} className="h-1" />;
        return <p key={i}>{line}</p>;
      })}
    </div>
  );
}

function IssueBadge({ n }: { n: number }) {
  if (n === 0) return (
    <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-green-50 text-green-700 border border-green-100">
      <CheckCircle2 className="w-3 h-3" /> Clean
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-red-50 text-red-700 border border-red-100">
      <AlertTriangle className="w-3 h-3" /> {n} issue{n !== 1 ? "s" : ""}
    </span>
  );
}

export default function SebiAuditPage() {
  const qc = useQueryClient();
  const [selectedFilename, setSelectedFilename] = useState<string | null>(null);
  const [runLog, setRunLog] = useState<string | null>(null);
  const [showLog, setShowLog] = useState(false);

  const { data: listData, isLoading: listLoading, refetch: refetchList } =
    useQuery<ReportsListResponse>({
      queryKey: ["sebi-reports"],
      queryFn: () => fetchAdmin<ReportsListResponse>("/options/sebi-reports"),
      retry: false,
    });

  // Compute reports + effective selection BEFORE the full-report query so
  // the query's `enabled` flag and key are correct on the first render after data loads.
  const reports = listData?.reports ?? [];
  const selected = selectedFilename ?? (reports[0]?.filename ?? null);

  const { data: fullReport, isLoading: reportLoading } =
    useQuery<FullReport>({
      queryKey: ["sebi-report-full", selected],
      queryFn: async () => {
        if (!selected) throw new Error("no selection");
        const all = await fetchAdmin<ReportsListResponse>("/options/sebi-reports?full=true");
        const found = all.reports.find(r => r.filename === selected);
        if (!found || !found.report) throw new Error("report not found");
        return found as FullReport;
      },
      enabled: !!selected,
      retry: false,
    });

  const run = useMutation<AuditResult>({
    mutationFn: () => fetchAdmin<AuditResult>("/options/sebi-audit", { method: "POST" }),
    onSuccess: (result) => {
      setRunLog(result.log);
      setShowLog(true);
      qc.invalidateQueries({ queryKey: ["sebi-reports"] });
      qc.invalidateQueries({ queryKey: ["sebi-report"] });
    },
  });

  return (
    <div className="space-y-5">

      {/* ── Header ── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <ShieldCheck className="w-6 h-6 text-indigo-600" />
            SEBI Compliance Audit
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            5-year circular database (2019–present) · live RSS · AI-powered diff against codebase
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => refetchList()}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
          <button
            onClick={() => run.mutate()}
            disabled={run.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition disabled:opacity-60"
          >
            {run.isPending
              ? <RefreshCw className="w-4 h-4 animate-spin" />
              : <Play className="w-4 h-4" />}
            {run.isPending ? "Running audit…" : "Run Audit Now"}
          </button>
        </div>
      </div>

      {/* ── Running banner ── */}
      {run.isPending && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 flex items-center gap-3 text-sm text-indigo-700">
          <RefreshCw className="w-4 h-4 animate-spin flex-shrink-0" />
          Audit in progress — loading 5-year SEBI DB + live RSS + running AI compliance diff…
          <span className="text-xs text-indigo-400">(~60–90 seconds)</span>
        </div>
      )}

      {/* ── Run log (collapsible) ── */}
      {runLog && (
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
          <button
            onClick={() => setShowLog(v => !v)}
            className="w-full flex items-center justify-between px-5 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            <span className="flex items-center gap-2">
              <Info className="w-4 h-4 text-indigo-500" />
              Last run output
            </span>
            {showLog ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
          </button>
          {showLog && (
            <div className="px-5 pb-4 border-t border-gray-50">
              <pre className="mt-3 bg-gray-900 text-green-400 rounded-lg p-4 text-xs font-mono whitespace-pre-wrap max-h-40 overflow-auto">
                {runLog}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* ── No reports yet ── */}
      {!listLoading && reports.length === 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-amber-800">No audit reports yet</p>
            <p className="text-sm text-amber-700 mt-1">
              Click <strong>Run Audit Now</strong> to generate your first report. The audit will load
              the full 5-year SEBI circular database (2019–present) plus the latest live RSS feed,
              scan your codebase, and produce a structured compliance report.
            </p>
          </div>
        </div>
      )}

      {/* ── Summary stats ── */}
      {reports.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            {
              label: "Total Runs",
              value: reports.length,
              icon: <Database className="w-5 h-5 text-indigo-600" />,
              bg: "bg-indigo-50",
            },
            {
              label: "Latest Run",
              value: reports[0]?.generated ?? "—",
              icon: <Clock className="w-5 h-5 text-blue-600" />,
              bg: "bg-blue-50",
            },
            {
              label: "Issues (latest)",
              value: reports[0]?.n_issues ?? 0,
              icon: reports[0]?.n_issues
                ? <AlertTriangle className="w-5 h-5 text-red-500" />
                : <CheckCircle2 className="w-5 h-5 text-green-500" />,
              bg: reports[0]?.n_issues ? "bg-red-50" : "bg-green-50",
            },
            {
              label: "Clean Runs",
              value: reports.filter(r => r.n_issues === 0).length,
              icon: <CheckCircle2 className="w-5 h-5 text-green-600" />,
              bg: "bg-green-50",
            },
          ].map(({ label, value, icon, bg }) => (
            <div key={label} className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 flex items-center gap-3">
              <div className={`w-10 h-10 rounded-lg ${bg} flex items-center justify-center flex-shrink-0`}>
                {icon}
              </div>
              <div>
                <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">{label}</p>
                <p className="text-sm font-bold text-gray-900 mt-0.5">{value}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Master-detail layout ── */}
      {reports.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

          {/* ─ Left: report list ─ */}
          <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-50 bg-gray-50">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5" />
                All Reports ({reports.length})
              </p>
            </div>
            <div className="divide-y divide-gray-50 max-h-[600px] overflow-auto">
              {reports.map((r) => {
                const isSelected = (selected === r.filename);
                return (
                  <button
                    key={r.filename}
                    onClick={() => setSelectedFilename(r.filename)}
                    className={`w-full text-left px-4 py-3 transition flex items-center justify-between gap-2 group
                      ${isSelected ? "bg-indigo-50 border-l-2 border-indigo-500" : "hover:bg-gray-50 border-l-2 border-transparent"}`}
                  >
                    <div className="min-w-0">
                      <p className={`text-sm font-semibold truncate ${isSelected ? "text-indigo-700" : "text-gray-800"}`}>
                        {r.generated}
                      </p>
                      <div className="mt-0.5">
                        <IssueBadge n={r.n_issues} />
                      </div>
                      <p className="text-xs text-gray-400 mt-0.5">{r.n_lines} lines</p>
                    </div>
                    <ChevronRight className={`w-4 h-4 flex-shrink-0 transition ${isSelected ? "text-indigo-500" : "text-gray-300 group-hover:text-gray-400"}`} />
                  </button>
                );
              })}
            </div>
          </div>

          {/* ─ Right: report content ─ */}
          <div className="lg:col-span-2 bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
            {reportLoading && (
              <div className="p-8 space-y-3">
                {[1,2,3,4].map(i => <div key={i} className="bg-gray-100 rounded-lg h-4 animate-pulse" />)}
              </div>
            )}
            {!reportLoading && fullReport && (
              <>
                <div className="px-6 py-4 border-b border-gray-50 bg-gray-50 flex items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold text-gray-900 text-sm flex items-center gap-2">
                      <ShieldCheck className="w-4 h-4 text-indigo-500" />
                      {fullReport.filename}
                    </p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      Generated: {fullReport.generated} · {fullReport.n_issues} issue(s) · {fullReport.n_lines} lines
                    </p>
                  </div>
                  <IssueBadge n={fullReport.n_issues} />
                </div>
                <div className="p-6 max-h-[560px] overflow-auto">
                  <MarkdownBlock text={fullReport.report} />
                </div>
              </>
            )}
            {!reportLoading && !fullReport && selected && (
              <div className="p-8 text-center text-gray-400 text-sm">
                Select a report from the list to view it.
              </div>
            )}
          </div>

        </div>
      )}
    </div>
  );
}
