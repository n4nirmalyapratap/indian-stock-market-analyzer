"""
Real-Time Earnings Scanner — Task #7
======================================
Polls BSE/NSE for recent "Financial Results" announcements, fetches XBRL
P&L data via financial_results_service, scores each filing on a 10-point
algorithm, persists scores in `earnings_alerts` (PG), and sends Telegram
alerts for score >= ALERT_THRESHOLD.

Score algorithm (max 10 pts):
  • Revenue YoY > 15% → 2 pts | 5–15% → 1 pt
  • PAT YoY > 20%    → 2 pts | 10–20% → 1 pt
  • QoQ Revenue AND PAT both up → 2 pts
  • OPM (operating margin) expansion YoY → 2 pts
  • No negative exceptional items AND finance costs YoY down → 2 pts
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx

from ..lib.auth_store import ensure_primary_schema, get_conn, now_ms

logger = logging.getLogger("earnings_scanner")

ALERT_THRESHOLD = 6
_POLL_INTERVAL_S = 30 * 60       # 30 minutes between full scans
_IST = timezone(timedelta(hours=5, minutes=30))

# BSE corporate API params — same as insights.py
_BSE_API = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
_BSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.bseindia.com",
    "Referer": "https://www.bseindia.com/",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct_change(new_val: Optional[float], old_val: Optional[float]) -> Optional[float]:
    """Percentage change from old → new. Returns None when not computable."""
    if new_val is None or old_val is None:
        return None
    if old_val == 0:
        return None
    return ((new_val - old_val) / abs(old_val)) * 100.0


def _opm(li: dict) -> Optional[float]:
    """Operating Profit Margin = (Revenue - OpEx) / Revenue.
    We use: OpProfit = profitBeforeExceptionalAndTax + financeCosts
    so that exceptional items and finance costs don't distort the
    operating margin.
    """
    rev = _float(li.get("revenueFromOperations"))
    pbex = _float(li.get("profitBeforeExceptionalAndTax"))
    fin = _float(li.get("financeCosts")) or 0.0
    if rev is None or pbex is None or rev == 0:
        return None
    return ((pbex + fin) / rev) * 100.0


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score_filing(
    symbol: str,
    quarters: list[dict],   # list of line_items dicts, newest first
) -> tuple[int, dict]:
    """
    Compute the 10-point score and return (score, detail_dict).
    `quarters` should be [Q0, Q_prev, Q_yoy, Q_yoy_prev_qoq] — 4 quarters
    newest first, each is the `line_items` JSONB from financial_results.
    """
    if len(quarters) < 3:
        return 0, {"reason": "insufficient_data"}

    q0 = quarters[0]        # current quarter
    q_prev = quarters[1]    # prior quarter (QoQ)
    q_yoy = quarters[2]     # same quarter last year (YoY)

    score = 0
    detail: dict = {}

    # 1. Revenue YoY
    rev_cur  = _float(q0.get("revenueFromOperations"))
    rev_yoy  = _float(q_yoy.get("revenueFromOperations"))
    rev_chg  = _pct_change(rev_cur, rev_yoy)
    detail["revYoY"] = round(rev_chg, 2) if rev_chg is not None else None
    if rev_chg is not None:
        if rev_chg > 15:
            score += 2
        elif rev_chg >= 5:
            score += 1

    # 2. PAT YoY
    pat_cur  = _float(q0.get("netProfit"))
    pat_yoy  = _float(q_yoy.get("netProfit"))
    pat_chg  = _pct_change(pat_cur, pat_yoy)
    detail["patYoY"] = round(pat_chg, 2) if pat_chg is not None else None
    if pat_chg is not None:
        if pat_chg > 20:
            score += 2
        elif pat_chg >= 10:
            score += 1

    # 3. QoQ: both revenue AND PAT up
    rev_prev = _float(q_prev.get("revenueFromOperations"))
    pat_prev = _float(q_prev.get("netProfit"))
    rev_qoq  = _pct_change(rev_cur, rev_prev)
    pat_qoq  = _pct_change(pat_cur, pat_prev)
    detail["revQoQ"] = round(rev_qoq, 2) if rev_qoq is not None else None
    detail["patQoQ"] = round(pat_qoq, 2) if pat_qoq is not None else None
    qoq_rev_up = rev_qoq is not None and rev_qoq > 0
    qoq_pat_up = pat_qoq is not None and pat_qoq > 0
    if qoq_rev_up and qoq_pat_up:
        score += 2
        detail["qoqBothUp"] = True
    else:
        detail["qoqBothUp"] = False

    # 4. OPM expansion YoY
    opm_cur = _opm(q0)
    opm_yoy = _opm(q_yoy)
    detail["opmCur"] = round(opm_cur, 2) if opm_cur is not None else None
    detail["opmYoY"] = round(opm_yoy, 2) if opm_yoy is not None else None
    if opm_cur is not None and opm_yoy is not None and opm_cur > opm_yoy:
        score += 2
        detail["opmExpanded"] = True
    else:
        detail["opmExpanded"] = False

    # 5. No negative exceptional items AND finance costs YoY down
    exc_cur  = _float(q0.get("exceptionalItems"))
    fin_cur  = _float(q0.get("financeCosts"))
    fin_yoy  = _float(q_yoy.get("financeCosts"))
    no_neg_exc = exc_cur is None or exc_cur >= 0
    fin_chg  = _pct_change(fin_cur, fin_yoy)
    detail["exceptionalItems"] = exc_cur
    detail["finCostChg"] = round(fin_chg, 2) if fin_chg is not None else None
    fin_down = fin_chg is not None and fin_chg < 0
    if no_neg_exc and fin_down:
        score += 2
        detail["qualityBonus"] = True
    else:
        detail["qualityBonus"] = False

    detail["score"] = score
    return score, detail


# ── DB helpers ────────────────────────────────────────────────────────────────

def _quarters_for_symbol(symbol: str, basis: str = "standalone") -> list[dict]:
    """Read the 4 most recent line_items rows for symbol from financial_results.
    Falls back from consolidated→standalone if needed."""
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT line_items FROM financial_results
                 WHERE symbol = %s AND basis = %s
                 ORDER BY period_end DESC
                 LIMIT 5
                """,
                (symbol, basis),
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
    if not rows and basis == "consolidated":
        return _quarters_for_symbol(symbol, "standalone")
    result = []
    for r in rows:
        li = r.get("line_items")
        if isinstance(li, str):
            try:
                li = json.loads(li)
            except Exception:
                li = {}
        result.append(li or {})
    return result


def _latest_period_end(symbol: str) -> Optional[date]:
    """Most recent period_end in financial_results for symbol."""
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT period_end FROM financial_results WHERE symbol = %s ORDER BY period_end DESC LIMIT 1",
                (symbol,),
            )
            row = cur.fetchone()
    if not row:
        return None
    pe = row["period_end"]
    return pe if isinstance(pe, date) else None


def _already_alerted(symbol: str, period_end_str: str) -> bool:
    """True if we have already fired a Telegram alert for this symbol+quarter."""
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM earnings_alerts WHERE symbol = %s AND period_end = %s AND telegram_sent = TRUE",
                (symbol, period_end_str),
            )
            return cur.fetchone() is not None


def _upsert_alert(
    symbol: str,
    company: str,
    period_end_str: str,
    score: int,
    detail: dict,
    telegram_sent: bool,
) -> None:
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO earnings_alerts
                    (symbol, company, period_end, score, detail_json, telegram_sent, scanned_at_ms)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
                ON CONFLICT (symbol, period_end) DO UPDATE SET
                    company       = EXCLUDED.company,
                    score         = EXCLUDED.score,
                    detail_json   = EXCLUDED.detail_json,
                    telegram_sent = earnings_alerts.telegram_sent OR EXCLUDED.telegram_sent,
                    scanned_at_ms = EXCLUDED.scanned_at_ms
                """,
                (
                    symbol, company, period_end_str, score,
                    json.dumps(detail), telegram_sent, now_ms(),
                ),
            )
        conn.commit()


def get_alerts(limit: int = 100) -> list[dict]:
    """Return most recent earnings alerts, newest first."""
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT symbol, company, period_end, score, detail_json,
                       telegram_sent, scanned_at_ms
                  FROM earnings_alerts
                 ORDER BY scanned_at_ms DESC
                 LIMIT %s
                """,
                (limit,),
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]
    out = []
    for r in rows:
        dj = r.get("detail_json")
        if isinstance(dj, str):
            try:
                dj = json.loads(dj)
            except Exception:
                dj = {}
        pe = r.get("period_end")
        out.append({
            "symbol":       r["symbol"],
            "company":      r.get("company") or r["symbol"],
            "periodEnd":    pe.isoformat() if hasattr(pe, "isoformat") else str(pe),
            "score":        r["score"],
            "detail":       dj or {},
            "telegramSent": r.get("telegram_sent") or False,
            "scannedAt":    r.get("scanned_at_ms"),
        })
    return out


# ── BSE result announcement poller ───────────────────────────────────────────

async def _fetch_bse_recent_results(pages: int = 3) -> list[dict]:
    """Fetch recent 'Financial Results' announcements from BSE (last N pages)."""
    items: list[dict] = []
    async with httpx.AsyncClient(timeout=12.0, headers=_BSE_HEADERS) as cli:
        for page in range(1, pages + 1):
            try:
                resp = await cli.get(_BSE_API, params={
                    "pageno": page,
                    "strCat": "Result",
                    "strPrevDate": "",
                    "strScrip": "",
                    "strSearch": "P",
                    "strToDate": "",
                    "strType": "C",
                })
                if resp.status_code >= 400:
                    break
                payload = resp.json()
                rows = payload.get("Table") or []
                for r in rows:
                    if not isinstance(r, dict):
                        continue
                    scrip = str(r.get("SCRIP_CD", "")).strip()
                    company = (r.get("SLONGNAME") or "").strip() or scrip
                    if scrip:
                        items.append({"symbol": scrip, "company": company})
            except Exception as exc:
                logger.debug("BSE result page %d fetch error: %s", page, exc)
                break
    # Deduplicate by symbol
    seen: set[str] = set()
    unique: list[dict] = []
    for it in items:
        sym = it["symbol"]
        if sym not in seen:
            seen.add(sym)
            unique.append(it)
    return unique


# ── Main scan routine ─────────────────────────────────────────────────────────

async def scan_recent_results(
    telegram_svc=None,
    telegram_chat_id: Optional[str] = None,
) -> dict:
    """
    Full scan cycle:
      1. Poll BSE for recent result filers
      2. For each, read quarters from financial_results (already populated by
         financial_results_service when users view stock pages)
      3. Score; upsert to earnings_alerts
      4. Fire Telegram alert if score >= threshold and not already sent
    Returns a summary dict.
    """
    from . import financial_results_service as _frs  # noqa: PLC0415

    # Resolve chat_id from env if not provided
    import os as _os  # noqa: PLC0415
    if not telegram_chat_id:
        telegram_chat_id = _os.environ.get("TELEGRAM_EARNINGS_CHAT_ID", "") or \
                           _os.environ.get("TELEGRAM_ALERT_CHAT_ID", "")

    logger.info("Earnings scanner: starting scan cycle")
    announcements = await _fetch_bse_recent_results(pages=2)
    logger.info("Earnings scanner: %d unique BSE result filers found", len(announcements))

    scored = 0
    alerted = 0
    errors = 0

    for item in announcements[:80]:       # cap at 80 companies per cycle
        symbol = item["symbol"]
        company = item["company"]
        try:
            # Ensure latest XBRL data is in DB (triggers refresh if stale)
            try:
                await asyncio.wait_for(
                    _frs.get_financial_results(symbol, basis="consolidated", quarters=5),
                    timeout=25.0,
                )
            except asyncio.TimeoutError:
                logger.debug("Earnings scanner: XBRL timeout for %s", symbol)

            quarters = _quarters_for_symbol(symbol, "consolidated")
            if len(quarters) < 3:
                quarters = _quarters_for_symbol(symbol, "standalone")
            if len(quarters) < 3:
                continue

            period_end = _latest_period_end(symbol)
            if not period_end:
                continue
            period_end_str = period_end.isoformat()

            score, detail = _score_filing(symbol, quarters)
            scored += 1

            should_telegram = (
                score >= ALERT_THRESHOLD
                and telegram_svc is not None
                and telegram_chat_id
                and not _already_alerted(symbol, period_end_str)
            )

            telegram_sent = False
            if should_telegram:
                msg = _format_telegram_alert(symbol, company, period_end_str, score, detail)
                try:
                    ok = await telegram_svc.send_message(telegram_chat_id, msg)
                    telegram_sent = bool(ok)
                    if telegram_sent:
                        alerted += 1
                        logger.info("Earnings alert sent: %s score=%d", symbol, score)
                except Exception as tg_exc:
                    logger.warning("Earnings alert TG send failed for %s: %s", symbol, tg_exc)

            _upsert_alert(symbol, company, period_end_str, score, detail, telegram_sent)

        except Exception as exc:
            errors += 1
            logger.debug("Earnings scanner: error for %s: %s", symbol, str(exc)[:120])

    logger.info(
        "Earnings scanner: done. scored=%d alerted=%d errors=%d",
        scored, alerted, errors,
    )
    return {"scored": scored, "alerted": alerted, "errors": errors, "total": len(announcements)}


def _format_telegram_alert(
    symbol: str,
    company: str,
    period_end: str,
    score: int,
    detail: dict,
) -> str:
    stars = "⭐" * score + "☆" * (10 - score)
    lines = [
        f"📊 *Earnings Radar Alert* — {score}/10",
        f"*{company}* (`{symbol}`) • Q ending {period_end}",
        stars,
        "",
    ]

    def _pct(val) -> str:
        if val is None:
            return "N/A"
        sign = "+" if val >= 0 else ""
        return f"{sign}{val:.1f}%"

    rev_yoy = detail.get("revYoY")
    pat_yoy = detail.get("patYoY")
    opm_cur = detail.get("opmCur")
    opm_yoy_val = detail.get("opmYoY")
    fin_chg = detail.get("finCostChg")

    lines.append(f"• Revenue YoY: {_pct(rev_yoy)}")
    lines.append(f"• PAT YoY: {_pct(pat_yoy)}")
    if detail.get("qoqBothUp"):
        lines.append(f"• QoQ: Revenue {_pct(detail.get('revQoQ'))} | PAT {_pct(detail.get('patQoQ'))} ✅")
    if detail.get("opmExpanded") and opm_cur is not None and opm_yoy_val is not None:
        lines.append(f"• OPM: {opm_yoy_val:.1f}% → {opm_cur:.1f}% ✅")
    if detail.get("qualityBonus"):
        lines.append(f"• Finance costs: {_pct(fin_chg)} | No negative exceptional ✅")

    lines.append("")
    lines.append(f"🔗 https://www.bseindia.com/stock-share-price/{symbol}")
    return "\n".join(lines)


# ── Scheduler entrypoint ──────────────────────────────────────────────────────

async def earnings_scanner_loop(telegram_svc=None) -> None:
    """Background scheduler — runs a scan every _POLL_INTERVAL_S seconds."""
    import os as _os  # noqa: PLC0415
    chat_id = _os.environ.get("TELEGRAM_EARNINGS_CHAT_ID", "") or \
              _os.environ.get("TELEGRAM_ALERT_CHAT_ID", "")

    await asyncio.sleep(90)        # let the server fully start first
    while True:
        try:
            await scan_recent_results(telegram_svc=telegram_svc, telegram_chat_id=chat_id)
        except asyncio.CancelledError:
            logger.info("Earnings scanner loop stopped.")
            break
        except Exception as exc:
            logger.warning("Earnings scanner loop error: %s", exc)
        try:
            await asyncio.sleep(_POLL_INTERVAL_S)
        except asyncio.CancelledError:
            logger.info("Earnings scanner loop stopped.")
            break
