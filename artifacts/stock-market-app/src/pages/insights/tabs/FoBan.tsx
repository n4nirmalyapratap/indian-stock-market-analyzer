import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import {
  PageHeader, Loading, EmptyState, ErrorState, PillTabs,
} from "../_shared";
import {
  Ban, Search, X, RefreshCw, AlertTriangle, ArrowUpRight, ArrowDownRight,
} from "lucide-react";

interface FoBanItem {
  symbol: string;
  name: string;
  exchange: string;
  isin?: string | null;
  ltp: number | null;
  change: number | null;
  changePct: number | null;
  prevMwplPct: number | null;
  currentMwplPct: number | null;
  logo?: string;
  status: "Banned" | "Possible Entrant" | "Possible Exit" | "Watch";
}
interface FoBanResponse {
  available: boolean;
  message?: string;
  items: FoBanItem[];
  highlights: FoBanItem[];
  totalSymbols: number;
  matched: number;
  bannedCount: number;
  tradeDate: string | null;
  sources?: string[];
}

const STATUS_TABS = [
  { value: "",                  label: "All" },
  { value: "Banned",            label: "Banned" },
  { value: "Possible Entrant",  label: "Entrants" },
  { value: "Possible Exit",     label: "Exits" },
];

function fmt(v: number | null | undefined, digits = 2): string {
  if (v == null || !isFinite(v)) return "—";
  return v.toFixed(digits);
}
function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

export default function FoBan() {
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");

  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (search) params.set("search", search);
  params.set("limit", "300");

  const { data, isLoading, error, refetch, isFetching } = useQuery<FoBanResponse>({
    queryKey: ["insights/fo-ban", status, search],
    queryFn: () => fetchApi(`/insights/fo-ban?${params}`),
    staleTime: 5 * 60_000,
  });

  return (
    <div>
      <PageHeader
        title="F&O Ban — MWPL Tracker"
        info={
          data?.sources && data.sources.length
            ? `MWPL & ban-list status — sources: ${data.sources.join(" + ")}`
            : "Market Wide Position Limit usage — entering / exiting the F&O ban list"
        }
        right={
          <div className="flex items-center gap-3">
            {data?.available && (
              <span className="text-[11px] text-gray-500 dark:text-gray-400">
                <span className="font-semibold text-rose-600 dark:text-rose-400">{data.bannedCount}</span> banned
                {" · "}
                <span className="font-semibold text-gray-900 dark:text-white">{data.matched.toLocaleString()}</span>
                {" of "}
                <span className="font-semibold text-gray-900 dark:text-white">{data.totalSymbols.toLocaleString()}</span>
                {data.tradeDate && (
                  <span className="hidden sm:inline ml-1.5">· {fmtDate(data.tradeDate)}</span>
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

      {/* Highlights — top 5 most-stressed names */}
      {data?.highlights && data.highlights.length > 0 && (
        <div className="mb-4 -mx-1 overflow-x-auto scrollbar-thin">
          <div className="flex gap-2.5 px-1 min-w-min">
            {data.highlights.map(it => <HighlightCard key={it.symbol} item={it}/>)}
          </div>
        </div>
      )}

      {/* Filter card */}
      <div className="mb-4 rounded-2xl border border-gray-200 dark:border-gray-700/60 bg-gradient-to-br from-white to-gray-50/40 dark:from-gray-800/80 dark:to-gray-900/40 backdrop-blur shadow-sm p-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[260px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500 pointer-events-none"/>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search symbol or company…"
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
          <PillTabs value={status} onChange={setStatus} options={STATUS_TABS} />
        </div>
      </div>

      {isLoading && <Loading label="Fetching MWPL & ban-list data…" />}
      {error && !isLoading && <ErrorState message={(error as Error).message} />}
      {!error && !isLoading && data?.available === false && (
        <EmptyState
          title="Feed unavailable"
          message={data.message || "F&O ban / MWPL feed temporarily unavailable."}
          icon={<Ban className="w-10 h-10"/>}/>
      )}
      {!isLoading && data?.available && data.items.length === 0 && (
        <EmptyState
          title="No matches"
          message="No symbols match the selected filters."
          icon={<Ban className="w-10 h-10"/>}/>
      )}

      {data?.items && data.items.length > 0 && (
        <div role="table" aria-label="F&O ban and MWPL list" className="space-y-2">
          {/* Column header strip */}
          <div role="row" className="hidden md:grid px-3 py-1.5 grid-cols-[44px_minmax(0,1.5fr)_120px_90px_80px_90px_180px] gap-3 items-center text-[10px] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-medium">
            <span></span>
            <span role="columnheader">Stock</span>
            <span role="columnheader">Status</span>
            <span role="columnheader" className="text-right">LTP</span>
            <span role="columnheader" className="text-right">% Chg</span>
            <span role="columnheader" className="text-right">Prev MWPL</span>
            <span role="columnheader">Current MWPL</span>
          </div>
          <div role="rowgroup" className="space-y-1.5">
            {data.items.map(it => <FoBanRow key={it.symbol} item={it}/>)}
          </div>
        </div>
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────── */

function HighlightCard({ item }: { item: FoBanItem }) {
  const cur = item.currentMwplPct ?? 0;
  const stressed = cur >= 95;
  return (
    <div className="flex-shrink-0 w-[240px] rounded-xl border border-gray-200 dark:border-gray-700/60 bg-white dark:bg-gray-800/60 p-3 shadow-sm hover:shadow-md hover:border-indigo-200 dark:hover:border-indigo-500/40 transition">
      <div className="flex items-start gap-2.5">
        <StockLogo logo={item.logo} symbol={item.symbol} size={36}/>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-gray-900 dark:text-white truncate" title={item.name}>
            {item.name}
          </div>
          <div className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5">{item.symbol} · {item.exchange}</div>
        </div>
        <StatusPill status={item.status}/>
      </div>
      <div className="mt-2.5">
        <div className="text-[10px] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-medium">Current MWPL</div>
        <div className="flex items-baseline justify-between mt-0.5">
          <div className={`text-base font-bold tabular-nums ${stressed ? "text-rose-600 dark:text-rose-400" : "text-amber-600 dark:text-amber-400"}`}>
            {fmt(item.currentMwplPct, 2)}%
          </div>
          {item.changePct != null && (
            <div className={`text-xs tabular-nums ${item.changePct >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
              {item.changePct >= 0 ? "+" : ""}{item.changePct.toFixed(2)}%
            </div>
          )}
        </div>
        <MwplBar pct={item.currentMwplPct ?? 0} className="mt-2"/>
      </div>
    </div>
  );
}

function FoBanRow({ item }: { item: FoBanItem }) {
  const chg = item.changePct ?? 0;
  return (
    <div role="row"
      className="group rounded-xl border border-gray-200 dark:border-gray-700/60 bg-white dark:bg-gray-800/60 shadow-sm hover:border-indigo-200 dark:hover:border-indigo-500/40 hover:shadow-md transition px-3 py-2.5 grid grid-cols-[44px_minmax(0,1fr)_auto] md:grid-cols-[44px_minmax(0,1.5fr)_120px_90px_80px_90px_180px] gap-3 items-center"
    >
      <StockLogo logo={item.logo} symbol={item.symbol} size={36}/>
      <div className="min-w-0">
        <div className="text-sm font-semibold text-gray-900 dark:text-white truncate" title={item.name}>{item.name}</div>
        <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">
          {item.symbol} · {item.exchange}
          <span className="md:hidden"> · MWPL {fmt(item.currentMwplPct, 1)}%</span>
        </div>
      </div>

      {/* Status (mobile shows on right) */}
      <div className="hidden md:block">
        <StatusPill status={item.status}/>
      </div>

      <div className="hidden md:block text-right text-xs text-gray-700 dark:text-gray-200 tabular-nums">
        {item.ltp != null ? `₹${fmt(item.ltp)}` : "—"}
      </div>
      <div className={`hidden md:block text-right text-xs tabular-nums font-medium ${chg >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
        {item.changePct != null
          ? <span className="inline-flex items-center gap-0.5 justify-end">
              {chg >= 0 ? <ArrowUpRight className="w-3 h-3"/> : <ArrowDownRight className="w-3 h-3"/>}
              {chg >= 0 ? "+" : ""}{chg.toFixed(2)}%
            </span>
          : "—"}
      </div>
      <div className="hidden md:block text-right text-xs text-gray-500 dark:text-gray-400 tabular-nums">
        {fmt(item.prevMwplPct, 1)}%
      </div>
      <div className="hidden md:flex items-center gap-2 min-w-0">
        <span className={`text-xs tabular-nums font-bold flex-shrink-0 w-12 text-right ${
          (item.currentMwplPct ?? 0) >= 95
            ? "text-rose-600 dark:text-rose-400"
            : (item.currentMwplPct ?? 0) >= 80
              ? "text-amber-600 dark:text-amber-400"
              : "text-gray-700 dark:text-gray-200"
        }`}>
          {fmt(item.currentMwplPct, 1)}%
        </span>
        <MwplBar pct={item.currentMwplPct ?? 0} className="flex-1"/>
      </div>

      {/* Mobile: status + change */}
      <div className="md:hidden text-right">
        <StatusPill status={item.status}/>
        {item.changePct != null && (
          <div className={`mt-1 text-xs tabular-nums ${chg >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
            {chg >= 0 ? "+" : ""}{chg.toFixed(2)}%
          </div>
        )}
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: FoBanItem["status"] }) {
  const map: Record<string, string> = {
    "Banned":           "bg-rose-500/10 text-rose-700 dark:text-rose-400 border-rose-500/20",
    "Possible Entrant": "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/20",
    "Possible Exit":    "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20",
    "Watch":            "bg-gray-500/10 text-gray-600 dark:text-gray-400 border-gray-500/20",
  };
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wide border ${map[status]}`}>
      {status === "Banned" && <AlertTriangle className="w-3 h-3"/>}
      {status}
    </span>
  );
}

function MwplBar({ pct, className = "" }: { pct: number; className?: string }) {
  // Bar fills at most 100% width; values >100 are clamped but tagged red.
  const clamped = Math.max(0, Math.min(pct, 100));
  const color = pct >= 95
    ? "bg-rose-500"
    : pct >= 80
      ? "bg-amber-500"
      : "bg-indigo-500";
  return (
    <div role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}
      aria-label={`MWPL ${pct.toFixed(1)}%`}
      className={`h-1.5 rounded-full bg-gray-200 dark:bg-gray-700/60 overflow-hidden ${className}`}>
      <div className={`h-full ${color} transition-all`} style={{ width: `${clamped}%` }}/>
    </div>
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
    <img src={logo} alt={symbol} loading="lazy" onError={() => setErr(true)}
      style={{ width: size, height: size }}
      className="rounded-lg object-contain bg-white border border-gray-200 dark:border-gray-700 p-0.5 flex-shrink-0"/>
  );
}
