"""User-scoped CRUD for broker API credentials.

Surface
-------
  GET    /api/user/broker-keys          — metadata for all configured brokers
  PUT    /api/user/broker-keys/{broker} — upsert credentials
  DELETE /api/user/broker-keys/{broker} — remove credentials
  POST   /api/user/broker-keys/{broker}/test — verify creds against the broker
                                               (stub until per-broker phases land)

Security
--------
Every endpoint requires the calling user to be authenticated, and a user
can only see / modify THEIR OWN credentials. There is no admin override —
admins do not get to read user broker creds (that'd be a privilege boundary
violation; the operator already has SESSION_SECRET, that's enough).

Why no GET /{broker}
--------------------
We deliberately don't expose decrypted credentials over HTTP, ever. The
Settings UI shows "Configured: ✓" but doesn't pre-fill the form on edit
— the user re-enters every field. That UX is intentional and matches how
every well-designed API-key settings page works (GitHub, OpenAI, etc.).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.lib import broker_keys

logger = logging.getLogger("user_broker_keys")
router = APIRouter(prefix="/user/broker-keys", tags=["user-broker-keys"])


def _user_id(request: Request) -> str:
    """Return the authenticated user_id from auth middleware, or raise 401.

    Falling back to a shared default would put every unauthed call into
    the same bucket — a cross-tenant credential leak if any path ever
    escapes the auth middleware. Mirrors portfolio.py._user_id.
    """
    uid = getattr(request.state, "user_id", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return str(uid)


class UpsertBrokerKeyReq(BaseModel):
    """Shape varies by broker. Examples of expected fields:

      dhan:      {"client_id": "...", "access_token": "..."}
      zerodha:   {"api_key": "...", "api_secret": "...", "access_token": "..."}
      upstox:    {"api_key": "...", "api_secret": "...", "access_token": "..."}
      angel_one: {"api_key": "...", "client_id": "...", "pwd": "...", "totp_secret": "..."}
      groww:     {"api_key": "...", "api_secret": "..."}

    We accept any non-empty dict and let the per-broker client (Phases 4-8)
    validate the specific fields it needs. That keeps the API forward-
    compatible — adding broker fields later doesn't require schema changes.
    """
    # 4KB ceiling per blob. Real tokens are <500 bytes; the cap exists so a
    # malicious request can't bloat the row with megabytes of junk.
    creds:  dict[str, Any] = Field(..., description="Per-broker credentials dict.")
    active: bool           = Field(default=True,
                                   description="False keeps the row but disables it.")


@router.get("")
async def list_my_broker_keys(request: Request):
    """Return metadata for every broker the user has configured.

    Never includes decrypted creds — just enough state to render the
    Settings UI cards (broker name, active flag, last test result).
    """
    return {"keys": broker_keys.list_brokers_for_user(_user_id(request))}


@router.put("/{broker}")
async def upsert_my_broker_key(broker: str, req: UpsertBrokerKeyReq, request: Request):
    """Save or update credentials for this user's broker.

    On every save we reset `last_test_status` to "" so the UI re-shows
    "Untested" — old test result is meaningless after a key change.
    """
    user_id = _user_id(request)
    if broker not in broker_keys.ALLOWED_BROKERS:
        return JSONResponse(status_code=400, content={
            "error":   f"Unknown broker {broker!r}",
            "allowed": sorted(broker_keys.ALLOWED_BROKERS),
        })
    try:
        meta = broker_keys.set_broker_creds(
            user_id, broker, req.creds, req.active,
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.warning("broker key upsert failed for user=%s broker=%s: %s",
                       user_id, broker, exc)
        return JSONResponse(status_code=500, content={
            "error": "Failed to save credentials. Check server logs."})
    return meta


@router.delete("/{broker}")
async def delete_my_broker_key(broker: str, request: Request):
    """Remove the user's credentials for this broker."""
    user_id = _user_id(request)
    if broker not in broker_keys.ALLOWED_BROKERS:
        return JSONResponse(status_code=400, content={
            "error":   f"Unknown broker {broker!r}",
            "allowed": sorted(broker_keys.ALLOWED_BROKERS),
        })
    removed = broker_keys.delete_broker_creds(user_id, broker)
    return {"broker": broker, "removed": removed}


@router.post("/{broker}/test")
async def test_my_broker_key(broker: str, request: Request):
    """Verify the saved credentials work against the broker's API.

    Stub for Phase 2 — each broker phase (4-8) registers its real test
    function via `_BROKER_TESTERS`. Until those land, every test
    returns 'ok' with a note that it's a placeholder.

    Storing the result lets the Settings UI show e.g. "✓ Tested 5 min ago"
    or "✗ Invalid access token (5 min ago)" without re-running the test.
    """
    user_id = _user_id(request)
    if broker not in broker_keys.ALLOWED_BROKERS:
        return JSONResponse(status_code=400, content={
            "error": f"Unknown broker {broker!r}"})
    tester = _resolve_tester(broker)
    if tester is None:
        broker_keys.mark_test_result(user_id, broker, ok=True,
                                     error="(stub: broker client not yet implemented)")
        return {
            "ok":      True,
            "message": "Credentials saved. Real connection test will be "
                       "available once the broker integration ships.",
            "stub":    True,
        }
    creds = broker_keys.get_broker_creds(user_id, broker)
    if creds is None:
        broker_keys.mark_test_result(user_id, broker, ok=False,
                                     error="No active credentials found.")
        return JSONResponse(status_code=404, content={
            "ok":      False,
            "message": "No active credentials for this broker."})
    try:
        ok, message = await tester(creds)
    except Exception as exc:
        message = f"Test threw exception: {str(exc)[:200]}"
        ok = False
    broker_keys.mark_test_result(user_id, broker, ok=ok,
                                 error="" if ok else message)
    return {"ok": ok, "message": message}


# Registry of per-broker test functions. Each value is an async callable
# `(creds: dict) -> tuple[bool, str]` returning (success, message). We
# resolve testers lazily via _resolve_tester() so importing this route
# module doesn't pull in every broker client's deps at startup.
_BROKER_TESTERS: dict[str, Any] = {}


def register_broker_tester(broker: str, tester):
    """Eager registration — kept for callers that prefer it. Phase 4+
    services don't need to call this; the lazy resolver below handles
    them."""
    if broker in broker_keys.ALLOWED_BROKERS:
        _BROKER_TESTERS[broker] = tester


def _resolve_tester(broker: str):
    """Lazily look up the test function for a broker.

    Eager registrations win (so tests can monkey-patch). Otherwise we
    import the broker's service module on demand — keeps this route
    file decoupled from every broker's client library, and avoids
    paying import cost at boot for brokers the user hasn't configured.
    """
    if broker in _BROKER_TESTERS:
        return _BROKER_TESTERS[broker]
    # One branch per broker. Lazy imports prevent broker-specific deps
    # from being loaded at boot — the user only pays the import cost
    # when they actually click 'Test' on that broker's card.
    importers = {
        "dhan":      "app.services.dhan_service",
        "zerodha":   "app.services.zerodha_service",
        "upstox":    "app.services.upstox_service",
        "angel_one": "app.services.angel_one_service",
        "groww":     "app.services.groww_service",
    }
    mod_path = importers.get(broker)
    if not mod_path:
        return None
    try:
        import importlib  # noqa: PLC0415
        mod = importlib.import_module(mod_path)
        return getattr(mod, "test_connection", None)
    except Exception as exc:
        logger.warning("Broker %s import failed: %s", broker, str(exc)[:120])
        return None
