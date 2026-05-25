"""
nse_service.py — NSE India data fetcher.

Techniques adapted from github.com/aeron7/nsepython (MIT):
  • Two-page session warm-up (homepage + /option-chain) before every API call
    so the WAF cookie jar is complete for both equity and derivatives endpoints.
  • Full browser-like headers (Connection, DNT, Upgrade-Insecure-Requests,
    Sec-Fetch-*, Cache-Control, Accept-Encoding) to pass Akamai bot checks.
  • New NextApi endpoints (?functionName=…) used for quotes, option chains,
    derivative quotes, and expiry lists — alongside the classic /api/* paths
    for historical data and sector indices.
  • Persistent httpx.AsyncClient with auto-cookie-jar so cookies propagate
    naturally across the warm-up requests.
  • Symbol purification (nsesymbolpurify equivalent) for clean URL encoding.
"""

import asyncio
import logging
import time
from typing import Any, Optional
from urllib.parse import quote as _url_quote
import httpx

logger = logging.getLogger(__name__)

from . import market_cache_service as _mcs

# ── In-memory response cache ──────────────────────────────────────────────────

MAX_ENTRIES = 200
_CACHE: dict[str, dict] = {}
_CACHE_VERSION = 0

# ── Shared persistent httpx client ───────────────────────────────────────────
# A single module-level client retains the cookie jar across requests — this is
# exactly what nsepython's requests.Session() achieves. The client is replaced
# on each cookie refresh so the jar is always clean.

_client: Optional[httpx.AsyncClient] = None
_cookie_expiry: float = 0.0
_refresh_lock = asyncio.Lock()

NSE_BASE = "https://www.nseindia.com"

# ── Headers (nsepython-style — full browser fingerprint) ─────────────────────

HEADERS_BROWSER = {
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Sec-Fetch-User": "?1",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.9"
    ),
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
}

HEADERS_API = {
    "Connection": "keep-alive",
    "DNT": "1",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "X-Requested-With": "XMLHttpRequest",
}

# ── Cache helpers ─────────────────────────────────────────────────────────────

def _flush_if_state_changed() -> None:
    global _CACHE_VERSION, _CACHE
    v = _mcs.cache_version()
    if v != _CACHE_VERSION:
        _CACHE.clear()
        _CACHE_VERSION = v


def _get_cache(key: str) -> Optional[Any]:
    _flush_if_state_changed()
    entry = _CACHE.get(key)
    if entry and time.time() < entry["expiry"]:
        return entry["data"]
    if entry:
        del _CACHE[key]
    return None


def _set_cache(key: str, data: Any, ttl: int) -> None:
    global _CACHE
    _flush_if_state_changed()
    if len(_CACHE) >= MAX_ENTRIES:
        now = time.time()
        expired = [k for k, v in _CACHE.items() if now > v["expiry"]]
        for k in expired:
            del _CACHE[k]
        if len(_CACHE) >= MAX_ENTRIES:
            oldest = next(iter(_CACHE))
            del _CACHE[oldest]
    _CACHE[key] = {"data": data, "expiry": time.time() + ttl}


def _ttl_for(default_ttl: int) -> int:
    if _mcs.is_market_open():
        return min(default_ttl, 60)
    return default_ttl


# ── Symbol helper (nsesymbolpurify equivalent) ───────────────────────────────

def _purify(symbol: str) -> str:
    """URL-encode symbol for NSE API URLs, preserving safe chars."""
    return _url_quote(symbol.strip().upper(), safe="")


# ── Session / cookie management ───────────────────────────────────────────────

async def _refresh_cookies() -> None:
    """
    Two-page warm-up — exactly what nsepython does in its Session-based mode:
      1. GET https://www.nseindia.com           (sets __utma, nseappid, …)
      2. GET https://www.nseindia.com/option-chain   (sets nsit, ak_bmsc, …)
    Using a persistent httpx.AsyncClient so cookies flow automatically.
    """
    global _client, _cookie_expiry
    try:
        new_client = httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers=HEADERS_BROWSER,
        )
        # Step 1 — homepage
        await new_client.get(f"{NSE_BASE}/")
        # Step 2 — option-chain page (nsepython's key insight: this page sets
        #           the derivatives-specific WAF cookies)
        await new_client.get(f"{NSE_BASE}/option-chain")

        # Replace the old client only after both warm-up pages succeed
        if _client:
            await _client.aclose()
        _client = new_client
        _cookie_expiry = time.time() + 20 * 60
        logger.debug("NSE cookies refreshed (two-page warm-up complete)")
    except Exception as exc:
        logger.warning("NSE cookie refresh failed: %s", exc)


async def _ensure_cookies() -> None:
    global _cookie_expiry
    if _client and time.time() < _cookie_expiry:
        return
    async with _refresh_lock:
        if _client and time.time() < _cookie_expiry:
            return
        await _refresh_cookies()


def _force_expire() -> None:
    global _cookie_expiry
    _cookie_expiry = 0.0


# ── Core JSON fetcher ─────────────────────────────────────────────────────────

class NseService:

    async def fetch_nse(
        self,
        path: str,
        cache_key: str,
        ttl: int = 300,
        retries: int = 3,
        referer: Optional[str] = None,
    ) -> Optional[Any]:
        """Fetch a JSON endpoint from nseindia.com with cookie auth + caching."""
        ttl = _ttl_for(ttl)
        cached = _get_cache(cache_key)
        if cached is not None:
            return cached

        headers = dict(HEADERS_API)
        if referer:
            headers["Referer"] = referer

        for attempt in range(retries):
            await _ensure_cookies()
            try:
                resp = await _client.get(f"{NSE_BASE}{path}", headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    _set_cache(cache_key, data, ttl)
                    return data
                elif resp.status_code in (401, 403):
                    _force_expire()
                    continue
                elif resp.status_code == 429:
                    await asyncio.sleep(2 ** attempt)
                    continue
                elif resp.status_code == 503:
                    # Akamai bot-challenge — force a fresh cookie warm-up
                    _force_expire()
                    await _ensure_cookies()
                    continue
            except Exception as exc:
                logger.debug("NSE fetch attempt %d failed: %s", attempt, exc)
                await asyncio.sleep(1)

        return None

    # ── Plain-text / CSV archive fetcher ────────────────────────────────────

    async def fetch_nse_archive_text(
        self,
        url: str,
        cache_key: str,
        ttl: int = 86400,
        retries: int = 2,
    ) -> Optional[str]:
        """Fetch a static-archive resource (CSV/text) from nsearchives."""
        cached = _get_cache(cache_key)
        if cached is not None:
            return cached

        headers = {
            "User-Agent": HEADERS_BROWSER["User-Agent"],
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.nseindia.com/all-reports-derivatives",
            "DNT": "1",
        }
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                    resp = await client.get(url, headers=headers)
                if resp.status_code == 200 and resp.text and len(resp.text) > 50:
                    _set_cache(cache_key, resp.text, ttl)
                    return resp.text
                if resp.status_code == 429:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None
            except Exception:
                await asyncio.sleep(1)
        return None

    # ── Sector / index helpers ────────────────────────────────────────────────

    def get_sector_indices(self):
        return self.fetch_nse("/api/allIndices", "sector-indices", 300)

    def get_stock_quote(self, symbol: str):
        encoded = _purify(symbol)
        return self.fetch_nse(
            f"/api/quote-equity?symbol={encoded}",
            f"quote-{symbol}",
            120,
            referer=f"{NSE_BASE}/get-quotes/equity?symbol={encoded}",
        )

    def get_nifty100(self):
        return self.fetch_nse(
            "/api/equity-stockIndices?index=NIFTY%20100",
            "nifty100",
            1800,
        )

    def get_nifty_midcap150(self):
        return self.fetch_nse(
            "/api/equity-stockIndices?index=NIFTY%20MIDCAP%20150",
            "midcap150",
            1800,
        )

    def get_nifty_smallcap250(self):
        return self.fetch_nse(
            "/api/equity-stockIndices?index=NIFTY%20SMALLCAP%20250",
            "smallcap250",
            1800,
        )

    # ── New NextApi — stock quote (nsepython's primary endpoint) ─────────────

    async def get_stock_quote_v2(self, symbol: str) -> Optional[dict]:
        """
        Fetch equity quote via NSE's new NextApi.
        Endpoint pattern used by nsepython:
          /api/NextApi/apiClient/GetQuoteApi
          ?functionName=getSymbolData&marketType=N&series=EQ&symbol=<SYM>

        Returns the raw NSE payload.  Falls back to classic quote-equity.
        """
        encoded = _purify(symbol)
        cache_key = f"quote-v2-{symbol}"
        cached = _get_cache(cache_key)
        if cached is not None:
            return cached

        path = (
            f"/api/NextApi/apiClient/GetQuoteApi"
            f"?functionName=getSymbolData&marketType=N&series=EQ&symbol={encoded}"
        )
        data = await self.fetch_nse(
            path,
            cache_key,
            ttl=_ttl_for(120),
            referer=f"{NSE_BASE}/get-quotes/equity?symbol={encoded}",
        )
        if data:
            return data
        # Fall back to classic endpoint
        return await self.get_stock_quote(symbol)

    # ── New NextApi — derivative quote ───────────────────────────────────────

    async def get_derivative_quote(self, symbol: str) -> Optional[dict]:
        """
        Fetch derivatives (F&O) quote for an index/stock via NextApi.
        Pattern: ?functionName=getDerivativeQuote&marketType=N&symbol=<SYM>
        """
        encoded = _purify(symbol)
        cache_key = f"deriv-quote-{symbol}"
        cached = _get_cache(cache_key)
        if cached is not None:
            return cached

        path = (
            f"/api/NextApi/apiClient/GetQuoteApi"
            f"?functionName=getDerivativeQuote&marketType=N&symbol={encoded}"
        )
        return await self.fetch_nse(
            path,
            cache_key,
            ttl=_ttl_for(60),
            referer=f"{NSE_BASE}/get-quotes/derivatives?symbol={encoded}",
        )

    # ── New NextApi — option chain ────────────────────────────────────────────

    async def get_option_chain(
        self,
        symbol: str,
        expiry_date: Optional[str] = None,
        instrument: str = "OPTIDX",
    ) -> Optional[dict]:
        """
        Fetch the live NSE option chain via the v3 endpoint (current, active
        replacement for the legacy /api/option-chain-indices path which was
        retired in 2024 and now returns 404).

        Endpoint: /api/option-chain-v3?type=<Indices|Equity>&symbol=<SYM>&expiry=<DD-Mon-YYYY>
        Returns:  Brotli-compressed JSON shaped as
                  { "records": { "underlyingValue": float, "expiryDates": [...], "data": [...] } }

        v3 requires an `expiry` query param. When omitted we probe for the
        expiry list, then fetch the nearest expiry's chain.

        instrument: "OPTIDX" for indices, "OPTSTK" for equity stocks.
        """
        import datetime as _dt
        encoded = _purify(symbol)
        type_q  = "Indices" if instrument == "OPTIDX" else "Equity"

        # If no expiry supplied, look up the nearest one first
        if not expiry_date:
            expiries = await self.get_expiry_list(symbol, instrument)
            if not expiries:
                logger.debug("No expiries found for %s; cannot fetch chain", symbol)
                return None
            expiry_date = expiries[0]

        # Strictly validate expiry_date format (DD-Mon-YYYY) — protects against
        # query-string injection and silent NSE 200/empty responses.
        try:
            _dt.datetime.strptime(expiry_date, "%d-%b-%Y")
        except (ValueError, TypeError):
            logger.warning("Invalid expiry_date %r for %s; expected DD-Mon-YYYY", expiry_date, symbol)
            return None

        cache_key = f"option-chain-v3-{type_q}-{symbol}-{expiry_date}"
        cached = _get_cache(cache_key)
        if cached is not None:
            return cached

        path = (
            f"/api/option-chain-v3?type={type_q}"
            f"&symbol={encoded}&expiry={_url_quote(expiry_date, safe='-')}"
        )
        data = await self.fetch_nse(
            path,
            cache_key,
            ttl=_ttl_for(60),
            referer=f"{NSE_BASE}/option-chain",
        )
        return data

    # ── New NextApi — expiry list ─────────────────────────────────────────────

    async def get_expiry_list(
        self,
        symbol: str,
        instrument: str = "OPTIDX",
    ) -> list[str]:
        """
        Return a sorted list of expiry date strings (format: "DD-Mon-YYYY")
        via the v3 option-chain endpoint. A probe call with a far-future
        placeholder expiry returns the full expiryDates array with no chain
        payload, which is the cheapest way to enumerate available expiries.

        instrument: "OPTIDX" for indices, "OPTSTK" for stocks.
        """
        encoded = _purify(symbol)
        type_q  = "Indices" if instrument == "OPTIDX" else "Equity"
        cache_key = f"expiry-list-v3-{symbol}-{instrument}"
        cached = _get_cache(cache_key)
        if cached is not None:
            return cached

        # Probe v3 with a placeholder expiry to harvest the expiryDates list
        probe_path = (
            f"/api/option-chain-v3?type={type_q}"
            f"&symbol={encoded}&expiry=01-Jan-2099"
        )
        data = await self.fetch_nse(
            probe_path,
            f"{cache_key}-probe",
            ttl=_ttl_for(300),
            referer=f"{NSE_BASE}/option-chain",
        )

        if not data:
            return []

        dates: list[str] = []
        if isinstance(data, dict):
            # v3 shape: { "records": { "expiryDates": [...] } }
            records = data.get("records") or {}
            dates = records.get("expiryDates") or data.get("expiryDates") or []
        elif isinstance(data, list):
            dates = data

        # Normalise & sort ascending by actual date
        import datetime
        result: list[str] = []
        for d in dates:
            if not d:
                continue
            try:
                datetime.datetime.strptime(d, "%d-%b-%Y")
                result.append(d)
            except ValueError:
                pass

        result.sort(key=lambda x: datetime.datetime.strptime(x, "%d-%b-%Y"))
        if result:
            _set_cache(cache_key, result, _ttl_for(300))
        return result

    # ── PCR (Put-Call Ratio) ─────────────────────────────────────────────────

    def calculate_pcr(self, option_chain_payload: dict, expiry_index: int = 0) -> float:
        """
        Compute Put-Call Ratio from an option chain payload.
        Handles both new ("data" list) and legacy ("records"→"data") formats.
        Adapted from nsepython's pcr() function.
        """
        import datetime

        ce_oi: float = 0.0
        pe_oi: float = 0.0

        # Detect format
        if "records" in option_chain_payload:
            data_list = option_chain_payload["records"].get("data", [])
            expiry_dates: list[str] = option_chain_payload["records"].get("expiryDates", [])
            date_fmt = "%d-%b-%Y"
        elif "data" in option_chain_payload:
            data_list = option_chain_payload["data"]
            unique: set[str] = set()
            for entry in data_list:
                ed = entry.get("expiryDate") or entry.get("expiryDates")
                if ed:
                    unique.add(ed)
            # Try to detect format from the first date sample
            sample = next(iter(unique), "")
            if sample and "-" in sample and sample.split("-")[1].isdigit():
                date_fmt = "%d-%m-%Y"
            else:
                date_fmt = "%d-%b-%Y"
            try:
                expiry_dates = sorted(
                    list(unique),
                    key=lambda x: datetime.datetime.strptime(x, date_fmt),
                )
            except ValueError:
                expiry_dates = sorted(list(unique))
        else:
            return 0.0

        if not expiry_dates or expiry_index >= len(expiry_dates):
            # Sum across all expiries if index out of range
            for item in data_list:
                try:
                    if item.get("CE"):
                        ce_oi += item["CE"].get("openInterest", 0) or 0
                    if item.get("PE"):
                        pe_oi += item["PE"].get("openInterest", 0) or 0
                except (KeyError, TypeError):
                    pass
        else:
            target = expiry_dates[expiry_index]
            for item in data_list:
                curr = item.get("expiryDate") or item.get("expiryDates")
                if curr != target:
                    continue
                try:
                    if item.get("CE"):
                        ce_oi += item["CE"].get("openInterest", 0) or 0
                    if item.get("PE"):
                        pe_oi += item["PE"].get("openInterest", 0) or 0
                except (KeyError, TypeError):
                    pass

        if ce_oi == 0:
            return 0.0
        return round(pe_oi / ce_oi, 4)

    # ── Historical OHLCV ──────────────────────────────────────────────────────

    async def get_historical_data(self, symbol: str, days: int = 90) -> list[dict]:
        """
        Fetch daily OHLCV from NSE India historical API.
        Warms the session by hitting the equity quote page first (browser does
        this before issuing the XHR) — aligns with nsepython's two-step pattern.
        """
        from datetime import datetime, timedelta
        import json as _json

        cache_key = f"nse-hist-{symbol}-{days}"
        cached = _get_cache(cache_key)
        if cached is not None:
            return cached

        to_date   = datetime.utcnow()
        from_date = to_date - timedelta(days=days)
        fmt = lambda d: d.strftime("%d-%m-%Y")

        encoded       = _purify(symbol)
        series_param  = _url_quote(_json.dumps(["EQ"]))
        path = (
            f"/api/historical/cm/equity"
            f"?symbol={encoded}"
            f"&series={series_param}"
            f"&from={fmt(from_date)}"
            f"&to={fmt(to_date)}"
        )

        await _ensure_cookies()

        headers = dict(HEADERS_API)
        headers["Referer"] = f"{NSE_BASE}/get-quotes/equity?symbol={encoded}"

        try:
            # Warm the equity quote page first (nsepython pattern — Akamai
            # rejects the XHR when the Referer page hasn't been visited)
            try:
                await _client.get(
                    f"{NSE_BASE}/get-quotes/equity?symbol={encoded}",
                    headers=HEADERS_BROWSER,
                )
            except Exception:
                pass

            resp = await _client.get(f"{NSE_BASE}{path}", headers=headers)

            if resp.status_code == 503:
                _force_expire()
                await _ensure_cookies()
                resp = await _client.get(f"{NSE_BASE}{path}", headers=headers)

            if resp.status_code != 200:
                logger.warning(
                    "NSE historical %s for %s — falling back to Yahoo",
                    resp.status_code, symbol,
                )
                return []

            raw  = resp.json()
            rows = raw.get("data", [])
            if not rows:
                return []

            data = []
            for r in rows:
                ts = r.get("CH_TIMESTAMP") or r.get("mTIMESTAMP", "")
                c  = r.get("CH_CLOSING_PRICE") or r.get("CH_LAST_TRADED_PRICE")
                if not c:
                    continue
                data.append({
                    "date":   ts[:10],
                    "open":   r.get("CH_OPENING_PRICE",   0) or 0,
                    "high":   r.get("CH_TRADE_HIGH_PRICE", 0) or 0,
                    "low":    r.get("CH_TRADE_LOW_PRICE",  0) or 0,
                    "close":  float(c),
                    "volume": r.get("CH_TOT_TRADED_QTY",  0) or 0,
                })

            data.sort(key=lambda x: x["date"])
            if data:
                _set_cache(cache_key, data, 1800)
            return data

        except Exception as exc:
            logger.debug("NSE historical fetch error for %s: %s", symbol, exc)
            return []
