"""
sentiment.py — Centralized Market Sentiment API Routes

GET /api/sentiment/market   → full composite sentiment snapshot
GET /api/sentiment/sectors  → per-sector sentiment heatmap data
GET /api/sentiment/refresh  → force refresh (bypasses 15-min cache)
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from ..services import market_sentiment_engine as engine
from ..services import market_cache_service as _disk

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sentiment", tags=["sentiment"])


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
    except Exception as e:
        logger.error("Market sentiment error: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/sectors")
async def get_sector_sentiments():
    """Per-sector sentiment scores for heatmap (cached 15 min)."""
    try:
        data = await engine.get_sector_sentiments()
        return {"sectors": data, "count": len(data), "meta": _meta()}
    except Exception as e:
        logger.error("Sector sentiment error: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/refresh")
async def refresh_sentiment():
    """Force-refresh the sentiment cache (bypasses TTL)."""
    try:
        engine.clear_cache()
        data = await engine.get_market_sentiment(force_refresh=True)
        sectors = await engine.get_sector_sentiments(force_refresh=True)
        return {
            "status": "refreshed",
            "market": data,
            "sectors": sectors,
        }
    except Exception as e:
        logger.error("Sentiment refresh error: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})
