# Indian Stock Market Analyzer

## Overview

Full-stack Indian stock market analysis platform with NSE sector rotation tracking, chart pattern detection, stock scanners, and WhatsApp bot integration.

**Source:** https://github.com/n4nirmalyapratap/indian-stock-market-analyzer

> All Replit compatibility fixes are already committed to GitHub. When you clone fresh in any Replit account, everything should work without manual fixes.

---

## Architecture

```
Stock Market Frontend  (Vite + React, port 3002)
    ↓ proxies /api to localhost:8080
API Server             (Express, port 8080)   ← main data backend
    ↓ fetches data from NSE / Yahoo Finance

NestJS Backend         (NestJS, port 3001)    ← WhatsApp bot + separate API
    Swagger: http://localhost:3001/api/docs
```

---

## Folder Structure

```
artifacts/
  api-server/                  ← Express backend (port 8080) — stock data API
  nestjs-backend/              ← NestJS backend (port 3001) — WhatsApp bot
  nestjs-backend-placeholder/  ← Vite + React frontend (port 3002) — main UI
  mockup-sandbox/              ← Replit canvas tool (managed by artifact system)
lib/
  api-zod/                     ← Zod schemas (used by api-server health check)
scripts/                       ← Utility scripts
```

## Stack

- **Monorepo**: pnpm workspaces
- **Node.js**: 24
- **Package manager**: pnpm
- **TypeScript**: 5.9
- **Frontend**: Vite + React (`artifacts/nestjs-backend-placeholder`)
- **Main backend**: Express 5 (`artifacts/api-server`)
- **WhatsApp backend**: NestJS (`artifacts/nestjs-backend`)
- **Data sources**: NSE India API (with cookie refresh), Yahoo Finance fallback

---

## Workflows

| Workflow Name | Command | Port | Purpose |
|---|---|---|---|
| **Stock Market Frontend** | `BASE_PATH=/ PORT=3002 pnpm --filter @workspace/nestjs-backend-placeholder run dev` | 3002 | Main React UI |
| **NestJS Backend** | `pnpm --filter @workspace/nestjs-backend run dev` | 3001 | WhatsApp bot API |
| **API Server** (artifact) | Managed by artifact system | 8080 | Stock data API |

---

## Key Commands

```bash
# Install all dependencies
pnpm install

# Run specific packages
pnpm --filter @workspace/nestjs-backend-placeholder run dev   # Frontend
pnpm --filter @workspace/nestjs-backend run dev               # NestJS
pnpm --filter @workspace/api-server run dev                   # Express API

# Swagger docs (NestJS)
open http://localhost:3001/api/docs
```

---

## Replit Compatibility Fixes (already applied to GitHub)

These were fixed during the initial Replit setup and are now committed to the repo:

1. **`nestjs-backend/tsconfig.json`** — Added `"esModuleInterop": true`
   - Fixes: `node_cache_1.default is not a constructor` runtime error (CJS interop)

2. **`nestjs-backend/src/main.ts`** — Changed `import * as cors` → `import cors`
   - Fixes: `TS2349: This expression is not callable` TypeScript error

3. **`nestjs-backend/src/modules/sectors/sectors.service.ts`** — Made `parseNseSectorData` async
   - Fixes: `TS2740: Type 'Promise<any[]>' is missing properties from type 'any[]'`

4. **`pnpm-workspace.yaml`** — Added `@nestjs/core` and `puppeteer` to `onlyBuiltDependencies`
   - Fixes: NestJS and Puppeteer (whatsapp-web.js) build scripts not running on install

5. **`REPLIT_SETUP.md`** — Added full setup guide at repo root

---

## Features

- **Dashboard**: Real-time sector rotation, market breadth, CALL/PUT signal count
- **Sectors**: 15 NSE sector indices with performance rankings
- **Stocks**: Individual stock lookup with EMA, RSI, MACD, Bollinger Bands, VWAP
- **Patterns**: Chart pattern detection (candlestick, H&S, Double Top/Bottom, Cup & Handle, etc.)
- **Scanners**: Custom stock filters with visual condition builder and quick templates
- **WhatsApp Bot**: Automated market alerts via WhatsApp Web.js
