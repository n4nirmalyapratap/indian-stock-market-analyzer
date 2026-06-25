"""IPO Center data service.

Wraps the public NSE IPO endpoints (no auth required, cookie-bootstrap handled
by `NseService.fetch_nse`) and normalises the payloads into a single shape the
frontend can render directly. Subscription details for OPEN issues are fetched
in parallel via /api/ipo-detail and aggregated into the per-category multiples
the IPO Center cards display.

Sources:
  * NSE  /api/all-upcoming-issues?category=ipo  → Open + Forthcoming list
  * NSE  /api/ipo-detail?symbol=XXX             → live subscription multiples
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Optional

from .nse_service import NseService
from . import gmp_service

logger = logging.getLogger("ipo")

# How many minutes the response stays cached before we re-hit NSE.
OPEN_TTL_SEC     = 5 * 60      # subscription numbers refresh ~every 5 min
UPCOMING_TTL_SEC = 30 * 60     # forthcoming list rarely changes intra-day

# Top-level result cache so repeated page loads don't re-run the full
# NSE + GMP + subscription pipeline.  5 min TTL matches OPEN_TTL_SEC.
import time as _time  # noqa: E402
_RESULT_CACHE: dict = {}
_RESULT_CACHE_TTL = 5 * 60   # seconds


def _to_int(v: Any) -> Optional[int]:
    try:
        if v in (None, "", "-"):
            return None
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _to_float(v: Any) -> Optional[float]:
    try:
        if v in (None, "", "-"):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


_PRICE_RE = re.compile(r"(\d+(?:\.\d+)?)")


def _parse_price_band(s: Any) -> tuple[Optional[float], Optional[float]]:
    """'Rs.162 to Rs.171' → (162.0, 171.0). Handles single-price ('Rs.95')
    and weird whitespace too."""
    if not s or not isinstance(s, str):
        return (None, None)
    nums = _PRICE_RE.findall(s)
    if not nums:
        return (None, None)
    if len(nums) == 1:
        v = float(nums[0])
        return (v, v)
    return (float(nums[0]), float(nums[1]))


def _parse_iso(d: Any) -> Optional[str]:
    """'30-Apr-2026' → '2026-04-30' (frontend then formats as needed)."""
    if not d or not isinstance(d, str):
        return None
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(d.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _classify(item: dict) -> str:
    """NSE marks both Active and Forthcoming in the same feed. We split them
    into 'open' (currently accepting bids) vs 'upcoming' (bid window not yet
    started) — the two tabs the UI surfaces separately."""
    status = (item.get("status") or "").lower()
    if status == "active":
        return "open"
    return "upcoming"


def _norm_name(name: str) -> str:
    """Lowercase + strip suffixes/punctuation so the same company spelled
    slightly differently across NSE and ipowatch collapses to one key.
    Used to deduplicate the two sources when we merge them in
    `IpoService.get_calendar`.
    """
    import re  # noqa: PLC0415
    s = (name or "").lower()
    s = re.sub(r"\b(limited|ltd|pvt|private|co\.?|inc\.?|corp\.?|company)\b", "", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_DATE_RANGE_RE = None


def _parse_gmp_date_range(s: str) -> tuple[Optional[str], Optional[str]]:
    """ipowatch.in dates come as `21-25 May` or `26 May - 29 May` style
    strings. We pull out the open / close ISO dates best-effort.

    Returns (openIso, closeIso). Either may be None when the string can't
    be parsed — the UI is defensive about missing dates.
    """
    import re  # noqa: PLC0415
    from datetime import date as _date  # noqa: PLC0415
    global _DATE_RANGE_RE
    if _DATE_RANGE_RE is None:
        # Matches '21-25 May' OR '21 May-25 May' OR '21 May - 25 May'
        _DATE_RANGE_RE = re.compile(
            r"(\d{1,2})\s*(?:([A-Za-z]+))?\s*[-–to]+\s*(\d{1,2})\s*([A-Za-z]+)",
            re.I,
        )
    if not s or not isinstance(s, str):
        return (None, None)
    m = _DATE_RANGE_RE.search(s)
    if not m:
        return (None, None)
    d1, m1, d2, m2 = m.groups()
    months = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
              "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
    mn1 = months.get((m1 or m2 or "").lower()[:3])
    mn2 = months.get((m2 or "").lower()[:3])
    if not mn1 or not mn2:
        return (None, None)
    today = _date.today()
    year = today.year
    try:
        d_open  = _date(year, mn1, int(d1)).isoformat()
        d_close = _date(year, mn2, int(d2)).isoformat()
        return (d_open, d_close)
    except (ValueError, TypeError):
        return (None, None)


def _synth_issue_from_gmp(row: dict) -> Optional[dict]:
    """Convert an ipowatch.in row into the same flat IpoIssue shape that
    `_normalise_issue` produces from NSE rows.

    Used for IPOs that ipowatch tracks but NSE doesn't return — the bulk
    of SME issues (BSE SME entirely, and many NSE EMERGE issues missing
    from the public upcoming-issues feed). Subscription multiples are
    absent because only NSE exposes them; the UI handles that gracefully.

    Returns None when the row lacks the bare minimum (name + status) to
    be useful.
    """
    name = (row.get("name") or "").strip()
    if not name:
        return None
    status = (row.get("status") or "").lower()
    if status not in ("open", "upcoming", "closed"):
        status = "open"  # default to open so the UI shows it somewhere
    if status == "closed":
        return None  # don't surface listed IPOs on the open/upcoming tabs
    raw_type = (row.get("type") or "").lower()
    is_sme   = "sme" in raw_type
    series   = "SME" if is_sme else "EQ"
    # Synth a stable symbol slug from the name so the frontend's key={symbol}
    # doesn't collide across rows. Pure cosmetic — these slugs aren't real
    # NSE/BSE tickers.
    import re  # noqa: PLC0415
    slug = re.sub(r"[^A-Z0-9]", "", name.upper())[:24] or name.upper()[:24]
    # Price band: ipowatch only stores the cap price, treat it as priceHigh.
    price_high = row.get("priceBand")
    open_iso, close_iso = _parse_gmp_date_range(row.get("date") or "")
    return {
        "symbol":       slug,
        "companyName":  name,
        "series":       series,
        "isSme":        is_sme,
        "isReit":       False,
        "openDate":     open_iso,
        "closeDate":    close_iso,
        "priceLow":     None,
        "priceHigh":    float(price_high) if isinstance(price_high, (int, float)) else None,
        "lotSize":      None,
        "issueSizeCr":  None,
        "issueShares":  None,
        "status":       "open" if status == "open" else "upcoming",
        "rawStatus":    status,
        # Mark provenance so the UI can show a small "ipowatch source" hint
        # if it ever wants to.
        "fromGmpOnly":  True,
    }


def _normalise_issue(item: dict) -> dict:
    """Flatten a raw NSE upcoming-issues row into the shape the UI consumes."""
    low, high = _parse_price_band(item.get("issuePrice") or item.get("priceBand"))
    issue_size_shares = _to_int(item.get("issueSize"))
    # NSE returns issue size in number of shares — convert to ₹ crore using the
    # midpoint of the price band so cards can show "₹X Cr" like every other
    # IPO calendar does.
    issue_size_cr = None
    if issue_size_shares and low and high:
        midpoint = (low + high) / 2
        issue_size_cr = round(issue_size_shares * midpoint / 1e7, 2)

    return {
        "symbol":       item.get("symbol") or "",
        "companyName":  item.get("companyName") or "",
        "series":       item.get("series") or "EQ",     # EQ / SME / RR
        "isSme":        (item.get("series") or "").upper() == "SME",
        "isReit":       (item.get("series") or "").upper() in ("RR", "RETT"),
        "openDate":     _parse_iso(item.get("issueStartDate")),
        "closeDate":    _parse_iso(item.get("issueEndDate")),
        "priceLow":     low,
        "priceHigh":    high,
        "lotSize":      _to_int(item.get("lotSize")),
        "issueSizeCr":  issue_size_cr,
        "issueShares":  issue_size_shares,
        "status":       _classify(item),
        "rawStatus":    item.get("status"),
    }


def _summarise_subscription(detail: dict) -> dict:
    """Pull the four headline subscription multiples (QIB / NII / Retail /
    Total) out of NSE's per-category bidDetails table.

    NSE labels are inconsistent across issues (sometimes "Non Institutional
    Investors", sometimes "Non-Institutional Investors", sometimes split
    into >10L / <10L sub-rows). We pick the **first** parent-row match per
    category — these always appear before their sub-rows — and ignore
    anything that has a parenthesised qualifier (which marks sub-rows)."""
    out: dict[str, Optional[float]] = {"qib": None, "nii": None, "retail": None, "total": None}
    for row in (detail or {}).get("bidDetails", []) or []:
        cat = (row.get("category") or "").strip().lower()
        if not cat:
            continue
        n = _to_float(row.get("noOfTime"))
        if n is None:
            continue
        # Skip parenthesised sub-rows so we only capture the parent row's total.
        is_subrow = "(" in cat and not cat.endswith("(qibs)")
        if cat == "total" and out["total"] is None:
            out["total"] = n
        elif "qualified institutional" in cat and out["qib"] is None:
            # Parent QIB row ends in "(qibs)" — accept that, skip FII/Mutual sub-rows.
            if cat.endswith("(qibs)") or not is_subrow:
                out["qib"] = n
        elif "non" in cat and "institutional" in cat and not is_subrow and out["nii"] is None:
            out["nii"] = n
        elif "retail" in cat and "individual" in cat and not is_subrow and out["retail"] is None:
            out["retail"] = n
    return out


class IpoService:
    """Thin orchestration on top of NseService — read-through with TTL
    cache. Successful NSE responses are persisted to the local SQLite
    ipo_store so the calendar still works when NSE is blocked."""

    def __init__(self, nse: NseService):
        self._nse = nse

    async def get_calendar(self) -> dict:
        """Build the combined open+upcoming IPO list.

        Two sources:
          1. **NSE mainboard** via `/api/all-upcoming-issues?category=ipo` —
             authoritative for NSE-listed mainboard issues, ships subscription
             multiples for OPEN issues.
          2. **ipowatch.in** GMP table — covers BSE SME, NSE SME (EMERGE),
             and mainboard. SME IPOs are listed here but NOT on NSE's public
             upcoming-issues feed, so this is the only practical source for
             the bulk of SME activity.

        Strategy: NSE rows are the spine (richer data). For every ipowatch
        row whose company name isn't already in the NSE list, we synthesise
        a thinner IpoIssue with whatever ipowatch gives us (name, gmp,
        priceBand, type=SME/Mainboard, status). The user gets a complete
        IPO calendar instead of the silently-truncated mainboard-only list.

        Result is cached in-process for _RESULT_CACHE_TTL seconds so repeated
        page loads skip the full NSE + GMP + subscription pipeline.
        """
        now = _time.monotonic()
        cached = _RESULT_CACHE.get("result")
        if cached and now - cached[0] < _RESULT_CACHE_TTL:
            logger.debug("ipo calendar: serving from cache")
            return cached[1]

        from . import ipo_store as _store  # noqa: PLC0415

        # NSE mainboard + ipowatch.in scrape concurrently.
        raw_main, gmp_table = await asyncio.gather(
            self._nse.fetch_nse(
                "/api/all-upcoming-issues?category=ipo",
                "ipo-upcoming-issues",
                ttl=OPEN_TTL_SEC,
            ),
            gmp_service.fetch_gmp_table(),
            return_exceptions=True,
        )
        main_ok = isinstance(raw_main, list)
        if isinstance(gmp_table, Exception):
            gmp_table = {"byName": {}, "fetchedAt": None}

        # ── Step 1: normalise the NSE mainboard list ──────────────────────
        seen_names: set[str] = set()
        items: list[dict] = []
        if main_ok:
            for it in raw_main:
                if not isinstance(it, dict) or not it.get("symbol"):
                    continue
                norm = _normalise_issue(it)
                items.append(norm)
                seen_names.add(_norm_name(norm.get("companyName") or ""))

        # ── Step 2: add SME / unknown issues from ipowatch.in ─────────────
        gmp_by_name = (gmp_table or {}).get("byName") or {}
        for _key, row in gmp_by_name.items():
            company = (row.get("name") or "").strip()
            if not company:
                continue
            if _norm_name(company) in seen_names:
                continue
            synth = _synth_issue_from_gmp(row)
            if synth is None:
                continue
            items.append(synth)
            seen_names.add(_norm_name(company))

        # ── Step 3: persist to SQLite store (survives NSE blocks/restarts) ─
        if items:
            try:
                saved = _store.upsert_nse(items)
                logger.debug("ipo_store: saved/updated %d records", saved)
            except Exception as e:
                logger.warning("ipo_store write failed: %s", e)

        # ── Step 4: fall back to store when NSE returned nothing ───────────
        if not items:
            try:
                store_items = _store.get_active()
                if store_items:
                    logger.info("ipo calendar: NSE unavailable, serving %d items from store",
                                len(store_items))
                    items = [
                        {
                            "symbol":      r["symbol"],
                            "companyName": r["companyName"],
                            "series":      r["series"],
                            "isSme":       r["isSme"],
                            "isReit":      r["isReit"],
                            "openDate":    r["openDate"],
                            "closeDate":   r["closeDate"],
                            "priceLow":    r["priceLow"],
                            "priceHigh":   r["priceHigh"],
                            "lotSize":     r["lotSize"],
                            "issueSizeCr": r["issueSizeCr"],
                            "status":      "open" if (r.get("openDate") or "9") <= datetime.utcnow().date().isoformat() else "upcoming",
                            "fromGmpOnly": r["fromGmpOnly"],
                            "fromCache":   True,
                        }
                        for r in store_items
                    ]
            except Exception as e:
                logger.warning("ipo_store read failed: %s", e)

        if not items:
            # Also check for manually added IPOs
            try:
                manual = _store.get_active()
                if manual:
                    items = manual
            except Exception:
                pass

        if not items:
            return {"available": False, "message": "No IPO data available right now.",
                    "open": [], "upcoming": [], "listed": []}

        # Enrich OPEN issues with subscription multiples concurrently.
        open_items = [it for it in items if it["status"] == "open"]
        upcoming   = [it for it in items if it["status"] == "upcoming"]
        if open_items and not any(it.get("fromCache") for it in open_items):
            details = await asyncio.gather(
                *[self._fetch_detail(it["symbol"]) for it in open_items],
                return_exceptions=True,
            )
            for it, det in zip(open_items, details):
                if isinstance(det, dict):
                    it["subscription"] = _summarise_subscription(det)
                else:
                    it["subscription"] = {"qib": None, "nii": None, "retail": None, "total": None}

        # Tag every issue (open + upcoming) with live GMP data.
        # GMP is NOT stored in the DB — it changes hourly and ipowatch
        # already caches it for 10 min. We always merge it fresh here.
        for it in items:
            match = gmp_service.find_gmp(gmp_table, it["companyName"], it["symbol"])
            if match:
                it["gmp"] = {
                    "premium":     match.get("gmp"),
                    "estListing":  match.get("estListing"),
                    "estGainPct":  match.get("estGainPct"),
                    "lastUpdated": match.get("lastUpdated"),
                    "matchedName": match.get("name"),
                }
            else:
                it["gmp"] = None

        # Sort: open by closeDate ascending (closing soonest first), upcoming
        # by openDate ascending (next to launch first).
        open_items.sort(key=lambda x: x.get("closeDate") or "9999")
        upcoming.sort(key=lambda x: x.get("openDate") or "9999")

        # ── Step 5: recently listed (from persistent store) ────────────────
        try:
            listed = _store.get_listed(limit=20)
            # Attach GMP for listed too (ipowatch shows closed status briefly)
            for it in listed:
                match = gmp_service.find_gmp(gmp_table, it["companyName"], it["symbol"])
                it["gmp"] = {
                    "premium":     match.get("gmp"),
                    "estListing":  match.get("estListing"),
                    "estGainPct":  match.get("estGainPct"),
                    "lastUpdated": match.get("lastUpdated"),
                    "matchedName": match.get("name"),
                } if match else None
        except Exception as e:
            logger.warning("ipo_store listed read failed: %s", e)
            listed = []

        result = {
            "available": True,
            "open":      open_items,
            "upcoming":  upcoming,
            "listed":    listed,
            "fetchedAt": datetime.utcnow().isoformat() + "Z",
            "gmpSource": {
                "url":       (gmp_table or {}).get("sourceUrl"),
                "fetchedAt": (gmp_table or {}).get("fetchedAt"),
                "note":      "GMP is live from ipowatch.in (refreshed every 10 min). "
                             "It changes intra-day and drops to zero on listing day.",
            },
        }
        _RESULT_CACHE["result"] = (_time.monotonic(), result)
        return result

    async def _fetch_detail(self, symbol: str) -> Optional[dict]:
        from urllib.parse import quote
        return await self._nse.fetch_nse(
            f"/api/ipo-detail?symbol={quote(symbol, safe='')}",
            f"ipo-detail-{symbol}",
            ttl=OPEN_TTL_SEC,
        )
