import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { Link } from "wouter";
import {
  Newspaper, TrendingUp, TrendingDown, Minus, Search, RefreshCw,
  ExternalLink, Clock, Zap, BarChart2, ChevronDown, ChevronUp,
  Tag, Radio, AlertTriangle, Building2, ArrowUpRight, ArrowDownRight,
  Film, List, X,
} from "lucide-react";
import { api, NewsArticle } from "@/lib/api";
import { useTheme } from "@/context/ThemeContext";

// ── Helpers ───────────────────────────────────────────────────────────────────

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function sentimentColor(s: string, isDark: boolean) {
  if (s === "bullish") return { border: "#16a34a", bg: isDark ? "rgba(22,163,74,0.08)" : "#f0fdf4", text: "#16a34a" };
  if (s === "bearish") return { border: "#dc2626", bg: isDark ? "rgba(220,38,38,0.08)" : "#fef2f2", text: "#dc2626" };
  return { border: isDark ? "#334155" : "#e2e8f0", bg: isDark ? "#1e293b" : "#fff", text: isDark ? "#94a3b8" : "#6b7280" };
}

const SENTIMENT_ICONS: Record<string, React.ReactNode> = {
  bullish: <TrendingUp  className="w-3 h-3" />,
  bearish: <TrendingDown className="w-3 h-3" />,
  neutral: <Minus       className="w-3 h-3" />,
};

const EVENT_TYPE_COLORS: Record<string, string> = {
  dividend:     "#7c3aed",
  results:      "#0891b2",
  split:        "#ea580c",
  meeting:      "#6b7280",
  merger:       "#d97706",
  announcement: "#6366f1",
};

const CATEGORY_META: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  all:       { label: "All News",       icon: <Newspaper className="w-3.5 h-3.5" />,  color: "#6366f1" },
  market:    { label: "Market",         icon: <BarChart2 className="w-3.5 h-3.5" />,  color: "#0891b2" },
  corporate: { label: "Companies",      icon: <Building2 className="w-3.5 h-3.5" />,  color: "#7c3aed" },
  general:   { label: "General",        icon: <Zap       className="w-3.5 h-3.5" />,  color: "#ea580c" },
  deals:     { label: "Bulk/Block Deals", icon: <Tag      className="w-3.5 h-3.5" />,  color: "#16a34a" },
  events:    { label: "Corp. Events",   icon: <AlertTriangle className="w-3.5 h-3.5" />, color: "#d97706" },
};

// ── Ticker Banner ─────────────────────────────────────────────────────────────

function TickerBanner({ articles, isDark }: { articles: NewsArticle[]; isDark: boolean }) {
  const headlines = articles.slice(0, 12).map(a => a.title);
  if (!headlines.length) return null;

  const text = headlines.join("   ·   ");

  return (
    <div
      className="relative overflow-hidden rounded-xl flex items-center gap-3 px-4 py-2.5"
      style={{ background: isDark ? "#0f172a" : "#1e1b4b", minHeight: 40 }}
    >
      <div className="flex items-center gap-1.5 shrink-0 z-10">
        <span className="relative flex h-2.5 w-2.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500" />
        </span>
        <span className="text-xs font-bold text-white tracking-widest uppercase">Live</span>
      </div>
      <div className="overflow-hidden flex-1 relative">
        <div
          className="whitespace-nowrap text-xs font-medium text-white/90"
          style={{
            animation: "tickerScroll 60s linear infinite",
            display: "inline-block",
          }}
        >
          {text}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{text}
        </div>
      </div>
    </div>
  );
}

// ── Market Mood Bar ───────────────────────────────────────────────────────────

function MoodBar({
  bullish, bearish, neutral, mood, isDark,
}: { bullish: number; bearish: number; neutral: number; mood: string; isDark: boolean }) {
  const total = bullish + bearish + neutral || 1;
  const bPct = Math.round((bullish / total) * 100);
  const rPct = Math.round((bearish / total) * 100);
  const nPct = 100 - bPct - rPct;

  return (
    <div className="rounded-2xl border p-4" style={{ background: isDark ? "#1e293b" : "#fff", borderColor: isDark ? "#334155" : "#e2e8f0" }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Radio className="w-4 h-4" style={{ color: "#6366f1" }} />
          <span className="text-sm font-semibold" style={{ color: isDark ? "#f1f5f9" : "#111827" }}>
            Market Mood Sensor
          </span>
        </div>
        <div
          className="flex items-center gap-1.5 text-xs font-bold px-3 py-1 rounded-full"
          style={{
            background: mood === "bullish" ? "#dcfce7" : mood === "bearish" ? "#fee2e2" : isDark ? "#334155" : "#f3f4f6",
            color: mood === "bullish" ? "#15803d" : mood === "bearish" ? "#b91c1c" : isDark ? "#94a3b8" : "#6b7280",
          }}
        >
          {mood === "bullish" ? <TrendingUp className="w-3 h-3" /> : mood === "bearish" ? <TrendingDown className="w-3 h-3" /> : <Minus className="w-3 h-3" />}
          {mood.charAt(0).toUpperCase() + mood.slice(1)}
        </div>
      </div>

      <div className="h-3 rounded-full overflow-hidden flex gap-0.5">
        <div style={{ width: `${bPct}%`, background: "#16a34a", transition: "width 1s ease", borderRadius: "6px 0 0 6px" }} />
        <div style={{ width: `${nPct}%`, background: isDark ? "#475569" : "#d1d5db", transition: "width 1s ease" }} />
        <div style={{ width: `${rPct}%`, background: "#dc2626", transition: "width 1s ease", borderRadius: "0 6px 6px 0" }} />
      </div>

      <div className="flex justify-between mt-2 text-xs" style={{ color: isDark ? "#94a3b8" : "#6b7280" }}>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-600 inline-block" />{bPct}% Bullish</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full inline-block" style={{ background: isDark ? "#475569" : "#d1d5db" }} />{nPct}% Neutral</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-600 inline-block" />{rPct}% Bearish</span>
      </div>
    </div>
  );
}

// ── News Card ─────────────────────────────────────────────────────────────────

function NewsCard({ article, isDark, index }: { article: NewsArticle; isDark: boolean; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const colors = sentimentColor(article.sentiment, isDark);

  return (
    <div
      className="rounded-xl border overflow-hidden cursor-pointer transition-all duration-200 hover:shadow-lg hover:-translate-y-0.5"
      style={{
        background: colors.bg,
        borderLeft: `3px solid ${colors.border}`,
        borderTop: `1px solid ${isDark ? "#334155" : "#e2e8f0"}`,
        borderRight: `1px solid ${isDark ? "#334155" : "#e2e8f0"}`,
        borderBottom: `1px solid ${isDark ? "#334155" : "#e2e8f0"}`,
        animationDelay: `${index * 40}ms`,
      }}
      onClick={() => setExpanded(e => !e)}
    >
      <div className="p-3.5">
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-1.5 mb-1.5">
              <span
                className="text-xs font-bold px-2 py-0.5 rounded-md text-white"
                style={{ background: article.sourceColor }}
              >
                {article.sourceShort}
              </span>
              <span
                className="flex items-center gap-0.5 text-xs font-semibold px-1.5 py-0.5 rounded-md"
                style={{ background: colors.border + "20", color: colors.border }}
              >
                {SENTIMENT_ICONS[article.sentiment]}
                {article.sentiment}
              </span>
              <span className="text-xs" style={{ color: isDark ? "#64748b" : "#9ca3af" }}>
                {timeAgo(article.published)}
              </span>
            </div>

            <p className="text-sm font-semibold leading-snug" style={{ color: isDark ? "#f1f5f9" : "#111827" }}>
              {article.title}
            </p>

            {expanded && article.summary && (
              <p className="text-xs mt-2 leading-relaxed" style={{ color: isDark ? "#94a3b8" : "#6b7280" }}>
                {article.summary}
              </p>
            )}

            {article.tickers.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {article.tickers.map(t => (
                  <Link key={t} href={`/stocks?q=${t}`} onClick={e => e.stopPropagation()}>
                    <span
                      className="text-xs font-mono font-bold px-1.5 py-0.5 rounded cursor-pointer hover:opacity-80 transition-opacity"
                      style={{ background: isDark ? "#334155" : "#f3f4f6", color: "#6366f1" }}
                    >
                      {t}
                    </span>
                  </Link>
                ))}
              </div>
            )}
          </div>

          <div className="flex flex-col items-end gap-2 shrink-0">
            <a
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              className="p-1.5 rounded-lg transition-colors hover:bg-indigo-100 dark:hover:bg-indigo-900/30"
              style={{ color: "#6366f1" }}
            >
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
            <button style={{ color: isDark ? "#475569" : "#d1d5db" }}>
              {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Deals Table ───────────────────────────────────────────────────────────────

function DealsSection({ isDark }: { isDark: boolean }) {
  const { data, isLoading, isFetching } = useQuery({ queryKey: ["newsDeals"], queryFn: api.newsDeals, staleTime: 20 * 60 * 1000, placeholderData: keepPreviousData });
  const [activeDealsTab, setActiveDealsTab] = useState<"bulk" | "block">("bulk");

  const hdrTxt = isDark ? "#f1f5f9" : "#111827";
  const muTxt = isDark ? "#94a3b8" : "#6b7280";
  const borderCol = isDark ? "#334155" : "#e2e8f0";
  const rowBg = isDark ? "#1e293b" : "#fff";

  const deals = data ? (activeDealsTab === "bulk" ? data.bulk : data.block) : [];

  if (isLoading && !data) return <LoadingCards isDark={isDark} />;

  return (
    <div className="relative space-y-4">
      <SectionLoader active={isFetching && !isLoading} />
      <div className="flex gap-2">
        {(["bulk", "block"] as const).map(t => (
          <button
            key={t}
            onClick={() => setActiveDealsTab(t)}
            className="px-4 py-1.5 rounded-lg text-xs font-semibold transition-all"
            style={{
              background: activeDealsTab === t ? "#6366f1" : isDark ? "#1e293b" : "#fff",
              color: activeDealsTab === t ? "#fff" : muTxt,
              border: `1px solid ${activeDealsTab === t ? "#6366f1" : borderCol}`,
            }}
          >
            {t === "bulk" ? "Bulk Deals" : "Block Deals"}
            {data && (
              <span className="ml-1.5 text-xs opacity-70">
                ({t === "bulk" ? data.bulk.length : data.block.length})
              </span>
            )}
          </button>
        ))}
      </div>

      {deals.length === 0 ? (
        <div className="text-center py-10 text-sm" style={{ color: muTxt }}>
          No {activeDealsTab} deals data available today
        </div>
      ) : (
        <div className="rounded-xl border overflow-hidden" style={{ borderColor: borderCol }}>
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[600px]">
              <thead>
                <tr style={{ background: isDark ? "#0f172a" : "#f8fafc", borderBottom: `1px solid ${borderCol}` }}>
                  {["Date", "Symbol", "Company", "Client", "Side", "Qty", "Price (₹)"].map(h => (
                    <th key={h} className="text-left px-3 py-2.5 font-semibold" style={{ color: muTxt }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {deals.map((d, i) => (
                  <tr
                    key={i}
                    style={{ background: rowBg, borderBottom: `1px solid ${borderCol}` }}
                    className="hover:brightness-95 transition-all"
                  >
                    <td className="px-3 py-2.5 font-mono" style={{ color: muTxt }}>{d.date}</td>
                    <td className="px-3 py-2.5">
                      <span className="font-bold font-mono" style={{ color: "#6366f1" }}>{d.symbol}</span>
                    </td>
                    <td className="px-3 py-2.5 max-w-[160px] truncate" style={{ color: hdrTxt }}>{d.name}</td>
                    <td className="px-3 py-2.5 max-w-[140px] truncate" style={{ color: muTxt }}>{d.client}</td>
                    <td className="px-3 py-2.5">
                      <span
                        className="px-2 py-0.5 rounded-full text-xs font-bold"
                        style={{
                          background: d.side === "BUY" ? "#dcfce7" : "#fee2e2",
                          color: d.side === "BUY" ? "#15803d" : "#b91c1c",
                        }}
                      >
                        {d.side === "BUY" ? <span className="flex items-center gap-0.5"><ArrowUpRight className="w-3 h-3" />BUY</span> : <span className="flex items-center gap-0.5"><ArrowDownRight className="w-3 h-3" />SELL</span>}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 font-mono" style={{ color: hdrTxt }}>
                      {d.quantity ? d.quantity.toLocaleString("en-IN") : "—"}
                    </td>
                    <td className="px-3 py-2.5 font-mono font-bold" style={{ color: hdrTxt }}>
                      {d.price ? `₹${d.price.toLocaleString("en-IN")}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Corporate Events ──────────────────────────────────────────────────────────

function EventsSection({ isDark }: { isDark: boolean }) {
  const { data, isLoading, isFetching } = useQuery({ queryKey: ["newsEvents"], queryFn: api.newsEvents, staleTime: 15 * 60 * 1000, placeholderData: keepPreviousData });
  const muTxt = isDark ? "#94a3b8" : "#6b7280";
  const borderCol = isDark ? "#334155" : "#e2e8f0";
  const hdrTxt = isDark ? "#f1f5f9" : "#111827";

  if (isLoading && !data) return <LoadingCards isDark={isDark} />;

  const events = data?.events ?? [];
  if (!events.length) {
    return <div className="text-center py-10 text-sm" style={{ color: muTxt }}>No upcoming corporate events found</div>;
  }

  return (
    <div className="relative space-y-2">
      <SectionLoader active={isFetching && !isLoading} />
      {events.map((ev, i) => (
        <div
          key={i}
          className="flex items-center gap-3 rounded-xl border p-3.5 hover:brightness-95 transition-all"
          style={{ background: isDark ? "#1e293b" : "#fff", borderColor: borderCol }}
        >
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-white text-xs font-bold"
            style={{ background: EVENT_TYPE_COLORS[ev.type] ?? "#6366f1" }}
          >
            {ev.type.slice(0, 2).toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-bold" style={{ color: "#6366f1" }}>{ev.symbol}</span>
              <span className="text-xs font-medium" style={{ color: hdrTxt }}>{ev.company}</span>
            </div>
            <p className="text-xs mt-0.5 truncate" style={{ color: muTxt }}>{ev.purpose}</p>
          </div>
          <div className="text-xs font-mono shrink-0 flex items-center gap-1" style={{ color: muTxt }}>
            <Clock className="w-3 h-3" /> {ev.date || "TBA"}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Loading Skeletons ─────────────────────────────────────────────────────────

function LoadingCards({ isDark }: { isDark: boolean }) {
  return (
    <div className="space-y-3">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="h-24 rounded-xl animate-pulse" style={{ background: isDark ? "#1e293b" : "#f3f4f6", animationDelay: `${i * 100}ms` }} />
      ))}
    </div>
  );
}

// ── Section Loader ────────────────────────────────────────────────────────────

function SectionLoader({ active }: { active: boolean }) {
  if (!active) return null;
  return (
    <span
      style={{
        position: "absolute", top: 10, right: 10,
        width: 14, height: 14,
        border: "2.5px solid #818cf8",
        borderTopColor: "transparent",
        borderRadius: "50%",
        display: "inline-block",
        animation: "spin 0.75s linear infinite",
        zIndex: 2,
      }}
    />
  );
}

// ── Refresh Countdown ─────────────────────────────────────────────────────────

function RefreshCountdown({
  seconds, onRefresh, isDark, isRefreshing,
}: { seconds: number; onRefresh: () => void; isDark: boolean; isRefreshing: boolean }) {
  const pct = (seconds / (8 * 60)) * 100;
  return (
    <button
      onClick={onRefresh}
      disabled={isRefreshing}
      className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg transition-all hover:brightness-90 disabled:opacity-60"
      style={{ background: isDark ? "#1e293b" : "#f3f4f6", color: isDark ? "#94a3b8" : "#6b7280" }}
      title={isRefreshing ? "Refreshing…" : `Auto-refresh in ${Math.floor(seconds / 60)}m ${seconds % 60}s`}
    >
      <RefreshCw
        className="w-3.5 h-3.5"
        style={{ animation: isRefreshing ? "spin 0.7s linear infinite" : "none" }}
      />
      <span>{isRefreshing ? "Refreshing…" : "Refresh"}</span>
      {!isRefreshing && (
        <div className="w-8 h-1 rounded-full overflow-hidden" style={{ background: isDark ? "#334155" : "#e2e8f0" }}>
          <div className="h-full rounded-full bg-indigo-500 transition-all duration-1000" style={{ width: `${pct}%` }} />
        </div>
      )}
    </button>
  );
}

// ── Reels View (TikTok-style snap scroll) ─────────────────────────────────────

function getReelGradient(article: NewsArticle): string {
  const p: Record<string, Record<string, string>> = {
    market: {
      bullish: "linear-gradient(160deg,#0a0f1e 0%,#0d2a4a 45%,#0a2a1a 100%)",
      bearish: "linear-gradient(160deg,#0a0f1e 0%,#0d1a4a 45%,#2a0a14 100%)",
      neutral: "linear-gradient(160deg,#0a0f1e 0%,#111e40 45%,#0d1a34 100%)",
    },
    corporate: {
      bullish: "linear-gradient(160deg,#160b3a 0%,#0d3030 45%,#0a2818 100%)",
      bearish: "linear-gradient(160deg,#160b3a 0%,#3a0b2a 45%,#40080e 100%)",
      neutral: "linear-gradient(160deg,#160b3a 0%,#1e1650 45%,#120d3a 100%)",
    },
    general: {
      bullish: "linear-gradient(160deg,#1a0800 0%,#3a1a00 45%,#0e2212 100%)",
      bearish: "linear-gradient(160deg,#1a0800 0%,#3a0800 45%,#2a0008 100%)",
      neutral: "linear-gradient(160deg,#1a0a00 0%,#2a1800 45%,#14100a 100%)",
    },
  };
  return p[article.category]?.[article.sentiment] ?? p.market.neutral;
}

function getReelOrbs(article: NewsArticle): [string, string] {
  const cat = article.category;
  const s   = article.sentiment;
  const green = "rgba(34,197,94,0.35)";
  const red   = "rgba(239,68,68,0.35)";
  const neu   = "rgba(148,163,184,0.25)";
  if (cat === "market")    return s === "bullish" ? ["rgba(99,102,241,0.45)", green]   : s === "bearish" ? ["rgba(99,102,241,0.4)", red]   : ["rgba(99,102,241,0.35)", neu];
  if (cat === "corporate") return s === "bullish" ? ["rgba(139,92,246,0.45)", green]  : s === "bearish" ? ["rgba(139,92,246,0.4)", red]  : ["rgba(139,92,246,0.35)", neu];
  return                          s === "bullish" ? ["rgba(251,146,60,0.45)",  green]  : s === "bearish" ? ["rgba(251,146,60,0.4)",  red]  : ["rgba(251,146,60,0.35)",  neu];
}

// Curated Picsum photo IDs that look finance/business/market appropriate.
// Picsum serves from a fast CDN — images load in ~80–150ms, no generation needed.
const REEL_PHOTO_POOLS: Record<string, Record<string, number[]>> = {
  market: {
    bullish: [1067,1070,1074,1075,1076,273,277,1,7,20,39,48,67,119,180],
    bearish: [399,425,434,542,677,765,783,398,380,350,329],
    neutral: [323,333,370,375,450,460,470,480,490,500,510],
  },
  corporate: {
    bullish: [239,266,270,271,259,260,261,263,265,267,268,269],
    bearish: [297,299,302,306,310,315,320,325,330,335],
    neutral: [262,264,337,360,361,362,363,364,365,366],
  },
  general: {
    bullish: [338,342,343,344,349,352,355,357,358,359,361,362],
    bearish: [430,431,432,433,435,440,445,450,455,460],
    neutral: [366,367,368,369,371,372,373,374,376,377,378],
  },
};

function getFallbackImageUrl(article: NewsArticle): string {
  const pool = REEL_PHOTO_POOLS[article.category]?.[article.sentiment]
    ?? REEL_PHOTO_POOLS.market.neutral;
  // Derive a stable index from the article id
  const n = Math.abs(parseInt(article.id.replace(/\D/g, "").slice(0, 6) || "1", 10));
  const id = pool[n % pool.length];
  return `https://picsum.photos/id/${id}/800/500`;
}

// Preload image URLs eagerly so they are cache-warm before the user scrolls to them
function preloadImages(urls: string[]) {
  urls.forEach(src => {
    if (!src) return;
    const img = new window.Image();
    img.src = src;
  });
}

function ReelsView({ articles, onClose }: { articles: NewsArticle[]; onClose: () => void }) {
  const [current, setCurrent] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);

  const goTo = useCallback((idx: number) => {
    const clamped = Math.max(0, Math.min(idx, articles.length - 1));
    setCurrent(clamped);
    cardRefs.current[clamped]?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [articles.length]);

  // Preload images for current + next 4 cards so they're ready before swipe
  useEffect(() => {
    const urls = articles
      .slice(current, current + 5)
      .map(a => a.image_url || getFallbackImageUrl(a));
    preloadImages(urls);
  }, [current, articles]);

  // Also eagerly preload first 5 on mount
  useEffect(() => {
    const urls = articles.slice(0, 5).map(a => a.image_url || getFallbackImageUrl(a));
    preloadImages(urls);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "ArrowDown" || e.key === "j") { e.preventDefault(); goTo(current + 1); }
      if (e.key === "ArrowUp"   || e.key === "k") { e.preventDefault(); goTo(current - 1); }
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [current, goTo, onClose]);

  const handleScroll = useCallback(() => {
    if (!containerRef.current) return;
    const { scrollTop, clientHeight } = containerRef.current;
    if (clientHeight === 0) return;
    const idx = Math.round(scrollTop / clientHeight);
    setCurrent(Math.min(Math.max(idx, 0), articles.length - 1));
  }, [articles.length]);

  const sentLabel = (s: string) =>
    s === "bullish" ? { txt: "BULLISH", color: "#22c55e", bg: "rgba(34,197,94,0.15)" }
    : s === "bearish" ? { txt: "BEARISH", color: "#ef4444", bg: "rgba(239,68,68,0.15)" }
    : { txt: "NEUTRAL", color: "#94a3b8", bg: "rgba(148,163,184,0.12)" };

  const catLabel = (c: string) =>
    c === "market" ? { txt: "MARKET", color: "#38bdf8" }
    : c === "corporate" ? { txt: "COMPANY", color: "#c084fc" }
    : { txt: "GENERAL", color: "#fb923c" };

  const DOTS_MAX = 12;

  return (
    <div className="relative rounded-2xl overflow-hidden" style={{ height: "calc(100vh - 120px)" }}>
      {/* Top bar overlay */}
      <div className="absolute top-0 left-0 right-0 z-30 flex items-center justify-between px-4 py-3 pointer-events-none"
        style={{ background: "linear-gradient(to bottom, rgba(0,0,0,0.65) 0%, transparent 100%)" }}>
        <div className="flex items-center gap-2">
          <Film className="w-4 h-4 text-white" />
          <span className="text-white text-sm font-bold tracking-wide">News Reels</span>
        </div>
        <div className="flex items-center gap-3 pointer-events-auto">
          <span className="text-white/60 text-xs font-mono bg-black/30 px-2 py-0.5 rounded-full">
            {current + 1} / {articles.length}
          </span>
          <button onClick={onClose}
            className="flex items-center gap-1 text-xs text-white/80 hover:text-white transition px-2.5 py-1.5 rounded-lg"
            style={{ background: "rgba(255,255,255,0.12)", backdropFilter: "blur(8px)", border: "1px solid rgba(255,255,255,0.15)" }}>
            <List className="w-3.5 h-3.5" /> List
          </button>
        </div>
      </div>

      {/* Progress dots — right side */}
      <div className="absolute right-3 top-1/2 -translate-y-1/2 z-30 flex flex-col gap-1.5 items-center">
        {articles.slice(0, DOTS_MAX).map((_, i) => (
          <button key={i} onClick={() => goTo(i)}
            className="transition-all duration-200 rounded-full"
            style={{
              width:  i === current ? 6 : 4,
              height: i === current ? 20 : 4,
              background: i === current ? "#fff" : "rgba(255,255,255,0.3)",
            }} />
        ))}
        {articles.length > DOTS_MAX && (
          <span className="text-white/30 text-[9px] mt-1">+{articles.length - DOTS_MAX}</span>
        )}
      </div>

      {/* Snap-scroll container */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="h-full overflow-y-scroll"
        style={{ scrollSnapType: "y mandatory", scrollbarWidth: "none", msOverflowStyle: "none" }}
      >
        {articles.map((article, i) => {
          const [orb1, orb2] = getReelOrbs(article);
          const sent = sentLabel(article.sentiment);
          const cat  = catLabel(article.category);
          const fallbackSrc = getFallbackImageUrl(article);
          const imgSrc = article.image_url || fallbackSrc;
          return (
            <div
              key={article.id}
              ref={el => { cardRefs.current[i] = el; }}
              className="relative flex flex-col overflow-hidden"
              style={{ height: "100%", scrollSnapAlign: "start", flexShrink: 0, background: getReelGradient(article) }}
            >
              {/* Full-bleed background image — fades in on load; gradient shows as placeholder */}
              <img
                src={imgSrc}
                alt=""
                aria-hidden
                className="absolute inset-0 w-full h-full object-cover"
                style={{ zIndex: 0, opacity: 0, transition: "opacity 0.4s ease" }}
                onLoad={e => { e.currentTarget.style.opacity = "1"; }}
                onError={e => {
                  const el = e.currentTarget;
                  if (el.src !== fallbackSrc) {
                    el.src = fallbackSrc;
                  } else {
                    // Picsum also failed — show gradient only (keep opacity 0)
                    el.style.display = "none";
                  }
                }}
              />
              {/* Dark gradient overlay for text readability */}
              <div className="absolute inset-0 pointer-events-none" style={{ zIndex: 1,
                background: "linear-gradient(to bottom, rgba(0,0,0,0.25) 0%, rgba(0,0,0,0.45) 35%, rgba(0,0,0,0.82) 70%, rgba(0,0,0,0.95) 100%)" }} />
              {/* Decorative blurred orbs on top of image */}
              <div className="absolute inset-0 pointer-events-none overflow-hidden" style={{ zIndex: 1 }}>
                <div style={{ position: "absolute", top: "-15%", right: "-8%", width: "55%", height: "55%", borderRadius: "50%",
                  background: `radial-gradient(circle, ${orb1} 0%, transparent 70%)`, filter: "blur(50px)", opacity: 0.5 }} />
                <div style={{ position: "absolute", bottom: "-10%", left: "-8%", width: "50%", height: "50%", borderRadius: "50%",
                  background: `radial-gradient(circle, ${orb2} 0%, transparent 70%)`, filter: "blur(45px)", opacity: 0.5 }} />
              </div>

              {/* Card content */}
              <div className="relative z-10 flex flex-col h-full px-6 pt-16 pb-5">
                {/* Source + meta row */}
                <div className="flex items-center justify-between mb-6">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold px-2.5 py-1 rounded-lg text-white"
                      style={{ background: article.sourceColor ?? "#6366f1" }}>
                      {article.sourceShort}
                    </span>
                    <span className="text-xs font-bold px-2.5 py-1 rounded-lg border"
                      style={{ color: sent.color, background: sent.bg, borderColor: sent.color + "40" }}>
                      {sent.txt}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold px-2 py-0.5 rounded-md"
                      style={{ color: cat.color, background: cat.color + "20" }}>{cat.txt}</span>
                    <span className="text-xs text-white/45 flex items-center gap-1">
                      <Clock className="w-3 h-3" />{timeAgo(article.published)}
                    </span>
                  </div>
                </div>

                {/* Spacer pushes content to bottom 40% */}
                <div className="flex-1" />

                {/* Hero headline */}
                <h2 className="text-[22px] md:text-[28px] font-black leading-tight text-white mb-3"
                  style={{ textShadow: "0 2px 20px rgba(0,0,0,0.6)" }}>
                  {article.title}
                </h2>

                {/* Summary */}
                {article.summary && (
                  <p className="text-sm leading-relaxed text-white/70 mb-4 line-clamp-3">
                    {article.summary}
                  </p>
                )}

                {/* Ticker chips */}
                {article.tickers.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-4">
                    {article.tickers.map(t => (
                      <Link key={t} href={`/stocks?q=${t}`}>
                        <span className="text-xs font-mono font-bold px-2.5 py-1 rounded-lg cursor-pointer hover:opacity-80 transition"
                          style={{ background: "rgba(255,255,255,0.1)", color: "#c7d2fe", border: "1px solid rgba(255,255,255,0.18)" }}>
                          {t}
                        </span>
                      </Link>
                    ))}
                  </div>
                )}

                {/* Bottom bar */}
                <div className="flex items-center justify-between pt-3 border-t border-white/10">
                  <span className="text-xs text-white/30 hidden sm:block">↑↓ scroll · arrow keys · ESC to exit</span>
                  <div className="flex items-center gap-2 ml-auto">
                    {i > 0 && (
                      <button onClick={() => goTo(i - 1)}
                        className="flex items-center gap-1 text-xs text-white/60 hover:text-white transition px-3 py-1.5 rounded-lg"
                        style={{ background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.12)" }}>
                        <ChevronUp className="w-3.5 h-3.5" /> Prev
                      </button>
                    )}
                    <a href={article.url} target="_blank" rel="noopener noreferrer"
                      className="flex items-center gap-1.5 text-sm font-semibold px-4 py-1.5 rounded-xl text-white hover:opacity-90 active:scale-95 transition"
                      style={{ background: "rgba(255,255,255,0.14)", backdropFilter: "blur(8px)", border: "1px solid rgba(255,255,255,0.22)" }}>
                      Read Full Story <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                    {i < articles.length - 1 && (
                      <button onClick={() => goTo(i + 1)}
                        className="flex items-center gap-1 text-xs text-white/60 hover:text-white transition px-3 py-1.5 rounded-lg"
                        style={{ background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.12)" }}>
                        Next <ChevronDown className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>

                {/* Swipe hint for first card */}
                {i === current && i < articles.length - 1 && (
                  <div className="flex flex-col items-center mt-3 text-white/25 text-[11px]">
                    <ChevronDown className="w-4 h-4 animate-bounce" />
                    <span>swipe up for next</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

type Tab = "all" | "market" | "corporate" | "general" | "deals" | "events";
const TABS: Tab[] = ["all", "market", "corporate", "general", "deals", "events"];

export default function NewsFeed() {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const qc = useQueryClient();

  const [activeTab, setActiveTab] = useState<Tab>("all");
  const [reelsMode, setReelsMode] = useState(false);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [countdown, setCountdown] = useState(8 * 60);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const hdrTxt = isDark ? "#f1f5f9" : "#111827";
  const muTxt  = isDark ? "#94a3b8" : "#6b7280";
  const bg     = isDark ? "#0f172a" : "#f8fafc";
  const borderCol = isDark ? "#334155" : "#e2e8f0";

  const feedCategory = (activeTab === "deals" || activeTab === "events") ? "all" : activeTab;

  const { data: feed, isLoading: feedLoading, isFetching: feedFetching } = useQuery({
    queryKey: ["newsFeed", feedCategory, debouncedSearch],
    queryFn:  () => api.newsFeed({ category: feedCategory, search: debouncedSearch, limit: 60 }),
    staleTime: 8 * 60 * 1000,
    placeholderData: keepPreviousData,
    enabled: activeTab !== "deals" && activeTab !== "events",
  });

  const { data: stats, isFetching: statsFetching } = useQuery({
    queryKey: ["newsStats"],
    queryFn:  api.newsStats,
    staleTime: 0,               // always re-fetch fresh — backend has its own 8-min TTL
    refetchOnMount: "always",   // never serve cached zeros after a backend restart
    placeholderData: keepPreviousData,
  });

  const refreshMutation = useMutation({ mutationFn: api.newsRefresh });

  // Stable ref so the interval never needs to re-register
  const refreshFnRef = useRef<() => void>(() => {});
  refreshFnRef.current = useCallback(() => {
    refreshMutation.mutate(undefined, {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["newsFeed"] });
        qc.invalidateQueries({ queryKey: ["newsStats"] });
        qc.invalidateQueries({ queryKey: ["newsDeals"] });
        qc.invalidateQueries({ queryKey: ["newsEvents"] });
        setCountdown(8 * 60);
      },
    });
  }, [refreshMutation, qc]);

  const handleRefresh = useCallback(() => { refreshFnRef.current(); }, []);

  useEffect(() => {
    const id = setInterval(() => {
      setCountdown(c => {
        if (c <= 1) { refreshFnRef.current(); return 8 * 60; }
        return c - 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, []); // empty deps — interval never re-registers

  useEffect(() => {
    clearTimeout(debounceRef.current ?? undefined);
    debounceRef.current = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(debounceRef.current ?? undefined);
  }, [search]);

  const articles = feed?.articles ?? [];

  const sourceStats = useMemo(() => {
    const s = stats?.sources ?? {};
    return Object.entries(s).map(([k, v]) => ({ name: k, count: v as number })).sort((a, b) => b.count - a.count);
  }, [stats]);

  return (
    <div className="space-y-4 min-h-screen" style={{ background: bg }}>
      <style>{`
        @keyframes tickerScroll {
          0%   { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        @keyframes slideIn {
          from { opacity: 0; transform: translateY(12px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        .news-card-enter {
          animation: slideIn 0.3s ease forwards;
        }
      `}</style>

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2" style={{ color: hdrTxt }}>
            <Newspaper className="w-6 h-6 text-indigo-500" />
            Market News Feed
          </h1>
          <p className="text-sm mt-0.5" style={{ color: muTxt }}>
            Live headlines from ET, Livemint, Moneycontrol + NSE data
          </p>
        </div>
        <div className="flex items-center gap-2">
          {activeTab !== "deals" && activeTab !== "events" && (
            <button
              onClick={() => setReelsMode(r => !r)}
              className="flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-xl border transition-all"
              style={{
                background: reelsMode ? "#6366f1" : isDark ? "#1e293b" : "#fff",
                color:      reelsMode ? "#fff" : isDark ? "#94a3b8" : "#6b7280",
                borderColor: reelsMode ? "#6366f1" : isDark ? "#334155" : "#e2e8f0",
                boxShadow:  reelsMode ? "0 0 0 3px rgba(99,102,241,0.2)" : "none",
              }}
            >
              {reelsMode ? <List className="w-3.5 h-3.5" /> : <Film className="w-3.5 h-3.5" />}
              {reelsMode ? "List View" : "Reels"}
            </button>
          )}
          <RefreshCountdown seconds={countdown} onRefresh={handleRefresh} isDark={isDark} isRefreshing={refreshMutation.isPending} />
        </div>
      </div>

      {/* Live ticker */}
      {articles.length > 0 && <TickerBanner articles={articles} isDark={isDark} />}

      {/* Stats row */}
      {stats && (
        <div className="relative grid grid-cols-2 md:grid-cols-4 gap-3">
          <SectionLoader active={statsFetching} />
          <div className="rounded-xl border p-3" style={{ background: isDark ? "#1e293b" : "#fff", borderColor: borderCol }}>
            <div className="text-xs mb-1" style={{ color: muTxt }}>Total Articles</div>
            <div className="text-2xl font-bold" style={{ color: hdrTxt }}>{stats.totalArticles}</div>
          </div>
          <div className="rounded-xl border p-3" style={{ background: isDark ? "#1e293b" : "#fff", borderColor: borderCol }}>
            <div className="text-xs mb-1" style={{ color: muTxt }}>Bullish Signals</div>
            <div className="text-2xl font-bold text-green-600">{stats.sentiments.bullish}</div>
          </div>
          <div className="rounded-xl border p-3" style={{ background: isDark ? "#1e293b" : "#fff", borderColor: borderCol }}>
            <div className="text-xs mb-1" style={{ color: muTxt }}>Bearish Signals</div>
            <div className="text-2xl font-bold text-red-600">{stats.sentiments.bearish}</div>
          </div>
          <div className="rounded-xl border p-3" style={{ background: isDark ? "#1e293b" : "#fff", borderColor: borderCol }}>
            <div className="text-xs mb-1" style={{ color: muTxt }}>Sources</div>
            <div className="flex flex-wrap gap-1 mt-1">
              {sourceStats.map(s => (
                <span key={s.name} className="text-xs px-1.5 py-0.5 rounded font-mono"
                  style={{ background: isDark ? "#334155" : "#f3f4f6", color: "#6366f1" }}>
                  {s.name} {s.count}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Mood bar */}
      {stats && (
        <div className="relative">
          <SectionLoader active={statsFetching} />
          <MoodBar
            bullish={stats.sentiments.bullish}
            bearish={stats.sentiments.bearish}
            neutral={stats.sentiments.neutral}
            mood={stats.marketMood}
            isDark={isDark}
          />
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-hide">
        {TABS.map(tab => {
          const meta = CATEGORY_META[tab];
          const isActive = activeTab === tab;
          return (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold whitespace-nowrap transition-all duration-150 shrink-0"
              style={{
                background: isActive ? meta.color : isDark ? "#1e293b" : "#fff",
                color:      isActive ? "#fff" : muTxt,
                border:     `1px solid ${isActive ? meta.color : borderCol}`,
                boxShadow:  isActive ? `0 0 0 3px ${meta.color}22` : "none",
              }}
            >
              {meta.icon}
              {meta.label}
            </button>
          );
        })}
      </div>

      {/* Search (only for news tabs) */}
      {activeTab !== "deals" && activeTab !== "events" && (
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: muTxt }} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search headlines, companies, sectors…"
            className="w-full pl-9 pr-4 py-2.5 rounded-xl text-sm border outline-none transition-all"
            style={{
              background: isDark ? "#1e293b" : "#fff",
              borderColor: search ? "#6366f1" : borderCol,
              color: hdrTxt,
            }}
          />
          {search && (
            <button className="absolute right-3 top-1/2 -translate-y-1/2 text-xs" style={{ color: muTxt }} onClick={() => setSearch("")}>
              clear
            </button>
          )}
        </div>
      )}

      {/* Content area */}
      {activeTab === "deals" ? (
        <DealsSection isDark={isDark} />
      ) : activeTab === "events" ? (
        <EventsSection isDark={isDark} />
      ) : reelsMode && articles.length > 0 ? (
        <ReelsView articles={articles} onClose={() => setReelsMode(false)} />
      ) : reelsMode && feedLoading ? (
        <div className="flex flex-col items-center justify-center py-24 gap-3" style={{ color: muTxt }}>
          <Film className="w-10 h-10 opacity-30" />
          <p className="text-sm">Loading reels…</p>
        </div>
      ) : feedLoading ? (
        <LoadingCards isDark={isDark} />
      ) : articles.length === 0 ? (
        <div className="text-center py-16" style={{ color: muTxt }}>
          <Newspaper className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="font-medium">No articles found</p>
          <p className="text-sm mt-1">{search ? "Try a different search term" : "Check back soon"}</p>
        </div>
      ) : (
        <div className="relative space-y-3">
          <SectionLoader active={feedFetching && !feedLoading} />
          {articles.map((article, i) => (
            <div key={article.id} className="news-card-enter" style={{ animationDelay: `${Math.min(i * 30, 400)}ms` }}>
              <NewsCard article={article} isDark={isDark} index={i} />
            </div>
          ))}
          <p className="text-center text-xs py-4" style={{ color: muTxt }}>
            Showing {articles.length} of {feed?.total ?? articles.length} articles · Auto-refreshes every 8 minutes
          </p>
        </div>
      )}
    </div>
  );
}
