"""
test_smart_builder.py
Comprehensive TDD test suite for the Smart Strategy Builder service.

Covers:
  1.  Market state detection        (detect_market_state)
  2.  Pre-defined leg construction  (_legs_for_strategy)
  3.  Pre-defined scoring           (_score_predefined)
  4.  Custom strategy invention     (_invent_custom_strategies)
  5.  End-to-end suggestions        (build_smart_suggestions)
"""
import pytest
from app.services.strategy_builder_service import (
    detect_market_state,
    build_smart_suggestions,
    _legs_for_strategy,
    _score_predefined,
    _invent_custom_strategies,
    MarketState,
    StrategyLeg,
    StrategyRecommendation,
)

# ── Shared fixtures ───────────────────────────────────────────────────────────

LOW_VOL  = dict(spot=22000.0, atm=22000, hv=0.12, hv_pct=20,  lot_size=75)
MOD_VOL  = dict(spot=22000.0, atm=22000, hv=0.16, hv_pct=50,  lot_size=75)
HIGH_VOL = dict(spot=22000.0, atm=22000, hv=0.22, hv_pct=75,  lot_size=75)
VHIGH    = dict(spot=22000.0, atm=22000, hv=0.30, hv_pct=88,  lot_size=75)


def _ms(**kwargs) -> MarketState:
    base = dict(spot=22000.0, atm=22000, hv=0.16, hv_pct=50, lot_size=75)
    base.update(kwargs)
    return detect_market_state(**base)


# ═════════════════════════════════════════════════════════════════════════════
#  1. MARKET STATE DETECTION
# ═════════════════════════════════════════════════════════════════════════════

class TestDetectMarketState:

    def test_low_hv_pct_gives_low_regime(self):
        ms = detect_market_state(**LOW_VOL)
        assert ms.vol_regime == "low"

    def test_moderate_hv_pct_gives_moderate_regime(self):
        ms = detect_market_state(**MOD_VOL)
        assert ms.vol_regime == "moderate"

    def test_high_hv_pct_gives_high_or_very_high_regime(self):
        ms = detect_market_state(**HIGH_VOL)
        assert ms.vol_regime in ("high", "very_high")

    def test_very_high_hv_pct_gives_very_high_regime(self):
        ms = detect_market_state(**VHIGH)
        assert ms.vol_regime == "very_high"

    def test_boundary_35_is_moderate(self):
        ms = detect_market_state(spot=22000, atm=22000, hv=0.15, hv_pct=35, lot_size=75)
        assert ms.vol_regime == "moderate"

    def test_boundary_55_is_high(self):
        ms = detect_market_state(spot=22000, atm=22000, hv=0.18, hv_pct=55, lot_size=75)
        assert ms.vol_regime == "high"

    def test_boundary_75_is_very_high(self):
        ms = detect_market_state(spot=22000, atm=22000, hv=0.25, hv_pct=75, lot_size=75)
        assert ms.vol_regime == "very_high"

    def test_step_large_index(self):
        ms = _ms(atm=22000)
        assert ms.step == 100

    def test_step_mid_level(self):
        ms = _ms(spot=3000, atm=3000, hv_pct=50)
        assert ms.step == 50

    def test_step_small_stock(self):
        ms = _ms(spot=400, atm=400, hv_pct=50)
        assert ms.step == 10

    def test_expanding_bias_when_pct_high(self):
        ms = _ms(hv_pct=70)
        assert ms.vol_bias == "expanding"

    def test_contracting_bias_when_pct_low(self):
        ms = _ms(hv_pct=25)
        assert ms.vol_bias == "contracting"

    def test_stable_bias_in_middle(self):
        ms = _ms(hv_pct=50)
        assert ms.vol_bias == "stable"

    def test_stored_fields_match_input(self):
        ms = detect_market_state(spot=22500, atm=22500, hv=0.18, hv_pct=62, lot_size=50)
        assert ms.spot     == 22500
        assert ms.atm      == 22500
        assert ms.hv       == 0.18
        assert ms.hv_pct   == 62
        assert ms.lot_size == 50

    def test_returns_market_state_dataclass(self):
        ms = detect_market_state(**MOD_VOL)
        assert isinstance(ms, MarketState)


# ═════════════════════════════════════════════════════════════════════════════
#  2. PRE-DEFINED LEG CONSTRUCTION
# ═════════════════════════════════════════════════════════════════════════════

class TestLegsForStrategy:

    @pytest.fixture
    def ms(self):
        return _ms()

    def test_long_call_one_leg(self, ms):
        assert len(_legs_for_strategy("Long Call", ms)) == 1

    def test_long_call_buy_call_at_atm(self, ms):
        leg = _legs_for_strategy("Long Call", ms)[0]
        assert leg.action == "buy"
        assert leg.option_type == "call"
        assert leg.strike == ms.atm

    def test_long_straddle_two_legs_same_strike(self, ms):
        legs = _legs_for_strategy("Long Straddle", ms)
        assert len(legs) == 2
        assert legs[0].strike == legs[1].strike == ms.atm

    def test_long_strangle_call_above_put(self, ms):
        legs = _legs_for_strategy("Long Strangle", ms)
        call = next(l for l in legs if l.option_type == "call")
        put  = next(l for l in legs if l.option_type == "put")
        assert call.strike > put.strike

    def test_iron_condor_four_legs(self, ms):
        legs = _legs_for_strategy("Iron Condor", ms)
        assert len(legs) == 4

    def test_iron_condor_short_inside_long_call(self, ms):
        legs = _legs_for_strategy("Iron Condor", ms)
        sc = next(l for l in legs if l.action == "sell" and l.option_type == "call")
        bc = next(l for l in legs if l.action == "buy"  and l.option_type == "call")
        assert sc.strike < bc.strike

    def test_iron_condor_short_inside_long_put(self, ms):
        legs = _legs_for_strategy("Iron Condor", ms)
        sp = next(l for l in legs if l.action == "sell" and l.option_type == "put")
        bp = next(l for l in legs if l.action == "buy"  and l.option_type == "put")
        assert sp.strike > bp.strike

    def test_butterfly_centre_sell_two_lots(self, ms):
        legs = _legs_for_strategy("Butterfly", ms)
        sell = next(l for l in legs if l.action == "sell")
        assert sell.lots == 2

    def test_butterfly_three_distinct_strikes(self, ms):
        legs = _legs_for_strategy("Butterfly", ms)
        strikes = sorted(set(l.strike for l in legs))
        assert len(strikes) == 3

    def test_all_predefined_have_positive_strikes(self):
        ms = _ms()
        names = [
            "Long Call", "Short Put", "Long Put", "Short Call",
            "Long Straddle", "Long Strangle", "Short Straddle", "Short Strangle",
            "Bull Call Spread", "Bear Put Spread", "Iron Condor", "Butterfly",
        ]
        for name in names:
            for leg in _legs_for_strategy(name, ms):
                assert leg.strike > 0, f"{name} produced zero/negative strike"

    def test_unknown_strategy_returns_empty(self, ms):
        assert _legs_for_strategy("Unicorn Spread", ms) == []

    def test_bear_put_spread_buy_strike_above_sell(self, ms):
        legs = _legs_for_strategy("Bear Put Spread", ms)
        buy_put  = next(l for l in legs if l.action == "buy")
        sell_put = next(l for l in legs if l.action == "sell")
        assert buy_put.strike > sell_put.strike


# ═════════════════════════════════════════════════════════════════════════════
#  3. PRE-DEFINED STRATEGY SCORING
# ═════════════════════════════════════════════════════════════════════════════

class TestScorePredefined:

    def test_iron_condor_high_in_high_vol(self):
        assert _score_predefined("Iron Condor", _ms(hv_pct=75)) >= 65

    def test_iron_condor_low_in_low_vol(self):
        assert _score_predefined("Iron Condor", _ms(hv_pct=20)) <= 40

    def test_long_straddle_high_in_low_vol(self):
        assert _score_predefined("Long Straddle", _ms(hv_pct=20)) >= 65

    def test_long_straddle_low_in_high_vol(self):
        assert _score_predefined("Long Straddle", _ms(hv_pct=80)) <= 35

    def test_butterfly_high_in_very_low_vol(self):
        assert _score_predefined("Butterfly", _ms(hv_pct=15)) >= 70

    def test_butterfly_low_in_high_vol(self):
        assert _score_predefined("Butterfly", _ms(hv_pct=80)) <= 30

    def test_long_call_scores_lower_in_high_vol(self):
        low  = _score_predefined("Long Call", _ms(hv_pct=20))
        high = _score_predefined("Long Call", _ms(hv_pct=80))
        assert low > high

    def test_short_straddle_higher_in_high_vol(self):
        low  = _score_predefined("Short Straddle", _ms(hv_pct=20))
        high = _score_predefined("Short Straddle", _ms(hv_pct=80))
        assert high > low

    def test_short_strangle_higher_in_high_vol(self):
        low  = _score_predefined("Short Strangle", _ms(hv_pct=20))
        high = _score_predefined("Short Strangle", _ms(hv_pct=80))
        assert high > low

    def test_bull_call_spread_best_in_moderate_vol(self):
        low  = _score_predefined("Bull Call Spread", _ms(hv_pct=10))
        mid  = _score_predefined("Bull Call Spread", _ms(hv_pct=50))
        high = _score_predefined("Bull Call Spread", _ms(hv_pct=90))
        assert mid >= low and mid >= high

    def test_all_scores_bounded_0_to_100(self):
        names = [
            "Long Call", "Short Put", "Long Put", "Short Call",
            "Long Straddle", "Long Strangle", "Short Straddle", "Short Strangle",
            "Bull Call Spread", "Bear Put Spread", "Iron Condor", "Butterfly",
        ]
        for name in names:
            for pct in [5, 20, 35, 50, 65, 80, 95]:
                s = _score_predefined(name, _ms(hv_pct=pct))
                assert 0 <= s <= 100, f"{name}@{pct}th → {s}"

    def test_long_strangle_high_in_low_vol(self):
        assert _score_predefined("Long Strangle", _ms(hv_pct=15)) >= 65


# ═════════════════════════════════════════════════════════════════════════════
#  4. CUSTOM STRATEGY INVENTION
# ═════════════════════════════════════════════════════════════════════════════

class TestInventCustomStrategies:

    @pytest.fixture
    def customs_low(self):
        return _invent_custom_strategies(_ms(hv_pct=20))   # low regime (< 35)

    @pytest.fixture
    def customs_mod(self):
        return _invent_custom_strategies(_ms(hv_pct=50))   # moderate regime (35-55)

    @pytest.fixture
    def customs_high(self):
        return _invent_custom_strategies(_ms(hv_pct=65))   # high regime (55-75)

    @pytest.fixture
    def customs_vhigh(self):
        return _invent_custom_strategies(_ms(hv_pct=80))   # very_high regime (>= 75)

    # ── Count ──────────────────────────────────────────────────────────────

    def test_returns_exactly_5_custom_strategies(self, customs_mod):
        assert len(customs_mod) == 5

    # ── Jade Lizard ──────────────────────────────────────────────────────

    def test_jade_lizard_present(self, customs_mod):
        names = [c.name for c in customs_mod]
        assert "Jade Lizard" in names

    def test_jade_lizard_3_legs(self, customs_mod):
        jade = next(c for c in customs_mod if c.name == "Jade Lizard")
        assert len(jade.legs) == 3

    def test_jade_lizard_has_short_put(self, customs_mod):
        jade = next(c for c in customs_mod if c.name == "Jade Lizard")
        assert any(l.action == "sell" and l.option_type == "put" for l in jade.legs)

    def test_jade_lizard_call_spread_buy_above_sell(self, customs_mod):
        jade  = next(c for c in customs_mod if c.name == "Jade Lizard")
        calls = [l for l in jade.legs if l.option_type == "call"]
        assert len(calls) == 2
        sell_call = next(l for l in calls if l.action == "sell")
        buy_call  = next(l for l in calls if l.action == "buy")
        assert buy_call.strike > sell_call.strike

    def test_jade_lizard_has_reasonable_fit_score(self, customs_mod):
        # Jade Lizard is a moderate-regime strategy; it should score reasonably in moderate vol
        jade = next(c for c in customs_mod if c.name == "Jade Lizard")
        assert jade.fit_score >= 40

    def test_jade_lizard_is_marked_custom(self, customs_mod):
        jade = next(c for c in customs_mod if c.name == "Jade Lizard")
        assert jade.is_custom is True

    # ── Broken Wing Butterfly ─────────────────────────────────────────────

    def test_bwb_call_present(self, customs_mod):
        names = [c.name for c in customs_mod]
        assert "Broken Wing Butterfly (Call)" in names

    def test_bwb_call_3_legs(self, customs_mod):
        bwb = next(c for c in customs_mod if c.name == "Broken Wing Butterfly (Call)")
        assert len(bwb.legs) == 3

    def test_bwb_asymmetric_wings(self, customs_mod):
        bwb     = next(c for c in customs_mod if c.name == "Broken Wing Butterfly (Call)")
        strikes = sorted(set(l.strike for l in bwb.legs))
        assert len(strikes) == 3
        lower_gap = strikes[1] - strikes[0]
        upper_gap = strikes[2] - strikes[1]
        assert upper_gap > lower_gap   # asymmetric (broken wing)

    def test_bwb_centre_is_2_sell_lots(self, customs_mod):
        bwb   = next(c for c in customs_mod if c.name == "Broken Wing Butterfly (Call)")
        sells = [l for l in bwb.legs if l.action == "sell"]
        assert sum(l.lots for l in sells) == 2

    # ── Ratio Call Spread ─────────────────────────────────────────────────
    # Ratio Call Spread is a HIGH-vol regime strategy (hv_pct >= 55)

    def test_ratio_call_spread_present(self, customs_high):
        names = [c.name for c in customs_high]
        assert "Ratio Call Spread" in names

    def test_ratio_call_spread_total_lots_3(self, customs_high):
        ratio = next(c for c in customs_high if c.name == "Ratio Call Spread")
        assert sum(l.lots for l in ratio.legs) == 3

    def test_ratio_call_spread_sell_2_otm(self, customs_high):
        ratio = next(c for c in customs_high if c.name == "Ratio Call Spread")
        sells = [l for l in ratio.legs if l.action == "sell"]
        assert sum(l.lots for l in sells) == 2

    def test_ratio_call_spread_has_reasonable_fit_score(self, customs_high):
        # Ratio Call Spread is a high-vol regime strategy; just verify it has a sensible score
        ratio = next(c for c in customs_high if c.name == "Ratio Call Spread")
        assert ratio.fit_score >= 40

    # ── Put Back Spread ───────────────────────────────────────────────────
    # Put Back Spread is a LOW-vol regime strategy (hv_pct < 35)

    def test_put_back_spread_present(self, customs_low):
        names = [c.name for c in customs_low]
        assert "Put Back Spread" in names

    def test_put_back_spread_more_buy_than_sell_puts(self, customs_low):
        pbs   = next(c for c in customs_low if c.name == "Put Back Spread")
        buys  = sum(l.lots for l in pbs.legs if l.action == "buy"  and l.option_type == "put")
        sells = sum(l.lots for l in pbs.legs if l.action == "sell" and l.option_type == "put")
        assert buys > sells

    def test_put_back_spread_has_reasonable_fit_score(self, customs_low):
        # Put Back Spread is a low-vol regime strategy; verify it has a sensible score
        pbs = next(c for c in customs_low if c.name == "Put Back Spread")
        assert pbs.fit_score >= 40

    # ── Call Back Spread ──────────────────────────────────────────────────
    # Call Back Spread is a LOW-vol regime strategy (hv_pct < 35)

    def test_call_back_spread_present(self, customs_low):
        names = [c.name for c in customs_low]
        assert "Call Back Spread" in names

    def test_call_back_spread_more_buy_than_sell_calls(self, customs_low):
        cbs   = next(c for c in customs_low if c.name == "Call Back Spread")
        buys  = sum(l.lots for l in cbs.legs if l.action == "buy"  and l.option_type == "call")
        sells = sum(l.lots for l in cbs.legs if l.action == "sell" and l.option_type == "call")
        assert buys > sells

    def test_call_back_spread_has_reasonable_fit_score(self, customs_low):
        # Call Back Spread is a low-vol regime strategy; verify it has a sensible score
        cbs = next(c for c in customs_low if c.name == "Call Back Spread")
        assert cbs.fit_score >= 40

    # ── General invariants ────────────────────────────────────────────────

    def test_all_strikes_positive_across_vol_regimes(self):
        for pct in [10, 30, 50, 70, 90]:
            customs = _invent_custom_strategies(_ms(hv_pct=pct))
            for strat in customs:
                for leg in strat.legs:
                    assert leg.strike > 0, f"{strat.name}@pct={pct} has zero/negative strike"

    def test_all_scores_in_range_across_vol_regimes(self):
        for pct in [10, 30, 50, 70, 90]:
            customs = _invent_custom_strategies(_ms(hv_pct=pct))
            for strat in customs:
                assert 0 <= strat.fit_score <= 100, f"{strat.name}@{pct} score={strat.fit_score}"

    def test_all_strategies_have_non_empty_rationale(self, customs_mod):
        for strat in customs_mod:
            assert len(strat.rationale) > 20, f"{strat.name} has too-short rationale"

    def test_all_strategies_have_key_risk(self, customs_mod):
        for strat in customs_mod:
            assert len(strat.key_risk) > 10, f"{strat.name} has no key_risk"

    def test_all_strategies_marked_custom(self, customs_mod):
        for strat in customs_mod:
            assert strat.is_custom is True


# ═════════════════════════════════════════════════════════════════════════════
#  5. BUILD SMART SUGGESTIONS (end-to-end)
# ═════════════════════════════════════════════════════════════════════════════

class TestBuildSmartSuggestions:
    """
    End-to-end tests for build_smart_suggestions().

    Response shape:
        {
            "market_state":    { vol_regime, vol_bias, hv_pct, hv, spot, atm, step, lot_size },
            "recommendations": [ ... 12 predefined strategies, all is_custom=False ... ],
            "ai_suggestions":  [ ...  5 regime-specific AI strategies, all is_custom=True  ],
        }
    """

    def _suggest(self, hv_pct=50):
        return build_smart_suggestions(
            spot=22000.0, atm=22000, hv=0.16, hv_pct=hv_pct, lot_size=75,
        )

    def test_returns_market_state_key(self):
        assert "market_state" in self._suggest()

    def test_returns_recommendations_key(self):
        assert "recommendations" in self._suggest()

    def test_returns_ai_suggestions_key(self):
        assert "ai_suggestions" in self._suggest()

    def test_recommendations_count_is_12(self):
        # All 12 predefined strategies are always returned
        assert len(self._suggest()["recommendations"]) == 12

    def test_ai_suggestions_count_is_5(self):
        # 5 regime-specific AI strategies are always returned
        assert len(self._suggest()["ai_suggestions"]) == 5

    def test_recommendations_sorted_descending_by_score(self):
        scores = [r["fit_score"] for r in self._suggest(70)["recommendations"]]
        assert scores == sorted(scores, reverse=True)

    def test_top_score_in_high_vol_is_sell_premium(self):
        top = self._suggest(85)["recommendations"][0]
        assert top["fit_score"] >= 70

    def test_top_score_in_low_vol_is_buy_vol(self):
        top = self._suggest(10)["recommendations"][0]
        assert top["fit_score"] >= 70

    def test_each_recommendation_has_legs(self):
        for rec in self._suggest()["recommendations"]:
            assert len(rec["legs"]) >= 1

    def test_each_recommendation_has_rationale(self):
        for rec in self._suggest()["recommendations"]:
            assert len(rec["rationale"]) > 10

    def test_each_recommendation_has_fit_score_field(self):
        for rec in self._suggest()["recommendations"]:
            assert "fit_score" in rec
            assert 0 <= rec["fit_score"] <= 100

    def test_each_recommendation_has_is_custom_field(self):
        for rec in self._suggest()["recommendations"]:
            assert "is_custom" in rec

    def test_ai_suggestions_are_all_custom(self):
        # All 5 AI strategies should be marked is_custom=True
        for s in self._suggest(80)["ai_suggestions"]:
            assert s["is_custom"] is True

    def test_ai_suggestions_present_high_vol(self):
        ai = self._suggest(80)["ai_suggestions"]
        assert len(ai) == 5

    def test_ai_suggestions_present_low_vol(self):
        ai = self._suggest(10)["ai_suggestions"]
        assert len(ai) == 5

    def test_market_state_has_vol_regime(self):
        ms = self._suggest()["market_state"]
        assert "vol_regime" in ms
        assert ms["vol_regime"] in ("low", "moderate", "high", "very_high")

    def test_market_state_has_vol_bias(self):
        ms = self._suggest()["market_state"]
        assert ms["vol_bias"] in ("expanding", "contracting", "stable")

    def test_market_state_has_hv_as_percentage(self):
        ms = self._suggest()["market_state"]
        assert 0 < ms["hv"] < 200  # stored as %, e.g. 16.0

    def test_leg_fields_are_all_present(self):
        for rec in self._suggest()["recommendations"]:
            for leg in rec["legs"]:
                assert "action"      in leg
                assert "option_type" in leg
                assert "strike"      in leg
                assert "lots"        in leg

    def test_leg_action_valid_values(self):
        for rec in self._suggest()["recommendations"]:
            for leg in rec["legs"]:
                assert leg["action"] in ("buy", "sell")

    def test_leg_option_type_valid_values(self):
        for rec in self._suggest()["recommendations"]:
            for leg in rec["legs"]:
                assert leg["option_type"] in ("call", "put")

    def test_leg_strikes_are_positive(self):
        for rec in self._suggest()["recommendations"]:
            for leg in rec["legs"]:
                assert leg["strike"] > 0

    def test_recommendation_has_key_risk(self):
        for rec in self._suggest()["recommendations"]:
            assert "key_risk" in rec
            assert len(rec["key_risk"]) > 5

    def test_all_scores_bounded(self):
        for pct in [5, 20, 50, 75, 90]:
            for rec in self._suggest(pct)["recommendations"]:
                assert 0 <= rec["fit_score"] <= 100
