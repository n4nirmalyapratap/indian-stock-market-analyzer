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

## First-Time Setup (Fresh Replit Account)

Follow these steps in order after forking/cloning the repo into a new Replit workspace.

### Step 1 — Add Secrets

Open **Secrets** (lock icon in the left sidebar → "New Secret") and add all tokens before doing anything else.

#### GITHUB_TOKEN (required for git push)
1. Go to https://github.com/settings/tokens
2. Click **Generate new token (classic)**
3. Give it a name (e.g. "Replit push")
4. Tick the **`repo`** checkbox (full repo access)
5. Scroll down → click **Generate token**
6. Copy the token immediately (it is shown only once)
7. In Replit Secrets: Key = `GITHUB_TOKEN`, Value = the token you copied

#### TELEGRAM_BOT_TOKEN (required for Telegram bot)
1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Follow the prompts — choose a name and username for your bot
4. BotFather will reply with a token like `123456:ABC-DEF...`
5. In Replit Secrets: Key = `TELEGRAM_BOT_TOKEN`, Value = the token

#### TWILIO secrets (optional — only needed for WhatsApp bot)
Get these from your Twilio console (https://console.twilio.com):

| Secret Key | Where to find it |
|---|---|
| `TWILIO_ACCOUNT_SID` | Twilio Console → Account Info |
| `TWILIO_AUTH_TOKEN` | Twilio Console → Account Info |
| `TWILIO_WHATSAPP_NUMBER` | Twilio Console → Messaging → WhatsApp Senders |

#### SESSION_SECRET (optional)
Any random string works. In Replit Secrets: Key = `SESSION_SECRET`, Value = any long random string.

---

### Step 2 — Install Python 3.11

In the Replit package manager, install **Python 3.11** as the programming language runtime.

---

### Step 3 — Install Python packages

Open the **Shell** tab and run:

```bash
pip install fastapi "uvicorn[standard]" httpx pandas numpy ta spacy python-multipart openpyxl yfinance
python -m spacy download en_core_web_sm
```

> `run.py` will also auto-download `en_core_web_sm` on first start, but running it manually here avoids a slow first boot.

---

### Step 4 — Install Node.js packages

In the Shell, run:

```bash
pnpm install
```

This installs all frontend and scripts dependencies across the pnpm workspace.

---

### Step 5 — Configure Workflows

Go to the **Workflows** panel (wrench icon) and create or verify two workflows:

**Workflow 1 — API Server**
- Name: `artifacts/api-server: API Server`
- Command:
  ```
  bash -c 'cd /home/runner/workspace/artifacts/python-backend && PORT=8090 python run.py'
  ```

**Workflow 2 — Stock Market Frontend**
- Name: `artifacts/stock-market-app: web`
- Command:
  ```
  BASE_PATH=/ PORT=3002 pnpm --filter @workspace/nestjs-backend-placeholder run dev
  ```

Start both workflows. The API Server takes ~30 seconds on first boot (downloading the spaCy model).

---

### Step 6 — Configure Git Remote for Pushing

In the Shell, run once:

```bash
git remote add origin https://$GITHUB_TOKEN@github.com/n4nirmalyapratap/indian-stock-market-analyzer.git
```

> If `origin` already exists, use `set-url` instead of `add`:
> ```bash
> git remote set-url origin https://$GITHUB_TOKEN@github.com/n4nirmalyapratap/indian-stock-market-analyzer.git
> ```

After this, pushing to GitHub any time is just:

```bash
git add -A
git commit -m "describe your changes"
git push origin main
```

---

### Step 7 — Verify Everything is Working

**Check the API is live:**
```bash
curl http://localhost:8090/api/sectors
```
Look for `"source": "YAHOO"` or `"source": "NSE"` in the response. If you see `"source": "UNAVAILABLE"` something is wrong with the network.

**Check the frontend:** Open the Replit preview pane — the dashboard should show live sector data with non-zero values (e.g. Auto +6.69%, IT +1.2%, etc.).

**Check Telegram bot:** Navigate to the Telegram page in the app. If `TELEGRAM_BOT_TOKEN` is set correctly, the bot status will show active.

---

## Pushing Changes to GitHub

After making any changes:

```bash
git add -A
git commit -m "describe what changed"
git push origin main
```

The `GITHUB_TOKEN` secret handles authentication automatically. No password prompt will appear.

---

## Known Issues & Fixes

### NSE India Returns 403 on Replit (FIXED)

**Symptom:** Dashboard shows all zeros — Advancing: 0, Declining: 0, sector prices all 0.

**Root cause:** NSE India (`www.nseindia.com`) blocks requests from Replit's cloud IP addresses with a 403 Forbidden. The original `SectorsService.get_all_sectors()` only tried NSE and fell back to hardcoded zeros — no Yahoo Finance fallback.

**Fix applied:** `artifacts/python-backend/app/services/sectors_service.py`
- Added `_get_sectors_from_yahoo()` that fetches all sector prices in parallel via Yahoo Finance
- When NSE returns 403, sector prices now come from Yahoo Finance instead of being zeroed out
- `source` field is `"YAHOO"` when Yahoo fallback is used, `"NSE"` when NSE works

**Yahoo Finance tickers per sector:**

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
| Nifty Financial Services | `HDFCBANK.NS` | Stock proxy |
| Nifty Consumer Durables | `TITAN.NS` | Stock proxy |
| Nifty Oil & Gas | `RELIANCE.NS` | Stock proxy |
| Nifty Healthcare | `APOLLOHOSP.NS` | Stock proxy |

> Stock proxy sectors show the proxy stock's % change, not the index value — but directional accuracy is the same.

**A/D counts** remain 0 when NSE is unavailable — breadth is calculated from `pChange > 0` count across all sectors instead.

---

## Stack

- **Monorepo**: pnpm workspaces
- **Python**: 3.11 · FastAPI · uvicorn · spaCy 3.8 · pandas · numpy · ta · yfinance
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
  mockup-sandbox/              ← Replit canvas tool (managed by artifact system)
lib/
  api-zod/                     ← Zod schemas (unused in active code)
scripts/
  src/push-github.ts           ← GitHub push script (used internally by agent for API-based pushes)
```

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
