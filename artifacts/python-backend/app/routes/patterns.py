from fastapi import APIRouter, Query
from typing import Optional
from ..services.patterns_service import PatternsService
from ..services.yahoo_service import YahooService
from ..services.nse_service import NseService

router = APIRouter(prefix="/patterns", tags=["patterns"])

_yahoo = YahooService()
_nse = NseService()
_service = PatternsService(_yahoo, _nse)


async def _get_patterns(
    universe: Optional[str] = Query(None),
    signal: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
):
    return await _service.get_patterns(universe, signal, category)

router.add_api_route("",  _get_patterns, methods=["GET"])
router.add_api_route("/", _get_patterns, methods=["GET"])


@router.post("/scan")
async def trigger_scan():
    return await _service.trigger_scan()
