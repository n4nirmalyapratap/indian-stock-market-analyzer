"""
Tests for the capital-gains tax report — the FIFO matching is fiddly enough
that drift in the math would silently report wrong gains to the user.

These lock in:
  * FY parsing (positive + negative cases)
  * STCG vs LTCG split at the 365-day boundary
  * FIFO across multiple buy lots feeding one sell
  * Proportional fee allocation per matched share
  * DIVIDEND captured separately, not as a capital gain
  * Unmatched sells surfaced as warnings (not silently dropped)
  * Aggregates (totals, count) compute correctly with gains + losses

We monkeypatch `tax_report_service.ps` with a tiny in-memory stub so the
tests don't need Postgres or any other infra.
"""
from __future__ import annotations

import pytest

from app.services import tax_report_service as trs


# ── Stub portfolio_service so we don't need a DB ─────────────────────────────

class _FakePortfolioService:
    """Tiny in-memory stand-in for portfolio_service. Only `get_portfolio`
    and `list_transactions` are needed by tax_report_service."""

    def __init__(self):
        self.portfolios: dict[tuple[str, str], dict] = {}
        self.txs: dict[str, list[dict]] = {}

    def get_portfolio(self, user_id: str, pid: str):
        return self.portfolios.get((user_id, pid))

    def list_transactions(self, user_id: str, pid: str, symbol=None):
        return list(self.txs.get(pid, []))


@pytest.fixture
def fake_ps(monkeypatch):
    fake = _FakePortfolioService()
    monkeypatch.setattr(trs, "ps", fake)
    fake.portfolios[("u1", "p1")] = {"id": "p1", "userId": "u1", "cash": 0,
                                      "name": "Test"}
    return fake


# ── FY parsing ───────────────────────────────────────────────────────────────

def test_parse_fy_basic():
    start, end = trs._parse_fy("2024-25")
    assert (start.year, start.month, start.day) == (2024, 4, 1)
    assert (end.year, end.month, end.day) == (2025, 3, 31)


def test_parse_fy_four_digit_end():
    start, end = trs._parse_fy("2024-2025")
    assert start.year == 2024 and end.year == 2025


def test_parse_fy_rejects_malformed():
    with pytest.raises(ValueError):
        trs._parse_fy("")
    with pytest.raises(ValueError):
        trs._parse_fy("2024")
    with pytest.raises(ValueError):
        trs._parse_fy("2024-26")  # not consecutive
    with pytest.raises(ValueError):
        trs._parse_fy("abc-25")


# ── STCG / LTCG split ────────────────────────────────────────────────────────

def test_stcg_when_held_less_than_one_year(fake_ps):
    """Sold 200 days after buy — must land in STCG."""
    fake_ps.txs["p1"] = [
        _buy("RELIANCE", qty=10, price=2000, date="2024-05-01"),
        _sell("RELIANCE", qty=10, price=2200, date="2024-11-17"),
    ]
    report = trs.compute_report("u1", "p1", "2024-25")
    assert report["shortTerm"]["count"] == 1
    assert report["longTerm"]["count"] == 0
    row = report["shortTerm"]["rows"][0]
    assert row["gainLoss"] == pytest.approx(2000.0)   # (2200-2000)*10
    assert row["holdingDays"] == 200


def test_ltcg_when_held_more_than_one_year(fake_ps):
    """Held 366 days — flips to LTCG."""
    fake_ps.txs["p1"] = [
        _buy("TCS", qty=5, price=3000, date="2023-04-01"),
        _sell("TCS", qty=5, price=3500, date="2024-04-01"),  # 366 days
    ]
    report = trs.compute_report("u1", "p1", "2024-25")
    assert report["shortTerm"]["count"] == 0
    assert report["longTerm"]["count"] == 1
    assert report["longTerm"]["rows"][0]["holdingDays"] == 366


def test_exactly_365_days_is_ltcg(fake_ps):
    """Boundary check — 365 days exactly counts as long-term per our threshold."""
    fake_ps.txs["p1"] = [
        _buy("INFY", qty=1, price=1000, date="2023-04-01"),
        _sell("INFY", qty=1, price=1100, date="2024-03-31"),  # exactly 365 days
    ]
    report = trs.compute_report("u1", "p1", "2023-24")
    assert report["longTerm"]["count"] == 1
    assert report["shortTerm"]["count"] == 0


# ── FIFO across multiple lots ────────────────────────────────────────────────

def test_fifo_consumes_oldest_lot_first(fake_ps):
    """Two BUY lots, one SELL — FIFO must consume the cheaper, older lot
    first, producing a larger gain than averaging would."""
    fake_ps.txs["p1"] = [
        _buy("HDFC", qty=10, price=1000, date="2024-05-01"),  # older
        _buy("HDFC", qty=10, price=1500, date="2024-08-01"),  # newer
        _sell("HDFC", qty=10, price=2000, date="2024-12-01"),
    ]
    report = trs.compute_report("u1", "p1", "2024-25")
    assert len(report["shortTerm"]["rows"]) == 1
    row = report["shortTerm"]["rows"][0]
    # FIFO: matched against the ₹1000 lot, not the ₹1500 lot.
    assert row["buyPrice"] == 1000.0
    assert row["gainLoss"] == pytest.approx(10000.0)  # (2000-1000)*10


def test_fifo_splits_sell_across_two_lots(fake_ps):
    """SELL of 15 spans the 10-share old lot and 5 shares of the newer lot —
    must produce two matched rows."""
    fake_ps.txs["p1"] = [
        _buy("HDFC", qty=10, price=1000, date="2024-05-01"),
        _buy("HDFC", qty=10, price=1500, date="2024-08-01"),
        _sell("HDFC", qty=15, price=2000, date="2024-12-01"),
    ]
    report = trs.compute_report("u1", "p1", "2024-25")
    rows = report["shortTerm"]["rows"]
    assert len(rows) == 2
    # First row uses the old ₹1000 lot fully (qty=10)
    assert rows[0]["buyPrice"] == 1000.0 and rows[0]["qty"] == 10
    # Second row uses 5 from the ₹1500 lot
    assert rows[1]["buyPrice"] == 1500.0 and rows[1]["qty"] == 5
    # Aggregate gain = (2000-1000)*10 + (2000-1500)*5 = 12,500
    assert report["shortTerm"]["net"] == pytest.approx(12500.0)


# ── Fee allocation ───────────────────────────────────────────────────────────

def test_fees_pro_rated_when_lot_is_partially_consumed(fake_ps):
    """Buy 10 shares with ₹100 fees, sell only 4 — the matched lot should
    carry ₹40 of the buy fees (4/10 share)."""
    fake_ps.txs["p1"] = [
        _buy("WIPRO", qty=10, price=500, date="2024-05-01", fees=100),
        _sell("WIPRO", qty=4, price=600, date="2024-08-01", fees=8),
    ]
    report = trs.compute_report("u1", "p1", "2024-25")
    row = report["shortTerm"]["rows"][0]
    # Buy cost  = 500*4 + 40 (4/10 of 100)  = 2040
    # Sell value= 600*4 - 8                  = 2392
    # Gain      = 2392 - 2040 = 352
    assert row["gainLoss"] == pytest.approx(352.0)
    assert row["feeAllocated"] == pytest.approx(48.0)  # 40 + 8


# ── Dividends ────────────────────────────────────────────────────────────────

def test_dividends_are_separate_section(fake_ps):
    """A DIVIDEND tx must NOT count as a capital gain; it lands in the
    dividends bucket only."""
    fake_ps.txs["p1"] = [
        _dividend("ITC", qty=100, per_share=5.0, date="2024-09-15"),
    ]
    report = trs.compute_report("u1", "p1", "2024-25")
    assert report["shortTerm"]["count"] == 0
    assert report["longTerm"]["count"] == 0
    assert report["dividends"]["count"] == 1
    assert report["dividends"]["total"] == pytest.approx(500.0)
    assert report["dividends"]["rows"][0]["symbol"] == "ITC"


# ── Unmatched sells ──────────────────────────────────────────────────────────

def test_unmatched_sell_is_surfaced(fake_ps):
    """A SELL with no preceding BUY (e.g. partial CSV import) must NOT be
    silently dropped — it lands in unmatched.sells so the user sees it."""
    fake_ps.txs["p1"] = [
        _sell("UNKNOWN", qty=10, price=500, date="2024-08-01"),
    ]
    report = trs.compute_report("u1", "p1", "2024-25")
    assert report["unmatched"]["count"] == 1
    assert report["unmatched"]["sells"][0]["unmatchedQty"] == 10
    # Capital gains buckets must be empty — no buy means no realised gain.
    assert report["shortTerm"]["count"] == 0


def test_partial_unmatched_sell(fake_ps):
    """Sell 15 but only own 10 — 10 get matched as STCG, 5 land in unmatched."""
    fake_ps.txs["p1"] = [
        _buy("HDFC", qty=10, price=1000, date="2024-05-01"),
        _sell("HDFC", qty=15, price=2000, date="2024-08-01"),
    ]
    report = trs.compute_report("u1", "p1", "2024-25")
    assert report["shortTerm"]["count"] == 1
    assert report["shortTerm"]["rows"][0]["qty"] == 10
    assert report["unmatched"]["count"] == 1
    assert report["unmatched"]["sells"][0]["unmatchedQty"] == 5


# ── Out-of-FY filtering ──────────────────────────────────────────────────────

def test_only_sells_within_fy_appear_in_buckets(fake_ps):
    """Buy in 2022, sell in FY 2024-25, query FY 2023-24 → empty.
    Query FY 2024-25 → one matched row. The FIFO queue must still
    consume the buy lot during the 2024 sell traversal even when the
    user asks for the 2023 report."""
    fake_ps.txs["p1"] = [
        _buy("RELIANCE", qty=10, price=2000, date="2022-05-01"),
        _sell("RELIANCE", qty=10, price=2500, date="2024-08-01"),
    ]
    r23 = trs.compute_report("u1", "p1", "2023-24")
    assert r23["shortTerm"]["count"] == 0
    assert r23["longTerm"]["count"] == 0

    r24 = trs.compute_report("u1", "p1", "2024-25")
    assert r24["longTerm"]["count"] == 1  # held > 2 years


def test_aggregate_totals_handle_gains_and_losses(fake_ps):
    """STCG aggregator should split gains vs losses, then net them."""
    fake_ps.txs["p1"] = [
        _buy("A", qty=10, price=100, date="2024-05-01"),
        _sell("A", qty=10, price=150, date="2024-08-01"),  # +500
        _buy("B", qty=10, price=200, date="2024-05-01"),
        _sell("B", qty=10, price=180, date="2024-08-01"),  # -200
    ]
    report = trs.compute_report("u1", "p1", "2024-25")
    stcg = report["shortTerm"]
    assert stcg["totalGains"]  == pytest.approx(500.0)
    assert stcg["totalLosses"] == pytest.approx(-200.0)
    assert stcg["net"]         == pytest.approx(300.0)


# ── list_available_fys ───────────────────────────────────────────────────────

def test_list_available_fys_returns_distinct_fys_newest_first(fake_ps):
    fake_ps.txs["p1"] = [
        _buy("A", qty=1, price=1, date="2022-09-15"),  # FY 2022-23
        _buy("B", qty=1, price=1, date="2024-04-10"),  # FY 2024-25
        _sell("A", qty=1, price=2, date="2025-01-20"), # FY 2024-25
    ]
    fys = trs.list_available_fys("u1", "p1")
    assert fys == ["2024-25", "2022-23"]


# ── CSV export ───────────────────────────────────────────────────────────────

def test_to_csv_includes_all_three_sections(fake_ps):
    fake_ps.txs["p1"] = [
        _buy("A", qty=1, price=100, date="2024-05-01"),
        _sell("A", qty=1, price=150, date="2024-08-01"),
        _dividend("B", qty=10, per_share=2.5, date="2024-10-01"),
        _sell("UNKNOWN", qty=1, price=50, date="2024-12-01"),
    ]
    report = trs.compute_report("u1", "p1", "2024-25")
    csv_text = trs.to_csv(report)
    assert "Short-Term Capital Gains" in csv_text
    assert "Long-Term Capital Gains"  in csv_text
    assert "Dividend income"          in csv_text
    assert "Unmatched SELLs"          in csv_text
    assert "STCG total:" in csv_text


# ── Helpers ──────────────────────────────────────────────────────────────────

def _buy(symbol: str, *, qty: float, price: float, date: str,
         fees: float = 0.0) -> dict:
    return {"id": f"buy-{symbol}-{date}", "symbol": symbol, "side": "BUY",
            "qty": qty, "price": price, "fees": fees, "tradedAt": date}


def _sell(symbol: str, *, qty: float, price: float, date: str,
          fees: float = 0.0) -> dict:
    return {"id": f"sell-{symbol}-{date}", "symbol": symbol, "side": "SELL",
            "qty": qty, "price": price, "fees": fees, "tradedAt": date}


def _dividend(symbol: str, *, qty: float, per_share: float, date: str) -> dict:
    return {"id": f"div-{symbol}-{date}", "symbol": symbol, "side": "DIVIDEND",
            "qty": qty, "price": per_share, "fees": 0.0, "tradedAt": date}
