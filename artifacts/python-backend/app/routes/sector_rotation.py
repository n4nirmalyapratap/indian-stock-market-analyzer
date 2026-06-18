"""Sector-Rotation cockpit endpoints — RRG, top-down funnel, and the
winning-stocks shortlist. All read-only; heavy builds are cached in the service.
"""
from fastapi import APIRouter, Query

from ..services import sector_rotation_service as svc

router = APIRouter(prefix="/sector-rotation", tags=["sector-rotation"])


@router.get("/rrg")
async def rrg(
    level: str = Query("sector", pattern="^(sector|subindustry)$"),
    timeframe: str = Query("short", pattern="^(short|mid|long)$"),
):
    """Relative Rotation Graph + RS%-over-timeframe for sectors or sub-industries
    vs Nifty 50. timeframe: short=1M, mid=3M, long=6M."""
    return await svc.get_rrg(level, timeframe)


@router.get("/funnel")
async def funnel(timeframe: str = Query("short", pattern="^(short|mid|long)$")):
    """Top-down feed: NSE sectors (RRG quadrant + RS%-over-timeframe +
    quantity-weighted delivery) plus the sub-industry grid."""
    return await svc.funnel(timeframe)


@router.get("/shortlist")
async def shortlist(subIndustry: str = Query(None), sector: str = Query(None)):
    """Ranked 'winning stocks' inside a sub-industry OR an NSE sector index
    (relative strength + delivery + above-trend composite)."""
    if not subIndustry and not sector:
        return {"available": False, "stocks": [], "note": "Provide subIndustry or sector."}
    return await svc.shortlist(sub_industry=subIndustry, sector=sector)
