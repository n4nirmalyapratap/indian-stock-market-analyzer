"""
Security registry — the single source of truth for "what is this ticker?"

Why this exists
---------------
The app pulls price data from seven sources (NSE, BSE, Yahoo, Twelve Data,
Stooq, broker APIs, history-derived synthesis). Each source has its own
notion of a symbol:

    NSE     -> "BATAINDIA"        (current ticker, EQ series)
    BSE     -> "500043"           (numeric scrip code)
    Yahoo   -> "BATAINDIA.NS"     (NSE ticker + .NS suffix)
    legacy  -> "BATA"             (popular short name in universe lists)

Without a registry, every caller has to know about every alias. That
ended in a hand-maintained `CANONICAL_ALIASES` dict that grew by one
entry every time a scanner failed in production — exactly the kind of
hidden coupling we want to eliminate.

The registry resolves any inbound symbol form to a `Security` record,
which the provider chain then projects into the right per-provider
ticker via dedicated accessors (`security.nse_symbol`, `.bse_code`,
`.yahoo_ticker`).

Resolution cascade
------------------
Input is uppercased and trimmed, then tried in order:
  1. exact match on `nse_symbol`
  2. exact match on `isin`
  3. exact match on any `alias`
  4. exact match on normalized company name (strip "Ltd"/"Limited" suffixes)
  5. fuzzy match on company name via difflib (cutoff 0.85)

The first hit wins. Misses return None — callers fall back to passing
the raw symbol through (preserving current behaviour for tickers we
don't know about, e.g. brand-new IPOs the registry hasn't refreshed yet).

Multi-source resilience
-----------------------
The registry's source-of-truth is NSE's EQUITY_L.csv, but NSE direct
fails plenty (Akamai blocks, server-IP rate limits, network glitches).
The loader tries sources in this order on every refresh:

  1. NSE direct          (archives.nseindia.com/content/equities/EQUITY_L.csv)
  2. Zerodha instruments (api.kite.trade/instruments — public, no auth)
  3. Disk cache          (data/security_registry.json — last good fetch)
  4. Bundled baseline    (app/data/security_registry_baseline.json)

If 1+2 fail and 3 has anything (even stale), we use it. If everything
fails, baseline (shipped in the repo) keeps the app functional with
~150 hand-curated entries — enough to cover Nifty 100 + every known
legacy alias.

Refresh policy
--------------
A scheduler in main.py calls `refresh()` once a day at 06:00 IST (well
after NSE's overnight CSV update). The refresh runs in the background;
existing in-memory state is only swapped on a successful full load —
partial fetches don't corrupt the registry.

Thread / async safety
---------------------
The registry is a process-global singleton built lazily on first
access. An `asyncio.Lock` serialises refreshes so concurrent callers
don't double-fetch. Reads (resolve / get_by_*) are lock-free because
the internal dicts are only ever swapped (never mutated in place).
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import re
import time
from dataclasses import dataclass, field
from difflib import get_close_matches
from pathlib import Path
from typing import Iterable, Optional

import httpx

logger = logging.getLogger("security_registry")


# ── Paths ───────────────────────────────────────────────────────────────────
#
# We resolve paths relative to THIS file rather than a CWD-dependent
# rooted constant, so the registry works in tests, scheduled tasks,
# and the main API process identically.

_THIS_DIR     = Path(__file__).resolve().parent
_BASELINE_DIR = _THIS_DIR.parent / "data"
_BASELINE_FP  = _BASELINE_DIR / "security_registry_baseline.json"

# Disk cache lives outside the package tree (in `data/` at the repo
# root) because it's runtime state, not bundled assets. We don't ship
# it; it's rebuilt from the network on first refresh.
_DISK_CACHE_DIR = _THIS_DIR.parent.parent / "data"
_DISK_CACHE_FP  = _DISK_CACHE_DIR / "security_registry.json"


# ── Network endpoints ───────────────────────────────────────────────────────

_NSE_EQUITY_L_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
_ZERODHA_DUMP_URL = "https://api.kite.trade/instruments"
# NSE's symbol-change history. Every corporate rename + demerger that
# changes a ticker is published here. Critical for resolving stale
# universe entries like LTFH (now LTF), GMRINFRA (now GMRAIRPORT),
# MOTILALOS (now MOTILALOFS), etc. — without this, the registry only
# knows current tickers and can't translate the legacy names that
# saved scanners / watchlists / universe lists still contain.
_NSE_SYMBOL_CHANGE_URL = "https://nsearchives.nseindia.com/content/equities/eq_symbolchange.csv"

# Standard browser-ish headers; NSE Akamai rejects bare httpx UA.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/csv, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# Hard timeouts — we don't want a slow NSE response blocking the
# refresh scheduler. Better to fail fast and use the disk cache.
_FETCH_TIMEOUT_S = 20.0


# ── Data shape ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Security:
    """One row in the registry — a single tradeable Indian equity.

    Why frozen=True: the registry hands these out to callers; we don't
    want a downstream bug accidentally mutating a record and corrupting
    the index. Reconstruction is cheap.

    Why slots=True: ~2000 of these live in memory at all times; slots
    saves ~30% per instance vs the default __dict__ layout.

    Field semantics:
      nse_symbol      Current canonical NSE ticker. The primary key.
      isin            Globally unique 12-char ISIN. Stable across renames.
      name            Company display name from NSE/BSE master list.
      series          Equity series (EQ, BE, SM, …). EQ = normal trading.
      bse_code        6-digit BSE scrip code; None when not dual-listed.
      yahoo_override  Manual Yahoo ticker for cases where the default
                      ``{nse_symbol}.NS`` is broken (e.g. LTIM post-merger).
                      None means "use the default".
      aliases         Legacy short names that should resolve to this
                      security. Populated from the baseline; the live
                      NSE CSV never sets these.
    """
    nse_symbol:     str
    isin:           str
    name:           str
    series:         str = "EQ"
    bse_code:       Optional[str]   = None
    yahoo_override: Optional[str]   = None
    aliases:        tuple[str, ...] = field(default_factory=tuple)

    @property
    def yahoo_ticker(self) -> str:
        """Resolve to the Yahoo Finance ticker for this security.
        Falls back to ``{nse_symbol}.NS`` when no override is set."""
        return self.yahoo_override or f"{self.nse_symbol}.NS"


# ── Internal state container ────────────────────────────────────────────────


@dataclass
class _Index:
    """Internal lookup tables. Held as one struct so we can swap the
    whole index atomically on refresh (no half-built state visible to
    concurrent readers)."""
    by_symbol:    dict[str, Security]
    by_isin:      dict[str, Security]
    by_alias:     dict[str, Security]
    by_norm_name: dict[str, Security]
    # List of all normalized names — input to difflib's fuzzy matcher.
    # Held separately because difflib wants a list, not dict keys.
    all_names:    list[str]
    # Loaded-from-where, for debugging / health endpoints.
    source_tag:   str
    loaded_at:    float


def _empty_index() -> _Index:
    return _Index({}, {}, {}, {}, [], source_tag="<empty>", loaded_at=0.0)


# ── Helpers ─────────────────────────────────────────────────────────────────


_NAME_NOISE_RE = re.compile(
    r"\b(limited|ltd|industries|company|co|corp|corporation|"
    r"private|pvt|public|the|of|india|indian)\b\.?",
    re.IGNORECASE,
)


def _normalize_name(name: str) -> str:
    """Strip corporate suffixes/noise so 'BATA INDIA LIMITED' and
    'Bata India Ltd' both collapse to 'BATA'. Used as the index key
    for name-based lookups AND as the difflib match corpus."""
    s = _NAME_NOISE_RE.sub("", (name or ""))
    s = re.sub(r"[^A-Za-z0-9& ]+", "", s)
    s = re.sub(r"\s+", " ", s).strip().upper()
    return s


def _norm(s: str) -> str:
    """Trim + upper — the lightweight canonical form used as the
    primary lookup key across the registry."""
    return (s or "").strip().upper()


def _build_index(securities: Iterable[Security], source_tag: str) -> _Index:
    """Build all lookup tables from a flat sequence of Security records.
    Late-arriving duplicates (same NSE symbol) overwrite earlier ones —
    NSE direct fetches are always preferred to baseline-shipped entries
    via the call site's ordering, not via dedup logic here."""
    by_symbol:    dict[str, Security] = {}
    by_isin:      dict[str, Security] = {}
    by_alias:     dict[str, Security] = {}
    by_norm_name: dict[str, Security] = {}
    for sec in securities:
        sym = _norm(sec.nse_symbol)
        if not sym:
            continue
        by_symbol[sym] = sec
        if sec.isin:
            by_isin[_norm(sec.isin)] = sec
        for a in sec.aliases:
            by_alias[_norm(a)] = sec
        n = _normalize_name(sec.name)
        if n:
            by_norm_name[n] = sec
    return _Index(
        by_symbol    = by_symbol,
        by_isin      = by_isin,
        by_alias     = by_alias,
        by_norm_name = by_norm_name,
        all_names    = sorted(by_norm_name.keys()),
        source_tag   = source_tag,
        loaded_at    = time.time(),
    )


# ── Loaders (one per source) ────────────────────────────────────────────────


def _load_baseline() -> list[Security]:
    """Read the bundled-in-repo baseline JSON. Always synchronous —
    it's a local file read, ~5 ms."""
    try:
        raw = json.loads(_BASELINE_FP.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("Baseline registry file missing at %s", _BASELINE_FP)
        return []
    except Exception as exc:
        logger.warning("Baseline registry parse failed: %s", exc)
        return []
    return _parse_security_list(raw.get("securities") or [])


def _load_disk_cache() -> list[Security]:
    """Read the last successful network refresh, if any."""
    if not _DISK_CACHE_FP.exists():
        return []
    try:
        raw = json.loads(_DISK_CACHE_FP.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Disk cache parse failed: %s", exc)
        return []
    return _parse_security_list(raw.get("securities") or [])


def _parse_security_list(rows: list[dict]) -> list[Security]:
    """Convert a list of dicts (baseline / cache JSON shape) into
    Security records. Quietly skips malformed rows — we'd rather have
    a smaller clean registry than poison it with garbage."""
    out: list[Security] = []
    for r in rows:
        try:
            sym  = _norm(r.get("nse_symbol") or "")
            isin = _norm(r.get("isin") or "")
            name = (r.get("name") or "").strip()
            if not sym or not name:
                continue
            aliases = tuple(_norm(a) for a in (r.get("aliases") or []) if a)
            out.append(Security(
                nse_symbol     = sym,
                isin           = isin,
                name           = name,
                series         = (r.get("series") or "EQ").upper(),
                bse_code       = r.get("bse_code") or None,
                yahoo_override = r.get("yahoo_override") or None,
                aliases        = aliases,
            ))
        except Exception:
            continue
    return out


async def _fetch_nse_equity_list() -> list[Security]:
    """Pull NSE's EQUITY_L.csv. ~2000 rows, ~120 KB, no cookies needed
    on the archives subdomain (only the live nseindia.com requires the
    session-cookie dance). Returns [] on any failure."""
    try:
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT_S, headers=_BROWSER_HEADERS) as client:
            r = await client.get(_NSE_EQUITY_L_URL)
            r.raise_for_status()
            text = r.text
    except Exception as exc:
        logger.info("NSE EQUITY_L fetch failed: %s", str(exc)[:160])
        return []
    return _parse_nse_csv(text)


def _parse_nse_csv(text: str) -> list[Security]:
    """Parse the EQUITY_L.csv format:
       SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE,
       MARKET LOT, ISIN NUMBER, FACE VALUE
    Column names have rogue spaces in the live file — we strip them."""
    out: list[Security] = []
    try:
        reader = csv.DictReader(io.StringIO(text))
        # Normalize headers (strip whitespace from each column name).
        normalised_rows = []
        if reader.fieldnames:
            cleaned = [h.strip() for h in reader.fieldnames]
            for raw in reader:
                normalised_rows.append({c: (raw.get(orig) or "").strip()
                                        for c, orig in zip(cleaned, reader.fieldnames)})
        for row in normalised_rows:
            sym  = _norm(row.get("SYMBOL") or "")
            name = row.get("NAME OF COMPANY") or ""
            isin = _norm(row.get("ISIN NUMBER") or "")
            ser  = (row.get("SERIES") or "EQ").upper()
            if not sym or not name:
                continue
            # EQ series only — we don't want SME platform listings,
            # block deals, derivatives series in the resolver corpus.
            if ser not in ("EQ", "BE"):
                continue
            out.append(Security(
                nse_symbol = sym,
                isin       = isin,
                name       = name.strip(),
                series     = ser,
            ))
    except Exception as exc:
        logger.warning("NSE CSV parse failed: %s", exc)
        return []
    return out


async def _fetch_zerodha_dump() -> list[Security]:
    """Pull Zerodha's public instruments CSV. ~80k rows (covers NSE + BSE
    + futures + options); we filter to NSE EQ only. No API key required —
    Kite exposes this dump for public download. Independent infra from
    NSE, so it survives Akamai-blocking the server's IP.

    Format columns (as of 2026):
        instrument_token, exchange_token, tradingsymbol, name,
        last_price, expiry, strike, tick_size, lot_size,
        instrument_type, segment, exchange
    """
    try:
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT_S, headers=_BROWSER_HEADERS) as client:
            r = await client.get(_ZERODHA_DUMP_URL)
            r.raise_for_status()
            text = r.text
    except Exception as exc:
        logger.info("Zerodha instruments fetch failed: %s", str(exc)[:160])
        return []
    return _parse_zerodha_csv(text)


def _parse_zerodha_csv(text: str) -> list[Security]:
    """Filter Zerodha dump to NSE equities (EQ segment). Skip everything
    else (BFO/NFO/MCX/indices/derivatives) — those aren't securities in
    our model."""
    out: list[Security] = []
    seen: set[str] = set()
    try:
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            seg  = (row.get("segment") or "").upper()
            exch = (row.get("exchange") or "").upper()
            itype = (row.get("instrument_type") or "").upper()
            # Equities only — Kite uses segment=NSE for NSE equities.
            if seg != "NSE" or exch != "NSE" or itype != "EQ":
                continue
            sym  = _norm(row.get("tradingsymbol") or "")
            name = (row.get("name") or "").strip()
            if not sym or not name or sym in seen:
                continue
            seen.add(sym)
            out.append(Security(
                nse_symbol = sym,
                isin       = "",   # Zerodha dump doesn't include ISIN
                name       = name,
                series     = "EQ",
            ))
    except Exception as exc:
        logger.warning("Zerodha CSV parse failed: %s", exc)
        return []
    return out


# ── Symbol-rename history ───────────────────────────────────────────────────


async def _fetch_nse_symbol_changes() -> dict[str, str]:
    """Pull NSE's published symbol-change history CSV.

    Why this matters: universe lists, saved watchlists, alerts, and
    scanner conditions all carry the symbol form that was current when
    they were saved. When a company renames (LTFH -> LTF) or demerges
    (GMRINFRA -> GMRAIRPORT), every stored reference goes dead. The
    rename history lets us auto-translate the old form to the current
    one so saved state keeps working without manual cleanup.

    Returns {old_symbol: current_symbol}. Chained renames (A->B->C)
    collapse to {A: C, B: C} so users typing the oldest form still
    reach today's ticker.

    Returns {} on any failure — caller treats no-data as "skip the
    rename merge" and proceeds with whatever it had.

    CSV format (as of 2026):
        SM_KEY_SYMBOL,SM_NAME,SM_NEW_SYMBOL,SM_CHANGE_DATE
        LTFH,L&T Finance Holdings Limited,LTF,2024-06-17
        GMRINFRA,GMR Infrastructure Limited,GMRAIRPORT,2023-05-31
    The exact column names sometimes shift (leading/trailing spaces);
    we look up by normalised name to absorb that.
    """
    try:
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT_S, headers=_BROWSER_HEADERS) as client:
            r = await client.get(_NSE_SYMBOL_CHANGE_URL)
            r.raise_for_status()
            text = r.text
    except Exception as exc:
        logger.info("NSE symbol-change CSV fetch failed: %s", str(exc)[:160])
        return {}

    raw_map: dict[str, str] = {}
    try:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return {}
        # Normalise headers (strip whitespace per-column).
        col_map = {h.strip().upper(): h for h in reader.fieldnames}
        old_col = col_map.get("SM_KEY_SYMBOL") or col_map.get("OLD_SYMBOL") or col_map.get("OLDSYMBOL")
        new_col = col_map.get("SM_NEW_SYMBOL") or col_map.get("NEW_SYMBOL") or col_map.get("NEWSYMBOL")
        if not old_col or not new_col:
            logger.warning("NSE symbol-change CSV: unexpected columns %s", reader.fieldnames)
            return {}
        for row in reader:
            old = _norm(row.get(old_col) or "")
            new = _norm(row.get(new_col) or "")
            if old and new and old != new:
                raw_map[old] = new
    except Exception as exc:
        logger.warning("NSE symbol-change CSV parse failed: %s", exc)
        return {}

    # Collapse chained renames so A->B->C becomes {A:C, B:C}. Without
    # this, a user typing the oldest form would resolve to the
    # intermediate form (B) which itself isn't current.
    resolved: dict[str, str] = {}
    for old in raw_map.keys():
        current = old
        seen: set[str] = set()
        # Follow the chain. Guard against accidental cycles in the
        # source data — break out the moment we revisit a node.
        while current in raw_map and current not in seen:
            seen.add(current)
            current = raw_map[current]
        if current != old:
            resolved[old] = current
    logger.info("NSE symbol-change history: %d renames loaded", len(resolved))
    return resolved


def _apply_symbol_changes(
    merged: list[Security],
    rename_map: dict[str, str],
) -> list[Security]:
    """Attach renamed historical symbols as aliases on their current
    Security. Mutates nothing — returns a new list. Renames whose
    target isn't in our index are silently dropped (the target was
    likely delisted post-rename; aliasing to nothing helps no one).

    Idempotent: a Security that already has the alias just gets a
    set-union that preserves it."""
    if not rename_map:
        return merged
    by_symbol = {_norm(s.nse_symbol): s for s in merged}
    # Build {current_symbol: set(old_symbols)}.
    extras: dict[str, set[str]] = {}
    for old, new in rename_map.items():
        if new not in by_symbol:
            continue
        # If the OLD symbol itself is now a *different* live security
        # (unlikely but possible: NSE reuses delisted tickers years
        # later), don't shadow it.
        if old in by_symbol:
            continue
        extras.setdefault(new, set()).add(old)
    if not extras:
        return merged

    out: list[Security] = []
    for sec in merged:
        key = _norm(sec.nse_symbol)
        adds = extras.get(key)
        if adds:
            sec = Security(
                nse_symbol     = sec.nse_symbol,
                isin           = sec.isin,
                name           = sec.name,
                series         = sec.series,
                bse_code       = sec.bse_code,
                yahoo_override = sec.yahoo_override,
                aliases        = tuple(sorted(set(sec.aliases) | adds)),
            )
        out.append(sec)
    return out


def _merge_sources(*lists: list[Security]) -> list[Security]:
    """Combine multiple loader outputs into one deduplicated list.
    Earlier args take priority — so call order is "best source first".

    Two-pass dedup:
      1. Symbol-level: first source wins for any given NSE symbol.
      2. ISIN-level: when the live NSE list and the baseline both
         carry an entry for the *same security* but under different
         symbols (e.g. live has ETERNAL with ISIN INE758T01015, the
         baseline still has the old ZOMATO with the same ISIN), the
         older entry is folded into the newer as an alias — never as
         a parallel by_symbol record. Without this, the stale baseline
         symbol leaks into `by_symbol` and the resolver returns the
         wrong canonical ticker, which is the exact bug scanners hit
         on ZOMATO, MAMAEARTH, TIPSINDLTD, etc.

    The "newer" decision rule: the first list wins because it's the
    higher-priority source. Live NSE comes before baseline in the
    caller, so live always wins the canonical symbol. The baseline's
    symbol becomes an alias on the live entry."""
    # Pass 1 — symbol dedup, with alias accumulation.
    merged: dict[str, Security] = {}
    extra_aliases: dict[str, set[str]] = {}
    for src in lists:
        for sec in src:
            key = _norm(sec.nse_symbol)
            if key not in merged:
                merged[key] = sec
            # Always accumulate aliases regardless of which source won
            # the symbol — the baseline supplies BATA->BATAINDIA, and
            # we want that alias even after NSE supplies BATAINDIA.
            if sec.aliases:
                extra_aliases.setdefault(key, set()).update(sec.aliases)

    # Pass 2 — ISIN collision detection. Walk every (symbol -> Security)
    # pair and group by ISIN. For each group with >1 symbols, the FIRST
    # symbol encountered (which is the higher-priority source's choice
    # by construction of pass 1) keeps its canonical slot; the others
    # are folded in as aliases and removed from the symbol map.
    by_isin: dict[str, list[str]] = {}
    for key, sec in merged.items():
        if sec.isin:
            by_isin.setdefault(_norm(sec.isin), []).append(key)

    drop_keys: set[str] = set()
    for isin, syms in by_isin.items():
        if len(syms) <= 1:
            continue
        keeper, *others = syms        # iteration order = insertion order = priority order
        for other_key in others:
            other_sec = merged[other_key]
            # Fold other's symbol + its aliases onto the keeper.
            extras = extra_aliases.setdefault(keeper, set())
            extras.add(other_key)
            extras.update(other_sec.aliases)
            drop_keys.add(other_key)
            logger.debug(
                "ISIN dedup: folding %s into %s (shared ISIN %s)",
                other_key, keeper, isin,
            )
    for k in drop_keys:
        merged.pop(k, None)

    # Re-emit with merged aliases.
    out: list[Security] = []
    for key, sec in merged.items():
        all_aliases = set(sec.aliases) | extra_aliases.get(key, set())
        # Don't include the canonical symbol itself in its own aliases
        # — would be a no-op lookup but adds index noise.
        all_aliases.discard(_norm(sec.nse_symbol))
        if all_aliases != set(sec.aliases):
            sec = Security(
                nse_symbol     = sec.nse_symbol,
                isin           = sec.isin,
                name           = sec.name,
                series         = sec.series,
                bse_code       = sec.bse_code,
                yahoo_override = sec.yahoo_override,
                aliases        = tuple(sorted(all_aliases)),
            )
        out.append(sec)
    return out


def _persist_disk_cache(securities: list[Security]) -> None:
    """Write the merged registry to disk for next-boot fallback. Atomic
    via write-then-rename so a kill mid-write doesn't truncate."""
    try:
        _DISK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "version":   1,
            "fetched":   time.time(),
            "count":     len(securities),
            "securities": [
                {
                    "nse_symbol":     s.nse_symbol,
                    "isin":           s.isin,
                    "name":           s.name,
                    "series":         s.series,
                    "bse_code":       s.bse_code,
                    "yahoo_override": s.yahoo_override,
                    "aliases":        list(s.aliases),
                }
                for s in securities
            ],
        }
        tmp = _DISK_CACHE_FP.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=None), encoding="utf-8")
        tmp.replace(_DISK_CACHE_FP)
    except Exception as exc:
        logger.warning("Persisting registry disk cache failed: %s", exc)


# ── Registry (singleton) ────────────────────────────────────────────────────


class SecurityRegistry:
    """Process-global registry. Built lazily on first read; refreshed
    in the background by an external scheduler.

    Concurrency model:
      * Reads (resolve, get_by_*) are lock-free — they look at
        ``self._index``, which is only ever reassigned, never mutated.
      * Writes (refresh) hold ``self._refresh_lock`` so we don't run
        two refreshes at the same time, but readers don't see partial
        state because we build the new index off to the side and swap
        it in atomically with a single attribute assignment.
    """

    def __init__(self) -> None:
        # _index always references a complete _Index — never None,
        # never partially-built. Initial value is empty; the first
        # `_ensure_loaded()` call replaces it with the baseline.
        self._index: _Index = _empty_index()
        self._refresh_lock = asyncio.Lock()
        self._loaded_from_baseline = False

    # ── lifecycle ──────────────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        """Lazy initialiser called from every read path. Loads in this
        priority: disk cache → baseline. Network refresh is deferred to
        the explicit `refresh()` call (which is wired to a scheduler in
        main.py), so reads never block on I/O.

        Side-effect-free if already loaded."""
        if self._index.by_symbol:
            return
        # Disk cache first — last successful network fetch is fresher
        # than the bundled baseline.
        disk = _load_disk_cache()
        baseline = _load_baseline()
        if disk:
            self._index = _build_index(_merge_sources(disk, baseline), "disk+baseline")
            logger.info("Security registry bootstrapped from disk cache (%d entries).",
                        len(self._index.by_symbol))
        elif baseline:
            self._index = _build_index(baseline, "baseline")
            self._loaded_from_baseline = True
            logger.info("Security registry bootstrapped from baseline (%d entries).",
                        len(self._index.by_symbol))
        else:
            logger.error("Security registry bootstrap: NO sources available!")
            # Keep _empty_index() — callers will get None from resolve()
            # which preserves the current "pass-through" behaviour for
            # unknown symbols.

    async def refresh(self) -> None:
        """Pull NSE + Zerodha and rebuild the index. Safe to call
        concurrently — second caller just waits on the lock then
        returns (the cache is already fresh).

        Failure mode: if every network source fails, we don't touch
        the existing index — callers continue using whatever was loaded
        before. This is the "API failure resilience" the user flagged.
        """
        async with self._refresh_lock:
            self._ensure_loaded()  # ensure we have *something* loaded first

            # Fan out the two independent network calls in parallel.
            # The equity list and the symbol-change history live on
            # different NSE subdomains so failures aren't correlated.
            nse_rows, symbol_changes = await asyncio.gather(
                _fetch_nse_equity_list(),
                _fetch_nse_symbol_changes(),
            )
            zerodha_rows: list[Security] = []
            if not nse_rows:
                # Only try Zerodha when NSE was empty — successful NSE
                # is authoritative and Zerodha is just a backup.
                zerodha_rows = await _fetch_zerodha_dump()

            # Even when both equity sources fail, if we got the rename
            # history we can still apply it to the *existing* index.
            # That's enough to fix saved scanners breaking on renames
            # like LTFH -> LTF when the universe-list endpoint hasn't
            # been refreshed yet.
            if not nse_rows and not zerodha_rows:
                if symbol_changes:
                    existing = list(self._index.by_symbol.values())
                    updated  = _apply_symbol_changes(existing, symbol_changes)
                    new_idx  = _build_index(
                        updated,
                        source_tag = f"{self._index.source_tag}+renames",
                    )
                    _persist_disk_cache(updated)
                    old_count = len(self._index.by_symbol)
                    self._index = new_idx
                    logger.info(
                        "Security registry: equity sources failed but applied "
                        "%d renames to existing %d-entry index.",
                        len(symbol_changes), old_count,
                    )
                else:
                    logger.warning(
                        "Security registry refresh: NSE + Zerodha + rename "
                        "history all failed; keeping existing index from %s "
                        "with %d entries.",
                        self._index.source_tag, len(self._index.by_symbol),
                    )
                return

            # Merge in priority order: live source > baseline (for
            # alias coverage). We always include baseline so manual
            # aliases (BATA, INFOEDGE, …) survive a network refresh.
            baseline = _load_baseline()
            live     = nse_rows or zerodha_rows
            merged   = _merge_sources(live, baseline)
            # Apply NSE's published symbol-rename history. This is what
            # turns LTFH into an alias of LTF, GMRINFRA into an alias
            # of GMRAIRPORT, etc. — automatically, for every historical
            # rename, without any manual baseline maintenance.
            merged   = _apply_symbol_changes(merged, symbol_changes)
            new_idx  = _build_index(
                merged,
                source_tag = "nse+baseline" if nse_rows else "zerodha+baseline",
            )

            # Persist BEFORE swap so a successful in-memory swap means
            # the disk version is at least as new.
            _persist_disk_cache(merged)

            # Atomic swap — readers immediately see the new index.
            old_count = len(self._index.by_symbol)
            self._index = new_idx
            logger.info(
                "Security registry refreshed: %d entries (was %d) from %s, "
                "%d renames applied.",
                len(new_idx.by_symbol), old_count, new_idx.source_tag,
                len(symbol_changes),
            )

    # ── reads ──────────────────────────────────────────────────────────────

    def resolve(self, user_input: str) -> Optional[Security]:
        """Return the Security matching `user_input`, or None.
        Implements the cascade documented at module top."""
        if not user_input:
            return None
        self._ensure_loaded()
        idx = self._index   # snapshot — survives a mid-call refresh swap
        key = _norm(user_input)

        # 1. exact NSE symbol
        sec = idx.by_symbol.get(key)
        if sec:
            return sec

        # 2. ISIN (12 chars, starts with 2 letters, e.g. INE...)
        if len(key) == 12 and key[:2].isalpha() and key[2:].isalnum():
            sec = idx.by_isin.get(key)
            if sec:
                return sec

        # 3. aliases
        sec = idx.by_alias.get(key)
        if sec:
            return sec

        # 4. exact normalized name
        norm = _normalize_name(user_input)
        if norm:
            sec = idx.by_norm_name.get(norm)
            if sec:
                return sec

            # 5. fuzzy on name (difflib). Cutoff is 0.85 — empirically,
            # 0.80 starts producing false positives ("INFY" -> "INFRA"),
            # 0.90 misses obvious typos. Limit to 1 result.
            matches = get_close_matches(norm, idx.all_names, n=1, cutoff=0.85)
            if matches:
                return idx.by_norm_name.get(matches[0])

        return None

    def get_by_nse_symbol(self, sym: str) -> Optional[Security]:
        """Pure NSE-symbol lookup, no cascade. Used by callers that
        already know they have a canonical ticker."""
        if not sym:
            return None
        self._ensure_loaded()
        return self._index.by_symbol.get(_norm(sym))

    def all_securities(self) -> list[Security]:
        """Snapshot copy of every Security currently indexed. Used by
        health endpoints and the universe-population script."""
        self._ensure_loaded()
        return list(self._index.by_symbol.values())

    def stats(self) -> dict:
        """Health snapshot — exposed via the diagnostics endpoint."""
        self._ensure_loaded()
        idx = self._index
        return {
            "count":      len(idx.by_symbol),
            "isins":      len(idx.by_isin),
            "aliases":    len(idx.by_alias),
            "source":     idx.source_tag,
            "loaded_at":  idx.loaded_at,
            "from_baseline_only": self._loaded_from_baseline,
        }


# ── Singleton accessor ──────────────────────────────────────────────────────

_REGISTRY: Optional[SecurityRegistry] = None


def get_registry() -> SecurityRegistry:
    """Return the process-global SecurityRegistry singleton. Lazy
    construction — the first caller pays the bootstrap cost (one local
    file read), every subsequent caller is just an attribute lookup."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = SecurityRegistry()
    return _REGISTRY


# Convenience top-level functions — most callers want one of these
# rather than the registry object itself.

def resolve(user_input: str) -> Optional[Security]:
    """Resolve any inbound symbol form to a Security. None on miss."""
    return get_registry().resolve(user_input)


def canonical_nse_symbol(user_input: str) -> str:
    """Return the canonical NSE symbol for an inbound user_input.
    Falls back to the upper-cased input when the registry has no
    matching entry — preserves the existing "pass-through" behaviour
    so unknown tickers (brand new IPOs, etc.) still flow through the
    chain instead of being dropped."""
    sec = resolve(user_input)
    if sec:
        return sec.nse_symbol
    return _norm(user_input) or user_input


async def refresh_registry() -> None:
    """Trigger a background network refresh. Called by the scheduler in
    main.py once per day, and once at startup as a fire-and-forget task."""
    await get_registry().refresh()
