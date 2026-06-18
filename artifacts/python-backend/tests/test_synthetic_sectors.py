"""
Unit tests for the Hyper-Granular Sector Rotation synthetic engine.

These cover the *pure-math* core of `synthetic_sectors_service` — the parts
that turn real per-constituent history + NSE delivery into a sub-industry
synthetic index, breadth, relative strength and delivery build-up. All DB /
network I/O is excluded; these functions are deliberately side-effect-free so
they can be exercised directly without a Postgres connection.

Async tests use `asyncio.run` + `AsyncMock` (no pytest-asyncio), matching the
rest of the suite.
"""
from __future__ import annotations

import asyncio
import datetime as dt
from unittest.mock import AsyncMock

import pytest

from app.services import synthetic_sectors_service as sss


# ── _ema: standard EMA, None when too few points ─────────────────────────────


def test_ema_returns_none_when_fewer_points_than_span():
    assert sss._ema([1.0, 2.0, 3.0], span=5) is None


def test_ema_of_flat_series_equals_the_constant():
    # A perfectly flat series has EMA == the constant for any span.
    assert sss._ema([100.0] * 60, span=50) == pytest.approx(100.0)


def test_ema_seeds_with_sma_then_smooths():
    # Reproduce the implementation exactly: SMA seed over first `span`, then
    # recursively smooth with k = 2/(span+1).
    values = [float(i) for i in range(1, 11)]  # 1..10
    span = 3
    k = 2.0 / (span + 1.0)
    expected = sum(values[:span]) / span
    for v in values[span:]:
        expected = v * k + expected * (1 - k)
    assert sss._ema(values, span) == pytest.approx(expected)


# ── compute_group_metrics: cap-weighted return, breadth, delivery ────────────


def _stock(symbol: str, cap: float) -> dict:
    return {"symbol": symbol, "market_cap": cap}


def test_compute_group_metrics_market_cap_weights_returns():
    """Daily return is market-cap weighted, NOT a simple average."""
    constituents = [_stock("A", 9_000.0), _stock("B", 1_000.0), _stock("C", 1_000.0)]
    signals = {
        "A": {"daily_return_pct": 10.0, "above_50ema": True},
        "B": {"daily_return_pct": 0.0, "above_50ema": True},
        "C": {"daily_return_pct": 0.0, "above_50ema": False},
    }
    m = sss.compute_group_metrics(constituents, signals, delivery=None)
    # (10*9000 + 0*1000 + 0*1000) / 11000 = 8.1818...
    assert m["daily_return_pct"] == pytest.approx(90_000.0 / 11_000.0)
    # A simple mean would be 3.33% — confirm we are NOT doing that.
    assert m["daily_return_pct"] != pytest.approx(10.0 / 3.0)


def test_compute_group_metrics_breadth_is_pct_above_50ema():
    constituents = [_stock("A", 1.0), _stock("B", 1.0), _stock("C", 1.0), _stock("D", 1.0)]
    signals = {
        "A": {"daily_return_pct": 1.0, "above_50ema": True},
        "B": {"daily_return_pct": 1.0, "above_50ema": True},
        "C": {"daily_return_pct": 1.0, "above_50ema": True},
        "D": {"daily_return_pct": 1.0, "above_50ema": False},
    }
    m = sss.compute_group_metrics(constituents, signals, delivery=None)
    assert m["breadth_50ema_pct"] == pytest.approx(75.0)
    assert m["constituent_count"] == 4


def test_compute_group_metrics_breadth_ignores_unknown_50ema_position():
    """Constituents with above_50ema=None are excluded from the breadth
    denominator (thin history shouldn't drag breadth toward 0)."""
    constituents = [_stock("A", 1.0), _stock("B", 1.0), _stock("C", 1.0)]
    signals = {
        "A": {"daily_return_pct": 1.0, "above_50ema": True},
        "B": {"daily_return_pct": 1.0, "above_50ema": False},
        "C": {"daily_return_pct": 1.0, "above_50ema": None},  # thin history
    }
    m = sss.compute_group_metrics(constituents, signals, delivery=None)
    # Only A and B counted → 1/2 = 50%, NOT 1/3 = 33%.
    assert m["breadth_50ema_pct"] == pytest.approx(50.0)


def test_compute_group_metrics_avg_delivery_only_over_present_symbols():
    constituents = [_stock("A", 1.0), _stock("B", 1.0), _stock("C", 1.0)]
    signals = {s: {"daily_return_pct": 0.0, "above_50ema": True} for s in ("A", "B", "C")}
    delivery = {"A": 80.0, "B": 60.0}  # C absent from the archive
    m = sss.compute_group_metrics(constituents, signals, delivery)
    assert m["avg_delivery_pct"] == pytest.approx(70.0)


def test_compute_group_metrics_delivery_none_when_archive_unavailable():
    constituents = [_stock("A", 1.0), _stock("B", 1.0), _stock("C", 1.0)]
    signals = {s: {"daily_return_pct": 0.0, "above_50ema": True} for s in ("A", "B", "C")}
    m = sss.compute_group_metrics(constituents, signals, delivery=None)
    assert m["avg_delivery_pct"] is None  # honest unavailable, not 0


def test_compute_group_metrics_skips_zero_and_missing_cap():
    """A constituent with no/zero market cap can't carry weight and must be
    excluded from the index entirely."""
    constituents = [_stock("A", 5_000.0), _stock("B", 0.0), _stock("C", None)]
    signals = {
        "A": {"daily_return_pct": 4.0, "above_50ema": True},
        "B": {"daily_return_pct": 99.0, "above_50ema": True},
        "C": {"daily_return_pct": 99.0, "above_50ema": True},
    }
    # Only A is usable → falls below _MIN_CONSTITUENTS (3) → None.
    assert sss.compute_group_metrics(constituents, signals, delivery=None) is None


def test_compute_group_metrics_none_below_min_constituents():
    constituents = [_stock("A", 1.0), _stock("B", 1.0)]
    signals = {
        "A": {"daily_return_pct": 1.0, "above_50ema": True},
        "B": {"daily_return_pct": 1.0, "above_50ema": True},
    }
    # 2 usable < _MIN_CONSTITUENTS (default 3)
    assert sss.compute_group_metrics(constituents, signals, delivery=None) is None


def test_compute_group_metrics_skips_constituents_without_signal():
    """A classified stock with no history signal is simply not counted."""
    constituents = [_stock("A", 1.0), _stock("B", 1.0), _stock("C", 1.0), _stock("D", 1.0)]
    signals = {
        "A": {"daily_return_pct": 2.0, "above_50ema": True},
        "B": {"daily_return_pct": 2.0, "above_50ema": True},
        "C": {"daily_return_pct": 2.0, "above_50ema": True},
        # D has no signal (history fetch failed)
    }
    m = sss.compute_group_metrics(constituents, signals, delivery=None)
    assert m["constituent_count"] == 3
    assert m["daily_return_pct"] == pytest.approx(2.0)


# ── relative_strength_30d: date-aligned, true 30D window ─────────────────────


def _dated(values: list[float], end: dt.date = dt.date(2026, 6, 1)) -> list[tuple]:
    """Build a (date, value) series on consecutive calendar days ending at
    `end`, so all points fall inside the trailing 30-day RS window."""
    n = len(values)
    return [(end - dt.timedelta(days=(n - 1 - i)), v) for i, v in enumerate(values)]


def _ramp(start: float, end: float, n: int) -> list[float]:
    if n == 1:
        return [start]
    step = (end - start) / (n - 1)
    return [start + step * i for i in range(n)]


def test_relative_strength_outperformance_positive():
    # index 100→110 (+10%), nifty 100→104 (+4%) over an aligned 20-session window.
    index = _dated(_ramp(100.0, 110.0, 20))
    nifty = _dated(_ramp(100.0, 104.0, 20))
    assert sss.relative_strength_30d(index, nifty) == pytest.approx(6.0)


def test_relative_strength_underperformance_negative():
    index = _dated(_ramp(100.0, 102.0, 20))   # +2%
    nifty = _dated(_ramp(100.0, 108.0, 20))   # +8%
    assert sss.relative_strength_30d(index, nifty) == pytest.approx(-6.0)


def test_relative_strength_none_when_too_few_aligned_observations():
    # Only 10 aligned sessions (< _RS_MIN_OBS) → not a real 30D RS.
    index = _dated(_ramp(100.0, 110.0, 10))
    nifty = _dated(_ramp(100.0, 104.0, 10))
    assert sss.relative_strength_30d(index, nifty) is None


def test_relative_strength_aligns_on_dates_and_drops_mismatches():
    """A sub-industry skipped on some sessions must be compared only over the
    dates it shares with Nifty — never against Nifty sessions it lacks."""
    end = dt.date(2026, 6, 1)
    nifty = _dated(_ramp(100.0, 104.0, 20), end=end)
    nifty_dates = [d for d, _ in nifty]
    # index shares only 19 of the 20 nifty dates, PLUS an extra stale earlier
    # date that nifty doesn't have (must be ignored, not compared).
    index = [(nifty_dates[i], v) for i, v in enumerate(_ramp(100.0, 110.0, 20)) if i != 0]
    index.insert(0, (end - dt.timedelta(days=120), 50.0))  # stale, unaligned
    rs = sss.relative_strength_30d(index, nifty)
    assert rs is not None
    # Aligned window starts at nifty_dates[1]; both endpoints come from aligned
    # dates only, so the stale 50.0 never enters the math.
    assert rs == pytest.approx(
        (110.0 - _ramp(100.0, 110.0, 20)[1]) / _ramp(100.0, 110.0, 20)[1] * 100.0
        - (104.0 - _ramp(100.0, 104.0, 20)[1]) / _ramp(100.0, 104.0, 20)[1] * 100.0
    )


def test_relative_strength_restricts_to_trailing_30_calendar_days():
    """Points older than the 30-day window are excluded, so a huge early move
    doesn't leak into the 30D figure."""
    end = dt.date(2026, 6, 1)
    # 18 recent aligned sessions inside the window, flat → RS 0.
    recent_idx = _dated(_ramp(100.0, 100.0, 18), end=end)
    recent_nifty = _dated(_ramp(100.0, 100.0, 18), end=end)
    # Prepend a far-older point (60 days back) with a wild value — must be dropped.
    old = end - dt.timedelta(days=60)
    index = [(old, 10.0)] + recent_idx
    nifty = [(old, 10.0)] + recent_nifty
    assert sss.relative_strength_30d(index, nifty) == pytest.approx(0.0)


def test_relative_strength_none_when_series_empty():
    assert sss.relative_strength_30d([], _dated(_ramp(100.0, 105.0, 20))) is None
    assert sss.relative_strength_30d(_dated(_ramp(100.0, 105.0, 20)), []) is None


def test_relative_strength_none_when_base_nonpositive():
    index = _dated([0.0] + _ramp(100.0, 110.0, 19))
    nifty = _dated(_ramp(100.0, 105.0, 20))
    assert sss.relative_strength_30d(index, nifty) is None


# ── delivery_buildup: today vs 20-DMA, +15% threshold ────────────────────────


def test_delivery_buildup_true_above_threshold():
    # 70 vs 20-DMA 60 → ratio 1.166 ≥ 1.15
    assert sss.delivery_buildup(70.0, 60.0) is True


def test_delivery_buildup_false_at_or_below_threshold():
    # exactly +14% → below 1.15 threshold
    assert sss.delivery_buildup(57.0, 50.0) is False


def test_delivery_buildup_true_exactly_at_threshold():
    # exactly +15% → inclusive boundary
    assert sss.delivery_buildup(57.5, 50.0) is True


def test_delivery_buildup_none_when_data_missing():
    assert sss.delivery_buildup(None, 60.0) is None
    assert sss.delivery_buildup(70.0, None) is None
    assert sss.delivery_buildup(70.0, 0.0) is None


# ── _cap_category: market-cap bucketing ──────────────────────────────────────


def test_cap_category_buckets():
    assert sss._cap_category(2_000_000_000_000) == "Large-Cap"   # ₹2L Cr
    assert sss._cap_category(sss._LARGE_CAP_MIN) == "Large-Cap"  # boundary
    assert sss._cap_category(500_000_000_000) == "Mid-Cap"       # ₹50k Cr
    assert sss._cap_category(sss._MID_CAP_MIN) == "Mid-Cap"      # boundary
    assert sss._cap_category(10_000_000_000) == "Small-Cap"      # ₹1k Cr
    assert sss._cap_category(None) is None


# ── _latest_trading_day: 16:00 IST seal + weekend rollback ───────────────────


def _ist(y, m, d, hh, mm) -> dt.datetime:
    # When `now` is passed explicitly, _latest_trading_day treats it as
    # already-IST (it only adds the offset when deriving from utcnow()).
    return dt.datetime(y, m, d, hh, mm)


def test_latest_trading_day_before_4pm_uses_prior_day():
    # Thursday 2026-06-04, 10:00 IST → not yet sealed → Wednesday 06-03
    now = _ist(2026, 6, 4, 10, 0)
    assert sss._latest_trading_day(now) == dt.date(2026, 6, 3)


def test_latest_trading_day_after_4pm_uses_same_day():
    # Thursday 2026-06-04, 18:00 IST → sealed → Thursday 06-04
    now = _ist(2026, 6, 4, 18, 0)
    assert sss._latest_trading_day(now) == dt.date(2026, 6, 4)


def test_latest_trading_day_weekend_rolls_back_to_friday():
    # Sunday 2026-06-07, 18:00 IST → rolls back to Friday 06-05
    now = _ist(2026, 6, 7, 18, 0)
    assert sss._latest_trading_day(now) == dt.date(2026, 6, 5)


def test_latest_trading_day_monday_morning_rolls_to_friday():
    # Monday 2026-06-08, 09:00 IST → not sealed → Sunday → roll back to Friday 06-05
    now = _ist(2026, 6, 8, 9, 0)
    assert sss._latest_trading_day(now) == dt.date(2026, 6, 5)


# ── _constituent_signal: derive daily return + 50-EMA position ────────────────


def _bars(closes: list[float]) -> list[dict]:
    return [{"close": c} for c in closes]


def test_constituent_signal_computes_daily_return_and_breadth():
    yahoo = AsyncMock()
    # 60 rising closes → last > 50-EMA, and a clear +ve last daily return.
    closes = [float(100 + i) for i in range(60)]
    yahoo.get_historical_data.return_value = _bars(closes)
    sem = asyncio.Semaphore(2)

    sig = asyncio.run(sss._constituent_signal(yahoo, "TEST.NS", sem))
    assert sig is not None
    prev, last = closes[-2], closes[-1]
    assert sig["daily_return_pct"] == pytest.approx((last - prev) / prev * 100.0)
    assert sig["above_50ema"] is True
    assert sig["last_close"] == pytest.approx(last)


def test_constituent_signal_none_when_history_too_thin():
    yahoo = AsyncMock()
    yahoo.get_historical_data.return_value = _bars([100.0])  # only 1 bar
    sem = asyncio.Semaphore(2)
    assert asyncio.run(sss._constituent_signal(yahoo, "TEST.NS", sem)) is None


def test_constituent_signal_above_50ema_none_when_under_50_bars():
    yahoo = AsyncMock()
    closes = [float(100 + i) for i in range(10)]  # < 50 → EMA None
    yahoo.get_historical_data.return_value = _bars(closes)
    sem = asyncio.Semaphore(2)
    sig = asyncio.run(sss._constituent_signal(yahoo, "TEST.NS", sem))
    assert sig is not None
    assert sig["above_50ema"] is None  # honest: can't judge without 50 bars


def test_constituent_signal_none_on_history_exception():
    yahoo = AsyncMock()
    yahoo.get_historical_data.side_effect = RuntimeError("yahoo down")
    sem = asyncio.Semaphore(2)
    assert asyncio.run(sss._constituent_signal(yahoo, "TEST.NS", sem)) is None
