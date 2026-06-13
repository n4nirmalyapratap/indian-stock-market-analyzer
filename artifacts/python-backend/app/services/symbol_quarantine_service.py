"""
Symbol quarantine — silently skip symbols that have no usable price data.

The problem
-----------
Universe lists (NIFTY100, MIDCAP, SMALLCAP, MICROCAP) accumulate
symbols that have no usable data in any provider:
  * Genuinely delisted        — JSWISPL merged into JSWSTEEL in 2022
  * SME-only / EMERGE listings — DRONEACHARYA, SAMEERA — not on the
                                 main board, so EQ-series providers
                                 return nothing
  * Low-volume names           — no recent trades on any exchange
  * Suspended stocks           — temporarily halted by SEBI

Each one wastes a fetch attempt per scan AND surfaces as a scanner
"error" that the user has to visually filter past. The Security Registry
can't fix this — these symbols ARE the canonical NSE ticker; the
underlying security just has no data anywhere.

The fix
-------
Track empirical fetch outcomes per symbol in PG:
  * record_failure(symbol) — called when the chain returned 0 bars
  * record_success(symbol) — called when the chain returned >=1 bars
  * filter_quarantined(symbols) — scanner pre-filter

Auto-quarantine policy (configurable via env, sensible defaults):
  * After 3 consecutive failures with zero recorded successes
  * Quarantine lasts 30 days, then a single trial fetch is allowed
  * Any success at any time wipes the failure counter
  * Manual override (admin release) sticks for the rest of the session
    so the system doesn't immediately re-quarantine behind the operator

Performance
-----------
Reads (filter_quarantined) hit a process-cached set with a 5-minute TTL
so a scan over 500 symbols pays ONE PG round-trip max, not 500. Writes
go straight to PG with no batching — write volume is small (<200/scan
typical, most of which are no-ops because the symbol already had a
recorded outcome).

Cache invalidation: the cache is purely a read-side optimisation. Writes
update PG immediately; the in-process cache may be up to 5 minutes
stale but the worst-case impact is "one scan still surfaces a symbol we
just quarantined" — harmless.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

from ..lib.auth_store import ensure_primary_schema, get_conn, now_ms

logger = logging.getLogger("symbol_quarantine")


# ── Policy knobs ────────────────────────────────────────────────────────────
#
# Threshold for auto-quarantine. Conservative defaults — 3 failures is
# enough to catch genuinely-dead symbols on the very next scan after
# this code ships, while still tolerating one-off NSE blackouts.

def _int_env(name: str, default: int) -> int:
    try:
        v = int(os.environ.get(name) or default)
        return max(1, v)
    except Exception:
        return default


CONSECUTIVE_FAILS_TO_QUARANTINE = _int_env("QUARANTINE_THRESHOLD",       3)
QUARANTINE_DAYS                 = _int_env("QUARANTINE_RELEASE_DAYS",   30)
CACHE_TTL_S                     = _int_env("QUARANTINE_CACHE_TTL_S",   300)


# ── In-process cache ────────────────────────────────────────────────────────
#
# The cache is a set of currently-quarantined symbols, refreshed every
# CACHE_TTL_S seconds. Guarded by a lock because the scanner runs
# concurrent fetches (each can trigger a write); the cache itself
# is only ever swapped (never mutated in-place) so reads outside the
# lock see a consistent snapshot.

_cache_lock           = threading.Lock()
_cache_set: set[str]  = set()
_cache_loaded_at_s    = 0.0


def _refresh_cache() -> set[str]:
    """Pull the active-quarantine list from PG and replace the cache.
    Called automatically when the cache is older than CACHE_TTL_S."""
    global _cache_set, _cache_loaded_at_s
    ensure_primary_schema()
    cutoff_ms = now_ms() - QUARANTINE_DAYS * 86400 * 1000
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT symbol
                      FROM symbol_quarantine
                     WHERE quarantined = TRUE
                       AND quarantined_at_ms > %s
                    """,
                    (cutoff_ms,),
                )
                rows = cur.fetchall() or []
        fresh = {row["symbol"] for row in rows}
    except Exception as exc:
        logger.warning("quarantine cache refresh failed: %s", exc)
        return _cache_set    # keep stale rather than empty
    with _cache_lock:
        _cache_set = fresh
        _cache_loaded_at_s = time.time()
    return fresh


def _cached_set() -> set[str]:
    """Return the active-quarantine set, refreshing on TTL expiry."""
    if time.time() - _cache_loaded_at_s > CACHE_TTL_S:
        return _refresh_cache()
    return _cache_set


# ── Public API ──────────────────────────────────────────────────────────────


def is_quarantined(symbol: str) -> bool:
    """Fast lookup — O(1) on cache, refreshes on TTL miss."""
    if not symbol:
        return False
    return symbol.strip().upper() in _cached_set()


def filter_quarantined(symbols: list[str]) -> tuple[list[str], list[str]]:
    """Split a symbol list into (kept, quarantined).

    Pre-filter for the scanner: scanner iterates `kept`, surfaces
    `quarantined` count separately as "auto-skipped — N symbols with
    no usable data" instead of N individual error rows."""
    if not symbols:
        return [], []
    qset = _cached_set()
    kept: list[str] = []
    quarantined: list[str] = []
    for s in symbols:
        if (s or "").strip().upper() in qset:
            quarantined.append(s)
        else:
            kept.append(s)
    return kept, quarantined


def record_failure(symbol: str, reason: str = "no-data") -> None:
    """Record one fetch failure. Auto-quarantines once consecutive
    failures cross the threshold.

    A "failure" here means: the chain returned 0 bars (NOT a transient
    HTTP error). 0 bars across NSE + BSE + Yahoo + Twelve Data + Stooq
    is empirically a dead symbol; HTTP errors are noise that we don't
    want to count as a failure signal.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return
    ensure_primary_schema()
    ts = now_ms()
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Upsert pattern: on first failure, INSERT a row with
                # consecutive_failures=1. On subsequent failures,
                # INCREMENT consecutive_failures. Once we cross the
                # threshold AND the user hasn't manually released
                # this symbol, flip quarantined = TRUE.
                cur.execute(
                    """
                    INSERT INTO symbol_quarantine
                        (symbol, first_failed_at_ms, last_attempted_at_ms,
                         consecutive_failures, total_failures, reason)
                    VALUES (%s, %s, %s, 1, 1, %s)
                    ON CONFLICT (symbol) DO UPDATE SET
                        last_attempted_at_ms = EXCLUDED.last_attempted_at_ms,
                        consecutive_failures = symbol_quarantine.consecutive_failures + 1,
                        total_failures       = symbol_quarantine.total_failures       + 1,
                        reason               = EXCLUDED.reason,
                        -- Only auto-quarantine when:
                        --   1. not already quarantined
                        --   2. not manually released by an admin
                        --   3. consecutive failure count >= threshold (-1 because we just incremented)
                        quarantined          = CASE
                            WHEN symbol_quarantine.quarantined        THEN TRUE
                            WHEN symbol_quarantine.manual_override    THEN FALSE
                            WHEN symbol_quarantine.consecutive_failures + 1 >= %s THEN TRUE
                            ELSE FALSE
                        END,
                        quarantined_at_ms    = CASE
                            WHEN symbol_quarantine.quarantined        THEN symbol_quarantine.quarantined_at_ms
                            WHEN symbol_quarantine.manual_override    THEN NULL
                            WHEN symbol_quarantine.consecutive_failures + 1 >= %s THEN EXCLUDED.last_attempted_at_ms
                            ELSE NULL
                        END
                    """,
                    (sym, ts, ts, reason,
                     CONSECUTIVE_FAILS_TO_QUARANTINE,
                     CONSECUTIVE_FAILS_TO_QUARANTINE),
                )
            conn.commit()
    except Exception as exc:
        logger.warning("quarantine record_failure(%s) failed: %s", sym, exc)


def record_success(symbol: str) -> None:
    """Record one fetch success. Wipes consecutive_failures and
    un-quarantines if previously quarantined.

    Called from the scanner whenever the chain returned >=1 bars for
    this symbol. We don't bother checking the current PG state first —
    UPDATE is cheap, and the "no row exists" case is fine (no-op when
    nothing to update)."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return
    ensure_primary_schema()
    ts = now_ms()
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE symbol_quarantine
                       SET last_success_at_ms   = %s,
                           consecutive_failures = 0,
                           total_successes      = total_successes + 1,
                           quarantined          = FALSE,
                           quarantined_at_ms    = NULL
                     WHERE symbol = %s
                    """,
                    (ts, sym),
                )
            conn.commit()
    except Exception as exc:
        logger.warning("quarantine record_success(%s) failed: %s", sym, exc)


def list_quarantined() -> list[dict]:
    """Admin read — every currently-quarantined symbol with metadata."""
    ensure_primary_schema()
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT symbol, first_failed_at_ms, last_attempted_at_ms,
                           last_success_at_ms, consecutive_failures,
                           total_failures, total_successes,
                           quarantined_at_ms, reason, manual_override
                      FROM symbol_quarantine
                     WHERE quarantined = TRUE
                  ORDER BY quarantined_at_ms DESC
                    """
                )
                rows = cur.fetchall() or []
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("quarantine list_quarantined failed: %s", exc)
        return []


def release(symbol: str) -> bool:
    """Admin release — clears quarantine on `symbol` and marks it
    manual_override so the auto-quarantine doesn't immediately re-fire
    on the next scan.

    Returns True if a row was updated, False if symbol wasn't quarantined."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return False
    ensure_primary_schema()
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE symbol_quarantine
                       SET quarantined          = FALSE,
                           quarantined_at_ms    = NULL,
                           consecutive_failures = 0,
                           manual_override      = TRUE
                     WHERE symbol = %s
                       AND quarantined = TRUE
                    """,
                    (sym,),
                )
                rowcount = cur.rowcount
            conn.commit()
    except Exception as exc:
        logger.warning("quarantine release(%s) failed: %s", sym, exc)
        return False
    # Invalidate the in-process cache so the next read picks up the change.
    _refresh_cache()
    return rowcount > 0


def release_all() -> int:
    """Nuclear admin option — release every quarantined symbol. Returns
    the number released. Useful after a major upstream outage where the
    auto-quarantine over-flagged a bunch of valid symbols."""
    ensure_primary_schema()
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE symbol_quarantine
                       SET quarantined          = FALSE,
                           quarantined_at_ms    = NULL,
                           consecutive_failures = 0,
                           manual_override      = TRUE
                     WHERE quarantined = TRUE
                    """
                )
                rowcount = cur.rowcount
            conn.commit()
    except Exception as exc:
        logger.warning("quarantine release_all failed: %s", exc)
        return 0
    _refresh_cache()
    return rowcount


def stats() -> dict:
    """One-shot health snapshot for the admin dashboard."""
    ensure_primary_schema()
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        COUNT(*)                                AS tracked,
                        COUNT(*) FILTER (WHERE quarantined)     AS active,
                        COUNT(*) FILTER (WHERE manual_override) AS released_by_admin
                      FROM symbol_quarantine
                    """
                )
                row = cur.fetchone()
        return dict(row) if row else {"tracked": 0, "active": 0, "released_by_admin": 0}
    except Exception as exc:
        logger.warning("quarantine stats failed: %s", exc)
        return {"tracked": 0, "active": 0, "released_by_admin": 0, "error": str(exc)}
