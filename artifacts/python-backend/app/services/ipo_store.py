"""Persistent SQLite store for IPO calendar data.

This is the **system of record** the /insights/ipos endpoint serves from —
requests never wait on NSE or scrapers. A background refresher (see
IpoService.refresh + main._ipo_refresh_scheduler) writes here; reads are
local-disk SQLite and return in milliseconds.

Key behaviours:

  • `upsert_nse(items)`      — bulk-save what the refresher scraped.
  • `upsert_manual(item)`    — admin adds a record the feeds don't know about.
  • `set_subscriptions(map)` — persist live QIB/NII/Retail multiples per symbol.
  • `set_gmps(map)`          — persist last-known GMP per symbol (never blanked
                               by a failed scrape — stale GMP beats no GMP).
  • `get_active()`           — open + upcoming IPOs (close_date ≥ today-7d).
  • `get_listed()`           — IPOs whose subscription window closed >7 days ago.
  • `delete(symbol)`         — hard-delete (admin only).
  • `mark_listed(symbol)`    — force-promote to listed status.

The DB lives on LOCAL disk via app.lib.db_paths.local_db_path — NEVER under
market_cache/, which in production is an SMB mount where WAL-mode SQLite
fails with "database is locked". (The store used to live there, which is
why the NSE-block fallback never worked in prod.) On first run we migrate
any rows we can still read out of the legacy file so admin-entered IPOs
survive the move.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from datetime import date, timedelta
from typing import Optional

from ..lib.db_paths import local_db_path

logger = logging.getLogger("ipo_store")

_DB_PATH = str(local_db_path("ipo_store.db"))

# Legacy location (pre-2026-07): the SMB-mounted cache dir. Read-only source
# for the one-time migration below; we never write here again.
_LEGACY_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "market_cache")
_LEGACY_DB  = os.path.join(_LEGACY_DIR, "ipo_store.db")  # sqlite-on-mount-ok: read-only legacy migration source

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

# Columns added after the first release — applied via ALTER TABLE so existing
# DBs upgrade in place. subscription/gmp are JSON blobs in the exact shape the
# frontend consumes.
_EXTRA_COLS: dict[str, str] = {
    "issue_shares":   "INTEGER",
    "raw_status":     "TEXT",
    "subscription":   "TEXT",   # JSON {"qib":..,"nii":..,"retail":..,"total":..}
    "sub_updated_at": "TEXT",
    "gmp":            "TEXT",   # JSON {"premium":..,"estListing":..,...}
    "gmp_updated_at": "TEXT",
    "last_seen_at":   "TEXT",   # last time a live feed returned this row
}

_LISTED_GRACE_DAYS = 7   # close_date + N days → auto-promote to listed

_schema_ready = False
# Serialises the one-time schema init/migration. Without it, two threads
# opening the store for the first time (WAL allows concurrent connections)
# can both see a missing column and race into the same ALTER TABLE, which
# fails the loser with "duplicate column name".
_schema_lock = threading.Lock()


def _ensure_schema(c: sqlite3.Connection) -> None:
    c.execute(_CREATE_SQL)
    have = {row[1] for row in c.execute("PRAGMA table_info(ipos)").fetchall()}
    for col, typ in _EXTRA_COLS.items():
        if col not in have:
            try:
                c.execute(f"ALTER TABLE ipos ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError as e:
                # Belt-and-suspenders behind _schema_lock: tolerate a
                # duplicate-column add if another path already applied it.
                if "duplicate column" not in str(e).lower():
                    raise


def _migrate_legacy(c: sqlite3.Connection) -> None:
    """One-time best-effort copy from the old market_cache/ DB. Reads may
    fail on the SMB mount (that's the bug that forced the move) — any error
    just skips the migration; live feeds repopulate within minutes."""
    try:
        if c.execute("SELECT COUNT(*) FROM ipos").fetchone()[0] > 0:
            return
        if not os.path.exists(_LEGACY_DB):
            return
        src = sqlite3.connect(f"file:{_LEGACY_DB}?mode=ro", uri=True)
        try:
            src.row_factory = sqlite3.Row
            rows = src.execute("SELECT * FROM ipos").fetchall()
        finally:
            src.close()
        have = {r[1] for r in c.execute("PRAGMA table_info(ipos)").fetchall()}
        n = 0
        for row in rows:
            d = {k: row[k] for k in row.keys() if k in have}
            if not d.get("symbol"):
                continue
            cols = ",".join(d.keys())
            ph   = ",".join("?" * len(d))
            c.execute(f"INSERT OR IGNORE INTO ipos ({cols}) VALUES ({ph})",
                      tuple(d.values()))
            n += 1
        if n:
            logger.info("ipo_store: migrated %d rows from legacy market_cache DB", n)
    except Exception as e:
        logger.warning("ipo_store: legacy migration skipped: %s", e)


def _conn() -> sqlite3.Connection:
    global _schema_ready
    c = sqlite3.connect(_DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    if not _schema_ready:
        with _schema_lock:
            if not _schema_ready:   # re-check under the lock
                _ensure_schema(c)
                _migrate_legacy(c)
                c.commit()
                _schema_ready = True
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
    d["issueShares"] = d.pop("issue_shares", None)
    d["rawStatus"]   = d.pop("raw_status", None)
    d["createdAt"]   = d.pop("created_at", None)
    d["updatedAt"]   = d.pop("updated_at", None)
    d["lastSeenAt"]  = d.pop("last_seen_at", None)
    d["subUpdatedAt"] = d.pop("sub_updated_at", None)
    d["gmpUpdatedAt"] = d.pop("gmp_updated_at", None)
    for key in ("subscription", "gmp"):
        raw = d.pop(key, None)
        parsed = None
        if raw:
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError):
                parsed = None
        d[key] = parsed
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
            cur = c.execute(
                """INSERT INTO ipos
                    (symbol, company_name, series, is_sme, is_reit,
                     open_date, close_date, price_low, price_high,
                     lot_size, issue_size_cr, issue_shares, raw_status,
                     source, from_gmp_only, is_listed,
                     created_at, updated_at, last_seen_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'nse',?,0,?,?,?)
                   ON CONFLICT(symbol) DO UPDATE SET
                     company_name  = excluded.company_name,
                     series        = excluded.series,
                     is_sme        = excluded.is_sme,
                     is_reit       = excluded.is_reit,
                     open_date     = COALESCE(excluded.open_date,  ipos.open_date),
                     close_date    = COALESCE(excluded.close_date, ipos.close_date),
                     price_low     = COALESCE(excluded.price_low,  ipos.price_low),
                     price_high    = COALESCE(excluded.price_high, ipos.price_high),
                     lot_size      = COALESCE(excluded.lot_size,   ipos.lot_size),
                     issue_size_cr = COALESCE(excluded.issue_size_cr, ipos.issue_size_cr),
                     issue_shares  = COALESCE(excluded.issue_shares,  ipos.issue_shares),
                     raw_status    = COALESCE(excluded.raw_status,    ipos.raw_status),
                     from_gmp_only = excluded.from_gmp_only,
                     updated_at    = excluded.updated_at,
                     last_seen_at  = excluded.last_seen_at
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
                    it.get("issueShares"),
                    it.get("rawStatus"),
                    1 if it.get("fromGmpOnly") else 0,
                    now,  # created_at (only used on INSERT)
                    now,  # updated_at
                    now,  # last_seen_at
                ),
            )
            # rowcount lives on the CURSOR, not the Connection — reading
            # c.rowcount here raised AttributeError, which rolled back the
            # whole batch and silently persisted nothing.
            count += cur.rowcount
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


def set_subscriptions(subs: dict[str, dict]) -> int:
    """Persist live subscription multiples per symbol ({sym: {qib,nii,...}}).
    Only non-empty payloads are written, so a failed NSE detail fetch never
    wipes the last known numbers. Returns rows updated."""
    if not subs:
        return 0
    now = _now_iso()
    with _conn() as c:
        n = 0
        for sym, sub in subs.items():
            if not sym or not isinstance(sub, dict) or not sub:
                continue
            # _summarise_subscription always returns a 4-key dict; when NSE's
            # detail response was empty every value is None. Persisting that
            # would erase the last-known multiples — skip all-null snapshots.
            if not any(v is not None for v in sub.values()):
                continue
            cur = c.execute(
                "UPDATE ipos SET subscription=?, sub_updated_at=?, updated_at=? "
                "WHERE symbol=?",
                (json.dumps(sub), now, now, sym.strip().upper()),
            )
            n += cur.rowcount
        c.commit()
    return n


def set_gmps(gmps: dict[str, dict]) -> int:
    """Persist last-known GMP per symbol ({sym: gmp_payload}). Only non-empty
    payloads are written — a failed scrape keeps yesterday's GMP visible.
    Returns rows updated."""
    if not gmps:
        return 0
    now = _now_iso()
    with _conn() as c:
        n = 0
        for sym, gmp in gmps.items():
            if not sym or not isinstance(gmp, dict) or not gmp:
                continue
            cur = c.execute(
                "UPDATE ipos SET gmp=?, gmp_updated_at=?, updated_at=? "
                "WHERE symbol=?",
                (json.dumps(gmp), now, now, sym.strip().upper()),
            )
            n += cur.rowcount
        c.commit()
    return n


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
