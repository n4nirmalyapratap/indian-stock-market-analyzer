// Shared React-Query options for all market-data fetches.
//
// Goal: every page that displays prices uses the same staleTime / refetchInterval
// so they all share the same snapshot. When market is open, refresh more often;
// when closed, prices won't change so we can be lazy.

import type { QueryKey, UseQueryOptions } from "@tanstack/react-query";
import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

/**
 * Provenance metadata returned by every market-data endpoint.
 * Used by DataFreshness to render the "NSE • 5 min ago • Closed" pill.
 */
export interface MarketDataMeta {
  source?:        string;       // "NSE" | "YAHOO" | "DISK" | "LIVE"
  asOf?:          string | null;
  marketState?:   string;       // "OPEN" | "PRE_OPEN" | "CLOSED" | "WEEKEND"
  cacheVersion?: number;
  eodSealed?:    boolean;
  eodDate?:      string | null;
  [key: string]: unknown;
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
  // Convert local time to IST
  const utc = now.getTime() + now.getTimezoneOffset() * 60_000;
  const ist = new Date(utc + 5.5 * 60 * 60_000);
  const day = ist.getDay();              // 0=Sun, 6=Sat
  if (day === 0 || day === 6) return false;
  const minutes = ist.getHours() * 60 + ist.getMinutes();
  return minutes >= 9 * 60 + 15 && minutes <= 15 * 60 + 30;
}

/**
 * Build React-Query options for a market-data query.
 * Open  market → 60s stale, 60s background refresh.
 * Closed market → 5min stale, no auto-refresh (prices won't change).
 */
export function marketDataQueryOptions<TData>(
  queryKey: QueryKey,
  queryFn: () => Promise<TData>,
  overrides: Partial<UseQueryOptions<TData>> = {},
): UseQueryOptions<TData> {
  const open = isMarketOpenIST();
  return {
    queryKey,
    queryFn,
    staleTime:        open ?  60_000 : 5 * 60_000,
    refetchInterval:  open ?  60_000 : false,
    refetchOnWindowFocus: open,
    ...overrides,
  } as UseQueryOptions<TData>;
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
