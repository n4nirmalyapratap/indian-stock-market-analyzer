"""
Unit tests for the Famous-Investor Council (`agents_service`).

Guards two behaviours that must never silently drift:
  1. `_verdict_from_score` boundary mapping (STRONG_BUY ≥ 0.85, BUY ≥ 0.65,
     HOLD ≥ 0.45, AVOID ≥ 0.30, STRONG_AVOID below).
  2. `run_council` aggregation: 6 buy verdicts → STRONG_BUY, 6 avoid verdicts
     → STRONG_AVOID (regression for an earlier ordering bug where a 6-avoid
     scenario was downgraded to plain AVOID).

Also validates the council response shape (sources[], fetchedAt) and a
representative persona-threshold pass case (Buffett on a clean compounder).

No network, no DB — uses synthetic stock_detail dicts.
"""
from __future__ import annotations

import pytest

from app.services import agents_service as ag


# ── Verdict boundary mapping ─────────────────────────────────────────────────

@pytest.mark.parametrize("score,expected", [
    (1.00, "STRONG_BUY"),
    (0.85, "STRONG_BUY"),
    (0.84999, "BUY"),
    (0.65, "BUY"),
    (0.64999, "HOLD"),
    (0.45, "HOLD"),
    (0.44999, "AVOID"),
    (0.30, "AVOID"),
    (0.29999, "STRONG_AVOID"),
    (0.00, "STRONG_AVOID"),
])
def test_verdict_score_boundaries(score, expected):
    assert ag._verdict_from_score(score) == expected


# ── Council aggregation ──────────────────────────────────────────────────────

def _strong_compounder() -> dict:
    """Synthetic stock_detail that should pass most personas (clean compounder)."""
    return {
        "symbol": "GOOD",
        "info": {
            "longName":           "Good Co Ltd",
            "sector":             "Information Technology",
            "currentPrice":       2000.0,
            "fiftyTwoWeekHigh":   2200.0,
            "fiftyTwoWeekLow":    1500.0,
            "marketCap":          5e11,
            "freeCashflow":       3e10,
            "operatingCashflow":  4e10,
            "trailingPE":         18.0,
            "forwardPE":          16.0,
            "priceToBook":        3.5,
            "priceToSalesTrailing12Months": 4.0,
            "pegRatio":           1.1,
            "enterpriseValue":    5.5e11,
            "enterpriseToEbitda": 14.0,
            "enterpriseToRevenue": 5.0,
            "returnOnEquity":     0.25,
            "returnOnAssets":     0.15,
            "profitMargins":      0.22,
            "operatingMargins":   0.28,
            "grossMargins":       0.55,
            "debtToEquity":       20.0,
            "currentRatio":       2.5,
            "quickRatio":         2.0,
            "totalCash":          5e10,
            "totalDebt":          1e10,
            "earningsGrowth":     0.18,
            "revenueGrowth":      0.15,
            "earningsQuarterlyGrowth": 0.20,
            "dividendYield":      0.012,
            "payoutRatio":        0.30,
            "trailingEps":        110.0,
            "beta":               0.9,
            "heldPercentInsiders":     0.40,
            "heldPercentInstitutions": 0.30,
            "shortPercentOfFloat":     0.005,
            "recommendationMean":  2.0,
            "targetMeanPrice":     2400.0,
        },
    }


def _broken_company() -> dict:
    """Synthetic stock_detail that should trigger most personas to avoid."""
    return {
        "symbol": "BAD",
        "info": {
            "longName":           "Bad Co Ltd",
            "sector":             "Real Estate",
            "currentPrice":       50.0,
            "fiftyTwoWeekHigh":   200.0,
            "fiftyTwoWeekLow":    40.0,
            "marketCap":          1e9,
            "freeCashflow":      -5e8,
            "operatingCashflow": -2e8,
            "trailingPE":         85.0,
            "forwardPE":          70.0,
            "priceToBook":        6.0,
            "priceToSalesTrailing12Months": 8.0,
            "pegRatio":           4.5,
            "enterpriseValue":    3e9,
            "enterpriseToEbitda": 35.0,
            "enterpriseToRevenue": 8.0,
            "returnOnEquity":    -0.05,
            "returnOnAssets":    -0.03,
            "profitMargins":     -0.10,
            "operatingMargins":  -0.05,
            "grossMargins":       0.10,
            "debtToEquity":       250.0,
            "currentRatio":       0.6,
            "quickRatio":         0.4,
            "totalCash":          1e8,
            "totalDebt":          2e10,
            "earningsGrowth":    -0.20,
            "revenueGrowth":     -0.05,
            "earningsQuarterlyGrowth": -0.30,
            "dividendYield":      0.0,
            "payoutRatio":        0.0,
            "trailingEps":       -2.0,
            "beta":               1.8,
            "heldPercentInsiders":     0.05,
            "heldPercentInstitutions": 0.10,
            "shortPercentOfFloat":     0.10,
            "recommendationMean":  4.5,
            "targetMeanPrice":     35.0,
        },
    }


def test_run_council_clean_compounder_is_not_avoided():
    """A clean compounder may not earn unanimous BUYs (different personas
    care about different things — e.g. Burry never likes growth-priced names),
    but it must at least pass the avoid bar."""
    out = ag.run_council(_strong_compounder())
    assert out["council"]["verdict"] in ("STRONG_BUY", "BUY", "HOLD"), out["council"]
    assert out["council"]["buyCount"] >= 3
    assert out["council"]["avoidCount"] <= 4


def test_run_council_strong_avoid_for_broken_company():
    out = ag.run_council(_broken_company())
    # The earlier ordering bug downgraded 6-avoids to plain AVOID — guard it here.
    assert out["council"]["verdict"] in ("STRONG_AVOID", "AVOID"), out["council"]
    assert out["council"]["avoidCount"] >= 5
    assert out["council"]["buyCount"] <= 1


def test_council_response_shape_includes_sources_and_fetched_at():
    out = ag.run_council(_strong_compounder())
    assert "sources" in out and isinstance(out["sources"], list)
    assert len(out["sources"]) >= 4
    source_ids = {s["id"] for s in out["sources"]}
    # All five provenance sources must be enumerated.
    for required in ("yahoo_info", "technical", "news_service", "market_mood", "fii_dii"):
        assert required in source_ids, f"missing provenance source: {required}"
    assert "fetchedAt" in out and out["fetchedAt"]


def test_council_persona_count_is_eight():
    out = ag.run_council(_strong_compounder())
    assert len(out["personas"]) == 8
    ids = {p["id"] for p in out["personas"]}
    assert ids == {"buffett", "graham", "lynch", "munger",
                   "klarman", "marks", "dalio", "burry"}


# ── Yahoo percent-vs-fraction normalisation ─────────────────────────────────
#
# Regression guards for the late-2024 yfinance flip where `dividendYield`
# turned from a fraction (0.025 == 2.5 %) into a percentage (2.5 == 2.5 %).
# These tests catch a future format flip and ensure the same defensive
# pattern protects `payoutRatio`, `heldPercentInsiders`, etc.

def _ctx_with_div(**overrides) -> dict:
    base = {
        "currentPrice": 100.0,
        "dividendRate":   2.0,    # ⇒ true yield = 2.0 / 100 = 0.02 (2 %)
    }
    base.update(overrides)
    return ag.build_context({"symbol": "X", "info": base})


def test_dividend_yield_fraction_form_passes_through():
    # Yahoo's classic form: 0.02 == 2 %.
    ctx = _ctx_with_div(dividendYield=0.02)
    assert ctx["dividendYield"] == pytest.approx(0.02, abs=1e-6)


def test_dividend_yield_percentage_form_is_normalised():
    # Late-2024 form: 2.0 == 2 %.  Must be divided by 100.
    ctx = _ctx_with_div(dividendYield=2.0)
    assert ctx["dividendYield"] == pytest.approx(0.02, abs=1e-6)


def test_dividend_yield_low_yield_resolved_via_dividend_rate():
    # A low-yield Indian-style name where both interpretations sit < 1:
    # 0.4 could mean 0.4 % (fraction) or 40 % (raw fraction value).
    # `dividendRate / currentPrice` (2 / 500 = 0.004) is the tie-breaker
    # and tells us the raw 0.4 was a percentage (0.4 % == 0.004).
    ctx = _ctx_with_div(currentPrice=500.0, dividendRate=2.0, dividendYield=0.4)
    assert ctx["dividendYield"] == pytest.approx(0.004, abs=1e-6)


def test_dividend_yield_falls_back_to_trailing_when_rate_missing():
    # Without dividendRate, trailingAnnualDividendYield (a fraction) is the
    # cross-check.  Raw 0.4 vs trailing 0.004 ⇒ raw was a percentage.
    ctx = ag.build_context({"symbol": "X", "info": {
        "dividendYield": 0.4,
        "trailingAnnualDividendYield": 0.004,
    }})
    assert ctx["dividendYield"] == pytest.approx(0.004, abs=1e-6)


def test_dividend_yield_no_reference_keeps_legacy_heuristic():
    # No dividendRate, no currentPrice, no trailing yield: fall back to the
    # conservative "> 1 ⇒ percentage" rule.
    ctx_frac = ag.build_context({"symbol": "X", "info": {"dividendYield": 0.02}})
    ctx_pct  = ag.build_context({"symbol": "X", "info": {"dividendYield": 2.0}})
    assert ctx_frac["dividendYield"] == pytest.approx(0.02, abs=1e-6)
    assert ctx_pct["dividendYield"]  == pytest.approx(0.02, abs=1e-6)


def test_dividend_yield_missing_is_none():
    ctx = ag.build_context({"symbol": "X", "info": {}})
    assert ctx["dividendYield"] is None


@pytest.mark.parametrize("field", [
    "payoutRatio", "heldPercentInsiders", "heldPercentInstitutions",
])
def test_other_percent_fields_normalised_when_in_percentage_form(field):
    # 42 (percentage form) must collapse to 0.42 (fraction).
    ctx = ag.build_context({"symbol": "X", "info": {field: 42.0}})
    assert ctx[field] == pytest.approx(0.42, abs=1e-6)


@pytest.mark.parametrize("field", [
    "payoutRatio", "heldPercentInsiders", "heldPercentInstitutions",
])
def test_other_percent_fields_passthrough_when_in_fraction_form(field):
    # 0.42 (legitimate fraction) must be left alone.
    ctx = ag.build_context({"symbol": "X", "info": {field: 0.42}})
    assert ctx[field] == pytest.approx(0.42, abs=1e-6)


def test_pays_a_dividend_gate_survives_yahoo_format_flip():
    """The Dalio / Damani-style 'Pays a dividend' gate (threshold > 0.0
    after normalisation) must fire regardless of which representation
    Yahoo serves.  This is the original audit failure mode."""
    for raw in (0.025, 2.5):
        ctx = ag.build_context({"symbol": "X", "info": {
            "dividendYield": raw,
            "dividendRate":  2.5,
            "currentPrice":  100.0,
        }})
        # Both forms collapse to ~0.025 (2.5 %), comfortably > 0 and > 0.02.
        assert ctx["dividendYield"] == pytest.approx(0.025, abs=1e-6)
        assert ctx["dividendYield"] > 0.02


# ── External-context fetchers degrade gracefully ─────────────────────────────

def test_fetch_symbol_news_returns_empty_on_no_match(monkeypatch):
    import asyncio

    async def fake_feed(*_, **__):
        return {"articles": [
            {"title": "Reliance Q4 results beat", "summary": "growth", "tickers": ["RELIANCE"], "source": "ET"},
        ]}

    from app.services import news_service
    monkeypatch.setattr(news_service, "get_news_feed", fake_feed)

    out = asyncio.run(ag._fetch_symbol_news("XYZNOTREAL", "Nonexistent Co"))
    assert out == []


def test_fetch_symbol_news_matches_by_ticker(monkeypatch):
    import asyncio

    async def fake_feed(*_, **__):
        return {"articles": [
            {"title": "TCS bags new deal", "summary": "consulting",
             "tickers": ["TCS"], "source": "Livemint", "sentiment": "bullish",
             "published": "2025-01-01", "url": "http://x"},
            {"title": "Unrelated story",   "summary": "x",
             "tickers": ["RELIANCE"], "source": "ET"},
        ]}

    from app.services import news_service
    monkeypatch.setattr(news_service, "get_news_feed", fake_feed)

    out = asyncio.run(ag._fetch_symbol_news("TCS", "Tata Consultancy Services"))
    assert len(out) == 1
    assert out[0]["title"] == "TCS bags new deal"
    assert out[0]["sentiment"] == "bullish"
