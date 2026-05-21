"""
ai_analyst.py — REST + SSE endpoints for the Deep AI Analyst feature.

Endpoints (all behind JWT, like every other /api route):
  POST /api/ai-analyst/run                     — SSE stream (ticker in JSON body)
  POST /api/ai-analyst/run/{ticker}            — SSE stream (ticker in path, alias)
  GET  /api/ai-analyst/report/{ticker}         — cached report or 404
  GET  /api/ai-analyst/quota                   — remaining quota for caller
  POST /api/ai-analyst/compare?a=…&b=…         — run two analyses in parallel (JSON)
  POST /api/ai-analyst/scan                    — SSE scan of a watchlist (JSON body)
  GET  /api/ai-analyst/admin/stats             — admin-only (strict X-Admin-Token)
  POST /api/ai-analyst/admin/flush             — admin-only (strict X-Admin-Token)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import AsyncGenerator, List, Optional

from fastapi import APIRouter, Request, Query, HTTPException, Body
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..services import ai_analyst_service as svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai-analyst", tags=["ai-analyst"])


def _user_id(request: Request) -> str:
    return getattr(request.state, "user_id", "anonymous") or "anonymous"


def _require_admin(request: Request) -> None:
    """Strict admin gate: require a valid X-Admin-Token header on the request,
    independent of any bearer-auth identity. Bearer-auth callers — even if
    their JWT subject literally equals 'admin' — cannot reach admin routes."""
    token = request.headers.get("X-Admin-Token", "")
    if not token:
        raise HTTPException(403, "X-Admin-Token required")
    try:
        from ..routes.admin import _valid_session  # noqa: PLC0415
    except Exception as e:  # pragma: no cover
        logger.error("admin token validator unavailable: %s", e)
        raise HTTPException(503, "admin auth unavailable") from e
    if not _valid_session(token):
        raise HTTPException(403, "invalid admin token")


@router.get("/feature")
async def feature():
    return {"enabled": svc.feature_enabled()}


@router.get("/quota")
async def quota(request: Request):
    return svc.get_quota(_user_id(request))


@router.get("/report/{ticker}")
async def report(ticker: str, request: Request):
    rpt = svc.get_saved_single(ticker, _user_id(request))
    if not rpt:
        return JSONResponse(status_code=404,
                            content={"error": "no saved report for this ticker"})
    return rpt


async def _sse_stream(gen: AsyncGenerator[dict, None]) -> AsyncGenerator[bytes, None]:
    """Wrap dict events into SSE `data: <json>\\n\\n` frames."""
    try:
        async for event in gen:
            payload = json.dumps(event, default=str)
            yield f"data: {payload}\n\n".encode("utf-8")
    except Exception as e:
        logger.exception("AI analyst stream error")
        err = json.dumps({"phase": "error", "status": "error",
                          "error": str(e)[:200]})
        yield f"data: {err}\n\n".encode("utf-8")


class RunPayload(BaseModel):
    ticker: str
    force: Optional[bool] = False


def _stream_response(gen):
    return StreamingResponse(
        _sse_stream(gen),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",   # disable nginx-style proxy buffering
        },
    )


@router.post("/run")
async def run_body(request: Request, payload: RunPayload = Body(...)):
    """SSE stream — ticker provided in JSON body (per task spec)."""
    if not svc.feature_enabled():
        raise HTTPException(503, "AI Analyst feature is disabled")
    ticker = _validate_ticker(payload.ticker)
    return _stream_response(
        svc.run_analysis(ticker, _user_id(request),
                         force_refresh=bool(payload.force))
    )


@router.post("/run/{ticker}")
async def run_path(ticker: str, request: Request,
                   force: bool = Query(False)):
    """SSE stream — ticker in path (alias of POST /run, kept for the
    frontend's path-style URLs)."""
    if not svc.feature_enabled():
        raise HTTPException(503, "AI Analyst feature is disabled")
    ticker = _validate_ticker(ticker)
    return _stream_response(
        svc.run_analysis(ticker, _user_id(request), force_refresh=force)
    )


_TICKER_RX = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,19}$")


def _validate_ticker(t: str) -> str:
    """Reject empty or unsafe tickers before they reach the prompt/DB layer."""
    u = (t or "").strip().upper()
    if not _TICKER_RX.match(u):
        raise HTTPException(400, f"invalid ticker: {t!r}")
    return u


@router.post("/compare")
async def compare(request: Request,
                  a: str = Query(...), b: str = Query(...),
                  force: bool = Query(False)):
    """Run two analyses in parallel. Serves the per-user saved single
    report when present; ``force=true`` re-runs both. The combined pair
    is also persisted as a saved entry under the sorted scope key
    ``A|B`` so the user can re-open it from Saved Analyses."""
    if not svc.feature_enabled():
        raise HTTPException(503, "AI Analyst feature is disabled")
    a = _validate_ticker(a)
    b = _validate_ticker(b)
    user = _user_id(request)

    # Pre-check quota: if both sides need a fresh run, ensure we have at
    # least 2 slots so a parallel fan-out can't push the user to -1.
    if force or not svc.get_saved_single(a, user) or not svc.get_saved_single(b, user):
        need = 0
        if force or not svc.get_saved_single(a, user):
            need += 1
        if force or not svc.get_saved_single(b, user):
            need += 1
        q = svc.get_quota(user)
        if q.get("remaining", 0) < need:
            raise HTTPException(
                429,
                f"daily AI Analyst quota exhausted — need {need} run(s), "
                f"have {q.get('remaining', 0)} of {q.get('limit', 0)} left",
            )

    async def _one(t: str) -> dict:
        if not force:
            saved = svc.get_saved_single(t, user)
            if saved:
                return saved
        # Drain the generator into the final report
        final = None
        async for ev in svc.run_analysis(t, user, force_refresh=force):
            if ev.get("phase") == "done":
                final = ev.get("report")
            elif ev.get("phase") == "error":
                return {"ticker": t.upper(),
                        "error": ev.get("error", "unknown error")}
        return final or {"ticker": t.upper(), "error": "no report produced"}

    a_rpt, b_rpt = await asyncio.gather(_one(a), _one(b))
    saved_meta = None
    if not (a_rpt.get("error") or b_rpt.get("error")):
        try:
            saved_meta = svc.save_pair(user, a_rpt, b_rpt)
        except Exception as e:  # pragma: no cover
            logger.warning("save_pair failed: %s", e)
    return {"a": a_rpt, "b": b_rpt,
            "quota": svc.get_quota(user),
            "saved": saved_meta}


@router.get("/saved/pair")
async def saved_pair(request: Request,
                     a: str = Query(...), b: str = Query(...)):
    rpt = svc.get_saved_pair(a, b, _user_id(request))
    if not rpt:
        return JSONResponse(status_code=404,
                            content={"error": "no saved pair analysis"})
    return rpt


class ScanPayload(BaseModel):
    tickers: List[str]
    force: Optional[bool] = False
    name: Optional[str] = Field(default=None, max_length=80)


_MAX_SCAN = 50  # accommodates the default Nifty 50 watchlist in one scan


@router.post("/scan")
async def scan(request: Request, payload: ScanPayload = Body(...)):
    """SSE stream — sequentially scan a watchlist of tickers.
    Saved reports are served free; fresh runs respect the daily quota and
    the rest are reported as ``skipped`` once the quota is exhausted.
    The full group is persisted as a saved entry on completion."""
    if not svc.feature_enabled():
        raise HTTPException(503, "AI Analyst feature is disabled")
    if not payload.tickers:
        raise HTTPException(400, "tickers required")
    if len(payload.tickers) > _MAX_SCAN:
        raise HTTPException(
            400, f"too many tickers — max {_MAX_SCAN} per scan")
    cleaned = [_validate_ticker(t) for t in payload.tickers]
    return _stream_response(
        svc.scan_watchlist(cleaned, _user_id(request),
                           force_refresh=bool(payload.force),
                           group_name=payload.name)
    )


@router.get("/saved/group")
async def saved_group(request: Request, tickers: str = Query(...)):
    """Fetch the saved scan/group for the given comma-separated ticker set."""
    parts = [t for t in (tickers or "").split(",") if t.strip()]
    if not parts:
        raise HTTPException(400, "tickers required")
    rpt = svc.get_saved_group(parts, _user_id(request))
    if not rpt:
        return JSONResponse(status_code=404,
                            content={"error": "no saved group analysis"})
    return rpt


@router.get("/saved")
async def saved_list(request: Request,
                     scope: Optional[str] = Query(None),
                     q: Optional[str] = Query(None),
                     limit: int = Query(50, ge=1, le=200),
                     offset: int = Query(0, ge=0)):
    return svc.list_saved(_user_id(request), scope=scope, q=q,
                          limit=limit, offset=offset)


@router.get("/saved/{sid}")
async def saved_get(sid: int, request: Request):
    rpt = svc.get_saved_by_id(_user_id(request), sid)
    if not rpt:
        raise HTTPException(404, "saved analysis not found")
    return rpt


@router.delete("/saved/{sid}")
async def saved_delete(sid: int, request: Request):
    ok = svc.delete_saved(_user_id(request), sid)
    if not ok:
        raise HTTPException(404, "saved analysis not found")
    return {"deleted": sid}


class BulkDeleteBody(BaseModel):
    """Body for the bulk-delete endpoint. Capped at 500 ids so a runaway
    client can't trigger an expensive ANY-array delete."""
    ids: list[int] = Field(..., min_length=1, max_length=500)


@router.post("/saved/bulk-delete")
async def saved_delete_bulk(body: BulkDeleteBody, request: Request):
    """Delete many saved analyses in one call.

    Returns the number of rows actually deleted. We POST (not DELETE) with
    a body because DELETE-with-body has spotty support across nginx /
    cloudflare / corporate proxies.
    """
    count = svc.delete_saved_bulk(_user_id(request), body.ids)
    return {"requested": len(body.ids), "deleted": count}


# ── Backtest / track-record endpoints ─────────────────────────────────────────
# Show how the AI Analyst's BUY/SELL verdicts have actually played out.
# Honest stats build trust; hiding them only hides bad calls until users
# notice on their own.

@router.get("/backtest/overall")
async def backtest_overall():
    """App-wide hit rate by horizon and verdict direction."""
    from ..services import ai_backtest_service as _bt  # noqa: PLC0415
    return _bt.get_overall_stats()


@router.get("/backtest/recent")
async def backtest_recent(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    scope: str = Query("me", regex="^(me|all)$"),
):
    """Most recent backtested verdicts. scope=me restricts to the caller;
    scope=all is admin-only and shows the app-wide stream."""
    from ..services import ai_backtest_service as _bt  # noqa: PLC0415
    if scope == "all":
        _require_admin(request)
        return _bt.get_recent_calls(limit=limit)
    return _bt.get_recent_calls(limit=limit, user_id=_user_id(request))


@router.get("/backtest/by-ticker")
async def backtest_by_ticker(symbol: str = Query(..., min_length=1, max_length=24)):
    """Per-ticker track record + last 10 calls."""
    from ..services import ai_backtest_service as _bt  # noqa: PLC0415
    return _bt.get_stats_by_ticker(symbol)


@router.get("/admin/stats")
async def admin_stats(request: Request):
    _require_admin(request)
    return svc.admin_stats()


@router.post("/admin/flush")
async def admin_flush(request: Request):
    _require_admin(request)
    n = svc.flush_cache()
    return {"flushed": n}


@router.put("/admin/quota")
async def admin_set_quota(request: Request, payload: dict):
    """Set the per-user daily quota (admin-only). Body: {"limit": <int>}."""
    _require_admin(request)
    raw = payload.get("limit") if isinstance(payload, dict) else None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(400, "limit must be an integer")
    if n < 1 or n > 1000:
        raise HTTPException(400, "limit must be between 1 and 1000")
    from app.lib.secrets_store import set_secret  # noqa: PLC0415
    set_secret(
        "AI_ANALYST_DAILY_QUOTA",
        value=str(n),
        description=("Deep AI Analyst: max fresh analyses per user per IST "
                     "day (default: 3). Cached reports don't count."),
        masked=False,
    )
    return svc.admin_stats()
