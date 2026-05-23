"""Per-user broker API credentials — encrypted-at-rest storage layer.

This module is the ONE place where broker credentials cross the in-memory ↔
database boundary. Everywhere else in the app uses the typed helpers below;
never touches the `encrypted_creds` column directly.

Security model
--------------
  * Credentials are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) using
    a key derived from `SESSION_SECRET`.
  * Derivation: HMAC-SHA256(SESSION_SECRET, "broker_keys_kdf_v1") → 32 bytes
    → base64url. Stable per-deployment, so restarts don't lose access; but
    rotating SESSION_SECRET invalidates every stored credential (intended).
  * Each ciphertext has its own random nonce/IV (Fernet handles this).
  * A leaked DB dump alone is useless without SESSION_SECRET.
  * SESSION_SECRET must already be set to a real 32+ char value (the app
    refuses to start otherwise — see env validation in main.py).

Why not per-user keys
---------------------
A per-user encryption key (derived from password / OAuth subject) would
let us claim "even the operator can't decrypt user creds." That sounds
nice but doesn't survive contact with reality:
  * OAuth sub is in the DB anyway — not a real secret from the operator.
  * The server has to decrypt creds on every quote call (operator runs
    the server, so operator sees the plaintext at least once).
The current single-key model is the honest "we encrypt for storage,
operator with the env var can decrypt." Don't oversell it.

API surface
-----------
  ALLOWED_BROKERS  → set of broker slugs the app accepts.
  set_broker_creds(user_id, broker, creds, active)
  get_broker_creds(user_id, broker)              → dict or None
  list_brokers_for_user(user_id)                 → metadata list (no creds)
  delete_broker_creds(user_id, broker)
  mark_test_result(user_id, broker, ok, error)
  list_active_creds_for_user(user_id)            → [(broker, creds), ...]
                                                   used by PriceService in Phase 9
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.lib.auth_store import ensure_primary_schema, get_conn

logger = logging.getLogger("broker_keys")

# Brokers we accept. Reject anything else at the API boundary so a typo
# can't accidentally create orphan rows. Add new brokers here when their
# clients ship (Phases 4-8). Each broker phase will also document its
# expected creds shape — we don't validate the shape here so adding a
# broker doesn't require schema migrations.
ALLOWED_BROKERS: set[str] = {
    "dhan", "zerodha", "upstox", "angel_one", "groww",
}


def _now_ms() -> int:
    return int(time.time() * 1000)


# ── Encryption ──────────────────────────────────────────────────────────────

_fernet_singleton: Optional[Fernet] = None


def _fernet() -> Fernet:
    """Lazy-init the Fernet instance from SESSION_SECRET.

    Cached as a module-level singleton because Fernet construction does a
    bit of key-derivation work — calling this in every encrypt/decrypt
    pass without caching adds measurable overhead on hot paths.
    """
    global _fernet_singleton
    if _fernet_singleton is not None:
        return _fernet_singleton

    secret = (os.environ.get("SESSION_SECRET") or "").strip()
    if not secret or len(secret) < 32:
        raise RuntimeError(
            "SESSION_SECRET must be set to a real 32+ char value before "
            "broker credentials can be stored. (Currently unset or too short.)"
        )
    # HKDF-style derivation. Stable as long as SESSION_SECRET doesn't
    # change. The context string `broker_keys_kdf_v1` keeps this key
    # domain-separated from any other HMAC derivations we might add
    # later — never reuse the same key material across purposes.
    digest = hmac.new(
        secret.encode("utf-8"),
        b"broker_keys_kdf_v1",
        hashlib.sha256,
    ).digest()  # 32 bytes
    _fernet_singleton = Fernet(base64.urlsafe_b64encode(digest))
    return _fernet_singleton


def _encrypt(creds: dict) -> str:
    """Encrypt a creds dict to a base64-encoded token suitable for PG TEXT."""
    plain = json.dumps(creds, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _fernet().encrypt(plain).decode("utf-8")


def _decrypt(token: str) -> Optional[dict]:
    """Decrypt back to dict. Returns None on tamper or wrong key.

    We swallow the decryption error rather than raise because the most
    likely cause is "SESSION_SECRET was rotated and old rows are now
    unreadable" — that's a user-facing condition (they need to re-enter
    their key), not a server crash.
    """
    try:
        decoded = _fernet().decrypt(token.encode("utf-8"))
        return json.loads(decoded.decode("utf-8"))
    except (InvalidToken, ValueError, UnicodeDecodeError):
        return None
    except Exception as exc:
        logger.warning("broker_keys decrypt failed: %s", str(exc)[:120])
        return None


# ── Storage helpers ────────────────────────────────────────────────────────


def set_broker_creds(
    user_id: str,
    broker: str,
    creds: dict,
    active: bool = True,
) -> dict:
    """Upsert credentials for (user, broker). Encrypts before storage.

    Returns a metadata dict (no creds) matching what the list endpoint
    returns so the frontend can update its state without a second fetch.

    Raises ValueError if `broker` isn't in ALLOWED_BROKERS, or if `creds`
    is empty (would silently lock the user out). All other errors
    propagate to the caller so the route handler can return a clean 500.
    """
    if broker not in ALLOWED_BROKERS:
        raise ValueError(f"Unknown broker {broker!r}. "
                         f"Allowed: {sorted(ALLOWED_BROKERS)}")
    if not isinstance(creds, dict) or not creds:
        raise ValueError("Credentials must be a non-empty dict.")

    ensure_primary_schema()
    token = _encrypt(creds)
    now_ms = _now_ms()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_broker_keys
                       (user_id, broker, encrypted_creds, active,
                        created_at_ms, updated_at_ms)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, broker) DO UPDATE
                       SET encrypted_creds = EXCLUDED.encrypted_creds,
                           active          = EXCLUDED.active,
                           updated_at_ms   = EXCLUDED.updated_at_ms,
                           last_test_status= '',
                           last_test_at_ms = NULL,
                           last_test_error = ''
                """,
                (user_id, broker, token, active, now_ms, now_ms),
            )
    return {
        "broker":    broker,
        "active":    active,
        "configured": True,
        "updatedAt": now_ms,
    }


def get_broker_creds(user_id: str, broker: str) -> Optional[dict]:
    """Return the decrypted creds dict for (user, broker), or None.

    Only callers inside the server should use this — never expose the
    output via an API endpoint. Broker clients call this from server-side
    code to authenticate their upstream calls.
    """
    if broker not in ALLOWED_BROKERS:
        return None
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT encrypted_creds, active FROM user_broker_keys "
                "WHERE user_id = %s AND broker = %s",
                (user_id, broker),
            )
            row = cur.fetchone()
    if not row:
        return None
    if not row.get("active"):
        return None
    return _decrypt(row["encrypted_creds"])


def list_brokers_for_user(user_id: str) -> list[dict]:
    """Return metadata for every broker the user has configured.

    No decrypted creds. Used by the Settings UI to render the per-broker
    cards with their state (active / configured / last test result).
    """
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT broker, active, last_test_status, last_test_at_ms, "
                "       last_test_error, created_at_ms, updated_at_ms "
                "FROM user_broker_keys WHERE user_id = %s "
                "ORDER BY broker",
                (user_id,),
            )
            rows = cur.fetchall()
    out: list[dict] = []
    for r in rows:
        out.append({
            "broker":         r["broker"],
            "active":         bool(r["active"]),
            "configured":     True,
            "lastTestStatus": r.get("last_test_status") or "",
            "lastTestAtMs":   r.get("last_test_at_ms"),
            "lastTestError":  r.get("last_test_error") or "",
            "createdAt":      r.get("created_at_ms"),
            "updatedAt":      r.get("updated_at_ms"),
        })
    return out


def delete_broker_creds(user_id: str, broker: str) -> bool:
    """Remove the user's creds for this broker. Returns True if a row was
    deleted, False if none existed."""
    if broker not in ALLOWED_BROKERS:
        return False
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM user_broker_keys "
                "WHERE user_id = %s AND broker = %s",
                (user_id, broker),
            )
            return cur.rowcount > 0


def mark_test_result(user_id: str, broker: str, ok: bool, error: str = "") -> None:
    """Record the outcome of a 'Test connection' attempt.

    Stored in-band on the credentials row so the Settings UI can show
    e.g. ✓ Tested 5 min ago / ✗ Invalid access token. Truncates errors
    to a reasonable length so a verbose stack trace can't bloat the row.
    """
    if broker not in ALLOWED_BROKERS:
        return
    ensure_primary_schema()
    status = "ok" if ok else "failed"
    err = (error or "")[:300]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE user_broker_keys "
                "   SET last_test_status = %s, last_test_at_ms = %s, "
                "       last_test_error = %s, updated_at_ms = %s "
                " WHERE user_id = %s AND broker = %s",
                (status, _now_ms(), err, _now_ms(), user_id, broker),
            )


def list_active_creds_for_user(user_id: str) -> list[tuple[str, dict]]:
    """Return every active broker's decrypted creds for this user.

    Used by Phase 9's `UserPriceService` to know which broker tiers to
    try first when answering a price request for this user. Returns
    (broker, creds) tuples; brokers whose decryption fails (e.g. after
    SESSION_SECRET rotation) are silently skipped — they'll show up in
    the Settings UI as needing re-entry.
    """
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT broker, encrypted_creds FROM user_broker_keys "
                "WHERE user_id = %s AND active = TRUE ORDER BY broker",
                (user_id,),
            )
            rows = cur.fetchall()
    out: list[tuple[str, dict]] = []
    for r in rows:
        creds = _decrypt(r["encrypted_creds"])
        if creds is not None:
            out.append((r["broker"], creds))
    return out
