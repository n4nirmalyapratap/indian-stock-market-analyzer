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

---

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
│   ├── api-server/         ← ROUTING SHIM ONLY — do NOT touch source code or start workflow
│   │   └── .replit-artifact/artifact.toml  ← localPort=8090, paths=["/api"]
│   │                                         Tells Replit proxy: route /api/* → port 8090
│   │
│   └── mockup-sandbox/     ← Canvas design tool (do not touch)
│
├── scripts/
│   └── src/push-github.ts  ← GitHub push via Replit connector
└── lib/                    ← Shared TypeScript libraries
```

---

## Workflows (Active)

| Workflow name | Command | Port | State |
|---|---|---|---|
| `Python Backend` | `bash -c 'cd /home/runner/workspace/artifacts/python-backend && PORT=8090 python3.11 run.py'` | 8090 | RUNNING |
| `artifacts/stock-market-app: web` | `BASE_PATH=/ PORT=3002 pnpm --filter @workspace/stock-market-app run dev` | 3002 | RUNNING |
| `Start application` | `echo 'App now served by artifacts/stock-market-app workflow'` | — | FINISHED (no-op) |
| `artifacts/api-server: API Server` | (do not start) | — | NOT_STARTED |
| `artifacts/mockup-sandbox: Component Preview Server` | (do not start) | — | NOT_STARTED |

---

## ⚠️ Critical: Two-Layer Proxy Architecture

There are **two separate proxy layers**. Both must be correctly configured or the API will 502.

### Layer 1 — Replit Proxy (outermost, browser-facing)

The Replit proxy sits at the public domain (`https://xxx.riker.replit.dev`).
It routes requests to local ports based on **registered artifact paths** in each artifact's `artifact.toml`.

| URL path | Routes to port | Controlled by |
|---|---|---|
| `/api/*` | **8090** | `artifacts/api-server/.replit-artifact/artifact.toml` |
| `/*` (everything else) | **3002** | `artifacts/stock-market-app/.replit-artifact/artifact.toml` |

The `api-server` artifact acts as a **routing shim** — `localPort = 8090` and `paths = ["/api"]`
tell the Replit proxy to forward all `/api/...` browser requests directly to the Python backend.
Its own workflow is intentionally NOT started.

### Layer 2 — Vite Dev Server Proxy (internal, server-side only)

Inside `vite.config.ts`:
```js
proxy: { "/api": { target: "http://localhost:8090" } }
```
This only applies to requests that reach Vite directly (e.g., `curl localhost:3002/api/...`).
**It is bypassed entirely when the browser accesses the app through the Replit proxy.**

---

## Full Incident RCA — "App Not Starting / API 502" (April 2026)

This section documents every step taken to fix the startup issues when the `stock-market-app`
artifact was first registered by Replit. Record it in full so future agents don't repeat the same path.

### Timeline & findings

#### Step 1 — Artifact auto-registered with wrong package filter
When Replit registered the `stock-market-app` as a formal artifact, it auto-generated workflow
`artifacts/stock-market-app: web` with a broken `--filter` pointing to whatever package Replit
guessed (in our case `nestjs-backend-placeholder`). The workflow immediately exits with:
```
No projects matched the filters in "/home/runner/workspace"
```

**Finding**: Artifact-managed workflows get their command from `artifact.toml`, not from the
Replit UI workflow configuration. The auto-generated `artifact.toml` picks an arbitrary package
name that may be wrong — especially if folder names have changed.

**How to find the correct package name** — always verify dynamically, never assume:
```bash
cat artifacts/stock-market-app/package.json | python3.11 -c "import sys,json; print(json.load(sys.stdin)['name'])"
# → should print the actual name, e.g. @workspace/stock-market-app
```
Then confirm that name matches the `--filter` in `artifacts/stock-market-app/.replit-artifact/artifact.toml`.
If they differ, fix `artifact.toml` using `verifyAndReplaceArtifactToml()` (see Step 3).

#### Step 2 — `configureWorkflow()` cannot override artifact-managed workflows
Attempted to fix the workflow command using `configureWorkflow()` in the code_execution sandbox:
```
Error: "artifacts/stock-market-app: web" is managed by an artifact and cannot be overridden via setRunWorkflow
```
**Finding**: Artifact-managed workflows (those whose name matches `artifacts/X: Y`) can only
be changed by editing `artifact.toml`. You cannot use `configureWorkflow()` on them.

#### Step 3 — `artifact.toml` cannot be edited directly
Attempting to write to `artifacts/stock-market-app/.replit-artifact/artifact.toml` directly fails:
```
Error: You are forbidden from creating or editing the artifact.toml file.
```
**Finding**: Must use the `verifyAndReplaceArtifactToml()` sandbox function. Workflow:
1. Copy `artifact.toml` to a temp path inside the workspace (NOT `/tmp` — cross-device rename fails)
2. Edit the temp file with the correct package name
3. Call `verifyAndReplaceArtifactToml({ tempFilePath: "...", artifactTomlPath: "..." })`

#### Step 4 — Port 3002 conflict between two workflows
After fixing `artifact.toml`, the `artifacts/stock-market-app: web` workflow still exited
because `Start application` was already bound to port 3002.

**Finding**: Only one process can bind to port 3002. The two workflows had an identical command
and were fighting over the same port. Resolution:
1. Reconfigure `Start application` to a no-op: `configureWorkflow({ name: "Start application", command: "echo ...", autoStart: false })`
2. Restart `Start application` → it runs the echo, finishes, releases port 3002
3. Restart `artifacts/stock-market-app: web` → now binds port 3002 successfully

#### Step 5 — API returning 502 (proxy layer collision)
Even with the frontend running, all `/api/...` calls returned 502 in the browser.
`curl localhost:3002/api/sectors` worked fine (Vite proxy worked), but browser calls failed.

**Finding**: The `api-server` artifact was registered with `localPort = 8080` and `paths = ["/api"]`.
The Replit proxy (outermost layer) intercepted all `/api/...` browser requests and forwarded
them to port 8080 — where nothing was running — before Vite's proxy ever got involved.
`curl localhost:3002/...` bypasses the Replit proxy, which is why it worked but the browser didn't.

Fix: Updated `artifacts/api-server/.replit-artifact/artifact.toml`:
- Changed `localPort = 8080` → `localPort = 8090`
- Changed `run` command to point to the Python backend
- The `api-server` workflow remains NOT_STARTED — only the port routing entry matters

### Checklist to verify working state
```
[ ] curl http://localhost:8090/api/healthz  → 200 OK
[ ] curl http://localhost:3002/api/healthz  → 200 OK (Vite proxy)
[ ] Workflow "Python Backend" → RUNNING
[ ] Workflow "artifacts/stock-market-app: web" → RUNNING
[ ] Workflow "Start application" → FINISHED (no-op, not port 3002)
[ ] Workflow "artifacts/api-server: API Server" → NOT_STARTED
[ ] artifacts/api-server/artifact.toml → localPort = 8090
[ ] artifacts/stock-market-app/artifact.toml → run command uses @workspace/stock-market-app
```

---

## Debugging — API 502 Errors

1. `curl http://localhost:8090/api/healthz` — if this fails, Python backend is down → restart `Python Backend` workflow
2. Check `artifacts/api-server/.replit-artifact/artifact.toml`:
   - `localPort` must be `8090`
   - `paths` must be `["/api"]`
   - If wrong → copy to a temp file in the workspace, fix, use `verifyAndReplaceArtifactToml()`
3. Make sure `artifacts/api-server: API Server` workflow is NOT_STARTED (starting it would conflict on port 8090)
4. `curl http://localhost:3002/api/healthz` — if this fails but 8090 works, Vite proxy is broken → check `vite.config.ts`

## Debugging — Frontend Not Showing in Canvas Preview

1. Check `artifacts/stock-market-app: web` → must be RUNNING
2. If FINISHED:
   - Another workflow likely holds port 3002
   - Check `Start application` — if RUNNING, reconfigure it to no-op then restart it
   - Then restart `artifacts/stock-market-app: web`
3. If workflow command shows a wrong package filter (any name that isn't the actual package):
   - Find the correct name: `cat artifacts/stock-market-app/package.json | python3.11 -c "import sys,json; print(json.load(sys.stdin)['name'])"`
   - Read `artifacts/stock-market-app/.replit-artifact/artifact.toml`
   - Copy to `artifacts/stock-market-app/.replit-artifact/artifact-temp.toml`
   - Fix `run` to `BASE_PATH=/ PORT=3002 pnpm --filter <correct-name> run dev`
   - Call `verifyAndReplaceArtifactToml({ tempFilePath: "...artifact-temp.toml", artifactTomlPath: "...artifact.toml" })`
   - Restart `artifacts/stock-market-app: web`
4. Do NOT use `configureWorkflow()` on artifact-managed workflows — it will throw PROHIBITED_ACTION

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
curl http://localhost:3002/api/healthz      # Via Vite proxy

# Manual run (debug only — use workflows in normal operation)
python3.11 artifacts/python-backend/run.py
BASE_PATH=/ PORT=3002 pnpm --filter @workspace/stock-market-app run dev
```

---

## Important Rules

- Python backend MUST use `python3.11` (not generic `python`)
- All Indian stock symbols use `.NS` suffix for NSE (e.g., RELIANCE.NS)
- yfinance: ALWAYS use `yf.Ticker(ticker).history()` NOT `yf.download()` for concurrency safety
- spaCy model (en_core_web_sm) auto-downloads on first run via `run.py` self-heal block
- `vite.config.ts` requires both `PORT` and `BASE_PATH` env vars or it throws at startup
- **NEVER touch `artifacts/api-server/` source code** — it is a routing shim only
- **NEVER touch `artifacts/nestjs-backend/` or `artifacts/api-server/` pnpm packages**
- **NEVER use `configureWorkflow()` on artifact-managed workflows** — use `verifyAndReplaceArtifactToml()`
- `artifact.toml` cannot be written directly — always copy → edit copy → `verifyAndReplaceArtifactToml()`
- Temp files for `verifyAndReplaceArtifactToml` must be inside `/home/runner/workspace/` (not `/tmp/`) to avoid cross-device rename errors
- GlobalAssistant (Learn tab) must be placed INSIDE WouterRouter in App.tsx
- GlobalAssistant returns null on `/trading` and `/chart/*` routes
- UI style: glass cards (`bg-indigo-600 dark:bg-white/10`), Tailwind + `dark:` variants
- Always add `feedparser` and `nsepython` to `requirements.txt` if used
