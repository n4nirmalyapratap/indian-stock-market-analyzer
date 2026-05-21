"""
ai_analyst_service.py — "Deep AI Analyst" multi-agent research pipeline.

Architecture mirrors TauricResearch/TradingAgents v0.2.4 (5 layers) but is
implemented natively over our existing OpenRouter-only `ai_client` and our
existing Indian-data services. See `.local/tradingagents_spike.md` for the
why.

Pipeline (one run = ~5 LLM calls):

    Phase 1 — Analysts (parallel):
        • Fundamentals analyst   (yfinance .info + StocksService)
        • News analyst           (news_service Indian RSS + sentiment)
        • Technicals analyst     (StocksService technicalAnalysis block)
        • Macro/Flow analyst     (FII/DII pulse + market state)

    Phase 2 — Research debate:
        • Bull researcher  vs  Bear researcher  (single round)

    Phase 3 — Trader synthesis:
        • Verdict (BUY/HOLD/SELL) + confidence + headline thesis

    Phase 4 — Risk gate:
        • SEBI-compliant rephrase: strip advice language, ensure disclaimer.

Public API:
    async run_analysis(ticker, user_id, force_refresh=False)
        → async generator yielding dict events:
            {phase, agent, status, partialText?}
          and finally {phase: "done", report: {...}}

    get_cached_report(ticker)             → dict | None
    get_quota(user_id)                    → {used, limit, resetsAtIst}
    feature_enabled()                     → bool

Persistence: Postgres tables ``ai_analyst_quota`` and ``ai_analyst_saved``
(schema bootstrapped by app.lib.auth_store.ensure_primary_schema).
This used to be a local SQLite file at market_cache/ai_analyst.db; the
migration moved it to the shared Postgres so multi-instance deployments
don't corrupt the write log.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any, AsyncGenerator, Optional

from psycopg.rows import dict_row

from app.lib.auth_store import ensure_primary_schema, get_conn

from . import ai_client
from .nse_service import NseService
from .yahoo_service import YahooService
from .stocks_service import StocksService
from . import news_service
from .fii_dii_service import FiiDiiService
from . import market_cache_service as mcache

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

IST = timezone(timedelta(hours=5, minutes=30))

DEFAULT_DAILY_QUOTA = 3      # free tier (admin-configurable via secret AI_ANALYST_DAILY_QUOTA)
PAID_DAILY_QUOTA    = 25     # paid tier (no billing wired yet)

# When RSS coverage of a ticker is below this many articles, we top up via
# Tavily search (gated on TAVILY_API_KEY — otherwise the top-up is a no-op).
_NEWS_TAVILY_FLOOR = 3


def _daily_quota_limit() -> int:
    """Resolve the per-user daily quota.

    Priority: ``AI_ANALYST_DAILY_QUOTA`` from secrets_store (DB → env)
    → ``DEFAULT_DAILY_QUOTA``. Clamped to [1, 1000] to guard against
    typos that would either lock everyone out or let one user burn the
    whole free tier.
    """
    try:
        from app.lib.secrets_store import get_secret  # noqa: PLC0415
        raw = (get_secret("AI_ANALYST_DAILY_QUOTA", "") or "").strip()
    except Exception:
        raw = ""
    if not raw:
        return DEFAULT_DAILY_QUOTA
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_DAILY_QUOTA
    return max(1, min(1000, n))

# Shared services
_nse    = NseService()
_yahoo  = YahooService()
_stocks = StocksService(_nse, _yahoo)


def feature_enabled() -> bool:
    """Feature flag — defaults OFF for staged rollout (per task spec).
    Set FEATURE_AI_ANALYST=on (or 1/true/yes) to enable."""
    val = (os.environ.get("FEATURE_AI_ANALYST", "off") or "").lower()
    return val in ("1", "true", "on", "yes")


# Hard wall-clock timeout per analysis (task spec: ≤4 min).
_ANALYSIS_TIMEOUT_SEC = int(os.environ.get("AI_ANALYST_TIMEOUT_SEC", "240"))


# ── DB ────────────────────────────────────────────────────────────────────────
# Tables (`ai_analyst_quota`, `ai_analyst_saved`) are managed centrally by
# app.lib.auth_store.ensure_primary_schema(). We call it on import so a
# hot-restart can serve queries immediately. Postgres handles concurrency
# at the row level — no Python-side write lock needed (this used to be a
# threading.Lock around SQLite).

def _conn():
    """Open a Postgres connection with dict-row results, matching the
    previous SQLite ``conn.row_factory = sqlite3.Row`` access pattern.
    """
    conn = get_conn()
    conn.row_factory = dict_row  # type: ignore[attr-defined]
    return conn


ensure_primary_schema()


def _today_ist() -> str:
    return datetime.now(tz=IST).date().isoformat()


def _midnight_ist_iso() -> str:
    now = datetime.now(tz=IST)
    tomorrow = (now + timedelta(days=1)).date()
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=IST).isoformat()


# ── Quota ─────────────────────────────────────────────────────────────────────

def get_quota(user_id: str) -> dict:
    today = _today_ist()
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT runs_used FROM ai_analyst_quota "
                "WHERE user_id=%s AND run_date_ist=%s",
                (user_id, today),
            )
            row = cur.fetchone()
    used = int(row["runs_used"]) if row else 0
    limit = _daily_quota_limit()
    return {
        "used":         used,
        "limit":        limit,
        "remaining":    max(0, limit - used),
        "resetsAtIst":  _midnight_ist_iso(),
    }


def _increment_quota(user_id: str) -> None:
    today = _today_ist()
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ai_analyst_quota (user_id, run_date_ist, runs_used)
                VALUES (%s, %s, 1)
                ON CONFLICT (user_id, run_date_ist) DO UPDATE SET
                    runs_used = ai_analyst_quota.runs_used + 1
                """,
                (user_id, today),
            )
        c.commit()


def _refund_quota(user_id: str) -> None:
    """Roll back a reserved quota slot if the run failed before producing a report."""
    today = _today_ist()
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                """
                UPDATE ai_analyst_quota
                   SET runs_used = GREATEST(0, runs_used - 1)
                 WHERE user_id = %s AND run_date_ist = %s
                """,
                (user_id, today),
            )
        c.commit()


def _try_reserve_quota(user_id: str, limit: Optional[int] = None) -> bool:
    """Atomically reserve one quota slot. Returns True on success, False if exhausted.

    Uses a single Postgres statement: INSERT a fresh row at runs_used=1, or
    on conflict UPDATE-and-bump only when the existing row is still under
    the cap. The RETURNING clause tells us which path ran. This closes the
    check-then-increment race that mattered for /compare (two parallel
    analyses fanned out from one click).
    """
    if limit is None:
        limit = _daily_quota_limit()
    today = _today_ist()
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ai_analyst_quota (user_id, run_date_ist, runs_used)
                VALUES (%s, %s, 1)
                ON CONFLICT (user_id, run_date_ist) DO UPDATE SET
                    runs_used = ai_analyst_quota.runs_used + 1
                  WHERE ai_analyst_quota.runs_used < %s
                RETURNING runs_used
                """,
                (user_id, today, limit),
            )
            row = cur.fetchone()
        c.commit()
        return row is not None


# ── Saved analyses store ──────────────────────────────────────────────────────
# One persistent row per (user, scope_type, scope_key). Re-running the same
# input upserts the row. No daily expiry — entries live until the user
# deletes them or re-runs (which overwrites).

def _norm_ticker(t: str) -> str:
    return (t or "").upper().strip()


def _pair_scope_key(a: str, b: str) -> tuple[str, list[str]]:
    pair = sorted([_norm_ticker(a), _norm_ticker(b)])
    return "|".join(pair), pair


def _group_scope_key(tickers: list[str]) -> tuple[str, list[str]]:
    cleaned = sorted({_norm_ticker(t) for t in (tickers or []) if _norm_ticker(t)})
    h = hashlib.sha1("|".join(cleaned).encode("utf-8")).hexdigest()
    return h, cleaned


def _row_to_preview(row: dict) -> dict:
    return {
        "id":         int(row["id"]),
        "scope":      row["scope_type"],
        "scopeKey":   row["scope_key"],
        "tickers":    json.loads(row["tickers_json"] or "[]"),
        "label":      row["label"],
        "verdict":    row["verdict"],
        "confidence": row["confidence"],
        "headline":   row["headline"],
        "savedAt":    datetime.fromtimestamp(int(row["updated_at"]), tz=IST).isoformat(),
        "createdAt":  datetime.fromtimestamp(int(row["created_at"]), tz=IST).isoformat(),
    }


def _row_to_full(row: dict) -> dict:
    out = _row_to_preview(row)
    try:
        out["report"] = json.loads(row["report_json"])
    except Exception:
        out["report"] = None
    out["modelsUsed"]  = [m for m in (row["models_used"] or "").split(",") if m]
    out["sourcesUsed"] = [s for s in (row["sources_used"] or "").split(",") if s]
    out["wallClockMs"] = int(row["wall_clock_ms"] or 0)
    return out


def _upsert_saved(user_id: str, scope_type: str, scope_key: str,
                  tickers: list[str], label: Optional[str],
                  verdict: Optional[str], confidence: Optional[str],
                  headline: Optional[str], report: dict,
                  models: list[str], sources: list[str],
                  wall_clock_ms: int) -> int:
    now = int(time.time())
    uid = user_id or "anonymous"
    # Single-statement upsert. RETURNING id avoids the follow-up SELECT we
    # had on SQLite. COALESCE on label preserves a non-null existing label
    # when the new payload didn't supply one.
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ai_analyst_saved
                    (user_id, scope_type, scope_key, tickers_json, label,
                     verdict, confidence, headline, report_json,
                     models_used, sources_used, wall_clock_ms,
                     created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (user_id, scope_type, scope_key) DO UPDATE SET
                    tickers_json  = EXCLUDED.tickers_json,
                    label         = COALESCE(EXCLUDED.label, ai_analyst_saved.label),
                    verdict       = EXCLUDED.verdict,
                    confidence    = EXCLUDED.confidence,
                    headline      = EXCLUDED.headline,
                    report_json   = EXCLUDED.report_json,
                    models_used   = EXCLUDED.models_used,
                    sources_used  = EXCLUDED.sources_used,
                    wall_clock_ms = EXCLUDED.wall_clock_ms,
                    updated_at    = EXCLUDED.updated_at
                RETURNING id
                """,
                (
                    uid, scope_type, scope_key,
                    json.dumps(tickers), label,
                    verdict, confidence, headline,
                    json.dumps(report),
                    ",".join(models), ",".join(sources),
                    int(wall_clock_ms), now, now,
                ),
            )
            row = cur.fetchone()
        c.commit()
        return int(row["id"]) if row else 0


def get_saved_single(ticker: str, user_id: str) -> Optional[dict]:
    """Return the saved single-stock report for ``user_id`` with no day expiry.
    The returned dict is the original report blob with ``cached``/``cachedAt``
    plus the new ``savedAt``/``savedId`` fields tacked on for the frontend."""
    uid = user_id or "anonymous"
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT * FROM ai_analyst_saved "
                "WHERE user_id=%s AND scope_type='single' AND scope_key=%s",
                (uid, _norm_ticker(ticker)),
            )
            row = cur.fetchone()
    if not row:
        return None
    try:
        rpt = json.loads(row["report_json"])
    except Exception:
        return None
    saved_at = datetime.fromtimestamp(int(row["updated_at"]), tz=IST).isoformat()
    rpt["cached"]   = True
    rpt["cachedAt"] = saved_at
    rpt["savedAt"]  = saved_at
    rpt["savedId"]  = int(row["id"])
    return rpt


# Back-compat alias used by ai_analyst.py routes and the orchestrator.
get_cached_report = get_saved_single


def save_single(ticker: str, user_id: str, report: dict, models: list[str],
                sources: list[str], wall_clock_ms: int) -> int:
    upper = _norm_ticker(ticker)
    return _upsert_saved(
        user_id, "single", upper, [upper], None,
        report.get("verdict"), report.get("confidence"),
        report.get("headline"), report,
        models, sources, wall_clock_ms,
    )


# Internal alias used by the orchestrator. Kept under the old name so the
# existing call site doesn't churn.
def _save_report(ticker: str, user_id: str, report: dict, models: list[str],
                 sources: list[str], wall_clock_ms: int) -> None:
    save_single(ticker, user_id, report, models, sources, wall_clock_ms)


def get_saved_pair(a: str, b: str, user_id: str) -> Optional[dict]:
    key, _pair = _pair_scope_key(a, b)
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT * FROM ai_analyst_saved "
                "WHERE user_id=%s AND scope_type='pair' AND scope_key=%s",
                (user_id or "anonymous", key),
            )
            row = cur.fetchone()
    return _row_to_full(row) if row else None


def save_pair(user_id: str, a_report: dict, b_report: dict) -> dict:
    a_t = _norm_ticker(a_report.get("ticker") or "")
    b_t = _norm_ticker(b_report.get("ticker") or "")
    key, pair = _pair_scope_key(a_t, b_t)
    headline = (
        f"{pair[0]} {a_report.get('verdict','?') if pair[0]==a_t else b_report.get('verdict','?')}"
        f" · {pair[1]} {b_report.get('verdict','?') if pair[1]==b_t else a_report.get('verdict','?')}"
    )
    blob = {"a": a_report, "b": b_report}
    new_id = _upsert_saved(
        user_id, "pair", key, pair, None,
        None, None, headline, blob, [], [], 0,
    )
    return {"id": new_id, "scopeKey": key, "tickers": pair}


def get_saved_group(tickers: list[str], user_id: str) -> Optional[dict]:
    key, _ = _group_scope_key(tickers)
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT * FROM ai_analyst_saved "
                "WHERE user_id=%s AND scope_type='group' AND scope_key=%s",
                (user_id or "anonymous", key),
            )
            row = cur.fetchone()
    return _row_to_full(row) if row else None


def save_group(user_id: str, tickers: list[str], items: list[dict],
               name: Optional[str] = None) -> dict:
    key, sorted_t = _group_scope_key(tickers)
    counts = {"BUY": 0, "HOLD": 0, "SELL": 0,
              "skipped": 0, "error": 0, "analyzed": 0, "cached": 0}
    for it in items:
        st = (it.get("status") or "").lower()
        if st in ("analyzed", "cached", "saved"):
            counts[st if st != "saved" else "cached"] = counts.get(
                st if st != "saved" else "cached", 0) + 1
            v = ((it.get("report") or {}).get("verdict") or "").upper()
            if v in counts:
                counts[v] += 1
        elif st == "skipped":
            counts["skipped"] += 1
        elif st == "error":
            counts["error"] += 1
    parts = []
    if counts["BUY"]:  parts.append(f"{counts['BUY']} BUY")
    if counts["HOLD"]: parts.append(f"{counts['HOLD']} HOLD")
    if counts["SELL"]: parts.append(f"{counts['SELL']} SELL")
    if counts["skipped"]: parts.append(f"{counts['skipped']} skipped")
    if counts["error"]:   parts.append(f"{counts['error']} failed")
    headline = f"{len(sorted_t)} stocks · " + (" · ".join(parts) if parts else "no verdicts")
    label = (name or "").strip() or None
    blob = {"tickers": sorted_t, "name": label, "items": items, "counts": counts}
    new_id = _upsert_saved(
        user_id, "group", key, sorted_t, label,
        None, None, headline, blob, [], [], 0,
    )
    return {"id": new_id, "scopeKey": key, "tickers": sorted_t, "label": label}


def list_saved(user_id: str, scope: Optional[str] = None,
               q: Optional[str] = None, limit: int = 50,
               offset: int = 0) -> dict:
    uid = user_id or "anonymous"
    # Build the filter clause + its args once, then reuse for both the
    # paginated SELECT and the unpaginated COUNT — this keeps the two
    # queries provably consistent and avoids any args-slicing tricks.
    where: list[str] = ["user_id = %s"]
    filter_args: list = [uid]
    if scope in ("single", "pair", "group"):
        where.append("scope_type = %s")
        filter_args.append(scope)
    if q:
        where.append("(UPPER(tickers_json) LIKE %s OR UPPER(COALESCE(label,'')) LIKE %s)")
        like = f"%{q.upper()}%"
        filter_args.extend([like, like])
    where_sql = " AND ".join(where)

    lim = max(1, min(200, int(limit)))
    off = max(0, int(offset))
    list_sql = (f"SELECT * FROM ai_analyst_saved WHERE {where_sql} "
                f"ORDER BY updated_at DESC LIMIT %s OFFSET %s")
    count_sql = f"SELECT COUNT(*) AS n FROM ai_analyst_saved WHERE {where_sql}"
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(list_sql, tuple(filter_args + [lim, off]))
            rows = cur.fetchall()
            cur.execute(count_sql, tuple(filter_args))
            total_row = cur.fetchone()
    total = int(total_row["n"]) if total_row else 0
    return {
        "items": [_row_to_preview(r) for r in rows],
        "total": total,
        "limit": lim,
        "offset": off,
    }


def get_saved_by_id(user_id: str, sid: int) -> Optional[dict]:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT * FROM ai_analyst_saved WHERE id=%s AND user_id=%s",
                (int(sid), user_id or "anonymous"),
            )
            row = cur.fetchone()
    return _row_to_full(row) if row else None


def delete_saved(user_id: str, sid: int) -> bool:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "DELETE FROM ai_analyst_saved WHERE id=%s AND user_id=%s",
                (int(sid), user_id or "anonymous"),
            )
            deleted = cur.rowcount > 0
        c.commit()
        return deleted


def delete_saved_bulk(user_id: str, ids: list[int]) -> int:
    """Delete multiple saved analyses by id, scoped to one user.

    Returns the number of rows actually deleted (≤ len(ids)). Rows belonging
    to other users are silently skipped — the `user_id` clause makes this
    safe even when the client sends ids it doesn't own. Empty list returns 0
    without a DB round-trip.
    """
    if not ids:
        return 0
    clean = [int(i) for i in ids if i is not None]
    if not clean:
        return 0
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "DELETE FROM ai_analyst_saved "
                "WHERE id = ANY(%s) AND user_id = %s",
                (clean, user_id or "anonymous"),
            )
            count = cur.rowcount
        c.commit()
    return count


def admin_stats() -> dict:
    """Aggregate metrics for admin dashboard, computed off the saved store."""
    week_ago_ts = int((datetime.now(tz=IST) - timedelta(days=7)).timestamp())
    today_start_ts = int(datetime.now(tz=IST).replace(
        hour=0, minute=0, second=0, microsecond=0).timestamp())
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM ai_analyst_saved WHERE updated_at>=%s",
                (today_start_ts,),
            )
            today_runs = (cur.fetchone() or {}).get("n", 0)
            cur.execute(
                "SELECT COUNT(*) AS n FROM ai_analyst_saved WHERE updated_at>=%s",
                (week_ago_ts,),
            )
            week_runs = (cur.fetchone() or {}).get("n", 0)
            cur.execute(
                "SELECT AVG(wall_clock_ms) AS avg FROM ai_analyst_saved "
                "WHERE updated_at>=%s AND scope_type='single'",
                (week_ago_ts,),
            )
            avg_ms = (cur.fetchone() or {}).get("avg") or 0
            cur.execute(
                """
                SELECT scope_key AS ticker, COUNT(*) AS n FROM ai_analyst_saved
                WHERE updated_at >= %s AND scope_type='single'
                GROUP BY scope_key ORDER BY n DESC LIMIT 10
                """,
                (week_ago_ts,),
            )
            top = cur.fetchall()
    return {
        "todayRuns":        int(today_runs),
        "weekRuns":         int(week_runs),
        "avgWallClockMs":   int(avg_ms or 0),
        "topTickers":       [{"ticker": r["ticker"], "runs": int(r["n"])} for r in top],
        "quotaPerUserDay":  _daily_quota_limit(),
        "quotaDefault":     DEFAULT_DAILY_QUOTA,
    }


def flush_cache() -> int:
    """Wipe the saved analyses store (legacy ai_analyst_reports table was
    dropped during the SQLite→Postgres migration; only ai_analyst_saved
    remains)."""
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("DELETE FROM ai_analyst_saved")
            n = cur.rowcount
        c.commit()
        return n


# ── Data gathering ────────────────────────────────────────────────────────────

async def _gather_context(ticker: str) -> dict:
    """Collect all the Indian-data context blocks the analysts will reason over.
    Each fetch is best-effort; failures degrade to an empty section, never raise."""
    upper = ticker.upper().strip()

    async def _stock_detail():
        try:
            return await _stocks.get_stock_details(upper)
        except Exception as e:
            logger.warning("ai_analyst: stock_details failed for %s: %s", upper, e)
            return {}

    async def _news():
        # RSS feeds are the primary source — they're free, immediate, and
        # already cached. For mid/small-cap tickers the RSS hit rate is
        # thin, so we top up with Tavily when configured and the RSS
        # match count is below `_NEWS_TAVILY_FLOOR`.
        try:
            feed = await news_service.get_news_feed(category="all", limit=80, offset=0)
        except Exception as e:
            logger.warning("ai_analyst: news fetch failed: %s", e)
            feed = {"articles": []}
        sym = upper.replace(".NS", "").replace(".BO", "")
        out: list[dict] = []
        for art in feed.get("articles", [])[:80]:
            tickers = [t.upper() for t in (art.get("tickers") or [])]
            title = (art.get("title") or "").lower()
            if sym in tickers or sym.lower() in title:
                out.append({
                    "title":     art.get("title"),
                    "source":    art.get("source"),
                    "published": art.get("published"),
                    "sentiment": art.get("sentiment"),
                })
            if len(out) >= 8:
                break

        # Tavily top-up: when RSS coverage is thin, fetch from Tavily and
        # merge in unique titles. Configured by TAVILY_API_KEY — if unset,
        # the call returns [] immediately without an HTTP request.
        if len(out) < _NEWS_TAVILY_FLOOR:
            try:
                from . import tavily_service  # noqa: PLC0415
                tav = await tavily_service.search_ticker_news(sym, days=7, max_results=8)
            except Exception as e:
                logger.warning("ai_analyst: tavily fetch failed: %s", e)
                tav = []
            seen_titles = {(a.get("title") or "").lower().strip() for a in out}
            for art in tav:
                t = (art.get("title") or "").lower().strip()
                if not t or t in seen_titles:
                    continue
                seen_titles.add(t)
                out.append({
                    "title":     art.get("title"),
                    "source":    art.get("source"),
                    "published": art.get("published"),
                    "sentiment": art.get("sentiment"),
                })
                if len(out) >= 8:
                    break
        return out

    async def _fii_dii():
        try:
            snap = await FiiDiiService().fetch_equity_snapshot()
            if snap is None or snap.empty:
                return {}
            row = snap.iloc[0]
            return {
                "date":    str(row.get("date")),
                "fiiNet":  float(row.get("fii_net") or 0.0),
                "diiNet":  float(row.get("dii_net") or 0.0),
            }
        except Exception as e:
            logger.warning("ai_analyst: FII/DII fetch failed: %s", e)
            return {}

    detail, news, fii_dii = await asyncio.gather(_stock_detail(), _news(), _fii_dii())
    return {
        "ticker":      upper,
        "stockDetail": detail or {},
        "news":        news,
        "fiiDii":      fii_dii,
        "marketState": mcache.current_market_state(),
        "asOfIst":     datetime.now(tz=IST).isoformat(),
    }


def _fmt_inr(v: Any) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "N/A"
    if abs(n) >= 1e7:
        return f"₹{n/1e7:.2f} Cr"
    if abs(n) >= 1e5:
        return f"₹{n/1e5:.2f} L"
    return f"₹{n:,.2f}"


def _summarise_for_prompt(ctx: dict) -> dict:
    """Boil the full context dict down into compact strings safe to embed in prompts."""
    d = ctx.get("stockDetail") or {}
    ta = d.get("technicalAnalysis") or {}
    info = d.get("info") or {}

    quote_lines = [
        f"Symbol: {ctx['ticker']}",
        f"Name: {info.get('longName') or d.get('companyName') or ctx['ticker']}",
        f"Sector: {info.get('sector') or d.get('sector') or 'N/A'}",
        f"Last price: {_fmt_inr(d.get('lastPrice'))}",
        f"Day change %: {d.get('pChange', 'N/A')}",
        f"52w range: {_fmt_inr(d.get('low52'))} – {_fmt_inr(d.get('high52'))}",
        f"Market cap: {_fmt_inr(info.get('marketCap'))}",
        f"PE (TTM): {info.get('trailingPE', 'N/A')}",
        f"PB: {info.get('priceToBook', 'N/A')}",
        f"ROE: {info.get('returnOnEquity', 'N/A')}",
        f"Profit margin: {info.get('profitMargins', 'N/A')}",
        f"Debt/Equity: {info.get('debtToEquity', 'N/A')}",
        f"Dividend yield: {info.get('dividendYield', 'N/A')}",
    ]
    tech_lines = [
        f"Trend: {ta.get('trend', 'N/A')}",
        f"RSI(14): {ta.get('rsi', 'N/A')}",
        f"MACD: {ta.get('macd', 'N/A')}",
        f"EMA9/21/50/200: {ta.get('ema9')}/{ta.get('ema21')}/{ta.get('ema50')}/{ta.get('ema200')}",
        f"Bollinger upper/lower: {ta.get('bollUpper')}/{ta.get('bollLower')}",
        f"ATR(14): {ta.get('atr', 'N/A')}",
    ]
    news = ctx.get("news") or []
    news_lines = [f"- [{n.get('sentiment','?')}] {n.get('title')} ({n.get('source')})"
                  for n in news[:6]] or ["(no recent India news matched this ticker)"]
    fii = ctx.get("fiiDii") or {}
    if fii:
        flow_line = (f"Latest NSE cash flows ({fii.get('date')}): "
                     f"FII net ₹{fii.get('fiiNet', 0):.0f} cr, "
                     f"DII net ₹{fii.get('diiNet', 0):.0f} cr.")
    else:
        flow_line = "Latest FII/DII flow data unavailable."
    return {
        "quote":  "\n".join(quote_lines),
        "tech":   "\n".join(tech_lines),
        "news":   "\n".join(news_lines),
        "flow":   flow_line,
        "marketState": ctx.get("marketState", "UNKNOWN"),
    }


# ── LLM analyst prompts ───────────────────────────────────────────────────────

_SYSTEM_BASE = (
    "You are an experienced equity research analyst writing for a transparent, "
    "explainable AI research platform serving Indian retail investors. "
    "Frame everything as RESEARCH and EDUCATIONAL ANALYSIS — never as advice "
    "or a directive. Follow SEBI Research Analyst regulations: do not say "
    "'you should buy/sell', use 'the bull case sees…' / 'the bear case sees…' "
    "framing. All prices in INR (₹). Be concise: 130–200 words."
)


def _analyst_prompt(role: str, summary: dict) -> str:
    return f"""You are the {role} ANALYST for {summary['quote'].splitlines()[0]}.

QUOTE & FUNDAMENTALS:
{summary['quote']}

TECHNICALS:
{summary['tech']}

RECENT INDIAN PRESS:
{summary['news']}

MARKET FLOWS:
{summary['flow']}
NSE market state right now: {summary['marketState']}.

Write a 130–200 word analyst note from your domain's perspective only.
Cite the specific data points you used. End with a single one-line
"My read:" sentence framing the situation as research, not advice.
"""


def _debate_prompt(side: str, analyst_notes: dict) -> str:
    return f"""You are the {side} RESEARCHER. Read the four analyst notes
below and argue the {side.lower()} case.

FUNDAMENTALS NOTE:
{analyst_notes['fundamentals']}

NEWS NOTE:
{analyst_notes['news']}

TECHNICALS NOTE:
{analyst_notes['technicals']}

MACRO/FLOW NOTE:
{analyst_notes['macro']}

Write 120–180 words. Quote specific data. End with one line:
"{side} thesis in one sentence:".
"""


def _trader_prompt(analyst_notes: dict, bull: str, bear: str, summary: dict) -> str:
    return f"""You are the TRADER synthesising the desk's research into a
single verdict for {summary['quote'].splitlines()[0]}.

ANALYST NOTES:
- Fundamentals: {analyst_notes['fundamentals']}
- News: {analyst_notes['news']}
- Technicals: {analyst_notes['technicals']}
- Macro/flow: {analyst_notes['macro']}

BULL THESIS:
{bull}

BEAR THESIS:
{bear}

Output STRICT JSON (no prose, no markdown fences) with this exact shape:
{{
  "verdict":      "BUY" | "HOLD" | "SELL",
  "confidence":   "LOW" | "MEDIUM" | "HIGH",
  "headline":     "<one-sentence research framing, max 30 words>",
  "priceTarget":  "<short string in ₹ or 'N/A'>",
  "horizon":      "<e.g. '3-6 months'>",
  "keyRisks":     ["<risk 1>", "<risk 2>"]
}}

Use research framing — never imperatives.
"""


# ── Risk / SEBI compliance gate ───────────────────────────────────────────────

_ADVICE_REPLACEMENTS = [
    # Imperatives → research framing
    (re.compile(r"\byou (should|must|need to|ought to) (buy|sell|hold|short|exit|enter|invest|accumulate|book|trim|add|reduce)\b", re.I),
     r"the research view is to consider \2ing"),
    (re.compile(r"\b(I|we|our team) (recommend|advise|suggest)s? (buying|selling|holding|shorting|accumulating|booking|trimming|adding|reducing)\b", re.I),
     r"this analysis points to \3"),
    (re.compile(r"\b(strong|firm|clear|sure-shot|sureshot)\s+(buy|sell|hold)\b", re.I),
     r"a high-conviction \2-side bias in the research"),
    (re.compile(r"\bbuy (now|today|here|the dip|on dips|at cmp|at this level)\b", re.I),
     "the bull case is intact at current levels"),
    (re.compile(r"\bsell (now|today|here|on rallies|at cmp|at this level)\b", re.I),
     "the bear case is intact at current levels"),
    (re.compile(r"\b(enter|exit|book profit(?:s)?|book loss(?:es)?)\s+(now|today|here|on dips|on rallies|at cmp|at this level)\b", re.I),
     r"the research framing for \1ing improves at these levels"),
    (re.compile(r"\b(must|should)\s+(accumulate|hold|exit|trim|book)\b", re.I),
     r"the analysis suggests \2ing"),
    (re.compile(r"\b(go|going)\s+(long|short)\b", re.I),
     r"the \2 case is supported"),
    # Outcome guarantees
    (re.compile(r"\b(guaranteed|assured|risk[-\s]?free)\s+(profit|return|gain|win)s?\b", re.I),
     "potential outcome (no guarantees)"),
    (re.compile(r"\b(can[''\u2019\u2018]?t lose|sure[-\s]?shot|sureshot|no[-\s]?brainer|nobrainer)\b", re.I),
     "high-conviction (still subject to market risk)"),
    (re.compile(r"\bmultibagger\b", re.I),
     "structurally compounding"),
    (re.compile(r"\b(target price is|price target of)\b", re.I),
     "the research points to a target around"),
]


def _scrub_advice(text: str) -> str:
    if not text:
        return text
    out = text
    for pat, repl in _ADVICE_REPLACEMENTS:
        out = pat.sub(repl, out)
    return out


def _scrub_report(report: dict) -> dict:
    """Apply SEBI compliance scrub across every user-visible string in the report.
    Defence-in-depth: even if an upstream prompt slips, this final pass catches it."""
    for k in ("headline", "priceTarget", "horizon"):
        if isinstance(report.get(k), str):
            report[k] = _scrub_advice(report[k])
    if isinstance(report.get("keyRisks"), list):
        report["keyRisks"] = [_scrub_advice(str(r)) for r in report["keyRisks"]]
    if isinstance(report.get("analysts"), dict):
        report["analysts"] = {k: _scrub_advice(v or "")
                              for k, v in report["analysts"].items()}
    if isinstance(report.get("debate"), dict):
        report["debate"] = {k: _scrub_advice(v or "")
                            for k, v in report["debate"].items()}
    return report


SEBI_DISCLAIMER = (
    "AI-generated research only — not investment advice. Generated by an "
    "automated multi-agent LLM pipeline; outputs may be inaccurate or "
    "incomplete. Not a SEBI-registered Research Analyst recommendation. "
    "Markets carry risk; consult a SEBI-registered advisor before acting."
)


# ── Orchestrator ──────────────────────────────────────────────────────────────

ANALYST_ROLES = [
    ("fundamentals", "FUNDAMENTALS"),
    ("news",         "NEWS & SENTIMENT"),
    ("technicals",   "TECHNICALS"),
    ("macro",        "MACRO & FLOW"),
]


def _ev(phase: str, agent: str = "", status: str = "running",
        partial: str = "", **extra) -> dict:
    e = {"phase": phase, "agent": agent, "status": status,
         "ts": datetime.now(tz=IST).isoformat()}
    if partial:
        e["partialText"] = partial
    e.update(extra)
    return e


async def _run_analyst(role_key: str, role_label: str, summary: dict) -> tuple[str, str]:
    note = await ai_client.ask(
        _analyst_prompt(role_label, summary),
        system=_SYSTEM_BASE,
        max_tokens=600,
        temperature=0.4,
    )
    return role_key, _scrub_advice(note or "").strip()


async def _safe_json(text: str) -> dict:
    """Best-effort JSON parse from a model reply."""
    if not text:
        return {}
    s = text.strip()
    # Strip markdown fences if any
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.M).strip()
    # Find first {...} block
    m = re.search(r"\{.*\}", s, re.S)
    if m:
        s = m.group(0)
    try:
        return json.loads(s)
    except Exception:
        return {}


async def _run_analysis_impl(ticker: str, user_id: str,
                              force_refresh: bool = False) -> AsyncGenerator[dict, None]:
    """Inner pipeline. Wrap with `run_analysis` to enforce the wall-clock budget."""
    upper = (ticker or "").upper().strip()
    if not upper:
        yield _ev("error", status="error", error="Ticker is required")
        return

    if not feature_enabled():
        yield _ev("error", status="error", error="AI Analyst feature is disabled")
        return

    if not ai_client.is_available():
        yield _ev("error", status="error",
                  error="OpenRouter is not configured. Ask an admin to set "
                        "AI_INTEGRATIONS_OPENROUTER_API_KEY in Admin → Integrations.")
        return

    # Cache hit (per-user)
    if not force_refresh:
        cached = get_cached_report(upper, user_id)
        if cached:
            yield _ev("cached", status="done")
            yield _ev("done", status="done", report=cached)
            return

    # Atomic quota reservation — closes the check-then-increment race
    # (matters for /compare which launches two analyses in parallel).
    if not _try_reserve_quota(user_id):
        yield _ev("error", status="error", error="quota_exceeded",
                  quota=get_quota(user_id))
        return
    # `quota_reserved` is a single-element list so the post-reservation
    # generator block can flip it via assignment AND the outer
    # try/except/finally can still see the latest value.
    # On client disconnect / asyncio cancellation the runtime calls
    # aclose() on this generator, which raises GeneratorExit at the
    # current `yield` — we MUST refund the reserved slot in that case
    # so a stop-mid-scan doesn't burn quota the user never received a
    # report for.
    quota_reserved = [True]

    started = time.time()
    sources_used: list[str] = []
    models_used: list[str] = []

    try:
      # Phase 0 — gather context
      yield _ev("context", status="running")
      ctx = await _gather_context(upper)
      summary = _summarise_for_prompt(ctx)
      if ctx.get("stockDetail"):
          sources_used.append("stocks_service")
      if ctx.get("news"):
          sources_used.append("news_service")
      if ctx.get("fiiDii"):
          sources_used.append("fii_dii_service")
      yield _ev("context", status="done")

      if not ctx.get("stockDetail") or (ctx["stockDetail"] or {}).get("error"):
          # Refund the reserved quota slot — we never made any LLM calls.
          if quota_reserved[0]:
              _refund_quota(user_id)
              quota_reserved[0] = False
          yield _ev("error", status="error",
                    error=f"Could not load market data for {upper}. "
                          f"Check the ticker (e.g. RELIANCE, TCS, INFY).")
          return

      # Phase 1 — analysts in parallel
      notes: dict[str, str] = {}
      for key, _ in ANALYST_ROLES:
          yield _ev("analyst", agent=key, status="pending")

      # Mark all running, then await
      for key, _ in ANALYST_ROLES:
          yield _ev("analyst", agent=key, status="running")
      results = await asyncio.gather(*[
          _run_analyst(key, label, summary) for key, label in ANALYST_ROLES
      ], return_exceptions=True)
      models_used.append(ai_client.AI_MODEL)
      for r in results:
          if isinstance(r, tuple):
              k, txt = r
              notes[k] = txt
              yield _ev("analyst", agent=k, status="done", partial=txt)
          else:
              logger.warning("Analyst gather error: %s", r)

      # Backfill any analyst that errored so the debate has all four notes
      for k, _ in ANALYST_ROLES:
          notes.setdefault(k, "(analyst note unavailable)")

      # Phase 2 — Bull vs Bear (in parallel)
      yield _ev("debate", agent="bull", status="running")
      yield _ev("debate", agent="bear", status="running")
      bull_task = ai_client.ask(_debate_prompt("BULL", notes),
                                system=_SYSTEM_BASE, max_tokens=500, temperature=0.5)
      bear_task = ai_client.ask(_debate_prompt("BEAR", notes),
                                system=_SYSTEM_BASE, max_tokens=500, temperature=0.5)
      bull_text, bear_text = await asyncio.gather(bull_task, bear_task,
                                                  return_exceptions=True)
      bull_text = _scrub_advice((bull_text if isinstance(bull_text, str)
                                 else "(bull researcher unavailable)").strip())
      bear_text = _scrub_advice((bear_text if isinstance(bear_text, str)
                                 else "(bear researcher unavailable)").strip())
      yield _ev("debate", agent="bull", status="done", partial=bull_text)
      yield _ev("debate", agent="bear", status="done", partial=bear_text)

      # Phase 3 — Trader synthesis (JSON verdict)
      yield _ev("trader", status="running")
      trader_raw = await ai_client.ask(
          _trader_prompt(notes, bull_text, bear_text, summary),
          system=_SYSTEM_BASE + " Reply with strict JSON only.",
          max_tokens=400,
          temperature=0.2,
      )
      verdict_obj = await _safe_json(trader_raw)
      verdict = (verdict_obj.get("verdict") or "HOLD").upper()
      if verdict not in ("BUY", "HOLD", "SELL"):
          verdict = "HOLD"
      confidence = (verdict_obj.get("confidence") or "MEDIUM").upper()
      headline = _scrub_advice((verdict_obj.get("headline") or
                                "Synthesis incomplete — review the analyst notes.").strip())

      # ── Anti-FOMO / bias-rate check ───────────────────────────────────────
      # If the verdict is BUY but the stock is already trading well above its
      # 20-day moving average, downgrade to HOLD with a "wait for pullback"
      # warning. Strong trend stacks (MA5>MA10>MA20) get a relaxed threshold
      # so legitimate momentum setups aren't suppressed. See bias_check.py.
      from . import bias_check  # noqa: PLC0415
      ta = (ctx.get("stockDetail") or {}).get("technicalAnalysis") or {}
      bb_middle = ((ta.get("bollingerBands") or {}).get("middle"))
      last_price_for_bias = (ctx.get("stockDetail") or {}).get("lastPrice") \
                            or ta.get("currentPrice")
      hist_closes = [
          float(row.get("close") or 0)
          for row in ((ctx.get("stockDetail") or {}).get("historicalData") or [])
          if row.get("close") is not None
      ]
      bias_assessment = bias_check.assess(
          last_price=last_price_for_bias,
          closes=hist_closes if hist_closes else None,
          # bb_middle is SMA20 by Bollinger Bands convention; use it as our
          # MA20 anchor when present (cheaper than re-deriving from closes).
          ma20=float(bb_middle) if bb_middle is not None else None,
      )
      downgraded_verdict, bias_warning = bias_check.downgrade_verdict_if_chasing(
          verdict, bias_assessment,
      )
      if downgraded_verdict != verdict:
          logger.info(
              "ai_analyst: %s BUY→%s (bias=%.1f%% > %s%%)",
              upper, downgraded_verdict,
              bias_assessment.get("biasPct") or 0,
              bias_assessment.get("threshold"),
          )
          verdict = downgraded_verdict

      yield _ev("trader", status="done", partial=json.dumps(verdict_obj))

      # Phase 4 — Risk gate
      yield _ev("risk", status="running")
      # Already scrubbed all components; the risk gate is the final assembly.
      # If the bias check fired, prepend the warning to keyRisks so it's the
      # first thing the user sees — and lower the confidence one notch.
      base_risks = verdict_obj.get("keyRisks") or []
      if bias_warning:
          base_risks = [bias_warning] + list(base_risks)
          # Step confidence down one notch when we downgraded — keeps the
          # report honest about the regime change.
          if confidence == "HIGH":
              confidence = "MEDIUM"
          elif confidence == "MEDIUM":
              confidence = "LOW"

      report = {
          "ticker":     upper,
          "name":       (ctx["stockDetail"].get("info") or {}).get("longName")
                         or ctx["stockDetail"].get("companyName") or upper,
          "verdict":    verdict,
          "confidence": confidence,
          "headline":   headline,
          "priceTarget": verdict_obj.get("priceTarget") or "N/A",
          "horizon":    verdict_obj.get("horizon") or "3-6 months",
          "keyRisks":   base_risks,
          "biasCheck":  bias_assessment,
          "analysts": {
              "fundamentals": notes.get("fundamentals", ""),
              "news":         notes.get("news", ""),
              "technicals":   notes.get("technicals", ""),
              "macro":        notes.get("macro", ""),
          },
          "debate": {
              "bull": bull_text,
              "bear": bear_text,
          },
          "snapshot": {
              "lastPrice":   ctx["stockDetail"].get("lastPrice"),
              "pChange":     ctx["stockDetail"].get("pChange"),
              "marketState": ctx.get("marketState"),
              "asOfIst":     ctx.get("asOfIst"),
          },
          "modelsUsed":  list(dict.fromkeys(models_used)),
          "sourcesUsed": sources_used,
          "disclaimer":  SEBI_DISCLAIMER,
          "cached":      False,
      }
      # Final defence-in-depth scrub pass across every user-visible string.
      report = _scrub_report(report)
      yield _ev("risk", status="done")

      elapsed_ms = int((time.time() - started) * 1000)
      report["wallClockMs"] = elapsed_ms

      # Persist (quota was already reserved atomically before LLM calls).
      try:
          _save_report(upper, user_id, report, models_used, sources_used, elapsed_ms)
      except Exception as e:
          logger.warning("Failed to persist AI analyst report: %s", e)

      # User actually received a report — the reserved slot is rightfully spent.
      quota_reserved[0] = False
      new_quota = get_quota(user_id)
      try:
          yield _ev("done", status="done", report=report, quota=new_quota)
      except (asyncio.CancelledError, GeneratorExit):
          # Client disconnected at the very last frame — the report is
          # persisted to the shared cache anyway, so quota was earned. Just
          # propagate so the runtime closes cleanly.
          raise
    except (asyncio.CancelledError, GeneratorExit):
        # Client disconnected (browser navigated away, Stop pressed,
        # request aborted). Refund the reserved quota slot — the user
        # never got a finished report.
        if quota_reserved[0]:
            _refund_quota(user_id)
            quota_reserved[0] = False
        raise


async def scan_watchlist(tickers: list, user_id: str,
                         force_refresh: bool = False,
                         group_name: Optional[str] = None) -> AsyncGenerator[dict, None]:
    """Scan a list of tickers sequentially.

    Strategy (cost-aware):
      1. For each ticker, serve today's shared cached report immediately
         (free — does NOT touch the user's quota).
      2. For uncached tickers, attempt a fresh run only while the user has
         remaining quota. Stop cleanly with a `quota_exhausted` event when
         out, marking the rest as `skipped`.

    Yields:
      - {phase:"start", total, queued:[…]}
      - {phase:"item", ticker, status:"cached"|"analyzing"}
      - {phase:"result", ticker, report}                      (success)
      - {phase:"result", ticker, error, status:"error"}       (per-item failure)
      - {phase:"result", ticker, status:"skipped",
         reason:"quota_exhausted"}                            (out of quota)
      - {phase:"done", processed, cached, analyzed, skipped, errors,
         quota:{…}}
    """
    # Normalise + dedupe in order
    seen = set()
    queue = []
    for t in (tickers or []):
        u = (t or "").upper().strip()
        if u and u not in seen:
            seen.add(u)
            queue.append(u)

    if not queue:
        yield _ev("done", processed=0, cached=0, analyzed=0,
                  skipped=0, errors=0, quota=get_quota(user_id))
        return

    yield _ev("start", total=len(queue), queued=queue)

    cached_n = analyzed_n = skipped_n = errors_n = 0
    items_for_save: list[dict] = []

    for tk in queue:
        # 1. Serve the user's saved report if present and the caller hasn't
        #    asked for a refresh. Cache hits do NOT count against the quota.
        if not force_refresh:
            saved = get_saved_single(tk, user_id)
            if saved:
                cached_n += 1
                # Emit both "saved" (new) and the legacy "cached" string in
                # the same event so older clients keep working.
                yield _ev("item", ticker=tk, status="saved")
                yield _ev("result", ticker=tk, status="saved", report=saved)
                items_for_save.append({"ticker": tk, "status": "saved",
                                       "report": saved})
                continue

        # 2. Need a fresh run — check quota first (peek; reservation is atomic
        #    inside _run_analysis_impl). If clearly out, skip without trying.
        q = get_quota(user_id)
        if q.get("remaining", 0) <= 0:
            skipped_n += 1
            yield _ev("result", ticker=tk, status="skipped",
                      reason="quota_exhausted")
            items_for_save.append({"ticker": tk, "status": "skipped",
                                   "reason": "quota_exhausted"})
            continue

        yield _ev("item", ticker=tk, status="analyzing")
        final = None
        per_item_error = None
        async for ev in run_analysis(tk, user_id, force_refresh=force_refresh):
            phase = ev.get("phase")
            if phase == "done":
                final = ev.get("report")
            elif phase == "error":
                per_item_error = ev.get("error", "unknown error")
                # If quota was the cause, mark as skipped instead of error.
                if "quota" in (per_item_error or "").lower():
                    skipped_n += 1
                    yield _ev("result", ticker=tk, status="skipped",
                              reason=per_item_error)
                    items_for_save.append({"ticker": tk, "status": "skipped",
                                           "reason": per_item_error})
                    per_item_error = "__handled__"
                    break
        if per_item_error == "__handled__":
            continue
        if per_item_error:
            errors_n += 1
            yield _ev("result", ticker=tk, status="error",
                      error=per_item_error)
            items_for_save.append({"ticker": tk, "status": "error",
                                   "error": per_item_error})
        elif final:
            analyzed_n += 1
            yield _ev("result", ticker=tk, status="analyzed", report=final)
            items_for_save.append({"ticker": tk, "status": "analyzed",
                                   "report": final})
        else:
            errors_n += 1
            yield _ev("result", ticker=tk, status="error",
                      error="no report produced")
            items_for_save.append({"ticker": tk, "status": "error",
                                   "error": "no report produced"})

    # Persist the whole scan as a saved group entry (upsert per scope_key).
    saved_meta = None
    try:
        saved_meta = save_group(user_id, queue, items_for_save,
                                name=group_name)
    except Exception as e:  # pragma: no cover
        logger.warning("save_group failed: %s", e)

    yield _ev("done",
              processed=cached_n + analyzed_n + errors_n,
              cached=cached_n, analyzed=analyzed_n,
              skipped=skipped_n, errors=errors_n,
              quota=get_quota(user_id),
              saved=saved_meta)


async def run_analysis(ticker: str, user_id: str,
                       force_refresh: bool = False) -> AsyncGenerator[dict, None]:
    """Public entry point — enforces a hard wall-clock budget around the
    inner pipeline (task spec: fail gracefully within ~4 minutes)."""
    inner = _run_analysis_impl(ticker, user_id, force_refresh=force_refresh)
    deadline = time.time() + _ANALYSIS_TIMEOUT_SEC
    try:
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                yield _ev("error", status="error",
                          error=f"Analysis exceeded {_ANALYSIS_TIMEOUT_SEC}s budget. "
                                f"Try again later — the model may be slow right now.")
                # Quota refund is owned by `_run_analysis_impl`'s GeneratorExit
                # handler, which fires when `inner.aclose()` runs in the finally
                # below. Refunding here too would double-decrement the slot and
                # could let other concurrent runs exceed the daily limit.
                return
            try:
                ev = await asyncio.wait_for(inner.__anext__(), timeout=remaining)
            except StopAsyncIteration:
                return
            except asyncio.TimeoutError:
                yield _ev("error", status="error",
                          error=f"Analysis exceeded {_ANALYSIS_TIMEOUT_SEC}s budget.")
                # Same — refund happens once via aclose() → GeneratorExit.
                return
            yield ev
    finally:
        # Make sure the inner generator is fully closed even on early return.
        # This is what triggers the cancellation-refund path in
        # `_run_analysis_impl` for both timeouts and client disconnects.
        try:
            await inner.aclose()
        except Exception:  # pragma: no cover
            pass
