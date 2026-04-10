import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "wouter";
import {
  Newspaper, TrendingUp, TrendingDown, Minus, Search, RefreshCw,
  ExternalLink, Clock, Zap, BarChart2, ChevronDown, ChevronUp,
  Tag, Radio, AlertTriangle, Building2, ArrowUpRight, ArrowDownRight,
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
  const { data, isLoading } = useQuery({ queryKey: ["newsDeals"], queryFn: api.newsDeals, staleTime: 20 * 60 * 1000 });
  const [activeDealsTab, setActiveDealsTab] = useState<"bulk" | "block">("bulk");

  const hdrTxt = isDark ? "#f1f5f9" : "#111827";
  const muTxt = isDark ? "#94a3b8" : "#6b7280";
  const borderCol = isDark ? "#334155" : "#e2e8f0";
  const rowBg = isDark ? "#1e293b" : "#fff";

  const deals = data ? (activeDealsTab === "bulk" ? data.bulk : data.block) : [];

  if (isLoading) return <LoadingCards isDark={isDark} />;

  return (
    <div className="space-y-4">
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
  const { data, isLoading } = useQuery({ queryKey: ["newsEvents"], queryFn: api.newsEvents, staleTime: 15 * 60 * 1000 });
  const muTxt = isDark ? "#94a3b8" : "#6b7280";
  const borderCol = isDark ? "#334155" : "#e2e8f0";
  const hdrTxt = isDark ? "#f1f5f9" : "#111827";

  if (isLoading) return <LoadingCards isDark={isDark} />;

  const events = data?.events ?? [];
  if (!events.length) {
    return <div className="text-center py-10 text-sm" style={{ color: muTxt }}>No upcoming corporate events found</div>;
  }

  return (
    <div className="space-y-2">
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

// ── Refresh Countdown ─────────────────────────────────────────────────────────

function RefreshCountdown({ seconds, onRefresh, isDark }: { seconds: number; onRefresh: () => void; isDark: boolean }) {
  const pct = (seconds / (8 * 60)) * 100;
  return (
    <button
      onClick={onRefresh}
      className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg transition-all hover:brightness-90"
      style={{ background: isDark ? "#1e293b" : "#f3f4f6", color: isDark ? "#94a3b8" : "#6b7280" }}
      title={`Auto-refresh in ${Math.floor(seconds / 60)}m ${seconds % 60}s`}
    >
      <RefreshCw className="w-3.5 h-3.5" style={{ animation: seconds < 10 ? "spin 1s linear infinite" : "none" }} />
      <span>Refresh</span>
      <div className="w-8 h-1 rounded-full overflow-hidden" style={{ background: isDark ? "#334155" : "#e2e8f0" }}>
        <div className="h-full rounded-full bg-indigo-500 transition-all" style={{ width: `${pct}%` }} />
      </div>
    </button>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

type Tab = "all" | "market" | "corporate" | "general" | "deals" | "events";
const TABS: Tab[] = ["all", "market", "corporate", "general", "deals", "events"];

export default function NewsFeed() {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const qc = useQueryClient();

  const [activeTab, setActiveTab] = useState<Tab>("all");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [countdown, setCountdown] = useState(8 * 60);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  const hdrTxt = isDark ? "#f1f5f9" : "#111827";
  const muTxt  = isDark ? "#94a3b8" : "#6b7280";
  const bg     = isDark ? "#0f172a" : "#f8fafc";
  const borderCol = isDark ? "#334155" : "#e2e8f0";

  const feedCategory = (activeTab === "deals" || activeTab === "events") ? "all" : activeTab;

  const { data: feed, isLoading: feedLoading, refetch: refetchFeed } = useQuery({
    queryKey: ["newsFeed", feedCategory, debouncedSearch],
    queryFn:  () => api.newsFeed({ category: feedCategory, search: debouncedSearch, limit: 60 }),
    staleTime: 8 * 60 * 1000,
    enabled: activeTab !== "deals" && activeTab !== "events",
  });

  const { data: stats } = useQuery({
    queryKey: ["newsStats"],
    queryFn:  api.newsStats,
    staleTime: 8 * 60 * 1000,
  });

  const refreshMutation = useMutation({
    mutationFn: api.newsRefresh,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["newsFeed"] });
      qc.invalidateQueries({ queryKey: ["newsStats"] });
      qc.invalidateQueries({ queryKey: ["newsDeals"] });
      qc.invalidateQueries({ queryKey: ["newsEvents"] });
      setCountdown(8 * 60);
    },
  });

  const handleRefresh = useCallback(() => {
    refreshMutation.mutate();
  }, [refreshMutation]);

  useEffect(() => {
    const id = setInterval(() => {
      setCountdown(c => {
        if (c <= 1) { handleRefresh(); return 8 * 60; }
        return c - 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [handleRefresh]);

  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(debounceRef.current);
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
        <RefreshCountdown seconds={countdown} onRefresh={handleRefresh} isDark={isDark} />
      </div>

      {/* Live ticker */}
      {articles.length > 0 && <TickerBanner articles={articles} isDark={isDark} />}

      {/* Stats row */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
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
        <MoodBar
          bullish={stats.sentiments.bullish}
          bearish={stats.sentiments.bearish}
          neutral={stats.sentiments.neutral}
          mood={stats.marketMood}
          isDark={isDark}
        />
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
      ) : feedLoading ? (
        <LoadingCards isDark={isDark} />
      ) : articles.length === 0 ? (
        <div className="text-center py-16" style={{ color: muTxt }}>
          <Newspaper className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="font-medium">No articles found</p>
          <p className="text-sm mt-1">{search ? "Try a different search term" : "Check back soon"}</p>
        </div>
      ) : (
        <div className="space-y-3">
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
