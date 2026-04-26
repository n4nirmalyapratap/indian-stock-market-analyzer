import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, PillTabs, Card, Loading, EmptyState } from "../_shared";
import { FileText, ExternalLink } from "lucide-react";

type Category = "all" | "Result" | "Board Meeting" | "AGM/EGM" | "Dividend" | "Company Update";

interface Filing {
  id: string;
  symbol: string;
  company: string;
  category: string;
  purpose: string;
  subject: string;
  date: string;
  documentUrl: string;
}

interface FilingsResponse {
  available: boolean;
  source?: string;
  message?: string;
  items: Filing[];
}

const CAT_OPTIONS: { value: Category; label: string }[] = [
  { value: "all", label: "All" },
  { value: "Result", label: "Result" },
  { value: "Board Meeting", label: "Board Meeting" },
  { value: "AGM/EGM", label: "AGM / EGM" },
  { value: "Dividend", label: "Dividend" },
  { value: "Company Update", label: "Company Update" },
];

function fmtDate(s: string) {
  if (!s) return "—";
  try { return new Date(s).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }); }
  catch { return s; }
}

export default function CompanyFilings() {
  const [cat, setCat] = useState<Category>("all");
  const [search, setSearch] = useState("");

  const { data, isLoading } = useQuery<FilingsResponse>({
    queryKey: ["insights/company-filings"],
    queryFn: () => fetchApi(`/insights/company-filings?category=-1&page=1`),
    staleTime: 5 * 60_000,
  });

  const items: Filing[] = data?.items || [];

  const filtered = useMemo(() => {
    let r = items;
    if (cat !== "all") {
      const target = cat.toLowerCase();
      r = r.filter(it => (it.category || "").toLowerCase().includes(target.split("/")[0]));
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      r = r.filter(it =>
        (it.company || "").toLowerCase().includes(q) ||
        (it.symbol || "").toLowerCase().includes(q) ||
        (it.purpose || "").toLowerCase().includes(q)
      );
    }
    return r;
  }, [items, cat, search]);

  return (
    <div>
      <PageHeader
        title="Company Filings"
        info="Live BSE corporate disclosures (results, dividends, AGMs, board meetings)"
        right={
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search company / symbol / purpose"
            className="text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 w-64 outline-none focus:border-indigo-400 dark:focus:border-indigo-500"
          />
        }
      />

      <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
        <PillTabs value={cat} onChange={setCat} options={CAT_OPTIONS}/>
        {data?.source && (
          <span className="text-[11px] text-gray-500 dark:text-gray-400">
            Source: <span className="font-semibold">{data.source}</span> · {filtered.length} of {items.length}
          </span>
        )}
      </div>

      {isLoading && <Loading />}
      {!isLoading && data?.available === false && (
        <EmptyState title="Feed unavailable" message={data.message || "BSE feed temporarily unavailable."}
          icon={<FileText className="w-10 h-10"/>}/>
      )}
      {!isLoading && data?.available !== false && filtered.length === 0 && (
        <EmptyState title="No filings" message="No corporate filings match the selected filter."
          icon={<FileText className="w-10 h-10"/>}/>
      )}

      {filtered.length > 0 && (
        <Card className="mt-1 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/40">
              <tr>
                <th className="px-4 py-3 text-left">Company</th>
                <th className="px-4 py-3 text-left">Code</th>
                <th className="px-4 py-3 text-left">Category</th>
                <th className="px-4 py-3 text-left">Purpose</th>
                <th className="px-4 py-3 text-left">Date</th>
                <th className="px-4 py-3 text-right">Doc</th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, 200).map((e) => (
                <tr key={e.id} className="border-t border-gray-100 dark:border-white/[0.05]">
                  <td className="px-4 py-2.5 font-medium text-gray-900 dark:text-white">{e.company || "—"}</td>
                  <td className="px-4 py-2.5 text-gray-500 dark:text-gray-400">{e.symbol || "—"}</td>
                  <td className="px-4 py-2.5">
                    <span className="text-xs px-2 py-1 rounded-md bg-indigo-50 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 whitespace-nowrap">
                      {e.category || "Other"}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-gray-600 dark:text-gray-300 max-w-md truncate" title={e.purpose}>{e.purpose || "—"}</td>
                  <td className="px-4 py-2.5 text-gray-500 dark:text-gray-400 text-xs whitespace-nowrap">{fmtDate(e.date)}</td>
                  <td className="px-4 py-2.5 text-right">
                    {e.documentUrl ? (
                      <a href={e.documentUrl} target="_blank" rel="noreferrer"
                         className="inline-flex items-center gap-1 text-xs text-indigo-600 dark:text-indigo-400 hover:underline">
                        PDF <ExternalLink className="w-3 h-3"/>
                      </a>
                    ) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
