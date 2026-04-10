"""
TDD tests for GET /api/stocks/{symbol}/technical-summary

Red → Green → Refactor cycle.
All tests written before the endpoint is implemented.
"""

import os
import math
import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock

from starlette.testclient import TestClient

_TEST_SECRET = "tech-summary-test-secret-32chars!"

# ── Mock data helpers ─────────────────────────────────────────────────────────

def _make_ohlcv(n: int = 250) -> pd.DataFrame:
    """Generate synthetic OHLCV data with a clear uptrend so signals are deterministic."""
    np.random.seed(42)
    close = 2500.0
    closes, highs, lows, opens, volumes = [], [], [], [], []
    for i in range(n):
        change = np.random.normal(0.3, 2.0)  # slight uptrend
        close = max(10.0, close + change)
        daily_range = abs(np.random.normal(0, 5))
        high  = close + daily_range
        low   = close - daily_range
        open_ = close - np.random.normal(0, 2)
        closes.append(close)
        highs.append(high)
        lows.append(low)
        opens.append(open_)
        volumes.append(int(np.random.uniform(1e5, 1e7)))

    idx = pd.date_range(end="2026-04-10", periods=n, freq="B")
    return pd.DataFrame({"Open": opens, "High": highs, "Low": lows,
                         "Close": closes, "Volume": volumes}, index=idx)


def _mock_ticker(ohlcv: pd.DataFrame | None = None):
    df = ohlcv if ohlcv is not None else _make_ohlcv()
    t = MagicMock()
    t.history.return_value = df
    t.info = {
        "shortName": "Test Corp", "longName": "Test Corporation Ltd",
        "currency": "INR",
    }
    return t


def _test_token() -> str:
    import jwt as pyjwt
    import datetime
    return pyjwt.encode(
        {"sub": "test-user",
         "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)},
        _TEST_SECRET,
        algorithm="HS256",
    )


@pytest.fixture(scope="module")
def client():
    from main import app
    token = _test_token()
    with patch.dict(os.environ, {"SESSION_SECRET": _TEST_SECRET}), \
         patch("app.routes.auth._secret", return_value=_TEST_SECRET):
        yield TestClient(app, headers={"Authorization": f"Bearer {token}"})


# ── Helper: fetch the summary response ───────────────────────────────────────

def _get(client, symbol: str = "TCS", interval: str = "1d"):
    with patch("yfinance.Ticker", return_value=_mock_ticker()):
        return client.get(f"/api/stocks/{symbol}/technical-summary?interval={interval}")


# ══════════════════════════════════════════════════════════════════════════════
# Section 1 — Response structure
# ══════════════════════════════════════════════════════════════════════════════

class TestTechnicalSummaryStructure:

    def test_returns_200(self, client):
        assert _get(client).status_code == 200

    def test_top_level_keys(self, client):
        data = _get(client).json()
        required = {"symbol", "interval", "summary", "oscillators", "movingAverages", "pivots"}
        assert required.issubset(data.keys()), f"Missing: {required - set(data.keys())}"

    def test_summary_structure(self, client):
        s = _get(client).json()["summary"]
        assert {"signal", "buy", "sell", "neutral"}.issubset(s.keys())
        assert s["signal"] in {"BUY", "STRONG_BUY", "SELL", "STRONG_SELL", "NEUTRAL"}
        assert isinstance(s["buy"],     int)
        assert isinstance(s["sell"],    int)
        assert isinstance(s["neutral"], int)

    def test_summary_counts_add_up(self, client):
        data = _get(client).json()
        s  = data["summary"]
        osc = data["oscillators"]
        ma  = data["movingAverages"]
        # Summary totals should equal oscillators + moving averages totals
        assert s["buy"]     == osc["buy"]     + ma["buy"]
        assert s["sell"]    == osc["sell"]    + ma["sell"]
        assert s["neutral"] == osc["neutral"] + ma["neutral"]

    def test_oscillators_structure(self, client):
        osc = _get(client).json()["oscillators"]
        assert {"signal", "buy", "sell", "neutral", "indicators"}.issubset(osc.keys())
        assert osc["signal"] in {"BUY", "STRONG_BUY", "SELL", "STRONG_SELL", "NEUTRAL"}
        assert isinstance(osc["indicators"], list)

    def test_moving_averages_structure(self, client):
        ma = _get(client).json()["movingAverages"]
        assert {"signal", "buy", "sell", "neutral", "indicators"}.issubset(ma.keys())
        assert isinstance(ma["indicators"], list)

    def test_pivots_structure(self, client):
        p = _get(client).json()["pivots"]
        assert {"classic", "fibonacci", "camarilla", "woodie", "dm"}.issubset(p.keys())

    def test_pivot_type_structure(self, client):
        p = _get(client).json()["pivots"]
        for ptype in ("classic", "fibonacci", "camarilla", "woodie"):
            levels = p[ptype]
            assert {"r3", "r2", "r1", "p", "s1", "s2", "s3"}.issubset(levels.keys()), \
                f"{ptype} missing levels"

    def test_dm_pivot_structure(self, client):
        dm = _get(client).json()["pivots"]["dm"]
        assert {"r1", "p", "s1"}.issubset(dm.keys())

    def test_indicator_row_structure(self, client):
        osc = _get(client).json()["oscillators"]
        for row in osc["indicators"]:
            assert "name"   in row, f"No 'name' in {row}"
            assert "value"  in row, f"No 'value' in {row}"
            assert "action" in row, f"No 'action' in {row}"
            assert row["action"] in {"BUY", "SELL", "NEUTRAL"}, f"Bad action: {row['action']}"

    def test_ma_indicator_row_structure(self, client):
        ma = _get(client).json()["movingAverages"]
        for row in ma["indicators"]:
            assert "name"   in row
            assert "value"  in row
            assert "action" in row
            assert row["action"] in {"BUY", "SELL", "NEUTRAL"}

    def test_no_nan_in_response(self, client):
        import json
        raw = _get(client).text
        assert "NaN" not in raw, "Raw NaN found in JSON response"
        assert "Infinity" not in raw

    def test_symbol_and_interval_echoed(self, client):
        data = _get(client, symbol="RELIANCE", interval="1d").json()
        assert data["symbol"]   == "RELIANCE"
        assert data["interval"] == "1d"


# ══════════════════════════════════════════════════════════════════════════════
# Section 2 — Oscillator indicators
# ══════════════════════════════════════════════════════════════════════════════

EXPECTED_OSCILLATORS = [
    "RSI (14)",
    "Stochastic %K (14, 3, 3)",
    "CCI (20)",
    "ADX (14)",
    "Awesome Oscillator",
    "Momentum (10)",
    "MACD Level (12, 26)",
    "Stochastic RSI Fast (3, 3, 14, 14)",
    "Williams %R (14)",
    "Bull Bear Power",
    "Ultimate Oscillator (7, 14, 28)",
]

class TestOscillatorIndicators:

    def test_all_oscillators_present(self, client):
        names = [i["name"] for i in _get(client).json()["oscillators"]["indicators"]]
        for exp in EXPECTED_OSCILLATORS:
            assert exp in names, f"Missing oscillator: {exp}"

    def test_exactly_eleven_oscillators(self, client):
        indicators = _get(client).json()["oscillators"]["indicators"]
        assert len(indicators) == 11, f"Expected 11, got {len(indicators)}"

    def test_oscillator_values_are_numbers_or_null(self, client):
        for row in _get(client).json()["oscillators"]["indicators"]:
            assert row["value"] is None or isinstance(row["value"], (int, float)), \
                f"Bad type for {row['name']}: {type(row['value'])}"

    def test_oscillator_buy_sell_neutral_counts_consistent(self, client):
        osc = _get(client).json()["oscillators"]
        actions = [i["action"] for i in osc["indicators"]]
        assert osc["buy"]     == actions.count("BUY")
        assert osc["sell"]    == actions.count("SELL")
        assert osc["neutral"] == actions.count("NEUTRAL")


# ══════════════════════════════════════════════════════════════════════════════
# Section 3 — Moving Average indicators
# ══════════════════════════════════════════════════════════════════════════════

EXPECTED_MAS = [
    "EMA (10)", "SMA (10)",
    "EMA (20)", "SMA (20)",
    "EMA (30)", "SMA (30)",
    "EMA (50)", "SMA (50)",
    "EMA (100)", "SMA (100)",
    "EMA (200)", "SMA (200)",
    "Ichimoku Base Line (9, 26, 52, 26)",
    "VWMA (20)",
    "HMA (9)",
]

class TestMovingAverageIndicators:

    def test_all_mas_present(self, client):
        names = [i["name"] for i in _get(client).json()["movingAverages"]["indicators"]]
        for exp in EXPECTED_MAS:
            assert exp in names, f"Missing MA: {exp}"

    def test_exactly_fifteen_mas(self, client):
        indicators = _get(client).json()["movingAverages"]["indicators"]
        assert len(indicators) == 15, f"Expected 15, got {len(indicators)}"

    def test_ma_values_are_numbers_or_null(self, client):
        for row in _get(client).json()["movingAverages"]["indicators"]:
            assert row["value"] is None or isinstance(row["value"], (int, float)), \
                f"Bad type for {row['name']}: {type(row['value'])}"

    def test_ma_buy_sell_neutral_counts_consistent(self, client):
        ma = _get(client).json()["movingAverages"]
        actions = [i["action"] for i in ma["indicators"]]
        assert ma["buy"]     == actions.count("BUY")
        assert ma["sell"]    == actions.count("SELL")
        assert ma["neutral"] == actions.count("NEUTRAL")


# ══════════════════════════════════════════════════════════════════════════════
# Section 4 — Signal logic
# ══════════════════════════════════════════════════════════════════════════════

class TestSignalLogic:

    def _ohlcv_with_rsi(self, rsi_target: float, n: int = 250) -> pd.DataFrame:
        """Generate data where last RSI is approximately rsi_target."""
        np.random.seed(0)
        if rsi_target > 65:
            # Strong uptrend → high RSI
            closes = [2500 + i * 3 + np.random.normal(0, 0.5) for i in range(n)]
        elif rsi_target < 35:
            # Strong downtrend → low RSI
            closes = [2500 - i * 3 + np.random.normal(0, 0.5) for i in range(n)]
        else:
            # Flat → neutral RSI
            closes = [2500 + np.random.normal(0, 2) for _ in range(n)]

        highs  = [c + abs(np.random.normal(0, 5)) for c in closes]
        lows   = [c - abs(np.random.normal(0, 5)) for c in closes]
        opens  = [c - np.random.normal(0, 2) for c in closes]
        vols   = [int(1e6)] * n
        idx    = pd.date_range(end="2026-04-10", periods=n, freq="B")
        return pd.DataFrame({"Open": opens, "High": highs, "Low": lows,
                              "Close": closes, "Volume": vols}, index=idx)

    def test_rsi_sell_when_overbought(self, client):
        df = self._ohlcv_with_rsi(80)
        with patch("yfinance.Ticker", return_value=_mock_ticker(df)):
            data = client.get("/api/stocks/TEST/technical-summary").json()
        rsi_row = next(i for i in data["oscillators"]["indicators"] if i["name"] == "RSI (14)")
        assert rsi_row["action"] == "SELL", f"RSI value={rsi_row['value']}, expected SELL for overbought"

    def test_rsi_buy_when_oversold(self, client):
        df = self._ohlcv_with_rsi(20)
        with patch("yfinance.Ticker", return_value=_mock_ticker(df)):
            data = client.get("/api/stocks/TEST/technical-summary").json()
        rsi_row = next(i for i in data["oscillators"]["indicators"] if i["name"] == "RSI (14)")
        assert rsi_row["action"] == "BUY", f"RSI value={rsi_row['value']}, expected BUY for oversold"

    def test_ma_buy_when_price_above(self, client):
        """Price well above all MAs → all MA actions should be BUY."""
        n = 250
        # Rising trend: price is always above any reasonable MA
        closes = [1000 + i * 5 for i in range(n)]  # strong linear uptrend
        highs  = [c + 2 for c in closes]
        lows   = [c - 2 for c in closes]
        opens  = [c - 1 for c in closes]
        vols   = [int(1e6)] * n
        idx    = pd.date_range(end="2026-04-10", periods=n, freq="B")
        df = pd.DataFrame({"Open": opens, "High": highs, "Low": lows,
                           "Close": closes, "Volume": vols}, index=idx)
        with patch("yfinance.Ticker", return_value=_mock_ticker(df)):
            data = client.get("/api/stocks/TEST/technical-summary").json()
        ma_data = data["movingAverages"]
        # At least EMA(10)/SMA(10) should be BUY (short MAs are close, definitely below close)
        ema10 = next(i for i in ma_data["indicators"] if i["name"] == "EMA (10)")
        assert ema10["action"] == "BUY", f"EMA10={ema10['value']}, price={closes[-1]}"

    def test_ma_sell_when_price_below(self, client):
        """Price well below all MAs → all MA actions should be SELL."""
        n = 250
        # Falling trend: price is always below any reasonable MA
        closes = [2500 - i * 5 for i in range(n)]
        highs  = [c + 2 for c in closes]
        lows   = [c - 2 for c in closes]
        opens  = [c + 1 for c in closes]
        vols   = [int(1e6)] * n
        idx    = pd.date_range(end="2026-04-10", periods=n, freq="B")
        df = pd.DataFrame({"Open": opens, "High": highs, "Low": lows,
                           "Close": closes, "Volume": vols}, index=idx)
        with patch("yfinance.Ticker", return_value=_mock_ticker(df)):
            data = client.get("/api/stocks/TEST/technical-summary").json()
        ma_data = data["movingAverages"]
        ema10 = next(i for i in ma_data["indicators"] if i["name"] == "EMA (10)")
        assert ema10["action"] == "SELL", f"EMA10={ema10['value']}, price={closes[-1]}"

    def test_pivot_classic_formula(self, client):
        """Verify Classic pivot = (H+L+C)/3 of yesterday's candle."""
        n = 250
        np.random.seed(99)
        closes = [2500.0 + i * 0.1 for i in range(n)]
        highs  = [c + 10 for c in closes]
        lows   = [c - 10 for c in closes]
        opens  = [c - 1  for c in closes]
        vols   = [int(1e6)] * n
        idx    = pd.date_range(end="2026-04-10", periods=n, freq="B")
        df = pd.DataFrame({"Open": opens, "High": highs, "Low": lows,
                           "Close": closes, "Volume": vols}, index=idx)

        # Use last completed period (second-to-last row)
        prev_h = highs[-2]
        prev_l = lows[-2]
        prev_c = closes[-2]
        expected_p = (prev_h + prev_l + prev_c) / 3

        with patch("yfinance.Ticker", return_value=_mock_ticker(df)):
            data = client.get("/api/stocks/TEST/technical-summary").json()
        classic = data["pivots"]["classic"]
        assert abs(classic["p"] - expected_p) < 0.01, \
            f"Classic P={classic['p']:.4f}, expected {expected_p:.4f}"

    def test_pivot_fibonacci_r1_formula(self, client):
        """R1 for Fibonacci = P + 0.382*(H-L)."""
        n = 250
        closes = [2500.0] * n
        highs  = [2600.0] * n
        lows   = [2400.0] * n
        opens  = [2500.0] * n
        vols   = [int(1e6)] * n
        idx    = pd.date_range(end="2026-04-10", periods=n, freq="B")
        df = pd.DataFrame({"Open": opens, "High": highs, "Low": lows,
                           "Close": closes, "Volume": vols}, index=idx)

        prev_h, prev_l, prev_c = 2600.0, 2400.0, 2500.0
        p = (prev_h + prev_l + prev_c) / 3
        expected_r1 = p + 0.382 * (prev_h - prev_l)

        with patch("yfinance.Ticker", return_value=_mock_ticker(df)):
            data = client.get("/api/stocks/TEST/technical-summary").json()
        fib_r1 = data["pivots"]["fibonacci"]["r1"]
        assert abs(fib_r1 - expected_r1) < 0.01, \
            f"Fibonacci R1={fib_r1:.4f}, expected {expected_r1:.4f}"

    def test_summary_signal_strong_buy(self, client):
        """Strong uptrend → Summary signal should be BUY or STRONG_BUY."""
        n = 250
        closes = [1000 + i * 5 for i in range(n)]
        highs  = [c + 2 for c in closes]
        lows   = [c - 2 for c in closes]
        opens  = [c - 1 for c in closes]
        vols   = [int(1e6)] * n
        idx    = pd.date_range(end="2026-04-10", periods=n, freq="B")
        df = pd.DataFrame({"Open": opens, "High": highs, "Low": lows,
                           "Close": closes, "Volume": vols}, index=idx)
        with patch("yfinance.Ticker", return_value=_mock_ticker(df)):
            data = client.get("/api/stocks/TEST/technical-summary").json()
        assert data["summary"]["signal"] in {"BUY", "STRONG_BUY"}, \
            f"Expected BUY/STRONG_BUY, got {data['summary']['signal']}"
