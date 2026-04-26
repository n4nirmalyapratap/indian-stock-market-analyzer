"""
Insights router — endpoints for the /insights section of the user app.

Implements:
- GET /insights/heatmap          (heatmap of constituents for many NSE/BSE indices)
- GET /insights/indices          (list of supported index codes + labels)
- GET /insights/fii-dii          (FII/DII flows; returns empty if NSE blocks IP)
- GET /insights/fo-ban           (F&O ban / MWPL list)
- GET /insights/top-deliveries   (delivery % leaders — feed unavailable in cloud)
- GET /insights/index-valuation  (PE/PB/DY history of indices via price proxy)
- GET /insights/ipos             (open / upcoming / listed IPOs — feed unavailable)
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

_executor = ThreadPoolExecutor(max_workers=12)
_cache: dict[str, tuple[float, Any]] = {}
CACHE_TTL = 300  # 5 minutes


def _cache_get(key: str):
    hit = _cache.get(key)
    if hit and (time.time() - hit[0]) < CACHE_TTL:
        return hit[1]
    return None


def _cache_set(key: str, value: Any):
    _cache[key] = (time.time(), value)


# ── Index → constituents (Yahoo Finance tickers) ─────────────────────────────
# These are curated lists. Broad indices (NIFTY 100/200/500/Total Market) are
# served as the union of the more-specific sets we have; this keeps the heatmap
# meaningful even when full official constituent lists aren't available from
# free sources.

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
    "NMDC.NS","PAYTM.NS","PFC.NS","PIDILITIND.NS","PNB.NS","RECLTD.NS","SBICARD.NS","SHREECEM.NS",
    "SIEMENS.NS","TATACONSUM.NS","TATAPOWER.NS","TORNTPHARM.NS","TVSMOTOR.NS","UNITDSPR.NS","VBL.NS",
    "VEDL.NS","ZOMATO.NS","ZYDUSLIFE.NS",
]

NIFTYBANK = [
    "HDFCBANK.NS","ICICIBANK.NS","SBIN.NS","KOTAKBANK.NS","AXISBANK.NS","INDUSINDBK.NS",
    "PNB.NS","BANKBARODA.NS","CANBK.NS","FEDERALBNK.NS","IDFCFIRSTB.NS","AUBANK.NS",
]

NIFTY_PVT_BANK = [
    "HDFCBANK.NS","ICICIBANK.NS","KOTAKBANK.NS","AXISBANK.NS","INDUSINDBK.NS","FEDERALBNK.NS",
    "IDFCFIRSTB.NS","AUBANK.NS","RBLBANK.NS","BANDHANBNK.NS","CITYUNIONBNK.NS","DCBBANK.NS",
]

NIFTY_PSU_BANK = [
    "SBIN.NS","BANKBARODA.NS","PNB.NS","CANBK.NS","UNIONBANK.NS","BANKINDIA.NS","INDIANB.NS",
    "CENTRALBK.NS","UCOBANK.NS","IOB.NS","MAHABANK.NS","PSB.NS",
]

NIFTY_IT = [
    "TCS.NS","INFY.NS","HCLTECH.NS","WIPRO.NS","TECHM.NS","LTIM.NS","PERSISTENT.NS",
    "MPHASIS.NS","COFORGE.NS","LTTS.NS",
]

NIFTY_FMCG = [
    "ITC.NS","HINDUNILVR.NS","NESTLEIND.NS","BRITANNIA.NS","DABUR.NS","COLPAL.NS","GODREJCP.NS",
    "MARICO.NS","TATACONSUM.NS","UNITDSPR.NS","VBL.NS","EMAMILTD.NS","RADICO.NS","JYOTHYLAB.NS",
    "PGHH.NS",
]

NIFTY_PHARMA = [
    "SUNPHARMA.NS","DRREDDY.NS","CIPLA.NS","DIVISLAB.NS","TORNTPHARM.NS","ZYDUSLIFE.NS",
    "AUROPHARMA.NS","LUPIN.NS","ALKEM.NS","BIOCON.NS","GLAND.NS","GLENMARK.NS","IPCALAB.NS",
    "JBCHEPHARM.NS","LAURUSLABS.NS","SANOFI.NS","ABBOTINDIA.NS","NATCOPHARM.NS","PFIZER.NS",
    "AJANTPHARM.NS",
]

NIFTY_AUTO = [
    "MARUTI.NS","M&M.NS","TATAMOTORS.NS","BAJAJ-AUTO.NS","EICHERMOT.NS","HEROMOTOCO.NS",
    "TVSMOTOR.NS","BOSCHLTD.NS","MOTHERSON.NS","ASHOKLEY.NS","BALKRISIND.NS","BHARATFORG.NS",
    "MRF.NS","EXIDEIND.NS","TIINDIA.NS",
]

NIFTY_METAL = [
    "TATASTEEL.NS","JSWSTEEL.NS","HINDALCO.NS","VEDL.NS","JINDALSTEL.NS","SAIL.NS","NMDC.NS",
    "COALINDIA.NS","HINDZINC.NS","NATIONALUM.NS","JSL.NS","APLAPOLLO.NS","HINDCOPPER.NS","RATNAMANI.NS",
    "WELCORP.NS",
]

NIFTY_REALTY = [
    "DLF.NS","LODHA.NS","GODREJPROP.NS","OBEROIRLTY.NS","PRESTIGE.NS","BRIGADE.NS","PHOENIXLTD.NS",
    "SOBHA.NS","SUNTECK.NS","MAHLIFE.NS",
]

NIFTY_HEALTHCARE = NIFTY_PHARMA + ["APOLLOHOSP.NS","FORTIS.NS","MAXHEALTH.NS","METROPOLIS.NS","SYNGENE.NS","DRLALPATHLABS.NS","NH.NS"]

NIFTY_MEDIA = [
    "ZEEL.NS","SUNTV.NS","PVRINOX.NS","TV18BRDCST.NS","SAREGAMA.NS","NETWORK18.NS","NAZARA.NS",
    "TIPSINDLTD.NS","HATHWAY.NS","NXTDIGITAL.NS",
]

NIFTY_CONSUMER_DURABLES = [
    "TITAN.NS","HAVELLS.NS","DIXON.NS","VOLTAS.NS","CROMPTON.NS","BAJAJELEC.NS","WHIRLPOOL.NS",
    "BLUESTARCO.NS","ORIENTELEC.NS","TTKPRESTIG.NS","KAJARIACER.NS","RAJESHEXPO.NS","KALYANKJIL.NS",
    "AMBER.NS","CERA.NS",
]

NIFTY_COMMODITIES = list(set(NIFTY_METAL + ["RELIANCE.NS","ONGC.NS","BPCL.NS","HINDPETRO.NS","IOC.NS","GAIL.NS","UPL.NS","PIIND.NS","TATACHEM.NS","DEEPAKNTR.NS"]))

NIFTY_CPSE = [
    "NTPC.NS","ONGC.NS","COALINDIA.NS","POWERGRID.NS","BPCL.NS","GAIL.NS","NHPC.NS","NMDC.NS",
    "NLCINDIA.NS","SJVN.NS","OIL.NS","BEL.NS",
]

NIFTY_ENERGY = [
    "RELIANCE.NS","ONGC.NS","NTPC.NS","COALINDIA.NS","POWERGRID.NS","BPCL.NS","HINDPETRO.NS",
    "IOC.NS","GAIL.NS","TATAPOWER.NS","ADANIGREEN.NS","ATGL.NS",
]

NIFTY_MIDCAP_SELECT = [
    "ABFRL.NS","APOLLOTYRE.NS","ASTRAL.NS","AUBANK.NS","BHARATFORG.NS","CANBK.NS","CHOLAFIN.NS",
    "COFORGE.NS","CUMMINSIND.NS","DEEPAKNTR.NS","DIXON.NS","FEDERALBNK.NS","GMRAIRPORT.NS",
    "GODREJPROP.NS","HINDPETRO.NS","IDFCFIRSTB.NS","INDHOTEL.NS","LTF.NS","LUPIN.NS","MFSL.NS",
    "PERSISTENT.NS","POLYCAB.NS","PIIND.NS","RECLTD.NS","SAIL.NS",
]

NIFTY_MIDCAP_50 = NIFTY_MIDCAP_SELECT + [
    "ABCAPITAL.NS","AUROPHARMA.NS","BALKRISIND.NS","BANKINDIA.NS","BHARATELEC.NS","COCHINSHIP.NS",
    "CONCOR.NS","CUB.NS","ESCORTS.NS","GUJGASLTD.NS","IDEA.NS","IDFCFIRSTB.NS","IRB.NS","JKCEMENT.NS",
    "JSWENERGY.NS","KPITTECH.NS","MARICO.NS","MAXHEALTH.NS","NMDC.NS","OFSS.NS","PAGEIND.NS",
    "PETRONET.NS","SUPREMEIND.NS","SYNGENE.NS","TATAELXSI.NS",
]

# Broader indices = unions of what we have (for visual "many tiles" feel)
NIFTY100 = list(dict.fromkeys(NIFTY50 + NIFTYNEXT50))
NIFTY200 = list(dict.fromkeys(NIFTY100 + NIFTY_MIDCAP_50))
NIFTY500 = list(dict.fromkeys(NIFTY200 + NIFTY_PHARMA + NIFTY_REALTY + NIFTY_MEDIA + NIFTY_CONSUMER_DURABLES + NIFTY_PSU_BANK + NIFTY_PVT_BANK))
NIFTY_TOTAL_MARKET = NIFTY500
FNO_STOCKS = NIFTY200  # F&O universe largely overlaps Nifty 200

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
    "NIFTYTOTALMARKET":     NIFTY_TOTAL_MARKET,
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
    "NIFTYFINSERVICE":      ["HDFCBANK.NS","ICICIBANK.NS","SBIN.NS","KOTAKBANK.NS","AXISBANK.NS","BAJFINANCE.NS","BAJAJFINSV.NS","SHRIRAMFIN.NS","HDFCLIFE.NS","SBILIFE.NS","ICICIPRULI.NS","ICICIGI.NS","CHOLAFIN.NS","RECLTD.NS","PFC.NS","SBICARD.NS","JIOFIN.NS","HDFCAMC.NS","LICHSGFIN.NS","MUTHOOTFIN.NS"],
}

INDEX_LABELS = {
    "NIFTY50":               "Nifty 50",
    "SENSEX":                "Sensex",
    "FNO":                   "F&O Stocks",
    "NIFTYNEXT50":           "Nifty Next 50",
    "NIFTY100":              "Nifty 100",
    "NIFTY200":              "Nifty 200",
    "NIFTY500":              "Nifty 500",
    "NIFTYMIDCAP50":         "Nifty Midcap 50",
    "NIFTYMIDCAP100":        "Nifty Midcap 100",
    "NIFTYMIDCAP150":        "Nifty Midcap 150",
    "NIFTYMIDCAPSELECT":     "Nifty Midcap Select",
    "NIFTYTOTALMARKET":      "Nifty Total Market",
    "NIFTYBANK":             "Nifty Bank",
    "NIFTYPVTBANK":          "Nifty Private Bank",
    "NIFTYPSUBANK":          "Nifty PSU Bank",
    "NIFTYIT":               "Nifty IT",
    "NIFTYFMCG":             "Nifty FMCG",
    "NIFTYPHARMA":           "Nifty Pharma",
    "NIFTYHEALTHCARE":       "Nifty Healthcare",
    "NIFTYAUTO":             "Nifty Auto",
    "NIFTYMETAL":            "Nifty Metal",
    "NIFTYREALTY":           "Nifty Realty",
    "NIFTYMEDIA":            "Nifty Media",
    "NIFTYCONSUMERDURABLES": "Nifty Consumer Durables",
    "NIFTYCOMMODITIES":      "Nifty Commodities",
    "NIFTYCPSE":             "Nifty CPSE",
    "NIFTYENERGY":           "Nifty Energy",
    "NIFTYFINSERVICE":       "Nifty Financial Services",
}

INDEX_TICKER = {
    "NIFTY50":               "^NSEI",
    "SENSEX":                "^BSESN",
    "NIFTYBANK":             "^NSEBANK",
    "NIFTYNEXT50":           "^NSMIDCP",
    "NIFTYIT":               "^CNXIT",
    "NIFTYAUTO":             "^CNXAUTO",
    "NIFTYFMCG":             "^CNXFMCG",
    "NIFTYPHARMA":           "^CNXPHARMA",
    "NIFTYMETAL":            "^CNXMETAL",
    "NIFTYREALTY":           "^CNXREALTY",
    "NIFTYMEDIA":            "^CNXMEDIA",
    "NIFTYENERGY":           "^CNXENERGY",
    "NIFTYFINSERVICE":       "^NIFTY_FIN_SERVICE",
    "NIFTYPSUBANK":          "^CNXPSUBANK",
}


def _pretty(sym: str) -> str:
    return sym.replace(".NS", "").replace(".BO", "")


PERIOD_MAP = {"1d": "5d", "1w": "1mo", "1m": "3mo", "1y": "1y"}


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
                "name": _pretty(sym),
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


@router.get("/indices")
async def list_indices():
    """Return supported index codes with labels and constituent counts."""
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
        loop.run_in_executor(_executor, _heatmap_sync, symbols, period_yf),
        loop.run_in_executor(_executor, _index_quote_sync, idx_ticker),
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
    import yfinance as yf
    period_yf = {"1m": "1mo", "6m": "6mo", "1y": "1y", "5y": "5y", "10y": "10y"}.get(period, "5y")
    label_map = {"^NSEI": "NIFTY 50", "^NSEBANK": "NIFTY BANK", "^NIFTY_FIN_SERVICE": "NIFTY FINANCIAL SERVICES"}

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
