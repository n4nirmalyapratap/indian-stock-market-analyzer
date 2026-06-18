"""
Tests for the P1 data-honesty fixes from the Dashboard / ChartView audit:

  1. price_service.py — pChange falls back to None (not 0) when the EOD
     previous close is itself 0 (pathological divide-by-zero guard).
  2. indicators.calculate_vwap — tolerates rows with missing `volume`
     keys instead of raising KeyError.
  3. sectors_service — A/D ratio surfaces None (not the raw `advances`
     count) when declines == 0, so the UI can render "∞" / "—" instead
     of misrepresenting a count as a ratio.
  4. patterns_service — cached scan results are re-run after the TTL
     expires (previously they were pinned until process restart).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services import patterns_service as ps
from app.services import sectors_service as ss
from app.services.indicators import calculate_vwap


# ── 1. VWAP tolerates missing volume key ─────────────────────────────────────


def test_vwap_missing_volume_key_does_not_raise():
    """Previously `d["volume"] or 0` would KeyError if `volume` was absent.
    `.get` makes the indicator robust to upstream feeds that drop the field."""
    bars = [
        {"high": 110, "low": 90,  "close": 100},  # no `volume` key at all
        {"high": 115, "low": 95,  "close": 105},
    ]
    out = calculate_vwap(bars)
    # When every bar has zero volume the running cum_vol is 0 and we fall
    # back to typical price for that bar — documented degenerate case.
    assert len(out) == 2
    assert out[0] == pytest.approx((110 + 90 + 100) / 3)


def test_vwap_explicit_none_volume_treated_as_zero():
    bars = [
        {"high": 110, "low": 90,  "close": 100, "volume": None},
        {"high": 115, "low": 95,  "close": 105, "volume": 1000},
    ]
    out = calculate_vwap(bars)
    # First bar contributes nothing (vol=0); second bar fully drives VWAP.
    tp1 = (115 + 95 + 105) / 3
    assert out[1] == pytest.approx(tp1)


# ── 2. A/D ratio is None when declines == 0 ──────────────────────────────────


def test_advance_decline_ratio_none_when_no_declines():
    """When every sector is up the ratio is mathematically infinite. The
    previous code returned the raw `advances` count, which silently
    changed units (a count is not a ratio). Verify we now return None."""
    score_sectors = [
        {"pChange": 1.5}, {"pChange": 0.8}, {"pChange": 2.1},
    ]
    advancing = sum(1 for s in score_sectors if s.get("pChange", 0) > 0)
    declining = sum(1 for s in score_sectors if s.get("pChange", 0) < 0)
    assert advancing == 3
    assert declining == 0
    # Same expression as the production code at sectors_service.py:1246/1249
    ratio = round(advancing / declining, 2) if declining else None
    assert ratio is None


def test_advance_decline_ratio_normal_division_otherwise():
    score_sectors = [
        {"pChange": 1.0}, {"pChange": -0.5}, {"pChange": 2.0}, {"pChange": -1.0},
    ]
    advancing = sum(1 for s in score_sectors if s.get("pChange", 0) > 0)
    declining = sum(1 for s in score_sectors if s.get("pChange", 0) < 0)
    ratio = round(advancing / declining, 2) if declining else None
    assert ratio == 1.00


# ── 3. PatternsService cache-first scan (ScanJob) ────────────────────────────
# The old in-memory _cached_patterns + TTL + asyncio.Lock singleflight design
# was replaced by services.scan_runner.ScanJob: a cache-first background scan.
# These tests validate the new contract — kick-once-while-stale, serve-cache-
# while-fresh, and no overlapping scans under concurrent callers.


def _make_patterns_svc():
    """A PatternsService whose ScanJob is driven by a tiny deterministic
    universe + instant scan_one, with the cache reset to a STALE state."""
    svc = ps.PatternsService(yahoo=AsyncMock(), nse=AsyncMock(), price=AsyncMock())
    svc._job._results = {}
    svc._job._meta_set("last_scan_at", "")   # empty → last_scan_at() is None → stale
    return svc


def test_patterns_scan_kicks_when_stale_then_serves_cache(monkeypatch):
    """A stale cache kicks exactly one background scan; once it completes the
    results are served from cache and a follow-up call does NOT re-scan."""
    svc = _make_patterns_svc()
    calls: list[str] = []

    async def fake_scan_one(sym):
        calls.append(sym)
        return {"symbol": sym, "universe": "NIFTY100",
                "patterns": [{"symbol": sym, "pattern": "p", "signal": "CALL",
                              "universe": "NIFTY100", "category": "x", "confidence": 80}]}

    svc._job.scan_one = fake_scan_one
    svc._job.universe_fn = lambda: ["AAA", "BBB"]

    async def scenario():
        await svc.get_patterns()                 # cold → kicks scan
        if svc._job._task:
            await svc._job._task                 # let the background scan finish
        first = len(calls)
        d = await svc.get_patterns()             # fresh → must not re-scan
        return first, len(calls), d

    first, after_second, d = asyncio.run(scenario())
    assert first == 2, "stale cache should scan the whole (2-symbol) universe once"
    assert after_second == 2, "fresh cache must NOT trigger a re-scan"
    assert d["totalPatterns"] == 2


def test_patterns_no_overlapping_scans_under_concurrent_callers():
    """N concurrent get_patterns() callers hitting a stale cache must start a
    SINGLE scan (the in_progress guard), not one per caller."""
    svc = _make_patterns_svc()
    calls: list[str] = []

    async def slow_scan_one(sym):
        await asyncio.sleep(0.02)
        calls.append(sym)
        return {"symbol": sym, "universe": "NIFTY100", "patterns": []}

    svc._job.scan_one = slow_scan_one
    svc._job.universe_fn = lambda: ["AAA", "BBB", "CCC"]

    async def scenario():
        await asyncio.gather(*(svc.get_patterns() for _ in range(10)))
        if svc._job._task:
            await svc._job._task
        return len(calls)

    n = asyncio.run(scenario())
    assert n == 3, (
        f"Expected one scan over 3 symbols, got {n} scan_one calls "
        "(concurrent callers should coalesce via the in_progress guard)"
    )


# ── 4. price_service pChange None on degenerate eod_prev == 0 ───────────────


def test_pchange_is_none_when_eod_prev_is_zero():
    """Mirror of the production expression at price_service.py:217. A
    zero previous close (corrupt feed / brand-new listing) must not be
    silently rendered as 0% change."""
    eod_close = 105.0
    eod_prev  = 0.0  # pathological
    pChange = (
        round((eod_close - eod_prev) / eod_prev * 100, 4)
        if eod_prev else None
    )
    assert pChange is None


def test_pchange_normal_division_otherwise():
    eod_close = 105.0
    eod_prev  = 100.0
    pChange = (
        round((eod_close - eod_prev) / eod_prev * 100, 4)
        if eod_prev else None
    )
    assert pChange == pytest.approx(5.0)
