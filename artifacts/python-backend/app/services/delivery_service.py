"""delivery_service.py — single source of truth for NSE delivery data and
*accurate* group (sector) delivery rollups.

Why this exists
---------------
The insights "Top Deliveries" sector rollup was inaccurate for three reasons:
  1. it aggregated only the *filtered* on-screen slice, so a sector's delivery
     changed depending on the selected index / minDelivPct filter;
  2. its headline number was a simple mean of per-stock delivery % (a tiny
     illiquid stock at 90% counted the same as a mega-cap at 40%);
  3. classification came from a patchy external source, not our own taxonomy.

This module fetches the FULL market delivery once (NSE ``sec_bhavdata_full``),
caches it, and rolls it up by NSE sector-index membership **quantity-weighted**
(Σ delivQty / Σ tradedQty) — the statistically correct measure — independent of
any UI filter. It's the shared delivery source for the Sector-Rotation cockpit,
the per-stock shortlist, and the (fixed) insights sector block.

Sub-industry delivery is intentionally NOT recomputed here: ``synthetic_sectors_service``
already stores it per sub-industry (with 20-DMA / build-up) consistently with its
RS and breadth, so we reuse that there.
"""
from __future__ import annotations

import csv as _csv
import io
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("delivery_service")

_NSE_BHAVDATA_URL_TPL = (
    "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
)
_TTL_SEC = 4 * 3600
# Module-level cache of the latest full-market delivery rows.
_cache: dict = {"rows": None, "date": None, "ts": 0.0}


def _parse(text: str) -> list[dict]:
    """Parse NSE sec_bhavdata_full CSV → per-symbol delivery rows (EQ series).

    Columns: SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN, HIGH, LOW, LAST, CLOSE,
    AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY, DELIV_PER.
    """
    rows: list[dict] = []
    rdr = _csv.reader(io.StringIO(text))
    header = None
    for raw in rdr:
        if not raw:
            continue
        cells = [c.strip() for c in raw]
        if header is None:
            header = cells
            continue
        if len(cells) < 15 or cells[1].upper() != "EQ":
            continue
        sym = cells[0].upper()
        try:
            avg_price  = float(cells[9] or 0)
            traded_qty = int(float(cells[10] or 0))
            turnover_l = float(cells[11] or 0)            # lakhs
            deliv_qty  = int(float(cells[13] or 0)) if cells[13] not in ("", "-") else 0
            deliv_pct  = float(cells[14] or 0) if cells[14] not in ("", "-") else 0.0
        except (TypeError, ValueError):
            continue
        if traded_qty <= 0 or deliv_pct <= 0:
            continue
        rows.append({
            "symbol":     sym,
            "tradedQty":  traded_qty,
            "delivQty":   deliv_qty,
            "delivPct":   round(deliv_pct, 2),
            "turnover":   round(turnover_l * 1_00_000, 0),       # lakhs → ₹
            "delivValue": round(deliv_qty * avg_price, 0) if avg_price else 0.0,
        })
    return rows


async def get_delivery_rows() -> tuple[list[dict], Optional[str]]:
    """Full-market per-symbol delivery rows for the latest available session.

    Walks back up to 7 days for the most recent published bhavcopy. Cached 4h.
    Returns ``(rows, trade_date_iso)``; ``rows`` is ``[]`` when unavailable.
    """
    now = time.time()
    if _cache["rows"] is not None and (now - _cache["ts"]) < _TTL_SEC:
        return _cache["rows"], _cache["date"]

    from ..services import registry as svc  # noqa: PLC0415 — lazy, avoid import cycle

    rows: list[dict] = []
    trade_date: Optional[str] = None
    today = datetime.utcnow()
    for offset in range(0, 8):
        d = today - timedelta(days=offset)
        if d.weekday() >= 5:                  # skip Sat/Sun
            continue
        ddmmyyyy = d.strftime("%d%m%Y")
        url = _NSE_BHAVDATA_URL_TPL.format(ddmmyyyy=ddmmyyyy)
        try:
            text = await svc.nse.fetch_nse_archive_text(url, f"bhav-{ddmmyyyy}", ttl=86400)
        except Exception as exc:
            logger.warning("delivery bhavdata %s fetch failed: %s", ddmmyyyy, exc)
            text = None
        if text and "SYMBOL" in text[:50] and "DELIV_PER" in text[:300]:
            parsed = _parse(text)
            if parsed:
                rows = parsed
                trade_date = d.strftime("%Y-%m-%d")
                break

    _cache.update(rows=rows, date=trade_date, ts=now)
    return rows, trade_date


async def get_delivery_map() -> dict[str, float]:
    """``{SYMBOL: delivery%}`` for the latest session (for per-symbol lookups)."""
    rows, _ = await get_delivery_rows()
    return {r["symbol"]: r["delivPct"] for r in rows}


def aggregate_delivery(groups: dict[str, list[str]], rows: list[dict]) -> list[dict]:
    """Quantity-weighted delivery per group. Pure function (unit-testable).

    ``groups``: group name → member symbols. ``delivRatio`` (Σ delivQty / Σ
    tradedQty × 100) is the accurate headline; ``avgDelivPct`` (simple mean) is
    kept only for reference. Groups with no matched symbols are dropped.
    """
    by_sym = {r["symbol"]: r for r in rows}
    out: list[dict] = []
    for name, syms in groups.items():
        tt = td = 0
        turnover = dv = pct_sum = 0.0
        cnt = 0
        top_sym: Optional[str] = None
        top_pct = -1.0
        for s in syms:
            r = by_sym.get((s or "").upper())
            if not r:
                continue
            tt += r["tradedQty"]
            td += r["delivQty"]
            turnover += r["turnover"]
            dv += r["delivValue"]
            pct_sum += r["delivPct"]
            cnt += 1
            if r["delivPct"] > top_pct:
                top_pct = r["delivPct"]
                top_sym = r["symbol"]
        if cnt == 0:
            continue
        out.append({
            "group":           name,
            "count":           cnt,
            "totalTraded":     tt,
            "totalDeliv":      td,
            "totalTurnover":   round(turnover, 2),
            "totalDelivValue": round(dv, 0),
            "delivRatio":      round(td / tt * 100, 2) if tt else 0.0,   # accurate, quantity-weighted
            "avgDelivPct":     round(pct_sum / cnt, 2),                  # simple mean (reference only)
            "topSymbol":       top_sym,
            "topDelivPct":     round(top_pct, 2) if top_pct >= 0 else 0.0,
        })
    out.sort(key=lambda g: g["delivRatio"], reverse=True)
    return out


async def get_sector_delivery() -> tuple[list[dict], Optional[str]]:
    """Quantity-weighted delivery per NSE sector index (FULL membership), so the
    number is stable regardless of any on-screen filter. Each row also carries a
    ``sector`` alias for the group name (drop-in for the insights sector block).
    """
    from ..lib import universe as _u  # noqa: PLC0415 — lazy
    rows, trade_date = await get_delivery_rows()
    groups = {sec: syms for sec, syms in _u.SECTOR_SYMBOLS.items() if syms}
    agg = aggregate_delivery(groups, rows)
    for g in agg:
        g["sector"] = g["group"]
    return agg, trade_date


# ── Per-symbol delivery history (from recent daily bhavcopies) ────────────────
# Historical bhavcopy files are immutable, so per-date parsed maps are cached
# forever. The first history request warms ~N days; every later symbol reuses
# the cached day-maps, so it's cheap thereafter (no per-symbol storage needed).
_DAY_MAP_CACHE: dict[str, dict[str, float]] = {}


async def _delivery_map_for_date(d) -> Optional[dict[str, float]]:
    key = d.strftime("%Y-%m-%d")
    if key in _DAY_MAP_CACHE:
        return _DAY_MAP_CACHE[key]
    from ..services import registry as svc  # noqa: PLC0415
    url = _NSE_BHAVDATA_URL_TPL.format(ddmmyyyy=d.strftime("%d%m%Y"))
    try:
        text = await svc.nse.fetch_nse_archive_text(url, f"bhav-{d.strftime('%d%m%Y')}", ttl=86400)
    except Exception:
        text = None
    if not (text and "SYMBOL" in text[:50] and "DELIV_PER" in text[:300]):
        return None
    m = {r["symbol"]: r["delivPct"] for r in _parse(text)}
    _DAY_MAP_CACHE[key] = m
    return m


async def get_recent_day_maps(days: int = 15, lookback: int = 45) -> list[tuple[str, dict[str, float]]]:
    """Last `days` trading days of {symbol: delivPct}, oldest→newest. Walks back
    up to `lookback` calendar days, skipping weekends/holidays/missing files."""
    out: list[tuple[str, dict[str, float]]] = []
    d = datetime.utcnow().date()
    checked = 0
    while len(out) < days and checked < lookback:
        checked += 1
        if d.weekday() < 5:
            m = await _delivery_map_for_date(d)
            if m:
                out.append((d.isoformat(), m))
        d -= timedelta(days=1)
    out.reverse()
    return out


async def get_symbol_delivery_history(symbol: str, days: int = 40) -> list[dict]:
    """Per-symbol delivery % over the last `days` trading sessions."""
    sym = (symbol or "").upper()
    maps = await get_recent_day_maps(days=days, lookback=days * 2)
    return [{"date": dteiso, "delivPct": m[sym]} for dteiso, m in maps if sym in m]
