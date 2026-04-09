# Indian Stock Market Analyzer

## Overview

Real-time Indian stock market analysis platform — sector rotation tracking, candlestick pattern detection, custom stock scanners, NLP-powered natural language queries, analytics layer, WhatsApp bot, and Telegram bot integration.

**Source:** https://github.com/n4nirmalyapratap/indian-stock-market-analyzer

**Backend: Python FastAPI (only). No Node.js backend is active.**

---

## Architecture

```
Stock Market Frontend  (React + Vite, port 3002)
    ↓ Reverse proxy: / → port 3002
    ↓ Reverse proxy: /api → port 8090
Python Backend         (FastAPI + uvicorn, port 8090)   ← ALL API routes
    ↓ fetches market data from Yahoo Finance (primary) + NSE India (when available)
```

---

## Active Services

| Workflow | Command | Port | Purpose |
|---|---|---|---|
| **API Server** | `bash -c 'cd /home/runner/workspace/artifacts/python-backend && PORT=8090 python run.py'` | 8090 | FastAPI — all stock/analytics/NLP/Telegram APIs |
| **Stock Market Frontend** | `BASE_PATH=/ PORT=3002 pnpm --filter @workspace/nestjs-backend-placeholder run dev` | 3002 | React UI |

---

## Known Issues & Fixes

### ⚠️ NSE India Returns 403 on Replit (FIXED)

**Symptom:** Dashboard shows all zeros — Advancing: 0, Declining: 0, sector prices all 0.

**Root cause:** NSE India (`www.nseindia.com`) blocks requests from Replit's cloud IP addresses with a 403 Forbidden. The original `SectorsService.get_all_sectors()` only tried NSE and fell back to hardcoded zeros — no Yahoo Finance fallback.

**Fix applied:** `artifacts/python-backend/app/services/sectors_service.py`
- Added `_get_sectors_from_yahoo()` method that fetches all sector prices in parallel via Yahoo Finance
- When NSE returns 403, sector prices now come from Yahoo Finance instead of being zeroed out
- `source` field is set to `"YAHOO"` when Yahoo fallback is used (vs `"NSE"` when NSE works)

**Yahoo Finance tickers for sectors:**

| Sector | Yahoo Ticker | Type |
|---|---|---|
| Nifty Bank | `^NSEBANK` | True index |
| Nifty IT | `^CNXIT` | True index |
| Nifty Auto | `^CNXAUTO` | True index |
| Nifty Pharma | `^CNXPHARMA` | True index |
| Nifty FMCG | `^CNXFMCG` | True index |
| Nifty Metal | `^CNXMETAL` | True index |
| Nifty Realty | `^CNXREALTY` | True index |
| Nifty Energy | `^CNXENERGY` | True index |
| Nifty Media | `^CNXMEDIA` | True index |
| Nifty PSU Bank | `^CNXPSUBANK` | True index |
| NIFTY 50 | `^NSEI` | True index |
| Nifty Financial Services | `HDFCBANK.NS` | Stock proxy (no Yahoo index ticker) |
| Nifty Consumer Durables | `TITAN.NS` | Stock proxy (no Yahoo index ticker) |
| Nifty Oil & Gas | `RELIANCE.NS` | Stock proxy (no Yahoo index ticker) |
| Nifty Healthcare | `APOLLOHOSP.NS` | Stock proxy (no Yahoo index ticker) |

**Note:** Stock proxy sectors show the proxy stock price, not the index value — but % change is still accurate.

**A/D counts** (advances/declines per sector) remain 0 when NSE is unavailable because that data only comes from NSE's API. Breadth is calculated from the `pChange > 0` count across all sectors instead.

---

## Stack

- **Monorepo**: pnpm workspaces
- **Python**: 3.11 · FastAPI · uvicorn · spaCy 3.8 · pandas · numpy · ta library
- **Node.js**: 24 (frontend only — Vite + React + TailwindCSS + TanStack Query)
- **Data sources**: Yahoo Finance (primary, always works) · NSE India REST API (secondary, may 403 on cloud IPs)
- **NLP**: spaCy rule-based EntityRuler + Nifty100/sector vocabulary
- **pandas-ta**: custom shim at `artifacts/python-backend/pandas_ta/` wrapping `ta` library

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
  stock-market-app/            ← Artifact registration (proxy config, routes / → port 3002)
  api-server/                  ← Artifact registration (proxy config, routes /api → port 8090)
  nestjs-backend/              ← DEPRECATED (reference only)
  mockup-sandbox/              ← Replit canvas tool (managed by artifact system)
lib/
  api-zod/                     ← Zod schemas (unused in active code)
scripts/
  src/push-github.ts           ← GitHub push script (uses Replit OAuth connector)
```

---

## Setup Instructions (fresh Replit account)

1. **Install Python 3.11** — use Replit's package management (installProgrammingLanguage)
2. **Install Python packages**: `fastapi uvicorn[standard] httpx pandas numpy ta spacy python-multipart openpyxl`
3. **Install Node.js deps**: `pnpm install` from workspace root
4. **Configure API Server workflow** to run: `bash -c 'cd /home/runner/workspace/artifacts/python-backend && PORT=8090 python run.py'`
5. **Configure Stock Market Frontend workflow** to run: `BASE_PATH=/ PORT=3002 pnpm --filter @workspace/nestjs-backend-placeholder run dev`
6. `run.py` auto-downloads spaCy's `en_core_web_sm` model on first start

**Verify data is loading:** Call `/api/sectors` — if `source` field is `"NSE"` or `"YAHOO"`, data is live. If `source` is `"UNAVAILABLE"`, Yahoo Finance fetch is failing too (network issue).

---

## GitHub Push Log

Pushes are performed via `pnpm --filter @workspace/scripts run push-github`  
This script uses the Replit GitHub OAuth connector (no PAT needed) to create commits  
via the GitHub REST API. Source-only files are synced (no node_modules, .pythonlibs, binary  
assets >400 KB, or generated directories).

| Date | Commit ID | Short SHA | Notes |
|---|---|---|---|
| 2026-04-09 | `a97cfcb7f42e08ee9fe97b016bb3ff2b668333a8` | `a97cfcb` | Initial Replit setup: NSE 403 fix (Yahoo Finance fallback), GitHub push script |

---

## Environment Variables / Secrets

| Key | Required | Purpose |
|---|---|---|
| `SESSION_SECRET` | Optional | Session security |
| `TELEGRAM_BOT_TOKEN` | Optional | Telegram bot — bot will show unconfigured without it |
| `TWILIO_*` | Optional | WhatsApp bot via Twilio |

---

## Features

- **Dashboard**: Real-time sector rotation, market breadth, CALL/PUT signal count
- **Sectors**: 15 NSE sector indices with performance, 3-phase economic cycle analysis, momentum tiers
- **Stocks**: Individual stock lookup with EMA9/21/50/200, RSI, MACD, Bollinger Bands, ATR
- **Patterns**: 20+ candlestick patterns with CALL/PUT signal classification
- **Scanners**: Custom stock filters with condition builder + built-in templates
- **NLP / AI Analyzer**: Plain-English queries ("analyze RELIANCE", "bullish IT stocks")
- **Analytics**: Sector correlation matrix, breadth history, top movers, heatmap
- **WhatsApp Bot**: Twilio webhook with NLP fallback
- **Telegram Bot**: Long-poll bot with commands + NLP fallback
