import asyncio
import time
from datetime import datetime
from typing import Any, Optional
import httpx
from . import market_cache_service as _disk
from ..lib.symbol_map import to_yahoo_ticker, is_yahoo_unavailable

MAX_ENTRIES = 400
_CACHE: dict[str, dict] = {}
_IN_FLIGHT: dict[str, asyncio.Task] = {}
_CACHE_VERSION = 0  # tracks the market-state version of the entries above

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ── Retry + circuit breaker for Yahoo HTTP calls ──────────────────────────
# Yahoo's chart endpoint occasionally returns 5xx or times out under load.
# Two-attempt retry with 200 ms then 400 ms backoff smooths out transient
# blips. A per-host circuit breaker prevents thundering-herd retries when
# Yahoo is genuinely down: 5 consecutive failures within 60 s open the
# breaker for 30 s, during which requests short-circuit to None instead
# of stacking up against a dead host.
_RETRY_ATTEMPTS = 2
_RETRY_BACKOFF_MS = (200, 400)
_BREAKER_THRESHOLD = 5            # consecutive failures to trip
_BREAKER_WINDOW_S = 60            # within this rolling window
_BREAKER_OPEN_S = 30              # stay open this long once tripped
_breaker_state: dict[str, dict] = {
    # host: {"failures": [ts,...], "opened_at": float|None}
}


def _breaker_is_open(host: str) -> bool:
    s = _breaker_state.setdefault(host, {"failures": [], "opened_at": None})
    if s["opened_at"] is None:
        return False
    if time.time() - s["opened_at"] > _BREAKER_OPEN_S:
        # Cool-off elapsed — half-close: reset and let the next call try.
        s["failures"] = []
        s["opened_at"] = None
        return False
    return True


def _breaker_record(host: str, ok: bool) -> None:
    s = _breaker_state.setdefault(host, {"failures": [], "opened_at": None})
    now = time.time()
    if ok:
        s["failures"] = []
        s["opened_at"] = None
        return
    # Drop failures older than the window, append this one.
    s["failures"] = [t for t in s["failures"] if now - t <= _BREAKER_WINDOW_S]
    s["failures"].append(now)
    if len(s["failures"]) >= _BREAKER_THRESHOLD and s["opened_at"] is None:
        s["opened_at"] = now


async def _yahoo_get(url: str, *, timeout: float = 10.0) -> Optional[httpx.Response]:
    """GET with bounded retry + per-host circuit breaker.

    Returns the Response on success (any status code — caller decides what
    counts as success), or None when the breaker is open or all attempts
    failed. Never raises — on irrecoverable failure the caller gets None.
    """
    try:
        host = httpx.URL(url).host or "yahoo"
    except Exception:
        host = "yahoo"
    if _breaker_is_open(host):
        return None
    last_exc: Optional[BaseException] = None
    for attempt in range(_RETRY_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, headers=HEADERS)
            # Treat 5xx and 429 as retryable provider failures; 4xx (e.g.
            # 404 for a bad ticker) is a *symbol-level* problem that won't
            # get better on retry AND must NOT count against the provider
            # circuit breaker — otherwise a burst of unknown symbols would
            # trip the breaker and starve every other valid symbol of data.
            if resp.status_code < 500 and resp.status_code != 429:
                # Only a true success (2xx) clears prior failure history.
                # Other 4xx don't count as failures, but also don't reset
                # an already-accumulating provider-failure streak.
                if 200 <= resp.status_code < 300:
                    _breaker_record(host, ok=True)
                return resp
            last_exc = RuntimeError(f"HTTP {resp.status_code}")
        except (httpx.TimeoutException, httpx.HTTPError, OSError) as e:
            last_exc = e
        # Backoff before the next retry (none after the final attempt)
        if attempt < _RETRY_ATTEMPTS:
            ms = _RETRY_BACKOFF_MS[min(attempt, len(_RETRY_BACKOFF_MS) - 1)]
            await asyncio.sleep(ms / 1000.0)
    # Reached only on transport error or 5xx/429 exhausted — provider fault.
    _breaker_record(host, ok=False)
    return None


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
        # Short-circuit symbols Yahoo is known to 404 on (e.g.
        # ^CNXHEALTH, ^CNXOILGAS after Yahoo dropped them late 2025).
        # Returning None here lets the price-provider chain fall through
        # to NSE / BSE / disk-cache without spamming yfinance warnings.
        if is_yahoo_unavailable(symbol):
            return None

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
                resp = await _yahoo_get(url, timeout=10.0)
                if resp is None or resp.status_code != 200:
                    return None
                if True:
                    result = resp.json()
                    meta = result.get("chart", {}).get("result", [None])[0]
                    if not meta:
                        return None
                    meta = meta.get("meta", {})
                    # Yahoo misidentifies some post-merger / BSE-only equities as
                    # MUTUALFUND and returns regularMarketPrice: None.  Treat a
                    # missing price as a failed quote so the caller can fall
                    # through to the disk-EOD overlay — never return ₹0.00.
                    raw_price = meta.get("regularMarketPrice")
                    if raw_price is None:
                        return None
                    price = float(raw_price) or 0
                    prev_close = float(meta.get("chartPreviousClose") or 0)
                    data = {
                        "symbol": symbol,
                        "companyName": meta.get("longName", symbol),
                        "lastPrice": price,
                        "change": price - prev_close,
                        "pChange": ((price - prev_close) / prev_close * 100) if prev_close else 0,
                        "open": meta.get("regularMarketOpen") or 0,
                        "dayHigh": meta.get("regularMarketDayHigh") or 0,
                        "dayLow": meta.get("regularMarketDayLow") or 0,
                        "previousClose": prev_close,
                        "volume": meta.get("regularMarketVolume") or 0,
                        "marketCap": meta.get("marketCap") or None,
                        "fiftyTwoWeekHigh": meta.get("fiftyTwoWeekHigh") or meta.get("52WeekHigh") or None,
                        "fiftyTwoWeekLow": meta.get("fiftyTwoWeekLow") or meta.get("52WeekLow") or None,
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
        # Same short-circuit as get_quote — saves a guaranteed-404 round
        # trip for indices Yahoo no longer publishes.
        if is_yahoo_unavailable(symbol):
            return []

        cache_key = f"yh-{symbol}-{days}"

        # --- Disk cache: when market is closed AND we have an EOD-sealed snapshot,
        #     serve from disk. Intraday-only snapshots may need refreshing.
        #     For indices only, reject thin payloads — sectors_service writes a
        #     2-row OHLC stub to the same canonical path for sector cards, and
        #     we don't want the chart to serve it. Equities (incl. new listings
        #     with very short history) are not gated.
        from ..lib.symbol_map import is_index_symbol as _is_index
        min_rows = max(5, min(days // 4, 20)) if (_is_index(symbol) and days >= 10) else 1
        if not _disk.is_market_open():
            payload = _disk.load_with_meta(symbol, days)
            cached = payload.get("data") if payload else None
            if (
                payload
                and payload.get("eodSealed")
                and isinstance(cached, list)
                and len(cached) >= min_rows
            ):
                _set_cache(cache_key, cached, _hist_ttl())
                return cached

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
            elif days <= 800:
                rng = "2y"
            elif days <= 2000:
                rng = "5y"
            elif days <= 4000:
                rng = "10y"
            else:
                rng = "max"
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{_to_yahoo(symbol)}?interval=1d&range={rng}"
                resp = await _yahoo_get(url, timeout=10.0)
                if resp is None or resp.status_code != 200:
                    return []
                if True:
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
            resp = await _yahoo_get(url, timeout=15.0)
            if resp is None or resp.status_code != 200:
                return {"candles": [], "source": "YAHOO_ERROR"}
            if True:
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
