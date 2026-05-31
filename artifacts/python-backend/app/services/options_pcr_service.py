"""PCR time-series — snapshot + read.

A scheduler (see `main._pcr_snapshot_scheduler`) calls `snapshot_now()`
every 15 minutes during market hours, capturing the Put-Call Ratio for
a small watch-list of liquid F&O underlyings. The intraday + multi-day
series is then read by `GET /api/options/pcr-history/{symbol}` and
rendered as a line chart on the F&O analytics tab.

Why per-snapshot history matters: a single PCR number ("0.92") is
nearly meaningless out of context — what traders actually look for is
the *direction* over the session (PCR climbing through 1.0 from below
often coincides with intraday capitulation; falling through 1.0 from
above suggests rally exhaustion). The chart makes that visible.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from app.lib.auth_store import ensure_primary_schema, get_conn

logger = logging.getLogger("options_pcr")

# Cache the CREATE TABLE IF NOT EXISTS check. `IF NOT EXISTS` is cheap
# (~ms) but on a high-traffic read path it adds up; the flag below
# elevates it to "free after the first call" while staying safe across
# threads via the lock.
_TABLE_INITIALIZED = False
_TABLE_INIT_LOCK = threading.Lock()


# Symbols we snapshot. Limited to the most-traded F&O underlyings;
# stock options change list daily so we focus on stable index PCR plus
# the top-volume single names. Operators can extend this via the
# OPTIONS_PCR_WATCHLIST env var (comma-separated symbols).
_DEFAULT_WATCHLIST = [
    "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY",
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS",
]


def _watchlist() -> list[str]:
    import os  # noqa: PLC0415
    raw = os.getenv("OPTIONS_PCR_WATCHLIST", "")
    if raw.strip():
        return [s.strip().upper() for s in raw.split(",") if s.strip()]
    return list(_DEFAULT_WATCHLIST)


def _ensure_table():
    """Create the PCR history table if it doesn't exist. Idempotent and
    thread-safe; only the first call actually hits PG, subsequent calls
    are a flag check (~ns)."""
    global _TABLE_INITIALIZED
    if _TABLE_INITIALIZED:
        return
    with _TABLE_INIT_LOCK:
        if _TABLE_INITIALIZED:
            return
        ensure_primary_schema()
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS options_pcr_history (
                        symbol         TEXT NOT NULL,
                        expiry_index   INT  NOT NULL DEFAULT 0,
                        fetched_at_ms  BIGINT NOT NULL,
                        pcr_oi         DOUBLE PRECISION,
                        pcr_volume     DOUBLE PRECISION,
                        spot           DOUBLE PRECISION,
                        expiry         TEXT,
                        PRIMARY KEY (symbol, expiry_index, fetched_at_ms)
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_pcr_recent "
                    "ON options_pcr_history (symbol, fetched_at_ms DESC)"
                )
        _TABLE_INITIALIZED = True


def get_history(symbol: str, hours: int = 24, expiry_index: int = 0) -> list[dict]:
    """Return the accumulated PCR snapshots for `symbol`, oldest-first.

    `hours` caps the lookback window — 24 covers an intraday view; 168
    (7 days) covers a multi-session trend. Older rows still live in
    the table; the cap is for response size only.
    """
    _ensure_table()
    cutoff_ms = int(time.time() * 1000) - max(1, hours) * 3600 * 1000
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT fetched_at_ms, pcr_oi, pcr_volume, spot, expiry "
                "  FROM options_pcr_history "
                " WHERE symbol = %s AND expiry_index = %s "
                "   AND fetched_at_ms >= %s "
                " ORDER BY fetched_at_ms ASC",
                (symbol.upper(), expiry_index, cutoff_ms),
            )
            rows = cur.fetchall()
    return [
        {
            "fetchedAtMs": r["fetched_at_ms"],
            "pcrOi":       r["pcr_oi"],
            "pcrVolume":   r["pcr_volume"],
            "spot":        r["spot"],
            "expiry":      r["expiry"],
        }
        for r in rows
    ]


async def snapshot_now(nse_service, symbols: Optional[list[str]] = None) -> int:
    """Snapshot PCR for every symbol in the watch-list.

    Called by the scheduler in main.py every 15 minutes during market
    hours. Returns the number of rows successfully written; partial
    failures are logged but never raise.
    """
    _ensure_table()
    syms = symbols if symbols else _watchlist()
    if not syms:
        return 0

    now_ms = int(time.time() * 1000)
    saved  = 0
    _IDX   = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"}

    for sym in syms:
        try:
            instrument = "OPTIDX" if any(idx in sym for idx in _IDX) else "OPTSTK"
            payload = await nse_service.get_option_chain(sym, instrument=instrument)
            if not payload:
                continue
            pcr = nse_service.calculate_pcr(payload, 0)
            # `calculate_pcr` returns dict {pcr_oi, pcr_volume, ...}
            # — guard against shape changes by defensive `.get()`.
            pcr_oi = (pcr or {}).get("pcr_oi") or (pcr or {}).get("pcr")
            pcr_vol = (pcr or {}).get("pcr_volume")
            # Extract spot + expiry for context. NSE's payload has
            # `records.underlyingValue` and `records.expiryDates[0]`.
            records = (payload or {}).get("records") or {}
            spot    = records.get("underlyingValue")
            expiries = records.get("expiryDates") or []
            expiry   = expiries[0] if expiries else None

            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO options_pcr_history
                            (symbol, expiry_index, fetched_at_ms,
                             pcr_oi, pcr_volume, spot, expiry)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, expiry_index, fetched_at_ms)
                        DO NOTHING
                        """,
                        (sym.upper(), 0, now_ms,
                         pcr_oi, pcr_vol, spot, expiry),
                    )
                    # rowcount reflects whether ON CONFLICT was a NO-OP
                    # (1 = inserted, 0 = duplicate / skipped). Counting
                    # only successful inserts gives an honest log line.
                    if cur.rowcount > 0:
                        saved += 1
        except Exception as exc:
            logger.warning("PCR snapshot failed for %s: %s", sym, str(exc)[:120])
            continue
    if saved:
        logger.info("PCR snapshot tick: saved %d/%d symbols.", saved, len(syms))
    return saved
