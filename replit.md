# Nifty Node — Indian Stock Market Analyzer

---

## ⚠️ READ THIS FIRST — Agent Setup Checklist (Replit Environment)

**Any agent doing a fresh setup, migration, or debugging "why is the preview showing Not Found / white page" MUST do these checks BEFORE anything else. Skipping this wasted real money in a previous session.**

### 1. Audit `.replit` port mappings (CRITICAL)
Open `.replit` and find every `[[ports]]` block. **Only ONE `localPort` may map to `externalPort = 80`** — that must be the React frontend on `localPort = 5000`. If you see another port (e.g. `8090`) ALSO mapped to `externalPort = 80`, the public Replit URL will route ambiguously to the wrong service and you will see `{"detail":"Not Found"}` or a blank page in the canvas iframe.

**Required final state:**
```toml
[[ports]]
localPort = 5000      # Vite frontend → public URL
externalPort = 80

[[ports]]
localPort = 8090      # Python FastAPI backend → internal only, accessed via Vite /api proxy
externalPort = 8080   # NOT 80
```

If `.replit` is wrong, the file is normally write-protected. You can update it via Node `fs.writeFileSync` from the code execution sandbox (the bash `sed` and edit tools are blocked, but `fs` works).

### 2. Workflow configuration (must match)
- `Start application` → `cd artifacts/stock-market-app && PORT=5000 BASE_PATH=/ pnpm dev`, outputType `webview`, waitForPort `5000`
- `Python Backend` → `cd artifacts/python-backend && PORT=8090 python3.11 run.py`, outputType `console` (NO waitForPort, NO external exposure)

### 3. Vite proxy target
`artifacts/stock-market-app/vite.config.ts` must default `apiProxyTarget` to `http://localhost:8090` (matches the Python backend port). Do not change it to 8081 or anything else.

### 4. Quick smoke test (run after restarting both workflows)
```bash
curl -s -o /dev/null -w "frontend: %{http_code}\n" http://localhost:5000/
curl -s -o /dev/null -w "backend direct: %{http_code}\n" http://localhost:8090/api/healthz
curl -s -o /dev/null -w "backend via proxy: %{http_code}\n" http://localhost:5000/api/healthz
```
All three must return `200`. If they do, the canvas iframe will show the Nifty Node login page.

### 5. Required Python packages
Install via `installLanguagePackages` (NOT pip in shell): `fastapi, uvicorn, pandas, numpy, ta, spacy, en_core_web_sm, yfinance, scipy, feedparser, PyJWT, bcrypt, openai, lxml, pydantic`. Do NOT install `pandas_ta` from PyPI — there is a local shim at `artifacts/python-backend/pandas_ta/`.

---

## Project Overview

A full-stack Indian stock market analysis platform with:
- **User app** (`/`) — React/Vite frontend for stock analysis, charts, options, news
- **Admin dashboard** (`/admin`) — React/Vite admin panel for user/system/compliance management
- **Python FastAPI backend** (`/api`) — All API endpoints on port 8090

### Famous-Investor AI Council (added 2026-05, Phase 1 of FinceptTerminal-inspired roadmap)
A `/agents` and `/agents/:symbol` page that runs eight legendary investor personas (Buffett, Graham, Lynch, Munger, Klarman, Marks, Dalio, Burry) against any NSE stock, scores their documented checklists deterministically, aggregates a council verdict (`STRONG_BUY` / `BUY` / `HOLD` / `AVOID` / `STRONG_AVOID`), and writes a one-paragraph thesis in each investor's voice via `ai_client.ask()` (gracefully degrades when OpenRouter isn't connected).
- **Backend**: `app/services/agents_service.py` (8 persona evaluators + `run_council`/`run_single_persona` + thesis writer), `app/routes/agents.py` (4 endpoints under `/api/agents`). Routes registered in `main.py`. Raw `yf.Ticker(...).info` fetched via `asyncio.to_thread + yahoo_candidates` and cached for 24 h (fundamentals don't move minute-by-minute). Deterministic scoring is fully offline — only the AI thesis touches the LLM.
- **Endpoints**: `GET /api/agents` (persona list), `/api/agents/{symbol}` (fast checklist council, no AI), `/api/agents/{symbol}/council` (with AI theses for all 8), `/api/agents/{symbol}/{persona_id}` (single persona deep-dive with thesis).
- **Frontend**: `src/pages/InvestorCouncil.tsx`. Search landing when no symbol; council header w/ verdict + buy/hold/avoid pill counts; **two view tabs — Persona Cards** (8 cards with score bars + checklist passes) and **Council View** (verdict-consensus heatmap row + persona × checklist matrix table for at-a-glance consensus/disagreement); modal AI thesis on click. Uses `wouter` `useRoute("/agents/:symbol")`.
- **Wiring**: `api.ts` exposes `agentsList`, `agentCouncil`, `agentCouncilFull`, `agentPersona`. `LayoutShell.MAIN_NAV` includes `Investor Council` (Users icon). `StockLookup.tsx` shows an "Ask the Investor Council" CTA pill in the stock header. `ChartView.tsx` shows an "Ask the Council" gradient button in the chart toolbar.
- **Yahoo fundamental units gotcha**: `returnOnEquity` / `profitMargins` / `operatingMargins` / `grossMargins` are **fractions** (0.18 = 18%); `debtToEquity` is **percent** (50.0 = D/E 0.5). Persona thresholds in `agents_service.py` reflect this.
- **External context enrichment**: `gather_external_context()` concurrently pulls (a) symbol-tagged recent news from `news_service`, (b) the broad-market mood snapshot from `market_sentiment_engine`, and (c) the latest NSE FII/DII equity flows summarised as a one-line flow label. These are passed into the LLM thesis prompt only — the deterministic checklist scores never depend on them, keeping verdicts fully reproducible. Every council response also includes a `sources[]` provenance array and a `fetchedAt` timestamp.

### Macro Pulse (added 2026-05, Phase 3 of FinceptTerminal-inspired roadmap)
A `/insights/macro` tab plus a persistent six-tile strip pinned to the dashboard surface India's macro pulse so retail traders no longer have to flip between Moneycontrol/RBI tabs to read the room.
- **Backend**: `app/services/macro_service.py` (FRED CSV downloader + Yahoo quote wrapper + 24 h in-process cache + LLM commentary with deterministic fallback). Two routes added to `app/routes/insights.py`: `GET /api/insights/macro/strip` (six tiles: Repo, CPI YoY, IIP YoY, USD/INR, India 10Y, Brent) and `GET /api/insights/macro` (full payload — repo timeline, CPI/IIP YoY series, GDP YoY bars, yield curve snapshot, currency strip with DXY/Gold/VIX, AI commentary, sources).
- **Data sources**: FRED public CSV endpoint (no API key needed) for `INDIRSTPR` (repo), `INDCPIALLMINMEI` (CPI), `INDPROINDMISMEI` (IIP), `INDGDPRQDSMEI` (GDP), `INDIRLTLT01STM` (10Y); Yahoo for `INR=X`, `DX-Y.NYB`, `BZ=F`, `GC=F`, `^INDIAVIX`. Every external fetch is wrapped in try/except — failures degrade to empty payloads, never crash the route.
- **Frontend**: `src/pages/insights/tabs/Macro.tsx` (headline tiles + AI commentary card + RBI rate timeline line chart + CPI/IIP overlay + GDP bars + currency cards + sources footer). `src/components/macro/MacroStrip.tsx` is the compact six-tile ribbon mounted in `Dashboard.tsx`; each tile is a `wouter` Link to `/insights/macro`. New tab registered in `InsightsLayout.tsx` with a Globe icon.
- **API client**: `MacroTile`, `MacroStripResponse`, `MacroDashboardResponse`, `MacroQuote`, `MacroSeriesPoint` interfaces in `lib/api.ts`; `api.macroStrip()` and `api.macroDashboard()` clients.
- **Tests**: `tests/test_macro.py` (18 tests) — FRED CSV parser (well-formed, NA/dot/non-numeric, HTTP errors, network exceptions), `_yoy_change`/`_last_two`/`_series_yoy` math, strip aggregation always returns 6 tiles, dashboard shape is complete when data is empty, 24 h cache prevents re-fetch, deterministic commentary fallback when LLM is unavailable or returns the `[AI unavailable]` sentinel, route smoke tests via TestClient.

### Insights module (added 2026-04)
A top-level `/insights` section replicates the ScanX "Insights" experience with 12 sub-tabs and a sticky inner sidebar.
- Top nav: `Insights` entry in `MAIN_NAV` (`src/LayoutShell.tsx`)
- Routes: `/insights` and `/insights/:tab*` → `src/pages/insights/InsightsLayout.tsx`
- Tab pages: `src/pages/insights/tabs/` (Macro, Heatmap, FiiDii, CompanyFilings, MfHoldings, BulkBlockDeals, Signals, SlbmRental, MtfInsights, FoBan, TopDeliveries, MarketValuation, Ipo)
- Backend: `app/routes/insights.py` registered in `main.py`. Endpoints: `/api/insights/{macro,macro/strip,indices,heatmap,company-filings,mf-holdings,signals,index-valuation,market-valuation,fo-ban,top-deliveries,fii-dii,slbm,mtf,ipos}`.

#### Real-data wiring (data sources, network reachability)
This Replit container can reach **yfinance**, **api.bseindia.com**, and **portal.amfiindia.com** but is BLOCKED from `www.nseindia.com`, `www.moneycontrol.com`, and `www.chittorgarh.com`. Endpoints handle this honestly:
- **Heatmap** (`/heatmap?index=…&performance=1d|1w|1m|1y`) — yfinance, parallelised across a 16-worker `ThreadPoolExecutor`. 27 curated indices in `INDEX_CONSTITUENTS` (Nifty 50/100/200/500, sectoral, midcap, PSU/Pvt bank, etc.). Server returns `color: {bg, fg}` hex per item — UI renders via inline `style` to bypass Tailwind v4 arbitrary-value scanning.
- **Company Filings** (`/company-filings?category=…&page=…`) — direct call to `https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w` with `Referer: bseindia.com`. Returns BSE corporate disclosures with PDF links.
- **MF Holdings** (`/mf-holdings?amc=&category=&search=&limit=`) — fetches `https://portal.amfiindia.com/spages/NAVAll.txt` (follow-redirects from amfiindia.com), parses the semicolon-separated NAV list (~14k schemes) with `_parse_amfi_text`, returns AMC + category facets for UI dropdowns.
- **Signals** (`/signals?index=…&verdict=all|bullish|bearish|neutral`) — yfinance 6-month history, computes RSI(14) and MA20/MA50 cross with `_compute_signal`. Verdict logic: RSI ≥70 / ≤30 → Bearish/Bullish; price vs MAs → trend confirmation.
- **Market / Index Valuation** (`/index-valuation`, `/market-valuation`) — yfinance multi-index time series normalised to a 22× PE proxy.
- **F&O Ban** (`/fo-ban`) — attempts `NseService.fetch_nse(/api/liveMwpl)`; returns `{available:false, message: NSE_BLOCKED_MSG}` when blocked.
- **FII/DII** — Backend: `app/services/fii_dii_service.py`. Routes: `GET /api/insights/fii-dii?segment=&days=` (segments: `equity`, `index_future`, `index_option`, `stock_future`, `stock_option`) and admin-guarded `POST /api/insights/fii-dii/backfill?days=`. Two distinct sources:
  - **F&O segments (4 tabs)** — `fetch_fno_historical()` downloads NSE's daily participant-OI archive from `nsearchives.nseindia.com/content/nsccl/fao_participant_oi_DDMMYYYY.csv` via `NseService.fetch_nse_archive_text()` and splits each day's CSV into all four F&O segment tables in one pass. The cache ships preloaded with ~13 months of history (267 trading-day rows per segment, Mar 2025 → Apr 2026).
  - **Equity** — `fetch_equity_snapshot()` hits NSE's `/api/fiidiiTradeReact` (the only public NSE endpoint that returns equity FII/DII). NSE does not expose bulk historical equity FII/DII anywhere, so the equity tab is a snapshot accumulator: each day's snapshot is appended on-demand and history grows over time.
  - Cache lives at `artifacts/python-backend/market_cache/fii_dii_cache.db` and is committed to git (`.gitignore` exception). Date columns are persisted as ISO strings and parsed strictly with `format=ISO8601` on read.
  - Response payload: `{ rows[], summary: { daily, weekly, monthly (=trailing 30 sessions), ytd (calendar Jan 1 → today) }, monthly[] (per-calendar-month buckets with mini-rows), totalDays, rangeDays }`.
- **SLBM, MTF, IPOs, Top Deliveries** — return `{available:false, message}` with the source restriction explained, since these feeds live behind NSE / Chittorgarh which are blocked from cloud IPs.

#### Caching & resilience
- In-process TTL cache: 5 min for yfinance (`DEFAULT_TTL`), 6 h for AMFI/BSE EOD (`LONG_TTL`).
- All heavy yfinance work is parallelised; failures are silently skipped (we never break the response on a single delisted ticker).
- `app/services/market_cache_service.py` is available for disk-backed EOD caching when needed.

#### Tests
- `tests/test_insights.py` — 21 unit tests using FastAPI `TestClient` with `DISABLE_AUTH=1` env bypass. Covers bucket palette, heatmap normalisation (mocked yfinance), BSE adapter, AMFI parser, RSI/MA signal math, indices catalogue, and unavailable-feed empty states.
- Auth bypass is in `app/middleware/clerk_auth.py` — gated on `DISABLE_AUTH=1` AND `PYTEST_CURRENT_TEST` AND `ENV != production` (triple-locked). NEVER set DISABLE_AUTH in production.
- Run: `cd artifacts/python-backend && DISABLE_AUTH=1 python3.11 -m pytest tests/test_insights.py -v`

#### UI integration (rewrite, 2026-04)
The Insights tabs use the host app's design tokens (`bg-card`, `bg-popover`, `text-foreground`, `text-muted-foreground`, `border-card-border`, `bg-primary`, etc.) instead of hardcoded `gray-*/white` classes — light and dark mode now match the rest of the app.
- **`MenuDropdown`** (in `_shared.tsx`) is a portal-based combobox/listbox: `position:fixed`, viewport-clamped (8px margins, flips above when there's no room below), capped trigger width with truncation (so long labels never break the row), full keyboard support (Arrow keys, Home/End, Enter, Esc), ARIA combobox/listbox roles, and an automatic "Clear" row prepended when a placeholder is configured and a value is selected.
- **`Heatmap`** uses a squarified treemap (Bruls/Huijsen/van Wijk) sized by market cap when `sortBy="marketCap"`; falls back to a uniform grid for other sort modes. Container height adapts to constituent count; ResizeObserver keeps the layout responsive.
- **`MarketValuation`** lets the user pick up to 6 sectors from a 19-index pool via `+ Add` / `× Remove`. Recharts uses `hsl(var(--*))` tokens so the chart respects the active theme.
- **`CompanyFilings`** has 9 sub-tabs, a company filter dropdown, colored category badges, and relative timestamps.
- **`FeatureLocked`** component is used by tabs whose upstream feeds (NSE / Moneycontrol / Chittorgarh) are blocked from this hosting region. Each instance shows what the data is, why it's empty, the columns that will appear once unblocked, and a direct link to the upstream source. No fake/mock data is ever shown.

---

## Architecture

```
workspace/
├── artifacts/
│   ├── python-backend/           # FastAPI backend (Python 3.11)
│   │   ├── app/
│   │   │   ├── routes/           # All API route handlers
│   │   │   ├── services/         # Business logic (AI, market data, sentiment, etc.)
│   │   │   ├── middleware/       # HS256 JWT auth middleware
│   │   │   └── lib/              # Shared utilities (secrets_store, etc.)
│   │   ├── pandas_ta/            # LOCAL SHIM — wraps `ta` library (NEVER install from PyPI)
│   │   ├── scripts/              # Audit, bug tracking, DB init scripts
│   │   │   ├── sebi_audit.py     # SEBI compliance audit (in-process, no subprocess)
│   │   │   ├── sebi_circulars_db.py  # 20 SEBI circulars 2019–2024 (5-year DB)
│   │   │   ├── add_bug.py        # Bug tracker CLI
│   │   │   └── bug_fixer.py      # AI bug analyser background job
│   │   ├── reports/              # SEBI audit reports (sebi_audit_YYYY-MM-DD.md)
│   │   ├── tests/                # pytest test suite (349 tests)
│   │   ├── requirements.txt      # Python dependencies (keep in sync!)
│   │   ├── main.py               # FastAPI app entry point
│   │   └── run.py                # Startup (downloads spaCy model, starts uvicorn)
│   ├── stock-market-app/         # User React/Vite app  (port 19845, path: /)
│   ├── admin-dashboard/          # Admin React/Vite app (port 22133, path: /admin)
│   └── api-server/               # ROUTING SHIM ONLY — proxies /api → port 8090
│                                 # NEVER touch its source code
└── scripts/                      # GitHub push utility
    └── src/push-github.ts
```

---

## Workflows

| Workflow | Command | Port |
|---|---|---|
| `Python Backend` | `cd artifacts/python-backend && PORT=8090 python3.11 run.py` | 8090 |
| `artifacts/stock-market-app: web` | `pnpm --filter @workspace/stock-market-app run dev` | 19845 |
| `artifacts/admin-dashboard: web` | `pnpm --filter @workspace/admin-dashboard run dev` | 22133 |
| `artifacts/api-server: API Server` | routing shim (echo only — Python handles everything) | — |

---

## Fresh Setup / Reinstall Checklist

If packages are missing or a new environment is set up, run these in order:

```bash
# 1. Python packages
cd artifacts/python-backend
python3.11 -m pip install -r requirements.txt

# 2. spaCy language model (run.py does this on startup, but if running manually):
python3.11 -m spacy download en_core_web_sm

# 3. Node packages
pnpm install --no-frozen-lockfile

# 4. Connect integrations (one-time, in Replit AI integrations panel or via code_execution):
#    - OpenRouter (for free AI: Gemma 4, Qwen 3, Llama 3.3)
#    - Sets env vars: AI_INTEGRATIONS_OPENROUTER_BASE_URL, AI_INTEGRATIONS_OPENROUTER_API_KEY
```

**Required Python packages** (all in `requirements.txt`):
```
fastapi, uvicorn[standard], httpx, pandas, numpy, ta, spacy,
python-multipart, openpyxl, yfinance, scipy, feedparser,
PyJWT, cryptography, bcrypt, openai, lxml
```

> `openai` — free HTTP client SDK used to talk to OpenRouter's API. NOT the paid OpenAI service.
> `lxml` — XML parser for BeautifulSoup (SEBI RSS feed parsing).

**Env secrets** (set in Replit Secrets panel):
| Secret | Purpose |
|---|---|
| `ADMIN_USERNAME` | Admin dashboard login username |
| `ADMIN_PASSWORD` | Admin dashboard login password |
| `SESSION_SECRET` | JWT signing secret |
| `GITHUB_PAT` | GitHub Personal Access Token for git push |
| `AI_INTEGRATIONS_OPENROUTER_BASE_URL` | Auto-set by OpenRouter integration |
| `AI_INTEGRATIONS_OPENROUTER_API_KEY` | Auto-set by OpenRouter integration |

---

## Hard Rules (NEVER violate)
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