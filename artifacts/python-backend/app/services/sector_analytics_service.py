"""
Sector Analytics Service
========================
Provides deep-dive analytics for the "Sector Analytics" module:
  - Heatmap data: all sectors with market-cap proxy + multi-period performance
  - Top movers: gainers/losers by timeframe
  - Sector detail: relative strength chart, performance table, valuation,
    profitability, financial health, and constituent stocks table

Data sources: NSE sectors service (live prices) + yfinance (historical + fundamentals)
Cache: fundamentals 4h, performance 15 min, heatmap 5 min
"""

import asyncio
import logging
import time
from datetime import date, timedelta
from typing import Any, Optional

import pandas as pd
import yfinance as yf

from .yahoo_service import YahooService
from .sectors_service import SECTOR_INDICES

logger = logging.getLogger(__name__)

# ── Approximate sector market caps (₹ Lakh Crore) ────────────────────────────
# Used to size heat-map blocks. Updated manually; order doesn't matter.

SECTOR_MARKET_CAP_PROXY: dict[str, float] = {
    "NIFTY BANK":               46.0,
    "NIFTY FINANCIAL SERVICES": 30.0,
    "NIFTY IT":                 35.0,
    "NIFTY OIL AND GAS":        22.0,
    "NIFTY ENERGY":             20.0,
    "NIFTY AUTO":               16.0,
    "NIFTY PHARMA":             12.0,
    "NIFTY FMCG":               11.0,
    "NIFTY PSU BANK":           12.0,
    "NIFTY HEALTHCARE INDEX":   10.0,
    "NIFTY CONSUMER DURABLES":   8.0,
    "NIFTY METAL":               9.0,
    "NIFTY REALTY":              5.0,
    "NIFTY MEDIA":               2.0,
}

# ── Extended constituent stocks (10 per sector, .NS suffix for yfinance) ──────

SECTOR_CONSTITUENTS: dict[str, list[str]] = {
    "NIFTY BANK": [
        "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS",
        "INDUSINDBK.NS", "BANKBARODA.NS", "PNB.NS", "FEDERALBNK.NS", "IDFCFIRSTB.NS",
    ],
    "NIFTY IT": [
        "TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS", "TECHM.NS",
        "LTIM.NS", "MPHASIS.NS", "COFORGE.NS", "PERSISTENT.NS", "LTTS.NS",
    ],
    "NIFTY AUTO": [
        "MARUTI.NS", "TATAMOTORS.NS", "BAJAJ-AUTO.NS", "EICHERMOT.NS", "HEROMOTOCO.NS",
        "M&M.NS", "TVSMOTOR.NS", "BOSCHLTD.NS", "MOTHERSON.NS", "BALKRISIND.NS",
    ],
    "NIFTY PHARMA": [
        "SUNPHARMA.NS", "CIPLA.NS", "DRREDDY.NS", "DIVISLAB.NS", "LUPIN.NS",
        "AUROPHARMA.NS", "TORNTPHARM.NS", "BIOCON.NS", "ALKEM.NS", "GLAXO.NS",
    ],
    "NIFTY FMCG": [
        "HINDUNILVR.NS", "ITC.NS", "BRITANNIA.NS", "NESTLEIND.NS", "DABUR.NS",
        "MARICO.NS", "GODREJCP.NS", "COLPAL.NS", "TATACONSUM.NS", "EMAMILTD.NS",
    ],
    "NIFTY METAL": [
        "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "COALINDIA.NS", "SAIL.NS",
        "VEDL.NS", "NMDC.NS", "APLAPOLLO.NS", "NATIONALUM.NS", "WELCORP.NS",
    ],
    "NIFTY REALTY": [
        "DLF.NS", "GODREJPROP.NS", "OBEROIRLTY.NS", "PRESTIGE.NS", "SOBHA.NS",
        "MAHLIFE.NS", "BRIGADE.NS", "PHOENIXLTD.NS", "LODHA.NS", "SUNTECK.NS",
    ],
    "NIFTY ENERGY": [
        "RELIANCE.NS", "ONGC.NS", "BPCL.NS", "GAIL.NS", "NTPC.NS",
        "POWERGRID.NS", "TATAPOWER.NS", "ADANIGREEN.NS", "ADANIPORTS.NS", "IOC.NS",
    ],
    "NIFTY MEDIA": [
        "ZEEL.NS", "SUNTV.NS", "NAZARA.NS", "PVRINOX.NS", "SAREGAMA.NS",
        "TIPSMUSIC.NS", "TVTODAY.NS", "JAGRAN.NS", "DBCORP.NS", "HATHWAY.NS",
    ],
    "NIFTY FINANCIAL SERVICES": [
        "BAJFINANCE.NS", "BAJAJFINSV.NS", "MUTHOOTFIN.NS", "SBILIFE.NS", "HDFCLIFE.NS",
        "ICICIGI.NS", "ICICIPRULI.NS", "CHOLAFIN.NS", "M&MFIN.NS", "LICHSGFIN.NS",
    ],
    "NIFTY PSU BANK": [
        "SBIN.NS", "BANKBARODA.NS", "PNB.NS", "CANBK.NS", "UNIONBANK.NS",
        "INDIANB.NS", "BANKINDIA.NS", "CENTRALBK.NS", "UCOBANK.NS", "MAHABANK.NS",
    ],
    "NIFTY CONSUMER DURABLES": [
        "TITAN.NS", "HAVELLS.NS", "VOLTAS.NS", "WHIRLPOOL.NS", "BLUESTARCO.NS",
        "CROMPTON.NS", "DIXON.NS", "KALYANKJIL.NS", "KAJARIACER.NS", "BATAINDIA.NS",
    ],
    "NIFTY OIL AND GAS": [
        "RELIANCE.NS", "ONGC.NS", "BPCL.NS", "GAIL.NS", "HINDPETRO.NS",
        "IOC.NS", "PETRONET.NS", "OIL.NS", "MGL.NS", "IGL.NS",
    ],
    "NIFTY HEALTHCARE INDEX": [
        "SUNPHARMA.NS", "APOLLOHOSP.NS", "MAXHEALTH.NS", "FORTIS.NS", "CIPLA.NS",
        "DRREDDY.NS", "METROPOLIS.NS", "THYROCARE.NS", "NH.NS", "LALPATHLAB.NS",
    ],
    # NIFTY 50 is a broad-market index, not a sector. Top 10 weights only,
    # so the Sector Detail page renders meaningfully if anyone navigates here.
    "NIFTY 50": [
        "RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "TCS.NS",
        "ITC.NS", "BHARTIARTL.NS", "LT.NS", "SBIN.NS", "AXISBANK.NS",
    ],
}

# Map nseKey to Yahoo Finance index ticker
SECTOR_YAHOO_TICKER: dict[str, str] = {
    "NIFTY BANK":               "^NSEBANK",
    "NIFTY IT":                 "^CNXIT",
    "NIFTY AUTO":               "^CNXAUTO",
    "NIFTY PHARMA":             "^CNXPHARMA",
    "NIFTY FMCG":               "^CNXFMCG",
    "NIFTY METAL":              "^CNXMETAL",
    "NIFTY REALTY":             "^CNXREALTY",
    "NIFTY ENERGY":             "^CNXENERGY",
    "NIFTY MEDIA":              "^CNXMEDIA",
    "NIFTY FINANCIAL SERVICES": "^CNXFIN",
    "NIFTY PSU BANK":           "^CNXPSUBANK",
    "NIFTY CONSUMER DURABLES":  "^CNXCONSUM",
    "NIFTY OIL AND GAS":        "^CNXOILGAS",
    "NIFTY HEALTHCARE INDEX":   "^CNXHEALTH",
    "NIFTY 50":                 "^NSEI",
}

# ── Cache ─────────────────────────────────────────────────────────────────────

_CACHE: dict[str, dict] = {}
_CACHE_VERSION = 0  # tracks the market-state version of the entries above


def _flush_if_state_changed() -> None:
    """Drop in-memory entries when market state has just transitioned (open↔closed)."""
    global _CACHE_VERSION, _CACHE
    from . import market_cache_service as _disk
    v = _disk.cache_version()
    if v != _CACHE_VERSION:
        _CACHE.clear()
        _CACHE_VERSION = v


def _cache_get(key: str) -> Optional[Any]:
    _flush_if_state_changed()
    e = _CACHE.get(key)
    if e and time.time() < e["expiry"]:
        return e["data"]
    return None


def _cache_set(key: str, data: Any, ttl: int) -> None:
    _flush_if_state_changed()
    _CACHE[key] = {"data": data, "expiry": time.time() + ttl}


# ── Yfinance helpers (run in thread pool to avoid blocking event loop) ────────

async def _yf_info(ticker: str) -> dict:
    cached = _cache_get(f"yfi:{ticker}")
    if cached is not None:
        return cached

    def _empty(reason: Exception | None = None) -> dict:
        """Failure / missing-data shape — every numeric is None so the UI
        renders '—' instead of '₹0' / '0.00%' and rankings exclude it."""
        if reason is not None:
            logger.warning("yf.info failed for %s: %s", ticker, reason)
        return {
            "symbol":         ticker,
            "name":           ticker,
            "price":          None,
            "change1d":       None,
            "marketCap":      None,
            "pe":             None,
            "pb":             None,
            "ps":             None,
            "evEbitda":       None,
            "roe":            None,
            "roa":            None,
            "earningsGrowth": None,
            "revenueGrowth":  None,
            "debtToEquity":   None,
            "netMargin":      None,
            "dividendYield":  None,
            "beta":           None,
            "sector":         None,
            "industry":       None,
        }

    def _fetch():
        try:
            t = yf.Ticker(ticker)
            info = t.info or {}
            # Yahoo Finance reports debtToEquity as a *percentage* (e.g. 50 = 50% = 0.5×).
            # Normalise to a true ratio so the UI can render it as "0.50×".
            de_raw = info.get("debtToEquity")
            de_ratio = (de_raw / 100.0) if isinstance(de_raw, (int, float)) else None
            return {
                "symbol":        ticker,
                "name":          info.get("longName") or info.get("shortName") or ticker,
                "price":         info.get("currentPrice") or info.get("regularMarketPrice"),
                "change1d":      info.get("regularMarketChangePercent"),
                "marketCap":     info.get("marketCap"),
                "pe":            info.get("trailingPE"),
                "pb":            info.get("priceToBook"),
                "ps":            info.get("priceToSalesTrailingTwelveMonths"),
                "evEbitda":      info.get("enterpriseToEbitda"),
                "roe":            info.get("returnOnEquity"),
                "roa":            info.get("returnOnAssets"),
                "earningsGrowth": info.get("earningsGrowth"),
                "revenueGrowth":  info.get("revenueGrowth"),
                "debtToEquity":  de_ratio,
                "netMargin":     info.get("profitMargins"),
                "dividendYield": info.get("dividendYield"),
                "beta":          info.get("beta"),
                "sector":        info.get("sector"),
                "industry":      info.get("industry"),
            }
        except Exception as e:
            return _empty(e)

    data = await asyncio.to_thread(_fetch)
    _cache_set(f"yfi:{ticker}", data, 4 * 3600)
    return data


async def _yf_history(ticker: str, period: str = "1y") -> list[dict]:
    cached = _cache_get(f"yfh:{ticker}:{period}")
    if cached is not None:
        return cached

    # SINGLE-SOURCE OF TRUTH: try the sealed EOD snapshot from disk first
    # (PriceService writes here for every NSE symbol). If present, every
    # consumer of this analytic gets the SAME closes as the quote/history/
    # sectors endpoints. Only fall back to a direct yfinance pull when the
    # disk snapshot is missing (e.g. an index ticker not in our universe).
    from . import market_cache_service as _disk
    period_to_days = {
        "1mo": 35, "3mo": 95, "6mo": 185, "1y": 370, "2y": 740, "5y": 1830,
    }
    days_needed = period_to_days.get(period, 370)
    bare_sym = ticker.replace(".NS", "").replace(".BO", "").upper()
    payload = _disk.load_with_meta(bare_sym, days_needed)
    if payload and payload.get("data"):
        rows = [
            {
                "date":   r.get("date"),
                "open":   r.get("open"),
                "high":   r.get("high"),
                "low":    r.get("low"),
                "close":  r.get("close"),
                "volume": r.get("volume", 0),
            }
            for r in payload["data"]
            if r.get("close") is not None
        ]
        if rows:
            # Cache version is consulted by _cache_set's _flush_if_state_changed
            # so the next market-state transition flushes this entry.
            _cache_set(f"yfh:{ticker}:{period}", rows, 4 * 3600)
            return rows

    def _fetch():
        try:
            # Use Ticker.history() to avoid thread-safety issues with yf.download()
            t = yf.Ticker(ticker)
            df = t.history(period=period, interval="1d", auto_adjust=True)
            if df is None or df.empty:
                return []
            rows = []
            for idx, row in df.iterrows():
                try:
                    close_val = float(row["Close"])
                except (KeyError, TypeError, ValueError):
                    continue
                if close_val > 0:
                    rows.append({"date": idx.strftime("%Y-%m-%d"), "close": close_val})
            return rows
        except Exception as e:
            logger.warning("yf history failed for %s: %s", ticker, e)
            return []

    data = await asyncio.to_thread(_fetch)
    # When the market is closed this fallback history is frozen until the next
    # session, so cache it for hours instead of re-pulling Yahoo every 15 min
    # (the in-memory cache is flushed on the next market-state transition, so
    # this can't bleed into the open session). Keep the short TTL when open, or
    # when the fetch came back empty so a transient Yahoo failure retries soon.
    _ttl = (4 * 3600) if (data and not _disk.is_market_open()) else (15 * 60)
    _cache_set(f"yfh:{ticker}:{period}", data, _ttl)
    return data


def _pct_change_from_history(history: list[dict], days: int) -> Optional[float]:
    if len(history) < 2:
        return None
    end = history[-1]["close"]
    start_idx = max(0, len(history) - days - 1)
    start = history[start_idx]["close"]
    if start <= 0:
        return None
    return round((end - start) / start * 100, 2)


async def _constituent_pct_changes(constituents: list[str]) -> dict[str, Optional[float]]:
    """
    Fallback for sectors whose Yahoo Finance index ticker has no data.
    Fetches 1-year history for up to 5 constituent stocks and returns
    equal-weighted average % changes for 1w / 1m / 1y / YTD.
    """
    if not constituents:
        return {"change1w": None, "change1m": None, "change1y": None, "changeYTD": None}

    hists = await asyncio.gather(
        *[_yf_history(s, "1y") for s in constituents[:5]],
        return_exceptions=True,
    )

    def _avg(days: int) -> Optional[float]:
        vals = [
            _pct_change_from_history(h, days)
            for h in hists
            if not isinstance(h, Exception) and h
        ]
        valid = [v for v in vals if v is not None]
        return round(sum(valid) / len(valid), 2) if valid else None

    def _avg_ytd() -> Optional[float]:
        vals = [
            _ytd_change(h)
            for h in hists
            if not isinstance(h, Exception) and h
        ]
        valid = [v for v in vals if v is not None]
        return round(sum(valid) / len(valid), 2) if valid else None

    return {
        "change1d":  _avg(1),
        "change1w":  _avg(5),
        "change1m":  _avg(21),
        "change1y":  _avg(252),
        "changeYTD": _avg_ytd(),
    }


async def _synthetic_history(constituents: list[str], period: str = "1y") -> list[dict]:
    """
    Build a synthetic sector price series from constituent stocks.
    Each stock is normalised to 100 at its first available date, then
    the normalised series are averaged across all stocks that share
    that date.  Result: [{"date": "YYYY-MM-DD", "close": float}, ...]
    """
    if not constituents:
        return []

    hists = await asyncio.gather(
        *[_yf_history(s, period) for s in constituents[:5]],
        return_exceptions=True,
    )

    valid_hists = [h for h in hists if not isinstance(h, Exception) and len(h) > 5]
    if not valid_hists:
        return []

    # Build a date-keyed map for each stock, normalised to 100 at its first date
    stock_maps: list[dict[str, float]] = []
    for h in valid_hists:
        base = h[0]["close"]
        if not base or base <= 0:
            continue
        stock_maps.append({row["date"]: row["close"] / base * 100.0 for row in h})

    if not stock_maps:
        return []

    # Collect all dates that appear in at least one stock, sorted
    all_dates = sorted({d for m in stock_maps for d in m})

    result: list[dict] = []
    for d in all_dates:
        vals = [m[d] for m in stock_maps if d in m]
        if vals:
            result.append({"date": d, "close": round(sum(vals) / len(vals), 4)})

    return result


def _ytd_change(history: list[dict]) -> Optional[float]:
    if not history:
        return None
    today = date.today()
    jan1 = date(today.year, 1, 1)
    # Find closest date on or after Jan 1
    start_row = next((h for h in history if h["date"] >= jan1.strftime("%Y-%m-%d")), None)
    if not start_row:
        return None
    end = history[-1]["close"]
    start = start_row["close"]
    if start <= 0:
        return None
    return round((end - start) / start * 100, 2)


# ── Main service class ────────────────────────────────────────────────────────

class SectorAnalyticsService:
    def __init__(self, yahoo: YahooService, price=None):
        """price: optional PriceService used to overlay the canonical
        NSE/EOD price/change/previousClose onto each constituent stock,
        so the sector-detail table matches Stock Lookup / Charts / Portfolio.
        """
        self.yahoo = yahoo
        self.price = price

    # ── Heatmap ───────────────────────────────────────────────────────────────

    async def get_heatmap(self, sectors_live: list[dict]) -> list[dict]:
        """
        Return heatmap-ready sector data.
        sectors_live: output of SectorsService.get_all_sectors()
        """
        today_str = date.today().strftime("%Y-%m-%d")
        cache_key_hm = f"heatmap:{today_str}"
        cached = _cache_get(cache_key_hm)
        if cached:
            return cached

        # Fetch 1-year history for all sector indices in parallel
        symbols_needed = [
            (s["symbol"], SECTOR_YAHOO_TICKER.get(s["symbol"], "^NSEI"))
            for s in sectors_live
            if s["symbol"] in SECTOR_MARKET_CAP_PROXY
        ]

        hist_results = await asyncio.gather(
            *[_yf_history(yahoo, "1y") for _, yahoo in symbols_needed],
            return_exceptions=True,
        )

        # For any sector whose Yahoo index returned no usable history, fetch constituent fallback.
        # "No usable" = empty list OR history that's too short to compute a 1W change.
        fallback_tasks = []
        fallback_indices = []
        for i, (nse_sym, _) in enumerate(symbols_needed):
            hist = hist_results[i] if not isinstance(hist_results[i], Exception) else []
            needs_fallback = (not hist) or (_pct_change_from_history(hist, 5) is None)
            if needs_fallback:
                constituents = SECTOR_CONSTITUENTS.get(nse_sym, [])
                fallback_tasks.append(_constituent_pct_changes(constituents))
                fallback_indices.append(i)

        fallback_results = await asyncio.gather(*fallback_tasks, return_exceptions=True) if fallback_tasks else []

        # Map fallback results back to their sector indices
        fallback_map: dict[int, dict] = {}
        for j, fi in enumerate(fallback_indices):
            fb = fallback_results[j]
            fallback_map[fi] = fb if not isinstance(fb, Exception) else {}

        result = []
        for i, (nse_sym, _yahoo) in enumerate(symbols_needed):
            live = next((s for s in sectors_live if s["symbol"] == nse_sym), {})
            hist = hist_results[i] if not isinstance(hist_results[i], Exception) else []
            fb   = fallback_map.get(i, {})

            # Use explicit None checks for fallback (NOT `or`) — a legit 0.0%
            # change must NOT be replaced by the constituent-average fallback.
            def _pref(primary: Optional[float], fallback: Optional[float]) -> Optional[float]:
                return primary if primary is not None else fallback

            # Honest missing-data: when the live sectors feed lacks a field
            # (e.g. NSE sector quote temporarily unavailable), surface None
            # so the UI renders "—" instead of fabricating a flat 0.0%.
            live_last = live.get("lastPrice")
            live_pchg = live.get("pChange")
            # For sectors whose Yahoo index ticker returns no live quote
            # (e.g. NIFTY OIL AND GAS, NIFTY HEALTHCARE INDEX), fall back to
            # the equal-weighted constituent average so the tile is never "—".
            change1d = round(live_pchg, 2) if live_pchg is not None else fb.get("change1d")
            result.append({
                "symbol":    nse_sym,
                "name":      live.get("name", nse_sym),
                "category":  live.get("category", ""),
                "lastPrice": live_last if live_last is not None else None,
                "change1d":  change1d,
                "change1w":  _pref(_pct_change_from_history(hist, 5),   fb.get("change1w")),
                "change1m":  _pref(_pct_change_from_history(hist, 21),  fb.get("change1m")),
                "change3m":  _pct_change_from_history(hist, 63),
                "change6m":  _pct_change_from_history(hist, 126),
                "change1y":  _pref(_pct_change_from_history(hist, 252), fb.get("change1y")),
                "changeYTD": _pref(_ytd_change(hist),                   fb.get("changeYTD")),
                "marketCap": SECTOR_MARKET_CAP_PROXY.get(nse_sym, 5.0),
                "advances":  live.get("advances", 0),
                "declines":  live.get("declines", 0),
            })

        result.sort(key=lambda s: s["marketCap"], reverse=True)
        # When market is closed the data is static until the next trading day —
        # use a long TTL so cold starts after a server restart don't re-fetch
        # 1-year yfinance history for every sector index on every request.
        from . import market_cache_service as _mcs
        hm_ttl = (5 * 60) if _mcs.is_market_open() else (4 * 3600)
        _cache_set(cache_key_hm, result, hm_ttl)
        return result

    # ── Top movers ────────────────────────────────────────────────────────────

    async def get_top_movers(self, heatmap: list[dict], period: str = "1d") -> dict:
        field_map = {
            "1d": "change1d", "1w": "change1w",
            "1m": "change1m", "1y": "change1y",
        }
        field = field_map.get(period, "change1d")
        valid = [s for s in heatmap if s.get(field) is not None]
        sorted_asc = sorted(valid, key=lambda s: s[field])
        sorted_desc = sorted(valid, key=lambda s: s[field], reverse=True)
        return {
            "period":  period,
            "gainers": sorted_desc[:5],
            "losers":  sorted_asc[:5],
        }

    # ── Sector deep-dive ──────────────────────────────────────────────────────

    async def get_sector_detail(self, sector_symbol: str, period: str = "1y") -> Optional[dict]:
        cache_key = f"detail:{sector_symbol}:{period}"
        cached = _cache_get(cache_key)
        if cached:
            return cached

        yahoo_ticker = SECTOR_YAHOO_TICKER.get(sector_symbol)
        if not yahoo_ticker:
            return None

        constituents = SECTOR_CONSTITUENTS.get(sector_symbol, [])

        # Fetch everything in parallel
        top_constituents = constituents[:10]
        sector_hist_task = _yf_history(yahoo_ticker, period)
        nifty_hist_task  = _yf_history("^NSEI", period)
        stock_info_tasks = [_yf_info(s) for s in top_constituents]
        # Canonical NSE/EOD overlay — bare symbol (no .NS) for PriceService
        canonical_tasks = (
            [self.price.get_quote_with_meta(s.replace(".NS", "")) for s in top_constituents]
            if self.price else []
        )

        n = len(top_constituents)
        gathered = await asyncio.gather(
            sector_hist_task, nifty_hist_task,
            *stock_info_tasks, *canonical_tasks,
            return_exceptions=True,
        )
        sector_hist, nifty_hist = gathered[0], gathered[1]
        stock_infos = list(gathered[2 : 2 + n])
        canonicals  = list(gathered[2 + n : 2 + 2 * n]) if canonical_tasks else [None] * n

        if isinstance(sector_hist, Exception):
            sector_hist = []
        if isinstance(nifty_hist, Exception):
            nifty_hist = []
        stock_infos = [s if not isinstance(s, Exception) else {} for s in stock_infos]

        # Overlay canonical NSE quote onto each constituent so the sector-detail
        # table never contradicts Stock Lookup / Charts / Portfolio. Only
        # overwrite a yfinance value when the canonical source actually
        # provides one — never replace a real number with None.
        for info, canon in zip(stock_infos, canonicals):
            if isinstance(canon, Exception) or not canon:
                continue
            q = (canon or {}).get("quote") or {}
            if q.get("lastPrice") is not None:
                info["price"] = q.get("lastPrice")
                if q.get("pChange") is not None:
                    info["change1d"] = q.get("pChange")
                if q.get("previousClose") is not None:
                    info["previousClose"] = q.get("previousClose")
                # Provenance: `source` = originating provider (NSE/YAHOO),
                # `servedFrom` = which layer returned it on this call
                # (PRICE_SERVICE for live, DISK_EOD when EOD overlay applied).
                info["_priceSource"]      = canon.get("source")
                info["_priceServedFrom"]  = canon.get("servedFrom")

        # Drop empty fundamentals shells so they don't pollute aggregates / sorting.
        stock_infos = [s for s in stock_infos if s and s.get("symbol")]

        # If Yahoo Finance has no index history for this sector (e.g. delisted
        # ticker like ^CNXOILGAS / ^CNXHEALTH), synthesize a price series from
        # constituent stocks (normalised equal-weight avg). Surface a flag so
        # the UI can disclose this — the Performance and Relative Strength
        # numbers are then approximations rather than the official index.
        history_synthetic = False
        if len(sector_hist) < 10 and constituents:
            sector_hist = await _synthetic_history(constituents, period)
            history_synthetic = True

        # Use the canonical sector name from SECTOR_INDICES (e.g. "Nifty IT")
        # instead of `sector_symbol.title()` which mangles acronyms ("Nifty It").
        canonical_name = next(
            (s["name"] for s in SECTOR_INDICES if s["symbol"] == sector_symbol),
            sector_symbol.title(),
        )

        result = {
            "symbol":       sector_symbol,
            "name":         canonical_name,
            "marketCap":    SECTOR_MARKET_CAP_PROXY.get(sector_symbol, 5.0),
            "historySynthetic": history_synthetic,
            "relativeStrength": self._compute_rs_chart(sector_hist, nifty_hist),
            "performance":  self._compute_performance(sector_hist),
            "valuation":    self._compute_valuation(stock_infos),
            "profitability": self._compute_profitability(stock_infos),
            "financialHealth": self._compute_financial_health(stock_infos),
            "constituents": self._build_constituents_table(stock_infos),
            "topGainers":   sorted(
                [s for s in stock_infos if s.get("change1d") is not None],
                key=lambda s: s.get("change1d", 0), reverse=True
            )[:5],
            "topLosers":    sorted(
                [s for s in stock_infos if s.get("change1d") is not None],
                key=lambda s: s.get("change1d", 0)
            )[:5],
        }

        # Detail is frozen when the market is closed → cache 4h instead of
        # 15 min (version-flush clears it at the next market-state transition,
        # so the open session always recomputes). Same data, fewer recomputes.
        from . import market_cache_service as _mcs  # noqa: PLC0415
        _cache_set(cache_key, result, (15 * 60) if _mcs.is_market_open() else (4 * 3600))
        return result

    # ── Helper computation methods ────────────────────────────────────────────

    def _compute_rs_chart(self, sector_hist: list[dict], nifty_hist: list[dict]) -> list[dict]:
        """Compute relative strength ratio: sector / nifty, normalized to 100."""
        if not sector_hist or not nifty_hist:
            return []

        nifty_map = {h["date"]: h["close"] for h in nifty_hist if h["close"] > 0}
        pairs = [
            (h["date"], h["close"], nifty_map.get(h["date"]))
            for h in sector_hist
            if h["close"] > 0 and nifty_map.get(h["date"])
        ]
        if not pairs:
            return []

        base_ratio = pairs[0][1] / pairs[0][2]
        if base_ratio <= 0:
            return []

        return [
            {
                "date":  d,
                "ratio": round((s / n) / base_ratio * 100, 4),
                "sector": round(s, 2),
                "nifty":  round(n, 2),
            }
            for d, s, n in pairs
        ]

    def _compute_performance(self, hist: list[dict]) -> dict:
        return {
            "1W":   _pct_change_from_history(hist, 5),
            "1M":   _pct_change_from_history(hist, 21),
            "3M":   _pct_change_from_history(hist, 63),
            "6M":   _pct_change_from_history(hist, 126),
            "1Y":   _pct_change_from_history(hist, 252),
            "YTD":  _ytd_change(hist),
        }

    def _compute_valuation(self, stocks: list[dict]) -> dict:
        """Market-cap-weighted aggregate valuation ratios."""
        total_cap = sum(s.get("marketCap", 0) or 0 for s in stocks)
        if total_cap <= 0:
            return {"pe": None, "pb": None, "ps": None, "evEbitda": None,
                    "method": "cap_weighted", "sampleSize": 0}

        def w_avg(field: str) -> tuple[Optional[float], int]:
            num = denom = 0.0
            n = 0
            for s in stocks:
                cap = s.get("marketCap") or 0
                val = s.get(field)
                if cap > 0 and val and val > 0:
                    num   += cap * val
                    denom += cap
                    n     += 1
            return (round(num / denom, 2) if denom > 0 else None), n

        pe,       pe_n  = w_avg("pe")
        pb,       pb_n  = w_avg("pb")
        ps,       ps_n  = w_avg("ps")
        evEbitda, ev_n  = w_avg("evEbitda")

        # Equal-weighted for comparison
        def e_avg(field: str) -> Optional[float]:
            vals = [s.get(field) for s in stocks if s.get(field) and s[field] > 0]
            return round(sum(vals) / len(vals), 2) if vals else None

        # Headline sampleSize uses the strongest contributor (P/E) so the
        # frontend "Based on N constituents" reflects actual coverage, not
        # the total number of stocks pulled.
        return {
            "pe":           pe,
            "pb":           pb,
            "ps":           ps,
            "evEbitda":     evEbitda,
            "pe_equal":     e_avg("pe"),
            "pb_equal":     e_avg("pb"),
            "ps_equal":     e_avg("ps"),
            "evEbitda_equal": e_avg("evEbitda"),
            "method":       "cap_weighted",
            "sampleSize":   pe_n,
            "peSampleSize":       pe_n,
            "pbSampleSize":       pb_n,
            "psSampleSize":       ps_n,
            "evEbitdaSampleSize": ev_n,
        }

    def _compute_profitability(self, stocks: list[dict]) -> dict:
        total_cap = sum(s.get("marketCap", 0) or 0 for s in stocks)

        def w_avg(field: str) -> Optional[float]:
            num = denom = 0.0
            for s in stocks:
                cap = s.get("marketCap") or 0
                val = s.get(field)
                if cap > 0 and val is not None:
                    num   += cap * val
                    denom += cap
            return round(num / denom * 100, 2) if denom > 0 else None

        return {
            "netMargin": w_avg("netMargin"),
            "roe":       w_avg("roe"),
            "sampleSize": len([s for s in stocks if s.get("netMargin") is not None]),
        }

    def _compute_financial_health(self, stocks: list[dict]) -> dict:
        de_vals = [s["debtToEquity"] for s in stocks if s.get("debtToEquity") is not None and s["debtToEquity"] >= 0]
        roa_vals = [s["roa"] for s in stocks if s.get("roa") is not None]
        eg_vals  = [s["earningsGrowth"] for s in stocks if s.get("earningsGrowth") is not None]
        rg_vals  = [s["revenueGrowth"]  for s in stocks if s.get("revenueGrowth")  is not None]

        def avg(vals: list) -> float | None:
            return round(sum(vals) / len(vals), 4) if vals else None

        return {
            "debtToEquity":  round(sum(de_vals) / len(de_vals), 2) if de_vals else None,
            "sampleSize":    len(de_vals),
            "roa":           avg(roa_vals),
            "roaSampleSize": len(roa_vals),
            "earningsGrowth": avg(eg_vals),
            "revenueGrowth":  avg(rg_vals),
            # isBanking: True when no stock has a valid D/E but ROA data exists
            # — tells the frontend to show banking-specific health metrics instead
            "isBanking":     len(de_vals) == 0 and len(roa_vals) > 0,
        }

    def _build_constituents_table(self, stocks: list[dict]) -> list[dict]:
        rows = []
        for s in stocks:
            rows.append({
                "symbol":        s.get("symbol", ""),
                "name":          s.get("name", s.get("symbol", "")),
                "price":         s.get("price"),
                "change1d":      s.get("change1d"),
                "marketCap":     s.get("marketCap"),
                "pe":            s.get("pe"),
                "pb":            s.get("pb"),
                "ps":            s.get("ps"),
                "evEbitda":      s.get("evEbitda"),
                "roe":           s.get("roe"),
                "roa":           s.get("roa"),
                "earningsGrowth": s.get("earningsGrowth"),
                "revenueGrowth":  s.get("revenueGrowth"),
                "debtToEquity":  s.get("debtToEquity"),
                "dividendYield": s.get("dividendYield"),
                "beta":          s.get("beta"),
                "industry":      s.get("industry"),
                "priceSource":     s.get("_priceSource"),
                "priceServedFrom": s.get("_priceServedFrom"),
            })
        # Drop rows that have neither a price nor any fundamentals — these
        # are pure failure shells (e.g. delisted/wrong tickers in the
        # constituent list) and would render as a row of "—"s otherwise.
        rows = [
            r for r in rows
            if r.get("price") is not None or r.get("marketCap") is not None
            or r.get("pe") is not None or r.get("pb") is not None
        ]
        return sorted(rows, key=lambda r: r.get("marketCap") or 0, reverse=True)
