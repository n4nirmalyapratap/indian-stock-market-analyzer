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
import time
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services import agents_service
from ..services.stocks_service import StocksService
from ..services.nse_service import NseService
from ..services.yahoo_service import YahooService
from ..lib.symbol_map import yahoo_candidates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])

_nse    = NseService()
_yahoo  = YahooService()
_stocks = StocksService(_nse, _yahoo)


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
        detail = await _stocks.get_stock_details(upper)
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


# ── Consensus screener (registered BEFORE /{symbol} to avoid routing conflict) ─

_SCREENER_UNIVERSE = [
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","ITC","SBIN","BAJFINANCE",
    "HINDUNILVR","MARUTI","WIPRO","ASIANPAINT","LT","SUNPHARMA","TITAN",
    "KOTAKBANK","AXISBANK","NESTLEIND","ULTRACEMCO","TATAMOTORS","TATASTEEL",
    "ONGC","POWERGRID","NTPC","COALINDIA","JSWSTEEL","TECHM","HCLTECH",
    "ADANIENT","DRREDDY",
]
_SCREENER_THRESHOLD = 14          # out of 16 personas — 87.5%
_SCREENER_TTL_S     = 4 * 3600   # cache for 4 hours

_screener_cache: dict = {}        # {"result": {...}, "ts": float}


async def _run_one(symbol: str) -> dict | None:
    """Load stock + run fast council for one symbol; returns None on failure."""
    try:
        detail, err = await _load_stock(symbol)
        if err is not None or detail is None:
            return None
        result = agents_service.run_council(detail)
        council = result.get("council", {})
        return {
            "symbol":         result.get("symbol", symbol),
            "name":           result.get("name"),
            "sector":         result.get("sector"),
            "lastPrice":      result.get("lastPrice"),
            "buyCount":       council.get("buyCount", 0),
            "avoidCount":     council.get("avoidCount", 0),
            "holdCount":      council.get("holdCount", 0),
            "total":          sum([council.get("buyCount", 0),
                                   council.get("avoidCount", 0),
                                   council.get("holdCount", 0)]),
            "avgScore":       round(council.get("avgScore", 0), 4),
            "councilVerdict": council.get("verdict", "HOLD"),
        }
    except Exception as exc:
        logger.warning("screener: failed for %s: %s", symbol, exc)
        return None


@router.get("/screener/consensus")
async def get_consensus_screener():
    """Screen the Nifty 50 universe for near-unanimous council consensus.

    Returns stocks where ≥ 87.5% (14/16) of personas agree on BUY or AVOID.
    Results are cached for 4 hours — first call may take 5-15 s while yfinance
    fetches fundamentals; subsequent calls return instantly.
    """
    cached = _screener_cache.get("result")
    if cached and (time.time() - _screener_cache.get("ts", 0)) < _SCREENER_TTL_S:
        return cached

    tasks = [_run_one(sym) for sym in _SCREENER_UNIVERSE]
    all_results = await asyncio.gather(*tasks)
    screened = [r for r in all_results if r is not None]

    buy_picks   = sorted(
        [r for r in screened if r["buyCount"]   >= _SCREENER_THRESHOLD],
        key=lambda r: r["avgScore"], reverse=True,
    )
    avoid_picks = sorted(
        [r for r in screened if r["avoidCount"] >= _SCREENER_THRESHOLD],
        key=lambda r: r["avgScore"],
    )

    result = {
        "buyPicks":       buy_picks,
        "avoidPicks":     avoid_picks,
        "thresholdPct":   round(_SCREENER_THRESHOLD / 16 * 100, 1),
        "thresholdCount": _SCREENER_THRESHOLD,
        "totalScreened":  len(screened),
        "cachedAt":       __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }
    _screener_cache["result"] = result
    _screener_cache["ts"]     = time.time()
    return result


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
