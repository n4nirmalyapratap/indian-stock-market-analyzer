import asyncio
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from ..services.stocks_service import StocksService
from ..services.nse_service import NseService
from ..services.yahoo_service import YahooService
from ..services.price_service import PriceService
from ..services import market_cache_service as _disk
from ..lib.symbol_map import SYMBOL_MAP, to_yahoo_ticker, yahoo_candidates  # noqa: F401  (re-export for callers)

router = APIRouter(prefix="/stocks", tags=["stocks"])

_nse = NseService()
_yahoo = YahooService()
_price = PriceService(_nse, _yahoo)
_service = StocksService(_nse, _yahoo)

VALID_PERIODS   = {"1d","5d","1mo","3mo","6mo","1y","2y","5y","10y","max"}
VALID_INTERVALS = {"1m","2m","5m","15m","30m","60m","90m","1h","1d","5d","1wk","1mo"}


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
    return await _service.get_nifty100_stocks()


@router.get("/midcap")
async def get_midcap():
    return await _service.get_midcap_stocks()


@router.get("/smallcap")
async def get_smallcap():
    return await _service.get_smallcap_stocks()


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
        chart = await _price.get_range_history(symbol, start=start, end=end, interval=interval)
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
    chart = await _price.get_intraday_history(symbol, period=period, interval=interval)
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

    annual_income    = _df_to_list(fs,  INCOME_MAP)
    quarterly_income = _df_to_list(qfs, INCOME_MAP)
    annual_bs        = _df_to_list(bs,  BS_MAP)
    annual_cf        = _df_to_list(cf,  CF_MAP)

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

    return {
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
        df = await _price.get_history_dataframe(symbol_upper, days=730)
        meta = _disk.load_with_meta(symbol_upper, 730) or _disk.load_with_meta(symbol_upper, 300) or {}
        source     = meta.get("source") or "NSE"
        eod_sealed = bool(meta.get("eodSealed"))
        eod_date   = meta.get("eodDate")
        as_of      = meta.get("savedAt")

    if df is None or df.empty:
        # Sub-daily, or NSE empty → PriceService (Yahoo intraday under the hood)
        chart = await _price.get_intraday_history(symbol_upper, period=period, interval=yf_interval)
        if not chart.get("candles"):
            return JSONResponse(
                status_code=404,
                content={"error": f"No price data for {symbol_upper} (interval={interval})"},
            )
        # Reconstruct a DataFrame the indicator library can consume
        rows = chart["candles"]
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

    try:
        result = await asyncio.to_thread(_compute, df)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Could not compute technical summary: {e}"})

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


@router.get("/{symbol}")
async def get_stock(symbol: str):
    data = await _service.get_stock_details(symbol)
    if data.get("error"):
        return JSONResponse(status_code=404, content={"error": data["error"]})
    return data
