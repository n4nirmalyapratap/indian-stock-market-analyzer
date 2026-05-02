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
    if not name:
        return JSONResponse(status_code=400, content={"error": "Name cannot be empty"})

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


# ── Secrets Management ─────────────────────────────────────────────────────────

@router.get("/admin/secrets")
async def list_secrets_endpoint(request: Request, reveal: bool = False):
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    from app.lib.secrets_store import list_secrets  # noqa: PLC0415
    return {"secrets": list_secrets(reveal=reveal)}


@router.put("/admin/secrets/{key}")
async def upsert_secret(key: str, request: Request):
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    value = body.get("value", "")
    description = body.get("description", "")
    masked = body.get("masked", True)

    from app.lib.secrets_store import set_secret  # noqa: PLC0415
    set_secret(key, value=value, description=description, masked=masked)
    return {"updated": True, "key": key}


@router.delete("/admin/secrets/{key}")
async def delete_secret_endpoint(key: str, request: Request):
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    from app.lib.secrets_store import delete_secret  # noqa: PLC0415
    deleted = delete_secret(key)
    if not deleted:
        return JSONResponse(status_code=404, content={"error": "Secret not found in DB (env-only secrets cannot be deleted)"})
    return {"deleted": True, "key": key}


@router.post("/admin/secrets/validate")
async def validate_secrets(request: Request):
    """Quick-check which known secrets are set (never returns values)."""
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    from app.lib.secrets_store import list_secrets  # noqa: PLC0415
    rows = list_secrets(reveal=False)
    return {
        "summary": {r["key"]: r["source"] for r in rows},
        "unset_count": sum(1 for r in rows if r["source"] == "unset"),
        "total": len(rows),
    }


# ── Data Consistency Audit ─────────────────────────────────────────────────────

@router.get("/admin/data-consistency")
async def data_consistency(request: Request, symbols: str = ""):
    """
    Cross-check that every page serves the same price for the same symbol.

    For each symbol we compare:
      - `/stocks/{sym}`              → quote.lastPrice  (StocksService)
      - `/stocks/{sym}/history`      → last candle close (PriceService, daily)
      - `/sectors`                   → only if symbol is a known index

    Drift > 0.1% (or > ₹0.05 absolute) is flagged.

    Open to admins only.
    """
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})

    syms = [s.strip().upper() for s in (symbols or "").split(",") if s.strip()]
    if not syms:
        syms = ["RELIANCE", "TCS", "HDFCBANK", "INFY"]

    from app.services.nse_service import NseService              # noqa: PLC0415
    from app.services.yahoo_service import YahooService          # noqa: PLC0415
    from app.services.price_service import PriceService          # noqa: PLC0415
    from app.services.stocks_service import StocksService        # noqa: PLC0415
    from app.services.sectors_service import SectorsService, SECTOR_INDICES  # noqa: PLC0415
    from app.services import market_cache_service as _disk       # noqa: PLC0415

    nse    = NseService()
    yahoo  = YahooService()
    price  = PriceService(nse, yahoo)
    stocks = StocksService(nse, yahoo)
    sectors_svc = SectorsService(nse, yahoo)

    sectors_list = await sectors_svc.get_all_sectors()
    sector_map = {s["symbol"].upper(): s for s in sectors_list}

    results = []
    drift_count = 0
    nse_yahoo_div = 0
    market_closed = not _disk.is_market_open()

    for sym in syms:
        try:
            details = await stocks.get_stock_details(sym)
            quote_price = details.get("lastPrice")

            history = await price.get_historical_data(sym, 30)
            hist_close = history[-1]["close"] if history else None
            hist_date  = history[-1]["date"]  if history else None

            sector_price = None
            if sym in sector_map:
                sector_price = sector_map[sym].get("lastPrice")

            # NSE-vs-Yahoo divergence check (closed market only — both should
            # agree on the official close). NSE is preferred; we report drift
            # so ops can spot upstream data-source disagreements.
            nse_close = None
            yahoo_close = None
            divergence = None
            divergence_pct = None
            if market_closed:
                try:
                    nq = await nse.get_stock_quote(sym)
                    if nq and nq.get("priceInfo"):
                        nse_close = nq["priceInfo"].get("lastPrice")
                except Exception:
                    nse_close = None
                try:
                    yq = await yahoo.get_quote(sym)
                    if yq:
                        yahoo_close = yq.get("lastPrice")
                except Exception:
                    yahoo_close = None
                if nse_close is not None and yahoo_close is not None:
                    divergence     = round(abs(nse_close - yahoo_close), 4)
                    divergence_pct = round(divergence / nse_close * 100, 4) if nse_close else 0
                    if divergence > 0.05 and divergence_pct > 0.1:
                        nse_yahoo_div += 1

            # Compare across our internal endpoints
            references = [v for v in (quote_price, hist_close, sector_price) if v is not None]
            drift = None
            drift_pct = None
            consistent = True
            if len(references) >= 2:
                lo, hi = min(references), max(references)
                drift = round(hi - lo, 4)
                drift_pct = round((drift / lo * 100), 4) if lo else 0
                consistent = (drift <= 0.05) or (drift_pct <= 0.1)
            if not consistent:
                drift_count += 1

            results.append({
                "symbol":         sym,
                "quotePrice":     quote_price,
                "historyClose":   hist_close,
                "historyDate":    hist_date,
                "sectorPrice":    sector_price,
                "nseClose":       nse_close,
                "yahooClose":     yahoo_close,
                "nseYahooDiff":   divergence,
                "nseYahooDiffPct": divergence_pct,
                "preferredSource": "NSE" if nse_close is not None else ("YAHOO" if yahoo_close is not None else None),
                "drift":          drift,
                "driftPct":       drift_pct,
                "consistent":     consistent,
                "meta":           details.get("meta", {}),
            })
        except Exception as e:
            results.append({"symbol": sym, "error": str(e)})

    # ── Sector index audit ────────────────────────────────────────────────
    # Cross-check the sector page's lastPrice against the sealed disk close
    # for every NIFTY index (NIFTY IT, NIFTY BANK, NIFTY 50, …) so ops can
    # spot drift between /sectors and the canonical EOD snapshot.
    index_results: list[dict] = []
    index_drift_count = 0
    expected_eod_date = _disk._eod_date_for(_disk.current_market_state())
    for idx in SECTOR_INDICES:
        sym = idx["symbol"]
        sector_entry = sector_map.get(sym.upper()) or {}
        sector_price = sector_entry.get("lastPrice")

        # Only treat the disk row as a valid sealed close when the snapshot
        # matches the sealed-snapshot contract: eodSealed + source==NSE +
        # eodDate==today's expected EOD date. Otherwise we'd compare against
        # a stale or non-canonical row and emit noisy false drift.
        payload = _disk.load_with_meta(sym, 30)
        is_sealed_nse = bool(
            payload
            and payload.get("eodSealed")
            and (payload.get("source") or "").upper() == "NSE"
            and payload.get("eodDate") == expected_eod_date
            and payload.get("data")
        )
        disk_close = None
        disk_date  = None
        if is_sealed_nse:
            rows = payload["data"]
            if rows and rows[-1].get("close") is not None:
                disk_close = round(float(rows[-1]["close"]), 2)
                disk_date  = rows[-1].get("date")

        refs = [v for v in (sector_price, disk_close) if v is not None]
        comparable = len(refs) >= 2
        idx_drift = idx_drift_pct = None
        idx_consistent = True
        if comparable:
            lo, hi = min(refs), max(refs)
            idx_drift     = round(hi - lo, 4)
            idx_drift_pct = round(idx_drift / lo * 100, 4) if lo else 0
            idx_consistent = idx_drift <= 0.05 or idx_drift_pct <= 0.1
        if comparable and not idx_consistent:
            index_drift_count += 1

        index_results.append({
            "name":         idx["name"],
            "symbol":       sym,
            "category":     idx["category"],
            "sectorPrice":  sector_price,
            "diskClose":    disk_close,
            "diskDate":     disk_date,
            "eodSealed":    is_sealed_nse,
            "servedFrom":   sector_entry.get("servedFrom"),
            "drift":        idx_drift,
            "driftPct":     idx_drift_pct,
            # `comparable=false` means we couldn't run the audit (sector
            # price or sealed disk close was absent). Such rows do NOT
            # count toward `indexDriftCount` and `consistent` is null —
            # this prevents silently passing audits that weren't actually
            # checked.
            "comparable":   comparable,
            "consistent":   idx_consistent if comparable else None,
        })

    return {
        "marketState":      _disk.current_market_state(),
        "marketOpen":       _disk.is_market_open(),
        "cacheVersion":     _disk.cache_version(),
        "asOf":             _disk._now_ist().isoformat(),
        "checked":          len(results),
        "driftCount":       drift_count,
        "nseYahooDivergent": nse_yahoo_div,
        "indexChecked":     len(index_results),
        "indexComparableCount": (index_comparable_count := sum(1 for ir in index_results if ir.get("comparable"))),
        "indexDriftCount":  index_drift_count,
        # On closed-market runs we expect at least some indices to be
        # comparable (sealed disk + sector price both present). If NONE
        # are comparable we cannot honestly claim consistency for the
        # sector audit, so degrade `consistent` to false and surface why.
        "indexAuditUnavailable": (
            not _disk.is_market_open() and index_comparable_count == 0
        ),
        "consistent":       (
            drift_count == 0
            and nse_yahoo_div == 0
            and index_drift_count == 0
            and not (not _disk.is_market_open() and index_comparable_count == 0)
        ),
        "preferredSource":  "NSE",
        "results":          results,
        "indexResults":     index_results,
    }


# ── Bug Fixer ─────────────────────────────────────────────────────────────────

_fixer_running = False
_fixer_last_run: dict = {}


@router.post("/admin/bugs/run-fixer")
async def run_bug_analyser(request: Request):
    """
    Trigger the AI bug analyser for all open bugs (or a specific bug via ?bug_id=).
    Analysis only — no code changes, no git push.
    Results are stored in the bug description field for the developer to review.
    """
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})

    global _fixer_running
    if _fixer_running:
        return {"status": "already_running", "message": "Analyser is already in progress."}

    import asyncio  # noqa: PLC0415
    from urllib.parse import urlparse, parse_qs  # noqa: PLC0415
    qs     = parse_qs(str(request.url.query))
    bug_id = qs.get("bug_id", [None])[0]

    async def _run():
        global _fixer_running, _fixer_last_run
        _fixer_running = True
        start = time.time()
        try:
            import sys as _sys  # noqa: PLC0415
            from pathlib import Path as _Path  # noqa: PLC0415
            _sys.path.insert(0, str(_Path(__file__).parents[2]))
            from scripts.bug_fixer import run_all  # noqa: PLC0415
            results = await run_all(bug_id=bug_id)
            _fixer_last_run = {
                "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "duration_s": round(time.time() - start, 1),
                "results": results,
                "status": "ok",
            }
        except Exception as exc:
            logger.error("Bug analyser error: %s", exc)
            _fixer_last_run = {
                "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "duration_s": round(time.time() - start, 1),
                "results": [f"ERROR: {exc}"],
                "status": "error",
            }
        finally:
            _fixer_running = False

    asyncio.create_task(_run())
    return {
        "status": "started",
        "message": f"AI analyser started — analysing {'bug #' + bug_id if bug_id else 'all open bugs'}.",
    }


@router.get("/admin/bugs/fixer-status")
async def bug_analyser_status(request: Request):
    """Return current bug analyser status and last run summary."""
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    return {
        "running": _fixer_running,
        "last_run": _fixer_last_run if _fixer_last_run else None,
    }


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
