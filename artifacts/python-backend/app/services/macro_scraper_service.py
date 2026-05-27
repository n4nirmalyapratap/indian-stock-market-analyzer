"""Macro scraper — aggressive PG-cached scraping of public macro pages.

Why this exists
---------------
Every other macro source we've tried (FRED, IMF, DBnomics, World Bank)
suffers from the same problem for Indian indicators: they republish OECD
or BIS mirrors that lag by months or years. The numbers shown on
tradingeconomics.com/india are typically current to within days of the
official release because TE has its own data team pulling directly from
RBI/MOSPI/CMIE.

We don't pay TE — instead we scrape their public web page once per day
(very polite, very low-bandwidth) and cache every indicator in PG for
24 hours. The cache is the system of record on the read path; the
scraper just keeps it fresh. Caches survive container restarts, so a
fresh deploy doesn't lose data.

What we extract
---------------
A single fetch of `tradingeconomics.com/india/indicators` returns clean
HTML tables covering:
  * Overview tab — Currency, Stock Market, Bond Yields, etc.
  * GDP tab — GDP, GDP Growth, GDP per Capita, …
  * Labour tab — Unemployment, Wages
  * Prices tab — CPI, WPI, Food Inflation, Core Inflation, etc.
  * Money tab — Interest Rate, Cash Reserve Ratio, Money Supply M0/M1/M3
  * Trade tab — Trade Balance, Exports, Imports, Current Account, FX Reserves
  * Government tab — Govt Debt to GDP, Fiscal Deficit, Government Spending
  * Business tab — Manufacturing PMI, Services PMI, Industrial Production
  * Consumer tab — Consumer Confidence, Retail Sales

~30 indicators per scrape, parsed into a single dict.

Robustness
----------
  * If the scrape fails (TE blocks us, network down, HTML structure
    changes), every public read function falls back silently — the
    upstream macro chain (FRED, IMF, etc.) continues to work.
  * The PG cache is the source of truth — readers never wait for
    a fresh scrape; they read whatever the last successful scrape
    saved, with the fetched-at timestamp visible so callers can
    decide whether to treat it as stale.
  * 24h cache means even if TE blocks us today, the dashboard keeps
    showing yesterday's data — almost always still correct for
    monthly-release indicators.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional

import httpx

from app.lib.auth_store import ensure_primary_schema, get_conn

logger = logging.getLogger("macro_scraper")

# ── Source URLs ──────────────────────────────────────────────────────────────

TE_INDIA_INDICATORS_URL = "https://tradingeconomics.com/india/indicators"

# Realistic browser-like headers. Without these TE serves a Cloudflare
# challenge page; the User-Agent has to look like a real desktop browser.
_SCRAPER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control":   "no-cache",
    "Pragma":          "no-cache",
}

# How long the scrape is considered fresh. Bumped to 24h because TE only
# updates indicators ~once per release (monthly for most), so re-scraping
# more often gains nothing.
_FRESH_TTL_SEC = 24 * 60 * 60

# Source slug used for the PG `source` column. Adding a new scrape source
# in future (PIB, macromicro) means a new slug here + the matching parser.
SOURCE_TE = "tradingeconomics"

# Map TE row labels → our canonical indicator slugs. The macro orchestrator
# already uses the slugs on the right (repo / cpi / iip / wpi / gdp /
# yield10) for its tile resolution chain. New slugs added here get
# automatically picked up by `get_indicator` below; the existing macro
# tiles only know the original 6, but adding tiles is a small UI change.
TE_LABEL_TO_SLUG = {
    # ── Core 6 (already in macro tiles) ────────────────────────────────────
    "interest rate":            "repo",
    "inflation rate":           "cpi",
    "industrial production":    "iip",
    "producer prices change":   "wpi",
    "gdp annual growth rate":   "gdp",
    "government bond 10y":      "yield10",
    # ── Useful additions (could become new tiles) ──────────────────────────
    "manufacturing pmi":        "manufacturing_pmi",
    "services pmi":             "services_pmi",
    "composite pmi":            "composite_pmi",
    "unemployment rate":        "unemployment",
    "foreign exchange reserves":"fx_reserves",
    "balance of trade":         "trade_balance",
    "exports":                  "exports",
    "imports":                  "imports",
    "current account":          "current_account",
    "current account to gdp":   "current_account_pct_gdp",
    "fiscal deficit":           "fiscal_deficit",
    "government debt to gdp":   "govt_debt_pct_gdp",
    "money supply m3":          "money_supply_m3",
    "cash reserve ratio":       "crr",
    "core inflation rate":      "core_cpi",
    "food inflation":           "food_cpi",
    "wholesale prices yoy":     "wpi_yoy",
    "consumer confidence":      "consumer_confidence",
    "business confidence":      "business_confidence",
    "car registrations":        "car_registrations",
    "manufacturing production": "manufacturing_production",
    "mining production":        "mining_production",
    "electricity production":   "electricity_production",
    "steel production":         "steel_production",
    "cement production":        "cement_production",
}


# ── PG storage layer ────────────────────────────────────────────────────────


def _now_ms() -> int:
    return int(time.time() * 1000)


def _save_scraped(source: str, indicators: dict[str, dict]) -> int:
    """Bulk-upsert the result of a single scrape into PG. Returns count."""
    if not indicators:
        return 0
    ensure_primary_schema()
    now_ms = _now_ms()
    rows = []
    for slug, d in indicators.items():
        rows.append((
            source, slug,
            d.get("value"),
            d.get("previous_value"),
            d.get("forecast_value"),
            (d.get("unit") or "")[:32],
            (d.get("as_of") or "")[:32],
            (d.get("category") or "")[:64],
            (d.get("raw_label") or "")[:128],
            now_ms,
        ))
    sql = (
        "INSERT INTO macro_scraped_data "
        "(source, indicator, value, previous_value, forecast_value, "
        " unit, as_of, category, raw_label, fetched_at_ms) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (source, indicator) DO UPDATE "
        "       SET value          = EXCLUDED.value, "
        "           previous_value = EXCLUDED.previous_value, "
        "           forecast_value = EXCLUDED.forecast_value, "
        "           unit           = EXCLUDED.unit, "
        "           as_of          = EXCLUDED.as_of, "
        "           category       = EXCLUDED.category, "
        "           raw_label      = EXCLUDED.raw_label, "
        "           fetched_at_ms  = EXCLUDED.fetched_at_ms"
    )
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
    return len(rows)


def get_indicator(indicator: str, source: str = SOURCE_TE,
                  max_age_sec: Optional[int] = None) -> Optional[dict]:
    """Read one cached indicator from PG.

    `max_age_sec` lets callers reject overly-stale entries. None means
    "any age" — fine for dashboard tiles where 'one day late' is still
    better than 'months-old FRED data'.

    Returns the same dict shape we stored: {value, previous_value,
    forecast_value, unit, as_of, category, raw_label, fetched_at_ms}.
    None when no row exists (or it's older than max_age_sec).
    """
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT value, previous_value, forecast_value, unit, as_of, "
                "       category, raw_label, fetched_at_ms "
                "  FROM macro_scraped_data "
                " WHERE source = %s AND indicator = %s",
                (source, indicator),
            )
            row = cur.fetchone()
    if not row:
        return None
    if max_age_sec is not None:
        age_sec = (_now_ms() - int(row["fetched_at_ms"] or 0)) // 1000
        if age_sec > max_age_sec:
            return None
    return dict(row)


def list_indicators(source: Optional[str] = None) -> list[dict]:
    """Admin/diagnostic — return every cached indicator (optionally
    filtered by source). Used by the admin endpoint to show what the
    scraper actually pulled."""
    ensure_primary_schema()
    sql = (
        "SELECT source, indicator, value, previous_value, forecast_value, "
        "       unit, as_of, category, raw_label, fetched_at_ms "
        "  FROM macro_scraped_data"
    )
    params: tuple = ()
    if source:
        sql += " WHERE source = %s"
        params = (source,)
    sql += " ORDER BY source, category, indicator"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [dict(r) for r in rows]


# ── Tradingeconomics scraper ────────────────────────────────────────────────


# TE's indicator rows match this pattern reliably across all sections.
# Layout per row:
#   <a href="/india/...">Indicator Name</a> ... <td>Last</td> <td>Previous</td>
#   <td>Highest</td> <td>Lowest</td> <td>Dates</td> <td>Unit</td> <td>Frequency</td>
# The structure has been stable for years; if TE redesigns, the scraper
# falls back to None and the macro chain continues with FRED/IMF.
_TE_ROW_RE = re.compile(
    r'<tr[^>]*>\s*'
    r'<td[^>]*>\s*<a[^>]*href="/india/[^"]*"[^>]*>([^<]+)</a>'  # 1: label
    r'.*?'
    r'<td[^>]*>\s*([-+]?\d[\d,\.]*)\s*</td>'                    # 2: last
    r'\s*<td[^>]*>\s*([-+]?\d[\d,\.]*)\s*</td>'                 # 3: previous
    r'.*?'
    r'<td[^>]*>\s*([A-Za-z]{3}[/ ]\d{2,4}|\d{4})\s*</td>'       # 4: ref date
    r'.*?'
    r'<td[^>]*>\s*([^<]+?)\s*</td>',                            # 5: unit
    re.IGNORECASE | re.DOTALL,
)


def _parse_te_number(s: str) -> Optional[float]:
    """Parse '5.50', '5,500.10', '1.5 thousand' etc into a float."""
    if not s:
        return None
    cleaned = str(s).replace(",", "").strip()
    # Drop any trailing magnitude word — TE sometimes appends 'Thousand'
    # / 'Million' / 'Billion'. We capture the numeric part only; the
    # unit column already conveys magnitude.
    m = re.match(r"([-+]?\d+(?:\.\d+)?)", cleaned)
    if not m:
        return None
    try:
        return float(m.group(1))
    except (TypeError, ValueError):
        return None


def _detect_category(html_segment: str) -> str:
    """Best-effort: find the nearest section header before this row.
    TE wraps each indicator group in <h2 class="card-header">Category</h2>;
    we look backwards in the page text. Cheap & defensive."""
    m = re.search(r'<h2[^>]*>([^<]{3,40})</h2>', html_segment)
    return (m.group(1) if m else "").strip()


async def scrape_tradingeconomics_india() -> dict[str, dict]:
    """Fetch + parse the TE India indicators page.

    Returns a dict mapping our canonical indicator slugs to per-indicator
    dicts ({value, previous_value, unit, as_of, raw_label, category}).
    Empty dict on any failure (network, parse, or zero rows matched).
    """
    try:
        async with httpx.AsyncClient(
            timeout=20.0, follow_redirects=True, http2=False,
        ) as client:
            resp = await client.get(TE_INDIA_INDICATORS_URL,
                                    headers=_SCRAPER_HEADERS)
        if resp.status_code != 200:
            logger.warning(
                "TE scrape HTTP %s — probably Cloudflare-challenged this IP. "
                "Falling back to existing macro chain.",
                resp.status_code,
            )
            return {}
        html = resp.text
    except Exception as exc:
        logger.warning("TE scrape failed: %s", str(exc)[:160])
        return {}

    # The HTML is large; we scan once for every row matching our regex
    # then map labels to our slugs. Unknown labels are silently skipped.
    out: dict[str, dict] = {}
    for m in _TE_ROW_RE.finditer(html):
        label_raw = (m.group(1) or "").strip()
        label_key = re.sub(r"\s+", " ", label_raw.lower()).strip()
        slug = TE_LABEL_TO_SLUG.get(label_key)
        if not slug:
            continue
        value = _parse_te_number(m.group(2))
        prev  = _parse_te_number(m.group(3))
        as_of = (m.group(4) or "").strip()
        unit  = (m.group(5) or "").strip()
        # Find the section header that contains this row — gives us
        # the category column the admin UI groups by.
        category = _detect_category(html[max(0, m.start() - 4000): m.start()])
        out[slug] = {
            "value":          value,
            "previous_value": prev,
            "forecast_value": None,
            "unit":           unit,
            "as_of":          as_of,
            "category":       category,
            "raw_label":      label_raw,
        }

    if not out:
        logger.warning(
            "TE scrape parsed 0 rows — HTML structure may have changed. "
            "Page length: %d bytes.", len(html),
        )
    else:
        logger.info("TE scrape ok: %d indicators parsed.", len(out))
    return out


async def refresh_all_sources() -> dict[str, int]:
    """Run every scraper (currently just TE) and persist results.

    Returns a per-source count of indicators saved. Called by the
    background scheduler in main.py and by the admin force-refresh
    endpoint.
    """
    saved: dict[str, int] = {}
    try:
        te_data = await scrape_tradingeconomics_india()
        if te_data:
            saved[SOURCE_TE] = _save_scraped(SOURCE_TE, te_data)
        else:
            saved[SOURCE_TE] = 0
    except Exception as exc:
        logger.warning("TE refresh failed: %s", str(exc)[:160])
        saved[SOURCE_TE] = 0
    return saved
