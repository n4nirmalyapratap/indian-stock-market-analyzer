# Indian Stock Market Analyzer — Workspace

## Overview

Real-time Indian stock market analysis platform — sector rotation tracking, candlestick pattern detection, custom stock scanners, NLP-powered natural language queries, analytics, WhatsApp bot, and Telegram bot.

**Source:** https://github.com/n4nirmalyapratap/indian-stock-market-analyzer

**Backend: Python FastAPI only. No Node.js backend is active.**

---

## Active Services

| Workflow | Command | Port | Purpose |
|---|---|---|---|
| **Python Backend** | `bash -c 'cd /home/runner/workspace/artifacts/python-backend && PORT=8090 python run.py'` | 8090 | FastAPI — all stock/analytics/NLP APIs |
| **artifacts/nestjs-backend-placeholder: web** | `BASE_PATH=/ PORT=3002 pnpm --filter @workspace/nestjs-backend-placeholder run dev` | 3002 | React/Vite frontend |

---

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **Python**: 3.11 · FastAPI · uvicorn · spaCy · pandas · numpy · ta · yfinance · scipy
- **Frontend**: React 18 · Vite · TypeScript · TailwindCSS · TanStack Query

---

## First-Time Setup (after cloning into a fresh Replit workspace)

Follow these steps **in order**:

### Step 1 — Clone the repo and copy files
```bash
git clone https://github.com/n4nirmalyapratap/indian-stock-market-analyzer /tmp/repo
cp -r /tmp/repo/artifacts/python-backend /home/runner/workspace/artifacts/
cp -r /tmp/repo/artifacts/nestjs-backend-placeholder /home/runner/workspace/artifacts/
cp -r /tmp/repo/attached_assets /home/runner/workspace/
```

### Step 2 — Install Python 3.11
Use the Replit package manager to install **Python 3.11** as a language module.

### Step 3 — Install Python packages
```bash
pip install fastapi "uvicorn[standard]" httpx pandas numpy ta spacy python-multipart openpyxl yfinance scipy
python3 -m spacy download en_core_web_sm --break-system-packages
```

### Step 4 — Install Node.js packages
```bash
pnpm install
```

### Step 5 — Register the frontend artifact
Copy the artifact config so Replit's preview system can find the frontend:
```bash
cp artifacts/nestjs-backend-placeholder/.replit-artifact/artifact.edit.toml \
   artifacts/nestjs-backend-placeholder/.replit-artifact/artifact.toml
```

### Step 6 — Update the API routing
Edit `artifacts/api-server/.replit-artifact/artifact.toml` so the `/api` proxy path
points to the Python backend on **port 8090** (not the old Node.js server on 8080).
The file should contain:
```toml
[[services]]
localPort = 8090
name = "API Server"
paths = ["/api"]
```

### Step 7 — Start workflows
Start **Python Backend** first, then **artifacts/nestjs-backend-placeholder: web**.

---

## Known Gotcha — Duplicate Workflow Port Conflict

**Symptom:** After registering the frontend artifact, the preview pane shows "App is not running."

**Root cause:** When you register `nestjs-backend-placeholder` as a Replit artifact, the platform
automatically creates a new managed workflow called `artifacts/nestjs-backend-placeholder: web`
on port 3002. If you had already manually created a workflow (e.g. "Stock Market Frontend") using
the same port, the two workflows fight over port 3002 and neither starts cleanly.

**Fix:**
1. Remove any manually created frontend workflow (e.g. "Stock Market Frontend").
2. Start only the artifact-managed one: `artifacts/nestjs-backend-placeholder: web`.

This only happens when cloning into a fresh Replit workspace — it does not recur once the
correct workflows are in place.

---

## Key API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/healthz` | Health check |
| GET | `/api/sectors/rotation` | Sector rotation phase + recommendations |
| GET | `/api/stocks/nifty100` | Full Nifty 100 quotes |
| GET | `/api/patterns` | Detected candlestick patterns |
| POST | `/api/nlp/query` | Natural language query |
| GET | `/api/analytics/top-movers` | Top gainers/losers |

Full API reference: see `artifacts/python-backend/README.md`

---

## Key Commands

- `pnpm install` — install all Node.js packages across workspace
- `pnpm --filter @workspace/nestjs-backend-placeholder run dev` — start frontend manually
- `curl http://localhost:8090/api/healthz` — verify Python backend is live
- `curl http://localhost:80/api/sectors/rotation` — verify full proxy routing works
