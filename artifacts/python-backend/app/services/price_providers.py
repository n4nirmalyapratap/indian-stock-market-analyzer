"""Standardized price provider pattern — ported from OpenBB.

Why
---
The old `PriceService` had two nearly-identical fallback chains (one
for quotes, one for history), each with a hand-coded try/except per
source. Adding a 7th source touched ~12 places. Subtle behavior
differences (which providers cache to disk, which skip indices, which
have a minimum row gate) lived as inline conditionals scattered across
hundreds of lines.

This module formalizes the contract:

  * One Pydantic `Quote` shape every provider returns.
  * One Pydantic `Bar` shape every provider returns for history.
  * One `PriceProvider` abstract base class with two methods
    (`get_quote`, `get_historical`) plus a handful of declarative
    attributes (`name`, `skip_for_indices`, `min_history_rows`,
    `disk_cache_safe`).
  * One `PriceProviderChain` that walks an ordered list of providers
    and returns the first hit.

Adding a new provider is now a single file: subclass `PriceProvider`,
implement two async methods, append the instance to the chain. Zero
changes to `PriceService` itself.

What's intentionally NOT here
-----------------------------
  * The disk cache (`market_cache_service`) and the EOD overlay logic
    in `PriceService.get_quote_with_meta` stay in PriceService. They're
    cross-cutting concerns, not per-provider.
  * The divergence sanity check (NSE-vs-Yahoo cross-validation) also
    stays in PriceService — it's a post-processing step on the chain's
    output, not a provider concern.
  * The history-derived synthetic quote IS modelled as a provider
    (`HistoryDerivedProvider`) because it cleanly fits — it just needs
    a reference to the PriceService to call `get_historical_data`.
"""
from __future__ import annotations

import asyncio
import importlib
import logging
from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger("price_providers")


# ── Cross-provider data contracts ───────────────────────────────────────────


class Bar(BaseModel):
    """One daily OHLCV bar. Identical shape across every provider —
    callers don't have to know which source produced the row."""
    model_config = ConfigDict(extra="ignore")

    date:   str         # ISO YYYY-MM-DD
    open:   float
    high:   float
    low:    float
    close:  float
    volume: int


class Quote(BaseModel):
    """A single-symbol quote snapshot. Most fields are optional because
    only NSE supplies the rich industry/sector metadata; other providers
    leave them None.

    The `source` field is the provider's `name`, populated by the
    adapter — it's how PriceService stamps provenance on the response."""
    model_config = ConfigDict(extra="ignore")

    symbol:           str
    companyName:      Optional[str]   = None
    lastPrice:        Optional[float] = None
    change:           Optional[float] = None
    pChange:          Optional[float] = None
    open:             Optional[float] = None
    dayHigh:          Optional[float] = None
    dayLow:           Optional[float] = None
    previousClose:    Optional[float] = None
    volume:           Optional[int]   = None

    # NSE-rich extras (other providers leave these None).
    industry:         Optional[str]   = None
    sector:           Optional[str]   = None
    macroSector:      Optional[str]   = None
    basicIndustry:    Optional[str]   = None
    fiftyTwoWeekHigh: Optional[float] = None
    fiftyTwoWeekLow:  Optional[float] = None
    marketCap:        Optional[float] = None
    issuedSize:       Optional[float] = None

    # Provenance. Set by the adapter; the chain uses this to populate
    # the envelope's `source` field.
    source:           str


# ── Base provider ───────────────────────────────────────────────────────────


class PriceProvider(ABC):
    """Contract every price source implements. Declarative attributes
    on the subclass tell the chain how to handle this source (whether
    to skip for indices, minimum row gate for history, whether the
    chain may persist its output to the user-agnostic disk cache).

    Subclass example:

        class MyProvider(PriceProvider):
            name             = "MYSOURCE"
            skip_for_indices = True
            min_history_rows = 10
            disk_cache_safe  = True

            async def get_quote(self, symbol, *, user_id=None): ...
            async def get_historical(self, symbol, days, *, user_id=None): ...
    """

    # Display/provenance name. Mirrors the existing source strings used
    # by the frontend ("NSE", "BSE", "YAHOO", "TWELVE_DATA", "STOOQ",
    # "HISTORY"). Broker tier overrides per-call with the actual broker
    # slug uppercased.
    name: str = ""

    # NSE's historical endpoint doesn't serve indices — set True to
    # skip this provider when the symbol is an index.
    skip_for_indices: bool = False

    # Minimum bar count from this provider before its history is
    # accepted. NSE/BSE = 10 (reject thin/empty stubs); fallbacks = 1.
    min_history_rows: int = 1

    # Whether PriceService may write this provider's output to the
    # user-agnostic disk cache. False for broker-tier providers because
    # broker data is per-user and would leak cross-tenant.
    disk_cache_safe: bool = True

    @abstractmethod
    async def get_quote(
        self,
        symbol: str,
        *,
        user_id: Optional[str] = None,
    ) -> Optional[Quote]:
        """Return a `Quote` for `symbol` or None when this source has
        nothing. Implementations should swallow their own network/parse
        errors and just return None — the chain will move on."""
        ...

    @abstractmethod
    async def get_historical(
        self,
        symbol: str,
        days:   int,
        *,
        user_id: Optional[str] = None,
    ) -> list[Bar]:
        """Return up to `days` of daily bars (oldest → newest) or []
        when this source has nothing."""
        ...


# ── Adapter helpers ─────────────────────────────────────────────────────────


def _bars_from_dicts(rows: list[dict]) -> list[Bar]:
    """Normalize the per-provider list-of-dicts response into Bars.
    Quietly drops any row missing fields or with non-numeric values —
    we'd rather return a shorter clean list than poison the chart with
    a row of NaNs."""
    out: list[Bar] = []
    for r in rows or []:
        try:
            out.append(Bar(
                date   = str(r["date"])[:10],
                open   = float(r.get("open")   or 0),
                high   = float(r.get("high")   or 0),
                low    = float(r.get("low")    or 0),
                close  = float(r.get("close")  or 0),
                volume = int(r.get("volume")   or 0),
            ))
        except Exception:
            continue
    return out


def _bars_to_dicts(bars: list[Bar]) -> list[dict]:
    """Inverse of `_bars_from_dicts` — back to the dict shape every
    downstream component (disk cache, technical indicators, frontend
    chart payload) expects."""
    return [b.model_dump() for b in bars]


def _quote_from_dict(d: dict, symbol: str, source: str) -> Quote:
    """Build a `Quote` from a provider's raw response dict, ensuring
    `symbol` and `source` are always the canonical values supplied by
    the adapter (provider responses often include their own `symbol` /
    `source` keys; the explicit args win)."""
    payload = {**d, "symbol": symbol, "source": source}
    return Quote(**payload)


# ── Provider: user-configured brokers (Dhan / Zerodha / Upstox / …) ─────────


_BROKER_MODULES: dict[str, str] = {
    "dhan":      "app.services.dhan_service",
    "zerodha":   "app.services.zerodha_service",
    "upstox":    "app.services.upstox_service",
    "angel_one": "app.services.angel_one_service",
    "groww":     "app.services.groww_service",
}


class UserBrokerProvider(PriceProvider):
    """Walks every active broker the user has configured, returning
    the first successful quote/history. Sits at the top of the chain
    so authenticated users get their own broker's data before we hit
    any public source.

    Per-call source name — when Dhan answers we stamp `DHAN`, when
    Zerodha answers we stamp `ZERODHA`. The class-level `name` is just
    "USER_BROKERS" for debug logging.

    Broker data is NEVER written to the user-agnostic disk cache; we
    set `disk_cache_safe = False` to communicate that to the chain.
    """
    name             = "USER_BROKERS"
    skip_for_indices = False
    min_history_rows = 1
    disk_cache_safe  = False

    def _list_active(self, user_id: str):
        try:
            from app.lib.broker_keys import list_active_creds_for_user  # noqa: PLC0415
            return list_active_creds_for_user(user_id)
        except Exception as exc:
            logger.debug("broker_keys lookup failed for %s: %s", user_id, exc)
            return []

    async def get_quote(self, symbol, *, user_id=None):
        if not user_id:
            return None
        active = self._list_active(user_id)
        if not active:
            return None
        for broker, creds in active:
            mod_path = _BROKER_MODULES.get(broker)
            if not mod_path:
                continue
            try:
                m  = importlib.import_module(mod_path)
                fn = getattr(m, "get_quote", None)
                if fn is None:
                    continue
                q = await fn(symbol, creds)
                if q:
                    return _quote_from_dict(q, symbol, broker.upper())
            except Exception as exc:
                logger.debug("broker %s get_quote failed for %s: %s",
                             broker, symbol, str(exc)[:120])
                continue
        return None

    async def get_historical(self, symbol, days, *, user_id=None):
        if not user_id:
            return []
        active = self._list_active(user_id)
        if not active:
            return []
        for broker, creds in active:
            mod_path = _BROKER_MODULES.get(broker)
            if not mod_path:
                continue
            try:
                m  = importlib.import_module(mod_path)
                fn = getattr(m, "get_historical", None)
                if fn is None:
                    continue
                bars = await fn(symbol, days, creds)
                if bars:
                    return _bars_from_dicts(bars)
            except Exception as exc:
                logger.debug("broker %s get_historical failed for %s: %s",
                             broker, symbol, str(exc)[:120])
                continue
        return []


# ── Provider: NSE Bhav Copy (EOD archive) ────────────────────────────────────


class NseBhavcopyProvider(PriceProvider):
    """NSE official EOD data sourced from the CM Bhav Copy archives.

    Behaviour is market-state-aware:

      • Market CLOSED  — returns bars from the local SQLite store built by
                         nightly archive downloads.  Fast, zero network call
                         at query time.  Sits before NSE live and Yahoo in the
                         chain, so it wins every historical request when the
                         exchange is shut.

      • Market OPEN    — returns [] so the chain falls through to Yahoo, which
                         has today's intraday candle.  We never want yesterday's
                         EOD close as the "last" bar while the market is live.

      • get_quote      — always None (EOD only; live quotes go to BSE/Yahoo).

    Indices are skipped — they are not in the CM bhav copy files.
    """

    name             = "NSE_BHAV"
    skip_for_indices = True   # indices not present in CM bhav copy
    min_history_rows = 10
    disk_cache_safe  = True

    async def get_quote(self, symbol, *, user_id=None):
        return None  # EOD only; live quotes fall through to BSE/Yahoo

    async def get_historical(self, symbol, days, *, user_id=None):
        from .market_cache_service import is_market_open                  # noqa: PLC0415
        if is_market_open():
            # Yield to Yahoo — it has today's live intraday bars; we don't.
            return []

        from . import nse_equity_bhavcopy_service as _bhav               # noqa: PLC0415
        from datetime import date, timedelta                              # noqa: PLC0415

        to_date   = date.today()
        from_date = to_date - timedelta(days=days + 14)  # +14 buffer for holidays

        try:
            rows = await asyncio.to_thread(
                _bhav.get_bars, symbol, from_date, to_date
            )
        except Exception as exc:
            logger.debug("NseBhavcopyProvider.get_bars(%s) error: %s", symbol, exc)
            return []

        if not rows:
            return []

        return [
            Bar(
                date   = r["trade_date"],
                open   = float(r["open"]   or 0),
                high   = float(r["high"]   or 0),
                low    = float(r["low"]    or 0),
                close  = float(r["close"]  or 0),
                volume = int(r["volume"]   or 0),
            )
            for r in rows
        ]


# ── Provider: NSE ───────────────────────────────────────────────────────────


class NseProvider(PriceProvider):
    """Primary Indian source — official exchange data via NSE's
    cookie-authenticated JSON endpoints. Rich enough to populate the
    NSE-only extras on the Quote model (industry / sector / market cap
    derived from issuedSize, etc.)."""
    name             = "NSE"
    skip_for_indices = True   # `/api/historical/cm/equity` doesn't serve indices
    min_history_rows = 10     # reject thin stubs that would poison the disk cache
    disk_cache_safe  = True

    def __init__(self, nse_service):
        self.nse = nse_service

    async def get_quote(self, symbol, *, user_id=None):
        try:
            nse_quote = await self.nse.get_stock_quote(symbol)
        except Exception as exc:
            logger.debug("NSE quote fetch failed for %s: %s", symbol, str(exc)[:120])
            return None
        if not (nse_quote and nse_quote.get("priceInfo")):
            return None
        p        = nse_quote["priceInfo"]
        info     = nse_quote.get("info") or nse_quote.get("metadata") or {}
        ind_info = nse_quote.get("industryInfo") or {}
        sec_info = nse_quote.get("securityInfo") or {}
        week_hl  = p.get("weekHighLow", {}) or {}
        # NSE doesn't ship marketCap directly but issuedSize × lastPrice is
        # the same authoritative number nseindia.com uses.
        last_price = p.get("lastPrice") or 0
        issued     = sec_info.get("issuedSize") or 0
        derived_mcap = (
            float(issued) * float(last_price)
            if issued and last_price else None
        )
        return Quote(
            symbol           = symbol,
            companyName      = info.get("companyName", symbol),
            industry         = ind_info.get("industry") or info.get("industry"),
            # NSE's `industryInfo.sector` is the real sector classification —
            # `info.sector` is almost always blank. Prefer the rich source.
            sector           = ind_info.get("sector") or info.get("sector"),
            macroSector      = ind_info.get("macro"),
            basicIndustry    = ind_info.get("basicIndustry"),
            lastPrice        = last_price,
            change           = p.get("change"),
            pChange          = p.get("pChange"),
            open             = p.get("open"),
            dayHigh          = p.get("intraDayHighLow", {}).get("max") or p.get("dayHigh"),
            dayLow           = p.get("intraDayHighLow", {}).get("min") or p.get("dayLow"),
            previousClose    = p.get("previousClose"),
            volume           = p.get("totalTradedVolume"),
            fiftyTwoWeekHigh = week_hl.get("max"),
            fiftyTwoWeekLow  = week_hl.get("min"),
            marketCap        = derived_mcap,
            issuedSize       = float(issued) if issued else None,
            source           = self.name,
        )

    async def get_historical(self, symbol, days, *, user_id=None):
        try:
            rows = await self.nse.get_historical_data(symbol, days)
        except Exception as exc:
            logger.debug("NSE historical failed for %s: %s", symbol, str(exc)[:120])
            return []
        return _bars_from_dicts(rows or [])


# ── Provider: BSE ───────────────────────────────────────────────────────────


class BseProvider(PriceProvider):
    """Second-exchange Indian fallback — most NSE stocks are dual-listed
    and BSE's infra is independent, so this works when NSE is Akamai-
    blocked. Free, no API key."""
    name             = "BSE"
    skip_for_indices = False
    min_history_rows = 10
    disk_cache_safe  = True

    async def get_quote(self, symbol, *, user_id=None):
        try:
            from . import bse_service as _bse  # noqa: PLC0415
            q = await _bse.get_quote(symbol)
        except Exception as exc:
            logger.debug("BSE quote failed for %s: %s", symbol, str(exc)[:120])
            return None
        if not q:
            return None
        # BSE service already returns a flat quote dict.
        return _quote_from_dict(q, symbol, self.name)

    async def get_historical(self, symbol, days, *, user_id=None):
        try:
            from . import bse_service as _bse  # noqa: PLC0415
            rows = await _bse.get_historical(symbol, days)
        except Exception as exc:
            logger.debug("BSE historical failed for %s: %s", symbol, str(exc)[:120])
            return []
        return _bars_from_dicts(rows or [])


# ── Provider: Yahoo Finance ─────────────────────────────────────────────────


class YahooProvider(PriceProvider):
    """Global fallback. Reliable for most symbols, handles indices,
    handles post-merger / dual-listed names that NSE/BSE may miss."""
    name             = "YAHOO"
    skip_for_indices = False
    min_history_rows = 1
    disk_cache_safe  = True

    def __init__(self, yahoo_service):
        self.yahoo = yahoo_service

    async def get_quote(self, symbol, *, user_id=None):
        try:
            q = await self.yahoo.get_quote(symbol)
        except Exception as exc:
            logger.debug("Yahoo quote failed for %s: %s", symbol, str(exc)[:120])
            return None
        if not q:
            return None
        return _quote_from_dict(q, symbol, self.name)

    async def get_historical(self, symbol, days, *, user_id=None):
        try:
            rows = await self.yahoo.get_historical_data(symbol, days)
        except Exception as exc:
            logger.debug("Yahoo historical failed for %s: %s", symbol, str(exc)[:120])
            return []
        return _bars_from_dicts(rows or [])


# ── Provider: Twelve Data ───────────────────────────────────────────────────


class TwelveDataProvider(PriceProvider):
    """Free 800 calls/day with admin-set API key. Independent infra so
    it survives Yahoo outages. No-ops silently when the key isn't set."""
    name             = "TWELVE_DATA"
    skip_for_indices = False
    min_history_rows = 1
    disk_cache_safe  = True

    async def get_quote(self, symbol, *, user_id=None):
        try:
            from . import twelve_data_service as _td  # noqa: PLC0415
            q = await _td.get_quote(symbol)
        except Exception as exc:
            logger.debug("Twelve Data quote failed for %s: %s", symbol, str(exc)[:120])
            return None
        if not q:
            return None
        return _quote_from_dict(q, symbol, self.name)

    async def get_historical(self, symbol, days, *, user_id=None):
        try:
            from . import twelve_data_service as _td  # noqa: PLC0415
            rows = await _td.get_historical(symbol, days)
        except Exception as exc:
            logger.debug("Twelve Data historical failed for %s: %s", symbol, str(exc)[:120])
            return []
        return _bars_from_dicts(rows or [])


# ── Provider: Stooq ─────────────────────────────────────────────────────────


class StooqProvider(PriceProvider):
    """Polish-based free EOD data. Uncorrelated infra from NSE/Yahoo,
    has 10+ years of Indian EOD when reachable. Last public fallback
    before history-derived synthesis."""
    name             = "STOOQ"
    skip_for_indices = False
    min_history_rows = 1
    disk_cache_safe  = True

    async def get_quote(self, symbol, *, user_id=None):
        try:
            from . import stooq_service as _stooq  # noqa: PLC0415
            q = await _stooq.get_quote(symbol)
        except Exception as exc:
            logger.debug("Stooq quote failed for %s: %s", symbol, str(exc)[:120])
            return None
        if not q:
            return None
        return _quote_from_dict(q, symbol, self.name)

    async def get_historical(self, symbol, days, *, user_id=None):
        try:
            from . import stooq_service as _stooq  # noqa: PLC0415
            rows = await _stooq.get_historical_csv(symbol, days)
        except Exception as exc:
            logger.debug("Stooq historical failed for %s: %s", symbol, str(exc)[:120])
            return []
        return _bars_from_dicts(rows or [])


# ── Provider: history-derived synthesis ─────────────────────────────────────


class HistoryDerivedProvider(PriceProvider):
    """Last-resort quote synthesizer. When every live source returns
    nothing (e.g. post-merger BSE-only tickers that Yahoo misclassifies),
    we pull the last EOD bar and synthesise a minimal quote so the UI
    shows the official close instead of ₹0.

    For history requests this provider returns []. By the time the
    chain reaches us for history, NSE/BSE/Yahoo/Twelve Data/Stooq have
    already failed; we have nothing left to try."""
    name             = "HISTORY"
    skip_for_indices = False
    min_history_rows = 1
    disk_cache_safe  = False  # synthesized — don't reseal as authoritative

    def __init__(self, history_lookup):
        # `history_lookup(symbol, days) -> list[Bar]` injected by the
        # chain so we don't have a circular import with PriceService.
        self._history_lookup = history_lookup

    async def get_quote(self, symbol, *, user_id=None):
        try:
            bars = await self._history_lookup(symbol, 5)
        except Exception as exc:
            logger.debug("History-derived lookup failed for %s: %s", symbol, str(exc)[:120])
            return None
        if not bars or len(bars) < 2:
            return None
        last, prev = bars[-1], bars[-2]
        eod_close = last.close
        eod_prev  = prev.close
        if not eod_close:
            return None
        change  = round(eod_close - eod_prev, 2) if eod_prev else 0
        pchange = (
            round(change / eod_prev * 100, 4)
            if eod_prev else 0
        )
        logger.info(
            "Quote for %s synthesised from history (live providers all empty).",
            symbol,
        )
        return Quote(
            symbol        = symbol,
            companyName   = symbol,
            lastPrice     = eod_close,
            change        = change,
            pChange       = pchange,
            open          = last.open,
            dayHigh       = last.high,
            dayLow        = last.low,
            previousClose = eod_prev,
            volume        = last.volume,
            source        = self.name,
        )

    async def get_historical(self, symbol, days, *, user_id=None):
        return []


# ── Chain orchestrator ──────────────────────────────────────────────────────


class PriceProviderChain:
    """Holds an ordered list of providers and walks them in priority
    order. The first provider whose `get_quote` returns a non-None
    `Quote` wins; same for `get_historical` with the per-provider
    `min_history_rows` gate applied."""

    def __init__(self, providers: list[PriceProvider]):
        self.providers = providers

    async def fetch_quote(
        self,
        symbol:  str,
        *,
        user_id: Optional[str] = None,
    ) -> Optional[Quote]:
        # Canonicalise BEFORE handing to any provider. Universe lists
        # historically used legacy short names (BATA, INFOEDGE) that
        # don't exist on NSE/BSE/Yahoo; the alias map in symbol_map.py
        # translates them to real tickers (BATAINDIA, NAUKRI). Doing
        # this at the chain layer means every provider gets the right
        # symbol for free — one change, seven beneficiaries.
        from ..lib.symbol_map import canonical_symbol  # noqa: PLC0415
        canon = canonical_symbol(symbol)
        for p in self.providers:
            try:
                q = await p.get_quote(canon, user_id=user_id)
            except Exception as exc:
                logger.debug("provider %s raised on get_quote(%s): %s",
                             p.name, canon, str(exc)[:120])
                continue
            if q is not None:
                # Preserve the CALLER's symbol on the returned Quote
                # so downstream callers don't suddenly see "BATAINDIA"
                # when they asked for "BATA" — the alias is internal.
                if canon != symbol and q.symbol == canon:
                    q.symbol = symbol.upper().strip() or symbol
                return q
        return None

    async def fetch_history(
        self,
        symbol:       str,
        days:         int,
        *,
        user_id:      Optional[str] = None,
        is_index:     bool = False,
    ) -> tuple[list[Bar], Optional[PriceProvider]]:
        """Returns `(bars, winning_provider)`. The provider is exposed
        so PriceService can consult its `disk_cache_safe` flag before
        persisting."""
        from ..lib.symbol_map import canonical_symbol  # noqa: PLC0415
        canon = canonical_symbol(symbol)
        for p in self.providers:
            if is_index and p.skip_for_indices:
                continue
            try:
                bars = await p.get_historical(canon, days, user_id=user_id)
            except Exception as exc:
                logger.debug("provider %s raised on get_historical(%s): %s",
                             p.name, canon, str(exc)[:120])
                continue
            if bars and len(bars) >= p.min_history_rows:
                return bars, p
        return [], None
