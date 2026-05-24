"""
Analytics routes: sector correlation, breadth history, pattern stats, top movers, sector heatmap.
"""
from fastapi import APIRouter, Query
from typing import Optional
from ..services import registry as svc

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/sector-correlation")
async def get_sector_correlation(days: int = Query(30, ge=7, le=90)):
    return await svc.analytics.get_sector_correlation(days)


@router.get("/breadth-history")
async def get_breadth_history(days: int = Query(30, ge=5, le=90)):
    return await svc.analytics.get_breadth_history(days)


@router.get("/top-movers")
async def get_top_movers():
    return await svc.analytics.get_top_movers()


@router.get("/pattern-stats")
async def get_pattern_stats():
    return await svc.analytics.get_pattern_stats()


@router.get("/sector-heatmap")
async def get_sector_heatmap():
    return await svc.analytics.get_sector_heatmap()
