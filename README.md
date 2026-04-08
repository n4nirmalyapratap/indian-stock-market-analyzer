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
| WhatsApp | Twilio (webhook-based) |

> **Node.js is NOT used for any active functionality.**
> The `artifacts/nestjs-backend/` and `artifacts/api-server/` directories are
> retained for historical reference only and are marked DEPRECATED. Do not start
> those servers or reference them in new code.

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
│   │       │   ├── nse_service.py
│   │       │   ├── yahoo_service.py
│   │       │   ├── stocks_service.py
│   │       │   ├── sectors_service.py
│   │       │   ├── patterns_service.py
│   │       │   ├── scanners_service.py
│   │       │   ├── whatsapp_service.py
│   │       │   ├── nlp_service.py      ← spaCy NLP pipeline
│   │       │   └── analytics_service.py← Correlation, heatmap, breadth, movers
│   │       └── lib/
│   │           ├── universe.py  ← Nifty100, Midcap, Smallcap, SECTOR_SYMBOLS
│   │           └── indicators.py
│   │
│   ├── nestjs-backend-placeholder/  ← ACTIVE: React/Vite frontend (port 3002)
│   │   └── src/
│   │       ├── lib/api.ts       ← All API calls (relative /api, proxied to Python)
│   │       └── pages/           ← Dashboard, Sectors, Patterns, Scanners, WhatsApp
│   │
│   ├── nestjs-backend/          ← DEPRECATED (reference only, not started)
│   └── api-server/              ← DEPRECATED (reference only, not started)
```

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

This project runs on **Replit** with the following modules enabled in `.replit`:
- `nodejs-24` (for the React/Vite frontend only)
- `python-3.11` (for the FastAPI backend)

### First-time setup (new Replit account)

1. **Import from GitHub**
   - Fork or import `n4nirmalyapratap/indian-stock-market-analyzer` into your Replit account.

2. **Install Python dependencies**
   ```bash
   cd artifacts/python-backend
   pip install -r requirements.txt
   python3 -m spacy download en_core_web_sm --break-system-packages
   ```
   > Note: `run.py` auto-downloads the spaCy model if it is missing, so step 2 is optional.

3. **Install Node.js dependencies** (frontend only)
   ```bash
   pnpm install
   ```

4. **Set environment variables** (optional — for WhatsApp bot)
   - `SESSION_SECRET` — any random string (session security)
   - Twilio credentials if you want the WhatsApp webhook to work

5. **Start workflows**
   - The `Project` run button starts both **Python Backend** (port 8090) and
     **Stock Market Frontend** (port 3002) automatically.
   - The frontend Vite dev server proxies all `/api` calls to `http://localhost:8090`.

### Do NOT start these servers
- `artifacts/nestjs-backend/` — DEPRECATED, no workflow configured
- `artifacts/api-server/` — DEPRECATED, no workflow configured

---

## Development Notes

- **All new features go into `artifacts/python-backend/`** — Python only.
- **Frontend changes go into `artifacts/nestjs-backend-placeholder/src/`**.
- The frontend uses relative `/api/*` paths; the Vite proxy routes them to the Python backend.
- `pandas-ta` is not available on PyPI for Python 3.11+ — the project uses a custom shim
  at `artifacts/python-backend/pandas_ta/` that wraps the `ta` library.
- The `ta` library mirrors `pandas-ta` API for EMA, RSI, MACD, Bollinger Bands, and ATR.

---

## GitHub

Repository: [n4nirmalyapratap/indian-stock-market-analyzer](https://github.com/n4nirmalyapratap/indian-stock-market-analyzer)

All commits are pushed to the `main` branch after each set of changes.
