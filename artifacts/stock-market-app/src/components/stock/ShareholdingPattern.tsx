/**
 * ShareholdingPattern — quarterly Promoter / FII / DII / Public %
 * breakdown for a single security. Renders the table layout the user
 * asked for, plus a small sources badge and a Quarterly/Yearly toggle.
 *
 * Why a table not a chart
 * -----------------------
 * The reference screenshot shows the data as a one-row-per-bucket
 * matrix with quarters as columns — that's how every Indian stock-data
 * UI (Screener, Tickertape, Trendlyne) renders it because each
 * percentage's quarter-on-quarter delta is the actionable signal.
 * Stacked-bar charts hide those deltas.
 *
 * Data shape: ShareholdingResponse from the backend, with rows ordered
 * newest-quarter-first. We pivot client-side so each row becomes a
 * column in the rendered table.
 */
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type ShareholdingRow } from "@/lib/api";
import { AlertCircle, Users, Loader2 } from "lucide-react";


interface Props {
  symbol: string;
}


// ── Bucket definitions ────────────────────────────────────────────────────
//
// Centralised so the row order, label text, and per-bucket color stay
// in lock-step between header and body. Adding a bucket = one line here.

type BucketKey = "promoterPct" | "fiiPct" | "diiPct" | "publicPct";

interface Bucket {
  key:        BucketKey;
  label:      string;
  /** Hex/Tailwind class for the small color dot next to the label.
   *  Same palette Screener uses for visual consistency. */
  dotClass:   string;
}

const BUCKETS: Bucket[] = [
  { key: "promoterPct", label: "Promoters", dotClass: "bg-indigo-500" },
  { key: "fiiPct",      label: "FIIs",      dotClass: "bg-emerald-500" },
  { key: "diiPct",      label: "DIIs",      dotClass: "bg-amber-500" },
  { key: "publicPct",   label: "Public",    dotClass: "bg-sky-500" },
];


// ── Cell renderers ────────────────────────────────────────────────────────


function PctCell({ value }: { value: number | null }) {
  if (value === null || value === undefined) {
    // Distinguish "not reported" from "0%" — null becomes "—".
    return <td className="px-3 py-2 text-right text-gray-400 dark:text-gray-600">—</td>;
  }
  return (
    <td className="px-3 py-2 text-right tabular-nums text-gray-900 dark:text-gray-100">
      {value.toFixed(2)}%
    </td>
  );
}

function CountCell({ value }: { value: number | null }) {
  if (value === null || value === undefined) {
    return <td className="px-3 py-2 text-right text-gray-400 dark:text-gray-600">—</td>;
  }
  return (
    <td className="px-3 py-2 text-right tabular-nums text-gray-500 dark:text-gray-400">
      {value.toLocaleString("en-IN")}
    </td>
  );
}


// ── Quarter-label formatter ───────────────────────────────────────────────


function quarterLabel(iso: string): string {
  // Backend gives us 2024-03-31; we want "Mar 2024". Doing this with
  // Intl is overkill — split the ISO and map the month.
  const [y, m] = iso.split("-");
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${months[parseInt(m, 10) - 1]} ${y}`;
}


// ── Component ─────────────────────────────────────────────────────────────


export default function ShareholdingPattern({ symbol }: Props) {
  const [view, setView] = useState<"quarterly" | "yearly">("quarterly");
  const [forceRefresh, setForceRefresh] = useState(false);

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    // Include `forceRefresh` in the queryKey so toggling it triggers
    // a fresh queryFn invocation — useQuery skips refetch if key + fn
    // didn't change, so a plain `refetch()` would re-hit the same
    // backend URL without the force flag.
    queryKey: ["shareholding", symbol, view, forceRefresh],
    queryFn:  () => {
      // 32 quarters = 8 years. NSE corp-info has 80+ quarters back;
      // the XBRL fan-out fetches up to 32 of those for FII/DII
      // enrichment. Anything beyond stays Promoter/Public-only from
      // the NSE summary.
      const opts = { view, quarters: 32, force: forceRefresh };
      // One-shot — once the request is in flight, drop the flag back
      // to false. The PG cache that comes back from this force-fetch
      // is now authoritative for any subsequent reads from this query.
      if (forceRefresh) {
        setTimeout(() => setForceRefresh(false), 0);
      }
      return api.stockShareholding(symbol, opts);
    },
    enabled:  !!symbol,
    // SEBI filings are immutable per quarter; weekly stale time is plenty.
    staleTime: 7 * 24 * 3600 * 1000,
  });

  /** Called from the Refresh button — flips the force flag, which
   *  changes the queryKey, which makes useQuery actually re-run the
   *  fetch with `?force=1` instead of just re-reading the React-Query
   *  cache. Without this, the previous version called `refetch()`
   *  which re-fired the SAME queryFn (no force flag) and the backend
   *  just served from PG cache again. */
  const handleForceRefresh = () => {
    setForceRefresh(true);
  };

  // Reverse the row order client-side so columns read left-to-right
  // oldest → newest, matching the screenshot. Server gives newest first
  // (good for "most recent" reads); pivoting needs the opposite.
  const ordered = useMemo<ShareholdingRow[]>(() => {
    if (!data?.rows) return [];
    return [...data.rows].reverse();
  }, [data]);

  // ── render branches ──
  if (isLoading) {
    return (
      <div className="flex items-center gap-2 p-6 text-sm text-gray-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading shareholding pattern…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 text-amber-600 bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm">
        <AlertCircle className="w-4 h-4" /> {(error as Error).message}
      </div>
    );
  }

  if (!ordered.length) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Shareholding Pattern
          </h3>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          No shareholding pattern data available for {symbol}. This is usually
          because the security is brand new, delisted, or NSE/BSE/Yahoo all
          returned empty filings — try refreshing in a minute.
        </p>
        <button
          onClick={handleForceRefresh}
          className="mt-3 text-xs px-3 py-1.5 rounded-md bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600"
        >
          Refresh
        </button>
      </div>
    );
  }

  // ── main table ──
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      {/* Header strip: title, view toggle, source badge */}
      <div className="px-5 py-4 flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 dark:border-gray-700">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Shareholding Pattern
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400">Numbers in percentages</p>
        </div>
        <div className="flex items-center gap-2">
          {data?.sources?.length ? (
            <span className="text-[10px] uppercase tracking-wide px-2 py-1 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
              {data.sources.join(" + ")}
            </span>
          ) : null}
          {/* Quarterly / Yearly toggle — segmented control. */}
          <div className="inline-flex rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 text-xs font-medium">
            <button
              onClick={() => setView("quarterly")}
              className={`px-3 py-1.5 rounded-md transition-colors ${
                view === "quarterly"
                  ? "bg-indigo-50 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-200"
                  : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              }`}
            >
              Quarterly
            </button>
            <button
              onClick={() => setView("yearly")}
              className={`px-3 py-1.5 rounded-md transition-colors ${
                view === "yearly"
                  ? "bg-indigo-50 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-200"
                  : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              }`}
            >
              Yearly
            </button>
          </div>
          <button
            onClick={handleForceRefresh}
            disabled={isFetching}
            className="text-xs px-3 py-1.5 rounded-md bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50"
            title="Re-fetch from primary sources (bypasses PG cache via ?force=1)"
          >
            {isFetching ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      {/* Pivoted table — buckets as rows, quarters as columns. */}
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-900/40">
            <tr>
              <th className="sticky left-0 z-10 bg-gray-50 dark:bg-gray-900/40 px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                {/* empty corner — buckets go in this column */}
              </th>
              {ordered.map((r) => (
                <th key={r.asOnDate}
                    className="px-3 py-2 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  {quarterLabel(r.asOnDate)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
            {BUCKETS.map((b, i) => {
              // Solid (non-transparent) backgrounds for both row stripes.
              // The sticky left column inherits from this — if the row
              // is semi-transparent (was `bg-gray-50/50`), the sticky
              // cell becomes see-through and the FIRST data column
              // visually leaks through the label area while scrolling.
              // Use opaque colours so the sticky cell fully covers.
              const rowBg = i % 2 === 0
                ? "bg-white dark:bg-gray-800"
                : "bg-gray-50 dark:bg-gray-900";
              return (
                <tr key={b.key} className={rowBg}>
                  <td className={`sticky left-0 z-10 ${rowBg} px-3 py-2 font-medium text-gray-700 dark:text-gray-200`}>
                    <span className="inline-flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${b.dotClass}`} />
                      {b.label}
                    </span>
                  </td>
                  {ordered.map((r) => (
                    <PctCell key={r.asOnDate} value={r[b.key]} />
                  ))}
                </tr>
              );
            })}
            {/* Number-of-shareholders row — same structure but integers,
                not percentages. Hidden when every cell is null. */}
            {ordered.some((r) => r.numShareholders != null) && (
              <tr className="bg-white dark:bg-gray-800">
                <td className="sticky left-0 z-10 bg-white dark:bg-gray-800 px-3 py-2 font-medium text-gray-500 dark:text-gray-400">
                  <span className="inline-flex items-center gap-2">
                    <Users className="w-3.5 h-3.5" />
                    No. of Shareholders
                  </span>
                </td>
                {ordered.map((r) => (
                  <CountCell key={r.asOnDate} value={r.numShareholders} />
                ))}
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Footer note — same SEBI caveat Screener shows; reassures
          users that classifications can shift over time. */}
      <div className="px-5 py-2 text-[11px] text-gray-400 dark:text-gray-500 border-t border-gray-100 dark:border-gray-700">
        * Categories follow SEBI LODR filings. Classifications may have changed across periods.
      </div>
    </div>
  );
}
