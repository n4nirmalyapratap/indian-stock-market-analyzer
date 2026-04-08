"""
Hydra-Alpha Engine — NLP Sentiment Module
VADER-based sentiment scoring on financial text.
Generates per-ticker sentiment features for the Forecasting module.
"""
from __future__ import annotations
import logging
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Lazy-load VADER to avoid import-time crash if not installed
_vader = None

def _get_vader():
    global _vader
    if _vader is None:
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            _vader = SentimentIntensityAnalyzer()
        except ImportError:
            logger.warning("vaderSentiment not installed; sentiment will be neutral")
    return _vader


# ── Financial lexicon augmentation ────────────────────────────────────────────
FINANCIAL_LEXICON: dict[str, float] = {
    # Strong bullish
    "breakout": 2.5, "rallied": 2.0, "surged": 2.5, "soared": 2.5,
    "upgraded": 2.0, "beat": 1.8, "outperform": 2.0, "accumulate": 1.5,
    "buy": 1.5, "strong buy": 3.0, "bullish": 2.0, "recovery": 1.5,
    "record high": 2.5, "all time high": 2.5, "profit": 1.5, "revenue beat": 2.5,
    # Moderate bullish
    "positive": 1.0, "growth": 1.0, "expansion": 1.0, "momentum": 1.0,
    "overweight": 1.2, "raise target": 1.5, "dividend": 0.8,
    # Bearish
    "downgrade": -2.0, "sell": -1.5, "crash": -2.5, "plunge": -2.5,
    "decline": -1.0, "weak": -1.2, "miss": -2.0, "loss": -1.5,
    "bearish": -2.0, "underperform": -2.0, "reduce": -1.2, "cut": -1.0,
    "warning": -1.5, "recall": -1.5, "fraud": -3.0, "default": -3.0,
    "bankruptcy": -3.0, "investigation": -2.0, "lawsuit": -1.8,
    # NSE/India specific
    "sebi": -0.5, "rbi": 0.0, "npa": -2.0, "gross npa": -2.5,
    "ipo": 1.0, "fii buying": 2.0, "fii selling": -2.0,
    "promoter buying": 1.5, "promoter selling": -1.5,
}


def _augmented_score(text: str) -> float:
    """VADER + financial lexicon augmentation → compound score."""
    sia = _get_vader()
    if sia is None:
        return 0.0
    scores = sia.polarity_scores(text)
    compound = scores["compound"]
    # Check financial lexicon overlays
    text_lower = text.lower()
    overlay = 0.0
    count = 0
    for term, val in FINANCIAL_LEXICON.items():
        if term in text_lower:
            overlay += val
            count += 1
    if count > 0:
        overlay_norm = max(-1.0, min(1.0, overlay / (count * 3.0)))
        compound = 0.6 * compound + 0.4 * overlay_norm
    return round(max(-1.0, min(1.0, compound)), 4)


def score_text(text: str) -> dict:
    """Score a single piece of financial text."""
    compound = _augmented_score(text)
    label = (
        "VERY_POSITIVE" if compound >= 0.5 else
        "POSITIVE"      if compound >= 0.05 else
        "NEUTRAL"        if compound > -0.05 else
        "NEGATIVE"       if compound > -0.5 else
        "VERY_NEGATIVE"
    )
    return {
        "text": text[:200],
        "compound": compound,
        "label": label,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


def score_batch(texts: list[str]) -> dict:
    """Score a list of texts and aggregate into a per-ticker sentiment."""
    if not texts:
        return {"compound": 0.0, "label": "NEUTRAL", "count": 0, "scores": []}
    scored = [score_text(t) for t in texts]
    compounds = [s["compound"] for s in scored]
    avg = sum(compounds) / len(compounds)
    # Weighted recent sentiment (later items carry more weight)
    n = len(compounds)
    weights = [(i + 1) / n for i in range(n)]
    weighted_avg = sum(c * w for c, w in zip(compounds, weights)) / sum(weights)
    label = (
        "VERY_POSITIVE" if weighted_avg >= 0.5 else
        "POSITIVE"      if weighted_avg >= 0.05 else
        "NEUTRAL"        if weighted_avg > -0.05 else
        "NEGATIVE"       if weighted_avg > -0.5 else
        "VERY_NEGATIVE"
    )
    return {
        "compound": round(weighted_avg, 4),
        "label": label,
        "count": n,
        "scores": scored[-10:],  # last 10 for display
    }


# ── Price-action based synthetic sentiment ─────────────────────────────────────
def price_action_sentiment(closes: list[float]) -> dict:
    """
    Derive a sentiment proxy from recent price action when no news is available.
    Uses momentum, RSI, and trend direction as sentiment signals.
    """
    if len(closes) < 14:
        return {"compound": 0.0, "label": "NEUTRAL", "count": 0, "scores": [],
                "source": "insufficient_data"}
    # 5-day momentum
    mom5 = (closes[-1] - closes[-5]) / closes[-5] * 100 if closes[-5] > 0 else 0
    # 20-day momentum
    mom20 = (closes[-1] - closes[-20]) / closes[-20] * 100 if len(closes) >= 20 and closes[-20] > 0 else 0
    # Simplified RSI
    gains, losses = [], []
    for i in range(1, min(15, len(closes))):
        diff = closes[-i] - closes[-(i+1)]
        (gains if diff > 0 else losses).append(abs(diff))
    avg_gain = sum(gains) / 14 if gains else 0
    avg_loss = sum(losses) / 14 if losses else 0.001
    rsi = 100 - (100 / (1 + avg_gain / avg_loss))
    # Compose compound score
    mom_score = max(-1.0, min(1.0, (mom5 * 0.6 + mom20 * 0.4) / 10))
    rsi_score = (rsi - 50) / 50  # -1 to +1
    compound = round(0.7 * mom_score + 0.3 * rsi_score, 4)
    compound = max(-1.0, min(1.0, compound))
    label = (
        "VERY_POSITIVE" if compound >= 0.5 else
        "POSITIVE"      if compound >= 0.05 else
        "NEUTRAL"        if compound > -0.05 else
        "NEGATIVE"       if compound > -0.5 else
        "VERY_NEGATIVE"
    )
    return {
        "compound": compound,
        "label": label,
        "count": 0,
        "scores": [],
        "source": "price_action",
        "indicators": {
            "momentum5d": round(mom5, 2),
            "momentum20d": round(mom20, 2),
            "rsi14": round(rsi, 1),
        },
    }
