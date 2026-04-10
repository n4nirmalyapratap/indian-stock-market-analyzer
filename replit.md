# Indian Stock Market Analyzer — Agent Memory

## Overview

A real-time Indian stock market analysis platform with:
- Sector rotation tracking, candlestick patterns, custom scanners, NLP queries
- Telegram bot + WhatsApp bot (accessible via admin panel only)
- **User app** (Clerk auth) at `/` and **Admin dashboard** (username/password) at `/admin/`
- Python FastAPI backend + two React/Vite frontends

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 · FastAPI · uvicorn |
| Data sources | NSE India API · Yahoo Finance (`yfinance`) |
| NLP | spaCy 3.8 (rule-based EntityRuler) |
| Analytics | pandas · numpy · scipy |
| Technical indicators | `ta` library via local `pandas_ta/` shim |
| User Frontend | React 19 · Vite · TypeScript · TailwindCSS · TanStack Query · Clerk auth |
| Admin Frontend | React 19 · Vite · TypeScript · TailwindCSS · TanStack Query · username/password auth |
| Router | wouter (NOT react-router) |
| UI | shadcn/ui |
| Monorepo | pnpm workspaces (Node.js 24) |
| Auth (users) | Clerk (Google OAuth + email) — `@clerk/react` + Python JWKS verification |
| Auth (admin) | Username/password → session token (`X-Admin-Token` header, 8h TTL) |
| Deployment | Docker (two-container: nginx serving both frontends + Python backend) |

---

## Project Structure

```
/
├── artifacts/
│   ├── python-backend/          ← ACTIVE: FastAPI backend (port 8090)
│   │   ├── main.py              ← App entry point, all routers registered
│   │   ├── run.py               ← Startup script + spaCy model self-heal
│   │   ├── requirements.txt     ← Python dependencies
│   │   ├── Dockerfile           ← Production Docker image (python:3.11-slim)
│   │   ├── pandas_ta/           ← LOCAL SHIM — NOT a PyPI package (see below)
│   │   └── app/
│   │       ├── middleware/
│   │       │   └── clerk_auth.py  ← Clerk JWT + admin token passthrough
│   │       └── routes/
│   │           ├── admin.py     ← /api/admin/* (session-token protected)
│   │           ├── whatsapp.py
│   │           ├── telegram.py
│   │           └── ...
│   │
│   ├── stock-market-app/        ← ACTIVE: User React/Vite frontend (port 3002)
│   │   ├── Dockerfile           ← Builds BOTH frontends + nginx (combined image)
│   │   ├── nginx.conf           ← Routes /api, /admin/, / in production
│   │   └── src/
│   │       ├── App.tsx          ← Clerk auth + sidebar (NO WhatsApp/Telegram nav)
│   │       └── lib/api.ts       ← fetchApi: auto-attaches Clerk JWT
│   │
│   ├── admin-dashboard/         ← ACTIVE: Admin React/Vite (port 22133, /admin)
│   │   └── src/
│   │       ├── App.tsx          ← No Clerk — uses session token from login
│   │       ├── pages/
│   │       │   ├── LoginPage.tsx    ← Username/password form
│   │       │   ├── AppStatus.tsx    ← Backend health/uptime
│   │       │   ├── UsersPage.tsx    ← Clerk user list
│   │       │   ├── WhatsAppBot.tsx  ← Bot simulator (moved from user app)
│   │       │   ├── TelegramBot.tsx  ← Bot management (moved from user app)
│   │       │   └── LogsPage.tsx     ← Log viewer
│   │       └── lib/api.ts       ← fetchAdmin: sends X-Admin-Token header
│   │
│   ├── api-server/              ← ROUTING SHIM ONLY — do NOT touch or start
│   └── mockup-sandbox/          ← Canvas design tool (do not touch)
│
├── docker-compose.yml           ← Orchestrates backend + frontend containers
├── .env.example                 ← Template — copy to .env
├── SETUP.md                     ← Complete setup documentation
└── replit.md                    ← This file (agent memory)
```

### ⚠️ Deleted Directories (do NOT recreate)

| Directory | Reason removed |
|---|---|
| `artifacts/nestjs-backend/` | Deprecated — replaced by Python |
| `artifacts/nestjs-backend-placeholder/` | Old placeholder |

---

## Workflows (Replit — Active)

| Workflow name | Command | Port | State |
|---|---|---|---|
| `Python Backend` | `bash -c 'cd /home/runner/workspace/artifacts/python-backend && PORT=8090 python run.py'` | 8090 | RUNNING |
| `artifacts/stock-market-app: web` | `BASE_PATH=/ PORT=3002 pnpm --filter @workspace/stock-market-app run dev` | 3002 | RUNNING |
| `artifacts/admin-dashboard: web` | `BASE_PATH=/admin PORT=22133 pnpm --filter @workspace/admin-dashboard run dev` | 22133 | RUNNING |
| `artifacts/api-server: API Server` | routing shim echo — intentionally NOT_STARTED | 8090 | NOT_STARTED |

---

## Authentication Architecture

### User App (Clerk)
```
Browser → Clerk sign-in → JWT token
  → API calls: Authorization: Bearer <clerk-jwt>
  → Python middleware: verifies JWT via JWKS
```

### Admin Dashboard (session token)
```
Browser → POST /api/admin/login {username, password}
  → Python: checks ADMIN_USERNAME / ADMIN_PASSWORD env vars
  → Returns session token (random hex, 8h TTL, stored in memory dict)
  → API calls: X-Admin-Token: <session-token>
  → Python middleware: validates token in _sessions dict
  → Admin token bypasses Clerk check for all /api/* routes
```

### Isolation
- `/api/admin/*`: skip Clerk entirely — only respond to valid admin session tokens
- `/api/*` (non-admin): accepts either Clerk JWT or admin session token
- Regular Clerk users: **cannot** reach any `/api/admin/*` endpoint

---

## ⚠️ Critical: Two-Layer Proxy Architecture (Replit)

### Layer 1 — Replit Proxy (outermost, browser-facing)

| URL path | Routes to port | Controlled by |
|---|---|---|
| `/api/*` | **8090** | `artifacts/api-server/.replit-artifact/artifact.toml` |
| `/admin/*` | **22133** | `artifacts/admin-dashboard/.replit-artifact/artifact.toml` |
| `/*` | **3002** | `artifacts/stock-market-app/.replit-artifact/artifact.toml` |

### Layer 2 — Vite Dev Server Proxy (internal only)
Both Vite servers proxy `/api/*` → `http://localhost:8090`.

### In Docker (production)
nginx handles all routing in one config (`nginx.conf`):
```nginx
location /api/    { proxy_pass http://backend:8090; }
location /admin/  { alias /usr/share/nginx/admin/; try_files ... }
location /        { root /usr/share/nginx/html; try_files ... }
```

---

## Docker Deployment

### Architecture

```
Browser → http://localhost (port 80)
    → nginx container
        → /api/*   → backend container (port 8090, internal)
        → /admin/  → admin dashboard static files
        → /        → user app static files
```

### First-time setup

```bash
git clone https://github.com/n4nirmalyapratap/indian-stock-market-analyzer
cd indian-stock-market-analyzer
cp .env.example .env
# Edit .env — at minimum set Clerk keys and ADMIN_PASSWORD
docker compose up --build -d
```

### Update after any code/config change

```bash
git pull && docker compose up --build -d
```

**`--build` is mandatory** — pnpm-lock.yaml is not committed, so Docker cannot skip the install step.

### Key Docker files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Orchestrates backend + combined frontend; env vars; healthcheck |
| `artifacts/python-backend/Dockerfile` | python:3.11-slim; pip install; spaCy model pre-baked |
| `artifacts/stock-market-app/Dockerfile` | **Builds both frontends** (user + admin) → nginx:alpine |
| `artifacts/stock-market-app/nginx.conf` | Routes /api, /admin, / — SPA fallbacks for both apps |
| `.env.example` | Template for all required env vars |

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `CLERK_PUBLISHABLE_KEY` | Yes | Backend JWT verification (Clerk JWKS) |
| `CLERK_SECRET_KEY` | Yes | Clerk REST API (admin user list) |
| `VITE_CLERK_PUBLISHABLE_KEY` | Yes | Baked into user frontend at build time |
| `ADMIN_USERNAME` | Yes | Admin dashboard login username |
| `ADMIN_PASSWORD` | Yes | Admin dashboard login password |
| `TELEGRAM_BOT_TOKEN` | No | Enables Telegram polling |
| `TWILIO_ACCOUNT_SID` | No | Enables WhatsApp |
| `TWILIO_AUTH_TOKEN` | No | Enables WhatsApp |

---

## pandas_ta — Local Package Shim

`pandas-ta` from PyPI is broken on Python 3.11+. Custom shim at `artifacts/python-backend/pandas_ta/`.

- Wraps the `ta` library with pandas-ta function signatures
- `PYTHONPATH=/app` in Docker; `sys.path.insert` in `run.py` + `indicators.py`
- **Never** `pip install pandas_ta` | **Never** add to `requirements.txt`
- **Never** add `pandas_ta` to `SKIP_DIRS` in push script

---

## GitHub Push Script

```bash
pnpm --filter @workspace/scripts run push-github
```

### What is NEVER pushed (skipped)

| Category | Items |
|---|---|
| Directories | `node_modules`, `dist`, `build`, `__pycache__`, `.pythonlibs`, `market_cache`, `.git`, `.agents`, `.local` |
| Files | `pnpm-lock.yaml`, `hydra_prices.db`, `.DS_Store`, `.tsbuildinfo` |
| Extensions | `.png`, `.jpg`, `.gif`, `.webp`, `.ico`, `.woff`, `.ttf`, `.mp4`, `.pdf`, `.zip`, `.pyc` |

**`pandas_ta/` is always included in pushes.**

### ⚠️ Never add `base_tree` to the Git trees API call

Push script builds a **complete new tree** without `base_tree`. Adding it causes deleted files to silently persist on GitHub. See `GITHUB_PUSH.md`.

---

## App Pages

### User App (`/`)

| Path | Page |
|---|---|
| `/` | Market Dashboard |
| `/trading` | Chart Studio |
| `/sectors` | Market Sectors + rotation |
| `/stocks` | Stock Lookup |
| `/patterns` | Candlestick pattern detection |
| `/scanners` | Custom stock scanners |
| `/hydra` | AI Analyzer (NLP) |
| `/options` | Options Strategy Tester |
| `/news` | Market News Feed |
| `/settings` | App Settings |

### Admin Dashboard (`/admin/`)

| Path | Page |
|---|---|
| `/admin/` | App Status (uptime, health) |
| `/admin/users` | Clerk user list |
| `/admin/whatsapp` | WhatsApp Bot simulator |
| `/admin/telegram` | Telegram Bot management |
| `/admin/logs` | Backend log viewer |

---

## Key Commands

```bash
# Push to GitHub
pnpm --filter @workspace/scripts run push-github

# Health checks (Replit dev)
curl http://localhost:8090/api/healthz      # Python backend direct
curl http://localhost:3002/api/healthz      # Via user Vite proxy

# Docker (local machine)
docker compose up --build -d               # Build and start everything
docker compose down                        # Stop
curl http://localhost/api/healthz          # App health via nginx
docker compose logs -f backend             # Backend logs
docker compose logs -f frontend            # nginx logs
```

---

## Important Rules

- **Auth**: Clerk for user app; username/password + session token for admin — NEVER cross them
- **python-backend routes**: all registered in `main.py` with `prefix="/api"`
- **yfinance**: ALWAYS `yf.Ticker().history()` — NEVER `yf.download()` (not thread-safe)
- **pandas_ta**: NEVER pip install — use local shim; NEVER add to SKIP_DIRS
- **Router**: wouter — NEVER import from `react-router`
- **Docker base image**: `node:24-slim` (Debian/glibc) — NEVER alpine (musl breaks rollup)
- **Docker**: always `docker compose up --build` after any change
- **api-server artifact**: ROUTING SHIM ONLY — never start its workflow, never edit source
- **configureWorkflow()**: PROHIBITED on artifact-managed workflows — use `verifyAndReplaceArtifactToml()`
- **artifact.toml edits**: copy → edit → `verifyAndReplaceArtifactToml()` (temp file must be in `/home/runner/workspace/`, NOT `/tmp/`)
- **UI**: always Tailwind `dark:` variants — never bare inline hex colors
- **base_tree**: NEVER add to GitHub trees API call in push script
- **WhatsApp/Telegram bot pages**: ONLY in admin dashboard — removed from user app

---

## Debugging Guide

### API 502 on Replit
1. `curl http://localhost:8090/api/healthz` — if fails → restart `Python Backend` workflow
2. Check `artifacts/api-server/.replit-artifact/artifact.toml`: `localPort = 8090`, `paths = ["/api"]`
3. Never start `artifacts/api-server: API Server` workflow

### Admin dashboard blank on Replit
1. `artifacts/admin-dashboard: web` must be RUNNING
2. Check `artifacts/admin-dashboard/.replit-artifact/artifact.toml`: `localPort = 22133`, paths includes `/admin`

### Admin login: "ADMIN_PASSWORD not configured"
- Set `ADMIN_PASSWORD` secret in Replit Secrets tab (or `.env` for Docker)
- Restart Python Backend workflow

### Docker build fails: rollup/musl error
- Frontend Dockerfile must use `node:24-slim` — never alpine

### Docker build fails: pandas_ta not found
- Backend Dockerfile must have `ENV PYTHONPATH=/app`

### Frontend changes not visible in Docker
- Run `docker compose up --build -d` — `--build` is mandatory

---

## Incident RCA Log (April 2026)

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | Wrong package filter in workflow | Auto-generated with `nestjs-backend-placeholder` | Use `verifyAndReplaceArtifactToml()` |
| 2 | `configureWorkflow()` throws PROHIBITED_ACTION | Artifact-managed workflows | Use `verifyAndReplaceArtifactToml()` instead |
| 3 | Port 3002 conflict | Two workflows bound to same port | Make `Start application` a no-op |
| 4 | API 502 | `api-server` artifact had `localPort = 8080` | Change to `localPort = 8090` |
| 5 | Rollup musl error in Docker | `node:24-alpine` used | Change to `node:24-slim` |
| 6 | pandas_ta not found in Docker | `SKIP_DIRS` had `pandas_ta` in push script | Removed from SKIP_DIRS |
| 7 | setuptools.backends error | pyproject.toml used new syntax | Changed to `setuptools.build_meta` |
| 8 | pandas_ta still missing | Switched to `pip install -e ./pandas_ta/` (fragile) | Use `ENV PYTHONPATH=/app` instead |
| 9 | Docker spaCy re-downloads on every build | spaCy download placed after `COPY . .` | Moved before `COPY . .` |
| 10 | Unnecessary `COPY lib/` in frontend Dockerfile | frontend has no workspace:* deps | Removed |
