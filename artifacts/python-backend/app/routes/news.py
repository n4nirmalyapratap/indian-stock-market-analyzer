import time as _time

from fastapi import APIRouter, Query, Request
from ..services import news_service
from ..services import market_cache_service as _disk

router = APIRouter(prefix="/news", tags=["news"])


# /refresh is callable by any authenticated user (the frontend auto-fires it
# every 8 minutes via NewsFeed.tsx), but we throttle the cache-wipe so a
# stuck client or hostile caller can't repeatedly evict the in-memory news
# cache. _MIN_REFRESH_INTERVAL ≪ frontend interval (8 minutes), so a typical
# user-initiated click still goes through.
_MIN_REFRESH_INTERVAL = 30.0  # seconds
_last_refresh_at: float = 0.0


def _meta(source: str = "NSE", as_of_iso: str | None = None) -> dict:
    state = _disk.current_market_state()
    return {
        "source":       source,
        "servedFrom":   "NEWS_FEED",
        "asOf":         as_of_iso or _disk._now_ist().isoformat(),
        "marketState":  state,
        "eodSealed":    state in ("CLOSED", "WEEKEND"),
        "eodDate":      _disk._eod_date_for(state),
        "cacheVersion": _disk.cache_version(),
    }


@router.get("/feed")
async def get_feed(
    category: str = Query("all", description="all | market | corporate | general | deals"),
    search:   str = Query("", description="Search query"),
    limit:    int = Query(30, ge=1, le=100),
    offset:   int = Query(0, ge=0),
):
    data = await news_service.get_news_feed(category, search, limit, offset)
    if isinstance(data, dict):
        # Surface honest provenance (matches Sentiment dashboard pattern):
        # the source label includes ScanX, and `asOf` reflects the real
        # cache fill time rather than always being "now".
        meta = _meta(
            source=data.get("source", news_service.NEWS_SOURCE_LABEL),
            as_of_iso=data.get("refreshedAt"),
        )
        data.setdefault("meta", meta)
    return data


@router.get("/deals")
async def get_deals():
    return await news_service.get_deals()


@router.get("/events")
async def get_events():
    return await news_service.get_corporate_events()


@router.get("/stats")
async def get_stats():
    return await news_service.get_news_stats()


@router.post("/refresh")
async def refresh(request: Request):
    global _last_refresh_at
    now = _time.time()
    if now - _last_refresh_at < _MIN_REFRESH_INTERVAL:
        # Throttled — too soon since the previous refresh. Return 200 with a
        # `throttled: true` marker so the frontend timer keeps ticking
        # smoothly without flagging an error.
        return {
            "ok": True,
            "throttled": True,
            "retryAfterSeconds": int(_MIN_REFRESH_INTERVAL - (now - _last_refresh_at)),
            "message": "Cache refresh skipped — recently refreshed",
        }
    _last_refresh_at = now
    await news_service.invalidate_cache()
    # Eagerly re-warm the feed cache so the next /stats request
    # doesn't race against an empty cache and return all zeros.
    try:
        await news_service.get_news_feed()
    except Exception:
        pass
    return {"ok": True, "message": "Cache refreshed with latest articles"}
