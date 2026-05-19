"""
Smart stock-search endpoints.

  GET /api/search/suggest?q=&limit=

Used by the frontend ``<StockCombobox>`` to power autocomplete on every
ticker input across the app (Dashboard, Stock Lookup, AI Analyst, Portfolio
Add-transaction, DCF, Investor Council, …).

Matching strategy — applied to both ticker codes (``RELIANCE``) and live
company names from ``COMPANY_MAP`` (``Reliance Industries Ltd``):

  1. Exact match on the ticker        — highest score
  2. Prefix match on the ticker        — high score
  3. Prefix match on the company name  — medium-high score
  4. Substring (contains) match        — lower score
  5. Fuzzy / Levenshtein               — lowest score, only if everything
                                          else returned fewer than `limit`
                                          results (otherwise it's noise)

The endpoint is cheap and read-only — runs entirely off in-memory lists
(``ALL_SYMBOLS``, ``COMPANY_MAP``) so it doesn't touch Postgres or the
upstream NSE/Yahoo feeds.
"""
from __future__ import annotations

import logging
from difflib import SequenceMatcher

from fastapi import APIRouter, Query

from ..lib import universe

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search"])


def _normalize(s: str) -> str:
    """Strip whitespace, lowercase, drop the most common ticker suffixes so
    'tcs.ns' and 'tcs-eq' still match 'TCS'."""
    s = (s or "").strip().lower()
    for suffix in ("-eq", ".ns", ".bo", ":nse", ":bse"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    return s


def _score(query_norm: str, symbol: str, company_name: str) -> tuple[int, float]:
    """Return (bucket, intra-bucket-score) where lower bucket = better match.

    Buckets:
      0 = exact ticker match
      1 = ticker starts with query
      2 = company name starts with query
      3 = ticker contains query
      4 = company name contains query
      5 = fuzzy similarity above the floor
      99 = no match
    """
    sym_lower  = symbol.lower()
    name_lower = (company_name or "").lower()

    if sym_lower == query_norm:
        return (0, -len(symbol))  # within bucket, shorter ticker first
    if sym_lower.startswith(query_norm):
        return (1, -len(query_norm) / max(1, len(sym_lower)))
    if name_lower.startswith(query_norm):
        return (2, -len(query_norm) / max(1, len(name_lower)))
    if query_norm in sym_lower:
        return (3, sym_lower.index(query_norm))
    if name_lower and query_norm in name_lower:
        return (4, name_lower.index(query_norm))

    # Fuzzy ratio — only meaningful for short typos (≥0.7 similarity).
    if len(query_norm) >= 3:
        ratio = SequenceMatcher(None, query_norm, sym_lower).quick_ratio()
        if ratio >= 0.7:
            return (5, -ratio)  # higher ratio → "smaller" intra-bucket score
        if name_lower:
            ratio_name = SequenceMatcher(None, query_norm, name_lower).quick_ratio()
            if ratio_name >= 0.7:
                return (5, -ratio_name)

    return (99, 0.0)


def _category_for(symbol: str) -> str:
    """Best-effort cap-bucket label for the suggestion UI."""
    if symbol in universe.NIFTY100:
        return "Large Cap"
    if symbol in universe.MIDCAP:
        return "Mid Cap"
    if symbol in universe.SMALLCAP:
        return "Small Cap"
    if symbol in universe.MICROCAP:
        return "Micro Cap"
    if symbol in universe.INDICES:
        return "Index"
    return ""


@router.get("/suggest")
async def suggest(
    q: str = Query("", description="Search query — ticker, company name, or partial of either."),
    limit: int = Query(10, ge=1, le=25, description="Max number of suggestions to return."),
):
    """Return autocomplete suggestions for a ticker or company name.

    Always returns 200; an empty query returns an empty list. The result
    array is sorted best-match first (see `_score`).
    """
    q_norm = _normalize(q)
    if not q_norm:
        return {"query": q, "results": []}

    company_map = universe.COMPANY_MAP
    seen_symbols: set[str] = set()
    scored: list[tuple[tuple[int, float], dict]] = []

    # Walk every known symbol exactly once. Tickers are unique by
    # construction; company names may collide but we de-dup by ticker.
    for sym in universe.ALL_SYMBOLS:
        if sym in seen_symbols:
            continue
        seen_symbols.add(sym)
        name = company_map.get(sym, "") or ""
        score = _score(q_norm, sym, name)
        if score[0] >= 99:
            continue
        scored.append((score, {
            "symbol":      sym,
            "name":        name or None,
            "category":    _category_for(sym),
        }))

    scored.sort(key=lambda pair: pair[0])
    results = [item for _score_, item in scored[:limit]]
    return {"query": q, "results": results}
