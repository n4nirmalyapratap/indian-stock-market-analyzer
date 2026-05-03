import { useState, useEffect } from "react";
import { useSearch, Link } from "wouter";
import { Brain, Loader2, AlertCircle, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { useCustomAuth } from "@/context/CustomAuthContext";

type Verdict = "BUY" | "HOLD" | "SELL";

interface Report {
  ticker: string;
  name: string;
  verdict: Verdict;
  confidence: string;
  headline: string;
  priceTarget: string;
  horizon: string;
  keyRisks: string[];
  analysts: { fundamentals: string; news: string; technicals: string; macro: string };
  modelsUsed: string[];
  sourcesUsed: string[];
  disclaimer: string;
  error?: string;
}

const COLOUR: Record<Verdict, string> = {
  BUY:  "border-green-300 dark:border-green-800 bg-green-50/40 dark:bg-green-900/10",
  HOLD: "border-amber-300 dark:border-amber-800 bg-amber-50/40 dark:bg-amber-900/10",
  SELL: "border-red-300   dark:border-red-800   bg-red-50/40   dark:bg-red-900/10",
};
const ICON: Record<Verdict, any> = { BUY: TrendingUp, HOLD: Minus, SELL: TrendingDown };

function ReportCard({ r }: { r: Report | null }) {
  if (!r) return null;
  if (r.error) {
    return (
      <div className="border border-red-200 dark:border-red-800 rounded-xl p-4 bg-red-50 dark:bg-red-900/20">
        <p className="text-sm font-medium text-red-700 dark:text-red-300">
          {r.ticker}: {r.error}
        </p>
      </div>
    );
  }
  const Icon = ICON[r.verdict] || Minus;
  return (
    <div className={`border rounded-xl p-4 ${COLOUR[r.verdict]}`}>
      <div className="flex items-center gap-3 mb-3">
        <Icon className="w-6 h-6" />
        <div className="flex-1">
          <p className="font-bold text-gray-900 dark:text-white">{r.name}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">{r.ticker} · {r.confidence} confidence · {r.horizon}</p>
        </div>
        <span className="text-xl font-bold">{r.verdict}</span>
      </div>
      <p className="text-sm text-gray-700 dark:text-gray-200 leading-relaxed mb-3">{r.headline}</p>
      {r.priceTarget && r.priceTarget !== "N/A" && (
        <p className="text-xs text-gray-600 dark:text-gray-300"><span className="font-semibold">Target:</span> {r.priceTarget}</p>
      )}
      <div className="mt-3 space-y-2 text-xs text-gray-600 dark:text-gray-300">
        <p><span className="font-semibold">Fundamentals:</span> {r.analysts.fundamentals}</p>
        <p><span className="font-semibold">Charts:</span> {r.analysts.technicals}</p>
      </div>
    </div>
  );
}


export default function AIAnalystCompare() {
  const search = useSearch();
  const params = new URLSearchParams(search);
  const [a, setA] = useState((params.get("a") || "").toUpperCase());
  const [b, setB] = useState((params.get("b") || "").toUpperCase());
  const { token } = useCustomAuth();
  const [running, setRunning] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [data,  setData]      = useState<{ a: Report; b: Report } | null>(null);

  useEffect(() => {
    if (a && b && !running && !data) void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const run = async () => {
    if (!a.trim() || !b.trim()) { setError("Pick two tickers"); return; }
    if (!token) { setError("Please sign in"); return; }
    setError(null); setData(null); setRunning(true);
    try {
      const res = await fetch(`/api/ai-analyst/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error((await res.text()) || `HTTP ${res.status}`);
      setData(await res.json());
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Brain className="w-6 h-6 text-indigo-600 dark:text-indigo-400" />
        <h1 className="text-xl font-bold text-gray-900 dark:text-white">Compare two stocks</h1>
        <Link href={`/ai-analyst/${a || ""}`}
              className="ml-auto text-xs text-indigo-600 dark:text-indigo-400 hover:underline">
          ← Single-stock view
        </Link>
      </div>

      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded-xl p-4 flex flex-wrap items-center gap-2">
        <input value={a} onChange={e => setA(e.target.value.toUpperCase())}
               placeholder="Ticker A (e.g. RELIANCE)"
               className="flex-1 min-w-[160px] px-3 py-2 text-sm bg-gray-50 dark:bg-gray-950 border border-gray-200 dark:border-white/10 rounded-lg" />
        <span className="text-gray-400">vs</span>
        <input value={b} onChange={e => setB(e.target.value.toUpperCase())}
               placeholder="Ticker B (e.g. TCS)"
               className="flex-1 min-w-[160px] px-3 py-2 text-sm bg-gray-50 dark:bg-gray-950 border border-gray-200 dark:border-white/10 rounded-lg" />
        <button onClick={() => run()} disabled={running}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg flex items-center gap-2">
          {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Brain className="w-4 h-4" />}
          {running ? "Analysing…" : "Compare"}
        </button>
      </div>

      {running && (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Running two parallel multi-agent analyses — this can take 30–90 seconds…
        </p>
      )}

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 flex items-start gap-2">
          <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400" />
          <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
        </div>
      )}

      {data && (
        <div className="grid md:grid-cols-2 gap-4">
          <ReportCard r={data.a} />
          <ReportCard r={data.b} />
        </div>
      )}

      {data && (
        <div className="bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-900/30 rounded-lg p-4 text-xs text-amber-900 dark:text-amber-200">
          AI-generated research only — not investment advice. Outputs may be inaccurate.
          Consult a SEBI-registered advisor before acting.
        </div>
      )}
    </div>
  );
}
