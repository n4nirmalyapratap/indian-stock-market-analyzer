"""
Sector Analytics Routes
=======================
/api/sector-analytics/heatmap              → all sectors with multi-period perf + market cap
/api/sector-analytics/top-movers?period=1d → top 5 gainers + losers
/api/sector-analytics/{sector}/detail      → full deep-dive for one sector

Hyper-granular synthetic sub-industry rotation engine:
/api/sector-analytics/synthetic/grid               → all sub-industries (RS / delivery / breadth)
/api/sector-analytics/synthetic/{subIndustry}/drilldown → constituents ranked by cap weight
"""

import asyncio

from fastapi import APIRouter, Query, HTTPException
from ..services import registry as svc
from ..services import synthetic_sectors_service as synth

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


@router.get("/synthetic/grid")
async def synthetic_grid():
    """Hyper-granular rotation grid — one row per Yahoo sub-industry with 30D
    RS vs Nifty 50, delivery build-up vs 20-DMA, and 50-EMA breadth. Returns
    an honest `available: false` state until the nightly worker has run."""
    return await asyncio.to_thread(synth.get_grid)


@router.get("/synthetic/{sub_industry}/drilldown")
async def synthetic_drilldown(sub_industry: str):
    """Constituents of one sub-industry ranked by market-cap weight."""
    return await asyncio.to_thread(synth.get_drilldown, sub_industry, svc.yahoo)


@router.get("/{sector}/detail")
async def sector_detail(
    sector: str,
    period: str = Query("1y", pattern="^(3mo|6mo|1y|5y)$"),
):
    data = await svc.sector_analytics.get_sector_detail(sector, period)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Sector '{sector}' not found")
    return data
