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
| Backend pytest | `cd artifacts/python-backend && python3 -m pytest tests/ -v` | **513** (2 skipped/VADER) |
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

### Frontend test files
| File | What it covers |
|---|---|
| `options-utils.test.ts` | fmtINR, pct, computeHeatBars, QUICK_STRATEGIES |
| `indicators.test.ts` | Client-side indicator helpers |
| `smart-builder.test.ts` | Vol regime detection, score colour, scoring logic |

## Docker

```bash
cp .env.example .env   # fill SESSION_SECRET, ADMIN_PASSWORD
docker compose up --build -d
# User app:   http://localhost
# Admin:      http://localhost/admin
# API health: http://localhost/api/healthz
```

Required env vars: `SESSION_SECRET`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`
Optional: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`
