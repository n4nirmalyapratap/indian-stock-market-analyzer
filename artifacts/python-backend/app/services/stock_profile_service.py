"""Per-stock business profile — what the company does (description) plus its
canonical sector and industry — backed by a persistent on-disk cache.

Sector resolution always goes through the centralised classifier
(``sector_utils.classify_sector``):

  1. Nifty-index constituent map (most authoritative — a symbol that sits in a
     sector index is tagged from that index).
  2. If the symbol isn't in any sector index ("undecided"), we fetch the stock's
     Yahoo profile and classify its raw sector/industry string through the same
     centralised table.

Whatever we resolve — together with the business description — is persisted to
``market_cache/stock_profile_cache.json`` (flat JSON — fine on the prod SMB
mount, and it survives redeploys, unlike the old copy inside ``app/lib/`` which
reset to its committed 38 entries on every deploy). The committed
``app/lib/stock_profile_cache.json`` is still read as a seed. A background
trickle (main._stock_profile_warmup_scheduler → ``warm_profiles``) walks the
full universe so the About section fills for every listed symbol instead of
only the stocks users happened to open while Yahoo was feeling generous.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

from ..lib.sector_utils import classify_sector, get_sub_sector
from ..lib.symbol_map import yahoo_candidates
from ..lib import unclassified_log, sector_cache

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
# Persistent home (flat JSON — SMB-safe, survives deploys).
_CACHE_FILE = _BACKEND_ROOT / "market_cache" / "stock_profile_cache.json"
# Committed seed shipped with the repo — read-only starting point.
_SEED_FILE = Path(__file__).parent.parent / "lib" / "stock_profile_cache.json"
# Profiles (sector / what-the-company-does) change very rarely — 90 days.
_TTL = 90 * 24 * 3600
# ...but an entry that never got a description retries daily, not in 90 days.
_RETRY_TTL = 24 * 3600

_lock = threading.Lock()
_cache: Optional[dict[str, dict]] = None


def _read_json(path: Path) -> dict[str, dict]:
    try:
        if path.exists():
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        logger.warning("stock_profile: could not read %s: %s", path.name, e)
    return {}


def _load() -> dict[str, dict]:
    """Lazy-load the on-disk cache into memory (once): committed seed first,
    overlaid by the persistent market_cache copy (persistent wins)."""
    global _cache
    if _cache is not None:
        return _cache
    with _lock:
        if _cache is not None:
            return _cache
        merged = _read_json(_SEED_FILE)
        merged.update(_read_json(_CACHE_FILE))
        _cache = merged
    return _cache


def _persist() -> None:
    """Atomic write (tmp + replace) so a crash mid-dump can't torn-file the
    cache — _load falls back to the seed if this file is ever unreadable."""
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_FILE.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False)
        os.replace(tmp, _CACHE_FILE)
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


async def _fetch_nse_industry(symbol: str) -> tuple[Optional[str], Optional[str]]:
    """(sector, industry) from NSE's own quote payload (`industryInfo`).

    Yahoo aggressively rate-limits cloud IPs, so for the long tail of the
    ~2.4k-symbol universe the Yahoo profile fetch often returns nothing.
    NSE's quote-equity endpoint knows the sector/industry of every listed
    symbol and goes through our hardened cookie/session layer — it can't
    provide a business description, but it keeps the sector chips honest."""
    try:
        from . import registry as svc  # noqa: PLC0415 — lazy, avoids import cycle
        q = await svc.nse.get_stock_quote(symbol)
        ii = (q or {}).get("industryInfo") or {}
        sec = (ii.get("sector") or ii.get("macro") or "").strip() or None
        ind = (ii.get("industry") or ii.get("basicIndustry") or "").strip() or None
        if not (sec or ind):
            # Legacy payload shape: info.industry
            ind = ((q or {}).get("info") or {}).get("industry") or None
        return (sec, ind)
    except Exception as e:
        logger.debug("stock_profile: NSE industry lookup failed for %s: %s",
                     symbol, str(e)[:120])
        return (None, None)


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
    if entry:
        # Entries WITH a description are stable for 90 days; entries that
        # never got one (Yahoo failed / rate-limited) retry daily so the
        # About section eventually fills instead of staying blank for 90d.
        ttl = _TTL if entry.get("description") else _RETRY_TTL
        if (time.time() - entry.get("fetchedAt", 0)) < ttl:
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
    # Keep whatever description we already had if this refresh couldn't get one.
    if not description and entry:
        description = entry.get("description")

    if index_sector:
        sector, source = index_sector, "index-map"
    else:
        resolved = classify_sector(raw_sector or raw_industry, upper)
        sector = resolved if resolved != "Other" else None
        source = "yahoo" if sector else "unresolved"

    # 3. NSE fallback — when neither the index map nor Yahoo identified the
    #    stock, NSE's own quote still knows its sector/industry.
    if not sector or not raw_industry:
        nse_sector, nse_industry = await _fetch_nse_industry(upper)
        if not raw_industry and nse_industry:
            raw_industry = nse_industry
        if not sector and (nse_sector or nse_industry):
            resolved = classify_sector(nse_sector or nse_industry, upper)
            # Prefer the canonical bucket; fall back to NSE's raw sector
            # string — a real label beats an empty About section.
            sector = resolved if resolved != "Other" else nse_sector
            if sector:
                source = "nse"

    # Never regress: if this refresh learned less than the cached entry
    # (all sources down), keep the previously-known sector/industry.
    if entry:
        if not sector and entry.get("sector"):
            sector, source = entry["sector"], entry.get("source") or source
        if not raw_industry and entry.get("industry"):
            raw_industry = entry["industry"]

    result_entry = {
        "sector":      sector,
        "industry":    raw_industry,
        "description": description,
        "source":      source,
        "fetchedAt":   time.time(),
    }

    # Persist when we learned anything useful (sector, industry or
    # description) — a description-less entry still renders the sector
    # chips, and the daily _RETRY_TTL keeps trying for the description.
    # A totally empty result isn't cached; we'd rather retry next time.
    if sector or description or raw_industry:
        with _lock:
            cache[upper] = result_entry
            _persist()
        # Also write to the runtime sector cache so the bhavcopy delivery
        # table can look up sectors for stocks not in the static curated map.
        if sector:
            sector_cache.write(upper, sector, raw_industry)

    return _shape(upper, result_entry)


def _needs_warm(sym: str, cache: dict[str, dict], now: float) -> bool:
    e = cache.get(sym)
    if not e:
        return True
    if e.get("description"):
        return False
    return (now - e.get("fetchedAt", 0)) >= _RETRY_TTL


async def warm_profiles(batch: int = 60, delay_sec: float = 40.0) -> dict:
    """Trickle-fill business profiles across the whole universe.

    Called by main._stock_profile_warmup_scheduler. Processes up to `batch`
    symbols that have no profile yet (or no description and are due a daily
    retry), sleeping `delay_sec` between symbols so Yahoo never sees a
    burst. Returns {"fetched", "withDescription", "pending"}."""
    from ..lib import universe  # noqa: PLC0415

    cache = _load()
    now = time.time()
    pending = [s for s in universe.ALL_SYMBOLS if _needs_warm(s, cache, now)]
    fetched = with_desc = 0
    for sym in pending[:batch]:
        try:
            p = await get_profile(sym)
            fetched += 1
            if p.get("description"):
                with_desc += 1
        except Exception as e:
            logger.debug("stock_profile warm failed for %s: %s", sym, str(e)[:120])
        await asyncio.sleep(delay_sec)
    return {"fetched": fetched, "withDescription": with_desc,
            "pending": max(0, len(pending) - batch)}
