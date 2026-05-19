import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { TrendingUp, TrendingDown, Loader2, Minus } from "lucide-react";
import { api } from "@/lib/api";

/* ──────────────────────────────────────────────────────────────────────────
 * MacroStrip — six tiles pinned across the top of the dashboard:
 *   Repo · CPI · IIP · USD/INR · India 10Y · Brent
 * Each tile shows value, unit, delta arrow, and links to /insights/macro.
 * ────────────────────────────────────────────────────────────────────── */

function fmtValue(v: number | null | undefined, unit: string): string {
  if (v == null || isNaN(v)) return "—";
  if (unit === "₹") return `₹${v.toFixed(2)}`;
  if (unit === "$") return `$${v.toFixed(2)}`;
  return `${v.toFixed(2)}${unit}`;
}

function fmtDelta(d: number | null | undefined, unit: string): string {
  if (d == null || isNaN(d)) return "—";
  const sign = d >= 0 ? "+" : "";
  return `${sign}${d.toFixed(2)}${unit}`;
}

function Tile({ tile }: { tile: MacroTile }) {
  const up   = (tile.delta ?? 0) > 0;
  const down = (tile.delta ?? 0) < 0;
  const flat = tile.delta == null || tile.delta === 0;

  return (
    <Link
      href="/insights/macro"
      className="flex-1 min-w-0 group bg-white dark:bg-gray-800 rounded-lg border border-gray-100 dark:border-gray-700 px-3 py-2 hover:border-indigo-300 dark:hover:border-indigo-600 hover:shadow-sm transition cursor-pointer"
    >
      <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 truncate">
        {tile.label}
      </p>
      <div className="flex items-baseline justify-between gap-1 mt-0.5">
        <span className="text-sm font-bold text-gray-900 dark:text-white truncate">
          {fmtValue(tile.value, tile.unit)}
        </span>
        <span
          className={`text-[11px] font-semibold flex items-center gap-0.5 flex-shrink-0
            ${up ? "text-green-600 dark:text-green-400" : ""}
            ${down ? "text-red-500 dark:text-red-400" : ""}
            ${flat ? "text-gray-400 dark:text-gray-500" : ""}`}
        >
          {up && <TrendingUp className="w-3 h-3" />}
          {down && <TrendingDown className="w-3 h-3" />}
          {flat && <Minus className="w-3 h-3" />}
          {fmtDelta(tile.delta, tile.deltaUnit)}
        </span>
      </div>
    </Link>
  );
}

interface MacroTile {
  id: string;
  label: string;
  unit: string;
  value: number | null;
  delta: number | null;
  deltaUnit: string;
  asOf: string | null;
}

export default function MacroStrip() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["macro-strip"],
    queryFn:  api.macroStrip,
    staleTime: 60 * 60 * 1000,         // 1 h frontend stale
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });

  if (error) return null; // Macro strip is supplementary — fail silently.

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 bg-gray-50 dark:bg-gray-900/50 rounded-xl border border-gray-100 dark:border-gray-800 px-3 py-2">
        <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-500" />
        <span className="text-xs text-gray-500 dark:text-gray-400">Loading macro pulse…</span>
      </div>
    );
  }

  const tiles = (data?.tiles ?? []) as MacroTile[];
  if (tiles.length === 0) return null;

  return (
    <div className="bg-gray-50 dark:bg-gray-900/40 rounded-xl border border-gray-100 dark:border-gray-800 p-1.5">
      <div className="flex items-center gap-1.5 overflow-x-auto">
        <span className="text-[10px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 px-2 py-1 flex-shrink-0">
          Macro Pulse
        </span>
        {tiles.map(t => <Tile key={t.id} tile={t} />)}
      </div>
    </div>
  );
}
