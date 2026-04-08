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
