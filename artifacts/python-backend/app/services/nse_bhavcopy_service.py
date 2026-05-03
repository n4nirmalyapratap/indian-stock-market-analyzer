"""
nse_bhavcopy_service.py
NSE F&O Bhavcopy archive downloader, parser and SQLite cache.

Public API:
    download_bhavcopy(d)           -> bytes (raw CSV) or None
    parse_bhavcopy(csv_bytes, d)   -> list[dict] of option records
    ingest_bhavcopy(d)             -> int   (rows inserted)
    lookup_premium(...)            -> float | None  (point-in-time CLOSE)
    get_coverage()                 -> dict (date_min, date_max, row_count, …)
    refresh_recent(days=7)         -> dict (per-day status)

Honesty principles:
- Never silently substitute synthetic prices.  Callers must check the return
  value; `lookup_premium` returns None when the (symbol, date, strike, expiry,
  type) tuple is missing, and the caller is responsible for tagging the
  fallback path explicitly (e.g. `premium_source = "synthetic_bs"`).
- Network/parse errors are logged at WARNING and bubble up to the caller via
  return value, never re-raised silently.

Sources tried in order:
    1. NSE UDiFF (post-2024-07-08):
       https://nsearchives.nseindia.com/content/fo/
         BhavCopy_NSE_FO_0_0_0_<YYYYMMDD>_F_0000.csv.zip
    2. NSE legacy (pre-2024-07-08):
       https://nsearchives.nseindia.com/content/historical/DERIVATIVES/
         <YYYY>/<MON>/fo<DD><MON><YYYY>bhav.csv.zip
    3. BSE UDiFF (SENSEX/BANKEX):
       https://www.bseindia.com/download/BhavCopy/Derivative/
         BhavCopy_BSE_DR_0_0_0_<YYYYMMDD>_F_0000.CSV

NSE serves the historical archive without auth, but enforces a browser-like
User-Agent.  We do *not* spoof cookies or session tokens — only the UA.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import sqlite3
import zipfile
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

import httpx

logger = logging.getLogger("nse_bhavcopy")

# ── Storage ──────────────────────────────────────────────────────────────────
_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "nse_options_cache.sqlite"
_DB_PATH = Path(os.environ.get("NSE_BHAVCOPY_DB", str(_DEFAULT_DB_PATH)))

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0 Safari/537.36"
)
_HTTP_TIMEOUT = 30.0
_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
           "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

# Map our internal symbol space → bhavcopy SYMBOL column
_NSE_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"}
_BSE_SYMBOLS = {"SENSEX", "BANKEX"}


# ── Schema ───────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS option_quotes (
    symbol      TEXT NOT NULL,
    trade_date  TEXT NOT NULL,    -- ISO YYYY-MM-DD
    expiry      TEXT NOT NULL,    -- ISO YYYY-MM-DD
    strike      REAL NOT NULL,
    opt_type    TEXT NOT NULL,    -- 'call' | 'put'
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    settle      REAL,
    contracts   INTEGER,
    oi          INTEGER,
    PRIMARY KEY (symbol, trade_date, expiry, strike, opt_type)
);
CREATE INDEX IF NOT EXISTS idx_oq_lookup ON option_quotes (symbol, trade_date);
CREATE INDEX IF NOT EXISTS idx_oq_expiry ON option_quotes (symbol, expiry);

CREATE TABLE IF NOT EXISTS ingest_log (
    trade_date  TEXT PRIMARY KEY,
    source      TEXT,            -- 'nse_udiff' | 'nse_legacy' | 'bse_udiff' | 'mixed'
    rows        INTEGER,
    fetched_at  TEXT,
    status      TEXT             -- 'ok' | 'empty' | 'http_error' | 'parse_error'
);
"""


@contextmanager
def _connect():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    try:
        conn.executescript(_SCHEMA)
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        conn.close()


# ── URL builders ─────────────────────────────────────────────────────────────

def _nse_udiff_url(d: date) -> str:
    return ("https://nsearchives.nseindia.com/content/fo/"
            f"BhavCopy_NSE_FO_0_0_0_{d.strftime('%Y%m%d')}_F_0000.csv.zip")


def _nse_legacy_url(d: date) -> str:
    mon = _MONTHS[d.month - 1]
    return ("https://nsearchives.nseindia.com/content/historical/DERIVATIVES/"
            f"{d.year}/{mon}/fo{d.strftime('%d')}{mon}{d.year}bhav.csv.zip")


def _bse_udiff_url(d: date) -> str:
    return ("https://www.bseindia.com/download/BhavCopy/Derivative/"
            f"BhavCopy_BSE_DR_0_0_0_{d.strftime('%Y%m%d')}_F_0000.CSV")


# Cutover: NSE moved to UDiFF format on 2024-07-08
_UDIFF_CUTOVER = date(2024, 7, 8)


# ── HTTP ─────────────────────────────────────────────────────────────────────

def _http_get(url: str, *, referer: str = "https://www.nseindia.com/") -> Optional[bytes]:
    """GET with browser-like UA. Returns body bytes on 200, else None."""
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": referer,
    }
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True) as c:
            r = c.get(url, headers=headers)
        if r.status_code == 200 and r.content:
            return r.content
        logger.info("bhavcopy GET %s → %d (%d bytes)", url, r.status_code, len(r.content or b""))
        return None
    except httpx.HTTPError as exc:
        logger.warning("bhavcopy GET %s failed: %s", url, exc)
        return None


# ── Download orchestration ──────────────────────────────────────────────────

def download_bhavcopy(d: date) -> tuple[Optional[bytes], str]:
    """Try all known sources for a given trading date. Returns (csv_bytes, source).

    csv_bytes is the *unzipped* CSV (latin-1 / ascii); source is one of
    'nse_udiff', 'nse_legacy', 'bse_udiff', or '' on failure.
    """
    # NSE — UDiFF first (post-Jul 2024), legacy first (pre-Jul 2024).
    nse_attempts = (
        [_nse_udiff_url, _nse_legacy_url] if d >= _UDIFF_CUTOVER
        else [_nse_legacy_url, _nse_udiff_url]
    )
    for builder in nse_attempts:
        url = builder(d)
        body = _http_get(url)
        if not body:
            continue
        try:
            with zipfile.ZipFile(io.BytesIO(body)) as zf:
                name = next((n for n in zf.namelist() if n.lower().endswith(".csv")), None)
                if not name:
                    continue
                csv_bytes = zf.read(name)
            tag = "nse_udiff" if "BhavCopy_NSE" in url else "nse_legacy"
            return csv_bytes, tag
        except zipfile.BadZipFile:
            logger.warning("bhavcopy %s: not a zip (likely HTML error page)", url)

    # BSE — UDiFF only; CSV is served plain (no zip)
    bse_body = _http_get(_bse_udiff_url(d), referer="https://www.bseindia.com/")
    if bse_body:
        return bse_body, "bse_udiff"

    return None, ""


# ── Parsing ─────────────────────────────────────────────────────────────────

def _norm_opt_type(s: str) -> Optional[str]:
    s = (s or "").strip().upper()
    if s in ("CE", "CALL", "C"):
        return "call"
    if s in ("PE", "PUT", "P"):
        return "put"
    return None


def _norm_expiry(s: str) -> Optional[str]:
    """Parse expiry from any of the known bhavcopy formats → ISO YYYY-MM-DD."""
    s = (s or "").strip()
    if not s:
        return None
    # Try common formats
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _norm_trade_date(s: str) -> Optional[str]:
    return _norm_expiry(s)  # same set of formats


def parse_bhavcopy(csv_bytes: bytes, trade_date: date,
                   source: str = "") -> list[dict]:
    """Parse a bhavcopy CSV → list of option records.

    Handles three column layouts transparently:
      - NSE legacy   (INSTRUMENT, SYMBOL, EXPIRY_DT, STRIKE_PR, OPTION_TYP, ...)
      - NSE UDiFF    (TckrSymb, XpryDt, StrkPric, OptnTp, FinInstrmTp, ClsPric, ...)
      - BSE UDiFF    (same UDiFF columns; FinInstrmTp like 'IO' / 'STO')
    """
    text = csv_bytes.decode("latin-1", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    cols = {c.lower(): c for c in (reader.fieldnames or [])}

    is_legacy = "option_typ" in cols
    out: list[dict] = []
    td = trade_date.isoformat()

    for row in reader:
        if is_legacy:
            instrument = (row.get("INSTRUMENT") or "").strip().upper()
            if instrument not in ("OPTIDX", "OPTSTK"):
                continue
            sym = (row.get("SYMBOL") or "").strip().upper()
            opt = _norm_opt_type(row.get("OPTION_TYP", ""))
            exp = _norm_expiry(row.get("EXPIRY_DT", ""))
            try:
                strike = float(row.get("STRIKE_PR") or 0)
            except ValueError:
                continue
            if not (sym and opt and exp and strike > 0):
                continue
            try:
                rec = dict(
                    symbol=sym, trade_date=td, expiry=exp,
                    strike=strike, opt_type=opt,
                    open=float(row.get("OPEN") or 0) or None,
                    high=float(row.get("HIGH") or 0) or None,
                    low=float(row.get("LOW") or 0) or None,
                    close=float(row.get("CLOSE") or 0) or None,
                    settle=float(row.get("SETTLE_PR") or 0) or None,
                    contracts=int(float(row.get("CONTRACTS") or 0)) or None,
                    oi=int(float(row.get("OPEN_INT") or 0)) or None,
                )
            except (TypeError, ValueError):
                continue
            out.append(rec)
        else:
            # UDiFF (NSE & BSE share the column names)
            instr = (row.get("FinInstrmTp") or "").strip().upper()
            # NSE: OPTIDX/OPTSTK ; BSE: IO (Index Option) / STO (Stock Option)
            if instr not in ("OPTIDX", "OPTSTK", "IO", "STO"):
                continue
            sym = (row.get("TckrSymb") or "").strip().upper()
            opt = _norm_opt_type(row.get("OptnTp", ""))
            exp = _norm_expiry(row.get("XpryDt", ""))
            try:
                strike = float(row.get("StrkPric") or 0)
            except ValueError:
                continue
            if not (sym and opt and exp and strike > 0):
                continue
            try:
                rec = dict(
                    symbol=sym, trade_date=td, expiry=exp,
                    strike=strike, opt_type=opt,
                    open=float(row.get("OpnPric") or 0) or None,
                    high=float(row.get("HghPric") or 0) or None,
                    low=float(row.get("LwPric") or 0) or None,
                    close=float(row.get("ClsPric") or 0) or None,
                    settle=float(row.get("SttlmPric") or 0) or None,
                    contracts=int(float(row.get("TtlTradgVol") or 0)) or None,
                    oi=int(float(row.get("OpnIntrst") or 0)) or None,
                )
            except (TypeError, ValueError):
                continue
            out.append(rec)
    return out


# ── DB writes ────────────────────────────────────────────────────────────────

def _insert_records(conn: sqlite3.Connection, recs: Iterable[dict]) -> int:
    rows = [
        (r["symbol"], r["trade_date"], r["expiry"], r["strike"], r["opt_type"],
         r.get("open"), r.get("high"), r.get("low"), r.get("close"),
         r.get("settle"), r.get("contracts"), r.get("oi"))
        for r in recs
    ]
    if not rows:
        return 0
    conn.executemany(
        "INSERT OR REPLACE INTO option_quotes "
        "(symbol, trade_date, expiry, strike, opt_type, open, high, low, "
        " close, settle, contracts, oi) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    return len(rows)


def _log_ingest(conn: sqlite3.Connection, d: date, source: str,
                rows: int, status: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO ingest_log (trade_date, source, rows, fetched_at, status) "
        "VALUES (?,?,?,?,?)",
        (d.isoformat(), source, rows, datetime.utcnow().isoformat(timespec="seconds"), status),
    )


def ingest_bhavcopy(d: date) -> dict:
    """Download → parse → upsert one trading date.  Returns status dict."""
    csv_bytes, source = download_bhavcopy(d)
    if not csv_bytes:
        with _connect() as conn:
            _log_ingest(conn, d, "", 0, "http_error")
            conn.commit()
        return {"date": d.isoformat(), "rows": 0, "source": "", "status": "http_error"}
    try:
        recs = parse_bhavcopy(csv_bytes, d, source)
    except Exception as exc:                                 # pragma: no cover
        logger.warning("bhavcopy parse failed for %s: %s", d, exc)
        with _connect() as conn:
            _log_ingest(conn, d, source, 0, "parse_error")
            conn.commit()
        return {"date": d.isoformat(), "rows": 0, "source": source, "status": "parse_error"}
    with _connect() as conn:
        n = _insert_records(conn, recs)
        _log_ingest(conn, d, source, n, "ok" if n > 0 else "empty")
        conn.commit()
    logger.info("bhavcopy %s: %d rows from %s", d, n, source)
    return {"date": d.isoformat(), "rows": n, "source": source,
            "status": "ok" if n > 0 else "empty"}


# ── Lookup ───────────────────────────────────────────────────────────────────

def lookup_premium(symbol: str, expiry: date, strike: float, opt_type: str,
                   trade_date: date) -> Optional[float]:
    """Return the historical CLOSE price for the exact contract on the given
    trading day.  Returns None when the row does not exist.

    Caller is responsible for tagging the fallback path when None is returned.
    """
    sym = symbol.upper()
    if sym not in _NSE_SYMBOLS and sym not in _BSE_SYMBOLS:
        return None
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT close, settle FROM option_quotes "
                "WHERE symbol=? AND trade_date=? AND expiry=? AND strike=? AND opt_type=?",
                (sym, trade_date.isoformat(), expiry.isoformat(),
                 float(strike), opt_type.lower()),
            ).fetchone()
    except sqlite3.Error as exc:                              # pragma: no cover
        logger.warning("bhavcopy lookup_premium DB error: %s", exc)
        return None
    if not row:
        return None
    # Prefer CLOSE; fall back to SETTLE_PR when the option did not trade.
    px = row["close"] if row["close"] not in (None, 0) else row["settle"]
    return float(px) if px not in (None, 0) else None


# ── Coverage / introspection ─────────────────────────────────────────────────

def get_coverage() -> dict:
    """Return cache stats — used by the /options/bhavcopy/coverage endpoint."""
    try:
        with _connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS c, MIN(trade_date) AS mn, MAX(trade_date) AS mx "
                "FROM option_quotes"
            ).fetchone()
            by_sym = conn.execute(
                "SELECT symbol, COUNT(*) AS c, MIN(trade_date) AS mn, "
                "       MAX(trade_date) AS mx "
                "FROM option_quotes GROUP BY symbol"
            ).fetchall()
            recent = conn.execute(
                "SELECT trade_date, source, rows, status FROM ingest_log "
                "ORDER BY trade_date DESC LIMIT 20"
            ).fetchall()
    except sqlite3.Error as exc:                              # pragma: no cover
        return {"error": str(exc), "row_count": 0}
    return {
        "row_count": total["c"] if total else 0,
        "date_min":  total["mn"] if total else None,
        "date_max":  total["mx"] if total else None,
        "by_symbol": [dict(r) for r in by_sym],
        "recent_ingests": [dict(r) for r in recent],
        "db_path": str(_DB_PATH),
    }


def refresh_recent(days: int = 7) -> list[dict]:
    """Re-fetch the last `days` calendar days that aren't already cached.
    Skips weekends and dates already marked 'ok'.
    """
    today = date.today()
    out: list[dict] = []
    with _connect() as conn:
        cached = {row["trade_date"] for row in conn.execute(
            "SELECT trade_date FROM ingest_log WHERE status='ok'"
        )}
    for i in range(1, days + 1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:           # skip Sat/Sun
            continue
        if d.isoformat() in cached:
            continue
        out.append(ingest_bhavcopy(d))
    return out
