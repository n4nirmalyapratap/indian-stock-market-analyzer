"""scan_runner.py — reusable cache-first background scan engine.

Generalises the Investor Council screener pattern (``routes/agents.py``) so any
feature can scan the full ~2,000-symbol NSE universe without blocking a request:

  * results persist in a per-job SQLite table and stream in as each symbol
    finishes — callers read the cached rows IMMEDIATELY,
  * a background scan runs with bounded concurrency and reports ``{done,total}``
    progress the UI can poll, and
  * freshness is anchored to the NSE close: when the market is closed one scan
    per session suffices (served from cache the rest of the day); when open, a
    bounded rolling re-scan refreshes results every ``market_hours_ttl`` seconds.

A feature supplies two callables:
  * ``universe_fn() -> list[str]``         — the symbols to scan
  * ``scan_one(symbol) -> dict | None``    — JSON-serialisable result for one
    symbol, or ``None`` to drop it (e.g. no match / insufficient data). Results
    are upserted per-symbol; ``None`` deletes any stale prior row so the cache
    self-cleans across re-scans.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("scan_runner")

# Sentinel a scan_one() may return to mean "couldn't fetch — KEEP the last good
# cached row" (vs None = "delete it"). Prevents a transient network failure from
# wiping otherwise-valid rows during a scan (genuine delistings still get pruned
# when the symbol drops out of the universe).
KEEP = object()

_IST = ZoneInfo("Asia/Kolkata")
_NSE_CLOSE_HOUR = 15        # NSE settles at 15:30 IST
_NSE_CLOSE_MINUTE = 30
_POST_CLOSE_GRACE_MIN = 30  # trust EOD sources from 16:00 IST


def most_recent_nse_close() -> float:
    """Unix timestamp of the most recent NSE close (handles weekends/intraday).

    Walks back day-by-day from now-IST until it lands on a weekday whose
    16:00 IST has passed; that weekday's 15:30 close is the most recent
    settlement. Mirrors the screener's ``_most_recent_nse_close``.
    """
    now_ist = dt.datetime.now(_IST)
    today_close = now_ist.replace(hour=_NSE_CLOSE_HOUR, minute=_NSE_CLOSE_MINUTE,
                                  second=0, microsecond=0)
    cutoff = today_close + dt.timedelta(minutes=_POST_CLOSE_GRACE_MIN)
    candidate = now_ist if now_ist >= cutoff else now_ist - dt.timedelta(days=1)
    while candidate.weekday() >= 5:           # Sat=5, Sun=6 → walk to Friday
        candidate -= dt.timedelta(days=1)
    close = candidate.replace(hour=_NSE_CLOSE_HOUR, minute=_NSE_CLOSE_MINUTE,
                              second=0, microsecond=0)
    return close.timestamp()


def market_open_now() -> bool:
    """True during NSE cash hours (09:15–15:30 IST, Mon–Fri)."""
    now = dt.datetime.now(_IST)
    if now.weekday() >= 5:
        return False
    mins = now.hour * 60 + now.minute
    return 9 * 60 + 15 <= mins <= 15 * 60 + 30


class ScanJob:
    """One cache-first background scan over a symbol universe.

    Thread-safe progress state + SQLite-backed result cache. Construct once
    (module-level) per feature and call :meth:`maybe_kick` from the GET handler.
    """

    def __init__(
        self,
        name: str,
        db_path: str | Path,
        scan_one: Callable[[str], Awaitable[Optional[dict]]],
        universe_fn: Callable[[], list[str]],
        concurrency: int = 10,
        market_hours_ttl: int = 600,
        eod_only: bool = False,
    ) -> None:
        self.name = name
        self.db_path = Path(db_path)
        self.scan_one = scan_one
        self.universe_fn = universe_fn
        self.concurrency = max(1, int(concurrency))
        self.market_hours_ttl = market_hours_ttl
        # eod_only: auto-scans are anchored purely to the NSE close — NONE while
        # the market is open (serve the last sealed EOD), and a single scan after
        # each close. Manual force=True still scans anytime. (market_hours_ttl is
        # ignored when this is set.) Used by daily/EOD features like patterns.
        self.eod_only = eod_only
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "in_progress": False, "done": 0, "total": 0, "started_at": 0.0,
        }
        # In-memory mirror of the SQLite `results` table (symbol → result dict).
        # All reads (read_all) serve from here, so the hot request path never
        # re-parses thousands of JSON rows or touches the DB. SQLite is a
        # write-through store purely for crash/restart persistence. Both the
        # background workers and the request handlers touch this on the single
        # asyncio event-loop thread, so no extra lock is needed for it.
        self._results: dict[str, dict] = {}
        # Strong ref to the running scan task so it can't be GC'd mid-flight.
        self._task: Optional["asyncio.Task"] = None
        self._init_db()

    # ── persistence ──────────────────────────────────────────────────────────
    # NOTE: `with sqlite3.connect(...) as c` commits but does NOT close the
    # connection, so every helper opens its own connection in a try/finally and
    # closes it explicitly to avoid leaking handles across a 2,000-symbol scan.
    def _conn(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.db_path, timeout=10.0)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")   # WAL+NORMAL: durable enough, faster writes
        return c

    def _init_db(self) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS results ("
                "symbol TEXT PRIMARY KEY, data TEXT, updated_at REAL NOT NULL)"
            )
            conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
            conn.commit()
            # Warm the in-memory mirror from disk once at construction.
            for row in conn.execute("SELECT symbol, data FROM results").fetchall():
                try:
                    self._results[row["symbol"]] = json.loads(row["data"])
                except Exception:
                    continue
        finally:
            conn.close()

    def _meta_get(self, key: str) -> Optional[str]:
        conn = self._conn()
        try:
            r = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return r["value"] if r else None
        finally:
            conn.close()

    def _meta_set(self, key: str, value: Any) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO meta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )
            conn.commit()
        finally:
            conn.close()

    def _upsert(self, symbol: str, data: dict) -> None:
        self._results[symbol] = data            # in-memory mirror (hot reads)
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO results(symbol,data,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(symbol) DO UPDATE SET data=excluded.data, "
                "updated_at=excluded.updated_at",
                (symbol, json.dumps(data), time.time()),
            )
            conn.commit()
        finally:
            conn.close()

    def _delete(self, symbol: str) -> None:
        self._results.pop(symbol, None)
        conn = self._conn()
        try:
            conn.execute("DELETE FROM results WHERE symbol=?", (symbol,))
            conn.commit()
        finally:
            conn.close()

    def _prune_orphans(self, scanned: set[str]) -> int:
        """Drop cached rows for symbols that were NOT in the latest scan's universe.

        The per-symbol upsert/delete in `_run` only refreshes symbols that are
        actually scanned this pass. Symbols that fall OUT of the universe between
        runs (it's a dynamic registry∪cache union that can shrink) would otherwise
        linger forever with stale data — the very thing this prunes. Called once
        after each completed scan so the cache reflects exactly the current
        universe. Returns the number of rows removed.
        """
        orphans = [s for s in self._results if s not in scanned]
        if not orphans:
            return 0
        for s in orphans:
            self._results.pop(s, None)
        conn = self._conn()
        try:
            conn.executemany("DELETE FROM results WHERE symbol=?", [(s,) for s in orphans])
            conn.commit()
        finally:
            conn.close()
        return len(orphans)

    def read_all(self) -> list[dict]:
        """All cached per-symbol result dicts — served from the in-memory
        mirror (no DB hit, no JSON parsing). Order not guaranteed."""
        return list(self._results.values())

    # ── status ───────────────────────────────────────────────────────────────
    def last_scan_at(self) -> Optional[float]:
        v = self._meta_get("last_scan_at")
        try:
            return float(v) if v else None
        except (TypeError, ValueError):
            return None

    def status(self) -> dict:
        """Status block for the API: cache-first results metadata + progress."""
        with self._lock:
            st = dict(self._state)
        last = self.last_scan_at()
        cached_at = (
            dt.datetime.fromtimestamp(last, dt.timezone.utc)
              .isoformat().replace("+00:00", "Z")
            if last else None
        )
        return {
            "scanInProgress": st["in_progress"],
            "scanProgress": (
                {"done": st["done"], "total": st["total"]}
                if st["in_progress"] else None
            ),
            "cachedAt": cached_at,
            "universeSize": int(self._meta_get("last_scan_universe") or st["total"] or 0),
        }

    # ── freshness + kick ───────────────────────────────────────────────────────
    def _is_fresh(self) -> bool:
        last = self.last_scan_at()
        if self.eod_only:
            # Daily/EOD features: never auto-scan during market hours (the EOD
            # data can't change intraday — serve the last sealed close), and once
            # closed a single post-close scan suffices for the whole session.
            # Exception: a cold deploy (last is None) must still trigger the
            # first scan even if the market is currently open.
            if market_open_now():
                return last is not None
            return bool(last) and last >= most_recent_nse_close()
        if not last:
            return False
        if market_open_now():
            # Intraday: re-scan on a bounded interval so values keep updating.
            return (time.time() - last) < self.market_hours_ttl
        # Closed/weekend: fresh once the last scan ran after the latest close.
        return last >= most_recent_nse_close()

    def maybe_kick(self, force: bool = False) -> None:
        """Start a background scan if stale and none is running. Non-blocking.

        Claims the in-progress flag inside the lock to avoid two requests both
        starting a scan (same guard the screener uses).
        """
        with self._lock:
            if self._state["in_progress"]:
                return
            if not force and self._is_fresh():
                return
            try:
                symbols = list(self.universe_fn() or [])
            except Exception as exc:
                logger.warning("scan_runner[%s]: universe_fn failed: %s", self.name, exc)
                return
            if not symbols:
                return
            self._state.update(
                in_progress=True, done=0, total=len(symbols), started_at=time.time(),
            )
        try:
            # Keep a strong ref so the task can't be garbage-collected mid-run.
            self._task = asyncio.create_task(self._run(symbols))
        except RuntimeError as exc:
            logger.error("scan_runner[%s]: cannot start scan: %s", self.name, exc)
            with self._lock:
                self._state["in_progress"] = False

    async def _run(self, symbols: list[str]) -> None:
        logger.info("scan_runner[%s]: scanning %d symbols (concurrency=%d)",
                    self.name, len(symbols), self.concurrency)
        sem = asyncio.Semaphore(self.concurrency)

        async def _worker(sym: str) -> None:
            async with sem:
                try:
                    res = await self.scan_one(sym)
                except Exception as exc:
                    logger.debug("scan_runner[%s]: %s failed: %s", self.name, sym, exc)
                    res = None
                try:
                    if res is KEEP:
                        pass                      # transient fetch failure — keep last good row
                    elif res is None:
                        self._delete(sym)
                    else:
                        self._upsert(sym, res)
                except Exception as exc:
                    logger.warning("scan_runner[%s]: persist failed for %s: %s",
                                   self.name, sym, exc)
                with self._lock:
                    self._state["done"] += 1

        try:
            await asyncio.gather(*[_worker(s) for s in symbols], return_exceptions=True)
            # Prune rows for symbols that dropped out of the universe since the
            # last scan — the per-symbol loop above only refreshes scanned
            # symbols, so without this, results for removed symbols persist
            # forever (stale data with old timestamps). Keeps cache-first UX:
            # old rows stay visible DURING the scan, orphans vanish once it ends.
            removed = self._prune_orphans(set(symbols))
            if removed:
                logger.info("scan_runner[%s]: pruned %d stale symbol(s) no longer in universe",
                            self.name, removed)
            self._meta_set("last_scan_at", time.time())
            self._meta_set("last_scan_universe", len(symbols))
            with self._lock:
                started = self._state["started_at"]
            logger.info("scan_runner[%s]: scan complete in %ds",
                        self.name, int(time.time() - started))
        finally:
            with self._lock:
                self._state["in_progress"] = False
