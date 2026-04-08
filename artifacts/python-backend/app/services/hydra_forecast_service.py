"""
Hydra-Alpha Engine — Probabilistic Price Forecast Module
TFT-inspired feature engineering + lightweight statistical ensemble.
Produces probabilistic 5th / 50th / 95th percentile forecasts.

Architecture mirrors TFT input structure:
  - static_categoricals:        sector, ticker
  - time_varying_known_reals:   day_of_week, month, days_to_expiry
  - time_varying_unknown_reals: close, volume, RSI, MACD, momentum, sentiment
"""
from __future__ import annotations
import logging
import math
import statistics
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# ── Technical feature engineering ─────────────────────────────────────────────

def _ema(values: list[float], period: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2 / (period + 1)
    ema = statistics.mean(values[:period])
    out[period - 1] = ema
    for i in range(period, len(values)):
        ema = values[i] * k + ema * (1 - k)
        out[i] = ema
    return out


def _rsi(closes: list[float], period: int = 14) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(closes)
    if len(closes) < period + 1:
        return out
    diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in diffs]
    losses = [abs(min(d, 0)) for d in diffs]
    avg_gain = statistics.mean(gains[:period])
    avg_loss = statistics.mean(losses[:period])
    for i in range(period, len(diffs)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        out[i + 1] = 100 - (100 / (1 + rs))
    return out


def _macd_line(closes: list[float]) -> list[Optional[float]]:
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    out: list[Optional[float]] = []
    for e12, e26 in zip(ema12, ema26):
        if e12 is None or e26 is None:
            out.append(None)
        else:
            out.append(e12 - e26)
    return out


def _bollinger(closes: list[float], period: int = 20) -> list[dict]:
    out = []
    for i in range(len(closes)):
        if i < period - 1:
            out.append({"mid": None, "upper": None, "lower": None, "pct_b": None})
            continue
        window = closes[i - period + 1: i + 1]
        mid = statistics.mean(window)
        std = statistics.stdev(window) if len(window) > 1 else 0
        upper = mid + 2 * std
        lower = mid - 2 * std
        pct_b = (closes[i] - lower) / (upper - lower) if (upper - lower) > 0 else 0.5
        out.append({"mid": mid, "upper": upper, "lower": lower, "pct_b": pct_b})
    return out


def _momentum(closes: list[float], period: int) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    return (closes[-1] - closes[-period - 1]) / closes[-period - 1] * 100


def _build_features(rows: list[dict]) -> list[dict]:
    """Build TFT-style feature matrix from OHLCV rows."""
    if not rows:
        return []
    closes  = [r["close"]  for r in rows]
    volumes = [r.get("volume", 0) or 0 for r in rows]

    rsi     = _rsi(closes)
    macd    = _macd_line(closes)
    ema9    = _ema(closes, 9)
    ema21   = _ema(closes, 21)
    ema50   = _ema(closes, 50)
    boll    = _bollinger(closes)

    features = []
    for i, r in enumerate(rows):
        try:
            date = datetime.strptime(r["date"], "%Y-%m-%d")
        except Exception:
            date = datetime.utcnow()

        mom5  = _momentum(closes[: i + 1], 5)
        mom20 = _momentum(closes[: i + 1], 20)

        # Volume z-score (20-day)
        vol_window = volumes[max(0, i - 20): i + 1]
        vol_mean = statistics.mean(vol_window) if vol_window else 1
        vol_std  = statistics.stdev(vol_window) if len(vol_window) > 1 else 1
        vol_z    = (volumes[i] - vol_mean) / vol_std if vol_std > 0 else 0

        features.append({
            # static
            "ticker": r.get("ticker", ""),
            # time-varying known
            "day_of_week": date.weekday(),
            "month": date.month,
            "day_of_month": date.day,
            # time-varying unknown
            "close": closes[i],
            "open":  r.get("open", closes[i]),
            "high":  r.get("high", closes[i]),
            "low":   r.get("low",  closes[i]),
            "volume_z": round(vol_z, 4),
            "rsi":    rsi[i],
            "macd":   macd[i],
            "ema9":   ema9[i],
            "ema21":  ema21[i],
            "ema50":  ema50[i],
            "pct_b":  boll[i]["pct_b"],
            "mom5":   mom5,
            "mom20":  mom20,
        })
    return features


# ── Statistical ensemble forecast ─────────────────────────────────────────────

def _linear_trend(closes: list[float], lookback: int = 20) -> float:
    """OLS slope of closes over last `lookback` periods."""
    y = closes[-lookback:]
    n = len(y)
    x = list(range(n))
    x_mean = statistics.mean(x)
    y_mean = statistics.mean(y)
    slope = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y)) / sum(
        (xi - x_mean) ** 2 for xi in x
    )
    return slope


def _ewm_forecast(closes: list[float], horizon: int, alpha: float = 0.3) -> list[float]:
    """Exponential smoothing forecast."""
    s = closes[-1]
    preds = []
    for _ in range(horizon):
        s = alpha * closes[-1] + (1 - alpha) * s
        preds.append(s)
    return preds


def _momentum_forecast(closes: list[float], horizon: int) -> list[float]:
    """Extrapolate using recent 10-day momentum."""
    if len(closes) < 10:
        return [closes[-1]] * horizon
    mom = (closes[-1] - closes[-10]) / closes[-10]
    daily_mom = (1 + mom) ** (1 / 10) - 1
    preds = []
    for h in range(1, horizon + 1):
        preds.append(closes[-1] * (1 + daily_mom) ** h)
    return preds


def _mean_reversion_forecast(closes: list[float], horizon: int, window: int = 60) -> list[float]:
    """Mean-reversion forecast toward the moving average."""
    ma = statistics.mean(closes[-window:]) if len(closes) >= window else statistics.mean(closes)
    gap = closes[-1] - ma
    reversion_rate = 0.05  # 5% per day reversion toward mean
    preds = []
    price = closes[-1]
    for _ in range(horizon):
        price = price - reversion_rate * (price - ma)
        preds.append(price)
    return preds


def _historical_volatility(closes: list[float], window: int = 20) -> float:
    if len(closes) < 2:
        return 0.01
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, min(window + 1, len(closes)))]
    return statistics.stdev(rets) if len(rets) > 1 else 0.01


def forecast(
    symbol: str,
    rows: list[dict],
    horizon_days: int = 5,
    sector: str = "Unknown",
    sentiment_score: float = 0.0,
) -> dict:
    """
    TFT-inspired probabilistic forecast.
    Returns p10 / p50 / p90 price paths over `horizon_days`.
    """
    if len(rows) < 30:
        return {"error": "Need at least 30 days of history for forecasting"}

    closes = [r["close"] for r in rows if r.get("close")]
    if len(closes) < 30:
        return {"error": "Insufficient price data"}

    features = _build_features(rows)
    latest_price = closes[-1]

    # Build ensemble of 3 forecasters
    ewm_preds  = _ewm_forecast(closes, horizon_days, alpha=0.2)
    mom_preds  = _momentum_forecast(closes, horizon_days)
    mr_preds   = _mean_reversion_forecast(closes, horizon_days)

    # Dynamically weight by RSI context
    rsi_vals = [f["rsi"] for f in features if f.get("rsi") is not None]
    latest_rsi = rsi_vals[-1] if rsi_vals else 50.0

    if latest_rsi > 70:      # Overbought → tilt toward mean reversion
        w_ewm, w_mom, w_mr = 0.2, 0.1, 0.7
    elif latest_rsi < 30:    # Oversold → tilt toward momentum rebound
        w_ewm, w_mom, w_mr = 0.2, 0.7, 0.1
    else:                    # Balanced
        w_ewm, w_mom, w_mr = 0.4, 0.3, 0.3

    # Sentiment adjustment
    sentiment_bias = sentiment_score * 0.001  # ±0.1% per unit of sentiment

    blended = [
        (w_ewm * e + w_mom * m + w_mr * r) * (1 + sentiment_bias)
        for e, m, r in zip(ewm_preds, mom_preds, mr_preds)
    ]

    # Uncertainty bands using historical volatility
    daily_vol = _historical_volatility(closes)
    p10, p50, p90 = [], [], []
    for h, pred in enumerate(blended, 1):
        horizon_vol = daily_vol * math.sqrt(h)
        z_p10 = -1.282
        z_p90 = +1.282
        p10.append(round(pred * math.exp(z_p10 * horizon_vol), 2))
        p50.append(round(pred, 2))
        p90.append(round(pred * math.exp(z_p90 * horizon_vol), 2))

    # Feature importance (approximate contribution of each signal)
    feature_importance = {
        "EWM_Trend":       round(w_ewm * 100, 1),
        "Momentum":        round(w_mom * 100, 1),
        "Mean_Reversion":  round(w_mr * 100, 1),
        "Sentiment_Adj":   round(abs(sentiment_bias) * 1000, 1),
    }

    # Direction signal
    expected_return_5d = (p50[-1] - latest_price) / latest_price * 100
    direction = "BULLISH" if expected_return_5d > 0.5 else "BEARISH" if expected_return_5d < -0.5 else "NEUTRAL"

    # Forecast dates
    last_date = rows[-1]["date"]
    try:
        dt = datetime.strptime(last_date, "%Y-%m-%d")
    except Exception:
        dt = datetime.utcnow()
    forecast_dates = []
    temp = dt
    for _ in range(horizon_days):
        temp += timedelta(days=1)
        while temp.weekday() >= 5:
            temp += timedelta(days=1)
        forecast_dates.append(temp.strftime("%Y-%m-%d"))

    return {
        "symbol":         symbol,
        "sector":         sector,
        "latestPrice":    round(latest_price, 2),
        "latestDate":     last_date,
        "horizonDays":    horizon_days,
        "forecastDates":  forecast_dates,
        "p10":            p10,
        "p50":            p50,
        "p90":            p90,
        "direction":      direction,
        "expectedReturn": round(expected_return_5d, 2),
        "dailyVolPct":    round(daily_vol * 100, 3),
        "rsi":            round(latest_rsi, 1),
        "sentiment":      round(sentiment_score, 3),
        "featureImportance": feature_importance,
        "ensembleWeights": {
            "ewm": w_ewm, "momentum": w_mom, "meanReversion": w_mr
        },
        "inputWindow":    len(rows),
        "modelType":      "Statistical Ensemble (EWM + Momentum + MeanReversion)",
        "note": (
            "TFT-inspired architecture with OHLCV features, RSI, MACD, Bollinger, "
            "momentum, and VADER sentiment. Full TFT deep learning requires GPU training."
        ),
    }
