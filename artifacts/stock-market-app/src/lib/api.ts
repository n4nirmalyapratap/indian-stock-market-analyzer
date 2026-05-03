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

// ── Famous-Investor AI Council types ─────────────────────────────────────────

export type AgentVerdict = "STRONG_BUY" | "BUY" | "HOLD" | "AVOID" | "STRONG_AVOID";

export interface ChecklistItem {
  label:     string;
  passed:    boolean;
  value:     number | null;
  threshold: number | number[];
  op:        string;
  weight:    number;
  detail:    string;
}

export interface PersonaResult {
  id:         string;
  name:       string;
  firm:       string;
  philosophy: string;
  signature:  string;
  score:      number;
  verdict:    AgentVerdict;
  checklist:  ChecklistItem[];
  thesis?:    string;
}

export interface PersonaMeta {
  id:         string;
  name:       string;
  firm:       string;
  era:        string;
  philosophy: string;
  signature:  string;
}

export interface AgentSource {
  id:     string;
  label:  string;
  covers: string;
}

export interface CouncilResponse {
  symbol:    string;
  name:      string | null;
  sector:    string | null;
  lastPrice: number | null;
  context:   Record<string, unknown>;
  personas:  PersonaResult[];
  council: {
    verdict:    AgentVerdict;
    avgScore:   number;
    buyCount:   number;
    avoidCount: number;
    holdCount:  number;
  };
  sources?:   AgentSource[];
  fetchedAt?: string;
}

export interface PersonaDeepDive extends PersonaMeta {
  symbol:     string;
  name_stock: string | null;
  sector:     string | null;
  lastPrice:  number | null;
  score:      number;
  verdict:    AgentVerdict;
  checklist:  ChecklistItem[];
  thesis:     string;
  context:    Record<string, unknown>;
}

export interface AgentsListResponse {
  personas: PersonaMeta[];
  count:    number;
}

// ── Macro Pulse (India macro indicators) ─────────────────────────────────────

export interface MacroTile {
  id:        string;
  label:     string;
  unit:      string;
  value:     number | null;
  delta:     number | null;
  deltaUnit: string;
  asOf:      string | null;
}

export interface MacroSource {
  id:      string;
  label:   string;
  covers:  string;
  ok?:     boolean;
  url?:    string | null;
  note?:   string | null;
}

export interface MacroYieldCurvePoint {
  tenor:        string;
  tenorMonths:  number;
  value:        number | null;
  asOf:         string | null;
}

export interface MacroStripResponse {
  tiles:     MacroTile[];
  fetchedAt: string;
  sources:   MacroSource[];
  meta?:     unknown;
}

export interface MacroSeriesPoint {
  date:  string;
  value: number;
}

export interface MacroQuote {
  symbol?:  string;
  price?:   number | null;
  change?:  number;
  pChange?: number;
  name?:    string;
}

export interface MacroDashboardResponse {
  rateTimeline: MacroSeriesPoint[];
  cpi:          MacroSeriesPoint[];
  wpi:          MacroSeriesPoint[];
  iip:          MacroSeriesPoint[];
  gdp:          MacroSeriesPoint[];
  yieldCurve: {
    ind10yNow:     number | null;
    ind10yAsOf:    string | null;
    ind10yHistory: MacroSeriesPoint[];
    snapshot:      MacroYieldCurvePoint[];
  };
  currencyStrip: {
    usdinr: MacroQuote;
    dxy:    MacroQuote;
    brent:  MacroQuote;
    gold:   MacroQuote;
    vix:    MacroQuote;
  };
  commentary: string;
  fetchedAt:  string;
  sources:    MacroSource[];
  meta?:      unknown;
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

// ─── Auth token injection ─────────────────────────────────────────────────────

let _getToken: ((opts?: Record<string, unknown>) => Promise<string | null>) | null = null;

export function setTokenGetter(fn: (opts?: Record<string, unknown>) => Promise<string | null>) {
  _getToken = fn;
}

// ─── Base fetch ───────────────────────────────────────────────────────────────

const BASE = (import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");

export async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const authHeaders: Record<string, string> = {};
  if (_getToken) {
    try {
      const token = await _getToken();
      if (token) authHeaders["Authorization"] = `Bearer ${token}`;
    } catch {
      // User may not be signed in yet
    }
  }

  const existingHeaders = (options?.headers as Record<string, string>) ?? {};
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { ...existingHeaders, ...authHeaders },
  });
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

  stockFinancials: (symbol: string) =>
    fetchApi<StockFinancials>(`/stocks/${encodeURIComponent(symbol)}/financials`),

  stockTechnicalSummary: (symbol: string, interval = "1d") =>
    fetchApi<TechnicalSummary>(`/stocks/${encodeURIComponent(symbol)}/technical-summary?interval=${interval}`),

  // ── Famous-Investor AI Council ──
  agentsList: () =>
    fetchApi<AgentsListResponse>("/agents"),

  agentCouncil: (symbol: string) =>
    fetchApi<CouncilResponse>(`/agents/${encodeURIComponent(symbol)}`),

  agentCouncilFull: (symbol: string) =>
    fetchApi<CouncilResponse>(`/agents/${encodeURIComponent(symbol)}/council`),

  agentPersona: (symbol: string, personaId: string) =>
    fetchApi<PersonaDeepDive>(
      `/agents/${encodeURIComponent(symbol)}/${encodeURIComponent(personaId)}`,
    ),

  // ── Macro Pulse ──
  macroStrip:     () => fetchApi<MacroStripResponse>("/insights/macro/strip"),
  macroDashboard: () => fetchApi<MacroDashboardResponse>("/insights/macro"),

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

  scanners:      async () => {
    const res = await fetchApi<Scanner[] | { scanners: Scanner[]; meta?: unknown }>("/scanners");
    return Array.isArray(res) ? res : (res?.scanners ?? []);
  },
  scannersWithMeta: () => fetchApi<{ scanners: Scanner[]; meta?: unknown }>("/scanners"),
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

  // ── Portfolio Manager ──
  portfolios: () =>
    fetchApi<{ portfolios: Portfolio[] }>("/portfolio"),

  createPortfolio: (data: { name: string; cash?: number; baseCurrency?: string }) =>
    fetchApi<Portfolio>("/portfolio", {
      method: "POST", headers: JSON_HEADERS, body: JSON.stringify(data),
    }),

  updatePortfolio: (pid: string, data: { name?: string; cash?: number }) =>
    fetchApi<Portfolio>(`/portfolio/${encodeURIComponent(pid)}`, {
      method: "PUT", headers: JSON_HEADERS, body: JSON.stringify(data),
    }),

  deletePortfolio: (pid: string) =>
    fetchApi<{ success: boolean; id: string }>(`/portfolio/${encodeURIComponent(pid)}`, {
      method: "DELETE",
    }),

  portfolioValuation: (pid: string) =>
    fetchApi<PortfolioValuation>(`/portfolio/${encodeURIComponent(pid)}/valuation`),

  portfolioTransactions: (pid: string) =>
    fetchApi<{ transactions: PortfolioTx[] }>(`/portfolio/${encodeURIComponent(pid)}/transactions`),

  addPortfolioTx: (pid: string, tx: PortfolioTxInput) =>
    fetchApi<PortfolioTx>(`/portfolio/${encodeURIComponent(pid)}/transactions`, {
      method: "POST", headers: JSON_HEADERS, body: JSON.stringify(tx),
    }),

  deletePortfolioTx: (pid: string, txId: string) =>
    fetchApi<{ success: boolean; id: string }>(
      `/portfolio/${encodeURIComponent(pid)}/transactions/${encodeURIComponent(txId)}`,
      { method: "DELETE" },
    ),

  importPortfolioCsv: (pid: string, csv: string) =>
    fetchApi<PortfolioImportResult>(`/portfolio/${encodeURIComponent(pid)}/import`, {
      method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ csv }),
    }),

  portfolioRisk: (pid: string, params: PortfolioRiskParams = {}) =>
    fetchApi<PortfolioRiskResult>(`/portfolio/${encodeURIComponent(pid)}/risk`, {
      method: "POST", headers: JSON_HEADERS, body: JSON.stringify(params),
    }),

  portfolioPerformance: (pid: string, benchmark = "NIFTY 50", days = 365) =>
    fetchApi<PortfolioPerformance>(
      `/portfolio/${encodeURIComponent(pid)}/performance?benchmark=${encodeURIComponent(benchmark)}&days=${days}`,
    ),

  portfolioOptimize: (pid: string, params: PortfolioOptimizeParams) =>
    fetchApi<PortfolioOptimizeResult>(`/portfolio/${encodeURIComponent(pid)}/optimize`, {
      method: "POST", headers: JSON_HEADERS, body: JSON.stringify(params),
    }),

  dataConsistency: (symbols: string[] = []) => {
    const q = symbols.length ? `?symbols=${encodeURIComponent(symbols.join(","))}` : "";
    return fetchApi<{
      marketState: string;
      marketOpen:  boolean;
      cacheVersion: number;
      asOf:        string;
      checked:     number;
      driftCount:  number;
      consistent:  boolean;
      results: Array<{
        symbol:        string;
        quotePrice?:   number;
        historyClose?: number;
        historyDate?:  string;
        sectorPrice?:  number | null;
        drift?:        number | null;
        driftPct?:     number | null;
        consistent?:   boolean;
        meta?:         Record<string, unknown>;
        error?:        string;
      }>;
    }>(`/admin/data-consistency${q}`);
  },
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
  roa:          number | null;
  earningsGrowth: number | null;
  revenueGrowth:  number | null;
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
  /** Provenance fields surfaced by the backend for DataFreshness. */
  asOf?:           string;
  marketState?:    string;
  source?:         "NSE" | "YAHOO" | string;
  servedFrom?:     string;
}

// ── Technical Summary (TradingView Indicators' Summary) ──────────────────────

export type TechAction = "BUY" | "SELL" | "NEUTRAL";
export type TechSignal = "STRONG_BUY" | "BUY" | "NEUTRAL" | "SELL" | "STRONG_SELL";

export interface TechIndicatorRow {
  name:   string;
  value:  number | null;
  action: TechAction;
}

export interface TechSection {
  signal:     TechSignal;
  buy:        number;
  sell:       number;
  neutral:    number;
  indicators: TechIndicatorRow[];
}

export interface PivotLevel {
  r3: number | null;
  r2: number | null;
  r1: number | null;
  p:  number | null;
  s1: number | null;
  s2: number | null;
  s3: number | null;
}

export interface DmPivot {
  r1: number | null;
  p:  number | null;
  s1: number | null;
}

export interface TechnicalSummary {
  symbol:          string;
  interval:        string;
  summary:         { signal: TechSignal; buy: number; sell: number; neutral: number };
  oscillators:     TechSection;
  movingAverages:  TechSection;
  pivots: {
    classic:   PivotLevel;
    fibonacci: PivotLevel;
    camarilla: PivotLevel;
    woodie:    PivotLevel;
    dm:        DmPivot;
  };
  meta?: {
    source?:       string;
    asOf?:         string | null;
    marketState?:  string;
    eodSealed?:    boolean;
    eodDate?:      string | null;
    cacheVersion?: number;
  };
}

// ── Stock Financials (TradingView-style) ────────────────────────────────────

export interface FinancialOverview {
  marketCap:       number | null;
  trailingPE:      number | null;
  forwardPE:       number | null;
  priceToBook:     number | null;
  priceToSales:    number | null;
  evToEbitda:      number | null;
  trailingEps:     number | null;
  forwardEps:      number | null;
  roe:             number | null;
  roa:             number | null;
  debtToEquity:    number | null;
  currentRatio:    number | null;
  grossMargin:     number | null;
  operatingMargin: number | null;
  netMargin:       number | null;
  dividendYield:   number | null;
  dividendRate:    number | null;
  earningsGrowth:  number | null;
  revenueGrowth:   number | null;
  bookValue:       number | null;
  weekChange52:    number | null;
}

export interface IncomeRow {
  date:            string;
  revenue:         number | null;
  grossProfit:     number | null;
  operatingIncome: number | null;
  netIncome:       number | null;
  ebitda:          number | null;
}

export interface BalanceSheetRow {
  date:        string;
  totalAssets: number | null;
  totalDebt:   number | null;
  equity:      number | null;
  cash:        number | null;
}

export interface CashFlowRow {
  date:        string;
  operatingCF: number | null;
  investingCF: number | null;
  financingCF: number | null;
  freeCF:      number | null;
  capex:       number | null;
}

export interface DividendRow {
  date:   string;
  amount: number;
}

export interface EpsRow {
  date: string;
  eps:  number | null;
}

export interface StockFinancials {
  symbol:          string;
  companyName:     string;
  currency:        string;
  overview:        FinancialOverview;
  incomeStatement: { annual: IncomeRow[]; quarterly: IncomeRow[] };
  balanceSheet:    { annual: BalanceSheetRow[] };
  cashFlow:        { annual: CashFlowRow[] };
  dividends:       DividendRow[];
  eps:             { annual: EpsRow[]; quarterly: EpsRow[] };
}

// ─── Portfolio Manager types ─────────────────────────────────────────────────

export interface Portfolio {
  id:           string;
  userId:       string;
  name:         string;
  baseCurrency: string;
  cash:         number;
  createdAt:    string;
  updatedAt:    string;
}

export interface PortfolioTx {
  id:          string;
  portfolioId: string;
  symbol:      string;
  side:        "BUY" | "SELL" | "DIVIDEND";
  qty:         number;
  price:       number;
  fees:        number;
  tradedAt:    string;
  source:      string;
  note?:       string | null;
}

export interface PortfolioTxInput {
  symbol:    string;
  side:      "BUY" | "SELL" | "DIVIDEND";
  qty:       number;
  price:     number;
  fees?:     number;
  tradedAt?: string;
  note?:     string;
}

export interface PortfolioHolding {
  symbol:           string;
  companyName?:     string;
  qty:              number;
  avgCost:          number;
  invested:         number;
  realised:         number;
  dividends:        number;
  fees:             number;
  buys:             number;
  sells:            number;
  firstTradedAt:    string;
  lastTradedAt:     string;
  lastPrice:        number;
  previousClose:    number;
  marketValue:      number;
  unrealisedPnl:    number;
  unrealisedPnlPct: number;
  dayPnl:           number;
  dayPnlPct:        number;
  sector:           string;
  marketCap:        number | null;
  marketCapBucket:  string;
  weight:           number;
}

export interface PortfolioTotals {
  cash:             number;
  marketValue:      number;
  investedValue:    number;
  dayPnl:           number;
  dayPnlPct:        number;
  unrealisedPnl:    number;
  unrealisedPnlPct: number;
  realisedPnl:      number;
  dividendsRcvd:    number;
  totalEquity:      number;
}

export interface AllocationSlice { label: string; value: number; weight: number; }

export interface PortfolioValuation {
  portfolio:      Portfolio;
  holdings:       PortfolioHolding[];
  closedHoldings: Array<Omit<PortfolioHolding, "marketValue" | "lastPrice" | "previousClose" | "unrealisedPnl" | "unrealisedPnlPct" | "dayPnl" | "dayPnlPct" | "sector" | "marketCap" | "marketCapBucket" | "weight" | "companyName">>;
  allocation?:    { sector: AllocationSlice[]; marketCap: AllocationSlice[]; };
  totals:         PortfolioTotals;
  concentration:  Array<{ symbol: string; weight: number; marketValue: number }>;
  fetchedAt:      string;
}

export interface PortfolioImportResult {
  format:       string;
  rowsParsed:   number;
  rowsInserted: number;
  errors:       string[];
}

export interface PortfolioRiskParams {
  confidence?:    number;
  horizonDays?:   number;
  riskFreeRate?:  number;
  lookbackDays?:  number;
}

export interface PortfolioRiskResult {
  portfolioId:  string;
  totals:       PortfolioTotals;
  var: {
    valueAtRisk?:    number;
    varPct?:         number;
    cvarPct?:        number;
    confidence?:     number;
    horizonDays?:    number;
    method?:         string;
    [key: string]:   unknown;
  };
  perPosition: Array<{
    symbol:            string;
    weight:            number;
    sharpe:            number | null;
    sortino:           number | null;
    annualReturn:      number | null;
    annualVolatility:  number | null;
    maxDrawdownPct:    number | null;
  }>;
  portfolio: {
    sharpe:            number | null;
    sortino:           number | null;
    annualReturn:      number | null;
    annualVolatility:  number | null;
    maxDrawdownPct:    number | null;
  };
  fetchedAt:    string;
}

export interface PortfolioPerformancePoint {
  date:        string;
  equity:      number;
  marketValue: number;
}

export interface PortfolioPerformance {
  portfolioId:      string;
  series:           PortfolioPerformancePoint[];
  benchmark:        string;
  benchmarkSeries:  Array<{ date: string; value: number }>;
  fetchedAt:        string;
}

export interface PortfolioOptimizeParams {
  method?:        "markowitz" | "cvar" | "min_vol";
  confidence?:    number;
  riskFreeRate?:  number;
  universe?:      string[];
  points?:        number;
  targetWeights?: Record<string, number>;
}

export interface FrontierPoint {
  expectedReturn: number;
  volatility:     number;
  sharpe:         number;
  weights:        number[];
}

export interface PortfolioOptimizeResult {
  portfolioId:     string;
  method:          string;
  result:          (FrontierPoint & { cvarPct?: number; varPct?: number; annualCvarPct?: number; confidence?: number }) | null;
  frontier?:       {
    symbols:           string[];
    frontier:          FrontierPoint[];
    maxSharpe:         FrontierPoint | null;
    minVol:            FrontierPoint | null;
    riskFreeRateAnnual: number;
    lookbackDays:      number;
  } | null;
  currentWeights:  Record<string, number>;
  targetWeights:   Record<string, number>;
  trades: Array<{
    symbol:        string;
    side:          "BUY" | "SELL";
    qty:           number;
    price:         number;
    notional:      number;
    currentQty:    number;
    currentWeight: number;
    targetWeight:  number;
  }>;
  equity:    number;
  universe:  string[];
  fetchedAt: string;
}
