"""Per-stock business profile — what the company does (description) plus its
canonical sector and industry — backed by a persistent on-disk cache.

Sector resolution always goes through the centralised classifier
(``sector_utils.classify_sector``):

  1. Nifty-index constituent map (most authoritative — a symbol that sits in a
     sector index is tagged from that index).
  2. If the symbol isn't in any sector index ("undecided"), we fetch the stock's
     Yahoo profile and classify its raw sector/industry string through the same
     centralised table.

Whatever we resolve — together with the business description — is written to
``app/lib/stock_profile_cache.json`` so the next lookup for the same symbol is
instant and never has to hit Yahoo again. This is the "identify once, store for
future reference" behaviour.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

from ..lib.sector_utils import classify_sector, get_sub_sector
from ..lib.symbol_map import yahoo_candidates
from ..lib import unclassified_log, sector_cache

logger = logging.getLogger(__name__)

# Sits next to universe_cache.json so all derived universe data lives together.
_CACHE_FILE = Path(__file__).parent.parent / "lib" / "stock_profile_cache.json"
# Profiles (sector / what-the-company-does) change very rarely — 90 days.
_TTL = 90 * 24 * 3600

_lock = threading.Lock()
_cache: Optional[dict[str, dict]] = None


def _load() -> dict[str, dict]:
    """Lazy-load the on-disk cache into memory (once)."""
    global _cache
    if _cache is not None:
        return _cache
    with _lock:
        if _cache is not None:
            return _cache
        if _CACHE_FILE.exists():
            try:
                with _CACHE_FILE.open(encoding="utf-8") as f:
                    _cache = json.load(f)
            except Exception as e:
                logger.warning("stock_profile: could not read cache: %s", e)
                _cache = {}
        else:
            _cache = {}
    return _cache


def _persist() -> None:
    try:
        with _CACHE_FILE.open("w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False)
    except Exception as e:
        logger.warning("stock_profile: could not write cache: %s", e)


def _short_description(text: Optional[str], max_chars: int = 600) -> Optional[str]:
    """Collapse whitespace and trim a long business summary back to a sentence
    boundary so the UI shows a tidy 'small detail', not a wall of text."""
    if not text:
        return None
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    for sep in (". ", "! ", "? "):
        idx = cut.rfind(sep)
        if idx > max_chars * 0.5:
            return cut[: idx + 1].strip()
    idx = cut.rfind(" ")
    return (cut[:idx] if idx > 0 else cut).strip() + "…"


def _fetch_yahoo_info(symbol: str) -> Optional[dict]:
    """Fetch the Yahoo profile (sector / industry / business summary). Blocking —
    call via asyncio.to_thread."""
    import yfinance as yf
    for tick in yahoo_candidates(symbol):
        try:
            info = yf.Ticker(tick).info or {}
            if info.get("longBusinessSummary") or info.get("sector") or info.get("industry"):
                return info
        except Exception:
            continue
    return None


def _shape(symbol: str, entry: dict) -> dict:
    sub_sector = get_sub_sector(symbol)
    sector     = entry.get("sector")
    industry   = entry.get("industry")
    # Log symbols that have sector data but no sub-sector classification so
    # the admin "Needs Classification" queue surfaces them automatically.
    if sector and not sub_sector:
        unclassified_log.record(symbol, sector, industry)
    return {
        "symbol":      symbol,
        "sector":      sector,
        "industry":    industry,
        "sub_sector":  sub_sector,
        "description": entry.get("description"),
        "source":      entry.get("source"),
    }


async def get_profile(symbol: str) -> dict:
    """Return {symbol, sector, industry, description, source} for a symbol.

    Serves from the persistent cache when available; otherwise resolves the
    sector centrally, fetches the description from Yahoo, stores the result, and
    returns it.
    """
    upper = symbol.upper().strip()
    cache = _load()

    entry = cache.get(upper)
    if entry and (time.time() - entry.get("fetchedAt", 0)) < _TTL:
        return _shape(upper, entry)

    # 1. Centralised sector — index-constituent map is the authoritative path.
    mapped = classify_sector(None, upper)
    index_sector = mapped if mapped != "Other" else None

    # 2. Yahoo profile — for the description, and to identify the sector when the
    #    index map didn't ("undecided" symbols).
    info = await asyncio.to_thread(_fetch_yahoo_info, upper)

    raw_sector   = (info or {}).get("sector")
    raw_industry = (info or {}).get("industry")
    description  = _short_description((info or {}).get("longBusinessSummary"))

    if index_sector:
        sector, source = index_sector, "index-map"
    else:
        resolved = classify_sector(raw_sector or raw_industry, upper)
        sector = resolved if resolved != "Other" else None
        source = "yahoo" if sector else "unresolved"

    result_entry = {
        "sector":      sector,
        "industry":    raw_industry,
        "description": description,
        "source":      source,
        "fetchedAt":   time.time(),
    }

    # Only persist when we learned something useful — a transient Yahoo failure
    # that yields neither a sector nor a description shouldn't be cached as a
    # permanent "unknown"; we'd rather retry next time.
    if sector or description:
        with _lock:
            cache[upper] = result_entry
            _persist()
        # Also write to the runtime sector cache so the bhavcopy delivery
        # table can look up sectors for stocks not in the static curated map.
        if sector:
            sector_cache.write(upper, sector, raw_industry)

    return _shape(upper, result_entry)
