import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchAdmin } from "@/lib/api";
import {
  Bug, Plus, RefreshCw, Trash2, ChevronDown,
  AlertCircle, AlertTriangle, Info, CheckCircle2, Clock,
  Wrench, Play, Loader2, Terminal,
} from "lucide-react";

type BugReport = {
  id: string;
  title: string;
  description: string;
  severity: "low" | "medium" | "high" | "critical";
  status: "open" | "in-progress" | "fixed" | "closed";
  component: string;
  reported_by: string;
  created_at: number;
  updated_at: number;
};

type BugsResponse = { bugs: BugReport[]; total: number };
type FixerStatus  = {
  running: boolean;
  last_run: {
    ran_at: string;
    duration_s: number;
    results: string[];
    status: "ok" | "error";
  } | null;
};

const SEVERITIES = ["critical", "high", "medium", "low"] as const;
const STATUSES   = ["open", "in-progress", "fixed", "closed"] as const;
const COMPONENTS = [
  "Options Strategy Tester", "Stock Analysis", "Charts", "Chatbot",
  "Backtest", "Admin Dashboard", "API", "Authentication", "Other",
];

const severityStyle: Record<string, string> = {
  critical: "bg-red-100 text-red-700 border-red-200",
  high:     "bg-orange-100 text-orange-700 border-orange-200",
  medium:   "bg-amber-100 text-amber-700 border-amber-200",
  low:      "bg-blue-50 text-blue-600 border-blue-200",
};
const statusStyle: Record<string, string> = {
  open:         "bg-red-50 text-red-600 border-red-200",
  "in-progress":"bg-amber-50 text-amber-700 border-amber-200",
  fixed:        "bg-green-50 text-green-700 border-green-200",
  closed:       "bg-gray-100 text-gray-500 border-gray-200",
};

function Badge({ text, style }: { text: string; style: string }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold border ${style}`}>
      {text}
    </span>
  );
}

// ── Auto-Fixer Panel ────────────────────────────────────────────────────────

function FixerPanel() {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);

  const { data: status, refetch: refetchStatus } = useQuery<FixerStatus>({
    queryKey: ["fixer-status"],
    queryFn:  () => fetchAdmin<FixerStatus>("/admin/bugs/fixer-status"),
    refetchInterval: (data) => (data?.state.data?.running ? 2000 : 15000),
  });

  const trigger = useMutation({
    mutationFn: () => fetchAdmin("/admin/bugs/run-fixer", { method: "POST" }),
    onSuccess: () => {
      refetchStatus();
      qc.invalidateQueries({ queryKey: ["bugs"] });
      setExpanded(true);
    },
  });

  const running = status?.running ?? false;
  const last    = status?.last_run;

  const resultColor = (r: string) => {
    if (r.startsWith("FIXED"))      return "text-green-700";
    if (r.startsWith("SKIP"))       return "text-amber-600";
    if (r.startsWith("ERROR"))      return "text-red-600";
    if (r.startsWith("TEST_FAIL"))  return "text-orange-600";
    if (r.startsWith("PATCH_FAIL")) return "text-orange-600";
    if (r.startsWith("DRY-RUN"))    return "text-blue-600";
    return "text-gray-600";
  };

  return (
    <div className="bg-gradient-to-r from-indigo-50 to-violet-50 border border-indigo-200 rounded-xl overflow-hidden">
      <div className="px-5 py-4 flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-indigo-100 rounded-lg flex items-center justify-center flex-shrink-0">
            <Wrench className="w-5 h-5 text-indigo-600" />
          </div>
          <div>
            <p className="font-semibold text-gray-900 text-sm">Autonomous Bug Fixer</p>
            <p className="text-xs text-gray-500">
              {running
                ? "Running — analysing open bugs and applying fixes…"
                : last
                  ? `Last run ${last.ran_at.replace("T", " ").replace("Z", " UTC")} · ${last.duration_s}s · ${last.results.length} bug(s) processed`
                  : "Runs automatically every 10 minutes. Analyses open bugs, applies safe fixes, runs tests, pushes to GitHub."}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {last && (
            <button
              onClick={() => setExpanded(v => !v)}
              className="text-xs text-indigo-600 hover:text-indigo-800 underline underline-offset-2"
            >
              {expanded ? "Hide results" : "Show last results"}
            </button>
          )}
          <button
            onClick={() => trigger.mutate()}
            disabled={running || trigger.isPending}
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition disabled:opacity-60"
          >
            {running
              ? <><Loader2 className="w-4 h-4 animate-spin" /> Running…</>
              : <><Play className="w-4 h-4" /> Run Now</>}
          </button>
        </div>
      </div>

      {expanded && last && (
        <div className="border-t border-indigo-200 bg-white/60 px-5 py-4">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-1.5">
            <Terminal className="w-3.5 h-3.5" /> Last Run Results
          </p>
          <div className="space-y-1 font-mono text-xs">
            {last.results.map((r, i) => (
              <p key={i} className={resultColor(r)}>{r}</p>
            ))}
          </div>
          <p className={`mt-3 text-xs font-medium ${last.status === "ok" ? "text-green-600" : "text-red-600"}`}>
            {last.status === "ok" ? "✓ Completed successfully" : "✗ Completed with errors"}
            {" · "}Duration: {last.duration_s}s
          </p>
        </div>
      )}
    </div>
  );
}

// ── Add Bug Modal ───────────────────────────────────────────────────────────

function AddBugModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    title: "", description: "", severity: "medium",
    component: "", reported_by: "",
  });
  const [err, setErr] = useState("");

  const create = useMutation({
    mutationFn: (data: typeof form) =>
      fetchAdmin("/admin/bugs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["bugs"] }); onClose(); },
    onError: (e: any) => setErr(e.message),
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.title.trim()) { setErr("Title is required"); return; }
    create.mutate(form);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-2">
          <Bug className="w-5 h-5 text-indigo-600" />
          <h2 className="font-bold text-gray-900">Report a Bug</h2>
        </div>
        <form onSubmit={submit} className="p-6 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">Title *</label>
            <input
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              placeholder="Brief description of the bug"
              value={form.title}
              onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">Description</label>
            <textarea
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 resize-none h-24"
              placeholder="Steps to reproduce, expected vs actual behaviour…"
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">Severity</label>
              <div className="relative">
                <select
                  className="w-full appearance-none border border-gray-200 rounded-lg px-3 py-2 text-sm pr-8 focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  value={form.severity}
                  onChange={e => setForm(f => ({ ...f, severity: e.target.value }))}
                >
                  {SEVERITIES.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
                </select>
                <ChevronDown className="absolute right-2 top-2.5 w-4 h-4 text-gray-400 pointer-events-none" />
              </div>
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">Component</label>
              <div className="relative">
                <select
                  className="w-full appearance-none border border-gray-200 rounded-lg px-3 py-2 text-sm pr-8 focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  value={form.component}
                  onChange={e => setForm(f => ({ ...f, component: e.target.value }))}
                >
                  <option value="">— Select —</option>
                  {COMPONENTS.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
                <ChevronDown className="absolute right-2 top-2.5 w-4 h-4 text-gray-400 pointer-events-none" />
              </div>
            </div>
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">Reported by</label>
            <input
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              placeholder="Name or email"
              value={form.reported_by}
              onChange={e => setForm(f => ({ ...f, reported_by: e.target.value }))}
            />
          </div>
          {err && <p className="text-red-600 text-xs">{err}</p>}
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose}
              className="px-4 py-2 text-sm text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition">
              Cancel
            </button>
            <button type="submit" disabled={create.isPending}
              className="px-4 py-2 text-sm text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition disabled:opacity-60">
              {create.isPending ? "Saving…" : "Save Bug"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Bug Card ────────────────────────────────────────────────────────────────

function BugCard({ bug }: { bug: BugReport }) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);

  const patch = useMutation({
    mutationFn: (data: Partial<BugReport>) =>
      fetchAdmin(`/admin/bugs/${bug.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["bugs"] }),
  });

  const remove = useMutation({
    mutationFn: () => fetchAdmin(`/admin/bugs/${bug.id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["bugs"] }),
  });

  const date = new Date(bug.created_at * 1000).toLocaleDateString("en-IN", {
    day: "numeric", month: "short", year: "numeric",
  });

  return (
    <div className={`bg-white rounded-xl border shadow-sm transition-all
      ${bug.status === "closed" || bug.status === "fixed" ? "opacity-70" : ""}
      ${bug.severity === "critical" ? "border-l-4 border-l-red-500" :
        bug.severity === "high"     ? "border-l-4 border-l-orange-400" :
        "border border-gray-100"}`}>
      <div className="px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-mono text-gray-400">#{bug.id}</span>
              <Badge text={bug.severity} style={severityStyle[bug.severity] ?? ""} />
              <Badge text={bug.status}   style={statusStyle[bug.status]   ?? ""} />
              {bug.component && (
                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{bug.component}</span>
              )}
            </div>
            <p className="font-semibold text-gray-900 mt-1.5 text-sm">{bug.title}</p>
            {bug.description && (
              <button
                onClick={() => setExpanded(v => !v)}
                className="text-xs text-indigo-500 hover:text-indigo-700 mt-1 flex items-center gap-0.5"
              >
                {expanded ? "Hide details" : "Show details"}
                <ChevronDown className={`w-3 h-3 transition-transform ${expanded ? "rotate-180" : ""}`} />
              </button>
            )}
            {expanded && bug.description && (
              <p className="text-xs text-gray-600 mt-2 bg-gray-50 rounded-lg p-3 whitespace-pre-wrap">{bug.description}</p>
            )}
            <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
              {bug.reported_by && <span>by {bug.reported_by}</span>}
              <span>{date}</span>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <div className="relative">
              <select
                value={bug.status}
                onChange={e => patch.mutate({ status: e.target.value as BugReport["status"] })}
                className="appearance-none text-xs border border-gray-200 rounded-lg px-2 py-1.5 pr-6 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-400"
              >
                {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
              <ChevronDown className="absolute right-1.5 top-2 w-3 h-3 text-gray-400 pointer-events-none" />
            </div>
            <button
              onClick={() => remove.mutate()}
              disabled={remove.isPending}
              className="p-1.5 text-gray-300 hover:text-red-500 rounded transition"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────────────────

const FILTER_STATUSES   = ["all", ...STATUSES];
const FILTER_SEVERITIES = ["all", ...SEVERITIES];

export default function BugReportsPage() {
  const [showAdd, setShowAdd]             = useState(false);
  const [filterStatus, setFilterStatus]   = useState("all");
  const [filterSeverity, setFilterSeverity] = useState("all");
  const [search, setSearch]               = useState("");

  const { data, isLoading, isError, refetch, isFetching } = useQuery<BugsResponse>({
    queryKey: ["bugs"],
    queryFn:  () => fetchAdmin<BugsResponse>("/admin/bugs"),
    refetchInterval: 30000,
  });

  const bugs     = data?.bugs ?? [];
  const filtered = bugs.filter(b => {
    if (filterStatus   !== "all" && b.status   !== filterStatus)   return false;
    if (filterSeverity !== "all" && b.severity !== filterSeverity) return false;
    if (search && !b.title.toLowerCase().includes(search.toLowerCase()) &&
        !b.description.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const counts = {
    open:       bugs.filter(b => b.status === "open").length,
    inProgress: bugs.filter(b => b.status === "in-progress").length,
    fixed:      bugs.filter(b => b.status === "fixed" || b.status === "closed").length,
    critical:   bugs.filter(b => b.severity === "critical").length,
  };

  return (
    <div className="space-y-6">
      {showAdd && <AddBugModal onClose={() => setShowAdd(false)} />}

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Bug className="w-6 h-6 text-red-500" />
            Bug Tracker
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            All bugs are tracked here first — nothing is resolved without a ticket
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
            onClick={() => setShowAdd(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition"
          >
            <Plus className="w-4 h-4" />
            Report Bug
          </button>
        </div>
      </div>

      {/* Auto-Fixer Panel */}
      <FixerPanel />

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: "Open",        value: counts.open,       color: "text-red-600",   bg: "bg-red-50",   icon: Clock },
          { label: "In Progress", value: counts.inProgress, color: "text-amber-700", bg: "bg-amber-50", icon: RefreshCw },
          { label: "Resolved",    value: counts.fixed,      color: "text-green-700", bg: "bg-green-50", icon: CheckCircle2 },
          { label: "Critical",    value: counts.critical,   color: "text-red-700",   bg: "bg-red-100",  icon: AlertCircle },
        ].map(({ label, value, color, bg, icon: Icon }) => (
          <div key={label} className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 flex items-center gap-3">
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${bg}`}>
              <Icon className={`w-5 h-5 ${color}`} />
            </div>
            <div>
              <p className="text-xs text-gray-500 font-medium">{label}</p>
              <p className={`text-xl font-bold ${color}`}>{value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <input
          className="flex-1 min-w-[180px] border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
          placeholder="Search bugs…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <div className="relative">
          <select
            className="appearance-none border border-gray-200 rounded-lg px-3 py-2 text-sm pr-7 focus:outline-none focus:ring-2 focus:ring-indigo-400"
            value={filterStatus}
            onChange={e => setFilterStatus(e.target.value)}
          >
            {FILTER_STATUSES.map(s => <option key={s} value={s}>{s === "all" ? "All statuses" : s}</option>)}
          </select>
          <ChevronDown className="absolute right-2 top-2.5 w-4 h-4 text-gray-400 pointer-events-none" />
        </div>
        <div className="relative">
          <select
            className="appearance-none border border-gray-200 rounded-lg px-3 py-2 text-sm pr-7 focus:outline-none focus:ring-2 focus:ring-indigo-400"
            value={filterSeverity}
            onChange={e => setFilterSeverity(e.target.value)}
          >
            {FILTER_SEVERITIES.map(s => <option key={s} value={s}>{s === "all" ? "All severities" : s}</option>)}
          </select>
          <ChevronDown className="absolute right-2 top-2.5 w-4 h-4 text-gray-400 pointer-events-none" />
        </div>
      </div>

      {/* Bug list */}
      {isLoading && (
        <div className="space-y-3">
          {[1,2,3].map(i => <div key={i} className="bg-gray-100 rounded-xl h-20 animate-pulse" />)}
        </div>
      )}

      {isError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
          Failed to load bug reports.
        </div>
      )}

      {!isLoading && filtered.length === 0 && (
        <div className="bg-white rounded-xl border border-gray-100 p-10 text-center">
          <Bug className="w-10 h-10 text-gray-200 mx-auto mb-3" />
          <p className="font-medium text-gray-500">
            {bugs.length === 0 ? "No bugs reported yet" : "No bugs match your filters"}
          </p>
          {bugs.length === 0 && (
            <button
              onClick={() => setShowAdd(true)}
              className="mt-3 px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition"
            >
              Report the first bug
            </button>
          )}
        </div>
      )}

      <div className="space-y-3">
        {filtered.map(bug => <BugCard key={bug.id} bug={bug} />)}
      </div>
    </div>
  );
}
