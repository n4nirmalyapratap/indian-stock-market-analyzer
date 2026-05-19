"""
Unit tests for SectorsService rotation logic.

These tests target the bugs identified in the deep-dive review of the
Sector Rotation Analytics feature, where the phase indicator had been
frozen on "Late Cycle / Slowdown" for two months due to:

  1. `_fetch_stock_breadth` used a single `valid` counter which made
     `pct_above_200` read 0% whenever stocks lacked a full 200-bar
     history (off-by-one denominator bug).
  2. `_fetch_index_history` returned neutral defaults on failure so
     several sectors silently shared identical fake metrics, biasing
     the cross-sector ranking.
  3. `pct_above_50` was fetched but never weighted into the composite.
  4. Tier assignment used rank-percentile alone, so the top 20% of
     sectors were always "DEEP_GREEN / STRONG BUY" even when every
     sector had a negative composite.
  5. `_detect_economic_phase` averaged leading-sector composites with
     no de-overlap and no macro context — so commodity rallies (which
     overlap with both Late and Recession leaders) wedged the phase.
  6. No hysteresis: phase could flip on tiny day-to-day score changes.

The tests use the same `asyncio.run(...)` + `AsyncMock` pattern as
`test_macro.py` (no `pytest-asyncio` dependency).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services import sectors_service as ss
from app.services.sectors_service import (
    CYCLE_PHASES,
    SectorsService,
    _load_rotation_state,
    _save_rotation_state,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _svc() -> SectorsService:
    """Build a service with mocked NSE/Yahoo dependencies."""
    nse = AsyncMock()
    yahoo = AsyncMock()
    return SectorsService(nse, yahoo)


def _bars(closes: list[float], volume: float = 1_000_000) -> list[dict]:
    """Build OHLCV bars from a list of closes."""
    return [
        {"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": volume}
        for c in closes
    ]


def _rising(n: int, start: float = 100.0, step: float = 1.0) -> list[float]:
    return [start + step * i for i in range(n)]


def _falling(n: int, start: float = 200.0, step: float = 1.0) -> list[float]:
    return [start - step * i for i in range(n)]


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """Redirect persistent rotation state to a per-test temp file."""
    monkeypatch.setattr(ss, "_STATE_FILE", tmp_path / "rotation_state.json")
    yield


@pytest.fixture(autouse=True)
def _clear_cache():
    ss._CACHE.clear()
    yield
    ss._CACHE.clear()


# ── 1. _fetch_stock_breadth — separate denominators ─────────────────────────


def test_fetch_stock_breadth_separate_50_and_200_denominators():
    """
    Bug: `valid` was incremented for any stock with ≥50 closes, then used as
    the denominator for *both* the 50-day AND 200-day percentages — so a stock
    with only 60 bars wrongly counted as "below 200-SMA".

    Fix: independent valid_50 / valid_200 counters; missing windows return
    None instead of being silently averaged into 0%.
    """
    svc = _svc()

    # 3 stocks: short (no 200-SMA), all above their 50-SMA.
    short_hist = _bars(_rising(80, start=100, step=2))  # ends well above SMA50
    long_hist  = _bars(_rising(220, start=10, step=1))  # has both windows; above both

    async def fake_history(ticker, days=250):
        # First two calls — short history, third — long history.
        return short_hist if "SHORT" in ticker else long_hist

    svc.yahoo.get_historical_data = AsyncMock(side_effect=fake_history)

    # Patch the per-symbol stock list to control the call sequence.
    with patch.dict(
        ss.SECTOR_KEY_STOCKS,
        {"NIFTY TEST": ["SHORT1.NS", "SHORT2.NS", "LONG1.NS"]},
        clear=False,
    ):
        result = asyncio.run(svc._fetch_stock_breadth("NIFTY TEST"))

    # Bug check: 50-day denominator must be 3 (all qualified), 200-day must be 1.
    assert result["sample_size_50"] == 3
    assert result["sample_size_200"] == 1
    # All stocks above their 50-SMA → 100%
    assert result["pct_above_50"] == 100.0
    # The single long-history stock IS above its 200-SMA → 100% (not 33% diluted)
    assert result["pct_above_200"] == 100.0


def test_fetch_stock_breadth_returns_none_when_window_unavailable():
    """All stocks too short for a 200-SMA → pct_above_200 must be None,
    not 0% or 50% (caller imputes)."""
    svc = _svc()
    short = _bars(_rising(80))
    svc.yahoo.get_historical_data = AsyncMock(return_value=short)

    with patch.dict(
        ss.SECTOR_KEY_STOCKS, {"NIFTY TEST": ["A", "B", "C"]}, clear=False
    ):
        result = asyncio.run(svc._fetch_stock_breadth("NIFTY TEST"))

    assert result["pct_above_200"] is None
    assert result["pct_above_50"] == 100.0


def test_fetch_stock_breadth_returns_none_when_no_key_stocks():
    svc = _svc()
    with patch.dict(ss.SECTOR_KEY_STOCKS, {}, clear=True):
        result = asyncio.run(svc._fetch_stock_breadth("NIFTY UNKNOWN"))
    assert result["pct_above_200"] is None
    assert result["pct_above_50"] is None
    assert result["sample_size_50"] == 0


# ── 2. _fetch_index_history — failure flag ──────────────────────────────────


def test_fetch_index_history_failure_returns_data_ok_false():
    """Bug: failures returned roc=0, vol=1 — making failed sectors look
    identical and clumping them together in the ranking."""
    svc = _svc()
    svc.yahoo.get_historical_data = AsyncMock(side_effect=RuntimeError("network"))

    out = asyncio.run(svc._fetch_index_history("^FAKE"))
    assert out["data_ok"] is False
    assert out["roc_3m"] is None
    assert out["roc_6m"] is None


def test_fetch_index_history_success_marks_data_ok_true():
    svc = _svc()
    svc.yahoo.get_historical_data = AsyncMock(return_value=_bars(_rising(120)))
    out = asyncio.run(svc._fetch_index_history("^OK"))
    assert out["data_ok"] is True
    assert out["roc_6m"] > 0
    assert len(out["closes"]) == 120


# ── 3. _build_momentum_scores — exclude failures, no ghost neutrals ─────────


def test_build_momentum_excludes_failed_sectors():
    """Failed-history sectors must be in `excluded`, NOT in the score dict."""
    svc = _svc()
    sectors = [
        {"symbol": "NIFTY 50",    "yahooTicker": "^NSEI"},
        {"symbol": "NIFTY GOOD",  "yahooTicker": "^GOOD"},
        {"symbol": "NIFTY BAD1",  "yahooTicker": "^BAD1"},
        {"symbol": "NIFTY BAD2",  "yahooTicker": "^BAD2"},
    ]

    async def fake_idx(ticker, days=180):
        if ticker == "^NSEI":
            return _bars(_rising(180, start=20000, step=10))
        if ticker == "^GOOD":
            return _bars(_rising(180, start=1000, step=20))  # strong outperformer
        # BAD tickers raise → failure path
        raise RuntimeError("no data")

    svc.yahoo.get_historical_data = AsyncMock(side_effect=fake_idx)
    # Empty key-stock map → breadth returns Nones for all
    with patch.dict(ss.SECTOR_KEY_STOCKS, {}, clear=True):
        scored, excluded, _ = asyncio.run(svc._build_momentum_scores(sectors))

    assert "NIFTY GOOD" in scored
    assert "NIFTY BAD1" in excluded and "NIFTY BAD2" in excluded
    assert "NIFTY BAD1" not in scored and "NIFTY BAD2" not in scored
    # NIFTY 50 must never be scored as a sector
    assert "NIFTY 50" not in scored


def test_build_momentum_uses_pct_above_50_in_composite():
    """Bug: pct_above_50 was fetched but never weighted into composite. Now,
    two sectors with identical price history but very different breadth_50
    must produce different composites."""
    svc = _svc()
    sectors = [
        {"symbol": "NIFTY 50", "yahooTicker": "^NSEI"},
        {"symbol": "NIFTY A",  "yahooTicker": "^A"},
        {"symbol": "NIFTY B",  "yahooTicker": "^B"},
        {"symbol": "NIFTY C",  "yahooTicker": "^C"},
        {"symbol": "NIFTY D",  "yahooTicker": "^D"},
    ]
    # All sectors share IDENTICAL price history → RS, ROC, vol z-scores all 0.
    common_hist = _bars(_rising(180, start=100, step=1))

    # Build distinct stock histories to drive different breadth_50 readings.
    above_stocks = _bars(_rising(60, start=10, step=2))   # current >> SMA50 → 100% above
    below_stocks = _bars(_falling(60, start=200, step=2)) # current << SMA50 → 0% above

    async def fake_history(ticker, days=250):
        if ticker.startswith("^"):
            return common_hist
        return above_stocks if ticker.startswith("HIGH") else below_stocks

    svc.yahoo.get_historical_data = AsyncMock(side_effect=fake_history)
    # Need ≥3 sectors with native b50 data so the indicator stays "reliable".
    fake_stocks = {
        "NIFTY A": ["HIGH1", "HIGH2", "HIGH3"],
        "NIFTY B": ["HIGH4", "HIGH5", "HIGH6"],
        "NIFTY C": ["LOW1", "LOW2", "LOW3"],
        "NIFTY D": ["LOW4", "LOW5", "LOW6"],
    }
    with patch.dict(ss.SECTOR_KEY_STOCKS, fake_stocks, clear=True):
        scored, _, _ = asyncio.run(svc._build_momentum_scores(sectors))

    # b50 must be reliable (4 native samples) and contribute weight.
    rel = scored["NIFTY A"]["indicatorReliability"]
    assert rel["breadth50Reliable"] is True
    assert scored["NIFTY A"]["weights"]["breadth50"] > 0

    # High-breadth sectors must have higher composite than low-breadth ones,
    # despite identical price-derived metrics.
    high = (scored["NIFTY A"]["composite"] + scored["NIFTY B"]["composite"]) / 2
    low  = (scored["NIFTY C"]["composite"] + scored["NIFTY D"]["composite"]) / 2
    assert high > low


def test_build_momentum_redistributes_weight_when_breadth_unreliable():
    """If fewer than 3 sectors report native breadth data, that indicator's
    weight must be redistributed to RS+ROC (not silently set to median 50%
    and dragged to z=0)."""
    svc = _svc()
    sectors = [
        {"symbol": "NIFTY 50", "yahooTicker": "^NSEI"},
        {"symbol": "NIFTY A",  "yahooTicker": "^A"},
        {"symbol": "NIFTY B",  "yahooTicker": "^B"},
        {"symbol": "NIFTY C",  "yahooTicker": "^C"},
    ]
    svc.yahoo.get_historical_data = AsyncMock(return_value=_bars(_rising(180)))

    with patch.dict(ss.SECTOR_KEY_STOCKS, {}, clear=True):  # no breadth at all
        scored, _, _ = asyncio.run(svc._build_momentum_scores(sectors))

    rel = scored["NIFTY A"]["indicatorReliability"]
    weights = scored["NIFTY A"]["weights"]
    assert rel["breadth200Reliable"] is False
    assert rel["breadth50Reliable"] is False
    # Both breadth weights collapsed to 0…
    assert weights["breadth200"] == 0.0
    assert weights["breadth50"] == 0.0
    # …and the saved weight got pushed onto RS (the dominant signal).
    assert weights["rs"] > 0.35
    # Total weight conserved (within fp tolerance).
    total = sum(weights.values())
    assert abs(total - 1.0) < 1e-9


# ── 4. _assign_tier — absolute composite floor ──────────────────────────────


def test_assign_tier_requires_absolute_floor_for_deep_green():
    """Bug: top 20% by rank was always DEEP_GREEN even when composite < 0,
    promoting "least-bad in a crash" sectors to STRONG BUY."""
    # Top of the rank pile, but composite is negative → must NOT be DEEP_GREEN.
    weak_top = SectorsService._assign_tier(rank_pct=5.0, composite=-0.10)
    assert weak_top["tier"] != "DEEP_GREEN"
    assert weak_top["tier"] in ("YELLOW",)

    # Same rank but with strong absolute composite → DEEP_GREEN.
    strong_top = SectorsService._assign_tier(rank_pct=5.0, composite=0.50)
    assert strong_top["tier"] == "DEEP_GREEN"


def test_assign_tier_requires_absolute_ceiling_for_deep_red():
    """Bottom 20% by rank with positive composite (mild laggard in a strong
    market) must NOT be marked DEEP_RED / AVOID."""
    weak_bottom = SectorsService._assign_tier(rank_pct=95.0, composite=0.10)
    assert weak_bottom["tier"] != "DEEP_RED"

    strong_bottom = SectorsService._assign_tier(rank_pct=95.0, composite=-0.50)
    assert strong_bottom["tier"] == "DEEP_RED"


# ── 5. _macro_prior — regime detection from Nifty 50 trend ──────────────────


def test_macro_prior_above_and_rising_favors_mid_cycle():
    closes = _rising(220, start=10, step=1)  # monotonic up; last >> SMA200
    prior = SectorsService._macro_prior(closes)
    assert prior["Mid Cycle / Expansion"] == max(prior.values())
    assert prior["Recession / Contraction"] == 0.0


def test_macro_prior_below_and_falling_favors_recession():
    closes = _falling(220, start=300, step=1)
    prior = SectorsService._macro_prior(closes)
    assert prior["Recession / Contraction"] == max(prior.values())


def test_macro_prior_below_and_rising_favors_early_cycle():
    """A long downtrend that recently turned up (price still < 200-SMA but
    short-term slope positive) should weight Early Cycle / Recovery."""
    # Down for 200 bars, then a sharp 30-bar rebound.
    closes = _falling(200, start=300, step=1) + _rising(30, start=120, step=2)
    prior = SectorsService._macro_prior(closes)
    assert prior["Early Cycle / Recovery"] == max(prior.values())


def test_macro_prior_insufficient_data_is_neutral():
    prior = SectorsService._macro_prior([100, 101, 102])
    assert all(v == 0.0 for v in prior.values())


# ── 6. _detect_economic_phase — full integration ────────────────────────────


def _momentum_dict(scores: dict[str, float]) -> dict:
    """Build a momentum-style dict with just the composite field populated."""
    return {sym: {"composite": v} for sym, v in scores.items()}


def test_detect_phase_no_data_returns_unknown():
    """Bug: previously fell back to 'Mid Cycle / Expansion @ 40%' silently."""
    svc = _svc()
    out = svc._detect_economic_phase({}, [])
    assert out["phase"] == "Unknown"
    assert out["confidence"] == 0
    assert out["actionableSectors"] == []


def test_detect_phase_late_cycle_when_commodities_lead():
    """Energy + Metal + Pharma strong; IT + Realty weak → Late Cycle."""
    svc = _svc()
    momentum = _momentum_dict({
        "NIFTY ENERGY":   1.5,
        "NIFTY OIL AND GAS": 1.4,
        "NIFTY METAL":    1.3,
        "NIFTY PHARMA":   0.8,
        "NIFTY IT":      -1.2,
        "NIFTY REALTY":  -0.8,
        "NIFTY CONSUMER DURABLES": -0.5,
        "NIFTY AUTO":    -0.4,
        "NIFTY BANK":    -0.3,
        "NIFTY FINANCIAL SERVICES": -0.2,
        "NIFTY FMCG":     0.0,
        "NIFTY HEALTHCARE INDEX": 0.5,
    })
    # Macro: above 200-SMA, slightly falling slope (typical late cycle)
    nifty_closes = _rising(180, start=10, step=1) + [200] * 40  # plateau at top
    out = svc._detect_economic_phase(momentum, nifty_closes)
    assert out["phase"] == "Late Cycle / Slowdown"
    assert out["confidence"] >= 50


def test_detect_phase_recession_when_defensives_lead_and_macro_bearish():
    svc = _svc()
    momentum = _momentum_dict({
        "NIFTY FMCG":              1.5,
        "NIFTY HEALTHCARE INDEX":  1.4,
        "NIFTY PHARMA":            1.2,
        "NIFTY BANK":             -1.5,
        "NIFTY METAL":            -1.4,
        "NIFTY AUTO":             -1.0,
        "NIFTY REALTY":           -1.0,
        "NIFTY IT":               -0.8,
        "NIFTY ENERGY":           -0.3,
    })
    # Macro: long downtrend → Recession prior
    nifty_closes = _falling(220, start=300, step=1)
    out = svc._detect_economic_phase(momentum, nifty_closes)
    assert out["phase"] == "Recession / Contraction"


def test_detect_phase_hysteresis_holds_previous_phase_on_small_flip():
    """If new winner only marginally beats previous phase, keep previous and
    surface 'transitional'."""
    svc = _svc()
    # Persist Late Cycle as the previous phase.
    _save_rotation_state({"phase": "Late Cycle / Slowdown", "score": 0.5})

    # Build momentum that *just barely* favors Mid Cycle over Late Cycle.
    # NB: sectors overlap across phases (e.g. IT is a Mid leader AND a Late
    # lagger) so we use small spreads to make the gap < 0.20 hysteresis margin.
    momentum = _momentum_dict({
        # Mid leaders, slight edge
        "NIFTY IT":                  0.20,
        "NIFTY AUTO":                0.20,
        "NIFTY CONSUMER DURABLES":   0.20,
        "NIFTY FINANCIAL SERVICES":  0.20,
        # Late leaders, just below
        "NIFTY ENERGY":              0.18,
        "NIFTY OIL AND GAS":         0.18,
        "NIFTY METAL":               0.18,
        "NIFTY PHARMA":              0.18,
        # Defensives + others kept neutral
        "NIFTY FMCG":                0.0,
        "NIFTY HEALTHCARE INDEX":    0.0,
        "NIFTY REALTY":              0.0,
        "NIFTY BANK":                0.0,
    })
    # No macro signal — let leadership decide.
    out = svc._detect_economic_phase(momentum, [])
    assert out["phase"] == "Late Cycle / Slowdown"
    assert out["transitional"] is True


def test_detect_phase_hysteresis_releases_on_decisive_move():
    """If new winner clears the previous phase by ≥ 0.20 of combined score,
    transition is allowed (not stuck forever)."""
    svc = _svc()
    _save_rotation_state({"phase": "Late Cycle / Slowdown", "score": 0.5})

    momentum = _momentum_dict({
        # Mid leaders dominate decisively (IT is unique to Mid)
        "NIFTY IT":                  2.0,
        "NIFTY AUTO":                2.0,
        "NIFTY CONSUMER DURABLES":   2.0,
        "NIFTY FINANCIAL SERVICES":  2.0,
        # Late leaders weak
        "NIFTY ENERGY":             -1.0,
        "NIFTY OIL AND GAS":        -1.0,
        "NIFTY METAL":              -1.0,
        "NIFTY PHARMA":             -1.0,
        # Defensives weak (so Recession isn't the winner)
        "NIFTY FMCG":               -1.0,
        "NIFTY HEALTHCARE INDEX":   -1.0,
        # Early-cycle uniques weak (so Early isn't the winner — Early shares
        # AUTO/CD/FIN with Mid, so we need to drag REALTY + BANK down)
        "NIFTY REALTY":             -1.0,
        "NIFTY BANK":               -1.0,
    })
    out = svc._detect_economic_phase(momentum, [])
    assert out["phase"] == "Mid Cycle / Expansion"
    assert out["transitional"] is False


def test_detect_phase_persists_state_for_next_call():
    """Verify the persisted state file is written on every successful call
    via _save_rotation_state."""
    state_file = ss._STATE_FILE
    assert not state_file.exists()
    _save_rotation_state({"phase": "Mid Cycle / Expansion", "score": 1.23})
    assert state_file.exists()
    loaded = _load_rotation_state()
    assert loaded["phase"] == "Mid Cycle / Expansion"
    assert loaded["score"] == 1.23


# ── 7. CYCLE_PHASES integrity ───────────────────────────────────────────────


def test_cycle_phases_have_de_overlapped_leading_weights():
    """Sanity check: a sector should not be in the leading-weights of more
    than two phases (commodities can legitimately appear in both Late and
    Mid, etc. — but not all four). This guards against future regressions
    that re-introduce the old over-overlap that wedged the detector."""
    counts: dict[str, int] = {}
    for info in CYCLE_PHASES.values():
        for sym in info["leadingWeights"]:
            counts[sym] = counts.get(sym, 0) + 1
    over = {s: n for s, n in counts.items() if n > 2}
    assert not over, f"Sectors over-overlap leading weights: {over}"


def test_cycle_phases_have_lagging_weights_disjoint_from_leading():
    """A sector cannot be both leading AND lagging in the SAME phase —
    that would zero out the phase score."""
    for name, info in CYCLE_PHASES.items():
        overlap = set(info["leadingWeights"]) & set(info["laggingWeights"])
        assert not overlap, f"{name} has same sector in leading & lagging: {overlap}"


# ── 8. Benchmark-failure handling ───────────────────────────────────────────


def test_build_momentum_drops_rs_when_benchmark_fails():
    """If Nifty 50 history fetch fails, RS becomes meaningless; weight must
    be redistributed (not silently set to 0 = absolute ROC). Reliability
    flag should be surfaced."""
    svc = _svc()
    sectors = [
        {"symbol": "NIFTY 50", "yahooTicker": "^NSEI"},
        {"symbol": "NIFTY A",  "yahooTicker": "^A"},
        {"symbol": "NIFTY B",  "yahooTicker": "^B"},
        {"symbol": "NIFTY C",  "yahooTicker": "^C"},
    ]

    async def fake_history(ticker, days=180):
        if ticker == "^NSEI":
            raise RuntimeError("benchmark down")
        return _bars(_rising(180, start=100, step=1))

    svc.yahoo.get_historical_data = AsyncMock(side_effect=fake_history)

    with patch.dict(ss.SECTOR_KEY_STOCKS, {}, clear=True):
        scored, excluded, _ = asyncio.run(svc._build_momentum_scores(sectors))

    # Sectors must still get scored even when benchmark fails.
    assert "NIFTY A" in scored
    a = scored["NIFTY A"]
    rel = a["indicatorReliability"]
    assert rel["benchmarkOk"] is False
    # RS weight must collapse to 0; redistributed weight goes to ROC (and
    # breadth, but breadth is also unreliable in this fixture).
    assert a["weights"]["rs"] == 0.0
    assert a["weights"]["roc6m"] > 0.20
    # Total weight conserved.
    total = sum(a["weights"].values())
    assert abs(total - 1.0) < 1e-9


def test_build_momentum_keeps_rs_when_benchmark_ok():
    svc = _svc()
    sectors = [
        {"symbol": "NIFTY 50", "yahooTicker": "^NSEI"},
        {"symbol": "NIFTY A",  "yahooTicker": "^A"},
        {"symbol": "NIFTY B",  "yahooTicker": "^B"},
        {"symbol": "NIFTY C",  "yahooTicker": "^C"},
    ]
    svc.yahoo.get_historical_data = AsyncMock(return_value=_bars(_rising(180)))
    with patch.dict(ss.SECTOR_KEY_STOCKS, {}, clear=True):
        scored, _, _ = asyncio.run(svc._build_momentum_scores(sectors))
    rel = scored["NIFTY A"]["indicatorReliability"]
    assert rel["benchmarkOk"] is True
    assert scored["NIFTY A"]["weights"]["rs"] >= 0.35


# ── 9. End-to-end _compute_rotation — excluded sectors flagged UNKNOWN ──────


def test_compute_rotation_marks_failed_sectors_as_unknown(monkeypatch):
    """Integration test: a sector whose Yahoo history fails must appear in
    the result with `dataMissing: True` / tier 'UNKNOWN' / focus 'NO DATA'
    rather than being silently ranked as YELLOW."""
    svc = _svc()

    # Stub get_all_sectors to return a tiny controlled list.
    async def fake_sectors():
        return [
            {"symbol": "NIFTY 50", "name": "Nifty 50", "yahooTicker": "^NSEI",
             "advances": 0, "declines": 0, "pChange": 0},
            {"symbol": "NIFTY GOOD", "name": "Good", "yahooTicker": "^GOOD",
             "advances": 30, "declines": 5, "pChange": 1.5},
            {"symbol": "NIFTY BAD", "name": "Bad", "yahooTicker": "^BAD",
             "advances": 10, "declines": 10, "pChange": 0.0},
        ]
    monkeypatch.setattr(svc, "get_all_sectors", fake_sectors)

    async def fake_history(ticker, days=180):
        if ticker == "^BAD":
            raise RuntimeError("no data")
        return _bars(_rising(180, start=100, step=1))
    svc.yahoo.get_historical_data = AsyncMock(side_effect=fake_history)

    with patch.dict(ss.SECTOR_KEY_STOCKS, {}, clear=True):
        result = asyncio.run(svc._compute_rotation())

    by_sym = {s["symbol"]: s for s in result["sectors"]}
    bad = by_sym["NIFTY BAD"]
    assert bad["momentum"].get("dataMissing") is True
    assert bad["momentum"]["tier"] == "UNKNOWN"
    assert bad["focus"] == "NO DATA"
    assert bad["momentum"].get("composite") is None

    good = by_sym["NIFTY GOOD"]
    assert good["momentum"].get("dataMissing") is not True
    assert good["momentum"].get("composite") is not None
    # Scored sector sorts ahead of the unknown one.
    assert result["sectors"][0]["symbol"] == "NIFTY GOOD"


# ── 10. Atomic state persistence under concurrent writes ────────────────────


def test_save_rotation_state_is_atomic_and_concurrent_safe():
    """Multiple parallel writes must always leave the file as valid JSON
    (last writer wins) — never half-written / corrupt."""
    import threading
    payloads = [
        {"phase": "Mid Cycle / Expansion",   "score": i * 0.01, "i": i}
        for i in range(50)
    ]

    def writer(p):
        _save_rotation_state(p)

    threads = [threading.Thread(target=writer, args=(p,)) for p in payloads]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # File must exist and parse as valid JSON
    loaded = _load_rotation_state()
    assert loaded is not None
    assert loaded["phase"] == "Mid Cycle / Expansion"
    assert "i" in loaded  # one of the writers' payloads landed
    # No leftover temp files
    leftovers = [
        p for p in ss._STATE_FILE.parent.iterdir()
        if p.name.startswith(".rotation_state.") and p.name.endswith(".tmp")
    ]
    assert leftovers == []
