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

    info, hist = await asyncio.to_thread(_fetch)

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


@router.get("/{symbol}/financials")
async def get_stock_financials(symbol: str):
    """
    Return TradingView-style financial data for a stock:
    overview metrics, income statement (annual + quarterly),
    balance sheet, cash flow, dividends, and EPS history.
    All monetary values are in ₹ Crores (1 Crore = 1e7).
    """
    import math
    import pandas as pd
    import yfinance as yf

    symbol = symbol.upper()

    def _safe(val):
        """Return None for NaN/inf, else the value."""
        try:
            if val is None:
                return None
            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                return None
            return val
        except Exception:
            return None

    def _cr(val):
        """Convert raw rupee value → ₹ Crores, rounded to 2 dp."""
        v = _safe(val)
        if v is None:
            return None
        return round(float(v) / 1e7, 2)

    def _pct(val):
        """Convert 0-1 fraction → percentage rounded to 2 dp."""
        v = _safe(val)
        if v is None:
            return None
        return round(float(v) * 100, 2)

    def _f(val, decimals=2):
        v = _safe(val)
        if v is None:
            return None
        return round(float(v), decimals)

    def _row(df, key):
        """Safe lookup of a row from a DataFrame; returns None if missing."""
        try:
            if df is None or df.empty or key not in df.index:
                return None
            return df.loc[key]
        except Exception:
            return None

    def _df_to_list(df, row_map: dict, sort_asc=True):
        """
        Convert a transposed financial DataFrame into a list of dicts.

        df       : DataFrame where rows=metrics, cols=dates
        row_map  : {output_key: (df_row_name, transform_fn)}
        sort_asc : sort by date ascending (oldest first)
        """
        if df is None or df.empty:
            return []
        results = []
        for col in df.columns:
            entry = {"date": str(col.date())}
            for out_key, (row_name, fn) in row_map.items():
                try:
                    val = df.loc[row_name, col] if row_name in df.index else None
                    entry[out_key] = fn(val)
                except Exception:
                    entry[out_key] = None
            results.append(entry)
        if sort_asc:
            results.sort(key=lambda x: x["date"])
        return results

    def _fetch():
        candidates = [f"{symbol}.NS", symbol]

        for tick_sym in candidates:
            try:
                t = yf.Ticker(tick_sym)
                info = t.info or {}
                if not (info.get("regularMarketPrice") or info.get("currentPrice")
                        or info.get("marketCap")):
                    continue

                return {
                    "info": info,
                    "financials": t.financials,
                    "q_financials": t.quarterly_financials,
                    "balance_sheet": t.balance_sheet,
                    "cash_flow": t.cash_flow,
                    "dividends": t.dividends,
                }
            except Exception:
                continue
        return None

    raw = await asyncio.to_thread(_fetch)
    if raw is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"No financial data found for {symbol}. "
                               "Check the NSE symbol is correct."},
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

    eps_annual = []
    for row in _df_to_list(fs, {"eps": ("Diluted EPS", _f)}):
        if row["eps"] is not None:
            eps_annual.append(row)

    eps_quarterly = []
    for row in _df_to_list(qfs, {"eps": ("Diluted EPS", _f)}):
        if row["eps"] is not None:
            eps_quarterly.append(row)

    div_list = []
    if divs is not None and len(divs) > 0:
        for dt, amount in divs.items():
            v = _safe(amount)
            if v is not None:
                date_str = str(pd.Timestamp(dt).date())
                div_list.append({"date": date_str, "amount": round(float(v), 2)})
        div_list.sort(key=lambda x: x["date"])

    ov = info
    overview = {
        "marketCap":      _safe(ov.get("marketCap")),
        "trailingPE":     _f(ov.get("trailingPE")),
        "forwardPE":      _f(ov.get("forwardPE")),
        "priceToBook":    _f(ov.get("priceToBook")),
        "priceToSales":   _f(ov.get("priceToSalesTrailing12Months")),
        "evToEbitda":     _f(ov.get("enterpriseToEbitda")),
        "trailingEps":    _f(ov.get("trailingEps")),
        "forwardEps":     _f(ov.get("forwardEps")),
        "roe":            _pct(ov.get("returnOnEquity")),
        "roa":            _pct(ov.get("returnOnAssets")),
        "debtToEquity":   _f(ov.get("debtToEquity")),
        "currentRatio":   _f(ov.get("currentRatio")),
        "grossMargin":    _pct(ov.get("grossMargins")),
        "operatingMargin": _pct(ov.get("operatingMargins")),
        "netMargin":      _pct(ov.get("profitMargins")),
        "dividendYield":  _f(ov.get("dividendYield")),
        "dividendRate":   _f(ov.get("dividendRate")),
        "earningsGrowth": _pct(ov.get("earningsGrowth")),
        "revenueGrowth":  _pct(ov.get("revenueGrowth")),
        "bookValue":      _f(ov.get("bookValue")),
        "weekChange52":   _pct(ov.get("52WeekChange")),
    }

    return {
        "symbol":      symbol,
        "companyName": info.get("longName") or info.get("shortName") or symbol,
        "currency":    info.get("currency", "INR"),
        "overview":    overview,
        "incomeStatement": {
            "annual":    annual_income,
            "quarterly": quarterly_income,
        },
        "balanceSheet": {
            "annual": annual_bs,
        },
        "cashFlow": {
            "annual": annual_cf,
        },
        "dividends": div_list,
        "eps": {
            "annual":    eps_annual,
            "quarterly": eps_quarterly,
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
    """
    import math
    import pandas as pd
    import numpy as np
    import yfinance as yf

    # Map frontend interval → yfinance (period, interval) pairs
    INTERVAL_MAP = {
        "1m":  ("7d",  "1m"),
        "5m":  ("60d", "5m"),
        "15m": ("60d", "15m"),
        "30m": ("60d", "30m"),
        "1h":  ("60d", "60m"),
        "2h":  ("60d", "60m"),   # resample to 2h not implemented – use 1h
        "4h":  ("60d", "60m"),
        "1d":  ("2y",  "1d"),
        "1w":  ("10y", "1wk"),
        "1mo": ("10y", "1mo"),
    }
    period, yf_interval = INTERVAL_MAP.get(interval, ("2y", "1d"))

    symbol_upper = symbol.upper()
    ns_suffix = "" if symbol_upper.startswith("^") else ".NS"
    yf_symbol = symbol_upper if symbol_upper.startswith("^") else f"{symbol_upper}{ns_suffix}"

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
        if score >= 0.5:
            return "STRONG_BUY"
        if score > 0.1:
            return "BUY"
        if score <= -0.5:
            return "STRONG_SELL"
        if score < -0.1:
            return "SELL"
        return "NEUTRAL"

    def _compute(df: pd.DataFrame) -> dict:
        from ta.momentum import (
            RSIIndicator, StochasticOscillator, AwesomeOscillatorIndicator,
            WilliamsRIndicator, UltimateOscillator, StochRSIIndicator, ROCIndicator,
        )
        from ta.trend import (
            CCIIndicator, ADXIndicator, MACD, EMAIndicator, SMAIndicator,
            WMAIndicator, IchimokuIndicator,
        )

        close  = df["Close"]
        high   = df["High"]
        low    = df["Low"]
        volume = df["Volume"]
        open_  = df["Open"]

        # ── Oscillators ──────────────────────────────────────────────────────

        rsi_val      = _last(RSIIndicator(close, window=14).rsi())
        stoch        = StochasticOscillator(high, low, close, window=14, smooth_window=3)
        stoch_k_val  = _last(stoch.stoch_signal())   # slow %K
        cci_val      = _last(CCIIndicator(high, low, close, window=20).cci())
        adx_ind      = ADXIndicator(high, low, close, window=14)
        adx_val      = _last(adx_ind.adx())
        adx_pos      = _last(adx_ind.adx_pos())
        adx_neg      = _last(adx_ind.adx_neg())
        ao_val       = _last(AwesomeOscillatorIndicator(high, low).awesome_oscillator())

        # Momentum(10) = close - close[10] (TradingView definition, not ROC%)
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

        # Bull Bear Power = EMA(13) - based:
        # Bulls: High - EMA(13); Bears: Low - EMA(13); BBP = Bulls + Bears = (High+Low) - 2*EMA(13)
        ema13_val    = _last(EMAIndicator(close, window=13).ema_indicator())
        close_last   = _safe_float(close.iloc[-1]) if len(close) > 0 else None
        bbp_val      = (_safe_float(close.iloc[-1]) - ema13_val) if (close_last and ema13_val) else None

        # Signal rules for oscillators
        def _osc_signal(name: str, val, **kwargs) -> str:
            if val is None:
                return "NEUTRAL"
            if name == "RSI (14)":
                return "BUY" if val < 30 else ("SELL" if val > 70 else "NEUTRAL")
            if name == "Stochastic %K (14, 3, 3)":
                return "BUY" if val < 20 else ("SELL" if val > 80 else "NEUTRAL")
            if name == "CCI (20)":
                return "BUY" if val < -100 else ("SELL" if val > 100 else "NEUTRAL")
            if name == "ADX (14)":
                adx_pos_v = kwargs.get("adx_pos")
                adx_neg_v = kwargs.get("adx_neg")
                if val > 20 and adx_pos_v and adx_neg_v:
                    return "BUY" if adx_pos_v > adx_neg_v else "SELL"
                return "NEUTRAL"
            if name == "Awesome Oscillator":
                return "BUY" if val > 0 else ("SELL" if val < 0 else "NEUTRAL")
            if name == "Momentum (10)":
                return "BUY" if val > 0 else ("SELL" if val < 0 else "NEUTRAL")
            if name == "MACD Level (12, 26)":
                sig = kwargs.get("macd_signal")
                if sig is None:
                    return "NEUTRAL"
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
            ("RSI (14)",                         rsi_val,      {}),
            ("Stochastic %K (14, 3, 3)",         stoch_k_val,  {}),
            ("CCI (20)",                         cci_val,      {}),
            ("ADX (14)",                         adx_val,      {"adx_pos": adx_pos, "adx_neg": adx_neg}),
            ("Awesome Oscillator",               ao_val,       {}),
            ("Momentum (10)",                    mom_val,      {}),
            ("MACD Level (12, 26)",              macd_val,     {"macd_signal": macd_sig_val}),
            ("Stochastic RSI Fast (3, 3, 14, 14)", srsi_k_val, {}),
            ("Williams %R (14)",                 wr_val,       {}),
            ("Bull Bear Power",                  bbp_val,      {}),
            ("Ultimate Oscillator (7, 14, 28)",  uo_val,       {}),
        ]

        osc_rows = []
        for name, val, kw in oscillators:
            action = _osc_signal(name, val, **kw)
            osc_rows.append({"name": name, "value": val, "action": action})

        osc_buy     = sum(1 for r in osc_rows if r["action"] == "BUY")
        osc_sell    = sum(1 for r in osc_rows if r["action"] == "SELL")
        osc_neutral = sum(1 for r in osc_rows if r["action"] == "NEUTRAL")

        # ── Moving Averages ──────────────────────────────────────────────────

        def _ema(n):
            return _last(EMAIndicator(close, window=n).ema_indicator())

        def _sma(n):
            return _last(SMAIndicator(close, window=n).sma_indicator())

        def _wma(n):
            return _last(WMAIndicator(close, window=n).wma())

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
            if ma_val is None or close_last is None:
                return "NEUTRAL"
            if close_last > ma_val:
                return "BUY"
            if close_last < ma_val:
                return "SELL"
            return "NEUTRAL"

        ma_list = [
            ("EMA (10)",                          _ema(10)),
            ("SMA (10)",                          _sma(10)),
            ("EMA (20)",                          _ema(20)),
            ("SMA (20)",                          _sma(20)),
            ("EMA (30)",                          _ema(30)),
            ("SMA (30)",                          _sma(30)),
            ("EMA (50)",                          _ema(50)),
            ("SMA (50)",                          _sma(50)),
            ("EMA (100)",                         _ema(100)),
            ("SMA (100)",                         _sma(100)),
            ("EMA (200)",                         _ema(200)),
            ("SMA (200)",                         _sma(200)),
            ("Ichimoku Base Line (9, 26, 52, 26)", _ichimoku_base()),
            ("VWMA (20)",                         _vwma(20)),
            ("HMA (9)",                           _hma(9)),
        ]

        ma_rows = [{"name": n, "value": v, "action": _ma_signal(v)} for n, v in ma_list]
        ma_buy     = sum(1 for r in ma_rows if r["action"] == "BUY")
        ma_sell    = sum(1 for r in ma_rows if r["action"] == "SELL")
        ma_neutral = sum(1 for r in ma_rows if r["action"] == "NEUTRAL")

        # ── Pivots ───────────────────────────────────────────────────────────

        prev = df.iloc[-2] if len(df) >= 2 else df.iloc[-1]
        H, L, C = float(prev["High"]), float(prev["Low"]), float(prev["Close"])
        O_prev   = float(prev["Open"])

        def _r(v):
            return _safe_float(v)

        # Classic
        p_c   = (H + L + C) / 3
        classic = {
            "r3": _r(H + 2 * (p_c - L)),
            "r2": _r(p_c + (H - L)),
            "r1": _r(2 * p_c - L),
            "p":  _r(p_c),
            "s1": _r(2 * p_c - H),
            "s2": _r(p_c - (H - L)),
            "s3": _r(L - 2 * (H - p_c)),
        }

        # Fibonacci
        rng = H - L
        p_f  = p_c
        fibonacci = {
            "r3": _r(p_f + 1.000 * rng),
            "r2": _r(p_f + 0.618 * rng),
            "r1": _r(p_f + 0.382 * rng),
            "p":  _r(p_f),
            "s1": _r(p_f - 0.382 * rng),
            "s2": _r(p_f - 0.618 * rng),
            "s3": _r(p_f - 1.000 * rng),
        }

        # Camarilla
        camarilla = {
            "r3": _r(C + 1.2500 * rng),
            "r2": _r(C + 1.1666 * rng),
            "r1": _r(C + 1.0833 * rng),
            "p":  _r(p_c),
            "s1": _r(C - 1.0833 * rng),
            "s2": _r(C - 1.1666 * rng),
            "s3": _r(C - 1.2500 * rng),
        }

        # Woodie
        p_w = (H + L + 2 * C) / 4
        woodie = {
            "r3": _r(H + 2 * (p_w - L)),
            "r2": _r(p_w + H - L),
            "r1": _r(2 * p_w - L),
            "p":  _r(p_w),
            "s1": _r(2 * p_w - H),
            "s2": _r(p_w - H + L),
            "s3": _r(L - 2 * (H - p_w)),
        }

        # DM
        if C > O_prev:
            X = 2 * H + L + C
        elif C < O_prev:
            X = H + 2 * L + C
        else:
            X = H + L + 2 * C
        dm = {
            "r1": _r(X / 2 - L),
            "p":  _r(X / 4),
            "s1": _r(X / 2 - H),
        }

        # ── Summary ──────────────────────────────────────────────────────────

        tot_buy     = osc_buy  + ma_buy
        tot_sell    = osc_sell + ma_sell
        tot_neutral = osc_neutral + ma_neutral

        return {
            "oscillators": {
                "signal":     _signal_score(osc_buy, osc_sell, osc_neutral),
                "buy":        osc_buy,
                "sell":       osc_sell,
                "neutral":    osc_neutral,
                "indicators": osc_rows,
            },
            "movingAverages": {
                "signal":     _signal_score(ma_buy, ma_sell, ma_neutral),
                "buy":        ma_buy,
                "sell":       ma_sell,
                "neutral":    ma_neutral,
                "indicators": ma_rows,
            },
            "pivots": {
                "classic":    classic,
                "fibonacci":  fibonacci,
                "camarilla":  camarilla,
                "woodie":     woodie,
                "dm":         dm,
            },
            "summary": {
                "signal":  _signal_score(tot_buy, tot_sell, tot_neutral),
                "buy":     tot_buy,
                "sell":    tot_sell,
                "neutral": tot_neutral,
            },
        }

    try:
        result = await asyncio.to_thread(
            lambda: _compute(
                yf.Ticker(yf_symbol).history(period=period, interval=yf_interval)
            )
        )
        return {
            "symbol":   symbol_upper,
            "interval": interval,
            **result,
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Could not compute technical summary: {e}"},
        )


@router.get("/{symbol}")
async def get_stock(symbol: str):
    data = await _service.get_stock_details(symbol)
    if data.get("error"):
        return JSONResponse(status_code=404, content={"error": data["error"]})
    return data
