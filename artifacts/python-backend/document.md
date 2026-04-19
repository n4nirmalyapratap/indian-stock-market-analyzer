# Backend Index

This file is a quick index for the FastAPI backend in `artifacts/python-backend`.

## Purpose

- Powers all user and admin API endpoints
- Handles market data, analytics, scanners, options tools, sentiment, jobs, and bot integrations
- Enforces user JWT auth and admin session-token auth

## Markdown Sources Reviewed

- Root `README.md`
- Root `SETUP.md`
- Root `replit.md`
- Root `GITHUB_PUSH.md`
- Root `DOCUMENTATION_INDEX.md`

## Startup Flow

| File | Role |
|---|---|
| `run.py` | Startup entry point, ensures spaCy model, sets up log ring buffer, launches uvicorn |
| `main.py` | Creates the FastAPI app, mounts middleware, includes routers, and starts background tasks |
| `app/middleware/clerk_auth.py` | Auth middleware for `/api/*` requests |

## Background Tasks From `main.py`

- Telegram polling loop
- Universe refresh scheduler
- Cache warmup task
- Bug analyser scheduler

## Core Backend Areas

| Path | What is there |
|---|---|
| `app/routes/` | FastAPI routers and endpoint definitions |
| `app/services/` | Business logic and external data/service integrations |
| `app/lib/` | Shared backend utilities, universe data, and secret storage |
| `scripts/` | Maintenance utilities such as SEBI audit helpers and bug tooling |
| `tests/` | Backend test coverage for indicators, options, scanners, sentiment, Hydra, and endpoints |
| `pandas_ta/` | Local shim replacing the unavailable `pandas_ta` package |

## Authentication Model

- `/api/healthz` is public
- `/api/auth/*` is public for user registration and login
- `/api/admin/*` is handled by admin session-token checks
- Other `/api/*` endpoints require either:
  - `Authorization: Bearer <user-token>`
  - `X-Admin-Token: <admin-session-token>`

## Router Index

All routers are mounted under `/api` in `main.py`.

| Route file | Prefix | Main responsibility |
|---|---|---|
| `app/routes/health.py` | none | Health check |
| `app/routes/auth.py` | `/auth` | User registration and login |
| `app/routes/admin.py` | mixed `/admin/*` | Admin login, status, users, logs, secrets, bugs |
| `app/routes/jobs.py` | mixed `/admin/jobs*` | Admin job listing and manual job runs |
| `app/routes/stocks.py` | `/stocks` | Quotes, search, history, financials, technical summary |
| `app/routes/sectors.py` | `/sectors` | Sector list, rotation, single-sector lookup |
| `app/routes/sector_analytics.py` | `/sector-analytics` | Heatmap, top movers, sector detail analytics |
| `app/routes/patterns.py` | `/patterns` | Pattern scans |
| `app/routes/scanners.py` | `/scanners` | Saved scanners and ad hoc scans |
| `app/routes/options.py` | `/options` | Options chain, pricing, strategy, backtests, SEBI audit, chatbot |
| `app/routes/hydra.py` | `/hydra` | Hydra query, forecast, pairs, backtest, VaR, sentiment, data refresh |
| `app/routes/news.py` | `/news` | News feed, deals, events, stats, refresh |
| `app/routes/sentiment.py` | `/sentiment` | Market and sector sentiment refresh and reads |
| `app/routes/analytics.py` | `/analytics` | Correlation, breadth, movers, pattern stats, heatmap |
| `app/routes/nlp.py` | `/nlp` | Natural-language analysis endpoint |
| `app/routes/assistant.py` | `/assistant` | Assistant-related chat tooling |
| `app/routes/chat.py` | none | Symbol-specific chat history |
| `app/routes/cache.py` | none | Cache status and warmup |
| `app/routes/universe.py` | `/universe` | Universe status and refresh |
| `app/routes/telegram.py` | `/telegram` | Telegram bot status, messages, test, webhook, rotation sends |
| `app/routes/whatsapp.py` | `/whatsapp` | WhatsApp status, messages, test message, Twilio webhook |

## Key Services To Know First

| File | Responsibility |
|---|---|
| `app/services/price_service.py` | Price retrieval orchestration |
| `app/services/nse_service.py` | NSE data access |
| `app/services/yahoo_service.py` | Yahoo Finance access |
| `app/services/scanners_service.py` | Scanner execution logic |
| `app/services/patterns_service.py` | Pattern detection logic |
| `app/services/options_service.py` | Options calculations and market data helpers |
| `app/services/options_backtest_service.py` | Options backtesting |
| `app/services/news_service.py` | News aggregation and refresh |
| `app/services/market_sentiment_engine.py` | Sentiment scoring |
| `app/services/hydra_service.py` and related `hydra_*` files | Hydra analysis workflows |
| `app/services/log_buffer.py` | Structured in-memory logs for admin UI |

## Data And State

- `users.db` in the backend data directory stores email/password users and bug reports
- Admin sessions live in memory inside `app/routes/admin.py`
- `app/lib/universe_cache.json` stores cached universe data
- `reports/` stores generated SEBI audit markdown reports

## Related Repo Docs

- Root `README.md` for architecture and deployment overview
- Root `SETUP.md` for Docker, auth, and routing setup
- Root `replit.md` for backend rules, workflows, and feature notes
- Root `GITHUB_PUSH.md` for safe push behavior and protected-file rules
- Root `DOCUMENTATION_INDEX.md` for the markdown-level doc map
- `reports/sebi_audit_2026-04-12.md` as an example generated backend report
