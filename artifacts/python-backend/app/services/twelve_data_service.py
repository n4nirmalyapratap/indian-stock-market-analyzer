"""Twelve Data — free tier 800 req/day, supports NSE + BSE.

When this fires
---------------
Slots into the PriceService chain AFTER Yahoo. If the admin hasn't set
a `TWELVE_DATA_API_KEY` in the secrets store, every call returns None
quickly so the chain falls through to the next tier. No setup required
to deploy the code; activation is one secret-set away.

Why a third tier
----------------
Yahoo and NSE share a lot of failure correlation — Akamai bot challenges,
Cloudflare blocks, cookie expiry. Twelve Data runs on independent infra
(US-based), uses a real-time WebSocket-grade source on its backend, and
covers NSE/BSE Indian stocks explicitly via `exchange=NSE/BSE`.

Free tier limits
----------------
  * 800 req/day, 8/min — generous for EOD-analysis use even with 4
    cap segments × 100 stocks × 1 refresh/day = 400 req/day.
  * Each historical-bars call counts as 1 request regardless of how
    many bars are returned, so a 90-day window is the same cost as a
    1-day window.

We cache aggressively (4 hours for historical, 90 seconds for quote
during market hours) so a heavy user can't blow the daily quota.

Symbol mapping
--------------
We pass our raw symbol and `exchange=NSE` to Twelve Data. They accept
this format for ~95% of NSE-listed stocks. For the few that don't
resolve, the call returns 404 / status: error which we treat as a
miss and let the chain fall through.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger("twelve_data")

_BASE = "https://api.twelvedata.com"

# Cache TTLs. Quote during market is short (live data); historical is
# long because EOD candles don't change intraday.
_QUOTE_TTL_OPEN   = 90     # seconds during NSE trading hours
_QUOTE_TTL_CLOSED = 30 * 60
_HISTORICAL_TTL   = 4 * 3600

_cache: dict[str, tuple[float, dict]] = {}


def _api_key() -> Optional[str]:
    """Read TWELVE_DATA_API_KEY from the DB-managed secrets store.

    Returns None when the secret is unset or empty — every Twelve Data
    call short-circuits to None in that case, so deploying the code
    without a key is harmless (just doesn't help).
    """
    try:
        from app.lib.secrets_store import get_secret  # noqa: PLC0415
        key = (get_secret("TWELVE_DATA_API_KEY", "") or "").strip()
        return key or None
    except Exception:
        return None


def _is_market_open_ist() -> bool:
    """Lightweight 9:15–15:30 IST weekday check — avoids the full disk
    cache import path on every call."""
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415
    ist = datetime.now(tz=timezone(timedelta(hours=5, minutes=30)))
    if ist.weekday() >= 5:
        return False
    minutes = ist.hour * 60 + ist.minute
    return (9 * 60 + 15) <= minutes <= (15 * 60 + 30)


async def _get(path: str, params: dict) -> Optional[dict]:
    """Wrap the HTTP call so every public function has uniform error
    handling. Never raises."""
    key = _api_key()
    if not key:
        return None
    params = {**params, "apikey": key}
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(f"{_BASE}{path}", params=params)
            if resp.status_code != 200:
                logger.debug("Twelve Data non-200 %s on %s: %s",
                             resp.status_code, path, resp.text[:120])
                return None
            data = resp.json()
            # Their error responses come back as 200 with a `status` field.
            if isinstance(data, dict) and data.get("status") == "error":
                logger.debug("Twelve Data error for %s: %s",
                             params.get("symbol"), str(data.get("message"))[:120])
                return None
            return data
    except Exception as exc:
        logger.debug("Twelve Data fetch failed for %s: %s",
                     params.get("symbol"), str(exc)[:80])
        return None


async def get_quote(symbol: str) -> Optional[dict]:
    """Return a quote dict matching the chain's standard shape, or None.

    Caching: 90s during market hours, 30min when closed. Per-symbol so
    we don't double-spend the daily quota fetching the same ticker.
    """
    sym = (symbol or "").strip().upper()
    if not sym or not _api_key():
        return None

    ttl = _QUOTE_TTL_OPEN if _is_market_open_ist() else _QUOTE_TTL_CLOSED
    cache_key = f"quote:{sym}"
    cached = _cache.get(cache_key)
    if cached and (time.time() - cached[0]) < ttl:
        return cached[1]

    data = await _get("/quote", {"symbol": sym, "exchange": "NSE"})
    if not isinstance(data, dict) or not data.get("close"):
        return None

    try:
        last  = float(data.get("close")  or 0)
        prev  = float(data.get("previous_close") or 0)
        change  = float(data.get("change")  or (last - prev))
        pchange = float(data.get("percent_change") or 0)
        quote = {
            "symbol":         sym,
            "companyName":    data.get("name") or sym,
            "lastPrice":      last,
            "change":         change,
            "pChange":        pchange,
            "open":           float(data.get("open")  or 0) or None,
            "dayHigh":        float(data.get("high")  or 0) or None,
            "dayLow":         float(data.get("low")   or 0) or None,
            "previousClose":  prev or None,
            "volume":         int(float(data.get("volume") or 0)) or None,
            "fiftyTwoWeekHigh": float(data.get("fifty_two_week", {}).get("high") or 0) if isinstance(data.get("fifty_two_week"), dict) else None,
            "fiftyTwoWeekLow":  float(data.get("fifty_two_week", {}).get("low")  or 0) if isinstance(data.get("fifty_two_week"), dict) else None,
            "source":         "TWELVE_DATA",
        }
    except (TypeError, ValueError) as exc:
        logger.debug("Twelve Data parse failed for %s: %s", sym, exc)
        return None

    _cache[cache_key] = (time.time(), quote)
    return quote


async def get_historical(symbol: str, days: int = 90) -> list[dict]:
    """Daily OHLCV bars (oldest → newest) — same shape as Yahoo / Stooq.
    Empty list when no key is configured or the call fails.
    """
    sym = (symbol or "").strip().upper()
    if not sym or not _api_key():
        return []

    cache_key = f"history:{sym}:{days}"
    cached = _cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _HISTORICAL_TTL:
        return cached[1]

    # Twelve Data's `time_series` returns newest → oldest by default.
    data = await _get("/time_series", {
        "symbol":     sym,
        "exchange":   "NSE",
        "interval":   "1day",
        "outputsize": str(min(max(days, 1), 5000)),  # API caps at 5000
        "order":      "asc",                          # oldest first
        "timezone":   "Asia/Kolkata",
    })
    if not isinstance(data, dict):
        return []
    values = data.get("values")
    if not isinstance(values, list) or not values:
        return []

    out: list[dict] = []
    for v in values:
        if not isinstance(v, dict):
            continue
        try:
            out.append({
                "date":   v.get("datetime", "")[:10],
                "open":   float(v.get("open")  or 0),
                "high":   float(v.get("high")  or 0),
                "low":    float(v.get("low")   or 0),
                "close":  float(v.get("close") or 0),
                "volume": int(float(v.get("volume") or 0)),
            })
        except (TypeError, ValueError):
            continue

    if not out:
        return []
    _cache[cache_key] = (time.time(), out)
    return out
