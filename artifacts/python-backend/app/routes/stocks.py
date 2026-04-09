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

# Map NSE index names to Yahoo Finance tickers (indices need the ^ prefix)
SYMBOL_MAP = {
    "NIFTY 50":    "^NSEI",
    "NIFTY50":     "^NSEI",
    "NIFTY":       "^NSEI",
    "BANKNIFTY":   "^NSEBANK",
    "BANK NIFTY":  "^NSEBANK",
    "FINNIFTY":    "^CNXFIN",
    "MIDCPNIFTY":  "^CNXSC",
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
):
    symbol = symbol.upper()
    if period   not in VALID_PERIODS:   period   = "1mo"
    if interval not in VALID_INTERVALS: interval = "1d"

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
                tk   = yf.Ticker(ticker_sym)
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
