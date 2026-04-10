# Indian Stock Market Analyzer

## Overview

A real-time Indian stock market analysis platform with sector rotation tracking,
candlestick pattern detection, custom stock scanners, NLP-powered queries, and a
WhatsApp bot — all powered by a Python FastAPI backend.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 · FastAPI · uvicorn |
| Data sources | NSE India API · Yahoo Finance |
| NLP | spaCy 3.8 (rule-based EntityRuler) |
| Analytics | pandas · numpy |
| Technical indicators | `ta` library (EMA, RSI, MACD, Bollinger Bands, ATR) |
| Frontend | React 18 · Vite · TypeScript · TailwindCSS · TanStack Query |
| Router | wouter (NOT react-router) |
| UI | shadcn/ui |
| Monorepo | pnpm workspaces |
| Node.js version | 24 |

## Project Structure

```
/
├── artifacts/
│   ├── python-backend/     ← ACTIVE: FastAPI backend (port 8090)
│   │   ├── main.py         ← App entry point, all routers registered
│   │   ├── run.py          ← Startup script (ensures spaCy model is present)
│   │   ├── requirements.txt
│   │   └── app/
│   │       ├── routes/     ← FastAPI route modules
│   │       └── services/   ← Business logic
│   │
│   ├── stock-market-app/   ← ACTIVE: React/Vite frontend (port 3002)
│   │   ├── .replit-artifact/artifact.toml  ← Registered artifact (localPort=3002)
│   │   ├── vite.config.ts  ← Vite internal proxy: /api/* → localhost:8090
│   │   └── src/
│   │
│   ├── api-server/         ← ROUTING SHIM ONLY — do NOT touch source code
│   │   └── .replit-artifact/artifact.toml  ← Registered at path /api, localPort=8090
│   │                                         Points Replit proxy to Python backend
│   │
│   └── mockup-sandbox/     ← Canvas design tool (do not touch)
│
├── scripts/
│   └── src/push-github.ts  ← GitHub push via Replit connector
└── lib/                    ← Shared TypeScript libraries
```

## Workflows (Active)

| Workflow name | Command | Port | Purpose |
|---|---|---|---|
| `Python Backend` | `bash -c 'cd /home/runner/workspace/artifacts/python-backend && PORT=8090 python3.11 run.py'` | 8090 | FastAPI backend |
| `artifacts/stock-market-app: web` | `BASE_PATH=/ PORT=3002 pnpm --filter @workspace/stock-market-app run dev` | 3002 | React frontend |

> **⚠️ `Start application`** was the old frontend workflow. It was replaced by
> `artifacts/stock-market-app: web` when Replit registered the artifact. The old
> workflow now runs a no-op echo command and is FINISHED. Do not restore it —
> it conflicts with the artifact workflow on port 3002.

---

## ⚠️ Critical: Two-Layer Proxy Architecture

This is the most important thing to understand. There are **two separate proxy layers**
and they must both be configured correctly for the API to work.

### Layer 1 — Replit Proxy (outermost)

The Replit proxy sits at the public domain (e.g., `https://xxx.riker.replit.dev`).
It routes incoming requests to local ports based on **registered artifact paths**.

| Path | Routes to port | Artifact |
|---|---|---|
| `/api/*` | **8090** | `api-server` artifact (shim — do NOT start its workflow) |
| `/*` (all else) | **3002** | `stock-market-app` artifact |

The `api-server` artifact (`artifacts/api-server/.replit-artifact/artifact.toml`) is configured
as a **routing shim** — its `localPort = 8090` and `paths = ["/api"]` tell the Replit proxy
to send all `/api/...` browser requests directly to the Python backend on port 8090.

### Layer 2 — Vite Dev Server Proxy (internal)

Inside `vite.config.ts`, there is a server-side proxy:
```
/api → http://localhost:8090
```
This handles **direct dev-server access** (e.g., `curl localhost:3002/api/...`).
It is **not used** when the app is accessed through the Replit proxy (i.e., the browser).
The browser goes directly via Replit proxy → port 8090.

### ❌ The bug that happened (do not repeat)

When the `api-server` artifact had `localPort = 8080` (a dead NestJS service):
- Browser requests `GET /api/sectors`
- Replit proxy routes to port 8080 → nothing running → **502 Bad Gateway**
- Vite's internal proxy was **never reached** because the Replit proxy intercepted first

**Fix applied**: Updated `artifacts/api-server/.replit-artifact/artifact.toml` so
`localPort = 8090`, pointing the Replit proxy directly at the running Python backend.

---

## ⚠️ Artifact Workflow Conflict (port 3002)

When Replit auto-registers a new artifact for `stock-market-app`, it creates an
artifact-managed workflow `artifacts/stock-market-app: web`. This conflicts with
any manually-created workflow (like `Start application`) using the same port.

**Rules:**
- Only ONE workflow may bind to port 3002 at a time
- `artifacts/stock-market-app: web` is the **canonical** frontend workflow
- `Start application` is a legacy no-op — do not restore or restart it with `PORT=3002`
- The artifact workflow command auto-regenerates from `artifact.toml` — if it
  shows the wrong package filter, update `artifact.toml` using `verifyAndReplaceArtifactToml`

---

## App Pages

| Path | Page |
|---|---|
| `/` | Market Dashboard |
| `/trading` | Chart Studio (Learn tab hidden here) |
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

# Health checks
curl http://localhost:8090/api/healthz      # Python backend direct
curl http://localhost:3002/api/healthz      # Via Vite proxy (dev)

# Run manually (debug only)
python3.11 artifacts/python-backend/run.py
BASE_PATH=/ PORT=3002 pnpm --filter @workspace/stock-market-app run dev
```

---

## Debugging — API 502 Errors

If browser shows 502 on any `/api/...` call:

1. **Check Python backend is running**: `curl http://localhost:8090/api/healthz`
   - If not → restart workflow `Python Backend`
2. **Check Replit proxy routing** (`artifacts/api-server/.replit-artifact/artifact.toml`):
   - `localPort` must be `8090` (not 8080 or anything else)
   - `paths` must be `["/api"]`
3. **Check only one workflow uses port 3002**: `artifacts/stock-market-app: web` only
   - If `Start application` is also running on 3002 → it'll conflict → restart it (it's a no-op now)
4. **Check `api-server` workflow is NOT running** — it should always be `not_started`
   - The `api-server` artifact is a routing shim only; starting it would conflict with Python backend on 8090

## Debugging — App Not Showing in Canvas Preview

1. Check `artifacts/stock-market-app: web` workflow is RUNNING (not finished/not_started)
2. If FINISHED, it likely failed to bind port 3002 because another workflow holds it:
   - Run `Start application` → it's a no-op now so it'll finish → frees the port
   - Then restart `artifacts/stock-market-app: web`
3. If artifact command shows wrong package filter (e.g., `nestjs-backend-placeholder`):
   - Read `artifacts/stock-market-app/.replit-artifact/artifact.toml`
   - Fix `run` command to use `--filter @workspace/stock-market-app`
   - Use `verifyAndReplaceArtifactToml` to apply the change

---

## Important Rules

- Python backend MUST use `python3.11` (not generic `python`)
- All Indian stock symbols use `.NS` suffix for NSE (e.g., RELIANCE.NS)
- yfinance: ALWAYS use `yf.Ticker(ticker).history()` NOT `yf.download()` for concurrency safety
- spaCy model (en_core_web_sm) auto-downloads on first run via run.py self-heal block
- vite.config.ts requires both PORT and BASE_PATH env vars
- **NEVER touch `artifacts/api-server/` source code** — it is a routing shim only
- **NEVER touch `artifacts/nestjs-backend/` or `artifacts/api-server/` pnpm packages**
- GlobalAssistant (Learn tab) must be placed INSIDE WouterRouter in App.tsx
- GlobalAssistant returns null on /trading and /chart/* routes
- UI style: glass cards (`bg-indigo-600 dark:bg-white/10`), Tailwind + `dark:` variants
- Always add feedparser and nsepython to requirements.txt if used
