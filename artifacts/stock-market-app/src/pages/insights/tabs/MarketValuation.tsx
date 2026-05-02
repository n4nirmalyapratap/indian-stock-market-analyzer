import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, PillTabs, Card, Loading, EmptyState, MenuDropdown, ErrorState, useChartPalette } from "../_shared";
import { LineChart as LCIcon, X } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, Legend, CartesianGrid } from "recharts";
import DataFreshness from "@/components/DataFreshness";
import { pickMeta, marketDataQueryOptions } from "@/lib/marketData";

type Period = "1m" | "6m" | "1y" | "5y" | "10y";
type Metric = "pe" | "pb" | "dy";

interface PointBag { date: string; [key: string]: number | string; }

interface ValuationResponse {
  available: boolean;
  message?: string;
  series: PointBag[];
  indices: { code: string; label: string; lastPrice?: number; change?: number; changePct?: number; }[];
}

// Comprehensive list of NSE indices that have constituent data on yfinance.
const ALL_INDEX_OPTIONS = [
  { code: "^NSEI",                 label: "NIFTY 50" },
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
];

// Distinct, accessible chart colors that work in both themes.
const CHART_COLORS = [
  "#6366f1", // indigo
  "#10b981", // emerald
  "#f59e0b", // amber
  "#ec4899", // pink
  "#06b6d4", // cyan
  "#a855f7", // purple
  "#ef4444", // rose
  "#84cc16", // lime
  "#3b82f6", // blue
  "#f97316", // orange
];

export default function MarketValuation() {
  const [period, setPeriod] = useState<Period>("5y");
  const [metric, setMetric] = useState<Metric>("pe");
  const [selected, setSelected] = useState<string[]>(["^NSEI", "^NSEBANK"]);
  const [adding, setAdding] = useState("");

  const codes = selected.join(",");

  const palette = useChartPalette();
  const cBorder = palette.border;
  const cMuted  = palette.muted;
  const cText   = palette.text;
  const cSurf   = palette.surf;
  const cAccent = palette.accent;

  const { data, isLoading, error } = useQuery<ValuationResponse>(
    marketDataQueryOptions<ValuationResponse, { enabled: boolean }>(
      ["insights/index-valuation", codes, period, metric],
      () => fetchApi(`/insights/index-valuation?indices=${encodeURIComponent(codes)}&period=${period}&metric=${metric}`),
      { enabled: codes.length > 0 },
    ),
  );
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

  return (
    <div>
      <PageHeader title="Market Valuation"
        info="Historical price levels of selected indices. Add or remove sectors to compare."/>

      <div className="mb-3">
        <DataFreshness meta={valuationMeta} refreshKeys={[["insights/index-valuation", codes, period, metric]]} />
      </div>

      {/* Selected sector cards */}
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
                    <span className="font-semibold text-gray-900 dark:text-white">{meta.lastPrice?.toFixed(2)}</span>
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

        {/* Add another sector */}
        {addable.length > 0 && selected.length < 6 && (
          <MenuDropdown
            label="+ Add"
            value={adding as string}
            onChange={(v) => add(v as string)}
            options={addable.map(o => ({ value: o.code, label: o.label }))}
            placeholder="Pick a sector"
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
        <PillTabs value={metric} onChange={(v) => setMetric(v as Metric)} options={[
          {value:"pe",label:"Price"},{value:"pb",label:"Normalized"},{value:"dy",label:"% Change"},
        ]}/>
      </div>

      {isLoading && <Loading />}
      {!isLoading && data && data.series.length === 0 && (
        <EmptyState
          icon={<LCIcon className="w-10 h-10" />}
          title="No valuation history"
          message={data.message || "Index valuation history not currently available."}
        />
      )}

      {data && data.series.length > 0 && (
        <Card className="p-4">
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
                />
                <Legend wrapperStyle={{ fontSize: 12, color: cText }} />
                {selected.map((code, i) => {
                  const lbl = labelFor(code);
                  return (
                    <Line key={code}
                          type="monotone"
                          dataKey={lbl}
                          stroke={CHART_COLORS[i % CHART_COLORS.length]}
                          dot={false}
                          strokeWidth={2}
                          connectNulls />
                  );
                })}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}
    </div>
  );
}
