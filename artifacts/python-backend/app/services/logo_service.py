"""Logo cache service.

Fetches stock logos from Dhan's public CDN once and stores the raw PNG
binary in PostgreSQL so no subsequent request ever hits an external CDN.

Table: stock_logos
  symbol       – normalised NSE ticker (PRIMARY KEY)
  fetch_symbol – the key sent to Dhan (can differ from symbol if an admin
                 has set an override, e.g. LTIM → LTIMindtree)
  image_data   – raw bytes of the PNG (NULL when Dhan had no logo)
  content_type – 'image/png' (or 'image/svg+xml' for future use)
  fetch_ok     – FALSE when Dhan returned 4xx/5xx so we don't re-hammer it
  updated_by   – email/name of admin who last forced a refresh
  fetched_at_ms / updated_at_ms – epoch millis
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from app.lib.auth_store import ensure_primary_schema, get_conn, now_ms

logger = logging.getLogger(__name__)

DHAN_CDN = "https://images.dhan.co/symbol/{symbol}.png"
_FETCH_TIMEOUT = 8.0


def _normalise(sym: str) -> str:
    """Strip exchange suffixes so RELIANCE.NS and RELIANCE map to the same row."""
    s = (sym or "").strip().upper()
    for suffix in (".NS", ".BO", "-EQ", ":NSE", ":BSE"):
        if s.endswith(suffix):
            return s[: -len(suffix)]
    return s


def _fetch_from_dhan(fetch_symbol: str) -> tuple[Optional[bytes], str, bool]:
    """Synchronously download one logo from Dhan CDN.

    Returns (image_bytes, content_type, ok).
    `ok` is False when the CDN returned a non-2xx — we store the miss so
    we don't keep re-fetching on every request.
    """
    url = DHAN_CDN.format(symbol=fetch_symbol)
    try:
        resp = httpx.get(url, timeout=_FETCH_TIMEOUT, follow_redirects=True)
        if resp.status_code == 200:
            ct = resp.headers.get("content-type", "image/png").split(";")[0].strip()
            return resp.content, ct, True
        logger.debug("Dhan CDN %s for %s → %s", url, fetch_symbol, resp.status_code)
        return None, "image/png", False
    except Exception as exc:
        logger.warning("Dhan CDN fetch failed for %s: %s", fetch_symbol, exc)
        return None, "image/png", False


def get_logo(symbol: str) -> Optional[tuple[bytes, str]]:
    """Return (image_bytes, content_type) from cache, fetching on first call.

    Returns None when:
    - Dhan has no logo for this symbol (fetch_ok=False row exists), OR
    - The network call failed
    """
    ensure_primary_schema()
    sym = _normalise(symbol)
    if not sym:
        return None

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT image_data, content_type, fetch_ok, fetch_symbol "
                "FROM stock_logos WHERE symbol = %s",
                (sym,),
            )
            row = cur.fetchone()

    if row is not None:
        if not row["fetch_ok"]:
            return None
        data = row["image_data"]
        if data is None:
            return None
        return bytes(data), row["content_type"]

    # Cache miss — fetch now and store
    fetch_sym = sym
    img, ct, ok = _fetch_from_dhan(fetch_sym)
    _upsert_logo(sym, fetch_sym, img, ct, ok, updated_by="auto")
    if ok and img:
        return img, ct
    return None


def refresh_logo(
    symbol: str,
    *,
    fetch_as: Optional[str] = None,
    updated_by: str = "admin",
) -> dict:
    """Force a re-fetch from Dhan CDN, optionally using a different symbol key.

    Returns a summary dict for the admin UI:
    { symbol, fetch_symbol, ok, bytes_size, content_type }
    """
    ensure_primary_schema()
    sym = _normalise(symbol)
    fetch_sym = _normalise(fetch_as) if fetch_as else sym
    img, ct, ok = _fetch_from_dhan(fetch_sym)
    _upsert_logo(sym, fetch_sym, img, ct, ok, updated_by=updated_by)
    return {
        "symbol": sym,
        "fetch_symbol": fetch_sym,
        "ok": ok,
        "bytes_size": len(img) if img else 0,
        "content_type": ct,
    }


def list_logos(limit: int = 500, offset: int = 0) -> list[dict]:
    """Return cached logo rows ordered by symbol — for the admin table."""
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT symbol, fetch_symbol, content_type, bytes_size,
                       fetch_ok, updated_by, fetched_at_ms, updated_at_ms
                  FROM stock_logos
                 ORDER BY symbol
                 LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            rows = cur.fetchall()
            cur.execute("SELECT COUNT(*) AS n FROM stock_logos")
            total = (cur.fetchone() or {}).get("n", 0)
    return {"logos": [dict(r) for r in rows], "total": total}


def delete_logo(symbol: str) -> bool:
    """Remove a cached logo so it will be re-fetched on the next request."""
    ensure_primary_schema()
    sym = _normalise(symbol)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM stock_logos WHERE symbol = %s RETURNING symbol", (sym,))
            deleted = cur.fetchone() is not None
    return deleted


def _upsert_logo(
    symbol: str,
    fetch_symbol: str,
    image_data: Optional[bytes],
    content_type: str,
    fetch_ok: bool,
    updated_by: str,
) -> None:
    now = now_ms()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO stock_logos
                    (symbol, fetch_symbol, image_data, content_type,
                     bytes_size, fetch_ok, updated_by, fetched_at_ms, updated_at_ms)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol) DO UPDATE SET
                    fetch_symbol  = EXCLUDED.fetch_symbol,
                    image_data    = EXCLUDED.image_data,
                    content_type  = EXCLUDED.content_type,
                    bytes_size    = EXCLUDED.bytes_size,
                    fetch_ok      = EXCLUDED.fetch_ok,
                    updated_by    = EXCLUDED.updated_by,
                    updated_at_ms = EXCLUDED.updated_at_ms
                """,
                (
                    symbol,
                    fetch_symbol,
                    image_data,
                    content_type,
                    len(image_data) if image_data else None,
                    fetch_ok,
                    updated_by,
                    now,
                    now,
                ),
            )
