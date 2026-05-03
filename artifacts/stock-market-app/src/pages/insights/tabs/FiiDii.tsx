import { memo, useEffect, useMemo, useRef, useState, useTransition } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { fetchApi } from "@/lib/api";
import {
  PageHeader, Card, Loading, ErrorState,
  EmptyState, MenuDropdown, useChartPalette,
} from "../_shared";
import {
  ResponsiveContainer, ComposedChart, BarChart, CartesianGrid, XAxis, YAxis,
  Tooltip, Bar, ReferenceLine, Line,
} from "recharts";
import {
  ArrowDownUp, BarChart3, Table as TableIcon, Info, ExternalLink,
  TrendingUp, TrendingDown, ChevronDown, Calendar, LineChart as LineChartIcon,
  LayoutGrid, Building2, Globe2,
} from "lucide-react";

type Segment = "equity" | "index_future" | "index_option" | "stock_future" | "stock_option";
type ViewMode = "chart" | "table" | "both";
type Range = "30d" | "90d" | "180d" | "1y" | "all";

interface Row {
  date: string;
  displayDate: string;
  fiiBuy: number | null; fiiSell: number | null; fiiNet: number | null;
  diiBuy: number | null; diiSell: number | null; diiNet: number | null;
}

interface SummaryCell {
  fiiNet: number | null;
  diiNet: number | null;
  label: string | null;
  days?: number;
  expectedDays?: number;
  isPartial?: boolean;
}

interface MonthBucket {
  key: string;
  label: string;
  fiiNet: number;
  diiNet: number;
  greenDays: number;
  redDays: number;
  days: number;
  rows: Row[];
}

interface FiiDiiResponse {
  available: boolean;
  segment: string;
  source: string;
  sourceUrl: string;
  latest: Row | null;
  rows: Row[];                                 // descending by date
  summary: { daily: SummaryCell; weekly: SummaryCell; monthly: SummaryCell; ytd?: SummaryCell };
  monthly?: MonthBucket[];
  totalDays?: number;
  rangeDays?: number;
  message?: string | null;
}

const SEGMENT_OPTIONS: { value: Segment; label: string; short: string; icon: typeof Globe2 }[] = [
  { value: "equity",         label: "Equity Cash",     short: "Equity",      icon: Building2 },
  { value: "index_future",   label: "Index Futures",   short: "Idx Fut",     icon: TrendingUp },
  { value: "index_option",   label: "Index Options",   short: "Idx Opt",     icon: LineChartIcon },
  { value: "stock_future",   label: "Stock Futures",   short: "Stk Fut",     icon: BarChart3 },
  { value: "stock_option",   label: "Stock Options",   short: "Stk Opt",     icon: LayoutGrid },
];

const RANGE_OPTIONS: { value: Range; label: string }[] = [
  { value: "30d",  label: "Last 30 days" },
  { value: "90d",  label: "Last 90 days" },
  { value: "180d", label: "Last 180 days" },
  { value: "1y",   label: "Last 1 year" },
  { value: "all",  label: "All on file" },
];

function rangeLimit(r: Range): number {
  // 1500 is the backend's hard upper bound (validated by Query(le=1500)).
  return r === "30d" ? 30 : r === "90d" ? 90 : r === "180d" ? 180 : r === "1y" ? 365 : 1500;
}

function fmtCr(v: number | null | undefined, isContracts: boolean = false): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  const abs = Math.abs(v).toLocaleString("en-IN", {
    minimumFractionDigits: isContracts ? 0 : 2,
    maximumFractionDigits: isContracts ? 0 : 2,
  });
  return isContracts ? `${sign}${abs}` : `${sign}₹${abs} Cr`;
}

function fmtCompact(v: number | null | undefined, isContracts: boolean = false): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  const abs = Math.abs(v);
  let body: string;
  if (abs >= 1e7) body = `${(abs / 1e7).toFixed(2)}Cr`;
  else if (abs >= 1e5) body = `${(abs / 1e5).toFixed(2)}L`;
  else if (abs >= 1e3) body = `${(abs / 1e3).toFixed(2)}K`;
  else body = abs.toLocaleString("en-IN", { maximumFractionDigits: isContracts ? 0 : 2 });
  return isContracts ? `${sign}${body}` : `${sign}₹${body}`;
}

function netClass(v: number | null | undefined): string {
  if (v === null || v === undefined) return "text-gray-500 dark:text-gray-400";
  if (v > 0) return "text-emerald-600 dark:text-emerald-400";
  if (v < 0) return "text-red-600 dark:text-red-400";
  return "text-gray-500 dark:text-gray-400";
}

function netGradient(v: number | null | undefined): string {
  if (v === null || v === undefined) return "from-gray-500/10 to-gray-500/0";
  if (v > 0) return "from-emerald-500/15 to-emerald-500/0";
  if (v < 0) return "from-red-500/15 to-red-500/0";
  return "from-gray-500/10 to-gray-500/0";
}

export default function FiiDii() {
  const [segment, setSegment] = useState<Segment>("equity");
  const [view, setView] = useState<ViewMode>("both");
  const [range, setRange] = useState<Range>("1y");
  const reduced = useReducedMotion();
  // Concurrent transition for tab/range swaps so the heavy ~14-chart
  // re-render never blocks click feedback or the theme ripple.
  const [, startTransition] = useTransition();

  const { data, isLoading, isFetching, error } = useQuery<FiiDiiResponse>({
    queryKey: ["insights/fii-dii", segment, range],
    queryFn: () => fetchApi(`/insights/fii-dii?segment=${segment}&days=${rangeLimit(range)}`),
    staleTime: 10 * 60_000,
    // Keep showing the previous tab's content while the next segment loads —
    // no more "collapses to spinner then re-mounts everything" jank when
    // hopping between Equity → Index Futures → Stock Options.
    placeholderData: keepPreviousData,
  });

  const segMeta = SEGMENT_OPTIONS.find(s => s.value === segment)!;
  const switchSegment = (v: Segment) => startTransition(() => setSegment(v));
  const switchRange = (v: Range) => startTransition(() => setRange(v));

  return (
    <div>
      <PageHeader
        title="FII / DII Activity"
        info="Daily provisional cash and derivatives activity by Foreign and Domestic Institutional Investors. Data is fetched live from NSE and accumulated locally as a rolling history."
        right={data?.sourceUrl ? (
          <a href={data.sourceUrl} target="_blank" rel="noreferrer noopener"
             className="hidden md:inline-flex items-center gap-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition">
            Source: {data.source} <ExternalLink className="w-3.5 h-3.5" />
          </a>
        ) : undefined}
      />

      {/* Segment tabs — modern card-style strip */}
      <div className="mb-4 -mx-2 px-2 overflow-x-auto">
        <div className="inline-flex gap-2 min-w-full md:min-w-0">
          {SEGMENT_OPTIONS.map((o) => {
            const Icon = o.icon;
            const active = o.value === segment;
            return (
              <button
                key={o.value}
                onClick={() => switchSegment(o.value)}
                className={`group relative inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-medium transition border whitespace-nowrap
                  ${active
                    ? "bg-indigo-600 text-white border-indigo-600 dark:bg-indigo-500 dark:border-indigo-500 shadow-md shadow-indigo-500/20"
                    : "bg-white dark:bg-gray-800/60 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/60 hover:border-indigo-300 dark:hover:border-indigo-500/40"}`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">{o.label}</span>
                <span className="inline sm:hidden">{o.short}</span>
              </button>
            );
          })}
        </div>
      </div>

      {isLoading ? (
        <Loading label="Loading FII/DII history…" />
      ) : error ? (
        <ErrorState message="We couldn't load FII/DII data. Please try again in a moment." />
      ) : !data?.available ? (
        <EmptyState
          icon={<BarChart3 className="w-6 h-6" />}
          title={`${segMeta.label} flows are not available right now`}
          message={data?.message || "No data returned. Try again later."}
        />
      ) : (
        <div className={isFetching ? "transition-opacity duration-200 opacity-70" : "transition-opacity duration-200 opacity-100"}>
          <Body
            data={data}
            segMeta={segMeta}
            view={view} setView={setView}
            range={range} setRange={switchRange}
            reduced={!!reduced}
          />
        </div>
      )}
    </div>
  );
}

function Body({
  data, segMeta, view, setView, range, setRange, reduced,
}: {
  data: FiiDiiResponse;
  segMeta: typeof SEGMENT_OPTIONS[number];
  view: ViewMode; setView: (v: ViewMode) => void;
  range: Range; setRange: (r: Range) => void;
  reduced: boolean;
}) {
  const limit = rangeLimit(range);
  const rows = useMemo(() => data.rows.slice(0, limit), [data.rows, limit]);
  const isContracts = data.segment !== "equity";
  const totalDays = data.totalDays ?? data.rows.length;
  const monthly = data.monthly ?? [];
  // YTD sparkline rows = every cached row whose ISO date is in the current year.
  const ytdRows = useMemo(() => {
    const yr = new Date().getFullYear();
    const cutoff = `${yr}-01-01`;
    return data.rows.filter((r) => (r.date ?? "") >= cutoff);
  }, [data.rows]);

  return (
    <div className="space-y-5">
      {/* Hero summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <HeroCard
          title="Latest Day"
          icon={<Calendar className="w-3.5 h-3.5" />}
          cell={data.summary.daily}
          isContracts={isContracts}
          rowsForSpark={rows.slice(0, 1)}
          subtitle={data.summary.daily?.label || "—"}
          delay={0}
          reduced={reduced}
        />
        <HeroCard
          title="Last 5 Sessions"
          icon={<TrendingUp className="w-3.5 h-3.5" />}
          cell={data.summary.weekly}
          isContracts={isContracts}
          rowsForSpark={rows.slice(0, 5)}
          subtitle={daysWindowLabel(rows.slice(0, 5))}
          delay={0.05}
          reduced={reduced}
        />
        <HeroCard
          title="Last 30 Sessions"
          icon={<TrendingUp className="w-3.5 h-3.5" />}
          cell={data.summary.monthly}
          isContracts={isContracts}
          rowsForSpark={rows.slice(0, 30)}
          subtitle={daysWindowLabel(rows.slice(0, 30))}
          delay={0.1}
          reduced={reduced}
        />
        <HeroCard
          title="Year to Date"
          icon={<TrendingUp className="w-3.5 h-3.5" />}
          cell={data.summary.ytd}
          isContracts={isContracts}
          rowsForSpark={ytdRows}
          subtitle={ytdRows.length ? daysWindowLabel(ytdRows) : "—"}
          delay={0.15}
          reduced={reduced}
        />
      </div>

      {/* Toolbar */}
      <Card className="p-3 bg-gradient-to-br from-white to-gray-50 dark:from-gray-800 dark:to-gray-800/40">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div className="inline-flex items-center gap-1 p-1 rounded-xl bg-gray-100 dark:bg-gray-900/60 border border-gray-200 dark:border-gray-700">
            <ViewBtn current={view} value="chart" onClick={() => setView("chart")} icon={<BarChart3 className="w-3.5 h-3.5" />} label="Chart" />
            <ViewBtn current={view} value="table" onClick={() => setView("table")} icon={<TableIcon className="w-3.5 h-3.5" />} label="Table" />
            <ViewBtn current={view} value="both"  onClick={() => setView("both")}  icon={<LayoutGrid className="w-3.5 h-3.5" />} label="Chart + Table" />
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden sm:inline text-xs text-gray-500 dark:text-gray-400">
              <ArrowDownUp className="w-3 h-3 inline mr-1" /> Range
            </span>
            <MenuDropdown
              value={range}
              options={RANGE_OPTIONS}
              onChange={(v) => setRange((v || "1y") as Range)}
              minButtonWidth={170}
            />
          </div>
        </div>
        <p className="mt-2 text-[11px] text-gray-500 dark:text-gray-400 flex items-start gap-1.5">
          <Info className="w-3 h-3 flex-shrink-0 mt-0.5" />
          <span>
            Showing {Math.min(rows.length, limit)} of {totalDays} day(s) on file for {segMeta.label}.
            {data.segment === "equity" && totalDays < 60 && (
              <>
                {" "}NSE only publishes equity FII/DII as a daily snapshot, so this tab grows by
                one row per trading session. The four F&amp;O tabs ship preloaded with ~13 months
                of history.
              </>
            )}
            {data.segment !== "equity" && totalDays < 5 && " History is being built — this dashboard records each new trading day's snapshot."}
          </span>
        </p>
      </Card>

      {/* Combined view (chart + table or one of them) — both are deferred so the
          toolbar/hero cards reflow instantly on segment switch and the heavy
          chart/table mount in the next idle frame. */}
      {(view === "chart" || view === "both") && (
        <IdleMount deps={[data.segment, range]} placeholder={<ChartSkeleton />}>
          <FiiDiiChart rows={rows} segment={data.segment} />
        </IdleMount>
      )}
      {(view === "table" || view === "both") && (
        <IdleMount deps={[data.segment, range]} placeholder={<TableSkeleton />}>
          <FiiDiiTable rows={rows} segment={data.segment} />
        </IdleMount>
      )}

      {/* Month-wise breakdown — deferred so the heaviest part of the page
          (~13 mini-charts) doesn't block first paint when switching tabs. */}
      <IdleMount deps={[data.segment, range]} placeholder={<MonthlySkeleton months={monthly.length} />}>
        {monthly.length > 0 && <MonthlyBreakdown months={monthly} isContracts={isContracts} reduced={reduced} />}
      </IdleMount>
    </div>
  );
}

/** "Mount in the next animation frame" boundary. Re-defers whenever any
 *  dependency in `deps` changes — the placeholder paints in frame 1,
 *  the heavy children mount in frame 2 (~16-32 ms). Fast enough that
 *  cached tab switches never linger on a skeleton, but still gives the
 *  browser a frame to commit the lighter parts of the page first. */
function IdleMount({ deps, placeholder, children }: {
  deps: unknown[]; placeholder: React.ReactNode; children: React.ReactNode;
}) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setReady(false);
    let raf2 = 0;
    const raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(() => setReady(true));
    });
    return () => {
      cancelAnimationFrame(raf1);
      if (raf2) cancelAnimationFrame(raf2);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return <>{ready ? children : placeholder}</>;
}

/** Downsample an array of rows for charting. Returns the original rows
 *  when count <= maxPoints, otherwise groups consecutive rows into
 *  buckets and sums fii/dii nets per bucket so the chart never plots
 *  more than ~maxPoints bars. Massively reduces SVG paint cost on
 *  wide ranges (e.g. 1y of F&O = 365 → ~120 buckets). */
function downsampleRows(rows: Row[], maxPoints: number): Row[] {
  if (rows.length <= maxPoints) return rows;
  const bucketSize = Math.ceil(rows.length / maxPoints);
  const out: Row[] = [];
  for (let i = 0; i < rows.length; i += bucketSize) {
    const slice = rows.slice(i, i + bucketSize);
    let fii = 0, dii = 0;
    for (const r of slice) {
      fii += r.fiiNet ?? 0;
      dii += r.diiNet ?? 0;
    }
    const head = slice[0];
    const tail = slice[slice.length - 1];
    out.push({
      ...head,
      fiiNet: fii,
      diiNet: dii,
      // Label spans bucket window: "01 Jan→07 Jan"
      displayDate: slice.length > 1
        ? `${tail.displayDate || tail.date}→${head.displayDate || head.date}`
        : (head.displayDate || head.date),
    });
  }
  return out;
}

/** Mount-on-visible boundary using IntersectionObserver. Renders the
 *  placeholder until the wrapper enters the viewport, then mounts the
 *  children. Used by MonthCard so the 13 mini charts only build SVG
 *  when the user actually scrolls them into view. */
function VisibleOnce({ placeholder, children, rootMargin = "200px" }: {
  placeholder: React.ReactNode; children: React.ReactNode; rootMargin?: string;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (visible || !ref.current) return;
    const el = ref.current;
    if (typeof IntersectionObserver === "undefined") { setVisible(true); return; }
    const obs = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) { setVisible(true); obs.disconnect(); break; }
      }
    }, { rootMargin });
    obs.observe(el);
    return () => obs.disconnect();
  }, [visible, rootMargin]);
  return <div ref={ref}>{visible ? children : placeholder}</div>;
}

function ChartSkeleton() {
  return (
    <div className="rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
      <div className="h-4 w-40 rounded bg-gray-100 dark:bg-gray-700/50 animate-pulse mb-3" />
      <div className="h-72 md:h-80 rounded-lg bg-gray-50/80 dark:bg-gray-800/40 animate-pulse" />
    </div>
  );
}
function TableSkeleton() {
  return (
    <div className="rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800">
      <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700 h-12 animate-pulse" />
      <div className="p-4 space-y-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-7 rounded bg-gray-50/80 dark:bg-gray-800/40 animate-pulse" />
        ))}
      </div>
    </div>
  );
}
function MonthlySkeleton({ months }: { months: number }) {
  if (!months) return null;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 mt-2">
        <Calendar className="w-4 h-4 text-indigo-500 dark:text-indigo-400" />
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Month-wise Breakdown</h3>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {Array.from({ length: Math.min(4, months) }).map((_, i) => (
          <div key={i} className="h-40 rounded-xl border border-gray-100 dark:border-gray-700 bg-gray-50/60 dark:bg-gray-800/40 animate-pulse" />
        ))}
      </div>
    </div>
  );
}

function ViewBtn({ current, value, onClick, icon, label }: {
  current: ViewMode; value: ViewMode; onClick: () => void; icon: React.ReactNode; label: string;
}) {
  const active = current === value;
  return (
    <button
      onClick={onClick}
      className={`relative inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition whitespace-nowrap
        ${active
          ? "bg-white dark:bg-gray-800 text-indigo-600 dark:text-indigo-300 shadow-sm border border-gray-200 dark:border-gray-600"
          : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 border border-transparent"}`}
    >
      {icon} {label}
    </button>
  );
}

function daysWindowLabel(rows: Row[]): string {
  if (!rows.length) return "—";
  const first = rows[0]?.displayDate;
  const last = rows[rows.length - 1]?.displayDate;
  if (rows.length === 1) return first || "—";
  return `${last} → ${first}`;
}

/* ── Hero summary card with sparkline + green/red day count ─────────── */
const HeroCard = memo(_HeroCard);
function _HeroCard({
  title, icon, cell, isContracts, rowsForSpark, subtitle, delay, reduced,
}: {
  title: string;
  icon: React.ReactNode;
  cell: SummaryCell | undefined;
  isContracts: boolean;
  rowsForSpark: Row[];
  subtitle: string;
  delay: number;
  reduced: boolean;
}) {
  const c: SummaryCell = cell ?? { fiiNet: null, diiNet: null, label: null };
  const total = (c.fiiNet ?? 0) + (c.diiNet ?? 0);
  const palette = useChartPalette();

  // Green/red day counts based on combined FII+DII direction
  const { greens, reds } = useMemo(() => {
    let g = 0, r = 0;
    for (const row of rowsForSpark) {
      const net = (row.fiiNet ?? 0) + (row.diiNet ?? 0);
      if (net > 0) g++; else if (net < 0) r++;
    }
    return { greens: g, reds: r };
  }, [rowsForSpark]);

  // Sparkline data — ascending so it reads left-to-right
  const sparkData = useMemo(() =>
    [...rowsForSpark].reverse().map((r, i) => ({
      i, fii: r.fiiNet ?? 0, dii: r.diiNet ?? 0, total: (r.fiiNet ?? 0) + (r.diiNet ?? 0),
    })), [rowsForSpark]);

  return (
    <motion.div
      initial={reduced ? { opacity: 0 } : { opacity: 0, y: 16, scale: 0.97 }}
      animate={reduced ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
      transition={reduced ? { duration: 0.2 } : { delay, duration: 0.45, type: "spring", stiffness: 110, damping: 18 }}
      className={`relative overflow-hidden rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm`}
    >
      {/* Tinted gradient by net direction */}
      <div className={`absolute inset-0 bg-gradient-to-br ${netGradient(total)} pointer-events-none`} />

      <div className="relative p-4">
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
            <span className="text-indigo-500 dark:text-indigo-400">{icon}</span>
            {title}
          </div>
          {rowsForSpark.length > 1 && (
            <div className="flex items-center gap-1.5 text-[10px]">
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/20">
                <TrendingUp className="w-2.5 h-2.5" />{greens}
              </span>
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-500/20">
                <TrendingDown className="w-2.5 h-2.5" />{reds}
              </span>
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-0.5">FII Net</div>
            <div className={`text-base md:text-lg font-bold tabular-nums ${netClass(c.fiiNet)}`}>{fmtCompact(c.fiiNet, isContracts)}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-0.5">DII Net</div>
            <div className={`text-base md:text-lg font-bold tabular-nums ${netClass(c.diiNet)}`}>{fmtCompact(c.diiNet, isContracts)}</div>
          </div>
        </div>

        {/* Sparkline */}
        {sparkData.length > 1 && (
          <div className="h-12 mt-3 -mx-1">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={sparkData} margin={{ top: 2, right: 2, left: 2, bottom: 0 }}>
                <ReferenceLine y={0} stroke={palette.border} strokeWidth={1} />
                <Bar dataKey="fii" fill={palette.fii} opacity={0.55} maxBarSize={4} isAnimationActive={false} />
                <Bar dataKey="dii" fill={palette.dii} opacity={0.55} maxBarSize={4} isAnimationActive={false} />
                <Line type="monotone" dataKey="total" stroke={palette.line} strokeWidth={1.5} dot={false} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}

        <div className="mt-2 flex items-center justify-between text-[10px] text-gray-500 dark:text-gray-400">
          <span className="truncate" title={subtitle}>{subtitle}</span>
          <span className="text-gray-400 dark:text-gray-500 whitespace-nowrap ml-2">{c.days ?? 0}d</span>
        </div>
      </div>
    </motion.div>
  );
}

/* ── Main chart ─────────────────────────────────────────────────────── */
const FiiDiiChart = memo(function FiiDiiChart({ rows, segment }: { rows: Row[]; segment: string }) {
  const palette = useChartPalette();
  const isContracts = segment !== "equity";
  const data = useMemo(() => {
    // Downsample to keep SVG paint cost flat regardless of range.
    // 120 bars renders in a single frame even on mid-tier devices.
    const sampled = downsampleRows(rows, 120);
    return [...sampled].reverse().map(r => ({
      label: (r.displayDate || r.date).slice(0, 6),
      fii: r.fiiNet ?? 0,
      dii: r.diiNet ?? 0,
    }));
  }, [rows]);
  const isAggregated = rows.length > 120;

  if (!data.length) {
    return <EmptyState title="Nothing to plot yet" message="Once a few daily snapshots are collected, this chart will populate." icon={<BarChart3 className="w-6 h-6" />} />;
  }

  return (
    <div>
      <Card className="p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-indigo-500 dark:text-indigo-400" />
            Daily Net Flows
          </h3>
          <div className="flex items-center gap-3 text-[11px]">
            <LegendChip kind="fii" color={palette.fii} />
            <LegendChip kind="dii" color={palette.dii} />
          </div>
        </div>
        <div className="h-72 md:h-80">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 6, right: 12, left: 0, bottom: 6 }}>
              <CartesianGrid stroke={palette.border} strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="label" stroke={palette.muted} fontSize={11} tickLine={false}
                     axisLine={{ stroke: palette.border }} interval="preserveStartEnd" minTickGap={28} />
              <YAxis stroke={palette.muted} fontSize={11} tickLine={false} axisLine={{ stroke: palette.border }}
                     tickFormatter={(v) => fmtCompact(v, isContracts)} width={62} />
              <Tooltip
                contentStyle={{
                  background: palette.surf, border: `1px solid ${palette.border}`,
                  borderRadius: 10, color: palette.text, fontSize: 12, padding: "8px 10px",
                  boxShadow: "0 8px 24px rgba(0,0,0,0.18)",
                }}
                labelStyle={{ color: palette.muted, fontSize: 11, marginBottom: 4 }}
                cursor={{ fill: palette.border, opacity: 0.25 }}
                formatter={(value: number, name: string) => [fmtCr(value, isContracts), name === "fii" ? "FII Net" : "DII Net"]}
              />
              <ReferenceLine y={0} stroke={palette.muted} strokeWidth={1} />
              <Bar dataKey="fii" name="fii" fill={palette.fii} radius={[3, 3, 0, 0]} maxBarSize={22} isAnimationActive={false} />
              <Bar dataKey="dii" name="dii" fill={palette.dii} radius={[3, 3, 0, 0]} maxBarSize={22} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-2 text-[11px] text-gray-500 dark:text-gray-400">
          {isContracts ? "Net flows in contracts (Long − Short)." : "Net flows in ₹ Cr (Buy − Sell)."} Positive bars indicate net buying, negative bars indicate net selling.
          {isAggregated && ` Showing ${data.length} aggregated buckets across ${rows.length} sessions for performance — see the table for daily detail.`}
        </p>
      </Card>
    </div>
  );
});

function LegendChip({ kind, color }: { kind: "fii" | "dii"; color: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-gray-600 dark:text-gray-300">
      <span className="w-2.5 h-2.5 rounded-sm" style={{ background: color }} />
      {kind === "fii" ? "FII Net" : "DII Net"}
    </span>
  );
}

/* ── Table ──────────────────────────────────────────────────────────── */
const TABLE_INITIAL_ROWS = 80;
const FiiDiiTable = memo(function FiiDiiTable({ rows, segment }: { rows: Row[]; segment: string }) {
  const isContracts = segment !== "equity";
  const [showAll, setShowAll] = useState(false);
  // Reset paging when the underlying dataset shape changes.
  useEffect(() => { setShowAll(false); }, [segment, rows.length]);
  if (!rows.length) {
    return <EmptyState title="No rows in this range" message="Try a wider time range." icon={<TableIcon className="w-6 h-6" />} />;
  }
  const visible = showAll ? rows : rows.slice(0, TABLE_INITIAL_ROWS);
  const hidden = rows.length - visible.length;
  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700 flex items-center justify-between bg-gray-50/60 dark:bg-gray-900/30">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <TableIcon className="w-4 h-4 text-indigo-500 dark:text-indigo-400" /> Daily Activity
        </h3>
        <span className="text-[11px] text-gray-500 dark:text-gray-400">
          {showAll ? `${rows.length} sessions` : `${visible.length} of ${rows.length} sessions`}
        </span>
      </div>
      <div className="overflow-x-auto max-h-[520px]">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10">
            <tr className="bg-gray-50 dark:bg-gray-900/70 backdrop-blur text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
              <th className="text-left  font-semibold px-4 py-2.5">Date</th>
              <th className="text-right font-semibold px-3 py-2.5">{isContracts ? "FII Long" : "FII Buy"}</th>
              <th className="text-right font-semibold px-3 py-2.5">{isContracts ? "FII Short" : "FII Sell"}</th>
              <th className="text-right font-semibold px-3 py-2.5">FII Net</th>
              <th className="text-right font-semibold px-3 py-2.5">{isContracts ? "DII Long" : "DII Buy"}</th>
              <th className="text-right font-semibold px-3 py-2.5">{isContracts ? "DII Short" : "DII Sell"}</th>
              <th className="text-right font-semibold px-4 py-2.5">DII Net</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700/60">
            {visible.map(r => (
              <tr key={r.date} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                <td className="px-4 py-2 font-medium text-gray-900 dark:text-white whitespace-nowrap">{r.displayDate || r.date}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">{fmtNumCell(r.fiiBuy)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">{fmtNumCell(r.fiiSell)}</td>
                <td className={`px-3 py-2 text-right tabular-nums font-semibold ${netClass(r.fiiNet)}`}>{fmtNumCell(r.fiiNet)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">{fmtNumCell(r.diiBuy)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">{fmtNumCell(r.diiSell)}</td>
                <td className={`px-4 py-2 text-right tabular-nums font-semibold ${netClass(r.diiNet)}`}>{fmtNumCell(r.diiNet)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hidden > 0 && (
        <div className="px-4 py-2.5 border-t border-gray-100 dark:border-gray-700 bg-gray-50/60 dark:bg-gray-900/30 flex items-center justify-center">
          <button
            type="button"
            onClick={() => setShowAll(true)}
            className="text-xs font-medium text-indigo-600 dark:text-indigo-300 hover:text-indigo-700 dark:hover:text-indigo-200"
          >
            Show all {rows.length} sessions ({hidden} more)
          </button>
        </div>
      )}
    </Card>
  );
});

function fmtNumCell(n: number | null | undefined) {
  if (n == null || isNaN(n)) return "—";
  return new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);
}

/* ── Month-wise breakdown ───────────────────────────────────────────── */
function MonthlyBreakdown({ months, isContracts, reduced }: {
  months: MonthBucket[]; isContracts: boolean; reduced: boolean;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 mt-2">
        <Calendar className="w-4 h-4 text-indigo-500 dark:text-indigo-400" />
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Month-wise Breakdown</h3>
        <span className="text-[11px] text-gray-500 dark:text-gray-400">({months.length} months)</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {months.map((m) => (
          <MonthCard key={m.key} month={m} isContracts={isContracts} reduced={reduced} />
        ))}
      </div>
    </div>
  );
}

const MonthCard = memo(function MonthCard({ month, isContracts, reduced }: {
  month: MonthBucket; isContracts: boolean; reduced: boolean;
}) {
  const [open, setOpen] = useState(false);
  const palette = useChartPalette();
  const total = month.fiiNet + month.diiNet;

  // Mini bar data — ascending so it reads left-to-right oldest → newest
  const miniData = useMemo(() =>
    [...month.rows].reverse().map((r) => ({
      label: r.displayDate?.slice(0, 6) || "",
      fii: r.fiiNet ?? 0,
      dii: r.diiNet ?? 0,
    })), [month.rows]);

  return (
    <motion.div
      initial={reduced ? { opacity: 0 } : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="relative overflow-hidden rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm"
    >
      <div className={`absolute inset-0 bg-gradient-to-br ${netGradient(total)} pointer-events-none`} />
      <div className="relative">
        {/* Header */}
        <button
          onClick={() => setOpen(o => !o)}
          className="w-full p-4 text-left flex items-start justify-between gap-3 hover:bg-gray-50/60 dark:hover:bg-gray-700/30 transition"
        >
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h4 className="text-sm font-bold text-gray-900 dark:text-white truncate">{month.label}</h4>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-600">
                {month.days} sessions
              </span>
            </div>
            <div className="flex items-center gap-3 text-[11px]">
              <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-300">
                <TrendingUp className="w-3 h-3" /> {month.greenDays}
              </span>
              <span className="inline-flex items-center gap-1 text-red-700 dark:text-red-300">
                <TrendingDown className="w-3 h-3" /> {month.redDays}
              </span>
            </div>
          </div>
          <ChevronDown className={`w-4 h-4 text-gray-400 dark:text-gray-500 mt-0.5 transition-transform ${open ? "rotate-180" : ""}`} />
        </button>

        {/* Stats row */}
        <div className="px-4 pb-2 grid grid-cols-2 gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">FII Net</div>
            <div className={`text-sm font-bold tabular-nums ${netClass(month.fiiNet)}`}>{fmtCompact(month.fiiNet, isContracts)}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">DII Net</div>
            <div className={`text-sm font-bold tabular-nums ${netClass(month.diiNet)}`}>{fmtCompact(month.diiNet, isContracts)}</div>
          </div>
        </div>

        {/* Mini chart — only mounts when the card scrolls into view, so
            the initial 13-card grid doesn't pay for 13 SVG charts at once. */}
        {miniData.length > 1 && (
          <VisibleOnce
            placeholder={<div className="h-20 px-2 pb-2"><div className="h-full rounded bg-gray-50/80 dark:bg-gray-800/40 animate-pulse" /></div>}
          >
            <div className="h-20 px-2 pb-2">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={miniData} margin={{ top: 2, right: 2, left: 2, bottom: 0 }}>
                  <ReferenceLine y={0} stroke={palette.border} strokeWidth={1} />
                  <Tooltip
                    contentStyle={{
                      background: palette.surf, border: `1px solid ${palette.border}`,
                      borderRadius: 8, color: palette.text, fontSize: 11, padding: "6px 8px",
                    }}
                    labelStyle={{ color: palette.muted, fontSize: 10, marginBottom: 2 }}
                    cursor={{ fill: palette.border, opacity: 0.2 }}
                    formatter={(v: number, n: string) => [fmtCr(v, isContracts), n === "fii" ? "FII" : "DII"]}
                  />
                  <Bar dataKey="fii" fill={palette.fii} maxBarSize={6} isAnimationActive={false} />
                  <Bar dataKey="dii" fill={palette.dii} maxBarSize={6} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </VisibleOnce>
        )}

        {/* Expanded daily table */}
        <AnimatePresence initial={false}>
          {open && (
            <motion.div
              key="expand"
              initial={reduced ? { opacity: 0 } : { opacity: 0, height: 0 }}
              animate={reduced ? { opacity: 1 } : { opacity: 1, height: "auto" }}
              exit={reduced ? { opacity: 0 } : { opacity: 0, height: 0 }}
              transition={{ duration: 0.25 }}
              className="overflow-hidden border-t border-gray-100 dark:border-gray-700"
            >
              <div className="overflow-x-auto max-h-72">
                <table className="w-full text-xs">
                  <thead className="sticky top-0">
                    <tr className="bg-gray-50 dark:bg-gray-900/70 backdrop-blur text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
                      <th className="text-left  font-semibold px-3 py-2">Date</th>
                      <th className="text-right font-semibold px-2 py-2">FII Net</th>
                      <th className="text-right font-semibold px-3 py-2">DII Net</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 dark:divide-gray-700/50">
                    {month.rows.map(r => (
                      <tr key={r.date} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                        <td className="px-3 py-1.5 font-medium text-gray-900 dark:text-white whitespace-nowrap">{r.displayDate || r.date}</td>
                        <td className={`px-2 py-1.5 text-right tabular-nums ${netClass(r.fiiNet)}`}>{fmtNumCell(r.fiiNet)}</td>
                        <td className={`px-3 py-1.5 text-right tabular-nums ${netClass(r.diiNet)}`}>{fmtNumCell(r.diiNet)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
});
