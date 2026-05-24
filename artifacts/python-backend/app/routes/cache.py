from fastapi import APIRouter, BackgroundTasks
from app.services.market_cache_service import cache_status, warmup_cache
from app.services import registry as svc

router = APIRouter()

_warmup_running = False


@router.get("/cache/status")
def get_cache_status():
    return cache_status()


@router.post("/cache/warmup")
async def trigger_warmup(background_tasks: BackgroundTasks):
    global _warmup_running
    if _warmup_running:
        return {"status": "already_running", "message": "Warmup already in progress"}
    _warmup_running = True

    async def _run():
        global _warmup_running
        try:
            result = await warmup_cache(svc.price)
            return result
        finally:
            _warmup_running = False

    background_tasks.add_task(_run)
    return {
        "status": "started",
        "message": "Cache warmup started in background — NSE primary, Yahoo fallback. Check /api/cache/status.",
    }
