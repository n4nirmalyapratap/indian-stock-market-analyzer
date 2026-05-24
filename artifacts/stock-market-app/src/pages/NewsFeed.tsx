import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { Link } from "wouter";
import {
  Newspaper, TrendingUp, TrendingDown, Minus, Search, RefreshCw,
  ExternalLink, Clock, Zap, BarChart2, ChevronDown, ChevronUp,
  Radio, Building2, Film, List, X,
} from "lucide-react";
import { api, NewsArticle } from "@/lib/api";
import { useTheme } from "@/context/ThemeContext";
import DataFreshness from "@/components/DataFreshness";
import { pickMeta, marketDataQueryOptions } from "@/lib/marketData";

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

function sentimentConfig(s: string, isDark: boolean) {
  if (s === "bullish") return {
    border: "#22c55e",
    glow: "rgba(34,197,94,0.18)",
    bg: isDark ? "rgba(34,197,94,0.06)" : "rgba(34,197,94,0.07)",
    chip: isDark ? "rgba(34,197,94,0.12)" : "rgba(34,197,94,0.1)",
    chipBorder: isDark ? "rgba(34,197,94,0.22)" : "rgba(34,197,94,0.3)",
    text: isDark ? "#4ade80" : "#16a34a",
    Icon: TrendingUp,
    label: "Bullish",
  };
  if (s === "bearish") return {
    border: "#ef4444",
    glow: "rgba(239,68,68,0.18)",
    bg: isDark ? "rgba(239,68,68,0.06)" : "rgba(239,68,68,0.05)",
    chip: isDark ? "rgba(239,68,68,0.12)" : "rgba(239,68,68,0.08)",
    chipBorder: isDark ? "rgba(239,68,68,0.22)" : "rgba(239,68,68,0.25)",
    text: isDark ? "#f87171" : "#dc2626",
    Icon: TrendingDown,
    label: "Bearish",
  };
  return {
    border: isDark ? "#334155" : "#cbd5e1",
    glow: "rgba(99,102,241,0.06)",
    bg: isDark ? "rgba(15,30,55,0.4)" : "rgba(100,116,139,0.05)",
    chip: isDark ? "rgba(100,116,139,0.12)" : "rgba(100,116,139,0.08)",
    chipBorder: isDark ? "rgba(100,116,139,0.2)" : "rgba(100,116,139,0.2)",
    text: isDark ? "#64748b" : "#475569",
    Icon: Minus,
    label: "Neutral",
  };
}

const CATEGORY_META: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  all:       { label: "All News",  icon: <Newspaper className="w-3.5 h-3.5" />,  color: "#6366f1" },
  market:    { label: "Market",    icon: <BarChart2 className="w-3.5 h-3.5" />,  color: "#0891b2" },
  corporate: { label: "Companies", icon: <Building2 className="w-3.5 h-3.5" />,  color: "#7c3aed" },
  general:   { label: "General",   icon: <Zap       className="w-3.5 h-3.5" />,  color: "#ea580c" },
};

// ── Ticker Banner ─────────────────────────────────────────────────────────────

function TickerBanner({ articles, isDark }: { articles: NewsArticle[]; isDark: boolean }) {
  const headlines = articles.slice(0, 12).map(a => a.title);
  if (!headlines.length) return null;
  const text = headlines.join("   ·   ");
  return (
    <div className="relative overflow-hidden flex items-center gap-0 rounded-2xl" style={{
      background: isDark ? "linear-gradient(90deg,#0e1829 0%,#0a1020 100%)" : "#ffffff",
      border: isDark ? "1px solid #162244" : "1px solid #e2e8f0",
      borderLeft: isDark ? "1px solid #162244" : "4px solid #6366f1",
      minHeight: 44,
    }}>
      {/* LIVE badge */}
      <div className="flex items-center gap-2 px-4 py-2.5 shrink-0 border-r" style={{
        borderColor: isDark ? "#162244" : "#e2e8f0",
        background: isDark ? "rgba(99,102,241,0.1)" : "#eef2ff",
      }}>
        <span className="relative flex h-2.5 w-2.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-60" />
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500" />
        </span>
        <span className="text-xs font-black tracking-widest uppercase" style={{ color: isDark ? "#ffffff" : "#4338ca" }}>Live</span>
      </div>
      {/* Scroll text */}
      <div className="overflow-hidden flex-1 px-4">
        <div className="whitespace-nowrap text-xs font-medium" style={{ color: isDark ? "#94a3b8" : "#475569", animation: "tickerScroll 60s linear infinite", display: "inline-block" }}>
          {text}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{text}
        </div>
      </div>
    </div>
  );
}

// ── Market Mood Bar ───────────────────────────────────────────────────────────

function MoodBar({ bullish, bearish, neutral, mood, isDark }: { bullish: number; bearish: number; neutral: number; mood: string; isDark: boolean }) {
  const total = bullish + bearish + neutral || 1;
  const bPct = Math.round((bullish / total) * 100);
  const rPct = Math.round((bearish / total) * 100);
  const nPct = 100 - bPct - rPct;

  const moodConf = mood === "bullish"
    ? { label: "Bullish", color: "#22c55e", bg: isDark ? "rgba(34,197,94,0.12)" : "#dcfce7", border: isDark ? "rgba(34,197,94,0.25)" : "#86efac", Icon: TrendingUp }
    : mood === "bearish"
    ? { label: "Bearish", color: "#ef4444", bg: isDark ? "rgba(239,68,68,0.12)" : "#fee2e2", border: isDark ? "rgba(239,68,68,0.25)" : "#fca5a5", Icon: TrendingDown }
    : { label: "Neutral", color: isDark ? "#64748b" : "#475569", bg: isDark ? "rgba(100,116,139,0.12)" : "#f1f5f9", border: isDark ? "rgba(100,116,139,0.2)" : "#cbd5e1", Icon: Minus };

  return (
    <div className="rounded-2xl p-4" style={{
      background: isDark ? "#0a1020" : "#ffffff",
      border: isDark ? "1px solid #162244" : "1px solid #e2e8f0",
    }}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-lg" style={{ background: isDark ? "rgba(99,102,241,0.12)" : "#eef2ff", border: isDark ? "1px solid rgba(99,102,241,0.2)" : "1px solid #c7d2fe" }}>
            <Radio className="w-3.5 h-3.5" style={{ color: "#818cf8" }} />
          </div>
          <span className="text-sm font-semibold" style={{ color: isDark ? "#e2e8f0" : "#1e293b" }}>Market Mood Sensor</span>
        </div>
        <div className="flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-full" style={{ background: moodConf.bg, color: moodConf.color, border: `1px solid ${moodConf.border}` }}>
          <moodConf.Icon className="w-3 h-3" />{moodConf.label}
        </div>
      </div>

      <div className="h-3 rounded-full overflow-hidden flex gap-0.5" style={{ background: isDark ? "#162244" : "#f1f5f9" }}>
        <div style={{ width: `${bPct}%`, background: "linear-gradient(90deg,#15803d,#22c55e)", transition: "width 1s ease", borderRadius: "6px 0 0 6px" }} />
        <div style={{ width: `${nPct}%`, background: isDark ? "#1e3a5f" : "#cbd5e1", transition: "width 1s ease" }} />
        <div style={{ width: `${rPct}%`, background: "linear-gradient(90deg,#ef4444,#b91c1c)", transition: "width 1s ease", borderRadius: "0 6px 6px 0" }} />
      </div>

      <div className="flex justify-between mt-3 text-xs" style={{ color: isDark ? "#4a6080" : "#64748b" }}>
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-green-500 inline-block" />{bPct}% Bullish</span>
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full inline-block" style={{ background: isDark ? "#1e3a5f" : "#94a3b8" }} />{nPct}% Neutral</span>
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-red-500 inline-block" />{rPct}% Bearish</span>
      </div>
    </div>
  );
}

// ── News Card ─────────────────────────────────────────────────────────────────

function NewsCard({ article, index, isDark }: { article: NewsArticle; index: number; isDark: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const s = sentimentConfig(article.sentiment, isDark);

  return (
    <div
      className="rounded-2xl overflow-hidden cursor-pointer group transition-all duration-200"
      style={{
        background: s.bg,
        border: `1px solid ${s.border}30`,
        borderLeft: `4px solid ${s.border}`,
        boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
        animationDelay: `${index * 40}ms`,
      }}
      onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = `0 4px 24px ${s.glow}, 0 1px 3px rgba(0,0,0,0.3)`; (e.currentTarget as HTMLDivElement).style.transform = "translateY(-1px)"; }}
      onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.boxShadow = "0 1px 3px rgba(0,0,0,0.3)"; (e.currentTarget as HTMLDivElement).style.transform = "translateY(0)"; }}
      onClick={() => setExpanded(v => !v)}
    >
      <div className="p-4">
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            {/* Meta row */}
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <span className="text-xs font-black px-2.5 py-1 rounded-lg text-white" style={{ background: article.sourceColor }}>
                {article.sourceShort}
              </span>
              <span className="flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-lg" style={{ background: s.chip, color: s.text, border: `1px solid ${s.chipBorder}` }}>
                <s.Icon className="w-3 h-3" />{s.label}
              </span>
              <span className="flex items-center gap-1 text-xs" style={{ color: isDark ? "#4a6080" : "#94a3b8" }}>
                <Clock className="w-3 h-3" />{timeAgo(article.published)}
              </span>
            </div>

            {/* Title */}
            <p className="text-sm font-semibold leading-snug" style={{ color: isDark ? "#dde8f8" : "#0f172a" }}>
              {article.title}
            </p>

            {/* Summary */}
            {expanded && article.summary && (
              <p className="text-xs mt-2.5 leading-relaxed" style={{ color: isDark ? "#4a6080" : "#64748b" }}>
                {article.summary}
              </p>
            )}

            {/* Tickers */}
            {article.tickers.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2.5">
                {article.tickers.map(t => (
                  <Link key={t} href={`/stocks?q=${t}`} onClick={e => e.stopPropagation()}>
                    <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-md cursor-pointer hover:opacity-80 transition-opacity" style={{ background: "rgba(99,102,241,0.12)", color: "#818cf8", border: "1px solid rgba(99,102,241,0.2)" }}>
                      {t}
                    </span>
                  </Link>
                ))}
              </div>
            )}
          </div>

          {/* Right actions */}
          <div className="flex flex-col items-end gap-2.5 shrink-0">
            <a href={article.url} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}
              className="p-1.5 rounded-lg transition-all opacity-50 group-hover:opacity-100"
              style={{ color: "#818cf8" }}>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
            <span style={{ color: isDark ? "#334155" : "#94a3b8" }}>
              {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Loading Skeletons ─────────────────────────────────────────────────────────

function LoadingCards({ isDark }: { isDark: boolean }) {
  return (
    <div className="space-y-3">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="h-20 rounded-2xl" style={{
          background: isDark ? "linear-gradient(90deg,#0a1020 25%,#0e1829 50%,#0a1020 75%)" : "linear-gradient(90deg,#f1f5f9 25%,#e2e8f0 50%,#f1f5f9 75%)",
          backgroundSize: "200% 100%",
          animation: `shimmer 1.5s infinite ${i * 0.1}s`,
          borderLeft: isDark ? "4px solid #162244" : "4px solid #c7d2fe",
          border: isDark ? "1px solid #162244" : "1px solid #e2e8f0",
        }} />
      ))}
    </div>
  );
}

// ── Section Loader ────────────────────────────────────────────────────────────

function SectionLoader({ active }: { active: boolean }) {
  if (!active) return null;
  return (
    <span style={{
      position: "absolute", top: 10, right: 10,
      width: 14, height: 14,
      border: "2.5px solid #6366f1",
      borderTopColor: "transparent",
      borderRadius: "50%",
      display: "inline-block",
      animation: "spin 0.75s linear infinite",
      zIndex: 2,
    }} />
  );
}

// ── Refresh Countdown ─────────────────────────────────────────────────────────

function RefreshCountdown({ seconds, onRefresh, isRefreshing, isDark }: { seconds: number; onRefresh: () => void; isRefreshing: boolean; isDark: boolean }) {
  const pct = (seconds / (8 * 60)) * 100;
  return (
    <button
      onClick={onRefresh}
      disabled={isRefreshing}
      className="flex items-center gap-2 text-xs px-3 py-2 rounded-xl transition-all disabled:opacity-60"
      style={{ background: isDark ? "#0a1020" : "#f8fafc", color: isDark ? "#4a6080" : "#64748b", border: isDark ? "1px solid #162244" : "1px solid #e2e8f0" }}
      title={isRefreshing ? "Refreshing…" : `Auto-refresh in ${Math.floor(seconds / 60)}m ${seconds % 60}s`}
    >
      <RefreshCw className="w-3.5 h-3.5" style={{ animation: isRefreshing ? "spin 0.7s linear infinite" : "none", color: isRefreshing ? "#818cf8" : undefined }} />
      <span>{isRefreshing ? "Refreshing…" : "Refresh"}</span>
      {!isRefreshing && (
        <div className="w-8 h-1 rounded-full overflow-hidden" style={{ background: "#162244" }}>
          <div className="h-full rounded-full transition-all duration-1000" style={{ width: `${pct}%`, background: "linear-gradient(90deg,#6366f1,#818cf8)" }} />
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
  const pool = REEL_PHOTO_POOLS[article.category]?.[article.sentiment] ?? REEL_PHOTO_POOLS.market.neutral;
  const n = Math.abs(parseInt(article.id.replace(/\D/g, "").slice(0, 6) || "1", 10));
  const id = pool[n % pool.length];
  return `https://picsum.photos/id/${id}/800/500`;
}

function preloadImages(urls: string[]) {
  urls.forEach(src => {
    if (!src) return;
    const img = new window.Image();
    img.src = src;
  });
}

function ReelsView({ articles, onClose, onLoadMore, loadingMore }: {
  articles: NewsArticle[];
  onClose: () => void;
  onLoadMore?: () => void;
  loadingMore?: boolean;
}) {
  const [current, setCurrent] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);

  const goTo = useCallback((idx: number) => {
    const clamped = Math.max(0, Math.min(idx, articles.length - 1));
    setCurrent(clamped);
    cardRefs.current[clamped]?.scrollIntoView({ behavior: "smooth", block: "start" });
    // Trigger load-more when within 3 reels of the end
    if (idx >= articles.length - 3 && onLoadMore && !loadingMore) {
      onLoadMore();
    }
  }, [articles.length, onLoadMore, loadingMore]);

  useEffect(() => {
    const urls = articles.slice(current, current + 5).map(a => a.image_url || getFallbackImageUrl(a));
    preloadImages(urls);
  }, [current, articles]);

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
          const s = sentimentConfig(article.sentiment);
          return (
            <div
              key={article.id}
              ref={el => { cardRefs.current[i] = el; }}
              className="relative flex flex-col overflow-hidden"
              style={{ height: "100%", scrollSnapAlign: "start", flexShrink: 0, background: getReelGradient(article) }}
            >
              <img src={imgSrc} alt="" aria-hidden
                className="absolute inset-0 w-full h-full object-cover"
                style={{ zIndex: 0, opacity: 0, transition: "opacity 0.4s ease" }}
                onLoad={e => { e.currentTarget.style.opacity = "1"; }}
                onError={e => {
                  const el = e.currentTarget;
                  if (el.src !== fallbackSrc) { el.src = fallbackSrc; } else { el.style.display = "none"; }
                }}
              />
              <div className="absolute inset-0 pointer-events-none" style={{ zIndex: 1,
                background: "linear-gradient(to bottom, rgba(0,0,0,0.25) 0%, rgba(0,0,0,0.45) 35%, rgba(0,0,0,0.82) 70%, rgba(0,0,0,0.95) 100%)" }} />
              <div className="absolute inset-0 pointer-events-none overflow-hidden" style={{ zIndex: 1 }}>
                <div style={{ position: "absolute", top: "-15%", right: "-8%", width: "55%", height: "55%", borderRadius: "50%",
                  background: `radial-gradient(circle, ${orb1} 0%, transparent 70%)`, filter: "blur(50px)", opacity: 0.5 }} />
                <div style={{ position: "absolute", bottom: "-10%", left: "-8%", width: "50%", height: "50%", borderRadius: "50%",
                  background: `radial-gradient(circle, ${orb2} 0%, transparent 70%)`, filter: "blur(45px)", opacity: 0.5 }} />
              </div>

              <div className="relative z-10 flex flex-col h-full px-6 pt-16 pb-5">
                <div className="flex items-center justify-between mb-6">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold px-2.5 py-1 rounded-lg text-white" style={{ background: article.sourceColor ?? "#6366f1" }}>
                      {article.sourceShort}
                    </span>
                    <span className="text-xs font-bold px-2.5 py-1 rounded-lg border" style={{ color: sent.color, background: sent.bg, borderColor: sent.color + "40" }}>
                      {sent.txt}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold px-2 py-0.5 rounded-md" style={{ color: cat.color, background: cat.color + "20" }}>{cat.txt}</span>
                  </div>
                </div>

                <div className="flex-1 flex flex-col justify-end">
                  <h2 className="text-2xl font-black leading-tight text-white mb-3 drop-shadow-lg">{article.title}</h2>
                  {article.summary && (
                    <p className="text-sm leading-relaxed mb-4" style={{ color: "rgba(255,255,255,0.7)" }}>{article.summary}</p>
                  )}
                  {article.tickers.length > 0 && (
                    <div className="flex flex-wrap gap-2 mb-4">
                      {article.tickers.map(t => (
                        <span key={t} className="text-xs font-mono font-bold px-2.5 py-1 rounded-lg text-white" style={{ background: "rgba(255,255,255,0.12)", border: "1px solid rgba(255,255,255,0.2)" }}>{t}</span>
                      ))}
                    </div>
                  )}
                  <div className="flex items-center gap-3">
                    {i > 0 && (
                      <button onClick={() => goTo(i - 1)} className="flex items-center gap-1 text-xs text-white/60 hover:text-white transition px-3 py-1.5 rounded-lg" style={{ background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.12)" }}>
                        <ChevronUp className="w-3.5 h-3.5" /> Prev
                      </button>
                    )}
                    <a href={article.url} target="_blank" rel="noopener noreferrer"
                      className="flex items-center gap-1.5 text-sm font-semibold px-4 py-1.5 rounded-xl text-white hover:opacity-90 active:scale-95 transition"
                      style={{ background: "rgba(255,255,255,0.14)", backdropFilter: "blur(8px)", border: "1px solid rgba(255,255,255,0.22)" }}>
                      Read Full Story <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                    {i < articles.length - 1 && (
                      <button onClick={() => goTo(i + 1)} className="flex items-center gap-1 text-xs text-white/60 hover:text-white transition px-3 py-1.5 rounded-lg" style={{ background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.12)" }}>
                        Next <ChevronDown className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>

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

type Tab = "all" | "market" | "corporate" | "general";
const TABS: Tab[] = ["all", "market", "corporate", "general"];

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

  // ── Infinite scroll state ─────────────────────────────────────────────────
  const PAGE_SIZE = 25;
  const [allArticles, setAllArticles] = useState<import("@/lib/api").NewsArticle[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const sentinelRef = useRef<HTMLDivElement>(null);
  // Track which feed context the accumulated list belongs to (tab+search)
  const feedContextRef = useRef("");

  // Light-mode palette (dark mode uses the same rich values defined inline)
  const bg          = isDark ? "#04091a" : "#f1f5f9";
  const cardBg      = isDark ? "#0a1020" : "#ffffff";
  const borderCol   = isDark ? "#162244" : "#e2e8f0";
  const hdrTxt      = isDark ? "#e2e8f0" : "#0f172a";
  const muTxt       = isDark ? "#4a6080" : "#64748b";
  const inputBg     = isDark ? "#0a1020" : "#ffffff";

  const { data: feed, isLoading: feedLoading, isFetching: feedFetching } = useQuery(
    marketDataQueryOptions(
      ["newsFeed", activeTab, debouncedSearch],
      () => api.newsFeed({ category: activeTab, search: debouncedSearch, limit: PAGE_SIZE, offset: 0 }),
      { placeholderData: keepPreviousData },
    ),
  );

  // Reset accumulated list whenever the first page of a new tab/search arrives
  useEffect(() => {
    if (!feed) return;
    const ctx = `${activeTab}:${debouncedSearch}`;
    feedContextRef.current = ctx;
    setAllArticles(feed.articles ?? []);
    setHasMore((feed.articles?.length ?? 0) >= PAGE_SIZE);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feed]);

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const ctx = feedContextRef.current;
      const res = await api.newsFeed({
        category: activeTab,
        search: debouncedSearch,
        limit: PAGE_SIZE,
        offset: allArticles.length,
      });
      // Discard results if the user switched tab/search mid-flight
      if (feedContextRef.current !== ctx) return;
      const next = res.articles ?? [];
      setAllArticles(prev => {
        const seen = new Set(prev.map(a => a.id));
        return [...prev, ...next.filter(a => !seen.has(a.id))];
      });
      setHasMore(next.length >= PAGE_SIZE);
    } catch {
      setHasMore(false);
    } finally {
      setLoadingMore(false);
    }
  }, [loadingMore, hasMore, allArticles.length, activeTab, debouncedSearch]);

  // IntersectionObserver — fires loadMore when sentinel scrolls into view
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      entries => { if (entries[0].isIntersecting) loadMore(); },
      { threshold: 0.1 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [loadMore]);

  const { data: stats, isFetching: statsFetching } = useQuery({
    queryKey: ["newsStats"],
    queryFn:  api.newsStats,
    staleTime: 0,
    refetchOnMount: "always",
    placeholderData: keepPreviousData,
  });

  const refreshMutation = useMutation({ mutationFn: api.newsRefresh });

  const refreshFnRef = useRef<() => void>(() => {});
  refreshFnRef.current = useCallback(() => {
    refreshMutation.mutate(undefined, {
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["newsFeed"] });
        qc.invalidateQueries({ queryKey: ["newsStats"] });
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
  }, []);

  useEffect(() => {
    clearTimeout(debounceRef.current ?? undefined);
    debounceRef.current = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(debounceRef.current ?? undefined);
  }, [search]);

  const articles = allArticles;
  const feedMeta = pickMeta(feed);

  const sourceStats = useMemo(() => {
    const s = stats?.sources ?? {};
    return Object.entries(s).map(([k, v]) => ({ name: k, count: v as number })).sort((a, b) => b.count - a.count);
  }, [stats]);

  // Live sentiment counts derived from the currently-loaded articles.
  // These grow as the user scrolls and more pages are appended.
  const liveSentiments = useMemo(() => {
    const counts = { bullish: 0, bearish: 0, neutral: 0 };
    for (const a of allArticles) {
      const s = (a.sentiment ?? "neutral") as keyof typeof counts;
      if (s in counts) counts[s]++; else counts.neutral++;
    }
    const total = allArticles.length;
    const margin = Math.abs(counts.bullish - counts.bearish);
    const mood: "bullish" | "bearish" | "neutral" =
      total >= 5 && margin / total >= 0.10
        ? counts.bullish > counts.bearish ? "bullish" : "bearish"
        : "neutral";
    return { ...counts, total, mood };
  }, [allArticles]);

  return (
    <div className="space-y-4 min-h-screen" style={{ background: bg }}>
      <style>{`
        @keyframes tickerScroll {
          0%   { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        @keyframes slideIn {
          from { opacity: 0; transform: translateY(10px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        @keyframes shimmer {
          0%   { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
        .news-card-enter {
          animation: slideIn 0.3s ease forwards;
        }
      `}</style>

      {/* ── Header ─────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-black flex items-center gap-2.5" style={{ color: hdrTxt }}>
            <div className="p-1.5 rounded-xl" style={{ background: isDark ? "rgba(99,102,241,0.12)" : "#eef2ff", border: isDark ? "1px solid rgba(99,102,241,0.2)" : "1px solid #c7d2fe" }}>
              <Newspaper className="w-5 h-5" style={{ color: "#818cf8" }} />
            </div>
            <span style={isDark ? { background: "linear-gradient(90deg,#c7d2fe,#a5b4fc)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" } : {}}>
              Market News Feed
            </span>
          </h1>
          <p className="text-sm mt-1 ml-10" style={{ color: muTxt }}>
            Live headlines from ET · Livemint · Moneycontrol · Yahoo Finance · ScanX
          </p>
        </div>
        <div className="flex items-center gap-2">
          <DataFreshness meta={feedMeta} hideRefresh />
          <RefreshCountdown seconds={countdown} onRefresh={handleRefresh} isRefreshing={refreshMutation.isPending} isDark={isDark} />
        </div>
      </div>

      {/* ── Live ticker ─────────────────────────────────────────────── */}
      {articles.length > 0 && <TickerBanner articles={articles} isDark={isDark} />}

      {/* ── Stats row ───────────────────────────────────────────────── */}
      {(feedLoading || liveSentiments.total > 0 || stats) && (
        <div className="relative grid grid-cols-2 md:grid-cols-4 gap-3">
          <SectionLoader active={statsFetching} />

          {/* Total — grows with each page loaded */}
          <div className="rounded-2xl p-4" style={{ background: cardBg, borderTop: "3px solid #6366f1", borderRight: `1px solid ${borderCol}`, borderBottom: `1px solid ${borderCol}`, borderLeft: `1px solid ${borderCol}` }}>
            <div className="text-xs font-medium mb-1" style={{ color: muTxt }}>Total Articles</div>
            <div className="text-2xl font-black" style={{ color: isDark ? "#c7d2fe" : "#4f46e5" }}>
              {liveSentiments.total}
              {hasMore && <span className="text-sm font-normal ml-1 opacity-50">+</span>}
            </div>
          </div>

          {/* Bullish */}
          <div className="rounded-2xl p-4" style={{ background: isDark ? "rgba(34,197,94,0.05)" : "#f0fdf4", borderTop: "3px solid #22c55e", borderRight: `1px solid ${isDark ? "rgba(34,197,94,0.15)" : "#bbf7d0"}`, borderBottom: `1px solid ${isDark ? "rgba(34,197,94,0.15)" : "#bbf7d0"}`, borderLeft: `1px solid ${isDark ? "rgba(34,197,94,0.15)" : "#bbf7d0"}` }}>
            <div className="text-xs font-medium mb-1" style={{ color: muTxt }}>Bullish Signals</div>
            <div className="text-2xl font-black text-green-500">{liveSentiments.bullish}</div>
          </div>

          {/* Bearish */}
          <div className="rounded-2xl p-4" style={{ background: isDark ? "rgba(239,68,68,0.05)" : "#fef2f2", borderTop: "3px solid #ef4444", borderRight: `1px solid ${isDark ? "rgba(239,68,68,0.15)" : "#fecaca"}`, borderBottom: `1px solid ${isDark ? "rgba(239,68,68,0.15)" : "#fecaca"}`, borderLeft: `1px solid ${isDark ? "rgba(239,68,68,0.15)" : "#fecaca"}` }}>
            <div className="text-xs font-medium mb-1" style={{ color: muTxt }}>Bearish Signals</div>
            <div className="text-2xl font-black text-red-500">{liveSentiments.bearish}</div>
          </div>

          {/* Sources */}
          <div className="rounded-2xl p-4" style={{ background: cardBg, borderTop: "3px solid #7c3aed", borderRight: `1px solid ${borderCol}`, borderBottom: `1px solid ${borderCol}`, borderLeft: `1px solid ${borderCol}` }}>
            <div className="text-xs font-medium mb-2" style={{ color: muTxt }}>Sources</div>
            <div className="flex flex-wrap gap-1">
              {sourceStats.map(s => (
                <span key={s.name} className="text-xs px-2 py-0.5 rounded-lg font-mono font-semibold"
                  style={{ background: isDark ? "rgba(99,102,241,0.12)" : "#eef2ff", color: isDark ? "#818cf8" : "#4f46e5", border: isDark ? "1px solid rgba(99,102,241,0.2)" : "1px solid #c7d2fe" }}>
                  {s.name === "YF" ? "Yahoo Finance" : s.name} {s.count}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Mood bar ─ also driven by live counts ───────────────────── */}
      {liveSentiments.total > 0 && (
        <div className="relative">
          <SectionLoader active={statsFetching} />
          <MoodBar
            bullish={liveSentiments.bullish}
            bearish={liveSentiments.bearish}
            neutral={liveSentiments.neutral}
            mood={liveSentiments.mood}
            isDark={isDark}
          />
        </div>
      )}

      {/* ── Tabs ────────────────────────────────────────────────────── */}
      <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-hide">
        {TABS.map(tab => {
          const meta = CATEGORY_META[tab];
          const isActive = activeTab === tab;
          return (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold whitespace-nowrap transition-all duration-150 shrink-0"
              style={{
                background: isActive ? meta.color : isDark ? "#0a1020" : "#fff",
                color:      isActive ? "#fff" : muTxt,
                border:     `1px solid ${isActive ? meta.color : borderCol}`,
                boxShadow:  isActive ? `0 0 0 3px ${meta.color}25, 0 2px 8px ${meta.color}30` : "none",
              }}
            >
              {meta.icon}
              {meta.label}
            </button>
          );
        })}
      </div>

      {/* ── Search + view toggle ────────────────────────────────────── */}
      {!reelsMode && (
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: muTxt }} />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search headlines, companies, sectors…"
              className="w-full pl-10 pr-4 py-2.5 rounded-xl text-sm outline-none transition-all"
              style={{
                background: inputBg,
                border: `1.5px solid ${search ? "#6366f1" : borderCol}`,
                color: hdrTxt,
                boxShadow: search ? "0 0 0 3px rgba(99,102,241,0.1)" : "none",
              }}
            />
            {search && (
              <button className="absolute right-3 top-1/2 -translate-y-1/2" style={{ color: muTxt }} onClick={() => setSearch("")}>
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
          <button
            onClick={() => setReelsMode(r => !r)}
            title={reelsMode ? "Switch to list view" : "Switch to reels view"}
            className="flex items-center gap-1.5 text-xs font-semibold px-4 py-2.5 rounded-xl transition-all shrink-0"
            style={{
              background: isDark ? "#0a1020" : "#fff",
              color:      muTxt,
              border:     `1.5px solid ${borderCol}`,
            }}
          >
            <Film className="w-3.5 h-3.5" />Reels
          </button>
        </div>
      )}

      {/* ── Content ─────────────────────────────────────────────────── */}
      {reelsMode && articles.length > 0 ? (
        <ReelsView
          articles={articles}
          onClose={() => setReelsMode(false)}
          onLoadMore={hasMore ? loadMore : undefined}
          loadingMore={loadingMore}
        />
      ) : reelsMode && feedLoading ? (
        <div className="flex flex-col items-center justify-center py-24 gap-3" style={{ color: muTxt }}>
          <Film className="w-10 h-10 opacity-30" />
          <p className="text-sm">Loading reels…</p>
        </div>
      ) : feedLoading ? (
        <LoadingCards isDark={isDark} />
      ) : articles.length === 0 ? (
        <div className="text-center py-16" style={{ color: muTxt }}>
          <Newspaper className="w-12 h-12 mx-auto mb-3 opacity-20" />
          <p className="font-semibold">No articles found</p>
          <p className="text-sm mt-1 opacity-70">{search ? "Try a different search term" : "Check back soon"}</p>
        </div>
      ) : (
        <div className="relative space-y-2.5">
          <SectionLoader active={feedFetching && !feedLoading} />
          {articles.map((article, i) => (
            <div key={article.id} className="news-card-enter" style={{ animationDelay: `${Math.min(i * 30, 400)}ms` }}>
              <NewsCard article={article} index={i} isDark={isDark} />
            </div>
          ))}
          {/* Infinite scroll sentinel — becomes visible when near the bottom */}
          {hasMore && !loadingMore && (
            <div ref={sentinelRef} style={{ height: 1 }} />
          )}
          {/* Skeleton cards while the next page loads */}
          {loadingMore && <LoadingCards isDark={isDark} />}
          {!hasMore && articles.length > 0 && (
            <p className="text-center text-xs py-4" style={{ color: muTxt }}>
              {articles.length} articles loaded · Auto-refreshes every 8 minutes
            </p>
          )}
        </div>
      )}
    </div>
  );
}
