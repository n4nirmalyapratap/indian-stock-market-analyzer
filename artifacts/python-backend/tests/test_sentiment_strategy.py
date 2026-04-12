"""
test_sentiment_strategy.py
==========================
Unit tests for _strategy_table() in market_sentiment_engine.py.

Core invariant being tested:
  Iron Condor is a PREMIUM-SELLING strategy.  It should ONLY be recommended
  when India VIX ≥ 22 (high implied volatility = fat premiums).
  Recommending it in low/moderate-vol environments contradicts the Options
  Strategy Tester, which correctly scores Iron Condor as "Avoid" when
  HV-percentile < 40.

Test matrix:
  composite | vix   | expected scenario
  ──────────┼───────┼─────────────────────────────────────────────────
  ≥ +30     | < 22  | Bullish low/mod vol
  ≥ +30     | ≥ 22  | Bullish high vol
  ≤ -30     | < 22  | Bearish low/mod vol
  ≤ -30     | ≥ 22  | Bearish high vol
  neutral   | < 16  | Neutral low vol
  neutral   | 16-22 | Neutral moderate vol
  neutral   | ≥ 22  | Neutral high vol  ← only case Iron Condor is valid
"""
import pytest
from app.services.market_sentiment_engine import _strategy_table


# ── helpers ──────────────────────────────────────────────────────────────────

def strategy_names(composite: float, vix: float) -> list[str]:
    return [r["strategy"] for r in _strategy_table(composite, vix)]


def all_keys_present(composite: float, vix: float) -> bool:
    """Every row must have strategy, outlook, vol, risk keys."""
    rows = _strategy_table(composite, vix)
    required = {"strategy", "outlook", "vol", "risk"}
    return all(required <= row.keys() for row in rows)


# ── Iron Condor placement — the primary invariant ─────────────────────────────

class TestIronCondorPlacement:
    """Iron Condor must appear ONLY in the high-vol neutral quadrant."""

    # Cases where Iron Condor must NOT appear
    @pytest.mark.parametrize("composite,vix,label", [
        (  0,  12, "neutral + low vol (VIX=12)"),
        (  0,  14, "neutral + low vol (VIX=14)"),
        (  0,  15.9,"neutral + low vol (VIX=15.9)"),
        (  0,  18, "neutral + moderate vol (VIX=18)"),
        (  0,  20, "neutral + moderate vol (VIX=20)"),
        (  0,  21, "neutral + moderate vol (VIX=21)"),
        ( 50,  18, "bullish + moderate vol"),
        ( 50,  12, "bullish + low vol"),
        ( 50,  25, "bullish + high vol"),
        (-50,  18, "bearish + moderate vol"),
        (-50,  12, "bearish + low vol"),
        (-50,  25, "bearish + high vol"),
        ( 10,  18, "near-neutral + moderate vol"),
        (-10,  14, "near-neutral + low vol"),
    ])
    def test_iron_condor_absent(self, composite, vix, label):
        names = strategy_names(composite, vix)
        assert "Iron Condor" not in names, (
            f"Iron Condor incorrectly recommended for {label} "
            f"(composite={composite}, vix={vix}). "
            f"Got: {names}"
        )

    # Cases where Iron Condor MUST appear
    @pytest.mark.parametrize("composite,vix,label", [
        (  0, 22,   "neutral + high vol boundary (VIX=22)"),
        (  0, 25,   "neutral + high vol (VIX=25)"),
        (  0, 30,   "neutral + very high vol (VIX=30)"),
        ( 10, 24,   "slightly bullish but still neutral band + high vol"),
        (-10, 22,   "slightly bearish but still neutral band + high vol"),
        ( 29, 22,   "just below bullish threshold + high vol"),
        (-29, 25,   "just above bearish threshold + high vol"),
    ])
    def test_iron_condor_present(self, composite, vix, label):
        names = strategy_names(composite, vix)
        assert "Iron Condor" in names, (
            f"Iron Condor should be recommended for {label} "
            f"(composite={composite}, vix={vix}). "
            f"Got: {names}"
        )


# ── Correct strategies for each quadrant ─────────────────────────────────────

class TestBullishLowModVol:
    """Bullish + VIX < 22 → directional debit/credit spreads, no vol strategies."""

    @pytest.mark.parametrize("vix", [10, 14, 18, 21])
    def test_bull_call_spread_present(self, vix):
        assert "Bull Call Spread" in strategy_names(50, vix)

    @pytest.mark.parametrize("vix", [10, 14, 18, 21])
    def test_no_iron_condor(self, vix):
        assert "Iron Condor" not in strategy_names(50, vix)

    @pytest.mark.parametrize("vix", [10, 14, 18, 21])
    def test_no_long_straddle(self, vix):
        assert "Long Straddle" not in strategy_names(50, vix)


class TestBullishHighVol:
    """Bullish + VIX ≥ 22 → long vol strategies to capture directional move."""

    @pytest.mark.parametrize("vix", [22, 25, 30])
    def test_long_call_present(self, vix):
        assert "Long Call" in strategy_names(50, vix)

    @pytest.mark.parametrize("vix", [22, 25, 30])
    def test_no_iron_condor(self, vix):
        assert "Iron Condor" not in strategy_names(50, vix)


class TestBearishLowModVol:
    """Bearish + VIX < 22 → protective / spread strategies."""

    @pytest.mark.parametrize("vix", [10, 14, 18, 21])
    def test_bear_put_spread_present(self, vix):
        assert "Bear Put Spread" in strategy_names(-50, vix)

    @pytest.mark.parametrize("vix", [10, 14, 18, 21])
    def test_no_iron_condor(self, vix):
        assert "Iron Condor" not in strategy_names(-50, vix)


class TestBearishHighVol:
    """Bearish + VIX ≥ 22 → long vol to exploit uncertainty."""

    @pytest.mark.parametrize("vix", [22, 25, 30])
    def test_long_straddle_or_strangle_present(self, vix):
        names = strategy_names(-50, vix)
        assert "Long Straddle" in names or "Long Strangle" in names

    @pytest.mark.parametrize("vix", [22, 25, 30])
    def test_no_iron_condor(self, vix):
        assert "Iron Condor" not in strategy_names(-50, vix)


class TestNeutralLowVol:
    """Neutral + VIX < 16 → pin/income strategies; Iron Condor banned."""

    @pytest.mark.parametrize("vix", [10, 12, 14, 15])
    def test_butterfly_present(self, vix):
        assert "Butterfly Spread" in strategy_names(0, vix)

    @pytest.mark.parametrize("vix", [10, 12, 14, 15])
    def test_no_iron_condor(self, vix):
        assert "Iron Condor" not in strategy_names(0, vix)

    @pytest.mark.parametrize("composite", [-25, -10, 0, 10, 25])
    def test_no_iron_condor_across_neutral_band(self, composite):
        """Any composite in the neutral band (-30 to +30) + low vol → no Iron Condor."""
        assert "Iron Condor" not in strategy_names(composite, 14)


class TestNeutralModerateVol:
    """Neutral + 16 ≤ VIX < 22 → credit spreads; Iron Condor excluded."""

    @pytest.mark.parametrize("vix", [16, 18, 20, 21])
    def test_covered_call_or_spread_present(self, vix):
        names = strategy_names(0, vix)
        assert any(s in names for s in ["Covered Call", "Bull Put Spread", "Bear Call Spread"])

    @pytest.mark.parametrize("vix", [16, 18, 20, 21])
    def test_no_iron_condor(self, vix):
        assert "Iron Condor" not in strategy_names(0, vix)

    @pytest.mark.parametrize("composite", [-25, -10, 0, 10, 25])
    def test_no_iron_condor_across_neutral_band(self, composite):
        """Any composite in the neutral band + moderate vol → no Iron Condor."""
        assert "Iron Condor" not in strategy_names(composite, 19)


class TestNeutralHighVol:
    """Neutral + VIX ≥ 22 → Iron Condor is the primary recommendation."""

    @pytest.mark.parametrize("vix", [22, 24, 26, 30])
    def test_iron_condor_is_first(self, vix):
        """Iron Condor should be the first/primary recommendation."""
        names = strategy_names(0, vix)
        assert names[0] == "Iron Condor", (
            f"Expected Iron Condor first for neutral+high vol VIX={vix}, got: {names}"
        )

    @pytest.mark.parametrize("vix", [22, 24, 26, 30])
    def test_long_vol_also_present(self, vix):
        """Long vol alternatives (straddle/strangle) should also be offered."""
        names = strategy_names(0, vix)
        assert "Long Straddle" in names or "Long Strangle" in names


# ── Boundary conditions ───────────────────────────────────────────────────────

class TestBoundaryValues:
    """Test exact boundary values for composite and VIX thresholds."""

    def test_composite_exactly_30_is_bullish(self):
        """composite=30 triggers bullish path."""
        names = strategy_names(30, 18)
        assert "Bull Call Spread" in names

    def test_composite_29_is_neutral(self):
        """composite=29 stays in neutral path."""
        names = strategy_names(29, 18)
        assert "Bull Call Spread" not in names

    def test_composite_minus_30_is_bearish(self):
        names = strategy_names(-30, 18)
        assert "Bear Put Spread" in names

    def test_composite_minus_29_is_neutral(self):
        names = strategy_names(-29, 18)
        assert "Bear Put Spread" not in names

    def test_vix_22_is_high(self):
        """VIX=22 triggers high-vol path for neutral sentiment."""
        assert "Iron Condor" in strategy_names(0, 22)

    def test_vix_21_99_is_not_high(self):
        """VIX just below 22 → moderate path → no Iron Condor."""
        assert "Iron Condor" not in strategy_names(0, 21.99)

    def test_vix_16_is_moderate_not_low(self):
        """VIX=16 is moderate (not low), so Butterfly should not be primary."""
        names = strategy_names(0, 16)
        assert "Iron Condor" not in names
        assert "Butterfly Spread" not in names  # butterfly is for low vol only


# ── Data structure integrity ──────────────────────────────────────────────────

class TestDataStructure:
    """Every returned row must be a complete dict with all required keys."""

    @pytest.mark.parametrize("composite,vix", [
        ( 50, 12), ( 50, 25),
        (-50, 12), (-50, 25),
        (  0, 12), (  0, 18), (  0, 25),
        ( 29, 18), (-29, 18),
        (  0, 22), (  0, 15.9),
    ])
    def test_all_keys_present(self, composite, vix):
        assert all_keys_present(composite, vix), (
            f"Missing keys in strategy_table result for composite={composite}, vix={vix}"
        )

    @pytest.mark.parametrize("composite,vix", [
        ( 50, 12), ( 50, 25),
        (-50, 12), (-50, 25),
        (  0, 12), (  0, 18), (  0, 25),
    ])
    def test_at_least_one_strategy_returned(self, composite, vix):
        assert len(_strategy_table(composite, vix)) >= 1

    @pytest.mark.parametrize("composite,vix", [
        ( 50, 12), ( 50, 25),
        (-50, 12), (-50, 25),
        (  0, 12), (  0, 18), (  0, 25),
    ])
    def test_no_empty_strategy_names(self, composite, vix):
        for row in _strategy_table(composite, vix):
            assert row["strategy"].strip() != ""
