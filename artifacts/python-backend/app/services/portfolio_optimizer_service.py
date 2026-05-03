"""
Portfolio Optimizer Service — Markowitz mean-variance + CVaR optimization.

Inputs: a list of symbols + per-symbol daily close history.

Outputs:
  • Efficient frontier — sweep of (target return, vol, weights) along the
    convex hull of feasible long-only portfolios.
  • Max-Sharpe portfolio (tangency on the frontier).
  • Min-volatility portfolio.
  • CVaR-optimisation mode — minimise expected shortfall (left-tail) at the
    chosen confidence using historical-simulation returns. Long-only.
  • Suggested rebalance trades (BUY/SELL share counts) to move from current
    weights → target weights at the latest market prices.

The math is the standard mean-variance and Rockafellar-Uryasev CVaR
formulations.  We use scipy.optimize.minimize (SLSQP) so we don't pull in
cvxpy / pyportfolioopt as runtime dependencies.

Naming convention:  this is the project's `pyportfolioopt_wrapper` /
`fortitudo_tech_wrapper` equivalent (per the architecture guidance in the
roadmap doc) — a thin shim that we can swap for an external library later
without touching call sites.
"""
from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# ── Returns helpers ──────────────────────────────────────────────────────────

def _log_returns(closes: list[float]) -> np.ndarray:
    arr = np.array([float(c) for c in closes if c is not None and c > 0], dtype=float)
    if arr.size < 2:
        return np.array([])
    return np.log(arr[1:] / arr[:-1])


def _build_returns_matrix(symbols: list[str],
                          closes_map: dict[str, list[float]]) -> tuple[list[str], np.ndarray]:
    """Return (kept_symbols, T×N returns matrix). Drops symbols with insufficient data."""
    series: list[tuple[str, np.ndarray]] = []
    for s in symbols:
        r = _log_returns(closes_map.get(s, []))
        if r.size >= 30:
            series.append((s, r))
    if not series:
        return [], np.zeros((0, 0))
    min_len = min(r.size for _, r in series)
    kept    = [s for s, _ in series]
    matrix  = np.column_stack([r[-min_len:] for _, r in series])
    return kept, matrix


# ── Mean-variance optimisation (long-only, fully-invested) ───────────────────

def _portfolio_stats(weights: np.ndarray, mu: np.ndarray, cov: np.ndarray,
                     rf: float = 0.0) -> dict:
    ret = float(weights @ mu)            # daily expected return
    var = float(weights @ cov @ weights) # daily variance
    vol = math.sqrt(max(var, 0.0))
    annual_ret = ret * 252
    annual_vol = vol * math.sqrt(252)
    sharpe = ((annual_ret - rf) / annual_vol) if annual_vol > 0 else 0.0
    return {
        "expectedReturn":   round(annual_ret, 6),
        "volatility":       round(annual_vol, 6),
        "sharpe":           round(sharpe, 4),
        "weights":          [round(float(w), 4) for w in weights],
    }


def _solve_min_var(mu: np.ndarray, cov: np.ndarray,
                   target: Optional[float] = None) -> Optional[np.ndarray]:
    """Solve min  wᵀΣw  s.t. Σwᵢ=1, wᵢ≥0, optionally μᵀw = target."""
    from scipy.optimize import minimize  # noqa: PLC0415

    n = len(mu)
    if n == 0:
        return None
    x0 = np.full(n, 1.0 / n)
    bounds = [(0.0, 1.0)] * n
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    if target is not None:
        constraints.append({"type": "eq", "fun": lambda w, t=target: float(w @ mu) - t})

    try:
        res = minimize(
            lambda w: float(w @ cov @ w),
            x0, method="SLSQP",
            bounds=bounds, constraints=constraints,
            options={"maxiter": 250, "ftol": 1e-9, "disp": False},
        )
    except Exception as exc:
        logger.warning("min-var solve failed: %s", exc)
        return None
    if not res.success:
        logger.debug("min-var did not converge: %s", res.message)
    w = np.clip(res.x, 0.0, None)
    s = w.sum()
    return w / s if s > 0 else None


def _solve_max_sharpe(mu: np.ndarray, cov: np.ndarray,
                      rf_daily: float = 0.0) -> Optional[np.ndarray]:
    """Maximise Sharpe by minimising −Sharpe with SLSQP."""
    from scipy.optimize import minimize  # noqa: PLC0415

    n = len(mu)
    if n == 0:
        return None
    x0 = np.full(n, 1.0 / n)
    bounds = [(0.0, 1.0)] * n
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

    def neg_sharpe(w: np.ndarray) -> float:
        ret = float(w @ mu) - rf_daily
        vol = math.sqrt(max(float(w @ cov @ w), 1e-18))
        return -ret / vol if vol > 0 else 1e6

    try:
        res = minimize(
            neg_sharpe, x0, method="SLSQP",
            bounds=bounds, constraints=constraints,
            options={"maxiter": 250, "ftol": 1e-9, "disp": False},
        )
    except Exception as exc:
        logger.warning("max-Sharpe solve failed: %s", exc)
        return None
    w = np.clip(res.x, 0.0, None)
    s = w.sum()
    return w / s if s > 0 else None


# ── CVaR optimisation (Rockafellar-Uryasev historical simulation) ────────────

def _solve_min_cvar(returns: np.ndarray, alpha: float = 0.95) -> Optional[np.ndarray]:
    """
    Minimise CVaR_α of the portfolio loss distribution using historical
    simulation.  Loss_i = −rᵢᵀw.  Following Rockafellar-Uryasev:

        min over (w, ζ, u_i):
            ζ + 1/((1-α) T) Σᵢ uᵢ
        s.t. uᵢ ≥ Loss_i − ζ, uᵢ ≥ 0, Σwⱼ = 1, wⱼ ≥ 0.

    We can fold (ζ, u) into a closed form for any fixed w:
        u_i*(w) = max(Loss_i(w) − ζ, 0), with ζ chosen to be the (α)-quantile
        of losses; the resulting objective equals the empirical CVaR at level α.
    Plug that closed form into scipy.optimize.minimize (SLSQP).
    """
    from scipy.optimize import minimize  # noqa: PLC0415

    T, N = returns.shape
    if T == 0 or N == 0:
        return None

    x0 = np.full(N, 1.0 / N)
    bounds = [(0.0, 1.0)] * N
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

    def empirical_cvar(w: np.ndarray) -> float:
        losses = -(returns @ w)               # shape (T,)
        var = np.quantile(losses, alpha)       # VaRα
        tail = losses[losses >= var]
        return float(tail.mean()) if tail.size > 0 else float(var)

    try:
        res = minimize(
            empirical_cvar, x0, method="SLSQP",
            bounds=bounds, constraints=constraints,
            options={"maxiter": 300, "ftol": 1e-9, "disp": False},
        )
    except Exception as exc:
        logger.warning("min-CVaR solve failed: %s", exc)
        return None
    w = np.clip(res.x, 0.0, None)
    s = w.sum()
    return w / s if s > 0 else None


# ── Frontier ─────────────────────────────────────────────────────────────────

def efficient_frontier(symbols: list[str],
                       closes_map: dict[str, list[float]],
                       points: int = 25,
                       rf_annual: float = 0.07) -> dict:
    """
    Build the efficient frontier + tangency / min-vol portfolios.
    Returns weights expressed in the *kept* symbol order.
    """
    kept, R = _build_returns_matrix(symbols, closes_map)
    if R.size == 0 or len(kept) < 2:
        return {
            "error": "Need at least 2 symbols with ≥30 days of history",
            "symbols": [], "frontier": [],
            "maxSharpe": None, "minVol": None,
        }

    mu  = R.mean(axis=0)              # daily mean
    cov = np.cov(R, rowvar=False)      # daily covariance
    rf_daily = rf_annual / 252.0

    # Min-vol baseline
    w_min = _solve_min_var(mu, cov)
    # Highest-return single asset weight
    high_idx = int(np.argmax(mu))
    target_max = float(mu[high_idx])
    target_min = float(mu @ w_min) if w_min is not None else float(mu.min())

    targets = np.linspace(target_min, target_max, max(2, points))
    frontier = []
    for t in targets:
        w = _solve_min_var(mu, cov, target=t)
        if w is None:
            continue
        stats = _portfolio_stats(w, mu, cov, rf=rf_annual)
        frontier.append(stats)

    w_sharpe = _solve_max_sharpe(mu, cov, rf_daily=rf_daily)

    return {
        "symbols":  kept,
        "frontier": frontier,
        "maxSharpe": _portfolio_stats(w_sharpe, mu, cov, rf=rf_annual) if w_sharpe is not None else None,
        "minVol":    _portfolio_stats(w_min,    mu, cov, rf=rf_annual) if w_min    is not None else None,
        "riskFreeRateAnnual": rf_annual,
        "lookbackDays":  int(R.shape[0] + 1),
    }


def cvar_optimal(symbols: list[str],
                 closes_map: dict[str, list[float]],
                 confidence: float = 0.95,
                 rf_annual: float = 0.07) -> dict:
    """Minimise CVaR_alpha (default 95%) — fat-tail-aware allocation."""
    kept, R = _build_returns_matrix(symbols, closes_map)
    if R.size == 0 or len(kept) < 2:
        return {
            "error": "Need at least 2 symbols with ≥30 days of history",
            "symbols": [],
        }

    mu  = R.mean(axis=0)
    cov = np.cov(R, rowvar=False)
    w   = _solve_min_cvar(R, alpha=confidence)
    if w is None:
        return {"error": "CVaR optimisation did not converge", "symbols": kept}

    # Compute realised CVaR/VaR for the solution
    losses = -(R @ w)
    var_a = float(np.quantile(losses, confidence))
    tail  = losses[losses >= var_a]
    cvar_a = float(tail.mean()) if tail.size else var_a

    stats = _portfolio_stats(w, mu, cov, rf=rf_annual)
    return {
        "symbols":     kept,
        "weights":     stats["weights"],
        "expectedReturn": stats["expectedReturn"],
        "volatility":  stats["volatility"],
        "sharpe":      stats["sharpe"],
        "cvarPct":     round(cvar_a * 100, 4),       # daily
        "varPct":      round(var_a * 100, 4),
        "annualCvarPct": round(cvar_a * math.sqrt(252) * 100, 4),
        "confidence":  confidence,
        "lookbackDays": int(R.shape[0] + 1),
    }


# ── Rebalance trade calculator ───────────────────────────────────────────────

def rebalance_trades(*, target_weights: dict[str, float],
                     current_qty:    dict[str, float],
                     prices:         dict[str, float],
                     equity:         float,
                     min_trade_inr:  float = 100.0) -> list[dict]:
    """
    Compute concrete trades to move current holdings → target weights.

    Args:
      target_weights: symbol → fraction in [0,1]; should sum to ~1.
      current_qty:    symbol → current share count (0 if unheld).
      prices:         symbol → latest market price.
      equity:         total portfolio equity available to deploy (cash + MV).
      min_trade_inr:  ignore trades smaller than this notional.
    """
    trades: list[dict] = []
    universe = sorted(set(target_weights.keys()) | set(current_qty.keys()))
    for sym in universe:
        tw    = float(target_weights.get(sym, 0.0))
        px    = float(prices.get(sym, 0.0))
        cur_q = float(current_qty.get(sym, 0.0))
        if px <= 0:
            continue
        target_value = tw * equity
        target_qty   = target_value / px
        delta_qty    = target_qty - cur_q
        notional     = abs(delta_qty * px)
        if notional < min_trade_inr or abs(delta_qty) < 1e-6:
            continue
        side = "BUY" if delta_qty > 0 else "SELL"
        trades.append({
            "symbol":      sym,
            "side":        side,
            "qty":         round(abs(delta_qty), 4),
            "price":       round(px, 2),
            "notional":    round(notional, 2),
            "currentQty":  round(cur_q, 4),
            "currentWeight": round((cur_q * px / equity) if equity > 0 else 0, 4),
            "targetWeight":  round(tw, 4),
        })
    # BUYs first, SELLs second (sane default for rebalance display)
    trades.sort(key=lambda t: (t["side"] == "SELL", -t["notional"]))
    return trades
