"""Lightweight in-memory log of stocks that have been looked up but have
no sub-sector classification in _EXTRA_SUBSECTOR_MAP.

Design goals:
  • Zero DB writes — the log lives in process memory only.
  • Thread-safe — uses a simple lock around a dict.
  • Ephemeral — survives until the server restarts; that is fine because the
    admin reviews it periodically, not in real-time.
  • Admin can dismiss an entry (removes it from the queue without classifying).
  • When admin saves an override via POST /admin/subsectors/overrides the
    caller should call `dismiss(symbol)` so the entry disappears from the queue.

Typical flow:
  1. User visits SOMESYM stock page.
  2. stock_profile_service calls get_sub_sector("SOMESYM") → None.
  3. stock_profile_service calls unclassified_log.record("SOMESYM", sector, industry).
  4. Admin visits Sub-Industry Manager → "Needs Classification" tab.
  5. Admin clicks Classify → opens override modal pre-filled with SOMESYM.
  6. Admin saves → backend calls unclassified_log.dismiss("SOMESYM").
"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()

# symbol → {"symbol", "sector", "industry", "first_seen_ms", "hit_count"}
_queue: dict[str, dict] = {}

# Symbols the admin explicitly dismissed without classifying (skip re-adding).
_dismissed: set[str] = set()


def record(symbol: str, sector: str | None, industry: str | None) -> None:
    """Log a stock as needing sub-sector classification.
    Idempotent — repeat calls just increment the hit counter.
    Dismissed symbols are silently ignored.
    """
    sym = (symbol or "").upper().strip()
    if not sym or sym in _dismissed:
        return
    with _lock:
        if sym in _queue:
            _queue[sym]["hit_count"] += 1
            _queue[sym]["last_seen_ms"] = int(time.time() * 1000)
        else:
            _queue[sym] = {
                "symbol":       sym,
                "sector":       sector or None,
                "industry":     industry or None,
                "first_seen_ms": int(time.time() * 1000),
                "last_seen_ms": int(time.time() * 1000),
                "hit_count":    1,
            }


def dismiss(symbol: str) -> None:
    """Remove a symbol from the queue (called after admin classifies or dismisses it)."""
    sym = (symbol or "").upper().strip()
    if not sym:
        return
    with _lock:
        _queue.pop(sym, None)
        _dismissed.add(sym)


def get_all() -> list[dict]:
    """Return a snapshot of the unclassified queue sorted by hit count desc."""
    with _lock:
        return sorted(_queue.values(), key=lambda r: (-r["hit_count"], r["symbol"]))


def size() -> int:
    with _lock:
        return len(_queue)
