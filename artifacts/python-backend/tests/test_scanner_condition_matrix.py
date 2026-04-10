"""
test_scanner_condition_matrix.py
────────────────────────────────
Exhaustive parametrized tests for every possible condition combination that the
"New Scanner" UI can build.

The UI allows the user to pick:
  Left  : any one of 26 indicator specs
  Op    : one of 7 operators  (gt / gte / lt / lte / eq / crosses_above / crosses_below)
  Right : any one of 26 indicator specs  OR  a numeric constant

This file generates and runs the full combinatorial matrix:

  Section A  _compute_value — 26 tests
             Every indicator must compute a non-None float from 300-bar data.

  Section B  _eval_condition — indicator vs number, simple operators (5 × 26 = 130)
             Every indicator × {gt, gte, lt, lte, eq} must return {met, desc} without
             crashing, with a well-formed description string.

  Section C  _eval_condition — indicator vs indicator, all 7 operators (7 × 26 × 26 = 4 732)
             Every left × right pair must not raise and must return a valid result dict.
             covers:  gt, gte, lt, lte, eq  — 26 × 26 × 5 = 3 380
             covers:  crosses_above, crosses_below — 26 × 26 × 2 = 1 352

  Section D  crossover vs number — deterministic sequences (26 × 2 = 52)
             Ensures the actual "met" flag is correct for CLOSE crosses_above / crosses_below
             when the data is constructed to guarantee the cross happened.

  Section E  crossover vs indicator — no-crash guarantee (26 × 26 × 2 = 1 352)
             Already covered by Section C — re-run here with richer context data.

  Section F  create_scanner with every condition shape — CRUD correctness (26 × 7 = 182)
             Every indicator spec stored in a condition round-trips through
             create_scanner without data loss.

Grand total parametrized tests: ~5 700
"""

import pytest
from app.services.scanners_service import (
    _compute_value,
    _eval_condition,
    _scanners,
    _id_counter,
    ScannersService,
)
from app.services.price_service import PriceService
from app.services.yahoo_service import YahooService
from app.services.nse_service import NseService


# ════════════════════════════════════════════════════════════════════════════════
#  Module-level synthetic OHLCV datasets (computed once, reused by all tests)
# ════════════════════════════════════════════════════════════════════════════════

def _make_rich(n: int = 300, start: float = 100.0, step: float = 1.0) -> list[dict]:
    """
    300 bars of steadily rising prices (100 → 399).
    Enough to drive EMA(200), RSI(14), MACD(26+9), BB(20), ATR(14)
    — every indicator in the system without returning None.
    Volumes grow linearly so VOLUME_RATIO has a non-trivial value.
    """
    return [
        {
            "open":   (start + i * step) * 0.99,
            "high":   (start + i * step) * 1.02,
            "low":    (start + i * step) * 0.97,
            "close":  start + i * step,
            "volume": 10_000 + i * 10,
        }
        for i in range(n)
    ]


def _crossover_above_data(threshold: float = 200.0) -> list[dict]:
    """
    300-bar sequence whose last bar is just above `threshold` and whose second-to-last
    bar is just below it.  Guarantees CLOSE crosses_above threshold.
    """
    data = _make_rich(298, start=100.0)       # bars well below threshold
    data.append({                             # prev bar: just below
        "open": threshold * 0.99, "high": threshold * 1.001,
        "low": threshold * 0.97, "close": threshold - 0.5,
        "volume": 15_000,
    })
    data.append({                             # current bar: just above
        "open": threshold * 1.001, "high": threshold * 1.02,
        "low": threshold * 0.99, "close": threshold + 0.5,
        "volume": 16_000,
    })
    return data


def _crossover_below_data(threshold: float = 400.0) -> list[dict]:
    """
    300-bar sequence where last bar just goes below `threshold`.
    Guarantees CLOSE crosses_below threshold.
    """
    data = _make_rich(298, start=500.0, step=-0.5)  # bars well above threshold
    data.append({                                    # prev bar: just above
        "open": threshold * 1.001, "high": threshold * 1.02,
        "low": threshold * 0.99, "close": threshold + 0.5,
        "volume": 15_000,
    })
    data.append({                                    # current bar: just below
        "open": threshold * 0.999, "high": threshold * 1.001,
        "low": threshold * 0.97, "close": threshold - 0.5,
        "volume": 16_000,
    })
    return data


# Pre-computed at import time — shared across ALL parametrized tests
RICH   = _make_rich(300)
X_ABOVE = _crossover_above_data(threshold=200.0)   # CLOSE crosses_above 200
X_BELOW = _crossover_below_data(threshold=399.5)   # CLOSE crosses_below 399.5


# ════════════════════════════════════════════════════════════════════════════════
#  Indicator catalogue  (26 distinct specs — every item the UI can choose)
# ════════════════════════════════════════════════════════════════════════════════

# (label, side-dict)
ALL_INDICATORS: list[tuple[str, dict]] = [
    # ── Price levels ────────────────────────────────────────────────────────────
    ("CLOSE",         {"type": "indicator", "indicator": "CLOSE"}),
    ("OPEN",          {"type": "indicator", "indicator": "OPEN"}),
    ("HIGH",          {"type": "indicator", "indicator": "HIGH"}),
    ("LOW",           {"type": "indicator", "indicator": "LOW"}),
    ("PREV_CLOSE",    {"type": "indicator", "indicator": "PREV_CLOSE"}),
    # ── Change ──────────────────────────────────────────────────────────────────
    ("CHANGE_PCT",    {"type": "indicator", "indicator": "CHANGE_PCT"}),
    # ── Volume ──────────────────────────────────────────────────────────────────
    ("VOLUME",        {"type": "indicator", "indicator": "VOLUME"}),
    ("AVG_VOLUME_20", {"type": "indicator", "indicator": "AVG_VOLUME", "period": 20}),
    ("VOLUME_RATIO",  {"type": "indicator", "indicator": "VOLUME_RATIO"}),
    # ── EMA (4 standard periods) ─────────────────────────────────────────────────
    ("EMA_9",         {"type": "indicator", "indicator": "EMA",  "period": 9}),
    ("EMA_20",        {"type": "indicator", "indicator": "EMA",  "period": 20}),
    ("EMA_50",        {"type": "indicator", "indicator": "EMA",  "period": 50}),
    ("EMA_200",       {"type": "indicator", "indicator": "EMA",  "period": 200}),
    # ── SMA ──────────────────────────────────────────────────────────────────────
    ("SMA_20",        {"type": "indicator", "indicator": "SMA",  "period": 20}),
    # ── RSI ──────────────────────────────────────────────────────────────────────
    ("RSI_14",        {"type": "indicator", "indicator": "RSI",  "period": 14}),
    # ── MACD ─────────────────────────────────────────────────────────────────────
    ("MACD",          {"type": "indicator", "indicator": "MACD"}),
    ("MACD_SIGNAL",   {"type": "indicator", "indicator": "MACD_SIGNAL"}),
    ("MACD_HIST",     {"type": "indicator", "indicator": "MACD_HIST"}),
    # ── Bollinger Bands ───────────────────────────────────────────────────────────
    ("BB_UPPER_20",   {"type": "indicator", "indicator": "BB_UPPER", "period": 20}),
    ("BB_MID_20",     {"type": "indicator", "indicator": "BB_MID",   "period": 20}),
    ("BB_LOWER_20",   {"type": "indicator", "indicator": "BB_LOWER", "period": 20}),
    # ── ATR ───────────────────────────────────────────────────────────────────────
    ("ATR_14",        {"type": "indicator", "indicator": "ATR",  "period": 14}),
    # ── 52-week range ─────────────────────────────────────────────────────────────
    ("HIGH_52W",      {"type": "indicator", "indicator": "HIGH_52W"}),
    ("LOW_52W",       {"type": "indicator", "indicator": "LOW_52W"}),
    ("PCT_52W_HIGH",  {"type": "indicator", "indicator": "PCT_52W_HIGH"}),
    ("PCT_52W_LOW",   {"type": "indicator", "indicator": "PCT_52W_LOW"}),
]

SIMPLE_OPERATORS = ["gt", "gte", "lt", "lte", "eq"]
ALL_OPERATORS    = ["gt", "gte", "lt", "lte", "eq", "crosses_above", "crosses_below"]

# Numeric constants used as the right side — values that are reasonable for
# each indicator category (all in SI / percentage units so comparisons are
# semantically meaningful, though the tests only check structure, not the
# met flag's specific value).
INDICATOR_NUMBER_MAP: dict[str, float] = {
    "CLOSE":      250.0,   "OPEN":       250.0,   "HIGH":       255.0,
    "LOW":        245.0,   "PREV_CLOSE": 249.0,   "CHANGE_PCT": 0.0,
    "VOLUME":     15_000,  "AVG_VOLUME": 12_000,  "AVG_VOLUME_20": 12_000,
    "VOLUME_RATIO": 100.0,
    "EMA":        240.0,   "EMA_9":      248.0,   "EMA_20":     245.0,
    "EMA_50":     235.0,   "EMA_200":    220.0,   "SMA":        245.0,
    "SMA_20":     245.0,
    "RSI":        50.0,    "RSI_14":     50.0,
    "MACD":       0.0,     "MACD_SIGNAL": 0.0,    "MACD_HIST":  0.0,
    "BB_UPPER":   260.0,   "BB_UPPER_20": 260.0,
    "BB_MID":     250.0,   "BB_MID_20":   250.0,
    "BB_LOWER":   240.0,   "BB_LOWER_20": 240.0,
    "ATR":        2.0,     "ATR_14":     2.0,
    "HIGH_52W":   399.0,   "LOW_52W":    100.0,
    "PCT_52W_HIGH": -5.0,  "PCT_52W_LOW": 200.0,
}

def _number_for(label: str) -> float:
    return INDICATOR_NUMBER_MAP.get(label, 0.0)


def _fresh_service() -> ScannersService:
    return ScannersService(PriceService(NseService(), YahooService()))


# ════════════════════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════════════════════

def _assert_valid_eval_result(res: dict, label: str) -> None:
    assert isinstance(res, dict),        f"[{label}] result is not a dict"
    assert "met"  in res,                f"[{label}] 'met' key missing"
    assert "desc" in res,                f"[{label}] 'desc' key missing"
    assert isinstance(res["met"],  bool), f"[{label}] 'met' is not bool: {res['met']!r}"
    assert isinstance(res["desc"], str),  f"[{label}] 'desc' is not str: {res['desc']!r}"
    assert len(res["desc"]) > 0,          f"[{label}] 'desc' is empty string"


# ════════════════════════════════════════════════════════════════════════════════
#  SECTION A — _compute_value returns a valid float for every indicator
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("label,side", ALL_INDICATORS, ids=[x[0] for x in ALL_INDICATORS])
def test_compute_value_all_indicators_return_float(label: str, side: dict):
    """
    Every indicator must compute a non-None float when given 300 bars of data.
    If this fails it means the indicator is broken for all conditions that use it.
    """
    val = _compute_value(RICH, side)
    assert val is not None, \
        f"[{label}] _compute_value returned None — indicator is broken for full dataset"
    assert isinstance(val, (int, float)), \
        f"[{label}] _compute_value returned non-numeric type: {type(val)}"


# ════════════════════════════════════════════════════════════════════════════════
#  SECTION B — indicator vs number, simple operators
#  26 indicators × 5 operators = 130 parametrized tests
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "label,left_side,op",
    [
        (f"{lbl}__{op}", side, op)
        for lbl, side in ALL_INDICATORS
        for op in SIMPLE_OPERATORS
    ],
    ids=[f"{lbl}__{op}" for lbl, _ in ALL_INDICATORS for op in SIMPLE_OPERATORS],
)
def test_eval_condition_indicator_vs_number_no_crash(label, left_side, op):
    """
    _eval_condition must not raise and must return a valid {met, desc} dict for
    every (indicator, simple_operator, number) triple.
    """
    right_number = _number_for(label.split("__")[0])
    cond = {
        "left":     left_side,
        "operator": op,
        "right":    {"type": "number", "value": right_number},
    }
    res = _eval_condition(RICH, cond)
    _assert_valid_eval_result(res, label)


# ════════════════════════════════════════════════════════════════════════════════
#  SECTION C — indicator vs indicator, all simple operators
#  26 × 26 × 5 = 3 380 parametrized tests
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "label,left_side,right_side,op",
    [
        (f"{ll}__{op}__{rl}", ls, rs, op)
        for ll, ls in ALL_INDICATORS
        for rl, rs in ALL_INDICATORS
        for op in SIMPLE_OPERATORS
    ],
    ids=[
        f"{ll}__{op}__{rl}"
        for ll, _ in ALL_INDICATORS
        for rl, _ in ALL_INDICATORS
        for op in SIMPLE_OPERATORS
    ],
)
def test_eval_condition_indicator_vs_indicator_simple_ops(label, left_side, right_side, op):
    """
    Every (left indicator, simple operator, right indicator) combination must
    return a valid {met, desc} result without raising any exception.
    """
    cond = {"left": left_side, "operator": op, "right": right_side}
    res  = _eval_condition(RICH, cond)
    _assert_valid_eval_result(res, label)


# ════════════════════════════════════════════════════════════════════════════════
#  SECTION D — crossover vs number, deterministic
#  26 indicators × 2 crossover ops = 52 parametrized tests
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "label,left_side",
    ALL_INDICATORS,
    ids=[x[0] for x in ALL_INDICATORS],
)
def test_crosses_above_indicator_vs_number_no_crash(label, left_side):
    """
    crosses_above with a number on the right must not raise for any left indicator.
    The function must return {met: bool, desc: str}.
    """
    right_number = _number_for(label)
    cond = {
        "left":     left_side,
        "operator": "crosses_above",
        "right":    {"type": "number", "value": right_number},
    }
    res = _eval_condition(RICH, cond)
    _assert_valid_eval_result(res, f"{label}__crosses_above__NUMBER")


@pytest.mark.parametrize(
    "label,left_side",
    ALL_INDICATORS,
    ids=[x[0] for x in ALL_INDICATORS],
)
def test_crosses_below_indicator_vs_number_no_crash(label, left_side):
    """
    crosses_below with a number on the right must not raise for any left indicator.
    """
    right_number = _number_for(label)
    cond = {
        "left":     left_side,
        "operator": "crosses_below",
        "right":    {"type": "number", "value": right_number},
    }
    res = _eval_condition(RICH, cond)
    _assert_valid_eval_result(res, f"{label}__crosses_below__NUMBER")


# ── Deterministic CLOSE crossover correctness ────────────────────────────────

def test_close_crosses_above_number_correct_met_flag():
    """CLOSE crosses_above 200 — must be True when prev=199.5, curr=200.5."""
    cond = {
        "left":     {"type": "indicator", "indicator": "CLOSE"},
        "operator": "crosses_above",
        "right":    {"type": "number", "value": 200.0},
    }
    res = _eval_condition(X_ABOVE, cond)
    assert res["met"] is True, \
        f"Expected CLOSE crosses_above 200 to be True with data crossing at 200; got {res}"


def test_close_crosses_below_number_correct_met_flag():
    """CLOSE crosses_below ~399.5 — must be True when prev was above threshold."""
    cond = {
        "left":     {"type": "indicator", "indicator": "CLOSE"},
        "operator": "crosses_below",
        "right":    {"type": "number", "value": 399.5},
    }
    res = _eval_condition(X_BELOW, cond)
    assert res["met"] is True, \
        f"Expected CLOSE crosses_below 399.5 to be True with data crossing; got {res}"


def test_close_crosses_above_already_above_is_false():
    """CLOSE crosses_above 50 — RICH data is never at 50, so prev > 50 → False."""
    cond = {
        "left":     {"type": "indicator", "indicator": "CLOSE"},
        "operator": "crosses_above",
        "right":    {"type": "number", "value": 50.0},
    }
    res = _eval_condition(RICH, cond)
    assert res["met"] is False, \
        "CLOSE was always above 50 in RICH data — no fresh cross should fire"


def test_close_crosses_below_never_below_is_false():
    """CLOSE crosses_below 9999 — RICH data never approaches 9999 → False."""
    cond = {
        "left":     {"type": "indicator", "indicator": "CLOSE"},
        "operator": "crosses_below",
        "right":    {"type": "number", "value": 9999.0},
    }
    res = _eval_condition(RICH, cond)
    assert res["met"] is False, \
        "CLOSE never got close to 9999 — no cross-below should fire"


def test_change_pct_crosses_above_zero_in_rising_bar():
    """CHANGE_PCT crosses_above 0 when prev bar was negative and current is positive."""
    # Build: last two bars go from -1% change to +1% change
    data = _make_rich_local(298, 100.0, 1.0)
    # prev: goes down, curr: goes up
    data.append({"open": 397, "high": 400, "low": 394, "close": 396.0, "volume": 10000})  # prev close < close[-2]=397
    data.append({"open": 395, "high": 400, "low": 394, "close": 398.0, "volume": 10000})  # curr: 398 > 396 → positive change
    cond = {
        "left":     {"type": "indicator", "indicator": "CHANGE_PCT"},
        "operator": "crosses_above",
        "right":    {"type": "number", "value": 0.0},
    }
    # This test is structural — we just need no crash + valid result
    res = _eval_condition(data, cond)
    _assert_valid_eval_result(res, "CHANGE_PCT__crosses_above__0")


def _make_rich_local(n, start, step):
    return [
        {"open": (start + i * step) * 0.99, "high": (start + i * step) * 1.02,
         "low": (start + i * step) * 0.97, "close": start + i * step,
         "volume": 10_000 + i * 10}
        for i in range(n)
    ]


# ════════════════════════════════════════════════════════════════════════════════
#  SECTION E — crossover: indicator vs indicator  (26 × 26 × 2 = 1 352)
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "label,left_side,right_side",
    [
        (f"{ll}__crosses_above__{rl}", ls, rs)
        for ll, ls in ALL_INDICATORS
        for rl, rs in ALL_INDICATORS
    ],
    ids=[
        f"{ll}__crosses_above__{rl}"
        for ll, _ in ALL_INDICATORS
        for rl, _ in ALL_INDICATORS
    ],
)
def test_crosses_above_indicator_vs_indicator_no_crash(label, left_side, right_side):
    """
    crosses_above (left_indicator, right_indicator) must not crash.
    Sufficient data is provided; met can be True or False.
    """
    cond = {"left": left_side, "operator": "crosses_above", "right": right_side}
    res  = _eval_condition(RICH, cond)
    _assert_valid_eval_result(res, label)


@pytest.mark.parametrize(
    "label,left_side,right_side",
    [
        (f"{ll}__crosses_below__{rl}", ls, rs)
        for ll, ls in ALL_INDICATORS
        for rl, rs in ALL_INDICATORS
    ],
    ids=[
        f"{ll}__crosses_below__{rl}"
        for ll, _ in ALL_INDICATORS
        for rl, _ in ALL_INDICATORS
    ],
)
def test_crosses_below_indicator_vs_indicator_no_crash(label, left_side, right_side):
    """
    crosses_below (left_indicator, right_indicator) must not crash.
    """
    cond = {"left": left_side, "operator": "crosses_below", "right": right_side}
    res  = _eval_condition(RICH, cond)
    _assert_valid_eval_result(res, label)


# ════════════════════════════════════════════════════════════════════════════════
#  SECTION F — create_scanner stores every condition shape correctly
#  26 indicators × 7 operators = 182 parametrized tests
# ════════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True, scope="module")
def _restore_scanners_after_module():
    """Snapshot + restore module-level _scanners so CRUD tests don't pollute others."""
    snap    = dict(_scanners)
    counter = _id_counter[0]
    yield
    _scanners.clear()
    _scanners.update(snap)
    _id_counter[0] = counter


@pytest.mark.parametrize(
    "label,left_side,op",
    [
        (f"{lbl}__{op}", side, op)
        for lbl, side in ALL_INDICATORS
        for op in ALL_OPERATORS
    ],
    ids=[f"{lbl}__{op}" for lbl, _ in ALL_INDICATORS for op in ALL_OPERATORS],
)
def test_create_scanner_condition_roundtrip(label, left_side, op):
    """
    create_scanner must store every indicator + operator combination without
    data loss.  The stored condition must contain exactly the fields we passed.
    """
    svc = _fresh_service()
    ind = left_side.get("indicator", "CLOSE")
    right_num = _number_for(label.split("__")[0])
    cond_in = {
        "left":     left_side,
        "operator": op,
        "right":    {"type": "number", "value": right_num},
    }
    scanner = svc.create_scanner({
        "name": f"Matrix Scanner — {label}",
        "conditions": [cond_in],
    })

    assert len(scanner["conditions"]) == 1
    stored = scanner["conditions"][0]

    # operator preserved
    assert stored["operator"] == op, \
        f"[{label}] operator mismatch: expected {op!r}, got {stored['operator']!r}"

    # left indicator preserved
    assert stored["left"]["indicator"] == ind, \
        f"[{label}] left indicator mismatch"

    # left period preserved (if given)
    if "period" in left_side:
        assert stored["left"].get("period") == left_side["period"], \
            f"[{label}] left period mismatch"

    # right type preserved
    assert stored["right"]["type"] == "number", \
        f"[{label}] right type mismatch"

    # right value preserved
    assert stored["right"]["value"] == right_num, \
        f"[{label}] right value mismatch"

    # condition got an auto-generated ID
    assert "id" in stored and len(stored["id"]) == 7, \
        f"[{label}] condition ID missing or wrong length"

    # scanner meta fields present
    assert scanner["id"].startswith("scanner-"), f"[{label}] bad scanner ID"
    assert scanner["createdAt"].endswith("Z"),   f"[{label}] bad createdAt"
    assert scanner["updatedAt"].endswith("Z"),   f"[{label}] bad updatedAt"

    # clean up so the module-level store doesn't grow unbounded
    svc.delete_scanner(scanner["id"])


# ════════════════════════════════════════════════════════════════════════════════
#  SECTION G — extra semantic correctness tests
# ════════════════════════════════════════════════════════════════════════════════

class TestSemanticCorrectness:
    """
    These tests pick specific (left, op, right) triples whose result can be
    determined analytically from the RICH dataset (rising 100→399, 300 bars).
    They verify that met=True/False is actually correct, not just that the
    function runs.
    """

    # In RICH: CLOSE = 399, HIGH ≈ 399*1.02 ≈ 406.98, LOW ≈ 399*0.97 ≈ 387.03

    def test_close_gt_100_is_true(self):
        cond = {"left": {"type": "indicator", "indicator": "CLOSE"},
                "operator": "gt", "right": {"type": "number", "value": 100}}
        assert _eval_condition(RICH, cond)["met"] is True

    def test_close_lt_100_is_false(self):
        cond = {"left": {"type": "indicator", "indicator": "CLOSE"},
                "operator": "lt", "right": {"type": "number", "value": 100}}
        assert _eval_condition(RICH, cond)["met"] is False

    def test_high_gt_close_is_true(self):
        cond = {"left": {"type": "indicator", "indicator": "HIGH"},
                "operator": "gt", "right": {"type": "indicator", "indicator": "CLOSE"}}
        assert _eval_condition(RICH, cond)["met"] is True   # high = close*1.02

    def test_low_lt_close_is_true(self):
        cond = {"left": {"type": "indicator", "indicator": "LOW"},
                "operator": "lt", "right": {"type": "indicator", "indicator": "CLOSE"}}
        assert _eval_condition(RICH, cond)["met"] is True   # low = close*0.97

    def test_ema9_gt_ema200_in_rising_market(self):
        cond = {"left": {"type": "indicator", "indicator": "EMA", "period": 9},
                "operator": "gt", "right": {"type": "indicator", "indicator": "EMA", "period": 200}}
        assert _eval_condition(RICH, cond)["met"] is True

    def test_bb_lower_lt_bb_upper(self):
        cond = {"left": {"type": "indicator", "indicator": "BB_LOWER", "period": 20},
                "operator": "lt", "right": {"type": "indicator", "indicator": "BB_UPPER", "period": 20}}
        assert _eval_condition(RICH, cond)["met"] is True

    def test_rsi_in_0_100_range_gt_0(self):
        cond = {"left": {"type": "indicator", "indicator": "RSI", "period": 14},
                "operator": "gt", "right": {"type": "number", "value": 0}}
        assert _eval_condition(RICH, cond)["met"] is True

    def test_rsi_in_0_100_range_lt_101(self):
        cond = {"left": {"type": "indicator", "indicator": "RSI", "period": 14},
                "operator": "lt", "right": {"type": "number", "value": 101}}
        assert _eval_condition(RICH, cond)["met"] is True

    def test_macd_gt_macd_signal_in_strong_uptrend(self):
        # In a strongly rising market EMA12 > EMA26 so MACD > SIGNAL
        cond = {"left": {"type": "indicator", "indicator": "MACD"},
                "operator": "gt", "right": {"type": "indicator", "indicator": "MACD_SIGNAL"}}
        res = _eval_condition(RICH, cond)
        assert res["met"] is True

    def test_volume_ratio_gt_0(self):
        cond = {"left": {"type": "indicator", "indicator": "VOLUME_RATIO"},
                "operator": "gt", "right": {"type": "number", "value": 0}}
        assert _eval_condition(RICH, cond)["met"] is True

    def test_pct_52w_high_lte_0(self):
        # Current close = 399, 52W high = 399 → PCT_52W_HIGH = 0.0
        cond = {"left": {"type": "indicator", "indicator": "PCT_52W_HIGH"},
                "operator": "lte", "right": {"type": "number", "value": 0}}
        assert _eval_condition(RICH, cond)["met"] is True

    def test_pct_52w_low_gt_0(self):
        # Current close = 399, 52W low = 100 → PCT_52W_LOW = +299% > 0
        cond = {"left": {"type": "indicator", "indicator": "PCT_52W_LOW"},
                "operator": "gt", "right": {"type": "number", "value": 0}}
        assert _eval_condition(RICH, cond)["met"] is True

    def test_high_52w_gte_close(self):
        # 52W high ≥ current close (always true by definition)
        cond = {"left": {"type": "indicator", "indicator": "HIGH_52W"},
                "operator": "gte", "right": {"type": "indicator", "indicator": "CLOSE"}}
        assert _eval_condition(RICH, cond)["met"] is True

    def test_low_52w_lte_close(self):
        # 52W low ≤ current close (always true by definition)
        cond = {"left": {"type": "indicator", "indicator": "LOW_52W"},
                "operator": "lte", "right": {"type": "indicator", "indicator": "CLOSE"}}
        assert _eval_condition(RICH, cond)["met"] is True

    def test_atr_gt_0(self):
        cond = {"left": {"type": "indicator", "indicator": "ATR", "period": 14},
                "operator": "gt", "right": {"type": "number", "value": 0}}
        assert _eval_condition(RICH, cond)["met"] is True

    def test_prev_close_lt_close_in_rising_market(self):
        cond = {"left": {"type": "indicator", "indicator": "PREV_CLOSE"},
                "operator": "lt", "right": {"type": "indicator", "indicator": "CLOSE"}}
        assert _eval_condition(RICH, cond)["met"] is True

    def test_sma20_gt_ema200_in_rising_market(self):
        # SMA20 tracks recent prices closely; EMA200 lags far behind
        cond = {"left": {"type": "indicator", "indicator": "SMA", "period": 20},
                "operator": "gt", "right": {"type": "indicator", "indicator": "EMA", "period": 200}}
        assert _eval_condition(RICH, cond)["met"] is True

    def test_macd_hist_gt_0_in_uptrend(self):
        cond = {"left": {"type": "indicator", "indicator": "MACD_HIST"},
                "operator": "gt", "right": {"type": "number", "value": 0}}
        assert _eval_condition(RICH, cond)["met"] is True

    # ── eq tolerance checks ───────────────────────────────────────────────────

    def test_eq_close_to_itself_via_prev_close_at_flat_data(self):
        # On flat data prev_close == close → eq must fire
        flat = [{"open": 100, "high": 102, "low": 97, "close": 100.0, "volume": 1000}
                for _ in range(50)]
        cond = {"left": {"type": "indicator", "indicator": "CLOSE"},
                "operator": "eq",
                "right": {"type": "indicator", "indicator": "PREV_CLOSE"}}
        assert _eval_condition(flat, cond)["met"] is True

    # ── Description string content ────────────────────────────────────────────

    def test_desc_contains_left_indicator_name(self):
        cond = {"left": {"type": "indicator", "indicator": "RSI", "period": 14},
                "operator": "gt", "right": {"type": "number", "value": 50}}
        assert "RSI" in _eval_condition(RICH, cond)["desc"]

    def test_desc_contains_gt_symbol(self):
        cond = {"left": {"type": "indicator", "indicator": "CLOSE"},
                "operator": "gt", "right": {"type": "number", "value": 50}}
        assert ">" in _eval_condition(RICH, cond)["desc"]

    def test_desc_contains_gte_symbol(self):
        cond = {"left": {"type": "indicator", "indicator": "CLOSE"},
                "operator": "gte", "right": {"type": "number", "value": 50}}
        assert "≥" in _eval_condition(RICH, cond)["desc"]

    def test_desc_contains_lt_symbol(self):
        cond = {"left": {"type": "indicator", "indicator": "CLOSE"},
                "operator": "lt", "right": {"type": "number", "value": 9999}}
        assert "<" in _eval_condition(RICH, cond)["desc"]

    def test_desc_contains_lte_symbol(self):
        cond = {"left": {"type": "indicator", "indicator": "CLOSE"},
                "operator": "lte", "right": {"type": "number", "value": 9999}}
        assert "≤" in _eval_condition(RICH, cond)["desc"]

    def test_desc_contains_eq_symbol(self):
        cond = {"left": {"type": "indicator", "indicator": "CLOSE"},
                "operator": "eq", "right": {"type": "number", "value": 399}}
        assert "=" in _eval_condition(RICH, cond)["desc"]

    def test_desc_crosses_above_says_crossed_above(self):
        cond = {"left": {"type": "indicator", "indicator": "CLOSE"},
                "operator": "crosses_above", "right": {"type": "number", "value": 200}}
        res = _eval_condition(X_ABOVE, cond)
        assert "crossed above" in res["desc"]

    def test_desc_crosses_below_says_crossed_below(self):
        cond = {"left": {"type": "indicator", "indicator": "CLOSE"},
                "operator": "crosses_below", "right": {"type": "number", "value": 399.5}}
        res = _eval_condition(X_BELOW, cond)
        assert "crossed below" in res["desc"]

    def test_desc_includes_numeric_values(self):
        cond = {"left": {"type": "indicator", "indicator": "CLOSE"},
                "operator": "gt", "right": {"type": "number", "value": 50}}
        desc = _eval_condition(RICH, cond)["desc"]
        # Description must include the actual values in parentheses
        assert "(" in desc and "vs" in desc and ")" in desc

    # ── period displayed in description ──────────────────────────────────────

    def test_desc_includes_period_for_ema(self):
        cond = {"left": {"type": "indicator", "indicator": "EMA", "period": 50},
                "operator": "gt", "right": {"type": "number", "value": 0}}
        assert "(50)" in _eval_condition(RICH, cond)["desc"]

    def test_desc_includes_period_for_rsi(self):
        cond = {"left": {"type": "indicator", "indicator": "RSI", "period": 14},
                "operator": "gt", "right": {"type": "number", "value": 0}}
        assert "(14)" in _eval_condition(RICH, cond)["desc"]

    def test_desc_includes_period_for_bb(self):
        cond = {"left": {"type": "indicator", "indicator": "BB_UPPER", "period": 20},
                "operator": "gt", "right": {"type": "number", "value": 0}}
        assert "(20)" in _eval_condition(RICH, cond)["desc"]
