import { useLocation } from "wouter";
import { BarChart2 } from "lucide-react";

interface ChartButtonProps {
  symbol: string;
  className?: string;
}

export default function ChartButton({ symbol, className = "" }: ChartButtonProps) {
  const [, navigate] = useLocation();
  return (
    <button
      onClick={(e) => { e.stopPropagation(); navigate(`/chart/${encodeURIComponent(symbol.toUpperCase())}`); }}
      title={`View ${symbol} chart`}
      className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-indigo-400 hover:text-indigo-600 hover:bg-indigo-50 transition flex-shrink-0 ${className}`}
    >
      <BarChart2 className="w-3.5 h-3.5" />
    </button>
  );
}
