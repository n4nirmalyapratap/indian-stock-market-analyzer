import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearch, useLocation, Link } from "wouter";
import { api } from "@/lib/api";
import { Search, TrendingUp, TrendingDown, AlertCircle, BarChart2, Activity, Users, ArrowLeft, Newspaper, Layers, PieChart, Calculator, GitBranch } from "lucide-react";
import ChartButton from "@/components/ChartButton";
import AIAnalystButton from "@/components/AIAnalystButton";
import StockFinancials from "@/components/financials/StockFinancials";
import TechnicalSummary from "@/components/technicals/TechnicalSummary";
import DataFreshness from "@/components/DataFreshness";
import { StockCombobox } from "@/components/StockCombobox";
import TickerNewsPanel from "@/components/TickerNewsPanel";
import { marketDataQueryOptions, pickMeta } from "@/lib/marketData";
import StockLogo from "@/components/StockLogo";
import TriFactorScoring from "@/components/TriFactorScoring";
import ShareholdingPattern from "@/components/stock/ShareholdingPattern";
import DCFView from "@/components/stock/DCFView";
import EventAttribution from "@/components/stock/EventAttribution";

const NIFTY100_QUICK = ["RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","ITC","SBIN","BHARTIARTL","KOTAKBANK","BAJFINANCE","AXISBANK","MARUTI","HCLTECH","WIPRO","TITAN","SUNPHARMA"];

export default function StockLookup() {
  const search = useSearch();
  const [, navigate] = useLocation();
  const [input, setInput] = useState("");
  const [symbol, setSymbol] = useState("");
  const [view, setView] = useState<"technicals" | "financials" | "news" | "scoring" | "shareholding" | "dcf" | "attribution">("technicals");
  // True only when ChartButton explicitly set the flag — cleared immediately so
  // coming back from Investor Council (or any other back-nav) never re-shows it.
  const cameFromLink = useRef((() => {
    const v = sessionStorage.getItem("_stockLookupRef") === "1";
    sessionStorage.removeItem("_stockLookupRef");
    return v;
  })());

  // Auto-search when ?symbol=XYZ is present in the URL (e.g. from Heatmap click or back-nav)
  useEffect(() => {
    const params = new URLSearchParams(search);
    const sym = (params.get("symbol") || "").toUpperCase().trim();
    if (sym && sym !== symbol) {
      setInput(sym);
      setSymbol(sym);
      setView("technicals");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const { data, isLoading, error } = useQuery({
    ...marketDataQueryOptions(["stock", symbol], () => api.stockDetail(symbol)),
    enabled: !!symbol,
  });

  // Company profile (what it does + canonical sector) — independent of the
  // quote so a slow first-time Yahoo profile fetch never blocks price/analysis.
  const { data: profile } = useQuery({
    queryKey: ["stock-profile", symbol],
    queryFn: () => api.stockProfile(symbol),
    enabled: !!symbol,
    staleTime: 24 * 60 * 60 * 1000,
  });

  // Push symbol into the URL so back-navigation always restores the looked-up stock
  function handleSearch(sym?: string) {
    const s = (sym || input).toUpperCase().trim();
    if (s) {
      navigate(`/stocks?symbol=${encodeURIComponent(s)}`, { replace: false });
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        {cameFromLink.current && (
          <button
            onClick={() => window.history.back()}
            title="Go back"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-white transition-colors flex-shrink-0"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </button>
        )}
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Stock Analysis</h1>
          <p className="text-sm text-gray-500">Enter any NSE symbol for technical and fundamental analysis</p>
        </div>
      </div>

      <div className="flex gap-2">
        <div className="flex-1">
          <StockCombobox
            value={input}
            onChange={setInput}
            onSelect={(s) => { setInput(s.symbol); handleSearch(s.symbol); }}
            onSubmit={() => handleSearch()}
            placeholder="Enter NSE symbol (e.g., RELIANCE) or company name"
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
              <div className="flex items-start gap-3">
                <StockLogo symbol={data.symbol} name={data.companyName} size={44} shape="rounded" className="flex-shrink-0 mt-0.5" />
                <div>
                <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
                  {data.companyName || data.symbol}
                  <ChartButton symbol={data.symbol} />
                </h2>
                <p className="text-sm text-gray-500">{data.symbol} • {profile?.sector || data.industry || data.sector || "NSE"}</p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-2xl font-bold text-gray-900">₹{data.lastPrice?.toLocaleString("en-IN", { minimumFractionDigits: 2 }) || "—"}</p>
                <p className={`text-sm font-medium flex items-center gap-1 justify-end ${(data.pChange || 0) >= 0 ? "text-green-600" : "text-red-500"}`}>
                  {(data.pChange || 0) >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                  {/* Coerce to Number — some providers return change/pChange as
                      strings, which would crash `.toFixed` ("…toFixed is not a function"). */}
                  {Number(data.pChange ?? 0) >= 0 ? "+" : ""}{Number(data.pChange ?? 0).toFixed(2)}% ({Number(data.change ?? 0) >= 0 ? "+" : ""}{Number(data.change ?? 0).toFixed(2)})
                </p>
              </div>
            </div>
            <p className="mt-3 text-sm text-gray-600 leading-relaxed">{data.insight}</p>

            {/* About — what the company does + its canonical sector (centralised
                classification, resolved & cached server-side). */}
            {profile && (profile.description || profile.sector) && (
              <div className="mt-3 rounded-lg bg-gray-50 dark:bg-gray-800/40 border border-gray-100 dark:border-white/5 p-3">
                <div className="flex flex-wrap items-center gap-1.5 mb-1.5">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">About</span>
                  {profile.sector && (
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-300">
                      <Layers className="w-3 h-3" /> {profile.sector}
                    </span>
                  )}
                  {profile.industry && profile.industry !== profile.sector && (
                    <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700/50 text-gray-600 dark:text-gray-300">
                      {profile.industry}
                    </span>
                  )}
                  {(profile as any).sub_sector && (
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-cyan-50 dark:bg-cyan-500/15 text-cyan-700 dark:text-cyan-300">
                      {(profile as any).sub_sector}
                    </span>
                  )}
                </div>
                {profile.description && (
                  <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed line-clamp-3">
                    {profile.description}
                  </p>
                )}
              </div>
            )}

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Link
                href={`/agents/${encodeURIComponent(data.symbol)}`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-gradient-to-r from-indigo-50 to-violet-50 hover:from-indigo-100 hover:to-violet-100 text-indigo-700 text-xs font-medium border border-indigo-200/60 transition"
              >
                <Users className="w-3.5 h-3.5" />
                Ask the Investor Council about {data.symbol}
              </Link>
              <AIAnalystButton symbol={data.symbol} />
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <DataFreshness meta={pickMeta(data)} refreshKeys={["stock", symbol]} />
              {/* History provenance pill — quote can be live NSE while
                  candles came off disk EOD; surface that distinction so
                  "EMA50 below price" reads honestly when the bars are stale. */}
              {pickMeta(data)?.historySource && pickMeta(data)?.historySource !== pickMeta(data)?.source && (
                <span className="text-xs px-2 py-1 rounded-full bg-slate-100 text-slate-600 border border-slate-200" title="Historical-bars source (used for EMA / RSI / MACD)">
                  History: {String(pickMeta(data)?.historySource)}
                  {pickMeta(data)?.historyEodDate ? ` · ${pickMeta(data)?.historyEodDate}` : ""}
                </span>
              )}
            </div>
          </div>

          {/* View toggle: Technicals | Financials | News */}
          <div className="w-full overflow-x-auto">
            <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1 w-fit min-w-max">
            <button
              onClick={() => setView("technicals")}
              data-testid="technicals-tab-btn"
              className={`flex items-center gap-1.5 px-3 sm:px-4 py-2 rounded-md text-sm font-medium transition-all whitespace-nowrap ${view === "technicals" ? "bg-white dark:bg-gray-700 text-indigo-700 dark:text-indigo-300 shadow-sm" : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"}`}
            >
              <Activity className="w-3.5 h-3.5 shrink-0" /> <span className="hidden sm:inline">Technicals</span>
            </button>
            <button
              onClick={() => setView("financials")}
              data-testid="financials-tab-btn"
              className={`flex items-center gap-1.5 px-3 sm:px-4 py-2 rounded-md text-sm font-medium transition-all whitespace-nowrap ${view === "financials" ? "bg-white dark:bg-gray-700 text-indigo-700 dark:text-indigo-300 shadow-sm" : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"}`}
            >
              <BarChart2 className="w-3.5 h-3.5 shrink-0" /> <span className="hidden sm:inline">Financials</span>
            </button>
            <button
              onClick={() => setView("news")}
              data-testid="news-tab-btn"
              className={`flex items-center gap-1.5 px-3 sm:px-4 py-2 rounded-md text-sm font-medium transition-all whitespace-nowrap ${view === "news" ? "bg-white dark:bg-gray-700 text-indigo-700 dark:text-indigo-300 shadow-sm" : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"}`}
            >
              <Newspaper className="w-3.5 h-3.5 shrink-0" /> <span className="hidden sm:inline">News</span>
            </button>
            <button
              onClick={() => setView("scoring")}
              className={`flex items-center gap-1.5 px-3 sm:px-4 py-2 rounded-md text-sm font-medium transition-all whitespace-nowrap ${view === "scoring" ? "bg-white dark:bg-gray-700 text-indigo-700 dark:text-indigo-300 shadow-sm" : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"}`}
            >
              <Layers className="w-3.5 h-3.5 shrink-0" /> <span className="hidden sm:inline">Scoring</span>
            </button>
            <button
              onClick={() => setView("shareholding")}
              data-testid="shareholding-tab-btn"
              className={`flex items-center gap-1.5 px-3 sm:px-4 py-2 rounded-md text-sm font-medium transition-all whitespace-nowrap ${view === "shareholding" ? "bg-white dark:bg-gray-700 text-indigo-700 dark:text-indigo-300 shadow-sm" : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"}`}
            >
              <PieChart className="w-3.5 h-3.5 shrink-0" /> <span className="hidden sm:inline">Shareholding</span>
            </button>
            <button
              onClick={() => setView("dcf")}
              className={`flex items-center gap-1.5 px-3 sm:px-4 py-2 rounded-md text-sm font-medium transition-all whitespace-nowrap ${view === "dcf" ? "bg-white dark:bg-gray-700 text-indigo-700 dark:text-indigo-300 shadow-sm" : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"}`}
            >
              <Calculator className="w-3.5 h-3.5 shrink-0" /> <span className="hidden sm:inline">DCF Value</span>
            </button>
            <button
              onClick={() => setView("attribution")}
              className={`flex items-center gap-1.5 px-3 sm:px-4 py-2 rounded-md text-sm font-medium transition-all whitespace-nowrap ${view === "attribution" ? "bg-white dark:bg-gray-700 text-indigo-700 dark:text-indigo-300 shadow-sm" : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"}`}
            >
              <GitBranch className="w-3.5 h-3.5 shrink-0" /> <span className="hidden sm:inline">Attribution</span>
            </button>
            </div>
          </div>

          {/* Technicals view — TradingView-style Indicators Summary */}
          {view === "technicals" && (
            <TechnicalSummary symbol={data.symbol} />
          )}

          {/* Financials view */}
          {view === "financials" && (
            <StockFinancials symbol={data.symbol} />
          )}

          {/* News view — per-stock news from yfinance + RSS + Tavily */}
          {view === "news" && (
            <TickerNewsPanel symbol={data.symbol} limit={15} />
          )}

          {/* Tri-Factor Composite Scoring */}
          {view === "scoring" && (
            <TriFactorScoring symbol={data.symbol} />
          )}

          {/* Shareholding pattern — quarterly Promoter / FII / DII / Public % */}
          {view === "shareholding" && (
            <ShareholdingPattern symbol={data.symbol} />
          )}

          {/* DCF Intrinsic Value */}
          {view === "dcf" && (
            <DCFView symbol={data.symbol} />
          )}

          {/* Event Attribution Timeline */}
          {view === "attribution" && (
            <EventAttribution
              symbol={data.symbol}
              companyName={data.companyName || data.symbol}
            />
          )}
        </div>
      )}

      {data?.error && (
        <div className="flex items-center gap-2 text-amber-600 bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm">
          <AlertCircle className="w-4 h-4" /> {(error as Error).message}
        </div>
      )}
    </div>
  );
}