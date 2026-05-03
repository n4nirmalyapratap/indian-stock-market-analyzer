"""
sebi_registry.py — Single source of truth for SEBI/NSE/BSE rule data.

Provides date-aware lookups for:
  - Lot sizes (with effective date + circular reference)
  - Monthly expiry weekday per symbol
  - Strike step (NSE convention)
  - NSE trading-holiday calendar (2023-2026)
  - Cost schedule (STT, SEBI charge, exchange charge, stamp, GST, brokerage)

All public helpers accept an `on_date` parameter; when omitted, today's
effective rule is returned.  Each rule record carries a `circular_ref`
pointing back to the SEBI/exchange notice that created it, so the
compliance endpoint can show "where this number comes from".
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional


# ── Lot size history ─────────────────────────────────────────────────────────
# Each rule has an effective_from date (inclusive) and effective_to (exclusive,
# None = open-ended).  Latest rule with on_date in [from, to) wins.

@dataclass(frozen=True)
class LotSizeRule:
    symbol: str
    lot_size: int
    effective_from: date
    effective_to: Optional[date]
    circular_ref: str
    notes: str = ""


# Symbols are stored in their canonical (upper) form.  Index aliases (^NSEI etc.)
# are resolved through SYMBOL_ALIASES below before lookup.
LOT_SIZE_RULES: list[LotSizeRule] = [
    # NIFTY 50 — current 75 (revised from 50, then 25, then 75 over the years)
    LotSizeRule("NIFTY",      75, date(2023,  4, 28), None,
                "NSE/FAOP/56321 (2023-04)",
                "Quarterly lot revision under SEBI master circular"),
    LotSizeRule("BANKNIFTY",  30, date(2024, 11, 25), None,
                "NSE/FAOP/63112 (2024-10)",
                "Lot revision aligned with notional value Rs 15-20 lakh"),
    LotSizeRule("BANKNIFTY",  15, date(2023,  7,  1), date(2024, 11, 25),
                "NSE/FAOP/57122 (2023-06)",
                "Earlier lot size before Nov 2024 revision"),
    LotSizeRule("FINNIFTY",   65, date(2024, 11, 25), None,
                "SEBI/HO/MRD/MRD-PoD-2/P/CIR/2024/113",
                "Tighter framework for index derivatives"),
    LotSizeRule("FINNIFTY",   40, date(2023,  4, 28), date(2024, 11, 25),
                "NSE/FAOP/56321 (2023-04)", ""),
    LotSizeRule("MIDCPNIFTY", 120, date(2024, 11, 25), None,
                "SEBI/HO/MRD/MRD-PoD-2/P/CIR/2024/113",
                "Tighter framework for index derivatives"),
    LotSizeRule("MIDCPNIFTY",  75, date(2023,  4, 28), date(2024, 11, 25),
                "NSE/FAOP/56321 (2023-04)", ""),
    LotSizeRule("SENSEX",     10, date(2024,  4,  1), None,
                "BSE/Notice 20240315-26",
                "BSE F&O lot revision"),
    LotSizeRule("BANKEX",     15, date(2024,  4,  1), None,
                "BSE/Notice 20240315-26", ""),
]


# Aliases — every yfinance / NSE / BSE symbol that maps to the canonical name.
SYMBOL_ALIASES: dict[str, str] = {
    "NIFTY":                "NIFTY",
    "NIFTY50":              "NIFTY",
    "^NSEI":                "NIFTY",
    "BANKNIFTY":            "BANKNIFTY",
    "^NSEBANK":             "BANKNIFTY",
    "FINNIFTY":             "FINNIFTY",
    "^CNXFIN":              "FINNIFTY",
    "NIFTY_FIN_SERVICE.NS": "FINNIFTY",
    "MIDCPNIFTY":           "MIDCPNIFTY",
    "^NSMIDCP":             "MIDCPNIFTY",
    "SENSEX":               "SENSEX",
    "^BSESN":               "SENSEX",
    "BANKEX":               "BANKEX",
    "BANKEX.BO":            "BANKEX",
    "^BSXN":                "BANKEX",
}


def canonical_symbol(symbol: str) -> str:
    """Resolve any alias to the canonical key used in rule tables."""
    return SYMBOL_ALIASES.get(symbol.upper(), symbol.upper())


def get_lot_size_on(symbol: str, on_date: Optional[date] = None) -> Optional[LotSizeRule]:
    """Return the LotSizeRule effective on `on_date` (defaults to today).

    Returns None if no rule covers the symbol on that date.
    """
    canon = canonical_symbol(symbol)
    target = on_date or date.today()
    matching = [
        r for r in LOT_SIZE_RULES
        if r.symbol == canon
        and r.effective_from <= target
        and (r.effective_to is None or target < r.effective_to)
    ]
    if not matching:
        return None
    # Most recently effective rule wins (defensive — there should only be one).
    return max(matching, key=lambda r: r.effective_from)


# ── Expiry weekday history ───────────────────────────────────────────────────
# 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri.  Same effective-date pattern.

@dataclass(frozen=True)
class ExpiryRule:
    symbol: str
    weekday: int
    effective_from: date
    effective_to: Optional[date]
    circular_ref: str
    notes: str = ""


EXPIRY_RULES: list[ExpiryRule] = [
    # NIFTY has expired on Thursdays since exchange-traded options launched.
    ExpiryRule("NIFTY",      3, date(2001,  6,  4), None, "NSE/FAOP origin", ""),
    # BANKNIFTY: was Thursday → Wednesday (Jul 2023) — kept as Wednesday in
    # NiftyNode tests; SEBI Apr 2024 proposal to revert to Thursday is not
    # yet enforced in this codebase.
    ExpiryRule("BANKNIFTY",  2, date(2023,  7,  6), None,
               "NSE/FAOP/57122 (2023-06)",
               "Moved from Thursday to Wednesday in Jul 2023"),
    ExpiryRule("FINNIFTY",   1, date(2023,  9,  4), None,
               "NSE/FAOP/57612 (2023-08)",
               "Moved to Tuesday in Sep 2023"),
    ExpiryRule("MIDCPNIFTY", 0, date(2024,  3,  4), None,
               "NSE/FAOP/61021 (2024-02)",
               "Monday expiry effective Mar 2024"),
    ExpiryRule("SENSEX",     4, date(2024,  1,  1), None,
               "BSE/Notice 20231220-12",
               "Friday expiry"),
    ExpiryRule("BANKEX",     4, date(2024,  1,  1), None,
               "BSE/Notice 20231220-12", ""),
]


def get_expiry_weekday_on(symbol: str, on_date: Optional[date] = None) -> int:
    """Return the monthly-expiry weekday (0=Mon … 4=Fri) effective on date."""
    canon = canonical_symbol(symbol)
    target = on_date or date.today()
    matching = [
        r for r in EXPIRY_RULES
        if r.symbol == canon
        and r.effective_from <= target
        and (r.effective_to is None or target < r.effective_to)
    ]
    if not matching:
        return 3  # default Thursday
    return max(matching, key=lambda r: r.effective_from).weekday


# ── Weekly availability (post May-2024 SEBI restriction) ────────────────────
# Only NIFTY and SENSEX retain weekly contracts.

WEEKLY_AVAILABLE_FROM: dict[str, Optional[date]] = {
    # symbol → date weekly *stops* being available (None = still available)
    "NIFTY":      None,
    "BANKNIFTY":  date(2024, 11, 21),   # SEBI circular Oct 2024
    "FINNIFTY":   date(2024, 11, 21),
    "MIDCPNIFTY": date(2024, 11, 21),
    "SENSEX":     None,
    "BANKEX":     date(2024, 11, 21),
}


def is_weekly_available(symbol: str, on_date: Optional[date] = None) -> bool:
    canon = canonical_symbol(symbol)
    target = on_date or date.today()
    discontinued = WEEKLY_AVAILABLE_FROM.get(canon, None)
    if discontinued is None:
        return True
    return target < discontinued


# ── Strike step (NSE convention) ─────────────────────────────────────────────
# Same step ladder as the legacy options_service._strike_step helper —
# kept here so the registry is the single source of truth.

def get_strike_step(symbol: str, S: float) -> float:
    """Return NSE strike increment for a given spot price."""
    if S >= 20_000:
        return 100.0
    if S >= 10_000:
        return 100.0
    if S >= 5_000:
        return 50.0
    if S >= 2_000:
        return 50.0
    if S >= 1_000:
        return 20.0
    if S >= 500:
        return 10.0
    return 5.0


# ── NSE trading-holiday calendar ─────────────────────────────────────────────
# Sourced from NSE annual holiday notices.  Includes only equity-segment
# trading holidays; muhurat trading sessions (Diwali) are treated as holidays
# for backtest purposes since regular trading is closed.

NSE_HOLIDAYS: dict[int, set[date]] = {
    2023: {
        date(2023,  1, 26), date(2023,  3,  7), date(2023,  3, 30),
        date(2023,  4,  4), date(2023,  4,  7), date(2023,  4, 14),
        date(2023,  5,  1), date(2023,  6, 28), date(2023,  8, 15),
        date(2023,  9, 19), date(2023, 10,  2), date(2023, 10, 24),
        date(2023, 11, 14), date(2023, 11, 27), date(2023, 12, 25),
    },
    2024: {
        date(2024,  1, 22),  # Ram Mandir Pran-Pratishtha (special)
        date(2024,  1, 26),  # Republic Day (Friday)
        date(2024,  3,  8),  # Mahashivratri
        date(2024,  3, 25),  # Holi
        date(2024,  3, 29),  # Good Friday
        date(2024,  4, 11),  # Eid-Ul-Fitr
        date(2024,  4, 17),  # Ram Navami
        date(2024,  5,  1),  # Maharashtra Day
        date(2024,  5, 20),  # Mumbai general election
        date(2024,  6, 17),  # Bakri Eid
        date(2024,  7, 17),  # Muharram
        date(2024,  8, 15),  # Independence Day
        date(2024, 10,  2),  # Gandhi Jayanti
        date(2024, 11,  1),  # Diwali / Laxmi Pujan
        date(2024, 11, 15),  # Guru Nanak Jayanti
        date(2024, 12, 25),  # Christmas
    },
    2025: {
        date(2025,  2, 26),  # Mahashivratri (Wednesday)
        date(2025,  3, 14),  # Holi
        date(2025,  3, 31),  # Eid-Ul-Fitr
        date(2025,  4, 10),  # Mahavir Jayanti
        date(2025,  4, 14),  # Ambedkar Jayanti
        date(2025,  4, 18),  # Good Friday
        date(2025,  5,  1),  # Maharashtra Day
        date(2025,  6,  6),  # Bakri Eid
        date(2025,  7,  6),  # Muharram (Sunday — already non-trading)
        date(2025,  8, 15),  # Independence Day
        date(2025,  8, 27),  # Ganesh Chaturthi
        date(2025, 10,  2),  # Gandhi Jayanti
        date(2025, 10, 21),  # Diwali / Laxmi Pujan
        date(2025, 10, 22),  # Diwali / Balipratipada
        date(2025, 11,  5),  # Guru Nanak Jayanti
        date(2025, 12, 25),  # Christmas
    },
    2026: {
        date(2026,  1, 26),  # Republic Day
        date(2026,  2, 17),  # Mahashivratri
        date(2026,  3,  5),  # Holi
        date(2026,  4,  3),  # Good Friday
        date(2026,  5,  1),  # Maharashtra Day
        date(2026,  9, 17),  # Eid-e-Milad (approx)
        date(2026, 10,  2),  # Gandhi Jayanti
        date(2026, 11,  9),  # Diwali / Laxmi Pujan (approx)
        date(2026, 12, 25),  # Christmas
    },
}


def is_holiday(d: date) -> bool:
    return d in NSE_HOLIDAYS.get(d.year, set())


def is_trading_day(d: date) -> bool:
    """Mon-Fri and not an NSE holiday."""
    return d.weekday() < 5 and not is_holiday(d)


def previous_trading_day(d: date) -> date:
    """Walk backwards until a trading day is found (max 14 days back)."""
    cur = d
    for _ in range(14):
        cur = cur - timedelta(days=1)
        if is_trading_day(cur):
            return cur
    return d  # give up


def shift_expiry_for_holiday(d: date) -> date:
    """If `d` is a holiday or weekend, return the previous trading day.

    NSE convention: when a scheduled expiry falls on a non-trading day,
    the contract expires on the immediately preceding trading day.
    """
    if is_trading_day(d):
        return d
    return previous_trading_day(d)


# ── Expiry-date generators (holiday-aware) ───────────────────────────────────

def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    cal = calendar.monthcalendar(year, month)
    days = [week[weekday] for week in cal if week[weekday] != 0]
    return date(year, month, max(days))


def monthly_expiries(symbol: str, start: date, end: date,
                     holiday_adjust: bool = True) -> list[date]:
    """Generate monthly expiries in [start, end] for the given symbol,
    using the expiry-weekday rule that was effective on each expiry month."""
    if end < start:
        return []
    out: list[date] = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        wd = get_expiry_weekday_on(symbol, date(y, m, 1))
        exp = _last_weekday_of_month(y, m, wd)
        if holiday_adjust:
            exp = shift_expiry_for_holiday(exp)
        if start <= exp <= end:
            out.append(exp)
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def weekly_expiries(symbol: str, start: date, end: date,
                    holiday_adjust: bool = True,
                    enforce_availability: bool = True) -> list[date]:
    """Generate weekly expiries (every occurrence of the target weekday)
    in [start, end], holiday-shifted by default.

    The weekday is re-evaluated per occurrence so the function stays correct
    across rule-change boundaries (e.g. BANKNIFTY's 2023 Thu→Wed move).
    When `enforce_availability` is True (default), occurrences after the
    SEBI Nov-2024 weekly-restriction cutoff are dropped for symbols that
    lost weekly contracts.
    """
    if end < start:
        return []
    out: list[date] = []
    # Walk day-by-day; pick every date whose weekday matches the
    # then-effective expiry weekday for the symbol.  Cheap for typical
    # backtest ranges (≤ a few thousand days).
    d = start
    while d <= end:
        wd_today = get_expiry_weekday_on(symbol, d)
        if d.weekday() == wd_today:
            if enforce_availability and not is_weekly_available(symbol, d):
                d = d + timedelta(days=1)
                continue
            exp = shift_expiry_for_holiday(d) if holiday_adjust else d
            if start <= exp <= end and (not out or out[-1] != exp):
                out.append(exp)
            d = d + timedelta(days=7)
        else:
            d = d + timedelta(days=1)
    return out


# ── Cost schedule (effective from Oct 2024 STT revision onward) ──────────────
# Sources:
#   - STT: Finance (No. 2) Act 2024 — options sell premium 0.10%, exercise 0.125%
#   - Exchange charge NSE F&O: 0.0035% on premium turnover (effective Oct 2024)
#   - SEBI turnover charge: Rs 10 / crore = 0.0001%
#   - Stamp duty (buy side only): 0.003% — Indian Stamp Act amendment (2020)
#   - GST: 18% on (brokerage + exchange + SEBI)
#   - Brokerage: Rs 20 flat per executed order — discount-broker baseline

@dataclass(frozen=True)
class CostSchedule:
    effective_from: date
    stt_sell_premium_pct: float       # of premium (sell side)
    stt_exercise_pct: float            # of intrinsic (exercise / ITM expiry)
    exchange_charge_pct: float         # of premium (both sides)
    sebi_charge_pct: float             # of premium (both sides)
    stamp_duty_pct: float              # of premium (buy side)
    gst_pct: float                     # on (brokerage + exchange + sebi)
    brokerage_per_order: float         # flat per executed order per leg
    circular_ref: str = ""


COST_SCHEDULES: list[CostSchedule] = [
    CostSchedule(
        effective_from=date(2024, 10,  1),
        stt_sell_premium_pct=0.0010,    # 0.10%
        stt_exercise_pct=0.00125,       # 0.125%
        exchange_charge_pct=0.000035,
        sebi_charge_pct=0.000001,
        stamp_duty_pct=0.00003,
        gst_pct=0.18,
        brokerage_per_order=20.0,
        circular_ref="Finance (No. 2) Act 2024 §163; NSE/FAOP/63450",
    ),
    CostSchedule(
        effective_from=date(2020,  1,  1),
        stt_sell_premium_pct=0.000625,  # 0.0625% (pre Oct-2024)
        stt_exercise_pct=0.00125,
        exchange_charge_pct=0.0000503,  # NSE F&O premium turnover pre-2024
        sebi_charge_pct=0.000001,
        stamp_duty_pct=0.00003,
        gst_pct=0.18,
        brokerage_per_order=20.0,
        circular_ref="NSE/FAOP/47323; Indian Stamp Act 2020",
    ),
]


def get_cost_schedule(on_date: Optional[date] = None) -> CostSchedule:
    target = on_date or date.today()
    matching = [c for c in COST_SCHEDULES if c.effective_from <= target]
    if not matching:
        return COST_SCHEDULES[0]
    return max(matching, key=lambda c: c.effective_from)


@dataclass
class CostBreakdown:
    brokerage: float
    stt: float
    exchange_charge: float
    sebi_charge: float
    stamp_duty: float
    gst: float
    total: float


def compute_leg_costs(
    *,
    action: str,                # "buy" | "sell"
    premium: float,             # per-unit premium (or intrinsic, on exercise)
    quantity: int,              # lots * lot_size (number of underlying units)
    is_entry: bool,
    on_date: Optional[date] = None,
    is_exercise: bool = False,
) -> CostBreakdown:
    """Compute the realistic cost of one fill (entry or exit) of one leg.

    For exits of long positions or of short positions, the actual side that
    executes (buy-to-close vs sell-to-close) determines STT/stamp applicability.

    When `is_exercise=True` (option held to expiry / cash settlement), no
    executed order exists, so brokerage / exchange charge / SEBI charge /
    stamp duty / GST are not levied.  Only STT on the intrinsic (when ITM
    and the holder is selling) applies — this matches NSE settlement
    treatment and avoids overstating regulatory costs at expiry.
    """
    sched = get_cost_schedule(on_date)
    notional = abs(premium) * quantity

    # Determine the effective side of THIS fill
    if is_entry:
        side = action                                 # "buy" or "sell"
    else:
        side = "sell" if action == "buy" else "buy"   # closing reverses

    if is_exercise:
        # Cash-settled expiry: no exchange order, no brokerage/stamp/GST.
        # STT @ exercise rate only on the long-side seller of intrinsic.
        stt = notional * sched.stt_exercise_pct if side == "sell" else 0.0
        return CostBreakdown(
            brokerage=0.0, stt=round(stt, 4),
            exchange_charge=0.0, sebi_charge=0.0,
            stamp_duty=0.0, gst=0.0,
            total=round(stt, 4),
        )

    brokerage      = sched.brokerage_per_order
    exchange_chg   = notional * sched.exchange_charge_pct
    sebi_chg       = notional * sched.sebi_charge_pct
    stamp_duty     = notional * sched.stamp_duty_pct if side == "buy" else 0.0
    stt            = notional * sched.stt_sell_premium_pct if side == "sell" else 0.0
    gst            = (brokerage + exchange_chg + sebi_chg) * sched.gst_pct
    total          = brokerage + stt + exchange_chg + sebi_chg + stamp_duty + gst
    return CostBreakdown(
        brokerage=round(brokerage, 4),
        stt=round(stt, 4),
        exchange_charge=round(exchange_chg, 4),
        sebi_charge=round(sebi_chg, 4),
        stamp_duty=round(stamp_duty, 4),
        gst=round(gst, 4),
        total=round(total, 4),
    )


# ── Compliance snapshot (used by GET /options/compliance) ────────────────────

def compliance_snapshot(symbol: Optional[str] = None,
                        on_date: Optional[date] = None) -> dict:
    """Return a JSON-friendly snapshot of every effective rule on `on_date`.

    If `symbol` is given, returns symbol-specific rules; otherwise returns
    rules for every supported symbol.
    """
    target = on_date or date.today()
    sched = get_cost_schedule(target)

    def _symbol_block(sym: str) -> dict:
        canon = canonical_symbol(sym)
        lot = get_lot_size_on(canon, target)
        return {
            "symbol": canon,
            "lot_size": {
                "value": lot.lot_size if lot else None,
                "effective_from": lot.effective_from.isoformat() if lot else None,
                "circular_ref": lot.circular_ref if lot else None,
                "notes": lot.notes if lot else "",
            },
            "expiry_weekday": {
                "value": get_expiry_weekday_on(canon, target),
                "weekday_name": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][
                    get_expiry_weekday_on(canon, target)
                ],
            },
            "weekly_available": is_weekly_available(canon, target),
        }

    if symbol:
        symbols_block = [_symbol_block(symbol)]
    else:
        unique_canons = sorted(set(SYMBOL_ALIASES.values()))
        symbols_block = [_symbol_block(s) for s in unique_canons]

    return {
        "as_of": target.isoformat(),
        "symbols": symbols_block,
        "cost_schedule": {
            "effective_from": sched.effective_from.isoformat(),
            "stt_sell_premium_pct": sched.stt_sell_premium_pct,
            "stt_exercise_pct": sched.stt_exercise_pct,
            "exchange_charge_pct": sched.exchange_charge_pct,
            "sebi_charge_pct": sched.sebi_charge_pct,
            "stamp_duty_pct": sched.stamp_duty_pct,
            "gst_pct": sched.gst_pct,
            "brokerage_per_order": sched.brokerage_per_order,
            "circular_ref": sched.circular_ref,
        },
        "holidays_this_year": sorted(
            d.isoformat() for d in NSE_HOLIDAYS.get(target.year, set())
        ),
    }
