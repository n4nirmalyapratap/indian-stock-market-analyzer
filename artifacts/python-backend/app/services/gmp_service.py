"""Grey Market Premium (GMP) scraper — multi-source with merge + fallback.

GMP is the single most-watched number on the IPO page, so we no longer bet
on one site. Three independent sources, fetched concurrently and merged in
priority order (first source that knows a company wins; later sources only
fill companies/fields the earlier ones missed):

  1. ipowatch.in       — static HTML table (proven, richest Type/Status cols)
  2. investorgain.com  — JSON API (webnodejs.investorgain.com report 331);
                         ships clean ISO open/close dates + lot size
  3. niftytrader.in    — server-rendered HTML table (full dates with year)

All HTML sources go through the same generic table extractor with
header-keyword column mapping, so a renamed/reordered column degrades to
"field missing" instead of silent mis-parses.

Failure model: a source that errors or parses zero rows is skipped; if every
source fails we serve the last successfully merged table (kept in-process,
no TTL) so GMP never vanishes from the UI mid-outage. Per-IPO persistence
across restarts lives in ipo_store (IpoService writes matched GMP there).
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Optional

import httpx

logger = logging.getLogger("gmp")

IPOWATCH_URL    = "https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/"
NIFTYTRADER_URL = "https://www.niftytrader.in/ipo/gmp"
# investorgain URL is date-dependent — see _investorgain_url().

GMP_URL    = IPOWATCH_URL   # kept for backwards-compat (route/meta references)
CACHE_TTL  = 10 * 60        # GMP shifts intra-day; 10 min is a sane refresh
HEADERS    = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept":     "text/html,application/xhtml+xml",
}

_IST = timezone(timedelta(hours=5, minutes=30))

_cache: dict[str, tuple[float, dict]] = {}
# Last successfully merged table (no TTL). Served when every source fails so
# a scrape outage degrades to "slightly stale GMP" instead of "no GMP".
_last_good: Optional[dict] = None


# ── HTML table parsing ──────────────────────────────────────────────────────
class _TableParser(HTMLParser):
    """Minimal HTML→rows parser. Collects every top-level <table> on the
    page (up to MAX_TABLES) so callers can pick the one whose header row
    looks like a GMP table — promo/nav tables above the data don't break us."""

    MAX_TABLES = 8

    def __init__(self):
        super().__init__()
        self.depth      = 0          # how many tables deep we are
        self.in_row     = False
        self.in_cell    = False
        self.cell_buf:  list[str] = []
        self.row_buf:   list[str] = []
        self._cur:      list[list[str]] = []   # rows of the table being read
        self.tables:    list[list[list[str]]] = []
        self.done       = False

    @property
    def rows(self) -> list[list[str]]:
        """Rows of the FIRST table on the page (legacy accessor)."""
        return self.tables[0] if self.tables else self._cur

    def handle_starttag(self, tag, attrs):
        if self.done:
            return
        if tag == "table":
            self.depth += 1
            if self.depth == 1:
                self._cur = []
        elif self.depth >= 1:
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
                self._cur.append(self.row_buf)
        elif tag == "table" and self.depth > 0:
            self.depth -= 1
            if self.depth == 0:
                if self._cur:
                    self.tables.append(self._cur)
                    self._cur = []
                if len(self.tables) >= self.MAX_TABLES:
                    self.done = True

    def handle_data(self, data):
        if self.in_cell:
            self.cell_buf.append(data)


# ── parsing helpers ─────────────────────────────────────────────────────────
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
_PCT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")
_TAG_RE = re.compile(r"<[^>]+>")


def _to_float(s) -> Optional[float]:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    m = _NUM_RE.search(str(s))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _strip_tags(s: str) -> str:
    return " ".join(_TAG_RE.sub(" ", s or "").split())


def _normalise_name(name: str) -> str:
    """Lowercase, strip suffixes/punctuation/extra-whitespace so two slightly
    different spellings of the same company collapse to the same key.

    'Bagmane Prime Office REIT' → 'bagmane prime office reit'
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


def _clean_company(name: str) -> str:
    """'IC Electricals IPO' → 'IC Electricals' (niftytrader suffixes rows)."""
    return re.sub(r"\s+ipo$", "", (name or "").strip(), flags=re.I).strip()


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
    pct_match = _PCT_RE.search(s)
    if pct_match:
        try: pct = float(pct_match.group(1))
        except ValueError: pass
    return (price, pct)


_FLEX_DATE_FMTS = ("%Y-%m-%d", "%d %b %Y", "%d-%b-%Y", "%d %B %Y", "%d-%b", "%d-%B", "%d %b")


def _parse_flex_date(s: str) -> Optional[str]:
    """Best-effort '03 Jul 2026' / '2026-07-03' / '3-Jul' → ISO date.
    Year-less dates get the year that lands them within ±6 months of today
    (IST) so a December row parsed in January doesn't jump a year."""
    s = (s or "").strip()
    if not s:
        return None
    for fmt in _FLEX_DATE_FMTS:
        try:
            d = datetime.strptime(s, fmt).date()
        except ValueError:
            continue
        if "%Y" not in fmt:
            today = datetime.now(_IST).date()
            d = d.replace(year=today.year)
            if (d - today).days > 183:
                d = d.replace(year=d.year - 1)
            elif (today - d).days > 183:
                d = d.replace(year=d.year + 1)
        return d.isoformat()
    return None


def _derive_status(open_iso: Optional[str], close_iso: Optional[str]) -> str:
    """Open/Upcoming/Closed from the bid window (IST). '' when undecidable."""
    if not open_iso:
        return ""
    today = datetime.now(_IST).date().isoformat()
    if today < open_iso:
        return "Upcoming"
    if close_iso and today > close_iso:
        return "Closed"
    return "Open"


# ── generic header-mapped table → rows ──────────────────────────────────────
# Column detection by header keywords, so renames/reorders degrade gracefully.
def _map_headers(cells: list[str]) -> Optional[dict[str, int]]:
    m: dict[str, int] = {}
    for i, raw in enumerate(cells):
        h = (raw or "").lower()
        if not h:
            continue
        if "gmp" in h or "premium" in h:
            m.setdefault("gmp", i)
        elif "listing" in h and ("est" in h or "gain" in h or "%" in h):
            m.setdefault("est", i)
        elif ("name" in h and "ipo" in h) or "company" in h or h in ("ipo", "ipo name"):
            m.setdefault("name", i)
        elif "price" in h or "band" in h:
            m.setdefault("price", i)
        elif "lot" in h:
            m.setdefault("lot", i)
        elif "updated" in h:
            m.setdefault("updated", i)
        elif "type" in h or "board" in h:
            m.setdefault("type", i)
        elif "status" in h:
            m.setdefault("status", i)
        elif h.startswith("open"):
            m.setdefault("open", i)
        elif h.startswith("close"):
            m.setdefault("close", i)
        elif "date" in h:
            m.setdefault("date", i)
    if "name" not in m or "gmp" not in m:
        return None
    return m


def _pick_gmp_table(tables: list[list[list[str]]]) -> Optional[tuple[dict[str, int], list[list[str]]]]:
    """First table whose header row maps to (name + gmp) columns."""
    for rows in tables:
        if len(rows) < 2:
            continue
        m = _map_headers(rows[0])
        if m:
            return (m, rows[1:])
    return None


def _cell(row: list[str], idx: Optional[int]) -> str:
    if idx is None or idx >= len(row):
        return ""
    return row[idx]


def _row_from_cells(m: dict[str, int], row: list[str], source: str) -> Optional[dict]:
    """One mapped table row → the common GMP row shape (None if unusable)."""
    name = _clean_company(_cell(row, m.get("name")))
    if not name or len(name) < 3:
        return None
    price_cell = _cell(row, m.get("price"))
    # Guard against size-like cells ("₹48 Cr") landing in a price column.
    price = None if re.search(r"\bcr\b", price_cell, re.I) else _to_float(price_cell)
    est_price, est_pct = _parse_est_listing(_cell(row, m.get("est")))
    open_iso  = _parse_flex_date(_cell(row, m.get("open")))
    close_iso = _parse_flex_date(_cell(row, m.get("close")))
    status = (_cell(row, m.get("status")) or "").strip()
    if status.lower() in ("live", "current"):
        status = "Open"
    if not status:
        status = _derive_status(open_iso, close_iso)
    lot = _to_float(_cell(row, m.get("lot")))
    return {
        "name":        name,
        "gmp":         _to_float(_cell(row, m.get("gmp"))),
        "priceBand":   price,
        "estListing":  est_price,
        "estGainPct":  est_pct,
        "type":        (_cell(row, m.get("type")) or "").strip(),
        "status":      status,
        "date":        (_cell(row, m.get("date")) or "").strip(),
        "openDate":    open_iso,
        "closeDate":   close_iso,
        "lotSize":     int(lot) if lot else None,
        "lastUpdated": (_cell(row, m.get("updated")) or "").strip(),
        "source":      source,
    }


def _parse_row(headers: list[str], row: list[str]) -> Optional[dict]:
    """Map a raw row of cells into a structured dict, keyed off the header
    row's column names so column-order changes don't silently mis-parse."""
    if len(row) < len(headers):
        return None
    m = _map_headers(headers)
    if not m:
        return None
    return _row_from_cells(m, row, "ipowatch")


def _rows_from_html_table(html: str, source: str) -> list[dict]:
    parser = _TableParser()
    parser.feed(html)
    picked = _pick_gmp_table(parser.tables)
    if not picked:
        return []
    m, data_rows = picked
    out: list[dict] = []
    for row in data_rows:
        parsed = _row_from_cells(m, row, source)
        if parsed:
            out.append(parsed)
    return out


# ── per-source fetchers ─────────────────────────────────────────────────────
async def _fetch_ipowatch(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(IPOWATCH_URL, headers=HEADERS)
    if resp.status_code != 200:
        raise RuntimeError(f"http {resp.status_code}")
    return _rows_from_html_table(resp.text, "ipowatch")


async def _fetch_niftytrader(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(NIFTYTRADER_URL, headers=HEADERS)
    if resp.status_code != 200:
        raise RuntimeError(f"http {resp.status_code}")
    return _rows_from_html_table(resp.text, "niftytrader")


def _investorgain_url() -> str:
    """Report 331 = live IPO GMP. Path embeds month/year/financial-year."""
    now = datetime.now(_IST)
    fy_start = now.year if now.month >= 4 else now.year - 1
    fy = f"{fy_start}-{str(fy_start + 1)[-2:]}"
    return (f"https://webnodejs.investorgain.com/cloud/report/data-read/"
            f"331/1/{now.month}/{now.year}/{fy}/0/all")


async def _fetch_investorgain(client: httpx.AsyncClient) -> list[dict]:
    headers = {**HEADERS, "Accept": "application/json",
               "Referer": "https://www.investorgain.com/"}
    resp = await client.get(_investorgain_url(), headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"http {resp.status_code}")
    payload = resp.json()
    rows = (payload or {}).get("reportTableData") or []
    out: list[dict] = []
    for el in rows:
        if not isinstance(el, dict):
            continue
        name = _clean_company(el.get("~ipo_name") or _strip_tags(str(el.get("Name") or "")))
        if not name or len(name) < 3:
            continue
        gmp_txt = _strip_tags(str(el.get("GMP") or ""))
        gmp = _to_float(gmp_txt)
        pct = None
        pm = _PCT_RE.search(gmp_txt)
        if pm:
            try: pct = float(pm.group(1))
            except ValueError: pass
        if pct is None:
            pct = _to_float(el.get("~gmp_percent_calc"))
        price = _to_float(el.get("Price (₹)") or el.get("Price"))
        est = round(price + gmp, 2) if (price is not None and gmp is not None) else None
        open_iso  = _parse_flex_date(str(el.get("~Srt_Open") or ""))
        close_iso = _parse_flex_date(str(el.get("~Srt_Close") or ""))
        cat = str(el.get("~IPO_Category") or "")
        is_sme = "sme" in cat.lower() or "SME" in _strip_tags(str(el.get("Name") or ""))
        out.append({
            "name":        name,
            "gmp":         gmp,
            "priceBand":   price,
            "estListing":  est,
            "estGainPct":  pct,
            "type":        "SME" if is_sme else "Mainboard",
            "status":      _derive_status(open_iso, close_iso),
            "date":        "",
            "openDate":    open_iso,
            "closeDate":   close_iso,
            "lotSize":     (lambda v: int(v) if v else None)(_to_float(el.get("Lot"))),
            "lastUpdated": _strip_tags(str(el.get("Updated-On") or "")),
            "source":      "investorgain",
        })
    return out


# Priority order: first source that knows a company wins.
_SOURCES = (
    ("ipowatch",     IPOWATCH_URL,       _fetch_ipowatch),
    ("investorgain", "https://www.investorgain.com/report/live-ipo-gmp/331/all/", _fetch_investorgain),
    ("niftytrader",  NIFTYTRADER_URL,    _fetch_niftytrader),
)

# Fields a lower-priority source may fill when the winner lacks them.
_FILL_FIELDS = ("priceBand", "type", "status", "date", "openDate", "closeDate",
                "lotSize", "lastUpdated")


def _merge_sources(per_source: list[list[dict]]) -> dict[str, dict]:
    by_name: dict[str, dict] = {}
    for rows in per_source:
        for row in rows:
            key = _normalise_name(row["name"])
            if not key:
                continue
            cur = by_name.get(key)
            if cur is None:
                by_name[key] = dict(row)
                continue
            # Fill factual gaps from the lower-priority source.
            for f in _FILL_FIELDS:
                if not cur.get(f):
                    cur[f] = row.get(f)
            # GMP numbers travel as a bundle so ₹ premium, est-listing and
            # gain% always come from ONE source and stay internally coherent.
            if cur.get("gmp") is None and row.get("gmp") is not None:
                cur["gmp"]        = row.get("gmp")
                cur["estListing"] = row.get("estListing")
                cur["estGainPct"] = row.get("estGainPct")
                cur["source"]     = row.get("source")
                if row.get("lastUpdated"):
                    cur["lastUpdated"] = row["lastUpdated"]
    return by_name


# ── public API ──────────────────────────────────────────────────────────────
async def fetch_gmp_table() -> dict:
    """Fetch + merge every GMP source. Returns:
        { 'byName':    { normalised_name: row_dict, ... },
          'fetchedAt': ISO time of this (or the last good) merge,
          'sourceUrl': page URL of the highest-priority source that answered,
          'sources':   [contributing source keys] }
    Cached in-process for CACHE_TTL seconds. When every source fails, the
    last successful merge is returned (stale beats blank); only if there has
    never been a good merge does `byName` come back empty."""
    global _last_good
    now = time.time()
    cached = _cache.get("table")
    if cached and now - cached[0] < CACHE_TTL:
        return cached[1]

    per_source: list[list[dict]] = []
    contributing: list[str] = []
    primary_url = IPOWATCH_URL
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            results = await asyncio.gather(
                *[fetch(client) for _key, _url, fetch in _SOURCES],
                return_exceptions=True,
            )
        for (key, url, _fetch), res in zip(_SOURCES, results):
            if isinstance(res, Exception):
                logger.warning("GMP source %s failed: %s", key, str(res)[:120])
                continue
            if not res:
                logger.info("GMP source %s returned no rows", key)
                continue
            if not contributing:
                primary_url = url
            contributing.append(key)
            per_source.append(res)
    except Exception as e:
        logger.warning("GMP fetch failed: %s", str(e)[:160])

    by_name = _merge_sources(per_source)
    if not by_name:
        if _last_good:
            logger.warning("all GMP sources failed — serving last good table "
                           "(fetched %s)", _last_good.get("fetchedAt"))
            return _last_good
        return {"byName": {}, "fetchedAt": None, "sourceUrl": IPOWATCH_URL, "sources": []}

    out = {
        "byName":    by_name,
        "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sourceUrl": primary_url,
        "sources":   contributing,
    }
    logger.info("GMP table merged: %d companies from %s", len(by_name), contributing)
    _cache["table"] = (now, out)
    _last_good = out
    return out


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
