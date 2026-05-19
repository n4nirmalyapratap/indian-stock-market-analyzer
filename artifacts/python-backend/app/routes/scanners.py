from fastapi import APIRouter
from fastapi.responses import JSONResponse
from typing import Any
from ..services.scanners_service import ScannersService
from ..services.yahoo_service import YahooService
from ..services.nse_service import NseService
from ..services.price_service import PriceService
from ..services import market_cache_service as _disk

router = APIRouter(prefix="/scanners", tags=["scanners"])

_yahoo = YahooService()
_nse   = NseService()
_price = PriceService(_nse, _yahoo)
_service = ScannersService(_price)


def _meta() -> dict:
    from ..lib.universe import universe_freshness
    state = _disk.current_market_state()
    return {
        "source":       "NSE",
        "servedFrom":   "PRICE_SERVICE",
        "asOf":         _disk._now_ist().isoformat(),
        "marketState":  state,
        "eodSealed":    state in ("CLOSED", "WEEKEND"),
        "eodDate":      _disk._eod_date_for(state),
        "cacheVersion": _disk.cache_version(),
        "universe":     universe_freshness(),
    }


async def _get_scanners():
    res = _service.get_all_scanners()
    if isinstance(res, list):
        return {"scanners": res, "meta": _meta()}
    if isinstance(res, dict):
        res.setdefault("meta", _meta())
    return res

async def _create_scanner(body: dict[str, Any]):
    return _service.create_scanner(body)

router.add_api_route("",  _get_scanners,    methods=["GET"])
router.add_api_route("/", _get_scanners,    methods=["GET"])
router.add_api_route("",  _create_scanner,  methods=["POST"])
router.add_api_route("/", _create_scanner,  methods=["POST"])


@router.post("/adhoc/run")
async def run_adhoc(body: dict[str, Any]):
    res = await _service.run_adhoc(body)
    if isinstance(res, dict):
        res.setdefault("meta", _meta())
    return res


@router.get("/{scanner_id}")
async def get_scanner(scanner_id: str):
    s = _service.get_scanner_by_id(scanner_id)
    if s is None:
        return JSONResponse(status_code=404, content={"error": "Scanner not found"})
    return s


@router.put("/{scanner_id}")
async def update_scanner(scanner_id: str, body: dict[str, Any]):
    s = _service.update_scanner(scanner_id, body)
    if s is None:
        return JSONResponse(status_code=404, content={"error": "Scanner not found"})
    return s


@router.delete("/{scanner_id}")
async def delete_scanner(scanner_id: str):
    ok = _service.delete_scanner(scanner_id)
    if not ok:
        return JSONResponse(status_code=404, content={"error": "Scanner not found"})
    return {"success": True, "id": scanner_id}


@router.post("/{scanner_id}/run")
async def run_scanner(scanner_id: str):
    result = await _service.run_scanner(scanner_id)
    if "error" in result:
        return JSONResponse(status_code=404, content={"error": result["error"]})
    return result
