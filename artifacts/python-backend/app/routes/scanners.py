import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from typing import Any
from ..services import registry as svc
from ..services import market_cache_service as _disk

router = APIRouter(prefix="/scanners", tags=["scanners"])
logger = logging.getLogger(__name__)


def _meta() -> dict:
    from ..lib.universe import universe_freshness
    state = _disk.current_market_state()
    return {
        "source":       "NSE",
        "servedFrom":   "PRICE_SERVICE",
        "asOf":         _disk._now_ist().isoformat(),
        "marketState":  state,
        "eodSealed":    state in ("CLOSED", "WEEKEND"),
        "eodDate":      _disk._eod_date_for(state),
        "cacheVersion": _disk.cache_version(),
        "universe":     universe_freshness(),
    }


async def _get_scanners():
    res = svc.scanners.get_all_scanners()
    if isinstance(res, list):
        return {"scanners": res, "meta": _meta()}
    if isinstance(res, dict):
        res.setdefault("meta", _meta())
    return res

async def _create_scanner(body: dict[str, Any]):
    return svc.scanners.create_scanner(body)

router.add_api_route("",  _get_scanners,    methods=["GET"])
router.add_api_route("/", _get_scanners,    methods=["GET"])
router.add_api_route("",  _create_scanner,  methods=["POST"])
router.add_api_route("/", _create_scanner,  methods=["POST"])


@router.post("/adhoc/run")
async def run_adhoc(body: dict[str, Any]):
    res = await svc.scanners.run_adhoc(body)
    if isinstance(res, dict):
        res.setdefault("meta", _meta())
    return res


@router.get("/{scanner_id}")
async def get_scanner(scanner_id: str):
    s = svc.scanners.get_scanner_by_id(scanner_id)
    if s is None:
        return JSONResponse(status_code=404, content={"error": "Scanner not found"})
    return s


@router.put("/{scanner_id}")
async def update_scanner(scanner_id: str, body: dict[str, Any]):
    s = svc.scanners.update_scanner(scanner_id, body)
    if s is None:
        return JSONResponse(status_code=404, content={"error": "Scanner not found"})
    return s


@router.delete("/{scanner_id}")
async def delete_scanner(scanner_id: str):
    ok = svc.scanners.delete_scanner(scanner_id)
    if not ok:
        return JSONResponse(status_code=404, content={"error": "Scanner not found"})
    return {"success": True, "id": scanner_id}


@router.post("/{scanner_id}/run")
async def run_scanner(scanner_id: str):
    """Synchronous run — kept for backward compat (older API consumers
    expect the result back in the response). The UI now prefers the
    async path below for live progress + background execution."""
    result = await svc.scanners.run_scanner(scanner_id)
    if "error" in result:
        return JSONResponse(status_code=404, content={"error": result["error"]})
    return result


# ── Async job-based scan (preferred by the UI for long-running scans) ───────

@router.post("/{scanner_id}/run-job")
async def run_scanner_job(scanner_id: str):
    """Start a scan as a background asyncio task and return the job id
    immediately. Client polls GET /scanners/jobs/{jobId} for progress
    + final result. The scan runs to completion regardless of whether
    the client is still polling — surviving navigation, tab closes, etc.
    """
    import asyncio  # noqa: PLC0415
    from ..services import scan_jobs_service as jobs  # noqa: PLC0415
    from ..lib.universe import build_universe       # noqa: PLC0415

    scanner = svc.scanners.get_scanner_by_id(scanner_id)
    if not scanner:
        return JSONResponse(status_code=404, content={"error": "Scanner not found"})

    universe_size = len(build_universe(scanner["universe"]))
    job_id = await jobs.create_job(
        scanner_id=scanner_id,
        scanner_name=scanner.get("name") or scanner_id,
        universe_size=universe_size,
    )

    async def _run():
        """Background task body. Uses the same run_scanner code path
        as the sync endpoint, but passes a progress_cb that writes to
        the in-memory job record."""
        jobs.mark_running(job_id)
        try:
            def _on_progress(**kwargs):
                # Demux: `match=<row>` goes onto the live partial-
                # matches stream; everything else (scanned, matched,
                # failed, errors, stage, total) is regular progress.
                # A single emit can carry both (one tick that records
                # the count update AND surfaces the new match).
                match = kwargs.pop("match", None)
                if match is not None:
                    jobs.push_match(job_id, match)
                if kwargs:
                    jobs.update_progress(job_id, **kwargs)
            result = await svc.scanners.run_scanner(scanner_id, progress_cb=_on_progress)
            if "error" in result:
                jobs.mark_failed(job_id, result["error"])
            else:
                jobs.mark_completed(job_id, result)
        except Exception as exc:
            logger.exception("scan job %s failed", job_id)
            jobs.mark_failed(job_id, f"{type(exc).__name__}: {exc}")

    # Spawn the task and return immediately. asyncio keeps the task
    # alive until completion even after this handler returns.
    asyncio.create_task(_run())

    return {
        "jobId":       job_id,
        "scannerId":   scanner_id,
        "scannerName": scanner.get("name"),
        "universeSize": universe_size,
        "status":      "queued",
    }


@router.get("/jobs/{job_id}")
async def get_scan_job(job_id: str):
    """Poll a scan job. Returns the live record:
        {jobId, scannerId, scannerName, status, progress: {...},
         result?, error?, startedAt, completedAt?}
    Frontend polls every ~1s while status == 'running'."""
    from ..services import scan_jobs_service as jobs  # noqa: PLC0415
    record = jobs.get(job_id)
    if not record:
        return JSONResponse(status_code=404, content={"error": "Job not found or expired"})
    return record
