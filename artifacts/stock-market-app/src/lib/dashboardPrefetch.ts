/**
 * Dashboard prefetch + localStorage persistence.
 *
 * Two mechanisms work together to make the dashboard feel instant:
 *
 *  1. localStorage cache (survives page refresh):
 *     – `hydrateDashboardCache` is called synchronously at module level in
 *       App.tsx, immediately after `new QueryClient()`.  By the time React
 *       mounts the Dashboard the cache already has data — no skeleton shown.
 *     – `saveDashboardCache` is called after every prefetch cycle and after
 *       the token changes so the snapshot stays fresh.
 *
 *  2. Eager prefetch (survives in-app navigation):
 *     – `prefetchDashboardQueries` is called from TokenInjector the moment
 *       the auth token is set.  All 10 queries fire in the background; the
 *       cache is warm before the user ever clicks through to /.
 */
import { QueryClient } from "@tanstack/react-query";
import { api, fetchApi } from "@/lib/api";

const CACHE_KEY = "nn_dash_v2";
const MAX_AGE_MS = 30 * 60 * 1000;

export const DASHBOARD_KEYS = [
  ["patterns-overview"],
  ["insights/fii-dii", "equity", "30d"],
  ["sector-rotation-dash"],
  ["news-dash"],
  ["ipo-dash"],
  ["macro-strip"],
  ["volume-summary-dash"],
  ["sentiment-market"],
  ["global-indices"],
  ["dashboard/top-movers/all"],
] as const;

type KeyTuple = (typeof DASHBOARD_KEYS)[number];

const PREFETCH_CONFIGS: Array<{ key: KeyTuple; fn: () => Promise<unknown>; staleTime: number }> = [
  { key: ["global-indices"],        fn: api.globalIndices,                                          staleTime: 3 * 60_000  },
  { key: ["macro-strip"],           fn: api.macroStrip,                                             staleTime: 15 * 60_000 },
  { key: ["volume-summary-dash"],   fn: () => fetchApi("/insights/volume-summary"),                 staleTime: 30 * 60_000 },
  { key: ["dashboard/top-movers/all"], fn: () => api.topMoversAll(10),                             staleTime: 3 * 60_000  },
  { key: ["ipo-dash"],              fn: () => fetchApi("/insights/ipos"),                           staleTime: 10 * 60_000 },
  { key: ["sentiment-market"],      fn: () => fetchApi("/sentiment/market"),                        staleTime: 15 * 60_000 },
  { key: ["news-dash"],             fn: () => api.newsFeed({ limit: 7 }),                          staleTime: 7 * 60_000  },
  { key: ["insights/fii-dii", "equity", "30d"], fn: () => fetchApi("/insights/fii-dii?segment=equity&days=30"), staleTime: 10 * 60_000 },
  { key: ["sector-rotation-dash"],  fn: api.sectorRotation,                                         staleTime: 5 * 60_000  },
  { key: ["patterns-overview"],     fn: api.patterns,                                               staleTime: 10 * 60_000 },
];

export function hydrateDashboardCache(queryClient: QueryClient): void {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw) as Record<string, { data: unknown; ts: number }>;
    const now = Date.now();
    for (const [keyStr, { data, ts }] of Object.entries(saved)) {
      if (now - ts > MAX_AGE_MS) continue;
      const key = JSON.parse(keyStr) as unknown[];
      if (!queryClient.getQueryData(key)) {
        queryClient.setQueryData(key, data);
      }
    }
  } catch {}
}

export function saveDashboardCache(queryClient: QueryClient): void {
  try {
    const toSave: Record<string, { data: unknown; ts: number }> = {};
    for (const key of DASHBOARD_KEYS) {
      const state = queryClient.getQueryState(key as unknown[]);
      if (state?.status === "success" && state.data != null) {
        toSave[JSON.stringify(key)] = { data: state.data, ts: Date.now() };
      }
    }
    if (Object.keys(toSave).length > 0) {
      localStorage.setItem(CACHE_KEY, JSON.stringify(toSave));
    }
  } catch {}
}

let _prefetchInFlight = false;

export function prefetchDashboardQueries(queryClient: QueryClient): void {
  if (_prefetchInFlight) return;
  _prefetchInFlight = true;

  const promises = PREFETCH_CONFIGS.map(({ key, fn, staleTime }) =>
    queryClient
      .prefetchQuery({ queryKey: key as unknown[], queryFn: fn, staleTime })
      .catch(() => {}),
  );

  Promise.all(promises).then(() => {
    saveDashboardCache(queryClient);
    _prefetchInFlight = false;
  });
}
