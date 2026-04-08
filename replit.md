# Indian Stock Market Analyzer

## Overview

Real-time Indian stock market analysis platform — sector rotation tracking,
candlestick pattern detection, custom stock scanners, NLP-powered natural
language queries, analytics layer, WhatsApp bot, and Telegram bot integration.

**Backend: Python FastAPI (only). No Node.js backend is active.**

**Source:** https://github.com/n4nirmalyapratap/indian-stock-market-analyzer

---

## Architecture

```
Stock Market Frontend  (React + Vite, port 3002)
    ↓ Reverse proxy: / → port 3002
    ↓ Reverse proxy: /api → port 8090
Python Backend         (FastAPI + uvicorn, port 8090)   ← ALL API routes
    ↓ fetches market data from NSE India + Yahoo Finance
```

---

## Active Services

| Workflow | Command | Port | Purpose |
|---|---|---|---|
| **Python Backend** | `cd artifacts/python-backend && PORT=8090 python run.py` | 8090 | FastAPI — all stock/analytics/NLP/Telegram APIs |
| **Stock Market Frontend** | `BASE_PATH=/ PORT=3002 pnpm --filter @workspace/nestjs-backend-placeholder run dev` | 3002 | React UI |

## DEPRECATED Services (kept for reference, NOT started)

| Directory | What it was |
|---|---|
| `artifacts/nestjs-backend/` | Original NestJS/WhatsApp backend — replaced by Python |
| `artifacts/api-server/` | Original Express stock data API — replaced by Python |

---

## Proxy Routing

The Replit reverse proxy routes traffic based on artifact.toml registrations:

| Path | Port | Service |
|---|---|---|
| `/api` | 8090 | Python FastAPI backend |
| `/` | 3002 | React + Vite frontend |

Artifact configs:
- `artifacts/api-server/.replit-artifact/artifact.toml` → routes `/api` to port 8090
- `artifacts/stock-market-app/.replit-artifact/artifact.toml` → routes `/` to port 3002

---

## Folder Structure

```
artifacts/
  python-backend/              ← ACTIVE: FastAPI backend (port 8090)
    main.py                    ← App entry, all routers registered
    run.py                     ← Startup (auto-downloads spaCy model)
    requirements.txt           ← Python dependencies
    pandas_ta/                 ← ta-library shim (mirrors pandas-ta API)
    app/
      routes/                  ← sectors, stocks, patterns, scanners, whatsapp, nlp, analytics, telegram, universe
      services/                ← nse_service, yahoo_service, stocks, sectors, patterns,
                                  scanners, whatsapp, nlp_service, analytics_service, telegram_service
      lib/
        universe.py            ← NIFTY100 (80 syms), MIDCAP, SMALLCAP, SECTOR_SYMBOLS
        indicators.py          ← Technical indicator wrappers
  nestjs-backend-placeholder/  ← ACTIVE: Vite + React frontend (port 3002)
    src/lib/api.ts             ← All frontend API calls (relative /api/*)
    src/pages/                 ← Dashboard, Sectors, Stocks, Patterns, Scanners, WhatsApp, Telegram
  stock-market-app/            ← Artifact registration only (proxy config)
    .replit-artifact/          ← Routes / to port 3002
  nestjs-backend/              ← DEPRECATED (reference only)
  api-server/                  ← DEPRECATED (reference only); artifact.toml routes /api → 8090
  mockup-sandbox/              ← Replit canvas tool (managed by artifact system)
lib/
  api-zod/                     ← Zod schemas (unused in active code)
scripts/                       ← post-merge.sh
```

---

## Python Backend — API Routes

| Group | Endpoint | Description |
|---|---|---|
| Health | `GET /api/healthz` | Health check |
| Sectors | `GET /api/sectors` | All NSE sector indices |
| Sectors | `GET /api/sectors/rotation` | Rotation phase + buy recommendations |
| Sectors | `GET /api/sectors/:symbol` | Single sector |
| Stocks | `GET /api/stocks/nifty100` | Nifty 100 quotes |
| Stocks | `GET /api/stocks/midcap` | Midcap quotes |
| Stocks | `GET /api/stocks/smallcap` | Smallcap quotes |
| Stocks | `GET /api/stocks/:symbol` | Full detail + TA + entry recommendation |
| Patterns | `GET /api/patterns` | Detected candlestick patterns |
| Patterns | `POST /api/patterns/scan` | Trigger fresh scan |
| Scanners | `GET/POST /api/scanners` | List / create custom scanners |
| Scanners | `PUT/DELETE /api/scanners/:id` | Update / delete scanner |
| Scanners | `POST /api/scanners/:id/run` | Execute scanner |
| WhatsApp | `GET /api/whatsapp/status` | Bot status |
| WhatsApp | `POST /api/whatsapp/status` | Update status |
| WhatsApp | `GET /api/whatsapp/messages` | Message history |
| WhatsApp | `POST /api/whatsapp/message` | Send/test message |
| Telegram | `GET /api/telegram/status` | Bot status + polling mode |
| Telegram | `GET /api/telegram/messages` | Message log |
| Telegram | `POST /api/telegram/webhook` | Telegram webhook receiver |
| Telegram | `POST /api/telegram/set-webhook` | Register webhook URL |
| Telegram | `POST /api/telegram/test` | Send test message |
| NLP | `POST /api/nlp/query` | Natural language query |
| Analytics | `GET /api/analytics/sector-correlation` | 30-day Pearson correlation |
| Analytics | `GET /api/analytics/breadth-history` | A/D ratio time series |
| Analytics | `GET /api/analytics/top-movers` | Nifty100 gainers/losers |
| Analytics | `GET /api/analytics/pattern-stats` | Pattern backtest stats |
| Analytics | `GET /api/analytics/sector-heatmap` | Sector daily % change |

---

## Environment Variables / Secrets

| Key | Required | Purpose |
|---|---|---|
| `SESSION_SECRET` | Optional | Session security |
| `TELEGRAM_BOT_TOKEN` | Optional | Telegram bot — bot will show unconfigured without it |
| `TWILIO_*` | Optional | WhatsApp bot via Twilio |

---

## Stack

- **Monorepo**: pnpm workspaces
- **Python**: 3.11 · FastAPI · uvicorn · spaCy 3.8 · pandas · numpy · ta library
- **Node.js**: 24 (frontend only — Vite + React + TailwindCSS + TanStack Query)
- **Data sources**: NSE India REST API · Yahoo Finance (httpx)
- **NLP**: spaCy rule-based EntityRuler + Nifty100/sector vocabulary
- **pandas-ta**: custom shim at `artifacts/python-backend/pandas_ta/` wrapping `ta` library

---

## New Replit Account Setup

1. Import repo from GitHub: `n4nirmalyapratap/indian-stock-market-analyzer`
2. `pnpm install` (installs frontend dependencies)
3. Install Python 3.11 module in Replit
4. `cd artifacts/python-backend && pip install -r requirements.txt`
5. The `run.py` auto-downloads `en_core_web_sm` (spaCy model) on first start
6. Add `TELEGRAM_BOT_TOKEN` secret if you want Telegram bot active
7. Hit **Run** — starts Python Backend + Stock Market Frontend

---

## Features

- **Dashboard**: Real-time sector rotation, market breadth, CALL/PUT signal count
- **Sectors**: 15 NSE sector indices with performance and A/D rankings
- **Stocks**: Individual stock lookup with EMA9/21/50/200, RSI, MACD, Bollinger Bands, ATR
- **Patterns**: 20+ candlestick patterns with CALL/PUT signal classification
- **Scanners**: Custom stock filters with condition builder + built-in templates
- **NLP**: Plain-English queries ("analyze RELIANCE", "bullish IT stocks")
- **Analytics**: Sector correlation matrix, breadth history, top movers, heatmap
- **WhatsApp Bot**: Twilio webhook with NLP fallback
- **Telegram Bot**: Long-poll bot with commands (/analyze, /sectors, /rotation, /patterns, /movers, /heatmap) + NLP fallback
