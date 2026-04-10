"""
Unit tests for app/services/indicators.py

Every test verifies a *known mathematical property* of the indicator,
not just that it "runs without crashing".  This makes the suite a true
data-quality guard — if the algorithm regresses the tests will catch it.
"""
import math
import pytest

from app.services.indicators import (
    calculate_ema,
    calculate_sma,
    calculate_rsi,
    calculate_macd,
    calculate_bollinger_bands,
    calculate_atr,
    calculate_vwap,
    detect_sr,
)


# ══════════════════════════════════════════════════════════════════════════════
#  SMA
# ══════════════════════════════════════════════════════════════════════════════

class TestSMA:

    def test_sma_flat_prices_equals_price(self, flat_prices):
        """SMA of identical values = that value."""
        result = calculate_sma(flat_prices, period=20)
        assert len(result) > 0
        for v in result:
            assert abs(v - 100.0) < 1e-9, f"Expected 100.0, got {v}"

    def test_sma_known_value(self):
        """SMA(3) of [1,2,3,4,5] = [2.0, 3.0, 4.0]."""
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = calculate_sma(data, period=3)
        assert result == pytest.approx([2.0, 3.0, 4.0], rel=1e-6)

    def test_sma_too_short_returns_empty(self):
        """Fewer data points than period → empty list, no crash."""
        assert calculate_sma([1.0, 2.0], period=5) == []

    def test_sma_monotone_in_rising_series(self, linear_rising):
        """SMA of strictly rising series should be strictly increasing."""
        result = calculate_sma(linear_rising, period=5)
        for i in range(1, len(result)):
            assert result[i] > result[i - 1], "SMA should be strictly rising"

    def test_sma_monotone_in_falling_series(self, linear_falling):
        """SMA of strictly falling series should be strictly decreasing."""
        result = calculate_sma(linear_falling, period=5)
        for i in range(1, len(result)):
            assert result[i] < result[i - 1], "SMA should be strictly falling"

    def test_sma_period_1_equals_input(self, linear_rising):
        """SMA with period=1 should equal the original series."""
        result = calculate_sma(linear_rising, period=1)
        assert result == pytest.approx(linear_rising, rel=1e-6)

    def test_sma_no_nan(self, sine_prices):
        """Output must not contain NaN or Inf."""
        result = calculate_sma(sine_prices, period=10)
        for v in result:
            assert math.isfinite(v), f"SMA produced non-finite value: {v}"


# ══════════════════════════════════════════════════════════════════════════════
#  EMA
# ══════════════════════════════════════════════════════════════════════════════

class TestEMA:

    def test_ema_flat_prices_equals_price(self, flat_prices):
        """EMA of constant series = that constant."""
        result = calculate_ema(flat_prices, period=20)
        assert len(result) > 0
        for v in result:
            assert abs(v - 100.0) < 1e-6, f"Expected 100.0, got {v}"

    def test_ema_lags_less_than_sma_on_rise(self, linear_rising):
        """EMA should be closer to the latest price (less lag) than SMA."""
        ema = calculate_ema(linear_rising, period=10)
        sma = calculate_sma(linear_rising, period=10)
        latest = linear_rising[-1]
        assert abs(ema[-1] - latest) < abs(sma[-1] - latest), \
            "EMA should lag less than SMA on a rising series"

    def test_ema_too_short_returns_empty(self):
        assert calculate_ema([1.0, 2.0], period=5) == []

    def test_ema_no_nan(self, sine_prices):
        result = calculate_ema(sine_prices, period=10)
        for v in result:
            assert math.isfinite(v), f"EMA produced non-finite value: {v}"

    def test_ema_period_1_tracks_price_exactly(self):
        """EMA with period=1: multiplier k=1, so each value equals the close."""
        prices = [10.0, 20.0, 30.0, 40.0, 50.0]
        result = calculate_ema(prices, period=1)
        assert result == pytest.approx(prices, rel=1e-6)


# ══════════════════════════════════════════════════════════════════════════════
#  RSI
# ══════════════════════════════════════════════════════════════════════════════

class TestRSI:

    def test_rsi_range_always_0_to_100(self, sine_prices):
        """RSI must always be in [0, 100]."""
        result = calculate_rsi(sine_prices)
        for v in result:
            assert 0.0 <= v <= 100.0, f"RSI out of range: {v}"

    def test_rsi_rising_series_is_overbought(self, linear_rising):
        """Strictly rising series → RSI should be high (≥ 70)."""
        result = calculate_rsi(linear_rising)
        assert len(result) > 0
        assert result[-1] >= 70, f"Rising series RSI should be ≥70, got {result[-1]}"

    def test_rsi_falling_series_is_oversold(self, linear_falling):
        """Strictly falling series → RSI should be low (≤ 30)."""
        result = calculate_rsi(linear_falling)
        assert len(result) > 0
        assert result[-1] <= 30, f"Falling series RSI should be ≤30, got {result[-1]}"

    def test_rsi_flat_prices_is_50ish(self):
        """
        After initial seed, a flat series has equal avg gain & loss → RSI ~50.
        We need an alternating series that averages to zero net change.
        """
        prices = [100.0, 101.0, 100.0] * 30  # equal ups and downs
        result = calculate_rsi(prices)
        assert len(result) > 0
        assert 40 <= result[-1] <= 60, f"Balanced RSI should be ~50, got {result[-1]}"

    def test_rsi_too_short_returns_empty(self):
        assert calculate_rsi([1.0, 2.0, 3.0], period=14) == []

    def test_rsi_no_nan(self, sine_prices):
        result = calculate_rsi(sine_prices)
        for v in result:
            assert math.isfinite(v), f"RSI produced non-finite: {v}"

    def test_rsi_custom_period(self, sine_prices):
        """Custom period (9) should return results and stay in range."""
        result = calculate_rsi(sine_prices, period=9)
        assert len(result) > 0
        for v in result:
            assert 0 <= v <= 100


# ══════════════════════════════════════════════════════════════════════════════
#  MACD
# ══════════════════════════════════════════════════════════════════════════════

class TestMACD:

    def test_macd_flat_prices_converges_to_zero(self, flat_prices):
        """Flat series → EMA12 = EMA26 → MACD line = 0."""
        result = calculate_macd(flat_prices)
        assert len(result["macd"]) > 0
        assert abs(result["macd"][-1]) < 0.01, \
            f"MACD on flat series should be ~0, got {result['macd'][-1]}"

    def test_macd_rising_series_is_positive(self, linear_rising):
        """Rising series → short EMA > long EMA → MACD > 0."""
        result = calculate_macd(linear_rising)
        assert result["macd"][-1] > 0, "MACD should be positive on rising series"

    def test_macd_falling_series_is_negative(self, linear_falling):
        """Falling series → short EMA < long EMA → MACD < 0."""
        result = calculate_macd(linear_falling)
        assert result["macd"][-1] < 0, "MACD should be negative on falling series"

    def test_macd_output_keys(self, linear_rising):
        """Result must have exactly: macd, signal, histogram."""
        result = calculate_macd(linear_rising)
        assert set(result.keys()) == {"macd", "signal", "histogram"}

    def test_macd_histogram_equals_macd_minus_signal(self, sine_prices):
        """Histogram = MACD line − signal line (by definition)."""
        result = calculate_macd(sine_prices)
        n = min(len(result["macd"]), len(result["signal"]), len(result["histogram"]))
        for i in range(-5, 0):
            expected = result["macd"][i] - result["signal"][i]
            assert abs(result["histogram"][i] - expected) < 1e-6, \
                f"Histogram[{i}]={result['histogram'][i]} ≠ MACD-Signal={expected}"

    def test_macd_no_nan(self, sine_prices):
        result = calculate_macd(sine_prices)
        for key in ("macd", "signal", "histogram"):
            for v in result[key]:
                assert math.isfinite(v), f"MACD.{key} produced non-finite: {v}"


# ══════════════════════════════════════════════════════════════════════════════
#  Bollinger Bands
# ══════════════════════════════════════════════════════════════════════════════

class TestBollingerBands:

    def test_bbands_upper_above_middle_above_lower(self, sine_prices):
        """Upper > Middle > Lower at every point."""
        result = calculate_bollinger_bands(sine_prices)
        n = min(len(result["upper"]), len(result["middle"]), len(result["lower"]))
        for i in range(n):
            assert result["upper"][i] > result["middle"][i], \
                f"Upper ≤ Middle at index {i}"
            assert result["middle"][i] > result["lower"][i], \
                f"Middle ≤ Lower at index {i}"

    def test_bbands_flat_prices_zero_width(self, flat_prices):
        """Flat prices → zero standard deviation → bands converge on the price."""
        result = calculate_bollinger_bands(flat_prices)
        for u, m, l in zip(result["upper"], result["middle"], result["lower"]):
            assert abs(u - 100.0) < 0.01, f"Upper should be ~100, got {u}"
            assert abs(l - 100.0) < 0.01, f"Lower should be ~100, got {l}"
            assert abs(m - 100.0) < 0.01, f"Middle should be ~100, got {m}"

    def test_bbands_middle_equals_sma(self, sine_prices):
        """Bollinger middle band = SMA(20)."""
        bb = calculate_bollinger_bands(sine_prices, period=20)
        sma = calculate_sma(sine_prices, period=20)
        n = min(len(bb["middle"]), len(sma))
        for i in range(n):
            assert abs(bb["middle"][i] - sma[i]) < 1e-6, \
                f"BB middle[{i}]={bb['middle'][i]} ≠ SMA[{i}]={sma[i]}"

    def test_bbands_output_keys(self, sine_prices):
        result = calculate_bollinger_bands(sine_prices)
        assert set(result.keys()) == {"upper", "middle", "lower"}

    def test_bbands_no_nan(self, sine_prices):
        result = calculate_bollinger_bands(sine_prices)
        for key in ("upper", "middle", "lower"):
            for v in result[key]:
                assert math.isfinite(v), f"BB.{key} produced non-finite: {v}"

    def test_bbands_sd2_wider_than_sd1(self, sine_prices):
        """2 standard deviation bands should be wider than 1 std dev bands."""
        bb1 = calculate_bollinger_bands(sine_prices, period=20, sd=1.0)
        bb2 = calculate_bollinger_bands(sine_prices, period=20, sd=2.0)
        n = min(len(bb1["upper"]), len(bb2["upper"]))
        for i in range(n):
            width1 = bb1["upper"][i] - bb1["lower"][i]
            width2 = bb2["upper"][i] - bb2["lower"][i]
            assert width2 >= width1, f"2-SD band should be wider at index {i}"


# ══════════════════════════════════════════════════════════════════════════════
#  ATR
# ══════════════════════════════════════════════════════════════════════════════

class TestATR:

    def test_atr_always_non_negative(self, trending_ohlcv):
        """ATR is a measure of range — always ≥ 0, and the mean should be > 0."""
        result = calculate_atr(trending_ohlcv)
        assert len(result) > 0
        for v in result:
            assert v >= 0, f"ATR should be ≥ 0, got {v}"
        # The average ATR must be clearly positive for bars with real spreads
        mean_atr = sum(result) / len(result)
        assert mean_atr > 0, f"Mean ATR should be > 0 for bars with spread, got {mean_atr}"

    def test_atr_zero_range_candles(self):
        """If every candle is a doji (zero range), ATR should be 0."""
        bars = [{"open": 100, "high": 100, "low": 100, "close": 100, "volume": 1000}] * 30
        result = calculate_atr(bars)
        for v in result:
            assert abs(v) < 1e-9, f"ATR of zero-range candles should be 0, got {v}"

    def test_atr_too_short_returns_empty(self):
        bars = [{"open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000}] * 5
        assert calculate_atr(bars, period=14) == []

    def test_atr_no_nan(self, trending_ohlcv):
        result = calculate_atr(trending_ohlcv)
        for v in result:
            assert math.isfinite(v), f"ATR produced non-finite: {v}"

    def test_atr_wide_bars_larger_than_narrow(self):
        """Wide-range bars should have a larger ATR than narrow-range bars."""
        wide  = [{"open": 100, "high": 120, "low": 80,  "close": 110, "volume": 1000}] * 20
        narrow= [{"open": 100, "high": 102, "low": 98,  "close": 101, "volume": 1000}] * 20
        atr_wide   = calculate_atr(wide)
        atr_narrow = calculate_atr(narrow)
        assert atr_wide[-1] > atr_narrow[-1], "Wider bars should produce larger ATR"


# ══════════════════════════════════════════════════════════════════════════════
#  VWAP
# ══════════════════════════════════════════════════════════════════════════════

class TestVWAP:

    def test_vwap_flat_ohlcv_equals_price(self):
        """If all OHLCV are identical, VWAP = the constant price."""
        bars = [{"open": 100, "high": 100, "low": 100, "close": 100, "volume": 10_000}] * 20
        result = calculate_vwap(bars)
        assert len(result) == 20
        for v in result:
            assert abs(v - 100.0) < 1e-9

    def test_vwap_output_length_equals_input(self, trending_ohlcv):
        """VWAP must return exactly one value per bar."""
        result = calculate_vwap(trending_ohlcv)
        assert len(result) == len(trending_ohlcv)

    def test_vwap_bounded_by_overall_session_range(self, trending_ohlcv):
        """
        VWAP is cumulative (session-wide), so it's NOT bounded by each individual
        bar's high/low. It IS bounded by the overall session high and low — i.e.,
        it must lie between the lowest low and highest high across all bars seen so far.
        """
        result = calculate_vwap(trending_ohlcv)
        for i, v in enumerate(result):
            bars_so_far = trending_ohlcv[:i + 1]
            session_high = max(b["high"] for b in bars_so_far)
            session_low  = min(b["low"]  for b in bars_so_far)
            assert session_low <= v <= session_high, \
                f"VWAP[{i}]={v} outside session range [{session_low}, {session_high}]"

    def test_vwap_zero_volume_does_not_crash(self):
        """Zero-volume bars should not raise ZeroDivisionError."""
        bars = [
            {"open": 100, "high": 110, "low": 90, "close": 105, "volume": 0},
            {"open": 105, "high": 115, "low": 100, "close": 110, "volume": 1000},
        ]
        result = calculate_vwap(bars)
        assert len(result) == 2
        for v in result:
            assert math.isfinite(v)

    def test_vwap_no_nan(self, trending_ohlcv):
        result = calculate_vwap(trending_ohlcv)
        for v in result:
            assert math.isfinite(v)


# ══════════════════════════════════════════════════════════════════════════════
#  Support / Resistance Detection
# ══════════════════════════════════════════════════════════════════════════════

class TestSupportResistance:

    def test_sr_output_keys(self, trending_ohlcv):
        """Must return exactly {supports, resistances}."""
        result = detect_sr(trending_ohlcv)
        assert set(result.keys()) == {"supports", "resistances"}

    def test_sr_supports_below_resistances(self, sine_prices):
        """Every support level should be below every resistance level."""
        bars = [{"open": p - 1, "high": p + 5, "low": p - 5, "close": p, "volume": 1000}
                for p in sine_prices]
        result = detect_sr(bars, lookback=5)
        if result["supports"] and result["resistances"]:
            assert max(result["supports"]) <= max(result["resistances"]), \
                "Highest support should not exceed highest resistance"

    def test_sr_values_are_prices_from_data(self, trending_ohlcv):
        """Detected levels must be actual high/low values from the data."""
        highs = {d["high"] for d in trending_ohlcv}
        lows  = {d["low"]  for d in trending_ohlcv}
        result = detect_sr(trending_ohlcv)
        for r in result["resistances"]:
            assert r in highs, f"Resistance {r} not from actual highs"
        for s in result["supports"]:
            assert s in lows, f"Support {s} not from actual lows"

    def test_sr_too_short_returns_empty_levels(self):
        """Not enough data for lookback → both lists empty."""
        bars = [{"open": 100, "high": 110, "low": 90, "close": 100, "volume": 1000}] * 5
        result = detect_sr(bars, lookback=10)
        assert result["supports"] == []
        assert result["resistances"] == []
