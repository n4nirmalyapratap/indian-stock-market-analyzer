import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, NewsEvent } from "@/lib/api";
import {
  PageHeader, Loading, EmptyState, ErrorState, PillTabs, Card,
} from "../_shared";
import { CalendarClock, Search, X } from "lucide-react";

const EVENT_TYPE_META: Record<string, { label: string; dot: string }> = {
  dividend:     { label: "Dividend",     dot: "bg-violet-500" },
  results:      { label: "Results",      dot: "bg-cyan-500" },
  split:        { label: "Split",        dot: "bg-orange-500" },
  meeting:      { label: "Meeting",      dot: "bg-gray-500" },
  merger:       { label: "M&A",          dot: "bg-amber-500" },
  announcement: { label: "Announcement", dot: "bg-indigo-500" },
};

function eventMeta(t: string) {
  return EVENT_TYPE_META[t] ?? { label: t.toUpperCase(), dot: "bg-indigo-500" };
}

const FILTERS = [
  { value: "all",           label: "All" },
  { value: "results",       label: "Results" },
  { value: "dividend",      label: "Dividend" },
  { value: "split",         label: "Split" },
  { value: "meeting",       label: "Meeting" },
  { value: "merger",        label: "M&A" },
  { value: "announcement",  label: "Announcement" },
];

export default function CorpEvents() {
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["insightsCorpEvents"],
    queryFn:  api.newsEvents,
    staleTime: 15 * 60 * 1000,
  });

  const filtered = useMemo(() => {
    const events: NewsEvent[] = data?.events ?? [];
    const q = search.trim().toLowerCase();
    return events.filter(ev => {
      if (filter !== "all" && ev.type !== filter) return false;
      if (!q) return true;
      return (
        ev.symbol.toLowerCase().includes(q) ||
        ev.company.toLowerCase().includes(q) ||
        ev.purpose.toLowerCase().includes(q)
      );
    });
  }, [data, filter, search]);

  const subtitle = data
    ? `${data.total} upcoming corporate event${data.total === 1 ? "" : "s"} from NSE`
    : "Upcoming corporate events from NSE";

  return (
    <div>
      <PageHeader
        title="Corporate Events"
        subtitle={subtitle}
        info="Dividend, results, splits, board meetings, M&A and other scheduled corporate actions."
      />

      {isLoading ? (
        <Loading label="Loading corporate events…" />
      ) : isError ? (
        <ErrorState message={(error as Error)?.message || "Failed to load corporate events."} />
      ) : !data?.available ? (
        <ErrorState
          message={
            data?.error
              ? `NSE events unavailable: ${data.error}`
              : "Corporate events feed is currently unavailable."
          }
        />
      ) : (
        <>
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-4">
            <PillTabs value={filter} onChange={setFilter} options={FILTERS} />
            <div className="relative w-full md:w-72">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search symbol, company, purpose…"
                className="w-full pl-9 pr-8 py-2 rounded-lg text-sm border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white outline-none focus:border-indigo-500"
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                  aria-label="Clear search"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>

          {filtered.length === 0 ? (
            <EmptyState
              icon={<CalendarClock className="w-10 h-10" />}
              title="No matching events"
              message={
                search || filter !== "all"
                  ? "Try clearing filters or your search."
                  : "No upcoming corporate events were returned for the next window."
              }
            />
          ) : (
            <Card className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[640px]">
                  <thead>
                    <tr className="bg-gray-50 dark:bg-gray-900/40 border-b border-gray-100 dark:border-gray-700">
                      {["Type", "Symbol", "Company", "Purpose", "Date"].map(h => (
                        <th
                          key={h}
                          className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((ev, i) => {
                      const meta = eventMeta(ev.type);
                      return (
                        <tr
                          key={i}
                          className="border-b border-gray-100 dark:border-gray-700/60 last:border-0 hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors"
                        >
                          <td className="px-4 py-3">
                            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-700 dark:text-gray-300">
                              <span className={`w-2 h-2 rounded-full ${meta.dot}`} />
                              {meta.label}
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            <span className="font-mono font-bold text-indigo-600 dark:text-indigo-400">
                              {ev.symbol || "—"}
                            </span>
                          </td>
                          <td className="px-4 py-3 max-w-[240px] truncate text-gray-900 dark:text-white">
                            {ev.company || "—"}
                          </td>
                          <td className="px-4 py-3 max-w-[320px] truncate text-gray-600 dark:text-gray-300">
                            {ev.purpose || "—"}
                          </td>
                          <td className="px-4 py-3 font-mono text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
                            {ev.date || "TBA"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
