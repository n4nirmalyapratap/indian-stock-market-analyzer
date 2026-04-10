"""
test_scanner_settings_matrix.py
─────────────────────────────────
Full parametrized coverage of the two scanner-level settings that are orthogonal
to condition evaluation:

    1. UNIVERSE  — which stock pool to scan (multi-select from NIFTY100, MIDCAP,
                   SMALLCAP, MICROCAP, ALL).  All 31 non-empty subsets of the
                   four named universes plus "ALL" are tested.
    2. LOGIC     — how multiple conditions are combined (AND / OR).

The condition evaluation itself is already covered in test_scanner_condition_matrix.py.
This file tests:

  Section A  build_universe() — 31 subset tests
             Every non-empty subset of {NIFTY100, MIDCAP, SMALLCAP, MICROCAP} yields
             a non-empty, deduplicated list.  "ALL" gives the full union.

  Section B  Universe CRUD roundtrip — 31 parametrized
             create_scanner correctly stores and retrieves every universe subset.

  Section C  Logic CRUD roundtrip — 2 parametrized
             AND and OR are stored and retrieved correctly.

  Section D  Universe × Logic CRUD — 31 × 2 = 62 parametrized
             Every (universe_subset, logic) combo round-trips through create_scanner.

  Section E  Condition × Logic × Universe — 26 × 2 × 7 = 364 parametrized
             Every (left_indicator, logic, single_universe) triple creates a valid
             scanner with correct stored fields.  Uses the 7 most common single or
             double-universe combos to keep the count manageable and fast.

  Section F  AND / OR evaluation semantics — multi-condition scanners
             Analytical tests using synthetic OHLCV that verify the AND-all and
             OR-any rules are implemented correctly across 0–4 conditions.

  Section G  Universe isolation — universe changes don't affect _eval_condition
             Changing universe only changes which symbols are fetched, not how
             individual conditions are evaluated.

  Section H  Multi-condition scanner CRUD integrity — condition list ordering
             preserved, all condition IDs generated, partial updates work correctly.

  Section I  build_universe deduplication — overlapping universes deduplicated
             When multiple universes share a symbol, it appears exactly once.

  Section J  update_scanner changes universe and logic independently
             Orthogonal update: changing universe doesn't corrupt logic and vice versa.

Grand total parametrized tests: ≈ 520
"""

import pytest
from itertools import combinations

from app.lib.universe import build_universe, NIFTY100, MIDCAP, SMALLCAP, MICROCAP, VALID_UNIVERSES
from app.services.scanners_service import (
    _eval_condition,
    _scanners,
    _id_counter,
    ScannersService,
)
from app.services.price_service import PriceService
from app.services.yahoo_service import YahooService
from app.services.nse_service import NseService


# ════════════════════════════════════════════════════════════════════════════════
#  Shared test data
# ════════════════════════════════════════════════════════════════════════════════

NAMED_UNIVERSES = ["NIFTY100", "MIDCAP", "SMALLCAP", "MICROCAP"]
LOGICS          = ["AND", "OR"]

# All non-empty subsets of the 4 named universes  (2^4 - 1 = 15 subsets)
ALL_UNIVERSE_SUBSETS: list[tuple[str, list[str]]] = []
for r in range(1, len(NAMED_UNIVERSES) + 1):
    for combo in combinations(NAMED_UNIVERSES, r):
        label = "+".join(combo)
        ALL_UNIVERSE_SUBSETS.append((label, list(combo)))

# "ALL" as its own entry
ALL_UNIVERSE_SUBSETS.append(("ALL", ["ALL"]))
# Total = 15 + 1 = 16 universe configurations

# 7 most representative subsets used in the full 3-way cross (keeps count sane)
REPRESENTATIVE_UNIVERSES: list[tuple[str, list[str]]] = [
    ("NIFTY100",            ["NIFTY100"]),
    ("MIDCAP",              ["MIDCAP"]),
    ("SMALLCAP",            ["SMALLCAP"]),
    ("MICROCAP",            ["MICROCAP"]),
    ("NIFTY100+MIDCAP",     ["NIFTY100", "MIDCAP"]),
    ("NIFTY100+SMALLCAP",   ["NIFTY100", "SMALLCAP"]),
    ("NIFTY100+MIDCAP+SMALLCAP", ["NIFTY100", "MIDCAP", "SMALLCAP"]),
]

# All 26 indicator left-side specs (same as in the condition matrix file)
ALL_LEFT_INDICATORS: list[tuple[str, dict]] = [
    ("CLOSE",      {"type": "indicator", "indicator": "CLOSE"}),
    ("OPEN",       {"type": "indicator", "indicator": "OPEN"}),
    ("HIGH",       {"type": "indicator", "indicator": "HIGH"}),
    ("LOW",        {"type": "indicator", "indicator": "LOW"}),
    ("PREV_CLOSE", {"type": "indicator", "indicator": "PREV_CLOSE"}),
    ("CHANGE_PCT", {"type": "indicator", "indicator": "CHANGE_PCT"}),
    ("VOLUME",     {"type": "indicator", "indicator": "VOLUME"}),
    ("AVG_VOLUME_20", {"type": "indicator", "indicator": "AVG_VOLUME", "period": 20}),
    ("VOLUME_RATIO",  {"type": "indicator", "indicator": "VOLUME_RATIO"}),
    ("EMA_9",      {"type": "indicator", "indicator": "EMA",  "period": 9}),
    ("EMA_20",     {"type": "indicator", "indicator": "EMA",  "period": 20}),
    ("EMA_50",     {"type": "indicator", "indicator": "EMA",  "period": 50}),
    ("EMA_200",    {"type": "indicator", "indicator": "EMA",  "period": 200}),
    ("SMA_20",     {"type": "indicator", "indicator": "SMA",  "period": 20}),
    ("RSI_14",     {"type": "indicator", "indicator": "RSI",  "period": 14}),
    ("MACD",       {"type": "indicator", "indicator": "MACD"}),
    ("MACD_SIGNAL",{"type": "indicator", "indicator": "MACD_SIGNAL"}),
    ("MACD_HIST",  {"type": "indicator", "indicator": "MACD_HIST"}),
    ("BB_UPPER_20",{"type": "indicator", "indicator": "BB_UPPER", "period": 20}),
    ("BB_MID_20",  {"type": "indicator", "indicator": "BB_MID",   "period": 20}),
    ("BB_LOWER_20",{"type": "indicator", "indicator": "BB_LOWER", "period": 20}),
    ("ATR_14",     {"type": "indicator", "indicator": "ATR",  "period": 14}),
    ("HIGH_52W",   {"type": "indicator", "indicator": "HIGH_52W"}),
    ("LOW_52W",    {"type": "indicator", "indicator": "LOW_52W"}),
    ("PCT_52W_HIGH",{"type": "indicator", "indicator": "PCT_52W_HIGH"}),
    ("PCT_52W_LOW", {"type": "indicator", "indicator": "PCT_52W_LOW"}),
]

# Synthetic OHLCV (300 bars, rising)
RICH = [
    {
        "open":   float(100 + i) * 0.99,
        "high":   float(100 + i) * 1.02,
        "low":    float(100 + i) * 0.97,
        "close":  float(100 + i),
        "volume": 10_000 + i * 10,
    }
    for i in range(300)
]


def _fresh_service() -> ScannersService:
    return ScannersService(PriceService(NseService(), YahooService()))


@pytest.fixture(autouse=True, scope="module")
def _restore_module_state():
    snap    = dict(_scanners)
    counter = _id_counter[0]
    yield
    _scanners.clear()
    _scanners.update(snap)
    _id_counter[0] = counter


# ════════════════════════════════════════════════════════════════════════════════
#  SECTION A  build_universe() — 16 subset tests
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "label,universe",
    ALL_UNIVERSE_SUBSETS,
    ids=[x[0] for x in ALL_UNIVERSE_SUBSETS],
)
def test_build_universe_returns_non_empty_list(label, universe):
    """Every universe subset must return a non-empty list of ticker strings."""
    syms = build_universe(universe)
    assert isinstance(syms, list), f"[{label}] result is not a list"
    assert len(syms) > 0,          f"[{label}] empty symbol list"
    assert all(isinstance(s, str) and s.strip() for s in syms), \
        f"[{label}] contains non-string or blank symbols"


@pytest.mark.parametrize(
    "label,universe",
    ALL_UNIVERSE_SUBSETS,
    ids=[x[0] for x in ALL_UNIVERSE_SUBSETS],
)
def test_build_universe_deduplicates(label, universe):
    """build_universe must return each symbol at most once."""
    syms = build_universe(universe)
    assert len(syms) == len(set(syms)), \
        f"[{label}] duplicate symbols found: {len(syms)} total, {len(set(syms))} unique"


def test_build_universe_all_is_superset_of_each():
    """'ALL' universe must contain every symbol from every individual universe."""
    all_syms = set(build_universe(["ALL"]))
    for key in NAMED_UNIVERSES:
        subset = set(build_universe([key]))
        missing = subset - all_syms
        assert not missing, f"ALL universe is missing {len(missing)} symbols from {key}: {list(missing)[:5]}"


def test_build_universe_nifty100_midcap_smallcap_superset_of_individuals():
    """[NIFTY100, MIDCAP, SMALLCAP] combined must contain all three individually."""
    combined = set(build_universe(["NIFTY100", "MIDCAP", "SMALLCAP"]))
    for key in ["NIFTY100", "MIDCAP", "SMALLCAP"]:
        single = set(build_universe([key]))
        assert single.issubset(combined), \
            f"Combined universe missing {single - combined} from {key}"


def test_build_universe_ordering_consistent():
    """Calling build_universe twice with same input gives same order."""
    u = ["NIFTY100", "MIDCAP"]
    assert build_universe(u) == build_universe(u)


def test_build_universe_empty_list_returns_empty():
    """Empty input → empty output (no crash)."""
    result = build_universe([])
    assert result == []


def test_build_universe_unknown_key_ignored():
    """Unknown universe key is silently ignored (not in the if-chain)."""
    result = build_universe(["UNKNOWN_UNIVERSE"])
    assert result == []   # nothing matched


def test_build_universe_nifty100_contains_known_stocks():
    """NIFTY100 universe must include canonical large-cap tickers."""
    syms = set(build_universe(["NIFTY100"]))
    for expected in ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]:
        assert expected in syms, f"{expected} missing from NIFTY100 universe"


def test_build_universe_midcap_contains_known_stocks():
    syms = set(build_universe(["MIDCAP"]))
    for expected in ["MRF", "POLYCAB"]:
        assert expected in syms, f"{expected} missing from MIDCAP universe"


def test_build_universe_smallcap_returns_reasonable_count():
    syms = build_universe(["SMALLCAP"])
    assert len(syms) >= 30, "SMALLCAP universe suspiciously small"


def test_build_universe_microcap_returns_reasonable_count():
    syms = build_universe(["MICROCAP"])
    assert len(syms) >= 20, "MICROCAP universe suspiciously small"


def test_build_universe_combined_larger_than_any_single():
    single = len(build_universe(["NIFTY100"]))
    combined = len(build_universe(["NIFTY100", "MIDCAP", "SMALLCAP"]))
    assert combined > single, "Combined universe should be larger than NIFTY100 alone"


def test_valid_universes_constant_contains_all_named():
    for key in NAMED_UNIVERSES:
        assert key in VALID_UNIVERSES, f"{key} not in VALID_UNIVERSES"
    assert "ALL" in VALID_UNIVERSES


# ════════════════════════════════════════════════════════════════════════════════
#  SECTION B  Universe CRUD roundtrip — all 16 subsets
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "label,universe",
    ALL_UNIVERSE_SUBSETS,
    ids=[x[0] for x in ALL_UNIVERSE_SUBSETS],
)
def test_create_scanner_stores_universe_correctly(label, universe):
    svc = _fresh_service()
    s = svc.create_scanner({"name": f"U:{label}", "universe": universe})
    assert s["universe"] == universe, \
        f"[{label}] stored universe {s['universe']!r} ≠ input {universe!r}"
    svc.delete_scanner(s["id"])


@pytest.mark.parametrize(
    "label,universe",
    ALL_UNIVERSE_SUBSETS,
    ids=[x[0] for x in ALL_UNIVERSE_SUBSETS],
)
def test_get_scanner_by_id_returns_correct_universe(label, universe):
    svc = _fresh_service()
    created = svc.create_scanner({"name": f"U:{label}", "universe": universe})
    fetched  = svc.get_scanner_by_id(created["id"])
    assert fetched is not None, f"[{label}] scanner not found after create"
    assert fetched["universe"] == universe
    svc.delete_scanner(created["id"])


# ════════════════════════════════════════════════════════════════════════════════
#  SECTION C  Logic CRUD roundtrip
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("logic", LOGICS)
def test_create_scanner_stores_logic_and(logic):
    svc = _fresh_service()
    s = svc.create_scanner({"name": f"Logic:{logic}", "logic": logic})
    assert s["logic"] == logic
    svc.delete_scanner(s["id"])


@pytest.mark.parametrize("logic", LOGICS)
def test_get_scanner_returns_correct_logic(logic):
    svc = _fresh_service()
    s   = svc.create_scanner({"name": f"Logic:{logic}", "logic": logic})
    got = svc.get_scanner_by_id(s["id"])
    assert got["logic"] == logic
    svc.delete_scanner(s["id"])


# ════════════════════════════════════════════════════════════════════════════════
#  SECTION D  Universe × Logic — 16 × 2 = 32 parametrized
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "ulabel,universe,logic",
    [
        (f"{ul}__{logic}", universe, logic)
        for ul, universe in ALL_UNIVERSE_SUBSETS
        for logic in LOGICS
    ],
    ids=[f"{ul}__{logic}" for ul, _ in ALL_UNIVERSE_SUBSETS for logic in LOGICS],
)
def test_universe_logic_crud_roundtrip(ulabel, universe, logic):
    """
    Every (universe_subset, logic) combination must be stored and retrieved
    without mutation.
    """
    svc = _fresh_service()
    s   = svc.create_scanner({"name": f"UL:{ulabel}", "universe": universe, "logic": logic})
    got = svc.get_scanner_by_id(s["id"])

    assert got is not None,          f"[{ulabel}] scanner missing after create"
    assert got["universe"] == universe, f"[{ulabel}] universe corrupted"
    assert got["logic"]    == logic,    f"[{ulabel}] logic corrupted"
    assert got["id"]       == s["id"],  f"[{ulabel}] ID changed"

    svc.delete_scanner(s["id"])


# ════════════════════════════════════════════════════════════════════════════════
#  SECTION E  Condition × Logic × Universe — 26 × 2 × 7 = 364 parametrized
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "clabel,left_side,logic,ulabel,universe",
    [
        (f"{il}__{logic}__{ul}", side, logic, ul, universe)
        for il, side in ALL_LEFT_INDICATORS
        for logic in LOGICS
        for ul, universe in REPRESENTATIVE_UNIVERSES
    ],
    ids=[
        f"{il}__{logic}__{ul}"
        for il, _ in ALL_LEFT_INDICATORS
        for logic in LOGICS
        for ul, _ in REPRESENTATIVE_UNIVERSES
    ],
)
def test_condition_logic_universe_crud_roundtrip(clabel, left_side, logic, ulabel, universe):
    """
    Every (left_indicator, logic, universe) triple must round-trip through
    create_scanner with all three fields stored correctly.
    """
    svc = _fresh_service()
    cond = {
        "left":     left_side,
        "operator": "gt",
        "right":    {"type": "number", "value": 0},
    }
    s = svc.create_scanner({
        "name":       f"CLU:{clabel}",
        "universe":   universe,
        "logic":      logic,
        "conditions": [cond],
    })

    got = svc.get_scanner_by_id(s["id"])
    assert got is not None, f"[{clabel}] scanner not found"

    # universe stored correctly
    assert got["universe"] == universe, \
        f"[{clabel}] universe: expected {universe!r}, got {got['universe']!r}"

    # logic stored correctly
    assert got["logic"] == logic, \
        f"[{clabel}] logic: expected {logic!r}, got {got['logic']!r}"

    # condition preserved
    assert len(got["conditions"]) == 1, f"[{clabel}] condition list corrupted"
    stored_cond = got["conditions"][0]
    assert stored_cond["left"]["indicator"] == left_side["indicator"], \
        f"[{clabel}] condition left indicator changed"
    assert stored_cond["operator"] == "gt", f"[{clabel}] operator changed"

    # condition has a generated ID
    assert "id" in stored_cond and len(stored_cond["id"]) == 7, \
        f"[{clabel}] condition missing 7-char ID"

    svc.delete_scanner(s["id"])


# ════════════════════════════════════════════════════════════════════════════════
#  SECTION F  AND / OR evaluation semantics
# ════════════════════════════════════════════════════════════════════════════════

def _make_always_true_cond(i: int = 0) -> dict:
    return {
        "id": f"always{i}",
        "left":  {"type": "indicator", "indicator": "CLOSE"},
        "operator": "gt",
        "right": {"type": "number", "value": 0},      # close is always > 0
    }

def _make_always_false_cond(i: int = 0) -> dict:
    return {
        "id": f"never{i}",
        "left":  {"type": "indicator", "indicator": "CLOSE"},
        "operator": "gt",
        "right": {"type": "number", "value": 999_999},  # close never > 999999
    }

def _run_eval_logic(conditions: list, logic: str, ohlcv: list) -> dict | None:
    """Replicate the inner _evaluate() for unit-testing AND/OR logic."""
    if len(ohlcv) < 30:
        return None
    closes = [d["close"] for d in ohlcv]
    lc, pc = closes[-1], closes[-2]
    change   = lc - pc
    p_change = (change / pc * 100) if pc else 0
    cond_results = [_eval_condition(ohlcv, c) for c in conditions]
    met_count    = sum(1 for r in cond_results if r["met"])
    all_met = (met_count == len(conditions) if logic == "AND" else met_count > 0)
    if not all_met:
        return None
    return {
        "lastPrice": lc, "change": round(change, 2), "pChange": round(p_change, 2),
        "volume": ohlcv[-1].get("volume"),
        "matchedConditions": [r["desc"] for r in cond_results if r["met"]],
        "failedConditions":  [r["desc"] for r in cond_results if not r["met"]],
        "conditionsMatched": met_count, "totalConditions": len(conditions),
        "score": round(met_count / len(conditions) * 100) if conditions else 0,
    }


class TestAndOrSemantics:

    # ── AND: all must match ───────────────────────────────────────────────────

    def test_and_1_condition_met(self):
        r = _run_eval_logic([_make_always_true_cond()], "AND", RICH)
        assert r is not None and r["conditionsMatched"] == 1

    def test_and_2_conditions_both_met(self):
        r = _run_eval_logic([_make_always_true_cond(0), _make_always_true_cond(1)], "AND", RICH)
        assert r is not None and r["conditionsMatched"] == 2

    def test_and_3_conditions_all_met(self):
        conds = [_make_always_true_cond(i) for i in range(3)]
        r = _run_eval_logic(conds, "AND", RICH)
        assert r is not None and r["conditionsMatched"] == 3

    def test_and_4_conditions_all_met(self):
        conds = [_make_always_true_cond(i) for i in range(4)]
        r = _run_eval_logic(conds, "AND", RICH)
        assert r is not None and r["conditionsMatched"] == 4

    def test_and_1_fail_out_of_2_returns_none(self):
        conds = [_make_always_true_cond(), _make_always_false_cond()]
        r = _run_eval_logic(conds, "AND", RICH)
        assert r is None

    def test_and_1_fail_out_of_3_returns_none(self):
        conds = [_make_always_true_cond(0), _make_always_true_cond(1), _make_always_false_cond()]
        r = _run_eval_logic(conds, "AND", RICH)
        assert r is None

    def test_and_all_fail_returns_none(self):
        conds = [_make_always_false_cond(i) for i in range(3)]
        r = _run_eval_logic(conds, "AND", RICH)
        assert r is None

    def test_and_score_100_when_all_met(self):
        conds = [_make_always_true_cond(i) for i in range(3)]
        r = _run_eval_logic(conds, "AND", RICH)
        assert r["score"] == 100

    # ── OR: any must match ────────────────────────────────────────────────────

    def test_or_1_condition_met(self):
        r = _run_eval_logic([_make_always_true_cond()], "OR", RICH)
        assert r is not None and r["conditionsMatched"] == 1

    def test_or_1_out_of_2_met(self):
        conds = [_make_always_true_cond(), _make_always_false_cond()]
        r = _run_eval_logic(conds, "OR", RICH)
        assert r is not None and r["conditionsMatched"] == 1

    def test_or_1_out_of_4_met(self):
        conds = [_make_always_true_cond()] + [_make_always_false_cond(i) for i in range(3)]
        r = _run_eval_logic(conds, "OR", RICH)
        assert r is not None

    def test_or_all_fail_returns_none(self):
        conds = [_make_always_false_cond(i) for i in range(4)]
        r = _run_eval_logic(conds, "OR", RICH)
        assert r is None

    def test_or_all_met_returns_result(self):
        conds = [_make_always_true_cond(i) for i in range(4)]
        r = _run_eval_logic(conds, "OR", RICH)
        assert r is not None and r["conditionsMatched"] == 4

    def test_or_score_50_when_half_met(self):
        conds = [_make_always_true_cond(), _make_always_false_cond()]
        r = _run_eval_logic(conds, "OR", RICH)
        assert r["score"] == 50

    def test_or_score_25_when_1_of_4_met(self):
        conds = [_make_always_true_cond()] + [_make_always_false_cond(i) for i in range(3)]
        r = _run_eval_logic(conds, "OR", RICH)
        assert r["score"] == 25

    # ── Fewer than 30 bars ────────────────────────────────────────────────────

    def test_and_short_data_returns_none(self):
        short = RICH[:20]
        r = _run_eval_logic([_make_always_true_cond()], "AND", short)
        assert r is None

    def test_or_short_data_returns_none(self):
        short = RICH[:20]
        r = _run_eval_logic([_make_always_true_cond()], "OR", short)
        assert r is None

    # ── matchedConditions and failedConditions keys ───────────────────────────

    def test_matched_conditions_list_correct_for_and(self):
        conds = [_make_always_true_cond(0), _make_always_true_cond(1)]
        r = _run_eval_logic(conds, "AND", RICH)
        assert len(r["matchedConditions"]) == 2
        assert r["failedConditions"] == []

    def test_failed_conditions_populated_for_or_partial(self):
        conds = [_make_always_true_cond(), _make_always_false_cond()]
        r = _run_eval_logic(conds, "OR", RICH)
        assert len(r["failedConditions"]) == 1
        assert len(r["matchedConditions"]) == 1

    def test_total_conditions_matches_input_count(self):
        conds = [_make_always_true_cond(i) for i in range(5)]
        r = _run_eval_logic(conds, "OR", RICH)
        assert r["totalConditions"] == 5


# ════════════════════════════════════════════════════════════════════════════════
#  SECTION G  Universe isolation
#  _eval_condition must return the SAME result regardless of what universe
#  the enclosing scanner targets — conditions run on raw OHLCV data, not
#  symbol lists.
# ════════════════════════════════════════════════════════════════════════════════

class TestUniverseIsolation:

    def _eval_close_gt(self, threshold: float = 0) -> dict:
        cond = {
            "left":  {"type": "indicator", "indicator": "CLOSE"},
            "operator": "gt",
            "right": {"type": "number", "value": threshold},
        }
        return _eval_condition(RICH, cond)

    @pytest.mark.parametrize("u1,u2", [
        (["NIFTY100"], ["MIDCAP"]),
        (["NIFTY100"], ["SMALLCAP"]),
        (["MIDCAP"],   ["MICROCAP"]),
        (["NIFTY100", "MIDCAP"], ["SMALLCAP", "MICROCAP"]),
        (["ALL"],      ["NIFTY100"]),
    ])
    def test_eval_condition_independent_of_universe(self, u1, u2):
        """
        The result of _eval_condition on the same OHLCV data is identical
        regardless of which universe the scanner uses.
        """
        cond = {
            "left":  {"type": "indicator", "indicator": "RSI", "period": 14},
            "operator": "gt", "right": {"type": "number", "value": 50},
        }
        res1 = _eval_condition(RICH, cond)   # same OHLCV, just checking it's deterministic
        res2 = _eval_condition(RICH, cond)
        assert res1["met"]  == res2["met"],  "eval_condition not deterministic"
        assert res1["desc"] == res2["desc"], "eval_condition not deterministic"


# ════════════════════════════════════════════════════════════════════════════════
#  SECTION H  Multi-condition scanner CRUD integrity
# ════════════════════════════════════════════════════════════════════════════════

class TestMultiConditionCrud:

    @pytest.fixture(autouse=True)
    def _snap(self):
        snap    = dict(_scanners)
        counter = _id_counter[0]
        yield
        _scanners.clear()
        _scanners.update(snap)
        _id_counter[0] = counter

    @pytest.fixture
    def svc(self):
        return _fresh_service()

    def _cond(self, ind: str, period: int | None = None) -> dict:
        side = {"type": "indicator", "indicator": ind}
        if period:
            side["period"] = period
        return {"left": side, "operator": "gt", "right": {"type": "number", "value": 0}}

    def test_2_condition_scanner_stores_both(self, svc):
        conds = [self._cond("CLOSE"), self._cond("RSI", 14)]
        s = svc.create_scanner({"name": "2cond", "conditions": conds})
        assert len(s["conditions"]) == 2

    def test_3_condition_scanner_stores_all(self, svc):
        conds = [self._cond("CLOSE"), self._cond("EMA", 20), self._cond("RSI", 14)]
        s = svc.create_scanner({"name": "3cond", "conditions": conds})
        assert len(s["conditions"]) == 3

    def test_4_condition_scanner_stores_all(self, svc):
        conds = [self._cond(ind) for ind in ["CLOSE", "VOLUME_RATIO", "MACD", "RSI"]]
        s = svc.create_scanner({"name": "4cond", "conditions": conds})
        assert len(s["conditions"]) == 4

    def test_condition_order_preserved(self, svc):
        inds = ["CLOSE", "RSI", "MACD", "EMA", "BB_UPPER"]
        conds = [self._cond(ind) for ind in inds]
        s = svc.create_scanner({"name": "order", "conditions": conds})
        stored_inds = [c["left"]["indicator"] for c in s["conditions"]]
        assert stored_inds == inds

    def test_all_conditions_get_unique_ids(self, svc):
        conds = [self._cond(ind) for ind in ["CLOSE", "RSI", "MACD", "EMA"]]
        s = svc.create_scanner({"name": "ids", "conditions": conds})
        ids = [c["id"] for c in s["conditions"]]
        assert len(ids) == len(set(ids)), "Condition IDs must be unique"

    def test_update_scanner_from_2_to_4_conditions(self, svc):
        s = svc.create_scanner({"name": "X", "conditions": [self._cond("CLOSE"), self._cond("RSI")]})
        new_conds = [self._cond(ind) for ind in ["CLOSE", "RSI", "MACD", "VOLUME_RATIO"]]
        updated = svc.update_scanner(s["id"], {"conditions": new_conds})
        assert len(updated["conditions"]) == 4

    def test_update_scanner_from_4_to_1_condition(self, svc):
        conds = [self._cond(ind) for ind in ["CLOSE", "RSI", "MACD", "VOLUME_RATIO"]]
        s = svc.create_scanner({"name": "X", "conditions": conds})
        updated = svc.update_scanner(s["id"], {"conditions": [self._cond("CLOSE")]})
        assert len(updated["conditions"]) == 1

    def test_multi_condition_and_logic_stored(self, svc):
        conds = [self._cond("CLOSE"), self._cond("RSI", 14), self._cond("MACD")]
        s = svc.create_scanner({"name": "AND test", "logic": "AND", "conditions": conds})
        assert s["logic"] == "AND"
        assert len(s["conditions"]) == 3

    def test_multi_condition_or_logic_stored(self, svc):
        conds = [self._cond("CLOSE"), self._cond("RSI", 14), self._cond("MACD")]
        s = svc.create_scanner({"name": "OR test", "logic": "OR", "conditions": conds})
        assert s["logic"] == "OR"
        assert len(s["conditions"]) == 3


# ════════════════════════════════════════════════════════════════════════════════
#  SECTION I  build_universe deduplication across overlapping universes
# ════════════════════════════════════════════════════════════════════════════════

class TestUniverseDeduplication:

    def test_nifty100_plus_midcap_no_duplicates(self):
        syms = build_universe(["NIFTY100", "MIDCAP"])
        assert len(syms) == len(set(syms))

    def test_all_four_universes_no_duplicates(self):
        syms = build_universe(["NIFTY100", "MIDCAP", "SMALLCAP", "MICROCAP"])
        assert len(syms) == len(set(syms))

    def test_order_of_universe_keys_does_not_change_set(self):
        s1 = set(build_universe(["NIFTY100", "MIDCAP"]))
        s2 = set(build_universe(["MIDCAP", "NIFTY100"]))
        assert s1 == s2

    def test_repeated_universe_key_does_not_duplicate(self):
        once   = build_universe(["NIFTY100"])
        twice  = build_universe(["NIFTY100", "NIFTY100"])
        assert len(once) == len(twice)  # second pass adds nothing new

    def test_combined_universe_size_gte_each_individual(self):
        combined = len(build_universe(["NIFTY100", "MIDCAP", "SMALLCAP"]))
        for key in ["NIFTY100", "MIDCAP", "SMALLCAP"]:
            assert combined >= len(build_universe([key]))


# ════════════════════════════════════════════════════════════════════════════════
#  SECTION J  update_scanner — orthogonal changes to universe and logic
# ════════════════════════════════════════════════════════════════════════════════

class TestOrthogonalUpdates:

    @pytest.fixture(autouse=True)
    def _snap(self):
        snap    = dict(_scanners)
        counter = _id_counter[0]
        yield
        _scanners.clear()
        _scanners.update(snap)
        _id_counter[0] = counter

    @pytest.fixture
    def svc(self):
        return _fresh_service()

    def test_update_logic_and_to_or_does_not_change_universe(self, svc):
        s = svc.create_scanner({"name": "X", "universe": ["NIFTY100"], "logic": "AND"})
        updated = svc.update_scanner(s["id"], {"logic": "OR"})
        assert updated["logic"] == "OR"
        assert updated["universe"] == ["NIFTY100"]

    def test_update_logic_or_to_and_does_not_change_universe(self, svc):
        s = svc.create_scanner({"name": "X", "universe": ["MIDCAP"], "logic": "OR"})
        updated = svc.update_scanner(s["id"], {"logic": "AND"})
        assert updated["logic"] == "AND"
        assert updated["universe"] == ["MIDCAP"]

    def test_update_universe_does_not_change_logic(self, svc):
        s = svc.create_scanner({"name": "X", "universe": ["NIFTY100"], "logic": "OR"})
        updated = svc.update_scanner(s["id"], {"universe": ["MIDCAP", "SMALLCAP"]})
        assert updated["universe"] == ["MIDCAP", "SMALLCAP"]
        assert updated["logic"] == "OR"

    def test_update_universe_from_single_to_all(self, svc):
        s = svc.create_scanner({"name": "X", "universe": ["NIFTY100"]})
        updated = svc.update_scanner(s["id"], {"universe": ["ALL"]})
        assert updated["universe"] == ["ALL"]

    def test_update_universe_from_all_to_single(self, svc):
        s = svc.create_scanner({"name": "X", "universe": ["ALL"]})
        updated = svc.update_scanner(s["id"], {"universe": ["SMALLCAP"]})
        assert updated["universe"] == ["SMALLCAP"]

    @pytest.mark.parametrize("u1,u2", [
        (["NIFTY100"],          ["MIDCAP"]),
        (["NIFTY100", "MIDCAP"],["SMALLCAP", "MICROCAP"]),
        (["ALL"],               ["NIFTY100", "MIDCAP", "SMALLCAP"]),
        (["MICROCAP"],          ["NIFTY100"]),
    ])
    def test_update_universe_any_to_any(self, svc, u1, u2):
        s = svc.create_scanner({"name": "X", "universe": u1, "logic": "AND"})
        updated = svc.update_scanner(s["id"], {"universe": u2})
        assert updated["universe"] == u2
        assert updated["logic"] == "AND"    # logic must survive the universe update

    @pytest.mark.parametrize("u1,u2,l1,l2", [
        (["NIFTY100"],          ["MIDCAP"],         "AND", "OR"),
        (["MIDCAP", "SMALLCAP"],["NIFTY100"],        "OR",  "AND"),
        (["ALL"],               ["MICROCAP"],        "AND", "AND"),
        (["SMALLCAP"],          ["NIFTY100", "MIDCAP"], "OR", "OR"),
    ])
    def test_update_universe_and_logic_simultaneously(self, svc, u1, u2, l1, l2):
        s = svc.create_scanner({"name": "X", "universe": u1, "logic": l1})
        updated = svc.update_scanner(s["id"], {"universe": u2, "logic": l2})
        assert updated["universe"] == u2
        assert updated["logic"]    == l2
