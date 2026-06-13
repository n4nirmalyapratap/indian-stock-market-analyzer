"""Per-symbol fundamentals — Yahoo Finance `info` dict, normalised + cached.

Why this exists
---------------
The Hidden Gems screener combines technical indicators (already in the
scanner DSL) with fundamental ratios (PE, ROE, debt/equity, market cap,
etc.) that the existing OHLCV-only evaluator can't reach. Each Yahoo
`info` call is ~1-2s of blocking work and the underlying data only
changes when companies file quarterly results — so the right cache
TTL is hours, not seconds.

Read path
---------
  * `prefetch(symbols)` — async, parallel-warms the cache for a list
    of symbols. Called from `ScannersService.run_scanner` once, BEFORE
    the per-symbol evaluation loop, when any condition uses a
    fundamental indicator. Without this every fundamental-indicator
    scan would serially block on Yahoo.
  * `get_cached(symbol)` — sync, O(1) dict lookup. Returns None if
    fundamentals aren't in cache yet (caller should treat as "data
    unavailable" rather than 0/NaN).

Cache shape
-----------
A normalised dict (output of `yahoo_norm.normalise_fundamentals`) plus
two derived fields the scanner DSL benefits from:
  * `marketCapCr`  — market cap in ₹ Crores (1 Cr = 10^7). The screener
    UI thinks in crores, not raw rupees.
  * `debtToEquityRatio` — yfinance ships the ratio × 100 (i.e. 35 means
    0.35). We divide so threshold conditions like `DEBT_TO_EQUITY < 0.5`
    work intuitively without callers having to remember.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Optional

from ..lib.yahoo_norm import normalise_fundamentals
from ..lib.symbol_map import yahoo_candidates

logger = logging.getLogger("fundamentals")

# 12 hour TTL — fundamentals only update on quarterly result releases.
# A 12h window covers the post-market re-analysis window without ever
# serving truly stale data (next morning's open re-warms it).
_TTL_SEC = 12 * 60 * 60

# `_CACHE[symbol] = (fetched_at_ms, fundamentals_dict | None)`. None is
# stored explicitly for symbols where Yahoo returned nothing — keeps us
# from hammering the upstream for known-bad tickers within the TTL window.
_CACHE: dict[str, tuple[float, Optional[dict]]] = {}
_CACHE_LOCK = threading.Lock()


def _is_fresh(entry: tuple[float, Optional[dict]]) -> bool:
    return (time.time() - entry[0]) < _TTL_SEC


def get_cached(symbol: str) -> Optional[dict]:
    """Return cached fundamentals for `symbol`, or None.

    Sync — safe to call from `_SymbolEvaluator.value()` on the scanner
    hot path. Returns None either when (a) the symbol has never been
    prefetched, or (b) Yahoo returned no usable data on the last fetch.
    Either way the caller should treat fundamental indicators as
    "unavailable" for that symbol (typically: condition fails).
    """
    sym = (symbol or "").upper().strip()
    if not sym:
        return None
    with _CACHE_LOCK:
        entry = _CACHE.get(sym)
    if not entry:
        return None
    return entry[1] if _is_fresh(entry) else None


def _enrich(raw: dict) -> dict:
    """Add the two derived fields the scanner DSL expects on top of
    the standard yahoo_norm output."""
    out = dict(raw)
    # Market cap in ₹ Crores (raw is in rupees from Yahoo).
    mc = out.get("marketCap")
    out["marketCapCr"] = round(mc / 1e7, 2) if mc else None
    # Debt/Equity as a ratio (yfinance ships it as a percentage).
    de = out.get("debtToEquity")
    out["debtToEquityRatio"] = round(de / 100.0, 3) if de else None
    return out


def _fetch_blocking(symbol: str) -> Optional[dict]:
    """Hit yfinance for the symbol. Blocking — call inside
    `asyncio.to_thread` from async contexts."""
    import yfinance as yf  # local import — heavy module, defer cost
    sym = symbol.upper().strip()
    for tk_sym in yahoo_candidates(sym):
        try:
            info = yf.Ticker(tk_sym).info or {}
            if not info:
                continue
            # Yahoo sometimes returns a near-empty dict for non-existent
            # tickers. Require at least one of the headline fundamentals
            # to consider this a real hit.
            if not any(info.get(k) for k in ("trailingPE", "marketCap",
                                              "returnOnEquity", "totalRevenue")):
                continue
            return _enrich(normalise_fundamentals(info))
        except Exception as exc:
            logger.debug("fundamentals fetch failed for %s (tk=%s): %s",
                         sym, tk_sym, str(exc)[:120])
            continue
    return None


def _set_cache(symbol: str, value: Optional[dict]) -> None:
    sym = symbol.upper().strip()
    with _CACHE_LOCK:
        _CACHE[sym] = (time.time(), value)


async def get_async(symbol: str) -> Optional[dict]:
    """Async, cache-aware accessor. Returns cached if fresh, else
    fetches via threadpool. Safe to call concurrently — multiple
    awaits for the same symbol will independently fetch (small waste,
    no correctness issue). For bulk warming use `prefetch()` instead."""
    sym = (symbol or "").upper().strip()
    if not sym:
        return None
    cached = get_cached(sym)
    if cached is not None:
        return cached
    with _CACHE_LOCK:
        entry = _CACHE.get(sym)
        if entry and _is_fresh(entry):
            return entry[1]
    val = await asyncio.to_thread(_fetch_blocking, sym)
    _set_cache(sym, val)
    return val


async def prefetch(symbols: list[str], concurrency: int = 8) -> int:
    """Warm the cache for a list of symbols in parallel.

    Skips symbols whose entry is already fresh — repeat scans of the
    same universe within 12h are essentially free. Bounded concurrency
    (default 8) prevents overwhelming yfinance's underlying HTTP
    client. Returns the count of symbols actually fetched (cache
    misses + non-None hits).
    """
    sem = asyncio.Semaphore(max(1, concurrency))
    misses = [s for s in symbols if get_cached(s) is None]

    async def _one(sym: str) -> int:
        async with sem:
            try:
                val = await asyncio.to_thread(_fetch_blocking, sym)
                _set_cache(sym, val)
                return 1 if val is not None else 0
            except Exception as exc:
                logger.debug("prefetch failed for %s: %s", sym, str(exc)[:120])
                _set_cache(sym, None)
                return 0

    if not misses:
        return 0
    results = await asyncio.gather(*[_one(s) for s in misses], return_exceptions=True)
    hits = sum(r for r in results if isinstance(r, int))
    logger.info("fundamentals prefetch: %d hits / %d misses / %d skipped",
                hits, len(misses), len(symbols) - len(misses))
    return hits


# ── Hidden Gem score ────────────────────────────────────────────────────────
# Pure derivation from cached fundamentals — no I/O. Called by the
# scanner result builder ONLY when the scanner's `category` is
# "Hidden Gems" (skipping the cost for the other 30+ scanners).


def compute_hidden_gem_score(fundamentals: dict) -> tuple[int, list[str]]:
    """Returns (score, breakdown_strings).

    Mirrors the user's research framework — each metric contributes a
    bounded sub-score, total clamped to [0, 100]. `breakdown` lets the
    UI render a tooltip like "+20 PE < 15, +15 ROE > 18, …" so users
    understand WHY a stock scored where it did, not just the number.
    """
    score = 0
    breakdown: list[str] = []

    pe = fundamentals.get("pe")
    if pe and pe > 0:
        if pe < 15:
            score += 20; breakdown.append(f"+20 PE {pe:.1f} < 15")
        elif pe < 20:
            score += 10; breakdown.append(f"+10 PE {pe:.1f} < 20")

    roe = fundamentals.get("roe")
    if roe is not None:
        if roe > 20:
            score += 20; breakdown.append(f"+20 ROE {roe:.1f}% > 20")
        elif roe > 15:
            score += 15; breakdown.append(f"+15 ROE {roe:.1f}% > 15")

    de = fundamentals.get("debtToEquityRatio")
    if de is not None:
        if de < 0.3:
            score += 15; breakdown.append(f"+15 D/E {de:.2f} < 0.3")
        elif de < 0.5:
            score += 10; breakdown.append(f"+10 D/E {de:.2f} < 0.5")

    rg = fundamentals.get("revenueGrowth")
    if rg is not None:
        if rg > 20:
            score += 15; breakdown.append(f"+15 Rev growth {rg:.1f}% > 20")
        elif rg > 15:
            score += 10; breakdown.append(f"+10 Rev growth {rg:.1f}% > 15")

    # Net margin — strong margin = pricing power = quality
    nm = fundamentals.get("netMargin")
    if nm is not None and nm > 10:
        score += 10; breakdown.append(f"+10 Net margin {nm:.1f}% > 10")

    # Free cash flow yield — positive FCF % of market cap is genuine
    # cash generation, not accounting earnings.
    fcf = fundamentals.get("freeCashflow")
    mc  = fundamentals.get("marketCap")
    if fcf and mc and mc > 0:
        fcf_yield = (fcf / mc) * 100
        if fcf_yield > 4:
            score += 10; breakdown.append(f"+10 FCF yield {fcf_yield:.1f}% > 4")

    # Small-cap bonus — hidden gems are by definition under-covered.
    mc_cr = fundamentals.get("marketCapCr")
    if mc_cr and 500 <= mc_cr <= 5000:
        score += 5; breakdown.append(f"+5 small-cap (₹{mc_cr:.0f} Cr)")

    return min(100, score), breakdown
