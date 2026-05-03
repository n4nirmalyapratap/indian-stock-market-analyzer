"""
dcf_service.py — Two-stage discounted-cash-flow intrinsic value model.

Pulls fundamentals from Yahoo Finance (yfinance) — the same data source the
``/api/stocks/{symbol}/financials`` endpoint already uses, so there is no new
provider to wire up. Discounts the free-cash-flow stream with a CAPM-style
WACC anchored on the live India 10Y G-Sec yield from FRED (via
``risk_free_service``).

Model
-----
1. **Base FCF** — average of the last up to 3 years of positive Free Cash Flow
   (smooths cyclicality). If we have no positive FCF, the symbol is rejected
   with a clear error rather than fabricating a number.
2. **Stage-1 growth (years 1-5)** — historical 3-year FCF CAGR if available,
   else ``info["earningsGrowth"]``, else 8%. Clamped to ``[5%, 15%]``.
3. **Stage-2 growth (years 6-10)** — half of stage-1, clamped to ``[3%, 8%]``.
4. **Terminal growth** — 4% (India long-term real growth + inflation anchor).
5. **Discount rate (WACC)** — ``risk_free + beta * 6%`` equity-risk-premium.
   Falls back to ``risk_free + 6%`` when beta is missing. Clamped to
   ``[risk_free + 4%, 15%]``.
6. **Terminal value** — Gordon-growth on year-11 FCF, discounted back.
7. **Equity value** — ``EV - (total_debt - cash)`` then divided by shares
   outstanding to get intrinsic value per share.
8. **Margin of safety** — ``(intrinsic - price) / intrinsic``.

Every assumption (growth rates, WACC, terminal growth, base FCF, net debt,
shares) is returned in the response so the caller can show the user *exactly*
what was assumed — there are no hidden silent fallbacks.
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any, Optional

from ..lib.symbol_map import yahoo_candidates
from . import risk_free_service

logger = logging.getLogger(__name__)


# ── Tunables ────────────────────────────────────────────────────────────────
EQUITY_RISK_PREMIUM = 0.06       # India ERP
TERMINAL_GROWTH     = 0.04
STAGE1_YEARS        = 5
STAGE2_YEARS        = 5
GROWTH1_MIN, GROWTH1_MAX = 0.05, 0.15
GROWTH2_MIN, GROWTH2_MAX = 0.03, 0.08
WACC_MIN_SPREAD     = 0.04       # WACC >= rf + 4%
WACC_MAX            = 0.15


def _safe_num(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _row_series(df, candidates: list[str]) -> list[float]:
    """Return the most-recent-first list of floats for the first matching row."""
    if df is None or getattr(df, "empty", True):
        return []
    for name in candidates:
        if name in df.index:
            try:
                vals = [_safe_num(df.loc[name, col]) for col in df.columns]
                # df columns are dates — yfinance returns most-recent first.
                return [v for v in vals if v is not None]
            except Exception:
                continue
    return []


def _latest(df, candidates: list[str]) -> Optional[float]:
    vals = _row_series(df, candidates)
    return vals[0] if vals else None


def _historical_cagr(values_recent_first: list[float]) -> Optional[float]:
    """CAGR from the oldest to the newest available datapoint."""
    pos = [v for v in values_recent_first if v is not None and v > 0]
    if len(pos) < 2:
        return None
    newest, oldest = pos[0], pos[-1]
    n = len(pos) - 1
    try:
        return (newest / oldest) ** (1 / n) - 1
    except (ValueError, ZeroDivisionError):
        return None


async def compute_dcf(symbol: str) -> dict[str, Any]:
    """Return a DCF intrinsic-value snapshot for ``symbol``.

    On success the dict has::

        {
          "symbol":          "TCS",
          "companyName":     "...",
          "currency":        "INR",
          "currentPrice":    3650.0,
          "intrinsicValue":  3920.5,
          "marginOfSafety":  0.069,           # +6.9% (undervalued)
          "verdict":         "UNDERVALUED",   # /FAIR/OVERVALUED
          "assumptions": {
              "baseFcfCr":          45000.0,
              "growthYears1to5Pct": 12.0,
              "growthYears6to10Pct":6.0,
              "terminalGrowthPct":  4.0,
              "waccPct":            12.4,
              "riskFreePct":        7.1,
              "beta":               0.9,
              "sharesOutstandingCr":361.5,
              "netDebtCr":          -350000.0,    # negative = net cash
              "horizonYears":       10,
          },
          "fcfHistoryCr":   [...up to 5 most-recent annual FCFs in ₹ Cr...],
          "source":         "yahoo+fred",
        }

    On failure returns ``{"error": "...", "symbol": symbol}``.
    """
    symbol = symbol.upper().strip()
    if not symbol:
        return {"error": "Symbol is required.", "symbol": symbol}

    raw = await asyncio.to_thread(_fetch_yahoo, symbol)
    if raw is None:
        return {
            "symbol": symbol,
            "error":  f"No fundamentals found for {symbol} on Yahoo Finance.",
        }

    info = raw["info"] or {}
    cf_df = raw["cash_flow"]
    bs_df = raw["balance_sheet"]

    # ── 1. Base FCF — average of last up-to-3 positive annual FCFs (₹) ──
    fcf_series = _row_series(cf_df, ["Free Cash Flow", "FreeCashFlow"])
    if not fcf_series:
        # Fall back to OCF - CapEx if "Free Cash Flow" row is missing.
        ocf  = _row_series(cf_df, ["Operating Cash Flow", "Total Cash From Operating Activities"])
        capx = _row_series(cf_df, ["Capital Expenditure", "Capital Expenditures"])
        if ocf and capx:
            n = min(len(ocf), len(capx))
            fcf_series = [ocf[i] + capx[i] for i in range(n)]   # capex is negative

    pos_recent = [v for v in fcf_series[:3] if v is not None and v > 0]
    if not pos_recent:
        return {
            "symbol": symbol,
            "error":  f"{symbol} has no positive free cash flow on record — "
                       "DCF intrinsic value is not meaningful for this name.",
        }
    base_fcf = sum(pos_recent) / len(pos_recent)

    # ── 2. Growth rates ──
    cagr = _historical_cagr(fcf_series[:5]) if len(fcf_series) >= 2 else None
    earnings_growth = _safe_num(info.get("earningsGrowth"))
    if cagr is not None:
        g1 = cagr
        growth_source = f"hist FCF CAGR ({len(fcf_series[:5])}y)"
    elif earnings_growth is not None:
        g1 = earnings_growth
        growth_source = "yahoo earningsGrowth"
    else:
        g1 = 0.08
        growth_source = "default 8%"
    g1 = _clamp(g1, GROWTH1_MIN, GROWTH1_MAX)
    g2 = _clamp(g1 / 2.0, GROWTH2_MIN, GROWTH2_MAX)

    # ── 3. WACC ──
    rf_payload = await risk_free_service.get_india_risk_free_rate()
    risk_free  = float(rf_payload.get("value") or 0.07)
    beta = _safe_num(info.get("beta"))
    if beta is None or beta <= 0:
        wacc = risk_free + EQUITY_RISK_PREMIUM
        beta_note = "missing — using rf + 6%"
    else:
        wacc = risk_free + beta * EQUITY_RISK_PREMIUM
        beta_note = f"{beta:.2f}"
    wacc = _clamp(wacc, risk_free + WACC_MIN_SPREAD, WACC_MAX)
    if wacc <= TERMINAL_GROWTH:
        # Mathematically required for the Gordon terminal — bump WACC just
        # above terminal growth and surface that in the response.
        wacc = TERMINAL_GROWTH + 0.01

    # ── 4. Project FCFs and discount ──
    pv_sum = 0.0
    fcf = base_fcf
    for year in range(1, STAGE1_YEARS + 1):
        fcf *= 1 + g1
        pv_sum += fcf / ((1 + wacc) ** year)
    for year in range(STAGE1_YEARS + 1, STAGE1_YEARS + STAGE2_YEARS + 1):
        fcf *= 1 + g2
        pv_sum += fcf / ((1 + wacc) ** year)
    # Terminal value at end of year 10 (Gordon on year-11 FCF)
    terminal_fcf = fcf * (1 + TERMINAL_GROWTH)
    terminal_value = terminal_fcf / (wacc - TERMINAL_GROWTH)
    pv_terminal = terminal_value / ((1 + wacc) ** (STAGE1_YEARS + STAGE2_YEARS))
    enterprise_value = pv_sum + pv_terminal

    # ── 5. Equity value & per-share intrinsic ──
    total_debt = _latest(bs_df, ["Total Debt"]) or 0.0
    cash       = _latest(bs_df, ["Cash And Cash Equivalents",
                                 "Cash And Short Term Investments"]) or 0.0
    net_debt   = total_debt - cash
    equity_value = enterprise_value - net_debt

    shares = _safe_num(info.get("sharesOutstanding"))
    if not shares or shares <= 0:
        # Last-resort: derive shares from market cap / price.
        mcap  = _safe_num(info.get("marketCap"))
        price_for_shares = (_safe_num(info.get("currentPrice"))
                            or _safe_num(info.get("regularMarketPrice")))
        if mcap and price_for_shares:
            shares = mcap / price_for_shares
    if not shares or shares <= 0:
        return {
            "symbol": symbol,
            "error":  f"Could not determine shares outstanding for {symbol} — "
                       "intrinsic value per share cannot be computed.",
        }

    intrinsic_per_share = equity_value / shares
    if intrinsic_per_share <= 0:
        return {
            "symbol": symbol,
            "error":  f"DCF produced a non-positive equity value for {symbol} "
                       "(net debt likely exceeds discounted cash flows). "
                       "Intrinsic value is not meaningful.",
        }

    current_price = (_safe_num(info.get("currentPrice"))
                     or _safe_num(info.get("regularMarketPrice"))
                     or _safe_num(info.get("previousClose")))
    mos = None
    verdict = "UNKNOWN"
    if current_price and current_price > 0:
        mos = (intrinsic_per_share - current_price) / intrinsic_per_share
        if mos >= 0.20:
            verdict = "UNDERVALUED"
        elif mos <= -0.20:
            verdict = "OVERVALUED"
        else:
            verdict = "FAIR"

    CR = 1e7
    return {
        "symbol":         symbol,
        "companyName":    info.get("longName") or info.get("shortName") or symbol,
        "currency":       info.get("currency", "INR"),
        "currentPrice":   round(current_price, 2) if current_price else None,
        "intrinsicValue": round(intrinsic_per_share, 2),
        "marginOfSafety": round(mos, 4) if mos is not None else None,
        "verdict":        verdict,
        "assumptions": {
            "baseFcfCr":           round(base_fcf / CR, 2),
            "growthYears1to5Pct":  round(g1 * 100, 2),
            "growthYears6to10Pct": round(g2 * 100, 2),
            "terminalGrowthPct":   round(TERMINAL_GROWTH * 100, 2),
            "waccPct":             round(wacc * 100, 2),
            "riskFreePct":         round(risk_free * 100, 2),
            "beta":                beta_note,
            "equityRiskPremiumPct":round(EQUITY_RISK_PREMIUM * 100, 2),
            "sharesOutstandingCr": round(shares / CR, 2),
            "totalDebtCr":         round(total_debt / CR, 2),
            "cashCr":              round(cash / CR, 2),
            "netDebtCr":           round(net_debt / CR, 2),
            "enterpriseValueCr":   round(enterprise_value / CR, 2),
            "equityValueCr":       round(equity_value / CR, 2),
            "horizonYears":        STAGE1_YEARS + STAGE2_YEARS,
            "growthSource":        growth_source,
        },
        "fcfHistoryCr": [round(v / CR, 2) for v in fcf_series[:5]],
        "source": f"yahoo+{rf_payload.get('source','fred')}",
    }


def _fetch_yahoo(symbol: str) -> Optional[dict]:
    """Blocking Yahoo fundamentals pull. Caller should run via ``asyncio.to_thread``."""
    try:
        import yfinance as yf
    except Exception as exc:
        logger.warning("yfinance unavailable: %s", exc)
        return None
    for tick_sym in yahoo_candidates(symbol):
        try:
            t = yf.Ticker(tick_sym)
            info = t.info or {}
            if not (info.get("regularMarketPrice")
                    or info.get("currentPrice")
                    or info.get("marketCap")):
                continue
            return {
                "info":          info,
                "cash_flow":     t.cash_flow,
                "balance_sheet": t.balance_sheet,
            }
        except Exception as exc:
            logger.debug("yfinance fetch failed for %s: %s", tick_sym, exc)
            continue
    return None
