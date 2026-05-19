"""End-to-end tests for the Portfolio Manager (`/api/portfolio/*`).

These hit the FastAPI app end-to-end and rely on the Postgres-backed
portfolio_service. Skipped when ``DATABASE_URL`` is unset (e.g. CI without
a Postgres service) — set it to a disposable local instance to run them.
"""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

# Skip the whole module if no Postgres is reachable. portfolio_service
# now writes to PG and ``ensure_primary_schema()`` runs at import time;
# without DATABASE_URL the import itself blows up.
pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; skipping Postgres-backed portfolio tests.",
)


@pytest.fixture(scope="module")
def client(monkeypatch_module):
    monkeypatch_module.setenv("DISABLE_AUTH", "1")
    from main import app  # noqa: PLC0415
    return TestClient(app)


@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch  # noqa: PLC0415
    mp = MonkeyPatch()
    yield mp
    mp.undo()


def test_create_list_delete(client):
    r = client.post("/api/portfolio", json={"name": "T1", "cash": 50_000})
    assert r.status_code == 200
    pid = r.json()["id"]

    r = client.get("/api/portfolio")
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()["portfolios"]]
    assert pid in ids

    r = client.delete(f"/api/portfolio/{pid}")
    assert r.status_code == 200
    assert r.json()["success"] is True


def test_transactions_and_valuation(client):
    pid = client.post("/api/portfolio", json={"name": "T2", "cash": 100_000}).json()["id"]
    try:
        for tx in [
            {"symbol": "RELIANCE", "side": "BUY",  "qty": 10, "price": 2400, "tradedAt": "2024-01-15"},
            {"symbol": "TCS",      "side": "BUY",  "qty": 5,  "price": 3500, "tradedAt": "2024-02-20"},
            {"symbol": "RELIANCE", "side": "SELL", "qty": 3,  "price": 2600, "tradedAt": "2024-03-01"},
        ]:
            r = client.post(f"/api/portfolio/{pid}/transactions", json=tx)
            assert r.status_code == 200, r.text

        v = client.get(f"/api/portfolio/{pid}/valuation").json()
        symbols = {h["symbol"]: h for h in v["holdings"]}
        assert symbols["RELIANCE"]["qty"] == 7    # 10 - 3 sold
        assert symbols["TCS"]["qty"] == 5
        # SELL booked realised P&L: (2600-2400)*3 = 600
        assert any(round(h["realised"], 0) == 600 for h in v["holdings"]
                   if h["symbol"] == "RELIANCE")
        # Cash: 100000 - (10*2400) - (5*3500) + (3*2600) = 66300
        assert abs(v["totals"]["cash"] - 66300) < 1e-6
    finally:
        client.delete(f"/api/portfolio/{pid}")


def test_csv_import_zerodha_and_generic(client):
    pid = client.post("/api/portfolio", json={"name": "T3"}).json()["id"]
    try:
        zerodha_csv = (
            "trade_date,tradingsymbol,exchange,segment,trade_type,quantity,price,brokerage\n"
            "2024-04-10,WIPRO,NSE,EQ,buy,20,250,0.5\n"
            "2024-04-15,ITC,NSE,EQ,buy,30,420,0.5\n"
        )
        r = client.post(f"/api/portfolio/{pid}/import", json={"csv": zerodha_csv})
        assert r.status_code == 200
        body = r.json()
        assert body["format"] == "zerodha"
        assert body["rowsInserted"] == 2

        # Generic CSV with explicit symbol normalisation (-EQ suffix)
        generic = "symbol,side,qty,price,date\nINFY-EQ,BUY,12,1450,2024-05-01\n"
        r = client.post(f"/api/portfolio/{pid}/import", json={"csv": generic})
        assert r.status_code == 200
        assert r.json()["rowsInserted"] == 1

        txs = client.get(f"/api/portfolio/{pid}/transactions").json()["transactions"]
        # INFY-EQ should be normalised to INFY
        assert {"WIPRO", "ITC", "INFY"}.issubset({t["symbol"] for t in txs})
    finally:
        client.delete(f"/api/portfolio/{pid}")


def test_optimizer_markowitz_and_cvar(client):
    pid = client.post("/api/portfolio", json={"name": "T4"}).json()["id"]
    try:
        for sym, qty in [("RELIANCE", 5), ("TCS", 3), ("HDFCBANK", 8), ("INFY", 6)]:
            client.post(f"/api/portfolio/{pid}/transactions",
                        json={"symbol": sym, "side": "BUY", "qty": qty,
                              "price": 1000, "tradedAt": "2024-02-01"})

        r = client.post(f"/api/portfolio/{pid}/optimize", json={"method": "markowitz"})
        assert r.status_code == 200, r.text
        opt = r.json()
        assert opt["method"] == "markowitz"
        # Frontier may degrade if history fetch fails — accept both shapes but
        # require at least target weights + trades to come back.
        if opt.get("frontier"):
            assert len(opt["frontier"]["frontier"]) > 0
        assert sum(opt["targetWeights"].values()) == pytest.approx(1.0, abs=0.05)

        r = client.post(f"/api/portfolio/{pid}/optimize",
                        json={"method": "cvar", "confidence": 0.95})
        assert r.status_code == 200
        body = r.json()
        if not body.get("result", {}).get("error"):
            assert body["result"]["cvarPct"] is not None
    finally:
        client.delete(f"/api/portfolio/{pid}")


def test_equity_curve_no_double_count_cash(client):
    """Regression: equity must equal mark-to-market + actual cash (not double-count).

    Setup: seed ₹100,000 cash, BUY 10 RELIANCE @ 2000 (uses ₹20,000), so the
    book holds 10 shares + ₹80,000 cash. With a stub price feed that pins
    RELIANCE at exactly ₹2000 every day, the equity series must be flat at
    ₹100,000 — *not* ₹100,000 + ₹80,000 (the previous double-count bug).
    """
    import asyncio  # noqa: PLC0415
    from app.services import portfolio_service as ps  # noqa: PLC0415

    pid = client.post("/api/portfolio", json={"name": "EQ-CURVE", "cash": 100_000}).json()["id"]
    try:
        client.post(f"/api/portfolio/{pid}/transactions",
                    json={"symbol": "RELIANCE", "side": "BUY", "qty": 10,
                          "price": 2000, "tradedAt": "2024-01-15"})

        class _StubPS:
            async def get_historical_data(self, symbol, days):
                # Generate `days`+30 calendar dates with constant 2000 close
                # for any symbol (positions and benchmark).
                from datetime import date, timedelta  # noqa: PLC0415
                today = date(2024, 6, 30)
                out = []
                for i in range(days + 30):
                    d = today - timedelta(days=days + 30 - i - 1)
                    if d.weekday() < 5:  # weekdays only
                        out.append({"date": d.isoformat(), "close": 2000.0})
                return out

        # User id when DISABLE_AUTH=1 + no headers is "test_user" (see
        # `app/middleware/clerk_auth.py`) — match that so the portfolio is
        # found in the SQLite store.
        result = asyncio.run(
            ps.equity_curve("test_user", pid, _StubPS(), days=180, benchmark="^NSEI"))
        series = result["series"]
        assert len(series) > 0, "equity_curve produced no points"

        # Every point: 10 shares * 2000 + 80,000 cash = 100,000 (post-buy),
        # or 100,000 cash (pre-buy). Both sides must equal exactly 100,000.
        for pt in series:
            assert abs(pt["equity"] - 100_000) < 1.0, \
                f"equity_curve double-counted cash on {pt['date']}: {pt['equity']}"
    finally:
        client.delete(f"/api/portfolio/{pid}")


def test_sortino_extension():
    """Verify the new Sortino + Sharpe + max-DD extensions of hydra_var_service."""
    from app.services import hydra_var_service as hv  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    rng = np.random.default_rng(42)
    closes = (100 * np.exp(np.cumsum(rng.normal(0.0005, 0.012, size=400)))).tolist()

    s = hv.sortino_ratio(closes)
    assert s.get("sortino") is not None
    assert s["sampleSize"] >= 350

    sh = hv.sharpe_ratio(closes)
    assert sh.get("sharpe") is not None

    dd = hv.max_drawdown(closes)
    assert dd["maxDrawdownPct"] <= 0
    assert dd["peakIndex"] <= dd["troughIndex"]


def test_xlsx_import_endpoint(client):
    """Excel upload via /import-file must reach the same import pipeline as CSV."""
    from io import BytesIO  # noqa: PLC0415
    from openpyxl import Workbook  # noqa: PLC0415

    # Build a tiny workbook in memory
    wb = Workbook()
    ws = wb.active
    ws.append(["symbol", "side", "qty", "price", "date"])
    ws.append(["RELIANCE", "BUY",  10, 2500.0, "2024-03-01"])
    ws.append(["TCS",      "BUY",   5, 3500.0, "2024-04-01"])
    ws.append(["RELIANCE", "SELL",  3, 2700.0, "2024-05-01"])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    # Create a portfolio
    pid = client.post("/api/portfolio", json={"name": "XLSX-Test", "cash": 100_000}).json()["id"]
    try:
        r = client.post(
            f"/api/portfolio/{pid}/import-file",
            files={"file": ("trades.xlsx", buf.getvalue(),
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["rowsParsed"] == 3
        assert body["rowsInserted"] == 3
        assert body.get("source_filename") == "trades.xlsx"

        # Verify transactions actually landed
        txs = client.get(f"/api/portfolio/{pid}/transactions").json()["transactions"]
        assert len(txs) == 3
        assert {t["symbol"] for t in txs} == {"RELIANCE", "TCS"}
    finally:
        client.delete(f"/api/portfolio/{pid}")


def test_xlsx_helper_neutralises_formula_injection():
    """=,+,-,@ at cell start must be quoted so downstream Excel opens
    don't auto-execute formulas (CWE-1236).
    We bypass the helper's openpyxl reader by feeding ``_safe_cell_str``
    directly — that's the unit under test for sanitisation."""
    from app.services import portfolio_service as ps  # noqa: PLC0415

    assert ps._safe_cell_str("=cmd|'/c calc'!A0").startswith("'=")
    assert ps._safe_cell_str("+1+1").startswith("'+")
    assert ps._safe_cell_str("-2+3").startswith("'-")
    assert ps._safe_cell_str("@SUM(A1:A2)").startswith("'@")
    # Benign strings must pass through unchanged
    assert ps._safe_cell_str("RELIANCE") == "RELIANCE"
    assert ps._safe_cell_str(None) == ""
    assert ps._safe_cell_str(42) == "42"


def test_xlsx_helper_rejects_oversize_blob():
    """Compressed-size cap must trip before openpyxl parses the bytes."""
    from app.services import portfolio_service as ps  # noqa: PLC0415
    blob = b"\x00" * (ps.XLSX_MAX_RAW_BYTES + 1)
    import pytest as _pt  # noqa: PLC0415
    with _pt.raises(ValueError, match="too large"):
        ps.xlsx_bytes_to_csv(blob)


def test_xlsx_import_endpoint_rejects_bad_file(client):
    """A non-spreadsheet file must be refused with a clean 4xx, not crash."""
    pid = client.post("/api/portfolio", json={"name": "XLSX-Bad", "cash": 0}).json()["id"]
    try:
        r = client.post(
            f"/api/portfolio/{pid}/import-file",
            files={"file": ("junk.bin", b"not a workbook", "application/octet-stream")},
        )
        assert r.status_code in (400, 422), r.text
    finally:
        client.delete(f"/api/portfolio/{pid}")
