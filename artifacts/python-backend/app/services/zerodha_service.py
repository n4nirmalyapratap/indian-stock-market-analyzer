"""Zerodha Kite Connect client — BYO-key broker integration.

Same shape as `dhan_service.py`. Exposes:
  * `test_connection(creds)` — checks the access_token via /user/profile
  * `get_quote(symbol, creds)` — last-traded price + OHLC
  * `get_historical(symbol, days, creds)` — daily candles

Auth quirks
-----------
Kite Connect access tokens **expire every day at ~6 AM IST**. There's no
refresh token. Users must re-run the login flow and update their key in
Settings each day. Test connection fails with "Token expired" → that's
the user's cue.

Required creds dict:
  {
    "api_key":      "<your Kite API key>",
    "api_secret":   "<your Kite API secret>",  # currently unused — held for completeness
    "access_token": "<today's daily token>",
  }

Kite REST headers
  Authorization: token <api_key>:<access_token>
  X-Kite-Version: 3
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger("zerodha_service")

_BASE = "https://api.kite.trade"
_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)

# Seed map: NSE ticker → Kite instrument_token. Long tail can be added
# from Kite's `/instruments` CSV (15K+ rows). Phase 9 will need a CSV
# loader if the user trades names outside this map; for the Settings
# UI's test_connection (which uses /user/profile) this map isn't needed.
_NSE_TO_KITE_TOKEN: dict[str, int] = {
    "RELIANCE":  738561,  "TCS":       2953217, "HDFCBANK":   341249,
    "INFY":      408065,  "ICICIBANK": 1270529, "HINDUNILVR": 356865,
    "ITC":       424961,  "SBIN":      779521,  "BHARTIARTL": 2714625,
    "KOTAKBANK": 492033,  "BAJFINANCE":81153,   "AXISBANK":   1510401,
    "ASIANPAINT":60417,   "MARUTI":    2815745, "HCLTECH":    1850625,
    "WIPRO":     969473,  "TITAN":     897537,  "NTPC":       2977281,
    "SUNPHARMA": 857857,  "TATAMOTORS":884737,  "LT":         2939649,
    "COALINDIA": 5215745, "BAJAJ-AUTO":4267265, "DIVISLAB":   2800641,
    "CIPLA":     177665,  "DRREDDY":   225537,  "TECHM":      3465729,
    "HINDALCO":  348929,  "ONGC":      633601,  "POWERGRID":  3834113,
    "JSWSTEEL":  3001089, "INDUSINDBK":1346049, "ULTRACEMCO": 2952193,
    "NESTLEIND": 4598529, "TATACONSUM":878593,  "ADANIPORTS": 3861249,
    "BRITANNIA": 140033,  "APOLLOHOSP":40193,   "BPCL":       134657,
    "TATASTEEL": 895745,  "ADANIENT":  6401,    "EICHERMOT":  232961,
    "HEROMOTOCO":345089,  "GRASIM":    315393,  "HAVELLS":    2513665,
    "SBILIFE":   5582849, "HDFCLIFE":  119553,
}


def _auth_headers(creds: dict) -> Optional[dict]:
    api_key      = (creds.get("api_key")      or "").strip()
    access_token = (creds.get("access_token") or "").strip()
    if not api_key or not access_token:
        return None
    return {
        "Authorization":   f"token {api_key}:{access_token}",
        "X-Kite-Version":  "3",
        "Accept":          "application/json",
    }


async def _get(path: str, creds: dict, params: Optional[dict] = None) -> Optional[dict]:
    headers = _auth_headers(creds)
    if not headers:
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_BASE}{path}", params=params or {}, headers=headers)
            if resp.status_code == 200:
                try:
                    return resp.json()
                except Exception:
                    return None
            return {"_http_status": resp.status_code, "_body": resp.text[:240]}
    except Exception as exc:
        logger.debug("Kite GET %s failed: %s", path, str(exc)[:120])
        return None


async def test_connection(creds: dict) -> tuple[bool, str]:
    """Cheapest auth-check Kite exposes: /user/profile."""
    res = await _get("/user/profile", creds)
    if res is None:
        return False, "Could not reach Kite Connect API."
    if "_http_status" in res:
        s = res["_http_status"]
        if s == 403 or s == 401:
            return False, "Token expired or invalid. Kite tokens expire each day at ~6 AM IST — regenerate via the daily login flow."
        return False, f"Kite returned HTTP {s}."
    if isinstance(res, dict) and res.get("status") == "success":
        name = (res.get("data") or {}).get("user_name") or "(unknown)"
        return True, f"Connected as {name}."
    return False, "Unexpected response from Kite Connect."


async def get_quote(symbol: str, creds: dict) -> Optional[dict]:
    """Full quote via /quote — returns OHLC + LTP + volume."""
    sym = (symbol or "").strip().upper()
    token = _NSE_TO_KITE_TOKEN.get(sym)
    if not token:
        return None
    # Kite's /quote accepts either instrument_tokens or trading symbols.
    # We pass the trading-symbol form `NSE:RELIANCE` so we don't need to
    # keep token mappings in sync forever.
    res = await _get("/quote", creds, {"i": f"NSE:{sym}"})
    if not isinstance(res, dict) or res.get("status") != "success":
        return None
    block = (res.get("data") or {}).get(f"NSE:{sym}")
    if not isinstance(block, dict):
        return None
    last = block.get("last_price")
    ohlc = block.get("ohlc") or {}
    prev = ohlc.get("close")
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
        "open":           float(ohlc.get("open"))  if ohlc.get("open")  else None,
        "dayHigh":        float(ohlc.get("high"))  if ohlc.get("high")  else None,
        "dayLow":         float(ohlc.get("low"))   if ohlc.get("low")   else None,
        "previousClose":  prev_f or None,
        "volume":         int(block.get("volume") or 0) or None,
        "source":         "ZERODHA",
    }


async def get_historical(symbol: str, days: int = 90, creds: dict | None = None) -> list[dict]:
    """Daily candles via /instruments/historical/{token}/day."""
    if not creds:
        return []
    sym = (symbol or "").strip().upper()
    token = _NSE_TO_KITE_TOKEN.get(sym)
    if not token:
        return []
    from datetime import date, timedelta  # noqa: PLC0415
    today = date.today()
    res = await _get(
        f"/instruments/historical/{token}/day",
        creds,
        {
            "from": (today - timedelta(days=days + 7)).isoformat(),
            "to":   today.isoformat(),
        },
    )
    if not isinstance(res, dict) or res.get("status") != "success":
        return []
    candles = ((res.get("data") or {}).get("candles") or [])
    rows: list[dict] = []
    for c in candles:
        # Each candle: [timestamp, open, high, low, close, volume]
        if not isinstance(c, list) or len(c) < 6:
            continue
        try:
            date_s = str(c[0])[:10]
            rows.append({
                "date":   date_s,
                "open":   float(c[1]),
                "high":   float(c[2]),
                "low":    float(c[3]),
                "close":  float(c[4]),
                "volume": int(c[5]),
            })
        except (TypeError, ValueError):
            continue
    rows.sort(key=lambda r: r["date"])
    return rows[-days:] if len(rows) > days else rows
