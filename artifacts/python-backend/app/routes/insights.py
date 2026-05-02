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

logger = logging.getLogger("insights")
router = APIRouter(prefix="/insights", tags=["insights"])

_executor = ThreadPoolExecutor(max_workers=16)
_cache: dict[str, tuple[float, Any]] = {}
DEFAULT_TTL = 300              # 5 min for yfinance / fast-changing data
LONG_TTL    = 60 * 60 * 6      # 6 h for AMFI / BSE end-of-day data


def _cache_get(key: str, ttl: int = DEFAULT_TTL):
    hit = _cache.get(key)
    if hit and (time.time() - hit[0]) < ttl:
        return hit[1]
    return None


def _cache_set(key: str, value: Any):
    _cache[key] = (time.time(), value)


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


def _quote_from_closes(sym: str, closes: list[float], market_cap: float = 0.0) -> dict | None:
    if not closes or len(closes) < 2:
        return None
    close = float(closes[-1])
    base  = float(closes[0])
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


def _fetch_one_quote(sym: str, period_yf: str) -> dict | None:
    """Fetch a single quote. When the market is closed we first try the
    on-disk EOD cache (artifacts/python-backend/market_cache/<date>/) so we
    serve instantly without hitting yfinance. Successful live fetches are
    written back to disk for the next call."""
    days = _PERIOD_DAYS.get(period_yf, 7)
    market_open = mcache.is_market_open()

    # Disk-first when market is closed.
    if not market_open:
        cached = mcache.load_from_disk(sym, days)
        if cached:
            closes = [float(r.get("close", 0)) for r in cached if isinstance(r, dict)]
            mc = float(cached[0].get("marketCap", 0.0)) if cached and isinstance(cached[0], dict) else 0.0
            res = _quote_from_closes(sym, closes, mc)
            if res:
                return res

    import yfinance as yf
    try:
        t = yf.Ticker(sym)
        hist = t.history(period=period_yf, auto_adjust=False)
        if hist.empty or len(hist) < 2:
            return None
        closes = [float(x) for x in hist["Close"].tolist()]
        mc = 0.0
        try:
            mc = float(t.fast_info.get("marketCap") or 0.0)
        except Exception:
            pass
        # Persist to disk so the next "market closed" call is free.
        try:
            rows = [{"date": ts.strftime("%Y-%m-%d"), "close": float(c), "marketCap": mc}
                     for ts, c in hist["Close"].items()]
            mcache.save_to_disk(sym, days, rows)
        except Exception:
            pass
        return _quote_from_closes(sym, closes, mc)
    except Exception as e:
        logger.debug("heatmap %s failed: %s", sym, e)
        return None


def _heatmap_sync(symbols: list[str], period_yf: str) -> list[dict]:
    items: list[dict] = []
    futs = [_executor.submit(_fetch_one_quote, s, period_yf) for s in symbols]
    for f in futs:
        try:
            r = f.result(timeout=20)
            if r:
                items.append(r)
        except Exception:
            pass
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
    cached = _cache_get(cache_key)
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

    loop = asyncio.get_event_loop()
    items, idx_q = await asyncio.gather(
        loop.run_in_executor(None, _heatmap_sync, symbols, period_yf),
        loop.run_in_executor(None, _index_quote_sync, idx_ticker),
    )

    response = {
        "available": True,
        "index": code,
        "label": INDEX_LABELS.get(code, code),
        "indexPrice": idx_q.get("lastPrice"),
        "indexChange": idx_q.get("change"),
        "indexChangePct": idx_q.get("changePct"),
        "items": items,
    }
    _cache_set(cache_key, response)
    return response


# ────────────────────────────────────────────────────────────────────────────
# Company filings (BSE)
# ────────────────────────────────────────────────────────────────────────────
BSE_API = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
BSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.bseindia.com",
    "Referer": "https://www.bseindia.com/",
}


def _adapt_bse_announcements(payload: Any) -> list[dict]:
    """Convert BSE API JSON to our normalised filing shape."""
    if not isinstance(payload, dict):
        return []
    rows = payload.get("Table") or []
    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        scrip = str(r.get("SCRIP_CD", "")).strip()
        attachment = (r.get("ATTACHMENTNAME") or "").strip()
        doc_url = ""
        if attachment:
            doc_url = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{attachment}"
        out.append({
            "id": r.get("NEWSID", ""),
            "symbol": scrip,
            "company": (r.get("SLONGNAME") or "").strip() or scrip,
            "category": (r.get("CATEGORYNAME") or "").strip() or "Other",
            "purpose": (r.get("HEADLINE") or r.get("NEWSSUB") or "").strip(),
            "subject": (r.get("NEWSSUB") or "").strip(),
            "date": (r.get("NEWS_DT") or "").strip(),
            "documentUrl": doc_url,
        })
    return out


@router.get("/company-filings")
async def get_company_filings(
    category: str = Query("-1", description="-1=All; 'Result','AGM','Dividend','Board Meeting'..."),
    page: int = Query(1),
):
    cache_key = f"company-filings:{category}:{page}"
    cached = _cache_get(cache_key, ttl=900)  # 15 min
    if cached is not None:
        return cached
    try:
        async with httpx.AsyncClient(timeout=12.0, headers=BSE_HEADERS) as cli:
            resp = await cli.get(BSE_API, params={
                "pageno": page,
                "strCat": category,
                "strPrevDate": "",
                "strScrip": "",
                "strSearch": "P",
                "strToDate": "",
                "strType": "C",
            })
        resp.raise_for_status()
        items = _adapt_bse_announcements(resp.json())
    except Exception as e:
        logger.warning("BSE filings fetch failed: %s", e)
        return {"available": False, "message": "BSE feed temporarily unavailable.", "items": []}

    res = {"available": True, "source": "BSE Corporate Announcements", "items": items}
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


def _signals_sync(symbols: list[str]) -> list[dict]:
    """Compute per-symbol signals. Uses the EOD disk cache when the market is
    closed (same key/path scheme as the heatmap), saving on yfinance calls
    overnight and on weekends."""
    import yfinance as yf
    market_open = mcache.is_market_open()
    out = []
    def _one(sym):
        try:
            if not market_open:
                cached = mcache.load_from_disk(sym, _PERIOD_DAYS["6mo"])
                if cached:
                    closes = [float(r.get("close", 0)) for r in cached if isinstance(r, dict)]
                    if len(closes) >= 50:
                        return _compute_signal(sym, closes)
            h = yf.Ticker(sym).history(period="6mo", auto_adjust=False)
            if h.empty:
                return None
            closes = [float(x) for x in h["Close"].tolist()]
            try:
                rows = [{"date": ts.strftime("%Y-%m-%d"), "close": float(c)}
                         for ts, c in h["Close"].items()]
                mcache.save_to_disk(sym, _PERIOD_DAYS["6mo"], rows)
            except Exception:
                pass
            return _compute_signal(sym, closes)
        except Exception:
            return None
    futs = [_executor.submit(_one, s) for s in symbols]
    for f in futs:
        try:
            r = f.result(timeout=20)
            if r:
                out.append(r)
        except Exception:
            pass
    return out


@router.get("/signals")
async def get_signals(
    index: str = Query("NIFTY50"),
    verdict: str = Query("all", description="all|bullish|bearish|neutral"),
):
    code = index.upper().replace(" ", "").replace("-", "")
    cache_key = f"signals:{code}"
    cached = _cache_get(cache_key, ttl=900)
    if cached is None:
        symbols = INDEX_CONSTITUENTS.get(code, NIFTY50)
        loop = asyncio.get_event_loop()
        items = await loop.run_in_executor(None, _signals_sync, symbols[:50])
        cached = {"available": True, "items": items}
        _cache_set(cache_key, cached)
    items = cached.get("items", [])
    if verdict and verdict != "all":
        items = [it for it in items if it["verdict"].lower() == verdict.lower()]
    return {**cached, "items": items, "filterApplied": verdict}


# ────────────────────────────────────────────────────────────────────────────
# Market valuation (yfinance proxy)
# ────────────────────────────────────────────────────────────────────────────
def _index_valuation_sync(codes: list[str], period: str) -> dict:
    import yfinance as yf
    period_yf = {"1m":"1mo","6m":"6mo","1y":"1y","5y":"5y","10y":"10y"}.get(period, "5y")
    label_map = {"^NSEI":"NIFTY 50","^NSEBANK":"NIFTY BANK","^NIFTY_FIN_SERVICE":"NIFTY FIN SERVICES"}

    series_dict: dict[str, dict[str, float]] = {}
    indices = []
    for code in codes:
        try:
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
        return cached
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, _index_valuation_sync, codes, period)
    _cache_set(cache_key, res)
    return res


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
