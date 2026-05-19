"""
Google-only auth routes.

Public endpoints:
  POST /api/auth/google    { credential }  -> { token, user }

Legacy email/password routes are intentionally disabled.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.lib.auth_store import upsert_google_user
from app.lib.auth_tokens import create_token, verify_token
from app.lib.google_identity import admin_email_allowlist, verify_google_credential

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleLoginRequest(BaseModel):
    credential: str


def verify_custom_token(token: str) -> dict:
    """
    Backward-compatible export used by auth middleware.
    """
    return verify_token(token)


@router.post("/google")
async def google_login(req: GoogleLoginRequest):
    try:
        claims = verify_google_credential(req.credential)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Google sign-in verification failed.") from exc

    email = (claims.get("email") or "").strip().lower()
    user = upsert_google_user(
        email=email,
        name=(claims.get("name") or "").strip(),
        google_sub=str(claims.get("sub") or ""),
        picture_url=(claims.get("picture") or "").strip(),
        is_admin=email in admin_email_allowlist(),
    )
    token = create_token(user, scope="user")
    logger.info("Google user logged in: %s", email)
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "pictureUrl": user.get("picture_url", ""),
            "isAdmin": bool(user.get("is_admin")),
        },
    }


@router.post("/login")
async def disabled_password_login():
    raise HTTPException(status_code=410, detail="Password login is disabled. Use Google sign-in.")


@router.post("/register")
async def disabled_registration():
    raise HTTPException(status_code=410, detail="Registration is disabled. Use Google sign-in.")
