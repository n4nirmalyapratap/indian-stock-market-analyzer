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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sentiment", tags=["sentiment"])


@router.get("/market")
async def get_market_sentiment():
    """Full centralized market sentiment snapshot (cached 15 min)."""
    try:
        data = await engine.get_market_sentiment()
        data["cached"] = True
        return data
    except Exception as e:
        logger.error("Market sentiment error: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/sectors")
async def get_sector_sentiments():
    """Per-sector sentiment scores for heatmap (cached 15 min)."""
    try:
        data = await engine.get_sector_sentiments()
        return {"sectors": data, "count": len(data)}
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
