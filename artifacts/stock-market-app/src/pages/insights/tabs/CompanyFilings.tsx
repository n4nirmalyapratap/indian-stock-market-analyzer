import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, PillTabs, Card, Loading, EmptyState, Dropdown } from "../_shared";
import { FileText } from "lucide-react";

type Category = "all" | "results" | "dividend" | "split" | "meeting" | "agm" | "other";

interface RawEvent {
  symbol?: string;
  company?: string;
  purpose?: string;
  date?: string;
  type?: string;   // already classified by backend (e.g. "Results", "Dividend")
}

interface EventsResponse {
  events: RawEvent[];
  total?: number;
  refreshedAt?: string;
}

const CAT_OPTIONS: { value: Category; label: string }[] = [
  { value: "all", label: "All" },
  { value: "results", label: "Financial Results" },
  { value: "dividend", label: "Dividend" },
  { value: "split", label: "Splits / Bonus" },
  { value: "meeting", label: "Board Meeting" },
  { value: "agm", label: "AGM / EGM" },
  { value: "other", label: "Other" },
];

function matchCategory(cat: Category, t: string): boolean {
  if (cat === "all") return true;
  const lc = (t || "").toLowerCase();
  switch (cat) {
    case "results":  return lc.includes("result") || lc.includes("earning");
    case "dividend": return lc.includes("dividend");
    case "split":    return lc.includes("split") || lc.includes("bonus");
    case "meeting":  return lc.includes("board") || lc.includes("meeting");
    case "agm":      return lc.includes("agm") || lc.includes("egm");
    case "other":    return !["result","earning","dividend","split","bonus","board","meeting","agm","egm"]
                              .some(k => lc.includes(k));
  }
}

export default function CompanyFilings() {
  const [cat, setCat] = useState<Category>("all");
  const [companyFilter, setCompanyFilter] = useState<string>("all");

  const { data, isLoading } = useQuery<EventsResponse>({
    queryKey: ["insights/company-filings"],
    queryFn: () => fetchApi(`/news/events`),
    staleTime: 5 * 60_000,
  });

  const events: RawEvent[] = data?.events || [];

  const filtered = useMemo(() => {
    let r = events.filter(e => matchCategory(cat, e.type || e.purpose || ""));
    if (companyFilter !== "all") {
      r = r.filter(e => (e.company || "").toLowerCase() === companyFilter.toLowerCase());
    }
    return r;
  }, [events, cat, companyFilter]);

  const companies = useMemo(() => {
    const set = new Set<string>();
    events.forEach(e => e.company && set.add(e.company));
    return ["all", ...Array.from(set).sort()];
  }, [events]);

  return (
    <div>
      <PageHeader
        title="Company Filings"
        info="Latest BSE/NSE corporate disclosures"
        right={
          <Dropdown value={companyFilter} onChange={setCompanyFilter}
            options={companies.map(c => ({value: c, label: c === "all" ? "All Companies" : c}))}/>
        }
      />
      <PillTabs value={cat} onChange={setCat} options={CAT_OPTIONS}/>

      {isLoading && <Loading />}
      {!isLoading && filtered.length === 0 && (
        <EmptyState title="No filings" message="No corporate filings match the selected filter." icon={<FileText className="w-10 h-10"/>}/>
      )}

      {filtered.length > 0 && (
        <Card className="mt-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/40">
              <tr>
                <th className="px-4 py-3 text-left">Company</th>
                <th className="px-4 py-3 text-left">Symbol</th>
                <th className="px-4 py-3 text-left">Category</th>
                <th className="px-4 py-3 text-left">Purpose</th>
                <th className="px-4 py-3 text-left">Date</th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, 200).map((e, i) => (
                <tr key={(e.symbol || "") + i} className="border-t border-gray-100 dark:border-white/[0.05]">
                  <td className="px-4 py-2.5 font-medium text-gray-900 dark:text-white">{e.company || "—"}</td>
                  <td className="px-4 py-2.5 text-gray-500 dark:text-gray-400">{e.symbol || "—"}</td>
                  <td className="px-4 py-2.5">
                    <span className="text-xs px-2 py-1 rounded-md bg-indigo-50 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-300">
                      {e.type || "Other"}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-gray-600 dark:text-gray-300 max-w-md truncate" title={e.purpose}>{e.purpose || "—"}</td>
                  <td className="px-4 py-2.5 text-gray-500 dark:text-gray-400 text-xs">{e.date || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
