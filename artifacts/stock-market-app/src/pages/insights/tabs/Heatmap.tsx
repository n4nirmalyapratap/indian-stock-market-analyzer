import { useState, useMemo, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { PageHeader, Loading, ErrorState, EmptyState, MenuDropdown, Card } from "../_shared";
import { LayoutGrid } from "lucide-react";

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

/** Squarified treemap layout (Bruls, Huijsen & van Wijk, 2000).
 *  Returns absolute-positioned rectangles inside a fixed-width container.
 *  Falls back to equal-weighted layout if all weights are 0. */
type Rect = { x: number; y: number; w: number; h: number; item: HeatmapItem };

function squarify(items: HeatmapItem[], width: number, height: number): Rect[] {
  if (!items.length || width <= 0 || height <= 0) return [];
  // Use market cap; if all zero, fall back to equal weights.
  const allZero = items.every(it => !it.marketCap || it.marketCap <= 0);
  const rawWeights = items.map(it => allZero ? 1 : Math.max(it.marketCap || 0, 0));
  const totalW = rawWeights.reduce((a, b) => a + b, 0) || 1;
  const totalArea = width * height;
  const areas = rawWeights.map(w => (w / totalW) * totalArea);

  // Pair (item, area) and sort largest first.
  const queue = items.map((it, i) => ({ it, area: areas[i] }))
                     .sort((a, b) => b.area - a.area);

  const rects: Rect[] = [];
  let x = 0, y = 0, remW = width, remH = height;

  const worst = (row: number[], side: number) => {
    if (!row.length) return Infinity;
    const sum = row.reduce((a, b) => a + b, 0);
    const max = Math.max(...row);
    const min = Math.min(...row);
    const s2 = side * side;
    const sum2 = sum * sum;
    return Math.max((s2 * max) / sum2, sum2 / (s2 * min));
  };

  const layoutRow = (row: { it: HeatmapItem; area: number }[], side: number, horizontal: boolean) => {
    const sum = row.reduce((a, b) => a + b.area, 0);
    if (horizontal) {
      const rowH = sum / side;
      let cx = x;
      for (const r of row) {
        const w = r.area / rowH;
        rects.push({ x: cx, y: y, w, h: rowH, item: r.it });
        cx += w;
      }
      y += rowH; remH -= rowH;
    } else {
      const rowW = sum / side;
      let cy = y;
      for (const r of row) {
        const h = r.area / rowW;
        rects.push({ x: x, y: cy, w: rowW, h, item: r.it });
        cy += h;
      }
      x += rowW; remW -= rowW;
    }
  };

  let row: { it: HeatmapItem; area: number }[] = [];
  let i = 0;
  while (i < queue.length) {
    const horizontal = remW >= remH;
    const side = horizontal ? remW : remH;
    const next = queue[i];
    const trial = [...row.map(r => r.area), next.area];
    if (row.length === 0 || worst(row.map(r => r.area), side) >= worst(trial, side)) {
      row.push(next);
      i++;
    } else {
      layoutRow(row, side, horizontal);
      row = [];
    }
  }
  if (row.length) layoutRow(row, (remW >= remH ? remW : remH), remW >= remH);
  return rects;
}

function useElementWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(entries => {
      for (const e of entries) setW(e.contentRect.width);
    });
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
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

  // Treemap layout — only when sorting by market cap; other sorts use uniform grid.
  const [containerRef, containerW] = useElementWidth<HTMLDivElement>();
  // Choose container height: tighter for few items, taller for many.
  const treemapH = useMemo(() => {
    const n = items.length || 30;
    if (n <= 10) return 360;
    if (n <= 30) return 540;
    if (n <= 60) return 680;
    return 780;
  }, [items.length]);

  const rects = useMemo(() => {
    if (sortBy !== "marketCap" || !containerW) return null;
    return squarify(items, containerW, treemapH);
  }, [items, sortBy, containerW, treemapH]);

  return (
    <div>
      <PageHeader
        title={`${indexLabel} Heatmap`}
        info="Performance heatmap of index constituents. Tile size = market cap (sorted by market cap)."
        right={
          data?.indexPrice != null && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-muted-foreground font-medium">{indexLabel}</span>
              <span className="font-bold text-foreground">{data.indexPrice?.toFixed(2)}</span>
              <span className={`font-semibold ${(data.indexChange ?? 0) >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-500"}`}>
                {(data.indexChange ?? 0) >= 0 ? "+" : ""}{data.indexChange?.toFixed(2)} ({data.indexChangePct?.toFixed(2)}%)
              </span>
            </div>
          )
        }
      />

      <div className="flex flex-wrap items-center gap-2 mb-3">
        <MenuDropdown label="Index" value={index} onChange={setIndex}
          options={indexOptions.length ? indexOptions : [{ value: "NIFTY50", label: "Nifty 50" }]}
          maxButtonWidth={260}
        />
        <MenuDropdown label="Sort" value={sortBy} onChange={(v) => setSortBy(v as SortBy)} options={SORT_OPTIONS} maxButtonWidth={180} />
        <MenuDropdown label="Perf" value={perf} onChange={(v) => setPerf(v as Performance)} options={PERF_OPTIONS} maxButtonWidth={140} />

        <div className="ml-auto flex items-center gap-1.5 text-[11px] flex-wrap">
          {[-3, -2, -1, 0, 1, 2, 3].map(v => {
            const b = bucket(v + (v >= 0 ? 0.5 : -0.5));
            return (
              <span key={v} className="px-2 py-0.5 rounded-md font-bold"
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

      {/* Treemap mode (sort = market cap) */}
      {items.length > 0 && sortBy === "marketCap" && (
        <Card className="overflow-hidden p-1">
          <div ref={containerRef} className="relative w-full" style={{ height: treemapH }}>
            {rects?.map(({ x, y, w, h, item }) => {
              const b = item.color ?? bucket(item.changePct);
              const pct = item.changePct ?? 0;
              // Decide what to show based on tile size.
              const small = w < 60 || h < 40;
              const tiny  = w < 36 || h < 28;
              const symFontPx  = Math.max(9, Math.min(18, Math.floor(Math.min(w, h) / 5.2)));
              const pctFontPx  = Math.max(8, Math.min(14, Math.floor(Math.min(w, h) / 7)));
              return (
                <div
                  key={item.symbol}
                  title={`${item.name} • ₹${item.price?.toFixed(2)} • ${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`}
                  className="absolute overflow-hidden ring-1 ring-black/10 dark:ring-white/15 cursor-default transition-transform hover:z-10 hover:scale-[1.01]"
                  style={{
                    left: x, top: y, width: w, height: h,
                    backgroundColor: b.bg, color: b.fg, padding: tiny ? 1 : 4,
                  }}
                >
                  {!tiny && (
                    <div className="h-full w-full flex flex-col items-center justify-center text-center leading-tight">
                      <div className="font-extrabold tracking-tight uppercase truncate w-full px-1"
                           style={{ fontSize: symFontPx }}>
                        {item.symbol.replace(/\.NS$/, "")}
                      </div>
                      {!small && (
                        <div className="font-semibold opacity-95" style={{ fontSize: pctFontPx, marginTop: 2 }}>
                          {pct >= 0 ? "▲" : "▼"} {Math.abs(pct).toFixed(2)}%
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* Uniform grid mode (sort = name / % change) */}
      {items.length > 0 && sortBy !== "marketCap" && (
        <div className="grid gap-2 select-none"
             style={{ gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))" }}>
          {items.map(it => {
            const b = it.color ?? bucket(it.changePct);
            const pct = it.changePct ?? 0;
            return (
              <div key={it.symbol}
                   title={`${it.name} • ₹${it.price?.toFixed(2)} • ${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`}
                   className="relative overflow-hidden rounded-lg px-3 py-2.5 flex flex-col justify-between min-h-[88px] ring-1 ring-black/5 dark:ring-white/10 shadow-sm hover:shadow-lg hover:scale-[1.03] transition-all duration-150 cursor-default"
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
