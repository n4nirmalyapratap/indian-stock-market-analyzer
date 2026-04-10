// ─── Shared response types ────────────────────────────────────────────────────

export interface SectorData {
  name: string;
  symbol: string;
  lastPrice: number;
  pChange: number;
  /** Total advancing stocks in the sector */
  advance: number;
  advances?: number;
  /** Total declining stocks in the sector */
  decline: number;
  declines?: number;
  unchanged: number;
  /** Sector category label, e.g. "Banking", "IT" */
  category?: string;
  /** Buy/Avoid/Watch signal for the sector */
  focus?: string;
  /** Data source label */
  source?: string;
  /** A/D ratio for the sector */
  advanceDeclineRatio?: number;
  [key: string]: unknown;
}

export interface EconomicPhase {
  phase: string;
  code: string;
  color: string;
  bgColor: string;
  leadingSectors: string[];
  characteristics: string;
  theorySectors: string[];
  actionableSectors: string[];
  strategy: string;
  confidence: number;
  phaseScores: Record<string, number>;
}

export interface PortfolioTopPick {
  sector: string;
  symbol: string;
  tier: string;
  tierLabel: string;
  color: string;
  bgColor: string;
  composite: number;
  rs: number;
  roc_6m: number;
  pct_above_200: number;
  maxAllocation: string;
  theoryMatch: boolean;
  entryReason: string;
  exitRule: string;
  profitRule: string;
}

export interface PortfolioStrategy {
  coreSatellite: { core: string; satellite: string };
  topPicks: PortfolioTopPick[];
  riskManagement: {
    stopLoss: string;
    profitTaking: string;
    exitSignal: string;
    cashReserve: string;
    maxPerSector: string;
    maxPerStock: string;
  };
  trendlessMarket: string | null;
}

export interface SectorRotation {
  rotationPhase: string;
  recommendation: string;
  timestamp: string;
  economicPhase: EconomicPhase;
  portfolioStrategy: PortfolioStrategy;
  marketBreadth: {
    advancing: number;
    declining: number;
    unchanged: number;
    /** A/D ratio as a formatted string, e.g. "5.00" */
    advanceDeclineRatio?: number | string;
    /** Market breadth percentage 0–100 */
    breadthScore?: number;
  };
  adRatio: number;
  sectors: SectorData[];
  whereToBuyNow: SectorData[];
  phasedOut?: SectorData[];
  tierCounts?: Record<string, number>;
  tiers?: { tier: string; label: string; color: string; bg: string; description: string }[];
  topPerformers?: SectorData[];
  laggards?: SectorData[];
  currentlyFocused?: string[];
}

export interface ConditionSide {
  type: "indicator" | "number";
  indicator?: string;
  period?: number;
  value?: number;
}

export interface Condition {
  id: string;
  left: ConditionSide;
  operator: string;
  right: ConditionSide;
}

export interface Scanner {
  id: string;
  name: string;
  description?: string;
  universe: string[];
  logic: "AND" | "OR";
  conditions: Condition[];
  createdAt: string;
  updatedAt: string;
  lastRunAt?: string;
  lastResultCount?: number;
}

export interface ScannerCreateInput {
  name: string;
  description?: string;
  universe: string[];
  logic: "AND" | "OR";
  conditions: Condition[];
}

export interface MatchedStock {
  symbol: string;
  lastPrice: number;
  change: number;
  pChange: number;
  volume: number;
  score: number;
  conditionsMatched: number;
  totalConditions: number;
  matchedConditions: string[];
  failedConditions: string[];
}

export interface ScanResult {
  scannerId: string;
  scannerName: string;
  logic: "AND" | "OR";
  runAt: string;
  totalScanned: number;
  totalMatched: number;
  results: MatchedStock[];
  error?: string;
}

export interface ChartPattern {
  symbol: string;
  pattern: string;
  patternType: string;
  signal: "CALL" | "PUT" | "WAIT";
  confidence: number;
  detectedAt: string;
  currentPrice: number;
  targetPrice?: number;
  stopLoss?: number;
  description: string;
  timeframe: string;
  universe: string;
  category: string;
}

export interface PatternsResponse {
  lastScanTime: string;
  totalPatterns: number;
  callSignals: number;
  putSignals: number;
  categories: string[];
  patterns: ChartPattern[];
  topCalls: ChartPattern[];
  topPuts: ChartPattern[];
}

export interface TechnicalAnalysis {
  trend?: string;
  rsi?: number;
  rsiZone?: string;
  atr?: number;
  ema?: {
    ema9?: number;
    ema21?: number;
    ema50?: number;
    ema200?: number;
    [key: string]: number | undefined;
  };
  macd?: {
    crossover?: string;
    histogram?: number;
    value?: number;
    signal?: number;
    [key: string]: unknown;
  };
  bollingerBands?: {
    position?: string;
    upper?: number;
    middle?: number;
    lower?: number;
    [key: string]: unknown;
  };
  nearestSupport?: number;
  nearestResistance?: number;
  resistances?: number[];
  supports?: number[];
  [key: string]: unknown;
}

export interface EntryRecommendation {
  signal?: string;
  entryCall?: string;
  confidence?: string | number;
  summary?: string;
  targetPrice?: number;
  stopLoss?: number;
  riskReward?: number | string;
  bullishFactors?: number | string;
  bearishFactors?: number | string;
  [key: string]: unknown;
}

export interface StockQuote {
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
  /** Optional enriched fields from stock detail endpoint */
  industry?: string;
  sector?: string;
  insight?: string;
  error?: string;
  technicalAnalysis?: TechnicalAnalysis;
  entryRecommendation?: EntryRecommendation;
  [key: string]: unknown;
}

export interface WhatsAppMessage {
  from: string;
  text: string;
  timestamp: string;
  response: string;
  processingTime?: string;
}

export interface BotStatus {
  status: string;
  enabled: boolean;
  qrCode: string | null;
  sessionActive: boolean;
  lastActive: string | null;
  totalMessages: number;
  capabilities: string[];
  commands: string[];
}

// ─── API error class ──────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

// ─── Base fetch ───────────────────────────────────────────────────────────────

const BASE = "/api";

export async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    throw new ApiError(res.status, body.error || `API error ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ─── API client ───────────────────────────────────────────────────────────────

const JSON_HEADERS = { "Content-Type": "application/json" };

export const api = {
  health: () =>
    fetchApi<{ status: string }>("/healthz"),

  sectors: () =>
    fetchApi<SectorData[]>("/sectors"),

  sectorRotation: () =>
    fetchApi<SectorRotation>("/sectors/rotation"),

  nifty100:  () => fetchApi<StockQuote[]>("/stocks/nifty100"),
  midcap:    () => fetchApi<StockQuote[]>("/stocks/midcap"),
  smallcap:  () => fetchApi<StockQuote[]>("/stocks/smallcap"),

  stockDetail: (symbol: string) =>
    fetchApi<StockQuote>(`/stocks/${encodeURIComponent(symbol)}`),

  patterns: (params?: { universe?: string; signal?: string; category?: string }) => {
    const filtered = Object.fromEntries(
      Object.entries(params ?? {}).filter(([, v]) => v != null && v !== ""),
    );
    const q = new URLSearchParams(filtered as Record<string, string>).toString();
    return fetchApi<PatternsResponse>(`/patterns${q ? "?" + q : ""}`);
  },

  triggerScan: () =>
    fetchApi<{ message: string; totalFound: number; callSignals: number; putSignals: number; patterns: ChartPattern[] }>(
      "/patterns/scan",
      { method: "POST" },
    ),

  scanners:      () => fetchApi<Scanner[]>("/scanners"),
  createScanner: (data: ScannerCreateInput) =>
    fetchApi<Scanner>("/scanners", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(data) }),
  updateScanner: (id: string, data: Partial<ScannerCreateInput>) =>
    fetchApi<Scanner>(`/scanners/${id}`, { method: "PUT", headers: JSON_HEADERS, body: JSON.stringify(data) }),
  deleteScanner: (id: string) =>
    fetchApi<{ success: boolean }>(`/scanners/${id}`, { method: "DELETE" }),
  runScanner:    (id: string) =>
    fetchApi<ScanResult>(`/scanners/${id}/run`, { method: "POST" }),
  runAdHoc:      (data: ScannerCreateInput) =>
    fetchApi<ScanResult>("/scanners/adhoc/run", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(data) }),

  whatsappStatus:   () => fetchApi<BotStatus>("/whatsapp/status"),
  whatsappMessages: () => fetchApi<WhatsAppMessage[]>("/whatsapp/messages"),
  whatsappMessage:  (from: string, message: string) =>
    fetchApi<WhatsAppMessage>("/whatsapp/message", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ from, message }),
    }),

  telegramStatus:     () => fetchApi<Record<string, unknown>>("/telegram/status"),
  telegramMessages:   () => fetchApi<WhatsAppMessage[]>("/telegram/messages"),
  telegramTest:       (text: string) =>
    fetchApi<{ text: string; response: string; timestamp: string }>("/telegram/test", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ text }),
    }),
  telegramSetWebhook: (url: string) =>
    fetchApi<{ success: boolean; description: string; webhookUrl: string }>("/telegram/set-webhook", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ url }),
    }),

  sectorHeatmap: () =>
    fetchApi<SectorHeatmapItem[]>("/sector-analytics/heatmap"),

  sectorTopMovers: (period: "1d" | "1w" | "1m" | "1y" = "1d") =>
    fetchApi<SectorTopMovers>(`/sector-analytics/top-movers?period=${period}`),

  sectorDetail: (sector: string, period: "3mo" | "6mo" | "1y" | "5y" = "1y") =>
    fetchApi<SectorDetailData>(`/sector-analytics/${encodeURIComponent(sector)}/detail?period=${period}`),

  newsFeed: (params?: { category?: string; search?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams(
      Object.fromEntries(Object.entries(params ?? {}).filter(([, v]) => v != null && v !== "").map(([k, v]) => [k, String(v)]))
    ).toString();
    return fetchApi<NewsFeedResponse>(`/news/feed${q ? "?" + q : ""}`);
  },

  newsDeals: () => fetchApi<NewsDealsResponse>("/news/deals"),

  newsEvents: () => fetchApi<NewsEventsResponse>("/news/events"),

  newsStats: () => fetchApi<NewsStatsResponse>("/news/stats"),

  newsRefresh: () => fetchApi<{ ok: boolean }>("/news/refresh", { method: "POST" }),
};

// ─── News types ────────────────────────────────────────────────────────────────

export interface NewsArticle {
  id: string;
  title: string;
  summary: string;
  url: string;
  source: string;
  sourceShort: string;
  sourceColor: string;
  category: "market" | "corporate" | "general";
  published: string;
  sentiment: "bullish" | "bearish" | "neutral";
  tickers: string[];
  image_url?: string | null;
  type: "news";
}

export interface NewsFeedResponse {
  articles: NewsArticle[];
  total: number;
  cached: boolean;
  refreshedAt: string;
  categories: string[];
}

export interface Deal {
  type: "bulk" | "block";
  date: string;
  symbol: string;
  name: string;
  client: string;
  side: string;
  quantity: number;
  price: number;
}

export interface NewsDealsResponse {
  bulk: Deal[];
  block: Deal[];
  total: number;
  refreshedAt: string;
}

export interface NewsEvent {
  symbol: string;
  company: string;
  purpose: string;
  date: string;
  type: string;
}

export interface NewsEventsResponse {
  events: NewsEvent[];
  total: number;
  refreshedAt: string;
}

export interface NewsStatsResponse {
  totalArticles: number;
  sentiments: { bullish: number; bearish: number; neutral: number };
  sources: Record<string, number>;
  marketMood: "bullish" | "bearish" | "neutral";
}

// ─── Sector Analytics types ───────────────────────────────────────────────────

export interface SectorHeatmapItem {
  symbol:    string;
  name:      string;
  category:  string;
  lastPrice: number;
  change1d:  number | null;
  change1w:  number | null;
  change1m:  number | null;
  change3m:  number | null;
  change6m:  number | null;
  change1y:  number | null;
  changeYTD: number | null;
  marketCap: number;
  advances:  number;
  declines:  number;
}

export interface SectorTopMovers {
  period:  string;
  gainers: SectorHeatmapItem[];
  losers:  SectorHeatmapItem[];
}

export interface RSPoint {
  date:   string;
  ratio:  number;
  sector: number;
  nifty:  number;
}

export interface SectorValuation {
  pe:           number | null;
  pb:           number | null;
  ps:           number | null;
  evEbitda:     number | null;
  pe_equal:     number | null;
  pb_equal:     number | null;
  ps_equal:     number | null;
  evEbitda_equal: number | null;
  method:       string;
  sampleSize:   number;
}

export interface SectorProfitability {
  netMargin:  number | null;
  roe:        number | null;
  sampleSize: number;
}

export interface SectorFinancialHealth {
  debtToEquity:   number | null;
  sampleSize:     number;
  roa:            number | null;
  roaSampleSize:  number;
  earningsGrowth: number | null;
  revenueGrowth:  number | null;
  isBanking:      boolean;
}

export interface ConstituentStock {
  symbol:       string;
  name:         string;
  price:        number | null;
  change1d:     number | null;
  marketCap:    number | null;
  pe:           number | null;
  pb:           number | null;
  ps:           number | null;
  evEbitda:     number | null;
  roe:          number | null;
  debtToEquity: number | null;
  dividendYield: number | null;
  beta:         number | null;
  industry:     string | null;
}

export interface SectorDetailData {
  symbol:          string;
  name:            string;
  marketCap:       number;
  relativeStrength: RSPoint[];
  performance:     Record<string, number | null>;
  valuation:       SectorValuation;
  profitability:   SectorProfitability;
  financialHealth: SectorFinancialHealth;
  constituents:    ConstituentStock[];
  topGainers:      ConstituentStock[];
  topLosers:       ConstituentStock[];
}
