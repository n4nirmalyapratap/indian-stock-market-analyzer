from fastapi import APIRouter, BackgroundTasks
from ..lib.universe_builder import (
    load_cache, get_or_refresh, CACHE_FILE, CACHE_TTL, cache_age_seconds,
)
from ..lib import universe as _univ

router = APIRouter(prefix="/universe", tags=["universe"])


@router.get("/status")
async def universe_status():
    # ignore_ttl: a stale-but-real cache is still "live data" (just old). We
    # report its age so callers can decide whether it's fresh enough, instead
    # of pretending we're on the hardcoded fallback the moment it crosses 24h.
    cache = load_cache(ignore_ttl=True)
    age   = cache_age_seconds()
    return {
        "total_symbols":     len(_univ.ALL_SYMBOLS),
        "total_sectors":     len(_univ.SECTOR_SYMBOLS),
        "sectors":           {k: len(v) for k, v in _univ.SECTOR_SYMBOLS.items()},
        "cache_exists":      CACHE_FILE.exists(),
        "cache_generated_at": cache.get("generated_at") if cache else None,
        "cache_age_seconds": age,
        "cache_stale":       (age is None or age > CACHE_TTL),
        "live_data_active":  bool(cache) and _univ.is_live_universe,
        "source": "live NSE data" if cache else "hardcoded fallback",
    }


@router.post("/refresh")
async def refresh_universe(background_tasks: BackgroundTasks):
    """Force a fresh live fetch of NSE universe data (ignores cache, runs in background)."""
    from ..lib.universe_builder import fetch_universe, save_cache

    async def _do():
        data = await fetch_universe()
        if data and data.get("all_symbols"):
            save_cache(data)
            _univ._apply_live_data(data)

    background_tasks.add_task(_do)
    return {"message": "Universe refresh started — check /api/universe/status in ~30 seconds"}
