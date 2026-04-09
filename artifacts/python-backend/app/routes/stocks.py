import asyncio
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from ..services.stocks_service import StocksService
from ..services.nse_service import NseService
from ..services.yahoo_service import YahooService

router = APIRouter(prefix="/stocks", tags=["stocks"])

_nse = NseService()
_yahoo = YahooService()
_service = StocksService(_nse, _yahoo)

VALID_PERIODS   = {"1d","5d","1mo","3mo","6mo","1y","2y","5y"}
VALID_INTERVALS = {"1m","2m","5m","15m","30m","60m","90m","1d","5d","1wk","1mo"}

# Map index display names → Yahoo Finance tickers
# NSE broad-market
SYMBOL_MAP = {
    # ── NSE Broad Market ──────────────────────────────────────────────────────
    "NIFTY 50":               "^NSEI",
    "NIFTY50":                "^NSEI",
    "NIFTY":                  "^NSEI",
    "NIFTY NEXT 50":          "^NSMIDCP",
    "NIFTYNEXT50":            "^NSMIDCP",
    "NIFTY 100":              "^CNX100",
    "NIFTY100":               "^CNX100",
    "NIFTY 200":              "^CNX200",
    "NIFTY200":               "^CNX200",
    "NIFTY 500":              "^CNX500",
    "NIFTY500":               "^CNX500",
    "NIFTY MIDCAP 50":        "NIFMID50.NS",
    "NIFTY MIDCAP50":         "NIFMID50.NS",
    "NIFTY MIDCAP 100":       "^CNXMID",
    "NIFTY MIDCAP100":        "^CNXMID",
    "NIFTY MIDCAP 150":       "^NIFMDCP150",
    "NIFTY MIDCAP150":        "^NIFMDCP150",
    "NIFTY MIDCAP SELECT":    "NIFMDCPSEL.NS",
    "NIFTY SMALLCAP 50":      "NIFTYSC50.NS",
    "NIFTY SMALLCAP50":       "NIFTYSC50.NS",
    "NIFTY SMALLCAP 100":     "^CNXSC",
    "NIFTY SMALLCAP100":      "^CNXSC",
    "NIFTY SMALLCAP 250":     "^CNXSMCP250",
    "NIFTY SMALLCAP250":      "^CNXSMCP250",
    "NIFTY MICROCAP 250":     "NIFTYMICRO250.NS",
    "NIFTY LARGEMIDCAP 250":  "^NIFTYLARGMID250",

    # ── NSE Sectoral ──────────────────────────────────────────────────────────
    "NIFTY BANK":             "^NSEBANK",
    "BANKNIFTY":              "^NSEBANK",
    "BANK NIFTY":             "^NSEBANK",
    "NIFTY FIN SERVICE":      "^CNXFIN",
    "NIFTY FINANCIAL SERVICES": "^CNXFIN",
    "FINNIFTY":               "^CNXFIN",
    "NIFTY IT":               "^CNXIT",
    "NIFTY AUTO":             "^CNXAUTO",
    "NIFTY PHARMA":           "^CNXPHARMA",
    "NIFTY FMCG":             "^CNXFMCG",
    "NIFTY METAL":            "^CNXMETAL",
    "NIFTY REALTY":           "^CNXREALTY",
    "NIFTY ENERGY":           "^CNXENERGY",
    "NIFTY INFRA":            "^CNXINFRA",
    "NIFTY INFRASTRUCTURE":   "^CNXINFRA",
    "NIFTY PSU BANK":         "^CNXPSUBANK",
    "NIFTY MNC":              "^CNXMNC",
    "NIFTY MEDIA":            "^CNXMEDIA",
    "NIFTY HEALTHCARE":       "^CNXHEALTH",
    "NIFTY COMMODITIES":      "^CNXCOMDTY",
    "NIFTY SERVICES SECTOR":  "^CNXSERVICE",
    "NIFTY CPSE":             "^CNXCPSE",
    "NIFTY PSE":              "^CNXPSE",
    "NIFTY OIL & GAS":        "^CNXOILGAS",
    "NIFTY OIL AND GAS":      "^CNXOILGAS",
    "NIFTY CONSUMER DURABLES":"^CNXCONDURAB",
    "NIFTY INDIA CONSUMPTION": "^CNXCONSUM",
    "NIFTY INDIA DIGITAL":    "^CNXDIGITAL",
    "NIFTY INDIA DEFENCE":    "NIFTYINDDEF.NS",
    "MIDCPNIFTY":             "^NIFMDCP150",

    # ── NSE Strategy / Thematic ───────────────────────────────────────────────
    "INDIA VIX":              "^NSEVIXY",
    "NIFTY ALPHA 50":         "^NIFTYALPHA50",
    "NIFTY50 VALUE 20":       "^NIFTVAL20",
    "NIFTY QUALITY LOW-VOLATILITY 30": "^NIFQL30",

    # ── BSE Broad Market ──────────────────────────────────────────────────────
    "SENSEX":                 "^BSESN",
    "BSE SENSEX":             "^BSESN",
    "BSE 100":                "^BSE100",
    "BSE100":                 "^BSE100",
    "BSE 200":                "^BSE200",
    "BSE200":                 "^BSE200",
    "BSE 500":                "^BSE500",
    "BSE500":                 "^BSE500",
    "BSE MIDCAP":             "^BSEMIDCAP",
    "BSE MID CAP":            "^BSEMIDCAP",
    "BSE SMALLCAP":           "^BSESMLCAP",
    "BSE SMALL CAP":          "^BSESMLCAP",
    "BSE LARGECAP":           "^BSELCAP",
    "BSE LARGE CAP":          "^BSELCAP",

    # ── BSE Sectoral ──────────────────────────────────────────────────────────
    "BANKEX":                 "^BSEBANKEX",
    "BSE BANKEX":             "^BSEBANKEX",
    "BSE IT":                 "^BSEIT",
    "BSE HEALTHCARE":         "^BSEHEALTHCARE",
    "BSE AUTO":               "^BSEAUTO",
    "BSE FMCG":               "^BSEFMCG",
    "BSE METAL":              "^BSEMETAL",
    "BSE REALTY":             "^BSEREALTY",
    "BSE ENERGY":             "^BSEENERGY",
    "BSE POWER":              "^BSEPOWER",
    "BSE CAPITAL GOODS":      "^BSECG",
    "BSE CONSUMER DURABLES":  "^BSECD",
    "BSE TECK":               "^BSETECK",
    "BSE OIL & GAS":          "^BSEOILGAS",
    "BSE OIL AND GAS":        "^BSEOILGAS",
    "BSE UTILITIES":          "^BSEUTIL",
    "BSE FINANCE":            "^BSEFINANCE",
    "BSE INDUSTRIALS":        "^BSEINDUS",
    "BSE TELECOM":            "^BSETELECOM",
    "BSE COMMODITIES":        "^BSECOMDTY",
}


@router.get("/nifty100")
async def get_nifty100():
    return await _service.get_nifty100_stocks()


@router.get("/midcap")
async def get_midcap():
    return await _service.get_midcap_stocks()


@router.get("/smallcap")
async def get_smallcap():
    return await _service.get_smallcap_stocks()


@router.get("/search")
async def search_stocks(q: str = Query(default="")):
    """Search ALL_SYMBOLS universe by ticker or company name. Returns up to 20 results."""
    from ..lib.universe import ALL_SYMBOLS, COMPANY_MAP
    if not q or len(q.strip()) < 1:
        return {"results": []}
    q_upper = q.strip().upper()
    q_lower = q.strip().lower()
    # Tier 1: symbol starts-with (highest priority)
    starts   = [s for s in ALL_SYMBOLS if s.startswith(q_upper)]
    # Tier 2: symbol contains
    contains = [s for s in ALL_SYMBOLS if q_upper in s and not s.startswith(q_upper)]
    # Tier 3: company name contains
    name_set = set(starts + contains)
    by_name  = [s for s in ALL_SYMBOLS if s not in name_set
                and q_lower in COMPANY_MAP.get(s, "").lower()]
    combined = (starts + contains + by_name)[:20]
    return {
        "results": [{"symbol": s, "name": COMPANY_MAP.get(s, "")} for s in combined]
    }


@router.get("/{symbol}/history")
async def get_stock_history(
    symbol: str,
    period:   str = Query(default="1mo",  description="yfinance period, e.g. 1d 5d 1mo 3mo 6mo 1y"),
    interval: str = Query(default="1d",   description="yfinance interval, e.g. 5m 15m 1h 1d 1wk"),
    start:    str = Query(default=None,   description="Start date YYYY-MM-DD (overrides period)"),
    end:      str = Query(default=None,   description="End date YYYY-MM-DD (used with start)"),
):
    symbol = symbol.upper()
    if interval not in VALID_INTERVALS: interval = "1d"
    use_range = bool(start and end)
    if not use_range and period not in VALID_PERIODS: period = "1mo"

    import yfinance as yf

    def _fetch():
        # Check explicit map first (indices need ^ prefix, never .NS suffix)
        if symbol in SYMBOL_MAP:
            candidates = [SYMBOL_MAP[symbol]]
        elif symbol.startswith("^"):
            candidates = [symbol]
        else:
            candidates = [f"{symbol}.NS", symbol]

        for ticker_sym in candidates:
            try:
                tk = yf.Ticker(ticker_sym)
                if use_range:
                    hist = tk.history(start=start, end=end, interval=interval, auto_adjust=True)
                else:
                    hist = tk.history(period=period, interval=interval, auto_adjust=True)
                if not hist.empty:
                    return tk.info, hist
            except Exception:
                continue
        return {}, None

    info, hist = await asyncio.get_event_loop().run_in_executor(None, _fetch)

    if hist is None or hist.empty:
        return JSONResponse(status_code=404, content={"error": f"No history data found for {symbol}"})

    candles = []
    for dt_idx, row in hist.iterrows():
        try:
            ts = int(dt_idx.timestamp())
            candles.append({
                "time":   ts,
                "open":   round(float(row["Open"]),   2),
                "high":   round(float(row["High"]),   2),
                "low":    round(float(row["Low"]),    2),
                "close":  round(float(row["Close"]),  2),
                "volume": int(row.get("Volume", 0)),
            })
        except Exception:
            continue

    return {
        "symbol":      symbol,
        "period":      period,
        "interval":    interval,
        "companyName": info.get("longName") or info.get("shortName") or symbol,
        "currency":    info.get("currency", "INR"),
        "candles":     candles,
    }


@router.get("/{symbol}")
async def get_stock(symbol: str):
    data = await _service.get_stock_details(symbol)
    if data.get("error"):
        return JSONResponse(status_code=404, content={"error": data["error"]})
    return data
