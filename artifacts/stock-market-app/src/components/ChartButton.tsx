import { useLocation } from "wouter";
import { LineChart, SearchCode } from "lucide-react";

interface ChartButtonProps {
  symbol: string;
  className?: string;
  /** Hide the Stock Lookup icon (e.g. when rendered inside the lookup page itself). */
  hideLookup?: boolean;
}

/**
 * A compact action group placed next to any stock or sector name.
 * Renders two subtle icons:
 *   • LineChart  → Chart Studio (`/trading?symbol=…`)
 *   • SearchCode → Stock Lookup (`/stocks?symbol=…`)
 *
 * Kept as a single drop-in component so all existing call-sites
 * (`<ChartButton symbol="RELIANCE.NS" />`) automatically gain the
 * second icon without any code changes.
 *
 * Usage:
 *   <ChartButton symbol="RELIANCE.NS" />            ← stock (.NS stripped automatically)
 *   <ChartButton symbol="NIFTY BANK" />             ← sector index (chart only)
 *   <ChartButton symbol="ITC" hideLookup />         ← suppress lookup icon
 */
export default function ChartButton({ symbol, className = "", hideLookup = false }: ChartButtonProps) {
  const [, navigate] = useLocation();
  const clean = symbol.replace(/\.(NS|BO)$/i, "").trim().toUpperCase();
  // Sector indices ("NIFTY BANK", "BANK NIFTY", "NIFTY 50") shouldn't go to
  // /stocks lookup — that page is for tickers only. Detect by space.
  const isIndex = /\s/.test(clean);
  const showLookup = !hideLookup && !isIndex;

  const baseBtn =
    "inline-flex items-center justify-center w-5 h-5 rounded-md flex-shrink-0 " +
    "opacity-60 hover:opacity-100 transition-all duration-150";

  return (
    <span
      className={`inline-flex items-center gap-0.5 align-middle ${className}`}
      onClick={(e) => e.stopPropagation()}
    >
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          navigate(`/trading?symbol=${encodeURIComponent(clean)}`);
        }}
        title={`Open ${clean} in Chart Studio`}
        aria-label={`Open ${clean} in Chart Studio`}
        className={`${baseBtn} text-indigo-400 dark:text-indigo-400 hover:text-indigo-600 dark:hover:text-indigo-300 hover:bg-indigo-100 dark:hover:bg-indigo-900/40`}
      >
        <LineChart className="w-3.5 h-3.5" />
      </button>
      {showLookup && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/stocks?symbol=${encodeURIComponent(clean)}`);
          }}
          title={`Look up ${clean}`}
          aria-label={`Look up ${clean} in Stock Lookup`}
          className={`${baseBtn} text-violet-400 dark:text-violet-400 hover:text-violet-600 dark:hover:text-violet-300 hover:bg-violet-100 dark:hover:bg-violet-900/40`}
        >
          <SearchCode className="w-3.5 h-3.5" />
        </button>
      )}
    </span>
  );
}
