# Workspace — Indian Stock Market Analyzer

---

## ⚠️ Development Mandate: Test-Driven Development (TDD)

**All new features must be built using TDD — no exceptions.**

The workflow for every feature, endpoint, or component:

1. **Write failing tests first** — define what correct behaviour looks like before writing any implementation code.
2. **Write the minimum code to make tests pass** — no speculative code, no untested logic paths.
3. **Refactor** — clean up implementation while keeping tests green.
4. **Run the full suite before pushing** — backend pytest + frontend vitest must both be green.

### Test locations
| Layer | Location | Command |
|---|---|---|
| Backend | `artifacts/python-backend/tests/test_<feature>.py` | `cd artifacts/python-backend && python3 -m pytest tests/ -v` |
| Frontend | `artifacts/stock-market-app/src/lib/__tests__/<feature>.test.ts` | `pnpm --filter @workspace/stock-market-app run test` |

### Why TDD here?
This project is **data-heavy** (live market data, Black-Scholes pricing, options Greeks, HV percentiles). Pure unit tests catch regressions in financial calculations that are impossible to spot visually. Every pricing formula, scoring function, and strategy-builder rule must have a test.

---

## Overview

pnpm workspace monorepo. Python FastAPI backend + two React/Vite frontends
(user stock market app and admin dashboard). No NestJS, no PostgreSQL, no Clerk.

## Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11 · FastAPI · uvicorn (port 8090) |
| **User frontend** | React 18 · Vite · TypeScript · TailwindCSS · wouter |
| **Admin dashboard** | React 18 · Vite · TypeScript · TailwindCSS · wouter |
| **Auth (user app)** | Custom email+password, HS256 JWT — no Clerk |
| **Auth (admin)** | Username+password session token |
| **DB** | SQLite (user accounts only, via `users.db` in DATA_DIR) |
| **Charts** | Lightweight Charts · ECharts · Recharts |
| **Monorepo** | pnpm workspaces |
| **Node.js** | v24 |
| **TypeScript** | 5.9 |

## Ports & Paths

| Service | Port | Preview path |
|---|---|---|
| Python backend | 8090 | `/api` (via proxy) |
| User frontend | 3002 | `/` |
| Admin dashboard | 22133 | `/admin` |
| Mockup sandbox | 8081 | (canvas only) |

## Key Commands

```bash
# Run all backend unit tests
cd artifacts/python-backend && python3 -m pytest tests/ -v

# Run frontend unit tests
pnpm --filter @workspace/stock-market-app run test

# Push to GitHub
pnpm --filter @workspace/scripts run push-github

# Type-check all packages
pnpm run typecheck
```

## Critical Rules

- **Never install `pandas_ta` from PyPI** — the local shim at
  `artifacts/python-backend/pandas_ta/` wraps the `ta` library and must be used instead.
- **Always use `yf.Ticker(symbol).history()`** — never `yf.download()`.
- **Router is `wouter`** — never `react-router` or `next/navigation`.
- **Never recreate `artifacts/nestjs-backend/`** — deleted permanently.
- **Never touch `artifacts/api-server/` source** — it is a routing shim only.
- **`artifacts/api-server/artifact.toml`** uses absolute path
  `/home/runner/workspace/artifacts/python-backend` — never use relative paths.
- **Clerk is fully removed** — no `@clerk/*` imports, no `VITE_CLERK_PUBLISHABLE_KEY`,
  no `CLERK_SECRET_KEY` anywhere in the codebase.
- **Docker changes are mandatory and simultaneous** — any code change that affects
  deployment must update Docker files at the same time, in the same commit:
  - New Python dependency → add to `requirements.txt`
  - New environment variable → add to both `docker-compose.yml` (with `:-` default)
    and `.env.example` (with documentation comment)
  - New Vite plugin that is dev-only → guard behind `NODE_ENV !== "production"` in
    both `artifacts/stock-market-app/vite.config.ts` and
    `artifacts/admin-dashboard/vite.config.ts`
  - New route prefix or port → update `nginx.conf` and `docker-compose.yml`

## Project Structure

```
artifacts/
  python-backend/       FastAPI backend
    app/routes/         sectors, stocks, patterns, scanners, nlp, analytics, admin, auth, whatsapp
    app/services/       business logic
    app/lib/            universe.py, indicators.py
    pandas_ta/          local shim (do not pip install pandas_ta)
    tests/              116 pytest unit tests
  stock-market-app/     User frontend (/)
    src/lib/            api.ts, indicators.ts, __tests__/ (37 vitest tests)
    src/context/        CustomAuthContext.tsx (email+password JWT auth)
    src/pages/          Dashboard, Sectors, Patterns, Scanners, HydraAlpha, etc.
  admin-dashboard/      Admin panel (/admin)
    src/lib/api.ts      Admin API client (X-Admin-Token header)
    src/pages/          Overview, Users, Stocks, Scanners, Logs, Settings
  api-server/           Routing shim only — artifact.toml maps /api → port 8090
  mockup-sandbox/       Canvas design preview tool
scripts/
  src/push-github.ts    GitHub push script (Replit connector)
```

## Admin Panel

- URL: `/admin`
- Default credentials: `admin` / `NiftyAdmin@2026` (Replit dev only — change in prod via `ADMIN_PASSWORD` env var)
- Features: Overview stats, user management, stock data browser, scanner management, live log viewer (Summary + Raw views)

## Logs Page (admin)

- **Summary view** (default): Plain-English health banner, stats grid, recent activity, top error/warning groups
- **Raw view**: Dark terminal with Time/Level/Logger/Message columns, level filter pills, search, auto-scroll

## Testing

All features are built TDD — tests are written first, then the implementation.

| Suite | Command | Count |
|---|---|---|
| Backend pytest | `cd artifacts/python-backend && python3 -m pytest tests/ -v` | **6 384** (2 skipped/VADER) |
| Frontend vitest | `pnpm --filter @workspace/stock-market-app run test` | **160** |

### Backend test files
| File | What it covers |
|---|---|
| `test_options.py` | Black-Scholes, Greeks, IV, payoff, ATM helpers, backtest metrics |
| `test_hydra.py` | Hydra Alpha: signals, scoring, pairs, VaR, sentiment |
| `test_smart_builder.py` | Smart Strategy Builder: market state detection, scoring, custom strategy invention |
| `test_indicators.py` | Technical indicators (SMA, EMA, RSI, MACD, Bollinger, etc.) |
| `test_patterns.py` | Candlestick pattern detection |
| `test_log_buffer.py` | Admin log ring buffer |
| `test_data_quality.py` | Universe, sector, and stock data integrity |
| `test_scanners.py` | Scanner engine: `_compute_value` (all 20 indicator types), `_compare` (all 6 operators), `_eval_condition` (comparisons + crossovers), CRUD (create/read/update/delete with every field), default scanner integrity, AND/OR logic, score calculation, result shape, complex multi-condition combinations, edge cases |
| `test_scanner_condition_matrix.py` | **Full Cartesian-product matrix** of every condition the "New Scanner" UI can build: 26 left indicators × 7 operators × (26 right indicators + number) = 5 158 parametrized tests. Covers: `_compute_value` for all 26 specs with 300-bar data, indicator-vs-number (130), indicator-vs-indicator simple ops (3 380), crossover-vs-number (52), crossover-vs-indicator (1 352), CRUD round-trip for every indicator+operator (182), semantic correctness assertions, description string content. |
| `test_scanner_settings_matrix.py` | **Scanner-level settings matrix** — the two dimensions orthogonal to condition evaluation: (A) `build_universe` for all 16 non-empty subsets of {NIFTY100, MIDCAP, SMALLCAP, MICROCAP} + ALL, deduplication, ordering, symbol correctness; (B) Universe CRUD roundtrip × 16; (C) Logic CRUD × 2; (D) Universe × Logic × 32 combos; (E) Condition × Logic × Universe 3-way cross = 364 parametrized CRUD; (F) AND/OR multi-condition evaluation semantics (1–4 conditions each); (G) Universe isolation proof; (H) Multi-condition CRUD integrity; (I) Deduplication across overlapping universes; (J) Orthogonal updates (change universe without affecting logic and vice versa). 527 tests. |

### Frontend test files
| File | What it covers |
|---|---|
| `options-utils.test.ts` | fmtINR, pct, computeHeatBars, QUICK_STRATEGIES |
| `indicators.test.ts` | Client-side indicator helpers |
| `smart-builder.test.ts` | Vol regime detection, score colour, scoring logic |

## Docker

```bash
cp .env.example .env          # fill in required values (see .env.example comments)
docker compose up --build -d
# User app:   http://localhost
# Admin:      http://localhost/admin
# API health: http://localhost/api/healthz
# API docs:   http://localhost:8090/docs  (dev only — remove port 8090 in prod)
```

### Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `SESSION_SECRET` | **Yes** | Signs HS256 JWT tokens for user login (32+ random chars) |
| `ADMIN_PASSWORD` | **Yes** | Admin panel password |
| `ADMIN_USERNAME` | No (default: `admin`) | Admin panel username |
| `TWILIO_ACCOUNT_SID` | No | WhatsApp alerts via Twilio |
| `TWILIO_AUTH_TOKEN` | No | WhatsApp alerts via Twilio |
| `TELEGRAM_BOT_TOKEN` | No | Telegram bot alerts (get from @BotFather) |
| `WHATSAPP_ENABLED` | No (default: `false`) | Enable WhatsApp webhook endpoint |

### Docker file map

| File | Purpose |
|---|---|
| `docker-compose.yml` | Orchestrates backend + frontend containers, env vars, volumes, healthcheck |
| `artifacts/python-backend/Dockerfile` | Python 3.11-slim, installs requirements + spaCy model |
| `artifacts/stock-market-app/Dockerfile` | Multi-stage: builds both React apps, serves from nginx |
| `artifacts/stock-market-app/nginx.conf` | Routes `/api/` → backend, `/admin/` → admin app, `/` → user app |
| `.env.example` | Template for `.env` — all vars documented with comments |

### Sync rule
> When adding a new backend service, frontend feature, or env var — update all Docker files in the same commit. See the **Docker changes are mandatory and simultaneous** rule in Critical Rules above.
