# Indian Stock Market Analyzer — Full Setup Guide

This document covers everything needed to get **both apps** running from scratch — locally with Docker or on Replit.

---

## What You Get

| App | URL | Auth |
|---|---|---|
| **User Stock Market App** | `http://localhost/` | Clerk (Google OAuth + email) |
| **Admin Dashboard** | `http://localhost/admin/` | Username + password (no Clerk) |
| **API (backend)** | `http://localhost/api/` | JWT (user) or session token (admin) |
| **API Docs** | `http://localhost:8090/docs` | Open (dev only) |

---

## Architecture

```
Browser
  └─► nginx:80  (frontend container)
        ├─ /api/*    → proxy → FastAPI:8090  (backend container)
        ├─ /admin/   → Admin Dashboard static files (built React app)
        └─ /         → User App static files (built React app)
```

---

## Local Setup with Docker

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)
- [Git](https://git-scm.com/)

### Step 1 — Clone the repo

```bash
git clone https://github.com/n4nirmalyapratap/indian-stock-market-analyzer
cd indian-stock-market-analyzer
```

### Step 2 — Create your `.env` file

```bash
cp .env.example .env
```

Then edit `.env` with your real values:

| Variable | Required | Where to get it |
|---|---|---|
| `CLERK_PUBLISHABLE_KEY` | Yes | [Clerk dashboard](https://dashboard.clerk.com) → API Keys |
| `CLERK_SECRET_KEY` | Yes | Same Clerk dashboard page |
| `VITE_CLERK_PUBLISHABLE_KEY` | Yes | Same as `CLERK_PUBLISHABLE_KEY` |
| `ADMIN_USERNAME` | Yes | Your choice (default: `admin`) |
| `ADMIN_PASSWORD` | Yes | Your choice — make it strong |
| `TELEGRAM_BOT_TOKEN` | No | @BotFather on Telegram |
| `TWILIO_ACCOUNT_SID` | No | Twilio console |
| `TWILIO_AUTH_TOKEN` | No | Twilio console |

### Step 3 — Build and start

```bash
docker compose up --build -d
```

> **Always use `--build`**. Without it Docker reuses cached images and your code changes don't take effect.

### Step 4 — Verify

```bash
# API health check
curl http://localhost/api/healthz

# Expected response:
# {"status": "ok"}
```

Then open:
- User app: **http://localhost**
- Admin panel: **http://localhost/admin**

### Updating (after git pull)

```bash
git pull
docker compose up --build -d
```

### Stop everything

```bash
docker compose down
```

### View logs

```bash
docker compose logs -f           # all containers
docker compose logs -f backend   # Python only
docker compose logs -f frontend  # nginx only
```

---

## Admin Panel Login

URL: `http://localhost/admin`

Default credentials set in your `.env`:
```
Username: admin
Password: (whatever you set as ADMIN_PASSWORD)
```

**Admin panel features:**
- App Status — uptime, Python version, endpoint count, bot status
- Users — all Clerk-registered users (requires `CLERK_SECRET_KEY`)
- WhatsApp Bot — test bot commands
- Telegram Bot — bot status, test messages, message log
- Logs — backend log viewer

---

## Replit Setup

### First time on Replit

1. **Open the Auth pane** in the Replit toolbar to configure Clerk (Google OAuth + email sign-in)
2. **Set secrets** in the Replit Secrets tab:

| Secret | Value |
|---|---|
| `CLERK_PUBLISHABLE_KEY` | From Clerk dashboard |
| `CLERK_SECRET_KEY` | From Clerk dashboard |
| `VITE_CLERK_PUBLISHABLE_KEY` | Same as publishable key |
| `ADMIN_USERNAME` | `admin` |
| `ADMIN_PASSWORD` | Your chosen password |
| `TELEGRAM_BOT_TOKEN` | Optional |

3. **Start workflows** (they auto-start, but if stopped):
   - `Python Backend` → starts FastAPI on port 8090
   - `artifacts/stock-market-app: web` → starts Vite dev server on port 3002
   - `artifacts/admin-dashboard: web` → starts Vite dev server on port 22133

4. **Never start** `artifacts/api-server: API Server` — it's a routing shim only.

### Replit URL routing

| Path | Goes to | How |
|---|---|---|
| `/api/*` | Port 8090 (Python) | `api-server` artifact.toml |
| `/admin/*` | Port 22133 (admin Vite) | `admin-dashboard` artifact.toml |
| `/*` | Port 3002 (user Vite) | `stock-market-app` artifact.toml |

### Push to GitHub (from Replit)

```bash
pnpm --filter @workspace/scripts run push-github
```

---

## Project Structure

```
/
├── artifacts/
│   ├── python-backend/           Python FastAPI backend
│   │   ├── main.py               App entry, all routers registered
│   │   ├── run.py                Startup script + spaCy self-heal
│   │   ├── requirements.txt      Python dependencies
│   │   ├── Dockerfile            Production image (python:3.11-slim)
│   │   ├── pandas_ta/            LOCAL shim — NOT from PyPI (see below)
│   │   └── app/
│   │       ├── middleware/
│   │       │   └── clerk_auth.py Clerk JWT verification + admin token passthrough
│   │       └── routes/
│   │           ├── admin.py      Admin API: /api/admin/* (session-token protected)
│   │           ├── whatsapp.py   WhatsApp bot routes
│   │           ├── telegram.py   Telegram bot + polling
│   │           └── ...           Other domain routes
│   │
│   ├── stock-market-app/         User React/Vite app (Clerk auth)
│   │   ├── Dockerfile            Builds BOTH frontends + nginx
│   │   ├── nginx.conf            Routes /api, /admin, / in production
│   │   └── src/
│   │       ├── App.tsx           Main app shell + Clerk + sidebar
│   │       └── lib/api.ts        API client (auto-attaches Clerk JWT)
│   │
│   ├── admin-dashboard/          Admin React/Vite app (username/password)
│   │   └── src/
│   │       ├── App.tsx           Admin shell (no Clerk)
│   │       ├── pages/LoginPage.tsx  Username/password login form
│   │       ├── pages/AppStatus.tsx  Backend health + uptime
│   │       ├── pages/UsersPage.tsx  Clerk user list
│   │       ├── pages/WhatsAppBot.tsx Bot simulator
│   │       ├── pages/TelegramBot.tsx Bot management
│   │       ├── pages/LogsPage.tsx   Log viewer
│   │       └── lib/api.ts           API client (sends X-Admin-Token header)
│   │
│   ├── api-server/               ROUTING SHIM ONLY — do not touch
│   └── mockup-sandbox/           Canvas design tool — do not touch
│
├── docker-compose.yml            Orchestrates backend + frontend
├── .env.example                  Template for .env
├── SETUP.md                      This file
└── replit.md                     Agent memory / architecture notes
```

---

## Authentication Architecture

### User App (main app at `/`)

```
Browser → Clerk sign-in → gets JWT token
  → all API calls include: Authorization: Bearer <clerk-jwt>
  → Python middleware verifies JWT against Clerk JWKS
```

### Admin Dashboard (at `/admin/`)

```
Browser → Username/password form → POST /api/admin/login
  → Python returns session token (random hex, 8h TTL)
  → all API calls include: X-Admin-Token: <session-token>
  → Python checks token against in-memory session store
  → Admin token also bypasses Clerk auth for non-admin endpoints
    (so admin can access /api/whatsapp/*, /api/telegram/*, etc.)
```

### Isolation

- `/api/admin/*` endpoints: **never reachable** with a Clerk token — they only respond to admin session tokens
- Regular Clerk users: **cannot access** any admin API even with a valid JWT

---

## Key Technical Notes

### pandas_ta — local shim

`pandas-ta` from PyPI is broken on Python 3.11+. This project uses a custom shim at `artifacts/python-backend/pandas_ta/` that wraps the `ta` library.

**Never** `pip install pandas_ta`. **Never** add it to `requirements.txt`.

### yfinance

Always use `yf.Ticker(symbol).history()`. **Never** `yf.download()` — it is not thread-safe.

### Docker build always requires `--build`

`pnpm-lock.yaml` is not committed (excluded from push script). Docker's cache cannot skip the `pnpm install` step if the lockfile is missing — always pass `--build`.

### spaCy model is pre-baked into the Docker image

The `en_core_web_sm` model is downloaded at Docker build time (before `COPY . .` so it's a separate cached layer). First Replit start auto-downloads it via `run.py` self-heal.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `curl localhost/api/healthz` → connection refused | Backend container not healthy yet | Wait 20–30s or check `docker compose logs backend` |
| `curl localhost/api/healthz` → 401 | Clerk key missing or wrong | Check `CLERK_PUBLISHABLE_KEY` in `.env` |
| Admin login → "ADMIN_PASSWORD not configured" | Missing env var | Set `ADMIN_PASSWORD` in `.env` |
| `/admin` shows blank or 404 | nginx config or build issue | Check `docker compose logs frontend` |
| Build fails: rollup musl error | Wrong Docker base image | Dockerfile must use `node:24-slim` not alpine |
| Build fails: pandas_ta not found | PYTHONPATH not set | Backend Dockerfile must have `ENV PYTHONPATH=/app` |
| Frontend changes not applied | `--build` flag missing | Run `docker compose up --build -d` |
| Telegram bot not polling | Token missing | Set `TELEGRAM_BOT_TOKEN` in `.env` |
