"""
Market Data Disk Cache
======================
NSE market hours: 9:15 AM – 3:30 PM IST (Mon-Fri)

When the market is CLOSED:
  - All historical data reads are served from disk (JSON files, keyed by date).
  - Any live fetch that succeeds also saves to disk automatically.
  - Scanner runs hit the disk instead of Yahoo Finance → near-instant.

When the market is OPEN:
  - Normal in-memory cache + live Yahoo Finance fetches apply.
  - Disk cache is NOT consulted (data may be stale from yesterday).

Cache location:  artifacts/python-backend/market_cache/<date>/<SYMBOL>_<days>.json
Warmup endpoint: POST /api/cache/warmup   (auto-triggered at startup if cache missing)
Status endpoint: GET  /api/cache/status
"""

import json
import os
import asyncio
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Any

_CACHE_ROOT = Path(__file__).parent.parent.parent / "market_cache"

IST_OFFSET_HOURS = 5.5  # UTC+5:30


def _now_ist() -> datetime:
    utc_now = datetime.utcnow()
    return utc_now + timedelta(hours=IST_OFFSET_HOURS)


def is_market_open() -> bool:
    now = _now_ist()
    if now.weekday() >= 5:
        return False
    market_open  = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close


def last_trading_date() -> str:
    """Return the most recent trading day's date (YYYY-MM-DD in IST)."""
    d = _now_ist().date()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def _cache_path(symbol: str, days: int) -> Path:
    date_dir = _CACHE_ROOT / last_trading_date()
    date_dir.mkdir(parents=True, exist_ok=True)
    return date_dir / f"{symbol}_{days}.json"


def load_from_disk(symbol: str, days: int) -> Optional[list]:
    try:
        p = _cache_path(symbol, days)
        if p.exists():
            with open(p, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def save_to_disk(symbol: str, days: int, data: Any) -> None:
    try:
        p = _cache_path(symbol, days)
        with open(p, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def cache_status() -> dict:
    date_str = last_trading_date()
    date_dir = _CACHE_ROOT / date_str
    cached_count = len(list(date_dir.glob("*.json"))) if date_dir.exists() else 0
    return {
        "marketOpen": is_market_open(),
        "cacheDate": date_str,
        "cachedSymbols": cached_count,
        "cacheRoot": str(_CACHE_ROOT),
        "servingFromCache": not is_market_open() and cached_count > 0,
    }


async def warmup_cache(price_service, batch_size: int = 10) -> dict:
    """
    Pre-fetch and cache historical data for ALL universe symbols.
    Uses PriceService so each symbol tries NSE first, then Yahoo fallback.
    Runs in parallel batches of `batch_size` to avoid overwhelming APIs.
    Returns a summary dict.
    """
    from ..lib.universe import build_universe

    all_symbols = list(set(build_universe(["NIFTY100", "MIDCAP", "SMALLCAP"])))
    total = len(all_symbols)
    saved = 0
    errors = 0

    async def fetch_one(sym: str):
        nonlocal saved, errors
        for days in [90, 300]:
            existing = load_from_disk(sym, days)
            if existing:
                continue
            try:
                # PriceService: NSE primary → Yahoo fallback
                data = await price_service.get_historical_data(sym, days)
                if data:
                    saved += 1
                    # save_to_disk already called inside PriceService on success
            except Exception:
                errors += 1
            await asyncio.sleep(0.15)

    for i in range(0, total, batch_size):
        batch = all_symbols[i : i + batch_size]
        await asyncio.gather(*[fetch_one(s) for s in batch])

    return {
        "totalSymbols": total,
        "filesSaved": saved,
        "errors": errors,
        "cacheDate": last_trading_date(),
    }
