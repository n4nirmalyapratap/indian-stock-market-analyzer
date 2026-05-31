"""
PriceService — single source of truth for price data.

Architecture (post-refactor, Jan 2026)
--------------------------------------
The multi-source fallback chain that used to live as nested try/except
blocks here now lives in `price_providers.py`, which exposes:

  * `Quote` / `Bar` — Pydantic data contracts every provider returns.
  * `PriceProvider` — abstract base with `get_quote` + `get_historical`.
  * Six provider adapters (UserBroker → NSE → BSE → Yahoo → Twelve Data
    → Stooq → HistoryDerived).
  * `PriceProviderChain` — orchestrator that walks providers in
    priority order and returns the first hit.

Adding a 7th data source is now ONE new file in `price_providers.py`
(subclass `PriceProvider`, implement two async methods, append to the
chain). Nothing in this file needs to change.

What stays here
---------------
The chain returns raw quote/history data. PriceService adds the
cross-cutting concerns the chain doesn't know about:

  * Disk cache read/write (`market_cache_service`)
  * EOD overlay (replace live `lastPrice` with sealed close when market
    is closed and we have a sealed snapshot)
  * NSE-vs-Yahoo divergence sanity check (post-process)
  * Intraday / range / dataframe convenience helpers

Public API contract (unchanged from pre-refactor)
-------------------------------------------------
  * `get_historical_data(symbol, days, user_id) -> list[dict]`
  * `get_historical_with_meta(symbol, days) -> dict`
  * `get_quote(symbol, user_id) -> dict | None`
  * `get_quote_with_meta(symbol, user_id) -> dict | None`
  * `get_intraday_history(symbol, period, interval) -> dict`
  * `get_range_history(symbol, start, end, interval) -> dict`
  * `get_history_dataframe(symbol, days) -> DataFrame`

Same return shapes, same provenance strings, same call sites. Never
call yahoo_service / nse_service directly — always go through here.
"""

import logging
from typing import Optional

from .nse_service import NseService
from .yahoo_service import YahooService
from . import market_cache_service as _disk
from . import price_providers as _pp

logger = logging.getLogger(__name__)


class PriceService:
    def __init__(self, nse: NseService, yahoo: YahooService):
        self.nse   = nse
        self.yahoo = yahoo
        # Build the provider chain. Order = priority (top of list runs
        # first). HistoryDerivedProvider lives last and uses a back-
        # reference to this instance so it can synthesise a quote from
        # the historical chain when every live source is empty.
        self._chain = _pp.PriceProviderChain([
            _pp.UserBrokerProvider(),
            _pp.NseProvider(self.nse),
            _pp.BseProvider(),
            _pp.YahooProvider(self.yahoo),
            _pp.TwelveDataProvider(),
            _pp.StooqProvider(),
            _pp.HistoryDerivedProvider(self._history_bars_for_synth),
        ])

    async def _history_bars_for_synth(self, symbol: str, days: int) -> list[_pp.Bar]:
        """Helper passed to HistoryDerivedProvider. Returns the LIVE
        chain's history output (i.e. the chain minus the synthesizer
        itself) as Bars, so the synthesizer can use them to construct a
        last-resort quote without infinitely recursing into itself."""
        rows = await self.get_historical_data(symbol, days)
        return [_pp.Bar(**r) for r in rows] if rows else []

    # ── Daily OHLCV (used by every scanner / chart / technical analysis) ─────

    async def get_historical_data(
        self,
        symbol: str,
        days: int = 90,
        force_refresh: bool = False,
        user_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Returns a list of daily OHLCV dicts sorted oldest → newest:
          { date, open, high, low, close, volume }

        Order: EOD-sealed disk cache → provider chain (brokers → NSE →
        BSE → Yahoo → Twelve Data → Stooq). When `force_refresh=True`
        the disk cache is bypassed (used by
        market_cache_service.seal_eod_for_today_if_overdue).
        """
        from ..lib.symbol_map import is_index_symbol as _is_index
        is_idx = _is_index(symbol)

        # Minimum acceptable row count for a cached payload — only enforced
        # for index symbols, because sectors_service writes a 2-row OHLC stub
        # to the same canonical path for sector cards. Equities can have any
        # row count (newly listed names may legitimately have <5 bars).
        min_rows = max(5, min(days // 4, 20)) if (is_idx and days >= 10) else 1

        # Disk cache — closed-market only, returns EOD-sealed bars without
        # touching any provider. Skipped when `force_refresh=True` (called
        # by the seal-EOD job that fetches live and overwrites the cache).
        if not force_refresh and not _disk.is_market_open():
            payload = _disk.load_with_meta(symbol, days)
            cached_rows = payload.get("data") if payload else None
            if (
                payload
                and payload.get("eodSealed")
                and isinstance(cached_rows, list)
                and len(cached_rows) >= min_rows
            ):
                return cached_rows

        # Walk the provider chain. `is_index` skips providers (NSE) whose
        # historical endpoint doesn't serve indices; each provider's
        # `min_history_rows` gate rejects thin/empty stubs.
        bars, winner = await self._chain.fetch_history(
            symbol, days, user_id=user_id, is_index=is_idx,
        )
        if not bars:
            return []
        rows = _pp._bars_to_dicts(bars)
        # Persist to the user-agnostic disk cache only when the winning
        # provider is safe to share across tenants (brokers are not —
        # their data is per-user).
        if winner is not None and winner.disk_cache_safe:
            _disk.save_to_disk(symbol, days, rows, source=winner.name)
        return rows

    async def get_historical_with_meta(self, symbol: str, days: int = 90) -> dict:
        """Same as `get_historical_data` but returns provenance metadata."""
        # Try disk first to surface its provenance
        if not _disk.is_market_open():
            payload = _disk.load_with_meta(symbol, days)
            if payload and payload.get("eodSealed") and payload.get("data"):
                return {
                    "data":        payload["data"],
                    "source":      payload.get("source") or "DISK",
                    "asOf":        payload.get("savedAt"),
                    "marketState": _disk.current_market_state(),
                    "eodSealed":   True,
                    "eodDate":     payload.get("eodDate"),
                }

        data = await self.get_historical_data(symbol, days)
        payload = _disk.load_with_meta(symbol, days) or {}
        return {
            "data":        data,
            "source":      payload.get("source") or "LIVE",
            "asOf":        payload.get("savedAt"),
            "marketState": _disk.current_market_state(),
            "eodSealed":   bool(payload.get("eodSealed")),
            "eodDate":     payload.get("eodDate"),
        }

    # ── Quote (single price snapshot) ─────────────────────────────────────────

    async def get_quote(self, symbol: str, user_id: Optional[str] = None) -> Optional[dict]:
        """
        Real-time quote — NSE primary, Yahoo fallback.
        Returns the bare quote dict (back-compat). Use `get_quote_with_meta`
        when you also need provenance.

        Pass `user_id` to enable the user's configured broker tier as the
        highest-priority source (Dhan/Zerodha/Upstox/Angel One/Groww).
        """
        snap = await self.get_quote_with_meta(symbol, user_id=user_id)
        return snap.get("quote") if snap else None

    async def get_quote_with_meta(self, symbol: str, user_id: Optional[str] = None) -> Optional[dict]:
        """Returns `{quote, source, asOf, marketState}` or None.

        Crucially — when the market is closed and we have an EOD-sealed
        snapshot on disk, `lastPrice` is overlaid from the last sealed
        candle so the quote, history, and sector pages all show the
        same official close.
        """
        sym = symbol.upper()
        market_state = _disk.current_market_state()

        # Walk the provider chain. First non-None Quote wins. Sources
        # tried, top → bottom:
        #   UserBrokerProvider (per-broker if `user_id`)
        #   NseProvider → BseProvider → YahooProvider
        #   TwelveDataProvider → StooqProvider
        #   HistoryDerivedProvider (last-resort synthesis from EOD bars)
        # Each provider swallows its own errors and returns None on
        # failure, so the chain stays loud-but-graceful.
        quote_obj = await self._chain.fetch_quote(sym, user_id=user_id)
        if quote_obj is None:
            return None

        snap = {
            "quote":       quote_obj.model_dump(exclude_none=True),
            "source":      quote_obj.source,
            "asOf":        _disk._now_ist().isoformat(),
            "marketState": market_state,
        }
        # The synthesised history-derived quote needs the extra
        # `servedFrom` provenance the old code path stamped, plus the
        # `eodDate` so the UI's freshness pill renders the correct
        # bar date instead of "now".
        if quote_obj.source == "HISTORY":
            snap["servedFrom"] = "HISTORY_DERIVED"
            snap["quote"]["servedFrom"] = "HISTORY_DERIVED"

        # 3. EOD overlay — when market is closed AND we have an EOD-sealed
        # snapshot on disk, replace the live `lastPrice` with the last sealed
        # candle's close. This guarantees the quote endpoint, the history
        # endpoint, and the sector endpoint all return the same number.
        #
        # CRITICAL: at the close-transition window the on-disk snapshot may
        # still be intraday (eodSealed=False). We force a seal here so the
        # quote /history /sectors path all converge to the SAME official
        # close on the very first post-close request.
        if not _disk.is_market_open():
            try:
                payload = _disk.load_with_meta(sym, 30)
                if not (payload and payload.get("eodSealed")):
                    await _disk.seal_eod_for_today_if_overdue(self, symbols=[sym])
            except Exception as _se:
                logger.debug("EOD seal-before-quote failed for %s: %s", sym, _se)
            payload = _disk.load_with_meta(sym, 30)
            if payload and payload.get("eodSealed") and payload.get("data"):
                rows = payload["data"]
                last = rows[-1] if rows else None
                prev = rows[-2] if len(rows) >= 2 else None
                if last and last.get("close") is not None:
                    eod_close = round(float(last["close"]), 2)
                    eod_prev  = round(float(prev["close"]), 2) if prev and prev.get("close") is not None else None
                    q = snap["quote"]
                    q["lastPrice"]     = eod_close
                    if eod_prev is not None:
                        q["previousClose"] = eod_prev
                        q["change"]        = round(eod_close - eod_prev, 2)
                        # Guard against the pathological eod_prev == 0 (would
                        # divide by zero). Surface None instead of pretending
                        # the change was 0% — the UI's formatPctChange will
                        # render "—" so we don't lie about a missing number.
                        q["pChange"]       = (
                            round((eod_close - eod_prev) / eod_prev * 100, 4)
                            if eod_prev else None
                        )
                    # Provenance contract:
                    #   `source`     = the original provider that produced the
                    #                  number (preserved from the cached
                    #                  payload — NSE if NSE sealed it, YAHOO
                    #                  if Yahoo did).
                    #   `servedFrom` = the layer that returned it on this call
                    #                  (DISK_EOD when overlay applied, else
                    #                  PRICE_SERVICE for live).
                    overlay_source     = payload.get("source") or snap["source"]
                    q["source"]        = overlay_source
                    q["servedFrom"]    = "DISK_EOD"
                    snap["source"]     = overlay_source
                    snap["servedFrom"] = "DISK_EOD"
                    snap["asOf"]       = payload.get("savedAt") or snap["asOf"]
                    snap["eodSealed"]  = True
                    snap["eodDate"]    = payload.get("eodDate")

            # 4. NSE-vs-Yahoo divergence sanity check (closed-market only).
            # Both providers should agree on the official close. If they don't,
            # log a warning and surface the divergence in the response so the
            # admin audit endpoint and the UI freshness pill can flag it.
            try:
                second_q = None
                # NSE-vs-Yahoo cross-check: pull the OTHER provider's number.
                # `source` is now always the originating provider (NSE/YAHOO),
                # never the cache layer, so this comparison is well-defined.
                if snap["source"] == "NSE":
                    yq = await self.yahoo.get_quote(sym)
                    second_q = yq.get("lastPrice") if yq else None
                else:
                    nq = await self.nse.get_stock_quote(sym)
                    if nq and nq.get("priceInfo"):
                        second_q = nq["priceInfo"].get("lastPrice")
                primary = snap["quote"].get("lastPrice")
                if primary is not None and second_q is not None and primary > 0:
                    diff     = round(abs(primary - second_q), 4)
                    diff_pct = round(diff / primary * 100, 4)
                    snap["divergence"] = {
                        "otherClose": second_q,
                        "diff":       diff,
                        "diffPct":    diff_pct,
                        "preferred":  "NSE",
                    }
                    if diff > 0.05 and diff_pct > 0.1:
                        logger.warning(
                            "Quote divergence for %s: primary=%s other=%s diff=%s%% (preferring NSE)",
                            sym, primary, second_q, diff_pct,
                        )
            except Exception as _e:
                logger.debug("Divergence check failed for %s: %s", sym, _e)

        return snap

    # ── Intraday / chart history (any interval) ───────────────────────────────

    async def get_intraday_history(
        self,
        symbol: str,
        period: str = "1mo",
        interval: str = "1d",
    ) -> dict:
        """
        Chart candles at any interval/period for the chart UI.
        Returns `{candles, companyName, currency, source, asOf, marketState}`.

        For interval=='1d' (daily) we prefer NSE / disk-cached EOD data so it
        matches every other page; for sub-daily intervals we always go to Yahoo
        (NSE only exposes EOD).
        """
        market_state = _disk.current_market_state()

        if interval == "1d":
            # Translate period → days for the daily aggregator
            period_to_days = {
                "1d": 5, "5d": 10, "1mo": 35, "3mo": 95, "6mo": 185,
                "1y": 370, "2y": 740, "5y": 1830, "10y": 3660, "max": 36500,
            }
            days = period_to_days.get(period, 95)
            data = await self.get_historical_data(symbol, days)
            payload = _disk.load_with_meta(symbol, days) or {}
            candles = []
            from datetime import datetime as _dt
            for d in data:
                try:
                    ts = int(_dt.strptime(d["date"], "%Y-%m-%d").timestamp())
                except Exception:
                    continue
                candles.append({
                    "time":   ts,
                    "open":   round(float(d.get("open")  or 0), 2),
                    "high":   round(float(d.get("high")  or 0), 2),
                    "low":    round(float(d.get("low")   or 0), 2),
                    "close":  round(float(d.get("close") or 0), 2),
                    "volume": int(d.get("volume") or 0),
                })
            return {
                "candles":     candles,
                "companyName": symbol.upper(),
                "currency":    "INR",
                "source":      payload.get("source") or "NSE",
                "asOf":        payload.get("savedAt"),
                "marketState": market_state,
                "eodSealed":   bool(payload.get("eodSealed")),
                "eodDate":     payload.get("eodDate"),
            }

        # Sub-daily → Yahoo (NSE exposes only EOD)
        chart = await self.yahoo.get_intraday_chart(symbol, period=period, interval=interval)
        chart.update({
            "asOf":        _disk._now_ist().isoformat(),
            "marketState": market_state,
        })
        return chart

    # ── Custom date-range history (used by chart range picker) ───────────────

    async def get_range_history(
        self,
        symbol: str,
        start: str,
        end: str,
        interval: str = "1d",
    ) -> dict:
        """Yahoo-backed range fetcher (NSE doesn't expose arbitrary windows).

        Routed through PriceService so callers don't talk to yfinance directly
        and so the response carries the same provenance contract as every
        other market-data endpoint.
        """
        import asyncio as _asyncio
        import yfinance as yf
        from ..lib.symbol_map import yahoo_candidates as _yc

        market_state = _disk.current_market_state()
        sym = symbol.upper()

        def _fetch():
            for tk_sym in _yc(sym):
                try:
                    tk = yf.Ticker(tk_sym)
                    hist = tk.history(start=start, end=end, interval=interval, auto_adjust=True)
                    if not hist.empty:
                        return tk.info, hist
                except Exception:
                    continue
            return {}, None

        info, hist = await _asyncio.to_thread(_fetch)
        if hist is None or hist.empty:
            return {
                "candles":     [],
                "companyName": sym,
                "currency":    "INR",
                "source":      "YAHOO",
                "asOf":        _disk._now_ist().isoformat(),
                "marketState": market_state,
                "eodSealed":   not _disk.is_market_open(),
                "eodDate":     _disk._eod_date_for(market_state),
            }

        candles = []
        for dt_idx, row in hist.iterrows():
            try:
                candles.append({
                    "time":   int(dt_idx.timestamp()),
                    "open":   round(float(row["Open"]),  2),
                    "high":   round(float(row["High"]),  2),
                    "low":    round(float(row["Low"]),   2),
                    "close":  round(float(row["Close"]), 2),
                    "volume": int(row.get("Volume", 0)),
                })
            except Exception:
                continue

        return {
            "candles":     candles,
            "companyName": info.get("longName") or info.get("shortName") or sym,
            "currency":    info.get("currency", "INR"),
            "source":      "YAHOO",
            "asOf":        _disk._now_ist().isoformat(),
            "marketState": market_state,
            "eodSealed":   not _disk.is_market_open(),
            "eodDate":     _disk._eod_date_for(market_state),
        }

    # ── Daily OHLCV as a pandas DataFrame (for indicator libraries) ──────────

    async def get_history_dataframe(self, symbol: str, days: int = 500):
        """Convenience helper for technical-analysis libraries (`ta`, etc.)."""
        import pandas as pd
        rows = await self.get_historical_data(symbol, days)
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df["Date"]   = pd.to_datetime(df["date"])
        df["Open"]   = df["open"].astype(float)
        df["High"]   = df["high"].astype(float)
        df["Low"]    = df["low"].astype(float)
        df["Close"]  = df["close"].astype(float)
        df["Volume"] = df["volume"].astype(float)
        df = df.set_index("Date").sort_index()
        return df[["Open", "High", "Low", "Close", "Volume"]]
