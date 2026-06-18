import asyncio
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from ..services import registry as svc
from ..services import market_cache_service as _disk
from ..lib.symbol_map import SYMBOL_MAP, to_yahoo_ticker, yahoo_candidates  # noqa: F401  (re-export for callers)

router = APIRouter(prefix="/stocks", tags=["stocks"])






VALID_PERIODS   = {"1d","5d","1mo","3mo","6mo","1y","2y","5y","10y","max"}
VALID_INTERVALS = {"1m","2m","5m","15m","30m","60m","90m","1h","1d","5d","1wk","1mo"}

# Fundamentals change quarterly — cache for 24 h so repeated visits to the
# Financials tab don't re-issue multiple blocking yfinance calls every time.
import time as _time
_FINANCIALS_CACHE: dict[str, tuple[float, dict]] = {}
_FINANCIALS_TTL = 24 * 3600


def _provenance() -> dict:
    return {
        "source":       "NSE",
        "servedFrom":   "MIXED",
        "asOf":         _disk._now_ist().isoformat(),
        "marketState":  _disk.current_market_state(),
        "cacheVersion": _disk.cache_version(),
    }


def _history_meta(chart: dict) -> dict:
    """
    Build meta for history endpoints.

    `source`/`asOf`/`eodSealed`/`eodDate` describe the candle series itself —
    on `/history` they are the history provenance. We *also* publish them
    under `historySource` / `historyAsOf` / etc. so any consumer that uses the
    unified `MarketDataMeta` shape (where quote-source and history-source can
    differ — e.g. live NSE quote with disk-EOD bars) gets a single field name
    to read across endpoints.
    """
    src        = chart.get("source")
    as_of      = chart.get("asOf")
    eod_sealed = chart.get("eodSealed")
    eod_date   = chart.get("eodDate")
    return {
        "source":           src,
        "asOf":             as_of,
        "marketState":      chart.get("marketState"),
        "eodSealed":        eod_sealed,
        "eodDate":          eod_date,
        "cacheVersion":     _disk.cache_version(),
        # Aliased fields — on /history the candles ARE the payload, so the
        # history-* fields just mirror source/asOf. The aliases exist so the
        # frontend's MarketDataMeta interface works uniformly across
        # /details (quote ≠ history) and /history (quote == history).
        "historySource":    src,
        "historyAsOf":      as_of,
        "historyEodSealed": eod_sealed,
        "historyEodDate":   eod_date,
    }


@router.get("/nifty100")
async def get_nifty100():
    return await svc.stocks.get_nifty100_stocks()


@router.get("/midcap")
async def get_midcap():
    return await svc.stocks.get_midcap_stocks()


@router.get("/smallcap")
async def get_smallcap():
    return await svc.stocks.get_smallcap_stocks()


@router.get("/search")
async def search_stocks(q: str = Query(default="")):
    """Search ALL_SYMBOLS universe by ticker or company name. Returns up to 20 results.

    Minimum 2 characters — single-character queries are too noisy to be useful
    (e.g. 'A' returned 200+ matches and broke the dropdown UX).
    """
    from ..lib.universe import ALL_SYMBOLS, COMPANY_MAP
    if not q or len(q.strip()) < 2:
        return {"results": []}
    q_upper = q.strip().upper()
    q_lower = q.strip().lower()
    starts   = [s for s in ALL_SYMBOLS if s.startswith(q_upper)]
    contains = [s for s in ALL_SYMBOLS if q_upper in s and not s.startswith(q_upper)]
    name_set = set(starts + contains)
    by_name  = [s for s in ALL_SYMBOLS if s not in name_set
                and q_lower in COMPANY_MAP.get(s, "").lower()]
    combined = (starts + contains + by_name)[:20]
    return {
        "results": [{"symbol": s, "name": COMPANY_MAP.get(s, "")} for s in combined]
    }


@router.get("/quotes")
async def get_quotes(symbols: str = Query(default="", description="Comma-separated NSE symbols")):
    """Lightweight batch quotes for watchlist-style consumers — company
    name, last price and %change only.

    `/stocks/{symbol}` pulls 500 days of history, computes the full
    technical-analysis stack, and (closed-market) runs an NSE-vs-Yahoo
    divergence cross-check — all wasted on a watchlist row that shows
    only price + %change. This endpoint skips every one of those.

    Closed market: served straight from the sealed EOD bars on disk
    (zero network) — see below. Open market: a plain quote per symbol
    with the divergence cross-check disabled, concurrency bounded.
    """
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()][:100]
    if not syms:
        return {"quotes": []}

    # ── Closed-market fast path ──────────────────────────────────────────────
    # The official closes are sealed on disk by the post-close warmup, so serve
    # price + %change straight from the last two sealed bars: zero network,
    # instant, and identical to the EOD overlay the detail panel shows (the row
    # and the detail panel never disagree). Without this, every symbol walks the
    # live chain whose NSE provider is tried FIRST — and while NSE is IP-blocked
    # that serialises on the cookie lock and burns the retry+sleep loop per
    # symbol (the watchlist "stuck on Loading…"). Symbols not yet sealed (cold
    # start before the warmup runs) fall through to the live quote below.
    disk_hits: dict[str, dict] = {}
    if not _disk.is_market_open():
        from ..lib.universe import COMPANY_MAP  # noqa: PLC0415 — bars carry no name

        def _disk_quote(sym):
            payload = _disk.load_with_meta(sym, 5)
            if not (payload and payload.get("eodSealed") and payload.get("data")):
                return None
            bars = payload["data"]
            if len(bars) < 2:
                return None
            last, prev = bars[-1], bars[-2]
            lc, pc = last.get("close"), prev.get("close")
            if lc is None or pc is None or not pc:
                return None
            try:
                lc, pc = float(lc), float(pc)
            except (TypeError, ValueError):
                return None
            return {
                "symbol":      sym,
                "companyName": COMPANY_MAP.get(sym) or sym,
                "lastPrice":   round(lc, 2),
                "pChange":     round((lc - pc) / pc * 100, 2),
            }

        def _read_all():
            out: dict[str, dict] = {}
            for s in syms:
                q = _disk_quote(s)
                if q is not None:
                    out[s] = q
            return out

        # Off the event loop — up to 100 small file reads.
        disk_hits = await asyncio.to_thread(_read_all)

    sem = asyncio.Semaphore(8)

    async def _one(sym: str) -> dict:
        if sym in disk_hits:
            return disk_hits[sym]
        async with sem:
            try:
                snap = await svc.price.get_quote_with_meta(sym, cross_check=False)
            except Exception:
                snap = None
        if not snap:
            return {"symbol": sym, "error": "not found"}
        q = snap["quote"]
        return {
            "symbol":      sym,
            "companyName": q.get("companyName") or sym,
            "lastPrice":   q.get("lastPrice"),
            "pChange":     q.get("pChange"),
        }

    quotes = await asyncio.gather(*[_one(s) for s in syms])
    return {"quotes": quotes}


@router.get("/{symbol}/history")
async def get_stock_history(
    symbol: str,
    period:   str = Query(default="1mo",  description="Period: 1d 5d 1mo 3mo 6mo 1y 2y 5y"),
    interval: str = Query(default="1d",   description="Interval: 1m 5m 15m 30m 1h 1d 1wk 1mo"),
    start:    str = Query(default=None,   description="Start date YYYY-MM-DD (overrides period — Yahoo only)"),
    end:      str = Query(default=None,   description="End date YYYY-MM-DD (used with start)"),
):
    """
    Chart candles. Daily ('1d') comes from PriceService (NSE-first → disk EOD →
    Yahoo) so it matches every other page. Sub-daily intervals always go to
    Yahoo (NSE only exposes daily EOD).
    """
    symbol = symbol.upper()
    # Honest 4xx instead of silently coercing to defaults — caller asked for
    # something we don't support; pretending we honoured it would just hand
    # back the wrong chart with no signal that the request was malformed.
    if interval == "60m":
        interval = "1h"
    if interval not in VALID_INTERVALS:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid interval '{interval}'. Allowed: {sorted(VALID_INTERVALS)}"},
        )
    use_range = bool(start and end)
    if not use_range and period not in VALID_PERIODS:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid period '{period}'. Allowed: {sorted(VALID_PERIODS)}"},
        )

    # Custom start/end range → PriceService (single source of truth)
    if use_range:
        chart = await svc.price.get_range_history(symbol, start=start, end=end, interval=interval)
        if not chart.get("candles"):
            return JSONResponse(status_code=404, content={"error": f"No history data found for {symbol}"})
        return {
            "symbol":      symbol,
            "period":      period,
            "interval":    interval,
            "companyName": chart.get("companyName") or symbol,
            "currency":    chart.get("currency", "INR"),
            "candles":     chart["candles"],
            "meta": _history_meta(chart),
        }

    # Standard period+interval — go through PriceService
    chart = await svc.price.get_intraday_history(symbol, period=period, interval=interval)
    if not chart.get("candles"):
        return JSONResponse(status_code=404, content={"error": f"No history data found for {symbol}"})

    return {
        "symbol":      symbol,
        "period":      period,
        "interval":    interval,
        "companyName": chart.get("companyName") or symbol,
        "currency":    chart.get("currency", "INR"),
        "candles":     chart["candles"],
        "meta": _history_meta(chart),
    }


@router.get("/{symbol}/financials")
async def get_stock_financials(symbol: str):
    """
    TradingView-style financials. Yahoo is used for fundamentals (income statement,
    balance sheet, cash flow, dividends, EPS) — these are reported quarterly /
    annually so the EOD-vs-intraday distinction does not apply. We still stamp
    the response with provenance metadata so the UI can label the data source.
    All monetary values are in ₹ Crores (1 Crore = 1e7).
    """
    import math
    import pandas as pd
    import yfinance as yf

    symbol = symbol.upper()

    # Financials are quarterly/annual — serve from 24-hour cache on repeat visits
    # so the Financials tab doesn't re-issue multiple blocking yfinance calls.
    _fin_cached = _FINANCIALS_CACHE.get(symbol)
    if _fin_cached and (_time.time() - _fin_cached[0]) < _FINANCIALS_TTL:
        return _fin_cached[1]

    def _safe(val):
        try:
            if val is None:
                return None
            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                return None
            return val
        except Exception:
            return None

    def _cr(val):
        v = _safe(val)
        return None if v is None else round(float(v) / 1e7, 2)

    def _pct(val):
        v = _safe(val)
        return None if v is None else round(float(v) * 100, 2)

    def _f(val, decimals=2):
        v = _safe(val)
        return None if v is None else round(float(v), decimals)

    import logging as _logging
    _flog = _logging.getLogger(__name__)

    def _df_to_list(df, row_map: dict, sort_asc=True):
        if df is None or df.empty:
            return []
        results = []
        for col in df.columns:
            entry = {"date": str(col.date())}
            for out_key, (row_name, fn) in row_map.items():
                try:
                    val = df.loc[row_name, col] if row_name in df.index else None
                    entry[out_key] = fn(val)
                except Exception as e:
                    # Don't swallow silently — a row that's consistently broken
                    # for every column is a Yahoo schema change we want to know
                    # about, not a data point we can pretend doesn't exist.
                    _flog.debug(
                        "financials: failed extracting %s/%s for %s — %s: %s",
                        out_key, row_name, symbol, type(e).__name__, e,
                    )
                    entry[out_key] = None
            results.append(entry)
        if sort_asc:
            results.sort(key=lambda x: x["date"])
        return results

    def _fetch():
        for tick_sym in yahoo_candidates(symbol):
            try:
                t = yf.Ticker(tick_sym)
                info = t.info or {}
                if not (info.get("regularMarketPrice") or info.get("currentPrice") or info.get("marketCap")):
                    continue
                return {
                    "info":          info,
                    "financials":    t.financials,
                    "q_financials":  t.quarterly_financials,
                    "balance_sheet": t.balance_sheet,
                    "cash_flow":     t.cash_flow,
                    "dividends":     t.dividends,
                }
            except Exception:
                continue
        return None

    raw = await asyncio.to_thread(_fetch)
    if raw is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"No financial data found for {symbol}. Check the NSE symbol is correct."},
        )

    info = raw["info"]
    fs   = raw["financials"]
    qfs  = raw["q_financials"]
    bs   = raw["balance_sheet"]
    cf   = raw["cash_flow"]
    divs = raw["dividends"]

    INCOME_MAP = {
        "revenue":         ("Total Revenue",    _cr),
        "grossProfit":     ("Gross Profit",      _cr),
        "operatingIncome": ("Operating Income",  _cr),
        "netIncome":       ("Net Income",        _cr),
        "ebitda":          ("EBITDA",            _cr),
    }
    BS_MAP = {
        "totalAssets": ("Total Assets",              _cr),
        "totalDebt":   ("Total Debt",                _cr),
        "equity":      ("Common Stock Equity",       _cr),
        "cash":        ("Cash And Cash Equivalents", _cr),
    }
    CF_MAP = {
        "operatingCF": ("Operating Cash Flow",  _cr),
        "investingCF": ("Investing Cash Flow",  _cr),
        "financingCF": ("Financing Cash Flow",  _cr),
        "freeCF":      ("Free Cash Flow",       _cr),
        "capex":       ("Capital Expenditure",  _cr),
    }

    # Yahoo often returns one extra period at the oldest edge (e.g. FY22)
    # with every value NaN → null. Drop any period where all metrics are
    # null so the UI doesn't render an empty column of dashes; a row with
    # even one real value is kept.
    def _has_values(row: dict) -> bool:
        return any(v is not None for k, v in row.items() if k != "date")

    annual_income    = [r for r in _df_to_list(fs,  INCOME_MAP) if _has_values(r)]
    quarterly_income = [r for r in _df_to_list(qfs, INCOME_MAP) if _has_values(r)]
    annual_bs        = [r for r in _df_to_list(bs,  BS_MAP) if _has_values(r)]
    annual_cf        = [r for r in _df_to_list(cf,  CF_MAP) if _has_values(r)]

    eps_annual    = [r for r in _df_to_list(fs,  {"eps": ("Diluted EPS", _f)}) if r["eps"] is not None]
    eps_quarterly = [r for r in _df_to_list(qfs, {"eps": ("Diluted EPS", _f)}) if r["eps"] is not None]

    div_list = []
    if divs is not None and len(divs) > 0:
        for dt, amount in divs.items():
            v = _safe(amount)
            if v is not None:
                div_list.append({"date": str(pd.Timestamp(dt).date()), "amount": round(float(v), 2)})
        div_list.sort(key=lambda x: x["date"])

    ov = info
    overview = {
        "marketCap":       _safe(ov.get("marketCap")),
        "trailingPE":      _f(ov.get("trailingPE")),
        "forwardPE":       _f(ov.get("forwardPE")),
        "priceToBook":     _f(ov.get("priceToBook")),
        "priceToSales":    _f(ov.get("priceToSalesTrailing12Months")),
        "evToEbitda":      _f(ov.get("enterpriseToEbitda")),
        "trailingEps":     _f(ov.get("trailingEps")),
        "forwardEps":      _f(ov.get("forwardEps")),
        "roe":             _pct(ov.get("returnOnEquity")),
        "roa":             _pct(ov.get("returnOnAssets")),
        "debtToEquity":    _f(ov.get("debtToEquity")),
        "currentRatio":    _f(ov.get("currentRatio")),
        "grossMargin":     _pct(ov.get("grossMargins")),
        "operatingMargin": _pct(ov.get("operatingMargins")),
        "netMargin":       _pct(ov.get("profitMargins")),
        "dividendYield":   _pct(ov.get("dividendYield")),
        "dividendRate":    _f(ov.get("dividendRate")),
        "earningsGrowth":  _pct(ov.get("earningsGrowth")),
        "revenueGrowth":   _pct(ov.get("revenueGrowth")),
        "bookValue":       _f(ov.get("bookValue")),
        "weekChange52":    _pct(ov.get("52WeekChange")),
    }

    _result = {
        "symbol":      symbol,
        "companyName": info.get("longName") or info.get("shortName") or symbol,
        "currency":    info.get("currency", "INR"),
        "overview":    overview,
        "incomeStatement": {"annual": annual_income, "quarterly": quarterly_income},
        "balanceSheet":    {"annual": annual_bs},
        "cashFlow":        {"annual": annual_cf},
        "dividends": div_list,
        "eps": {"annual": eps_annual, "quarterly": eps_quarterly},
        "meta": {
            "source":      "YAHOO",
            "asOf":        _disk._now_ist().isoformat(),
            "marketState": _disk.current_market_state(),
            "note":        "Fundamentals are quarterly/annual — not affected by intraday market state.",
        },
    }
    _FINANCIALS_CACHE[symbol] = (_time.time(), _result)
    return _result


@router.get("/{symbol}/dcf")
async def get_stock_dcf(symbol: str):
    """
    Two-stage DCF intrinsic-value snapshot for a single equity.

    Same data source (Yahoo) and same calculation as the bot's `/dcf`
    command — exposes them here so the web app shows identical numbers.
    """
    from ..services import dcf_service
    res = await dcf_service.compute_dcf(symbol)
    if res.get("error"):
        return JSONResponse(status_code=404, content=res)
    return res


@router.get("/{symbol}/technical-summary")
async def get_technical_summary(symbol: str, interval: str = "1d"):
    """
    TradingView-style technical summary:
    - oscillators (RSI, Stochastic, CCI, ADX, AO, Momentum, MACD, StochRSI, WR, BBP, UO)
    - moving averages (EMA/SMA 10-200, Ichimoku, VWMA, HMA)
    - pivots (Classic, Fibonacci, Camarilla, Woodie, DM)
    - aggregate summary signal (STRONG_BUY / BUY / NEUTRAL / SELL / STRONG_SELL)

    Daily ('1d') uses PriceService → NSE-first daily OHLCV (matches every other
    page). Sub-daily intervals fall through to Yahoo.
    """
    import math
    import pandas as pd

    symbol_upper = symbol.upper()
    market_state = _disk.current_market_state()

    # Map frontend interval → fetch strategy
    INTERVAL_MAP = {
        "1m":  ("7d",  "1m"),
        "5m":  ("60d", "5m"),
        "15m": ("60d", "15m"),
        "30m": ("60d", "30m"),
        "1h":  ("60d", "60m"),
        "2h":  ("60d", "60m"),
        "4h":  ("60d", "60m"),
        "1d":  ("2y",  "1d"),
        "1w":  ("10y", "1wk"),
        "1mo": ("10y", "1mo"),
    }
    period, yf_interval = INTERVAL_MAP.get(interval, ("2y", "1d"))

    def _safe_float(v):
        if v is None:
            return None
        try:
            f = float(v)
            return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
        except Exception:
            return None

    def _last(series: pd.Series):
        return _safe_float(series.dropna().iloc[-1] if not series.dropna().empty else None)

    def _signal_score(buy: int, sell: int, neutral: int) -> str:
        total = buy + sell + neutral
        if total == 0:
            return "NEUTRAL"
        score = (buy - sell) / total
        if score >= 0.5:  return "STRONG_BUY"
        if score > 0.1:   return "BUY"
        if score <= -0.5: return "STRONG_SELL"
        if score < -0.1:  return "SELL"
        return "NEUTRAL"

    def _compute(df: pd.DataFrame) -> dict:
        from ta.momentum import (
            RSIIndicator, StochasticOscillator, AwesomeOscillatorIndicator,
            WilliamsRIndicator, UltimateOscillator, StochRSIIndicator,
        )
        from ta.trend import (
            CCIIndicator, ADXIndicator, MACD, EMAIndicator, SMAIndicator,
            WMAIndicator, IchimokuIndicator,
        )

        close, high, low, volume, open_ = df["Close"], df["High"], df["Low"], df["Volume"], df["Open"]

        # ── Oscillators ─────────────────────────────────────────────────────
        rsi_val      = _last(RSIIndicator(close, window=14).rsi())
        stoch        = StochasticOscillator(high, low, close, window=14, smooth_window=3)
        stoch_k_val  = _last(stoch.stoch_signal())
        cci_val      = _last(CCIIndicator(high, low, close, window=20).cci())
        adx_ind      = ADXIndicator(high, low, close, window=14)
        adx_val      = _last(adx_ind.adx())
        adx_pos      = _last(adx_ind.adx_pos())
        adx_neg      = _last(adx_ind.adx_neg())
        ao_val       = _last(AwesomeOscillatorIndicator(high, low).awesome_oscillator())
        mom_series   = close - close.shift(10)
        mom_val      = _last(mom_series)
        macd_ind     = MACD(close, window_fast=12, window_slow=26, window_sign=9)
        macd_val     = _last(macd_ind.macd())
        macd_sig_val = _last(macd_ind.macd_signal())
        srsi_ind     = StochRSIIndicator(close, window=14, smooth1=3, smooth2=3)
        srsi_k_val   = _last(srsi_ind.stochrsi_k())
        wr_val       = _last(WilliamsRIndicator(high, low, close, lbp=14).williams_r())
        uo_val       = _last(UltimateOscillator(high, low, close,
                                                 window1=7, window2=14, window3=28).ultimate_oscillator())
        ema13_val    = _last(EMAIndicator(close, window=13).ema_indicator())
        close_last   = _safe_float(close.iloc[-1]) if len(close) > 0 else None
        bbp_val      = (_safe_float(close.iloc[-1]) - ema13_val) if (close_last and ema13_val) else None

        def _osc_signal(name: str, val, **kwargs) -> str:
            if val is None: return "NEUTRAL"
            if name == "RSI (14)":
                return "BUY" if val < 30 else ("SELL" if val > 70 else "NEUTRAL")
            if name == "Stochastic %K (14, 3, 3)":
                return "BUY" if val < 20 else ("SELL" if val > 80 else "NEUTRAL")
            if name == "CCI (20)":
                return "BUY" if val < -100 else ("SELL" if val > 100 else "NEUTRAL")
            if name == "ADX (14)":
                a_pos, a_neg = kwargs.get("adx_pos"), kwargs.get("adx_neg")
                if val > 20 and a_pos and a_neg:
                    return "BUY" if a_pos > a_neg else "SELL"
                return "NEUTRAL"
            if name == "Awesome Oscillator":
                return "BUY" if val > 0 else ("SELL" if val < 0 else "NEUTRAL")
            if name == "Momentum (10)":
                return "BUY" if val > 0 else ("SELL" if val < 0 else "NEUTRAL")
            if name == "MACD Level (12, 26)":
                sig = kwargs.get("macd_signal")
                if sig is None: return "NEUTRAL"
                return "BUY" if val > sig else ("SELL" if val < sig else "NEUTRAL")
            if name == "Stochastic RSI Fast (3, 3, 14, 14)":
                return "BUY" if val < 0.2 else ("SELL" if val > 0.8 else "NEUTRAL")
            if name == "Williams %R (14)":
                return "BUY" if val < -80 else ("SELL" if val > -20 else "NEUTRAL")
            if name == "Bull Bear Power":
                return "BUY" if val > 0 else ("SELL" if val < 0 else "NEUTRAL")
            if name == "Ultimate Oscillator (7, 14, 28)":
                return "BUY" if val < 30 else ("SELL" if val > 70 else "NEUTRAL")
            return "NEUTRAL"

        oscillators = [
            ("RSI (14)",                            rsi_val,     {}),
            ("Stochastic %K (14, 3, 3)",            stoch_k_val, {}),
            ("CCI (20)",                            cci_val,     {}),
            ("ADX (14)",                            adx_val,     {"adx_pos": adx_pos, "adx_neg": adx_neg}),
            ("Awesome Oscillator",                  ao_val,      {}),
            ("Momentum (10)",                       mom_val,     {}),
            ("MACD Level (12, 26)",                 macd_val,    {"macd_signal": macd_sig_val}),
            ("Stochastic RSI Fast (3, 3, 14, 14)",  srsi_k_val,  {}),
            ("Williams %R (14)",                    wr_val,      {}),
            ("Bull Bear Power",                     bbp_val,     {}),
            ("Ultimate Oscillator (7, 14, 28)",     uo_val,      {}),
        ]
        osc_rows = [{"name": n, "value": v, "action": _osc_signal(n, v, **kw)} for n, v, kw in oscillators]
        osc_buy     = sum(1 for r in osc_rows if r["action"] == "BUY")
        osc_sell    = sum(1 for r in osc_rows if r["action"] == "SELL")
        osc_neutral = sum(1 for r in osc_rows if r["action"] == "NEUTRAL")

        # ── Moving Averages ────────────────────────────────────────────────
        def _ema(n): return _last(EMAIndicator(close, window=n).ema_indicator())
        def _sma(n): return _last(SMAIndicator(close, window=n).sma_indicator())
        def _wma(n): return _last(WMAIndicator(close, window=n).wma())
        def _hma(n):
            half = max(2, n // 2)
            wma_half = WMAIndicator(close, window=half).wma()
            wma_full = WMAIndicator(close, window=n).wma()
            raw = 2 * wma_half - wma_full
            sqrt_n = max(2, round(n ** 0.5))
            return _last(WMAIndicator(raw, window=sqrt_n).wma())
        def _ichimoku_base():
            try:
                ich = IchimokuIndicator(high, low, window1=9, window2=26)
                return _last(ich.ichimoku_base_line())
            except Exception:
                return None
        def _vwma(n):
            try:
                num = (close * volume).rolling(window=n).sum()
                den = volume.rolling(window=n).sum()
                return _last(num / den)
            except Exception:
                return None

        close_last = _safe_float(close.iloc[-1]) if len(close) > 0 else None

        def _ma_signal(ma_val):
            if ma_val is None or close_last is None: return "NEUTRAL"
            if close_last > ma_val: return "BUY"
            if close_last < ma_val: return "SELL"
            return "NEUTRAL"

        ma_list = [
            ("EMA (10)",  _ema(10)), ("SMA (10)",  _sma(10)),
            ("EMA (20)",  _ema(20)), ("SMA (20)",  _sma(20)),
            ("EMA (30)",  _ema(30)), ("SMA (30)",  _sma(30)),
            ("EMA (50)",  _ema(50)), ("SMA (50)",  _sma(50)),
            ("EMA (100)", _ema(100)),("SMA (100)", _sma(100)),
            ("EMA (200)", _ema(200)),("SMA (200)", _sma(200)),
            ("Ichimoku Base Line (9, 26, 52, 26)", _ichimoku_base()),
            ("VWMA (20)", _vwma(20)),
            ("HMA (9)",   _hma(9)),
        ]
        ma_rows = [{"name": n, "value": v, "action": _ma_signal(v)} for n, v in ma_list]
        ma_buy     = sum(1 for r in ma_rows if r["action"] == "BUY")
        ma_sell    = sum(1 for r in ma_rows if r["action"] == "SELL")
        ma_neutral = sum(1 for r in ma_rows if r["action"] == "NEUTRAL")

        # ── Pivots (based on previous SEALED candle) ───────────────────────
        # Pick the most recent SEALED daily bar:
        #   • Market OPEN/PRE_OPEN: iloc[-1] is today's unsealed intraday
        #     candle — step back to iloc[-2].
        #   • Market CLOSED + eod_sealed: iloc[-1] IS today's sealed close,
        #     use it directly.
        #   • Market CLOSED + NOT eod_sealed (rare — intraday cache before
        #     today's EOD lands): iloc[-1] is still unsealed, step back.
        # Previously we always took iloc[-2], which silently turned
        # "yesterday's pivots" into "two-days-ago's pivots" every EOD.
        last_is_unsealed = (market_state in ("OPEN", "PRE_OPEN")) or (not eod_sealed)
        if last_is_unsealed and len(df) >= 2:
            prev = df.iloc[-2]
        elif len(df) >= 1:
            prev = df.iloc[-1]
        else:
            return JSONResponse(status_code=404,
                content={"error": f"No price history for {symbol_upper}"})
        H, L, C = float(prev["High"]), float(prev["Low"]), float(prev["Close"])
        O_prev = float(prev["Open"])

        def _r(v): return _safe_float(v)

        p_c = (H + L + C) / 3
        classic = {
            "r3": _r(H + 2 * (p_c - L)), "r2": _r(p_c + (H - L)), "r1": _r(2 * p_c - L),
            "p":  _r(p_c),
            "s1": _r(2 * p_c - H), "s2": _r(p_c - (H - L)), "s3": _r(L - 2 * (H - p_c)),
        }
        rng = H - L
        p_f = p_c
        fibonacci = {
            "r3": _r(p_f + 1.0   * rng), "r2": _r(p_f + 0.618 * rng), "r1": _r(p_f + 0.382 * rng),
            "p":  _r(p_f),
            "s1": _r(p_f - 0.382 * rng), "s2": _r(p_f - 0.618 * rng), "s3": _r(p_f - 1.0 * rng),
        }
        camarilla = {
            "r3": _r(C + 1.25 * rng), "r2": _r(C + 1.1666 * rng), "r1": _r(C + 1.0833 * rng),
            "p":  _r(p_c),
            "s1": _r(C - 1.0833 * rng), "s2": _r(C - 1.1666 * rng), "s3": _r(C - 1.25 * rng),
        }
        p_w = (H + L + 2 * C) / 4
        woodie = {
            "r3": _r(H + 2 * (p_w - L)), "r2": _r(p_w + H - L), "r1": _r(2 * p_w - L),
            "p":  _r(p_w),
            "s1": _r(2 * p_w - H), "s2": _r(p_w - H + L), "s3": _r(L - 2 * (H - p_w)),
        }
        if   C > O_prev: X = 2 * H + L + C
        elif C < O_prev: X = H + 2 * L + C
        else:            X = H + L + 2 * C
        dm = {"r1": _r(X / 2 - L), "p": _r(X / 4), "s1": _r(X / 2 - H)}

        tot_buy     = osc_buy + ma_buy
        tot_sell    = osc_sell + ma_sell
        tot_neutral = osc_neutral + ma_neutral

        return {
            "oscillators":    {"signal": _signal_score(osc_buy, osc_sell, osc_neutral),
                                "buy": osc_buy, "sell": osc_sell, "neutral": osc_neutral,
                                "indicators": osc_rows},
            "movingAverages": {"signal": _signal_score(ma_buy, ma_sell, ma_neutral),
                                "buy": ma_buy, "sell": ma_sell, "neutral": ma_neutral,
                                "indicators": ma_rows},
            "pivots": {"classic": classic, "fibonacci": fibonacci, "camarilla": camarilla,
                       "woodie": woodie, "dm": dm},
            "summary": {"signal": _signal_score(tot_buy, tot_sell, tot_neutral),
                        "buy": tot_buy, "sell": tot_sell, "neutral": tot_neutral},
        }

    # ── Fetch the price feed (always via PriceService) ───────────────────────
    df = None
    source = "NSE"
    eod_sealed = False
    eod_date = None
    as_of = None

    if interval == "1d":
        df = await svc.price.get_history_dataframe(symbol_upper, days=730)
        meta = _disk.load_with_meta(symbol_upper, 730) or _disk.load_with_meta(symbol_upper, 300) or {}
        source     = meta.get("source") or "NSE"
        eod_sealed = bool(meta.get("eodSealed"))
        eod_date   = meta.get("eodDate")
        as_of      = meta.get("savedAt")

    if df is None or df.empty:
        # Sub-daily / weekly / monthly → Yahoo intraday (NSE only exposes EOD).
        chart = await svc.price.get_intraday_history(symbol_upper, period=period, interval=yf_interval)
        rows = chart.get("candles") or []
        if rows:
            # Reconstruct a DataFrame the indicator library can consume
            df = pd.DataFrame({
                "Open":   [r["open"]   for r in rows],
                "High":   [r["high"]   for r in rows],
                "Low":    [r["low"]    for r in rows],
                "Close":  [r["close"]  for r in rows],
                "Volume": [r.get("volume", 0) for r in rows],
            }, index=pd.to_datetime([r["time"] for r in rows], unit="s"))
            source     = chart.get("source") or "YAHOO"
            eod_sealed = bool(chart.get("eodSealed"))
            eod_date   = chart.get("eodDate")
            as_of      = chart.get("asOf") or _disk._now_ist().isoformat()
        elif interval in ("1w", "1mo"):
            # Yahoo had no weekly/monthly bars — common for recently-listed
            # names (e.g. ENRIN) whose monthly feed Yahoo hasn't built yet.
            # Resample from the daily disk series instead: the same reliable
            # source the 1D view uses, so the tab works for any symbol we hold
            # daily bars for.
            daily = await svc.price.get_history_dataframe(symbol_upper, days=3660)
            if daily is not None and not daily.empty:
                rule = "W" if interval == "1w" else "ME"
                df = daily.resample(rule).agg({
                    "Open": "first", "High": "max", "Low": "min",
                    "Close": "last", "Volume": "sum",
                }).dropna()
                meta = _disk.load_with_meta(symbol_upper, 3660) or _disk.load_with_meta(symbol_upper, 300) or {}
                source     = meta.get("source") or "NSE"
                eod_sealed = bool(meta.get("eodSealed"))
                eod_date   = meta.get("eodDate")
                as_of      = meta.get("savedAt")

    if df is None or df.empty:
        return JSONResponse(
            status_code=404,
            content={"error": f"No price data for {symbol_upper} (interval={interval})"},
        )

    # Graceful degradation: a recently-listed name on a long timeframe has only
    # a handful of bars, which can yield mostly-empty indicators (or, rarely, a
    # library error). Return a valid NEUTRAL structure rather than failing the
    # whole tab — the UI then renders an empty summary instead of an error.
    try:
        result = await asyncio.to_thread(_compute, df)
        if not isinstance(result, dict):
            raise ValueError("compute did not return a result dict")
    except Exception as e:
        import logging as _lg
        _lg.getLogger(__name__).warning(
            "technical-summary compute failed for %s (interval=%s, bars=%d): %s",
            symbol_upper, interval, len(df), e,
        )
        _neutral = {"signal": "NEUTRAL", "buy": 0, "sell": 0, "neutral": 0, "indicators": []}
        result = {
            "oscillators":    dict(_neutral),
            "movingAverages": dict(_neutral),
            "pivots": {"classic": {}, "fibonacci": {}, "camarilla": {}, "woodie": {}, "dm": {}},
            "summary": {"signal": "NEUTRAL", "buy": 0, "sell": 0, "neutral": 0},
        }

    return {
        "symbol":   symbol_upper,
        "interval": interval,
        **result,
        "meta": {
            "source":       source,
            "asOf":         as_of,
            "marketState":  market_state,
            "eodSealed":    eod_sealed,
            "eodDate":      eod_date,
            "cacheVersion": _disk.cache_version(),
        },
    }


@router.get("/{symbol}/tri-factor")
async def get_tri_factor_score(symbol: str):
    """
    Composite Scoring Model.
    Returns scores in [-1, +1] for Technical, Fundamental, Sentiment, and
    Ownership factors. The Ownership factor is derived from the SEBI
    shareholding XBRL (promoter pledge as a risk penalty; promoter and
    institutional FII+DII stake trends QoQ as conviction signals).
    """
    import math
    import pandas as pd
    import yfinance as yf
    from ..services import news_service

    sym = symbol.upper()

    # ── Sector P/E benchmarks (NSE-calibrated) ───────────────────────────
    SECTOR_PE: dict[str, float] = {
        "Technology":              26.0,
        "Financial Services":      18.0,
        "Consumer Cyclical":       35.0,
        "Consumer Defensive":      48.0,
        "Healthcare":              28.0,
        "Energy":                  12.0,
        "Basic Materials":         14.0,
        "Industrials":             28.0,
        "Communication Services":  20.0,
        "Real Estate":             32.0,
        "Utilities":               18.0,
    }
    DEFAULT_SECTOR_PE = 22.0

    def _sf(v):
        try:
            f = float(v)
            return None if (math.isnan(f) or math.isinf(f)) else f
        except Exception:
            return None

    # ── 1. FUNDAMENTAL SCORE ─────────────────────────────────────────────
    def _fetch_info():
        for tick_sym in yahoo_candidates(sym):
            try:
                t = yf.Ticker(tick_sym)
                info = t.info or {}
                if info.get("regularMarketPrice") or info.get("currentPrice") or info.get("marketCap"):
                    return info
            except Exception:
                continue
        return None

    info = await asyncio.to_thread(_fetch_info)

    pe: float | None = None
    sector_pe: float = DEFAULT_SECTOR_PE
    sector_name: str | None = None
    eps_growth_pct: float | None = None
    debt_to_equity: float | None = None

    if info:
        pe = _sf(info.get("trailingPE") or info.get("forwardPE"))
        sector_name = info.get("sector") or info.get("industry")
        sector_pe = SECTOR_PE.get(sector_name or "", DEFAULT_SECTOR_PE)

        eg = _sf(info.get("earningsGrowth") or info.get("revenueGrowth"))
        if eg is not None:
            eps_growth_pct = round(eg * 100, 1)

        de_raw = _sf(info.get("debtToEquity"))
        if de_raw is not None:
            debt_to_equity = round(de_raw / 100.0, 3)   # yfinance gives percent

    valuation_score = (0.5 if (pe is not None and pe < sector_pe)
                       else -0.5 if (pe is not None and pe > sector_pe)
                       else 0.0)

    # Return-on-equity fallback: use ROE ≥ 15% as proxy for "healthy" when
    # earningsGrowth is unavailable (common for Indian small/mid-caps on yfinance)
    roe: float | None = None
    if info:
        roe_raw = _sf(info.get("returnOnEquity"))
        if roe_raw is not None:
            roe = round(roe_raw * 100, 1)   # fraction → percent

    if eps_growth_pct is not None or debt_to_equity is not None:
        # Use reported EPS growth if available, else fall back to ROE proxy
        if eps_growth_pct is not None:
            eg_v = eps_growth_pct
        elif roe is not None:
            # Map ROE > 15% → +10% proxy growth; ROE < 0 → -10% proxy
            eg_v = 15.0 if roe > 15 else (-5.0 if roe < 0 else 5.0)
        else:
            eg_v = 0.0

        de_v = debt_to_equity if debt_to_equity is not None else 0.5
        health_score = (0.5  if (eg_v > 10  and de_v < 1.0)
                        else -0.5 if (eg_v < 0   or  de_v > 2.0)
                        else 0.0)
    elif roe is not None:
        # Only ROE available — use it alone as health proxy
        health_score = 0.5 if roe > 15 else (-0.5 if roe < 0 else 0.0)
    else:
        health_score = 0.0

    s_f = round(max(-1.0, min(1.0, valuation_score + health_score)), 2)

    # ── 2. TECHNICAL SCORE ───────────────────────────────────────────────
    _TECH_NULL = {
        "price": None, "ema50": None, "ema200": None, "rsi14": None,
        "trend_score": 0.0, "momentum_score": 0.0, "score": 0.0,
        "data_note": None,
    }

    def _compute_tech(df: pd.DataFrame) -> dict:
        try:
            from ta.momentum import RSIIndicator
            from ta.trend import EMAIndicator

            close = df["Close"].dropna()
            n = len(close)
            if n == 0:
                return {**_TECH_NULL, "data_note": "No price data after dropping NaNs"}

            price = _sf(close.iloc[-1])

            ema50_s  = EMAIndicator(close, window=50).ema_indicator().dropna()
            ema200_s = EMAIndicator(close, window=200).ema_indicator().dropna()
            rsi_s    = RSIIndicator(close, window=14).rsi().dropna()

            ema50  = _sf(ema50_s.iloc[-1])  if not ema50_s.empty  else None
            ema200 = _sf(ema200_s.iloc[-1]) if not ema200_s.empty else None
            rsi14  = _sf(rsi_s.iloc[-1])    if not rsi_s.empty    else None

            # Adaptive long EMA: use Option-A ratio rule (2.5× warm-up requirement).
            # An EMA of window W needs ~2.5×W bars to be well-settled;
            # using n−10 would give EMA146 from 156 bars — only 10 recursive
            # steps past the SMA seed, meaning the "EMA" is 87% SMA and 13%
            # exponential.  floor(n/2.5) guarantees ≥1.5W settling bars.
            # Cap at 200 (canonical long anchor); floor at 50 (EMA50 minimum).
            long_window = min(200, max(50, int(n / 2.5)))
            ema_long_s = EMAIndicator(close, window=long_window).ema_indicator().dropna()
            ema_long   = _sf(ema_long_s.iloc[-1]) if not ema_long_s.empty else None
            # Keep ema200 as the "canonical" slot; overwrite with adaptive value
            # when the true 200-bar EMA is unavailable.
            if ema200 is None and ema_long is not None:
                ema200 = ema_long          # used in the return dict below

            # Build a human-readable note about data completeness
            notes = []
            if long_window < 200:
                notes.append(
                    f"EMA {long_window} used as long-term anchor "
                    f"({n} bars available; EMA 200 needs 200+)"
                )
            if rsi14 is None:
                notes.append("RSI unavailable (insufficient bars)")
            data_note = "; ".join(notes) if notes else None

            # Trend: full ±0.5 when long EMA (≥100 days) + EMA50 both confirm;
            # partial ±0.25 when only EMA50 is available (< 100 bars total).
            use_full_signal = (
                price is not None and ema50 is not None
                and ema_long is not None and long_window >= 100
            )
            use_partial_signal = (
                not use_full_signal
                and price is not None and ema50 is not None
            )

            if use_full_signal:
                if price > ema50 > ema_long:
                    trend = 0.5
                elif price < ema50 < ema_long:
                    trend = -0.5
                else:
                    trend = 0.0
            elif use_partial_signal:
                trend = 0.25 if price > ema50 else (-0.25 if price < ema50 else 0.0)
            else:
                trend = 0.0

            # Momentum: proportional RSI — linear from 0 at RSI=50 to ±0.5 at 30/70
            # RSI 66.9 → -0.5 × (66.9-50)/20 ≈ -0.42 instead of 0.0 at the hard cliff
            if rsi14 is not None:
                momentum = round(max(-0.5, min(0.5, -0.5 * (rsi14 - 50) / 20)), 3)
            else:
                momentum = 0.0

            def _r2(v: float | None) -> float | None:
                return round(v, 2) if v is not None else None

            return {
                "price":          _r2(price),
                "ema50":          _r2(ema50),
                "ema200":         _r2(ema200),   # adaptive: may be EMA<200
                "ema_long_window": long_window,  # actual window used (50–200)
                "rsi14":          _r2(rsi14),
                "trend_score":    trend,
                "momentum_score": momentum,
                "score":          round(max(-1.0, min(1.0, trend + momentum)), 2),
                "bars":           n,
                "data_note":      data_note,
            }
        except Exception as exc:
            return {**_TECH_NULL, "data_note": f"Computation error: {exc}"}

    df = await svc.price.get_history_dataframe(sym, days=600)

    # The service chain (NSE blocked → BSE ~60–500 bars → Yahoo) often
    # returns fewer bars than a settled EMA200 requires.
    # By the 2.5× warm-up rule, EMA200 needs 200×2.5 = 500 bars.
    # If the chain returns < 500 bars, fall back to yfinance 3y directly.
    if df is None or df.empty or len(df) < 500:
        def _yf_fetch(ticker: str) -> "pd.DataFrame":
            import yfinance as _yf
            import pandas as pd
            yf_sym = ticker if "." in ticker else f"{ticker}.NS"
            hist = _yf.Ticker(yf_sym).history(period="3y", interval="1d", auto_adjust=True)
            if hist.empty and yf_sym.endswith(".NS"):
                hist = _yf.Ticker(ticker).history(period="3y", interval="1d", auto_adjust=True)
            return hist[["Open", "High", "Low", "Close", "Volume"]] if not hist.empty else pd.DataFrame()

        df_yf = await asyncio.to_thread(_yf_fetch, sym)
        if not df_yf.empty and len(df_yf) > (len(df) if df is not None else 0):
            df = df_yf

    if df is not None and not df.empty and len(df) >= 15:
        tech = await asyncio.to_thread(_compute_tech, df)
    else:
        bars = len(df) if df is not None else 0
        tech = {**_TECH_NULL, "data_note": f"Insufficient price history ({bars} bars)"}
    s_t = tech["score"]

    # ── 3. SENTIMENT SCORE ───────────────────────────────────────────────
    news_data = await news_service.get_ticker_news(sym, limit=30)
    articles  = news_data.get("articles", [])

    pos   = sum(1 for a in articles if a.get("sentiment") == "bullish")
    neg   = sum(1 for a in articles if a.get("sentiment") == "bearish")
    neu   = sum(1 for a in articles if a.get("sentiment") == "neutral")
    total = pos + neg + neu

    s_s = round(max(-1.0, min(1.0, (pos - neg) / total)), 3) if total > 0 else 0.0

    headlines = [
        {"title": a.get("title", ""), "sentiment": a.get("sentiment", "neutral")}
        for a in articles[:8]
        if a.get("title")
    ]

    # ── 4. OWNERSHIP SCORE ───────────────────────────────────────────────
    # Conviction / risk signal mined from the SEBI shareholding XBRL we
    # already parse (no new fetch infra). Three components, summed & clamped:
    #   (a) promoter pledge — a pure risk penalty (rising pledge = distress);
    #   (b) promoter stake trend QoQ — promoters adding = skin in the game;
    #   (c) institutional (FII+DII) stake trend QoQ — smart-money accumulation.
    from ..services.shareholding_service import get_shareholding as _get_shp  # noqa: PLC0415

    own_factor: dict = {
        "promoter_pct": None, "promoter_pledge_pct": None,
        "promoter_change": None, "institutional_change": None,
        "fii_pct": None, "dii_pct": None,
        "pledge_score": 0.0, "promoter_trend_score": 0.0, "institutional_trend_score": 0.0,
        "as_on": None, "data_note": None,
    }
    s_o = 0.0
    try:
        shp = await _get_shp(sym, quarters=8)
        rows = shp.get("rows") or []          # newest quarter first
        if not rows:
            own_factor["data_note"] = "No shareholding data available"
        else:
            latest = rows[0]
            own_factor["as_on"]               = latest.get("asOnDate")
            own_factor["promoter_pct"]        = latest.get("promoterPct")
            own_factor["fii_pct"]             = latest.get("fiiPct")
            own_factor["dii_pct"]             = latest.get("diiPct")
            pledge = latest.get("promoterPledgePct")
            own_factor["promoter_pledge_pct"] = pledge

            # (a) pledge penalty — only ever negative; pledge is a red flag.
            pledge_score = 0.0
            if pledge is not None and pledge > 0:
                if   pledge > 50: pledge_score = -0.6
                elif pledge > 25: pledge_score = -0.45
                elif pledge > 10: pledge_score = -0.30
                else:             pledge_score = -0.15
            own_factor["pledge_score"] = pledge_score

            def _trend(delta: float) -> float:
                if delta >=  0.5: return  0.25
                if delta >  0.0:  return  0.10
                if delta <= -0.5: return -0.25
                if delta <  0.0:  return -0.10
                return 0.0

            # (b) promoter stake trend vs the most recent prior quarter.
            prom_trend = 0.0
            if latest.get("promoterPct") is not None:
                prev = next((r for r in rows[1:] if r.get("promoterPct") is not None), None)
                if prev is not None:
                    d = latest["promoterPct"] - prev["promoterPct"]
                    own_factor["promoter_change"] = round(d, 2)
                    prom_trend = _trend(d)
            own_factor["promoter_trend_score"] = prom_trend

            # (c) institutional (FII+DII) stake trend.
            def _inst(r: dict):
                f, dd = r.get("fiiPct"), r.get("diiPct")
                if f is None and dd is None:
                    return None
                return (f or 0.0) + (dd or 0.0)

            inst_trend = 0.0
            latest_inst = _inst(latest)
            if latest_inst is not None:
                prev_inst = next((pi for pi in (_inst(r) for r in rows[1:]) if pi is not None), None)
                if prev_inst is not None:
                    d = latest_inst - prev_inst
                    own_factor["institutional_change"] = round(d, 2)
                    inst_trend = _trend(d)
            own_factor["institutional_trend_score"] = inst_trend

            s_o = round(max(-1.0, min(1.0, pledge_score + prom_trend + inst_trend)), 2)
    except Exception as exc:
        own_factor["data_note"] = f"Ownership computation error: {exc}"

    return {
        "symbol": sym,
        "scores": {
            "technical":   s_t,
            "fundamental": s_f,
            "sentiment":   s_s,
            "ownership":   s_o,
        },
        "factors": {
            "technical": tech,
            "fundamental": {
                "pe":              round(pe,  1) if pe  else None,
                "sector_pe":       sector_pe,
                "sector":          sector_name,
                "eps_growth_pct":  eps_growth_pct,
                "debt_to_equity":  debt_to_equity,
                "valuation_score": valuation_score,
                "health_score":    health_score,
            },
            "sentiment": {
                "bullish":   pos,
                "bearish":   neg,
                "neutral":   neu,
                "total":     total,
                "headlines": headlines,
            },
            "ownership": own_factor,
        },
    }


@router.get("/{symbol}/shareholding")
async def get_shareholding(
    symbol: str,
    view:   str = Query("quarterly", pattern="^(quarterly|yearly)$"),
    quarters: int = Query(32, ge=1, le=40),
    force:  bool = Query(False),
):
    """Quarterly shareholding-pattern history (Promoter / FII / DII /
    Public %) for the requested symbol. Data merged from NSE, BSE,
    Yahoo and (last-resort) Screener.in, cached in PG.

    Query params:
      view      `quarterly` (default) or `yearly` (only March quarters).
      quarters  Max rows to return (1..40). Default 16 = 4 years.
      force     Skip the staleness check and force a refresh fetch.
                Helpful for the "Refresh" button on the UI.
    """
    from ..services.shareholding_service import get_shareholding as _svc  # noqa: PLC0415
    data = await _svc(symbol, view=view, quarters=quarters, force=force)
    return data


@router.get("/{symbol}/quarterly-results")
async def get_quarterly_results(
    symbol: str,
    basis:    str  = Query("consolidated", pattern="^(consolidated|standalone)$"),
    quarters: int  = Query(12, ge=1, le=24),
    force:    bool = Query(False),
):
    """Quarterly financial results parsed from the SEBI Reg-33 (in-bse-fin)
    XBRL filing — the full P&L that Yahoo collapses: revenue, the complete
    expense breakdown, current/deferred tax, PAT, basic + diluted EPS, and
    segment results, for the standalone or consolidated basis.

    Query params:
      basis     `consolidated` (default) or `standalone`. Falls back to
                whichever basis the company actually files.
      quarters  Max quarters to return (1..24). Default 12 = 3 years.
      force     Skip the staleness check and force a refresh fetch.
    """
    from ..services.financial_results_service import get_financial_results as _svc  # noqa: PLC0415
    return await _svc(symbol, basis=basis, quarters=quarters, force=force)


@router.get("/{symbol}/profile")
async def get_stock_profile(symbol: str):
    """Company business profile — what the company does (description) and its
    canonical sector / industry. Sector is resolved through the centralised
    classifier (sector_utils) and persisted for future lookups.
    """
    from ..services import stock_profile_service
    return await stock_profile_service.get_profile(symbol)


@router.get("/{symbol}/quote")
async def get_stock_quote_lite(symbol: str):
    """Lightweight single-symbol quote for the chart-studio detail panel:
    price, %change, OHLC, prev close and volume — WITHOUT the 500-day history
    fetch + technical-analysis stack that `/stocks/{symbol}` runs (the detail
    panel discards those). Closed market: served straight from the sealed EOD
    bars on disk — zero network, no doomed NSE call. 52-week range and
    fundamentals come from the separate `/key-stats` call so the slow yfinance
    lookup never blocks the price. Falls back to a live quote (no divergence
    cross-check) when the symbol isn't sealed yet."""
    sym = symbol.upper()

    if not _disk.is_market_open():
        payload = _disk.load_with_meta(sym, 5)
        if payload and payload.get("eodSealed") and payload.get("data"):
            bars = payload["data"]
            if len(bars) >= 2 and bars[-1].get("close") is not None:
                from ..lib.universe import COMPANY_MAP  # noqa: PLC0415
                last, prev = bars[-1], bars[-2]
                lc = round(float(last["close"]), 2)
                pc = round(float(prev["close"]), 2) if prev.get("close") is not None else None
                return {
                    "symbol":        sym,
                    "companyName":   COMPANY_MAP.get(sym) or sym,
                    "lastPrice":     lc,
                    "previousClose": pc,
                    "pChange":       (round((lc - pc) / pc * 100, 2) if pc else None),
                    "open":          round(float(last["open"]), 2) if last.get("open")   is not None else None,
                    "dayHigh":       round(float(last["high"]), 2) if last.get("high")   is not None else None,
                    "dayLow":        round(float(last["low"]), 2)  if last.get("low")    is not None else None,
                    "volume":        int(last["volume"])           if last.get("volume") is not None else None,
                    "servedFrom":    "DISK_EOD",
                }

    # Open market, or no sealed snapshot yet → live quote (no divergence call).
    snap = await svc.price.get_quote_with_meta(sym, cross_check=False)
    if not snap:
        return JSONResponse(status_code=404, content={"error": f"Stock {sym} not found"})
    q = snap["quote"]
    return {
        "symbol":           sym,
        "companyName":      q.get("companyName") or sym,
        "lastPrice":        q.get("lastPrice"),
        "pChange":          q.get("pChange"),
        "open":             q.get("open"),
        "dayHigh":          q.get("dayHigh"),
        "dayLow":           q.get("dayLow"),
        "previousClose":    q.get("previousClose"),
        "volume":           q.get("volume"),
        "fiftyTwoWeekHigh": q.get("fiftyTwoWeekHigh"),
        "fiftyTwoWeekLow":  q.get("fiftyTwoWeekLow"),
        "marketCap":        q.get("marketCap"),
        "servedFrom":       snap.get("servedFrom"),
    }


@router.get("/{symbol}/key-stats")
async def get_stock_key_stats(symbol: str):
    """marketCap / trailing P/E / dividend yield / 52-week range from cached
    yfinance `.info`. Separate from the quote so this (often slow, 2-10s)
    lookup fills in progressively and never blocks the price display."""
    stats = await svc.stocks.get_key_stats(symbol.upper())
    return {
        "marketCap":        stats.get("marketCap"),
        "trailingPE":       stats.get("trailingPE"),
        "dividendYield":    stats.get("dividendYield"),
        "fiftyTwoWeekHigh": stats.get("fiftyTwoWeekHigh"),
        "fiftyTwoWeekLow":  stats.get("fiftyTwoWeekLow"),
    }


@router.get("/{symbol}")
async def get_stock(symbol: str):
    data = await svc.stocks.get_stock_details(symbol)
    if data.get("error"):
        return JSONResponse(status_code=404, content={"error": data["error"]})
    return data
