import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchAdmin } from "@/lib/api";
import {
  KeyRound, Eye, EyeOff, Save, Trash2, RefreshCw,
  Plus, CheckCircle2, AlertTriangle, Info, Lock, Unlock,
} from "lucide-react";

type SecretRow = {
  key: string;
  value: string;
  description: string;
  masked: boolean;
  source: "db" | "env" | "unset";
  updated_at: number | null;
};

type SecretsResp = { secrets: SecretRow[] };

const sourceStyle: Record<string, string> = {
  db:    "bg-green-50 text-green-700 border-green-200",
  env:   "bg-blue-50 text-blue-600 border-blue-200",
  unset: "bg-gray-100 text-gray-400 border-gray-200",
};
const sourceLabel: Record<string, string> = {
  db:    "DB (live)",
  env:   "Env var",
  unset: "Not set",
};

function SourceBadge({ source }: { source: string }) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold border ${sourceStyle[source] ?? ""}`}>
      {sourceLabel[source] ?? source}
    </span>
  );
}

function SecretEditor({
  row,
  onSaved,
  onDelete,
}: {
  row: SecretRow;
  onSaved: () => void;
  onDelete?: () => void;
}) {
  const [value, setValue] = useState(row.source === "unset" ? "" : "");
  const [show, setShow]   = useState(false);
  const [saved, setSaved] = useState(false);

  const upsert = useMutation({
    mutationFn: (v: string) =>
      fetchAdmin(`/admin/secrets/${encodeURIComponent(row.key)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value: v, masked: row.masked }),
      }),
    onSuccess: () => {
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      onSaved();
    },
  });

  const remove = useMutation({
    mutationFn: () =>
      fetchAdmin(`/admin/secrets/${encodeURIComponent(row.key)}`, { method: "DELETE" }),
    onSuccess: onSaved,
  });

  const placeholder = row.source === "unset"
    ? "Enter value…"
    : row.masked
      ? "Enter new value to override…"
      : "Enter new value…";

  return (
    <div className="flex items-center gap-2 mt-2">
      <div className="relative flex-1">
        <input
          type={show || !row.masked ? "text" : "password"}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono pr-10 focus:outline-none focus:ring-2 focus:ring-indigo-400"
          placeholder={placeholder}
          value={value}
          onChange={e => setValue(e.target.value)}
        />
        {row.masked && (
          <button
            type="button"
            onClick={() => setShow(v => !v)}
            className="absolute right-2.5 top-2.5 text-gray-400 hover:text-gray-700"
          >
            {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        )}
      </div>
      <button
        onClick={() => upsert.mutate(value)}
        disabled={!value.trim() || upsert.isPending}
        className="flex items-center gap-1 px-3 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition disabled:opacity-50"
      >
        {saved
          ? <CheckCircle2 className="w-4 h-4" />
          : upsert.isPending
            ? <RefreshCw className="w-4 h-4 animate-spin" />
            : <Save className="w-4 h-4" />}
        {saved ? "Saved!" : "Save"}
      </button>
      {onDelete && row.source === "db" && (
        <button
          onClick={() => remove.mutate()}
          disabled={remove.isPending}
          className="p-2 text-gray-300 hover:text-red-500 rounded-lg transition"
          title="Remove DB override (env var will be used again)"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}

function SecretCard({ row, onRefresh }: { row: SecretRow; onRefresh: () => void }) {
  const [expanded, setExpanded] = useState(false);

  const borderClass =
    row.source === "unset" ? "border-l-4 border-l-amber-400" :
    row.source === "db"    ? "border-l-4 border-l-green-400" :
    "border border-gray-100";

  return (
    <div className={`bg-white rounded-xl shadow-sm ${borderClass}`}>
      <div className="px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <code className="text-sm font-mono font-semibold text-gray-900">{row.key}</code>
              <SourceBadge source={row.source} />
              <span title={row.masked ? "Masked" : "Plaintext"}>
                {row.masked
                  ? <Lock className="w-3.5 h-3.5 text-gray-300" />
                  : <Unlock className="w-3.5 h-3.5 text-gray-300" />}
              </span>
            </div>
            {row.description && (
              <p className="text-xs text-gray-500 mt-1">{row.description}</p>
            )}
            {row.source !== "unset" && row.value !== "" && (
              <p className="text-xs font-mono text-gray-400 mt-1">
                Current: <span className="text-gray-600">{row.value}</span>
                {row.updated_at && (
                  <span className="ml-2 text-gray-300">
                    · updated {new Date(row.updated_at * 1000).toLocaleDateString("en-IN", { day:"numeric", month:"short", year:"numeric" })}
                  </span>
                )}
              </p>
            )}
          </div>
          <button
            onClick={() => setExpanded(v => !v)}
            className={`text-xs px-3 py-1.5 rounded-lg border transition flex-shrink-0 ${
              row.source === "unset"
                ? "bg-amber-50 border-amber-200 text-amber-700 hover:bg-amber-100"
                : "bg-gray-50 border-gray-200 text-gray-600 hover:bg-gray-100"
            }`}
          >
            {row.source === "unset" ? "Set value" : "Edit"}
          </button>
        </div>

        {expanded && (
          <SecretEditor
            row={row}
            onSaved={() => { onRefresh(); setExpanded(false); }}
            onDelete={onRefresh}
          />
        )}
      </div>
    </div>
  );
}

function AddCustomSecret({ onAdded }: { onAdded: () => void }) {
  const [key, setKey]     = useState("");
  const [value, setValue] = useState("");
  const [desc, setDesc]   = useState("");
  const [masked, setMasked] = useState(true);
  const [open, setOpen]   = useState(false);

  const upsert = useMutation({
    mutationFn: () =>
      fetchAdmin(`/admin/secrets/${encodeURIComponent(key.trim())}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value, description: desc, masked }),
      }),
    onSuccess: () => {
      setKey(""); setValue(""); setDesc(""); setMasked(true); setOpen(false);
      onAdded();
    },
  });

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 px-4 py-2.5 text-sm border-2 border-dashed border-gray-200 rounded-xl text-gray-400 hover:border-indigo-300 hover:text-indigo-600 transition w-full"
      >
        <Plus className="w-4 h-4" />
        Add custom secret
      </button>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-indigo-200 shadow-sm p-5 space-y-3">
      <p className="font-semibold text-sm text-gray-800 flex items-center gap-2">
        <Plus className="w-4 h-4 text-indigo-500" />
        New Secret
      </p>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Key *</label>
          <input
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-400"
            placeholder="MY_API_KEY"
            value={key}
            onChange={e => setKey(e.target.value.toUpperCase().replace(/\s/g, "_"))}
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Value *</label>
          <input
            type={masked ? "password" : "text"}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-400"
            placeholder="secret-value"
            value={value}
            onChange={e => setValue(e.target.value)}
          />
        </div>
      </div>
      <div>
        <label className="block text-xs text-gray-500 mb-1">Description (optional)</label>
        <input
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
          placeholder="What is this key used for?"
          value={desc}
          onChange={e => setDesc(e.target.value)}
        />
      </div>
      <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
        <input type="checkbox" checked={masked} onChange={e => setMasked(e.target.checked)} className="rounded" />
        Mask value in UI (recommended for API keys)
      </label>
      <div className="flex gap-2 justify-end">
        <button onClick={() => setOpen(false)} className="px-3 py-1.5 text-sm text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition">
          Cancel
        </button>
        <button
          onClick={() => upsert.mutate()}
          disabled={!key.trim() || !value.trim() || upsert.isPending}
          className="px-4 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition disabled:opacity-50"
        >
          {upsert.isPending ? "Saving…" : "Save Secret"}
        </button>
      </div>
    </div>
  );
}

export default function SecretsPage() {
  const qc = useQueryClient();

  const { data, isLoading, isError, refetch, isFetching } = useQuery<SecretsResp>({
    queryKey: ["secrets"],
    queryFn: () => fetchAdmin<SecretsResp>("/admin/secrets"),
    refetchOnWindowFocus: false,
  });

  const secrets = data?.secrets ?? [];
  const unset  = secrets.filter(s => s.source === "unset").length;
  const db     = secrets.filter(s => s.source === "db").length;
  const env    = secrets.filter(s => s.source === "env").length;

  function refresh() {
    qc.invalidateQueries({ queryKey: ["secrets"] });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <KeyRound className="w-6 h-6 text-indigo-600" />
            Secrets & Config
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Manage API keys and settings here — no environment variables needed.
            DB values take effect immediately without a server restart.
          </p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition disabled:opacity-60"
        >
          <RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {unset > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-amber-800">
              {unset} secret{unset !== 1 ? "s" : ""} not configured
            </p>
            <p className="text-sm text-amber-700 mt-0.5">
              Click <strong>Set value</strong> on the items marked "Not set" below to configure them.
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Set in DB",   value: db,    color: "text-green-700", bg: "bg-green-50",  icon: CheckCircle2 },
          { label: "Env var",     value: env,   color: "text-blue-700",  bg: "bg-blue-50",   icon: Info },
          { label: "Not set",     value: unset, color: "text-amber-700", bg: "bg-amber-50",  icon: AlertTriangle },
        ].map(({ label, value, color, bg, icon: Icon }) => (
          <div key={label} className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 flex items-center gap-3">
            <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${bg}`}>
              <Icon className={`w-4 h-4 ${color}`} />
            </div>
            <div>
              <p className="text-xs text-gray-500">{label}</p>
              <p className={`text-xl font-bold ${color}`}>{value}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 flex items-start gap-3">
        <Info className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
        <p className="text-xs text-blue-700">
          <strong>Priority:</strong> DB (green) overrides Env var (blue). Deleting a DB value reverts to the env var.
          Environment variable values are read-only from here — set via your hosting config if needed.
        </p>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {[1,2,3,4].map(i => <div key={i} className="bg-gray-100 rounded-xl h-20 animate-pulse" />)}
        </div>
      )}

      {isError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
          Failed to load secrets.
        </div>
      )}

      {!isLoading && (
        <div className="space-y-3">
          {secrets.map(row => (
            <SecretCard key={row.key} row={row} onRefresh={refresh} />
          ))}
          <AddCustomSecret onAdded={refresh} />
        </div>
      )}
    </div>
  );
}
