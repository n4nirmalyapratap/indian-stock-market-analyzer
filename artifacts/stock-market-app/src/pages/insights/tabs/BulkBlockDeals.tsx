import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import {
  PageHeader, Loading, EmptyState, ErrorState, PillTabs,
} from "../_shared";
import {
  Briefcase, Search, X, ArrowUpRight, ArrowDownRight, RefreshCw, TrendingUp, Calendar,
} from "lucide-react";
import ChartButton from "@/components/ChartButton";

interface Deal {
  date: string;
  exchange: string;
  symbol: string;
  company: string;
  dealType: "BULK" | "BLOCK";
  client: string;
  side: "BUY" | "SELL";
  qty: number;
  avgPrice: number;
  valueRs: number;
  logo: string;
  source?: "NSE" | "SCANX" | string;
}
interface DealsResponse {
  available: boolean;
  message?: string;
  items: Deal[];
  highlights: Deal[];
  totalDeals: number;
  matched: number;
  dateRange: { from: string | null; to: string | null };
  sources?: string[];
}

const SIDE_TABS = [
  { value: "",     label: "All deals" },
  { value: "BUY",  label: "Buy" },
  { value: "SELL", label: "Sell" },
];

const DEAL_TYPE_TABS = [
  { value: "",      label: "All" },
  { value: "BULK",  label: "Bulk only" },
  { value: "BLOCK", label: "Block only" },
];

function fmtCr(rs: number): string {
  if (!isFinite(rs)) return "—";
  return `₹${(rs / 1e7).toFixed(2)} Cr`;
}
function fmtQty(n: number): string {
  // Indian numbering: 12,34,567
  return n.toLocaleString("en-IN");
}
function fmtDate(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

export default function BulkBlockDeals() {
  const [side, setSide] = useState("");
  const [dealType, setDealType] = useState("");
  const [search, setSearch] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const params = new URLSearchParams();
  if (side) params.set("side", side);
  if (dealType) params.set("deal_type", dealType);
  if (search) params.set("search", search);
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  params.set("limit", "500");

  const { data, isLoading, error, refetch, isFetching } = useQuery<DealsResponse>({
    queryKey: ["insights/bulk-block-deals", side, dealType, search, startDate, endDate],
    queryFn: () => fetchApi(`/insights/bulk-block-deals?${params}`),
    staleTime: 15 * 60_000,
  });

  const dateMin = data?.dateRange.from || undefined;
  const dateMax = data?.dateRange.to || undefined;
  const hasDates = !!(startDate || endDate);

  return (
    <div>
      <PageHeader
        title="Bulk & Block Deals"
        info={
          data?.sources && data.sources.length
            ? `Large single-trade disclosures under SEBI rules — sources: ${data.sources.join(" + ")}`
            : "Large single-trade transactions disclosed under SEBI rules (NSE & BSE EOD)"
        }
        right={
          <div className="flex items-center gap-3">
            {data?.available && (
              <span className="text-[11px] text-gray-500 dark:text-gray-400">
                <span className="font-semibold text-gray-900 dark:text-white">{data.matched.toLocaleString()}</span>
                {" of "}
                <span className="font-semibold text-gray-900 dark:text-white">{data.totalDeals.toLocaleString()}</span>
                {" deals"}
                {data.dateRange.from && (
                  <span className="ml-1.5 hidden sm:inline">· {fmtDate(data.dateRange.from)} → {fmtDate(data.dateRange.to || "")}</span>
                )}
              </span>
            )}
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-60"
              title="Refresh">
              <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? "animate-spin" : ""}`} />
              Refresh
            </button>
          </div>
        }
      />

      {/* Highlights strip — biggest 5 deals as horizontally-scrolling cards */}
      {data?.highlights && data.highlights.length > 0 && (
        <div className="mb-4 -mx-1 overflow-x-auto scrollbar-thin">
          <div className="flex gap-2.5 px-1 min-w-min">
            {data.highlights.map((d, i) => <HighlightCard key={i} deal={d}/>)}
          </div>
        </div>
      )}

      {/* Filter card — side pills + deal-type pills + search */}
      <div className="mb-4 rounded-2xl border border-gray-200 dark:border-gray-700/60 bg-gradient-to-br from-white to-gray-50/40 dark:from-gray-800/80 dark:to-gray-900/40 backdrop-blur shadow-sm p-2.5">
        <div className="flex flex-wrap items-center gap-2">
          {/* Search */}
          <div className="relative flex-1 min-w-[260px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500 pointer-events-none"/>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search stock or client (e.g. HFCL, Goldman, Norges Bank)…"
              className="w-full text-sm bg-white dark:bg-gray-900/50 border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white rounded-xl pl-9 pr-9 py-2.5 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 placeholder:text-gray-400 dark:placeholder:text-gray-500 transition shadow-sm"
            />
            {search && (
              <button onClick={() => setSearch("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700 dark:hover:text-gray-200 transition"
                title="Clear">
                <X className="w-3.5 h-3.5"/>
              </button>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <PillTabs value={side} onChange={setSide} options={SIDE_TABS} />
            <PillTabs value={dealType} onChange={setDealType} options={DEAL_TYPE_TABS} />
          </div>
        </div>
        {/* Duration row */}
        <div className="mt-2 flex flex-wrap items-center gap-2 px-1">
          <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-gray-500 dark:text-gray-400">
            <Calendar className="w-3.5 h-3.5"/> Duration
          </span>
          <div className="flex items-center gap-1.5">
            <input
              type="date" value={startDate} min={dateMin} max={dateMax}
              onChange={e => setStartDate(e.target.value)}
              className="text-xs bg-white dark:bg-gray-900/50 border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white rounded-lg px-2 py-1 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/30"
              aria-label="Start date"
            />
            <span className="text-gray-400 dark:text-gray-500 text-xs">→</span>
            <input
              type="date" value={endDate} min={startDate || dateMin} max={dateMax}
              onChange={e => setEndDate(e.target.value)}
              className="text-xs bg-white dark:bg-gray-900/50 border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white rounded-lg px-2 py-1 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/30"
              aria-label="End date"
            />
          </div>
          {hasDates && (
            <button
              onClick={() => { setStartDate(""); setEndDate(""); }}
              className="inline-flex items-center gap-1 text-[11px] font-medium text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 px-1.5 py-1 rounded transition"
            >
              <X className="w-3 h-3"/> Clear dates
            </button>
          )}
          {dateMin && dateMax && !hasDates && (
            <span className="text-[10px] text-gray-400 dark:text-gray-500">
              Available: {fmtDate(dateMin)} → {fmtDate(dateMax)}
            </span>
          )}
        </div>
      </div>

      {isLoading && <Loading label="Fetching latest bulk/block deals…" />}
      {error && !isLoading && <ErrorState message={(error as Error).message} />}
      {!error && !isLoading && data?.available === false && (
        <EmptyState title="Feed unavailable"
          message={data.message || "Bulk/block deals feed temporarily unavailable."}
          icon={<Briefcase className="w-10 h-10"/>}/>
      )}
      {!isLoading && data?.available && data.items.length === 0 && (
        <EmptyState title="No deals" message="No deals match the selected filters."
          icon={<Briefcase className="w-10 h-10"/>}/>
      )}

      {data?.items && data.items.length > 0 && (
        <div role="table" aria-label="Bulk and block deals" className="space-y-2">
          {/* Column header strip — aligns with the row grid below */}
          <div role="row" className="hidden md:grid px-3 py-1.5 grid-cols-[44px_minmax(0,1.5fr)_92px_minmax(0,1.4fr)_72px_110px_110px_110px] gap-3 items-center text-[10px] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-medium">
            <span role="columnheader" aria-label="Logo"></span>
            <span role="columnheader">Stock</span>
            <span role="columnheader">Date</span>
            <span role="columnheader">Client</span>
            <span role="columnheader">Action</span>
            <span role="columnheader" className="text-right">Qty</span>
            <span role="columnheader" className="text-right">Avg price</span>
            <span role="columnheader" className="text-right">Value</span>
          </div>

          <div role="rowgroup" className="space-y-1.5">
            {data.items.map((d, i) => <DealRow key={i} deal={d}/>)}
          </div>
        </div>
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────── */

function HighlightCard({ deal }: { deal: Deal }) {
  const buy = deal.side === "BUY";
  return (
    <div className="flex-shrink-0 w-[260px] rounded-xl border border-gray-200 dark:border-gray-700/60 bg-white dark:bg-gray-800/60 p-3 shadow-sm hover:shadow-md hover:border-indigo-200 dark:hover:border-indigo-500/40 transition">
      <div className="flex items-start gap-2.5">
        <StockLogo logo={deal.logo} symbol={deal.symbol} size={36}/>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-1">
            <div className="flex items-center gap-1 min-w-0">
              <span className="text-sm font-semibold text-gray-900 dark:text-white truncate" title={deal.company}>
                {deal.company}
              </span>
              {deal.symbol && <ChartButton symbol={deal.symbol} />}
            </div>
            <SideBadge side={deal.side}/>
          </div>
          <div className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5 flex items-center gap-1">
            <DealTypePill type={deal.dealType}/>
            <span>·</span>
            <span>{fmtDate(deal.date)}</span>
          </div>
        </div>
      </div>
      <div className="mt-2.5 flex items-baseline justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-medium">Deal size</div>
          <div className={`text-base font-bold tabular-nums ${buy ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
            {fmtCr(deal.valueRs)}
          </div>
        </div>
        <TrendingUp className={`w-4 h-4 ${buy ? "text-emerald-500" : "text-rose-500 rotate-180"}`}/>
      </div>
      <div className="mt-1.5 text-[11px] text-gray-500 dark:text-gray-400 truncate" title={deal.client}>
        by {toTitleCase(deal.client)}
      </div>
    </div>
  );
}

function DealRow({ deal }: { deal: Deal }) {
  return (
    <div role="row"
      className="group rounded-xl border border-gray-200 dark:border-gray-700/60 bg-white dark:bg-gray-800/60 shadow-sm hover:border-indigo-200 dark:hover:border-indigo-500/40 hover:shadow-md transition px-3 py-2.5 grid grid-cols-[44px_minmax(0,1fr)_auto] md:grid-cols-[44px_minmax(0,1.5fr)_92px_minmax(0,1.4fr)_72px_110px_110px_110px] gap-3 items-center"
    >
      <StockLogo logo={deal.logo} symbol={deal.symbol} size={36}/>
      <div className="min-w-0">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="text-sm font-semibold text-gray-900 dark:text-white truncate" title={deal.company}>
            {deal.company}
          </span>
          <DealTypePill type={deal.dealType}/>
          {deal.symbol && <ChartButton symbol={deal.symbol} />}
        </div>
        <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">
          {deal.symbol} · {deal.exchange}
          <span className="md:hidden"> · {fmtDate(deal.date)}</span>
        </div>
      </div>

      {/* Date */}
      <div className="hidden md:block text-xs text-gray-600 dark:text-gray-300 whitespace-nowrap">
        {fmtDate(deal.date)}
      </div>

      {/* Client */}
      <div className="hidden md:block text-xs text-gray-700 dark:text-gray-200 truncate" title={deal.client}>
        {toTitleCase(deal.client)}
      </div>

      {/* Action */}
      <div className="hidden md:block">
        <SideBadge side={deal.side}/>
      </div>

      {/* Qty */}
      <div className="hidden md:block text-right text-xs text-gray-700 dark:text-gray-200 tabular-nums">
        {fmtQty(deal.qty)}
      </div>

      {/* Avg price */}
      <div className="hidden md:block text-right text-xs text-gray-700 dark:text-gray-200 tabular-nums">
        ₹{deal.avgPrice.toFixed(2)}
      </div>

      {/* Value */}
      <div className="hidden md:block text-right">
        <div className={`text-sm font-bold tabular-nums ${deal.side === "BUY" ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
          {fmtCr(deal.valueRs)}
        </div>
      </div>

      {/* Mobile-only: side + value */}
      <div className="md:hidden text-right">
        <div className={`text-sm font-bold tabular-nums ${deal.side === "BUY" ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
          {fmtCr(deal.valueRs)}
        </div>
        <SideBadge side={deal.side}/>
      </div>
    </div>
  );
}

function SideBadge({ side }: { side: "BUY" | "SELL" }) {
  const buy = side === "BUY";
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wide ${
      buy
        ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20"
        : "bg-rose-500/10 text-rose-700 dark:text-rose-400 border border-rose-500/20"
    }`}>
      {buy ? <ArrowUpRight className="w-3 h-3"/> : <ArrowDownRight className="w-3 h-3"/>}
      {side}
    </span>
  );
}

function DealTypePill({ type }: { type: "BULK" | "BLOCK" }) {
  const block = type === "BLOCK";
  return (
    <span className={`inline-block px-1.5 py-px rounded text-[9px] font-bold tracking-wider uppercase flex-shrink-0 ${
      block
        ? "bg-violet-500/10 text-violet-700 dark:text-violet-400 border border-violet-500/20"
        : "bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/20"
    }`}>
      {type}
    </span>
  );
}

function StockLogo({ logo, symbol, size = 32 }: { logo?: string; symbol: string; size?: number }) {
  const [err, setErr] = useState(false);
  const initial = (symbol || "?").slice(0, 2).toUpperCase();
  if (err || !logo) return (
    <div style={{ width: size, height: size }}
      className="rounded-lg flex items-center justify-center text-[10px] font-bold text-white bg-gradient-to-br from-indigo-500 to-violet-600 flex-shrink-0">
      {initial}
    </div>
  );
  return (
    <img
      src={logo} alt={symbol} loading="lazy"
      onError={() => setErr(true)}
      style={{ width: size, height: size }}
      className="rounded-lg object-contain bg-white border border-gray-200 dark:border-gray-700 p-0.5 flex-shrink-0"/>
  );
}

function toTitleCase(s: string): string {
  return (s || "").toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
}
