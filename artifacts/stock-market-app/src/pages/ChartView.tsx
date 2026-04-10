import { useEffect, useRef, useCallback } from "react";
import { useParams, useLocation } from "wouter";
import { ArrowLeft, ExternalLink } from "lucide-react";

declare global {
  interface Window { TradingView: any; }
}

function toTVSymbol(raw: string): string {
  const sym = raw.toUpperCase();
  const indexMap: Record<string, string> = {
    "NIFTY":       "NSE:NIFTY50",
    "NIFTY50":     "NSE:NIFTY50",
    "BANKNIFTY":   "NSE:BANKNIFTY",
    "FINNIFTY":    "NSE:FINNIFTY",
    "MIDCPNIFTY":  "NSE:MIDCPNIFTY",
    "NIFTYMIDCAP": "NSE:NIFTYMIDCAP100",
    "SENSEX":      "BSE:SENSEX",
    "BANKEX":      "BSE:BANKEX",
  };
  return indexMap[sym] ?? `NSE:${sym}`;
}

export default function ChartView() {
  const { symbol } = useParams<{ symbol: string }>();
  const [, navigate] = useLocation();
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetRef    = useRef<any>(null);
  const scriptRef    = useRef<HTMLScriptElement | null>(null);

  const isDark = () => document.documentElement.classList.contains("dark");

  const initWidget = useCallback(() => {
    if (!containerRef.current || !symbol) return;

    const containerId = "tv_chart_advanced";
    containerRef.current.id = containerId;

    if (widgetRef.current) {
      try { widgetRef.current.remove?.(); } catch {}
      widgetRef.current = null;
    }
    containerRef.current.innerHTML = "";

    widgetRef.current = new window.TradingView.widget({
      autosize:              true,
      symbol:                toTVSymbol(symbol),
      interval:              "D",
      timezone:              "Asia/Kolkata",
      theme:                 isDark() ? "dark" : "light",
      style:                 "1",
      locale:                "en",
      enable_publishing:     false,
      allow_symbol_change:   true,
      hide_top_toolbar:      false,
      hide_side_toolbar:     false,
      withdateranges:        true,
      details:               true,
      hotlist:               true,
      calendar:              true,
      show_popup_button:     true,
      popup_width:           "1000",
      popup_height:          "650",
      studies: [
        "STD;MACD",
        "STD;RSI",
        "STD;Volume",
      ],
      container_id: containerId,
    });
  }, [symbol]);

  useEffect(() => {
    if (window.TradingView) {
      initWidget();
      return;
    }

    const script = document.createElement("script");
    script.src   = "https://s3.tradingview.com/tv.js";
    script.async = true;
    script.onload = () => initWidget();
    document.head.appendChild(script);
    scriptRef.current = script;

    return () => {
      if (scriptRef.current && document.head.contains(scriptRef.current)) {
        document.head.removeChild(scriptRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (window.TradingView) initWidget();
  }, [symbol]);

  return (
    <div className="flex flex-col h-full bg-[#131722]">
      {/* Minimal header */}
      <div className="flex items-center gap-3 px-4 py-2.5 bg-[#1e222d] border-b border-[#2a2e39] flex-shrink-0">
        <button
          onClick={() => navigate("/")}
          className="text-gray-400 hover:text-white transition-colors"
          title="Back"
        >
          <ArrowLeft size={18} />
        </button>
        <div className="flex items-baseline gap-2">
          <span className="font-bold text-white text-sm tracking-wide">
            {symbol?.toUpperCase()}
          </span>
          <span className="text-xs text-gray-500">
            {toTVSymbol(symbol ?? "")}
          </span>
        </div>
        <a
          href={`https://www.tradingview.com/chart/?symbol=${toTVSymbol(symbol ?? "")}`}
          target="_blank"
          rel="noreferrer"
          className="ml-auto text-gray-500 hover:text-gray-300 transition-colors flex items-center gap-1 text-xs"
          title="Open in TradingView"
        >
          <ExternalLink size={13} />
          TradingView
        </a>
      </div>

      {/* TradingView Advanced Chart */}
      <div className="flex-1 min-h-0 relative">
        <div ref={containerRef} className="absolute inset-0 w-full h-full" />
      </div>
    </div>
  );
}
