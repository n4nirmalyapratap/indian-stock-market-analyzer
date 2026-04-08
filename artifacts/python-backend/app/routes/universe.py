from fastapi import APIRouter, BackgroundTasks
from ..lib.universe_builder import load_cache, get_or_refresh, CACHE_FILE
from ..lib import universe as _univ

router = APIRouter(prefix="/universe", tags=["universe"])


@router.get("/status")
async def universe_status():
    cache = load_cache()
    return {
        "total_symbols":     len(_univ.ALL_SYMBOLS),
        "total_sectors":     len(_univ.SECTOR_SYMBOLS),
        "sectors":           {k: len(v) for k, v in _univ.SECTOR_SYMBOLS.items()},
        "cache_exists":      CACHE_FILE.exists(),
        "cache_generated_at": cache.get("generated_at") if cache else None,
        "live_data_active":  bool(cache),
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
