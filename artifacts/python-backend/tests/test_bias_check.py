"""
Unit tests for the anti-FOMO bias check.

These lock in:
  * The bias-rate math (signed percent vs MA20)
  * Strong-trend relaxation widens the threshold
  * `downgrade_verdict_if_chasing` only fires on BUY (HOLD/SELL pass through)
  * Env-var overrides for threshold / multiplier / disable
"""
from __future__ import annotations

import pytest

from app.services import bias_check as bc


# ── Math ──────────────────────────────────────────────────────────────────────

def test_bias_pct_basic():
    # 100 above an MA20 of 80 = +25%
    assert bc.bias_pct(100, 80) == pytest.approx(25.0)


def test_bias_pct_below_ma_is_negative():
    # 90 below an MA20 of 100 = −10%
    assert bc.bias_pct(90, 100) == pytest.approx(-10.0)


def test_bias_pct_handles_zero_and_none():
    assert bc.bias_pct(None, 100) is None
    assert bc.bias_pct(100, None) is None
    assert bc.bias_pct(100, 0)   is None  # divide-by-zero guarded


# ── assess() ──────────────────────────────────────────────────────────────────

def test_assess_flags_extended_buy_setup(monkeypatch):
    monkeypatch.setenv("BIAS_THRESHOLD", "5.0")
    monkeypatch.setenv("BIAS_CHECK_ENABLED", "true")
    # Price 8% above MA20, no clean trend stack (ma5 < ma10) → extended.
    out = bc.assess(last_price=108, ma20=100, ma5=104, ma10=105)
    assert out["enabled"]
    assert out["biasPct"] == pytest.approx(8.0)
    assert out["isExtended"]
    assert out["warning"]
    # No strong-trend stack (ma5 < ma10) so threshold stays at base 5%.
    assert out["threshold"] == pytest.approx(5.0)
    assert not out["strongTrend"]


def test_assess_relaxes_threshold_on_strong_trend(monkeypatch):
    monkeypatch.setenv("BIAS_THRESHOLD", "5.0")
    monkeypatch.setenv("BIAS_RELAX_MULTIPLIER", "1.6")
    monkeypatch.setenv("BIAS_CHECK_ENABLED", "true")

    # Counter-example first: ma5(98) < ma10(99) is NOT a strong uptrend stack,
    # so the threshold stays at base 5% and bias of 7% trips the warning.
    weak = bc.assess(last_price=107, ma20=100, ma10=99, ma5=98)
    assert not weak["strongTrend"]
    assert weak["threshold"] == pytest.approx(5.0)
    assert weak["isExtended"]

    # Real strong-trend stack: MA5(102) > MA10(101) > MA20(100). The threshold
    # widens to 5.0 × 1.6 = 8.0%, so a bias of 7% no longer trips the warning.
    strong = bc.assess(last_price=107, ma20=100, ma10=101, ma5=102)
    assert strong["strongTrend"]
    assert strong["threshold"] == pytest.approx(5.0 * 1.6)
    assert not strong["isExtended"]
    assert strong["warning"] is None


def test_assess_returns_disabled_marker_when_env_off(monkeypatch):
    monkeypatch.setenv("BIAS_CHECK_ENABLED", "false")
    out = bc.assess(last_price=200, ma20=100)
    assert out["enabled"] is False
    # When disabled we still surface lastPrice but never fire warnings.
    assert out["isExtended"] is False
    assert out["warning"] is None


def test_assess_derives_mas_from_closes(monkeypatch):
    monkeypatch.setenv("BIAS_THRESHOLD", "5.0")
    monkeypatch.setenv("BIAS_CHECK_ENABLED", "true")
    # 25 ascending closes — MA20 of last 20 = mean(5..24) = 14.5
    closes = [float(i) for i in range(25)]
    out = bc.assess(last_price=24.0, closes=closes)
    assert out["ma20"] is not None
    assert out["biasPct"] is not None
    # 24 vs 14.5 = +65.5% bias — clearly extended.
    assert out["isExtended"]


# ── downgrade_verdict_if_chasing() ────────────────────────────────────────────

def test_downgrade_only_affects_buy(monkeypatch):
    monkeypatch.setenv("BIAS_THRESHOLD", "5.0")
    monkeypatch.setenv("BIAS_CHECK_ENABLED", "true")
    extended = bc.assess(last_price=120, ma20=100)
    assert extended["isExtended"]

    v, w = bc.downgrade_verdict_if_chasing("BUY", extended)
    assert v == "HOLD"
    assert w  # warning text supplied

    # HOLD/SELL pass straight through, no warning.
    assert bc.downgrade_verdict_if_chasing("HOLD", extended) == ("HOLD", None)
    assert bc.downgrade_verdict_if_chasing("SELL", extended) == ("SELL", None)
    assert bc.downgrade_verdict_if_chasing("", extended)     == ("", None)


def test_downgrade_no_op_when_not_extended(monkeypatch):
    monkeypatch.setenv("BIAS_THRESHOLD", "5.0")
    monkeypatch.setenv("BIAS_CHECK_ENABLED", "true")
    not_extended = bc.assess(last_price=103, ma20=100)
    assert not not_extended["isExtended"]
    assert bc.downgrade_verdict_if_chasing("BUY", not_extended) == ("BUY", None)


def test_downgrade_no_op_when_disabled(monkeypatch):
    monkeypatch.setenv("BIAS_CHECK_ENABLED", "false")
    disabled = bc.assess(last_price=999, ma20=100)
    # Even though 999 is wildly above MA20, the disabled flag short-circuits
    # the BUY downgrade so the verdict passes through untouched.
    v, w = bc.downgrade_verdict_if_chasing("BUY", disabled)
    assert v == "BUY"
    assert w is None
