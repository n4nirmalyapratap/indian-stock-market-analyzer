"""
Analytics routes: sector correlation, breadth history, pattern stats, top movers, sector heatmap.
"""
from fastapi import APIRouter, Query
from typing import Optional
from ..services.analytics_service import AnalyticsService
from ..services.yahoo_service import YahooService
from ..services.nse_service import NseService
from ..services.sectors_service import SectorsService
from ..services.patterns_service import PatternsService

router = APIRouter(prefix="/analytics", tags=["analytics"])

_yahoo    = YahooService()
_nse      = NseService()
_sectors  = SectorsService(_nse, _yahoo)
_patterns = PatternsService(_yahoo, _nse)
_service  = AnalyticsService(_yahoo, _nse, _sectors, _patterns)


@router.get("/sector-correlation")
async def get_sector_correlation(days: int = Query(30, ge=7, le=90)):
    return await _service.get_sector_correlation(days)


@router.get("/breadth-history")
async def get_breadth_history(days: int = Query(30, ge=5, le=90)):
    return await _service.get_breadth_history(days)


@router.get("/top-movers")
async def get_top_movers():
    return await _service.get_top_movers()


@router.get("/pattern-stats")
async def get_pattern_stats():
    return await _service.get_pattern_stats()


@router.get("/sector-heatmap")
async def get_sector_heatmap():
    return await _service.get_sector_heatmap()
