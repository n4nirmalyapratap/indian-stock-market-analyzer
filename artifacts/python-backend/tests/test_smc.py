"""
test_smc.py — unit tests for the Smart Money Concepts primitives.

The detection module (app/lib/smc.py) is intentionally dependency-free, so
these tests import only it and run on a bare interpreter. Candles are built
explicitly (not via price helpers) so each gap/zone is hand-verifiable.

Phase 1 covers Fair Value Gaps (FVG): geometry, the significance gate,
mitigation tracking, lookback windowing, and malformed-input resilience.
"""
from app.lib import smc


# ── Builders ─────────────────────────────────────────────────────────────────

def _c(o, h, lo, c, v=1000) -> dict:
    return {"open": o, "high": h, "low": lo, "close": c, "volume": v}


def _flat(n: int, price: float = 100.0) -> list[dict]:
    """n identical-ish candles with a small fixed range and no gaps."""
    return [_c(price, price + 1, price - 1, price) for _ in range(n)]


# A clean bullish FVG: candle3.low (105) > candle1.high (100).
# Zone = [100, 105]. Middle candle is the impulse leg.
def _bullish_fvg_triplet() -> list[dict]:
    return [
        _c(99,  100, 98,  99),    # i-2: high = 100
        _c(100, 112, 99,  110),   # i-1: displacement up
        _c(111, 114, 105, 113),   # i:   low = 105  > 100  → bullish gap [100,105]
    ]


# A clean bearish FVG: candle3.high (95) < candle1.low (100).
# Zone = [95, 100].
def _bearish_fvg_triplet() -> list[dict]:
    return [
        _c(101, 102, 100, 101),   # i-2: low = 100
        _c(100, 101, 88,  90),    # i-1: displacement down
        _c(89,  95,  86,  87),    # i:   high = 95 < 100  → bearish gap [95,100]
    ]


# ── fvg_at: geometry ─────────────────────────────────────────────────────────

class TestFvgGeometry:
    def test_bullish_fvg_detected(self):
        f = smc.fvg_at(_bullish_fvg_triplet(), 2, min_range_mult=0)
        assert f is not None
        assert f["type"] == "bullish"
        assert f["bottom"] == 100      # high of candle 1
        assert f["top"] == 105         # low of candle 3
        assert f["index"] == 2

    def test_bearish_fvg_detected(self):
        f = smc.fvg_at(_bearish_fvg_triplet(), 2, min_range_mult=0)
        assert f is not None
        assert f["type"] == "bearish"
        assert f["bottom"] == 95       # high of candle 3
        assert f["top"] == 100         # low of candle 1
        assert f["index"] == 2

    def test_top_always_ge_bottom(self):
        for trip in (_bullish_fvg_triplet(), _bearish_fvg_triplet()):
            f = smc.fvg_at(trip, 2, min_range_mult=0)
            assert f["top"] >= f["bottom"]

    def test_no_gap_when_candles_overlap(self):
        # Three overlapping candles around 100 — no imbalance.
        bars = [_c(99, 101, 98, 100), _c(100, 102, 99, 101), _c(100, 103, 99, 102)]
        assert smc.fvg_at(bars, 2, min_range_mult=0) is None

    def test_index_below_2_returns_none(self):
        bars = _bullish_fvg_triplet()
        assert smc.fvg_at(bars, 0) is None
        assert smc.fvg_at(bars, 1) is None

    def test_index_out_of_range_returns_none(self):
        assert smc.fvg_at(_bullish_fvg_triplet(), 5) is None


# ── fvg_at: significance gate ────────────────────────────────────────────────

class TestFvgSignificanceGate:
    def test_tiny_gap_filtered_out(self):
        # A 0.5-wide gap embedded in wide-range candles → below the gate.
        bars = [
            _c(90, 100.0, 80, 95),    # i-2: high 100, range 20
            _c(95, 120,   90, 118),   # i-1: huge impulse, range 30
            _c(118, 125, 100.5, 122), # i:   low 100.5 > 100 → gap of only 0.5
        ]
        # avg range ≈ (20+30+25)/3 ≈ 25; gate at 0.25 ≈ 6.25 → 0.5 gap rejected.
        assert smc.fvg_at(bars, 2, min_range_mult=0.25) is None

    def test_tiny_gap_passes_when_gate_disabled(self):
        bars = [
            _c(90, 100.0, 80, 95),
            _c(95, 120,   90, 118),
            _c(118, 125, 100.5, 122),
        ]
        f = smc.fvg_at(bars, 2, min_range_mult=0)
        assert f is not None and f["type"] == "bullish"

    def test_large_gap_passes_gate(self):
        f = smc.fvg_at(_bullish_fvg_triplet(), 2, min_range_mult=0.25)
        assert f is not None   # 5-wide gap clears the default gate


# ── find_fvgs: series scan + mitigation ──────────────────────────────────────

class TestFindFvgs:
    def test_finds_single_bullish(self):
        bars = _bullish_fvg_triplet() + _flat(3, 113)
        fvgs = smc.find_fvgs(bars, min_range_mult=0)
        bull = [f for f in fvgs if f["type"] == "bullish"]
        assert len(bull) >= 1

    def test_unmitigated_when_price_stays_away(self):
        # Bullish gap [100,105]; price runs up and never returns into the zone.
        bars = _bullish_fvg_triplet() + [_c(113, 118, 110, 116), _c(116, 122, 114, 120)]
        f = [f for f in smc.find_fvgs(bars, min_range_mult=0) if f["type"] == "bullish"][0]
        assert f["mitigated"] is False
        assert f["mitigatedIndex"] is None

    def test_mitigated_when_price_returns_into_zone(self):
        # A later candle dips to 103 — inside the [100,105] gap → mitigated.
        bars = _bullish_fvg_triplet() + [_c(112, 113, 103, 108)]
        f = [f for f in smc.find_fvgs(bars, min_range_mult=0) if f["type"] == "bullish"][0]
        assert f["mitigated"] is True
        assert f["mitigatedIndex"] == 3

    def test_include_mitigated_false_drops_consumed_zones(self):
        bars = _bullish_fvg_triplet() + [_c(112, 113, 103, 108)]
        open_only = smc.find_fvgs(bars, min_range_mult=0, include_mitigated=False)
        assert all(not f["mitigated"] for f in open_only)
        bull = [f for f in open_only if f["type"] == "bullish"]
        assert bull == []   # the only bullish gap was mitigated

    def test_lookback_limits_window(self):
        # Old gap at the start, then many flat bars. lookback=3 should miss it.
        bars = _bullish_fvg_triplet() + _flat(20, 113)
        assert smc.find_fvgs(bars, min_range_mult=0, lookback=3) == []
        assert len(smc.find_fvgs(bars, min_range_mult=0)) >= 1


# ── Resilience ───────────────────────────────────────────────────────────────

class TestResilience:
    def test_empty_series(self):
        assert smc.find_fvgs([]) == []
        assert smc.fvg_at([], 2) is None

    def test_too_few_bars(self):
        assert smc.find_fvgs(_flat(2)) == []

    def test_flat_series_has_no_gaps(self):
        assert smc.find_fvgs(_flat(50), min_range_mult=0.25) == []

    def test_malformed_candle_does_not_crash(self):
        bars = [{"open": 1}, {"high": 2}, {"low": 3}]   # missing keys
        assert smc.fvg_at(bars, 2, min_range_mult=0) is None


# ── Phase 2: market structure (swings → BOS / CHoCH) ─────────────────────────

def _zz(closes: list[float]) -> list[dict]:
    """Candles whose high/low hug the close (±0.5), so swing highs/lows fall on
    local close extremes — makes the structure walk hand-verifiable."""
    return [_c(c, c + 0.5, c - 0.5, c) for c in closes]


# A zig-zag that prints: swing high @2, swing low @4, swing high @6, then a
# close above the @2 high (BOS up @6) and finally a close below the @4 low
# (CHoCH down @9 — against the now-up trend).
_STRUCT_CLOSES = [100, 101, 104, 101, 100, 103, 106, 103, 101, 99]


class TestSwingPoints:
    def test_finds_expected_swings(self):
        sh, sl = smc.swing_points(_zz(_STRUCT_CLOSES), n=2)
        assert {s["index"] for s in sh} == {2, 6}
        assert {s["index"] for s in sl} == {4}

    def test_swing_prices(self):
        sh, sl = smc.swing_points(_zz(_STRUCT_CLOSES), n=2)
        assert next(s for s in sh if s["index"] == 2)["price"] == 104.5
        assert next(s for s in sl if s["index"] == 4)["price"] == 99.5

    def test_flat_series_has_no_swings(self):
        sh, sl = smc.swing_points(_flat(20), n=2)
        assert sh == [] and sl == []

    def test_lagging_n_bars(self):
        # The last n bars can never hold a confirmed swing.
        sh, sl = smc.swing_points(_zz(_STRUCT_CLOSES), n=2)
        last_ok = len(_STRUCT_CLOSES) - 1 - 2
        assert all(s["index"] <= last_ok for s in sh + sl)


class TestMarketStructure:
    def test_detects_bos_then_choch(self):
        evs = smc.market_structure(_zz(_STRUCT_CLOSES), n=2)
        assert len(evs) == 2

        bos = evs[0]
        assert bos["type"] == "bullish" and bos["kind"] == "BOS"
        assert bos["index"] == 6 and bos["level"] == 104.5

        choch = evs[1]
        assert choch["type"] == "bearish" and choch["kind"] == "CHoCH"
        assert choch["index"] == 9 and choch["level"] == 99.5

    def test_structure_at_pinpoints_event(self):
        bars = _zz(_STRUCT_CLOSES)
        assert smc.structure_at(bars, 6)["kind"] == "BOS"
        assert smc.structure_at(bars, 9)["kind"] == "CHoCH"
        assert smc.structure_at(bars, 5) is None      # quiet bar

    def test_breaks_are_close_based_not_wick(self):
        # A wick pierces the @2 swing high (104.5) but the bar CLOSES below it →
        # no BOS. (Bar 6's high spikes to 110 but closes at 102.)
        closes = list(_STRUCT_CLOSES)
        bars = _zz(closes)
        bars[6] = _c(102, 110, 101.5, 102)            # big upper wick, close < 104.5
        evs = smc.market_structure(bars, n=2)
        assert not any(e["index"] == 6 for e in evs)

    def test_flat_series_no_events(self):
        assert smc.market_structure(_flat(40), n=2) == []

    def test_empty_and_short(self):
        assert smc.market_structure([]) == []
        assert smc.market_structure(_flat(3)) == []
        assert smc.structure_at([], 0) is None


# ── Phase 3: order blocks, liquidity, premium/discount ───────────────────────

class TestOrderBlocks:
    # swing high @2, pullback, bearish OB candle @4, then an up-impulse closing
    # above the @2 high → bullish BOS @6. OB = the @4 bearish candle [99, 102].
    # Bar 7 returns into the zone (close 101) → mitigation.
    _OB_BARS = [
        _c(100, 101, 99,  100.5),
        _c(101, 103, 100, 102),
        _c(104, 106, 103, 105),    # swing high
        _c(103, 104, 101, 102),
        _c(101, 102, 99,  100),    # ← bearish OB candle
        _c(102, 104, 101, 103.5),
        _c(106, 108, 105, 107.5),  # BOS up (break of @2 high)
        _c(102, 102.5, 100, 101),  # returns into the OB
    ]

    def test_detects_single_bullish_ob(self):
        obs = smc.order_blocks(self._OB_BARS)
        bull = [o for o in obs if o["type"] == "bullish"]
        assert len(bull) == 1
        ob = bull[0]
        assert ob["index"] == 4
        assert ob["top"] == 102 and ob["bottom"] == 99
        assert ob["createdIndex"] == 6

    def test_ob_mitigation(self):
        ob = smc.order_blocks(self._OB_BARS)[0]
        assert ob["mitigated"] is True and ob["mitigatedIndex"] == 7

    def test_at_order_block_true_inside_zone(self):
        assert smc.at_order_block(self._OB_BARS, 7, "bullish") is True

    def test_at_order_block_false_at_break_bar(self):
        # Bar 6 closed at 107.5 — above/outside the OB zone.
        assert smc.at_order_block(self._OB_BARS, 6, "bullish") is False

    def test_flat_series_no_obs(self):
        assert smc.order_blocks(_flat(40)) == []


class TestLiquiditySweep:
    _SWEEP_HIGH = [
        _c(100, 100.5, 99.5, 100),
        _c(101, 101.5, 100.5, 101),
        _c(104, 104.5, 103.5, 104),   # swing high 104.5
        _c(101, 101.5, 100.5, 101),
        _c(100, 100.5, 99.5, 100),
        _c(101, 101.5, 100.5, 101),
        _c(102, 105.0, 101.5, 102),   # wick to 105 > 104.5, closes 102 back inside
    ]
    _SWEEP_LOW = [
        _c(100, 100.5, 99.5, 100),
        _c(99,  99.5,  98.5, 99),
        _c(96,  96.5,  95.5, 96),     # swing low 95.5
        _c(99,  99.5,  98.5, 99),
        _c(100, 100.5, 99.5, 100),
        _c(99,  99.5,  98.5, 99),
        _c(98,  98.5,  95.0, 98),     # wick to 95 < 95.5, closes 98 back inside
    ]

    def test_buy_side_sweep(self):
        assert smc.liquidity_sweep_at(self._SWEEP_HIGH, 6) == "high"

    def test_sell_side_sweep(self):
        assert smc.liquidity_sweep_at(self._SWEEP_LOW, 6) == "low"

    def test_no_sweep_when_close_breaks_through(self):
        # Same setup but the bar CLOSES above the swing high → a run/break, not a sweep.
        bars = list(self._SWEEP_HIGH)
        bars[6] = _c(102, 106, 101.5, 105.5)   # close 105.5 > 104.5
        assert smc.liquidity_sweep_at(bars, 6) is None

    def test_flat_series_no_sweep(self):
        assert smc.liquidity_sweep_at(_flat(20), 19) is None


class TestEqualLevels:
    def test_equal_highs_cluster(self):
        bars = _zz([100, 101, 104, 101, 100, 101, 104, 101, 100])  # swing highs @2,@6 ≈104.5
        eq_highs, eq_lows = smc.equal_levels(bars)
        assert len(eq_highs) == 1
        assert eq_highs[0]["count"] == 2
        assert abs(eq_highs[0]["price"] - 104.5) < 1e-6
        assert eq_lows == []

    def test_no_equal_levels_when_distinct(self):
        bars = _zz([100, 101, 108, 101, 100, 101, 104, 101, 100])  # highs 108 vs 104 — far apart
        eq_highs, _ = smc.equal_levels(bars)
        assert eq_highs == []


class TestPremiumDiscount:
    # swing high @2 (105), swing low @4 (97) → equilibrium 101.
    _BARS = [
        _c(100, 101, 99,  100),
        _c(101, 102, 100, 101),
        _c(104, 105, 103, 104),   # swing high 105
        _c(101, 102, 100, 101),
        _c(98,  99,  97,  98),    # swing low 97
        _c(100, 101, 99,  100),
        _c(102, 103, 101, 102),   # close 102 (> eq 101)
    ]

    def test_dealing_range_equilibrium(self):
        dr = smc.dealing_range(self._BARS, 6)
        assert dr["high"] == 105 and dr["low"] == 97 and dr["eq"] == 101

    def test_close_above_eq_is_premium(self):
        assert smc.premium_discount_at(self._BARS, 6) == "premium"

    def test_close_below_eq_is_discount(self):
        bars = list(self._BARS)
        bars[6] = _c(100, 101, 98, 99)   # close 99 < eq 101
        assert smc.premium_discount_at(bars, 6) == "discount"

    def test_no_range_on_flat_series(self):
        assert smc.dealing_range(_flat(40), 39) is None
        assert smc.premium_discount_at(_flat(40), 39) is None
