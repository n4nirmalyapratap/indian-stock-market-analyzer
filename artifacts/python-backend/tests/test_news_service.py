"""
Tests for the news service after the 2026-05 data-honesty audit:
  * VADER-based sentiment classification (not naive bag-of-words)
  * Per-source health surfaced in the feed payload
  * Honest `cached` / `refreshedAt` / `fetchedAt` semantics
  * Undated articles flagged + sorted last
  * ScanX sitemap parsing
  * Deals / corporate-events availability flags
"""
from __future__ import annotations

import asyncio
import sys
import time
import types
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

from app.services import news_service as ns


# ─── helpers ──────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Wipe the in-memory cache between tests so cached_hit semantics are testable."""
    ns._CACHE.clear()
    yield
    ns._CACHE.clear()


# ─── 1. VADER sentiment ───────────────────────────────────────────────────────

def test_sentiment_neutral_for_empty_string():
    assert ns._sentiment("") == "neutral"


def test_sentiment_uses_vader_when_available():
    # The pre-audit naive classifier mis-labelled this headline as bullish
    # because of the words "soaring" / "high". VADER (with our financial
    # threshold of ±0.20) sees the polarity is mixed and falls into
    # neutral or bearish — definitively NOT bullish.
    text = "Gold rate today under pressure on soaring crude oil prices, hawkish central banks"
    label = ns._sentiment(text)
    assert label in ("neutral", "bearish"), \
        f"VADER mis-labelled mixed/negative headline as {label!r}"


def test_sentiment_clearly_negative_text():
    assert ns._sentiment("Sensex tumbles 500 points as IT stocks crash on weak guidance") == "bearish"


def test_sentiment_clearly_positive_text():
    assert ns._sentiment("Nifty surges to record high on strong earnings and bullish outlook") == "bullish"


def test_sentiment_falls_back_to_neutral_when_vader_unavailable():
    with patch.object(ns, "_get_vader", return_value=None):
        assert ns._sentiment("anything bullish bearish whatever") == "neutral"


# ─── 2. Undated handling ──────────────────────────────────────────────────────

def test_parse_published_returns_undated_flag_when_missing():
    entry = {}  # no published_parsed
    iso, undated = ns._parse_published(entry)
    assert undated is True
    # Sentinel epoch zero so sort puts undated entries last
    assert datetime.fromisoformat(iso).year == 1970


def test_parse_published_handles_real_timestamp():
    entry = {"published_parsed": (2026, 5, 1, 10, 30, 0, 0, 0, 0)}
    iso, undated = ns._parse_published(entry)
    assert undated is False
    assert "2026-05-01" in iso


# ─── 3. ScanX sitemap parsing ─────────────────────────────────────────────────

_SCANX_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
  <url>
    <loc>https://scanx.trade/stock-market-news/stocks/sample-recent/100</loc>
    <news:news>
      <news:publication>
        <news:name>ScanX News</news:name>
        <news:language>en</news:language>
      </news:publication>
      <news:publication_date>{recent}</news:publication_date>
      <news:title>Reliance Industries Reports Strong Q4 Earnings</news:title>
    </news:news>
  </url>
  <url>
    <loc>https://scanx.trade/stock-market-news/stocks/very-old/200</loc>
    <news:news>
      <news:publication>
        <news:name>ScanX News</news:name>
        <news:language>en</news:language>
      </news:publication>
      <news:publication_date>2020-01-01</news:publication_date>
      <news:title>This Should Be Filtered Out By Age Cutoff</news:title>
    </news:news>
  </url>
  <url>
    <loc>https://scanx.trade/stock-market-news/market/global-news/300</loc>
    <news:news>
      <news:publication>
        <news:name>ScanX News</news:name>
        <news:language>en</news:language>
      </news:publication>
      <news:publication_date>{recent}</news:publication_date>
      <news:title>US Markets Open Higher On Fed Decision</news:title>
    </news:news>
  </url>
</urlset>
"""


def _mock_scanx_response(text: str):
    resp = MagicMock()
    resp.text = text
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    return client


def test_scanx_sitemap_parser_filters_old_entries_and_categorises():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    body = _SCANX_SAMPLE.format(recent=today)
    with patch.object(ns.httpx, "Client", return_value=_mock_scanx_response(body)):
        articles, err = ns._fetch_scanx_sitemap()
    assert err is None
    titles = [a["title"] for a in articles]
    assert "Reliance Industries Reports Strong Q4 Earnings" in titles
    assert "US Markets Open Higher On Fed Decision" in titles
    assert "This Should Be Filtered Out By Age Cutoff" not in titles
    # /stocks/ → corporate, /market/ → market
    by_url = {a["url"]: a["category"] for a in articles}
    assert by_url["https://scanx.trade/stock-market-news/stocks/sample-recent/100"] == "corporate"
    assert by_url["https://scanx.trade/stock-market-news/market/global-news/300"] == "market"
    # All ScanX articles are dated (sitemap filter requires a date)
    assert all(a["undated"] is False for a in articles)
    # All ScanX articles use the SX_ id prefix
    assert all(a["id"].startswith("SX_") for a in articles)


def test_scanx_sitemap_returns_error_on_http_failure():
    def _raising_client(*args, **kwargs):
        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.get.side_effect = Exception("connection refused")
        return client
    with patch.object(ns.httpx, "Client", side_effect=_raising_client):
        articles, err = ns._fetch_scanx_sitemap()
    assert articles == []
    assert err is not None and "connection refused" in err


# ─── 4. Cache honesty: cached flag + refreshedAt ──────────────────────────────

def test_get_news_feed_first_call_is_uncached_second_is_cached():
    fake_payload = {
        "articles": [{
            "id": "X_1", "title": "Test", "summary": "", "url": "u",
            "source": "Test", "sourceShort": "T", "sourceColor": "#000",
            "category": "market",
            "published": "2026-05-01T00:00:00+00:00",
            "undated": False, "sentiment": "neutral", "tickers": [],
            "image_url": None, "type": "news",
        }],
        "sources": [{"name": "Test", "short": "T", "ok": True, "count": 1, "error": None}],
    }
    with patch.object(ns, "_fetch_all_feeds", side_effect=_async_return(fake_payload)) as mock_fetch:
        r1 = _run(ns.get_news_feed(limit=5))
        r2 = _run(ns.get_news_feed(limit=5))
    assert mock_fetch.call_count == 1, "second call should hit cache, not refetch"
    assert r1["cached"] is False, "first call is a cache miss"
    assert r2["cached"] is True,  "second call is a cache hit"
    # refreshedAt is the cache fill time and must be the SAME between calls
    assert r1["refreshedAt"] == r2["refreshedAt"]
    # fetchedAt is the wall-clock time of the call and may differ
    assert "fetchedAt" in r1 and "fetchedAt" in r2


def _async_return(value):
    """Helper: returns an async side_effect callable that returns `value`
    on every invocation. Use as `side_effect=_async_return(...)` so a
    fresh coroutine is produced on each call (return_value would reuse
    a single already-awaited coroutine)."""
    async def _f(*args, **kwargs):
        return value
    return _f


# ─── 5. Per-source health propagates ──────────────────────────────────────────

def test_feed_response_includes_source_health_per_short_name():
    fake_payload = {
        "articles": [],
        "sources": [
            {"name": "Economic Times", "short": "ET",   "ok": True,  "count": 12, "error": None},
            {"name": "Livemint",       "short": "Mint", "ok": False, "count": 0,  "error": "timeout"},
            {"name": "ScanX",          "short": "ScanX","ok": True,  "count": 8,  "error": None},
        ],
    }
    with patch.object(ns, "_fetch_all_feeds", side_effect=_async_return(fake_payload)):
        r = _run(ns.get_news_feed(limit=5))
    shorts = {s["short"]: s for s in r["sources"]}
    assert shorts["Mint"]["ok"] is False
    assert shorts["Mint"]["error"] == "timeout"
    assert shorts["ET"]["ok"] is True
    assert shorts["ScanX"]["count"] == 8
    # Source label is the unified provenance string
    assert r["source"] == ns.NEWS_SOURCE_LABEL


# ─── 6. _fetch_all_feeds collapses duplicate ET rows ──────────────────────────

def test_fetch_all_feeds_collapses_et_duplicate_rows():
    """ET appears in RSS_SOURCES under both 'market' and 'general'.
    The combined sources list should expose ET as one row, not two."""
    def _ok(src, *_a, **_k):
        return ([{"id": "x", "title": f"t-{src['category']}", "summary": "",
                  "url": "u", "source": src["name"], "sourceShort": src["short"],
                  "sourceColor": src["color"], "category": src["category"],
                  "published": "2026-05-01T00:00:00+00:00", "undated": False,
                  "sentiment": "neutral", "tickers": [], "image_url": None,
                  "type": "news"}], None)
    with patch.object(ns, "_fetch_one_feed", side_effect=_ok), \
         patch.object(ns, "_fetch_scanx_sitemap", return_value=([], "skip")):
        payload = _run(ns._fetch_all_feeds())
    shorts = [s["short"] for s in payload["sources"]]
    # ET appears exactly once after collapse, ScanX is listed too
    assert shorts.count("ET") == 1
    assert "ScanX" in shorts


# ─── 7. Undated articles sort last ────────────────────────────────────────────

def test_undated_articles_sort_after_dated_articles():
    def _stub(src, *_a, **_k):
        # First feed → dated; second feed → undated
        if src["category"] == "market" and src["short"] == "ET":
            arts = [{"id": "d1", "title": "dated", "summary": "", "url": "u",
                     "source": "x", "sourceShort": "ET", "sourceColor": "#000",
                     "category": "market",
                     "published": "2026-04-01T00:00:00+00:00",
                     "undated": False, "sentiment": "neutral",
                     "tickers": [], "image_url": None, "type": "news"}]
        else:
            arts = [{"id": f"u-{src['short']}", "title": f"undated-{src['short']}",
                     "summary": "", "url": "u",
                     "source": "x", "sourceShort": src["short"], "sourceColor": "#000",
                     "category": src["category"],
                     "published": "1970-01-01T00:00:00+00:00",
                     "undated": True, "sentiment": "neutral",
                     "tickers": [], "image_url": None, "type": "news"}]
        return (arts, None)
    with patch.object(ns, "_fetch_one_feed", side_effect=_stub), \
         patch.object(ns, "_fetch_scanx_sitemap", return_value=([], "skip")):
        payload = _run(ns._fetch_all_feeds())
    arts = payload["articles"]
    assert arts, "should have articles"
    assert arts[0]["undated"] is False, "dated article must come first"
    # All trailing entries are undated
    assert all(a["undated"] for a in arts[1:])


# ─── 8. Deals availability flag ───────────────────────────────────────────────

def test_get_deals_marks_unavailable_when_both_endpoints_fail():
    fake = {"deals": [], "errors": {"bulk": "fail-b", "block": "fail-k"}}
    with patch.object(ns, "_fetch_deals", side_effect=_async_return(fake)):
        r = _run(ns.get_deals())
    assert r["available"] is False
    assert r["errors"]["bulk"] == "fail-b"
    assert r["errors"]["block"] == "fail-k"


def test_get_deals_available_when_one_endpoint_works():
    fake = {
        "deals": [{"type": "bulk", "date": "", "symbol": "RELIANCE", "name": "",
                   "client": "", "side": "BUY", "quantity": 100, "price": 1.0}],
        "errors": {"bulk": None, "block": "block-failed"},
    }
    with patch.object(ns, "_fetch_deals", side_effect=_async_return(fake)):
        r = _run(ns.get_deals())
    assert r["available"] is True
    assert len(r["bulk"]) == 1 and r["block"] == []


# ─── 9. Corporate events availability flag ────────────────────────────────────

def test_get_corporate_events_marks_unavailable_on_error():
    fake = {"events": [], "error": "nse blocked"}
    with patch.object(ns, "_fetch_nse_events", side_effect=_async_return(fake)):
        r = _run(ns.get_corporate_events())
    assert r["available"] is False
    assert r["error"] == "nse blocked"
    assert r["events"] == []


def test_fetch_nse_events_handles_dataframe_shape():
    """nsepython.nse_events() returns a pandas DataFrame, not a list. The
    converter must normalise it; otherwise rows get silently dropped."""
    ns._CACHE.pop("events", None)

    class _FakeDF:
        def to_dict(self, orient="records"):
            assert orient == "records"
            return [
                {"symbol": "RELIANCE", "company": "Reliance Industries",
                 "purpose": "Dividend", "date": "10-May-2026"},
                {"symbol": "TCS", "company": "Tata Consultancy",
                 "purpose": "Quarterly Results", "date": "12-May-2026"},
            ]

    fake_mod = types.SimpleNamespace(nse_events=lambda: _FakeDF())
    with patch.dict(sys.modules, {"nsepython": fake_mod}):
        r = _run(ns._fetch_nse_events())
    assert r["error"] is None
    assert len(r["events"]) == 2
    assert r["events"][0]["symbol"] == "RELIANCE"
    assert r["events"][0]["type"] == "dividend"
    assert r["events"][1]["type"] == "results"


def test_fetch_nse_events_tolerates_nan_rows():
    """A single malformed/NaN row must not nuke the whole feed — pandas
    happily emits NaN for missing values and `.lower()` on a float blows
    up. The fetcher should coerce safely and skip empty rows."""
    ns._CACHE.pop("events", None)
    nan = float("nan")

    class _FakeDF:
        def to_dict(self, orient="records"):
            return [
                # NaN purpose — must not crash _classify_event
                {"symbol": "INFY", "company": "Infosys",
                 "purpose": nan, "date": "15-May-2026"},
                # totally empty row — should be skipped
                {"symbol": "", "company": "", "purpose": "", "date": ""},
                # good row that must still come through
                {"symbol": "HDFCBANK", "company": "HDFC Bank",
                 "purpose": "AGM", "date": "20-May-2026"},
            ]

    fake_mod = types.SimpleNamespace(nse_events=lambda: _FakeDF())
    with patch.dict(sys.modules, {"nsepython": fake_mod}):
        r = _run(ns._fetch_nse_events())
    assert r["error"] is None
    syms = [e["symbol"] for e in r["events"]]
    assert "INFY" in syms and "HDFCBANK" in syms
    assert "" not in syms  # empty row dropped
    infy = next(e for e in r["events"] if e["symbol"] == "INFY")
    assert infy["purpose"] == ""  # NaN coerced to empty string
    assert infy["type"] == "announcement"  # _classify_event default bucket


# ─── 10. /news/feed route surfaces honest meta.source ────────────────────────

def test_route_meta_source_includes_scanx():
    """Mounts only the news router on a minimal FastAPI app so the auth
    middleware doesn't gate the request — same pattern used by the
    market sentiment route tests."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes import news as news_route
    fake_payload = {
        "articles": [],
        "sources": [{"name": "ScanX", "short": "ScanX", "ok": True, "count": 5, "error": None}],
    }
    app = FastAPI()
    app.include_router(news_route.router)
    with patch.object(ns, "_fetch_all_feeds", side_effect=_async_return(fake_payload)):
        client = TestClient(app)
        r = client.get("/news/feed?limit=5")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == ns.NEWS_SOURCE_LABEL
    assert body["meta"]["source"] == ns.NEWS_SOURCE_LABEL
    # asOf reflects cache fill time, not "now"
    assert body["meta"]["asOf"] == body["refreshedAt"]
