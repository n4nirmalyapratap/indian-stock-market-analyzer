"""
ai_analyst.py — REST + SSE endpoints for the Deep AI Analyst feature.

Endpoints (all behind JWT, like every other /api route):
  POST /api/ai-analyst/run                     — SSE stream (ticker in JSON body)
  POST /api/ai-analyst/run/{ticker}            — SSE stream (ticker in path, alias)
  GET  /api/ai-analyst/report/{ticker}         — cached report or 404
  GET  /api/ai-analyst/quota                   — remaining quota for caller
  POST /api/ai-analyst/compare?a=…&b=…         — run two analyses in parallel (JSON)
  GET  /api/ai-analyst/admin/stats             — admin-only (strict X-Admin-Token)
  POST /api/ai-analyst/admin/flush             — admin-only (strict X-Admin-Token)
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Request, Query, HTTPException, Body
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

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
    rpt = svc.get_cached_report(ticker, _user_id(request))
    if not rpt:
        return JSONResponse(status_code=404,
                            content={"error": "no cached report for today"})
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
    return _stream_response(
        svc.run_analysis(payload.ticker, _user_id(request),
                         force_refresh=bool(payload.force))
    )


@router.post("/run/{ticker}")
async def run_path(ticker: str, request: Request,
                   force: bool = Query(False)):
    """SSE stream — ticker in path (alias of POST /run, kept for the
    frontend's path-style URLs)."""
    if not svc.feature_enabled():
        raise HTTPException(503, "AI Analyst feature is disabled")
    return _stream_response(
        svc.run_analysis(ticker, _user_id(request), force_refresh=force)
    )


@router.post("/compare")
async def compare(request: Request,
                  a: str = Query(...), b: str = Query(...)):
    """Run two analyses in parallel. Reuses cached reports when present."""
    if not svc.feature_enabled():
        raise HTTPException(503, "AI Analyst feature is disabled")
    user = _user_id(request)

    async def _one(t: str) -> dict:
        cached = svc.get_cached_report(t, user)
        if cached:
            return cached
        # Drain the generator into the final report
        final = None
        async for ev in svc.run_analysis(t, user, force_refresh=False):
            if ev.get("phase") == "done":
                final = ev.get("report")
            elif ev.get("phase") == "error":
                return {"ticker": t.upper(),
                        "error": ev.get("error", "unknown error")}
        return final or {"ticker": t.upper(), "error": "no report produced"}

    a_rpt, b_rpt = await asyncio.gather(_one(a), _one(b))
    return {"a": a_rpt, "b": b_rpt, "quota": svc.get_quota(user)}


@router.get("/admin/stats")
async def admin_stats(request: Request):
    _require_admin(request)
    return svc.admin_stats()


@router.post("/admin/flush")
async def admin_flush(request: Request):
    _require_admin(request)
    n = svc.flush_cache()
    return {"flushed": n}
