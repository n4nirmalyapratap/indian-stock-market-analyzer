"""
Anti-FOMO bias-rate check.

Many retail mistakes look the same: a stock has already run 8-15% above its
20-day moving average and *that's* when the BUY/CALL signal fires. By the
time the user clicks, the easy edge is gone and a routine pullback wipes the
position. We catch that case before issuing a BUY-style verdict.

Rule:
    bias_pct = (last_price - ma20) / ma20 * 100

    if bias_pct > BIAS_THRESHOLD_PCT (default 5%):
        the stock is "extended" — a BUY signal is downgraded to a watch
        and a warning is attached for the user.

Auto-relax for strong trends:
    If MA5 > MA10 > MA20 (a clean trend stack), we widen the threshold
    by RELAX_MULT (default 1.6×) — strong trends legitimately push bias
    higher and forcing them back to ≤5% would suppress every momentum
    setup.

Configurable via environment:
    BIAS_THRESHOLD          default 5.0   (percent)
    BIAS_RELAX_MULTIPLIER   default 1.6
    BIAS_CHECK_ENABLED      default true  (set "false" to disable)
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from . import indicators

logger = logging.getLogger(__name__)


def _f(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        return float(raw) if raw else default
    except (TypeError, ValueError):
        return default


def _b(name: str, default: bool) -> bool:
    raw = (os.environ.get(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def is_enabled() -> bool:
    return _b("BIAS_CHECK_ENABLED", True)


def bias_threshold_pct() -> float:
    return _f("BIAS_THRESHOLD", 5.0)


def bias_relax_multiplier() -> float:
    return _f("BIAS_RELAX_MULTIPLIER", 1.6)


def _strong_trend(ma5: Optional[float], ma10: Optional[float],
                  ma20: Optional[float]) -> bool:
    """MA5 > MA10 > MA20 — clean trend stack (no inversions, no equal values)."""
    if ma5 is None or ma10 is None or ma20 is None:
        return False
    return ma5 > ma10 > ma20


def bias_pct(last_price: Optional[float], ma20: Optional[float]) -> Optional[float]:
    """Return current bias from MA20 in percent, or None if either input is
    missing/zero."""
    if last_price is None or ma20 is None or ma20 <= 0:
        return None
    try:
        return (float(last_price) - float(ma20)) / float(ma20) * 100.0
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def assess(last_price: Optional[float],
           closes: Optional[list[float]] = None,
           ma5: Optional[float] = None,
           ma10: Optional[float] = None,
           ma20: Optional[float] = None) -> dict:
    """Compute the bias status for a stock.

    Either pass pre-computed MA5/10/20 directly, or pass a list of recent
    closes (oldest → newest) and we'll compute them. Both paths give the
    same result; the pre-computed path is cheaper when the caller already
    has the indicator block (e.g. the AI Analyst already loads it).

    Returns a dict:
        {
          "enabled":     bool,
          "lastPrice":   float | None,
          "ma20":        float | None,
          "biasPct":     float | None,   # current bias from MA20, signed
          "threshold":   float,           # effective threshold after relax
          "isExtended":  bool,            # True if bias > threshold
          "strongTrend": bool,            # MA5>MA10>MA20
          "warning":     str | None,      # user-facing message when extended
        }
    """
    out: dict = {
        "enabled":     is_enabled(),
        "lastPrice":   last_price,
        "ma20":        ma20,
        "biasPct":     None,
        "threshold":   bias_threshold_pct(),
        "isExtended":  False,
        "strongTrend": False,
        "warning":     None,
    }

    if not out["enabled"]:
        return out

    # If MAs weren't passed, derive from closes.
    if ma20 is None and closes:
        try:
            sma20 = indicators.calculate_sma(closes, 20)
            ma20 = float(sma20[-1]) if sma20 else None
        except Exception as exc:
            logger.warning("bias_check: SMA20 calc failed: %s", exc)
    if ma10 is None and closes:
        try:
            sma10 = indicators.calculate_sma(closes, 10)
            ma10 = float(sma10[-1]) if sma10 else None
        except Exception:
            ma10 = None
    if ma5 is None and closes:
        try:
            sma5 = indicators.calculate_sma(closes, 5)
            ma5 = float(sma5[-1]) if sma5 else None
        except Exception:
            ma5 = None

    out["ma20"] = ma20
    out["strongTrend"] = _strong_trend(ma5, ma10, ma20)

    # Relax the threshold when the trend stack is clean.
    base_threshold = bias_threshold_pct()
    effective_threshold = base_threshold * (bias_relax_multiplier() if out["strongTrend"]
                                            else 1.0)
    out["threshold"] = round(effective_threshold, 2)

    out["biasPct"] = bias_pct(last_price, ma20)
    if out["biasPct"] is None:
        return out

    if out["biasPct"] > effective_threshold:
        out["isExtended"] = True
        trend_note = " (uptrend allowance applied)" if out["strongTrend"] else ""
        out["warning"] = (
            f"Stock is trading {out['biasPct']:.1f}% above its 20-day moving "
            f"average — extended vs. the {effective_threshold:.1f}% comfort "
            f"threshold{trend_note}. Consider waiting for a pullback before "
            f"acting on a BUY signal."
        )

    return out


def downgrade_verdict_if_chasing(verdict: str, bias_assessment: dict) -> tuple[str, Optional[str]]:
    """If the verdict is BUY-style and the stock is extended, return a
    softened verdict and a warning string to attach to the report.

    Returns (verdict, warning_or_none). Non-BUY verdicts pass through
    unchanged regardless of bias.
    """
    v = (verdict or "").upper().strip()
    if v != "BUY":
        return verdict, None
    if not bias_assessment.get("enabled"):
        return verdict, None
    if not bias_assessment.get("isExtended"):
        return verdict, None
    # Downgrade BUY → HOLD (the schema's "wait and watch" bucket).
    return "HOLD", bias_assessment.get("warning")
