"""
risk_free_service.py — FRED-backed India 10-year G-Sec yield.

Fetches the latest observation for FRED series INDIRLTLT01STM (India long-term
government bond yield, monthly %), caches it for 24 hours, and falls back to
the legacy 7.0% constant when the API is unreachable or unconfigured.

Every result includes a `source` string ("fred:INDIRLTLT01STM" or
"fallback:0.07") so callers can show users where the rate came from.
"""

from __future__ import annotations

import os
import time
import logging
from typing import Any

import httpx

logger = logging.getLogger("risk_free_service")

FRED_SERIES_ID    = "INDIRLTLT01STM"
FRED_API_URL      = "https://api.stlouisfed.org/fred/series/observations"
FALLBACK_RATE     = 0.07
CACHE_TTL_SECONDS = 24 * 3600

_cache: dict[str, Any] = {"ts": 0.0, "value": None}


async def get_india_risk_free_rate(force_refresh: bool = False) -> dict[str, Any]:
    """Return {value, asOf, source, success, observation_count}.

    Always returns a dict — never raises.  When the FRED fetch fails the
    fallback 7% is returned with `success=False`, an explicit `source`
    string and a `note` explaining the failure mode so the caller can
    surface the degradation to the user.
    """
    now = time.time()
    if (not force_refresh
            and _cache["value"] is not None
            and (now - _cache["ts"]) < CACHE_TTL_SECONDS):
        return _cache["value"]

    api_key = os.environ.get("FRED_API_KEY", "").strip()
    if not api_key:
        result = {
            "value":   FALLBACK_RATE,
            "asOf":    None,
            "source":  "fallback:0.07",
            "success": False,
            "note":    "FRED_API_KEY not configured; using 7% default",
            "series":  FRED_SERIES_ID,
        }
        _cache.update(ts=now, value=result)
        return result

    params = {
        "series_id":  FRED_SERIES_ID,
        "api_key":    api_key,
        "file_type":  "json",
        "sort_order": "desc",
        "limit":      1,
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(
                FRED_API_URL,
                params=params,
                headers={"User-Agent": "NiftyNode/1.0 (+risk-free)"},
            )
        if resp.status_code != 200:
            logger.warning("FRED %s non-200: %s", FRED_SERIES_ID, resp.status_code)
            return _fallback_with_note(now, f"FRED HTTP {resp.status_code}")
        payload = resp.json()
    except Exception as exc:
        logger.warning("FRED %s fetch failed: %s", FRED_SERIES_ID, exc)
        return _fallback_with_note(now, f"FRED fetch error: {exc}")

    obs = (payload or {}).get("observations") or []
    if not obs:
        return _fallback_with_note(now, "FRED returned no observations")

    latest = obs[0]
    val_s  = str(latest.get("value", "")).strip()
    if not val_s or val_s in (".", "NA"):
        return _fallback_with_note(now, "FRED latest observation is null")

    try:
        # FRED returns the yield as a percentage (e.g. 6.78 for 6.78%); we
        # need the decimal (0.0678) for Black-Scholes math.
        rate_decimal = float(val_s) / 100.0
    except ValueError:
        return _fallback_with_note(now, f"FRED value not numeric: {val_s}")

    result = {
        "value":   round(rate_decimal, 6),
        "asOf":    str(latest.get("date") or ""),
        "source":  f"fred:{FRED_SERIES_ID}",
        "success": True,
        "note":    "Live India 10Y G-Sec yield from FRED",
        "series":  FRED_SERIES_ID,
    }
    _cache.update(ts=now, value=result)
    return result


def _fallback_with_note(now: float, note: str) -> dict[str, Any]:
    result = {
        "value":   FALLBACK_RATE,
        "asOf":    None,
        "source":  "fallback:0.07",
        "success": False,
        "note":    note,
        "series":  FRED_SERIES_ID,
    }
    _cache.update(ts=now, value=result)
    return result
