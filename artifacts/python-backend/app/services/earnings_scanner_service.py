"""
Real-Time Earnings Scanner — Task #7
======================================
Polls NSE + BSE for recent "Financial Results" announcements, fetches XBRL
P&L data via financial_results_service, scores each filing on a 10-point
algorithm, persists scores in `earnings_alerts` (PG), and sends Telegram
alerts for score >= ALERT_THRESHOLD.

Scheduler: runs every 3 minutes. Market-hours gated (Mon-Fri 09:00–17:30 IST).

Score algorithm (max 10 pts):
  • Revenue YoY > 15% → 2 pts | 5–15% → 1 pt
  • PAT YoY > 20%    → 2 pts | 10–20% → 1 pt
  • QoQ Revenue AND PAT both up → 2 pts
  • OPM expansion YoY → 2 pts
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
_POLL_INTERVAL_S = 3 * 60          # 3 minutes between scans
_IST = timezone(timedelta(hours=5, minutes=30))

# Market-hours gate: Mon–Fri 09:00–17:30 IST
_MKT_OPEN_H, _MKT_OPEN_M    = 9,  0
_MKT_CLOSE_H, _MKT_CLOSE_M  = 17, 30

# BSE corporate API — same base as insights.py
_BSE_API = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
_BSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.bseindia.com",
    "Referer": "https://www.bseindia.com/",
}


# ── Market-hours gate ─────────────────────────────────────────────────────────

def _is_market_hours() -> bool:
    """True if current IST time is Mon–Fri 09:00–17:30."""
    now_ist = datetime.now(_IST)
    if now_ist.weekday() >= 5:       # Saturday=5, Sunday=6
        return False
    cur_mins = now_ist.hour * 60 + now_ist.minute
    open_mins  = _MKT_OPEN_H  * 60 + _MKT_OPEN_M
    close_mins = _MKT_CLOSE_H * 60 + _MKT_CLOSE_M
    return open_mins <= cur_mins <= close_mins


# ── Math helpers ──────────────────────────────────────────────────────────────

def _float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct_change(new_val: Optional[float], old_val: Optional[float]) -> Optional[float]:
    if new_val is None or old_val is None:
        return None
    if old_val == 0:
        return None
    return ((new_val - old_val) / abs(old_val)) * 100.0


def _opm(li: dict) -> Optional[float]:
    """Operating Profit Margin = (EBIT + FinanceCosts) / Revenue.
    Using profitBeforeExceptionalAndTax + financeCosts as operating profit
    excludes one-off exceptional items from the margin calculation.
    """
    rev  = _float(li.get("revenueFromOperations"))
    pbex = _float(li.get("profitBeforeExceptionalAndTax"))
    fin  = _float(li.get("financeCosts")) or 0.0
    if rev is None or pbex is None or rev == 0:
        return None
    return ((pbex + fin) / rev) * 100.0


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score_filing(quarters: list[dict]) -> tuple[int, dict, dict]:
    """
    Compute 10-point score. Returns (score, score_breakdown, key_metrics).

    `quarters` = [Q0_cur, Q_prev_qoq, Q_yoy, ...] — newest first,
    each element is the `line_items` JSONB dict from financial_results.
    """
    if len(quarters) < 3:
        return 0, {"reason": "insufficient_data"}, {}

    q0    = quarters[0]   # current quarter
    q_qoq = quarters[1]   # prior quarter (QoQ base)
    q_yoy = quarters[2]   # same quarter last year (YoY base)

    score = 0
    breakdown: dict = {}

    # 1. Revenue YoY (0–2 pts)
    rev_cur  = _float(q0.get("revenueFromOperations"))
    rev_yoy  = _float(q_yoy.get("revenueFromOperations"))
    rev_chg  = _pct_change(rev_cur, rev_yoy)
    rev_pts  = 0
    if rev_chg is not None:
        if rev_chg > 15:
            rev_pts = 2
        elif rev_chg >= 5:
            rev_pts = 1
    score += rev_pts
    breakdown["revYoY"] = {"pct": round(rev_chg, 2) if rev_chg is not None else None, "pts": rev_pts}

    # 2. PAT YoY (0–2 pts)
    pat_cur  = _float(q0.get("netProfit"))
    pat_yoy  = _float(q_yoy.get("netProfit"))
    pat_chg  = _pct_change(pat_cur, pat_yoy)
    pat_pts  = 0
    if pat_chg is not None:
        if pat_chg > 20:
            pat_pts = 2
        elif pat_chg >= 10:
            pat_pts = 1
    score += pat_pts
    breakdown["patYoY"] = {"pct": round(pat_chg, 2) if pat_chg is not None else None, "pts": pat_pts}

    # 3. QoQ: both Revenue AND PAT up (0–2 pts)
    rev_prev = _float(q_qoq.get("revenueFromOperations"))
    pat_prev = _float(q_qoq.get("netProfit"))
    rev_qoq  = _pct_change(rev_cur, rev_prev)
    pat_qoq  = _pct_change(pat_cur, pat_prev)
    qoq_pts  = 2 if (
        rev_qoq is not None and rev_qoq > 0 and
        pat_qoq is not None and pat_qoq > 0
    ) else 0
    score += qoq_pts
    breakdown["qoq"] = {
        "revPct": round(rev_qoq, 2) if rev_qoq is not None else None,
        "patPct": round(pat_qoq, 2) if pat_qoq is not None else None,
        "bothUp": qoq_pts == 2,
        "pts": qoq_pts,
    }

    # 4. OPM expansion YoY (0–2 pts)
    opm_cur = _opm(q0)
    opm_yoy = _opm(q_yoy)
    opm_pts = 2 if (opm_cur is not None and opm_yoy is not None and opm_cur > opm_yoy) else 0
    score  += opm_pts
    breakdown["opm"] = {
        "cur": round(opm_cur, 2) if opm_cur is not None else None,
        "yoy": round(opm_yoy, 2) if opm_yoy is not None else None,
        "expanded": opm_pts == 2,
        "pts": opm_pts,
    }

    # 5. Quality: no negative exceptional AND finance costs down YoY (0–2 pts)
    exc_cur = _float(q0.get("exceptionalItems"))
    fin_cur = _float(q0.get("financeCosts"))
    fin_yoy = _float(q_yoy.get("financeCosts"))
    fin_chg = _pct_change(fin_cur, fin_yoy)
    no_neg_exc = exc_cur is None or exc_cur >= 0
    fin_down   = fin_chg is not None and fin_chg < 0
    qual_pts   = 2 if (no_neg_exc and fin_down) else 0
    score     += qual_pts
    breakdown["quality"] = {
        "exceptionalOk": no_neg_exc,
        "finCostChgPct": round(fin_chg, 2) if fin_chg is not None else None,
        "finCostDown": fin_down,
        "pts": qual_pts,
    }

    # Summary key_metrics for quick display
    key_metrics = {
        "revenueYoYPct":  breakdown["revYoY"]["pct"],
        "patYoYPct":      breakdown["patYoY"]["pct"],
        "revenueQoQPct":  breakdown["qoq"]["revPct"],
        "patQoQPct":      breakdown["qoq"]["patPct"],
        "opmCurPct":      breakdown["opm"]["cur"],
        "opmYoYPct":      breakdown["opm"]["yoy"],
        "finCostChgPct":  breakdown["quality"]["finCostChgPct"],
        "revenueCrores":  round(rev_cur, 2) if rev_cur is not None else None,
        "patCrores":      round(pat_cur, 2) if pat_cur is not None else None,
    }

    return score, breakdown, key_metrics


# ── DB helpers ────────────────────────────────────────────────────────────────

def _quarters_for_symbol(symbol: str, basis: str = "consolidated") -> tuple[list[dict], str]:
    """Read the 5 most recent line_items rows from financial_results.
    Falls back consolidated → standalone. Returns (quarters_list, actual_basis)."""
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
    return result, basis


def _latest_period_end(symbol: str, basis: str) -> Optional[date]:
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT period_end FROM financial_results
                 WHERE symbol = %s AND basis = %s
                 ORDER BY period_end DESC LIMIT 1
                """,
                (symbol, basis),
            )
            row = cur.fetchone()
    if not row:
        return None
    pe = row["period_end"]
    return pe if isinstance(pe, date) else None


def _already_alerted(symbol: str, period_end_str: str, basis: str) -> bool:
    """True if Telegram already fired for this symbol+quarter+basis."""
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM earnings_alerts
                 WHERE symbol = %s AND period_end = %s AND basis = %s
                   AND alerted = TRUE
                """,
                (symbol, period_end_str, basis),
            )
            return cur.fetchone() is not None


def _upsert_alert(
    symbol: str,
    company: str,
    period_end_str: str,
    basis: str,
    score: int,
    score_breakdown: dict,
    key_metrics: dict,
    alerted: bool,
) -> None:
    ensure_primary_schema()
    ts = now_ms()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO earnings_alerts
                    (symbol, company, period_end, basis, score,
                     score_breakdown, key_metrics, alerted, created_at_ms, scanned_at_ms)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
                ON CONFLICT (symbol, period_end, basis) DO UPDATE SET
                    company        = EXCLUDED.company,
                    score          = EXCLUDED.score,
                    score_breakdown = EXCLUDED.score_breakdown,
                    key_metrics    = EXCLUDED.key_metrics,
                    alerted        = earnings_alerts.alerted OR EXCLUDED.alerted,
                    scanned_at_ms  = EXCLUDED.scanned_at_ms
                """,
                (
                    symbol, company, period_end_str, basis, score,
                    json.dumps(score_breakdown), json.dumps(key_metrics),
                    alerted, ts, ts,
                ),
            )
        conn.commit()


def get_alerts(limit: int = 100, offset: int = 0, min_score: int = 0) -> tuple[list[dict], int]:
    """Return scored alerts newest-first. Returns (rows, total_count)."""
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS cnt FROM earnings_alerts WHERE score >= %s
                """,
                (min_score,),
            )
            total = (cur.fetchone() or {}).get("cnt") or 0

            cur.execute(
                """
                SELECT symbol, company, period_end, basis, score,
                       score_breakdown, key_metrics, alerted, created_at_ms, scanned_at_ms
                  FROM earnings_alerts
                 WHERE score >= %s
                 ORDER BY scanned_at_ms DESC, score DESC
                 LIMIT %s OFFSET %s
                """,
                (min_score, limit, offset),
            )
            rows = [dict(r) for r in (cur.fetchall() or [])]

    out = []
    for r in rows:
        def _parse_json(v):
            if isinstance(v, dict):
                return v
            if isinstance(v, str):
                try:
                    return json.loads(v)
                except Exception:
                    return {}
            return {}

        pe = r.get("period_end")
        out.append({
            "symbol":        r["symbol"],
            "company":       r.get("company") or r["symbol"],
            "periodEnd":     pe.isoformat() if hasattr(pe, "isoformat") else str(pe),
            "basis":         r.get("basis") or "standalone",
            "score":         r["score"],
            "scoreBreakdown": _parse_json(r.get("score_breakdown")),
            "keyMetrics":    _parse_json(r.get("key_metrics")),
            "alerted":       r.get("alerted") or False,
            "createdAt":     r.get("created_at_ms"),
            "scannedAt":     r.get("scanned_at_ms"),
        })
    return out, int(total)


# ── Feed pollers ──────────────────────────────────────────────────────────────

async def _fetch_nse_recent_results() -> list[dict]:
    """Poll NSE corporate announcements and return result-type filers.
    NSE gives us NSE symbols directly — preferred over BSE numeric codes."""
    from . import registry as svc  # noqa: PLC0415
    try:
        data = await svc.nse.fetch_nse(
            "/api/corporate-announcements?index=equities",
            cache_key="nse-corp-anno-scanner",
            ttl=60,          # 1-min cache so 3-min scanner sees fresh data
        )
    except Exception as exc:
        logger.debug("NSE announcements fetch failed: %s", exc)
        return []

    rows = data if isinstance(data, list) else (data or {}).get("data") or []
    result_filers: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        desc = (r.get("desc") or "").lower()
        subj = (r.get("attchmntText") or "").lower()
        if "result" not in desc and "result" not in subj:
            continue
        sym = (r.get("symbol") or "").strip()
        company = (r.get("sm_name") or sym).strip()
        if sym and sym not in seen:
            seen.add(sym)
            result_filers.append({"symbol": sym, "company": company, "source": "NSE"})
    return result_filers


async def _fetch_bse_recent_results(pages: int = 2) -> list[dict]:
    """Poll BSE corporate API for recent Result announcements.
    BSE SCRIP_CD is numeric — we attempt NSE-symbol resolution via security registry."""
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
                    scrip_cd = str(r.get("SCRIP_CD", "")).strip()
                    company  = (r.get("SLONGNAME") or "").strip()
                    if scrip_cd:
                        items.append({
                            "bseCode": scrip_cd,
                            "company": company,
                            "source": "BSE",
                        })
            except Exception as exc:
                logger.debug("BSE result page %d error: %s", page, exc)
                break
    return items


def _resolve_bse_symbol(bse_code: str, company: str) -> Optional[str]:
    """Try to map a BSE numeric SCRIP_CD to an NSE symbol via the stocks/security_registry tables."""
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 1. Check stocks table (has yahoo_ticker which maps bse→nse in many cases)
            if company:
                cur.execute(
                    """
                    SELECT symbol FROM stocks
                     WHERE LOWER(name) = LOWER(%s) OR symbol = %s
                     LIMIT 1
                    """,
                    (company, bse_code),
                )
                row = cur.fetchone()
                if row:
                    return row["symbol"]
            # 2. If BSE code is numeric and happens to be a valid NSE symbol (rare but possible)
            if not bse_code.isdigit():
                return bse_code
    return None


async def _collect_filers() -> list[dict]:
    """Merge NSE + BSE result filers, deduplicated by NSE symbol."""
    nse_filers, bse_filers = await asyncio.gather(
        _fetch_nse_recent_results(),
        _fetch_bse_recent_results(pages=2),
        return_exceptions=True,
    )

    seen_symbols: set[str] = set()
    merged: list[dict] = []

    # NSE feed first (gives clean symbols directly)
    if isinstance(nse_filers, list):
        for f in nse_filers:
            sym = f["symbol"]
            if sym and sym not in seen_symbols:
                seen_symbols.add(sym)
                merged.append(f)

    # BSE feed: resolve SCRIP_CD → NSE symbol
    if isinstance(bse_filers, list):
        for f in bse_filers:
            bse_code = f.get("bseCode", "")
            company  = f.get("company", "")
            nse_sym  = _resolve_bse_symbol(bse_code, company) if bse_code else None
            sym = nse_sym or (bse_code if not bse_code.isdigit() else None)
            if sym and sym not in seen_symbols:
                seen_symbols.add(sym)
                merged.append({"symbol": sym, "company": company, "source": "BSE"})

    return merged


# ── Main scan routine ─────────────────────────────────────────────────────────

async def scan_recent_results(
    telegram_svc=None,
    telegram_chat_id: Optional[str] = None,
) -> dict:
    """
    Full scan cycle:
      1. Poll NSE + BSE for recent result filers
      2. For each, refresh XBRL data via financial_results_service
      3. Score; upsert to earnings_alerts
      4. Fire Telegram alert if score >= threshold and not already sent
    """
    from ..services import financial_results_service as _frs  # noqa: PLC0415

    import os as _os  # noqa: PLC0415
    if not telegram_chat_id:
        telegram_chat_id = (
            _os.environ.get("TELEGRAM_EARNINGS_CHAT_ID", "") or
            _os.environ.get("TELEGRAM_ALERT_CHAT_ID", "")
        )

    logger.info("Earnings scanner: collecting filers…")
    filers = await _collect_filers()
    logger.info("Earnings scanner: %d unique filers (NSE+BSE)", len(filers))

    scored = 0
    alerted = 0
    errors = 0

    for item in filers[:100]:
        symbol  = item["symbol"]
        company = item.get("company") or symbol
        try:
            # Refresh XBRL data (non-blocking on timeout)
            try:
                await asyncio.wait_for(
                    _frs.get_financial_results(symbol, basis="consolidated", quarters=5),
                    timeout=20.0,
                )
            except asyncio.TimeoutError:
                logger.debug("Earnings scanner: XBRL timeout %s", symbol)
            except Exception as exc:
                logger.debug("Earnings scanner: XBRL error %s: %s", symbol, str(exc)[:80])

            quarters, actual_basis = _quarters_for_symbol(symbol, "consolidated")
            if len(quarters) < 3:
                continue

            period_end = _latest_period_end(symbol, actual_basis)
            if not period_end:
                continue
            period_end_str = period_end.isoformat()

            score, score_breakdown, key_metrics = _score_filing(quarters)
            scored += 1

            should_telegram = (
                score >= ALERT_THRESHOLD
                and telegram_svc is not None
                and telegram_chat_id
                and not _already_alerted(symbol, period_end_str, actual_basis)
            )

            sent = False
            if should_telegram:
                msg = _format_telegram_alert(symbol, company, period_end_str, score, score_breakdown, key_metrics)
                try:
                    ok = await telegram_svc.send_message(telegram_chat_id, msg)
                    sent = bool(ok)
                    if sent:
                        alerted += 1
                        logger.info("Earnings alert sent: %s score=%d/%d", symbol, score, 10)
                except Exception as tg_exc:
                    logger.warning("Earnings TG send failed %s: %s", symbol, tg_exc)

            _upsert_alert(symbol, company, period_end_str, actual_basis,
                          score, score_breakdown, key_metrics, sent)

        except Exception as exc:
            errors += 1
            logger.debug("Earnings scanner: error %s: %s", symbol, str(exc)[:120])

    result = {"scored": scored, "alerted": alerted, "errors": errors, "total": len(filers)}
    logger.info("Earnings scanner: done — %s", result)
    return result


def _format_telegram_alert(
    symbol: str,
    company: str,
    period_end: str,
    score: int,
    breakdown: dict,
    key_metrics: dict,
) -> str:
    stars = "⭐" * min(score, 10)

    def _pct(val) -> str:
        if val is None:
            return "N/A"
        sign = "+" if val >= 0 else ""
        return f"{sign}{val:.1f}%"

    def _pts(key: str) -> str:
        b = breakdown.get(key, {})
        p = b.get("pts", 0)
        return f"({p}/2 pts)" if isinstance(p, int) else ""

    lines = [
        f"📊 *Earnings Radar Alert* — {score}/10 {stars}",
        f"*{company}* (`{symbol}`) · Q ending {period_end}",
        "",
        f"📈 Revenue YoY: {_pct(key_metrics.get('revenueYoYPct'))} {_pts('revYoY')}",
        f"💰 PAT YoY: {_pct(key_metrics.get('patYoYPct'))} {_pts('patYoY')}",
        f"🔄 QoQ Rev/PAT: {_pct(key_metrics.get('revenueQoQPct'))} / {_pct(key_metrics.get('patQoQPct'))} {_pts('qoq')}",
    ]
    opm_cur = key_metrics.get("opmCurPct")
    opm_yoy = key_metrics.get("opmYoYPct")
    if opm_cur is not None and opm_yoy is not None:
        direction = "↑" if opm_cur > opm_yoy else "↓"
        lines.append(f"📊 OPM: {opm_yoy:.1f}% → {opm_cur:.1f}% {direction} {_pts('opm')}")
    fin_chg = key_metrics.get("finCostChgPct")
    lines.append(f"✅ Fin cost: {_pct(fin_chg)} {_pts('quality')}")
    lines += ["", f"🔗 https://www.bseindia.com/stock-share-price/{symbol}"]
    return "\n".join(lines)


# ── Background scheduler loop ─────────────────────────────────────────────────

async def earnings_scanner_loop(telegram_svc=None) -> None:
    """Runs every _POLL_INTERVAL_S; gated to Mon–Fri 09:00–17:30 IST."""
    import os as _os  # noqa: PLC0415
    chat_id = (
        _os.environ.get("TELEGRAM_EARNINGS_CHAT_ID", "") or
        _os.environ.get("TELEGRAM_ALERT_CHAT_ID", "")
    )

    await asyncio.sleep(90)  # let server fully start first
    while True:
        try:
            if _is_market_hours():
                await scan_recent_results(telegram_svc=telegram_svc, telegram_chat_id=chat_id)
            else:
                now_ist = datetime.now(_IST)
                logger.debug(
                    "Earnings scanner: outside market hours (%s %s) — skipping",
                    ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][now_ist.weekday()],
                    now_ist.strftime("%H:%M IST"),
                )
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
