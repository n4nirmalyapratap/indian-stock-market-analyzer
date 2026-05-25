"""
options_backtest_service.py
Event-driven options strategy backtester for Indian markets.

Design principles:
- Point-in-time data: only historical prices known before entry date are used
- No lookahead bias: HV is calculated from a rolling window ending on entry date
- Monthly expiry cycle: last expiry weekday of each month, per-symbol
- Realistic cost model: commission per lot + bid-ask spread slippage
- Full P&L tracking: entry premium, exit premium, expiry settlement
"""

import asyncio
import math
import logging
import calendar
from datetime import date, timedelta
from typing import Optional

import numpy as np
from scipy.stats import norm as _norm   # module-level import — not inside hot loop

from .options_service import bs_price as _bs_price
from . import sebi_registry as _sebi
from . import nse_bhavcopy_service as _bhav

logger = logging.getLogger("options_backtest")

# ── Costs (legacy constants — retained for back-compat with tests/imports) ───
# Realistic regulatory costs (STT/GST/stamp/SEBI/exchange) are now applied via
# sebi_registry.compute_leg_costs(); these constants remain only for callers
# that import them directly.
COMMISSION_PER_LOT = 20.0   # INR — flat brokerage per lot (Zerodha-style)
SLIPPAGE_PCT       = 0.003  # 0.3% of premium as bid-ask slippage

# ── Strategy templates ────────────────────────────────────────────────────────

STRATEGIES = [
    "long_call",
    "long_put",
    "short_call",
    "short_put",
    "straddle",
    "short_straddle",
    "strangle",
    "short_strangle",
    "bull_call_spread",
    "bear_put_spread",
    "iron_condor",
    "butterfly",
    # covered_call: short OTM call against a (assumed) long underlying position
    # We can only model the option leg; underlying P&L is excluded.
    "covered_call",
]


# NSE/BSE monthly expiry weekday per instrument (0=Mon … 6=Sun, matches date.weekday())
# NIFTY/NIFTY50  → last Thursday (3)
# BANKNIFTY      → last Wednesday (2)
# FINNIFTY       → last Tuesday  (1)
# MIDCPNIFTY     → last Monday   (0)
# SENSEX/BANKEX  → last Friday   (4)
EXPIRY_DOW: dict[str, int] = {
    "NIFTY":      3,
    "NIFTY50":    3,
    "^NSEI":      3,
    "BANKNIFTY":  2,
    "^NSEBANK":   2,
    "FINNIFTY":   1,
    "^CNXFIN":    1,
    "NIFTY_FIN_SERVICE.NS": 1,
    "MIDCPNIFTY": 0,
    "^NSMIDCP":   0,
    "SENSEX":     4,
    "^BSESN":     4,
    "BANKEX":     4,
    "BANKEX.BO":  4,
    "^BSXN":      4,
}


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Return the last occurrence of `weekday` (0=Mon…6=Sun) in the given month."""
    cal = calendar.monthcalendar(year, month)
    days = [week[weekday] for week in cal if week[weekday] != 0]
    return date(year, month, max(days))


def _last_thursday(year: int, month: int) -> date:
    """Return the last Thursday of the given month (backward-compat wrapper)."""
    return _last_weekday_of_month(year, month, weekday=3)


def _expiry_dates(start: date, end: date, symbol: str = "NIFTY",
                  use_weekly: bool = False) -> list[date]:
    """Generate expiry dates within [start, end].

    Args:
        start, end:  Date range (inclusive).
        symbol:      Index symbol — determines which weekday is the expiry day.
        use_weekly:  If True, generate every weekly expiry (every occurrence of
                     the expiry weekday).  If False (default), generate only the
                     last occurrence each month (monthly expiry).

    Historical note: SEBI restricted weekly options (May 2024).  Only NIFTY 50
    and SENSEX still have weekly contracts.  For backtesting periods that pre-date
    the restriction, pass use_weekly=True to model the historical weekly cycle.
    """
    upper   = symbol.upper()
    weekday = EXPIRY_DOW.get(upper, 3)   # default Thursday

    if use_weekly:
        # Walk day-by-day and collect every occurrence of the target weekday
        exps = []
        d = start
        # Advance to the first occurrence of the target weekday on or after start
        days_ahead = (weekday - d.weekday()) % 7
        d = d + timedelta(days=days_ahead)
        while d <= end:
            exps.append(d)
            d = d + timedelta(weeks=1)
        return exps

    # Monthly: last weekday of each month
    exps   = []
    yr, mo = start.year, start.month
    while True:
        exp = _last_weekday_of_month(yr, mo, weekday)
        if exp > end:
            break
        if exp >= start:
            exps.append(exp)
        mo += 1
        if mo > 12:
            mo, yr = 1, yr + 1
    return exps


def _to_yf_sym(symbol: str) -> str:
    """Resolve a human-readable Indian market symbol to its Yahoo Finance ticker."""
    upper = symbol.upper()
    _MAP = {
        "NIFTY":      "^NSEI",
        "NIFTY50":    "^NSEI",
        "BANKNIFTY":  "^NSEBANK",
        "FINNIFTY":   "^CNXFIN",
        "MIDCPNIFTY": "^NSMIDCP",
        "SENSEX":     "^BSESN",
        "BANKEX":     "BANKEX.BO",   # BSE BANKEX — try .BO format
        # Zomato rebranded to Eternal Ltd in 2025; NSE symbol → ETERNAL
        "ZOMATO":     "ETERNAL.NS",
        "ETERNAL":    "ETERNAL.NS",
    }
    if upper in _MAP:
        return _MAP[upper]
    if upper.startswith("^") or "." in upper:
        return upper
    return f"{upper}.NS"


def _to_yf_sym_candidates(symbol: str) -> list[str]:
    """Return ordered list of Yahoo Finance tickers to try for a symbol."""
    upper = symbol.upper()
    _FALLBACKS = {
        # BANKEX: ^BSXN rarely has data; fall back to SENSEX as last resort
        "BANKEX":   ["BANKEX.BO", "^BSXN", "^BSESN"],
        # FINNIFTY: ^CNXFIN returns only 1 bar in recent yfinance versions;
        #           NIFTY_FIN_SERVICE.NS is the reliable fallback.
        "FINNIFTY": ["^CNXFIN", "NIFTY_FIN_SERVICE.NS"],
    }
    if upper in _FALLBACKS:
        return _FALLBACKS[upper]
    return [_to_yf_sym(symbol)]


def _strike_step(S: float, symbol: str = "") -> float:
    """NSE standard strike increment (symbol-aware via SEBI registry).

    When called without a symbol, falls back to the legacy spot-bucketed
    ladder so older call sites keep working unchanged.
    """
    from .sebi_registry import get_strike_step
    if symbol:
        return get_strike_step(symbol, S)
    if S >= 10_000:
        return 100.0
    if S >= 2_000:
        return 50.0
    if S >= 500:
        return 10.0
    return 5.0


def _atm(S: float, symbol: str = "") -> float:
    step = _strike_step(S, symbol)
    return round(S / step) * step


def _build_legs(strategy: str, S: float, otm_pct: float,
                symbol: str = "") -> list[dict]:
    """
    Build raw leg definitions (strike, action, option_type) for a strategy.
    otm_pct: fraction of S used as OTM wing distance (e.g. 0.05 = 5%).

    IMPORTANT: strikes must be internally consistent — each leg must have a
    valid option premium (i.e. non-negative intrinsic or enough time value).
    For spread strategies, the wing strike must be further OTM than the body.
    """
    step    = _strike_step(S, symbol)
    atm     = _atm(S, symbol)
    otm_d   = max(step, round(S * otm_pct / step) * step)
    wide_d  = max(step * 2, otm_d * 2)

    def L(a: str, t: str, k: float) -> dict:
        return {"action": a, "option_type": t, "strike": k}

    if strategy == "long_call":
        return [L("buy", "call", atm)]
    if strategy == "long_put":
        return [L("buy", "put", atm)]
    if strategy == "short_call":
        return [L("sell", "call", atm)]
    if strategy == "short_put":
        return [L("sell", "put", atm)]
    if strategy == "straddle":
        return [L("buy", "call", atm), L("buy", "put", atm)]
    if strategy == "short_straddle":
        return [L("sell", "call", atm), L("sell", "put", atm)]
    if strategy == "strangle":
        return [L("buy", "call", atm + otm_d), L("buy", "put", atm - otm_d)]
    if strategy == "short_strangle":
        return [L("sell", "call", atm + otm_d), L("sell", "put", atm - otm_d)]
    if strategy == "bull_call_spread":
        return [L("buy", "call", atm), L("sell", "call", atm + otm_d)]
    if strategy == "bear_put_spread":
        return [L("buy", "put", atm), L("sell", "put", atm - otm_d)]
    if strategy == "iron_condor":
        # Sell near-OTM wings, buy far-OTM wings for defined risk
        return [
            L("sell", "call", atm + otm_d),   # near OTM call (sold)
            L("buy",  "call", atm + wide_d),  # far  OTM call (protection)
            L("sell", "put",  atm - otm_d),   # near OTM put  (sold)
            L("buy",  "put",  atm - wide_d),  # far  OTM put  (protection)
        ]
    if strategy == "butterfly":
        # Long call butterfly: buy lower, sell 2× ATM (single leg, 2 lots), buy upper
        # Use a 3-leg representation so commission is charged correctly (3 strikes, not 4).
        def L2(a: str, t: str, k: float, n: int = 1) -> dict:
            return {"action": a, "option_type": t, "strike": k, "lots_mult": n}
        return [
            {"action": "buy",  "option_type": "call", "strike": atm - otm_d, "lots_mult": 1},
            {"action": "sell", "option_type": "call", "strike": atm,          "lots_mult": 2},
            {"action": "buy",  "option_type": "call", "strike": atm + otm_d, "lots_mult": 1},
        ]
    if strategy == "covered_call":
        # Option leg only: short OTM call (underlying position not modelled)
        return [L("sell", "call", atm + otm_d)]

    raise ValueError(f"Unknown strategy: {strategy}")


# Backwards-compat alias — previously a duplicated inline BS pricer; now
# delegates to the canonical implementation in options_service so we do not
# carry two copies that can drift apart.
def _bs_price_fast(S: float, K: float, T: float, r: float, sigma: float,
                   opt_type: str) -> float:
    return _bs_price(S, K, T, r, sigma, opt_type)


def _apply_slippage(price: float, action: str, is_entry: bool) -> float:
    """
    Adjust price for bid-ask slippage.
    Buyers pay more (ask); sellers receive less (bid).
    is_entry=True: original action determines direction.
    is_entry=False: closing action is the reverse.
    """
    slip = price * SLIPPAGE_PCT
    if is_entry:
        return price + slip if action == "buy" else price - slip
    else:
        # closing: original buy → now selling, original sell → now buying
        return price - slip if action == "buy" else price + slip


def _run_backtest_sync(
    symbol: str,
    strategy: str,
    start_date: str,
    end_date: str,
    lots: int,
    lot_size: int,
    entry_dte: int,
    roll_dte: int,
    otm_pct: float,
    risk_free: float,
    use_weekly: bool = False,
) -> dict:
    """
    Synchronous implementation of the event-driven backtest.
    Runs blocking I/O (yfinance) and CPU-intensive pandas/numpy work.
    Called via asyncio.to_thread() from the async route handler.
    """
    import yfinance as yf
    import pandas as pd

    candidates = _to_yf_sym_candidates(symbol)

    # ── Fetch historical OHLCV (try each candidate ticker until one has data) ─
    fetch_start = (
        pd.to_datetime(start_date) - pd.Timedelta(days=60)
    ).strftime("%Y-%m-%d")

    raw = None
    last_err: str = ""
    for yf_sym in candidates:
        try:
            r = yf.Ticker(yf_sym).history(start=fetch_start, end=end_date,
                                           auto_adjust=True)
            if r is not None and not r.empty and len(r) >= 20:
                raw = r
                break
            last_err = f"Insufficient rows for {yf_sym}"
        except Exception as exc:
            last_err = str(exc)

    if raw is None:
        return {"error": f"Data fetch failed for {symbol}: {last_err}"}

    # Normalize column names (.history() returns Title-cased columns)
    raw.columns = [c.split()[0].capitalize() for c in raw.columns]

    hist = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    # Strip timezone info — .history() returns tz-aware (Asia/Kolkata); we need naive dates
    idx = pd.to_datetime(hist.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    hist.index = idx.normalize()
    hist = hist.sort_index()

    # ── Historical Volatility (30-day rolling, annualised, no lookahead) ─────
    hist["log_ret"] = np.log(hist["Close"] / hist["Close"].shift(1))
    hist["HV30"]    = hist["log_ret"].rolling(30).std() * math.sqrt(252)
    hist["HV30"]    = hist["HV30"].clip(lower=0.05)
    hist["HV30"]    = hist["HV30"].ffill().bfill().fillna(0.20)

    # ── Generate expiry cycle (correct weekday per symbol, holiday-aware) ────
    # The legacy `_expiry_dates` helper is preserved for back-compat in tests,
    # but the backtest loop uses the SEBI registry directly so that scheduled
    # expiries falling on NSE holidays (e.g. Republic Day 26 Jan 2024 for
    # SENSEX, Mahashivratri 26 Feb 2025 for BANKNIFTY) are shifted to the
    # previous trading day, matching real-world settlement.
    start_dt = pd.to_datetime(start_date).date()
    end_dt   = pd.to_datetime(end_date).date()
    if use_weekly:
        expiries = _sebi.weekly_expiries(symbol, start_dt, end_dt, holiday_adjust=True)
    else:
        expiries = _sebi.monthly_expiries(symbol, start_dt, end_dt, holiday_adjust=True)

    if not expiries:
        return {"error": "No expiry dates fall within the specified date range"}

    trading_days = hist.index

    def nearest_trading_day(target: date, after: bool = True) -> Optional[object]:
        ts = pd.Timestamp(target)
        avail = trading_days[trading_days >= ts] if after else trading_days[trading_days <= ts]
        return avail[0] if len(avail) > 0 else None

    # ── Main simulation loop ──────────────────────────────────────────────────
    trades:       list[dict] = []
    equity_curve: list[dict] = []
    cum_pnl       = 0.0
    # Premium-source accounting: every leg fill (entry + exit) is tagged with
    # one of {'bhavcopy', 'synthetic_bs'}.  Aggregated into the result so the
    # UI can show an honesty badge ("X% real / Y% synthetic").
    # Three honest buckets:
    #   bhavcopy            — fill price came from the NSE/BSE settlement archive
    #   synthetic_bs        — bhavcopy cache miss; Black-Scholes fallback used
    #   intrinsic_settlement— exit at T<=0; cash-settled at intrinsic value
    #                          (not a quote at all, kept separate from "real")
    premium_source_counter = {"bhavcopy": 0, "synthetic_bs": 0,
                              "intrinsic_settlement": 0}

    def _resolve_premium(opt_type: str, K: float, S_now: float, T_now: float,
                         iv_now: float, on_date: date, exp_date: date) -> tuple[float, str]:
        """Try real bhavcopy CLOSE first; on miss, fall back to Black-Scholes
        and tag the source loudly."""
        real = _bhav.lookup_premium(symbol, exp_date, K, opt_type, on_date)
        if real is not None and real > 0:
            return float(real), "bhavcopy"
        return _bs_price_fast(S_now, K, T_now, risk_free, iv_now, opt_type), "synthetic_bs"

    for exp in expiries:
        entry_target = exp - timedelta(days=entry_dte)
        entry_ts     = nearest_trading_day(entry_target, after=True)
        if entry_ts is None or entry_ts.date() >= exp:
            continue
        if entry_ts not in hist.index:
            continue

        entry_row = hist.loc[entry_ts]
        S_entry   = float(entry_row["Close"])
        iv_entry  = float(entry_row["HV30"])
        T_entry   = max(0.001, (exp - entry_ts.date()).days / 365.0)

        if roll_dte > 0:
            exit_target = exp - timedelta(days=roll_dte)
            exit_ts     = nearest_trading_day(exit_target, after=True)
        else:
            exit_ts = nearest_trading_day(exp, after=False)

        if exit_ts is None or exit_ts not in hist.index:
            continue

        exit_row = hist.loc[exit_ts]
        S_exit   = float(exit_row["Close"])
        iv_exit  = float(exit_row["HV30"])
        T_exit   = max(0.0, (exp - exit_ts.date()).days / 365.0)

        try:
            raw_legs = _build_legs(strategy, S_entry, otm_pct, symbol)
        except ValueError as e:
            return {"error": str(e)}

        entry_costs_total = 0.0
        exit_costs_total  = 0.0
        cost_breakdown    = {
            "brokerage": 0.0, "stt": 0.0, "exchange_charge": 0.0,
            "sebi_charge": 0.0, "stamp_duty": 0.0, "gst": 0.0,
        }
        entry_date_obj = entry_ts.date() if hasattr(entry_ts, "date") else entry_ts
        exit_date_obj  = exit_ts.date()  if hasattr(exit_ts,  "date") else exit_ts

        entry_credit = 0.0
        filled_legs: list[dict] = []

        for leg in raw_legs:
            K            = float(leg["strike"])
            opt_type     = leg["option_type"]
            action       = leg["action"]
            # lots_mult > 1 for butterfly ATM sell (2 lots at ATM, not 4 separate legs)
            effective_lots = lots * int(leg.get("lots_mult", 1))

            raw_price, src_entry = _resolve_premium(
                opt_type, K, S_entry, T_entry, iv_entry, entry_date_obj, exp,
            )
            premium_source_counter[src_entry] += 1
            fill_price = _apply_slippage(raw_price, action, is_entry=True)
            fill_price = max(0.01, fill_price)

            qty = effective_lots * lot_size
            if action == "sell":
                entry_credit += fill_price * qty
            else:
                entry_credit -= fill_price * qty

            entry_cb = _sebi.compute_leg_costs(
                action=action, premium=fill_price, quantity=qty,
                is_entry=True, on_date=entry_date_obj,
            )
            entry_costs_total += entry_cb.total
            for k in cost_breakdown:
                cost_breakdown[k] += getattr(entry_cb, k)

            filled_legs.append({**leg, "premium": fill_price, "lots": effective_lots,
                                 "lot_size": lot_size, "iv": iv_entry,
                                 "_entry_src": src_entry})

        exit_debit = 0.0

        for leg in filled_legs:
            K            = float(leg["strike"])
            opt_type     = leg["option_type"]
            action       = leg["action"]
            effective_lots = int(leg["lots"])  # already includes lots_mult from entry loop

            is_exercise_exit = (T_exit <= 0)
            if is_exercise_exit:
                # Cash settlement at expiry — intrinsic value is the truth,
                # but it is NOT a quote.  Counted in its own bucket.
                exit_price = max(0.0, S_exit - K) if opt_type == "call" else max(0.0, K - S_exit)
                src_exit   = "intrinsic_settlement"
                premium_source_counter["intrinsic_settlement"] += 1
            else:
                raw_exit, src_exit = _resolve_premium(
                    opt_type, K, S_exit, T_exit, iv_exit, exit_date_obj, exp,
                )
                premium_source_counter[src_exit] += 1
                exit_action = "sell" if action == "buy" else "buy"
                exit_price  = _apply_slippage(raw_exit, exit_action, is_entry=False)
                exit_price  = max(0.0, exit_price)
            leg["_exit_src"] = src_exit

            qty = effective_lots * lot_size
            if action == "buy":
                exit_debit -= exit_price * qty
            else:
                exit_debit += exit_price * qty

            exit_cb = _sebi.compute_leg_costs(
                action=action, premium=exit_price, quantity=qty,
                is_entry=False, on_date=exit_date_obj,
                is_exercise=is_exercise_exit,
            )
            exit_costs_total += exit_cb.total
            for k in cost_breakdown:
                cost_breakdown[k] += getattr(exit_cb, k)

        total_commission = entry_costs_total + exit_costs_total

        # Covered-call honesty fix: option leg alone understates P&L because the
        # short call is hedged by the assumed long underlying.  Track the
        # underlying P&L explicitly so the user sees a complete picture.
        underlying_pnl = 0.0
        if strategy == "covered_call":
            underlying_pnl = (S_exit - S_entry) * lots * lot_size

        trade_pnl = entry_credit - exit_debit - total_commission + underlying_pnl
        cum_pnl  += trade_pnl

        # Per-trade premium-source rollup: every leg fill gets its own
        # entry+exit tag so an auditor can reconstruct exactly which prices
        # came from real settlement data.
        leg_sources = [
            {"strike": float(l["strike"]), "option_type": l["option_type"],
             "action": l["action"],
             "entry_premium_source": l.get("_entry_src", "synthetic_bs"),
             "exit_premium_source":  l.get("_exit_src",  "synthetic_bs")}
            for l in filled_legs
        ]
        trade_counter = {"bhavcopy": 0, "synthetic_bs": 0,
                         "intrinsic_settlement": 0}
        for s in leg_sources:
            trade_counter[s["entry_premium_source"]] += 1
            trade_counter[s["exit_premium_source"]]  += 1
        # Promote the dominant source to a single trade-level label so the
        # trades table can show a one-glance honesty pill per row.
        trade_premium_source = max(trade_counter, key=trade_counter.get)

        # Strip internal _entry_src/_exit_src bookkeeping keys from filled_legs
        # — they are surfaced via leg_premium_sources above and shouldn't
        # leak into any downstream API consumer that touches filled_legs.
        for l in filled_legs:
            l.pop("_entry_src", None)
            l.pop("_exit_src",  None)

        trades.append({
            "entry_date":     str(entry_ts.date()),
            "exit_date":      str(exit_ts.date()),
            "expiry":         str(exp),
            "spot_entry":     round(S_entry, 2),
            "spot_exit":      round(S_exit, 2),
            "iv_entry_pct":   round(iv_entry * 100, 2),
            "entry_credit":   round(entry_credit, 2),
            "exit_debit":     round(exit_debit, 2),
            "commission":     round(total_commission, 2),
            "underlying_pnl": round(underlying_pnl, 2),
            "trade_pnl":      round(trade_pnl, 2),
            "cumulative_pnl": round(cum_pnl, 2),
            "costs_breakdown": {k: round(v, 2) for k, v in cost_breakdown.items()},
            "strategy":       strategy,
            # Honesty fields — see premium_source_breakdown for legend
            "premium_source":            trade_premium_source,
            "premium_source_breakdown":  trade_counter,
            "leg_premium_sources":       leg_sources,
        })
        equity_curve.append({
            "date":           str(exit_ts.date()),
            "cumulative_pnl": round(cum_pnl, 2),
        })

    if not trades:
        return {"error": "No trades executed — check date range and entry_dte settings"}

    # ── Performance metrics ───────────────────────────────────────────────────
    pnls      = [t["trade_pnl"] for t in trades]
    winners   = [p for p in pnls if p > 0]
    losers    = [p for p in pnls if p < 0]
    pnl_arr   = np.array(pnls, dtype=float)

    win_rate      = len(winners) / len(pnls) * 100 if pnls else 0.0
    avg_win       = float(np.mean(winners)) if winners else 0.0
    avg_loss      = float(np.mean(losers))  if losers  else 0.0
    total_wins    = sum(winners)
    total_losses  = abs(sum(losers))
    profit_factor = (total_wins / total_losses) if total_losses > 0 else float("inf")

    cum_series  = np.cumsum(pnl_arr)
    running_max = np.maximum.accumulate(np.maximum(cum_series, 0))
    drawdowns   = running_max - cum_series
    max_dd      = float(np.max(drawdowns))

    freq = math.sqrt(12)
    sharpe  = float(np.mean(pnl_arr) / np.std(pnl_arr) * freq) if np.std(pnl_arr) > 0 else 0.0
    neg_arr = pnl_arr[pnl_arr < 0]
    down_std = float(np.std(neg_arr)) if len(neg_arr) > 1 else (abs(avg_loss) or 1.0)
    sortino  = float(np.mean(pnl_arr) / down_std * freq) if down_std > 0 else 0.0

    total_fills        = sum(premium_source_counter.values()) or 1
    bhav_n             = premium_source_counter["bhavcopy"]
    synth_n            = premium_source_counter["synthetic_bs"]
    intrinsic_n        = premium_source_counter["intrinsic_settlement"]
    real_pct           = round(bhav_n / total_fills * 100, 1)
    synth_pct          = round(synth_n / total_fills * 100, 1)
    intrinsic_pct      = round(intrinsic_n / total_fills * 100, 1)
    primary_source     = max(premium_source_counter, key=premium_source_counter.get)

    return {
        "trades":       trades,
        "equity_curve": equity_curve,
        "premium_source_breakdown": {
            "bhavcopy_fills":             bhav_n,
            "synthetic_bs_fills":         synth_n,
            "intrinsic_settlement_fills": intrinsic_n,
            "total_fills":                total_fills,
            "real_pct":                   real_pct,
            "synthetic_pct":              synth_pct,
            "intrinsic_settlement_pct":   intrinsic_pct,
            "primary_source":             primary_source,
            "note": (
                "bhavcopy = NSE/BSE F&O daily settlement archive (real quote); "
                "synthetic_bs = Black-Scholes fallback used when the exact "
                "contract is missing from the cache; "
                "intrinsic_settlement = exit at expiry (T<=0) settled at "
                "intrinsic value — not a quote, tracked separately so the "
                "real-data ratio is not inflated."
            ),
        },
        "metrics": {
            "symbol":        symbol,
            "strategy":      strategy,
            "total_trades":  len(trades),
            "win_rate":      round(win_rate, 1),
            "avg_win":       round(avg_win, 2),
            "avg_loss":      round(avg_loss, 2),
            "profit_factor": round(profit_factor, 3) if profit_factor < 1e9 else None,
            "total_pnl":     round(float(cum_pnl), 2),
            "max_drawdown":  round(max_dd, 2),
            "sharpe_ratio":  round(sharpe, 3),
            "sortino_ratio": round(sortino, 3),
            "best_trade":    round(float(max(pnls)), 2),
            "worst_trade":   round(float(min(pnls)), 2),
            "avg_trade_pnl": round(float(np.mean(pnl_arr)), 2),
            "start_date":    start_date,
            "end_date":      end_date,
            "lots":          lots,
            "lot_size":      lot_size,
            "entry_dte":     entry_dte,
            "otm_pct":       otm_pct,
        },
    }


async def run_backtest(
    symbol: str,
    strategy: str,
    start_date: str,
    end_date: str,
    lots: int = 1,
    lot_size: int = 65,
    entry_dte: int = 30,
    roll_dte: int   = 0,
    otm_pct: float  = 0.05,
    risk_free: float = 0.07,
    use_weekly: bool = False,
) -> dict:
    """
    Async wrapper — runs blocking I/O and CPU work in a thread pool
    so the FastAPI event loop is never blocked.
    """
    return await asyncio.to_thread(
        _run_backtest_sync,
        symbol, strategy, start_date, end_date,
        lots, lot_size, entry_dte, roll_dte, otm_pct, risk_free, use_weekly,
    )
