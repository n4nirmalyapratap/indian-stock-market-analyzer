import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Search, TrendingUp, TrendingDown, AlertCircle, BarChart2, Activity } from "lucide-react";
import ChartButton from "@/components/ChartButton";
import StockFinancials from "@/components/financials/StockFinancials";
import TechnicalSummary from "@/components/technicals/TechnicalSummary";

const NIFTY100_QUICK = ["RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","ITC","SBIN","BHARTIARTL","KOTAKBANK","BAJFINANCE","AXISBANK","MARUTI","HCLTECH","WIPRO","TITAN","SUNPHARMA"];

export default function StockLookup() {
  const [input, setInput] = useState("");
  const [symbol, setSymbol] = useState("");
  const [view, setView] = useState<"technicals" | "financials">("technicals");

  const { data, isLoading, error } = useQuery({
    queryKey: ["stock", symbol],
    queryFn: () => api.stockDetail(symbol),
    enabled: !!symbol,
    staleTime: 5 * 60 * 1000,
  });

  function handleSearch(sym?: string) {
    const s = (sym || input).toUpperCase().trim();
    if (s) {
      setSymbol(s);
      setView("technicals");
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Stock Analysis</h1>
        <p className="text-sm text-gray-500">Enter any NSE symbol for technical and fundamental analysis</p>
      </div>

      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleSearch()}
            placeholder="Enter NSE symbol (e.g., RELIANCE)"
            className="w-full pl-9 pr-4 py-2.5 rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-300 text-sm"
          />
        </div>
        <button
          onClick={() => handleSearch()}
          className="px-4 py-2.5 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition"
        >
          Analyze
        </button>
      </div>

      <div className="flex flex-wrap gap-2">
        {NIFTY100_QUICK.map(s => (
          <button
            key={s}
            onClick={() => { setInput(s); handleSearch(s); }}
            className={`text-xs px-3 py-1.5 rounded-full border transition ${symbol === s ? "bg-indigo-600 text-white border-indigo-600" : "bg-white text-gray-600 border-gray-200 hover:border-indigo-300"}`}
          >
            {s}
          </button>
        ))}
      </div>

      {isLoading && (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => <div key={i} className="h-24 bg-gray-100 animate-pulse rounded-xl" />)}
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 text-red-600 bg-red-50 border border-red-200 rounded-lg p-3 text-sm">
          <AlertCircle className="w-4 h-4" /> {(error as Error).message}
        </div>
      )}

      {data && !data.error && (
        <div className="space-y-4">
          {/* Stock header */}
          <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
                  {data.companyName || data.symbol}
                  <ChartButton symbol={data.symbol} />
                </h2>
                <p className="text-sm text-gray-500">{data.symbol} • {data.industry || data.sector || "NSE"}</p>
              </div>
              <div className="text-right">
                <p className="text-2xl font-bold text-gray-900">₹{data.lastPrice?.toLocaleString("en-IN", { minimumFractionDigits: 2 }) || "—"}</p>
                <p className={`text-sm font-medium flex items-center gap-1 justify-end ${(data.pChange || 0) >= 0 ? "text-green-600" : "text-red-500"}`}>
                  {(data.pChange || 0) >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                  {data.pChange >= 0 ? "+" : ""}{data.pChange?.toFixed(2) || "0"}% ({data.change >= 0 ? "+" : ""}{data.change?.toFixed(2) || "0"})
                </p>
              </div>
            </div>
            <p className="mt-3 text-sm text-gray-600 leading-relaxed">{data.insight}</p>
          </div>

          {/* View toggle: Technicals | Financials */}
          <div className="flex gap-1 bg-gray-100 rounded-lg p-1 w-fit">
            <button
              onClick={() => setView("technicals")}
              data-testid="technicals-tab-btn"
              className={`flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-all ${view === "technicals" ? "bg-white text-indigo-700 shadow-sm" : "text-gray-500 hover:text-gray-700"}`}
            >
              <Activity className="w-3.5 h-3.5" /> Technicals
            </button>
            <button
              onClick={() => setView("financials")}
              data-testid="financials-tab-btn"
              className={`flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-all ${view === "financials" ? "bg-white text-indigo-700 shadow-sm" : "text-gray-500 hover:text-gray-700"}`}
            >
              <BarChart2 className="w-3.5 h-3.5" /> Financials
            </button>
          </div>

          {/* Technicals view — TradingView-style Indicators Summary */}
          {view === "technicals" && (
            <TechnicalSummary symbol={data.symbol} />
          )}

          {/* Financials view */}
          {view === "financials" && (
            <StockFinancials symbol={data.symbol} />
          )}
        </div>
      )}

      {data?.error && (
        <div className="flex items-center gap-2 text-amber-600 bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm">
          <AlertCircle className="w-4 h-4" /> {data.error}
        </div>
      )}
    </div>
  );
}
