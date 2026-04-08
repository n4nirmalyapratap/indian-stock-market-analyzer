from fastapi import APIRouter, HTTPException
from typing import Any
from ..services.scanners_service import ScannersService
from ..services.yahoo_service import YahooService
from ..services.nse_service import NseService

router = APIRouter(prefix="/scanners", tags=["scanners"])

_yahoo = YahooService()
_nse = NseService()
_service = ScannersService(_yahoo, _nse)


@router.get("/")
async def get_scanners():
    return _service.get_all_scanners()


@router.post("/")
async def create_scanner(body: dict[str, Any]):
    return _service.create_scanner(body)


@router.post("/adhoc/run")
async def run_adhoc(body: dict[str, Any]):
    return await _service.run_adhoc(body)


@router.get("/{scanner_id}")
async def get_scanner(scanner_id: str):
    s = _service.get_scanner_by_id(scanner_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Scanner not found")
    return s


@router.put("/{scanner_id}")
async def update_scanner(scanner_id: str, body: dict[str, Any]):
    s = _service.update_scanner(scanner_id, body)
    if s is None:
        raise HTTPException(status_code=404, detail="Scanner not found")
    return s


@router.delete("/{scanner_id}")
async def delete_scanner(scanner_id: str):
    ok = _service.delete_scanner(scanner_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Scanner not found")
    return {"deleted": True, "id": scanner_id}


@router.post("/{scanner_id}/run")
async def run_scanner(scanner_id: str):
    result = await _service.run_scanner(scanner_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
