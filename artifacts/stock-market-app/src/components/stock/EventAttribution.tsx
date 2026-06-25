import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import {
  ResponsiveContainer, ComposedChart, Line,
  XAxis, YAxis, Tooltip, CartesianGrid,
} from "recharts";
import {
  TrendingUp, TrendingDown, Loader2, AlertCircle,
  GitBranch, Newspaper, ExternalLink, Search,
} from "lucide-react";

// ── Types ──────────────────────────────────────────────────────────────────────

interface Headline {
  title:  string;
  url:    string;
  source: string;
}

interface SwingEvent {
  date:          string;
  price:         number;
  move_pct:      number;
  direction:     "peak" | "trough";
  reason?:       string;
  context_tags?: string[];
  headlines?:    Headline[];
  search_url?:   string;
}

interface ChartPoint {
  date:  string;
  close: number;
  event: SwingEvent | null;
}

// ── Context tag styling ────────────────────────────────────────────────────────

const TAG_STYLES: Record<string, string> = {
  "Union Budget":          "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  "RBI MPC":               "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
  "F&O Monthly Expiry":    "bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300",
  "Results Season":        "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  "Index Rebalancing":     "bg-slate-100 text-slate-700 dark:bg-slate-700/40 dark:text-slate-300",
};

function tagStyle(tag: string): string {
  for (const [key, cls] of Object.entries(TAG_STYLES)) {
    if (tag.includes(key)) return cls;
  }
  return "bg-gray-100 text-gray-700 dark:bg-gray-700/40 dark:text-gray-300";
}

// ── Chart helpers ──────────────────────────────────────────────────────────────

const PEAK_COLOR   = "#10b981";
const TROUGH_COLOR = "#ef4444";

function fmtDateTick(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-IN", { month: "short", year: "2-digit" });
}

function fmtPrice(v: number): string {
  if (v >= 1000) return `₹${(v / 1000).toFixed(1)}K`;
  return `₹${v.toFixed(0)}`;
}

const CustomDot = (props: any) => {
  const { cx, cy, payload } = props;
  if (!payload?.event) return null;
  const isPeak = payload.event.direction === "peak";
  const color  = isPeak ? PEAK_COLOR : TROUGH_COLOR;
  const s = 7;
  const pts = isPeak
    ? `${cx},${cy - s} ${cx - s * 0.87},${cy + s * 0.5} ${cx + s * 0.87},${cy + s * 0.5}`
    : `${cx},${cy + s} ${cx - s * 0.87},${cy - s * 0.5} ${cx + s * 0.87},${cy - s * 0.5}`;
  return <polygon points={pts} fill={color} stroke="white" strokeWidth={1} />;
};

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload as ChartPoint;
  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg p-2.5 shadow-lg text-xs max-w-[220px]">
      <p className="font-medium text-gray-900 dark:text-white">{d.date}</p>
      <p className="text-indigo-600 dark:text-indigo-400 font-bold">₹{d.close.toFixed(2)}</p>
      {d.event && (
        <>
          <p className={`mt-1 font-semibold ${d.event.direction === "peak" ? "text-emerald-600" : "text-red-500"}`}>
            {d.event.direction === "peak" ? "▲ Peak" : "▼ Trough"}&nbsp;
            {d.event.move_pct > 0 ? "+" : ""}{d.event.move_pct}%
          </p>
          {(d.event.context_tags ?? []).length > 0 && (
            <p className="mt-1 text-gray-500 dark:text-gray-400">
              {d.event.context_tags!.join(" · ")}
            </p>
          )}
        </>
      )}
    </div>
  );
};

// ── EventRow ───────────────────────────────────────────────────────────────────

function EventRow({ ev, idx }: { ev: SwingEvent; idx: number }) {
  const [showAll, setShowAll] = useState(false);

  const isPeak      = ev.direction === "peak";
  const moveCls     = isPeak
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-red-500 dark:text-red-400";
  const dateStr     = new Date(ev.date).toLocaleDateString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
  });

  const tags      = ev.context_tags ?? [];
  const headlines = ev.headlines   ?? [];
  const hasContext = tags.length > 0 || headlines.length > 0;

  return (
    <tr className={`border-b border-gray-100 dark:border-gray-700/60 hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors ${idx % 2 !== 0 ? "bg-gray-50/50 dark:bg-gray-800/30" : ""}`}>

      {/* Icon */}
      <td className="py-3 pl-4 pr-2 w-8 align-top">
        {isPeak
          ? <TrendingUp  className="w-4 h-4 text-emerald-500 mt-0.5" />
          : <TrendingDown className="w-4 h-4 text-red-400 mt-0.5" />}
      </td>

      {/* Date */}
      <td className="py-3 pr-4 text-xs font-mono text-gray-700 dark:text-gray-300 whitespace-nowrap align-top">
        {dateStr}
      </td>

      {/* Type */}
      <td className={`py-3 pr-4 text-xs font-semibold whitespace-nowrap align-top ${moveCls}`}>
        {isPeak ? "Peak" : "Trough"}
      </td>

      {/* Price */}
      <td className="py-3 pr-4 text-sm font-bold text-gray-900 dark:text-white whitespace-nowrap align-top">
        ₹{ev.price.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </td>

      {/* Move % */}
      <td className={`py-3 pr-4 text-sm font-semibold whitespace-nowrap align-top ${moveCls}`}>
        {ev.move_pct > 0 ? "+" : ""}{ev.move_pct}%
      </td>

      {/* What happened */}
      <td className="py-3 pr-4 align-top max-w-xs lg:max-w-md">
        <div className="space-y-2">

          {/* Calendar context tags */}
          {tags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {tags.map(tag => (
                <span
                  key={tag}
                  className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold leading-none ${tagStyle(tag)}`}
                >
                  {tag}
                </span>
              ))}
            </div>
          )}

          {/* Real news headlines (when matched) */}
          {headlines.length > 0 && (
            <div className="space-y-1">
              {(showAll ? headlines : headlines.slice(0, 1)).map((h, i) => (
                <a
                  key={i}
                  href={h.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-start gap-1.5 group text-xs text-gray-600 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
                >
                  <Newspaper className="w-3 h-3 mt-0.5 shrink-0 text-gray-400 group-hover:text-indigo-500" />
                  <span className="leading-snug">
                    {h.title}
                    {h.source && (
                      <span className="ml-1 text-gray-400 dark:text-gray-500 font-normal">
                        — {h.source}
                      </span>
                    )}
                  </span>
                  <ExternalLink className="w-2.5 h-2.5 mt-0.5 shrink-0 opacity-0 group-hover:opacity-60" />
                </a>
              ))}
              {headlines.length > 1 && (
                <button
                  onClick={() => setShowAll(s => !s)}
                  className="text-[10px] text-indigo-500 hover:text-indigo-700 dark:text-indigo-400"
                >
                  {showAll ? "show less" : `+${headlines.length - 1} more`}
                </button>
              )}
            </div>
          )}

          {/* No real data yet — small hint */}
          {!hasContext && (
            <span className="text-xs text-gray-400 dark:text-gray-500 italic">
              No calendar event matched
            </span>
          )}

          {/* Search link — always shown, primary CTA */}
          {ev.search_url && (
            <a
              href={ev.search_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-indigo-200 dark:border-indigo-700 text-[11px] font-medium text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 transition-colors"
            >
              <Search className="w-2.5 h-2.5" />
              Find reason on Google
            </a>
          )}
        </div>
      </td>
    </tr>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

interface Props {
  symbol:       string;
  companyName?: string;
}

export default function EventAttribution({ symbol, companyName }: Props) {
  const company = encodeURIComponent(companyName ?? "");

  const { data, isLoading, error } = useQuery<any>({
    queryKey: ["event-attribution", symbol, companyName],
    queryFn:  () => fetchApi(
      `/stocks/${encodeURIComponent(symbol)}/event-attribution?company=${company}`
    ),
    staleTime: 24 * 60 * 60_000,
    enabled:  !!symbol,
  });

  const chartData = useMemo<ChartPoint[]>(() => {
    if (!data?.prices) return [];
    const eventMap = new Map<string, SwingEvent>(
      (data.events ?? []).map((e: SwingEvent) => [e.date, e]),
    );
    return data.prices.map((p: { date: string; close: number }) => ({
      date:  p.date,
      close: p.close,
      event: eventMap.get(p.date) ?? null,
    }));
  }, [data]);

  const xTicks = useMemo(() => {
    if (!chartData.length) return [];
    const step = Math.max(1, Math.floor(chartData.length / 10));
    return chartData.filter((_, i) => i % step === 0).map(d => d.date);
  }, [chartData]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-gray-400 dark:text-gray-500">
        <Loader2 className="w-7 h-7 animate-spin text-indigo-500" />
        <p className="text-sm font-medium">Analysing price history…</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex items-center gap-3 p-4 text-sm text-red-600 bg-red-50 dark:bg-red-900/20 dark:text-red-400 rounded-xl border border-red-200 dark:border-red-800">
        <AlertCircle className="w-5 h-5 shrink-0" />
        Unable to load price history. Please try again.
      </div>
    );
  }

  const events: SwingEvent[] = data.events ?? [];
  const taggedCount    = events.filter(e => (e.context_tags?.length ?? 0) > 0).length;
  const headlineCount  = events.filter(e => (e.headlines?.length   ?? 0) > 0).length;

  return (
    <div className="space-y-6">

      {/* ── Chart ── */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 shadow-sm p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Price History</h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              <span className="text-emerald-500 font-bold">▲</span> Peaks &nbsp;
              <span className="text-red-400 font-bold">▼</span> Troughs
              {chartData.length > 0 && (
                <> &nbsp;· {chartData[0].date} → {chartData[chartData.length - 1].date}</>
              )}
            </p>
          </div>
          <span className="text-xs text-gray-400 dark:text-gray-500">{events.length} swings</span>
        </div>
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={chartData} margin={{ top: 10, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" strokeOpacity={0.4} />
            <XAxis
              dataKey="date"
              ticks={xTicks}
              tickFormatter={fmtDateTick}
              tick={{ fontSize: 10, fill: "#9ca3af" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tickFormatter={fmtPrice}
              tick={{ fontSize: 10, fill: "#9ca3af" }}
              axisLine={false}
              tickLine={false}
              width={50}
            />
            <Tooltip content={<CustomTooltip />} />
            <Line
              type="monotone"
              dataKey="close"
              stroke="#6366f1"
              strokeWidth={1.5}
              dot={<CustomDot />}
              activeDot={{ r: 4, fill: "#6366f1" }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* ── Table ── */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 shadow-sm overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-gray-100 dark:border-gray-700">
          <GitBranch className="w-4 h-4 text-indigo-500" />
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Swing Timeline</h3>

          {taggedCount > 0 && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 text-xs font-medium">
              🗓 {taggedCount} calendar events matched
            </span>
          )}
          {headlineCount > 0 && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 text-xs font-medium">
              <Newspaper className="w-2.5 h-2.5" /> {headlineCount} with news
            </span>
          )}

          <span className="ml-auto text-xs text-gray-400 dark:text-gray-500 hidden sm:block">
            Click "Find reason on Google" for full context
          </span>
        </div>

        {events.length === 0 ? (
          <p className="text-sm text-gray-400 dark:text-gray-500 text-center py-10">
            No significant swings detected (all moves &lt; 15%).
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-gray-100 dark:border-gray-700">
                  <th className="py-2 pl-4 pr-2 w-8" />
                  <th className="py-2 pr-4 text-xs font-semibold text-gray-400 uppercase tracking-wide whitespace-nowrap">Date</th>
                  <th className="py-2 pr-4 text-xs font-semibold text-gray-400 uppercase tracking-wide">Type</th>
                  <th className="py-2 pr-4 text-xs font-semibold text-gray-400 uppercase tracking-wide">Price</th>
                  <th className="py-2 pr-4 text-xs font-semibold text-gray-400 uppercase tracking-wide">Move</th>
                  <th className="py-2 pr-4 text-xs font-semibold text-gray-400 uppercase tracking-wide">What happened</th>
                </tr>
              </thead>
              <tbody>
                {events.map((ev, i) => (
                  <EventRow key={ev.date + ev.direction} ev={ev} idx={i} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Legend ── */}
      <div className="flex flex-wrap gap-3 text-[11px] text-gray-500 dark:text-gray-400 px-1 pb-1">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-sm bg-amber-400 inline-block" /> Union Budget
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-sm bg-blue-400 inline-block" /> RBI MPC Decision
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-sm bg-purple-400 inline-block" /> F&amp;O Expiry
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-sm bg-emerald-400 inline-block" /> Earnings Season
        </span>
        <span className="ml-auto opacity-60">AI explanations coming soon</span>
      </div>
    </div>
  );
}
