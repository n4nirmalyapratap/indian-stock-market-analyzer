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


class AppAuthMiddleware(BaseHTTPMiddleware):
    # Public, but each is responsible for its own authorization:
    #   /api/healthz                — health probe
    #   /api/telegram/webhook       — verifies X-Telegram-Bot-Api-Secret-Token
    #   /api/whatsapp/twilio        — verifies X-Twilio-Signature
    # These webhooks cannot send a Bearer token (Telegram/Twilio originate
    # them), so the middleware must let them through and the handler verifies
    # the per-provider signature instead.
    SKIP_PATHS = {
        "/api/healthz",
        "/api/telegram/webhook",
        "/api/whatsapp/twilio",
    }

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Test-only bypass: when DISABLE_AUTH=1 is set in env we grant a
        # synthetic identity. Hardened against production misconfiguration:
        # we refuse to bypass unless ENV is unset/dev/test AND a pytest
        # session is active (PYTEST_CURRENT_TEST is exported by pytest for
        # every running test). This prevents "left DISABLE_AUTH=1 in prod
        # by accident" from disabling all API auth globally.
        if os.getenv("DISABLE_AUTH") == "1":
            env = os.getenv("ENV", "").lower()
            in_pytest = "PYTEST_CURRENT_TEST" in os.environ or "PYTEST_VERSION" in os.environ
            if env in ("", "development", "dev", "test", "testing") and in_pytest:
                request.state.user_id = "test_user"
                return await call_next(request)
            logger.error("DISABLE_AUTH=1 ignored (env=%r, pytest=%s)", env, in_pytest)

        if path.startswith("/api/admin"):
            return await call_next(request)

        if path.startswith("/api/auth"):
            return await call_next(request)

        # Logo images are public — no auth token available in <img> tags.
        # The admin CRUD sub-routes (/api/admin/logos/…) are covered by the
        # /api/admin prefix check above and enforce their own token check.
        if path.startswith("/api/logos/"):
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
            request.state.user_email = custom_payload.get("email")
            request.state.is_admin = bool(custom_payload.get("is_admin"))
            return await call_next(request)

        return JSONResponse(
            status_code=401,
            content={"error": "Invalid or expired session. Please sign in again."},
        )


# Backward-compatible export to avoid touching every import/test at once.
ClerkAuthMiddleware = AppAuthMiddleware
