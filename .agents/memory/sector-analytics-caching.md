---
name: Sector analytics caching strategy
description: How the 4-layer cache works for sector heatmap drilldown and synthetic sub-industry grid
---

## Layers (innermost → outermost)

### 1. TanStack Query (frontend)
`App.tsx` queryClient: `staleTime: 5*60*1000, gcTime: 30*60*1000` as global defaults.
Individual queries in `SectorAnalytics.tsx` repeat these explicitly for safety.
**Effect:** Second navigate/click within 5 min = zero network requests.

### 2. In-memory TTL (backend, per process)
`sector_analytics_service._CACHE` dict (custom, version-flushed on market state change):
- Heatmap: 5 min open / 4 h closed
- Sector detail: 15 min open / 4 h closed
- yf.info fundamentals: 4 h

`synthetic_sectors_service._GRID_CACHE` / `_DRILLDOWN_CACHE` (MarketTTLCache):
- 5 min open / 4 h closed

**Effect:** After first build, all repeat calls within TTL return instantly.

### 3. Disk-level fundamentals (backend, survives restarts)
`market_cache/fundamentals/<ticker_slug>.json`, TTL 7 days.
Written by `_save_fund_disk()`, read by `_load_fund_disk()` before Yahoo call.
`_fund_ticker_slug()` replaces `^` → `idx_`, `.` → `_`, `/` → `_`.
**Effect:** yf.Ticker.info (slow ~1-2s per stock) avoided on cold starts.

### 4. Startup pre-warm
`_cache_warmup_task()` in `main.py` calls `pre_warm_sector_details(svc.sector_analytics)`
after `_srs.prewarm()`. Loops all 14 `SECTOR_YAHOO_TICKER` entries, skips cached ones.
Only runs when market is CLOSED (returns early if open).
**Effect:** First user click on any sector after restart served from cache.

## What NOT to cache (stay honest)
- `/api/sectors/` live quotes — these must always be fresh during market hours
- Nightly metrics grid (synthetic_sector_daily_metrics) — nightly worker handles freshness, cache just avoids re-reading DB on every page load

**Why:** User reported slow heatmap clicks. Root cause was yf.Ticker.info
for 10 stocks × ~1-2s each = 10-20s cold load, no disk persistence across restarts.
