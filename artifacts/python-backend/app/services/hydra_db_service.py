"""
Hydra-Alpha Engine — Data Layer
SQLite OHLCV database with incremental updates from Yahoo Finance.
Schema: daily_prices(ticker, date, open, high, low, close, volume)

Fix applied (code review):
  FIX-5: Enable WAL journal mode and set busy_timeout on every connection.
         Serialise all write operations through a single asyncio.Lock so
         concurrent asyncio.gather() calls do not race on the DB file.
"""
from __future__ import annotations
import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "hydra_prices.db")
HEADERS = {"User-Agent": "Mozilla/5.0"}

# Single async lock that serialises all DB writes
_DB_WRITE_LOCK: asyncio.Lock | None = None

def _write_lock() -> asyncio.Lock:
    global _DB_WRITE_LOCK
    if _DB_WRITE_LOCK is None:
        _DB_WRITE_LOCK = asyncio.Lock()
    return _DB_WRITE_LOCK


# ── Connection factory ─────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    """Open a WAL-mode connection with busy_timeout to prevent locking errors."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


# ── Schema setup ───────────────────────────────────────────────────────────────

def ensure_schema() -> sqlite3.Connection:
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_prices (
            ticker  TEXT NOT NULL,
            date    TEXT NOT NULL,
            open    REAL,
            high    REAL,
            low     REAL,
            close   REAL,
            volume  INTEGER,
            PRIMARY KEY (ticker, date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ticker ON daily_prices(ticker)")
    conn.commit()
    return conn


def _get_latest_date(conn: sqlite3.Connection, ticker: str) -> Optional[str]:
    row = conn.execute(
        "SELECT MAX(date) FROM daily_prices WHERE ticker = ?", (ticker,)
    ).fetchone()
    return row[0] if row else None


def _upsert_rows(conn: sqlite3.Connection, ticker: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    conn.executemany(
        "INSERT OR REPLACE INTO daily_prices(ticker,date,open,high,low,close,volume) "
        "VALUES(?,?,?,?,?,?,?)",
        [
            (ticker, r["date"], r.get("open"), r.get("high"),
             r.get("low"), r.get("close"), r.get("volume", 0))
            for r in rows
        ],
    )
    conn.commit()
    return len(rows)


# ── Read helpers (no lock needed — WAL allows concurrent reads) ────────────────

def get_history(ticker: str, days: int = 252) -> list[dict]:
    """Return up to `days` rows newest-last from the local DB."""
    conn = ensure_schema()
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT date,open,high,low,close,volume FROM daily_prices "
        "WHERE ticker=? AND date>=? ORDER BY date ASC",
        (ticker, cutoff),
    ).fetchall()
    conn.close()
    return [
        {"date": r[0], "open": r[1], "high": r[2], "low": r[3],
         "close": r[4], "volume": r[5]}
        for r in rows
    ]


def get_close_series(ticker: str, days: int = 252) -> list[float]:
    return [r["close"] for r in get_history(ticker, days) if r["close"]]


def db_stats() -> dict:
    """Return row counts and ticker list from the DB."""
    try:
        conn = ensure_schema()
        total = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
        tickers = [r[0] for r in conn.execute(
            "SELECT ticker, COUNT(*) as c FROM daily_prices GROUP BY ticker ORDER BY c DESC"
        ).fetchall()]
        conn.close()
        return {"totalRows": total, "tickers": tickers, "dbPath": DB_PATH}
    except Exception as e:
        return {"error": str(e)}


# ── Incremental Yahoo Finance fetch ───────────────────────────────────────────

async def _fetch_yahoo(yahoo_ticker: str, start_date: Optional[str] = None) -> list[dict]:
    rng = "2y" if not start_date else "6mo"
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}"
        f"?interval=1d&range={rng}"
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=HEADERS)
            if resp.status_code != 200:
                return []
            result = resp.json()
            cr = result.get("chart", {}).get("result", [None])[0]
            if not cr:
                return []
            timestamps = cr.get("timestamp", [])
            q = cr.get("indicators", {}).get("quote", [{}])[0]
            adj = cr.get("indicators", {}).get("adjclose", [{}])
            adj_closes = adj[0].get("adjclose", []) if adj else []
            rows = []
            for i, ts in enumerate(timestamps):
                c = (
                    adj_closes[i]
                    if i < len(adj_closes) and adj_closes[i]
                    else (q.get("close", [])[i] if i < len(q.get("close", [])) else None)
                )
                if c is None:
                    continue
                date_str = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
                if start_date and date_str <= start_date:
                    continue
                rows.append({
                    "date":   date_str,
                    "open":   q.get("open",   [])[i] if i < len(q.get("open",   [])) else c,
                    "high":   q.get("high",   [])[i] if i < len(q.get("high",   [])) else c,
                    "low":    q.get("low",    [])[i] if i < len(q.get("low",    [])) else c,
                    "close":  c,
                    "volume": q.get("volume", [])[i] if i < len(q.get("volume", [])) else 0,
                })
            return rows
    except Exception as e:
        logger.warning("Yahoo fetch failed for %s: %s", yahoo_ticker, e)
        return []


def _nse_to_yahoo(symbol: str) -> str:
    if symbol.startswith("^") or "." in symbol:
        return symbol
    return f"{symbol}.NS"


async def update_ticker(symbol: str) -> dict:
    """
    Incrementally update a single ticker in the DB.
    FIX-5: write is serialised through _DB_WRITE_LOCK.
    """
    # Read without lock (WAL allows concurrent reads)
    conn = ensure_schema()
    latest = _get_latest_date(conn, symbol)
    conn.close()

    yahoo_ticker = _nse_to_yahoo(symbol)
    rows = await _fetch_yahoo(yahoo_ticker, start_date=latest)

    if rows:
        # Serialise writes
        async with _write_lock():
            conn = ensure_schema()
            inserted = _upsert_rows(conn, symbol, rows)
            conn.close()
    else:
        inserted = 0

    return {"ticker": symbol, "inserted": inserted, "latestDate": latest}


async def bulk_update(symbols: list[str], max_concurrent: int = 5) -> list[dict]:
    """Update multiple tickers; fetches happen concurrently, writes are serialised."""
    results = []
    for i in range(0, len(symbols), max_concurrent):
        batch = symbols[i: i + max_concurrent]
        batch_results = await asyncio.gather(
            *[update_ticker(s) for s in batch], return_exceptions=True
        )
        for s, r in zip(batch, batch_results):
            results.append({"ticker": s, "error": str(r)} if isinstance(r, Exception) else r)
    return results
