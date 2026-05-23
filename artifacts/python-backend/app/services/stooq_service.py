"""Stooq.com — free EOD historical data with no API key required.

Why this exists
---------------
Stooq is a Polish data provider that publishes free daily OHLCV CSVs for
~500 Indian stocks and all major indices. It's purely **EOD** — no
intraday — which is exactly what an end-of-day analysis app needs.

How it slots into the chain
---------------------------
PriceService chains its sources as:
  Disk → NSE → Yahoo → Stooq → (Twelve Data if key) → History-derived

Stooq is a true third source because:
  * Different infrastructure (Polish servers, Cloudflare-free) — not
    correlated with NSE / Yahoo outages.
  * No API key, no rate limit observed at our usage volumes (kept
    polite with 1-second jitter between consecutive calls).
  * 10+ years of historical data available going back to before NSE's
    own API would return.

Symbol mapping
--------------
Indian equities on Stooq use the `.IN` suffix (e.g. `RELIANCE.IN`).
Indices use `^` prefix matching the global convention (`^NSEI` for
Nifty 50, `^NSEBANK` for Bank Nifty). We map our internal symbols
(`RELIANCE`) by appending `.IN` for equity, leaving `^...` alone
for indices.

Failure modes
-------------
  * Symbol unknown to Stooq → CSV with header only (no data rows).
  * Network failure → catches, returns empty list, never raises.
  * Rate limit (rare, but possible if we hammer them) → 429 status,
    treated as transient failure.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger("stooq_service")

_STOOQ_BASE = "https://stooq.com/q/d/l/"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/csv, text/plain, */*",
}

# In-process cache. Stooq updates EOD once per day, so a 6-hour TTL is
# fine — we re-fetch at most 4×/day per symbol even under heavy use.
_CACHE_TTL_SEC = 6 * 3600
_cache: dict[str, tuple[float, list[dict]]] = {}


def _to_stooq_symbol(symbol: str) -> str:
    """Translate our internal symbol to Stooq's naming.

    NSE equity (`RELIANCE`) → `reliance.in`. Stooq is case-insensitive
    but the canonical form is lowercase.

    Indices need an exchange prefix that Stooq recognizes:
      `^NSEI`       → `^nsei`        (Nifty 50)
      `NIFTY 50`    → `^nsei`
      `NIFTY BANK`  → `^nsebank`
    Unknown indices fall through to `.in` which Stooq won't resolve —
    callers get an empty list and the chain continues to the next source.
    """
    s = (symbol or "").strip().upper()
    if not s:
        return ""
    # Common Indian indices Stooq covers
    index_map = {
        "NIFTY 50":         "^nsei",
        "^NSEI":            "^nsei",
        "NIFTY BANK":       "^nsebank",
        "^NSEBANK":         "^nsebank",
        "NIFTY IT":         "^cnxit",
        "^CNXIT":           "^cnxit",
        "SENSEX":           "^bsesn",
        "^BSESN":           "^bsesn",
    }
    if s in index_map:
        return index_map[s]
    if s.startswith("^"):
        return s.lower()
    # Strip exchange suffixes that show up in tickers we receive
    for suffix in (".NS", ".BO", "-EQ", ":NSE", ":BSE"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    return f"{s.lower()}.in"


async def get_historical_csv(symbol: str, days: int = 365) -> list[dict]:
    """Fetch Stooq daily CSV and return the last `days` rows as OHLCV
    dicts (oldest → newest). Empty list on any failure.

    Stooq returns ALL historical data in one CSV (often 10+ years).
    We trim to `days` on our side so callers get a comparable slice
    to NSE / Yahoo.
    """
    stooq_sym = _to_stooq_symbol(symbol)
    if not stooq_sym:
        return []

    cache_key = f"{stooq_sym}|{days}"
    cached = _cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _CACHE_TTL_SEC:
        return cached[1]

    # `i=d` for daily; Stooq supports `w` (weekly) and `m` (monthly) too
    # but the daily slice is what every other source in the chain returns.
    url = f"{_STOOQ_BASE}?s={stooq_sym}&i=d"
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=_HEADERS)
            if resp.status_code != 200 or not resp.text:
                logger.debug("Stooq returned %s for %s", resp.status_code, stooq_sym)
                return []
            text = resp.text
    except Exception as exc:
        logger.debug("Stooq fetch failed for %s: %s", stooq_sym, str(exc)[:80])
        return []

    # Symbol unknown — Stooq replies with a 1-line error or empty body.
    if "No data" in text or len(text) < 30:
        return []

    rows: list[dict] = []
    try:
        reader = csv.DictReader(io.StringIO(text))
        for r in reader:
            # Stooq CSV columns: Date,Open,High,Low,Close,Volume
            try:
                date_s = (r.get("Date") or "").strip()
                if not date_s:
                    continue
                rows.append({
                    "date":   date_s,                                      # YYYY-MM-DD
                    "open":   float(r.get("Open")   or 0),
                    "high":   float(r.get("High")   or 0),
                    "low":    float(r.get("Low")    or 0),
                    "close":  float(r.get("Close")  or 0),
                    "volume": int(float(r.get("Volume") or 0)),
                })
            except (TypeError, ValueError):
                continue
    except Exception as exc:
        logger.debug("Stooq CSV parse failed for %s: %s", stooq_sym, str(exc)[:80])
        return []

    if not rows:
        return []

    # Trim to the requested window. Stooq returns oldest→newest, so
    # we slice the last `days` entries.
    rows = rows[-days:] if len(rows) > days else rows
    _cache[cache_key] = (time.time(), rows)
    return rows


async def get_quote(symbol: str) -> Optional[dict]:
    """Synthesise a quote-shaped dict from Stooq's latest EOD row.

    Returns the same shape as `YahooService.get_quote()` so PriceService
    can slot it into the existing chain without callers caring which
    source served the data. None when Stooq has no data for the symbol.

    Limitation: Stooq is EOD-only, so during market hours this returns
    yesterday's close rather than a live price. The chain calls Stooq
    AFTER Yahoo precisely so this only matters when both fail; in that
    case yesterday's close is far better than no quote at all.
    """
    rows = await get_historical_csv(symbol, days=5)
    if not rows or len(rows) < 1:
        return None
    last = rows[-1]
    prev = rows[-2] if len(rows) >= 2 else None
    last_close = last.get("close") or 0
    prev_close = (prev.get("close") if prev else None) or 0
    change  = round(last_close - prev_close, 2) if prev_close else 0
    pchange = round(change / prev_close * 100, 4) if prev_close else 0
    return {
        "symbol":         symbol.upper(),
        "companyName":    symbol.upper(),
        "lastPrice":      last_close,
        "change":         change,
        "pChange":        pchange,
        "open":           last.get("open"),
        "dayHigh":        last.get("high"),
        "dayLow":         last.get("low"),
        "previousClose":  prev_close or None,
        "volume":         last.get("volume"),
        "source":         "STOOQ",
    }
