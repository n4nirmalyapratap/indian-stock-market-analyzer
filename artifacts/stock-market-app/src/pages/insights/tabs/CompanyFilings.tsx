import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, Card, Loading, EmptyState, MenuDropdown, ErrorState } from "../_shared";
import { FileText, ExternalLink } from "lucide-react";

type Category =
  | "all" | "Result" | "Board Meeting" | "AGM/EGM" | "Dividend"
  | "Bonus" | "Acquisition" | "Investor Presentation" | "Company Update";

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

const SUB_TABS: { value: Category; label: string }[] = [
  { value: "all", label: "All" },
  { value: "Result", label: "Financial Results" },
  { value: "Investor Presentation", label: "Investor Presentation" },
  { value: "Board Meeting", label: "Board Meeting" },
  { value: "AGM/EGM", label: "AGM / EGM" },
  { value: "Dividend", label: "Dividend" },
  { value: "Bonus", label: "Bonus / Split" },
  { value: "Acquisition", label: "Acquisition" },
  { value: "Company Update", label: "Company Update" },
];

function fmtRelative(s: string) {
  if (!s) return "—";
  try {
    const d = new Date(s);
    const diff = Date.now() - d.getTime();
    const min = Math.round(diff / 60000);
    if (min < 60) return `${min} min ago`;
    const hrs = Math.round(min / 60);
    if (hrs < 24) return `${hrs} hr${hrs === 1 ? "" : "s"} ago`;
    const days = Math.round(hrs / 24);
    if (days < 7) return `${days} day${days === 1 ? "" : "s"} ago`;
    return d.toLocaleDateString("en-IN", { dateStyle: "medium" });
  } catch { return s; }
}

function categoryColor(cat: string) {
  const c = (cat || "").toLowerCase();
  if (c.includes("result")) return "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300";
  if (c.includes("dividend")) return "bg-sky-500/15 text-sky-700 dark:text-sky-300";
  if (c.includes("agm") || c.includes("egm")) return "bg-purple-500/15 text-purple-700 dark:text-purple-300";
  if (c.includes("board")) return "bg-amber-500/15 text-amber-700 dark:text-amber-300";
  if (c.includes("acquisition")) return "bg-rose-500/15 text-rose-700 dark:text-rose-300";
  if (c.includes("bonus") || c.includes("split")) return "bg-pink-500/15 text-pink-700 dark:text-pink-300";
  if (c.includes("investor")) return "bg-indigo-500/15 text-indigo-700 dark:text-indigo-300";
  return "bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400";
}

export default function CompanyFilings() {
  const [cat, setCat] = useState<Category>("all");
  const [companyFilter, setCompanyFilter] = useState("");
  const [search, setSearch] = useState("");

  const { data, isLoading, error } = useQuery<FilingsResponse>({
    queryKey: ["insights/company-filings"],
    queryFn: () => fetchApi(`/insights/company-filings?category=-1&page=1`),
    staleTime: 5 * 60_000,
  });

  const items: Filing[] = data?.items || [];

  // Build the company list dynamically from the current page (real BSE companies).
  const companyOptions = useMemo(() => {
    const set = new Map<string, string>();
    for (const it of items) {
      if (!it.company) continue;
      if (!set.has(it.company)) set.set(it.company, it.company);
    }
    return Array.from(set.values()).sort().map(c => ({ value: c, label: c }));
  }, [items]);

  const filtered = useMemo(() => {
    let r = items;
    if (cat !== "all") {
      const target = cat.toLowerCase();
      r = r.filter(it => {
        const ic = (it.category || "").toLowerCase();
        const ip = (it.purpose || "").toLowerCase();
        return ic.includes(target.split("/")[0]) || ip.includes(target.split("/")[0]);
      });
    }
    if (companyFilter) {
      r = r.filter(it => it.company === companyFilter);
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
  }, [items, cat, companyFilter, search]);

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
            placeholder="Search company / symbol / purpose…"
            className="text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white rounded-lg px-3 py-2 w-64 outline-none focus:border-indigo-600 dark:border-indigo-500 placeholder:text-gray-500 dark:text-gray-400"
          />
        }
      />

      {/* Sub-tabs row + company filter */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <div className="flex items-center gap-1.5 flex-wrap flex-1">
          {SUB_TABS.map(t => {
            const active = cat === t.value;
            return (
              <button
                key={t.value}
                onClick={() => setCat(t.value)}
                className={`text-xs px-3 py-1.5 rounded-lg border transition whitespace-nowrap font-medium
                  ${active
                    ? "bg-indigo-600 dark:bg-indigo-500 text-white border-indigo-600 dark:border-indigo-500"
                    : "bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-white"}`}
              >
                {t.label}
              </button>
            );
          })}
        </div>
        <MenuDropdown label="Company" value={companyFilter} onChange={setCompanyFilter}
          options={companyOptions} placeholder="All Companies" maxButtonWidth={240} />
      </div>

      {data?.source && (
        <p className="text-[11px] text-gray-500 dark:text-gray-400 mb-2">
          Source: <span className="font-semibold text-gray-900 dark:text-white">{data.source}</span> · Showing {filtered.length} of {items.length} latest filings
        </p>
      )}

      {isLoading && <Loading />}
      {error && !isLoading && <ErrorState message={(error as Error).message} />}
      {!error && !isLoading && data?.available === false && (
        <EmptyState title="Feed unavailable" message={data.message || "BSE feed temporarily unavailable."}
          icon={<FileText className="w-10 h-10"/>}/>
      )}
      {!isLoading && data?.available !== false && filtered.length === 0 && (
        <EmptyState title="No filings" message="No corporate filings match the selected filter."
          icon={<FileText className="w-10 h-10"/>}/>
      )}

      {filtered.length > 0 && (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-900/40">
              <tr>
                <th className="px-4 py-3 text-left">Company</th>
                <th className="px-4 py-3 text-left">Category</th>
                <th className="px-4 py-3 text-left">Description</th>
                <th className="px-4 py-3 text-left">Reported</th>
                <th className="px-4 py-3 text-right">Document</th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, 200).map((e) => (
                <tr key={e.id} className="border-t border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/30 transition">
                  <td className="px-4 py-2.5">
                    <div className="font-medium text-gray-900 dark:text-white">{e.company || "—"}</div>
                    {e.symbol && <div className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">{e.symbol}</div>}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`text-[11px] px-2 py-1 rounded-md whitespace-nowrap font-medium ${categoryColor(e.category || "")}`}>
                      {e.category || "Other"}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-gray-500 dark:text-gray-400 max-w-md truncate" title={e.purpose}>{e.purpose || "—"}</td>
                  <td className="px-4 py-2.5 text-gray-500 dark:text-gray-400 text-xs whitespace-nowrap">{fmtRelative(e.date)}</td>
                  <td className="px-4 py-2.5 text-right">
                    {e.documentUrl ? (
                      <a href={e.documentUrl} target="_blank" rel="noreferrer"
                         className="inline-flex items-center gap-1 text-xs text-indigo-600 dark:text-indigo-400 hover:underline font-medium">
                        View <ExternalLink className="w-3 h-3"/>
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
