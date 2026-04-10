# Indian Stock Market Analyzer

A real-time Indian stock market analysis platform with sector rotation tracking,
candlestick pattern detection, custom stock scanners, Hydra Alpha signals,
NLP-powered queries, and a full admin panel — all powered by a **Python FastAPI backend**.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 · FastAPI · uvicorn |
| Data sources | NSE India API · Yahoo Finance |
| NLP | spaCy 3.8 (rule-based EntityRuler) |
| Analytics | pandas · numpy |
| Technical indicators | `ta` library (EMA, RSI, MACD, Bollinger Bands, ATR, VWAP) |
| User frontend | React 18 · Vite · TypeScript · TailwindCSS · TanStack Query |
| Admin dashboard | React 18 · Vite · TypeScript · TailwindCSS · TanStack Query |
| Router | wouter (NOT react-router) |
| UI | shadcn/ui |
| Charts | Lightweight Charts · ECharts · Recharts |
| Auth | Custom email+password (HS256 JWT) — no Clerk, no Google OAuth |
| WhatsApp | Twilio webhook (backend only — `/api/whatsapp/*`) |

> **Node.js is used only for the React/Vite frontends** (build tooling + dev server).
> All Node.js / NestJS *backend* directories have been **permanently deleted** — the backend is Python only.

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
│   │   ├── tests/               ← pytest unit tests (116 tests)
│   │   │   ├── conftest.py      ← shared fixtures (OHLCV builders, candle makers)
│   │   │   ├── test_indicators.py   ← SMA/EMA/RSI/MACD/BB/ATR/VWAP/S&R (50 tests)
│   │   │   ├── test_data_quality.py ← RSI/MACD/BB/Z-score/VWAP/Hydra/cross-indicator (27 tests)
│   │   │   ├── test_patterns.py     ← candle helpers, doji, hammer, engulfing (29 tests)
│   │   │   └── test_log_buffer.py   ← log buffer ring tests (10 tests)
│   │   └── app/
│   │       ├── routes/          ← FastAPI route modules
│   │       │   ├── sectors.py   ← GET /api/sectors, /api/sectors/rotation
│   │       │   ├── stocks.py    ← GET /api/stocks/nifty100, /api/stocks/:symbol
│   │       │   ├── patterns.py  ← GET /api/patterns, POST /api/patterns/scan
│   │       │   ├── scanners.py  ← CRUD /api/scanners, POST /api/scanners/:id/run
│   │       │   ├── whatsapp.py  ← /api/whatsapp/* (backend webhook only)
│   │       │   ├── nlp.py       ← POST /api/nlp/query (natural language)
│   │       │   └── analytics.py ← GET /api/analytics/* (5 endpoints)
│   │       ├── services/        ← Business logic
│   │       └── lib/
│   │           ├── universe.py  ← Nifty100, Midcap, Smallcap, SECTOR_SYMBOLS
│   │           └── indicators.py
│   │
│   ├── stock-market-app/        ← ACTIVE: User frontend (port 3002 / path "/")
│   │   ├── .replit-artifact/artifact.toml
│   │   ├── vite.config.ts       ← proxies /api/* → localhost:8090
│   │   ├── vitest.config.ts     ← frontend unit test config
│   │   └── src/
│   │       ├── lib/
│   │       │   ├── api.ts       ← All API calls (relative /api, proxied to Python)
│   │       │   ├── indicators.ts    ← Client-side SMA/EMA/RSI/MACD/BB
│   │       │   └── __tests__/   ← Vitest unit tests (37 tests)
│   │       ├── context/
│   │       │   └── CustomAuthContext.tsx  ← Email+password auth (no Clerk)
│   │       └── pages/           ← Dashboard, Sectors, Patterns, Scanners, etc.
│   │
│   ├── admin-dashboard/         ← ACTIVE: Admin panel (path "/admin")
│   │   ├── .replit-artifact/artifact.toml
│   │   └── src/
│   │       ├── lib/api.ts       ← Admin API calls (X-Admin-Token header)
│   │       └── pages/
│   │           ├── LogsPage.tsx ← Live logs: Summary view + Raw terminal view
│   │           ├── OverviewPage.tsx
│   │           ├── UsersPage.tsx
│   │           └── SettingsPage.tsx
│   │
│   ├── api-server/              ← ROUTING SHIM ONLY — do NOT touch
│   │   └── .replit-artifact/artifact.toml
│   │       ← localPort=8090, paths=["/api"]
│   │       ← Tells Replit proxy to route /api/* → Python backend
│   │
│   └── mockup-sandbox/          ← Canvas design preview (do not touch)
│
├── scripts/
│   └── src/push-github.ts       ← GitHub push via Replit connector
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

3. **Set environment variables**
   - `SESSION_SECRET` — JWT signing secret (required)
   - `ADMIN_USERNAME` / `ADMIN_PASSWORD` — admin panel credentials (required)
   - Twilio credentials if you want the WhatsApp webhook (optional)

4. **Start all four workflows** (Replit starts them automatically)
   - `artifacts/api-server: API Server` — Python FastAPI backend on port 8090
   - `artifacts/stock-market-app: web` — user Vite app on port 3002
   - `artifacts/admin-dashboard: web` — admin Vite app on port 22133

5. **Verify**
   ```bash
   curl http://localhost:8090/api/healthz   # → {"status":"ok"}
   ```

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

## Docker Deployment (AWS / Azure / self-hosted)

The project ships with a complete Docker setup — two containers, one command.

### Architecture

```
                  ┌─────────────────────────────┐
Browser ──────────►  frontend container (nginx)  │ :80
                  │                             │
                  │  /api/*  ──────────────────►│───► backend:8090
                  │  /*  → React SPA (static)   │
                  └─────────────────────────────┘
                                                    │
                                          ┌─────────▼──────────┐
                                          │  backend container  │ :8090
                                          │  Python FastAPI     │
                                          └────────────────────┘
```

### Quick start (local)

```bash
# Build and start both containers
docker compose up --build

# App is live at:
open http://localhost

# Verify backend health:
curl http://localhost/api/healthz
```

### Production (detached)

```bash
SESSION_SECRET=your-secret docker compose up --build -d
```

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `SESSION_SECRET` | **Yes** | JWT signing secret — use a long random string |
| `ADMIN_USERNAME` | **Yes** | Admin panel login username (default: `admin`) |
| `ADMIN_PASSWORD` | **Yes** | Admin panel login password — make it strong |
| `TWILIO_ACCOUNT_SID` | No | WhatsApp webhook via Twilio |
| `TWILIO_AUTH_TOKEN` | No | WhatsApp webhook via Twilio |

Pass them in a `.env` file at the repo root — Docker Compose picks it up automatically:
```bash
cp .env.example .env
# then edit .env
```

### Deploying to AWS / Azure

**AWS ECS (Fargate):**
1. Push images to ECR: `docker tag stock-backend <ecr-url>; docker push`
2. Create two ECS task definitions (backend + frontend)
3. Put an ALB in front: `/api/*` → backend target group, `/*` → frontend target group

**Azure Container Apps:**
1. Push to ACR: `az acr build ...`
2. Deploy two container apps in the same environment
3. Set `BACKEND_URL=http://backend` (Container Apps resolves by name within the env)

**Self-hosted (EC2 / VM):**
```bash
git clone https://github.com/n4nirmalyapratap/indian-stock-market-analyzer
cd indian-stock-market-analyzer
echo "SESSION_SECRET=changeme" > .env
docker compose up --build -d
```

### Key files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Orchestrates both containers |
| `artifacts/python-backend/Dockerfile` | Python 3.11 + FastAPI backend image |
| `artifacts/stock-market-app/Dockerfile` | Node 24 build → nginx static image |
| `artifacts/stock-market-app/nginx.conf` | Serves SPA + proxies `/api/*` to backend |
| `.dockerignore` | Excludes `node_modules`, caches, deprecated folders |

---

## Testing

The project has a three-layer test suite.

### Backend unit tests (pytest — 221 tests)

```bash
cd artifacts/python-backend
python3 -m pytest tests/ -v
```

| File | Tests | What it covers |
|---|---|---|
| `test_indicators.py` | 50 | SMA, EMA, RSI, MACD, Bollinger Bands, ATR, VWAP, Support/Resistance |
| `test_data_quality.py` | 27 | RSI range, MACD structure, Z-score, VWAP cumulative behaviour |
| `test_patterns.py` | 29 | Candle helpers, doji, hammer, shooting star, engulfing |
| `test_log_buffer.py` | 10 | Ring-buffer log store |
| `test_hydra.py` | 105 | Full Hydra-Alpha Engine — all 7 services: symbol extraction, intent routing, NLP pipeline, forecast output contract, sentiment scoring, OU pairs calibration + signals, VaR calculator, event-driven backtester |

### Frontend unit tests (Vitest — 37 tests)

```bash
pnpm --filter @workspace/stock-market-app run test
```

Tests cover all five client-side indicator functions in `src/lib/indicators.ts`:
`calcSMA`, `calcEMA`, `calcRSI`, `calcMACD`, `calcBollingerBands`.

### End-to-end tests (Playwright)

Run via the Replit testing skill — covers login flows, dashboard rendering,
admin Logs page (Summary view + Raw terminal view), and level filtering.

---

## GitHub

Repository: [n4nirmalyapratap/indian-stock-market-analyzer](https://github.com/n4nirmalyapratap/indian-stock-market-analyzer)

To push: `pnpm --filter @workspace/scripts run push-github`

See `GITHUB_PUSH.md` for full push documentation including automatic OAuth setup.

All commits are pushed to the `main` branch after each set of changes.
