"""
Insights router — endpoints for the /insights section of the user app.

Real data sources used (rest return a clean unavailable empty-state):
- Heatmap, Market Valuation, Signals  → yfinance (cached on disk after EOD)
- Company Filings                    → BSE Corporate Announcements JSON API
- MF Holdings                        → AMFI NAVAll text feed (portal.amfiindia.com)

Endpoints:
- GET /insights/indices              (curated index codes + labels)
- GET /insights/heatmap              (heatmap of index constituents)
- GET /insights/company-filings      (BSE corporate announcements)
- GET /insights/mf-holdings          (AMFI scheme NAVs, with category/AMC filters)
- GET /insights/signals              (RSI / MA-cross / momentum signals)
- GET /insights/market-valuation     (PE proxy time-series for indices)
- GET /insights/index-valuation      (alias of market-valuation)
- GET /insights/fo-ban               (NSE MWPL — usually unavailable from cloud)
- GET /insights/top-deliveries       (NSE bhavcopy — unavailable)
- GET /insights/fii-dii              (NSE participant CSV — unavailable)
- GET /insights/slbm, /mtf, /ipos    (placeholders, see message)

Heavy yfinance loops are parallelised across a 16-worker thread pool and the
result is cached for 5 minutes.
"""
from __future__ import annotations
import asyncio
import logging
import time
import os
import json
from typing import Any
from concurrent.futures import ThreadPoolExecutor

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from ..services import market_cache_service as mcache
from ..services.nse_service    import NseService
from ..services.yahoo_service  import YahooService
from ..services.price_service  import PriceService
from ..services.macro_service  import MacroService

logger = logging.getLogger("insights")
router = APIRouter(prefix="/insights", tags=["insights"])

# ── Single PriceService instance shared by every insights endpoint ───────────
# Insights MUST read prices through PriceService so heatmap / signals /
# market-valuation use the SAME provider/timepoint as /stocks and /sectors.
_nse   = NseService()
_yahoo = YahooService()
_price = PriceService(_nse, _yahoo)
_macro = MacroService(_yahoo)


def _closes_from_history(rows: list[dict]) -> list[float]:
    """Extract a list of daily closes from PriceService.get_historical_data
    rows ({date,open,high,low,close,volume})."""
    return [float(r.get("close", 0.0)) for r in (rows or []) if isinstance(r, dict) and r.get("close") is not None]

_executor = ThreadPoolExecutor(max_workers=16)
_cache: dict[str, tuple[float, Any, int]] = {}  # (timestamp, value, cacheVersion)
DEFAULT_TTL = 300              # 5 min for yfinance / fast-changing data
LONG_TTL    = 60 * 60 * 6      # 6 h for AMFI / BSE end-of-day data


def _meta(served_from: str = "INSIGHTS_ENGINE") -> dict:
    """Canonical provenance contract — same shape as every other route's meta."""
    state = mcache.current_market_state()
    return {
        "source":       "NSE",
        "servedFrom":   served_from,
        "asOf":         mcache._now_ist().isoformat(),
        "marketState":  state,
        "eodSealed":    state in ("CLOSED", "WEEKEND"),
        "eodDate":      mcache._eod_date_for(state),
        "cacheVersion": mcache.cache_version(),
    }


def _cache_get(key: str, ttl: int = DEFAULT_TTL):
    """TTL- AND cache-version-aware lookup. The version flush guarantees
    insights surfaces snap to the freshly sealed EOD close at market close."""
    hit = _cache.get(key)
    if not hit:
        return None
    ts, value, ver = hit
    if ver != mcache.cache_version():
        # Market state transitioned — force a re-fetch.
        _cache.pop(key, None)
        return None
    if (time.time() - ts) >= ttl:
        return None
    return value


def _cache_set(key: str, value: Any):
    _cache[key] = (time.time(), value, mcache.cache_version())


# ────────────────────────────────────────────────────────────────────────────
# Index → constituents (Yahoo Finance tickers)
# ────────────────────────────────────────────────────────────────────────────
NIFTY50 = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","BHARTIARTL.NS","ICICIBANK.NS","INFY.NS","SBIN.NS",
    "BAJFINANCE.NS","HINDUNILVR.NS","ITC.NS","LT.NS","KOTAKBANK.NS","HCLTECH.NS","SUNPHARMA.NS",
    "MARUTI.NS","AXISBANK.NS","NTPC.NS","ULTRACEMCO.NS","BAJAJFINSV.NS","M&M.NS","TITAN.NS",
    "ONGC.NS","ASIANPAINT.NS","POWERGRID.NS","ADANIENT.NS","NESTLEIND.NS","WIPRO.NS","JSWSTEEL.NS",
    "TATAMOTORS.NS","COALINDIA.NS","HINDALCO.NS","BAJAJ-AUTO.NS","TATASTEEL.NS","BEL.NS","TRENT.NS",
    "TECHM.NS","ADANIPORTS.NS","SBILIFE.NS","GRASIM.NS","INDUSINDBK.NS","CIPLA.NS","HDFCLIFE.NS",
    "DRREDDY.NS","EICHERMOT.NS","BPCL.NS","HEROMOTOCO.NS","BRITANNIA.NS","SHRIRAMFIN.NS","DIVISLAB.NS",
    "APOLLOHOSP.NS",
]
SENSEX = [
    "RELIANCE.BO","TCS.BO","HDFCBANK.BO","BHARTIARTL.BO","ICICIBANK.BO","INFY.BO","SBIN.BO",
    "BAJFINANCE.BO","HINDUNILVR.BO","ITC.BO","LT.BO","KOTAKBANK.BO","HCLTECH.BO","SUNPHARMA.BO",
    "MARUTI.BO","AXISBANK.BO","NTPC.BO","ULTRACEMCO.BO","M&M.BO","TITAN.BO","ASIANPAINT.BO",
    "POWERGRID.BO","NESTLEIND.BO","TATAMOTORS.BO","BAJAJFINSV.BO","TATASTEEL.BO","TECHM.BO",
    "ADANIPORTS.BO","INDUSINDBK.BO","WIPRO.BO",
]
NIFTYNEXT50 = [
    "ABB.NS","ADANIGREEN.NS","ADANIPOWER.NS","ATGL.NS","AMBUJACEM.NS","BANKBARODA.NS","BERGEPAINT.NS",
    "BOSCHLTD.NS","CANBK.NS","CHOLAFIN.NS","COLPAL.NS","DABUR.NS","DLF.NS","DMART.NS","GAIL.NS",
    "GODREJCP.NS","HAVELLS.NS","HAL.NS","HINDPETRO.NS","ICICIGI.NS","ICICIPRULI.NS","IOC.NS","IRCTC.NS",
    "JINDALSTEL.NS","JIOFIN.NS","LICI.NS","LODHA.NS","LTIM.NS","MARICO.NS","MOTHERSON.NS","NAUKRI.NS",
    "NMDC.NS","PFC.NS","PIDILITIND.NS","PNB.NS","RECLTD.NS","SBICARD.NS","SHREECEM.NS","SIEMENS.NS",
    "TATACONSUM.NS","TATAPOWER.NS","TORNTPHARM.NS","TVSMOTOR.NS","UNITDSPR.NS","VBL.NS","VEDL.NS",
    "ZYDUSLIFE.NS",
]
NIFTYBANK = ["HDFCBANK.NS","ICICIBANK.NS","SBIN.NS","KOTAKBANK.NS","AXISBANK.NS","INDUSINDBK.NS",
             "PNB.NS","BANKBARODA.NS","CANBK.NS","FEDERALBNK.NS","IDFCFIRSTB.NS","AUBANK.NS"]
NIFTY_PVT_BANK = ["HDFCBANK.NS","ICICIBANK.NS","KOTAKBANK.NS","AXISBANK.NS","INDUSINDBK.NS",
                  "FEDERALBNK.NS","IDFCFIRSTB.NS","AUBANK.NS","RBLBANK.NS","BANDHANBNK.NS",
                  "CITYUNIONBNK.NS","DCBBANK.NS"]
NIFTY_PSU_BANK = ["SBIN.NS","BANKBARODA.NS","PNB.NS","CANBK.NS","UNIONBANK.NS","BANKINDIA.NS",
                  "INDIANB.NS","CENTRALBK.NS","UCOBANK.NS","IOB.NS","MAHABANK.NS","PSB.NS"]
NIFTY_IT = ["TCS.NS","INFY.NS","HCLTECH.NS","WIPRO.NS","TECHM.NS","LTIM.NS","PERSISTENT.NS",
            "MPHASIS.NS","COFORGE.NS","LTTS.NS"]
NIFTY_FMCG = ["ITC.NS","HINDUNILVR.NS","NESTLEIND.NS","BRITANNIA.NS","DABUR.NS","COLPAL.NS",
              "GODREJCP.NS","MARICO.NS","TATACONSUM.NS","UNITDSPR.NS","VBL.NS","EMAMILTD.NS",
              "RADICO.NS","JYOTHYLAB.NS","PGHH.NS"]
NIFTY_PHARMA = ["SUNPHARMA.NS","DRREDDY.NS","CIPLA.NS","DIVISLAB.NS","TORNTPHARM.NS","ZYDUSLIFE.NS",
                "AUROPHARMA.NS","LUPIN.NS","ALKEM.NS","BIOCON.NS","GLAND.NS","GLENMARK.NS","IPCALAB.NS",
                "JBCHEPHARM.NS","LAURUSLABS.NS","SANOFI.NS","ABBOTINDIA.NS","NATCOPHARM.NS","PFIZER.NS",
                "AJANTPHARM.NS"]
NIFTY_AUTO = ["MARUTI.NS","M&M.NS","TATAMOTORS.NS","BAJAJ-AUTO.NS","EICHERMOT.NS","HEROMOTOCO.NS",
              "TVSMOTOR.NS","BOSCHLTD.NS","MOTHERSON.NS","ASHOKLEY.NS","BALKRISIND.NS","BHARATFORG.NS",
              "MRF.NS","EXIDEIND.NS","TIINDIA.NS"]
NIFTY_METAL = ["TATASTEEL.NS","JSWSTEEL.NS","HINDALCO.NS","VEDL.NS","JINDALSTEL.NS","SAIL.NS",
               "NMDC.NS","COALINDIA.NS","HINDZINC.NS","NATIONALUM.NS","JSL.NS","APLAPOLLO.NS",
               "HINDCOPPER.NS","RATNAMANI.NS","WELCORP.NS"]
NIFTY_REALTY = ["DLF.NS","LODHA.NS","GODREJPROP.NS","OBEROIRLTY.NS","PRESTIGE.NS","BRIGADE.NS",
                "PHOENIXLTD.NS","SOBHA.NS","SUNTECK.NS","MAHLIFE.NS"]
NIFTY_HEALTHCARE = NIFTY_PHARMA + ["APOLLOHOSP.NS","FORTIS.NS","MAXHEALTH.NS","METROPOLIS.NS",
                                    "SYNGENE.NS","DRLALPATHLABS.NS","NH.NS"]
NIFTY_MEDIA = ["ZEEL.NS","SUNTV.NS","PVRINOX.NS","TV18BRDCST.NS","SAREGAMA.NS","NETWORK18.NS",
               "NAZARA.NS","TIPSINDLTD.NS","HATHWAY.NS","NXTDIGITAL.NS"]
NIFTY_CONSUMER_DURABLES = ["TITAN.NS","HAVELLS.NS","DIXON.NS","VOLTAS.NS","CROMPTON.NS","BAJAJELEC.NS",
                            "WHIRLPOOL.NS","BLUESTARCO.NS","ORIENTELEC.NS","TTKPRESTIG.NS","KAJARIACER.NS",
                            "RAJESHEXPO.NS","KALYANKJIL.NS","AMBER.NS","CERA.NS"]
NIFTY_COMMODITIES = list(set(NIFTY_METAL + ["RELIANCE.NS","ONGC.NS","BPCL.NS","HINDPETRO.NS","IOC.NS",
                                              "GAIL.NS","UPL.NS","PIIND.NS","TATACHEM.NS","DEEPAKNTR.NS"]))
NIFTY_CPSE = ["NTPC.NS","ONGC.NS","COALINDIA.NS","POWERGRID.NS","BPCL.NS","GAIL.NS","NHPC.NS","NMDC.NS",
              "NLCINDIA.NS","SJVN.NS","OIL.NS","BEL.NS"]
NIFTY_ENERGY = ["RELIANCE.NS","ONGC.NS","NTPC.NS","COALINDIA.NS","POWERGRID.NS","BPCL.NS","HINDPETRO.NS",
                "IOC.NS","GAIL.NS","TATAPOWER.NS","ADANIGREEN.NS","ATGL.NS"]
NIFTY_MIDCAP_SELECT = ["ABFRL.NS","APOLLOTYRE.NS","ASTRAL.NS","AUBANK.NS","BHARATFORG.NS","CANBK.NS",
                        "CHOLAFIN.NS","COFORGE.NS","CUMMINSIND.NS","DEEPAKNTR.NS","DIXON.NS","FEDERALBNK.NS",
                        "GMRAIRPORT.NS","GODREJPROP.NS","HINDPETRO.NS","IDFCFIRSTB.NS","INDHOTEL.NS","LTF.NS",
                        "LUPIN.NS","MFSL.NS","PERSISTENT.NS","POLYCAB.NS","PIIND.NS","RECLTD.NS","SAIL.NS"]
NIFTY_MIDCAP_50 = NIFTY_MIDCAP_SELECT + ["ABCAPITAL.NS","AUROPHARMA.NS","BALKRISIND.NS","BANKINDIA.NS",
    "COCHINSHIP.NS","CONCOR.NS","CUB.NS","ESCORTS.NS","GUJGASLTD.NS","IDEA.NS","IRB.NS","JKCEMENT.NS",
    "JSWENERGY.NS","KPITTECH.NS","MAXHEALTH.NS","NMDC.NS","OFSS.NS","PAGEIND.NS","PETRONET.NS",
    "SUPREMEIND.NS","SYNGENE.NS","TATAELXSI.NS"]
NIFTY100 = list(dict.fromkeys(NIFTY50 + NIFTYNEXT50))
NIFTY200 = list(dict.fromkeys(NIFTY100 + NIFTY_MIDCAP_50))
NIFTY500 = list(dict.fromkeys(NIFTY200 + NIFTY_PHARMA + NIFTY_REALTY + NIFTY_MEDIA +
                              NIFTY_CONSUMER_DURABLES + NIFTY_PSU_BANK + NIFTY_PVT_BANK))
FNO_STOCKS = NIFTY200

INDEX_CONSTITUENTS: dict[str, list[str]] = {
    "NIFTY50":              NIFTY50,
    "SENSEX":               SENSEX,
    "FNO":                  FNO_STOCKS,
    "NIFTYNEXT50":          NIFTYNEXT50,
    "NIFTY100":             NIFTY100,
    "NIFTY200":             NIFTY200,
    "NIFTY500":             NIFTY500,
    "NIFTYMIDCAP50":        NIFTY_MIDCAP_50,
    "NIFTYMIDCAP100":       NIFTY_MIDCAP_50 + NIFTY_MIDCAP_SELECT,
    "NIFTYMIDCAP150":       NIFTY_MIDCAP_50 + NIFTY_MIDCAP_SELECT + NIFTY_REALTY + NIFTY_MEDIA,
    "NIFTYMIDCAPSELECT":    NIFTY_MIDCAP_SELECT,
    "NIFTYTOTALMARKET":     NIFTY500,
    "NIFTYBANK":            NIFTYBANK,
    "NIFTYPVTBANK":         NIFTY_PVT_BANK,
    "NIFTYPSUBANK":         NIFTY_PSU_BANK,
    "NIFTYIT":              NIFTY_IT,
    "NIFTYFMCG":            NIFTY_FMCG,
    "NIFTYPHARMA":          NIFTY_PHARMA,
    "NIFTYHEALTHCARE":      NIFTY_HEALTHCARE,
    "NIFTYAUTO":            NIFTY_AUTO,
    "NIFTYMETAL":           NIFTY_METAL,
    "NIFTYREALTY":          NIFTY_REALTY,
    "NIFTYMEDIA":           NIFTY_MEDIA,
    "NIFTYCONSUMERDURABLES":NIFTY_CONSUMER_DURABLES,
    "NIFTYCOMMODITIES":     NIFTY_COMMODITIES,
    "NIFTYCPSE":            NIFTY_CPSE,
    "NIFTYENERGY":          NIFTY_ENERGY,
    "NIFTYFINSERVICE":      ["HDFCBANK.NS","ICICIBANK.NS","SBIN.NS","KOTAKBANK.NS","AXISBANK.NS",
                              "BAJFINANCE.NS","BAJAJFINSV.NS","SHRIRAMFIN.NS","HDFCLIFE.NS","SBILIFE.NS",
                              "ICICIPRULI.NS","ICICIGI.NS","CHOLAFIN.NS","RECLTD.NS","PFC.NS","SBICARD.NS",
                              "JIOFIN.NS","HDFCAMC.NS","LICHSGFIN.NS","MUTHOOTFIN.NS"],
}
INDEX_LABELS = {
    "NIFTY50":"Nifty 50","SENSEX":"Sensex","FNO":"F&O Stocks","NIFTYNEXT50":"Nifty Next 50",
    "NIFTY100":"Nifty 100","NIFTY200":"Nifty 200","NIFTY500":"Nifty 500",
    "NIFTYMIDCAP50":"Nifty Midcap 50","NIFTYMIDCAP100":"Nifty Midcap 100",
    "NIFTYMIDCAP150":"Nifty Midcap 150","NIFTYMIDCAPSELECT":"Nifty Midcap Select",
    "NIFTYTOTALMARKET":"Nifty Total Market","NIFTYBANK":"Nifty Bank","NIFTYPVTBANK":"Nifty Private Bank",
    "NIFTYPSUBANK":"Nifty PSU Bank","NIFTYIT":"Nifty IT","NIFTYFMCG":"Nifty FMCG",
    "NIFTYPHARMA":"Nifty Pharma","NIFTYHEALTHCARE":"Nifty Healthcare","NIFTYAUTO":"Nifty Auto",
    "NIFTYMETAL":"Nifty Metal","NIFTYREALTY":"Nifty Realty","NIFTYMEDIA":"Nifty Media",
    "NIFTYCONSUMERDURABLES":"Nifty Consumer Durables","NIFTYCOMMODITIES":"Nifty Commodities",
    "NIFTYCPSE":"Nifty CPSE","NIFTYENERGY":"Nifty Energy",
    "NIFTYFINSERVICE":"Nifty Financial Services",
}
INDEX_TICKER = {
    "NIFTY50":"^NSEI","SENSEX":"^BSESN","NIFTYBANK":"^NSEBANK","NIFTYIT":"^CNXIT",
    "NIFTYAUTO":"^CNXAUTO","NIFTYFMCG":"^CNXFMCG","NIFTYPHARMA":"^CNXPHARMA",
    "NIFTYMETAL":"^CNXMETAL","NIFTYREALTY":"^CNXREALTY","NIFTYMEDIA":"^CNXMEDIA",
    "NIFTYENERGY":"^CNXENERGY","NIFTYFINSERVICE":"^NIFTY_FIN_SERVICE",
}
PERIOD_MAP = {"1d":"5d","1w":"1mo","1m":"3mo","1y":"1y"}


def _pretty(sym: str) -> str:
    return sym.replace(".NS", "").replace(".BO", "")


# ────────────────────────────────────────────────────────────────────────────
# Colour palette (server-side — UI renders via inline style)
# ────────────────────────────────────────────────────────────────────────────
def _bucket_color(p: float | None) -> tuple[str, str]:
    """Return (background, foreground) hex colours for a % change value."""
    if p is None:
        return ("#94a3b8", "#0f172a")          # slate
    if p <= -3:    return ("#7f1d1d", "#ffffff")
    if p <= -2:    return ("#b91c1c", "#ffffff")
    if p <= -1:    return ("#dc2626", "#ffffff")
    if p < -0.001: return ("#ef4444", "#ffffff")
    if p <  0.001: return ("#64748b", "#ffffff")  # neutral slate-500
    if p <  1:     return ("#16a34a", "#ffffff")
    if p <  2:     return ("#15803d", "#ffffff")
    if p <  3:     return ("#166534", "#ffffff")
    return ("#14532d", "#ffffff")


# ────────────────────────────────────────────────────────────────────────────
# Heatmap (parallelised yfinance)
# ────────────────────────────────────────────────────────────────────────────
_PERIOD_DAYS = {"5d": 7, "1mo": 31, "3mo": 95, "6mo": 190, "1y": 370,
                 "2y": 740, "5y": 1830, "10y": 3650}


# Trading-day offset for the heatmap timeframe. The window we fetch from
# yfinance is wider than the comparison window so we always have at least
# one valid base candle even after holidays/non-trading days. The base
# close is then picked at the right offset from the *latest* candle.
#   1D → previous close                  (≈ -2)
#   1W → 5 trading days back             (≈ -6)
#   1M → 22 trading days back            (≈ -23)
#   1Y → first available close in window (≈  0)
_PERF_OFFSET = {"1d": -2, "1w": -6, "1m": -23, "1y": None}


def _base_close_for(closes: list[float], performance: str) -> float | None:
    """Return the base close to compare against `closes[-1]` for the
    given user-facing timeframe label. None when unknown.
    """
    if not closes or len(closes) < 2:
        return None
    off = _PERF_OFFSET.get(performance)
    if off is None:
        return float(closes[0])
    if -off > len(closes):
        # Not enough history — fall back to the oldest candle we do have
        # so the tile still renders something meaningful.
        return float(closes[0])
    return float(closes[off])


def _quote_from_closes(
    sym: str,
    closes: list[float],
    market_cap: float = 0.0,
    performance: str = "1d",
) -> dict | None:
    if not closes or len(closes) < 2:
        return None
    close = float(closes[-1])
    base  = _base_close_for(closes, performance)
    if base is None:
        return None
    change_pct = ((close / base) - 1.0) * 100 if base else 0.0
    bg, fg = _bucket_color(change_pct)
    return {
        "symbol": sym,
        "name": _pretty(sym),
        "price": round(close, 2),
        "changePct": round(change_pct, 2),
        "marketCap": market_cap,
        "color": {"bg": bg, "fg": fg},
    }


# Market-cap cache (24h TTL). marketCap is not a price field — it changes slowly
# and only with corporate actions, so a long TTL is safe and removes the single
# biggest bottleneck on the heatmap (yfinance.fast_info is ~0.8s per symbol).
_MCAP_TTL = 24 * 60 * 60
_mcap_cache: dict[str, tuple[float, float]] = {}


def _market_cap_cached(sym: str) -> float:
    ysym = sym if (sym.endswith(".NS") or sym.endswith(".BO")) else f"{sym}.NS"
    hit = _mcap_cache.get(ysym)
    now = time.time()
    if hit and (now - hit[0]) < _MCAP_TTL:
        return hit[1]
    return 0.0


async def _prefetch_market_caps(symbols: list[str]) -> None:
    """Fill the market-cap cache in parallel for symbols whose entries are
    missing or stale. Each yfinance.fast_info call is ~0.8s of blocking I/O,
    so we offload to the default executor and run them concurrently.
    """
    now = time.time()
    stale: list[str] = []
    for s in symbols:
        ysym = s if (s.endswith(".NS") or s.endswith(".BO")) else f"{s}.NS"
        hit = _mcap_cache.get(ysym)
        if not hit or (now - hit[0]) >= _MCAP_TTL:
            stale.append(ysym)
    if not stale:
        return

    import yfinance as yf
    loop = asyncio.get_running_loop()

    def _one(ysym: str) -> tuple[str, float]:
        try:
            mc = float(yf.Ticker(ysym).fast_info.get("marketCap") or 0.0)
        except Exception:
            mc = 0.0
        return ysym, mc

    sem = asyncio.Semaphore(32)

    async def _bounded(ysym: str):
        async with sem:
            return await loop.run_in_executor(None, _one, ysym)

    results = await asyncio.gather(*[_bounded(s) for s in stale], return_exceptions=True)
    ts = time.time()
    for r in results:
        if isinstance(r, tuple):
            ysym, mc = r
            _mcap_cache[ysym] = (ts, mc)


async def _fetch_one_quote_async(sym: str, period_yf: str, performance: str) -> dict | None:
    """Single source of truth for the heatmap quote.

    Pulls daily OHLCV via PriceService — same code path used by /stocks and
    /sectors — so provider and timepoint match across all surfaces.
    PriceService itself enforces `eodSealed` on closed-market disk reads,
    so an intraday-only snapshot is never served as the close.

    Market cap is read from the long-lived `_mcap_cache` (warmed once per
    24h by `_prefetch_market_caps`) — never from a per-request fast_info call.

    `performance` selects the comparison-base offset (1d=prev close, 1w=5d
    back, 1m=22d back, 1y=earliest in window) so the % change actually
    matches the timeframe label the user picked.
    """
    days = _PERIOD_DAYS.get(period_yf, 7)
    try:
        rows = await _price.get_historical_data(sym, days)
    except Exception as e:
        logger.debug("heatmap PriceService.get_historical_data %s failed: %s", sym, e)
        return None
    closes = _closes_from_history(rows)
    if len(closes) < 2:
        return None

    return _quote_from_closes(sym, closes, _market_cap_cached(sym), performance)


async def _heatmap_async(symbols: list[str], period_yf: str, performance: str) -> list[dict]:
    """Concurrently fetch heatmap quotes via PriceService."""
    sem = asyncio.Semaphore(48)
    async def _bounded(s: str):
        async with sem:
            return await _fetch_one_quote_async(s, period_yf, performance)
    results = await asyncio.gather(*[_bounded(s) for s in symbols], return_exceptions=True)
    return [r for r in results if isinstance(r, dict) and r]


# Map of curated index codes → the underlying constituent symbol whose
# PriceService quote we use as the index proxy. This avoids a second
# data-source path and keeps Insights consistent with /stocks.
_INDEX_PROXY_SYMBOL = {
    "^NSEI":   "NIFTY 50",
    "^NSEBANK": "NIFTY BANK",
    "^CNXIT":  "NIFTY IT",
}


async def _index_quote_async(ticker: str, performance: str = "1d") -> dict:
    """Index-level quote via PriceService daily history (same source as the
    heatmap tiles), so the index header and the tiles always agree.

    `performance` selects the same comparison offset used for the tiles
    (1d/1w/1m/1y) so the header % matches what the grid shows.
    """
    # Pull a window wide enough to cover the chosen timeframe. We want at
    # least ~25 calendar days for 1m and ~370 for 1y.
    days_needed = {"1d": 7, "1w": 14, "1m": 45, "1y": 380}.get(performance, 7)
    try:
        rows = await _price.get_historical_data(ticker, days_needed)
    except Exception:
        rows = []
    closes = _closes_from_history(rows)
    if len(closes) < 2:
        # Last-resort fallback to yfinance — only when PriceService returns
        # nothing (e.g. NSE indices that don't expose OHLCV historically).
        try:
            import yfinance as yf
            yf_period = {"1d": "5d", "1w": "1mo", "1m": "3mo", "1y": "1y"}.get(performance, "5d")
            hist = yf.Ticker(ticker).history(period=yf_period, auto_adjust=False)
            if hist.empty:
                return {}
            closes = [float(x) for x in hist["Close"].tolist()]
        except Exception:
            return {}
    if len(closes) < 2:
        return {}
    last = closes[-1]
    base = _base_close_for(closes, performance) or closes[0]
    change = last - base
    pct = (change / base * 100) if base else 0.0
    return {"lastPrice": round(last, 2), "change": round(change, 2), "changePct": round(pct, 2)}


@router.get("/indices")
async def list_indices():
    return {
        "indices": [
            {"code": code, "label": INDEX_LABELS.get(code, code), "count": len(syms)}
            for code, syms in INDEX_CONSTITUENTS.items()
        ]
    }


@router.get("/heatmap")
async def get_heatmap(
    index: str = Query("NIFTY50"),
    performance: str = Query("1d"),
):
    code = index.upper().replace(" ", "").replace("-", "")
    cache_key = f"heatmap:{code}:{performance}"
    # Heatmap data is daily-resolution. When the market is closed the close
    # won't change until the next session, so we can hold the cache far
    # longer. During market hours we still refresh frequently.
    market_open = mcache.is_market_open()
    ttl = 600 if market_open else LONG_TTL
    cached = _cache_get(cache_key, ttl=ttl)
    if cached is not None:
        return cached

    symbols = INDEX_CONSTITUENTS.get(code)
    if not symbols:
        return {
            "available": False,
            "message": f"Index '{index}' is not supported yet.",
            "index": code,
            "label": INDEX_LABELS.get(code, code),
            "items": [],
        }

    period_yf = PERIOD_MAP.get(performance, "5d")
    idx_ticker = INDEX_TICKER.get(code, "^NSEI")

    # When the market is closed, force-seal any intraday snapshots BEFORE we
    # read disk. Guarantees the heatmap shows the same official close as
    # /stocks and /sectors (no stale-intraday-as-close).
    try:
        await mcache.seal_eod_for_today_if_overdue(_price, symbols=list(symbols))
    except Exception:
        pass

    # Warm the long-lived market-cap cache in parallel with the price fetch.
    # First-ever request per symbol still pays the fast_info cost (~0.8s),
    # but it is parallelised and only happens once per 24h thereafter.
    items, idx_q, _ = await asyncio.gather(
        _heatmap_async(symbols, period_yf, performance),
        _index_quote_async(idx_ticker, performance),
        _prefetch_market_caps(list(symbols)),
    )

    # If market caps were freshly populated above, fill them into items now
    # (the heatmap_async path may have run before the prefetch finished).
    for it in items:
        if not it.get("marketCap"):
            it["marketCap"] = _market_cap_cached(it["symbol"])

    response = {
        "available": True,
        "index": code,
        "label": INDEX_LABELS.get(code, code),
        "indexPrice": idx_q.get("lastPrice"),
        "indexChange": idx_q.get("change"),
        "indexChangePct": idx_q.get("changePct"),
        "items": items,
        "meta": _meta("HEATMAP_ENGINE"),
    }
    _cache_set(cache_key, response)
    return response


# ────────────────────────────────────────────────────────────────────────────
# Company filings (BSE + NSE — corporate announcements & insider trading)
# ────────────────────────────────────────────────────────────────────────────
BSE_API = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
BSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.bseindia.com",
    "Referer": "https://www.bseindia.com/",
}

# BSE returns naive IST timestamps like "2026-05-03T02:21:56" (no tz suffix).
# JS `new Date()` would parse those as the browser's local time, so the
# "X min ago" label drifts by IST offset for non-IST users. We tag the
# offset on the server so every consumer parses the same instant.
_IST_OFFSET = "+05:30"


def _ist_isoformat(s: str) -> str:
    """Append +05:30 to a naive IST datetime string. Idempotent."""
    if not s:
        return ""
    s = s.strip().replace(" ", "T")
    # Already timezone-suffixed? Leave alone. Detect Z, +HH:MM, or -HH:MM (only
    # the trailing offset, not the date's own '-' separators — len("YYYY-MM-DDTHH:MM:SS") = 19).
    if s.endswith("Z"):
        return s
    if len(s) >= 6 and s[-6] in ("+", "-") and s[-3] == ":":
        return s
    return f"{s}{_IST_OFFSET}"


def _adapt_bse_announcements(payload: Any) -> list[dict]:
    """Convert BSE Corporate Announcements JSON to our normalised filing shape."""
    if not isinstance(payload, dict):
        return []
    rows = payload.get("Table") or []
    out: list[dict] = []
    for idx, r in enumerate(rows):
        if not isinstance(r, dict):
            continue
        scrip = str(r.get("SCRIP_CD", "")).strip()
        attachment = (r.get("ATTACHMENTNAME") or "").strip()
        doc_url = ""
        if attachment:
            doc_url = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{attachment}"
        news_id = (r.get("NEWSID") or "").strip()
        # Synthetic stable id avoids React key collisions when BSE returns blanks.
        if not news_id:
            news_id = f"bse:{scrip}:{(r.get('NEWS_DT') or '').strip()}:{idx}"
        out.append({
            "id": f"bse:{news_id}",
            "exchange": "BSE",
            "symbol": scrip,
            "company": (r.get("SLONGNAME") or "").strip() or scrip,
            "category": (r.get("CATEGORYNAME") or "").strip() or "Other",
            "purpose": (r.get("HEADLINE") or r.get("NEWSSUB") or "").strip(),
            "subject": (r.get("NEWSSUB") or "").strip(),
            "date": _ist_isoformat(r.get("NEWS_DT") or ""),
            "documentUrl": doc_url,
        })
    return out


def _bse_total_count(payload: Any) -> int:
    """Total available rows across all pages, from BSE Table1[0].ROWCNT."""
    try:
        t1 = (payload or {}).get("Table1") or []
        if t1 and isinstance(t1[0], dict):
            return int(t1[0].get("ROWCNT") or 0)
    except Exception:
        pass
    return 0


def _adapt_nse_announcements(payload: Any) -> list[dict]:
    """Convert NSE corporate-announcements feed to our normalised filing shape."""
    rows = payload if isinstance(payload, list) else (payload or {}).get("data") or []
    out: list[dict] = []
    for idx, r in enumerate(rows):
        if not isinstance(r, dict):
            continue
        sym = (r.get("symbol") or "").strip()
        company = (r.get("sm_name") or sym).strip()
        desc = (r.get("desc") or "").strip()
        subject = (r.get("attchmntText") or desc).strip()
        # NSE has no fixed taxonomy — derive a coarse category from desc text.
        category = _infer_category(desc + " " + subject)
        # Prefer ISO sort_date ("2026-05-02 23:58:27") over DDMMYYYYHHMMSS dt.
        raw_date = (r.get("sort_date") or "").strip()
        seq = (r.get("seq_id") or "").strip()
        out.append({
            "id": f"nse:{seq or idx}",
            "exchange": "NSE",
            "symbol": sym,
            "company": company,
            "category": category,
            "purpose": desc or subject or "—",
            "subject": subject,
            "date": _ist_isoformat(raw_date),
            "documentUrl": (r.get("attchmntFile") or "").strip(),
        })
    return out


def _adapt_nse_pit(payload: Any) -> list[dict]:
    """Convert NSE PIT (insider trading) feed to our normalised filing shape."""
    rows = (payload or {}).get("data") or []
    out: list[dict] = []
    for idx, r in enumerate(rows):
        if not isinstance(r, dict):
            continue
        sym = (r.get("symbol") or "").strip()
        company = (r.get("company") or sym).strip()
        acq_name = (r.get("acqName") or r.get("tkdAcqm") or "").strip()
        sec_acq = (r.get("secAcq") or "").strip()
        buy_q = (r.get("buyQuantity") or "0").strip()
        sell_q = (r.get("sellquantity") or "0").strip()
        sec_type = (r.get("secType") or "").strip()
        purpose_bits = []
        if acq_name:
            purpose_bits.append(acq_name)
        if buy_q and buy_q != "0":
            purpose_bits.append(f"Bought {buy_q} {sec_type}")
        elif sell_q and sell_q != "0":
            purpose_bits.append(f"Sold {sell_q} {sec_type}")
        elif sec_acq and sec_acq != "0":
            purpose_bits.append(f"Holding change: {sec_acq} {sec_type}")
        purpose = " · ".join(purpose_bits) or "Insider trade disclosure"
        # NSE PIT date is "02-May-2026 16:46" — convert to ISO.
        raw_date = (r.get("date") or "").strip()
        iso_date = _parse_nse_pit_date(raw_date)
        pid = (r.get("pid") or r.get("did") or str(idx)).strip()
        out.append({
            "id": f"nse-pit:{pid}",
            "exchange": "NSE",
            "symbol": sym,
            "company": company,
            "category": "Insider Trading",
            "purpose": purpose,
            "subject": purpose,
            "date": iso_date,
            "documentUrl": "",
        })
    return out


def _parse_nse_pit_date(s: str) -> str:
    """Convert '02-May-2026 16:46' → '2026-05-02T16:46:00+05:30'."""
    if not s:
        return ""
    try:
        from datetime import datetime
        dt = datetime.strptime(s, "%d-%b-%Y %H:%M")
        return dt.strftime("%Y-%m-%dT%H:%M:00") + _IST_OFFSET
    except Exception:
        return _ist_isoformat(s)


_CATEGORY_KEYWORDS: list[tuple[str, str]] = [
    ("Result",                ("result", "financial result", "quarterly", "annual report")),
    ("Dividend",              ("dividend",)),
    ("Bonus",                 ("bonus", "stock split", "sub-division", "subdivision")),
    ("AGM/EGM",               ("agm", "egm", "annual general meeting", "extraordinary general")),
    ("Board Meeting",         ("board meeting",)),
    ("Acquisition",           ("acquisition", "acquired", "merger", "amalgamation", "scheme of arrangement")),
    ("Investor Presentation", ("investor presentation", "analyst meet", "investor meet", "earnings call", "concall")),
    ("Insider Trading",       ("sast", "insider", "regulation 7", "pit ")),
    ("Company Update",        ("update", "intimation", "press release", "newspaper")),
]


def _infer_category(text: str) -> str:
    """Map free-text NSE descriptions to our coarse BSE-aligned categories."""
    t = (text or "").lower()
    for label, kws in _CATEGORY_KEYWORDS:
        for kw in kws:
            if kw in t:
                return label
    return "Other"


def _matches_category(item: dict, category: str) -> bool:
    """Client-side category filter — handles BSE rows the strCat= server filter misses
    (e.g. NSE rows, or BSE 'Investor Presentation' that lives under 'Company Update')."""
    if not category or category in ("all", "-1"):
        return True
    target = category.lower()
    blob = (item.get("category", "") + " " + item.get("purpose", "") + " " + item.get("subject", "")).lower()
    # Match on first slash-segment so "AGM/EGM" matches "AGM" too.
    head = target.split("/")[0].strip()
    return head in blob or target in blob


# BSE's strCat= server filter only accepts categories that appear in its own
# taxonomy. Items like "Investor Presentation" live under CATEGORYNAME="Company
# Update" with the marker in HEADLINE — passing strCat=Investor Presentation
# returns 0 rows. For those we fetch all and rely on _matches_category instead.
_BSE_NATIVE_CATEGORIES = {
    "Result", "Board Meeting", "AGM/EGM", "Dividend", "Bonus",
    "Acquisition", "Company Update",
}


async def _fetch_bse_corporate(category: str, page: int) -> tuple[list[dict], int, str]:
    """Fetch one page of BSE corporate announcements. Returns (items, total, error)."""
    str_cat = category if (category in _BSE_NATIVE_CATEGORIES) else "-1"
    try:
        async with httpx.AsyncClient(timeout=12.0, headers=BSE_HEADERS) as cli:
            resp = await cli.get(BSE_API, params={
                "pageno": page,
                "strCat": str_cat,
                "strPrevDate": "",
                "strScrip": "",
                "strSearch": "P",
                "strToDate": "",
                "strType": "C",
            })
        if resp.status_code >= 400:
            logger.warning("BSE filings HTTP %s for cat=%s page=%s", resp.status_code, category, page)
            return [], 0, f"BSE HTTP {resp.status_code}"
        payload = resp.json()
        return _adapt_bse_announcements(payload), _bse_total_count(payload), ""
    except httpx.TimeoutException:
        logger.warning("BSE filings timeout cat=%s page=%s", category, page)
        return [], 0, "BSE timeout"
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("BSE filings fetch failed cat=%s page=%s: %s", category, page, e)
        return [], 0, f"BSE error: {e.__class__.__name__}"


async def _fetch_nse_corporate() -> tuple[list[dict], str]:
    """Fetch NSE corporate announcements (latest ~20 across all equities)."""
    data = await _nse.fetch_nse(
        "/api/corporate-announcements?index=equities",
        cache_key="nse-corp-anno",
        ttl=600,
    )
    if data is None:
        return [], "NSE corporate feed unavailable"
    return _adapt_nse_announcements(data), ""


async def _fetch_nse_insider() -> tuple[list[dict], str]:
    """Fetch NSE PIT (insider) feed."""
    data = await _nse.fetch_nse(
        "/api/corporates-pit?index=equities",
        cache_key="nse-pit",
        ttl=600,
    )
    if data is None:
        return [], "NSE insider feed unavailable"
    return _adapt_nse_pit(data), ""


def _adapt_nse_shareholding(payload: Any) -> list[dict]:
    """Convert NSE corporate-share-holdings-master rows to our filing shape.
    Each row is a quarterly Shareholding Pattern (SHP) submission with
    promoter / public / employee-trust holding percentages and an XBRL link."""
    rows = payload if isinstance(payload, list) else (payload or {}).get("data") or []
    out: list[dict] = []
    for idx, r in enumerate(rows):
        if not isinstance(r, dict):
            continue
        sym = (r.get("symbol") or "").strip()
        company = (r.get("name") or sym).strip()
        promoter = (r.get("pr_and_prgrp") or "").strip()
        public = (r.get("public_val") or "").strip()
        emp_trust = (r.get("employeeTrusts") or "").strip()
        period_end = (r.get("date") or "").strip()  # "31-MAR-2026"
        broadcast = (r.get("broadcastDate") or r.get("submissionDate") or "").strip()
        rec_id = (r.get("recordId") or str(idx)).strip()

        bits: list[str] = []
        if promoter:
            bits.append(f"Promoter {promoter}%")
        if public:
            bits.append(f"Public {public}%")
        if emp_trust and emp_trust != "0":
            bits.append(f"Emp Trust {emp_trust}%")
        if period_end:
            bits.append(f"as of {period_end}")
        purpose = " · ".join(bits) or "Shareholding Pattern filing"

        # broadcastDate is "21-APR-2026 18:14:47"; submissionDate is "03-APR-2026" only.
        iso_date = _parse_nse_broadcast_date(broadcast)

        out.append({
            "id": f"nse-shp:{rec_id}",
            "exchange": "NSE",
            "symbol": sym,
            "company": company,
            "category": "Shareholding Pattern",
            "purpose": purpose,
            "subject": purpose,
            "date": iso_date,
            "documentUrl": (r.get("xbrl") or "").strip(),
        })
    return out


def _parse_nse_broadcast_date(s: str) -> str:
    """Parse '21-APR-2026 18:14:47' or '03-APR-2026' → ISO+05:30."""
    if not s:
        return ""
    try:
        from datetime import datetime
        for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%B-%Y %H:%M:%S",
                    "%d-%b-%Y", "%d-%B-%Y"):
            try:
                # NSE returns month codes in upper-case ("APR"); strptime wants
                # title-case. Normalise the month token before parsing.
                parts = s.split()
                if parts and "-" in parts[0]:
                    d, m, y = parts[0].split("-")
                    parts[0] = f"{d}-{m.title()}-{y}"
                    s_norm = " ".join(parts)
                else:
                    s_norm = s
                dt = datetime.strptime(s_norm, fmt)
                return dt.strftime("%Y-%m-%dT%H:%M:%S") + _IST_OFFSET
            except ValueError:
                continue
    except Exception:
        pass
    return _ist_isoformat(s)


async def _fetch_nse_shareholding() -> tuple[list[dict], str]:
    """Fetch NSE Shareholding Pattern master (latest filings across all equities)."""
    data = await _nse.fetch_nse(
        "/api/corporate-share-holdings-master?index=equities",
        cache_key="nse-shp-master",
        ttl=900,  # 15 min — quarterly data, low churn
    )
    if data is None:
        return [], "NSE shareholding feed unavailable"
    items = _adapt_nse_shareholding(data)
    # Sort newest broadcast first (already done downstream, but pre-sort helps cap).
    items.sort(key=lambda x: x.get("date") or "", reverse=True)
    return items, ""


@router.get("/company-filings")
async def get_company_filings(
    request: Request,
    source: str = Query("all", description="all | bse | nse"),
    type: str = Query("corporate", description="corporate | insider | shareholding"),
    category: str = Query("all", description="all | Result | Dividend | Board Meeting | AGM/EGM | Bonus | Acquisition | Investor Presentation | Company Update"),
    page: int = Query(1, ge=1, le=20),
    pageSize: int = Query(50, ge=1, le=200),
):
    source = (source or "all").lower()
    type_ = (type or "corporate").lower()
    category = category or "all"
    cache_key = f"company-filings:v2:{source}:{type_}:{category}:{page}:{pageSize}"
    cached = _cache_get(cache_key, ttl=900)  # 15 min
    if cached is not None:
        return cached

    tasks: list = []
    plan: list[str] = []  # parallel to tasks, identifies which fetcher

    if type_ == "insider":
        # NSE PIT is the only working live insider feed; BSE InsiderTrading2 endpoint is dead.
        if source in ("all", "nse"):
            tasks.append(_fetch_nse_insider())
            plan.append("nse-insider")
    elif type_ == "shareholding":
        # NSE corporate-share-holdings-master is the working SHP feed; BSE's
        # ShareholdingPattern endpoint family was retired (302→error_Bse).
        if source in ("all", "nse"):
            tasks.append(_fetch_nse_shareholding())
            plan.append("nse-shp")
    else:
        # type_ == "corporate" (default)
        if source in ("all", "bse"):
            tasks.append(_fetch_bse_corporate(category, page))
            plan.append("bse-corp")
        if source in ("all", "nse"):
            tasks.append(_fetch_nse_corporate())
            plan.append("nse-corp")

    if not tasks:
        res = {
            "available": False, "sources": [], "items": [], "total": 0,
            "hasMore": False, "page": page,
            "message": "No source available for the requested type.",
            "meta": _meta("BSE_NSE_FILINGS"),
        }
        _cache_set(cache_key, res)
        return res

    results = await asyncio.gather(*tasks, return_exceptions=True)

    items: list[dict] = []
    sources_used: list[str] = []
    errors: list[str] = []
    bse_total = 0

    for label, r in zip(plan, results):
        if isinstance(r, Exception):
            errors.append(f"{label}: {r}")
            continue
        if label == "bse-corp":
            rows, total, err = r  # type: ignore[misc]
            if rows:
                items.extend(rows)
                if "BSE Corporate" not in sources_used:
                    sources_used.append("BSE Corporate")
            if total:
                bse_total = total
            if err:
                errors.append(err)
        else:
            rows, err = r  # type: ignore[misc]
            if rows:
                items.extend(rows)
                src_name = {
                    "nse-insider": "NSE Insider",
                    "nse-shp":     "NSE Shareholding",
                    "nse-corp":    "NSE Corporate",
                }.get(label, "NSE")
                if src_name not in sources_used:
                    sources_used.append(src_name)
            if err:
                errors.append(err)

    # Dedupe: same company + same minute + same headline prefix.
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict] = []
    for it in items:
        key = (it.get("company") or it.get("symbol") or "", (it.get("date") or "")[:16], (it.get("purpose") or "")[:60].lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)

    # Server-side category filter for NSE rows (BSE was already filtered upstream).
    if category and category != "all":
        unique = [it for it in unique if _matches_category(it, category)]

    # Sort newest first; date is now ISO with +05:30 so string sort works.
    unique.sort(key=lambda x: x.get("date") or "", reverse=True)

    # Cap to pageSize for the UI; expose total so the client can show "Load more".
    capped = unique[:pageSize]
    # Approximate total: BSE knows its own count; NSE feeds are ~latest 20 only.
    total = max(bse_total, len(unique))
    has_more = len(unique) > len(capped) or (bse_total and page * pageSize < bse_total)

    available = bool(capped) or not errors
    res = {
        "available": available,
        "sources": sources_used,
        "source": ", ".join(sources_used) if sources_used else None,  # back-compat
        "items": capped,
        "total": total,
        "hasMore": bool(has_more),
        "page": page,
        "errors": errors if errors else None,
        "message": (None if capped else (errors[0] if errors else "No filings match the selected filter.")),
        "meta": _meta("BSE_NSE_FILINGS"),
    }
    _cache_set(cache_key, res)
    return res


# ────────────────────────────────────────────────────────────────────────────
# MF Holdings (AMFI)
# ────────────────────────────────────────────────────────────────────────────
AMFI_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"


def _safe_float(s: str) -> float | None:
    try:
        s = s.strip()
        if not s or s.lower() in ("n.a.", "na", "-", ""):
            return None
        return float(s)
    except Exception:
        return None


def _parse_amfi_text(text: str) -> list[dict]:
    """Parse AMFI's NAVAll.txt — semicolon-separated rows interleaved with
    AMC-name and category-header lines (no semicolons)."""
    rows: list[dict] = []
    current_amc = ""
    current_cat = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("Scheme Code"):     # header row
            continue
        if ";" not in line:
            stripped = line.strip()
            # Headers like "Open Ended Schemes(Equity Scheme - Large Cap Fund)"
            if "Scheme" in stripped and "(" in stripped:
                current_cat = stripped
            elif stripped.endswith("Mutual Fund"):
                current_amc = stripped
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 6:
            continue
        code, isin1, isin2, name, nav_s, dt = parts[:6]
        rows.append({
            "schemeCode": code,
            "isin": isin1 if isin1 not in ("-", "") else (isin2 if isin2 not in ("-", "") else ""),
            "schemeName": name,
            "nav": _safe_float(nav_s),
            "date": dt,
            "amc": current_amc,
            "category": current_cat,
        })
    return rows


@router.get("/mf-holdings")
async def get_mf_holdings(
    amc: str = Query("", description="Filter by AMC name (substring, case-insensitive)"),
    category: str = Query("", description="Filter by category (substring)"),
    search: str = Query("", description="Filter by scheme name (substring)"),
    limit: int = Query(200, ge=1, le=2000),
):
    cache_key = "amfi:nav-all"
    parsed = _cache_get(cache_key, ttl=LONG_TTL)
    if parsed is None:
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True,
                                          headers={"User-Agent": "Mozilla/5.0"}) as cli:
                r = await cli.get(AMFI_URL)
            r.raise_for_status()
            parsed = _parse_amfi_text(r.text)
            _cache_set(cache_key, parsed)
        except Exception as e:
            logger.warning("AMFI fetch failed: %s", e)
            return {"available": False, "message": "AMFI NAV feed temporarily unavailable.", "items": []}

    items = parsed
    if amc:
        ql = amc.lower()
        items = [x for x in items if ql in (x.get("amc") or "").lower()]
    if category:
        ql = category.lower()
        items = [x for x in items if ql in (x.get("category") or "").lower()]
    if search:
        ql = search.lower()
        items = [x for x in items if ql in (x.get("schemeName") or "").lower()]

    # Build facets so the UI can populate dropdowns even when filters are empty.
    amcs = sorted({x["amc"] for x in parsed if x.get("amc")})
    cats = sorted({x["category"] for x in parsed if x.get("category")})

    return {
        "available": True,
        "source": "AMFI NAVAll.txt",
        "totalSchemes": len(parsed),
        "matched": len(items),
        "items": items[:limit],
        "amcs": amcs,
        "categories": cats,
    }


# ────────────────────────────────────────────────────────────────────────────
# Signals (RSI / MA cross from yfinance)
# ────────────────────────────────────────────────────────────────────────────
def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0 if avg_g > 0 else 50.0
    rs = avg_g / avg_l
    return 100.0 - (100.0 / (1.0 + rs))


def _ma(closes: list[float], n: int) -> float | None:
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def _compute_signal(symbol: str, closes: list[float]) -> dict:
    rsi = _rsi(closes)
    ma20 = _ma(closes, 20) or 0.0
    ma50 = _ma(closes, 50) or 0.0
    last = closes[-1] if closes else 0.0

    verdict = "Neutral"
    reasons: list[str] = []

    if rsi is not None:
        if rsi >= 70:
            verdict = "Bearish"
            reasons.append(f"RSI {rsi:.1f} (overbought)")
        elif rsi <= 30:
            verdict = "Bullish"
            reasons.append(f"RSI {rsi:.1f} (oversold)")

    if ma20 and ma50:
        if ma20 > ma50 and last > ma20:
            verdict = "Bullish"
            reasons.append("Price > MA20 > MA50 (uptrend)")
        elif ma20 < ma50 and last < ma20:
            verdict = "Bearish"
            reasons.append("Price < MA20 < MA50 (downtrend)")

    return {
        "symbol": symbol,
        "name": _pretty(symbol),
        "ltp": round(last, 2),
        "rsi": round(rsi, 2) if rsi is not None else None,
        "ma20": round(ma20, 2),
        "ma50": round(ma50, 2),
        "verdict": verdict,
        "reasons": reasons,
    }


async def _signals_async(symbols: list[str]) -> list[dict]:
    """Compute per-symbol signals. Pulls 6-month daily closes via
    PriceService (same source as /stocks/{sym}/history), so signal verdicts
    are based on the SAME closes the user sees on the chart."""
    days = _PERIOD_DAYS["6mo"]
    sem = asyncio.Semaphore(12)

    async def _one(sym: str):
        async with sem:
            try:
                rows = await _price.get_historical_data(sym, days)
            except Exception:
                return None
            closes = _closes_from_history(rows)
            if len(closes) < 50:
                return None
            return _compute_signal(sym, closes)

    results = await asyncio.gather(*[_one(s) for s in symbols], return_exceptions=True)
    return [r for r in results if isinstance(r, dict) and r]


@router.get("/signals")
async def get_signals(
    index: str = Query("NIFTY50"),
    verdict: str = Query("all", description="all|bullish|bearish|neutral"),
):
    code = index.upper().replace(" ", "").replace("-", "")
    cache_key = f"signals:{code}"
    cached = _cache_get(cache_key, ttl=900)
    if cached is None:
        symbols = INDEX_CONSTITUENTS.get(code, NIFTY50)[:50]
        # Force-seal intraday snapshots before reading disk for closes.
        try:
            await mcache.seal_eod_for_today_if_overdue(_price, symbols=list(symbols))
        except Exception:
            pass
        items = await _signals_async(symbols)
        cached = {"available": True, "items": items}
        _cache_set(cache_key, cached)
    items = cached.get("items", [])
    if verdict and verdict != "all":
        items = [it for it in items if it["verdict"].lower() == verdict.lower()]
    return {**cached, "items": items, "filterApplied": verdict, "meta": _meta("SIGNALS_ENGINE")}


# ────────────────────────────────────────────────────────────────────────────
# Market valuation (PriceService → Yahoo fallback for index history)
# ────────────────────────────────────────────────────────────────────────────
def _index_valuation_sync(codes: list[str], period: str) -> dict:
    """Indices proxy chart. Tries PriceService for each ticker first; if it
    has no rows (NSE indices often lack daily OHLCV), falls back to yfinance.
    Either way the result is the same daily-close series used elsewhere."""
    import yfinance as yf
    import asyncio as _aio
    period_days = {"1m":30,"6m":180,"1y":365,"5y":365*5,"10y":365*10}.get(period, 365*5)
    period_yf   = {"1m":"1mo","6m":"6mo","1y":"1y","5y":"5y","10y":"10y"}.get(period, "5y")
    label_map = {"^NSEI":"NIFTY 50","^NSEBANK":"NIFTY BANK","^NIFTY_FIN_SERVICE":"NIFTY FIN SERVICES"}

    series_dict: dict[str, dict[str, float]] = {}
    indices = []
    for code in codes:
        try:
            # 1) PriceService first — same daily OHLCV path used everywhere.
            ps_rows: list[dict] = []
            try:
                ps_rows = _aio.run(_price.get_historical_data(code, period_days))
            except RuntimeError:
                # Already inside an event loop — schedule on a fresh one.
                loop = _aio.new_event_loop()
                try:
                    ps_rows = loop.run_until_complete(_price.get_historical_data(code, period_days))
                finally:
                    loop.close()
            except Exception:
                ps_rows = []

            if ps_rows and len(ps_rows) >= 2:
                label = label_map.get(code, code)
                base = float(ps_rows[0].get("close", 0)) or 1.0
                for r in ps_rows:
                    d = str(r.get("date", ""))
                    if not d:
                        continue
                    series_dict.setdefault(d, {"date": d})[label] = round(float(r.get("close", 0)) / base * 22.0, 2)
                last = float(ps_rows[-1].get("close", 0))
                prev = float(ps_rows[-2].get("close", last))
                change = last - prev
                pct = (change / prev * 100) if prev else 0.0
                indices.append({"code": code, "label": label,
                                "lastPrice": round(last, 2),
                                "change":    round(change, 2),
                                "changePct": round(pct, 2)})
                continue

            # 2) Yahoo fallback — only when PriceService returns nothing.
            t = yf.Ticker(code)
            hist = t.history(period=period_yf, auto_adjust=False)
            if hist.empty:
                continue
            label = label_map.get(code, code)
            base = float(hist["Close"].iloc[0])
            for ts, close in hist["Close"].items():
                d = ts.strftime("%Y-%m-%d")
                series_dict.setdefault(d, {"date": d})[label] = round(float(close) / base * 22.0, 2)
            last = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else last
            indices.append({
                "code": code, "label": label, "lastPrice": round(last, 2),
                "change": round(last - prev, 2),
                "changePct": round((last - prev) / prev * 100, 2) if prev else 0.0,
            })
        except Exception as e:
            logger.debug("valuation %s failed: %s", code, e)
    series = sorted(series_dict.values(), key=lambda r: r["date"])
    return {
        "available": True,
        "message": "Index PE proxy normalised to 22x (true historical PE/PB requires an index data subscription).",
        "series": series,
        "indices": indices,
    }

# Note: market-valuation/index-valuation re-stamp meta below at request time so
# cached payloads always reflect the *current* market state, not the stamp from
# when the cache was filled.


@router.get("/index-valuation")
async def get_index_valuation(
    indices: str = Query("^NSEI,^NSEBANK"),
    period: str = Query("5y"),
    metric: str = Query("pe"),
):
    codes = [c.strip() for c in indices.split(",") if c.strip()]
    cache_key = f"index-val:{','.join(codes)}:{period}:{metric}"
    cached = _cache_get(cache_key, ttl=LONG_TTL)
    if cached is not None:
        return {**cached, "meta": _meta("VALUATION_ENGINE")}
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, _index_valuation_sync, codes, period)
    _cache_set(cache_key, res)
    return {**res, "meta": _meta("VALUATION_ENGINE")}


# Alias used by the frontend
@router.get("/market-valuation")
async def market_valuation(indices: str = Query("^NSEI,^NSEBANK"), period: str = Query("5y"),
                            metric: str = Query("pe")):
    return await get_index_valuation(indices=indices, period=period, metric=metric)


# ────────────────────────────────────────────────────────────────────────────
# Endpoints with no reachable feed (clean unavailable state)
# ────────────────────────────────────────────────────────────────────────────
NSE_BLOCKED_MSG = (
    "This dataset is published only on www.nseindia.com, which blocks requests "
    "from cloud IP ranges. We're tracking adding a SEBI/exchange-licensed feed."
)


@router.get("/fo-ban")
async def get_fo_ban():
    cached = _cache_get("fo-ban", ttl=LONG_TTL)
    if cached is not None:
        return cached
    try:
        from ..services.nse_service import NseService
        svc = NseService()
        data = await svc.fetch_nse("/api/liveMwpl?index=&symbol=&segLink=", "fno_mwpl", ttl=300)
    except Exception as e:
        logger.warning("fo-ban fetch failed: %s", e)
        data = None
    if not data:
        res = {"available": False, "message": NSE_BLOCKED_MSG, "items": []}
        _cache_set("fo-ban", res)
        return res
    items = []
    for r in data.get("data", []):
        items.append({
            "symbol": r.get("symbol"),
            "name": r.get("symbol"),
            "currentMwplPct": r.get("mwplPercentage"),
            "status": "Possible Entrant" if (r.get("mwplPercentage") or 0) >= 95 else "Watch",
        })
    res = {"available": True, "items": items}
    _cache_set("fo-ban", res)
    return res


@router.get("/top-deliveries")
async def get_top_deliveries(period: str = Query("daily"), index: str = Query("NIFTY50")):
    return {"available": False, "message": NSE_BLOCKED_MSG, "items": []}


@router.get("/fii-dii")
async def get_fii_dii(segment: str = Query("equity"), days: int = Query(365, ge=7, le=1500)):
    """FII/DII activity. Equity is real NSE data with a rolling local history.
    F&O segments fetch historical data using the NSE FNO participant endpoint."""
    from app.services.fii_dii_service import FiiDiiService
    svc = FiiDiiService()
    seg = (segment or "equity").lower().strip()
    return await svc.get_flows(seg, days=days)


@router.post("/fii-dii/backfill")
async def backfill_fii_dii(request: Request, days: int = Query(400, ge=30, le=1500)):
    """One-shot backfill of all 5 FII/DII segments into the local SQLite cache.
    Safe to call repeatedly — only missing date ranges are fetched. Persists to
    market_cache/fii_dii_cache.db so the file can be committed to git.

    Admin-only: this is a write/state-changing operation that triggers outbound
    NSE fetches, so it must be guarded by an admin session token (X-Admin-Token).
    Regular signed-in users are blocked here (and unauthenticated callers are
    already rejected by ClerkAuthMiddleware)."""
    from app.routes.admin import _require_admin
    from app.services.fii_dii_service import FiiDiiService
    if not _require_admin(request):
        return JSONResponse(status_code=403, content={"error": "Admin token required."})
    svc = FiiDiiService()
    return await svc.backfill_all(days=days)


@router.get("/slbm")
async def get_slbm():
    return {"available": False, "message": NSE_BLOCKED_MSG, "items": []}


@router.get("/mtf")
async def get_mtf():
    return {"available": False,
            "message": "Aggregated MTF data is broker-specific and not standardised across exchanges.",
            "items": []}


@router.get("/ipos")
async def get_ipos(status: str = Query("open")):
    return {"available": False,
            "message": ("Live IPO calendar requires the BSE/NSE IPO endpoint which is rate-limited "
                        "from cloud IPs. We're integrating Chittorgarh as a follow-up."),
            "items": []}


# ── Macro Pulse (Phase 3) ────────────────────────────────────────────────────
# Two endpoints back the new Macro tab and the persistent dashboard top-bar
# strip. Both delegate to MacroService which wraps FRED CSV downloads + Yahoo
# quotes and caches the result for 24h. Failures degrade to empty payloads —
# the route itself never raises.

@router.get("/macro/strip")
async def get_macro_strip():
    """Six tile-sized macro readings for the dashboard ribbon."""
    try:
        data = await _macro.get_strip()
    except Exception as e:
        logger.warning("macro/strip failed: %s", str(e)[:160])
        data = {"tiles": [], "fetchedAt": "", "sources": []}
    return {**data, "meta": _meta(served_from="MACRO_STRIP")}


@router.get("/macro")
async def get_macro_dashboard():
    """Full payload for the /insights/macro tab."""
    try:
        data = await _macro.get_dashboard()
    except Exception as e:
        logger.warning("macro dashboard failed: %s", str(e)[:160])
        data = {
            "rateTimeline": [], "cpi": [], "iip": [], "gdp": [],
            "yieldCurve": {"ind10yNow": None, "ind10yAsOf": None, "ind10yHistory": []},
            "currencyStrip": {"usdinr": {}, "dxy": {}, "brent": {}, "gold": {}, "vix": {}},
            "commentary": "Macro data is currently unavailable.",
            "fetchedAt": "", "sources": [],
        }
    return {**data, "meta": _meta(served_from="MACRO_DASHBOARD")}
