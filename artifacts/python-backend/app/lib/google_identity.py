from __future__ import annotations

import os

from google.auth.transport import requests
from google.oauth2 import id_token


def google_client_id() -> str:
    client_id = (os.environ.get("GOOGLE_CLIENT_ID") or "").strip()
    if not client_id:
        raise RuntimeError("GOOGLE_CLIENT_ID is required for Google sign-in.")
    return client_id


def admin_email_allowlist() -> set[str]:
    raw = os.environ.get("ADMIN_GOOGLE_EMAILS", "")
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def verify_google_credential(credential: str) -> dict:
    if not credential:
        raise ValueError("Missing Google credential.")
    claims = id_token.verify_oauth2_token(
        credential,
        requests.Request(),
        google_client_id(),
    )
    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise ValueError("Google account did not provide an email address.")
    if not claims.get("email_verified"):
        raise ValueError("Google account email is not verified.")
    if not claims.get("sub"):
        raise ValueError("Google account did not provide a subject identifier.")
    return claims
