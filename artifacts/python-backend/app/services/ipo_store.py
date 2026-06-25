"""Persistent SQLite store for IPO calendar data.

Every IPO seen from NSE or added manually is persisted here. Surviving
server restarts and NSE blocks. Key behaviours:

  • `upsert_nse(items)`   — bulk-save what the NSE scrape returned.
  • `upsert_manual(item)` — admin adds a record that NSE doesn't know about.
  • `get_active()`        — open + upcoming IPOs (close_date ≥ today-7d).
  • `get_listed()`        — IPOs whose subscription window closed >7 days ago.
  • `delete(symbol)`      — hard-delete (admin only).
  • `mark_listed(symbol)` — force-promote to listed status.

GMP is intentionally NOT stored here — it shifts hourly and ipowatch.in
already caches it for 10 min. We merge GMP at query time in IpoService.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger("ipo_store")

_DB_DIR  = os.path.join(os.path.dirname(__file__), "..", "..", "market_cache")
_DB_PATH = os.path.join(_DB_DIR, "ipo_store.db")

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS ipos (
    symbol          TEXT PRIMARY KEY,
    company_name    TEXT NOT NULL,
    series          TEXT DEFAULT 'EQ',
    is_sme          INTEGER DEFAULT 0,
    is_reit         INTEGER DEFAULT 0,
    open_date       TEXT,
    close_date      TEXT,
    listing_date    TEXT,
    price_low       REAL,
    price_high      REAL,
    lot_size        INTEGER,
    issue_size_cr   REAL,
    source          TEXT DEFAULT 'nse',
    from_gmp_only   INTEGER DEFAULT 0,
    is_listed       INTEGER DEFAULT 0,
    created_at      TEXT,
    updated_at      TEXT
);
"""

_LISTED_GRACE_DAYS = 7   # close_date + N days → auto-promote to listed


def _conn() -> sqlite3.Connection:
    os.makedirs(_DB_DIR, exist_ok=True)
    c = sqlite3.connect(_DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute(_CREATE_SQL)
    c.commit()
    return c


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _cutoff_iso() -> str:
    """ISO date before which IPOs are considered listed (grace window elapsed)."""
    return (date.today() - timedelta(days=_LISTED_GRACE_DAYS)).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["isSme"]       = bool(d.pop("is_sme", 0))
    d["isReit"]      = bool(d.pop("is_reit", 0))
    d["isListed"]    = bool(d.pop("is_listed", 0))
    d["fromGmpOnly"] = bool(d.pop("from_gmp_only", 0))
    d["companyName"] = d.pop("company_name", "")
    d["openDate"]    = d.pop("open_date", None)
    d["closeDate"]   = d.pop("close_date", None)
    d["listingDate"] = d.pop("listing_date", None)
    d["priceLow"]    = d.pop("price_low", None)
    d["priceHigh"]   = d.pop("price_high", None)
    d["lotSize"]     = d.pop("lot_size", None)
    d["issueSizeCr"] = d.pop("issue_size_cr", None)
    d["createdAt"]   = d.pop("created_at", None)
    d["updatedAt"]   = d.pop("updated_at", None)
    return d


def upsert_nse(items: list[dict]) -> int:
    """Persist a batch of normalised IpoIssue dicts from IpoService.
    Returns the number of rows inserted/updated."""
    if not items:
        return 0
    now = _now_iso()
    with _conn() as c:
        count = 0
        for it in items:
            sym = (it.get("symbol") or "").strip().upper()
            if not sym:
                continue
            c.execute(
                """INSERT INTO ipos
                    (symbol, company_name, series, is_sme, is_reit,
                     open_date, close_date, price_low, price_high,
                     lot_size, issue_size_cr, source, from_gmp_only,
                     is_listed, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,'nse',?,0,?,?)
                   ON CONFLICT(symbol) DO UPDATE SET
                     company_name  = excluded.company_name,
                     series        = excluded.series,
                     is_sme        = excluded.is_sme,
                     is_reit       = excluded.is_reit,
                     open_date     = excluded.open_date,
                     close_date    = excluded.close_date,
                     price_low     = excluded.price_low,
                     price_high    = excluded.price_high,
                     lot_size      = excluded.lot_size,
                     issue_size_cr = excluded.issue_size_cr,
                     from_gmp_only = excluded.from_gmp_only,
                     updated_at    = excluded.updated_at
                   WHERE ipos.is_listed = 0""",
                (
                    sym,
                    it.get("companyName", ""),
                    it.get("series", "EQ"),
                    1 if it.get("isSme") else 0,
                    1 if it.get("isReit") else 0,
                    it.get("openDate"),
                    it.get("closeDate"),
                    it.get("priceLow"),
                    it.get("priceHigh"),
                    it.get("lotSize"),
                    it.get("issueSizeCr"),
                    1 if it.get("fromGmpOnly") else 0,
                    now,  # created_at (only used on INSERT)
                    now,  # updated_at
                ),
            )
            count += c.rowcount
        c.commit()
    return count


def upsert_manual(item: dict) -> dict:
    """Add or update an IPO record created by an admin.
    Returns the stored record."""
    now = _now_iso()
    sym = (item.get("symbol") or "").strip().upper()
    if not sym:
        raise ValueError("symbol is required")
    with _conn() as c:
        c.execute(
            """INSERT INTO ipos
                (symbol, company_name, series, is_sme, is_reit,
                 open_date, close_date, listing_date,
                 price_low, price_high, lot_size, issue_size_cr,
                 source, from_gmp_only, is_listed, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'manual',0,0,?,?)
               ON CONFLICT(symbol) DO UPDATE SET
                 company_name  = excluded.company_name,
                 series        = excluded.series,
                 is_sme        = excluded.is_sme,
                 is_reit       = excluded.is_reit,
                 open_date     = excluded.open_date,
                 close_date    = excluded.close_date,
                 listing_date  = excluded.listing_date,
                 price_low     = excluded.price_low,
                 price_high    = excluded.price_high,
                 lot_size      = excluded.lot_size,
                 issue_size_cr = excluded.issue_size_cr,
                 source        = 'manual',
                 updated_at    = excluded.updated_at""",
            (
                sym,
                item.get("companyName", ""),
                item.get("series", "EQ"),
                1 if item.get("isSme") else 0,
                1 if item.get("isReit") else 0,
                item.get("openDate"),
                item.get("closeDate"),
                item.get("listingDate"),
                item.get("priceLow"),
                item.get("priceHigh"),
                item.get("lotSize"),
                item.get("issueSizeCr"),
                now,
                now,
            ),
        )
        c.commit()
        row = c.execute("SELECT * FROM ipos WHERE symbol=?", (sym,)).fetchone()
    return _row_to_dict(row)


def _auto_promote(c: sqlite3.Connection) -> None:
    """Mark IPOs whose grace window has elapsed as listed."""
    cutoff = _cutoff_iso()
    c.execute(
        "UPDATE ipos SET is_listed=1, updated_at=? "
        "WHERE is_listed=0 AND close_date IS NOT NULL AND close_date < ?",
        (_now_iso(), cutoff),
    )


def get_active() -> list[dict]:
    """Open + upcoming IPOs (close_date within grace window or unknown)."""
    cutoff = _cutoff_iso()
    with _conn() as c:
        _auto_promote(c)
        c.commit()
        rows = c.execute(
            "SELECT * FROM ipos WHERE is_listed=0 "
            "AND (close_date IS NULL OR close_date >= ?) "
            "ORDER BY close_date ASC NULLS LAST",
            (cutoff,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_listed(limit: int = 30) -> list[dict]:
    """Recently listed IPOs (close_date elapsed grace window)."""
    with _conn() as c:
        _auto_promote(c)
        c.commit()
        rows = c.execute(
            "SELECT * FROM ipos WHERE is_listed=1 "
            "ORDER BY close_date DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_all(limit: int = 200) -> list[dict]:
    """All records, active first, then listed — for admin view."""
    with _conn() as c:
        _auto_promote(c)
        c.commit()
        rows = c.execute(
            "SELECT * FROM ipos ORDER BY is_listed ASC, close_date DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def mark_listed(symbol: str) -> bool:
    """Force-promote one IPO to listed status. Returns True if found."""
    with _conn() as c:
        c.execute(
            "UPDATE ipos SET is_listed=1, updated_at=? WHERE symbol=?",
            (_now_iso(), symbol.upper()),
        )
        c.commit()
        return c.execute(
            "SELECT 1 FROM ipos WHERE symbol=?", (symbol.upper(),)
        ).fetchone() is not None


def delete(symbol: str) -> bool:
    """Hard-delete an IPO record. Returns True if a row was removed."""
    with _conn() as c:
        cur = c.execute("DELETE FROM ipos WHERE symbol=?", (symbol.upper(),))
        c.commit()
        return cur.rowcount > 0


def count() -> dict:
    with _conn() as c:
        _auto_promote(c)
        c.commit()
        active = c.execute("SELECT COUNT(*) FROM ipos WHERE is_listed=0").fetchone()[0]
        listed = c.execute("SELECT COUNT(*) FROM ipos WHERE is_listed=1").fetchone()[0]
    return {"active": active, "listed": listed, "total": active + listed}
