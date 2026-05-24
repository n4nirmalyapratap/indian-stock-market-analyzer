import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { TrendingUp, TrendingDown, Minus, Loader2, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";

/* ──────────────────────────────────────────────────────────────────────────
 * MacroStrip — eight tiles pinned across the top of the dashboard.
 * Design constraints:
 *   • Each tile has a fixed minimum width so values never get clipped.
 *   • Values are formatted compactly (3 sig-figs max) so they fit.
 *   • Delta row is always on its own line — no horizontal space-fight.
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

/** Format a value compactly so it never overflows the tile.
 *  Examples: 84.2345 → "84.23", 6500 → "6,500", 0.065 → "0.07" */
function fmtValue(v: number | null | undefined, unit: string): string {
  if (v == null || isNaN(v)) return "—";
  const prefix = unit === "₹" ? "₹" : unit === "$" ? "$" : "";
  const suffix = unit !== "₹" && unit !== "$" ? unit : "";
  // Choose decimal places based on magnitude
  let decimals = 2;
  if (Math.abs(v) >= 10000) decimals = 0;
  else if (Math.abs(v) >= 100) decimals = 1;
  const num = v.toLocaleString("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return `${prefix}${num}${suffix}`;
}

function fmtDelta(d: number | null | undefined, unit: string): string {
  if (d == null || isNaN(d)) return "";
  const sign = d > 0 ? "+" : "";
  const decimals = Math.abs(d) < 1 ? 2 : Math.abs(d) < 10 ? 2 : 1;
  return `${sign}${d.toFixed(decimals)}${unit}`;
}

function Tile({ tile }: { tile: MacroTile }) {
  const up   = (tile.delta ?? 0) > 0;
  const down = (tile.delta ?? 0) < 0;
  const flat = tile.delta == null || tile.delta === 0;
  const stale = tile.isStale === true;
  const deltaStr = fmtDelta(tile.delta, tile.deltaUnit);

  return (
    <Link
      href="/insights/macro"
      title={
        stale && tile.staleDays != null
          ? `Data is ${tile.staleDays} days old — source: ${tile.servedFrom ?? "FRED"}`
          : tile.asOf ? `As of ${tile.asOf.slice(0, 10)}` : undefined
      }
      className={`
        flex-shrink-0 w-[108px]
        group rounded-lg border px-2.5 py-2
        hover:shadow-sm transition-all cursor-pointer
        ${stale
          ? "bg-amber-50 dark:bg-amber-900/10 border-amber-300 dark:border-amber-600/50 hover:border-amber-400"
          : "bg-white dark:bg-gray-800 border-gray-100 dark:border-gray-700 hover:border-indigo-300 dark:hover:border-indigo-600"
        }
      `}
    >
      {/* Label row */}
      <p className="text-[9px] font-bold uppercase tracking-widest text-gray-400 dark:text-gray-500 flex items-center gap-0.5 leading-none">
        {tile.label}
        {stale && <AlertTriangle className="w-2 h-2 text-amber-500 flex-shrink-0" />}
      </p>

      {/* Value */}
      <p className="mt-1 text-[15px] font-bold leading-tight text-gray-900 dark:text-white whitespace-nowrap">
        {tile.value != null ? fmtValue(tile.value, tile.unit) : <span className="text-gray-300 dark:text-gray-600">—</span>}
      </p>

      {/* Delta */}
      {deltaStr ? (
        <p className={`mt-0.5 text-[10px] font-semibold flex items-center gap-0.5 leading-none whitespace-nowrap
          ${up   ? "text-emerald-600 dark:text-emerald-400" : ""}
          ${down ? "text-red-500 dark:text-red-400" : ""}
          ${flat ? "text-gray-400 dark:text-gray-500" : ""}`}
        >
          {up   && <TrendingUp   className="w-2.5 h-2.5 flex-shrink-0" />}
          {down && <TrendingDown className="w-2.5 h-2.5 flex-shrink-0" />}
          {flat && <Minus        className="w-2.5 h-2.5 flex-shrink-0" />}
          {deltaStr}
        </p>
      ) : (
        <p className="mt-0.5 text-[10px] text-gray-300 dark:text-gray-600 leading-none">—</p>
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
      <div className="flex items-center gap-2 bg-gray-50 dark:bg-gray-900/50 rounded-xl border border-gray-100 dark:border-gray-800 px-3 py-2">
        <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-500 flex-shrink-0" />
        <span className="text-xs text-gray-400 dark:text-gray-500">Loading macro pulse…</span>
      </div>
    );
  }

  const tiles = (data?.tiles ?? []) as MacroTile[];
  if (tiles.length === 0) return null;

  return (
    <div className="bg-gray-50 dark:bg-gray-900/40 rounded-xl border border-gray-100 dark:border-gray-800 px-2 py-1.5">
      <div className="flex items-stretch gap-1.5 overflow-x-auto scrollbar-none">
        {/* Strip label */}
        <div className="flex flex-col justify-center px-1 flex-shrink-0">
          <span className="text-[9px] font-black uppercase tracking-[0.2em] text-gray-400 dark:text-gray-500 [writing-mode:vertical-rl] rotate-180 select-none">
            Macro
          </span>
        </div>

        {/* Divider */}
        <div className="w-px bg-gray-200 dark:bg-gray-700 flex-shrink-0 my-0.5" />

        {/* Tiles */}
        {tiles.map(t => <Tile key={t.id} tile={t} />)}
      </div>
    </div>
  );
}
