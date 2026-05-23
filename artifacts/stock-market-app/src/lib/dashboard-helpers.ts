/** Format the A/D ratio for display. When declining=0 we have no real
 * denominator — returning the literal advancing count would be misleading
 * (it's not a "ratio"), so we surface "∞" instead. */
export function formatAdRatio(advancing: number, declining: number): string {
  if (advancing === 0 && declining === 0) return "—";
  if (declining === 0) return "∞";
  return (advancing / declining).toFixed(2);
}

/** Strip the "Nifty " prefix for compact sector cards, but keep "Nifty 50"
 * and "Nifty Next 50" intact since dropping the prefix leaves an ambiguous
 * bare number ("50"). */
export function shortSectorName(name: string): string {
  if (!name) return "";
  if (/^Nifty\s+(?:Next\s+)?\d+$/i.test(name)) return name;
  return name.replace(/^Nifty\s+/i, "");
}

/** Format a percentage change, falling through gracefully when null/undefined.
 * Renders "—" when the value is genuinely missing (null/undefined) so a
 * data-fetch failure isn't displayed as "+0.00%". A legitimate 0.0%
 * still renders as "+0.00%". */
export function formatPctChange(p: number | null | undefined): string {
  if (p === null || p === undefined || Number.isNaN(p)) return "—";
  return `${p >= 0 ? "+" : ""}${p.toFixed(2)}%`;
}
