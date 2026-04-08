import axios from "axios";

// ─── Bounded TTL Cache ────────────────────────────────────────────────────────

const MAX_ENTRIES = 200;
const CACHE = new Map<string, { data: unknown; expiry: number }>();

function evictExpired() {
  const now = Date.now();
  for (const [k, v] of CACHE) if (now > v.expiry) CACHE.delete(k);
}

function getCache<T>(key: string): T | null {
  const entry = CACHE.get(key);
  if (entry && Date.now() < entry.expiry) return entry.data as T;
  if (entry) CACHE.delete(key);
  return null;
}

function setCache(key: string, data: unknown, ttlSeconds: number) {
  if (CACHE.size >= MAX_ENTRIES) {
    evictExpired();
    if (CACHE.size >= MAX_ENTRIES) {
      CACHE.delete(CACHE.keys().next().value as string);
    }
  }
  CACHE.set(key, { data, expiry: Date.now() + ttlSeconds * 1000 });
}

// ─── Cookie Management ────────────────────────────────────────────────────────

let cookies = "";
let cookieExpiry = 0;
let refreshPromise: Promise<void> | null = null;

async function refreshCookies() {
  try {
    const response = await axios.get("https://www.nseindia.com", {
      timeout: 15_000,
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      },
    });
    const setCookies = response.headers["set-cookie"];
    if (setCookies) {
      cookies = setCookies.map((c: string) => c.split(";")[0]).join("; ");
      cookieExpiry = Date.now() + 20 * 60 * 1000;
    }
  } catch {
    // Cookie refresh is best-effort; fall through with empty cookies
  } finally {
    refreshPromise = null;
  }
}

/** Ensure cookies are fresh — deduplicated so concurrent callers share one refresh */
async function ensureCookies() {
  if (cookies && Date.now() < cookieExpiry) return;
  if (!refreshPromise) refreshPromise = refreshCookies();
  await refreshPromise;
}

// ─── Service ──────────────────────────────────────────────────────────────────

export class NseService {
  async fetchNse<T>(path: string, cacheKey: string, ttl = 300): Promise<T | null> {
    const cached = getCache<T>(cacheKey);
    if (cached) return cached;

    await ensureCookies();
    try {
      const response = await axios.get<T>(`https://www.nseindia.com${path}`, {
        timeout: 15_000,
        headers: {
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
          Accept: "application/json, text/plain, */*",
          "Accept-Language": "en-US,en;q=0.9",
          Referer: "https://www.nseindia.com",
          Cookie: cookies,
          "X-Requested-With": "XMLHttpRequest",
        },
      });
      setCache(cacheKey, response.data, ttl);
      return response.data;
    } catch {
      return null;
    }
  }

  getSectorIndices()     { return this.fetchNse("/api/allIndices",                                      "sector-indices", 300);  }
  getStockQuote(symbol: string) {
    return this.fetchNse(`/api/quote-equity?symbol=${encodeURIComponent(symbol)}`, `quote-${symbol}`,   120);
  }
  getNifty100()          { return this.fetchNse("/api/equity-stockIndices?index=NIFTY%20100",           "nifty100",       1800); }
  getNiftyMidcap150()    { return this.fetchNse("/api/equity-stockIndices?index=NIFTY%20MIDCAP%20150",  "midcap150",      1800); }
  getNiftySmallcap250()  { return this.fetchNse("/api/equity-stockIndices?index=NIFTY%20SMALLCAP%20250","smallcap250",    1800); }
}
