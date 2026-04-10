from fastapi import APIRouter, Query
from ..services import news_service

router = APIRouter(prefix="/news", tags=["news"])


@router.get("/feed")
async def get_feed(
    category: str = Query("all", description="all | market | corporate | general"),
    search:   str = Query("", description="Search query"),
    limit:    int = Query(30, ge=1, le=100),
    offset:   int = Query(0, ge=0),
):
    return await news_service.get_news_feed(category, search, limit, offset)


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
async def refresh():
    await news_service.invalidate_cache()
    # Eagerly re-warm the feed cache so the next /stats request
    # doesn't race against an empty cache and return all zeros.
    try:
        await news_service.get_news_feed()
    except Exception:
        pass
    return {"ok": True, "message": "Cache refreshed with latest articles"}
