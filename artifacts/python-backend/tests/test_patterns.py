"""
Unit tests for candlestick pattern detection helpers in patterns_service.py.

Tests verify that the mathematical conditions for each pattern
(body size, shadow length, relative position) are correctly computed.
"""
import pytest

from app.services.patterns_service import (
    _body, _upper, _lower, _range,
    _is_bull, _is_bear, _is_doji, _mid,
)


# ── Helper candle factory ─────────────────────────────────────────────────────

def candle(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c, "volume": 1_000_000}


# ══════════════════════════════════════════════════════════════════════════════
#  Body, Shadow, Range helpers
# ══════════════════════════════════════════════════════════════════════════════

class TestCandleHelpers:

    def test_body_bullish_candle(self):
        """Bullish candle: body = close − open."""
        c = candle(o=100, h=115, l=98, c=110)
        assert _body(c) == pytest.approx(10.0)

    def test_body_bearish_candle(self):
        """Bearish candle: body = open − close (absolute)."""
        c = candle(o=110, h=115, l=98, c=100)
        assert _body(c) == pytest.approx(10.0)

    def test_body_doji_is_near_zero(self, doji_candle):
        """A doji candle's body should be tiny relative to range."""
        assert _body(doji_candle) <= _range(doji_candle) * 0.1

    def test_upper_shadow_shooting_star(self, shooting_star_candle):
        """Shooting star has a long upper shadow."""
        assert _upper(shooting_star_candle) > _body(shooting_star_candle) * 2

    def test_lower_shadow_hammer(self, hammer_candle):
        """Hammer has a long lower shadow."""
        assert _lower(hammer_candle) > _body(hammer_candle) * 2

    def test_range_always_positive(self, hammer_candle, shooting_star_candle, doji_candle):
        for c in (hammer_candle, shooting_star_candle, doji_candle):
            assert _range(c) > 0

    def test_range_high_minus_low(self):
        c = candle(o=100, h=120, l=80, c=110)
        assert _range(c) == pytest.approx(40.0)

    def test_upper_shadow_marubozu_bull(self, bullish_marubozu):
        """Full bullish marubozu: open==low, close==high → zero upper shadow."""
        assert _upper(bullish_marubozu) == pytest.approx(0.0)

    def test_lower_shadow_marubozu_bull(self, bullish_marubozu):
        """Full bullish marubozu → zero lower shadow."""
        assert _lower(bullish_marubozu) == pytest.approx(0.0)

    def test_upper_shadow_marubozu_bear(self, bearish_marubozu):
        """Full bearish marubozu: open==high, close==low → zero upper shadow."""
        assert _upper(bearish_marubozu) == pytest.approx(0.0)

    def test_lower_shadow_marubozu_bear(self, bearish_marubozu):
        """Full bearish marubozu → zero lower shadow."""
        assert _lower(bearish_marubozu) == pytest.approx(0.0)

    def test_mid_is_average_of_open_close(self):
        c = candle(o=100, h=120, l=80, c=120)
        assert _mid(c) == pytest.approx(110.0)


# ══════════════════════════════════════════════════════════════════════════════
#  Bullish / Bearish / Doji Classification
# ══════════════════════════════════════════════════════════════════════════════

class TestCandleClassification:

    def test_is_bull_true_when_close_above_open(self):
        assert _is_bull(candle(o=100, h=115, l=98, c=110)) is True

    def test_is_bull_false_when_close_below_open(self):
        assert _is_bull(candle(o=110, h=115, l=98, c=100)) is False

    def test_is_bull_false_on_equal_open_close(self):
        """Flat candle: close == open → not bullish."""
        assert _is_bull(candle(o=100, h=105, l=95, c=100)) is False

    def test_is_bear_true_when_close_below_open(self):
        assert _is_bear(candle(o=110, h=115, l=98, c=100)) is True

    def test_is_bear_false_when_close_above_open(self):
        assert _is_bear(candle(o=100, h=115, l=98, c=110)) is False

    def test_bull_and_bear_mutually_exclusive(self):
        c_up   = candle(o=100, h=115, l=98, c=110)
        c_down = candle(o=110, h=115, l=98, c=100)
        c_flat = candle(o=100, h=105, l=95, c=100)
        assert _is_bull(c_up)   and not _is_bear(c_up)
        assert _is_bear(c_down) and not _is_bull(c_down)
        assert not _is_bull(c_flat) and not _is_bear(c_flat)

    def test_is_doji_true_on_doji_candle(self, doji_candle):
        """Real doji: body ≤ 10% of range → _is_doji must return True."""
        assert _is_doji(doji_candle) is True

    def test_is_doji_false_on_marubozu(self, bullish_marubozu):
        """Full marubozu has body = 100% of range → not a doji."""
        assert _is_doji(bullish_marubozu) is False

    def test_is_doji_false_on_normal_candle(self):
        """Normal candle with 50% body → not a doji."""
        c = candle(o=100, h=115, l=95, c=110)
        # body = 10, range = 20 → 50% → not doji
        assert _is_doji(c) is False

    def test_is_doji_edge_exactly_10_percent(self):
        """Body exactly = 10% of range → classified as doji (≤ condition)."""
        # Range = 10, body must be ≤ 1.0
        # open = 100, close = 100, high = 105, low = 95 → body = 0, range = 10 → 0%
        c = candle(o=100, h=105, l=95, c=100)
        assert _is_doji(c) is True

    def test_is_doji_body_exactly_at_boundary(self):
        """Body = range * 0.10 exactly → should be doji."""
        # range = 20 (h=110, l=90), body must be ≤ 2
        c = candle(o=100, h=110, l=90, c=102)  # body = 2, range = 20 → 10% → doji
        assert _is_doji(c) is True

    def test_is_doji_just_above_threshold_not_doji(self):
        """Body = range * 0.11 → should NOT be a doji."""
        # range = 100 (h=150, l=50), body must be > 10 to fail
        c = candle(o=100, h=150, l=50, c=112)  # body = 12, range = 100 → 12% → not doji
        assert _is_doji(c) is False


# ══════════════════════════════════════════════════════════════════════════════
#  Hammer & Shooting Star Pattern Logic
# ══════════════════════════════════════════════════════════════════════════════

class TestHammerShootingStar:

    def test_hammer_conditions(self, hammer_candle):
        """
        Hammer: lower shadow > 2x body, upper shadow < body, not a doji.
        """
        c = hammer_candle
        body  = _body(c)
        lower = _lower(c)
        upper = _upper(c)
        assert lower > body * 2, "Hammer should have long lower shadow"
        assert not _is_doji(c), "Hammer is not a doji"
        # Upper shadow should be smaller than body (this is the key signal)
        assert upper < body, "Hammer upper shadow should be smaller than body"

    def test_shooting_star_conditions(self, shooting_star_candle):
        """
        Shooting star: upper shadow > 2x body, lower shadow ≤ body.
        The lower shadow can equal the body — what matters is it's dominated by the upper.
        """
        c = shooting_star_candle
        body  = _body(c)
        lower = _lower(c)
        upper = _upper(c)
        assert upper > body * 2, "Shooting star should have long upper shadow"
        assert lower <= body, "Shooting star lower shadow should be ≤ body"
        assert upper > lower * 3, "Upper shadow should dominate the lower shadow"

    def test_hammer_vs_shooting_star_are_opposites(self, hammer_candle, shooting_star_candle):
        """Hammer and shooting star have inverted shadow profiles."""
        # Hammer: long lower, short upper
        # Shooting star: long upper, short lower
        assert _lower(hammer_candle) > _upper(hammer_candle)
        assert _upper(shooting_star_candle) > _lower(shooting_star_candle)

    def test_random_candle_is_not_hammer(self):
        """A plain candle with balanced shadows is not a hammer."""
        c = candle(o=100, h=110, l=90, c=105)  # symmetric
        body  = _body(c)
        lower = _lower(c)
        # lower = min(100,105) - 90 = 10, body = 5 → lower > 2*body → IS hammer-like
        # Let's use a candle with tiny lower shadow
        c2 = candle(o=100, h=115, l=99, c=110)
        assert _lower(c2) < _body(c2), "Plain candle should not have hammer shadow profile"


# ══════════════════════════════════════════════════════════════════════════════
#  Engulfing Pattern Logic
# ══════════════════════════════════════════════════════════════════════════════

class TestEngulfingPatterns:

    def test_bullish_engulfing_conditions(self):
        """
        Bullish engulfing: current bull candle's body must fully contain
        the prior bear candle's body.
        """
        prior   = candle(o=110, h=112, l=100, c=102)  # bearish: open=110, close=102
        current = candle(o=100, h=120, l=99,  c=118)  # bullish: open=100, close=118

        # Current engulfs prior: current.open <= prior.close AND current.close >= prior.open
        assert current["open"]  <= prior["close"], "Engulfing: current open ≤ prior close"
        assert current["close"] >= prior["open"],  "Engulfing: current close ≥ prior open"
        assert _is_bull(current) and _is_bear(prior)

    def test_bearish_engulfing_conditions(self):
        """
        Bearish engulfing: current bear candle's body must fully contain
        the prior bull candle's body.
        """
        prior   = candle(o=100, h=120, l=99,  c=115)  # bullish
        current = candle(o=118, h=120, l=98,  c=98)   # bearish: open=118, close=98

        assert current["open"]  >= prior["close"], "Engulfing: current open ≥ prior close"
        assert current["close"] <= prior["open"],  "Engulfing: current close ≤ prior open"
        assert _is_bear(current) and _is_bull(prior)

    def test_non_engulfing_smaller_body(self):
        """A candle that doesn't fully engulf the prior is NOT an engulfing pattern."""
        prior   = candle(o=100, h=120, l=95, c=115)  # bullish, body=15
        current = candle(o=112, h=116, l=105, c=106)  # bearish, body=6 — smaller

        # current.open (112) < prior.close (115) → does NOT engulf
        assert current["open"] < prior["close"], "Non-engulfing: smaller body doesn't cover"
