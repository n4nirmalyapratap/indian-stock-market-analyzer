# Indian Stock Market Analyzer — Workspace

## Overview

Real-time Indian stock market analysis platform — sector rotation tracking, candlestick pattern detection, custom stock scanners, NLP-powered natural language queries, analytics, WhatsApp bot, and Telegram bot.

**Source:** https://github.com/n4nirmalyapratap/indian-stock-market-analyzer

**Backend: Python FastAPI only. No Node.js backend is active.**

---

## User Preferences

- **After every change: push to GitHub and share the commit link with the user.**
- Push command: `pnpm --filter @workspace/scripts run push-github`

---

## Active Services

| Workflow | Command | Port | Purpose |
|---|---|---|---|
| **artifacts/api-server: API Server** | `bash -c 'cd /home/runner/workspace/artifacts/python-backend && PORT=8090 python run.py'` | 8090 | FastAPI — all stock/analytics/NLP APIs |
| **artifacts/nestjs-backend-placeholder: web** | `BASE_PATH=/ PORT=3002 pnpm --filter @workspace/nestjs-backend-placeholder run dev` | 3002 | React/Vite frontend |

---

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **Python**: 3.11 · FastAPI · uvicorn · spaCy · pandas · numpy · ta · yfinance · scipy
- **Frontend**: React 18 · Vite · TypeScript · TailwindCSS · TanStack Query

---

## Key Commands

- `pnpm install` — install all Node.js packages across workspace
- `pnpm --filter @workspace/scripts run push-github` — push all changes to GitHub
- `pnpm --filter @workspace/nestjs-backend-placeholder run dev` — start frontend manually
- `curl http://localhost:8090/api/healthz` — verify Python backend is live
- `curl http://localhost:80/api/sectors/rotation` — verify full proxy routing works

---

## Project Structure

```
artifacts/python-backend/     ← ACTIVE: FastAPI backend (port 8090)
artifacts/nestjs-backend-placeholder/  ← ACTIVE: React/Vite frontend (port 3002)
artifacts/nestjs-backend/     ← DEPRECATED (reference only)
artifacts/api-server/         ← DEPRECATED Node.js server; artifact.toml now points to Python backend
scripts/src/push-github.ts    ← GitHub push script (uses Replit GitHub connector)
```

---

## GitHub Integration

- Connected via Replit GitHub connector (OAuth — no PAT needed)
- Push script: `scripts/src/push-github.ts`
- Repository: `n4nirmalyapratap/indian-stock-market-analyzer` (branch: `main`)
