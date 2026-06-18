"""
Synthetic Sub-Industry Rotation Engine
======================================
Hyper-granular sector rotation built on REAL data only. Instead of the ~20
broad NSE sector indices used by /sectors, this engine slices the curated
equity universe into Yahoo *industries* (the most granular level Yahoo
publishes) and synthesises a market-cap-weighted price index for each one.

Pipeline
--------
1. Classifier (`refresh_classifications`) — for every symbol in the curated
   universe, fetch the Yahoo profile (sector / industry / marketCap) and
   persist to the `stocks` table. Runs weekly with bounded concurrency.
   `classified_ok = FALSE` rows (Yahoo profile failed) are excluded from the
   index so we never fabricate a sub-industry tag.

2. Nightly worker (`run_nightly_metrics`) — after 16:00 IST on a trading day:
     • group active+classified stocks by sub_industry,
     • compute the market-cap-weighted daily return → chain it onto the
       previous synthetic index level (base 1000 at inception),
     • average the NSE delivery % across constituents (one sec_bhavdata_full
       CSV fetch for the whole market) and track its 20-DMA,
     • measure 50-EMA breadth (% of constituents trading above their own
       50-day EMA),
   then upsert ONE dated row per sub_industry into
   `synthetic_sector_daily_metrics`.

3. Scanner reads (`get_grid` / `get_drilldown`) — derive 30D relative
   strength vs Nifty 50, delivery build-up vs the 20-DMA, and breadth from
   the stored series. All "no data" states are honest, never zero-filled.

Data sources: Yahoo (profile + OHLCV via the shared YahooService, which uses
`yf.Ticker().history()` and disk-sealed EOD snapshots — never `yf.download`)
and the NSE delivery archive (`sec_bhavdata_full`). Both degrade to honest
`unavailable` states when blocked.
"""
from __future__ import annotations

import asyncio
import csv
import datetime as dt
import io
import logging
import math
import os
import time
from typing import Any, Optional

import httpx

from ..lib import auth_store
from ..lib.symbol_map import to_yahoo_ticker

logger = logging.getLogger("synthetic_sectors")

# ── Tunables ─────────────────────────────────────────────────────────────────
_CLASSIFY_CONCURRENCY = int(os.environ.get("SYNTH_CLASSIFY_CONCURRENCY", "6"))
_INDEX_CONCURRENCY    = int(os.environ.get("SYNTH_INDEX_CONCURRENCY", "8"))
# Re-classify a symbol only if its row is older than this (weekly cadence).
_CLASSIFY_MAX_AGE_S   = int(os.environ.get("SYNTH_CLASSIFY_MAX_AGE_S", str(7 * 24 * 3600)))
# A sub-industry needs at least this many classified constituents to be a
# meaningful index — singletons are just the stock itself, not a "sector".
_MIN_CONSTITUENTS     = int(os.environ.get("SYNTH_MIN_CONSTITUENTS", "3"))
_SYNTH_INDEX_BASE     = 1000.0

# 30-day relative strength: trailing calendar window + the minimum number of
# date-aligned observations the window must contain to be trustworthy (~one
# trading month of ~21 sessions, with slack for holidays). Below this the RS
# is reported as None rather than a distorted short-window figure.
_RS_WINDOW_CAL_DAYS = 30
_RS_MIN_OBS         = 18
# A delivery 20-DMA is only honest once a full 20 sessions of history exist.
_DELIVERY_DMA_WINDOW = 20

# Cap buckets from Yahoo marketCap (absolute INR). SEBI's top-100 / 101-250 /
# rest definition maps roughly onto these rupee thresholds.
_LARGE_CAP_MIN = 1_000_000_000_000   # ₹1,00,000 Cr
_MID_CAP_MIN   = 160_000_000_000     # ₹16,000 Cr

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_HTTP_TIMEOUT = 30.0

# Curated mid-level bucket map: collapses several granular Yahoo industries
# into a cleaner mid-level label for drill-down navigation. Falls back to the
# Yahoo *sector* when an industry is not explicitly mapped — never invented.
_INDUSTRY_BUCKET: dict[str, str] = {
    "Banks - Regional":               "Banks",
    "Banks - Diversified":            "Banks",
    "Asset Management":               "Capital Markets",
    "Capital Markets":                "Capital Markets",
    "Credit Services":                "NBFC & Lending",
    "Financial Data & Stock Exchanges": "Capital Markets",
    "Insurance - Life":               "Insurance",
    "Insurance - Diversified":        "Insurance",
    "Insurance - Property & Casualty": "Insurance",
    "Information Technology Services": "IT Services",
    "Software - Application":          "Software",
    "Software - Infrastructure":       "Software",
    "Drug Manufacturers - Specialty & Generic": "Pharmaceuticals",
    "Drug Manufacturers - General":    "Pharmaceuticals",
    "Auto Manufacturers":              "Automobiles",
    "Auto Parts":                      "Auto Components",
    "Steel":                           "Metals & Mining",
    "Other Industrial Metals & Mining": "Metals & Mining",
    "Aluminum":                        "Metals & Mining",
    "Building Materials":              "Construction Materials",
    "Oil & Gas Refining & Marketing":  "Oil & Gas",
    "Oil & Gas Integrated":            "Oil & Gas",
    "Utilities - Renewable":           "Power & Utilities",
    "Utilities - Independent Power Producers": "Power & Utilities",
    "Engineering & Construction":      "Capital Goods",
    "Specialty Industrial Machinery":  "Capital Goods",
}


# ── DB helpers ───────────────────────────────────────────────────────────────

def _now_ms() -> int:
    return int(time.time() * 1000)


def _cap_category(market_cap: Optional[float]) -> Optional[str]:
    if market_cap is None:
        return None
    if market_cap >= _LARGE_CAP_MIN:
        return "Large-Cap"
    if market_cap >= _MID_CAP_MIN:
        return "Mid-Cap"
    return "Small-Cap"


def _upsert_stock(row: dict[str, Any]) -> None:
    auth_store.ensure_primary_schema()
    with auth_store.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO stocks (symbol, name, yahoo_ticker, sector, industry,
                                    sub_industry, market_cap, cap_category, active,
                                    classified_ok, classify_error, updated_at_ms)
                VALUES (%(symbol)s, %(name)s, %(yahoo_ticker)s, %(sector)s, %(industry)s,
                        %(sub_industry)s, %(market_cap)s, %(cap_category)s, %(active)s,
                        %(classified_ok)s, %(classify_error)s, %(updated_at_ms)s)
                ON CONFLICT (symbol) DO UPDATE SET
                    name           = EXCLUDED.name,
                    yahoo_ticker   = EXCLUDED.yahoo_ticker,
                    sector         = EXCLUDED.sector,
                    industry       = EXCLUDED.industry,
                    sub_industry   = EXCLUDED.sub_industry,
                    market_cap     = EXCLUDED.market_cap,
                    cap_category   = EXCLUDED.cap_category,
                    active         = EXCLUDED.active,
                    classified_ok  = EXCLUDED.classified_ok,
                    classify_error = EXCLUDED.classify_error,
                    updated_at_ms  = EXCLUDED.updated_at_ms
                """,
                row,
            )


def _load_classified_stocks() -> list[dict[str, Any]]:
    """Active stocks that classified OK and have a real sub_industry tag,
    merged with admin-managed overrides. Overrides can add any symbol to any
    sub-industry even if Yahoo classification failed for that symbol."""
    auth_store.ensure_primary_schema()
    with auth_store.get_conn() as conn:
        with conn.cursor() as cur:
            # Yahoo-classified rows
            cur.execute(
                """
                SELECT symbol, name, yahoo_ticker, sector, industry, sub_industry,
                       market_cap, cap_category
                  FROM stocks
                 WHERE active AND classified_ok
                   AND sub_industry IS NOT NULL AND sub_industry <> ''
                   AND market_cap IS NOT NULL AND market_cap > 0
                 ORDER BY sub_industry, market_cap DESC
                """
            )
            yahoo_rows = [dict(r) for r in cur.fetchall()]

            # Admin overrides: pull market_cap from stocks if known
            cur.execute(
                """
                SELECT o.symbol, o.sub_industry, o.industry, o.sector,
                       s.name, s.yahoo_ticker, s.market_cap, s.cap_category,
                       s.active
                  FROM sub_industry_overrides o
                  LEFT JOIN stocks s ON s.symbol = o.symbol
                 ORDER BY o.sub_industry, s.market_cap DESC NULLS LAST
                """
            )
            override_rows = cur.fetchall()

    # Build set of (symbol, sub_industry) already in yahoo_rows to avoid duplication
    yahoo_keys = {(r["symbol"], r["sub_industry"]) for r in yahoo_rows}

    merged = list(yahoo_rows)
    for r in override_rows:
        r = dict(r)
        key = (r["symbol"], r["sub_industry"])
        if key in yahoo_keys:
            continue  # Yahoo classification already covers this slot
        market_cap = r.get("market_cap")
        if market_cap is None or market_cap <= 0:
            continue  # Can't contribute to market-cap-weighted index without cap
        merged.append({
            "symbol": r["symbol"],
            "name": r.get("name") or r["symbol"],
            "yahoo_ticker": r.get("yahoo_ticker") or r["symbol"],
            "sector": r.get("sector") or "",
            "industry": r.get("industry") or "",
            "sub_industry": r["sub_industry"],
            "market_cap": market_cap,
            "cap_category": r.get("cap_category"),
        })
    return merged


def _stale_or_missing_symbols(symbols: list[str]) -> list[str]:
    """Return the subset of `symbols` whose stocks row is missing or older
    than the weekly cadence — only these are re-fetched from Yahoo."""
    auth_store.ensure_primary_schema()
    cutoff = _now_ms() - _CLASSIFY_MAX_AGE_S * 1000
    with auth_store.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT symbol, updated_at_ms, classified_ok FROM stocks "
                "WHERE symbol = ANY(%s)",
                (symbols,),
            )
            existing = {r["symbol"]: r for r in cur.fetchall()}
    out: list[str] = []
    for s in symbols:
        row = existing.get(s)
        if row is None:
            out.append(s)
        elif not row["classified_ok"] or (row["updated_at_ms"] or 0) < cutoff:
            out.append(s)
    return out


# ── Classifier ───────────────────────────────────────────────────────────────

def _classify_one_sync(symbol: str) -> dict[str, Any]:
    """Blocking Yahoo profile fetch for a single symbol. Returns the stocks
    row payload — classified_ok is False on any failure so the symbol is
    excluded from the index rather than mislabelled."""
    import yfinance as yf

    yt = to_yahoo_ticker(symbol)
    base = {
        "symbol": symbol,
        "name": symbol,
        "yahoo_ticker": yt,
        "sector": None,
        "industry": None,
        "sub_industry": None,
        "market_cap": None,
        "cap_category": None,
        "active": True,
        "classified_ok": False,
        "classify_error": "",
        "updated_at_ms": _now_ms(),
    }
    try:
        info = yf.Ticker(yt).info or {}
        sector = (info.get("sector") or "").strip() or None
        industry = (info.get("industry") or "").strip() or None
        market_cap = info.get("marketCap")
        if not isinstance(market_cap, (int, float)) or market_cap <= 0:
            market_cap = None
        if not sector or not industry:
            base["classify_error"] = "missing sector/industry in Yahoo profile"
            base["sector"] = sector
            base["industry"] = _INDUSTRY_BUCKET.get(industry or "", sector)
            base["sub_industry"] = industry
            base["market_cap"] = market_cap
            base["cap_category"] = _cap_category(market_cap)
            return base
        base.update(
            {
                "name": info.get("longName") or info.get("shortName") or symbol,
                "sector": sector,
                "industry": _INDUSTRY_BUCKET.get(industry, sector),
                "sub_industry": industry,
                "market_cap": market_cap,
                "cap_category": _cap_category(market_cap),
                "classified_ok": market_cap is not None,
                "classify_error": "" if market_cap is not None else "missing marketCap",
            }
        )
        return base
    except Exception as exc:  # noqa: BLE001 — degrade to honest unclassified
        base["classify_error"] = str(exc)[:200]
        return base


def seed_overrides_from_taxonomy() -> dict[str, int]:
    """Bulk-seed `sub_industry_overrides` from SUBSECTOR_TAXONOMY for every
    symbol that already has a real market_cap in the `stocks` table.

    Unlike `_seed_taxonomy_stocks()` which puts stub rows in `stocks`
    (classified_ok=False, no market_cap), THIS function creates override rows
    for already-classified stocks — so the nightly metrics worker immediately
    sees all taxonomy sub-industries the next time it runs, without waiting for
    Yahoo to re-classify everyone under our new sub_industry label names.

    Safe to call repeatedly: ON CONFLICT (symbol, sub_industry) DO NOTHING
    means existing overrides are never clobbered.

    Returns {"seeded": <N new rows inserted>}
    """
    from ..lib.universe import SUBSECTOR_TAXONOMY
    auth_store.ensure_primary_schema()
    now = _now_ms()
    inserted = 0
    with auth_store.get_conn() as conn:
        with conn.cursor() as cur:
            for sub_industry, entry in SUBSECTOR_TAXONOMY.items():
                industry = entry.get("industry", "")
                sector = entry.get("sector", "")
                for sym in entry["symbols"]:
                    cur.execute(
                        """
                        INSERT INTO sub_industry_overrides
                            (symbol, sub_industry, industry, sector, note,
                             set_by, created_at_ms, updated_at_ms)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, sub_industry) DO NOTHING
                        """,
                        (sym, sub_industry, industry, sector,
                         "auto-seeded from SUBSECTOR_TAXONOMY",
                         "system", now, now),
                    )
                    inserted += cur.rowcount
    logger.info("seed_overrides_from_taxonomy: %d new override rows inserted", inserted)
    return {"seeded": inserted}


def _seed_taxonomy_stocks() -> None:
    """Upsert stub rows for every symbol in SUBSECTOR_TAXONOMY so they appear
    in the `stocks` table even before Yahoo classification succeeds. The row is
    marked classified_ok=False / active=True so it won't be included in the
    index calculation until Yahoo fills in the market_cap — but it WILL be
    picked up by the classifier's stale-check and fetched on the next weekly run.
    Rows that already exist are left untouched (the symbol col is the PK)."""
    from ..lib.universe import SUBSECTOR_TAXONOMY
    now = _now_ms()
    rows_to_seed: list[dict[str, Any]] = []
    for sub_industry, entry in SUBSECTOR_TAXONOMY.items():
        for sym in entry["symbols"]:
            rows_to_seed.append({
                "symbol": sym,
                "name": sym,
                "yahoo_ticker": sym,
                "sector": entry.get("sector", ""),
                "industry": entry.get("industry", ""),
                "sub_industry": sub_industry,
                "market_cap": None,
                "cap_category": None,
                "active": True,
                "classified_ok": False,
                "classify_error": "taxonomy seed — awaiting Yahoo classification",
                "updated_at_ms": now,
            })
    if not rows_to_seed:
        return
    auth_store.ensure_primary_schema()
    with auth_store.get_conn() as conn:
        with conn.cursor() as cur:
            for row in rows_to_seed:
                cur.execute(
                    """
                    INSERT INTO stocks (symbol, name, yahoo_ticker, sector, industry,
                                        sub_industry, market_cap, cap_category, active,
                                        classified_ok, classify_error, updated_at_ms)
                    VALUES (%(symbol)s, %(name)s, %(yahoo_ticker)s, %(sector)s, %(industry)s,
                            %(sub_industry)s, %(market_cap)s, %(cap_category)s, %(active)s,
                            %(classified_ok)s, %(classify_error)s, %(updated_at_ms)s)
                    ON CONFLICT (symbol) DO NOTHING
                    """,
                    row,
                )


async def refresh_classifications(force: bool = False) -> dict[str, Any]:
    """Classify the curated universe into the `stocks` table. Only stale /
    missing symbols are fetched unless `force=True`. Bounded concurrency keeps
    Yahoo load and event-loop pressure in check.

    Before fetching Yahoo data, we upsert taxonomy stub rows so that every
    curated sub-industry symbol exists in the table and will be picked up by
    the next classifier run even if it wasn't in the original universe lists."""
    from ..lib import universe

    # Seed taxonomy stubs first (ON CONFLICT DO NOTHING — safe to re-run)
    await asyncio.to_thread(_seed_taxonomy_stocks)

    symbols = [s for s in universe.ALL_SYMBOLS if not s.startswith("^")]
    targets = symbols if force else _stale_or_missing_symbols(symbols)
    if not targets:
        return {"classified": 0, "ok": 0, "failed": 0, "skipped": len(symbols)}

    sem = asyncio.Semaphore(_CLASSIFY_CONCURRENCY)
    ok = 0
    failed = 0

    async def _worker(sym: str) -> None:
        nonlocal ok, failed
        async with sem:
            row = await asyncio.to_thread(_classify_one_sync, sym)
        try:
            await asyncio.to_thread(_upsert_stock, row)
        except Exception as exc:  # noqa: BLE001
            logger.warning("classify: upsert failed for %s: %s", sym, exc)
            failed += 1
            return
        if row["classified_ok"]:
            ok += 1
        else:
            failed += 1

    await asyncio.gather(*(_worker(s) for s in targets))
    result = {
        "classified": len(targets),
        "ok": ok,
        "failed": failed,
        "skipped": len(symbols) - len(targets),
    }
    logger.info("synthetic classifier: %s", result)
    return result


# ── NSE delivery archive ─────────────────────────────────────────────────────

def _deliv_url(d: dt.date) -> str:
    return (
        "https://nsearchives.nseindia.com/products/content/"
        f"sec_bhavdata_full_{d.strftime('%d%m%Y')}.csv"
    )


def _fetch_delivery_map_sync(d: dt.date) -> Optional[dict[str, float]]:
    """One CSV fetch for the whole market → {SYMBOL: DELIV_PER}. EQ/BE series
    only. Returns None when the archive is unavailable for that date (holiday,
    not-yet-published, or blocked) so the caller degrades honestly."""
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
    }
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True) as c:
            r = c.get(_deliv_url(d), headers=headers)
        if r.status_code != 200 or not r.content:
            logger.info("delivery archive %s → %d", d, r.status_code)
            return None
    except httpx.HTTPError as exc:
        logger.warning("delivery archive %s failed: %s", d, exc)
        return None

    out: dict[str, float] = {}
    reader = csv.DictReader(io.StringIO(r.content.decode("utf-8", "replace")))
    for raw in reader:
        # NSE pads headers and values with spaces — normalise both.
        row = {(k or "").strip(): (v or "").strip() for k, v in raw.items()}
        series = row.get("SERIES", "")
        if series not in ("EQ", "BE"):
            continue
        sym = row.get("SYMBOL", "")
        deliv = row.get("DELIV_PER", "")
        if not sym or deliv in ("", "-"):
            continue
        try:
            out[sym] = float(deliv)
        except ValueError:
            continue
    return out or None


# ── Per-constituent metrics ──────────────────────────────────────────────────

def _ema(values: list[float], span: int) -> Optional[float]:
    """Standard EMA over a close series. Needs at least `span` points to be
    meaningful; returns None otherwise."""
    if len(values) < span:
        return None
    k = 2.0 / (span + 1.0)
    ema = sum(values[:span]) / span  # seed with SMA of the first window
    for v in values[span:]:
        ema = v * k + ema * (1 - k)
    return ema


async def _constituent_signal(
    yahoo, symbol: str, sem: asyncio.Semaphore
) -> Optional[dict[str, Any]]:
    """Fetch ~90d history and derive the last daily return + 50-EMA position.
    Returns None when history is too thin to be trustworthy."""
    async with sem:
        try:
            bars = await yahoo.get_historical_data(symbol, days=90)
        except Exception as exc:  # noqa: BLE001
            logger.debug("constituent history failed %s: %s", symbol, exc)
            return None
    if not bars or len(bars) < 2:
        return None
    closes = [float(b.get("close")) for b in bars if b.get("close")]
    if len(closes) < 2:
        return None
    prev, last = closes[-2], closes[-1]
    if prev <= 0:
        return None
    daily_return = (last - prev) / prev * 100.0
    ema50 = _ema(closes, 50)
    above_50ema = None if ema50 is None else bool(last > ema50)
    return {
        "symbol": symbol,
        "daily_return_pct": daily_return,
        "above_50ema": above_50ema,
        "last_close": last,
    }


# ── Nightly aggregation ──────────────────────────────────────────────────────

def _prev_index_levels(sub_industries: list[str], before: dt.date) -> dict[str, float]:
    """Latest stored synthetic index level per sub_industry strictly before
    `before` — used to chain today's return onto yesterday's level."""
    if not sub_industries:
        return {}
    with auth_store.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (sub_industry) sub_industry, index_value
                  FROM synthetic_sector_daily_metrics
                 WHERE sub_industry = ANY(%s) AND metric_date < %s
                       AND index_value IS NOT NULL
                 ORDER BY sub_industry, metric_date DESC
                """,
                (sub_industries, before),
            )
            return {r["sub_industry"]: float(r["index_value"]) for r in cur.fetchall()}


def _delivery_20dma(sub_industry: str, before: dt.date) -> Optional[float]:
    """Average of the last 20 stored avg_delivery_pct values strictly before
    `before`. None until enough history exists."""
    with auth_store.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT avg_delivery_pct FROM synthetic_sector_daily_metrics
                 WHERE sub_industry = %s AND metric_date < %s
                       AND avg_delivery_pct IS NOT NULL
                 ORDER BY metric_date DESC LIMIT %s
                """,
                (sub_industry, before, _DELIVERY_DMA_WINDOW),
            )
            vals = [float(r["avg_delivery_pct"]) for r in cur.fetchall()]
    # Only a *full* 20-session window is a real 20-DMA; partial history would
    # produce a misleading short-window average and trip the build-up flag early.
    if len(vals) < _DELIVERY_DMA_WINDOW:
        return None
    return sum(vals) / len(vals)


def _upsert_metric(row: dict[str, Any]) -> None:
    with auth_store.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO synthetic_sector_daily_metrics
                    (sub_industry, metric_date, index_value, daily_return_pct,
                     avg_delivery_pct, delivery_20dma, breadth_50ema_pct,
                     constituent_count, total_market_cap, created_at_ms)
                VALUES
                    (%(sub_industry)s, %(metric_date)s, %(index_value)s, %(daily_return_pct)s,
                     %(avg_delivery_pct)s, %(delivery_20dma)s, %(breadth_50ema_pct)s,
                     %(constituent_count)s, %(total_market_cap)s, %(created_at_ms)s)
                ON CONFLICT (sub_industry, metric_date) DO UPDATE SET
                    index_value       = EXCLUDED.index_value,
                    daily_return_pct  = EXCLUDED.daily_return_pct,
                    avg_delivery_pct  = EXCLUDED.avg_delivery_pct,
                    delivery_20dma    = EXCLUDED.delivery_20dma,
                    breadth_50ema_pct = EXCLUDED.breadth_50ema_pct,
                    constituent_count = EXCLUDED.constituent_count,
                    total_market_cap  = EXCLUDED.total_market_cap,
                    created_at_ms     = EXCLUDED.created_at_ms
                """,
                row,
            )


def compute_group_metrics(
    constituents: list[dict[str, Any]],
    signals: dict[str, dict[str, Any]],
    delivery: Optional[dict[str, float]],
) -> Optional[dict[str, Any]]:
    """Pure aggregation for one sub-industry (no I/O — unit-tested directly).

    constituents: rows from `stocks` (need symbol + market_cap).
    signals:      {symbol: {daily_return_pct, above_50ema}} from history.
    delivery:     {symbol: deliv_per} or None when archive unavailable.

    Returns the metric payload, or None when too few constituents have a
    usable signal to form a trustworthy index.
    """
    weighted_num = 0.0
    weight_sum = 0.0
    above = 0
    breadth_n = 0
    deliv_vals: list[float] = []
    used = 0

    for c in constituents:
        sym = c["symbol"]
        sig = signals.get(sym)
        if not sig:
            continue
        cap = c.get("market_cap")
        if not cap or cap <= 0:
            continue
        weighted_num += sig["daily_return_pct"] * cap
        weight_sum += cap
        used += 1
        if sig.get("above_50ema") is not None:
            breadth_n += 1
            if sig["above_50ema"]:
                above += 1
        if delivery is not None and sym in delivery:
            deliv_vals.append(delivery[sym])

    if used < _MIN_CONSTITUENTS or weight_sum <= 0:
        return None

    daily_return = weighted_num / weight_sum
    breadth = (above / breadth_n * 100.0) if breadth_n else None
    avg_delivery = (sum(deliv_vals) / len(deliv_vals)) if deliv_vals else None
    return {
        "daily_return_pct": daily_return,
        "breadth_50ema_pct": breadth,
        "avg_delivery_pct": avg_delivery,
        "constituent_count": used,
        "total_market_cap": weight_sum,
    }


async def _write_benchmark_row(yahoo, metric_date: dt.date) -> None:
    """Persist a Nifty 50 row (sub_industry='__NIFTY50__') chained identically
    to the sub-industry indices so read-time RS is apples-to-apples. Degrades
    silently when ^NSEI history is unavailable — RS then becomes None."""
    try:
        bars = await yahoo.get_historical_data("NIFTY 50", days=90)
    except Exception as exc:  # noqa: BLE001
        logger.debug("benchmark history failed: %s", exc)
        return
    closes = [float(b.get("close")) for b in (bars or []) if b.get("close")]
    if len(closes) < 2 or closes[-2] <= 0:
        return
    daily_return = (closes[-1] - closes[-2]) / closes[-2] * 100.0
    prev = (await asyncio.to_thread(_prev_index_levels, ["__NIFTY50__"], metric_date)).get("__NIFTY50__")
    index_value = _SYNTH_INDEX_BASE if prev is None else prev * (1.0 + daily_return / 100.0)
    row = {
        "sub_industry": "__NIFTY50__",
        "metric_date": metric_date,
        "index_value": index_value,
        "daily_return_pct": daily_return,
        "avg_delivery_pct": None,
        "delivery_20dma": None,
        "breadth_50ema_pct": None,
        "constituent_count": 0,
        "total_market_cap": None,
        "created_at_ms": _now_ms(),
    }
    await asyncio.to_thread(_upsert_metric, row)


async def run_nightly_metrics(
    yahoo, metric_date: Optional[dt.date] = None
) -> dict[str, Any]:
    """Build one dated row per sub_industry for `metric_date` (defaults to the
    latest IST trading day). Idempotent — safe to re-run for the same date."""
    if metric_date is None:
        metric_date = _latest_trading_day()

    stocks = await asyncio.to_thread(_load_classified_stocks)
    if not stocks:
        return {"date": str(metric_date), "groups": 0, "error": "no classified stocks"}

    groups: dict[str, list[dict[str, Any]]] = {}
    for s in stocks:
        groups.setdefault(s["sub_industry"], []).append(s)
    # Only groups that can clear the minimum-constituents bar are worth fetching.
    groups = {k: v for k, v in groups.items() if len(v) >= _MIN_CONSTITUENTS}
    if not groups:
        return {"date": str(metric_date), "groups": 0, "error": "no groups >= min constituents"}

    # 0) Nifty 50 benchmark — stored in lockstep so read-time RS is computed
    #    against a benchmark series chained exactly like the sub-industries.
    await _write_benchmark_row(yahoo, metric_date)

    # 1) Delivery — single market-wide CSV fetch (None ⇒ honest unavailable).
    delivery = await asyncio.to_thread(_fetch_delivery_map_sync, metric_date)

    # 2) Per-constituent signals with bounded concurrency.
    sem = asyncio.Semaphore(_INDEX_CONCURRENCY)
    all_symbols = [s["symbol"] for s in stocks]
    sig_list = await asyncio.gather(
        *(_constituent_signal(yahoo, sym, sem) for sym in all_symbols)
    )
    signals = {s["symbol"]: s for s in sig_list if s}

    # 3) Aggregate + chain index level, then persist.
    sub_inds = list(groups.keys())
    prev_levels = await asyncio.to_thread(_prev_index_levels, sub_inds, metric_date)

    written = 0
    skipped = 0
    for sub_ind, members in groups.items():
        m = compute_group_metrics(members, signals, delivery)
        if m is None:
            skipped += 1
            continue
        prev = prev_levels.get(sub_ind)
        index_value = (
            _SYNTH_INDEX_BASE
            if prev is None
            else prev * (1.0 + m["daily_return_pct"] / 100.0)
        )
        dma20 = await asyncio.to_thread(_delivery_20dma, sub_ind, metric_date)
        row = {
            "sub_industry": sub_ind,
            "metric_date": metric_date,
            "index_value": index_value,
            "daily_return_pct": m["daily_return_pct"],
            "avg_delivery_pct": m["avg_delivery_pct"],
            "delivery_20dma": dma20,
            "breadth_50ema_pct": m["breadth_50ema_pct"],
            "constituent_count": m["constituent_count"],
            "total_market_cap": m["total_market_cap"],
            "created_at_ms": _now_ms(),
        }
        await asyncio.to_thread(_upsert_metric, row)
        written += 1

    result = {
        "date": str(metric_date),
        "groups": len(groups),
        "written": written,
        "skipped": skipped,
        "deliveryAvailable": delivery is not None,
        "signals": len(signals),
    }
    logger.info("synthetic nightly metrics: %s", result)
    return result


# ── Read / scanner helpers ───────────────────────────────────────────────────

def _latest_trading_day(now: Optional[dt.datetime] = None) -> dt.date:
    """Most recent weekday in IST. (Holidays are tolerated — the archive
    fetch simply returns None and delivery degrades to unavailable.)"""
    now = now or dt.datetime.utcnow() + dt.timedelta(hours=5, minutes=30)
    d = now.date()
    # Before 16:00 IST the current day's EOD data isn't sealed → use prior day.
    if now.hour < 16:
        d -= dt.timedelta(days=1)
    while d.weekday() >= 5:  # Sat=5, Sun=6
        d -= dt.timedelta(days=1)
    return d


def relative_strength_30d(
    index_series: list[tuple[dt.date, float]],
    nifty_series: list[tuple[dt.date, float]],
) -> Optional[float]:
    """30-day relative strength: sub-industry % change minus Nifty 50 % change
    over a *date-aligned* trailing 30-calendar-day window.

    Both inputs are ``(date, index_value)`` pairs. The series are intersected on
    date (so a sub-industry that was skipped on a given session is never compared
    against a Nifty session it doesn't have), restricted to the trailing
    ``_RS_WINDOW_CAL_DAYS`` window, and only computed when the window holds at
    least ``_RS_MIN_OBS`` aligned observations. Positive ⇒ outperforming the
    broad market. None when the aligned window is too short to be a real 30D RS.
    """
    if not index_series or not nifty_series:
        return None
    nmap = {d: v for d, v in nifty_series}
    aligned = sorted(
        ((d, v, nmap[d]) for d, v in index_series if d in nmap),
        key=lambda t: t[0],
    )
    if not aligned:
        return None
    cutoff = aligned[-1][0] - dt.timedelta(days=_RS_WINDOW_CAL_DAYS)
    window = [t for t in aligned if t[0] >= cutoff]
    if len(window) < _RS_MIN_OBS:
        return None
    i0, n0 = window[0][1], window[0][2]
    i1, n1 = window[-1][1], window[-1][2]
    if i0 <= 0 or n0 <= 0:
        return None
    return (i1 - i0) / i0 * 100.0 - (n1 - n0) / n0 * 100.0


def delivery_buildup(avg_delivery: Optional[float], dma20: Optional[float]) -> Optional[bool]:
    """Build-up flag: today's avg delivery % is >15% above its 20-DMA —
    interpreted as fresh institutional accumulation. None when data missing."""
    if avg_delivery is None or dma20 is None or dma20 <= 0:
        return None
    return avg_delivery >= dma20 * 1.15


def _latest_metric_date() -> Optional[dt.date]:
    with auth_store.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT MAX(metric_date) AS d FROM synthetic_sector_daily_metrics"
            )
            row = cur.fetchone()
    return row["d"] if row and row["d"] else None


def _all_index_series_since(since: dt.date) -> dict[str, list[tuple[dt.date, float]]]:
    """Every sub-industry's (and ``__NIFTY50__``'s) index series since ``since`` in
    ONE query — replaces N per-sub-industry round-trips. Keyed by sub_industry,
    each value ascending by date. Used by get_grid and the rotation cockpit."""
    out: dict[str, list[tuple[dt.date, float]]] = {}
    with auth_store.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sub_industry, metric_date, index_value
                  FROM synthetic_sector_daily_metrics
                 WHERE metric_date >= %s AND index_value IS NOT NULL
                 ORDER BY sub_industry ASC, metric_date ASC
                """,
                (since,),
            )
            for r in cur.fetchall():
                out.setdefault(r["sub_industry"], []).append(
                    (r["metric_date"], float(r["index_value"]))
                )
    return out


def get_grid() -> dict[str, Any]:
    """Scanner grid feed: one entry per sub-industry with 30D RS vs Nifty 50,
    delivery build-up vs 20-DMA, and 50-EMA breadth. Honest unavailable state
    when the nightly worker has never run."""
    auth_store.ensure_primary_schema()
    latest = _latest_metric_date()
    if latest is None:
        return {"asOf": None, "available": False, "rows": [], "note": "No synthetic metrics computed yet."}

    since = latest - dt.timedelta(days=45)  # buffer ≥30 trading days
    # All sub-industry series + the Nifty 50 benchmark in ONE query (was 1 + N
    # sequential round-trips). Sliced per sub-industry below.
    series = _all_index_series_since(since)
    nifty_series = series.get("__NIFTY50__", [])

    with auth_store.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.sub_industry, s.index_value, s.daily_return_pct,
                       s.avg_delivery_pct, s.delivery_20dma, s.breadth_50ema_pct,
                       s.constituent_count
                  FROM synthetic_sector_daily_metrics s
                 WHERE s.metric_date = %s AND s.sub_industry <> '__NIFTY50__'
                 ORDER BY s.sub_industry ASC
                """,
                (latest,),
            )
            latest_rows = [dict(r) for r in cur.fetchall()]

    rows: list[dict[str, Any]] = []
    for r in latest_rows:
        sub = r["sub_industry"]
        idx_series = series.get(sub, [])
        rs = relative_strength_30d(idx_series, nifty_series) if nifty_series else None
        rows.append(
            {
                "subIndustry": sub,
                "indexValue": r["index_value"],
                "dailyReturnPct": r["daily_return_pct"],
                "rs30d": rs,
                "avgDeliveryPct": r["avg_delivery_pct"],
                "delivery20dma": r["delivery_20dma"],
                "deliveryBuildup": delivery_buildup(r["avg_delivery_pct"], r["delivery_20dma"]),
                "breadth50emaPct": r["breadth_50ema_pct"],
                "constituentCount": r["constituent_count"],
            }
        )
    return {"asOf": str(latest), "available": True, "rows": rows}


def get_drilldown(sub_industry: str, yahoo) -> dict[str, Any]:
    """Constituents of a sub-industry ranked by market-cap weight. Merges
    Yahoo-classified stocks with admin-managed overrides so every manually
    curated stock is visible even if Yahoo classification failed."""
    auth_store.ensure_primary_schema()
    with auth_store.get_conn() as conn:
        with conn.cursor() as cur:
            # Yahoo-classified members
            cur.execute(
                """
                SELECT symbol, name, sector, industry, market_cap, cap_category
                  FROM stocks
                 WHERE active AND classified_ok AND sub_industry = %s
                 ORDER BY market_cap DESC NULLS LAST
                """,
                (sub_industry,),
            )
            members = [dict(r) for r in cur.fetchall()]

            # Admin-override members (symbol may or may not be in stocks)
            cur.execute(
                """
                SELECT o.symbol, o.sub_industry, o.industry, o.sector, o.note,
                       s.name, s.market_cap, s.cap_category, s.classified_ok
                  FROM sub_industry_overrides o
                  LEFT JOIN stocks s ON s.symbol = o.symbol
                 WHERE o.sub_industry = %s
                 ORDER BY s.market_cap DESC NULLS LAST
                """,
                (sub_industry,),
            )
            overrides = cur.fetchall()

    yahoo_syms = {m["symbol"] for m in members}
    for r in overrides:
        r = dict(r)
        if r["symbol"] in yahoo_syms:
            continue
        members.append({
            "symbol": r["symbol"],
            "name": r.get("name") or r["symbol"],
            "sector": r.get("sector") or "",
            "industry": r.get("industry") or "",
            "market_cap": r.get("market_cap"),
            "cap_category": r.get("cap_category"),
            "_override": True,
            "_note": r.get("note", ""),
        })

    if not members:
        return {"subIndustry": sub_industry, "available": False, "constituents": []}
    total_cap = sum((m["market_cap"] or 0) for m in members) or 0
    out = []
    for m in members:
        cap = m["market_cap"] or 0
        out.append(
            {
                "symbol": m["symbol"],
                "name": m["name"],
                "sector": m["sector"],
                "industry": m["industry"],
                "marketCap": m["market_cap"],
                "capCategory": m["cap_category"],
                "weightPct": (cap / total_cap * 100.0) if total_cap else None,
            }
        )
    return {"subIndustry": sub_industry, "available": True, "constituents": out}
