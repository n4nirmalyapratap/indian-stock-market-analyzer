"""
Tests for `news_service.get_ticker_news` — the per-stock news endpoint that
blends RSS matches with a Tavily top-up.

We patch:
  * ``news_service._cache_get`` / ``_cache_set`` for cache-state isolation
  * ``news_service._fetch_all_feeds`` so the test doesn't hit the network
  * ``tavily_service.search_ticker_news`` so the test doesn't hit Tavily

The repo doesn't use pytest-asyncio; tests run coroutines via asyncio.run
to stay consistent with other backend tests.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from app.services import news_service as ns


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_article(title: str, *, tickers: list[str] | None = None,
                  category: str = "market") -> dict:
    return {
        "title":     title,
        "summary":   "",
        "url":       f"https://example.com/{title.lower().replace(' ', '-')}",
        "source":    "example.com",
        "published": "2026-05-10T08:30:00Z",
        "category":  category,
        "tickers":   tickers or [],
        "sentiment": None,
        "image":     None,
    }


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch):
    """Wipe news_service._CACHE before each test so we don't leak state.
    Also clear any TAVILY env vars so they're set explicitly per test."""
    monkeypatch.setattr(ns, "_CACHE", {})
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    yield
    # Belt and braces — restore an empty cache on the way out.
    monkeypatch.setattr(ns, "_CACHE", {})


def _seed_feed_cache(articles: list[dict]):
    """Drop articles straight into the feed cache so we don't trigger an RSS
    fetch during the test."""
    ns._CACHE["feed"] = {
        "ts": time.time(),
        "data": {"articles": articles, "sources": []},
    }


# ── Tests ────────────────────────────────────────────────────────────────────

def test_empty_symbol_returns_empty_without_fetching():
    """An empty symbol short-circuits before touching the cache or Tavily."""
    out = asyncio.run(ns.get_ticker_news(""))
    assert out["symbol"] == ""
    assert out["articles"] == []
    assert out["total"] == 0
    assert out["tavilyUsed"] is False


def test_matches_by_tickers_field():
    """An article whose `tickers` list contains the symbol matches even when
    the symbol isn't in the title."""
    _seed_feed_cache([
        _make_article("Q4 Earnings Boost", tickers=["RELIANCE"]),
        _make_article("Unrelated Pharma News", tickers=["CIPLA"]),
    ])
    out = asyncio.run(ns.get_ticker_news("RELIANCE"))
    assert out["total"] == 1
    assert out["articles"][0]["title"] == "Q4 Earnings Boost"


def test_matches_by_title_substring_case_insensitive():
    """If the title contains the symbol (lowercase/mixed-case), match it
    even when the tickers list is empty (a common RSS gap)."""
    _seed_feed_cache([
        _make_article("reliance Industries beats estimates", tickers=[]),
        _make_article("TCS announces dividend",              tickers=[]),
    ])
    out = asyncio.run(ns.get_ticker_news("RELIANCE"))
    assert out["total"] == 1


def test_tavily_top_up_when_rss_thin(monkeypatch):
    """RSS only has 1 match for RELIANCE (below _TICKER_TAVILY_FLOOR=5),
    so Tavily is called and its articles are appended after dedupe."""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    _seed_feed_cache([
        _make_article("RELIANCE soars on Q4", tickers=["RELIANCE"]),
        _make_article("Unrelated news",        tickers=[]),
    ])
    # Patch the lazy-imported tavily_service.search_ticker_news.
    from app.services import tavily_service
    fake = AsyncMock(return_value=[
        {"title": "Reliance fresh AI investment", "url": "https://x.com/a",
         "summary": "...", "source": "x.com",
         "published": "2026-05-11T00:00:00Z", "sentiment": None},
        # Dedupe: identical title (case-insensitive) to the RSS one — dropped.
        {"title": "RELIANCE SOARS ON Q4", "url": "https://x.com/b",
         "summary": "dupe", "source": "x.com",
         "published": "2026-05-11T00:00:00Z", "sentiment": None},
        {"title": "Mukesh Ambani interview", "url": "https://x.com/c",
         "summary": "...", "source": "x.com",
         "published": "2026-05-12T00:00:00Z", "sentiment": None},
    ])
    monkeypatch.setattr(tavily_service, "search_ticker_news", fake)

    out = asyncio.run(ns.get_ticker_news("RELIANCE"))
    titles = [a["title"] for a in out["articles"]]
    # RSS match + 2 unique Tavily articles (the dupe is dropped)
    assert "RELIANCE soars on Q4" in titles
    assert "Reliance fresh AI investment" in titles
    assert "Mukesh Ambani interview" in titles
    assert "RELIANCE SOARS ON Q4" not in titles  # deduped
    assert out["tavilyUsed"] is True
    assert "Tavily" in out["source"]


def test_no_tavily_topup_when_rss_already_sufficient(monkeypatch):
    """If RSS hits the floor, Tavily is NOT called — the AsyncMock would
    raise if invoked."""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    _seed_feed_cache([
        _make_article(f"TCS story {i}", tickers=["TCS"]) for i in range(7)
    ])
    from app.services import tavily_service
    fake = AsyncMock(side_effect=AssertionError("Tavily should not be called"))
    monkeypatch.setattr(tavily_service, "search_ticker_news", fake)

    out = asyncio.run(ns.get_ticker_news("TCS"))
    assert out["tavilyUsed"] is False
    assert out["total"] == 7
    fake.assert_not_called()


def test_no_tavily_key_silently_skips_topup(monkeypatch):
    """Without TAVILY_API_KEY, the Tavily call returns [] immediately (no
    network), so the response is RSS-only without any error surfacing."""
    # No TAVILY_API_KEY set (autouse fixture clears it)
    _seed_feed_cache([
        _make_article("Lone RELIANCE article", tickers=["RELIANCE"]),
    ])
    out = asyncio.run(ns.get_ticker_news("RELIANCE"))
    assert out["tavilyUsed"] is False
    assert out["total"] == 1
    assert out["source"] == ns.NEWS_SOURCE_LABEL  # no "+ Tavily" suffix


def test_tavily_exception_does_not_break_endpoint(monkeypatch):
    """A Tavily failure must not propagate — the endpoint returns RSS-only
    results and tavilyUsed=False so the client can keep rendering."""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    _seed_feed_cache([_make_article("Only RSS hit", tickers=["WIPRO"])])
    from app.services import tavily_service
    monkeypatch.setattr(
        tavily_service, "search_ticker_news",
        AsyncMock(side_effect=RuntimeError("network down")),
    )
    out = asyncio.run(ns.get_ticker_news("WIPRO"))
    assert out["total"] == 1
    assert out["tavilyUsed"] is False


def test_tavily_cache_avoids_repeat_calls(monkeypatch):
    """Within the 5-min ticker cache TTL, repeat calls for the same symbol
    do NOT hit Tavily again."""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    _seed_feed_cache([_make_article("Lone INFY note", tickers=["INFY"])])

    from app.services import tavily_service
    fake = AsyncMock(return_value=[
        {"title": "Infosys wins deal", "url": "https://x.com/i1",
         "summary": "", "source": "x.com",
         "published": "2026-05-10T00:00:00Z", "sentiment": None},
    ])
    monkeypatch.setattr(tavily_service, "search_ticker_news", fake)

    # First call hits Tavily once
    asyncio.run(ns.get_ticker_news("INFY"))
    assert fake.call_count == 1

    # Second call within TTL — cached, no extra Tavily hit
    asyncio.run(ns.get_ticker_news("INFY"))
    assert fake.call_count == 1


def test_looks_like_ticker_heuristic():
    """Sanity-check the ticker-shape heuristic used by get_news_feed for
    the Feature 6a top-up path."""
    assert ns._looks_like_ticker("RELIANCE")
    assert ns._looks_like_ticker("TCS")
    assert ns._looks_like_ticker("hdfc-eq")           # suffix stripped
    assert ns._looks_like_ticker("TATA-MOTORS")       # hyphen ok
    assert not ns._looks_like_ticker("")              # empty
    assert not ns._looks_like_ticker("A")             # too short
    assert not ns._looks_like_ticker("ASUPERLONGNAME1234567890")  # too long
    assert not ns._looks_like_ticker("12345")         # no letters
    assert not ns._looks_like_ticker("Ambuja Cements with spaces")
