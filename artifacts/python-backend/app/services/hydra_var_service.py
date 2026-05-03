"""
Hydra-Alpha Engine — Value at Risk (VaR) Module
Historical Simulation method:
  - Non-parametric (no normal distribution assumption)
  - Captures fat tails common in equity markets
  - Returns 95% and 99% VaR + Expected Shortfall (CVaR)

Fix applied (code review):
  FIX-3: Re-normalise weights AFTER filtering out symbols with insufficient data.
          Previously, weights were kept for the original symbol list and the
          portfolio return series was effectively under-weight, understating VaR.
          Now only valid symbols contribute and their weights sum to 1.0.
"""
from __future__ import annotations
import logging
import statistics
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def _log_returns(closes: list[float]) -> list[float]:
    """Compute daily log returns, skipping zero/negative prices."""
    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0 and closes[i] > 0:
            returns.append(float(np.log(closes[i] / closes[i - 1])))
    return returns


def sortino_ratio(
    closes: list[float],
    risk_free_rate_annual: float = 0.07,
    target_return_daily: float | None = None,
) -> dict:
    """
    Sortino ratio = (mean_excess_return / downside_deviation) * sqrt(252).

    Unlike Sharpe, Sortino only penalises *downside* volatility (returns
    below the target). Default target = risk-free rate / 252.

    Returns annualised Sortino + supporting components.  None when there is
    insufficient downside data.
    """
    if len(closes) < 30:
        return {"sortino": None, "error": "Need at least 30 days of history"}
    rets = _log_returns(closes)
    if not rets:
        return {"sortino": None, "error": "Could not compute returns"}

    rets_arr = np.array(rets)
    rf_daily = risk_free_rate_annual / 252.0
    target   = rf_daily if target_return_daily is None else float(target_return_daily)

    excess   = rets_arr - target
    downside = excess[excess < 0]
    if downside.size == 0:
        # No drawdowns in the sample — Sortino is undefined (treat as None to
        # avoid pretending the portfolio has infinite risk-adjusted return).
        return {
            "sortino":            None,
            "annualReturn":       round(float(rets_arr.mean()) * 252 * 100, 4),
            "downsideDeviation":  0.0,
            "riskFreeRateAnnual": risk_free_rate_annual,
            "sampleSize":         len(rets),
            "note":               "No downside observations in sample.",
        }

    downside_dev_daily = float(np.sqrt(np.mean(downside ** 2)))
    annual_excess      = float(excess.mean()) * 252
    annual_downside    = downside_dev_daily * np.sqrt(252)
    sortino            = annual_excess / annual_downside if annual_downside > 0 else None

    return {
        "sortino":            round(sortino, 4) if sortino is not None else None,
        "annualReturn":       round(float(rets_arr.mean()) * 252 * 100, 4),
        "downsideDeviation":  round(annual_downside * 100, 4),
        "riskFreeRateAnnual": risk_free_rate_annual,
        "sampleSize":         len(rets),
    }


def max_drawdown(closes: list[float]) -> dict:
    """Return the worst peak-to-trough drawdown over the price series."""
    if len(closes) < 2:
        return {"maxDrawdownPct": 0.0, "peakIndex": 0, "troughIndex": 0}
    arr  = np.array(closes, dtype=float)
    peak = np.maximum.accumulate(arr)
    dd   = (arr - peak) / peak
    trough_idx = int(np.argmin(dd))
    peak_idx   = int(np.argmax(arr[: trough_idx + 1])) if trough_idx > 0 else 0
    return {
        "maxDrawdownPct": round(float(dd.min()) * 100, 4),
        "peakIndex":      peak_idx,
        "troughIndex":    trough_idx,
        "peakPrice":      round(float(arr[peak_idx]), 2),
        "troughPrice":    round(float(arr[trough_idx]), 2),
    }


def sharpe_ratio(
    closes: list[float],
    risk_free_rate_annual: float = 0.07,
) -> dict:
    """Annualised Sharpe ratio = mean_excess_return / volatility * sqrt(252)."""
    if len(closes) < 30:
        return {"sharpe": None, "error": "Need at least 30 days of history"}
    rets = _log_returns(closes)
    if not rets:
        return {"sharpe": None, "error": "Could not compute returns"}
    rets_arr = np.array(rets)
    rf_daily = risk_free_rate_annual / 252.0
    excess   = rets_arr - rf_daily
    vol      = float(np.std(rets_arr))
    sharpe   = (float(excess.mean()) / vol * np.sqrt(252)) if vol > 0 else None
    return {
        "sharpe":             round(sharpe, 4) if sharpe is not None else None,
        "annualReturn":       round(float(rets_arr.mean()) * 252 * 100, 4),
        "annualVolatility":   round(vol * np.sqrt(252) * 100, 4),
        "riskFreeRateAnnual": risk_free_rate_annual,
        "sampleSize":         len(rets),
    }


def historical_var(
    closes: list[float],
    confidence: float = 0.95,
    horizon_days: int = 1,
    portfolio_value: float = 1_000_000.0,
) -> dict:
    """
    Historical simulation VaR for a single asset.
    Returns VaR and CVaR at the given confidence level.
    """
    if len(closes) < 30:
        return {"error": "Need at least 30 days of history"}
    rets = _log_returns(closes)
    if not rets:
        return {"error": "Could not compute returns"}

    rets_arr = np.array(rets)
    if horizon_days > 1:
        rets_arr = rets_arr * np.sqrt(horizon_days)

    pct      = (1 - confidence) * 100
    var_pct  = float(np.percentile(rets_arr, pct))
    cvar_pct = float(rets_arr[rets_arr <= var_pct].mean()) if (rets_arr <= var_pct).any() else var_pct

    return {
        "confidence":      confidence,
        "horizonDays":     horizon_days,
        "varPct":          round(var_pct * 100, 4),
        "cvarPct":         round(cvar_pct * 100, 4),
        "varAbsolute":     round(abs(var_pct) * portfolio_value, 2),
        "cvarAbsolute":    round(abs(cvar_pct) * portfolio_value, 2),
        "portfolioValue":  portfolio_value,
        "sampleSize":      len(rets),
        "dailyVolatility": round(float(np.std(rets_arr)) * 100, 4),
        "annVolatility":   round(float(np.std(rets_arr)) * np.sqrt(252) * 100, 2),
    }


def portfolio_var(
    symbols: list[str],
    closes_map: dict[str, list[float]],
    weights: list[float],
    confidence: float = 0.95,
    horizon_days: int = 1,
    portfolio_value: float = 1_000_000.0,
) -> dict:
    """
    Historical simulation VaR for a portfolio.
    Uses weighted portfolio returns to preserve fat-tail structure.

    FIX-3: weights are re-normalised after dropping symbols without sufficient
    data, so the weighted sum always equals 1.0.
    """
    if len(symbols) != len(weights):
        return {"error": "symbols and weights length mismatch"}

    # ── FIX-3: build valid-symbol / weight pairs FIRST, then normalise ─────────
    paired = [
        (sym, w)
        for sym, w in zip(symbols, weights)
        if len(closes_map.get(sym, [])) >= 30
    ]
    if not paired:
        return {"error": "No sufficient historical data for any symbol"}
    if len(paired) < 2:
        return {"error": "Need at least 2 symbols with ≥30 days of history for portfolio VaR"}

    valid_syms, raw_weights = zip(*paired)
    total_w = sum(raw_weights)
    norm_weights = [w / total_w for w in raw_weights]

    # Build return series — align to minimum common length
    returns_by_sym: dict[str, list[float]] = {
        sym: _log_returns(closes_map[sym]) for sym in valid_syms
    }
    min_len = min(len(r) for r in returns_by_sym.values())

    port_returns = np.zeros(min_len)
    for sym, w in zip(valid_syms, norm_weights):
        r = np.array(returns_by_sym[sym][-min_len:])
        port_returns += w * r

    if horizon_days > 1:
        port_returns = port_returns * np.sqrt(horizon_days)

    pct      = (1 - confidence) * 100
    var_pct  = float(np.percentile(port_returns, pct))
    cvar_pct = float(port_returns[port_returns <= var_pct].mean()) if (port_returns <= var_pct).any() else var_pct

    # Correlation matrix
    matrix = np.array([np.array(returns_by_sym[s][-min_len:]) for s in valid_syms])
    corr   = np.corrcoef(matrix)
    corr_matrix = [
        [round(float(corr[i][j]), 3) for j in range(len(valid_syms))]
        for i in range(len(valid_syms))
    ]

    # Individual VaR breakdown (using normalised weights)
    breakdown = []
    for sym, w in zip(valid_syms, norm_weights):
        individual = historical_var(
            closes_map[sym],
            confidence=confidence,
            horizon_days=horizon_days,
            portfolio_value=portfolio_value * w,
        )
        breakdown.append({"symbol": sym, "weight": round(w, 4), **individual})

    dropped = [s for s in symbols if s not in valid_syms]

    return {
        "portfolioVarPct":   round(var_pct * 100, 4),
        "portfolioCvarPct":  round(cvar_pct * 100, 4),
        "portfolioVarAbs":   round(abs(var_pct) * portfolio_value, 2),
        "portfolioCvarAbs":  round(abs(cvar_pct) * portfolio_value, 2),
        "portfolioValue":    portfolio_value,
        "confidence":        confidence,
        "horizonDays":       horizon_days,
        "sampleSize":        min_len,
        "portfolioVolatility": round(float(np.std(port_returns)) * np.sqrt(252) * 100, 2),
        "symbols":           list(valid_syms),
        "weights":           [round(w, 4) for w in norm_weights],
        "breakdown":         breakdown,
        "correlationMatrix": corr_matrix,
        "droppedSymbols":    dropped,
        "returnDistribution": {
            "p5":  round(float(np.percentile(port_returns,  5)) * 100, 4),
            "p25": round(float(np.percentile(port_returns, 25)) * 100, 4),
            "p50": round(float(np.percentile(port_returns, 50)) * 100, 4),
            "p75": round(float(np.percentile(port_returns, 75)) * 100, 4),
            "p95": round(float(np.percentile(port_returns, 95)) * 100, 4),
        },
    }
