import os
import sys
import time
import secrets
import logging
from fastapi import APIRouter, Request, Header
from fastapi.responses import JSONResponse

router = APIRouter(tags=["admin"])
logger = logging.getLogger(__name__)

_start_time = time.time()

# In-memory session store: token -> expiry timestamp
_sessions: dict[str, float] = {}
_SESSION_TTL = 8 * 3600  # 8 hours


def _purge_expired():
    now = time.time()
    expired = [t for t, exp in _sessions.items() if exp < now]
    for t in expired:
        del _sessions[t]


def _valid_session(token: str) -> bool:
    _purge_expired()
    return token in _sessions and _sessions[token] > time.time()


# ── Login (public — no auth required) ────────────────────────────────────────

@router.post("/admin/login")
async def admin_login(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    username = body.get("username", "").strip()
    password = body.get("password", "")

    expected_user = os.environ.get("ADMIN_USERNAME", "admin")
    expected_pass = os.environ.get("ADMIN_PASSWORD", "")

    if not expected_pass:
        return JSONResponse(
            status_code=503,
            content={"error": "ADMIN_PASSWORD not configured on server."},
        )

    if username != expected_user or password != expected_pass:
        return JSONResponse(
            status_code=401,
            content={"error": "Invalid username or password."},
        )

    token = secrets.token_hex(32)
    _sessions[token] = time.time() + _SESSION_TTL
    return {"token": token, "expires_in": _SESSION_TTL}


# ── Helper: check admin session ───────────────────────────────────────────────

def _require_admin(request: Request) -> bool:
    token = request.headers.get("X-Admin-Token", "")
    return _valid_session(token)


# ── Protected admin endpoints ─────────────────────────────────────────────────

@router.get("/admin/status")
async def admin_status(request: Request):
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})

    uptime = time.time() - _start_time
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
async def admin_users(request: Request):
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})

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
async def admin_logs(request: Request, lines: int = 100):
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})

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
        log_lines = [
            "Logs are written to stdout/stderr (Replit workflow console).",
            "To enable file logging set LOG_FILE=/tmp/app.log and restart.",
            "Check the 'Python Backend' workflow tab in the Replit workspace for live logs.",
        ]

    return {"logs": log_lines, "total": len(log_lines)}
