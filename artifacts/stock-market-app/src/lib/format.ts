/**
 * format.ts
 * =========
 * Single source of truth for all number/currency/percentage formatting
 * used across the app. Import from here instead of defining local helpers.
 *
 * Re-exports the dashboard-helpers utilities so callers only need one import.
 */

export { formatPctChange, formatAdRatio, shortSectorName } from "./dashboard-helpers";

// ── Generic number ─────────────────────────────────────────────────────────────

/** Format a number to `dec` decimal places; returns "—" for null/undefined. */
export function fmt(n: number | null | undefined, dec = 2, suffix = ""): string {
  if (n == null) return "—";
  return n.toFixed(dec) + suffix;
}

/** Format a number with explicit +/− sign; returns "—" for null/undefined. */
export function fmtSigned(n: number | null | undefined, dec = 2): string {
  if (n == null) return "—";
  return (n >= 0 ? "+" : "") + n.toFixed(dec);
}

// ── Percentage ─────────────────────────────────────────────────────────────────

/** Plain percentage without sign: "18.00%". Returns "—" for null. */
export function pct(n: number | null | undefined, dec = 2): string {
  if (n == null) return "—";
  return Number(n).toFixed(dec) + "%";
}

/** Signed percentage: "+1.23%" / "-0.45%". Returns "—" for null. */
export function fmtPct(n: number | null | undefined, dec = 2): string {
  if (n == null) return "—";
  return (n >= 0 ? "+" : "") + n.toFixed(dec) + "%";
}

// ── Indian currency ────────────────────────────────────────────────────────────

/**
 * Format a value in Indian units (Cr / L) with ₹ prefix.
 * Input is assumed to be in raw ₹ (not crores).
 * Examples: 1.5e9 → "₹150.00Cr", 1.2e11 → "₹12.00Kcr"
 */
export function fmtINR(n: number | null | undefined): string {
  if (n == null) return "—";
  const sign = n < 0 ? "-" : "";
  const v = Math.abs(n);
  if (v >= 1e7) return `${sign}₹${(v / 1e7).toFixed(2)}Cr`;
  if (v >= 1e5) return `${sign}₹${(v / 1e5).toFixed(2)}L`;
  return `${sign}₹${v.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

/**
 * Format a value already in ₹ Crore.
 * Used for sector / company financial figures reported in Cr.
 */
export function fmtCr(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_00_000) return "₹" + (n / 1_00_000).toFixed(1) + "L Cr";
  if (n >= 100)      return "₹" + n.toFixed(0) + " Cr";
  return "₹" + n.toFixed(2);
}

/**
 * Format sector/index market cap in ₹ Lakh Crore (already in L Cr).
 */
export function fmtMarketCap(cap: number | null | undefined): string {
  if (cap == null) return "—";
  return "₹" + cap.toFixed(1) + " L Cr";
}

// ── Tailwind colour helpers ────────────────────────────────────────────────────

/** Tailwind text-colour class based on sign. */
export function clr(v: number | null | undefined): string {
  if (v == null) return "text-gray-400";
  return v >= 0 ? "text-green-600" : "text-red-500";
}

/** Tailwind text-colour class (dark-mode variant). */
export function clrDark(v: number | null | undefined): string {
  if (v == null) return "text-gray-500";
  return v >= 0 ? "text-green-400" : "text-red-400";
}

/** Tailwind background+text badge class based on sign. */
export function bg(v: number | null | undefined): string {
  if (v == null) return "bg-gray-100 text-gray-500";
  return v >= 0 ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600";
}

/** Hex colour for percentage-based colour scales (e.g. sector detail charts). */
export function colorForPct(val: number | null | undefined): string {
  if (val == null) return "#6b7280";
  if (val >= 2)   return "#16a34a";
  if (val >= 0)   return "#4ade80";
  if (val >= -2)  return "#f87171";
  return "#dc2626";
}
