"""
Shareholding pattern service.

What it does
------------
Returns the quarterly shareholding-pattern history for any NSE-listed
Indian equity — the data shown as a per-quarter % breakdown of Promoter
/ FII / DII / Public ownership on stock-detail pages like Tickertape,
Trendlyne, Screener.

Data shape per row:
    {
        "asOnDate":        "2024-03-31",       # ISO date, quarter-end
        "promoterPct":     74.05,              # may be null when source unknown
        "fiiPct":          8.96,
        "diiPct":          1.27,
        "publicPct":       15.71,
        "numShareholders": 32500,              # may be null
        "source":          "BSE",              # which provider supplied this row
    }

Source chain — XBRL-first, multi-source resilient
-------------------------------------------------
SEBI mandates every listed company file a quarterly shareholding
pattern as an XBRL document (structured XML following the SEBI
taxonomy). These filings are the canonical source for everything —
Screener, Tickertape, and every other Indian-market data UI
ultimately reads from them. We do the same, directly:

  1. NSE corp-info     — `/api/corporate-share-holdings-master` gives
                          us 80 quarters of Promoter/Public totals
                          AND the XBRL URL per quarter (free index).
  2. XBRL filings      — fetch + parse the SEBI XBRL XML per quarter
                          for the full FII/DII/Public breakdown.
                          Same data Screener consumes, no middleman.
  3. Yahoo `info`      — last-resort current-quarter snapshot when
                          steps 1-2 both return nothing.
  4. Screener scrape   — defensive fallback when XBRL coverage is
                          thin (malformed XBRLs, older filings using
                          deprecated taxonomy versions, etc.).

Each fetch upserts rows into PG. So NSE writes Promoter/Public per
quarter, then XBRL enrichment fills in FII/DII for the most recent
16 quarters. Reads always come from PG and reflect the union of every
source that's ever successfully filled in for this symbol.

The previous BSE HTML scrape (Sharehold_Searchnew.aspx) was removed
when we switched to XBRL — they read from the same underlying filings,
so the HTML route was a redundant fragile parser.

Cache policy
------------
SEBI LODR filings are immutable once published — last quarter's row will
never change. So we cache forever for historical quarters, and only
re-fetch the current quarter (the row whose as_on_date is within the
last ~95 days). The reader applies a 24h staleness check on the current
quarter to keep refreshes cheap.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import date, datetime, timedelta
from typing import Optional

import httpx

from ..lib.auth_store import ensure_primary_schema, get_conn, now_ms
from ..lib.symbol_map import canonical_symbol
from .nse_service import NseService

logger = logging.getLogger("shareholding")


# ── Constants ───────────────────────────────────────────────────────────────

# Refresh staleness window for the *current* quarter only. Historical
# quarters are immutable so they're cached forever.
_CURRENT_QUARTER_REFRESH_S = 24 * 3600          # 24 h

# How recent an as_on_date must be to count as "the current quarter" for
# refresh purposes. SEBI gives companies 21 days from quarter-end to
# file, plus a bit of room for late publishers. 100 days is comfortably
# wider than any real filing cadence.
_CURRENT_QUARTER_WINDOW_DAYS = 100

# How many quarters back the API should attempt to fetch on a cold cache
# (no historical rows in PG yet). NSE corp-info exposes 80+ quarters
# but we cap reads at this so the response payload stays bounded and
# the UI doesn't choke on a 50-column table. 32 = 8 years of history,
# which covers most analytical use-cases (long-term promoter trend,
# multi-cycle FII/DII flows).
_DEFAULT_HISTORY_QUARTERS = 32

# Testing kill-switch. Set `SHAREHOLDING_DISABLE_CACHE=1` in the
# backend container's env to force every request to re-run the
# multi-source chain, regardless of PG cache freshness. Useful while
# debugging which source is failing — you don't have to remember to
# pass `?force=1` on every URL. Remove the env var to restore normal
# caching behaviour.
import os as _os                                             # noqa: PLC0415, E402
_CACHE_DISABLED = (_os.environ.get("SHAREHOLDING_DISABLE_CACHE") or "").strip() == "1"
if _CACHE_DISABLED:
    # Loud notice so this can't ship to production by accident — the
    # log line shows up at module import time, exactly once.
    logging.getLogger("shareholding").warning(
        "SHAREHOLDING_DISABLE_CACHE=1 — every request bypasses the PG "
        "staleness check and re-runs all sources. Unset for production."
    )


# ── Common HTTP headers (BSE / Screener don't need cookies; NSE flows
# through the cookie-managed NseService.fetch_nse). ─────────────────
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/html;q=0.9, */*;q=0.5",
    "Accept-Language": "en-US,en;q=0.9",
}


# ── Row dataclass ───────────────────────────────────────────────────────────


def _row(
    *,
    as_on_date:       date,
    promoter_pct:     Optional[float] = None,
    fii_pct:          Optional[float] = None,
    dii_pct:          Optional[float] = None,
    public_pct:       Optional[float] = None,
    num_shareholders: Optional[int]   = None,
    source:           str = "",
) -> dict:
    """Build one normalized shareholding row. Centralised so every
    source produces the same dict shape — easier upserts, easier UI.

    The `as_on_date` is snapped to the nearest standard quarter-end
    here, so any interim/corrigendum filing dates (e.g. OCT 2024 for a
    TCS re-filing) collapse into the matching quarter row instead of
    appearing as a phantom extra column."""
    return {
        "as_on_date":       _snap_to_quarter_end(as_on_date),
        "promoter_pct":     _round(promoter_pct),
        "fii_pct":          _round(fii_pct),
        "dii_pct":          _round(dii_pct),
        "public_pct":       _round(public_pct),
        "num_shareholders": int(num_shareholders) if num_shareholders else None,
        "source":           source,
    }


def _round(x: Optional[float]) -> Optional[float]:
    """Round to 2 dp, swallowing TypeErrors from None / non-numeric.
    Centralised so every per-source parser doesn't repeat this."""
    if x is None:
        return None
    try:
        return round(float(x), 2)
    except (TypeError, ValueError):
        return None


def _parse_date(s: str) -> Optional[date]:
    """Parse the wide variety of date formats these endpoints emit:
    '31-MAR-2024', '31/03/2024', '2024-03-31', 'March 31, 2024'."""
    if not s:
        return None
    s = s.strip()
    fmts = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d/%m/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ── Source 1: NSE direct ────────────────────────────────────────────────────


_nse = NseService()


async def _fetch_nse(symbol: str) -> list[dict]:
    """NSE's corporate-share-holdings-master endpoint.

    History note: an earlier version of this code used the singular
    `corporate-shareholdings-master` path which 404s. The correct path
    is `corporate-share-holdings-master` (3 hyphens, 2 separated
    words). Cost of that one-character bug: every NSE fetch returned
    empty, the chain fell straight to Yahoo (current quarter only), and
    the UI showed 1 column instead of 80.

    Verified shape (as of 2026 — RELIANCE returns ~80 quarters):
      GET /api/corporate-share-holdings-master
          ?index=equities&symbol=RELIANCE
      -> [                                  # NOTE: flat array, not {"data": [...]}
           {
             "symbol":       "RELIANCE",
             "name":         "Reliance Industries Limited",
             "isin":         "INE002A01018",
             "date":         "31-DEC-2025",
             "pr_and_prgrp": "50.01",       # Promoter + promoter group %
             "public_val":   "49.99",       # Public %
             "underlyingDrs":   "0.00",
             "employeeTrusts":  "0.00",
             "xbrl":         "https://nsearchives.nseindia.com/corporate/xbrl/SHP_*.xml",
             ...
           },
           ...
         ]

    The XBRL link per record is the door to the full FII/DII/MF
    breakdown — SEBI publishes the categorised filing as XBRL. Parsing
    that is a separate follow-up; for now we extract the Promoter/Public
    headlines, which alone is enough to surface 20+ quarters of history
    on the UI.
    """
    from urllib.parse import quote
    encoded = quote(symbol, safe="")
    raw = await _nse.fetch_nse(
        f"/api/corporate-share-holdings-master?index=equities&symbol={encoded}",
        f"shareholding-nse-{symbol}",
        ttl=12 * 3600,    # 12h — current quarter at this provider gets a re-fetch on staleness
        referer=f"https://www.nseindia.com/get-quotes/equity?symbol={encoded}",
    )
    rows: list[dict] = []
    # NSE returns a top-level flat array. If it's wrapped in {"data": [...]}
    # we handle that too (defensive — endpoint shape has shifted before).
    if isinstance(raw, list):
        payload = raw
    elif isinstance(raw, dict):
        payload = raw.get("data") or raw.get("Data") or []
    else:
        return rows
    if not isinstance(payload, list):
        return rows
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        # Date field is `date` (e.g. "31-DEC-2025"). Older code paths
        # used asOnDate variants — kept as defensive fallbacks in case
        # NSE flips the schema back.
        d = _parse_date(str(
            entry.get("date")
            or entry.get("asOnDate")
            or entry.get("as_on_date")
            or entry.get("AsOnDate")
            or ""
        ))
        if not d:
            continue
        promoter = (
            entry.get("pr_and_prgrp")
            or entry.get("promoterAndPromoterGroup")
            or entry.get("promoter")
            or entry.get("Promoter")
        )
        public = (
            entry.get("public_val")
            or entry.get("public")
            or entry.get("nonPromoter")
            or entry.get("Public")
        )
        row = _row(
            as_on_date    = d,
            promoter_pct  = promoter,
            public_pct    = public,
            # NSE summary doesn't carry FII/DII or shareholder count.
            # The XBRL link below is the door to that data — the
            # XBRL enricher in _refresh() will fetch and parse it.
            source        = "NSE",
        )
        # Stash the XBRL filing URL on the row as an internal field
        # (prefixed with `_` so _upsert_rows ignores it). _refresh()
        # picks these up and fans them out to the XBRL enricher.
        xbrl_url = entry.get("xbrl") or entry.get("xbrlUrl") or ""
        if xbrl_url:
            row["_xbrl_url"] = xbrl_url
        rows.append(row)
    return rows


# ── Source 2: SEBI XBRL filings (the same files Screener ingests) ───────────
#
# History note: this used to be a BSE HTML scraper hitting
# Sharehold_Searchnew.aspx. That was redundant with the XBRL parser
# below — both ultimately source from the same BSE-published XBRL
# filings. The HTML route added a fragile parser (ASP.NET GridView ids
# drift) for one quarter of data; the XBRL route gives us 16+ quarters
# of structured XML directly. BSE HTML code lived in commits prior to
# the XBRL switchover.


# SEBI XBRL Taxonomy mapping. Each company quarterly files an XBRL
# document tagging percentage values with a `contextRef` that points
# to a category definition. We aggregate leaf categories into 4 UI
# buckets, deliberately ignoring parent categories ("Public" parent
# total) so we don't double-count when both parent + children are
# present in the same filing.
#
# Matching is lowercased substring — robust against minor schema
# version drift across SEBI taxonomy versions (2013, 2016, 2018, 2021).
_XBRL_CATEGORY_PATTERNS = {
    "promoter": [
        "promoter",          # excludes "nonpromoter" via explicit check below
    ],
    "fii": [
        "foreignportfolio", "foreignportfolioinvestor",
        "fpicategory", "fpicat",
        "foreigninstitutional", "foreigncompan",
        "qfi",                # Qualified Foreign Investor (older filings)
    ],
    "dii": [
        "mutualfund",
        "insurance",
        "bank",               # banks / financial institutions
        "financialinstitution",
        "alternateinvestment", "alternativeinvestment",
        "nbfc", "nonbankingfinancial",
        "venturecapital",
        "providentfund", "pensionfund",
    ],
    "public": [
        "individual",
        "bodycorporate", "bodiescorporate",
        "trust",
        "nri",
        "clearing",
        "others", "anyother",
        # NOTE: we deliberately do NOT include bare "Public" here —
        # that's the parent category. Aggregating leaf sub-categories
        # gives us the correct breakdown without double-counting.
    ],
}


def _xbrl_category_to_bucket(category: str) -> Optional[str]:
    """Map an XBRL context-member name to one of our 4 buckets.

    Returns None for parent categories ("Public") and unknowns —
    callers skip those values, which is what we want (we only count
    leaf-level percentages so the totals across buckets add to ~100
    without double-counting parent + child contexts in the same file).
    """
    if not category:
        return None
    norm = category.lower()
    # Defensive: exclude "NonPromoterNonPublic" and similar
    # weirdness before considering the promoter bucket.
    if "nonpromoter" in norm or "non-promoter" in norm:
        # NonPromoterNonPublic = locked-in shares (employee trusts, ESOPs);
        # fold into public per SEBI convention.
        return "public"
    if any(p in norm for p in _XBRL_CATEGORY_PATTERNS["promoter"]):
        return "promoter"
    if any(p in norm for p in _XBRL_CATEGORY_PATTERNS["fii"]):
        return "fii"
    if any(p in norm for p in _XBRL_CATEGORY_PATTERNS["dii"]):
        return "dii"
    if any(p in norm for p in _XBRL_CATEGORY_PATTERNS["public"]):
        return "public"
    return None


# XBRL files are immutable per quarter — once a filing is published,
# the bytes never change. So we disk-cache aggressively. Cache lives
# alongside the other runtime caches at python-backend/data/xbrl_cache/.
import hashlib                                            # noqa: PLC0415
from pathlib import Path                                  # noqa: PLC0415

_XBRL_CACHE_DIR = (
    Path(__file__).resolve().parent.parent.parent / "data" / "xbrl_cache"
)


def _xbrl_cache_path(url: str) -> Path:
    """Map an XBRL URL to a deterministic cache file path. Hashing
    the URL avoids any filename character issues (the URLs contain
    timestamps, slashes, etc.) and gives O(1) lookup."""
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return _XBRL_CACHE_DIR / f"{h}.xml"


async def _fetch_xbrl_file(url: str) -> Optional[bytes]:
    """Download an XBRL XML file, with disk-cached read-through.

    Cache policy: XBRL filings are immutable (SEBI mandates no
    revisions — corrections are filed as fresh quarters), so we cache
    forever on disk. First fetch pays the HTTP round-trip; every
    subsequent fetch reads from disk in microseconds.
    """
    cache_path = _xbrl_cache_path(url)
    if cache_path.exists():
        try:
            return cache_path.read_bytes()
        except Exception as exc:
            logger.debug("XBRL cache read failed for %s: %s", url, exc)

    try:
        async with httpx.AsyncClient(timeout=15.0, headers=_BROWSER_HEADERS,
                                     follow_redirects=True) as client:
            r = await client.get(url)
            if r.status_code != 200:
                logger.debug("XBRL fetch %s -> %d", url, r.status_code)
                return None
            content = r.content
    except Exception as exc:
        logger.debug("XBRL fetch failed for %s: %s", url, str(exc)[:120])
        return None

    # Persist for future fetches. Write failures are non-fatal —
    # we always serve the in-memory bytes regardless.
    try:
        _XBRL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(content)
    except Exception as exc:
        logger.debug("XBRL cache write failed for %s: %s", url, exc)

    return content


def _parse_xbrl(xml_bytes: bytes) -> Optional[dict]:
    """Parse a SEBI XBRL shareholding pattern filing.

    Strategy:
      1. Walk the XML and find every <xbrli:context> element. Each
         carries an `id` and contains an `<xbrldi:explicitMember>`
         pointing to the SEBI taxonomy member name (the category).
         Build `context_id -> category` map.
      2. Walk again and find every `*PercentageOfShareholding*`
         element. Look up its `contextRef` -> category -> bucket.
         Sum percentages into the 4 UI buckets.
      3. Optionally pull `*NumberOfShareholders*` text content.

    Defensive against XBRL version drift: we match by `localname`
    (ignoring namespace) and use lowercase substring matching for
    category names. SEBI taxonomy is stable enough that the bucket
    mapping doesn't need per-version overrides.

    Returns None on any parse failure or if no recognised category
    yielded a value — caller treats as "skip, try next source".
    """
    try:
        from lxml import etree                              # noqa: PLC0415
    except Exception as exc:
        logger.warning("XBRL parse: lxml unavailable: %s", exc)
        return None

    try:
        root = etree.fromstring(xml_bytes)
    except Exception as exc:
        logger.debug("XBRL parse: lxml failed: %s", str(exc)[:120])
        return None

    # Step 1: context_id -> category member name
    context_to_category: dict[str, str] = {}
    for ctx in root.iter():
        if etree.QName(ctx).localname != "context":
            continue
        ctx_id = ctx.get("id", "").strip()
        if not ctx_id:
            continue
        # Find an explicitMember inside this context (anywhere — it
        # may be wrapped in scenario, segment, etc.).
        for descendant in ctx.iter():
            if etree.QName(descendant).localname == "explicitMember":
                member = (descendant.text or "").strip()
                # Member names are namespaced like "in-capmkt:PromoterMember";
                # strip the namespace prefix for cleaner pattern matching.
                if ":" in member:
                    member = member.split(":", 1)[1]
                # Strip trailing "Member" suffix common in SEBI taxonomy
                if member.endswith("Member"):
                    member = member[:-6]
                context_to_category[ctx_id] = member
                break

    # Step 2: aggregate percentages by bucket
    buckets = {"promoter": 0.0, "fii": 0.0, "dii": 0.0, "public": 0.0}
    found_any = False

    for el in root.iter():
        localname = etree.QName(el).localname
        # Match any element whose name looks like a percentage-of-
        # shareholding value. SEBI has used several variant names
        # across taxonomy versions.
        if not localname:
            continue
        ln_lower = localname.lower()
        is_pct_elem = (
            "percentageofshareholding" in ln_lower
            or "shareholdingaspercentage" in ln_lower
            or "percentageholding" in ln_lower
        )
        if not is_pct_elem:
            continue
        ctx_ref = el.get("contextRef", "")
        category = context_to_category.get(ctx_ref, "")
        bucket = _xbrl_category_to_bucket(category)
        if not bucket:
            continue
        try:
            pct = float((el.text or "0").strip())
        except (ValueError, TypeError):
            continue
        # Skip obviously bogus values.
        if pct < 0 or pct > 100:
            continue
        buckets[bucket] += pct
        found_any = True

    if not found_any:
        return None

    # Step 3: total shareholder count (optional)
    num_shareholders: Optional[int] = None
    for el in root.iter():
        ln = etree.QName(el).localname or ""
        if not ln:
            continue
        ll = ln.lower()
        if ("numberofshareholders" in ll
                or "totalnoofshareholders" in ll
                or "totalnumberofshareholders" in ll):
            # Skip context-scoped per-category counts; we want the
            # top-level total. Heuristic: pick the LARGEST value
            # encountered, which is always the all-shareholders total.
            try:
                v = int(float((el.text or "0").strip()))
                if num_shareholders is None or v > num_shareholders:
                    num_shareholders = v
            except (ValueError, TypeError):
                continue

    # Sanity check — if buckets total well above 100, something is
    # double-counted (probably parent + child contexts both included
    # despite our exclusion logic). Better to return None and let a
    # fallback source handle it than to surface obviously-wrong data.
    total = sum(buckets.values())
    if total > 105:
        logger.debug("XBRL parse: bucket total %.2f > 105, dropping", total)
        return None

    return {
        "promoter_pct": _round(buckets["promoter"]) if buckets["promoter"] else None,
        "fii_pct":      _round(buckets["fii"])      if buckets["fii"]      else None,
        "dii_pct":      _round(buckets["dii"])      if buckets["dii"]      else None,
        "public_pct":   _round(buckets["public"])   if buckets["public"]   else None,
        "num_shareholders": num_shareholders,
    }


async def _enrich_with_xbrl(symbol: str, xbrl_url: str, as_on: date) -> Optional[dict]:
    """Fetch + parse one XBRL filing, return an upsertable row dict.
    Returns None on any failure (no row written, COALESCE upsert
    means existing NSE-only Promoter/Public stays in place)."""
    if not xbrl_url:
        return None
    xml = await _fetch_xbrl_file(xbrl_url)
    if not xml:
        return None
    parsed = _parse_xbrl(xml)
    if not parsed:
        return None
    return _row(
        as_on_date       = as_on,
        promoter_pct     = parsed.get("promoter_pct"),
        fii_pct          = parsed.get("fii_pct"),
        dii_pct          = parsed.get("dii_pct"),
        public_pct       = parsed.get("public_pct"),
        num_shareholders = parsed.get("num_shareholders"),
        source           = "XBRL",
    )


# ── Source 3: Yahoo info snapshot (current quarter only) ────────────────────


async def _fetch_yahoo(symbol: str) -> list[dict]:
    """Yahoo's `info` dict carries `heldPercentInsiders` (≈ promoter
    for Indian stocks) and `heldPercentInstitutions` (sum of FII+DII).
    No history, no FII/DII split. Useful only when both exchanges fail —
    we get a single current-quarter row with `public_pct` derived as
    100 - insiders - institutions.

    Wrapping yfinance behind a thread to keep us off the event loop."""
    try:
        import yfinance as yf  # noqa: PLC0415
    except Exception:
        return []

    from ..lib.symbol_map import to_yahoo_ticker  # noqa: PLC0415
    ticker = to_yahoo_ticker(symbol)

    def _grab() -> dict:
        try:
            return yf.Ticker(ticker).info or {}
        except Exception as exc:
            logger.debug("Yahoo info failed for %s: %s", ticker, str(exc)[:120])
            return {}

    info = await asyncio.to_thread(_grab)
    if not info:
        return []

    promoter_frac = info.get("heldPercentInsiders")
    institut_frac = info.get("heldPercentInstitutions")
    if promoter_frac is None and institut_frac is None:
        return []

    promoter_pct = promoter_frac * 100 if isinstance(promoter_frac, (int, float)) else None
    institut_pct = institut_frac * 100 if isinstance(institut_frac, (int, float)) else None
    public_pct = None
    if promoter_pct is not None and institut_pct is not None:
        public_pct = max(0.0, 100.0 - promoter_pct - institut_pct)

    # Snap to today's quarter-end so this row slots into the same
    # PG cell as any NSE/BSE row for the same quarter (PK collision
    # = upsert, with the more-detailed source winning per merge).
    qe = _last_quarter_end(date.today())
    return [_row(
        as_on_date   = qe,
        promoter_pct = promoter_pct,
        # Yahoo's institutional figure conflates FII+DII; we can't
        # split them so we leave fii_pct/dii_pct NULL and just record
        # the total via the institutions field below in public_pct's
        # complement. Don't pretend we have a breakdown.
        public_pct   = public_pct,
        source       = "YAHOO",
    )]


# ── Source 4: Screener.in HTML scrape ───────────────────────────────────────


async def _fetch_screener(symbol: str) -> list[dict]:
    """Last-resort scrape. Screener.in hosts the canonical-UI version of
    this exact table at /company/<SYMBOL>/.

    Important: Screener's ToS discourages scraping. We treat this as a
    break-glass option that only fires when every official source is
    down. It hits one URL with no auth and parses one HTML chunk.

    Format: Screener renders the shareholding table as an HTML <table>
    with one row per category (Promoters, FIIs, DIIs, Public, No. of
    Shareholders) and one column per quarter. We parse the column
    headers as quarter labels and the rows as category → list-of-pcts.
    """
    url = f"https://www.screener.in/company/{symbol}/"
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=_BROWSER_HEADERS,
                                     follow_redirects=True) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return []
            html = r.text
    except Exception as exc:
        logger.debug("Screener fetch failed for %s: %s", symbol, str(exc)[:120])
        return []
    return _parse_screener_html(html)


def _parse_screener_html(html: str) -> list[dict]:
    """Pull the shareholding pattern table from a Screener company page.

    Lxml-based parser — more robust than regex against Screener's
    occasional HTML tweaks. Strategy:
      1. Find the section element with id="shareholding"
      2. Inside, find the quarterly <table> (the page also has a
         yearly table — we explicitly want the quarterly one).
      3. <thead><th> values are quarter labels (e.g. "Jun 2023").
      4. <tbody><tr>: first cell is the category label, remaining
         cells are per-quarter percentages.
      5. Aggregate Government holding into Public so buckets sum to
         ~100.
    """
    try:
        from lxml import html as _html  # noqa: PLC0415
    except Exception as exc:
        logger.warning("Screener parse: lxml not available: %s", exc)
        return []

    try:
        doc = _html.fromstring(html)
    except Exception as exc:
        logger.debug("Screener parse: lxml failed: %s", exc)
        return []

    # Section anchor — Screener wraps the table in
    # <section id="shareholding">. The page also has a yearly table
    # rendered inside a sibling <div data-target="...quarterly...">.
    sections = doc.xpath('//section[@id="shareholding"]')
    if not sections:
        return []
    section = sections[0]

    # Quarterly tab — fall back to the first <table> inside the
    # section if the data-target marker has changed.
    tables = section.xpath('.//div[contains(@class, "shareholding")]//table'
                          ' | .//div[@data-active]//table'
                          ' | .//table')
    if not tables:
        return []
    table = tables[0]

    # Quarter labels — <thead> <th>.
    th_texts = [th.text_content().strip()
                for th in table.xpath('.//thead//th')]
    # First column is the category label; the rest are quarters.
    quarter_labels = th_texts[1:] if th_texts else []
    quarter_dates: list[Optional[date]] = []
    for label in quarter_labels:
        try:
            d = datetime.strptime(label.strip(), "%b %Y").date()
            qe = _last_quarter_end(d.replace(day=28))
            quarter_dates.append(qe)
        except ValueError:
            quarter_dates.append(None)
    if not any(quarter_dates):
        return []

    # Body rows.
    label_map = {
        "promoters":          "promoter_pct",
        "fiis":               "fii_pct",
        "fii":                "fii_pct",
        "diis":               "dii_pct",
        "dii":                "dii_pct",
        "public":             "public_pct",
        "no of shareholders": "num_shareholders",
        "no. of shareholders":"num_shareholders",
    }

    out: dict[date, dict] = {}

    def _bucket(qd: date) -> dict:
        if qd not in out:
            out[qd] = _row(as_on_date=qd, source="SCREENER")
        return out[qd]

    for tr in table.xpath(".//tbody/tr"):
        cells = tr.xpath("./td")
        if len(cells) < 2:
            continue
        label_raw = cells[0].text_content().strip().rstrip("+").strip().lower()
        col = label_map.get(label_raw)
        is_government = label_raw == "government"
        if col is None and not is_government:
            continue
        for i, cell in enumerate(cells[1:]):
            if i >= len(quarter_dates):
                break
            qd = quarter_dates[i]
            if not qd:
                continue
            txt = cell.text_content().strip().replace("%", "").replace(",", "")
            try:
                val = float(txt)
            except ValueError:
                continue
            b = _bucket(qd)
            if col == "num_shareholders":
                b["num_shareholders"] = int(val)
            elif col:
                b[col] = _round(val)
            elif is_government:
                # Fold Government holding into Public so the 4 buckets
                # sum to ~100.
                existing = b["public_pct"] or 0
                b["public_pct"] = _round(existing + val)

    return list(out.values())


# ── Quarter math ────────────────────────────────────────────────────────────


def _last_quarter_end(d: date) -> date:
    """Snap a date to the most recent quarter-end (31-Mar, 30-Jun,
    30-Sep, 31-Dec). Used by Yahoo/Screener fallback paths that don't
    carry an explicit date — they default to today's last quarter-end."""
    m = d.month
    if   m >= 12: return date(d.year, 12, 31)
    elif m >=  9: return date(d.year,  9, 30)
    elif m >=  6: return date(d.year,  6, 30)
    elif m >=  3: return date(d.year,  3, 31)
    return date(d.year - 1, 12, 31)


def _snap_to_quarter_end(d: date) -> date:
    """Snap any filing date to the NEAREST standard quarter-end.

    Why this exists: SEBI requires shareholding filings for the four
    standard quarter-ends (31-Mar, 30-Jun, 30-Sep, 31-Dec). But the
    NSE / XBRL / Screener pipelines occasionally surface non-standard
    dates — interim corrigendum filings, re-filings with the actual
    document date instead of the period-end, off-by-a-day dates from
    different timezones. Without snapping, those become phantom
    columns in the UI ("OCT 2024" alongside SEP 2024 and DEC 2024),
    looking like the system is broken.

    Algorithm: build candidate quarter-ends for the same year and the
    previous-year December, pick the one closest in absolute days.
    A filing dated 2024-10-15 collapses into 2024-09-30 (15 days away)
    rather than 2024-12-31 (77 days away).

    Idempotent — already-snapped dates pass through unchanged."""
    candidates = [
        date(d.year, 3, 31),
        date(d.year, 6, 30),
        date(d.year, 9, 30),
        date(d.year, 12, 31),
        date(d.year - 1, 12, 31),
        date(d.year + 1, 3, 31),
    ]
    return min(candidates, key=lambda c: abs((c - d).days))


# ── PG layer ────────────────────────────────────────────────────────────────


def _upsert_rows(symbol: str, rows: list[dict]) -> int:
    """Upsert one batch of rows into shareholding_history. Returns
    number of rows actually written.

    Conflict resolution: when (symbol, as_on_date) collides we COALESCE
    incoming values onto existing — so a later BSE fetch that has FII/DII
    fills NULLs left by an earlier NSE-only fetch, but doesn't overwrite
    a real value with NULL. The `source` column always reflects the
    most-recent writer for traceability."""
    if not rows:
        return 0
    ensure_primary_schema()
    written = 0
    ts = now_ms()
    with get_conn() as conn:
        with conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO shareholding_history
                        (symbol, as_on_date, promoter_pct, fii_pct, dii_pct,
                         public_pct, num_shareholders, source, fetched_at_ms)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, as_on_date) DO UPDATE SET
                        promoter_pct     = COALESCE(EXCLUDED.promoter_pct,     shareholding_history.promoter_pct),
                        fii_pct          = COALESCE(EXCLUDED.fii_pct,          shareholding_history.fii_pct),
                        dii_pct          = COALESCE(EXCLUDED.dii_pct,          shareholding_history.dii_pct),
                        public_pct       = COALESCE(EXCLUDED.public_pct,       shareholding_history.public_pct),
                        num_shareholders = COALESCE(EXCLUDED.num_shareholders, shareholding_history.num_shareholders),
                        source           = EXCLUDED.source,
                        fetched_at_ms    = EXCLUDED.fetched_at_ms
                    """,
                    (
                        symbol,
                        r["as_on_date"],
                        r["promoter_pct"],
                        r["fii_pct"],
                        r["dii_pct"],
                        r["public_pct"],
                        r["num_shareholders"],
                        r["source"],
                        ts,
                    ),
                )
                written += 1
        conn.commit()
    return written


def _read_history(symbol: str) -> list[dict]:
    """Return every cached row for `symbol`, newest-quarter first."""
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT as_on_date, promoter_pct, fii_pct, dii_pct,
                       public_pct, num_shareholders, source, fetched_at_ms
                  FROM shareholding_history
                 WHERE symbol = %s
              ORDER BY as_on_date DESC
                """,
                (symbol,),
            )
            rows = cur.fetchall() or []
    return [dict(r) for r in rows]


def _needs_refresh(rows: list[dict]) -> bool:
    """Decide whether to hit the network. True when:
      * SHAREHOLDING_DISABLE_CACHE env var is set (testing kill-switch)
      * we have no rows at all
      * the latest row is older than the current quarter window
      * the latest row IS within the current quarter window but its
        cached snapshot is older than 24h
    """
    if _CACHE_DISABLED:
        return True
    if not rows:
        return True
    latest = rows[0]
    latest_date = latest["as_on_date"]
    if isinstance(latest_date, datetime):
        latest_date = latest_date.date()
    today = date.today()
    if (today - latest_date).days > _CURRENT_QUARTER_WINDOW_DAYS:
        return True
    fetched_at_ms = latest.get("fetched_at_ms") or 0
    age_s = (now_ms() - fetched_at_ms) / 1000.0
    return age_s > _CURRENT_QUARTER_REFRESH_S


# ── Public API ──────────────────────────────────────────────────────────────


async def get_shareholding(
    symbol:    str,
    *,
    view:      str = "quarterly",
    quarters:  int = _DEFAULT_HISTORY_QUARTERS,
    force:     bool = False,
) -> dict:
    """Return shareholding pattern for `symbol`. Reads from PG cache;
    triggers a multi-source refresh when cache is empty or stale.

    Args:
      view      "quarterly" (every row) or "yearly" (only March
                quarter-ends — Indian FY year-end snapshots).
      quarters  Cap on number of historical rows returned. The screenshot
                shows 12 columns; we default to 16 (4 years) so users can
                scroll a bit.
      force     Skip the staleness check and always refresh.

    Returns:
      {
        "symbol":   "BATAINDIA",
        "view":     "quarterly",
        "sources":  ["NSE","BSE"],     # which sources contributed rows
        "rows":     [ {asOnDate, promoterPct, ...}, ... ],
      }
    """
    canon = canonical_symbol(symbol)
    if not canon:
        return {"symbol": symbol, "view": view, "sources": [], "rows": []}

    cached = _read_history(canon)
    if force or _needs_refresh(cached):
        await _refresh(canon)
        cached = _read_history(canon)

    # Filter to view.
    rows = cached
    if view == "yearly":
        rows = [r for r in cached
                if (r["as_on_date"].month == 3)]
    # Apply quarter cap.
    rows = rows[:max(1, quarters)]

    sources = sorted({r["source"] for r in rows if r.get("source")})
    return {
        "symbol":  canon,
        "view":    view,
        "sources": sources,
        "rows":    [_to_api_row(r) for r in rows],
    }


def _to_api_row(r: dict) -> dict:
    """Convert a PG dict-row to the camelCased API shape the frontend
    expects."""
    d = r["as_on_date"]
    return {
        "asOnDate":        d.isoformat() if hasattr(d, "isoformat") else str(d),
        "promoterPct":     r.get("promoter_pct"),
        "fiiPct":          r.get("fii_pct"),
        "diiPct":          r.get("dii_pct"),
        "publicPct":       r.get("public_pct"),
        "numShareholders": r.get("num_shareholders"),
        "source":          r.get("source"),
    }


async def _refresh(symbol: str) -> None:
    """Walk the source chain, upserting rows from each.

    Source priority + role:
      1. NSE corp-info  — quarterly index (gives us 80 quarters of
                          Promoter/Public AND the XBRL URL per quarter)
      2. XBRL filings   — direct fetch of each quarter's SEBI filing,
                          parsed for the full FII/DII/Public breakdown.
                          Same data Screener ingests, just direct.
      3. Yahoo          — fallback ONLY when zero rows from above
                          (essentially "is this stock alive at all?")
      4. Screener       — defensive fallback when XBRL coverage is thin
                          (some XBRL files are malformed, some quarters
                          haven't been filed yet, some companies use
                          older formats)

    BSE HTML scrape (`_fetch_bse`) is no longer in the chain — it was
    redundant with the XBRL source (Screener gets data from BSE XBRL;
    we now get it from the same place directly, no middleman).

    Never raises — every source is independently try/excepted so one
    bad provider doesn't break the chain."""

    # 1. NSE — gives us the quarter index + XBRL URLs per quarter.
    nse_rows: list[dict] = []
    try:
        nse_rows = await _fetch_nse(symbol)
        if nse_rows:
            n = _upsert_rows(symbol, nse_rows)
            logger.info("shareholding NSE %s: %d rows upserted", symbol, n)
        else:
            # Silent-zero diagnosis. Without this line, an NSE endpoint
            # change / Akamai block looks identical to "nothing to fetch"
            # in the logs. Explicit logging here is the only way to tell.
            logger.info("shareholding NSE %s: returned 0 rows (empty response or fetch failed silently)", symbol)
    except Exception as exc:
        logger.warning("shareholding NSE %s failed: %s", symbol, str(exc)[:160])

    # 2. XBRL — fan-out fetch on the most recent quarters that have
    # an XBRL URL. Cap at 32 (8 years) to bound first-fetch latency.
    # Filings are immutable so the disk cache short-circuits every
    # subsequent call. Quarters beyond this stay as NSE-only
    # (Promoter/Public without FII/DII) — sufficiently old.
    #
    # Cold-cache cost: 32 parallel HTTPs to nsearchives.nseindia.com
    # (~5-10s wall time, all in parallel). Warm cache: O(1) disk reads.
    xbrl_candidates = [r for r in nse_rows if r.get("_xbrl_url")][:32]
    if xbrl_candidates:
        try:
            # Parallel fetch — XBRL files are independent and the disk
            # cache makes second-pass calls essentially free, so the
            # `gather` only pays HTTP cost on the cold-cache rows.
            enriched = await asyncio.gather(*[
                _enrich_with_xbrl(symbol, r["_xbrl_url"], r["as_on_date"])
                for r in xbrl_candidates
            ], return_exceptions=True)
            xbrl_rows = [
                e for e in enriched
                if isinstance(e, dict) and e is not None
            ]
            if xbrl_rows:
                n = _upsert_rows(symbol, xbrl_rows)
                logger.info(
                    "shareholding XBRL %s: %d rows upserted "
                    "(parsed %d/%d filings)",
                    symbol, n, len(xbrl_rows), len(xbrl_candidates),
                )
            else:
                logger.info(
                    "shareholding XBRL %s: 0 filings parsed (of %d URLs tried)",
                    symbol, len(xbrl_candidates),
                )
        except Exception as exc:
            logger.warning("shareholding XBRL %s failed: %s", symbol, str(exc)[:160])
    else:
        logger.info("shareholding XBRL %s: no XBRL URLs from NSE — skipping", symbol)

    # Audit state after the two primary sources.
    current = _read_history(symbol)
    latest_date = current[0]["as_on_date"] if current else None
    if isinstance(latest_date, datetime):
        latest_date = latest_date.date()
    needs_current = (
        latest_date is None
        or (date.today() - latest_date).days > _CURRENT_QUARTER_WINDOW_DAYS
    )
    # Coverage check: how many quarters now have both FII and DII?
    quarters_with_fii_dii = sum(
        1 for r in current
        if r.get("fii_pct") is not None and r.get("dii_pct") is not None
    )

    # 3. Yahoo — only when EVERYTHING above failed. Yahoo gives one
    # row, no FII/DII split, conflates institutional + insider. Useful
    # only as a "this stock isn't completely dark" signal.
    if needs_current and not current:
        try:
            y_rows = await _fetch_yahoo(symbol)
            if y_rows:
                n = _upsert_rows(symbol, y_rows)
                logger.info("shareholding YAHOO %s: %d rows upserted", symbol, n)
            else:
                logger.info("shareholding YAHOO %s: returned 0 rows", symbol)
        except Exception as exc:
            logger.warning("shareholding YAHOO %s failed: %s", symbol, str(exc)[:160])

    # 4. Screener — defensive fallback when XBRL didn't cover enough
    # quarters. Common reasons: pre-2018 filings used older XBRL formats
    # we don't parse, some XBRL URLs 404, new IPOs may not have XBRL
    # for the first 1-2 quarters. Screener has aggregated all of this
    # and serves it consistently. Trigger: <4 quarters with FII/DII.
    needs_screener = (not current) or (quarters_with_fii_dii < 4)
    if needs_screener:
        try:
            s_rows = await _fetch_screener(symbol)
            if s_rows:
                n = _upsert_rows(symbol, s_rows)
                logger.info(
                    "shareholding SCREENER %s: %d rows upserted "
                    "(coverage was %d quarters with FII/DII)",
                    symbol, n, quarters_with_fii_dii,
                )
            else:
                logger.info(
                    "shareholding SCREENER %s: returned 0 rows "
                    "(parser couldn't find the table or fetch failed silently)",
                    symbol,
                )
        except Exception as exc:
            logger.warning("shareholding SCREENER %s failed: %s", symbol, str(exc)[:160])
    else:
        logger.info(
            "shareholding SCREENER %s: skipping (already have %d quarters with FII/DII)",
            symbol, quarters_with_fii_dii,
        )
