/**
 * tier-meta.ts
 * ============
 * Single source of truth for momentum tier and economic-cycle phase
 * colour/label configuration used across Sectors, SectorDetail, and
 * HydraAlpha components.
 *
 * Import from here instead of defining getTierMeta / getPhaseMeta locally.
 */

export type TierKey = "DEEP_GREEN" | "LIGHT_GREEN" | "YELLOW" | "ORANGE" | "DEEP_RED" | "UNKNOWN";

export interface TierMeta {
  label:  string;
  color:  string;
  bg:     string;
  border: string;
  badge:  string;
}

export type PhaseKey =
  | "Early Cycle / Recovery"
  | "Mid Cycle / Expansion"
  | "Late Cycle / Slowdown"
  | "Recession / Contraction";

export interface PhaseMeta {
  icon:   string;
  abbr:   string;
  color:  string;
  bg:     string;
  border: string;
}

export const PHASE_ORDER: PhaseKey[] = [
  "Early Cycle / Recovery",
  "Mid Cycle / Expansion",
  "Late Cycle / Slowdown",
  "Recession / Contraction",
];

export function getTierMeta(isDark: boolean): Record<TierKey, TierMeta> {
  return {
    DEEP_GREEN:  { label: "Deep Green",  color: isDark ? "#4ade80" : "#15803d", bg: isDark ? "rgba(21,128,61,0.2)"    : "#dcfce7", border: isDark ? "rgba(74,222,128,0.3)"   : "#86efac", badge: "bg-green-700 text-white" },
    LIGHT_GREEN: { label: "Light Green", color: isDark ? "#86efac" : "#16a34a", bg: isDark ? "rgba(22,163,74,0.15)"   : "#f0fdf4", border: isDark ? "rgba(134,239,172,0.3)"  : "#bbf7d0", badge: "bg-green-500 text-white" },
    YELLOW:      { label: "Neutral",     color: isDark ? "#fde047" : "#ca8a04", bg: isDark ? "rgba(202,138,4,0.15)"   : "#fefce8", border: isDark ? "rgba(253,224,71,0.3)"   : "#fde68a", badge: "bg-yellow-500 text-white" },
    ORANGE:      { label: "Weakening",   color: isDark ? "#fb923c" : "#ea580c", bg: isDark ? "rgba(234,88,12,0.15)"   : "#fff7ed", border: isDark ? "rgba(251,146,60,0.3)"   : "#fed7aa", badge: "bg-orange-500 text-white" },
    DEEP_RED:    { label: "Deep Red",    color: isDark ? "#f87171" : "#dc2626", bg: isDark ? "rgba(220,38,38,0.15)"   : "#fef2f2", border: isDark ? "rgba(248,113,113,0.3)"  : "#fecaca", badge: "bg-red-600 text-white" },
    UNKNOWN:     { label: "No Data",     color: isDark ? "#94a3b8" : "#6b7280", bg: isDark ? "rgba(100,116,139,0.15)" : "#f3f4f6", border: isDark ? "rgba(148,163,184,0.3)"  : "#e5e7eb", badge: "bg-gray-500 text-white" },
  };
}

export function getPhaseMeta(isDark: boolean): Record<PhaseKey, PhaseMeta> {
  return {
    "Early Cycle / Recovery":  { icon: "🌱", abbr: "Early",     color: isDark ? "#86efac" : "#16a34a", bg: isDark ? "rgba(22,163,74,0.15)"  : "#f0fdf4", border: isDark ? "rgba(134,239,172,0.3)" : "#bbf7d0" },
    "Mid Cycle / Expansion":   { icon: "🚀", abbr: "Mid",       color: isDark ? "#93c5fd" : "#2563eb", bg: isDark ? "rgba(37,99,235,0.15)"  : "#eff6ff", border: isDark ? "rgba(147,197,253,0.3)" : "#bfdbfe" },
    "Late Cycle / Slowdown":   { icon: "🌅", abbr: "Late",      color: isDark ? "#fcd34d" : "#d97706", bg: isDark ? "rgba(217,119,6,0.15)"  : "#fffbeb", border: isDark ? "rgba(252,211,77,0.3)"  : "#fde68a" },
    "Recession / Contraction": { icon: "🛡️", abbr: "Recession", color: isDark ? "#f87171" : "#dc2626", bg: isDark ? "rgba(220,38,38,0.15)"  : "#fef2f2", border: isDark ? "rgba(248,113,113,0.3)" : "#fecaca" },
  };
}

/** Pick a tier from the map, falling back to UNKNOWN for unrecognised keys. */
export function pickTier(meta: Record<TierKey, TierMeta>, key: string | undefined): TierMeta {
  return meta[(key as TierKey) ?? "UNKNOWN"] ?? meta.UNKNOWN;
}
