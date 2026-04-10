import { useState, useRef, useEffect, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, LogRecord } from "@/lib/api";
import {
  RefreshCw, Search, X, ArrowDown, Copy, Check,
  FileText, Terminal, AlertTriangle, CheckCircle, Info,
  TrendingUp, Zap, Clock, AlertCircle,
} from "lucide-react";

const LEVELS = ["ALL", "ERROR", "WARNING", "INFO", "DEBUG"] as const;
type Level = typeof LEVELS[number];

const LINE_OPTIONS = [100, 200, 500, 1000];

const LEVEL_STYLES: Record<string, string> = {
  ERROR:    "bg-red-500/20 text-red-400 border border-red-500/30",
  CRITICAL: "bg-red-600/20 text-red-300 border border-red-600/30",
  WARNING:  "bg-amber-500/20 text-amber-400 border border-amber-500/30",
  WARN:     "bg-amber-500/20 text-amber-400 border border-amber-500/30",
  INFO:     "bg-blue-500/20 text-blue-400 border border-blue-500/30",
  DEBUG:    "bg-gray-700/60 text-gray-400 border border-gray-600/40",
};

const LEVEL_TEXT: Record<string, string> = {
  ERROR:    "text-red-300",
  CRITICAL: "text-red-300",
  WARNING:  "text-amber-300",
  WARN:     "text-amber-300",
  INFO:     "text-gray-200",
  DEBUG:    "text-gray-500",
};

// ─── Plain English helpers ───────────────────────────────────────────────────

interface LogSummary {
  health: "healthy" | "degraded" | "critical";
  headline: string;
  details: SummaryItem[];
  topErrors: { msg: string; count: number }[];
  topWarnings: { msg: string; count: number }[];
  recentActivity: string[];
  timespan: string | null;
}

interface SummaryItem {
  icon: React.ReactNode;
  label: string;
  value: string;
  color: string;
}

function normalise(msg: string): string {
  return msg.replace(/\b\d{4,}\b/g, "N").replace(/\b[0-9a-f-]{32,}\b/gi, "ID").trim();
}

function buildSummary(logs: LogRecord[]): LogSummary {
  if (logs.length === 0) {
    return {
      health: "healthy",
      headline: "No log records available",
      details: [],
      topErrors: [],
      topWarnings: [],
      recentActivity: [],
      timespan: null,
    };
  }

  const errors   = logs.filter(r => r.level === "ERROR" || r.level === "CRITICAL");
  const warnings = logs.filter(r => r.level === "WARNING" || r.level === "WARN");
  const infos    = logs.filter(r => r.level === "INFO");
  const debugs   = logs.filter(r => r.level === "DEBUG");

  // Determine health
  const health: LogSummary["health"] =
    errors.length > 5   ? "critical" :
    errors.length > 0   ? "degraded" :
    warnings.length > 5 ? "degraded" :
    "healthy";

  // Time span
  const timestamps = logs.map(r => r.ts).sort((a, b) => a - b);
  const oldest  = new Date(timestamps[0]  * 1000);
  const newest  = new Date(timestamps[timestamps.length - 1] * 1000);
  const spanMs  = newest.getTime() - oldest.getTime();
  const spanMin = Math.round(spanMs / 60000);
  const timespan = spanMin < 1
    ? "less than a minute"
    : spanMin < 60
    ? `${spanMin} minute${spanMin !== 1 ? "s" : ""}`
    : `${Math.round(spanMin / 60)} hour${Math.round(spanMin / 60) !== 1 ? "s" : ""}`;

  // Headline
  const headline =
    health === "critical"
      ? `Backend is experiencing errors — ${errors.length} error${errors.length !== 1 ? "s" : ""} in the last ${timespan}`
      : health === "degraded"
      ? warnings.length > 0 && errors.length === 0
        ? `Backend is running with ${warnings.length} warning${warnings.length !== 1 ? "s" : ""} over the last ${timespan}`
        : `Backend has had ${errors.length} error${errors.length !== 1 ? "s" : ""} in the last ${timespan} — check details below`
      : `Backend looks healthy — no errors in the last ${timespan}`;

  // Frequency
  const rate = spanMs > 0 ? (logs.length / (spanMs / 60000)).toFixed(1) : "—";

  const details: SummaryItem[] = [
    {
      icon: <FileText className="w-4 h-4" />,
      label: "Total records",
      value: `${logs.length} log line${logs.length !== 1 ? "s" : ""}`,
      color: "text-gray-300",
    },
    {
      icon: <Clock className="w-4 h-4" />,
      label: "Covering",
      value: timespan,
      color: "text-gray-300",
    },
    {
      icon: <TrendingUp className="w-4 h-4" />,
      label: "Log rate",
      value: `~${rate} lines / min`,
      color: "text-gray-300",
    },
    {
      icon: <AlertCircle className="w-4 h-4" />,
      label: "Errors",
      value: errors.length === 0 ? "None — great!" : `${errors.length} error${errors.length !== 1 ? "s" : ""}`,
      color: errors.length > 0 ? "text-red-400" : "text-green-400",
    },
    {
      icon: <AlertTriangle className="w-4 h-4" />,
      label: "Warnings",
      value: warnings.length === 0 ? "None" : `${warnings.length} warning${warnings.length !== 1 ? "s" : ""}`,
      color: warnings.length > 0 ? "text-amber-400" : "text-green-400",
    },
    {
      icon: <Info className="w-4 h-4" />,
      label: "Info messages",
      value: `${infos.length}`,
      color: "text-blue-400",
    },
    {
      icon: <Zap className="w-4 h-4" />,
      label: "Debug messages",
      value: `${debugs.length}`,
      color: "text-gray-500",
    },
  ];

  // Top errors by frequency
  const errorBuckets = new Map<string, number>();
  errors.forEach(r => {
    const key = normalise(r.msg).slice(0, 80);
    errorBuckets.set(key, (errorBuckets.get(key) ?? 0) + 1);
  });
  const topErrors = [...errorBuckets.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([msg, count]) => ({ msg, count }));

  // Top warnings
  const warnBuckets = new Map<string, number>();
  warnings.forEach(r => {
    const key = normalise(r.msg).slice(0, 80);
    warnBuckets.set(key, (warnBuckets.get(key) ?? 0) + 1);
  });
  const topWarnings = [...warnBuckets.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([msg, count]) => ({ msg, count }));

  // Recent activity (last 8 INFO+ messages, plain language)
  const recentActivity = logs
    .filter(r => r.level !== "DEBUG")
    .slice(-8)
    .reverse()
    .map(r => {
      const timeStr = new Date(r.ts * 1000).toLocaleTimeString();
      return `[${timeStr}] ${r.msg.slice(0, 100)}`;
    });

  return { health, headline, details, topErrors, topWarnings, recentActivity, timespan };
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function LevelBadge({ level }: { level: string }) {
  const cls = LEVEL_STYLES[level] ?? "bg-gray-700/60 text-gray-400 border border-gray-600/40";
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold font-mono shrink-0 ${cls}`}>
      {level.slice(0, 4)}
    </span>
  );
}

function formatTs(ts: number): string {
  const d = new Date(ts * 1000);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  const ms = String(d.getMilliseconds()).padStart(3, "0");
  return `${hh}:${mm}:${ss}.${ms}`;
}

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString(undefined, {
    month: "short", day: "numeric",
  });
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        });
      }}
      className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-gray-300 transition ml-2 flex-shrink-0"
      title="Copy line"
    >
      {copied
        ? <Check className="w-3 h-3 text-green-400" />
        : <Copy className="w-3 h-3" />}
    </button>
  );
}

function LogRow({ record, prev }: { record: LogRecord; prev?: LogRecord }) {
  const showDate = !prev || formatDate(record.ts) !== formatDate(prev.ts);
  const msgCls = LEVEL_TEXT[record.level] ?? "text-gray-300";

  return (
    <>
      {showDate && (
        <div className="flex items-center gap-3 py-1 px-4 sticky top-0 z-10 bg-gray-950/90 backdrop-blur-sm">
          <div className="flex-1 h-px bg-gray-800" />
          <span className="text-[10px] text-gray-600 font-medium">{formatDate(record.ts)}</span>
          <div className="flex-1 h-px bg-gray-800" />
        </div>
      )}
      <div className="group flex items-start gap-3 px-4 py-1.5 hover:bg-white/[0.03] rounded-sm transition-colors">
        <span className="text-[10px] text-gray-600 font-mono shrink-0 mt-0.5 w-[80px]">
          {formatTs(record.ts)}
        </span>
        <LevelBadge level={record.level} />
        <span className="text-[10px] text-gray-600 font-mono shrink-0 mt-0.5 max-w-[120px] truncate" title={record.logger}>
          {record.logger}
        </span>
        <span className={`flex-1 text-xs font-mono break-all leading-relaxed ${msgCls}`}>
          {record.msg}
        </span>
        <CopyButton text={`${formatTs(record.ts)} ${record.level} ${record.logger} ${record.msg}`} />
      </div>
    </>
  );
}

// ─── Summary tab ─────────────────────────────────────────────────────────────

function SummaryPanel({ logs, total }: { logs: LogRecord[]; total: number }) {
  const summary = buildSummary(logs);

  const healthConfig = {
    healthy:  { icon: <CheckCircle  className="w-5 h-5" />, bg: "bg-green-50",  border: "border-green-200",  text: "text-green-700",  dot: "bg-green-500"  },
    degraded: { icon: <AlertTriangle className="w-5 h-5" />, bg: "bg-amber-50",  border: "border-amber-200",  text: "text-amber-700",  dot: "bg-amber-500"  },
    critical: { icon: <AlertCircle  className="w-5 h-5" />, bg: "bg-red-50",    border: "border-red-200",    text: "text-red-700",    dot: "bg-red-500"    },
  }[summary.health];

  return (
    <div className="space-y-5 pb-6">

      {/* Health banner */}
      <div className={`flex items-start gap-3 p-4 rounded-xl border ${healthConfig.bg} ${healthConfig.border}`}>
        <span className={`${healthConfig.text} mt-0.5 flex-shrink-0`}>{healthConfig.icon}</span>
        <div>
          <p className={`font-semibold ${healthConfig.text}`}>{summary.headline}</p>
          {summary.timespan && (
            <p className="text-sm text-gray-500 mt-0.5">
              Analysing {logs.length.toLocaleString()} of {total.toLocaleString()} records
            </p>
          )}
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {summary.details.map((item, i) => (
          <div key={i} className="flex flex-col gap-1.5 p-3 bg-gray-50 rounded-xl border border-gray-200">
            <span className="text-gray-400 flex items-center gap-1.5">
              {item.icon}
              <span className="text-xs text-gray-500">{item.label}</span>
            </span>
            <span className={`text-sm font-semibold ${item.color}`}>{item.value}</span>
          </div>
        ))}
      </div>

      {/* Recent activity */}
      {summary.recentActivity.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Recent activity</h3>
          <div className="bg-gray-50 rounded-xl border border-gray-200 divide-y divide-gray-100">
            {summary.recentActivity.map((line, i) => (
              <p key={i} className="px-4 py-2 text-xs text-gray-600 font-mono leading-relaxed">{line}</p>
            ))}
          </div>
        </div>
      )}

      {/* Top errors */}
      {summary.topErrors.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-red-600 mb-2 flex items-center gap-1.5">
            <AlertCircle className="w-4 h-4" /> Most frequent errors
          </h3>
          <div className="space-y-2">
            {summary.topErrors.map((e, i) => (
              <div key={i} className="flex items-start gap-3 p-3 bg-red-50 rounded-xl border border-red-100">
                <span className="text-xs font-bold text-red-500 bg-red-100 px-2 py-0.5 rounded-full shrink-0 mt-0.5">
                  ×{e.count}
                </span>
                <p className="text-xs text-red-700 font-mono leading-relaxed">{e.msg}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Top warnings */}
      {summary.topWarnings.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-amber-600 mb-2 flex items-center gap-1.5">
            <AlertTriangle className="w-4 h-4" /> Most frequent warnings
          </h3>
          <div className="space-y-2">
            {summary.topWarnings.map((w, i) => (
              <div key={i} className="flex items-start gap-3 p-3 bg-amber-50 rounded-xl border border-amber-100">
                <span className="text-xs font-bold text-amber-600 bg-amber-100 px-2 py-0.5 rounded-full shrink-0 mt-0.5">
                  ×{w.count}
                </span>
                <p className="text-xs text-amber-700 font-mono leading-relaxed">{w.msg}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* All clear message */}
      {summary.topErrors.length === 0 && summary.topWarnings.length === 0 && summary.timespan && (
        <div className="flex items-center gap-3 p-4 bg-green-50 rounded-xl border border-green-200">
          <CheckCircle className="w-5 h-5 text-green-500 shrink-0" />
          <p className="text-sm text-green-700">
            No errors or warnings in this window — the backend is running cleanly.
          </p>
        </div>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

type View = "raw" | "summary";

export default function LogsPage() {
  const [view,         setView]         = useState<View>("summary");
  const [lines,        setLines]        = useState(200);
  const [levelFilter,  setLevelFilter]  = useState<Level>("ALL");
  const [search,       setSearch]       = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [streaming,    setStreaming]    = useState(true);
  const [atBottom,     setAtBottom]     = useState(true);
  const bottomRef  = useRef<HTMLDivElement>(null);
  const scrollRef  = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedSearch(search), 400);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [search]);

  const { data, isLoading, isFetching, refetch, dataUpdatedAt } = useQuery({
    queryKey: ["admin-logs", lines, levelFilter, debouncedSearch],
    queryFn:  () => api.adminLogs(
      lines,
      levelFilter === "ALL" ? "" : levelFilter,
      debouncedSearch,
    ),
    refetchInterval: streaming ? 5000 : false,
  });

  useEffect(() => {
    if (streaming && atBottom && view === "raw") {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [data, streaming, atBottom, view]);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 60);
  }, []);

  const scrollToBottom = () => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    setAtBottom(true);
  };

  const lastUpdate = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString()
    : null;

  const logs: LogRecord[]  = data?.logs ?? [];
  const errorCount   = logs.filter(r => r.level === "ERROR" || r.level === "CRITICAL").length;
  const warningCount = logs.filter(r => r.level === "WARNING" || r.level === "WARN").length;

  return (
    <div className="flex flex-col h-full space-y-3" style={{ minHeight: 0 }}>

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex-shrink-0">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Backend Logs</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              Live Python backend output
              {lastUpdate && (
                <span className="ml-2 text-gray-400">· updated {lastUpdate}</span>
              )}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {/* View toggle */}
            <div className="flex items-center bg-gray-100 rounded-lg p-1 gap-1">
              <button
                onClick={() => setView("summary")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition ${
                  view === "summary"
                    ? "bg-white text-gray-900 shadow-sm"
                    : "text-gray-500 hover:text-gray-700"
                }`}
              >
                <FileText className="w-3.5 h-3.5" /> Summary
              </button>
              <button
                onClick={() => setView("raw")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition ${
                  view === "raw"
                    ? "bg-white text-gray-900 shadow-sm"
                    : "text-gray-500 hover:text-gray-700"
                }`}
              >
                <Terminal className="w-3.5 h-3.5" /> Raw
              </button>
            </div>

            {/* Streaming toggle */}
            <button
              onClick={() => setStreaming(s => !s)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition ${
                streaming
                  ? "bg-green-50 border-green-200 text-green-700 hover:bg-green-100"
                  : "bg-gray-100 border-gray-200 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {streaming
                ? <><span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" /> Live</>
                : <><span className="w-1.5 h-1.5 rounded-full bg-gray-400" /> Paused</>}
            </button>

            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 transition disabled:opacity-60"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? "animate-spin" : ""}`} />
              Refresh
            </button>
          </div>
        </div>

        {/* Stats bar */}
        {logs.length > 0 && (
          <div className="flex items-center gap-3 mb-3">
            <span className="text-xs text-gray-500 bg-gray-100 px-2.5 py-1 rounded-full">
              {data?.total ?? 0} lines
            </span>
            {errorCount > 0 && (
              <span className="text-xs font-medium bg-red-50 text-red-600 border border-red-200 px-2.5 py-1 rounded-full">
                {errorCount} error{errorCount !== 1 ? "s" : ""}
              </span>
            )}
            {warningCount > 0 && (
              <span className="text-xs font-medium bg-amber-50 text-amber-600 border border-amber-200 px-2.5 py-1 rounded-full">
                {warningCount} warning{warningCount !== 1 ? "s" : ""}
              </span>
            )}
            {errorCount === 0 && warningCount === 0 && (
              <span className="text-xs font-medium bg-green-50 text-green-600 border border-green-200 px-2.5 py-1 rounded-full flex items-center gap-1">
                <CheckCircle className="w-3 h-3" /> All clear
              </span>
            )}
          </div>
        )}

        {/* Filters row (only shown in Raw view) */}
        {view === "raw" && (
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
              {LEVELS.map(lvl => (
                <button
                  key={lvl}
                  onClick={() => setLevelFilter(lvl)}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium transition ${
                    levelFilter === lvl
                      ? "bg-white text-gray-900 shadow-sm"
                      : "text-gray-500 hover:text-gray-700"
                  }`}
                >
                  {lvl === "ALL" ? "All" : lvl === "WARNING" ? "WARN" : lvl}
                </button>
              ))}
            </div>

            <div className="relative flex-1 min-w-[180px] max-w-xs">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
              <input
                type="text"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search logs…"
                className="w-full pl-8 pr-8 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition"
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            <select
              value={lines}
              onChange={e => setLines(Number(e.target.value))}
              className="text-sm border border-gray-200 rounded-lg px-2.5 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {LINE_OPTIONS.map(n => <option key={n} value={n}>Last {n}</option>)}
            </select>
          </div>
        )}

        {/* Line count selector in Summary view */}
        {view === "summary" && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">Analyse last</span>
            <select
              value={lines}
              onChange={e => setLines(Number(e.target.value))}
              className="text-sm border border-gray-200 rounded-lg px-2.5 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {LINE_OPTIONS.map(n => <option key={n} value={n}>{n} records</option>)}
            </select>
          </div>
        )}
      </div>

      {/* ── Summary view ─────────────────────────────────────────────────────── */}
      {view === "summary" && (
        <div className="flex-1 overflow-y-auto pr-1" style={{ minHeight: 0 }}>
          {isLoading ? (
            <div className="flex items-center justify-center h-32 text-gray-400 text-sm">
              Loading logs…
            </div>
          ) : (
            <SummaryPanel logs={logs} total={data?.total ?? logs.length} />
          )}
        </div>
      )}

      {/* ── Raw log panel ────────────────────────────────────────────────────── */}
      {view === "raw" && (
        <div className="relative flex flex-col bg-gray-950 rounded-xl border border-gray-800 overflow-hidden flex-1 min-h-0" style={{ minHeight: 400 }}>

          {/* Terminal header bar */}
          <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-800/80 bg-gray-900 flex-shrink-0">
            <div className="flex gap-1.5">
              <span className="w-3 h-3 rounded-full bg-red-500/70" />
              <span className="w-3 h-3 rounded-full bg-yellow-500/70" />
              <span className="w-3 h-3 rounded-full bg-green-500/70" />
            </div>
            <span className="flex-1 text-center text-[11px] text-gray-500 font-mono">
              python-backend · {data?.total ?? "…"} records
              {debouncedSearch && ` · filtered by "${debouncedSearch}"`}
            </span>
            {isFetching && (
              <span className="flex items-center gap-1 text-[10px] text-gray-500">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                syncing
              </span>
            )}
          </div>

          {/* Column headers */}
          <div className="flex items-center gap-3 px-4 py-1.5 border-b border-gray-800/50 bg-gray-900/50 flex-shrink-0">
            <span className="text-[9px] uppercase tracking-wider text-gray-600 w-[80px]">Time</span>
            <span className="text-[9px] uppercase tracking-wider text-gray-600 w-[36px]">Level</span>
            <span className="text-[9px] uppercase tracking-wider text-gray-600 w-[120px]">Logger</span>
            <span className="text-[9px] uppercase tracking-wider text-gray-600 flex-1">Message</span>
          </div>

          {/* Scrollable log body */}
          <div
            ref={scrollRef}
            onScroll={handleScroll}
            className="flex-1 overflow-y-auto py-1"
          >
            {isLoading && (
              <div className="flex items-center justify-center h-32 text-gray-600 text-sm font-mono">
                Loading logs…
              </div>
            )}

            {!isLoading && logs.length === 0 && (
              <div className="flex flex-col items-center justify-center h-32 gap-2 text-gray-600 text-sm font-mono">
                <span>No log records found</span>
                {(levelFilter !== "ALL" || search) && (
                  <button
                    onClick={() => { setLevelFilter("ALL"); setSearch(""); }}
                    className="text-xs text-indigo-400 hover:text-indigo-300"
                  >
                    Clear filters
                  </button>
                )}
              </div>
            )}

            {logs.map((record, i) => (
              <LogRow key={i} record={record} prev={logs[i - 1]} />
            ))}

            <div ref={bottomRef} className="h-2" />
          </div>

          {/* Jump to bottom button */}
          {!atBottom && (
            <button
              onClick={scrollToBottom}
              className="absolute bottom-4 right-4 flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium rounded-full shadow-lg transition"
            >
              <ArrowDown className="w-3 h-3" />
              Jump to bottom
            </button>
          )}
        </div>
      )}
    </div>
  );
}
