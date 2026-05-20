"""
Unit tests for the Tavily news fallback.

We mock httpx.AsyncClient so the tests don't hit the network. The point is
to lock in:
  * No API key → empty list (silent no-op, never raises)
  * Happy path → articles normalised into the expected shape
  * Network / HTTP / shape errors → empty list, never raises

The repo doesn't use pytest-asyncio; tests run coroutines via asyncio.run
to stay consistent with test_macro.py / test_sectors_rotation.py.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.services import tavily_service as tv


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Each test starts with TAVILY_API_KEY unset so we control it explicitly."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_URL", raising=False)
    monkeypatch.delenv("TAVILY_HTTP_TIMEOUT", raising=False)


def _mock_resp(*, status: int, json_data: dict | None = None):
    """Build a stand-in httpx.Response-like object."""
    r = MagicMock()
    r.status_code = status
    r.json = MagicMock(return_value=json_data or {})
    return r


def _patch_post(monkeypatch, *, status: int, json_data: dict | None = None):
    """Patch httpx.AsyncClient with a fake that returns the canned response."""
    canned = _mock_resp(status=status, json_data=json_data)

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *a, **kw):  # noqa: ARG002
            return canned

    monkeypatch.setattr(tv.httpx, "AsyncClient", _FakeClient)


# ── is_configured / no-key fast path ─────────────────────────────────────────

def test_no_api_key_returns_empty_without_http_call(monkeypatch):
    """When TAVILY_API_KEY is unset, the function returns [] without making
    any HTTP call. Patching AsyncClient to blow up loudly proves we don't
    accidentally make a network round-trip with no key."""
    monkeypatch.setattr(tv.httpx, "AsyncClient",
                        MagicMock(side_effect=AssertionError("must not call HTTP")))
    assert tv.is_configured() is False
    out = asyncio.run(tv.search_ticker_news("RELIANCE"))
    assert out == []


def test_empty_symbol_returns_empty(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    out = asyncio.run(tv.search_ticker_news(""))
    assert out == []


# ── Happy path ───────────────────────────────────────────────────────────────

def test_happy_path_normalises_results(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    _patch_post(monkeypatch, status=200, json_data={
        "results": [
            {
                "title": "Reliance Industries beats Q3 estimates",
                "url":   "https://www.moneycontrol.com/news/rel-q3.html",
                "content": "Reliance posted Q3 revenue of …",
                "published_date": "2026-05-10T08:30:00Z",
                "score": 0.94,
            },
            {
                "title": "Mukesh Ambani on AI investments",
                "url":   "https://economictimes.indiatimes.com/m-ambani.html",
                "content": "...",
                "published_date": "2026-05-09T12:00:00Z",
                "score": 0.88,
            },
        ]
    })
    out = asyncio.run(tv.search_ticker_news("RELIANCE"))
    assert len(out) == 2

    first = out[0]
    assert first["title"] == "Reliance Industries beats Q3 estimates"
    assert first["url"]   == "https://www.moneycontrol.com/news/rel-q3.html"
    assert first["summary"].startswith("Reliance posted")
    assert first["published"] == "2026-05-10T08:30:00Z"
    assert first["source"] == "moneycontrol.com"   # domain extracted
    assert first["sentiment"] is None              # left for downstream scorer
    assert first["score"] == pytest.approx(0.94)


def test_results_without_title_are_dropped(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    _patch_post(monkeypatch, status=200, json_data={
        "results": [
            {"title": "",  "url": "https://x.com/a", "content": "", "published_date": ""},
            {"url":   "https://y.com/b"},                                    # no title key
            {"title": "Keeps this one", "url": "https://z.com/c", "content": "ok"},
        ]
    })
    out = asyncio.run(tv.search_ticker_news("TCS"))
    assert len(out) == 1
    assert out[0]["title"] == "Keeps this one"


# ── Failure modes ────────────────────────────────────────────────────────────

def test_non_200_returns_empty(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    _patch_post(monkeypatch, status=429, json_data={"error": "rate limited"})
    out = asyncio.run(tv.search_ticker_news("RELIANCE"))
    assert out == []


def test_malformed_response_shape_returns_empty(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    # `results` is the wrong type (string instead of list)
    _patch_post(monkeypatch, status=200, json_data={"results": "oops"})
    out = asyncio.run(tv.search_ticker_news("RELIANCE"))
    assert out == []


def test_http_exception_returns_empty(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    class _ExplodingClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *a, **kw):  # noqa: ARG002
            raise RuntimeError("network down")

    monkeypatch.setattr(tv.httpx, "AsyncClient", _ExplodingClient)
    out = asyncio.run(tv.search_ticker_news("RELIANCE"))
    assert out == []


# ── _domain_from_url ─────────────────────────────────────────────────────────

def test_domain_extraction_handles_common_shapes():
    assert tv._domain_from_url("https://www.moneycontrol.com/news/x") == "moneycontrol.com"
    assert tv._domain_from_url("http://example.com")                  == "example.com"
    assert tv._domain_from_url("https://sub.example.co.in/abc")       == "sub.example.co.in"
    assert tv._domain_from_url("")                                    == "tavily"
    assert tv._domain_from_url("not a url")                           == "not a url"
