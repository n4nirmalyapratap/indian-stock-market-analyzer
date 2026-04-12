"""
market_sentiment_engine.py
Centralized Market Sentiment Engine — Single Source of Truth

Combines four independent signals into one composite sentiment score:
  • News NLP      (35%) — bullish/bearish article ratio from news_service
  • Price Action  (35%) — Nifty50 momentum + RSI via hydra_sentiment_service
  • India VIX     (20%) — fear gauge (inverted: high VIX → bearish)
  • PCR Proxy     (10%) — synthetic put/call ratio derived from VIX trend + breadth

Score range : -100 (Extremely Bearish) → +100 (Extremely Bullish)
Labels      : Extremely Bearish | Bearish | Neutral | Bullish | Extremely Bullish

Contrarian signals (from the research paper):
  • VIX > 25 AND score < -40  → Peak Fear      (potential market bottom)
  • VIX < 12 AND score > 60   → Peak Complacency (potential market top)
  • PCR proxy > 1.4            → Excessive Bearishness (contrarian buy)
  • PCR proxy < 0.5            → Excessive Bullishness (contrarian sell)

Cache TTL: 15 minutes (900 seconds)
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── In-memory cache ─────────────────────────────────────────────────────────
_CACHE: dict[str, Any] = {}
_CACHE_TTL = 900  # 15 minutes


def _cached(key: str) -> Any | None:
    entry = _CACHE.get(key)
    if entry and time.time() < entry["expiry"]:
        return entry["data"]
    return None


def _store(key: str, data: Any, ttl: int = _CACHE_TTL) -> None:
    _CACHE[key] = {"data": data, "expiry": time.time() + ttl}


def clear_cache() -> None:
    _CACHE.clear()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _label(score: float) -> str:
    if score >= 60:  return "Extremely Bullish"
    if score >= 25:  return "Bullish"
    if score > -25:  return "Neutral"
    if score > -60:  return "Bearish"
    return "Extremely Bearish"


def _vix_to_score(vix: float) -> float:
    """Convert India VIX to a sentiment contribution (-100 → +100)."""
    if vix <= 0:   return 0.0
    if vix < 10:   return 40.0    # unusually calm
    if vix < 12:   return 30.0    # very low fear
    if vix < 15:   return 15.0    # low fear
    if vix < 18:   return 5.0     # mildly calm
    if vix < 22:   return -5.0    # neutral-to-cautious
    if vix < 25:   return -20.0   # elevated fear
    if vix < 30:   return -40.0   # high fear
    return -60.0                   # panic (VIX ≥ 30)


def _vix_to_pcr_proxy(vix: float, vix_5d_change_pct: float) -> float:
    """
    Synthetic PCR proxy (Put/Call Ratio estimate).
    VIX and PCR are correlated — rising VIX = more put demand = rising PCR.
    Returns a PCR-like value (0.3 – 1.8).
    """
    # Base PCR from absolute VIX level
    if vix < 10:   base = 0.35
    elif vix < 13: base = 0.50
    elif vix < 16: base = 0.70
    elif vix < 20: base = 0.85
    elif vix < 25: base = 1.05
    elif vix < 30: base = 1.25
    else:          base = 1.50

    # Adjust for VIX trend: rising VIX → more put buying → higher PCR
    trend_adj = vix_5d_change_pct * 0.008   # e.g. +10% VIX move → +0.08 PCR
    return round(min(1.8, max(0.3, base + trend_adj)), 2)


def _pcr_to_score(pcr: float) -> float:
    """Convert synthetic PCR to sentiment score component (-100 → +100)."""
    if pcr < 0.5:  return 35.0    # extreme call dominance → bullish
    if pcr < 0.7:  return 20.0    # bullish
    if pcr < 1.0:  return 0.0     # neutral
    if pcr < 1.4:  return -20.0   # bearish
    return -35.0                   # extreme put dominance → bearish


def _interpret_vix(vix: float) -> dict:
    if vix < 12:
        return {"level": "Very Low", "emoji": "😴", "color": "green",
                "text": "Market is calm and complacent. Options are cheap. Ideal for buying strategies."}
    if vix < 15:
        return {"level": "Low", "emoji": "🟢", "color": "green",
                "text": "Low fear environment. Stable market conditions. Sellers have an edge in options."}
    if vix < 20:
        return {"level": "Moderate", "emoji": "🟡", "color": "yellow",
                "text": "Normal market volatility. Balanced conditions for most strategies."}
    if vix < 25:
        return {"level": "Elevated", "emoji": "🟠", "color": "orange",
                "text": "Elevated uncertainty. Caution warranted. Consider protective strategies."}
    if vix < 30:
        return {"level": "High", "emoji": "🔴", "color": "red",
                "text": "High fear. Markets expecting sharp moves. Premium sellers should be cautious."}
    return {"level": "Extreme", "emoji": "🚨", "color": "red",
            "text": "Extreme panic. Historically signals a potential reversal point (contrarian buy signal)."}


def _interpret_pcr(pcr: float) -> dict:
    if pcr < 0.5:
        return {"level": "Extreme Bullish", "emoji": "🐂", "color": "green",
                "text": "Extreme call dominance — market may be overbought. Contrarian bearish signal."}
    if pcr < 0.7:
        return {"level": "Bullish", "emoji": "🟢", "color": "green",
                "text": "More calls than puts. Bullish sentiment prevailing."}
    if pcr < 1.0:
        return {"level": "Neutral", "emoji": "⚖️", "color": "gray",
                "text": "Balanced put/call activity. Market in equilibrium."}
    if pcr < 1.4:
        return {"level": "Bearish", "emoji": "🔴", "color": "red",
                "text": "More puts than calls. Bearish expectations building."}
    return {"level": "Extreme Bearish", "emoji": "🐻", "color": "red",
            "text": "Extreme put dominance — market may be oversold. Contrarian bullish signal."}


def _contrarian_signals(
    composite: float, vix: float, pcr: float,
    news_bullish: int, news_bearish: int,
) -> list[dict]:
    signals = []

    # Peak Fear → potential bottom
    if vix > 25 and composite < -40:
        signals.append({
            "type": "PEAK_FEAR",
            "title": "Peak Fear Detected",
            "description": (
                f"India VIX at {vix:.1f} (extreme fear zone) combined with strongly bearish "
                "composite sentiment. Historically, extreme fear readings often coincide with "
                "market bottoms. Consider contrarian long positions with tight risk management."
            ),
            "signal": "Potential Market Bottom",
            "direction": "bullish_contrarian",
            "emoji": "🔔",
            "color": "amber",
        })

    # Peak Complacency → potential top
    if vix < 12 and composite > 60:
        signals.append({
            "type": "PEAK_COMPLACENCY",
            "title": "Peak Complacency Warning",
            "description": (
                f"India VIX at {vix:.1f} (extreme complacency) with euphoric sentiment. "
                "Extremely low VIX signals market may be vulnerable to a sharp correction. "
                "Review long positions and consider protective puts."
            ),
            "signal": "Potential Market Top",
            "direction": "bearish_contrarian",
            "emoji": "⚠️",
            "color": "red",
        })

    # Excessive bearishness (high PCR proxy)
    if pcr > 1.4 and composite > -20:
        signals.append({
            "type": "EXCESSIVE_BEARISHNESS",
            "title": "Excessive Bearishness in Options",
            "description": (
                f"PCR proxy at {pcr:.2f} indicates heavy put buying, yet price action "
                "is not as bearish. Crowd may be overly hedged — selling pressure could be "
                "exhausted. Watch for a bounce."
            ),
            "signal": "Contrarian Buy Watch",
            "direction": "bullish_contrarian",
            "emoji": "📊",
            "color": "amber",
        })

    # Excessive bullishness (low PCR proxy)
    if pcr < 0.5 and composite > 40:
        signals.append({
            "type": "EXCESSIVE_BULLISHNESS",
            "title": "Excessive Bullishness in Options",
            "description": (
                f"PCR proxy at {pcr:.2f} shows extreme call dominance. When everyone "
                "is positioned the same way, the trade gets crowded. Risk of a pullback is elevated."
            ),
            "signal": "Contrarian Sell Watch",
            "direction": "bearish_contrarian",
            "emoji": "📉",
            "color": "orange",
        })

    # News divergence
    total_articles = news_bullish + news_bearish
    if total_articles >= 5:
        bull_pct = news_bullish / total_articles
        if bull_pct > 0.75 and composite < 0:
            signals.append({
                "type": "NEWS_DIVERGENCE",
                "title": "News-Price Divergence",
                "description": (
                    f"{news_bullish} bullish vs {news_bearish} bearish articles, yet price action "
                    "is weak. News sentiment may be lagging reality — verify fundamentals."
                ),
                "signal": "Divergence Alert",
                "direction": "neutral",
                "emoji": "🔍",
                "color": "blue",
            })
        elif bull_pct < 0.25 and composite > 0:
            signals.append({
                "type": "NEWS_DIVERGENCE",
                "title": "News-Price Divergence",
                "description": (
                    f"{news_bearish} bearish vs {news_bullish} bullish articles, yet price action "
                    "remains positive. Resilient price action against negative news can be bullish."
                ),
                "signal": "Resilience Signal",
                "direction": "bullish",
                "emoji": "💪",
                "color": "green",
            })

    return signals


def _strategy_table(composite: float, vix: float) -> list[dict]:
    """Map sentiment + vol to recommended option strategies (from research paper)."""
    vol_high = vix >= 22
    vol_low = vix < 16

    if composite >= 30 and not vol_high:
        return [
            {"strategy": "Bull Call Spread",   "outlook": "Bullish",     "vol": "Low-Moderate",  "risk": "Limited"},
            {"strategy": "Covered Call",        "outlook": "Bullish",     "vol": "Low-Moderate",  "risk": "Limited"},
            {"strategy": "Bull Put Spread",     "outlook": "Bullish",     "vol": "Low-Moderate",  "risk": "Limited"},
        ]
    if composite >= 30 and vol_high:
        return [
            {"strategy": "Long Call",           "outlook": "Bullish",     "vol": "High",          "risk": "Limited"},
            {"strategy": "Long Straddle",       "outlook": "Any Direction","vol": "High",          "risk": "Limited"},
        ]
    if composite <= -30 and not vol_high:
        return [
            {"strategy": "Bear Put Spread",     "outlook": "Bearish",     "vol": "Low-Moderate",  "risk": "Limited"},
            {"strategy": "Protective Put",      "outlook": "Bearish",     "vol": "Low-Moderate",  "risk": "Limited"},
            {"strategy": "Bear Call Spread",    "outlook": "Bearish",     "vol": "Low-Moderate",  "risk": "Limited"},
        ]
    if composite <= -30 and vol_high:
        return [
            {"strategy": "Long Straddle",       "outlook": "Any Direction","vol": "High",          "risk": "Limited"},
            {"strategy": "Long Strangle",       "outlook": "Any Direction","vol": "High",          "risk": "Limited"},
        ]
    if vol_low:
        return [
            {"strategy": "Iron Condor",         "outlook": "Range-Bound", "vol": "Low",           "risk": "Limited"},
            {"strategy": "Butterfly Spread",    "outlook": "Range-Bound", "vol": "Low",           "risk": "Limited"},
            {"strategy": "Short Straddle",      "outlook": "Range-Bound", "vol": "Low",           "risk": "Unlimited"},
        ]
    if vol_high:
        return [
            {"strategy": "Long Straddle",       "outlook": "Any Direction","vol": "High VIX",      "risk": "Limited"},
            {"strategy": "Long Strangle",       "outlook": "Any Direction","vol": "High VIX",      "risk": "Limited"},
        ]
    return [
        {"strategy": "Iron Condor",             "outlook": "Range-Bound", "vol": "Moderate",      "risk": "Limited"},
        {"strategy": "Covered Call",            "outlook": "Neutral-Bullish","vol": "Moderate",   "risk": "Limited"},
        {"strategy": "Bull Put Spread",         "outlook": "Neutral-Bullish","vol": "Moderate",   "risk": "Limited"},
    ]


# ── Core async functions ─────────────────────────────────────────────────────

async def _fetch_vix() -> tuple[float, float]:
    """Returns (vix_current, vix_5d_pct_change)."""
    try:
        from .yahoo_service import YahooService
        from .market_cache_service import is_market_open
        import httpx

        yahoo_ticker = "^NSEVIXY"
        headers = {"User-Agent": "Mozilla/5.0"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}?interval=1d&range=1mo"
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return 15.0, 0.0
            data = resp.json()
            result = data.get("chart", {}).get("result", [None])[0]
            if not result:
                return 15.0, 0.0

            closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            closes = [c for c in closes if c is not None]
            if not closes:
                return 15.0, 0.0

            current_vix = closes[-1]
            vix_5d_ago  = closes[-6] if len(closes) >= 6 else closes[0]
            pct_change  = (current_vix - vix_5d_ago) / vix_5d_ago * 100 if vix_5d_ago else 0.0
            return current_vix, pct_change
    except Exception as e:
        logger.warning("VIX fetch failed: %s", e)
        return 15.0, 0.0


async def _fetch_nifty_price_action() -> dict:
    """Fetch Nifty50 history and compute price-action sentiment."""
    try:
        import httpx
        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1d&range=3mo"
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return {"compound": 0.0, "label": "NEUTRAL", "indicators": {}}
            data = resp.json()
            result = data.get("chart", {}).get("result", [None])[0]
            if not result:
                return {"compound": 0.0, "label": "NEUTRAL", "indicators": {}}
            closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            closes = [c for c in closes if c is not None]

        from .hydra_sentiment_service import price_action_sentiment
        return price_action_sentiment(closes)
    except Exception as e:
        logger.warning("Nifty price action fetch failed: %s", e)
        return {"compound": 0.0, "label": "NEUTRAL", "indicators": {}}


async def _fetch_news_mood() -> dict:
    """Fetch current news sentiment summary."""
    try:
        from .news_service import get_news_stats
        return await get_news_stats()
    except Exception as e:
        logger.warning("News mood fetch failed: %s", e)
        return {"totalArticles": 0, "sentiments": {"bullish": 0, "bearish": 0, "neutral": 0}, "marketMood": "neutral"}


async def _fetch_sector_sentiments() -> list[dict]:
    """Compute price-action sentiment for each Nifty sector index."""
    from .hydra_sentiment_service import price_action_sentiment
    import httpx

    SECTOR_TICKERS = [
        ("Nifty Bank",       "^NSEBANK"),
        ("Nifty IT",         "^CNXIT"),
        ("Nifty Auto",       "^CNXAUTO"),
        ("Nifty Pharma",     "^CNXPHARMA"),
        ("Nifty FMCG",       "^CNXFMCG"),
        ("Nifty Metal",      "^CNXMETAL"),
        ("Nifty Realty",     "^CNXREALTY"),
        ("Nifty Energy",     "^CNXENERGY"),
        ("Nifty Financial",  "^CNXFIN"),
        ("Nifty PSU Bank",   "^CNXPSUBANK"),
        ("Nifty Healthcare", "^CNXHEALTH"),
        ("Nifty Oil & Gas",  "^CNXOILGAS"),
    ]

    headers = {"User-Agent": "Mozilla/5.0"}

    async def _one(name: str, ticker: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=3mo"
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    return {"sector": name, "score": 0, "label": "Neutral", "compound": 0.0}
                data = resp.json()
                result = data.get("chart", {}).get("result", [None])[0]
                if not result:
                    return {"sector": name, "score": 0, "label": "Neutral", "compound": 0.0}
                closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
                closes = [c for c in closes if c is not None]
                pa = price_action_sentiment(closes)
                compound = pa.get("compound", 0.0)
                score = round(compound * 100)
                label = (
                    "Extremely Bullish" if score >= 60 else
                    "Bullish"           if score >= 20 else
                    "Neutral"           if score > -20 else
                    "Bearish"           if score > -60 else
                    "Extremely Bearish"
                )
                indicators = pa.get("indicators", {})
                return {
                    "sector": name,
                    "score": score,
                    "label": label,
                    "compound": compound,
                    "momentum5d": indicators.get("momentum5d", 0),
                    "momentum20d": indicators.get("momentum20d", 0),
                    "rsi14": indicators.get("rsi14", 50),
                }
        except Exception as e:
            logger.debug("Sector %s fetch error: %s", name, e)
            return {"sector": name, "score": 0, "label": "Neutral", "compound": 0.0}

    results = await asyncio.gather(*[_one(n, t) for n, t in SECTOR_TICKERS])
    return sorted(results, key=lambda x: x["score"], reverse=True)


# ── Public API ───────────────────────────────────────────────────────────────

async def get_market_sentiment(force_refresh: bool = False) -> dict:
    """
    Compute and return the full centralized market sentiment snapshot.
    Cached for 15 minutes. Call with force_refresh=True to bypass cache.
    """
    cache_key = "market_sentiment_full"
    if not force_refresh:
        cached = _cached(cache_key)
        if cached:
            return cached

    logger.info("Computing fresh market sentiment…")

    # ── Fetch all signals in parallel ────────────────────────────────────────
    vix_result, nifty_pa, news_mood = await asyncio.gather(
        _fetch_vix(),
        _fetch_nifty_price_action(),
        _fetch_news_mood(),
    )

    vix_current, vix_5d_pct = vix_result

    # ── News NLP score (-100 → +100) ─────────────────────────────────────────
    sentiments    = news_mood.get("sentiments", {})
    news_bullish  = sentiments.get("bullish", 0)
    news_bearish  = sentiments.get("bearish", 0)
    news_neutral  = sentiments.get("neutral", 0)
    news_total    = news_bullish + news_bearish + news_neutral

    if news_total > 0:
        news_raw   = (news_bullish - news_bearish) / news_total   # -1 → +1
        news_score = news_raw * 100
    else:
        news_score = 0.0

    # ── Price action score (-100 → +100) ─────────────────────────────────────
    pa_compound    = nifty_pa.get("compound", 0.0)
    pa_score       = pa_compound * 100
    pa_indicators  = nifty_pa.get("indicators", {})

    # ── VIX score (-100 → +100) ──────────────────────────────────────────────
    vix_score = _vix_to_score(vix_current)

    # ── PCR proxy ────────────────────────────────────────────────────────────
    pcr_proxy = _vix_to_pcr_proxy(vix_current, vix_5d_pct)
    pcr_score = _pcr_to_score(pcr_proxy)

    # ── Composite score (weighted average) ────────────────────────────────────
    composite = (
        news_score  * 0.35 +
        pa_score    * 0.35 +
        vix_score   * 0.20 +
        pcr_score   * 0.10
    )
    composite = round(max(-100.0, min(100.0, composite)), 1)
    label     = _label(composite)

    # ── Interpretations ───────────────────────────────────────────────────────
    vix_interp = _interpret_vix(vix_current)
    pcr_interp = _interpret_pcr(pcr_proxy)

    # ── Contrarian signals ────────────────────────────────────────────────────
    contrarian = _contrarian_signals(composite, vix_current, pcr_proxy, news_bullish, news_bearish)

    # ── Strategy recommendations ─────────────────────────────────────────────
    strategies = _strategy_table(composite, vix_current)

    # ── Component breakdown ───────────────────────────────────────────────────
    components = [
        {"name": "News Sentiment",  "score": round(news_score, 1),  "weight": 35,
         "detail": f"{news_bullish} bullish / {news_bearish} bearish / {news_neutral} neutral articles"},
        {"name": "Price Action",    "score": round(pa_score, 1),    "weight": 35,
         "detail": (f"Mom5d: {pa_indicators.get('momentum5d', 0):+.1f}% · "
                    f"Mom20d: {pa_indicators.get('momentum20d', 0):+.1f}% · "
                    f"RSI14: {pa_indicators.get('rsi14', 50):.0f}")},
        {"name": "India VIX",       "score": round(vix_score, 1),   "weight": 20,
         "detail": f"VIX {vix_current:.1f} ({vix_interp['level']}) · 5d change: {vix_5d_pct:+.1f}%"},
        {"name": "PCR Proxy",       "score": round(pcr_score, 1),   "weight": 10,
         "detail": f"Synthetic PCR estimate: {pcr_proxy:.2f} ({pcr_interp['level']})"},
    ]

    result = {
        "composite": composite,
        "label": label,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cached": False,
        "components": components,
        "vix": {
            "current": round(vix_current, 2),
            "change5d_pct": round(vix_5d_pct, 1),
            "score": round(vix_score, 1),
            "interpretation": vix_interp,
        },
        "pcr": {
            "proxy_value": pcr_proxy,
            "score": round(pcr_score, 1),
            "note": "Synthetic estimate based on VIX level and trend. Use NSE options chain for live PCR.",
            "interpretation": pcr_interp,
        },
        "news": {
            "total_articles": news_total,
            "bullish": news_bullish,
            "bearish": news_bearish,
            "neutral": news_neutral,
            "mood": news_mood.get("marketMood", "neutral"),
            "score": round(news_score, 1),
        },
        "price_action": {
            "score": round(pa_score, 1),
            "compound": pa_compound,
            "label": nifty_pa.get("label", "NEUTRAL"),
            "indicators": pa_indicators,
        },
        "contrarian_signals": contrarian,
        "strategy_recommendations": strategies,
    }

    _store(cache_key, result)
    return result


async def get_sector_sentiments(force_refresh: bool = False) -> list[dict]:
    """Return per-sector sentiment scores. Cached for 15 minutes."""
    cache_key = "sector_sentiment"
    if not force_refresh:
        cached = _cached(cache_key)
        if cached:
            return cached
    result = await _fetch_sector_sentiments()
    _store(cache_key, result)
    return result
