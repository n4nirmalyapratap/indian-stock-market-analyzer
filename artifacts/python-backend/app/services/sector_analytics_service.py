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
        "MAHLIFE.NS", "BRIGADE.NS", "PHOENIXLTD.NS", "SUNITY.NS", "SUNTECK.NS",
    ],
    "NIFTY ENERGY": [
        "RELIANCE.NS", "ONGC.NS", "BPCL.NS", "GAIL.NS", "NTPC.NS",
        "POWERGRID.NS", "TATAPOWER.NS", "ADANIGREEN.NS", "ADANIPORTS.NS", "IOC.NS",
    ],
    "NIFTY MEDIA": [
        "ZEEL.NS", "SUNTV.NS", "NAZARA.NS", "PVR.NS", "SAREGAMA.NS",
        "TIPS.NS", "TVTODAY.NS", "JAGRAN.NS", "DBCORP.NS", "HATHWAY.NS",
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
        "CROMPTON.NS", "BATAINDIA.NS", "RAJESHEXPO.NS", "VMART.NS", "AARTISIND.NS",
    ],
    "NIFTY OIL AND GAS": [
        "RELIANCE.NS", "ONGC.NS", "BPCL.NS", "GAIL.NS", "HINDPETRO.NS",
        "IOC.NS", "PETRONET.NS", "OIL.NS", "MGL.NS", "IGL.NS",
    ],
    "NIFTY HEALTHCARE INDEX": [
        "SUNPHARMA.NS", "APOLLOHOSP.NS", "MAXHEALTH.NS", "FORTIS.NS", "CIPLA.NS",
        "DRREDDY.NS", "METROPOLIS.NS", "THYROCARE.NS", "NARAYANA.NS", "LALPATHLAB.NS",
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


def _cache_get(key: str) -> Optional[Any]:
    e = _CACHE.get(key)
    if e and time.time() < e["expiry"]:
        return e["data"]
    return None


def _cache_set(key: str, data: Any, ttl: int) -> None:
    _CACHE[key] = {"data": data, "expiry": time.time() + ttl}


# ── Yfinance helpers (run in thread pool to avoid blocking event loop) ────────

async def _yf_info(ticker: str) -> dict:
    cached = _cache_get(f"yfi:{ticker}")
    if cached is not None:
        return cached

    def _fetch():
        try:
            t = yf.Ticker(ticker)
            info = t.info or {}
            return {
                "symbol":        ticker,
                "name":          info.get("longName") or info.get("shortName") or ticker,
                "price":         info.get("currentPrice") or info.get("regularMarketPrice") or 0,
                "change1d":      info.get("regularMarketChangePercent") or 0,
                "marketCap":     info.get("marketCap") or 0,
                "pe":            info.get("trailingPE"),
                "pb":            info.get("priceToBook"),
                "ps":            info.get("priceToSalesTrailingTwelveMonths"),
                "evEbitda":      info.get("enterpriseToEbitda"),
                "roe":           info.get("returnOnEquity"),
                "debtToEquity":  info.get("debtToEquity"),
                "netMargin":     info.get("profitMargins"),
                "dividendYield": info.get("dividendYield"),
                "beta":          info.get("beta"),
                "sector":        info.get("sector"),
                "industry":      info.get("industry"),
            }
        except Exception as e:
            logger.warning("yf.info failed for %s: %s", ticker, e)
            return {"symbol": ticker, "price": 0, "marketCap": 0}

    data = await asyncio.to_thread(_fetch)
    _cache_set(f"yfi:{ticker}", data, 4 * 3600)
    return data


async def _yf_history(ticker: str, period: str = "1y") -> list[dict]:
    cached = _cache_get(f"yfh:{ticker}:{period}")
    if cached is not None:
        return cached

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
    _cache_set(f"yfh:{ticker}:{period}", data, 15 * 60)
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
    def __init__(self, yahoo: YahooService):
        self.yahoo = yahoo

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

        result = []
        for i, (nse_sym, _yahoo) in enumerate(symbols_needed):
            live = next((s for s in sectors_live if s["symbol"] == nse_sym), {})
            hist = hist_results[i] if not isinstance(hist_results[i], Exception) else []

            result.append({
                "symbol":    nse_sym,
                "name":      live.get("name", nse_sym),
                "category":  live.get("category", ""),
                "lastPrice": live.get("lastPrice", 0),
                "change1d":  round(live.get("pChange", 0), 2),
                "change1w":  _pct_change_from_history(hist, 5),
                "change1m":  _pct_change_from_history(hist, 21),
                "change3m":  _pct_change_from_history(hist, 63),
                "change6m":  _pct_change_from_history(hist, 126),
                "change1y":  _pct_change_from_history(hist, 252),
                "changeYTD": _ytd_change(hist),
                "marketCap": SECTOR_MARKET_CAP_PROXY.get(nse_sym, 5.0),
                "advances":  live.get("advances", 0),
                "declines":  live.get("declines", 0),
            })

        result.sort(key=lambda s: s["marketCap"], reverse=True)
        _cache_set(cache_key_hm, result, 5 * 60)
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
        sector_hist_task = _yf_history(yahoo_ticker, period)
        nifty_hist_task  = _yf_history("^NSEI", period)
        stock_info_tasks = [_yf_info(s) for s in constituents[:10]]

        sector_hist, nifty_hist, *stock_infos = await asyncio.gather(
            sector_hist_task, nifty_hist_task, *stock_info_tasks,
            return_exceptions=True,
        )

        if isinstance(sector_hist, Exception):
            sector_hist = []
        if isinstance(nifty_hist, Exception):
            nifty_hist = []
        stock_infos = [s for s in stock_infos if not isinstance(s, Exception)]

        result = {
            "symbol":       sector_symbol,
            "name":         sector_symbol.title(),
            "marketCap":    SECTOR_MARKET_CAP_PROXY.get(sector_symbol, 5.0),
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

        _cache_set(cache_key, result, 15 * 60)
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
            return {"pe": None, "pb": None, "ps": None, "evEbitda": None, "method": "cap_weighted"}

        def w_avg(field: str) -> Optional[float]:
            num = denom = 0.0
            for s in stocks:
                cap = s.get("marketCap") or 0
                val = s.get(field)
                if cap > 0 and val and val > 0:
                    num   += cap * val
                    denom += cap
            return round(num / denom, 2) if denom > 0 else None

        pe       = w_avg("pe")
        pb       = w_avg("pb")
        ps       = w_avg("ps")
        evEbitda = w_avg("evEbitda")

        # Equal-weighted for comparison
        def e_avg(field: str) -> Optional[float]:
            vals = [s.get(field) for s in stocks if s.get(field) and s[field] > 0]
            return round(sum(vals) / len(vals), 2) if vals else None

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
            "sampleSize":   len(stocks),
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
        vals = [s.get("debtToEquity") for s in stocks if s.get("debtToEquity") is not None and s["debtToEquity"] >= 0]
        avg_de = round(sum(vals) / len(vals), 2) if vals else None
        return {
            "debtToEquity": avg_de,
            "sampleSize":   len(vals),
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
                "debtToEquity":  s.get("debtToEquity"),
                "dividendYield": s.get("dividendYield"),
                "beta":          s.get("beta"),
                "industry":      s.get("industry"),
            })
        return sorted(rows, key=lambda r: r.get("marketCap") or 0, reverse=True)
