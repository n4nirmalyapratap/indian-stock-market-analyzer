"""Grey Market Premium (GMP) scraper.

Pulls the live GMP table from ipowatch.in (the only source we tested that
ships the data in static HTML — investorgain and chittorgarh both render
client-side and would need a headless browser).

The first table on the page (`Current/Upcoming IPO GMP`) has columns:
    IPO Name | IPO GMP | Trend | Price Band | Est. Listing | Date | Type | Status | Last Updated

We parse it once every CACHE_TTL seconds and expose a dict keyed by a
normalised company name so `IpoService` can fuzzy-match NSE rows against it.
"""
from __future__ import annotations

import logging
import re
import time
from html.parser import HTMLParser
from typing import Optional

import httpx

logger = logging.getLogger("gmp")

GMP_URL    = "https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/"
CACHE_TTL  = 10 * 60   # GMP shifts intra-day; 10 min is a sane refresh
HEADERS    = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept":     "text/html,application/xhtml+xml",
}

_cache: dict[str, tuple[float, dict]] = {}


# ── HTML table parsing ──────────────────────────────────────────────────────
class _TableParser(HTMLParser):
    """Minimal HTML→rows parser for the first <table> on the page."""

    def __init__(self):
        super().__init__()
        self.in_table   = False
        self.depth      = 0          # how many tables deep we are
        self.in_row     = False
        self.in_cell    = False
        self.cell_buf:  list[str] = []
        self.row_buf:   list[str] = []
        self.rows:      list[list[str]] = []
        self.done       = False      # stop after first table closes

    def handle_starttag(self, tag, attrs):
        if self.done:
            return
        if tag == "table":
            self.depth += 1
            self.in_table = True
        elif self.in_table:
            if tag == "tr":
                self.in_row = True
                self.row_buf = []
            elif tag in ("td", "th"):
                self.in_cell = True
                self.cell_buf = []

    def handle_endtag(self, tag):
        if self.done:
            return
        if tag in ("td", "th") and self.in_cell:
            self.in_cell = False
            self.row_buf.append(" ".join("".join(self.cell_buf).split()))
        elif tag == "tr" and self.in_row:
            self.in_row = False
            if self.row_buf:
                self.rows.append(self.row_buf)
        elif tag == "table":
            self.depth -= 1
            if self.depth == 0:
                self.in_table = False
                self.done = True

    def handle_data(self, data):
        if self.in_cell:
            self.cell_buf.append(data)


# ── parsing helpers ─────────────────────────────────────────────────────────
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _to_float(s: str) -> Optional[float]:
    if not s:
        return None
    m = _NUM_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _normalise_name(name: str) -> str:
    """Lowercase, strip suffixes/punctuation/extra-whitespace so two slightly
    different spellings of the same company collapse to the same key.

    'Bagmane Prime Office REIT' → 'bagmane prime office reit'
    'Bagmane REIT'              → 'bagmane reit'
    'Onemi Technology Solutions Limited' → 'onemi technology solutions'
    """
    s = (name or "").lower()
    # drop common suffixes
    s = re.sub(r"\b(limited|ltd|pvt|private|co\.?|inc\.?|corp\.?|company)\b", "", s)
    # drop punctuation
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _name_tokens(name: str) -> set[str]:
    """Significant tokens for fuzzy matching — drop short stopwords like
    'the', 'of', 'and'."""
    stop = {"the", "of", "and", "an", "a", "for"}
    return {t for t in _normalise_name(name).split() if len(t) > 2 and t not in stop}


def _parse_est_listing(s: str) -> tuple[Optional[float], Optional[float]]:
    """'₹195 (23.42%)' → (195.0, 23.42). '₹- (0.00%)' → (None, 0.0)."""
    if not s:
        return (None, None)
    nums = _NUM_RE.findall(s)
    # First number is the price (or None if cell shows '-'), second is %.
    has_price = "₹-" not in s and "-" != s.replace("(0.00%)", "").strip()
    price: Optional[float] = None
    pct:   Optional[float] = None
    if has_price and nums:
        try: price = float(nums[0])
        except ValueError: pass
    # Percentage is always the last number followed by '%' in the cell.
    pct_match = re.search(r"(-?\d+(?:\.\d+)?)\s*%", s)
    if pct_match:
        try: pct = float(pct_match.group(1))
        except ValueError: pass
    return (price, pct)


def _parse_row(headers: list[str], row: list[str]) -> Optional[dict]:
    """Map a raw row of cells into a structured dict, keyed off the header
    row's column names so column-order changes don't silently mis-parse."""
    if len(row) < len(headers):
        return None
    cells = dict(zip(headers, row))
    name = cells.get("IPO Name", "").strip()
    if not name:
        return None
    gmp = _to_float(cells.get("IPO GMP", ""))
    price = _to_float(cells.get("Price Band", "") or cells.get("Price", ""))
    est_price, est_pct = _parse_est_listing(cells.get("Est. Listing", ""))
    return {
        "name":        name,
        "gmp":         gmp,                                    # ₹ premium
        "priceBand":   price,                                  # cap price (₹)
        "estListing":  est_price,                              # ₹
        "estGainPct":  est_pct,                                # %
        "type":        (cells.get("Type") or "").strip(),      # Mainboard / NSE SME / BSE SME
        "status":      (cells.get("Status") or "").strip(),    # Open / Upcoming / Closed
        "date":        (cells.get("Date") or "").strip(),      # e.g. "21-25 May"
        "lastUpdated": (cells.get("Last Updated") or "").strip(),
    }


# ── public API ──────────────────────────────────────────────────────────────
async def fetch_gmp_table() -> dict:
    """Fetch + parse the GMP page. Returns a dict:
        { 'byName': { normalised_name: row_dict, ... },
          'fetchedAt': '...',
          'sourceUrl': GMP_URL }
    Cached in-process for CACHE_TTL seconds. On any failure returns an
    empty `byName` map so the caller can degrade gracefully (IPO Center
    still renders, just without GMP badges)."""
    now = time.time()
    cached = _cache.get("table")
    if cached and now - cached[0] < CACHE_TTL:
        return cached[1]

    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            resp = await client.get(GMP_URL, headers=HEADERS)
        if resp.status_code != 200:
            logger.warning("ipowatch GMP returned %s", resp.status_code)
            return {"byName": {}, "fetchedAt": None, "sourceUrl": GMP_URL}

        parser = _TableParser()
        parser.feed(resp.text)
        rows = parser.rows
        if len(rows) < 2:
            return {"byName": {}, "fetchedAt": None, "sourceUrl": GMP_URL}

        headers = rows[0]
        by_name: dict[str, dict] = {}
        for row in rows[1:]:
            parsed = _parse_row(headers, row)
            if parsed:
                by_name[_normalise_name(parsed["name"])] = parsed

        out = {
            "byName":    by_name,
            "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "sourceUrl": GMP_URL,
        }
        _cache["table"] = (now, out)
        return out
    except Exception as e:
        logger.warning("GMP fetch failed: %s", str(e)[:160])
        return {"byName": {}, "fetchedAt": None, "sourceUrl": GMP_URL}


def find_gmp(table: dict, company_name: str, symbol: str = "") -> Optional[dict]:
    """Best-effort fuzzy match of an NSE company name (or its symbol) against
    the GMP table. Strategy:
      1. exact normalised-name match
      2. one normalised name is a substring of the other
      3. ≥2 significant tokens overlap (≥1 if either side is a single word)"""
    by_name = (table or {}).get("byName") or {}
    if not by_name:
        return None
    target = _normalise_name(company_name)
    if target in by_name:
        return by_name[target]
    # substring either direction
    for key, row in by_name.items():
        if key and (key in target or target in key):
            return row
    # token overlap
    target_tokens = _name_tokens(company_name) | _name_tokens(symbol)
    if not target_tokens:
        return None
    best: tuple[int, Optional[dict]] = (0, None)
    for key, row in by_name.items():
        cand_tokens = _name_tokens(row["name"])
        overlap = len(target_tokens & cand_tokens)
        # Require ≥2 overlapping tokens, OR ≥1 if either side is a 1-word name.
        threshold = 1 if (len(target_tokens) <= 1 or len(cand_tokens) <= 1) else 2
        if overlap >= threshold and overlap > best[0]:
            best = (overlap, row)
    return best[1]
