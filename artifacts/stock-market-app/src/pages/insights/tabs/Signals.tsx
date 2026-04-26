import { Link } from "wouter";
import { PageHeader, Card } from "../_shared";
import { Activity, Scan, Filter, Brain } from "lucide-react";

export default function Signals() {
  return (
    <div>
      <PageHeader title="Signals" subtitle="Technical, pattern and AI-driven signals available across the app" />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Link href="/patterns">
          <Card className="p-5 cursor-pointer hover:border-indigo-300 dark:hover:border-indigo-500 transition">
            <Scan className="w-7 h-7 text-indigo-500 mb-3" />
            <h3 className="font-semibold text-gray-900 dark:text-white">Chart Patterns</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Head &amp; Shoulders, Flags, Triangles, Cup &amp; Handle scanned across the universe.</p>
          </Card>
        </Link>
        <Link href="/scanners">
          <Card className="p-5 cursor-pointer hover:border-indigo-300 dark:hover:border-indigo-500 transition">
            <Filter className="w-7 h-7 text-indigo-500 mb-3" />
            <h3 className="font-semibold text-gray-900 dark:text-white">Custom Scanners</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Build your own filter (RSI, MACD, breakouts, etc.) and run on demand.</p>
          </Card>
        </Link>
        <Link href="/hydra">
          <Card className="p-5 cursor-pointer hover:border-indigo-300 dark:hover:border-indigo-500 transition">
            <Brain className="w-7 h-7 text-indigo-500 mb-3" />
            <h3 className="font-semibold text-gray-900 dark:text-white">AI Analyzer (Hydra)</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Forecasts, pair trades, VaR — algorithmic signal stack.</p>
          </Card>
        </Link>
        <Link href="/sentiment">
          <Card className="p-5 cursor-pointer hover:border-indigo-300 dark:hover:border-indigo-500 transition">
            <Activity className="w-7 h-7 text-indigo-500 mb-3" />
            <h3 className="font-semibold text-gray-900 dark:text-white">Market Sentiment</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Composite score from news NLP, price action, India VIX.</p>
          </Card>
        </Link>
      </div>
    </div>
  );
}
