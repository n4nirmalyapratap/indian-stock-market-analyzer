"""
options.py — FastAPI router for the Options Strategy Tester.

Endpoints:
    POST /options/price       — Price a single European option + Greeks
    POST /options/strategy    — Analyse a multi-leg strategy (payoff + Greeks + cost)
    POST /options/backtest    — Run an event-driven historical backtest
    POST /options/scenario    — 2-D scenario analysis matrix (price × vol shocks)
    POST /options/var         — Monte Carlo Value at Risk
    GET  /options/spot/{sym}  — Current spot price + 30-day HV estimate
    GET  /options/chain/{sym} — Live NSE options chain (current + next expiry)
    POST /options/chat        — Rule-based options chatbot (zero cost, no external API)
"""

from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

from ..services.options_service import (
    bs_price,
    bs_greeks,
    bs_iv,
    price_option,
    strategy_payoff_curve,
    strategy_greeks_aggregate,
    scenario_analysis,
    monte_carlo_var,
    get_lot_size,
    atm_strike,
    RISK_FREE_RATE,
)
from ..services.options_backtest_service import run_backtest, STRATEGIES, _to_yf_sym
from ..services.options_chatbot import chat_reply

router = APIRouter(prefix="/options", tags=["options"])
logger = logging.getLogger("options_route")


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _fetch_spot_and_hv_sync(symbol: str) -> dict:
    """
    Blocking implementation — fetch current spot + 30-day historical volatility.
    Must be called via asyncio.to_thread(); never directly from an async handler.
    """
    import yfinance as yf
    import numpy as np
    import math
    import pandas as pd

    upper  = symbol.upper()
    yf_sym = _to_yf_sym(upper)

    ticker = yf.Ticker(yf_sym)
    hist   = ticker.history(period="3mo")
    if hist.empty:
        raise ValueError(f"No data returned for {symbol}")

    hist.index = pd.to_datetime(hist.index).normalize()
    closes = hist["Close"].dropna()
    spot   = float(closes.iloc[-1])

    log_rets = np.log(closes / closes.shift(1)).dropna()
    hv30     = float(log_rets.rolling(30).std().iloc[-1]) * math.sqrt(252)
    hv30     = max(0.05, min(hv30, 3.0))

    lot = get_lot_size(upper)
    atm = atm_strike(spot)

    return {
        "symbol":   upper,
        "spot":     round(spot, 2),
        "hv30":     round(hv30, 4),
        "hv30_pct": round(hv30 * 100, 2),
        "lot_size": lot,
        "atm":      atm,
        "source":   "yahoo",
    }


async def _fetch_spot_and_hv(symbol: str) -> dict:
    """
    Async wrapper: runs blocking yfinance + pandas in a thread pool so the
    event loop is never blocked.
    """
    try:
        return await asyncio.to_thread(_fetch_spot_and_hv_sync, symbol)
    except Exception as exc:
        logger.warning("Spot fetch failed for %s: %s", symbol, exc)
        raise HTTPException(status_code=502,
                            detail=f"Could not fetch spot for {symbol}: {exc}")


def _auto_price_legs(legs: list[dict], S: float, T: float, r: float,
                     fallback_sigma: float) -> None:
    """
    In-place: price any leg whose premium == 0 using Black-Scholes.
    Required before scenario analysis or VaR so P&L numbers are correct.
    """
    for leg in legs:
        if leg.get("premium", 0.0) == 0.0:
            iv = leg.get("iv") or fallback_sigma
            leg["premium"] = round(
                bs_price(S, leg["strike"], T, r, iv, leg["option_type"]), 2
            )


# ── GET /options/spot/{symbol} ────────────────────────────────────────────────

@router.get("/spot/{symbol}")
async def get_spot(symbol: str):
    """Return current spot price and 30-day historical volatility estimate."""
    return await _fetch_spot_and_hv(symbol)


# ── GET /options/chain/{symbol} ───────────────────────────────────────────────

@router.get("/chain/{symbol}")
async def get_options_chain(symbol: str):
    """
    Fetch the live NSE options chain for the nearest expiry via yfinance.
    Returns calls and puts with strike, lastPrice, bid, ask, IV, OI, volume.
    """
    import yfinance as yf
    import pandas as pd

    upper  = symbol.upper()
    yf_sym = _to_yf_sym(upper)

    def _fetch_chain() -> dict:
        ticker = yf.Ticker(yf_sym)
        exps   = ticker.options
        if not exps:
            raise ValueError("No options available for this symbol")

        selected = exps[:min(2, len(exps))]
        result: dict = {}

        for exp in selected:
            chain = ticker.option_chain(exp)
            calls = chain.calls[
                ["strike", "lastPrice", "bid", "ask", "impliedVolatility",
                 "openInterest", "volume", "inTheMoney"]
            ].rename(columns={"impliedVolatility": "iv", "openInterest": "oi"}).copy()
            puts  = chain.puts[
                ["strike", "lastPrice", "bid", "ask", "impliedVolatility",
                 "openInterest", "volume", "inTheMoney"]
            ].rename(columns={"impliedVolatility": "iv", "openInterest": "oi"}).copy()

            result[exp] = {
                "calls": calls.fillna(0).to_dict("records"),
                "puts":  puts.fillna(0).to_dict("records"),
            }
        return selected, result

    try:
        selected, chain_data = await asyncio.to_thread(_fetch_chain)
        spot_info = await _fetch_spot_and_hv(symbol)

        return {
            "symbol":   upper,
            "spot":     spot_info["spot"],
            "expiries": list(selected),   # fixed: was "expiiries" (double-i)
            "chain":    chain_data,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ── Pydantic models ───────────────────────────────────────────────────────────

class SingleOptionReq(BaseModel):
    S:           float = Field(..., gt=0, description="Spot price (must be > 0)")
    K:           float = Field(..., gt=0, description="Strike price (must be > 0)")
    T:           float = Field(..., description="Time to expiry in years (e.g. 30/365)")
    sigma:       float = Field(..., description="Implied volatility (e.g. 0.20 for 20%)")
    option_type: str   = Field(..., description="'call' or 'put'")
    r:           float = Field(RISK_FREE_RATE, description="Risk-free rate")

    @validator("option_type")
    def validate_type(cls, v):
        v = v.lower()
        if v not in ("call", "put"):
            raise ValueError("option_type must be 'call' or 'put'")
        return v

    @validator("T")
    def validate_T(cls, v):
        if v < 0:
            raise ValueError("T cannot be negative")
        return v

    @validator("sigma")
    def validate_sigma(cls, v):
        if v < 0:
            raise ValueError("sigma cannot be negative")
        return v


class LegModel(BaseModel):
    action:      str   = Field(..., description="'buy' or 'sell'")
    option_type: str   = Field(..., description="'call' or 'put'")
    strike:      float = Field(..., gt=0, description="Strike price (must be > 0)")
    premium:     float = Field(0.0, description="Price paid/received per unit. 0 = auto-calculate")
    lots:        int   = Field(1, ge=1)
    lot_size:    int   = Field(75, ge=1)
    iv:          float = Field(0.20, description="IV for this leg (used in Greeks)")

    @validator("action")
    def va(cls, v):
        if v.lower() not in ("buy", "sell"):
            raise ValueError("action must be 'buy' or 'sell'")
        return v.lower()

    @validator("option_type")
    def vt(cls, v):
        if v.lower() not in ("call", "put"):
            raise ValueError("option_type must be 'call' or 'put'")
        return v.lower()


class StrategyReq(BaseModel):
    legs:    List[LegModel]
    S:       float = Field(..., gt=0, description="Current spot price")
    T:       float = Field(..., ge=0, description="Time to expiry in years")
    sigma:   float = Field(0.20, ge=0, description="Overall IV (used where leg IV is 0)")
    r:       float = Field(RISK_FREE_RATE)
    spot_range_pct: float = Field(0.20, description="±% spot range for payoff diagram")

    @validator("legs")
    def need_legs(cls, v):
        if not v:
            raise ValueError("At least one leg required")
        return v


class BacktestReq(BaseModel):
    symbol:     str   = Field(..., description="e.g. NIFTY, BANKNIFTY, RELIANCE")
    strategy:   str   = Field(..., description="Strategy template name")
    start_date: str   = Field(..., description="'YYYY-MM-DD'")
    end_date:   str   = Field(..., description="'YYYY-MM-DD'")
    lots:       int   = Field(1, ge=1, le=50)
    lot_size:   Optional[int] = Field(None, description="Auto-detected if None")
    entry_dte:  int   = Field(30, ge=1, le=90, description="Days before expiry to enter")
    roll_dte:   int   = Field(0,  ge=0, le=30, description="Exit N days before expiry (0=hold to expiry)")
    otm_pct:    float = Field(0.05, ge=0.01, le=0.30, description="OTM wing as fraction of spot")
    risk_free:  float = Field(RISK_FREE_RATE)

    @validator("strategy")
    def vs(cls, v):
        if v not in STRATEGIES:
            raise ValueError(f"Unknown strategy. Valid: {STRATEGIES}")
        return v


class ScenarioReq(BaseModel):
    legs:         List[LegModel]
    S:            float = Field(..., gt=0)
    T:            float = Field(..., ge=0)
    sigma:        float = Field(0.20, ge=0, description="Fallback IV for auto-pricing zero-premium legs")
    r:            float = RISK_FREE_RATE
    price_shocks: Optional[List[float]] = None
    vol_shocks:   Optional[List[float]] = None


class VaRReq(BaseModel):
    legs:            List[LegModel]
    S:               float = Field(..., gt=0)
    T:               float = Field(..., ge=0)
    sigma:           float = Field(0.20, ge=0, description="Underlying volatility for GBM simulation")
    r:               float = Field(RISK_FREE_RATE)
    horizon_days:    int   = Field(5,     ge=1,  le=252)
    num_simulations: int   = Field(10000, ge=100, le=50000)
    confidence:      float = Field(0.95,  ge=0.80, le=0.99)


# ── POST /options/price ───────────────────────────────────────────────────────

@router.post("/price")
async def price_single_option(req: SingleOptionReq):
    """Price a single European option and return price + full Greeks."""
    try:
        return price_option(req.S, req.K, req.T, req.r, req.sigma, req.option_type)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── POST /options/strategy ────────────────────────────────────────────────────

@router.post("/strategy")
async def analyse_strategy(req: StrategyReq):
    """
    Full strategy analysis:
    - Auto-price any leg with premium == 0 using Black-Scholes
    - Payoff diagram at expiry
    - Aggregate Greeks
    - Net premium, max profit/loss, breakevens
    """
    try:
        legs = [leg.dict() for leg in req.legs]

        # Auto-price legs where premium is 0
        for leg in legs:
            if leg["premium"] == 0.0:
                iv = leg.get("iv") or req.sigma
                leg["premium"] = round(
                    bs_price(req.S, leg["strike"], req.T, req.r, iv, leg["option_type"]), 2
                )

        # Expand spot range to cover all strikes so no breakeven is clipped
        all_strikes = [leg["strike"] for leg in legs]
        base_min = req.S * (1 - req.spot_range_pct)
        base_max = req.S * (1 + req.spot_range_pct)
        spot_min = min(base_min, min(all_strikes) * 0.95)
        spot_max = max(base_max, max(all_strikes) * 1.05)

        payoff_data = strategy_payoff_curve(legs, spot_min, spot_max)
        greeks      = strategy_greeks_aggregate(legs, req.S, req.T, req.r)

        leg_details = []
        for leg in legs:
            iv  = leg.get("iv") or req.sigma
            lp  = price_option(req.S, leg["strike"], req.T, req.r, iv, leg["option_type"])
            leg_details.append({**leg, **{f"leg_{k}": v for k, v in lp.items()
                                          if k not in leg}})

        return {
            "legs":   leg_details,
            "payoff": payoff_data,
            "greeks": greeks,
            "spot":   req.S,
            "T":      req.T,
            "sigma":  req.sigma,
        }
    except Exception as exc:
        logger.exception("Strategy analysis failed")
        raise HTTPException(status_code=400, detail=str(exc))


# ── POST /options/backtest ────────────────────────────────────────────────────

@router.post("/backtest")
async def backtest_strategy(req: BacktestReq):
    """Run an event-driven historical backtest for a predefined options strategy."""
    lot_size = req.lot_size or get_lot_size(req.symbol)
    result = await run_backtest(
        symbol     = req.symbol,
        strategy   = req.strategy,
        start_date = req.start_date,
        end_date   = req.end_date,
        lots       = req.lots,
        lot_size   = lot_size,
        entry_dte  = req.entry_dte,
        roll_dte   = req.roll_dte,
        otm_pct    = req.otm_pct,
        risk_free  = req.risk_free,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── POST /options/scenario ────────────────────────────────────────────────────

@router.post("/scenario")
async def run_scenario(req: ScenarioReq):
    """
    Scenario analysis: 2-D matrix of estimated P&L under price + vol shocks.
    Legs with premium == 0 are auto-priced using Black-Scholes before analysis.
    """
    try:
        legs = [leg.dict() for leg in req.legs]
        # Auto-price any legs that have no entry premium set
        _auto_price_legs(legs, req.S, req.T, req.r, req.sigma)
        return scenario_analysis(
            legs         = legs,
            S            = req.S,
            T            = req.T,
            r            = req.r,
            price_shocks = req.price_shocks,
            vol_shocks   = req.vol_shocks,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── POST /options/var ─────────────────────────────────────────────────────────

@router.post("/var")
async def calc_var(req: VaRReq):
    """
    Monte Carlo Value at Risk using Geometric Brownian Motion.
    Reprices every leg at simulated spot levels and returns VaR, CVaR,
    P&L distribution histogram, and percentiles.
    Legs with premium == 0 are auto-priced before simulation.
    """
    try:
        legs = [leg.dict() for leg in req.legs]
        # Auto-price any legs that have no entry premium set
        _auto_price_legs(legs, req.S, req.T, req.r, req.sigma)
        return monte_carlo_var(
            legs            = legs,
            S               = req.S,
            T               = req.T,
            sigma           = req.sigma,
            r               = req.r,
            horizon_days    = req.horizon_days,
            num_simulations = req.num_simulations,
            confidence      = req.confidence,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── GET /options/strategies ───────────────────────────────────────────────────

@router.get("/strategies")
async def list_strategies():
    """Return all available strategy template names."""
    return {"strategies": STRATEGIES}


# ── POST /options/chat ────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role:    str = Field(..., description="'user' or 'assistant'")
    content: str

class ChatReq(BaseModel):
    messages: List[ChatMessage] = Field(..., description="Conversation history")
    context:  Optional[Dict[str, Any]] = Field(None, description="Current strategy context")


@router.post("/chat")
async def options_chat(req: ChatReq):
    """
    Options education chatbot — rule-based, zero cost, instant responses.
    Covers strategies, Greeks, lot sizes, expiry, risk management, and more.
    Context-aware: uses the user's current legs, spot, and analysis results.
    """
    if not req.messages:
        return {"reply": "Hi! Ask me anything about options strategies, Greeks, or your current position."}

    # Last user message drives the response
    user_msg = next(
        (m.content for m in reversed(req.messages) if m.role == "user"), ""
    )
    ctx = req.context or {}

    try:
        reply = chat_reply(user_msg, ctx)
        return {"reply": reply}
    except Exception as exc:
        logger.error("Chat error: %s", exc)
        raise HTTPException(status_code=502, detail=f"AI service error: {exc}")
