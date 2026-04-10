import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Terminal, RefreshCw } from "lucide-react";
import { useState, useRef, useEffect } from "react";

const LINE_OPTIONS = [50, 100, 200, 500];

function classifyLine(line: string): string {
  const l = line.toLowerCase();
  if (l.includes("error") || l.includes("exception") || l.includes("traceback")) return "text-red-400";
  if (l.includes("warn")) return "text-amber-400";
  if (l.includes("info")) return "text-blue-400";
  if (l.includes("debug")) return "text-gray-500";
  return "text-gray-300";
}

export default function LogsPage() {
  const [lines, setLines] = useState(100);
  const [autoScroll, setAutoScroll] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["admin-logs", lines],
    queryFn: () => api.adminLogs(lines),
    refetchInterval: 10000,
  });

  useEffect(() => {
    if (autoScroll && data?.logs) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [data, autoScroll]);

  return (
    <div className="space-y-4 h-full flex flex-col">
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Backend Logs</h1>
          <p className="text-sm text-gray-500 mt-0.5">Live Python backend output</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={lines}
            onChange={e => setLines(Number(e.target.value))}
            className="text-sm border border-gray-200 rounded-lg px-2 py-1.5 bg-white"
          >
            {LINE_OPTIONS.map(n => <option key={n} value={n}>Last {n} lines</option>)}
          </select>
          <label className="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={e => setAutoScroll(e.target.checked)}
              className="rounded"
            />
            Auto-scroll
          </label>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-2 px-3 py-1.5 text-sm bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition disabled:opacity-60"
          >
            <RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {isError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700 flex-shrink-0">
          Failed to load logs. The <code className="bg-red-100 px-1 rounded">/api/admin/logs</code> endpoint may not exist yet.
        </div>
      )}

      <div className="bg-gray-950 rounded-xl border border-gray-800 overflow-hidden flex flex-col flex-1 min-h-0" style={{ minHeight: "400px" }}>
        <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-800 bg-gray-900 flex-shrink-0">
          <Terminal className="w-4 h-4 text-green-400" />
          <span className="text-xs text-gray-400 font-mono">
            {data ? `${data.total} lines` : "Loading…"}
          </span>
          {isFetching && <span className="text-xs text-gray-500 ml-2 animate-pulse">Refreshing…</span>}
        </div>
        <div className="flex-1 overflow-y-auto p-4 font-mono text-xs space-y-0.5">
          {isLoading && (
            <p className="text-gray-500 animate-pulse">Loading logs…</p>
          )}
          {data?.logs.map((line, i) => (
            <p key={i} className={classifyLine(line)}>{line || "\u00A0"}</p>
          ))}
          {!isLoading && (!data?.logs || data.logs.length === 0) && (
            <p className="text-gray-600">No logs available</p>
          )}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  );
}
