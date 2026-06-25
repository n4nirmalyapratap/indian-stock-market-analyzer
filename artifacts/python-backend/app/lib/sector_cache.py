"""
sector_cache.py
Lightweight SQLite-backed cache of symbol → sector / industry learned from
Yahoo Finance at runtime.  Written to by stock_profile_service whenever it
fetches a fresh Yahoo profile; read by the bhavcopy delivery endpoint as a
last-resort fallback to fill in sectors for stocks not in the static map.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from threading import Lock

logger = logging.getLogger("sector_cache")

_DB = Path(__file__).resolve().parent.parent.parent / "market_cache" / "sector_cache.db"
_lock = Lock()
_mem: dict[str, str] = {}   # symbol → sector (fast in-memory read path)


def _init() -> None:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sector_cache (
                symbol     TEXT PRIMARY KEY,
                sector     TEXT NOT NULL,
                industry   TEXT,
                updated_ms INTEGER NOT NULL
            )
        """)
        conn.commit()
        for row in conn.execute("SELECT symbol, sector FROM sector_cache"):
            _mem[row[0]] = row[1]
    logger.info("sector_cache: pre-loaded %d entries from disk", len(_mem))


def write(symbol: str, sector: str, industry: str | None = None) -> None:
    """Persist a symbol→sector mapping learned from Yahoo Finance.
    No-op when sector is empty or unchanged."""
    if not symbol or not sector:
        return
    sym = symbol.upper().strip()
    if _mem.get(sym) == sector:
        return
    with _lock:
        _mem[sym] = sector
        with sqlite3.connect(_DB) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sector_cache
                    (symbol, sector, industry, updated_ms)
                VALUES (?, ?, ?, ?)
                """,
                (sym, sector, industry, int(time.time() * 1000)),
            )
            conn.commit()


def get_all() -> dict[str, str]:
    """Return a live snapshot of all cached symbol→sector entries."""
    return dict(_mem)


def size() -> int:
    return len(_mem)


_init()
