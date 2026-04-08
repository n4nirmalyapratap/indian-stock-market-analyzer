import asyncio
import time
from datetime import datetime
from typing import Any, Optional
import httpx

MAX_ENTRIES = 400
_CACHE: dict[str, dict] = {}
_IN_FLIGHT: dict[str, asyncio.Task] = {}

HEADERS = {"User-Agent": "Mozilla/5.0"}


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


def _to_yahoo(symbol: str) -> str:
    return f"{symbol}.NS"


class YahooService:
    async def get_quote(self, symbol: str) -> Optional[dict]:
        cache_key = f"yq-{symbol}"
        cached = _get_cache(cache_key)
        if cached is not None:
            return cached

        if cache_key in _IN_FLIGHT:
            try:
                return await _IN_FLIGHT[cache_key]
            except Exception:
                return None

        async def _fetch():
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{_to_yahoo(symbol)}?interval=1d&range=1d"
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(url, headers=HEADERS)
                    if resp.status_code != 200:
                        return None
                    result = resp.json()
                    meta = result.get("chart", {}).get("result", [None])[0]
                    if not meta:
                        return None
                    meta = meta.get("meta", {})
                    prev_close = meta.get("chartPreviousClose", 0) or 0
                    price = meta.get("regularMarketPrice", 0) or 0
                    data = {
                        "symbol": symbol,
                        "companyName": meta.get("longName", symbol),
                        "lastPrice": price,
                        "change": price - prev_close,
                        "pChange": ((price - prev_close) / prev_close * 100) if prev_close else 0,
                        "open": meta.get("regularMarketOpen", 0),
                        "dayHigh": meta.get("regularMarketDayHigh", 0),
                        "dayLow": meta.get("regularMarketDayLow", 0),
                        "previousClose": prev_close,
                        "volume": meta.get("regularMarketVolume", 0),
                        "marketCap": meta.get("marketCap", 0),
                        "fiftyTwoWeekHigh": meta.get("52WeekHigh", 0),
                        "fiftyTwoWeekLow": meta.get("52WeekLow", 0),
                    }
                    _set_cache(cache_key, data, 300)
                    return data
            except Exception:
                return None
            finally:
                _IN_FLIGHT.pop(cache_key, None)

        task = asyncio.create_task(_fetch())
        _IN_FLIGHT[cache_key] = task
        return await task

    async def get_historical_data(self, symbol: str, days: int = 90) -> list[dict]:
        cache_key = f"yh-{symbol}-{days}"
        cached = _get_cache(cache_key)
        if cached is not None:
            return cached

        if cache_key in _IN_FLIGHT:
            try:
                return await _IN_FLIGHT[cache_key]
            except Exception:
                return []

        async def _fetch():
            if days <= 30:
                rng = "1mo"
            elif days <= 90:
                rng = "3mo"
            elif days <= 180:
                rng = "6mo"
            else:
                rng = "1y"
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{_to_yahoo(symbol)}?interval=1d&range={rng}"
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(url, headers=HEADERS)
                    if resp.status_code != 200:
                        return []
                    result = resp.json()
                    chart_result = result.get("chart", {}).get("result", [None])[0]
                    if not chart_result:
                        return []
                    timestamps = chart_result.get("timestamp", [])
                    indicators = chart_result.get("indicators", {}).get("quote", [{}])[0]
                    opens = indicators.get("open", [])
                    highs = indicators.get("high", [])
                    lows = indicators.get("low", [])
                    closes = indicators.get("close", [])
                    volumes = indicators.get("volume", [])
                    data = []
                    for i, ts in enumerate(timestamps):
                        c = closes[i] if i < len(closes) else None
                        if c is None:
                            continue
                        data.append({
                            "date": datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d"),
                            "open": opens[i] if i < len(opens) else 0,
                            "high": highs[i] if i < len(highs) else 0,
                            "low": lows[i] if i < len(lows) else 0,
                            "close": c,
                            "volume": volumes[i] if i < len(volumes) else 0,
                        })
                    _set_cache(cache_key, data, 3600)
                    return data
            except Exception:
                return []
            finally:
                _IN_FLIGHT.pop(cache_key, None)

        task = asyncio.create_task(_fetch())
        _IN_FLIGHT[cache_key] = task
        return await task
