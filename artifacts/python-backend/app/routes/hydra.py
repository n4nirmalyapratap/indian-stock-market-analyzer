"""
Hydra-Alpha Engine — API Routes

Fix applied (code review):
  FIX-4: All request bodies now use Pydantic models with field validators.
         Bad inputs return clean 422 responses instead of 500 crashes.
         Service-level {"error": ...} dicts are mapped to 4xx HTTP responses
         so the frontend can reliably detect failures.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from ..services.hydra_service import HydraEngine
from ..services import hydra_db_service as db
from ..services import hydra_sentiment_service as sentiment
from ..services import hydra_pairs_service as pairs
from ..services import hydra_backtest_service as backtest
from ..services import hydra_var_service as var_svc
from ..services import hydra_forecast_service as forecast_svc

logger = logging.getLogger(__name__)
router  = APIRouter(prefix="/hydra", tags=["hydra"])
_engine = HydraEngine()


# ── Pydantic request models ────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)

    @field_validator("query")
    @classmethod
    def strip_query(cls, v: str) -> str:
        return v.strip()


class ForecastRequest(BaseModel):
    symbol:  str = Field(default="RELIANCE", min_length=1, max_length=15)
    horizon: int = Field(default=5, ge=1, le=30)
    sector:  str = Field(default="Unknown")

    @field_validator("symbol")
    @classmethod
    def upper_symbol(cls, v: str) -> str:
        return v.upper().strip()


class PairAnalyzeRequest(BaseModel):
    symbolA: str = Field(..., min_length=1, max_length=15, alias="symbolA")
    symbolB: str = Field(..., min_length=1, max_length=15, alias="symbolB")

    model_config = {"populate_by_name": True}

    @field_validator("symbolA", "symbolB")
    @classmethod
    def upper_sym(cls, v: str) -> str:
        return v.upper().strip()


class PairScanRequest(BaseModel):
    symbols:    list[str] = Field(default=[])
    pThreshold: float     = Field(default=0.05, ge=0.001, le=0.1)

    @field_validator("symbols")
    @classmethod
    def upper_syms(cls, v: list[str]) -> list[str]:
        return [s.upper().strip() for s in v if s.strip()]


class BacktestRequest(BaseModel):
    symbolA:        str   = Field(default="RELIANCE", min_length=1, max_length=15)
    symbolB:        str   = Field(default="ONGC",     min_length=1, max_length=15)
    initialCapital: float = Field(default=1_000_000,  ge=10_000, le=1_000_000_000)
    entryZ:         float = Field(default=2.0,         ge=0.5, le=5.0)
    exitZ:          float = Field(default=0.5,          ge=0.1, le=2.0)
    commission:     float = Field(default=20.0,         ge=0, le=1000)
    slippageBps:    float = Field(default=5.0,           ge=0, le=100)

    @field_validator("symbolA", "symbolB")
    @classmethod
    def upper_sym(cls, v: str) -> str:
        return v.upper().strip()


class VaRRequest(BaseModel):
    symbols:        list[str] = Field(default=["RELIANCE", "TCS", "HDFCBANK"])
    weights:        Optional[list[float]] = Field(default=None)
    confidence:     float = Field(default=0.95, ge=0.80, le=0.999)
    horizon:        int   = Field(default=1,    ge=1,    le=30)
    portfolioValue: float = Field(default=1_000_000, ge=1_000, le=1_000_000_000)

    @field_validator("symbols")
    @classmethod
    def upper_syms(cls, v: list[str]) -> list[str]:
        cleaned = [s.upper().strip() for s in v if s.strip()]
        if len(cleaned) < 1:
            raise ValueError("At least one symbol required")
        if len(cleaned) > 30:
            raise ValueError("Maximum 30 symbols")
        return cleaned


class TextScoreRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1)


class DataUpdateRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1)

    @field_validator("symbols")
    @classmethod
    def upper_syms(cls, v: list[str]) -> list[str]:
        return [s.upper().strip() for s in v if s.strip()]


# ── Helper: turn service-level errors into HTTP errors ─────────────────────────

def _check_error(result: dict, status: int = 422) -> None:
    """Raise HTTPException if the service returned an error dict."""
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=status, detail=result["error"])


# ── Status / capabilities ──────────────────────────────────────────────────────

@router.get("/status")
async def hydra_status():
    return {
        "engine": "Hydra-Alpha Engine v1.1",
        "status": "online",
        "agents": _engine.capabilities(),
        "database": db.db_stats(),
        "modules": [
            "Data Layer (SQLite WAL + incremental Yahoo Finance updates)",
            "NLP Sentiment (VADER + Financial Lexicon augmentation)",
            "Pairs Trading (Engle-Granger cointegration + OU Process calibration)",
            "Event-Driven Backtesting (MarketEvent → Signal → Order → Fill)",
            "Value at Risk (Historical Simulation, fat-tail aware)",
            "Probabilistic Forecasting (TFT-inspired statistical ensemble)",
            "Supervisor Agent (NL intent routing to expert agents)",
        ],
        "fixes": ["FIX-1: Short PnL", "FIX-2: Sync event loop", "FIX-3: VaR weight normalisation",
                  "FIX-4: Pydantic validation", "FIX-5: SQLite WAL", "FIX-6: OU degenerate guard"],
    }

# ── Supervisor (NL query) ──────────────────────────────────────────────────────

@router.post("/query")
async def supervisor_query(body: QueryRequest):
    result = await _engine.query(body.query)
    _check_error(result, status=422)
    return result

# ── Forecast ──────────────────────────────────────────────────────────────────

@router.post("/forecast")
async def run_forecast(body: ForecastRequest):
    await db.update_ticker(body.symbol)
    rows = db.get_history(body.symbol, days=365)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No price data for {body.symbol}")
    closes = [r["close"] for r in rows if r.get("close")]
    sent   = sentiment.price_action_sentiment(closes)
    result = forecast_svc.forecast(
        body.symbol, rows, horizon_days=body.horizon,
        sector=body.sector, sentiment_score=sent["compound"],
    )
    _check_error(result)
    result["sentiment"] = sent
    return result

# ── Pairs Trading ─────────────────────────────────────────────────────────────

@router.post("/pairs/analyze")
async def analyze_pair(body: PairAnalyzeRequest):
    await asyncio.gather(db.update_ticker(body.symbolA), db.update_ticker(body.symbolB))
    rows_a   = db.get_history(body.symbolA, days=365)
    rows_b   = db.get_history(body.symbolB, days=365)
    closes_a = [r["close"] for r in rows_a if r.get("close")]
    closes_b = [r["close"] for r in rows_b if r.get("close")]
    result   = pairs.analyze_pair(body.symbolA, body.symbolB, closes_a, closes_b)
    _check_error(result)
    return result


@router.post("/pairs/scan")
async def scan_pairs(body: PairScanRequest):
    symbols = body.symbols or [
        "RELIANCE", "ONGC", "BPCL", "HDFCBANK", "ICICIBANK",
        "KOTAKBANK", "AXISBANK", "TCS", "INFY", "WIPRO",
        "HCLTECH", "SUNPHARMA", "CIPLA", "TATASTEEL", "HINDALCO",
    ]
    await asyncio.gather(*[db.update_ticker(s) for s in symbols], return_exceptions=True)

    histories: dict[str, list[float]] = {}
    for s in symbols:
        closes = [r["close"] for r in db.get_history(s, days=365) if r.get("close")]
        if len(closes) >= 30:
            histories[s] = closes

    found = pairs.scan_pairs(list(histories.keys()), histories, p_threshold=body.pThreshold)
    return {"symbols": list(histories.keys()), "pairs": found, "totalFound": len(found)}

# ── Backtesting ───────────────────────────────────────────────────────────────

@router.post("/backtest")
async def run_backtest(body: BacktestRequest):
    await asyncio.gather(db.update_ticker(body.symbolA), db.update_ticker(body.symbolB))
    rows_a   = db.get_history(body.symbolA, days=730)
    rows_b   = db.get_history(body.symbolB, days=730)
    closes_a = [r["close"] for r in rows_a if r.get("close")]
    closes_b = [r["close"] for r in rows_b if r.get("close")]

    pair_result = pairs.analyze_pair(body.symbolA, body.symbolB, closes_a, closes_b)
    _check_error(pair_result)

    ou = pair_result.get("ou", {})
    bt = backtest.run_pairs_backtest(
        body.symbolA, body.symbolB, rows_a, rows_b,
        hedge_ratio=pair_result.get("hedgeRatio", 1.0),
        mu=ou.get("mu", 0.0),
        sigma_eq=ou.get("sigmaEq", 1.0),
        initial_capital=body.initialCapital,
        commission=body.commission,
        slippage_bps=body.slippageBps,
        entry_z=body.entryZ,
        exit_z=body.exitZ,
    )
    _check_error(bt)
    bt["pairAnalysis"] = {k: v for k, v in pair_result.items() if k != "spreadSeries"}
    return bt

# ── Value at Risk ─────────────────────────────────────────────────────────────

@router.post("/var")
async def calculate_var(body: VaRRequest):
    await asyncio.gather(*[db.update_ticker(s) for s in body.symbols], return_exceptions=True)

    closes_map: dict[str, list[float]] = {}
    for s in body.symbols:
        closes = [r["close"] for r in db.get_history(s, days=365) if r.get("close")]
        if closes:
            closes_map[s] = closes

    if not closes_map:
        raise HTTPException(status_code=404, detail="No price data available for any symbol")

    # Build weight vector aligned to requested symbols
    if body.weights and len(body.weights) == len(body.symbols):
        w = [float(x) for x in body.weights]
    else:
        w = [1.0] * len(body.symbols)   # service will normalise after filtering

    result = var_svc.portfolio_var(body.symbols, closes_map, w, body.confidence, body.horizon, body.portfolioValue)
    _check_error(result)
    return result

# ── Sentiment ─────────────────────────────────────────────────────────────────

@router.get("/sentiment")
async def get_sentiment(symbol: str = Query("RELIANCE", min_length=1, max_length=15)):
    symbol = symbol.upper().strip()
    await db.update_ticker(symbol)
    closes = [r["close"] for r in db.get_history(symbol, days=180) if r.get("close")]
    if not closes:
        raise HTTPException(status_code=404, detail=f"No price data for {symbol}")
    result = sentiment.price_action_sentiment(closes)
    result["symbol"] = symbol
    return result


@router.post("/sentiment/score")
async def score_text_batch(body: TextScoreRequest):
    texts = [t for t in body.texts if t.strip()]
    if not texts:
        raise HTTPException(status_code=400, detail="No non-empty texts provided")
    return sentiment.score_batch(texts)

# ── Data management ───────────────────────────────────────────────────────────

@router.post("/data/update")
async def update_data(body: DataUpdateRequest):
    results = await db.bulk_update(body.symbols)
    return {"results": results, "updated": sum(1 for r in results if "error" not in r)}


@router.get("/data/history")
async def get_data_history(
    symbol: str = Query("RELIANCE", min_length=1, max_length=15),
    days:   int = Query(180, ge=1, le=1825),
):
    symbol = symbol.upper().strip()
    await db.update_ticker(symbol)
    rows = db.get_history(symbol, days=days)
    return {"symbol": symbol, "days": days, "rows": rows, "count": len(rows)}


@router.get("/data/stats")
async def data_stats():
    return db.db_stats()
