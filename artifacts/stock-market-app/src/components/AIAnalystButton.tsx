import { Link } from "wouter";
import { Microscope } from "lucide-react";

export function AIAnalystButton({ symbol, compact = false }: { symbol: string; compact?: boolean }) {
  if (!symbol) return null;
  if (compact) {
    return (
      <Link href={`/ai-analyst/${encodeURIComponent(symbol)}`}
            title="Run Deep AI Analysis"
            className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-md bg-indigo-50 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-100 dark:hover:bg-indigo-500/25">
        <Microscope className="w-3.5 h-3.5" />
        Deep AI
      </Link>
    );
  }
  return (
    <Link href={`/ai-analyst/${encodeURIComponent(symbol)}`}
          className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white">
      <Microscope className="w-4 h-4" />
      Run Deep AI Analysis
    </Link>
  );
}

export default AIAnalystButton;
