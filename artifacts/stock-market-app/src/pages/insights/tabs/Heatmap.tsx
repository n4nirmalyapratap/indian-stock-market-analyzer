import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, Loading, ErrorState, EmptyState } from "../_shared";
import { LayoutGrid, ChevronDown, Check } from "lucide-react";

type Performance = "1d" | "1w" | "1m" | "1y";
type SortBy = "marketCap" | "name" | "change";

interface HeatmapItem {
  symbol: string;
  name: string;
  price: number;
  changePct: number;
  marketCap: number;
  color?: { bg: string; fg: string };
}

interface HeatmapResponse {
  available?: boolean;
  message?: string;
  index: string;
  label?: string;
  indexPrice?: number;
  indexChange?: number;
  indexChangePct?: number;
  items: HeatmapItem[];
}

interface IndexInfo { code: string; label: string; count: number; }

/** Modern, high-contrast palette computed client-side as a fallback when the
 *  server omits per-item colours. Returns hex pairs so the CSS works with
 *  inline `style` (bypasses any Tailwind JIT scanning of arbitrary values). */
function bucket(p: number | null | undefined): { bg: string; fg: string } {
  if (p == null || isNaN(p)) return { bg: "#94a3b8", fg: "#0f172a" };
  if (p <= -3)    return { bg: "#7f1d1d", fg: "#ffffff" };
  if (p <= -2)    return { bg: "#b91c1c", fg: "#ffffff" };
  if (p <= -1)    return { bg: "#dc2626", fg: "#ffffff" };
  if (p < -0.001) return { bg: "#ef4444", fg: "#ffffff" };
  if (p <  0.001) return { bg: "#64748b", fg: "#ffffff" };
  if (p <  1)     return { bg: "#16a34a", fg: "#ffffff" };
  if (p <  2)     return { bg: "#15803d", fg: "#ffffff" };
  if (p <  3)     return { bg: "#166534", fg: "#ffffff" };
  return            { bg: "#14532d", fg: "#ffffff" };
}

const PERF_OPTIONS: { value: Performance; label: string }[] = [
  { value: "1d", label: "1 Day" },
  { value: "1w", label: "1 Week" },
  { value: "1m", label: "1 Month" },
  { value: "1y", label: "1 Year" },
];
const SORT_OPTIONS: { value: SortBy; label: string }[] = [
  { value: "marketCap", label: "Market Cap" },
  { value: "name",      label: "Name (A–Z)" },
  { value: "change",    label: "% Change" },
];

function MenuDropdown<T extends string>({
  label, value, options, onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  const [open, setOpen] = useState(false);
  const current = options.find(o => o.value === value);
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        className="inline-flex items-center gap-2 text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-700/80 transition shadow-sm"
      >
        <span className="text-gray-500 dark:text-gray-400">{label}</span>
        <span className="font-semibold text-indigo-600 dark:text-indigo-400">{current?.label || value}</span>
        <ChevronDown className={`w-3.5 h-3.5 text-indigo-500 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute z-30 left-0 mt-1.5 min-w-[220px] max-h-[360px] overflow-y-auto rounded-xl border border-gray-200 dark:border-white/[0.08] bg-white dark:bg-gray-900 shadow-2xl py-1.5">
          {options.map(o => {
            const sel = o.value === value;
            return (
              <button
                key={o.value}
                type="button"
                onMouseDown={(e) => { e.preventDefault(); onChange(o.value); setOpen(false); }}
                className={`w-full text-left text-sm px-3.5 py-2 flex items-center justify-between transition
                  ${sel
                    ? "bg-indigo-50 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 font-semibold"
                    : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"}`}
              >
                <span>{o.label}</span>
                {sel && <Check className="w-4 h-4 text-indigo-500" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function Heatmap() {
  const [index, setIndex] = useState<string>("NIFTY50");
  const [perf, setPerf] = useState<Performance>("1d");
  const [sortBy, setSortBy] = useState<SortBy>("marketCap");

  const { data: idxList } = useQuery<{ indices: IndexInfo[] }>({
    queryKey: ["insights/indices"],
    queryFn: () => fetchApi(`/insights/indices`),
    staleTime: 60 * 60_000,
  });
  const indexOptions = useMemo(
    () => (idxList?.indices || []).map(i => ({ value: i.code, label: i.label })),
    [idxList],
  );

  const { data, isLoading, error } = useQuery<HeatmapResponse>({
    queryKey: ["insights/heatmap", index, perf],
    queryFn: () => fetchApi(`/insights/heatmap?index=${index}&performance=${perf}`),
    staleTime: 60_000,
  });

  const items = useMemo(() => {
    const arr = [...(data?.items || [])];
    if (sortBy === "marketCap") arr.sort((a, b) => (b.marketCap ?? 0) - (a.marketCap ?? 0));
    else if (sortBy === "name") arr.sort((a, b) => a.name.localeCompare(b.name));
    else arr.sort((a, b) => (b.changePct ?? 0) - (a.changePct ?? 0));
    return arr;
  }, [data, sortBy]);

  const indexLabel = data?.label || indexOptions.find(o => o.value === index)?.label || "Nifty 50";

  return (
    <div>
      <PageHeader
        title={`${indexLabel} Heatmap`}
        info="Performance heatmap of index constituents"
        right={
          data?.indexPrice != null && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-gray-500 dark:text-gray-400 font-medium">{indexLabel}</span>
              <span className="font-bold text-gray-900 dark:text-white">{data.indexPrice?.toFixed(2)}</span>
              <span className={`font-semibold ${(data.indexChange ?? 0) >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-500"}`}>
                {(data.indexChange ?? 0) >= 0 ? "+" : ""}{data.indexChange?.toFixed(2)} ({data.indexChangePct?.toFixed(2)}%)
              </span>
            </div>
          )
        }
      />

      <div className="flex flex-wrap items-center gap-2.5 mb-4">
        <MenuDropdown label="Index" value={index} onChange={setIndex} options={indexOptions.length ? indexOptions : [{value:"NIFTY50",label:"Nifty 50"}]}/>
        <MenuDropdown label="Sort By" value={sortBy} onChange={setSortBy} options={SORT_OPTIONS}/>
        <MenuDropdown label="Performance" value={perf} onChange={setPerf} options={PERF_OPTIONS}/>

        <div className="ml-auto flex items-center gap-1.5 text-[11px] flex-wrap">
          {[-3,-2,-1,0,1,2,3].map(v => {
            const b = bucket(v + (v >= 0 ? 0.5 : -0.5));
            return (
              <span key={v}
                    className="px-2 py-0.5 rounded-md font-bold"
                    style={{ backgroundColor: b.bg, color: b.fg }}>
                {v >= 0 ? `+${v}%` : `${v}%`}
              </span>
            );
          })}
        </div>
      </div>

      {isLoading && <Loading label="Loading heatmap…" />}
      {error && <ErrorState message={(error as Error).message} />}
      {data?.available === false && (
        <EmptyState title="Index not supported"
          message={data.message || "Constituent list isn't available for this index yet."}
          icon={<LayoutGrid className="w-10 h-10"/>} />
      )}

      {data?.available !== false && !isLoading && items.length === 0 && (
        <EmptyState title="No data" message="No constituents returned for this index." icon={<LayoutGrid className="w-10 h-10"/>} />
      )}

      {items.length > 0 && (
        <div className="grid gap-2 select-none"
             style={{ gridTemplateColumns: "repeat(auto-fill, minmax(118px, 1fr))" }}>
          {items.map(it => {
            const b = it.color ?? bucket(it.changePct);
            const pct = it.changePct ?? 0;
            return (
              <div key={it.symbol}
                   title={`${it.name}  •  ₹${it.price?.toFixed(2)}  •  ${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`}
                   className="relative overflow-hidden rounded-xl px-3 py-2.5 flex flex-col justify-between min-h-[88px] ring-1 ring-black/5 dark:ring-white/10 shadow-sm hover:shadow-lg hover:scale-[1.03] transition-all duration-200 cursor-default"
                   style={{ backgroundColor: b.bg, color: b.fg }}>
                <div className="text-[11px] font-extrabold leading-tight tracking-tight uppercase truncate">{it.name}</div>
                <div className="mt-1">
                  <div className="text-[15px] font-bold leading-none">{it.price?.toFixed(2)}</div>
                  <div className="text-[11px] font-semibold opacity-95 mt-0.5">
                    {pct >= 0 ? "▲" : "▼"} {Math.abs(pct).toFixed(2)}%
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
