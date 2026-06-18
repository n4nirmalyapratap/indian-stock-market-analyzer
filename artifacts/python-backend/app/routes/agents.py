"""
agents.py — Famous-Investor AI Council endpoints.

  GET  /api/agents                         — list the 16 personas
  GET  /api/agents/screener/consensus      — near-unanimous buy/avoid picks from Nifty 50
  GET  /api/agents/{symbol}                — run all 16 checklists (fast, no LLM)
  GET  /api/agents/{symbol}/council        — same + AI-written thesis per persona
  GET  /api/agents/{symbol}/{persona_id}   — single persona deep view + thesis
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services import agents_service
from ..services import registry as svc
from ..lib.symbol_map import yahoo_candidates
from ..lib.universe import get_scan_universe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])



# Module-level info cache (24 h) — fundamentals don't move minute-by-minute.
_INFO_CACHE: dict[str, tuple[float, dict]] = {}
_INFO_TTL_S  = 24 * 3600


async def _fetch_yf_info(symbol: str) -> dict:
    """Fetch raw yfinance .info for fundamentals (ROE, margins, ratios, etc.).
    Heavy: yf.Ticker(...).info hits Yahoo synchronously, so it runs in a
    thread.  Cached for 24 h."""
    import asyncio as _asyncio
    import time as _time
    import yfinance as yf  # noqa: PLC0415 — lazy import; yfinance is heavy

    key = symbol.upper()
    cached = _INFO_CACHE.get(key)
    if cached and (_time.time() - cached[0]) < _INFO_TTL_S:
        return cached[1]

    def _do() -> dict:
        for tk_sym in yahoo_candidates(key):
            try:
                tk = yf.Ticker(tk_sym)
                info = tk.info or {}
                if info.get("regularMarketPrice") or info.get("marketCap") or info.get("longName"):
                    return info
            except Exception:
                continue
        return {}

    try:
        info = await _asyncio.to_thread(_do)
    except Exception as exc:
        logger.warning("yf.Ticker(%s).info failed: %s", key, exc)
        info = {}
    _INFO_CACHE[key] = (_time.time(), info)
    return info


async def _load_stock(symbol: str) -> tuple[dict | None, JSONResponse | None]:
    """Fetch the rich stock detail + raw yfinance .info merged together."""
    upper = (symbol or "").upper().strip()
    if not upper:
        return None, JSONResponse(status_code=400, content={"error": "symbol is required"})

    try:
        detail = await svc.stocks.get_stock_details(upper)
    except Exception as exc:
        logger.warning("agents._load_stock: stock_details failed for %s: %s", upper, exc)
        return None, JSONResponse(status_code=502,
                                  content={"error": f"Failed to load {upper}: {exc}"})

    if not detail or detail.get("error"):
        return None, JSONResponse(status_code=404,
                                  content={"error": (detail or {}).get("error") or f"{upper} not found"})

    info = await _fetch_yf_info(upper)
    if info:
        # Don't clobber StocksService keys — yfinance is a supplement.
        merged = {**info, **detail}
        merged["info"] = info
        return merged, None

    return detail, None


@router.get("")
async def list_agents():
    """Return the 16 investor personas with their philosophies."""
    return {"personas": agents_service.list_personas(),
            "count":    len(agents_service.PERSONAS)}


# ── Consensus screener (SQLite-backed, background scan) ──────────────────────
#
# Architecture:
#   * Universe = the FULL tradeable NSE equity list (~2,000 main-board symbols)
#     from get_scan_universe() (security-registry backed). Snapshotted at import;
#     a restart picks up the daily registry refresh. The scan is cache-first:
#     results persist in SQLite and a background scan streams updates in, so the
#     large universe never blocks a request.
#   * Results persist in market_cache/agents_screener.db (WAL SQLite) so they
#     survive backend restarts and only one full scan happens per NSE session.
#   * GET returns cached rows IMMEDIATELY and kicks off a background scan if
#     the cache is empty or stale. The response includes a progress block so the
#     UI can poll and show a live "scanning 412 / 2000" indicator.

_SCREENER_UNIVERSE: list[str] = get_scan_universe()
_SCREENER_THRESHOLD   = 14          # of 16 personas — 87.5%
_SCREENER_CONCURRENCY = 8           # parallel yfinance requests (rate-limit safe)
_SCREENER_DB          = Path(__file__).parent.parent.parent / "market_cache" / "agents_screener.db"
_IST                  = ZoneInfo("Asia/Kolkata")
_NSE_CLOSE_HOUR       = 15          # NSE settles at 15:30 IST
_NSE_CLOSE_MINUTE     = 30
# Grace window after close before we trust EOD data sources to have caught up.
_POST_CLOSE_GRACE_MIN = 30          # → refresh kicks in at 16:00 IST


def _most_recent_nse_close() -> float:
    """Return the unix timestamp of the most recent NSE market close.

    Logic: take 'now' in IST, walk back day-by-day until we land on a weekday
    whose 16:00 IST has already passed. That weekday's 15:30 IST close is the
    most recent settlement. If today is a weekday and we are past 16:00 IST,
    today qualifies; otherwise the previous trading day qualifies. This
    correctly handles weekends and pre-market intraday calls.
    """
    now_ist = datetime.now(_IST)
    today_close = now_ist.replace(hour=_NSE_CLOSE_HOUR,
                                  minute=_NSE_CLOSE_MINUTE,
                                  second=0, microsecond=0)
    cutoff = today_close + timedelta(minutes=_POST_CLOSE_GRACE_MIN)
    candidate = now_ist if now_ist >= cutoff else now_ist - timedelta(days=1)
    # Walk back over weekends (Sat=5, Sun=6) to land on Friday's close.
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    close = candidate.replace(hour=_NSE_CLOSE_HOUR,
                              minute=_NSE_CLOSE_MINUTE,
                              second=0, microsecond=0)
    return close.timestamp()

_SCAN_LOCK  = threading.Lock()
_SCAN_STATE = {"in_progress": False, "done": 0, "total": 0, "started_at": 0.0}


def _db_conn() -> sqlite3.Connection:
    _SCREENER_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_SCREENER_DB, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _db_init() -> None:
    with _db_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS picks (
                symbol           TEXT PRIMARY KEY,
                name             TEXT,
                sector           TEXT,
                last_price       REAL,
                buy_count        INTEGER NOT NULL DEFAULT 0,
                avoid_count      INTEGER NOT NULL DEFAULT 0,
                hold_count       INTEGER NOT NULL DEFAULT 0,
                avg_score        REAL    NOT NULL DEFAULT 0,
                council_verdict  TEXT,
                updated_at       REAL    NOT NULL
            )
        """)
        c.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")


def _db_upsert(row: dict) -> None:
    with _db_conn() as c:
        c.execute("""
            INSERT INTO picks(symbol, name, sector, last_price, buy_count, avoid_count,
                              hold_count, avg_score, council_verdict, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol) DO UPDATE SET
                name=excluded.name, sector=excluded.sector, last_price=excluded.last_price,
                buy_count=excluded.buy_count, avoid_count=excluded.avoid_count,
                hold_count=excluded.hold_count, avg_score=excluded.avg_score,
                council_verdict=excluded.council_verdict, updated_at=excluded.updated_at
        """, (
            row["symbol"], row.get("name"), row.get("sector"), row.get("lastPrice"),
            row["buyCount"], row["avoidCount"], row["holdCount"],
            row["avgScore"], row["councilVerdict"], time.time(),
        ))


def _db_meta_set(key: str, value: str) -> None:
    with _db_conn() as c:
        c.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def _db_meta_get(key: str) -> str | None:
    with _db_conn() as c:
        cur = c.execute("SELECT value FROM meta WHERE key=?", (key,))
        r = cur.fetchone()
        return r["value"] if r else None


def _db_read_all() -> list[dict]:
    with _db_conn() as c:
        cur = c.execute("SELECT * FROM picks")
        return [dict(r) for r in cur.fetchall()]


async def _run_one(symbol: str) -> dict | None:
    """Load stock + run fast council for one symbol; returns None on failure."""
    try:
        detail, err = await _load_stock(symbol)
        if err is not None or detail is None:
            return None
        result  = agents_service.run_council(detail)
        council = result.get("council", {})
        return {
            "symbol":         result.get("symbol", symbol),
            "name":           result.get("name"),
            "sector":         result.get("sector"),
            "lastPrice":      result.get("lastPrice"),
            "buyCount":       council.get("buyCount", 0),
            "avoidCount":     council.get("avoidCount", 0),
            "holdCount":      council.get("holdCount", 0),
            "avgScore":       round(council.get("avgScore", 0), 4),
            "councilVerdict": council.get("verdict", "HOLD"),
        }
    except Exception as exc:
        logger.debug("screener: failed for %s: %s", symbol, exc)
        return None


async def _background_scan() -> None:
    """Iterate the universe with bounded concurrency, upserting rows as they
    finish so the UI sees results stream in during polling."""
    logger.info("agents.screener: starting scan of %d symbols (concurrency=%d)",
                len(_SCREENER_UNIVERSE), _SCREENER_CONCURRENCY)
    sem = asyncio.Semaphore(_SCREENER_CONCURRENCY)

    async def _worker(sym: str) -> None:
        async with sem:
            row = await _run_one(sym)
            if row:
                try:
                    _db_upsert(row)
                except Exception as exc:
                    logger.warning("agents.screener: db upsert failed for %s: %s", sym, exc)
            _SCAN_STATE["done"] += 1

    try:
        await asyncio.gather(*[_worker(s) for s in _SCREENER_UNIVERSE],
                             return_exceptions=True)
        _db_meta_set("last_scan_at", str(time.time()))
        _db_meta_set("last_scan_universe", str(len(_SCREENER_UNIVERSE)))
        logger.info("agents.screener: scan complete in %ds",
                    int(time.time() - _SCAN_STATE["started_at"]))
    finally:
        with _SCAN_LOCK:
            _SCAN_STATE["in_progress"] = False


def _maybe_kick_scan(force: bool = False) -> None:
    """Start a background scan if the cache is stale/empty and no scan is
    already running. Claims the in-progress flag inside the lock to avoid the
    race where two simultaneous requests both kick off a scan."""
    with _SCAN_LOCK:
        if _SCAN_STATE["in_progress"]:
            return
        if not force:
            last        = _db_meta_get("last_scan_at")
            last_ts     = float(last) if last else 0.0
            last_close  = _most_recent_nse_close()
            # Fresh only if the last scan completed AFTER the most recent NSE
            # close — i.e. the cache reflects today's settlement (or Friday's
            # on a weekend). Otherwise we re-scan in the background.
            if last_ts >= last_close:
                return
        _SCAN_STATE.update(
            in_progress=True, done=0,
            total=len(_SCREENER_UNIVERSE), started_at=time.time(),
        )
    try:
        asyncio.create_task(_background_scan())
    except RuntimeError as exc:
        logger.error("agents.screener: cannot start scan: %s", exc)
        with _SCAN_LOCK:
            _SCAN_STATE["in_progress"] = False


def _row_to_pick(r: dict) -> dict:
    return {
        "symbol":         r["symbol"],
        "name":           r["name"],
        "sector":         r["sector"],
        "lastPrice":      r["last_price"],
        "buyCount":       r["buy_count"],
        "avoidCount":     r["avoid_count"],
        "holdCount":      r["hold_count"],
        "total":          r["buy_count"] + r["avoid_count"] + r["hold_count"],
        "avgScore":       r["avg_score"],
        "councilVerdict": r["council_verdict"] or "HOLD",
    }


@router.get("/screener/consensus")
async def get_consensus_screener(refresh: int = 0):
    """Screen large + mid + small-cap NSE stocks for near-unanimous council
    consensus.

    Returns whatever is currently cached in SQLite IMMEDIATELY (so the UI never
    waits more than a few ms), plus a status block telling the client whether a
    background scan is in progress. Pass ``?refresh=1`` to force a re-scan.
    """
    _db_init()
    _maybe_kick_scan(force=bool(refresh))

    rows = _db_read_all()

    buy_picks = sorted(
        [_row_to_pick(r) for r in rows if r["buy_count"]   >= _SCREENER_THRESHOLD],
        key=lambda x: x["avgScore"], reverse=True,
    )
    avoid_picks = sorted(
        [_row_to_pick(r) for r in rows if r["avoid_count"] >= _SCREENER_THRESHOLD],
        key=lambda x: x["avgScore"],
    )

    last = _db_meta_get("last_scan_at")
    cached_at = (
        datetime.fromtimestamp(float(last), timezone.utc)
                .isoformat().replace("+00:00", "Z")
        if last else None
    )

    return {
        "buyPicks":       buy_picks,
        "avoidPicks":     avoid_picks,
        "thresholdPct":   round(_SCREENER_THRESHOLD / 16 * 100, 1),
        "thresholdCount": _SCREENER_THRESHOLD,
        "totalScreened":  len(rows),
        "universeSize":   len(_SCREENER_UNIVERSE),
        "cachedAt":       cached_at,
        "scanInProgress": _SCAN_STATE["in_progress"],
        "scanProgress":   (
            {"done": _SCAN_STATE["done"], "total": _SCAN_STATE["total"]}
            if _SCAN_STATE["in_progress"] else None
        ),
    }


@router.get("/{symbol}")
async def get_council_fast(symbol: str):
    """Fast deterministic council — checklists only, no LLM."""
    detail, err = await _load_stock(symbol)
    if err is not None:
        return err
    try:
        return agents_service.run_council(detail)
    except Exception as exc:
        logger.exception("Council evaluation failed for %s", symbol)
        return JSONResponse(status_code=500, content={"error": f"Council failed: {exc}"})


@router.get("/{symbol}/council")
async def get_council_full(symbol: str):
    """Full council with AI-written thesis per persona (slower — ~8 LLM calls)."""
    detail, err = await _load_stock(symbol)
    if err is not None:
        return err
    try:
        return await agents_service.run_council_with_theses(detail)
    except Exception as exc:
        logger.exception("Council-with-theses failed for %s", symbol)
        return JSONResponse(status_code=500, content={"error": f"Council failed: {exc}"})


@router.get("/{symbol}/{persona_id}")
async def get_single_persona(symbol: str, persona_id: str):
    """Deep dive on a single persona's verdict + AI thesis."""
    pid = (persona_id or "").lower().strip()
    # Defence-in-depth: the catch-all `council` was already routed above, so
    # any other reserved word reaching here is genuinely an unknown persona.
    if pid not in agents_service.PERSONA_BY_ID:
        return JSONResponse(status_code=404,
                            content={"error": f"Unknown persona: {persona_id}",
                                     "available": list(agents_service.PERSONA_BY_ID.keys())})

    detail, err = await _load_stock(symbol)
    if err is not None:
        return err
    try:
        return await agents_service.run_single_persona(pid, detail)
    except Exception as exc:
        logger.exception("Single persona evaluation failed: %s / %s", symbol, pid)
        return JSONResponse(status_code=500, content={"error": f"Persona evaluation failed: {exc}"})
