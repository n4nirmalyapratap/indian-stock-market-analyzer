/**
 * <TickerNewsPanel> — "Latest news" panel scoped to a single stock.
 *
 * Hits GET /api/news/ticker?symbol=... which returns RSS feed matches plus a
 * Tavily top-up when RSS coverage is thin (Tavily is gated on
 * TAVILY_API_KEY — if unset the backend silently sticks to RSS).
 *
 * Used on:
 *   - StockLookup
 *   - AIAnalyst (compact mode)
 *
 * Fails open: if the API errors, the panel collapses to a short "couldn't
 * load" message rather than blocking the page.
 */
import { useEffect, useState } from "react";
import { ExternalLink, Loader2, Newspaper, AlertCircle, Sparkles } from "lucide-react";
import { api } from "@/lib/api";

type Article = {
  title:    string;
  summary?: string;
  url:      string;
  source:   string;
  published?: string;
  category?: string;
  sentiment?: string | null;
  image?:    string | null;
  via?:      string;          // "tavily" or undefined for RSS
};

type Props = {
  symbol:   string;
  /** How many articles to fetch from the backend (max 50). */
  limit?:   number;
  /** Compact mode = no padding, tighter rows. Used in dense layouts. */
  compact?: boolean;
  /** Optional title override. Defaults to "Latest news". */
  title?:   string;
  className?: string;
};

function relTimeFromIso(iso?: string): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "";
  const diff = Date.now() - t;
  const s = Math.floor(diff / 1000);
  if (s < 60)    return `${Math.max(1, s)}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60)    return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24)    return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

function sentimentDot(s?: string | null): { cls: string; label: string } | null {
  if (!s) return null;
  const norm = s.toLowerCase();
  if (norm.includes("positive") || norm === "bullish")
    return { cls: "bg-emerald-500", label: "Positive" };
  if (norm.includes("negative") || norm === "bearish")
    return { cls: "bg-rose-500",    label: "Negative" };
  return { cls: "bg-slate-400", label: "Neutral" };
}

export default function TickerNewsPanel({
  symbol, limit = 20, compact, title = "Latest news", className = "",
}: Props) {
  const [articles, setArticles] = useState<Article[]>([]);
  const [sourceLabel, setSourceLabel] = useState<string>("");
  const [tavilyUsed, setTavilyUsed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    if (!symbol) {
      setArticles([]);
      return;
    }
    let alive = true;
    setLoading(true);
    setError("");
    api.tickerNews(symbol, limit)
      .then(res => {
        if (!alive) return;
        setArticles(res.articles || []);
        setSourceLabel(res.source || "");
        setTavilyUsed(!!res.tavilyUsed);
      })
      .catch((e: Error) => { if (alive) setError(e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [symbol, limit]);

  const padding = compact ? "p-3" : "p-4";

  return (
    <section className={`bg-white dark:bg-gray-900 border border-gray-200 dark:border-white/10 rounded-xl ${padding} ${className}`}>
      <header className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-800 dark:text-gray-200 flex items-center gap-1.5">
          <Newspaper className="w-4 h-4 text-indigo-500" />
          {title}
          {symbol && <span className="font-mono text-gray-400 ml-1">· {symbol}</span>}
        </h3>
        {tavilyUsed && (
          <span
            className="text-[10px] uppercase tracking-wide text-indigo-600 dark:text-indigo-300 bg-indigo-50 dark:bg-indigo-900/30 px-1.5 py-0.5 rounded inline-flex items-center gap-1"
            title="Coverage was thin; Tavily search was used to top up."
          >
            <Sparkles className="w-3 h-3" /> Tavily
          </span>
        )}
      </header>

      {loading && (
        <div className="flex items-center gap-2 text-xs text-gray-400 py-6 justify-center">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading news…
        </div>
      )}

      {error && !loading && (
        <div className="flex items-start gap-1.5 text-xs text-amber-700 dark:text-amber-300 py-3">
          <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
          <span>Couldn't load news for {symbol}. ({error})</span>
        </div>
      )}

      {!loading && !error && articles.length === 0 && (
        <p className="text-xs text-gray-400 py-3">
          No recent news found for {symbol}.
        </p>
      )}

      <ul className="divide-y divide-gray-100 dark:divide-white/5">
        {articles.map((a, i) => {
          const dot = sentimentDot(a.sentiment);
          return (
            <li key={`${a.url}-${i}`} className="py-2">
              <a href={a.url} target="_blank" rel="noopener noreferrer"
                 className="block group">
                <div className="flex items-start gap-2">
                  {dot && (
                    <span
                      title={dot.label}
                      className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${dot.cls}`}
                    />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-gray-900 dark:text-gray-100 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 leading-snug">
                      {a.title}
                      <ExternalLink className="w-3 h-3 inline ml-1 text-gray-300 group-hover:text-indigo-400" />
                    </p>
                    <div className="text-[10px] text-gray-400 mt-0.5 flex flex-wrap items-center gap-x-1.5">
                      <span>{a.source}</span>
                      {a.published && (
                        <>
                          <span>·</span>
                          <span title={a.published}>{relTimeFromIso(a.published)}</span>
                        </>
                      )}
                      {a.via === "tavily" && (
                        <span className="text-indigo-500/70" title="From Tavily search">· via Tavily</span>
                      )}
                    </div>
                  </div>
                </div>
              </a>
            </li>
          );
        })}
      </ul>

      {!loading && !error && articles.length > 0 && sourceLabel && (
        <p className="text-[10px] text-gray-400 mt-2 pt-2 border-t border-gray-100 dark:border-white/5">
          Source: {sourceLabel}
        </p>
      )}
    </section>
  );
}
