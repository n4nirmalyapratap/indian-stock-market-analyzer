"""
Tests for the LLM-based news sentiment classifier (audit 2026-07):
  * Reply parsing tolerates fences / prose / bare-string arrays and drops
    invalid labels or indices.
  * classify_texts: availability gate, per-headline caching, batching,
    total-failure cooldown.
  * apply_llm_sentiment: overwrites labels + provenance on success; keeps
    the VADER label (sentimentVia="vader") on failure; defaults Tavily's
    sentiment=None articles to neutral (sentimentVia="none").
  * Integration: _fetch_all_feeds applies LLM labels over fetcher output.
"""
from __future__ import annotations

import asyncio
import json
import re
from unittest.mock import AsyncMock, patch

import pytest

from app.services import news_sentiment_llm as nsl


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _reset_state():
    """Wipe the label cache and the cooldown marker between tests."""
    nsl._label_cache.clear()
    nsl._llm_down_until = 0.0
    yield
    nsl._label_cache.clear()
    nsl._llm_down_until = 0.0


def _labels_json(mapping: dict[int, str]) -> str:
    return json.dumps([{"i": i, "s": s} for i, s in mapping.items()])


# ─── 1. _parse_labels ─────────────────────────────────────────────────────────

def test_parse_plain_array_of_objects():
    raw = '[{"i": 1, "s": "bullish"}, {"i": 2, "s": "bearish"}]'
    assert nsl._parse_labels(raw, 2) == {1: "bullish", 2: "bearish"}


def test_parse_fenced_json():
    raw = '```json\n[{"i": 1, "s": "neutral"}]\n```'
    assert nsl._parse_labels(raw, 1) == {1: "neutral"}


def test_parse_prose_wrapped_array():
    raw = 'Here are the labels:\n[{"i": 1, "s": "bearish"}]\nHope that helps!'
    assert nsl._parse_labels(raw, 1) == {1: "bearish"}


def test_parse_bare_string_list_uses_positional_indices():
    raw = '["bullish", "neutral", "bearish"]'
    assert nsl._parse_labels(raw, 3) == {1: "bullish", 2: "neutral", 3: "bearish"}


def test_parse_alternative_key_names():
    raw = '[{"index": 1, "sentiment": "bullish"}, {"index": 2, "label": "bearish"}]'
    parsed = nsl._parse_labels(raw, 2)
    assert parsed[1] == "bullish"
    assert parsed[2] == "bearish"


def test_parse_drops_invalid_labels_and_out_of_range_indices():
    raw = '[{"i": 1, "s": "moon"}, {"i": 99, "s": "bullish"}, {"i": 2, "s": "BEARISH"}]'
    # "moon" invalid, 99 out of range, "BEARISH" normalised to lowercase
    assert nsl._parse_labels(raw, 2) == {2: "bearish"}


def test_parse_garbage_returns_empty():
    assert nsl._parse_labels("total nonsense, no json here", 3) == {}
    assert nsl._parse_labels("", 3) == {}
    assert nsl._parse_labels('{"i": 1}', 3) == {}          # not a list
    assert nsl._parse_labels("[not valid json", 3) == {}


# ─── 2. classify_texts ────────────────────────────────────────────────────────

def test_classify_returns_none_when_no_provider():
    ask = AsyncMock()
    with patch.object(nsl.ai_client, "is_available", return_value=False), \
         patch.object(nsl.ai_client, "ask_with_meta", ask):
        out = _run(nsl.classify_texts(["RIL surges", "TCS falls"]))
    assert out == [None, None]
    ask.assert_not_called()


def test_classify_happy_path_maps_batch_positions_to_inputs():
    ask = AsyncMock(return_value=(_labels_json({1: "bullish", 2: "bearish"}), "groq/llama"))
    with patch.object(nsl.ai_client, "is_available", return_value=True), \
         patch.object(nsl.ai_client, "ask_with_meta", ask):
        out = _run(nsl.classify_texts(["Nifty soars on FII buying", "Bank NPA rises"]))
    assert out == ["bullish", "bearish"]
    assert ask.call_count == 1


def test_classify_uses_cache_on_second_call():
    ask = AsyncMock(return_value=(_labels_json({1: "bullish"}), "groq/llama"))
    with patch.object(nsl.ai_client, "is_available", return_value=True), \
         patch.object(nsl.ai_client, "ask_with_meta", ask):
        first = _run(nsl.classify_texts(["Sensex hits record high"]))
        second = _run(nsl.classify_texts(["Sensex hits record high"]))
    assert first == ["bullish"]
    assert second == ["bullish"]
    # Second call must be served from the label cache — one LLM call total.
    assert ask.call_count == 1


def test_classify_batches_large_input():
    n = nsl._BATCH_SIZE + 5  # forces two batches

    async def _fake_ask(prompt, **kwargs):
        # Answer "neutral" for every numbered line in this batch's prompt.
        count = len(re.findall(r"^\d+\. ", prompt, flags=re.MULTILINE))
        return _labels_json({i: "neutral" for i in range(1, count + 1)}), "groq/llama"

    ask = AsyncMock(side_effect=_fake_ask)
    texts = [f"Headline number {i} about the market" for i in range(n)]
    with patch.object(nsl.ai_client, "is_available", return_value=True), \
         patch.object(nsl.ai_client, "ask_with_meta", ask):
        out = _run(nsl.classify_texts(texts))
    assert ask.call_count == 2
    assert out == ["neutral"] * n


def test_classify_partial_parse_leaves_missing_as_none():
    # LLM only answers headline 1 of 2.
    ask = AsyncMock(return_value=(_labels_json({1: "bullish"}), "groq/llama"))
    with patch.object(nsl.ai_client, "is_available", return_value=True), \
         patch.object(nsl.ai_client, "ask_with_meta", ask):
        out = _run(nsl.classify_texts(["Nifty rallies", "TCS board meet on June 12"]))
    assert out == ["bullish", None]


def test_classify_total_failure_sets_cooldown():
    ask = AsyncMock(return_value=("[AI unavailable: no provider configured.]", "none"))
    with patch.object(nsl.ai_client, "is_available", return_value=True), \
         patch.object(nsl.ai_client, "ask_with_meta", ask):
        out = _run(nsl.classify_texts(["Some headline"]))
        assert out == [None]
        assert nsl._llm_down_until > 0
        # Cooldown active — the next call must not touch the LLM at all.
        out2 = _run(nsl.classify_texts(["Another headline"]))
    assert out2 == [None]
    assert ask.call_count == 1


def test_classify_empty_input():
    assert _run(nsl.classify_texts([])) == []


# ─── 3. apply_llm_sentiment ───────────────────────────────────────────────────

def _article(title: str, sentiment=None, via=None, summary: str = "") -> dict:
    art = {"title": title, "summary": summary, "sentiment": sentiment}
    if via is not None:
        art["sentimentVia"] = via
    return art


def test_apply_overwrites_vader_label_on_success():
    articles = [_article("Investors book profits, Sensex tanks",
                         sentiment="bullish", via="vader")]
    ask = AsyncMock(return_value=(_labels_json({1: "bearish"}), "groq/llama"))
    with patch.object(nsl.ai_client, "is_available", return_value=True), \
         patch.object(nsl.ai_client, "ask_with_meta", ask):
        stats = _run(nsl.apply_llm_sentiment(articles))
    assert articles[0]["sentiment"] == "bearish"
    assert articles[0]["sentimentVia"] == "llm"
    assert stats == {"llm": 1, "fallback": 0}


def test_apply_keeps_vader_label_on_failure():
    articles = [_article("Nifty surges", sentiment="bullish", via="vader")]
    with patch.object(nsl.ai_client, "is_available", return_value=False):
        stats = _run(nsl.apply_llm_sentiment(articles))
    assert articles[0]["sentiment"] == "bullish"
    assert articles[0]["sentimentVia"] == "vader"
    assert stats == {"llm": 0, "fallback": 1}


def test_apply_defaults_unlabelled_articles_to_neutral():
    # Tavily articles arrive with sentiment=None and no sentimentVia.
    articles = [_article("Small-cap stock in focus", sentiment=None)]
    with patch.object(nsl.ai_client, "is_available", return_value=False):
        stats = _run(nsl.apply_llm_sentiment(articles))
    assert articles[0]["sentiment"] == "neutral"
    assert articles[0]["sentimentVia"] == "none"
    assert stats == {"llm": 0, "fallback": 1}


def test_apply_empty_list():
    assert _run(nsl.apply_llm_sentiment([])) == {"llm": 0, "fallback": 0}


def test_apply_never_raises_when_classify_blows_up():
    articles = [_article("Anything", sentiment="neutral", via="vader")]
    boom = AsyncMock(side_effect=RuntimeError("kaboom"))
    with patch.object(nsl, "classify_texts", boom):
        stats = _run(nsl.apply_llm_sentiment(articles))
    assert stats == {"llm": 0, "fallback": 1}
    assert articles[0]["sentiment"] == "neutral"


# ─── 4. Integration: _fetch_all_feeds applies LLM labels ─────────────────────

def test_fetch_all_feeds_relabels_articles_with_llm():
    from app.services import news_service as ns

    def _fake_feed(src):
        return ([{
            "id": "T_000001",
            "title": f"Investors book profits after rally ({src['short']} {src['category']})",
            "summary": "",
            "url": "https://example.com/a",
            "source": src["name"], "sourceShort": src["short"],
            "sourceColor": src["color"], "category": src["category"],
            "published": "2026-07-16T09:00:00+00:00", "undated": False,
            "sentiment": "bullish",       # the classic VADER mislabel
            "sentimentVia": "vader",
            "tickers": [], "image_url": None, "type": "news",
        }], None)

    async def _fake_apply(articles):
        for a in articles:
            a["sentiment"] = "bearish"
            a["sentimentVia"] = "llm"
        return {"llm": len(articles), "fallback": 0}

    with patch.object(ns, "_fetch_one_feed", side_effect=_fake_feed), \
         patch.object(ns, "_fetch_scanx_sitemap", return_value=([], None)), \
         patch.object(ns, "_fetch_yfinance_feed_articles", return_value=([], None)), \
         patch.object(nsl, "apply_llm_sentiment", side_effect=_fake_apply):
        payload = _run(ns._fetch_all_feeds())

    articles = payload["articles"]
    assert articles, "expected at least one article from the fake feeds"
    assert all(a["sentiment"] == "bearish" for a in articles)
    assert all(a["sentimentVia"] == "llm" for a in articles)


def test_fetch_all_feeds_survives_llm_pass_crash():
    from app.services import news_service as ns

    def _fake_feed(src):
        return ([{
            "id": "T_000002",
            "title": f"Nifty ends flat ({src['short']} {src['category']})",
            "summary": "", "url": "https://example.com/b",
            "source": src["name"], "sourceShort": src["short"],
            "sourceColor": src["color"], "category": src["category"],
            "published": "2026-07-16T09:00:00+00:00", "undated": False,
            "sentiment": "neutral", "sentimentVia": "vader",
            "tickers": [], "image_url": None, "type": "news",
        }], None)

    boom = AsyncMock(side_effect=RuntimeError("provider exploded"))
    with patch.object(ns, "_fetch_one_feed", side_effect=_fake_feed), \
         patch.object(ns, "_fetch_scanx_sitemap", return_value=([], None)), \
         patch.object(ns, "_fetch_yfinance_feed_articles", return_value=([], None)), \
         patch.object(nsl, "apply_llm_sentiment", boom):
        payload = _run(ns._fetch_all_feeds())

    # Feed still returns; articles keep their VADER labels.
    assert payload["articles"]
    assert all(a["sentimentVia"] == "vader" for a in payload["articles"])
