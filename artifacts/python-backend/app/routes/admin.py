import os
import sys
import time
import uuid
import secrets
import logging
import sqlite3
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["admin"])
logger = logging.getLogger(__name__)

_start_time = time.time()

# In-memory session store: token -> expiry timestamp
_sessions: dict[str, float] = {}
_SESSION_TTL = 8 * 3600  # 8 hours

_DATA_DIR = os.environ.get(
    "DATA_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."),
)
_DB_PATH = os.path.join(_DATA_DIR, "users.db")


def _purge_expired():
    now = time.time()
    expired = [t for t, exp in _sessions.items() if exp < now]
    for t in expired:
        del _sessions[t]


def _valid_session(token: str) -> bool:
    _purge_expired()
    return token in _sessions and _sessions[token] > time.time()


def _require_admin(request: Request) -> bool:
    return _valid_session(request.headers.get("X-Admin-Token", ""))


# ── Users DB helpers ──────────────────────────────────────────────────────────

def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            TEXT PRIMARY KEY,
            email         TEXT UNIQUE NOT NULL,
            name          TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            created_at    INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── Login (public) ────────────────────────────────────────────────────────────

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


# ── App status ────────────────────────────────────────────────────────────────

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


# ── Google Users (removed — Clerk is not used) ────────────────────────────────

@router.get("/admin/users")
async def admin_users(request: Request):
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    return JSONResponse(status_code=410, content={"error": "Google OAuth (Clerk) is not configured. Only email+password users are supported."})


# ── App (custom auth) users ───────────────────────────────────────────────────

@router.get("/admin/users/app")
async def admin_app_users(request: Request):
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})

    _init_db()
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT id, email, name, created_at FROM users ORDER BY created_at DESC"
        ).fetchall()
    finally:
        conn.close()

    return {
        "users": [
            {"id": r["id"], "email": r["email"], "name": r["name"], "created_at": r["created_at"]}
            for r in rows
        ],
        "total": len(rows),
    }


@router.post("/admin/users/create")
async def admin_create_user(request: Request):
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    email    = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    name     = (body.get("name") or "").strip()

    if not email or "@" not in email:
        return JSONResponse(status_code=400, content={"error": "Enter a valid email address"})
    if len(password) < 6:
        return JSONResponse(status_code=400, content={"error": "Password must be at least 6 characters"})

    _init_db()
    conn = _get_db()
    try:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            return JSONResponse(status_code=400, content={"error": "An account with this email already exists"})

        import bcrypt
        user_id       = str(uuid.uuid4())
        display_name  = name or email.split("@")[0]
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        conn.execute(
            "INSERT INTO users (id, email, name, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, email, display_name, password_hash, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info("Admin created new app user: %s", email)
    return {"id": user_id, "email": email, "name": display_name}


@router.delete("/admin/users/app/{user_id}")
async def admin_delete_app_user(user_id: str, request: Request):
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})

    _init_db()
    conn = _get_db()
    try:
        row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return JSONResponse(status_code=404, content={"error": "User not found"})
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()

    return {"deleted": user_id}


# ── Structured logs from in-memory ring buffer ────────────────────────────────

@router.get("/admin/logs")
async def admin_logs(
    request: Request,
    lines: int = 200,
    level: str = "",
    search: str = "",
):
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})

    from app.services.log_buffer import get_ring_buffer  # noqa: PLC0415
    buf = get_ring_buffer()

    if buf is None:
        return {
            "logs": [{
                "ts":     time.time(),
                "level":  "INFO",
                "logger": "system",
                "msg":    "Log buffer not initialised — restart the backend to enable structured logs.",
            }],
            "total": 1,
            "structured": True,
        }

    records = buf.get_records(limit=lines, level=level or None, search=search or None)
    return {"logs": records, "total": len(records), "structured": True}


# ── Bug Reports ────────────────────────────────────────────────────────────────

def _init_bugs_db() -> None:
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bug_reports (
            id          TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            severity    TEXT NOT NULL DEFAULT 'medium',
            status      TEXT NOT NULL DEFAULT 'open',
            component   TEXT NOT NULL DEFAULT '',
            reported_by TEXT NOT NULL DEFAULT '',
            created_at  INTEGER NOT NULL,
            updated_at  INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()


@router.get("/admin/bugs")
async def list_bugs(request: Request):
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    _init_bugs_db()
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM bug_reports ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return {"bugs": [dict(r) for r in rows], "total": len(rows)}


@router.post("/admin/bugs")
async def create_bug(request: Request):
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    title = (body.get("title") or "").strip()
    if not title:
        return JSONResponse(status_code=400, content={"error": "title is required"})

    now = int(time.time())
    bug_id = str(uuid.uuid4())[:8]
    _init_bugs_db()
    conn = _get_db()
    conn.execute(
        """INSERT INTO bug_reports (id, title, description, severity, status, component, reported_by, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            bug_id,
            title,
            body.get("description", ""),
            body.get("severity", "medium"),
            "open",
            body.get("component", ""),
            body.get("reported_by", ""),
            now, now,
        ),
    )
    conn.commit()
    conn.close()
    return {"id": bug_id, "created": True}


@router.patch("/admin/bugs/{bug_id}")
async def update_bug(bug_id: str, request: Request):
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    allowed = {"title", "description", "severity", "status", "component", "reported_by"}
    updates = {k: v for k, v in body.items() if k in allowed and v is not None}
    if not updates:
        return JSONResponse(status_code=400, content={"error": "No valid fields to update"})

    updates["updated_at"] = int(time.time())
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [bug_id]

    _init_bugs_db()
    conn = _get_db()
    cur = conn.execute(f"UPDATE bug_reports SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        return JSONResponse(status_code=404, content={"error": "Bug not found"})
    return {"updated": True}


@router.delete("/admin/bugs/{bug_id}")
async def delete_bug(bug_id: str, request: Request):
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    _init_bugs_db()
    conn = _get_db()
    cur = conn.execute("DELETE FROM bug_reports WHERE id = ?", (bug_id,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        return JSONResponse(status_code=404, content={"error": "Bug not found"})
    return {"deleted": True}
