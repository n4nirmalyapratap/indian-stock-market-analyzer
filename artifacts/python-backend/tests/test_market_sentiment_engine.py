"""
test_market_sentiment_engine.py
================================

Data-honesty regression tests for the Market Sentiment composite engine.

These tests pin behaviour the previous implementation got silently wrong:

  • VIX fetch failures returned a plausible (15.0, 0.0) so users could not
    distinguish a fetch failure from a calm market day.
  • Failed legs (news / price-action / sector) returned a synthetic
    "Neutral 0" that still consumed their full weight in the composite.
  • PCR Proxy is a deterministic function f(VIX) yet contributed its own
    10% weight, double-counting the VIX leg.
  • marketMood was declared "bullish"/"bearish" off the tiniest sample.
  • Route forced `cached: True` and a "NSE" provenance string even when the
    engine had just freshly computed using Yahoo Finance + RSS feeds.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.services import market_sentiment_engine as eng
from app.services import news_service


# ── helpers ──────────────────────────────────────────────────────────────────

def _patch_legs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    vix: tuple[float | None, float | None],
    pa: dict,
    news: dict,
) -> None:
    """Replace the three composite legs with fixed return values and stub
    the (slow) sector fetch so tests don't hit the network."""
    async def _vix() -> tuple[float | None, float | None]:
        return vix

    async def _pa() -> dict:
        return pa

    async def _news() -> dict:
        return news

    async def _sectors() -> list[dict]:
        return []

    monkeypatch.setattr(eng, "_fetch_vix", _vix)
    monkeypatch.setattr(eng, "_fetch_nifty_price_action", _pa)
    monkeypatch.setattr(eng, "_fetch_news_mood", _news)
    monkeypatch.setattr(eng, "_fetch_sector_sentiments", _sectors)
    eng.clear_cache()


def _full_news(bullish: int, bearish: int, neutral: int) -> dict:
    return {
        "available": True,
        "totalArticles": bullish + bearish + neutral,
        "sentiments": {"bullish": bullish, "bearish": bearish, "neutral": neutral},
        "marketMood": "neutral",
    }


def _full_pa(compound: float) -> dict:
    return {
        "available": True,
        "compound": compound,
        "label": "BULLISH" if compound > 0 else "BEARISH",
        "indicators": {"momentum5d": 1.0, "momentum20d": 2.0, "rsi14": 60.0},
    }


# ── 1. VIX fetch failure returns (None, None) ────────────────────────────────

def test_fetch_vix_returns_none_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Previously returned (15.0, 0.0) — silently neutralising the VIX leg."""
    import httpx

    class _Boom:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): return False
        async def get(self, *a, **kw):  # noqa: D401
            raise httpx.ConnectError("simulated network failure")

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: _Boom())

    import asyncio
    cur, pct = asyncio.run(eng._fetch_vix())
    assert cur is None and pct is None


# ── 2. Composite excludes None leg and renormalises ──────────────────────────

def test_composite_excludes_unavailable_vix_and_renormalises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When VIX is unavailable, weights renormalise across news (35) + PA (35)
    so they sum to 100% — without inventing a synthetic VIX score."""
    import asyncio
    _patch_legs(
        monkeypatch,
        vix=(None, None),
        pa=_full_pa(0.50),                   # pa_score = +50, weight 35
        news=_full_news(20, 0, 0),           # news_score = +100, weight 35
    )

    result = asyncio.run(eng.get_market_sentiment(force_refresh=True))

    assert result["availability"] == {
        "news": True, "price_action": True, "vix": False, "pcr": False,
    }
    # Renormalised composite = (100*35 + 50*35) / 70 = 75.0
    assert result["composite"] == pytest.approx(75.0, abs=0.1)
    assert result["vix"]["available"] is False
    assert result["vix"]["current"] is None


# ── 3. All legs unavailable → composite is None / "Unavailable" ──────────────

def test_composite_none_when_no_legs_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio
    _patch_legs(
        monkeypatch,
        vix=(None, None),
        pa={"available": False, "compound": None, "label": "UNAVAILABLE",
            "indicators": {}},
        news={"available": False, "totalArticles": 0,
              "sentiments": {"bullish": 0, "bearish": 0, "neutral": 0},
              "marketMood": "neutral"},
    )

    result = asyncio.run(eng.get_market_sentiment(force_refresh=True))

    assert result["composite"] is None
    assert result["label"] == "Unavailable"
    assert result["strategy_recommendations"] == []
    assert result["contrarian_signals"] == []


# ── 4. PCR is NOT in composite math ──────────────────────────────────────────

def test_pcr_not_in_composite_math(monkeypatch: pytest.MonkeyPatch) -> None:
    """Composite must equal weighted average of (news, pa, vix) only.
    PCR is f(VIX) and should be display-only (weight=0)."""
    import asyncio
    _patch_legs(
        monkeypatch,
        vix=(18.0, 5.0),                     # vix_score will be some real value
        pa=_full_pa(0.20),
        news=_full_news(10, 5, 5),
    )

    result = asyncio.run(eng.get_market_sentiment(force_refresh=True))

    # Recompute composite from the three independent legs only.
    news_s = result["news"]["score"]
    pa_s   = result["price_action"]["score"]
    vix_s  = result["vix"]["score"]
    expected = round((news_s * 35 + pa_s * 35 + vix_s * 20) / 90, 1)
    assert result["composite"] == pytest.approx(expected, abs=0.1)

    # PCR component is present but weight=0 (informational)
    pcr_comp = next(c for c in result["components"] if c["name"] == "PCR Proxy")
    assert pcr_comp["weight"] == 0
    # And the response carries an honest disclosure note
    note = result["pcr"]["note"].lower()
    assert "display-only" in note or "informational" in note
    assert "composite" in note


# ── 5. marketMood thresholds ─────────────────────────────────────────────────

def _mood(monkeypatch: pytest.MonkeyPatch, articles: list[dict]) -> str:
    """Bypass network: stub _cache_get('feed') to return canned articles.
    The cache entry shape is `{ts, data: {articles, sources}}` after the
    2026-05 news-service audit."""
    import time as _time
    fake_entry = {
        "ts":   _time.time(),
        "data": {"articles": articles, "sources": []},
    }
    monkeypatch.setattr(news_service, "_cache_get",
                        lambda key: fake_entry if key == "feed" else None)
    import asyncio
    return asyncio.run(news_service.get_news_stats())["marketMood"]


def _mk_article(sentiment: str) -> dict:
    return {"sentiment": sentiment, "sourceShort": "x"}


def test_market_mood_insufficient_sample_is_neutral(monkeypatch: pytest.MonkeyPatch) -> None:
    arts = [_mk_article("bullish")] * 4   # only 4 articles
    assert _mood(monkeypatch, arts) == "neutral"


def test_market_mood_thin_margin_is_neutral(monkeypatch: pytest.MonkeyPatch) -> None:
    # 8 bull / 7 bear / 0 neutral → margin 1/15 ≈ 6.7% < 10% threshold
    arts = ([_mk_article("bullish")] * 8) + ([_mk_article("bearish")] * 7)
    assert _mood(monkeypatch, arts) == "neutral"


def test_market_mood_clear_lean_is_directional(monkeypatch: pytest.MonkeyPatch) -> None:
    arts = ([_mk_article("bullish")] * 10) + ([_mk_article("bearish")] * 1)
    assert _mood(monkeypatch, arts) == "bullish"


# ── 5b. Sector fetch failure semantics ───────────────────────────────────────

def test_sector_fetch_failure_returns_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed per-sector fetch must return `available:False, score:None,
    label:'Unavailable'` rather than the previous synthetic
    `score:0, label:'Neutral'` which was indistinguishable from a real
    flat reading."""
    import asyncio
    import httpx

    # Always-failing httpx client for the sector fetcher.
    class _Boom:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): return False
        async def get(self, *a, **kw):
            raise httpx.ConnectError("simulated")

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: _Boom())

    sectors = asyncio.run(eng._fetch_sector_sentiments())
    assert sectors, "expected one entry per SECTOR_TICKERS"
    for s in sectors:
        assert s["available"] is False
        assert s["score"] is None
        assert s["label"] == "Unavailable"
        assert s["compound"] is None


# ── 6. Route _meta provenance and cached preservation ────────────────────────

@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Minimal app exposing the sentiment router only."""
    from fastapi import FastAPI
    from app.routes import sentiment as sentiment_route

    # Patch engine to a fast deterministic snapshot so the route call doesn't
    # hit the network or take 10s.
    _patch_legs(
        monkeypatch,
        vix=(18.0, 0.0),
        pa=_full_pa(0.10),
        news=_full_news(10, 0, 0),
    )

    app = FastAPI()
    app.include_router(sentiment_route.router)
    return TestClient(app)


def test_route_meta_source_is_yahoo_plus_rss(client: TestClient) -> None:
    """Provenance was previously claimed as 'NSE' which is a lie — the
    engine never calls NSE for these legs."""
    resp = client.get("/sentiment/market")
    assert resp.status_code == 200
    body = resp.json()
    assert "meta" in body
    assert body["meta"]["source"] == "Yahoo Finance + RSS feeds"


def test_route_preserves_engine_cached_flag(client: TestClient) -> None:
    """Route was forcing `cached:True` even on fresh compute — masking
    whether the response was served from cache."""
    eng.clear_cache()
    fresh = client.get("/sentiment/market").json()
    assert fresh["cached"] is False

    cached = client.get("/sentiment/market").json()
    assert cached["cached"] is True
