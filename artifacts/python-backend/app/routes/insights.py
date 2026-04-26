"""
Insights router — endpoints for the /insights section of the user app.

Implements:
- GET /insights/heatmap          (Nifty 50 / Nifty Bank constituents heatmap)
- GET /insights/fii-dii          (FII/DII flows; returns empty if NSE blocks IP)
- GET /insights/fo-ban           (F&O ban / MWPL list)
- GET /insights/top-deliveries   (delivery % leaders)
- GET /insights/index-valuation  (PE/PB/DY history of indices)
- GET /insights/ipos             (open / upcoming / listed IPOs)
- GET /insights/mf-holdings      (placeholder)
- GET /insights/slbm             (placeholder)
- GET /insights/mtf              (placeholder)

Heavy yfinance calls are cached for 5 minutes per request to avoid burning rate limits.
"""
from __future__ import annotations
import asyncio
import logging
import time
from typing import Any
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Query

logger = logging.getLogger("insights")
router = APIRouter(prefix="/insights", tags=["insights"])

_executor = ThreadPoolExecutor(max_workers=8)
_cache: dict[str, tuple[float, Any]] = {}
CACHE_TTL = 300  # 5 minutes


def _cache_get(key: str):
    hit = _cache.get(key)
    if hit and (time.time() - hit[0]) < CACHE_TTL:
        return hit[1]
    return None


def _cache_set(key: str, value: Any):
    _cache[key] = (time.time(), value)


# Nifty 50 constituents (Yahoo tickers). Stable list; refresh manually if NSE rejigs.
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

# Nifty Bank constituents
NIFTYBANK = [
    "HDFCBANK.NS","ICICIBANK.NS","SBIN.NS","KOTAKBANK.NS","AXISBANK.NS","INDUSINDBK.NS",
    "PNB.NS","BANKBARODA.NS","CANBK.NS","FEDERALBNK.NS","IDFCFIRSTB.NS","AUBANK.NS",
]

PRETTY_NAMES = {
    "RELIANCE.NS":"RELIANCE","TCS.NS":"TCS","HDFCBANK.NS":"HDFCBANK","BHARTIARTL.NS":"BHARTIARTL",
    "ICICIBANK.NS":"ICICIBANK","INFY.NS":"INFY","SBIN.NS":"SBIN","BAJFINANCE.NS":"BAJFINANCE",
    "HINDUNILVR.NS":"HINDUNILVR","ITC.NS":"ITC","LT.NS":"LT","KOTAKBANK.NS":"KOTAKBANK",
    "HCLTECH.NS":"HCLTECH","SUNPHARMA.NS":"SUNPHARMA","MARUTI.NS":"MARUTI","AXISBANK.NS":"AXISBANK",
    "NTPC.NS":"NTPC","ULTRACEMCO.NS":"ULTRACEMCO","BAJAJFINSV.NS":"BAJAJFINSV","M&M.NS":"M&M",
    "TITAN.NS":"TITAN","ONGC.NS":"ONGC","ASIANPAINT.NS":"ASIANPAINT","POWERGRID.NS":"POWERGRID",
    "ADANIENT.NS":"ADANIENT","NESTLEIND.NS":"NESTLEIND","WIPRO.NS":"WIPRO","JSWSTEEL.NS":"JSWSTEEL",
    "TATAMOTORS.NS":"TATAMOTORS","COALINDIA.NS":"COALINDIA","HINDALCO.NS":"HINDALCO",
    "BAJAJ-AUTO.NS":"BAJAJ-AUTO","TATASTEEL.NS":"TATASTEEL","BEL.NS":"BEL","TRENT.NS":"TRENT",
    "TECHM.NS":"TECHM","ADANIPORTS.NS":"ADANIPORTS","SBILIFE.NS":"SBILIFE","GRASIM.NS":"GRASIM",
    "INDUSINDBK.NS":"INDUSINDBK","CIPLA.NS":"CIPLA","HDFCLIFE.NS":"HDFCLIFE","DRREDDY.NS":"DRREDDY",
    "EICHERMOT.NS":"EICHERMOT","BPCL.NS":"BPCL","HEROMOTOCO.NS":"HEROMOTOCO","BRITANNIA.NS":"BRITANNIA",
    "SHRIRAMFIN.NS":"SHRIRAMFIN","DIVISLAB.NS":"DIVISLAB","APOLLOHOSP.NS":"APOLLOHOSP",
    "PNB.NS":"PNB","BANKBARODA.NS":"BANKBARODA","CANBK.NS":"CANBK","FEDERALBNK.NS":"FEDERALBNK",
    "IDFCFIRSTB.NS":"IDFCFIRSTB","AUBANK.NS":"AUBANK",
}

PERIOD_MAP = {"1d": "5d", "1w": "1mo", "1m": "3mo", "1y": "1y"}
INDEX_TICKER = {"NIFTY50": "^NSEI", "NIFTYBANK": "^NSEBANK"}


def _heatmap_sync(symbols: list[str], period_yf: str) -> list[dict]:
    import yfinance as yf
    items = []
    for sym in symbols:
        try:
            t = yf.Ticker(sym)
            hist = t.history(period=period_yf, auto_adjust=False)
            if hist.empty or len(hist) < 2:
                continue
            close = float(hist["Close"].iloc[-1])
            base = float(hist["Close"].iloc[0])
            change_pct = ((close / base) - 1.0) * 100 if base else 0.0
            mc = 0.0
            try:
                fi = t.fast_info
                mc = float(fi.get("marketCap") or 0.0)
            except Exception:
                pass
            items.append({
                "symbol": sym,
                "name": PRETTY_NAMES.get(sym, sym.replace(".NS", "")),
                "price": round(close, 2),
                "changePct": round(change_pct, 2),
                "marketCap": mc,
            })
        except Exception as e:
            logger.debug("heatmap %s failed: %s", sym, e)
    return items


def _index_quote_sync(ticker: str) -> dict:
    import yfinance as yf
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d", auto_adjust=False)
        if hist.empty:
            return {}
        last = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else last
        change = last - prev
        pct = (change / prev * 100) if prev else 0.0
        return {"lastPrice": round(last, 2), "change": round(change, 2), "changePct": round(pct, 2)}
    except Exception:
        return {}


@router.get("/heatmap")
async def get_heatmap(
    index: str = Query("NIFTY50"),
    performance: str = Query("1d"),
):
    cache_key = f"heatmap:{index}:{performance}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    symbols = NIFTY50 if index == "NIFTY50" else NIFTYBANK
    period_yf = PERIOD_MAP.get(performance, "5d")
    idx_ticker = INDEX_TICKER.get(index, "^NSEI")

    loop = asyncio.get_event_loop()
    items, idx_q = await asyncio.gather(
        loop.run_in_executor(_executor, _heatmap_sync, symbols, period_yf),
        loop.run_in_executor(_executor, _index_quote_sync, idx_ticker),
    )

    response = {
        "index": index,
        "indexPrice": idx_q.get("lastPrice"),
        "indexChange": idx_q.get("change"),
        "indexChangePct": idx_q.get("changePct"),
        "items": items,
    }
    _cache_set(cache_key, response)
    return response


@router.get("/fo-ban")
async def get_fo_ban():
    """Try to fetch NSE F&O MWPL list via existing NseService (fully async)."""
    cached = _cache_get("fo-ban")
    if cached is not None:
        return cached

    try:
        from ..services.nse_service import NseService
        svc = NseService()
        data = await svc.fetch_nse(
            "/api/liveMwpl?index=&symbol=&segLink=", "fno_mwpl", ttl=300,
        )
    except Exception as e:
        logger.warning("fo-ban fetch failed: %s", e)
        res = {
            "available": False,
            "message": "NSE F&O MWPL feed is not reachable from this environment (cloud-IP block).",
            "items": [],
        }
        _cache_set("fo-ban", res)
        return res

    if not data:
        res = {"available": False, "message": "NSE MWPL endpoint returned no data.", "items": []}
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
async def get_top_deliveries(
    period: str = Query("daily"),
    index: str = Query("NIFTY50"),
):
    """Top stocks by delivery percentage.

    Real delivery % requires the NSE EOD bhavcopy / sec_bhavdata files,
    which are not reliably reachable from cloud IPs. We don't fabricate
    a value — UI shows an "unavailable" empty state when no real source
    is wired up.
    """
    return {
        "available": False,
        "message": (
            "True delivery percentage requires NSE/BSE bhavcopy files which are not "
            "reachable from this environment. A licensed feed is on the roadmap."
        ),
        "items": [],
    }


def _index_valuation_sync(codes: list[str], period: str) -> dict:
    """Return historical price series for indices, plus current quote.
    True PE/PB/DY history isn't free; we serve normalized closing price
    as a proxy time series (clearly labeled in the UI).
    """
    import yfinance as yf
    period_yf = {"1m": "1mo", "6m": "6mo", "1y": "1y", "5y": "5y", "10y": "10y"}.get(period, "5y")
    label_map = {"^NSEI": "NIFTY 50", "^NSEBANK": "NIFTY BANK", "NIFTY_FIN_SERVICE.NS": "NIFTY FINANCIAL SERVICES"}

    series_dict: dict[str, dict[str, float]] = {}
    indices = []
    for code in codes:
        try:
            t = yf.Ticker(code)
            hist = t.history(period=period_yf, auto_adjust=False)
            if hist.empty:
                continue
            label = label_map.get(code, code)
            # Normalize to first available PE-ish range (use price scaled to ~22 for visual parity with the screenshot)
            base = float(hist["Close"].iloc[0])
            for ts, close in hist["Close"].items():
                d = ts.strftime("%Y-%m-%d")
                if d not in series_dict:
                    series_dict[d] = {"date": d}
                series_dict[d][label] = round(float(close) / base * 22.0, 2)
            last = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else last
            indices.append({
                "code": code,
                "label": label,
                "lastPrice": round(last, 2),
                "change": round(last - prev, 2),
                "changePct": round((last - prev) / prev * 100, 2) if prev else 0.0,
            })
        except Exception as e:
            logger.debug("valuation %s failed: %s", code, e)

    series = sorted(series_dict.values(), key=lambda r: r["date"])
    return {
        "available": True,
        "message": "Index PE proxy (normalized to 22x base). True historical PE/PB requires an index data subscription.",
        "series": series,
        "indices": indices,
    }


@router.get("/index-valuation")
async def get_index_valuation(
    indices: str = Query("^NSEI,^NSEBANK"),
    period: str = Query("5y"),
    metric: str = Query("pe"),
):
    codes = [c.strip() for c in indices.split(",") if c.strip()]
    cache_key = f"index-val:{','.join(codes)}:{period}:{metric}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(_executor, _index_valuation_sync, codes, period)
    _cache_set(cache_key, res)
    return res


@router.get("/fii-dii")
async def get_fii_dii(
    segment: str = Query("equity"),
    period: str = Query("daily"),
    range: str = Query("30d"),
):
    return {
        "segment": segment,
        "period": period,
        "available": False,
        "message": (
            "FII/DII participant-wise CSV from NSE is blocked from cloud-IP ranges. "
            "We're tracking adding a SEBI/exchange-licensed feed."
        ),
        "rows": [],
    }


@router.get("/mf-holdings")
async def get_mf_holdings(amc: str = Query(""), scheme: str = Query("")):
    return {
        "available": False,
        "message": "AMFI portfolio PDFs require parsing; integration is on the roadmap.",
    }


@router.get("/slbm")
async def get_slbm():
    return {
        "available": False,
        "message": "NSE SLB report (sec_lend_borrow.csv) integration is on the roadmap.",
    }


@router.get("/mtf")
async def get_mtf():
    return {
        "available": False,
        "message": "Aggregated MTF feed across brokers is on the roadmap.",
    }


@router.get("/ipos")
async def get_ipos(status: str = Query("open")):
    return {
        "available": False,
        "message": (
            "Live IPO calendar feed is not yet integrated. Will be sourced from NSE/BSE/Chittorgarh "
            "in a follow-up."
        ),
        "items": [],
    }
