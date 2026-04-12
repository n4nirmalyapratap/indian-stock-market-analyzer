"""
Admin Jobs Registry
Tracks all background / on-demand jobs and exposes a unified control plane.

Endpoints (all require X-Admin-Token):
  GET  /api/admin/jobs           — list all jobs with current status
  POST /api/admin/jobs/{id}/run  — trigger a job immediately
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from .admin import _require_admin

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin-jobs"])

# ── Job registry ───────────────────────────────────────────────────────────────

class _Job:
    def __init__(
        self,
        id: str,
        name: str,
        description: str,
        category: str,
        icon: str,
    ):
        self.id          = id
        self.name        = name
        self.description = description
        self.category    = category
        self.icon        = icon
        self.status      = "idle"   # idle | running | success | error
        self.last_run_ts: float | None = None
        self.duration_s: float | None  = None
        self.last_result: str          = ""
        self._running    = False

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "name":        self.name,
            "description": self.description,
            "category":    self.category,
            "icon":        self.icon,
            "status":      self.status,
            "last_run":    self.last_run_ts,
            "duration_s":  self.duration_s,
            "last_result": self.last_result,
        }

    async def run(self) -> None:
        if self._running:
            return
        self._running  = True
        self.status    = "running"
        self.last_run_ts = time.time()
        t0 = time.time()
        try:
            result = await self._execute()
            self.status      = "success"
            self.last_result = result or "Completed successfully"
        except Exception as exc:
            self.status      = "error"
            self.last_result = str(exc)
            logger.exception("Job %s failed", self.id)
        finally:
            self.duration_s = round(time.time() - t0, 1)
            self._running   = False

    async def _execute(self) -> str:
        raise NotImplementedError


# ── Concrete job implementations ───────────────────────────────────────────────

class _CacheWarmupJob(_Job):
    async def _execute(self) -> str:
        from app.services.market_cache_service import warmup_cache
        from app.services.yahoo_service import YahooService
        from app.services.nse_service import NseService
        from app.services.price_service import PriceService
        price = PriceService(NseService(), YahooService())
        result = await warmup_cache(price)
        loaded  = result.get("loaded", 0)
        skipped = result.get("skipped", 0)
        errors  = result.get("errors", 0)
        return f"Loaded {loaded} symbols, skipped {skipped}, errors {errors}"


class _SentimentRefreshJob(_Job):
    async def _execute(self) -> str:
        from app.services.market_sentiment_engine import MarketSentimentEngine
        engine = MarketSentimentEngine()
        engine._cache = None   # bust in-memory cache
        data = await engine.get_market_sentiment()
        label = data.get("label", "unknown")
        vix   = data.get("vix", {}).get("current", "?")
        return f"Refreshed — sentiment: {label}, VIX: {vix}"


class _UniverseRefreshJob(_Job):
    async def _execute(self) -> str:
        from app.lib.universe_builder import fetch_universe, save_cache
        from app.lib import universe as _univ
        data = await fetch_universe()
        if data and data.get("all_symbols"):
            save_cache(data)
            _univ._apply_live_data(data)
            n = len(data["all_symbols"])
            return f"Updated — {n} symbols loaded from NSE live data"
        return "No live data returned (using hardcoded fallback)"


class _HydraDBSyncJob(_Job):
    async def _execute(self) -> str:
        from app.services import hydra_db_service as db
        from app.lib.universe import NIFTY100
        symbols = NIFTY100[:50]
        results = await db.bulk_update(symbols)
        inserted = sum(r.get("inserted", 0) for r in results if isinstance(r, dict))
        return f"Synced {len(symbols)} Nifty50 stocks — {inserted} new price rows inserted"


class _PatternScanJob(_Job):
    async def _execute(self) -> str:
        from app.services.patterns_service import PatternsService
        svc     = PatternsService()
        results = await svc.run_scan()
        n = len(results) if isinstance(results, list) else 0
        return f"Scan complete — {n} patterns found across universe"


class _CacheStatusJob(_Job):
    async def _execute(self) -> str:
        from app.services.market_cache_service import cache_status
        s = cache_status()
        loaded = s.get("loaded_symbols", 0)
        total  = s.get("total_symbols", 0)
        return f"Cache healthy — {loaded}/{total} symbols loaded"


# ── Register all jobs ──────────────────────────────────────────────────────────

_JOBS: dict[str, _Job] = {}

def _reg(job: _Job) -> None:
    _JOBS[job.id] = job

_reg(_CacheWarmupJob(
    id="cache_warmup",
    name="Cache Warmup",
    description="Pre-loads NSE market data into memory for fast frontend response. Fetches from NSE first, Yahoo Finance as fallback.",
    category="Market Data",
    icon="database",
))
_reg(_SentimentRefreshJob(
    id="sentiment_refresh",
    name="Sentiment Refresh",
    description="Clears the 15-minute sentiment cache and re-computes market sentiment: India VIX, PCR proxy, news mood, and price action signals.",
    category="Analysis",
    icon="activity",
))
_reg(_UniverseRefreshJob(
    id="universe_refresh",
    name="Universe Refresh",
    description="Downloads the latest NSE stock universe (symbols, sectors, market-cap categories) from official NSE/AMFI sources.",
    category="Market Data",
    icon="globe",
))
_reg(_HydraDBSyncJob(
    id="hydra_db_sync",
    name="Hydra DB Sync",
    description="Updates the Hydra price database with the latest Nifty 50 daily prices from Yahoo Finance. Used by AI forecasts, pairs trading, and VaR engine.",
    category="AI Engine",
    icon="cpu",
))
_reg(_PatternScanJob(
    id="pattern_scan",
    name="Pattern Scan",
    description="Scans the Nifty 100 universe for candlestick patterns (hammer, doji, engulfing, etc.) and updates the pattern cache.",
    category="Analysis",
    icon="bar-chart",
))
_reg(_CacheStatusJob(
    id="cache_healthcheck",
    name="Cache Health Check",
    description="Queries the current cache status and verifies that market data is populated. Non-destructive read-only check.",
    category="Monitoring",
    icon="heart-pulse",
))


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/admin/jobs")
async def list_jobs(request: Request):
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    return {"jobs": [j.to_dict() for j in _JOBS.values()]}


@router.post("/admin/jobs/{job_id}/run")
async def run_job(job_id: str, request: Request, background_tasks: BackgroundTasks):
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    job = _JOBS.get(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"error": f"Job '{job_id}' not found"})
    if job._running:
        return JSONResponse(status_code=409, content={"error": "Job is already running"})
    background_tasks.add_task(job.run)
    return {"job_id": job_id, "status": "started", "message": f"'{job.name}' started in background"}
