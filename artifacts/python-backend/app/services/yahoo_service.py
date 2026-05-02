import asyncio
import time
from datetime import datetime
from typing import Any, Optional
import httpx
from . import market_cache_service as _disk
from ..lib.symbol_map import to_yahoo_ticker

MAX_ENTRIES = 400
_CACHE: dict[str, dict] = {}
_IN_FLIGHT: dict[str, asyncio.Task] = {}
_CACHE_VERSION = 0  # tracks the market-state version of the entries above

HEADERS = {"User-Agent": "Mozilla/5.0"}


def _flush_if_state_changed() -> None:
    """Drop in-memory entries on every market-state transition.

    Also cancels in-flight tasks so a request started in the previous
    market state can't repopulate the new state's cache with stale data.
    """
    global _CACHE_VERSION, _CACHE, _IN_FLIGHT
    v = _disk.cache_version()
    if v != _CACHE_VERSION:
        _CACHE.clear()
        for task in list(_IN_FLIGHT.values()):
            try:
                task.cancel()
            except Exception:
                pass
        _IN_FLIGHT.clear()
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


def _to_yahoo(symbol: str) -> str:
    """Resolve any NSE/BSE/index symbol to its Yahoo Finance ticker."""
    return to_yahoo_ticker(symbol)


def _quote_ttl() -> int:
    """Quote freshness — short while market is open, long when closed."""
    return 60 if _disk.is_market_open() else 1800


def _hist_ttl() -> int:
    """Historical OHLCV cache TTL — short during market hours, long when closed."""
    return 300 if _disk.is_market_open() else 3600


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
                        "source": "YAHOO",
                    }
                    _set_cache(cache_key, data, _quote_ttl())
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

        # --- Disk cache: when market is closed AND we have an EOD-sealed snapshot,
        #     serve from disk. Intraday-only snapshots may need refreshing.
        if not _disk.is_market_open():
            payload = _disk.load_with_meta(symbol, days)
            if payload and payload.get("eodSealed") and payload.get("data"):
                _set_cache(cache_key, payload["data"], _hist_ttl())
                return payload["data"]

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
            elif days <= 400:
                rng = "1y"
            else:
                rng = "2y"
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
                    _set_cache(cache_key, data, _hist_ttl())
                    # Save to disk regardless of market state — always keep cache fresh
                    _disk.save_to_disk(symbol, days, data, source="YAHOO")
                    return data
            except Exception:
                return []
            finally:
                _IN_FLIGHT.pop(cache_key, None)

        task = asyncio.create_task(_fetch())
        _IN_FLIGHT[cache_key] = task
        return await task

    async def get_intraday_chart(self, symbol: str, period: str = "1mo", interval: str = "1d") -> dict:
        """
        Fetch chart candles at any interval/period for the chart UI.
        Returns `{candles: [...], companyName, currency, source}`.
        Sub-daily intervals always go to Yahoo (NSE only has daily).
        """
        ticker = _to_yahoo(symbol)
        cache_key = f"yc-{ticker}-{period}-{interval}"
        cached = _get_cache(cache_key)
        if cached is not None:
            return cached

        try:
            url = (
                f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
                f"?interval={interval}&range={period}"
            )
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=HEADERS)
                if resp.status_code != 200:
                    return {"candles": [], "source": "YAHOO_ERROR"}
                result = resp.json()
                chart = result.get("chart", {}).get("result", [None])[0]
                if not chart:
                    return {"candles": [], "source": "YAHOO_EMPTY"}
                meta = chart.get("meta", {}) or {}
                ts_list = chart.get("timestamp", []) or []
                ind = (chart.get("indicators", {}) or {}).get("quote", [{}])[0] or {}
                opens   = ind.get("open",   [])
                highs   = ind.get("high",   [])
                lows    = ind.get("low",    [])
                closes  = ind.get("close",  [])
                volumes = ind.get("volume", [])
                candles: list[dict] = []
                for i, ts in enumerate(ts_list):
                    c = closes[i] if i < len(closes) else None
                    if c is None:
                        continue
                    candles.append({
                        "time":   int(ts),
                        "open":   round(float(opens[i]),  2) if i < len(opens)  and opens[i]  is not None else None,
                        "high":   round(float(highs[i]),  2) if i < len(highs)  and highs[i]  is not None else None,
                        "low":    round(float(lows[i]),   2) if i < len(lows)   and lows[i]   is not None else None,
                        "close":  round(float(c), 2),
                        "volume": int(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0,
                    })
                payload = {
                    "candles":     candles,
                    "companyName": meta.get("longName") or meta.get("shortName") or symbol,
                    "currency":    meta.get("currency", "INR"),
                    "source":      "YAHOO",
                }
                _set_cache(cache_key, payload, _hist_ttl())
                return payload
        except Exception as e:
            return {"candles": [], "source": "YAHOO_ERROR", "error": str(e)}
