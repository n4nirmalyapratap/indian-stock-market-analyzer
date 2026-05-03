"""
Unit tests for MacroService.

Covers:
- FRED CSV parser (well-formed, malformed, empty, non-numeric values)
- _yoy_change math
- _last_two helper
- _series_yoy generates the correct number of points
- Strip aggregation degrades gracefully when FRED + Yahoo both return nothing
- Strip aggregation produces 6 tiles regardless of source availability
- Dashboard payload shape is correct (always returns required keys)
- Dashboard fetches WPI proxy and includes it in the response
- Dashboard yield curve snapshot includes both 3M and 10Y tenors
- Dashboard sources honestly report which probes succeeded/failed
- Cache TTL — second call hits the cache without re-invoking the fetcher
- Deterministic commentary fallback fires when LLM is unavailable
- Route smoke tests via TestClient
- _probe_url succeeds and fails cleanly

The codebase doesn't use pytest-asyncio; tests follow the existing
test_agents.py pattern of wrapping async helpers with asyncio.run().
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DISABLE_AUTH", "1")
    from importlib import reload
    import app.middleware.clerk_auth as ca
    try:
        reload(ca)
    except Exception:
        pass
    from main import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_macro_cache():
    """Clear the in-process macro cache between tests."""
    from app.services import macro_service
    macro_service._cache.clear()
    yield
    macro_service._cache.clear()


def _run(coro):
    """Run an async coroutine to completion in the test thread."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ── FRED CSV parsing ────────────────────────────────────────────────────────

def _fake_api_client(payload=None, status=200, text=""):
    """Helper that builds a fake httpx.AsyncClient returning a JSON response."""
    class FakeResp:
        status_code = status
        def __init__(self): self._payload = payload
        def json(self): return self._payload
        @property
        def text(self): return text or ""
    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **kw): return FakeResp()
    return FakeClient


def test_fred_api_parses_well_formed_response(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    from app.services.macro_service import _fetch_fred_series

    payload = {"observations": [
        {"date": "2025-01-01", "value": "6.50"},
        {"date": "2025-02-01", "value": "6.50"},
        {"date": "2025-03-01", "value": "6.25"},
    ]}
    Fake = _fake_api_client(payload=payload)
    with patch("app.services.macro_service.httpx.AsyncClient", lambda *a, **kw: Fake()):
        rows = _run(_fetch_fred_series("IRSTCB01INM156N"))

    assert len(rows) == 3
    assert rows[0] == {"date": "2025-01-01", "value": 6.5}
    assert rows[-1]["value"] == 6.25


def test_fred_api_skips_dot_and_na_values(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    from app.services.macro_service import _fetch_fred_series

    payload = {"observations": [
        {"date": "2025-01-01", "value": "."},
        {"date": "2025-02-01", "value": "NA"},
        {"date": "2025-03-01", "value": "4.5"},
        {"date": "2025-04-01", "value": "abc"},
    ]}
    Fake = _fake_api_client(payload=payload)
    with patch("app.services.macro_service.httpx.AsyncClient", lambda *a, **kw: Fake()):
        rows = _run(_fetch_fred_series("X"))

    assert len(rows) == 1
    assert rows[0]["value"] == 4.5


def test_fred_api_returns_empty_on_http_error(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    from app.services.macro_service import _fetch_fred_series

    Fake = _fake_api_client(payload=None, status=400, text="bad request")
    with patch("app.services.macro_service.httpx.AsyncClient", lambda *a, **kw: Fake()):
        rows = _run(_fetch_fred_series("X"))

    assert rows == []


def test_fred_api_returns_empty_on_network_exception(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    from app.services.macro_service import _fetch_fred_series

    class BoomClient:
        async def __aenter__(self): raise RuntimeError("DNS fail")
        async def __aexit__(self, *a): return False

    with patch("app.services.macro_service.httpx.AsyncClient", lambda *a, **kw: BoomClient()):
        rows = _run(_fetch_fred_series("X"))

    assert rows == []


def test_fred_api_returns_empty_on_malformed_payload(monkeypatch):
    """A 200 response with a totally unexpected JSON shape must not raise."""
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    from app.services.macro_service import _fetch_fred_series

    for bad in (None, [], {"observations": "oops"},
                {"observations": [None, 7, "x"]},
                {"observations": [{"date": None, "value": None}]},
                {"observations": [{"date": "2025-01-01", "value": {"nested": True}}]}):
        Fake = _fake_api_client(payload=bad)
        with patch("app.services.macro_service.httpx.AsyncClient", lambda *a, **kw: Fake()):
            rows = _run(_fetch_fred_series("X"))
        assert rows == [], f"expected [] for payload {bad!r}, got {rows!r}"


def test_fred_falls_back_to_csv_when_api_key_missing(monkeypatch):
    """Without FRED_API_KEY set, the fetcher must use the legacy CSV endpoint."""
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    from app.services.macro_service import _fetch_fred_series

    csv_body = "DATE,X\n2025-01-01,6.50\n2025-02-01,6.25\n"

    class FakeResp:
        status_code = 200
        text = csv_body
    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **kw): return FakeResp()

    with patch("app.services.macro_service.httpx.AsyncClient", lambda *a, **kw: FakeClient()):
        rows = _run(_fetch_fred_series("X"))

    assert len(rows) == 2
    assert rows[-1]["value"] == 6.25


# ── Probe helper ────────────────────────────────────────────────────────────

def test_probe_url_reports_ok_on_success():
    from app.services.macro_service import _probe_url

    class FakeResp:
        status_code = 200

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **kw): return FakeResp()

    with patch("app.services.macro_service.httpx.AsyncClient", lambda *a, **kw: FakeClient()):
        out = _run(_probe_url("https://example.com/foo"))

    assert out["ok"] is True
    assert out["status"] == 200
    assert out["url"] == "https://example.com/foo"


def test_probe_url_reports_failure_on_network_error():
    from app.services.macro_service import _probe_url

    class BoomClient:
        async def __aenter__(self): raise RuntimeError("blocked")
        async def __aexit__(self, *a): return False

    with patch("app.services.macro_service.httpx.AsyncClient", lambda *a, **kw: BoomClient()):
        out = _run(_probe_url("https://blocked.example.com"))

    assert out["ok"] is False
    assert out["status"] is None
    assert "blocked" in out["note"]


# ── Math helpers ────────────────────────────────────────────────────────────

def test_yoy_change_basic():
    from app.services.macro_service import _yoy_change
    series = [{"date": f"2024-{m:02d}-01", "value": 100.0} for m in range(1, 13)]
    series.append({"date": "2025-01-01", "value": 110.0})  # +10% YoY vs index 0
    assert _yoy_change(series, lag=12) == pytest.approx(10.0)


def test_yoy_change_returns_none_when_too_short():
    from app.services.macro_service import _yoy_change
    series = [{"date": "2025-01-01", "value": 100.0}]
    assert _yoy_change(series, lag=12) is None


def test_yoy_change_returns_none_when_prev_is_zero():
    from app.services.macro_service import _yoy_change
    series = [{"date": f"2024-{i:02d}-01", "value": 0.0} for i in range(1, 14)]
    series[-1]["value"] = 100.0
    assert _yoy_change(series, lag=12) is None


def test_last_two_handles_empty_and_single():
    from app.services.macro_service import _last_two
    assert _last_two([]) == (None, None)
    assert _last_two([{"date": "2025-01-01", "value": 1.0}]) == ({"date": "2025-01-01", "value": 1.0}, None)
    a, b = _last_two([{"date": "2025-01-01", "value": 1.0}, {"date": "2025-02-01", "value": 2.0}])
    assert a["value"] == 2.0
    assert b["value"] == 1.0


def test_series_yoy_produces_correct_length():
    from app.services.macro_service import MacroService
    series = [{"date": f"2024-{m:02d}-01", "value": 100.0 + m} for m in range(1, 13)]
    series += [{"date": f"2025-{m:02d}-01", "value": 110.0 + m} for m in range(1, 13)]
    out = MacroService._series_yoy(series, lag=12)
    # 24 inputs - 12 lag = 12 output points
    assert len(out) == 12
    assert all("date" in p and "value" in p for p in out)


def test_build_yield_curve_handles_missing_tenors():
    from app.services.macro_service import MacroService

    # Both empty → both points still emitted with value=None
    snap = MacroService._build_yield_curve([], [])
    assert len(snap) == 2
    assert {p["tenor"] for p in snap} == {"3M", "10Y"}
    assert all(p["value"] is None for p in snap)

    # 10Y populated, 3M missing
    snap = MacroService._build_yield_curve(
        [], [{"date": "2025-03-01", "value": 7.10}],
    )
    p10 = next(p for p in snap if p["tenor"] == "10Y")
    p3m = next(p for p in snap if p["tenor"] == "3M")
    assert p10["value"] == 7.10
    assert p10["asOf"] == "2025-03-01"
    assert p3m["value"] is None


# ── Strip & dashboard aggregation ───────────────────────────────────────────

def test_get_strip_returns_six_tiles_even_when_everything_fails():
    from app.services.macro_service import MacroService

    svc = MacroService()
    with patch("app.services.macro_service._fetch_fred_series", AsyncMock(return_value=[])), \
         patch.object(svc, "_yahoo_quote", AsyncMock(return_value={})):
        out = _run(svc.get_strip())

    assert "tiles" in out
    assert len(out["tiles"]) == 6
    ids = [t["id"] for t in out["tiles"]]
    assert ids == ["repo", "cpi", "iip", "usdinr", "yield10", "brent"]
    # Every tile is well-formed even when value is None.
    for t in out["tiles"]:
        assert {"id", "label", "unit", "value", "delta", "deltaUnit", "asOf"} <= set(t)


def test_get_strip_populates_repo_from_fred():
    from app.services.macro_service import MacroService

    repo_data = [
        {"date": "2025-01-01", "value": 6.50},
        {"date": "2025-02-01", "value": 6.25},
    ]

    from app.services.macro_service import FRED_SERIES

    async def fake_fetch(series_id: str):
        return repo_data if series_id == FRED_SERIES["repo"] else []

    svc = MacroService()
    with patch("app.services.macro_service._fetch_fred_series", side_effect=fake_fetch), \
         patch.object(svc, "_yahoo_quote", AsyncMock(return_value={})):
        out = _run(svc.get_strip())

    repo_tile = next(t for t in out["tiles"] if t["id"] == "repo")
    assert repo_tile["value"] == 6.25
    assert repo_tile["delta"] == pytest.approx(-0.25)
    assert repo_tile["deltaUnit"] == "pp"


def test_get_strip_populates_usdinr_from_yahoo():
    from app.services.macro_service import MacroService

    svc = MacroService()
    with patch("app.services.macro_service._fetch_fred_series", AsyncMock(return_value=[])), \
         patch.object(svc, "_yahoo_quote", new_callable=AsyncMock) as mock_y:
        mock_y.side_effect = lambda key: {
            "usdinr": {"price": 83.55, "pChange": 0.12},
            "brent":  {"price": 78.40, "pChange": -1.20},
        }.get(key, {})
        out = _run(svc.get_strip())

    usdinr = next(t for t in out["tiles"] if t["id"] == "usdinr")
    assert usdinr["value"] == 83.55
    assert usdinr["delta"] == pytest.approx(0.12)
    brent = next(t for t in out["tiles"] if t["id"] == "brent")
    assert brent["value"] == 78.40


def test_get_dashboard_shape_is_complete_when_data_is_empty():
    from app.services.macro_service import MacroService

    svc = MacroService()
    with patch("app.services.macro_service._fetch_fred_series", AsyncMock(return_value=[])), \
         patch.object(svc, "_yahoo_quote", AsyncMock(return_value={})), \
         patch("app.services.macro_service._probe_url",
               AsyncMock(return_value={"ok": False, "url": "x", "status": None, "note": "stub"})), \
         patch("app.services.macro_service.ai_client.is_available", return_value=False):
        out = _run(svc.get_dashboard())

    assert {"rateTimeline", "cpi", "wpi", "iip", "gdp", "yieldCurve",
            "currencyStrip", "commentary", "fetchedAt", "sources"} <= set(out)
    assert out["rateTimeline"] == []
    assert out["wpi"] == []
    assert isinstance(out["yieldCurve"], dict)
    assert {"ind10yNow", "ind10yAsOf", "ind10yHistory", "snapshot"} <= set(out["yieldCurve"])
    # Curve snapshot always carries both tenors even when empty.
    assert len(out["yieldCurve"]["snapshot"]) == 2
    assert {"usdinr", "dxy", "brent", "gold", "vix"} <= set(out["currencyStrip"])
    assert isinstance(out["commentary"], str) and len(out["commentary"]) > 0


def test_get_dashboard_includes_wpi_when_fred_returns_data():
    from app.services.macro_service import MacroService

    wpi_rows = [
        {"date": "2025-01-01", "value": 2.10},
        {"date": "2025-02-01", "value": 2.30},
    ]

    from app.services.macro_service import FRED_SERIES

    async def fake_fred(sid: str):
        return wpi_rows if sid == FRED_SERIES["wpi"] else []

    svc = MacroService()
    with patch("app.services.macro_service._fetch_fred_series", side_effect=fake_fred), \
         patch.object(svc, "_yahoo_quote", AsyncMock(return_value={})), \
         patch("app.services.macro_service._probe_url",
               AsyncMock(return_value={"ok": False, "url": "x", "status": None, "note": "stub"})), \
         patch("app.services.macro_service.ai_client.is_available", return_value=False):
        out = _run(svc.get_dashboard())

    assert out["wpi"] == wpi_rows


def test_get_dashboard_yield_curve_snapshot_populated_when_3m_and_10y_present():
    from app.services.macro_service import MacroService, FRED_SERIES

    async def fake_fred(sid: str):
        if sid == FRED_SERIES["yield3m"]:
            return [{"date": "2025-03-01", "value": 6.80}]
        if sid == FRED_SERIES["yield10"]:
            return [{"date": "2025-03-01", "value": 7.10}]
        return []

    svc = MacroService()
    with patch("app.services.macro_service._fetch_fred_series", side_effect=fake_fred), \
         patch.object(svc, "_yahoo_quote", AsyncMock(return_value={})), \
         patch("app.services.macro_service._probe_url",
               AsyncMock(return_value={"ok": False, "url": "x", "status": None, "note": "stub"})), \
         patch("app.services.macro_service.ai_client.is_available", return_value=False):
        out = _run(svc.get_dashboard())

    snap = out["yieldCurve"]["snapshot"]
    p3m = next(p for p in snap if p["tenor"] == "3M")
    p10y = next(p for p in snap if p["tenor"] == "10Y")
    assert p3m["value"] == 6.80
    assert p10y["value"] == 7.10
    assert p10y["tenorMonths"] == 120


def test_get_dashboard_sources_report_probe_results_honestly():
    """RBI/MOSPI/CCIL probe results must propagate into the sources array."""
    from app.services.macro_service import MacroService

    probe_results = {
        "https://www.rbi.org.in/scripts/BS_PressReleaseDisplay.aspx":
            {"ok": True,  "url": "https://www.rbi.org.in/scripts/BS_PressReleaseDisplay.aspx", "status": 200, "note": "reachable"},
        "https://eaindustry.nic.in/":
            {"ok": False, "url": "https://eaindustry.nic.in/", "status": None, "note": "unreachable: blocked"},
        "https://www.ccilindia.com/RiskManagement/SecuritiesSegment/Pages/IndianGovernmentBondData.aspx":
            {"ok": False, "url": "https://www.ccilindia.com/RiskManagement/SecuritiesSegment/Pages/IndianGovernmentBondData.aspx", "status": None, "note": "unreachable: blocked"},
    }

    async def fake_probe(url: str, timeout: float = 6.0):
        return probe_results.get(url, {"ok": False, "url": url, "status": None, "note": "stub"})

    svc = MacroService()
    with patch("app.services.macro_service._fetch_fred_series", AsyncMock(return_value=[])), \
         patch.object(svc, "_yahoo_quote", AsyncMock(return_value={})), \
         patch("app.services.macro_service._probe_url", side_effect=fake_probe), \
         patch("app.services.macro_service.ai_client.is_available", return_value=False):
        out = _run(svc.get_dashboard())

    by_id = {s["id"]: s for s in out["sources"]}
    assert by_id["rbi-dbie"]["ok"] is True
    assert by_id["mospi"]["ok"] is False
    assert by_id["ccil"]["ok"] is False
    # Every source carries an id, label, covers, ok, and a url field.
    for src in out["sources"]:
        assert {"id", "label", "covers", "ok"} <= set(src)


def test_get_dashboard_caches_for_24h():
    """Second call within TTL must NOT re-invoke _fetch_fred_csv."""
    from app.services.macro_service import MacroService

    svc = MacroService()
    fetch_mock = AsyncMock(return_value=[])
    with patch("app.services.macro_service._fetch_fred_series", fetch_mock), \
         patch.object(svc, "_yahoo_quote", AsyncMock(return_value={})), \
         patch("app.services.macro_service._probe_url",
               AsyncMock(return_value={"ok": False, "url": "x", "status": None, "note": "stub"})), \
         patch("app.services.macro_service.ai_client.is_available", return_value=False):
        _run(svc.get_dashboard())
        first_calls = fetch_mock.call_count
        _run(svc.get_dashboard())  # cached — no new fetches
        assert fetch_mock.call_count == first_calls


# ── Commentary fallback ─────────────────────────────────────────────────────

def test_commentary_falls_back_to_deterministic_when_ai_unavailable():
    from app.services.macro_service import MacroService

    svc = MacroService()
    repo_s = [{"date": "2025-03-01", "value": 6.25}]
    cpi_s  = [{"date": f"2024-{m:02d}-01", "value": 100.0} for m in range(1, 13)] + \
             [{"date": "2025-01-01", "value": 105.0}]   # 5% YoY
    wpi_s  = [{"date": "2025-03-01", "value": 2.40}]
    iip_s  = []
    yld_s  = [{"date": "2025-03-01", "value": 7.10}]
    usdinr = {"price": 83.5, "pChange": 0.1}
    brent  = {}

    with patch("app.services.macro_service.ai_client.is_available", return_value=False):
        out = _run(svc._build_commentary(repo_s, cpi_s, wpi_s, iip_s, yld_s, usdinr, brent))

    assert "6.25%" in out                 # repo present
    assert "5.00% YoY" in out             # CPI YoY
    assert "+2.40%" in out                # WPI growth
    assert "₹83.50" in out                # USD/INR
    assert "Industrial production" not in out  # iip empty → not mentioned


def test_commentary_uses_deterministic_when_ai_returns_sentinel():
    from app.services.macro_service import MacroService

    svc = MacroService()
    repo_s = [{"date": "2025-03-01", "value": 6.25}]
    with patch("app.services.macro_service.ai_client.is_available", return_value=True), \
         patch("app.services.macro_service.ai_client.ask",
               AsyncMock(return_value="[AI unavailable: rate-limited]")):
        out = _run(svc._build_commentary(repo_s, [], [], [], [], {}, {}))

    assert "6.25%" in out
    assert "AI unavailable" not in out


# ── Route smoke tests ───────────────────────────────────────────────────────

def test_macro_strip_route_returns_200_and_six_tiles(client):
    with patch("app.services.macro_service._fetch_fred_series", AsyncMock(return_value=[])), \
         patch("app.services.macro_service.YahooService.get_quote", AsyncMock(return_value=None)):
        r = client.get("/api/insights/macro/strip")

    assert r.status_code == 200
    body = r.json()
    assert "tiles" in body
    assert len(body["tiles"]) == 6
    assert "meta" in body and body["meta"]["servedFrom"] == "MACRO_STRIP"


def test_macro_dashboard_route_returns_200_with_full_shape(client):
    with patch("app.services.macro_service._fetch_fred_series", AsyncMock(return_value=[])), \
         patch("app.services.macro_service.YahooService.get_quote", AsyncMock(return_value=None)), \
         patch("app.services.macro_service._probe_url",
               AsyncMock(return_value={"ok": False, "url": "x", "status": None, "note": "stub"})), \
         patch("app.services.macro_service.ai_client.is_available", return_value=False):
        r = client.get("/api/insights/macro")

    assert r.status_code == 200
    body = r.json()
    assert {"rateTimeline", "cpi", "wpi", "iip", "gdp", "yieldCurve",
            "currencyStrip", "commentary", "fetchedAt", "sources", "meta"} <= set(body)
    assert body["meta"]["servedFrom"] == "MACRO_DASHBOARD"
    assert len(body["yieldCurve"]["snapshot"]) == 2
