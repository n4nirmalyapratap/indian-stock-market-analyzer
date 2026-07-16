# Nifty Node — Indian Stock Market Analyzer

## Run & Operate

```bash
# Python Backend
cd artifacts/python-backend && PORT=8090 python3.11 run.py

# Frontend User App
cd artifacts/stock-market-app && PORT=5000 BASE_PATH=/ pnpm dev

# Admin Dashboard
cd artifacts/admin-dashboard && PORT=22133 BASE_PATH=/admin pnpm dev
```

**Required Environment Variables:**
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `SESSION_SECRET` (for JWT signing)
- `GITHUB_PAT` (for git push utility)
- `AI_INTEGRATIONS_OPENROUTER_BASE_URL` (set by OpenRouter integration)
- `AI_INTEGRATIONS_OPENROUTER_API_KEY` (set by OpenRouter integration)
- `FRED_API_KEY` (for Macro Pulse data, optional)
- `FEATURE_AI_ANALYST` (set to `on`/`1`/`true` to enable AI Analyst, defaults OFF)

## Stack

- **Frontend:** React 18, Vite, Tailwind CSS, `wouter` (router), `TanStack Query` (data fetching), Recharts, ECharts, Lightweight Charts
- **Backend:** Python 3.11, FastAPI
- **ORM:** _Populate as you build_
- **Validation:** Pydantic
- **Build Tool:** PNPM, Vite

## Where things live

- `/artifacts/python-backend/`: FastAPI backend source code
  - `/artifacts/python-backend/app/routes/`: All API route handlers
  - `/artifacts/python-backend/app/services/`: Core business logic services
  - `/artifacts/python-backend/requirements.txt`: Python dependencies (source-of-truth)
  - `/artifacts/python-backend/market_cache/fii_dii_cache.db`: FII/DII data cache (source-of-truth)
  - `/artifacts/python-backend/market_cache/ai_analyst.db`: AI Analyst report cache (source-of-truth)
  - `/artifacts/python-backend/market_cache/portfolio.db`: Portfolio data store (source-of-truth)
- `/artifacts/stock-market-app/`: User-facing React/Vite frontend
- `/artifacts/admin-dashboard/`: Admin React/Vite dashboard
- `/artifacts/stock-market-app/vite.config.ts`: Vite proxy configuration
- `/artifacts/python-backend/pandas_ta/`: Local shim for `ta` library (NOT PyPI `pandas_ta`)

## Architecture decisions

- **AI Model Integration:** Utilizes OpenRouter for AI models (`google/gemma-4-31b-it`, `qwen/qwen3-30b-a3b`, `meta-llama/llama-3.3-70b-instruct`) via the `openai` Python SDK, not direct OpenAI service.
- **Custom Authentication:** Implements a custom HS256 JWT middleware instead of Clerk for user and admin authentication.
- **Backend Data Sources:** Prioritizes `yfinance`, `api.bseindia.com`, `portal.amfiindia.com` but acknowledges and handles blocking from `www.nseindia.com` and `www.moneycontrol.com` by providing honest `unavailable` states.
- **In-process SEBI Audit:** The `sebi_audit.py` runs in-process via `run_audit_async()` for compliance checks, never as a subprocess.
- **Deterministic AI Council:** The Investor Council provides deterministic checklist scores, with AI-generated theses that gracefully degrade when the LLM is unavailable. External context (news, sentiment, FII/DII flows) only enriches the LLM prompt, not the deterministic scores.

## Product

- **User App:** Stock analysis, interactive charts, options chain & strategies, news, investor council, macro insights, portfolio manager.
- **Admin Dashboard:** User management, system monitoring, SEBI audit report generation, bug tracking.
- **AI Analyst:** Multi-agent equity research for `/ai-analyst/:ticker` with compliance checks, per-user quota, and report caching.
- **Investor Council:** Evaluates stocks against 8 famous investor personas, providing a council verdict and AI-generated theses.
- **Macro Pulse:** Displays India's key economic indicators (Repo, CPI, IIP, USD/INR, 10Y, Brent) with AI commentary and source transparency.
- **Portfolio Manager:** Tracks holdings, calculates risk metrics, suggests rebalancing, and supports CSV import for transactions.
- **Insights Module:** Comprehensive market insights including Heatmap, FII/DII flows, Company Filings, MF Holdings, IPO Center.
- **Options Strategy Tester:** Live NSE options chain, Black-Scholes, Greeks, payoff curves, Monte Carlo VaR for 17 strategies.
- **Market Sentiment Engine:** Aggregates sentiment from various sources to recommend trading strategies.

## User preferences

- **NEVER install `pandas_ta` from PyPI** — use the local shim at `artifacts/python-backend/pandas_ta/`
- **NEVER use `yf.download()`** — always use `yf.Ticker(symbol).history()`
- **Router is `wouter`** — never use react-router in any frontend
- **NEVER touch `artifacts/api-server/` source** — it is a routing shim only
- **No Clerk** — `ClerkAuthMiddleware` is actually a custom HS256 JWT middleware
- **SEBI lot sizes (Nov 2024)**: NIFTY=75, BANKNIFTY=30, FINNIFTY=65, MIDCPNIFTY=120, SENSEX=10, BANKEX=15
- **Iron Condor rule**: ONLY recommend when VIX ≥ 22 AND composite sentiment is neutral (−30 to +30)
- **`hydra_db_service.get_history(ticker, days)`** is SYNC (not async), takes `days` not `limit`
- **`sebi_audit.py`** runs IN-PROCESS via `run_audit_async()` — NEVER call it as a subprocess
- **NEVER add `"pandas_ta"` to SKIP_DIRS** in `push-github.ts`
- Every bug must have a ticket before code changes.
- **NEVER make explicit git commits** — the user manages all commits themselves.
- **Council consensus screener cache** (`market_cache/agents_screener.db`) refreshes on the **next request after 16:00 IST** on any trading day (NSE close 15:30 + 30 min EOD-data grace); weekends roll back to Friday's close — never a flat 24-hour TTL.

## Gotchas

- **`.replit` port mapping:** Only one `localPort` may map to `externalPort = 80`. React frontend (port 5000) must map to `externalPort = 80`. Python backend (port 8090) should map to `externalPort = 8080`.
- **Vite proxy target:** `artifacts/stock-market-app/vite.config.ts` must default `apiProxyTarget` to `http://localhost:8090`.
- **Python packages:** Install via `installLanguagePackages` or `pip install -r requirements.txt`. Do NOT install `pandas_ta` from PyPI; use the local shim. `spacy` model `en_core_web_sm` must be downloaded.
- **Yahoo fundamental units:** `returnOnEquity`/`profitMargins`/`operatingMargins`/`grossMargins` are fractions (e.g., 0.18 for 18%); `debtToEquity` is percent (e.g., 50.0 for D/E 0.5). Persona thresholds reflect this.
- **Data lag for Macro Pulse:** Be aware of potential data lag for Repo, IIP, and WPI as surfaced by the `asOf` timestamp on each tile.
- **Blocked Data Sources:** `www.nseindia.com`, `www.moneycontrol.com`, `www.chittorgarh.com` are blocked from this Replit container. UI components dependent on these sources will show an `unavailable` state.
- **Testing:** `DISABLE_AUTH=1` and `PYTEST_CURRENT_TEST` are required for auth bypass in backend tests.

## Pointers

- **Replit Documentation:**
  - [Replit AI Integrations](https://docs.replit.com/ai/integrations)
  - [Replit Secrets](https://docs.replit.com/programming-environment/secrets)
- **Framework Documentation:**
  - [FastAPI](https://fastapi.tiangolo.com/)
  - [React](https://react.dev/)
  - [Vite](https://vitejs.dev/)
  - [Tailwind CSS](https://tailwindcss.com/)
  - [wouter](https://github.com/molefrog/wouter)
  - [TanStack Query](https://tanstack.com/query/latest)
- **API Documentation:**
  - [yfinance](https://pypi.org/project/yfinance/)
  - [BSE India API](https://api.bseindia.com/)
  - [AMFI India Portal](https://portal.amfiindia.com/)
  - [FRED API](https://fred.stlouisfed.org/docs/api/api_key.html)
  - [World Bank API](https://api.worldbank.org/v2)
  - [OpenRouter API](https://openrouter.ai/docs)
- **SEBI Regulations:**
  - [SEBI Investor Awareness](https://investor.sebi.gov.in/)