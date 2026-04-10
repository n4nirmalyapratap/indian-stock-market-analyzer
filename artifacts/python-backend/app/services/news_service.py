"""
News & Market Updates Service
Aggregates RSS feeds (ET, Livemint, Moneycontrol) + NSE bulk/block deals + corporate events.
All results are cached to avoid hammering sources.
"""
import asyncio
import logging
import time
import re
import html
from datetime import datetime, timezone
from typing import Optional

import feedparser

logger = logging.getLogger(__name__)

# ── In-memory cache ───────────────────────────────────────────────────────────

_CACHE: dict[str, dict] = {}
_CACHE_TTL = {
    "feed":  8 * 60,    # 8 minutes for RSS news
    "deals": 30 * 60,   # 30 minutes for deals
    "events": 15 * 60,  # 15 minutes for NSE events
}


def _cache_get(key: str) -> Optional[list]:
    entry = _CACHE.get(key)
    if entry and time.time() - entry["ts"] < _CACHE_TTL.get(key, 600):
        return entry["data"]
    return None


def _cache_set(key: str, data: list) -> None:
    _CACHE[key] = {"ts": time.time(), "data": data}


# ── RSS Feed Sources ──────────────────────────────────────────────────────────

RSS_SOURCES = [
    {
        "name": "Economic Times",
        "short": "ET",
        "color": "#1a56db",
        "category": "market",
        "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    },
    {
        "name": "Economic Times",
        "short": "ET",
        "color": "#1a56db",
        "category": "general",
        "url": "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
    },
    {
        "name": "Livemint",
        "short": "Mint",
        "color": "#059669",
        "category": "market",
        "url": "https://www.livemint.com/rss/markets",
    },
    {
        "name": "Livemint",
        "short": "Mint",
        "color": "#059669",
        "category": "corporate",
        "url": "https://www.livemint.com/rss/companies",
    },
    {
        "name": "Moneycontrol",
        "short": "MC",
        "color": "#7c3aed",
        "category": "market",
        "url": "https://www.moneycontrol.com/rss/latestnews.xml",
    },
]

# ── Keyword Sentiment ─────────────────────────────────────────────────────────

_BULLISH_WORDS = {
    "surge", "surges", "rally", "rallies", "gain", "gains", "rise", "rises",
    "up", "jumps", "soar", "soars", "climb", "climbs", "strong", "strengthen",
    "profit", "profits", "growth", "growing", "buy", "bullish", "upside",
    "outperform", "upgrade", "upgraded", "breakout", "record", "high", "positive",
    "beat", "beats", "exceeded", "recovery", "recover", "boom", "booms",
}

_BEARISH_WORDS = {
    "fall", "falls", "drop", "drops", "decline", "declines", "loss", "losses",
    "down", "tumbles", "tumble", "crash", "crashes", "sell", "selloff",
    "bearish", "downside", "underperform", "downgrade", "downgraded", "weak",
    "weakness", "cut", "cuts", "miss", "misses", "disappoint", "disappoints",
    "plunge", "plunges", "slump", "slumps", "negative", "concern", "concerns",
    "risk", "risks", "drag",
}


def _sentiment(text: str) -> str:
    words = set(re.findall(r"\b\w+\b", text.lower()))
    b = len(words & _BULLISH_WORDS)
    br = len(words & _BEARISH_WORDS)
    if b > br:
        return "bullish"
    if br > b:
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


# ── Time Parsing ──────────────────────────────────────────────────────────────

def _parse_published(entry) -> str:
    pt = entry.get("published_parsed")
    if pt:
        try:
            dt = datetime(*pt[:6], tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            pass
    return datetime.now(timezone.utc).isoformat()


# ── RSS Ingestion ─────────────────────────────────────────────────────────────

def _fetch_one_feed(src: dict) -> list[dict]:
    articles = []
    try:
        feed = feedparser.parse(src["url"])
        for entry in feed.entries[:15]:
            title = _clean(entry.get("title", ""))
            summary = _clean(entry.get("summary", entry.get("description", "")))
            if not title:
                continue
            combined = f"{title} {summary}"
            articles.append({
                "id":        f"{src['short']}_{hash(entry.get('link','') + title) & 0xFFFFFF:06x}",
                "title":     title,
                "summary":   summary,
                "url":       entry.get("link", "#"),
                "source":    src["name"],
                "sourceShort": src["short"],
                "sourceColor": src["color"],
                "category":  src["category"],
                "published": _parse_published(entry),
                "sentiment": _sentiment(combined),
                "tickers":   _extract_tickers(combined),
                "type":      "news",
            })
    except Exception as e:
        logger.warning("Feed %s failed: %s", src["url"], e)
    return articles


async def _fetch_all_feeds() -> list[dict]:
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, _fetch_one_feed, src) for src in RSS_SOURCES]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    articles: list[dict] = []
    seen_titles: set[str] = set()
    for r in results:
        if isinstance(r, list):
            for a in r:
                norm = re.sub(r"\W+", "", a["title"].lower())[:40]
                if norm not in seen_titles:
                    seen_titles.add(norm)
                    articles.append(a)
    articles.sort(key=lambda x: x["published"], reverse=True)
    return articles


# ── NSE Bulk / Block Deals ────────────────────────────────────────────────────

async def _fetch_deals() -> list[dict]:
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
        deals = []
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

        return deals

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do)


# ── NSE Corporate Events ──────────────────────────────────────────────────────

async def _fetch_nse_events() -> list[dict]:
    def _do():
        events = []
        try:
            from nsepython import nse_events
            data = nse_events()
            if isinstance(data, list):
                for ev in data[:30]:
                    sym = ev.get("symbol", "")
                    purpose = ev.get("purpose", ev.get("subject", ""))
                    date = ev.get("date", ev.get("bfDate", ""))
                    events.append({
                        "symbol":  sym,
                        "company": ev.get("company", ev.get("companyName", sym)),
                        "purpose": purpose,
                        "date":    date,
                        "type":    _classify_event(purpose),
                    })
        except Exception as e:
            logger.warning("NSE events error: %s", e)
        return events

    loop = asyncio.get_event_loop()
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

async def get_news_feed(
    category: str = "all",
    search: str = "",
    limit: int = 30,
    offset: int = 0,
) -> dict:
    cached = _cache_get("feed")
    if cached is None:
        cached = await _fetch_all_feeds()
        _cache_set("feed", cached)

    articles = cached
    if category != "all":
        articles = [a for a in articles if a.get("category") == category]
    if search:
        q = search.lower()
        articles = [
            a for a in articles
            if q in a["title"].lower() or q in a["summary"].lower()
        ]

    total = len(articles)
    return {
        "articles": articles[offset: offset + limit],
        "total":    total,
        "cached":   _cache_get("feed") is not None,
        "refreshedAt": datetime.now(timezone.utc).isoformat(),
        "categories": ["all", "market", "corporate", "general"],
    }


async def get_deals() -> dict:
    cached = _cache_get("deals")
    if cached is None:
        cached = await _fetch_deals()
        _cache_set("deals", cached)

    bulk  = [d for d in cached if d["type"] == "bulk"]
    block = [d for d in cached if d["type"] == "block"]
    return {
        "bulk":  bulk,
        "block": block,
        "total": len(cached),
        "refreshedAt": datetime.now(timezone.utc).isoformat(),
    }


async def get_corporate_events() -> dict:
    cached = _cache_get("events")
    if cached is None:
        cached = await _fetch_nse_events()
        _cache_set("events", cached)
    return {
        "events": cached,
        "total":  len(cached),
        "refreshedAt": datetime.now(timezone.utc).isoformat(),
    }


async def get_news_stats() -> dict:
    # If feed cache is empty (e.g. fresh backend restart), populate it first
    # so stats are never stuck at zero just because the cache hasn't warmed up yet.
    cached = _cache_get("feed")
    if not cached:
        try:
            result = await get_news_feed()
            cached = result.get("articles", [])
        except Exception:
            cached = []

    sentiments = {"bullish": 0, "bearish": 0, "neutral": 0}
    sources: dict[str, int] = {}
    for a in cached:
        s = a.get("sentiment", "neutral")
        sentiments[s] = sentiments.get(s, 0) + 1
        src = a.get("sourceShort", "?")
        sources[src] = sources.get(src, 0) + 1

    return {
        "totalArticles": len(cached),
        "sentiments":    sentiments,
        "sources":       sources,
        "marketMood":    "bullish" if sentiments["bullish"] > sentiments["bearish"] else
                         "bearish" if sentiments["bearish"] > sentiments["bullish"] else "neutral",
    }


async def invalidate_cache() -> None:
    _CACHE.clear()
