"""Candle pattern primitives — single source of truth.

Two consumers
-------------
  1. `patterns_service.py` — the scheduled scanner that emits richly-
     scored pattern detections (`{symbol, pattern, confidence, …}`) for
     the Patterns page. Uses these primitives plus ATR / location
     context for its confidence model.
  2. `scanners_service.py` — the user-facing scanner DSL. Uses these
     primitives directly as boolean indicators (BULLISH_ENGULFING, etc.)
     so a user can write conditions like
         BULLISH_ENGULFING eq 1 AND VOLUME_RATIO > 150
     in their custom scanner.

Why a separate module
---------------------
Previously the pattern logic lived inline in `patterns_service.py`. The
scanner DSL couldn't reach it without a circular import, and copying
the conditions into the scanner would have silently drifted over time
("which BULLISH_ENGULFING does this app actually detect?"). Pulling
the primitives into `app/lib` makes them stateless, reusable, and free
of any service-layer coupling.

Naming convention
-----------------
`is_<pattern>(...)` for shape-only checks (boolean, no context).
ATR / range-position dependent variants (Hammer-at-bottom, Shooting
Star-at-top) stay in `patterns_service.py` — those are detection-time
"is this in a meaningful spot?" decisions, not pattern primitives.
"""
from __future__ import annotations


# ── Candle primitives ───────────────────────────────────────────────────────


def body(c: dict) -> float:
    """Absolute body height = |close - open|."""
    return abs(c["close"] - c["open"])


def upper_wick(c: dict) -> float:
    """Wick above the body."""
    return c["high"] - max(c["open"], c["close"])


def lower_wick(c: dict) -> float:
    """Wick below the body."""
    return min(c["open"], c["close"]) - c["low"]


def candle_range(c: dict) -> float:
    """Total range = high - low."""
    return c["high"] - c["low"]


def is_bull(c: dict) -> bool:
    """Green candle — close > open."""
    return c["close"] > c["open"]


def is_bear(c: dict) -> bool:
    """Red candle — close < open."""
    return c["close"] < c["open"]


def midpoint(c: dict) -> float:
    """Mid-body price — halfway between open and close."""
    return (c["open"] + c["close"]) / 2.0


# ── Single-candle patterns ──────────────────────────────────────────────────


def is_doji(c: dict) -> bool:
    """Body is ≤ 10% of the total range. The "I have no idea" candle —
    indecision; gains meaning only with context (location, follow-up
    candle)."""
    rng = candle_range(c)
    return rng > 0 and body(c) <= rng * 0.1


def is_dragonfly_doji(c: dict) -> bool:
    """Doji whose lower wick is >70% of the range. Bullish-leaning
    indecision; sellers tried and failed."""
    if not is_doji(c):
        return False
    rng = candle_range(c)
    return rng > 0 and lower_wick(c) > rng * 0.7


def is_gravestone_doji(c: dict) -> bool:
    """Doji whose upper wick is >70% of the range. Bearish-leaning;
    buyers tried and failed."""
    if not is_doji(c):
        return False
    rng = candle_range(c)
    return rng > 0 and upper_wick(c) > rng * 0.7


def is_hammer(c: dict) -> bool:
    """Lower wick > 2× body AND upper wick < 50% body. The shape only —
    callers who want "hammer at the bottom of a downtrend" (the real
    signal) layer their own location check on top."""
    b = body(c)
    if b <= 0:
        return False
    return lower_wick(c) > 2 * b and upper_wick(c) < 0.5 * b


def is_inverted_hammer(c: dict) -> bool:
    """Mirror of Hammer — upper wick > 2× body, lower < 50% body, bull
    close. Shape-only check."""
    b = body(c)
    if b <= 0:
        return False
    return (
        upper_wick(c) > 2 * b
        and lower_wick(c) < 0.5 * b
        and is_bull(c)
    )


def is_shooting_star(c: dict) -> bool:
    """Same shape as inverted hammer (long upper wick, short lower) but
    appears after an uptrend — patterns_service adds the location
    context. Here we only check the shape."""
    b = body(c)
    if b <= 0:
        return False
    return upper_wick(c) > 2 * b and lower_wick(c) < 0.5 * b


def is_hanging_man(c: dict) -> bool:
    """Hammer shape but bearish close — same as is_hammer plus is_bear.
    Location context (at the top of an uptrend) lives in
    patterns_service."""
    b = body(c)
    if b <= 0:
        return False
    return (
        lower_wick(c) > 2 * b
        and upper_wick(c) < 0.5 * b
        and is_bear(c)
    )


def is_bullish_marubozu(c: dict) -> bool:
    """Big green body that's >90% of the bar's range — buyers in
    control from open to close."""
    r = candle_range(c)
    return r > 0 and is_bull(c) and body(c) > r * 0.9


def is_bearish_marubozu(c: dict) -> bool:
    """Symmetric of bullish marubozu."""
    r = candle_range(c)
    return r > 0 and is_bear(c) and body(c) > r * 0.9


def is_spinning_top(c: dict) -> bool:
    """Small body relative to range, with wicks longer than the body
    on both sides — indecision with active two-way trading."""
    if is_doji(c):
        return False
    r = candle_range(c)
    b = body(c)
    if r <= 0:
        return False
    return (
        b < r * 0.3
        and lower_wick(c) > b
        and upper_wick(c) > b
    )


# ── Two-candle patterns ─────────────────────────────────────────────────────


def is_bullish_engulfing(c0: dict, c1: dict) -> bool:
    """c0 (today) is a green candle whose body completely contains the
    body of c1 (yesterday's red candle).

    Math: yesterday was bear, today is bull, today's open ≤ yesterday's
    close, today's close ≥ yesterday's open."""
    return (
        is_bear(c1)
        and is_bull(c0)
        and c0["open"]  < c1["close"]
        and c0["close"] > c1["open"]
    )


def is_bearish_engulfing(c0: dict, c1: dict) -> bool:
    """Mirror — c0 red engulfs c1 green."""
    return (
        is_bull(c1)
        and is_bear(c0)
        and c0["open"]  > c1["close"]
        and c0["close"] < c1["open"]
    )


def is_bullish_harami(c0: dict, c1: dict) -> bool:
    """Today's small body sits INSIDE yesterday's big red body — a
    pause / potential reversal."""
    return (
        is_bear(c1)
        and is_bull(c0)
        and c0["open"]  > c1["close"]
        and c0["close"] < c1["open"]
        and body(c0) < body(c1) * 0.6
    )


def is_bearish_harami(c0: dict, c1: dict) -> bool:
    """Mirror — small green inside big red."""
    return (
        is_bull(c1)
        and is_bear(c0)
        and c0["open"]  < c1["close"]
        and c0["close"] > c1["open"]
        and body(c0) < body(c1) * 0.6
    )


def is_inside_bar(c0: dict, c1: dict) -> bool:
    """Today's high/low are both contained inside yesterday's range —
    consolidation, breakout candidate."""
    return (
        c0["high"] < c1["high"]
        and c0["low"]  > c1["low"]
        and body(c0) < body(c1) * 0.6
    )


def is_outside_bar(c0: dict, c1: dict) -> bool:
    """Today's high/low both exceed yesterday's — volatility expansion."""
    return (
        c0["high"] > c1["high"]
        and c0["low"]  < c1["low"]
        and body(c0) > body(c1) * 1.5
    )


def is_piercing_line(c0: dict, c1: dict) -> bool:
    """After a red candle, a green one opens below the prior low and
    closes above the prior body's midpoint but below the prior open."""
    return (
        is_bear(c1)
        and is_bull(c0)
        and c0["open"]  < c1["low"]
        and c0["close"] > midpoint(c1)
        and c0["close"] < c1["open"]
    )


def is_dark_cloud_cover(c0: dict, c1: dict) -> bool:
    """Bearish mirror of piercing line."""
    return (
        is_bull(c1)
        and is_bear(c0)
        and c0["open"]  > c1["high"]
        and c0["close"] < midpoint(c1)
        and c0["close"] > c1["open"]
    )


def is_tweezer_bottom(c0: dict, c1: dict, *, tolerance_pct: float = 0.003) -> bool:
    """Two consecutive lows that are within 0.3% of each other, with
    the second candle bullish — double-bottom rejection of a level."""
    if not c1["low"] or c1["low"] <= 0:
        return False
    diff = abs(c0["low"] - c1["low"]) / c1["low"]
    return (
        diff < tolerance_pct
        and is_bear(c1)
        and is_bull(c0)
    )


def is_tweezer_top(c0: dict, c1: dict, *, tolerance_pct: float = 0.003) -> bool:
    """Symmetric of tweezer bottom — two matching highs, second red."""
    if not c1["high"] or c1["high"] <= 0:
        return False
    diff = abs(c0["high"] - c1["high"]) / c1["high"]
    return (
        diff < tolerance_pct
        and is_bull(c1)
        and is_bear(c0)
    )
