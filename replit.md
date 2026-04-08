# Indian Stock Market Analyzer

## Overview

Full-stack Indian stock market analysis platform with NSE sector rotation tracking, chart pattern detection, stock scanners, and WhatsApp bot integration.

Source: https://github.com/n4nirmalyapratap/indian-stock-market-analyzer

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **Backend**: NestJS (artifacts/nestjs-backend) — port 3001
- **Frontend**: Next.js 14 (artifacts/nextjs-frontend) — port 3000
- **Data sources**: NSE India API, Yahoo Finance
- **Bot**: WhatsApp Web.js integration

## Key Commands

- `pnpm --filter @workspace/nestjs-backend run dev` — run NestJS backend
- `pnpm --filter @workspace/nextjs-frontend run dev` — run Next.js frontend
- Swagger API docs: http://localhost:3001/api/docs

## Workflows

- **NestJS Backend** — runs the NestJS API on port 3001
- **Next.js Frontend** — runs the Next.js UI on port 3000

## Features

- NSE Sector Rotation analysis (15 sector indices)
- Chart pattern detection (CALL/PUT signals)
- Stock scanner with custom filters
- Individual stock technical analysis (EMA, RSI, MACD, Bollinger Bands)
- WhatsApp bot for automated alerts
- Swagger API documentation
