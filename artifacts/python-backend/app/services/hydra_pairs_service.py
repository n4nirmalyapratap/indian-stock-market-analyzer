"""
Hydra-Alpha Engine — Pairs Trading Expert Agent
Implements:
  1. Systematic pair discovery via Engle-Granger cointegration test
  2. Ornstein-Uhlenbeck process calibration (μ, θ, σ)
  3. Entry/exit signal generation (±2σ spread threshold)
"""
from __future__ import annotations
import logging
import statistics
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# ── OU Process calibration ─────────────────────────────────────────────────────

def calibrate_ou(spread: list[float]) -> dict:
    """
    Fit the discrete OU process to the spread series using OLS.
    dx_t = θ(μ - x_t)dt + σdW_t
    Returns: μ (long-run mean), θ (speed of reversion), σ (volatility),
             half_life (days), z_score (latest normalised spread).
    """
    if len(spread) < 20:
        return {"error": "Insufficient data (need ≥ 20 points)"}

    x = np.array(spread)
    x_lag = x[:-1]
    dx = np.diff(x)

    # OLS: dx = a + b*x_lag
    # FIX-6: guard against near-zero variance in x_lag (degenerate spread)
    x_mean  = x_lag.mean()
    dx_mean = dx.mean()
    denom   = np.sum((x_lag - x_mean) ** 2)
    if denom < 1e-12:
        return {"error": "Spread series has near-zero variance — cannot calibrate OU process"}

    b = np.sum((x_lag - x_mean) * (dx - dx_mean)) / denom
    a = dx_mean - b * x_mean

    theta = -b                            # speed of reversion (should be > 0)
    mu    = a / theta if abs(theta) > 1e-10 else float(x.mean())
    residuals = dx - (a + b * x_lag)
    sigma = float(np.std(residuals))
    # theta <= 0 means non-stationary (explosive/random-walk spread) — not tradeable
    # theta > 0 but very small means extremely slow reversion → cap half_life at 9999
    if theta > 1e-10:
        raw_hl = float(np.log(2) / theta)
        half_life = min(raw_hl, 9999.0)   # cap so JSON serialisation never sees inf
        sigma_eq  = sigma / np.sqrt(2 * theta)
    else:
        half_life = 9999.0                 # non-stationary or negligible reversion
        sigma_eq  = sigma

    # FIX-6: guard z-score when sigma_eq is degenerate
    latest  = float(x[-1])
    z_score = (latest - mu) / sigma_eq if sigma_eq > 1e-10 else 0.0

    return {
        "mu":       round(float(mu), 6),
        "theta":    round(float(theta), 6),
        "sigma":    round(sigma, 6),
        "halfLife": round(half_life, 2),
        "sigmaEq":  round(float(sigma_eq), 6),
        "zScore":   round(z_score, 4),
        "latestSpread": round(latest, 6),
    }


def _compute_spread(closes_a: list[float], closes_b: list[float]) -> tuple[list[float], float]:
    """
    Compute the spread using OLS hedge ratio β: spread = A - β*B
    Returns (spread_series, hedge_ratio).
    """
    n = min(len(closes_a), len(closes_b))
    a = np.array(closes_a[-n:])
    b = np.array(closes_b[-n:])
    # OLS: regress A on B
    b_mean = b.mean()
    a_mean = a.mean()
    denom = float(np.sum((b - b_mean) ** 2))
    # Guard: if closes_b has near-zero variance (constant series) beta is undefined
    if denom < 1e-12:
        beta = 1.0  # safe fallback — treat as 1:1 ratio
    else:
        beta = float(np.sum((b - b_mean) * (a - a_mean)) / denom)
    spread = list(a - beta * b)
    return spread, round(beta, 6)


def _engle_granger_pvalue(closes_a: list[float], closes_b: list[float]) -> float:
    """
    Approximate Engle-Granger cointegration p-value.
    Uses the ADF test on the OLS residuals.
    """
    try:
        from statsmodels.tsa.stattools import coint
        n = min(len(closes_a), len(closes_b))
        a = np.array(closes_a[-n:])
        b = np.array(closes_b[-n:])
        _, pvalue, _ = coint(a, b)
        return float(pvalue)
    except ImportError:
        # Fallback: compute correlation of differenced series (weaker test)
        n = min(len(closes_a), len(closes_b))
        a = np.diff(closes_a[-n:])
        b = np.diff(closes_b[-n:])
        if len(a) < 5 or len(b) < 5:
            return 1.0
        corr = float(np.corrcoef(a, b)[0, 1])
        return 1.0 - abs(corr)
    except Exception:
        return 1.0


def generate_signal(ou: dict, entry_z: float = 2.0, exit_z: float = 0.5) -> dict:
    """
    Generate a trading signal based on the current z-score of the spread.
    Returns: signal (LONG_A_SHORT_B / LONG_B_SHORT_A / HOLD / EXIT), rationale.
    """
    z = ou.get("zScore", 0.0)
    half_life = ou.get("halfLife", float("inf"))

    if half_life > 365:
        return {"signal": "NO_TRADE", "zScore": z,
                "rationale": "Half-life too long (>365 days) — not a practical pair"}

    if z >= entry_z:
        signal = "SHORT_SPREAD"
        rationale = (f"Spread is {z:.2f}σ above mean — sell A, buy B. "
                     f"Expected reversion in ~{ou.get('halfLife',0):.0f} days.")
        strength = min(100, int((z - entry_z) * 40 + 60))
    elif z <= -entry_z:
        signal = "LONG_SPREAD"
        rationale = (f"Spread is {abs(z):.2f}σ below mean — buy A, sell B. "
                     f"Expected reversion in ~{ou.get('halfLife',0):.0f} days.")
        strength = min(100, int((abs(z) - entry_z) * 40 + 60))
    elif abs(z) <= exit_z:
        signal = "EXIT"
        rationale = f"Spread near mean (z={z:.2f}) — close any open positions."
        strength = 80
    else:
        signal = "HOLD"
        rationale = f"Spread at {z:.2f}σ — within noise band, no action."
        strength = 0

    return {
        "signal": signal,
        "zScore": round(z, 4),
        "strength": strength,
        "rationale": rationale,
        "entryThreshold": entry_z,
        "exitThreshold": exit_z,
    }


def analyze_pair(
    symbol_a: str,
    symbol_b: str,
    closes_a: list[float],
    closes_b: list[float],
) -> dict:
    """Full pair analysis: cointegration test → OU calibration → signal."""
    if len(closes_a) < 30 or len(closes_b) < 30:
        return {"error": "Need at least 30 trading days of history for both assets"}

    pvalue = _engle_granger_pvalue(closes_a, closes_b)
    is_cointegrated = pvalue < 0.05

    spread, hedge_ratio = _compute_spread(closes_a, closes_b)
    ou = calibrate_ou(spread)

    if "error" in ou:
        return {"symbolA": symbol_a, "symbolB": symbol_b,
                "cointegrationPValue": round(pvalue, 4),
                "isCointegrated": is_cointegrated, "error": ou["error"]}

    signal = generate_signal(ou)

    # Correlation for informational display
    n = min(len(closes_a), len(closes_b))
    corr = float(np.corrcoef(closes_a[-n:], closes_b[-n:])[0, 1])

    return {
        "symbolA": symbol_a,
        "symbolB": symbol_b,
        "cointegrationPValue": round(pvalue, 4),
        "isCointegrated": is_cointegrated,
        "hedgeRatio": hedge_ratio,
        "correlation": round(corr, 4),
        "ou": ou,
        "signal": signal,
        "spreadSeries": [round(s, 4) for s in spread[-60:]],  # last 60 for chart
        "warning": (
            None if is_cointegrated
            else f"Pair not statistically cointegrated (p={pvalue:.3f} > 0.05). "
                 "Proceed with caution."
        ),
    }


def scan_pairs(
    symbols: list[str],
    history_map: dict[str, list[float]],
    p_threshold: float = 0.05,
    max_pairs: int = 20,
) -> list[dict]:
    """
    Scan all unique pairs in `symbols`, return those with p < p_threshold.
    Applies Bonferroni correction for multiple comparisons.
    """
    n = len(symbols)
    total_tests = n * (n - 1) // 2
    # Bonferroni-corrected threshold
    corrected_threshold = min(p_threshold, 0.05 / max(total_tests, 1))

    results = []
    for i in range(n):
        for j in range(i + 1, n):
            sa, sb = symbols[i], symbols[j]
            ca = history_map.get(sa, [])
            cb = history_map.get(sb, [])
            if len(ca) < 30 or len(cb) < 30:
                continue
            pvalue = _engle_granger_pvalue(ca, cb)
            if pvalue <= p_threshold:
                _, beta = _compute_spread(ca, cb)
                spread, _ = _compute_spread(ca, cb)
                ou = calibrate_ou(spread)
                sig = generate_signal(ou) if "error" not in ou else {"signal": "UNKNOWN"}
                results.append({
                    "symbolA": sa,
                    "symbolB": sb,
                    "pValue": round(pvalue, 4),
                    "passedBonferroni": pvalue <= corrected_threshold,
                    "hedgeRatio": beta,
                    "signal": sig.get("signal", "UNKNOWN"),
                    "zScore": ou.get("zScore", 0.0),
                    "halfLife": ou.get("halfLife", 0.0),
                })
        if len(results) >= max_pairs:
            break

    return sorted(results, key=lambda r: r["pValue"])[:max_pairs]
