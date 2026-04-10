# Indian Stock Market Analyzer

## Overview

Real-time Indian stock market analysis platform with two frontends and a Python FastAPI backend:
- **User app** (`/`) — market dashboard, chart studio, sector analysis, AI analyzer, news, stock lookup, pattern detection, scanners, options tester
- **Admin dashboard** (`/admin/`) — user management, live log viewer, bot management, backend health

---

## User Preferences

- Clear, concise instructions. Prioritize stability and performance.
- Iterative approach with frequent, small commits.
- Outline plans before major architectural changes.
- Avoid technical jargon where simpler terms suffice.
- **Do not** modify `artifacts/api-server/` or `artifacts/mockup-sandbox/`.
- **Do not** delete `replit.md`.

---

## System Architecture

### Services (Replit)

| Workflow | Port | What it does |
|---|---|---|
| `Python Backend` | 8090 | FastAPI + uvicorn — all data + auth API |
| `artifacts/stock-market-app: web` | 3002 | User app — Vite dev server |
| `artifacts/admin-dashboard: web` | 22133 | Admin app — Vite dev server |
| `artifacts/api-server` | — | Routing shim only — do not start |

### Services (Docker / production)

```
Browser → nginx:80
  ├─ /api/*   → backend:8090  (Python FastAPI)
  ├─ /admin/  → /usr/share/nginx/admin/ (built admin app)
  └─ /        → /usr/share/nginx/html/  (built user app)
```

---

## Authentication

### User App — dual auth

Two methods work side by side. Both issue a JWT that the backend accepts.

**Custom auth (always available)**
- `POST /api/auth/register` + `POST /api/auth/login`
- HS256 JWT signed with `SESSION_SECRET`, 30-day expiry
- User DB: SQLite at `artifacts/python-backend/users.db` (Replit) or `/app/data/users.db` (Docker)
- `DATA_DIR` env var controls the DB directory; defaults to the repo root for Replit dev
- Middleware checks HS256 signature first, then falls back to Clerk RS256

**Clerk / Google OAuth (optional)**
- Enabled when `VITE_CLERK_PUBLISHABLE_KEY` is set
- RS256 JWT from Clerk — verified against Clerk JWKS on the backend
- Frontend shows "Continue with Google" button alongside email+password form
- Users created via Google appear in the admin "Google Users" tab

### Admin Dashboard

- `POST /api/admin/login` → session token (random hex, 8-hour TTL, in-memory map)
- All admin calls include `X-Admin-Token: <token>` header
- Completely separate from user auth — no Clerk required

### Middleware (`app/middleware/clerk_auth.py`)

1. If `Authorization: Bearer <token>` — try HS256 verify (custom); if fails, try Clerk RS256
2. If `X-Admin-Token: <token>` — check in-memory admin session map → skip user auth
3. `/api/auth/*` and `/api/admin/login` are public (bypass middleware)

---

## Admin Dashboard Features

| Page | Details |
|---|---|
| **App Status** | Uptime, Python version, endpoint count, bot configured flags |
| **Users → App Users** | List SQLite users; Add user (name+email+password); Delete user |
| **Users → Google Users** | List Clerk users via Clerk REST API (requires `CLERK_SECRET_KEY`) |
| **Logs** | AWS CloudWatch-style: structured records from in-memory ring buffer; level filter pills (All/Error/Warn/Info/Debug); text search; live mode (5s refresh); pause; jump to bottom |
| **WhatsApp Bot** | Bot simulator + message history |
| **Telegram Bot** | Status, test messages, polling log |

---

## User App — Settings Page

Located at `/settings`. Shows:
- Profile card (avatar, name, email, auth type badge — Google or Email+Password)
- Account details rows (name, email, sign-in method)
- Preferences (dark/light mode toggle)
- Bot Integrations (collapsed — expand to access WhatsApp/Telegram consoles)
- Sign Out button

For Clerk users, `SettingsWithClerk` wrapper in `App.tsx` extracts user info and passes as `clerkUser` prop. For custom-auth users, `useCustomAuth()` provides the data.

---

## Backend Services

### Log Buffer (`app/services/log_buffer.py`)

- `RingBufferHandler` — attaches to root Python logger, keeps last 2000 records (thread-safe)
- Set up in `run.py` **before** uvicorn starts, so all uvicorn + app logs are captured
- `get_ring_buffer().get_records(limit, level, search)` — used by `/api/admin/logs`
- Returns structured JSON: `{ts, level, logger, msg}` — no log file needed

### Custom Auth (`app/routes/auth.py`)

- `_DB_PATH` = `DATA_DIR/users.db` where `DATA_DIR` = env var or `artifacts/python-backend/`
- bcrypt password hashing; HS256 JWT with `SESSION_SECRET`
- `verify_custom_token()` is called by the Clerk auth middleware

### Admin Routes (`app/routes/admin.py`)

- Same `_DB_PATH` logic as auth.py
- `/api/admin/users/app` — GET all SQLite users
- `/api/admin/users/create` — POST create user (bcrypt + insert)
- `/api/admin/users/app/{id}` — DELETE user
- `/api/admin/logs` — GET structured records from ring buffer (supports `?level=&search=&lines=`)

---

## Docker

### Files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Orchestrates `backend` + `frontend` containers + `userdata` named volume |
| `artifacts/python-backend/Dockerfile` | `python:3.11-slim` — installs deps, spaCy model, copies source |
| `artifacts/stock-market-app/Dockerfile` | 3-stage build: user app → admin app → nginx |
| `artifacts/stock-market-app/nginx.conf` | Routes `/api/*`, `/admin/`, `/` |
| `.env.example` | Template — copy to `.env` |

### Named Volumes

| Volume | Mounted at | Contains |
|---|---|---|
| `userdata` | `/app/data` | `users.db` (SQLite, persists across restarts) |

### Build notes

- **Always `--build`** — `pnpm-lock.yaml` not committed; Docker can't cache-skip `pnpm install`
- **Use `node:24-slim`** (glibc/Debian) — never Alpine (musl); Rollup native binaries require glibc
- `DATA_DIR=/app/data` env var is set in docker-compose so both `auth.py` and `admin.py` find the same DB in the volume

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SESSION_SECRET` | **Yes** | Long random hex secret for HS256 JWT signing |
| `ADMIN_USERNAME` | **Yes** | Admin panel username (default: `admin`) |
| `ADMIN_PASSWORD` | **Yes** | Admin panel password |
| `CLERK_PUBLISHABLE_KEY` | Optional | Enables Clerk/Google OAuth (backend JWKS) |
| `CLERK_SECRET_KEY` | Optional | Enables admin "Google Users" tab |
| `VITE_CLERK_PUBLISHABLE_KEY` | Optional | Baked into user-app JS at build time |
| `DATA_DIR` | Optional | SQLite DB directory (default: source root) |
| `TELEGRAM_BOT_TOKEN` | Optional | Telegram bot |
| `TWILIO_ACCOUNT_SID` | Optional | WhatsApp via Twilio |
| `TWILIO_AUTH_TOKEN` | Optional | WhatsApp via Twilio |

---

## Critical Rules (never break these)

- **pandas_ta** — local shim at `artifacts/python-backend/pandas_ta/`. Never `pip install pandas_ta`. Never add to `requirements.txt`. Never add to skip dirs.
- **yfinance** — always `yf.Ticker(symbol).history()`. Never `yf.download()` (not thread-safe).
- **Router** — `wouter`, not `react-router`.
- **Node Docker image** — `node:24-slim` (glibc). Never Alpine.
- **api-server artifact** — routing shim only. Never add code. Never restart.
- **nestjs-backend** — do not recreate `artifacts/nestjs-backend/` or `artifacts/nestjs-backend-placeholder/`.
- **pnpm push** — `cd scripts && pnpm run push-github`. Never use `base_tree` in GitHub tree API calls.
- **Tailwind** — use `dark:` variants throughout; never hardcode colors without dark counterpart.

---

## Development Notes

- Replit auto-creates a `SESSION_SECRET` secret — check it's set before testing custom auth
- The admin password is `NiftyAdmin@2026` (set via `ADMIN_PASSWORD` env var / Replit secret)
- SQLite DB in Replit: `artifacts/python-backend/users.db` — excluded from GitHub pushes
- After adding new backend routes, restart the `Python Backend` workflow
- Vite hot-reloads frontend changes automatically — no restart needed for `.tsx` edits
