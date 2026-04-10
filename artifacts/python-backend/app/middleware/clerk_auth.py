import os
import json
import base64
import logging
import time
from typing import Optional

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)


def _get_jwks_url() -> str:
    pk = os.environ.get("CLERK_PUBLISHABLE_KEY", "")
    if not pk:
        return ""
    for prefix in ("pk_test_", "pk_live_"):
        if pk.startswith(prefix):
            pk = pk[len(prefix):]
            break
    pk = pk.rstrip("$")
    pk += "=" * (-len(pk) % 4)
    try:
        frontend_api = base64.b64decode(pk).decode("utf-8").rstrip("$").strip()
        return f"https://{frontend_api}/.well-known/jwks.json"
    except Exception:
        return ""


JWKS_URL = _get_jwks_url()

_jwks_cache: Optional[dict] = None
_jwks_cache_time: float = 0
_JWKS_TTL = 3600


async def _get_jwks() -> dict:
    global _jwks_cache, _jwks_cache_time
    now = time.time()
    if _jwks_cache and (now - _jwks_cache_time) < _JWKS_TTL:
        return _jwks_cache
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(JWKS_URL)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_cache_time = now
        return _jwks_cache


async def verify_clerk_token(token: str) -> dict:
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    jwks = await _get_jwks()
    key = None
    for k in jwks.get("keys", []):
        if k.get("kid") == kid:
            key = RSAAlgorithm.from_jwk(json.dumps(k))
            break
    if not key:
        raise ValueError(f"JWK key not found for kid: {kid}")
    payload = jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        options={"verify_aud": False},
    )
    return payload


def _check_admin_token(token: str) -> bool:
    """Check whether the token is a valid admin session (imported lazily to avoid circular)."""
    try:
        from app.routes.admin import _valid_session  # noqa: PLC0415
        return _valid_session(token)
    except Exception:
        return False


class ClerkAuthMiddleware(BaseHTTPMiddleware):
    SKIP_PATHS = {"/api/healthz"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Admin routes use their own token auth — handled inside the route handlers
        if path.startswith("/api/admin"):
            return await call_next(request)

        if not path.startswith("/api") or path in self.SKIP_PATHS:
            return await call_next(request)

        # Allow requests carrying a valid admin session token to pass through any /api/* route
        admin_token = request.headers.get("X-Admin-Token", "")
        if admin_token and _check_admin_token(admin_token):
            request.state.user_id = "admin"
            return await call_next(request)

        if not JWKS_URL:
            logger.warning("CLERK_PUBLISHABLE_KEY not set — API auth disabled")
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"error": "Authentication required. Please sign in."},
            )

        token = auth_header[7:]
        try:
            payload = await verify_clerk_token(token)
            request.state.user_id = payload.get("sub")
        except Exception as e:
            logger.debug("Token verification failed: %s", e)
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid or expired session. Please sign in again."},
            )

        return await call_next(request)
