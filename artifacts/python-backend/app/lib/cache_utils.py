"""
cache_utils.py
==============
Shared in-memory TTL cache used by lightweight services (BSE, Twelve Data,
etc.) that don't need the full flush-on-market-state logic of YahooService /
NseService.

Usage
-----
    from app.lib.cache_utils import MarketTTLCache

    _cache = MarketTTLCache(open_ttl=90, closed_ttl=1800)

    data = _cache.get("quote:RELIANCE")
    if data is None:
        data = await fetch_something()
        _cache.set("quote:RELIANCE", data)

Market-hours awareness is optional — if you pass `open_ttl` only, the same
TTL is used regardless of market state.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional


def _is_market_open() -> bool:
    """Lightweight 9:15–15:30 IST weekday check."""
    ist = datetime.now(tz=timezone(timedelta(hours=5, minutes=30)))
    if ist.weekday() >= 5:
        return False
    minutes = ist.hour * 60 + ist.minute
    return (9 * 60 + 15) <= minutes <= (15 * 60 + 30)


class MarketTTLCache:
    """Simple TTL-based in-memory cache.

    Thread-safety: safe for single-threaded asyncio use (no asyncio.Lock
    needed because Python's GIL protects dict mutations and we never await
    inside a mutation).
    """

    def __init__(
        self,
        open_ttl: int = 90,
        closed_ttl: Optional[int] = None,
        max_entries: int = 512,
    ) -> None:
        self._open_ttl    = open_ttl
        self._closed_ttl  = closed_ttl if closed_ttl is not None else open_ttl
        self._max_entries = max_entries
        self._store: dict[str, tuple[float, Any]] = {}

    def _ttl(self) -> int:
        return self._open_ttl if _is_market_open() else self._closed_ttl

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, data = entry
        if time.time() < expires_at:
            return data
        del self._store[key]
        return None

    def set(self, key: str, data: Any, ttl: Optional[int] = None) -> None:
        if ttl is None:
            ttl = self._ttl()
        if len(self._store) >= self._max_entries:
            now = time.time()
            expired = [k for k, (exp, _) in self._store.items() if now >= exp]
            for k in expired:
                del self._store[k]
            if len(self._store) >= self._max_entries:
                oldest = next(iter(self._store))
                del self._store[oldest]
        self._store[key] = (time.time() + ttl, data)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)
