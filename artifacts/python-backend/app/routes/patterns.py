from fastapi import APIRouter, Query
from typing import Optional
from ..services import registry as svc
from ..services import market_cache_service as _disk

router = APIRouter(prefix="/patterns", tags=["patterns"])


def _meta() -> dict:
    state = _disk.current_market_state()
    return {
        "source":       "NSE",
        "servedFrom":   "PATTERNS_ENGINE",
        "asOf":         _disk._now_ist().isoformat(),
        "marketState":  state,
        "eodSealed":    state in ("CLOSED", "WEEKEND"),
        "eodDate":      _disk._eod_date_for(state),
        "cacheVersion": _disk.cache_version(),
    }


async def _get_patterns(
    universe: Optional[str] = Query(None),
    signal: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
):
    res = await svc.patterns.get_patterns(universe, signal, category)
    if isinstance(res, dict):
        res.setdefault("meta", _meta())
    return res

router.add_api_route("",  _get_patterns, methods=["GET"])
router.add_api_route("/", _get_patterns, methods=["GET"])


@router.post("/scan")
async def trigger_scan():
    return await svc.patterns.trigger_scan()
