import { useState } from "react";
import { TrendingUp, TrendingDown, Minus, ExternalLink, RefreshCw, Search, Newspaper, ChevronDown, ChevronUp, Radio } from "lucide-react";

const MOCK_ARTICLES = [
  { id: "1", title: "SEBI tightens F&O margin norms — brokers flag liquidity crunch risk", source: "ET", sourceColor: "#f59e0b", sentiment: "bearish", category: "market", time: "4m ago", tickers: ["ZERODHA", "ANGELONE"], summary: "The regulator has asked all clearing corporations to increase intraday peak margins to 100% from the current 75%, effective next month." },
  { id: "2", title: "Reliance Industries Q4 profit beats estimates at ₹19,407 Cr; Jio & Retail drive growth", source: "Mint", sourceColor: "#818cf8", sentiment: "bullish", category: "corporate", time: "12m ago", tickers: ["RELIANCE"], summary: "Standalone net profit rose 7.3% YoY helped by strong performance in telecom and retail segments, offsetting O2C margin pressure." },
  { id: "3", title: "RBI holds repo at 6.5% for eighth consecutive meeting; GDP outlook revised upward", source: "MC", sourceColor: "#34d399", sentiment: "neutral", category: "market", time: "28m ago", tickers: [], summary: "The monetary policy committee voted 5-1 to keep rates unchanged, citing persistent core inflation while projecting FY26 GDP at 7.2%." },
  { id: "4", title: "NSE derivatives turnover hits ₹4.2 lakh Cr; options volume 3× year-ago levels", source: "ET", sourceColor: "#f59e0b", sentiment: "bullish", category: "market", time: "41m ago", tickers: ["NIFTY50"], summary: "Weekly expiry contracts dominated volumes, with index options accounting for 93% of all F&O trades on Thursday." },
  { id: "5", title: "Adani Green surges 7% as MSCI index inclusion boosts foreign inflows", source: "Mint", sourceColor: "#818cf8", sentiment: "bullish", category: "corporate", time: "1h ago", tickers: ["ADANIGREEN"], summary: "The stock was included in the MSCI Global Standard Index, triggering passive fund buying estimated at $340 million." },
  { id: "6", title: "FII outflows persist for fifth session; DII buying absorbs selling around 22,400", source: "MC", sourceColor: "#34d399", sentiment: "bearish", category: "market", time: "1h ago", tickers: [], summary: "Foreign investors sold ₹2,840 Cr worth of equities while domestic institutions bought ₹3,120 Cr, keeping the index range-bound." },
];

const STATS = { total: 214, bullish: 89, bearish: 61, neutral: 64 };

export function VariantB() {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState("all");

  const filtered = MOCK_ARTICLES.filter(a => {
    if (tab !== "all" && a.category !== tab) return false;
    if (search && !a.title.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const bPct = Math.round((STATS.bullish / STATS.total) * 100);
  const rPct = Math.round((STATS.bearish / STATS.total) * 100);

  const sentConf = (s: string) =>
    s === "bullish" ? { color: "#4ade80", bg: "rgba(74,222,128,0.1)", border: "rgba(74,222,128,0.2)", Icon: TrendingUp }
    : s === "bearish" ? { color: "#f87171", bg: "rgba(248,113,113,0.1)", border: "rgba(248,113,113,0.2)", Icon: TrendingDown }
    : { color: "#94a3b8", bg: "rgba(148,163,184,0.08)", border: "rgba(148,163,184,0.15)", Icon: Minus };

  return (
    <div className="min-h-screen relative overflow-hidden" style={{ fontFamily: "'Inter', sans-serif" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
        @keyframes ticker { 0%{transform:translateX(0)} 100%{transform:translateX(-50%)} }
        @keyframes glow { 0%,100%{opacity:0.6} 50%{opacity:1} }
        @keyframes float { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-20px)} }
        .ticker-run { animation: ticker 50s linear infinite; }
        .orb1 { animation: float 8s ease-in-out infinite; }
        .orb2 { animation: float 11s ease-in-out infinite reverse; }
      `}</style>

      {/* Background gradient */}
      <div className="fixed inset-0 z-0" style={{ background: "linear-gradient(135deg, #0a0118 0%, #0d0527 35%, #050e2e 65%, #000d1a 100%)" }} />

      {/* Floating orbs */}
      <div className="orb1 fixed pointer-events-none z-0" style={{ top: "-10%", right: "5%", width: 500, height: 500, borderRadius: "50%", background: "radial-gradient(circle, rgba(99,102,241,0.3) 0%, transparent 70%)", filter: "blur(60px)" }} />
      <div className="orb2 fixed pointer-events-none z-0" style={{ bottom: "5%", left: "-5%", width: 450, height: 450, borderRadius: "50%", background: "radial-gradient(circle, rgba(139,92,246,0.25) 0%, transparent 70%)", filter: "blur(60px)" }} />
      <div className="fixed pointer-events-none z-0" style={{ top: "40%", left: "50%", width: 300, height: 300, borderRadius: "50%", background: "radial-gradient(circle, rgba(56,189,248,0.12) 0%, transparent 70%)", filter: "blur(50px)" }} />

      <div className="relative z-10 p-6 space-y-5">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <div className="p-2 rounded-xl" style={{ background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.25)" }}>
                <Newspaper className="w-5 h-5" style={{ color: "#818cf8" }} />
              </div>
              <h1 className="text-2xl font-black" style={{ background: "linear-gradient(90deg, #c7d2fe, #a5b4fc, #818cf8)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                Market News Feed
              </h1>
            </div>
            <p className="text-sm ml-14" style={{ color: "rgba(148,163,184,0.7)" }}>Live intelligence from ET · Livemint · Moneycontrol · NSE</p>
          </div>
          <button className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium" style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", color: "rgba(255,255,255,0.7)", backdropFilter: "blur(12px)" }}>
            <RefreshCw className="w-4 h-4" /> Refresh
          </button>
        </div>

        {/* Live ticker */}
        <div className="rounded-2xl overflow-hidden" style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", backdropFilter: "blur(20px)" }}>
          <div className="flex items-center gap-3 px-4 py-2.5">
            <div className="flex items-center gap-1.5 shrink-0">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: "#f87171" }} />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5" style={{ background: "#ef4444" }} />
              </span>
              <span className="text-xs font-bold tracking-widest" style={{ color: "#f8fafc" }}>LIVE</span>
            </div>
            <div className="w-px h-4" style={{ background: "rgba(255,255,255,0.1)" }} />
            <div className="overflow-hidden flex-1">
              <div className="ticker-run whitespace-nowrap text-xs" style={{ color: "rgba(199,210,254,0.8)", display: "inline-block" }}>
                {MOCK_ARTICLES.map(a => a.title).join("   ·   ")}&nbsp;&nbsp;&nbsp;&nbsp;{MOCK_ARTICLES.map(a => a.title).join("   ·   ")}
              </div>
            </div>
          </div>
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-4 gap-3">
          {[
            { label: "Total Articles", val: STATS.total, color: "#818cf8", grad: "rgba(99,102,241,0.15)" },
            { label: "Bullish", val: STATS.bullish, color: "#4ade80", grad: "rgba(74,222,128,0.12)" },
            { label: "Bearish", val: STATS.bearish, color: "#f87171", grad: "rgba(248,113,113,0.12)" },
            { label: "Neutral", val: STATS.neutral, color: "#94a3b8", grad: "rgba(148,163,184,0.08)" },
          ].map(s => (
            <div key={s.label} className="rounded-2xl p-4" style={{ background: `linear-gradient(135deg, ${s.grad}, rgba(255,255,255,0.03))`, border: "1px solid rgba(255,255,255,0.08)", backdropFilter: "blur(12px)" }}>
              <div className="text-xs mb-2" style={{ color: "rgba(148,163,184,0.7)" }}>{s.label}</div>
              <div className="text-3xl font-black" style={{ color: s.color, textShadow: `0 0 30px ${s.color}50` }}>{s.val}</div>
            </div>
          ))}
        </div>

        {/* Mood sensor */}
        <div className="rounded-2xl p-4" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)", backdropFilter: "blur(12px)" }}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Radio className="w-4 h-4" style={{ color: "#818cf8" }} />
              <span className="text-sm font-semibold" style={{ color: "#e2e8f0" }}>Market Mood Sensor</span>
            </div>
            <span className="text-xs font-bold px-3 py-1 rounded-full" style={{ background: "rgba(74,222,128,0.15)", color: "#4ade80", border: "1px solid rgba(74,222,128,0.25)" }}>
              ▲ Bullish
            </span>
          </div>
          <div className="h-2.5 rounded-full overflow-hidden flex gap-0.5" style={{ background: "rgba(255,255,255,0.05)" }}>
            <div style={{ width: `${bPct}%`, background: "linear-gradient(90deg, #16a34a, #4ade80)", borderRadius: "6px 0 0 6px", transition: "width 1s" }} />
            <div style={{ width: `${100 - bPct - rPct}%`, background: "rgba(148,163,184,0.3)" }} />
            <div style={{ width: `${rPct}%`, background: "linear-gradient(90deg, #ef4444, #f87171)", borderRadius: "0 6px 6px 0", transition: "width 1s" }} />
          </div>
          <div className="flex justify-between mt-2 text-xs" style={{ color: "rgba(148,163,184,0.6)" }}>
            <span>{bPct}% Bullish</span><span>{100 - bPct - rPct}% Neutral</span><span>{rPct}% Bearish</span>
          </div>
        </div>

        {/* Search + tabs */}
        <div className="flex items-center gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: "rgba(148,163,184,0.5)" }} />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search headlines..."
              className="w-full pl-10 pr-4 py-2.5 rounded-xl text-sm outline-none"
              style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)", color: "#e2e8f0", backdropFilter: "blur(12px)" }}
            />
          </div>
          <div className="flex gap-1 p-1 rounded-xl" style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)" }}>
            {["all", "market", "corporate", "general"].map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-all"
                style={tab === t
                  ? { background: "rgba(99,102,241,0.3)", color: "#c7d2fe", border: "1px solid rgba(99,102,241,0.3)" }
                  : { color: "rgba(148,163,184,0.6)", border: "1px solid transparent" }}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        {/* News cards */}
        <div className="space-y-3">
          {filtered.map(article => {
            const s = sentConf(article.sentiment);
            const isOpen = expanded === article.id;
            return (
              <div
                key={article.id}
                onClick={() => setExpanded(isOpen ? null : article.id)}
                className="rounded-2xl cursor-pointer transition-all duration-200"
                style={{
                  background: "rgba(255,255,255,0.035)",
                  border: "1px solid rgba(255,255,255,0.07)",
                  backdropFilter: "blur(16px)",
                  borderLeft: `3px solid ${s.color}`,
                }}
              >
                <div className="p-4">
                  <div className="flex items-start gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2 mb-2">
                        <span className="text-xs font-bold px-2.5 py-1 rounded-lg text-white" style={{ background: article.sourceColor }}>
                          {article.source}
                        </span>
                        <span className="flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-lg" style={{ background: s.bg, color: s.color, border: `1px solid ${s.border}` }}>
                          <s.Icon className="w-3 h-3" />{article.sentiment}
                        </span>
                        <span className="text-xs" style={{ color: "rgba(148,163,184,0.5)" }}>{article.time}</span>
                      </div>
                      <p className="text-sm font-semibold leading-snug" style={{ color: "#f1f5f9" }}>{article.title}</p>
                      {isOpen && article.summary && (
                        <p className="text-xs mt-2.5 leading-relaxed" style={{ color: "rgba(148,163,184,0.8)" }}>{article.summary}</p>
                      )}
                      {article.tickers.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mt-2">
                          {article.tickers.map(t => (
                            <span key={t} className="text-xs font-mono font-bold px-2 py-0.5 rounded-lg" style={{ background: "rgba(99,102,241,0.15)", color: "#a5b4fc", border: "1px solid rgba(99,102,241,0.2)" }}>
                              {t}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex flex-col items-end gap-2 shrink-0">
                      <a href="#" onClick={e => e.stopPropagation()} style={{ color: "#818cf8" }}>
                        <ExternalLink className="w-4 h-4" />
                      </a>
                      <span style={{ color: "rgba(148,163,184,0.4)" }}>
                        {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
