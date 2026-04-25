# Nifty Node — Indian Stock Market Analyzer

## Project Overview

A full-stack Indian stock market analysis platform with:
- **User app** (`/`) — React/Vite frontend for stock analysis, charts, options, news
- **Admin dashboard** (`/admin`) — React/Vite admin panel for user/system/compliance management
- **Python FastAPI backend** (`/api`) — All API endpoints on port 8090

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
