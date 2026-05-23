import os
import sys
import time
import logging
import uuid
from fastapi import APIRouter, Request
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from app.lib.auth_store import get_conn, list_users, upsert_google_user
from app.lib.auth_tokens import create_token, verify_token
from app.lib.google_identity import admin_email_allowlist, verify_google_credential

router = APIRouter(tags=["admin"])
logger = logging.getLogger(__name__)

_start_time = time.time()

def _valid_session(token: str) -> bool:
    if not token:
        return False
    try:
        payload = verify_token(token, required_scope="admin")
    except Exception:
        return False
    return bool(payload.get("is_admin"))


def _require_admin(request: Request) -> bool:
    return _valid_session(request.headers.get("X-Admin-Token", ""))


# ── Users DB helpers ──────────────────────────────────────────────────────────



# ── Login (public) ────────────────────────────────────────────────────────────

@router.post("/admin/login")
async def disabled_admin_password_login():
    raise HTTPException(status_code=410, detail="Password login is disabled. Use Google sign-in.")


@router.post("/admin/google-login")
async def admin_google_login(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    try:
        claims = verify_google_credential((body.get("credential") or "").strip())
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception:
        return JSONResponse(status_code=401, content={"error": "Google sign-in verification failed."})

    email = (claims.get("email") or "").strip().lower()
    if email not in admin_email_allowlist():
        return JSONResponse(status_code=403, content={"error": "This Google account is not authorized for admin access."})

    user = upsert_google_user(
        email=email,
        name=(claims.get("name") or "").strip(),
        google_sub=str(claims.get("sub") or ""),
        picture_url=(claims.get("picture") or "").strip(),
        is_admin=True,
    )
    token = create_token(user, scope="admin")
    return {
        "token": token,
        "expires_in": 8 * 3600,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "pictureUrl": user.get("picture_url", ""),
        },
    }


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
    rows = list_users()
    return {
        "users": [
            {
                "id": row["id"],
                "email": row["email"],
                "name": row["name"],
                "picture_url": row.get("picture_url", ""),
                "auth_provider": row.get("auth_provider", "google"),
                "is_admin": bool(row.get("is_admin")),
                "created_at": int(row["created_at"]),
                "last_login_at": int(row["last_login_at"]),
            }
            for row in rows
        ],
        "total": len(rows),
    }


# ── App (custom auth) users ───────────────────────────────────────────────────

@router.get("/admin/users/app")
async def admin_app_users(request: Request):
    return await admin_users(request)


@router.post("/admin/users/create")
async def disabled_admin_create_user():
    raise HTTPException(status_code=410, detail="Manual user creation is disabled. Users are created on first Google sign-in.")


@router.delete("/admin/users/app/{user_id}")
async def disabled_admin_delete_user(user_id: str):
    raise HTTPException(status_code=410, detail="User deletion is disabled from the admin UI in Google-only mode.")


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
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bug_reports (
                    id          TEXT PRIMARY KEY,
                    title       TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    severity    TEXT NOT NULL DEFAULT 'medium',
                    status      TEXT NOT NULL DEFAULT 'open',
                    component   TEXT NOT NULL DEFAULT '',
                    reported_by TEXT NOT NULL DEFAULT '',
                    created_at  BIGINT NOT NULL,
                    updated_at  BIGINT NOT NULL
                )
            """)


@router.get("/admin/bugs")
async def list_bugs(request: Request):
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    _init_bugs_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM bug_reports ORDER BY created_at DESC")
            rows = cur.fetchall()
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
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO bug_reports
                   (id, title, description, severity, status, component, reported_by, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    bug_id,
                    title,
                    body.get("description", ""),
                    body.get("severity", "medium"),
                    "open",
                    body.get("component", ""),
                    body.get("reported_by", ""),
                    now,
                    now,
                ),
            )
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
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [bug_id]

    _init_bugs_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE bug_reports SET {set_clause} WHERE id = %s", values)
            updated = cur.rowcount
    if updated == 0:
        return JSONResponse(status_code=404, content={"error": "Bug not found"})
    return {"updated": True}


@router.delete("/admin/bugs/{bug_id}")
async def delete_bug(bug_id: str, request: Request):
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    _init_bugs_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM bug_reports WHERE id = %s", (bug_id,))
            deleted = cur.rowcount
    if deleted == 0:
        return JSONResponse(status_code=404, content={"error": "Bug not found"})
    return {"deleted": True}


# ── Macro indicator overrides ────────────────────────────────────────────────
# Lets an admin punch in fresh values for repo / CPI / IIP / WPI / GDP / 10Y
# when upstream providers haven't published yet (e.g. immediately after an
# RBI policy meeting). Stored in macro_overrides (auth_store schema), read
# by macro_service._get_override() with highest priority in the source chain.

# Indicators we accept overrides for — keeps the API surface narrow and
# rejects typos like 'repp' before they hit the DB.
_ALLOWED_MACRO_INDICATORS = {"repo", "cpi", "iip", "wpi", "gdp", "yield10"}


@router.get("/admin/macro/overrides")
async def list_macro_overrides(request: Request):
    """Return every admin-set override currently in effect."""
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    from app.lib.auth_store import ensure_primary_schema  # noqa: PLC0415
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT indicator, value, as_of, note, set_by, updated_at_ms "
                "FROM macro_overrides ORDER BY indicator"
            )
            rows = cur.fetchall()
    return {"overrides": [dict(r) for r in rows]}


@router.put("/admin/macro/overrides/{indicator}")
async def set_macro_override(indicator: str, request: Request):
    """Upsert an override for a single indicator.

    Body: { value: number, asOf: "YYYY-MM-DD", note?: string }
    The macro service caches its strip/dashboard responses for 24h; touching
    an override clears that cache so the change shows up immediately.
    """
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    if indicator not in _ALLOWED_MACRO_INDICATORS:
        return JSONResponse(status_code=400, content={
            "error": f"Unknown indicator {indicator!r}. "
                     f"Allowed: {sorted(_ALLOWED_MACRO_INDICATORS)}"})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})
    try:
        value = float(body.get("value"))
        as_of = str(body.get("asOf") or "").strip()
        note  = str(body.get("note") or "").strip()[:200]
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"error": "value must be a number"})
    if not as_of or len(as_of) < 8:
        return JSONResponse(status_code=400, content={"error": "asOf must be YYYY-MM-DD"})

    # Determine the admin's identifying email/name for the audit trail.
    set_by = ""
    try:
        from app.lib.auth_tokens import verify_token  # noqa: PLC0415
        payload = verify_token(request.headers.get("X-Admin-Token", ""), required_scope="admin")
        set_by  = str(payload.get("email") or payload.get("sub") or "")[:120]
    except Exception:
        pass

    from app.lib.auth_store import ensure_primary_schema  # noqa: PLC0415
    ensure_primary_schema()
    now_ms = int(time.time() * 1000)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO macro_overrides (indicator, value, as_of, note, set_by, updated_at_ms)
                     VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (indicator) DO UPDATE
                        SET value         = EXCLUDED.value,
                            as_of         = EXCLUDED.as_of,
                            note          = EXCLUDED.note,
                            set_by        = EXCLUDED.set_by,
                            updated_at_ms = EXCLUDED.updated_at_ms
                """,
                (indicator, value, as_of, note, set_by, now_ms),
            )

    # Invalidate the macro 24h in-memory cache so the override shows up
    # on the next /macro/strip request rather than after up to 24h.
    try:
        from app.services import macro_service as _ms  # noqa: PLC0415
        _ms._cache.clear()
    except Exception:
        pass

    return {"indicator": indicator, "value": value, "asOf": as_of, "setBy": set_by}


# ── FII/DII status + force-refresh ──────────────────────────────────────────
# Lets admins verify the daily scheduler is populating every segment (equity
# AND the 4 F&O segments) and trigger a backfill on demand when NSE archives
# come back online after a block.

@router.get("/admin/fii-dii/status")
async def fii_dii_status(request: Request):
    """Return per-segment row counts + freshest date for FII/DII history.

    Useful for diagnosing 'why is the F&O tab empty' — equity will usually
    have rows, F&O may be empty if nsearchives.nseindia.com is blocked from
    this container's egress.
    """
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    from app.lib.auth_store import ensure_primary_schema  # noqa: PLC0415
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT segment, COUNT(*) AS rows, MIN(date) AS first_date, "
                "       MAX(date) AS last_date, MAX(updated_at_ms) AS last_updated_ms "
                "FROM fii_dii_history GROUP BY segment ORDER BY segment"
            )
            rows = cur.fetchall()
    out = []
    for r in rows:
        out.append({
            "segment":         r["segment"],
            "rows":            int(r["rows"] or 0),
            "firstDate":       str(r["first_date"]) if r["first_date"] else None,
            "lastDate":        str(r["last_date"])  if r["last_date"]  else None,
            "lastUpdatedMs":   int(r["last_updated_ms"]) if r["last_updated_ms"] else None,
        })
    expected = {"equity", "index_future", "index_option", "stock_future", "stock_option"}
    present  = {r["segment"] for r in out}
    return {
        "segments":  out,
        "missing":   sorted(expected - present),
        "fetchedAt": int(time.time() * 1000),
    }


@router.post("/admin/fii-dii/refresh")
async def fii_dii_refresh(request: Request):
    """Trigger an immediate scheduled_daily_fetch tick — same code the
    background scheduler runs every 24h. Useful after NSE archives come
    back online to backfill the missing window without waiting."""
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    from app.services.fii_dii_service import FiiDiiService  # noqa: PLC0415
    svc = FiiDiiService()
    try:
        result = await svc.scheduled_daily_fetch(gap_days=30)
        return result
    except Exception as exc:
        return JSONResponse(status_code=500, content={
            "ok": False, "error": f"FII/DII refresh failed: {exc}"})


@router.delete("/admin/macro/overrides/{indicator}")
async def delete_macro_override(indicator: str, request: Request):
    """Remove an override so the macro service falls back to live sources."""
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    if indicator not in _ALLOWED_MACRO_INDICATORS:
        return JSONResponse(status_code=400, content={"error": f"Unknown indicator {indicator!r}"})
    from app.lib.auth_store import ensure_primary_schema  # noqa: PLC0415
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM macro_overrides WHERE indicator = %s", (indicator,))
            removed = cur.rowcount
    # Clear cache so the fallback value shows up immediately.
    try:
        from app.services import macro_service as _ms  # noqa: PLC0415
        _ms._cache.clear()
    except Exception:
        pass
    return {"indicator": indicator, "removed": removed > 0}
