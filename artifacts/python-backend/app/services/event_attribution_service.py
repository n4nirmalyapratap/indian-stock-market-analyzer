"""
Event Attribution Service
Detects significant price peaks and troughs in a stock's 5-year history.
Uses the app's internal hydra price cache (no external API calls, no AI).
Results are cached in-process for 24 hours.
"""

import logging

log = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 24 * 3600   # 24 hours


# ── Swing detection ─────────────────────────────────────────────────────────────

def detect_swings(closes: list[float], dates: list[str], min_pct: float = 0.15) -> list[dict]:
    """
    Zigzag-style swing detector.
    Walks through the price series tracking the current trend direction.
    Emits a confirmed peak/trough whenever the reversal exceeds `min_pct`.
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
                prev = events[-1]["price"] if events else closes[0]
                move = (extreme_price - prev) / prev * 100 if prev else 0
                events.append({
                    "date":      dates[extreme_idx],
                    "price":     round(extreme_price, 2),
                    "move_pct":  round(move, 1),
                    "direction": "peak",
                })
                direction     = "down"
                extreme_price = p
                extreme_idx   = i

        else:  # direction == "down"
            if p <= extreme_price:
                extreme_price = p
                extreme_idx   = i
            elif extreme_price > 0 and (p - extreme_price) / extreme_price >= min_pct:
                prev = events[-1]["price"] if events else closes[0]
                move = (extreme_price - prev) / prev * 100 if prev else 0
                events.append({
                    "date":      dates[extreme_idx],
                    "price":     round(extreme_price, 2),
                    "move_pct":  round(move, 1),
                    "direction": "trough",
                })
                direction     = "up"
                extreme_price = p
                extreme_idx   = i

    return events
