/**
 * StockLogo — single source of truth for rendering an Indian stock's logo.
 *
 * Logo source
 * -----------
 * Logos are served from our own backend at `/api/logos/<SYMBOL>`. The
 * backend fetches from Dhan's CDN on first access and caches the raw PNG
 * binary in PostgreSQL, so the external CDN is called at most once per
 * symbol and our pages load logos from localhost (< 1 ms vs CDN round-trip).
 *
 * Admins can override the fetch key for any symbol (e.g. LTIM → LTIMindtree)
 * from the Admin Dashboard → Logo Cache page.
 *
 * Symbol normalisation
 * --------------------
 * Strips the suffixes that show up in tickers from various sources
 * (`.NS`, `.BO`, `-EQ`, `:NSE`, `:BSE`) before building the URL so
 * `RELIANCE.NS`, `RELIANCE-EQ`, and `RELIANCE` all hit the same cache row.
 *
 * Fallback
 * --------
 * On image-load error (backend returns 204 — no logo for that symbol) the
 * component shows a deterministic colored circle/square with the symbol's
 * first letter. Same visual treatment Groww / Zerodha use.
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
  /** Optional explicit URL — bypasses the backend cache endpoint.
   *  Used when the caller has already built a Dhan URL or an alternative
   *  source (e.g. AMC logo from Insights tabs). */
  logo?: string | null;
  className?: string;
}


/** Cleanest form of an NSE ticker — used as the cache key. */
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
  const [errored, setErrored] = useState(false);
  const clean = _normalizeSymbol(symbol);

  // If the caller passes an explicit logo URL (e.g. AMC logos from Insights),
  // use it directly without going through the backend cache.
  const url = (logo && logo.length > 0)
    ? logo
    : (clean ? `/api/logos/${clean}` : "");

  const radius = shape === "circle" ? "rounded-full" : "rounded-lg";
  const sizeStyle = { width: size, height: size };
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
