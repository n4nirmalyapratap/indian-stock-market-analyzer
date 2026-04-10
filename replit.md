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
│   │   ├── vite.config.ts  ← Proxies /api/* to python backend port 8090
│   │   └── src/
│   │
│   ├── api-server/         ← DEPRECATED (do not touch)
│   └── mockup-sandbox/     ← DEPRECATED (do not touch)
│
├── scripts/
│   └── src/push-github.ts  ← GitHub push via Replit connector
└── lib/                    ← Shared TypeScript libraries
```

## Workflows

- **Python Backend**: `bash -c 'cd /home/runner/workspace/artifacts/python-backend && PORT=8090 python3.11 run.py'`
  - Port: 8090
  - Health check: `curl http://localhost:8090/api/healthz`

- **Start application** (Frontend): `BASE_PATH=/ PORT=3002 pnpm --filter @workspace/stock-market-app run dev`
  - Port: 3002
  - Proxies /api/* → localhost:8090

## App Pages

- `/` → Market Dashboard
- `/trading` → Chart Studio (full candlestick chart — Learn tab hidden here)
- `/sectors` → Market Sectors & rotation
- `/stocks` → Stock Lookup
- `/patterns` → Candlestick pattern detection
- `/scanners` → Custom stock scanners
- `/hydra` → AI Analyzer (NLP queries)
- `/options` → Options Strategy Tester
- `/settings` → Settings (WhatsApp/Telegram bot config)

## Key Commands

- `pnpm --filter @workspace/stock-market-app run dev` — run frontend
- `python3.11 artifacts/python-backend/run.py` — run backend
- `pnpm --filter @workspace/scripts run push-github` — push to GitHub

## Important Notes

- Python backend MUST use `python3.11` (not generic `python`)
- All Indian stock symbols use `.NS` suffix for NSE (e.g., RELIANCE.NS)
- yfinance: ALWAYS use `yf.Ticker(ticker).history()` NOT `yf.download()` for concurrency safety
- spaCy model (en_core_web_sm) auto-downloads on first run via run.py self-heal block
- vite.config.ts requires both PORT and BASE_PATH env vars
- Never touch artifacts/api-server/ source code
- GlobalAssistant (Learn tab) must be placed INSIDE WouterRouter in App.tsx
- GlobalAssistant returns null on /trading and /chart/* routes
