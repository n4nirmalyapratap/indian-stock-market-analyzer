from __future__ import annotations

import os
import time
from typing import Any, Optional

import jwt


def _secret() -> str:
    return os.environ.get("SESSION_SECRET", "changeme-in-production")


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
