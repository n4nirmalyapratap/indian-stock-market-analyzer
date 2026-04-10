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

## Dark / Light Mode — CRITICAL UI RULE

**Every UI change must fully support both dark and light mode. No exceptions.**

### How it works

- `ThemeContext` (`src/context/ThemeContext.tsx`) manages the theme state.
- It toggles the `dark` class on `<html>` (i.e. `document.documentElement`).
- Theme is persisted in `localStorage` under the key `"app-theme"`. Default is `"dark"`.
- To read the current theme: `const { theme, toggle } = useTheme()` from `ThemeContext`.

### CSS approach

- Light mode variables are defined on `:root` in `src/index.css`.
- Dark mode variables are defined on `.dark` in `src/index.css`.
- All color tokens use CSS custom properties (e.g. `var(--background)`, `var(--foreground)`, `var(--card)`, `var(--border)`, etc).
- **Never hardcode hex colors or Tailwind static colors** (e.g. avoid `bg-white`, `text-gray-900`).

### Tailwind approach

- Use semantic Tailwind classes that reference CSS variables: `bg-background`, `text-foreground`, `border-border`, `bg-card`, `text-card-foreground`, etc.
- For elements that need explicit dark overrides, use the `dark:` variant: e.g. `bg-gray-100 dark:bg-gray-800`.
- Charts and canvas elements must set background/text colors dynamically using the `theme` value from `useTheme()`.

### ⚠️ Glass / Transparent elements — SPECIAL RULE

**Frosted-glass styles (backdrop-blur + bg-white/10, bg-black/10, etc.) are ONLY safe in dark mode.**
On a light background, transparent whites become invisible and white text disappears entirely.

**Rule:** Any element that uses transparency or glass must define BOTH modes explicitly:

```
✅ CORRECT
bg-indigo-600 dark:bg-white/10          ← solid visible color in light, glass in dark
text-white                              ← readable on indigo bg (light) AND on dark glass
border-indigo-500 dark:border-white/20  ← always visible

❌ WRONG
bg-white/15 text-white/90              ← invisible white-on-white in light mode
bg-transparent text-white              ← white text vanishes on light backgrounds
```

**Pattern to follow for floating buttons, badges, overlays:**
- Light mode: use a solid, branded color (e.g. `bg-indigo-600 text-white`)
- Dark mode: use glass (e.g. `dark:bg-white/10 dark:text-white dark:border-white/20`)

### Checklist for every new component or page

- [ ] No hardcoded light-only or dark-only colors
- [ ] All backgrounds use `bg-background`, `bg-card`, `bg-sidebar`, or `dark:` variants
- [ ] All text uses `text-foreground`, `text-muted-foreground`, or `dark:` variants
- [ ] All borders use `border-border` or `dark:` variants
- [ ] Charts/canvas use dynamic colors derived from the current `theme`
- [ ] **Glass/transparent elements**: solid color in light mode + glass in dark mode
- [ ] Test mentally in BOTH modes before submitting — especially for floating or overlaid UI

---

## Active Services

| Workflow | Command | Port | Purpose |
|---|---|---|---|
| **artifacts/api-server: API Server** | `bash -c 'cd /home/runner/workspace/artifacts/python-backend && PORT=8090 python run.py'` | 8090 | FastAPI — all stock/analytics/NLP APIs |
| **artifacts/stock-market-app: web** | `BASE_PATH=/ PORT=19845 pnpm --filter @workspace/stock-market-app run dev` | 19845 | React/Vite frontend |

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
- `pnpm --filter @workspace/stock-market-app run dev` — start frontend manually
- `curl http://localhost:8090/api/healthz` — verify Python backend is live
- `curl http://localhost:80/api/sectors/rotation` — verify full proxy routing works

---

## Global AI Assistant

A floating chat button (bottom-right, every page) powered by the rule-based backend — **zero cost, no paid API**.

- **Frontend**: `artifacts/stock-market-app/src/components/GlobalAssistant.tsx`
- **Backend**: `artifacts/python-backend/app/routes/assistant.py` → `POST /api/assistant/chat`
- Handles: stock analysis, sector overview, sector rotation, pattern scans, scanner runs, and education Q&A (RSI, MACD, options, P/E, etc.)
- Uses the existing NLP intent parser + live market data services
- Returns all answers in simple, plain English

---

## Project Structure

```
artifacts/python-backend/                       ← ACTIVE: FastAPI backend (port 8090)
  app/routes/assistant.py                       ← Global assistant endpoint
  app/routes/nlp.py                             ← NLP query endpoint
  app/services/nlp_service.py                   ← Intent + entity parser
artifacts/stock-market-app/                     ← ACTIVE: React/Vite frontend (port 19845)
  src/components/GlobalAssistant.tsx            ← Floating AI chat panel (global)
  src/App.tsx                                   ← Root — GlobalAssistant mounted here
artifacts/nestjs-backend/                       ← DEPRECATED (reference only)
artifacts/api-server/                           ← DEPRECATED Node.js server; artifact.toml now points to Python backend
scripts/src/push-github.ts                      ← GitHub push script (uses Replit GitHub connector)
```

---

## Code Review Fixes (April 2026)

The following bugs were found in a deep code review and fixed:

1. **main.py** — Removed TEST MODE warmup block; startup cache warmup now correctly gated behind `not is_market_open() AND cache_is_thin` check
2. **SectorDetail.tsx** — Fixed period selector (3MO/6MO/1Y/5Y) so clicking a period now lifts state to parent and triggers a React Query refetch with the new period; previous local state was disconnected from the API call
3. **sectors_service.py** — Fixed all 4 SECTOR_INDICES Yahoo tickers that were using proxy stocks instead of real index tickers: NIFTY FINANCIAL SERVICES → `^CNXFIN`, NIFTY CONSUMER DURABLES → `^CNXCONDURAB`, NIFTY OIL AND GAS → `^CNXOILGAS`, NIFTY HEALTHCARE INDEX → `^CNXHEALTH`
4. **sector_analytics_service.py** — Fixed duplicate SECTOR_YAHOO_TICKER mappings: NIFTY OIL AND GAS → `^CNXOILGAS` (was `^CNXENERGY`, a duplicate of NIFTY ENERGY), NIFTY HEALTHCARE → `^CNXHEALTH` (was `^CNXPHARMA`, a duplicate of NIFTY PHARMA)
5. **sector_analytics_service.py** — Fixed heatmap cache key to include trading date (`heatmap:{YYYY-MM-DD}`) so yesterday's cached data is never served on the next day
6. **stocks.py** — Replaced deprecated `asyncio.get_event_loop().run_in_executor()` with `asyncio.to_thread()` (Python 3.10+ best practice)
7. **stocks_service.py** — Replaced silent `except Exception: pass` blocks with `except Exception as e: logger.warning(...)` for observability
8. **api.ts** — Added missing `EconomicPhase`, `PortfolioStrategy`, `PortfolioTopPick` TypeScript interfaces; extended `SectorRotation` with `economicPhase`, `portfolioStrategy`, `timestamp`, `tierCounts`, `tiers`, `topPerformers`, `laggards`, `currentlyFocused`
9. **App.tsx** — Fixed wouter `Route` TypeScript error for `WhatsAppBot`/`TelegramBot` components with optional `embedded` prop
10. **StockChat.tsx** — Replaced invalid `title` prop on Lucide icons with `aria-label`

**Note on `^CNXOILGAS` / `^CNXHEALTH`**: Yahoo Finance does not yet index these newer NSE indices. The backend correctly uses NSE as the primary source; the RS chart will show "Historical data unavailable" for these two sectors since Yahoo doesn't have their history — this is honest behavior, preferable to showing wrong data from a proxy ticker.

---

## GitHub Integration

- Connected via Replit GitHub connector (OAuth — no PAT needed)
- Push script: `scripts/src/push-github.ts`
- Repository: `n4nirmalyapratap/indian-stock-market-analyzer` (branch: `main`)
