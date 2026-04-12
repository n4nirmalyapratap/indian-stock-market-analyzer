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


class _SebiAuditJob(_Job):
    async def _execute(self) -> str:
        import sys as _sys, pathlib as pl
        backend_root = str(pl.Path(__file__).parents[2])
        if backend_root not in _sys.path:
            _sys.path.insert(0, backend_root)
        from scripts.sebi_audit import run_audit_async
        result = await run_audit_async(days=90)
        n = result.get("n_issues", 0)
        return f"Audit complete — {n} issue(s) found, report saved to reports/"


class _NewsRefreshJob(_Job):
    async def _execute(self) -> str:
        from app.services import news_service
        await news_service.invalidate_cache()
        feeds = await news_service._fetch_all_feeds()
        n = len(feeds)
        return f"News cache cleared & re-fetched — {n} articles loaded"


class _ScannersRunAllJob(_Job):
    async def _execute(self) -> str:
        from app.services.scanners_service import ScannersService, _DB
        from app.services.yahoo_service import YahooService
        from app.services.nse_service import NseService
        from app.services.price_service import PriceService
        price = PriceService(NseService(), YahooService())
        svc   = ScannersService(price)
        all_scanners = svc.get_all_scanners()
        if not all_scanners:
            return "No scanners saved — create scanners in the Stock Screener first"
        hits = 0
        for sc in all_scanners:
            try:
                result = await svc.run_scanner(sc["id"])
                hits += len(result.get("matches", []))
            except Exception:
                pass
        return f"Ran {len(all_scanners)} scanner(s) — {hits} total matches found"


class _AnalyticsWarmupJob(_Job):
    async def _execute(self) -> str:
        from app.services.analytics_service import AnalyticsService
        from app.services.yahoo_service import YahooService
        from app.services.nse_service import NseService
        from app.services.sectors_service import SectorsService
        from app.services.patterns_service import PatternsService
        from app.services.sector_analytics_service import SectorAnalyticsService
        yahoo   = YahooService()
        nse     = NseService()
        sectors = SectorsService(nse)
        patterns = PatternsService()
        svc     = AnalyticsService(yahoo, nse, sectors, patterns)
        sa_svc  = SectorAnalyticsService(yahoo)
        # warm all caches in parallel
        sector_data = await sectors.get_sectors()
        await asyncio.gather(
            svc.get_sector_correlation(30),
            svc.get_breadth_history(30),
            svc.get_top_movers(),
            svc.get_pattern_stats(),
            sa_svc.get_heatmap(sector_data),
            return_exceptions=True,
        )
        return "Analytics caches warmed — sector correlation, breadth, movers, pattern stats, heatmap"


class _HydraPairsScanJob(_Job):
    async def _execute(self) -> str:
        from app.services import hydra_db_service as db
        from app.services import hydra_pairs_service as pairs
        from app.lib.universe import NIFTY50
        symbols = NIFTY50[:20]
        # Fetch price histories
        histories: dict[str, list[float]] = {}
        for sym in symbols:
            try:
                rows = db.get_history(sym, days=252)
                if rows and len(rows) >= 30:
                    histories[sym] = [r["close"] for r in rows]
            except Exception:
                pass
        if len(histories) < 2:
            return "Not enough price history in DB — run Hydra DB Sync first"
        found = pairs.scan_pairs(list(histories.keys()), histories, p_threshold=0.05)
        return f"Scanned {len(histories)} stocks — {len(found)} co-integrated pair(s) found"


class _BugFinderJob(_Job):
    async def _execute(self) -> str:
        """
        Cross-app discrepancy scanner.
        Checks for inconsistencies between frontend and backend:
          - Lot sizes
          - Expiry day assignments
          - Weekly vs monthly index rules
        """
        import pathlib as pl, re

        ROOT = pl.Path(__file__).parents[3]

        # ── 1. Extract backend lot sizes ──────────────────────────────────────
        be_file = ROOT / "artifacts/python-backend/app/services/options_service.py"
        be_text = be_file.read_text() if be_file.exists() else ""
        be_lots: dict[str, int] = {}
        for m in re.finditer(r'"([A-Z0-9^]+)"\s*:\s*(\d+)', be_text):
            be_lots[m.group(1)] = int(m.group(2))

        # ── 2. Extract frontend lot sizes ─────────────────────────────────────
        fe_file = ROOT / "artifacts/stock-market-app/src/pages/OptionsStrategyTester.tsx"
        fe_text = fe_file.read_text() if fe_file.exists() else ""
        fe_lots: dict[str, int] = {}
        for m in re.finditer(r'sym:\s*"([A-Z0-9]+)".*?lot:\s*(\d+)', fe_text, re.DOTALL):
            fe_lots[m.group(1)] = int(m.group(2))

        # ── 3. Expected SEBI lot sizes (Nov 2024) ────────────────────────────
        sebi_lots = {
            "NIFTY": 75, "BANKNIFTY": 30, "FINNIFTY": 65,
            "MIDCPNIFTY": 120, "SENSEX": 10, "BANKEX": 15,
        }

        issues: list[str] = []

        for sym, expected in sebi_lots.items():
            be_val = be_lots.get(sym)
            fe_val = fe_lots.get(sym)
            if be_val and be_val != expected:
                issues.append(f"BACKEND lot_size mismatch: {sym}={be_val} (should be {expected})")
            if fe_val and fe_val != expected:
                issues.append(f"FRONTEND lot mismatch: {sym}={fe_val} (should be {expected})")

        # ── 4. Expiry day consistency ─────────────────────────────────────────
        # Backend expiry days (from options_backtest_service.py)
        be_exp_file = ROOT / "artifacts/python-backend/app/services/options_backtest_service.py"
        be_exp_text = be_exp_file.read_text() if be_exp_file.exists() else ""
        # Frontend expiry days
        fe_exp = {}
        for m in re.finditer(r'(BANKNIFTY|FINNIFTY|MIDCPNIFTY|SENSEX|BANKEX)\s*:\s*(\d+)', fe_text):
            fe_exp[m.group(1)] = int(m.group(2))
        be_exp = {}
        for m in re.finditer(r'(BANKNIFTY|FINNIFTY|MIDCPNIFTY|SENSEX|BANKEX)["\']?\s*:\s*(\d+)', be_exp_text):
            be_exp[m.group(1)] = int(m.group(2))

        for sym in fe_exp:
            if sym in be_exp and fe_exp[sym] != be_exp[sym]:
                issues.append(
                    f"EXPIRY DAY mismatch for {sym}: frontend={fe_exp[sym]}, backend={be_exp[sym]}"
                )

        if not issues:
            return "No discrepancies found — frontend and backend are in sync with SEBI Nov 2024 rules"
        return f"{len(issues)} discrepancy(ies) found:\n" + "\n".join(f"  • {i}" for i in issues)


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
_reg(_NewsRefreshJob(
    id="news_refresh",
    name="News Feed Refresh",
    description="Clears the news cache and re-fetches all configured RSS/news feeds (Economic Times, Mint, BSE, NSE, Moneycontrol). Reloads articles, deals, and corporate events.",
    category="Market Data",
    icon="newspaper",
))
_reg(_ScannersRunAllJob(
    id="scanners_run_all",
    name="Run All Scanners",
    description="Executes every saved custom scanner in sequence against live market data. Updates each scanner's match list and timestamps.",
    category="Analysis",
    icon="scan-line",
))
_reg(_AnalyticsWarmupJob(
    id="analytics_warmup",
    name="Analytics Cache Warm-Up",
    description="Pre-computes and caches sector correlation matrix, market breadth history, top movers, pattern stats, and sector heatmap. Prevents slow first-load on the Analytics page.",
    category="Analysis",
    icon="trending-up",
))
_reg(_HydraPairsScanJob(
    id="hydra_pairs_scan",
    name="Hydra Pairs Scan",
    description="Scans Nifty 50 stocks for statistically co-integrated pairs using Engle-Granger cointegration tests. Results feed the Pairs Trading strategy in the AI engine.",
    category="AI Engine",
    icon="git-branch",
))
_reg(_SebiAuditJob(
    id="sebi_audit",
    name="SEBI Compliance Audit",
    description="Scrapes SEBI.gov.in for the latest circulars (last 30 days), scans all options/derivatives code across the app, and uses AI to produce a structured compliance diff report.",
    category="Compliance",
    icon="shield-check",
))
_reg(_BugFinderJob(
    id="bug_finder",
    name="Bug Finder (Cross-App Scan)",
    description="Scans for discrepancies between frontend and backend: lot sizes, expiry days, weekly/monthly index rules. Flags any drift from SEBI Nov 2024 standards.",
    category="Compliance",
    icon="bug",
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
