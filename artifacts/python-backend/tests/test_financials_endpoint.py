"""
TDD tests for GET /api/stocks/{symbol}/financials

Written before implementation — these tests define the contract.
Run: python -m pytest tests/test_financials_endpoint.py -v
"""
import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


# ── Fixtures / helpers ──────────────────────────────────────────────────────

def _make_annual_income():
    """Minimal income statement DataFrame (rows=metrics, cols=dates)."""
    cols = pd.to_datetime(["2025-03-31", "2024-03-31", "2023-03-31", "2022-03-31"])
    return pd.DataFrame({
        cols[0]: {"Total Revenue": 2.5e12, "Gross Profit": 1.0e12,
                  "Operating Income": 6.0e11, "Net Income": 4.5e11,
                  "EBITDA": 7.0e11, "Diluted EPS": 135.0},
        cols[1]: {"Total Revenue": 2.4e12, "Gross Profit": 9.5e11,
                  "Operating Income": 5.8e11, "Net Income": 4.3e11,
                  "EBITDA": 6.7e11, "Diluted EPS": 127.0},
        cols[2]: {"Total Revenue": 2.2e12, "Gross Profit": 8.8e11,
                  "Operating Income": 5.2e11, "Net Income": 3.9e11,
                  "EBITDA": 6.1e11, "Diluted EPS": 115.0},
        cols[3]: {"Total Revenue": 1.9e12, "Gross Profit": 7.5e11,
                  "Operating Income": 4.5e11, "Net Income": 3.4e11,
                  "EBITDA": 5.3e11, "Diluted EPS": 100.0},
    })


def _make_quarterly_income():
    cols = pd.to_datetime(["2025-12-31", "2025-09-30", "2025-06-30", "2025-03-31"])
    return pd.DataFrame({
        cols[0]: {"Total Revenue": 6.5e11, "Gross Profit": 2.6e11,
                  "Operating Income": 1.6e11, "Net Income": 1.2e11,
                  "EBITDA": 1.8e11, "Diluted EPS": 35.5},
        cols[1]: {"Total Revenue": 6.3e11, "Gross Profit": 2.5e11,
                  "Operating Income": 1.55e11, "Net Income": 1.16e11,
                  "EBITDA": 1.75e11, "Diluted EPS": 34.0},
        cols[2]: {"Total Revenue": 6.1e11, "Gross Profit": 2.4e11,
                  "Operating Income": 1.5e11, "Net Income": 1.1e11,
                  "EBITDA": 1.7e11, "Diluted EPS": 32.0},
        cols[3]: {"Total Revenue": 5.9e11, "Gross Profit": 2.3e11,
                  "Operating Income": 1.4e11, "Net Income": 1.05e11,
                  "EBITDA": 1.6e11, "Diluted EPS": 30.0},
    })


def _make_balance_sheet():
    cols = pd.to_datetime(["2025-03-31", "2024-03-31", "2023-03-31"])
    return pd.DataFrame({
        cols[0]: {"Total Assets": 1.8e12, "Total Debt": 3.3e10,
                  "Common Stock Equity": 1.0e12, "Cash And Cash Equivalents": 5.0e11},
        cols[1]: {"Total Assets": 1.7e12, "Total Debt": 3.0e10,
                  "Common Stock Equity": 9.5e11, "Cash And Cash Equivalents": 4.5e11},
        cols[2]: {"Total Assets": 1.5e12, "Total Debt": 2.7e10,
                  "Common Stock Equity": 8.5e11, "Cash And Cash Equivalents": 4.0e11},
    })


def _make_cash_flow():
    cols = pd.to_datetime(["2025-03-31", "2024-03-31", "2023-03-31"])
    return pd.DataFrame({
        cols[0]: {"Operating Cash Flow": 5.0e11, "Investing Cash Flow": -1.0e11,
                  "Financing Cash Flow": -3.0e11, "Free Cash Flow": 4.5e11,
                  "Capital Expenditure": -5.0e10},
        cols[1]: {"Operating Cash Flow": 4.7e11, "Investing Cash Flow": -9.0e10,
                  "Financing Cash Flow": -2.8e11, "Free Cash Flow": 4.2e11,
                  "Capital Expenditure": -4.5e10},
        cols[2]: {"Operating Cash Flow": 4.3e11, "Investing Cash Flow": -8.0e10,
                  "Financing Cash Flow": -2.5e11, "Free Cash Flow": 3.9e11,
                  "Capital Expenditure": -4.0e10},
    })


def _make_dividends():
    idx = pd.to_datetime([
        "2026-01-16 00:00:00+05:30",
        "2025-06-04 00:00:00+05:30",
        "2025-01-17 00:00:00+05:30",
    ])
    idx.name = "Date"
    return pd.Series([57.0, 30.0, 76.0], index=idx, name="Dividends")


def _make_info():
    return {
        "longName": "Tata Consultancy Services Limited",
        "marketCap": 9133137854464,
        "trailingPE": 18.57,
        "forwardPE": 15.23,
        "priceToBook": 8.05,
        "priceToSalesTrailing12Months": 3.36,
        "enterpriseToEbitda": 11.45,
        "trailingEps": 135.92,
        "forwardEps": 165.74,
        "returnOnEquity": 0.484,
        "returnOnAssets": 0.260,
        "debtToEquity": 10.52,
        "currentRatio": 2.23,
        "grossMargins": 0.413,
        "operatingMargins": 0.253,
        "profitMargins": 0.181,
        "dividendYield": 2.43,
        "dividendRate": 63.0,
        "earningsGrowth": 0.122,
        "revenueGrowth": 0.096,
        "bookValue": 313.73,
        "52WeekChange": -0.199,
        "currentPrice": 2525.0,
        "currency": "INR",
    }


def _mock_ticker(info=None, financials=None, quarterly_financials=None,
                 balance_sheet=None, cash_flow=None, dividends=None):
    """Build a mock yfinance.Ticker with sensible defaults."""
    t = MagicMock()
    t.info = info if info is not None else _make_info()
    t.financials = financials if financials is not None else _make_annual_income()
    t.quarterly_financials = (quarterly_financials if quarterly_financials is not None
                               else _make_quarterly_income())
    t.balance_sheet = balance_sheet if balance_sheet is not None else _make_balance_sheet()
    t.cash_flow = cash_flow if cash_flow is not None else _make_cash_flow()
    t.dividends = dividends if dividends is not None else _make_dividends()
    return t


# ── App fixture ──────────────────────────────────────────────────────────────

_TEST_SECRET = "test-secret-for-financials"


def _test_token() -> str:
    """Generate a short-lived HS256 JWT signed with the test secret."""
    import jwt as pyjwt
    import datetime
    return pyjwt.encode(
        {"sub": "test-user", "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)},
        _TEST_SECRET,
        algorithm="HS256",
    )


@pytest.fixture(scope="module")
def client():
    """
    TestClient with auth bypassed via patched SESSION_SECRET and
    a matching JWT so the middleware accepts the request.
    """
    import os
    from main import app
    token = _test_token()
    # Patch both the env var and the cached secret so the middleware validates our token
    with patch.dict(os.environ, {"SESSION_SECRET": _TEST_SECRET}), \
         patch("app.routes.auth._secret", return_value=_TEST_SECRET):
        yield TestClient(app, headers={"Authorization": f"Bearer {token}"})


# ── Tests: response structure ─────────────────────────────────────────────────

class TestFinancialsEndpointStructure:
    """The /financials endpoint must return the right top-level keys."""

    def test_returns_200_for_valid_symbol(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            resp = client.get("/api/stocks/TCS/financials")
        assert resp.status_code == 200

    def test_top_level_keys_present(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            data = client.get("/api/stocks/TCS/financials").json()
        required = {"symbol", "companyName", "overview", "incomeStatement",
                    "balanceSheet", "cashFlow", "dividends", "eps"}
        assert required.issubset(set(data.keys())), f"Missing keys: {required - set(data.keys())}"

    def test_symbol_is_uppercased_in_response(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            data = client.get("/api/stocks/tcs/financials").json()
        assert data["symbol"] == "TCS"

    def test_company_name_is_string(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            data = client.get("/api/stocks/TCS/financials").json()
        assert isinstance(data["companyName"], str)
        assert len(data["companyName"]) > 0

    def test_returns_404_for_empty_info(self, client):
        bad = _mock_ticker(info={})
        bad.financials = pd.DataFrame()
        bad.quarterly_financials = pd.DataFrame()
        bad.balance_sheet = pd.DataFrame()
        bad.cash_flow = pd.DataFrame()
        bad.dividends = pd.Series([], dtype=float)
        with patch("yfinance.Ticker", return_value=bad):
            resp = client.get("/api/stocks/INVALID999/financials")
        assert resp.status_code == 404


class TestFinancialsOverview:
    """The overview object must contain all required valuation metrics."""

    REQUIRED_FLOAT_FIELDS = [
        "trailingPE", "forwardPE", "priceToBook", "priceToSales",
        "evToEbitda", "trailingEps", "forwardEps", "roe", "roa",
        "grossMargin", "operatingMargin", "netMargin",
        "dividendYield", "dividendRate",
    ]

    def test_overview_present(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            data = client.get("/api/stocks/TCS/financials").json()
        assert "overview" in data
        assert isinstance(data["overview"], dict)

    def test_overview_has_market_cap(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            ov = client.get("/api/stocks/TCS/financials").json()["overview"]
        assert "marketCap" in ov
        assert isinstance(ov["marketCap"], (int, float))
        assert ov["marketCap"] > 0

    def test_overview_trailing_pe_is_float(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            ov = client.get("/api/stocks/TCS/financials").json()["overview"]
        assert isinstance(ov["trailingPE"], float)
        assert ov["trailingPE"] > 0

    def test_overview_roe_between_0_and_100_pct(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            ov = client.get("/api/stocks/TCS/financials").json()["overview"]
        assert "roe" in ov
        assert 0 < ov["roe"] < 200  # percentage like 48.4

    def test_overview_margins_are_percentages(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            ov = client.get("/api/stocks/TCS/financials").json()["overview"]
        for field in ("grossMargin", "operatingMargin", "netMargin"):
            assert field in ov, f"Missing {field}"
            v = ov[field]
            if v is not None:
                assert -100 < v < 100, f"{field}={v} out of pct range"

    def test_overview_none_fields_are_not_nan(self, client):
        """NaN must be serialised as null/None, not the string 'NaN'."""
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            raw = client.get("/api/stocks/TCS/financials").text
        assert "NaN" not in raw, "Response must not contain literal 'NaN'"


class TestIncomeStatement:
    """incomeStatement must have 'annual' and 'quarterly' arrays."""

    def test_income_statement_has_annual_and_quarterly(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            data = client.get("/api/stocks/TCS/financials").json()
        assert "annual" in data["incomeStatement"]
        assert "quarterly" in data["incomeStatement"]

    def test_annual_income_is_list(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            annual = client.get("/api/stocks/TCS/financials").json()["incomeStatement"]["annual"]
        assert isinstance(annual, list)
        assert len(annual) >= 1

    def test_annual_income_sorted_oldest_first(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            annual = client.get("/api/stocks/TCS/financials").json()["incomeStatement"]["annual"]
        dates = [r["date"] for r in annual]
        assert dates == sorted(dates)

    def test_annual_income_has_required_fields(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            row = client.get("/api/stocks/TCS/financials").json()["incomeStatement"]["annual"][0]
        for field in ("date", "revenue", "grossProfit", "operatingIncome", "netIncome"):
            assert field in row, f"Missing '{field}' in income statement row"

    def test_quarterly_income_has_required_fields(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            row = client.get("/api/stocks/TCS/financials").json()["incomeStatement"]["quarterly"][0]
        for field in ("date", "revenue", "grossProfit", "netIncome"):
            assert field in row

    def test_revenue_is_positive_number(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            row = client.get("/api/stocks/TCS/financials").json()["incomeStatement"]["annual"][0]
        assert row["revenue"] is not None
        assert row["revenue"] > 0

    def test_income_values_in_crores(self, client):
        """Revenue should be reported in ₹ Crores (divided by 1e7)."""
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            row = client.get("/api/stocks/TCS/financials").json()["incomeStatement"]["annual"][-1]
        # TCS FY2025 revenue ~₹2.5 lakh crore → in crores ≈ 250000
        assert 1000 < row["revenue"] < 1_000_000, f"Revenue {row['revenue']} not in crore range"


class TestBalanceSheet:
    """balanceSheet.annual must be a non-empty list with key financial fields."""

    def test_balance_sheet_has_annual(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            data = client.get("/api/stocks/TCS/financials").json()
        assert "annual" in data["balanceSheet"]
        assert isinstance(data["balanceSheet"]["annual"], list)
        assert len(data["balanceSheet"]["annual"]) >= 1

    def test_balance_sheet_row_fields(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            row = client.get("/api/stocks/TCS/financials").json()["balanceSheet"]["annual"][0]
        for field in ("date", "totalAssets", "totalDebt", "equity"):
            assert field in row, f"Missing '{field}' in balance sheet row"

    def test_balance_sheet_sorted_oldest_first(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            rows = client.get("/api/stocks/TCS/financials").json()["balanceSheet"]["annual"]
        dates = [r["date"] for r in rows]
        assert dates == sorted(dates)


class TestCashFlow:
    """cashFlow.annual must have operating, investing, financing, free CF."""

    def test_cash_flow_has_annual(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            data = client.get("/api/stocks/TCS/financials").json()
        assert "annual" in data["cashFlow"]
        assert len(data["cashFlow"]["annual"]) >= 1

    def test_cash_flow_row_fields(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            row = client.get("/api/stocks/TCS/financials").json()["cashFlow"]["annual"][0]
        for field in ("date", "operatingCF", "investingCF", "financingCF", "freeCF"):
            assert field in row, f"Missing '{field}' in cash flow row"


class TestDividends:
    """dividends must be a list sorted by date (oldest first)."""

    def test_dividends_is_list(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            divs = client.get("/api/stocks/TCS/financials").json()["dividends"]
        assert isinstance(divs, list)

    def test_dividend_entry_has_date_and_amount(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            divs = client.get("/api/stocks/TCS/financials").json()["dividends"]
        assert len(divs) >= 1
        for d in divs:
            assert "date" in d
            assert "amount" in d
            assert d["amount"] > 0

    def test_dividends_sorted_oldest_first(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            divs = client.get("/api/stocks/TCS/financials").json()["dividends"]
        dates = [d["date"] for d in divs]
        assert dates == sorted(dates)

    def test_dividends_empty_when_no_data(self, client):
        t = _mock_ticker()
        t.dividends = pd.Series([], dtype=float)
        with patch("yfinance.Ticker", return_value=t):
            divs = client.get("/api/stocks/TCS/financials").json()["dividends"]
        assert divs == []


class TestEPS:
    """eps must have annual and quarterly arrays with date + eps fields."""

    def test_eps_has_annual_and_quarterly(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            eps = client.get("/api/stocks/TCS/financials").json()["eps"]
        assert "annual" in eps
        assert "quarterly" in eps

    def test_eps_annual_has_required_fields(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            rows = client.get("/api/stocks/TCS/financials").json()["eps"]["annual"]
        assert len(rows) >= 1
        for row in rows:
            assert "date" in row
            assert "eps" in row
            assert row["eps"] is not None

    def test_eps_quarterly_has_required_fields(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            rows = client.get("/api/stocks/TCS/financials").json()["eps"]["quarterly"]
        assert len(rows) >= 1

    def test_eps_sorted_oldest_first(self, client):
        with patch("yfinance.Ticker", return_value=_mock_ticker()):
            rows = client.get("/api/stocks/TCS/financials").json()["eps"]["annual"]
        dates = [r["date"] for r in rows]
        assert dates == sorted(dates)
