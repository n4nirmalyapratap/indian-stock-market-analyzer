"""
risk_free_service.py — FRED-backed India 10-year G-Sec yield.

Refreshes from FRED series ``INDIRLTLT01STM`` and persists the latest
observation to disk (``market_cache/risk_free_rate.json``) so we always have
a last-known value even when the FRED API is unreachable on cold start.

Resolution order on every call:
  1. In-memory cache (TTL 24h) → return immediately.
  2. Live FRED fetch → on success, update memory + disk caches.
  3. Disk cache (last good FRED value) → returned with ``stale=True``.
  4. Hard fallback constant 0.07 → only when steps 1-3 are all unavailable
     (truly first-ever run with no network).

Every result is a dict with ``value``, ``asOf``, ``source``, ``success`` and
``note`` so the caller can show provenance — there is no silent fallback.
"""

from __future__ import annotations

import json
import os
import time
import logging
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("risk_free_service")

FRED_SERIES_ID    = "INDIRLTLT01STM"
FRED_API_URL      = "https://api.stlouisfed.org/fred/series/observations"
HARD_FALLBACK     = 0.07
CACHE_TTL_SECONDS = 24 * 3600

_CACHE_DIR  = Path(__file__).resolve().parents[2] / "market_cache"
_CACHE_FILE = _CACHE_DIR / "risk_free_rate.json"

_mem: dict[str, Any] = {"ts": 0.0, "value": None}


def _load_disk() -> dict[str, Any] | None:
    try:
        if _CACHE_FILE.exists():
            return json.loads(_CACHE_FILE.read_text())
    except Exception as exc:
        logger.warning("risk_free disk cache read failed: %s", exc)
    return None


def _save_disk(payload: dict[str, Any]) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(payload, indent=2))
    except Exception as exc:
        logger.warning("risk_free disk cache write failed: %s", exc)


def _stale_from_disk(note: str) -> dict[str, Any] | None:
    disk = _load_disk()
    if not disk or disk.get("value") is None:
        return None
    return {
        "value":   disk["value"],
        "asOf":    disk.get("asOf"),
        "source":  f"disk_cache:{disk.get('source','fred:'+FRED_SERIES_ID)}",
        "success": False,
        "stale":   True,
        "note":    f"{note}; using last-known FRED value cached on "
                   f"{disk.get('cached_at','?')}",
        "series":  FRED_SERIES_ID,
    }


def _hard_fallback(note: str) -> dict[str, Any]:
    return {
        "value":   HARD_FALLBACK,
        "asOf":    None,
        "source":  "hardcoded:0.07",
        "success": False,
        "stale":   True,
        "note":    f"{note}; no FRED disk cache found — using 7% boot constant",
        "series":  FRED_SERIES_ID,
    }


async def get_india_risk_free_rate(force_refresh: bool = False) -> dict[str, Any]:
    """Return {value, asOf, source, success, note, series, stale?}.

    Always returns a dict; never raises.  See module docstring for the
    resolution order.
    """
    now = time.time()
    if (not force_refresh
            and _mem["value"] is not None
            and (now - _mem["ts"]) < CACHE_TTL_SECONDS):
        return _mem["value"]

    api_key = os.environ.get("FRED_API_KEY", "").strip()
    if not api_key:
        result = (_stale_from_disk("FRED_API_KEY not configured")
                  or _hard_fallback("FRED_API_KEY not configured"))
        _mem.update(ts=now, value=result)
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
            return _stale_or_fallback(now, f"FRED HTTP {resp.status_code}")
        payload = resp.json()
    except Exception as exc:
        logger.warning("FRED %s fetch failed: %s", FRED_SERIES_ID, exc)
        return _stale_or_fallback(now, f"FRED fetch error: {exc}")

    obs = (payload or {}).get("observations") or []
    if not obs:
        return _stale_or_fallback(now, "FRED returned no observations")

    latest = obs[0]
    val_s  = str(latest.get("value", "")).strip()
    if not val_s or val_s in (".", "NA"):
        return _stale_or_fallback(now, "FRED latest observation is null")

    try:
        rate_decimal = float(val_s) / 100.0
    except ValueError:
        return _stale_or_fallback(now, f"FRED value not numeric: {val_s}")

    result = {
        "value":   round(rate_decimal, 6),
        "asOf":    str(latest.get("date") or ""),
        "source":  f"fred:{FRED_SERIES_ID}",
        "success": True,
        "stale":   False,
        "note":    "Live India 10Y G-Sec yield from FRED",
        "series":  FRED_SERIES_ID,
    }
    _mem.update(ts=now, value=result)
    _save_disk({**result,
                "cached_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))})
    return result


def _stale_or_fallback(now: float, note: str) -> dict[str, Any]:
    result = _stale_from_disk(note) or _hard_fallback(note)
    _mem.update(ts=now, value=result)
    return result


def get_cached_rate_sync() -> float:
    """Synchronous accessor — returns the in-memory value if present, else
    the last-known disk value, else the hard fallback.  Safe to use as a
    default for non-async callers (e.g. pricing helpers).

    Logs *loudly* (WARNING) when the disk cache is missing and the boot
    constant 0.07 is used, so the operator sees provenance — there is no
    silent fallback.
    """
    if _mem["value"] is not None:
        return float(_mem["value"]["value"])
    disk = _load_disk()
    if disk and disk.get("value") is not None:
        logger.info(
            "risk_free_service: using disk-cached India 10Y G-Sec yield %.4f%% "
            "(asOf=%s, cached_at=%s)",
            float(disk["value"]) * 100,
            disk.get("asOf"), disk.get("cached_at"),
        )
        return float(disk["value"])
    logger.warning(
        "risk_free_service: NO disk cache and no live FRED fetch yet — "
        "falling back to HARD constant %.2f%%.  Pricing/backtest defaults "
        "will use 7%% until refresh_risk_free_rate_on_startup() runs.",
        HARD_FALLBACK * 100,
    )
    return HARD_FALLBACK


async def refresh_risk_free_rate_on_startup() -> dict[str, Any]:
    """Force a live FRED refresh on application startup so the 24h memory
    cache is warm before the first user request.  Falls back gracefully
    via the standard resolution chain (disk → hard fallback) and logs the
    result so operators can verify the daily refresh ran."""
    try:
        result = await get_india_risk_free_rate(force_refresh=True)
        if result.get("success"):
            logger.info(
                "risk_free_service: startup refresh OK — India 10Y G-Sec %.4f%% "
                "(asOf=%s, source=%s)",
                float(result["value"]) * 100,
                result.get("asOf"), result.get("source"),
            )
        else:
            logger.warning(
                "risk_free_service: startup refresh did NOT get a fresh FRED "
                "value (%.4f%% from %s, note=%s)",
                float(result["value"]) * 100,
                result.get("source"), result.get("note"),
            )
        return result
    except Exception as exc:
        logger.error("risk_free_service: startup refresh raised: %s", exc)
        return _hard_fallback(f"startup refresh raised: {exc}")
