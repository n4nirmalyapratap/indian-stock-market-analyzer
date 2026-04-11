import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchAdmin } from "@/lib/api";
import {
  ShieldCheck, RefreshCw, Play, AlertTriangle, CheckCircle2,
  Clock, FileText, ChevronDown, ChevronUp,
} from "lucide-react";

type SebiReport = {
  filename: string;
  generated: string;
  report: string;
};

type AuditResult = {
  status: "ok" | "error";
  stdout: string;
  report: string;
};

function MarkdownBlock({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <div className="space-y-1 text-sm text-gray-800 font-mono leading-relaxed whitespace-pre-wrap break-words">
      {lines.map((line, i) => {
        if (line.startsWith("## "))
          return <p key={i} className="font-bold text-gray-900 text-base mt-4 mb-1">{line.slice(3)}</p>;
        if (line.startsWith("# "))
          return <p key={i} className="font-extrabold text-gray-900 text-lg mt-2 mb-1">{line.slice(2)}</p>;
        if (line.startsWith("### "))
          return <p key={i} className="font-semibold text-gray-800 mt-3 mb-0.5">{line.slice(4)}</p>;
        if (line.startsWith("- ") || line.startsWith("* "))
          return <p key={i} className="pl-4">• {line.slice(2)}</p>;
        if (line.startsWith("---"))
          return <hr key={i} className="border-gray-200 my-3" />;
        if (line.startsWith("> "))
          return <p key={i} className="pl-3 border-l-2 border-indigo-300 text-gray-600 italic">{line.slice(2)}</p>;
        if (line === "")
          return <div key={i} className="h-1" />;
        return <p key={i}>{line}</p>;
      })}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    ok:    "bg-green-50 text-green-700 border-green-200",
    error: "bg-red-50 text-red-700 border-red-200",
  };
  return (
    <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${map[status] ?? "bg-gray-50 text-gray-600 border-gray-200"}`}>
      {status.toUpperCase()}
    </span>
  );
}

export default function SebiAuditPage() {
  const qc = useQueryClient();
  const [showReport, setShowReport] = useState(true);
  const [runLog, setRunLog] = useState<string | null>(null);

  const { data, isLoading, isError, refetch, isFetching } = useQuery<SebiReport>({
    queryKey: ["sebi-report"],
    queryFn: () => fetchAdmin<SebiReport>("/options/sebi-report"),
    retry: false,
  });

  const run = useMutation<AuditResult>({
    mutationFn: () => fetchAdmin<AuditResult>("/options/sebi-audit", { method: "POST" }),
    onSuccess: (result) => {
      setRunLog(result.stdout);
      qc.invalidateQueries({ queryKey: ["sebi-report"] });
    },
  });

  const reportLines = data?.report?.split("\n").length ?? 0;
  const hasIssues = data?.report?.includes("## Issues Found") &&
    !data.report.includes("(No issues found)");

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <ShieldCheck className="w-6 h-6 text-indigo-600" />
            SEBI Compliance Audit
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Scrapes SEBI circulars · diffs against codebase · generates agent-ready report
          </p>
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition disabled:opacity-60"
          >
            <RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} />
            Refresh
          </button>
          <button
            onClick={() => run.mutate()}
            disabled={run.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition disabled:opacity-60"
          >
            {run.isPending ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            {run.isPending ? "Running audit…" : "Run Audit Now"}
          </button>
        </div>
      </div>

      {run.isPending && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 flex items-center gap-3 text-sm text-indigo-700">
          <RefreshCw className="w-4 h-4 animate-spin flex-shrink-0" />
          Audit in progress — scraping SEBI circulars and running AI diff…
          <span className="text-xs text-indigo-400">(may take ~60–90 seconds)</span>
        </div>
      )}

      {run.isError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
          Audit failed — check the API server logs.
        </div>
      )}

      {runLog && (
        <div className="bg-gray-900 text-green-400 rounded-xl p-4 text-xs font-mono whitespace-pre-wrap max-h-48 overflow-auto">
          {runLog}
        </div>
      )}

      {isError && !data && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-amber-800">No report yet</p>
            <p className="text-sm text-amber-700 mt-0.5">
              Click <strong>Run Audit Now</strong> to generate your first report. It will scrape the latest
              SEBI circulars and compare them against the codebase.
            </p>
          </div>
        </div>
      )}

      {isLoading && (
        <div className="space-y-3">
          {[1,2,3].map(i => <div key={i} className="bg-gray-100 rounded-xl h-16 animate-pulse" />)}
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 flex items-center gap-4">
              <div className="w-11 h-11 rounded-lg bg-indigo-50 flex items-center justify-center flex-shrink-0">
                <Clock className="w-5 h-5 text-indigo-600" />
              </div>
              <div>
                <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">Generated</p>
                <p className="text-sm font-bold text-gray-900 mt-0.5">{data.generated}</p>
              </div>
            </div>
            <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 flex items-center gap-4">
              <div className="w-11 h-11 rounded-lg bg-blue-50 flex items-center justify-center flex-shrink-0">
                <FileText className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">Report</p>
                <p className="text-sm font-bold text-gray-900 mt-0.5">{reportLines} lines</p>
              </div>
            </div>
            <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 flex items-center gap-4">
              <div className={`w-11 h-11 rounded-lg flex items-center justify-center flex-shrink-0 ${hasIssues ? "bg-red-50" : "bg-green-50"}`}>
                {hasIssues
                  ? <AlertTriangle className="w-5 h-5 text-red-500" />
                  : <CheckCircle2 className="w-5 h-5 text-green-500" />}
              </div>
              <div>
                <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">Compliance</p>
                <p className={`text-sm font-bold mt-0.5 ${hasIssues ? "text-red-600" : "text-green-700"}`}>
                  {hasIssues ? "Issues Found" : "All Clear"}
                </p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl border border-gray-100 shadow-sm">
            <button
              onClick={() => setShowReport(v => !v)}
              className="w-full flex items-center justify-between px-6 py-4 text-left"
            >
              <span className="font-semibold text-gray-900 flex items-center gap-2">
                <FileText className="w-4 h-4 text-indigo-500" />
                Audit Report — {data.filename}
              </span>
              {showReport ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
            </button>
            {showReport && (
              <div className="px-6 pb-6 border-t border-gray-50">
                <div className="mt-4 bg-gray-50 rounded-lg p-5 max-h-[600px] overflow-auto">
                  <MarkdownBlock text={data.report} />
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
