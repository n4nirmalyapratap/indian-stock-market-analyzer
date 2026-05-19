from __future__ import annotations

import os
import time
from typing import Any, Optional

import jwt


# ── SECURITY ────────────────────────────────────────────────────────────────
# SESSION_SECRET is the HS256 signing key for every JWT issued by this app
# (user and admin scopes). If it is missing, weak, or one of the well-known
# placeholder strings that have shipped in earlier .env templates, every
# token in the system is forgeable — including admin tokens. We therefore
# refuse to mint or verify tokens unless a real secret is configured.
# Fail loud, not silent.
# ────────────────────────────────────────────────────────────────────────────

_KNOWN_BAD_SECRETS = {
    "",
    "changeme-in-production",
    "replace_with_a_long_random_secret_here",
    "A-Long-Random-String-123",
    "your-secret-here",
    "supersecretkey123",
    "secret",
    "changeme",
}

_MIN_SECRET_LEN = 32


class InsecureSessionSecretError(RuntimeError):
    """Raised when SESSION_SECRET is unset, too short, or a known placeholder."""


def _secret() -> str:
    raw = os.environ.get("SESSION_SECRET", "")
    if raw in _KNOWN_BAD_SECRETS or len(raw) < _MIN_SECRET_LEN:
        raise InsecureSessionSecretError(
            "SESSION_SECRET is missing, too short, or a known placeholder. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\" "
            "and set it in your environment (Replit Secrets / Container App secret) "
            "before starting the server."
        )
    return raw


def validate_session_secret() -> None:
    """Call at app startup to fail loud before serving any traffic."""
    _secret()


def create_token(user: dict[str, Any], *, scope: str) -> str:
    ttl = 8 * 3600 if scope == "admin" else 30 * 86400
    now = int(time.time())
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "name": user.get("name", ""),
        "picture_url": user.get("picture_url", ""),
        "provider": user.get("auth_provider", "google"),
        "is_admin": bool(user.get("is_admin")),
        "scope": scope,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def verify_token(token: str, *, required_scope: Optional[str] = None) -> dict[str, Any]:
    payload = jwt.decode(token, _secret(), algorithms=["HS256"])
    scope = payload.get("scope")
    if required_scope and scope != required_scope:
        raise jwt.InvalidTokenError(f"Token scope {scope!r} is not allowed here.")
    if scope not in {"user", "admin"}:
        raise jwt.InvalidTokenError("Unsupported token scope.")
    return payload
