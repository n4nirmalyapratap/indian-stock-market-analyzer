"""
Unit tests for the Insights router.

Tests cover:
- Heatmap colour-bucket helper math (deterministic, no network)
- Heatmap endpoint normalises yfinance rows correctly (mocked)
- Heatmap with an unknown index returns a clean unavailable response
- Company filings adapt BSE API JSON correctly (mocked HTTP)
- MF holdings parse the AMFI NAVAll text format correctly (mocked HTTP)
- Signals compute RSI / MA-cross from a known price series
- Endpoints with no real feed return {"available": False, ...}
- /insights/indices returns the curated list with > 25 indices
"""
from __future__ import annotations
from unittest.mock import patch, MagicMock
import json

import pytest
from fastapi.testclient import TestClient


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    """Build a TestClient against a freshly-imported app with auth disabled."""
    # Disable Clerk middleware so the test client can call the protected endpoints.
    monkeypatch.setenv("DISABLE_AUTH", "1")
    # Re-import to pick up env var (best-effort; if app caches it, tests still
    # exercise the route logic via direct module imports below).
    from importlib import reload
    import app.middleware.clerk_auth as ca
    try:
        reload(ca)
    except Exception:
        pass
    from main import app
    return TestClient(app)


@pytest.fixture
def fake_yf_history():
    """Return a callable producing a small DataFrame-like for yf.Ticker.history."""
    import pandas as pd
    def _make(closes: list[float]):
        idx = pd.date_range(end="2026-04-25", periods=len(closes), freq="D")
        return pd.DataFrame({"Open": closes, "High": closes, "Low": closes,
                             "Close": closes, "Volume": [1_000_000] * len(closes)}, index=idx)
    return _make


# ── Bucket palette tests ─────────────────────────────────────────────────────

def test_bucket_negative_extreme():
    from app.routes.insights import _bucket_color
    bg, fg = _bucket_color(-5.0)
    assert bg.startswith("#")
    assert fg in ("#ffffff", "#fff", "#FFFFFF")


def test_bucket_positive_extreme():
    from app.routes.insights import _bucket_color
    bg, fg = _bucket_color(5.0)
    assert bg.startswith("#")


def test_bucket_zero():
    from app.routes.insights import _bucket_color
    bg, fg = _bucket_color(0.0)
    assert bg.startswith("#")


# ── Heatmap endpoint ────────────────────────────────────────────────────────

def test_heatmap_unknown_index_returns_unavailable(client):
    r = client.get("/api/insights/heatmap?index=NIFTY_UNICORN")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert body["items"] == []
    assert "not supported" in body["message"].lower()


def test_heatmap_normalises_yfinance(client, fake_yf_history):
    """Mock yfinance and verify each item has the required schema fields."""
    fake_hist = fake_yf_history([100, 101, 99, 102, 105])
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = fake_hist
    fake_ticker.fast_info = {"marketCap": 1_500_000_000_000}

    with patch("yfinance.Ticker", return_value=fake_ticker):
        r = client.get("/api/insights/heatmap?index=NIFTYIT&performance=1d")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["index"] == "NIFTYIT"
    assert isinstance(body["items"], list) and len(body["items"]) > 0
    item = body["items"][0]
    for f in ("symbol", "name", "price", "changePct", "marketCap", "color"):
        assert f in item, f"missing field {f}"
    # Color must be a hex string we can render directly
    assert item["color"]["bg"].startswith("#")


# ── /indices ─────────────────────────────────────────────────────────────────

def test_indices_endpoint_lists_all_curated_indices(client):
    r = client.get("/api/insights/indices")
    assert r.status_code == 200
    body = r.json()
    assert "indices" in body
    codes = {i["code"] for i in body["indices"]}
    # Must include the major Nifty + sectoral set the UI dropdown shows.
    expected = {"NIFTY50", "SENSEX", "NIFTYBANK", "NIFTYIT", "NIFTYFMCG",
                "NIFTYPHARMA", "NIFTYAUTO", "NIFTYMETAL", "NIFTYREALTY",
                "NIFTYNEXT50", "NIFTY100", "NIFTY200", "NIFTY500"}
    assert expected.issubset(codes), f"missing: {expected - codes}"
    assert len(codes) >= 25


# ── Company filings (BSE) ───────────────────────────────────────────────────

def test_company_filings_parses_bse_json():
    """Direct unit test on the BSE adapter without HTTP."""
    from app.routes.insights import _adapt_bse_announcements
    sample = {
        "Table": [
            {
                "NEWSID": "abc-123",
                "SCRIP_CD": 532540,
                "SLONGNAME": "TCS Ltd",
                "NEWSSUB": "Board Meeting Outcome",
                "HEADLINE": "Approved Q4 results",
                "CATEGORYNAME": "Result",
                "NEWS_DT": "2026-04-25T14:30:00",
                "ATTACHMENTNAME": "abc.pdf",
            }
        ]
    }
    items = _adapt_bse_announcements(sample)
    assert len(items) == 1
    it = items[0]
    assert it["symbol"] == "532540"
    assert it["company"] == "TCS Ltd"
    assert it["category"] == "Result"
    assert it["purpose"]
    assert it["date"].startswith("2026-04-25")
    assert it["documentUrl"].startswith("https://www.bseindia.com/xml-data/")


def test_company_filings_handles_empty_response():
    from app.routes.insights import _adapt_bse_announcements
    assert _adapt_bse_announcements({"Table": []}) == []
    assert _adapt_bse_announcements({}) == []
    assert _adapt_bse_announcements(None) == []


def test_ist_isoformat_tags_naive_and_is_idempotent():
    from app.routes.insights import _ist_isoformat
    # Naive IST → +05:30 appended.
    assert _ist_isoformat("2026-05-03T02:21:56") == "2026-05-03T02:21:56+05:30"
    # Space separator normalised to T.
    assert _ist_isoformat("2026-05-03 02:21:56") == "2026-05-03T02:21:56+05:30"
    # Already +05:30 → unchanged (idempotent).
    assert _ist_isoformat("2026-05-03T02:21:56+05:30") == "2026-05-03T02:21:56+05:30"
    # Already Z → unchanged.
    assert _ist_isoformat("2026-05-03T02:21:56Z") == "2026-05-03T02:21:56Z"
    # Negative offset → unchanged (regression: earlier slice bug double-tagged this).
    assert _ist_isoformat("2026-05-03T02:21:56-05:00") == "2026-05-03T02:21:56-05:00"
    # Empty in → empty out.
    assert _ist_isoformat("") == ""


def test_company_filings_synthesises_id_when_blank():
    from app.routes.insights import _adapt_bse_announcements
    items = _adapt_bse_announcements({"Table": [
        {"NEWSID": "", "SCRIP_CD": 500001, "NEWS_DT": "2026-05-03T02:00:00", "HEADLINE": "X"},
        {"NEWSID": "",  "SCRIP_CD": 500001, "NEWS_DT": "2026-05-03T02:00:00", "HEADLINE": "Y"},
    ]})
    assert len({it["id"] for it in items}) == 2  # no key collision


def test_nse_announcements_adapter():
    from app.routes.insights import _adapt_nse_announcements
    sample = [{
        "symbol": "RAYMONDLSL", "sm_name": "Raymond Lifestyle Limited",
        "desc": "Analysts/Institutional Investor Meet/Con. Call Updates",
        "sort_date": "2026-05-02 23:58:27", "seq_id": "106607593",
        "attchmntFile": "https://nsearchives.nseindia.com/x.pdf",
        "attchmntText": "Schedule of meet",
    }]
    items = _adapt_nse_announcements(sample)
    assert len(items) == 1
    it = items[0]
    assert it["exchange"] == "NSE"
    assert it["symbol"] == "RAYMONDLSL"
    assert it["company"] == "Raymond Lifestyle Limited"
    assert it["category"] == "Investor Presentation"  # inferred from desc
    assert it["date"] == "2026-05-02T23:58:27+05:30"
    assert it["documentUrl"].startswith("https://nsearchives.nseindia.com/")
    assert it["id"].startswith("nse:")


def test_nse_pit_adapter_parses_date_and_purpose():
    from app.routes.insights import _adapt_nse_pit
    sample = {"data": [{
        "symbol": "RELTD", "company": "Ravindra Energy Limited",
        "acqName": "Shantanu Lath", "date": "02-May-2026 16:46",
        "buyQuantity": "70000", "sellquantity": "0", "secAcq": "70000",
        "secType": "Equity Shares", "pid": "1197873",
    }]}
    items = _adapt_nse_pit(sample)
    assert len(items) == 1
    it = items[0]
    assert it["exchange"] == "NSE"
    assert it["category"] == "Insider Trading"
    assert "Shantanu Lath" in it["purpose"]
    assert "70000" in it["purpose"]
    assert it["date"] == "2026-05-02T16:46:00+05:30"
    assert it["id"] == "nse-pit:1197873"


def test_infer_category_maps_keywords():
    from app.routes.insights import _infer_category
    assert _infer_category("Quarterly Result for Q4") == "Result"
    assert _infer_category("Interim Dividend Declared") == "Dividend"
    assert _infer_category("AGM Notice") == "AGM/EGM"
    assert _infer_category("Acquisition of subsidiary") == "Acquisition"
    assert _infer_category("Concall transcript") == "Investor Presentation"
    assert _infer_category("random press release blah") == "Company Update"
    assert _infer_category("totally unrelated") == "Other"


def test_matches_category_handles_slash_and_blob():
    from app.routes.insights import _matches_category
    item = {"category": "AGM/EGM", "purpose": "AGM notice", "subject": ""}
    assert _matches_category(item, "AGM/EGM")
    assert _matches_category(item, "all")
    assert not _matches_category({"category": "Result", "purpose": "Q4", "subject": ""}, "Dividend")


def test_bse_total_count_extracts_rowcnt():
    from app.routes.insights import _bse_total_count
    assert _bse_total_count({"Table1": [{"ROWCNT": 1500}]}) == 1500
    assert _bse_total_count({"Table1": []}) == 0
    assert _bse_total_count({}) == 0
    assert _bse_total_count(None) == 0


# ── MF holdings (AMFI parser) ───────────────────────────────────────────────

AMFI_SAMPLE = """Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date

Open Ended Schemes(Equity Scheme - Large Cap Fund)

Aditya Birla Sun Life Mutual Fund

103174;INF209K01YV3;INF209K01YW1;Aditya Birla Sun Life Frontline Equity Fund - Growth;512.34;25-Apr-2026
103175;INF209K01YX9;INF209K01YY7;Aditya Birla Sun Life Frontline Equity Fund - Direct - Growth;520.10;25-Apr-2026

Axis Mutual Fund

120503;INF846K01EW2;-;Axis Bluechip Fund - Growth;65.43;25-Apr-2026
"""


def test_mf_amfi_parser_extracts_schemes():
    from app.routes.insights import _parse_amfi_text
    parsed = _parse_amfi_text(AMFI_SAMPLE)
    assert len(parsed) >= 3
    # Each row should carry scheme code, name, NAV, AMC, category
    s = parsed[0]
    for f in ("schemeCode", "schemeName", "nav", "date", "amc", "category"):
        assert f in s, f"missing {f}"
    assert s["amc"] == "Aditya Birla Sun Life Mutual Fund"
    assert s["category"].startswith("Open Ended")
    assert isinstance(s["nav"], float)
    # Axis row should be present and have its own AMC
    axis = [r for r in parsed if "Axis Bluechip" in r["schemeName"]]
    assert len(axis) == 1 and axis[0]["amc"] == "Axis Mutual Fund"


def test_mf_amfi_parser_handles_dashes_and_missing_nav():
    from app.routes.insights import _parse_amfi_text
    txt = AMFI_SAMPLE + "\n999999;INF000;-;Bad Scheme - N.A.;N.A.;25-Apr-2026\n"
    parsed = _parse_amfi_text(txt)
    bad = [r for r in parsed if r["schemeCode"] == "999999"]
    # N.A. NAV should either be skipped or stored as None
    if bad:
        assert bad[0]["nav"] is None


# ── Signals ─────────────────────────────────────────────────────────────────

def test_compute_signal_for_constant_series_is_neutral():
    from app.routes.insights import _compute_signal
    closes = [100.0] * 60
    sig = _compute_signal("FAKE.NS", closes)
    # On flat prices RSI is undefined / 50 by convention; we accept Neutral verdict.
    assert sig["verdict"] in ("Neutral", "Hold")
    assert "rsi" in sig and "ma20" in sig and "ma50" in sig


def test_compute_signal_for_strong_uptrend_is_bullish():
    from app.routes.insights import _compute_signal
    closes = [float(i) for i in range(1, 121)]   # strict uptrend
    sig = _compute_signal("UP.NS", closes)
    assert sig["verdict"] in ("Bullish", "Strong Buy", "Buy")
    # In an uptrend, MA20 must be above MA50.
    assert sig["ma20"] > sig["ma50"]


def test_compute_signal_for_downtrend_is_bearish():
    from app.routes.insights import _compute_signal
    closes = [float(i) for i in range(120, 0, -1)]
    sig = _compute_signal("DOWN.NS", closes)
    assert sig["verdict"] in ("Bearish", "Strong Sell", "Sell")
    assert sig["ma20"] < sig["ma50"]


# ── Unavailable-feed endpoints ──────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    # NOTE: /api/insights/fii-dii used to live here when NSE was blocked from
    # this IP — it is now backed by a committed SQLite cache (FiiDiiService)
    # and serves real flow data, so it has its own assertion below.
    "/api/insights/slbm",
    "/api/insights/mtf",
    "/api/insights/ipos",
    "/api/insights/top-deliveries",
])
def test_unavailable_endpoints_return_clean_empty_state(client, path):
    r = client.get(path)
    assert r.status_code == 200
    body = r.json()
    assert body.get("available") is False
    assert "message" in body and len(body["message"]) > 10


def test_fii_dii_serves_data_from_local_cache(client):
    """FII/DII equity now reads from the committed market_cache SQLite snapshot,
    so it should report available=True with a populated `latest` entry even
    when the live NSE endpoint is unreachable from this IP."""
    r = client.get("/api/insights/fii-dii?segment=equity&days=365")
    assert r.status_code == 200
    body = r.json()
    assert body.get("available") is True
    latest = body.get("latest") or {}
    assert "fiiNet" in latest and "diiNet" in latest


# ── Indices count ────────────────────────────────────────────────────────────

def test_indices_have_constituents():
    from app.routes.insights import INDEX_CONSTITUENTS
    for code, syms in INDEX_CONSTITUENTS.items():
        assert isinstance(syms, list) and len(syms) >= 5, f"{code} has too few constituents"


# ── Auth-bypass hardening ────────────────────────────────────────────────────

def test_disable_auth_refused_in_production(monkeypatch):
    """DISABLE_AUTH=1 must NOT bypass auth when ENV=production."""
    monkeypatch.setenv("DISABLE_AUTH", "1")
    monkeypatch.setenv("ENV", "production")
    # Pretend we are NOT in pytest (the middleware checks PYTEST env signals).
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("PYTEST_VERSION", raising=False)
    from main import app
    c = TestClient(app)
    r = c.get("/api/insights/indices")
    assert r.status_code == 401, "auth bypass leaked in production!"


# ── EOD market cache integration ─────────────────────────────────────────────

def test_heatmap_serves_from_disk_when_market_closed(client, tmp_path, monkeypatch):
    """When market is closed and PriceService can return cached EOD bars,
    the heatmap must build entirely from those bars (no live yfinance)."""
    from app.routes import insights as insights_mod
    # Force market closed
    monkeypatch.setattr(insights_mod.mcache, "is_market_open", lambda: False)

    # Stub PriceService.get_historical_data — the actual data source the
    # heatmap route calls (via _fetch_one_quote_async).
    synthetic_rows = [
        {"date": "2026-04-21", "close": 100.0, "open": 100.0, "high": 100.0, "low": 100.0, "volume": 1000},
        {"date": "2026-04-22", "close": 101.0, "open": 101.0, "high": 101.0, "low": 101.0, "volume": 1000},
        {"date": "2026-04-23", "close": 102.0, "open": 102.0, "high": 102.0, "low": 102.0, "volume": 1000},
        {"date": "2026-04-24", "close": 103.0, "open": 103.0, "high": 103.0, "low": 103.0, "volume": 1000},
        {"date": "2026-04-25", "close": 104.0, "open": 104.0, "high": 104.0, "low": 104.0, "volume": 1000},
    ]
    async def fake_get_historical_data(symbol: str, days: int):
        return synthetic_rows
    monkeypatch.setattr(insights_mod._price, "get_historical_data", fake_get_historical_data)

    # Bust the in-process cache so a fresh fetch is forced
    insights_mod._cache.clear()

    # Disable the EOD-seal step (it would try to write to PriceService too).
    async def _noop_seal(*a, **kw):
        return None
    monkeypatch.setattr(insights_mod.mcache, "seal_eod_for_today_if_overdue", _noop_seal)

    # Market-cap fast_info still uses yfinance — make it a no-op stub so the
    # quote builder gets mc=0 instead of hitting the network.
    import yfinance as yf
    fake_ticker = MagicMock()
    fake_ticker.fast_info = {"marketCap": 0}
    monkeypatch.setattr(yf, "Ticker", lambda *a, **kw: fake_ticker)

    r = client.get("/api/insights/heatmap?index=NIFTYIT&performance=1d")
    body = r.json()
    assert body["available"] is True
    assert len(body["items"]) >= 5
    # 1D performance compares the last close to the previous close, so
    # 103 -> 104 ≈ +0.97% on the synthetic series.
    sample = body["items"][0]
    assert abs(sample["changePct"] - 0.97) < 0.01
    assert sample["color"]["bg"].startswith("#")

    # 1Y performance falls back to the earliest close in the window —
    # 100 -> 104 = +4.0% — proving the offset selection works end-to-end.
    insights_mod._cache.clear()
    r2 = client.get("/api/insights/heatmap?index=NIFTYIT&performance=1y")
    body2 = r2.json()
    sample2 = body2["items"][0]
    assert abs(sample2["changePct"] - 4.0) < 0.01
