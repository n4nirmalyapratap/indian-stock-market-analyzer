// Shared React-Query options for all market-data fetches.
//
// Every page that displays prices uses the same staleTime / refetchInterval
// so they all share the same snapshot. Window focus always re-validates so
// when the user returns to the tab after a market-state transition (open →
// closed) the page snaps to the freshly sealed EOD close instead of serving
// the last intraday number.

import type { QueryKey, UseQueryOptions } from "@tanstack/react-query";
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";

/**
 * Provenance metadata returned by every market-data endpoint.
 *
 *  source     = original provider that produced the price
 *               ("NSE" | "YAHOO")
 *  servedFrom = layer / engine that returned it on this call
 *               ("PRICE_SERVICE" | "DISK_EOD" | "MIXED" | "PATTERNS_ENGINE"
 *               | "SENTIMENT_ENGINE" | "NEWS_FEED")
 */
export interface MarketDataMeta {
  source?:        "NSE" | "YAHOO" | string;
  servedFrom?:    string;
  asOf?:          string | null;
  marketState?:   string;       // "OPEN" | "PRE_OPEN" | "CLOSED" | "WEEKEND"
  cacheVersion?:  number;
  eodSealed?:     boolean;
  eodDate?:       string | null;
  // Stock Lookup carries a separate provenance for the historical-bars block —
  // the quote can be live NSE while the candles came off disk EOD cache.
  historySource?: string;
  historyAsOf?:   string | null;
  historyEodSealed?: boolean;
  historyEodDate?:   string | null;
  // Scanners universe freshness (only present on /scanners endpoints).
  universe?: {
    isLiveUniverse: boolean;
    loadedAt:       string | null;
    ageSeconds?:    number | null;   // age of the live cache file; large ⇒ stale
    totalSymbols:   number;
    totalSectors:   number;
  };
  [key: string]:  unknown;
}

/** Extract `meta` from any payload that might carry it. */
export function pickMeta(payload: unknown): MarketDataMeta | null {
  if (!payload || typeof payload !== "object") return null;
  const m = (payload as { meta?: MarketDataMeta }).meta;
  return m && typeof m === "object" ? m : null;
}

/**
 * IST current time check — markets are 09:15-15:30 IST Mon-Fri.
 * Computed locally so we don't need an extra round-trip just to know
 * the cadence to use.
 */
export function isMarketOpenIST(now: Date = new Date()): boolean {
  const utc = now.getTime() + now.getTimezoneOffset() * 60_000;
  const ist = new Date(utc + 5.5 * 60 * 60_000);
  const day = ist.getDay();              // 0=Sun, 6=Sat
  if (day === 0 || day === 6) return false;
  const minutes = ist.getHours() * 60 + ist.getMinutes();
  return minutes >= 9 * 60 + 15 && minutes <= 15 * 60 + 30;
}

/**
 * Build React-Query options for a market-data query.
 *
 *   Open   market → 60s stale, 60s background refresh
 *   Closed market → 1h stale, NO background polling
 *
 * When closed there is no point polling — EOD bars are frozen until next
 * session. `useMarketStateBoundary` (mounted at the app root) already fires
 * every 30s and invalidates ALL queries the moment the market transitions
 * CLOSED→OPEN, so the first trade of the day is always reflected quickly.
 * `refetchOnWindowFocus: true` handles the user returning to the tab after
 * an overnight gap.
 */
export function marketDataQueryOptions<TData, TOpts extends Record<string, unknown> = Record<string, never>>(
  queryKey: QueryKey,
  queryFn: () => Promise<TData>,
  overrides?: TOpts,
): UseQueryOptions<TData> & TOpts {
  const open = isMarketOpenIST();
  return {
    queryKey,
    queryFn,
    staleTime:            open ? 60_000 : 60 * 60_000,  // 1h when closed — data is frozen
    refetchInterval:      open ? 60_000 : false,          // no polling after close
    refetchOnWindowFocus: true,
    refetchOnReconnect:   true,
    ...(overrides ?? ({} as TOpts)),
  } as UseQueryOptions<TData> & TOpts;
}

/**
 * Hook that watches IST market open/closed state and invalidates ALL
 * market-data queries (`marketData` namespace) the moment the market
 * transitions. This is the deterministic close-boundary invalidation:
 * within 30s of close, every page re-fetches and snaps to the sealed
 * official close instead of holding the last intraday number.
 *
 * Mount once at the app root.
 */
export function useMarketStateBoundary() {
  const qc = useQueryClient();
  const wasOpenRef = useRef<boolean>(isMarketOpenIST());

  useEffect(() => {
    const id = setInterval(() => {
      const open = isMarketOpenIST();
      if (open !== wasOpenRef.current) {
        wasOpenRef.current = open;
        // Invalidate every cached query — cheap because most are inactive,
        // and the active ones will re-fetch under the new cadence.
        void qc.invalidateQueries();
      }
    }, 30_000);
    return () => clearInterval(id);
  }, [qc]);
}

/**
 * Hook giving you a `refresh(keys?)` function that invalidates one or
 * many query keys. Used by `DataFreshness`'s manual Refresh button.
 */
export function useRefreshMarketData() {
  const qc = useQueryClient();
  return useCallback(
    (keys: QueryKey | QueryKey[]) => {
      const list: QueryKey[] = Array.isArray(keys[0]) ? (keys as QueryKey[]) : [keys as QueryKey];
      list.forEach(k => { void qc.invalidateQueries({ queryKey: k }); });
    },
    [qc],
  );
}
