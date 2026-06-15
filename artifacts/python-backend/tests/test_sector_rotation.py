"""Unit tests for the Sector-Rotation cockpit pure logic:
  * RRG math (rsRatio / rsMomentum / quadrant) — sector_rotation_service
  * quantity-weighted group delivery — delivery_service
  * winning-stocks composite ranking — sector_rotation_service

These cover the parts that must be exactly right; the data wiring
(Postgres / yfinance / synthetic) is integration-tested via the running app.
"""
from __future__ import annotations

from app.services import sector_rotation_service as sr
from app.services import delivery_service as deliv


# ── RRG ──────────────────────────────────────────────────────────────────────

def test_quadrant_for_mapping():
    assert sr.quadrant_for(101, 101) == "Leading"
    assert sr.quadrant_for(99, 101) == "Improving"
    assert sr.quadrant_for(101, 99) == "Weakening"
    assert sr.quadrant_for(99, 99) == "Lagging"
    # Exactly 100 counts as the upper side (>=100).
    assert sr.quadrant_for(100, 100) == "Leading"


def _series(vals):
    return [(f"2026-01-{i + 1:02d}", v) for i, v in enumerate(vals)]


def test_compute_rrg_steady_outperformer_is_leading():
    n = 40
    bench = _series([100.0] * n)
    entity = _series([100 + i * 0.8 for i in range(n)])   # steadily outperforming
    out = sr.compute_rrg(entity, bench, smooth=10, tail=8, sample_every=5)
    assert out is not None
    assert out["quadrant"] == "Leading"
    assert out["rsRatio"] >= 100
    assert len(out["tail"]) >= 1
    # tail points carry their own quadrant label
    assert all("quadrant" in p for p in out["tail"])


def test_compute_rrg_flat_is_neutral():
    n = 40
    out = sr.compute_rrg(_series([100.0] * n), _series([100.0] * n), smooth=10)
    assert out is not None
    assert abs(out["rsRatio"] - 100.0) < 1e-6
    assert abs(out["rsMomentum"] - 100.0) < 1e-6


def test_compute_rrg_insufficient_history_returns_none():
    bench = _series([100.0] * 40)
    assert sr.compute_rrg(_series([100.0] * 5), bench, smooth=10) is None


# ── Delivery aggregation (the accuracy fix) ──────────────────────────────────

def test_aggregate_delivery_is_quantity_weighted_not_simple_mean():
    rows = [
        {"symbol": "BIGBANK", "tradedQty": 10_000_000, "delivQty": 4_000_000,
         "delivPct": 40.0, "turnover": 1e9, "delivValue": 4e8},
        {"symbol": "TINYBANK", "tradedQty": 10_000, "delivQty": 9_000,
         "delivPct": 90.0, "turnover": 1e6, "delivValue": 9e5},
    ]
    groups = {"NIFTY BANK": ["BIGBANK", "TINYBANK", "MISSING"]}
    res = deliv.aggregate_delivery(groups, rows)[0]
    assert res["count"] == 2                       # MISSING dropped
    # Quantity-weighted reflects real flow (~40%), NOT the distorted simple mean (65%).
    expected = round((4_000_000 + 9_000) / (10_000_000 + 10_000) * 100, 2)
    assert res["delivRatio"] == expected
    assert res["avgDelivPct"] == 65.0
    assert res["delivRatio"] < res["avgDelivPct"]
    assert res["topSymbol"] == "TINYBANK"


def test_aggregate_delivery_empty_group_dropped():
    rows = [{"symbol": "X", "tradedQty": 1, "delivQty": 1, "delivPct": 50.0,
             "turnover": 1, "delivValue": 1}]
    out = deliv.aggregate_delivery({"EMPTY": ["NOPE"]}, rows)
    assert out == []


# ── Shortlist composite ranking ──────────────────────────────────────────────

def test_rank_shortlist_orders_by_composite_score():
    rows = [
        {"symbol": "STRONG", "rs": 12.0, "delivPct": 80.0, "aboveTrend": True},
        {"symbol": "MID",    "rs": 2.0,  "delivPct": 55.0, "aboveTrend": True},
        {"symbol": "WEAK",   "rs": -8.0, "delivPct": 30.0, "aboveTrend": False},
        {"symbol": "NODATA", "rs": None, "delivPct": None, "aboveTrend": None},
    ]
    ranked = sr.rank_shortlist(rows)
    assert ranked[0]["symbol"] == "STRONG"
    assert [r["symbol"] for r in ranked[:2]] == ["STRONG", "MID"]
    # Every row gets a 0..100 score.
    assert all(0.0 <= r["score"] <= 100.0 for r in ranked)
    assert ranked[0]["score"] >= ranked[-1]["score"]
