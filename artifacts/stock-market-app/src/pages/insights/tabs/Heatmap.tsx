import { useState, useMemo, useCallback, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "wouter";
import { fetchApi } from "@/lib/api";
import { Loading, ErrorState, EmptyState, MenuDropdown } from "../_shared";
import { LayoutGrid, Zap, ArrowLeft } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import DataFreshness from "@/components/DataFreshness";
import { pickMeta, marketDataQueryOptions } from "@/lib/marketData";

type Performance = "1d" | "1w" | "1m" | "1y";
type SortBy = "marketCap" | "name" | "change";

interface HeatmapItem {
  symbol: string;
  name: string;
  price: number;
  changePct: number;
  marketCap: number;
  color?: { bg: string; border: string; text: string; glow: string };
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

/** High-end color palette for the heatmap */
function bucket(p: number | null | undefined): { bg: string; border: string; text: string; glow: string } {
  if (p == null || isNaN(p)) return { bg: "bg-slate-400", border: "border-slate-500", text: "text-slate-950", glow: "shadow-slate-500/20" };
  
  // Bearish (Red)
  if (p <= -3)    return { bg: "bg-red-700", border: "border-red-900", text: "text-white", glow: "shadow-red-900/40" };
  if (p <= -1.5)  return { bg: "bg-red-500", border: "border-red-700", text: "text-white", glow: "shadow-red-500/30" };
  if (p < -0.05)  return { bg: "bg-red-400/80", border: "border-red-500", text: "text-white", glow: "shadow-red-400/20" };
  
  // Neutral
  if (p <  0.05)  return { bg: "bg-slate-500/50", border: "border-slate-600", text: "text-white", glow: "shadow-slate-500/10" };
  
  // Bullish (Green)
  if (p <  1.5)   return { bg: "bg-emerald-400/80", border: "border-emerald-500", text: "text-emerald-950", glow: "shadow-emerald-400/20" };
  if (p <  3)     return { bg: "bg-emerald-500", border: "border-emerald-700", text: "text-white", glow: "shadow-emerald-500/30" };
  return            { bg: "bg-emerald-700", border: "border-emerald-900", text: "text-white", glow: "shadow-emerald-900/40" };
}

const PERF_OPTIONS: { value: Performance; label: string }[] = [
  { value: "1d", label: "1D" }, { value: "1w", label: "1W" }, { value: "1m", label: "1M" }, { value: "1y", label: "1Y" },
];
const SORT_OPTIONS: { value: SortBy; label: string }[] = [
  { value: "marketCap", label: "Market Cap" }, { value: "change", label: "Volatility" }, { value: "name", label: "Alphabetical" },
];

/** Treemap logic */
type Rect = { x: number; y: number; w: number; h: number; item: HeatmapItem };

function squarify(items: HeatmapItem[], width: number, height: number, weightFor: (it: HeatmapItem) => number): Rect[] {
  if (!items.length || width <= 0 || height <= 0) return [];
  const rawWeights = items.map(it => Math.max(weightFor(it) || 0, 0));
  const totalRaw = rawWeights.reduce((a, b) => a + b, 0);
  const weights = totalRaw > 0 ? rawWeights : items.map(() => 1);
  const totalW = weights.reduce((a, b) => a + b, 0) || 1;
  const areas = weights.map(w => (w / totalW) * (width * height));
  const queue = items.map((it, i) => ({ it, area: areas[i] })).sort((a, b) => b.area - a.area);
  const rects: Rect[] = [];
  let x = 0, y = 0, remW = width, remH = height;

  const worst = (row: number[], side: number) => {
    if (!row.length) return Infinity;
    const sum = row.reduce((a, b) => a + b, 0), max = Math.max(...row), min = Math.min(...row), s2 = side * side, sum2 = sum * sum;
    return Math.max((s2 * max) / sum2, sum2 / (s2 * min));
  };

  const layoutRow = (row: { it: HeatmapItem; area: number }[], side: number, horizontal: boolean) => {
    const sum = row.reduce((a, b) => a + b.area, 0);
    if (horizontal) {
      const rowH = sum / side; let cx = x;
      for (const r of row) { const w = r.area / rowH; rects.push({ x: cx, y, w, h: rowH, item: r.it }); cx += w; }
      y += rowH; remH -= rowH;
    } else {
      const rowW = sum / side; let cy = y;
      for (const r of row) { const h = r.area / rowW; rects.push({ x, y: cy, w: rowW, h, item: r.it }); cy += h; }
      x += rowW; remW -= rowW;
    }
  };

  let row: { it: HeatmapItem; area: number }[] = []; let i = 0;
  while (i < queue.length) {
    const side = remW >= remH ? remW : remH;
    const trial = [...row.map(r => r.area), queue[i].area];
    if (row.length === 0 || worst(row.map(r => r.area), side) >= worst(trial, side)) { row.push(queue[i]); i++; }
    else { layoutRow(row, side, remW >= remH); row = []; }
  }
  if (row.length) layoutRow(row, (remW >= remH ? remW : remH), remW >= remH);
  return rects;
}

function useElementSize<T extends HTMLElement>() {
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [node, setNode] = useState<T | null>(null);
  const setRef = useCallback((n: T | null) => setNode(n), []);
  useEffect(() => {
    if (!node) return;
    const ro = new ResizeObserver(entries => {
      for (const e of entries) setSize({ width: e.contentRect.width, height: e.contentRect.height });
    });
    ro.observe(node);
    return () => ro.disconnect();
  }, [node]);
  return [setRef, size.width, size.height] as const;
}

export default function Heatmap() {
  const [, navigate] = useLocation();
  const [index, setIndex] = useState<string>("NIFTY50");
  const [perf, setPerf] = useState<Performance>("1d");
  const [sortBy, setSortBy] = useState<SortBy>("marketCap");

  const { data: idxList } = useQuery<{ indices: IndexInfo[] }>({
    queryKey: ["insights/indices"],
    queryFn: () => fetchApi(`/insights/indices`),
    staleTime: 60 * 60_000,
  });
  const indexOptions = useMemo(() => (idxList?.indices || []).map(i => ({ value: i.code, label: i.label })), [idxList]);

  const { data, isLoading, error } = useQuery<HeatmapResponse>(
    marketDataQueryOptions<HeatmapResponse>(
      ["insights/heatmap", index, perf],
      () => fetchApi(`/insights/heatmap?index=${index}&performance=${perf}`),
    ),
  );
  const heatmapMeta = pickMeta(data);

  const items = useMemo(() => {
    const arr = [...(data?.items || [])];
    if (sortBy === "marketCap") arr.sort((a, b) => (b.marketCap ?? 0) - (a.marketCap ?? 0));
    else if (sortBy === "name") arr.sort((a, b) => a.symbol.localeCompare(b.symbol));
    else arr.sort((a, b) => Math.abs(b.changePct) - Math.abs(a.changePct));
    return arr;
  }, [data, sortBy]);

  const [containerRef, containerW, containerH] = useElementSize<HTMLDivElement>();

  const rects = useMemo(() => {
    if (!containerW || !containerH || items.length === 0) return null;
    
    // Visibility Scaling for large indices
    const isLarge = items.length > 100;
    const weightFor = sortBy === "marketCap" 
      ? (it: HeatmapItem) => isLarge ? Math.pow(it.marketCap, 0.45) : it.marketCap 
      : sortBy === "change" 
      ? (it: HeatmapItem) => Math.abs(it.changePct) + 0.5 
      : () => 1;

    let results = squarify(items, containerW, containerH, weightFor);

    // Physical Floor to ensure tiles are at least 4x4
    return results.map(r => ({
      ...r,
      w: Math.max(r.w, 4),
      h: Math.max(r.h, 4)
    }));
  }, [items, sortBy, containerW, containerH]);

  return (
    <div className="h-full flex flex-col overflow-hidden relative bg-slate-950">
      {/* Dynamic Background Glow */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-[10%] -left-[10%] w-[40%] h-[40%] bg-emerald-500/10 blur-[120px] rounded-full" />
        <div className="absolute -bottom-[10%] -right-[10%] w-[40%] h-[40%] bg-red-500/10 blur-[120px] rounded-full" />
      </div>

      {/* Data freshness pill — top-left, non-intrusive */}
      <div className="absolute top-6 left-6 z-30">
        <DataFreshness meta={heatmapMeta} refreshKeys={[["insights/heatmap", index, perf]]} />
      </div>

      {/* Unified Aesthetic Command Center */}
      <div className="absolute top-6 left-1/2 -translate-x-1/2 z-30 flex items-center gap-1 p-1 bg-black/40 backdrop-blur-2xl border border-white/10 rounded-2xl shadow-2xl transition-all hover:bg-black/60">
        
        {/* Integrated Back Button */}
        <button
          onClick={() => navigate("/insights")}
          className="p-2 hover:bg-white/10 rounded-xl text-white/40 hover:text-white transition-all group/back"
          title="Back to insights"
        >
          <ArrowLeft className="w-4 h-4 group-hover/back:-translate-x-0.5 transition-transform" />
        </button>

        <div className="w-[1px] h-6 bg-white/10 mx-1" />
        
        {/* Market Status Section */}
        {data?.indexPrice != null && (
          <div className="pl-4 pr-3 flex items-center gap-3">
            <div className="flex flex-col">
              <span className="text-[9px] uppercase tracking-tighter text-white/40 font-black leading-none">{data.label || "Market"}</span>
              <span className="text-sm font-black text-white tracking-tighter">{data.indexPrice.toLocaleString()}</span>
            </div>
            <span className={`text-[10px] font-black px-1.5 py-0.5 rounded-lg shadow-sm ${(data.indexChange ?? 0) >= 0 ? "bg-emerald-500/20 text-emerald-400" : "bg-red-500/20 text-red-400"}`}>
              {(data.indexChangePct ?? 0).toFixed(2)}%
            </span>
          </div>
        )}

        <div className="w-[1px] h-6 bg-white/10 mx-1" />

        {/* Index Selector */}
        <MenuDropdown label="" value={index} onChange={setIndex} options={indexOptions.length ? indexOptions : [{ value: "NIFTY50", label: "Nifty 50" }]} 
          customButton={<button className="px-3 py-1.5 text-xs font-bold text-white/70 hover:text-white transition-colors flex items-center gap-2 group/btn">
            <LayoutGrid className="w-3.5 h-3.5 text-indigo-400 group-hover/btn:scale-110 transition-transform" /> {indexOptions.find(o => o.value === index)?.label || "Select Index"}
          </button>}
        />

        <div className="w-[1px] h-4 bg-white/5" />

        {/* Timeframe Scroller */}
        <div className="flex bg-white/5 rounded-xl p-0.5">
          {PERF_OPTIONS.map(o => (
            <button key={o.value} onClick={() => setPerf(o.value)} 
              className={`px-3 py-1 text-[10px] font-black rounded-lg transition-all ${perf === o.value ? "bg-white/10 text-white shadow-lg" : "text-white/30 hover:text-white/50"}`}>
              {o.label}
            </button>
          ))}
        </div>

        <div className="w-[1px] h-4 bg-white/5" />

        {/* Sort & Logic Tooltip */}
        <div className="relative group/sort">
          <MenuDropdown label="" value={sortBy} onChange={(v) => setSortBy(v as SortBy)} options={SORT_OPTIONS}
            customButton={<button className="px-3 py-1.5 text-xs font-bold text-white/70 hover:text-white transition-colors flex items-center gap-2">
              <Zap className="w-3.5 h-3.5 text-amber-400" /> {SORT_OPTIONS.find(o => o.value === sortBy)?.label}
            </button>}
          />
          <div className="absolute top-full mt-2 left-1/2 -translate-x-1/2 px-2 py-1 bg-black/80 backdrop-blur-md rounded-lg text-[9px] text-white/40 whitespace-nowrap opacity-0 group-hover/sort:opacity-100 transition-opacity pointer-events-none border border-white/5">
            Tile size: {sortBy === "marketCap" ? "Weighted Cap" : sortBy === "change" ? "Volatility" : "Uniform"}
          </div>
        </div>
      </div>

      {isLoading && <div className="flex-1 flex items-center justify-center"><Loading label="Generating aesthetic heatmap..." /></div>}
      {error && <ErrorState message={(error as Error).message} />}

      {/* The Heatmap Canvas */}
      <div ref={containerRef} className="flex-1 relative m-2 md:m-4 rounded-3xl overflow-hidden border border-white/5 shadow-2xl bg-black/20">
        <AnimatePresence mode="popLayout">
          {rects?.map(({ x, y, w, h, item }) => {
            const style = bucket(item.changePct);
            const isSmall = w < 70 || h < 50;
            const isTiny = w < 40 || h < 30;
            const isMicro = w < 20 || h < 15;
            
            return (
              <motion.div
                key={item.symbol}
                initial={{ opacity: 0, scale: 0.9, filter: "blur(10px)" }}
                animate={{ opacity: 1, scale: 1, filter: "blur(0px)", left: x, top: y, width: w - 1, height: h - 1 }}
                exit={{ opacity: 0, scale: 1.1, filter: "blur(20px)" }}
                transition={{ type: "spring", stiffness: 300, damping: 30, mass: 0.8 }}
                className={`absolute overflow-hidden cursor-pointer group flex flex-col items-center justify-center transition-all duration-500
                  ${style.bg} ${style.border} border shadow-inner ${style.glow}`}
                whileHover={{ 
                  scale: isMicro ? 2.5 : isSmall ? 1.2 : 1.05, 
                  zIndex: 50, 
                  boxShadow: "0 25px 50px rgba(0,0,0,0.6)",
                  transition: { type: "spring", stiffness: 400, damping: 25 }
                }}
              >
                <div className="absolute top-0 left-0 right-0 h-[1px] bg-white/20" />
                
                {!isTiny && (
                  <div className="relative flex flex-col items-center justify-center px-1 text-center select-none">
                    <motion.span 
                      layout
                      className={`font-black tracking-tighter uppercase leading-none mb-0.5 ${style.text}`}
                      style={{ fontSize: Math.max(9, Math.min(24, Math.floor(Math.min(w, h) / 4))) }}
                    >
                      {item.symbol.split(".")[0]}
                    </motion.span>
                    {!isSmall && (
                      <motion.div 
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 0.9 }}
                        className={`font-bold flex items-center gap-1 ${style.text}`}
                        style={{ fontSize: Math.max(8, Math.min(12, Math.floor(Math.min(w, h) / 8))) }}
                      >
                        {item.changePct >= 0 ? "+" : ""}{item.changePct.toFixed(2)}%
                      </motion.div>
                    )}
                  </div>
                )}
                
                <div className="absolute inset-0 opacity-0 group-hover:opacity-100 bg-gradient-to-br from-white/20 to-transparent transition-opacity pointer-events-none" />
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      {data?.available === false && (
        <div className="absolute inset-0 flex items-center justify-center z-40 bg-slate-950/80 backdrop-blur-md">
          <EmptyState title="Index unavailable" message={data.message || "This index doesn't support heatmap visualization yet."} icon={<LayoutGrid className="w-10 h-10 text-indigo-500/50"/>} />
        </div>
      )}
    </div>
  );
}
