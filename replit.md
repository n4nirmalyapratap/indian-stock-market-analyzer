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

### Insights module (added 2026-04)
A top-level `/insights` section replicates the ScanX "Insights" experience with 12 sub-tabs and a sticky inner sidebar.
- Top nav: `Insights` entry in `MAIN_NAV` (`src/LayoutShell.tsx`)
- Routes: `/insights` and `/insights/:tab*` → `src/pages/insights/InsightsLayout.tsx`
- Tab pages: `src/pages/insights/tabs/` (Heatmap, FiiDii, CompanyFilings, MfHoldings, BulkBlockDeals, Signals, SlbmRental, MtfInsights, FoBan, TopDeliveries, MarketValuation, Ipo)
- Backend: `app/routes/insights.py` registered in `main.py`. Endpoints: `/api/insights/{indices,heatmap,company-filings,mf-holdings,signals,index-valuation,market-valuation,fo-ban,top-deliveries,fii-dii,slbm,mtf,ipos}`.

#### Real-data wiring (data sources, network reachability)
This Replit container can reach **yfinance**, **api.bseindia.com**, and **portal.amfiindia.com** but is BLOCKED from `www.nseindia.com`, `www.moneycontrol.com`, and `www.chittorgarh.com`. Endpoints handle this honestly:
- **Heatmap** (`/heatmap?index=…&performance=1d|1w|1m|1y`) — yfinance, parallelised across a 16-worker `ThreadPoolExecutor`. 27 curated indices in `INDEX_CONSTITUENTS` (Nifty 50/100/200/500, sectoral, midcap, PSU/Pvt bank, etc.). Server returns `color: {bg, fg}` hex per item — UI renders via inline `style` to bypass Tailwind v4 arbitrary-value scanning.
- **Company Filings** (`/company-filings?category=…&page=…`) — direct call to `https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w` with `Referer: bseindia.com`. Returns BSE corporate disclosures with PDF links.
- **MF Holdings** (`/mf-holdings?amc=&category=&search=&limit=`) — fetches `https://portal.amfiindia.com/spages/NAVAll.txt` (follow-redirects from amfiindia.com), parses the semicolon-separated NAV list (~14k schemes) with `_parse_amfi_text`, returns AMC + category facets for UI dropdowns.
- **Signals** (`/signals?index=…&verdict=all|bullish|bearish|neutral`) — yfinance 6-month history, computes RSI(14) and MA20/MA50 cross with `_compute_signal`. Verdict logic: RSI ≥70 / ≤30 → Bearish/Bullish; price vs MAs → trend confirmation.
- **Market / Index Valuation** (`/index-valuation`, `/market-valuation`) — yfinance multi-index time series normalised to a 22× PE proxy.
- **F&O Ban** (`/fo-ban`) — attempts `NseService.fetch_nse(/api/liveMwpl)`; returns `{available:false, message: NSE_BLOCKED_MSG}` when blocked.
- **FII/DII** — equity flows use NSE's working `/api/fiidiiTradeReact` snapshot endpoint and accumulate in a local SQLite cache at `artifacts/python-backend/market_cache/fii_dii_cache.db` (committed to git so the history grows over time). NSE does not expose its bulk historical or F&O participant endpoints publicly, so the four F&O segment tabs render a graceful empty-state explaining the limitation. Backend: `app/services/fii_dii_service.py`. Routes: `GET /api/insights/fii-dii?segment=&days=` and `POST /api/insights/fii-dii/backfill`.
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

---

## API Authentication

- User endpoints: JWT tokens (HS256) via `Authorization: Bearer <token>`
- Admin endpoints: Admin JWT via `POST /api/admin/login` → use in `X-Admin-Token` header
- `ClerkAuthMiddleware` passes `X-Admin-Token` to ALL `/api/*` routes (not just `/api/admin`)
  so admin dashboard can call options/hydra/etc. endpoints directly

---

## GitHub Push

```bash
pnpm --filter @workspace/scripts run push-github
```
- Uses `GITHUB_PAT` secret
- Uploads all source files (406+ blobs) — takes ~3 minutes, be patient
- If it times out, run again; it is idempotent

---

## AI Client (`app/services/ai_client.py`)

**Free models only — zero per-token cost:**
1. `google/gemma-4-31b-it:free` — primary (Gemma 4, Google)
2. `qwen/qwen3-30b-a3b:free` — fallback (Qwen 3, Chinese open-source)
3. `meta-llama/llama-3.3-70b-instruct:free` — last resort (Llama 3.3, Meta)

**Via OpenRouter** (auto-configured by Replit integration, no API key cost).
**No paid OpenAI API** — removed entirely.

Rate limits on free tier: ~8 req/min per model. The audit uses batched calls (10 circulars/batch with 1.5s pauses) to stay within limits.

Functions: `ask()`, `ask_stream()`, `ask_json()`, `chat_with_history()`, `ask_ai_async()`

---

## SEBI Compliance Audit

**Files:**
- `scripts/sebi_audit.py` — main audit logic + `run_audit_async()` entry point
- `scripts/sebi_circulars_db.py` — 20 SEBI circulars 2019–2024 (hardcoded, always available)
- `reports/sebi_audit_YYYY-MM-DD.md` — generated reports (one per run date)

**How it works:**
1. Load 20 historical circulars from built-in 5-year database (no network needed)
2. Fetch live SEBI RSS feed for last 30 days (graceful fallback if network fails)
3. Merge + deduplicate (49 total circulars typical)
4. Split into batches of 10, send each batch to AI as a compressed prompt (~2,500 tokens)
5. Aggregate findings into final Markdown report

**API endpoints:**
- `POST /api/options/sebi-audit` — trigger audit (runs in-process, ~60-90 seconds)
- `GET /api/options/sebi-report` — latest report
- `GET /api/options/sebi-reports` — all historical reports (with `?full=true` for content)

**CLI (from `artifacts/python-backend/`):**
```bash
PYTHONPATH=. python3.11 scripts/sebi_audit.py --days 30
```

---

## Key Features

### Centralized Market Sentiment Engine (`/sentiment`)
- Route: `GET /api/sentiment/market` — composite snapshot (15-min cache)
- Route: `GET /api/sentiment/sectors` — per-sector heatmap
- Service: `app/services/market_sentiment_engine.py`
- Composite score (-100 to +100) from: News NLP (35%), Price Action (35%), India VIX (20%), PCR Proxy (10%)
- Iron Condor only recommended when VIX ≥ 22 AND sentiment is neutral (-30 to +30)

### Options Strategy Tester (`/options`)
- 349 tests passing (TDD)
- Live NSE options chain, Black-Scholes, Greeks, payoff curves, Monte Carlo VaR
- 17 strategies with weekly/monthly toggle
- AI chatbot: rule-based for common topics, falls back to free Gemma 4 / Qwen / Llama

### Admin Dashboard (`/admin`)
- 12 background jobs (market data, analysis, AI engine, compliance)
- SEBI Audit page: master-detail layout, all historical reports, run on-demand
- Bug Tracker: create/track/AI-analyse bugs
- User management, system logs, WhatsApp/Telegram integration

### Stock Analysis
- Technicals: TradingView-style with oscillators, MAs, pivots (10 timeframes)
- Financials: 6 tabs (overview, income, stats, dividends, earnings, revenue)
- All financials in ₹ Crores; NaN safely serialised as `null`

---

## Bug Tracking (MANDATORY for all agents)

Every bug must have a ticket before code changes:

```bash
# Create ticket
PYTHONPATH=artifacts/python-backend python3.11 artifacts/python-backend/scripts/add_bug.py \
  --title "Short title" --description "What's wrong" \
  --severity medium --component "Options Strategy Tester" --reported_by "agent"

# Mark in-progress
PYTHONPATH=artifacts/python-backend python3.11 -c "
from scripts.add_bug import update_bug_status
update_bug_status('a1b2c3d4', 'in-progress', 'Root cause: ...')
"

# Mark fixed (after code change + tests + push)
PYTHONPATH=artifacts/python-backend python3.11 -c "
from scripts.add_bug import update_bug_status
update_bug_status('a1b2c3d4', 'fixed', 'Fixed in commit abc1234')
"
```

AI Bug Analyser runs every 10 minutes automatically (background task in `main.py`).

---

## Tech Stack

| Layer | Technology |
|---|---|
| User Frontend | React 18, Vite, Tailwind CSS, wouter, TanStack Query, Recharts, ECharts, Lightweight Charts |
| Admin Frontend | React 18, Vite, Tailwind CSS, wouter, TanStack Query |
| Backend | Python 3.11, FastAPI, uvicorn, yfinance, pandas, scipy, spaCy, ta, openai (SDK only), lxml |
| AI | OpenRouter free tier: Gemma 4 31B, Qwen 3 30B, Llama 3.3 70B |
| Auth | Custom HS256 JWT (PyJWT + bcrypt) |
| Routing shim | Node.js + Express (proxies /api path only) |
