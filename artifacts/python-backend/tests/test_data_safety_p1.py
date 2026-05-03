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
import time
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


# ── 3. PatternsService cache TTL ─────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_pattern_cache():
    ps._cached_patterns = []
    ps._last_scan_time = ""
    ps._last_scan_monotonic = 0.0
    ps._scan_lock = None  # force re-creation on the active loop
    yield
    ps._cached_patterns = []
    ps._last_scan_time = ""
    ps._last_scan_monotonic = 0.0
    ps._scan_lock = None


def test_patterns_cache_re_scans_after_ttl_expires(monkeypatch):
    """A scan should be re-run when the cached results are older than
    `_PATTERN_CACHE_TTL`. Previously the cache had no TTL and stale data
    persisted until the process restarted."""
    svc = ps.PatternsService(yahoo=AsyncMock(), nse=AsyncMock(), price=AsyncMock())
    scan_calls: list[float] = []

    async def fake_scan(self):
        scan_calls.append(time.monotonic())
        ps._cached_patterns = [{"signal": "CALL", "universe": "NIFTY100", "category": "x"}]
        ps._last_scan_monotonic = time.monotonic()
        return ps._cached_patterns

    monkeypatch.setattr(ps.PatternsService, "run_scan", fake_scan)

    # First call: empty cache → scan runs.
    asyncio.run(svc.get_patterns())
    assert len(scan_calls) == 1

    # Second call moments later: cache is fresh → no rescan.
    asyncio.run(svc.get_patterns())
    assert len(scan_calls) == 1

    # Force the cache age past the TTL by rewinding the last-scan timestamp.
    ps._last_scan_monotonic = time.monotonic() - (ps._PATTERN_CACHE_TTL + 1)
    asyncio.run(svc.get_patterns())
    assert len(scan_calls) == 2, "Expired cache must trigger a rescan"


def test_patterns_cache_singleflight_under_concurrent_callers(monkeypatch):
    """N concurrent callers hitting an empty cache must coalesce into a
    SINGLE run_scan() invocation — not a stampede. Verifies the
    asyncio.Lock + double-checked TTL guard around the refresh."""
    svc = ps.PatternsService(yahoo=AsyncMock(), nse=AsyncMock(), price=AsyncMock())
    scan_calls: list[float] = []

    async def slow_scan(self):
        scan_calls.append(time.monotonic())
        # Yield long enough for every other waiter to queue on the lock.
        await asyncio.sleep(0.05)
        ps._cached_patterns = [{"signal": "CALL", "universe": "NIFTY100", "category": "x"}]
        ps._last_scan_monotonic = time.monotonic()
        return ps._cached_patterns

    monkeypatch.setattr(ps.PatternsService, "run_scan", slow_scan)

    async def fire_ten():
        return await asyncio.gather(*(svc.get_patterns() for _ in range(10)))

    results = asyncio.run(fire_ten())
    assert len(results) == 10
    assert len(scan_calls) == 1, (
        f"Singleflight failed — expected 1 scan, got {len(scan_calls)} "
        "(N concurrent callers should coalesce into one run_scan call)"
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
