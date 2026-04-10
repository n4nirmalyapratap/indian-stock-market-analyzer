import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Search, TrendingUp, TrendingDown, AlertCircle, Target, BarChart2 } from "lucide-react";
import ChartButton from "@/components/ChartButton";
import StockFinancials from "@/components/financials/StockFinancials";

const NIFTY100_QUICK = ["RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","ITC","SBIN","BHARTIARTL","KOTAKBANK","BAJFINANCE","AXISBANK","MARUTI","HCLTECH","WIPRO","TITAN","SUNPHARMA"];

function Badge({ label, type }: { label?: string; type: "bull" | "bear" | "neutral" }) {
  const cls = type === "bull" ? "bg-green-100 text-green-700" : type === "bear" ? "bg-red-100 text-red-700" : "bg-gray-100 text-gray-600";
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cls}`}>{label ?? "—"}</span>;
}

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

  const ta = data?.technicalAnalysis;
  const er = data?.entryRecommendation;

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
              className={`flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-all ${view === "technicals" ? "bg-white text-indigo-700 shadow-sm" : "text-gray-500 hover:text-gray-700"}`}
            >
              <TrendingUp className="w-3.5 h-3.5" /> Technicals
            </button>
            <button
              onClick={() => setView("financials")}
              data-testid="financials-tab-btn"
              className={`flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-all ${view === "financials" ? "bg-white text-indigo-700 shadow-sm" : "text-gray-500 hover:text-gray-700"}`}
            >
              <BarChart2 className="w-3.5 h-3.5" /> Financials
            </button>
          </div>

          {/* Technicals view */}
          {view === "technicals" && ta && (
            <div className="grid md:grid-cols-2 gap-4">
              <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
                <h3 className="font-semibold text-gray-800 mb-3">Trend & EMA</h3>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Trend</span>
                    <Badge label={ta.trend} type={ta.trend?.includes("BULL") ? "bull" : ta.trend?.includes("BEAR") ? "bear" : "neutral"} />
                  </div>
                  <div className="flex justify-between"><span className="text-gray-500">EMA 9</span><span className="font-medium">₹{ta.ema?.ema9?.toFixed(2)}</span></div>
                  <div className="flex justify-between"><span className="text-gray-500">EMA 21</span><span className="font-medium">₹{ta.ema?.ema21?.toFixed(2)}</span></div>
                  <div className="flex justify-between"><span className="text-gray-500">EMA 50</span><span className="font-medium">₹{ta.ema?.ema50?.toFixed(2)}</span></div>
                  <div className="flex justify-between"><span className="text-gray-500">EMA 200</span><span className="font-medium">₹{ta.ema?.ema200?.toFixed(2)}</span></div>
                </div>
              </div>

              <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
                <h3 className="font-semibold text-gray-800 mb-3">Oscillators</h3>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between items-center">
                    <span className="text-gray-500">RSI (14)</span>
                    <div className="flex items-center gap-2">
                      <div className="w-24 h-2 bg-gray-100 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${(ta.rsi ?? 50) > 70 ? "bg-red-400" : (ta.rsi ?? 50) < 30 ? "bg-green-400" : "bg-blue-400"}`} style={{ width: `${Math.min(ta.rsi ?? 0, 100)}%` }} />
                      </div>
                      <span className="font-medium">{ta.rsi?.toFixed(1)}</span>
                      <Badge label={ta.rsiZone} type={ta.rsiZone === "OVERSOLD" ? "bull" : ta.rsiZone === "OVERBOUGHT" ? "bear" : "neutral"} />
                    </div>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">MACD</span>
                    <Badge label={ta.macd?.crossover} type={ta.macd?.crossover === "BULLISH" ? "bull" : "bear"} />
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">MACD Histogram</span>
                    <span className={`font-medium ${(ta.macd?.histogram || 0) >= 0 ? "text-green-600" : "text-red-500"}`}>{ta.macd?.histogram?.toFixed(3)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">BB Position</span>
                    <Badge label={ta.bollingerBands?.position} type={ta.bollingerBands?.position === "BELOW_LOWER" ? "bull" : ta.bollingerBands?.position === "ABOVE_UPPER" ? "bear" : "neutral"} />
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">ATR</span>
                    <span className="font-medium">{ta.atr?.toFixed(2)}</span>
                  </div>
                </div>
              </div>

              <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 md:col-span-2">
                <h3 className="font-semibold text-gray-800 mb-3">Support & Resistance</h3>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-xs font-medium text-red-600 uppercase mb-2">Resistances</p>
                    {ta.resistances?.map((r: number, i: number) => (
                      <div key={i} className={`flex justify-between py-1 border-b border-gray-50 ${i === 0 && ta.nearestResistance === r ? "font-semibold text-red-600" : "text-gray-700"}`}>
                        <span>R{i + 1}</span><span>₹{r?.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                  <div>
                    <p className="text-xs font-medium text-green-600 uppercase mb-2">Supports</p>
                    {ta.supports?.map((s: number, i: number) => (
                      <div key={i} className={`flex justify-between py-1 border-b border-gray-50 ${ta.nearestSupport === s ? "font-semibold text-green-600" : "text-gray-700"}`}>
                        <span>S{i + 1}</span><span>₹{s?.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Entry signal */}
          {view === "technicals" && er && (
            <div className={`rounded-xl border p-5 ${er.signal === "BULLISH" ? "bg-green-50 border-green-200" : er.signal === "BEARISH" ? "bg-red-50 border-red-200" : "bg-gray-50 border-gray-200"}`}>
              <div className="flex items-start gap-3">
                <Target className={`w-5 h-5 mt-0.5 ${er.signal === "BULLISH" ? "text-green-600" : er.signal === "BEARISH" ? "text-red-600" : "text-gray-500"}`} />
                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap mb-2">
                    <h3 className="font-semibold text-gray-900">Entry Signal: {er.entryCall?.replace("_", " ")}</h3>
                    <Badge label={er.signal} type={er.signal === "BULLISH" ? "bull" : er.signal === "BEARISH" ? "bear" : "neutral"} />
                    <span className="text-xs text-gray-500">Confidence: {er.confidence}</span>
                  </div>
                  <p className="text-sm text-gray-700 mb-3">{er.summary}</p>
                  <div className="flex flex-wrap gap-4 text-sm">
                    {er.targetPrice && <div><span className="text-gray-500">Target: </span><span className="font-medium text-green-700">₹{er.targetPrice?.toFixed(2)}</span></div>}
                    {er.stopLoss && <div><span className="text-gray-500">Stop Loss: </span><span className="font-medium text-red-600">₹{er.stopLoss?.toFixed(2)}</span></div>}
                    {er.riskReward && <div><span className="text-gray-500">R:R Ratio: </span><span className="font-medium">{er.riskReward}:1</span></div>}
                  </div>
                  <div className="mt-2 flex gap-4 text-xs text-gray-500">
                    <span>🟢 Bullish factors: {er.bullishFactors}</span>
                    <span>🔴 Bearish factors: {er.bearishFactors}</span>
                  </div>
                </div>
              </div>
            </div>
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
