import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import {
  PageHeader, Loading, EmptyState, MenuDropdown, ErrorState,
  PillTabs, useChartPalette,
} from "../_shared";
import {
  PieChart, ChevronDown, ExternalLink, RefreshCw, TrendingUp, TrendingDown,
  ArrowUpRight, ArrowDownRight, Sparkles, Building2, Search, Layers, X,
} from "lucide-react";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend,
} from "recharts";

interface Scheme {
  schemeCode: string;
  isin: string;
  schemeName: string;
  nav: number | null;
  date: string;
  amc: string;
  category: string;
  assetClass: string;
  subCategory: string;
  openEnded: boolean;
  amcLogo?: string;
  seo?: string;
}
interface HoldingRow {
  symbol: string;
  name: string;
  isin: string;
  sector: string;
  subSector: string;
  action: string;
  latestPct: number | null;
  series: number[];
  months: string[];
  logo: string;
}
interface HoldingCategory { name: string; rows: HoldingRow[]; }
interface Holdings { months: string[]; categories: HoldingCategory[]; }
interface MfResponse {
  available: boolean;
  source?: string;
  message?: string;
  totalSchemes?: number;
  matched?: number;
  items: Scheme[];
  amcs?: string[];
  assetClasses?: string[];
  subCategoriesByClass?: Record<string, string[]>;
}
interface SchemeDetail {
  available: boolean;
  message?: string;
  schemeCode?: string;
  meta?: {
    schemeName: string; fundHouse: string; schemeType: string;
    schemeCategory: string; isinGrowth: string; isinDivReinvestment: string;
  };
  latest?: { nav: number; date: string };
  returns?: Record<string, number | null | string>;
  risk?: { alpha?: number; beta?: number; stdDev?: number; sharpe?: number; maxDrawdown?: number };
  navChart?: { date: string; nav: number; navIdx: number }[];
  benchmarkChart?: { date: string; benchIdx: number }[];
  benchmarkLabel?: string | null;
  factsheetUrl?: string;
  amcLogo?: string;
  holdings?: Holdings;
  holdingsSource?: string | null;
}

const ASSET_TABS = [
  { value: "", label: "All" },
  { value: "Equity", label: "Equity" },
  { value: "Debt", label: "Debt" },
  { value: "Hybrid", label: "Hybrid" },
  { value: "Index / ETF", label: "Index / ETF" },
  { value: "Solution Oriented", label: "Solution" },
  { value: "Other", label: "Other" },
];

function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v == null || !isFinite(v as number)) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${(v as number).toFixed(digits)}%`;
}
function pctClass(v: number | null | undefined): string {
  if (v == null) return "text-gray-500 dark:text-gray-400";
  return v >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400";
}
function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null || !isFinite(v as number)) return "—";
  return (v as number).toFixed(digits);
}

export default function MfHoldings() {
  const [assetClass, setAssetClass] = useState("");
  const [subCategory, setSubCategory] = useState("");
  const [amc, setAmc] = useState("");
  const [search, setSearch] = useState("");
  const [openOnly, setOpenOnly] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  const params = new URLSearchParams();
  if (assetClass) params.set("assetClass", assetClass);
  if (subCategory) params.set("subCategory", subCategory);
  if (amc) params.set("amc", amc);
  if (search) params.set("search", search);
  params.set("openOnly", String(openOnly));
  params.set("limit", "500");

  const { data, isLoading, error, refetch, isFetching } = useQuery<MfResponse>({
    queryKey: ["insights/mf-holdings", assetClass, subCategory, amc, search, openOnly],
    queryFn: () => fetchApi(`/insights/mf-holdings?${params}`),
    staleTime: 30 * 60_000,
  });

  // Map AMC name → logo URL by scanning the items we already loaded.
  // (Backend attaches `amcLogo` to every scheme item.) Falls back to the
  // gradient initial avatar when an AMC isn't covered by Dhan's CDN.
  const amcLogoByName = useMemo(() => {
    const map: Record<string, string> = {};
    for (const it of data?.items || []) {
      if (it.amc && it.amcLogo && !map[it.amc]) map[it.amc] = it.amcLogo;
    }
    return map;
  }, [data?.items]);

  const amcOptions = useMemo(
    () => (data?.amcs || []).map(a => ({ value: a, label: a })),
    [data?.amcs],
  );
  const subOptions = useMemo(() => {
    const subs = assetClass
      ? (data?.subCategoriesByClass?.[assetClass] || [])
      : Object.values(data?.subCategoriesByClass || {}).flat();
    return Array.from(new Set(subs)).sort().map(s => ({ value: s, label: s }));
  }, [assetClass, data?.subCategoriesByClass]);

  const setAssetAndReset = (v: string) => { setAssetClass(v); setSubCategory(""); setExpanded(null); };

  return (
    <div>
      <PageHeader
        title="Mutual Funds — Schemes, Returns & Risk"
        info="AMFI live NAV feed + per-scheme historical returns and risk metrics vs Nifty 50"
        right={
          <div className="flex items-center gap-3">
            {data?.available && (
              <span className="text-[11px] text-gray-500 dark:text-gray-400">
                <span className="font-semibold text-gray-900 dark:text-white">{data.matched?.toLocaleString()}</span>
                {" of "}
                <span className="font-semibold text-gray-900 dark:text-white">{data.totalSchemes?.toLocaleString()}</span>
                {" schemes"}
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

      {/* Filter row 1 — asset class chips */}
      <div className="mb-3">
        <PillTabs value={assetClass} onChange={setAssetAndReset} options={ASSET_TABS} />
      </div>

      {/* Beautiful unified filter bar */}
      <div className="mb-4 rounded-2xl border border-gray-200 dark:border-gray-700/60 bg-gradient-to-br from-white to-gray-50/40 dark:from-gray-800/80 dark:to-gray-900/40 backdrop-blur shadow-sm p-2.5">
        <div className="flex flex-wrap items-center gap-2">

          {/* Search — flexible primary input with icon */}
          <div className="relative flex-1 min-w-[260px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500 pointer-events-none"/>
            <input
              value={search}
              onChange={e => { setSearch(e.target.value); setExpanded(null); }}
              placeholder="Search scheme name…"
              className="w-full text-sm bg-white dark:bg-gray-900/50 border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white rounded-xl pl-9 pr-9 py-2.5 outline-none focus:border-indigo-500 dark:focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 placeholder:text-gray-400 dark:placeholder:text-gray-500 transition shadow-sm"
            />
            {search && (
              <button onClick={() => setSearch("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700 dark:hover:text-gray-200 transition"
                title="Clear search">
                <X className="w-3.5 h-3.5"/>
              </button>
            )}
          </div>

          {/* Sub-category dropdown */}
          <MenuDropdown
            value={subCategory}
            onChange={(v) => { setSubCategory(v); setExpanded(null); }}
            options={subOptions}
            placeholder={assetClass ? `All ${assetClass}` : "All sub-categories"}
            clearable
            customButton={
              <FilterTrigger
                icon={<Layers className="w-3.5 h-3.5"/>}
                label="Category"
                value={subCategory || (assetClass ? `All ${assetClass}` : "All categories")}
                active={!!subCategory}
              />
            }
          />

          {/* AMC dropdown — with logos in rows + selected logo in trigger */}
          <MenuDropdown
            value={amc}
            onChange={(v) => { setAmc(v); setExpanded(null); }}
            options={amcOptions}
            placeholder="All AMCs"
            clearable
            searchPlaceholder="Search AMC…"
            customButton={
              <FilterTrigger
                icon={
                  amc && amcLogoByName[amc]
                    ? <AmcAvatar logo={amcLogoByName[amc]} name={amc} size={20}/>
                    : <Building2 className="w-3.5 h-3.5"/>
                }
                label="AMC"
                value={amc || "All AMCs"}
                active={!!amc}
              />
            }
            renderOption={(o) => (
              <div className="flex items-center gap-2.5 min-w-0">
                <AmcAvatar logo={amcLogoByName[o.value]} name={o.label} size={22}/>
                <span className="truncate text-sm">{o.label}</span>
              </div>
            )}
          />

          {/* Modern toggle switch — open-ended only */}
          <button
            type="button"
            role="switch"
            aria-checked={openOnly}
            onClick={() => setOpenOnly(o => !o)}
            className={`group inline-flex items-center gap-2 pl-3 pr-3.5 py-2 rounded-xl border transition shadow-sm select-none ${
              openOnly
                ? "border-indigo-300 dark:border-indigo-500/50 bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300"
                : "border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900/50 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
            }`}
            title="Show only open-ended schemes (currently subscribable)"
          >
            <span className={`relative inline-flex w-7 h-4 rounded-full transition ${openOnly ? "bg-indigo-600" : "bg-gray-300 dark:bg-gray-600"}`}>
              <span className={`absolute top-0.5 w-3 h-3 bg-white rounded-full shadow-sm transition-all ${openOnly ? "left-3.5" : "left-0.5"}`}/>
            </span>
            <span className="text-xs font-medium whitespace-nowrap">Open-ended</span>
          </button>
        </div>

        {/* Active filter chip strip — only when something is set */}
        {(subCategory || amc || search) && (
          <div className="flex flex-wrap items-center gap-1.5 mt-2 pt-2 border-t border-gray-200/60 dark:border-gray-700/40">
            <span className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500 font-medium">Filters:</span>
            {search && (
              <FilterChip label={`"${search}"`} onClear={() => setSearch("")}/>
            )}
            {subCategory && (
              <FilterChip label={subCategory} onClear={() => setSubCategory("")}/>
            )}
            {amc && (
              <FilterChip
                label={amc}
                logo={amcLogoByName[amc]}
                onClear={() => setAmc("")}
              />
            )}
            <button
              onClick={() => { setSearch(""); setSubCategory(""); setAmc(""); setExpanded(null); }}
              className="ml-1 text-[11px] text-gray-500 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition"
            >
              Clear all
            </button>
          </div>
        )}
      </div>

      {isLoading && <Loading label="Fetching AMFI NAV feed…" />}
      {error && !isLoading && <ErrorState message={(error as Error).message} />}
      {!error && !isLoading && data?.available === false && (
        <EmptyState title="Feed unavailable" message={data.message || "AMFI NAV feed temporarily unavailable."}
          icon={<PieChart className="w-10 h-10"/>}/>
      )}
      {!isLoading && data?.available && (data.items || []).length === 0 && (
        <EmptyState title="No schemes" message="No schemes match the selected filters."
          icon={<PieChart className="w-10 h-10"/>}/>
      )}

      {data?.items && data.items.length > 0 && (
        <div role="table" aria-label="Mutual fund schemes" className="space-y-2">
          {/* Column header strip — aligns with the row grid below */}
          <div role="row" className="hidden md:grid px-4 py-1.5 grid-cols-[44px_minmax(0,1fr)_140px_120px_28px] lg:grid-cols-[44px_minmax(0,1fr)_180px_140px_28px] gap-3 items-center text-[10px] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-medium">
            <span role="columnheader" aria-label="AMC logo"></span>
            <span role="columnheader">Scheme</span>
            <span role="columnheader">Category</span>
            <span role="columnheader" className="text-right">NAV (₹)</span>
            <span role="columnheader" aria-label="Expand"></span>
          </div>

          <div role="rowgroup" className="space-y-1.5">
            {data.items.map(s => {
              const isOpen = expanded === s.schemeCode;
              return (
                <div
                  key={s.schemeCode}
                  role="row"
                  className={`group rounded-xl border bg-white dark:bg-gray-800/60 shadow-sm transition-all ${
                    isOpen
                      ? "border-indigo-300 dark:border-indigo-500/50 shadow-md ring-1 ring-indigo-500/10"
                      : "border-gray-200 dark:border-gray-700/60 hover:border-indigo-200 dark:hover:border-indigo-500/40 hover:shadow-md"
                  }`}
                >
                  <button
                    onClick={() => setExpanded(isOpen ? null : s.schemeCode)}
                    className="w-full text-left px-3 py-3 grid grid-cols-[44px_minmax(0,1fr)_auto] md:grid-cols-[44px_minmax(0,1fr)_140px_120px_28px] lg:grid-cols-[44px_minmax(0,1fr)_180px_140px_28px] gap-3 items-center"
                    aria-expanded={isOpen}
                  >
                    {/* AMC logo */}
                    <AmcAvatar logo={s.amcLogo} name={s.amc} size={40}/>

                    {/* Scheme name + AMC + holdings badge */}
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-gray-900 dark:text-white truncate" title={s.schemeName}>
                        {s.schemeName}
                      </div>
                      <div className="flex items-center gap-1.5 mt-0.5 text-[11px] text-gray-500 dark:text-gray-400 min-w-0">
                        <span className="truncate" title={s.amc}>{s.amc}</span>
                        {s.seo && (
                          <span className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-px rounded-full bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 text-[10px] font-medium flex-shrink-0">
                            <Sparkles className="w-2.5 h-2.5"/> Holdings
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Asset class + sub-category chips (md+) */}
                    <div className="hidden md:flex flex-col gap-0.5 min-w-0">
                      {s.assetClass && (
                        <span className="inline-flex items-center self-start max-w-full px-2 py-0.5 rounded-md bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 text-[10px] font-medium truncate">
                          {s.assetClass}
                        </span>
                      )}
                      {s.subCategory && (
                        <span className="text-[11px] text-gray-500 dark:text-gray-400 truncate" title={s.subCategory}>
                          {s.subCategory}
                        </span>
                      )}
                    </div>

                    {/* NAV + as-of date (md+) */}
                    <div className="hidden md:block text-right">
                      <div className="text-sm font-bold text-gray-900 dark:text-white tabular-nums">
                        {s.nav != null ? `₹${s.nav.toFixed(4)}` : "—"}
                      </div>
                      <div className="text-[10px] text-gray-400 dark:text-gray-500 tabular-nums whitespace-nowrap">
                        {s.date}
                      </div>
                    </div>

                    {/* Mobile-only NAV (replaces last 2 columns) */}
                    <div className="md:hidden text-right">
                      <div className="text-sm font-bold text-gray-900 dark:text-white tabular-nums">
                        {s.nav != null ? `₹${s.nav.toFixed(2)}` : "—"}
                      </div>
                      <ChevronDown className={`w-4 h-4 text-gray-400 ml-auto mt-0.5 transition-transform ${isOpen ? "rotate-180 text-indigo-500" : ""}`}/>
                    </div>

                    {/* Chevron (md+) */}
                    <ChevronDown className={`hidden md:block w-4 h-4 text-gray-400 transition-transform ${isOpen ? "rotate-180 text-indigo-500" : "group-hover:text-indigo-500"}`}/>
                  </button>

                  {isOpen && (
                    <div className="px-4 pt-2 pb-4 border-t border-gray-200 dark:border-gray-700/60">
                      <SchemeDetailPanel code={s.schemeCode} fallbackName={s.schemeName} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
 * Per-scheme expansion: NAV chart vs Nifty + return ladder + risk badges.
 * ────────────────────────────────────────────────────────────────────── */

function SchemeDetailPanel({ code, fallbackName }: { code: string; fallbackName: string }) {
  const { data, isLoading, error } = useQuery<SchemeDetail>({
    queryKey: ["insights/mf-scheme", code],
    queryFn: () => fetchApi(`/insights/mf-scheme/${code}`),
    staleTime: 30 * 60_000,
  });

  if (isLoading) {
    return <div className="text-xs text-gray-500 dark:text-gray-400 py-3">Loading scheme details…</div>;
  }
  if (error || !data || data.available === false) {
    return (
      <div className="text-xs text-gray-500 dark:text-gray-400 py-2">
        {(data?.message) || "Could not load scheme details."}
      </div>
    );
  }

  const ret = data.returns || {};
  const risk = data.risk || {};
  const returnEntries: { label: string; key: string; isCagr: boolean }[] = [
    { label: "1M",  key: "1M",  isCagr: false },
    { label: "3M",  key: "3M",  isCagr: false },
    { label: "6M",  key: "6M",  isCagr: false },
    { label: "1Y",  key: "1Y",  isCagr: false },
    { label: "3Y",  key: "3Y",  isCagr: true  },
    { label: "5Y",  key: "5Y",  isCagr: true  },
    { label: "10Y", key: "10Y", isCagr: true  },
    { label: "SI",  key: "SI",  isCagr: true  },
  ];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {/* Left: chart */}
      <div className="lg:col-span-2 rounded-xl border border-gray-200 dark:border-gray-700/60 bg-gradient-to-br from-white to-gray-50/40 dark:from-gray-900/40 dark:to-gray-800/30 p-3">
        <div className="flex items-center justify-between mb-1.5">
          <div className="text-[11px] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-medium">
            NAV history · 5 yrs
          </div>
          <div className="text-[11px] text-gray-500 dark:text-gray-400">
            indexed to 100{data.benchmarkLabel ? ` vs ${data.benchmarkLabel}` : ""}
          </div>
        </div>
        <NavChart nav={data.navChart || []} bench={data.benchmarkChart || []} benchLabel={data.benchmarkLabel || ""} />
      </div>

      {/* Right: meta + returns + risk */}
      <div className="space-y-3">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-gray-400 dark:text-gray-500">Scheme</div>
          <div className="text-sm font-semibold text-gray-900 dark:text-white leading-tight">
            {data.meta?.schemeName || fallbackName}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">
            {data.meta?.fundHouse} · {data.meta?.schemeCategory}
          </div>
          {data.latest && (
            <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              NAV ₹<span className="font-semibold text-gray-900 dark:text-white">{data.latest.nav.toFixed(4)}</span>
              <span className="ml-1">as of {data.latest.date}</span>
            </div>
          )}
        </div>

        <div>
          <div className="text-[11px] uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-1.5">Returns</div>
          <div className="grid grid-cols-4 gap-1.5">
            {returnEntries.map(r => {
              const v = ret[r.key] as number | null | undefined;
              return (
                <div key={r.key}
                  className="rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-1.5 py-1 text-center">
                  <div className="text-[10px] text-gray-500 dark:text-gray-400">
                    {r.label}{r.isCagr && v != null ? <span className="text-[9px] opacity-70"> CAGR</span> : ""}
                  </div>
                  <div className={`text-xs font-semibold tabular-nums ${pctClass(v)}`}>
                    {fmtPct(v, 1)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div>
          <div className="text-[11px] uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-1.5">Risk (3-yr daily, vs Nifty 50)</div>
          <div className="grid grid-cols-2 gap-1.5">
            <RiskBadge label="Alpha"     value={fmtPct(risk.alpha, 2)} positive={(risk.alpha ?? 0) >= 0} />
            <RiskBadge label="Beta"      value={fmtNum(risk.beta, 2)} />
            <RiskBadge label="Std Dev"   value={fmtPct(risk.stdDev, 2)} />
            <RiskBadge label="Sharpe"    value={fmtNum(risk.sharpe, 2)} positive={(risk.sharpe ?? 0) >= 1} />
            <RiskBadge label="Max DD" value={fmtPct(risk.maxDrawdown, 1)} negative className="col-span-2" />
          </div>
        </div>

        {data.factsheetUrl && (
          <div className="pt-1">
            <a href={data.factsheetUrl} target="_blank" rel="noopener noreferrer"
               className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:underline">
              View AMC factsheet <ExternalLink className="w-3 h-3"/>
            </a>
          </div>
        )}
      </div>

      {/* Full-width holdings panel */}
      {data.holdings && (data.holdings.categories?.length || 0) > 0 && (
        <div className="lg:col-span-3 pt-2">
          <HoldingsPanel holdings={data.holdings} amcLogo={data.amcLogo}/>
        </div>
      )}
      {(!data.holdings || (data.holdings.categories?.length || 0) === 0) && (
        <div className="lg:col-span-3 text-[11px] text-gray-500 dark:text-gray-400 italic">
          Stock-level holdings not in our index for this scheme — check the AMC factsheet for the latest portfolio.
        </div>
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
 * Holdings panel — scanx-style stock-level table with logos + monthly %
 * ────────────────────────────────────────────────────────────────────── */

function HoldingsPanel({ holdings, amcLogo }: { holdings: Holdings; amcLogo?: string }) {
  void amcLogo;
  const cats = holdings.categories.filter(c => c.rows.length);
  const [activeCat, setActiveCat] = useState(cats[0]?.name || "");
  const [showAll, setShowAll] = useState(false);
  const cat = cats.find(c => c.name === activeCat) || cats[0];
  if (!cat) return null;
  // Show last 6 months of columns (newest-first → display oldest→newest)
  const months = (cat.rows[0]?.months || holdings.months || []).slice(0, 6).reverse();
  const visibleRows = showAll ? cat.rows : cat.rows.slice(0, 12);

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 dark:border-gray-700 bg-gray-50/60 dark:bg-gray-900/30">
        <div className="flex items-center gap-2">
          <PieChart className="w-3.5 h-3.5 text-indigo-500"/>
          <div className="text-xs font-semibold text-gray-900 dark:text-white">Portfolio Holdings</div>
          <span className="text-[10px] text-gray-500 dark:text-gray-400">· {cat.rows.length} positions</span>
        </div>
        <div className="flex flex-wrap items-center gap-1">
          {cats.map(c => (
            <button key={c.name}
              onClick={() => { setActiveCat(c.name); setShowAll(false); }}
              className={`text-[11px] px-2 py-0.5 rounded-full transition ${
                c.name === cat.name
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-100 dark:bg-gray-700/50 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600"
              }`}>
              {c.name} <span className="opacity-70">({c.rows.length})</span>
            </button>
          ))}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-[10px] uppercase text-gray-500 dark:text-gray-400 bg-gray-50/40 dark:bg-gray-900/20">
            <tr>
              <th className="px-3 py-2 text-left">Stock</th>
              <th className="px-2 py-2 text-left">Sector</th>
              <th className="px-2 py-2 text-center">Action</th>
              {months.map(m => (
                <th key={m} className="px-2 py-2 text-right whitespace-nowrap">{fmtMonth(m)}</th>
              ))}
              <th className="px-3 py-2 text-right">Latest %</th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map(r => {
              const newestFirst = r.series.slice(0, 6);
              const cells = newestFirst.slice().reverse();
              while (cells.length < months.length) cells.unshift(NaN as unknown as number);
              return (
                <tr key={(r.isin || r.symbol) + r.name} className="border-t border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/20">
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <StockLogo logo={r.logo} symbol={r.symbol}/>
                      <div className="min-w-0">
                        <div className="font-medium text-gray-900 dark:text-white truncate max-w-[200px]" title={r.name}>{r.name || r.symbol}</div>
                        <div className="text-[10px] text-gray-500 dark:text-gray-400">{r.symbol || r.isin}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-2 py-2 text-gray-600 dark:text-gray-300 max-w-[140px] truncate" title={r.subSector || r.sector}>{r.sector || "—"}</td>
                  <td className="px-2 py-2 text-center"><ActionBadge action={r.action}/></td>
                  {cells.map((v, i) => (
                    <td key={i} className="px-2 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">
                      {isFinite(v) ? v.toFixed(2) : "—"}
                    </td>
                  ))}
                  <td className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-white tabular-nums">
                    {r.latestPct != null ? r.latestPct.toFixed(2) + "%" : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {cat.rows.length > 12 && (
        <div className="px-3 py-2 border-t border-gray-200 dark:border-gray-700 text-center">
          <button onClick={() => setShowAll(s => !s)}
            className="text-[11px] font-medium text-indigo-600 dark:text-indigo-400 hover:underline">
            {showAll ? "Show top 12 only" : `Show all ${cat.rows.length} positions`}
          </button>
        </div>
      )}
      <div className="px-3 py-1.5 text-[10px] text-gray-400 dark:text-gray-500 text-right border-t border-gray-200 dark:border-gray-700">
        Holdings sourced from public AMC monthly portfolio disclosures
      </div>
    </div>
  );
}

function fmtMonth(m: string): string {
  if (!m || !/^\d{4}-\d{2}$/.test(m)) return m;
  const [y, mo] = m.split("-");
  const names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${names[Number(mo) - 1]} ${y.slice(2)}`;
}

function ActionBadge({ action }: { action: string }) {
  const a = (action || "").toLowerCase();
  if (a.includes("increase")) return (
    <span className="inline-flex items-center gap-0.5 text-[10px] font-medium px-1.5 py-0.5 rounded-md text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 border border-emerald-500/20">
      <ArrowUpRight className="w-2.5 h-2.5"/> Increased
    </span>
  );
  if (a.includes("decrease") || a.includes("reduce")) return (
    <span className="inline-flex items-center gap-0.5 text-[10px] font-medium px-1.5 py-0.5 rounded-md text-rose-700 dark:text-rose-400 bg-rose-500/10 border border-rose-500/20">
      <ArrowDownRight className="w-2.5 h-2.5"/> Decreased
    </span>
  );
  if (a.includes("new")) return (
    <span className="inline-flex items-center gap-0.5 text-[10px] font-medium px-1.5 py-0.5 rounded-md text-indigo-700 dark:text-indigo-400 bg-indigo-500/10 border border-indigo-500/20">
      <Sparkles className="w-2.5 h-2.5"/> New
    </span>
  );
  if (a.includes("exit") || a.includes("sold")) return (
    <span className="inline-flex items-center gap-0.5 text-[10px] font-medium px-1.5 py-0.5 rounded-md text-gray-700 dark:text-gray-300 bg-gray-500/10 border border-gray-500/20">
      Exited
    </span>
  );
  return <span className="text-[10px] text-gray-400 dark:text-gray-500">—</span>;
}

function StockLogo({ logo, symbol }: { logo: string; symbol: string }) {
  const [err, setErr] = useState(false);
  const initial = (symbol || "?").slice(0, 2).toUpperCase();
  if (err || !logo) return (
    <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500/20 to-fuchsia-500/20 border border-gray-200 dark:border-gray-700 flex items-center justify-center text-[9px] font-bold text-indigo-700 dark:text-indigo-300 flex-shrink-0">
      {initial}
    </div>
  );
  return (
    <img src={logo} alt={symbol} onError={() => setErr(true)}
      className="w-7 h-7 rounded-full object-contain bg-white border border-gray-200 dark:border-gray-700 flex-shrink-0"/>
  );
}

/* Filter bar trigger button — uniform pill with icon + tiny label + value. */
function FilterTrigger(
  { icon, label, value, active, ...rest }:
  { icon: React.ReactNode; label: string; value: string; active?: boolean } & React.ButtonHTMLAttributes<HTMLButtonElement>,
) {
  return (
    <button
      type="button"
      aria-label={`${label}: ${value}`}
      {...rest}
      className={`group inline-flex items-center gap-2 pl-2.5 pr-2 py-2 rounded-xl border transition shadow-sm select-none max-w-[260px] ${
        active
          ? "border-indigo-300 dark:border-indigo-500/50 bg-indigo-50 dark:bg-indigo-500/10"
          : "border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900/50 hover:bg-gray-50 dark:hover:bg-gray-800"
      }`}
    >
      <span className={`flex-shrink-0 inline-flex items-center justify-center ${active ? "text-indigo-600 dark:text-indigo-400" : "text-gray-500 dark:text-gray-400"}`}>
        {icon}
      </span>
      <span className="flex flex-col leading-tight min-w-0 text-left">
        <span className="text-[9px] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-medium">{label}</span>
        <span className={`text-xs font-semibold truncate ${active ? "text-indigo-700 dark:text-indigo-300" : "text-gray-700 dark:text-gray-200"}`}>{value}</span>
      </span>
      <ChevronDown className={`w-3.5 h-3.5 flex-shrink-0 transition-transform ${active ? "text-indigo-500" : "text-gray-400"}`}/>
    </button>
  );
}

/* Active-filter chip with clear button. */
function FilterChip({ label, logo, onClear }: { label: string; logo?: string; onClear: () => void }) {
  return (
    <span className="inline-flex items-center gap-1.5 pl-1.5 pr-1 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 text-[11px] font-medium border border-indigo-200/60 dark:border-indigo-500/30 max-w-[240px]">
      {logo && <AmcAvatar logo={logo} name={label} size={16}/>}
      <span className="truncate">{label}</span>
      <button onClick={onClear}
        className="p-0.5 rounded-full hover:bg-indigo-200 dark:hover:bg-indigo-500/30 transition"
        aria-label={`Clear ${label}`}>
        <X className="w-2.5 h-2.5"/>
      </button>
    </span>
  );
}

function AmcAvatar({ logo, name, size = 28 }: { logo?: string; name: string; size?: number }) {
  const [err, setErr] = useState(false);
  const initial = (name || "?").trim().split(/\s+/).map(w => w[0]).slice(0, 2).join("").toUpperCase() || "MF";
  if (err || !logo) return (
    <div style={{ width: size, height: size }}
      className="rounded-lg bg-gradient-to-br from-indigo-500/15 to-fuchsia-500/15 border border-gray-200 dark:border-gray-700 flex items-center justify-center text-[9px] font-bold text-indigo-700 dark:text-indigo-300 flex-shrink-0">
      {initial.length > 1 ? initial : <Building2 className="w-3 h-3"/>}
    </div>
  );
  return (
    <img src={logo} alt={name} onError={() => setErr(true)}
      style={{ width: size, height: size }}
      className="rounded-lg object-contain bg-white border border-gray-200 dark:border-gray-700 p-0.5 flex-shrink-0"/>
  );
}

function RiskBadge({ label, value, positive, negative, className = "" }: {
  label: string; value: string; positive?: boolean; negative?: boolean; className?: string;
}) {
  const tone = negative
    ? "text-rose-600 dark:text-rose-400"
    : positive === true
      ? "text-emerald-600 dark:text-emerald-400"
      : positive === false
        ? "text-rose-600 dark:text-rose-400"
        : "text-gray-900 dark:text-white";
  const Icon = positive === true ? TrendingUp : positive === false ? TrendingDown : null;
  return (
    <div className={`rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-2 py-1.5 ${className}`}>
      <div className="text-[10px] text-gray-500 dark:text-gray-400 leading-none">{label}</div>
      <div className={`text-sm font-semibold tabular-nums leading-tight inline-flex items-center gap-1 ${tone}`}>
        {Icon && <Icon className="w-3 h-3"/>}
        {value}
      </div>
    </div>
  );
}

function NavChart({ nav, bench, benchLabel }: {
  nav: { date: string; navIdx: number }[];
  bench: { date: string; benchIdx: number }[];
  benchLabel: string;
}) {
  const palette = useChartPalette();
  // Stable gradient ids per render so multiple charts on the page don't collide.
  const gid = useMemo(() => `mfg-${Math.random().toString(36).slice(2, 8)}`, []);

  // Merge nav + benchmark on date (chart needs single series array).
  const merged = useMemo(() => {
    const map = new Map<string, { date: string; navIdx?: number; benchIdx?: number }>();
    for (const p of nav) map.set(p.date, { date: p.date, navIdx: p.navIdx });
    for (const p of bench) {
      const cur = map.get(p.date);
      if (cur) cur.benchIdx = p.benchIdx;
      else map.set(p.date, { date: p.date, benchIdx: p.benchIdx });
    }
    return Array.from(map.values()).sort((a, b) => a.date.localeCompare(b.date));
  }, [nav, bench]);

  // Headline stats — first vs last NAV index gives the indexed return.
  const stats = useMemo(() => {
    const navs = merged.filter(m => m.navIdx != null);
    if (navs.length < 2) return null;
    const first = navs[0].navIdx!;
    const last  = navs[navs.length - 1].navIdx!;
    const pct   = ((last - first) / first) * 100;
    return { first, last, pct };
  }, [merged]);

  if (merged.length === 0) {
    return (
      <div className="h-56 flex items-center justify-center text-xs text-gray-500 dark:text-gray-400 italic">
        No NAV history available.
      </div>
    );
  }

  const positive = (stats?.pct ?? 0) >= 0;
  const navColor = positive ? palette.pos : palette.neg;

  return (
    <div>
      {stats && (
        <div className="flex items-baseline gap-2 mb-1">
          <div className="text-2xl font-bold text-gray-900 dark:text-white tabular-nums leading-none">
            {stats.last.toFixed(2)}
          </div>
          <div className={`text-xs font-semibold tabular-nums ${positive ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
            {positive ? "▲" : "▼"} {Math.abs(stats.pct).toFixed(2)}%
          </div>
        </div>
      )}
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={merged} margin={{ top: 6, right: 8, left: -10, bottom: 0 }}>
            <defs>
              <linearGradient id={`${gid}-nav`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={navColor} stopOpacity={0.32}/>
                <stop offset="100%" stopColor={navColor} stopOpacity={0}/>
              </linearGradient>
              <linearGradient id={`${gid}-bench`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={palette.line} stopOpacity={0.12}/>
                <stop offset="100%" stopColor={palette.line} stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={palette.border} vertical={false}/>
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: palette.muted }}
              stroke={palette.border}
              interval="preserveStartEnd"
              minTickGap={50}
              tickFormatter={(d: string) => d.slice(0, 7)}
            />
            <YAxis
              tick={{ fontSize: 10, fill: palette.muted }}
              stroke={palette.border}
              domain={["auto", "auto"]}
              width={40}
            />
            <Tooltip
              contentStyle={{ background: palette.surf, border: `1px solid ${palette.border}`, borderRadius: 8, fontSize: 11, color: palette.text, boxShadow: "0 4px 12px rgba(0,0,0,0.08)" }}
              labelStyle={{ color: palette.muted, marginBottom: 4 }}
              formatter={(v: number, name: string) => [v.toFixed(2), name]}
            />
            <Legend wrapperStyle={{ fontSize: 11, paddingTop: 4 }} iconType="plainline"/>
            {bench.length > 0 && (
              <Area
                type="monotone"
                dataKey="benchIdx"
                name={benchLabel || "Benchmark"}
                stroke={palette.line}
                strokeWidth={1.5}
                strokeDasharray="4 3"
                fill={`url(#${gid}-bench)`}
                dot={false}
                isAnimationActive
                animationDuration={900}
                animationEasing="ease-out"
              />
            )}
            <Area
              type="monotone"
              dataKey="navIdx"
              name="Scheme"
              stroke={navColor}
              strokeWidth={2.25}
              fill={`url(#${gid}-nav)`}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 2, stroke: palette.surf }}
              isAnimationActive
              animationDuration={1100}
              animationEasing="ease-out"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
