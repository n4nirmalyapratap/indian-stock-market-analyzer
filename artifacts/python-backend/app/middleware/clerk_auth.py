import os
import logging
from typing import Optional

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)


def _verify_custom_token(token: str) -> Optional[dict]:
    try:
        from app.routes.auth import verify_custom_token  # noqa: PLC0415
        return verify_custom_token(token)
    except Exception:
        return None


def _check_admin_token(token: str) -> bool:
    try:
        from app.routes.admin import _valid_session  # noqa: PLC0415
        return _valid_session(token)
    except Exception:
        return False


class ClerkAuthMiddleware(BaseHTTPMiddleware):
    SKIP_PATHS = {"/api/healthz"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path.startswith("/api/admin"):
            return await call_next(request)

        if path.startswith("/api/auth"):
            return await call_next(request)

        if not path.startswith("/api") or path in self.SKIP_PATHS:
            return await call_next(request)

        admin_token = request.headers.get("X-Admin-Token", "")
        if admin_token and _check_admin_token(admin_token):
            request.state.user_id = "admin"
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"error": "Authentication required. Please sign in."},
            )

        token = auth_header[7:]

        custom_payload = _verify_custom_token(token)
        if custom_payload:
            request.state.user_id = custom_payload.get("sub", "custom")
            return await call_next(request)

        return JSONResponse(
            status_code=401,
            content={"error": "Invalid or expired session. Please sign in again."},
        )
