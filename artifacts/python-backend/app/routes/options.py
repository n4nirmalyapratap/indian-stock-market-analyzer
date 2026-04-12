"""
options.py — FastAPI router for the Options Strategy Tester.

Endpoints:
    POST /options/price        — Price a single European option + Greeks
    POST /options/strategy     — Analyse a multi-leg strategy (payoff + Greeks + cost)
    POST /options/backtest     — Run an event-driven historical backtest
    POST /options/scenario     — 2-D scenario analysis matrix (price × vol shocks)
    POST /options/var          — Monte Carlo Value at Risk
    GET  /options/spot/{sym}   — Current spot price + 30-day HV estimate
    GET  /options/chain/{sym}  — Live NSE options chain (current + next expiry)
    POST /options/chat         — AI-powered chatbot (rule-based + Gemma 4 / Qwen / OpenAI fallback)
    POST /options/sebi-audit   — Run SEBI compliance audit (on-demand trigger)
    GET  /options/sebi-report  — Fetch the latest SEBI audit report
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
from ..services.options_backtest_service import run_backtest, STRATEGIES, _to_yf_sym, _to_yf_sym_candidates
from ..services.options_chatbot import chat_reply, _AI_FALLBACK_REPLY

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

    upper      = symbol.upper()
    candidates = _to_yf_sym_candidates(upper)

    hist = None
    used_sym = None
    for yf_sym in candidates:
        try:
            t = yf.Ticker(yf_sym)
            h = t.history(period="3mo")
            # Require at least 31 rows: 30 for rolling HV window + 1 for log returns.
            # Some symbols (e.g. ^CNXFIN) return only 1 bar, which would crash the
            # rolling-30 std calculation even though h.empty is False.
            if not h.empty and len(h) >= 31:
                hist = h
                used_sym = yf_sym
                break
            logger.warning(
                f"{yf_sym}: insufficient history ({len(h)} rows), trying next candidate"
            )
        except Exception as e:
            logger.warning(f"{yf_sym}: fetch error ({e}), trying next candidate")

    if hist is None or hist.empty:
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
    action:       str            = Field(..., description="'buy' or 'sell'")
    option_type:  str            = Field(..., description="'call' or 'put'")
    strike:       float          = Field(..., gt=0, description="Strike price (must be > 0)")
    premium:      float          = Field(0.0, description="Price paid/received per unit. 0 = auto-calculate")
    lots:         int            = Field(1, ge=1)
    lot_size:     int            = Field(75, ge=1)
    iv:           float          = Field(0.20, description="IV for this leg (used in Greeks)")
    residual_dte: Optional[int]  = Field(None, description="For time-spreads: days remaining on this leg when the short leg expires. If set, payoff uses BS residual value instead of intrinsic.")

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
    use_weekly: bool  = Field(False, description="Use weekly expiry cycle (historical backtest). SEBI note: only NIFTY and SENSEX have live weekly contracts post-May 2024.")

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

        # Auto-price legs where premium is 0.
        # Time-spread legs (residual_dte set) are priced at T + residual_dte/365
        # so the far leg's entry premium reflects its longer expiry.
        for leg in legs:
            if leg["premium"] == 0.0:
                iv      = leg.get("iv") or req.sigma
                res_dte = leg.get("residual_dte") or 0
                T_leg   = req.T + res_dte / 365.0   # near leg: T_leg==T; far leg: T_leg>T
                leg["premium"] = round(
                    bs_price(req.S, leg["strike"], T_leg, req.r, iv, leg["option_type"]), 2
                )

        # Expand spot range to cover all strikes so no breakeven is clipped
        all_strikes = [leg["strike"] for leg in legs]
        base_min = req.S * (1 - req.spot_range_pct)
        base_max = req.S * (1 + req.spot_range_pct)
        spot_min = min(base_min, min(all_strikes) * 0.95)
        spot_max = max(base_max, max(all_strikes) * 1.05)

        payoff_data = strategy_payoff_curve(legs, spot_min, spot_max,
                                             r=req.r, sigma=req.sigma)
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
        use_weekly = req.use_weekly,
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


# ── POST /options/smart-suggest ──────────────────────────────────────────────

class SmartSuggestReq(BaseModel):
    symbol: str = Field(..., description="NSE symbol, e.g. NIFTY or RELIANCE")


@router.post("/smart-suggest")
async def smart_suggest(req: SmartSuggestReq):
    """
    Read live market data for the symbol and return all 17 strategy suggestions:
      - 12 predefined strategies scored and sorted by fit score
      - 5 AI-invented strategies tailored to the current vol regime
        (different strategies are generated for low/moderate/high/very_high vol)
    Returns { market_state, recommendations (12), ai_suggestions (5) }.
    """
    from ..services.strategy_builder_service import build_smart_suggestions

    spot_data = await asyncio.to_thread(_fetch_spot_and_hv_sync, req.symbol)
    if "error" in spot_data:
        raise HTTPException(status_code=502, detail=spot_data["error"])

    result = build_smart_suggestions(
        spot     = spot_data["spot"],
        atm      = spot_data["atm"],
        hv       = spot_data.get("hv30", 0.0),
        hv_pct   = spot_data.get("hv30_pct", 50.0),
        lot_size = spot_data["lot_size"],
    )
    return result


@router.post("/chat")
async def options_chat(req: ChatReq):
    """
    Options chatbot — instant rule-based answers with AI fallback for unknown questions.
    Rule-based: zero latency, zero cost, covers all common options topics.
    AI fallback (Gemma 4 → Qwen 3 → Llama 3.3 → gpt-4o-mini): activates for
    questions not covered by the rule engine.
    """
    if not req.messages:
        return {"reply": "Hi! Ask me anything about options strategies, Greeks, or your current position."}

    user_msg = next(
        (m.content for m in reversed(req.messages) if m.role == "user"), ""
    )
    ctx = req.context or {}

    try:
        reply = chat_reply(user_msg, ctx)

        # ── AI fallback for unrecognised questions ──────────────────────────
        if reply == _AI_FALLBACK_REPLY:
            from ..services.ai_client import ask_ai_async

            # Build a focused system prompt so the AI stays on-topic
            strategy_ctx = ""
            if ctx.get("legs"):
                legs = ctx["legs"]
                spot = ctx.get("spot", "?")
                strategy_ctx = (
                    f"\n\nUser's current strategy context:\n"
                    f"- Symbol: {ctx.get('symbol', '?')}, Spot: {spot}\n"
                    f"- Legs: {legs}\n"
                    f"- Analysis: {ctx.get('analysis', {})}"
                )

            system = (
                "You are an expert Indian stock-market options assistant. "
                "Answer clearly and concisely in Markdown. "
                "Focus on NSE options, SEBI rules, and practical strategy advice. "
                "Keep responses under 250 words unless the user asks for detail."
                + strategy_ctx
            )

            history = [{"role": m.role, "content": m.content} for m in req.messages[-6:]]

            ai_text = await ask_ai_async(system=system, history=history)
            reply = ai_text or (
                "I couldn't generate a response right now — please try rephrasing "
                "or ask about a specific strategy, Greek, or SEBI rule."
            )

        return {"reply": reply}
    except Exception as exc:
        logger.error("Chat error: %s", exc)
        raise HTTPException(status_code=502, detail=f"AI service error: {exc}")


# ── POST /options/sebi-audit ──────────────────────────────────────────────────

@router.post("/sebi-audit")
async def trigger_sebi_audit():
    """
    Trigger an on-demand SEBI compliance audit.
    Runs entirely in-process (no subprocess) so all dependencies
    (openai, etc.) are available.  Saves a Markdown report to reports/.
    """
    import sys as _sys
    import pathlib as pl

    # Add python-backend/ to sys.path so `scripts.*` imports resolve
    backend_root = str(pl.Path(__file__).parents[2])
    if backend_root not in _sys.path:
        _sys.path.insert(0, backend_root)

    try:
        from scripts.sebi_audit import run_audit_async
        result = await run_audit_async(days=90)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Audit failed: {exc}")

    # Return the freshly written report text as well
    reports_dir = pl.Path(__file__).parents[2] / "reports"
    reports = sorted(reports_dir.glob("sebi_audit_*.md")) if reports_dir.exists() else []
    report_text = reports[-1].read_text() if reports else "(no report generated)"

    return {
        "status":    result.get("status", "ok"),
        "log":       result.get("log", ""),
        "n_issues":  result.get("n_issues", 0),
        "report":    report_text,
    }


# ── GET /options/sebi-report  (latest only) ───────────────────────────────────

@router.get("/sebi-report")
async def get_sebi_report():
    """Return the most recently generated SEBI audit report as Markdown."""
    import pathlib as pl

    reports_dir = pl.Path(__file__).parents[2] / "reports"
    reports = sorted(reports_dir.glob("sebi_audit_*.md")) if reports_dir.exists() else []
    if not reports:
        raise HTTPException(status_code=404, detail="No SEBI audit report found. Run /sebi-audit first.")

    latest = reports[-1]
    text = latest.read_text()
    return {
        "filename":  latest.name,
        "generated": latest.stem.replace("sebi_audit_", ""),
        "report":    text,
        "n_issues":  text.count("### ISSUE-"),
    }


# ── GET /options/sebi-reports (all reports — list view) ───────────────────────

@router.get("/sebi-reports")
async def list_sebi_reports(full: bool = False):
    """
    Return metadata for ALL historical SEBI audit reports, newest first.
    If full=true, also include the full report text for each entry.
    """
    import pathlib as pl

    reports_dir = pl.Path(__file__).parents[2] / "reports"
    reports = sorted(
        reports_dir.glob("sebi_audit_*.md"), reverse=True
    ) if reports_dir.exists() else []

    result = []
    for p in reports:
        text = p.read_text()
        entry = {
            "filename":  p.name,
            "generated": p.stem.replace("sebi_audit_", ""),
            "n_issues":  text.count("### ISSUE-"),
            "n_lines":   text.count("\n"),
        }
        if full:
            entry["report"] = text
        result.append(entry)

    return {"reports": result, "total": len(result)}
