import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, PillTabs, Card, Loading, EmptyState, MenuDropdown, useChartPalette } from "../_shared";
import { LineChart as LCIcon, X, Info } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, Legend, CartesianGrid } from "recharts";
import DataFreshness from "@/components/DataFreshness";
import { pickMeta, marketDataQueryOptions } from "@/lib/marketData";

type Period = "1m" | "6m" | "1y" | "5y" | "10y";
type Metric = "price" | "indexed" | "change";

interface PointBag { date: string; [key: string]: number | string; }

interface ValuationResponse {
  available: boolean;
  message?: string;
  metric?: Metric;
  series: PointBag[];
  indices: { code: string; label: string; lastPrice?: number; change?: number; changePct?: number; }[];
}

// Comprehensive list of indices available on yfinance.
const ALL_INDEX_OPTIONS = [
  // ── India ──
  { code: "^NSEI",                 label: "NIFTY 50" },
  { code: "^BSESN",               label: "SENSEX" },
  { code: "^NSEBANK",              label: "NIFTY BANK" },
  { code: "^CNXIT",                label: "NIFTY IT" },
  { code: "^CNXFMCG",              label: "NIFTY FMCG" },
  { code: "^CNXAUTO",              label: "NIFTY AUTO" },
  { code: "^CNXPHARMA",            label: "NIFTY PHARMA" },
  { code: "^CNXMETAL",             label: "NIFTY METAL" },
  { code: "^CNXENERGY",            label: "NIFTY ENERGY" },
  { code: "^CNXREALTY",            label: "NIFTY REALTY" },
  { code: "^CNXMEDIA",             label: "NIFTY MEDIA" },
  { code: "^CNXPSUBANK",           label: "NIFTY PSU BANK" },
  { code: "^CNXPSE",               label: "NIFTY PSE" },
  { code: "^CNXINFRA",             label: "NIFTY INFRA" },
  { code: "NIFTY_FIN_SERVICE.NS",  label: "NIFTY FINANCIAL SERVICES" },
  { code: "^NSMIDCP",              label: "NIFTY MIDCAP 100" },
  { code: "^CNXSC",                label: "NIFTY SMALLCAP 100" },
  { code: "^CNX100",               label: "NIFTY 100" },
  { code: "^CNX200",               label: "NIFTY 200" },
  { code: "^CRSLDX",               label: "NIFTY 500" },
  // ── Americas ──
  { code: "^GSPC",                 label: "S&P 500 (US)" },
  { code: "^DJI",                  label: "Dow Jones (US)" },
  { code: "^IXIC",                 label: "NASDAQ (US)" },
  // ── Europe ──
  { code: "^FTSE",                 label: "FTSE 100 (UK)" },
  { code: "^GDAXI",                label: "DAX (Germany)" },
  { code: "^FCHI",                 label: "CAC 40 (France)" },
  { code: "^STOXX50E",             label: "Euro Stoxx 50" },
  // ── Asia Pacific ──
  { code: "^N225",                 label: "Nikkei 225 (Japan)" },
  { code: "^HSI",                  label: "Hang Seng (HK)" },
  { code: "000001.SS",             label: "Shanghai Comp. (China)" },
  { code: "^KS11",                 label: "KOSPI (South Korea)" },
  { code: "^AXJO",                 label: "ASX 200 (Australia)" },
];

// Distinct, accessible chart colors that work in both themes.
const CHART_COLORS = [
  "#6366f1", "#10b981", "#f59e0b", "#ec4899", "#06b6d4",
  "#a855f7", "#ef4444", "#84cc16", "#3b82f6", "#f97316",
];

const METRIC_OPTIONS: { value: Metric; label: string }[] = [
  { value: "indexed", label: "Indexed (100)" },
  { value: "price",   label: "Price" },
  { value: "change",  label: "% Change" },
];

const formatValue = (v: number | string | undefined, metric: Metric) => {
  if (v === undefined || v === null || v === "") return "—";
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return "—";
  if (metric === "change") return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
  if (metric === "price")  return n.toLocaleString("en-IN", { maximumFractionDigits: 2 });
  return n.toFixed(2); // indexed → 100-based
};

export default function MarketValuation() {
  const [period, setPeriod] = useState<Period>("5y");
  const [metric, setMetric] = useState<Metric>("indexed");
  const [selected, setSelected] = useState<string[]>(["^NSEI", "^NSEBANK"]);
  const [adding, setAdding] = useState("");

  const codes = selected.join(",");

  const palette = useChartPalette();
  const { border: cBorder, muted: cMuted, text: cText, surf: cSurf, accent: cAccent } = palette;

  const { data, isLoading, isFetching } = useQuery<ValuationResponse>(
    marketDataQueryOptions<ValuationResponse, { enabled: boolean; placeholderData: (prev: ValuationResponse | undefined) => ValuationResponse | undefined }>(
      ["insights/index-valuation", codes, period, metric],
      () => fetchApi(`/insights/index-valuation?indices=${encodeURIComponent(codes)}&period=${period}&metric=${metric}`),
      { enabled: codes.length > 0, placeholderData: (prev) => prev },
    ),
  );
  // Show data the moment we have any (placeholderData = previous response).
  // `isFetching && !isLoading` means a background refetch is in flight — dim
  // the chart slightly so the user sees something is happening but the page
  // doesn't go fully blank.
  const isRefetching = isFetching && !isLoading;
  const valuationMeta = pickMeta(data);

  const addable = useMemo(
    () => ALL_INDEX_OPTIONS.filter(o => !selected.includes(o.code)),
    [selected],
  );

  const remove = (code: string) => setSelected(s => s.filter(c => c !== code));
  const add = (code: string) => {
    if (!code || selected.includes(code) || selected.length >= 6) return;
    setSelected(s => [...s, code]);
    setAdding("");
  };

  const labelFor = (code: string) =>
    ALL_INDEX_OPTIONS.find(o => o.code === code)?.label || code;

  const subtitle =
    metric === "indexed" ? "Compare relative performance of Indian and global indices, rebased to 100 at the start of the window."
    : metric === "price" ? "Daily closing levels of selected indices."
    : "Percent change of each index from the start of the window.";

  return (
    <div>
      <PageHeader title="Index Comparison" info={subtitle}/>

      <div className="mb-3">
        <DataFreshness meta={valuationMeta} refreshKeys={[["insights/index-valuation", codes, period, metric]]} />
      </div>

      {/* Selected index cards */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        {selected.map((code, i) => {
          const meta = data?.indices?.find(x => x.code === code);
          const color = CHART_COLORS[i % CHART_COLORS.length];
          return (
            <Card key={code} className="px-3 py-2 flex items-center gap-2.5 group">
              <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
              <div className="min-w-0">
                <p className="text-xs font-bold text-gray-900 dark:text-white leading-tight truncate max-w-[160px]" title={labelFor(code)}>
                  {labelFor(code)}
                </p>
                {meta?.lastPrice != null && (
                  <p className="text-[11px] tabular-nums leading-tight">
                    <span className="font-semibold text-gray-900 dark:text-white">
                      {meta.lastPrice.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
                    </span>
                    <span className={`ml-1 ${(meta.change ?? 0) >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-500"}`}>
                      {(meta.change ?? 0) >= 0 ? "+" : ""}{meta.changePct?.toFixed(2)}%
                    </span>
                  </p>
                )}
              </div>
              {selected.length > 1 && (
                <button onClick={() => remove(code)}
                        className="ml-1 w-5 h-5 rounded hover:bg-red-100 dark:hover:bg-red-900/20 text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 transition flex items-center justify-center opacity-0 group-hover:opacity-100"
                        title="Remove">
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </Card>
          );
        })}

        {/* Add another index */}
        {addable.length > 0 && selected.length < 6 && (
          <MenuDropdown
            label="+ Add"
            value={adding as string}
            onChange={(v) => add(v as string)}
            options={addable.map(o => ({ value: o.code, label: o.label }))}
            placeholder="Pick an index"
            minButtonWidth={150}
            maxButtonWidth={240}
          />
        )}
      </div>

      {/* Period & metric controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <PillTabs value={period} onChange={(v) => setPeriod(v as Period)} options={[
          {value:"1m",label:"1M"},{value:"6m",label:"6M"},{value:"1y",label:"1Y"},{value:"5y",label:"5Y"},{value:"10y",label:"10Y"},
        ]}/>
        <PillTabs value={metric} onChange={(v) => setMetric(v as Metric)} options={METRIC_OPTIONS}/>
      </div>

      {isLoading && <Loading />}
      {!isLoading && data && data.series.length === 0 && (
        <EmptyState
          icon={<LCIcon className="w-10 h-10" />}
          title="No history available"
          message={data.message || "Index history not currently available."}
        />
      )}

      {data && data.series.length > 0 && (
        <Card className={`p-4 transition-opacity duration-200 ${isRefetching ? "opacity-60" : "opacity-100"}`}>
          <div className="h-[460px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.series} margin={{ top: 8, right: 16, left: -8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={cBorder} strokeOpacity={0.5}/>
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11, fill: cMuted }}
                  stroke={cBorder}
                  minTickGap={40}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: cMuted }}
                  stroke={cBorder}
                  width={56}
                  tickFormatter={(v) => formatValue(v, metric)}
                  domain={metric === "change" ? ["auto", "auto"] : ["auto", "auto"]}
                />
                <Tooltip
                  contentStyle={{
                    background: cSurf,
                    border: `1px solid ${cBorder}`,
                    borderRadius: 8,
                    color: cText,
                    fontSize: 12,
                  }}
                  labelStyle={{ color: cMuted, marginBottom: 4 }}
                  cursor={{ stroke: cAccent, strokeOpacity: 0.3 }}
                  formatter={(value: number | string, name: string) => [formatValue(value, metric), labelFor(name)]}
                />
                <Legend
                  wrapperStyle={{ fontSize: 12, color: cText }}
                  formatter={(value: string) => labelFor(value)}
                />
                {selected.map((code, i) => (
                  <Line key={code}
                        type="monotone"
                        dataKey={code}
                        name={code}
                        stroke={CHART_COLORS[i % CHART_COLORS.length]}
                        dot={false}
                        strokeWidth={2}
                        connectNulls />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          {data.message && (
            <p className="mt-3 flex items-start gap-1.5 text-[11px] text-gray-500 dark:text-gray-400">
              <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
              <span>{data.message}</span>
            </p>
          )}
        </Card>
      )}
    </div>
  );
}
