"""
Email-digest subscription + queued send service.

Architecture (see also docs/email_digest.md):

  - Scheduler (`_email_digest_scheduler` in main.py) wakes once a minute,
    walks `email_digest_subs`, and inserts a queue row for every subscription
    that's due today but hasn't been sent yet. The digest is *materialised*
    at enqueue time (subject + html + text frozen on the row) so a user
    editing their subscription between enqueue and send doesn't change what
    gets delivered.

  - Worker (`_email_digest_worker` in main.py) drains the queue at a
    controlled rate via a token-bucket throttle (default: 20 sends/minute,
    400/day). When the bucket is empty the worker just sleeps; when the
    day cap is hit it stops sending and resumes at the IST day boundary.

  - SMTP transport uses the stdlib `smtplib` + `email.message` — no extra
    dependencies. Gmail / Workspace / SES / any STARTTLS-capable server
    works as long as you supply SMTP_HOST/PORT/USER/PASS env vars.

Failure modes:
  - Bad credentials: every send raises smtplib.SMTPAuthenticationError →
    the row goes to `status='failed'` immediately (no retry) so we don't
    burn through retries against the same bad creds.
  - Transient (4xx/timeout): row stays `pending`, attempt counter bumped,
    next_retry_ms set to now + exp-backoff. The worker picks it back up on
    its next tick.
  - Soft 5xx: same as transient.
  - Daily cap hit: worker stops sending until the IST day rolls over.

Public API (called from routes + scheduler):
    list_subscriptions(user_id)             → list[dict]
    upsert_subscription(...)                → dict
    delete_subscription(user_id, sub_id)    → bool
    enqueue_due_digests(now_ist_dt)         → {enqueued, skipped}
    drain_queue(price_service)              → {sent, failed, throttled}
"""
from __future__ import annotations

import asyncio
import email.utils as email_utils
import logging
import os
import smtplib
import time
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from typing import Any, Optional

from psycopg.rows import dict_row

from app.lib.auth_store import ensure_primary_schema, get_conn

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


# ── Configuration ─────────────────────────────────────────────────────────────

def _s(name: str, default: str = "") -> str:
    return (os.environ.get(name, "") or "").strip() or default


def _i(name: str, default: int) -> int:
    raw = _s(name, "")
    try:
        return int(raw) if raw else default
    except (TypeError, ValueError):
        return default


def _b(name: str, default: bool) -> bool:
    raw = _s(name, "").lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def smtp_config() -> dict:
    """Pull SMTP config from env. Returns a dict with all the knobs the worker
    needs; `enabled` flips False when host/user/pass aren't all present so
    the worker becomes a silent no-op in dev."""
    host = _s("SMTP_HOST")
    user = _s("SMTP_USERNAME")
    pwd  = _s("SMTP_PASSWORD")
    return {
        "host":      host,
        "port":      _i("SMTP_PORT", 587),
        "username":  user,
        "password":  pwd,
        "use_tls":   _b("SMTP_USE_TLS", True),
        "from_addr": _s("SMTP_FROM_EMAIL", user),
        "from_name": _s("SMTP_FROM_NAME", "Indian Stock Market Analyzer"),
        "enabled":   bool(host and user and pwd),
    }


# Throttle knobs — see header comment.
SEND_RATE_PER_MIN = lambda: _i("EMAIL_DIGEST_SENDS_PER_MIN", 20)  # noqa: E731
SEND_RATE_PER_DAY = lambda: _i("EMAIL_DIGEST_SENDS_PER_DAY", 400)  # noqa: E731

# Default symbol cap per subscription — anything beyond this is dropped at
# enqueue with a warning so a typo of `RELIANCE,TCS,…` (literal "…") doesn't
# wedge the renderer.
MAX_SYMBOLS_PER_SUB = 50

# Per-quote timeout. With ~50 symbols hitting NSE/Yahoo concurrently a slow
# upstream can stall the whole digest; 6s per fetch keeps total render time
# under ~10s in the worst case while still being kind to slow networks.
_PER_QUOTE_TIMEOUT_SEC = 6.0

# Soft cap on rendered body size. Gmail itself accepts ~25 MB, but anything
# beyond ~250 KB is almost certainly a bug (e.g. a runaway symbol list) and
# the resulting email would be unreadable anyway. We truncate to be safe.
_MAX_BODY_BYTES = 250_000


# ── DB helpers ────────────────────────────────────────────────────────────────

def _conn():
    """Open a Postgres connection.

    Schema bootstrap is best-effort: if the DB is briefly unreachable when
    this module is imported (e.g. compose starts the backend before
    postgres is healthy), we don't want the import to error out — that
    would prevent the routes from being registered at all and the user
    would see 404s forever even after the DB comes up. So we run the
    bootstrap defensively on every connect; ``ensure_primary_schema`` is
    idempotent and protected by a double-checked lock, so the cost is
    one boolean comparison after the first successful call.
    """
    try:
        ensure_primary_schema()
    except Exception as exc:  # pragma: no cover
        logger.warning("email_digest: schema bootstrap deferred: %s", exc)
    conn = get_conn()
    conn.row_factory = dict_row  # type: ignore[attr-defined]
    return conn


def _now_ms() -> int:
    return int(time.time() * 1000)


def _ist_today() -> str:
    return datetime.now(tz=IST).date().isoformat()


# ── Subscription CRUD ────────────────────────────────────────────────────────

def list_subscriptions(user_id: str) -> list[dict]:
    """Return every subscription for one user, oldest first."""
    if not user_id:
        return []
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, group_name, recipient_email,
                       symbols, send_time_ist, enabled,
                       last_sent_date_ist, created_at, updated_at
                  FROM email_digest_subs
                 WHERE user_id = %s
              ORDER BY created_at ASC
                """,
                (user_id,),
            )
            rows = cur.fetchall()
    return [_row_to_dict(r) for r in rows]


def upsert_subscription(
    *,
    user_id: str,
    group_name: str,
    recipient_email: str,
    symbols: list[str],
    send_time_ist: str = "18:00",
    enabled: bool = True,
) -> dict:
    """Create or update one subscription. Unique on (user_id, group_name)."""
    if not user_id:
        raise ValueError("user_id is required")
    if not _valid_email(recipient_email):
        raise ValueError(f"invalid recipient_email: {recipient_email!r}")
    if not _valid_send_time(send_time_ist):
        raise ValueError(f"send_time_ist must be HH:MM (24h IST), got {send_time_ist!r}")

    group = (group_name or "default").strip()[:32]
    clean_symbols = _normalise_symbols(symbols)
    if not clean_symbols:
        # An empty symbol list is allowed — the digest then shows the user's
        # whole portfolio. We still enforce a cap when the list is non-empty.
        pass
    elif len(clean_symbols) > MAX_SYMBOLS_PER_SUB:
        clean_symbols = clean_symbols[:MAX_SYMBOLS_PER_SUB]

    now = _now_ms()
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                """
                INSERT INTO email_digest_subs
                    (user_id, group_name, recipient_email, symbols,
                     send_time_ist, enabled, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, group_name) DO UPDATE SET
                    recipient_email = EXCLUDED.recipient_email,
                    symbols         = EXCLUDED.symbols,
                    send_time_ist   = EXCLUDED.send_time_ist,
                    enabled         = EXCLUDED.enabled,
                    updated_at      = EXCLUDED.updated_at
                RETURNING id, user_id, group_name, recipient_email,
                          symbols, send_time_ist, enabled,
                          last_sent_date_ist, created_at, updated_at
                """,
                (user_id, group, recipient_email, clean_symbols,
                 send_time_ist, enabled, now, now),
            )
            row = cur.fetchone()
        c.commit()
    return _row_to_dict(row) if row else {}


def delete_subscription(user_id: str, sub_id: int) -> bool:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "DELETE FROM email_digest_subs WHERE id = %s AND user_id = %s",
                (int(sub_id), user_id),
            )
            deleted = cur.rowcount > 0
        c.commit()
    return deleted


def _row_to_dict(row: dict) -> dict:
    return {
        "id":              int(row["id"]),
        "groupName":       row["group_name"],
        "recipientEmail":  row["recipient_email"],
        "symbols":         list(row["symbols"] or []),
        "sendTimeIst":     row["send_time_ist"],
        "enabled":         bool(row["enabled"]),
        "lastSentDateIst": row["last_sent_date_ist"],
        "createdAt":       int(row["created_at"]),
        "updatedAt":       int(row["updated_at"]),
    }


# ── Validation ───────────────────────────────────────────────────────────────

import re as _re

_EMAIL_RE = _re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_HHMM_RE  = _re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _valid_email(s: str) -> bool:
    return bool(s and _EMAIL_RE.match(s))


def _valid_send_time(s: str) -> bool:
    return bool(_HHMM_RE.match(s or ""))


def _normalise_symbols(symbols: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for s in symbols or []:
        u = (s or "").strip().upper()
        if not u or u in seen:
            continue
        # Strip exchange suffixes — match the convention used in
        # portfolio_service._norm_symbol.
        for suffix in ("-EQ", ".NS", ".BO", ":NSE", ":BSE"):
            if u.endswith(suffix):
                u = u[: -len(suffix)]
        if not u:
            continue
        seen.add(u)
        out.append(u)
    return out


# ── Digest rendering ─────────────────────────────────────────────────────────

async def render_digest(sub: dict, price_service) -> dict:
    """Build the actual digest content for one subscription.

    Returns ``{subject, html, text}``. Pulls live data via price_service so
    the digest reflects the latest close at enqueue time.
    """
    today_ist = _ist_today()
    symbols = sub.get("symbols") or []
    # If the subscription doesn't pin a symbol list, fall back to the user's
    # portfolio holdings (the portfolio service is the source of truth for
    # what they own).
    if not symbols:
        try:
            from . import portfolio_service as ps  # noqa: PLC0415
            portfolios = ps.list_portfolios(sub["user_id"])
            derived: set[str] = set()
            for p in portfolios:
                holdings = ps.derive_holdings(p["id"])
                # Guard against qty=None — `dict.get(k, 0)` returns the value
                # even when it's None, which would TypeError on `> 0`.
                derived.update(h["symbol"] for h in holdings if (h.get("qty") or 0) > 0)
            symbols = sorted(derived)
        except Exception:
            symbols = []

    rows = await _gather_rows(symbols, price_service)
    market_state, sector_snippet = await _market_snippet()

    subject = f"📈 Daily digest — {today_ist} · {len(rows)} holdings"
    if not rows:
        subject = f"📈 Daily digest — {today_ist}"
    html = _render_html(today_ist, sub, rows, market_state, sector_snippet)
    text = _render_text(today_ist, sub, rows, market_state, sector_snippet)

    # Belt-and-braces size guard — a runaway symbol list shouldn't produce
    # a 5 MB email that bounces from spam filters. Truncate both bodies and
    # tack on a "[truncated]" notice. UTF-8 byte length, not char length,
    # because the actual SMTP transport counts bytes.
    if len(html.encode("utf-8")) > _MAX_BODY_BYTES:
        html = html[:_MAX_BODY_BYTES] + "<p>[digest truncated — too large]</p>"
    if len(text.encode("utf-8")) > _MAX_BODY_BYTES:
        text = text[:_MAX_BODY_BYTES] + "\n[digest truncated — too large]"

    return {"subject": subject, "html": html, "text": text}


async def _gather_rows(symbols: list[str], price_service) -> list[dict]:
    """Pull one quote per symbol, return a list ready for the table renderer.

    Each fetch has its own ``_PER_QUOTE_TIMEOUT_SEC`` timeout so one slow
    upstream (NSE / Yahoo) can't hang the whole digest. Concurrent via
    ``asyncio.gather(return_exceptions=True)`` — a thrown task can't poison
    a sibling. Failures degrade to a row with ``error`` set, which the
    renderer marks visually instead of silently rendering as `—`.
    """
    if not symbols:
        return []

    async def _one(sym: str) -> dict:
        try:
            qm = await asyncio.wait_for(
                price_service.get_quote_with_meta(sym, cross_check=False),
                timeout=_PER_QUOTE_TIMEOUT_SEC,
            )
            q = (qm or {}).get("quote") or {}
            last = q.get("lastPrice") or q.get("regularMarketPrice")
            prev = q.get("previousClose") or q.get("regularMarketPreviousClose")
            chg_pct = None
            if last and prev:
                try:
                    chg_pct = (float(last) - float(prev)) / float(prev) * 100.0
                except (TypeError, ValueError, ZeroDivisionError):
                    chg_pct = None
            return {
                "symbol": sym,
                "name":   q.get("companyName") or q.get("longName") or sym,
                "last":   float(last) if last else None,
                "chgPct": chg_pct,
                "error":  None,
            }
        except asyncio.TimeoutError:
            return {"symbol": sym, "name": sym, "last": None,
                    "chgPct": None, "error": "quote timed out"}
        except Exception as exc:
            return {"symbol": sym, "name": sym, "last": None,
                    "chgPct": None, "error": str(exc)[:80]}

    # return_exceptions=True is belt-and-braces — every _one() already
    # catches its own exceptions, but if we ever miss one we want a
    # row-shaped result back rather than aborting the whole gather.
    results = await asyncio.gather(
        *[_one(s) for s in symbols], return_exceptions=True,
    )
    out: list[dict] = []
    for r in results:
        if isinstance(r, dict):
            out.append(r)
        else:
            # Shouldn't reach here because _one swallows exceptions; if it
            # does, surface the row as an error row instead of a raw raise.
            out.append({"symbol": "?", "name": "?", "last": None,
                        "chgPct": None, "error": str(r)[:80]})
    return out


async def _market_snippet() -> tuple[str, str]:
    """Cheap one-line summary of NSE market state and top-moving sector,
    rendered into both the HTML and text bodies. Always returns something —
    even on upstream errors — to keep the digest informative."""
    try:
        from . import market_cache_service as mcs  # noqa: PLC0415
        state = mcs.current_market_state()
    except Exception:
        state = "UNKNOWN"

    snippet = ""
    try:
        from .sectors_service import SectorsService  # noqa: PLC0415
        from .nse_service import NseService           # noqa: PLC0415
        from .yahoo_service import YahooService       # noqa: PLC0415
        svc = SectorsService(NseService(), YahooService())
        rot = await svc.get_sector_rotation()
        phase = (rot or {}).get("phase") or "—"
        leaders = (rot or {}).get("recommendations") or []
        top = leaders[0].get("sector") if leaders else None
        snippet = f"Phase: {phase}" + (f" · Leader: {top}" if top else "")
    except Exception as exc:
        logger.debug("digest market snippet failed: %s", exc)
        snippet = "Sector rotation snapshot unavailable."

    return state, snippet


def _fmt_pct(x: Optional[float]) -> str:
    if x is None:
        return "—"
    sign = "+" if x >= 0 else ""
    return f"{sign}{x:.2f}%"


def _fmt_inr(x: Optional[float]) -> str:
    if x is None:
        return "—"
    return f"₹{x:,.2f}"


def _render_html(date_ist: str, sub: dict, rows: list[dict],
                 market_state: str, sector_snippet: str) -> str:
    """Pure-string HTML render. Deliberately doesn't use Jinja2 — adding a
    template engine for one email isn't worth the dependency and keeps the
    digest easy to read in `git diff`."""
    rows_html = []
    if not rows:
        rows_html.append(
            "<tr><td colspan='3' style='padding:12px;color:#888;text-align:center;font-size:13px;'>"
            "No symbols configured — add some on the Email Digest settings page."
            "</td></tr>"
        )
    else:
        for r in rows:
            # Surface errored rows distinctly so the user can tell which
            # symbols failed vs which simply had no price move today.
            if r.get("error"):
                rows_html.append(
                    f"<tr>"
                    f"<td style='padding:8px 12px;border-bottom:1px solid #eee;font-family:monospace;'>"
                    f"<b>{_escape(r['symbol'])}</b><br/>"
                    f"<span style='color:#888;font-family:sans-serif;font-size:11px;'>{_escape(r['name'])}</span></td>"
                    f"<td colspan='2' style='padding:8px 12px;border-bottom:1px solid #eee;font-family:sans-serif;font-size:11px;color:#c1272d;text-align:right;'>"
                    f"⚠ price unavailable ({_escape(r['error'])})</td>"
                    f"</tr>"
                )
                continue
            colour = "#0a8a3e" if (r["chgPct"] or 0) > 0 else (
                     "#c1272d" if (r["chgPct"] or 0) < 0 else "#666")
            rows_html.append(
                f"<tr>"
                f"<td style='padding:8px 12px;border-bottom:1px solid #eee;font-family:monospace;'>"
                f"<b>{_escape(r['symbol'])}</b><br/>"
                f"<span style='color:#888;font-family:sans-serif;font-size:11px;'>{_escape(r['name'])}</span></td>"
                f"<td style='padding:8px 12px;border-bottom:1px solid #eee;text-align:right;font-family:monospace;'>"
                f"{_fmt_inr(r['last'])}</td>"
                f"<td style='padding:8px 12px;border-bottom:1px solid #eee;text-align:right;font-family:monospace;color:{colour};'>"
                f"{_fmt_pct(r['chgPct'])}</td>"
                f"</tr>"
            )

    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f6f7fb;font-family:Arial,Helvetica,sans-serif;color:#222;">
<div style="max-width:600px;margin:0 auto;padding:20px;">
  <h1 style="font-size:18px;margin:0 0 4px 0;">📈 Daily Stock Digest</h1>
  <p style="color:#777;font-size:12px;margin:0 0 16px 0;">
    {_escape(date_ist)} · Group: <b>{_escape(sub.get("groupName") or "default")}</b> · Market: <b>{_escape(market_state)}</b>
  </p>
  <p style="color:#444;font-size:13px;margin:0 0 16px 0;">{_escape(sector_snippet)}</p>
  <table cellspacing="0" cellpadding="0" style="width:100%;background:#fff;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">
    <thead>
      <tr style="background:#f1f3f8;">
        <th style="padding:8px 12px;text-align:left;font-size:11px;color:#666;text-transform:uppercase;">Symbol</th>
        <th style="padding:8px 12px;text-align:right;font-size:11px;color:#666;text-transform:uppercase;">Last</th>
        <th style="padding:8px 12px;text-align:right;font-size:11px;color:#666;text-transform:uppercase;">Day %</th>
      </tr>
    </thead>
    <tbody>{"".join(rows_html)}</tbody>
  </table>
  <p style="color:#aaa;font-size:11px;margin-top:24px;line-height:1.6;">
    Not investment advice. AI-generated educational content only. Consult a
    SEBI-registered investment adviser before making investment decisions.
    Unsubscribe or change your subscription on the Email Digest settings page.
  </p>
</div>
</body></html>"""


def _render_text(date_ist: str, sub: dict, rows: list[dict],
                 market_state: str, sector_snippet: str) -> str:
    """Plain-text alternative — required by RFC 2822 multipart/alternative
    spam-filter heuristics. Mirrors the HTML content closely."""
    lines = [
        f"Daily Stock Digest — {date_ist}",
        f"Group: {sub.get('groupName') or 'default'}",
        f"Market state: {market_state}",
        f"{sector_snippet}",
        "",
    ]
    if not rows:
        lines.append("(No symbols configured — add some on the Email Digest settings page.)")
    else:
        lines.append(f"{'Symbol':<14} {'Last':>12} {'Day %':>9}")
        lines.append("-" * 38)
        for r in rows:
            if r.get("error"):
                # Plain-text counterpart of the error-row treatment in the
                # HTML body so the text alternative isn't silently
                # misleading.
                lines.append(f"{r['symbol']:<14}  ! price unavailable ({r['error']})")
            else:
                lines.append(f"{r['symbol']:<14} {_fmt_inr(r['last']):>12} {_fmt_pct(r['chgPct']):>9}")
    lines.append("")
    lines.append("Not investment advice. AI-generated educational content only.")
    return "\n".join(lines)


def _escape(s: Any) -> str:
    """Tiny HTML-escape — avoids `cgi.escape` (deprecated)."""
    if s is None:
        return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


# ── Enqueue (called from scheduler) ──────────────────────────────────────────

async def enqueue_due_digests(price_service) -> dict:
    """Walk every enabled subscription. For each one whose send_time_ist has
    passed today AND that hasn't been sent today yet, render the digest and
    insert a queue row.

    Idempotent — `last_sent_date_ist` is updated only when the queue row is
    successfully inserted, so a scheduler crash mid-loop just retries.
    """
    now_ist = datetime.now(tz=IST)
    today_ist = now_ist.date().isoformat()
    enqueued, skipped = 0, 0

    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, group_name, recipient_email,
                       symbols, send_time_ist, last_sent_date_ist
                  FROM email_digest_subs
                 WHERE enabled = TRUE
                """
            )
            subs = cur.fetchall()

    for sub in subs:
        # Already queued/sent today
        if sub["last_sent_date_ist"] == today_ist:
            skipped += 1
            continue
        # Not yet time
        if not _due_now(sub["send_time_ist"], now_ist):
            skipped += 1
            continue

        try:
            rendered = await render_digest(dict(sub), price_service)
        except Exception as exc:
            logger.warning("digest render failed for sub=%s: %s", sub["id"], exc)
            skipped += 1
            continue

        try:
            with _conn() as c:
                with c.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO email_digest_queue
                            (sub_id, recipient_email, subject, body_html,
                             body_text, status, enqueued_at_ms)
                        VALUES (%s, %s, %s, %s, %s, 'pending', %s)
                        """,
                        (sub["id"], sub["recipient_email"],
                         rendered["subject"], rendered["html"],
                         rendered["text"], _now_ms()),
                    )
                    cur.execute(
                        "UPDATE email_digest_subs SET last_sent_date_ist = %s, "
                        "updated_at = %s WHERE id = %s",
                        (today_ist, _now_ms(), sub["id"]),
                    )
                c.commit()
            enqueued += 1
        except Exception as exc:
            logger.warning("digest enqueue failed for sub=%s: %s", sub["id"], exc)
            skipped += 1

    return {"enqueued": enqueued, "skipped": skipped, "candidates": len(subs)}


def _due_now(send_time_ist: str, now_ist: datetime) -> bool:
    """True if the send_time_ist (HH:MM) has already passed in `now_ist`."""
    try:
        hh, mm = (int(p) for p in (send_time_ist or "18:00").split(":"))
    except Exception:
        return False
    target = now_ist.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return now_ist >= target


# ── Worker (called from scheduler) ───────────────────────────────────────────

def drain_queue(max_sends: Optional[int] = None) -> dict:
    """Send up to `max_sends` queued digests, respecting the daily cap.

    Token-bucket throttle:
      * Per-tick burst capped at `EMAIL_DIGEST_SENDS_PER_MIN` (default 20)
      * Daily cap `EMAIL_DIGEST_SENDS_PER_DAY` (default 400) tracked in
        `email_digest_send_counter` keyed by IST date.

    Per-message:
      * Authentication errors → permanent failure (status='failed')
      * Transient errors → row stays pending, attempts+=1, next_retry_ms
        set via exponential backoff (60s × 2^attempts capped at 1 hour)
    """
    cfg = smtp_config()
    if not cfg["enabled"]:
        logger.debug("email_digest: SMTP not configured; worker is a no-op")
        return {"sent": 0, "failed": 0, "throttled": True,
                "reason": "smtp_not_configured"}

    # How many can we still send today?
    today_ist = _ist_today()
    daily_cap = SEND_RATE_PER_DAY()
    burst_cap = max_sends if max_sends is not None else SEND_RATE_PER_MIN()
    sends_today = _read_counter(today_ist)
    if sends_today >= daily_cap:
        return {"sent": 0, "failed": 0, "throttled": True,
                "reason": "daily_cap", "sentToday": sends_today,
                "dailyCap": daily_cap}

    headroom = min(burst_cap, daily_cap - sends_today)
    if headroom <= 0:
        return {"sent": 0, "failed": 0, "throttled": True,
                "reason": "burst_cap"}

    now_ms = _now_ms()
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                """
                SELECT id, sub_id, recipient_email, subject,
                       body_html, body_text, attempts
                  FROM email_digest_queue
                 WHERE status = 'pending'
                   AND (next_retry_ms IS NULL OR next_retry_ms <= %s)
              ORDER BY enqueued_at_ms ASC
                 LIMIT %s
                """,
                (now_ms, headroom),
            )
            batch = cur.fetchall()

    sent, failed = 0, 0
    for row in batch:
        try:
            _send_one(cfg, row)
            _mark_sent(row["id"])
            sent += 1
            sends_today += 1
            if sends_today >= daily_cap:
                logger.info("email_digest: daily cap %d hit, pausing", daily_cap)
                break
        except smtplib.SMTPAuthenticationError as exc:
            logger.error("email_digest: SMTP auth failed for queue=%s: %s",
                         row["id"], exc)
            _mark_failed(row["id"], f"auth: {exc}")
            failed += 1
        except smtplib.SMTPRecipientsRefused as exc:
            logger.warning("email_digest: recipient refused for queue=%s: %s",
                           row["id"], exc)
            _mark_failed(row["id"], f"recipient_refused: {exc}")
            failed += 1
        except Exception as exc:
            attempts = int(row["attempts"] or 0) + 1
            backoff_s = min(3600, 60 * (2 ** attempts))
            next_retry_ms = now_ms + backoff_s * 1000
            logger.warning(
                "email_digest: send failed for queue=%s (attempt %d, retry in %ds): %s",
                row["id"], attempts, backoff_s, exc,
            )
            _mark_retry(row["id"], attempts, next_retry_ms, str(exc)[:300])
            failed += 1

    if sent > 0:
        _bump_counter(today_ist, sent)

    return {
        "sent": sent, "failed": failed, "throttled": False,
        "sentToday": sends_today, "dailyCap": daily_cap,
    }


def _send_one(cfg: dict, row: dict) -> None:
    """Build a multipart/alternative message and dispatch via SMTP STARTTLS."""
    msg = EmailMessage()
    msg["Subject"] = row["subject"]
    msg["From"]    = email_utils.formataddr((cfg["from_name"], cfg["from_addr"]))
    msg["To"]      = row["recipient_email"]
    msg["Date"]    = email_utils.formatdate(localtime=True)
    msg["Message-ID"] = email_utils.make_msgid(domain="indian-stock-market-analyzer")
    msg.set_content(row["body_text"])
    msg.add_alternative(row["body_html"], subtype="html")

    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as smtp:
        smtp.ehlo()
        if cfg["use_tls"]:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(cfg["username"], cfg["password"])
        smtp.send_message(msg)


def _mark_sent(queue_id: int) -> None:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "UPDATE email_digest_queue SET status = 'sent', "
                "attempts = attempts + 1, sent_at_ms = %s, "
                "last_error = NULL, next_retry_ms = NULL WHERE id = %s",
                (_now_ms(), queue_id),
            )
        c.commit()


def _mark_failed(queue_id: int, error: str) -> None:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "UPDATE email_digest_queue SET status = 'failed', "
                "attempts = attempts + 1, last_error = %s, "
                "next_retry_ms = NULL WHERE id = %s",
                (error[:500], queue_id),
            )
        c.commit()


def _mark_retry(queue_id: int, attempts: int,
                next_retry_ms: int, error: str) -> None:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "UPDATE email_digest_queue SET attempts = %s, "
                "last_error = %s, next_retry_ms = %s WHERE id = %s",
                (attempts, error[:500], next_retry_ms, queue_id),
            )
        c.commit()


# ── Daily send counter (token bucket) ────────────────────────────────────────

def _read_counter(date_ist: str) -> int:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT sends_today FROM email_digest_send_counter WHERE date_ist = %s",
                (date_ist,),
            )
            row = cur.fetchone()
    return int(row["sends_today"]) if row else 0


def _bump_counter(date_ist: str, delta: int) -> None:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                """
                INSERT INTO email_digest_send_counter (date_ist, sends_today, updated_at_ms)
                VALUES (%s, %s, %s)
                ON CONFLICT (date_ist) DO UPDATE SET
                    sends_today = email_digest_send_counter.sends_today + EXCLUDED.sends_today,
                    updated_at_ms = EXCLUDED.updated_at_ms
                """,
                (date_ist, delta, _now_ms()),
            )
        c.commit()
