# Indian Stock Market Analyzer

[![Python](https://img.shields.io/badge/python-3.11-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61dafb)](https://react.dev/)
[![Docker](https://img.shields.io/badge/docker-compose-2496ed)](https://docs.docker.com/compose/)

A real-time Indian equity analysis platform — sector rotation, technical analysis, candlestick patterns,
custom scanners, options analytics, a portfolio engine with FIFO tax reporting, an AI Stock Analyst,
macro pulse, FII/DII flows, news sentiment, SEBI compliance checks, plus WhatsApp & Telegram bots.

> **At a glance:** Python FastAPI backend · 30+ routers · 175+ endpoints · 50+ services · ~40 test files
> · Postgres-backed · Dockerised · live brokerage integrations · LLM-powered analyst with 3-provider fallback.

---

## Table of Contents

- [What it does](#what-it-does)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Running locally](#running-locally)
- [Docker deployment](#docker-deployment)
- [API surface](#api-surface)
- [Background workers](#background-workers)
- [Environment variables](#environment-variables)
- [Development notes](#development-notes)
- [Testing](#testing)
- [Contributing](#contributing)

---

## What it does

| Domain | Capabilities |
|---|---|
| **Market data** | Live NSE quotes (sectors, Nifty 100, Midcap, Smallcap, F&O universe), Yahoo Finance fallback, Stooq + Twelve Data backups, BSE coverage |
| **Sector analysis** | 15-sector rotation engine, correlation matrix, sector heatmap, sentiment per sector |
| **Technical analysis** | EMA, RSI, MACD, Bollinger Bands, ATR via `ta` library + vendored `pandas_ta` shim |
| **Patterns & scanners** | Candlestick pattern detection across the Nifty 100 universe, custom user-defined scanners with CRUD, ad-hoc scan runs |
| **Options** | Live chain, expiry list, PCR, single-leg pricing with full Greeks, multi-leg strategy analyser, event-driven backtester, scenario engine, VaR, F&O bhavcopy cache, SEBI/exchange compliance checks |
| **Portfolio** | Tradebook ingest (CSV / XLSX / screenshot OCR), broker import mapping wizard, valuation, risk metrics, performance, optimiser, FIFO capital-gains tax report (download as CSV) |
| **AI Stock Analyst** | Streaming SSE deep reports per ticker, watchlist scan mode, compare mode, daily quota, persistent saved analyses, real-money backtest of every BUY/SELL verdict at 1d/5d/30d horizons |
| **Council agents** | Multi-persona "council" verdicts per stock with consensus screener across all market caps |
| **Hydra quant engine** | Forecasting, Engle-Granger pair trading, generic backtester, parametric & historical VaR, news sentiment scoring |
| **Macro pulse** | RBI Repo Rate, India CPI/IIP, India 10Y G-Sec yield (FRED), global indices, FII/DII flows across 5 segments (Cash / F&O Index / F&O Stock / Provisional / Confirmed) |
| **Insights page** | Bulk + block deals, F&O ban list, SLBM, MTF, live IPO calendar, mutual fund scheme detail with NAV history |
| **Bots** | NLP-powered WhatsApp (Twilio) and Telegram bots — quotes, patterns, scanners, alerts, sector rotation pushes |
| **Email digests** | Per-user daily portfolio summaries at custom IST times, rate-limited delivery worker (default 20/min, 400/day) |
| **Admin ops** | Live logs ring buffer, secrets management (hot-reload), data-consistency dashboard, bug analyser, macro overrides, FII/DII status, logo cache, jobs runner, SEBI audit |

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 · FastAPI 0.115+ · uvicorn |
| Database | PostgreSQL 17 (auth, portfolios, AI analyses, FII/DII history, bug reports, secrets, etc.) |
| Data sources | NSE India · Yahoo Finance · Stooq · Twelve Data · BSE · FRED · World Bank · Tavily (news search) |
| NLP | spaCy 3.8 (rule-based EntityRuler) · VADER sentiment |
| Analytics | pandas · numpy 1.x · scipy · statsmodels (Engle-Granger cointegration) |
| Technical indicators | `ta` (EMA/RSI/MACD/BB/ATR) + vendored `pandas_ta` shim |
| LLM providers | OpenRouter (primary) · OpenAI (fallback) · Groq (fast primary for AI Analyst since 2026-05) |
| Frontend | React 18 · Vite · TypeScript · TailwindCSS · TanStack Query · wouter (not react-router) · shadcn/ui |
| Auth | Google OAuth (JWT-signed sessions) · Clerk middleware also wired |
| Bots | Twilio (WhatsApp) · Telegram Bot API (long-polling) |
| Background work | Pure asyncio tasks managed via FastAPI `lifespan` |
| Container runtime | Docker Compose (3 services: postgres + backend + nginx-frontend) |
| Dev platform | Replit (`.replit` workflows) — also runs natively anywhere |

> **Why pure Python on the backend:** there was a Node/NestJS backend earlier that has since been permanently removed.
> If you see `artifacts/nestjs-backend/` or `artifacts/nestjs-backend-placeholder/` reappear, delete them and push again.

---

## Project structure

```
.
├── artifacts/
│   ├── python-backend/              ← ACTIVE backend (FastAPI on port 8090)
│   │   ├── main.py                  ← app factory + 13 background schedulers + router registrations
│   │   ├── run.py                   ← startup wrapper (ensures spaCy model + ring buffer)
│   │   ├── requirements.txt         ← pinned Python deps with CVE-aware minimums
│   │   ├── Dockerfile               ← Python 3.11 image
│   │   ├── pandas_ta/               ← local shim wrapping the `ta` library
│   │   ├── app/
│   │   │   ├── routes/              ← 30 router modules (175+ endpoints)
│   │   │   ├── services/            ← 50+ domain services
│   │   │   ├── lib/                 ← auth_store, broker_keys, secrets_store,
│   │   │   │                          universe, symbol_map, sector_utils, etc.
│   │   │   └── middleware/clerk_auth.py
│   │   ├── scripts/                 ← bug_fixer, sebi_audit, backfill_bhavcopy,
│   │   │                              portfolio_audit_demo, sebi_circulars_db
│   │   ├── tests/                   ← ~40 test files, broad coverage
│   │   └── docs/BOT_COMMANDS.md
│   │
│   ├── stock-market-app/            ← ACTIVE frontend (React/Vite on port 3002)
│   │   ├── vite.config.ts           ← proxies /api/* → localhost:8090
│   │   ├── Dockerfile               ← multi-stage Node 24 → nginx static
│   │   ├── nginx.conf               ← serves SPA + proxies /api/* to backend
│   │   └── src/{pages,lib,components}/
│   │
│   ├── admin-dashboard/             ← Separate React app for ops (port 5173)
│   │   └── src/pages/               ← Logs, BugReports, MacroOverrides,
│   │                                  SebiAudit, Secrets, Telegram, WhatsApp,
│   │                                  Jobs, Users, AiAnalyst, LogoCache
│   │
│   ├── api-server/                  ← Replit routing shim ONLY — do NOT touch
│   │   └── .replit-artifact/        ← maps Replit's /api/* proxy to port 8090
│   │
│   └── mockup-sandbox/              ← Canvas design tool (do NOT touch)
│
├── docker-compose.yml               ← orchestrates postgres + backend + frontend
├── scripts/src/push-github.ts       ← GitHub push helper (uses Replit connector)
├── lib/                             ← shared TypeScript libs
├── .env.example                     ← every documented env var with context
├── SETUP.md                         ← deep-dive setup guide
├── CLAUDE.md                        ← coding agent guidelines
├── GITHUB_PUSH.md                   ← push workflow docs
└── EXAMPLES.md / DOCUMENTATION_INDEX.md / SECURITY_NOTES.md
```

### Deleted directories — do NOT recreate

| Directory | Replaced by |
|---|---|
| `artifacts/nestjs-backend/` | `artifacts/python-backend/` |
| `artifacts/nestjs-backend-placeholder/` | `artifacts/stock-market-app/` |

---

## Running locally

### Requirements

- Python 3.11
- Node.js 24 (frontend only) + `pnpm`
- PostgreSQL 17 (or run via Docker Compose, see below)

### 1. Install backend deps

```bash
cd artifacts/python-backend
pip install -r requirements.txt
```

`run.py` auto-downloads the spaCy `en_core_web_sm` model on first boot.

The backend **refuses to start** if any of these critical packages is missing
(`nsepython`, `statsmodels`, `pandas_ta`, `vaderSentiment`, `feedparser`,
`yfinance`, `spacy`) — loud failure beats silent degraded data.

### 2. Install frontend deps (monorepo root)

```bash
pnpm install     # pnpm is enforced via the root preinstall script
```

### 3. Configure environment

```bash
cp .env.example .env
# At minimum set SESSION_SECRET, POSTGRES_PASSWORD, DATABASE_URL,
# GOOGLE_CLIENT_ID + VITE_GOOGLE_CLIENT_ID, and ADMIN_GOOGLE_EMAILS.
# Generate a session secret with:
python -c "import secrets; print(secrets.token_hex(32))"
```

The backend will also **refuse to start** if `SESSION_SECRET` is missing, too
short, or one of the known placeholder strings (see `app/lib/auth_tokens.py`).

### 4. Start Postgres

```bash
docker run -d --name stock-postgres \
  -e POSTGRES_DB=niftynode -e POSTGRES_USER=niftynode \
  -e POSTGRES_PASSWORD=changeme \
  -p 5432:5432 postgres:17-alpine
```

Or use the `postgres` service from `docker-compose.yml`:
```bash
docker compose up -d postgres
```

### 5. Start backend + frontend

```bash
# Terminal 1 — backend
cd artifacts/python-backend && PORT=8090 python run.py

# Terminal 2 — frontend
cd artifacts/stock-market-app && pnpm dev
```

### 6. Verify

```bash
curl http://localhost:8090/api/healthz   # → {"status":"ok"}
open http://localhost:8090/docs          # Interactive OpenAPI (Swagger UI)
open http://localhost:3002               # Frontend app
```

### Running on Replit

The repo ships with `.replit` workflows:

| Workflow | What it runs |
|---|---|
| `Python Backend` | `cd artifacts/python-backend && PORT=8090 python run.py` |
| `artifacts/stock-market-app: web` | Vite dev server (auto-starts from `artifact.toml`) |

> **Do NOT start** `artifacts/api-server: API Server` — it is a routing-shim entry only.
> Replit reads its `.replit-artifact/artifact.toml` to route `/api/*` → port 8090, and the source code inside the folder is unused.

Use the Replit Secrets pane (padlock icon) instead of `.env` — Replit ignores `.env` files.

---

## Docker deployment

Three containers, one command.

### Architecture

```
                     ┌──────────────────────────────┐
   Browser ─────────►│  frontend container (nginx)  │ :80
                     │                              │
                     │  /api/*  ────────────────────┼─► backend:8090
                     │  /*      → React SPA (static)│
                     └──────────────────────────────┘
                                                       │
                                          ┌────────────▼────────────┐
                                          │  backend container       │ :8090
                                          │  Python FastAPI          │
                                          │  → postgres:5432         │
                                          └─────────────┬────────────┘
                                                        │
                                          ┌─────────────▼────────────┐
                                          │  postgres:17-alpine       │ :5432
                                          │  volume: postgres-data    │
                                          └──────────────────────────┘
```

### Quick start (local)

```bash
cp .env.example .env       # fill in at least the required vars
docker compose up --build
open http://localhost
curl http://localhost/api/healthz   # → {"status":"ok"}
```

### Production (detached)

```bash
docker compose up --build -d
```

### Deploying to a cloud provider

**AWS ECS (Fargate)**
1. Push images to ECR (`docker tag stock-backend <ecr-url>; docker push`)
2. Create three task definitions (postgres or RDS, backend, frontend)
3. Put an ALB in front: `/api/*` → backend target group, `/*` → frontend
4. Use RDS for Postgres in production — the bundled container is a dev convenience

**Azure Container Apps**
1. `az acr build ...` to push to ACR
2. Deploy three container apps in the same environment
3. Use Azure Database for PostgreSQL (Flexible Server) for `DATABASE_URL`
4. Container Apps resolves services by name within an environment

**Self-hosted (EC2 / VM)**
```bash
git clone https://github.com/n4nirmalyapratap/indian-stock-market-analyzer
cd indian-stock-market-analyzer
cp .env.example .env && $EDITOR .env
docker compose up --build -d
```

### Key files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Postgres + backend + frontend orchestration |
| `artifacts/python-backend/Dockerfile` | Python 3.11 + FastAPI image |
| `artifacts/stock-market-app/Dockerfile` | Node 24 build → nginx static image |
| `artifacts/stock-market-app/nginx.conf` | SPA serve + `/api/*` reverse proxy |
| `.dockerignore` | Excludes `node_modules`, caches, deprecated folders |

---

## API surface

> **Canonical reference:** with the backend running, the full live OpenAPI spec is at
> **`http://localhost:8090/docs`** (Swagger UI) and **`/redoc`** (ReDoc).
> Below is a curated index — see `/docs` for request/response schemas.

All routes are mounted under `/api`.

### Health & system

| Method | Path |
|---|---|
| GET | `/api/healthz` |
| GET | `/api/cache/status` |
| POST | `/api/cache/warmup` |

### Sectors

| Method | Path |
|---|---|
| GET | `/api/sectors` *(all NSE sector indices)* |
| GET | `/api/sectors/rotation` *(rotation phase + buy recommendations)* |
| GET | `/api/sectors/{symbol}` |
| GET | `/api/sector-analytics/heatmap` |
| GET | `/api/sector-analytics/top-movers` |
| GET | `/api/sector-analytics/{sector}/detail` |

### Stocks

| Method | Path |
|---|---|
| GET | `/api/stocks/nifty100` |
| GET | `/api/stocks/midcap` |
| GET | `/api/stocks/smallcap` |
| GET | `/api/stocks/search?q=...` |
| GET | `/api/stocks/{symbol}` *(quote + technical analysis + entry recommendation)* |
| GET | `/api/stocks/{symbol}/financials` |
| GET | `/api/stocks/{symbol}/dcf` |
| GET | `/api/stocks/{symbol}/technical-summary` |
| GET | `/api/stocks/{symbol}/tri-factor` |
| GET | `/api/dashboard/top-movers/all` |

### Patterns

| Method | Path |
|---|---|
| GET | `/api/patterns` *(via insights router — query: `signal=CALL\|PUT&universe=NIFTY100`)* |
| POST | `/api/patterns/scan` *(trigger fresh scan)* |

### Scanners

| Method | Path |
|---|---|
| GET | `/api/scanners` *(list)* |
| POST | `/api/scanners` *(create)* |
| GET | `/api/scanners/{scanner_id}` |
| PUT | `/api/scanners/{scanner_id}` |
| DELETE | `/api/scanners/{scanner_id}` |
| POST | `/api/scanners/{scanner_id}/run` |
| POST | `/api/scanners/adhoc/run` *(one-off conditions without persistence)* |

### Options

| Method | Path |
|---|---|
| GET | `/api/options/spot/{symbol}` |
| GET | `/api/options/chain/{symbol}` |
| GET | `/api/options/expiries/{symbol}` |
| GET | `/api/options/pcr/{symbol}` |
| GET | `/api/options/fo-stocks` |
| POST | `/api/options/price` *(single-leg + Greeks)* |
| POST | `/api/options/strategy` *(multi-leg analyser)* |
| POST | `/api/options/simulate` |
| POST | `/api/options/scenario` |
| POST | `/api/options/backtest` *(event-driven)* |
| POST | `/api/options/var` |
| POST | `/api/options/smart-suggest` |
| POST | `/api/options/chat` *(NLP options assistant)* |
| GET | `/api/options/strategies` *(template names)* |
| GET | `/api/options/bhavcopy/coverage` |
| POST | `/api/options/bhavcopy/refresh` |
| GET | `/api/options/compliance?on_date=YYYY-MM-DD` |
| POST | `/api/options/sebi-audit` |
| GET | `/api/options/sebi-report` |
| GET | `/api/options/sebi-reports` |

### Portfolio

| Method | Path |
|---|---|
| GET / PUT / DELETE | `/api/portfolio/{pid}` |
| GET / POST | `/api/portfolio/{pid}/transactions` |
| DELETE | `/api/portfolio/{pid}/transactions/{tx_id}` |
| POST | `/api/portfolio/{pid}/transactions/bulk-delete` |
| POST | `/api/portfolio/{pid}/import` *(CSV)* |
| POST | `/api/portfolio/{pid}/import-file` *(CSV or XLSX)* |
| POST | `/api/portfolio/{pid}/preview-import` *(mapping wizard step 1)* |
| POST | `/api/portfolio/{pid}/import-with-mapping` *(mapping wizard step 2)* |
| POST | `/api/portfolio/{pid}/extract-from-image` *(broker screenshot OCR)* |
| POST | `/api/portfolio/{pid}/apply-extracted` |
| GET | `/api/portfolio/{pid}/valuation` |
| GET / POST | `/api/portfolio/{pid}/risk` |
| GET | `/api/portfolio/{pid}/performance` |
| POST | `/api/portfolio/{pid}/optimize` |
| GET | `/api/portfolio/{pid}/tax-report?fy=YYYY-YY` |
| GET | `/api/portfolio/{pid}/tax-report/fys` *(list available FYs)* |
| GET | `/api/portfolio/{pid}/tax-report.csv` *(download)* |

### AI Stock Analyst

| Method | Path |
|---|---|
| GET | `/api/ai-analyst/feature` |
| GET | `/api/ai-analyst/quota` |
| GET | `/api/ai-analyst/report/{ticker}` |
| POST | `/api/ai-analyst/run` *(SSE stream — body provides ticker)* |
| POST | `/api/ai-analyst/run/{ticker}` *(SSE stream — ticker in path)* |
| POST | `/api/ai-analyst/scan` *(SSE stream — sequential watchlist scan)* |
| GET | `/api/ai-analyst/saved/{sid}` |
| DELETE | `/api/ai-analyst/saved/{sid}` |
| POST | `/api/ai-analyst/saved/bulk-delete` |
| GET | `/api/ai-analyst/saved/group?tickers=...` |
| GET | `/api/ai-analyst/backtest/overall` *(hit rate by horizon + verdict)* |
| GET | `/api/ai-analyst/backtest/by-ticker` |

### Council agents

| Method | Path |
|---|---|
| GET | `/api/agents/screener/consensus` *(near-unanimous picks across all caps)* |
| GET | `/api/agents/{symbol}` *(fast deterministic council — no LLM)* |
| GET | `/api/agents/{symbol}/council` *(full council with AI thesis per persona)* |
| GET | `/api/agents/{symbol}/{persona_id}` *(single-persona deep dive)* |

### Hydra quant engine

| Method | Path |
|---|---|
| GET | `/api/hydra/status` |
| POST | `/api/hydra/query` *(supervisor — auto-routes to the right tool)* |
| POST | `/api/hydra/forecast` |
| POST | `/api/hydra/pairs/analyze` |
| POST | `/api/hydra/pairs/scan` |
| POST | `/api/hydra/backtest` |
| POST | `/api/hydra/var` |
| GET | `/api/hydra/sentiment` |
| POST | `/api/hydra/sentiment/score` |
| GET | `/api/hydra/data/stats` |
| POST | `/api/hydra/data/update` |

### Insights

| Method | Path |
|---|---|
| GET | `/api/insights/indices` |
| GET | `/api/insights/global-indices` *(grouped by region)* |
| GET | `/api/insights/macro/strip` *(6 tile-sized macro readings)* |
| GET | `/api/insights/macro` *(full macro dashboard payload)* |
| GET | `/api/insights/bulk-block-deals` |
| GET | `/api/insights/fo-ban` |
| GET | `/api/insights/slbm` |
| GET | `/api/insights/mtf` |
| GET | `/api/insights/ipos` *(live calendar — mainboard + SME)* |
| GET | `/api/insights/mf-scheme/{code}` *(NAV history + returns ladder)* |
| POST | `/api/insights/fii-dii/backfill` |

### Analytics

| Method | Path |
|---|---|
| GET | `/api/analytics/sector-correlation` *(30-day Pearson)* |
| GET | `/api/analytics/breadth-history` |
| GET | `/api/analytics/top-movers` |
| GET | `/api/analytics/pattern-stats` *(detection counts + 5-day backtest)* |
| GET | `/api/analytics/sector-heatmap` |

### Sentiment

| Method | Path |
|---|---|
| GET | `/api/sentiment/market` *(centralised snapshot, 15-min cache)* |
| GET | `/api/sentiment/sectors` *(per-sector for heatmap)* |
| GET | `/api/sentiment/refresh` *(bypass cache)* |

### News

| Method | Path |
|---|---|
| GET | `/api/news/deals` |
| GET | `/api/news/events` |
| GET | `/api/news/stats` |
| POST | `/api/news/refresh` |

### NLP

| Method | Path |
|---|---|
| POST | `/api/nlp/query` *("analyze RELIANCE", "bullish IT stocks", etc.)* |

### Email digest

| Method | Path |
|---|---|
| GET / POST | `/api/email-digest/subscriptions` |
| DELETE | `/api/email-digest/subscriptions/{sub_id}` |
| GET | `/api/email-digest/config` *(non-sensitive SMTP wire status)* |
| POST | `/api/email-digest/send-now/{sub_id}` |

### Telegram bot

| Method | Path |
|---|---|
| GET | `/api/telegram/status` |
| GET | `/api/telegram/messages` |
| POST | `/api/telegram/webhook` |
| POST | `/api/telegram/set-webhook` |
| POST | `/api/telegram/test` |
| GET | `/api/telegram/rotation-preview` |
| POST | `/api/telegram/send-rotation` |

### WhatsApp bot

| Method | Path |
|---|---|
| GET / PUT / POST | `/api/whatsapp/status` |
| POST | `/api/whatsapp/message` *(NLP-powered, test endpoint)* |
| POST | `/api/whatsapp/twilio` *(Twilio webhook)* |
| GET | `/api/whatsapp/messages` |
| POST | `/api/whatsapp/qr` |

### Universe & logos

| Method | Path |
|---|---|
| GET | `/api/universe/status` |
| POST | `/api/universe/refresh` |
| GET | `/api/logos/{symbol}` *(cached PNG — fetches from Dhan CDN first time)* |

### Search & chat history

| Method | Path |
|---|---|
| GET | `/api/search/suggest?q=...` |
| GET | `/api/chat/history/{symbol}` |
| POST | `/api/assistant/chat` |

### Auth

| Method | Path |
|---|---|
| POST | `/api/auth/google` |

> Password login + registration endpoints exist but are intentionally disabled — Google OAuth only.

### User broker keys

| Method | Path |
|---|---|
| PUT | `/api/user/broker-keys/{broker}` |
| DELETE | `/api/user/broker-keys/{broker}` |
| POST | `/api/user/broker-keys/{broker}/test` |

Supported brokers: `zerodha`, `angel_one`, `dhan`, `groww`, `upstox`.

### Admin (Google-restricted via `ADMIN_GOOGLE_EMAILS`)

| Method | Path |
|---|---|
| POST | `/api/admin/google-login` |
| GET | `/api/admin/status` |
| GET | `/api/admin/users` / `/api/admin/users/app` |
| GET | `/api/admin/logs` *(in-memory ring buffer)* |
| GET / PUT / DELETE | `/api/admin/secrets[/{key}]` *(hot-reload, no restart)* |
| POST | `/api/admin/secrets/validate` |
| GET | `/api/admin/data-consistency` |
| GET / POST / PATCH / DELETE | `/api/admin/bugs[/{bug_id}]` |
| POST | `/api/admin/bugs/run-fixer` |
| GET | `/api/admin/bugs/fixer-status` |
| GET / PUT / DELETE | `/api/admin/macro/overrides[/{indicator}]` |
| GET | `/api/admin/fii-dii/status` |
| POST | `/api/admin/fii-dii/refresh` |
| GET | `/api/admin/jobs` |
| POST | `/api/admin/jobs/{job_id}/run` |
| GET | `/api/admin/logos` |
| POST / DELETE | `/api/admin/logos/{symbol}[/refresh]` |
| GET / POST / PUT | `/api/ai-analyst/admin/{stats,flush,quota}` |

---

## Background workers

The backend runs **13 async background tasks** (managed via the FastAPI `lifespan` context),
all started on boot and cancelled gracefully on shutdown. These do real, important work — they're
not nice-to-haves.

| Task | Cadence | What it does |
|---|---|---|
| `_telegram_polling_loop` | continuous | Long-polls `getUpdates` for the Telegram bot |
| `_universe_scheduler` | daily @ 16:05 IST | Refreshes NSE Nifty 100 / Midcap / Smallcap / sector universe |
| `_cache_warmup_task` | once on boot | Warms the disk price cache when market is closed + cache is thin |
| `_market_state_transition_loop` | every 60s | Watches NSE state (OPEN/CLOSED/WEEKEND/PRE_OPEN), bumps cache version on transitions, seals EOD snapshots |
| `_bug_fixer_loop` | every 10 min | AI bug analyser — diagnoses open bugs, suggests fixes, **never auto-applies code changes** |
| `_risk_free_rate_scheduler` | daily | Refreshes the India 10Y G-Sec yield from FRED |
| `_bhavcopy_refresh_scheduler` | daily | Pulls F&O bhavcopy from NSE/BSE (last 7 trading days on first run) |
| `_bot_alerts_tick_loop` | every 5 min | Evaluates per-chat alert subscriptions, dispatches via Telegram + WhatsApp |
| `_ai_backtest_scheduler` | daily (after 6h delay) | Evaluates every BUY/SELL verdict against actual price moves at 1d/5d/30d horizons |
| `_email_digest_scheduler` | every 60s | Enqueues due daily digests into `email_digest_queue` |
| `_email_digest_worker` | every 60s | Drains the queue via SMTP at the configured burst-cap rate |
| `_fii_dii_scheduler` | every 4h (full sync every 24h) | Keeps FII/DII history fresh across all 5 segments, gap-fills last 30 trading days, F&O recent-day healer every tick |
| `_dhan_scrip_master_preload` | once per calendar day | Downloads the Dhan F&O scrip master CSV — used for symbol-to-token mapping |

All loops follow a **loud-fallback** pattern: a single tick failure is logged as a warning and the
loop continues with the next tick. None of them can crash the server.

---

## Environment variables

See `.env.example` for the full annotated list. The required + recommended subset:

### Required

| Variable | Purpose |
|---|---|
| `SESSION_SECRET` | JWT signing key — must be long, random, and not a known placeholder |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Postgres bootstrap |
| `DATABASE_URL` | `postgresql://user:pass@host:5432/dbname` |
| `GOOGLE_CLIENT_ID` + `VITE_GOOGLE_CLIENT_ID` | Google OAuth (must match) |
| `ADMIN_GOOGLE_EMAILS` | Comma-separated list of admin Google accounts |

### Recommended

| Variable | Unlocks |
|---|---|
| `FRED_API_KEY` | RBI Repo Rate, India CPI/IIP, 10Y G-Sec yield tiles |
| `AI_INTEGRATIONS_OPENROUTER_API_KEY` | AI Stock Analyst, Compare, Scan, Macro commentary |
| `AI_INTEGRATIONS_OPENROUTER_BASE_URL` | Defaults to `https://openrouter.ai/api/v1` |
| `AI_MODEL` / `AI_FALLBACK_MODEL` | Override model selection (any OpenRouter slug) |
| `AI_INTEGRATIONS_OPENAI_API_KEY` | Fallback when OpenRouter is down |
| `TAVILY_API_KEY` | Tops up AI Analyst news block for mid/small caps |

### Optional

| Variable | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Enables Telegram polling |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `WHATSAPP_ENABLED` | Enables WhatsApp via Twilio |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM_EMAIL` / `SMTP_FROM_NAME` | Email digests (Gmail App Password recommended) |
| `EMAIL_DIGEST_SENDS_PER_MIN` (default `20`) | Worker burst cap |
| `EMAIL_DIGEST_SENDS_PER_DAY` (default `400`) | Stays under Gmail free-tier 500/day limit |
| `CORS_ALLOWED_ORIGINS` | Comma-separated production origins (wildcard `*` is intentionally rejected) |
| `FEATURE_AI_ANALYST` (default `on`) | Feature gate |
| `AI_ANALYST_TIMEOUT_SEC` (default `240`) | Per-call timeout |
| `AI_ANALYST_DAILY_QUOTA` (default `3`) | Deep reports per user per day (cached reports don't count) |
| `BIAS_CHECK_ENABLED` (default `true`) | Anti-FOMO guard — downgrades BUY → HOLD when stock is `BIAS_THRESHOLD`% above 20-day MA |
| `BIAS_THRESHOLD` (default `5.0`) | Percent threshold |
| `BIAS_RELAX_MULTIPLIER` (default `1.6`) | Relaxes threshold on strong trend stacks (MA5>MA10>MA20) |

Secrets can also be set live via the **Admin Dashboard → Secrets** page — no restart needed.

---

## Development notes

- **New backend features** go into `artifacts/python-backend/` — Python only.
- **Frontend changes** go into `artifacts/stock-market-app/src/`. Frontend uses relative `/api/*`
  paths; the Vite proxy routes them to port 8090.
- **Admin-dashboard changes** go into `artifacts/admin-dashboard/src/` — separate Vite app.
- `pandas_ta` is not available on PyPI for Python 3.11+ — the project uses a custom shim at
  `artifacts/python-backend/pandas_ta/` that wraps the `ta` library. The boot check verifies
  it's importable.
- **NEVER touch `artifacts/api-server/` source code** — it's a Replit routing shim, only
  `artifact.toml` matters.
- **NEVER recreate `artifacts/nestjs-backend/` or `artifacts/nestjs-backend-placeholder/`** —
  if they reappear, delete them.
- CORS allowlist is **pinned** — wildcard `*` is rejected on purpose (combined with
  token-bearing fetches it lets any third-party site drive the API).
- See `CLAUDE.md` for behavioural guidelines when using LLM coding assistants on this repo.
- See `SETUP.md` for the long-form setup walkthrough.
- See `EXAMPLES.md` for sample API calls.
- See `SECURITY_NOTES.md` for the security posture and known threat model.

---

## Testing

```bash
cd artifacts/python-backend
pytest                            # full suite
pytest tests/test_patterns.py     # one file
pytest -k "scanner"               # by keyword
pytest --cov=app --cov-report=term-missing   # coverage report
```

The test suite covers patterns, scanners, options pricing + backtest, portfolio + tax,
Hydra forecasting + pairs + VaR, macro, sectors rotation, FII/DII, news, sentiment,
email digest, AI analyst safety, data quality, dashboard data, and more.

---

## GitHub

Repository: [`n4nirmalyapratap/indian-stock-market-analyzer`](https://github.com/n4nirmalyapratap/indian-stock-market-analyzer)

To push from Replit: `pnpm --filter @workspace/scripts run push-github`
See [`GITHUB_PUSH.md`](GITHUB_PUSH.md) for the full workflow including OAuth setup.

All commits are pushed to the `main` branch after each set of changes.

---

## Contributing

This is a personal project — issues and PRs welcome but expect some delay in review.

The repo has **no license file** as of writing, which legally means all rights reserved.
If you intend to fork or contribute, ping the owner first.
