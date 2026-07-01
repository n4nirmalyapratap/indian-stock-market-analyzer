import os
import sys
import time
import logging
import uuid
from fastapi import APIRouter, Request, UploadFile, File
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

@router.get("/admin/registry/stats")
async def admin_registry_stats(request: Request):
    """Inspect the Security Registry's current state. Use this to
    triage "symbol not found" issues in scanners — if `count` is small
    (~150) the live NSE refresh hasn't succeeded yet and the registry
    is running from baseline. Pass ?resolve=LTFH (etc.) to test how a
    specific symbol would resolve."""
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    from app.services.security_registry_service import get_registry  # noqa: PLC0415
    reg = get_registry()
    stats = reg.stats()
    # Optional resolution probe — let the admin test arbitrary inputs.
    probe = (request.query_params.get("resolve") or "").strip()
    probe_result = None
    if probe:
        sec = reg.resolve(probe)
        probe_result = (
            {"input": probe, "nse_symbol": sec.nse_symbol, "name": sec.name,
             "aliases": list(sec.aliases), "isin": sec.isin}
            if sec else
            {"input": probe, "resolved": False}
        )
    return {**stats, "probe": probe_result}


@router.get("/admin/shareholding/diagnose/{symbol}")
async def admin_shareholding_diagnose(symbol: str, request: Request):
    """Per-source diagnostic for the shareholding chain.

    Walks NSE → XBRL (first available URL only) → Screener → Yahoo
    INDEPENDENTLY (no upserts, no caching), and reports what each
    source returned. Use this to triage "Shareholding tab shows 1
    column with YAHOO badge" — the response tells you exactly which
    source is failing and why.

    Example: GET /admin/shareholding/diagnose/TCS
    Returns: {
      "input": "TCS",
      "canonical": "TCS",
      "sources": {
        "nse":      { "ok": true,  "rows_count": 80, "first_row": {...}, "xbrl_urls": 80 },
        "xbrl":     { "ok": true,  "xml_size": 23456, "parsed": {...} },
        "screener": { "ok": false, "error": "..."  },
        "yahoo":    { "ok": true,  "rows_count": 1 }
      }
    }
    """
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})

    from app.services import shareholding_service as _sh  # noqa: PLC0415
    from app.lib.symbol_map import canonical_symbol       # noqa: PLC0415

    canon = canonical_symbol(symbol)
    result: dict = {
        "input": symbol,
        "canonical": canon,
        "sources": {},
    }

    # NSE — primary index source.
    nse_rows: list = []
    try:
        nse_rows = await _sh._fetch_nse(canon)
        result["sources"]["nse"] = {
            "ok":          True,
            "rows_count":  len(nse_rows),
            "xbrl_urls":   sum(1 for r in nse_rows if r.get("_xbrl_url")),
            "first_row":   _sanitize_row_for_debug(nse_rows[0]) if nse_rows else None,
            "first_xbrl_url": next(
                (r["_xbrl_url"] for r in nse_rows if r.get("_xbrl_url")),
                None,
            ),
        }
    except Exception as e:
        result["sources"]["nse"] = {
            "ok": False,
            "error": f"{type(e).__name__}: {str(e)[:200]}",
        }

    # XBRL — only if NSE gave us a URL.
    xbrl_url = result["sources"]["nse"].get("first_xbrl_url") if isinstance(result["sources"]["nse"], dict) else None
    if xbrl_url:
        try:
            xml = await _sh._fetch_xbrl_file(xbrl_url)
            if xml:
                parsed = _sh._parse_xbrl(xml)
                result["sources"]["xbrl"] = {
                    "ok":       True,
                    "url":      xbrl_url,
                    "xml_size": len(xml),
                    "parsed":   parsed,
                }
            else:
                result["sources"]["xbrl"] = {
                    "ok": False, "url": xbrl_url, "reason": "fetch returned empty bytes",
                }
        except Exception as e:
            result["sources"]["xbrl"] = {
                "ok": False, "url": xbrl_url,
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            }
    else:
        result["sources"]["xbrl"] = {"ok": False, "reason": "no XBRL URL from NSE"}

    # Screener — independent HTML scrape.
    try:
        s_rows = await _sh._fetch_screener(canon)
        result["sources"]["screener"] = {
            "ok":         True,
            "rows_count": len(s_rows),
            "first_row":  _sanitize_row_for_debug(s_rows[0]) if s_rows else None,
            "url":        f"https://www.screener.in/company/{canon}/",
        }
    except Exception as e:
        result["sources"]["screener"] = {
            "ok": False,
            "error": f"{type(e).__name__}: {str(e)[:200]}",
        }

    # Yahoo — the conflated last-resort.
    try:
        y_rows = await _sh._fetch_yahoo(canon)
        result["sources"]["yahoo"] = {
            "ok":         True,
            "rows_count": len(y_rows),
            "first_row":  _sanitize_row_for_debug(y_rows[0]) if y_rows else None,
        }
    except Exception as e:
        result["sources"]["yahoo"] = {
            "ok": False,
            "error": f"{type(e).__name__}: {str(e)[:200]}",
        }

    return result


def _sanitize_row_for_debug(row: dict) -> dict:
    """Strip the internal `_xbrl_url` field and ISO-format dates so
    the diagnostic JSON is paste-safe."""
    if not isinstance(row, dict):
        return {}
    out = {k: v for k, v in row.items() if not k.startswith("_")}
    if "as_on_date" in out and hasattr(out["as_on_date"], "isoformat"):
        out["as_on_date"] = out["as_on_date"].isoformat()
    return out


@router.get("/admin/quarantine")
async def admin_list_quarantine(request: Request):
    """List every symbol currently quarantined by the scanner. These
    are symbols where every provider returned 0 bars enough times to
    trip the auto-quarantine threshold — typically delisted, SME-only,
    or genuinely no-data tickers that scanners would otherwise show as
    errors on every run."""
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    from app.services import symbol_quarantine_service as _qsvc  # noqa: PLC0415
    rows  = _qsvc.list_quarantined()
    stats = _qsvc.stats()
    return {"stats": stats, "quarantined": rows}


@router.delete("/admin/quarantine/{symbol}")
async def admin_release_quarantine(symbol: str, request: Request):
    """Release one symbol from quarantine. Useful when manual
    investigation confirms a flagged symbol is actually valid (e.g. a
    transient NSE outage caused the auto-quarantine).

    The released symbol carries a `manual_override` flag so the
    auto-quarantine logic won't immediately re-fire on the next scan
    — gives operators room to investigate without the system fighting
    them."""
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    from app.services import symbol_quarantine_service as _qsvc  # noqa: PLC0415
    released = _qsvc.release(symbol)
    return {"symbol": symbol.upper(), "released": released}


@router.post("/admin/quarantine/release-all")
async def admin_release_all_quarantine(request: Request):
    """Nuclear option — release every quarantined symbol. Use after a
    sustained upstream outage that over-flagged a large batch."""
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    from app.services import symbol_quarantine_service as _qsvc  # noqa: PLC0415
    count = _qsvc.release_all()
    return {"released": count}


@router.post("/admin/registry/refresh")
async def admin_registry_refresh(request: Request):
    """Force an immediate registry refresh (fetches NSE EQUITY_L + the
    symbol-change history). Returns the new stats. Useful after a
    rename ships in production and you don't want to wait 24h for the
    scheduler's next tick."""
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    from app.services.security_registry_service import get_registry, refresh_registry  # noqa: PLC0415
    await refresh_registry()
    return get_registry().stats()


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
# rejects typos like 'repp' before they hit the DB. Headline 6 are the
# tiles on the dashboard strip; the catalog below adds PMI / FX reserves
# / unemployment / etc. so admins can manually update those too via the
# extras grid on the Macro Pulse page.
from app.services.macro_extras_catalog import MACRO_EXTRAS_SLUGS  # noqa: E402
_ALLOWED_MACRO_INDICATORS = (
    {"repo", "cpi", "iip", "wpi", "gdp", "yield10"} | MACRO_EXTRAS_SLUGS
)


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


@router.post("/admin/fii-dii/upsert")
async def fii_dii_upsert(request: Request):
    """Manually insert or overwrite FII/DII data for one or more dates.

    Body: { "segment": str, "rows": [{ "date": "YYYY-MM-DD", <flow fields> }] }

    Segment values: equity | index_future | index_option | stock_future | stock_option
    Equity fields : fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net
    F&O fields    : fii_long, fii_short, dii_long, dii_short,
                    client_long, client_short, pro_long, pro_short
    fii_net / dii_net are auto-calculated from buy-sell or long-short if omitted.
    All rows use ON CONFLICT UPDATE — safe to re-submit.
    """
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})

    import pandas as pd  # noqa: PLC0415
    from app.services.fii_dii_service import _pg_upsert_rows  # noqa: PLC0415

    VALID_SEGMENTS = {"equity", "index_future", "index_option", "stock_future", "stock_option"}

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body."})

    segment = (body.get("segment") or "").strip()
    if segment not in VALID_SEGMENTS:
        return JSONResponse(status_code=400, content={
            "error": f"Invalid segment {segment!r}. Must be one of: {sorted(VALID_SEGMENTS)}"})

    rows = body.get("rows") or []
    if not rows:
        return JSONResponse(status_code=400, content={"error": "No rows provided."})

    # Auto-calculate net fields if omitted
    cleaned = []
    for r in rows:
        row = dict(r)
        if not row.get("date"):
            continue
        if segment == "equity":
            fb = row.get("fii_buy") or 0
            fs = row.get("fii_sell") or 0
            db = row.get("dii_buy") or 0
            ds = row.get("dii_sell") or 0
            if row.get("fii_net") is None:
                row["fii_net"] = round(float(fb) - float(fs), 4)
            if row.get("dii_net") is None:
                row["dii_net"] = round(float(db) - float(ds), 4)
        else:
            fl = row.get("fii_long") or 0
            fs = row.get("fii_short") or 0
            dl = row.get("dii_long") or 0
            ds = row.get("dii_short") or 0
            if row.get("fii_net") is None:
                row["fii_net"] = round(float(fl) - float(fs), 4)
            if row.get("dii_net") is None:
                row["dii_net"] = round(float(dl) - float(ds), 4)
        cleaned.append(row)

    if not cleaned:
        return JSONResponse(status_code=400, content={"error": "All rows were missing a date field."})

    try:
        df = pd.DataFrame(cleaned)
        written = await asyncio.to_thread(_pg_upsert_rows, segment, df)
        return {"ok": True, "segment": segment, "written": written}
    except Exception as exc:
        logger.error("FII/DII upsert failed: %s", exc)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


@router.post("/admin/fii-dii/upload-csv")
async def fii_dii_upload_csv(request: Request, file: UploadFile = File(...)):
    """Batch-ingest FII/DII data from a CSV upload.

    Expected CSV columns (all optional except segment and date):
      segment, date,
      fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net,
      fii_long, fii_short, dii_long, dii_short,
      client_long, client_short, pro_long, pro_short

    Returns: { written, skipped, errors }
    """
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})

    import csv as _csv  # noqa: PLC0415
    import io as _io    # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415
    from app.services.fii_dii_service import _pg_upsert_rows  # noqa: PLC0415

    VALID_SEGMENTS = {"equity", "index_future", "index_option", "stock_future", "stock_option"}
    NUMERIC_COLS = [
        "fii_buy", "fii_sell", "fii_net", "dii_buy", "dii_sell", "dii_net",
        "fii_long", "fii_short", "dii_long", "dii_short",
        "client_long", "client_short", "pro_long", "pro_short",
    ]

    try:
        raw = await file.read()
        text = raw.decode("utf-8-sig", errors="replace")
        reader = _csv.DictReader(_io.StringIO(text))
        rows_by_seg: dict[str, list[dict]] = {}
        errors: list[str] = []
        skipped = 0

        for i, row in enumerate(reader, start=2):  # 2 = first data line
            row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            seg = row.get("segment", "").strip().lower()
            date_val = row.get("date", "").strip()
            if not seg or not date_val:
                errors.append(f"Row {i}: missing segment or date — skipped")
                skipped += 1
                continue
            if seg not in VALID_SEGMENTS:
                errors.append(f"Row {i}: unknown segment {seg!r} — skipped")
                skipped += 1
                continue

            clean: dict[str, object] = {"date": date_val}
            for col in NUMERIC_COLS:
                v = row.get(col, "")
                if v:
                    try:
                        clean[col] = float(v)
                    except ValueError:
                        errors.append(f"Row {i}: {col}={v!r} is not a number — set to null")
                        clean[col] = None
                else:
                    clean[col] = None

            # Auto-calc net if blank
            if seg == "equity":
                if clean.get("fii_net") is None and clean.get("fii_buy") is not None:
                    clean["fii_net"] = round(float(clean["fii_buy"] or 0) - float(clean["fii_sell"] or 0), 4)
                if clean.get("dii_net") is None and clean.get("dii_buy") is not None:
                    clean["dii_net"] = round(float(clean["dii_buy"] or 0) - float(clean["dii_sell"] or 0), 4)
            else:
                if clean.get("fii_net") is None and clean.get("fii_long") is not None:
                    clean["fii_net"] = round(float(clean["fii_long"] or 0) - float(clean["fii_short"] or 0), 4)
                if clean.get("dii_net") is None and clean.get("dii_long") is not None:
                    clean["dii_net"] = round(float(clean["dii_long"] or 0) - float(clean["dii_short"] or 0), 4)

            rows_by_seg.setdefault(seg, []).append(clean)

        written = 0
        for seg, seg_rows in rows_by_seg.items():
            df = pd.DataFrame(seg_rows)
            written += await asyncio.to_thread(_pg_upsert_rows, seg, df)

        return {"ok": True, "written": written, "skipped": skipped, "errors": errors}

    except Exception as exc:
        logger.error("FII/DII CSV upload failed: %s", exc)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc), "written": 0, "skipped": 0, "errors": []})


@router.get("/admin/subsectors")
async def list_subsectors(request: Request):
    """Return the full taxonomy (from universe.py) merged with all DB overrides,
    showing which sub-industries exist, how many curated symbols they have, and
    every admin-added override row."""
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    from app.lib.auth_store import ensure_primary_schema  # noqa: PLC0415
    from app.lib.universe import SUBSECTOR_TAXONOMY  # noqa: PLC0415
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT o.id, o.symbol, o.sub_industry, o.industry, o.sector,
                       o.note, o.set_by, o.created_at_ms, o.updated_at_ms,
                       s.name AS stock_name, s.market_cap, s.cap_category,
                       s.classified_ok
                  FROM sub_industry_overrides o
                  LEFT JOIN stocks s ON s.symbol = o.symbol
                 ORDER BY o.sub_industry, o.symbol
                """
            )
            overrides = [dict(r) for r in cur.fetchall()]

    taxonomy_out = [
        {
            "subIndustry": k,
            "industry": v.get("industry", ""),
            "sector": v.get("sector", ""),
            "curatedCount": len(v.get("symbols", [])),
            "curatedSymbols": v.get("symbols", []),
        }
        for k, v in sorted(SUBSECTOR_TAXONOMY.items())
    ]
    return {
        "taxonomy": taxonomy_out,
        "overrides": overrides,
        "totalSubIndustries": len(taxonomy_out),
        "totalOverrides": len(overrides),
    }


@router.post("/admin/subsectors/overrides")
async def add_subsector_override(request: Request):
    """Add a symbol to a sub-industry. If the sub-industry doesn't exist in
    the taxonomy it is created as a new group. The symbol will be picked up by
    the next classifier run and included in the rotation grid once it has
    market-cap data."""
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})
    symbol      = (str(body.get("symbol") or "")).strip().upper()
    sub_industry = (str(body.get("subIndustry") or "")).strip()
    industry    = (str(body.get("industry") or "")).strip()
    sector      = (str(body.get("sector") or "")).strip()
    note        = (str(body.get("note") or "")).strip()[:300]
    if not symbol or not sub_industry:
        return JSONResponse(status_code=400, content={"error": "symbol and subIndustry are required"})

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
                INSERT INTO sub_industry_overrides
                    (id, symbol, sub_industry, industry, sector, note, set_by,
                     created_at_ms, updated_at_ms)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, sub_industry) DO UPDATE SET
                    industry     = EXCLUDED.industry,
                    sector       = EXCLUDED.sector,
                    note         = EXCLUDED.note,
                    set_by       = EXCLUDED.set_by,
                    updated_at_ms = EXCLUDED.updated_at_ms
                RETURNING id
                """,
                (str(uuid.uuid4()), symbol, sub_industry, industry, sector, note, set_by, now_ms, now_ms),
            )
            row = cur.fetchone()
    # Clear from the unclassified queue now that it's been assigned
    from app.lib import unclassified_log as _ul  # noqa: PLC0415
    _ul.dismiss(symbol)

    return {"ok": True, "id": row["id"] if row else None,
            "symbol": symbol, "subIndustry": sub_industry}


@router.delete("/admin/subsectors/overrides/{override_id}")
async def delete_subsector_override(override_id: str, request: Request):
    """Remove an admin override by its ID."""
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    from app.lib.auth_store import ensure_primary_schema  # noqa: PLC0415
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM sub_industry_overrides WHERE id = %s RETURNING symbol, sub_industry",
                (override_id,),
            )
            row = cur.fetchone()
    if not row:
        return JSONResponse(status_code=404, content={"error": "Override not found"})
    return {"ok": True, "removed": dict(row)}


@router.get("/admin/subsectors/unclassified")
async def list_unclassified(request: Request):
    """Return the in-memory queue of stocks that were looked up but have no
    sub-sector classification.  Sorted by hit count descending (most-viewed
    unclassified stocks first).  No DB read — purely from the live process log."""
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    from app.lib import unclassified_log  # noqa: PLC0415
    return {"items": unclassified_log.get_all(), "total": unclassified_log.size()}


@router.delete("/admin/subsectors/unclassified/{symbol}")
async def dismiss_unclassified(symbol: str, request: Request):
    """Dismiss a symbol from the unclassified queue without classifying it
    (e.g. it's a warrant/ETF that doesn't need a sub-sector)."""
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    from app.lib import unclassified_log  # noqa: PLC0415
    unclassified_log.dismiss(symbol.upper().strip())
    return {"ok": True, "dismissed": symbol.upper().strip()}


@router.post("/admin/subsectors/reclassify")
async def trigger_reclassify(request: Request):
    """Trigger an immediate classifier run for all taxonomy symbols, then
    re-seed overrides from the taxonomy and rebuild today's metrics grid so
    the /sector-analytics page shows all sub-industries immediately."""
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    try:
        import asyncio  # noqa: PLC0415
        from app.services import synthetic_sectors_service as synth  # noqa: PLC0415
        from app.services.yahoo_service import YahooService as _YS  # noqa: PLC0415

        classify_result = await synth.refresh_classifications(force=False)
        seed_result = await asyncio.to_thread(synth.seed_overrides_from_taxonomy)
        yahoo = _YS()
        metrics_result = await synth.run_nightly_metrics(yahoo)
        return {"ok": True, "classify": classify_result, "seed": seed_result, "metrics": metrics_result}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


## ── IPO Manager ────────────────────────────────────────────────────────────


@router.get("/admin/ipos")
async def admin_list_ipos(request: Request):
    """List all IPOs (active + listed) from the persistent store."""
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    from app.services import ipo_store as _s  # noqa: PLC0415
    return {"ipos": _s.get_all(), "counts": _s.count()}


@router.post("/admin/ipos")
async def admin_add_ipo(request: Request):
    """Manually add or update an IPO record.

    Body (all optional except companyName + symbol):
      symbol, companyName, series, isSme, isReit,
      openDate, closeDate, listingDate,
      priceLow, priceHigh, lotSize, issueSizeCr
    """
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})
    name = (body.get("companyName") or "").strip()
    sym  = (body.get("symbol") or "").strip().upper()
    if not name:
        return JSONResponse(status_code=400, content={"error": "companyName is required"})
    if not sym:
        import re  # noqa: PLC0415
        sym = re.sub(r"[^A-Z0-9]", "", name.upper())[:24] or "MANUAL"
    try:
        from app.services import ipo_store as _s  # noqa: PLC0415
        # Invalidate the in-process calendar cache so next load picks up the new entry.
        from app.services import ipo_service as _is  # noqa: PLC0415
        _is._RESULT_CACHE.clear()
        record = _s.upsert_manual({**body, "symbol": sym})
        return {"ok": True, "record": record}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@router.patch("/admin/ipos/{symbol}/mark-listed")
async def admin_mark_ipo_listed(symbol: str, request: Request):
    """Force an IPO into the 'listed' bucket (removes it from open/upcoming)."""
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    from app.services import ipo_store as _s  # noqa: PLC0415
    from app.services import ipo_service as _is  # noqa: PLC0415
    _is._RESULT_CACHE.clear()
    found = _s.mark_listed(symbol)
    if not found:
        return JSONResponse(status_code=404, content={"error": f"IPO {symbol!r} not found"})
    return {"ok": True, "symbol": symbol.upper()}


@router.delete("/admin/ipos/{symbol}")
async def admin_delete_ipo(symbol: str, request: Request):
    """Hard-delete an IPO record from the persistent store."""
    if not _require_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin authentication required."})
    from app.services import ipo_store as _s  # noqa: PLC0415
    from app.services import ipo_service as _is  # noqa: PLC0415
    _is._RESULT_CACHE.clear()
    removed = _s.delete(symbol)
    return {"ok": removed, "symbol": symbol.upper()}


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
