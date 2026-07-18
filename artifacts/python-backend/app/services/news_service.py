"""
News & Market Updates Service
Aggregates RSS feeds (ET, Livemint, Moneycontrol) + ScanX Google-News sitemap
+ NSE bulk/block deals + corporate events.

Audit 2026-05 (data honesty pass, parallel to Sentiment dashboard):
  * Sentiment classifier moved from a naive bag-of-words to VADER (same
    library the rest of the app uses in `hydra_sentiment_service`). The
    old classifier mis-labelled headlines like "Gold under pressure on
    soaring crude prices, hawkish central banks" as bullish.
  * Per-source health is now surfaced. RSS feed failures used to be
    swallowed silently; now `/news/feed` returns a `sources` array with
    {name, ok, count, error} so the UI can show "Mint feed unavailable".
  * `cached` flag now reflects whether the response came from cache
    (was always True after the function populated the cache).
  * `refreshedAt` now reflects the cache fill time (was always now()).
    A separate `fetchedAt` field gives the wall-clock time of the call.
  * Articles without a publication date are flagged `undated: true` and
    sorted *after* dated entries, so undated items don't masquerade as
    fresh.
  * `/news/deals` and `/news/events` now expose an `available: bool`.
  * New source: ScanX (`scanx.trade`). Their `robots.txt` explicitly
    allows all paths, and they publish a Google-News-format sitemap at
    `sitemap-stock-market-news.xml` — the documented public discovery
    mechanism. We parse it with `feedparser` (sitemap mode) and only
    keep entries from the last 3 days to avoid stale items.

Audit 2026-07 (sentiment accuracy pass):
  * Sentiment labels are now produced by the app's LLM stack
    (`news_sentiment_llm` → ai_client Groq/OpenRouter cascade) in
    batched, cached calls. VADER — which scored 53% on a battery of
    typical Indian financial headlines and inverted classics like
    "investors book profits" (→ bullish) and "upgrades to overweight"
    (→ bearish) — remains only as the fallback when no AI provider is
    reachable. Every article carries `sentimentVia: "llm" | "vader" |
    "none"` so consumers can tell which classifier labelled it.
  * Tavily top-up articles (previously `sentiment: None`) are classified
    too, so the tri-factor sentiment leg counts them.
"""
import asyncio
import logging
import time
import re
import html
from datetime import datetime, timezone, timedelta
from typing import Optional

import feedparser
import httpx
from xml.etree import ElementTree as ET

from .hydra_sentiment_service import _get_vader

logger = logging.getLogger(__name__)

# ── In-memory cache ───────────────────────────────────────────────────────────

_CACHE: dict[str, dict] = {}
_CACHE_TTL = {
    "feed":   8 * 60,    # 8 minutes for RSS news
    "deals":  30 * 60,   # 30 minutes for deals
    "events": 15 * 60,   # 15 minutes for NSE events
    # Per-ticker Tavily top-up — short TTL so repeated searches for the same
    # symbol in the news feed don't hammer the Tavily API, but the user still
    # gets fresh stories within 5 minutes of new coverage being published.
    "ticker": 5 * 60,
}


def _looks_like_ticker(s: str) -> bool:
    """Cheap heuristic: 2-15 uppercase chars (after stripping common suffixes)
    looks like an NSE ticker. We use it to decide whether a free-text search
    query is worth firing a Tavily call for."""
    if not s:
        return False
    cleaned = s.strip().upper()
    for suffix in ("-EQ", ".NS", ".BO"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
    if not 2 <= len(cleaned) <= 15:
        return False
    return cleaned.replace("-", "").replace("&", "").isalnum() and any(
        c.isalpha() for c in cleaned
    )


def _cache_get(key: str) -> Optional[dict]:
    """Return the full cache entry (with `ts` and `data`) or None if stale."""
    entry = _CACHE.get(key)
    if entry and time.time() - entry["ts"] < _CACHE_TTL.get(key, 600):
        return entry
    return None


def _cache_set(key: str, data) -> None:
    _CACHE[key] = {"ts": time.time(), "data": data}


def _iso_from_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ── RSS Feed Sources ──────────────────────────────────────────────────────────

RSS_SOURCES = [
    {
        "name":     "Economic Times",
        "short":    "ET",
        "color":    "#1a56db",
        "category": "market",
        "url":      "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    },
    {
        "name":     "Economic Times",
        "short":    "ET",
        "color":    "#1a56db",
        "category": "general",
        "url":      "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
    },
    {
        "name":     "Livemint",
        "short":    "Mint",
        "color":    "#059669",
        "category": "market",
        "url":      "https://www.livemint.com/rss/markets",
    },
    {
        "name":     "Livemint",
        "short":    "Mint",
        "color":    "#059669",
        "category": "corporate",
        "url":      "https://www.livemint.com/rss/companies",
    },
    {
        "name":     "Moneycontrol",
        "short":    "MC",
        "color":    "#7c3aed",
        "category": "market",
        "url":      "https://www.moneycontrol.com/rss/latestnews.xml",
    },
]

# ScanX sitemap-based source. Sitemap is the documented public discovery
# mechanism (linked from robots.txt) — we are not scraping HTML.
#
# Audit note: probed all listed scanx sitemaps. `sitemap-stock-market-news.xml`
# is mostly stale (latest entries ~6 weeks old at the time of audit), while
# `sitemap-market-news.xml` is updated daily. We use the latter for live
# market coverage. 7-day window keeps the feed lively even on long
# weekends / holidays.
SCANX_SOURCE = {
    "name":            "ScanX",
    "short":           "ScanX",
    "color":           "#0ea5e9",
    "category":        "market",
    "sitemap_url":     "https://scanx.trade/sitemap-market-news.xml",
    "max_age_days":    7,
    "max_entries":     30,
}


# ── Sentiment (VADER) ─────────────────────────────────────────────────────────

# VADER compound thresholds — kept conservative so noisy headlines fall
# into "neutral" rather than being mis-labelled. The VADER docs suggest
# ±0.05 as a default; we widen to ±0.20 for financial headlines because
# stock-news lexicon overlaps heavily with VADER's mildly-positive words
# ("strong", "high", "growth") that, in financial context, carry less
# directional signal than VADER assumes.
_VADER_POS_THRESHOLD = 0.20
_VADER_NEG_THRESHOLD = -0.20


def _sentiment(text: str) -> str:
    """VADER-based sentiment classification. Falls back to neutral when
    VADER is unavailable rather than guessing with a brittle keyword list."""
    if not text:
        return "neutral"
    sia = _get_vader()
    if sia is None:
        return "neutral"
    try:
        compound = sia.polarity_scores(text).get("compound", 0.0)
    except Exception:
        return "neutral"
    if compound >= _VADER_POS_THRESHOLD:
        return "bullish"
    if compound <= _VADER_NEG_THRESHOLD:
        return "bearish"
    return "neutral"


# ── Stock Ticker Extraction ───────────────────────────────────────────────────

_KNOWN_TICKERS = {
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "KOTAKBANK", "SBIN",
    "AXISBANK", "HINDUNILVR", "ITC", "WIPRO", "BAJFINANCE", "LT", "HCLTECH",
    "ASIANPAINT", "TITAN", "ULTRACEMCO", "MARUTI", "TATAMOTORS", "SUNPHARMA",
    "DRREDDY", "CIPLA", "BHARTIARTL", "TECHM", "NESTLEIND", "POWERGRID",
    "NTPC", "ONGC", "COALINDIA", "TATASTEEL", "JSWSTEEL", "HINDALCO",
    "ADANIPORTS", "ADANIENT", "BRITANNIA", "EICHERMOT", "BAJAJFINSV",
    "ZEEL", "SUNTV", "PVRINOX", "NAZARA", "SAREGAMA", "TIPSMUSIC",
    "DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE", "VEDL", "NMDC",
    "BPCL", "GAIL", "IOC", "PETRONET", "BAJAJ-AUTO", "HEROMOTOCO",
    "M&M", "TVSMOTOR", "BOSCHLTD", "VOLTAS", "HAVELLS", "WHIRLPOOL",
    "MUTHOOTFIN", "SBILIFE", "HDFCLIFE", "ICICIGI", "ICICIPRULI",
    "DIVISLAB", "LUPIN", "AUROPHARMA", "TORNTPHARM", "BIOCON", "ALKEM",
    "APOLLOHOSP", "MAXHEALTH", "FORTIS", "METROPOLIS", "THYROCARE",
    "NIFTY", "SENSEX", "BANKNIFTY",
}


def _extract_tickers(text: str) -> list[str]:
    found = []
    words = re.findall(r"\b[A-Z][A-Z0-9&-]{1,12}\b", text)
    for w in words:
        if w in _KNOWN_TICKERS:
            found.append(w)
    return list(dict.fromkeys(found))[:5]


# ── Clean HTML ────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:400]


# ── Image Extraction ───────────────────────────────────────────────────────────

def _extract_image(entry) -> Optional[str]:
    """Extract image URL from RSS entry via media tags, enclosures, or inline HTML."""
    mt = entry.get("media_thumbnail")
    if mt and isinstance(mt, list) and mt[0].get("url"):
        return mt[0]["url"]

    mc = entry.get("media_content")
    if mc and isinstance(mc, list):
        for m in mc:
            url = m.get("url", "")
            if url and ("image" in m.get("medium", "") or "image" in m.get("type", "")):
                return url

    for enc in entry.get("enclosures", []):
        if enc.get("type", "").startswith("image/") and enc.get("href"):
            return enc["href"]

    for field in ("summary", "description", "content"):
        raw = entry.get(field, "")
        if isinstance(raw, list):
            raw = " ".join(item.get("value", "") for item in raw)
        if raw:
            m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw, re.IGNORECASE)
            if m:
                url = m.group(1)
                if url.startswith("http") and "pixel" not in url and "track" not in url and "beacon" not in url:
                    return url

    return None


# ── Time Parsing ──────────────────────────────────────────────────────────────

def _parse_published(entry) -> tuple[str, bool]:
    """Returns (iso_timestamp, undated_flag).

    Undated entries previously got `now()` which made them appear at the
    top of the feed. We now return a sentinel time and an `undated`
    flag so the UI can sort/label them honestly.
    """
    pt = entry.get("published_parsed")
    if pt:
        try:
            dt = datetime(*pt[:6], tzinfo=timezone.utc)
            return dt.isoformat(), False
        except Exception:
            pass
    # Sentinel: epoch zero so undated entries sort to the bottom by `published`,
    # but the `undated` flag is the source of truth.
    return datetime.fromtimestamp(0, tz=timezone.utc).isoformat(), True


# ── RSS Ingestion ─────────────────────────────────────────────────────────────

def _fetch_one_feed(src: dict) -> tuple[list[dict], Optional[str]]:
    """Fetch one RSS feed. Returns (articles, error_string_or_None)."""
    articles: list[dict] = []
    try:
        feed = feedparser.parse(src["url"])
        # feedparser sets `bozo` on parse errors but many real feeds also
        # set it (CDATA quirks etc.) — rely on entry presence as the
        # actual signal of success.
        if not getattr(feed, "entries", None):
            err = getattr(feed, "bozo_exception", None)
            return [], f"no entries returned ({err})" if err else "no entries returned"
        for entry in feed.entries[:15]:
            title = _clean(entry.get("title", ""))
            summary = _clean(entry.get("summary", entry.get("description", "")))
            if not title:
                continue
            combined = f"{title} {summary}"
            published, undated = _parse_published(entry)
            articles.append({
                "id":          f"{src['short']}_{hash(entry.get('link','') + title) & 0xFFFFFF:06x}",
                "title":       title,
                "summary":     summary,
                "url":         entry.get("link", "#"),
                "source":      src["name"],
                "sourceShort": src["short"],
                "sourceColor": src["color"],
                "category":    src["category"],
                "published":   published,
                "undated":     undated,
                "sentiment":   _sentiment(combined),
                "sentimentVia": "vader",
                "tickers":     _extract_tickers(combined),
                "image_url":   _extract_image(entry),
                "type":        "news",
            })
    except Exception as e:
        logger.warning("Feed %s failed: %s", src["url"], e)
        return [], str(e)
    return articles, None


# ── ScanX Sitemap Ingestion ───────────────────────────────────────────────────

# Google News sitemap namespace
_NEWS_NS = "{http://www.google.com/schemas/sitemap-news/0.9}"
_SM_NS   = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def _scanx_category_from_url(url: str) -> str:
    """Derive a category from a ScanX news URL.

    URLs look like:
      /stock-market-news/stocks/<slug>/<id>
      /stock-market-news/ipo/...
      /stock-market-news/earnings/...
      /stock-market-news/market/...
    """
    if "/ipo" in url or "/earnings" in url:
        return "corporate"
    if "/market" in url or "/global" in url:
        return "market"
    if "/bulk" in url or "/block" in url:
        return "deals"
    return "corporate"


def _fetch_scanx_sitemap() -> tuple[list[dict], Optional[str]]:
    """Pull ScanX's Google-News sitemap and convert to article dicts.
    Returns (articles, error_string_or_None)."""
    src = SCANX_SOURCE
    articles: list[dict] = []
    try:
        with httpx.Client(timeout=15.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = client.get(src["sitemap_url"])
            resp.raise_for_status()
            xml = resp.text
    except Exception as e:
        logger.warning("ScanX sitemap fetch failed: %s", e)
        return [], str(e)

    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        return [], f"sitemap parse error: {e}"

    cutoff = datetime.now(timezone.utc) - timedelta(days=src["max_age_days"])
    raw: list[tuple[datetime, str, str]] = []  # (dt, title, url)

    for url_el in root.findall(f"{_SM_NS}url"):
        loc_el   = url_el.find(f"{_SM_NS}loc")
        news_el  = url_el.find(f"{_NEWS_NS}news")
        if news_el is None or loc_el is None or not loc_el.text:
            continue
        title_el = news_el.find(f"{_NEWS_NS}title")
        date_el  = news_el.find(f"{_NEWS_NS}publication_date")
        if title_el is None or not title_el.text:
            continue

        # Date may be `YYYY-MM-DD` or full ISO 8601
        dt: Optional[datetime] = None
        if date_el is not None and date_el.text:
            txt = date_el.text.strip()
            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(txt, fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
        if dt is None or dt < cutoff:
            continue
        raw.append((dt, _clean(title_el.text), loc_el.text.strip()))

    # Newest first, then trim
    raw.sort(key=lambda x: x[0], reverse=True)
    raw = raw[: src["max_entries"]]

    for dt, title, url in raw:
        articles.append({
            "id":          f"SX_{hash(url + title) & 0xFFFFFF:06x}",
            "title":       title,
            "summary":     "",  # sitemap doesn't include body
            "url":         url,
            "source":      src["name"],
            "sourceShort": src["short"],
            "sourceColor": src["color"],
            "category":    _scanx_category_from_url(url),
            "published":   dt.astimezone(timezone.utc).isoformat(),
            "undated":     False,
            "sentiment":   _sentiment(title),
            "sentimentVia": "vader",
            "tickers":     _extract_tickers(title),
            "image_url":   None,
            "type":        "news",
        })
    return articles, None


# ── yfinance market-feed basket ───────────────────────────────────────────────

# Major Nifty 50 stocks used to populate the general news feed via yfinance.
# Kept to 20 symbols — enough breadth to cover Indian market news without
# making too many parallel network calls on each 8-minute cache refresh.
_YF_FEED_BASKET = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
    "BAJFINANCE", "AXISBANK", "MARUTI", "HCLTECH", "WIPRO",
    "TITAN", "SUNPHARMA", "TATAMOTORS", "LT", "ADANIPORTS",
]

# Keep articles from within this many days (avoids stale quarterly-report
# pieces from clogging the general feed).
_YF_FEED_MAX_AGE_DAYS = 7


def _fetch_one_yf_stock(sym: str, cutoff: "datetime") -> list[dict]:
    """Fetch and normalise yfinance news for a single NSE symbol.
    Called concurrently from _fetch_yfinance_feed_articles."""
    try:
        import yfinance as yf  # noqa: PLC0415
        raw = yf.Ticker(f"{sym}.NS").news or []
    except Exception:
        return []

    articles: list[dict] = []
    for item in raw:
        c = item.get("content") if isinstance(item.get("content"), dict) else item
        title = (c.get("title") or "").strip()
        if not title:
            continue
        url = (
            (c.get("canonicalUrl") or {}).get("url")
            or (c.get("clickThroughUrl") or {}).get("url")
            or c.get("link", "")
        )
        if not url:
            continue
        pub_raw = c.get("pubDate") or c.get("displayTime") or ""
        pub_dt: Optional[datetime] = None
        if pub_raw:
            try:
                pub_dt = datetime.fromisoformat(pub_raw.replace("Z", "+00:00"))
                if pub_dt < cutoff:
                    continue
            except Exception:
                pass
        provider = c.get("provider") or {}
        source = (
            provider.get("displayName")
            or c.get("publisher")
            or "Yahoo Finance"
        )
        pub_iso = pub_dt.isoformat() if pub_dt else datetime.now(timezone.utc).isoformat()
        thumb = c.get("thumbnail") or {}
        image = thumb.get("originalUrl") or None
        if not image:
            resolutions = thumb.get("resolutions") or []
            if resolutions:
                image = resolutions[0].get("url")
        summary = (c.get("summary") or c.get("description") or "").strip()
        articles.append({
            "id":          f"YF_{hash(url) & 0xFFFFFF:06x}",
            "title":       title,
            "summary":     summary[:400] if summary else "",
            "url":         url,
            "source":      source,
            "sourceShort": "YF",
            "sourceColor": "#6366f1",
            "category":    "market",
            "published":   pub_iso,
            "undated":     pub_dt is None,
            "sentiment":   _sentiment(f"{title} {summary}"),
            "sentimentVia": "vader",
            "tickers":     [sym],
            "image_url":   image,
            "type":        "news",
            "via":         "yfinance",
        })
    return articles


def _fetch_yfinance_feed_articles() -> tuple[list[dict], Optional[str]]:
    """Fetch news for the basket of major Nifty stocks from yfinance.

    All symbols are fetched in parallel (up to 10 workers) so the total
    wall-clock time is ~3-5 s instead of the sequential ~40 s.
    Runs in a thread-pool executor so it doesn't block the event loop.
    Returns (articles, error_string_or_None).
    """
    import concurrent.futures  # noqa: PLC0415
    cutoff = datetime.now(timezone.utc) - timedelta(days=_YF_FEED_MAX_AGE_DAYS)
    all_articles: list[dict] = []
    seen_urls: set[str] = set()

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = {pool.submit(_fetch_one_yf_stock, sym, cutoff): sym
                       for sym in _YF_FEED_BASKET}
            for future in concurrent.futures.as_completed(futures):
                try:
                    for art in future.result():
                        if art["url"] not in seen_urls:
                            seen_urls.add(art["url"])
                            all_articles.append(art)
                except Exception:
                    pass
    except Exception as exc:
        logger.warning("yfinance feed batch failed: %s", exc)
        return [], str(exc)

    return all_articles, None


# ── Combined fetch with per-source health ─────────────────────────────────────

async def _fetch_all_feeds() -> dict:
    """Fetches all sources in parallel and returns:
      { 'articles': [...], 'sources': [{'name','short','ok','count','error'}, ...] }
    """
    loop = asyncio.get_running_loop()
    rss_tasks = [
        loop.run_in_executor(None, _fetch_one_feed, src) for src in RSS_SOURCES
    ]
    scanx_task  = loop.run_in_executor(None, _fetch_scanx_sitemap)
    yf_task     = loop.run_in_executor(None, _fetch_yfinance_feed_articles)

    rss_results, scanx_result, yf_result = await asyncio.gather(
        asyncio.gather(*rss_tasks, return_exceptions=True),
        scanx_task,
        yf_task,
        return_exceptions=False,
    )

    sources_health: list[dict] = []
    articles: list[dict] = []
    seen_titles: set[str] = set()

    def _add_articles(items: list[dict]) -> int:
        added = 0
        for a in items:
            norm = re.sub(r"\W+", "", a["title"].lower())[:40]
            if norm and norm not in seen_titles:
                seen_titles.add(norm)
                articles.append(a)
                added += 1
        return added

    for src, res in zip(RSS_SOURCES, rss_results):
        if isinstance(res, Exception):
            sources_health.append({
                "name":  src["name"], "short": src["short"],
                "category": src["category"],
                "ok": False, "count": 0, "error": str(res),
            })
            continue
        items, err = res
        added = _add_articles(items)
        sources_health.append({
            "name":  src["name"], "short": src["short"],
            "category": src["category"],
            "ok": err is None and len(items) > 0,
            "count": added,
            "error": err,
        })

    # Collapse RSS rows that share the same `short` (ET appears under
    # both 'market' and 'general'). We keep one row per short with
    # ok = any(ok), count = sum(count), error = first error.
    collapsed: dict[str, dict] = {}
    for row in sources_health:
        key = row["short"]
        if key not in collapsed:
            collapsed[key] = {
                "name": row["name"], "short": key,
                "ok": row["ok"], "count": row["count"],
                "error": row["error"] if not row["ok"] else None,
            }
        else:
            c = collapsed[key]
            c["ok"] = c["ok"] or row["ok"]
            c["count"] += row["count"]
            if not c["ok"] and row["error"] and not c["error"]:
                c["error"] = row["error"]
    sources_health = list(collapsed.values())

    # ScanX
    sx_items, sx_err = scanx_result
    sx_added = _add_articles(sx_items)
    sources_health.append({
        "name":  SCANX_SOURCE["name"], "short": SCANX_SOURCE["short"],
        "ok":    sx_err is None and len(sx_items) > 0,
        "count": sx_added,
        "error": sx_err,
    })

    # Yahoo Finance (yfinance basket of major Nifty stocks)
    yf_items, yf_err = yf_result
    yf_added = _add_articles(yf_items)
    sources_health.append({
        "name":  "Yahoo Finance",
        "short": "YF",
        "ok":    yf_err is None and len(yf_items) > 0,
        "count": yf_added,
        "error": yf_err,
    })

    # Sort: dated entries first (newest first), undated entries last.
    articles.sort(key=lambda x: (x.get("undated", False), -1 * _ts(x["published"])))

    # LLM sentiment pass — re-label articles through the app's AI stack
    # (Groq/OpenRouter via ai_client). VADER mislabels financial headlines
    # badly ("book profits" → bullish); the LLM labels replace it wherever a
    # provider is reachable. On failure articles keep their VADER label and
    # sentimentVia stays "vader". Per-headline labels are cached 24 h, so a
    # refresh only classifies headlines it hasn't seen before.
    try:
        from .news_sentiment_llm import apply_llm_sentiment  # noqa: PLC0415
        await apply_llm_sentiment(articles)
    except Exception as exc:
        logger.warning("LLM sentiment pass skipped: %s", exc)

    return {"articles": articles, "sources": sources_health}


def _ts(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


# ── NSE Bulk / Block Deals ────────────────────────────────────────────────────

async def _fetch_deals() -> dict:
    """Returns {'deals': [...], 'errors': {...}, 'available': bool}."""
    def _safe_float(v, default=0.0) -> float:
        try:
            import math
            f = float(v)
            return default if math.isnan(f) else f
        except Exception:
            return default

    def _safe_int(v, default=0) -> int:
        try:
            import math
            f = float(v)
            return default if math.isnan(f) else int(f)
        except Exception:
            return default

    def _safe_str(v, default="") -> str:
        try:
            import pandas as pd
            if pd.isna(v):
                return default
            return str(v).strip()
        except Exception:
            return str(v) if v is not None else default

    def _do():
        deals: list[dict] = []
        errors: dict[str, Optional[str]] = {"bulk": None, "block": None}

        try:
            from nsepython import get_bulkdeals
            import pandas as pd
            bd = get_bulkdeals()
            if isinstance(bd, pd.DataFrame) and not bd.empty:
                for _, row in bd.iterrows():
                    sym = _safe_str(row.get("Symbol", ""))
                    if not sym or sym.upper() == "NAN":
                        continue
                    deals.append({
                        "type":     "bulk",
                        "date":     _safe_str(row.get("Date", "")),
                        "symbol":   sym,
                        "name":     _safe_str(row.get("Security Name", "")),
                        "client":   _safe_str(row.get("Client Name", "")),
                        "side":     _safe_str(row.get("Buy/Sell", "")),
                        "quantity": _safe_int(row.get("Quantity Traded", 0)),
                        "price":    _safe_float(row.get("Trade Price / Wght. Avg. Price", 0)),
                    })
        except Exception as e:
            logger.warning("Bulk deals error: %s", e)
            errors["bulk"] = str(e)

        try:
            from nsepython import get_blockdeals
            import pandas as pd
            bk = get_blockdeals()
            if isinstance(bk, pd.DataFrame) and not bk.empty:
                for _, row in bk.iterrows():
                    sym = _safe_str(row.get("Symbol", row.get("symbol", "")))
                    if not sym or sym.upper() == "NAN":
                        continue
                    deals.append({
                        "type":     "block",
                        "date":     _safe_str(row.get("Date", "")),
                        "symbol":   sym,
                        "name":     _safe_str(row.get("Security Name", row.get("name", ""))),
                        "client":   _safe_str(row.get("Client Name", row.get("clientName", ""))),
                        "side":     _safe_str(row.get("Buy/Sell", row.get("buySell", ""))),
                        "quantity": _safe_int(row.get("Quantity Traded", 0)),
                        "price":    _safe_float(row.get("Trade Price / Wght. Avg. Price", row.get("tradePrice", 0))),
                    })
        except Exception as e:
            logger.warning("Block deals error: %s", e)
            errors["block"] = str(e)

        return {"deals": deals, "errors": errors}

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _do)


# ── NSE Corporate Events ──────────────────────────────────────────────────────

async def _fetch_nse_events() -> dict:
    """Returns {'events': [...], 'error': str|None}."""
    def _do():
        events: list[dict] = []
        err: Optional[str] = None
        try:
            from nsepython import nse_events
            data = nse_events()
            # nsepython 2.97 returns a pandas DataFrame, not a list — earlier
            # code only handled `list`, so 365 real events were being silently
            # dropped on the floor. Normalise both shapes to a list of dicts.
            rows: list[dict]
            if isinstance(data, list):
                rows = data
            elif hasattr(data, "to_dict"):
                rows = data.to_dict(orient="records")  # pandas DataFrame
            else:
                rows = []
            def _s(v) -> str:
                # pandas rows can carry NaN/None/numeric; coerce to a safe
                # string so a single malformed row can't blow up the whole
                # fetch (which would mark the entire feed unavailable).
                if v is None:
                    return ""
                try:
                    if isinstance(v, float) and v != v:  # NaN check
                        return ""
                except Exception:
                    pass
                return str(v)

            for ev in rows[:30]:
                try:
                    sym     = _s(ev.get("symbol", ""))
                    purpose = _s(ev.get("purpose", ev.get("subject", "")))
                    date    = _s(ev.get("date", ev.get("bfDate", "")))
                    company = _s(ev.get("company", ev.get("companyName", sym)))
                    if not sym and not purpose:
                        continue  # empty row — skip silently
                    events.append({
                        "symbol":  sym,
                        "company": company,
                        "purpose": purpose,
                        "date":    date,
                        "type":    _classify_event(purpose),
                    })
                except Exception as row_err:
                    logger.warning("NSE events row skipped: %s", row_err)
                    continue
        except Exception as e:
            logger.warning("NSE events error: %s", e)
            err = str(e)
        return {"events": events, "error": err}

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _do)


def _classify_event(purpose: str) -> str:
    p = purpose.lower()
    if any(w in p for w in ["dividend", "div"]):
        return "dividend"
    if any(w in p for w in ["result", "quarterly", "financial"]):
        return "results"
    if any(w in p for w in ["split", "bonus"]):
        return "split"
    if any(w in p for w in ["agm", "egm", "meeting"]):
        return "meeting"
    if any(w in p for w in ["merger", "acquisition", "amalgam"]):
        return "merger"
    return "announcement"


# ── Public API ────────────────────────────────────────────────────────────────

# Source-string surfaced via /news/feed meta. Mirrors the Sentiment
# dashboard's provenance pill so the UI can show one honest label.
NEWS_SOURCE_LABEL = "RSS feeds + ScanX sitemap"

# When the user types a ticker-shaped query in the news feed search and the
# RSS filter returns fewer than this many matches, we top up via Tavily.
_TAVILY_FLOOR = 3

# The dedicated per-stock news endpoint has a higher floor because the
# expectation is that the panel actually shows news for that one stock —
# 5+ articles is the minimum useful set.
_TICKER_TAVILY_FLOOR = 5


async def get_news_feed(
    category: str = "all",
    search: str = "",
    limit: int = 30,
    offset: int = 0,
) -> dict:
    entry = _cache_get("feed")
    cached_hit = entry is not None
    if entry is None:
        payload = await _fetch_all_feeds()
        _cache_set("feed", payload)
        entry = _CACHE["feed"]

    payload = entry["data"]
    all_articles  = payload["articles"]
    sources_health = payload["sources"]

    articles = all_articles
    if category != "all":
        articles = [a for a in articles if a.get("category") == category]
    if search:
        q = search.lower()
        articles = [
            a for a in articles
            if q in a["title"].lower() or q in a["summary"].lower()
        ]

    # ── Tavily top-up ────────────────────────────────────────────────────────
    # If the user typed a ticker-shaped query and RSS came back thin, augment
    # with Tavily search. Gated to keep cost predictable:
    #   - category in ("all", "market") only (skip "corporate"/"deals"/"general"
    #     because Tavily isn't a corporate-events / bulk-deals source)
    #   - query looks like a ticker (uppercase, 2-15 chars)
    #   - RSS returned fewer than `_TAVILY_FLOOR` articles
    #   - Result is cached per-symbol for 5 minutes (see _CACHE_TTL["ticker"])
    # If TAVILY_API_KEY isn't set the helper is a no-op, so this is safe to
    # leave on by default.
    tavily_used = False
    if (
        search
        and category in ("all", "market")
        and len(articles) < _TAVILY_FLOOR
        and _looks_like_ticker(search)
    ):
        symbol_key = search.strip().upper()
        cache_key  = f"ticker:{symbol_key}"
        cached = _cache_get(cache_key)
        if cached:
            tav_articles = cached["data"]
        else:
            try:
                from . import tavily_service  # noqa: PLC0415
                tav_articles = await tavily_service.search_ticker_news(
                    symbol_key, days=7, max_results=10,
                )
            except Exception:
                tav_articles = []
            # Tavily articles arrive with sentiment=None — classify them via
            # the LLM before caching so they carry real labels downstream
            # (feed UI, tri-factor, AI Analyst).
            if tav_articles:
                try:
                    from .news_sentiment_llm import apply_llm_sentiment  # noqa: PLC0415
                    await apply_llm_sentiment(tav_articles)
                except Exception:
                    pass
            _cache_set(cache_key, tav_articles)

        if tav_articles:
            tavily_used = True
            # Dedupe by lowercase title against what RSS already returned.
            seen = {(a.get("title") or "").lower().strip() for a in articles}
            for art in tav_articles:
                t = (art.get("title") or "").lower().strip()
                if not t or t in seen:
                    continue
                seen.add(t)
                # Project Tavily's shape into the RSS article shape the
                # frontend expects (category + tickers fields).
                articles.append({
                    "title":     art.get("title"),
                    "summary":   art.get("summary") or "",
                    "url":       art.get("url") or "",
                    "source":    art.get("source") or "tavily",
                    "published": art.get("published") or "",
                    "category":  "market",
                    "tickers":   [symbol_key],
                    "sentiment": art.get("sentiment"),
                    "sentimentVia": art.get("sentimentVia"),
                    "image":     None,
                    "via":       "tavily",   # provenance marker for the UI
                })

    total = len(articles)
    return {
        "articles":    articles[offset: offset + limit],
        "total":       total,
        "cached":      cached_hit,
        "fetchedAt":   datetime.now(timezone.utc).isoformat(),
        "refreshedAt": _iso_from_ts(entry["ts"]),
        "categories":  ["all", "market", "corporate", "general", "deals"],
        "sources":     sources_health,
        "source":      (NEWS_SOURCE_LABEL + " + Tavily")
                        if tavily_used else NEWS_SOURCE_LABEL,
        "tavilyUsed":  tavily_used,
    }


def _yfinance_ticker_news(sym: str) -> list[dict]:
    """Fetch per-stock news from yfinance and normalise to article dicts.

    yfinance ≥ 0.2.55 wraps each item as {"id": ..., "content": {...}}.
    We extract the nested content and map it to our article schema so the
    frontend can reuse the same card components.
    """
    try:
        import yfinance as yf  # noqa: PLC0415
        raw = yf.Ticker(f"{sym}.NS").news or []
        articles: list[dict] = []
        seen_urls: set[str] = set()
        for item in raw:
            # Support both old flat shape and new nested {"content": {...}} shape
            c = item.get("content") if isinstance(item.get("content"), dict) else item
            title = (c.get("title") or "").strip()
            if not title:
                continue
            # URL: prefer canonicalUrl, fall back to clickThroughUrl / link
            url = (
                (c.get("canonicalUrl") or {}).get("url")
                or (c.get("clickThroughUrl") or {}).get("url")
                or c.get("link", "")
            )
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            # Publisher
            provider = c.get("provider") or {}
            source = (
                provider.get("displayName")
                or c.get("publisher")
                or "Yahoo Finance"
            )
            # Timestamp
            pub_date = (
                c.get("pubDate")
                or c.get("displayTime")
                or ""
            )
            if pub_date and not pub_date.endswith("Z") and "+" not in pub_date:
                pub_date = pub_date + "Z"
            # Image
            thumb = c.get("thumbnail") or {}
            image = thumb.get("originalUrl") or None
            if not image:
                resolutions = thumb.get("resolutions") or []
                if resolutions:
                    image = resolutions[0].get("url")
            summary = (c.get("summary") or c.get("description") or "").strip()
            articles.append({
                "title":       title,
                "summary":     summary[:400] if summary else "",
                "url":         url,
                "source":      source,
                "published":   pub_date,
                "category":    "market",
                "tickers":     [sym],
                "sentiment":   _sentiment(f"{title} {summary}"),
                "sentimentVia": "vader",
                "image_url":   image,
                "type":        "news",
                "via":         "yfinance",
            })
        return articles
    except Exception as exc:
        logger.debug("yfinance news fetch failed for %s: %s", sym, exc)
        return []


async def get_ticker_news(symbol: str, limit: int = 20) -> dict:
    """Return news for a single ticker.

    Strategy (in priority order):
      1. yfinance `.news` — stock-specific, reliable, cached 5 min per symbol.
      2. RSS feed title-match — filters the general feed for the symbol name.
      3. Tavily top-up — when combined count is still below the floor.

    Returns the same shape as ``get_news_feed`` so the frontend can reuse
    the existing article card components.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return {"articles": [], "total": 0, "symbol": "",
                "tavilyUsed": False, "source": NEWS_SOURCE_LABEL}

    lim = max(1, min(50, int(limit)))
    now_iso = datetime.now(timezone.utc).isoformat()

    # Step 1: yfinance per-stock news (primary source, cached per symbol)
    yf_cache_key = f"yf:{sym}"
    yf_entry = _cache_get(yf_cache_key)
    if yf_entry is not None:
        yf_articles: list[dict] = yf_entry["data"]
    else:
        yf_articles = await asyncio.get_event_loop().run_in_executor(
            None, _yfinance_ticker_news, sym
        )
        # LLM re-label before caching (VADER label kept as fallback).
        if yf_articles:
            try:
                from .news_sentiment_llm import apply_llm_sentiment  # noqa: PLC0415
                await apply_llm_sentiment(yf_articles)
            except Exception:
                pass
        _cache_set(yf_cache_key, yf_articles)

    matched: list[dict] = list(yf_articles)
    seen_titles = {(a.get("title") or "").lower().strip() for a in matched}

    # Step 2: RSS pass — supplement with any general-feed articles that
    # mention this ticker in their title (keeps RSS articles alongside yf ones)
    rss_entry = _cache_get("feed")
    if rss_entry is None:
        payload = await _fetch_all_feeds()
        _cache_set("feed", payload)
        rss_entry = _CACHE["feed"]

    sym_lc = sym.lower()
    for art in rss_entry["data"]["articles"]:
        tickers_up = [t.upper() for t in (art.get("tickers") or [])]
        title_lc = (art.get("title") or "").lower()
        if sym in tickers_up or sym_lc in title_lc:
            t = title_lc.strip()
            if t and t not in seen_titles:
                seen_titles.add(t)
                matched.append(art)

    # Step 3: Tavily top-up when still below floor
    tavily_used = False
    if len(matched) < _TICKER_TAVILY_FLOOR:
        tav_cache_key = f"ticker:{sym}"
        cached_tav = _cache_get(tav_cache_key)
        if cached_tav:
            tav_articles = cached_tav["data"]
        else:
            try:
                from . import tavily_service  # noqa: PLC0415
                tav_articles = await tavily_service.search_ticker_news(
                    sym, days=14, max_results=12,
                )
            except Exception:
                tav_articles = []
            # Tavily articles arrive with sentiment=None — classify before
            # caching so the tri-factor sentiment leg counts them too.
            if tav_articles:
                try:
                    from .news_sentiment_llm import apply_llm_sentiment  # noqa: PLC0415
                    await apply_llm_sentiment(tav_articles)
                except Exception:
                    pass
            _cache_set(tav_cache_key, tav_articles)

        if tav_articles:
            tavily_used = True
            for art in tav_articles:
                t = (art.get("title") or "").lower().strip()
                if not t or t in seen_titles:
                    continue
                seen_titles.add(t)
                matched.append({
                    "title":     art.get("title"),
                    "summary":   art.get("summary") or "",
                    "url":       art.get("url") or "",
                    "source":    art.get("source") or "tavily",
                    "published": art.get("published") or "",
                    "category":  "market",
                    "tickers":   [sym],
                    "sentiment": art.get("sentiment"),
                    "sentimentVia": art.get("sentimentVia"),
                    "image":     None,
                    "via":       "tavily",
                })

    source_label = "Yahoo Finance"
    if tavily_used:
        source_label += " + Tavily"
    elif any(a.get("via") != "yfinance" for a in matched):
        source_label += " + " + NEWS_SOURCE_LABEL

    return {
        "symbol":      sym,
        "articles":    matched[:lim],
        "total":       len(matched),
        "source":      source_label,
        "tavilyUsed":  tavily_used,
        "fetchedAt":   now_iso,
        "refreshedAt": now_iso,
    }


async def get_deals() -> dict:
    entry = _cache_get("deals")
    cached_hit = entry is not None
    if entry is None:
        payload = await _fetch_deals()
        _cache_set("deals", payload)
        entry = _CACHE["deals"]

    payload = entry["data"]
    deals  = payload["deals"]
    errors = payload["errors"]
    bulk  = [d for d in deals if d["type"] == "bulk"]
    block = [d for d in deals if d["type"] == "block"]
    return {
        "bulk":        bulk,
        "block":       block,
        "total":       len(deals),
        "available":   errors.get("bulk") is None or errors.get("block") is None,
        "errors":      errors,
        "cached":      cached_hit,
        "refreshedAt": _iso_from_ts(entry["ts"]),
        "fetchedAt":   datetime.now(timezone.utc).isoformat(),
    }


async def get_corporate_events() -> dict:
    entry = _cache_get("events")
    cached_hit = entry is not None
    if entry is None:
        payload = await _fetch_nse_events()
        _cache_set("events", payload)
        entry = _CACHE["events"]

    payload = entry["data"]
    events = payload["events"]
    err    = payload["error"]
    return {
        "events":      events,
        "total":       len(events),
        "available":   err is None,
        "error":       err,
        "cached":      cached_hit,
        "refreshedAt": _iso_from_ts(entry["ts"]),
        "fetchedAt":   datetime.now(timezone.utc).isoformat(),
    }


async def get_news_stats() -> dict:
    # Eager-warm the feed cache if empty so stats aren't stuck at zero
    # immediately after a backend restart.
    entry = _cache_get("feed")
    if entry is None:
        try:
            await get_news_feed()
            entry = _CACHE.get("feed")
        except Exception:
            entry = None

    cached = entry["data"]["articles"] if entry else []
    sources_health = entry["data"]["sources"] if entry else []

    sentiments = {"bullish": 0, "bearish": 0, "neutral": 0}
    sources: dict[str, int] = {}
    sentiment_via = {"llm": 0, "vader": 0, "none": 0}
    for a in cached:
        s = a.get("sentiment", "neutral")
        sentiments[s] = sentiments.get(s, 0) + 1
        src = a.get("sourceShort", "?")
        sources[src] = sources.get(src, 0) + 1
        v = a.get("sentimentVia") or "vader"
        sentiment_via[v] = sentiment_via.get(v, 0) + 1

    # marketMood requires a meaningful sample (≥5 articles) AND a
    # meaningful margin (≥10% of articles must lean one way more than
    # the other) before we declare a directional mood. Otherwise small
    # noisy samples like "5 bullish, 4 bearish, 90 neutral" would be
    # labelled "bullish".
    total = len(cached)
    margin = abs(sentiments["bullish"] - sentiments["bearish"])
    if total >= 5 and margin / total >= 0.10:
        mood = "bullish" if sentiments["bullish"] > sentiments["bearish"] else "bearish"
    else:
        mood = "neutral"
    return {
        "totalArticles": total,
        "sentiments":    sentiments,
        "sources":       sources,
        "sourcesHealth": sources_health,
        "marketMood":    mood,
        # Provenance of the labels behind `sentiments`: how many articles were
        # classified by the LLM vs left on the VADER fallback. Lets consumers
        # (and the UI) tell an AI-labelled mood from a lexicon-labelled one.
        "sentimentVia":  sentiment_via,
    }


async def invalidate_cache() -> None:
    _CACHE.clear()
