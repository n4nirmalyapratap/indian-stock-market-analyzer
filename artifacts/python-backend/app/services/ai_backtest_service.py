"""
AI Analyst backtest evaluator.

For every saved single-stock report with verdict ∈ {BUY, SELL}, this service:

  1. Reads the verdict's saved-at timestamp + the price target horizon
  2. Waits until N trading days have passed (configurable per horizon)
  3. Fetches the close price on that horizon-day from the price cache
  4. Computes actual_return_pct vs the verdict-time price
  5. Decides was_correct using a 0.5% deadband:
        BUY  → correct iff price moved up   by more than DEADBAND_PCT
        SELL → correct iff price moved down by more than DEADBAND_PCT
        HOLD → ignored (no directional bet)

Each (saved_id, horizon_days) gets at most one row, so re-running the
evaluator is idempotent. We evaluate the three standard horizons (1, 5, 30
calendar days) so users can see short, medium, and long-term hit rates
without paying for a sixth column.

Public API:
    await evaluate_pending(price_service)  → {evaluated, skipped, errors}
    get_overall_stats()                    → dict of hit rates by horizon/verdict
    get_recent_calls(limit=50)             → list of recent verdict + outcome rows
    get_stats_by_ticker(ticker)            → per-ticker track record
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from psycopg.rows import dict_row

from app.lib.auth_store import ensure_primary_schema, get_conn

logger = logging.getLogger(__name__)

# Horizons we evaluate (calendar days). 1/5/30 covers short / medium / long.
EVAL_HORIZONS = (1, 5, 30)

# Movements smaller than this are treated as noise and verdicts in either
# direction are marked correct iff the move went the right way *at all*; we
# don't reward a BUY for sideways action.
DEADBAND_PCT = 0.5


def _conn():
    """Open a Postgres connection with dict-row results."""
    conn = get_conn()
    conn.row_factory = dict_row  # type: ignore[attr-defined]
    return conn


ensure_primary_schema()


# ── Pending-work selector ────────────────────────────────────────────────────

def _find_pending(now_ms: int) -> list[dict]:
    """Return saved verdicts that are ready to be backtested at one or more
    horizons. A row is 'ready' for horizon H if:
      - scope_type = 'single'
      - the report.verdict is BUY or SELL
      - at least H calendar days have passed since updated_at
      - we haven't already written a backtest row for (saved_id, H)
    """
    candidates: list[dict] = []
    with _conn() as c:
        with c.cursor() as cur:
            for horizon in EVAL_HORIZONS:
                cutoff_ms = now_ms - horizon * 86400 * 1000
                cur.execute(
                    """
                    SELECT s.id            AS saved_id,
                           s.user_id       AS user_id,
                           s.scope_key     AS ticker,
                           s.verdict       AS verdict,
                           s.confidence    AS confidence,
                           s.updated_at    AS updated_at,
                           s.report_json   AS report_json
                      FROM ai_analyst_saved s
                 LEFT JOIN ai_analyst_backtest b
                        ON b.saved_id = s.id AND b.horizon_days = %s
                     WHERE s.scope_type = 'single'
                       AND UPPER(COALESCE(s.verdict, '')) IN ('BUY', 'SELL')
                       AND s.updated_at <= %s
                       AND b.id IS NULL
                  ORDER BY s.updated_at ASC
                     LIMIT 500
                    """,
                    (horizon, cutoff_ms),
                )
                for row in cur.fetchall():
                    row["horizon_days"] = horizon
                    candidates.append(row)
    return candidates


# ── Price helpers ────────────────────────────────────────────────────────────

def _verdict_time_price(report_json: str) -> Optional[float]:
    """Pull the price recorded at verdict time out of the saved report blob.

    Prefer the trader's `entry` price, fall back to `lastPrice` or the
    `priceTarget` if neither is present. Returns None when nothing usable
    is in the blob.
    """
    try:
        blob = json.loads(report_json) if isinstance(report_json, str) else (report_json or {})
    except Exception:
        return None
    if not isinstance(blob, dict):
        return None

    candidates = [
        blob.get("entryPrice"),
        blob.get("entry"),
        blob.get("lastPrice"),
        blob.get("price"),
    ]
    # Some reports nest the price under stockDetail.quote
    stock_detail = blob.get("stockDetail")
    if isinstance(stock_detail, dict):
        candidates.append(stock_detail.get("lastPrice"))
        quote = stock_detail.get("quote")
        if isinstance(quote, dict):
            candidates.append(quote.get("lastPrice"))
    for v in candidates:
        try:
            f = float(v) if v is not None else 0
            if f > 0:
                return f
        except (TypeError, ValueError):
            continue
    return None


async def _close_on_or_before(price_service, symbol: str,
                              target_ms: int, days_back: int = 60) -> Optional[float]:
    """Return the daily close on (or just before) the given UTC ms timestamp.

    We use `<=` so weekends/holidays fall through to the last trading day.
    `days_back` controls how many days of history to fetch — 60 is plenty
    for horizons up to 30d while keeping the fetch small.
    """
    import datetime as _dt
    target_date = _dt.datetime.utcfromtimestamp(target_ms / 1000).date()
    try:
        bars = await price_service.get_historical_data(symbol, days=days_back)
    except Exception as exc:
        logger.warning("backtest: history fetch failed for %s: %s", symbol, exc)
        return None
    best: Optional[float] = None
    for bar in bars or []:
        d = str(bar.get("date") or "")[:10]
        if not d:
            continue
        try:
            bar_date = _dt.date.fromisoformat(d)
        except ValueError:
            continue
        if bar_date <= target_date:
            try:
                close = float(bar.get("close") or 0)
                if close > 0:
                    best = close  # keep walking — bars are sorted ASC
            except (TypeError, ValueError):
                continue
        else:
            break
    return best


def _was_correct(verdict: str, return_pct: float) -> bool:
    """Apply the deadband rule."""
    v = (verdict or "").upper()
    if v == "BUY":
        return return_pct > DEADBAND_PCT
    if v == "SELL":
        return return_pct < -DEADBAND_PCT
    return False  # HOLD / unknown — never counted


# ── Main evaluator ───────────────────────────────────────────────────────────

async def evaluate_pending(price_service) -> dict:
    """Walk every saved verdict that's now eligible for evaluation and write
    a row to ai_analyst_backtest. Idempotent — called daily from the
    scheduler. Returns a summary dict."""
    now_ms = int(time.time() * 1000)
    pending = _find_pending(now_ms)
    evaluated = 0
    skipped = 0
    errors = 0

    # Cache verdict-time prices by saved_id so we don't re-parse the same
    # JSON blob for all three horizons of the same verdict.
    verdict_price_cache: dict[int, Optional[float]] = {}
    # And cache history fetches per-symbol-day to avoid hammering Yahoo.
    bar_cache: dict[str, list[dict]] = {}

    for row in pending:
        saved_id = int(row["saved_id"])
        horizon  = int(row["horizon_days"])
        ticker   = str(row["ticker"] or "").upper().strip()
        verdict  = str(row["verdict"] or "").upper().strip()
        updated_at_ms = int(row["updated_at"])

        if not ticker:
            skipped += 1
            continue

        if saved_id not in verdict_price_cache:
            verdict_price_cache[saved_id] = _verdict_time_price(row["report_json"])
        verdict_price = verdict_price_cache[saved_id]
        if verdict_price is None or verdict_price <= 0:
            # We can't compute a return without a verdict-time price. Write a
            # placeholder so we don't keep retrying this verdict forever.
            _write_backtest(
                saved_id=saved_id, user_id=row["user_id"], ticker=ticker,
                verdict=verdict, confidence=row["confidence"],
                verdict_at_ms=updated_at_ms, verdict_price=None,
                horizon_days=horizon, evaluated_at_ms=now_ms,
                actual_price=None, actual_return_pct=None, was_correct=None,
                notes="no verdict-time price in report",
            )
            skipped += 1
            continue

        target_ms = updated_at_ms + horizon * 86400 * 1000
        try:
            actual_price = await _close_on_or_before(
                price_service, ticker, target_ms,
                days_back=max(horizon * 2 + 10, 60),
            )
        except Exception as exc:
            logger.warning("backtest: %s @ horizon=%d failed: %s", ticker, horizon, exc)
            errors += 1
            continue

        if actual_price is None or actual_price <= 0:
            # Couldn't get a price — leave it unevaluated for a retry tomorrow.
            errors += 1
            continue

        return_pct = (actual_price - verdict_price) / verdict_price * 100.0
        correct = _was_correct(verdict, return_pct)

        try:
            _write_backtest(
                saved_id=saved_id, user_id=row["user_id"], ticker=ticker,
                verdict=verdict, confidence=row["confidence"],
                verdict_at_ms=updated_at_ms, verdict_price=verdict_price,
                horizon_days=horizon, evaluated_at_ms=now_ms,
                actual_price=actual_price, actual_return_pct=return_pct,
                was_correct=correct, notes=None,
            )
            evaluated += 1
        except Exception as exc:
            logger.warning("backtest: write failed for %s: %s", ticker, exc)
            errors += 1

    return {"evaluated": evaluated, "skipped": skipped, "errors": errors,
            "candidates": len(pending)}


def _write_backtest(**fields) -> None:
    """Insert a backtest row. Idempotent on (saved_id, horizon_days)."""
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ai_analyst_backtest
                    (saved_id, user_id, ticker, verdict, confidence,
                     verdict_at_ms, verdict_price, horizon_days,
                     evaluated_at_ms, actual_price, actual_return_pct,
                     was_correct, notes)
                VALUES (%(saved_id)s, %(user_id)s, %(ticker)s,
                        %(verdict)s, %(confidence)s,
                        %(verdict_at_ms)s, %(verdict_price)s, %(horizon_days)s,
                        %(evaluated_at_ms)s, %(actual_price)s, %(actual_return_pct)s,
                        %(was_correct)s, %(notes)s)
                ON CONFLICT (saved_id, horizon_days) DO NOTHING
                """,
                fields,
            )
        c.commit()


# ── Read API ─────────────────────────────────────────────────────────────────

def get_overall_stats() -> dict:
    """Aggregate accuracy stats by horizon and by verdict direction.

    Only rows with non-null was_correct are counted (skips evaluations where
    we couldn't get a price). Returns a structure friendly to the frontend:

        {
          totalCalls: int,            # total backtested rows
          byHorizon: {
            "1": {total, correct, hitRate, avgReturn},
            ...
          },
          byVerdict: { "BUY": {...}, "SELL": {...} }
        }
    """
    out: dict[str, Any] = {
        "totalCalls": 0,
        "byHorizon": {},
        "byVerdict": {},
        "lastEvaluatedAt": None,
    }
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                """
                SELECT horizon_days,
                       COUNT(*)                                         AS total,
                       COUNT(*) FILTER (WHERE was_correct = TRUE)       AS correct,
                       AVG(actual_return_pct)                           AS avg_return
                  FROM ai_analyst_backtest
                 WHERE was_correct IS NOT NULL
              GROUP BY horizon_days
              ORDER BY horizon_days
                """
            )
            for row in cur.fetchall():
                total = int(row["total"])
                correct = int(row["correct"])
                out["byHorizon"][str(row["horizon_days"])] = {
                    "total":    total,
                    "correct":  correct,
                    "hitRate":  (correct / total) if total else 0,
                    "avgReturn": float(row["avg_return"] or 0),
                }
                out["totalCalls"] += total

            cur.execute(
                """
                SELECT verdict,
                       COUNT(*)                                          AS total,
                       COUNT(*) FILTER (WHERE was_correct = TRUE)        AS correct,
                       AVG(actual_return_pct)                            AS avg_return
                  FROM ai_analyst_backtest
                 WHERE was_correct IS NOT NULL
              GROUP BY verdict
                """
            )
            for row in cur.fetchall():
                total = int(row["total"])
                correct = int(row["correct"])
                out["byVerdict"][str(row["verdict"])] = {
                    "total":    total,
                    "correct":  correct,
                    "hitRate":  (correct / total) if total else 0,
                    "avgReturn": float(row["avg_return"] or 0),
                }

            cur.execute(
                "SELECT MAX(evaluated_at_ms) AS last FROM ai_analyst_backtest"
            )
            last_row = cur.fetchone()
            if last_row and last_row.get("last"):
                out["lastEvaluatedAt"] = int(last_row["last"])
    return out


def get_recent_calls(limit: int = 50, user_id: Optional[str] = None) -> list[dict]:
    """Most recently evaluated verdicts. If `user_id` is supplied the list
    is scoped to that user; otherwise it's app-wide (admin view)."""
    lim = max(1, min(200, int(limit)))
    with _conn() as c:
        with c.cursor() as cur:
            if user_id:
                cur.execute(
                    """
                    SELECT ticker, verdict, confidence, horizon_days,
                           verdict_at_ms, verdict_price,
                           evaluated_at_ms, actual_price, actual_return_pct,
                           was_correct
                      FROM ai_analyst_backtest
                     WHERE user_id = %s
                  ORDER BY evaluated_at_ms DESC
                     LIMIT %s
                    """,
                    (user_id, lim),
                )
            else:
                cur.execute(
                    """
                    SELECT ticker, verdict, confidence, horizon_days,
                           verdict_at_ms, verdict_price,
                           evaluated_at_ms, actual_price, actual_return_pct,
                           was_correct
                      FROM ai_analyst_backtest
                  ORDER BY evaluated_at_ms DESC
                     LIMIT %s
                    """,
                    (lim,),
                )
            rows = cur.fetchall()
    return [_serialize_row(r) for r in rows]


def get_stats_by_ticker(ticker: str) -> dict:
    """Per-ticker track record: total calls, hit rate, last 10 calls."""
    sym = (ticker or "").upper().strip()
    out: dict[str, Any] = {"ticker": sym, "byHorizon": {}, "recent": []}
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                """
                SELECT horizon_days,
                       COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE was_correct = TRUE) AS correct,
                       AVG(actual_return_pct) AS avg_return
                  FROM ai_analyst_backtest
                 WHERE ticker = %s AND was_correct IS NOT NULL
              GROUP BY horizon_days
                """,
                (sym,),
            )
            for row in cur.fetchall():
                total = int(row["total"])
                out["byHorizon"][str(row["horizon_days"])] = {
                    "total":     total,
                    "correct":   int(row["correct"]),
                    "hitRate":   (int(row["correct"]) / total) if total else 0,
                    "avgReturn": float(row["avg_return"] or 0),
                }

            cur.execute(
                """
                SELECT ticker, verdict, confidence, horizon_days,
                       verdict_at_ms, verdict_price,
                       evaluated_at_ms, actual_price, actual_return_pct,
                       was_correct
                  FROM ai_analyst_backtest
                 WHERE ticker = %s
              ORDER BY evaluated_at_ms DESC
                 LIMIT 10
                """,
                (sym,),
            )
            rows = cur.fetchall()
    out["recent"] = [_serialize_row(r) for r in rows]
    return out


def _serialize_row(row: dict) -> dict:
    return {
        "ticker":          row["ticker"],
        "verdict":         row["verdict"],
        "confidence":      row["confidence"],
        "horizonDays":     int(row["horizon_days"]),
        "verdictAtMs":     int(row["verdict_at_ms"]),
        "verdictPrice":    (float(row["verdict_price"]) if row["verdict_price"] is not None else None),
        "evaluatedAtMs":   int(row["evaluated_at_ms"]),
        "actualPrice":     (float(row["actual_price"]) if row["actual_price"] is not None else None),
        "actualReturnPct": (float(row["actual_return_pct"]) if row["actual_return_pct"] is not None else None),
        "wasCorrect":      row["was_correct"],
    }
