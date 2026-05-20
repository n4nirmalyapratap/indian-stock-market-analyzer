"""
Tavily Search wrapper for ticker-scoped news.

Used as a fallback news source when the RSS feed returns too few articles
for a given ticker (mid-cap and small-cap coverage is thin). Tavily's
``topic=news`` endpoint returns structured results that play nicely with
LLM prompts.

Configuration:
    TAVILY_API_KEY        required to enable the service (otherwise the
                          fetch returns []). Get one at https://tavily.com.
    TAVILY_API_URL        optional override; defaults to the public host.
    TAVILY_HTTP_TIMEOUT   seconds, default 8.

Failure modes:
    - No API key: returns [] (silent — caller falls back to RSS).
    - Network / 4xx / 5xx: logged at WARNING, returns [].
    - Malformed response: logged at WARNING, returns [].

The returned list matches the shape the AI Analyst expects, so callers
can mix it freely with RSS articles:
    [{"title": str, "source": str, "published": str, "url": str,
      "summary": str, "sentiment": None}]
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_URL = "https://api.tavily.com/search"
DEFAULT_TIMEOUT = 8.0


def is_configured() -> bool:
    """True iff a Tavily API key is set in env or DB secrets."""
    return bool(_api_key())


def _api_key() -> str:
    raw = os.environ.get("TAVILY_API_KEY", "")
    if raw:
        return raw.strip()
    # Optional DB-secrets fallback (matches the pattern used by ai_client).
    try:
        from app.lib.secrets_store import get_secret  # noqa: PLC0415
        return (get_secret("TAVILY_API_KEY", "") or "").strip()
    except Exception:
        return ""


def _base_url() -> str:
    return os.environ.get("TAVILY_API_URL", DEFAULT_URL).strip() or DEFAULT_URL


def _timeout() -> float:
    raw = os.environ.get("TAVILY_HTTP_TIMEOUT", "").strip()
    try:
        return float(raw) if raw else DEFAULT_TIMEOUT
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT


async def search_ticker_news(
    symbol: str,
    *,
    days: int = 7,
    max_results: int = 10,
) -> list[dict]:
    """Return news articles for a ticker via Tavily.

    Builds the query as ``<SYMBOL> NSE stock news`` which biases the
    results toward Indian equity coverage. Returns [] on any error so
    the caller's main flow is never disrupted.
    """
    key = _api_key()
    if not key:
        return []

    sym = (symbol or "").strip().upper()
    if not sym:
        return []

    query = f"{sym} NSE stock news"
    payload: dict[str, Any] = {
        "api_key":       key,
        "query":         query,
        "topic":         "news",
        "search_depth":  "basic",
        "days":          max(1, min(30, int(days))),
        "max_results":   max(1, min(20, int(max_results))),
    }

    try:
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            resp = await client.post(_base_url(), json=payload)
            if resp.status_code != 200:
                logger.warning(
                    "tavily: %s %s (status=%d) — falling back to RSS",
                    resp.status_code, query, resp.status_code,
                )
                return []
            data = resp.json()
    except Exception as exc:
        logger.warning("tavily: fetch failed for %s: %s", sym, exc)
        return []

    raw = data.get("results") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        logger.warning("tavily: malformed response for %s: %r", sym,
                       (str(data)[:120] if data is not None else None))
        return []

    out: list[dict] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        title = (r.get("title") or "").strip()
        if not title:
            continue
        out.append({
            "title":     title,
            "url":       r.get("url") or "",
            "summary":   (r.get("content") or "").strip(),
            "published": r.get("published_date") or r.get("publishedDate") or "",
            "source":    _domain_from_url(r.get("url") or ""),
            "sentiment": None,
            "score":     float(r.get("score") or 0.0),
        })
    return out


def _domain_from_url(url: str) -> str:
    """Cheap-and-cheerful domain extractor — avoids pulling in urlparse just
    for a display label."""
    if not url:
        return "tavily"
    s = url
    if "://" in s:
        s = s.split("://", 1)[1]
    s = s.split("/", 1)[0]
    if s.startswith("www."):
        s = s[4:]
    return s or "tavily"
