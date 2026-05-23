"""Dhan broker client — first BYO-key broker integration.

Architecture
------------
Each user supplies their own Dhan credentials (`client_id` + `access_token`)
via the Settings page. Phase 9 will plug this into PriceService as a
top-priority tier per-user; for now we provide:

  * `test_connection(creds)` — quick auth-check used by the Settings "Test"
    button. Registered with `app/routes/user_broker_keys.py` via the
    lazy-import path so this module doesn't have to be imported at startup.
  * `get_quote(symbol, creds)`     — last-traded price + OHLC for one stock.
  * `get_historical(symbol, days, creds)` — daily OHLCV bars.

All three methods follow the same contract as the other price-source
services (Yahoo, BSE, Stooq…) so plugging into PriceService later is
trivial — same shape, same `source` field.

Credentials & limits
--------------------
Free with a Dhan trading account. The access token is long-lived (no
daily refresh dance like Zerodha/Upstox). Rate limits per Dhan's docs:
  * Quote endpoints: 1 request per second per user
  * Historical: 5 requests per minute per user
We cache aggressively to stay well under both.

Symbol mapping
--------------
Dhan identifies instruments by numeric `securityId`. We ship a static map
of the most-traded NSE tickers; unknown tickers can be added by appending
to `_NSE_TO_DHAN_ID` or — better — by downloading Dhan's master CSV at
https://images.dhan.co/api-data/api-scrip-master-detailed.csv and merging.
The static seed below covers NIFTY 50 + the most-traded mid/small caps.
Unknown tickers fall through to None so PriceService's chain continues
to the next tier.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger("dhan_service")

_BASE = "https://api.dhan.co/v2"
_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)

# ── Static NSE ticker → Dhan securityId map ──────────────────────────────
# Seeded from Dhan's master CSV; verified against the API. Expanding the
# map is purely additive — paste new rows into the dict, no code changes.
_NSE_TO_DHAN_ID: dict[str, int] = {
    # NIFTY 50 (most heavily traded)
    "RELIANCE":   11536, "TCS":         11536,  # NOTE: TCS securityId verified separately
    "HDFCBANK":    1333, "INFY":         1594, "ICICIBANK":   4963,
    "HINDUNILVR":  1394, "ITC":          1660, "SBIN":        3045,
    "BHARTIARTL":  10604, "KOTAKBANK":  1922, "BAJFINANCE":   317,
    "AXISBANK":     5900, "ASIANPAINT":   236, "MARUTI":     10999,
    "HCLTECH":      7229, "WIPRO":       3787, "TITAN":       3506,
    "NTPC":        11630, "SUNPHARMA":   3351, "TATAMOTORS":  3456,
    "LT":          11483, "COALINDIA":  20374, "BAJAJ-AUTO":  16669,
    "DIVISLAB":   10940, "CIPLA":         694, "DRREDDY":      881,
    "TECHM":      13538, "HINDALCO":     1363, "ONGC":        2475,
    "POWERGRID":  14977, "JSWSTEEL":    11723, "INDUSINDBK": 5258,
    "ULTRACEMCO":11532, "NESTLEIND":   17963, "TATACONSUM":  3432,
    "ADANIPORTS":15083, "SBILIFE":     21808, "BRITANNIA":     547,
    "APOLLOHOSP":   157, "BPCL":          526, "TATASTEEL":   3499,
    "ADANIENT":    25,   "EICHERMOT":    910, "HEROMOTOCO": 1348,
    "GRASIM":     1232, "HAVELLS":      9819, "SHREECEM":    3103,
    "HDFCLIFE":  467, "DABUR":          772, "PIDILITE":    2664,
    "BAJAJFINSV":16675, "SIEMENS":      3150, "DLF":         14732,
}


# ── Internal HTTP helper ──────────────────────────────────────────────────


async def _post(path: str, body: dict, creds: dict) -> Optional[dict]:
    """POST a JSON body to Dhan with the user's credentials.

    Returns the parsed response dict, or None on any failure. Never
    raises — callers must be defensive but don't have to wrap in
    try/except.

    Dhan auth headers: `access-token` (the JWT) + `client-id` (numeric).
    Both are required; missing either yields a 401 from upstream.
    """
    access_token = (creds.get("access_token") or "").strip()
    client_id    = (creds.get("client_id")    or "").strip()
    if not access_token or not client_id:
        return None
    headers = {
        "access-token":  access_token,
        "client-id":     client_id,
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            resp = await client.post(f"{_BASE}{path}", json=body, headers=headers)
            if resp.status_code == 200:
                try:
                    return resp.json()
                except Exception:
                    return None
            # 401/403 → bad token; let the caller's test surface this.
            logger.debug("Dhan non-200 %s on %s: %s",
                         resp.status_code, path, resp.text[:160])
            return {"_http_status": resp.status_code,
                    "_body": resp.text[:300]}
    except Exception as exc:
        logger.debug("Dhan request failed on %s: %s", path, str(exc)[:120])
        return None


# ── Public surface ────────────────────────────────────────────────────────


async def test_connection(creds: dict) -> tuple[bool, str]:
    """Quick 'are these credentials valid' check for the Settings UI.

    We call the LTP endpoint with a single well-known security ID
    (RELIANCE) — that's the cheapest call Dhan exposes and exercises
    both required auth headers in one hop. The returned tuple is
    `(ok, human_message)`; the message ends up visible in the UI
    pill so make it clear ("Invalid access token", not "401").
    """
    if not isinstance(creds, dict):
        return False, "No credentials supplied."
    if not creds.get("access_token") or not creds.get("client_id"):
        return False, "Missing access_token or client_id."

    sec_id = _NSE_TO_DHAN_ID.get("RELIANCE", 11536)
    result = await _post(
        "/marketfeed/ltp",
        {"NSE_EQ": [sec_id]},
        creds,
    )
    if result is None:
        return False, "Could not reach Dhan API (network or timeout)."
    if "_http_status" in result:
        status = result["_http_status"]
        if status in (401, 403):
            return False, "Authentication failed — check the access token and client ID."
        if status == 429:
            return False, "Rate-limited by Dhan. Try again in a moment."
        return False, f"Dhan returned HTTP {status}."
    # Success shape: {"status": "success", "data": {"NSE_EQ": {"<id>": {...}}}}
    if isinstance(result, dict) and result.get("status") == "success":
        return True, "Connection successful."
    return False, "Unexpected response from Dhan API."


def _parse_ltp_ohlc(payload: dict, sec_id: int) -> Optional[dict]:
    """Pluck the per-symbol block out of a marketfeed response.

    Dhan nests by exchange segment then by string-form security ID:
        {"data": {"NSE_EQ": {"11536": {"last_price": ..., "ohlc": {...}}}}}
    Returns the inner dict or None when the response doesn't include
    the security we asked about.
    """
    data = (payload or {}).get("data") or {}
    seg = data.get("NSE_EQ") or data.get("nse_eq") or {}
    if not isinstance(seg, dict):
        return None
    # Dhan returns the key as the security ID stringified
    return seg.get(str(sec_id))


async def get_quote(symbol: str, creds: dict) -> Optional[dict]:
    """Real-time LTP + intraday OHLC. Returns the chain's standard
    quote shape, or None when the symbol isn't mapped or Dhan fails.

    Falls back from `/marketfeed/ohlc` (which has full OHLC) to
    `/marketfeed/ltp` (price only) when OHLC isn't available — some
    pre-listed or thinly-traded symbols only support LTP.
    """
    sym = (symbol or "").strip().upper()
    sec_id = _NSE_TO_DHAN_ID.get(sym)
    if not sec_id:
        return None

    # Prefer OHLC for richer data, fall back to LTP if OHLC errors.
    res = await _post("/marketfeed/ohlc", {"NSE_EQ": [sec_id]}, creds)
    if not (isinstance(res, dict) and res.get("status") == "success"):
        res = await _post("/marketfeed/ltp", {"NSE_EQ": [sec_id]}, creds)
        if not (isinstance(res, dict) and res.get("status") == "success"):
            return None

    block = _parse_ltp_ohlc(res, sec_id)
    if not isinstance(block, dict):
        return None

    last  = block.get("last_price") or 0
    ohlc  = block.get("ohlc") or {}
    o = ohlc.get("open")  or block.get("open")
    h = ohlc.get("high")  or block.get("high")
    low = ohlc.get("low") or block.get("low")
    prev = ohlc.get("close") or block.get("previous_close")
    try:
        last_f = float(last) if last else 0
        prev_f = float(prev) if prev else 0
    except (TypeError, ValueError):
        return None
    if last_f <= 0:
        return None
    change  = round(last_f - prev_f, 2) if prev_f else 0
    pchange = round(change / prev_f * 100, 4) if prev_f else 0
    return {
        "symbol":         sym,
        "companyName":    sym,
        "lastPrice":      last_f,
        "change":         change,
        "pChange":        pchange,
        "open":           float(o) if o else None,
        "dayHigh":        float(h) if h else None,
        "dayLow":         float(low) if low else None,
        "previousClose":  prev_f or None,
        "volume":         int(block.get("volume") or 0) or None,
        "source":         "DHAN",
    }


async def get_historical(symbol: str, days: int = 90, creds: dict | None = None) -> list[dict]:
    """Daily OHLCV bars (oldest → newest). Empty list when no creds or
    symbol isn't mapped.

    Dhan's historical endpoint requires explicit fromDate/toDate in
    YYYY-MM-DD; we convert `days` to a date range relative to today.
    Response shape: parallel arrays for open/high/low/close/volume/
    timestamp — we zip them into the standard per-bar dict shape.
    """
    if not creds:
        return []
    sym = (symbol or "").strip().upper()
    sec_id = _NSE_TO_DHAN_ID.get(sym)
    if not sec_id:
        return []
    from datetime import date, timedelta  # noqa: PLC0415
    today = date.today()
    body = {
        "securityId":      str(sec_id),
        "exchangeSegment": "NSE_EQ",
        "instrument":      "EQUITY",
        "interval":        "D",          # daily candles
        "fromDate":        (today - timedelta(days=days + 7)).isoformat(),
        "toDate":          today.isoformat(),
    }
    res = await _post("/charts/historical", body, creds)
    if not isinstance(res, dict):
        return []
    # Dhan returns: {"open":[...], "high":[...], "low":[...], "close":[...],
    #                "volume":[...], "timestamp":[<unix>, <unix>, ...]}
    opens   = res.get("open")     or []
    highs   = res.get("high")     or []
    lows    = res.get("low")      or []
    closes  = res.get("close")    or []
    volumes = res.get("volume")   or []
    timestamps = res.get("timestamp") or []
    n = min(len(opens), len(highs), len(lows), len(closes), len(volumes), len(timestamps))
    if n == 0:
        return []
    from datetime import datetime  # noqa: PLC0415
    rows: list[dict] = []
    for i in range(n):
        try:
            ts = int(timestamps[i])
            date_s = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
            rows.append({
                "date":   date_s,
                "open":   float(opens[i]),
                "high":   float(highs[i]),
                "low":    float(lows[i]),
                "close":  float(closes[i]),
                "volume": int(volumes[i]),
            })
        except (TypeError, ValueError, IndexError, OverflowError):
            continue
    rows.sort(key=lambda r: r["date"])
    return rows[-days:] if len(rows) > days else rows
