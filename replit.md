# Nifty Node — Indian Stock Market Analyzer

## Project Overview

A full-stack Indian stock market analysis platform with:
- **User app** (`/`) — React/Vite frontend for stock analysis, charts, news
- **Admin dashboard** (`/admin`) — React/Vite admin panel for user/system management
- **Python FastAPI backend** (`/api`) — Serves all API endpoints on port 8090

## Architecture

```
workspace/
├── artifacts/
│   ├── python-backend/       # FastAPI backend (Python 3.11)
│   │   ├── app/              # Application logic
│   │   │   ├── routes/       # API route handlers
│   │   │   ├── services/     # Business logic services
│   │   │   ├── middleware/   # Auth & other middleware
│   │   │   └── lib/          # Shared libraries
│   │   ├── pandas_ta/        # Local shim wrapping the `ta` library
│   │   ├── main.py           # FastAPI app entry point
│   │   └── run.py            # Startup script (downloads spaCy model, starts uvicorn)
│   ├── stock-market-app/     # User-facing React/Vite app (port 19845, path: /)
│   ├── admin-dashboard/      # Admin React/Vite app (port 22133, path: /admin)
│   └── api-server/           # Node.js routing shim (proxies /api → Python backend)
└── scripts/                  # GitHub push and utility scripts
```

## Workflows

| Workflow | Description |
|---|---|
| `Python Backend` | FastAPI server on port 8090 |
| `artifacts/stock-market-app: web` | Vite dev server on port 19845 |
| `artifacts/admin-dashboard: web` | Vite dev server on port 22133 |
| `artifacts/api-server: API Server` | Node.js proxy shim on port 8080 |

## Important Rules

- **NEVER install `pandas_ta` from PyPI** — there is a local shim at `artifacts/python-backend/pandas_ta/` that wraps the `ta` library
- **NEVER use `yf.download()`** — always use `yf.Ticker(symbol).history()`
- **Router is `wouter`** — never use react-router
- **NEVER touch `artifacts/api-server/` source code** — it is a routing shim only
- **No Clerk auth** — `ClerkAuthMiddleware` is actually custom HS256 JWT middleware
- The stock-market-app vite.config proxies `/api` → `http://localhost:8090`

## Environment Secrets

| Secret | Purpose |
|---|---|
| `ADMIN_USERNAME` | Admin dashboard login username |
| `ADMIN_PASSWORD` | Admin dashboard login password |
| `SESSION_SECRET` | JWT signing secret |

## API Authentication

- User endpoints: JWT tokens (HS256) via `Authorization: Bearer <token>`
- Admin endpoints: Separate admin JWT via `/api/admin/login`
- Default admin in dev: username from `ADMIN_USERNAME`, password from `ADMIN_PASSWORD`

## GitHub Push

See `GITHUB_PUSH.md` for instructions on pushing to GitHub.
Run: `pnpm --filter @workspace/scripts run push-github`

## Key Features

### Options Strategy Tester (`/options`)
- **7 core bugs fixed** (all with TDD): `use_weekly` toggle wired end-to-end, butterfly wing width fixed (otmMult ±1 = ±300pts), SEBI May-2024 expiry rule (only NIFTY/SENSEX have weekly options)
- **230 tests passing** across `tests/test_options.py` (sections 1–17)
- Live options chain from NSE, Black-Scholes pricing, Greeks, payoff curves, Monte Carlo VaR, 2-D scenario matrix
- Historical backtester for 17 strategies (Iron Condor, Butterfly, Straddle, etc.) with weekly/monthly toggle
- **AI-powered chatbot** — rule-based for all common topics (instant, zero cost), falls back to Gemma 4 / Qwen 3 / Llama 3.3 / gpt-4o-mini for unknown questions

### SEBI Compliance Audit (`scripts/sebi_audit.py`)
- Scrapes `sebi.gov.in/sebirss.xml` for latest 30 circulars
- Diffs circulars against 5 key codebase files using free AI (OpenRouter + OpenAI fallback)
- Writes agent-ready report to `artifacts/python-backend/reports/sebi_audit_YYYY-MM-DD.md`
- Run on-demand: `PYTHONPATH=. python3.11 scripts/sebi_audit.py` (from `artifacts/python-backend/`)
- API endpoint: `POST /api/options/sebi-audit` | `GET /api/options/sebi-report`

### AI Client (`app/services/ai_client.py`)
- Centralized multi-model client with full cascade: Gemma 4 31B → Qwen 3 80B → Llama 3.3 70B (OpenRouter free) → gpt-4o-mini (Replit credits)
- Functions: `ask()`, `ask_stream()`, `ask_json()`, `chat_with_history()`, `ask_ai_async()`
- OpenRouter free models: 429 rate-limit handled with retry/backoff
- gpt-5+ models: `temperature` param skipped (they only support default=1)

### Stock Analysis Page
- **Technicals view** (TradingView Indicators' Summary style, dark theme):
  - Timeframe selector: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 1d, 1w, 1mo
  - Summary SVG gauge (speedometer needle) with Buy/Sell/Neutral counts
  - **Oscillators** sub-gauge + expandable table: RSI(14), Stochastic %K, CCI(20), ADX(14), Awesome Oscillator, Momentum(10), MACD(12,26), StochRSI Fast, Williams %R(14), Bull Bear Power, Ultimate Oscillator(7,14,28)
  - **Moving Averages** sub-gauge + expandable table: EMA/SMA (10/20/30/50/100/200), Ichimoku Base Line, VWMA(20), HMA(9)
  - **Pivots** table with Classic / Fibonacci / Camarilla / Woodie / DM tabs (R3–S3)
- **Financials view** (TradingView-style, 6 tabs):
  - **Overview** — Valuation & Profitability metric cards + mini Revenue/Net Income charts
  - **Income Statement** — Revenue vs Profits bar chart + EBITDA bar chart + sortable table (Annual/Quarterly toggle)
  - **Statistics & Ratios** — Valuation / Profitability / Financial Health stat rows
  - **Dividends** — Annual dividend payout chart + recent dividend payment table
  - **Earnings** — Diluted EPS bar chart with positive/negative colour coding + growth % table
  - **Revenue** — Revenue + Gross Profit bars with YoY growth % line overlay + table

### Backend API — `/api/stocks/{symbol}/financials`
- Returns: `overview`, `incomeStatement` (annual+quarterly), `balanceSheet`, `cashFlow`, `dividends`, `eps`
- All monetary values in ₹ Crores; NaN values safely serialised as `null`
- 31 TDD tests in `tests/test_financials_endpoint.py`

## Tech Stack

| Layer | Technology |
|---|---|
| User Frontend | React 18, Vite, Tailwind CSS, wouter, TanStack Query, Recharts, ECharts, Lightweight Charts |
| Admin Frontend | React 18, Vite, Tailwind CSS, wouter, TanStack Query, Recharts |
| Backend | Python 3.11, FastAPI, uvicorn, yfinance, pandas, scipy, spaCy, ta |
| Auth | Custom HS256 JWT (PyJWT + bcrypt) |
| Routing shim | Node.js + Express (proxies /api path) |
