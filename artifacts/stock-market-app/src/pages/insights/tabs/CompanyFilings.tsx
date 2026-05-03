import { useState, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, Card, Loading, EmptyState, MenuDropdown, ErrorState } from "../_shared";
import { FileText, ExternalLink, RefreshCw } from "lucide-react";

type FilingType = "corporate" | "insider" | "shareholding";
type FilingSource = "all" | "bse" | "nse";
type Category =
  | "all" | "Result" | "Board Meeting" | "AGM/EGM" | "Dividend"
  | "Bonus" | "Acquisition" | "Investor Presentation" | "Company Update";

interface Filing {
  id: string;
  exchange?: "BSE" | "NSE";
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
  sources?: string[];
  source?: string;
  message?: string;
  items: Filing[];
  total?: number;
  hasMore?: boolean;
  page?: number;
  meta?: { asOf?: string };
}

const TYPE_TABS: { value: FilingType; label: string }[] = [
  { value: "corporate",    label: "Corporate" },
  { value: "insider",      label: "Insider Trading" },
  { value: "shareholding", label: "Shareholding" },
];

const SOURCE_TABS: { value: FilingSource; label: string }[] = [
  { value: "all", label: "BSE + NSE" },
  { value: "bse", label: "BSE" },
  { value: "nse", label: "NSE" },
];

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
    // Backend returns ISO with explicit +05:30 offset, so JS parses the
    // correct instant regardless of the user's timezone.
    const d = new Date(s);
    if (isNaN(d.getTime())) return s;
    const diff = Date.now() - d.getTime();
    const min = Math.round(diff / 60000);
    if (min < 1) return "just now";
    if (min < 60) return `${min} min ago`;
    const hrs = Math.round(min / 60);
    if (hrs < 24) return `${hrs} hr${hrs === 1 ? "" : "s"} ago`;
    const days = Math.round(hrs / 24);
    if (days < 7) return `${days} day${days === 1 ? "" : "s"} ago`;
    return d.toLocaleDateString("en-IN", { dateStyle: "medium" });
  } catch { return s; }
}

function fmtAsOf(s?: string) {
  if (!s) return "";
  try {
    const d = new Date(s);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleTimeString("en-IN", {
      hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata",
    }) + " IST";
  } catch { return ""; }
}

function categoryColor(cat: string) {
  const c = (cat || "").toLowerCase();
  if (c.includes("result")) return "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300";
  if (c.includes("dividend")) return "bg-sky-500/15 text-sky-700 dark:text-sky-300";
  if (c.includes("agm") || c.includes("egm")) return "bg-purple-500/15 text-purple-700 dark:text-purple-300";
  if (c.includes("board")) return "bg-amber-500/15 text-amber-700 dark:text-amber-300";
  if (c.includes("acquisition") || c.includes("merger")) return "bg-rose-500/15 text-rose-700 dark:text-rose-300";
  if (c.includes("bonus") || c.includes("split")) return "bg-pink-500/15 text-pink-700 dark:text-pink-300";
  if (c.includes("investor")) return "bg-indigo-500/15 text-indigo-700 dark:text-indigo-300";
  if (c.includes("insider")) return "bg-orange-500/15 text-orange-700 dark:text-orange-300";
  return "bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400";
}

function exchangeBadge(ex?: string) {
  if (ex === "NSE") return "bg-blue-500/15 text-blue-700 dark:text-blue-300";
  if (ex === "BSE") return "bg-violet-500/15 text-violet-700 dark:text-violet-300";
  return "bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400";
}

const PAGE_SIZE = 50;

export default function CompanyFilings() {
  const [type, setType] = useState<FilingType>("corporate");
  const [source, setSource] = useState<FilingSource>("all");
  const [cat, setCat] = useState<Category>("all");
  const [companyFilter, setCompanyFilter] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const qc = useQueryClient();

  // Reset paging whenever a server-side filter changes.
  const queryKey = useMemo(
    () => ["insights/company-filings", type, source, cat, page],
    [type, source, cat, page],
  );

  const { data, isLoading, isFetching, error, refetch } = useQuery<FilingsResponse>({
    queryKey,
    queryFn: () => {
      const params = new URLSearchParams({
        source,
        type,
        category: cat === "all" ? "all" : cat,
        page: String(page),
        pageSize: String(PAGE_SIZE),
      });
      return fetchApi(`/insights/company-filings?${params.toString()}`);
    },
    staleTime: 5 * 60_000,
    placeholderData: (prev) => prev,
  });

  const items: Filing[] = data?.items || [];

  const setTypeAndReset = (t: FilingType) => {
    setType(t);
    setPage(1);
    // Insider tab forces NSE source (only working insider feed).
    if (t === "insider") setSource("nse");
    if (t === "corporate" && source === "nse") setSource("all");
  };
  const setSourceAndReset = (s: FilingSource) => { setSource(s); setPage(1); };
  const setCatAndReset = (c: Category) => { setCat(c); setPage(1); };

  // Client-side narrowing on top of server-side filters.
  const filtered = useMemo(() => {
    let r = items;
    if (companyFilter) r = r.filter(it => it.company === companyFilter);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      r = r.filter(it =>
        (it.company || "").toLowerCase().includes(q) ||
        (it.symbol  || "").toLowerCase().includes(q) ||
        (it.purpose || "").toLowerCase().includes(q),
      );
    }
    return r;
  }, [items, companyFilter, search]);

  const companyOptions = useMemo(() => {
    const set = new Map<string, string>();
    for (const it of items) {
      if (!it.company) continue;
      if (!set.has(it.company)) set.set(it.company, it.company);
    }
    return Array.from(set.values()).sort().map(c => ({ value: c, label: c }));
  }, [items]);

  const total = data?.total ?? items.length;
  const hasMore = !!data?.hasMore && page < 20;
  const sources = data?.sources?.length ? data.sources.join(" · ") : data?.source;
  const asOf = fmtAsOf(data?.meta?.asOf);

  const handleRefresh = () => {
    qc.invalidateQueries({ queryKey: ["insights/company-filings"] });
    refetch();
  };

  // Type-specific tab visibility.
  const showCategoryTabs = type === "corporate";
  const showSourceTabs   = type === "corporate";
  const isUnavailable = data?.available === false;

  return (
    <div>
      <PageHeader
        title="Company Filings"
        info="Live BSE + NSE corporate disclosures (results, dividends, AGMs, board meetings, insider trades)"
        right={
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search company / symbol / purpose…"
              className="text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white rounded-lg px-3 py-2 w-64 outline-none focus:border-indigo-600 dark:focus:border-indigo-500 placeholder:text-gray-500 dark:placeholder:text-gray-400"
            />
            <button
              onClick={handleRefresh}
              disabled={isFetching}
              title="Refresh"
              className="text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white rounded-lg p-2 transition disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? "animate-spin" : ""}`} />
            </button>
          </div>
        }
      />

      {/* Type segmented control */}
      <div className="flex items-center gap-1.5 mb-3 flex-wrap">
        {TYPE_TABS.map(t => {
          const active = type === t.value;
          return (
            <button
              key={t.value}
              onClick={() => setTypeAndReset(t.value)}
              className={`text-xs px-3 py-1.5 rounded-lg border transition whitespace-nowrap font-medium
                ${active
                  ? "bg-gray-900 dark:bg-white text-white dark:text-gray-900 border-gray-900 dark:border-white"
                  : "bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-white"}`}
            >
              {t.label}
            </button>
          );
        })}
        {showSourceTabs && (
          <>
            <span className="text-gray-300 dark:text-gray-600 mx-1">|</span>
            {SOURCE_TABS.map(s => {
              const active = source === s.value;
              return (
                <button
                  key={s.value}
                  onClick={() => setSourceAndReset(s.value)}
                  className={`text-xs px-3 py-1.5 rounded-lg border transition whitespace-nowrap font-medium
                    ${active
                      ? "bg-indigo-600 dark:bg-indigo-500 text-white border-indigo-600 dark:border-indigo-500"
                      : "bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-white"}`}
                >
                  {s.label}
                </button>
              );
            })}
          </>
        )}
      </div>

      {/* Sub-tabs row + company filter */}
      {showCategoryTabs && (
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          <div className="flex items-center gap-1.5 flex-wrap flex-1">
            {SUB_TABS.map(t => {
              const active = cat === t.value;
              return (
                <button
                  key={t.value}
                  onClick={() => setCatAndReset(t.value)}
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
      )}

      <p className="text-[11px] text-gray-500 dark:text-gray-400 mb-2">
        {sources && (
          <>Source: <span className="font-semibold text-gray-900 dark:text-white">{sources}</span> · </>
        )}
        Showing {filtered.length} of {items.length} filings
        {total > items.length && <> · {total.toLocaleString("en-IN")} total</>}
        {asOf && <> · Updated {asOf}</>}
      </p>

      {isLoading && <Loading />}
      {error && !isLoading && <ErrorState message={(error as Error)?.message || "Failed to load filings"} />}
      {!error && !isLoading && isUnavailable && (
        <EmptyState title="Feed unavailable" message={data?.message || "Filings feed temporarily unavailable."}
          icon={<FileText className="w-10 h-10"/>}/>
      )}
      {!isLoading && !isUnavailable && filtered.length === 0 && (
        <EmptyState title="No filings" message={data?.message || "No filings match the selected filter."}
          icon={<FileText className="w-10 h-10"/>}/>
      )}

      {filtered.length > 0 && (
        <>
          <Card className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-900/40">
                <tr>
                  <th className="px-4 py-3 text-left">Company</th>
                  <th className="px-4 py-3 text-left">Exchange</th>
                  <th className="px-4 py-3 text-left">Category</th>
                  <th className="px-4 py-3 text-left">Description</th>
                  <th className="px-4 py-3 text-left">Reported</th>
                  <th className="px-4 py-3 text-right">Document</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((e) => (
                  <tr key={e.id} className="border-t border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/30 transition">
                    <td className="px-4 py-2.5">
                      <div className="font-medium text-gray-900 dark:text-white">{e.company || "—"}</div>
                      {e.symbol && <div className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">{e.symbol}</div>}
                    </td>
                    <td className="px-4 py-2.5">
                      {e.exchange && (
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${exchangeBadge(e.exchange)}`}>
                          {e.exchange}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={`text-[11px] px-2 py-1 rounded-md whitespace-nowrap font-medium ${categoryColor(e.category || "")}`}>
                        {e.category || "Other"}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-gray-500 dark:text-gray-400 max-w-md truncate" title={e.purpose}>{e.purpose || "—"}</td>
                    <td className="px-4 py-2.5 text-gray-500 dark:text-gray-400 text-xs whitespace-nowrap" title={e.date}>{fmtRelative(e.date)}</td>
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

          {(page > 1 || hasMore) && (
            <div className="flex items-center justify-center gap-3 mt-4">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={isFetching || page <= 1}
                className="text-xs px-4 py-2 rounded-lg border bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white hover:bg-gray-100 dark:hover:bg-gray-700 transition disabled:opacity-40 font-medium"
              >
                ← Previous
              </button>
              <span className="text-xs text-gray-500 dark:text-gray-400 font-medium">Page {page}</span>
              <button
                onClick={() => setPage(p => p + 1)}
                disabled={isFetching || !hasMore}
                className="text-xs px-4 py-2 rounded-lg border bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white hover:bg-gray-100 dark:hover:bg-gray-700 transition disabled:opacity-40 font-medium"
              >
                {isFetching ? "Loading…" : "Next →"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
