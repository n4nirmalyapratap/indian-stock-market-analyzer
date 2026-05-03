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

logger = logging.getLogger("ipo")

# How many minutes the response stays cached before we re-hit NSE.
OPEN_TTL_SEC     = 5 * 60      # subscription numbers refresh ~every 5 min
UPCOMING_TTL_SEC = 30 * 60     # forthcoming list rarely changes intra-day


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
    """Thin orchestration on top of NseService — pure read-through with TTL
    cache so we never hammer NSE more than once per cache window."""

    def __init__(self, nse: NseService):
        self._nse = nse

    async def get_calendar(self) -> dict:
        """Fetch the combined open+upcoming list, then enrich every OPEN
        issue with its live subscription multiples (parallel fetches)."""
        raw = await self._nse.fetch_nse(
            "/api/all-upcoming-issues?category=ipo",
            "ipo-upcoming-issues",
            ttl=OPEN_TTL_SEC,
        )
        if not isinstance(raw, list):
            return {"available": False, "message": "NSE IPO feed unavailable.", "open": [], "upcoming": []}

        items = [_normalise_issue(it) for it in raw if isinstance(it, dict) and it.get("symbol")]

        # Enrich OPEN issues with subscription multiples concurrently.
        open_items = [it for it in items if it["status"] == "open"]
        upcoming   = [it for it in items if it["status"] == "upcoming"]
        if open_items:
            details = await asyncio.gather(
                *[self._fetch_detail(it["symbol"]) for it in open_items],
                return_exceptions=True,
            )
            for it, det in zip(open_items, details):
                if isinstance(det, dict):
                    it["subscription"] = _summarise_subscription(det)
                else:
                    it["subscription"] = {"qib": None, "nii": None, "retail": None, "total": None}

        # Sort: open by closeDate ascending (closing soonest first), upcoming
        # by openDate ascending (next to launch first).
        open_items.sort(key=lambda x: x.get("closeDate") or "9999")
        upcoming.sort(key=lambda x: x.get("openDate") or "9999")

        return {
            "available": True,
            "open":      open_items,
            "upcoming":  upcoming,
            "fetchedAt": datetime.utcnow().isoformat() + "Z",
        }

    async def _fetch_detail(self, symbol: str) -> Optional[dict]:
        from urllib.parse import quote
        return await self._nse.fetch_nse(
            f"/api/ipo-detail?symbol={quote(symbol, safe='')}",
            f"ipo-detail-{symbol}",
            ttl=OPEN_TTL_SEC,
        )
