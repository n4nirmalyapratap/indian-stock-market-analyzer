"""
Earnings Radar API routes.
  GET  /api/earnings-scanner/alerts      — recent scored alerts (auth required)
  POST /api/earnings-scanner/scan        — trigger an on-demand scan (admin only)
  GET  /api/earnings-scanner/stats       — summary stats (auth required)
"""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from typing import Any

router = APIRouter(prefix="/earnings-scanner", tags=["earnings-scanner"])


def _require_auth(request: Request) -> None:
    user_id = getattr(request.state, "user_id", None)
    is_admin = getattr(request.state, "is_admin", False)
    if not user_id and not is_admin:
        raise HTTPException(status_code=401, detail="Authentication required.")


def _require_admin(request: Request) -> None:
    if not getattr(request.state, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin privilege required.")


@router.get("/alerts")
async def get_earnings_alerts(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    min_score: int = Query(0, ge=0, le=10),
):
    _require_auth(request)
    try:
        from ..services.earnings_scanner_service import get_alerts
        alerts = get_alerts(limit=limit)
        if min_score > 0:
            alerts = [a for a in alerts if a["score"] >= min_score]
        return {
            "available": True,
            "alerts": alerts,
            "total": len(alerts),
            "alertThreshold": 6,
        }
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"available": False, "error": str(exc), "alerts": []},
        )


@router.get("/stats")
async def get_earnings_stats(request: Request):
    _require_auth(request)
    try:
        from ..services.earnings_scanner_service import get_alerts
        all_alerts = get_alerts(limit=500)
        scores = [a["score"] for a in all_alerts]
        high = [a for a in all_alerts if a["score"] >= 6]
        medium = [a for a in all_alerts if 4 <= a["score"] < 6]
        return {
            "total": len(all_alerts),
            "high": len(high),
            "medium": len(medium),
            "avgScore": round(sum(scores) / len(scores), 1) if scores else 0,
            "telegramSent": sum(1 for a in all_alerts if a.get("telegramSent")),
        }
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/scan")
async def trigger_scan(body: dict[str, Any], request: Request):
    _require_admin(request)
    import asyncio
    from ..services import earnings_scanner_service as _ess
    from ..routes.telegram import get_service as _tg_svc
    chat_id = (body.get("chatId") or body.get("chat_id") or "").strip()

    try:
        svc = _tg_svc()
    except Exception:
        svc = None

    try:
        result = await asyncio.wait_for(
            _ess.scan_recent_results(
                telegram_svc=svc if svc and svc.configured else None,
                telegram_chat_id=chat_id or None,
            ),
            timeout=120.0,
        )
        return {"ok": True, **result}
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=504,
            content={"ok": False, "error": "Scan timed out after 120s"},
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(exc)},
        )
