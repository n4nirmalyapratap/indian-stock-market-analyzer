"""
Famous-Investor AI Agents — deterministic checklist evaluators inspired by the
documented investing philosophies of eight legendary investors.

Each persona implements:
  • metadata    — id, name, era, philosophy, signature_line
  • evaluate(ctx) → {score, verdict, checklist[], rationale}

The checklist items are derived from PUBLIC, well-documented investor
checklists (Buffett's owner-earnings, Graham's 7-rule defensive list, Lynch's
GARP, Klarman's margin-of-safety, etc.). No proprietary code is copied from
any source — only widely published philosophy is encoded as deterministic gates.

LLM is used ONLY to write a 1-paragraph plain-English thesis on top of the
deterministic verdict; the verdict itself never depends on the LLM.
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
from datetime import datetime, timezone
from typing import Any, Optional

from . import ai_client

logger = logging.getLogger(__name__)


# ── External-context fetchers (news + market sentiment) ──────────────────────
# These run alongside the deterministic checklist so personas (and the LLM
# thesis) can be aware of recent news flow and the broad-market mood.
# Failures degrade gracefully — agents must always work with whatever data
# is available.

async def _fetch_symbol_news(symbol: str, name: Optional[str], limit: int = 5) -> list[dict]:
    """Pull recent symbol-relevant news from the cached RSS feed.

    Matches on (a) the symbol token in extracted tickers or (b) the company's
    short name (first 1-2 words) appearing in the article title/summary.
    """
    try:
        from . import news_service
        feed = await news_service.get_news_feed(category="all", limit=100, offset=0)
    except Exception as exc:
        logger.warning("agents: news fetch failed: %s", exc)
        return []

    sym_u = (symbol or "").upper()
    # Build a name token (e.g. "Reliance Industries Ltd" → "reliance")
    name_tok = ""
    if name:
        first = re.split(r"[\s\.,&]+", name.strip())[0]
        if len(first) >= 4:
            name_tok = first.lower()

    matches: list[dict] = []
    for art in feed.get("articles", []):
        tickers = [t.upper() for t in (art.get("tickers") or [])]
        title   = (art.get("title")   or "").lower()
        summary = (art.get("summary") or "").lower()
        if (
            sym_u in tickers
            or (name_tok and (name_tok in title or name_tok in summary))
        ):
            matches.append({
                "title":     art.get("title"),
                "source":    art.get("source"),
                "published": art.get("published"),
                "sentiment": art.get("sentiment"),
                "url":       art.get("url"),
            })
            if len(matches) >= limit:
                break
    return matches


async def _fetch_fii_dii_pulse() -> dict:
    """Latest FII / DII equity flows (₹ crore, net) from NSE.

    Returned shape is intentionally tiny so it slots cleanly into the LLM
    prompt. Empty dict on any failure — pulse is informational only.
    """
    try:
        from .fii_dii_service import FiiDiiService
        snap = await FiiDiiService().fetch_equity_snapshot()
    except Exception as exc:
        logger.warning("agents: FII/DII pulse fetch failed: %s", exc)
        return {}
    if snap is None or snap.empty:
        return {}
    row = snap.iloc[0]
    fii_net = float(row.get("fii_net") or 0.0)
    dii_net = float(row.get("dii_net") or 0.0)
    if fii_net > 0 and dii_net > 0:
        flow = "Both FIIs and DIIs net buyers"
    elif fii_net < 0 and dii_net < 0:
        flow = "Both FIIs and DIIs net sellers"
    elif fii_net < 0 and dii_net > 0:
        flow = "FIIs selling, DIIs absorbing"
    elif fii_net > 0 and dii_net < 0:
        flow = "FIIs buying, DIIs selling"
    else:
        flow = "Flat institutional flows"
    return {
        "date":   str(row.get("date"))[:10],
        "fiiNet": round(fii_net, 1),  # ₹ crore
        "diiNet": round(dii_net, 1),
        "flow":   flow,
    }


async def _fetch_market_mood() -> dict:
    """Get the broad-market sentiment snapshot (VIX + price action + news mood).

    Returns a thin summary safe for inclusion in LLM prompts.
    """
    try:
        from . import market_sentiment_engine
        snap = await market_sentiment_engine.get_market_sentiment(force_refresh=False)
    except Exception as exc:
        logger.warning("agents: market sentiment fetch failed: %s", exc)
        return {}

    composite = snap.get("composite") or snap.get("compositeScore")
    return {
        "composite":   composite,
        "label":       snap.get("label"),
        "vix":         (snap.get("vix") or {}).get("current") if isinstance(snap.get("vix"), dict) else snap.get("vix"),
        "newsScore":   (snap.get("breakdown") or {}).get("news"),
        "priceAction": (snap.get("breakdown") or {}).get("priceAction"),
    }


async def gather_external_context(symbol: str, name: Optional[str]) -> dict:
    """Fetch news + market mood + FII/DII pulse concurrently. Always returns
    dict (never raises) — every fetcher already swallows its own errors."""
    news, mood, fii_dii = await asyncio.gather(
        _fetch_symbol_news(symbol, name),
        _fetch_market_mood(),
        _fetch_fii_dii_pulse(),
        return_exceptions=False,
    )
    return {"recentNews": news, "marketMood": mood, "fiiDii": fii_dii}


# ── Verdict thresholds ────────────────────────────────────────────────────────

def _verdict_from_score(score: float) -> str:
    if score >= 0.85:
        return "STRONG_BUY"
    if score >= 0.65:
        return "BUY"
    if score >= 0.45:
        return "HOLD"
    if score >= 0.30:
        return "AVOID"
    return "STRONG_AVOID"


def _safe_num(v: Any) -> Optional[float]:
    """Coerce to float, return None for missing/invalid."""
    if v is None:
        return None
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _check(label: str, value: Any, op: str, threshold: float, weight: float = 1.0,
           detail: str = "") -> dict:
    """Build a single checklist item.  op ∈ {>=, >, <=, <, between}.

    For 'between', `threshold` is a tuple-as-list [low, high]."""
    v = _safe_num(value)
    if v is None:
        return {"label": label, "passed": False, "value": None,
                "threshold": threshold, "op": op, "weight": weight,
                "detail": detail or "data not available"}

    passed = False
    if op == ">=":   passed = v >= threshold
    elif op == ">":  passed = v > threshold
    elif op == "<=": passed = v <= threshold
    elif op == "<":  passed = v < threshold
    elif op == "between" and isinstance(threshold, (list, tuple)) and len(threshold) == 2:
        passed = threshold[0] <= v <= threshold[1]

    return {
        "label":     label,
        "passed":    bool(passed),
        "value":     round(v, 4),
        "threshold": threshold,
        "op":        op,
        "weight":    weight,
        "detail":    detail,
    }


def _aggregate(checklist: list[dict]) -> tuple[float, str]:
    total_w = sum(c["weight"] for c in checklist) or 1.0
    pass_w  = sum(c["weight"] for c in checklist if c["passed"])
    score   = pass_w / total_w
    return round(score, 4), _verdict_from_score(score)


# ── Context builder ───────────────────────────────────────────────────────────

def build_context(stock_detail: dict) -> dict:
    """
    Flatten the stock_detail blob (from StocksService.get_stock_details +
    yfinance .info dict) into a single dict the personas can consume.

    Yahoo's info dict already contains most of what we need.  We also accept
    the technical analysis block for momentum-aware personas.
    """
    info = stock_detail.get("info") or stock_detail.get("yahooInfo") or {}
    # Some routes flatten info onto the top level; merge both shapes.
    merged = {**info, **stock_detail}

    ta = stock_detail.get("technicalAnalysis") or {}
    last_price = _safe_num(merged.get("lastPrice") or merged.get("currentPrice")
                           or merged.get("regularMarketPrice"))
    high_52    = _safe_num(merged.get("fiftyTwoWeekHigh") or merged.get("high52"))
    low_52     = _safe_num(merged.get("fiftyTwoWeekLow")  or merged.get("low52"))

    pct_off_high = None
    if last_price and high_52 and high_52 > 0:
        pct_off_high = (last_price - high_52) / high_52 * 100  # negative = below high

    free_cf  = _safe_num(merged.get("freeCashflow"))
    mkt_cap  = _safe_num(merged.get("marketCap"))
    fcf_yld  = (free_cf / mkt_cap * 100) if (free_cf and mkt_cap) else None

    return {
        "symbol":       (stock_detail.get("symbol") or "").upper(),
        "name":         merged.get("longName") or merged.get("shortName") or merged.get("companyName"),
        "sector":       merged.get("sector") or merged.get("industry"),
        "lastPrice":    last_price,
        "marketCap":    mkt_cap,
        # Valuation
        "trailingPE":         _safe_num(merged.get("trailingPE")),
        "forwardPE":          _safe_num(merged.get("forwardPE")),
        "pegRatio":           _safe_num(merged.get("pegRatio")),
        "priceToBook":        _safe_num(merged.get("priceToBook")),
        "priceToSales":       _safe_num(merged.get("priceToSalesTrailing12Months")),
        "enterpriseValue":    _safe_num(merged.get("enterpriseValue")),
        "evToRevenue":        _safe_num(merged.get("enterpriseToRevenue")),
        "evToEbitda":         _safe_num(merged.get("enterpriseToEbitda")),
        # Profitability
        "returnOnEquity":     _safe_num(merged.get("returnOnEquity")),
        "returnOnAssets":     _safe_num(merged.get("returnOnAssets")),
        "profitMargin":       _safe_num(merged.get("profitMargins")),
        "operatingMargin":    _safe_num(merged.get("operatingMargins")),
        "grossMargin":        _safe_num(merged.get("grossMargins")),
        # Health
        "debtToEquity":       _safe_num(merged.get("debtToEquity")),
        "currentRatio":       _safe_num(merged.get("currentRatio")),
        "quickRatio":         _safe_num(merged.get("quickRatio")),
        "totalCash":          _safe_num(merged.get("totalCash")),
        "totalDebt":          _safe_num(merged.get("totalDebt")),
        # Growth
        "earningsGrowth":     _safe_num(merged.get("earningsGrowth")),
        "revenueGrowth":      _safe_num(merged.get("revenueGrowth")),
        "earningsQuarterlyGrowth": _safe_num(merged.get("earningsQuarterlyGrowth")),
        # Cash & dividends
        "freeCashflow":       free_cf,
        "operatingCashflow":  _safe_num(merged.get("operatingCashflow")),
        "fcfYield":           fcf_yld,
        "dividendYield":      _safe_num(merged.get("dividendYield")),
        "payoutRatio":        _safe_num(merged.get("payoutRatio")),
        "trailingEps":        _safe_num(merged.get("trailingEps")),
        # Ownership / risk
        "beta":               _safe_num(merged.get("beta")),
        "heldPercentInsiders":      _safe_num(merged.get("heldPercentInsiders")),
        "heldPercentInstitutions":  _safe_num(merged.get("heldPercentInstitutions")),
        "shortPercentOfFloat":      _safe_num(merged.get("shortPercentOfFloat")),
        # Price action
        "high52":       high_52,
        "low52":        low_52,
        "pctOffHigh":   pct_off_high,
        # Technical
        "rsi":          _safe_num(ta.get("rsi")),
        "trend":        ta.get("trend") or ta.get("signal"),
        "ma50":         _safe_num(ta.get("ema50") or ta.get("ma50")),
        "ma200":        _safe_num(ta.get("ema200") or ta.get("ma200")),
        # Analyst
        "recommendationMean": _safe_num(merged.get("recommendationMean")),
        "targetMeanPrice":    _safe_num(merged.get("targetMeanPrice")),
    }


# ── Persona evaluators ───────────────────────────────────────────────────────
#  Yahoo's `returnOnEquity`, `profitMargins`, `operatingMargins`, `grossMargins`
#  are returned as fractions (0.18 for 18%), so checklist thresholds use the
#  same scale.  `debtToEquity` is reported as a percentage by Yahoo (e.g. 50.0
#  for D/E = 0.5), so thresholds are scaled accordingly.

def _evaluate_buffett(c: dict) -> dict:
    checklist = [
        _check("Sustained ROE > 15%",         c["returnOnEquity"],   ">=", 0.15, 1.5,
               "Buffett wants businesses that earn high returns on shareholder capital."),
        _check("Operating margin > 15%",      c["operatingMargin"],  ">=", 0.15, 1.0,
               "Strong pricing power and efficient operations."),
        _check("Gross margin > 30% (moat)",   c["grossMargin"],      ">=", 0.30, 1.0,
               "Wide gross margin suggests durable competitive advantage."),
        _check("Debt-to-equity < 50",         c["debtToEquity"],     "<",  50.0, 1.0,
               "Conservative balance sheet; Buffett dislikes leverage."),
        _check("Free cash flow yield > 4%",   c["fcfYield"],         ">=", 4.0,  1.5,
               "Owner-earnings yield must beat long bonds for a margin of safety."),
        _check("P/E < 25 (don't overpay)",    c["trailingPE"],       "<",  25.0, 1.0,
               "Even great companies are bad investments at any price."),
        _check("Earnings growth positive",    c["earningsGrowth"],   ">",  0.0,  1.0,
               "Business must be moving forward, not stagnating."),
    ]
    score, verdict = _aggregate(checklist)
    return {"score": score, "verdict": verdict, "checklist": checklist}


def _evaluate_graham(c: dict) -> dict:
    pe = c["trailingPE"]
    pb = c["priceToBook"]
    pe_pb_product = (pe * pb) if (pe is not None and pb is not None and pe > 0 and pb > 0) else None
    checklist = [
        _check("P/E < 15 (Defensive Investor)", pe,                   "<",  15.0, 1.5,
               "Graham's hard cap on valuation for the defensive investor."),
        _check("Price-to-book < 1.5",            pb,                   "<",  1.5,  1.5,
               "Don't pay much more than the company's net asset value."),
        _check("P/E × P/B < 22.5 (Graham #)",    pe_pb_product,        "<",  22.5, 1.0,
               "Graham's combined valuation rule."),
        _check("Current ratio > 2",              c["currentRatio"],    ">=", 2.0,  1.0,
               "Strong working capital — short-term obligations covered twice."),
        _check("Debt-to-equity < 100",           c["debtToEquity"],    "<",  100.0,1.0,
               "Long-term debt should not exceed working capital."),
        _check("Positive trailing EPS",          c["trailingEps"],     ">",  0.0,  1.0,
               "Continuous earnings — no losses in the trailing period."),
        _check("Pays a dividend",                c["dividendYield"],   ">",  0.0,  1.0,
               "Uninterrupted dividends are a sign of a sound business."),
    ]
    score, verdict = _aggregate(checklist)
    return {"score": score, "verdict": verdict, "checklist": checklist}


def _evaluate_lynch(c: dict) -> dict:
    # PEG: prefer Yahoo's pegRatio; otherwise compute as PE / (earningsGrowth*100).
    peg = c["pegRatio"]
    if peg is None and c["trailingPE"] and c["earningsGrowth"] and c["earningsGrowth"] > 0:
        peg = c["trailingPE"] / (c["earningsGrowth"] * 100.0)
    checklist = [
        _check("PEG ratio < 1 (GARP sweet spot)", peg,                   "<",  1.0,  2.0,
               "Lynch's headline rule: pay no more than 1x the growth rate."),
        _check("Earnings growth 15–25%",          c["earningsGrowth"],   "between", [0.15, 0.25], 1.5,
               "Lynch's 'fast grower' band — growth without being a fad."),
        _check("Debt-to-equity < 50",             c["debtToEquity"],     "<",  50.0, 1.0,
               "Strong balance sheet so growth is real, not debt-fuelled."),
        _check("Insider ownership > 5%",          c["heldPercentInsiders"], ">=", 0.05, 1.0,
               "Insiders eat their own cooking — skin in the game."),
        _check("Institutional holding < 70%",     c["heldPercentInstitutions"], "<", 0.70, 1.0,
               "Lynch loved stocks Wall Street had not yet discovered."),
        _check("Operating margin > 10%",          c["operatingMargin"],  ">=", 0.10, 1.0,
               "Quality growth, not vanity revenue."),
    ]
    score, verdict = _aggregate(checklist)
    return {"score": score, "verdict": verdict, "checklist": checklist}


def _evaluate_munger(c: dict) -> dict:
    checklist = [
        _check("ROE > 20% (high quality)",       c["returnOnEquity"],  ">=", 0.20, 2.0,
               "Munger insisted on businesses that earn 20%+ on capital."),
        _check("ROA > 10%",                      c["returnOnAssets"],  ">=", 0.10, 1.0,
               "Asset-light, capital-efficient operations."),
        _check("Operating margin > 20%",         c["operatingMargin"], ">=", 0.20, 1.5,
               "Pricing power above the industry average."),
        _check("Free cash flow positive",        c["freeCashflow"],    ">",  0.0,  1.5,
               "A wonderful business compounds free cash, not accruals."),
        _check("Predictable (beta < 1.2)",       c["beta"],            "<",  1.2,  1.0,
               "Munger preferred businesses whose results don't surprise."),
        _check("P/E < 30 (premium for quality)", c["trailingPE"],      "<",  30.0, 1.0,
               "Munger paid up for quality — but not blindly."),
    ]
    score, verdict = _aggregate(checklist)
    return {"score": score, "verdict": verdict, "checklist": checklist}


def _evaluate_klarman(c: dict) -> dict:
    cash_to_cap = (c["totalCash"] / c["marketCap"]) if (c["totalCash"] and c["marketCap"]) else None
    checklist = [
        _check("Price-to-book < 1 (deep value)", c["priceToBook"],     "<",  1.0,  2.0,
               "Klarman insists on a real margin of safety vs tangible assets."),
        _check("P/E < 12",                       c["trailingPE"],      "<",  12.0, 1.5,
               "Buy earnings cheaply enough that mistakes don't ruin you."),
        _check("Net cash > 20% of market cap",   cash_to_cap,          ">=", 0.20, 1.5,
               "Hidden cash provides downside protection."),
        _check("Current ratio > 1.5",            c["currentRatio"],    ">=", 1.5,  1.0,
               "Survive long enough to be right."),
        _check("Free cash flow positive",        c["freeCashflow"],    ">",  0.0,  1.0,
               "A real business, not a turnaround story dependent on capital raises."),
        _check("Debt-to-equity < 100",           c["debtToEquity"],    "<",  100.0,1.0,
               "Avoid balance-sheet risk in distressed situations."),
    ]
    score, verdict = _aggregate(checklist)
    return {"score": score, "verdict": verdict, "checklist": checklist}


def _evaluate_marks(c: dict) -> dict:
    # Marks loves "second-level thinking" — buy when others are fearful and the
    # cycle is against the asset.  Use price action as a sentiment proxy.
    checklist = [
        _check("Down 20%+ from 52w high",        c["pctOffHigh"],      "<=", -20.0, 2.0,
               "Marks: bargains exist when sentiment has turned against an asset."),
        _check("RSI < 40 (oversold)",            c["rsi"],             "<",  40.0, 1.5,
               "Technical oversold confirms the negative crowd sentiment."),
        _check("P/E < 18 (cycle low pricing)",   c["trailingPE"],      "<",  18.0, 1.0,
               "Buying cheap when everyone else won't."),
        _check("Free cash flow positive",        c["freeCashflow"],    ">",  0.0,  1.5,
               "The business must survive the down-cycle on its own cash."),
        _check("Current ratio > 1.2",            c["currentRatio"],    ">=", 1.2,  1.0,
               "Liquidity to weather the cycle."),
        _check("Debt-to-equity < 100",           c["debtToEquity"],    "<",  100.0,1.0,
               "Distressed situations need a survivable balance sheet."),
    ]
    score, verdict = _aggregate(checklist)
    return {"score": score, "verdict": verdict, "checklist": checklist}


def _evaluate_dalio(c: dict) -> dict:
    # Dalio's "All-Weather" wants stable cash-yielding assets that survive any
    # macro environment.  Large, dividend-paying, low-debt businesses score best.
    checklist = [
        _check("Dividend yield > 2%",            c["dividendYield"],   ">=", 0.02, 1.5,
               "Income contribution helps the All-Weather portfolio."),
        _check("Debt-to-equity < 50",            c["debtToEquity"],    "<",  50.0, 1.5,
               "Survives rising-rate / deleveraging environments."),
        _check("Beta < 1.3",                     c["beta"],            "<",  1.3,  1.0,
               "Lower volatility fits risk-parity sizing."),
        _check("Market cap > ₹50,000 Cr",        c["marketCap"],       ">=", 5e11, 1.0,
               "Large-cap liquidity for institutional sizing."),
        _check("Operating margin > 12%",         c["operatingMargin"], ">=", 0.12, 1.0,
               "Profitable through full economic cycles."),
        _check("Free cash flow positive",        c["freeCashflow"],    ">",  0.0,  1.5,
               "Cash generation is the bedrock of any-environment resilience."),
    ]
    score, verdict = _aggregate(checklist)
    return {"score": score, "verdict": verdict, "checklist": checklist}


def _evaluate_burry(c: dict) -> dict:
    checklist = [
        _check("P/E < 10 (deep contrarian value)", c["trailingPE"],      "<",  10.0, 2.0,
               "Burry hunts for stocks the market has given up on."),
        _check("Price-to-book < 1.2",              c["priceToBook"],     "<",  1.2,  1.5,
               "Trading near or below tangible book — hard-asset support."),
        _check("Insider ownership > 10%",          c["heldPercentInsiders"], ">=", 0.10, 1.0,
               "Insiders heavily invested signals contrarian conviction."),
        _check("Debt-to-equity < 70",              c["debtToEquity"],    "<",  70.0, 1.0,
               "Leverage destroys deep-value plays in a downturn."),
        _check("Down 25%+ from 52w high",          c["pctOffHigh"],      "<=", -25.0,1.5,
               "Burry buys hated assets after they've already broken."),
        _check("Free cash flow positive",          c["freeCashflow"],    ">",  0.0,  1.0,
               "The business can self-fund through the contrarian thesis."),
    ]
    score, verdict = _aggregate(checklist)
    return {"score": score, "verdict": verdict, "checklist": checklist}


# ── Persona registry ──────────────────────────────────────────────────────────

PERSONAS: list[dict] = [
    {
        "id": "buffett", "name": "Warren Buffett", "firm": "Berkshire Hathaway",
        "era": "1956–present",
        "philosophy": "Quality at a fair price — wonderful businesses with durable moats.",
        "signature": "It's far better to buy a wonderful company at a fair price than a fair company at a wonderful price.",
        "evaluate": _evaluate_buffett,
    },
    {
        "id": "graham", "name": "Benjamin Graham", "firm": "Graham-Newman",
        "era": "1928–1956",
        "philosophy": "Deep value with a margin of safety — the father of value investing.",
        "signature": "The intelligent investor is a realist who sells to optimists and buys from pessimists.",
        "evaluate": _evaluate_graham,
    },
    {
        "id": "lynch", "name": "Peter Lynch", "firm": "Fidelity Magellan",
        "era": "1977–1990",
        "philosophy": "Growth at a reasonable price (GARP) — invest in what you understand.",
        "signature": "The person that turns over the most rocks wins the game.",
        "evaluate": _evaluate_lynch,
    },
    {
        "id": "munger", "name": "Charlie Munger", "firm": "Berkshire Hathaway",
        "era": "1962–2023",
        "philosophy": "High-quality compounders — buy great businesses and almost never sell.",
        "signature": "The big money is not in the buying or selling, but in the waiting.",
        "evaluate": _evaluate_munger,
    },
    {
        "id": "klarman", "name": "Seth Klarman", "firm": "Baupost Group",
        "era": "1982–present",
        "philosophy": "Margin of safety — risk-aversion above all, deep value with hard catalysts.",
        "signature": "Value investing is at its core the marriage of a contrarian streak and a calculator.",
        "evaluate": _evaluate_klarman,
    },
    {
        "id": "marks", "name": "Howard Marks", "firm": "Oaktree Capital",
        "era": "1995–present",
        "philosophy": "Cycles and second-level thinking — buy when others are forced to sell.",
        "signature": "The most dangerous investment conditions generally stem from psychology that's too positive.",
        "evaluate": _evaluate_marks,
    },
    {
        "id": "dalio", "name": "Ray Dalio", "firm": "Bridgewater Associates",
        "era": "1975–present",
        "philosophy": "All-weather macro — own assets that perform in any economic environment.",
        "signature": "He who lives by the crystal ball will eat shattered glass.",
        "evaluate": _evaluate_dalio,
    },
    {
        "id": "burry", "name": "Michael Burry", "firm": "Scion Asset Management",
        "era": "2000–present",
        "philosophy": "Contrarian deep value — bet against consensus when the math demands it.",
        "signature": "The fundamentals are clear and ugly; the question is when, not if.",
        "evaluate": _evaluate_burry,
    },
]


PERSONA_BY_ID = {p["id"]: p for p in PERSONAS}


def list_personas() -> list[dict]:
    """Public metadata only (no evaluator function)."""
    return [
        {k: v for k, v in p.items() if k != "evaluate"}
        for p in PERSONAS
    ]


# ── Council runner ────────────────────────────────────────────────────────────

def run_council(stock_detail: dict, external: Optional[dict] = None) -> dict:
    """Run all eight personas against the given stock_detail blob.  Pure
    deterministic — no LLM, fast (< 50 ms).

    `external` may carry recent news + market mood from `gather_external_context()`
    — these are passed through so the LLM thesis writer can cite them, but they
    do NOT affect the checklist scores (we keep verdicts fully reproducible).
    """
    ctx = build_context(stock_detail)
    if external:
        ctx["recentNews"]  = external.get("recentNews") or []
        ctx["marketMood"]  = external.get("marketMood") or {}
        ctx["fiiDii"]      = external.get("fiiDii") or {}

    results = []
    for p in PERSONAS:
        outcome = p["evaluate"](ctx)
        results.append({
            "id":         p["id"],
            "name":       p["name"],
            "firm":       p["firm"],
            "philosophy": p["philosophy"],
            "signature":  p["signature"],
            "score":      outcome["score"],
            "verdict":    outcome["verdict"],
            "checklist":  outcome["checklist"],
        })

    # Aggregate council verdict
    avg_score = sum(r["score"] for r in results) / len(results)
    buys      = sum(1 for r in results if r["verdict"] in ("BUY", "STRONG_BUY"))
    avoids    = sum(1 for r in results if r["verdict"] in ("AVOID", "STRONG_AVOID"))
    # Order matters: evaluate the strongest verdicts FIRST so e.g. 6 avoids
    # don't get downgraded to plain AVOID. Mutually exclusive in practice
    # because the buy/avoid counts are disjoint.
    council_verdict = (
        "STRONG_BUY"   if buys   >= 6 and avoids == 0 else
        "STRONG_AVOID" if avoids >= 6 and buys   == 0 else
        "BUY"          if buys   >= 5 and avoids <= 1 else
        "AVOID"        if avoids >= 5 and buys   <= 1 else
        "HOLD"
    )

    return {
        "symbol":        ctx["symbol"],
        "name":          ctx["name"],
        "sector":        ctx["sector"],
        "lastPrice":     ctx["lastPrice"],
        "context":       ctx,
        "personas":      results,
        "council": {
            "verdict":   council_verdict,
            "avgScore":  round(avg_score, 4),
            "buyCount":  buys,
            "avoidCount":avoids,
            "holdCount": len(results) - buys - avoids,
        },
        # Provenance / citations — every metric the council looked at can be
        # traced back to one of these public sources.
        "sources": [
            {"id": "yahoo_info",     "label": "Yahoo Finance fundamentals (yfinance .info)",
             "covers": "P/E, P/B, ROE, margins, debt/equity, FCF, growth, beta, ownership"},
            {"id": "technical",      "label": "Internal technical-analysis pipeline",
             "covers": "RSI, EMA50/EMA200, trend label"},
            {"id": "news_service",   "label": "RSS feed (Economic Times, Livemint, Moneycontrol)",
             "covers": "Symbol-tagged headlines + per-article sentiment"},
            {"id": "market_mood",    "label": "Market sentiment engine (VIX + Nifty PA + news NLP)",
             "covers": "Composite mood score and risk-on/risk-off label"},
            {"id": "fii_dii",        "label": "NSE FII/DII daily equity flows",
             "covers": "Net institutional buying/selling pressure (₹ crore)"},
        ],
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
    }


# ── LLM thesis writer ────────────────────────────────────────────────────────

def _persona_system_prompt(persona: dict) -> str:
    return (
        f"You are channelling the documented public investing philosophy of "
        f"{persona['name']} ({persona['firm']}, {persona['era']}). "
        f"{persona['philosophy']} "
        f"You are NOT giving personalised financial advice — you are writing "
        f"how this investor's PUBLIC checklist would view a given Indian stock. "
        f"Always end with the explicit disclaimer: "
        f"\"This is educational only and not personalised investment advice.\" "
        f"Stay in character — use this investor's voice and metaphors. "
        f"Be specific about numbers from the checklist provided."
    )


def _persona_user_prompt(persona: dict, evaluation: dict, ctx: dict) -> str:
    passed = [c for c in evaluation["checklist"] if c["passed"]]
    failed = [c for c in evaluation["checklist"] if not c["passed"]]

    def _line(c: dict) -> str:
        v = c["value"]
        v_str = f"{v}" if v is not None else "n/a"
        return f"  • {c['label']}  →  value={v_str}, target {c['op']} {c['threshold']}"

    sector = ctx.get("sector") or "Unknown sector"
    pe     = ctx.get("trailingPE")
    pb     = ctx.get("priceToBook")
    roe    = ctx.get("returnOnEquity")
    de     = ctx.get("debtToEquity")
    fcf_y  = ctx.get("fcfYield")
    pct_off= ctx.get("pctOffHigh")

    # ── External context (news + market mood). Fully optional — block omitted
    # from the prompt when both are empty so the model isn't distracted.
    news = ctx.get("recentNews") or []
    mood = ctx.get("marketMood") or {}
    news_block = ""
    if news:
        lines = []
        for n in news[:4]:
            sent = n.get("sentiment") or "neutral"
            lines.append(f"  • [{sent}] {n.get('title')} — {n.get('source')}")
        news_block = "Recent symbol news (RSS, last 24-48 h):\n" + "\n".join(lines) + "\n\n"
    mood_block = ""
    if mood and mood.get("label"):
        mood_block = (
            f"Broad-market mood: {mood.get('label')} "
            f"(composite {mood.get('composite')}, VIX {mood.get('vix')}).\n\n"
        )
    fii_dii = ctx.get("fiiDii") or {}
    fii_block = ""
    if fii_dii and fii_dii.get("flow"):
        fii_block = (
            f"FII/DII flows ({fii_dii.get('date')}): {fii_dii.get('flow')} "
            f"— FII net ₹{fii_dii.get('fiiNet')} cr, "
            f"DII net ₹{fii_dii.get('diiNet')} cr.\n\n"
        )

    return (
        f"Indian stock: {ctx.get('name')} ({ctx.get('symbol')})\n"
        f"Sector: {sector}\n"
        f"Last price: ₹{ctx.get('lastPrice')}\n"
        f"Key fundamentals available:\n"
        f"  P/E={pe}, P/B={pb}, ROE={roe}, D/E={de}, FCF yield={fcf_y}%, "
        f"% off 52w high={pct_off}\n\n"
        f"{news_block}{mood_block}{fii_block}"
        f"Your verdict from the deterministic checklist: "
        f"{evaluation['verdict']} (score {evaluation['score']*100:.0f}%).\n\n"
        f"Checks PASSED:\n" + ("\n".join(_line(c) for c in passed) or "  (none)") + "\n\n"
        f"Checks FAILED:\n" + ("\n".join(_line(c) for c in failed) or "  (none)") + "\n\n"
        f"Write a SHORT 4-6 sentence thesis in your voice explaining WHY you arrive "
        f"at the verdict, citing the most important 2-3 numbers above. If recent "
        f"news or market mood is provided, weave in ONE brief reference to it. "
        f"End with the required educational disclaimer."
    )


async def _thesis_for(persona: dict, evaluation: dict, ctx: dict) -> str:
    if not ai_client.is_available():
        return (
            f"{persona['name']} would say: verdict is {evaluation['verdict']} "
            f"based on a {evaluation['score']*100:.0f}% checklist score. "
            f"Connect OpenRouter in Admin → Integrations to get the full AI thesis. "
            f"This is educational only and not personalised investment advice."
        )
    try:
        text = await ai_client.ask(
            prompt=_persona_user_prompt(persona, evaluation, ctx),
            system=_persona_system_prompt(persona),
            max_tokens=400,
            temperature=0.55,
        )
        return text.strip()
    except Exception as exc:
        logger.warning("Thesis LLM call failed for %s: %s", persona["id"], exc)
        return (
            f"{persona['name']} would say: verdict is {evaluation['verdict']} "
            f"based on a {evaluation['score']*100:.0f}% checklist score. "
            f"(AI thesis temporarily unavailable.) "
            f"This is educational only and not personalised investment advice."
        )


async def run_council_with_theses(stock_detail: dict) -> dict:
    """Run the council and additionally generate an AI-written thesis per persona.
    Theses are produced concurrently (one LLM call per persona).

    Also enriches the context with recent symbol news and broad-market mood so
    each persona's thesis can cite real-time signals — without affecting the
    deterministic checklist scores.
    """
    sym  = (stock_detail.get("symbol") or "").upper()
    name = (stock_detail.get("info") or {}).get("longName") or stock_detail.get("companyName")
    external = await gather_external_context(sym, name)
    council  = run_council(stock_detail, external=external)
    ctx      = council["context"]

    coros = []
    for persona_result in council["personas"]:
        persona_def = PERSONA_BY_ID[persona_result["id"]]
        coros.append(_thesis_for(persona_def, persona_result, ctx))

    theses = await asyncio.gather(*coros, return_exceptions=False)
    for persona_result, thesis in zip(council["personas"], theses):
        persona_result["thesis"] = thesis

    return council


async def run_single_persona(persona_id: str, stock_detail: dict) -> dict:
    persona = PERSONA_BY_ID.get(persona_id)
    if not persona:
        return {"error": f"Unknown persona: {persona_id}"}

    ctx = build_context(stock_detail)
    sym  = ctx.get("symbol") or ""
    name = ctx.get("name")
    external = await gather_external_context(sym, name)
    ctx["recentNews"] = external.get("recentNews") or []
    ctx["marketMood"] = external.get("marketMood") or {}
    ctx["fiiDii"]     = external.get("fiiDii") or {}

    evaluation = persona["evaluate"](ctx)
    thesis = await _thesis_for(persona, evaluation, ctx)

    return {
        "id":         persona["id"],
        "name":       persona["name"],
        "firm":       persona["firm"],
        "era":        persona["era"],
        "philosophy": persona["philosophy"],
        "signature":  persona["signature"],
        "symbol":     ctx["symbol"],
        "name_stock": ctx["name"],
        "sector":     ctx["sector"],
        "lastPrice":  ctx["lastPrice"],
        "score":      evaluation["score"],
        "verdict":    evaluation["verdict"],
        "checklist":  evaluation["checklist"],
        "thesis":     thesis,
        "context":    ctx,
    }
