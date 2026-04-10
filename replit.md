# Indian Stock Market Analyzer — Agent Memory

## Overview

A real-time Indian stock market analysis platform with sector rotation tracking,
candlestick pattern detection, custom stock scanners, NLP-powered queries, a
Telegram bot, and a WhatsApp bot — powered by a **Python FastAPI backend** and
a **React/Vite frontend**.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 · FastAPI · uvicorn |
| Data sources | NSE India API · Yahoo Finance (`yfinance`) |
| NLP | spaCy 3.8 (rule-based EntityRuler) |
| Analytics | pandas · numpy · scipy |
| Technical indicators | `ta` library via local `pandas_ta/` shim |
| Frontend | React 19 · Vite · TypeScript · TailwindCSS · TanStack Query |
| Router | wouter (NOT react-router) |
| UI | shadcn/ui |
| Monorepo | pnpm workspaces (Node.js 24) |
| Auth | Clerk (Google OAuth + email) — `@clerk/react` frontend · JWT verification in Python |
| Deployment | Docker (two-container: nginx frontend + Python backend) |

---

## Project Structure

```
/
├── artifacts/
│   ├── python-backend/          ← ACTIVE: FastAPI backend (port 8090)
│   │   ├── main.py              ← App entry point, all routers registered
│   │   ├── run.py               ← Startup script + spaCy model self-heal
│   │   ├── requirements.txt     ← Python dependencies (includes feedparser)
│   │   ├── Dockerfile           ← Production Docker image (python:3.11-slim)
│   │   ├── pandas_ta/           ← LOCAL SHIM — NOT a PyPI package (see below)
│   │   │   ├── __init__.py      ← Wraps `ta` library with pandas-ta API
│   │   │   └── pyproject.toml   ← Allows optional pip install if needed
│   │   └── app/
│   │       ├── routes/          ← FastAPI route modules
│   │       └── services/        ← Business logic + indicators.py
│   │
│   ├── stock-market-app/        ← ACTIVE: React/Vite frontend (port 3002 on Replit)
│   │   ├── .replit-artifact/artifact.toml
│   │   ├── Dockerfile           ← Production Docker image (node:24-slim + nginx:alpine)
│   │   ├── nginx.conf           ← Serves SPA + proxies /api/* → backend container
│   │   └── vite.config.ts       ← Dev: proxies /api/* → localhost:8090
│   │
│   ├── api-server/              ← ROUTING SHIM ONLY — do NOT touch or start
│   │   └── .replit-artifact/artifact.toml
│   │       ← localPort=8090, paths=["/api"]
│   │       ← Tells Replit proxy: route /api/* → Python backend on port 8090
│   │       ← Source code inside is unused; only artifact.toml matters
│   │
│   └── mockup-sandbox/          ← Canvas design tool (do not touch)
│
├── docker-compose.yml           ← Orchestrates backend + frontend containers
├── .dockerignore                ← Excludes node_modules, caches, deprecated folders
├── scripts/
│   └── src/push-github.ts      ← GitHub push via Replit connector (no PAT needed)
├── lib/                         ← Shared TypeScript libraries
├── README.md                    ← Developer-facing docs
└── GITHUB_PUSH.md               ← Push script documentation
```

### ⚠️ Deleted Directories (do NOT recreate)

| Directory | Reason removed |
|---|---|
| `artifacts/nestjs-backend/` | Deprecated Node.js/NestJS backend — replaced by Python |
| `artifacts/nestjs-backend-placeholder/` | Old placeholder — replaced by `stock-market-app/` |

---

## Workflows (Replit — Active)

| Workflow name | Command | Port | State |
|---|---|---|---|
| `Python Backend` | `bash -c 'cd /home/runner/workspace/artifacts/python-backend && PORT=8090 python run.py'` | 8090 | RUNNING |
| `artifacts/stock-market-app: web` | `BASE_PATH=/ PORT=3002 pnpm --filter @workspace/stock-market-app run dev` | 3002 | RUNNING |
| `artifacts/api-server: API Server` | routing shim echo only — intentionally NOT_STARTED | 8090 routing | NOT_STARTED |

---

## ⚠️ Critical: Two-Layer Proxy Architecture (Replit only)

### Layer 1 — Replit Proxy (outermost, browser-facing)

| URL path | Routes to port | Controlled by |
|---|---|---|
| `/api/*` | **8090** | `artifacts/api-server/.replit-artifact/artifact.toml` |
| `/*` | **3002** | `artifacts/stock-market-app/.replit-artifact/artifact.toml` |

### Layer 2 — Vite Dev Server Proxy (internal only)

```js
proxy: { "/api": { target: "http://localhost:8090" } }
```
Only applies when hitting Vite directly (e.g. `curl localhost:3002/api/...`).
**Bypassed entirely when the browser accesses through the Replit proxy.**

### In Docker (no Replit proxy)

nginx handles both layers in one config:
```nginx
location /api/ { proxy_pass http://backend:8090; }
location /     { try_files $uri /index.html; }
```

---

## Docker Deployment

### Architecture

```
Browser → http://localhost
    → nginx (port 80)
        → /api/* → Python FastAPI backend (port 8090, internal)
        → /*     → React SPA (static HTML/JS/CSS)
```

### Quick start

```bash
git clone https://github.com/n4nirmalyapratap/indian-stock-market-analyzer
cd indian-stock-market-analyzer
docker compose up --build
```

App: **http://localhost**
API health: **http://localhost/api/healthz**
API docs: **http://localhost:8090/docs**

### Always use `--build` after `git pull`

```bash
git pull
docker compose up --build     # ← --build is REQUIRED to rebuild images
```

Without `--build`, Docker reuses cached images and changes don't take effect.

### Key Docker files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Orchestrates backend + frontend; healthcheck; env vars |
| `artifacts/python-backend/Dockerfile` | python:3.11-slim; pip install; spaCy model baked in |
| `artifacts/stock-market-app/Dockerfile` | node:24-slim builder → nginx:alpine; two-stage build |
| `artifacts/stock-market-app/nginx.conf` | SPA fallback + /api/* proxy + gzip + security headers |
| `.dockerignore` | Excludes node_modules, __pycache__, market_cache, runtime DBs |

### Environment variables

| Variable | Default in Docker | Description |
|---|---|---|
| `SESSION_SECRET` | `changeme-in-production` | Session signing key — set for real prod |
| `PORT` | `8090` | Python backend listen port |
| `TELEGRAM_BOT_TOKEN` | (unset) | Optional — enables Telegram polling |
| `TWILIO_ACCOUNT_SID` | (unset) | Optional — enables WhatsApp webhook |
| `TWILIO_AUTH_TOKEN` | (unset) | Optional — enables WhatsApp webhook |

Pass via `.env` file at repo root — Docker Compose picks it up automatically.

---

## pandas_ta — Local Package Shim

`pandas-ta` is not installable on Python 3.11+ via PyPI (the PyPI package is unmaintained).
This project uses a custom shim at `artifacts/python-backend/pandas_ta/`.

### How it works

- `pandas_ta/__init__.py` wraps the `ta` library with the same function signatures
- Provides: `ema()`, `sma()`, `rsi()`, `macd()`, `bbands()`, `atr()`
- Both `run.py` and `app/services/indicators.py` add `/app/` to `sys.path` at startup
- The backend `Dockerfile` also sets `ENV PYTHONPATH=/app` as belt-and-suspenders

### Rules

- **Never** `pip install pandas-ta` or `pip install pandas_ta` from PyPI
- **Never** add `pandas_ta` to `requirements.txt`
- **Never** add `pandas_ta` back to `SKIP_DIRS` in `scripts/src/push-github.ts`
- The `pandas_ta/pyproject.toml` exists for optional pip editable install — the Docker build does NOT use it (PYTHONPATH is sufficient)

---

## GitHub Push Script

```bash
pnpm --filter @workspace/scripts run push-github
```

### What is skipped (never pushed)

| Category | Items |
|---|---|
| Directories | `node_modules`, `dist`, `build`, `__pycache__`, `.pythonlibs`, `market_cache`, `.git`, `.agents`, `.local` |
| Files | `pnpm-lock.yaml`, `hydra_prices.db`, `.DS_Store`, `.tsbuildinfo` |
| Extensions | `.png`, `.jpg`, `.gif`, `.webp`, `.ico`, `.woff`, `.ttf`, `.mp4`, `.pdf`, `.zip`, `.pyc` |

**`pandas_ta/` is included in pushes** (was incorrectly skipped as "vendored shim" — fixed April 2026).

### ⚠️ Never add `base_tree` to the Git trees API call

The push script builds a **complete new tree** without `base_tree`. If `base_tree` is added, deleted files silently persist on GitHub forever. See `GITHUB_PUSH.md` for full explanation.

---

## Full Incident RCA — "App Not Starting / API 502" (April 2026)

### Step 1 — Artifact auto-registered with wrong package filter
`artifacts/stock-market-app: web` workflow auto-generated with `--filter nestjs-backend-placeholder`.
Fix: use `verifyAndReplaceArtifactToml()` to update `artifact.toml`.

### Step 2 — `configureWorkflow()` cannot override artifact-managed workflows
Throws `PROHIBITED_ACTION`. Must use `verifyAndReplaceArtifactToml()` instead.

### Step 3 — `artifact.toml` cannot be edited directly
Must copy → edit temp file inside workspace (NOT `/tmp`) → `verifyAndReplaceArtifactToml()`.

### Step 4 — Port 3002 conflict
Two workflows bound to same port. Resolution: make `Start application` a no-op, restart it, then restart `artifacts/stock-market-app: web`.

### Step 5 — API returning 502
`api-server` artifact had `localPort = 8080`. Replit proxy forwarded `/api/*` to port 8080 where nothing ran. Fix: change to `localPort = 8090`.

---

## Docker Bug Fix History (April 2026)

All these were fixed in a single session — documented here so they are never repeated.

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | `Cannot find module @rollup/rollup-linux-x64-musl` | Frontend Dockerfile used `node:24-alpine` (musl). pnpm-workspace.yaml excludes musl rollup binary. | Changed builder to `node:24-slim` (Debian/glibc). |
| 2 | `ModuleNotFoundError: No module named 'pandas_ta'` | `pandas_ta/` directory was in push script `SKIP_DIRS` — never reached GitHub. Users who cloned the repo had an empty `python-backend/` with no shim. | Removed `"pandas_ta"` from `SKIP_DIRS` in `push-github.ts`. |
| 3 | `No module named 'setuptools.backends'` | `pyproject.toml` used `setuptools.backends.legacy:build` (setuptools 68+ syntax) but Docker image ships with older pip/setuptools. | Changed to `setuptools.build_meta` (supported since setuptools 40+). |
| 4 | `ModuleNotFoundError: No module named 'pandas_ta'` (again, even after fix #2) | Switched to `pip install -e ./pandas_ta/` approach with a separate `COPY pandas_ta/` step, which introduced new fragility. Unnecessary — the code already has `sys.path.insert` in `run.py` and `indicators.py`. | Removed the separate COPY and pip install entirely. Set `ENV PYTHONPATH=/app`. `COPY . .` includes `pandas_ta/` naturally. |
| 5 | Docker layer cache invalidated on every source change | spaCy model download was placed after `COPY . .` — so every code change triggered a 60–90s re-download. | Moved spaCy download before `COPY . .`. Order: apt-get → pip install → spaCy → source. |
| 6 | Unnecessary `COPY lib/ ./lib/` in frontend Dockerfile | Frontend has zero workspace dependencies on `lib/*` packages (verified). Wasted build time and a potential failure point. | Removed `COPY lib/ ./lib/`. |

---

## Debugging Guide

### API 502 on Replit

1. `curl http://localhost:8090/api/healthz` — if fails → Python backend is down → restart `Python Backend` workflow
2. Check `artifacts/api-server/.replit-artifact/artifact.toml`:
   - `localPort` must be `8090`
   - `paths` must be `["/api"]`
3. Never start `artifacts/api-server: API Server` workflow

### Frontend not showing on Replit

1. `artifacts/stock-market-app: web` must be RUNNING
2. If FINISHED: another workflow holds port 3002 → reconfigure `Start application` to no-op
3. If wrong package filter: fix via `verifyAndReplaceArtifactToml()`

### Docker not working locally

1. Always use `docker compose up --build` after any `git pull`
2. If build fails with rollup error → wrong base image (must be `node:24-slim`, not alpine)
3. If `pandas_ta` not found → check `PYTHONPATH=/app` is in backend Dockerfile
4. If frontend build fails with tsconfig error → `tsconfig.base.json` must be present at workspace root

---

## App Pages

| Path | Page |
|---|---|
| `/` | Market Dashboard |
| `/trading` | Chart Studio |
| `/sectors` | Market Sectors & rotation |
| `/stocks` | Stock Lookup |
| `/patterns` | Candlestick pattern detection |
| `/scanners` | Custom stock scanners |
| `/hydra` | AI Analyzer (NLP queries) |
| `/options` | Options Strategy Tester |
| `/news` | Market News Feed |
| `/settings` | Settings (WhatsApp/Telegram bot config) |

---

## Key Commands

```bash
# Push to GitHub
pnpm --filter @workspace/scripts run push-github

# Health checks (Replit)
curl http://localhost:8090/api/healthz      # Python backend direct
curl http://localhost:3002/api/healthz      # Via Vite proxy

# Docker (local machine)
docker compose up --build                  # Build and run everything
docker compose down                        # Stop
curl http://localhost/api/healthz          # App health via nginx
```

---

## Important Rules

- Python backend: use `python` (Replit uses `python3.11` in the workflow command explicitly)
- yfinance: **ALWAYS** use `yf.Ticker(ticker).history()` — NEVER `yf.download()` (not thread-safe)
- All NSE stock symbols need `.NS` suffix (e.g., `RELIANCE.NS`)
- spaCy model auto-downloads via `run.py` self-heal block on first Replit start; pre-baked into Docker image
- `vite.config.ts` requires both `PORT` and `BASE_PATH` env vars or it throws at startup
- **NEVER** `pip install pandas_ta` — use the local shim
- **NEVER** add `pandas_ta` back to `SKIP_DIRS` in push script
- **NEVER** use `base_tree` in the GitHub trees API call (see GITHUB_PUSH.md)
- **NEVER** touch `artifacts/api-server/` source code — routing shim only
- **NEVER** use `configureWorkflow()` on artifact-managed workflows
- `artifact.toml` edits: copy → edit → `verifyAndReplaceArtifactToml()` (temp file must be in `/home/runner/workspace/`, not `/tmp/`)
- UI: always use Tailwind `dark:` variants — never bare inline hex styles for surfaces or text
- Router is `wouter` — NEVER import from `react-router`
