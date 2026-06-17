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
import json
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
    as_on_date:          date,
    promoter_pct:        Optional[float] = None,
    fii_pct:             Optional[float] = None,
    dii_pct:             Optional[float] = None,
    public_pct:          Optional[float] = None,
    govt_pct:            Optional[float] = None,
    num_shareholders:    Optional[int]   = None,
    promoter_pledge_pct: Optional[float] = None,
    pledged_shares:      Optional[int]   = None,
    demat_pct:           Optional[float] = None,
    locked_in_pct:       Optional[float] = None,
    details:             Optional[dict]  = None,
    source:              str = "",
) -> dict:
    """Build one normalized shareholding row. Centralised so every
    source produces the same dict shape — easier upserts, easier UI.

    Only the XBRL source populates the enrichment fields (govt_pct,
    pledge, demat/locked-in, details); the NSE/Yahoo/Screener fallbacks
    leave them None and the COALESCE upsert preserves whatever XBRL
    filled in.

    The `as_on_date` is snapped to the nearest standard quarter-end
    here, so any interim/corrigendum filing dates (e.g. OCT 2024 for a
    TCS re-filing) collapse into the matching quarter row instead of
    appearing as a phantom extra column."""
    return {
        "as_on_date":          _snap_to_quarter_end(as_on_date),
        "promoter_pct":        _round(promoter_pct),
        "fii_pct":             _round(fii_pct),
        "dii_pct":             _round(dii_pct),
        "public_pct":          _round(public_pct),
        "govt_pct":            _round(govt_pct),
        "num_shareholders":    int(num_shareholders) if num_shareholders else None,
        "promoter_pledge_pct": _round(promoter_pledge_pct),
        "pledged_shares":      int(pledged_shares) if pledged_shares else None,
        "demat_pct":           _round(demat_pct),
        "locked_in_pct":       _round(locked_in_pct),
        "details":             details or None,
        "source":              source,
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


# ── XBRL category mapping (multi-taxonomy) ──────────────────────────────────
#
# SEBI has published five distinct XBRL taxonomy versions for the
# shareholding pattern schema between 2019 and 2026. The member names
# differ across versions, so a single substring matcher silently
# misses values for any version it wasn't tuned to. The disk cache
# in /app/data/xbrl_cache shows files spanning all five:
#
#   2019-06-30  ForeignInstitutions (FII rollup), ForeignPortfolioInvestor,
#               MutualFundsOrUti, NBFCsRegisteredWithRbi, NonInstitutions, …
#               NO InstitutionsDomestic rollup — DII must be computed.
#   2020-09-30  Same member set as 2019-06-30.
#   2022-09-30  New rollups InstitutionsForeign + InstitutionsDomestic;
#               FPI split into Cat I / Cat II ("Catergory" typo);
#               retains MutualFundsOrUti / NBFCsRegisteredWithRbi casing.
#   2025-05-31  Same shape as 2022-09-30.
#   2025-10-31  Typo fixed (Catergory → Category); case changes
#               (MutualFundsOrUTI, NBFCsRegisteredWithRBI); new members
#               BanksMember, ForeignNationalsMember, KMP, IEPF, …
#
# Strategy: prefer aggregate (rollup) members per bucket; back-fill
# with a component sum when no aggregate exists for that taxonomy.
# All comparisons happen after lowercasing + stripping the trailing
# "Member" suffix.

# Exact aggregate member names → bucket. EXACT match (not substring)
# so children like "InstitutionsForeignPortfolioInvestor" don't
# accidentally collide with the "InstitutionsForeign" aggregate.
_XBRL_BUCKETS_BY_AGGREGATE = {
    # Promoter — consistent across every taxonomy version.
    "shareholdingofpromoterandpromotergroup":  "promoter",
    # FII rollup — distinct names per taxonomy era.
    "institutionsforeign":                     "fii",      # 2022-09-30, 2025-05-31, 2025-10-31
    "foreigninstitutions":                     "fii",      # 2019-06-30, 2020-09-30
    # DII rollup — post-2022 taxonomies only. Pre-2022 has no aggregate
    # so we compute via Institutions − ForeignInstitutions, or via
    # component sum (see _parse_xbrl below).
    "institutionsdomestic":                    "dii",      # 2022-09-30 onwards
    # Public (non-institutional retail) rollup — every taxonomy.
    "noninstitutions":                         "public",
    # Government rollup. In the SEBI category tree, Government (Central +
    # State + President of India) sits under "Public" alongside
    # Institutions and Non-Institutions, but it is NOT part of the
    # NonInstitutions aggregate above. Surfacing it as its own bucket is
    # what makes Promoter+FII+DII+Public+Govt sum to ~100 for PSUs and
    # any company with sovereign holding (else the 4 buckets under-sum).
    "governments":                             "govt",     # GovernmentsMember rollup
}

# Pre-2022 "Institutions" total — used to derive DII as
# Institutions − ForeignInstitutions when no DII aggregate exists.
_XBRL_INSTITUTIONS_TOTAL = "institutions"

# Component (leaf) member name patterns per bucket. Substring matched
# against the lowercased member name. Only used to fill in a bucket
# whose aggregate wasn't found in this filing.
_XBRL_COMPONENT_PATTERNS = {
    "fii": (
        "foreignportfolioinvestor",      # FPI in every taxonomy (incl Cat I/II)
        "foreignventurecapital",         # FVCI
        "foreigndirectinvestment",       # FDI
        "foreignnational",               # ForeignNationalsMember (2025-10)
        "otherinstitutionsforeign",      # 2022+
        "otherforeignshareholder",       # 2019/2020
        "overseasdepositor",             # GDR holders
        "sovereignwealthfundsforeign",   # 2022+
        "qfi",                           # legacy Qualified Foreign Investor
    ),
    "dii": (
        "mutualfunds",                   # MutualFundsOrUti / MutualFundsOrUTI
        "insurancecompanies",
        "alternativeinvestmentfund", "alternateinvestmentfund",
        "venturecapitalfund",            # domestic VC; foreign VC handled in FII
        "indianfinancialinstitutionsorbanks",
        "financialinstitutionorbanks",
        "nbfcsregisteredwith",           # NBFCsRegisteredWithRbi / WithRBI
        "providentfundsorpensionfunds",
        "assetreconstructioncompanies",
        "sovereignwealthfundsdomestic",
        "otherfinancialinstitutions",
        "otherinstitutionsdomestic",
    ),
    "public": (
        "individualsorhindu", "individualshareholder",
        "bodiescorporate", "bodycorporate",
        # NOTE: government members (centralgovernment, stategovernment,
        # presidentofindia, governments) are deliberately NOT here — they
        # belong to the dedicated "govt" bucket below. Keeping them in
        # public would double-count once the govt aggregate is resolved.
        "nonresidentindi",                # NRI variants
        "trust",
        "clearing",
        "otherindianshareholder",
        "anyother", "anyothers",
        "investoreducation",              # IEPF (2025-10)
        "directorsanddirectorsrelative",  # 2025-10
        "keymanagerialpersonnel",         # 2025-10
        "relativesofpromotersotherthanpromotergroup",
        "shareholdingbycompaniesorbodiescorporate",
        "employeebenefitstrust", "employeetrust",
    ),
    "govt": (
        "centralgovernmentorpresidentofindia",   # 2022+ combined member
        "centralgovernment", "stategovernment", "presidentofindia",
        "governments", "goverments",      # "Goverments" typo seen in 2019/2020
    ),
}

# Parent / supercategory members to skip during the component-sum
# pass — they're already covered by an aggregate or would double-count.
_XBRL_PARENT_MEMBERS = frozenset({
    "publicshareholding",          # = NonInstitutions + Institutions + …
    "shareholdingpattern",         # grand total = 100%
    "indian", "foreign",           # 2019/2020 super-rollups
    "sharesheldbynonpromotnonpublicshareholders",
    "sharesheldbynonpromoternonpublicshareholders",
})


# ── Named-shareholder extraction (Tier 2) ───────────────────────────────────
#
# Individual holders disclosed above the SEBI threshold (all promoters,
# every public holder >1%) live in TYPED-dimension contexts, NOT the
# explicit-member category contexts used for the rollup percentages.
# Each holder has two contexts joined by a typed-domain value:
#   * a duration context (period startDate/endDate, id usually prefixed
#     "D_") carrying the string attributes — name, PAN, sub-category;
#   * an instant context carrying the numeric values — shares, holding %.
# The join key is the <xbrldi:typedMember> domain text (e.g.
# "MutualFundsOrUTI_Context15"), identical on both contexts.
#
# Map each typed axis to a coarse display group so the UI can bucket
# "which mutual funds / FIIs hold this" the way Tickertape/Trendlyne do.
_XBRL_NAMED_AXIS_GROUP = {
    "detailsofsharesheldbymutualfundsoruti":                          "Mutual Fund",
    "detailsofsharesheldbyinsurancecompanies":                        "Insurance",
    "detailsofsharesheldbyinstitutionsforeignportfolioinvestorone":   "FII / FPI",
    "detailsofsharesheldbyinstitutionsforeignportfolioinvestortwo":   "FII / FPI",
    "detailsofsharesheldbyfpi":                                       "FII / FPI",
    "detailsofsharesheldbyothernoninstitutions":                      "Public",
    "detailsofsharesheldbyothersindianshareholders":                  "Other Indian",
    "detailsoftheshareholdersactingaspersonsinconcertforpublic":      "PAC",
    "detailsofshareswhichremainunclaimedforpublicshareholders":       "Unclaimed",
}

# Entity-level Yes/No disclosure flags (Tier 3.8). Keyed by the exact
# lowercased element local-name read from the main (no-category) context.
# These describe the capital structure — useful context for whether the
# plain % understates dilution (warrants/ESOPs/convertibles outstanding).
_XBRL_STRUCTURE_FLAGS = {
    "whetherthelistedentityhasanysharesagainstwhichdepositoryreceiptsareissued": "hasDepositoryReceipts",
    "whetherthelistedentityhasgrantedanyesopwhichareoutstanding":                "hasOutstandingEsop",
    "whetherthelistedentityhasissuedanywarrants":                                "hasWarrants",
    "whetherthelistedentityhasissuedanyconvertiblesecurities":                   "hasConvertibles",
    "whetherthelistedentityhasissuedanypartlypaidupshares":                      "hasPartlyPaidShares",
    "whetherthelistedentityhasanysignificantbeneficialowner":                    "hasSignificantBeneficialOwner",
    "whetherthelistedentityispublicsectorundertaking":                           "isPsu",
    "whethercompanyissme":                                                       "isSme",
    "whethercompanyhasequityshareswithdifferentialvotingrights":                 "hasDifferentialVotingRights",
}


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

    Returns the 5 headline buckets (Promoter / FII / DII / Public / Govt)
    plus the enrichments mined from the same file: promoter pledge,
    demat / locked-in %, per-category shareholder counts, the named-holder
    list (typed-dimension rows), FPI limits, voting, and capital-structure
    flags. See the return dict at the bottom for the exact shape.

    Multi-taxonomy strategy:
      1. Walk every <xbrli:context> and build `ctx_id → member` (lowercased,
         "Member" suffix stripped, namespace prefix stripped).
      2. Walk every percentage element and collect `member → pct` for the
         holding-% values. Members are emitted once per filing so a dict
         is fine (last-write-wins is irrelevant here).
      3. Aggregate-first resolution per bucket:
           a. Look up exact aggregate names (`InstitutionsForeign`,
              `InstitutionsDomestic`, `NonInstitutions`,
              `ShareholdingOfPromoterAndPromoterGroup`).
           b. For DII in pre-2022 filings without that aggregate, derive
              as Institutions − ForeignInstitutions.
           c. Last resort: sum leaf components per bucket from
              `_XBRL_COMPONENT_PATTERNS`, with foreign/domestic cross-
              contamination excluded.
      4. Sanity: total of the 4 buckets must be ≤105.

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

    # Detect taxonomy version from any in-bse-shp namespace URL —
    # surfaced in the diagnostic log line so future drift is visible.
    taxo_version = "unknown"
    nsmap = getattr(root, "nsmap", {}) or {}
    for ns in nsmap.values():
        m = re.search(r"xbrl/shp/(\d{4}-\d{2}-\d{2})", ns or "")
        if m:
            taxo_version = m.group(1)
            break

    def _f(text: Optional[str]) -> Optional[float]:
        """float() that swallows None / junk — used all over the new
        numeric extractions below."""
        if text is None:
            return None
        try:
            return float(text)
        except (ValueError, TypeError):
            return None

    # Step 1: walk every <context> ONCE, building two indexes:
    #   context_to_member : ctx_id → last explicit member (lowercased,
    #                       "Member" stripped) — drives bucket resolution.
    #   ctx_index         : ctx_id → {members, typed, period} — the richer
    #                       view the Tier-2/3 extractions need (typed
    #                       dimensions carry the named-holder rows; period
    #                       distinguishes the duration context that holds a
    #                       holder's name/PAN from the instant context that
    #                       holds its share count / %).
    context_to_member: dict[str, str] = {}
    ctx_index: dict[str, dict] = {}
    for ctx in root.iter():
        if etree.QName(ctx).localname != "context":
            continue
        ctx_id = ctx.get("id", "").strip()
        if not ctx_id:
            continue
        members: list[tuple[str, str]] = []
        typed: Optional[tuple[str, Optional[str]]] = None
        period = "?"
        for descendant in ctx.iter():
            ln = etree.QName(descendant).localname
            if ln == "explicitMember":
                member = (descendant.text or "").strip()
                if ":" in member:
                    member = member.split(":", 1)[1]
                if member.endswith("Member"):
                    member = member[:-6]
                dim = (descendant.get("dimension") or "").split(":")[-1].lower()
                members.append((dim, member.lower()))
            elif ln == "typedMember":
                axis = (descendant.get("dimension") or "").split(":")[-1].lower()
                dom = None
                for child in descendant:
                    dom = (child.text or "").strip()
                if axis:
                    typed = (axis, dom)
            elif ln == "instant":
                period = "I"
            elif ln == "endDate":
                period = "D"
        ctx_index[ctx_id] = {"members": members, "typed": typed, "period": period}
        if members:
            # Last explicit member = the most specific category on this
            # context (the bucket logic only ever wants the leaf member).
            context_to_member[ctx_id] = members[-1][1]

    # Step 2: collect MAX % per member. SEBI filings sometimes emit
    # the same member across multiple contexts with one zero placeholder
    # and one real value (varies by filer). Max-per-member picks the
    # real value while still producing 0 for genuinely-empty categories.
    member_pct: dict[str, float] = {}
    # vals: ctx_id → {element_localname_lower: text}. A flat per-context
    # view of every value-carrying element, used by the Tier-2/3
    # extractions (named holders, pledge, demat, counts, flags). Element
    # local-names are unique within a context in these filings, so a
    # first-write-wins dict is correct.
    vals: dict[str, dict[str, str]] = {}
    for el in root.iter():
        localname = etree.QName(el).localname
        if not localname:
            continue
        ln_lower = localname.lower()
        text = (el.text or "").strip()
        ctx_ref = el.get("contextRef", "")
        if ctx_ref and text:
            bag = vals.get(ctx_ref)
            if bag is None:
                bag = vals[ctx_ref] = {}
            bag.setdefault(ln_lower, text)
        # Skip elements that report locked-in / pledged status, not the
        # bucket breakdown.
        if "lockedinshares" in ln_lower or "pledgedorencumbered" in ln_lower:
            continue
        is_holding = (
            "shareholdingasapercentageoftotalnumberofshares" in ln_lower
            or "shareholdingasapercentageassumingfullconversion" in ln_lower
        )
        if not is_holding:
            continue
        # Skip elements with no text — empty placeholders read as 0 and
        # would wrongly populate a member entry.
        if not text:
            continue
        member = context_to_member.get(ctx_ref, "")
        if not member:
            continue
        try:
            pct = float(text)
        except (ValueError, TypeError):
            continue
        # Accept 0-100 (percentage form) and 0-1 (fraction form); we
        # detect-and-scale fractions after bucket resolution.
        if pct < 0 or pct > 100:
            continue
        existing = member_pct.get(member, -1.0)
        if pct > existing:
            member_pct[member] = pct

    if not member_pct:
        return None

    # Step 3a: aggregate-first resolution.
    # Note: many SEBI filings emit the FII/DII rollups as a value-0
    # placeholder and only fill component leaves. We reject value==0
    # for those two buckets so the component-sum step can fill them.
    # Promoter/Public aggregates are accepted at 0 because some companies
    # genuinely have zero promoter holding (and have no component
    # fallback patterns defined here).
    buckets: dict[str, Optional[float]] = {
        "promoter": None, "fii": None, "dii": None, "public": None,
        "govt": None,
    }
    bucket_strategy: dict[str, str] = {}    # diagnostic trail

    for member, value in member_pct.items():
        bucket = _XBRL_BUCKETS_BY_AGGREGATE.get(member)
        if not bucket or buckets[bucket] is not None:
            continue
        if value == 0 and bucket in ("fii", "dii"):
            # Placeholder aggregate; let the component-sum step
            # backfill from the leaves.
            continue
        buckets[bucket] = value
        bucket_strategy[bucket] = f"aggregate:{member}"

    # Step 3b: DII via subtraction (pre-2022 taxonomies have
    # InstitutionsMember total and a ForeignInstitutions aggregate
    # but no DomesticInstitutions rollup).
    if buckets["dii"] is None:
        inst_total = member_pct.get(_XBRL_INSTITUTIONS_TOTAL)
        foreign_inst = (
            member_pct.get("foreigninstitutions")
            or member_pct.get("institutionsforeign")
        )
        if inst_total is not None and foreign_inst is not None:
            diff = inst_total - foreign_inst
            if 0 <= diff <= 100:
                buckets["dii"] = diff
                bucket_strategy["dii"] = "subtract:institutions-foreigninst"

    # Step 3c: component-sum fallback for any bucket still NULL.
    for bucket_name, patterns in _XBRL_COMPONENT_PATTERNS.items():
        if buckets[bucket_name] is not None:
            continue
        total = 0.0
        any_matched = False
        for member, value in member_pct.items():
            # Skip members already consumed as aggregates / parents.
            if member in _XBRL_BUCKETS_BY_AGGREGATE:
                continue
            if member in _XBRL_PARENT_MEMBERS:
                continue
            if member == _XBRL_INSTITUTIONS_TOTAL:
                continue
            # Cross-bucket exclusions so e.g. ForeignVentureCapital
            # doesn't get pulled into DII via the "venturecapital"
            # substring.
            if bucket_name == "dii" and "foreign" in member:
                continue
            if bucket_name == "fii" and ("domestic" in member
                                         or "indian" in member):
                continue
            if any(p in member for p in patterns):
                total += value
                any_matched = True
        if any_matched:
            buckets[bucket_name] = total
            bucket_strategy[bucket_name] = "component_sum"

    # Detect fraction-encoded filings and scale. Starting with some
    # 2025-09-30 filings, certain filers emit percentage element values
    # as 0-1 fractions (e.g. 0.7177 for 71.77%) rather than 0-100. The
    # XBRL `unitRef="pure"` doesn't distinguish — only the magnitude
    # gives it away. Real percentage breakdowns always sum to ~100; if
    # the total is below 5, treat the file as fraction-encoded.
    total_all = sum(v for v in buckets.values() if v is not None)
    # `scale` is reused by the Tier-2/3 extractions below so named-holder
    # %, pledge %, etc. land in the same units as the headline buckets.
    scale = 100.0 if (0 < total_all < 5) else 1.0
    if scale != 1.0:
        for k in list(buckets.keys()):
            if buckets[k] is not None:
                buckets[k] *= scale
        total_all *= scale
        bucket_strategy["_scale"] = "x100_fractions"

    # Infer Promoter = 0 for companies with no promoter holding (e.g.
    # ICICIBANK, HDFCBANK). These filers omit the Promoter aggregate
    # element entirely rather than emit it as zero. If the other three
    # buckets account for ~100%, the missing Promoter is genuinely 0%.
    if buckets["promoter"] is None:
        others_sum = sum(v for k, v in buckets.items()
                         if k != "promoter" and v is not None)
        if 90 < others_sum < 105:
            buckets["promoter"] = 0.0
            bucket_strategy["promoter"] = "inferred_zero"
            total_all = others_sum

    # Sanity check — sum > 105 indicates double-counting (parent +
    # children both pulled in). Drop and let a fallback source handle.
    if total_all > 105:
        logger.debug(
            "XBRL parse (taxo=%s): bucket total %.2f > 105 — dropping (buckets=%s)",
            taxo_version, total_all, buckets,
        )
        return None

    if all(v is None for v in buckets.values()):
        logger.debug(
            "XBRL parse (taxo=%s): no buckets resolved from %d members",
            taxo_version, len(member_pct),
        )
        return None

    # Diagnostic — emitted at DEBUG so it's visible when
    # SHAREHOLDING_DISABLE_CACHE=1 + LOG_LEVEL=DEBUG is set.
    logger.debug(
        "XBRL parse (taxo=%s) promoter=%s fii=%s dii=%s public=%s govt=%s strategies=%s",
        taxo_version,
        buckets["promoter"], buckets["fii"], buckets["dii"], buckets["public"],
        buckets["govt"], bucket_strategy,
    )

    # Step 4: total shareholder count. The grand total is the max across
    # every context (the company-wide "Total" row ≥ any single category).
    num_shareholders: Optional[int] = None
    for el in root.iter():
        ln = etree.QName(el).localname or ""
        if not ln:
            continue
        ll = ln.lower()
        if ("numberofshareholders" in ll
                or "totalnoofshareholders" in ll
                or "totalnumberofshareholders" in ll):
            try:
                v = int(float((el.text or "0").strip()))
                if num_shareholders is None or v > num_shareholders:
                    num_shareholders = v
            except (ValueError, TypeError):
                continue

    # ── Helpers shared by the Tier-2/3 extractions ───────────────────────
    def _num(cid: Optional[str], *names: str) -> Optional[float]:
        """First parseable numeric among `names` in context `cid`."""
        if not cid:
            return None
        bag = vals.get(cid, {})
        for n in names:
            f = _f(bag.get(n))
            if f is not None:
                return f
        return None

    def _cat_ctx(target_member: str) -> Optional[str]:
        """ctx_id of the single-category INSTANT context for `target_member`
        (e.g. the promoter aggregate). Single-member so we don't match a
        named-holder typed context that happens to share the category."""
        for cid, info in ctx_index.items():
            if (info["period"] == "I" and len(info["members"]) == 1
                    and info["members"][0][1] == target_member):
                return cid
        return None

    # ── Tier 1.3: per-category shareholder counts ────────────────────────
    # Iterate single-member instant contexts; whenever the member maps to
    # one of our buckets, record its NumberOfShareholders. First-write-wins
    # keeps the aggregate (FII rollup) over any stray duplicate.
    category_counts: dict[str, int] = {}
    for cid, info in ctx_index.items():
        if info["period"] != "I" or len(info["members"]) != 1:
            continue
        bucket = _XBRL_BUCKETS_BY_AGGREGATE.get(info["members"][0][1])
        if not bucket or bucket in category_counts:
            continue
        n = _num(cid, "numberofshareholders")
        if n is not None:
            category_counts[bucket] = int(n)

    # ── Tier 1.1: promoter pledge / encumbrance ──────────────────────────
    # Pledge % is reported in Screener's convention as a fraction of the
    # PROMOTER holding (not of total shares), so we derive it from the
    # pledged-share count over the promoter group's share count.
    promoter_cid = _cat_ctx("shareholdingofpromoterandpromotergroup")
    promoter_shares = _num(promoter_cid, "numberofshares",
                           "numberoffullypaidupequityshares")
    pledged_shares = _num(promoter_cid, "pledgedorencumberednumberofshares")
    promoter_pledge_pct: Optional[float] = None
    if pledged_shares is not None and promoter_shares and promoter_shares > 0:
        promoter_pledge_pct = round(pledged_shares / promoter_shares * 100, 2)

    # ── Tier 2.5: demat % and locked-in % (company-wide) ─────────────────
    # The grand-total context = the one carrying the largest "total nos.
    # of shares held" count; its demat / locked-in totals are the
    # company-wide figures. The denominator MUST be NumberOfShares (the
    # total incl. partly-paid + DR-underlying), NOT NumberOfFullyPaidUp:
    # demat / locked-in are reported against the total, so dividing by
    # fully-paid alone overshoots 100% whenever a company has partly-paid
    # shares (e.g. a rights issue) or large ADR/GDR underlying (e.g.
    # HDFCBANK). Count ratios are already true % — no fraction-scaling.
    grand_cid: Optional[str] = None
    grand_shares = -1.0
    for cid, bag in vals.items():
        f = _f(bag.get("numberofshares")) or _f(bag.get("numberoffullypaidupequityshares"))
        if f is not None and f > grand_shares:
            grand_shares, grand_cid = f, cid
    total_shares = grand_shares if grand_shares >= 0 else None
    demat_pct: Optional[float] = None
    locked_in_pct: Optional[float] = None
    if total_shares and total_shares > 0 and grand_cid:
        dm = _num(grand_cid, "numberofequitysharesheldindematerializedform")
        lk = _num(grand_cid, "numberofthelockedinshares")
        if dm is not None:
            demat_pct = round(min(dm / total_shares * 100, 100.0), 2)
        if lk is not None:
            locked_in_pct = round(lk / total_shares * 100, 2)

    # ── Tier 2.4: named shareholders (typed-dimension join) ──────────────
    # Index instant contexts by their typed (axis, domain) key, then walk
    # the duration contexts (which carry name/PAN/category) and join to the
    # matching instant context (which carries shares / %).
    inst_by_typed: dict[tuple, str] = {}
    for cid, info in ctx_index.items():
        if info["typed"] and info["period"] == "I":
            inst_by_typed[info["typed"]] = cid

    named_holders: list[dict] = []
    for cid, info in ctx_index.items():
        if not info["typed"] or info["period"] != "D":
            continue
        bag = vals.get(cid, {})
        name = bag.get("nameoftheshareholder")
        if not name:
            continue
        axis, dom = info["typed"]
        ibag = vals.get(inst_by_typed.get((axis, dom), ""), {})
        shares = _f(ibag.get("numberofshares")
                    or ibag.get("numberoffullypaidupequityshares"))
        pct = _f(ibag.get("shareholdingasapercentageoftotalnumberofshares"))
        if pct is not None:
            pct = round(pct * scale, 4)
        group = "Other"
        for key, label in _XBRL_NAMED_AXIS_GROUP.items():
            if key in axis:
                group = label
                break
        pan = bag.get("permanentaccountnumberofshareholder")
        if pan and set(pan) <= {"*"}:        # masked PAN ("******") → drop
            pan = None
        named_holders.append({
            "name":     name.strip(),
            "pan":      pan,
            "group":    group,
            "category": bag.get("categoryofotherindianshareholders")
                        or bag.get("categoryofothernoninstitutions"),
            "shares":   int(shares) if shares is not None else None,
            "pct":      pct,
        })
    # Most-significant holders first; nulls (PAC/unclaimed rows w/o %) last.
    named_holders.sort(key=lambda h: (h["pct"] is None, -(h["pct"] or 0.0)))

    # ── Tier 3.6/3.7/3.8: FPI limits, voting, capital-structure flags ────
    # Entity-level disclosures are tagged against a single no-dimension
    # context — but its id/shape varies by taxonomy (2025 filings use a
    # member-less "MainI"; 2022 filings reference a "OneI" context that
    # isn't even separately defined). Rather than guess the context, look
    # each entity-level element up across every context's bag. These
    # names are unique and unscoped — the per-category variants carry a
    # "...ForPromoterAndPromoterGroup"-style suffix (a different local
    # name) — so the first occurrence is the entity-level value.
    def _any_val(name: str) -> Optional[str]:
        for bag in vals.values():
            v = bag.get(name)
            if v is not None:
                return v
        return None

    flags: dict[str, bool] = {}
    for elem_name, key in _XBRL_STRUCTURE_FLAGS.items():
        raw = _any_val(elem_name)
        if raw is not None:
            flags[key] = raw.strip().lower() in ("true", "1", "yes")

    fpi_limits: dict[str, float] = {}
    # Same fraction-vs-percent encoding as the holdings, so apply `scale`.
    bl = _f(_any_val("percentageofboardapprovedlimits"))
    lu = _f(_any_val("percentageoflimitsutilized"))
    if bl is not None:
        fpi_limits["boardApprovedPct"] = round(bl * scale, 2)
    if lu is not None:
        fpi_limits["limitsUtilizedPct"] = round(lu * scale, 2)

    voting: dict = {}
    if flags.get("hasDifferentialVotingRights"):
        voting["hasDifferentialVotingRights"] = True
    frozen = _num(grand_cid, "votingrightswhicharefrozen") if grand_cid else None
    if frozen:
        voting["frozenVotingRights"] = int(frozen)

    details: dict = {}
    if named_holders:
        details["namedHolders"] = named_holders[:200]
    if category_counts:
        details["categoryCounts"] = category_counts
    if voting:
        details["voting"] = voting
    if fpi_limits:
        details["fpiLimits"] = fpi_limits
    if flags:
        details["flags"] = flags

    return {
        "promoter_pct":        _round(buckets["promoter"]),
        "fii_pct":             _round(buckets["fii"]),
        "dii_pct":             _round(buckets["dii"]),
        "public_pct":          _round(buckets["public"]),
        "govt_pct":            _round(buckets["govt"]),
        "num_shareholders":    num_shareholders,
        "promoter_pledge_pct": promoter_pledge_pct,
        "pledged_shares":      int(pledged_shares) if pledged_shares else None,
        "demat_pct":           demat_pct,
        "locked_in_pct":       locked_in_pct,
        "details":             details or None,
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
        as_on_date          = as_on,
        promoter_pct        = parsed.get("promoter_pct"),
        fii_pct             = parsed.get("fii_pct"),
        dii_pct             = parsed.get("dii_pct"),
        public_pct          = parsed.get("public_pct"),
        govt_pct            = parsed.get("govt_pct"),
        num_shareholders    = parsed.get("num_shareholders"),
        promoter_pledge_pct = parsed.get("promoter_pledge_pct"),
        pledged_shares      = parsed.get("pledged_shares"),
        demat_pct           = parsed.get("demat_pct"),
        locked_in_pct       = parsed.get("locked_in_pct"),
        details             = parsed.get("details"),
        source              = "XBRL",
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
      5. Government maps to its own govt_pct column (matching the XBRL
         path), so the five buckets sum to ~100.
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
        "government":         "govt_pct",
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
        if col is None:
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
            else:
                b[col] = _round(val)

    return list(out.values())


# ── Quarter math ────────────────────────────────────────────────────────────


def _last_quarter_end(d: date) -> date:
    """Return the most recent COMPLETED quarter-end on or before `d`.

    For d=2026-06-13 returns 2026-03-31 — Jun 30 hasn't happened yet,
    so labelling a snapshot today with "Jun 30 2026" creates a phantom
    column ahead of reality. For d=2026-06-30 returns 2026-06-30 (the
    quarter just completed). For d=2026-04-01 returns 2026-03-31.

    Used by Yahoo / Screener fallback paths that take a current
    snapshot and need to label it with a quarter-end. Always snaps
    backward so the row goes into a real, settled column.
    """
    candidates = [
        date(d.year - 1, 12, 31),
        date(d.year,      3, 31),
        date(d.year,      6, 30),
        date(d.year,      9, 30),
        date(d.year,     12, 31),
    ]
    past = [c for c in candidates if c <= d]
    return max(past) if past else candidates[0]


def _snap_to_quarter_end(d: date) -> date:
    """Snap any filing date to the nearest PAST or CURRENT standard
    quarter-end (31-Mar, 30-Jun, 30-Sep, 31-Dec).

    Why this exists: SEBI requires shareholding filings for the four
    standard quarter-ends. But the NSE / XBRL / Screener pipelines
    occasionally surface non-standard dates — interim corrigendum
    filings, re-filings with the document date instead of the
    period-end, corporate-event record dates (bonus issue, buyback).
    Without snapping, those become phantom columns in the UI ("OCT 2024"
    alongside SEP 2024 and DEC 2024).

    Constraint: never snap to a FUTURE quarter-end. A filing dated
    2026-06-11 (when today is 2026-06-13) used to snap forward to
    2026-06-30 — a quarter that hasn't occurred yet. That created a
    phantom JUN 2026 column with partial data. We now cap candidates
    at the most recently completed quarter-end.

    Algorithm: pick the closest quarter-end that is ≤ today's last
    completed quarter-end. For an Oct 29 2024 filing, snaps to Sep 30
    2024 (29 days back). For a Jun 11 2026 filing (when today is
    mid-June 2026), snaps to Mar 31 2026 instead of Jun 30 2026.

    Idempotent — already-snapped dates pass through unchanged."""
    candidates = [
        date(d.year - 1, 12, 31),
        date(d.year - 1,  9, 30),
        date(d.year,      3, 31),
        date(d.year,      6, 30),
        date(d.year,      9, 30),
        date(d.year,     12, 31),
    ]
    # Cap at today's last completed quarter-end so we never project
    # a row forward into a quarter that hasn't happened.
    last_completed = _last_quarter_end(date.today())
    candidates = [c for c in candidates if c <= last_completed]
    if not candidates:
        # Pathological: d is far in the past. Fall back to the floor.
        return last_completed
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
                details_json = (
                    json.dumps(r.get("details"))
                    if r.get("details") is not None else None
                )
                cur.execute(
                    """
                    INSERT INTO shareholding_history
                        (symbol, as_on_date, promoter_pct, fii_pct, dii_pct,
                         public_pct, govt_pct, num_shareholders,
                         promoter_pledge_pct, pledged_shares, demat_pct,
                         locked_in_pct, details, source, fetched_at_ms)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s::jsonb, %s, %s)
                    ON CONFLICT (symbol, as_on_date) DO UPDATE SET
                        promoter_pct        = COALESCE(EXCLUDED.promoter_pct,        shareholding_history.promoter_pct),
                        fii_pct             = COALESCE(EXCLUDED.fii_pct,             shareholding_history.fii_pct),
                        dii_pct             = COALESCE(EXCLUDED.dii_pct,             shareholding_history.dii_pct),
                        public_pct          = COALESCE(EXCLUDED.public_pct,          shareholding_history.public_pct),
                        govt_pct            = COALESCE(EXCLUDED.govt_pct,            shareholding_history.govt_pct),
                        num_shareholders    = COALESCE(EXCLUDED.num_shareholders,    shareholding_history.num_shareholders),
                        promoter_pledge_pct = COALESCE(EXCLUDED.promoter_pledge_pct, shareholding_history.promoter_pledge_pct),
                        pledged_shares      = COALESCE(EXCLUDED.pledged_shares,      shareholding_history.pledged_shares),
                        demat_pct           = COALESCE(EXCLUDED.demat_pct,           shareholding_history.demat_pct),
                        locked_in_pct       = COALESCE(EXCLUDED.locked_in_pct,       shareholding_history.locked_in_pct),
                        details             = COALESCE(EXCLUDED.details,             shareholding_history.details),
                        source              = EXCLUDED.source,
                        fetched_at_ms       = EXCLUDED.fetched_at_ms
                    """,
                    (
                        symbol,
                        r["as_on_date"],
                        r["promoter_pct"],
                        r["fii_pct"],
                        r["dii_pct"],
                        r["public_pct"],
                        r.get("govt_pct"),
                        r["num_shareholders"],
                        r.get("promoter_pledge_pct"),
                        r.get("pledged_shares"),
                        r.get("demat_pct"),
                        r.get("locked_in_pct"),
                        details_json,
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
                       public_pct, govt_pct, num_shareholders,
                       promoter_pledge_pct, pledged_shares, demat_pct,
                       locked_in_pct, details, source, fetched_at_ms
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
    expects. `details` (JSONB) round-trips as a dict from psycopg3; we
    defensively json.loads it in case a driver hands it back as text."""
    d = r["as_on_date"]
    details = r.get("details")
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except (ValueError, TypeError):
            details = None
    return {
        "asOnDate":          d.isoformat() if hasattr(d, "isoformat") else str(d),
        "promoterPct":       r.get("promoter_pct"),
        "fiiPct":            r.get("fii_pct"),
        "diiPct":            r.get("dii_pct"),
        "publicPct":         r.get("public_pct"),
        "govtPct":           r.get("govt_pct"),
        "numShareholders":   r.get("num_shareholders"),
        "promoterPledgePct": r.get("promoter_pledge_pct"),
        "pledgedShares":     r.get("pledged_shares"),
        "dematPct":          r.get("demat_pct"),
        "lockedInPct":       r.get("locked_in_pct"),
        "details":           details,
        "source":            r.get("source"),
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
