"""
dhan_scrip_master_service.py — Dhan public F&O contract master.

Dhan Technology publishes a daily-refreshed CSV of all exchange-traded
F&O instruments (no authentication required) at:
  https://images.dhan.co/api-data/api-scrip-master.csv

This service uses that file to answer three questions:
  1. get_expiry_dates(symbol)     — which expiry dates exist?
  2. get_strikes(symbol, expiry)  — which strikes trade on a given expiry?
  3. get_lot_size(symbol)         — what is the lot size?

Why Dhan instead of synthesising dates:
  The scrip master is Dhan's live trading reference — it is authoritative,
  updated every trading day, and covers BOTH NSE (NIFTY, BANKNIFTY, …) and
  BSE (SENSEX, BANKEX) index derivatives as well as all equity F&O stocks.
  Using it eliminates the need to hard-code monthly/weekly expiry calendars
  and correctly reflects any SEBI circular changes.

CSV columns used:
  SEM_EXM_EXCH_ID     — "NSE" or "BSE"
  SEM_INSTRUMENT_NAME — "OPTIDX" (index option) | "OPTSTK" (stock option)
  SEM_TRADING_SYMBOL  — e.g. "BANKNIFTY-Jun2026-65400-CE"
  SEM_EXPIRY_DATE     — "YYYY-MM-DD HH:MM:SS"
  SEM_STRIKE_PRICE    — numeric string
  SEM_LOT_UNITS       — numeric string (lot size)
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import time
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("dhan_scrip_master")

_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"

# Disk cache — stored in market_cache/ so it survives process restarts.
# One file per calendar day; if the file's date is today we never hit Dhan again
# regardless of how many times the server is restarted.
_HERE            = Path(__file__).resolve().parent.parent.parent  # …/python-backend
_DISK_CACHE_PATH = _HERE / "market_cache" / "dhan_scrip_master.csv"

_cache_rows: list[dict] = []
_cache_ts:   float      = 0.0
_fetch_lock  = asyncio.Lock()

_MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

# ── Symbol → (exchange, trading-symbol prefix) mapping ───────────────────────
# Trading symbols in the CSV have the form  <PREFIX>-<MonYYYY>-<STRIKE>-<CE/PE>
# so we only need the prefix (up to and including the first dash) to filter rows.

_SYM_INFO: dict[str, dict] = {
    # BSE index derivatives
    "SENSEX":     {"exch": "BSE", "prefix": "SENSEX"},
    "BANKEX":     {"exch": "BSE", "prefix": "BANKEX"},
    # NSE index derivatives
    "NIFTY":      {"exch": "NSE", "prefix": "NIFTY"},
    "NIFTY50":    {"exch": "NSE", "prefix": "NIFTY"},
    "BANKNIFTY":  {"exch": "NSE", "prefix": "BANKNIFTY"},
    "FINNIFTY":   {"exch": "NSE", "prefix": "FINNIFTY"},
    "MIDCPNIFTY": {"exch": "NSE", "prefix": "MIDCPNIFTY"},
}


def _sym_info(symbol: str) -> dict:
    """Return exchange + prefix dict for a symbol.

    For known index derivatives uses the static map; for equity F&O stocks
    defaults to NSE with the symbol itself as prefix (e.g. RELIANCE → RELIANCE-).
    """
    upper = symbol.strip().upper()
    if upper in _SYM_INFO:
        return _SYM_INFO[upper]
    return {"exch": "NSE", "prefix": upper}


def _parse_expiry(raw: str) -> Optional[str]:
    """Convert "YYYY-MM-DD HH:MM:SS" → "DD-Mon-YYYY".  Returns None on failure."""
    try:
        d = datetime.strptime(raw[:10], "%Y-%m-%d")
        return f"{d.day:02d}-{_MON[d.month - 1]}-{d.year}"
    except (ValueError, TypeError):
        return None


def _expiry_to_ymd(nse_fmt: str) -> Optional[str]:
    """Convert "DD-Mon-YYYY" → "YYYY-MM-DD" for CSV date comparison."""
    try:
        d = datetime.strptime(nse_fmt, "%d-%b-%Y")
        return d.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


# ── Disk cache helpers ────────────────────────────────────────────────────────

def _disk_is_fresh() -> bool:
    """Return True if the on-disk CSV was written today (IST calendar day).

    The scrip master changes at most once per trading day (new contracts are
    added for upcoming expiries). If we already have today's file, there is
    nothing new to download — even across process restarts.
    """
    try:
        if not _DISK_CACHE_PATH.exists():
            return False
        from datetime import timezone, timedelta
        ist = timezone(timedelta(hours=5, minutes=30))
        mtime_ist = datetime.fromtimestamp(_DISK_CACHE_PATH.stat().st_mtime, tz=ist).date()
        today_ist = datetime.now(tz=ist).date()
        return mtime_ist >= today_ist
    except Exception:
        return False


def _load_from_disk() -> list[dict]:
    """Read the on-disk CSV into a list of dicts.  Returns [] on any error."""
    try:
        with open(_DISK_CACHE_PATH, encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
    except Exception as exc:
        logger.debug("Dhan disk cache read failed: %s", exc)
        return []


def _save_to_disk(text: str) -> None:
    """Persist CSV text to disk (creates market_cache/ if needed)."""
    try:
        _DISK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _DISK_CACHE_PATH.write_text(text, encoding="utf-8")
    except Exception as exc:
        logger.warning("Dhan disk cache write failed: %s", exc)


# ── CSV fetch / in-memory cache ───────────────────────────────────────────────

async def _get_rows() -> list[dict]:
    """Return the scrip-master rows, using this priority:

    1. In-memory cache (fastest — set after first successful load each run).
    2. Today's on-disk CSV (fast — avoids the HTTP round-trip on restart).
    3. Live download from Dhan CDN (at most once per calendar day).

    The live download is therefore called at most once per day total —
    on the first request after the previous day's file becomes stale.
    """
    global _cache_rows, _cache_ts

    # 1 — hot in-memory cache
    if _cache_rows:
        return _cache_rows

    async with _fetch_lock:
        if _cache_rows:          # re-check inside lock
            return _cache_rows

        # 2 — today's disk file (survives restarts without another HTTP call)
        if _disk_is_fresh():
            rows = _load_from_disk()
            if rows:
                _cache_rows = rows
                _cache_ts   = time.time()
                logger.info("Dhan scrip master loaded from disk: %d rows", len(rows))
                return rows

        # 3 — download from Dhan (once per calendar day)
        try:
            async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
                resp = await client.get(_URL)
            if resp.status_code != 200:
                logger.warning("Dhan scrip master HTTP %s — using stale cache", resp.status_code)
                # fall back to whatever is on disk (even if stale)
                stale = _load_from_disk()
                if stale:
                    _cache_rows = stale
                return _cache_rows
            _save_to_disk(resp.text)
            rows = list(csv.DictReader(io.StringIO(resp.text)))
            _cache_rows = rows
            _cache_ts   = time.time()
            logger.info("Dhan scrip master downloaded and cached: %d rows", len(rows))
            return rows
        except Exception as exc:
            logger.warning("Dhan scrip master download failed: %s — using stale cache", exc)
            stale = _load_from_disk()
            if stale:
                _cache_rows = stale
            return _cache_rows


async def preload() -> None:
    """Eagerly populate the scrip-master cache at startup.

    Called from the FastAPI lifespan so the first user request never has to
    wait for the CSV download.  Safe to call multiple times — the lock
    prevents duplicate downloads.
    """
    rows = await _get_rows()
    logger.info("Dhan scrip master pre-warm complete: %d rows", len(rows))


def _filter_rows(rows: list[dict], symbol: str) -> list[dict]:
    """Return option rows for a symbol (OPTIDX or OPTSTK, matching exchange+prefix)."""
    info    = _sym_info(symbol)
    exch    = info["exch"]
    prefix  = info["prefix"].upper() + "-"
    result  = []
    for row in rows:
        if row.get("SEM_EXM_EXCH_ID", "").strip() != exch:
            continue
        if row.get("SEM_INSTRUMENT_NAME", "").strip() not in ("OPTIDX", "OPTSTK"):
            continue
        if not row.get("SEM_TRADING_SYMBOL", "").strip().upper().startswith(prefix):
            continue
        result.append(row)
    return result


# ── Public API ────────────────────────────────────────────────────────────────

async def get_expiry_dates(symbol: str) -> list[str]:
    """Return sorted list of future expiry dates in DD-Mon-YYYY format.

    Includes today's expiry (if trading is still ongoing) and all future
    ones. Stale/expired contracts are excluded.
    """
    rows    = await _get_rows()
    matched = _filter_rows(rows, symbol)
    if not matched:
        return []

    now = datetime.now()
    seen: set[str] = set()
    for row in matched:
        exp = _parse_expiry(row.get("SEM_EXPIRY_DATE", ""))
        if exp:
            seen.add(exp)

    future = [e for e in seen
              if datetime.strptime(e, "%d-%b-%Y") >= now.replace(hour=0, minute=0, second=0, microsecond=0)]
    future.sort(key=lambda x: datetime.strptime(x, "%d-%b-%Y"))
    return future


async def get_strikes(symbol: str, expiry_date: str) -> list[float]:
    """Return sorted list of available strike prices for a symbol+expiry."""
    rows    = await _get_rows()
    matched = _filter_rows(rows, symbol)
    if not matched:
        return []

    ymd = _expiry_to_ymd(expiry_date)
    if not ymd:
        return []

    strikes: set[float] = set()
    for row in matched:
        if row.get("SEM_EXPIRY_DATE", "")[:10] != ymd:
            continue
        try:
            k = float(row.get("SEM_STRIKE_PRICE", "0") or "0")
            if k > 0:
                strikes.add(k)
        except (ValueError, TypeError):
            pass

    return sorted(strikes)


async def get_lot_size(symbol: str) -> Optional[int]:
    """Return the lot size for a symbol, or None if not found."""
    rows    = await _get_rows()
    matched = _filter_rows(rows, symbol)
    for row in matched:
        try:
            lot = float(row.get("SEM_LOT_UNITS", "0") or "0")
            if lot > 0:
                return int(lot)
        except (ValueError, TypeError):
            pass
    return None
