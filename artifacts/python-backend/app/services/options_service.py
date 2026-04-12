"""
options_service.py
Core options pricing engine for Indian markets.

Features:
- Black-Scholes European option pricing (correct for NIFTY/BANKNIFTY indices)
- Full Greeks: Delta, Gamma, Theta, Vega, Rho
- Implied Volatility via Newton-Raphson with Brenner-Subrahmanyam initial guess
- Strategy payoff curve at expiry with breakeven detection
- Aggregate strategy Greeks
- Scenario analysis (2D: price shocks × vol shocks)
- Monte Carlo VaR using Geometric Brownian Motion
"""

import math
import logging
from typing import Optional
import numpy as np
from scipy.stats import norm

logger = logging.getLogger("options_service")

# ── Indian market constants ────────────────────────────────────────────────────
RISK_FREE_RATE = 0.07  # 7% India 10-year G-Sec approx

# NSE lot sizes (current as of 2024-25)
LOT_SIZES: dict[str, int] = {
    "NIFTY":       75,
    "NIFTY50":     75,
    "^NSEI":       75,
    "BANKNIFTY":   30,
    "^NSEBANK":    30,
    "FINNIFTY":    65,   # SEBI/HO/MRD/MRD-PoD-2/P/CIR/2024/113 — effective Nov 2024
    "^CNXFIN":     65,   # SEBI/HO/MRD/MRD-PoD-2/P/CIR/2024/113 — effective Nov 2024
    "MIDCPNIFTY":  120,  # SEBI/HO/MRD/MRD-PoD-2/P/CIR/2024/113 — effective Nov 2024
    "^NSMIDCP":    120,  # SEBI/HO/MRD/MRD-PoD-2/P/CIR/2024/113 — effective Nov 2024
    "SENSEX":      10,
    "^BSESN":      10,
    "BANKEX":      15,
    "^BSXN":       15,
    "BANKEX.BO":   15,
}
DEFAULT_LOT_SIZE = 100

# Strike step sizes (NSE rounds strikes to these multiples)
def _strike_step(S: float) -> float:
    """Return the standard strike increment for a given spot price."""
    if S >= 20_000:
        return 100.0
    if S >= 10_000:
        return 100.0
    if S >= 5_000:
        return 50.0
    if S >= 2_000:
        return 50.0
    if S >= 1_000:
        return 20.0
    if S >= 500:
        return 10.0
    return 5.0


def get_lot_size(symbol: str) -> int:
    upper = symbol.upper()
    # Exact match first
    if upper in LOT_SIZES:
        return LOT_SIZES[upper]
    # Substring match — longest key wins to avoid "NIFTY" matching inside "BANKNIFTY"
    matches = [(k, v) for k, v in LOT_SIZES.items() if k in upper]
    if matches:
        return max(matches, key=lambda x: len(x[0]))[1]
    return DEFAULT_LOT_SIZE


def atm_strike(S: float) -> float:
    """Round spot price to nearest ATM strike."""
    step = _strike_step(S)
    return round(S / step) * step


# ── Black-Scholes core ─────────────────────────────────────────────────────────

def _d1_d2(S: float, K: float, T: float, r: float, sigma: float):
    """Compute d1 and d2 for Black-Scholes. T must be > 0."""
    sqrt_t = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    return d1, d2


def bs_price(S: float, K: float, T: float, r: float, sigma: float,
             option_type: str) -> float:
    """
    Black-Scholes European option price.
    Args:
        S:           Current underlying price
        K:           Strike price
        T:           Time to expiry in years (>= 0)
        r:           Risk-free rate (annualised, e.g. 0.07)
        sigma:       Implied/historical volatility (annualised, e.g. 0.20)
        option_type: 'call' or 'put'
    Returns:
        Option price (non-negative)
    """
    if T <= 0:
        return max(0.0, S - K) if option_type == "call" else max(0.0, K - S)
    if sigma <= 0:
        return max(0.0, max(0.0, S - K) if option_type == "call" else max(0.0, K - S))

    d1, d2 = _d1_d2(S, K, T, r, sigma)
    exp_rt = math.exp(-r * T)

    if option_type == "call":
        price = S * norm.cdf(d1) - K * exp_rt * norm.cdf(d2)
    else:
        price = K * exp_rt * norm.cdf(-d2) - S * norm.cdf(-d1)

    return max(0.0, float(price))


def bs_greeks(S: float, K: float, T: float, r: float, sigma: float,
              option_type: str) -> dict:
    """
    Full Black-Scholes Greeks.
    Theta is expressed per calendar day (always negative for long positions).
    Vega is per 1 percentage-point change in IV (divide by 100 from raw).
    Rho is per 1 percentage-point change in r.
    """
    if T <= 0:
        if option_type == "call":
            delta = 1.0 if S > K else (0.5 if S == K else 0.0)
        else:
            delta = -1.0 if S < K else (-0.5 if S == K else 0.0)
        return {"delta": delta, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}

    if sigma <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}

    d1, d2 = _d1_d2(S, K, T, r, sigma)
    nd1_pdf = float(norm.pdf(d1))
    sqrt_t = math.sqrt(T)
    exp_rt = math.exp(-r * T)

    # Delta
    delta = float(norm.cdf(d1)) if option_type == "call" else float(-norm.cdf(-d1))

    # Gamma (identical for calls and puts)
    gamma = nd1_pdf / (S * sigma * sqrt_t)

    # Theta (per calendar day — divide annual theta by 365)
    common_theta = -S * nd1_pdf * sigma / (2.0 * sqrt_t)
    if option_type == "call":
        theta = (common_theta - r * K * exp_rt * float(norm.cdf(d2))) / 365.0
    else:
        theta = (common_theta + r * K * exp_rt * float(norm.cdf(-d2))) / 365.0

    # Vega per 1% IV move (raw vega / 100)
    vega = S * nd1_pdf * sqrt_t / 100.0

    # Rho per 1% rate move
    if option_type == "call":
        rho = K * T * exp_rt * float(norm.cdf(d2)) / 100.0
    else:
        rho = -K * T * exp_rt * float(norm.cdf(-d2)) / 100.0

    return {
        "delta": round(delta, 4),
        "gamma": round(float(gamma), 6),
        "theta": round(float(theta), 4),
        "vega":  round(float(vega), 4),
        "rho":   round(float(rho), 4),
    }


def bs_iv(market_price: float, S: float, K: float, T: float, r: float,
          option_type: str, tol: float = 1e-5, max_iter: int = 200) -> Optional[float]:
    """
    Implied Volatility via Newton-Raphson with Brenner-Subrahmanyam seed.
    Returns IV in decimal (0.20 = 20%) or None if not converged / invalid.
    """
    if T <= 0 or market_price <= 0 or S <= 0 or K <= 0:
        return None

    intrinsic = max(0.0, S - K) if option_type == "call" else max(0.0, K - S)
    if market_price < intrinsic - 1e-6:
        return None  # price below intrinsic — arbitrage; skip

    # Brenner-Subrahmanyam ATM approximation as starting guess
    sigma = math.sqrt(2.0 * math.pi / T) * market_price / S
    sigma = max(0.01, min(sigma, 10.0))

    for _ in range(max_iter):
        price = bs_price(S, K, T, r, sigma, option_type)
        vega_raw = bs_greeks(S, K, T, r, sigma, option_type)["vega"] * 100.0  # per-unit vega
        if abs(vega_raw) < 1e-10:
            break
        sigma_new = sigma - (price - market_price) / vega_raw
        sigma_new = max(0.001, min(sigma_new, 10.0))
        if abs(sigma_new - sigma) < tol:
            return round(sigma_new, 6)
        sigma = sigma_new

    return round(sigma, 6) if 0 < sigma < 10 else None


# ── Single-option pricing ─────────────────────────────────────────────────────

def price_option(S: float, K: float, T: float, r: float, sigma: float,
                 option_type: str) -> dict:
    """
    Price a single European option and return price + full Greeks.
    """
    price   = bs_price(S, K, T, r, sigma, option_type)
    greeks  = bs_greeks(S, K, T, r, sigma, option_type)
    intrinsic = max(0.0, S - K) if option_type == "call" else max(0.0, K - S)
    time_value = max(0.0, price - intrinsic)

    return {
        "price":       round(price, 2),
        "intrinsic":   round(intrinsic, 2),
        "time_value":  round(time_value, 2),
        **greeks,
        "S": S, "K": K, "T": round(T, 6), "r": r, "sigma": sigma,
        "option_type": option_type,
    }


# ── Strategy analysis ─────────────────────────────────────────────────────────

def strategy_payoff_curve(legs: list[dict],
                          spot_min: float,
                          spot_max: float,
                          points: int = 250,
                          r: float = RISK_FREE_RATE,
                          sigma: float = 0.20) -> dict:
    """
    Payoff at expiry across a range of spot prices.

    Each leg dict requires:
        action:      'buy' | 'sell'
        option_type: 'call' | 'put'
        strike:      float
        premium:     float  (price paid/received per unit when entering)
        lots:        int    (number of lots)
        lot_size:    int    (units per lot)

    Optional per-leg field:
        residual_dte: int — for time-spread far legs.  When set, payoff at the
                            short leg's expiry uses the Black-Scholes residual
                            value (residual_dte days remaining) instead of
                            intrinsic value.  This produces the correct tent-
                            shaped payoff for Calendar Spreads / Strangles.
        iv:          float — leg-specific IV used for residual BS pricing.

    Returns:
        spots:      List[float] — x-axis values
        payoffs:    List[float] — net P&L in INR at each spot
        breakevens: List[float] — approximate spot levels where P&L = 0
        max_profit: float | None (None if theoretically unlimited)
        max_loss:   float | None (None if theoretically unlimited)
        net_premium: float — total premium paid (<0) or received (>0)
    """
    spots    = list(np.linspace(spot_min, spot_max, points))
    payoffs  = []
    net_prem = 0.0

    for leg in legs:
        K        = float(leg["strike"])
        prem     = float(leg["premium"])
        lots     = int(leg.get("lots", 1))
        lot_size = int(leg.get("lot_size", 1))
        action   = leg["action"]   # 'buy' | 'sell'
        qty      = lots * lot_size
        # buy = pay premium (negative cash flow); sell = receive (positive)
        sign     = -1 if action == "buy" else 1
        net_prem += sign * prem * qty

    for S in spots:
        total = 0.0
        for leg in legs:
            K           = float(leg["strike"])
            prem        = float(leg["premium"])
            lots        = int(leg.get("lots", 1))
            lot_size    = int(leg.get("lot_size", 1))
            opt_type    = leg["option_type"]
            action      = leg["action"]
            qty         = lots * lot_size
            res_dte     = leg.get("residual_dte")   # None for normal legs
            leg_iv      = float(leg.get("iv") or sigma)

            if res_dte and res_dte > 0:
                # Time-spread far leg: use BS residual value at the short leg's expiry
                # rather than intrinsic, so Calendar Spreads show the characteristic
                # tent-shaped payoff instead of a flat zero line.
                T_residual = res_dte / 365.0
                value_at_expiry = bs_price(S, K, T_residual, r, leg_iv, opt_type)
            else:
                value_at_expiry = max(0.0, S - K) if opt_type == "call" else max(0.0, K - S)

            if action == "buy":
                leg_pnl = (value_at_expiry - prem) * qty
            else:
                leg_pnl = (prem - value_at_expiry) * qty
            total += leg_pnl
        payoffs.append(round(total, 2))

    # Breakeven detection (zero crossings via linear interpolation)
    breakevens: list[float] = []
    for i in range(len(payoffs) - 1):
        p0, p1 = payoffs[i], payoffs[i + 1]
        if p0 == 0.0:
            breakevens.append(round(spots[i], 2))
        elif p0 * p1 < 0:
            frac = -p0 / (p1 - p0)
            be   = spots[i] + frac * (spots[i + 1] - spots[i])
            breakevens.append(round(be, 2))

    # Deduplicate breakevens that are very close to each other
    unique_bes: list[float] = []
    for be in breakevens:
        if not unique_bes or abs(be - unique_bes[-1]) > (spot_max - spot_min) * 0.005:
            unique_bes.append(be)

    raw_max = max(payoffs)
    raw_min = min(payoffs)
    UNLIMITED = 1e9  # treat values beyond this as "unlimited"

    return {
        "spots":       [round(s, 2) for s in spots],
        "payoffs":     payoffs,
        "breakevens":  unique_bes,
        "max_profit":  None if raw_max > UNLIMITED else round(raw_max, 2),
        "max_loss":    None if raw_min < -UNLIMITED else round(raw_min, 2),
        "net_premium": round(net_prem, 2),
    }


def strategy_greeks_aggregate(legs: list[dict], S: float, T: float,
                               r: float = RISK_FREE_RATE) -> dict:
    """
    Net (portfolio-level) Greeks for a multi-leg strategy.
    Each leg needs: action, option_type, strike, iv (or sigma), lots, lot_size.
    """
    net = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}

    for leg in legs:
        sigma  = float(leg.get("iv", leg.get("sigma", 0.20)))
        K      = float(leg["strike"])
        lots   = int(leg.get("lots", 1))
        ls     = int(leg.get("lot_size", 1))
        qty    = lots * ls
        sign   = 1 if leg["action"] == "buy" else -1
        greeks = bs_greeks(S, K, T, r, sigma, leg["option_type"])
        for g in net:
            net[g] += sign * greeks[g] * qty

    return {k: round(v, 4) for k, v in net.items()}


# ── Scenario analysis ─────────────────────────────────────────────────────────

def scenario_analysis(legs: list[dict],
                      S: float,
                      T: float,
                      r: float = RISK_FREE_RATE,
                      price_shocks: Optional[list[float]] = None,
                      vol_shocks:   Optional[list[float]] = None) -> dict:
    """
    2-D scenario matrix: each cell shows estimated P&L under a
    combined price shock (% move in underlying) and vol shock (absolute ΔIV).

    price_shocks: e.g. [-0.15, -0.10, -0.05, 0, 0.05, 0.10, 0.15]
    vol_shocks:   e.g. [-0.10, -0.05,  0, 0.05, 0.10, 0.20]

    Returns a matrix[row=price_shock][col=vol_shock] of P&L floats.
    """
    if price_shocks is None:
        price_shocks = [-0.15, -0.10, -0.05, -0.02, 0, 0.02, 0.05, 0.10, 0.15]
    if vol_shocks is None:
        vol_shocks   = [-0.10, -0.05, 0, 0.05, 0.10, 0.20]

    matrix: list[list[dict]] = []

    for ps in price_shocks:
        row: list[dict] = []
        new_S = S * (1.0 + ps)
        for vs in vol_shocks:
            total = 0.0
            for leg in legs:
                base_sigma = float(leg.get("iv", leg.get("sigma", 0.20)))
                new_sigma  = max(0.01, base_sigma + vs)
                K          = float(leg["strike"])
                prem       = float(leg["premium"])
                lots       = int(leg.get("lots", 1))
                ls         = int(leg.get("lot_size", 1))
                qty        = lots * ls
                opt_type   = leg["option_type"]
                action     = leg["action"]

                new_price = bs_price(new_S, K, T, r, new_sigma, opt_type)
                if action == "buy":
                    leg_pnl = (new_price - prem) * qty
                else:
                    leg_pnl = (prem - new_price) * qty
                total += leg_pnl

            row.append({
                "price_shock_pct": round(ps * 100, 1),
                "vol_shock_pct":   round(vs * 100, 1),
                "pnl":             round(total, 2),
            })
        matrix.append(row)

    return {
        "matrix":        matrix,
        "price_shocks":  [round(ps * 100, 1) for ps in price_shocks],
        "vol_shocks":    [round(vs * 100, 1) for vs in vol_shocks],
    }


# ── Monte Carlo Value at Risk ─────────────────────────────────────────────────

def monte_carlo_var(legs: list[dict],
                    S: float,
                    T: float,
                    sigma: float,
                    r: float = RISK_FREE_RATE,
                    horizon_days: int = 5,
                    num_simulations: int = 10_000,
                    confidence: float = 0.95,
                    seed: int = 42) -> dict:
    """
    Monte Carlo Value at Risk for an options portfolio.

    Uses Geometric Brownian Motion to simulate `num_simulations` spot price
    paths over `horizon_days` trading days, re-prices every leg at the
    resulting spot and reduced time-to-expiry, then reports the loss at
    the (1 - confidence) percentile.

    Returns:
        var:             Positive number — loss not exceeded with `confidence`
        cvar (ES):       Expected loss beyond VaR (average tail loss)
        histogram:       [{midpoint, count}] for plotting P&L distribution
        percentiles:     {p1, p5, p10, p25, p50, p75, p90, p95, p99}
    """
    dt     = horizon_days / 252.0      # fraction of a trading year
    T_rem  = max(0.0, T - dt)          # time remaining after horizon

    rng = np.random.default_rng(seed)
    z   = rng.standard_normal(num_simulations)

    # GBM: S_T = S * exp((r - 0.5σ²)dt + σ√dt·Z)
    drift          = (r - 0.5 * sigma ** 2) * dt
    diffusion      = sigma * math.sqrt(dt) * z
    simulated_spots = S * np.exp(drift + diffusion)

    pnls = np.zeros(num_simulations)

    for leg in legs:
        base_sigma = float(leg.get("iv", leg.get("sigma", sigma)))
        K          = float(leg["strike"])
        prem       = float(leg["premium"])
        lots       = int(leg.get("lots", 1))
        ls         = int(leg.get("lot_size", 1))
        qty        = lots * ls
        opt_type   = leg["option_type"]
        action     = leg["action"]

        if T_rem <= 0:
            # At expiry: use intrinsic value
            if opt_type == "call":
                new_prices = np.maximum(0.0, simulated_spots - K)
            else:
                new_prices = np.maximum(0.0, K - simulated_spots)
        else:
            # Re-price using Black-Scholes vectorised via scipy
            sqrt_t = math.sqrt(T_rem)
            safe_spots = np.maximum(simulated_spots, 1e-6)
            log_sk = np.log(safe_spots / K)
            d1 = (log_sk + (r + 0.5 * base_sigma ** 2) * T_rem) / (base_sigma * sqrt_t)
            d2 = d1 - base_sigma * sqrt_t
            exp_rt = math.exp(-r * T_rem)
            if opt_type == "call":
                new_prices = np.maximum(
                    0.0,
                    safe_spots * norm.cdf(d1) - K * exp_rt * norm.cdf(d2)
                )
            else:
                new_prices = np.maximum(
                    0.0,
                    K * exp_rt * norm.cdf(-d2) - safe_spots * norm.cdf(-d1)
                )

        if action == "buy":
            pnls += (new_prices - prem) * qty
        else:
            pnls += (prem - new_prices) * qty

    # VaR and CVaR
    sorted_pnls    = np.sort(pnls)
    tail_idx       = int(np.floor((1.0 - confidence) * num_simulations))
    tail_idx       = max(1, min(tail_idx, num_simulations - 1))
    var_value      = float(-sorted_pnls[tail_idx])        # positive loss
    cvar_value     = float(-np.mean(sorted_pnls[:tail_idx]))  # expected shortfall

    # Histogram for chart
    counts, edges  = np.histogram(pnls, bins=60)
    histogram      = [
        {"midpoint": round(float((edges[i] + edges[i + 1]) / 2), 2),
         "count":    int(counts[i])}
        for i in range(len(counts))
    ]

    # P&L distribution percentiles
    ptiles = {f"p{p}": round(float(np.percentile(pnls, p)), 2)
              for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]}

    return {
        "var":              round(var_value, 2),
        "cvar":             round(cvar_value, 2),
        "confidence":       confidence,
        "horizon_days":     horizon_days,
        "num_simulations":  num_simulations,
        "mean_pnl":         round(float(np.mean(pnls)), 2),
        "std_pnl":          round(float(np.std(pnls)), 2),
        "min_pnl":          round(float(np.min(pnls)), 2),
        "max_pnl":          round(float(np.max(pnls)), 2),
        "percentiles":      ptiles,
        "histogram":        histogram,
    }
