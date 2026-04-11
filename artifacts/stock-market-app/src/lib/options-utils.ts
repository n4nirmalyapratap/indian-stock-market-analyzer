/**
 * options-utils.ts
 * Pure utility functions for the Options Strategy Tester.
 * Extracted here so they can be unit-tested without rendering React components.
 */

// ── INR formatter ─────────────────────────────────────────────────────────────
export function fmtINR(n: number | null | undefined): string {
  if (n == null) return "—";
  const sign = n < 0 ? "-" : "";
  const v = Math.abs(n);
  if (v >= 1e7) return `${sign}₹${(v / 1e7).toFixed(2)}Cr`;
  if (v >= 1e5) return `${sign}₹${(v / 1e5).toFixed(2)}L`;
  return `${sign}₹${v.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

// ── Generic formatters ────────────────────────────────────────────────────────
export function pct(n: number | null | undefined, d = 2): string {
  return n == null ? "—" : `${Number(n).toFixed(d)}%`;
}

export function fmt(n: number | null | undefined, d = 2): string {
  return n == null ? "—" : Number(n).toFixed(d);
}

// ── Color helpers ─────────────────────────────────────────────────────────────
export function clr(v: number): string {
  return v >= 0 ? "text-green-600" : "text-red-500";
}

export function bg(v: number): string {
  return v >= 0 ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600";
}

// ── Heatmap bar data ──────────────────────────────────────────────────────────
export interface HeatBar {
  s:     number;
  pnl:   number;
  color: string;
}

/**
 * Compute the downsampled heatmap bar array for the P&L heatmap.
 * Maximum ~80 bars for performance (matching PnlHeatmap component).
 */
export function computeHeatBars(
  spots: number[],
  payoffs: number[],
  maxBars = 80,
): HeatBar[] {
  if (spots.length === 0) return [];
  const maxAbs = Math.max(...payoffs.map(Math.abs), 1);
  const step   = Math.max(1, Math.floor(spots.length / maxBars));

  return spots
    .filter((_, i) => i % step === 0)
    .map((s, i) => {
      const pnl  = payoffs[i * step] ?? 0;
      const norm = Math.min(Math.abs(pnl) / maxAbs, 1);
      const alpha = 0.12 + norm * 0.88;
      const color =
        pnl > 0 ? `rgba(22,163,74,${alpha})`
        : pnl < 0 ? `rgba(220,38,38,${alpha})`
        : "rgba(200,200,200,0.2)";
      return { s, pnl, color };
    });
}

// ── Quick-strategy definitions (leg counts + composition) ─────────────────────

export type Outlook = "bullish" | "bearish" | "neutral" | "volatile";

export interface QuickLeg {
  action:      "buy" | "sell";
  option_type: "call" | "put";
  lots:        number;
  otmMult?:    number;
  spreadMult?: number;
}

export interface QuickStrategy {
  label:    string;
  category: string;
  outlook:  Outlook;
  legs:     QuickLeg[];
}

export const QUICK_STRATEGIES: QuickStrategy[] = [
  // ── Directional ──────────────────────────────────────────────────────
  { label: "Long Call",  category: "Directional", outlook: "bullish",
    legs: [{ action: "buy",  option_type: "call", lots: 1, otmMult: 0 }] },
  { label: "Short Put",  category: "Directional", outlook: "bullish",
    legs: [{ action: "sell", option_type: "put",  lots: 1, otmMult: 1 }] },
  { label: "Long Put",   category: "Directional", outlook: "bearish",
    legs: [{ action: "buy",  option_type: "put",  lots: 1, otmMult: 0 }] },
  { label: "Short Call", category: "Directional", outlook: "bearish",
    legs: [{ action: "sell", option_type: "call", lots: 1, otmMult: 1 }] },
  // ── Volatility ───────────────────────────────────────────────────────
  { label: "Long Straddle",  category: "Volatility", outlook: "volatile",
    legs: [{ action: "buy", option_type: "call", lots: 1, otmMult: 0 },
           { action: "buy", option_type: "put",  lots: 1, otmMult: 0 }] },
  { label: "Long Strangle",  category: "Volatility", outlook: "volatile",
    legs: [{ action: "buy", option_type: "call", lots: 1, otmMult: 1 },
           { action: "buy", option_type: "put",  lots: 1, otmMult: 1 }] },
  { label: "Short Straddle", category: "Volatility", outlook: "neutral",
    legs: [{ action: "sell", option_type: "call", lots: 1, otmMult: 0 },
           { action: "sell", option_type: "put",  lots: 1, otmMult: 0 }] },
  { label: "Short Strangle", category: "Volatility", outlook: "neutral",
    legs: [{ action: "sell", option_type: "call", lots: 1, otmMult: 1 },
           { action: "sell", option_type: "put",  lots: 1, otmMult: 1 }] },
  // ── Spreads ──────────────────────────────────────────────────────────
  { label: "Bull Call Spread", category: "Spreads", outlook: "bullish",
    legs: [{ action: "buy",  option_type: "call", lots: 1, otmMult: 0 },
           { action: "sell", option_type: "call", lots: 1, otmMult: 1 }] },
  { label: "Bear Put Spread",  category: "Spreads", outlook: "bearish",
    legs: [{ action: "buy",  option_type: "put",  lots: 1, otmMult: 0 },
           { action: "sell", option_type: "put",  lots: 1, otmMult: 1 }] },
  // ── Multi-leg ─────────────────────────────────────────────────────────
  { label: "Iron Condor", category: "Multi-leg", outlook: "neutral",
    legs: [{ action: "sell", option_type: "call", lots: 1, otmMult: 1 },
           { action: "buy",  option_type: "call", lots: 1, otmMult: 2 },
           { action: "sell", option_type: "put",  lots: 1, otmMult: 1 },
           { action: "buy",  option_type: "put",  lots: 1, otmMult: 2 }] },
  { label: "Butterfly",   category: "Multi-leg", outlook: "neutral",
    legs: [{ action: "buy",  option_type: "call", lots: 1, otmMult: -1 },
           { action: "sell", option_type: "call", lots: 2, otmMult:  0 },
           { action: "buy",  option_type: "call", lots: 1, otmMult:  1 }] },
];

/** Expected leg counts per strategy label — ground truth for tests. */
export const EXPECTED_LEG_COUNTS: Record<string, number> = {
  "Long Call":        1,
  "Short Put":        1,
  "Long Put":         1,
  "Short Call":       1,
  "Long Straddle":    2,
  "Long Strangle":    2,
  "Short Straddle":   2,
  "Short Strangle":   2,
  "Bull Call Spread": 2,
  "Bear Put Spread":  2,
  "Iron Condor":      4,
  "Butterfly":        3,
};

/** Maximum total lots in a strategy (sum across all legs). */
export function totalLots(legs: QuickLeg[]): number {
  return legs.reduce((s, l) => s + l.lots, 0);
}

/** Returns the net directional bias: net buy legs minus net sell legs. */
export function netDirection(legs: QuickLeg[]): number {
  return legs.reduce((acc, l) => acc + (l.action === "buy" ? 1 : -1), 0);
}
