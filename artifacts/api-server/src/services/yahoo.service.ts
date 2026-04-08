import axios from "axios";

// ─── Bounded TTL Cache ────────────────────────────────────────────────────────

const MAX_ENTRIES = 400;
const CACHE = new Map<string, { data: unknown; expiry: number }>();

function evictExpired() {
  const now = Date.now();
  for (const [k, v] of CACHE) if (now > v.expiry) CACHE.delete(k);
}

function getCache<T>(key: string): T | null {
  const e = CACHE.get(key);
  if (e && Date.now() < e.expiry) return e.data as T;
  if (e) CACHE.delete(key);
  return null;
}

function setCache(key: string, data: unknown, ttl: number) {
  if (CACHE.size >= MAX_ENTRIES) {
    evictExpired();
    if (CACHE.size >= MAX_ENTRIES) {
      CACHE.delete(CACHE.keys().next().value as string);
    }
  }
  CACHE.set(key, { data, expiry: Date.now() + ttl * 1000 });
}

// ─── In-Flight Deduplication ─────────────────────────────────────────────────
// Prevents duplicate parallel HTTP calls for the same key during bulk scans

const inFlight = new Map<string, Promise<unknown>>();

function dedupe<T>(key: string, fn: () => Promise<T>): Promise<T> {
  if (inFlight.has(key)) return inFlight.get(key) as Promise<T>;
  const p = fn().finally(() => inFlight.delete(key));
  inFlight.set(key, p);
  return p;
}

// ─── Quote / History shapes ───────────────────────────────────────────────────

export interface QuoteData {
  symbol: string;
  companyName: string;
  lastPrice: number;
  change: number;
  pChange: number;
  open: number;
  dayHigh: number;
  dayLow: number;
  previousClose: number;
  volume: number;
  marketCap: number;
  fiftyTwoWeekHigh: number;
  fiftyTwoWeekLow: number;
}

export interface OHLCV {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

// ─── Service ──────────────────────────────────────────────────────────────────

export class YahooService {
  private toYahoo(s: string) { return `${s}.NS`; }

  async getQuote(symbol: string): Promise<QuoteData | null> {
    const cacheKey = `yq-${symbol}`;
    const cached = getCache<QuoteData>(cacheKey);
    if (cached) return cached;

    return dedupe(cacheKey, async () => {
      try {
        const r = await axios.get(
          `https://query1.finance.yahoo.com/v8/finance/chart/${this.toYahoo(symbol)}?interval=1d&range=1d`,
          { headers: { "User-Agent": "Mozilla/5.0" }, timeout: 10_000 },
        );
        const meta = r.data?.chart?.result?.[0]?.meta;
        if (!meta) return null;

        const data: QuoteData = {
          symbol,
          companyName:      meta.longName || symbol,
          lastPrice:        meta.regularMarketPrice,
          change:           meta.regularMarketPrice - meta.chartPreviousClose,
          pChange:          ((meta.regularMarketPrice - meta.chartPreviousClose) / meta.chartPreviousClose) * 100,
          open:             meta.regularMarketOpen,
          dayHigh:          meta.regularMarketDayHigh,
          dayLow:           meta.regularMarketDayLow,
          previousClose:    meta.chartPreviousClose,
          volume:           meta.regularMarketVolume,
          marketCap:        meta.marketCap,
          fiftyTwoWeekHigh: meta["52WeekHigh"],
          fiftyTwoWeekLow:  meta["52WeekLow"],
        };
        setCache(cacheKey, data, 300);
        return data;
      } catch {
        return null;
      }
    }) as Promise<QuoteData | null>;
  }

  async getHistoricalData(symbol: string, days = 90): Promise<OHLCV[]> {
    const cacheKey = `yh-${symbol}-${days}`;
    const cached = getCache<OHLCV[]>(cacheKey);
    if (cached) return cached;

    return dedupe(cacheKey, async () => {
      const range = days <= 30 ? "1mo" : days <= 90 ? "3mo" : days <= 180 ? "6mo" : "1y";
      try {
        const r = await axios.get(
          `https://query1.finance.yahoo.com/v8/finance/chart/${this.toYahoo(symbol)}?interval=1d&range=${range}`,
          { headers: { "User-Agent": "Mozilla/5.0" }, timeout: 10_000 },
        );
        const result = r.data?.chart?.result?.[0];
        if (!result) return [];

        const ts = (result.timestamp || []) as number[];
        const q  = (result.indicators?.quote?.[0] || {}) as Record<string, number[]>;

        const data: OHLCV[] = ts
          .map((t, i) => ({
            date:   new Date(t * 1000).toISOString().split("T")[0],
            open:   q.open?.[i],
            high:   q.high?.[i],
            low:    q.low?.[i],
            close:  q.close?.[i],
            volume: q.volume?.[i],
          }))
          .filter(d => d.close != null) as OHLCV[];

        setCache(cacheKey, data, 3600);
        return data;
      } catch {
        return [];
      }
    }) as Promise<OHLCV[]>;
  }
}
