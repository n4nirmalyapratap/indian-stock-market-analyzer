"""Top Movers service — biggest gainers and losers per market-cap segment.

Powers the Dashboard "Top Movers" tab. Two-tier sourcing:

  1. **NSE bulk index endpoint** (`/api/equity-stockIndices?index=...`) —
     fast, single call returns all constituents with pChange already
     computed. Preferred when NSE is reachable.

  2. **Per-stock fallback via PriceService** — when the bulk endpoint
     returns None twice in a row (NSE cookie / Akamai 503 / cloud egress
     block), iterate the segment's universe list calling
     `PriceService.get_quote_with_meta()` per symbol. That call has its
     own NSE-primary / Yahoo-fallback chain built in, so individual stock
     quotes succeed even when the bulk index endpoint is blocked.

Cap segment → NSE index mapping:
  * large → NIFTY 100
  * mid   → NIFTY MIDCAP 150
  * small → NIFTY SMALLCAP 250
  * micro → NIFTY MICROCAP 250

When the market is closed the NSE feed keeps returning the most recent
session's close, so users see yesterday's top movers naturally — no extra
fall-back logic needed.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Optional

from . import market_cache_service as _disk
from .nse_service import NseService

logger = logging.getLogger("top_movers")

# Per-segment cache of the slow Yahoo-fallback result so we don't re-scan
# 100+ symbols on every page render. 5-minute TTL matches the NSE-feed
# TTL for closed markets and is short enough for the open-market case
# (most users won't notice 5-min lag in top-movers).
_FALLBACK_TTL_SEC = 5 * 60
_fallback_cache: dict[str, tuple[float, dict]] = {}

# Per-segment cache of the closed-market disk leaderboard, keyed (value side) by
# trading date. When the market is closed the sealed EOD bars are frozen for the
# whole session, so the ranking is stable — caching by date means we compute it
# ONCE per session instead of re-reading ~750 canonical snapshots from the
# (SMB-mounted in prod) market_cache on every dashboard render.
_disk_movers_cache: dict[str, tuple[str, dict]] = {}

# Segment → (label, NSE index slug, cache key).  Cache key is namespaced
# per-segment so the existing nse_service cache layer doesn't collide.
SEGMENT_INDEX = {
    "large": ("Large Cap", "NIFTY 100",           "top_movers_large"),
    "mid":   ("Mid Cap",   "NIFTY MIDCAP 150",    "top_movers_mid"),
    "small": ("Small Cap", "NIFTY SMALLCAP 250",  "top_movers_small"),
    "micro": ("Micro Cap", "NIFTY MICROCAP 250",  "top_movers_micro"),
}

# How long the per-index NSE response is cached locally.  60s during market
# hours matches the other live endpoints; 5 min after-close is fine because
# the underlying close doesn't change.
_OPEN_TTL  = 60
_CLOSED_TTL = 5 * 60


def _ttl() -> int:
    return _OPEN_TTL if _disk.is_market_open() else _CLOSED_TTL


def _name_for(sym: str, provided: Optional[str]) -> str:
    """Best available company name: provider's name → universe COMPANY_MAP → symbol.

    Brand-new tickers (e.g. TMCV after the Tata Motors demerger) often have no
    company name from Yahoo / NSE index meta yet, but our universe cache does —
    so fall back to it instead of showing a bare symbol (which the UI then
    renders as just a price)."""
    p = (provided or "").strip()
    if p and p.upper() != sym.upper():
        return p
    from ..lib import universe as _u  # noqa: PLC0415
    return _u.COMPANY_MAP.get(sym) or p or sym


def _row(stock: dict) -> Optional[dict]:
    """Flatten one NSE constituent into the shape the frontend expects.

    Returns None for the index-aggregate row itself (NSE sometimes emits a
    leading row with `priority=0` and symbol equal to the index name), and
    for any row that doesn't have a usable pChange (avoids ranking a stock
    that's currently suspended or pre-listed)."""
    if not isinstance(stock, dict):
        return None
    sym = (stock.get("symbol") or "").strip()
    if not sym:
        return None
    # NSE's index-summary row has the index's own name as its symbol —
    # filter it out so it doesn't show up as the #1 mover.
    if sym.upper().startswith("NIFTY"):
        return None
    pchange = stock.get("pChange")
    if pchange is None:
        return None
    try:
        pchange = float(pchange)
    except (TypeError, ValueError):
        return None
    _nse_name = stock.get("meta", {}).get("companyName") if isinstance(stock.get("meta"), dict) else None
    return {
        "symbol":      sym,
        "name":        _name_for(sym, _nse_name),
        "lastPrice":   stock.get("lastPrice"),
        "change":      stock.get("change"),
        "pChange":     round(pchange, 2),
        "open":        stock.get("open"),
        "dayHigh":     stock.get("dayHigh"),
        "dayLow":      stock.get("dayLow"),
        "previousClose": stock.get("previousClose"),
        "volume":      stock.get("totalTradedVolume"),
        "valueLakhs":  stock.get("totalTradedValue"),
        "yearHigh":    stock.get("yearHigh"),
        "yearLow":     stock.get("yearLow"),
    }


class TopMoversService:
    """Stateless — safe to instantiate per-request or share."""

    def __init__(self, nse: Optional[NseService] = None) -> None:
        self.nse = nse or NseService()
        # Lazy-init PriceService so the import chain (Yahoo → indicators →
        # numpy) only loads when the Yahoo fallback actually fires.
        self._price: Any = None

    def _yahoo(self) -> Any:
        """Lazy-init the YahooService instance. Top Movers fallback talks
        to Yahoo *directly* rather than going through PriceService — the
        latter now has a 5-tier chain (NSE → BSE → Yahoo → Twelve → Stooq)
        and waiting through NSE's timeout per-stock × 120 symbols was the
        dominant cost when this fallback was triggered.
        """
        if self._price is None:
            from .yahoo_service import YahooService  # noqa: PLC0415
            self._price = YahooService()
        return self._price

    def _disk_movers(self, segment: str, count: int) -> Optional[dict]:
        """Closed-market fast path: rank gainers/losers straight from the
        EOD-sealed bars already on disk — zero network, instant.

        `pChange = (last_close - prev_close) / prev_close` from each symbol's
        sealed canonical snapshot is the same number the session produced, and
        it's the SAME sealed bar the chart/quote endpoints serve — so this is a
        consistency improvement, not a data-quality compromise.

        Returns None when too few of the segment's symbols are sealed yet (cold
        start before the post-close warmup has run), so the caller falls
        through to the live NSE/Yahoo path.
        """
        # Session-frozen result cache: the sealed EOD bars don't change until the
        # next session, so memoise the computed leaderboard keyed by trading date.
        # A hit turns ~750 canonical-snapshot reads (over the SMB-mounted
        # market_cache in prod) into one dict lookup — the dominant cost of the
        # closed-market dashboard render. Only non-None results are cached (below),
        # so a cold start keeps retrying until the post-close warmup has sealed
        # enough of the segment.
        td = _disk.last_trading_date()
        cache_key = f"{segment}:{count}"
        hit = _disk_movers_cache.get(cache_key)
        if hit and hit[0] == td:
            return hit[1]

        from ..lib import universe  # noqa: PLC0415
        universe_map = {
            "large": universe.NIFTY100,
            "mid":   universe.MIDCAP,
            "small": universe.SMALLCAP,
            "micro": universe.MICROCAP,
        }
        symbols = list(dict.fromkeys(universe_map.get(segment, [])))
        if not symbols:
            return None

        rows: list[dict] = []
        as_of: Optional[str] = None
        for sym in symbols:
            payload = _disk.load_with_meta(sym, 5)
            if not (payload and payload.get("eodSealed") and payload.get("data")):
                continue
            bars = payload["data"]
            if len(bars) < 2:
                continue
            last, prev = bars[-1], bars[-2]
            lc, pc = last.get("close"), prev.get("close")
            if lc is None or pc is None:
                continue
            try:
                lc, pc = float(lc), float(pc)
            except (TypeError, ValueError):
                continue
            if pc == 0:
                continue
            as_of = as_of or payload.get("savedAt") or payload.get("eodDate")
            rows.append({
                "symbol":        sym,
                "name":          _name_for(sym, None),
                "lastPrice":     round(lc, 2),
                "change":        round(lc - pc, 2),
                "pChange":       round((lc - pc) / pc * 100, 2),
                "open":          last.get("open"),
                "dayHigh":       last.get("high"),
                "dayLow":        last.get("low"),
                "previousClose": round(pc, 2),
                "volume":        last.get("volume"),
                "valueLakhs":    None,
                "yearHigh":      None,
                "yearLow":       None,
            })

        # Trust the disk ranking only when a solid majority of the segment is
        # sealed — otherwise the leaderboard is biased toward whichever symbols
        # happen to be on disk. Below the floor, signal a miss so the caller
        # falls back to the live path.
        if len(rows) < min(20, max(1, len(symbols) // 2)):
            return None

        gainers = sorted(rows, key=lambda r: r["pChange"], reverse=True)[:count]
        losers  = sorted(rows, key=lambda r: r["pChange"])[:count]
        label = SEGMENT_INDEX[segment][0]
        out = {
            "available":    True,
            "segment":      segment,
            "label":        label,
            "indexSlug":    SEGMENT_INDEX[segment][1],
            "asOf":         as_of or _disk._now_ist().isoformat(),
            "marketState":  _disk.current_market_state(),
            "totalScanned": len(rows),
            "gainers":      gainers,
            "losers":       losers,
            "servedFrom":   "DISK_EOD",
        }
        _disk_movers_cache[cache_key] = (td, out)
        return out

    async def _yahoo_fallback_scan(self, segment: str, count: int) -> Optional[dict]:
        """Per-stock Yahoo-backed fallback when the NSE bulk index endpoint
        is unreachable.

        Walks the segment's universe list and calls Yahoo directly for
        each symbol. We deliberately skip the PriceService chain here:
        when we're in this code path, NSE bulk has already failed and
        Yahoo is the goal — going through the chain would add the cost
        of NSE/BSE timeouts per stock with no benefit.

        Returns the same shape as the primary path, with
        `servedFrom: "Yahoo"` so the UI can show provenance. Returns None
        only when the universe list is empty for the segment.

        Caching: the Yahoo scan is cached for 5 minutes per segment
        so subsequent renders within that window are instant.
        """
        from ..lib import universe  # noqa: PLC0415

        # Per-segment cache check.
        cache_key = f"yahoo_fallback:{segment}"
        cached = _fallback_cache.get(cache_key)
        if cached and (time.time() - cached[0]) < _FALLBACK_TTL_SEC:
            return cached[1]

        label = SEGMENT_INDEX[segment][0]
        universe_map = {
            "large": universe.NIFTY100,
            "mid":   universe.MIDCAP,
            "small": universe.SMALLCAP,
            "micro": universe.MICROCAP,
        }
        # dict.fromkeys dedups while preserving order — the universe lists are
        # hand-maintained and occasionally carry a repeated symbol, which would
        # otherwise surface as the same stock twice in a gainers/losers column.
        symbols = list(dict.fromkeys(universe_map.get(segment, [])))
        if not symbols:
            return None

        # Cap the scan: 100 symbols at concurrency 25 → ~3-4s wall time
        # with direct-Yahoo calls. Bigger universes get truncated to keep
        # dashboard cold-start tolerable; subsequent loads are instant
        # via the 5-min cache.
        if len(symbols) > 100:
            symbols = symbols[:100]

        yahoo = self._yahoo()
        # Yahoo can comfortably handle higher parallelism than NSE — 25
        # concurrent requests is well within their tolerance and cuts
        # wall time roughly proportionally vs the old sem=15.
        sem   = asyncio.Semaphore(25)

        async def _one(sym: str) -> Optional[dict]:
            async with sem:
                try:
                    q = await yahoo.get_quote(sym)
                except Exception:
                    return None
                if not q:
                    return None
                pchange = q.get("pChange")
                if pchange is None:
                    return None
                try:
                    pchange_f = float(pchange)
                except (TypeError, ValueError):
                    return None
                return {
                    "symbol":         sym,
                    "name":           _name_for(sym, q.get("companyName")),
                    "lastPrice":      q.get("lastPrice"),
                    "change":         q.get("change"),
                    "pChange":        round(pchange_f, 2),
                    "open":           q.get("open"),
                    "dayHigh":        q.get("dayHigh"),
                    "dayLow":         q.get("dayLow"),
                    "previousClose":  q.get("previousClose"),
                    "volume":         q.get("totalTradedVolume") or q.get("volume"),
                    "valueLakhs":     None,
                    "yearHigh":       q.get("fiftyTwoWeekHigh"),
                    "yearLow":        q.get("fiftyTwoWeekLow"),
                }

        gathered = await asyncio.gather(
            *[_one(s) for s in symbols], return_exceptions=True,
        )
        rows = [r for r in gathered if isinstance(r, dict)]
        if not rows:
            return None

        gainers = sorted(rows, key=lambda r: r["pChange"], reverse=True)[:count]
        losers  = sorted(rows, key=lambda r: r["pChange"])[:count]
        out = {
            "available":    True,
            "segment":      segment,
            "label":        f"{label} (Yahoo fallback)",
            "indexSlug":    SEGMENT_INDEX[segment][1],
            "asOf":         _disk._now_ist().isoformat(),
            "marketState":  _disk.current_market_state(),
            "totalScanned": len(rows),
            "gainers":      gainers,
            "losers":       losers,
            "servedFrom":   "Yahoo",
        }
        _fallback_cache[cache_key] = (time.time(), out)
        logger.info("Top Movers Yahoo fallback ok for %s: %d rows scanned",
                    segment, len(rows))
        return out

    async def get_top_movers(self, segment: str, count: int = 10) -> dict:
        """Return top `count` gainers + top `count` losers for `segment`.

        Always returns a status envelope so the frontend can render an
        empty/error state without distinguishing 404 from 500."""
        if segment not in SEGMENT_INDEX:
            return {
                "available": False,
                "segment":   segment,
                "message":   f"Unknown segment {segment!r}. "
                             f"Allowed: {sorted(SEGMENT_INDEX)}",
                "gainers":   [], "losers": [],
            }

        # Closed-market fast path: the session's closes are frozen and already
        # sealed to disk by the post-close warmup. Rank from those bars
        # directly — instant, zero network, consistent with the chart/quote
        # endpoints. Falls through to the live path if the snapshot isn't ready
        # yet (cold start before warmup completes).
        if not _disk.is_market_open():
            # Offload the per-symbol disk reads to a thread so the event loop
            # stays free (get_all_segments runs four of these concurrently).
            disk = await asyncio.to_thread(self._disk_movers, segment, count)
            if disk is not None:
                return disk

        label, index_slug, cache_key = SEGMENT_INDEX[segment]
        # URL-encode the spaces in the NSE index name. fetch_nse handles
        # cookie bootstrap + retries + per-cache-version invalidation.
        from urllib.parse import quote  # noqa: PLC0415
        url = f"/api/equity-stockIndices?index={quote(index_slug)}"

        # NSE intermittently returns None — usually cookie expiry after
        # 30+ minutes of idle, or an Akamai 503 challenge that bot-blocks
        # all 3 retries inside fetch_nse. Re-trying once after a small
        # delay almost always succeeds because the cookie warm-up the
        # previous failure triggered is now finished.
        data = None
        last_err: Optional[str] = None
        for attempt in range(2):
            try:
                data = await self.nse.fetch_nse(url, cache_key, ttl=_ttl())
                if data is not None:
                    break
                last_err = "NSE returned no body (likely cookie / Akamai challenge)"
            except Exception as exc:
                last_err = str(exc)[:120]
                logger.debug("NSE constituents fetch attempt %d failed for %s: %s",
                             attempt, index_slug, last_err)
            if attempt == 0:
                # Brief delay so the cookie warm-up inside fetch_nse has time
                # to settle before we hit it again.
                await asyncio.sleep(1.5)

        # If the NSE bulk endpoint is unreachable, fall back to the per-stock
        # Yahoo path (slower but routes through PriceService's built-in
        # NSE→Yahoo chain, which works even when the bulk index endpoint is
        # Akamai-blocked from this egress IP).
        if data is None:
            logger.warning("NSE constituents fetch exhausted retries for %s: %s "
                           "— trying Yahoo fallback.",
                           index_slug, last_err)
            fb = await self._yahoo_fallback_scan(segment, count)
            if fb is not None:
                return fb
            return {
                "available": False,
                "segment":   segment, "label": label,
                "indexSlug": index_slug,
                "message":   f"NSE feed unreachable AND Yahoo fallback empty: "
                             f"{last_err or 'no response after retries'}",
                "gainers":   [], "losers": [],
            }

        if not isinstance(data, dict):
            logger.warning("Unexpected NSE response type for %s: %s — trying Yahoo fallback.",
                           index_slug, type(data).__name__)
            fb = await self._yahoo_fallback_scan(segment, count)
            if fb is not None:
                return fb
            return {
                "available": False,
                "segment":   segment, "label": label,
                "indexSlug": index_slug,
                "message":   f"NSE returned {type(data).__name__}; Yahoo fallback also empty.",
                "gainers":   [], "losers": [],
            }
        raw = data.get("data") or []
        rows = [r for r in (_row(s) for s in raw) if r is not None]
        if not rows:
            logger.warning("NSE returned empty constituents for %s — trying Yahoo fallback.",
                           index_slug)
            fb = await self._yahoo_fallback_scan(segment, count)
            if fb is not None:
                return fb
            return {
                "available": False,
                "segment":   segment, "label": label,
                "indexSlug": index_slug,
                "message":   "NSE returned 0 constituents and Yahoo fallback also empty.",
                "gainers":   [], "losers": [],
            }

        # Sort by pChange in both directions, slice to `count` each.
        gainers = sorted(rows, key=lambda r: r["pChange"], reverse=True)[:count]
        losers  = sorted(rows, key=lambda r: r["pChange"])[:count]
        # Use the NSE timestamp when it's present — falls back to 'now'
        # so the freshness-pill in the UI has something to render.
        as_of = data.get("timestamp") or _disk._now_ist().isoformat()
        market_state = _disk.current_market_state()
        return {
            "available":    True,
            "segment":      segment,
            "label":        label,
            "indexSlug":    index_slug,
            "asOf":         as_of,
            "marketState":  market_state,
            "totalScanned": len(rows),
            "gainers":      gainers,
            "losers":       losers,
            "servedFrom":   "NSE",
        }

    async def get_all_segments(self, count: int = 10) -> dict:
        """Fetch every cap segment in parallel — used by the Dashboard tab
        on first render so the user gets all four panels in one round-trip
        rather than waiting on serial calls."""
        keys = list(SEGMENT_INDEX.keys())
        results = await asyncio.gather(
            *[self.get_top_movers(k, count=count) for k in keys],
            return_exceptions=True,
        )
        by_segment: dict[str, Any] = {}
        for k, r in zip(keys, results):
            if isinstance(r, Exception):
                by_segment[k] = {
                    "available": False, "segment": k,
                    "message": f"fetch error: {str(r)[:120]}",
                    "gainers": [], "losers": [],
                }
            else:
                by_segment[k] = r
        return {
            "fetchedAt": datetime.now(_disk.IST).isoformat(),
            "segments":  by_segment,
        }
