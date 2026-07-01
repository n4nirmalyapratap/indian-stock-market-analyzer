"""
nse_equity_bhavcopy_service.py

NSE Capital Market (CM) Bhav Copy downloader, parser and SQLite store.

Market-state-aware EOD data source:
  • Market CLOSED → primary historical source (instant local SQLite lookup)
  • Market OPEN   → provider skips itself so Yahoo can serve today's intraday

URL pattern (post 2024-07-08 UDiFF format):
  https://nsearchives.nseindia.com/content/cm/
      BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F.csv.zip

The archives subdomain has no Akamai wall — a browser User-Agent is enough.

Public API (all sync, safe to call via asyncio.to_thread):
    download_for_date(d)             -> int   rows ingested (0 = skip/error)
    backfill(days=90)                -> dict  {date_str: "ok"|"skipped"|"error"}
    get_bars(symbol, from_d, to_d)   -> list[dict]  sorted oldest→newest
    latest_date()                    -> date | None  most recent ingested date

Honesty rules (matching nse_bhavcopy_service.py):
  - Never silently return synthetic / empty candles. Callers get [] on miss.
  - HTTP / parse errors are logged and surfaced as "error" status; never
    silently replaced with zeros.
"""

from __future__ import annotations

import csv
import io
import logging
import sqlite3
import zipfile
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Optional

import httpx

from app.lib.db_paths import local_db_path

logger = logging.getLogger("equity_bhavcopy")

# ── Storage ───────────────────────────────────────────────────────────────────
_DB_PATH = local_db_path("equity_bhavcopy.db")

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0 Safari/537.36"
)
_HTTP_TIMEOUT  = 30.0
_UDIFF_CUTOVER = date(2024, 7, 8)

# ── Schema ────────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS equity_ohlcv (
    symbol      TEXT NOT NULL,
    trade_date  TEXT NOT NULL,    -- ISO YYYY-MM-DD
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      INTEGER,
    PRIMARY KEY (symbol, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_eq_symbol ON equity_ohlcv (symbol);
CREATE INDEX IF NOT EXISTS idx_eq_date   ON equity_ohlcv (trade_date);

CREATE TABLE IF NOT EXISTS ingest_log (
    trade_date  TEXT PRIMARY KEY,
    source      TEXT,
    rows        INTEGER,
    fetched_at  TEXT,
    status      TEXT             -- 'ok' | 'empty' | 'http_error' | 'parse_error'
);
"""


@contextmanager
def _conn():
    """Open a SQLite connection with the schema self-healed on every open."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    try:
        conn.executescript(_SCHEMA)
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        conn.close()


# ── URL builders ───────────────────────────────────────────────────────────────
def _udiff_url(d: date) -> str:
    # _0000 suffix is required — without it NSE returns 404.
    # Same pattern as the F&O equivalent: BhavCopy_NSE_FO_0_0_0_YYYYMMDD_F_0000.csv.zip
    return (
        "https://nsearchives.nseindia.com/content/cm/"
        f"BhavCopy_NSE_CM_0_0_0_{d.strftime('%Y%m%d')}_F_0000.csv.zip"
    )


def _legacy_url(d: date) -> str:
    """Pre-2024-07-08 format (EQ<DD><MON><YYYY>bhav.csv.zip)."""
    mon = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
           "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"][d.month - 1]
    return (
        "https://nsearchives.nseindia.com/content/historical/EQUITIES/"
        f"{d.year}/{mon}/cm{d.strftime('%d')}{mon}{d.year}bhav.csv.zip"
    )


# ── HTTP ───────────────────────────────────────────────────────────────────────
def _http_get(url: str) -> Optional[bytes]:
    """GET with browser UA. Returns raw bytes on 200, else None."""
    headers = {
        "User-Agent":      _USER_AGENT,
        "Accept":          "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer":         "https://www.nseindia.com/",
    }
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True) as c:
            r = c.get(url, headers=headers)
        if r.status_code == 200 and r.content:
            return r.content
        logger.debug("equity bhavcopy GET %s → HTTP %d", url, r.status_code)
        return None
    except httpx.HTTPError as exc:
        logger.warning("equity bhavcopy GET failed %s: %s", url, exc)
        return None


# ── Parse ──────────────────────────────────────────────────────────────────────
def _parse(raw: bytes, trade_date: date) -> list[dict]:
    """Extract CSV from ZIP (or raw bytes) and return equity OHLCV rows.

    Column name mapping handles both the new UDiFF names and the legacy names
    so one function covers the full date range.

    UDiFF headers (post-2024-07-08):
        TckrSymb, SctySrs, OpnPric, HghPric, LwPric, ClsPric, TtlTradgVol

    Legacy headers (pre-2024-07-08):
        SYMBOL, SERIES, OPEN, HIGH, LOW, CLOSE, TOTTRDQTY
    """
    # Unzip if needed
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            csv_name = next(
                (n for n in zf.namelist() if n.lower().endswith(".csv")), None
            )
            if csv_name is None:
                logger.warning("equity bhavcopy: no CSV in ZIP for %s", trade_date)
                return []
            csv_bytes = zf.read(csv_name)
    except zipfile.BadZipFile:
        csv_bytes = raw

    text   = csv_bytes.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    rows: list[dict] = []
    for rec in reader:
        # Normalize: strip whitespace from keys and values
        rec = {k.strip(): (v or "").strip() for k, v in rec.items() if k}

        # Series filter — keep EQ (main board) only; skip SM, BE, BZ, etc.
        series = rec.get("SctySrs") or rec.get("SERIES") or "EQ"
        if series.upper() not in ("EQ",):
            continue

        symbol = (rec.get("TckrSymb") or rec.get("SYMBOL") or "").upper()
        if not symbol:
            continue

        def _f(*keys: str) -> Optional[float]:
            for k in keys:
                v = rec.get(k, "")
                if v:
                    try:
                        return float(v)
                    except ValueError:
                        pass
            return None

        o   = _f("OpnPric",    "OPEN")
        h   = _f("HghPric",    "HIGH")
        lo  = _f("LwPric",     "LOW")
        c   = _f("ClsPric",    "CLOSE")
        vol = _f("TtlTradgVol","TOTTRDQTY")

        if c is None:
            continue

        rows.append({
            "symbol":     symbol,
            "trade_date": trade_date.isoformat(),
            "open":       o,
            "high":       h,
            "low":        lo,
            "close":      c,
            "volume":     int(vol) if vol is not None else None,
        })

    return rows


# ── Public: ingest one day ─────────────────────────────────────────────────────
def download_for_date(d: date) -> int:
    """Download and ingest one trading day into the local DB.

    Returns number of rows inserted (0 = already cached, holiday, or error).
    Idempotent: re-runs on the same date are no-ops if status is 'ok'.
    """
    # Already ingested successfully?
    with _conn() as conn:
        existing = conn.execute(
            "SELECT status FROM ingest_log WHERE trade_date = ?",
            (d.isoformat(),),
        ).fetchone()
    if existing and existing["status"] == "ok":
        return 0

    fetched_at = datetime.utcnow().isoformat()

    # Try UDiFF first (post-cutover), fall back to legacy format
    if d >= _UDIFF_CUTOVER:
        raw    = _http_get(_udiff_url(d))
        source = "nse_udiff"
        if raw is None:
            raw    = _http_get(_legacy_url(d))
            source = "nse_legacy_fallback"
    else:
        raw    = _http_get(_legacy_url(d))
        source = "nse_legacy"

    if raw is None:
        with _conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ingest_log VALUES (?,?,?,?,?)",
                (d.isoformat(), source, 0, fetched_at, "http_error"),
            )
            conn.commit()
        return 0

    parsed = _parse(raw, d)
    if not parsed:
        with _conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ingest_log VALUES (?,?,?,?,?)",
                (d.isoformat(), source, 0, fetched_at, "empty"),
            )
            conn.commit()
        return 0

    with _conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO equity_ohlcv
               (symbol, trade_date, open, high, low, close, volume)
               VALUES (:symbol,:trade_date,:open,:high,:low,:close,:volume)""",
            parsed,
        )
        conn.execute(
            "INSERT OR REPLACE INTO ingest_log VALUES (?,?,?,?,?)",
            (d.isoformat(), source, len(parsed), fetched_at, "ok"),
        )
        conn.commit()

    logger.info("equity bhavcopy %s: %d rows ingested [%s]", d, len(parsed), source)
    return len(parsed)


# ── Public: backfill N calendar days ──────────────────────────────────────────
def backfill(days: int = 90) -> dict[str, str]:
    """Download the last `days` calendar days not already in the DB.

    Weekends are skipped automatically (NSE has no trading on weekends).
    Holidays return http_error and are logged; they don't block backfill.

    Returns {date_iso: "ok" | "skipped" | "error"}.
    """
    today   = date.today()
    results: dict[str, str] = {}

    for i in range(1, days + 1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:          # Saturday=5, Sunday=6
            continue
        with _conn() as conn:
            row = conn.execute(
                "SELECT status FROM ingest_log WHERE trade_date = ?",
                (d.isoformat(),),
            ).fetchone()
        if row and row["status"] == "ok":
            results[d.isoformat()] = "skipped"
            continue
        n = download_for_date(d)
        results[d.isoformat()] = "ok" if n > 0 else "error"

    return results


# ── Public: query bars ─────────────────────────────────────────────────────────
def get_bars(
    symbol:    str,
    from_date: date,
    to_date:   date,
) -> list[dict]:
    """Return sorted OHLCV rows for `symbol` in [from_date, to_date]."""
    sym = symbol.strip().upper()
    with _conn() as conn:
        rows = conn.execute(
            """SELECT trade_date, open, high, low, close, volume
               FROM equity_ohlcv
               WHERE symbol = ? AND trade_date BETWEEN ? AND ?
               ORDER BY trade_date ASC""",
            (sym, from_date.isoformat(), to_date.isoformat()),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Public: coverage check ─────────────────────────────────────────────────────
def latest_date() -> Optional[date]:
    """Return the most recently ingested trading date, or None if DB is empty."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT MAX(trade_date) AS d FROM ingest_log WHERE status = 'ok'"
        ).fetchone()
    if row and row["d"]:
        return date.fromisoformat(row["d"])
    return None
