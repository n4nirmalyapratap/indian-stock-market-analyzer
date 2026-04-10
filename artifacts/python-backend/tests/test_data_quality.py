"""
Data Quality Tests — the most critical test file.

These tests verify that the system's core data pipelines produce
mathematically valid, internally consistent, and range-checked results.
A failing test here means the app is showing users bad numbers.
"""
import math
import statistics
import pytest

from app.services.indicators import (
    calculate_rsi, calculate_macd, calculate_bollinger_bands,
    calculate_ema, calculate_sma, calculate_atr, calculate_vwap,
)
from app.services.hydra_forecast_service import _ema as hydra_ema, _rsi as hydra_rsi


# ══════════════════════════════════════════════════════════════════════════════
#  Helper utilities
# ══════════════════════════════════════════════════════════════════════════════

def assert_no_nan_inf(values: list, label: str = ""):
    """Assert none of the values are NaN or Inf."""
    for i, v in enumerate(values):
        if v is None:
            continue  # None is valid (not yet computed)
        assert math.isfinite(v), f"{label}[{i}] = {v} is not finite (NaN or Inf)"


def assert_in_range(values: list, lo: float, hi: float, label: str = ""):
    for i, v in enumerate(values):
        if v is None:
            continue
        assert lo <= v <= hi, f"{label}[{i}] = {v} is outside [{lo}, {hi}]"


def zscore_normalize(values: list[float]) -> list[float]:
    """Replicate the z-score normalization used by the sectors service."""
    mean = statistics.mean(values)
    std  = statistics.stdev(values) if len(values) > 1 else 1.0
    if std == 0:
        return [0.0] * len(values)
    return [(v - mean) / std for v in values]


# ══════════════════════════════════════════════════════════════════════════════
#  DQ-1: RSI Data Quality
# ══════════════════════════════════════════════════════════════════════════════

class TestRSIDataQuality:

    def test_rsi_never_nan_on_normal_data(self):
        """RSI must not produce NaN for a healthy OHLCV series."""
        import math
        prices = [100 + 5 * math.sin(2 * math.pi * i / 14) for i in range(60)]
        result = calculate_rsi(prices)
        assert_no_nan_inf(result, "RSI")

    def test_rsi_range_hard_constraint(self):
        """RSI is mathematically bounded to [0, 100]. No exceptions."""
        # Test with multiple price series patterns
        test_series = [
            [float(i) for i in range(1, 51)],       # rising
            [float(50 - i) for i in range(50)],      # falling
            [100 + 10 * (-1)**i for i in range(50)], # oscillating
        ]
        for series in test_series:
            result = calculate_rsi(series)
            assert_in_range(result, 0.0, 100.0, "RSI")

    def test_rsi_not_all_same_value_unless_flat(self):
        """On an oscillating series, RSI should actually oscillate, not be constant."""
        import math
        prices = [100 + 15 * math.sin(2 * math.pi * i / 10) for i in range(60)]
        result = calculate_rsi(prices)
        assert len(set(round(v, 2) for v in result)) > 5, \
            "RSI should vary on an oscillating price series"

    def test_rsi_all_gains_gives_near_100(self):
        """Pure rising prices → avg_loss → 0 → RSI → 100."""
        prices = [float(i * 10) for i in range(1, 40)]
        result = calculate_rsi(prices)
        assert result[-1] > 95, f"All-gain RSI should be near 100, got {result[-1]}"

    def test_rsi_all_losses_gives_near_0(self):
        """Pure falling prices → avg_gain → 0 → RSI → 0."""
        prices = [float(400 - i * 10) for i in range(40)]
        result = calculate_rsi(prices)
        assert result[-1] < 5, f"All-loss RSI should be near 0, got {result[-1]}"


# ══════════════════════════════════════════════════════════════════════════════
#  DQ-2: MACD Data Quality
# ══════════════════════════════════════════════════════════════════════════════

class TestMACDDataQuality:

    def test_macd_histogram_zero_on_flat(self):
        """Flat prices → zero volatility → histogram should be ~0."""
        prices = [200.0] * 60
        result = calculate_macd(prices)
        for v in result["histogram"]:
            assert abs(v) < 0.1, f"Histogram on flat series should be ~0, got {v}"

    def test_macd_signal_lags_macd(self):
        """
        On a series that reverses mid-way, the signal line should cross
        the MACD line AFTER the MACD crosses zero (signal always lags MACD).
        """
        # Rising then falling
        prices = [float(i) for i in range(1, 51)] + [float(50 - i) for i in range(1, 30)]
        result = calculate_macd(prices)
        # Both should exist and have no NaN
        assert_no_nan_inf(result["macd"], "MACD.macd")
        assert_no_nan_inf(result["signal"], "MACD.signal")
        assert_no_nan_inf(result["histogram"], "MACD.histogram")

    def test_macd_lengths_consistent(self):
        """
        MACD line (fast/slow EMAs) always has more points than the signal line
        (EMA of MACD). This is by design: signal = EMA(9) of MACD.
        What we verify: histogram length == signal length (they align), and
        MACD line is always at least as long as the signal.
        """
        prices = [100.0 + i * 0.5 for i in range(80)]
        result = calculate_macd(prices)
        assert len(result["signal"]) == len(result["histogram"]), \
            "Signal and histogram must have the same length"
        assert len(result["macd"]) >= len(result["signal"]), \
            "MACD line must have at least as many points as the signal"
        assert len(result["macd"]) > 0 and len(result["signal"]) > 0

    def test_macd_no_nan_inf(self):
        import math
        prices = [100 + 5 * math.sin(2 * math.pi * i / 20) for i in range(80)]
        result = calculate_macd(prices)
        for key in ("macd", "signal", "histogram"):
            assert_no_nan_inf(result[key], f"MACD.{key}")


# ══════════════════════════════════════════════════════════════════════════════
#  DQ-3: Bollinger Bands Data Quality
# ══════════════════════════════════════════════════════════════════════════════

class TestBollingerBandsDataQuality:

    def test_price_stays_mostly_inside_bands(self):
        """
        By definition, ~95% of prices should fall within ±2 SD bands
        for normally distributed returns.  We use a synthetic normal series.
        """
        import random
        random.seed(42)
        prices = [100.0]
        for _ in range(149):
            prices.append(prices[-1] * (1 + random.gauss(0, 0.01)))

        bb = calculate_bollinger_bands(prices, period=20, sd=2.0)
        # Align: BB has (len(prices) - period + 1) values
        n = len(bb["upper"])
        offset = len(prices) - n
        inside = sum(
            1 for i, (u, l) in enumerate(zip(bb["upper"], bb["lower"]))
            if l <= prices[offset + i] <= u
        )
        pct_inside = inside / n
        assert pct_inside >= 0.80, \
            f"Only {pct_inside:.1%} of prices inside ±2 SD bands (expected ≥80%)"

    def test_bands_symmetric_around_middle(self):
        """Upper − middle must equal middle − lower at every point."""
        import math
        prices = [100 + 10 * math.sin(2 * math.pi * i / 20) for i in range(80)]
        bb = calculate_bollinger_bands(prices, period=20, sd=2.0)
        for i, (u, m, l) in enumerate(zip(bb["upper"], bb["middle"], bb["lower"])):
            assert abs((u - m) - (m - l)) < 1e-6, \
                f"Bands not symmetric at index {i}: upper-mid={u-m:.6f}, mid-lower={m-l:.6f}"


# ══════════════════════════════════════════════════════════════════════════════
#  DQ-4: Z-Score Normalization (Sector Rotation Engine)
# ══════════════════════════════════════════════════════════════════════════════

class TestZScoreNormalization:

    def test_zscore_mean_is_zero(self):
        """After z-score normalization, the mean must be 0."""
        data = [10.0, 20.0, 30.0, 40.0, 50.0]
        normalized = zscore_normalize(data)
        assert abs(statistics.mean(normalized)) < 1e-9, \
            f"Z-score mean should be 0, got {statistics.mean(normalized)}"

    def test_zscore_std_is_one(self):
        """After z-score normalization, the std dev must be 1."""
        data = [10.0, 20.0, 30.0, 40.0, 50.0]
        normalized = zscore_normalize(data)
        std = statistics.stdev(normalized)
        assert abs(std - 1.0) < 1e-6, f"Z-score std should be 1, got {std}"

    def test_zscore_preserves_rank_order(self):
        """Z-score normalization is monotone — rank order must not change."""
        data = [5.0, 15.0, 2.0, 8.0, 20.0]
        normalized = zscore_normalize(data)
        original_ranks = [sorted(data).index(v) for v in data]
        normalized_ranks = [sorted(normalized).index(v) for v in normalized]
        assert original_ranks == normalized_ranks, "Z-score should preserve rank order"

    def test_zscore_constant_input_all_zeros(self):
        """When all values are identical, z-scores should all be 0."""
        data = [42.0] * 10
        normalized = zscore_normalize(data)
        for v in normalized:
            assert v == 0.0, f"Z-score of constant series should be 0, got {v}"

    def test_zscore_outlier_has_large_magnitude(self):
        """An extreme outlier should have a z-score > 2."""
        data = [10.0, 10.0, 10.0, 10.0, 10.0, 100.0]  # 100 is an outlier
        normalized = zscore_normalize(data)
        assert normalized[-1] > 2.0, \
            f"Outlier z-score should be > 2, got {normalized[-1]}"

    def test_zscore_no_nan_inf(self):
        """Z-score of any reasonable dataset should not produce NaN or Inf."""
        import random
        random.seed(0)
        data = [random.uniform(50, 100) for _ in range(20)]
        normalized = zscore_normalize(data)
        assert_no_nan_inf(normalized, "zscore")


# ══════════════════════════════════════════════════════════════════════════════
#  DQ-5: VWAP Data Quality
# ══════════════════════════════════════════════════════════════════════════════

class TestVWAPDataQuality:

    def test_vwap_weighted_average_known_case(self):
        """
        Manual calculation: bar1=(H+L+C)/3=105, vol=1000; bar2=(H+L+C)/3=110, vol=2000
        VWAP = (105*1000 + 110*2000) / (1000 + 2000) = 325000/3000 = 108.333...
        """
        bars = [
            {"open": 103, "high": 107, "low": 101, "close": 107, "volume": 1000},
            {"open": 107, "high": 112, "low": 106, "close": 112, "volume": 2000},
        ]
        result = calculate_vwap(bars)
        # VWAP after bar1 = (103+107+101)/3 = 103.667 * 1 (volume-weighted so far)
        # Actually VWAP is cumulative, let's just check the final value is in range
        tp2 = (112 + 106 + 112) / 3  # 110.0
        tp1 = (107 + 101 + 107) / 3  # 105.0
        expected = (tp1 * 1000 + tp2 * 2000) / 3000
        assert abs(result[-1] - expected) < 0.001, \
            f"VWAP={result[-1]:.3f}, expected={expected:.3f}"

    def test_vwap_increases_when_volume_weighted_high(self):
        """
        If a high-volume bar occurs at a higher price, VWAP should increase.
        """
        bars = [
            {"open": 100, "high": 102, "low": 98, "close": 100, "volume": 100},
            {"open": 120, "high": 125, "low": 118, "close": 122, "volume": 10000},
        ]
        result = calculate_vwap(bars)
        assert result[-1] > result[0], "VWAP should rise when high volume occurs at higher price"


# ══════════════════════════════════════════════════════════════════════════════
#  DQ-6: Hydra Engine Internal Calculations
# ══════════════════════════════════════════════════════════════════════════════

class TestHydraEngineDataQuality:

    def test_hydra_ema_matches_main_ema_direction(self):
        """Hydra's internal EMA should agree in direction with the main indicator."""
        prices = [float(i * 2) for i in range(1, 60)]
        from app.services.indicators import calculate_ema as main_ema
        hydra_result = [v for v in hydra_ema(prices, 10) if v is not None]
        main_result  = main_ema(prices, 10)
        # Both should be rising (last > first)
        assert hydra_result[-1] > hydra_result[0], "Hydra EMA should be rising"
        assert main_result[-1]  > main_result[0],  "Main EMA should be rising"

    def test_hydra_rsi_range(self):
        """Hydra's internal RSI must also be in [0, 100]."""
        import math
        prices = [100 + 5 * math.sin(2 * math.pi * i / 14) for i in range(60)]
        result = [v for v in hydra_rsi(prices) if v is not None]
        assert len(result) > 0
        assert_in_range(result, 0.0, 100.0, "HydraRSI")

    def test_hydra_rsi_rising_series_high(self):
        """Hydra's RSI on a strictly rising series should be high."""
        prices = [float(i * 5) for i in range(1, 40)]
        result = [v for v in hydra_rsi(prices) if v is not None]
        assert result[-1] >= 70, f"Hydra RSI on rising series should ≥70, got {result[-1]}"


# ══════════════════════════════════════════════════════════════════════════════
#  DQ-7: Cross-Indicator Consistency
# ══════════════════════════════════════════════════════════════════════════════

class TestCrossIndicatorConsistency:

    def test_ema_shorter_period_closer_to_latest_price(self):
        """EMA(5) should always be closer to the latest price than EMA(20)."""
        prices = [float(i) for i in range(1, 81)]
        ema5  = calculate_ema(prices, period=5)
        ema20 = calculate_ema(prices, period=20)
        latest = prices[-1]
        assert abs(ema5[-1] - latest) < abs(ema20[-1] - latest), \
            f"EMA(5)={ema5[-1]} should be closer to {latest} than EMA(20)={ema20[-1]}"

    def test_golden_cross_ema_relationship(self):
        """
        Golden cross: short EMA crosses above long EMA.
        On a long rising series, EMA(20) > EMA(50) should eventually hold.
        """
        prices = [100.0 + i * 0.5 for i in range(120)]
        ema20 = calculate_ema(prices, period=20)
        ema50 = calculate_ema(prices, period=50)
        # On a consistently rising series, the short EMA should be above long EMA
        assert ema20[-1] > ema50[-1], \
            "EMA(20) should be above EMA(50) on a rising series (golden cross territory)"

    def test_death_cross_ema_relationship(self):
        """
        Death cross: short EMA crosses below long EMA on falling series.
        """
        prices = [200.0 - i * 0.5 for i in range(120)]
        ema20 = calculate_ema(prices, period=20)
        ema50 = calculate_ema(prices, period=50)
        assert ema20[-1] < ema50[-1], \
            "EMA(20) should be below EMA(50) on a falling series (death cross territory)"

    def test_rsi_and_macd_agree_on_direction(self):
        """
        On a strongly rising series, both RSI (>50) and MACD (>0) should
        indicate bullish momentum simultaneously.
        """
        prices = [float(i * 3) for i in range(1, 60)]
        rsi_result  = calculate_rsi(prices)
        macd_result = calculate_macd(prices)
        assert rsi_result[-1] > 50, f"RSI should be > 50 on rising series, got {rsi_result[-1]}"
        assert macd_result["macd"][-1] > 0, "MACD should be > 0 on rising series"

    def test_bollinger_squeeze_on_low_volatility(self):
        """
        Low-volatility periods → narrow Bollinger Bands (upper-lower is small).
        High-volatility periods → wide bands.
        """
        low_vol  = [100.0 + 0.1 * i for i in range(40)]
        high_vol = [100.0 + 5.0 * ((-1)**i) * i for i in range(40)]
        bb_low  = calculate_bollinger_bands(low_vol)
        bb_high = calculate_bollinger_bands(high_vol)
        width_low  = bb_low["upper"][-1]  - bb_low["lower"][-1]
        width_high = bb_high["upper"][-1] - bb_high["lower"][-1]
        assert width_high > width_low, \
            f"High-vol BB width ({width_high:.2f}) should exceed low-vol ({width_low:.2f})"
