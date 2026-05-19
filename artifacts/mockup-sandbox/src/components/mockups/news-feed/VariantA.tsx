import { useState } from "react";
import { TrendingUp, TrendingDown, Minus, ExternalLink, Radio, RefreshCw, Search, Zap } from "lucide-react";

const MOCK_ARTICLES = [
  { id: "1", title: "SEBI tightens F&O margin norms — brokers flag liquidity crunch risk", source: "ET", sourceColor: "#f59e0b", sentiment: "bearish", category: "market", time: "4m ago", tickers: ["ZERODHA", "ANGELONE"] },
  { id: "2", title: "Reliance Industries Q4 profit beats estimates at ₹19,407 Cr; Jio, Retail drive growth", source: "Mint", sourceColor: "#6366f1", sentiment: "bullish", category: "corporate", time: "12m ago", tickers: ["RELIANCE"] },
  { id: "3", title: "RBI holds repo at 6.5% for eighth consecutive meet; GDP outlook revised upward", source: "MC", sourceColor: "#22c55e", sentiment: "neutral", category: "market", time: "28m ago", tickers: [] },
  { id: "4", title: "NSE derivatives turnover hits ₹4.2 lakh Cr — options volume 3× year-ago levels", source: "ET", sourceColor: "#f59e0b", sentiment: "bullish", category: "market", time: "41m ago", tickers: ["NIFTY50"] },
  { id: "5", title: "Adani Green surges 7% as MSCI index inclusion boosts foreign inflows", source: "Mint", sourceColor: "#6366f1", sentiment: "bullish", category: "corporate", time: "1h ago", tickers: ["ADANIGREEN"] },
  { id: "6", title: "FII outflows persist for fifth session; DII buying provides support around 22,400", source: "MC", sourceColor: "#22c55e", sentiment: "bearish", category: "market", time: "1h ago", tickers: [] },
  { id: "7", title: "Infosys raises FY26 revenue guidance to 4.5–7%; deal wins at all-time high", source: "ET", sourceColor: "#f59e0b", sentiment: "bullish", category: "corporate", time: "2h ago", tickers: ["INFY"] },
  { id: "8", title: "Crude oil slips below $79; Brent weakness eases inflation pressure on India", source: "Mint", sourceColor: "#6366f1", sentiment: "bullish", category: "general", time: "2h ago", tickers: [] },
];

const STATS = { total: 214, bullish: 89, bearish: 61, neutral: 64 };

const SENT = {
  bullish: { label: "BULL", color: "#22c55e", bg: "rgba(34,197,94,0.12)", icon: <TrendingUp className="w-3 h-3" /> },
  bearish: { label: "BEAR", color: "#ef4444", bg: "rgba(239,68,68,0.12)", icon: <TrendingDown className="w-3 h-3" /> },
  neutral: { label: "NEUT", color: "#64748b", bg: "rgba(100,116,139,0.12)", icon: <Minus className="w-3 h-3" /> },
};

export function VariantA() {
  const [filter, setFilter] = useState<"all" | "bullish" | "bearish">("all");
  const [search, setSearch] = useState("");

  const filtered = MOCK_ARTICLES.filter(a => {
    if (filter !== "all" && a.sentiment !== filter) return false;
    if (search && !a.title.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const bPct = Math.round((STATS.bullish / STATS.total) * 100);
  const rPct = Math.round((STATS.bearish / STATS.total) * 100);

  return (
    <div className="min-h-screen" style={{ background: "#060b17", fontFamily: "'JetBrains Mono', 'Fira Mono', monospace" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@400;500;600;700;800&display=swap');
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
        @keyframes scan { 0%{transform:translateY(-100%)} 100%{transform:translateY(100vh)} }
        @keyframes ticker { 0%{transform:translateX(0)} 100%{transform:translateX(-50%)} }
        .scanline { animation: scan 8s linear infinite; }
        .ticker-text { animation: ticker 40s linear infinite; }
        .cursor { animation: blink 1.2s step-end infinite; }
      `}</style>

      {/* Scanline overlay */}
      <div className="fixed inset-0 pointer-events-none z-50" style={{ background: "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,255,100,0.015) 2px, rgba(0,255,100,0.015) 4px)" }} />

      {/* Header */}
      <div className="border-b px-6 py-4" style={{ borderColor: "#0f2a1a", background: "#060b17" }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-green-400" style={{ boxShadow: "0 0 8px #22c55e" }} />
              <span className="text-xs font-bold tracking-[0.2em] uppercase" style={{ color: "#22c55e" }}>NIFTYNODE</span>
            </div>
            <div className="h-4 w-px" style={{ background: "#0f2a1a" }} />
            <span className="text-xs tracking-widest" style={{ color: "#1d4e2a" }}>MARKET_NEWS_TERMINAL v2.1</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs" style={{ color: "#1d4e2a" }}>SESSION</span>
            <span className="text-xs font-bold" style={{ color: "#22c55e" }}>ACTIVE<span className="cursor ml-1">_</span></span>
            <div className="text-xs px-2 py-1 rounded" style={{ background: "#0a1f12", color: "#22c55e", border: "1px solid #0f3319" }}>
              IST 14:32:07
            </div>
          </div>
        </div>

        {/* Ticker */}
        <div className="mt-3 overflow-hidden rounded" style={{ background: "#02090e", border: "1px solid #0f3319" }}>
          <div className="flex items-center gap-3 py-1.5 px-3">
            <span className="text-xs font-bold shrink-0" style={{ color: "#22c55e" }}>LIVE&gt;</span>
            <div className="overflow-hidden flex-1">
              <div className="ticker-text whitespace-nowrap text-xs" style={{ color: "#4ade80", display: "inline-block" }}>
                {MOCK_ARTICLES.map(a => a.title).join("   ///   ")}&nbsp;&nbsp;&nbsp;&nbsp;{MOCK_ARTICLES.map(a => a.title).join("   ///   ")}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="px-6 py-4 space-y-4">
        {/* Stats bar */}
        <div className="grid grid-cols-4 gap-3">
          {[
            { label: "TOTAL_ITEMS", val: STATS.total, color: "#22c55e" },
            { label: "BULL_SIGNALS", val: STATS.bullish, color: "#4ade80" },
            { label: "BEAR_SIGNALS", val: STATS.bearish, color: "#ef4444" },
            { label: "NEUTRAL_ITEMS", val: STATS.neutral, color: "#64748b" },
          ].map(s => (
            <div key={s.label} className="rounded px-4 py-3" style={{ background: "#080e18", border: "1px solid #0e2017" }}>
              <div className="text-[9px] tracking-widest mb-1" style={{ color: "#1d4e2a" }}>{s.label}</div>
              <div className="text-2xl font-bold" style={{ color: s.color, textShadow: `0 0 20px ${s.color}40` }}>{s.val}</div>
            </div>
          ))}
        </div>

        {/* Mood bar */}
        <div className="rounded px-4 py-3" style={{ background: "#080e18", border: "1px solid #0e2017" }}>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Radio className="w-3.5 h-3.5" style={{ color: "#22c55e" }} />
              <span className="text-xs tracking-widest" style={{ color: "#22c55e" }}>MARKET_MOOD_SENSOR</span>
            </div>
            <span className="text-xs font-bold px-2 py-0.5 rounded" style={{ background: "rgba(34,197,94,0.1)", color: "#22c55e", border: "1px solid rgba(34,197,94,0.2)" }}>
              ▲ BULLISH {bPct}%
            </span>
          </div>
          <div className="h-2 rounded-full overflow-hidden flex" style={{ background: "#0a1510" }}>
            <div style={{ width: `${bPct}%`, background: "linear-gradient(90deg, #14532d, #22c55e)", transition: "width 1s" }} />
            <div style={{ width: `${100 - bPct - rPct}%`, background: "#1e293b" }} />
            <div style={{ width: `${rPct}%`, background: "linear-gradient(90deg, #ef4444, #7f1d1d)", transition: "width 1s" }} />
          </div>
          <div className="flex justify-between mt-1.5 text-[10px]" style={{ color: "#1d4e2a" }}>
            <span>■ BULL {bPct}%</span><span>■ NEUT {100 - bPct - rPct}%</span><span>■ BEAR {rPct}%</span>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5" style={{ color: "#1d4e2a" }} />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="SEARCH_ARTICLES..."
              className="w-full pl-9 pr-4 py-2 rounded text-xs outline-none"
              style={{ background: "#080e18", border: "1px solid #0e2017", color: "#4ade80", fontFamily: "inherit" }}
            />
          </div>
          {(["all", "bullish", "bearish"] as const).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className="px-4 py-2 rounded text-[10px] tracking-widest transition-all"
              style={{
                background: filter === f ? (f === "bullish" ? "rgba(34,197,94,0.15)" : f === "bearish" ? "rgba(239,68,68,0.15)" : "rgba(34,197,94,0.08)") : "transparent",
                color: filter === f ? (f === "bullish" ? "#22c55e" : f === "bearish" ? "#ef4444" : "#22c55e") : "#1d4e2a",
                border: `1px solid ${filter === f ? (f === "bullish" ? "rgba(34,197,94,0.3)" : f === "bearish" ? "rgba(239,68,68,0.3)" : "rgba(34,197,94,0.2)") : "#0e2017"}`,
                fontFamily: "inherit",
              }}
            >
              {f.toUpperCase()}
            </button>
          ))}
          <button className="flex items-center gap-1.5 px-3 py-2 rounded text-[10px] tracking-widest" style={{ background: "#080e18", color: "#22c55e", border: "1px solid #0e2017", fontFamily: "inherit" }}>
            <RefreshCw className="w-3 h-3" /> REFRESH
          </button>
        </div>

        {/* News list */}
        <div className="space-y-1.5">
          {filtered.map((article, i) => {
            const s = SENT[article.sentiment as keyof typeof SENT];
            return (
              <div
                key={article.id}
                className="group rounded transition-all duration-150"
                style={{
                  background: "#080e18",
                  border: "1px solid #0e2017",
                  borderLeft: `3px solid ${s.color}`,
                }}
              >
                <div className="px-4 py-3 flex items-start gap-4">
                  {/* Line number */}
                  <span className="text-[10px] shrink-0 mt-0.5 w-6 text-right" style={{ color: "#1d4e2a" }}>{String(i + 1).padStart(2, "0")}</span>

                  {/* Source badge */}
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded shrink-0" style={{ background: article.sourceColor + "20", color: article.sourceColor, border: `1px solid ${article.sourceColor}30` }}>
                    {article.source}
                  </span>

                  {/* Title */}
                  <p className="flex-1 text-sm leading-snug" style={{ color: "#d1fae5" }}>{article.title}</p>

                  {/* Right meta */}
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded" style={{ background: s.bg, color: s.color, border: `1px solid ${s.color}30` }}>
                      {s.icon}{s.label}
                    </span>
                    <span className="text-[10px]" style={{ color: "#1d4e2a" }}>{article.time}</span>
                    <a href="#" className="opacity-0 group-hover:opacity-100 transition-opacity" style={{ color: "#22c55e" }}>
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  </div>
                </div>

                {/* Ticker chips */}
                {article.tickers.length > 0 && (
                  <div className="px-4 pb-2 flex gap-1.5 pl-16">
                    {article.tickers.map(t => (
                      <span key={t} className="text-[10px] font-bold px-2 py-0.5 rounded" style={{ background: "rgba(34,197,94,0.08)", color: "#22c55e", border: "1px solid rgba(34,197,94,0.15)", fontFamily: "inherit" }}>
                        ${t}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between py-2 border-t" style={{ borderColor: "#0e2017" }}>
          <div className="flex items-center gap-2">
            <Zap className="w-3 h-3" style={{ color: "#22c55e" }} />
            <span className="text-[10px] tracking-widest" style={{ color: "#1d4e2a" }}>SOURCES: ET · LIVEMINT · MONEYCONTROL · NSE</span>
          </div>
          <span className="text-[10px]" style={{ color: "#1d4e2a" }}>NEXT_REFRESH: 07:23<span className="cursor ml-1">_</span></span>
        </div>
      </div>
    </div>
  );
}
