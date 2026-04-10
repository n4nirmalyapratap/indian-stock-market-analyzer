"""
Sector Analytics Routes
=======================
/api/sector-analytics/heatmap              → all sectors with multi-period perf + market cap
/api/sector-analytics/top-movers?period=1d → top 5 gainers + losers
/api/sector-analytics/{sector}/detail      → full deep-dive for one sector
"""

from fastapi import APIRouter, Query, HTTPException
from ..services.sector_analytics_service import SectorAnalyticsService
from ..services.sectors_service import SectorsService
from ..services.nse_service import NseService
from ..services.yahoo_service import YahooService

router = APIRouter(prefix="/sector-analytics", tags=["sector-analytics"])

_nse     = NseService()
_yahoo   = YahooService()
_sectors = SectorsService(_nse, _yahoo)
_svc     = SectorAnalyticsService(_yahoo)


@router.get("/heatmap")
async def heatmap():
    live = await _sectors.get_all_sectors()
    return await _svc.get_heatmap(live)


@router.get("/top-movers")
async def top_movers(period: str = Query("1d", pattern="^(1d|1w|1m|1y)$")):
    live = await _sectors.get_all_sectors()
    hm   = await _svc.get_heatmap(live)
    return await _svc.get_top_movers(hm, period)


@router.get("/{sector}/detail")
async def sector_detail(
    sector: str,
    period: str = Query("1y", pattern="^(3mo|6mo|1y|5y)$"),
):
    data = await _svc.get_sector_detail(sector, period)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Sector '{sector}' not found")
    return data
