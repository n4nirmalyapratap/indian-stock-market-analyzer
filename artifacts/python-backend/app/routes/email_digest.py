"""
Email digest routes — `/api/email-digest/*`

  GET    /api/email-digest/subscriptions          — list caller's subscriptions
  POST   /api/email-digest/subscriptions          — create or update a sub
  DELETE /api/email-digest/subscriptions/{sub_id} — delete one sub
  GET    /api/email-digest/config                 — SMTP wire-status (no secrets)
  POST   /api/email-digest/send-now/{sub_id}      — manually fire one digest now
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..services import email_digest_service as eds
from ..services.nse_service import NseService
from ..services.yahoo_service import YahooService
from ..services.price_service import PriceService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/email-digest", tags=["email-digest"])


def _user_id(request: Request) -> str:
    """Pull the JWT subject. Refusing anonymous requests prevents one user
    from spamming digests to arbitrary addresses."""
    uid = getattr(request.state, "user_id", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return uid


# Single PriceService instance — created lazily on first /send-now call.
_price_service: Optional[PriceService] = None


def _price() -> PriceService:
    global _price_service
    if _price_service is None:
        _price_service = PriceService(NseService(), YahooService())
    return _price_service


class SubscriptionBody(BaseModel):
    """Body for create / update. The (user_id, groupName) pair is unique —
    POSTing the same groupName twice updates the existing row.

    `recipientEmail` is a plain str here — the service-layer `_valid_email`
    regex catches malformed addresses and raises ValueError, which the
    route maps to a 400. Avoids depending on the optional `email-validator`
    package that pydantic.EmailStr requires.
    """
    groupName:       str       = Field("default", max_length=32)
    recipientEmail:  str       = Field(..., max_length=254)
    # 50 matches MAX_SYMBOLS_PER_SUB in email_digest_service. Pydantic
    # caps the client-side; the service also enforces it after dedupe.
    symbols:         list[str] = Field(default_factory=list, max_length=50)
    sendTimeIst:     str       = Field("18:00", pattern=r"^([01]\d|2[0-3]):([0-5]\d)$")
    enabled:         bool      = True


@router.get("/subscriptions")
async def list_subs(request: Request):
    return {"subscriptions": eds.list_subscriptions(_user_id(request))}


@router.post("/subscriptions")
async def upsert_sub(body: SubscriptionBody, request: Request):
    try:
        sub = eds.upsert_subscription(
            user_id        = _user_id(request),
            group_name     = body.groupName,
            recipient_email= body.recipientEmail.strip(),
            symbols        = body.symbols,
            send_time_ist  = body.sendTimeIst,
            enabled        = body.enabled,
        )
    except ValueError as exc:
        # `_valid_email` / `_valid_send_time` raise ValueError on malformed
        # input — surface as 400 with the original message.
        raise HTTPException(status_code=400, detail=str(exc))
    return sub


@router.delete("/subscriptions/{sub_id}")
async def delete_sub(sub_id: int, request: Request):
    if not eds.delete_subscription(_user_id(request), sub_id):
        raise HTTPException(status_code=404, detail="Subscription not found.")
    return {"deleted": sub_id}


@router.get("/config")
async def get_config(request: Request):
    """Surface non-sensitive SMTP wire-status so the settings page can show
    'configured / not configured'. NEVER returns the password."""
    _user_id(request)
    cfg = eds.smtp_config()
    return {
        "configured":   cfg["enabled"],
        "host":         cfg["host"],
        "port":         cfg["port"],
        "fromAddress":  cfg["from_addr"],
        "useTls":       cfg["use_tls"],
        "sendsPerMin":  eds.SEND_RATE_PER_MIN(),
        "sendsPerDay":  eds.SEND_RATE_PER_DAY(),
    }


@router.post("/send-now/{sub_id}")
async def send_now(sub_id: int, request: Request):
    """Force-enqueue this subscription's digest right now, bypassing the
    sendTimeIst gate. Still respects the daily/burst caps. Useful for
    'preview my digest' flow and for testing SMTP wiring.

    Pre-flight check: if SMTP isn't configured, we'd silently enqueue a row
    that the worker would refuse to send forever. Better to reject 400 up
    front so the user goes and fixes their env vars first.
    """
    if not eds.smtp_config()["enabled"]:
        raise HTTPException(
            status_code=400,
            detail="SMTP is not configured on the backend. Set SMTP_HOST, "
                   "SMTP_USERNAME, SMTP_PASSWORD in the env and restart the "
                   "backend before triggering a send.",
        )
    uid = _user_id(request)
    subs = [s for s in eds.list_subscriptions(uid) if s["id"] == int(sub_id)]
    if not subs:
        raise HTTPException(status_code=404, detail="Subscription not found.")
    sub = subs[0]
    # Build a temporary row that looks like the DB representation and call
    # the service-level renderer + enqueue helpers.
    try:
        rendered = await eds.render_digest(
            {"user_id": uid, **{
                "group_name": sub["groupName"],
                "recipient_email": sub["recipientEmail"],
                "symbols": sub["symbols"],
            }},
            _price(),
        )
    except Exception as exc:
        logger.exception("send_now: render failed")
        raise HTTPException(status_code=503,
                            detail=f"Digest render failed: {exc}") from exc

    # Inline insert with status='pending' so the worker picks it up on the
    # next tick. We do NOT update last_sent_date_ist so the scheduled fire
    # for today still runs (unless it already happened).
    import time as _time
    from app.lib.auth_store import get_conn
    with get_conn() as c:
        with c.cursor() as cur:
            cur.execute(
                """
                INSERT INTO email_digest_queue
                    (sub_id, recipient_email, subject, body_html,
                     body_text, status, enqueued_at_ms)
                VALUES (%s, %s, %s, %s, %s, 'pending', %s)
                """,
                (sub_id, sub["recipientEmail"], rendered["subject"],
                 rendered["html"], rendered["text"],
                 int(_time.time() * 1000)),
            )
        c.commit()
    return {"queued": True, "subject": rendered["subject"]}
