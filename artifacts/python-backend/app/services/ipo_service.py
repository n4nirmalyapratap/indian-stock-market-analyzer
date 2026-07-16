"""IPO Center data service.

Architecture (rebuilt for speed + consistency):

  ┌ background ────────────────────────────────────────────────────────────┐
  │ refresh()  — the ONLY network path. Runs from main._ipo_refresh_       │
  │ scheduler every few minutes (and admin force-refresh):                 │
  │   NSE /api/all-upcoming-issues  +  multi-source GMP scrape (parallel)  │
  │   → normalise → upsert into the SQLite ipo_store                       │
  │   → NSE /api/ipo-detail per OPEN issue → persist subscription          │
  │   → fuzzy-match GMP per stored IPO → persist gmp payload               │
  │   → rebuild the in-memory response snapshot from the store             │
  └────────────────────────────────────────────────────────────────────────┘
  ┌ request path ──────────────────────────────────────────────────────────┐
  │ get_calendar() — never touches the network. Serves the in-memory       │
  │ snapshot (µs); if stale, serves it anyway and kicks a background       │
  │ refresh (stale-while-revalidate). On a cold process it assembles       │
  │ straight from SQLite (ms). Only a brand-new instance with an empty     │
  │ store briefly waits (≤ _COLD_WAIT_SEC) for the first refresh.          │
  └────────────────────────────────────────────────────────────────────────┘

Because serving is store-backed, an NSE block or scraper outage degrades to
"data a few minutes old" instead of empty/flickering lists, and the open ⇄
upcoming ⇄ listed buckets are recomputed from dates on every assembly so
day-boundary transitions happen even between refreshes.

Sources:
  * NSE  /api/all-upcoming-issues?category=ipo  → Open + Forthcoming list
  * NSE  /api/ipo-detail?symbol=XXX             → live subscription multiples
  * gmp_service (ipowatch / investorgain / niftytrader) → GMP + SME coverage
"""
from __future__ import annotations

import asyncio
import logging
import re
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .nse_service import NseService
from . import gmp_service

logger = logging.getLogger("ipo")

_IST = timezone(timedelta(hours=5, minutes=30))

# Snapshot staleness at which a request triggers a background refresh. The
# scheduler normally refreshes first (5 min while the market is open); this
# is the self-healing backstop if the scheduler ever dies.
SNAPSHOT_TTL_SEC   = 10 * 60
# Never start refreshes closer together than this (protects NSE + scrapers
# from thundering herds when the feeds are down and the store is empty).
_MIN_REFRESH_GAP   = 60
# How long a cold, empty instance waits for the first refresh before giving
# the visitor a "warming up" response.
_COLD_WAIT_SEC     = 12
# Bounds on the network legs of one refresh, so a hanging NSE session can't
# stall the pipeline (the next tick simply retries).
_NSE_LIST_TIMEOUT  = 25
_NSE_DETAIL_TIMEOUT = 20
OPEN_TTL_SEC       = 5 * 60   # nse_service response-cache TTL for IPO calls

# ── module-level snapshot shared by every IpoService instance ───────────────
# NOTE: deliberately no asyncio.Lock here — a module-level Lock binds to the
# first event loop that touches it and breaks any later loop (tests, reloads).
# Single-flight is enforced by the _refresh_task dedup in _kick_refresh; a
# rare direct-refresh overlap (scheduler + admin) is harmless because every
# store write is an idempotent upsert.
_SNAPSHOT: dict = {}          # {"at": monotonic, "data": response_dict}
_GMP_META: dict = {}          # {"url":…, "fetchedAt":…, "sources": […]} from last refresh
_refresh_task: Optional[asyncio.Task] = None
_last_refresh_attempt: float = float("-inf")   # monotonic; -inf = never
_last_refresh_iso: Optional[str] = None


def invalidate_snapshot() -> None:
    """Drop the served snapshot so the next request re-assembles from the
    store. Called by admin routes after manual add/delete/mark-listed."""
    _SNAPSHOT.clear()


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


def _today_ist() -> str:
    return datetime.now(_IST).date().isoformat()


def _classify(item: dict) -> str:
    """NSE marks both Active and Forthcoming in the same feed. We split them
    into 'open' (currently accepting bids) vs 'upcoming' (bid window not yet
    started); serve-time recomputation from dates happens in _status_for."""
    status = (item.get("status") or "").lower()
    if status == "active":
        return "open"
    return "upcoming"


def _norm_name(name: str) -> str:
    """Lowercase + strip suffixes/punctuation so the same company spelled
    slightly differently across NSE and the GMP sources collapses to one
    key. Used to deduplicate sources when we merge them."""
    s = (name or "").lower()
    s = re.sub(r"\b(limited|ltd|pvt|private|co\.?|inc\.?|corp\.?|company)\b", "", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_DATE_RANGE_RE = re.compile(
    # Matches '21-25 May' OR '21 May-25 May' OR '21 May - 25 May'
    r"(\d{1,2})\s*(?:([A-Za-z]+))?\s*[-–to]+\s*(\d{1,2})\s*([A-Za-z]+)",
    re.I,
)


def _parse_gmp_date_range(s: str) -> tuple[Optional[str], Optional[str]]:
    """ipowatch.in dates come as `21-25 May` or `26 May - 29 May` style
    strings. We pull out the open / close ISO dates best-effort.

    Year-less strings get the year that lands the open date within ±6
    months of today (IST) so December windows parsed in January don't jump
    a year. Returns (openIso, closeIso); either may be None."""
    if not s or not isinstance(s, str):
        return (None, None)
    m = _DATE_RANGE_RE.search(s)
    if not m:
        return (None, None)
    d1, m1, d2, m2 = m.groups()
    months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
              "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    mn1 = months.get((m1 or m2 or "").lower()[:3])
    mn2 = months.get((m2 or "").lower()[:3])
    if not mn1 or not mn2:
        return (None, None)
    from datetime import date as _date  # noqa: PLC0415
    today = datetime.now(_IST).date()
    try:
        d_open = _date(today.year, mn1, int(d1))
        if (d_open - today).days > 183:
            d_open = d_open.replace(year=d_open.year - 1)
        elif (today - d_open).days > 183:
            d_open = d_open.replace(year=d_open.year + 1)
        d_close = _date(d_open.year, mn2, int(d2))
        if d_close < d_open:  # '28 Dec - 2 Jan' rolls into the next year
            d_close = d_close.replace(year=d_close.year + 1)
        return (d_open.isoformat(), d_close.isoformat())
    except (ValueError, TypeError):
        return (None, None)


def _synth_issue_from_gmp(row: dict) -> Optional[dict]:
    """Convert a GMP-table row into the same flat IpoIssue shape that
    `_normalise_issue` produces from NSE rows.

    Used for IPOs the GMP sources track but NSE doesn't return — the bulk
    of SME issues (BSE SME entirely, and many NSE EMERGE issues missing
    from the public upcoming-issues feed). Subscription multiples are
    absent because only NSE exposes them; the UI handles that gracefully.

    Returns None when the row lacks the bare minimum (name + status) to
    be useful."""
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
    slug = re.sub(r"[^A-Z0-9]", "", name.upper())[:24] or name.upper()[:24]
    # Price band: GMP sources only store the cap price, treat it as priceHigh.
    price_high = row.get("priceBand")
    # Prefer explicit ISO dates (investorgain / niftytrader ship them);
    # fall back to parsing ipowatch's '21-25 May' range strings.
    open_iso  = row.get("openDate")
    close_iso = row.get("closeDate")
    if not open_iso and not close_iso:
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
        "lotSize":      _to_int(row.get("lotSize")),
        "issueSizeCr":  None,
        "issueShares":  None,
        "status":       "open" if status == "open" else "upcoming",
        "rawStatus":    status,
        # Mark provenance so the UI can show a small "GMP source" hint
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


def _status_for(open_iso: Optional[str], close_iso: Optional[str],
                raw_status: Optional[str], today_iso: str) -> str:
    """'open' / 'upcoming' / 'closed' recomputed from the bid window at
    serve time, so issues flip buckets on the right day even when no
    refresh has run since midnight. Falls back to the feed's own status
    when dates are missing."""
    if open_iso:
        if today_iso < open_iso:
            return "upcoming"
        if close_iso is None or today_iso <= close_iso:
            return "open"
        return "closed"
    rs = (raw_status or "").lower()
    if rs in ("active", "open"):
        return "open"
    if rs == "closed":
        return "closed"
    return "upcoming"


def _issue_from_store_row(r: dict) -> dict:
    """Store row (camelCase, JSON columns already parsed) → response issue."""
    return {
        "symbol":       r.get("symbol"),
        "companyName":  r.get("companyName"),
        "series":       r.get("series") or "EQ",
        "isSme":        bool(r.get("isSme")),
        "isReit":       bool(r.get("isReit")),
        "openDate":     r.get("openDate"),
        "closeDate":    r.get("closeDate"),
        "priceLow":     r.get("priceLow"),
        "priceHigh":    r.get("priceHigh"),
        "lotSize":      r.get("lotSize"),
        "issueSizeCr":  r.get("issueSizeCr"),
        "issueShares":  r.get("issueShares"),
        "rawStatus":    r.get("rawStatus"),
        "fromGmpOnly":  bool(r.get("fromGmpOnly")),
        "gmp":          r.get("gmp") or None,
    }


class IpoService:
    """Store-backed IPO calendar. `get_calendar` is the read path (no
    network); `refresh` is the write path (scheduler/admin only)."""

    def __init__(self, nse: NseService):
        self._nse = nse

    # ── read path ───────────────────────────────────────────────────────────
    async def get_calendar(self) -> dict:
        snap = _SNAPSHOT.get("data")
        if snap is not None:
            if _time.monotonic() - _SNAPSHOT.get("at", 0) >= SNAPSHOT_TTL_SEC:
                self._kick_refresh()  # stale-while-revalidate
            return snap

        # Cold process: assemble from the persistent store (local SQLite, ms).
        try:
            data = self._assemble_from_store()
        except Exception as e:
            logger.warning("ipo store assembly failed: %s", e)
            data = None
        task = self._kick_refresh()
        if data and (data["open"] or data["upcoming"] or data["listed"]):
            _SNAPSHOT.update({"at": _time.monotonic(), "data": data})
            return data

        # Brand-new instance with an empty store — give the first refresh a
        # bounded chance to finish so the very first visitor still sees data.
        if task is not None and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=_COLD_WAIT_SEC)
            except Exception:
                pass
        snap = _SNAPSHOT.get("data")
        if snap is not None:
            return snap
        return {
            "available": False,
            "message":   "IPO data is warming up — try again in a few seconds.",
            "open": [], "upcoming": [], "listed": [],
            "fetchedAt": datetime.utcnow().isoformat() + "Z",
            "gmpSource": {"url": gmp_service.GMP_URL, "fetchedAt": None, "note": None},
        }

    def _kick_refresh(self) -> Optional[asyncio.Task]:
        """Start a background refresh unless one is running or one ran
        moments ago. Returns the in-flight task when there is one."""
        global _refresh_task, _last_refresh_attempt
        if _refresh_task is not None and not _refresh_task.done():
            return _refresh_task
        if _time.monotonic() - _last_refresh_attempt < _MIN_REFRESH_GAP:
            return _refresh_task
        _last_refresh_attempt = _time.monotonic()
        _refresh_task = asyncio.create_task(self.refresh())
        _refresh_task.add_done_callback(_log_refresh_outcome)
        return _refresh_task

    # ── write path (network) ────────────────────────────────────────────────
    async def refresh(self) -> bool:
        """Pull every source, persist into the store, rebuild the snapshot.
        Safe to call from the scheduler, admin routes and stale-triggered
        requests concurrently (request-path calls are deduped through
        _kick_refresh; store writes are idempotent upserts). Returns True
        when at least one source contributed fresh data."""
        global _last_refresh_attempt, _last_refresh_iso
        _last_refresh_attempt = _time.monotonic()
        from . import ipo_store as _store  # noqa: PLC0415

        raw_main, gmp_table = await asyncio.gather(
            asyncio.wait_for(
                self._nse.fetch_nse(
                    "/api/all-upcoming-issues?category=ipo",
                    "ipo-upcoming-issues",
                    ttl=OPEN_TTL_SEC,
                ),
                timeout=_NSE_LIST_TIMEOUT,
            ),
            gmp_service.fetch_gmp_table(),
            return_exceptions=True,
        )
        main_ok = isinstance(raw_main, list)
        if not main_ok and isinstance(raw_main, Exception):
            logger.warning("ipo refresh: NSE list failed: %s", str(raw_main)[:120])
        if isinstance(gmp_table, Exception):
            logger.warning("ipo refresh: GMP fetch failed: %s", str(gmp_table)[:120])
            gmp_table = {"byName": {}, "fetchedAt": None, "sourceUrl": gmp_service.GMP_URL}

        # ── normalise NSE rows (the spine — richer data) ────────────────────
        seen_names: set[str] = set()
        nse_items: list[dict] = []
        if main_ok:
            for it in raw_main:
                if not isinstance(it, dict) or not it.get("symbol"):
                    continue
                norm = _normalise_issue(it)
                nse_items.append(norm)
                seen_names.add(_norm_name(norm.get("companyName") or ""))

        # ── synth rows for GMP-tracked issues NSE doesn't list (SME) ────────
        synth_items: list[dict] = []
        gmp_by_name = (gmp_table or {}).get("byName") or {}
        for _key, row in gmp_by_name.items():
            company = (row.get("name") or "").strip()
            if not company or _norm_name(company) in seen_names:
                continue
            synth = _synth_issue_from_gmp(row)
            if synth is None:
                continue
            synth_items.append(synth)
            seen_names.add(_norm_name(company))

        items = nse_items + synth_items
        if items:
            try:
                saved = _store.upsert_nse(items)
                logger.debug("ipo_store: saved/updated %d records", saved)
            except Exception as e:
                logger.warning("ipo_store write failed: %s", e)

        # ── live subscription multiples for OPEN NSE-tracked issues ─────────
        today = _today_ist()
        open_syms = [
            it["symbol"] for it in nse_items
            if _status_for(it.get("openDate"), it.get("closeDate"),
                           it.get("rawStatus"), today) == "open"
        ]
        if open_syms:
            try:
                details = await asyncio.wait_for(
                    asyncio.gather(
                        *[self._fetch_detail(s) for s in open_syms],
                        return_exceptions=True,
                    ),
                    timeout=_NSE_DETAIL_TIMEOUT,
                )
                subs = {
                    sym: _summarise_subscription(det)
                    for sym, det in zip(open_syms, details)
                    if isinstance(det, dict)
                }
                if subs:
                    _store.set_subscriptions(subs)
            except asyncio.TimeoutError:
                logger.warning("ipo refresh: subscription detail fetch timed out")
            except Exception as e:
                logger.warning("ipo refresh: subscription fetch failed: %s", e)

        # ── persist matched GMP per stored IPO (last-known-good) ────────────
        if gmp_by_name:
            try:
                gmps: dict[str, dict] = {}
                for r in _store.get_active() + _store.get_listed(limit=20):
                    match = gmp_service.find_gmp(gmp_table, r["companyName"], r["symbol"])
                    if match and match.get("gmp") is not None:
                        gmps[r["symbol"]] = {
                            "premium":     match.get("gmp"),
                            "estListing":  match.get("estListing"),
                            "estGainPct":  match.get("estGainPct"),
                            "lastUpdated": match.get("lastUpdated"),
                            "matchedName": match.get("name"),
                            "source":      match.get("source"),
                        }
                if gmps:
                    _store.set_gmps(gmps)
                _GMP_META.update({
                    "url":       (gmp_table or {}).get("sourceUrl"),
                    "fetchedAt": (gmp_table or {}).get("fetchedAt"),
                    "sources":   (gmp_table or {}).get("sources") or [],
                })
            except Exception as e:
                logger.warning("ipo refresh: gmp persist failed: %s", e)

        # ── rebuild the served snapshot from the store ──────────────────────
        _last_refresh_iso = datetime.utcnow().isoformat() + "Z"
        try:
            data = self._assemble_from_store()
            _SNAPSHOT.update({"at": _time.monotonic(), "data": data})
        except Exception as e:
            logger.warning("ipo snapshot rebuild failed: %s", e)
        return bool(items)

    # ── assembly (store → response, no network) ─────────────────────────────
    def _assemble_from_store(self) -> dict:
        from . import ipo_store as _store  # noqa: PLC0415

        rows   = _store.get_active()
        listed = _store.get_listed(limit=20)

        # Dedup by normalised company name: an IPO can exist both as a real
        # NSE row and as an older GMP-synth slug row — prefer the real one.
        by_name: dict[str, dict] = {}
        for r in rows:
            key = _norm_name(r.get("companyName") or "") or r.get("symbol", "")
            cur = by_name.get(key)
            if cur is None or (cur.get("fromGmpOnly") and not r.get("fromGmpOnly")):
                by_name[key] = r

        today = _today_ist()
        open_items: list[dict] = []
        upcoming:   list[dict] = []
        for r in by_name.values():
            status = _status_for(r.get("openDate"), r.get("closeDate"),
                                 r.get("rawStatus"), today)
            if status == "closed":
                continue  # bid window over, listing pending — neither tab fits
            it = _issue_from_store_row(r)
            it["status"] = status
            if status == "open":
                if isinstance(r.get("subscription"), dict):
                    it["subscription"] = r["subscription"]
                open_items.append(it)
            else:
                upcoming.append(it)

        # Sort: open by closeDate ascending (closing soonest first), upcoming
        # by openDate ascending (next to launch first).
        open_items.sort(key=lambda x: x.get("closeDate") or "9999")
        upcoming.sort(key=lambda x: x.get("openDate") or "9999")

        listed_out: list[dict] = []
        for r in listed:
            it = _issue_from_store_row(r)
            it["status"] = "listed"
            it["source"] = r.get("source") or "nse"
            listed_out.append(it)

        gmp_fetched = _GMP_META.get("fetchedAt")
        if not gmp_fetched:
            # Cold process: best per-IPO timestamp we persisted before restart.
            stamps = [r.get("gmpUpdatedAt") for r in rows + listed if r.get("gmpUpdatedAt")]
            gmp_fetched = max(stamps) if stamps else None

        available = bool(open_items or upcoming or listed_out)
        return {
            "available": available,
            **({} if available else
               {"message": "No IPO data available right now."}),
            "open":      open_items,
            "upcoming":  upcoming,
            "listed":    listed_out,
            "fetchedAt": _last_refresh_iso or datetime.utcnow().isoformat() + "Z",
            "gmpSource": {
                "url":       _GMP_META.get("url") or gmp_service.GMP_URL,
                "fetchedAt": gmp_fetched,
                "note":      "GMP is merged from ipowatch.in, investorgain.com and "
                             "niftytrader.in (first source that tracks each issue wins) "
                             "and refreshed every few minutes. It changes intra-day and "
                             "drops to zero on listing day.",
            },
        }

    async def _fetch_detail(self, symbol: str) -> Optional[dict]:
        from urllib.parse import quote
        return await self._nse.fetch_nse(
            f"/api/ipo-detail?symbol={quote(symbol, safe='')}",
            f"ipo-detail-{symbol}",
            ttl=OPEN_TTL_SEC,
        )


def _log_refresh_outcome(task: asyncio.Task) -> None:
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    if exc:
        logger.warning("ipo background refresh failed: %s", exc)
