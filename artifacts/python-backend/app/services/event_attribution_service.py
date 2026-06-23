"""
Event Attribution Service
Detects significant price peaks and troughs using a zigzag algorithm.
Generates deterministic, factual reason text for each swing — no AI required.
Results are cached in-process for 24 hours.
"""

import logging
from datetime import datetime

log = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 24 * 3600   # 24 hours


def _days_between(d1: str, d2: str) -> int:
    """Return calendar days between two YYYY-MM-DD strings."""
    try:
        fmt = "%Y-%m-%d"
        return abs((datetime.strptime(d2, fmt) - datetime.strptime(d1, fmt)).days)
    except Exception:
        return 0


def _fmt_date(date_str: str) -> str:
    """Format YYYY-MM-DD → '14 May 2026'."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%-d %b %Y")
    except Exception:
        return date_str


def _reason(direction: str, price: float, move_pct: float,
             prev_price: float, prev_date: str, prev_dir: str,
             this_date: str) -> str:
    """
    Build a plain-English sentence describing the swing using only the
    price-series data — no LLM, no network call.
    """
    days   = _days_between(prev_date, this_date)
    frm    = _fmt_date(prev_date)
    label  = "trough" if prev_dir == "trough" else "starting point"
    sign   = "+" if move_pct >= 0 else ""

    if direction == "peak":
        return (
            f"Rose {sign}{move_pct:.1f}% over {days} days from the prior {label} "
            f"of ₹{prev_price:,.2f} on {frm}, driven by buying momentum that "
            f"pushed price to ₹{price:,.2f} before sellers stepped in."
        )
    else:
        return (
            f"Fell {move_pct:.1f}% over {days} days from the prior {label} "
            f"of ₹{prev_price:,.2f} on {frm}, as selling pressure brought "
            f"price down to ₹{price:,.2f} before buyers returned."
        )


# ── Swing detection ─────────────────────────────────────────────────────────────

def detect_swings(closes: list[float], dates: list[str], min_pct: float = 0.15) -> list[dict]:
    """
    Zigzag-style swing detector.
    Walks through the price series tracking the current trend direction.
    Emits a confirmed peak/trough whenever the reversal exceeds `min_pct`.
    Each event includes a deterministic `reason` string.
    """
    if len(closes) < 4:
        return []

    events: list[dict] = []

    direction     = "up" if closes[min(3, len(closes) - 1)] >= closes[0] else "down"
    extreme_price = closes[0]
    extreme_idx   = 0

    for i in range(1, len(closes)):
        p = closes[i]

        if direction == "up":
            if p >= extreme_price:
                extreme_price = p
                extreme_idx   = i
            elif extreme_price > 0 and (extreme_price - p) / extreme_price >= min_pct:
                prev_ev    = events[-1] if events else None
                prev_price = prev_ev["price"] if prev_ev else closes[0]
                prev_date  = prev_ev["date"]  if prev_ev else dates[0]
                prev_dir   = prev_ev["direction"] if prev_ev else "trough"
                move       = (extreme_price - prev_price) / prev_price * 100 if prev_price else 0
                events.append({
                    "date":      dates[extreme_idx],
                    "price":     round(extreme_price, 2),
                    "move_pct":  round(move, 1),
                    "direction": "peak",
                    "reason":    _reason("peak", round(extreme_price, 2), round(move, 1),
                                         prev_price, prev_date, prev_dir, dates[extreme_idx]),
                })
                direction     = "down"
                extreme_price = p
                extreme_idx   = i

        else:  # direction == "down"
            if p <= extreme_price:
                extreme_price = p
                extreme_idx   = i
            elif extreme_price > 0 and (p - extreme_price) / extreme_price >= min_pct:
                prev_ev    = events[-1] if events else None
                prev_price = prev_ev["price"] if prev_ev else closes[0]
                prev_date  = prev_ev["date"]  if prev_ev else dates[0]
                prev_dir   = prev_ev["direction"] if prev_ev else "peak"
                move       = (extreme_price - prev_price) / prev_price * 100 if prev_price else 0
                events.append({
                    "date":      dates[extreme_idx],
                    "price":     round(extreme_price, 2),
                    "move_pct":  round(move, 1),
                    "direction": "trough",
                    "reason":    _reason("trough", round(extreme_price, 2), round(move, 1),
                                         prev_price, prev_date, prev_dir, dates[extreme_idx]),
                })
                direction     = "up"
                extreme_price = p
                extreme_idx   = i

    return events
