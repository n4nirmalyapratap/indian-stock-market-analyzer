/**
 * MacroExtrasGrid — pinned tiles for curated "useful" Indian macro
 * indicators (Manufacturing PMI, FX reserves, unemployment, trade
 * balance, etc.) that don't have a reliable free data source.
 *
 * Data path
 * ---------
 * Every tile's value comes from the manual-override system. The grid
 * fetches `GET /api/insights/macro/extras`, which returns the catalog
 * joined with any admin-set values. Tiles without an override show
 * "—" with a friendly "no value yet" indicator and (if the current
 * user is an admin) a pencil to enter one.
 *
 * Admin editing
 * -------------
 * Admins see a pencil icon on every tile. Clicking opens a modal with
 * three inputs (value, as-of date, optional note). Saving calls
 * `PUT /api/admin/macro/overrides/{slug}` with the user's JWT in
 * `X-Admin-Token`. On success, the grid invalidates the React-Query
 * cache and re-renders with the new value immediately.
 *
 * Non-admin users see the same grid in read-only mode — no pencils,
 * no edit modal.
 */
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, AlertCircle, Pencil, X as XIcon, ExternalLink } from "lucide-react";

import { api } from "@/lib/api";
import type { MacroExtra, MacroExtrasResponse } from "@/lib/api";
import { useCustomAuth } from "@/context/CustomAuthContext";


// ── Helpers ─────────────────────────────────────────────────────────────────

function fmtValue(v: number | null, unit: string): string {
  if (v == null || isNaN(v)) return "—";
  const abs = Math.abs(v);
  // Larger magnitudes get a thousands separator; small percentages keep 2 dp.
  if (abs >= 1000) return v.toLocaleString("en-IN", { maximumFractionDigits: 0 });
  if (abs >= 100)  return v.toFixed(1);
  if (abs >= 10)   return v.toFixed(1);
  // Show 2 decimals for anything under 10; unit decoration handled separately.
  return v.toFixed(2);
}


// ── Edit modal ──────────────────────────────────────────────────────────────

function EditModal({
  extra, token, onClose,
}: {
  extra:    MacroExtra;
  token:    string;
  onClose:  () => void;
}) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState<string>(
    extra.value != null ? String(extra.value) : "",
  );
  const [asOf,  setAsOf]  = useState<string>(extra.asOf ?? new Date().toISOString().slice(0, 10));
  const [note,  setNote]  = useState<string>(extra.note ?? "");
  const [errMsg, setErrMsg] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () => api.setMacroOverride(token, extra.slug, {
      value: Number(value),
      asOf,
      note: note.trim() || undefined,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["insights/macro/extras"] });
      // Headline tiles read overrides through the orchestrator — clear
      // their queries too so values like cpi/repo refresh if the admin
      // chose to override one of those instead.
      queryClient.invalidateQueries({ queryKey: ["macro-strip"] });
      queryClient.invalidateQueries({ queryKey: ["macro-dashboard"] });
      onClose();
    },
    onError: (err: Error) => setErrMsg(err.message || "Save failed."),
  });

  // Basic validation — number required, date required.
  const valueValid = value !== "" && !isNaN(Number(value));
  const asOfValid  = !!asOf && asOf.length >= 8;
  const canSubmit  = valueValid && asOfValid && !save.isPending;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-white/[0.08] shadow-2xl w-full max-w-md overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 py-3 border-b border-gray-100 dark:border-white/[0.04] flex items-start justify-between gap-3">
          <div>
            <h3 className="font-bold text-gray-900 dark:text-white text-sm">
              Update {extra.label}
            </h3>
            <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
              {extra.description}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
            <XIcon className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-3">
          <label className="block">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Value {extra.unit && <span className="text-gray-400">({extra.unit})</span>}
            </span>
            <input
              type="number"
              step="any"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-white tabular-nums focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400 outline-none"
              placeholder={extra.unit === "%" ? "e.g. 56.7" : "e.g. 720.5"}
              autoFocus
            />
          </label>

          <label className="block">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
              As of (YYYY-MM-DD)
            </span>
            <input
              type="date"
              value={asOf}
              onChange={(e) => setAsOf(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400 outline-none"
            />
          </label>

          <label className="block">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Note <span className="text-gray-400 normal-case">(optional)</span>
            </span>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={200}
              className="mt-1 block w-full rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400 outline-none"
              placeholder="e.g. Jan release"
            />
          </label>

          <div className="text-[11px] text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/50 rounded p-2 leading-relaxed">
            <strong className="text-gray-700 dark:text-gray-300">Source:</strong> {extra.sourceHint}
          </div>

          {errMsg && (
            <div className="text-[12px] text-rose-600 dark:text-rose-400 flex items-start gap-1.5">
              <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
              <span>{errMsg}</span>
            </div>
          )}
        </div>

        <div className="px-5 py-3 border-t border-gray-100 dark:border-white/[0.04] flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded-md text-xs font-medium bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300"
          >
            Cancel
          </button>
          <button
            onClick={() => { setErrMsg(null); save.mutate(); }}
            disabled={!canSubmit}
            className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {save.isPending
              ? <><Loader2 className="w-3 h-3 animate-spin"/>Saving…</>
              : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}


// ── Tile ────────────────────────────────────────────────────────────────────

function ExtraTile({
  extra, isAdmin, onEdit,
}: {
  extra:   MacroExtra;
  isAdmin: boolean;
  onEdit:  (e: MacroExtra) => void;
}) {
  const hasValue = extra.value != null && !isNaN(extra.value);
  return (
    <div
      className={`group p-3 rounded-lg border transition relative
        ${hasValue
          ? "bg-white dark:bg-gray-800 border-gray-100 dark:border-gray-700"
          : "bg-gray-50/50 dark:bg-gray-800/30 border-dashed border-gray-200 dark:border-gray-700"}`}
      title={extra.description}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500 dark:text-gray-400 truncate">
            {extra.label}
          </p>
          <p className={`text-xl font-bold mt-1 tabular-nums ${
            hasValue ? "text-gray-900 dark:text-white" : "text-gray-300 dark:text-gray-600"
          }`}>
            {fmtValue(extra.value, extra.unit)}
            {hasValue && extra.unit && (
              <span className="text-[11px] font-medium text-gray-400 dark:text-gray-500 ml-1">
                {extra.unit}
              </span>
            )}
          </p>
        </div>
        {isAdmin && (
          <button
            onClick={() => onEdit(extra)}
            title="Edit value"
            className="opacity-0 group-hover:opacity-100 focus:opacity-100 transition p-1 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400"
          >
            <Pencil className="w-3 h-3" />
          </button>
        )}
      </div>

      <div className="mt-1 text-[10px] text-gray-400 dark:text-gray-500 flex items-center gap-1 truncate">
        {hasValue ? (
          <>
            <span>as of {extra.asOf?.slice(0, 10)}</span>
            {extra.note && <span className="truncate">· {extra.note}</span>}
          </>
        ) : (
          <span className="italic">not set yet</span>
        )}
      </div>
    </div>
  );
}


// ── Grid ────────────────────────────────────────────────────────────────────

export default function MacroExtrasGrid() {
  const { user, token } = useCustomAuth();
  const isAdmin = user?.isAdmin === true;
  const [editing, setEditing] = useState<MacroExtra | null>(null);

  const { data, isLoading, error } = useQuery<MacroExtrasResponse>({
    queryKey: ["insights/macro/extras"],
    queryFn:  api.macroExtras,
    staleTime: 60 * 60 * 1000,
    refetchOnWindowFocus: false,
  });

  if (error) {
    return (
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-white/[0.06] p-4 text-sm text-rose-500">
        <AlertCircle className="inline w-4 h-4 mr-1.5"/>
        Could not load macro extras.
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-white/[0.06] p-4 flex items-center gap-2 text-sm text-gray-500">
        <Loader2 className="w-4 h-4 animate-spin"/>
        Loading additional indicators…
      </div>
    );
  }

  const items = data?.items ?? [];
  if (items.length === 0) return null;

  // Group tiles by category, preserving catalog order within each group.
  const byCategory = new Map<string, MacroExtra[]>();
  for (const it of items) {
    const arr = byCategory.get(it.category) ?? [];
    arr.push(it);
    byCategory.set(it.category, arr);
  }

  const setCount = items.filter(i => i.value != null).length;

  return (
    <>
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-white/[0.06] overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 dark:border-white/[0.04]">
          <div className="flex items-baseline justify-between gap-3 flex-wrap">
            <div>
              <h3 className="text-sm font-bold text-gray-900 dark:text-white">
                Additional indicators
              </h3>
              <p className="text-[11px] text-gray-500 dark:text-gray-400">
                Curated macro indicators with admin-entered values. {setCount}/{items.length} populated.
                {isAdmin && " Hover a tile and click the pencil to edit."}
              </p>
            </div>
            {!isAdmin && (
              <a
                href="https://www.rbi.org.in/Scripts/PublicationsView.aspx?id=22141"
                target="_blank" rel="noreferrer"
                className="text-[10px] font-semibold text-indigo-600 dark:text-indigo-400 hover:underline flex items-center gap-1"
              >
                Source data <ExternalLink className="w-2.5 h-2.5"/>
              </a>
            )}
          </div>
        </div>

        <div className="p-3 space-y-3">
          {Array.from(byCategory.entries()).map(([cat, tiles]) => (
            <div key={cat}>
              <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 dark:text-gray-500 px-1 mb-1.5">
                {cat}
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
                {tiles.map(t => (
                  <ExtraTile
                    key={t.slug}
                    extra={t}
                    isAdmin={isAdmin}
                    onEdit={setEditing}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {editing && token && (
        <EditModal extra={editing} token={token} onClose={() => setEditing(null)} />
      )}
    </>
  );
}
