"""Top Movers route — powers the Dashboard 'Top Movers' tab.

  GET /api/dashboard/top-movers?segment=large|mid|small|micro&count=10
  GET /api/dashboard/top-movers/all?count=10

The single-segment endpoint is handy for the segment-pill switcher (no need
to re-fetch the other three when the user clicks 'Mid Cap'); the /all
endpoint is what the page calls on first mount so every panel arrives in
one round-trip.
"""
from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from ..services.top_movers_service import TopMoversService, SEGMENT_INDEX

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_svc = TopMoversService()


@router.get("/top-movers")
async def top_movers(
    segment: str = Query("large", description="large | mid | small | micro"),
    count:   int = Query(10, ge=1, le=50,
                         description="Number of gainers AND losers to return (each)"),
):
    """Top gainers + losers for a single market-cap segment."""
    if segment not in SEGMENT_INDEX:
        return JSONResponse(status_code=400, content={
            "error":   f"Unknown segment {segment!r}",
            "allowed": sorted(SEGMENT_INDEX),
        })
    return await _svc.get_top_movers(segment, count=count)


@router.get("/top-movers/all")
async def top_movers_all(
    count: int = Query(10, ge=1, le=50,
                       description="Number of gainers AND losers per segment"),
):
    """All four cap segments in one round-trip — used by the Dashboard tab
    on initial render."""
    return await _svc.get_all_segments(count=count)
