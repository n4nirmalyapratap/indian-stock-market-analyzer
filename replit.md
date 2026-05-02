# Nifty Node — Indian Stock Market Analyzer

### Overview
Nifty Node is a full-stack platform designed for comprehensive Indian stock market analysis. It provides a user-facing application for stock analysis, charting, options strategies, and news, alongside an admin dashboard for managing users, system configurations, and compliance. The project aims to deliver advanced financial insights and tools, leveraging AI for sentiment analysis and compliance auditing.

### User Preferences
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

### System Architecture
The project is structured with a clear separation of concerns:
- **Frontend (User App & Admin Dashboard):** Both are built with React 18, Vite, and Tailwind CSS for a modern, responsive UI. `wouter` is used for routing, and `TanStack Query` for data fetching. Charting libraries include Recharts, ECharts, and Lightweight Charts. The UI adheres to consistent design tokens for theming.
- **Backend:** A Python 3.11 FastAPI application handles all API endpoints, business logic, and integrations. Key services include market data processing, AI-driven sentiment analysis, and SEBI compliance auditing.
- **Insights Module:** Replicates a detailed "Insights" experience with 12 sub-tabs (Heatmap, FiiDii, CompanyFilings, MfHoldings, BulkBlockDeals, Signals, SlbmRental, MtfInsights, FoBan, TopDeliveries, MarketValuation, Ipo), powered by `app/routes/insights.py`.
- **API Authentication:** Custom HS256 JWT tokens are used for user endpoints, and a separate admin JWT for the admin dashboard, passed via `X-Admin-Token`.
- **Market Sentiment Engine:** Calculates a composite sentiment score from News NLP, Price Action, India VIX, and PCR Proxy, with recommendations for strategies like Iron Condor based on sentiment and VIX levels.
- **Options Strategy Tester:** Features live NSE options chain, Black-Scholes model, Greeks, payoff curves, and Monte Carlo VaR, supporting 17 strategies. An AI chatbot provides strategy assistance.
- **Admin Dashboard:** Manages background jobs, SEBI audit reports, bug tracking, user management, and system logs.
- **SEBI Compliance Audit:** Automatically loads historical and live SEBI circulars, processes them with AI models, and generates Markdown reports. This runs in-process and never as a subprocess.
- **Technical Analysis:** TradingView-style charts with various indicators across 10 timeframes.
- **Financials:** Detailed financial data presented in ₹ Crores across multiple tabs.
- **Caching:** In-process TTL cache for market data (5 min for yfinance, 6 hours for AMFI/BSE EOD).
- **Error Handling:** Heavy yfinance operations are parallelized, with silent skipping of individual failures to maintain response integrity.

### External Dependencies
- **Data Sources:**
    - `yfinance`: For fetching stock data (used with `yf.Ticker(symbol).history()`).
    - `api.bseindia.com`: For company filings and corporate disclosures.
    - `portal.amfiindia.com`: For mutual fund holdings and NAV data.
- **AI Models (via OpenRouter integration):**
    - `google/gemma-4-31b-it:free` (Primary)
    - `qwen/qwen3-30b-a3b:free` (Fallback)
    - `meta-llama/llama-3.3-70b-instruct:free` (Last resort)
    - **Note:** Utilizes the `openai` Python SDK to interact with OpenRouter's API; no direct OpenAI service usage.
- **Python Libraries:** `fastapi`, `uvicorn`, `httpx`, `pandas`, `numpy`, `scipy`, `spacy` (with `en_core_web_sm` model), `ta` (wrapped by local `pandas_ta` shim), `feedparser`, `PyJWT`, `cryptography`, `bcrypt`, `lxml`, `python-multipart`, `openpyxl`.
- **Node.js/Frontend Libraries:** `pnpm`, `React`, `Vite`, `Tailwind CSS`, `wouter`, `TanStack Query`, `Recharts`, `ECharts`, `Lightweight Charts`.
- **GitHub:** `GITHUB_PAT` for pushing code.