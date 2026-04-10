# Indian Stock Market Analyzer

A real-time Indian stock market analysis platform with sector rotation tracking,
candlestick pattern detection, custom stock scanners, NLP-powered queries, and a
WhatsApp bot — all powered by a **Python FastAPI backend**.

---

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
| WhatsApp | Twilio (webhook-based) |

> **Node.js is NOT used for any active functionality.**
> All previous Node.js / NestJS backend directories have been **permanently deleted**.

---

## Project Structure

```
/
├── artifacts/
│   ├── python-backend/          ← ACTIVE: FastAPI backend (port 8090)
│   │   ├── main.py              ← App entry point, all routers registered
│   │   ├── run.py               ← Startup script (ensures spaCy model is present)
│   │   ├── requirements.txt     ← Python dependencies
│   │   ├── pandas_ta/           ← ta-library shim (mirrors pandas-ta API)
│   │   └── app/
│   │       ├── routes/          ← FastAPI route modules
│   │       │   ├── sectors.py   ← GET /api/sectors, /api/sectors/rotation
│   │       │   ├── stocks.py    ← GET /api/stocks/nifty100, /api/stocks/:symbol
│   │       │   ├── patterns.py  ← GET /api/patterns, POST /api/patterns/scan
│   │       │   ├── scanners.py  ← CRUD /api/scanners, POST /api/scanners/:id/run
│   │       │   ├── whatsapp.py  ← /api/whatsapp/status, /message, /messages
│   │       │   ├── nlp.py       ← POST /api/nlp/query (natural language)
│   │       │   └── analytics.py ← GET /api/analytics/* (5 endpoints)
│   │       ├── services/        ← Business logic
│   │       └── lib/
│   │           ├── universe.py  ← Nifty100, Midcap, Smallcap, SECTOR_SYMBOLS
│   │           └── indicators.py
│   │
│   ├── stock-market-app/        ← ACTIVE: React/Vite frontend (port 3002)
│   │   ├── .replit-artifact/artifact.toml
│   │   ├── vite.config.ts       ← proxies /api/* → localhost:8090
│   │   └── src/
│   │       ├── lib/api.ts       ← All API calls (relative /api, proxied to Python)
│   │       └── pages/           ← Dashboard, Sectors, Patterns, Scanners, WhatsApp
│   │
│   ├── api-server/              ← ROUTING SHIM ONLY — do NOT touch or start
│   │   └── .replit-artifact/artifact.toml
│   │       ← localPort=8090, paths=["/api"]
│   │       ← Tells Replit proxy: route /api/* → Python backend on port 8090
│   │       ← Source code inside this folder is unused; only artifact.toml matters
│   │
│   └── mockup-sandbox/          ← Canvas design tool (do not touch)
│
├── scripts/
│   └── src/push-github.ts       ← GitHub push via Replit connector
├── lib/                         ← Shared TypeScript libraries
├── GITHUB_PUSH.md               ← Push workflow documentation
└── AGENT_PROMPT.md              ← Full agent setup instructions
```

### ⚠️ Deleted Directories (do NOT recreate)

| Directory | Reason removed |
|---|---|
| `artifacts/nestjs-backend/` | Deprecated Node.js/NestJS backend — replaced by Python backend |
| `artifacts/nestjs-backend-placeholder/` | Old frontend placeholder — replaced by `stock-market-app/` |

These folders were permanently removed in the April 2026 cleanup.
If you see them reappear, delete them and push again.

---

## API Endpoints (Python Backend — port 8090)

### Core Data
| Method | Path | Description |
|---|---|---|
| GET | `/api/healthz` | Health check |
| GET | `/api/sectors` | All NSE sector indices with live data |
| GET | `/api/sectors/rotation` | Sector rotation phase + buy recommendations |
| GET | `/api/sectors/:symbol` | Single sector detail |
| GET | `/api/stocks/nifty100` | Full Nifty 100 quotes |
| GET | `/api/stocks/midcap` | Midcap stock quotes |
| GET | `/api/stocks/smallcap` | Smallcap stock quotes |
| GET | `/api/stocks/:symbol` | Full stock detail + technical analysis + entry recommendation |

### Patterns & Scanners
| Method | Path | Description |
|---|---|---|
| GET | `/api/patterns` | Detected candlestick patterns (`?signal=CALL\|PUT&universe=NIFTY100`) |
| POST | `/api/patterns/scan` | Trigger fresh pattern scan |
| GET | `/api/scanners` | List all custom scanners |
| POST | `/api/scanners` | Create scanner |
| PUT | `/api/scanners/:id` | Update scanner |
| DELETE | `/api/scanners/:id` | Delete scanner |
| POST | `/api/scanners/:id/run` | Run scanner, returns matched stocks |

### NLP & Analytics
| Method | Path | Description |
|---|---|---|
| POST | `/api/nlp/query` | Natural language query (e.g. "analyze RELIANCE", "bullish IT stocks") |
| GET | `/api/analytics/sector-correlation` | 30-day Pearson correlation matrix for all 15 sectors |
| GET | `/api/analytics/breadth-history` | Advance/decline history (Nifty 100 sample) |
| GET | `/api/analytics/top-movers` | Top gainers/losers/most-active from Nifty 100 |
| GET | `/api/analytics/pattern-stats` | Pattern detection counts + 5-day backtest success rates |
| GET | `/api/analytics/sector-heatmap` | Daily % change per sector with color coding |

### WhatsApp Bot
| Method | Path | Description |
|---|---|---|
| GET | `/api/whatsapp/status` | Bot status |
| POST | `/api/whatsapp/status` | Update bot status |
| GET | `/api/whatsapp/messages` | Message history |
| POST | `/api/whatsapp/message` | Send test message (NLP-powered) |

---

## Running on Replit

### Requirements

This project runs on **Replit** with:
- `nodejs-24` (for the React/Vite frontend only)
- `python-3.11` (for the FastAPI backend)

### Setup steps

1. **Install Python dependencies**
   ```bash
   cd artifacts/python-backend
   pip install -r requirements.txt
   ```
   > `run.py` auto-downloads the spaCy model (`en_core_web_sm`) on first start.

2. **Install Node.js dependencies** (frontend only)
   ```bash
   pnpm install
   ```

3. **Set environment variables** (optional — for WhatsApp bot)
   - `SESSION_SECRET` — any random string (session security)
   - Twilio credentials if you want the WhatsApp webhook to work

4. **Start workflows**
   - `Python Backend` — `bash -c 'cd artifacts/python-backend && PORT=8090 python run.py'`
   - `artifacts/stock-market-app: web` — starts automatically from `artifact.toml`

5. **Verify**
   ```bash
   curl http://localhost:8090/api/healthz   # → {"status":"ok"}
   ```

### Do NOT start these
- `artifacts/api-server: API Server` — routing shim only, no server code to run

---

## Development Notes

- **All new backend features** go into `artifacts/python-backend/` — Python only
- **Frontend changes** go into `artifacts/stock-market-app/src/`
- Frontend uses relative `/api/*` paths; the Vite proxy routes them to the Python backend
- `pandas-ta` is not available on PyPI for Python 3.11+ — the project uses a custom shim
  at `artifacts/python-backend/pandas_ta/` that wraps the `ta` library
- The `ta` library mirrors `pandas-ta` API for EMA, RSI, MACD, Bollinger Bands, and ATR
- **NEVER touch `artifacts/api-server/` source code** — it is a routing shim only
- **NEVER recreate `artifacts/nestjs-backend/` or `artifacts/nestjs-backend-placeholder/`**

---

## GitHub

Repository: [n4nirmalyapratap/indian-stock-market-analyzer](https://github.com/n4nirmalyapratap/indian-stock-market-analyzer)

To push: `pnpm --filter @workspace/scripts run push-github`

See `GITHUB_PUSH.md` for full push documentation including automatic OAuth setup.

All commits are pushed to the `main` branch after each set of changes.
