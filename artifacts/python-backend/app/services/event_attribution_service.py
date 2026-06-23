"""
Event Attribution Service
Detects significant price peaks and troughs using a zigzag algorithm.
Annotates each event with:
  - context_tags : real calendar context (Budget, RBI, F&O Expiry, Earnings Season)
  - reason       : kept for internal use / backward-compat; not shown in UI
Results are cached in-process for 24 hours.
"""

import calendar as _cal
import logging
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 24 * 3600   # 24 hours


# ── Calendar event helpers ────────────────────────────────────────────────────

# RBI MPC policy outcome days (the day the rate decision is announced).
# Markets react on this day and the next.
_RBI_OUTCOME_DATES = {
    # 2024
    "2024-02-08", "2024-04-05", "2024-06-07",
    "2024-08-08", "2024-10-09", "2024-12-06",
    # 2025
    "2025-02-07", "2025-04-09", "2025-06-06",
    "2025-08-08", "2025-10-09", "2025-12-05",
    # 2026
    "2026-02-07", "2026-04-09", "2026-06-06",
}
_RBI_DT = {datetime.strptime(d, "%Y-%m-%d") for d in _RBI_OUTCOME_DATES}

# Earnings result season: month → quarter label.
# NSE-listed companies report within roughly 45 days of quarter-end.
# Q1 Apr-Jun → results Jul-Aug  |  Q2 Jul-Sep → results Oct-Nov
# Q3 Oct-Dec → results Jan-Feb  |  Q4 Jan-Mar → results Apr-May
_EARNINGS_MONTHS: dict[int, str] = {
    1: "Q3 Results Season", 2: "Q3 Results Season",
    4: "Q4 Results Season", 5: "Q4 Results Season",
    7: "Q1 Results Season", 8: "Q1 Results Season",
    10: "Q2 Results Season", 11: "Q2 Results Season",
}


def _last_thursday(year: int, month: int) -> int:
    """Return the day-of-month of the last Thursday in the given month."""
    last_day = _cal.monthrange(year, month)[1]
    for d in range(last_day, 0, -1):
        if datetime(year, month, d).weekday() == 3:  # Thursday
            return d
    return last_day


def context_tags(date_str: str) -> list[str]:
    """
    Return a list of human-readable market-calendar tags for a YYYY-MM-DD date.
    All data is deterministic — no external API required.
    """
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        return []

    tags: list[str] = []
    m, d, y = dt.month, dt.day, dt.year

    # ── Union Budget (Feb 1 each year) ────────────────────────────────────────
    if m == 2 and 1 <= d <= 3:
        tags.append(f"Union Budget {y}")

    # ── RBI MPC policy decision (±1 day window) ───────────────────────────────
    for rbi_dt in _RBI_DT:
        if abs((dt - rbi_dt).days) <= 1:
            tags.append("RBI MPC Policy Decision")
            break

    # ── NSE F&O monthly expiry (last Thursday ±1 day) ────────────────────────
    last_thu = _last_thursday(y, m)
    if abs(d - last_thu) <= 1:
        tags.append("F&O Monthly Expiry")

    # ── Quarterly results season ──────────────────────────────────────────────
    if m in _EARNINGS_MONTHS and d <= 25:
        tags.append(_EARNINGS_MONTHS[m])

    # ── Interim Budget / Vote-on-Account (Feb of election year — approx) ─────
    # Simplified: flag Feb 1 already covered above by Budget tag.

    # ── Nifty/Sensex half-yearly rebalancing (roughly Jan & Jul) ─────────────
    if m in (1, 7) and 15 <= d <= 31:
        tags.append("Index Rebalancing Window")

    return tags


# ── Swing reason (kept for internal use, not shown in UI) ────────────────────

def _days_between(d1: str, d2: str) -> int:
    try:
        fmt = "%Y-%m-%d"
        return abs((datetime.strptime(d2, fmt) - datetime.strptime(d1, fmt)).days)
    except Exception:
        return 0


def _fmt_date(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%-d %b %Y")
    except Exception:
        return date_str


def _reason(direction: str, price: float, move_pct: float,
             prev_price: float, prev_date: str, prev_dir: str,
             this_date: str) -> str:
    days  = _days_between(prev_date, this_date)
    frm   = _fmt_date(prev_date)
    label = "trough" if prev_dir == "trough" else "starting point"
    sign  = "+" if move_pct >= 0 else ""
    if direction == "peak":
        return (
            f"Rose {sign}{move_pct:.1f}% over {days} days from the prior {label} "
            f"of ₹{prev_price:,.2f} on {frm}."
        )
    return (
        f"Fell {move_pct:.1f}% over {days} days from the prior {label} "
        f"of ₹{prev_price:,.2f} on {frm}."
    )


# ── Swing detection ───────────────────────────────────────────────────────────

def detect_swings(closes: list[float], dates: list[str], min_pct: float = 0.15) -> list[dict]:
    """
    Zigzag-style swing detector.
    Each event includes context_tags (real calendar markers) and reason (price description).
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
                ev_date    = dates[extreme_idx]
                events.append({
                    "date":         ev_date,
                    "price":        round(extreme_price, 2),
                    "move_pct":     round(move, 1),
                    "direction":    "peak",
                    "reason":       _reason("peak", round(extreme_price, 2), round(move, 1),
                                            prev_price, prev_date, prev_dir, ev_date),
                    "context_tags": context_tags(ev_date),
                })
                direction     = "down"
                extreme_price = p
                extreme_idx   = i

        else:
            if p <= extreme_price:
                extreme_price = p
                extreme_idx   = i
            elif extreme_price > 0 and (p - extreme_price) / extreme_price >= min_pct:
                prev_ev    = events[-1] if events else None
                prev_price = prev_ev["price"] if prev_ev else closes[0]
                prev_date  = prev_ev["date"]  if prev_ev else dates[0]
                prev_dir   = prev_ev["direction"] if prev_ev else "peak"
                move       = (extreme_price - prev_price) / prev_price * 100 if prev_price else 0
                ev_date    = dates[extreme_idx]
                events.append({
                    "date":         ev_date,
                    "price":        round(extreme_price, 2),
                    "move_pct":     round(move, 1),
                    "direction":    "trough",
                    "reason":       _reason("trough", round(extreme_price, 2), round(move, 1),
                                            prev_price, prev_date, prev_dir, ev_date),
                    "context_tags": context_tags(ev_date),
                })
                direction     = "up"
                extreme_price = p
                extreme_idx   = i

    return events
