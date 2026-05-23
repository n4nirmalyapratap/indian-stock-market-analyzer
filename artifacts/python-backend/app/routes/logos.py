"""Logo routes.

Public
  GET  /api/logos/{symbol}           – serve cached logo (or fetch+cache on miss)

Admin (X-Admin-Token required)
  GET  /api/admin/logos              – list all cached rows
  POST /api/admin/logos/{symbol}/refresh  – force re-fetch (body: { fetchAs? })
  DELETE /api/admin/logos/{symbol}   – evict from cache
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app.services.logo_service import delete_logo, get_logo, list_logos, refresh_logo
from app.lib.auth_tokens import verify_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["logos"])


def _is_admin(request: Request) -> bool:
    token = request.headers.get("X-Admin-Token", "")
    if not token:
        return False
    try:
        payload = verify_token(token, required_scope="admin")
        return bool(payload.get("is_admin"))
    except Exception:
        return False


# ── Public: serve logo image ──────────────────────────────────────────────────

@router.get("/logos/{symbol}")
async def serve_logo(symbol: str):
    """Return the cached PNG for `symbol`.  Fetches from Dhan CDN on first call.

    Responds with the raw image bytes and long-lived caching headers so browsers
    and Vite's dev proxy both cache it after the first fetch.
    """
    result = await asyncio.to_thread(get_logo, symbol)
    if result is None:
        return Response(status_code=204)

    image_data, content_type = result
    return Response(
        content=image_data,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=604800, immutable",
            "Vary": "Accept-Encoding",
        },
    )


# ── Admin: manage logo cache ──────────────────────────────────────────────────

@router.get("/admin/logos")
async def admin_list_logos(request: Request, limit: int = 200, offset: int = 0):
    if not _is_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin auth required."})
    result = await asyncio.to_thread(list_logos, limit, offset)
    return result


@router.post("/admin/logos/{symbol}/refresh")
async def admin_refresh_logo(symbol: str, request: Request):
    if not _is_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin auth required."})
    body: dict = {}
    try:
        body = await request.json()
    except Exception:
        pass
    fetch_as: Optional[str] = body.get("fetchAs") or None

    # Resolve admin identity for audit trail
    token = request.headers.get("X-Admin-Token", "")
    admin_email = "admin"
    try:
        payload = verify_token(token, required_scope="admin")
        admin_email = payload.get("email") or payload.get("sub") or "admin"
    except Exception:
        pass

    result = await asyncio.to_thread(
        refresh_logo, symbol, fetch_as=fetch_as, updated_by=admin_email
    )
    return result


@router.delete("/admin/logos/{symbol}")
async def admin_delete_logo(symbol: str, request: Request):
    if not _is_admin(request):
        return JSONResponse(status_code=401, content={"error": "Admin auth required."})
    deleted = await asyncio.to_thread(delete_logo, symbol)
    return {"deleted": deleted, "symbol": symbol.upper()}
