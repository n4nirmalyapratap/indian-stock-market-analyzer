// ─── Shared response types ────────────────────────────────────────────────────

export interface TaxReportRow {
  symbol:        string;
  qty:           number;
  buyDate:       string;
  buyPrice:      number;
  sellDate:      string;
  sellPrice:     number;
  buyCost:       number;
  sellValue:     number;
  gainLoss:      number;
  holdingDays:   number;
  feeAllocated:  number;
}

export interface TaxReportSection {
  rows:        TaxReportRow[];
  count:       number;
  totalGains:  number;
  totalLosses: number;
  net:         number;
}

export interface TaxReportDividend {
  symbol:   string;
  date:     string;
  qty:      number;
  perShare: number;
  amount:   number;
}

export interface TaxReportUnmatched {
  symbol:        string;
  sellDate:      string;
  sellPrice:     number;
  unmatchedQty:  number;
}

export interface TaxReport {
  portfolioId: string;
  fy:          string;
  fyStart:     string;
  fyEnd:       string;
  shortTerm:   TaxReportSection;
  longTerm:    TaxReportSection;
  dividends:   { rows: TaxReportDividend[]; count: number; total: number };
  unmatched:   { sells: TaxReportUnmatched[]; count: number };
  notes:       string[];
  error?:      string;
}

export interface EmailDigestSubscription {
  id:              number;
  groupName:       string;
  recipientEmail:  string;
  symbols:         string[];
  sendTimeIst:     string;     // "HH:MM" 24-hour
  enabled:         boolean;
  lastSentDateIst: string | null;
  createdAt:       number;
  updatedAt:       number;
}

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
  /** A/D ratio for the sector. null when declines == 0 (infinite). */
  advanceDeclineRatio?: number | null;
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
    advanceDeclineRatio?: number | string | null;
    /** Market breadth percentage 0–100 */
    breadthScore?: number;
  };
  /** null when declines == 0 (mathematically infinite ratio). UI renders "∞". */
  adRatio: number | null;
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

export type PersonaRegion = "India" | "Global";

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
  region?:    PersonaRegion;
}

export interface PersonaMeta {
  id:         string;
  name:       string;
  firm:       string;
  era:        string;
  philosophy: string;
  signature:  string;
  region?:    PersonaRegion;
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

export interface ConsensusPick {
  symbol:         string;
  name:           string | null;
  sector:         string | null;
  lastPrice:      number | null;
  buyCount:       number;
  avoidCount:     number;
  holdCount:      number;
  total:          number;
  avgScore:       number;
  councilVerdict: AgentVerdict;
}

export interface ConsensusScreenerResponse {
  buyPicks:       ConsensusPick[];
  avoidPicks:     ConsensusPick[];
  thresholdPct:   number;
  thresholdCount: number;
  totalScreened:  number;
  universeSize:   number;
  cachedAt:       string | null;
  scanInProgress: boolean;
  scanProgress:   { done: number; total: number } | null;
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
  // Provenance + staleness — added by the multi-source orchestrator. Optional
  // for backward-compat; older backends without the chain won't send these.
  servedFrom?: string;
  isStale?:    boolean;
  staleDays?:  number | null;
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

export interface GlobalIndex {
  symbol:        string;
  name:          string;
  region:        string;
  flag:          string;
  value:         number | null;
  change:        number | null;
  pChange:       number | null;
  source_blocked?: boolean;
}

export interface GlobalIndicesRegion {
  label:   string;
  indices: GlobalIndex[];
}

export interface GlobalIndicesResponse {
  regions: GlobalIndicesRegion[];
  asOf:    string;
  meta?:   unknown;
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

/** Headline value resolved by the backend's multi-source orchestrator
 *  (Manual override → Trading Economics → RBI direct → DBnomics → FRED →
 *  World Bank). Carries the provenance + staleness signal so the UI can
 *  warn when a tile is months old. */
export interface MacroHeadlinePoint {
  value:       number | null;
  asOf:        string | null;
  servedFrom:  string;          // "Manual" | "TradingEconomics" | "RBI" | "DBnomics" | "FRED" | "WorldBank"
  isStale:     boolean;
  staleDays:   number | null;
}

/** Curated "extra" macro indicator with optional admin-set value.
 *  Returned by GET /api/insights/macro/extras. */
export interface MacroExtra {
  slug:        string;
  label:       string;
  unit:        string;
  category:    string;
  description: string;
  sourceHint:  string;
  value:       number | null;
  asOf:        string | null;
  note:        string | null;
  setBy:       string | null;
  updatedAtMs: number | null;
}

export interface MacroExtrasResponse {
  items: MacroExtra[];
  total: number;
}

export interface MacroDashboardResponse {
  rateTimeline: MacroSeriesPoint[];
  cpi:          MacroSeriesPoint[];
  wpi:          MacroSeriesPoint[];
  iip:          MacroSeriesPoint[];
  gdp:          MacroSeriesPoint[];
  // Headline values from the orchestrator (preferred over last(series) by
  // the tile components for fresh-data display).
  repoNow?:     MacroHeadlinePoint;
  cpiNow?:      MacroHeadlinePoint;
  iipNow?:      MacroHeadlinePoint;
  wpiNow?:      MacroHeadlinePoint;
  gdpNow?:      MacroHeadlinePoint;
  yieldCurve: {
    ind10yNow:        number | null;
    ind10yAsOf:       string | null;
    ind10yServedFrom?: string;
    ind10yHistory:    MacroSeriesPoint[];
    snapshot:         MacroYieldCurvePoint[];
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

const BASE = ((window as any).__ENV__?.VITE_API_URL || import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");

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

export interface DcfResponse {
  symbol:         string;
  companyName:    string;
  currency:       string;
  currentPrice:   number | null;
  intrinsicValue: number;
  marginOfSafety: number | null;
  verdict:        "UNDERVALUED" | "FAIR" | "OVERVALUED" | "UNKNOWN";
  assumptions: {
    baseFcfCr:            number;
    growthYears1to5Pct:   number;
    growthYears6to10Pct:  number;
    terminalGrowthPct:    number;
    waccPct:              number;
    riskFreePct:          number;
    beta:                 string;
    equityRiskPremiumPct: number;
    sharesOutstandingCr:  number;
    totalDebtCr:          number;
    cashCr:               number;
    netDebtCr:            number;
    enterpriseValueCr:    number;
    equityValueCr:        number;
    horizonYears:         number;
    growthSource:         string;
  };
  fcfHistoryCr: number[];
  source:       string;
}

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

  stockDcf: (symbol: string) =>
    fetchApi<DcfResponse>(`/stocks/${encodeURIComponent(symbol)}/dcf`),

  stockTechnicalSummary: (symbol: string, interval = "1d") =>
    fetchApi<TechnicalSummary>(`/stocks/${encodeURIComponent(symbol)}/technical-summary?interval=${interval}`),

  stockTriFactor: (symbol: string) =>
    fetchApi<any>(`/stocks/${encodeURIComponent(symbol)}/tri-factor`),

  // ── Famous-Investor AI Council ──
  agentsList: () =>
    fetchApi<AgentsListResponse>("/agents"),

  agentConsensusScreener: (refresh = false) =>
    fetchApi<ConsensusScreenerResponse>(
      `/agents/screener/consensus${refresh ? "?refresh=1" : ""}`
    ),

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
  globalIndices:  () => fetchApi<GlobalIndicesResponse>("/insights/global-indices"),
  /** Curated extra macro indicators (PMI, FX reserves, unemployment, …)
   *  with whatever admin-set values exist in `macro_overrides`. */
  macroExtras:    () => fetchApi<MacroExtrasResponse>("/insights/macro/extras"),
  /** Admin: upsert a manual override for any whitelisted indicator.
   *  Token from useCustomAuth() is sent as X-Admin-Token. */
  setMacroOverride: (token: string, indicator: string, body: { value: number; asOf: string; note?: string }) =>
    fetchApi<{ ok: boolean }>(
      `/admin/macro/overrides/${encodeURIComponent(indicator)}`,
      {
        method:  "PUT",
        headers: { "Content-Type": "application/json", "X-Admin-Token": token },
        body:    JSON.stringify(body),
      },
    ),

  // ── Top Movers (Dashboard tab) ──
  topMoversAll: (count = 10) =>
    fetchApi<TopMoversAllResponse>(`/dashboard/top-movers/all?count=${count}`),
  topMovers: (segment: "large" | "mid" | "small" | "micro", count = 10) =>
    fetchApi<TopMoversResponse>(
      `/dashboard/top-movers?segment=${segment}&count=${count}`,
    ),

  // ── User broker API keys (Settings) ──
  // Stored encrypted in PG via Phase 2; the GET never returns decrypted
  // credentials, only metadata. PUT replaces creds and resets the test
  // status; DELETE removes the row entirely.
  listBrokerKeys: () =>
    fetchApi<{ keys: BrokerKeyMeta[] }>(`/user/broker-keys`),
  upsertBrokerKey: (
    broker: string,
    creds: Record<string, string>,
    active = true,
  ) =>
    fetchApi<BrokerKeyMeta>(
      `/user/broker-keys/${encodeURIComponent(broker)}`,
      {
        method: "PUT",
        headers: JSON_HEADERS,
        body: JSON.stringify({ creds, active }),
      },
    ),
  deleteBrokerKey: (broker: string) =>
    fetchApi<{ removed: boolean }>(
      `/user/broker-keys/${encodeURIComponent(broker)}`,
      { method: "DELETE" },
    ),
  testBrokerKey: (broker: string) =>
    fetchApi<{ ok: boolean; message: string; stub?: boolean }>(
      `/user/broker-keys/${encodeURIComponent(broker)}/test`,
      { method: "POST" },
    ),

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

  // ── Email digest ──
  emailDigestList: () =>
    fetchApi<{ subscriptions: EmailDigestSubscription[] }>("/email-digest/subscriptions"),
  emailDigestUpsert: (body: {
    groupName?: string;
    recipientEmail: string;
    symbols?: string[];
    sendTimeIst?: string;
    enabled?: boolean;
  }) =>
    fetchApi<EmailDigestSubscription>("/email-digest/subscriptions", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  emailDigestDelete: (id: number) =>
    fetchApi<{ deleted: number }>(`/email-digest/subscriptions/${id}`, {
      method: "DELETE",
    }),
  emailDigestConfig: () =>
    fetchApi<{
      configured: boolean;
      host: string; port: number;
      fromAddress: string; useTls: boolean;
      sendsPerMin: number; sendsPerDay: number;
    }>("/email-digest/config"),
  emailDigestSendNow: (id: number) =>
    fetchApi<{ queued: boolean; subject: string }>(`/email-digest/send-now/${id}`, {
      method: "POST",
    }),

  // Per-stock news (RSS matched to this ticker + Tavily top-up when thin).
  // Used by the "Latest news" panel on Stock Lookup and AI Analyst pages.
  tickerNews: (symbol: string, limit = 20) =>
    fetchApi<{
      symbol: string;
      articles: Array<{
        title:    string;
        summary?: string;
        url:      string;
        source:   string;
        published?: string;
        category?: string;
        sentiment?: string | null;
        image?:    string | null;
        via?:      string;
      }>;
      total: number;
      source: string;
      tavilyUsed: boolean;
      fetchedAt?: string;
      refreshedAt?: string;
    }>(`/news/ticker?symbol=${encodeURIComponent(symbol)}&limit=${limit}`),

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

  // Bulk delete — POST (not DELETE) because DELETE-with-body has shaky
  // proxy support. The cash impact of each row is reversed atomically.
  deletePortfolioTxBulk: (pid: string, ids: string[]) =>
    fetchApi<{ requested: number; deleted: number; skipped: number }>(
      `/portfolio/${encodeURIComponent(pid)}/transactions/bulk-delete`,
      {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify({ ids }),
      },
    ),

  // ── Tax report (Indian FY, FIFO capital gains) ──
  taxReportFys: (pid: string) =>
    fetchApi<{ fys: string[] }>(
      `/portfolio/${encodeURIComponent(pid)}/tax-report/fys`,
    ),
  taxReport: (pid: string, fy: string) => {
    const q = fy ? `?fy=${encodeURIComponent(fy)}` : "";
    return fetchApi<TaxReport>(
      `/portfolio/${encodeURIComponent(pid)}/tax-report${q}`,
    );
  },
  taxReportCsvUrl: (pid: string, fy: string) =>
    // Returns a URL the browser can hit directly (with the bearer token
    // attached by the existing fetch wrapper — we open it via fetch+blob
    // download to keep the auth header intact).
    `/api/portfolio/${encodeURIComponent(pid)}/tax-report.csv${fy ? `?fy=${encodeURIComponent(fy)}` : ""}`,

  // Bulk delete for AI Analyst saved analyses.
  deleteSavedAnalysesBulk: (ids: number[]) =>
    fetchApi<{ requested: number; deleted: number }>(
      "/ai-analyst/saved/bulk-delete",
      {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify({ ids }),
      },
    ),

  importPortfolioCsv: (pid: string, csv: string) =>
    fetchApi<PortfolioImportResult>(`/portfolio/${encodeURIComponent(pid)}/import`, {
      method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ csv }),
    }),

  importPortfolioFile: (pid: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetchApi<PortfolioImportResult & { source_filename?: string }>(
      `/portfolio/${encodeURIComponent(pid)}/import-file`,
      { method: "POST", body: fd },  // browser sets multipart boundary
    );
  },

  // ── Two-step import (mapping popup) ────────────────────────────────────────
  // Step 1: upload file, get detected columns + suggested mapping + preview.
  // Step 2: send back the same CSV text + user-confirmed mapping to commit.
  previewPortfolioImport: (pid: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetchApi<PortfolioImportPreview>(
      `/portfolio/${encodeURIComponent(pid)}/preview-import`,
      { method: "POST", body: fd },
    );
  },
  importPortfolioWithMapping: (
    pid: string,
    csvText: string,
    mapping: Record<string, number | null>,
    synth: Record<string, string>,
  ) =>
    fetchApi<PortfolioImportResult>(
      `/portfolio/${encodeURIComponent(pid)}/import-with-mapping`,
      {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify({ csvText, mapping, synth }),
      },
    ),

  // Vision-LLM extraction from a broker screenshot. Returns extracted rows
  // + confidence; nothing is written to the DB until applyExtractedHoldings
  // is called with the user-confirmed subset.
  extractPortfolioFromImage: (pid: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetchApi<{
      filename: string;
      rowsFound: number;
      holdings: Array<{
        symbol: string;
        qty: number;
        avgPrice: number;
        confidence: number;
        rawName?: string | null;
      }>;
    }>(
      `/portfolio/${encodeURIComponent(pid)}/extract-from-image`,
      { method: "POST", body: fd },
    );
  },

  applyExtractedHoldings: (
    pid: string,
    holdings: Array<{
      symbol: string;
      qty: number;
      avgPrice: number;
      confidence: number;
      rawName?: string | null;
    }>,
    tradedAt?: string,
  ) =>
    fetchApi<{ rowsApplied: number; rowsRejected: number; errors: string[] }>(
      `/portfolio/${encodeURIComponent(pid)}/apply-extracted`,
      {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify({ holdings, tradedAt, source: "screenshot" }),
      },
    ),

  portfolioRisk: (pid: string, params: PortfolioRiskParams = {}) =>
    fetchApi<PortfolioRiskResult>(`/portfolio/${encodeURIComponent(pid)}/risk`, {
      method: "POST", headers: JSON_HEADERS, body: JSON.stringify(params),
    }),

  portfolioPerformance: (pid: string, benchmark = "NIFTY 50", days = 365) =>
    fetchApi<PortfolioPerformance>(
      `/portfolio/${encodeURIComponent(pid)}/performance?benchmark=${encodeURIComponent(benchmark)}&days=${days}`,
    ),

  /** Pairwise Pearson correlation between every open holding's daily
   *  returns + portfolio beta vs benchmark. Feeds the heatmap and Beta
   *  KPI tile on the Risk tab. */
  portfolioCorrelation: (pid: string, lookbackDays = 365) =>
    fetchApi<PortfolioCorrelationResult>(
      `/portfolio/${encodeURIComponent(pid)}/correlation?lookbackDays=${lookbackDays}`,
    ),

  /** Running drawdown timeseries derived from the equity curve. */
  portfolioDrawdown: (pid: string, lookbackDays = 365) =>
    fetchApi<PortfolioDrawdownResult>(
      `/portfolio/${encodeURIComponent(pid)}/drawdown?lookbackDays=${lookbackDays}`,
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
  available: boolean;
  error: string | null;
  cached: boolean;
  refreshedAt: string;
  fetchedAt: string;
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
  priceSource?:     string | null;
  priceServedFrom?: string | null;
}

export interface SectorDetailData {
  symbol:          string;
  name:            string;
  marketCap:       number;
  /** True when the official sector-index history is unavailable (e.g. the
   *  Yahoo ticker is delisted) and we reconstruct the series from
   *  equal-weighted constituents. Performance/RS numbers are then approximations. */
  historySynthetic?: boolean;
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
  meta?: {
    source?:       string;
    asOf?:         string | null;
    marketState?:  string | null;
    note?:         string;
    [k: string]:   unknown;
  };
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

// ── Top Movers (Dashboard tab) ─────────────────────────────────────────────
export interface TopMoverRow {
  symbol:        string;
  name?:         string | null;
  lastPrice?:    number | null;
  change?:       number | null;
  pChange:       number;
  open?:         number | null;
  dayHigh?:      number | null;
  dayLow?:       number | null;
  previousClose?: number | null;
  volume?:       number | null;
  valueLakhs?:   number | null;
  yearHigh?:     number | null;
  yearLow?:      number | null;
}
export interface TopMoversResponse {
  available:    boolean;
  segment:      "large" | "mid" | "small" | "micro";
  label?:       string;
  indexSlug?:   string;
  asOf?:        string;
  marketState?: string;
  totalScanned?: number;
  gainers:      TopMoverRow[];
  losers:       TopMoverRow[];
  message?:     string;
  /** Which upstream provided the values: "NSE" (bulk index endpoint) or
   *  "Yahoo" (per-stock fallback when NSE blocked us). */
  servedFrom?:  string;
}
export interface TopMoversAllResponse {
  fetchedAt: string;
  segments:  Record<"large" | "mid" | "small" | "micro", TopMoversResponse>;
}

// ── User broker API key metadata ────────────────────────────────────────────
// Returned by /user/broker-keys list endpoint. Note: this NEVER contains the
// actual credentials — the API deliberately never returns decrypted values
// over HTTP. The frontend uses `configured` to render the per-broker card
// state but always asks the user to re-enter on update.
export interface BrokerKeyMeta {
  broker:          string;
  active:          boolean;
  configured:      boolean;
  lastTestStatus?: string;   // "ok" | "failed" | ""
  lastTestAtMs?:   number;
  lastTestError?:  string;
  createdAt?:      number;
  updatedAt?:      number;
}

/** Preview returned by /portfolio/{pid}/preview-import — drives the
 *  mapping popup before any DB writes happen. */
export interface PortfolioImportPreview {
  format:            string;
  headerless:        boolean;
  sourceColumns:     string[];
  sampleRows:        string[][];
  suggestedMapping:  Record<string, number | null>;
  syntheticDefaults: Record<string, string>;
  totalRows:         number;
  errors:            string[];
  csvText:           string;
  source_filename?:  string;
}

export interface PortfolioRiskParams {
  confidence?:    number;
  horizonDays?:   number;
  riskFreeRate?:  number;
  lookbackDays?:  number;
}

/** Pairwise Pearson correlation between every open holding + portfolio
 *  beta vs benchmark. `matrix[i][j]` is corr(symbols[i], symbols[j]),
 *  always in [-1, 1]. Empty `matrix` means insufficient overlapping
 *  history (fewer than 30 common trading days). */
export interface PortfolioCorrelationResult {
  portfolioId:     string;
  symbols:         string[];
  matrix:          number[][];
  observationDays: number;
  beta:            number | null;
  benchmarkSymbol: string;
}

/** Running drawdown timeseries. Each point is `equity` valued against
 *  the running `peak`; `drawdown` (%) is always ≤ 0. `maxDrawdownPct`
 *  is the deepest point and `maxDrawdownDate` is when it happened. */
export interface PortfolioDrawdownResult {
  portfolioId:      string;
  series:           Array<{
    date:     string;
    equity:   number;
    peak:     number;
    drawdown: number;  // negative %, e.g. -12.34 means 12.34% below peak
  }>;
  maxDrawdownPct:   number;
  maxDrawdownDate:  string | null;
  observationDays:  number;
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
