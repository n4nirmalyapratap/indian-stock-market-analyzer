"""
Hydra-Alpha Engine — Supervisor / Orchestration Layer
Natural language query router that dispatches to expert agents:
  → Pairs Trader, Forecaster, VaR Calculator, Backtest Engine, Sentiment Analyzer
"""
from __future__ import annotations
import asyncio
import logging
import re
from typing import Any

from . import hydra_db_service as db
from . import hydra_sentiment_service as sentiment
from . import hydra_pairs_service as pairs
from . import hydra_backtest_service as backtest
from . import hydra_var_service as var_svc
from . import hydra_forecast_service as forecast
from ..lib.universe import ALL_SYMBOLS

logger = logging.getLogger(__name__)

# ── Words that look like NSE tickers but are not ───────────────────────────────
_SYMBOL_STOPWORDS = {
    # Action / command words
    "BACKTEST", "PAIR", "PAIRS", "FORECAST", "PREDICT", "ANALYZE", "ANALYSE",
    "ANALYSIS", "SENTIMENT", "SIGNAL", "SCAN", "FIND", "RISK", "VAR", "WHAT",
    "THE", "AND", "FOR", "WITH", "GIVE", "SHOW", "TELL", "WILL", "IS", "ARE",
    "OF", "IN", "AT", "TO", "ON", "BY", "AS", "LAST", "NEXT", "GET", "RUN",
    "DAY", "DAYS", "WEEK", "WEEKS", "MONTH", "MONTHS", "YEAR", "CALCULATE",
    "SIMULATE", "HISTORICAL", "HISTORY", "PORTFOLIO", "STOCK", "STOCKS", "NSE",
    "NIFTY", "INDEX", "BETWEEN", "VS", "OR", "NOT", "ALL", "MY", "ME", "DO",
    # Common English words that look like 2-10 uppercase letters
    "PROCEED", "CONTINUE", "START", "STOP", "HELP", "PLEASE", "YES", "NO",
    "OK", "OKAY", "SURE", "THANKS", "THANK", "HI", "HELLO", "HEY",
    "HOW", "MUCH", "WHEN", "WHERE", "WHO", "WHY", "ANY", "ABOUT", "CAN",
    "COULD", "WOULD", "SHOULD", "LET", "USE", "USING", "USED", "FROM",
    "WANT", "NEED", "HAVE", "HAD", "HAS", "BEEN", "BEING", "DOES", "DID",
    "WHICH", "SOME", "MORE", "LESS", "BETTER", "GOOD", "BAD", "HIGH", "LOW",
    "UP", "DOWN", "LONG", "SHORT", "BUY", "SELL", "HOLD", "EXIT", "ENTER",
    "OPEN", "CLOSE", "NEW", "OLD", "FEW", "LOT", "LOTS", "ONE", "TWO", "THREE",
    "CURRENT", "LATEST", "RECENT", "TODAY", "NOW", "THEN", "ALSO", "JUST",
    "PRICE", "TRADE", "TRADING", "MARKET", "DATA", "INFO", "INFORMATION",
    "RETURN", "PROFIT", "LOSS", "GAIN", "VALUE", "RATE", "RATIO", "SCORE",
    "TOP", "BEST", "WORST", "SAME", "BOTH", "EACH", "EVERY", "SUCH",
}

# ── Full universe lookup: every symbol in universe.py, keyed by its lowercase ──
# e.g. "zomato" → "ZOMATO", "hdfcbank" → "HDFCBANK", "360one" → "360ONE"
_UNIVERSE_LOOKUP: dict[str, str] = {
    sym.lower(): sym
    for sym in ALL_SYMBOLS
    if not any(c.isspace() for c in sym)   # exclude index names like "NIFTY 50"
}

# ── Human-readable name aliases (multi-word or non-obvious) ───────────────────
_FRIENDLY_NAMES: dict[str, str] = {
    # Popular / consumer tech
    "zomato": "ZOMATO", "swiggy": "SWIGGY", "nykaa": "NYKAA",
    "paytm": "PAYTM", "dmart": "DMART", "avenue supermarts": "DMART",
    "irctc": "IRCTC", "policy bazaar": "POLICYBZR", "policybazaar": "POLICYBZR",
    # Adani group
    "adani green": "ADANIGREEN", "adani power": "ADANIPOWER",
    "adani enterprises": "ADANIENT", "adani ports": "ADANIPORTS",
    "adani transmission": "ADANITRANS", "adani": "ADANIPORTS",
    # Tata group
    "tata motors": "TATAMOTORS", "tata steel": "TATASTEEL",
    "tata power": "TATAPOWER", "tata tech": "TATATECH",
    "tata elxsi": "TATAELXSI", "tata comm": "TATACOMM",
    "tata communications": "TATACOMM", "tata consumer": "TATACONSUM",
    "tata investment": "TATAINVEST",
    # Banks
    "hdfc bank": "HDFCBANK", "hdfcbank": "HDFCBANK",
    "icici bank": "ICICIBANK", "icici": "ICICIBANK",
    "axis bank": "AXISBANK", "kotak bank": "KOTAKBANK", "kotak": "KOTAKBANK",
    "indusind": "INDUSINDBK", "indusind bank": "INDUSINDBK",
    "idfc first": "IDFCFIRSTB", "bandhan bank": "BANDHANBNK",
    "rbl bank": "RBLBANK", "yes bank": "YESBANK", "federal bank": "FEDERALBNK",
    "bank of baroda": "BANKBARODA", "punjab national": "PNB",
    "canara bank": "CANBK", "sbi": "SBIN", "state bank": "SBIN",
    # IT
    "infosys": "INFY", "hcl tech": "HCLTECH", "hcltech": "HCLTECH",
    "wipro": "WIPRO", "tech mahindra": "TECHM", "techmahindra": "TECHM",
    "mphasis": "MPHASIS", "coforge": "COFORGE", "persistent": "PERSISTENT",
    # Pharma
    "sun pharma": "SUNPHARMA", "dr reddy": "DRREDDY", "dr. reddy": "DRREDDY",
    "divis lab": "DIVISLAB", "divislab": "DIVISLAB",
    "lupin": "LUPIN", "biocon": "BIOCON", "cipla": "CIPLA",
    "aurobindo": "AUROPHARMA", "glenmark": "GLENMARK",
    # FMCG / consumer
    "hul": "HINDUNILVR", "hindustan unilever": "HINDUNILVR",
    "nestle": "NESTLEIND", "nestleind": "NESTLEIND",
    "asian paints": "ASIANPAINT", "asianpaint": "ASIANPAINT",
    "colgate": "COLPAL", "dabur": "DABUR", "marico": "MARICO",
    "godrej": "GODREJCP", "britannia": "BRITANNIA",
    # Energy / infra
    "reliance": "RELIANCE", "ongc": "ONGC", "bpcl": "BPCL",
    "ntpc": "NTPC", "powergrid": "POWERGRID", "coalindia": "COALINDIA",
    "l&t": "LT", "lt": "LT", "larsen": "LT",
    # Auto
    "maruti": "MARUTI", "maruti suzuki": "MARUTI",
    "bajaj auto": "BAJAJ-AUTO", "hero moto": "HEROMOTOCO",
    "eicher": "EICHERMOT", "mahindra": "M&M",
    # Financials
    "bajaj finance": "BAJFINANCE", "bajaj finserv": "BAJAJFINSV",
    "muthoot": "MUTHOOTFIN", "hdfc life": "HDFCLIFE", "sbi life": "SBILIFE",
    "cholafin": "CHOLAFIN", "shriram": "SHRIRAMFIN",
}

# ── Merged symbol resolver: friendly names + full universe ────────────────────
_SYMBOL_RESOLVER: dict[str, str] = {**_UNIVERSE_LOOKUP, **_FRIENDLY_NAMES}

AGENT_DESCRIPTIONS = [
    {
        "name": "forecast",
        "description": "Predict the future price of a stock over 5-30 days using probabilistic TFT-inspired forecasting",
        "keywords": ["forecast", "predict", "price target", "where will", "next week", "next month", "future", "will it go", "target"],
    },
    {
        # backtest MUST appear before pairs — "backtest X Y pair" matches both;
        # putting backtest first ensures it wins the tie when scores are equal
        "name": "backtest",
        "description": "Run an event-driven backtest of a pairs trading strategy with realistic slippage and commissions",
        "keywords": ["backtest", "historical", "simulate", "performance", "sharpe", "drawdown", "test strategy"],
    },
    {
        "name": "pairs",
        "description": "Find cointegrated pairs of stocks using the Engle-Granger test and analyze their OU spread signals",
        "keywords": ["pairs", "cointegrated", "pair", "spread", "arbitrage", "OU", "ornstein", "mean revert"],
    },
    {
        "name": "var",
        "description": "Calculate the Value at Risk and Expected Shortfall for a stock or portfolio",
        "keywords": ["var", "value at risk", "risk", "loss", "drawdown risk", "portfolio risk", "shortfall", "cvar"],
    },
    {
        "name": "sentiment",
        "description": "Analyze the market sentiment for a stock using NLP-based VADER scoring",
        "keywords": ["sentiment", "news", "opinion", "buzz", "feeling", "mood", "bullish feeling", "bearish feeling"],
    },
]


def _extract_symbols(text: str) -> list[str]:
    """
    Extract NSE ticker symbols from free-form text.
    Filters out stopwords and common English words so 'BACKTEST', 'PAIR' etc.
    are never treated as stock tickers.
    Universe-known symbols are returned as-is (canonical casing from universe.py).
    Unknown uppercase tokens are also included so novel symbols still work.
    """
    candidates = re.findall(r'\b([A-Z0-9]{2,10})\b', text.upper())
    results = []
    for c in candidates:
        if c in _SYMBOL_STOPWORDS:
            continue
        # Return the canonical symbol if it's in the universe
        canonical = _UNIVERSE_LOOKUP.get(c.lower())
        results.append(canonical if canonical else c)
    return results


def _resolve_symbol(text: str) -> str | None:
    """
    Try to resolve a single NSE ticker from free-form text.
    Priority:
      1. Multi-word friendly names (e.g. 'adani green') — substring match (longest first)
      2. Single-word universe lookup — whole-word boundary match to avoid 'atam' in 'tatamotors'
      3. Uppercase token extraction fallback
    Handles any case: 'Zomato', 'ZOMATO', 'zomato', 'Adani Green' all work.
    """
    lower = text.lower()

    # 1a. Multi-word friendly names (e.g. 'adani green') — safe to substring-match
    #     since a two-word phrase won't accidentally appear inside a single word.
    #     Checked longest-first so 'adani green' wins over 'adani'.
    for name in sorted((n for n in _FRIENDLY_NAMES if ' ' in n), key=len, reverse=True):
        if name in lower:
            return _FRIENDLY_NAMES[name]

    # 1b. Single-word friendly names and universe symbols — token-based lookup
    #     so 'wipro' won't match inside 'tatamotors' and 'pnb' won't match 'pncinfra'.
    tokens = re.split(r'[\s,;/]+', lower)
    for tok in tokens:
        sym = _FRIENDLY_NAMES.get(tok) or _UNIVERSE_LOOKUP.get(tok)
        if sym:
            return sym

    # 3. Fall back to uppercase token extraction
    syms = _extract_symbols(text)
    return syms[0] if syms else None


def _route_intent(query: str) -> str:
    """
    Intent classifier → agent name. Returns '' if nothing matches.
    First tries keyword scoring; if no keyword matches, falls back to
    structural patterns so shorthand queries like 'CDSL for 5 days'
    or 'ZOMATO 7 days' still route correctly.
    """
    lower = query.lower()
    scores = {}
    for agent in AGENT_DESCRIPTIONS:
        score = sum(1 for kw in agent["keywords"] if kw in lower)
        scores[agent["name"]] = score
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best

    # ── Structural fallbacks when no keyword matched ───────────────────────────
    # "[symbol] [for] N day/days/week/weeks" → forecast
    if re.search(r'\d+\s*(day|days|week|weeks)', lower):
        return "forecast"
    # "[symbol] and [symbol]" / "vs" / "versus" → pairs
    if re.search(r'\b(and|vs\.?|versus)\b', lower):
        return "pairs"

    return ""


_HELP_MESSAGE = (
    "I didn't quite understand that. Here are some things I can help with:\n\n"
    "• **Forecast a stock** — e.g. \"Forecast RELIANCE for 5 days\"\n"
    "• **Find paired stocks** — e.g. \"Analyze pair HDFCBANK and ICICIBANK\"\n"
    "• **Test a strategy** — e.g. \"Backtest ONGC BPCL pair\"\n"
    "• **Check portfolio risk** — e.g. \"What is the VaR of TCS INFY WIPRO?\"\n"
    "• **Read market mood** — e.g. \"Sentiment for TATAMOTORS\"\n\n"
    "Just type a question with the stock name (e.g. RELIANCE, TCS, INFY)."
)


def _plain_english_forecast(result: dict, symbol: str, horizon: int) -> str:
    p50 = result.get("p50", [])
    p10 = result.get("p10", [])
    p90 = result.get("p90", [])
    direction = result.get("direction", "NEUTRAL")
    exp_ret = result.get("expectedReturn", 0)
    rsi = result.get("rsi", 50)

    dir_word = {"BULLISH": "likely to go UP 📈", "BEARISH": "likely to go DOWN 📉"}.get(direction, "expected to stay FLAT ➡️")
    p50_final = f"₹{p50[-1]:.1f}" if p50 else "?"
    p10_final = f"₹{p10[-1]:.1f}" if p10 else "?"
    p90_final = f"₹{p90[-1]:.1f}" if p90 else "?"

    rsi_note = ""
    if rsi > 70:
        rsi_note = " The stock looks overbought — it may be due for a pullback."
    elif rsi < 30:
        rsi_note = " The stock looks oversold — it may bounce back soon."

    return (
        f"**{symbol} over the next {horizon} day(s):** The price is {dir_word}, "
        f"with an expected change of {exp_ret:+.2f}%. "
        f"The likely price range is {p10_final} (worst case) to {p90_final} (best case), "
        f"with the most likely landing around {p50_final}.{rsi_note} "
        f"Remember: this is a forecast, not a guarantee."
    )


def _plain_english_pairs(result: dict) -> str:
    sym_a = result.get("symbolA", "A")
    sym_b = result.get("symbolB", "B")
    is_coint = result.get("isCointegrated", False)
    signal = result.get("signal", {}).get("signal", "HOLD")
    half_life = result.get("ou", {}).get("halfLife", 9999)
    z = result.get("ou", {}).get("zScore", 0)

    coint_note = (
        f"✅ {sym_a} and {sym_b} historically move together — a good pair for spread trading."
        if is_coint else
        f"⚠️ {sym_a} and {sym_b} don't reliably move together — trading this pair carries higher risk."
    )

    hl_note = f"When they diverge, prices typically snap back in about {half_life:.0f} days." if half_life < 200 else "Price convergence is slow — patience required."

    signal_map = {
        "LONG_SPREAD": f"📌 Right now the gap is unusually wide ({z:.2f}σ) — this suggests buying {sym_a} and selling {sym_b}.",
        "SHORT_SPREAD": f"📌 Right now the gap is unusually narrow ({z:.2f}σ) — this suggests selling {sym_a} and buying {sym_b}.",
        "EXIT": "📌 The gap has returned to normal — a good time to close any open positions.",
        "HOLD": "📌 The gap is within normal range — no action needed right now.",
        "NO_TRADE": "📌 This pair moves too slowly to trade profitably.",
    }
    signal_note = signal_map.get(signal, "")

    return f"{coint_note} {hl_note} {signal_note}"


def _plain_english_backtest(sym_a: str, sym_b: str, result: dict) -> str:
    m = result.get("metrics", {})
    ret = m.get("totalReturnPct", 0)
    sharpe = m.get("annSharpe", 0)
    dd = m.get("maxDrawdownPct", 0)
    win = m.get("winRatePct", 0)
    trades = m.get("totalTrades", 0)
    days = result.get("totalDays", 0)

    ret_note = f"the portfolio **grew by {ret:.2f}%**" if ret > 0 else f"the portfolio **lost {abs(ret):.2f}%**"
    sharpe_note = (
        "That's an excellent risk-adjusted return (Sharpe > 2)." if sharpe > 2 else
        "That's a decent risk-adjusted return (Sharpe 1–2)." if sharpe > 1 else
        "The returns don't well compensate for the risk taken (Sharpe < 1)."
    )
    win_note = f"{win:.0f}% of trades were profitable."
    dd_note = f"The worst losing stretch was {dd:.1f}% below the peak."

    return (
        f"Testing the {sym_a}/{sym_b} pair strategy over {days} trading days: {ret_note}. "
        f"{sharpe_note} {win_note} {dd_note} "
        f"Total of {trades} round-trip trade(s) were made. "
        "This is a historical simulation — past performance does not guarantee future results."
    )


def _plain_english_var(result: dict) -> str:
    var_pct = result.get("portfolioVarPct", 0)
    cvar_pct = result.get("portfolioCvarPct", 0)
    var_abs = result.get("portfolioVarAbs", 0)
    symbols = result.get("symbols", [])
    conf = result.get("confidence", 0.95)
    syms_str = ", ".join(symbols[:3]) + ("..." if len(symbols) > 3 else "")

    severity = "low" if abs(var_pct) < 1 else "moderate" if abs(var_pct) < 2 else "high"

    return (
        f"**Risk check for {syms_str}:** On {conf * 100:.0f}% of days, your portfolio "
        f"should not lose more than **{abs(var_pct):.2f}%** in a single day. "
        f"On the worst days (the remaining {(1-conf)*100:.0f}%), losses could average around "
        f"{abs(cvar_pct):.2f}%. For a ₹10 lakh investment, that's roughly ₹{var_abs:,.0f} at risk on a bad day. "
        f"Overall risk level: **{severity.upper()}**."
    )


def _plain_english_sentiment(symbol: str, result: dict) -> str:
    label = result.get("label", "NEUTRAL")
    score = result.get("compound", 0)
    trend = result.get("trend", "")

    mood_map = {
        "STRONGLY_BULLISH": f"**Very positive** — {symbol} is showing strong upward momentum. Investors appear confident.",
        "BULLISH":          f"**Positive** — {symbol} has been trending upward recently.",
        "NEUTRAL":          f"**Neutral** — {symbol} is moving sideways with no clear direction.",
        "BEARISH":          f"**Negative** — {symbol} has been weakening recently.",
        "STRONGLY_BEARISH": f"**Very negative** — {symbol} is showing strong downward pressure.",
    }
    note = mood_map.get(label, f"Sentiment for {symbol}: {label}.")
    return (
        f"{note} The sentiment score is {score:.2f} "
        f"(scale: −1 very bearish → 0 neutral → +1 very bullish). "
        "This is based on recent price action, not news headlines."
    )


class HydraEngine:
    """Central orchestrator. Routes NL queries to the correct expert agent."""

    def __init__(self):
        self.agents = {a["name"]: a for a in AGENT_DESCRIPTIONS}

    # ── Public query interface ─────────────────────────────────────────────────

    async def query(self, user_query: str) -> dict:
        """
        Process a natural language query:
          1. Classify intent → select expert agent
          2. Extract parameters (symbols, horizon, etc.)
          3. Fetch data from DB (or Yahoo if missing)
          4. Run the expert agent
          5. Return structured result + human-readable summary
        """
        intent = _route_intent(user_query)
        symbol = _resolve_symbol(user_query)
        syms = _extract_symbols(user_query)  # stopword-filtered symbol list

        # Extract forecast horizon
        horizon = 5
        m = re.search(r'(\d+)\s*(day|week)', user_query.lower())
        if m:
            n = int(m.group(1))
            horizon = n * 5 if "week" in m.group(2) else n
            horizon = min(30, max(1, horizon))

        logger.info("Query: %r → intent=%s symbol=%s syms=%s", user_query, intent, symbol, syms)

        # No recognisable intent → return friendly help, not a crash
        if not intent:
            return {
                "intent": "help",
                "summary": _HELP_MESSAGE,
                "plain_english": _HELP_MESSAGE,
            }

        # Intent detected but no usable symbol → also show help
        if intent == "forecast" and not symbol and not syms:
            return {
                "intent": "help",
                "summary": "Please tell me which stock to forecast — e.g. \"Forecast RELIANCE for 5 days\".",
                "plain_english": "Please tell me which stock to forecast — e.g. \"Forecast RELIANCE for 5 days\".",
            }

        if intent == "forecast":
            return await self._run_forecast(symbol or syms[0] if syms else "RELIANCE", horizon, user_query)
        elif intent == "pairs":
            if len(syms) >= 2:
                return await self._run_pair_analysis(syms[0], syms[1])
            return await self._run_pair_scan(user_query)
        elif intent == "backtest":
            if len(syms) >= 2:
                return await self._run_backtest(syms[0], syms[1])
            return {
                "intent": "help",
                "summary": "Please give me two stock symbols — e.g. \"Backtest RELIANCE TCS pair\".",
                "plain_english": "Please give me two stock symbols — e.g. \"Backtest RELIANCE TCS pair\".",
            }
        elif intent == "var":
            if syms:
                return await self._run_var(syms[:5])
            return await self._run_var(["RELIANCE", "TCS", "HDFCBANK"])
        elif intent == "sentiment":
            return await self._run_sentiment(symbol or (syms[0] if syms else "RELIANCE"))

        return {
            "intent": "help",
            "summary": _HELP_MESSAGE,
            "plain_english": _HELP_MESSAGE,
        }

    # ── Expert agent implementations ───────────────────────────────────────────

    async def _ensure_data(self, symbol: str) -> list[dict]:
        """Fetch from DB, update from Yahoo if stale/empty."""
        history = db.get_history(symbol, days=365)
        if len(history) < 30:
            await db.update_ticker(symbol)
            history = db.get_history(symbol, days=365)
        return history

    async def _run_forecast(self, symbol: str, horizon: int, query: str = "") -> dict:
        rows = await self._ensure_data(symbol)
        if not rows:
            return {"error": f"No price data found for '{symbol}'. Please check the NSE symbol and try again."}
        closes = [r["close"] for r in rows if r.get("close")]
        sent = sentiment.price_action_sentiment(closes)
        result = forecast.forecast(symbol, rows, horizon_days=horizon,
                                   sentiment_score=sent["compound"])
        plain = _plain_english_forecast(result, symbol, horizon) if "error" not in result else result.get("error", "")
        return {
            "agent": "Forecaster",
            "intent": "forecast",
            "symbol": symbol,
            "result": result,
            "sentiment": sent,
            "plain_english": plain,
            "summary": (
                f"{symbol} {horizon}-day forecast: "
                f"P50={result.get('p50',['?'])[-1] if result.get('p50') else '?'} "
                f"| Direction: {result.get('direction','?')} "
                f"| Expected: {result.get('expectedReturn','?')}%"
            ),
        }

    async def _run_pair_analysis(self, symbol_a: str, symbol_b: str) -> dict:
        rows_a = await self._ensure_data(symbol_a)
        rows_b = await self._ensure_data(symbol_b)
        closes_a = [r["close"] for r in rows_a if r.get("close")]
        closes_b = [r["close"] for r in rows_b if r.get("close")]
        result = pairs.analyze_pair(symbol_a, symbol_b, closes_a, closes_b)
        plain = _plain_english_pairs(result) if "error" not in result else result.get("error", "")
        return {
            "agent": "PairsTrader",
            "intent": "pairs",
            "symbolA": symbol_a,
            "symbolB": symbol_b,
            "result": result,
            "plain_english": plain,
            "summary": (
                f"{symbol_a}/{symbol_b}: "
                f"p={result.get('cointegrationPValue','?')} "
                f"| {'✅ Cointegrated' if result.get('isCointegrated') else '⚠️ Not cointegrated'} "
                f"| Signal: {result.get('signal',{}).get('signal','?')}"
            ),
        }

    async def _run_pair_scan(self, query: str) -> dict:
        default_syms = ["RELIANCE", "ONGC", "BPCL", "HDFCBANK", "ICICIBANK",
                        "KOTAKBANK", "TCS", "INFY", "WIPRO", "HCLTECH"]
        histories = {}
        await asyncio.gather(*[db.update_ticker(s) for s in default_syms], return_exceptions=True)
        for s in default_syms:
            rows = db.get_history(s, days=365)
            closes = [r["close"] for r in rows if r.get("close")]
            if closes:
                histories[s] = closes
        found = pairs.scan_pairs(list(histories.keys()), histories)
        n = len(found)
        plain = (
            f"I scanned {len(histories)} large-cap NSE stocks and found {n} pairs that historically move together. "
            + (f"The best match is {found[0]['symbolA']}/{found[0]['symbolB']} (p={found[0]['pValue']:.4f})." if n > 0 else "No cointegrated pairs found right now — markets may be uncorrelated.")
        )
        return {
            "agent": "PairsTrader",
            "intent": "pairs_scan",
            "result": found,
            "plain_english": plain,
            "summary": f"Found {n} cointegrated pairs among {len(histories)} symbols",
        }

    async def _run_backtest(self, symbol_a: str, symbol_b: str) -> dict:
        rows_a = await self._ensure_data(symbol_a)
        rows_b = await self._ensure_data(symbol_b)
        closes_a = [r["close"] for r in rows_a if r.get("close")]
        closes_b = [r["close"] for r in rows_b if r.get("close")]
        pair_result = pairs.analyze_pair(symbol_a, symbol_b, closes_a, closes_b)
        ou = pair_result.get("ou", {})
        if "error" in ou or "error" in pair_result:
            return {"error": pair_result.get("error", "Pair analysis failed — not enough price data.")}
        bt_result = backtest.run_pairs_backtest(
            symbol_a, symbol_b, rows_a, rows_b,
            hedge_ratio=pair_result.get("hedgeRatio", 1.0),
            mu=ou.get("mu", 0.0),
            sigma_eq=ou.get("sigmaEq", 1.0),
        )
        plain = _plain_english_backtest(symbol_a, symbol_b, bt_result) if "error" not in bt_result else bt_result.get("error", "")
        return {
            "agent": "BacktestEngine",
            "intent": "backtest",
            "symbolA": symbol_a,
            "symbolB": symbol_b,
            "pairAnalysis": pair_result,
            "result": bt_result,
            "plain_english": plain,
            "summary": (
                f"Backtest {symbol_a}/{symbol_b}: "
                f"Return={bt_result.get('metrics',{}).get('totalReturnPct','?')}% "
                f"| Sharpe={bt_result.get('metrics',{}).get('annSharpe','?')} "
                f"| MaxDD={bt_result.get('metrics',{}).get('maxDrawdownPct','?')}%"
            ),
        }

    async def _run_var(self, symbols: list[str]) -> dict:
        closes_map = {}
        await asyncio.gather(*[db.update_ticker(s) for s in symbols], return_exceptions=True)
        for s in symbols:
            rows = db.get_history(s, days=365)
            closes = [r["close"] for r in rows if r.get("close")]
            if closes:
                closes_map[s] = closes
        valid = list(closes_map.keys())
        weights = [1 / len(valid)] * len(valid) if valid else []
        result = var_svc.portfolio_var(valid, closes_map, weights)
        plain = _plain_english_var(result) if "error" not in result else result.get("error", "")
        return {
            "agent": "VaRCalculator",
            "intent": "var",
            "symbols": valid,
            "result": result,
            "plain_english": plain,
            "summary": (
                f"95% VaR ({len(valid)} stocks, equal weight): "
                f"{result.get('portfolioVarPct','?')}% "
                f"(₹{result.get('portfolioVarAbs', 0):,.0f} per ₹10L)"
                if "error" not in result
                else f"VaR error: {result.get('error', 'unknown')}"
            ),
        }

    async def _run_sentiment(self, symbol: str) -> dict:
        rows = await self._ensure_data(symbol)
        closes = [r["close"] for r in rows if r.get("close")]
        sent = sentiment.price_action_sentiment(closes)
        plain = _plain_english_sentiment(symbol, sent)
        return {
            "agent": "SentimentAnalyzer",
            "intent": "sentiment",
            "symbol": symbol,
            "result": sent,
            "plain_english": plain,
            "summary": (
                f"{symbol} Sentiment: {sent['label']} "
                f"(score={sent['compound']:.3f})"
            ),
        }

    def capabilities(self) -> list[dict]:
        return AGENT_DESCRIPTIONS
