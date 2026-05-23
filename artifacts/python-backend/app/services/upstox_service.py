"""Upstox API v2 client — BYO-key broker integration.

Required creds:
  {
    "api_key":      "<your Upstox API key>",
    "api_secret":   "<your Upstox API secret>",  # currently unused; kept for completeness
    "access_token": "<today's daily token>",
  }

Like Zerodha, Upstox access tokens expire daily at 03:30 AM IST.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger("upstox_service")

_BASE = "https://api.upstox.com/v2"
_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)

# Seed map: NSE ticker → Upstox instrument_key ("NSE_EQ|ISIN") format.
# Full set comes from Upstox's `/instruments/complete` endpoint.
_NSE_TO_UPSTOX_KEY: dict[str, str] = {
    "RELIANCE":   "NSE_EQ|INE002A01018",  "TCS":        "NSE_EQ|INE467B01029",
    "HDFCBANK":   "NSE_EQ|INE040A01034",  "INFY":       "NSE_EQ|INE009A01021",
    "ICICIBANK":  "NSE_EQ|INE090A01021",  "HINDUNILVR": "NSE_EQ|INE030A01027",
    "ITC":        "NSE_EQ|INE154A01025",  "SBIN":       "NSE_EQ|INE062A01020",
    "BHARTIARTL": "NSE_EQ|INE397D01024",  "KOTAKBANK":  "NSE_EQ|INE237A01028",
    "BAJFINANCE": "NSE_EQ|INE296A01024",  "AXISBANK":   "NSE_EQ|INE238A01034",
    "ASIANPAINT": "NSE_EQ|INE021A01026",  "MARUTI":     "NSE_EQ|INE585B01010",
    "HCLTECH":    "NSE_EQ|INE860A01027",  "WIPRO":      "NSE_EQ|INE075A01022",
    "TITAN":      "NSE_EQ|INE280A01028",  "NTPC":       "NSE_EQ|INE733E01010",
    "SUNPHARMA":  "NSE_EQ|INE044A01036",  "TATAMOTORS": "NSE_EQ|INE155A01022",
    "LT":         "NSE_EQ|INE018A01030",  "COALINDIA":  "NSE_EQ|INE522F01014",
    "BAJAJ-AUTO": "NSE_EQ|INE917I01010",  "DIVISLAB":   "NSE_EQ|INE361B01024",
    "CIPLA":      "NSE_EQ|INE059A01026",  "DRREDDY":    "NSE_EQ|INE089A01023",
    "TECHM":      "NSE_EQ|INE669C01036",  "HINDALCO":   "NSE_EQ|INE038A01020",
    "ONGC":       "NSE_EQ|INE213A01029",  "POWERGRID":  "NSE_EQ|INE752E01010",
    "JSWSTEEL":   "NSE_EQ|INE019A01038",  "INDUSINDBK": "NSE_EQ|INE095A01012",
    "ULTRACEMCO": "NSE_EQ|INE481G01011",  "NESTLEIND":  "NSE_EQ|INE239A01016",
    "TATACONSUM": "NSE_EQ|INE192A01025",  "ADANIPORTS": "NSE_EQ|INE742F01042",
    "BRITANNIA":  "NSE_EQ|INE216A01030",  "APOLLOHOSP": "NSE_EQ|INE437A01024",
    "BPCL":       "NSE_EQ|INE029A01011",  "TATASTEEL":  "NSE_EQ|INE081A01020",
    "ADANIENT":   "NSE_EQ|INE423A01024",  "EICHERMOT":  "NSE_EQ|INE066A01021",
    "HEROMOTOCO": "NSE_EQ|INE158A01026",  "GRASIM":     "NSE_EQ|INE047A01021",
    "HAVELLS":    "NSE_EQ|INE176B01034",  "SBILIFE":    "NSE_EQ|INE123W01016",
    "HDFCLIFE":   "NSE_EQ|INE795G01014",
}


def _auth_headers(creds: dict) -> Optional[dict]:
    token = (creds.get("access_token") or "").strip()
    if not token:
        return None
    return {
        "Authorization": f"Bearer {token}",
        "Api-Version":   "2.0",
        "Accept":        "application/json",
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
        logger.debug("Upstox GET %s failed: %s", path, str(exc)[:120])
        return None


async def test_connection(creds: dict) -> tuple[bool, str]:
    res = await _get("/user/profile", creds)
    if res is None:
        return False, "Could not reach Upstox API."
    if "_http_status" in res:
        s = res["_http_status"]
        if s in (401, 403):
            return False, "Token expired or invalid. Upstox tokens expire daily — regenerate via the login flow."
        return False, f"Upstox returned HTTP {s}."
    if isinstance(res, dict) and (res.get("status") == "success" or "data" in res):
        name = ((res.get("data") or {}).get("user_name")
                or (res.get("data") or {}).get("name")
                or "(unknown)")
        return True, f"Connected as {name}."
    return False, "Unexpected response from Upstox."


async def get_quote(symbol: str, creds: dict) -> Optional[dict]:
    sym = (symbol or "").strip().upper()
    inst_key = _NSE_TO_UPSTOX_KEY.get(sym)
    if not inst_key:
        return None
    res = await _get("/market-quote/quotes", creds, {"instrument_key": inst_key})
    if not isinstance(res, dict) or res.get("status") != "success":
        return None
    # Response shape: {"data": {"<inst_key>": {ohlc, last_price, ...}}}
    block = None
    data = res.get("data") or {}
    if isinstance(data, dict):
        # Upstox sometimes returns the key with the original instrument_key
        # OR with a normalised form — try both.
        block = data.get(inst_key) or data.get(inst_key.replace("|", ":")) or next(iter(data.values()), None)
    if not isinstance(block, dict):
        return None

    last = block.get("last_price")
    ohlc = block.get("ohlc") or {}
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
        "open":           float(ohlc.get("open"))  if ohlc.get("open")  else None,
        "dayHigh":        float(ohlc.get("high"))  if ohlc.get("high")  else None,
        "dayLow":         float(ohlc.get("low"))   if ohlc.get("low")   else None,
        "previousClose":  prev_f or None,
        "volume":         int(block.get("volume") or 0) or None,
        "source":         "UPSTOX",
    }


async def get_historical(symbol: str, days: int = 90, creds: dict | None = None) -> list[dict]:
    if not creds:
        return []
    sym = (symbol or "").strip().upper()
    inst_key = _NSE_TO_UPSTOX_KEY.get(sym)
    if not inst_key:
        return []
    from datetime import date, timedelta  # noqa: PLC0415
    today = date.today()
    from_d = today - timedelta(days=days + 7)
    # Upstox historical-candle path: /historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}
    # `inst_key` already has a `|` — must be URL-encoded.
    from urllib.parse import quote  # noqa: PLC0415
    path = (f"/historical-candle/{quote(inst_key, safe='')}/day/"
            f"{today.isoformat()}/{from_d.isoformat()}")
    res = await _get(path, creds)
    if not isinstance(res, dict) or res.get("status") != "success":
        return []
    candles = ((res.get("data") or {}).get("candles") or [])
    rows: list[dict] = []
    for c in candles:
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
