"""
Hydra-Alpha Engine — Event-Driven Backtesting Engine
Implements the classic event-driven architecture:
  MarketEvent → Strategy → SignalEvent → Portfolio → OrderEvent → ExecutionHandler → FillEvent
Supports: OU pairs strategy, transaction costs, slippage, performance metrics.
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


# ── Data Handler ──────────────────────────────────────────────────────────────

class DataHandler:
    """Reads OHLCV rows chronologically and emits MarketEvents."""

    def __init__(self, symbol: str, rows: list[dict]):
        self.symbol = symbol
        self._rows = rows
        self._idx = 0

    def has_next(self) -> bool:
        return self._idx < len(self._rows)

    def next_event(self) -> Optional[MarketEvent]:
        if not self.has_next():
            return None
        r = self._rows[self._idx]
        self._idx += 1
        return MarketEvent(
            symbol=self.symbol,
            date=r.get("date", ""),
            open=r.get("open", 0),
            high=r.get("high", 0),
            low=r.get("low", 0),
            close=r.get("close", 0),
            volume=r.get("volume", 0),
        )

    def latest(self) -> Optional[dict]:
        i = max(0, self._idx - 1)
        return self._rows[i] if self._rows else None


# ── OU Pairs Strategy ─────────────────────────────────────────────────────────

class OUPairsStrategy:
    """
    Generates LONG/SHORT signals on the spread of two assets
    using the OU process z-score as the trigger.
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
        lookback: int = 60,
    ):
        self.symbol_a   = symbol_a
        self.symbol_b   = symbol_b
        self.hedge_ratio = hedge_ratio
        self.mu          = mu
        self.sigma_eq    = sigma_eq
        self.entry_z     = entry_z
        self.exit_z      = exit_z
        self.prices_a: deque[float] = deque(maxlen=lookback)
        self.prices_b: deque[float] = deque(maxlen=lookback)
        self.position    = 0   # -1 short spread, 0 flat, 1 long spread

    def on_market(self, event: MarketEvent, queue: deque) -> None:
        if event.symbol == self.symbol_a:
            self.prices_a.append(event.close)
        elif event.symbol == self.symbol_b:
            self.prices_b.append(event.close)
        if not self.prices_a or not self.prices_b:
            return

        spread = self.prices_a[-1] - self.hedge_ratio * self.prices_b[-1]
        z = (spread - self.mu) / self.sigma_eq if self.sigma_eq > 0 else 0.0

        if self.position == 0:
            if z >= self.entry_z:
                queue.append(SignalEvent(symbol=self.symbol_a, direction="SHORT", strength=abs(z)))
                queue.append(SignalEvent(symbol=self.symbol_b, direction="LONG",  strength=abs(z)))
                self.position = -1
            elif z <= -self.entry_z:
                queue.append(SignalEvent(symbol=self.symbol_a, direction="LONG",  strength=abs(z)))
                queue.append(SignalEvent(symbol=self.symbol_b, direction="SHORT", strength=abs(z)))
                self.position = 1
        elif self.position != 0 and abs(z) <= self.exit_z:
            queue.append(SignalEvent(symbol=self.symbol_a, direction="EXIT", strength=1.0))
            queue.append(SignalEvent(symbol=self.symbol_b, direction="EXIT", strength=1.0))
            self.position = 0


# ── Portfolio Manager ─────────────────────────────────────────────────────────

class PortfolioManager:
    def __init__(self, initial_capital: float = 1_000_000.0, position_size: float = 0.10):
        self.capital     = initial_capital
        self.initial_cap = initial_capital
        self.pos_size    = position_size
        self.holdings: dict[str, int] = {}
        self.avg_cost:  dict[str, float] = {}
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
            if held != 0:
                direction = "SELL" if held > 0 else "BUY"
                queue.append(OrderEvent(symbol=event.symbol, quantity=abs(held), direction=direction))

    def on_fill(self, event: FillEvent) -> None:
        sym = event.symbol
        q   = event.quantity
        if event.direction == "BUY":
            cost = q * event.fill_price + event.commission
            self.capital -= cost
            prev = self.holdings.get(sym, 0)
            self.holdings[sym] = prev + q
            self.avg_cost[sym] = (
                (self.avg_cost.get(sym, event.fill_price) * abs(prev) + event.fill_price * q)
                / (abs(prev) + q)
            )
        else:
            proceeds = q * event.fill_price - event.commission
            self.capital += proceeds
            self.holdings[sym] = self.holdings.get(sym, 0) - q
            if self.holdings[sym] == 0:
                pnl = (event.fill_price - self.avg_cost.get(sym, event.fill_price)) * q - event.commission
                self.trades.append({"symbol": sym, "pnl": round(pnl, 2),
                                    "date": event.date, "exitPrice": event.fill_price})

        total_market = sum(
            self.holdings.get(s, 0) * self.current_prices.get(s, 0)
            for s in self.holdings
        )
        self.equity_curve.append(round(self.capital + total_market, 2))

    def mark_to_market(self) -> float:
        mv = sum(
            self.holdings.get(s, 0) * self.current_prices.get(s, 0)
            for s in self.holdings
        )
        return self.capital + mv


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


# ── Backtesting runner ────────────────────────────────────────────────────────

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
    if len(returns) > 0:
        avg_ret = statistics.mean(returns)
        std_ret = statistics.stdev(returns) if len(returns) > 1 else 0.0001
        sharpe = (avg_ret / std_ret) * (ann_factor ** 0.5) if std_ret > 0 else 0
    else:
        avg_ret = std_ret = sharpe = 0.0

    # Max drawdown
    peak = equity[0]
    max_dd = 0.0
    for e in equity:
        peak = max(peak, e)
        dd = (peak - e) / peak
        max_dd = max(max_dd, dd)

    win_trades = [t for t in trades if t["pnl"] > 0]
    win_rate = len(win_trades) / len(trades) * 100 if trades else 0

    return {
        "totalReturnPct":  round(total_return, 2),
        "annSharpe":       round(sharpe, 3),
        "maxDrawdownPct":  round(max_dd * 100, 2),
        "winRatePct":      round(win_rate, 1),
        "totalTrades":     len(trades),
        "finalEquity":     round(equity[-1], 2),
        "initialEquity":   round(initial, 2),
    }


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
    # Align dates
    dates_a = {r["date"]: r for r in rows_a}
    dates_b = {r["date"]: r for r in rows_b}
    common_dates = sorted(set(dates_a) & set(dates_b))
    if len(common_dates) < 30:
        return {"error": "Not enough overlapping trading days"}

    queue:    deque = deque()
    handler_a = DataHandler(symbol_a, [dates_a[d] for d in common_dates])
    handler_b = DataHandler(symbol_b, [dates_b[d] for d in common_dates])
    strategy  = OUPairsStrategy(
        symbol_a, symbol_b, hedge_ratio, mu, sigma_eq, entry_z, exit_z
    )
    portfolio = PortfolioManager(initial_capital)
    executor  = ExecutionHandler(commission, slippage_bps)

    for date in common_dates:
        row_a = dates_a[date]
        row_b = dates_b[date]
        portfolio.current_prices["_date"] = date
        portfolio.update_price(symbol_a, row_a["close"])
        portfolio.update_price(symbol_b, row_b["close"])

        evt_a = MarketEvent(symbol=symbol_a, date=date, **{k: row_a[k] for k in ("open","high","low","close","volume") if k in row_a})
        evt_b = MarketEvent(symbol=symbol_b, date=date, **{k: row_b[k] for k in ("open","high","low","close","volume") if k in row_b})

        strategy.on_market(evt_a, queue)
        strategy.on_market(evt_b, queue)

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
        "symbolA": symbol_a,
        "symbolB": symbol_b,
        "metrics": metrics,
        "equityCurve": portfolio.equity_curve[::max(1, len(portfolio.equity_curve)//100)],
        "trades": portfolio.trades[-20:],  # last 20 trades for display
        "totalDays": len(common_dates),
        "config": {
            "hedgeRatio": hedge_ratio,
            "mu": round(mu, 4),
            "sigmaEq": round(sigma_eq, 4),
            "entryZ": entry_z,
            "exitZ": exit_z,
            "commission": commission,
            "slippageBps": slippage_bps,
        },
    }
