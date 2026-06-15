import { useState, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import {
  PageHeader, Loading, EmptyState, ErrorState, PillTabs, MenuDropdown,
} from "../_shared";
import {
  Truck, Search, X, RefreshCw, ArrowUpRight, ArrowDownRight,
  TrendingUp, Package, Sparkles, IndianRupee, Layers,
  ListFilter, Check, Trophy, CalendarCheck,
} from "lucide-react";
import ChartButton from "@/components/ChartButton";
import StockLogo from "@/components/StockLogo";

interface DeliveryItem {
  symbol: string;
  name: string;
  exchange: string;
  ltp: number;
  prevClose: number;
  avgPrice: number;
  change: number;
  changePct: number;
  tradedQty: number;
  delivQty: number;
  delivPct: number;
  trades: number;
  turnover: number;       // in ₹
  delivValue: number;     // in ₹
  sector: string | null;
  sectors?: string[];   // NSE sector-index memberships (a stock can be in several)
  logo?: string;
}
interface DeliveryStats {
  avgDelivPct: number;
  totalTraded: number;
  totalDeliv: number;
  totalTurnover: number;
  totalDelivValue: number;
  delivRatio: number;
  sectorCount?: number;
}
interface SectorRow {
  sector: string;
  count: number;
  totalTraded: number;
  totalDeliv: number;
  totalTurnover: number;
  totalDelivValue: number;
  avgDelivPct: number;
  delivRatio: number;
  topSymbol: string | null;
  topDelivPct: number;
}
interface TopDeliveriesResponse {
  available: boolean;
  message?: string;
  items: DeliveryItem[];
  highlights: DeliveryItem[];
  sectors?: SectorRow[];
  totalSymbols: number;
  matched: number;
  tradeDate: string | null;
  sources: string[];
  indexCode: string;
  indexLabel: string;
  stats?: DeliveryStats;
}

const INDEX_OPTIONS = [
  // ── Broad market ──────────────────────────────────────────
  { value: "NIFTY50",              label: "Nifty 50" },
  { value: "NIFTYNEXT50",          label: "Nifty Next 50" },
  { value: "NIFTY100",             label: "Nifty 100" },
  { value: "NIFTY200",             label: "Nifty 200" },
  { value: "NIFTY500",             label: "Nifty 500" },
  // ── Mid-cap ───────────────────────────────────────────────
  { value: "NIFTYMIDCAP50",        label: "Nifty Midcap 50" },
  { value: "NIFTYMIDCAP100",       label: "Nifty Midcap 100" },
  { value: "NIFTYMIDCAP150",       label: "Nifty Midcap 150" },
  // ── Small-cap ─────────────────────────────────────────────
  { value: "NIFTYSMALLCAP50",      label: "Nifty Smallcap 50" },
  { value: "NIFTYSMALLCAP100",     label: "Nifty Smallcap 100" },
  { value: "NIFTYSMALLCAP250",     label: "Nifty Smallcap 250" },
  // ── Combined ──────────────────────────────────────────────
  { value: "NIFTYLARGEMIDCAP250",  label: "Nifty LargeMidcap 250" },
  { value: "FNO",                  label: "F&O Stocks" },
  { value: "ALL",                  label: "All Stocks" },
  // ── Sectoral ──────────────────────────────────────────────
  { value: "NIFTYBANK",            label: "Nifty Bank" },
  { value: "NIFTYIT",              label: "Nifty IT" },
  { value: "NIFTYAUTO",            label: "Nifty Auto" },
  { value: "NIFTYPHARMA",          label: "Nifty Pharma" },
  { value: "NIFTYFMCG",            label: "Nifty FMCG" },
  { value: "NIFTYMETAL",           label: "Nifty Metal" },
  { value: "NIFTYENERGY",          label: "Nifty Energy" },
  { value: "NIFTYREALTY",          label: "Nifty Realty" },
  { value: "NIFTYFINSERVICE",      label: "Nifty Fin Services" },
];

const SORT_OPTIONS = [
  { value: "delivPct",   label: "Delivery %" },
  { value: "delivQty",   label: "Delivered Qty" },
  { value: "delivValue", label: "Delivered Value" },
  { value: "turnover",   label: "Turnover" },
  { value: "changePct",  label: "% Change" },
];

const MIN_DELIV_OPTIONS = [
  { value: "0",  label: "All" },
  { value: "30", label: "≥ 30%" },
  { value: "50", label: "≥ 50%" },
  { value: "70", label: "≥ 70%" },
  { value: "85", label: "≥ 85%" },
];

/* ──────────────────────────── helpers ──────────────────────────── */

function fmtIndianNum(n: number): string {
  if (!isFinite(n) || n === 0) return "—";
  // Indian numbering: lakhs / crores
  if (n >= 1e7) return `${(n / 1e7).toFixed(2)} Cr`;
  if (n >= 1e5) return `${(n / 1e5).toFixed(2)} L`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)} K`;
  return n.toLocaleString("en-IN");
}
function fmtRupees(n: number): string {
  if (!isFinite(n) || n === 0) return "—";
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)} L`;
  return `₹${n.toLocaleString("en-IN")}`;
}
function fmtPrice(n: number): string {
  if (!isFinite(n)) return "—";
  return n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtDate(iso: string | null): string {
  if (!iso) return "Latest available";
  const d = new Date(iso + "T00:00:00");
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

/* ─────────────────────────── component ──────────────────────────── */

const SS_KEY = "topDeliveries_filters";
function loadFilters() {
  try { return JSON.parse(sessionStorage.getItem(SS_KEY) || "{}"); } catch { return {}; }
}

export default function TopDeliveries() {
  const _saved = loadFilters();
  const [indexCode, setIndexCode]   = useState(_saved.indexCode ?? "NIFTY50");
  const [sort, setSort]             = useState(_saved.sort ?? "delivPct");
  const [minPct, setMinPct]         = useState(_saved.minPct ?? "0");
  const [search, setSearch]         = useState(_saved.search ?? "");
  const [sectorFilter, setSectorFilter] = useState<string | null>(_saved.sectorFilter ?? null);

  // Persist filters to sessionStorage whenever they change
  useEffect(() => {
    sessionStorage.setItem(SS_KEY, JSON.stringify({ indexCode, sort, minPct, search, sectorFilter }));
  }, [indexCode, sort, minPct, search, sectorFilter]);

  // Reset sector filter whenever the underlying universe changes.
  const onIndexChange = (v: string) => { setSectorFilter(null); setIndexCode(v); };

  const params = new URLSearchParams();
  params.set("index", indexCode);
  params.set("sort", sort);
  params.set("minDelivPct", minPct);
  if (search) params.set("search", search);
  params.set("limit", "1000");

  const { data, isLoading, error, refetch, isFetching } = useQuery<TopDeliveriesResponse>({
    queryKey: ["insights/top-deliveries", indexCode, sort, minPct, search],
    queryFn: () => fetchApi(`/insights/top-deliveries?${params}`),
    staleTime: 10 * 60_000,
  });

  // Client-side sector slice — keeps the API call cheap and lets users
  // toggle sectors without a network round-trip.
  const visibleItems = sectorFilter && data?.items
    ? data.items.filter(it => (it.sectors || []).includes(sectorFilter))
    : (data?.items || []);

  const stocksRef = useRef<HTMLDivElement | null>(null);
  const scrollToStocks = () => {
    stocksRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div>
      <PageHeader
        title="Top Deliveries"
        info={
          data?.sources?.length
            ? `Long-term accumulation tracker — sources: ${data.sources.join(" + ")}`
            : "Stocks with the highest delivery percentage — institutional-conviction signal."
        }
        right={
          <div className="flex items-center gap-2">
            {data?.available && data.tradeDate && (
              <span
                className="inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-semibold rounded-lg bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30"
                title={`Official NSE end-of-day data for ${fmtDate(data.tradeDate)}. Delivery numbers are published by NSE only after market close, so this is the freshest data available.`}>
                <CalendarCheck className="w-3.5 h-3.5"/>
                EOD · {fmtDate(data.tradeDate)}
              </span>
            )}
            {data?.available && (
              <span className="hidden md:inline text-[11px] text-gray-500 dark:text-gray-400">
                <span className="font-semibold text-gray-900 dark:text-white">{data.matched.toLocaleString()}</span>
                {" / "}
                <span className="font-semibold text-gray-900 dark:text-white">{data.totalSymbols.toLocaleString()}</span>
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

      {/* Stats strip */}
      {data?.available && data.stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 mb-4">
          <StatTile
            icon={<TrendingUp className="w-4 h-4" />}
            label="Avg Delivery %"
            value={`${data.stats.avgDelivPct.toFixed(2)}%`}
            sub={`${data.indexLabel}`}
            color="text-violet-600 dark:text-violet-400"
            bg="bg-violet-500/10"
          />
          <StatTile
            icon={<Package className="w-4 h-4" />}
            label="Delivery Ratio"
            value={`${data.stats.delivRatio.toFixed(2)}%`}
            sub="Index aggregate"
            color="text-emerald-600 dark:text-emerald-400"
            bg="bg-emerald-500/10"
          />
          <StatTile
            icon={<IndianRupee className="w-4 h-4" />}
            label="Delivery Value"
            value={fmtRupees(data.stats.totalDelivValue)}
            sub="Held overnight"
            color="text-amber-600 dark:text-amber-400"
            bg="bg-amber-500/10"
          />
          <StatTile
            icon={<Sparkles className="w-4 h-4" />}
            label="Total Turnover"
            value={fmtRupees(data.stats.totalTurnover)}
            sub={`${fmtIndianNum(data.stats.totalTraded)} shares`}
            color="text-indigo-600 dark:text-indigo-400"
            bg="bg-indigo-500/10"
          />
        </div>
      )}

      {/* Top picks — slim inline strip, no header chrome */}
      {data?.highlights && data.highlights.length > 0 && (
        <div className="mb-4">
          <div className="flex items-center gap-1.5 mb-1.5 px-0.5">
            <Trophy className="w-3.5 h-3.5 text-amber-500"/>
            <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Top Picks
            </span>
            <span className="text-[11px] text-gray-400 dark:text-gray-500">
              · highest delivery % in {data.indexLabel}
            </span>
          </div>
          <div className="-mx-1 overflow-x-auto scrollbar-thin">
            <div className="flex gap-2.5 px-1 min-w-min">
              {data.highlights.map((it, i) => (
                <HighlightCard key={it.symbol} item={it} rank={i + 1}/>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Sector chip strip — always visible, single horizontal row */}
      {data?.sectors && data.sectors.length > 0 && (
        <SectorChipStrip
          sectors={data.sectors}
          activeSector={sectorFilter}
          onSelect={(s) => {
            setSectorFilter(prev => prev === s ? null : s);
            setTimeout(scrollToStocks, 60);
          }}
        />
      )}

      {/* Sector detail panel — appears when a chip is selected */}
      {sectorFilter && data?.sectors && (() => {
        const s = data.sectors.find(x => x.sector === sectorFilter);
        if (!s) return null;
        const totalDV = data.stats?.totalDelivValue || 0;
        const sharePct = totalDV > 0 ? (s.totalDelivValue / totalDV) * 100 : 0;
        return (
          <div className="mb-3 rounded-xl border border-violet-200 dark:border-violet-500/30 bg-gradient-to-br from-violet-50 to-white dark:from-violet-500/10 dark:to-gray-900/40 shadow-sm p-3">
            <div className="flex items-center justify-between gap-2 mb-2">
              <div className="flex items-center gap-2 min-w-0">
                <span className="inline-flex items-center justify-center w-6 h-6 rounded-md bg-violet-600 text-white">
                  <Layers className="w-3.5 h-3.5"/>
                </span>
                <div className="min-w-0">
                  <div className="text-sm font-bold text-gray-900 dark:text-white truncate">{s.sector}</div>
                  <div className="text-[11px] text-gray-500 dark:text-gray-400">
                    {s.count} stocks · {sharePct.toFixed(1)}% of {data.indexLabel} delivered value
                  </div>
                </div>
              </div>
              <button
                onClick={() => setSectorFilter(null)}
                className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium rounded-md bg-white dark:bg-gray-800/60 text-violet-700 dark:text-violet-300 border border-violet-200 dark:border-violet-500/30 hover:bg-violet-100 dark:hover:bg-violet-500/15 transition flex-shrink-0">
                <X className="w-2.5 h-2.5"/> Clear
              </button>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
              <SectorMetric label="Avg deliv %"  value={`${s.avgDelivPct.toFixed(1)}%`} accent/>
              <SectorMetric label="Deliv ratio"  value={`${s.delivRatio.toFixed(1)}%`}/>
              <SectorMetric label="Delivered"    value={`₹${fmtIndianNum(s.totalDelivValue)}`}/>
              <SectorMetric label="Turnover"     value={`₹${fmtIndianNum(s.totalTurnover)}`}/>
            </div>
            {s.topSymbol && (
              <div className="mt-2 pt-2 border-t border-violet-200/60 dark:border-violet-500/20 flex items-center justify-between text-[11px]">
                <span className="text-gray-500 dark:text-gray-400">Top stock in sector</span>
                <span className="font-bold text-gray-900 dark:text-white">
                  {s.topSymbol}
                  <span className="ml-1.5 text-violet-600 dark:text-violet-400">{s.topDelivPct.toFixed(1)}%</span>
                </span>
              </div>
            )}
          </div>
        );
      })()}

      {/* Stock list — main content */}
      <div ref={stocksRef} className="scroll-mt-4">
      <div className="flex items-center justify-between gap-2 mb-2 px-0.5">
        <div className="flex items-center gap-1.5 min-w-0">
          <ListFilter className="w-3.5 h-3.5 text-indigo-500 flex-shrink-0"/>
          <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Stocks
          </span>
          <span className="text-[11px] text-gray-400 dark:text-gray-500 truncate">
            {sectorFilter
              ? `· ${visibleItems.length} stocks in ${sectorFilter}`
              : `· every stock in ${data?.indexLabel || "the selected index"}`}
          </span>
        </div>
        {sectorFilter && (
          <button
            onClick={() => setSectorFilter(null)}
            className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium rounded-md bg-violet-100 dark:bg-violet-500/15 text-violet-700 dark:text-violet-300 border border-violet-200 dark:border-violet-500/30 hover:bg-violet-200 dark:hover:bg-violet-500/25 transition flex-shrink-0">
            <X className="w-2.5 h-2.5"/> Clear filter
          </button>
        )}
      </div>

      {/* Filter card */}
      <div className="mb-4 rounded-2xl border border-gray-200 dark:border-gray-700/60 bg-gradient-to-br from-white to-gray-50/40 dark:from-gray-800/80 dark:to-gray-900/40 backdrop-blur shadow-sm p-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[240px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500 pointer-events-none"/>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              aria-label="Search symbol or company"
              placeholder="Search symbol or company…"
              className="w-full text-sm bg-white dark:bg-gray-900/50 border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white rounded-xl pl-9 pr-9 py-2.5 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 placeholder:text-gray-400 dark:placeholder:text-gray-500 transition shadow-sm"
            />
            {search && (
              <button onClick={() => setSearch("")}
                aria-label="Clear search"
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700 dark:hover:text-gray-200 transition">
                <X className="w-3.5 h-3.5"/>
              </button>
            )}
          </div>
          <MenuDropdown
            label="Index"
            value={indexCode}
            options={INDEX_OPTIONS}
            onChange={onIndexChange}
          />
          <MenuDropdown
            label="Sort"
            value={sort}
            options={SORT_OPTIONS}
            onChange={setSort}
          />
          <PillTabs
            value={minPct}
            onChange={setMinPct}
            options={MIN_DELIV_OPTIONS}
          />
        </div>
      </div>

      {isLoading && <Loading label="Fetching delivery data…" />}
      {error && !isLoading && <ErrorState message={(error as Error).message} />}
      {!error && !isLoading && data?.available === false && (
        <EmptyState
          title="Feed unavailable"
          message={data.message || "Top deliveries feed temporarily unavailable."}
          icon={<Truck className="w-10 h-10"/>}/>
      )}
      {!isLoading && data?.available && data.items.length === 0 && (
        <EmptyState
          title="No matches"
          message={`No symbols match the selected filters in ${data.indexLabel}. Try lowering the delivery % threshold or selecting a wider index.`}
          icon={<Truck className="w-10 h-10"/>}/>
      )}
      {!isLoading && data?.available && data.items.length > 0 && visibleItems.length === 0 && (
        <EmptyState
          title={`No stocks in ${sectorFilter}`}
          message={`The current filters returned no stocks for the ${sectorFilter} sector. Clear the sector filter or relax the delivery threshold.`}
          icon={<Truck className="w-10 h-10"/>}/>
      )}

      {visibleItems.length > 0 && (
        <div className="space-y-2">
          {/* Header row (md+) */}
          <div className="hidden md:grid px-3 py-1.5 grid-cols-[44px_minmax(0,1.6fr)_90px_90px_120px_120px_minmax(0,200px)] gap-3 items-center text-[10px] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-medium">
            <span></span>
            <span>Stock</span>
            <span className="text-right">LTP</span>
            <span className="text-right">% Chg</span>
            <span className="text-right">Traded Qty</span>
            <span className="text-right">Delivered</span>
            <span>Delivery %</span>
          </div>
          <div className="space-y-1.5">
            {visibleItems.map(it => <DeliveryRow key={it.symbol} item={it}/>)}
          </div>
        </div>
      )}
      </div>
    </div>
  );
}

/* ──────────────────── sector chip strip ──────────────────── */

function SectorChipStrip({ sectors, activeSector, onSelect }: {
  sectors: SectorRow[]; activeSector: string | null;
  onSelect: (sector: string) => void;
}) {
  const stripRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll active chip into view when it changes.
  useEffect(() => {
    if (!activeSector || !stripRef.current) return;
    const el = stripRef.current.querySelector<HTMLElement>(`[data-sector="${CSS.escape(activeSector)}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  }, [activeSector]);

  return (
    <div className="mb-3">
      <div className="flex items-center gap-1.5 mb-1.5 px-0.5">
        <Layers className="w-3.5 h-3.5 text-violet-500"/>
        <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
          Filter by sector
        </span>
        <span className="text-[11px] text-gray-400 dark:text-gray-500">
          · {sectors.length} sectors · click any chip
        </span>
      </div>
      <div ref={stripRef}
        className="flex items-stretch gap-1.5 overflow-x-auto scrollbar-thin pb-1 -mx-1 px-1 snap-x">
        <button
          type="button"
          onClick={() => activeSector && onSelect(activeSector)}
          aria-pressed={!activeSector}
          className={`flex-shrink-0 snap-start inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12px] font-semibold border transition ${
            !activeSector
              ? "bg-indigo-600 text-white border-indigo-600 shadow-sm"
              : "bg-white dark:bg-gray-800/60 text-gray-700 dark:text-gray-200 border-gray-200 dark:border-gray-700/60 hover:border-indigo-400/60 hover:bg-indigo-50 dark:hover:bg-indigo-500/10"
          }`}>
          All
          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
            !activeSector ? "bg-white/20 text-white" : "bg-gray-100 dark:bg-gray-700/60 text-gray-500 dark:text-gray-400"
          }`}>
            {sectors.reduce((n, s) => n + s.count, 0)}
          </span>
        </button>
        {sectors.map(s => {
          const active = activeSector === s.sector;
          return (
            <button key={s.sector}
              data-sector={s.sector}
              type="button"
              onClick={() => onSelect(s.sector)}
              aria-pressed={active}
              title={`${s.sector} · avg ${s.avgDelivPct.toFixed(1)}% · ₹${fmtIndianNum(s.totalDelivValue)} delivered`}
              className={`flex-shrink-0 snap-start inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12px] font-semibold border transition ${
                active
                  ? "bg-violet-600 text-white border-violet-600 shadow-md ring-2 ring-violet-300 dark:ring-violet-500/40"
                  : "bg-white dark:bg-gray-800/60 text-gray-700 dark:text-gray-200 border-gray-200 dark:border-gray-700/60 hover:border-violet-400/60 hover:bg-violet-50 dark:hover:bg-violet-500/10"
              }`}>
              {active && <Check className="w-3 h-3 -ml-0.5"/>}
              <span className="truncate max-w-[160px]">{s.sector}</span>
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full tabular-nums ${
                active ? "bg-white/20 text-white" : "bg-violet-500/10 text-violet-700 dark:text-violet-300"
              }`}>
                {s.count}
              </span>
              <span className={`text-[10px] tabular-nums ${active ? "text-white/80" : "text-gray-400 dark:text-gray-500"}`}>
                {s.avgDelivPct.toFixed(0)}%
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ──────────────────────────── pieces ──────────────────────────── */

function StatTile({
  icon, label, value, sub, color, bg,
}: {
  icon: React.ReactNode; label: string; value: string; sub?: string;
  color: string; bg: string;
}) {
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700/60 bg-white dark:bg-gray-800/60 p-3 shadow-sm">
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400 font-medium">
        <span className={`p-1 rounded-md ${bg} ${color}`}>{icon}</span>
        {label}
      </div>
      <div className="mt-1.5">
        <div className="text-lg font-bold text-gray-900 dark:text-white tabular-nums truncate">{value}</div>
        {sub && <div className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5 truncate">{sub}</div>}
      </div>
    </div>
  );
}

function HighlightCard({ item, rank }: { item: DeliveryItem; rank: number }) {
  return (
    <div className="flex-shrink-0 w-[260px] rounded-xl border border-gray-200 dark:border-gray-700/60 bg-white dark:bg-gray-800/60 p-3 shadow-sm hover:shadow-md hover:border-violet-200 dark:hover:border-violet-500/40 transition">
      <div className="flex items-start gap-2.5">
        <div className="relative">
          <StockLogo symbol={item.symbol} size={36}/>
          <span className="absolute -top-1 -left-1 w-4 h-4 rounded-full bg-violet-500 text-white text-[9px] font-bold flex items-center justify-center shadow-sm">
            {rank}
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1 min-w-0">
            <span className="text-sm font-semibold text-gray-900 dark:text-white truncate" title={item.name}>
              {item.name}
            </span>
            <ChartButton symbol={item.symbol} />
          </div>
          <div className="text-[10px] text-gray-500 dark:text-gray-400 truncate">
            {item.symbol}{item.sector ? ` · ${item.sector}` : ""}
          </div>
        </div>
      </div>
      <div className="mt-2.5 flex items-baseline justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-medium">Delivery %</div>
          <div className="text-lg font-bold tabular-nums text-violet-600 dark:text-violet-400">
            {item.delivPct.toFixed(2)}%
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs tabular-nums text-gray-700 dark:text-gray-200">
            ₹{fmtPrice(item.ltp)}
          </div>
          <div className={`text-[11px] tabular-nums ${item.changePct >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
            {item.changePct >= 0 ? "+" : ""}{item.changePct.toFixed(2)}%
          </div>
        </div>
      </div>
      <DelivBar pct={item.delivPct} className="mt-2"/>
      <div className="mt-2 flex justify-between text-[10px] text-gray-500 dark:text-gray-400">
        <span>{fmtIndianNum(item.delivQty)} delivered</span>
        <span>of {fmtIndianNum(item.tradedQty)}</span>
      </div>
    </div>
  );
}

function DeliveryRow({ item }: { item: DeliveryItem }) {
  return (
    <div role="row"
      className="group rounded-xl border border-gray-200 dark:border-gray-700/60 bg-white dark:bg-gray-800/60 shadow-sm hover:border-violet-200 dark:hover:border-violet-500/40 hover:shadow-md transition px-3 py-2.5 grid grid-cols-[44px_minmax(0,1fr)_auto] md:grid-cols-[44px_minmax(0,1.6fr)_90px_90px_120px_120px_minmax(0,200px)] gap-3 items-center"
    >
      <StockLogo logo={item.logo} symbol={item.symbol} size={36}/>

      <div className="min-w-0">
        <div className="flex items-center gap-1 min-w-0">
          <span className="text-sm font-semibold text-gray-900 dark:text-white truncate" title={item.name}>{item.name}</span>
          <ChartButton symbol={item.symbol} />
        </div>
        <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">
          {item.symbol} · {item.exchange}
          {item.sector && <span className="hidden lg:inline"> · {item.sector}</span>}
          <span className="md:hidden"> · {item.delivPct.toFixed(1)}% deliv</span>
        </div>
      </div>

      <div className="hidden md:block text-right text-xs text-gray-700 dark:text-gray-200 tabular-nums">
        ₹{fmtPrice(item.ltp)}
      </div>

      <div className={`hidden md:flex items-center justify-end gap-0.5 text-xs tabular-nums font-medium ${item.changePct >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
        {item.changePct >= 0 ? <ArrowUpRight className="w-3 h-3"/> : <ArrowDownRight className="w-3 h-3"/>}
        {item.changePct >= 0 ? "+" : ""}{item.changePct.toFixed(2)}%
      </div>

      <div className="hidden md:block text-right text-xs text-gray-500 dark:text-gray-400 tabular-nums">
        {fmtIndianNum(item.tradedQty)}
      </div>

      <div className="hidden md:block text-right text-xs text-gray-700 dark:text-gray-200 tabular-nums">
        <div>{fmtIndianNum(item.delivQty)}</div>
        <div className="text-[10px] text-gray-500 dark:text-gray-400">{fmtRupees(item.delivValue)}</div>
      </div>

      <div className="hidden md:flex items-center gap-2 min-w-0">
        <span className={`text-xs tabular-nums font-bold flex-shrink-0 w-12 text-right ${
          item.delivPct >= 70
            ? "text-violet-600 dark:text-violet-400"
            : item.delivPct >= 50
              ? "text-indigo-600 dark:text-indigo-400"
              : "text-gray-700 dark:text-gray-200"
        }`}>
          {item.delivPct.toFixed(1)}%
        </span>
        <DelivBar pct={item.delivPct} className="flex-1"/>
      </div>

      {/* Mobile right column */}
      <div className="md:hidden text-right">
        <div className="text-xs font-bold tabular-nums text-violet-600 dark:text-violet-400">
          {item.delivPct.toFixed(1)}%
        </div>
        <div className={`mt-0.5 text-[11px] tabular-nums ${item.changePct >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
          {item.changePct >= 0 ? "+" : ""}{item.changePct.toFixed(2)}%
        </div>
      </div>
    </div>
  );
}

function DelivBar({ pct, className = "" }: { pct: number; className?: string }) {
  const clamped = Math.max(0, Math.min(pct, 100));
  const color = pct >= 70
    ? "bg-violet-500"
    : pct >= 50
      ? "bg-indigo-500"
      : "bg-gray-400 dark:bg-gray-500";
  return (
    <div role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}
      aria-label={`Delivery percentage ${pct.toFixed(1)}%`}
      className={`h-1.5 rounded-full bg-gray-200 dark:bg-gray-700/60 overflow-hidden ${className}`}>
      <div className={`h-full ${color} transition-all`} style={{ width: `${clamped}%` }}/>
    </div>
  );
}

function SectorMetric({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-lg bg-white/70 dark:bg-gray-900/40 border border-violet-200/60 dark:border-violet-500/20 px-2.5 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400">{label}</div>
      <div className={`text-sm font-bold tabular-nums ${accent ? "text-violet-700 dark:text-violet-300" : "text-gray-900 dark:text-white"}`}>
        {value}
      </div>
    </div>
  );
}

// StockLogo moved to `@/components/StockLogo` — same call signature, so
// no changes at the call sites above.
