"""sector_rotation_service.py — the "Find Winning Stocks via Sector Rotation"
cockpit backend.

Three capabilities, all built on data the app already produces:
  * RRG (Relative Rotation Graph) — places each sector / sub-industry in
    Leading / Improving / Weakening / Lagging with a rotation tail.
  * Funnel — sectors → sub-industries ranked by rotation strength + delivery.
  * Shortlist — the strongest stocks inside a chosen sub-industry.

This module starts with the RRG math, which is pure and unit-tested. The data
wiring (sub-industry series from synthetic_sector_daily_metrics, sector series
from sector_analytics._yf_history, delivery from delivery_service, constituents
from synthetic drilldown) is layered on top.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import math
import time
from typing import Any, Optional

logger = logging.getLogger("sector_rotation")

# In-memory cache for the expensive RRG/funnel builds (yf + DB). Market-state
# aware, mirroring sector_analytics_service: when the market is CLOSED the
# underlying closes/metrics are frozen until the next session, so we hold for
# hours; when OPEN we keep it short. The whole cache is flushed the moment the
# market state transitions (via market_cache_service.cache_version), so a
# closed-state build can never bleed into the open session.
_cache: dict[str, dict] = {}
_cache_version = 0


def _flush_if_state_changed() -> None:
    """Drop in-memory entries when market state has just transitioned (open↔closed)."""
    global _cache_version, _cache
    from . import market_cache_service as _disk  # noqa: PLC0415
    v = _disk.cache_version()
    if v != _cache_version:
        _cache.clear()
        _cache_version = v


def _cache_get(key: str) -> Optional[Any]:
    _flush_if_state_changed()
    e = _cache.get(key)
    if e and time.time() < e["expiry"]:
        return e["data"]
    return None


def _seconds_until_next_open() -> int:
    """Seconds from now until the next NSE open (next weekday 09:15 IST).

    Used as the closed-market cache TTL so a build done after the close stays
    fresh for the WHOLE closed session instead of rebuilding every few hours
    (the old flat 4h TTL forced repeated cold rebuilds overnight and across
    weekends). The data is frozen between closes, so the only real invalidator
    is the market reopening — and `_flush_if_state_changed` already drops the
    cache precisely on that transition. This bound is the backstop. Skips
    weekends; holidays at worst cause one extra rebuild on the holiday morning.
    """
    from . import market_cache_service as _disk  # noqa: PLC0415
    now = _disk._now_ist()
    nxt = now.replace(hour=9, minute=15, second=0, microsecond=0)
    if now >= nxt:
        nxt += dt.timedelta(days=1)
    while nxt.weekday() >= 5:   # Sat=5, Sun=6 → roll to Monday
        nxt += dt.timedelta(days=1)
    return max(600, int((nxt - now).total_seconds()))


def _cache_set(key: str, data: Any, ttl: Optional[int] = None) -> None:
    _flush_if_state_changed()
    from . import market_cache_service as _disk  # noqa: PLC0415
    if ttl is None:
        ttl = 600 if _disk.is_market_open() else _seconds_until_next_open()
    _cache[key] = {"data": data, "expiry": time.time() + ttl}

# ── RRG math (pure) ──────────────────────────────────────────────────────────

# Quadrant names by (rsRatio>=100, rsMomentum>=100).
_QUADRANTS = {
    (True, True):   "Leading",
    (True, False):  "Weakening",
    (False, False): "Lagging",
    (False, True):  "Improving",
}


def quadrant_for(rs_ratio: float, rs_momentum: float) -> str:
    return _QUADRANTS[(rs_ratio >= 100.0, rs_momentum >= 100.0)]


def _rolling_zscored_100(series: list[float], window: int) -> list[Optional[float]]:
    """Map a raw series to a 100-centred, z-scored series over a trailing window.

    value_t = 100 + (x_t - mean(window))/std(window). Returns None for the
    leading positions that don't yet have a full window, and 100.0 when the
    window has zero variance (flat) so the point sits neutrally on the axis.
    """
    out: list[Optional[float]] = []
    for i in range(len(series)):
        if i + 1 < window:
            out.append(None)
            continue
        win = series[i + 1 - window: i + 1]
        mean = sum(win) / window
        var = sum((v - mean) ** 2 for v in win) / window
        std = math.sqrt(var)
        out.append(100.0 if std == 0 else 100.0 + (series[i] - mean) / std)
    return out


def compute_rrg(
    entity_series: list[tuple[str, float]],
    benchmark_series: list[tuple[str, float]],
    *,
    smooth: int = 10,
    tail: int = 10,
    sample_every: int = 5,
) -> Optional[dict]:
    """Simplified JdK RS-Ratio / RS-Momentum for one entity vs a benchmark.

    Inputs are ``[(date_iso, value), ...]`` ascending (daily). Steps:
      rs_t        = entity_t / benchmark_t           (date-aligned)
      rsRatio_t   = 100 + zscore(rs, trailing `smooth`)
      mom_t       = rsRatio_t - rsRatio_{t-1}
      rsMomentum_t= 100 + zscore(mom, trailing `smooth`)

    Returns the latest ``{rsRatio, rsMomentum, quadrant}`` plus a ``tail`` of the
    last ``tail`` points sampled every ``sample_every`` days (≈weekly), or None
    when there isn't enough aligned history.
    """
    bench = {d: v for d, v in benchmark_series if v}
    aligned = [(d, v / bench[d]) for d, v in entity_series if v and d in bench and bench[d]]
    if len(aligned) < smooth + 2:
        return None
    dates = [d for d, _ in aligned]
    rs = [v for _, v in aligned]

    rs_ratio = _rolling_zscored_100(rs, smooth)
    # Momentum = first difference of rsRatio (only where rsRatio is defined).
    mom_raw: list[Optional[float]] = [None]
    for i in range(1, len(rs_ratio)):
        a, b = rs_ratio[i], rs_ratio[i - 1]
        mom_raw.append((a - b) if (a is not None and b is not None) else None)
    # z-score the defined momentum points.
    defined = [(i, m) for i, m in enumerate(mom_raw) if m is not None]
    rs_mom: list[Optional[float]] = [None] * len(mom_raw)
    if len(defined) >= smooth:
        vals = [m for _, m in defined]
        z = _rolling_zscored_100(vals, smooth)
        for (orig_i, _), zz in zip(defined, z):
            rs_mom[orig_i] = zz

    # Collect points where BOTH ratio and momentum are defined.
    pts = [
        {"date": dates[i], "rsRatio": round(rs_ratio[i], 2), "rsMomentum": round(rs_mom[i], 2),
         "quadrant": quadrant_for(rs_ratio[i], rs_mom[i])}
        for i in range(len(dates))
        if rs_ratio[i] is not None and rs_mom[i] is not None
    ]
    if not pts:
        return None

    sampled = pts[::sample_every]
    # Always include the most recent point even if sampling skipped it.
    if sampled[-1]["date"] != pts[-1]["date"]:
        sampled.append(pts[-1])
    tail_pts = sampled[-tail:]
    latest = pts[-1]
    return {
        "rsRatio": latest["rsRatio"],
        "rsMomentum": latest["rsMomentum"],
        "quadrant": latest["quadrant"],
        "tail": tail_pts,
    }


# ── Shortlist scoring (pure) ─────────────────────────────────────────────────

def _norm(x: Optional[float], lo: float, hi: float) -> float:
    """Min-max normalise to 0..1; neutral 0.5 when the range is degenerate,
    0.0 when the value is missing."""
    if x is None:
        return 0.0
    if hi <= lo:
        return 0.5
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


def rank_shortlist(raw_rows: list[dict]) -> list[dict]:
    """Rank constituents into a 'winning stocks' shortlist (pure, unit-tested).

    Each raw row carries: symbol, name, rs (relative strength %, stock minus
    benchmark), delivPct, aboveTrend (bool|None), marketCapWeight. We min-max
    normalise rs and delivPct ACROSS the set, then score:
        score = 100 * (0.5*rs_n + 0.3*deliv_n + 0.2*trend_bonus)
    Sorted by score desc. Transparent + deterministic for a given set.
    """
    rs_vals = [r["rs"] for r in raw_rows if r.get("rs") is not None]
    dp_vals = [r["delivPct"] for r in raw_rows if r.get("delivPct") is not None]
    rs_lo, rs_hi = (min(rs_vals), max(rs_vals)) if rs_vals else (0.0, 0.0)
    dp_lo, dp_hi = (min(dp_vals), max(dp_vals)) if dp_vals else (0.0, 0.0)
    out: list[dict] = []
    for r in raw_rows:
        rs_n = _norm(r.get("rs"), rs_lo, rs_hi)
        dp_n = _norm(r.get("delivPct"), dp_lo, dp_hi)
        trend = 1.0 if r.get("aboveTrend") else 0.0
        score = round(100.0 * (0.5 * rs_n + 0.3 * dp_n + 0.2 * trend), 1)
        out.append({**r, "score": score})
    out.sort(key=lambda r: r["score"], reverse=True)
    return out


def _ema_last(values: list[float], span: int) -> Optional[float]:
    if len(values) < span:
        return None
    k = 2.0 / (span + 1.0)
    ema = sum(values[:span]) / span
    for v in values[span:]:
        ema = v * k + ema * (1 - k)
    return ema


def _pct_return(closes: list[float], lookback: int) -> Optional[float]:
    if len(closes) <= lookback or closes[-1 - lookback] == 0:
        return None
    return (closes[-1] / closes[-1 - lookback] - 1.0) * 100.0


# ── Timeframes ───────────────────────────────────────────────────────────────
# One control unifies the two old views: long ≈ the Market-Sectors strength page
# (6-month trend), short = early rotation. `lookback` is trading days for the RS%
# ranking; `smooth` is the RRG z-score window.
TIMEFRAMES: dict[str, dict] = {
    "short": {"lookback": 21,  "smooth": 10, "label": "1M"},
    "mid":   {"lookback": 63,  "smooth": 16, "label": "3M"},
    "long":  {"lookback": 126, "smooth": 26, "label": "6M"},
}


def _tf(timeframe: Optional[str]) -> dict:
    return TIMEFRAMES.get((timeframe or "short").lower(), TIMEFRAMES["short"])


def _rs_pct(entity_series: list[tuple], bench_series: list[tuple], lookback: int) -> Optional[float]:
    """Relative strength over the window = entity return − benchmark return, via
    the date-aligned RS ratio (entity/bench). Positive ⇒ outperforming Nifty."""
    bench = {d: v for d, v in bench_series if v}
    al = [(d, v / bench[d]) for d, v in entity_series if v and d in bench and bench[d]]
    if len(al) < 2:
        return None
    lb = min(lookback, len(al) - 1)   # degrade to available history so the bar still fills
    now, then = al[-1][1], al[-1 - lb][1]
    if not then:
        return None
    return round((now / then - 1.0) * 100.0, 2)


# ── Strength (composite) logic — the other lens (matches the Market Sectors page) ──
TIER_LABELS = {
    "DEEP_GREEN": "Deep Green", "LIGHT_GREEN": "Light Green", "YELLOW": "Neutral",
    "ORANGE": "Weakening", "DEEP_RED": "Deep Red",
}


def _tier_for_score(s: float) -> str:
    if s >= 70: return "DEEP_GREEN"
    if s >= 58: return "LIGHT_GREEN"
    if s >= 45: return "YELLOW"
    if s >= 32: return "ORANGE"
    return "DEEP_RED"


def _subind_strength(rs30d: Optional[float], breadth: Optional[float]) -> tuple[float, str]:
    """Composite strength for a sub-industry (no 200-DMA feed): blend 50-EMA
    breadth with 30-day relative strength → 0..100 score + tier. Approximation."""
    rs = rs30d if rs30d is not None else 0.0
    br = breadth if breadth is not None else 50.0
    score = round(0.5 * br + 0.5 * max(0.0, min(100.0, 50.0 + rs)), 1)
    return score, _tier_for_score(score)


async def _attach_sector_strength(entities: list[dict]) -> None:
    """Attach the Market-Sectors composite (score + tier) to each sector entity,
    so 'Strength' mode is the SAME data as the Market Sectors page (single
    source of truth). Joined by NSE index name; unmatched sectors stay None."""
    from . import registry as svc  # noqa: PLC0415
    try:
        rot = await svc.sectors.get_sector_rotation()
    except Exception:
        return
    smap: dict[str, dict] = {}
    for s in rot.get("sectors", []):
        mom = s.get("momentum") or {}
        for key in (s.get("symbol"), s.get("name")):
            if key:
                smap[str(key).strip().upper()] = mom
    for e in entities:
        mom = smap.get(str(e.get("name", "")).strip().upper())
        if mom:
            # sectors_service names the composite momentum score "composite".
            e["strengthScore"] = mom.get("composite")
            e["tier"] = mom.get("tier")


# ── RRG wiring ───────────────────────────────────────────────────────────────

async def sector_rrg(timeframe: str = "short") -> dict:
    """RRG + RS%-over-timeframe for the ~14 NSE sector indices vs Nifty 50, from
    Yahoo index history (disk-EOD-first). Ranked by RS% over the timeframe, so
    'long' matches the Market-Sectors strength view and 'short' shows rotation."""
    tf = _tf(timeframe)
    cache_key = f"rrg:sector:{timeframe}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    from . import sector_analytics_service as _sa  # noqa: PLC0415

    bench = await _sa._yf_history("^NSEI", "1y")
    bench_series = [(r["date"], r["close"]) for r in bench if r.get("close")]
    if not bench_series:
        return {"level": "sector", "available": False, "entities": []}

    names = [n for n in _sa.SECTOR_YAHOO_TICKER if n != "NIFTY 50"]
    hists = await asyncio.gather(
        *[_sa._yf_history(_sa.SECTOR_YAHOO_TICKER[n], "1y") for n in names],
        return_exceptions=True,
    )
    entities = []
    for name, hist in zip(names, hists):
        if isinstance(hist, Exception) or not hist:
            continue
        ent_series = [(r["date"], r["close"]) for r in hist if r.get("close")]
        rrg = compute_rrg(ent_series, bench_series, smooth=tf["smooth"])
        if rrg:
            entities.append({"name": name, **rrg,
                             "rsPct": _rs_pct(ent_series, bench_series, tf["lookback"])})
    # Rank by RS% over the timeframe (intuitive strength); RRG quadrant is the
    # rotation overlay. None rsPct sinks to the bottom.
    entities.sort(key=lambda e: (e.get("rsPct") is not None, e.get("rsPct") or -1e9), reverse=True)
    # Confluence: attach the Market-Sectors composite (the 'Strength' lens).
    await _attach_sector_strength(entities)

    # Auto-inject curated sectors from _EXTRA_SECTOR_MAP that have no NSE Yahoo
    # ticker. Compute on-the-fly RS% from their constituent stocks (equal-weight)
    # so they appear with real gaining/fading/quadrant data, not "no data yet".
    from ..lib import sector_utils as _su_rrg  # noqa: PLC0415
    covered = {_su_rrg.classify_sector(e["name"]) for e in entities}
    uncovered = [c for c in _su_rrg.get_all_extra_sectors() if c not in covered]
    if uncovered and bench_series:
        otf = await _curated_sector_rrg_onthefly(uncovered, bench_series, tf, timeframe)
        entities.extend(otf)

    out = {"level": "sector", "available": True, "benchmark": "NIFTY 50",
           "timeframe": timeframe, "entities": entities}
    _cache_set(cache_key, out)
    return out



async def subindustry_rrg(timeframe: str = "short") -> dict:
    """RRG + RS%-over-timeframe for curated sub-industries vs Nifty 50.

    Single source of truth: _EXTRA_SUBSECTOR_MAP in sector_utils.py.
    To add or change a sub-industry, edit that map only — no DB migration,
    no SUBSECTOR_TAXONOMY entry, no separate seeding step required.

    Computation mirrors the curated-sector path: deep Nifty history fetched
    once (disk-first when market is closed), then equal-weight price series
    built per sub-industry from its constituent stocks.
    Ranked by RS% over the selected timeframe.
    """
    tf = _tf(timeframe)
    cache_key = f"rrg:subindustry:{timeframe}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    from ..lib import sector_utils as _su_si  # noqa: PLC0415
    t0 = time.perf_counter()

    all_subs = _su_si.get_all_extra_subsectors()
    if not all_subs:
        return {"level": "subindustry", "available": False, "entities": [],
                "note": "No sub-industries defined in _EXTRA_SUBSECTOR_MAP."}

    # Deep Nifty benchmark — disk-first, zero network I/O when market is closed.
    needed = tf["lookback"] + tf["smooth"] * 2 + 5
    _nifty_raw = await _deep_history("^NSEI", 320, needed, asyncio.Semaphore(2))
    if not _nifty_raw:
        return {"level": "subindustry", "available": False, "entities": [],
                "note": "Nifty benchmark unavailable — try again after a market close."}
    bench_series = [(d, v) for d, v in _nifty_raw]

    entities = await _curated_sector_rrg_onthefly(
        all_subs, bench_series, tf, timeframe,
        sym_getter=_su_si.get_subsector_symbols,
    )

    entities.sort(key=lambda e: (e.get("rsPct") is not None, e.get("rsPct") or -1e9), reverse=True)

    note = None if entities else (
        "Rotation graph unavailable — constituent price history could not be "
        "fetched. Try again after a market close."
    )
    out = {
        "level": "subindustry",
        "available": bool(entities),
        "benchmark": "NIFTY 50",
        "timeframe": timeframe,
        "entities": entities,
        "note": note,
        "diag": {"subs": len(all_subs), "rendered": len(entities),
                 "benchPoints": len(bench_series), "source": "curated"},
    }
    logger.info("subindustry_rrg tf=%s subs=%d rendered=%d in %.2fs",
                timeframe, len(all_subs), len(entities), time.perf_counter() - t0)
    _cache_set(cache_key, out)
    return out


async def _deep_history(symbol: str, days: int, needed: int, sem) -> list[tuple]:
    """REAL price history. Force a deep provider pull when the disk cache is too
    shallow for the requested window — this is the 'deepen now' path: it bypasses
    the thin EOD cache, fetches ~`days` from the provider chain, and re-caches it
    deep so every later read (any timeframe, anywhere in the app) is fast.
    Returns [(date_iso, close)]. No fabrication — empty on genuine failure."""
    from . import registry as svc                    # noqa: PLC0415
    from . import market_cache_service as _disk       # noqa: PLC0415
    async with sem:
        good: list = []
        try:
            h = await svc.price.get_historical_data(symbol, days)
            good = [b for b in (h or []) if b.get("close")]
            # Force a live deepen ONLY while the market is open. When closed the
            # sealed disk EOD cache is authoritative and complete, so a
            # force_refresh would just storm the (NSE-blocked / slow-Yahoo)
            # providers for every constituent inside the request — the cause of
            # the cold-build hang. Serve what's on disk instead.
            if len(good) < needed and _disk.is_market_open():
                h2 = await svc.price.get_historical_data(symbol, days, force_refresh=True)
                g2 = [b for b in (h2 or []) if b.get("close")]
                if len(g2) > len(good):
                    good = g2
        except Exception:
            good = []
    return [(b["date"], b["close"]) for b in good]


def _ema_series(closes: list[float], period: int) -> list[float]:
    """Exponential moving average — same kernel used by the NSE breadth model."""
    if not closes:
        return []
    k = 2.0 / (period + 1)
    out = [closes[0]]
    for p in closes[1:]:
        out.append(p * k + out[-1] * (1 - k))
    return out


def _curated_composite(rs_pct: Optional[float], breadth_pct: Optional[float]) -> tuple[Optional[float], Optional[str]]:
    """Blend 50-EMA breadth with RS% into the same -1→+1 composite scale the
    NSE Market-Sectors model uses, so curated and indexed sectors are directly
    comparable on the leaderboard bar chart.

    breadth_pct : 0..100  (% of constituents above their 50-EMA)
    rs_pct      : signed %, e.g. +3.2 means 3.2 pp outperformance vs Nifty
    """
    rs_score = (rs_pct / 15.0) if rs_pct is not None else 0.0
    br_score = ((breadth_pct - 50.0) / 50.0) if breadth_pct is not None else rs_score
    composite = round(0.5 * rs_score + 0.5 * br_score, 4)
    if composite >= 0.20:
        tier = "DEEP_GREEN"
    elif composite >= 0.05:
        tier = "LIGHT_GREEN"
    elif composite >= -0.05:
        tier = "YELLOW"
    elif composite >= -0.20:
        tier = "ORANGE"
    else:
        tier = "DEEP_RED"
    return composite, tier


async def _curated_sector_rrg_onthefly(
    sectors: list[str],
    bench_series: list[tuple],
    tf: dict,
    timeframe: str = "short",
    sym_getter=None,
) -> list[dict]:
    """Compute RS/RRG + real breadth on-the-fly for curated sectors/sub-industries
    that have no NSE Yahoo ticker.  Uses the top-N constituents from
    _EXTRA_SECTOR_MAP (or _EXTRA_SUBSECTOR_MAP when sym_getter is provided).
    Breadth = % of stocks above their 50-EMA, computed from the same price
    bars already fetched for the RS calculation — no extra API calls.
    Returns a list of RRG entity dicts — same shape as Yahoo-sourced entities."""
    from ..lib import sector_utils as _su  # noqa: PLC0415
    from ..lib.symbol_map import canonical_symbol  # noqa: PLC0415

    _get_syms = sym_getter or _su.get_sector_symbols

    tf_obj = _tf(timeframe)
    needed = tf_obj["lookback"] + tf_obj["smooth"] * 2 + 5
    fetch_sem = asyncio.Semaphore(6)
    sector_sem = asyncio.Semaphore(4)

    async def _one(canon: str) -> Optional[dict]:
        async with sector_sem:
            syms = [canonical_symbol(s) for s in _get_syms(canon)][:8]
            if not syms:
                return None
            hists = await asyncio.gather(
                *[_deep_history(s, 320, needed, fetch_sem) for s in syms],
                return_exceptions=True,
            )

        good_hists: list[list[tuple]] = []
        maps = []
        for h in hists:
            if isinstance(h, Exception) or not h or len(h) < 30:
                continue
            base = h[0][1]
            if not base:
                continue
            good_hists.append(h)
            maps.append({d: c / base * 100.0 for d, c in h})

        if not maps:
            return None

        # ── Equal-weight index series for RRG ────────────────────────────
        all_dates = sorted({d for m in maps for d in m})
        series = [
            (d, sum(m[d] for m in maps if d in m) / sum(1 for m in maps if d in m))
            for d in all_dates
        ]
        rrg = compute_rrg(series, bench_series, smooth=tf_obj["smooth"])
        if not rrg:
            return None
        rs_pct = _rs_pct(series, bench_series, tf_obj["lookback"])

        # ── 50-EMA breadth — same bars, no extra fetch ───────────────────
        above = 0
        total = 0
        for h in good_hists:
            closes = [c for _, c in h if c]
            if len(closes) < 50:
                continue
            ema50 = _ema_series(closes, 50)
            total += 1
            if closes[-1] > ema50[-1]:
                above += 1
        breadth_pct: Optional[float] = (above / total * 100.0) if total > 0 else None

        composite, tier = _curated_composite(rs_pct, breadth_pct)
        return {
            "name": canon, **rrg,
            "rsPct": rs_pct,
            "breadth50emaPct": breadth_pct,
            "strengthScore": composite,
            "tier": tier,
            "curated": True,
        }

    results = await asyncio.gather(*[_one(s) for s in sectors], return_exceptions=True)
    return [r for r in results if isinstance(r, dict)]



async def get_rrg(level: str = "sector", timeframe: str = "short") -> dict:
    return await (subindustry_rrg(timeframe) if level == "subindustry" else sector_rrg(timeframe))


async def prewarm(timeframe: str = "short") -> dict:
    """Pre-build caches for a single timeframe (funnel + subindustry RRG).
    Safe to call repeatedly — later calls are cache hits."""
    out: dict[str, bool] = {}
    for label, coro in (("funnel", funnel(timeframe)), ("subindustry", subindustry_rrg(timeframe))):
        try:
            await coro
            out[label] = True
        except Exception as exc:  # noqa: BLE001 — pre-warm is best-effort
            logger.warning("rotation prewarm %s/%s failed: %s", label, timeframe, exc)
            out[label] = False
    return out


async def prewarm_all() -> dict:
    """Pre-build caches for ALL three timeframes (short/mid/long) in parallel.
    Runs each timeframe's funnel+subindustry concurrently so total time ≈ one
    timeframe instead of three sequential builds (~20s vs ~60s)."""
    results = await asyncio.gather(
        prewarm("short"),
        prewarm("mid"),
        prewarm("long"),
        return_exceptions=True,
    )
    labels = ("short", "mid", "long")
    out: dict[str, Any] = {}
    for tf, res in zip(labels, results):
        if isinstance(res, Exception):
            logger.warning("rotation prewarm_all %s failed: %s", tf, res)
            out[tf] = False
        else:
            out[tf] = res
    return out


# ── Funnel ───────────────────────────────────────────────────────────────────

async def funnel(timeframe: str = "short") -> dict:
    """Top-down feed: NSE sectors (RRG quadrant + RS%-over-timeframe + accurate
    quantity-weighted delivery) and the sub-industry grid."""
    cache_key = f"funnel:{timeframe}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    from . import synthetic_sectors_service as _syn   # noqa: PLC0415
    from . import delivery_service as _deliv          # noqa: PLC0415

    srrg = await sector_rrg(timeframe)
    sect_deliv, deliv_date = await _deliv.get_sector_delivery()
    deliv_by_sector = {d["sector"]: d for d in sect_deliv}

    sectors = []
    for e in srrg.get("entities", []):
        d = deliv_by_sector.get(e["name"]) or {}
        sectors.append({
            **e,
            "delivRatio": d.get("delivRatio"),
            "topSymbol": d.get("topSymbol"),
            "topDelivPct": d.get("topDelivPct"),
        })

    grid = await asyncio.to_thread(_syn.get_grid)
    out = {
        "sectors": sectors,
        "subIndustries": grid.get("rows", []),
        "timeframe": timeframe,
        "asOf": grid.get("asOf"),
        "deliveryDate": deliv_date,
    }
    _cache_set(cache_key, out)
    return out


# ── Shortlist (winning stocks in a sub-industry) ─────────────────────────────

async def shortlist(sub_industry: Optional[str] = None, sector: Optional[str] = None,
                    timeframe: str = "short", concurrency: int = 20) -> dict:
    """Rank a group's constituents into a winning-stocks shortlist — relative
    strength (stock ~1mo return minus Nifty), delivery %, and an above-50-EMA
    trend flag → composite score. The group is either a sub-industry (synthetic
    drilldown) or an NSE sector index (SECTOR_SYMBOLS membership).

    For sectors the universe is capped at _SECTOR_SHORTLIST_CAP symbols to
    keep response time under ~3 s.  NSE live-index members (large-caps) are
    always included first; the curated extra-map fills the remaining slots.
    """
    _SECTOR_SHORTLIST_CAP = 50   # max symbols fetched per sector click
    tf_obj = _tf(timeframe)
    rs_lookback = tf_obj["lookback"]   # 21 / 63 / 126 for short / mid / long

    # Fast path — return cached result if still fresh (keyed per timeframe)
    _ck = f"shortlist:{'sector' if sector else 'sub'}:{sector or sub_industry}:{timeframe}"
    _hit = _cache_get(_ck)
    if _hit is not None:
        return _hit

    from . import synthetic_sectors_service as _syn       # noqa: PLC0415
    from . import delivery_service as _deliv              # noqa: PLC0415
    from . import sector_analytics_service as _sa         # noqa: PLC0415
    from . import registry as svc                         # noqa: PLC0415
    from ..lib.symbol_map import canonical_symbol         # noqa: PLC0415
    from ..lib import universe as _u                      # noqa: PLC0415

    from ..lib import sector_utils as _su  # noqa: PLC0415

    if sector:
        label, kind = sector, "sector"
        # NSE index members first (large-caps from live index) — always included
        nse_syms: set[str] = {
            s.replace(".NS", "").replace(".BO", "")
            for s in _u.SECTOR_SYMBOLS.get(sector, [])
        }
        raw_consts = [{"symbol": s, "name": s, "weightPct": None} for s in nse_syms]
        # Curated extra-map — fill remaining slots up to the cap
        slots_left = _SECTOR_SHORTLIST_CAP - len(raw_consts)
        if slots_left > 0:
            for sym in _su.get_sector_symbols(sector):
                if sym not in nse_syms:
                    raw_consts.append({"symbol": sym, "name": sym, "weightPct": None})
                    slots_left -= 1
                    if slots_left <= 0:
                        break
    else:
        label, kind = (sub_industry or ""), "subindustry"
        dd = await asyncio.to_thread(_syn.get_drilldown, sub_industry, svc.yahoo)
        raw_consts = list(dd.get("constituents", []))
        # Centralized map — symbols tagged to this sub-industry in _EXTRA_SUBSECTOR_MAP
        db_syms: set[str] = {c["symbol"] for c in raw_consts}
        for sym in _su.get_subsector_symbols(sub_industry):
            if sym not in db_syms:
                raw_consts.append({"symbol": sym, "name": sym, "weightPct": None})
    if not raw_consts:
        return {"group": label, "kind": kind, "available": False, "stocks": []}

    # Canonicalise via the central symbol_map (fixes stale aliases like KAJARIA →
    # KAJARIACER) and dedupe so dead symbols don't surface as blank rows.
    seen: set[str] = set()
    canon: list[dict] = []
    for c in raw_consts:
        raw = (c.get("symbol") or "").strip()
        if not raw:
            continue
        csym = canonical_symbol(raw)
        if csym in seen:
            continue
        seen.add(csym)
        canon.append({
            "symbol": csym,
            "name": c.get("name") or csym,
            "weightPct": c.get("weightPct"),
        })

    # Recent delivery day-maps (shared, cached) → latest snapshot + per-stock trend.
    day_maps = await _deliv.get_recent_day_maps(days=12)
    deliv_map = day_maps[-1][1] if day_maps else {}
    # Benchmark return over the selected timeframe window for relative strength.
    # short=1M→3mo history, mid=3M→6mo, long=6M→1y
    _hist_period = {"short": "3mo", "mid": "6mo", "long": "1y"}.get(timeframe, "3mo")
    nifty = await _sa._yf_history("^NSEI", _hist_period)
    nifty_closes = [r["close"] for r in nifty if r.get("close")]
    nifty_ret = _pct_return(nifty_closes, rs_lookback)

    from . import market_cache_service as _disk  # noqa: PLC0415
    _market_closed = not _disk.is_market_open()

    sem = asyncio.Semaphore(max(1, concurrency))

    # Depth needed: lookback + 50 (for EMA50) + small buffer.
    _fetch_days = max(120, rs_lookback + 60)

    async def _one(c: dict) -> dict:
        sym = c["symbol"]
        # When market is closed, try the disk cache first regardless of
        # eodSealed status — prices are frozen and any data on disk for
        # today's trading date is valid.  This mirrors _yf_history's
        # pattern and avoids all yfinance network calls on closed days.
        h: list[dict] = []
        if _market_closed:
            disk_rows = _disk.load_from_disk(sym, _fetch_days)
            if disk_rows:
                h = disk_rows
        if not h:
            async with sem:
                try:
                    h = await svc.price.get_historical_data(sym, _fetch_days)
                except Exception:
                    h = []
        closes = [b["close"] for b in (h or []) if b.get("close")]
        stock_ret = _pct_return(closes, rs_lookback)
        rs = (stock_ret - nifty_ret) if (stock_ret is not None and nifty_ret is not None) else None
        ema50 = _ema_last(closes, 50)
        above = (closes[-1] > ema50) if (ema50 is not None and closes) else None
        trend = [m.get(sym) for _, m in day_maps if m.get(sym) is not None]
        return {
            "symbol": sym,
            "name": c.get("name"),
            "rs": round(rs, 2) if rs is not None else None,
            "delivPct": deliv_map.get(sym),
            "delivTrend": [round(t, 1) for t in trend],
            "aboveTrend": above,
            "marketCapWeight": c.get("weightPct"),
        }

    raw = await asyncio.gather(*[_one(c) for c in canon])
    # Drop rows with NO usable data at all — dead/bogus tickers would otherwise
    # show as blank "RS — Del — 0" noise.
    usable = [r for r in raw
              if r and (r["rs"] is not None or r["delivPct"] is not None or r["aboveTrend"] is not None)]
    ranked = rank_shortlist(usable)
    out = {"group": label, "kind": kind, "available": True,
           "benchmark": "NIFTY 50", "stocks": ranked,
           "diag": {"constituents": len(raw_consts), "scored": len(usable),
                    "dropped": len(canon) - len(usable)}}
    _cache_set(_ck, out)
    return out
