import { useState } from "react";
import { TrendingUp, TrendingDown, Minus, ExternalLink, RefreshCw, Search, BarChart2, Building2, Zap, Newspaper, Clock, Radio } from "lucide-react";

const MOCK_ARTICLES = [
  { id: "1", title: "SEBI tightens F&O margin norms — brokers flag liquidity crunch risk", source: "Economic Times", sourceShort: "ET", sourceColor: "#f59e0b", sentiment: "bearish", category: "market", time: "4m ago", tickers: ["ZERODHA", "ANGELONE"], summary: "The regulator has asked all clearing corporations to increase intraday peak margins to 100%." },
  { id: "2", title: "Reliance Industries Q4 profit beats estimates at ₹19,407 Cr; Jio & Retail drive growth", source: "Livemint", sourceShort: "MINT", sourceColor: "#6366f1", sentiment: "bullish", category: "corporate", time: "12m ago", tickers: ["RELIANCE"], summary: "Standalone net profit rose 7.3% YoY helped by strong performance in telecom and retail segments." },
  { id: "3", title: "RBI holds repo at 6.5% for eighth meet; GDP outlook revised upward to 7.2%", source: "Moneycontrol", sourceShort: "MC", sourceColor: "#10b981", sentiment: "neutral", category: "market", time: "28m ago", tickers: [], summary: "The monetary policy committee voted 5-1 to keep rates unchanged, citing persistent core inflation." },
  { id: "4", title: "NSE derivatives turnover hits ₹4.2 lakh Cr; options volume 3× year-ago levels", source: "Economic Times", sourceShort: "ET", sourceColor: "#f59e0b", sentiment: "bullish", category: "market", time: "41m ago", tickers: ["NIFTY50"], summary: "Weekly expiry contracts dominated volumes, with index options accounting for 93% of all F&O trades." },
  { id: "5", title: "Adani Green surges 7% as MSCI index inclusion triggers ₹2,800 Cr foreign inflows", source: "Livemint", sourceShort: "MINT", sourceColor: "#6366f1", sentiment: "bullish", category: "corporate", time: "1h ago", tickers: ["ADANIGREEN"], summary: "The stock was included in the MSCI Global Standard Index, triggering passive fund buying." },
  { id: "6", title: "FII outflows persist for fifth session; DII buying absorbs selling around 22,400", source: "Moneycontrol", sourceShort: "MC", sourceColor: "#10b981", sentiment: "bearish", category: "market", time: "1h ago", tickers: [], summary: "Foreign investors sold ₹2,840 Cr worth of equities while domestic institutions bought ₹3,120 Cr." },
  { id: "7", title: "Infosys raises FY26 revenue guidance to 4.5–7%; deal wins at all-time high", source: "Economic Times", sourceShort: "ET", sourceColor: "#f59e0b", sentiment: "bullish", category: "corporate", time: "2h ago", tickers: ["INFY"], summary: "Robust deal pipeline and strong verticals helped Infosys beat street estimates for the quarter." },
];

const STATS = { total: 214, bullish: 89, bearish: 61, neutral: 64 };

const CAT_META: Record<string, { label: string; color: string; bg: string; Icon: React.ElementType }> = {
  market:    { label: "Market",    color: "#0891b2", bg: "#ecfeff",    Icon: BarChart2 },
  corporate: { label: "Companies", color: "#7c3aed", bg: "#f5f3ff",   Icon: Building2 },
  general:   { label: "General",   color: "#ea580c", bg: "#fff7ed",   Icon: Zap },
};

const SENT_META: Record<string, { label: string; color: string; bg: string; border: string; Icon: React.ElementType }> = {
  bullish: { label: "Bullish", color: "#16a34a", bg: "#dcfce7", border: "#bbf7d0", Icon: TrendingUp },
  bearish: { label: "Bearish", color: "#dc2626", bg: "#fee2e2", border: "#fecaca", Icon: TrendingDown },
  neutral: { label: "Neutral", color: "#6b7280", bg: "#f9fafb", border: "#e5e7eb", Icon: Minus },
};

export function VariantC() {
  const [activeTab, setActiveTab] = useState("all");
  const [search, setSearch] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const filtered = MOCK_ARTICLES.filter(a => {
    if (activeTab !== "all" && a.category !== activeTab) return false;
    if (search && !a.title.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const featured = filtered[0];
  const rest = filtered.slice(1);

  const bPct = Math.round((STATS.bullish / STATS.total) * 100);
  const rPct = Math.round((STATS.bearish / STATS.total) * 100);

  return (
    <div className="min-h-screen" style={{ background: "#f8fafc", fontFamily: "'Inter', sans-serif" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Playfair+Display:wght@700;800&display=swap');
        @keyframes ticker { 0%{transform:translateX(0)} 100%{transform:translateX(-50%)} }
        .ticker-run { animation: ticker 50s linear infinite; }
      `}</style>

      {/* Top accent bar */}
      <div className="h-1.5" style={{ background: "linear-gradient(90deg, #4f46e5, #7c3aed, #db2777, #ea580c)" }} />

      {/* Header */}
      <div className="bg-white border-b px-6 py-4" style={{ borderColor: "#e2e8f0" }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: "linear-gradient(135deg, #4f46e5, #7c3aed)" }}>
                <Newspaper className="w-4 h-4 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-black leading-none tracking-tight" style={{ color: "#0f172a" }}>Market News Feed</h1>
                <p className="text-[11px] mt-0.5" style={{ color: "#94a3b8" }}>ET · Livemint · Moneycontrol · NSE</p>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5" style={{ color: "#cbd5e1" }} />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search news..."
                className="pl-9 pr-4 py-2 rounded-xl text-sm outline-none w-56"
                style={{ background: "#f8fafc", border: "1.5px solid #e2e8f0", color: "#0f172a" }}
              />
            </div>
            <button className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold transition-all hover:brightness-95" style={{ background: "#4f46e5", color: "white" }}>
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </button>
          </div>
        </div>

        {/* Live ticker */}
        <div className="mt-3 flex items-center gap-3 rounded-xl overflow-hidden px-4 py-2" style={{ background: "#0f172a" }}>
          <div className="flex items-center gap-1.5 shrink-0">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500" />
            </span>
            <span className="text-[11px] font-black text-white tracking-widest">LIVE</span>
          </div>
          <div className="w-px h-4 bg-white/20" />
          <div className="overflow-hidden flex-1">
            <div className="ticker-run whitespace-nowrap text-[11px] text-white/70 font-medium" style={{ display: "inline-block" }}>
              {MOCK_ARTICLES.map(a => `${a.sourceShort} · ${a.title}`).join("   |   ")}&nbsp;&nbsp;&nbsp;{MOCK_ARTICLES.map(a => `${a.sourceShort} · ${a.title}`).join("   |   ")}
            </div>
          </div>
        </div>
      </div>

      <div className="px-6 py-5 space-y-5">
        {/* Stats + Mood */}
        <div className="grid grid-cols-5 gap-3">
          {[
            { label: "Total", val: STATS.total, color: "#4f46e5", lightBg: "#eef2ff" },
            { label: "Bullish", val: STATS.bullish, color: "#16a34a", lightBg: "#dcfce7" },
            { label: "Bearish", val: STATS.bearish, color: "#dc2626", lightBg: "#fee2e2" },
            { label: "Neutral", val: STATS.neutral, color: "#6b7280", lightBg: "#f3f4f6" },
          ].map(s => (
            <div key={s.label} className="rounded-2xl p-4 bg-white border" style={{ borderColor: "#e2e8f0" }}>
              <div className="text-xs mb-1 font-medium" style={{ color: "#94a3b8" }}>{s.label}</div>
              <div className="text-2xl font-black" style={{ color: s.color }}>{s.val}</div>
            </div>
          ))}

          <div className="rounded-2xl p-4 bg-white border col-span-1" style={{ borderColor: "#e2e8f0" }}>
            <div className="flex items-center gap-1.5 mb-2">
              <Radio className="w-3.5 h-3.5" style={{ color: "#4f46e5" }} />
              <span className="text-xs font-semibold" style={{ color: "#0f172a" }}>Mood</span>
            </div>
            <div className="h-2 rounded-full overflow-hidden flex" style={{ background: "#f3f4f6" }}>
              <div style={{ width: `${bPct}%`, background: "#16a34a", borderRadius: "4px 0 0 4px" }} />
              <div style={{ width: `${100 - bPct - rPct}%`, background: "#d1d5db" }} />
              <div style={{ width: `${rPct}%`, background: "#dc2626", borderRadius: "0 4px 4px 0" }} />
            </div>
            <div className="flex justify-between mt-1.5 text-[10px]" style={{ color: "#94a3b8" }}>
              <span>{bPct}%</span><span>{rPct}%</span>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 bg-white rounded-2xl p-1 border" style={{ borderColor: "#e2e8f0", display: "inline-flex" }}>
          {[{ id: "all", label: "All News", Icon: Newspaper }, { id: "market", label: "Market", Icon: BarChart2 }, { id: "corporate", label: "Companies", Icon: Building2 }, { id: "general", label: "General", Icon: Zap }].map(t => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold transition-all"
              style={activeTab === t.id
                ? { background: "#4f46e5", color: "white" }
                : { color: "#64748b" }}
            >
              <t.Icon className="w-3.5 h-3.5" />
              {t.label}
            </button>
          ))}
        </div>

        {/* Featured article */}
        {featured && (() => {
          const cat = CAT_META[featured.category] ?? CAT_META.market;
          const sent = SENT_META[featured.sentiment];
          return (
            <div className="rounded-2xl overflow-hidden bg-white border" style={{ borderColor: "#e2e8f0" }}>
              <div className="h-1" style={{ background: `linear-gradient(90deg, ${cat.color}, ${sent.color})` }} />
              <div className="p-5">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-xs font-black px-2.5 py-1 rounded-lg text-white" style={{ background: featured.sourceColor }}>{featured.source}</span>
                  <span className="flex items-center gap-1 text-xs font-bold px-2.5 py-1 rounded-lg" style={{ background: sent.bg, color: sent.color, border: `1px solid ${sent.border}` }}>
                    <sent.Icon className="w-3 h-3" />{sent.label}
                  </span>
                  <span className="flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-lg" style={{ background: cat.bg, color: cat.color }}>
                    <cat.Icon className="w-3 h-3" />{cat.label}
                  </span>
                  <span className="text-xs ml-auto flex items-center gap-1" style={{ color: "#94a3b8" }}><Clock className="w-3 h-3" />{featured.time}</span>
                </div>
                <h2 className="text-xl font-black leading-snug mb-2" style={{ color: "#0f172a" }}>{featured.title}</h2>
                {featured.summary && <p className="text-sm leading-relaxed" style={{ color: "#64748b" }}>{featured.summary}</p>}
                <div className="flex items-center gap-3 mt-3">
                  {featured.tickers.map(t => (
                    <span key={t} className="text-xs font-mono font-bold px-2 py-1 rounded-lg" style={{ background: "#eef2ff", color: "#4f46e5" }}>{t}</span>
                  ))}
                  <a href="#" className="ml-auto flex items-center gap-1.5 text-sm font-semibold" style={{ color: "#4f46e5" }}>
                    Read full story <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                </div>
              </div>
            </div>
          );
        })()}

        {/* Rest of articles */}
        <div className="space-y-2.5">
          {rest.map(article => {
            const cat = CAT_META[article.category] ?? CAT_META.market;
            const sent = SENT_META[article.sentiment];
            const isOpen = expandedId === article.id;
            return (
              <div
                key={article.id}
                onClick={() => setExpandedId(isOpen ? null : article.id)}
                className="rounded-2xl bg-white border cursor-pointer transition-all hover:shadow-md"
                style={{ borderColor: "#e2e8f0", borderLeft: `4px solid ${sent.color}` }}
              >
                <div className="p-4">
                  <div className="flex items-start gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2 mb-2">
                        <span className="text-xs font-black px-2 py-0.5 rounded-md text-white" style={{ background: article.sourceColor }}>{article.sourceShort}</span>
                        <span className="flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-md" style={{ background: sent.bg, color: sent.color }}>
                          <sent.Icon className="w-3 h-3" />{sent.label}
                        </span>
                        <span className="flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-md" style={{ background: cat.bg, color: cat.color }}>
                          <cat.Icon className="w-3 h-3" />{cat.label}
                        </span>
                        <span className="text-xs ml-auto" style={{ color: "#94a3b8" }}>{article.time}</span>
                      </div>
                      <p className="text-sm font-semibold leading-snug" style={{ color: "#0f172a" }}>{article.title}</p>
                      {isOpen && article.summary && (
                        <p className="text-xs mt-2 leading-relaxed" style={{ color: "#64748b" }}>{article.summary}</p>
                      )}
                      {article.tickers.length > 0 && (
                        <div className="flex gap-1.5 mt-2">
                          {article.tickers.map(t => (
                            <span key={t} className="text-xs font-mono font-bold px-2 py-0.5 rounded-md" style={{ background: "#eef2ff", color: "#4f46e5" }}>{t}</span>
                          ))}
                        </div>
                      )}
                    </div>
                    <a href="#" onClick={e => e.stopPropagation()} className="shrink-0 mt-1 transition-colors hover:text-indigo-600" style={{ color: "#cbd5e1" }}>
                      <ExternalLink className="w-4 h-4" />
                    </a>
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
