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
import { api, type ShareholdingRow, type ShareholdingNamedHolder } from "@/lib/api";
import { AlertCircle, Users, Loader2, ShieldAlert, Lock } from "lucide-react";


interface Props {
  symbol: string;
}


// ── Bucket definitions ────────────────────────────────────────────────────
//
// Centralised so the row order, label text, and per-bucket color stay
// in lock-step between header and body. Adding a bucket = one line here.
// `core` rows always render; non-core rows (Government) only render when
// at least one quarter actually reports a value, so the vast majority of
// companies (zero government holding) don't get an all-"—" row.

type BucketKey = "promoterPct" | "fiiPct" | "diiPct" | "govtPct" | "publicPct";

interface Bucket {
  key:      BucketKey;
  label:    string;
  /** Tailwind class for the small color dot next to the label.
   *  Same palette Screener uses for visual consistency. */
  dotClass: string;
  core:     boolean;
}

const BUCKETS: Bucket[] = [
  { key: "promoterPct", label: "Promoters",  dotClass: "bg-indigo-500",  core: true  },
  { key: "fiiPct",      label: "FIIs",       dotClass: "bg-emerald-500", core: true  },
  { key: "diiPct",      label: "DIIs",       dotClass: "bg-amber-500",   core: true  },
  { key: "govtPct",     label: "Government", dotClass: "bg-rose-400",    core: false },
  { key: "publicPct",   label: "Public",     dotClass: "bg-sky-500",     core: true  },
];

// Capital-structure flags worth surfacing as badges (a "true" here means
// the plain % can understate eventual dilution / divergence from economic
// ownership). Keyed by the backend `details.flags` keys.
const FLAG_LABELS: Record<string, string> = {
  hasOutstandingEsop:          "ESOP outstanding",
  hasWarrants:                 "Warrants",
  hasConvertibles:             "Convertibles",
  hasDifferentialVotingRights: "DVR",
  hasDepositoryReceipts:       "ADR/GDR",
  hasPartlyPaidShares:         "Partly-paid",
  isPsu:                       "PSU",
  isSme:                       "SME",
};

// Color chip per named-holder group.
const GROUP_CLASS: Record<string, string> = {
  "FII / FPI":   "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  "Mutual Fund": "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  "Insurance":   "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  "Public":      "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  "Other Indian":"bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
};


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


// ── Top named holders panel ───────────────────────────────────────────────
//
// Same "which funds / FIIs hold this, and did they add or trim" view that
// Tickertape/Trendlyne lead with. Built from the latest quarter's
// `details.namedHolders`, with a quarter-on-quarter delta computed by
// matching holder names against the previous quarter.

function holderDelta(
  holder: ShareholdingNamedHolder,
  prevByName: Map<string, number>,
): { text: string; cls: string } | null {
  if (holder.pct == null) return null;
  const prev = prevByName.get(holder.name.trim().toLowerCase());
  if (prev === undefined) return { text: "NEW", cls: "text-indigo-600 dark:text-indigo-400" };
  const d = holder.pct - prev;
  if (Math.abs(d) < 0.01) return { text: "—", cls: "text-gray-400" };
  const sign = d > 0 ? "+" : "";
  return {
    text: `${sign}${d.toFixed(2)}`,
    cls: d > 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400",
  };
}

function TopHolders({ rows }: { rows: ShareholdingRow[] }) {
  const latest = rows[0];
  const holders = (latest?.details?.namedHolders ?? []).filter((h) => h.pct != null);
  if (!holders.length) return null;

  const prevByName = new Map<string, number>();
  for (const h of rows[1]?.details?.namedHolders ?? []) {
    if (h.pct != null) prevByName.set(h.name.trim().toLowerCase(), h.pct);
  }

  const top = holders.slice(0, 12);
  return (
    <div className="px-5 py-4 border-t border-gray-100 dark:border-gray-700">
      <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-0.5">
        Top Disclosed Holders
      </h4>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
        Largest named holders as of {quarterLabel(latest.asOnDate)}. Δ vs previous quarter.
      </p>
      <div className="space-y-1">
        {top.map((h) => {
          const delta = holderDelta(h, prevByName);
          return (
            <div key={`${h.name}-${h.shares}`} className="flex items-center gap-2 text-sm">
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0 ${
                  GROUP_CLASS[h.group] ?? "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300"
                }`}
              >
                {h.group}
              </span>
              <span className="flex-1 truncate text-gray-700 dark:text-gray-200" title={h.name}>
                {h.name}
              </span>
              <span className="tabular-nums font-medium text-gray-900 dark:text-gray-100">
                {h.pct!.toFixed(2)}%
              </span>
              {delta && (
                <span className={`tabular-nums text-xs w-12 text-right ${delta.cls}`}>
                  {delta.text}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}


// ── Latest-quarter structure strip ────────────────────────────────────────
//
// Compact "current state" facts that aren't quarter-on-quarter trends:
// demat %, lock-in overhang, FII headroom, and capital-structure flags.

function StructureStrip({ row }: { row: ShareholdingRow }) {
  const stats: { label: string; value: string }[] = [];
  if (row.dematPct != null) stats.push({ label: "Demat", value: `${row.dematPct.toFixed(1)}%` });
  if (row.lockedInPct != null && row.lockedInPct > 0.01)
    stats.push({ label: "Locked-in", value: `${row.lockedInPct.toFixed(1)}%` });
  const fpi = row.details?.fpiLimits;
  if (fpi?.limitsUtilizedPct != null && fpi?.boardApprovedPct != null)
    stats.push({ label: "FII limit used", value: `${fpi.limitsUtilizedPct.toFixed(1)}% / ${fpi.boardApprovedPct.toFixed(0)}%` });

  const flags = Object.entries(row.details?.flags ?? {})
    .filter(([k, v]) => v && FLAG_LABELS[k])
    .map(([k]) => FLAG_LABELS[k]);

  if (!stats.length && !flags.length) return null;

  return (
    <div className="px-5 py-3 border-t border-gray-100 dark:border-gray-700 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
      {stats.map((s) => (
        <span key={s.label} className="text-gray-500 dark:text-gray-400">
          {s.label}: <span className="font-medium text-gray-800 dark:text-gray-200 tabular-nums">{s.value}</span>
        </span>
      ))}
      {flags.length > 0 && (
        <span className="flex flex-wrap items-center gap-1.5">
          {flags.map((f) => (
            <span key={f} className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
              {f}
            </span>
          ))}
        </span>
      )}
    </div>
  );
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

  // Server gives newest first. Keep that order in the pivot so columns
  // read left-to-right newest → oldest (most recent quarter is leftmost,
  // which is what the user wants in the table view).
  const ordered = useMemo<ShareholdingRow[]>(() => {
    if (!data?.rows) return [];
    return data.rows;
  }, [data]);

  // Core buckets always show; Government only when some quarter reports
  // it (avoids an all-"—" row for the ~99% of companies with none).
  const visibleBuckets = useMemo(
    () => BUCKETS.filter((b) => b.core || ordered.some((r) => r[b.key] != null)),
    [ordered],
  );
  // The pledge row only renders when at least one quarter has a pledge
  // figure (XBRL-sourced). A rising trend here is the distress signal.
  const showPledge = useMemo(
    () => ordered.some((r) => r.promoterPledgePct != null),
    [ordered],
  );

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
            {visibleBuckets.map((b, i) => {
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
            {/* Promoter pledge row — XBRL-sourced, % of promoter holding
                that is pledged/encumbered. Highlighted because a rising
                pledge is the classic promoter-distress signal. Only shown
                when some quarter reports it. */}
            {showPledge && (
              <tr className="bg-rose-50/60 dark:bg-rose-900/10">
                <td className="sticky left-0 z-10 bg-rose-50/60 dark:bg-rose-900/10 px-3 py-2 font-medium text-rose-700 dark:text-rose-300">
                  <span className="inline-flex items-center gap-2">
                    <ShieldAlert className="w-3.5 h-3.5" />
                    Promoter Pledge
                  </span>
                </td>
                {ordered.map((r) => {
                  const v = r.promoterPledgePct;
                  return (
                    <td key={r.asOnDate}
                        className={`px-3 py-2 text-right tabular-nums ${
                          v && v > 0 ? "text-rose-600 dark:text-rose-400 font-semibold"
                                     : "text-gray-500 dark:text-gray-400"
                        }`}>
                      {v == null ? "—" : `${v.toFixed(2)}%`}
                    </td>
                  );
                })}
              </tr>
            )}
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

      {/* Latest-quarter structure facts + top named holders (XBRL only). */}
      {ordered[0] && <StructureStrip row={ordered[0]} />}
      <TopHolders rows={ordered} />

      {/* Footer note — same SEBI caveat Screener shows; reassures
          users that classifications can shift over time. */}
      <div className="px-5 py-2 text-[11px] text-gray-400 dark:text-gray-500 border-t border-gray-100 dark:border-gray-700">
        * Categories follow SEBI LODR filings. Pledge / demat / holder details are from the XBRL filing; classifications may shift across periods.
      </div>
    </div>
  );
}
