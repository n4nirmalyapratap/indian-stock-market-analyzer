import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { TrendingUp, TrendingDown, Minus, Loader2, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";

/* ──────────────────────────────────────────────────────────────────────────
 * MacroStrip — India macro indicators pinned above the dashboard.
 *
 * Layout: 4-col grid (mobile) → 8-col grid (lg). Tiles stretch to fill
 * the container — no horizontal scroll, no clipping.
 * ────────────────────────────────────────────────────────────────────── */

interface MacroTile {
  id:          string;
  label:       string;
  unit:        string;
  value:       number | null;
  delta:       number | null;
  deltaUnit:   string;
  asOf:        string | null;
  servedFrom?: string;
  isStale?:    boolean;
  staleDays?:  number | null;
}

function fmtValue(v: number | null | undefined, unit: string): string {
  if (v == null || isNaN(v)) return "—";
  const prefix = unit === "₹" ? "₹" : unit === "$" ? "$" : "";
  const suffix = unit !== "₹" && unit !== "$" ? unit : "";
  const decimals = Math.abs(v) >= 10000 ? 0 : Math.abs(v) >= 100 ? 1 : 2;
  const num = v.toLocaleString("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return `${prefix}${num}${suffix}`;
}

function fmtDelta(d: number | null | undefined, unit: string): string {
  if (d == null || isNaN(d) || d === 0) return "";
  const sign = d > 0 ? "+" : "";
  const decimals = Math.abs(d) < 10 ? 2 : 1;
  return `${sign}${d.toFixed(decimals)}${unit}`;
}

function Tile({ tile, isLast }: { tile: MacroTile; isLast: boolean }) {
  const up    = (tile.delta ?? 0) > 0;
  const down  = (tile.delta ?? 0) < 0;
  const stale = tile.isStale === true;
  const deltaStr = fmtDelta(tile.delta, tile.deltaUnit);
  const hasValue = tile.value != null && !isNaN(tile.value);

  return (
    <Link
      href="/insights/macro"
      title={
        stale && tile.staleDays != null
          ? `Data is ${tile.staleDays} days old — source: ${tile.servedFrom ?? "FRED"}`
          : tile.asOf ? `As of ${tile.asOf.slice(0, 10)}` : undefined
      }
      className={`
        group relative flex flex-col justify-between gap-0.5 px-3 py-2 cursor-pointer
        hover:bg-white dark:hover:bg-gray-800/80 rounded-lg transition-colors
        ${stale ? "hover:bg-amber-50 dark:hover:bg-amber-900/10" : ""}
        ${!isLast ? "border-r border-gray-200 dark:border-gray-700" : ""}
      `}
    >
      {/* Label */}
      <p className="text-[9px] font-bold uppercase tracking-widest text-gray-400 dark:text-gray-500 flex items-center gap-0.5 leading-none">
        {tile.label}
        {stale && <AlertTriangle className="w-2 h-2 text-amber-500 flex-shrink-0" />}
      </p>

      {/* Value */}
      <p className={`text-sm font-bold leading-snug whitespace-nowrap ${
        hasValue ? "text-gray-900 dark:text-white" : "text-gray-300 dark:text-gray-600"
      }`}>
        {hasValue ? fmtValue(tile.value, tile.unit) : "—"}
      </p>

      {/* Delta */}
      {deltaStr ? (
        <p className={`text-[10px] font-semibold flex items-center gap-0.5 leading-none whitespace-nowrap
          ${up   ? "text-emerald-600 dark:text-emerald-400" : ""}
          ${down ? "text-red-500    dark:text-red-400"      : ""}`}
        >
          {up   && <TrendingUp   className="w-2.5 h-2.5 flex-shrink-0" />}
          {down && <TrendingDown className="w-2.5 h-2.5 flex-shrink-0" />}
          {deltaStr}
        </p>
      ) : (
        <p className="text-[10px] text-gray-300 dark:text-gray-600 flex items-center gap-0.5 leading-none">
          <Minus className="w-2.5 h-2.5" />
          <span>—</span>
        </p>
      )}

      {/* Stale accent bar */}
      {stale && (
        <span className="absolute bottom-0 left-2 right-2 h-[2px] rounded-full bg-amber-400 dark:bg-amber-500 opacity-60" />
      )}
    </Link>
  );
}

export default function MacroStrip() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["macro-strip"],
    queryFn:  api.macroStrip,
    staleTime: 60 * 60 * 1000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });

  if (error) return null;

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-900/40 px-4 py-2.5">
        <Loader2 className="w-3 h-3 animate-spin text-indigo-500 flex-shrink-0" />
        <span className="text-xs text-gray-400">Loading macro indicators…</span>
      </div>
    );
  }

  const tiles = (data?.tiles ?? []) as MacroTile[];
  if (tiles.length === 0) return null;

  return (
    <div className="rounded-xl border border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-900/40 overflow-hidden">
      {/* Header label */}
      <div className="px-3 pt-2 pb-1 border-b border-gray-100 dark:border-gray-800">
        <span className="text-[9px] font-black uppercase tracking-[0.25em] text-gray-400 dark:text-gray-500">
          Macro Pulse — India
        </span>
      </div>

      {/* Tile grid: 4 cols on mobile, 8 on large screens */}
      <div className="grid grid-cols-4 lg:grid-cols-8">
        {tiles.map((t, i) => (
          <Tile key={t.id} tile={t} isLast={i === tiles.length - 1} />
        ))}
      </div>
    </div>
  );
}
