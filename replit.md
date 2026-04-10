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

## Tech Stack

| Layer | Technology |
|---|---|
| User Frontend | React 18, Vite, Tailwind CSS, wouter, TanStack Query, Recharts, ECharts, Lightweight Charts |
| Admin Frontend | React 18, Vite, Tailwind CSS, wouter, TanStack Query, Recharts |
| Backend | Python 3.11, FastAPI, uvicorn, yfinance, pandas, scipy, spaCy, ta |
| Auth | Custom HS256 JWT (PyJWT + bcrypt) |
| Routing shim | Node.js + Express (proxies /api path) |
