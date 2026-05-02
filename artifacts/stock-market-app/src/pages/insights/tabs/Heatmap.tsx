import { useState, useMemo, useCallback, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "wouter";
import { fetchApi } from "@/lib/api";
import { Loading, ErrorState, EmptyState, MenuDropdown } from "../_shared";
import { LayoutGrid, Zap, ArrowLeft } from "lucide-react";
import { motion, AnimatePresence, useMotionValue, useTransform, useReducedMotion } from "framer-motion";
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

/** Format a market cap (in raw INR) into a compact Indian-style label. */
function formatMarketCap(v: number | null | undefined): string {
  if (v == null || isNaN(v) || v <= 0) return "—";
  const cr = v / 1e7; // 1 crore = 10,000,000
  if (cr >= 1e5) return `₹${(cr / 1e5).toFixed(2)} L Cr`;
  if (cr >= 1e3) return `₹${(cr / 1e3).toFixed(2)} K Cr`;
  if (cr >= 1)   return `₹${cr.toFixed(0)} Cr`;
  return `₹${(v / 1e5).toFixed(2)} L`;
}

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
  const reduced = useReducedMotion();
  const [index, setIndex] = useState<string>("NIFTY50");
  const [perf, setPerf] = useState<Performance>("1d");
  const [sortBy, setSortBy] = useState<SortBy>("marketCap");
  // Hover *item* is React state (changes only on enter/leave). Hover *position*
  // lives in motion values so onMouseMove never re-renders the parent (and the
  // ~500-tile grid in Nifty500 stays buttery smooth).
  const [hoverItem, setHoverItem] = useState<HeatmapItem | null>(null);
  const tipX = useMotionValue(-9999);
  const tipY = useMotionValue(-9999);
  const [clicked, setClicked] = useState<string | null>(null);
  const navigatingRef = useRef(false);
  const navigateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Always clear any pending navigation timeout on unmount so a late
  // ripple-then-navigate cannot fire after the page has been left.
  useEffect(() => () => {
    if (navigateTimerRef.current) clearTimeout(navigateTimerRef.current);
  }, []);

  // Tooltip clamping derived from the live motion values (no re-renders).
  const TOOLTIP_W = 240, TOOLTIP_H = 110, OFFSET = 14;
  const tipLeft = useTransform(tipX, (x) => {
    const w = typeof window !== "undefined" ? window.innerWidth : 1024;
    let l = x + OFFSET;
    if (l + TOOLTIP_W > w - 8) l = x - TOOLTIP_W - OFFSET;
    return Math.max(8, l);
  });
  const tipTop = useTransform(tipY, (y) => {
    const h = typeof window !== "undefined" ? window.innerHeight : 768;
    let t = y + OFFSET;
    if (t + TOOLTIP_H > h - 8) t = y - TOOLTIP_H - OFFSET;
    return Math.max(8, t);
  });

  // Single guarded navigation path. Prevents rapid clicks from queueing
  // multiple setTimeouts that would push duplicate history entries, and
  // stores the timer id so it can be cancelled on unmount.
  const triggerNavigate = useCallback((sym: string) => {
    if (navigatingRef.current) return;
    navigatingRef.current = true;
    setClicked(sym);
    if (navigateTimerRef.current) clearTimeout(navigateTimerRef.current);
    navigateTimerRef.current = setTimeout(() => {
      navigateTimerRef.current = null;
      navigate(`/stocks?symbol=${encodeURIComponent(sym)}`);
    }, reduced ? 0 : 220);
  }, [navigate, reduced]);

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

  // Clear hover/click state whenever the underlying tiles change so transient
  // animations never play on stale or vanished tiles.
  useEffect(() => {
    setHoverItem(null);
    setClicked(null);
    navigatingRef.current = false;
  }, [index, perf, data?.items]);

  const items = useMemo(() => {
    const arr = [...(data?.items || [])];
    if (sortBy === "marketCap") arr.sort((a, b) => (b.marketCap ?? 0) - (a.marketCap ?? 0));
    else if (sortBy === "name") arr.sort((a, b) => a.symbol.localeCompare(b.symbol));
    else arr.sort((a, b) => Math.abs(b.changePct) - Math.abs(a.changePct));
    return arr;
  }, [data, sortBy]);

  // The 3 biggest gainers and 3 biggest losers — these get a continuous "live" pulse
  // animation so the eye is drawn to them. Cheap because the set is tiny.
  const topMovers = useMemo(() => {
    const set = new Set<string>();
    const sorted = [...items].sort((a, b) => b.changePct - a.changePct);
    sorted.slice(0, 3).forEach(it => set.add(it.symbol));
    sorted.slice(-3).forEach(it => set.add(it.symbol));
    return set;
  }, [items]);

  // Aggregate market mood drives the background gradient color (-1 bearish → +1 bullish).
  const mood = useMemo(() => {
    if (!items.length) return 0;
    const avg = items.reduce((s, it) => s + (it.changePct || 0), 0) / items.length;
    return Math.max(-1, Math.min(1, avg / 2)); // ±2% saturates
  }, [items]);

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
    <div className="h-full min-h-0 flex flex-col overflow-hidden relative bg-slate-100 dark:bg-slate-950">
      {/* Dynamic Background Glow — drifts slowly + tints with market mood.
          Continuous motion is disabled when the user prefers reduced motion. */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <motion.div
          className="absolute w-[50%] h-[50%] rounded-full blur-[120px]"
          animate={reduced ? { opacity: 0.4 } : {
            x: ["-10%", "10%", "-10%"],
            y: ["-10%", "5%", "-10%"],
            opacity: [0.35, 0.55, 0.35],
            backgroundColor: mood >= 0
              ? ["rgba(16,185,129,0.18)", "rgba(16,185,129,0.28)", "rgba(16,185,129,0.18)"]
              : ["rgba(239,68,68,0.18)", "rgba(239,68,68,0.28)", "rgba(239,68,68,0.18)"],
          }}
          transition={reduced ? { duration: 0 } : { duration: 12, repeat: Infinity, ease: "easeInOut" }}
          style={{
            left: "-10%", top: "-10%",
            backgroundColor: mood >= 0 ? "rgba(16,185,129,0.22)" : "rgba(239,68,68,0.22)",
          }}
        />
        <motion.div
          className="absolute w-[50%] h-[50%] rounded-full blur-[120px]"
          animate={reduced ? { opacity: 0.35 } : {
            x: ["10%", "-5%", "10%"],
            y: ["10%", "-5%", "10%"],
            opacity: [0.3, 0.5, 0.3],
            backgroundColor: mood >= 0
              ? ["rgba(99,102,241,0.18)", "rgba(99,102,241,0.28)", "rgba(99,102,241,0.18)"]
              : ["rgba(239,68,68,0.18)", "rgba(220,38,38,0.32)", "rgba(239,68,68,0.18)"],
          }}
          transition={reduced ? { duration: 0 } : { duration: 14, repeat: Infinity, ease: "easeInOut" }}
          style={{
            right: "-10%", bottom: "-10%",
            backgroundColor: mood >= 0 ? "rgba(99,102,241,0.22)" : "rgba(220,38,38,0.22)",
          }}
        />
      </div>

      {/* Data freshness pill — top-left, non-intrusive */}
      <div className="absolute top-6 left-6 z-30">
        <DataFreshness meta={heatmapMeta} refreshKeys={[["insights/heatmap", index, perf]]} />
      </div>

      {/* Unified Aesthetic Command Center */}
      <div className="absolute top-6 left-1/2 -translate-x-1/2 z-30 flex items-center gap-1 p-1 bg-white/80 dark:bg-black/40 backdrop-blur-2xl border border-slate-200 dark:border-white/10 rounded-2xl shadow-2xl transition-all hover:bg-white dark:hover:bg-black/60">
        
        {/* Integrated Back Button */}
        <button
          onClick={() => navigate("/insights")}
          className="p-2 hover:bg-slate-100 dark:hover:bg-white/10 rounded-xl text-slate-500 dark:text-white/40 hover:text-slate-900 dark:hover:text-white transition-all group/back"
          title="Back to insights"
        >
          <ArrowLeft className="w-4 h-4 group-hover/back:-translate-x-0.5 transition-transform" />
        </button>

        <div className="w-[1px] h-6 bg-slate-200 dark:bg-white/10 mx-1" />
        
        {/* Market Status Section */}
        {data?.indexPrice != null && (
          <div className="pl-4 pr-3 flex items-center gap-3">
            <div className="flex flex-col">
              <span className="text-[9px] uppercase tracking-tighter text-slate-500 dark:text-white/40 font-black leading-none">{data.label || "Market"}</span>
              <span className="text-sm font-black text-slate-900 dark:text-white tracking-tighter">{data.indexPrice.toLocaleString()}</span>
            </div>
            <span className={`text-[10px] font-black px-1.5 py-0.5 rounded-lg shadow-sm ${(data.indexChange ?? 0) >= 0 ? "bg-emerald-500/20 text-emerald-700 dark:text-emerald-400" : "bg-red-500/20 text-red-700 dark:text-red-400"}`}>
              {(data.indexChangePct ?? 0).toFixed(2)}%
            </span>
          </div>
        )}

        <div className="w-[1px] h-6 bg-slate-200 dark:bg-white/10 mx-1" />

        {/* Index Selector */}
        <MenuDropdown label="" value={index} onChange={setIndex} options={indexOptions.length ? indexOptions : [{ value: "NIFTY50", label: "Nifty 50" }]} 
          customButton={<button className="px-3 py-1.5 text-xs font-bold text-slate-700 dark:text-white/70 hover:text-slate-900 dark:hover:text-white transition-colors flex items-center gap-2 group/btn">
            <LayoutGrid className="w-3.5 h-3.5 text-indigo-500 dark:text-indigo-400 group-hover/btn:scale-110 transition-transform" /> {indexOptions.find(o => o.value === index)?.label || "Select Index"}
          </button>}
        />

        <div className="w-[1px] h-4 bg-slate-200 dark:bg-white/5" />

        {/* Timeframe Scroller */}
        <div className="flex bg-slate-100 dark:bg-white/5 rounded-xl p-0.5">
          {PERF_OPTIONS.map(o => (
            <button key={o.value} onClick={() => setPerf(o.value)} 
              className={`px-3 py-1 text-[10px] font-black rounded-lg transition-all ${perf === o.value ? "bg-white dark:bg-white/10 text-slate-900 dark:text-white shadow-lg" : "text-slate-500 dark:text-white/30 hover:text-slate-700 dark:hover:text-white/50"}`}>
              {o.label}
            </button>
          ))}
        </div>

        <div className="w-[1px] h-4 bg-slate-200 dark:bg-white/5" />

        {/* Sort & Logic Tooltip */}
        <div className="relative group/sort">
          <MenuDropdown label="" value={sortBy} onChange={(v) => setSortBy(v as SortBy)} options={SORT_OPTIONS}
            customButton={<button className="px-3 py-1.5 text-xs font-bold text-slate-700 dark:text-white/70 hover:text-slate-900 dark:hover:text-white transition-colors flex items-center gap-2">
              <Zap className="w-3.5 h-3.5 text-amber-500 dark:text-amber-400" /> {SORT_OPTIONS.find(o => o.value === sortBy)?.label}
            </button>}
          />
          <div className="absolute top-full mt-2 left-1/2 -translate-x-1/2 px-2 py-1 bg-slate-900/90 dark:bg-black/80 backdrop-blur-md rounded-lg text-[9px] text-white/70 dark:text-white/40 whitespace-nowrap opacity-0 group-hover/sort:opacity-100 transition-opacity pointer-events-none border border-white/10 dark:border-white/5">
            Tile size: {sortBy === "marketCap" ? "Weighted Cap" : sortBy === "change" ? "Volatility" : "Uniform"}
          </div>
        </div>
      </div>

      {isLoading && <div className="flex-1 flex items-center justify-center"><Loading label="Generating aesthetic heatmap..." /></div>}
      {error && <ErrorState message={(error as Error).message} />}

      {/* The Heatmap Canvas */}
      <div ref={containerRef} className="flex-1 min-h-0 relative m-2 md:m-4 rounded-3xl overflow-hidden border border-slate-200 dark:border-white/5 shadow-2xl bg-white/40 dark:bg-black/20">
        {/* Keying the AnimatePresence by index+perf forces every tile to
            unmount/remount when the user switches index or timeframe, so
            the wave-stagger entrance animation always replays — even when
            data comes back instantly from cache. Sort changes keep the
            same key so tiles re-flow smoothly without re-entering. */}
        <AnimatePresence mode="popLayout" key={`${index}-${perf}`}>
          {rects?.map(({ x, y, w, h, item }, idx) => {
            const style = bucket(item.changePct);
            const isSmall = w < 70 || h < 50;
            const isTiny = w < 40 || h < 30;
            const cleanSymbol = item.symbol.split(".")[0];
            const isTopMover = topMovers.has(item.symbol);
            const isClicked = clicked === item.symbol;
            // Wave-stagger: tiles flow in diagonally from top-left to bottom-right.
            // Skipped entirely when reduced motion is preferred.
            // Cap stagger window so the entrance never feels long, and so the
            // last tile lands within ~350ms even on Nifty 500.
            const diag = reduced ? 0 : (containerW && containerH)
              ? Math.min((x / containerW + y / containerH) * 0.12, 0.18)
              : Math.min(idx * 0.002, 0.18);

            return (
              <motion.div
                key={item.symbol}
                // Position via inline style (paint-only) instead of animating
                // left/top/width/height — those properties trigger layout on
                // every frame for every tile, which is what made the entrance
                // feel laggy on big indices.
                style={{ left: x, top: y, width: w - 1, height: h - 1, willChange: "transform, opacity" }}
                // Tiles "shoot" in from above and settle into place. We
                // animate transform (translateY + scale) and opacity only —
                // both are compositor-only properties so even ~500 tiles
                // stay at 60fps. No layout, no paint, no blur.
                initial={reduced ? { opacity: 0 } : { opacity: 0, y: -56, scale: 0.96 }}
                animate={{
                  opacity: 1,
                  y: 0,
                  scale: isClicked && !reduced ? [1, 1.08, 1] : 1,
                }}
                exit={reduced ? { opacity: 0 } : { opacity: 0, y: -32, scale: 0.97 }}
                transition={reduced
                  ? { duration: 0.12, delay: 0 }
                  : {
                      // Critically-damped spring → no bounce, soft landing,
                      // settles in one pass. Feels "elegant + shooting"
                      // without the wobble of an under-damped spring.
                      type: "spring",
                      stiffness: 320,
                      damping: 34,
                      mass: 0.55,
                      delay: diag,
                      opacity: { duration: 0.28, ease: [0.22, 1, 0.36, 1], delay: diag },
                      scale: isClicked ? { duration: 0.35, ease: "easeOut" } : undefined,
                    }
                }
                role="button"
                tabIndex={0}
                aria-label={`${item.name || cleanSymbol}, ${item.changePct >= 0 ? "up" : "down"} ${Math.abs(item.changePct).toFixed(2)} percent. Press Enter to open analysis.`}
                onClick={() => triggerNavigate(cleanSymbol)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    triggerNavigate(cleanSymbol);
                  }
                }}
                onMouseEnter={(e) => {
                  setHoverItem(item);
                  tipX.set(e.clientX);
                  tipY.set(e.clientY);
                }}
                onMouseMove={(e) => {
                  // Position-only update via motion values — does NOT re-render
                  // the parent or the ~500-tile grid. Critical for smoothness.
                  tipX.set(e.clientX);
                  tipY.set(e.clientY);
                }}
                onMouseLeave={() => setHoverItem(null)}
                onFocus={(e) => {
                  const r = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
                  setHoverItem(item);
                  tipX.set(r.left + r.width / 2);
                  tipY.set(r.top + r.height / 2);
                }}
                onBlur={() => setHoverItem(null)}
                className={`absolute overflow-hidden cursor-pointer group flex flex-col items-center justify-center outline-none focus-visible:ring-2 focus-visible:ring-white/80
                  ${style.bg} ${style.border} border shadow-inner ${style.glow} hover:brightness-125 hover:ring-2 hover:ring-white/60 transition-[filter,box-shadow,ring] duration-200`}
              >
                {/* Top reflective highlight line */}
                <div className="absolute top-0 left-0 right-0 h-[1px] bg-white/20" />

                {/* Live pulse for top movers — a softly-throbbing inner glow */}
                {isTopMover && !isTiny && !reduced && (
                  <motion.div
                    className="absolute inset-0 pointer-events-none"
                    animate={{ opacity: [0, 0.45, 0], scale: [0.92, 1, 0.92] }}
                    transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
                    style={{ background: "radial-gradient(circle at center, rgba(255,255,255,0.5), transparent 70%)" }}
                  />
                )}

                {/* Live pulse ring on top movers (tiny corner indicator) */}
                {isTopMover && !isTiny && (
                  <div className="absolute top-1 right-1 z-10 pointer-events-none">
                    <span className="relative flex h-1.5 w-1.5">
                      {!reduced && (
                        <motion.span
                          className="absolute inset-0 rounded-full bg-white"
                          animate={{ scale: [1, 2.4, 1], opacity: [0.7, 0, 0.7] }}
                          transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut" }}
                        />
                      )}
                      <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-white shadow-[0_0_6px_rgba(255,255,255,0.8)]" />
                    </span>
                  </div>
                )}

                {/* Click ripple — radial flash when activated */}
                {isClicked && !reduced && (
                  <motion.div
                    className="absolute inset-0 pointer-events-none"
                    initial={{ opacity: 0.9, scale: 0.2 }}
                    animate={{ opacity: 0, scale: 2.5 }}
                    transition={{ duration: 0.6, ease: "easeOut" }}
                    style={{ background: "radial-gradient(circle at center, rgba(255,255,255,0.85), transparent 60%)" }}
                  />
                )}

                {/* Hover sweep — diagonal shimmer that crosses the tile on hover (CSS only) */}
                {!reduced && (
                  <div className="absolute inset-0 overflow-hidden pointer-events-none">
                    <div className="absolute inset-y-0 -left-1/3 w-1/3 bg-gradient-to-r from-transparent via-white/25 to-transparent skew-x-12 -translate-x-full group-hover:translate-x-[400%] transition-transform duration-1000 ease-out" />
                  </div>
                )}

                {!isTiny && (
                  <div className="relative flex flex-col items-center justify-center px-1 text-center select-none pointer-events-none z-[6]">
                    <span
                      className={`font-black tracking-tighter uppercase leading-none mb-0.5 ${style.text} drop-shadow-sm`}
                      style={{ fontSize: Math.max(9, Math.min(24, Math.floor(Math.min(w, h) / 4))) }}
                    >
                      {cleanSymbol}
                    </span>
                    {!isSmall && (
                      <motion.div
                        initial={reduced ? { opacity: 0 } : { opacity: 0, y: 4 }}
                        animate={{ opacity: 0.95, y: 0 }}
                        transition={reduced ? { duration: 0.15 } : { delay: diag + 0.15, duration: 0.4 }}
                        className={`font-bold flex items-center gap-1 ${style.text}`}
                        style={{ fontSize: Math.max(8, Math.min(12, Math.floor(Math.min(w, h) / 8))) }}
                      >
                        {item.changePct >= 0 ? "+" : ""}{item.changePct.toFixed(2)}%
                      </motion.div>
                    )}
                  </div>
                )}
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      {/* Floating tooltip — spring-animated, follows cursor via motion values
          (no parent re-render on mousemove). Mounts/unmounts only when the
          hovered *item* changes. */}
      <AnimatePresence>
        {hoverItem && (() => {
          const cleanSymbol = hoverItem.symbol.split(".")[0];
          const positive = (hoverItem.changePct ?? 0) >= 0;
          return (
            <motion.div
              key="heatmap-tooltip"
              initial={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.92, y: 4 }}
              animate={reduced ? { opacity: 1 } : { opacity: 1, scale: 1, y: 0 }}
              exit={reduced ? { opacity: 0, transition: { duration: 0.1 } } : { opacity: 0, scale: 0.95, y: 2, transition: { duration: 0.12 } }}
              transition={reduced ? { duration: 0.12 } : { type: "spring", stiffness: 500, damping: 32, mass: 0.6 }}
              className="fixed z-[100] pointer-events-none bg-slate-900/95 dark:bg-black/90 backdrop-blur-xl border border-white/10 rounded-xl shadow-2xl px-3 py-2.5 text-white origin-top-left"
              style={{ width: TOOLTIP_W, left: tipLeft, top: tipTop }}
            >
              {/* Glowing top accent that matches the tile's mood */}
              <motion.div
                className={`absolute top-0 left-3 right-3 h-[2px] rounded-full ${positive ? "bg-emerald-400" : "bg-red-400"}`}
                initial={reduced ? { opacity: 0 } : { scaleX: 0, opacity: 0 }}
                animate={reduced ? { opacity: 1 } : { scaleX: 1, opacity: 1 }}
                transition={reduced ? { duration: 0.12 } : { duration: 0.35, ease: "easeOut" }}
                style={{ boxShadow: positive ? "0 0 12px rgba(52,211,153,0.7)" : "0 0 12px rgba(248,113,113,0.7)" }}
              />
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="text-xs font-black tracking-tight text-white/95 truncate">{cleanSymbol}</span>
                <motion.span
                  initial={reduced ? { opacity: 0 } : { opacity: 0, x: 4 }}
                  animate={reduced ? { opacity: 1 } : { opacity: 1, x: 0 }}
                  transition={reduced ? { duration: 0.12 } : { delay: 0.05 }}
                  className={`text-[10px] font-black px-1.5 py-0.5 rounded-md ${positive ? "bg-emerald-500/20 text-emerald-300" : "bg-red-500/20 text-red-300"}`}
                >
                  {positive ? "+" : ""}{(hoverItem.changePct ?? 0).toFixed(2)}%
                </motion.span>
              </div>
              <div className="text-[10px] text-white/60 truncate mb-1.5">{hoverItem.name || cleanSymbol}</div>
              <div className="flex items-center justify-between text-[10px]">
                <span className="text-white/40 uppercase tracking-wider">Mkt Cap</span>
                <span className="text-white/90 font-bold">{formatMarketCap(hoverItem.marketCap)}</span>
              </div>
              <div className="mt-1 text-[9px] text-white/30 text-center flex items-center justify-center gap-1">
                Click to open analysis
                {!reduced ? (
                  <motion.span
                    animate={{ x: [0, 3, 0] }}
                    transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
                  >→</motion.span>
                ) : <span>→</span>}
              </div>
            </motion.div>
          );
        })()}
      </AnimatePresence>

      {data?.available === false && (
        <div className="absolute inset-0 flex items-center justify-center z-40 bg-slate-100/80 dark:bg-slate-950/80 backdrop-blur-md">
          <EmptyState title="Index unavailable" message={data.message || "This index doesn't support heatmap visualization yet."} icon={<LayoutGrid className="w-10 h-10 text-indigo-500/50"/>} />
        </div>
      )}
    </div>
  );
}
