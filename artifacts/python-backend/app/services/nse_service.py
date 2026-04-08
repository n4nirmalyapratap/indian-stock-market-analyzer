import asyncio
import time
from typing import Any, Optional
import httpx

MAX_ENTRIES = 200
_CACHE: dict[str, dict] = {}

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


def _get_cache(key: str) -> Optional[Any]:
    entry = _CACHE.get(key)
    if entry and time.time() < entry["expiry"]:
        return entry["data"]
    if entry:
        del _CACHE[key]
    return None


def _set_cache(key: str, data: Any, ttl: int) -> None:
    global _CACHE
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


class NseService:
    async def fetch_nse(self, path: str, cache_key: str, ttl: int = 300) -> Optional[Any]:
        cached = _get_cache(cache_key)
        if cached is not None:
            return cached

        await _ensure_cookies()
        headers = {**HEADERS_API, "Cookie": _cookies}
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(f"https://www.nseindia.com{path}", headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    _set_cache(cache_key, data, ttl)
                    return data
        except Exception:
            pass
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
