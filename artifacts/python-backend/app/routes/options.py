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
from datetime import datetime, timezone, date
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
    simulate_strategy_over_time,
    get_lot_size,
    atm_strike,
    RISK_FREE_RATE,
)
from ..services.options_backtest_service import run_backtest, STRATEGIES, _to_yf_sym, _to_yf_sym_candidates
from ..services.options_chatbot import chat_reply, _AI_FALLBACK_REPLY
from ..services import sebi_registry
from ..services.risk_free_service import get_india_risk_free_rate
from ..services import nse_bhavcopy_service as _bhav
from ..services import registry as svc

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

    # ── MIDCPNIFTY special case ───────────────────────────────────────────────
    # The NIFTY MIDCAP SELECT index (which MIDCPNIFTY F&O tracks) has no
    # Yahoo Finance ticker. The closest working ticker is ^NSEMDCP50 (NIFTY
    # MIDCAP 50), whose HV30 is a reasonable volatility proxy but whose spot
    # level (~17,650) is wrong. Override spot from Dhan's scrip-master disk
    # cache: the median listed strike for the nearest expiry = approximate ATM.
    if upper == "MIDCPNIFTY":
        try:
            import csv as _csv
            from pathlib import Path as _P
            _dhan_csv = (
                _P(__file__).resolve().parent.parent.parent
                / "market_cache" / "dhan_scrip_master.csv"
            )
            if _dhan_csv.exists():
                with open(_dhan_csv, encoding="utf-8", newline="") as _fh:
                    _dhan_rows = list(_csv.DictReader(_fh))
                _mc_strikes = sorted(
                    float(r["SEM_STRIKE_PRICE"])
                    for r in _dhan_rows
                    if r.get("SEM_EXM_EXCH_ID", "").strip() == "NSE"
                    and r.get("SEM_TRADING_SYMBOL", "").startswith("MIDCPNIFTY-")
                    and float(r.get("SEM_STRIKE_PRICE", 0) or 0) > 1000
                )
                if _mc_strikes:
                    _dhan_spot = _mc_strikes[len(_mc_strikes) // 2]
                    logger.info(
                        "MIDCPNIFTY: overriding yfinance spot %.2f → Dhan "
                        "median strike %.2f (NIFTY MIDCAP SELECT has no yf ticker)",
                        spot, _dhan_spot,
                    )
                    spot = _dhan_spot
        except Exception as _exc:
            logger.debug("MIDCPNIFTY Dhan spot override failed: %s", _exc)

    lot = get_lot_size(upper)
    atm = atm_strike(spot)

    return {
        "symbol":   upper,
        "spot":     round(spot, 2),
        "hv30":     round(hv30, 4),
        "hv30_pct": round(hv30 * 100, 2),
        "lot_size": lot,
        "atm":      atm,
        "source":   f"yahoo:{used_sym}",
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

def _normalise_nse_chain(payload: dict) -> tuple[list[str], dict]:
    """
    Convert NSE option chain payload (both new 'data' list format and legacy
    'records' format) into {expiry: {calls:[…], puts:[…]}} + sorted expiry list.
    """
    import datetime

    # Detect format
    if "records" in payload:
        data_list     = payload["records"].get("data", [])
        expiry_dates  = payload["records"].get("expiryDates", [])
        date_fmt      = "%d-%b-%Y"
        underlying    = payload["records"].get("underlyingValue", 0)
    elif "data" in payload:
        data_list = payload["data"]
        unique: set[str] = set()
        for e in data_list:
            ed = e.get("expiryDate") or e.get("expiryDates")
            if ed:
                unique.add(ed)
        sample   = next(iter(unique), "")
        date_fmt = "%d-%m-%Y" if (sample and "-" in sample and sample.split("-")[1].isdigit()) else "%d-%b-%Y"
        try:
            expiry_dates = sorted(list(unique), key=lambda x: datetime.datetime.strptime(x, date_fmt))
        except ValueError:
            expiry_dates = sorted(list(unique))
        underlying = 0
        if data_list:
            underlying = data_list[0].get("underlyingValue", 0) or 0
    else:
        return [], {}, 0

    # Build per-expiry calls/puts
    chain: dict = {}
    for item in data_list:
        exp = item.get("expiryDate") or item.get("expiryDates") or ""
        if not exp:
            continue
        if exp not in chain:
            chain[exp] = {"calls": [], "puts": []}
        strike = item.get("strikePrice", 0)

        def _leg(d: dict) -> dict:
            return {
                "strike":      strike,
                "lastPrice":   d.get("lastPrice", 0) or 0,
                "bid":         d.get("bidprice", d.get("bid", 0)) or 0,
                "ask":         d.get("askPrice", d.get("ask", 0)) or 0,
                "iv":          round((d.get("impliedVolatility", 0) or 0) / 100, 4),
                "oi":          d.get("openInterest", 0) or 0,
                # Day-over-day OI change — needed by the OI-buildup
                # classifier on the F&O analytics tab. NSE returns it
                # under `changeinOpenInterest`; Yahoo doesn't ship it
                # so the Yahoo-fallback path will leave this at 0.
                "oiChange":    d.get("changeinOpenInterest", 0) or 0,
                "volume":      d.get("totalTradedVolume", d.get("volume", 0)) or 0,
                "inTheMoney":  d.get("inTheMoney", False),
                "change":      d.get("change", 0) or 0,
                "pChange":     d.get("pChange", 0) or 0,
            }

        if item.get("CE"):
            chain[exp]["calls"].append(_leg(item["CE"]))
        if item.get("PE"):
            chain[exp]["puts"].append(_leg(item["PE"]))

    # Sort strikes within each expiry
    for exp in chain:
        chain[exp]["calls"].sort(key=lambda x: x["strike"])
        chain[exp]["puts"].sort(key=lambda x: x["strike"])

    return expiry_dates, chain, underlying


def _bs_fill_nse_chain(
    chain_data: dict,
    spot: float,
    hv30: float,
) -> None:
    """Fill zero-LTP / zero-IV entries in an NSE chain dict with Black-Scholes prices.

    Only patches rows where ``lastPrice == 0`` — real traded prices are never
    overwritten.  This makes illiquid chains (e.g. MIDCPNIFTY) display a
    complete chain instead of rows full of "—".

    IV skew applied matches the Dhan+BS tier:
      • Calls: base HV30 + 0.60 × moneyness (puts bid up for OTM calls)
      • Puts:  base HV30 + 0.15 × moneyness (mild put skew)
    """
    from datetime import datetime as _dt, date as _date

    for exp_str, exp_chain in chain_data.items():
        try:
            dte = max(1, (_dt.strptime(exp_str, "%d-%b-%Y").date() - _date.today()).days)
        except (ValueError, TypeError):
            dte = 30
        T = dte / 365.0

        for opt_type, legs in (("call", exp_chain.get("calls", [])),
                                ("put",  exp_chain.get("puts",  []))):
            for leg in legs:
                K = leg.get("strike", 0)
                if not K or spot <= 0:
                    continue
                if (leg.get("lastPrice") or 0) == 0:
                    mono = abs(K - spot) / spot
                    iv   = max(0.05, hv30 + (0.60 if opt_type == "call" else 0.15) * mono)
                    price = bs_price(spot, K, T, RISK_FREE_RATE, iv, opt_type)
                    if price >= 0.005:  # skip values that round to 0.00
                        leg["lastPrice"] = round(price, 2)
                        if not (leg.get("iv") or 0):
                            leg["iv"] = round(iv, 4)


_YF_MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def _yf_to_nse_date(yf_exp: str) -> str:
    """Convert Yahoo YYYY-MM-DD → DD-Mon-YYYY (NSE standard)."""
    import datetime as _dt
    try:
        d = _dt.datetime.strptime(yf_exp, "%Y-%m-%d")
        return f"{d.day:02d}-{_YF_MON[d.month - 1]}-{d.year}"
    except (ValueError, TypeError):
        return yf_exp


def _nse_to_yf_date(nse_exp: str) -> Optional[str]:
    """Convert DD-Mon-YYYY → YYYY-MM-DD for Yahoo API calls."""
    import datetime as _dt
    try:
        d = _dt.datetime.strptime(nse_exp, "%d-%b-%Y")
        return d.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _yahoo_chain_fallback(upper: str, requested_expiry: Optional[str] = None) -> tuple[list, dict]:
    """
    Yahoo Finance fallback — returns (expiries_in_DD-Mon-YYYY, chain_dict).

    Tries all symbol candidates in order (e.g. FINNIFTY → ^CNXFIN then
    NIFTY_FIN_SERVICE.NS).  Expiry dates are always normalised to DD-Mon-YYYY
    so the caller receives a consistent format regardless of source.

    requested_expiry: DD-Mon-YYYY (optional).  When supplied, only that
    expiry's chain is fetched; the full expiry list is still returned.
    """
    import yfinance as yf

    last_err: Exception = ValueError(f"No Yahoo Finance options for {upper}")
    for yf_sym in _to_yf_sym_candidates(upper):
        try:
            ticker = yf.Ticker(yf_sym)
            exps   = ticker.options          # tuple of YYYY-MM-DD strings
            if not exps:
                continue

            # Full list in NSE format (for the dropdown)
            nse_exps = [_yf_to_nse_date(e) for e in exps]

            # Determine which raw Yahoo expiry/expiries to fetch chain data for
            if requested_expiry:
                yf_req = _nse_to_yf_date(requested_expiry)
                fetch_yf = [yf_req] if yf_req and yf_req in exps else [exps[0]]
            else:
                fetch_yf = list(exps[:min(3, len(exps))])

            result: dict = {}
            for yf_exp in fetch_yf:
                try:
                    ch      = ticker.option_chain(yf_exp)
                    nse_key = _yf_to_nse_date(yf_exp)
                    _cols   = ["strike", "lastPrice", "bid", "ask",
                               "impliedVolatility", "openInterest", "volume", "inTheMoney"]
                    calls = ch.calls[_cols].rename(
                        columns={"impliedVolatility": "iv", "openInterest": "oi"}
                    ).copy()
                    puts  = ch.puts[_cols].rename(
                        columns={"impliedVolatility": "iv", "openInterest": "oi"}
                    ).copy()
                    result[nse_key] = {
                        "calls": calls.fillna(0).to_dict("records"),
                        "puts":  puts.fillna(0).to_dict("records"),
                    }
                except Exception as _chain_exc:
                    logger.debug("Yahoo chain for %s exp %s: %s", yf_sym, yf_exp, _chain_exc)

            if result:
                return nse_exps[:8], result

        except Exception as exc:
            last_err = exc
            logger.debug("Yahoo candidate %s failed: %s", yf_sym, exc)

    raise ValueError(str(last_err))


async def _dhan_bs_chain(upper: str, expiry: Optional[str]) -> Optional[dict]:
    """
    Tier-3 option chain fallback: Dhan public scrip-master for expiry/strike
    data + Black-Scholes for theoretical pricing.

    Why this is better than a fully-synthetic chain:
      • Expiry dates come from Dhan's live trading reference — authoritative
        and updated daily; covers BOTH NSE (NIFTY, BANKNIFTY, …) and BSE
        (SENSEX, BANKEX) derivatives.
      • Strike prices are the actual listed strikes, not an arithmetic series
        generated from the ATM step.  This matches what traders see on screen.
      • Spot + HV30 come from yfinance just like the spot endpoint.
      • Pricing via Black-Scholes with a mild Indian-market IV skew.

    Returns the same JSON envelope as NSE/Yahoo sources, with
    `source="Dhan+BS"` and `is_synthetic=True` so the frontend can show
    the appropriate notice.
    Returns None when Dhan data is unavailable (network failure, unknown
    symbol) so the caller can propagate a 503.
    """
    from ..services import dhan_scrip_master_service as _dsm
    from datetime import date as _date, datetime as _dt

    expiry_dates = await _dsm.get_expiry_dates(upper)
    if not expiry_dates:
        return None

    sel_expiry = expiry if (expiry and expiry in expiry_dates) else expiry_dates[0]

    strikes_all = await _dsm.get_strikes(upper, sel_expiry)
    if not strikes_all:
        return None

    try:
        spot_info = await _fetch_spot_and_hv(upper)
    except HTTPException:
        return None

    spot = spot_info.get("spot", 0) or 0
    hv30 = spot_info.get("hv30", 0.20)

    # Safety net: if the yfinance spot has zero overlap with Dhan's listed
    # strikes (e.g. a wrong ticker maps to a completely different index), derive
    # the ATM from Dhan's median strike instead.  This covers MIDCPNIFTY today
    # and any future symbol whose Yahoo ticker mismaps.
    valid_strikes = sorted(k for k in strikes_all if k > 0)
    if spot > 0 and valid_strikes:
        wide_match = [k for k in valid_strikes if abs(k - spot) / spot <= 0.40]
        if len(wide_match) < 5:
            inferred = valid_strikes[len(valid_strikes) // 2]
            logger.warning(
                "%s: yfinance spot %.2f has no overlap with Dhan strikes "
                "(%.0f–%.0f); using median strike %.0f as ATM proxy",
                upper, spot, min(valid_strikes), max(valid_strikes), inferred,
            )
            spot = inferred

    # Filter strikes to ±15 % of spot so the chain stays manageable
    if spot > 0:
        filtered = [k for k in strikes_all if abs(k - spot) / spot <= 0.15]
        strikes  = filtered if filtered else strikes_all
    else:
        strikes = strikes_all

    try:
        exp_date = _dt.strptime(sel_expiry, "%d-%b-%Y").date()
        dte      = max(1, (exp_date - _date.today()).days)
    except (ValueError, TypeError):
        dte = 30
    T_years = dte / 365.0

    calls: list[dict] = []
    puts:  list[dict] = []
    for K in strikes:
        if K <= 0:
            continue
        mono = abs(K - spot) / spot if spot > 0 else 0
        iv_c = max(0.05, hv30 + 0.60 * mono)
        iv_p = max(0.05, hv30 + 0.15 * mono)
        cp   = bs_price(spot, K, T_years, RISK_FREE_RATE, iv_c, "call")
        pp   = bs_price(spot, K, T_years, RISK_FREE_RATE, iv_p, "put")

        def _sp(v: float) -> float:
            return max(0.05, v * 0.004)

        calls.append({
            "strike":     K,
            "lastPrice":  round(cp, 2),
            "bid":        round(cp - _sp(cp), 2),
            "ask":        round(cp + _sp(cp), 2),
            "iv":         round(iv_c, 4),
            "oi":         0,
            "volume":     0,
            "inTheMoney": K < spot,
        })
        puts.append({
            "strike":     K,
            "lastPrice":  round(pp, 2),
            "bid":        round(pp - _sp(pp), 2),
            "ask":        round(pp + _sp(pp), 2),
            "iv":         round(iv_p, 4),
            "oi":         0,
            "volume":     0,
            "inTheMoney": K > spot,
        })

    if not calls:
        return None

    return {
        "symbol":       upper,
        "spot":         spot,
        "expiries":     expiry_dates,
        "chain":        {sel_expiry: {"calls": calls, "puts": puts}},
        "pcr":          None,
        "source":       "Dhan+BS",
        "is_synthetic": True,
    }


@router.get("/chain/{symbol}")
async def get_options_chain(symbol: str, expiry: Optional[str] = None):
    """
    Fetch the live options chain for a symbol.

    Three-tier source waterfall:
      1. NSE native API — works for NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY.
      2. Yahoo Finance  — fallback for NSE-listed symbols with yfinance coverage.
      3. Dhan scrip-master + Black-Scholes — covers SENSEX, BANKEX and any
         symbol where the first two tiers fail.  Returns real expiry dates and
         actual market strikes from Dhan's public contract master, priced
         theoretically via Black-Scholes (marked `is_synthetic: true`).

    Query param `expiry` (DD-Mon-YYYY) selects a specific expiry; omit for
    the nearest available.
    """
    upper = symbol.upper()

    _IDX = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"}
    instrument = "OPTIDX" if any(idx in upper for idx in _IDX) else "OPTSTK"

    try:
        # ── Tier 1: NSE native chain ──────────────────────────────────────────
        nse_payload = await svc.nse.get_option_chain(upper, expiry_date=expiry, instrument=instrument)
        if nse_payload:
            expiry_dates, chain_data, underlying = _normalise_nse_chain(nse_payload)
            if chain_data:
                spot_info = await _fetch_spot_and_hv(symbol)
                spot      = spot_info.get("spot") or underlying or 0
                hv30      = spot_info.get("hv30", 0.20)
                # Fill zero-LTP strikes (illiquid/non-traded) with BS theoretical
                # prices so the chain displays complete rows instead of gaps ("—").
                # Real traded prices are never overwritten.
                _bs_fill_nse_chain(chain_data, spot, hv30)
                pcr       = svc.nse.calculate_pcr(nse_payload, 0)
                return {
                    "symbol":   upper,
                    "spot":     spot,
                    "expiries": expiry_dates[:8],
                    "chain":    chain_data,
                    "pcr":      pcr,
                    "source":   "NSE",
                }

        # ── Tier 2: Yahoo Finance fallback ────────────────────────────────────
        yahoo_exc: Optional[Exception] = None
        try:
            selected, chain_data = await asyncio.to_thread(_yahoo_chain_fallback, upper, expiry)
            spot_info = await _fetch_spot_and_hv(symbol)
            return {
                "symbol":   upper,
                "spot":     spot_info.get("spot", 0),
                "expiries": selected,
                "chain":    chain_data,
                "pcr":      None,
                "source":   "YAHOO",
            }
        except Exception as _ye:
            yahoo_exc = _ye
            logger.debug("Yahoo fallback failed for %s: %s", upper, _ye)

        # ── Tier 3: Dhan scrip-master + Black-Scholes ─────────────────────────
        dhan_result = await _dhan_bs_chain(upper, expiry)
        if dhan_result:
            return dhan_result

        raise HTTPException(
            status_code=503,
            detail=f"Option chain unavailable for {upper} (NSE/Yahoo/Dhan all failed). Yahoo: {yahoo_exc}",
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Options chain fetch failed for %s: %s", upper, exc)
        raise HTTPException(status_code=502, detail=str(exc))


# ── GET /options/expiries/{symbol} ────────────────────────────────────────────

@router.get("/expiries/{symbol}")
async def get_expiry_list(symbol: str):
    """
    Return sorted list of F&O expiry dates for a symbol.
    Primary: NSE NextApi.  Fallback: Dhan public scrip-master.
    Format: ["DD-Mon-YYYY", ...]
    """
    upper = symbol.upper()
    _IDX  = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"}
    instrument = "OPTIDX" if any(idx in upper for idx in _IDX) else "OPTSTK"
    try:
        dates = await svc.nse.get_expiry_list(upper, instrument=instrument)
        if dates:
            return {"symbol": upper, "expiries": dates, "instrument": instrument, "source": "NSE"}
    except Exception:
        pass
    try:
        from ..services import dhan_scrip_master_service as _dsm
        dhan_dates = await _dsm.get_expiry_dates(upper)
        if dhan_dates:
            return {"symbol": upper, "expiries": dhan_dates, "instrument": instrument, "source": "Dhan"}
    except Exception:
        pass
    raise HTTPException(status_code=503, detail=f"Expiry dates unavailable for {upper}")


# ── GET /options/pcr/{symbol} ─────────────────────────────────────────────────

@router.get("/analytics/{symbol}")
async def get_options_analytics(symbol: str, expiry: Optional[str] = None):
    """Run the six-pass F&O analytics suite (max pain, OI buildup,
    IV smile, unusual activity, strategy heatmap) on a single chain
    snapshot.

    Reuses `get_options_chain` for the actual chain fetch so the
    source waterfall (NSE → Yahoo → Dhan-BS) and the BS-fill behavior
    stay consistent with what the existing chain table shows.

    Returns:
        {
          "symbol":   str,
          "spot":     float,
          "expiry":   str,
          "expiries": list[str],
          "source":   "NSE" | "YAHOO" | "DHAN_BS",
          "analytics": {
            "maxPain":   { maxPainStrike, byStrike },
            "oiBuildup": { calls, puts },
            "smile":     [{strike, callIV, putIV, isATM}],
            "unusual":   [...],
            "strategy":  [...],
          }
        }
    """
    upper = symbol.upper()
    # Reuse the same chain fetcher the existing chain endpoint uses.
    # Calling the route function directly bypasses the HTTP layer
    # entirely — no extra round-trip, full source-waterfall behavior.
    chain_resp = await get_options_chain(upper, expiry=expiry)
    spot     = chain_resp.get("spot", 0) or 0
    expiries = chain_resp.get("expiries", [])
    chain    = chain_resp.get("chain", {}) or {}

    # Pick the expiry we'll analyze. The chain endpoint returns a dict
    # keyed by expiry string; we use the first key if no `expiry` was
    # supplied (matches NSE's "nearest" default).
    if expiry and expiry in chain:
        selected_expiry = expiry
    elif chain:
        selected_expiry = next(iter(chain))
    else:
        raise HTTPException(status_code=503,
                            detail="No option chain data to analyze.")
    leg = chain[selected_expiry]
    calls, puts = leg.get("calls", []), leg.get("puts", [])

    from ..services import options_analytics_service as _ana  # noqa: PLC0415
    return {
        "symbol":    upper,
        "spot":      spot,
        "expiry":    selected_expiry,
        "expiries":  expiries,
        "source":    chain_resp.get("source"),
        "analytics": _ana.compute_analytics(calls, puts, spot),
    }


# ── PCR time-series (history) ───────────────────────────────────────────────


@router.get("/pcr-history/{symbol}")
async def get_pcr_history(symbol: str, hours: int = 24, expiry_index: int = 0):
    """Return accumulated PCR snapshots for a symbol over the last N hours.

    The intraday scheduler snapshots PCR every 15 min during market
    hours and persists to `options_pcr_history`. This endpoint pulls
    the rows back for the F&O analytics chart on the frontend.

    Inputs are clamped to safe bounds (not 400'd) so the chart still
    renders if a client passes an oddly large value — but `hours` is
    capped at 30 days so a caller can't unintentionally trigger a
    full-table scan.
    """
    _MAX_HOURS = 24 * 30   # 30 days — plenty for the chart's 72h default
    _MAX_EXPIRY_INDEX = 10
    safe_hours = max(1, min(int(hours or 24), _MAX_HOURS))
    safe_idx   = max(0, min(int(expiry_index or 0), _MAX_EXPIRY_INDEX))

    from ..services import options_pcr_service as _pcr  # noqa: PLC0415
    rows = _pcr.get_history(symbol.upper(), hours=safe_hours, expiry_index=safe_idx)
    return {
        "symbol":       symbol.upper(),
        "expiry_index": safe_idx,
        "hours":        safe_hours,
        "count":        len(rows),
        "series":       rows,
    }


@router.get("/pcr/{symbol}")
async def get_pcr(symbol: str, expiry_index: int = 0):
    """
    Return the Put-Call Ratio for a symbol's nearest (or Nth) expiry.
    """
    upper = symbol.upper()
    _IDX  = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"}
    instrument = "OPTIDX" if any(idx in upper for idx in _IDX) else "OPTSTK"
    try:
        payload = await svc.nse.get_option_chain(upper, instrument=instrument)
        if not payload:
            raise HTTPException(status_code=503, detail="NSE option chain unavailable")
        pcr = svc.nse.calculate_pcr(payload, expiry_index)
        return {"symbol": upper, "expiry_index": expiry_index, "pcr": pcr}
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


# ── GET /options/bhavcopy/coverage ───────────────────────────────────────────

@router.get("/bhavcopy/coverage")
async def bhavcopy_coverage():
    """Return NSE/BSE F&O bhavcopy cache statistics — date range, row count
    per symbol, and last 20 ingest attempts.  Used by the Backtest UI to
    show the user exactly which dates are backed by real settlement data."""
    return await asyncio.to_thread(_bhav.get_coverage)


@router.post("/bhavcopy/refresh")
async def bhavcopy_refresh(days: int = 7):
    """Manually pull the last `days` trading days into the cache.
    Skips dates already marked 'ok'."""
    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="days must be 1..90")
    results = await asyncio.to_thread(_bhav.refresh_recent, days)
    return {"requested_days": days, "results": results}


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


# ── GET /options/compliance (SEBI rule snapshot) ──────────────────────────────

@router.get("/compliance")
async def get_compliance(symbol: Optional[str] = None,
                         on_date: Optional[str] = None,
                         strategy: Optional[str] = None,
                         lots: int = 1,
                         spot: Optional[float] = None):
    """Return the SEBI/exchange rule set effective on `on_date` (defaults to
    today), plus the live India 10-yr risk-free rate from FRED.

    Query params:
        symbol    Canonical symbol (NIFTY, BANKNIFTY, …).
                  If omitted every supported symbol is returned.
        on_date   ISO date (YYYY-MM-DD).  Defaults to today.
        strategy  Optional strategy id (e.g. ``bull_call_spread``,
                  ``short_straddle``, ``iron_condor``); when provided the
                  response gains ``per_leg_costs`` (STT/exchange/stamp/GST
                  per leg per fill) and ``margin_estimate``.
        lots      Number of lots per leg (used only when ``strategy`` is set).
        spot      Optional spot override; otherwise pulled from the cached
                  index quote.  Used for margin notional + ATM strikes.

    The response is the user-facing source of truth for: lot size + circular
    reference, monthly expiry weekday + applicable circular, weekly
    availability per strategy, the realistic cost schedule
    (STT/SEBI/exchange/stamp/GST/brokerage with circulars), the FRED
    risk-free rate with ``asOf`` / ``source`` (no silent fallback), and the
    estimated SEBI SPAN+ELM margin for the chosen strategy.
    """
    from datetime import date as _date

    parsed: Optional[_date] = None
    if on_date:
        try:
            parsed = datetime.strptime(on_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400,
                                detail=f"on_date must be YYYY-MM-DD, got {on_date!r}")

    snap = sebi_registry.compliance_snapshot(symbol=symbol, on_date=parsed)
    rfr  = await get_india_risk_free_rate()
    snap["risk_free_rate"] = rfr

    # ─── Per-strategy enrichment ─────────────────────────────────────────
    if strategy and symbol:
        if lots < 1:
            raise HTTPException(status_code=400,
                                detail=f"lots must be >= 1, got {lots}")
        canon = sebi_registry.canonical_symbol(symbol)
        target_date = parsed or date.today()
        lot_rule = sebi_registry.get_lot_size_on(canon, target_date)
        lot_size = lot_rule.lot_size if lot_rule else 1

        # Resolve spot — prefer caller-supplied override, else cached quote
        spot_px = float(spot) if spot else None
        if spot_px is None:
            try:
                quote = await _fetch_spot_and_hv(canon)
                # `_fetch_spot_and_hv` returns {"spot": <float>, "hv30": ...};
                # accept the legacy "S" key too as a defensive fallback.
                spot_px = quote.get("spot") or quote.get("S")
                spot_px = float(spot_px) if spot_px else None
            except Exception:
                spot_px = None

        # Build a representative leg set from the strategy id
        legs = _build_synthetic_legs(strategy, spot_px or 0.0, canon, lots)

        snap["per_leg_costs"] = sebi_registry.estimate_strategy_costs(
            legs, lot_size=lot_size, on_date=target_date,
        )
        snap["margin_estimate"] = sebi_registry.estimate_margin_inr(
            legs, spot=spot_px or 0.0, lot_size=lot_size,
        )
        snap["strategy"] = {
            "id": strategy,
            "lots": lots,
            "lot_size": lot_size,
            "spot": spot_px,
            "weekly_available_now": sebi_registry.is_weekly_available(canon, target_date),
            "applicable_circulars": [
                {"ref": ref, "url": sebi_registry.circular_url(ref)}
                for ref in [
                    lot_rule.circular_ref if lot_rule else None,
                    snap["cost_schedule"]["circular_ref"],
                ] if ref
            ],
        }

    return snap


def _build_synthetic_legs(strategy: str, spot: float, symbol: str,
                          lots: int) -> list[dict]:
    """Generate a representative ATM-anchored leg set for a named strategy
    so the cost/margin estimator has something to compute on.  Premiums are
    rough fractions of spot — fine for cost estimation (which scales linearly
    with premium) but not pricing-exact."""
    if not spot:
        return []
    step = sebi_registry.get_strike_step(symbol, spot)
    atm  = round(spot / step) * step
    s = strategy.lower()
    # Default premium ≈ 1.5% of spot for ATM, 0.7% for OTM
    p_atm = round(spot * 0.015, 2)
    p_otm = round(spot * 0.007, 2)
    if s in ("bull_call_spread", "bullcallspread"):
        return [
            {"action": "buy",  "type": "call", "strike": atm,        "premium": p_atm, "lots": lots},
            {"action": "sell", "type": "call", "strike": atm + step, "premium": p_otm, "lots": lots},
        ]
    if s in ("bear_put_spread", "bearputspread"):
        return [
            {"action": "buy",  "type": "put",  "strike": atm,        "premium": p_atm, "lots": lots},
            {"action": "sell", "type": "put",  "strike": atm - step, "premium": p_otm, "lots": lots},
        ]
    if s in ("short_straddle", "shortstraddle"):
        return [
            {"action": "sell", "type": "call", "strike": atm, "premium": p_atm, "lots": lots},
            {"action": "sell", "type": "put",  "strike": atm, "premium": p_atm, "lots": lots},
        ]
    if s in ("long_straddle", "longstraddle"):
        return [
            {"action": "buy",  "type": "call", "strike": atm, "premium": p_atm, "lots": lots},
            {"action": "buy",  "type": "put",  "strike": atm, "premium": p_atm, "lots": lots},
        ]
    if s in ("iron_condor", "ironcondor"):
        return [
            {"action": "sell", "type": "call", "strike": atm + step,     "premium": p_otm, "lots": lots},
            {"action": "buy",  "type": "call", "strike": atm + 2 * step, "premium": p_otm * 0.5, "lots": lots},
            {"action": "sell", "type": "put",  "strike": atm - step,     "premium": p_otm, "lots": lots},
            {"action": "buy",  "type": "put",  "strike": atm - 2 * step, "premium": p_otm * 0.5, "lots": lots},
        ]
    if s in ("covered_call", "coveredcall"):
        return [
            {"action": "sell", "type": "call", "strike": atm + step, "premium": p_otm, "lots": lots},
        ]
    if s in ("long_call", "longcall"):
        return [{"action": "buy", "type": "call", "strike": atm, "premium": p_atm, "lots": lots}]
    if s in ("long_put", "longput"):
        return [{"action": "buy", "type": "put",  "strike": atm, "premium": p_atm, "lots": lots}]
    return []


# ── F&O Stock Universe ────────────────────────────────────────────────────────
# Curated list of NSE F&O eligible stocks (equity derivatives universe, 2025)
_FO_STOCKS: list[tuple[str, str, str, int]] = [
    # (symbol, display_name, sector, lot_size)
    # Banks
    ("HDFCBANK",   "HDFC Bank",               "Banks",       550),
    ("ICICIBANK",  "ICICI Bank",               "Banks",       700),
    ("SBIN",       "State Bank of India",       "Banks",      1500),
    ("AXISBANK",   "Axis Bank",                "Banks",      1200),
    ("KOTAKBANK",  "Kotak Mahindra Bank",       "Banks",       400),
    ("INDUSINDBK", "IndusInd Bank",             "Banks",       300),
    ("PNB",        "Punjab National Bank",      "Banks",      8000),
    ("BANKBARODA", "Bank of Baroda",            "Banks",      2700),
    ("FEDERALBNK", "Federal Bank",              "Banks",     10000),
    ("IDFCFIRSTB", "IDFC First Bank",           "Banks",     10000),
    ("BANDHANBNK", "Bandhan Bank",              "Banks",      5000),
    ("AUBANK",     "AU Small Finance Bank",     "Banks",       500),
    ("RBLBANK",    "RBL Bank",                  "Banks",      6250),
    ("YESBANK",    "Yes Bank",                  "Banks",     40000),
    ("CANBK",      "Canara Bank",               "Banks",      3200),
    ("UNIONBANK",  "Union Bank of India",       "Banks",      4500),
    # IT
    ("TCS",        "Tata Consultancy Services", "IT",           175),
    ("INFY",       "Infosys",                   "IT",           400),
    ("WIPRO",      "Wipro",                     "IT",          1500),
    ("HCLTECH",    "HCL Technologies",          "IT",           350),
    ("TECHM",      "Tech Mahindra",             "IT",           500),
    ("LTIM",       "LTIMindtree",               "IT",           150),
    ("MPHASIS",    "Mphasis",                   "IT",           250),
    ("COFORGE",    "Coforge",                   "IT",           125),
    ("PERSISTENT", "Persistent Systems",        "IT",           125),
    ("KPIT",       "KPIT Technologies",         "IT",           250),
    ("BIRLASOFT",  "Birlasoft",                 "IT",          1000),
    ("CYIENT",     "Cyient",                    "IT",           250),
    ("SONATSOFTW", "Sonata Software",           "IT",           700),
    # FMCG
    ("HINDUNILVR", "Hindustan Unilever",        "FMCG",        300),
    ("ITC",        "ITC",                       "FMCG",       3200),
    ("NESTLEIND",  "Nestle India",              "FMCG",         50),
    ("BRITANNIA",  "Britannia Industries",      "FMCG",        200),
    ("DABUR",      "Dabur India",               "FMCG",       1250),
    ("MARICO",     "Marico",                    "FMCG",       1500),
    ("GODREJCP",   "Godrej Consumer Products",  "FMCG",        500),
    ("TATACONSUM", "Tata Consumer Products",    "FMCG",       1000),
    ("COLPAL",     "Colgate-Palmolive India",   "FMCG",        450),
    ("UBL",        "United Breweries",          "FMCG",        400),
    # Auto
    ("MARUTI",     "Maruti Suzuki India",       "Auto",         100),
    ("TATAMOTORS", "Tata Motors",               "Auto",        2800),
    ("M&M",        "Mahindra & Mahindra",       "Auto",         350),
    ("BAJAJ-AUTO", "Bajaj Auto",               "Auto",         250),
    ("HEROMOTOCO", "Hero MotoCorp",             "Auto",         300),
    ("TVSMOTOR",   "TVS Motor Company",         "Auto",         350),
    ("EICHERMOT",  "Eicher Motors",             "Auto",         175),
    ("ASHOKLEY",   "Ashok Leyland",             "Auto",        4000),
    ("ESCORTS",    "Escorts Kubota",            "Auto",         200),
    ("TIINDIA",    "Tube Investments of India", "Auto",         300),
    # Pharma
    ("SUNPHARMA",  "Sun Pharmaceutical",        "Pharma",       350),
    ("DRREDDY",    "Dr. Reddy's Laboratories",  "Pharma",       125),
    ("CIPLA",      "Cipla",                     "Pharma",       650),
    ("DIVISLAB",   "Divi's Laboratories",       "Pharma",       200),
    ("AUROPHARMA", "Aurobindo Pharma",          "Pharma",       650),
    ("TORNTPHARM", "Torrent Pharmaceuticals",   "Pharma",       250),
    ("GLENMARK",   "Glenmark Pharmaceuticals",  "Pharma",       500),
    ("ALKEM",      "Alkem Laboratories",        "Pharma",       125),
    ("BIOCON",     "Biocon",                    "Pharma",      1800),
    ("MANKIND",    "Mankind Pharma",            "Pharma",       250),
    ("ZYDUSLIFE",  "Zydus Lifesciences",        "Pharma",       600),
    ("IPCALAB",    "IPCA Laboratories",         "Pharma",       350),
    ("LAURUS",     "Laurus Labs",               "Pharma",       600),
    # Energy & Oil
    ("RELIANCE",   "Reliance Industries",       "Energy",       250),
    ("ONGC",       "ONGC",                      "Energy",      3850),
    ("BPCL",       "BPCL",                      "Energy",      4750),
    ("IOC",        "Indian Oil Corporation",    "Energy",      7500),
    ("HINDPETRO",  "HPCL",                      "Energy",      4250),
    ("PETRONET",   "Petronet LNG",              "Energy",      3000),
    ("GAIL",       "GAIL India",                "Energy",      5850),
    ("MRPL",       "MRPL",                      "Energy",      7600),
    # Power & Utilities
    ("NTPC",       "NTPC",                      "Power",       3750),
    ("POWERGRID",  "Power Grid Corporation",    "Power",       3450),
    ("TATAPOWER",  "Tata Power",                "Power",       1500),
    ("ADANIGREEN", "Adani Green Energy",        "Power",        500),
    ("CESC",       "CESC",                      "Power",       2500),
    ("TORNTPOWER", "Torrent Power",             "Power",        500),
    ("NHPC",       "NHPC",                      "Power",      10000),
    ("SJVN",       "SJVN",                      "Power",      10000),
    # Metals & Mining
    ("TATASTEEL",  "Tata Steel",                "Metals",     11350),
    ("JSWSTEEL",   "JSW Steel",                 "Metals",      1350),
    ("HINDALCO",   "Hindalco Industries",       "Metals",      1350),
    ("VEDL",       "Vedanta",                   "Metals",      2600),
    ("SAIL",       "SAIL",                      "Metals",      8550),
    ("COALINDIA",  "Coal India",                "Metals",      4200),
    ("NMDC",       "NMDC",                      "Metals",      6750),
    ("HINDCOPPER", "Hindustan Copper",          "Metals",      4700),
    # Infrastructure
    ("LT",         "Larsen & Toubro",           "Infra",        175),
    ("ADANIPORTS", "Adani Ports & SEZ",         "Infra",       1250),
    ("GMRINFRA",   "GMR Airports Infrastructure","Infra",     22750),
    ("IRB",        "IRB Infrastructure",        "Infra",       9375),
    ("CONCOR",     "Container Corp of India",   "Infra",       1000),
    ("BHEL",       "Bharat Heavy Electricals",  "Defence",     5425),
    ("HAL",        "Hindustan Aeronautics",     "Defence",      175),
    ("BEL",        "Bharat Electronics",        "Defence",     2900),
    # Finance & NBFC
    ("BAJFINANCE", "Bajaj Finance",             "Finance",      125),
    ("BAJAJFINSV", "Bajaj Finserv",             "Finance",      500),
    ("CHOLAFIN",   "Cholamandalam Finance",     "Finance",      500),
    ("MUTHOOTFIN", "Muthoot Finance",           "Finance",      500),
    ("LICHSGFIN",  "LIC Housing Finance",       "Finance",     1500),
    ("PFC",        "Power Finance Corporation", "Finance",     2500),
    ("RECLTD",     "REC Limited",               "Finance",     2500),
    ("M&MFIN",     "Mahindra Finance",          "Finance",     2000),
    # Insurance
    ("HDFCLIFE",   "HDFC Life Insurance",       "Insurance",   1100),
    ("SBILIFE",    "SBI Life Insurance",        "Insurance",    750),
    ("ICICIPRULI", "ICICI Prudential Life",     "Insurance",    700),
    ("LICI",       "LIC of India",              "Insurance",    700),
    # Consumer & Retail
    ("TITAN",      "Titan Company",             "Consumer",     375),
    ("DMART",      "Avenue Supermarts",         "Consumer",      75),
    ("TRENT",      "Trent",                     "Consumer",     350),
    ("BATAINDIA",  "Bata India",                "Consumer",     500),
    ("PAGEIND",    "Page Industries",           "Consumer",      30),
    ("ABFRL",      "Aditya Birla Fashion",      "Consumer",    3500),
    ("MANYAVAR",   "Vedant Fashions",           "Consumer",     700),
    # Paints & Chemicals
    ("ASIANPAINT", "Asian Paints",              "Chemicals",    350),
    ("BERGEPAINT", "Berger Paints",             "Chemicals",   1000),
    ("PIDILITIND", "Pidilite Industries",       "Chemicals",    350),
    ("ATUL",       "Atul",                      "Chemicals",     75),
    # Cement
    ("ULTRACEMCO", "UltraTech Cement",          "Cement",        70),
    ("SHREECEM",   "Shree Cement",              "Cement",        25),
    ("AMBUJACEM",  "Ambuja Cements",            "Cement",      2500),
    ("ACCLTD",     "ACC",                       "Cement",       500),
    ("RAMCOCEM",   "Ramco Cements",             "Cement",       500),
    # Industrials & Capital Goods
    ("HAVELLS",    "Havells India",             "Industrials",  500),
    ("SIEMENS",    "Siemens India",             "Industrials",  125),
    ("ABB",        "ABB India",                 "Industrials",  200),
    ("BOSCHLTD",   "Bosch India",               "Industrials",   25),
    ("CUMMINSIND", "Cummins India",             "Industrials",  400),
    ("THERMAX",    "Thermax",                   "Industrials",  225),
    # New Age / Tech
    ("ETERNAL",    "Eternal Ltd (Zomato)",      "New Age",     5625),
    ("IRCTC",      "IRCTC",                     "New Age",     2000),
    ("NAUKRI",     "Info Edge (Naukri)",        "New Age",      175),
    ("INDIAMART",  "IndiaMart InterMESH",       "New Age",       75),
    # Healthcare
    ("APOLLOHOSP", "Apollo Hospitals",          "Healthcare",   250),
    ("FORTIS",     "Fortis Healthcare",         "Healthcare",  3250),
    ("MAXHEALTH",  "Max Healthcare",            "Healthcare",  1000),
    ("METROPOLIS", "Metropolis Healthcare",     "Healthcare",   250),
    # Realty
    ("DLF",        "DLF",                       "Realty",      1650),
    ("GODREJPROP", "Godrej Properties",         "Realty",       300),
    ("OBEROIRLTY", "Oberoi Realty",             "Realty",       400),
    ("PRESTIGE",   "Prestige Estates",          "Realty",       500),
    # Diversified / Conglomerate
    ("GRASIM",     "Grasim Industries",         "Diversified",  475),
    ("ADANIENT",   "Adani Enterprises",         "Diversified",  250),
    ("LTTS",       "L&T Technology Services",   "Diversified",  125),
]


@router.get("/fo-stocks")
async def get_fo_stocks():
    """
    Return the curated list of NSE F&O-eligible equity stocks.
    Used by the frontend asset selector for the F&O Stocks panel.
    """
    return {
        "stocks": [
            {"sym": sym, "name": name, "sector": sector, "lot": lot}
            for sym, name, sector, lot in _FO_STOCKS
        ],
        "total": len(_FO_STOCKS),
    }


# ── Simulator ─────────────────────────────────────────────────────────────────

class SimulateLegModel(BaseModel):
    action:       str   = Field(..., description="'buy' or 'sell'")
    option_type:  str   = Field(..., description="'call' or 'put'")
    strike:       float = Field(..., gt=0)
    premium:      float = Field(0.0)
    lots:         int   = Field(1, ge=1)
    lot_size:     int   = Field(75, ge=1)
    iv:           float = Field(0.20, ge=0)

    @validator("action")
    def va(cls, v): return v.lower()

    @validator("option_type")
    def vt(cls, v): return v.lower()


class SimulateReq(BaseModel):
    legs:           List[SimulateLegModel]
    S:              float = Field(..., gt=0)
    T_current:      float = Field(..., ge=0, description="Current DTE in years")
    sigma:          float = Field(0.20, ge=0)
    r:              float = Field(RISK_FREE_RATE)
    iv_shift:       float = Field(0.0, description="Additive IV shift, e.g. 0.05 = +5%")
    time_steps:     int   = Field(40, ge=5, le=100)
    spot_range_pct: float = Field(0.22, ge=0.05, le=0.50)


@router.post("/simulate")
async def simulate_strategy(req: SimulateReq):
    """
    Generate multiple payoff curves (DTE slices from T_current → 0) for
    the interactive Options Simulator panel.  All slices are returned in
    a single response to minimise round-trips during animation.
    """
    try:
        legs = [leg.dict() for leg in req.legs]
        result = await asyncio.to_thread(
            simulate_strategy_over_time,
            legs, req.S, req.T_current, req.sigma,
            req.r, req.iv_shift, req.time_steps, req.spot_range_pct,
        )
        return result
    except Exception as exc:
        logger.exception("simulate_strategy failed")
        raise HTTPException(status_code=400, detail=str(exc))
