"""
Hydra-Alpha Engine — API Routes
GET  /api/hydra/status
POST /api/hydra/query            NL supervisor query
POST /api/hydra/forecast         Price forecast
POST /api/hydra/pairs/analyze    Cointegration + OU analysis for a pair
POST /api/hydra/pairs/scan       Scan for cointegrated pairs in a universe
POST /api/hydra/backtest         Event-driven pairs backtest
POST /api/hydra/var              Value at Risk (portfolio)
GET  /api/hydra/sentiment        VADER sentiment for a symbol
POST /api/hydra/data/update      Incrementally update OHLCV DB for a list of tickers
GET  /api/hydra/data/stats       DB stats
"""
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from typing import Any

from ..services.hydra_service import HydraEngine
from ..services import hydra_db_service as db
from ..services import hydra_sentiment_service as sentiment
from ..services import hydra_pairs_service as pairs
from ..services import hydra_backtest_service as backtest
from ..services import hydra_var_service as var_svc
from ..services import hydra_forecast_service as forecast_svc

router  = APIRouter(prefix="/hydra", tags=["hydra"])
_engine = HydraEngine()

# ── Status / capabilities ──────────────────────────────────────────────────────

@router.get("/status")
async def hydra_status():
    db_info = db.db_stats()
    return {
        "engine": "Hydra-Alpha Engine v1.0",
        "status": "online",
        "agents": _engine.capabilities(),
        "database": db_info,
        "modules": [
            "Data Layer (SQLite OHLCV + incremental Yahoo Finance updates)",
            "NLP Sentiment (VADER + Financial Lexicon augmentation)",
            "Pairs Trading (Engle-Granger cointegration + OU Process calibration)",
            "Event-Driven Backtesting (MarketEvent → Signal → Order → Fill)",
            "Value at Risk (Historical Simulation, fat-tail aware)",
            "Probabilistic Forecasting (TFT-inspired statistical ensemble)",
            "Supervisor Agent (NL intent routing to expert agents)",
        ],
    }

# ── Supervisor (NL query) ──────────────────────────────────────────────────────

@router.post("/query")
async def supervisor_query(body: dict[str, Any]):
    query = (body.get("query") or body.get("text") or "").strip()
    if not query:
        return JSONResponse(status_code=400, content={"error": "query field is required"})
    result = await _engine.query(query)
    return result

# ── Forecast ──────────────────────────────────────────────────────────────────

@router.post("/forecast")
async def run_forecast(body: dict[str, Any]):
    symbol  = (body.get("symbol") or "RELIANCE").upper().strip()
    horizon = max(1, min(30, int(body.get("horizon", 5))))
    rows = await db.update_ticker(symbol) and db.get_history(symbol, days=365)
    if not isinstance(rows, list):
        rows = db.get_history(symbol, days=365)
    if not rows:
        # Fetch fresh
        await db.update_ticker(symbol)
        rows = db.get_history(symbol, days=365)
    if not rows:
        return JSONResponse(status_code=404, content={"error": f"No data for {symbol}"})
    closes = [r["close"] for r in rows if r.get("close")]
    sent = sentiment.price_action_sentiment(closes)
    result = forecast_svc.forecast(
        symbol, rows, horizon_days=horizon,
        sector=body.get("sector", "Unknown"),
        sentiment_score=sent["compound"],
    )
    result["sentiment"] = sent
    return result

# ── Pairs Trading ─────────────────────────────────────────────────────────────

@router.post("/pairs/analyze")
async def analyze_pair(body: dict[str, Any]):
    symbol_a = (body.get("symbolA") or body.get("symbol_a") or "").upper().strip()
    symbol_b = (body.get("symbolB") or body.get("symbol_b") or "").upper().strip()
    if not symbol_a or not symbol_b:
        return JSONResponse(status_code=400, content={"error": "symbolA and symbolB are required"})
    await db.update_ticker(symbol_a)
    await db.update_ticker(symbol_b)
    rows_a = db.get_history(symbol_a, days=365)
    rows_b = db.get_history(symbol_b, days=365)
    closes_a = [r["close"] for r in rows_a if r.get("close")]
    closes_b = [r["close"] for r in rows_b if r.get("close")]
    result = pairs.analyze_pair(symbol_a, symbol_b, closes_a, closes_b)
    return result


@router.post("/pairs/scan")
async def scan_pairs(body: dict[str, Any]):
    symbols = [s.upper().strip() for s in (body.get("symbols") or [])]
    if not symbols:
        symbols = ["RELIANCE", "ONGC", "BPCL", "HDFCBANK", "ICICIBANK",
                   "KOTAKBANK", "AXISBANK", "TCS", "INFY", "WIPRO",
                   "HCLTECH", "SUNPHARMA", "CIPLA", "TATASTEEL", "HINDALCO"]
    max_p = float(body.get("pThreshold", 0.05))

    import asyncio
    await asyncio.gather(*[db.update_ticker(s) for s in symbols], return_exceptions=True)

    histories = {}
    for s in symbols:
        rows = db.get_history(s, days=365)
        closes = [r["close"] for r in rows if r.get("close")]
        if len(closes) >= 30:
            histories[s] = closes

    found = pairs.scan_pairs(list(histories.keys()), histories, p_threshold=max_p)
    return {"symbols": list(histories.keys()), "pairs": found, "totalFound": len(found)}

# ── Backtesting ───────────────────────────────────────────────────────────────

@router.post("/backtest")
async def run_backtest(body: dict[str, Any]):
    symbol_a = (body.get("symbolA") or "RELIANCE").upper().strip()
    symbol_b = (body.get("symbolB") or "ONGC").upper().strip()
    initial  = float(body.get("initialCapital", 1_000_000))
    entry_z  = float(body.get("entryZ", 2.0))
    exit_z   = float(body.get("exitZ", 0.5))

    await db.update_ticker(symbol_a)
    await db.update_ticker(symbol_b)
    rows_a = db.get_history(symbol_a, days=730)
    rows_b = db.get_history(symbol_b, days=730)
    closes_a = [r["close"] for r in rows_a if r.get("close")]
    closes_b = [r["close"] for r in rows_b if r.get("close")]

    pair_result = pairs.analyze_pair(symbol_a, symbol_b, closes_a, closes_b)
    ou = pair_result.get("ou", {})
    if "error" in pair_result:
        return JSONResponse(status_code=422, content={"error": pair_result["error"]})

    bt = backtest.run_pairs_backtest(
        symbol_a, symbol_b, rows_a, rows_b,
        hedge_ratio=pair_result.get("hedgeRatio", 1.0),
        mu=ou.get("mu", 0.0),
        sigma_eq=ou.get("sigmaEq", 1.0),
        initial_capital=initial,
        entry_z=entry_z,
        exit_z=exit_z,
    )
    bt["pairAnalysis"] = {k: v for k, v in pair_result.items() if k != "spreadSeries"}
    return bt

# ── Value at Risk ─────────────────────────────────────────────────────────────

@router.post("/var")
async def calculate_var(body: dict[str, Any]):
    symbols  = [s.upper().strip() for s in (body.get("symbols") or ["RELIANCE", "TCS", "HDFCBANK"])]
    weights  = body.get("weights")  # optional; defaults to equal weight
    conf     = float(body.get("confidence", 0.95))
    horizon  = int(body.get("horizon", 1))
    port_val = float(body.get("portfolioValue", 1_000_000))

    import asyncio
    await asyncio.gather(*[db.update_ticker(s) for s in symbols], return_exceptions=True)

    closes_map = {}
    for s in symbols:
        rows = db.get_history(s, days=365)
        closes = [r["close"] for r in rows if r.get("close")]
        if closes:
            closes_map[s] = closes

    valid = list(closes_map.keys())
    if not valid:
        return JSONResponse(status_code=404, content={"error": "No data available"})

    if weights and len(weights) == len(valid):
        w = [float(x) for x in weights]
    else:
        w = [1 / len(valid)] * len(valid)

    return var_svc.portfolio_var(valid, closes_map, w, conf, horizon, port_val)

# ── Sentiment ─────────────────────────────────────────────────────────────────

@router.get("/sentiment")
async def get_sentiment(symbol: str = Query("RELIANCE")):
    symbol = symbol.upper().strip()
    await db.update_ticker(symbol)
    rows = db.get_history(symbol, days=180)
    closes = [r["close"] for r in rows if r.get("close")]
    if not closes:
        return JSONResponse(status_code=404, content={"error": f"No data for {symbol}"})
    result = sentiment.price_action_sentiment(closes)
    result["symbol"] = symbol
    return result


@router.post("/sentiment/score")
async def score_text_batch(body: dict[str, Any]):
    texts = body.get("texts") or []
    if isinstance(texts, str):
        texts = [texts]
    if not texts:
        return JSONResponse(status_code=400, content={"error": "texts field required"})
    return sentiment.score_batch(texts)

# ── Data management ───────────────────────────────────────────────────────────

@router.post("/data/update")
async def update_data(body: dict[str, Any]):
    symbols = [s.upper().strip() for s in (body.get("symbols") or [])]
    if not symbols:
        return JSONResponse(status_code=400, content={"error": "symbols list required"})
    results = await db.bulk_update(symbols)
    return {"results": results, "updated": len([r for r in results if "error" not in r])}


@router.get("/data/history")
async def get_data_history(
    symbol: str = Query("RELIANCE"),
    days: int = Query(180),
):
    symbol = symbol.upper().strip()
    await db.update_ticker(symbol)
    rows = db.get_history(symbol, days=days)
    return {"symbol": symbol, "days": days, "rows": rows, "count": len(rows)}


@router.get("/data/stats")
async def data_stats():
    return db.db_stats()
