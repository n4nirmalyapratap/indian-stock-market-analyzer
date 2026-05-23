"""Angel One SmartAPI client — BYO-key broker integration.

Required creds:
  {
    "api_key":     "<SmartAPI app key>",
    "client_id":   "<your Angel client ID>",
    "pwd":         "<trading PIN/password>",   # NOT the login PIN
    "totp_secret": "<base32 secret from SmartAPI portal>",
  }

Auth model
----------
Angel One requires a TOTP-protected login on every session: POST
`/rest/auth/angelbroking/user/v1/loginByPassword` with `clientcode`,
`password`, and a fresh 6-digit `totp` code. The response gives a
short-lived `jwtToken` (~8 hours) that authenticates subsequent
data calls.

We don't cache the JWT here — every call re-logs-in. That's wasteful
during heavy use but keeps Phase 7 simple; Phase 9 can add an
in-process token cache keyed by (user_id, broker) when wired into
PriceService.

TOTP generation uses stdlib only (hmac + struct) — no `pyotp` dep needed.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import struct
import time as _time
from typing import Optional

import httpx

logger = logging.getLogger("angel_one_service")

_BASE = "https://apiconnect.angelone.in"
_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)

# Common headers Angel One requires on every call. Some are obviously
# bogus (`X-MACAddress` / `X-PrivateKey`) but they're required by the
# upstream API per their docs; sending fixed placeholders is fine.
def _common_headers(api_key: str, jwt: str | None = None) -> dict:
    h = {
        "X-PrivateKey":   api_key,
        "Accept":         "application/json",
        "X-SourceID":     "WEB",
        "X-ClientLocalIP": "127.0.0.1",
        "X-ClientPublicIP": "127.0.0.1",
        "X-MACAddress":   "00:00:00:00:00:00",
        "X-UserType":     "USER",
        "Content-Type":   "application/json",
    }
    if jwt:
        h["Authorization"] = f"Bearer {jwt}"
    return h


# ── Seed map: NSE ticker → Angel One symbol token ────────────────────────
_NSE_TO_ANGEL_TOKEN: dict[str, str] = {
    "RELIANCE":  "2885",  "TCS":      "11536", "HDFCBANK":  "1333",
    "INFY":      "1594",  "ICICIBANK":"4963",  "HINDUNILVR":"1394",
    "ITC":       "1660",  "SBIN":     "3045",  "BHARTIARTL":"10604",
    "KOTAKBANK": "1922",  "BAJFINANCE":"317",  "AXISBANK":  "5900",
    "ASIANPAINT":"236",   "MARUTI":   "10999", "HCLTECH":   "7229",
    "WIPRO":     "3787",  "TITAN":    "3506",  "NTPC":      "11630",
    "SUNPHARMA": "3351",  "TATAMOTORS":"3456", "LT":        "11483",
    "COALINDIA": "20374", "BAJAJ-AUTO":"16669","DIVISLAB":  "10940",
    "CIPLA":     "694",   "DRREDDY":  "881",   "TECHM":     "13538",
    "HINDALCO":  "1363",  "ONGC":     "2475",  "POWERGRID": "14977",
    "JSWSTEEL":  "11723", "INDUSINDBK":"5258", "ULTRACEMCO":"11532",
    "NESTLEIND": "17963", "TATACONSUM":"3432", "ADANIPORTS":"15083",
    "BRITANNIA": "547",   "APOLLOHOSP":"157",  "BPCL":      "526",
    "TATASTEEL": "3499",  "ADANIENT": "25",    "EICHERMOT": "910",
    "HEROMOTOCO":"1348",  "GRASIM":   "1232",  "HAVELLS":   "9819",
    "SBILIFE":   "21808", "HDFCLIFE": "467",
}


def _generate_totp(secret_b32: str) -> Optional[str]:
    """Stdlib TOTP — no pyotp dependency.

    Returns the 6-digit code as a zero-padded string, or None when the
    secret can't be base32-decoded. Time-step = 30s (RFC 6238 default
    and what every authenticator app uses).
    """
    if not secret_b32:
        return None
    try:
        # Some users paste secrets with spaces / lowercase. Normalize.
        cleaned = secret_b32.upper().replace(" ", "").replace("-", "")
        # Pad to a multiple of 8 if needed (base32 requires padding).
        pad_len = (8 - len(cleaned) % 8) % 8
        cleaned += "=" * pad_len
        key = base64.b32decode(cleaned)
    except Exception as exc:
        logger.debug("TOTP base32 decode failed: %s", str(exc)[:80])
        return None
    counter = struct.pack(">Q", int(_time.time()) // 30)
    h = hmac.new(key, counter, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{code % 1_000_000:06d}"


async def _login(creds: dict) -> tuple[Optional[str], Optional[str]]:
    """Perform Angel One TOTP login, return (jwt_token, error_message).

    On success returns (jwt, None). On failure returns (None, message).
    """
    api_key      = (creds.get("api_key")    or "").strip()
    client_id    = (creds.get("client_id")  or "").strip()
    pwd          = (creds.get("pwd")        or "").strip()
    totp_secret  = (creds.get("totp_secret")or "").strip()
    if not all([api_key, client_id, pwd, totp_secret]):
        return None, "Missing required field (api_key / client_id / pwd / totp_secret)."

    totp = _generate_totp(totp_secret)
    if not totp:
        return None, "Could not generate TOTP — totp_secret must be a base32 string."

    body = {"clientcode": client_id, "password": pwd, "totp": totp}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_BASE}/rest/auth/angelbroking/user/v1/loginByPassword",
                json=body,
                headers=_common_headers(api_key),
            )
    except Exception as exc:
        return None, f"Network error: {str(exc)[:120]}"

    if resp.status_code != 200:
        return None, f"Angel One returned HTTP {resp.status_code}."
    try:
        data = resp.json()
    except Exception:
        return None, "Non-JSON response from Angel One."
    if not isinstance(data, dict) or not data.get("status"):
        return None, str(data.get("message") or "Login failed (unknown error).")[:200]
    jwt = (data.get("data") or {}).get("jwtToken") or ""
    if not jwt:
        return None, "Login succeeded but no JWT returned."
    return jwt, None


async def test_connection(creds: dict) -> tuple[bool, str]:
    """Login → fetch /user/profile to confirm the JWT works end-to-end."""
    jwt, err = await _login(creds)
    if not jwt:
        return False, err or "Login failed."
    api_key = (creds.get("api_key") or "").strip()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_BASE}/rest/secure/angelbroking/user/v1/getProfile",
                headers=_common_headers(api_key, jwt),
            )
            if resp.status_code != 200:
                return False, f"Profile fetch returned HTTP {resp.status_code}."
            data = resp.json()
    except Exception as exc:
        return False, f"Profile fetch error: {str(exc)[:120]}"
    if isinstance(data, dict) and data.get("status"):
        name = (data.get("data") or {}).get("name") or "(unknown)"
        return True, f"Connected as {name}."
    return False, "Login OK but profile fetch failed."


async def get_quote(symbol: str, creds: dict) -> Optional[dict]:
    sym = (symbol or "").strip().upper()
    token = _NSE_TO_ANGEL_TOKEN.get(sym)
    if not token:
        return None
    jwt, _ = await _login(creds)
    if not jwt:
        return None
    api_key = (creds.get("api_key") or "").strip()
    body = {"exchange": "NSE", "tradingsymbol": f"{sym}-EQ", "symboltoken": token}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_BASE}/rest/secure/angelbroking/order/v1/getLtpData",
                json=body,
                headers=_common_headers(api_key, jwt),
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
    except Exception as exc:
        logger.debug("Angel One get_quote failed: %s", str(exc)[:120])
        return None
    if not isinstance(data, dict) or not data.get("status"):
        return None
    d = data.get("data") or {}
    try:
        last_f = float(d.get("ltp") or 0)
        prev_f = float(d.get("close") or 0)
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
        "open":           float(d.get("open"))  if d.get("open")  else None,
        "dayHigh":        float(d.get("high"))  if d.get("high")  else None,
        "dayLow":         float(d.get("low"))   if d.get("low")   else None,
        "previousClose":  prev_f or None,
        "volume":         None,
        "source":         "ANGEL_ONE",
    }


async def get_historical(symbol: str, days: int = 90, creds: dict | None = None) -> list[dict]:
    if not creds:
        return []
    sym = (symbol or "").strip().upper()
    token = _NSE_TO_ANGEL_TOKEN.get(sym)
    if not token:
        return []
    jwt, _ = await _login(creds)
    if not jwt:
        return []
    api_key = (creds.get("api_key") or "").strip()
    from datetime import date, timedelta  # noqa: PLC0415
    today = date.today()
    body = {
        "exchange":    "NSE",
        "symboltoken": token,
        "interval":    "ONE_DAY",
        "fromdate":    (today - timedelta(days=days + 7)).strftime("%Y-%m-%d 09:15"),
        "todate":      today.strftime("%Y-%m-%d 15:30"),
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_BASE}/rest/secure/angelbroking/historical/v1/getCandleData",
                json=body,
                headers=_common_headers(api_key, jwt),
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
    except Exception:
        return []
    candles = (data or {}).get("data") or []
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
