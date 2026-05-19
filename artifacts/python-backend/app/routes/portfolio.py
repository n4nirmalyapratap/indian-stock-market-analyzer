"""
Portfolio routes — `/api/portfolio/*`

  GET    /api/portfolio                                 — list user's portfolios
  POST   /api/portfolio                                 — create a portfolio
  GET    /api/portfolio/{pid}                           — portfolio meta
  PUT    /api/portfolio/{pid}                           — rename / update cash
  DELETE /api/portfolio/{pid}                           — delete a portfolio

  GET    /api/portfolio/{pid}/valuation                 — live MV, P&L, allocation
  GET    /api/portfolio/{pid}/transactions              — list transactions
  POST   /api/portfolio/{pid}/transactions              — add a transaction
  DELETE /api/portfolio/{pid}/transactions/{tx_id}      — delete a transaction
  POST   /api/portfolio/{pid}/import                    — import Zerodha/Upstox CSV

  GET    /api/portfolio/{pid}/risk                      — VaR / CVaR / Sharpe / Sortino / max-DD
  GET    /api/portfolio/{pid}/performance               — equity curve vs benchmark
  POST   /api/portfolio/{pid}/optimize                  — Markowitz / CVaR + rebalance trades
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Request, Body, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..services import portfolio_service as ps
from ..services import portfolio_optimizer_service as opt
from ..services import hydra_var_service as hv
from ..services.nse_service import NseService
from ..services.yahoo_service import YahooService
from ..services.price_service import PriceService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portfolio", tags=["portfolio"])

_nse   = NseService()
_yahoo = YahooService()
_price = PriceService(_nse, _yahoo)


def _user_id(request: Request) -> str:
    """Return the authenticated user_id from middleware, or raise 401.

    Falling back to a literal "anonymous" string would put every unauthed
    caller into the same shared portfolio bucket — a cross-tenant data leak
    if any /api/portfolio/* path ever escapes the auth middleware.
    """
    from fastapi import HTTPException
    uid = getattr(request.state, "user_id", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return uid


# ── Pydantic input schemas ───────────────────────────────────────────────────

class CreatePortfolioReq(BaseModel):
    name:         str
    cash:         float = 0.0
    baseCurrency: str   = "INR"


class UpdatePortfolioReq(BaseModel):
    name: Optional[str]   = None
    cash: Optional[float] = None


class TxReq(BaseModel):
    symbol:   str
    side:     str
    qty:      float
    price:    float
    fees:     float = 0.0
    tradedAt: Optional[str] = None
    note:     Optional[str] = None


class ImportReq(BaseModel):
    # Cap the in-body CSV at ~10 MB so a giant string can't OOM the worker.
    # A human tradebook is well under 1 MB.
    csv: str = Field(..., max_length=10 * 1024 * 1024)


class OptimizeReq(BaseModel):
    method:        str   = "markowitz"  # 'markowitz' | 'cvar' | 'min_vol'
    confidence:    float = 0.95
    riskFreeRate:  float = 0.07
    # Cap to 200 extra symbols — enough for a watchlist, prevents O(n²)
    # covariance from stalling the worker on attacker-controlled lists.
    universe:      Optional[list[str]] = Field(default=None, max_length=200)
    points:        int   = 25
    targetWeights: Optional[dict[str, float]] = None  # if user already chose


class RiskReq(BaseModel):
    confidence:    float = 0.95
    horizonDays:   int   = 1
    riskFreeRate:  float = 0.07
    lookbackDays:  int   = 365


# ── Portfolio CRUD ───────────────────────────────────────────────────────────

@router.get("")
async def list_portfolios(request: Request):
    return {"portfolios": ps.list_portfolios(_user_id(request))}


@router.post("")
async def create_portfolio(req: CreatePortfolioReq, request: Request):
    p = ps.create_portfolio(_user_id(request), req.name, req.cash, req.baseCurrency)
    return p


@router.get("/{pid}")
async def get_portfolio(pid: str, request: Request):
    p = ps.get_portfolio(_user_id(request), pid)
    if not p:
        return JSONResponse(status_code=404, content={"error": "portfolio not found"})
    return p


@router.put("/{pid}")
async def update_portfolio(pid: str, req: UpdatePortfolioReq, request: Request):
    p = ps.update_portfolio(_user_id(request), pid, name=req.name, cash=req.cash)
    if not p:
        return JSONResponse(status_code=404, content={"error": "portfolio not found"})
    return p


@router.delete("/{pid}")
async def delete_portfolio(pid: str, request: Request):
    if not ps.delete_portfolio(_user_id(request), pid):
        return JSONResponse(status_code=404, content={"error": "portfolio not found"})
    return {"success": True, "id": pid}


# ── Transactions ─────────────────────────────────────────────────────────────

@router.get("/{pid}/transactions")
async def list_transactions(pid: str, request: Request, symbol: Optional[str] = None):
    if not ps.get_portfolio(_user_id(request), pid):
        return JSONResponse(status_code=404, content={"error": "portfolio not found"})
    return {"transactions": ps.list_transactions(_user_id(request), pid, symbol)}


@router.post("/{pid}/transactions")
async def add_transaction(pid: str, req: TxReq, request: Request):
    try:
        tx = ps.add_transaction(
            _user_id(request), pid,
            symbol=req.symbol, side=req.side, qty=req.qty, price=req.price,
            fees=req.fees, traded_at=req.tradedAt, note=req.note,
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    if tx is None:
        return JSONResponse(status_code=404, content={"error": "portfolio not found"})
    return tx


@router.delete("/{pid}/transactions/{tx_id}")
async def delete_transaction(pid: str, tx_id: str, request: Request):
    if not ps.delete_transaction(_user_id(request), pid, tx_id):
        return JSONResponse(status_code=404, content={"error": "transaction not found"})
    return {"success": True, "id": tx_id}


@router.post("/{pid}/import")
async def import_csv(pid: str, req: ImportReq, request: Request):
    res = ps.import_transactions(_user_id(request), pid, req.csv)
    if res.get("error"):
        return JSONResponse(status_code=404, content=res)
    return res


@router.post("/{pid}/import-file")
async def import_file(pid: str, request: Request, file: UploadFile = File(...)):
    """Upload a tradebook as a file — accepts .csv or .xlsx.
    Excel workbooks are flattened to CSV (first sheet only) before parsing
    so the same column conventions apply (Zerodha / Upstox / generic
    symbol,side,qty,price,date)."""
    # Cap the upload at 10 MB to prevent memory-exhaustion DoS. A real
    # tradebook for a human is well under 1 MB even after years of trading.
    _MAX_UPLOAD_BYTES = 10 * 1024 * 1024
    raw = await file.read(_MAX_UPLOAD_BYTES + 1)
    if not raw:
        return JSONResponse(status_code=400, content={"error": "Empty file"})
    if len(raw) > _MAX_UPLOAD_BYTES:
        return JSONResponse(
            status_code=413,
            content={"error": f"File too large (>{_MAX_UPLOAD_BYTES // (1024 * 1024)} MB)."},
        )
    name = (file.filename or "").lower()
    try:
        if name.endswith(".xlsx") or name.endswith(".xlsm"):
            csv_text = ps.xlsx_bytes_to_csv(raw)
        elif name.endswith(".csv") or name.endswith(".txt") or not name:
            csv_text = raw.decode("utf-8", errors="replace")
        else:
            return JSONResponse(status_code=400,
                content={"error": f"Unsupported file type: {file.filename!r}. "
                                  "Upload a .csv or .xlsx tradebook."})
    except Exception as exc:
        return JSONResponse(status_code=400,
            content={"error": f"Could not read file: {exc}"})
    res = ps.import_transactions(_user_id(request), pid, csv_text)
    if res.get("error"):
        return JSONResponse(status_code=404, content=res)
    res["source_filename"] = file.filename
    return res


# ── Live valuation ───────────────────────────────────────────────────────────

@router.get("/{pid}/valuation")
async def get_valuation(pid: str, request: Request):
    val = await ps.value_portfolio(_user_id(request), pid, _price)
    if val is None:
        return JSONResponse(status_code=404, content={"error": "portfolio not found"})
    return val


# ── Risk metrics (VaR / CVaR / Sharpe / Sortino / max-DD) ────────────────────

@router.get("/{pid}/risk")
async def compute_risk_get(
    pid: str,
    request: Request,
    confidence: float = 0.95,
    horizonDays: int = 1,
    riskFreeRate: float = 0.07,
    lookbackDays: int = 365,
):
    """GET alias for /risk so consumers expecting REST-style GET semantics
    (per the original Phase-2 spec) can use query parameters instead of a
    POST body. Both endpoints return identical payloads."""
    return await compute_risk(pid, RiskReq(
        confidence=confidence, horizonDays=horizonDays,
        riskFreeRate=riskFreeRate, lookbackDays=lookbackDays,
    ), request)


@router.post("/{pid}/risk")
async def compute_risk(pid: str, req: RiskReq, request: Request):
    user_id = _user_id(request)
    val = await ps.value_portfolio(user_id, pid, _price)
    if val is None:
        return JSONResponse(status_code=404, content={"error": "portfolio not found"})
    holdings = val["holdings"]
    if not holdings:
        return {"error": "no open holdings"}

    # Pull daily history for every symbol
    import asyncio  # noqa: PLC0415
    syms = [h["symbol"] for h in holdings]
    weights = [h["weight"] for h in holdings]

    async def _hist(sym: str) -> tuple[str, list[float]]:
        try:
            data = await _price.get_historical_data(sym, req.lookbackDays)
            return sym, [float(d["close"]) for d in (data or []) if d.get("close")]
        except Exception as exc:
            logger.warning("portfolio.risk: %s history failed: %s", sym, exc)
            return sym, []

    results = dict(await asyncio.gather(*[_hist(s) for s in syms]))

    portfolio_value = float(val["totals"]["marketValue"]) or 1.0
    var = hv.portfolio_var(
        symbols=syms,
        closes_map=results,
        weights=weights,
        confidence=req.confidence,
        horizon_days=req.horizonDays,
        portfolio_value=portfolio_value,
    )

    # Per-position Sharpe / Sortino / max-DD
    per_position = []
    for h in holdings:
        closes = results.get(h["symbol"], [])
        sortino = hv.sortino_ratio(closes, risk_free_rate_annual=req.riskFreeRate)
        sharpe  = hv.sharpe_ratio(closes,  risk_free_rate_annual=req.riskFreeRate)
        dd      = hv.max_drawdown(closes)
        per_position.append({
            "symbol":   h["symbol"],
            "weight":   h["weight"],
            "sharpe":   sharpe.get("sharpe"),
            "sortino":  sortino.get("sortino"),
            "annualReturn":     sharpe.get("annualReturn"),
            "annualVolatility": sharpe.get("annualVolatility"),
            "maxDrawdownPct":   dd.get("maxDrawdownPct"),
        })

    # Portfolio-level Sortino + Sharpe + max-DD via the equity curve
    perf = await ps.equity_curve(user_id, pid, _price, days=req.lookbackDays)
    equity_closes = [pt["equity"] for pt in (perf or {}).get("series", []) if pt.get("equity", 0) > 0] if perf else []
    pf_sharpe  = hv.sharpe_ratio(equity_closes,  risk_free_rate_annual=req.riskFreeRate) if equity_closes else {}
    pf_sortino = hv.sortino_ratio(equity_closes, risk_free_rate_annual=req.riskFreeRate) if equity_closes else {}
    pf_dd      = hv.max_drawdown(equity_closes) if equity_closes else {}

    return {
        "portfolioId":   pid,
        "totals":        val["totals"],
        "var":           var,
        "perPosition":   per_position,
        "portfolio": {
            "sharpe":         pf_sharpe.get("sharpe"),
            "sortino":        pf_sortino.get("sortino"),
            "annualReturn":   pf_sharpe.get("annualReturn"),
            "annualVolatility": pf_sharpe.get("annualVolatility"),
            "maxDrawdownPct": pf_dd.get("maxDrawdownPct"),
        },
        "fetchedAt":     val["fetchedAt"],
    }


# ── Performance vs benchmark ─────────────────────────────────────────────────

@router.get("/{pid}/performance")
async def performance(pid: str, request: Request, benchmark: str = "NIFTY 50",
                      days: int = 365):
    perf = await ps.equity_curve(_user_id(request), pid, _price,
                                 days=days, benchmark=benchmark)
    if perf is None:
        return JSONResponse(status_code=404, content={"error": "portfolio not found"})
    return perf


# ── Optimizer (Markowitz frontier + CVaR + rebalance trades) ─────────────────

@router.post("/{pid}/optimize")
async def optimize(pid: str, req: OptimizeReq, request: Request):
    user_id = _user_id(request)
    val = await ps.value_portfolio(user_id, pid, _price)
    if val is None:
        return JSONResponse(status_code=404, content={"error": "portfolio not found"})

    held_syms = [h["symbol"] for h in val["holdings"]]
    extra_syms = [s.upper().strip() for s in (req.universe or []) if s and s.strip()]
    universe   = sorted(set(held_syms + extra_syms))
    if len(universe) < 2:
        return JSONResponse(status_code=400, content={
            "error": "Need at least 2 symbols (current holdings + optional universe). "
                     "Add more positions or pass `universe` with extra tickers."})

    import asyncio  # noqa: PLC0415

    async def _hist(sym: str) -> tuple[str, list[float]]:
        try:
            data = await _price.get_historical_data(sym, 400)
            return sym, [float(d["close"]) for d in (data or []) if d.get("close")]
        except Exception as exc:
            logger.warning("portfolio.optimize: %s history failed: %s", sym, exc)
            return sym, []

    closes_map = dict(await asyncio.gather(*[_hist(s) for s in universe]))

    method = (req.method or "markowitz").lower()
    if method == "cvar":
        result = opt.cvar_optimal(universe, closes_map,
                                  confidence=req.confidence,
                                  rf_annual=req.riskFreeRate)
        # Bail out early on optimiser failure (insufficient history, solver
        # divergence, etc.) — otherwise an empty target-weights dict would
        # cause `rebalance_trades` to suggest selling every existing
        # position, which is an unsafe failure mode.
        if not req.targetWeights and (result.get("error") or not result.get("weights")):
            return JSONResponse(status_code=400, content=result)
        target_weights = (
            req.targetWeights
            if req.targetWeights else
            dict(zip(result["symbols"], result["weights"]))
        )
        frontier = None
    else:
        frontier = opt.efficient_frontier(universe, closes_map,
                                          points=req.points,
                                          rf_annual=req.riskFreeRate)
        if frontier.get("error"):
            return JSONResponse(status_code=400, content=frontier)
        # Use max-Sharpe by default; min-vol if method == 'min_vol'.
        chosen = frontier["minVol"] if method == "min_vol" else frontier["maxSharpe"]
        if not chosen:
            return JSONResponse(status_code=500,
                                content={"error": "Optimisation failed to converge"})
        target_weights = (
            req.targetWeights
            if req.targetWeights else
            dict(zip(frontier["symbols"], chosen["weights"]))
        )
        result = chosen

    # Build rebalance trades
    current_qty: dict[str, float] = {h["symbol"]: float(h["qty"]) for h in val["holdings"]}
    prices: dict[str, float] = {h["symbol"]: float(h.get("lastPrice") or 0) for h in val["holdings"]}
    # Add prices for symbols in target set that we don't currently hold
    for sym in target_weights.keys():
        if sym not in prices:
            closes = closes_map.get(sym, [])
            prices[sym] = float(closes[-1]) if closes else 0.0
            current_qty.setdefault(sym, 0.0)

    equity = float(val["totals"]["totalEquity"])
    trades = opt.rebalance_trades(
        target_weights=target_weights,
        current_qty=current_qty,
        prices=prices,
        equity=equity,
    )

    return {
        "portfolioId":   pid,
        "method":        method,
        "result":        result,
        "frontier":      frontier,
        "currentWeights": {h["symbol"]: h["weight"] for h in val["holdings"]},
        "targetWeights": {k: round(float(v), 4) for k, v in target_weights.items()},
        "trades":        trades,
        "equity":        equity,
        "universe":      universe,
        "fetchedAt":     val["fetchedAt"],
    }
