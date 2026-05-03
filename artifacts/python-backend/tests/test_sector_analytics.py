"""
Unit tests for SectorAnalyticsService.

Covers the data-quality bugs discovered during the heatmap + sector-detail
deep-dive review:

  1. `_yf_info` returned 0 for missing price/change1d/marketCap, which
     silently rendered as "₹0" / "0.00%" and ranked failed-fetch stocks
     as flat in Top Gainers/Losers.
  2. `debtToEquity` from Yahoo is in percent form (50 = 0.5×). The
     backend stored the raw value, so a real D/E of 0.5× rendered as
     "50.00×" — critical misrepresentation.
  3. The heatmap fallback used `_pct_change_from_history(...) or fb.get(...)`
     so a legitimate flat day (0.0%) was clobbered by the constituent
     average.
  4. Constituent stock prices/change1d came directly from Yahoo Finance,
     bypassing the canonical PriceService, so the sector detail could
     contradict the same stock's price elsewhere in the app.

Async tests use `asyncio.run` + `AsyncMock` (no pytest-asyncio).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import sector_analytics_service as sas
from app.services.sector_analytics_service import SectorAnalyticsService


# ── Cache reset ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_cache():
    sas._CACHE.clear()
    yield
    sas._CACHE.clear()


# ── 1. _yf_info: missing fields → None, not 0 ────────────────────────────────


def test_yf_info_returns_none_on_yahoo_failure():
    """yfinance throws → every numeric is None (not 0), so the UI renders '—'."""

    class _RaisingTicker:
        def __init__(self, *_a, **_kw): raise RuntimeError("yahoo down")

    with patch.object(sas.yf, "Ticker", _RaisingTicker):
        info = asyncio.run(sas._yf_info("RELIANCE.NS"))

    assert info["price"]      is None
    assert info["change1d"]   is None
    assert info["marketCap"]  is None
    assert info["pe"]         is None
    assert info["debtToEquity"] is None
    # symbol is preserved so the row still appears in the table as "—" placeholders
    assert info["symbol"] == "RELIANCE.NS"


def test_yf_info_missing_price_keeps_none_not_zero():
    """When yfinance returns an info dict with no price keys, we must keep None."""

    class _Ticker:
        def __init__(self, *_a, **_kw): pass
        @property
        def info(self): return {"longName": "Reliance"}

    with patch.object(sas.yf, "Ticker", _Ticker):
        info = asyncio.run(sas._yf_info("RELIANCE.NS"))

    assert info["price"]    is None      # not 0
    assert info["change1d"] is None      # not 0
    assert info["marketCap"] is None     # not 0
    assert info["name"] == "Reliance"


# ── 2. debtToEquity converted from percent to ratio ──────────────────────────


def test_yf_info_converts_debt_to_equity_to_ratio():
    """Yahoo reports D/E as a percentage (e.g. 50 means 0.5×). Backend must divide by 100."""

    class _Ticker:
        def __init__(self, *_a, **_kw): pass
        @property
        def info(self):
            return {
                "longName": "HDFC Bank", "currentPrice": 1500,
                "debtToEquity": 152.4,   # Yahoo: 152.4% → 1.524× ratio
                "trailingPE": 18.0,
            }

    with patch.object(sas.yf, "Ticker", _Ticker):
        info = asyncio.run(sas._yf_info("HDFCBANK.NS"))

    assert info["debtToEquity"] == pytest.approx(1.524, rel=1e-6)
    # sanity: other fields untouched
    assert info["price"] == 1500
    assert info["pe"]    == 18.0


def test_yf_info_debt_to_equity_none_when_yahoo_missing():
    class _Ticker:
        def __init__(self, *_a, **_kw): pass
        @property
        def info(self): return {"longName": "X"}

    with patch.object(sas.yf, "Ticker", _Ticker):
        info = asyncio.run(sas._yf_info("X.NS"))
    assert info["debtToEquity"] is None


# ── 3. Heatmap fallback uses None-check, not falsy `or` ──────────────────────


def test_heatmap_preserves_legit_zero_change():
    """A legit 0.0% change (flat day) must NOT be replaced by the constituent fallback."""
    svc = SectorAnalyticsService(yahoo=MagicMock(), price=None)
    today = "2026-05-03"

    # Build a 1-year history where today's close == 5 days ago close → 0.00% 1W
    base = 1000.0
    hist = []
    for i in range(260):
        # date doesn't matter for _pct_change_from_history; only used for YTD
        hist.append({"date": f"2025-{(i % 12) + 1:02d}-01", "close": base})
    # last 5 closes flat
    hist[-5:] = [{"date": "2026-05-01", "close": base}] * 5
    hist[-1]  = {"date": today, "close": base}  # today close
    hist[-6]  = {"date": "2026-04-25", "close": base}

    fallback_payload = {
        "change1w": 99.0, "change1m": 99.0, "change1y": 99.0, "changeYTD": 99.0,
    }

    sectors_live = [{"symbol": "NIFTY BANK", "name": "Nifty Bank", "category": "Banks",
                     "lastPrice": 1000, "pChange": 0.0, "advances": 10, "declines": 5}]

    async def _fake_history(_t, _p="1y"): return hist
    async def _fake_constituent_pct(_c): return fallback_payload

    with patch.object(sas, "_yf_history", side_effect=_fake_history), \
         patch.object(sas, "_constituent_pct_changes", side_effect=_fake_constituent_pct):
        out = asyncio.run(svc.get_heatmap(sectors_live))

    row = next(r for r in out if r["symbol"] == "NIFTY BANK")
    # 1W change came from history → 0.0%, MUST NOT be overwritten by 99.0% fallback
    assert row["change1w"] == 0.0


def test_heatmap_uses_fallback_when_history_unavailable():
    """When yfinance index history is empty, fallback values must be used."""
    svc = SectorAnalyticsService(yahoo=MagicMock(), price=None)
    fallback_payload = {"change1w": 1.5, "change1m": 4.0, "change1y": 22.0, "changeYTD": 8.0}
    sectors_live = [{"symbol": "NIFTY BANK", "name": "Nifty Bank", "category": "Banks",
                     "lastPrice": 1000, "pChange": 0.5, "advances": 10, "declines": 5}]

    async def _fake_history(_t, _p="1y"): return []
    async def _fake_constituent_pct(_c): return fallback_payload

    with patch.object(sas, "_yf_history", side_effect=_fake_history), \
         patch.object(sas, "_constituent_pct_changes", side_effect=_fake_constituent_pct):
        out = asyncio.run(svc.get_heatmap(sectors_live))

    row = next(r for r in out if r["symbol"] == "NIFTY BANK")
    assert row["change1w"]  == 1.5
    assert row["change1m"]  == 4.0
    assert row["change1y"]  == 22.0
    assert row["changeYTD"] == 8.0


# ── 4. Canonical PriceService overlay on constituent prices ──────────────────


def _stub_yf_info_for(*infos: dict):
    """Create a side-effect that returns the given info dicts in call order."""
    iterator = iter(infos)

    async def _side_effect(_ticker):
        try:
            return next(iterator)
        except StopIteration:
            return {"symbol": _ticker, "price": None}

    return _side_effect


def test_constituent_prices_overlaid_with_canonical_quote():
    """When PriceService returns a quote, sector-detail must use those values
    instead of the yfinance Ticker.info values — so the table never contradicts
    Stock Lookup / Charts / Portfolio."""
    price = AsyncMock()
    # Canonical quote for HDFCBANK — different price/pChange from yfinance
    price.get_quote_with_meta.return_value = {
        "quote": {"lastPrice": 1650.5, "pChange": 1.25, "previousClose": 1630.1},
        "source": "NSE",
    }

    svc = SectorAnalyticsService(yahoo=MagicMock(), price=price)

    yf_payload = {
        "symbol": "HDFCBANK.NS", "name": "HDFC Bank",
        "price": 1500.0,            # stale yfinance
        "change1d": -0.30,           # stale yfinance
        "marketCap": 1.2e13, "pe": 18.0, "pb": 2.5, "ps": None, "evEbitda": None,
        "roe": 0.15, "roa": 0.012, "earningsGrowth": 0.08, "revenueGrowth": 0.10,
        "debtToEquity": 1.5, "netMargin": 0.20, "dividendYield": 0.01, "beta": 0.8,
        "sector": "Financial", "industry": "Banks",
    }

    async def _fake_history(*_a, **_kw): return [{"date": "2025-01-01", "close": 1.0}] * 30

    with patch.object(sas, "_yf_info", side_effect=_stub_yf_info_for(yf_payload)), \
         patch.object(sas, "_yf_history", side_effect=_fake_history), \
         patch.dict(sas.SECTOR_CONSTITUENTS, {"NIFTY BANK": ["HDFCBANK.NS"]}, clear=False), \
         patch.dict(sas.SECTOR_YAHOO_TICKER, {"NIFTY BANK": "^NSEBANK"}, clear=False):
        result = asyncio.run(svc.get_sector_detail("NIFTY BANK", "1y"))

    assert result is not None
    row = next(c for c in result["constituents"] if c["symbol"] == "HDFCBANK.NS")

    # Canonical price wins
    assert row["price"]    == pytest.approx(1650.5)
    assert row["change1d"] == pytest.approx(1.25)
    assert row["priceSource"] == "NSE"
    # Fundamentals from yfinance are preserved
    assert row["pe"]  == 18.0
    assert row["roe"] == 0.15
    # And D/E was already stored as ratio (test #2 covers conversion)
    assert row["debtToEquity"] == 1.5

    # PriceService called with the *bare* symbol (no .NS)
    price.get_quote_with_meta.assert_awaited_with("HDFCBANK")


def test_constituent_overlay_keeps_yfinance_change_when_canonical_pchange_missing():
    """Canonical quote may have a `lastPrice` but no `pChange` (e.g. NSE feed
    momentarily missing the change field). We must NOT overwrite the
    yfinance change1d with None — that would replace real data with a gap."""
    price = AsyncMock()
    price.get_quote_with_meta.return_value = {
        "quote": {"lastPrice": 1650.5, "pChange": None, "previousClose": None},
        "source": "NSE",
    }
    svc = SectorAnalyticsService(yahoo=MagicMock(), price=price)
    yf_payload = {
        "symbol": "HDFCBANK.NS", "name": "HDFC Bank",
        "price": 1500.0, "change1d": -0.30, "marketCap": 1e13,
        "pe": 18.0, "pb": None, "ps": None, "evEbitda": None,
        "roe": None, "roa": None, "earningsGrowth": None, "revenueGrowth": None,
        "debtToEquity": None, "netMargin": None, "dividendYield": None,
        "beta": None, "sector": None, "industry": None,
    }
    async def _fake_history(*_a, **_kw): return [{"date": "2025-01-01", "close": 1.0}] * 30

    with patch.object(sas, "_yf_info", side_effect=_stub_yf_info_for(yf_payload)), \
         patch.object(sas, "_yf_history", side_effect=_fake_history), \
         patch.dict(sas.SECTOR_CONSTITUENTS, {"NIFTY BANK": ["HDFCBANK.NS"]}, clear=False), \
         patch.dict(sas.SECTOR_YAHOO_TICKER, {"NIFTY BANK": "^NSEBANK"}, clear=False):
        result = asyncio.run(svc.get_sector_detail("NIFTY BANK", "1y"))

    row = next(c for c in result["constituents"] if c["symbol"] == "HDFCBANK.NS")
    assert row["price"]    == pytest.approx(1650.5)   # canonical price wins
    assert row["change1d"] == pytest.approx(-0.30)    # yfinance change preserved


# ── 6. Valuation sampleSize reflects actual contributors ─────────────────────


def test_valuation_sample_size_counts_contributors_not_total():
    """`sampleSize` must reflect how many constituents contributed to the
    headline P/E — not the total number of stocks pulled, since stocks with
    missing/negative earnings are excluded from the cap-weighted average."""
    svc = SectorAnalyticsService(yahoo=MagicMock(), price=None)
    stocks = [
        {"marketCap": 1e10, "pe": 20.0, "pb": 3.0,  "ps": 2.0, "evEbitda": 10.0},
        {"marketCap": 5e9,  "pe": None, "pb": 2.0,  "ps": None, "evEbitda": 8.0},   # no P/E
        {"marketCap": 2e9,  "pe": -5.0, "pb": None, "ps": 1.5,  "evEbitda": None},   # negative P/E excluded
        {"marketCap": 0,    "pe": 15.0, "pb": 1.5,  "ps": 1.0,  "evEbitda": 6.0},    # zero cap excluded
    ]
    v = svc._compute_valuation(stocks)
    assert v["peSampleSize"] == 1            # only the first stock contributes
    assert v["pbSampleSize"] == 2
    assert v["psSampleSize"] == 2
    assert v["evEbitdaSampleSize"] == 2
    # Headline sampleSize is the strongest contributor (P/E)
    assert v["sampleSize"] == 1


def test_constituent_overlay_falls_back_to_yfinance_when_canonical_missing():
    price = AsyncMock()
    price.get_quote_with_meta.return_value = None  # NSE lookup failed

    svc = SectorAnalyticsService(yahoo=MagicMock(), price=price)

    yf_payload = {
        "symbol": "HDFCBANK.NS", "name": "HDFC Bank",
        "price": 1500.0, "change1d": -0.30, "marketCap": 1e13,
        "pe": 18.0, "pb": None, "ps": None, "evEbitda": None,
        "roe": None, "roa": None, "earningsGrowth": None, "revenueGrowth": None,
        "debtToEquity": None, "netMargin": None, "dividendYield": None,
        "beta": None, "sector": None, "industry": None,
    }

    async def _fake_history(*_a, **_kw): return [{"date": "2025-01-01", "close": 1.0}] * 30

    with patch.object(sas, "_yf_info", side_effect=_stub_yf_info_for(yf_payload)), \
         patch.object(sas, "_yf_history", side_effect=_fake_history), \
         patch.dict(sas.SECTOR_CONSTITUENTS, {"NIFTY BANK": ["HDFCBANK.NS"]}, clear=False), \
         patch.dict(sas.SECTOR_YAHOO_TICKER, {"NIFTY BANK": "^NSEBANK"}, clear=False):
        result = asyncio.run(svc.get_sector_detail("NIFTY BANK", "1y"))

    row = next(c for c in result["constituents"] if c["symbol"] == "HDFCBANK.NS")
    # Falls back to yfinance values
    assert row["price"]    == 1500.0
    assert row["change1d"] == -0.30
    assert row["priceSource"] is None  # not overlaid


# ── 7. Empty rows are dropped from constituent table ─────────────────────────


def test_constituents_table_drops_pure_failure_rows():
    """If a constituent yfinance call fails completely AND the canonical
    PriceService also has no data, the row would be all '—'s. Filter it out
    so wrong/delisted tickers in our SECTOR_CONSTITUENTS list don't pollute
    the table with useless rows."""
    price = AsyncMock()
    price.get_quote_with_meta.return_value = None  # canonical also failed

    svc = SectorAnalyticsService(yahoo=MagicMock(), price=price)

    payloads = [
        {"symbol": "GOOD.NS", "name": "Good", "price": 100, "change1d": 1.5,
         "marketCap": 1e10, "pe": 10, "pb": 1, "ps": 1, "evEbitda": 5,
         "roe": 0.1, "roa": 0.05, "earningsGrowth": 0.1, "revenueGrowth": 0.1,
         "debtToEquity": 0.5, "netMargin": 0.1, "dividendYield": 0.01,
         "beta": 1, "sector": None, "industry": None},
        # Pure failure shell (delisted/wrong ticker) — should be dropped
        {"symbol": "DEAD.NS", "name": "DEAD.NS", "price": None, "change1d": None,
         "marketCap": None, "pe": None, "pb": None, "ps": None, "evEbitda": None,
         "roe": None, "roa": None, "earningsGrowth": None, "revenueGrowth": None,
         "debtToEquity": None, "netMargin": None, "dividendYield": None,
         "beta": None, "sector": None, "industry": None},
    ]

    async def _fake_history(*_a, **_kw): return [{"date": "2025-01-01", "close": 1.0}] * 30

    with patch.object(sas, "_yf_info", side_effect=_stub_yf_info_for(*payloads)), \
         patch.object(sas, "_yf_history", side_effect=_fake_history), \
         patch.dict(sas.SECTOR_CONSTITUENTS, {"NIFTY BANK": ["GOOD.NS", "DEAD.NS"]}, clear=False), \
         patch.dict(sas.SECTOR_YAHOO_TICKER, {"NIFTY BANK": "^NSEBANK"}, clear=False):
        result = asyncio.run(svc.get_sector_detail("NIFTY BANK", "1y"))

    syms = [c["symbol"] for c in result["constituents"]]
    assert syms == ["GOOD.NS"]   # DEAD.NS dropped


# ── 8. historySynthetic flag surfaces when index history is unavailable ──────


def test_history_synthetic_flag_set_when_index_history_empty():
    """When yfinance has no index history (e.g. delisted ^CNXOILGAS), we
    fall back to a synthetic equal-weight series. The response must surface
    a `historySynthetic` flag so the UI can disclose the approximation."""
    price = AsyncMock()
    price.get_quote_with_meta.return_value = None

    svc = SectorAnalyticsService(yahoo=MagicMock(), price=price)

    yf_payload = {
        "symbol": "X.NS", "name": "X", "price": 100, "change1d": 0.0,
        "marketCap": 1e9, "pe": 10, "pb": 1, "ps": 1, "evEbitda": 5,
        "roe": 0.1, "roa": 0.05, "earningsGrowth": 0.1, "revenueGrowth": 0.1,
        "debtToEquity": 0.5, "netMargin": 0.1, "dividendYield": 0.01,
        "beta": 1, "sector": None, "industry": None,
    }

    call_count = {"n": 0}
    async def _fake_history(ticker, _p="1y"):
        call_count["n"] += 1
        # First call is for the sector index (empty), subsequent calls are
        # for synthetic-history reconstruction (return real bars).
        if ticker.startswith("^"):
            return []
        return [{"date": f"2025-{(i%12)+1:02d}-01", "close": 100 + i} for i in range(60)]

    with patch.object(sas, "_yf_info", side_effect=_stub_yf_info_for(yf_payload)), \
         patch.object(sas, "_yf_history", side_effect=_fake_history), \
         patch.dict(sas.SECTOR_CONSTITUENTS, {"NIFTY OIL AND GAS": ["X.NS"]}, clear=False), \
         patch.dict(sas.SECTOR_YAHOO_TICKER, {"NIFTY OIL AND GAS": "^CNXOILGAS"}, clear=False):
        result = asyncio.run(svc.get_sector_detail("NIFTY OIL AND GAS", "1y"))

    assert result["historySynthetic"] is True


def test_history_synthetic_flag_false_when_index_history_present():
    price = AsyncMock()
    price.get_quote_with_meta.return_value = None
    svc = SectorAnalyticsService(yahoo=MagicMock(), price=price)
    yf_payload = {
        "symbol": "X.NS", "name": "X", "price": 100, "change1d": 0.0,
        "marketCap": 1e9, "pe": 10, "pb": 1, "ps": 1, "evEbitda": 5,
        "roe": 0.1, "roa": 0.05, "earningsGrowth": 0.1, "revenueGrowth": 0.1,
        "debtToEquity": 0.5, "netMargin": 0.1, "dividendYield": 0.01,
        "beta": 1, "sector": None, "industry": None,
    }
    async def _fake_history(*_a, **_kw):
        return [{"date": f"2025-{(i%12)+1:02d}-01", "close": 100 + i} for i in range(60)]

    with patch.object(sas, "_yf_info", side_effect=_stub_yf_info_for(yf_payload)), \
         patch.object(sas, "_yf_history", side_effect=_fake_history), \
         patch.dict(sas.SECTOR_CONSTITUENTS, {"NIFTY BANK": ["X.NS"]}, clear=False), \
         patch.dict(sas.SECTOR_YAHOO_TICKER, {"NIFTY BANK": "^NSEBANK"}, clear=False):
        result = asyncio.run(svc.get_sector_detail("NIFTY BANK", "1y"))

    assert result["historySynthetic"] is False


# ── 5. Top gainers/losers exclude None change1d ──────────────────────────────


def test_top_gainers_losers_exclude_failed_fetch_stocks():
    """A constituent with `change1d=None` (yf failure) must NOT appear in
    Top Gainers/Losers — otherwise it ranks ahead of legit -0.5% losers."""
    price = AsyncMock()
    price.get_quote_with_meta.return_value = None

    svc = SectorAnalyticsService(yahoo=MagicMock(), price=price)

    payloads = [
        {"symbol": "A.NS", "name": "A", "price": 100, "change1d": 1.5, "marketCap": 1e10,
         "pe": 10, "pb": 1, "ps": 1, "evEbitda": 5, "roe": 0.1, "roa": 0.05,
         "earningsGrowth": 0.1, "revenueGrowth": 0.1, "debtToEquity": 0.5,
         "netMargin": 0.1, "dividendYield": 0.01, "beta": 1, "sector": None, "industry": None},
        {"symbol": "B.NS", "name": "B", "price": None, "change1d": None, "marketCap": None,
         "pe": None, "pb": None, "ps": None, "evEbitda": None, "roe": None, "roa": None,
         "earningsGrowth": None, "revenueGrowth": None, "debtToEquity": None,
         "netMargin": None, "dividendYield": None, "beta": None, "sector": None, "industry": None},
        {"symbol": "C.NS", "name": "C", "price": 50, "change1d": -0.5, "marketCap": 5e9,
         "pe": 12, "pb": 1, "ps": 1, "evEbitda": 5, "roe": 0.1, "roa": 0.05,
         "earningsGrowth": 0, "revenueGrowth": 0, "debtToEquity": 0.5,
         "netMargin": 0.05, "dividendYield": 0, "beta": 1, "sector": None, "industry": None},
    ]

    async def _fake_history(*_a, **_kw): return [{"date": "2025-01-01", "close": 1.0}] * 30

    with patch.object(sas, "_yf_info", side_effect=_stub_yf_info_for(*payloads)), \
         patch.object(sas, "_yf_history", side_effect=_fake_history), \
         patch.dict(sas.SECTOR_CONSTITUENTS, {"NIFTY BANK": ["A.NS", "B.NS", "C.NS"]}, clear=False), \
         patch.dict(sas.SECTOR_YAHOO_TICKER, {"NIFTY BANK": "^NSEBANK"}, clear=False):
        result = asyncio.run(svc.get_sector_detail("NIFTY BANK", "1y"))

    gainer_syms = {g["symbol"] for g in result["topGainers"]}
    loser_syms  = {g["symbol"] for g in result["topLosers"]}

    assert "B.NS" not in gainer_syms
    assert "B.NS" not in loser_syms
    assert "A.NS" in gainer_syms       # +1.5%
    assert "C.NS" in loser_syms        # -0.5%
