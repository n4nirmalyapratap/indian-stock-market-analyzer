import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchAdmin } from "@/lib/api";
import {
  Database, Activity, Globe, Cpu, BarChart2, HeartPulse,
  Play, RefreshCw, CheckCircle2, XCircle, Clock, Loader2,
} from "lucide-react";

type Job = {
  id: string;
  name: string;
  description: string;
  category: string;
  icon: string;
  status: "idle" | "running" | "success" | "error";
  last_run: number | null;
  duration_s: number | null;
  last_result: string;
};

const ICONS: Record<string, React.ElementType> = {
  database:     Database,
  activity:     Activity,
  globe:        Globe,
  cpu:          Cpu,
  "bar-chart":  BarChart2,
  "heart-pulse": HeartPulse,
};

const CATEGORY_COLORS: Record<string, string> = {
  "Market Data": "bg-blue-50 text-blue-700 border-blue-100",
  "Analysis":    "bg-purple-50 text-purple-700 border-purple-100",
  "AI Engine":   "bg-indigo-50 text-indigo-700 border-indigo-100",
  "Monitoring":  "bg-green-50 text-green-700 border-green-100",
};

function StatusBadge({ status }: { status: Job["status"] }) {
  if (status === "running") return (
    <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-100">
      <Loader2 className="w-3 h-3 animate-spin" /> Running
    </span>
  );
  if (status === "success") return (
    <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-green-50 text-green-700 border border-green-100">
      <CheckCircle2 className="w-3 h-3" /> Success
    </span>
  );
  if (status === "error") return (
    <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-red-50 text-red-700 border border-red-100">
      <XCircle className="w-3 h-3" /> Error
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-gray-50 text-gray-500 border border-gray-100">
      <Clock className="w-3 h-3" /> Idle
    </span>
  );
}

function fmtTs(ts: number | null): string {
  if (!ts) return "Never";
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    + " · " + d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
}

function JobCard({ job, onRun, running }: { job: Job; onRun: (id: string) => void; running: boolean }) {
  const Icon = ICONS[job.icon] ?? Activity;
  const catColor = CATEGORY_COLORS[job.category] ?? "bg-gray-50 text-gray-600 border-gray-100";
  const isRunning = job.status === "running" || running;

  return (
    <div className={`bg-white rounded-xl border shadow-sm p-5 flex flex-col gap-3 transition-all ${
      isRunning ? "border-amber-200 shadow-amber-50" :
      job.status === "success" ? "border-green-100" :
      job.status === "error" ? "border-red-100" : "border-gray-100"
    }`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${catColor}`}>
            <Icon className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <p className="font-semibold text-sm text-gray-900 leading-tight">{job.name}</p>
            <span className={`inline-block text-[10px] font-medium px-1.5 py-0.5 rounded border mt-0.5 ${catColor}`}>
              {job.category}
            </span>
          </div>
        </div>
        <StatusBadge status={isRunning ? "running" : job.status} />
      </div>

      <p className="text-xs text-gray-500 leading-relaxed">{job.description}</p>

      {job.last_result && (
        <div className={`text-xs rounded-lg px-3 py-2 font-mono leading-snug break-all ${
          job.status === "error"
            ? "bg-red-50 text-red-700 border border-red-100"
            : "bg-gray-50 text-gray-600 border border-gray-100"
        }`}>
          {job.last_result}
        </div>
      )}

      <div className="flex items-center justify-between pt-1 border-t border-gray-50">
        <div className="text-[11px] text-gray-400 space-y-0.5">
          <p><span className="font-medium">Last run:</span> {fmtTs(job.last_run)}</p>
          {job.duration_s != null && (
            <p><span className="font-medium">Duration:</span> {job.duration_s}s</p>
          )}
        </div>
        <button
          onClick={() => onRun(job.id)}
          disabled={isRunning}
          className={`inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg transition-all ${
            isRunning
              ? "bg-gray-100 text-gray-400 cursor-not-allowed"
              : "bg-indigo-600 hover:bg-indigo-500 active:scale-95 text-white shadow-sm"
          }`}
        >
          {isRunning
            ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Running…</>
            : <><Play className="w-3.5 h-3.5" /> Run now</>}
        </button>
      </div>
    </div>
  );
}

export default function JobsPage() {
  const qc = useQueryClient();
  const [runningIds, setRunningIds] = useState<Set<string>>(new Set());

  const { data, isLoading, isError, refetch, isFetching } = useQuery<{ jobs: Job[] }>({
    queryKey: ["admin-jobs"],
    queryFn: () => fetchAdmin("/admin/jobs"),
    refetchInterval: 3000,
  });

  const triggerMut = useMutation({
    mutationFn: (jobId: string) =>
      fetchAdmin<{ status: string }>(`/admin/jobs/${jobId}/run`, { method: "POST" }),
    onMutate: (jobId) => {
      setRunningIds(s => new Set(s).add(jobId));
    },
    onSettled: (_, __, jobId) => {
      setRunningIds(s => { const n = new Set(s); n.delete(jobId); return n; });
      setTimeout(() => qc.invalidateQueries({ queryKey: ["admin-jobs"] }), 500);
    },
  });

  const jobs = data?.jobs ?? [];
  const categories = Array.from(new Set(jobs.map(j => j.category)));

  const runningCount = jobs.filter(j => j.status === "running").length;
  const successCount = jobs.filter(j => j.status === "success").length;
  const errorCount   = jobs.filter(j => j.status === "error").length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Background Jobs</h1>
          <p className="text-sm text-gray-500 mt-0.5">Monitor and trigger all backend jobs on demand</p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-2 text-sm font-medium text-gray-600 hover:text-gray-900 bg-white border border-gray-200 rounded-lg px-3 py-2 hover:bg-gray-50 transition-all"
        >
          <RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Running", value: runningCount, color: "text-amber-600", bg: "bg-amber-50" },
          { label: "Last Success", value: successCount, color: "text-green-600", bg: "bg-green-50" },
          { label: "Errors", value: errorCount, color: "text-red-600", bg: "bg-red-50" },
        ].map(s => (
          <div key={s.label} className={`${s.bg} rounded-xl p-4 border border-white/60`}>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{s.label}</p>
            <p className={`text-3xl font-black mt-1 ${s.color}`}>{s.value}</p>
          </div>
        ))}
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-16 text-gray-400">
          <Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading jobs…
        </div>
      )}

      {isError && (
        <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl p-4 text-sm">
          Failed to load jobs. Make sure you are authenticated.
        </div>
      )}

      {categories.map(cat => (
        <div key={cat}>
          <h2 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-3">{cat}</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {jobs
              .filter(j => j.category === cat)
              .map(job => (
                <JobCard
                  key={job.id}
                  job={job}
                  running={runningIds.has(job.id)}
                  onRun={(id) => triggerMut.mutate(id)}
                />
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}
