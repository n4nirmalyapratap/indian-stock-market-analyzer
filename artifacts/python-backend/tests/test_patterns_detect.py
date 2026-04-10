"""
test_patterns_detect.py
=======================
Comprehensive unit tests for ALL chart patterns detected by
PatternsService._detect() and the get_patterns() filtering logic.

Coverage map
────────────
Category           | Patterns
───────────────────┼──────────────────────────────────────────────────────────
Candlestick (×12)  | Hammer, Inverted Hammer, Shooting Star, Hanging Man,
                   | Doji, Dragonfly Doji, Gravestone Doji, Spinning Top,
                   | Bullish Marubozu, Bearish Marubozu, Inside Bar, Outside Bar
Two-Candle (×8)    | Bullish Engulfing, Bearish Engulfing, Bullish Harami,
                   | Bearish Harami, Piercing Line, Dark Cloud Cover,
                   | Tweezer Bottom, Tweezer Top
Three-Candle (×6)  | Morning Star, Evening Star, Morning Doji Star,
                   | Evening Doji Star, Three White Soldiers, Three Black Crows
Indicator (×12)    | RSI Oversold Bounce, RSI Bullish Divergence, RSI Overbought,
                   | RSI Bearish Divergence, MACD Bullish Crossover,
                   | MACD Bearish Crossover, MACD Histogram Expanding (Bull),
                   | MACD Histogram Expanding (Bear), EMA Golden Cross (20/50),
                   | EMA Death Cross (20/50), EMA Golden Cross (50/200),
                   | EMA Death Cross (50/200)

Additionally:
  • _mk() output-structure tests
  • get_patterns() universe / signal / category filter tests
  • Exhaustive Universe × Category × Signal combination-matrix test
"""
import sys
import os
import asyncio
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.patterns_service import PatternsService, _mk
import app.services.patterns_service as _ps_mod


# ══════════════════════════════════════════════════════════════════════════════
#  OHLCV Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _c(o, h, l, c, v=1_000_000):
    """Build a single OHLCV candle dict."""
    return {"open": float(o), "high": float(h), "low": float(l),
            "close": float(c), "volume": int(v)}


def _falling_bars(n=50, start=120.0, step=0.4, wick=0.5):
    """
    Strictly-falling price series.
    RSI with period 14 will converge to ~5-15 (well below 35, 45, 50, 55).
    ATR ≈ wick * 2 = 1.0 (tight bars).
    """
    bars, price = [], start
    for _ in range(n):
        bars.append(_c(price + wick, price + wick, price - wick, price))
        price -= step
    return bars


def _rising_bars(n=50, start=80.0, step=0.4, wick=0.5):
    """
    Strictly-rising price series.
    RSI will converge to ~85-100 (well above 55, 60, 72).
    ATR ≈ 1.0 (tight bars).
    """
    bars, price = [], start
    for _ in range(n):
        bars.append(_c(price - wick, price + wick, price - wick, price))
        price += step
    return bars


def _flat_bars(n=50, base=100.0, wick=1.0):
    """
    Alternating ±0.2 flat bars → RSI ≈ 50.
    ATR ≈ 2.0.
    """
    bars = []
    for i in range(n):
        alt = 0.2 if i % 2 == 0 else -0.2
        p = base + alt
        bars.append(_c(base, base + wick, base - wick, p))
    return bars


def _splice(bars, *candles):
    """
    Return a copy of *bars* with the last len(candles) entries replaced.
    Candles are ordered oldest→newest (same order as positional args).
    The rightmost arg becomes c0 (the most-recent bar).
    """
    out = list(bars)
    for i, c in enumerate(reversed(candles)):
        out[-(i + 1)] = c
    return out


def _names(result: list[dict]) -> set[str]:
    """Extract the set of pattern names from _detect output."""
    return {p["pattern"] for p in result}


# ── Fake dependencies so PatternsService can be instantiated ─────────────────

class _FakeYahoo:
    pass


class _FakeNse:
    pass


SVC = PatternsService(_FakeYahoo(), _FakeNse())

# Convenience constants
NIFTY100 = "NIFTY100"
MIDCAP    = "MIDCAP"
SMALLCAP  = "SMALLCAP"
SYM       = "TEST.NS"


# ══════════════════════════════════════════════════════════════════════════════
#  _mk() Output-Structure Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestMkHelper:
    """Verify the _mk() factory produces a correctly-shaped pattern dict."""

    BASE = _mk("RELIANCE", "NIFTY100", "Hammer", "BULLISH", "CALL",
                72, 2500.0, "Test desc", "Candlestick", 2600.0, 2450.0)

    REQUIRED_KEYS = {
        "symbol", "pattern", "patternType", "signal", "confidence",
        "detectedAt", "currentPrice", "targetPrice", "stopLoss",
        "description", "timeframe", "universe", "category",
    }

    def test_all_required_keys_present(self):
        assert self.REQUIRED_KEYS <= set(self.BASE.keys())

    def test_symbol_stored_correctly(self):
        assert self.BASE["symbol"] == "RELIANCE"

    def test_universe_stored_correctly(self):
        assert self.BASE["universe"] == "NIFTY100"

    def test_pattern_name_stored(self):
        assert self.BASE["pattern"] == "Hammer"

    def test_pattern_type_stored(self):
        assert self.BASE["patternType"] == "BULLISH"

    def test_signal_stored(self):
        assert self.BASE["signal"] == "CALL"

    def test_confidence_stored(self):
        assert self.BASE["confidence"] == 72

    def test_current_price_stored(self):
        assert self.BASE["currentPrice"] == pytest.approx(2500.0)

    def test_target_price_stored(self):
        assert self.BASE["targetPrice"] == pytest.approx(2600.0)

    def test_stop_loss_stored(self):
        assert self.BASE["stopLoss"] == pytest.approx(2450.0)

    def test_description_stored(self):
        assert self.BASE["description"] == "Test desc"

    def test_timeframe_is_1d(self):
        assert self.BASE["timeframe"] == "1D"

    def test_category_stored(self):
        assert self.BASE["category"] == "Candlestick"

    def test_detected_at_is_iso_string(self):
        dt = self.BASE["detectedAt"]
        assert isinstance(dt, str) and "T" in dt and dt.endswith("Z")

    def test_optional_target_none(self):
        mk_no_tgt = _mk("X", "NIFTY100", "Doji", "NEUTRAL", "WAIT",
                         55, 100.0, "desc", "Candlestick")
        assert mk_no_tgt["targetPrice"] is None
        assert mk_no_tgt["stopLoss"] is None

    def test_confidence_range_typical(self):
        for conf in [50, 55, 60, 65, 68, 70, 72, 75, 78, 80, 82, 84, 88]:
            m = _mk("X", "NIFTY100", "P", "BULLISH", "CALL", conf, 100.0, "", "C")
            assert m["confidence"] == conf

    def test_all_three_universes_accepted(self):
        for u in ("NIFTY100", "MIDCAP", "SMALLCAP"):
            m = _mk("X", u, "P", "BULLISH", "CALL", 70, 100.0, "", "C")
            assert m["universe"] == u

    def test_all_four_categories_accepted(self):
        for cat in ("Candlestick", "Two-Candle", "Three-Candle", "Indicator"):
            m = _mk("X", "NIFTY100", "P", "BULLISH", "CALL", 70, 100.0, "", cat)
            assert m["category"] == cat

    def test_all_three_signals_accepted(self):
        for sig in ("CALL", "PUT", "WAIT"):
            m = _mk("X", "NIFTY100", "P", "NEUTRAL", sig, 55, 100.0, "", "C")
            assert m["signal"] == sig


# ══════════════════════════════════════════════════════════════════════════════
#  Single-Candle Patterns  (Candlestick category)
# ══════════════════════════════════════════════════════════════════════════════

class TestSingleCandlePatterns:
    """
    All 12 single-candle patterns, tested against realistic OHLCV histories
    that satisfy both the geometric and RSI conditions.
    """

    # ── Hammer ────────────────────────────────────────────────────────────────
    # Condition: _lower(c0) > 2*body, _upper(c0) < 0.5*body, RSI < 50

    def test_hammer_detected_in_falling_market(self):
        # body=4, lower=18>8✓, upper=1.9<2✓  ↳ falling series → RSI ≪ 50
        c0 = _c(100, 105.9, 82, 104)
        h  = _splice(_falling_bars(), c0)
        assert "Hammer" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_hammer_not_detected_when_lower_shadow_too_short(self):
        # lower = 2, body = 10 → 2 < 2*10=20 → no hammer
        c0 = _c(100, 112, 98, 110)
        h  = _splice(_falling_bars(), c0)
        assert "Hammer" not in _names(SVC._detect(SYM, h, NIFTY100))

    def test_hammer_not_detected_in_rising_market_rsi_above_50(self):
        # Same shape but RSI > 50 (rising history)
        c0 = _c(100, 105.9, 82, 104)
        h  = _splice(_rising_bars(), c0)
        assert "Hammer" not in _names(SVC._detect(SYM, h, NIFTY100))

    def test_hammer_signal_is_call(self):
        c0 = _c(100, 105.9, 82, 104)
        h  = _splice(_falling_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Hammer"]
        assert hits and hits[0]["signal"] == "CALL"

    def test_hammer_confidence_is_72(self):
        c0 = _c(100, 105.9, 82, 104)
        h  = _splice(_falling_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Hammer"]
        assert hits and hits[0]["confidence"] == 72

    def test_hammer_category_is_candlestick(self):
        c0 = _c(100, 105.9, 82, 104)
        h  = _splice(_falling_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Hammer"]
        assert hits and hits[0]["category"] == "Candlestick"

    def test_hammer_has_target_and_stoploss(self):
        c0 = _c(100, 105.9, 82, 104)
        h  = _splice(_falling_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Hammer"]
        assert hits
        assert hits[0]["targetPrice"] is not None
        assert hits[0]["stopLoss"] is not None

    # ── Inverted Hammer ───────────────────────────────────────────────────────
    # Condition: _upper > 2*body, _lower < 0.5*body, RSI < 45, is_bull
    # Need aggressively falling bars so RSI ≪ 45 (step=2.0 → RSI ≈ 14)

    def test_inverted_hammer_detected(self):
        # body=6(bull), upper=14>12✓, lower=1<3✓; steep fall → RSI≈14 <45✓
        c0 = _c(100, 120, 99, 106)
        h  = _splice(_falling_bars(start=200.0, step=2.0), c0)
        assert "Inverted Hammer" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_inverted_hammer_requires_bullish_candle(self):
        # Bearish version should NOT trigger
        c0 = _c(106, 120, 99, 100)   # bear
        h  = _splice(_falling_bars(start=200.0, step=2.0), c0)
        assert "Inverted Hammer" not in _names(SVC._detect(SYM, h, NIFTY100))

    def test_inverted_hammer_not_in_rising_market(self):
        # RSI > 45 in rising market → condition fails
        c0 = _c(100, 120, 99, 106)
        h  = _splice(_rising_bars(), c0)
        assert "Inverted Hammer" not in _names(SVC._detect(SYM, h, NIFTY100))

    def test_inverted_hammer_signal_is_call(self):
        c0 = _c(100, 120, 99, 106)
        h  = _splice(_falling_bars(start=200.0, step=2.0), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Inverted Hammer"]
        assert hits and hits[0]["signal"] == "CALL"

    def test_inverted_hammer_confidence_is_65(self):
        c0 = _c(100, 120, 99, 106)
        h  = _splice(_falling_bars(start=200.0, step=2.0), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Inverted Hammer"]
        assert hits and hits[0]["confidence"] == 65

    # ── Shooting Star ─────────────────────────────────────────────────────────
    # Condition: _upper > 2*body, _lower < 0.5*body, RSI > 55

    def test_shooting_star_detected(self):
        # body=2, upper=14>4✓, lower=0<1✓; rising → RSI>55
        c0 = _c(106, 120, 104, 104)
        h  = _splice(_rising_bars(), c0)
        assert "Shooting Star" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_shooting_star_not_in_falling_market(self):
        c0 = _c(106, 120, 104, 104)
        h  = _splice(_falling_bars(), c0)
        assert "Shooting Star" not in _names(SVC._detect(SYM, h, NIFTY100))

    def test_shooting_star_signal_is_put(self):
        c0 = _c(106, 120, 104, 104)
        h  = _splice(_rising_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Shooting Star"]
        assert hits and hits[0]["signal"] == "PUT"

    def test_shooting_star_confidence_is_72(self):
        c0 = _c(106, 120, 104, 104)
        h  = _splice(_rising_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Shooting Star"]
        assert hits and hits[0]["confidence"] == 72

    def test_shooting_star_has_stop_loss_no_target(self):
        c0 = _c(106, 120, 104, 104)
        h  = _splice(_rising_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Shooting Star"]
        assert hits
        assert hits[0]["stopLoss"] is not None
        assert hits[0]["targetPrice"] is None

    # ── Hanging Man ───────────────────────────────────────────────────────────
    # Condition: _lower > 2*body, _upper < 0.5*body, RSI > 60, is_bear

    def test_hanging_man_detected(self):
        # body=4(bear), lower=18>8✓, upper=2<2✓; rising → RSI>60
        c0 = _c(104, 105.9, 82, 100)
        h  = _splice(_rising_bars(), c0)
        assert "Hanging Man" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_hanging_man_requires_bearish_candle(self):
        c0 = _c(100, 105.9, 82, 104)   # bull
        h  = _splice(_rising_bars(), c0)
        assert "Hanging Man" not in _names(SVC._detect(SYM, h, NIFTY100))

    def test_hanging_man_not_in_falling_market(self):
        c0 = _c(104, 105.9, 82, 100)
        h  = _splice(_falling_bars(), c0)
        assert "Hanging Man" not in _names(SVC._detect(SYM, h, NIFTY100))

    def test_hanging_man_signal_is_put(self):
        c0 = _c(104, 105.9, 82, 100)
        h  = _splice(_rising_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Hanging Man"]
        assert hits and hits[0]["signal"] == "PUT"

    def test_hanging_man_confidence_is_68(self):
        c0 = _c(104, 105.9, 82, 100)
        h  = _splice(_rising_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Hanging Man"]
        assert hits and hits[0]["confidence"] == 68

    # ── Doji ─────────────────────────────────────────────────────────────────
    # Condition: is_doji(c0) AND range > atr*0.5

    def test_doji_detected(self):
        # body=0.5, range=20 → 2.5% < 10% → doji; range=20 >> atr≈1
        c0 = _c(100, 110, 90, 100.5)
        h  = _splice(_flat_bars(), c0)
        assert "Doji" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_doji_not_detected_on_marubozu(self):
        c0 = _c(100, 115, 100, 115)   # body=range=15 → not doji
        h  = _splice(_flat_bars(), c0)
        assert "Doji" not in _names(SVC._detect(SYM, h, NIFTY100))

    def test_doji_signal_is_wait(self):
        c0 = _c(100, 110, 90, 100.5)
        h  = _splice(_flat_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Doji"]
        assert hits and hits[0]["signal"] == "WAIT"

    def test_doji_confidence_is_55(self):
        c0 = _c(100, 110, 90, 100.5)
        h  = _splice(_flat_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Doji"]
        assert hits and hits[0]["confidence"] == 55

    def test_doji_has_no_target_or_stoploss(self):
        c0 = _c(100, 110, 90, 100.5)
        h  = _splice(_flat_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Doji"]
        assert hits
        assert hits[0]["targetPrice"] is None
        assert hits[0]["stopLoss"] is None

    # ── Dragonfly Doji ────────────────────────────────────────────────────────
    # Condition: is_doji(c0) AND _lower > range*0.7

    def test_dragonfly_doji_detected(self):
        # body=0.5, range=20, lower=19 > 14(70%) ✓; doji ✓
        c0 = _c(109, 110, 90, 109.5)
        h  = _splice(_flat_bars(), c0)
        assert "Dragonfly Doji" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_dragonfly_doji_not_detected_when_lower_short(self):
        # long upper, short lower → Gravestone, not Dragonfly
        c0 = _c(91, 110, 90, 91.5)
        h  = _splice(_flat_bars(), c0)
        assert "Dragonfly Doji" not in _names(SVC._detect(SYM, h, NIFTY100))

    def test_dragonfly_doji_signal_is_call(self):
        c0 = _c(109, 110, 90, 109.5)
        h  = _splice(_flat_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Dragonfly Doji"]
        assert hits and hits[0]["signal"] == "CALL"

    def test_dragonfly_doji_confidence_is_70(self):
        c0 = _c(109, 110, 90, 109.5)
        h  = _splice(_flat_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Dragonfly Doji"]
        assert hits and hits[0]["confidence"] == 70

    # ── Gravestone Doji ───────────────────────────────────────────────────────
    # Condition: is_doji(c0) AND _upper > range*0.7

    def test_gravestone_doji_detected(self):
        # body=0.5, range=20, upper=18.5 > 14(70%) ✓; doji ✓
        c0 = _c(91, 110, 90, 91.5)
        h  = _splice(_flat_bars(), c0)
        assert "Gravestone Doji" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_gravestone_doji_not_detected_when_upper_short(self):
        c0 = _c(109, 110, 90, 109.5)   # long lower → Dragonfly
        h  = _splice(_flat_bars(), c0)
        assert "Gravestone Doji" not in _names(SVC._detect(SYM, h, NIFTY100))

    def test_gravestone_doji_signal_is_put(self):
        c0 = _c(91, 110, 90, 91.5)
        h  = _splice(_flat_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Gravestone Doji"]
        assert hits and hits[0]["signal"] == "PUT"

    def test_gravestone_doji_confidence_is_70(self):
        c0 = _c(91, 110, 90, 91.5)
        h  = _splice(_flat_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Gravestone Doji"]
        assert hits and hits[0]["confidence"] == 70

    def test_gravestone_doji_has_stop_loss(self):
        c0 = _c(91, 110, 90, 91.5)
        h  = _splice(_flat_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Gravestone Doji"]
        assert hits and hits[0]["stopLoss"] is not None

    # ── Spinning Top ──────────────────────────────────────────────────────────
    # Condition: not doji, body < range*0.3, lower > body, upper > body

    def test_spinning_top_detected(self):
        # body=4, range=24(16.7%<30%), lower=12>4, upper=8>4; doji=4/24=16.7%>10%
        c0 = _c(100, 112, 88, 104)
        h  = _splice(_flat_bars(), c0)
        assert "Spinning Top" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_spinning_top_not_detected_for_doji(self):
        # A doji cannot also be a Spinning Top (explicit 'not _is_doji' guard)
        c0 = _c(100, 110, 90, 100.5)   # doji
        h  = _splice(_flat_bars(), c0)
        assert "Spinning Top" not in _names(SVC._detect(SYM, h, NIFTY100))

    def test_spinning_top_signal_is_wait(self):
        c0 = _c(100, 112, 88, 104)
        h  = _splice(_flat_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Spinning Top"]
        assert hits and hits[0]["signal"] == "WAIT"

    def test_spinning_top_confidence_is_50(self):
        c0 = _c(100, 112, 88, 104)
        h  = _splice(_flat_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Spinning Top"]
        assert hits and hits[0]["confidence"] == 50

    # ── Bullish Marubozu ──────────────────────────────────────────────────────
    # Condition: is_bull, body > range*0.9, body > atr*1.2

    def test_bullish_marubozu_detected(self):
        # body=15(bull), range=16, 93.75%>90%; ATR≈1 → body 15 >> 1.2
        c0 = _c(100, 115.5, 99.5, 115)
        h  = _splice(_falling_bars(), c0)
        assert "Bullish Marubozu" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_bullish_marubozu_requires_bull_candle(self):
        c0 = _c(115, 115.5, 99.5, 100)   # bear
        h  = _splice(_falling_bars(), c0)
        assert "Bullish Marubozu" not in _names(SVC._detect(SYM, h, NIFTY100))

    def test_bullish_marubozu_signal_is_call(self):
        c0 = _c(100, 115.5, 99.5, 115)
        h  = _splice(_falling_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Bullish Marubozu"]
        assert hits and hits[0]["signal"] == "CALL"

    def test_bullish_marubozu_confidence_is_75(self):
        c0 = _c(100, 115.5, 99.5, 115)
        h  = _splice(_falling_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Bullish Marubozu"]
        assert hits and hits[0]["confidence"] == 75

    # ── Bearish Marubozu ──────────────────────────────────────────────────────
    # Condition: is_bear, body > range*0.9, body > atr*1.2

    def test_bearish_marubozu_detected(self):
        # body=15(bear), range=15.5, 96.8%>90%; ATR≈1
        c0 = _c(115, 115.5, 100, 100)
        h  = _splice(_rising_bars(), c0)
        assert "Bearish Marubozu" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_bearish_marubozu_requires_bear_candle(self):
        c0 = _c(100, 115.5, 99.5, 115)   # bull
        h  = _splice(_rising_bars(), c0)
        assert "Bearish Marubozu" not in _names(SVC._detect(SYM, h, NIFTY100))

    def test_bearish_marubozu_signal_is_put(self):
        c0 = _c(115, 115.5, 100, 100)
        h  = _splice(_rising_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Bearish Marubozu"]
        assert hits and hits[0]["signal"] == "PUT"

    def test_bearish_marubozu_confidence_is_75(self):
        c0 = _c(115, 115.5, 100, 100)
        h  = _splice(_rising_bars(), c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Bearish Marubozu"]
        assert hits and hits[0]["confidence"] == 75

    # ── Inside Bar ────────────────────────────────────────────────────────────
    # Condition: c0.high < c1.high AND c0.low > c1.low AND body(c0) < body(c1)*0.6

    def test_inside_bar_detected(self):
        # c1: wide range; c0 body=3 < 8*0.6=4.8✓, high=115<120✓, low=85>80✓
        c1 = _c(100, 120, 80, 108)   # body=8
        c0 = _c(104, 115, 85, 107)   # body=3
        h  = _splice(_flat_bars(), c1, c0)
        assert "Inside Bar" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_inside_bar_not_detected_when_high_exceeds_prior(self):
        c1 = _c(100, 120, 80, 108)
        c0 = _c(104, 125, 85, 107)   # high=125 > c1.high=120 → not inside
        h  = _splice(_flat_bars(), c1, c0)
        assert "Inside Bar" not in _names(SVC._detect(SYM, h, NIFTY100))

    def test_inside_bar_signal_is_wait(self):
        c1 = _c(100, 120, 80, 108)
        c0 = _c(104, 115, 85, 107)
        h  = _splice(_flat_bars(), c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Inside Bar"]
        assert hits and hits[0]["signal"] == "WAIT"

    def test_inside_bar_confidence_is_60(self):
        c1 = _c(100, 120, 80, 108)
        c0 = _c(104, 115, 85, 107)
        h  = _splice(_flat_bars(), c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Inside Bar"]
        assert hits and hits[0]["confidence"] == 60

    # ── Outside Bar ───────────────────────────────────────────────────────────
    # Condition: c0.high > c1.high AND c0.low < c1.low AND body(c0) > body(c1)*1.5

    def test_outside_bar_detected(self):
        # c1: body=5; c0: body=8>7.5✓, high=115>108✓, low=85<92✓
        c1 = _c(100, 108, 92, 105)   # body=5
        c0 = _c(100, 115, 85, 108)   # body=8
        h  = _splice(_flat_bars(), c1, c0)
        assert "Outside Bar" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_outside_bar_not_detected_when_smaller(self):
        c1 = _c(100, 115, 85, 110)   # wide
        c0 = _c(100, 110, 90, 108)   # narrow → inside bar, not outside
        h  = _splice(_flat_bars(), c1, c0)
        assert "Outside Bar" not in _names(SVC._detect(SYM, h, NIFTY100))

    def test_outside_bar_signal_is_wait(self):
        c1 = _c(100, 108, 92, 105)
        c0 = _c(100, 115, 85, 108)
        h  = _splice(_flat_bars(), c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Outside Bar"]
        assert hits and hits[0]["signal"] == "WAIT"

    def test_outside_bar_confidence_is_58(self):
        c1 = _c(100, 108, 92, 105)
        c0 = _c(100, 115, 85, 108)
        h  = _splice(_flat_bars(), c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Outside Bar"]
        assert hits and hits[0]["confidence"] == 58


# ══════════════════════════════════════════════════════════════════════════════
#  Two-Candle Patterns
# ══════════════════════════════════════════════════════════════════════════════

class TestTwoCandlePatterns:

    # ── Bullish Engulfing ─────────────────────────────────────────────────────
    # c1 bear, c0 bull, c0.open <= c1.close, c0.close >= c1.open

    def test_bullish_engulfing_detected(self):
        c1 = _c(110, 112, 100, 102)   # bear
        c0 = _c(100, 120, 99,  118)   # bull; open<102✓, close>110✓
        h  = _splice(_falling_bars(), c1, c0)
        assert "Bullish Engulfing" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_bullish_engulfing_signal_is_call(self):
        c1 = _c(110, 112, 100, 102)
        c0 = _c(100, 120, 99,  118)
        h  = _splice(_falling_bars(), c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Bullish Engulfing"]
        assert hits and hits[0]["signal"] == "CALL"

    def test_bullish_engulfing_confidence_is_78(self):
        c1 = _c(110, 112, 100, 102)
        c0 = _c(100, 120, 99,  118)
        h  = _splice(_falling_bars(), c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Bullish Engulfing"]
        assert hits and hits[0]["confidence"] == 78

    def test_bullish_engulfing_not_detected_when_c1_is_bull(self):
        c1 = _c(100, 112, 99, 110)   # bull — wrong direction
        c0 = _c(100, 120, 99, 118)
        h  = _splice(_falling_bars(), c1, c0)
        assert "Bullish Engulfing" not in _names(SVC._detect(SYM, h, NIFTY100))

    def test_bullish_engulfing_not_detected_when_c0_does_not_engulf(self):
        c1 = _c(110, 112, 100, 102)   # bear, body=8
        c0 = _c(103, 108, 101, 107)   # bull, smaller
        h  = _splice(_falling_bars(), c1, c0)
        assert "Bullish Engulfing" not in _names(SVC._detect(SYM, h, NIFTY100))

    # ── Bearish Engulfing ─────────────────────────────────────────────────────
    # c1 bull, c0 bear, c0.open >= c1.close, c0.close <= c1.open

    def test_bearish_engulfing_detected(self):
        c1 = _c(100, 120, 99,  115)   # bull
        c0 = _c(118, 120, 98,   98)   # bear; open>115✓, close<100✓
        h  = _splice(_rising_bars(), c1, c0)
        assert "Bearish Engulfing" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_bearish_engulfing_signal_is_put(self):
        c1 = _c(100, 120, 99,  115)
        c0 = _c(118, 120, 98,   98)
        h  = _splice(_rising_bars(), c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Bearish Engulfing"]
        assert hits and hits[0]["signal"] == "PUT"

    def test_bearish_engulfing_confidence_is_78(self):
        c1 = _c(100, 120, 99,  115)
        c0 = _c(118, 120, 98,   98)
        h  = _splice(_rising_bars(), c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Bearish Engulfing"]
        assert hits and hits[0]["confidence"] == 78

    # ── Bullish Harami ────────────────────────────────────────────────────────
    # c1 bear, c0 bull inside c1; body(c0) < body(c1)*0.6

    def test_bullish_harami_detected(self):
        # c1 bear body=20; c0 bull body=6<12; inside c1
        c1 = _c(120, 122, 95, 100)   # bear, body=20
        c0 = _c(102, 115, 100, 108)   # bull, body=6<12✓, open>100✓, close<120✓
        h  = _splice(_falling_bars(), c1, c0)
        assert "Bullish Harami" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_bullish_harami_signal_is_call(self):
        c1 = _c(120, 122, 95, 100)
        c0 = _c(102, 115, 100, 108)
        h  = _splice(_falling_bars(), c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Bullish Harami"]
        assert hits and hits[0]["signal"] == "CALL"

    def test_bullish_harami_confidence_is_65(self):
        c1 = _c(120, 122, 95, 100)
        c0 = _c(102, 115, 100, 108)
        h  = _splice(_falling_bars(), c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Bullish Harami"]
        assert hits and hits[0]["confidence"] == 65

    def test_bullish_harami_not_detected_when_c0_too_large(self):
        c1 = _c(120, 122, 95, 100)    # body=20
        c0 = _c(102, 118, 100, 115)   # bull body=13>12 → not harami
        h  = _splice(_falling_bars(), c1, c0)
        assert "Bullish Harami" not in _names(SVC._detect(SYM, h, NIFTY100))

    # ── Bearish Harami ────────────────────────────────────────────────────────
    # c1 bull, c0 bear inside c1; body(c0) < body(c1)*0.6

    def test_bearish_harami_detected(self):
        # c1 bull body=20; c0 bear body=6<12; inside c1
        c1 = _c(100, 125, 98, 120)   # bull, body=20
        c0 = _c(118, 120, 100, 112)   # bear, body=6<12✓, open<120✓, close>100✓
        h  = _splice(_rising_bars(), c1, c0)
        assert "Bearish Harami" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_bearish_harami_signal_is_put(self):
        c1 = _c(100, 125, 98, 120)
        c0 = _c(118, 120, 100, 112)
        h  = _splice(_rising_bars(), c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Bearish Harami"]
        assert hits and hits[0]["signal"] == "PUT"

    def test_bearish_harami_confidence_is_65(self):
        c1 = _c(100, 125, 98, 120)
        c0 = _c(118, 120, 100, 112)
        h  = _splice(_rising_bars(), c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Bearish Harami"]
        assert hits and hits[0]["confidence"] == 65

    # ── Piercing Line ─────────────────────────────────────────────────────────
    # c1 bear, c0 bull; c0.open < c1.low AND c0.close > mid(c1) AND c0.close < c1.open

    def test_piercing_line_detected(self):
        # c1 bear: open=120, close=102, mid=111, low=100
        # c0 bull: open=98<100✓, close=115>111✓, close=115<120✓
        c1 = _c(120, 122, 100, 102)
        c0 = _c(98,  120, 97,  115)
        h  = _splice(_falling_bars(), c1, c0)
        assert "Piercing Line" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_piercing_line_signal_is_call(self):
        c1 = _c(120, 122, 100, 102)
        c0 = _c(98,  120, 97,  115)
        h  = _splice(_falling_bars(), c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Piercing Line"]
        assert hits and hits[0]["signal"] == "CALL"

    def test_piercing_line_confidence_is_70(self):
        c1 = _c(120, 122, 100, 102)
        c0 = _c(98,  120, 97,  115)
        h  = _splice(_falling_bars(), c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Piercing Line"]
        assert hits and hits[0]["confidence"] == 70

    def test_piercing_line_not_detected_when_close_below_midpoint(self):
        # c0 closes only at 107 — below mid(c1)=111 → no piercing line
        c1 = _c(120, 122, 100, 102)
        c0 = _c(98,  120, 97,  107)
        h  = _splice(_falling_bars(), c1, c0)
        assert "Piercing Line" not in _names(SVC._detect(SYM, h, NIFTY100))

    # ── Dark Cloud Cover ──────────────────────────────────────────────────────
    # c1 bull, c0 bear; c0.open > c1.high AND c0.close < mid(c1) AND c0.close > c1.open

    def test_dark_cloud_cover_detected(self):
        # c1 bull: open=100, close=118, mid=109, high=120
        # c0 bear: open=122>120✓, close=105<109✓, close=105>100✓
        c1 = _c(100, 120, 98, 118)
        c0 = _c(122, 125, 100, 105)
        h  = _splice(_rising_bars(), c1, c0)
        assert "Dark Cloud Cover" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_dark_cloud_cover_signal_is_put(self):
        c1 = _c(100, 120, 98, 118)
        c0 = _c(122, 125, 100, 105)
        h  = _splice(_rising_bars(), c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Dark Cloud Cover"]
        assert hits and hits[0]["signal"] == "PUT"

    def test_dark_cloud_cover_confidence_is_70(self):
        c1 = _c(100, 120, 98, 118)
        c0 = _c(122, 125, 100, 105)
        h  = _splice(_rising_bars(), c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Dark Cloud Cover"]
        assert hits and hits[0]["confidence"] == 70

    # ── Tweezer Bottom ────────────────────────────────────────────────────────
    # |c0.low - c1.low| / price < 0.003, c1 bear, c0 bull, RSI < 55
    # Use steep fall (step=2) so RSI ≪ 55 even after a small bounce

    def test_tweezer_bottom_detected(self):
        # price ≈ 108; |100.2-100.0|/108 = 0.00185 < 0.003 ✓; steep→RSI<<55✓
        c1 = _c(105, 108, 100.0, 101)     # bear
        c0 = _c(100.5, 110, 100.2, 108)   # bull
        h  = _splice(_falling_bars(start=200.0, step=2.0), c1, c0)
        assert "Tweezer Bottom" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_tweezer_bottom_signal_is_call(self):
        c1 = _c(105, 108, 100.0, 101)
        c0 = _c(100.5, 110, 100.2, 108)
        h  = _splice(_falling_bars(start=200.0, step=2.0), c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Tweezer Bottom"]
        assert hits and hits[0]["signal"] == "CALL"

    def test_tweezer_bottom_confidence_is_68(self):
        c1 = _c(105, 108, 100.0, 101)
        c0 = _c(100.5, 110, 100.2, 108)
        h  = _splice(_falling_bars(start=200.0, step=2.0), c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Tweezer Bottom"]
        assert hits and hits[0]["confidence"] == 68

    def test_tweezer_bottom_not_detected_when_lows_differ_too_much(self):
        # lows differ by 10 — price=108, ratio=10/108≈0.09 > 0.003
        c1 = _c(115, 118, 100, 101)
        c0 = _c(100, 115, 110, 114)   # low=110 vs c1.low=100, diff=10/114≈0.088
        h  = _splice(_falling_bars(), c1, c0)
        assert "Tweezer Bottom" not in _names(SVC._detect(SYM, h, NIFTY100))

    # ── Tweezer Top ───────────────────────────────────────────────────────────
    # |c0.high - c1.high| / price < 0.003, c1 bull, c0 bear, RSI > 55

    def test_tweezer_top_detected(self):
        # price ≈ 105; |110.2-110.0|/105 = 0.0019 < 0.003 ✓
        c1 = _c(100, 110.0, 99, 108)   # bull
        c0 = _c(108.5, 110.2, 104, 105)   # bear
        h  = _splice(_rising_bars(), c1, c0)
        assert "Tweezer Top" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_tweezer_top_signal_is_put(self):
        c1 = _c(100, 110.0, 99, 108)
        c0 = _c(108.5, 110.2, 104, 105)
        h  = _splice(_rising_bars(), c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Tweezer Top"]
        assert hits and hits[0]["signal"] == "PUT"

    def test_tweezer_top_confidence_is_68(self):
        c1 = _c(100, 110.0, 99, 108)
        c0 = _c(108.5, 110.2, 104, 105)
        h  = _splice(_rising_bars(), c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Tweezer Top"]
        assert hits and hits[0]["confidence"] == 68

    def test_tweezer_top_not_in_falling_market(self):
        c1 = _c(100, 110.0, 99, 108)
        c0 = _c(108.5, 110.2, 104, 105)
        h  = _splice(_falling_bars(), c1, c0)   # RSI < 55 → no match
        assert "Tweezer Top" not in _names(SVC._detect(SYM, h, NIFTY100))


# ══════════════════════════════════════════════════════════════════════════════
#  Three-Candle Patterns
# ══════════════════════════════════════════════════════════════════════════════

class TestThreeCandlePatterns:

    # ── Morning Star ──────────────────────────────────────────────────────────
    # c2 bear, small c1, c0 bull; c0.close > mid(c2); RSI < 55
    # Use smaller c2 body (mid=105) and modest c0.close=106 to prevent RSI spike.
    # Also use steep falling history so RSI stays well below 55.

    def test_morning_star_detected(self):
        # c2 bear body=10, mid=105; c1 body=1<4✓; c0 bull close=106>105✓; RSI≈17<<55✓
        c2 = _c(110, 112, 98, 100)   # bear, body=10, mid=(110+100)/2=105
        c1 = _c(100, 102, 98, 101)   # body=1 < 10*0.4=4 ✓
        c0 = _c(101, 108, 100, 106)  # bull, close=106>105 ✓
        h  = _splice(_falling_bars(start=200.0, step=2.0), c2, c1, c0)
        assert "Morning Star" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_morning_star_signal_is_call(self):
        c2 = _c(110, 112, 98, 100)
        c1 = _c(100, 102, 98, 101)
        c0 = _c(101, 108, 100, 106)
        h  = _splice(_falling_bars(start=200.0, step=2.0), c2, c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Morning Star"]
        assert hits and hits[0]["signal"] == "CALL"

    def test_morning_star_confidence_is_82(self):
        c2 = _c(110, 112, 98, 100)
        c1 = _c(100, 102, 98, 101)
        c0 = _c(101, 108, 100, 106)
        h  = _splice(_falling_bars(start=200.0, step=2.0), c2, c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Morning Star"]
        assert hits and hits[0]["confidence"] == 82

    def test_morning_star_not_detected_in_rising_market(self):
        c2 = _c(110, 112, 98, 100)
        c1 = _c(100, 102, 98, 101)
        c0 = _c(101, 108, 100, 106)
        h  = _splice(_rising_bars(), c2, c1, c0)   # RSI > 55 → condition fails
        assert "Morning Star" not in _names(SVC._detect(SYM, h, NIFTY100))

    def test_morning_star_not_detected_when_c2_is_bull(self):
        c2 = _c(100, 122, 98, 120)   # bull → wrong direction
        c1 = _c(120, 122, 118, 121)
        c0 = _c(121, 135, 120, 130)
        h  = _splice(_falling_bars(), c2, c1, c0)
        assert "Morning Star" not in _names(SVC._detect(SYM, h, NIFTY100))

    # ── Evening Star ──────────────────────────────────────────────────────────
    # c2 bull, small c1, c0 bear; c0.close < mid(c2); RSI > 55

    def test_evening_star_detected(self):
        # c2 bull body=20, mid=110; c1 body=1<8; c0 bear close=102<110✓; rising→RSI>55
        c2 = _c(100, 125, 98, 120)   # bull, body=20, mid=(100+120)/2=110
        c1 = _c(120, 122, 118, 121)  # body=1 < 8 ✓
        c0 = _c(120, 122, 98, 102)   # bear, close=102<110 ✓
        h  = _splice(_rising_bars(), c2, c1, c0)
        assert "Evening Star" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_evening_star_signal_is_put(self):
        c2 = _c(100, 125, 98, 120)
        c1 = _c(120, 122, 118, 121)
        c0 = _c(120, 122, 98, 102)
        h  = _splice(_rising_bars(), c2, c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Evening Star"]
        assert hits and hits[0]["signal"] == "PUT"

    def test_evening_star_confidence_is_82(self):
        c2 = _c(100, 125, 98, 120)
        c1 = _c(120, 122, 118, 121)
        c0 = _c(120, 122, 98, 102)
        h  = _splice(_rising_bars(), c2, c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Evening Star"]
        assert hits and hits[0]["confidence"] == 82

    def test_evening_star_not_in_falling_market(self):
        c2 = _c(100, 125, 98, 120)
        c1 = _c(120, 122, 118, 121)
        c0 = _c(120, 122, 98, 102)
        h  = _splice(_falling_bars(), c2, c1, c0)
        assert "Evening Star" not in _names(SVC._detect(SYM, h, NIFTY100))

    # ── Morning Doji Star ─────────────────────────────────────────────────────
    # c2 bear, c1 is doji, c0 bull; c0.close > mid(c2)

    def test_morning_doji_star_detected(self):
        # c2 bear mid=110; c1 doji; c0 bull close=118>110
        c2 = _c(120, 122, 98,  100)   # bear, mid=110
        c1 = _c(100, 105, 95,  100.5)  # doji: body=0.5, range=10 → 5%<10% ✓
        c0 = _c(102, 125, 101, 118)   # bull, close=118>110 ✓
        h  = _splice(_falling_bars(), c2, c1, c0)
        assert "Morning Doji Star" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_morning_doji_star_signal_is_call(self):
        c2 = _c(120, 122, 98, 100)
        c1 = _c(100, 105, 95, 100.5)
        c0 = _c(102, 125, 101, 118)
        h  = _splice(_falling_bars(), c2, c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Morning Doji Star"]
        assert hits and hits[0]["signal"] == "CALL"

    def test_morning_doji_star_confidence_is_84(self):
        c2 = _c(120, 122, 98, 100)
        c1 = _c(100, 105, 95, 100.5)
        c0 = _c(102, 125, 101, 118)
        h  = _splice(_falling_bars(), c2, c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Morning Doji Star"]
        assert hits and hits[0]["confidence"] == 84

    def test_morning_doji_star_not_when_c1_not_doji(self):
        c2 = _c(120, 122, 98, 100)
        c1 = _c(100, 115, 95, 108)   # body=8/range=20=40%>10% → NOT a doji
        c0 = _c(102, 125, 101, 118)
        h  = _splice(_falling_bars(), c2, c1, c0)
        assert "Morning Doji Star" not in _names(SVC._detect(SYM, h, NIFTY100))

    # ── Evening Doji Star ─────────────────────────────────────────────────────
    # c2 bull, c1 is doji, c0 bear; c0.close < mid(c2)

    def test_evening_doji_star_detected(self):
        c2 = _c(100, 125, 98,  120)   # bull, mid=110
        c1 = _c(120, 125, 115, 120.5)  # doji: body=0.5, range=10 → 5%<10% ✓
        c0 = _c(120, 122, 98,  102)   # bear, close=102<110 ✓
        h  = _splice(_rising_bars(), c2, c1, c0)
        assert "Evening Doji Star" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_evening_doji_star_signal_is_put(self):
        c2 = _c(100, 125, 98, 120)
        c1 = _c(120, 125, 115, 120.5)
        c0 = _c(120, 122, 98, 102)
        h  = _splice(_rising_bars(), c2, c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Evening Doji Star"]
        assert hits and hits[0]["signal"] == "PUT"

    def test_evening_doji_star_confidence_is_84(self):
        c2 = _c(100, 125, 98, 120)
        c1 = _c(120, 125, 115, 120.5)
        c0 = _c(120, 122, 98, 102)
        h  = _splice(_rising_bars(), c2, c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Evening Doji Star"]
        assert hits and hits[0]["confidence"] == 84

    # ── Three White Soldiers ──────────────────────────────────────────────────
    # 3 bull candles, each close > prior close, each body > atr*0.7

    def test_three_white_soldiers_detected(self):
        # Each body=7, ATR≈1 → 7>0.7✓; c0>c1>c2 closes ✓
        c2 = _c(100, 108, 99,  107)   # bull, body=7, close=107
        c1 = _c(107, 115, 106, 114)   # bull, body=7, close=114>107 ✓
        c0 = _c(114, 122, 113, 121)   # bull, body=7, close=121>114 ✓
        h  = _splice(_falling_bars(), c2, c1, c0)
        assert "Three White Soldiers" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_three_white_soldiers_signal_is_call(self):
        c2 = _c(100, 108, 99, 107)
        c1 = _c(107, 115, 106, 114)
        c0 = _c(114, 122, 113, 121)
        h  = _splice(_falling_bars(), c2, c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Three White Soldiers"]
        assert hits and hits[0]["signal"] == "CALL"

    def test_three_white_soldiers_confidence_is_80(self):
        c2 = _c(100, 108, 99, 107)
        c1 = _c(107, 115, 106, 114)
        c0 = _c(114, 122, 113, 121)
        h  = _splice(_falling_bars(), c2, c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Three White Soldiers"]
        assert hits and hits[0]["confidence"] == 80

    def test_three_white_soldiers_not_when_one_is_bear(self):
        c2 = _c(100, 108, 99, 107)
        c1 = _c(110, 115, 106, 104)   # bear — breaks the 3-bull requirement
        c0 = _c(114, 122, 113, 121)
        h  = _splice(_falling_bars(), c2, c1, c0)
        assert "Three White Soldiers" not in _names(SVC._detect(SYM, h, NIFTY100))

    # ── Three Black Crows ─────────────────────────────────────────────────────
    # 3 bear candles, each close < prior close, each body > atr*0.7

    def test_three_black_crows_detected(self):
        c2 = _c(121, 122, 113, 114)   # bear, body=7, close=114
        c1 = _c(114, 115, 106, 107)   # bear, body=7, close=107<114 ✓
        c0 = _c(107, 108, 99,  100)   # bear, body=7, close=100<107 ✓
        h  = _splice(_rising_bars(), c2, c1, c0)
        assert "Three Black Crows" in _names(SVC._detect(SYM, h, NIFTY100))

    def test_three_black_crows_signal_is_put(self):
        c2 = _c(121, 122, 113, 114)
        c1 = _c(114, 115, 106, 107)
        c0 = _c(107, 108, 99,  100)
        h  = _splice(_rising_bars(), c2, c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Three Black Crows"]
        assert hits and hits[0]["signal"] == "PUT"

    def test_three_black_crows_confidence_is_80(self):
        c2 = _c(121, 122, 113, 114)
        c1 = _c(114, 115, 106, 107)
        c0 = _c(107, 108, 99,  100)
        h  = _splice(_rising_bars(), c2, c1, c0)
        hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "Three Black Crows"]
        assert hits and hits[0]["confidence"] == 80

    def test_three_black_crows_not_when_close_not_descending(self):
        c2 = _c(121, 122, 113, 114)
        c1 = _c(114, 115, 106, 107)
        c0 = _c(107, 115, 106, 110)   # close=110 > c1.close=107 → not descending
        h  = _splice(_rising_bars(), c2, c1, c0)
        assert "Three Black Crows" not in _names(SVC._detect(SYM, h, NIFTY100))


# ══════════════════════════════════════════════════════════════════════════════
#  Indicator Patterns  (mocked)
# ══════════════════════════════════════════════════════════════════════════════

def _base_history_with_closes(closes: list[float]) -> list[dict]:
    """Build OHLCV history from a specific close-price list."""
    bars = []
    for c in closes:
        bars.append(_c(c - 0.5, c + 0.5, c - 0.5, c))
    return bars


def _mock_ema_factory(period_map: dict):
    """Return a side_effect function that maps (closes, period) → list."""
    def _ema(closes, period):
        return period_map.get(period, [closes[-1]])
    return _ema


def _mock_macd_factory(macd, signal, histogram):
    def _macd(_closes):
        return {"macd": macd, "signal": signal, "histogram": histogram}
    return _macd


# Patch targets
_RSI  = "app.services.patterns_service.calculate_rsi"
_EMA  = "app.services.patterns_service.calculate_ema"
_MACD = "app.services.patterns_service.calculate_macd"
_BB   = "app.services.patterns_service.calculate_bollinger_bands"
_ATR  = "app.services.patterns_service.calculate_atr"

_NEUTRAL_BB   = lambda _c, _p=20: {"upper": [110.0, 110.0], "middle": [100.0, 100.0], "lower": [90.0, 90.0]}
_NEUTRAL_ATR  = lambda _bars, _p=14: [2.0, 2.0]


class TestIndicatorPatterns:
    """All 12 indicator patterns, with indicator functions mocked."""

    # ── RSI Oversold Bounce ───────────────────────────────────────────────────
    # RSI < 35, price > ema50

    def test_rsi_oversold_bounce_detected(self):
        closes = [100.0] * 50
        h = _base_history_with_closes(closes)
        with patch(_RSI, return_value=[30.0, 30.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9: [100.0], 20: [100.0], 50: [90.0], 200: [80.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            result = SVC._detect(SYM, h, NIFTY100)
        assert "RSI Oversold Bounce" in _names(result)

    def test_rsi_oversold_bounce_not_when_rsi_above_35(self):
        closes = [100.0] * 50
        h = _base_history_with_closes(closes)
        with patch(_RSI, return_value=[40.0, 40.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9: [100.0], 20: [100.0], 50: [90.0], 200: [80.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            result = SVC._detect(SYM, h, NIFTY100)
        assert "RSI Oversold Bounce" not in _names(result)

    def test_rsi_oversold_bounce_signal_is_call(self):
        closes = [100.0] * 50
        h = _base_history_with_closes(closes)
        with patch(_RSI, return_value=[28.0, 28.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9: [100.0], 20: [100.0], 50: [90.0], 200: [80.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "RSI Oversold Bounce"]
        assert hits and hits[0]["signal"] == "CALL"

    def test_rsi_oversold_bounce_confidence_is_70(self):
        closes = [100.0] * 50
        h = _base_history_with_closes(closes)
        with patch(_RSI, return_value=[28.0, 28.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9: [100.0], 20: [100.0], 50: [90.0], 200: [80.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "RSI Oversold Bounce"]
        assert hits and hits[0]["confidence"] == 70

    # ── RSI Bullish Divergence ────────────────────────────────────────────────
    # price_low2 < price_low1, rsi_low2 > rsi_low1, RSI < 50

    def test_rsi_bullish_divergence_detected(self):
        # Closes: older 5 = [100,99,98,97,96], newer 5 = [95,94,93,92,91]
        # price_low1=96, price_low2=91 → lower lows ✓
        closes = [105.0] * 40 + [100,99,98,97,96, 95,94,93,92,91]
        h = _base_history_with_closes(closes)
        rsi_vals = [50.0] * 40 + [40,38,36,34,32, 33,35,37,39,41]  # len=50
        # rsi_low1=min([-10:-5])=32, rsi_low2=min([-5:])=33 → higher RSI lows ✓; lr=41<50 ✓
        with patch(_RSI, return_value=rsi_vals), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[91.0], 20:[91.0], 50:[92.0], 200:[80.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            result = SVC._detect(SYM, h, NIFTY100)
        assert "RSI Bullish Divergence" in _names(result)

    def test_rsi_bullish_divergence_signal_is_call(self):
        closes = [105.0] * 40 + [100,99,98,97,96, 95,94,93,92,91]
        h = _base_history_with_closes(closes)
        rsi_vals = [50.0] * 40 + [40,38,36,34,32, 33,35,37,39,41]
        with patch(_RSI, return_value=rsi_vals), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[91.0], 20:[91.0], 50:[92.0], 200:[80.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "RSI Bullish Divergence"]
        assert hits and hits[0]["signal"] == "CALL"

    def test_rsi_bullish_divergence_confidence_is_80(self):
        closes = [105.0] * 40 + [100,99,98,97,96, 95,94,93,92,91]
        h = _base_history_with_closes(closes)
        rsi_vals = [50.0] * 40 + [40,38,36,34,32, 33,35,37,39,41]
        with patch(_RSI, return_value=rsi_vals), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[91.0], 20:[91.0], 50:[92.0], 200:[80.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "RSI Bullish Divergence"]
        assert hits and hits[0]["confidence"] == 80

    # ── RSI Overbought ────────────────────────────────────────────────────────

    def test_rsi_overbought_detected(self):
        closes = [100.0] * 50
        h = _base_history_with_closes(closes)
        with patch(_RSI, return_value=[75.0, 75.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0], 50:[105.0], 200:[100.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            result = SVC._detect(SYM, h, NIFTY100)
        assert "RSI Overbought" in _names(result)

    def test_rsi_overbought_threshold_is_72(self):
        closes = [100.0] * 50
        h = _base_history_with_closes(closes)
        # Condition is strict lr > 72: 73 should trigger, 72 should NOT
        for rsi, expect in [(73.0, True), (72.0, False)]:
            with patch(_RSI, return_value=[rsi, rsi]), \
                 patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0], 50:[105.0], 200:[100.0]})), \
                 patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
                 patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
                result = SVC._detect(SYM, h, NIFTY100)
            found = "RSI Overbought" in _names(result)
            assert found == expect, f"RSI={rsi}: expected found={expect}, got {found}"

    def test_rsi_overbought_signal_is_put(self):
        closes = [100.0] * 50
        h = _base_history_with_closes(closes)
        with patch(_RSI, return_value=[75.0, 75.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0], 50:[105.0], 200:[100.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "RSI Overbought"]
        assert hits and hits[0]["signal"] == "PUT"

    def test_rsi_overbought_confidence_is_65(self):
        closes = [100.0] * 50
        h = _base_history_with_closes(closes)
        with patch(_RSI, return_value=[75.0, 75.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0], 50:[105.0], 200:[100.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "RSI Overbought"]
        assert hits and hits[0]["confidence"] == 65

    # ── RSI Bearish Divergence ────────────────────────────────────────────────
    # price_high2 > price_high1, rsi_high2 < rsi_high1, RSI > 55

    def test_rsi_bearish_divergence_detected(self):
        # Closes: older 5 = [100,101,102,103,104], newer 5 = [105,106,107,108,109]
        # price_high1=104, price_high2=109 → higher highs ✓
        closes = [100.0] * 40 + [100,101,102,103,104, 105,106,107,108,109]
        h = _base_history_with_closes(closes)
        # rsi_high1=max([-10:-5])=78, rsi_high2=max([-5:])=77 → lower RSI highs ✓; lr=69>55 ✓
        rsi_vals = [60.0] * 40 + [70,72,74,76,78, 77,75,73,71,69]
        with patch(_RSI, return_value=rsi_vals), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[109.0], 20:[109.0], 50:[105.0], 200:[100.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            result = SVC._detect(SYM, h, NIFTY100)
        assert "RSI Bearish Divergence" in _names(result)

    def test_rsi_bearish_divergence_signal_is_put(self):
        closes = [100.0] * 40 + [100,101,102,103,104, 105,106,107,108,109]
        h = _base_history_with_closes(closes)
        rsi_vals = [60.0] * 40 + [70,72,74,76,78, 77,75,73,71,69]
        with patch(_RSI, return_value=rsi_vals), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[109.0], 20:[109.0], 50:[105.0], 200:[100.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "RSI Bearish Divergence"]
        assert hits and hits[0]["signal"] == "PUT"

    def test_rsi_bearish_divergence_confidence_is_80(self):
        closes = [100.0] * 40 + [100,101,102,103,104, 105,106,107,108,109]
        h = _base_history_with_closes(closes)
        rsi_vals = [60.0] * 40 + [70,72,74,76,78, 77,75,73,71,69]
        with patch(_RSI, return_value=rsi_vals), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[109.0], 20:[109.0], 50:[105.0], 200:[100.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "RSI Bearish Divergence"]
        assert hits and hits[0]["confidence"] == 80

    # ── MACD Bullish Crossover ────────────────────────────────────────────────
    # pm < ps AND lm > ls

    def test_macd_bullish_crossover_detected(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0], 50:[100.0], 200:[100.0]})), \
             patch(_MACD, return_value={"macd": [0.5, 1.5], "signal": [1.0, 1.0], "histogram": [0.5, 0.5]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            result = SVC._detect(SYM, h, NIFTY100)
        assert "MACD Bullish Crossover" in _names(result)

    def test_macd_bullish_crossover_signal_is_call(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0], 50:[100.0], 200:[100.0]})), \
             patch(_MACD, return_value={"macd": [0.5, 1.5], "signal": [1.0, 1.0], "histogram": [0.5, 0.5]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "MACD Bullish Crossover"]
        assert hits and hits[0]["signal"] == "CALL"

    def test_macd_bullish_crossover_confidence_is_75(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0], 50:[100.0], 200:[100.0]})), \
             patch(_MACD, return_value={"macd": [0.5, 1.5], "signal": [1.0, 1.0], "histogram": [0.5, 0.5]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "MACD Bullish Crossover"]
        assert hits and hits[0]["confidence"] == 75

    def test_macd_bullish_crossover_not_when_already_above(self):
        # pm > ps → already above, no fresh crossover
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0], 50:[100.0], 200:[100.0]})), \
             patch(_MACD, return_value={"macd": [1.5, 2.0], "signal": [1.0, 1.0], "histogram": [0.5, 1.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            result = SVC._detect(SYM, h, NIFTY100)
        assert "MACD Bullish Crossover" not in _names(result)

    # ── MACD Bearish Crossover ────────────────────────────────────────────────
    # pm > ps AND lm < ls

    def test_macd_bearish_crossover_detected(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0], 50:[100.0], 200:[100.0]})), \
             patch(_MACD, return_value={"macd": [1.5, 0.5], "signal": [1.0, 1.0], "histogram": [-0.5, -0.5]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            result = SVC._detect(SYM, h, NIFTY100)
        assert "MACD Bearish Crossover" in _names(result)

    def test_macd_bearish_crossover_signal_is_put(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0], 50:[100.0], 200:[100.0]})), \
             patch(_MACD, return_value={"macd": [1.5, 0.5], "signal": [1.0, 1.0], "histogram": [-0.5, -0.5]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "MACD Bearish Crossover"]
        assert hits and hits[0]["signal"] == "PUT"

    def test_macd_bearish_crossover_confidence_is_75(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0], 50:[100.0], 200:[100.0]})), \
             patch(_MACD, return_value={"macd": [1.5, 0.5], "signal": [1.0, 1.0], "histogram": [-0.5, -0.5]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "MACD Bearish Crossover"]
        assert hits and hits[0]["confidence"] == 75

    # ── MACD Histogram Expanding (Bull) ───────────────────────────────────────
    # lh > 0, lh > ph, ph != 0, lh > ph*1.3

    def test_macd_histogram_expanding_bull_detected(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0], 50:[100.0], 200:[100.0]})), \
             patch(_MACD, return_value={"macd": [1.0, 1.0], "signal": [0.0, 0.0], "histogram": [1.0, 1.5]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            result = SVC._detect(SYM, h, NIFTY100)
        assert "MACD Histogram Expanding (Bull)" in _names(result)

    def test_macd_histogram_expanding_bull_signal_is_call(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0], 50:[100.0], 200:[100.0]})), \
             patch(_MACD, return_value={"macd": [1.0, 1.0], "signal": [0.0, 0.0], "histogram": [1.0, 1.5]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "MACD Histogram Expanding (Bull)"]
        assert hits and hits[0]["signal"] == "CALL"

    def test_macd_histogram_expanding_bull_not_when_ph_is_zero(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0], 50:[100.0], 200:[100.0]})), \
             patch(_MACD, return_value={"macd": [1.0, 1.0], "signal": [0.0, 0.0], "histogram": [0.0, 1.5]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            result = SVC._detect(SYM, h, NIFTY100)
        assert "MACD Histogram Expanding (Bull)" not in _names(result)

    def test_macd_histogram_expanding_bull_confidence_is_68(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0], 50:[100.0], 200:[100.0]})), \
             patch(_MACD, return_value={"macd": [1.0, 1.0], "signal": [0.0, 0.0], "histogram": [1.0, 1.5]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "MACD Histogram Expanding (Bull)"]
        assert hits and hits[0]["confidence"] == 68

    # ── MACD Histogram Expanding (Bear) ───────────────────────────────────────
    # lh < 0, ph != 0, |lh| > |ph|*1.3

    def test_macd_histogram_expanding_bear_detected(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0], 50:[100.0], 200:[100.0]})), \
             patch(_MACD, return_value={"macd": [-1.0, -1.0], "signal": [0.0, 0.0], "histogram": [-1.0, -1.5]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            result = SVC._detect(SYM, h, NIFTY100)
        assert "MACD Histogram Expanding (Bear)" in _names(result)

    def test_macd_histogram_expanding_bear_signal_is_put(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0], 50:[100.0], 200:[100.0]})), \
             patch(_MACD, return_value={"macd": [-1.0, -1.0], "signal": [0.0, 0.0], "histogram": [-1.0, -1.5]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "MACD Histogram Expanding (Bear)"]
        assert hits and hits[0]["signal"] == "PUT"

    def test_macd_histogram_expanding_bear_confidence_is_68(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0], 50:[100.0], 200:[100.0]})), \
             patch(_MACD, return_value={"macd": [-1.0, -1.0], "signal": [0.0, 0.0], "histogram": [-1.0, -1.5]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "MACD Histogram Expanding (Bear)"]
        assert hits and hits[0]["confidence"] == 68

    # ── EMA Golden Cross (20/50) ──────────────────────────────────────────────
    # pe20 < pe50 AND le20 > le50

    def test_ema_golden_cross_20_50_detected(self):
        h = _flat_bars()
        # pe20=90 < pe50=95; le20=101 > le50=100 → crossover ✓
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[90.0, 101.0], 50:[95.0, 100.0], 200:[80.0, 82.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            result = SVC._detect(SYM, h, NIFTY100)
        assert "EMA Golden Cross (20/50)" in _names(result)

    def test_ema_golden_cross_20_50_signal_is_call(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[90.0, 101.0], 50:[95.0, 100.0], 200:[80.0, 82.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "EMA Golden Cross (20/50)"]
        assert hits and hits[0]["signal"] == "CALL"

    def test_ema_golden_cross_20_50_confidence_is_82(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[90.0, 101.0], 50:[95.0, 100.0], 200:[80.0, 82.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "EMA Golden Cross (20/50)"]
        assert hits and hits[0]["confidence"] == 82

    # ── EMA Death Cross (20/50) ───────────────────────────────────────────────
    # pe20 > pe50 AND le20 < le50

    def test_ema_death_cross_20_50_detected(self):
        h = _flat_bars()
        # pe20=105 > pe50=100; le20=95 < le50=100 → crossover ✓
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[105.0, 95.0], 50:[100.0, 100.0], 200:[110.0, 110.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            result = SVC._detect(SYM, h, NIFTY100)
        assert "EMA Death Cross (20/50)" in _names(result)

    def test_ema_death_cross_20_50_signal_is_put(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[105.0, 95.0], 50:[100.0, 100.0], 200:[110.0, 110.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "EMA Death Cross (20/50)"]
        assert hits and hits[0]["signal"] == "PUT"

    def test_ema_death_cross_20_50_confidence_is_82(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[105.0, 95.0], 50:[100.0, 100.0], 200:[110.0, 110.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "EMA Death Cross (20/50)"]
        assert hits and hits[0]["confidence"] == 82

    # ── EMA Golden Cross (50/200) ─────────────────────────────────────────────
    # pe50 < pe200 AND le50 > le200

    def test_ema_golden_cross_50_200_detected(self):
        h = _flat_bars()
        # pe50=90 < pe200=95; le50=101 > le200=100 ✓
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0, 100.0], 50:[90.0, 101.0], 200:[95.0, 100.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            result = SVC._detect(SYM, h, NIFTY100)
        assert "EMA Golden Cross (50/200)" in _names(result)

    def test_ema_golden_cross_50_200_signal_is_call(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0, 100.0], 50:[90.0, 101.0], 200:[95.0, 100.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "EMA Golden Cross (50/200)"]
        assert hits and hits[0]["signal"] == "CALL"

    def test_ema_golden_cross_50_200_confidence_is_88(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0, 100.0], 50:[90.0, 101.0], 200:[95.0, 100.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "EMA Golden Cross (50/200)"]
        assert hits and hits[0]["confidence"] == 88

    # ── EMA Death Cross (50/200) ──────────────────────────────────────────────
    # pe50 > pe200 AND le50 < le200

    def test_ema_death_cross_50_200_detected(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0, 100.0], 50:[105.0, 95.0], 200:[100.0, 100.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            result = SVC._detect(SYM, h, NIFTY100)
        assert "EMA Death Cross (50/200)" in _names(result)

    def test_ema_death_cross_50_200_signal_is_put(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0, 100.0], 50:[105.0, 95.0], 200:[100.0, 100.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "EMA Death Cross (50/200)"]
        assert hits and hits[0]["signal"] == "PUT"

    def test_ema_death_cross_50_200_confidence_is_88(self):
        h = _flat_bars()
        with patch(_RSI, return_value=[50.0, 50.0]), \
             patch(_EMA, side_effect=_mock_ema_factory({9:[100.0], 20:[100.0, 100.0], 50:[105.0, 95.0], 200:[100.0, 100.0]})), \
             patch(_MACD, return_value={"macd": [0.0, 0.0], "signal": [0.0, 0.0], "histogram": [0.0, 0.0]}), \
             patch(_BB, _NEUTRAL_BB), patch(_ATR, _NEUTRAL_ATR):
            hits = [p for p in SVC._detect(SYM, h, NIFTY100) if p["pattern"] == "EMA Death Cross (50/200)"]
        assert hits and hits[0]["confidence"] == 88


# ══════════════════════════════════════════════════════════════════════════════
#  get_patterns() Filtering Tests
# ══════════════════════════════════════════════════════════════════════════════

def _run(coro):
    """Run an async coroutine synchronously in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_mock_patterns():
    """Return a set of patterns covering all universes, signals, categories."""
    return [
        _mk("RELIANCE", "NIFTY100",  "Hammer",              "BULLISH", "CALL", 72, 2500, "d", "Candlestick",   2600, 2450),
        _mk("RELIANCE", "NIFTY100",  "Shooting Star",       "BEARISH", "PUT",  72, 2500, "d", "Candlestick"),
        _mk("RELIANCE", "NIFTY100",  "Doji",                "NEUTRAL", "WAIT", 55, 2500, "d", "Candlestick"),
        _mk("TCS",      "NIFTY100",  "Bullish Engulfing",   "BULLISH", "CALL", 78, 3400, "d", "Two-Candle",    3500, 3300),
        _mk("TCS",      "NIFTY100",  "Bearish Engulfing",   "BEARISH", "PUT",  78, 3400, "d", "Two-Candle"),
        _mk("INFY",     "NIFTY100",  "Morning Star",        "BULLISH", "CALL", 82, 1500, "d", "Three-Candle",  1600, 1450),
        _mk("INFY",     "NIFTY100",  "RSI Overbought",      "BEARISH", "PUT",  65, 1500, "d", "Indicator"),
        _mk("AURO",     "MIDCAP",    "MACD Bullish Cross",  "BULLISH", "CALL", 75, 900,  "d", "Indicator",     950,  870),
        _mk("AURO",     "MIDCAP",    "Inside Bar",          "NEUTRAL", "WAIT", 60, 900,  "d", "Candlestick"),
        _mk("HAPPY",    "SMALLCAP",  "Three Black Crows",   "BEARISH", "PUT",  80, 500,  "d", "Three-Candle"),
        _mk("HAPPY",    "SMALLCAP",  "EMA Golden Cross",    "BULLISH", "CALL", 82, 500,  "d", "Indicator",     540,  480),
        _mk("HAPPY",    "SMALLCAP",  "Piercing Line",       "BULLISH", "CALL", 70, 500,  "d", "Two-Candle",    520,  480),
    ]


class TestGetPatternsFiltering:

    MOCK_PATTERNS = _make_mock_patterns()

    def _run_with_cache(self, universe=None, signal=None, category=None):
        with patch.object(_ps_mod, "_cached_patterns", self.MOCK_PATTERNS):
            return _run(SVC.get_patterns(universe, signal, category))

    # ── No filter ─────────────────────────────────────────────────────────────

    def test_no_filter_returns_all_patterns(self):
        result = self._run_with_cache()
        assert result["totalPatterns"] == len(self.MOCK_PATTERNS)

    def test_no_filter_has_correct_structure(self):
        result = self._run_with_cache()
        for key in ("lastScanTime", "totalPatterns", "callSignals", "putSignals",
                    "categories", "patterns", "topCalls", "topPuts"):
            assert key in result, f"Missing key: {key}"

    def test_no_filter_call_and_put_counts_correct(self):
        result = self._run_with_cache()
        calls = sum(1 for p in self.MOCK_PATTERNS if p["signal"] == "CALL")
        puts  = sum(1 for p in self.MOCK_PATTERNS if p["signal"] == "PUT")
        assert result["callSignals"] == calls
        assert result["putSignals"]  == puts

    # ── Universe filter ───────────────────────────────────────────────────────

    def test_universe_filter_nifty100(self):
        result = self._run_with_cache(universe="NIFTY100")
        assert all(p["universe"] == "NIFTY100" for p in result["patterns"])

    def test_universe_filter_midcap(self):
        result = self._run_with_cache(universe="MIDCAP")
        assert all(p["universe"] == "MIDCAP" for p in result["patterns"])

    def test_universe_filter_smallcap(self):
        result = self._run_with_cache(universe="SMALLCAP")
        assert all(p["universe"] == "SMALLCAP" for p in result["patterns"])

    def test_universe_filter_case_insensitive(self):
        # "nifty100" (lowercase) should match "NIFTY100"
        result = self._run_with_cache(universe="nifty100")
        assert all(p["universe"] == "NIFTY100" for p in result["patterns"])

    def test_universe_filter_midcap_count(self):
        midcap_count = sum(1 for p in self.MOCK_PATTERNS if p["universe"] == "MIDCAP")
        result = self._run_with_cache(universe="MIDCAP")
        assert result["totalPatterns"] == midcap_count

    def test_universe_filter_unknown_returns_empty(self):
        result = self._run_with_cache(universe="UNKNOWN_UNIVERSE")
        assert result["totalPatterns"] == 0

    # ── Signal filter ─────────────────────────────────────────────────────────

    def test_signal_filter_call(self):
        result = self._run_with_cache(signal="CALL")
        assert all(p["signal"] == "CALL" for p in result["patterns"])

    def test_signal_filter_put(self):
        result = self._run_with_cache(signal="PUT")
        assert all(p["signal"] == "PUT" for p in result["patterns"])

    def test_signal_filter_wait(self):
        result = self._run_with_cache(signal="WAIT")
        assert all(p["signal"] == "WAIT" for p in result["patterns"])

    def test_signal_filter_case_insensitive(self):
        result_upper = self._run_with_cache(signal="CALL")
        result_lower = self._run_with_cache(signal="call")
        assert result_upper["totalPatterns"] == result_lower["totalPatterns"]

    def test_signal_filter_call_count_matches(self):
        expected = sum(1 for p in self.MOCK_PATTERNS if p["signal"] == "CALL")
        result   = self._run_with_cache(signal="CALL")
        assert result["totalPatterns"] == expected

    # ── Category filter ───────────────────────────────────────────────────────

    def test_category_filter_candlestick(self):
        result = self._run_with_cache(category="Candlestick")
        assert all("candlestick" in (p.get("category") or "").lower()
                   for p in result["patterns"])

    def test_category_filter_two_candle(self):
        result = self._run_with_cache(category="Two-Candle")
        assert all("two-candle" in (p.get("category") or "").lower()
                   for p in result["patterns"])

    def test_category_filter_three_candle(self):
        result = self._run_with_cache(category="Three-Candle")
        assert all("three-candle" in (p.get("category") or "").lower()
                   for p in result["patterns"])

    def test_category_filter_indicator(self):
        result = self._run_with_cache(category="Indicator")
        assert all("indicator" in (p.get("category") or "").lower()
                   for p in result["patterns"])

    def test_category_filter_case_insensitive(self):
        result = self._run_with_cache(category="INDICATOR")
        expected = sum(1 for p in self.MOCK_PATTERNS
                       if "indicator" in (p.get("category") or "").lower())
        assert result["totalPatterns"] == expected

    # ── Combined filters ──────────────────────────────────────────────────────

    def test_universe_and_signal_filter(self):
        result = self._run_with_cache(universe="NIFTY100", signal="CALL")
        assert all(p["universe"] == "NIFTY100" and p["signal"] == "CALL"
                   for p in result["patterns"])

    def test_universe_and_category_filter(self):
        result = self._run_with_cache(universe="NIFTY100", category="Candlestick")
        assert all(p["universe"] == "NIFTY100" and
                   "candlestick" in (p.get("category") or "").lower()
                   for p in result["patterns"])

    def test_all_three_filters_combined(self):
        result = self._run_with_cache(universe="NIFTY100", signal="CALL",
                                       category="Two-Candle")
        for p in result["patterns"]:
            assert p["universe"] == "NIFTY100"
            assert p["signal"]   == "CALL"
            assert "two-candle"  in (p.get("category") or "").lower()

    def test_top_calls_limited_to_15(self):
        # Even with many patterns, topCalls should be ≤ 15
        result = self._run_with_cache()
        assert len(result["topCalls"]) <= 15

    def test_top_puts_limited_to_15(self):
        result = self._run_with_cache()
        assert len(result["topPuts"]) <= 15

    def test_top_calls_are_all_call_signals(self):
        result = self._run_with_cache()
        assert all(p["signal"] == "CALL" for p in result["topCalls"])

    def test_top_puts_are_all_put_signals(self):
        result = self._run_with_cache()
        assert all(p["signal"] == "PUT" for p in result["topPuts"])


# ══════════════════════════════════════════════════════════════════════════════
#  Universe × Category × Signal Exhaustive Combination Matrix
# ══════════════════════════════════════════════════════════════════════════════

class TestUniverseCategorySignalMatrix:
    """
    The _detect() method tags every result with universe (passed in) and
    category (hard-coded per pattern).  This matrix verifies that filtering
    by each (universe, category, signal) triple gives consistent, non-overlapping
    subsets and that the union covers the whole unfiltered result.
    """

    ALL_UNIVERSES  = ["NIFTY100", "MIDCAP", "SMALLCAP"]
    ALL_CATEGORIES = ["Candlestick", "Two-Candle", "Three-Candle", "Indicator"]
    ALL_SIGNALS    = ["CALL", "PUT", "WAIT"]

    MOCK = _make_mock_patterns()

    def _filter(self, universe=None, signal=None, category=None):
        with patch.object(_ps_mod, "_cached_patterns", self.MOCK):
            return _run(SVC.get_patterns(universe, signal, category))["patterns"]

    def test_all_universe_filters_are_disjoint(self):
        """Patterns from NIFTY100, MIDCAP, SMALLCAP should not overlap."""
        sets = [
            set(p["symbol"] + p["pattern"] for p in self._filter(universe=u))
            for u in self.ALL_UNIVERSES
        ]
        for i in range(len(sets)):
            for j in range(i + 1, len(sets)):
                assert sets[i].isdisjoint(sets[j]), \
                    f"Universes {self.ALL_UNIVERSES[i]} and {self.ALL_UNIVERSES[j]} overlap"

    def test_universe_union_covers_all(self):
        """The union of all per-universe subsets equals the unfiltered set."""
        unfiltered = {p["symbol"] + p["pattern"] for p in self._filter()}
        union = set()
        for u in self.ALL_UNIVERSES:
            union |= {p["symbol"] + p["pattern"] for p in self._filter(universe=u)}
        assert union == unfiltered

    def test_signal_filters_are_disjoint(self):
        """CALL, PUT, WAIT subsets should be disjoint."""
        sets = {sig: set(p["symbol"] + p["pattern"] for p in self._filter(signal=sig))
                for sig in self.ALL_SIGNALS}
        sigs = self.ALL_SIGNALS
        for i in range(len(sigs)):
            for j in range(i + 1, len(sigs)):
                assert sets[sigs[i]].isdisjoint(sets[sigs[j]]), \
                    f"Signals {sigs[i]} and {sigs[j]} overlap"

    def test_signal_union_covers_all(self):
        """CALL ∪ PUT ∪ WAIT = unfiltered."""
        unfiltered = {p["symbol"] + p["pattern"] for p in self._filter()}
        union = set()
        for sig in self.ALL_SIGNALS:
            union |= {p["symbol"] + p["pattern"] for p in self._filter(signal=sig)}
        assert union == unfiltered

    def test_category_filters_are_disjoint(self):
        """Patterns in different categories should not overlap."""
        sets = {
            cat: set(p["symbol"] + p["pattern"] for p in self._filter(category=cat))
            for cat in self.ALL_CATEGORIES
        }
        cats = self.ALL_CATEGORIES
        for i in range(len(cats)):
            for j in range(i + 1, len(cats)):
                assert sets[cats[i]].isdisjoint(sets[cats[j]]), \
                    f"Categories '{cats[i]}' and '{cats[j]}' overlap"

    def test_category_union_covers_all(self):
        """Candlestick ∪ Two-Candle ∪ Three-Candle ∪ Indicator = unfiltered."""
        unfiltered = {p["symbol"] + p["pattern"] for p in self._filter()}
        union = set()
        for cat in self.ALL_CATEGORIES:
            union |= {p["symbol"] + p["pattern"] for p in self._filter(category=cat)}
        assert union == unfiltered

    def test_every_universe_category_combination(self):
        """For each (universe, category) pair, result is a subset of both."""
        for u in self.ALL_UNIVERSES:
            for cat in self.ALL_CATEGORIES:
                result = self._filter(universe=u, category=cat)
                for p in result:
                    assert p["universe"] == u, f"Universe mismatch in ({u},{cat})"
                    assert cat.lower() in (p.get("category") or "").lower(), \
                        f"Category mismatch in ({u},{cat})"

    def test_every_universe_signal_combination(self):
        """For each (universe, signal) pair, result is a subset of both."""
        for u in self.ALL_UNIVERSES:
            for sig in self.ALL_SIGNALS:
                result = self._filter(universe=u, signal=sig)
                for p in result:
                    assert p["universe"] == u
                    assert p["signal"]   == sig

    def test_every_category_signal_combination(self):
        """For each (category, signal) pair, result respects both dimensions."""
        for cat in self.ALL_CATEGORIES:
            for sig in self.ALL_SIGNALS:
                result = self._filter(category=cat, signal=sig)
                for p in result:
                    assert cat.lower() in (p.get("category") or "").lower()
                    assert p["signal"] == sig

    def test_full_triple_combination_matrix(self):
        """Full (universe, category, signal) matrix: 3×4×3 = 36 combinations."""
        for u in self.ALL_UNIVERSES:
            for cat in self.ALL_CATEGORIES:
                for sig in self.ALL_SIGNALS:
                    result = self._filter(universe=u, category=cat, signal=sig)
                    for p in result:
                        assert p["universe"] == u
                        assert cat.lower() in (p.get("category") or "").lower()
                        assert p["signal"]   == sig

    def test_nifty100_has_more_patterns_than_smallcap_in_mock(self):
        """NIFTY100 in our mock has more patterns than SMALLCAP."""
        n100 = len(self._filter(universe="NIFTY100"))
        smc  = len(self._filter(universe="SMALLCAP"))
        assert n100 > smc

    def test_call_patterns_have_target_price_or_symbol(self):
        """Every CALL pattern must carry a symbol."""
        calls = self._filter(signal="CALL")
        for p in calls:
            assert p.get("symbol"), "CALL pattern missing symbol"

    def test_put_patterns_have_put_signal_type(self):
        """All PUT patterns after filtering must be bearish or signal=PUT."""
        puts = self._filter(signal="PUT")
        for p in puts:
            assert p["signal"] == "PUT"

    def test_wait_patterns_have_no_target_price(self):
        """WAIT patterns in our mock should not have a target price."""
        waits = self._filter(signal="WAIT")
        for p in waits:
            assert p.get("targetPrice") is None, \
                f"WAIT pattern '{p['pattern']}' unexpectedly has targetPrice"

    def test_confidence_values_are_within_valid_range(self):
        """All pattern confidences must be between 0 and 100."""
        all_patterns = self._filter()
        for p in all_patterns:
            assert 0 <= p["confidence"] <= 100, \
                f"Confidence {p['confidence']} out of range for {p['pattern']}"

    def test_timeframe_is_always_1d(self):
        """Every pattern must declare 1D timeframe."""
        for p in self._filter():
            assert p["timeframe"] == "1D"

    def test_detected_at_present_on_all_patterns(self):
        """Every pattern must have a detectedAt timestamp."""
        for p in self._filter():
            assert p.get("detectedAt"), f"Missing detectedAt on {p['pattern']}"

    def test_category_counts_sum_to_total(self):
        """Sum of per-category counts must equal the total pattern count."""
        total = len(self._filter())
        category_sum = sum(
            len(self._filter(category=cat)) for cat in self.ALL_CATEGORIES
        )
        assert category_sum == total

    def test_signal_counts_sum_to_total(self):
        """Sum of per-signal counts must equal the total pattern count."""
        total = len(self._filter())
        signal_sum = sum(len(self._filter(signal=sig)) for sig in self.ALL_SIGNALS)
        assert signal_sum == total

    def test_universe_counts_sum_to_total(self):
        """Sum of per-universe counts must equal the total pattern count."""
        total = len(self._filter())
        universe_sum = sum(
            len(self._filter(universe=u)) for u in self.ALL_UNIVERSES
        )
        assert universe_sum == total
