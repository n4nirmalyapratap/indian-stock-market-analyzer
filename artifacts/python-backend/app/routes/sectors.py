from fastapi import APIRouter, HTTPException
from ..services.sectors_service import SectorsService
from ..services.nse_service import NseService
from ..services.yahoo_service import YahooService

router = APIRouter(prefix="/sectors", tags=["sectors"])

_nse = NseService()
_yahoo = YahooService()
_service = SectorsService(_nse, _yahoo)


@router.get("/")
async def get_sectors():
    return await _service.get_all_sectors()


@router.get("/rotation")
async def get_rotation():
    return await _service.get_sector_rotation()


@router.get("/{symbol:path}")
async def get_sector(symbol: str):
    data = await _service.get_sector_detail(symbol)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Sector '{symbol}' not found")
    return data
