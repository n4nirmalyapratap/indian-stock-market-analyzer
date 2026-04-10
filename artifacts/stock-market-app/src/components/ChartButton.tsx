import { useLocation } from "wouter";
import { LineChart } from "lucide-react";

interface ChartButtonProps {
  symbol: string;
  className?: string;
}

/**
 * A subtle chart-studio link placed next to any stock or sector name.
 * Clicking opens Chart Studio (/trading?symbol=...) with that symbol pre-loaded.
 * The back button in Chart Studio appears automatically (cameFromLink pattern).
 *
 * Usage:
 *   <ChartButton symbol="RELIANCE.NS" />   ← stock (.NS stripped automatically)
 *   <ChartButton symbol="NIFTY BANK" />    ← sector index
 */
export default function ChartButton({ symbol, className = "" }: ChartButtonProps) {
  const [, navigate] = useLocation();
  const clean = symbol.replace(/\.(NS|BO)$/i, "").trim().toUpperCase();

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        navigate(`/trading?symbol=${encodeURIComponent(clean)}`);
      }}
      title={`Open ${clean} in Chart Studio`}
      className={`
        inline-flex items-center justify-center w-5 h-5 rounded flex-shrink-0
        opacity-60 hover:opacity-100
        text-indigo-400 dark:text-indigo-400 hover:text-indigo-600 dark:hover:text-indigo-300
        hover:bg-indigo-100 dark:hover:bg-indigo-900/40
        transition-all duration-150
        ${className}
      `}
    >
      <LineChart className="w-3.5 h-3.5" />
    </button>
  );
}
