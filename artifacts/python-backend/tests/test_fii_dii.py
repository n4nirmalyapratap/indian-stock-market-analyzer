"""
Contract / smoke tests for the FII-DII Insights endpoint.

These tests guard the response shape (`summary.ytd`, `monthly[]`, `rows`,
`totalDays`, segment switching) so future refactors do not silently break
the frontend hero cards or month-wise breakdown.

Tests run against the in-memory FastAPI TestClient with auth disabled and
the FiiDiiService monkey-patched to return a deterministic frame — no
network and no SQLite I/O.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient


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


def _fake_equity_df(n: int = 40) -> pd.DataFrame:
    """Build a deterministic n-day equity frame ending today."""
    end = pd.Timestamp(datetime.today().date())
    dates = pd.date_range(end=end, periods=n, freq="D")
    rows = []
    for i, d in enumerate(dates):
        rows.append({
            "date":    d,
            "fii_buy":  1000.0 + i,
            "fii_sell":  900.0 + i,
            "fii_net":   100.0 + (i % 5 - 2),
            "dii_buy":   800.0 + i,
            "dii_sell":  700.0 + i,
            "dii_net":   100.0 - (i % 5 - 2),
        })
    return pd.DataFrame(rows)


def _fake_fno_df(n: int = 40) -> pd.DataFrame:
    end = pd.Timestamp(datetime.today().date())
    dates = pd.date_range(end=end, periods=n, freq="D")
    rows = []
    for i, d in enumerate(dates):
        rows.append({
            "date":         d,
            "fii_long":     500_000 + i,
            "fii_short":    400_000 + i,
            "fii_net":      100_000 + i,
            "dii_long":     300_000 + i,
            "dii_short":    250_000 + i,
            "dii_net":       50_000 + i,
            "client_long":  900_000,
            "client_short": 850_000,
            "pro_long":     200_000,
            "pro_short":    180_000,
        })
    return pd.DataFrame(rows)


def test_fii_dii_equity_contract(client):
    """Equity response must expose rows[], summary {daily,weekly,monthly,ytd},
    monthly[] buckets and totalDays/rangeDays."""
    fake = _fake_equity_df(40)

    async def fake_get_historical(self, segment, start, end):
        return fake

    with patch(
        "app.services.fii_dii_service.FiiDiiService.get_historical",
        new=fake_get_historical,
    ):
        resp = client.get("/api/insights/fii-dii?segment=equity&days=365")

    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    assert data["segment"] == "equity"
    assert data["totalDays"] == 40
    assert data["rangeDays"] == 365

    # Required summary shape
    summ = data["summary"]
    for key in ("daily", "weekly", "monthly", "ytd"):
        assert key in summ, f"summary.{key} missing"
        assert "fiiNet" in summ[key]
        assert "diiNet" in summ[key]
        assert "days" in summ[key]

    # "Last 30 Sessions" card binds to summary.monthly — must be exactly 30
    assert summ["monthly"]["expectedDays"] == 30
    assert summ["monthly"]["days"] == 30

    # YTD must be true calendar Jan 1 (yearStart present, days <= rows)
    assert summ["ytd"].get("yearStart", "").startswith(str(datetime.today().year))
    assert summ["ytd"]["days"] <= 40

    # Monthly buckets are non-empty and grouped by YYYY-MM keys
    monthly = data["monthly"]
    assert isinstance(monthly, list) and len(monthly) >= 1
    for b in monthly:
        for f in ("key", "label", "fiiNet", "diiNet", "greenDays", "redDays", "days", "rows"):
            assert f in b, f"monthly bucket missing field {f}"
        assert len(b["key"]) == 7  # YYYY-MM


def test_fii_dii_fno_segment_switch(client):
    """Switching segment query param routes to F&O frame and reports F&O long/short
    correctly mapped into the same fiiBuy/fiiSell/fiiNet wire shape."""
    fake = _fake_fno_df(40)

    async def fake_get_historical(self, segment, start, end):
        return fake

    with patch(
        "app.services.fii_dii_service.FiiDiiService.get_historical",
        new=fake_get_historical,
    ):
        resp = client.get("/api/insights/fii-dii?segment=index_future&days=180")

    assert resp.status_code == 200
    data = resp.json()
    assert data["segment"] == "index_future"
    assert data["totalDays"] == 40

    # Latest row exists and uses long/short mapped into buy/sell fields
    latest = data["latest"]
    assert latest is not None
    assert latest["fiiBuy"] is not None  # = fii_long
    assert latest["fiiSell"] is not None  # = fii_short
    assert latest["fiiNet"] is not None
    assert latest["diiNet"] is not None


def test_fii_dii_days_param_validation(client):
    """days must be capped at backend's hard upper bound (le=1500)."""
    resp = client.get("/api/insights/fii-dii?segment=equity&days=99999")
    assert resp.status_code == 422  # FastAPI validation rejects out-of-range


def test_fii_dii_backfill_requires_admin(client):
    """The state-changing backfill endpoint must reject callers lacking the
    admin token — defense in depth on top of ClerkAuthMiddleware."""
    resp = client.post("/api/insights/fii-dii/backfill?days=60")
    assert resp.status_code == 403
    assert "admin" in resp.json().get("error", "").lower()
