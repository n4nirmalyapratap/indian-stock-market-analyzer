# Indian Stock Market Analyzer — Development History

## Project Overview

Full-stack Indian stock market analysis platform.

| Layer | Technology | Location |
|---|---|---|
| Backend | Python 3.11 · FastAPI · uvicorn | `artifacts/python-backend/` |
| User frontend | React 18 · Vite · Tailwind CSS · wouter | `artifacts/stock-market-app/` |
| Admin dashboard | React 18 · Vite · Tailwind CSS | `artifacts/admin-dashboard/` |
| Production server | nginx (serves both frontends + proxies API) | Docker only |

---

## Architecture

### Replit (development)

```
localhost:8090   ← Python FastAPI backend
localhost:3002   ← User app  (Vite dev server)
localhost:22133  ← Admin app (Vite dev server)
```

### Docker (production)

```
Browser → nginx:80
  ├─ /api/*   → python-backend:8090
  ├─ /admin/  → built admin app (static)
  └─ /        → built user app  (static)
```

### Key files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Orchestrates backend + frontend containers + `userdata` volume |
| `artifacts/python-backend/Dockerfile` | Python 3.11-slim image |
| `artifacts/stock-market-app/Dockerfile` | 3-stage build: user app → admin app → nginx |
| `artifacts/stock-market-app/nginx.conf` | Routes `/api/*`, `/admin/`, `/` |
| `artifacts/python-backend/main.py` | FastAPI app entry-point with lifespan, CORS, middleware |
| `artifacts/python-backend/app/services/log_buffer.py` | In-memory ring buffer for live log viewer |
| `artifacts/python-backend/app/routes/auth.py` | Custom email/password auth (HS256 JWT, SQLite) |
| `artifacts/python-backend/app/routes/admin.py` | Admin REST routes (users CRUD, logs, health) |
| `artifacts/stock-market-app/src/App.tsx` | Root React app — dual auth routing, no-Clerk path |
| `artifacts/stock-market-app/src/ClerkApp.tsx` | All Clerk-dependent code (lazy-loaded) |
| `artifacts/stock-market-app/src/LayoutShell.tsx` | Shared sidebar + nav shell used by both auth paths |
| `artifacts/admin-dashboard/src/App.tsx` | Admin dashboard root — QueryCache 401 auto-logout |

---

## Features Built

### User App (`/`)

| Feature | Notes |
|---|---|
| **Dashboard** | Market overview, index cards, top movers |
| **Chart Studio** | Full-screen candlestick chart, indicators, timeframes |
| **Market Sectors** | Sector performance overview + drill-down pages |
| **News Feed** | Live market news aggregator |
| **Stock Lookup** | Symbol search + fundamentals |
| **Patterns** | Candlestick pattern scanner |
| **Scanners** | Custom technical screeners |
| **AI Analyzer (Hydra)** | NLP-based stock analysis |
| **Options Tester** | Options strategy simulator |
| **Settings** | Profile, preferences, bot integrations |
| **Dark mode** | Full Tailwind `dark:` variant support throughout |
| **Sidebar** | Collapsible with icon-only and expanded modes; persists state |
| **Global AI Assistant** | Floating chat assistant |

### Admin Dashboard (`/admin/`)

| Page | Notes |
|---|---|
| **App Status** | Uptime, Python version, endpoint count, bot status flags |
| **App Users** | List / add / delete SQLite users |
| **Google Users** | Clerk users via Clerk REST API (needs `CLERK_SECRET_KEY`) |
| **Logs** | CloudWatch-style live log viewer — ring buffer, level filter, text search, live/pause mode |
| **WhatsApp Bot** | Simulator + message history |
| **Telegram Bot** | Status, test messages, polling log |

---

## Authentication

### User App — dual auth

Both methods issue a JWT that the single backend middleware accepts.

**Custom email + password**
- `POST /api/auth/register` and `POST /api/auth/login`
- bcrypt password hashing; HS256 JWT with `SESSION_SECRET`; 30-day expiry
- Users stored in SQLite: `users.db` (Replit: source root; Docker: `/app/data/`)
- `DATA_DIR` env var controls the DB path in both `auth.py` and `admin.py`

**Clerk / Google OAuth (optional)**
- Activated only when `VITE_CLERK_PUBLISHABLE_KEY` is set at build time
- RS256 JWT from Clerk, verified against Clerk JWKS on the backend
- Frontend shows "Continue with Google" button
- Whole `@clerk/react` module is **lazy-loaded** — never imported when the key is absent

**Middleware flow (`app/middleware/clerk_auth.py`)**
1. `Authorization: Bearer <token>` → try HS256 (custom) first; fall back to Clerk RS256
2. `X-Admin-Token: <token>` → check in-memory admin session map → skip user auth
3. `/api/auth/*` and `/api/admin/login` are public routes — no auth required

### Admin Dashboard
- `POST /api/admin/login` → random hex session token, 8-hour TTL, in-memory map
- All subsequent admin calls carry `X-Admin-Token: <token>` header
- No Clerk dependency; completely separate from user auth

---

## Bug Fixes & Improvements (chronological)

### 1 — Admin 401 auto-logout

**Problem**: After the Python backend restarts (e.g. during Docker rebuild), the admin session token becomes invalid. Every admin API call returns 401. The dashboard kept retrying and showing stale data instead of redirecting to login.

**Fix**: Added a `QueryCache` subscription in `AdminApp`. Any query that returns `error?.status === 401` triggers `handleSignOut()`, which clears the token and navigates to the login page. Retry config skips retrying on 401 to avoid hammering the backend.

---

### 2 — Ring buffer log capture race condition

**Problem**: The `setup_ring_buffer()` call was in `run.py`, before uvicorn started. uvicorn resets its own loggers (`uvicorn`, `uvicorn.error`, `uvicorn.access`) after startup with `propagate=False`, so they bypassed the ring buffer and their logs never appeared in the admin log viewer.

**Fix**: Moved `setup_ring_buffer()` into the FastAPI `lifespan()` context manager in `main.py`. After uvicorn resets its loggers, the lifespan immediately re-attaches the `RingBufferHandler` to each uvicorn logger explicitly. This ensures all backend logs (including request logs) appear in the live log viewer.

---

### 3 — Docker build: phantom dependency errors

**Problem**: Docker build failed at the `pnpm install` step for the admin dashboard with errors about missing packages `@workspace/api-client-react` and `@clerk/react`, and a missing TypeScript project reference to `../../lib/api-client-react`.

**Fix**:
- Removed `@workspace/api-client-react` and `@clerk/react` from `admin-dashboard/package.json`
- Removed the dangling `references` entry in `admin-dashboard/tsconfig.json`
- Added `ENV PIP_ROOT_USER_ACTION=ignore` to the backend Dockerfile to suppress pip root warnings

---

### 4 — Docker blank page (Replit-only plugin crash)

**Problem**: The user app built and served fine in Docker, but the browser showed a blank white page. nginx logs showed the HTML loaded correctly. The issue was `runtimeErrorOverlay()` — a Replit-specific Vite plugin that connects to a Replit WebSocket server. When included unconditionally in production, it crashed on load because the Replit WebSocket server does not exist in Docker.

**Fix**: Gated `runtimeErrorOverlay()` and all other Replit-specific plugins behind a dev-only condition in `vite.config.ts`:
```ts
...(process.env.NODE_ENV !== "production" && process.env.REPL_ID
  ? [runtimeErrorOverlay(), cartographer()]
  : [])
```

---

### 5 — Error surfacing (global error capture)

**Problem**: Module-level JavaScript errors (ones that crash before React renders) produced a completely blank white page with no indication of what went wrong. This made debugging Docker production issues nearly impossible.

**Fix**:
- Added `window.onerror` and `window.addEventListener("unhandledrejection", ...)` handlers directly in `index.html` (before the module script tag). When triggered, they inject a visible red error card into `document.body` showing the exact error message.
- Added a `RootErrorBoundary` class component in `main.tsx` to catch React render errors and display them instead of crashing silently.

---

### 6 — Wrong page title

**Problem**: Browser tab showed "NestJS Backend (API)" — a leftover from the original scaffold.

**Fix**: Updated `<title>` in `index.html` to "Nifty Node | Indian Stock Market Analysis".

---

### 7 — Clerk CDN fetch crashing Docker app (root cause of blank page)

**Problem**: After adding the global error capture, the real cause of the Docker blank page became visible:

```
Unhandled Promise Rejection
Clerk: Failed to load Clerk JS, failed to load script:
https://npm/@clerk/clerk-js@6/dist/clerk.browser.js
(code="failed_to_load_clerk_js")
```

`@clerk/react` v6 eagerly tries to download the Clerk browser SDK from a CDN the moment its module is evaluated — even without rendering `<ClerkProvider>`. In Docker (no `VITE_CLERK_PUBLISHABLE_KEY`, no internet or CDN access), this fetch fails and throws an unhandled promise rejection. Our global error overlay then covered the login form, making the page appear blank.

**Fix**: Restructured the frontend into three files:

| File | Contents |
|---|---|
| `src/LayoutShell.tsx` | `NavLink`, `ThemeToggle`, `LayoutShell` — shared by both auth paths |
| `src/ClerkApp.tsx` | All `@clerk/react` code: `ClerkProvider`, Clerk hooks, Clerk-specific routes |
| `src/App.tsx` | Root app — never imports `@clerk/react`; conditionally lazy-loads `ClerkApp` |

In `App.tsx`:
```tsx
const ClerkApp = lazy(() => import("./ClerkApp"));

// Only loads the Clerk chunk when a key is actually configured
{clerkPubKey
  ? <Suspense fallback={null}><ClerkApp /></Suspense>
  : <AppWithoutClerk />
}
```

**Result**: When no Clerk key is set, the browser never requests `ClerkApp-*.js`, so `@clerk/react` is never evaluated, and the CDN fetch never happens. The main bundle also shrank by ~350 kB.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SESSION_SECRET` | **Yes** | Random hex secret for HS256 JWT signing |
| `ADMIN_USERNAME` | **Yes** | Admin panel login username |
| `ADMIN_PASSWORD` | **Yes** | Admin panel login password |
| `CLERK_PUBLISHABLE_KEY` | Optional | Enables Clerk/Google OAuth on the backend |
| `CLERK_SECRET_KEY` | Optional | Enables "Google Users" tab in admin dashboard |
| `VITE_CLERK_PUBLISHABLE_KEY` | Optional | Baked into user-app JS at build time |
| `DATA_DIR` | Optional | SQLite DB directory (`/app/data` in Docker) |
| `TELEGRAM_BOT_TOKEN` | Optional | Enables Telegram bot |
| `TWILIO_ACCOUNT_SID` | Optional | WhatsApp via Twilio |
| `TWILIO_AUTH_TOKEN` | Optional | WhatsApp via Twilio |

---

## Docker Deployment

### First-time setup

```bash
git clone https://github.com/n4nirmalyapratap/indian-stock-market-analyzer
cd indian-stock-market-analyzer
cp .env.example .env
# Edit .env — fill in SESSION_SECRET, ADMIN_USERNAME, ADMIN_PASSWORD
docker compose up --build -d
```

### After any code change

```bash
git pull
docker compose up --build -d
```

### If you suspect stale Docker cache

```bash
git pull
docker compose down
docker compose up --build --no-cache -d
```

### Verify it is running

```bash
docker compose ps          # both containers should be "Up"
curl http://localhost/api/health
# open http://localhost        ← user app
# open http://localhost/admin/ ← admin dashboard
```

---

## Critical Rules

- **pandas_ta** — local shim at `artifacts/python-backend/pandas_ta/`. Never `pip install pandas_ta`. Never add to `requirements.txt`.
- **yfinance** — always `yf.Ticker(symbol).history()`. Never `yf.download()` (not thread-safe).
- **Router** — `wouter`. Never `react-router`.
- **Node Docker image** — `node:24-slim` (glibc/Debian). Never Alpine (musl — breaks native Rollup binaries).
- **api-server artifact** — routing shim only. Never add code. Never restart it.
- **nestjs-backend** — do not recreate `artifacts/nestjs-backend/` or `artifacts/nestjs-backend-placeholder/`.
- **GitHub push** — `cd scripts && pnpm run push-github`. Never use `base_tree` in GitHub Trees API calls.
- **Tailwind** — use `dark:` variants throughout. Never hardcode colors without a dark counterpart.
- **Clerk imports** — all `@clerk/react` code must stay in `ClerkApp.tsx`. Never import from `@clerk/react` in `App.tsx` or any shared file.
- **Ring buffer setup** — must be in `lifespan()` in `main.py`, not in `run.py`.
- **runtimeErrorOverlay** — must stay inside the `NODE_ENV !== "production" && REPL_ID` guard in `vite.config.ts`.

---

## GitHub Commits (key milestones)

| Short SHA | Description |
|---|---|
| `6533ba6` | Initial working state — backend + both frontends + Docker |
| `3b155be` | Global error capture in index.html + correct page title |
| `3cf7032` | Clerk lazy-load refactor — fixes Docker blank page |
