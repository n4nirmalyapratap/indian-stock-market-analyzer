import { useLocation } from "wouter";
import { LineChart, SearchCode, PieChart } from "lucide-react";
import type { PatternOverlay } from "@/components/trading/ChartPanel";

interface ChartButtonProps {
  symbol: string;
  className?: string;
  /** Hide the secondary lookup/detail icon (e.g. when rendered inside the destination page itself). */
  hideLookup?: boolean;
  /** Comma-separated indicator keys to pre-apply in Chart Studio (e.g. "rsi,ema50,macd"). */
  indicators?: string;
  /** Detected pattern geometry to replay as a read-only overlay in Chart Studio (symbol is attached here). */
  overlay?: Omit<PatternOverlay, "symbol"> | null;
}

/**
 * A compact action group placed next to any stock or sector name.
 * Always renders the Chart Studio icon, plus a context-aware second icon:
 *   • Stocks  → SearchCode → Stock Lookup    (`/stocks?symbol=…`)
 *   • Sectors → PieChart   → Sector Detail   (`/sectors/…`)
 *
 * Sector vs stock is detected by the presence of whitespace in the symbol
 * (e.g. "NIFTY BANK", "NIFTY 50", "BANK NIFTY"). Stock tickers never have
 * spaces (RELIANCE, HDFCBANK, M&M).
 *
 * Kept as a single drop-in component so all existing call-sites
 * (`<ChartButton symbol="RELIANCE.NS" />`) automatically gain the second
 * icon without any code changes.
 */
export default function ChartButton({ symbol, className = "", hideLookup = false, indicators, overlay }: ChartButtonProps) {
  const [, navigate] = useLocation();
  const clean = symbol.replace(/\.(NS|BO)$/i, "").trim().toUpperCase();
  const isSector = /\s/.test(clean);

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
          let overlayParam = "";
          if (overlay && (overlay.markers?.length || overlay.lines?.length)) {
            // Geometry is too large for the URL, so hand it over via sessionStorage;
            // the ?overlay=1 flag tells Chart Studio to consume it once on arrival.
            try {
              sessionStorage.setItem("_patternOverlay", JSON.stringify({ ...overlay, symbol: clean }));
              overlayParam = "&overlay=1";
            } catch { /* sessionStorage unavailable — open chart without the overlay */ }
          }
          navigate(`/trading?symbol=${encodeURIComponent(clean)}${indicators ? `&indicators=${encodeURIComponent(indicators)}` : ""}${overlayParam}`);
        }}
        title={overlay ? `Open ${clean} in Chart Studio — pattern drawn` : `Open ${clean} in Chart Studio`}
        aria-label={`Open ${clean} in Chart Studio`}
        className={`${baseBtn} text-indigo-400 dark:text-indigo-400 hover:text-indigo-600 dark:hover:text-indigo-300 hover:bg-indigo-100 dark:hover:bg-indigo-900/40`}
      >
        <LineChart className="w-3.5 h-3.5" />
      </button>
      {!hideLookup && (isSector ? (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/sectors/${encodeURIComponent(clean)}`);
          }}
          title={`Open ${clean} sector page`}
          aria-label={`Open ${clean} in Sector Detail`}
          className={`${baseBtn} text-emerald-500 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300 hover:bg-emerald-100 dark:hover:bg-emerald-900/40`}
        >
          <PieChart className="w-3.5 h-3.5" />
        </button>
      ) : (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            sessionStorage.setItem("_stockLookupRef", "1");
            navigate(`/stocks?symbol=${encodeURIComponent(clean)}`);
          }}
          title={`Look up ${clean}`}
          aria-label={`Look up ${clean} in Stock Lookup`}
          className={`${baseBtn} text-violet-400 dark:text-violet-400 hover:text-violet-600 dark:hover:text-violet-300 hover:bg-violet-100 dark:hover:bg-violet-900/40`}
        >
          <SearchCode className="w-3.5 h-3.5" />
        </button>
      ))}
    </span>
  );
}
