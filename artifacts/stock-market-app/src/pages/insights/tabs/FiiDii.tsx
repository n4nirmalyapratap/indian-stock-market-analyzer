import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import {
  PageHeader, PillTabs, Card, Loading, ErrorState,
  EmptyState, MenuDropdown, useChartPalette, fmtNum,
} from "../_shared";
import {
  ResponsiveContainer, ComposedChart, CartesianGrid, XAxis, YAxis,
  Tooltip, Legend, Bar, ReferenceLine,
} from "recharts";
import { ArrowDownUp, BarChart3, Table as TableIcon, Info, ExternalLink } from "lucide-react";

type Segment = "equity" | "index_future" | "index_option" | "stock_future" | "stock_option";
type View = "table" | "chart";
type Range = "30d" | "90d" | "180d" | "all";

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

interface FiiDiiResponse {
  available: boolean;
  segment: string;
  source: string;
  sourceUrl: string;
  latest: Row | null;
  rows: Row[];                                 // descending by date
  summary: { daily: SummaryCell; weekly: SummaryCell; monthly: SummaryCell };
  message?: string | null;
}

const SEGMENT_OPTIONS: { value: Segment; label: string }[] = [
  { value: "equity",         label: "Equity" },
  { value: "index_future",   label: "Index Future" },
  { value: "index_option",   label: "Index Option" },
  { value: "stock_future",   label: "Stock Future" },
  { value: "stock_option",   label: "Stock Options" },
];

const RANGE_OPTIONS: { value: Range; label: string }[] = [
  { value: "30d",  label: "Last 30 days" },
  { value: "90d",  label: "Last 90 days" },
  { value: "180d", label: "Last 180 days" },
  { value: "all",  label: "All available" },
];

function rangeLimit(r: Range): number {
  return r === "30d" ? 30 : r === "90d" ? 90 : r === "180d" ? 180 : 9999;
}

/** Format a Cr-rupee value with sign, e.g. "+₹4,700.71 Cr" / "−₹8,827.87 Cr". */
function fmtCr(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  const abs = Math.abs(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${sign}₹${abs} Cr`;
}

function netClass(v: number | null | undefined): string {
  if (v === null || v === undefined) return "text-gray-500 dark:text-gray-400";
  if (v > 0) return "text-emerald-600 dark:text-emerald-400";
  if (v < 0) return "text-red-600 dark:text-red-400";
  return "text-gray-500 dark:text-gray-400";
}

export default function FiiDii() {
  const [segment, setSegment] = useState<Segment>("equity");
  const [view, setView] = useState<View>("table");
  const [range, setRange] = useState<Range>("30d");

  const { data, isLoading, error } = useQuery<FiiDiiResponse>({
    queryKey: ["insights/fii-dii", segment],
    queryFn: () => fetchApi(`/insights/fii-dii?segment=${segment}`),
    staleTime: 10 * 60_000,
  });

  return (
    <div>
      <PageHeader
        title="FII / DII Activity"
        info="Daily provisional cash-market trades by Foreign and Domestic Institutional Investors. Equity data is fetched live from NSE; a rolling history is built up day by day."
        right={data?.sourceUrl ? (
          <a href={data.sourceUrl} target="_blank" rel="noreferrer noopener"
             className="hidden md:inline-flex items-center gap-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition">
            Source: {data.source} <ExternalLink className="w-3.5 h-3.5" />
          </a>
        ) : undefined}
      />

      {/* Sub-tab strip */}
      <div className="mb-4">
        <PillTabs
          value={segment}
          onChange={(v) => setSegment(v as Segment)}
          options={SEGMENT_OPTIONS}
        />
      </div>

      {isLoading ? (
        <Loading />
      ) : error ? (
        <ErrorState message="We couldn't load FII/DII data. Please try again in a moment." />
      ) : !data?.available ? (
        <EmptyState
          icon={<BarChart3 className="w-6 h-6" />}
          title={`${SEGMENT_OPTIONS.find(s => s.value === segment)?.label} flows are not available right now`}
          message={data?.message || "No data returned. Try again later."}
        />
      ) : (
        <Body data={data} view={view} setView={setView} range={range} setRange={setRange} />
      )}
    </div>
  );
}

function Body({ data, view, setView, range, setRange }: {
  data: FiiDiiResponse;
  view: View; setView: (v: View) => void;
  range: Range; setRange: (r: Range) => void;
}) {
  const rows = useMemo(() => data.rows.slice(0, rangeLimit(range)), [data.rows, range]);
  const totalDays = data.rows.length;

  return (
    <div className="space-y-5">
      {/* Summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <SummaryCard title="Daily"   cell={data.summary.daily}   sub="Provisional cash trades on the latest session" />
        <SummaryCard title="Weekly"  cell={data.summary.weekly}  sub="Sum of net flows over the last 5 trading days" />
        <SummaryCard title="Monthly" cell={data.summary.monthly} sub="Sum of net flows over the last 22 trading days" />
      </div>

      {/* Toolbar */}
      <Card className="p-3">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setView("table")}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition border whitespace-nowrap
                ${view === "table"
                  ? "bg-indigo-600 text-white border-indigo-600 dark:bg-indigo-500 dark:border-indigo-500"
                  : "bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700"}`}
            >
              <TableIcon className="w-3.5 h-3.5" /> Table view
            </button>
            <button
              onClick={() => setView("chart")}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition border whitespace-nowrap
                ${view === "chart"
                  ? "bg-indigo-600 text-white border-indigo-600 dark:bg-indigo-500 dark:border-indigo-500"
                  : "bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700"}`}
            >
              <BarChart3 className="w-3.5 h-3.5" /> Chart view
            </button>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden sm:inline text-xs text-gray-500 dark:text-gray-400">
              <ArrowDownUp className="w-3 h-3 inline mr-1" /> Range
            </span>
            <MenuDropdown
              value={range}
              options={RANGE_OPTIONS}
              onChange={(v) => setRange((v || "30d") as Range)}
              minButtonWidth={160}
            />
          </div>
        </div>
        <p className="mt-2 text-[11px] text-gray-500 dark:text-gray-400 flex items-start gap-1.5">
          <Info className="w-3 h-3 flex-shrink-0 mt-0.5" />
          Showing {Math.min(rows.length, rangeLimit(range))} of {totalDays} day(s) on file.
          {totalDays < 5 && " History is being built up — this dashboard records each new trading day's snapshot."}
        </p>
      </Card>

      {/* Body */}
      {view === "table" ? <FiiDiiTable rows={rows} /> : <FiiDiiChart rows={rows} />}
    </div>
  );
}

function SummaryCard({ title, cell, sub }: { title: string; cell: SummaryCell | undefined; sub: string }) {
  // Defend against an empty `cell` (e.g. derivatives segments where the
  // service returns `summary: { daily: {}, weekly: {}, monthly: {} }`).
  const c: SummaryCell = cell ?? { fiiNet: null, diiNet: null, label: null };
  const partial = c.isPartial && c.expectedDays && c.days !== undefined && c.days > 0;
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-3 gap-2">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          {title}
          {partial && (
            <span title={`Computed over ${c.days} of ${c.expectedDays} expected trading days`}
                  className="text-[9px] px-1.5 py-0.5 rounded bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-500/20 uppercase tracking-wide">
              Partial · {c.days}/{c.expectedDays}d
            </span>
          )}
        </h3>
        {c.label && (
          <span className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500 whitespace-nowrap">
            since {c.label}
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1">FII Net</div>
          <div className={`text-lg font-bold ${netClass(c.fiiNet)}`}>{fmtCr(c.fiiNet)}</div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1">DII Net</div>
          <div className={`text-lg font-bold ${netClass(c.diiNet)}`}>{fmtCr(c.diiNet)}</div>
        </div>
      </div>
      <p className="mt-3 text-[11px] text-gray-500 dark:text-gray-400">{sub}</p>
    </Card>
  );
}

function FiiDiiTable({ rows }: { rows: Row[] }) {
  if (!rows.length) {
    return <EmptyState title="No rows in this range" message="Try a wider time range." icon={<TableIcon className="w-6 h-6" />} />;
  }
  return (
    <Card className="p-0 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 dark:bg-gray-900/40 text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
              <th className="text-left  font-semibold px-4 py-2.5">Date</th>
              <th className="text-right font-semibold px-3 py-2.5">FII Buy</th>
              <th className="text-right font-semibold px-3 py-2.5">FII Sell</th>
              <th className="text-right font-semibold px-3 py-2.5">FII Net</th>
              <th className="text-right font-semibold px-3 py-2.5">DII Buy</th>
              <th className="text-right font-semibold px-3 py-2.5">DII Sell</th>
              <th className="text-right font-semibold px-4 py-2.5">DII Net</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700/60">
            {rows.map(r => (
              <tr key={r.date} className="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition">
                <td className="px-4 py-2.5 font-medium text-gray-900 dark:text-white whitespace-nowrap">{r.displayDate || r.date}</td>
                <td className="px-3 py-2.5 text-right tabular-nums text-gray-700 dark:text-gray-300">{fmtNum(r.fiiBuy)}</td>
                <td className="px-3 py-2.5 text-right tabular-nums text-gray-700 dark:text-gray-300">{fmtNum(r.fiiSell)}</td>
                <td className={`px-3 py-2.5 text-right tabular-nums font-semibold ${netClass(r.fiiNet)}`}>{fmtNum(r.fiiNet)}</td>
                <td className="px-3 py-2.5 text-right tabular-nums text-gray-700 dark:text-gray-300">{fmtNum(r.diiBuy)}</td>
                <td className="px-3 py-2.5 text-right tabular-nums text-gray-700 dark:text-gray-300">{fmtNum(r.diiSell)}</td>
                <td className={`px-4 py-2.5 text-right tabular-nums font-semibold ${netClass(r.diiNet)}`}>{fmtNum(r.diiNet)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function FiiDiiChart({ rows }: { rows: Row[] }) {
  const palette = useChartPalette();
  // Recharts wants ascending order so bars read left-to-right oldest → newest.
  const data = useMemo(() => [...rows].reverse().map(r => ({
    label: (r.displayDate || r.date).slice(0, 6),
    fii: r.fiiNet ?? 0,
    dii: r.diiNet ?? 0,
  })), [rows]);

  if (!data.length) {
    return <EmptyState title="Nothing to plot yet" message="Once a few daily snapshots are collected, this chart will populate." icon={<BarChart3 className="w-6 h-6" />} />;
  }

  return (
    <Card className="p-4">
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 10, right: 12, left: 0, bottom: 8 }}>
            <CartesianGrid stroke={palette.border} strokeDasharray="2 4" vertical={false} />
            <XAxis dataKey="label" stroke={palette.muted} fontSize={11} tickLine={false} axisLine={{ stroke: palette.border }} />
            <YAxis stroke={palette.muted} fontSize={11} tickLine={false} axisLine={{ stroke: palette.border }}
                   tickFormatter={(v) => `${v >= 0 ? "" : "−"}${Math.abs(v).toLocaleString("en-IN")}`} />
            <Tooltip
              contentStyle={{
                background: palette.surf, border: `1px solid ${palette.border}`,
                borderRadius: 8, color: palette.text, fontSize: 12,
              }}
              labelStyle={{ color: palette.muted, fontSize: 11, marginBottom: 4 }}
              formatter={(value: number, name: string) => [fmtCr(value), name === "fii" ? "FII Net" : "DII Net"]}
            />
            <Legend wrapperStyle={{ fontSize: 12, color: palette.text }}
                    formatter={(v) => v === "fii" ? "FII Net" : "DII Net"} />
            <ReferenceLine y={0} stroke={palette.muted} strokeWidth={1} />
            <Bar dataKey="fii" name="fii" fill={palette.fii} radius={[3, 3, 0, 0]} maxBarSize={28} />
            <Bar dataKey="dii" name="dii" fill={palette.dii} radius={[3, 3, 0, 0]} maxBarSize={28} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-[11px] text-gray-500 dark:text-gray-400">
        Net flows in ₹ Cr. Positive bars indicate net buying, negative bars indicate net selling.
      </p>
    </Card>
  );
}
