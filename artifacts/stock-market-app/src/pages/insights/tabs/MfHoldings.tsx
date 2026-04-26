import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, Card, Loading, EmptyState } from "../_shared";
import { PieChart, ChevronDown, Check } from "lucide-react";

interface Scheme {
  schemeCode: string;
  isin: string;
  schemeName: string;
  nav: number | null;
  date: string;
  amc: string;
  category: string;
}

interface MfResponse {
  available: boolean;
  source?: string;
  message?: string;
  totalSchemes?: number;
  matched?: number;
  items: Scheme[];
  amcs?: string[];
  categories?: string[];
}

function ComboBox({ label, value, options, onChange, placeholder = "All" }:
  { label: string; value: string; options: string[]; onChange: (v: string) => void; placeholder?: string }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const filtered = useMemo(
    () => (q ? options.filter(o => o.toLowerCase().includes(q.toLowerCase())) : options).slice(0, 200),
    [options, q],
  );
  return (
    <div className="relative">
      <button type="button" onClick={() => setOpen(o => !o)} onBlur={() => setTimeout(() => setOpen(false), 150)}
        className="inline-flex items-center gap-2 text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-700/80 transition shadow-sm min-w-[180px]">
        <span className="text-gray-500 dark:text-gray-400">{label}</span>
        <span className="font-semibold text-indigo-600 dark:text-indigo-400 truncate max-w-[180px]">{value || placeholder}</span>
        <ChevronDown className={`w-3.5 h-3.5 text-indigo-500 ml-auto transition-transform ${open ? "rotate-180" : ""}`}/>
      </button>
      {open && (
        <div className="absolute z-30 left-0 mt-1.5 min-w-[260px] max-h-[360px] overflow-hidden rounded-xl border border-gray-200 dark:border-white/[0.08] bg-white dark:bg-gray-900 shadow-2xl">
          <input autoFocus value={q} onChange={e => setQ(e.target.value)}
            placeholder="Search…" className="w-full text-sm px-3 py-2 border-b border-gray-100 dark:border-white/[0.06] bg-transparent outline-none" />
          <div className="max-h-[300px] overflow-y-auto py-1">
            <button onMouseDown={(e) => { e.preventDefault(); onChange(""); setOpen(false); }}
              className={`w-full text-left text-sm px-3.5 py-2 flex items-center justify-between
                ${value === "" ? "bg-indigo-50 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 font-semibold" : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"}`}>
              {placeholder}
              {value === "" && <Check className="w-4 h-4 text-indigo-500"/>}
            </button>
            {filtered.map(o => (
              <button key={o} onMouseDown={(e) => { e.preventDefault(); onChange(o); setOpen(false); }}
                className={`w-full text-left text-sm px-3.5 py-2 flex items-center justify-between
                  ${o === value ? "bg-indigo-50 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 font-semibold" : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"}`}>
                <span className="truncate">{o}</span>
                {o === value && <Check className="w-4 h-4 text-indigo-500 flex-shrink-0"/>}
              </button>
            ))}
            {filtered.length === 0 && <div className="px-3 py-3 text-xs text-gray-500 dark:text-gray-400">No matches</div>}
          </div>
        </div>
      )}
    </div>
  );
}

export default function MfHoldings() {
  const [amc, setAmc] = useState("");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");

  const params = new URLSearchParams();
  if (amc) params.set("amc", amc);
  if (category) params.set("category", category);
  if (search) params.set("search", search);
  params.set("limit", "300");

  const { data, isLoading } = useQuery<MfResponse>({
    queryKey: ["insights/mf-holdings", amc, category, search],
    queryFn: () => fetchApi(`/insights/mf-holdings?${params}`),
    staleTime: 30 * 60_000,
  });

  return (
    <div>
      <PageHeader
        title="Mutual Fund — Schemes & NAVs"
        info="Live AMFI scheme list with daily Net Asset Values (all AMCs, all categories)"
        right={
          data?.available && (
            <span className="text-[11px] text-gray-500 dark:text-gray-400">
              Source: <span className="font-semibold">{data.source}</span> · {data.matched?.toLocaleString()} of {data.totalSchemes?.toLocaleString()} schemes
            </span>
          )
        }
      />

      <div className="flex flex-wrap items-center gap-2.5 mb-4">
        <ComboBox label="AMC :" value={amc} onChange={setAmc} options={data?.amcs || []} placeholder="All AMCs" />
        <ComboBox label="Category :" value={category} onChange={setCategory} options={data?.categories || []} placeholder="All categories"/>
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search scheme name…"
          className="text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 w-72 outline-none focus:border-indigo-400 dark:focus:border-indigo-500" />
      </div>

      {isLoading && <Loading label="Fetching AMFI NAV feed…" />}
      {!isLoading && data?.available === false && (
        <EmptyState title="Feed unavailable" message={data.message || "AMFI NAV feed temporarily unavailable."}
          icon={<PieChart className="w-10 h-10"/>}/>
      )}
      {!isLoading && data?.available && (data.items || []).length === 0 && (
        <EmptyState title="No schemes" message="No schemes match the selected filters."
          icon={<PieChart className="w-10 h-10"/>}/>
      )}

      {data?.items && data.items.length > 0 && (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/40">
              <tr>
                <th className="px-4 py-3 text-left">Scheme</th>
                <th className="px-4 py-3 text-left">AMC</th>
                <th className="px-4 py-3 text-left">Category</th>
                <th className="px-4 py-3 text-right">NAV (₹)</th>
                <th className="px-4 py-3 text-left">As of</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map(s => (
                <tr key={s.schemeCode} className="border-t border-gray-100 dark:border-white/[0.05]">
                  <td className="px-4 py-2.5 font-medium text-gray-900 dark:text-white max-w-md truncate" title={s.schemeName}>{s.schemeName}</td>
                  <td className="px-4 py-2.5 text-gray-600 dark:text-gray-300 text-xs">{s.amc}</td>
                  <td className="px-4 py-2.5 text-gray-500 dark:text-gray-400 text-xs">{s.category}</td>
                  <td className="px-4 py-2.5 text-right font-semibold text-gray-900 dark:text-white tabular-nums">
                    {s.nav != null ? s.nav.toFixed(4) : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-gray-500 dark:text-gray-400 text-xs">{s.date}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
