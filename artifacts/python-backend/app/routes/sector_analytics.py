"""
Sector Analytics Routes
=======================
/api/sector-analytics/heatmap              → all sectors with multi-period perf + market cap
/api/sector-analytics/top-movers?period=1d → top 5 gainers + losers
/api/sector-analytics/{sector}/detail      → full deep-dive for one sector
"""

from fastapi import APIRouter, Query, HTTPException
from ..services import registry as svc

router = APIRouter(prefix="/sector-analytics", tags=["sector-analytics"])


@router.get("/heatmap")
async def heatmap():
    live = await svc.sectors.get_all_sectors()
    return await svc.sector_analytics.get_heatmap(live)


@router.get("/top-movers")
async def top_movers(period: str = Query("1d", pattern="^(1d|1w|1m|1y)$")):
    live = await svc.sectors.get_all_sectors()
    hm   = await svc.sector_analytics.get_heatmap(live)
    return await svc.sector_analytics.get_top_movers(hm, period)


@router.get("/{sector}/detail")
async def sector_detail(
    sector: str,
    period: str = Query("1y", pattern="^(3mo|6mo|1y|5y)$"),
):
    data = await svc.sector_analytics.get_sector_detail(sector, period)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Sector '{sector}' not found")
    return data
