import asyncio
import logging
import time
from typing import Any, Optional
import httpx

logger = logging.getLogger(__name__)

from . import market_cache_service as _mcs

MAX_ENTRIES = 200
_CACHE: dict[str, dict] = {}
_CACHE_VERSION = 0   # tracks the market-state version of the entries above

_cookies = ""
_cookie_expiry = 0.0
_refresh_lock = asyncio.Lock()
_refresh_task: Optional[asyncio.Task] = None

HEADERS_BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

HEADERS_API = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com",
    "X-Requested-With": "XMLHttpRequest",
}


def _flush_if_state_changed() -> None:
    """Drop in-memory cache entries when market state has just transitioned."""
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


async def _refresh_cookies() -> None:
    global _cookies, _cookie_expiry
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get("https://www.nseindia.com", headers=HEADERS_BROWSER)
            set_cookie = resp.headers.get_list("set-cookie")
            if set_cookie:
                parts = [c.split(";")[0] for c in set_cookie]
                _cookies = "; ".join(parts)
                _cookie_expiry = time.time() + 20 * 60
    except Exception:
        pass


async def _ensure_cookies() -> None:
    global _cookies, _cookie_expiry, _refresh_task
    if _cookies and time.time() < _cookie_expiry:
        return
    async with _refresh_lock:
        if _cookies and time.time() < _cookie_expiry:
            return
        await _refresh_cookies()


def _ttl_for(default_ttl: int) -> int:
    """Shorten TTLs when market is open (data changes), keep long when closed."""
    if _mcs.is_market_open():
        return min(default_ttl, 60)
    return default_ttl


class NseService:
    async def fetch_nse(self, path: str, cache_key: str, ttl: int = 300, retries: int = 3) -> Optional[Any]:
        ttl = _ttl_for(ttl)
        cached = _get_cache(cache_key)
        if cached is not None:
            return cached

        for attempt in range(retries):
            await _ensure_cookies()
            headers = {**HEADERS_API, "Cookie": _cookies}
            try:
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                    resp = await client.get(f"https://www.nseindia.com{path}", headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        _set_cache(cache_key, data, ttl)
                        return data
                    elif resp.status_code in (401, 403):
                        # Force cookie refresh
                        global _cookie_expiry
                        _cookie_expiry = 0
                        continue
                    elif resp.status_code == 429:
                        await asyncio.sleep(2 ** attempt)
                        continue
            except Exception:
                await asyncio.sleep(1)
                
        return None

    def get_sector_indices(self):
        return self.fetch_nse("/api/allIndices", "sector-indices", 300)

    def get_stock_quote(self, symbol: str):
        from urllib.parse import quote as url_encode
        encoded = url_encode(symbol, safe="")
        return self.fetch_nse(
            f"/api/quote-equity?symbol={encoded}",
            f"quote-{symbol}",
            120,
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

    async def fetch_nse_archive_text(
        self,
        url: str,
        cache_key: str,
        ttl: int = 86400,
        retries: int = 2,
    ) -> Optional[str]:
        """Fetch a static-archive resource from nsearchives.nseindia.com (CSV /
        text endpoints) using the same shared in-process cache and browser
        headers as the JSON API path. Returns the raw text body on HTTP 200,
        None otherwise (e.g. weekend/holiday 404s for daily reports).

        Used by callers like fii_dii_service for the participant-OI archive
        which only exists as a CSV — going through NseService keeps a single
        place for header/UA/cache discipline."""
        cached = _get_cache(cache_key)
        if cached is not None:
            return cached
        headers = {
            "User-Agent": HEADERS_BROWSER["User-Agent"],
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/all-reports-derivatives",
        }
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                    resp = await client.get(url, headers=headers)
                if resp.status_code == 200 and resp.text and len(resp.text) > 50:
                    _set_cache(cache_key, resp.text, ttl)
                    return resp.text
                if resp.status_code in (429,):
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None  # 404 / 403 / etc — don't retry, holiday or unavailable
            except Exception:
                await asyncio.sleep(1)
        return None

    async def get_historical_data(self, symbol: str, days: int = 90) -> list[dict]:
        """
        Fetch daily OHLCV from NSE India historical API (cookie method).
        NSE endpoint: /api/historical/cm/equity?symbol=X&series=["EQ"]&from=dd-mm-yyyy&to=dd-mm-yyyy
        Returns same shape as YahooService.get_historical_data for drop-in compatibility.
        """
        from datetime import datetime, timedelta
        cache_key = f"nse-hist-{symbol}-{days}"
        cached = _get_cache(cache_key)
        if cached is not None:
            return cached

        to_date   = datetime.utcnow()
        from_date = to_date - timedelta(days=days)
        fmt = lambda d: d.strftime("%d-%m-%Y")

        from urllib.parse import quote as url_encode
        import json as _json
        series_param = url_encode(_json.dumps(["EQ"]))
        path = (
            f"/api/historical/cm/equity"
            f"?symbol={url_encode(symbol, safe='')}"
            f"&series={series_param}"
            f"&from={fmt(from_date)}"
            f"&to={fmt(to_date)}"
        )

        await _ensure_cookies()
        # Path-specific Referer — Akamai's WAF rejects bare-domain Referer for
        # the historical endpoints. Plus retry-on-503 (transient Akamai
        # bot-challenge) with one cookie refresh in between.
        headers = {
            **HEADERS_API,
            "Cookie":  _cookies,
            "Referer": f"https://www.nseindia.com/get-quotes/equity?symbol={symbol}",
        }
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                # Warm session by hitting the equity quote page first — this
                # is what the browser does before issuing the XHR.
                try:
                    await client.get(
                        f"https://www.nseindia.com/get-quotes/equity?symbol={symbol}",
                        headers={**HEADERS_BROWSER, "Cookie": _cookies},
                    )
                except Exception:
                    pass
                resp = await client.get(f"https://www.nseindia.com{path}", headers=headers)
                if resp.status_code == 503:
                    # Akamai bot-challenge — refresh cookies and retry once
                    global _cookie_expiry
                    _cookie_expiry = 0
                    await _ensure_cookies()
                    headers["Cookie"] = _cookies
                    resp = await client.get(f"https://www.nseindia.com{path}", headers=headers)
                if resp.status_code != 200:
                    # Visible warning so the YAHOO-sealed disk fallback is
                    # never silent. NSE historical is commonly Akamai-blocked
                    # from data-center IPs (Replit / AWS / GCP).
                    logger.warning(
                        "NSE historical %s for %s — falling back to Yahoo",
                        resp.status_code, symbol,
                    )
                    return []
                raw = resp.json()
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
                        "open":   r.get("CH_OPENING_PRICE", 0) or 0,
                        "high":   r.get("CH_TRADE_HIGH_PRICE", 0) or 0,
                        "low":    r.get("CH_TRADE_LOW_PRICE", 0) or 0,
                        "close":  float(c),
                        "volume": r.get("CH_TOT_TRADED_QTY", 0) or 0,
                    })
                # NSE returns newest-first — sort ascending
                data.sort(key=lambda x: x["date"])
                if data:
                    _set_cache(cache_key, data, 1800)
                return data
        except Exception:
            return []
