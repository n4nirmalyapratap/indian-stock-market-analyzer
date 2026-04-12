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

### Centralized Market Sentiment Engine (`/sentiment`)
**Single source of truth for all sentiment-related decisions across the app.**

- **Route:** `GET /api/sentiment/market` — full composite snapshot (15-min cache)
- **Route:** `GET /api/sentiment/sectors` — per-sector heatmap data
- **Route:** `GET /api/sentiment/refresh` — force-refresh both caches
- **Service:** `app/services/market_sentiment_engine.py`

**Composite score (-100 to +100) from 4 weighted signals:**
| Signal | Weight | Source |
|---|---|---|
| News NLP | 35% | `news_service.get_summary()` bullish/bearish article ratio |
| Price Action | 35% | Nifty50 history → `hydra_sentiment_service.price_action_sentiment()` |
| India VIX | 20% | Yahoo Finance `^NSEVIXY` — inverted (high VIX = bearish) |
| PCR Proxy | 10% | Synthetic PCR derived from VIX level + 5-day VIX trend |

**Labels:** Extremely Bearish / Bearish / Neutral / Bullish / Extremely Bullish

**Contrarian signals (from research paper):**
- VIX > 25 AND score < -40 → Peak Fear (potential market bottom)
- VIX < 12 AND score > 60 → Peak Complacency (potential market top)
- PCR proxy > 1.4 → Excessive Bearishness (contrarian buy watch)
- PCR proxy < 0.5 → Excessive Bullishness (contrarian sell watch)

**Frontend page (`SentimentDashboard.tsx`):**
- SVG speedometer gauge for composite score
- VIX level bar with gradient zones + interpretation card
- PCR proxy bar with zone markers + interpretation card
- News breakdown (bullish/bearish/neutral bars)
- Nifty50 Price Action KPIs (5d momentum, 20d momentum, RSI14)
- Sector heatmap (12 sectors, color-coded green→red)
- Strategy recommendations table (from research paper mapping)
- Contrarian signal alerts

**Integration points:**
- `OptionsStrategyTester` — Smart Strategy Builder uses this as supplementary context
- `hydra_forecast_service.py` — sentiment_bias already used in price forecasting
- `news_service.py` — `get_summary()` is the news signal source

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

## Bug Tracking Process (MANDATORY — Applies to All Agents)

**Every bug must go through the Bug Tracker before it is resolved. No exceptions.**

### Agent Workflow for Fixing Bugs

#### Scenario A — User reports a bug without mentioning a ticket
1. **Create the ticket first** (before touching any code):
   ```bash
   PYTHONPATH=artifacts/python-backend python3.11 artifacts/python-backend/scripts/add_bug.py \
     --title "Short bug title" --description "What's wrong and how to reproduce" \
     --severity medium --component "Options Strategy Tester" --reported_by "agent"
   ```
   Save the returned ID (e.g. `#a1b2c3d4`).

2. **Mark in-progress** when you start the fix:
   ```bash
   PYTHONPATH=artifacts/python-backend python3.11 -c "
   from scripts.add_bug import update_bug_status
   update_bug_status('a1b2c3d4', 'in-progress', 'Starting fix — root cause: ...')
   "
   ```

3. **Apply the fix, run tests, push to GitHub.**

4. **Mark fixed** after confirmed working:
   ```bash
   PYTHONPATH=artifacts/python-backend python3.11 -c "
   from scripts.add_bug import update_bug_status
   update_bug_status('a1b2c3d4', 'fixed', 'Fixed in commit abc1234: explanation')
   "
   ```

#### Scenario B — User mentions a specific bug ticket ID
- Read the bug from the tracker to understand the description and any AI analysis notes.
- Use the AI analysis (if present in the description under `[AI Analysis]`) as your starting point.
- Follow steps 2–4 from Scenario A using that ticket ID.

### Hard Rules
- NEVER fix a bug without first creating or referencing a ticket. This is non-negotiable.
- A bug is NOT `fixed` until there is actual code change + passing tests + git push.
- Only the **human user** (or someone they delegate) changes a bug to `closed`. Agents mark `fixed`, humans close.
- Agents must never skip the tracker step, even for tiny one-line fixes.

### AI Bug Analyser (read-only background job)
The analyser runs every 10 minutes automatically (background task in `main.py`).

**What it does:**
- Reads all open/in-progress bugs that don't have a recent analysis
- Finds relevant source code for each bug based on component + keywords
- Uses AI to diagnose the root cause and write numbered fix steps
- Stores the analysis in the bug's description field under `[AI Analysis]`

**What it does NOT do:**
- Apply any code changes
- Run tests
- Push to GitHub
- Change bug status
- Auto-close bugs

The human (or an AI agent delegated by the human) reads the analysis and decides how to act on it.

**Files:**
- `artifacts/python-backend/scripts/bug_fixer.py` — analyser script
- `artifacts/python-backend/scripts/add_bug.py` — CLI helper for creating/updating bugs

**Admin UI:** Bug Tracker page → "Analyse All Bugs" button → AI analysis appears in each bug card's expanded view (purple `AI Analysis` panel)

**Endpoints:**
- `POST /admin/bugs/run-fixer` — trigger analysis on demand (optionally `?bug_id=<id>` for one bug)
- `GET /admin/bugs/fixer-status` — current analyser status + last run results

## Tech Stack

| Layer | Technology |
|---|---|
| User Frontend | React 18, Vite, Tailwind CSS, wouter, TanStack Query, Recharts, ECharts, Lightweight Charts |
| Admin Frontend | React 18, Vite, Tailwind CSS, wouter, TanStack Query, Recharts |
| Backend | Python 3.11, FastAPI, uvicorn, yfinance, pandas, scipy, spaCy, ta |
| Auth | Custom HS256 JWT (PyJWT + bcrypt) |
| Routing shim | Node.js + Express (proxies /api path) |
