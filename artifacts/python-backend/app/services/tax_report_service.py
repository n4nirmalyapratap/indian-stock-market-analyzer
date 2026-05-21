"""
Capital-gains tax report — Indian financial year, FIFO lot matching.

Builds a per-portfolio report you can hand to a CA. Rules implemented:

  * FIFO lot matching per symbol — the share bought first is the one
    deemed sold first, which is the standard Indian retail convention
    enforced by SEBI/DPs.
  * Holding period split:
        < 365 days → Short-Term Capital Gain (STCG)
        ≥ 365 days → Long-Term Capital Gain (LTCG)
    (Equity listed on a recognised Indian stock exchange. The threshold
    is 12 months under section 2(42A); we use 365 days as the practical
    proxy.)
  * Dividends are surfaced separately — they're taxed as "income from
    other sources" at the user's slab rate, not as capital gains.
  * Fees are pro-rated per matched share so a partial lot match gets the
    correct share of the original buy fees.

Tax RATES are *not* applied here. The report shows realised gains/losses
per category; the user's effective tax depends on their slab + the year
(STCG was 15% pre-FY24, 20% from FY24; LTCG is 10% above ₹1L pre-FY24,
12.5% above ₹1.25L from FY24). Computing tax owed would require the
caller's FY, slab, and whether STT was paid — out of scope.

Public API:
    compute_report(user_id, portfolio_id, fy="2024-25") → dict
    list_available_fys(user_id, portfolio_id)          → list[str]
"""
from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, date
from typing import Optional

from . import portfolio_service as ps

logger = logging.getLogger(__name__)

# LTCG threshold (calendar days). Section 2(42A) actually says 12 months for
# listed equity — we use 365 days as an approximation. For shares held
# 11 months + 28 days, the practical day-count tips correctly.
LTCG_DAYS = 365


# ── FY helpers ────────────────────────────────────────────────────────────────

def _parse_fy(fy: str) -> tuple[date, date]:
    """Return (start_date, end_date) for an Indian FY string like '2024-25'.

    Indian FY runs April 1 to March 31 of the following calendar year.
    """
    fy = (fy or "").strip()
    if not fy or "-" not in fy:
        raise ValueError(f"FY must be in 'YYYY-YY' form (e.g. '2024-25'), got {fy!r}")
    left, right = fy.split("-", 1)
    try:
        start_year = int(left)
        end_two    = int(right)
    except ValueError as exc:
        raise ValueError(f"FY {fy!r} couldn't be parsed: {exc}") from exc

    # Normalise the right-hand side: "2024-25" or "2024-2025" both mean
    # FY starting April 2024.
    end_year = end_two if end_two >= 100 else (start_year // 100) * 100 + end_two
    if end_year != start_year + 1:
        raise ValueError(f"FY {fy!r} doesn't span consecutive years")

    return date(start_year, 4, 1), date(end_year, 3, 31)


def _ist_date_from_iso(iso: Optional[str]) -> Optional[date]:
    """Take the first 10 chars of an ISO timestamp and parse as date."""
    if not iso:
        return None
    try:
        return date.fromisoformat(iso[:10])
    except ValueError:
        # Fall back to dateutil-style parsing for non-strict ISO strings
        try:
            return datetime.fromisoformat(iso).date()
        except ValueError:
            return None


def list_available_fys(user_id: str, portfolio_id: str) -> list[str]:
    """Return the FY strings that have at least one transaction in this
    portfolio, newest first. Useful for the frontend's FY dropdown."""
    if not ps.get_portfolio(user_id, portfolio_id):
        return []
    txs = ps.list_transactions(user_id, portfolio_id)
    fys: set[str] = set()
    for tx in txs:
        d = _ist_date_from_iso(tx.get("tradedAt"))
        if not d:
            continue
        # FY label: month >= April → FY starts this year; month <= March →
        # FY started last year.
        if d.month >= 4:
            start = d.year
        else:
            start = d.year - 1
        fys.add(f"{start}-{str(start + 1)[-2:]}")
    return sorted(fys, reverse=True)


# ── Main computation ─────────────────────────────────────────────────────────

def compute_report(user_id: str, portfolio_id: str, fy: str) -> dict:
    """Build the capital-gains report.

    Edge cases handled:
      * Sell with no matching buy (e.g. user imported partial history) —
        surfaced under `unmatched.sells` so the user sees the problem.
      * Multiple SELLs spanning multiple buy lots — proportional fee
        allocation per matched share.
      * DIVIDEND transactions — captured separately under `dividends`.
      * BUY with qty=0 or price=0 — skipped at intake.
    """
    if not ps.get_portfolio(user_id, portfolio_id):
        return {"error": "portfolio not found"}

    fy_start, fy_end = _parse_fy(fy)
    txs = ps.list_transactions(user_id, portfolio_id)
    # The service returns txs newest-first; we need oldest-first for FIFO.
    txs = sorted(txs, key=lambda t: (t.get("tradedAt") or "", t.get("id") or ""))

    # One FIFO queue per symbol.
    lots_by_sym: dict[str, deque[dict]] = {}

    # Output buckets — only sells that fall within the requested FY actually
    # land in stcg/ltcg. Buys outside the FY still populate the FIFO queues
    # (so a sell in FY 2024-25 can match against a 2022 buy).
    stcg: list[dict] = []
    ltcg: list[dict] = []
    dividends: list[dict] = []
    unmatched_sells: list[dict] = []

    for tx in txs:
        side = (tx.get("side") or "").upper()
        sym  = (tx.get("symbol") or "").upper()
        qty  = float(tx.get("qty") or 0)
        price = float(tx.get("price") or 0)
        fees  = float(tx.get("fees") or 0)
        tdate = _ist_date_from_iso(tx.get("tradedAt"))
        if not sym or qty <= 0 or price < 0 or not tdate:
            continue

        if side == "BUY":
            lots_by_sym.setdefault(sym, deque()).append({
                "qty":  qty,
                "price": price,
                "fees":  fees,
                "date":  tdate,
            })
        elif side == "SELL":
            remaining = qty
            lots = lots_by_sym.setdefault(sym, deque())
            matched_qty_total = 0.0
            while remaining > 0 and lots:
                lot = lots[0]
                take = min(remaining, lot["qty"])
                # Pro-rate the original buy fees across matched shares.
                buy_fee_share = lot["fees"] * (take / lot["qty"]) if lot["qty"] > 0 else 0.0
                # Pro-rate the sell fees across the matched portion of the sell.
                sell_fee_share = fees * (take / qty) if qty > 0 else 0.0

                buy_cost   = lot["price"] * take + buy_fee_share
                sell_value = price * take - sell_fee_share
                gain       = sell_value - buy_cost
                holding_days = (tdate - lot["date"]).days
                bucket = ltcg if holding_days >= LTCG_DAYS else stcg

                # Only record sells that fall inside the requested FY. Sells
                # outside the FY still consume FIFO lots so the queue stays
                # accurate for the inside-FY ones.
                if fy_start <= tdate <= fy_end:
                    bucket.append({
                        "symbol":      sym,
                        "qty":         round(take, 6),
                        "buyDate":     lot["date"].isoformat(),
                        "buyPrice":    round(lot["price"], 4),
                        "sellDate":    tdate.isoformat(),
                        "sellPrice":   round(price, 4),
                        "buyCost":     round(buy_cost, 2),
                        "sellValue":   round(sell_value, 2),
                        "gainLoss":    round(gain, 2),
                        "holdingDays": holding_days,
                        # `feeAllocated` = sum of buy+sell fees applied to
                        # this matched lot. Surfaced so the user can verify
                        # the proportional split.
                        "feeAllocated": round(buy_fee_share + sell_fee_share, 2),
                    })

                # Consume from the lot.
                lot["qty"]  -= take
                lot["fees"] -= buy_fee_share
                if lot["qty"] <= 1e-9:
                    lots.popleft()
                remaining   -= take
                matched_qty_total += take

            if remaining > 1e-9 and fy_start <= tdate <= fy_end:
                # We had a SELL with no matching BUY history — surface it so
                # the user notices the data gap (commonly a partial CSV
                # import).
                unmatched_sells.append({
                    "symbol":      sym,
                    "sellDate":    tdate.isoformat(),
                    "sellPrice":   round(price, 4),
                    "unmatchedQty": round(remaining, 6),
                })

        elif side == "DIVIDEND":
            if fy_start <= tdate <= fy_end:
                dividends.append({
                    "symbol":   sym,
                    "date":     tdate.isoformat(),
                    "amount":   round(qty * price, 2),
                    # Many users record dividends as qty=DPS, price=shares; some
                    # do qty=1, price=total. Surface qty+price so the user can
                    # sanity-check rather than us guessing.
                    "qty":      round(qty, 6),
                    "perShare": round(price, 4),
                })

    # Aggregates
    def _agg(rows: list[dict]) -> dict:
        gains  = sum(r["gainLoss"] for r in rows if r["gainLoss"] > 0)
        losses = sum(r["gainLoss"] for r in rows if r["gainLoss"] < 0)
        return {
            "rows":       rows,
            "count":      len(rows),
            "totalGains":  round(gains, 2),
            "totalLosses": round(losses, 2),
            "net":         round(gains + losses, 2),
        }

    return {
        "portfolioId":   portfolio_id,
        "fy":            fy,
        "fyStart":       fy_start.isoformat(),
        "fyEnd":         fy_end.isoformat(),
        "shortTerm":     _agg(stcg),
        "longTerm":      _agg(ltcg),
        "dividends": {
            "rows":   dividends,
            "count":  len(dividends),
            "total":  round(sum(d["amount"] for d in dividends), 2),
        },
        "unmatched": {
            "sells": unmatched_sells,
            "count": len(unmatched_sells),
        },
        "notes": [
            "Holding period uses calendar days; section 2(42A) uses 12 months.",
            "Tax rates not applied — show this to your CA for the final liability.",
            "LTCG over ₹1 lakh (or ₹1.25 lakh from FY24 onwards) is taxable.",
            "Bonus issues / splits are not reconciled here — adjust manually.",
        ],
    }


# ── CSV export ────────────────────────────────────────────────────────────────

def to_csv(report: dict) -> str:
    """Render the matched-lot rows as a CSV the user can hand to a CA.

    Three sections (STCG, LTCG, dividends) concatenated with blank-line
    separators. Each section has its own header row so the file is still
    parseable by Excel / Google Sheets via the "auto-detect" import.
    """
    import csv as _csv
    import io as _io

    buf = _io.StringIO()
    w = _csv.writer(buf)

    w.writerow([f"Capital Gains Report — FY {report.get('fy', '?')}"])
    w.writerow([f"Portfolio {report.get('portfolioId', '?')} · "
                f"{report.get('fyStart')} to {report.get('fyEnd')}"])
    w.writerow([])

    def _section(title: str, rows: list[dict], cols: list[tuple[str, str]]) -> None:
        w.writerow([title])
        w.writerow([label for label, _ in cols])
        for r in rows:
            w.writerow([r.get(k, "") for _, k in cols])
        w.writerow([])

    _section(
        "Short-Term Capital Gains (held < 365 days)",
        report["shortTerm"]["rows"],
        [("Symbol", "symbol"), ("Qty", "qty"),
         ("Buy date", "buyDate"), ("Buy price", "buyPrice"),
         ("Sell date", "sellDate"), ("Sell price", "sellPrice"),
         ("Buy cost", "buyCost"), ("Sell value", "sellValue"),
         ("Gain/Loss", "gainLoss"), ("Holding days", "holdingDays"),
         ("Fees allocated", "feeAllocated")],
    )
    w.writerow([f"STCG total: ₹{report['shortTerm']['net']:,.2f}"])
    w.writerow([])

    _section(
        "Long-Term Capital Gains (held ≥ 365 days)",
        report["longTerm"]["rows"],
        [("Symbol", "symbol"), ("Qty", "qty"),
         ("Buy date", "buyDate"), ("Buy price", "buyPrice"),
         ("Sell date", "sellDate"), ("Sell price", "sellPrice"),
         ("Buy cost", "buyCost"), ("Sell value", "sellValue"),
         ("Gain/Loss", "gainLoss"), ("Holding days", "holdingDays"),
         ("Fees allocated", "feeAllocated")],
    )
    w.writerow([f"LTCG total: ₹{report['longTerm']['net']:,.2f}"])
    w.writerow([])

    _section(
        "Dividend income",
        report["dividends"]["rows"],
        [("Symbol", "symbol"), ("Date", "date"), ("Qty", "qty"),
         ("Per-share", "perShare"), ("Amount", "amount")],
    )
    w.writerow([f"Dividends total: ₹{report['dividends']['total']:,.2f}"])

    if report["unmatched"]["sells"]:
        w.writerow([])
        _section(
            "Unmatched SELLs (sold without a recorded buy — likely missing history)",
            report["unmatched"]["sells"],
            [("Symbol", "symbol"), ("Sell date", "sellDate"),
             ("Sell price", "sellPrice"), ("Unmatched qty", "unmatchedQty")],
        )

    return buf.getvalue()
