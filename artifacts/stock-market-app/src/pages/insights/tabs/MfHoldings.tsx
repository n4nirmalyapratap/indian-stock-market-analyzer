import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, Card, Loading, EmptyState, MenuDropdown, ErrorState } from "../_shared";
import { PieChart } from "lucide-react";

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

export default function MfHoldings() {
  const [amc, setAmc] = useState("");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");

  const params = new URLSearchParams();
  if (amc) params.set("amc", amc);
  if (category) params.set("category", category);
  if (search) params.set("search", search);
  params.set("limit", "300");

  const { data, isLoading, error } = useQuery<MfResponse>({
    queryKey: ["insights/mf-holdings", amc, category, search],
    queryFn: () => fetchApi(`/insights/mf-holdings?${params}`),
    staleTime: 30 * 60_000,
  });

  const amcOptions = (data?.amcs || []).map(a => ({ value: a, label: a }));
  const catOptions = (data?.categories || []).map(c => ({ value: c, label: c }));

  return (
    <div>
      <PageHeader
        title="Mutual Fund — Schemes & NAVs"
        info="Live AMFI scheme list with daily Net Asset Values"
        right={
          data?.available && (
            <span className="text-[11px] text-gray-500 dark:text-gray-400">
              <span className="font-semibold text-gray-900 dark:text-white">{data.matched?.toLocaleString()}</span> of <span className="font-semibold text-gray-900 dark:text-white">{data.totalSchemes?.toLocaleString()}</span> schemes
            </span>
          )
        }
      />

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <MenuDropdown label="AMC" value={amc} onChange={setAmc} options={amcOptions}
          placeholder="All AMCs" minButtonWidth={180} maxButtonWidth={260} />
        <MenuDropdown label="Category" value={category} onChange={setCategory} options={catOptions}
          placeholder="All categories" minButtonWidth={180} maxButtonWidth={260} />
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search scheme name…"
          className="text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white rounded-lg px-3 py-2 w-72 outline-none focus:border-indigo-600 dark:border-indigo-500 placeholder:text-gray-500 dark:text-gray-400" />
      </div>

      {isLoading && <Loading label="Fetching AMFI NAV feed…" />}
      {error && !isLoading && <ErrorState message={(error as Error).message} />}
      {!error && !isLoading && data?.available === false && (
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
            <thead className="text-xs uppercase text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-900/40">
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
                <tr key={s.schemeCode} className="border-t border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/30 transition">
                  <td className="px-4 py-2.5 font-medium text-gray-900 dark:text-white max-w-md truncate" title={s.schemeName}>{s.schemeName}</td>
                  <td className="px-4 py-2.5 text-gray-500 dark:text-gray-400 text-xs max-w-[200px] truncate" title={s.amc}>{s.amc}</td>
                  <td className="px-4 py-2.5 text-gray-500 dark:text-gray-400 text-xs max-w-[180px] truncate" title={s.category}>{s.category}</td>
                  <td className="px-4 py-2.5 text-right font-semibold text-gray-900 dark:text-white tabular-nums">
                    {s.nav != null ? s.nav.toFixed(4) : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-gray-500 dark:text-gray-400 text-xs whitespace-nowrap">{s.date}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
