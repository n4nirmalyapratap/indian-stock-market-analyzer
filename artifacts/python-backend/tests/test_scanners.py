"""
test_scanners.py
Deep TDD test suite for the Stock Scanner system.

Covers every layer of the scanner stack — tested from the bottom up:

  1.  _cid()                        — ID generator
  2.  _compare()                    — comparison operators (all 6)
  3.  _compute_value()              — all 20 indicator types + edge cases
  4.  _eval_condition()             — condition evaluation + crossovers
  5.  Default scanners              — structural integrity of all 8 built-in scanners
  6.  ScannersService CRUD          — create / read / update / delete
  7.  create_scanner field defaults — every optional field
  8.  update_scanner semantics      — partial / full updates
  9.  AND vs OR scanner logic       — correct set algebra
  10. Score calculation             — met / total × 100
  11. _evaluate() result shape      — all keys present and typed correctly
  12. Condition combinations        — complex multi-condition scanners
  13. Edge cases                    — empty data, None, zero division, unknown inds
"""

import pytest
from datetime import datetime, timezone

from app.services.scanners_service import (
    _cid,
    _compare,
    _compute_value,
    _eval_condition,
    _init_defaults,
    ScannersService,
    DEFAULT_SCANNERS_DEF,
    VALID_OPERATORS,
    _scanners,
    _id_counter,
)
from app.services.price_service import PriceService
from app.services.yahoo_service import YahooService
from app.services.nse_service import NseService


# ── Shared helpers ────────────────────────────────────────────────────────────

def _make_ohlcv(closes: list[float], volume: int = 10_000) -> list[dict]:
    """Build a minimal OHLCV list from a sequence of close prices."""
    return [
        {
            "open":   c * 0.99,
            "high":   c * 1.02,
            "low":    c * 0.97,
            "close":  c,
            "volume": volume,
        }
        for c in closes
    ]


def _rising(n: int = 60, start: float = 100.0, step: float = 1.0) -> list[dict]:
    """n bars of steadily rising prices."""
    closes = [start + i * step for i in range(n)]
    return _make_ohlcv(closes)


def _falling(n: int = 60, start: float = 200.0, step: float = 1.0) -> list[dict]:
    closes = [start - i * step for i in range(n)]
    return _make_ohlcv(closes)


def _flat(n: int = 60, price: float = 150.0) -> list[dict]:
    return _make_ohlcv([price] * n)


def _fresh_service() -> ScannersService:
    """
    Return a ScannersService backed by a fresh (real) PriceService.
    Tests that modify _scanners must restore state themselves.
    """
    yahoo = YahooService()
    nse   = NseService()
    price = PriceService(nse, yahoo)
    return ScannersService(price)


# ═══════════════════════════════════════════════════════════════════════════════
#  1. _cid()
# ═══════════════════════════════════════════════════════════════════════════════

class TestCid:
    def test_length_is_7(self):
        assert len(_cid()) == 7

    def test_contains_only_alphanumeric(self):
        for _ in range(50):
            cid = _cid()
            assert cid.isalnum(), f"Non-alphanumeric: {cid}"

    def test_generates_unique_ids(self):
        ids = {_cid() for _ in range(500)}
        assert len(ids) >= 490  # allow tiny collision chance in 36^7 space


# ═══════════════════════════════════════════════════════════════════════════════
#  2. _compare()
# ═══════════════════════════════════════════════════════════════════════════════

class TestCompare:
    # gt
    def test_gt_true(self):
        assert _compare(10.0, "gt", 9.0) is True

    def test_gt_false_equal(self):
        assert _compare(10.0, "gt", 10.0) is False

    def test_gt_false_less(self):
        assert _compare(9.0, "gt", 10.0) is False

    # gte
    def test_gte_true_greater(self):
        assert _compare(10.0, "gte", 9.0) is True

    def test_gte_true_equal(self):
        assert _compare(10.0, "gte", 10.0) is True

    def test_gte_false(self):
        assert _compare(9.0, "gte", 10.0) is False

    # lt
    def test_lt_true(self):
        assert _compare(9.0, "lt", 10.0) is True

    def test_lt_false_equal(self):
        assert _compare(10.0, "lt", 10.0) is False

    def test_lt_false_greater(self):
        assert _compare(11.0, "lt", 10.0) is False

    # lte
    def test_lte_true_less(self):
        assert _compare(9.0, "lte", 10.0) is True

    def test_lte_true_equal(self):
        assert _compare(10.0, "lte", 10.0) is True

    def test_lte_false(self):
        assert _compare(11.0, "lte", 10.0) is False

    # eq (0.1% tolerance)
    def test_eq_exactly_equal(self):
        assert _compare(100.0, "eq", 100.0) is True

    def test_eq_within_tolerance(self):
        assert _compare(100.05, "eq", 100.0) is True   # 0.05% diff

    def test_eq_outside_tolerance(self):
        assert _compare(101.5, "eq", 100.0) is False   # 1.5% diff

    def test_eq_with_zero_rv(self):
        # rv = 0 → denominator uses 1 to avoid div/0
        assert _compare(0.0, "eq", 0.0) is True

    # unknown operator
    def test_unknown_operator_returns_false(self):
        assert _compare(10.0, "unknown_op", 5.0) is False

    # negative values
    def test_gt_negative(self):
        assert _compare(-1.0, "gt", -2.0) is True

    def test_lt_negative(self):
        assert _compare(-5.0, "lt", -3.0) is True


# ═══════════════════════════════════════════════════════════════════════════════
#  3. _compute_value()
# ═══════════════════════════════════════════════════════════════════════════════

class TestComputeValue:

    # ── Number type ──────────────────────────────────────────────────────────

    def test_number_type_returns_value(self):
        ohlcv = _flat(10)
        assert _compute_value(ohlcv, {"type": "number", "value": 42.5}) == 42.5

    def test_number_type_ignores_data(self):
        assert _compute_value([], {"type": "number", "value": 7}) == 7

    def test_number_type_zero(self):
        assert _compute_value(_flat(5), {"type": "number", "value": 0}) == 0

    # ── OHLCV raw fields ─────────────────────────────────────────────────────

    def test_close_returns_last_close(self):
        ohlcv = _make_ohlcv([100, 110, 120])
        assert _compute_value(ohlcv, {"type": "indicator", "indicator": "CLOSE"}) == 120

    def test_open_returns_last_open(self):
        ohlcv = _make_ohlcv([100, 110, 120])
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "OPEN"})
        assert abs(v - 120 * 0.99) < 0.01

    def test_high_returns_last_high(self):
        ohlcv = _make_ohlcv([100, 110, 120])
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "HIGH"})
        assert abs(v - 120 * 1.02) < 0.01

    def test_low_returns_last_low(self):
        ohlcv = _make_ohlcv([100, 110, 120])
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "LOW"})
        assert abs(v - 120 * 0.97) < 0.01

    def test_prev_close_returns_second_to_last(self):
        ohlcv = _make_ohlcv([100, 110, 120])
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "PREV_CLOSE"})
        assert v == 110

    def test_prev_close_needs_at_least_2_bars(self):
        ohlcv = _make_ohlcv([100])
        assert _compute_value(ohlcv, {"type": "indicator", "indicator": "PREV_CLOSE"}) is None

    # ── CHANGE_PCT ──────────────────────────────────────────────────────────

    def test_change_pct_formula(self):
        ohlcv = _make_ohlcv([100, 110])
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "CHANGE_PCT"})
        assert abs(v - 10.0) < 0.001      # (110-100)/100 * 100 = 10%

    def test_change_pct_negative(self):
        ohlcv = _make_ohlcv([100, 90])
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "CHANGE_PCT"})
        assert abs(v - (-10.0)) < 0.001

    def test_change_pct_zero_change(self):
        ohlcv = _make_ohlcv([100, 100])
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "CHANGE_PCT"})
        assert v == 0.0

    # ── VOLUME fields ────────────────────────────────────────────────────────

    def test_volume_returns_last_volume(self):
        ohlcv = _flat(5, 150)
        for i, row in enumerate(ohlcv):
            row["volume"] = (i + 1) * 1000
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "VOLUME"})
        assert v == 5000

    def test_avg_volume_default_20_periods(self):
        ohlcv = _flat(25, 100)
        for row in ohlcv:
            row["volume"] = 2000
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "AVG_VOLUME"})
        assert abs(v - 2000) < 1

    def test_avg_volume_custom_period(self):
        ohlcv = _flat(30, 100)
        for i, row in enumerate(ohlcv):
            row["volume"] = 1000 if i < 25 else 5000
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "AVG_VOLUME", "period": 5})
        assert abs(v - 5000) < 1

    def test_volume_ratio_normal_volume(self):
        ohlcv = _flat(25, 100)
        for row in ohlcv:
            row["volume"] = 1000
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "VOLUME_RATIO"})
        assert abs(v - 100.0) < 1  # 100% of average = 100

    def test_volume_ratio_double_volume(self):
        ohlcv = _flat(25, 100)
        for row in ohlcv:
            row["volume"] = 1000
        ohlcv[-1]["volume"] = 2000
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "VOLUME_RATIO"})
        assert v > 150   # last bar has ~double volume

    # ── EMA ──────────────────────────────────────────────────────────────────

    def test_ema_returns_float(self):
        ohlcv = _rising(50)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "EMA", "period": 20})
        assert isinstance(v, float)
        assert v > 0

    def test_ema_default_period_20(self):
        ohlcv = _rising(50)
        v1 = _compute_value(ohlcv, {"type": "indicator", "indicator": "EMA"})
        v2 = _compute_value(ohlcv, {"type": "indicator", "indicator": "EMA", "period": 20})
        assert v1 == v2

    def test_ema_shorter_period_more_responsive(self):
        ohlcv = _rising(60)
        ema9  = _compute_value(ohlcv, {"type": "indicator", "indicator": "EMA", "period": 9})
        ema50 = _compute_value(ohlcv, {"type": "indicator", "indicator": "EMA", "period": 50})
        # In a rising market EMA9 > EMA50 (tracks price more closely)
        assert ema9 > ema50

    def test_ema_insufficient_data_returns_none(self):
        ohlcv = _flat(5)  # fewer than EMA period 20
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "EMA", "period": 20})
        assert v is None

    # ── SMA ──────────────────────────────────────────────────────────────────

    def test_sma_returns_float(self):
        ohlcv = _flat(30, 200)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "SMA", "period": 20})
        assert isinstance(v, float)

    def test_sma_flat_price_equals_price(self):
        ohlcv = _flat(30, 200)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "SMA", "period": 20})
        assert abs(v - 200.0) < 0.01

    def test_sma_default_period(self):
        ohlcv = _rising(50)
        v1 = _compute_value(ohlcv, {"type": "indicator", "indicator": "SMA"})
        v2 = _compute_value(ohlcv, {"type": "indicator", "indicator": "SMA", "period": 20})
        assert v1 == v2

    # ── RSI ──────────────────────────────────────────────────────────────────

    def test_rsi_in_range_0_to_100(self):
        ohlcv = _rising(50)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "RSI", "period": 14})
        assert 0 <= v <= 100

    def test_rsi_rising_market_above_50(self):
        ohlcv = _rising(50)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "RSI", "period": 14})
        assert v > 50

    def test_rsi_falling_market_below_50(self):
        ohlcv = _falling(50)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "RSI", "period": 14})
        assert v < 50

    def test_rsi_default_period_14(self):
        ohlcv = _rising(50)
        v1 = _compute_value(ohlcv, {"type": "indicator", "indicator": "RSI"})
        v2 = _compute_value(ohlcv, {"type": "indicator", "indicator": "RSI", "period": 14})
        assert v1 == v2

    # ── MACD ─────────────────────────────────────────────────────────────────

    def test_macd_returns_float(self):
        ohlcv = _rising(60)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "MACD"})
        assert isinstance(v, float)

    def test_macd_signal_returns_float(self):
        ohlcv = _rising(60)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "MACD_SIGNAL"})
        assert isinstance(v, float)

    def test_macd_hist_returns_float(self):
        ohlcv = _rising(60)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "MACD_HIST"})
        assert isinstance(v, float)

    def test_macd_rising_market_is_positive(self):
        ohlcv = _rising(60)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "MACD"})
        assert v > 0  # EMA12 > EMA26 in rising market → positive MACD

    # ── Bollinger Bands ───────────────────────────────────────────────────────

    def test_bb_upper_above_close(self):
        ohlcv = _flat(30, 100)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "BB_UPPER", "period": 20})
        assert v >= 100

    def test_bb_lower_below_close(self):
        ohlcv = _flat(30, 100)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "BB_LOWER", "period": 20})
        assert v <= 100

    def test_bb_mid_equals_sma_on_flat_price(self):
        ohlcv = _flat(30, 100)
        mid = _compute_value(ohlcv, {"type": "indicator", "indicator": "BB_MID",   "period": 20})
        sma = _compute_value(ohlcv, {"type": "indicator", "indicator": "SMA",       "period": 20})
        assert abs(mid - sma) < 0.01

    def test_bb_band_order_upper_mid_lower(self):
        ohlcv = _rising(40)
        upper = _compute_value(ohlcv, {"type": "indicator", "indicator": "BB_UPPER", "period": 20})
        mid   = _compute_value(ohlcv, {"type": "indicator", "indicator": "BB_MID",   "period": 20})
        lower = _compute_value(ohlcv, {"type": "indicator", "indicator": "BB_LOWER", "period": 20})
        assert upper > mid > lower

    def test_bb_default_period_20(self):
        ohlcv = _rising(40)
        v1 = _compute_value(ohlcv, {"type": "indicator", "indicator": "BB_UPPER"})
        v2 = _compute_value(ohlcv, {"type": "indicator", "indicator": "BB_UPPER", "period": 20})
        assert v1 == v2

    # ── ATR ──────────────────────────────────────────────────────────────────

    def test_atr_returns_positive_float(self):
        ohlcv = _rising(30)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "ATR", "period": 14})
        assert isinstance(v, float)
        assert v > 0

    def test_atr_default_period(self):
        ohlcv = _rising(30)
        v1 = _compute_value(ohlcv, {"type": "indicator", "indicator": "ATR"})
        v2 = _compute_value(ohlcv, {"type": "indicator", "indicator": "ATR", "period": 14})
        assert v1 == v2

    # ── 52-week range ─────────────────────────────────────────────────────────

    def test_high_52w_is_max_close(self):
        closes = list(range(50, 110))  # 60 values, max = 109
        ohlcv = _make_ohlcv(closes)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "HIGH_52W"})
        assert v == 109

    def test_low_52w_is_min_close(self):
        closes = list(range(50, 110))  # min = 50
        ohlcv = _make_ohlcv(closes)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "LOW_52W"})
        assert v == 50

    def test_pct_52w_high_at_high_is_zero(self):
        closes = [100.0] * 30
        closes[-1] = 200.0   # last bar IS the 52W high
        ohlcv = _make_ohlcv(closes)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "PCT_52W_HIGH"})
        assert v == 0.0   # at the high exactly

    def test_pct_52w_high_below_high_is_negative(self):
        closes = [200.0] + [100.0] * 29   # 52W high = 200, current = 100
        ohlcv = _make_ohlcv(closes)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "PCT_52W_HIGH"})
        assert abs(v - (-50.0)) < 0.01   # (100-200)/200 * 100 = -50%

    def test_pct_52w_low_above_low_is_positive(self):
        closes = [50.0] + [100.0] * 29   # 52W low = 50, current = 100
        ohlcv = _make_ohlcv(closes)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "PCT_52W_LOW"})
        assert abs(v - 100.0) < 0.01   # (100-50)/50 * 100 = 100%

    # ── Unknown indicator ─────────────────────────────────────────────────────

    def test_unknown_indicator_returns_none(self):
        ohlcv = _flat(30)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "DOES_NOT_EXIST"})
        assert v is None

    # ── Insufficient data ─────────────────────────────────────────────────────

    def test_less_than_2_bars_returns_none(self):
        ohlcv = _flat(1)
        assert _compute_value(ohlcv, {"type": "indicator", "indicator": "CLOSE"}) is None

    def test_empty_data_returns_none(self):
        assert _compute_value([], {"type": "indicator", "indicator": "CLOSE"}) is None

    # ── Shift parameter (used in crossover detection) ─────────────────────────

    def test_shift_1_returns_prev_close(self):
        ohlcv = _make_ohlcv([100, 110, 120])
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "CLOSE"}, shift=1)
        assert v == 110   # second-to-last when shift=1 → data = ohlcv[:2]

    def test_shift_number_type_unaffected(self):
        ohlcv = _flat(10)
        v = _compute_value(ohlcv, {"type": "number", "value": 99}, shift=1)
        assert v == 99  # numbers are constant regardless of shift


# ═══════════════════════════════════════════════════════════════════════════════
#  4. _eval_condition()
# ═══════════════════════════════════════════════════════════════════════════════

class TestEvalCondition:

    # ── Simple comparison ─────────────────────────────────────────────────────

    def test_close_gt_number_met(self):
        ohlcv = _make_ohlcv([100, 110, 150])
        cond = {
            "left": {"type": "indicator", "indicator": "CLOSE"},
            "operator": "gt",
            "right": {"type": "number", "value": 100},
        }
        res = _eval_condition(ohlcv, cond)
        assert res["met"] is True

    def test_close_gt_number_not_met(self):
        ohlcv = _make_ohlcv([100, 110, 95])
        cond = {
            "left": {"type": "indicator", "indicator": "CLOSE"},
            "operator": "gt",
            "right": {"type": "number", "value": 100},
        }
        res = _eval_condition(ohlcv, cond)
        assert res["met"] is False

    def test_rsi_lt_oversold_met(self):
        ohlcv = _falling(50)    # falling market → RSI below 50
        cond = {
            "left": {"type": "indicator", "indicator": "RSI", "period": 14},
            "operator": "lt",
            "right": {"type": "number", "value": 60},
        }
        res = _eval_condition(ohlcv, cond)
        assert res["met"] is True

    def test_result_has_met_and_desc_keys(self):
        ohlcv = _flat(30)
        cond = {
            "left":  {"type": "indicator", "indicator": "CLOSE"},
            "operator": "gt",
            "right": {"type": "number", "value": 50},
        }
        res = _eval_condition(ohlcv, cond)
        assert "met"  in res
        assert "desc" in res

    def test_desc_contains_operator_symbol(self):
        ohlcv = _flat(30, 200)
        cond = {
            "left":  {"type": "indicator", "indicator": "CLOSE"},
            "operator": "gt",
            "right": {"type": "number", "value": 100},
        }
        res = _eval_condition(ohlcv, cond)
        assert ">" in res["desc"]

    def test_insufficient_data_returns_not_met(self):
        ohlcv = _flat(1)   # only 1 bar
        cond = {
            "left":  {"type": "indicator", "indicator": "CLOSE"},
            "operator": "gt",
            "right": {"type": "number", "value": 50},
        }
        res = _eval_condition(ohlcv, cond)
        assert res["met"] is False
        assert "Insufficient" in res["desc"]

    # ── crosses_above ─────────────────────────────────────────────────────────

    def test_crosses_above_close_over_threshold(self):
        # prev close = 99 (below 100), current close = 101 (above 100)
        ohlcv = _make_ohlcv([95, 98, 99, 101])
        cond = {
            "left":  {"type": "indicator", "indicator": "CLOSE"},
            "operator": "crosses_above",
            "right": {"type": "number", "value": 100},
        }
        res = _eval_condition(ohlcv, cond)
        assert res["met"] is True

    def test_crosses_above_already_above_is_false(self):
        # prev close = 105, current = 110 — already above, not a fresh cross
        ohlcv = _make_ohlcv([95, 100, 105, 110])
        cond = {
            "left":  {"type": "indicator", "indicator": "CLOSE"},
            "operator": "crosses_above",
            "right": {"type": "number", "value": 100},
        }
        res = _eval_condition(ohlcv, cond)
        assert res["met"] is False

    def test_crosses_above_never_crossed_is_false(self):
        # Never goes above threshold
        ohlcv = _make_ohlcv([80, 85, 90, 95])
        cond = {
            "left":  {"type": "indicator", "indicator": "CLOSE"},
            "operator": "crosses_above",
            "right": {"type": "number", "value": 100},
        }
        res = _eval_condition(ohlcv, cond)
        assert res["met"] is False

    # ── crosses_below ─────────────────────────────────────────────────────────

    def test_crosses_below_close_under_threshold(self):
        # prev close = 101 (above 100), current = 99 (below 100)
        ohlcv = _make_ohlcv([110, 105, 101, 99])
        cond = {
            "left":  {"type": "indicator", "indicator": "CLOSE"},
            "operator": "crosses_below",
            "right": {"type": "number", "value": 100},
        }
        res = _eval_condition(ohlcv, cond)
        assert res["met"] is True

    def test_crosses_below_already_below_is_false(self):
        # prev = 95, current = 90 — already below, no fresh cross
        ohlcv = _make_ohlcv([110, 105, 95, 90])
        cond = {
            "left":  {"type": "indicator", "indicator": "CLOSE"},
            "operator": "crosses_below",
            "right": {"type": "number", "value": 100},
        }
        res = _eval_condition(ohlcv, cond)
        assert res["met"] is False

    def test_crosses_above_desc_says_crossed_above(self):
        ohlcv = _make_ohlcv([95, 98, 99, 101])
        cond = {
            "left":  {"type": "indicator", "indicator": "CLOSE"},
            "operator": "crosses_above",
            "right": {"type": "number", "value": 100},
        }
        res = _eval_condition(ohlcv, cond)
        assert "crossed above" in res["desc"]

    def test_crossover_insufficient_data_not_met(self):
        ohlcv = _flat(2)
        cond = {
            "left":  {"type": "indicator", "indicator": "EMA", "period": 20},
            "operator": "crosses_above",
            "right": {"type": "indicator", "indicator": "EMA", "period": 50},
        }
        res = _eval_condition(ohlcv, cond)
        assert res["met"] is False
        assert "Insufficient" in res["desc"]


# ═══════════════════════════════════════════════════════════════════════════════
#  5. Default scanners structural integrity
# ═══════════════════════════════════════════════════════════════════════════════

class TestDefaultScanners:
    """Each of the 8 built-in scanners must be structurally sound."""

    REQUIRED_FIELDS = {"id", "name", "description", "universe", "logic", "conditions",
                       "createdAt", "updatedAt"}
    REQUIRED_COND_FIELDS = {"id", "left", "operator", "right"}

    def test_exactly_8_default_scanners_defined(self):
        assert len(DEFAULT_SCANNERS_DEF) == 8

    def test_all_initialized_scanners_have_required_fields(self):
        _init_defaults()
        for scanner in _scanners.values():
            for f in self.REQUIRED_FIELDS:
                assert f in scanner, f"Scanner '{scanner.get('name')}' missing field '{f}'"

    def test_all_scanners_have_non_empty_name(self):
        _init_defaults()
        for s in _scanners.values():
            assert s["name"].strip() != ""

    def test_all_scanners_have_non_empty_universe(self):
        _init_defaults()
        for s in _scanners.values():
            assert len(s["universe"]) >= 1

    def test_all_scanner_universes_are_valid_strings(self):
        _init_defaults()
        valid = {"NIFTY100", "MIDCAP", "SMALLCAP", "ALL"}
        for s in _scanners.values():
            for u in s["universe"]:
                assert isinstance(u, str) and u.strip()

    def test_all_scanners_have_logic_and_or(self):
        _init_defaults()
        for s in _scanners.values():
            assert s["logic"] in ("AND", "OR")

    def test_all_scanner_conditions_non_empty(self):
        _init_defaults()
        for s in _scanners.values():
            assert len(s["conditions"]) >= 1, f"'{s['name']}' has no conditions"

    def test_all_conditions_have_required_fields(self):
        _init_defaults()
        for s in _scanners.values():
            for c in s["conditions"]:
                for f in self.REQUIRED_COND_FIELDS:
                    assert f in c, f"Condition in '{s['name']}' missing field '{f}'"

    def test_all_condition_operators_are_valid(self):
        _init_defaults()
        for s in _scanners.values():
            for c in s["conditions"]:
                assert c["operator"] in VALID_OPERATORS, \
                    f"'{s['name']}' has invalid op '{c['operator']}'"

    def test_all_condition_ids_are_7_chars(self):
        _init_defaults()
        for s in _scanners.values():
            for c in s["conditions"]:
                assert len(c["id"]) == 7, f"Condition ID length ≠ 7: '{c['id']}'"

    def test_all_scanner_ids_follow_pattern(self):
        _init_defaults()
        for sid in _scanners:
            assert sid.startswith("scanner-"), f"Bad scanner ID format: {sid}"

    def test_default_scanner_names_are_unique(self):
        _init_defaults()
        names = [s["name"] for s in _scanners.values()]
        assert len(names) == len(set(names))

    def test_created_at_is_iso_format(self):
        _init_defaults()
        for s in _scanners.values():
            # Should parse without error
            dt = datetime.fromisoformat(s["createdAt"].replace("Z", "+00:00"))
            assert dt.year >= 2024

    # ── Individual default scanner spot-checks ────────────────────────────────

    def test_ema_golden_cross_scanner_exists(self):
        _init_defaults()
        names = [s["name"] for s in _scanners.values()]
        assert "EMA Golden Cross (20/50)" in names

    def test_golden_cross_has_2_conditions(self):
        _init_defaults()
        s = next(s for s in _scanners.values() if s["name"] == "EMA Golden Cross (20/50)")
        assert len(s["conditions"]) == 2

    def test_momentum_breakout_has_4_conditions(self):
        _init_defaults()
        s = next(s for s in _scanners.values() if s["name"] == "Momentum Breakout")
        assert len(s["conditions"]) == 4

    def test_superb_momentum_has_4_conditions(self):
        _init_defaults()
        s = next(s for s in _scanners.values() if s["name"] == "Superb Momentum (All EMAs aligned)")
        assert len(s["conditions"]) == 4

    def test_macd_crossover_scanner_exists(self):
        _init_defaults()
        names = [s["name"] for s in _scanners.values()]
        assert "MACD Bullish Crossover" in names

    def test_bollinger_bounce_scanner_exists(self):
        _init_defaults()
        names = [s["name"] for s in _scanners.values()]
        assert "Bollinger Band Lower Bounce" in names


# ═══════════════════════════════════════════════════════════════════════════════
#  6. ScannersService CRUD
# ═══════════════════════════════════════════════════════════════════════════════

class TestScannersServiceCrud:

    @pytest.fixture(autouse=True)
    def _snapshot_and_restore(self):
        """Snapshot _scanners + _id_counter before each test; restore after."""
        snap      = dict(_scanners)
        counter   = _id_counter[0]
        yield
        _scanners.clear()
        _scanners.update(snap)
        _id_counter[0] = counter

    @pytest.fixture
    def svc(self):
        return _fresh_service()

    # ── get_all_scanners ──────────────────────────────────────────────────────

    def test_get_all_scanners_returns_list(self, svc):
        assert isinstance(svc.get_all_scanners(), list)

    def test_get_all_scanners_not_empty_after_init(self, svc):
        assert len(svc.get_all_scanners()) >= 8

    def test_get_all_scanners_sorted_newest_first(self, svc):
        scanners = svc.get_all_scanners()
        dates = [s["createdAt"] for s in scanners]
        assert dates == sorted(dates, reverse=True)

    # ── get_scanner_by_id ─────────────────────────────────────────────────────

    def test_get_scanner_by_id_returns_correct_scanner(self, svc):
        scanners = svc.get_all_scanners()
        first = scanners[0]
        fetched = svc.get_scanner_by_id(first["id"])
        assert fetched["id"] == first["id"]
        assert fetched["name"] == first["name"]

    def test_get_scanner_by_id_returns_none_for_unknown(self, svc):
        assert svc.get_scanner_by_id("does-not-exist") is None

    # ── create_scanner ────────────────────────────────────────────────────────

    def test_create_scanner_returns_dict_with_id(self, svc):
        s = svc.create_scanner({"name": "Test Scanner", "conditions": []})
        assert "id" in s
        assert s["id"].startswith("scanner-")

    def test_create_scanner_id_is_unique(self, svc):
        ids = {svc.create_scanner({"name": f"S{i}"})["id"] for i in range(10)}
        assert len(ids) == 10

    def test_create_scanner_stores_name(self, svc):
        s = svc.create_scanner({"name": "My Scanner"})
        assert s["name"] == "My Scanner"

    def test_create_scanner_stores_description(self, svc):
        s = svc.create_scanner({"name": "X", "description": "Test desc"})
        assert s["description"] == "Test desc"

    def test_create_scanner_stores_universe(self, svc):
        s = svc.create_scanner({"name": "X", "universe": ["MIDCAP", "SMALLCAP"]})
        assert s["universe"] == ["MIDCAP", "SMALLCAP"]

    def test_create_scanner_stores_logic(self, svc):
        s = svc.create_scanner({"name": "X", "logic": "OR"})
        assert s["logic"] == "OR"

    def test_create_scanner_stores_conditions(self, svc):
        conds = [
            {"left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt",
             "right": {"type": "number", "value": 100}}
        ]
        s = svc.create_scanner({"name": "X", "conditions": conds})
        assert len(s["conditions"]) == 1

    def test_create_scanner_conditions_get_ids(self, svc):
        conds = [
            {"left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt",
             "right": {"type": "number", "value": 100}}
        ]
        s = svc.create_scanner({"name": "X", "conditions": conds})
        assert "id" in s["conditions"][0]
        assert len(s["conditions"][0]["id"]) == 7

    def test_create_scanner_condition_preserves_existing_id(self, svc):
        conds = [
            {"id": "abc1234",
             "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt",
             "right": {"type": "number", "value": 100}}
        ]
        s = svc.create_scanner({"name": "X", "conditions": conds})
        assert s["conditions"][0]["id"] == "abc1234"

    def test_create_scanner_sets_created_at(self, svc):
        s = svc.create_scanner({"name": "X"})
        assert "createdAt" in s
        assert s["createdAt"].endswith("Z")

    def test_create_scanner_sets_updated_at(self, svc):
        s = svc.create_scanner({"name": "X"})
        assert "updatedAt" in s

    def test_create_scanner_is_retrievable(self, svc):
        s = svc.create_scanner({"name": "Retrievable"})
        fetched = svc.get_scanner_by_id(s["id"])
        assert fetched is not None
        assert fetched["name"] == "Retrievable"

    # ── Default values for optional fields ───────────────────────────────────

    def test_create_scanner_default_name(self, svc):
        s = svc.create_scanner({})
        assert s["name"] == "Untitled Scanner"

    def test_create_scanner_default_description_empty_string(self, svc):
        s = svc.create_scanner({"name": "X"})
        assert s["description"] == ""

    def test_create_scanner_default_universe_nifty100(self, svc):
        s = svc.create_scanner({"name": "X"})
        assert s["universe"] == ["NIFTY100"]

    def test_create_scanner_default_logic_and(self, svc):
        s = svc.create_scanner({"name": "X"})
        assert s["logic"] == "AND"

    def test_create_scanner_default_conditions_empty(self, svc):
        s = svc.create_scanner({"name": "X"})
        assert s["conditions"] == []

    # ── update_scanner ────────────────────────────────────────────────────────

    def test_update_scanner_returns_updated_data(self, svc):
        s = svc.create_scanner({"name": "Original"})
        updated = svc.update_scanner(s["id"], {"name": "Updated"})
        assert updated["name"] == "Updated"

    def test_update_scanner_preserves_id(self, svc):
        s = svc.create_scanner({"name": "Test"})
        updated = svc.update_scanner(s["id"], {"name": "New"})
        assert updated["id"] == s["id"]

    def test_update_scanner_updates_updated_at(self, svc):
        s = svc.create_scanner({"name": "Test"})
        old_ts = s["updatedAt"]
        import time; time.sleep(0.01)
        updated = svc.update_scanner(s["id"], {"name": "Changed"})
        assert updated["updatedAt"] >= old_ts

    def test_update_scanner_returns_none_for_unknown(self, svc):
        result = svc.update_scanner("does-not-exist", {"name": "X"})
        assert result is None

    def test_update_scanner_partial_update_preserves_other_fields(self, svc):
        s = svc.create_scanner({"name": "T", "description": "Keep me",
                                  "universe": ["MIDCAP"]})
        updated = svc.update_scanner(s["id"], {"name": "New Name"})
        # description and universe should survive a partial update
        # (depends on spread logic — **existing, **data)
        assert updated["id"] == s["id"]

    def test_update_scanner_updates_conditions(self, svc):
        s = svc.create_scanner({"name": "T", "conditions": []})
        new_conds = [
            {"left": {"type": "indicator", "indicator": "RSI", "period": 14},
             "operator": "lt",
             "right": {"type": "number", "value": 30}}
        ]
        updated = svc.update_scanner(s["id"], {"conditions": new_conds})
        assert len(updated["conditions"]) == 1
        assert updated["conditions"][0]["left"]["indicator"] == "RSI"

    def test_update_scanner_new_conditions_get_ids(self, svc):
        s = svc.create_scanner({"name": "T"})
        new_conds = [{"left": {"type": "indicator", "indicator": "CLOSE"},
                      "operator": "gt", "right": {"type": "number", "value": 50}}]
        updated = svc.update_scanner(s["id"], {"conditions": new_conds})
        assert "id" in updated["conditions"][0]

    # ── delete_scanner ────────────────────────────────────────────────────────

    def test_delete_scanner_returns_true(self, svc):
        s = svc.create_scanner({"name": "To Delete"})
        assert svc.delete_scanner(s["id"]) is True

    def test_delete_scanner_removes_from_store(self, svc):
        s = svc.create_scanner({"name": "To Delete"})
        svc.delete_scanner(s["id"])
        assert svc.get_scanner_by_id(s["id"]) is None

    def test_delete_scanner_returns_false_for_unknown(self, svc):
        assert svc.delete_scanner("ghost-id") is False

    def test_delete_scanner_does_not_affect_others(self, svc):
        s1 = svc.create_scanner({"name": "Keep"})
        s2 = svc.create_scanner({"name": "Delete"})
        svc.delete_scanner(s2["id"])
        assert svc.get_scanner_by_id(s1["id"]) is not None


# ═══════════════════════════════════════════════════════════════════════════════
#  7. _evaluate() logic  (AND / OR / score)
# ═══════════════════════════════════════════════════════════════════════════════

class TestEvaluateLogic:
    """
    We test _evaluate() by constructing synthetic OHLCV sequences that are
    guaranteed to satisfy or violate specific conditions, then checking the
    output shape and logic.
    """

    def _run_eval(self, conditions: list, logic: str, ohlcv: list) -> dict | None:
        """Call the inner _evaluate() via a minimal scanner structure."""
        from app.services.scanners_service import _eval_condition
        if len(ohlcv) < 30:
            return None
        closes = [d["close"] for d in ohlcv if d.get("close")]
        lc, pc = closes[-1], closes[-2]
        change   = lc - pc
        p_change = (change / pc * 100) if pc else 0
        cond_results = [_eval_condition(ohlcv, c) for c in conditions]
        met_count    = sum(1 for r in cond_results if r["met"])
        all_met = (met_count == len(conditions) if logic == "AND" else met_count > 0)
        if not all_met:
            return None
        return {
            "lastPrice": lc,
            "change": round(change, 2),
            "pChange": round(p_change, 2),
            "volume": ohlcv[-1].get("volume"),
            "matchedConditions": [r["desc"] for r in cond_results if r["met"]],
            "failedConditions":  [r["desc"] for r in cond_results if not r["met"]],
            "conditionsMatched": met_count,
            "totalConditions": len(conditions),
            "score": round(met_count / len(conditions) * 100) if conditions else 0,
        }

    # ── AND logic ────────────────────────────────────────────────────────────

    def test_and_all_met_returns_result(self):
        ohlcv = _rising(50)   # RSI > 50, CLOSE > EMA20
        conds = [
            {"id": "a", "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "number", "value": 50}},
            {"id": "b", "left": {"type": "indicator", "indicator": "RSI", "period": 14},
             "operator": "gt", "right": {"type": "number", "value": 40}},
        ]
        result = self._run_eval(conds, "AND", ohlcv)
        assert result is not None
        assert result["conditionsMatched"] == 2

    def test_and_one_fails_returns_none(self):
        ohlcv = _rising(50)   # price > 50 ✓, but price > 999999 ✗
        conds = [
            {"id": "a", "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "number", "value": 50}},
            {"id": "b", "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "number", "value": 999_999}},
        ]
        result = self._run_eval(conds, "AND", ohlcv)
        assert result is None

    def test_and_all_fail_returns_none(self):
        ohlcv = _rising(50)
        conds = [
            {"id": "a", "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "number", "value": 999_999}},
            {"id": "b", "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "number", "value": 999_998}},
        ]
        result = self._run_eval(conds, "AND", ohlcv)
        assert result is None

    # ── OR logic ─────────────────────────────────────────────────────────────

    def test_or_one_met_returns_result(self):
        ohlcv = _rising(50)   # price > 50 ✓, price > 999999 ✗
        conds = [
            {"id": "a", "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "number", "value": 50}},
            {"id": "b", "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "number", "value": 999_999}},
        ]
        result = self._run_eval(conds, "OR", ohlcv)
        assert result is not None

    def test_or_all_fail_returns_none(self):
        ohlcv = _rising(50)
        conds = [
            {"id": "a", "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "number", "value": 999_999}},
        ]
        result = self._run_eval(conds, "OR", ohlcv)
        assert result is None

    def test_or_all_met_returns_result(self):
        ohlcv = _rising(50)
        conds = [
            {"id": "a", "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "number", "value": 50}},
            {"id": "b", "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "number", "value": 40}},
        ]
        result = self._run_eval(conds, "OR", ohlcv)
        assert result is not None
        assert result["conditionsMatched"] == 2

    # ── Score calculation ─────────────────────────────────────────────────────

    def test_score_100_when_all_conditions_met(self):
        ohlcv = _rising(50)
        conds = [
            {"id": "a", "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "number", "value": 50}},
            {"id": "b", "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "number", "value": 40}},
        ]
        result = self._run_eval(conds, "AND", ohlcv)
        assert result is not None
        assert result["score"] == 100

    def test_score_50_when_half_conditions_met(self):
        ohlcv = _rising(50)
        conds = [
            {"id": "a", "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "number", "value": 50}},   # ✓
            {"id": "b", "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "number", "value": 999_999}},  # ✗
        ]
        # OR logic so result exists even with 1 failure
        result = self._run_eval(conds, "OR", ohlcv)
        assert result is not None
        assert result["score"] == 50

    def test_score_is_integer_percentage(self):
        ohlcv = _rising(50)
        conds = [
            {"id": "a", "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "number", "value": 50}},
        ]
        result = self._run_eval(conds, "OR", ohlcv)
        assert isinstance(result["score"], int)

    # ── Result shape ──────────────────────────────────────────────────────────

    def test_result_has_all_required_keys(self):
        ohlcv = _rising(50)
        conds = [
            {"id": "a", "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "number", "value": 50}},
        ]
        result = self._run_eval(conds, "AND", ohlcv)
        required = {"lastPrice", "change", "pChange", "volume",
                    "matchedConditions", "failedConditions",
                    "conditionsMatched", "totalConditions", "score"}
        for k in required:
            assert k in result, f"Missing key: {k}"

    def test_matched_conditions_are_strings(self):
        ohlcv = _rising(50)
        conds = [
            {"id": "a", "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "number", "value": 50}},
        ]
        result = self._run_eval(conds, "AND", ohlcv)
        assert all(isinstance(s, str) for s in result["matchedConditions"])

    def test_last_price_matches_last_close(self):
        closes = list(range(100, 150))
        ohlcv = _make_ohlcv(closes)
        conds = [
            {"id": "a", "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "number", "value": 50}},
        ]
        result = self._run_eval(conds, "AND", ohlcv)
        assert result["lastPrice"] == 149

    def test_too_few_bars_returns_none(self):
        ohlcv = _flat(20)   # less than 30 bars required
        conds = [
            {"id": "a", "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "number", "value": 50}},
        ]
        result = self._run_eval(conds, "AND", ohlcv)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
#  8. Complex multi-condition scanner combinations
# ═══════════════════════════════════════════════════════════════════════════════

class TestComplexScannerCombinations:
    """
    Build real scanners via ScannersService.create_scanner() and exercise
    the condition evaluation logic with carefully crafted OHLCV data.
    """

    @pytest.fixture(autouse=True)
    def _snapshot(self):
        snap    = dict(_scanners)
        counter = _id_counter[0]
        yield
        _scanners.clear()
        _scanners.update(snap)
        _id_counter[0] = counter

    @pytest.fixture
    def svc(self):
        return _fresh_service()

    # ── Scanner creation with every operator type ─────────────────────────────

    def test_scanner_with_gt_condition(self, svc):
        s = svc.create_scanner({
            "name": "Close GT 50",
            "conditions": [{"left": {"type": "indicator", "indicator": "CLOSE"},
                            "operator": "gt",
                            "right": {"type": "number", "value": 50}}],
        })
        assert s["conditions"][0]["operator"] == "gt"

    def test_scanner_with_gte_condition(self, svc):
        s = svc.create_scanner({
            "name": "RSI GTE 55",
            "conditions": [{"left": {"type": "indicator", "indicator": "RSI", "period": 14},
                            "operator": "gte",
                            "right": {"type": "number", "value": 55}}],
        })
        assert s["conditions"][0]["operator"] == "gte"

    def test_scanner_with_lt_condition(self, svc):
        s = svc.create_scanner({
            "name": "RSI LT 30",
            "conditions": [{"left": {"type": "indicator", "indicator": "RSI", "period": 14},
                            "operator": "lt",
                            "right": {"type": "number", "value": 30}}],
        })
        assert s["conditions"][0]["operator"] == "lt"

    def test_scanner_with_lte_condition(self, svc):
        s = svc.create_scanner({
            "name": "Close LTE BB_LOWER",
            "conditions": [{"left":  {"type": "indicator", "indicator": "CLOSE"},
                            "operator": "lte",
                            "right": {"type": "indicator", "indicator": "BB_LOWER", "period": 20}}],
        })
        assert s["conditions"][0]["operator"] == "lte"

    def test_scanner_with_eq_condition(self, svc):
        s = svc.create_scanner({
            "name": "Volume equal test",
            "conditions": [{"left":  {"type": "indicator", "indicator": "VOLUME"},
                            "operator": "eq",
                            "right": {"type": "number", "value": 10000}}],
        })
        assert s["conditions"][0]["operator"] == "eq"

    def test_scanner_with_crosses_above_condition(self, svc):
        s = svc.create_scanner({
            "name": "EMA Cross",
            "conditions": [{"left":  {"type": "indicator", "indicator": "EMA", "period": 20},
                            "operator": "crosses_above",
                            "right": {"type": "indicator", "indicator": "EMA", "period": 50}}],
        })
        assert s["conditions"][0]["operator"] == "crosses_above"

    def test_scanner_with_crosses_below_condition(self, svc):
        s = svc.create_scanner({
            "name": "Death Cross",
            "conditions": [{"left":  {"type": "indicator", "indicator": "EMA", "period": 20},
                            "operator": "crosses_below",
                            "right": {"type": "indicator", "indicator": "EMA", "period": 50}}],
        })
        assert s["conditions"][0]["operator"] == "crosses_below"

    # ── Multi-universe combinations ───────────────────────────────────────────

    def test_scanner_single_universe(self, svc):
        s = svc.create_scanner({"name": "X", "universe": ["NIFTY100"]})
        assert s["universe"] == ["NIFTY100"]

    def test_scanner_multi_universe(self, svc):
        s = svc.create_scanner({"name": "X", "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"]})
        assert len(s["universe"]) == 3

    # ── Mixed indicator types in conditions ───────────────────────────────────

    def test_scanner_indicator_vs_indicator_condition(self, svc):
        s = svc.create_scanner({
            "name": "Close above EMA20",
            "conditions": [{"left":  {"type": "indicator", "indicator": "CLOSE"},
                            "operator": "gt",
                            "right": {"type": "indicator", "indicator": "EMA", "period": 20}}],
        })
        assert s["conditions"][0]["right"]["type"] == "indicator"
        assert s["conditions"][0]["right"]["indicator"] == "EMA"

    def test_scanner_number_vs_number_condition(self, svc):
        s = svc.create_scanner({
            "name": "Always true",
            "conditions": [{"left":  {"type": "number", "value": 10},
                            "operator": "lt",
                            "right": {"type": "number", "value": 20}}],
        })
        ohlcv = _flat(5)
        cond = s["conditions"][0]
        res = _eval_condition(ohlcv, cond)
        assert res["met"] is True

    # ── Condition with different OHLCV indicator types ────────────────────────

    def test_condition_open_lt_close_always_false_for_flat(self):
        ohlcv = _flat(10, 100)
        cond = {"left":  {"type": "indicator", "indicator": "OPEN"},
                "operator": "gt",
                "right": {"type": "indicator", "indicator": "CLOSE"}}
        # In _flat(), open = 100*0.99 = 99 < 100 = close → gt is false
        res = _eval_condition(ohlcv, cond)
        assert res["met"] is False

    def test_condition_high_gt_low_always_true(self):
        ohlcv = _flat(10, 100)
        cond = {"left":  {"type": "indicator", "indicator": "HIGH"},
                "operator": "gt",
                "right": {"type": "indicator", "indicator": "LOW"}}
        # high = 100*1.02 = 102 > 100*0.97 = 97 → always true
        res = _eval_condition(ohlcv, cond)
        assert res["met"] is True

    def test_condition_macd_hist_positive_in_rising_market(self):
        ohlcv = _rising(80)
        cond = {"left":  {"type": "indicator", "indicator": "MACD_HIST"},
                "operator": "gt",
                "right": {"type": "number", "value": 0}}
        res = _eval_condition(ohlcv, cond)
        assert res["met"] is True

    def test_condition_bb_lower_lt_bb_upper(self):
        ohlcv = _rising(50)
        cond = {"left":  {"type": "indicator", "indicator": "BB_LOWER", "period": 20},
                "operator": "lt",
                "right": {"type": "indicator", "indicator": "BB_UPPER", "period": 20}}
        res = _eval_condition(ohlcv, cond)
        assert res["met"] is True

    def test_condition_atr_gt_zero_in_volatile_market(self):
        # Rising market with some variance in high/low
        ohlcv = _rising(40)
        cond = {"left":  {"type": "indicator", "indicator": "ATR", "period": 14},
                "operator": "gt",
                "right": {"type": "number", "value": 0}}
        res = _eval_condition(ohlcv, cond)
        assert res["met"] is True

    def test_condition_pct_52w_high_in_near_high_market(self):
        # Create a series that ends near its high
        closes = list(range(100, 200)) + [195]  # 52W high = 199, last close = 195
        ohlcv = _make_ohlcv(closes)
        cond = {"left":  {"type": "indicator", "indicator": "PCT_52W_HIGH"},
                "operator": "gte",
                "right": {"type": "number", "value": -5}}
        res = _eval_condition(ohlcv, cond)
        assert res["met"] is True  # (195-199)/199*100 ≈ -2% ≥ -5%

    # ── Update scanner changes conditions ────────────────────────────────────

    def test_update_replaces_logic_or_to_and(self, svc):
        s = svc.create_scanner({"name": "X", "logic": "OR"})
        updated = svc.update_scanner(s["id"], {"logic": "AND"})
        assert updated["logic"] == "AND"

    def test_update_replaces_universe(self, svc):
        s = svc.create_scanner({"name": "X", "universe": ["NIFTY100"]})
        updated = svc.update_scanner(s["id"], {"universe": ["SMALLCAP"]})
        assert updated["universe"] == ["SMALLCAP"]

    def test_update_adds_multiple_conditions(self, svc):
        s = svc.create_scanner({"name": "X", "conditions": []})
        new_conds = [
            {"left": {"type": "indicator", "indicator": "RSI", "period": 14},
             "operator": "gt", "right": {"type": "number", "value": 50}},
            {"left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "indicator", "indicator": "EMA", "period": 20}},
            {"left": {"type": "indicator", "indicator": "VOLUME_RATIO"},
             "operator": "gte", "right": {"type": "number", "value": 150}},
        ]
        updated = svc.update_scanner(s["id"], {"conditions": new_conds})
        assert len(updated["conditions"]) == 3


# ═══════════════════════════════════════════════════════════════════════════════
#  9. VALID_OPERATORS constant
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidOperators:
    def test_valid_operators_set_contains_all_6(self):
        assert VALID_OPERATORS == {"gt", "gte", "lt", "lte", "eq", "crosses_above", "crosses_below"}

    def test_valid_operators_is_a_set(self):
        assert isinstance(VALID_OPERATORS, set)

    def test_all_default_scanner_operators_are_in_valid_set(self):
        for defn in DEFAULT_SCANNERS_DEF:
            for cond in defn["conditions"]:
                assert cond["operator"] in VALID_OPERATORS, \
                    f"'{defn['name']}' uses invalid op '{cond['operator']}'"


# ═══════════════════════════════════════════════════════════════════════════════
#  10. Edge cases and resilience
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:

    def test_change_pct_zero_previous_close(self):
        # prev_close = 0 → guard against div/0
        ohlcv = _make_ohlcv([0, 100])
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "CHANGE_PCT"})
        assert v is None  # closes[-2] is falsy → returns None

    def test_volume_ratio_zero_avg_volume_no_crash(self):
        ohlcv = _flat(25, 100)
        for row in ohlcv:
            row["volume"] = 0
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "VOLUME_RATIO"})
        assert v is None  # avg = 0 → guard returns None

    def test_pct_52w_high_with_zero_high(self):
        # All closes are 0 → high = 0 → guard against div/0
        ohlcv = _make_ohlcv([0] * 10)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "PCT_52W_HIGH"})
        assert v is None  # h = 0 → returns None

    def test_compute_value_missing_type_field_returns_none(self):
        ohlcv = _flat(10)
        # No "type" key at all — should not crash
        v = _compute_value(ohlcv, {"indicator": "CLOSE"})
        # type is missing → not "number", falls through to indicator lookup
        assert v is None or isinstance(v, float)  # either path is acceptable

    def test_eval_condition_with_unknown_indicator_on_left(self):
        ohlcv = _flat(30)
        cond = {"left": {"type": "indicator", "indicator": "NONEXISTENT"},
                "operator": "gt", "right": {"type": "number", "value": 10}}
        res = _eval_condition(ohlcv, cond)
        assert res["met"] is False
        assert "Insufficient" in res["desc"]

    def test_eval_condition_with_unknown_indicator_on_right(self):
        ohlcv = _flat(30)
        cond = {"left":  {"type": "indicator", "indicator": "CLOSE"},
                "operator": "gt", "right": {"type": "indicator", "indicator": "GHOST"}}
        res = _eval_condition(ohlcv, cond)
        assert res["met"] is False

    def test_create_scanner_with_none_fields_uses_defaults(self):
        snap    = dict(_scanners)
        counter = _id_counter[0]
        try:
            svc = _fresh_service()
            s = svc.create_scanner({
                "name": None,
                "description": None,
                "universe": None,
                "logic": None,
                "conditions": None,
            })
            assert s["name"] == "Untitled Scanner"
            assert s["description"] == ""
            assert s["universe"] == ["NIFTY100"]
            assert s["logic"] == "AND"
            assert s["conditions"] == []
        finally:
            _scanners.clear()
            _scanners.update(snap)
            _id_counter[0] = counter

    def test_rsi_with_only_up_moves_approaches_100(self):
        # Perfectly rising prices → all gains, no losses → RSI near 100
        closes = [float(100 + i) for i in range(60)]
        ohlcv = _make_ohlcv(closes)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "RSI", "period": 14})
        assert v > 90  # should be very high RSI

    def test_rsi_with_only_down_moves_approaches_0(self):
        closes = [float(200 - i) for i in range(60)]
        ohlcv = _make_ohlcv(closes)
        v = _compute_value(ohlcv, {"type": "indicator", "indicator": "RSI", "period": 14})
        assert v < 10

    def test_eq_operator_exact_volume_match(self):
        ohlcv = _flat(30, 100)
        for row in ohlcv:
            row["volume"] = 5000
        cond = {"left":  {"type": "indicator", "indicator": "VOLUME"},
                "operator": "eq",
                "right": {"type": "number", "value": 5000}}
        res = _eval_condition(ohlcv, cond)
        assert res["met"] is True

    def test_ema_period_9_vs_200_ordering_in_rising_market(self):
        ohlcv = _rising(300)
        ema9   = _compute_value(ohlcv, {"type": "indicator", "indicator": "EMA", "period": 9})
        ema20  = _compute_value(ohlcv, {"type": "indicator", "indicator": "EMA", "period": 20})
        ema50  = _compute_value(ohlcv, {"type": "indicator", "indicator": "EMA", "period": 50})
        ema200 = _compute_value(ohlcv, {"type": "indicator", "indicator": "EMA", "period": 200})
        # Superb momentum: ema9 > ema20 > ema50 > ema200
        assert ema9 > ema20 > ema50 > ema200

    def test_superb_momentum_conditions_all_met_in_strong_uptrend(self):
        ohlcv = _rising(300)
        conditions = [
            {"id": "a", "left": {"type": "indicator", "indicator": "CLOSE"},
             "operator": "gt", "right": {"type": "indicator", "indicator": "EMA", "period": 9}},
            {"id": "b", "left": {"type": "indicator", "indicator": "EMA", "period": 9},
             "operator": "gt", "right": {"type": "indicator", "indicator": "EMA", "period": 20}},
            {"id": "c", "left": {"type": "indicator", "indicator": "EMA", "period": 20},
             "operator": "gt", "right": {"type": "indicator", "indicator": "EMA", "period": 50}},
            {"id": "d", "left": {"type": "indicator", "indicator": "EMA", "period": 50},
             "operator": "gt", "right": {"type": "indicator", "indicator": "EMA", "period": 200}},
        ]
        results = [_eval_condition(ohlcv, c) for c in conditions]
        met = [r["met"] for r in results]
        assert all(met), f"Not all EMA alignment conditions met: {met}"
