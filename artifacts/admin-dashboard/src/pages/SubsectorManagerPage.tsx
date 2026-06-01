import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchAdmin } from "@/lib/api";
import {
  Layers, Plus, Trash2, RefreshCw, ChevronDown, ChevronRight,
  CheckCircle2, AlertTriangle, Search, X,
} from "lucide-react";

type TaxonomyEntry = {
  subIndustry: string;
  industry: string;
  sector: string;
  curatedCount: number;
  curatedSymbols: string[];
};

type OverrideRow = {
  id: string;
  symbol: string;
  sub_industry: string;
  industry: string;
  sector: string;
  note: string;
  set_by: string;
  created_at_ms: number;
  updated_at_ms: number;
  stock_name: string | null;
  market_cap: number | null;
  cap_category: string | null;
  classified_ok: boolean | null;
};

type SubsectorsResp = {
  taxonomy: TaxonomyEntry[];
  overrides: OverrideRow[];
  totalSubIndustries: number;
  totalOverrides: number;
};

function fmtCap(v: number | null): string {
  if (!v || v <= 0) return "—";
  const cr = v / 1e7;
  if (cr >= 1e5) return `₹${(cr / 1e5).toFixed(2)}L Cr`;
  if (cr >= 1e3) return `₹${(cr / 1e3).toFixed(1)}K Cr`;
  return `₹${cr.toFixed(0)} Cr`;
}

function fmtDate(ms: number): string {
  if (!ms) return "—";
  return new Date(ms).toLocaleDateString("en-IN");
}

const J = { "Content-Type": "application/json" };

export default function SubsectorManagerPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [addSub, setAddSub] = useState("");
  const [addSymbol, setAddSymbol] = useState("");
  const [addIndustry, setAddIndustry] = useState("");
  const [addSector, setAddSector] = useState("");
  const [addNote, setAddNote] = useState("");
  const [toast, setToast] = useState<{ ok: boolean; msg: string } | null>(null);

  function showToast(ok: boolean, msg: string) {
    setToast({ ok, msg });
    setTimeout(() => setToast(null), 4000);
  }

  const { data, isLoading, isError } = useQuery<SubsectorsResp>({
    queryKey: ["admin-subsectors"],
    queryFn: () => fetchAdmin<SubsectorsResp>("/admin/subsectors"),
  });

  const reclassify = useMutation({
    mutationFn: () => fetchAdmin<{ ok: boolean; classified: number }>("/admin/subsectors/reclassify", { method: "POST" }),
    onSuccess: (r) => {
      showToast(true, `Reclassification queued: ${r.classified ?? 0} symbols targeted.`);
      qc.invalidateQueries({ queryKey: ["admin-subsectors"] });
    },
    onError: (e: any) => showToast(false, e.message || "Reclassify failed"),
  });

  const addOverride = useMutation({
    mutationFn: (body: object) => fetchAdmin<{ ok: boolean }>("/admin/subsectors/overrides", {
      method: "POST",
      headers: J,
      body: JSON.stringify(body),
    }),
    onSuccess: () => {
      showToast(true, `${addSymbol.toUpperCase()} added to "${addSub}".`);
      setAddSymbol(""); setAddSub(""); setAddIndustry(""); setAddSector(""); setAddNote(""); setAddOpen(false);
      qc.invalidateQueries({ queryKey: ["admin-subsectors"] });
    },
    onError: (e: any) => showToast(false, e.message || "Failed to add override"),
  });

  const removeOverride = useMutation({
    mutationFn: (id: string) => fetchAdmin<{ ok: boolean }>(`/admin/subsectors/overrides/${id}`, { method: "DELETE" }),
    onSuccess: (_, id) => {
      showToast(true, "Override removed.");
      qc.invalidateQueries({ queryKey: ["admin-subsectors"] });
    },
    onError: (e: any) => showToast(false, e.message || "Failed to remove"),
  });

  const overridesBySubIndustry = useMemo(() => {
    const map: Record<string, OverrideRow[]> = {};
    for (const o of data?.overrides ?? []) {
      (map[o.sub_industry] ??= []).push(o);
    }
    return map;
  }, [data]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    if (!q) return data?.taxonomy ?? [];
    return (data?.taxonomy ?? []).filter(
      t =>
        t.subIndustry.toLowerCase().includes(q) ||
        t.industry.toLowerCase().includes(q) ||
        t.sector.toLowerCase().includes(q) ||
        t.curatedSymbols.some(s => s.toLowerCase().includes(q))
    );
  }, [data, search]);

  const subIndustryNames = useMemo(
    () => (data?.taxonomy ?? []).map(t => t.subIndustry).sort(),
    [data]
  );

  function handleAdd() {
    const sym = addSymbol.trim().toUpperCase();
    const sub = addSub.trim();
    if (!sym || !sub) { showToast(false, "Symbol and Sub-Industry are required."); return; }
    addOverride.mutate({ symbol: sym, subIndustry: sub, industry: addIndustry, sector: addSector, note: addNote });
  }

  return (
    <div className="space-y-6">
      {/* Toast */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 flex items-center gap-2 px-4 py-3 rounded-xl shadow-lg text-sm font-medium text-white transition-all
          ${toast.ok ? "bg-green-600" : "bg-red-600"}`}>
          {toast.ok ? <CheckCircle2 className="w-4 h-4 flex-shrink-0" /> : <AlertTriangle className="w-4 h-4 flex-shrink-0" />}
          {toast.msg}
        </div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-50 flex items-center justify-center flex-shrink-0">
            <Layers className="w-5 h-5 text-indigo-600" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">Sub-Industry Manager</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              {data ? `${data.totalSubIndustries} curated sub-industries · ${data.totalOverrides} admin override${data.totalOverrides !== 1 ? "s" : ""}` : "Curated taxonomy + admin overrides for the rotation engine."}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={() => reclassify.mutate()}
            disabled={reclassify.isPending}
            title="Re-run Yahoo classifier for all taxonomy symbols"
            className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${reclassify.isPending ? "animate-spin" : ""}`} />
            Reclassify
          </button>
          <button
            onClick={() => setAddOpen(true)}
            className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition"
          >
            <Plus className="w-4 h-4" />
            Add Stock
          </button>
        </div>
      </div>

      {/* Add Override Modal */}
      {addOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-gray-900">Add Stock to Sub-Industry</h2>
              <button onClick={() => setAddOpen(false)} className="text-gray-400 hover:text-gray-600 transition">
                <X className="w-5 h-5" />
              </button>
            </div>
            <p className="text-xs text-gray-500">
              Use this when a data provider misses a stock. The stock will be fetched by the classifier
              and appear in the rotation grid after its market-cap is known.
            </p>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">NSE Symbol *</label>
                <input
                  value={addSymbol}
                  onChange={e => setAddSymbol(e.target.value.toUpperCase())}
                  placeholder="e.g. HDFCBANK"
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-400 font-mono"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">Sub-Industry *</label>
                <input
                  value={addSub}
                  onChange={e => setAddSub(e.target.value)}
                  list="sub-industry-list"
                  placeholder="e.g. Banks - Private Large Cap"
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-400"
                />
                <datalist id="sub-industry-list">
                  {subIndustryNames.map(n => <option key={n} value={n} />)}
                </datalist>
                <p className="text-[10px] text-gray-400 mt-1">Type a new name to create a new sub-industry group.</p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">Industry (optional)</label>
                  <input
                    value={addIndustry}
                    onChange={e => setAddIndustry(e.target.value)}
                    placeholder="e.g. Banks"
                    className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">Sector (optional)</label>
                  <input
                    value={addSector}
                    onChange={e => setAddSector(e.target.value)}
                    placeholder="e.g. Financial Services"
                    className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">Note (optional)</label>
                <input
                  value={addNote}
                  onChange={e => setAddNote(e.target.value)}
                  placeholder="Why was this added manually?"
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-400"
                />
              </div>
            </div>
            <div className="flex gap-2 pt-1">
              <button
                onClick={() => setAddOpen(false)}
                className="flex-1 px-4 py-2 text-sm font-medium text-gray-600 bg-gray-50 border border-gray-200 rounded-lg hover:bg-gray-100 transition"
              >
                Cancel
              </button>
              <button
                onClick={handleAdd}
                disabled={addOverride.isPending}
                className="flex-1 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition disabled:opacity-50"
              >
                {addOverride.isPending ? "Adding…" : "Add Stock"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search sub-industries, sectors, or symbols…"
          className="w-full pl-9 pr-4 py-2.5 text-sm border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white"
        />
        {search && (
          <button onClick={() => setSearch("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* States */}
      {isLoading && (
        <div className="flex items-center justify-center py-16 text-sm text-gray-400">
          <RefreshCw className="w-4 h-4 animate-spin mr-2" /> Loading taxonomy…
        </div>
      )}
      {isError && (
        <div className="rounded-xl border border-red-100 bg-red-50 p-4 text-sm text-red-600">
          Failed to load sub-industry data. Check backend connection.
        </div>
      )}

      {/* Taxonomy Table */}
      {!isLoading && !isError && data && (
        <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden">
          {/* Header */}
          <div className="grid grid-cols-12 gap-3 px-5 py-3 text-[10px] font-semibold uppercase tracking-wide text-gray-400 border-b border-gray-100">
            <div className="col-span-5">Sub-Industry</div>
            <div className="col-span-2">Sector</div>
            <div className="col-span-2 text-right">Curated</div>
            <div className="col-span-2 text-right">Overrides</div>
            <div className="col-span-1" />
          </div>

          {filtered.length === 0 && (
            <div className="px-5 py-10 text-center text-sm text-gray-400">
              No sub-industries match your search.
            </div>
          )}

          {filtered.map(t => {
            const ov = overridesBySubIndustry[t.subIndustry] ?? [];
            const isOpen = expanded === t.subIndustry;
            return (
              <div key={t.subIndustry} className="border-b border-gray-50 last:border-b-0">
                {/* Row */}
                <button
                  onClick={() => setExpanded(isOpen ? null : t.subIndustry)}
                  className="w-full grid grid-cols-12 gap-3 px-5 py-3 items-center text-left hover:bg-gray-50 transition"
                >
                  <div className="col-span-5 flex items-center gap-2 min-w-0">
                    {isOpen
                      ? <ChevronDown className="w-3.5 h-3.5 flex-shrink-0 text-gray-400" />
                      : <ChevronRight className="w-3.5 h-3.5 flex-shrink-0 text-gray-400" />}
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-gray-800 truncate">{t.subIndustry}</p>
                      <p className="text-[10px] text-gray-400 truncate">{t.industry}</p>
                    </div>
                  </div>
                  <div className="col-span-2 text-xs text-gray-500 truncate">{t.sector}</div>
                  <div className="col-span-2 text-right">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-50 text-indigo-700">
                      {t.curatedCount} stocks
                    </span>
                  </div>
                  <div className="col-span-2 text-right">
                    {ov.length > 0 ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 text-amber-700">
                        +{ov.length} added
                      </span>
                    ) : (
                      <span className="text-[10px] text-gray-300">—</span>
                    )}
                  </div>
                  <div className="col-span-1 flex justify-end">
                    <button
                      onClick={e => { e.stopPropagation(); setAddSub(t.subIndustry); setAddIndustry(t.industry); setAddSector(t.sector); setAddOpen(true); }}
                      title="Add stock to this sub-industry"
                      className="p-1 rounded text-gray-300 hover:text-indigo-600 hover:bg-indigo-50 transition"
                    >
                      <Plus className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </button>

                {/* Expanded: curated + overrides */}
                {isOpen && (
                  <div className="border-t border-gray-50 bg-gray-50/50 px-6 pb-4 pt-3 space-y-4">
                    {/* Curated symbols */}
                    <div>
                      <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400 mb-2">Curated Symbols ({t.curatedCount})</p>
                      <div className="flex flex-wrap gap-1.5">
                        {t.curatedSymbols.map(s => (
                          <span key={s} className="px-2 py-0.5 rounded text-xs font-mono font-medium bg-white border border-gray-200 text-gray-700">{s}</span>
                        ))}
                      </div>
                    </div>

                    {/* Admin overrides */}
                    {ov.length > 0 && (
                      <div>
                        <p className="text-[10px] font-semibold uppercase tracking-wide text-amber-600 mb-2">Admin Overrides ({ov.length})</p>
                        <div className="space-y-1.5">
                          {ov.map(o => (
                            <div key={o.id} className="flex items-center gap-3 bg-white rounded-lg border border-amber-100 px-3 py-2">
                              <span className="text-xs font-mono font-semibold text-gray-800 w-28 flex-shrink-0">{o.symbol}</span>
                              <span className="text-xs text-gray-500 flex-1 truncate">
                                {o.stock_name || "—"}
                                {o.market_cap ? ` · ${fmtCap(o.market_cap)}` : ""}
                                {o.classified_ok === false ? " · ⚠ Yahoo pending" : ""}
                              </span>
                              {o.note && <span className="text-[10px] text-gray-400 italic truncate max-w-[140px]">{o.note}</span>}
                              <span className="text-[10px] text-gray-300 flex-shrink-0">{fmtDate(o.created_at_ms)}</span>
                              <button
                                onClick={() => removeOverride.mutate(o.id)}
                                disabled={removeOverride.isPending}
                                title="Remove this override"
                                className="text-gray-300 hover:text-red-500 transition flex-shrink-0"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {ov.length === 0 && (
                      <div className="text-xs text-gray-400 italic">
                        No admin overrides. Click <Plus className="inline w-3 h-3" /> above to add a missing stock.
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Info box */}
      <div className="rounded-xl border border-blue-100 bg-blue-50 p-4 text-xs text-blue-700 leading-relaxed">
        <strong>How this works:</strong> The curated taxonomy gives the rotation engine its initial sub-industry groups — every symbol listed is seeded into the classifier on the next run.
        Admin overrides let you add any NSE symbol that Yahoo, BSE or NSE data providers miss.
        The symbol will appear in the drill-down immediately; it contributes to the market-cap-weighted index calculation once Yahoo fills in its market cap (tap <em>Reclassify</em> to trigger this now rather than waiting for the weekly scheduler).
      </div>
    </div>
  );
}
