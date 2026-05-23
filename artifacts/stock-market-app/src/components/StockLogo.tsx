/**
 * StockLogo — single source of truth for rendering an Indian stock's logo.
 *
 * Logo source
 * -----------
 * Dhan hosts logos for every NSE-listed symbol at a stable public CDN URL:
 *   https://images.dhan.co/symbol/<NSE_SYMBOL>.png
 *
 * No auth, no API key, no rate-limit (it's a static-asset CDN). We've been
 * using this URL in Insights→MfHoldings, Insights→BulkBlockDeals and
 * Insights→TopDeliveries — each had its own local copy of an `<img>`
 * with onError fallback. This component is the centralized version.
 *
 * Symbol normalisation
 * --------------------
 * Strips the suffixes that show up in tickers from various sources
 * (`.NS`, `.BO`, `-EQ`, `:NSE`, `:BSE`) before building the URL so
 * `RELIANCE.NS`, `RELIANCE-EQ`, and `RELIANCE` all hit the same asset.
 *
 * Fallback
 * --------
 * On image-load error (Dhan doesn't have a logo for that symbol — true
 * for ~5% of long-tail tickers and for SME issues) the component shows
 * a deterministic colored circle/square with the symbol's first letter.
 * Same visual treatment Groww / Zerodha use when a logo isn't available.
 *
 * Variants
 * --------
 *   shape="rounded" → rounded-lg square (default, matches Insights tabs)
 *   shape="circle"  → rounded-full (matches Top Movers / Groww style)
 */
import { useState } from "react";

interface StockLogoProps {
  /** NSE ticker. Suffixes like `.NS` are stripped automatically. */
  symbol: string;
  /** Optional company name — used for the alt-text only. */
  name?: string | null;
  /** Edge length in pixels. Default 32. */
  size?: number;
  /** Layout / visual shape. Default rounded-lg square. */
  shape?: "rounded" | "circle";
  /** Optional explicit URL — bypasses Dhan CDN URL construction.
   *  Used by the Insights tabs where the backend already attaches a
   *  pre-built Dhan URL (or an alternative source). When absent we
   *  build the URL from the symbol. */
  logo?: string | null;
  className?: string;
}


/** Cleanest form of an NSE ticker — also used as the Dhan CDN key. */
function _normalizeSymbol(sym: string): string {
  let s = (sym || "").trim().toUpperCase();
  for (const suffix of [".NS", ".BO", "-EQ", ":NSE", ":BSE"]) {
    if (s.endsWith(suffix)) {
      s = s.slice(0, -suffix.length);
      break;
    }
  }
  return s;
}


/** Deterministic gradient pair from the symbol — stable per ticker so
 *  RELIANCE always gets the same fallback color across mounts. */
function _initialsGradient(symbol: string): string {
  const palette: string[] = [
    "from-indigo-500 to-violet-600",
    "from-emerald-500 to-teal-600",
    "from-rose-500 to-pink-600",
    "from-amber-500 to-orange-600",
    "from-blue-500 to-cyan-600",
    "from-purple-500 to-fuchsia-600",
    "from-lime-500 to-emerald-600",
    "from-red-500 to-rose-600",
    "from-sky-500 to-indigo-600",
    "from-fuchsia-500 to-purple-600",
  ];
  const hash = (symbol || "").split("")
    .reduce((acc, c) => acc + c.charCodeAt(0), 0);
  return palette[hash % palette.length];
}


export default function StockLogo({
  symbol,
  name,
  size = 32,
  shape = "rounded",
  logo,
  className = "",
}: StockLogoProps) {
  // Track image errors so we render the fallback after the first failure.
  // Reset on URL change so a re-mount with a different symbol re-tries.
  const [errored, setErrored] = useState(false);
  const clean = _normalizeSymbol(symbol);
  const url = (logo && logo.length > 0)
    ? logo
    : (clean ? `https://images.dhan.co/symbol/${clean}.png` : "");

  const radius = shape === "circle" ? "rounded-full" : "rounded-lg";
  const sizeStyle = { width: size, height: size };
  // Initials font scales with badge size — keeps the letter readable
  // at 16px and not overbearing at 64px.
  const fontPx = Math.max(9, Math.round(size * 0.36));

  if (!url || errored) {
    const initial = (clean || name || "?")[0]?.toUpperCase() ?? "?";
    const gradient = _initialsGradient(clean || name || "");
    return (
      <div
        style={{ ...sizeStyle, fontSize: fontPx }}
        className={`${radius} flex items-center justify-center font-bold text-white bg-gradient-to-br ${gradient} flex-shrink-0 ${className}`}
        aria-label={`${clean || name || "stock"} logo placeholder`}
      >
        {initial}
      </div>
    );
  }

  // Real logo from Dhan CDN. White background + thin padding keeps
  // transparent-PNG logos legible against dark mode.
  return (
    <img
      src={url}
      alt={name || clean || "stock logo"}
      loading="lazy"
      onError={() => setErrored(true)}
      style={sizeStyle}
      className={`${radius} object-contain bg-white border border-gray-200 dark:border-gray-700 p-0.5 flex-shrink-0 ${className}`}
    />
  );
}
