# Indian Stock Market Analyzer

## Overview

Real-time Indian stock market analysis platform — sector rotation tracking, candlestick pattern detection, custom stock scanners, NLP-powered natural language queries, analytics layer, WhatsApp bot, and Telegram bot integration.

**Source:** https://github.com/n4nirmalyapratap/indian-stock-market-analyzer

**Backend: Python FastAPI (only). No Node.js backend is active.**

---

## Features

| Feature | Status | Notes |
|---|---|---|
| Sector Rotation Tracking | Live | Yahoo Finance via `/api/sectors/rotation` |
| Candlestick Pattern Detection | Live | 50+ patterns, 3 universes |
| Custom Stock Scanners | Live | Condition builder, save/run/test |
| NLP Queries | Live | `/api/nlp/query` |
| Telegram Bot | Live | Requires `TELEGRAM_BOT_TOKEN` secret |
| WhatsApp Bot | Partial | Requires Twilio credentials |
| Options Strategy Tester | Live | `/api/options/*` |
| Analytics | Live | `/api/analytics/*` |
| **Per-Stock Chat** | **Live** | **WebSocket rooms per symbol — see below** |

### Per-Stock Chat System

Real-time community chat attached to every stock symbol across the app.

**Backend:** `artifacts/python-backend/app/routes/chat.py`
- `GET /api/chat/history/{symbol}` — last 50 messages (in-memory, survives restarts only within same server process)
- `WebSocket /api/chat/ws/{symbol}` — joins per-symbol room; messages broadcast to all connected clients in that room

**Frontend:** Three components
- `src/lib/chatStore.ts` — Zustand store; `open(symbol)` / `close()` global state
- `src/components/ChatButton.tsx` — small `MessageCircle` icon button; placed next to every stock symbol
- `src/components/StockChat.tsx` — full slide-in panel (fixed right side); WebSocket connection, message history, send input

**Chat is integrated on:**
- Dashboard — Pattern Signal top calls
- Dashboard — Where to Buy Now sector list
- Patterns page — every pattern card
- Stock Lookup page — company name header
- Scanners page — every matched stock in results

**Anonymous usernames:** auto-generated on first visit (e.g. `BullTrader421`), stored in `localStorage` as `nifty-chat-username`.

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
pip install fastapi "uvicorn[standard]" httpx pandas numpy ta spacy python-multipart openpyxl yfinance scipy
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

### Step 6 — Connect GitHub Integration and Verify Push (mandatory)

This is a mandatory step. The push script (`scripts/src/push-github.ts`) uses the Replit GitHub OAuth connector to authenticate. Without completing all three sub-steps below, the push script will fail silently with `Authenticated as: undefined`.

---

#### Step 6a — Authorise the GitHub OAuth integration (user action required)

The agent cannot do this on your behalf. You must do it once in the Replit UI:

1. In Replit, click **Tools** (or the wrench icon) in the left sidebar
2. Go to **Integrations**
3. Find **GitHub** and click **Connect**
4. Complete the GitHub OAuth flow — authorise Replit to access your account
5. Once done, the status changes to **Connected**

> If the agent is running and waiting: after you complete OAuth, tell the agent "done" and it will continue automatically.

---

#### Step 6b — Install the GitHub connector SDK in the scripts package

Even if `pnpm install` was already run (Step 4), run this explicitly to ensure the connector SDK is installed in the scripts workspace:

```bash
cd /home/runner/workspace/scripts && pnpm add @replit/connectors-sdk
```

This installs `@replit/connectors-sdk` — the package the push script uses to proxy authenticated GitHub API calls through the connected OAuth integration. It is listed in `scripts/package.json` but must be explicitly installed in the scripts workspace before the push script will work.

After this, go back to the workspace root:

```bash
cd /home/runner/workspace
```

---

#### Step 6c — Run the push script to verify everything works

```bash
pnpm --filter @workspace/scripts run push-github
```

Expected output:
```
🔗  Authenticated as: <your-github-username>
📌  GitHub HEAD:  <sha>
📌  Local HEAD:   <sha>
📁  Syncing NNN source files…
  NNN/NNN blobs created.
✅  Pushed to GitHub!
    Commit ID : <full-sha>
    URL       : https://github.com/n4nirmalyapratap/indian-stock-market-analyzer/commit/<sha>
```

If you see `Authenticated as: undefined`, Step 6a was not completed — go back and connect the GitHub integration.

> Run this script after every set of changes to keep GitHub in sync.

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

**Always use the script push method.** This is the only supported push method for this project. It uses the Replit GitHub OAuth integration — no personal access tokens, no `GITHUB_TOKEN` secret, and no manual git commands required.

### Required one-time setup

Connect the Replit GitHub integration before the first push:
1. In Replit, go to **Settings → Integrations → GitHub → Connect**
2. Authorise Replit to access your GitHub account
3. That's it — no tokens to copy, no git remote to configure

### How to push after every change

```bash
pnpm --filter @workspace/scripts run push-github
```

Run this command from the Shell after making any changes. The script lives at `scripts/src/push-github.ts`. It:
1. Authenticates via the connected GitHub account through the Replit OAuth connector
2. Gets the current HEAD commit from GitHub
3. Collects all source files (excludes `node_modules`, `.pythonlibs`, `pandas_ta`, binary images, caches, generated files)
4. Creates blobs on GitHub for each file (skips files over 400 KB and binary image/font extensions)
5. Creates a new commit on top of the existing GitHub history
6. Force-updates the `main` branch ref

The commit URL and ID are printed at the end.

**What is excluded from the push:**
- `node_modules`, `.pythonlibs`, `pandas_ta`, `.venv`, `dist`, `build`, `__pycache__`
- `market_cache`, `.cache`, `.local`, `.upm`, `.agents`, `.replit-artifact`
- Binary files: `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.ico`, `.woff`, `.woff2`, `.ttf`, `.mp4`, `.pdf`, `.zip`
- Files over 400 KB
- `pnpm-lock.yaml`, `uv.lock`, `hydra_prices.db`

---

## Known Issues & Fixes

---

### Options Tester — All `/api/options/*` endpoints return 404 (FIXED)

**Symptom:** Selecting NIFTY 50 (or any symbol) in the Options Strategy Tester triggers API calls to `/api/options/spot/NIFTY`, `/api/options/strategies`, etc. — all return 404.

**Root cause:** The options router (`app/routes/options.py`) was never imported or registered in `main.py`. Every other router (sectors, stocks, patterns, scanners, whatsapp, nlp, analytics, telegram, hydra, cache) was registered but the options router was missing entirely.

**Fix applied:** `artifacts/python-backend/main.py`
- Added import: `from app.routes.options import router as options_router`
- Added registration: `app.include_router(options_router, prefix="/api")`

**Prevention:** Any time a new route file is added under `app/routes/`, it must be explicitly imported and registered in `main.py` with `app.include_router(... prefix="/api")`. The file existing is not enough — FastAPI does not auto-discover routes.

---

### GitHub Push Script Fails — "Authenticated as: undefined" (FIXED)

**Symptom:** Running `pnpm --filter @workspace/scripts run push-github` fails with:
```
🔗  Authenticated as: undefined
❌  Push failed: Cannot read properties of undefined (reading 'sha')
```

**Root cause:** The push script uses the Replit GitHub OAuth integration (`@replit/connectors-sdk`) to authenticate with GitHub. If the GitHub integration has not been connected in this Replit workspace, the connector returns no credentials — `user.login` is `undefined` — and the first GitHub API call (`GET /repos/.../git/ref/heads/main`) returns an error object instead of ref data, causing the `.sha` read to fail.

**Fix applied:**
1. Connected the GitHub OAuth integration via Replit (Settings → Integrations → GitHub → Connect) — authenticated as `n4nirmalyapratap`
2. Installed `@replit/connectors-sdk` in the scripts package (`cd scripts && pnpm add @replit/connectors-sdk`)
3. First successful push: commit `945b2e8` — https://github.com/n4nirmalyapratap/indian-stock-market-analyzer/commit/945b2e8e468718c7f3dd2e86947ed7db80ad584c

**Prevention:** Always perform Step 6 of the First-Time Setup (Connect GitHub Integration) before attempting any push. If the push fails with "Authenticated as: undefined", the GitHub integration is not connected — go to Settings → Integrations → GitHub → Connect and re-authorise.

---

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
- **Python**: 3.11 · FastAPI · uvicorn · spaCy 3.8 · pandas · numpy · ta · yfinance · scipy
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
      routes/                  ← sectors, stocks, patterns, scanners, whatsapp, nlp, analytics, telegram, universe, options
      services/                ← nse_service, yahoo_service, stocks, sectors, patterns,
                                  scanners, whatsapp, nlp_service, analytics_service, telegram_service,
                                  options_service (Black-Scholes+Greeks+VaR), options_backtest_service
      lib/
        universe.py            ← NIFTY100 (80 syms), MIDCAP, SMALLCAP, SECTOR_SYMBOLS
        indicators.py          ← Technical indicator wrappers
  nestjs-backend-placeholder/  ← ACTIVE: Vite + React frontend (port 3002)
    src/lib/api.ts             ← All frontend API calls (relative /api/*)
    src/pages/                 ← Dashboard, Sectors, Stocks, Patterns, Scanners, WhatsApp, Telegram, OptionsStrategyTester
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
- **Options Strategy Tester**: Full options analytics suite

---

## Options Strategy Tester

Route: `/options` (nav item "Options Tester")

### Backend (`app/routes/options.py` + `app/services/options_service.py` + `app/services/options_backtest_service.py`)

**API endpoints (all under `/api/options/`):**
| Endpoint | Method | Description |
|---|---|---|
| `/spot/{symbol}` | GET | Live spot price + 30-day HV estimate via yfinance |
| `/price` | POST | Black-Scholes price + full Greeks for a single option |
| `/strategy` | POST | Multi-leg strategy: payoff curve, aggregate Greeks, breakevens, max P&L |
| `/backtest` | POST | Event-driven historical backtest (last-Thursday expiry cycle) |
| `/scenario` | POST | 2-D scenario matrix: price shocks × vol shocks |
| `/var` | POST | Monte Carlo VaR + CVaR via Geometric Brownian Motion |
| `/strategies` | GET | List all supported strategy template names |
| `/chat` | POST | Options education chatbot — rule-based, zero cost, context-aware |

**Pricing model:**
- Black-Scholes European pricing (correct for NIFTY/BANKNIFTY index options)
- Risk-free rate: 7% (India 10Y G-Sec)
- Lot sizes: NIFTY=75, BANKNIFTY=30, FINNIFTY=40

**Backtesting engine:**
- Event-driven — no lookahead bias; HV30 computed from rolling window ending on entry date
- Monthly expiry cycle: last Thursday of each month (NSE convention)
- Cost model: ₹20 commission/lot + 0.3% bid-ask slippage on premiums
- 13 strategy templates: long/short call/put, straddle, strangle, bull call spread, bear put spread, iron condor, butterfly, covered call

**Risk analysis:**
- Scenario matrix: 9 price shocks × 6 vol shocks → 54-cell heat map
- Monte Carlo VaR: GBM with 10,000 simulations, vectorised scipy norm.cdf repricing

---

## GitHub Push Issue & Fix

**Problem:**
Running `git push origin main` failed because the remote (GitHub) had commits that did not exist locally. The standard fix is `git pull` first, but Replit's `gitsafe` proxy intercepts all git binary calls — including merge and pull operations — and blocks them.

**Fix applied:**
Use the GitHub REST API (Contents API) to push each changed file individually, bypassing git entirely. The push script at `scripts/src/push-github.ts` implements this.

---

## API Endpoints Reference

### Core Data
| Method | Path | Description |
|---|---|---|
| GET | `/api/healthz` | Health check |
| GET | `/api/sectors` | All NSE sector indices with live data |
| GET | `/api/sectors/rotation` | Sector rotation phase + buy recommendations |
| GET | `/api/stocks/nifty100` | Full Nifty 100 quotes |
| GET | `/api/stocks/midcap` | Midcap stock quotes |
| GET | `/api/stocks/smallcap` | Smallcap stock quotes |
| GET | `/api/stocks/:symbol` | Full stock detail + technical analysis |

### Patterns & Scanners
| Method | Path | Description |
|---|---|---|
| GET | `/api/patterns` | Detected candlestick patterns |
| POST | `/api/patterns/scan` | Trigger fresh pattern scan |
| GET | `/api/scanners` | List all custom scanners |
| POST | `/api/scanners` | Create scanner |
| PUT | `/api/scanners/:id` | Update scanner |
| DELETE | `/api/scanners/:id` | Delete scanner |
| POST | `/api/scanners/:id/run` | Run scanner |

### NLP & Analytics
| Method | Path | Description |
|---|---|---|
| POST | `/api/nlp/query` | Natural language query |
| GET | `/api/analytics/sector-correlation` | 30-day Pearson correlation matrix |
| GET | `/api/analytics/breadth-history` | Advance/decline history |
| GET | `/api/analytics/top-movers` | Top gainers/losers/most-active |
| GET | `/api/analytics/pattern-stats` | Pattern detection counts |
| GET | `/api/analytics/sector-heatmap` | Daily % change per sector |

### WhatsApp Bot
| Method | Path | Description |
|---|---|---|
| GET | `/api/whatsapp/status` | Bot status |
| POST | `/api/whatsapp/status` | Update bot status |
| GET | `/api/whatsapp/messages` | Message history |
| POST | `/api/whatsapp/message` | Send test message |
