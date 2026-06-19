"""Smart Money Concepts (SMC) primitives — single source of truth.

Two consumers (mirrors the `candle_patterns.py` design):
  1. `scanners_service.py` — the user-facing scanner DSL. Uses the boolean
     helpers here as indicators (BULLISH_FVG, BEARISH_FVG, …) so a user can
     write conditions like  BULLISH_FVG eq 1 AND CLOSE > EMA(50).
  2. `routes/stocks.py` `/smc` endpoint — uses the `find_*` functions to return
     zone geometry the chart draws as overlays.

Why one module
--------------
Computing FVGs in Python for the screener and again in TypeScript for the
chart would silently drift ("the screener says there's a gap but the chart
shows none"). Keeping detection here, consumed by both, makes the screener
and the chart agree by construction.

Scope
-----
DAILY-bar, time-agnostic SMC only. ICT session/time concepts (killzones,
Silver Bullet, Judas swing) are intentionally excluded — they need reliable
intraday data the backend doesn't have, and their forex-session clock does
not map to NSE hours. See the integration research for the full rationale.

Convention
----------
Pure functions over the same dict-OHLCV the rest of the app uses:
``{open, high, low, close, volume}``. No external imports (kept dependency-free
like `candle_patterns.py`) so it's trivially testable and reusable.
"""
from __future__ import annotations

from typing import Optional


# ── Shared helpers ───────────────────────────────────────────────────────────


def _avg_range(ohlcv: list[dict], end: int, period: int = 14) -> float:
    """Mean high-low range over the ``period`` bars ending at index ``end``
    (inclusive).

    Used as a scale to filter insignificant gaps/zones so micro-noise on a
    quiet stock doesn't register as a "gap". A simple mean of the bar range is
    a deliberately cheap, dependency-free proxy for ATR — exact ATR precision
    isn't needed for a significance gate.
    """
    start = max(0, end - period + 1)
    rng = [
        c["high"] - c["low"]
        for c in ohlcv[start:end + 1]
        if c.get("high") is not None and c.get("low") is not None
    ]
    return sum(rng) / len(rng) if rng else 0.0


# ── Fair Value Gap (FVG) ─────────────────────────────────────────────────────
# A 3-candle imbalance. Looking at candles (i-2, i-1, i):
#   • Bullish FVG: low[i] > high[i-2] — an up-move left a gap nobody traded
#     through. The zone [high[i-2], low[i]] tends to act as later support.
#   • Bearish FVG: high[i] < low[i-2] — mirror; the zone acts as resistance.
# The middle candle (i-1) is the displacement leg; we don't require a separate
# body filter because the gap itself only exists when i-1 was impulsive.


def fvg_at(ohlcv: list[dict], i: int, *, min_range_mult: float = 0.25) -> Optional[dict]:
    """Detect a Fair Value Gap completing at bar index ``i`` (the 3rd candle
    of the pattern). Returns the FVG dict or ``None``.

    ``min_range_mult`` filters micro-gaps: the gap height must be at least this
    multiple of the recent average bar range (set 0 to disable).

    The returned zone uses ``top`` ≥ ``bottom`` regardless of direction so
    callers can draw a rectangle without re-deriving the ordering.
    """
    if i < 2 or i >= len(ohlcv):
        return None
    c0 = ohlcv[i]          # 3rd candle (where the gap completes)
    c2 = ohlcv[i - 2]      # 1st candle
    try:
        gate = _avg_range(ohlcv, i) * min_range_mult
        if c0["low"] > c2["high"]:
            gap = c0["low"] - c2["high"]
            if gap >= gate:
                return {"type": "bullish", "bottom": c2["high"], "top": c0["low"], "index": i, "size": gap}
        elif c0["high"] < c2["low"]:
            gap = c2["low"] - c0["high"]
            if gap >= gate:
                return {"type": "bearish", "bottom": c0["high"], "top": c2["low"], "index": i, "size": gap}
    except (KeyError, TypeError):
        return None
    return None


def find_fvgs(
    ohlcv: list[dict],
    *,
    min_range_mult: float = 0.25,
    lookback: Optional[int] = None,
    include_mitigated: bool = True,
) -> list[dict]:
    """All Fair Value Gaps in the series, each annotated with mitigation state.

    A gap is *mitigated* once a later bar trades back into the zone — for a
    bullish gap when a later low re-enters from above, for a bearish gap when a
    later high re-enters from below. ``mitigated``/``mitigatedIndex`` are added
    to each dict so the chart can dim consumed zones and the screener can
    filter for fresh ones.

    ``lookback`` limits detection to the last N bars (None = whole series).
    ``include_mitigated=False`` returns only still-open gaps.
    """
    n = len(ohlcv)
    start = 2 if lookback is None else max(2, n - lookback)
    out: list[dict] = []
    for i in range(start, n):
        f = fvg_at(ohlcv, i, min_range_mult=min_range_mult)
        if not f:
            continue
        f["mitigated"] = False
        f["mitigatedIndex"] = None
        for j in range(i + 1, n):
            cj = ohlcv[j]
            if f["type"] == "bullish":
                if cj.get("low") is not None and cj["low"] <= f["top"]:
                    f["mitigated"], f["mitigatedIndex"] = True, j
                    break
            else:
                if cj.get("high") is not None and cj["high"] >= f["bottom"]:
                    f["mitigated"], f["mitigatedIndex"] = True, j
                    break
        if include_mitigated or not f["mitigated"]:
            out.append(f)
    return out


# ── Market structure: swings → BOS / CHoCH ───────────────────────────────────
# Swing pivots are the atom everything structural builds on. A swing high at
# index i is a fractal: its high is strictly greater than the `n` bars on each
# side. It can only be KNOWN n bars later (after the right side prints), so
# detection is causal/lagging by n — the most recent n bars never contain a
# confirmed swing. This is the honest, non-repainting behaviour.


def swing_points(ohlcv: list[dict], n: int = 2) -> tuple[list[dict], list[dict]]:
    """Confirmed fractal swing highs and lows.

    Returns ``(highs, lows)`` where each item is ``{index, price}``. ``n`` is the
    lookback/lookforward (n=2 → the classic 5-bar fractal). Strict inequality on
    both sides, so flat plateaus don't register as swings.
    """
    highs = [c.get("high") for c in ohlcv]
    lows = [c.get("low") for c in ohlcv]
    n_bars = len(ohlcv)
    sh: list[dict] = []
    sl: list[dict] = []
    for i in range(n, n_bars - n):
        hi = highs[i]
        lo = lows[i]
        if hi is not None and all(
            highs[j] is not None and hi > highs[j]
            for j in range(i - n, i + n + 1) if j != i
        ):
            sh.append({"index": i, "price": hi})
        if lo is not None and all(
            lows[j] is not None and lo < lows[j]
            for j in range(i - n, i + n + 1) if j != i
        ):
            sl.append({"index": i, "price": lo})
    return sh, sl


def market_structure(ohlcv: list[dict], n: int = 2) -> list[dict]:
    """Break-of-Structure (BOS) and Change-of-Character (CHoCH) events.

    Walks bars chronologically. A swing only becomes "active" at its confirmation
    bar (``index + n``) — so a break can never be detected before the swing is
    knowable (no lookahead). A candle that CLOSES beyond the most recent active
    swing emits:
      • BOS   — break in the SAME direction as the prevailing trend (continuation)
      • CHoCH — break AGAINST the trend (first reversal signal); flips the trend

    Close-based by design ("wicks don't count"). Returns events:
    ``{index, type: 'bullish'|'bearish', kind: 'BOS'|'CHoCH', level, swingIndex}``.

    Simplification vs strict ICT: a break is measured against the most recent
    confirmed swing (LuxAlgo "internal structure" style), not necessarily the
    swing that produced the previous BOS. Good enough for screening/annotation;
    documented so it isn't mistaken for the stricter variant.
    """
    sh, sl = swing_points(ohlcv, n)
    sh_by_idx = {s["index"]: s["price"] for s in sh}
    sl_by_idx = {s["index"]: s["price"] for s in sl}
    events: list[dict] = []
    trend = 0                         # 1 = up, -1 = down, 0 = undetermined
    last_sh: Optional[tuple] = None   # (index, price) of active (unbroken) swing high
    last_sl: Optional[tuple] = None
    for i in range(len(ohlcv)):
        j = i - n                     # the swing at j (if any) is confirmed now
        if j >= 0:
            if j in sh_by_idx:
                last_sh = (j, sh_by_idx[j])
            if j in sl_by_idx:
                last_sl = (j, sl_by_idx[j])
        close = ohlcv[i].get("close")
        if close is None:
            continue
        if last_sh is not None and close > last_sh[1]:
            kind = "CHoCH" if trend == -1 else "BOS"
            events.append({"index": i, "type": "bullish", "kind": kind,
                           "level": last_sh[1], "swingIndex": last_sh[0]})
            trend = 1
            last_sh = None            # broken — wait for the next swing high
        elif last_sl is not None and close < last_sl[1]:
            kind = "CHoCH" if trend == 1 else "BOS"
            events.append({"index": i, "type": "bearish", "kind": kind,
                           "level": last_sl[1], "swingIndex": last_sl[0]})
            trend = -1
            last_sl = None
    return events


def structure_at(
    ohlcv: list[dict], i: int, n: int = 2, events: Optional[list[dict]] = None,
) -> Optional[dict]:
    """The structure event occurring exactly at bar ``i``, or ``None``.

    Used by the scanner DSL ("did a BOS/CHoCH print on the evaluated bar?"). Pass
    a precomputed ``events`` list to avoid recomputing per indicator on one symbol.
    """
    if i < 0 or i >= len(ohlcv):
        return None
    evs = events if events is not None else market_structure(ohlcv, n)
    for ev in evs:
        if ev["index"] == i:
            return ev
    return None


# ── Order Blocks ─────────────────────────────────────────────────────────────
# An order block is the last opposite-colour candle before the impulsive leg
# that broke structure — the institutional footprint left behind. We anchor OBs
# to confirmed BOS/CHoCH events (high quality: the OB actually caused a break),
# so this reuses the same structure walk. Zone = the OB candle's full range.


def order_blocks(ohlcv: list[dict], n: int = 2, events: Optional[list[dict]] = None) -> list[dict]:
    """Order blocks anchored to structure breaks, with mitigation state.

    Bullish OB = last bearish candle before the up-impulse that broke structure;
    bearish OB = last bullish candle before a down-impulse. Each:
    ``{type, top, bottom, index, createdIndex, mitigated, mitigatedIndex}`` where
    ``index`` is the OB candle and ``createdIndex`` is the break bar (when it
    became valid). Mitigated once price later trades back into the zone.
    """
    evs = events if events is not None else market_structure(ohlcv, n)
    n_bars = len(ohlcv)
    obs: list[dict] = []
    for ev in evs:
        i = ev["index"]
        lo_bound = ev["swingIndex"]
        want_bear = ev["type"] == "bullish"   # bullish break ← last bearish candle
        ob_i = None
        for k in range(i, lo_bound - 1, -1):
            c = ohlcv[k]
            o, cl = c.get("open"), c.get("close")
            if o is None or cl is None:
                continue
            if (want_bear and cl < o) or (not want_bear and cl > o):
                ob_i = k
                break
        if ob_i is None:
            continue
        c = ohlcv[ob_i]
        if c.get("high") is None or c.get("low") is None:
            continue   # malformed bar — skip rather than poison the zone/mitigation
        ob = {
            "type":         ev["type"],
            "top":          c["high"],
            "bottom":       c["low"],
            "index":        ob_i,
            "createdIndex": i,
            "mitigated":    False,
            "mitigatedIndex": None,
        }
        for j in range(i + 1, n_bars):
            cj = ohlcv[j]
            if ev["type"] == "bullish":
                if cj.get("low") is not None and cj["low"] <= ob["top"]:
                    ob["mitigated"], ob["mitigatedIndex"] = True, j
                    break
            else:
                if cj.get("high") is not None and cj["high"] >= ob["bottom"]:
                    ob["mitigated"], ob["mitigatedIndex"] = True, j
                    break
        obs.append(ob)
    return obs


def at_order_block(
    ohlcv: list[dict], i: int, kind: str, n: int = 2, obs: Optional[list[dict]] = None,
) -> bool:
    """True if bar ``i``'s close sits inside an *active* order block of ``kind``
    ('bullish'|'bearish') — i.e. one formed before ``i`` and not yet mitigated
    before ``i``. Screener "price testing demand/supply" filter.
    """
    if i < 0 or i >= len(ohlcv):
        return False
    obs = obs if obs is not None else order_blocks(ohlcv, n)
    c = ohlcv[i].get("close")
    if c is None:
        return False
    for ob in obs:
        if ob["type"] != kind or ob["createdIndex"] >= i:
            continue
        if ob["mitigatedIndex"] is not None and ob["mitigatedIndex"] < i:
            continue
        if ob["bottom"] <= c <= ob["top"]:
            return True
    return False


# ── Liquidity: sweeps + equal highs/lows ─────────────────────────────────────


def liquidity_sweep_at(
    ohlcv: list[dict], i: int, n: int = 2, swings: Optional[tuple] = None,
) -> Optional[str]:
    """Stop-hunt detection at bar ``i``: a wick PIERCES the most recent confirmed
    swing but the bar CLOSES back inside (the key wick-vs-close distinction).

    Returns 'high' (buy-side liquidity swept — bearish reversal cue) or 'low'
    (sell-side swept — bullish cue) or None.
    """
    if i < 0 or i >= len(ohlcv):
        return None
    sh, sl = swings if swings is not None else swing_points(ohlcv, n)
    c = ohlcv[i]
    hi, lo, cl = c.get("high"), c.get("low"), c.get("close")
    if cl is None:
        return None
    rsh = next((s for s in reversed(sh) if s["index"] <= i - n and s["index"] < i), None)
    if rsh and hi is not None and hi > rsh["price"] and cl < rsh["price"]:
        return "high"
    rsl = next((s for s in reversed(sl) if s["index"] <= i - n and s["index"] < i), None)
    if rsl and lo is not None and lo < rsl["price"] and cl > rsl["price"]:
        return "low"
    return None


def equal_levels(
    ohlcv: list[dict], n: int = 2, tol_mult: float = 0.1, swings: Optional[tuple] = None,
) -> tuple[list[dict], list[dict]]:
    """Equal highs / equal lows — clusters of swing extremes within
    ``tol_mult × avg-range`` of each other. These are liquidity pools (equal
    highs = buy-side above, equal lows = sell-side below).

    Returns ``(equal_highs, equal_lows)``; each cluster is
    ``{price, count, indices}`` (price = cluster mean).
    """
    sh, sl = swings if swings is not None else swing_points(ohlcv, n)
    tol = (_avg_range(ohlcv, len(ohlcv) - 1) or 1.0) * tol_mult

    def _cluster(points: list[dict]) -> list[dict]:
        out: list[dict] = []
        used = [False] * len(points)
        for a in range(len(points)):
            if used[a]:
                continue
            grp = [points[a]]
            for b in range(a + 1, len(points)):
                if not used[b] and abs(points[b]["price"] - points[a]["price"]) <= tol:
                    grp.append(points[b])
                    used[b] = True
            if len(grp) >= 2:
                used[a] = True
                out.append({
                    "price":   sum(g["price"] for g in grp) / len(grp),
                    "count":   len(grp),
                    "indices": [g["index"] for g in grp],
                })
        return out

    return _cluster(sh), _cluster(sl)


# ── Premium / Discount (dealing range + equilibrium) ─────────────────────────


def dealing_range(
    ohlcv: list[dict], i: int, n: int = 2, swings: Optional[tuple] = None,
) -> Optional[dict]:
    """The current dealing range from the most recent confirmed swing high & low.

    Returns ``{high, low, eq, highIndex, lowIndex}`` (eq = 0.5 equilibrium) or
    None if a range can't be formed yet.
    """
    sh, sl = swings if swings is not None else swing_points(ohlcv, n)
    rsh = next((s for s in reversed(sh) if s["index"] <= i - n), None)
    rsl = next((s for s in reversed(sl) if s["index"] <= i - n), None)
    if not rsh or not rsl:
        return None
    hi = max(rsh["price"], rsl["price"])
    lo = min(rsh["price"], rsl["price"])
    if hi <= lo:
        return None
    return {"high": hi, "low": lo, "eq": (hi + lo) / 2.0,
            "highIndex": rsh["index"], "lowIndex": rsl["index"]}


def premium_discount_at(
    ohlcv: list[dict], i: int, n: int = 2, swings: Optional[tuple] = None,
) -> Optional[str]:
    """Where bar ``i``'s close sits in the current dealing range:
    'premium' (above equilibrium — favour shorts), 'discount' (below — favour
    longs), 'equilibrium', or None."""
    dr = dealing_range(ohlcv, i, n, swings)
    if not dr:
        return None
    c = ohlcv[i].get("close")
    if c is None:
        return None
    if c > dr["eq"]:
        return "premium"
    if c < dr["eq"]:
        return "discount"
    return "equilibrium"
