/**
 * TopMoversPanel — compact Groww-style top movers tile for the Dashboard.
 *
 * Layout (idle):
 *   ┌─ Top Movers · Biggest gainers/losers by market cap · [Live ●] ────┐
 *   │  [Large] [Mid] [Small] [Micro]                                     │
 *   │                                                                    │
 *   │  ┌──── Top Gainers ──────┐  ┌──── Top Losers ──────┐               │
 *   │  │ (R) RELIANCE  +5.42% │  │ (I) ITC      -3.81%  │               │
 *   │  │     Reliance Inds 📊🔍│  │     ITC Ltd     📊🔍 │               │
 *   │  │ (H) HDFCBANK  +3.10% │  │ (W) WIPRO    -2.55%  │               │
 *   │  │ (T) TCS       +2.45% │  │ (S) SBIN     -2.10%  │               │
 *   │  │ View all 10 →        │  │ View all 10 →        │               │
 *   │  └──────────────────────┘  └──────────────────────┘               │
 *   └────────────────────────────────────────────────────────────────────┘
 *
 * Rows are NOT clickable — the user told us not to make the whole row
 * navigate. The two action icons (Chart Studio + Stock Lookup) on each
 * row use the standard ChartButton component used elsewhere in the app
 * (Patterns, Scanners, SectorDetail, BulkBlockDeals). Clicking either
 * icon stops propagation so the row never registers a click.
 *
 * "View all" opens a modal with the full 10-each list so we don't lose
 * the data when collapsing the inline view to 3.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  TrendingUp, TrendingDown, AlertCircle, Activity,
  X as XIcon,
} from "lucide-react";
import { api, TopMoverRow, TopMoversAllResponse } from "@/lib/api";
import { marketDataQueryOptions } from "@/lib/marketData";
import ChartButton from "@/components/ChartButton";
import StockLogo from "@/components/StockLogo";
import { fmtPct } from "@/lib/format";

type Segment = "large" | "mid" | "small" | "micro";

const SEGMENTS: { key: Segment; label: string; description: string }[] = [
  { key: "large", label: "Large Cap", description: "NIFTY 100" },
  { key: "mid",   label: "Mid Cap",   description: "NIFTY MIDCAP 150" },
  { key: "small", label: "Small Cap", description: "NIFTY SMALLCAP 250" },
  { key: "micro", label: "Micro Cap", description: "NIFTY MICROCAP 250" },
];

// How many rows to show inline before the "View all" expand. Three keeps
// the panel scan-friendly without dominating the dashboard.
const INLINE_COUNT = 3;

function fmtPrice(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return "—";
  return `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

/** Market-state pill: green when open, amber when closed. Identical to
 *  the previous design — only the layout around it changed. */
function MarketStatePill({ state, asOf }: { state?: string; asOf?: string }) {
  const isOpen = state === "OPEN";
  const cls = isOpen
    ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20"
    : "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/20";
  const label = isOpen ? "Live · Market Open"
              : state === "PRE_OPEN" ? "Pre-Open"
              : state === "WEEKEND"  ? "Weekend · Last close"
              :                        "Market Closed · Last close";
  return (
    <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold border ${cls}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${isOpen ? "bg-emerald-500 animate-pulse" : "bg-amber-500"}`} />
      <span>{label}</span>
      {asOf && <span className="opacity-70">· {asOf.slice(11, 16)}</span>}
    </div>
  );
}

/** One compact row — non-clickable container, two icon-buttons inside
 *  for navigation. */
function MoverRow({ row, tone }: { row: TopMoverRow; tone: "up" | "down" }) {
  const positive = tone === "up";
  const textColor = positive
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-rose-600 dark:text-rose-400";
  const Icon = positive ? TrendingUp : TrendingDown;
  return (
    <div className="px-3 py-2 hover:bg-gray-50 dark:hover:bg-white/[0.04] transition flex items-center gap-2">
      <StockLogo symbol={row.symbol} name={row.name} size={32} shape="circle" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <p className="text-sm font-bold text-gray-900 dark:text-white truncate">
            {row.symbol}
          </p>
          <ChartButton symbol={row.symbol} />
        </div>
        <p className="text-[11px] text-gray-500 dark:text-gray-400 truncate" title={row.name || ""}>
          {row.name && row.name !== row.symbol ? row.name : fmtPrice(row.lastPrice)}
        </p>
      </div>
      <div className={`flex items-center gap-0.5 text-sm font-bold tabular-nums ${textColor} flex-shrink-0`}>
        <Icon className="w-3.5 h-3.5" />
        {fmtPct(row.pChange)}
      </div>
    </div>
  );
}

/** Header for a gainers / losers column. */
function ColumnHeader({ tone, count }: { tone: "up" | "down"; count?: number }) {
  const positive = tone === "up";
  const Icon = positive ? TrendingUp : TrendingDown;
  const cls = positive
    ? "bg-emerald-50/60 dark:bg-emerald-500/5 border-emerald-100 dark:border-emerald-500/15 text-emerald-700 dark:text-emerald-300"
    : "bg-rose-50/60 dark:bg-rose-500/5 border-rose-100 dark:border-rose-500/15 text-rose-700 dark:text-rose-300";
  return (
    <div className={`px-3 py-1.5 border-b flex items-center justify-between ${cls}`}>
      <div className="flex items-center gap-1.5">
        <Icon className="w-3.5 h-3.5" />
        <span className="text-[11px] font-bold uppercase tracking-wide">
          Top {positive ? "Gainers" : "Losers"}
        </span>
      </div>
      {count != null && (
        <span className="text-[10px] opacity-70">of {count}</span>
      )}
    </div>
  );
}

/** Empty placeholder column when a segment returns no rows. */
function EmptyColumn({ message, tone }: { message: string; tone: "up" | "down" }) {
  const cls = tone === "up"
    ? "text-emerald-700/60 dark:text-emerald-300/40"
    : "text-rose-700/60 dark:text-rose-300/40";
  return (
    <div className={`flex flex-col items-center justify-center py-8 px-4 text-center ${cls}`}>
      <AlertCircle className="w-5 h-5 mb-1 opacity-60" />
      <p className="text-xs">{message}</p>
    </div>
  );
}

/** Modal listing all rows for one side, opened via the "View all" link. */
function ViewAllModal({
  title, rows, tone, onClose,
}: {
  title: string; rows: TopMoverRow[]; tone: "up" | "down"; onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
         onClick={onClose}>
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-white/[0.08] shadow-2xl max-w-md w-full max-h-[80vh] overflow-hidden flex flex-col"
           onClick={e => e.stopPropagation()}>
        <div className="px-5 py-3 border-b border-gray-100 dark:border-white/[0.04] flex items-center justify-between">
          <h3 className="font-bold text-gray-900 dark:text-white text-sm">{title}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
            <XIcon className="w-4 h-4" />
          </button>
        </div>
        <div className="overflow-y-auto divide-y divide-gray-100 dark:divide-gray-700/60">
          {rows.length === 0 ? (
            <EmptyColumn tone={tone} message="No data" />
          ) : (
            rows.map((r, i) => <MoverRow key={`${r.symbol}-${i}`} row={r} tone={tone} />)
          )}
        </div>
      </div>
    </div>
  );
}


export default function TopMoversPanel() {
  const [segment, setSegment] = useState<Segment>("large");
  const [modal, setModal] = useState<null | "gainers" | "losers">(null);

  const { data, isLoading, error } = useQuery<TopMoversAllResponse>(
    marketDataQueryOptions<TopMoversAllResponse>(
      ["dashboard/top-movers/all"],
      () => api.topMoversAll(10),
    ),
  );

  const segData = data?.segments?.[segment];
  const gainers = segData?.gainers ?? [];
  const losers  = segData?.losers  ?? [];
  const inlineGainers = gainers.slice(0, INLINE_COUNT);
  const inlineLosers  = losers.slice(0, INLINE_COUNT);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-indigo-500" />
            <h2 className="text-sm font-bold text-gray-900 dark:text-white">Top Movers</h2>
            <span className="text-[11px] text-gray-500 dark:text-gray-400">
              Biggest gainers & losers, by market cap
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            {segData?.servedFrom === "DISK_EOD" && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200 dark:bg-slate-500/10 dark:text-slate-300 dark:border-slate-500/20"
                    title="Served from the sealed end-of-day close on disk — no network call.">
                EOD close
              </span>
            )}
            {segData?.servedFrom && segData.servedFrom !== "NSE" && segData.servedFrom !== "DISK_EOD" && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/20"
                    title={`NSE bulk index endpoint was unreachable; data fetched per-stock via ${segData.servedFrom}.`}>
                {segData.servedFrom} fallback
              </span>
            )}
            {segData && (
              <MarketStatePill state={segData.marketState} asOf={segData.asOf} />
            )}
          </div>
        </div>

        {/* Segment pills */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {SEGMENTS.map(s => {
            const active = segment === s.key;
            return (
              <button
                key={s.key}
                onClick={() => setSegment(s.key)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition border ${
                  active
                    ? "bg-indigo-600 text-white border-indigo-600 shadow-sm"
                    : "bg-gray-50 text-gray-600 border-gray-200 hover:bg-gray-100 hover:text-gray-900 dark:bg-gray-700/50 dark:text-gray-300 dark:border-gray-700 dark:hover:bg-gray-700"
                }`}
              >
                <span>{s.label}</span>
                <span className={`ml-1.5 text-[10px] ${active ? "opacity-80" : "text-gray-400 dark:text-gray-500"}`}>
                  {s.description}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Body */}
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-gray-100 dark:divide-gray-700">
          {(["up", "down"] as const).map((tone) => (
            <div key={tone}>
              <ColumnHeader tone={tone} />
              <div className="divide-y divide-gray-100 dark:divide-gray-700/60">
                {Array.from({ length: INLINE_COUNT }).map((_, i) => (
                  <div key={i} className="flex items-center justify-between px-4 py-2.5">
                    <div className="flex items-center gap-2 min-w-0">
                      <div className="h-3 w-20 bg-gray-100 dark:bg-gray-700 rounded animate-pulse" />
                    </div>
                    <div className="h-3 w-12 bg-gray-100 dark:bg-gray-700 rounded animate-pulse" />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="flex items-center justify-center py-12 text-rose-600 dark:text-rose-400">
          <AlertCircle className="w-5 h-5 mr-2" />
          <span className="text-sm">Could not load top movers.</span>
        </div>
      )}

      {!isLoading && !error && segData && (
        <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-gray-100 dark:divide-gray-700">
          {/* Gainers column */}
          <div>
            <ColumnHeader tone="up" count={gainers.length || undefined} />
            {inlineGainers.length === 0 ? (
              <EmptyColumn tone="up"
                  message={segData.message || "No gainers data right now."} />
            ) : (
              <>
                <div className="divide-y divide-gray-100 dark:divide-gray-700/60">
                  {inlineGainers.map((row, i) => (
                    <MoverRow key={`${row.symbol}-${i}`} row={row} tone="up" />
                  ))}
                </div>
                {gainers.length > INLINE_COUNT && (
                  <button
                    onClick={() => setModal("gainers")}
                    className="w-full text-center py-2 text-[11px] font-semibold text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50/50 dark:hover:bg-indigo-500/10 border-t border-gray-100 dark:border-gray-700/60 transition"
                  >
                    View all {gainers.length} →
                  </button>
                )}
              </>
            )}
          </div>

          {/* Losers column */}
          <div>
            <ColumnHeader tone="down" count={losers.length || undefined} />
            {inlineLosers.length === 0 ? (
              <EmptyColumn tone="down"
                  message={segData.message || "No losers data right now."} />
            ) : (
              <>
                <div className="divide-y divide-gray-100 dark:divide-gray-700/60">
                  {inlineLosers.map((row, i) => (
                    <MoverRow key={`${row.symbol}-${i}`} row={row} tone="down" />
                  ))}
                </div>
                {losers.length > INLINE_COUNT && (
                  <button
                    onClick={() => setModal("losers")}
                    className="w-full text-center py-2 text-[11px] font-semibold text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50/50 dark:hover:bg-indigo-500/10 border-t border-gray-100 dark:border-gray-700/60 transition"
                  >
                    View all {losers.length} →
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* "View all" modal */}
      {modal === "gainers" && (
        <ViewAllModal
          title={`${segData?.label ?? segment} · Top Gainers`}
          rows={gainers} tone="up"
          onClose={() => setModal(null)}
        />
      )}
      {modal === "losers" && (
        <ViewAllModal
          title={`${segData?.label ?? segment} · Top Losers`}
          rows={losers} tone="down"
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}
