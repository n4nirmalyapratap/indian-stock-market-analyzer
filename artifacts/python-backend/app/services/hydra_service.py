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

logger = logging.getLogger(__name__)

# ── Known NSE large caps for quick resolution ──────────────────────────────────
NSE_POPULAR = {
    "reliance": "RELIANCE", "tcs": "TCS", "infosys": "INFY", "infy": "INFY",
    "hdfc bank": "HDFCBANK", "hdfcbank": "HDFCBANK", "icici": "ICICIBANK",
    "sbi": "SBIN", "wipro": "WIPRO", "hcl": "HCLTECH", "bajaj": "BAJFINANCE",
    "titan": "TITAN", "sunpharma": "SUNPHARMA", "cipla": "CIPLA",
    "drreddy": "DRREDDY", "maruti": "MARUTI", "tatamotors": "TATAMOTORS",
    "tata motors": "TATAMOTORS", "tata steel": "TATASTEEL", "tatasteel": "TATASTEEL",
    "jswsteel": "JSWSTEEL", "jsw steel": "JSWSTEEL", "hindalco": "HINDALCO",
    "ongc": "ONGC", "bpcl": "BPCL", "ntpc": "NTPC", "powergrid": "POWERGRID",
    "coalindia": "COALINDIA", "adani": "ADANIPORTS", "lt": "LT", "l&t": "LT",
    "kotakbank": "KOTAKBANK", "kotak": "KOTAKBANK", "axisbank": "AXISBANK",
    "axis bank": "AXISBANK", "indusind": "INDUSINDBK", "nestleind": "NESTLEIND",
    "nestle": "NESTLEIND", "itc": "ITC", "britannia": "BRITANNIA",
    "asianpaint": "ASIANPAINT", "asian paints": "ASIANPAINT",
}

AGENT_DESCRIPTIONS = [
    {
        "name": "forecast",
        "description": "Predict the future price of a stock over 5-30 days using probabilistic TFT-inspired forecasting",
        "keywords": ["forecast", "predict", "price target", "where will", "next week", "next month", "future", "will it go", "target"],
    },
    {
        "name": "pairs",
        "description": "Find cointegrated pairs of stocks using the Engle-Granger test and analyze their OU spread signals",
        "keywords": ["pairs", "cointegrated", "pair", "spread", "arbitrage", "OU", "ornstein", "mean revert"],
    },
    {
        "name": "backtest",
        "description": "Run an event-driven backtest of a pairs trading strategy with realistic slippage and commissions",
        "keywords": ["backtest", "historical", "simulate", "performance", "sharpe", "drawdown", "test strategy"],
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


def _resolve_symbol(text: str) -> str | None:
    """Try to resolve a ticker symbol from free-form text."""
    lower = text.lower()
    for name, sym in NSE_POPULAR.items():
        if name in lower:
            return sym
    m = re.search(r'\b([A-Z]{2,10})\b', text.upper())
    return m.group(1) if m else None


def _route_intent(query: str) -> str:
    """Simple keyword-based intent classifier → agent name."""
    lower = query.lower()
    scores = {}
    for agent in AGENT_DESCRIPTIONS:
        score = sum(1 for kw in agent["keywords"] if kw in lower)
        scores[agent["name"]] = score
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "forecast"


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

        # Extract forecast horizon
        horizon = 5
        m = re.search(r'(\d+)\s*(day|week)', user_query.lower())
        if m:
            n = int(m.group(1))
            horizon = n * 5 if "week" in m.group(2) else n
            horizon = min(30, max(1, horizon))

        logger.info("Query: %r → intent=%s symbol=%s", user_query, intent, symbol)

        if intent == "forecast":
            return await self._run_forecast(symbol or "RELIANCE", horizon, user_query)
        elif intent == "pairs":
            syms = re.findall(r'\b([A-Z]{2,10})\b', user_query.upper())
            if len(syms) >= 2:
                return await self._run_pair_analysis(syms[0], syms[1])
            return await self._run_pair_scan(user_query)
        elif intent == "backtest":
            syms = re.findall(r'\b([A-Z]{2,10})\b', user_query.upper())
            if len(syms) >= 2:
                return await self._run_backtest(syms[0], syms[1])
            return {"error": "Please specify two symbols for backtesting, e.g. 'backtest RELIANCE TCS'"}
        elif intent == "var":
            syms = re.findall(r'\b([A-Z]{2,10})\b', user_query.upper())
            if syms:
                return await self._run_var(syms[:5])
            return await self._run_var(["RELIANCE", "TCS", "HDFCBANK"])
        elif intent == "sentiment":
            return await self._run_sentiment(symbol or "RELIANCE")

        return {"error": "Could not understand query", "intent": intent}

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
            return {"error": f"No data available for {symbol}"}
        closes = [r["close"] for r in rows if r.get("close")]
        sent = sentiment.price_action_sentiment(closes)
        result = forecast.forecast(symbol, rows, horizon_days=horizon,
                                   sentiment_score=sent["compound"])
        return {
            "agent": "Forecaster",
            "intent": "forecast",
            "symbol": symbol,
            "result": result,
            "sentiment": sent,
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
        return {
            "agent": "PairsTrader",
            "intent": "pairs",
            "symbolA": symbol_a,
            "symbolB": symbol_b,
            "result": result,
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
        return {
            "agent": "PairsTrader",
            "intent": "pairs_scan",
            "result": found,
            "summary": f"Found {len(found)} cointegrated pairs among {len(histories)} symbols",
        }

    async def _run_backtest(self, symbol_a: str, symbol_b: str) -> dict:
        rows_a = await self._ensure_data(symbol_a)
        rows_b = await self._ensure_data(symbol_b)
        closes_a = [r["close"] for r in rows_a if r.get("close")]
        closes_b = [r["close"] for r in rows_b if r.get("close")]
        pair_result = pairs.analyze_pair(symbol_a, symbol_b, closes_a, closes_b)
        ou = pair_result.get("ou", {})
        if "error" in ou or "error" in pair_result:
            return {"error": pair_result.get("error", "Pair analysis failed")}
        bt_result = backtest.run_pairs_backtest(
            symbol_a, symbol_b, rows_a, rows_b,
            hedge_ratio=pair_result.get("hedgeRatio", 1.0),
            mu=ou.get("mu", 0.0),
            sigma_eq=ou.get("sigmaEq", 1.0),
        )
        return {
            "agent": "BacktestEngine",
            "intent": "backtest",
            "symbolA": symbol_a,
            "symbolB": symbol_b,
            "pairAnalysis": pair_result,
            "result": bt_result,
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
        return {
            "agent": "VaRCalculator",
            "intent": "var",
            "symbols": valid,
            "result": result,
            "summary": (
                f"95% VaR ({len(valid)} stocks, equal weight): "
                f"{result.get('portfolioVarPct','?')}% "
                f"(₹{result.get('portfolioVarAbs','?'):,} per ₹10L)"
            ),
        }

    async def _run_sentiment(self, symbol: str) -> dict:
        rows = await self._ensure_data(symbol)
        closes = [r["close"] for r in rows if r.get("close")]
        sent = sentiment.price_action_sentiment(closes)
        return {
            "agent": "SentimentAnalyzer",
            "intent": "sentiment",
            "symbol": symbol,
            "result": sent,
            "summary": (
                f"{symbol} Sentiment: {sent['label']} "
                f"(score={sent['compound']:.3f})"
            ),
        }

    def capabilities(self) -> list[dict]:
        return AGENT_DESCRIPTIONS
