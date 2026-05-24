from fastapi import APIRouter
from fastapi.responses import JSONResponse
from ..services import registry as svc

router = APIRouter(prefix="/sectors", tags=["sectors"])


async def _get_sectors():
    return await svc.sectors.get_all_sectors()

router.add_api_route("",  _get_sectors, methods=["GET"])
router.add_api_route("/", _get_sectors, methods=["GET"])


@router.get("/rotation")
async def get_rotation():
    return await svc.sectors.get_sector_rotation()


@router.get("/{symbol:path}")
async def get_sector(symbol: str):
    data = await svc.sectors.get_sector_detail(symbol)
    if data is None:
        return JSONResponse(status_code=404, content={"error": f"Sector '{symbol}' not found"})
    return data
