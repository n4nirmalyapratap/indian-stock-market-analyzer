"""
Shared fixtures and helpers for all backend unit tests.
"""
import sys
import os

# Make sure the backend root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


# ── Deterministic OHLCV candle fixtures ──────────────────────────────────────

def make_candle(o: float, h: float, l: float, c: float, v: float = 1_000_000) -> dict:
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


@pytest.fixture
def flat_prices():
    """100 identical close prices — all indicators should converge to a constant."""
    return [100.0] * 100


@pytest.fixture
def linear_rising():
    """Strictly rising prices 1..100."""
    return [float(i) for i in range(1, 101)]


@pytest.fixture
def linear_falling():
    """Strictly falling prices 100..1."""
    return [float(i) for i in range(100, 0, -1)]


@pytest.fixture
def sine_prices():
    """60 prices following a sine wave — useful for oscillator sanity checks."""
    import math
    return [100 + 10 * math.sin(2 * math.pi * i / 20) for i in range(60)]


@pytest.fixture
def trending_ohlcv():
    """50-day uptrending OHLCV bars with realistic spreads."""
    bars = []
    price = 1000.0
    for i in range(50):
        price += 5.0
        bars.append(make_candle(
            o=price - 3,
            h=price + 7,
            l=price - 8,
            c=price,
            v=500_000 + i * 1_000,
        ))
    return bars


@pytest.fixture
def hammer_candle():
    """
    Classic hammer: small body at the top, long lower shadow (≥2x body),
    tiny upper shadow (< body). Body must be > 10% of range (not a doji).
    open=100, high=106, low=82, close=104
      body = |104-100| = 4
      range = 106-82 = 24 → body/range = 16.7% > 10% ✓ (not a doji)
      lower = min(100,104)-82 = 18 > 2*4=8 ✓
      upper = 106-max(100,104) = 2 < 4 ✓
    """
    return make_candle(o=100, h=106, l=82, c=104)


@pytest.fixture
def shooting_star_candle():
    """
    Classic shooting star: small body at the bottom, long upper shadow (≥2x body),
    tiny lower shadow (< body). Body must be > 10% of range (not a doji).
    open=100, high=116, low=98, close=102
      body = |102-100| = 2
      range = 116-98 = 18 → body/range = 11.1% > 10% ✓ (not a doji)
      upper = 116-max(100,102) = 14 > 2*2=4 ✓
      lower = min(100,102)-98 = 2 = body (using ≤ in test)
    """
    return make_candle(o=100, h=116, l=98, c=102)


@pytest.fixture
def doji_candle():
    """Doji: body ≤ 10% of full range."""
    return make_candle(o=100, h=110, l=90, c=100.5)


@pytest.fixture
def bullish_marubozu():
    """Full bullish marubozu: open == low, close == high."""
    return make_candle(o=100, h=115, l=100, c=115)


@pytest.fixture
def bearish_marubozu():
    """Full bearish marubozu: open == high, close == low."""
    return make_candle(o=115, h=115, l=100, c=100)
