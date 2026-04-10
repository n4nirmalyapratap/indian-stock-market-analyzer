import os
import sys
import time
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["admin"])
logger = logging.getLogger(__name__)

_start_time = time.time()


@router.get("/admin/status")
async def admin_status():
    """Backend runtime metrics."""
    import app.routes as _r_pkg
    import fastapi

    uptime = time.time() - _start_time

    # Count registered routes by inspecting the FastAPI app via the request
    # (we can't import `app` here to avoid circular imports — count from sys.modules)
    endpoints = 0
    try:
        from main import app as _app  # noqa: PLC0415
        endpoints = len([r for r in _app.routes if hasattr(r, "methods")])
    except Exception:
        pass

    return {
        "uptime": round(uptime, 1),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_start_time)),
        "python_version": sys.version.split()[0],
        "endpoints": endpoints,
        "telegram_configured": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        "whatsapp_configured": bool(os.environ.get("WHATSAPP_ENABLED")),
    }


@router.get("/admin/users")
async def admin_users():
    """List users from Clerk using CLERK_SECRET_KEY."""
    secret_key = os.environ.get("CLERK_SECRET_KEY", "")
    if not secret_key:
        return JSONResponse(
            status_code=503,
            content={"error": "CLERK_SECRET_KEY not configured on backend."},
        )

    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.clerk.com/v1/users",
                headers={"Authorization": f"Bearer {secret_key}"},
                params={"limit": 100, "order_by": "-created_at"},
            )
            resp.raise_for_status()
            raw = resp.json()

        users = []
        for u in raw:
            primary_email = None
            for em in (u.get("email_addresses") or []):
                if em.get("id") == u.get("primary_email_address_id"):
                    primary_email = em.get("email_address")
                    break
            users.append({
                "id": u.get("id"),
                "email": primary_email,
                "first_name": u.get("first_name"),
                "last_name": u.get("last_name"),
                "image_url": u.get("image_url"),
                "created_at": u.get("created_at"),
                "last_sign_in_at": u.get("last_sign_in_at"),
            })

        return {"users": users, "total": len(users)}
    except Exception as e:
        logger.error("Failed to fetch Clerk users: %s", e)
        return JSONResponse(status_code=502, content={"error": str(e)})


@router.get("/admin/logs")
async def admin_logs(lines: int = 100):
    """Tail the Python backend log file (if available) or return empty."""
    log_lines: list[str] = []

    log_file = os.environ.get("LOG_FILE", "")
    if log_file and os.path.exists(log_file):
        try:
            with open(log_file, "r", errors="replace") as f:
                all_lines = f.readlines()
            log_lines = [l.rstrip() for l in all_lines[-lines:]]
        except Exception as e:
            log_lines = [f"[Error reading log file: {e}]"]
    else:
        # Fallback: return a note since uvicorn logs to stdout
        log_lines = [
            "Logs are written to stdout/stderr (Replit workflow console).",
            "To enable file logging set LOG_FILE=/tmp/app.log and restart.",
            "Check the 'Python Backend' workflow tab in the Replit workspace for live logs.",
        ]

    return {"logs": log_lines, "total": len(log_lines)}
