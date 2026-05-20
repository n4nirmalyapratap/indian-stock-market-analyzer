"""
PriceService — single source of truth for price data.

Fetch priority for daily OHLCV:
  1. Disk cache (when market is closed AND we have an EOD-sealed snapshot)
  2. NSE India historical API (cookies method — official Indian exchange data)
  3. Yahoo Finance (fallback — global, reliable but secondary)

Intraday/sub-daily candles always go to Yahoo (NSE only exposes EOD daily).

Quotes go NSE primary → Yahoo fallback. Each quote is returned with provenance
metadata: `source` ("NSE" | "YAHOO"), `asOf` (ISO IST timestamp), `marketState`.

Every public method returns provenance so the UI can show "NSE • 5 min ago • Closed".
Never call yahoo_service / nse_service directly — always go through PriceService.
"""

import logging
from typing import Optional

from .nse_service import NseService
from .yahoo_service import YahooService
from . import market_cache_service as _disk

logger = logging.getLogger(__name__)


class PriceService:
    def __init__(self, nse: NseService, yahoo: YahooService):
        self.nse   = nse
        self.yahoo = yahoo

    # ── Daily OHLCV (used by every scanner / chart / technical analysis) ─────

    async def get_historical_data(
        self,
        symbol: str,
        days: int = 90,
        force_refresh: bool = False,
    ) -> list[dict]:
        """
        Returns a list of daily OHLCV dicts sorted oldest → newest:
          { date, open, high, low, close, volume }

        Priority: EOD-sealed disk cache → NSE → Yahoo.
        When `force_refresh=True` the disk cache is bypassed (used by
        market_cache_service.seal_eod_for_today_if_overdue).
        """
        from ..lib.symbol_map import is_index_symbol as _is_index
        is_idx = _is_index(symbol)

        # Minimum acceptable row count for a cached payload — only enforced
        # for index symbols, because sectors_service writes a 2-row OHLC stub
        # to the same canonical path for sector cards. Equities can have any
        # row count (newly listed names may legitimately have <5 bars), so
        # we don't gate them.
        min_rows = max(5, min(days // 4, 20)) if (is_idx and days >= 10) else 1

        # 1. Disk cache — only when market is closed AND we have a sealed snapshot
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

        # 2. NSE India (primary — official exchange data via cookie method).
        #    Skip for indices: NSE's `/api/historical/cm/equity` doesn't serve
        #    them and would either return empty or a thin stub that poisons
        #    the disk cache.
        if not is_idx:
            try:
                nse_data = await self.nse.get_historical_data(symbol, days)
                if nse_data and len(nse_data) >= 10:
                    _disk.save_to_disk(symbol, days, nse_data, source="NSE")
                    return nse_data
            except Exception as e:
                logger.debug("NSE historical fetch failed for %s: %s", symbol, e)

        # 3. Yahoo Finance (fallback)
        yahoo_data = await self.yahoo.get_historical_data(symbol, days)
        if yahoo_data:
            _disk.save_to_disk(symbol, days, yahoo_data, source="YAHOO")
        return yahoo_data or []

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

    async def get_quote(self, symbol: str) -> Optional[dict]:
        """
        Real-time quote — NSE primary, Yahoo fallback.
        Returns the bare quote dict (back-compat). Use `get_quote_with_meta`
        when you also need provenance.
        """
        snap = await self.get_quote_with_meta(symbol)
        return snap.get("quote") if snap else None

    async def get_quote_with_meta(self, symbol: str) -> Optional[dict]:
        """Returns `{quote, source, asOf, marketState}` or None.

        Crucially — when the market is closed and we have an EOD-sealed
        snapshot on disk, `lastPrice` is overlaid from the last sealed
        candle so the quote, history, and sector pages all show the
        same official close.
        """
        sym = symbol.upper()
        market_state = _disk.current_market_state()

        snap: Optional[dict] = None

        # 1. NSE primary
        try:
            nse_quote = await self.nse.get_stock_quote(sym)
            if nse_quote and nse_quote.get("priceInfo"):
                p    = nse_quote["priceInfo"]
                info = nse_quote.get("info") or nse_quote.get("metadata") or {}
                # NSE exposes the *real* sector classification in
                # `industryInfo.sector` — `info.sector` is almost always blank.
                # Falling through gives "Unknown" which makes sector
                # concentration meaningless, so prefer the rich source.
                ind_info = nse_quote.get("industryInfo") or {}
                sec_info = nse_quote.get("securityInfo") or {}
                week_high = p.get("weekHighLow", {}) or {}
                # Market cap = issuedSize (shares outstanding) × lastPrice.
                # NSE doesn't ship marketCap directly but issuedSize is the
                # exact same authoritative number that nseindia.com uses.
                last_price = p.get("lastPrice") or 0
                issued = sec_info.get("issuedSize") or 0
                derived_mcap = (
                    float(issued) * float(last_price)
                    if issued and last_price else None
                )
                quote = {
                    "symbol":         sym,
                    "companyName":    info.get("companyName", sym),
                    "industry":       ind_info.get("industry") or info.get("industry"),
                    "sector":         ind_info.get("sector") or info.get("sector"),
                    "macroSector":    ind_info.get("macro"),
                    "basicIndustry":  ind_info.get("basicIndustry"),
                    "lastPrice":      last_price,
                    "change":         p.get("change"),
                    "pChange":        p.get("pChange"),
                    "open":           p.get("open"),
                    "dayHigh":        p.get("intraDayHighLow", {}).get("max") or p.get("dayHigh"),
                    "dayLow":         p.get("intraDayHighLow", {}).get("min") or p.get("dayLow"),
                    "previousClose":  p.get("previousClose"),
                    "volume":         p.get("totalTradedVolume"),
                    "fiftyTwoWeekHigh": week_high.get("max"),
                    "fiftyTwoWeekLow":  week_high.get("min"),
                    "marketCap":      derived_mcap,
                    "issuedSize":     float(issued) if issued else None,
                    "source":         "NSE",
                }
                snap = {
                    "quote":       quote,
                    "source":      "NSE",
                    "asOf":        _disk._now_ist().isoformat(),
                    "marketState": market_state,
                }
        except Exception as e:
            logger.debug("NSE quote failed for %s: %s", sym, e)

        # 2. Yahoo fallback
        if snap is None:
            y = await self.yahoo.get_quote(sym)
            if y:
                y.setdefault("source", "YAHOO")
                snap = {
                    "quote":       y,
                    "source":      "YAHOO",
                    "asOf":        _disk._now_ist().isoformat(),
                    "marketState": market_state,
                }

        # 2b. History-derived synthetic quote — last resort when both NSE and
        # Yahoo return no usable price (e.g. BSE-only tickers that Yahoo
        # misidentifies post-merger, like LTIM→540005.BO).  We pull the most
        # recent historical bar from PriceService (which DOES succeed via the
        # symbol_map BSE override) and synthesise a minimal quote so the
        # watchlist / details panel shows the correct EOD close instead of ₹0.
        # 2b applies in ALL market states — during open hours LTIM-style tickers
        # still have no live feed (NSE can't serve them, Yahoo returns None price).
        # History-derived is the only honest option; source="HISTORY_DERIVED" tells
        # the UI it is EOD data, not a live price.
        if snap is None:
            try:
                bars = await self.get_historical_data(sym, 5)
                if bars and len(bars) >= 2:
                    last = bars[-1]
                    prev = bars[-2]
                    eod_close  = float(last.get("close") or 0)
                    eod_prev   = float(prev.get("close") or 0)
                    if eod_close:
                        synth_change  = round(eod_close - eod_prev, 2) if eod_prev else 0
                        synth_pchange = (
                            round(synth_change / eod_prev * 100, 4)
                            if eod_prev else 0
                        )
                        synth_quote = {
                            "symbol":       sym,
                            "companyName":  sym,
                            "lastPrice":    eod_close,
                            "change":       synth_change,
                            "pChange":      synth_pchange,
                            "open":         float(last.get("open") or 0),
                            "dayHigh":      float(last.get("high") or 0),
                            "dayLow":       float(last.get("low") or 0),
                            "previousClose": eod_prev,
                            "volume":       int(last.get("volume") or 0),
                            "source":       "HISTORY",
                            "servedFrom":   "HISTORY_DERIVED",
                        }
                        snap = {
                            "quote":       synth_quote,
                            "source":      "HISTORY",
                            "servedFrom":  "HISTORY_DERIVED",
                            "asOf":        last.get("date", _disk._now_ist().isoformat()),
                            "marketState": market_state,
                        }
                        logger.info(
                            "Quote for %s synthesised from history (Yahoo/NSE both "
                            "returned no price — likely post-merger BSE-only ticker).",
                            sym,
                        )
            except Exception as _he:
                logger.debug("History-derived quote fallback failed for %s: %s", sym, _he)

        if snap is None:
            return None

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
