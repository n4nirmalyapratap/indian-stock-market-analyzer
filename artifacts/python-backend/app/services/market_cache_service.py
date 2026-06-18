"""
Market Data Disk Cache  (EOD-aware)
====================================
NSE market hours: 9:15 AM – 3:30 PM IST (Mon-Fri)

Every snapshot saved to disk is wrapped with provenance metadata so callers
can tell whether the data is intraday or an official end-of-day close:

    {
      "savedAt":     "2026-05-02T15:32:11+05:30",   # IST timestamp
      "marketState": "CLOSED",                       # OPEN / CLOSED / PRE_OPEN / WEEKEND
      "eodSealed":   true,                            # was this saved AFTER 15:30 IST on a trading day?
      "eodDate":     "2026-05-02",                    # the trading date this snapshot belongs to
      "source":      "NSE",                           # where the data came from
      "data":        [...]
    }

Loading helpers:
  - `load_from_disk(symbol, days)`   → raw `data` list (back-compat)
  - `load_with_meta(symbol, days)`   → full wrapped dict or None

Cache versioning:
  Every market-state transition (CLOSED → OPEN, OPEN → CLOSED) bumps
  `cache_version()`, which the in-memory caches in nse_service / yahoo_service
  consult to drop stale entries automatically.

Cache location:  artifacts/python-backend/market_cache/<date>/<SYMBOL>_<days>.json
Status endpoint: GET  /api/cache/status
Warmup endpoint: POST /api/cache/warmup
"""

import json
import os
import asyncio
import threading
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Optional, Any

_CACHE_ROOT = Path(__file__).parent.parent.parent / "market_cache"

IST = timezone(timedelta(hours=5, minutes=30))

# ── Market state versioning ──────────────────────────────────────────────────
# A monotonic counter — bumps on every market-state transition (e.g. CLOSED → OPEN).
# In-memory caches in nse_service / yahoo_service consult `cache_version()` and
# drop their entries when the version changes.
_state_lock = threading.Lock()
_last_state: Optional[str] = None
_cache_version: int = 0


def _now_ist() -> datetime:
    return datetime.now(tz=IST)


def is_market_open() -> bool:
    now = _now_ist()
    if now.weekday() >= 5:
        return False
    market_open  = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close


def current_market_state() -> str:
    """Return one of OPEN | PRE_OPEN | CLOSED | WEEKEND."""
    now = _now_ist()
    if now.weekday() >= 5:
        return "WEEKEND"
    market_open  = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    if now < market_open:
        return "PRE_OPEN"
    if now <= market_close:
        return "OPEN"
    return "CLOSED"


def bump_cache_version_if_needed() -> int:
    """
    Bump `_cache_version` whenever the market state has just transitioned.
    Callers should invoke this *before* reading their in-memory caches and
    invalidate anything older than the returned version.
    """
    global _last_state, _cache_version
    state = current_market_state()
    with _state_lock:
        if state != _last_state:
            _cache_version += 1
            _last_state = state
        return _cache_version


def cache_version() -> int:
    """Return the current cache version (bumps on every market-state transition)."""
    return bump_cache_version_if_needed()


def last_trading_date() -> str:
    """Return the most recent trading day's date (YYYY-MM-DD in IST).

    Before 9:15 AM IST on a weekday, the previous trading day is returned —
    so an intraday quote saved before market opens is still bucketed under
    yesterday (its actual EOD date). The cutoff is 9:15 (market open),
    not 9:00, so the entire pre-open window (09:00–09:14) buckets to
    yesterday's EOD — same as `_eod_date_for('PRE_OPEN')`.
    """
    now = _now_ist()
    d = now.date()
    # Pre-open on a weekday → previous trading session
    if now.weekday() < 5 and (now.hour, now.minute) < (9, 15):
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def _eod_date_for(state: str) -> str:
    """Return the trading date this snapshot logically belongs to.

    OPEN / PRE_OPEN → today's date (intraday).
    CLOSED         → today's date (EOD bucket).
    WEEKEND        → most recent Friday.
    """
    now = _now_ist()
    if state == "WEEKEND":
        d = now.date()
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d.isoformat()
    if state == "PRE_OPEN":
        # Pre-open snapshots reflect yesterday's close
        d = now.date() - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d.isoformat()
    return now.date().isoformat()


def _cache_path(symbol: str, days: int) -> Path:
    date_dir = _CACHE_ROOT / last_trading_date()
    date_dir.mkdir(parents=True, exist_ok=True)
    return date_dir / f"{symbol}_{days}.json"


def _canonical_path(symbol: str) -> Path:
    """Single canonical snapshot per symbol per trading date.

    Used so that quote, history (any period), sector, and admin-audit
    endpoints all read the SAME sealed close regardless of how many
    days they request.
    """
    date_dir = _CACHE_ROOT / last_trading_date()
    date_dir.mkdir(parents=True, exist_ok=True)
    return date_dir / f"{symbol}.json"


def _wrap(data: Any, source: str) -> dict:
    state = current_market_state()
    return {
        "savedAt":     _now_ist().isoformat(),
        "marketState": state,
        "eodSealed":   state in ("CLOSED", "WEEKEND"),
        "eodDate":     _eod_date_for(state),
        "source":      source,
        "data":        data,
    }


def _read_payload(p: Path) -> Optional[dict]:
    try:
        if not p.exists():
            return None
        with open(p, "r") as f:
            payload = json.load(f)
        if isinstance(payload, list):
            return {
                "savedAt":     None,
                "marketState": "UNKNOWN",
                "eodSealed":   False,
                "eodDate":     last_trading_date(),
                "source":      "LEGACY",
                "data":        payload,
            }
        if isinstance(payload, dict) and "data" in payload:
            return payload
        return None
    except Exception:
        return None


def load_with_meta(symbol: str, days: int) -> Optional[dict]:
    """Return the full wrapped payload sliced to the last `days` rows, or None.

    Read priority — canonical snapshot first (so every endpoint shares the
    same sealed EOD close regardless of `days` requested), then fall back
    to the legacy per-days file.
    """
    canonical = _read_payload(_canonical_path(symbol))
    if canonical and canonical.get("data"):
        rows = canonical["data"]
        sliced = rows[-days:] if isinstance(rows, list) and len(rows) > days else rows
        return {**canonical, "data": sliced}
    return _read_payload(_cache_path(symbol, days))


def load_from_disk(symbol: str, days: int) -> Optional[list]:
    """Back-compat helper — return just the raw data list (or None)."""
    payload = load_with_meta(symbol, days)
    if not payload:
        return None
    data = payload.get("data")
    return data if data else None


def is_eod_snapshot(payload: Optional[dict]) -> bool:
    """Return True iff the wrapped payload was sealed after market close."""
    return bool(payload and payload.get("eodSealed"))


def save_to_disk(symbol: str, days: int, data: Any, source: str = "UNKNOWN") -> None:
    try:
        if not data:
            return
        wrapped = _wrap(data, source)

        # Don't overwrite an EOD-sealed snapshot with intraday data for the same day —
        # protects the official close from being clobbered by a pre-open / late refresh.
        existing = _read_payload(_cache_path(symbol, days))
        if existing and existing.get("eodSealed") and current_market_state() in ("OPEN", "PRE_OPEN"):
            return
        with open(_cache_path(symbol, days), "w") as f:
            json.dump(wrapped, f)

        # Update canonical snapshot — keep whichever payload has more rows
        # (so every endpoint can read the same file regardless of `days`).
        canon_path = _canonical_path(symbol)
        canon_existing = _read_payload(canon_path)
        canon_rows = len((canon_existing or {}).get("data") or []) if canon_existing else 0
        new_rows   = len(data) if isinstance(data, list) else 0
        intraday   = current_market_state() in ("OPEN", "PRE_OPEN")
        canon_sealed = bool(canon_existing and canon_existing.get("eodSealed"))
        # Don't clobber a sealed canonical with intraday during the live session
        if canon_sealed and intraday:
            return
        # Prefer the LONGER series — never shrink the shared canonical. The old
        # rule also wrote on ANY sealed payload (`or wrapped.eodSealed`), so a
        # short EOD seal (e.g. 63 rows from a 90-day request) clobbered a longer
        # 247-row canonical and shadowed that history from every reader
        # (load_with_meta reads the canonical first). A sealed write of
        # equal-or-greater length still wins, which is what upgrades the
        # intraday canonical to the sealed EOD close.
        if new_rows >= canon_rows:
            with open(canon_path, "w") as f:
                json.dump(wrapped, f)
        elif wrapped.get("eodSealed") and not canon_sealed and canon_existing:
            # New sealed payload is SHORTER than an as-yet-unsealed canonical
            # (e.g. a seal re-fetch returned a few fewer rows). Merge by date:
            # keep the longer history, overlay the official sealed bars, and
            # mark it sealed — so we neither shrink the canonical nor leave it
            # unsealed (which would re-trigger sealing on every quote).
            by_date = {
                r["date"]: r for r in (canon_existing.get("data") or [])
                if isinstance(r, dict) and r.get("date")
            }
            for r in data:
                if isinstance(r, dict) and r.get("date"):
                    by_date[r["date"]] = r
            merged = sorted(by_date.values(), key=lambda r: r["date"])
            with open(canon_path, "w") as f:
                json.dump(_wrap(merged, source), f)
    except Exception:
        pass


def cache_status() -> dict:
    date_str = last_trading_date()
    date_dir = _CACHE_ROOT / date_str
    files = sorted(date_dir.glob("*.json")) if date_dir.exists() else []
    cached_count = len(files)

    eod_sealed = 0
    intraday   = 0
    for f in files[:50]:  # sample first 50 files for speed
        try:
            with open(f, "r") as fh:
                payload = json.load(fh)
            if isinstance(payload, dict) and payload.get("eodSealed"):
                eod_sealed += 1
            else:
                intraday += 1
        except Exception:
            pass

    return {
        "marketOpen":       is_market_open(),
        "marketState":      current_market_state(),
        "cacheVersion":     cache_version(),
        "cacheDate":        date_str,
        "cachedSymbols":    cached_count,
        "cacheRoot":        str(_CACHE_ROOT),
        "servingFromCache": not is_market_open() and cached_count > 0,
        "thin":             cached_count < 25,
        "sampledEodSealed": eod_sealed,
        "sampledIntraday":  intraday,
    }


async def seal_eod_for_today_if_overdue(price_service, symbols: Optional[list[str]] = None,
                                         max_concurrency: int = 10) -> dict:
    """
    When the market is CLOSED but the on-disk snapshot for today was saved
    intraday (eodSealed=False), force one re-fetch and overwrite with an
    EOD-sealed snapshot.

    Symbols defaults to all symbols that already have a cache file today.
    Returns a summary dict.
    """
    state = current_market_state()
    if state not in ("CLOSED", "WEEKEND"):
        return {"sealed": 0, "checked": 0, "skippedReason": f"market is {state}"}

    date_str = last_trading_date()
    date_dir = _CACHE_ROOT / date_str
    if not date_dir.exists():
        return {"sealed": 0, "checked": 0, "skippedReason": "no cache dir"}

    candidates: list[tuple[str, int]] = []
    promoted = 0  # count of sealed per-days files promoted to canonical

    if symbols:
        # For each requested symbol gather BOTH the canonical file and any
        # per-days buckets that exist (e.g. <SYM>.json, <SYM>_30.json,
        # <SYM>_90.json, <SYM>_180.json). Previously we only checked _90 which
        # silently skipped sealing when the only on-disk artefact was the
        # canonical snapshot or a different bucket.
        files_to_check: list[Path] = []
        for s in symbols:
            files_to_check.append(date_dir / f"{s}.json")
            files_to_check.extend(date_dir.glob(f"{s}_*.json"))
    else:
        files_to_check = list(date_dir.glob("*.json"))

    unsealed_max: dict[str, int] = {}  # sym → largest unsealed `days` bucket to seal
    for f in files_to_check:
        try:
            stem = f.stem  # "RELIANCE_90" (per-days bucket) or "RELIANCE" (canonical)
            if "_" in stem:
                sym, days_str = stem.rsplit("_", 1)
                try:
                    days = int(days_str)
                except ValueError:
                    # Symbol legitimately contains an underscore (e.g.
                    # NIFTY_FIN_SERVICE) and the suffix isn't a day count —
                    # treat the whole stem as canonical for that symbol.
                    sym, days = stem, 90
            else:
                sym, days = stem, 90  # canonical file → use a sane default
            payload = _read_payload(f)
            if payload is None:
                continue
            if not payload.get("eodSealed"):
                # Seal the LONGEST unsealed bucket per symbol. Sealing only the
                # first one found (often the shortest) sealed a short series
                # which — combined with the canonical write rule — left the
                # canonical truncated, shadowing the longer history on disk.
                if days > unsealed_max.get(sym, -1):
                    unsealed_max[sym] = days
                continue
            # Already sealed — make sure the canonical snapshot exists so
            # quote/history/sectors all read the same close.
            canon_path = _canonical_path(sym)
            canon = _read_payload(canon_path)
            canon_rows = len((canon or {}).get("data") or []) if canon else 0
            new_rows = len(payload.get("data") or [])
            if not canon or new_rows > canon_rows:
                with open(canon_path, "w") as fh:
                    json.dump(payload, fh)
                promoted += 1
        except Exception:
            continue

    candidates = list(unsealed_max.items())
    if not candidates:
        return {"sealed": 0, "checked": len(files_to_check), "promoted": promoted}

    sem = asyncio.Semaphore(max_concurrency)
    sealed = 0
    errors = 0

    async def _seal_one(sym: str, days: int):
        nonlocal sealed, errors
        async with sem:
            try:
                data = await price_service.get_historical_data(sym, days, force_refresh=True)
                if data:
                    sealed += 1
            except Exception:
                errors += 1
            await asyncio.sleep(0.05)

    await asyncio.gather(*[_seal_one(s, d) for s, d in candidates])
    return {"sealed": sealed, "checked": len(files_to_check), "errors": errors,
            "promoted": promoted, "cacheDate": date_str}


async def warmup_cache(price_service, batch_size: int = 10) -> dict:
    """
    Pre-fetch and cache historical data for ALL universe symbols.
    Uses PriceService so each symbol tries NSE first, then Yahoo fallback.
    Runs in parallel batches of `batch_size` to avoid overwhelming APIs.
    Returns a summary dict.
    """
    from ..lib.universe import get_scan_universe

    # Warm the FULL tradeable universe (~2,000) so the cache-first scans
    # (screener / patterns / scanners) read EOD data from disk and run fast.
    # Order-stable & deduped; gentle batch_size + per-fetch sleep keep providers
    # happy across the larger set.
    all_symbols = get_scan_universe()
    total = len(all_symbols)
    saved = 0
    errors = 0

    async def fetch_one(sym: str):
        nonlocal saved, errors
        for days in [90, 300]:
            existing = load_with_meta(sym, days)
            # Skip only if we already have an EOD-sealed snapshot for today
            if existing and existing.get("eodSealed"):
                continue
            try:
                data = await price_service.get_historical_data(sym, days)
                if data:
                    saved += 1
            except Exception:
                errors += 1
            await asyncio.sleep(0.15)

    for i in range(0, total, batch_size):
        batch = all_symbols[i : i + batch_size]
        await asyncio.gather(*[fetch_one(s) for s in batch])

    return {
        "totalSymbols": total,
        "filesSaved":   saved,
        "errors":       errors,
        "cacheDate":    last_trading_date(),
        "marketState":  current_market_state(),
    }
