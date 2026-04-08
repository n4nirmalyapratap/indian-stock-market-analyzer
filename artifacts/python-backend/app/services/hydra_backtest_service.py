"""
Hydra-Alpha Engine — Event-Driven Backtesting Engine
Implements the classic event-driven architecture:
  MarketEvent → Strategy → SignalEvent → Portfolio → OrderEvent → ExecutionHandler → FillEvent

Fixes applied (code review):
  FIX-1: Correct PnL accounting for both LONG and SHORT round-trips.
          Short entry (SELL) records avg_short_price; cover (BUY) computes
          PnL as (entry - exit) * qty.  Long exit unchanged.
  FIX-2: Strategy signals fire exactly once per date, after BOTH symbols
          have loaded their prices for that bar — eliminates stale-price
          duplicate signals.
"""
from __future__ import annotations
import logging
import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# ── Event types ───────────────────────────────────────────────────────────────

class EventType(Enum):
    MARKET  = "MARKET"
    SIGNAL  = "SIGNAL"
    ORDER   = "ORDER"
    FILL    = "FILL"

@dataclass
class MarketEvent:
    type: EventType = EventType.MARKET
    symbol: str = ""
    date: str = ""
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0

@dataclass
class SignalEvent:
    type: EventType = EventType.SIGNAL
    symbol: str = ""
    direction: str = ""   # LONG / SHORT / EXIT
    strength: float = 1.0

@dataclass
class OrderEvent:
    type: EventType = EventType.ORDER
    symbol: str = ""
    order_type: str = "MKT"
    quantity: int = 0
    direction: str = ""   # BUY / SELL

@dataclass
class FillEvent:
    type: EventType = EventType.FILL
    symbol: str = ""
    date: str = ""
    quantity: int = 0
    direction: str = ""
    fill_price: float = 0.0
    commission: float = 0.0


# ── OU Pairs Strategy ─────────────────────────────────────────────────────────
# FIX-2: accumulate both prices first, evaluate once per bar.

class OUPairsStrategy:
    """
    Generates LONG/SHORT signals on the spread of two assets
    using the OU process z-score as the trigger.
    Signals are emitted exactly ONCE per date, after both symbols report.
    """
    def __init__(
        self,
        symbol_a: str,
        symbol_b: str,
        hedge_ratio: float,
        mu: float,
        sigma_eq: float,
        entry_z: float = 2.0,
        exit_z: float = 0.5,
    ):
        self.symbol_a    = symbol_a
        self.symbol_b    = symbol_b
        self.hedge_ratio = hedge_ratio
        self.mu          = mu
        self.sigma_eq    = sigma_eq
        self.entry_z     = entry_z
        self.exit_z      = exit_z
        self.position    = 0   # -1 short spread, 0 flat, +1 long spread

    def evaluate(self, price_a: float, price_b: float, queue: deque) -> None:
        """
        Called once per date after both prices are known.
        Computes spread z-score and emits signals only when thresholds crossed.
        """
        spread = price_a - self.hedge_ratio * price_b
        z = (spread - self.mu) / self.sigma_eq if self.sigma_eq > 1e-10 else 0.0

        if self.position == 0:
            if z >= self.entry_z:
                # Spread too wide: short A, long B
                queue.append(SignalEvent(symbol=self.symbol_a, direction="SHORT", strength=abs(z)))
                queue.append(SignalEvent(symbol=self.symbol_b, direction="LONG",  strength=abs(z)))
                self.position = -1
            elif z <= -self.entry_z:
                # Spread too narrow: long A, short B
                queue.append(SignalEvent(symbol=self.symbol_a, direction="LONG",  strength=abs(z)))
                queue.append(SignalEvent(symbol=self.symbol_b, direction="SHORT", strength=abs(z)))
                self.position = 1
        elif self.position != 0 and abs(z) <= self.exit_z:
            queue.append(SignalEvent(symbol=self.symbol_a, direction="EXIT", strength=1.0))
            queue.append(SignalEvent(symbol=self.symbol_b, direction="EXIT", strength=1.0))
            self.position = 0


# ── Portfolio Manager ─────────────────────────────────────────────────────────
# FIX-1: separate tracking of long and short positions with correct PnL.

class PortfolioManager:
    def __init__(self, initial_capital: float = 1_000_000.0, position_size: float = 0.10):
        self.capital      = initial_capital
        self.initial_cap  = initial_capital
        self.pos_size     = position_size
        # net shares held: positive = long, negative = short
        self.holdings: dict[str, int] = {}
        # avg_entry_price tracks entry price for both long and short legs
        self.avg_entry:  dict[str, float] = {}
        self.equity_curve: list[float] = [initial_capital]
        self.trades: list[dict] = []
        self.current_prices: dict[str, float] = {}

    def update_price(self, symbol: str, price: float) -> None:
        self.current_prices[symbol] = price

    def on_signal(self, event: SignalEvent, queue: deque) -> None:
        price = self.current_prices.get(event.symbol, 0)
        if price <= 0:
            return
        max_spend = self.capital * self.pos_size
        qty = max(1, int(max_spend / price))

        if event.direction == "LONG":
            queue.append(OrderEvent(symbol=event.symbol, quantity=qty, direction="BUY"))
        elif event.direction == "SHORT":
            queue.append(OrderEvent(symbol=event.symbol, quantity=qty, direction="SELL"))
        elif event.direction == "EXIT":
            held = self.holdings.get(event.symbol, 0)
            if held > 0:
                queue.append(OrderEvent(symbol=event.symbol, quantity=held, direction="SELL"))
            elif held < 0:
                queue.append(OrderEvent(symbol=event.symbol, quantity=abs(held), direction="BUY"))

    def on_fill(self, event: FillEvent) -> None:
        sym = event.symbol
        q   = event.quantity
        prev_held = self.holdings.get(sym, 0)

        if event.direction == "BUY":
            cost = q * event.fill_price + event.commission
            self.capital -= cost
            new_held = prev_held + q
            self.holdings[sym] = new_held

            if prev_held >= 0:
                # Adding to / opening a long position
                total = abs(prev_held) + q
                self.avg_entry[sym] = (
                    self.avg_entry.get(sym, event.fill_price) * abs(prev_held)
                    + event.fill_price * q
                ) / total
            else:
                # Covering a short: prev_held < 0
                cover_qty = min(q, abs(prev_held))
                entry_price = self.avg_entry.get(sym, event.fill_price)
                # Short PnL: sold high, bought low → profit when fill < entry
                pnl = (entry_price - event.fill_price) * cover_qty - event.commission
                self.trades.append({
                    "symbol":     sym,
                    "direction":  "SHORT",
                    "pnl":        round(pnl, 2),
                    "date":       event.date,
                    "entryPrice": round(entry_price, 2),
                    "exitPrice":  round(event.fill_price, 2),
                    "qty":        cover_qty,
                })
                if new_held == 0:
                    self.avg_entry.pop(sym, None)
                elif new_held > 0:
                    # Flipped to long (unusual in pairs, but handle it)
                    self.avg_entry[sym] = event.fill_price

        else:  # SELL
            proceeds = q * event.fill_price - event.commission
            self.capital += proceeds
            new_held = prev_held - q
            self.holdings[sym] = new_held

            if prev_held > 0:
                # Closing / reducing a long position
                close_qty = min(q, prev_held)
                entry_price = self.avg_entry.get(sym, event.fill_price)
                pnl = (event.fill_price - entry_price) * close_qty - event.commission
                self.trades.append({
                    "symbol":     sym,
                    "direction":  "LONG",
                    "pnl":        round(pnl, 2),
                    "date":       event.date,
                    "entryPrice": round(entry_price, 2),
                    "exitPrice":  round(event.fill_price, 2),
                    "qty":        close_qty,
                })
                if new_held == 0:
                    self.avg_entry.pop(sym, None)
            else:
                # Opening / adding to a short position
                total = abs(prev_held) + q
                self.avg_entry[sym] = (
                    self.avg_entry.get(sym, event.fill_price) * abs(prev_held)
                    + event.fill_price * q
                ) / total

        # Mark-to-market equity
        total_mv = sum(
            self.holdings.get(s, 0) * self.current_prices.get(s, 0)
            for s in self.holdings
        )
        self.equity_curve.append(round(self.capital + total_mv, 2))


# ── Execution Handler ─────────────────────────────────────────────────────────

class ExecutionHandler:
    """Simulates fills with slippage and fixed commission."""
    def __init__(self, commission_per_trade: float = 20.0, slippage_bps: float = 5.0):
        self.commission = commission_per_trade
        self.slippage   = slippage_bps / 10_000

    def on_order(self, event: OrderEvent, portfolio: PortfolioManager, queue: deque) -> None:
        price = portfolio.current_prices.get(event.symbol, 0)
        if price <= 0:
            return
        slip = price * self.slippage
        fill_price = price + slip if event.direction == "BUY" else price - slip
        queue.append(FillEvent(
            symbol=event.symbol,
            date=portfolio.current_prices.get("_date", ""),
            quantity=event.quantity,
            direction=event.direction,
            fill_price=round(fill_price, 4),
            commission=self.commission,
        ))


# ── Performance metrics ───────────────────────────────────────────────────────

def _compute_metrics(equity: list[float], initial: float, trades: list[dict]) -> dict:
    if len(equity) < 2:
        return {}
    returns = [
        (equity[i] - equity[i - 1]) / equity[i - 1]
        for i in range(1, len(equity))
        if equity[i - 1] > 0
    ]
    total_return = (equity[-1] - initial) / initial * 100
    ann_factor = 252
    if len(returns) > 1:
        avg_ret = statistics.mean(returns)
        std_ret = statistics.stdev(returns) or 1e-9
        sharpe  = (avg_ret / std_ret) * (ann_factor ** 0.5)
    else:
        avg_ret = std_ret = sharpe = 0.0

    peak = equity[0]
    max_dd = 0.0
    for e in equity:
        peak   = max(peak, e)
        max_dd = max(max_dd, (peak - e) / peak if peak > 0 else 0)

    win_trades = [t for t in trades if t["pnl"] > 0]
    win_rate   = len(win_trades) / len(trades) * 100 if trades else 0

    total_pnl  = sum(t["pnl"] for t in trades)
    avg_win    = statistics.mean([t["pnl"] for t in win_trades]) if win_trades else 0
    loss_trades = [t for t in trades if t["pnl"] <= 0]
    avg_loss   = statistics.mean([t["pnl"] for t in loss_trades]) if loss_trades else 0
    gross_profit = abs(sum(t["pnl"] for t in win_trades))
    gross_loss   = abs(sum(t["pnl"] for t in loss_trades)) if loss_trades else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

    return {
        "totalReturnPct":  round(total_return, 2),
        "annSharpe":       round(sharpe, 3),
        "maxDrawdownPct":  round(max_dd * 100, 2),
        "winRatePct":      round(win_rate, 1),
        "totalTrades":     len(trades),
        "totalPnL":        round(total_pnl, 2),
        "avgWin":          round(avg_win, 2),
        "avgLoss":         round(avg_loss, 2),
        "profitFactor":    round(profit_factor, 3),
        "finalEquity":     round(equity[-1], 2),
        "initialEquity":   round(initial, 2),
    }


# ── Backtesting runner ────────────────────────────────────────────────────────

def run_pairs_backtest(
    symbol_a: str,
    symbol_b: str,
    rows_a: list[dict],
    rows_b: list[dict],
    hedge_ratio: float,
    mu: float,
    sigma_eq: float,
    initial_capital: float = 1_000_000.0,
    commission: float = 20.0,
    slippage_bps: float = 5.0,
    entry_z: float = 2.0,
    exit_z: float = 0.5,
) -> dict:
    """Run a full event-driven pairs backtest."""
    dates_a = {r["date"]: r for r in rows_a if r.get("close")}
    dates_b = {r["date"]: r for r in rows_b if r.get("close")}
    common_dates = sorted(set(dates_a) & set(dates_b))
    if len(common_dates) < 30:
        return {"error": "Not enough overlapping trading days"}

    queue     = deque()
    strategy  = OUPairsStrategy(symbol_a, symbol_b, hedge_ratio, mu, sigma_eq, entry_z, exit_z)
    portfolio = PortfolioManager(initial_capital)
    executor  = ExecutionHandler(commission, slippage_bps)

    for date in common_dates:
        row_a = dates_a[date]
        row_b = dates_b[date]

        # ── FIX-2: update prices for BOTH symbols, then evaluate strategy ONCE ──
        portfolio.current_prices["_date"] = date
        portfolio.update_price(symbol_a, row_a["close"])
        portfolio.update_price(symbol_b, row_b["close"])

        # Strategy evaluates spread with fully synchronised prices
        strategy.evaluate(row_a["close"], row_b["close"], queue)

        # Drain event queue
        while queue:
            e = queue.popleft()
            if e.type == EventType.SIGNAL:
                portfolio.on_signal(e, queue)
            elif e.type == EventType.ORDER:
                executor.on_order(e, portfolio, queue)
            elif e.type == EventType.FILL:
                portfolio.on_fill(e)

    metrics = _compute_metrics(portfolio.equity_curve, initial_capital, portfolio.trades)

    return {
        "symbolA":     symbol_a,
        "symbolB":     symbol_b,
        "metrics":     metrics,
        "equityCurve": portfolio.equity_curve[::max(1, len(portfolio.equity_curve) // 100)],
        "trades":      portfolio.trades[-20:],
        "totalDays":   len(common_dates),
        "config": {
            "hedgeRatio":  hedge_ratio,
            "mu":          round(mu, 4),
            "sigmaEq":     round(sigma_eq, 4),
            "entryZ":      entry_z,
            "exitZ":       exit_z,
            "commission":  commission,
            "slippageBps": slippage_bps,
        },
    }
