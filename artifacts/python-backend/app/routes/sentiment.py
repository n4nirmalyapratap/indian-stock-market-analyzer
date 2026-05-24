"""
sentiment.py — Centralized Market Sentiment API Routes

GET /api/sentiment/market   → full composite sentiment snapshot
GET /api/sentiment/sectors  → per-sector sentiment heatmap data
GET /api/sentiment/refresh  → force refresh (bypasses 15-min cache)
"""
from __future__ import annotations

import logging
import time as _time
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from ..services import market_sentiment_engine as engine
from ..services import market_cache_service as _disk
from ..services import news_service as _news

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sentiment", tags=["sentiment"])

# /refresh wipes the engine cache and force-fetches Yahoo + RSS. We throttle
# the wipe so a stuck client or hostile caller can't repeatedly evict the
# in-memory cache. Engine TTL is 15 min; a 30 s server-side cooldown still
# lets human clicks through.
_MIN_REFRESH_INTERVAL = 30.0
_last_refresh_at: float = 0.0


def _meta() -> dict:
    state = _disk.current_market_state()
    return {
        # Market Sentiment composes Yahoo Finance (VIX, Nifty, sector indices)
        # with RSS feed scoring (news leg). It does NOT call NSE directly —
        # claiming "NSE" as the source was provenance-lying.
        "source":       "Yahoo Finance + RSS feeds",
        "servedFrom":   "SENTIMENT_ENGINE",
        "asOf":         _disk._now_ist().isoformat(),
        "marketState":  state,
        "eodSealed":    state in ("CLOSED", "WEEKEND"),
        "eodDate":      _disk._eod_date_for(state),
        "cacheVersion": _disk.cache_version(),
    }


@router.get("/market")
async def get_market_sentiment():
    """Full centralized market sentiment snapshot (cached 15 min)."""
    try:
        data = await engine.get_market_sentiment()
        # Preserve engine's `cached` flag — it's False on a fresh compute and
        # True on a cache hit. The previous unconditional `data["cached"]=True`
        # made it impossible to tell from the response whether the engine had
        # just run or returned a cached snapshot.
        if isinstance(data, dict):
            data.setdefault("meta", _meta())
        return data
    except Exception:
        logger.exception("Market sentiment error")
        return JSONResponse(
            status_code=500,
            content={"error": "Market sentiment is temporarily unavailable."},
        )


@router.get("/sectors")
async def get_sector_sentiments():
    """Per-sector sentiment scores for heatmap (cached 15 min)."""
    try:
        data = await engine.get_sector_sentiments()
        return {"sectors": data, "count": len(data), "meta": _meta()}
    except Exception:
        logger.exception("Sector sentiment error")
        return JSONResponse(
            status_code=500,
            content={"error": "Sector sentiment is temporarily unavailable."},
        )


@router.get("/refresh")
async def refresh_sentiment():
    """Force-refresh the sentiment cache (bypasses TTL).

    Throttled so the cache can't be wiped more than once every
    ``_MIN_REFRESH_INTERVAL`` seconds across all callers — if you hit it
    again sooner you get the cached snapshot back with ``throttled: true``,
    not an error. The frontend handles either response identically.
    """
    global _last_refresh_at
    now = _time.time()
    try:
        if now - _last_refresh_at < _MIN_REFRESH_INTERVAL:
            data = await engine.get_market_sentiment()
            sectors = await engine.get_sector_sentiments()
            return {
                "status": "throttled",
                "throttled": True,
                "retryAfterSeconds": int(_MIN_REFRESH_INTERVAL - (now - _last_refresh_at)),
                "market": data,
                "sectors": sectors,
            }
        _last_refresh_at = now
        engine.clear_cache()
        # Also wipe the news cache so the sentiment recompute pulls
        # truly fresh headlines, not the 8-min-old cached snapshot.
        await _news.invalidate_cache()
        data = await engine.get_market_sentiment(force_refresh=True)
        sectors = await engine.get_sector_sentiments(force_refresh=True)
        return {
            "status": "refreshed",
            "market": data,
            "sectors": sectors,
        }
    except Exception:
        # Stop returning raw exception text in the body — log it and surface
        # a generic message instead.
        logger.exception("Sentiment refresh failed")
        return JSONResponse(
            status_code=500,
            content={"error": "Sentiment refresh failed; please try again shortly."},
        )
