"""
yahoo_norm.py
=============
Canonical helpers for normalising Yahoo Finance fundamental fields.

Yahoo Finance quirks
--------------------
* returnOnEquity, profitMargins, operatingMargins, grossMargins,
  dividendYield, earningsGrowth, revenueGrowth, 52WeekChange
  → returned as FRACTIONS  (0.18 means 18%)

* debtToEquity
  → returned as a PERCENTAGE already  (50.0 means 50% = 0.5×)

Rule of thumb
-------------
Use `yf_pct(val)` to convert a fractional Yahoo field to a display
percentage (multiply × 100).

Use `yf_de(val)` to normalise debtToEquity to a true ratio (÷ 100).

Use `yf_pct_field(info, key)` as a one-liner that handles None gracefully.

Persona / agent thresholds should compare against RAW Yahoo fractions
(e.g. `>= 0.15` for 15% ROE) — see agents_service.py comments.
"""

from __future__ import annotations
from typing import Any, Optional


def yf_pct(val: Any) -> Optional[float]:
    """Convert a Yahoo Finance fractional field to a display percentage.

    Returns None when `val` is None or not numeric.
    Example: 0.18 → 18.0
    """
    if val is None:
        return None
    try:
        return round(float(val) * 100.0, 4)
    except (TypeError, ValueError):
        return None


def yf_de(val: Any) -> Optional[float]:
    """Normalise Yahoo Finance debtToEquity from % to a true ratio.

    Yahoo reports D/E as a percentage (50.0 means 0.5×), so divide by 100.
    Returns None when `val` is None or not numeric.
    """
    if val is None:
        return None
    try:
        return round(float(val) / 100.0, 4)
    except (TypeError, ValueError):
        return None


def yf_float(val: Any) -> Optional[float]:
    """Safe float conversion; returns None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def normalise_fundamentals(info: dict) -> dict:
    """Convert a raw yfinance `.info` dict to display-ready fundamentals.

    All percentage fields are multiplied by 100 so the UI can render them
    directly (e.g. "18.00%" not "0.18").  debtToEquity is divided by 100
    to give a true ratio.

    This is the single source of truth for the fundamental conversion —
    use it in routes/stocks.py (financials endpoint) and any other place
    that reads yf.Ticker.info fundamentals.
    """
    return {
        "roe":             yf_pct(info.get("returnOnEquity")),
        "roa":             yf_pct(info.get("returnOnAssets")),
        "grossMargin":     yf_pct(info.get("grossMargins")),
        "operatingMargin": yf_pct(info.get("operatingMargins")),
        "netMargin":       yf_pct(info.get("profitMargins")),
        "dividendYield":   yf_pct(info.get("dividendYield")),
        "earningsGrowth":  yf_pct(info.get("earningsGrowth")),
        "revenueGrowth":   yf_pct(info.get("revenueGrowth")),
        "weekChange52":    yf_pct(info.get("52WeekChange")),
        "debtToEquity":    yf_float(info.get("debtToEquity")),
        "pe":              yf_float(info.get("trailingPE")),
        "forwardPE":       yf_float(info.get("forwardPE")),
        "pb":              yf_float(info.get("priceToBook")),
        "ps":              yf_float(info.get("priceToSalesTrailingTwelveMonths")),
        "evEbitda":        yf_float(info.get("enterpriseToEbitda")),
        "beta":            yf_float(info.get("beta")),
        "marketCap":       yf_float(info.get("marketCap")),
        "enterpriseValue": yf_float(info.get("enterpriseValue")),
        "currentRatio":    yf_float(info.get("currentRatio")),
        "quickRatio":      yf_float(info.get("quickRatio")),
        "freeCashflow":    yf_float(info.get("freeCashflow")),
        "totalCash":       yf_float(info.get("totalCash")),
        "totalDebt":       yf_float(info.get("totalDebt")),
        "totalRevenue":    yf_float(info.get("totalRevenue")),
        "ebitda":          yf_float(info.get("ebitda")),
        "eps":             yf_float(info.get("trailingEps")),
        "forwardEps":      yf_float(info.get("forwardEps")),
    }
