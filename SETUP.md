# Indian Stock Market Analyzer — Full Setup Guide

Everything needed to get both apps running — locally with Docker, or on Replit.

---

## What You Get

| App | URL | Auth |
|---|---|---|
| **User Stock App** | `http://localhost/` | Email + password · Google OAuth (Clerk, optional) |
| **Admin Dashboard** | `http://localhost/admin/` | Username + password |
| **API (backend)** | `http://localhost/api/` | JWT (user) · session token (admin) |
| **API Docs** | `http://localhost:8090/docs` | Open (dev only) |

---

## Architecture

```
Browser
  └─► nginx:80  (frontend container)
        ├─ /api/*    → proxy → FastAPI:8090  (backend container)
        ├─ /admin/   → Admin Dashboard static files
        └─ /         → User App static files
```

---

## Docker Setup (recommended for production)

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Compose)
- [Git](https://git-scm.com/)

### Step 1 — Clone

```bash
git clone https://github.com/n4nirmalyapratap/indian-stock-market-analyzer
cd indian-stock-market-analyzer
```

### Step 2 — Create your `.env` file

```bash
cp .env.example .env
```

Edit `.env` and fill in the values below.

#### Required variables

| Variable | What it does |
|---|---|
| `SESSION_SECRET` | Signs JWT tokens for email+password logins. Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_USERNAME` | Admin panel login username (default: `admin`) |
| `ADMIN_PASSWORD` | Admin panel login password — **make it strong** |

#### Optional — Clerk (enables Google OAuth)

If you skip Clerk, the user app works with email + password only. Add these to also enable "Continue with Google":

| Variable | Where to get it |
|---|---|
| `CLERK_PUBLISHABLE_KEY` | [Clerk dashboard](https://dashboard.clerk.com) → API Keys |
| `CLERK_SECRET_KEY` | Same page — needed for the admin "Google Users" tab |
| `VITE_CLERK_PUBLISHABLE_KEY` | Same value as `CLERK_PUBLISHABLE_KEY` |

#### Optional — Bot integrations

| Variable | What it does |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Enable Telegram bot (from @BotFather) |
| `TWILIO_ACCOUNT_SID` | Enable WhatsApp bot via Twilio |
| `TWILIO_AUTH_TOKEN` | Twilio auth |

### Step 3 — Build and start

```bash
docker compose up --build -d
```

> **Always use `--build`.** Without it Docker reuses a stale image and your code changes don't apply.

### Step 4 — Verify

```bash
curl http://localhost/api/healthz
# Expected: {"status": "ok"}
```

Open:
- User app: **http://localhost**
- Admin panel: **http://localhost/admin**

### Day-to-day commands

```bash
# Update after git pull
git pull && docker compose up --build -d

# Stop everything (keeps data)
docker compose down

# Stop and delete all data including user accounts
docker compose down -v

# Live logs
docker compose logs -f           # all containers
docker compose logs -f backend   # Python only
docker compose logs -f frontend  # nginx only
```

### Data persistence

User accounts (email + password) are stored in SQLite and kept in a named Docker volume (`userdata`). The database survives:
- `docker compose down` / `up --build` — **data is kept**
- `docker compose down -v` — **data is deleted** (use only for a clean reset)

---

## Admin Panel

URL: `http://localhost/admin`

Login with the credentials from your `.env` (`ADMIN_USERNAME` / `ADMIN_PASSWORD`).

### Features

| Page | What you can do |
|---|---|
| **App Status** | Backend uptime, Python version, endpoint count, bot connectivity |
| **Users → App Users** | List all email+password accounts · Add new user · Delete user |
| **Users → Google Users** | List all Clerk/Google sign-in users (requires `CLERK_SECRET_KEY`) |
| **Logs** | Live structured backend logs (AWS CloudWatch style) — filter by level, search, auto-refresh |
| **WhatsApp Bot** | Test bot commands, view message history |
| **Telegram Bot** | Bot status, test messages, message log |

### Add User (from admin)

Go to **Users → App Users → Add User**. Enter name, email, and password (min 6 chars). The user can immediately sign in on the main app.

---

## Replit Setup

### First time

1. Set secrets in the Replit Secrets tab:

| Secret | Value |
|---|---|
| `SESSION_SECRET` | Long random string — `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_USERNAME` | `admin` |
| `ADMIN_PASSWORD` | Your chosen password |
| `CLERK_PUBLISHABLE_KEY` | From Clerk dashboard (optional) |
| `CLERK_SECRET_KEY` | From Clerk dashboard (optional) |
| `VITE_CLERK_PUBLISHABLE_KEY` | Same as publishable key (optional) |
| `TELEGRAM_BOT_TOKEN` | Optional |

2. Workflows start automatically. If stopped, restart:
   - `Python Backend` → FastAPI on port 8090
   - `artifacts/stock-market-app: web` → user Vite on port 3002
   - `artifacts/admin-dashboard: web` → admin Vite on port 22133

3. **Never start** `artifacts/api-server` — routing shim only.

### Replit URL routing

| Path | Goes to |
|---|---|
| `/api/*` | Port 8090 (Python backend) |
| `/admin/*` | Port 22133 (admin Vite dev server) |
| `/*` | Port 3002 (user Vite dev server) |

### Push to GitHub

```bash
pnpm --filter @workspace/scripts run push-github
```

---

## Authentication Architecture

### User App (`/`)

Two methods work side by side:

**Email + Password (always available)**
```
User registers / logs in → POST /api/auth/register or /api/auth/login
  → Python returns HS256 JWT (signed with SESSION_SECRET, 30-day expiry)
  → Token stored in localStorage
  → All API calls: Authorization: Bearer <jwt>
  → Python middleware verifies HS256 signature first
```

**Google OAuth via Clerk (optional)**
```
User clicks "Continue with Google" → Clerk OAuth flow
  → Browser gets Clerk RS256 JWT
  → All API calls: Authorization: Bearer <clerk-jwt>
  → Python middleware verifies against Clerk JWKS (falls back if HS256 fails)
```

### Admin Dashboard (`/admin/`)

```
Admin enters username + password → POST /api/admin/login
  → Python returns session token (random hex, 8-hour TTL, stored in memory)
  → All API calls: X-Admin-Token: <session-token>
  → Python checks token against in-memory session map
```

### Security isolation

- `/api/admin/*` endpoints **only** accept admin session tokens — Clerk JWTs and custom JWTs cannot access them
- `/api/auth/*` endpoints are public (no auth needed) — registration and login
- All other `/api/*` endpoints require a valid user JWT (Clerk RS256 or custom HS256)

---

## Project Structure

```
/
├── artifacts/
│   ├── python-backend/             Python FastAPI backend
│   │   ├── main.py                 App entry — all routers registered here
│   │   ├── run.py                  Startup: spaCy self-heal + log buffer setup
│   │   ├── requirements.txt        Python dependencies
│   │   ├── Dockerfile              Production image (python:3.11-slim)
│   │   ├── pandas_ta/              LOCAL shim — wraps `ta` lib, NOT from PyPI
│   │   └── app/
│   │       ├── middleware/
│   │       │   └── clerk_auth.py   JWT middleware — accepts HS256 or Clerk RS256
│   │       ├── services/
│   │       │   └── log_buffer.py   In-memory ring buffer (2000 log records)
│   │       └── routes/
│   │           ├── admin.py        /api/admin/* — session-token protected
│   │           ├── auth.py         /api/auth/register + login — public
│   │           ├── whatsapp.py     WhatsApp bot
│   │           ├── telegram.py     Telegram bot + polling
│   │           └── ...             Other domain routes (stocks, sectors, etc.)
│   │
│   ├── stock-market-app/           User-facing React/Vite app
│   │   ├── Dockerfile              Builds BOTH frontends + nginx (3-stage)
│   │   ├── nginx.conf              Routes /api, /admin, / in production
│   │   └── src/
│   │       ├── App.tsx             App shell, sidebar, Clerk + custom auth
│   │       ├── context/
│   │       │   └── CustomAuthContext.tsx  Email+password auth state
│   │       ├── pages/
│   │       │   ├── LoginPage.tsx   Sign In / Register (email+password + Google)
│   │       │   ├── SettingsPage.tsx User profile, preferences, sign out
│   │       │   └── ...             Dashboard, ChartView, Sectors, etc.
│   │       └── lib/api.ts          API client — attaches JWT automatically
│   │
│   ├── admin-dashboard/            Admin-only React/Vite app
│   │   └── src/
│   │       ├── App.tsx             Admin shell, session management
│   │       ├── pages/
│   │       │   ├── LoginPage.tsx   Username + password form
│   │       │   ├── AppStatus.tsx   Backend health, uptime, config
│   │       │   ├── UsersPage.tsx   App Users + Google Users tabs, Add/Delete
│   │       │   ├── LogsPage.tsx    AWS CloudWatch-style log viewer
│   │       │   ├── WhatsAppBot.tsx WhatsApp bot console
│   │       │   └── TelegramBot.tsx Telegram bot management
│   │       └── lib/api.ts          Admin API client (X-Admin-Token header)
│   │
│   ├── api-server/                 ROUTING SHIM ONLY — do not modify
│   └── mockup-sandbox/             Canvas design tool — do not modify
│
├── docker-compose.yml              Orchestrates backend + frontend
├── .env.example                    Template for .env
├── SETUP.md                        This file
└── replit.md                       Agent memory / architecture notes
```

---

## API Endpoints Reference

### Public (no auth)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/healthz` | Health check |
| `POST` | `/api/auth/register` | Create email+password account |
| `POST` | `/api/auth/login` | Sign in with email+password |
| `POST` | `/api/admin/login` | Admin panel sign in |

### User endpoints (JWT required)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/stocks/{symbol}` | Stock quote + metadata |
| `GET` | `/api/stocks/{symbol}/history` | Price history |
| `GET` | `/api/sectors/rotation` | Sector rotation analysis |
| `GET` | `/api/patterns` | Candlestick pattern scan |
| `GET` | `/api/news/feed` | Market news feed |
| `POST` | `/api/hydra/analyze` | NLP stock query |
| … | … | (see `/api/docs` for full list) |

### Admin endpoints (X-Admin-Token required)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/admin/status` | Backend health + uptime |
| `GET` | `/api/admin/users` | List Clerk/Google users |
| `GET` | `/api/admin/users/app` | List email+password users |
| `POST` | `/api/admin/users/create` | Create email+password user |
| `DELETE` | `/api/admin/users/app/{id}` | Delete email+password user |
| `GET` | `/api/admin/logs` | Structured backend logs (ring buffer) |

---

## Key Technical Notes

### pandas_ta — local shim

`pandas-ta` from PyPI is broken on Python 3.11+. The project uses a hand-written shim at `artifacts/python-backend/pandas_ta/` that wraps the `ta` library.

**Never** `pip install pandas_ta`. **Never** add it to `requirements.txt`. **Never** add `pandas_ta/` to any skip/ignore list.

### yfinance

Always use `yf.Ticker(symbol).history()`. **Never** `yf.download()` — it is not thread-safe in a multi-request server.

### Docker build always requires `--build`

`pnpm-lock.yaml` is not committed (excluded from the push script). Docker cannot cache-skip `pnpm install` without it. Always pass `--build`.

### spaCy model

The `en_core_web_sm` model is downloaded inside the Docker image at build time (as a separate cached layer). On Replit the model is downloaded automatically on first start by `run.py`.

### In-memory log buffer

The admin Logs page reads from a Python `logging` ring buffer (last 2000 records, thread-safe). This means log records are available immediately without any file configuration. The buffer is set up in `run.py` before uvicorn starts so that uvicorn's own access logs are also captured.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `curl localhost/api/healthz` → connection refused | Backend not healthy yet | Wait 30s or check `docker compose logs backend` |
| `curl localhost/api/healthz` → 401 | Clerk key wrong or missing | Check `CLERK_PUBLISHABLE_KEY` in `.env` — or ignore if not using Clerk |
| Email login → "No account found" | User not registered | Register first or use Admin → Add User |
| Email login → "Incorrect password" | Wrong password | Double-check password; admin can create a new user |
| Admin login → "ADMIN_PASSWORD not configured" | Missing env var | Set `ADMIN_PASSWORD` in `.env` |
| Admin login → "Invalid username or password" | Wrong credentials | Check `ADMIN_USERNAME` / `ADMIN_PASSWORD` in `.env` |
| `/admin` shows blank or 404 | nginx config or build issue | Check `docker compose logs frontend` |
| Google OAuth not showing | Clerk key not set | Set `VITE_CLERK_PUBLISHABLE_KEY` in `.env` |
| Admin "Google Users" tab → error | `CLERK_SECRET_KEY` missing | Set it in `.env`; App Users tab still works without it |
| Build fails: rollup musl error | Wrong Docker base image | Dockerfile must use `node:24-slim` not alpine |
| Build fails: pandas_ta not found | PYTHONPATH not set | Backend Dockerfile must have `ENV PYTHONPATH=/app` |
| Frontend changes not applied | `--build` missing | Run `docker compose up --build -d` |
| User accounts lost after restart | Volume not mounted | Check that `userdata` volume is defined in docker-compose.yml |
| Telegram bot not polling | Token missing or wrong | Set `TELEGRAM_BOT_TOKEN` in `.env` |
