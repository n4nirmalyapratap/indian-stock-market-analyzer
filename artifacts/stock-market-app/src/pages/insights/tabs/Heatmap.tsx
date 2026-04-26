import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, Dropdown, Loading, ErrorState, EmptyState } from "../_shared";
import { LayoutGrid } from "lucide-react";

type Index = "NIFTY50" | "NIFTYBANK";
type Performance = "1d" | "1w" | "1m" | "1y";
type SortBy = "marketCap" | "name" | "change";

interface HeatmapItem {
  symbol: string;
  name: string;
  price: number;
  changePct: number;
  marketCap: number;
}

interface HeatmapResponse {
  index: string;
  indexPrice: number;
  indexChange: number;
  indexChangePct: number;
  items: HeatmapItem[];
}

function bucket(p: number) {
  if (p <= -3) return { bg: "bg-[#a83232]", text: "text-white" };
  if (p <= -2) return { bg: "bg-[#c54545]", text: "text-white" };
  if (p <= -1) return { bg: "bg-[#dc6f6f]", text: "text-white" };
  if (p <  0)  return { bg: "bg-[#f1a3a3]", text: "text-gray-900" };
  if (p === 0) return { bg: "bg-gray-300 dark:bg-gray-600", text: "text-gray-900 dark:text-white" };
  if (p <  1)  return { bg: "bg-[#a8e0a8]", text: "text-gray-900" };
  if (p <  2)  return { bg: "bg-[#5fc15f]", text: "text-white" };
  if (p <  3)  return { bg: "bg-[#3a9a3a]", text: "text-white" };
  return            { bg: "bg-[#1f7a1f]", text: "text-white" };
}

export default function Heatmap() {
  const [index, setIndex] = useState<Index>("NIFTY50");
  const [perf, setPerf] = useState<Performance>("1d");
  const [sortBy, setSortBy] = useState<SortBy>("marketCap");

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

  const indexLabel = index === "NIFTY50" ? "Nifty 50" : "Nifty Bank";

  return (
    <div>
      <PageHeader
        title={`${indexLabel} Heatmap`}
        info="Performance heatmap of index constituents"
        right={
          data && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-gray-500 dark:text-gray-400 font-medium">{indexLabel}</span>
              <span className="font-bold text-gray-900 dark:text-white">{data.indexPrice?.toFixed(2)}</span>
              <span className={`font-semibold ${data.indexChange >= 0 ? "text-green-600" : "text-red-500"}`}>
                {data.indexChange >= 0 ? "+" : ""}{data.indexChange?.toFixed(2)} ({data.indexChangePct?.toFixed(2)}%)
              </span>
            </div>
          )
        }
      />

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <Dropdown label="Index :" value={index} onChange={setIndex}
          options={[{value:"NIFTY50",label:"Nifty 50"},{value:"NIFTYBANK",label:"Nifty Bank"}]}/>
        <Dropdown label="Sort By :" value={sortBy} onChange={setSortBy}
          options={[{value:"marketCap",label:"Market Cap"},{value:"name",label:"Name"},{value:"change",label:"% Change"}]}/>
        <Dropdown label="Performance By :" value={perf} onChange={setPerf}
          options={[{value:"1d",label:"1D"},{value:"1w",label:"1W"},{value:"1m",label:"1M"},{value:"1y",label:"1Y"}]}/>

        <div className="ml-auto flex items-center gap-1 text-xs">
          <span className="text-gray-500">x1</span>
          {[-3,-2,-1,0,1,2,3].map(v => {
            const b = bucket(v + (v >= 0 ? 0.01 : -0.01));
            return <span key={v} className={`px-2 py-1 rounded font-semibold text-[11px] ${b.bg} ${b.text}`}>{v >= 0 ? `+${v}%` : `${v}%`}</span>;
          })}
        </div>
      </div>

      {isLoading && <Loading label="Loading heatmap…" />}
      {error && <ErrorState message={(error as Error).message} />}

      {data && items.length === 0 && (
        <EmptyState title="No data" message="No constituents returned for this index." icon={<LayoutGrid className="w-10 h-10"/>} />
      )}

      {items.length > 0 && (
        <div className="grid gap-1.5"
             style={{ gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))" }}>
          {items.map(it => {
            const b = bucket(it.changePct ?? 0);
            return (
              <div key={it.symbol}
                   className={`rounded-md p-2.5 ${b.bg} ${b.text} flex flex-col justify-between min-h-[80px] cursor-default hover:scale-[1.02] transition-transform`}>
                <div className="text-[11px] font-bold leading-tight uppercase truncate">{it.name}</div>
                <div>
                  <div className="text-sm font-bold">{it.price?.toFixed(2)}</div>
                  <div className="text-[11px] opacity-90">{it.changePct >= 0 ? "+" : ""}{it.changePct?.toFixed(2)}%</div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
