# Frontend Index

This file is a quick index for the user-facing React app in `artifacts/stock-market-app`.

## Purpose

- Serves the main stock analysis product at `/`
- Talks to the Python backend through relative `/api/*` requests
- Uses React, Vite, TypeScript, Wouter, TanStack Query, Tailwind, and shadcn/ui

## Markdown Sources Reviewed

- Root `README.md`
- Root `SETUP.md`
- Root `replit.md`
- Root `DOCUMENTATION_INDEX.md`

## Main Entry Points

| File | Role |
|---|---|
| `src/main.tsx` | React bootstrap |
| `src/App.tsx` | App root, auth gate, router, providers |
| `src/LayoutShell.tsx` | Desktop/mobile shell and primary navigation |
| `src/lib/api.ts` | Typed API client for user-facing backend calls |
| `src/context/CustomAuthContext.tsx` | Email/password auth state stored in `localStorage` |
| `src/context/ThemeContext.tsx` | Theme state and theme toggle behavior |

## Routed Pages

These routes are wired in `src/App.tsx`.

| Route | File | Main responsibility |
|---|---|---|
| `/` | `src/pages/Dashboard.tsx` | Sector rotation overview and top market signals |
| `/trading` | `src/pages/TradingPlatform.tsx` | Trading/chart workspace and symbol search |
| `/sectors` | `src/pages/Sectors.tsx` | Sector rotation and sector heatmap views |
| `/sectors/:sectorId` | `src/pages/SectorDetail.tsx` | Deep sector analytics and constituents |
| `/sentiment` | `src/pages/SentimentDashboard.tsx` | Market and sector sentiment views |
| `/news` | `src/pages/NewsFeed.tsx` | News feed, deals, events, and stats |
| `/stocks` | `src/pages/StockLookup.tsx` | Single-stock lookup |
| `/patterns` | `src/pages/Patterns.tsx` | Candlestick pattern scans |
| `/scanners` | `src/pages/Scanners.tsx` | Saved and ad hoc stock scanners |
| `/hydra` | `src/pages/HydraAlpha.tsx` | Hydra AI analysis tools |
| `/options` | `src/pages/OptionsStrategyTester.tsx` | Options pricing, strategy, scenario, and backtest tools |
| `/settings` | `src/pages/SettingsPage.tsx` | User settings and sign-out |
| `/chart/:symbol` | `src/pages/ChartView.tsx` | Focused chart page for a symbol |

## Present But Not Routed

These files exist but are not currently mounted in `src/App.tsx`.

- `src/pages/LandingPage.tsx`
- `src/pages/LoginPage.tsx` is rendered through the auth gate, not the route switch
- `src/pages/WhatsAppBot.tsx`
- `src/pages/TelegramBot.tsx`

## Important Component Areas

| Path | What is there |
|---|---|
| `src/components/trading/` | Chart panel, watchlist, and trading UI pieces |
| `src/components/technicals/` | Technical summary widgets |
| `src/components/financials/` | Stock financial data views |
| `src/components/GlobalAssistant.tsx` | Global assistant UI using `/options/chat` |
| `src/components/ui/` | Shared shadcn-style primitives |
| `src/lib/__tests__/` | Unit tests for indicators, options utils, and smart builder logic |

## Backend Touchpoints

Most pages call the shared client in `src/lib/api.ts`, which maps to these backend groups:

- `/auth/*` for email/password login and registration
- `/stocks/*` for quotes, history, technical summary, and financials
- `/sectors/*` and `/sector-analytics/*` for sector dashboards
- `/patterns/*` and `/scanners/*` for scan workflows
- `/news/*` for feed, deals, events, and stats
- `/options/*` for options analytics and assistant chat
- `/hydra/*` for Hydra AI tools
- `/sentiment/*` for market sentiment
- `/telegram/*` and `/whatsapp/*` for bot tooling

## Navigation Summary

The main sidebar is defined in `src/LayoutShell.tsx` as:

- Dashboard
- Chart Studio
- Market Sectors
- Sentiment
- News Feed
- Stock Lookup
- Patterns
- Scanners
- AI Analyzer
- Options Tester
- Settings

## Related Repo Docs

- Root `README.md` for overall architecture and deployment notes
- Root `SETUP.md` for local, Docker, auth, and routing setup
- Root `replit.md` for Replit workflows, hard rules, and feature notes
- Root `DOCUMENTATION_INDEX.md` for the markdown-level doc map
