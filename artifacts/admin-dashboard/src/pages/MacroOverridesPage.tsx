import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchAdmin } from "@/lib/api";
import {
  Save, Trash2, RefreshCw, CheckCircle2, AlertTriangle, Info,
} from "lucide-react";

// Manual override panel for the macro tiles (RBI Repo / CPI / IIP / WPI /
// GDP / India 10Y). Lets admins punch in fresh values immediately after a
// release when upstream providers (FRED, OECD) haven't caught up yet.
//
// Backend storage: macro_overrides table in PG. Manual values take the
// highest priority in the macro_service source chain
// (Manual → TradingEconomics → DBnomics → RBI direct → FRED → World Bank).

type OverrideRow = {
  indicator:     string;
  value:         number;
  as_of:         string;
  note:          string;
  set_by:        string;
  updated_at_ms: number;
};

type OverridesResp = { overrides: OverrideRow[] };

// All indicators the backend accepts. Must match _ALLOWED_MACRO_INDICATORS
// in app/routes/admin.py.
const INDICATORS = [
  { key: "repo",    label: "RBI Repo",     unit: "%",  hint: "e.g. 5.50 — set after each MPC meeting" },
  { key: "cpi",     label: "CPI YoY",      unit: "%",  hint: "e.g. 4.87 — set when MOSPI publishes" },
  { key: "iip",     label: "IIP YoY",      unit: "%",  hint: "e.g. 5.20 — Industrial production growth" },
  { key: "wpi",     label: "WPI YoY",      unit: "%",  hint: "e.g. 2.10 — Wholesale Price Index growth" },
  { key: "gdp",     label: "GDP YoY",      unit: "%",  hint: "e.g. 7.40 — Quarterly real GDP" },
  { key: "yield10", label: "India 10Y",    unit: "%",  hint: "e.g. 6.85 — benchmark sovereign yield" },
] as const;


function fmtDate(ms: number): string {
  if (!ms) return "—";
  return new Date(ms).toLocaleString();
}


function OverrideRowEditor({
  spec,
  existing,
  onChanged,
}: {
  spec: (typeof INDICATORS)[number];
  existing: OverrideRow | undefined;
  onChanged: () => void;
}) {
  const qc = useQueryClient();
  const [value, setValue] = useState<string>(existing ? String(existing.value) : "");
  const [asOf,  setAsOf]  = useState<string>(existing?.as_of  ?? new Date().toISOString().slice(0, 10));
  const [note,  setNote]  = useState<string>(existing?.note   ?? "");
  const [saved, setSaved] = useState(false);

  const save = useMutation({
    mutationFn: () => fetchAdmin(`/admin/macro/overrides/${spec.key}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        value: Number(value),
        asOf,
        note,
      }),
    }),
    onSuccess: () => {
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      onChanged();
      // Also invalidate the user-app macro queries so the dashboard tile
      // refreshes immediately on next mount.
      qc.invalidateQueries({ queryKey: ["admin-macro-overrides"] });
    },
  });

  const remove = useMutation({
    mutationFn: () => fetchAdmin(`/admin/macro/overrides/${spec.key}`, {
      method: "DELETE",
    }),
    onSuccess: onChanged,
  });

  const numericValid = value !== "" && !isNaN(Number(value));
  const dateValid    = /^\d{4}-\d{2}-\d{2}$/.test(asOf);

  return (
    <div className="rounded-lg border border-gray-100 p-4 bg-white">
      <div className="flex items-baseline justify-between mb-3">
        <div>
          <h3 className="font-semibold text-gray-900">{spec.label}</h3>
          <p className="text-xs text-gray-400">{spec.hint}</p>
        </div>
        {existing && (
          <span className="text-xs text-emerald-600 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full font-semibold">
            Active override
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mb-3">
        <label className="text-xs">
          <span className="text-gray-500 font-medium">Value ({spec.unit})</span>
          <input
            type="number" step="0.01"
            value={value} onChange={e => setValue(e.target.value)}
            className="mt-1 w-full px-2.5 py-1.5 border border-gray-200 rounded text-sm focus:outline-none focus:border-indigo-500"
            placeholder="e.g. 5.50"
          />
        </label>
        <label className="text-xs">
          <span className="text-gray-500 font-medium">As of</span>
          <input
            type="date"
            value={asOf} onChange={e => setAsOf(e.target.value)}
            className="mt-1 w-full px-2.5 py-1.5 border border-gray-200 rounded text-sm focus:outline-none focus:border-indigo-500"
          />
        </label>
        <label className="text-xs">
          <span className="text-gray-500 font-medium">Note (optional)</span>
          <input
            type="text" maxLength={200}
            value={note} onChange={e => setNote(e.target.value)}
            className="mt-1 w-full px-2.5 py-1.5 border border-gray-200 rounded text-sm focus:outline-none focus:border-indigo-500"
            placeholder="MPC meeting Apr-3"
          />
        </label>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={() => save.mutate()}
          disabled={!numericValid || !dateValid || save.isPending}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
        >
          {save.isPending ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
          {existing ? "Update" : "Save"}
        </button>

        {existing && (
          <button
            onClick={() => { if (confirm(`Clear the override for ${spec.label}?`)) remove.mutate(); }}
            disabled={remove.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-red-200 text-red-600 rounded hover:bg-red-50"
          >
            <Trash2 className="w-3 h-3" />
            Clear
          </button>
        )}

        {saved && (
          <span className="flex items-center gap-1 text-xs text-emerald-600">
            <CheckCircle2 className="w-3 h-3" /> Saved · tile will refresh on next dashboard load
          </span>
        )}

        {save.error != null && (
          <span className="text-xs text-red-500">{(save.error as Error).message}</span>
        )}

        {existing && (
          <span className="ml-auto text-[10px] text-gray-400">
            Last set by <span className="font-medium">{existing.set_by || "—"}</span> · {fmtDate(existing.updated_at_ms)}
          </span>
        )}
      </div>
    </div>
  );
}


export default function MacroOverridesPage() {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["admin-macro-overrides"],
    queryFn:  () => fetchAdmin<OverridesResp>("/admin/macro/overrides"),
  });

  const overrides = data?.overrides ?? [];
  const byIndicator = new Map<string, OverrideRow>();
  for (const o of overrides) byIndicator.set(o.indicator, o);

  return (
    <div className="max-w-4xl space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Macro Indicator Overrides</h1>
          <p className="text-sm text-gray-500">
            Punch in fresh values for the dashboard's Macro Pulse tiles.
            Manual values take priority over FRED / Trading Economics / RBI direct.
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium border border-gray-200 rounded hover:bg-gray-50"
        >
          <RefreshCw className="w-3 h-3" /> Refresh
        </button>
      </div>

      <div className="rounded-lg border border-amber-200 bg-amber-50/60 px-4 py-3 text-xs text-amber-900 flex gap-2">
        <Info className="w-4 h-4 flex-shrink-0 mt-0.5" />
        <div>
          <p className="font-semibold mb-0.5">Source priority chain (all free)</p>
          <p>
            <span className="font-mono">Manual override</span> →
            <span className="font-mono"> IMF API</span> →
            <span className="font-mono"> RBI direct</span> →
            <span className="font-mono"> DBnomics</span> →
            <span className="font-mono"> FRED</span> →
            <span className="font-mono"> World Bank</span>.
            The first source that returns a valid value wins. Clear an
            override to fall back to the next available source. Every
            source in the chain is free and requires no paid subscription.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <RefreshCw className="w-4 h-4 animate-spin" /> Loading overrides…
        </div>
      ) : (
        <div className="space-y-3">
          {INDICATORS.map(spec => (
            <OverrideRowEditor
              key={spec.key}
              spec={spec}
              existing={byIndicator.get(spec.key)}
              onChanged={() => refetch()}
            />
          ))}
        </div>
      )}

      {!isLoading && overrides.length === 0 && (
        <p className="text-xs text-gray-400 flex items-center gap-1.5">
          <AlertTriangle className="w-3 h-3 text-amber-500" />
          No overrides set — every tile is pulling from the live source chain.
        </p>
      )}
    </div>
  );
}
