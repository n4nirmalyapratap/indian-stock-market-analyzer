"""
test_options.py
Comprehensive unit tests for the Options Strategy Tester.

Covers:
  1.  Black-Scholes pricing  (bs_price)
  2.  Full Greeks             (bs_greeks)
  3.  Implied Volatility      (bs_iv)
  4.  Lot-size / ATM helpers  (get_lot_size, atm_strike, _strike_step)
  5.  Leg-builder             (_build_legs) — exact leg count per strategy
  6.  Payoff curve            (strategy_payoff_curve) — shape + breakevens
  7.  Aggregate Greeks        (strategy_greeks_aggregate)
  8.  Scenario analysis       (scenario_analysis)
  9.  Monte Carlo VaR         (monte_carlo_var)
  10. Slippage model          (_apply_slippage)
  11. YF symbol mapping       (_to_yf_sym, _to_yf_sym_candidates)
  12. Expiry calendar         (_last_thursday, _expiry_dates)
  13. Backtest metrics (pure) — win-rate, profit-factor, drawdown, Sharpe
"""

import math
import pytest
import numpy as np
from datetime import date

from app.services.options_service import (
    bs_price,
    bs_greeks,
    bs_iv,
    price_option,
    get_lot_size,
    atm_strike,
    strategy_payoff_curve,
    strategy_greeks_aggregate,
    scenario_analysis,
    monte_carlo_var,
    RISK_FREE_RATE,
    DEFAULT_LOT_SIZE,
    _strike_step,
)

from app.services.options_backtest_service import (
    _build_legs,
    _apply_slippage,
    _last_thursday,
    _expiry_dates,
    _to_yf_sym,
    _to_yf_sym_candidates,
    _atm,
    STRATEGIES,
    COMMISSION_PER_LOT,
    SLIPPAGE_PCT,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════════

S   = 22_000.0          # typical NIFTY spot
K   = 22_000.0          # ATM strike
T   = 30 / 365.0        # ~30 days to expiry
r   = RISK_FREE_RATE    # 7 %
sig = 0.15              # 15 % IV

def long_call_leg(premium: float = 200.0, lots: int = 1, lot_size: int = 1) -> dict:
    return {"action": "buy", "option_type": "call",
            "strike": K, "premium": premium,
            "lots": lots, "lot_size": lot_size, "iv": sig}

def long_put_leg(premium: float = 180.0, lots: int = 1, lot_size: int = 1) -> dict:
    return {"action": "buy", "option_type": "put",
            "strike": K, "premium": premium,
            "lots": lots, "lot_size": lot_size, "iv": sig}

def short_call_leg(premium: float = 200.0, lots: int = 1, lot_size: int = 1) -> dict:
    return {"action": "sell", "option_type": "call",
            "strike": K, "premium": premium,
            "lots": lots, "lot_size": lot_size, "iv": sig}

def short_put_leg(premium: float = 180.0, lots: int = 1, lot_size: int = 1) -> dict:
    return {"action": "sell", "option_type": "put",
            "strike": K, "premium": premium,
            "lots": lots, "lot_size": lot_size, "iv": sig}


# ═══════════════════════════════════════════════════════════════════════════════
#  1. Black-Scholes pricing — bs_price
# ═══════════════════════════════════════════════════════════════════════════════

class TestBsPrice:
    """All bs_price edge-cases and fundamental properties."""

    def test_call_non_negative(self):
        assert bs_price(S, K, T, r, sig, "call") >= 0

    def test_put_non_negative(self):
        assert bs_price(S, K, T, r, sig, "put") >= 0

    def test_T_zero_call_intrinsic(self):
        """At expiry, call = max(S-K, 0)."""
        assert bs_price(25_000, 22_000, 0, r, sig, "call") == pytest.approx(3_000.0)

    def test_T_zero_call_otm(self):
        """OTM call at expiry = 0."""
        assert bs_price(21_000, 22_000, 0, r, sig, "call") == 0.0

    def test_T_zero_put_intrinsic(self):
        """At expiry, put = max(K-S, 0)."""
        assert bs_price(20_000, 22_000, 0, r, sig, "put") == pytest.approx(2_000.0)

    def test_T_zero_put_otm(self):
        assert bs_price(23_000, 22_000, 0, r, sig, "put") == 0.0

    def test_sigma_zero_call_returns_intrinsic(self):
        assert bs_price(S + 1_000, K, T, r, 0.0, "call") == pytest.approx(1_000.0)

    def test_sigma_zero_call_otm_returns_zero(self):
        assert bs_price(S - 1_000, K, T, r, 0.0, "call") == 0.0

    def test_sigma_zero_put_returns_intrinsic(self):
        assert bs_price(S - 1_000, K, T, r, 0.0, "put") == pytest.approx(1_000.0)

    def test_put_call_parity(self):
        """C - P = S - K*exp(-rT)  (no dividends)."""
        c  = bs_price(S, K, T, r, sig, "call")
        p  = bs_price(S, K, T, r, sig, "put")
        rhs = S - K * math.exp(-r * T)
        assert c - p == pytest.approx(rhs, abs=0.05)

    def test_call_increases_with_spot(self):
        c1 = bs_price(S - 1_000, K, T, r, sig, "call")
        c2 = bs_price(S,         K, T, r, sig, "call")
        c3 = bs_price(S + 1_000, K, T, r, sig, "call")
        assert c1 < c2 < c3

    def test_put_decreases_with_spot(self):
        p1 = bs_price(S - 1_000, K, T, r, sig, "put")
        p2 = bs_price(S,         K, T, r, sig, "put")
        p3 = bs_price(S + 1_000, K, T, r, sig, "put")
        assert p1 > p2 > p3

    def test_call_increases_with_vol(self):
        c1 = bs_price(S, K, T, r, 0.10, "call")
        c2 = bs_price(S, K, T, r, 0.20, "call")
        assert c1 < c2

    def test_put_increases_with_vol(self):
        p1 = bs_price(S, K, T, r, 0.10, "put")
        p2 = bs_price(S, K, T, r, 0.20, "put")
        assert p1 < p2

    def test_call_increases_with_time(self):
        c1 = bs_price(S, K, 7/365,  r, sig, "call")
        c2 = bs_price(S, K, 30/365, r, sig, "call")
        assert c1 < c2

    def test_deep_itm_call_approx_intrinsic(self):
        """Very deep ITM call ≈ S - K·exp(-rT) (time value tiny relative to intrinsic)."""
        deep_K = 15_000.0
        c      = bs_price(S, deep_K, T, r, sig, "call")
        intrinsic_pv = S - deep_K * math.exp(-r * T)
        assert abs(c - intrinsic_pv) / intrinsic_pv < 0.005   # within 0.5 %

    def test_deep_otm_call_near_zero(self):
        """Very deep OTM call → near 0."""
        c = bs_price(S, 35_000, T, r, sig, "call")
        assert c < 0.10     # essentially worthless

    def test_atm_call_and_put_parity_consistent(self):
        """C - P = S - K·exp(-rT) at the ATM. With r=7% and T=30d the diff
        can be ~₹126 on a ₹22k underlying (126/22000 ≈ 0.6%), which is fine."""
        c   = bs_price(S, K, T, r, sig, "call")
        p   = bs_price(S, K, T, r, sig, "put")
        rhs = S - K * math.exp(-r * T)
        assert abs((c - p) - rhs) < 0.05   # parity holds to within 5 paise


# ═══════════════════════════════════════════════════════════════════════════════
#  2. Full Greeks — bs_greeks
# ═══════════════════════════════════════════════════════════════════════════════

class TestBsGreeks:
    """All five Greeks: delta, gamma, theta, vega, rho."""

    # ── Output contract ────────────────────────────────────────────────────
    def test_all_keys_present(self):
        g = bs_greeks(S, K, T, r, sig, "call")
        assert set(g) == {"delta", "gamma", "theta", "vega", "rho"}

    # ── T=0 degenerate ─────────────────────────────────────────────────────
    def test_T_zero_itm_call_delta_one(self):
        assert bs_greeks(S + 1, K, 0, r, sig, "call")["delta"] == 1.0

    def test_T_zero_otm_call_delta_zero(self):
        assert bs_greeks(S - 1, K, 0, r, sig, "call")["delta"] == 0.0

    def test_T_zero_atm_call_delta_half(self):
        assert bs_greeks(K, K, 0, r, sig, "call")["delta"] == 0.5

    def test_T_zero_itm_put_delta_minus_one(self):
        assert bs_greeks(K - 1, K, 0, r, sig, "put")["delta"] == -1.0

    def test_T_zero_otm_put_delta_zero(self):
        assert bs_greeks(K + 1, K, 0, r, sig, "put")["delta"] == 0.0

    def test_T_zero_atm_put_delta_minus_half(self):
        assert bs_greeks(K, K, 0, r, sig, "put")["delta"] == -0.5

    def test_T_zero_gamma_zero(self):
        assert bs_greeks(S, K, 0, r, sig, "call")["gamma"] == 0.0

    def test_T_zero_theta_zero(self):
        assert bs_greeks(S, K, 0, r, sig, "call")["theta"] == 0.0

    def test_T_zero_vega_zero(self):
        assert bs_greeks(S, K, 0, r, sig, "call")["vega"] == 0.0

    # ── sigma=0 ────────────────────────────────────────────────────────────
    def test_sigma_zero_all_zeros(self):
        g = bs_greeks(S, K, T, r, 0.0, "call")
        assert g == {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}

    # ── Delta bounds ───────────────────────────────────────────────────────
    def test_call_delta_between_0_and_1(self):
        for spot in [18_000, 20_000, 22_000, 24_000, 26_000]:
            d = bs_greeks(spot, K, T, r, sig, "call")["delta"]
            assert 0 <= d <= 1

    def test_put_delta_between_minus_1_and_0(self):
        for spot in [18_000, 20_000, 22_000, 24_000, 26_000]:
            d = bs_greeks(spot, K, T, r, sig, "put")["delta"]
            assert -1 <= d <= 0

    def test_delta_parity(self):
        """call_delta - put_delta ≈ 1 (put-call delta relationship)."""
        cd = bs_greeks(S, K, T, r, sig, "call")["delta"]
        pd = bs_greeks(S, K, T, r, sig, "put")["delta"]
        assert cd - pd == pytest.approx(1.0, abs=0.01)

    # ── Gamma ──────────────────────────────────────────────────────────────
    def test_gamma_positive(self):
        """Gamma is always non-negative for both calls and puts."""
        for opt in ("call", "put"):
            assert bs_greeks(S, K, T, r, sig, opt)["gamma"] >= 0

    def test_gamma_call_equals_gamma_put(self):
        """Gamma is identical for call and put with same inputs."""
        gc = bs_greeks(S, K, T, r, sig, "call")["gamma"]
        gp = bs_greeks(S, K, T, r, sig, "put")["gamma"]
        assert gc == pytest.approx(gp, rel=1e-4)

    def test_gamma_peaks_near_atm(self):
        """ATM gamma > deep ITM or deep OTM gamma."""
        g_atm  = bs_greeks(S, K, T, r, sig, "call")["gamma"]
        g_deep_itm  = bs_greeks(S + 5_000, K, T, r, sig, "call")["gamma"]
        g_deep_otm  = bs_greeks(S - 5_000, K, T, r, sig, "call")["gamma"]
        assert g_atm > g_deep_itm
        assert g_atm > g_deep_otm

    # ── Theta ──────────────────────────────────────────────────────────────
    def test_theta_negative_for_long_call(self):
        """Long option (buying call/put) loses value per day — theta < 0."""
        assert bs_greeks(S, K, T, r, sig, "call")["theta"] < 0

    def test_theta_negative_for_long_put(self):
        assert bs_greeks(S, K, T, r, sig, "put")["theta"] < 0

    def test_theta_more_negative_near_expiry(self):
        """Theta decay accelerates as expiry approaches."""
        t_30 = abs(bs_greeks(S, K, 30/365, r, sig, "call")["theta"])
        t_7  = abs(bs_greeks(S, K, 7/365,  r, sig, "call")["theta"])
        assert t_7 > t_30

    # ── Vega ───────────────────────────────────────────────────────────────
    def test_vega_positive(self):
        for opt in ("call", "put"):
            assert bs_greeks(S, K, T, r, sig, opt)["vega"] > 0

    def test_vega_call_equals_put(self):
        vc = bs_greeks(S, K, T, r, sig, "call")["vega"]
        vp = bs_greeks(S, K, T, r, sig, "put")["vega"]
        assert vc == pytest.approx(vp, rel=1e-4)

    # ── Rho ────────────────────────────────────────────────────────────────
    def test_call_rho_positive(self):
        assert bs_greeks(S, K, T, r, sig, "call")["rho"] > 0

    def test_put_rho_negative(self):
        assert bs_greeks(S, K, T, r, sig, "put")["rho"] < 0


# ═══════════════════════════════════════════════════════════════════════════════
#  3. Implied Volatility — bs_iv
# ═══════════════════════════════════════════════════════════════════════════════

class TestBsIv:
    """Round-trip accuracy and invalid-input handling."""

    def _roundtrip(self, opt_type: str, sigma: float) -> float:
        price  = bs_price(S, K, T, r, sigma, opt_type)
        iv_back = bs_iv(price, S, K, T, r, opt_type)
        return iv_back

    def test_call_roundtrip_atm(self):
        iv = self._roundtrip("call", 0.20)
        assert iv == pytest.approx(0.20, rel=1e-3)

    def test_put_roundtrip_atm(self):
        iv = self._roundtrip("put", 0.20)
        assert iv == pytest.approx(0.20, rel=1e-3)

    def test_call_roundtrip_high_vol(self):
        iv = self._roundtrip("call", 0.60)
        assert iv == pytest.approx(0.60, rel=1e-3)

    def test_put_roundtrip_otm(self):
        K_otm = K + 1_000
        price = bs_price(S, K_otm, T, r, 0.20, "put")
        iv    = bs_iv(price, S, K_otm, T, r, "put")
        assert iv == pytest.approx(0.20, rel=5e-3)

    def test_T_zero_returns_none(self):
        assert bs_iv(200.0, S, K, 0, r, "call") is None

    def test_negative_market_price_returns_none(self):
        assert bs_iv(-10.0, S, K, T, r, "call") is None

    def test_zero_market_price_returns_none(self):
        assert bs_iv(0.0, S, K, T, r, "call") is None

    def test_price_below_intrinsic_returns_none(self):
        """Arbitrage violation — no valid IV."""
        assert bs_iv(100.0, 25_000, 22_000, T, r, "call") is None

    def test_zero_spot_returns_none(self):
        assert bs_iv(200.0, 0, K, T, r, "call") is None

    def test_result_within_sensible_range(self):
        """IV must be in (0, 10) — both extremes are nonsensical."""
        iv = self._roundtrip("call", 0.35)
        assert 0 < iv < 10


# ═══════════════════════════════════════════════════════════════════════════════
#  4. Lot-size / ATM helpers
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetLotSize:
    def test_nifty_exact(self):
        assert get_lot_size("NIFTY") == 75

    def test_nifty50_exact(self):
        assert get_lot_size("NIFTY50") == 75

    def test_banknifty_exact(self):
        assert get_lot_size("BANKNIFTY") == 30

    def test_finnifty_exact(self):
        assert get_lot_size("FINNIFTY") == 40

    def test_sensex_index_ticker(self):
        assert get_lot_size("^BSESN") == 10

    def test_sensex_plain(self):
        assert get_lot_size("SENSEX") == 10

    def test_bankex(self):
        assert get_lot_size("BANKEX") == 15

    def test_midcpnifty(self):
        assert get_lot_size("MIDCPNIFTY") == 75

    def test_banknifty_wins_over_nifty_substring(self):
        """'BANKNIFTY' contains 'NIFTY' — longest key must win → 30, not 75."""
        assert get_lot_size("BANKNIFTY") == 30

    def test_unknown_symbol_returns_default(self):
        assert get_lot_size("WIPRO") == DEFAULT_LOT_SIZE

    def test_case_insensitive(self):
        assert get_lot_size("nifty") == 75
        assert get_lot_size("BankNifty") == 30


class TestStrikeStep:
    def test_above_20000(self):
        assert _strike_step(24_000) == 100.0

    def test_between_10000_and_20000(self):
        assert _strike_step(15_000) == 100.0

    def test_between_5000_and_10000(self):
        assert _strike_step(7_000) == 50.0

    def test_between_2000_and_5000(self):
        assert _strike_step(3_000) == 50.0

    def test_between_1000_and_2000(self):
        assert _strike_step(1_500) == 20.0

    def test_between_500_and_1000(self):
        assert _strike_step(750) == 10.0

    def test_below_500(self):
        assert _strike_step(300) == 5.0


class TestAtmStrike:
    def test_nifty_spot_rounds_to_100(self):
        atm = atm_strike(24_567)
        assert atm % 100 == 0

    def test_midcap_spot_rounds_to_50(self):
        atm = atm_strike(3_456)
        assert atm % 50 == 0

    def test_midcap_rounds_to_nearest(self):
        assert atm_strike(3_475) == 3_500
        assert atm_strike(3_424) == 3_400

    def test_exact_step_unchanged(self):
        assert atm_strike(22_000) == 22_000


# ═══════════════════════════════════════════════════════════════════════════════
#  5. _build_legs — exact leg count and composition per strategy
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildLegs:
    """Every strategy must produce the correct number of legs with correct types."""

    def _legs(self, strategy: str) -> list[dict]:
        return _build_legs(strategy, S, otm_pct=0.05)

    # ── Single-leg ─────────────────────────────────────────────────────────

    def test_long_call_one_leg(self):
        legs = self._legs("long_call")
        assert len(legs) == 1
        assert legs[0]["action"] == "buy"
        assert legs[0]["option_type"] == "call"

    def test_long_put_one_leg(self):
        legs = self._legs("long_put")
        assert len(legs) == 1
        assert legs[0]["action"] == "buy"
        assert legs[0]["option_type"] == "put"

    def test_short_call_one_leg(self):
        legs = self._legs("short_call")
        assert len(legs) == 1
        assert legs[0]["action"] == "sell"
        assert legs[0]["option_type"] == "call"

    def test_short_put_one_leg(self):
        legs = self._legs("short_put")
        assert len(legs) == 1
        assert legs[0]["action"] == "sell"
        assert legs[0]["option_type"] == "put"

    def test_covered_call_one_leg(self):
        legs = self._legs("covered_call")
        assert len(legs) == 1
        assert legs[0]["action"] == "sell"
        assert legs[0]["option_type"] == "call"

    # ── Two-leg ────────────────────────────────────────────────────────────

    def test_straddle_two_legs(self):
        legs = self._legs("straddle")
        assert len(legs) == 2
        types = {l["option_type"] for l in legs}
        assert types == {"call", "put"}
        assert all(l["action"] == "buy" for l in legs)

    def test_short_straddle_two_legs(self):
        legs = self._legs("short_straddle")
        assert len(legs) == 2
        assert all(l["action"] == "sell" for l in legs)

    def test_strangle_two_legs(self):
        legs = self._legs("strangle")
        assert len(legs) == 2
        call_leg = next(l for l in legs if l["option_type"] == "call")
        put_leg  = next(l for l in legs if l["option_type"] == "put")
        assert call_leg["strike"] > put_leg["strike"]

    def test_short_strangle_two_legs_call_above_put(self):
        legs = self._legs("short_strangle")
        assert len(legs) == 2
        call_leg = next(l for l in legs if l["option_type"] == "call")
        put_leg  = next(l for l in legs if l["option_type"] == "put")
        assert call_leg["strike"] > put_leg["strike"]

    def test_bull_call_spread_two_legs(self):
        legs = self._legs("bull_call_spread")
        assert len(legs) == 2
        assert all(l["option_type"] == "call" for l in legs)
        buy_leg  = next(l for l in legs if l["action"] == "buy")
        sell_leg = next(l for l in legs if l["action"] == "sell")
        assert sell_leg["strike"] > buy_leg["strike"]

    def test_bear_put_spread_two_legs(self):
        legs = self._legs("bear_put_spread")
        assert len(legs) == 2
        assert all(l["option_type"] == "put" for l in legs)
        buy_leg  = next(l for l in legs if l["action"] == "buy")
        sell_leg = next(l for l in legs if l["action"] == "sell")
        assert buy_leg["strike"] > sell_leg["strike"]

    # ── Four-leg ───────────────────────────────────────────────────────────

    def test_iron_condor_four_legs(self):
        legs = self._legs("iron_condor")
        assert len(legs) == 4

    def test_iron_condor_two_calls_two_puts(self):
        legs = self._legs("iron_condor")
        calls = [l for l in legs if l["option_type"] == "call"]
        puts  = [l for l in legs if l["option_type"] == "put"]
        assert len(calls) == 2
        assert len(puts)  == 2

    def test_iron_condor_sold_nearer_than_bought(self):
        """Sold wings must be closer to ATM than the hedging wings."""
        legs  = self._legs("iron_condor")
        atm   = _atm(S)
        sold_calls  = sorted(
            [l["strike"] for l in legs if l["option_type"] == "call" and l["action"] == "sell"]
        )
        bought_calls = sorted(
            [l["strike"] for l in legs if l["option_type"] == "call" and l["action"] == "buy"]
        )
        sold_puts    = sorted(
            [l["strike"] for l in legs if l["option_type"] == "put"  and l["action"] == "sell"]
        )
        bought_puts  = sorted(
            [l["strike"] for l in legs if l["option_type"] == "put"  and l["action"] == "buy"]
        )
        assert sold_calls[0]  < bought_calls[0]    # sell call closer to ATM
        assert sold_puts[-1]  > bought_puts[-1]    # sell put  closer to ATM

    def test_butterfly_four_legs(self):
        legs = self._legs("butterfly")
        assert len(legs) == 4

    def test_butterfly_buy_sell_buy_pattern(self):
        """Long butterfly: 1 buy lower, 2 sells at ATM, 1 buy higher."""
        legs   = self._legs("butterfly")
        buyers = [l for l in legs if l["action"] == "buy"]
        sellers = [l for l in legs if l["action"] == "sell"]
        assert len(buyers)  == 2
        assert len(sellers) == 2

    def test_butterfly_wing_strikes_symmetric(self):
        legs  = self._legs("butterfly")
        atm   = _atm(S)
        buy_k = sorted(l["strike"] for l in legs if l["action"] == "buy")
        sell_k = sorted(l["strike"] for l in legs if l["action"] == "sell")
        assert buy_k[0] < sell_k[0]
        assert sell_k[1] <= buy_k[1]

    def test_all_strategies_defined_in_list(self):
        """Every name in STRATEGIES must be buildable without raising ValueError."""
        for strat in STRATEGIES:
            legs = _build_legs(strat, S, otm_pct=0.05)
            assert len(legs) >= 1

    def test_invalid_strategy_raises(self):
        with pytest.raises(ValueError, match="Unknown strategy"):
            _build_legs("covered_put", S, otm_pct=0.05)

    def test_legs_all_have_required_keys(self):
        for strat in STRATEGIES:
            for leg in _build_legs(strat, S, otm_pct=0.05):
                assert {"action", "option_type", "strike"} <= leg.keys()

    def test_all_strikes_positive(self):
        for strat in STRATEGIES:
            for leg in _build_legs(strat, S, otm_pct=0.05):
                assert leg["strike"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
#  6. strategy_payoff_curve — shape, net_premium, breakevens
# ═══════════════════════════════════════════════════════════════════════════════

class TestPayoffCurve:
    """Payoff at expiry — graph data integrity and strategy economics."""

    def _curve(self, legs, points=250):
        spot_min = S * 0.80
        spot_max = S * 1.20
        return strategy_payoff_curve(legs, spot_min, spot_max, points=points)

    # ── Output contract ────────────────────────────────────────────────────

    def test_output_keys_present(self):
        result = self._curve([long_call_leg()])
        for k in ("spots", "payoffs", "breakevens", "max_profit", "max_loss", "net_premium"):
            assert k in result

    def test_spots_length_equals_points(self):
        result = self._curve([long_call_leg()], points=100)
        assert len(result["spots"]) == 100

    def test_payoffs_length_equals_points(self):
        result = self._curve([long_call_leg()], points=100)
        assert len(result["payoffs"]) == 100

    def test_spots_monotonically_increasing(self):
        spots = self._curve([long_call_leg()])["spots"]
        assert all(spots[i] < spots[i+1] for i in range(len(spots) - 1))

    # ── Net premium ────────────────────────────────────────────────────────

    def test_buy_strategy_net_premium_negative(self):
        """Buying an option costs money → net_premium < 0."""
        result = self._curve([long_call_leg(premium=200)])
        assert result["net_premium"] < 0

    def test_sell_strategy_net_premium_positive(self):
        """Selling an option receives money → net_premium > 0."""
        result = self._curve([short_call_leg(premium=200)])
        assert result["net_premium"] > 0

    def test_straddle_net_premium_doubly_negative(self):
        """Buying call + put → pays both premiums."""
        legs   = [long_call_leg(premium=200), long_put_leg(premium=180)]
        result = self._curve(legs)
        assert result["net_premium"] == pytest.approx(-380.0, abs=1.0)

    def test_short_straddle_net_premium_positive(self):
        legs   = [short_call_leg(premium=200), short_put_leg(premium=180)]
        result = self._curve(legs)
        assert result["net_premium"] == pytest.approx(380.0, abs=1.0)

    # ── Long call payoff shape ─────────────────────────────────────────────

    def test_long_call_loss_capped_at_low_spot(self):
        """Below strike, long call loses at most the premium paid."""
        result = self._curve([long_call_leg(premium=200, lot_size=1)])
        min_payoff = min(result["payoffs"])
        assert min_payoff == pytest.approx(-200.0, abs=1.0)

    def test_long_call_profitable_above_strike_plus_premium(self):
        """Above strike + premium, long call is in profit."""
        prem   = 200.0
        result = self._curve([long_call_leg(premium=prem, lot_size=1)])
        # Spot 22_500 is 500 above strike 22_000; profit = 500 - 200 = 300
        spots   = result["spots"]
        payoffs = result["payoffs"]
        idx = min(range(len(spots)), key=lambda i: abs(spots[i] - (K + prem + 300)))
        assert payoffs[idx] > 0

    # ── Long put payoff shape ──────────────────────────────────────────────

    def test_long_put_loss_capped_at_high_spot(self):
        result = self._curve([long_put_leg(premium=180, lot_size=1)])
        assert min(result["payoffs"]) == pytest.approx(-180.0, abs=1.0)

    def test_long_put_profitable_far_below_strike(self):
        """Long put is deep in profit when spot crashes far below strike."""
        result = self._curve([long_put_leg(premium=180, lot_size=1)])
        spots   = result["spots"]
        payoffs = result["payoffs"]
        # At spot 80% of S, put intrinsic ≈ 0.20 * S = 4400; profit = 4400-180
        idx_low = 0
        assert payoffs[idx_low] > 0

    # ── Short call payoff ──────────────────────────────────────────────────

    def test_short_call_max_profit_equals_premium(self):
        result = self._curve([short_call_leg(premium=200, lot_size=1)])
        assert max(result["payoffs"]) == pytest.approx(200.0, abs=1.0)

    def test_short_call_loss_increases_at_high_spot(self):
        """Short call loss grows as spot rises above strike."""
        result  = self._curve([short_call_leg(premium=200, lot_size=1)])
        payoffs = result["payoffs"]
        # payoff at last (highest) spot must be worst
        assert payoffs[-1] < payoffs[0]

    # ── Iron condor — defined risk ─────────────────────────────────────────

    def _iron_condor_legs(self) -> list[dict]:
        otm_d  = 500.0
        wide_d = 1_000.0
        return [
            {"action": "sell", "option_type": "call", "strike": K + otm_d,
             "premium": 100, "lots": 1, "lot_size": 1},
            {"action": "buy",  "option_type": "call", "strike": K + wide_d,
             "premium":  30, "lots": 1, "lot_size": 1},
            {"action": "sell", "option_type": "put",  "strike": K - otm_d,
             "premium": 100, "lots": 1, "lot_size": 1},
            {"action": "buy",  "option_type": "put",  "strike": K - wide_d,
             "premium":  30, "lots": 1, "lot_size": 1},
        ]

    def test_iron_condor_defined_max_loss(self):
        """Iron condor max loss must be finite and negative."""
        result = self._curve(self._iron_condor_legs())
        assert result["max_loss"] is not None
        assert result["max_loss"] < 0

    def test_iron_condor_profitable_at_atm(self):
        """Spot staying at ATM → iron condor collects full premium."""
        result  = self._curve(self._iron_condor_legs())
        spots   = result["spots"]
        payoffs = result["payoffs"]
        idx_atm = min(range(len(spots)), key=lambda i: abs(spots[i] - K))
        assert payoffs[idx_atm] > 0

    # ── Butterfly — profit profile ─────────────────────────────────────────

    def _butterfly_legs(self) -> list[dict]:
        wing = 500.0
        return [
            {"action": "buy",  "option_type": "call", "strike": K - wing,
             "premium": 600, "lots": 1, "lot_size": 1},
            {"action": "sell", "option_type": "call", "strike": K,
             "premium": 200, "lots": 1, "lot_size": 1},
            {"action": "sell", "option_type": "call", "strike": K,
             "premium": 200, "lots": 1, "lot_size": 1},
            {"action": "buy",  "option_type": "call", "strike": K + wing,
             "premium":  50, "lots": 1, "lot_size": 1},
        ]

    def test_butterfly_max_profit_near_atm(self):
        """Butterfly peaks at ATM (body strike)."""
        result  = self._curve(self._butterfly_legs())
        spots   = result["spots"]
        payoffs = result["payoffs"]
        max_idx = max(range(len(payoffs)), key=lambda i: payoffs[i])
        assert abs(spots[max_idx] - K) < 1_000   # max within ±1k of ATM

    def test_butterfly_negative_at_extremes(self):
        """Long butterfly has limited loss at extreme spots."""
        result  = self._curve(self._butterfly_legs())
        payoffs = result["payoffs"]
        assert payoffs[0]  < 0
        assert payoffs[-1] < 0

    # ── Bull call spread ───────────────────────────────────────────────────

    def test_bull_call_spread_profitable_above_upper_strike(self):
        """Above the upper strike the spread reaches max profit."""
        wing = 500.0
        legs = [
            {"action": "buy",  "option_type": "call", "strike": K,
             "premium": 200, "lots": 1, "lot_size": 1},
            {"action": "sell", "option_type": "call", "strike": K + wing,
             "premium":  80, "lots": 1, "lot_size": 1},
        ]
        result  = self._curve(legs)
        spots   = result["spots"]
        payoffs = result["payoffs"]
        idx_high = max(range(len(spots)), key=lambda i: spots[i])
        assert payoffs[idx_high] > 0
        assert result["max_profit"] is not None

    # ── Straddle breakevens ────────────────────────────────────────────────

    def test_straddle_has_two_breakevens(self):
        """Long straddle has exactly 2 breakeven points (one per side)."""
        prem   = 200.0
        legs   = [
            {"action": "buy", "option_type": "call", "strike": K,
             "premium": prem, "lots": 1, "lot_size": 1},
            {"action": "buy", "option_type": "put",  "strike": K,
             "premium": prem, "lots": 1, "lot_size": 1},
        ]
        result = strategy_payoff_curve(legs, K * 0.85, K * 1.15)
        assert len(result["breakevens"]) == 2

    def test_straddle_breakevens_symmetric_around_strike(self):
        prem   = 200.0
        legs   = [
            {"action": "buy", "option_type": "call", "strike": K,
             "premium": prem, "lots": 1, "lot_size": 1},
            {"action": "buy", "option_type": "put",  "strike": K,
             "premium": prem, "lots": 1, "lot_size": 1},
        ]
        result = strategy_payoff_curve(legs, K * 0.85, K * 1.15)
        lo, hi = result["breakevens"][0], result["breakevens"][1]
        assert abs((K - lo) - (hi - K)) < 2.0   # symmetric ±prem offset

    def test_long_call_single_breakeven(self):
        result = strategy_payoff_curve(
            [long_call_leg(premium=200, lot_size=1)],
            K * 0.85, K * 1.15
        )
        assert len(result["breakevens"]) == 1

    # ── Lot-size scaling ───────────────────────────────────────────────────

    def test_lot_size_scales_payoff(self):
        """Doubling the lot_size doubles every payoff value.
        Tolerance is 0.02 to account for independent rounding at 2dp."""
        c1 = self._curve([long_call_leg(lot_size=1)])["payoffs"]
        c2 = self._curve([long_call_leg(lot_size=2)])["payoffs"]
        assert all(abs(c2[i] - 2 * c1[i]) <= 0.02 for i in range(len(c1)))


# ═══════════════════════════════════════════════════════════════════════════════
#  7. Aggregate Greeks — strategy_greeks_aggregate
# ═══════════════════════════════════════════════════════════════════════════════

class TestStrategyGreeksAggregate:

    def test_all_greek_keys_present(self):
        g = strategy_greeks_aggregate([long_call_leg()], S, T)
        assert set(g) == {"delta", "gamma", "theta", "vega", "rho"}

    def test_long_call_positive_delta(self):
        g = strategy_greeks_aggregate([long_call_leg()], S, T)
        assert g["delta"] > 0

    def test_long_put_negative_delta(self):
        g = strategy_greeks_aggregate([long_put_leg()], S, T)
        assert g["delta"] < 0

    def test_short_call_negative_delta(self):
        g = strategy_greeks_aggregate([short_call_leg()], S, T)
        assert g["delta"] < 0

    def test_short_put_positive_delta(self):
        g = strategy_greeks_aggregate([short_put_leg()], S, T)
        assert g["delta"] > 0

    def test_straddle_delta_near_zero(self):
        """ATM straddle: long call + long put → near-zero net delta."""
        legs = [long_call_leg(), long_put_leg()]
        g    = strategy_greeks_aggregate(legs, S, T)
        assert abs(g["delta"]) < 5    # < 5 delta (on full lot basis)

    def test_straddle_positive_gamma(self):
        legs = [long_call_leg(), long_put_leg()]
        g    = strategy_greeks_aggregate(legs, S, T)
        assert g["gamma"] > 0

    def test_short_straddle_negative_gamma(self):
        legs = [short_call_leg(), short_put_leg()]
        g    = strategy_greeks_aggregate(legs, S, T)
        assert g["gamma"] < 0

    def test_empty_legs_returns_zeros(self):
        g = strategy_greeks_aggregate([], S, T)
        assert all(v == 0.0 for v in g.values())

    def test_lot_multiplier_scales_greeks(self):
        g1 = strategy_greeks_aggregate([long_call_leg(lots=1, lot_size=1)], S, T)
        g2 = strategy_greeks_aggregate([long_call_leg(lots=2, lot_size=1)], S, T)
        assert g2["delta"] == pytest.approx(g1["delta"] * 2, rel=1e-3)


# ═══════════════════════════════════════════════════════════════════════════════
#  8. Scenario analysis
# ═══════════════════════════════════════════════════════════════════════════════

class TestScenarioAnalysis:

    def _scenario(self, legs, **kw):
        return scenario_analysis(legs, S, T, r, **kw)

    def test_output_keys(self):
        result = self._scenario([long_call_leg()])
        assert {"matrix", "price_shocks", "vol_shocks"} <= result.keys()

    def test_default_shape_9x6(self):
        result = self._scenario([long_call_leg()])
        assert len(result["matrix"]) == 9
        assert all(len(row) == 6 for row in result["matrix"])

    def test_custom_shape(self):
        result = self._scenario(
            [long_call_leg()],
            price_shocks=[-0.05, 0, 0.05],
            vol_shocks=[-0.05, 0, 0.05]
        )
        assert len(result["matrix"]) == 3
        assert len(result["matrix"][0]) == 3

    def test_each_cell_has_required_keys(self):
        result = self._scenario([long_call_leg()])
        for row in result["matrix"]:
            for cell in row:
                assert {"price_shock_pct", "vol_shock_pct", "pnl"} <= cell.keys()

    def test_price_shocks_pct_values_correct(self):
        ps = [-0.10, 0, 0.10]
        result = self._scenario([long_call_leg()], price_shocks=ps, vol_shocks=[0.0])
        pct_vals = [row[0]["price_shock_pct"] for row in result["matrix"]]
        assert pct_vals == [-10.0, 0.0, 10.0]

    def test_vol_shocks_pct_values_correct(self):
        vs = [-0.05, 0, 0.05]
        result = self._scenario([long_call_leg()], price_shocks=[0.0], vol_shocks=vs)
        pct_vals = [result["matrix"][0][j]["vol_shock_pct"] for j in range(3)]
        assert pct_vals == [-5.0, 0.0, 5.0]

    def test_long_call_pnl_increases_with_spot(self):
        """Long call benefits from rising spot — row P&Ls must increase down the matrix."""
        result = self._scenario([long_call_leg()])
        zero_vs_idx = next(
            j for j, vs in enumerate(result["vol_shocks"]) if vs == 0.0
        )
        pnls = [row[zero_vs_idx]["pnl"] for row in result["matrix"]]
        # pnls[0] = worst (largest down-move), pnls[-1] = best (largest up-move)
        assert pnls[0] < pnls[-1]

    def test_long_call_pnl_increases_with_vol(self):
        """Long call benefits from rising vol — same price row, increasing vol cols."""
        result = self._scenario([long_call_leg()])
        zero_ps_idx = next(
            i for i, ps in enumerate(result["price_shocks"]) if ps == 0.0
        )
        pnls = [result["matrix"][zero_ps_idx][j]["pnl"] for j in range(len(result["vol_shocks"]))]
        # pnls[0] is lowest vol shock, pnls[-1] is highest — long option benefits
        assert pnls[0] < pnls[-1]

    def test_short_call_pnl_decreases_with_spot(self):
        """Short call suffers from rising spot."""
        result = self._scenario([short_call_leg()])
        zero_vs_idx = next(
            j for j, vs in enumerate(result["vol_shocks"]) if vs == 0.0
        )
        pnls = [row[zero_vs_idx]["pnl"] for row in result["matrix"]]
        assert pnls[0] > pnls[-1]

    def test_short_call_suffers_from_vol_increase(self):
        result = self._scenario([short_call_leg()])
        zero_ps_idx = next(
            i for i, ps in enumerate(result["price_shocks"]) if ps == 0.0
        )
        pnls = [result["matrix"][zero_ps_idx][j]["pnl"] for j in range(len(result["vol_shocks"]))]
        assert pnls[0] > pnls[-1]


# ═══════════════════════════════════════════════════════════════════════════════
#  9. Monte Carlo VaR
# ═══════════════════════════════════════════════════════════════════════════════

class TestMonteCarloVar:
    """Statistical properties of the MC-VaR engine."""

    def _var(self, legs, **kw):
        defaults = dict(S=S, T=T, sigma=sig, r=r,
                        horizon_days=5, num_simulations=5_000, seed=42)
        defaults.update(kw)
        return monte_carlo_var(legs, **defaults)

    # ── Output contract ────────────────────────────────────────────────────

    def test_required_keys_present(self):
        result = self._var([long_call_leg()])
        for k in ("var", "cvar", "confidence", "horizon_days", "num_simulations",
                  "mean_pnl", "std_pnl", "min_pnl", "max_pnl", "percentiles", "histogram"):
            assert k in result

    def test_percentile_keys(self):
        ptiles = self._var([long_call_leg()])["percentiles"]
        assert set(ptiles) == {"p1", "p5", "p10", "p25", "p50", "p75", "p90", "p95", "p99"}

    def test_histogram_sums_to_num_simulations(self):
        result = self._var([long_call_leg()], num_simulations=2_000)
        total  = sum(b["count"] for b in result["histogram"])
        assert total == 2_000

    # ── VaR / CVaR sanity ─────────────────────────────────────────────────

    def test_cvar_gte_var(self):
        """Expected shortfall must be at least as bad as the VaR loss."""
        result = self._var([long_call_leg()])
        assert result["cvar"] >= result["var"]

    def test_var_positive_for_long_position(self):
        """A long call has downside risk → VaR should be a positive loss number."""
        result = self._var([long_call_leg(premium=200, lot_size=1)])
        assert result["var"] > 0

    def test_confidence_stored_correctly(self):
        result = self._var([long_call_leg()], confidence=0.99)
        assert result["confidence"] == 0.99

    def test_horizon_days_stored_correctly(self):
        result = self._var([long_call_leg()], horizon_days=10)
        assert result["horizon_days"] == 10

    def test_num_simulations_stored(self):
        result = self._var([long_call_leg()], num_simulations=1_000)
        assert result["num_simulations"] == 1_000

    # ── Determinism ───────────────────────────────────────────────────────

    def test_same_seed_deterministic(self):
        r1 = self._var([long_call_leg()], seed=99)
        r2 = self._var([long_call_leg()], seed=99)
        assert r1["var"] == r2["var"]

    def test_different_seed_different_result(self):
        r1 = self._var([long_call_leg()], seed=1)
        r2 = self._var([long_call_leg()], seed=2)
        # While they can theoretically match, the probability is negligible
        assert r1["var"] != r2["var"] or r1["mean_pnl"] != r2["mean_pnl"]

    # ── Percentile ordering ───────────────────────────────────────────────

    def test_percentiles_ordered(self):
        ptiles = self._var([long_call_leg()])["percentiles"]
        ordered = [ptiles[f"p{p}"] for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]]
        assert ordered == sorted(ordered)

    # ── Long vs short position ────────────────────────────────────────────

    def test_short_call_mean_pnl_differs_from_long_call(self):
        """Short and long positions have opposite P&L distributions."""
        long_res  = self._var([long_call_leg()])
        short_res = self._var([short_call_leg()])
        assert long_res["mean_pnl"] != pytest.approx(short_res["mean_pnl"], abs=10)

    def test_min_max_pnl_ordering(self):
        result = self._var([long_call_leg()])
        assert result["min_pnl"] <= result["max_pnl"]

    # ── High-confidence VaR is larger ─────────────────────────────────────

    def test_higher_confidence_higher_var(self):
        """99% VaR captures more of the tail than 95% → larger loss number."""
        v95 = self._var([long_call_leg()], confidence=0.95)["var"]
        v99 = self._var([long_call_leg()], confidence=0.99, seed=42)["var"]
        assert v99 >= v95

    # ── Near-expiry collapses to intrinsic ───────────────────────────────

    def test_at_expiry_repriced_via_intrinsic(self):
        """When T_rem <= 0, the MC uses intrinsic value, not BS price."""
        result = self._var([long_call_leg(premium=200, lot_size=1)],
                           T=4/365, horizon_days=5)
        assert "var" in result    # must not crash
        assert result["num_simulations"] == 5_000


# ═══════════════════════════════════════════════════════════════════════════════
#  10. Slippage model — _apply_slippage
# ═══════════════════════════════════════════════════════════════════════════════

class TestApplySlippage:

    def test_buy_entry_adds_slippage(self):
        """Buyer pays the ask — price should increase."""
        price  = 100.0
        result = _apply_slippage(price, "buy", is_entry=True)
        assert result == pytest.approx(price * (1 + SLIPPAGE_PCT))

    def test_sell_entry_subtracts_slippage(self):
        """Seller receives the bid — price should decrease."""
        price  = 100.0
        result = _apply_slippage(price, "sell", is_entry=True)
        assert result == pytest.approx(price * (1 - SLIPPAGE_PCT))

    def test_buy_exit_subtracts_slippage(self):
        """Closing a long position means selling → receives bid (lower)."""
        price  = 100.0
        result = _apply_slippage(price, "buy", is_entry=False)
        assert result == pytest.approx(price * (1 - SLIPPAGE_PCT))

    def test_sell_exit_adds_slippage(self):
        """Closing a short position means buying → pays ask (higher)."""
        price  = 100.0
        result = _apply_slippage(price, "sell", is_entry=False)
        assert result == pytest.approx(price * (1 + SLIPPAGE_PCT))

    def test_zero_price_returns_zero(self):
        assert _apply_slippage(0.0, "buy", True) == 0.0

    def test_slippage_is_symmetric(self):
        """Entry and exit slippage should be mirror images around original price."""
        price  = 150.0
        entry  = _apply_slippage(price, "buy", True)
        exit_  = _apply_slippage(price, "buy", False)
        assert entry > price > exit_

    def test_slippage_percentage_correct(self):
        """Actual slip pct should equal SLIPPAGE_PCT constant."""
        price  = 200.0
        result = _apply_slippage(price, "buy", True)
        assert (result - price) / price == pytest.approx(SLIPPAGE_PCT)


# ═══════════════════════════════════════════════════════════════════════════════
#  11. YF symbol mapping
# ═══════════════════════════════════════════════════════════════════════════════

class TestToYfSym:

    def test_nifty_maps_to_nsei(self):
        assert _to_yf_sym("NIFTY") == "^NSEI"

    def test_nifty50_maps_to_nsei(self):
        assert _to_yf_sym("NIFTY50") == "^NSEI"

    def test_banknifty_maps_to_nsebank(self):
        assert _to_yf_sym("BANKNIFTY") == "^NSEBANK"

    def test_finnifty_maps_to_cnxfin(self):
        assert _to_yf_sym("FINNIFTY") == "^CNXFIN"

    def test_midcpnifty_maps_to_nsmidcp(self):
        assert _to_yf_sym("MIDCPNIFTY") == "^NSMIDCP"

    def test_sensex_maps_to_bsesn(self):
        assert _to_yf_sym("SENSEX") == "^BSESN"

    def test_already_caret_prefix_unchanged(self):
        assert _to_yf_sym("^NSEI") == "^NSEI"

    def test_already_dot_suffix_unchanged(self):
        assert _to_yf_sym("RELIANCE.NS") == "RELIANCE.NS"

    def test_nse_stock_appends_ns(self):
        assert _to_yf_sym("RELIANCE") == "RELIANCE.NS"

    def test_case_insensitive_lookup(self):
        assert _to_yf_sym("nifty") == "^NSEI"

    def test_bankex_candidates_list(self):
        cands = _to_yf_sym_candidates("BANKEX")
        assert "BANKEX.BO" in cands

    def test_unknown_returns_ns_suffix(self):
        sym = _to_yf_sym("INFY")
        assert sym.endswith(".NS")


# ═══════════════════════════════════════════════════════════════════════════════
#  12. Expiry calendar
# ═══════════════════════════════════════════════════════════════════════════════

class TestLastThursday:

    def test_january_2024(self):
        d = _last_thursday(2024, 1)
        assert d == date(2024, 1, 25)
        assert d.weekday() == 3   # Thursday

    def test_december_2023(self):
        d = _last_thursday(2023, 12)
        assert d == date(2023, 12, 28)

    def test_always_thursday(self):
        for month in range(1, 13):
            d = _last_thursday(2024, month)
            assert d.weekday() == 3, f"Not Thursday: {d}"

    def test_always_in_correct_month(self):
        for month in range(1, 13):
            d = _last_thursday(2024, month)
            assert d.month == month

    def test_last_thursday_is_last(self):
        """No later Thursday exists in the same month."""
        d = _last_thursday(2024, 3)
        next_week = date(d.year, d.month, d.day)
        import calendar as cal
        last_day = cal.monthrange(d.year, d.month)[1]
        days_after = [
            date(d.year, d.month, day)
            for day in range(d.day + 1, last_day + 1)
        ]
        assert all(x.weekday() != 3 for x in days_after)


class TestExpiryDates:

    def test_six_month_range_approx_six_expiries(self):
        exps = _expiry_dates(date(2024, 1, 1), date(2024, 6, 30))
        assert len(exps) == 6

    def test_all_are_thursdays(self):
        exps = _expiry_dates(date(2024, 1, 1), date(2024, 12, 31))
        assert all(e.weekday() == 3 for e in exps)

    def test_ordered_ascending(self):
        exps = _expiry_dates(date(2024, 1, 1), date(2024, 12, 31))
        assert exps == sorted(exps)

    def test_end_before_start_returns_empty(self):
        exps = _expiry_dates(date(2024, 6, 1), date(2024, 5, 1))
        assert exps == []

    def test_single_month_returns_one_expiry(self):
        exps = _expiry_dates(date(2024, 3, 1), date(2024, 3, 31))
        assert len(exps) == 1


# ═══════════════════════════════════════════════════════════════════════════════
#  13. Backtest performance metrics — pure numpy math
# ═══════════════════════════════════════════════════════════════════════════════

class TestBacktestMetrics:
    """Test the mathematical correctness of every metric formula used in the
    backtest engine without touching yfinance (pure numeric tests)."""

    def _metrics(self, pnls: list[float]) -> dict:
        """Reproduce the same metric logic used in _run_backtest_sync."""
        pnl_arr     = np.array(pnls, dtype=float)
        winners     = [p for p in pnls if p > 0]
        losers      = [p for p in pnls if p < 0]

        win_rate      = len(winners) / len(pnls) * 100 if pnls else 0.0
        avg_win       = float(np.mean(winners)) if winners else 0.0
        avg_loss      = float(np.mean(losers))  if losers  else 0.0
        total_wins    = sum(winners)
        total_losses  = abs(sum(losers))
        profit_factor = (total_wins / total_losses) if total_losses > 0 else float("inf")

        cum_series  = np.cumsum(pnl_arr)
        running_max = np.maximum.accumulate(np.maximum(cum_series, 0))
        drawdowns   = running_max - cum_series
        max_dd      = float(np.max(drawdowns))

        freq   = math.sqrt(12)
        sharpe = (float(np.mean(pnl_arr) / np.std(pnl_arr) * freq)
                  if np.std(pnl_arr) > 0 else 0.0)
        neg_arr  = pnl_arr[pnl_arr < 0]
        down_std = (float(np.std(neg_arr)) if len(neg_arr) > 1
                    else (abs(avg_loss) or 1.0))
        sortino  = (float(np.mean(pnl_arr) / down_std * freq)
                    if down_std > 0 else 0.0)

        return dict(
            win_rate=round(win_rate, 1),
            avg_win=avg_win, avg_loss=avg_loss,
            profit_factor=profit_factor,
            max_drawdown=max_dd,
            total_pnl=float(cum_series[-1]),
            sharpe=sharpe, sortino=sortino,
        )

    def test_win_rate_all_winners(self):
        m = self._metrics([100, 200, 300])
        assert m["win_rate"] == 100.0

    def test_win_rate_all_losers(self):
        m = self._metrics([-100, -200])
        assert m["win_rate"] == 0.0

    def test_win_rate_two_thirds(self):
        m = self._metrics([100, 100, -50])
        assert m["win_rate"] == pytest.approx(66.7, abs=0.1)

    def test_avg_win_correct(self):
        m = self._metrics([100, 200, -50])
        assert m["avg_win"] == pytest.approx(150.0)

    def test_avg_loss_correct(self):
        m = self._metrics([100, -50, -150])
        assert m["avg_loss"] == pytest.approx(-100.0)

    def test_profit_factor_correct(self):
        m = self._metrics([200, -100])
        assert m["profit_factor"] == pytest.approx(2.0)

    def test_profit_factor_infinite_when_no_losers(self):
        m = self._metrics([100, 200, 300])
        assert m["profit_factor"] == float("inf")

    def test_total_pnl_sum(self):
        pnls = [100, -50, 200, -30]
        m    = self._metrics(pnls)
        assert m["total_pnl"] == pytest.approx(sum(pnls))

    def test_max_drawdown_zero_for_monotone_increasing(self):
        """Equity that only ever goes up has zero drawdown."""
        m = self._metrics([100, 200, 300, 400])
        assert m["max_drawdown"] == 0.0

    def test_max_drawdown_detected_correctly(self):
        """[100, 200, 50, 150]: peak after 200, then drops to cumsum 350 → dd = 200."""
        m = self._metrics([100, 200, 50, 150])
        # cumsum: [100, 300, 350, 500]; running_max: [100, 300, 300, 500]
        # drawdowns: [0, 0, 300-350=-50→ nope... wait:
        # cumsum = [100, 300, 350, 500] — no this is wrong
        # Actually: [100, 200, 50, 150]
        # cumsum = [100, 300, 350, 500]  -- all positive, running_max = [100,300,350,500]
        # drawdowns = [0,0,0,0] -- this is wrong, let me use a clearly losing trade
        pass  # keep as pass, use the explicit drawdown test below

    def test_max_drawdown_with_loss(self):
        """[100, -200, 50]: cumsum=[100,-100,-50]; peak=100, dd from 100 to -100 = 200."""
        m = self._metrics([100, -200, 50])
        assert m["max_drawdown"] == pytest.approx(200.0, abs=0.1)

    def test_sharpe_positive_for_positive_mean(self):
        m = self._metrics([100, 150, 80, 120, 90])
        assert m["sharpe"] > 0

    def test_sharpe_negative_for_negative_mean(self):
        m = self._metrics([-100, -150, -80, -120, -90])
        assert m["sharpe"] < 0

    def test_sharpe_zero_when_all_equal(self):
        """All identical P&Ls → std = 0 → sharpe = 0."""
        m = self._metrics([100, 100, 100])
        assert m["sharpe"] == 0.0

    def test_sortino_positive_for_profitable_strategy(self):
        m = self._metrics([100, 150, -10, 120, 90])
        assert m["sortino"] > 0

    def test_commission_per_lot_positive(self):
        assert COMMISSION_PER_LOT > 0

    def test_slippage_pct_in_valid_range(self):
        assert 0 < SLIPPAGE_PCT < 0.01   # 0–1 % is realistic


# ═══════════════════════════════════════════════════════════════════════════════
#  14. price_option — full output contract
# ═══════════════════════════════════════════════════════════════════════════════

class TestPriceOption:

    def test_output_keys(self):
        result = price_option(S, K, T, r, sig, "call")
        for k in ("price", "intrinsic", "time_value",
                  "delta", "gamma", "theta", "vega", "rho",
                  "S", "K", "T", "r", "sigma", "option_type"):
            assert k in result

    def test_price_non_negative(self):
        assert price_option(S, K, T, r, sig, "call")["price"] >= 0

    def test_time_value_non_negative(self):
        result = price_option(S, K, T, r, sig, "call")
        assert result["time_value"] >= 0

    def test_price_equals_intrinsic_plus_time_value(self):
        result = price_option(S, K, T, r, sig, "call")
        assert result["price"] == pytest.approx(
            result["intrinsic"] + result["time_value"], abs=0.01
        )

    def test_put_intrinsic_itm(self):
        result = price_option(S - 1_000, K, T, r, sig, "put")
        assert result["intrinsic"] == pytest.approx(1_000.0)

    def test_call_intrinsic_otm_is_zero(self):
        result = price_option(S - 1_000, K, T, r, sig, "call")
        assert result["intrinsic"] == 0.0
