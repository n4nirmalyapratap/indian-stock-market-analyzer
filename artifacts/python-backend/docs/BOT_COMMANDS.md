# Bot Command Reference

_Auto-generated from `app/services/bot_dispatcher.py`._

Both Telegram and WhatsApp share this command spec. Telegram uses `/command`, WhatsApp uses `!command`. Either bot also accepts plain natural language — the NLP layer routes intents to the same handlers.

All bots are **stateless** with respect to your trading account: portfolio P&L and VaR commands accept inline holdings of the form `SYMBOL:qty[@avg]` (e.g. `RELIANCE:10@2400 TCS:5`). Alerts are keyed only by chat ID — no account linking required.

## Help

| Command | Aliases | Usage | Description |
|---------|---------|-------|-------------|
| `/start` | — | `/start` | Welcome message |
| `/help` | `?`, `menu`, `commands` | `/help` | Show this command list |
| `/status` | — | `/status` | Bot status & subscription count |

## Market

| Command | Aliases | Usage | Description |
|---------|---------|-------|-------------|
| `/sectors` | — | `/sectors` | Sector performance overview |
| `/rotation` | — | `/rotation` | Sector rotation report (where to invest) |
| `/movers` | `gainers`, `losers` | `/movers` | Top gainers & losers |
| `/heatmap` | — | `/heatmap` | Sector % change heatmap |
| `/news` | — | `/news [SYMBOL]` | Latest market news headlines |

## Stock

| Command | Aliases | Usage | Description |
|---------|---------|-------|-------------|
| `/analyze` | `a`, `stock` | `/analyze SYMBOL` | Full technical analysis |
| `/entry` | — | `/entry SYMBOL` | Entry/exit signal with target & stop-loss |
| `/dcf` | `intrinsic` | `/dcf SYMBOL` | Intrinsic-value (DCF) snapshot |
| `/sentiment` | — | `/sentiment SYMBOL` | Price-action sentiment score |
| `/forecast` | — | `/forecast SYMBOL [days]` | N-day price forecast (Hydra) |

## Signals

| Command | Aliases | Usage | Description |
|---------|---------|-------|-------------|
| `/patterns` | — | `/patterns` | CALL/PUT chart-pattern signals |
| `/scan` | — | `/scan` | Trigger a fresh pattern scan |
| `/scanners` | `scanner` | `/scanners [list|run ID]` | List or run custom scanners |

## Quant

| Command | Aliases | Usage | Description |
|---------|---------|-------|-------------|
| `/pairs` | — | `/pairs SYMBOL_A SYMBOL_B` | Cointegrated pairs analysis |
| `/backtest` | — | `/backtest SYMBOL_A SYMBOL_B` | Pairs-trading backtest |
| `/var` | — | `/var SYM:qty[@avg] …` | Portfolio Value-at-Risk (uses /portfolio holdings) |
| `/portfolio` | `pnl`, `pf` | `/portfolio SYM:qty@avg …` | Stateless P&L from inline holdings |

## Options

| Command | Aliases | Usage | Description |
|---------|---------|-------|-------------|
| `/greeks` | — | `/greeks SYM CALL|PUT STRIKE DAYS [IV%]` | Black-Scholes greeks for a single option |
| `/payoff` | — | `/payoff SYM STRATEGY STRIKE [WIDTH]` | Strategy payoff (max profit/loss/breakevens) |
| `/cost` | — | `/cost SYM CALL|PUT STRIKE QTY PREMIUM` | Per-trade cost breakdown (premium × lot + fees) |

## Alerts

| Command | Aliases | Usage | Description |
|---------|---------|-------|-------------|
| `/alerts` | `alert` | `/alerts list|add SYM TYPE VAL|remove ID|clear` | List, add or remove price/pattern alerts |

## Inline holdings syntax

```
RELIANCE:10@2400  → 10 shares of RELIANCE bought at ₹2400
TCS:5             → 5 shares of TCS, no cost basis
```

Use this with `/portfolio` (P&L) or `/var` (Value-at-Risk).
