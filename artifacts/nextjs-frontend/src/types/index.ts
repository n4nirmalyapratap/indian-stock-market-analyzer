export interface Sector {
  name: string;
  symbol: string;
  category: string;
  lastPrice: number;
  change: number;
  pChange: number;
  open?: number;
  high?: number;
  low?: number;
  previousClose?: number;
  yearHigh?: number;
  yearLow?: number;
  advances?: number;
  declines?: number;
  momentum: number;
  focus: 'BUY' | 'HOLD' | 'AVOID';
  source: string;
}

export interface SectorRotation {
  date: string;
  timestamp: string;
  sectors: Sector[];
  topPerformers: Sector[];
  laggards: Sector[];
  currentlyFocused: string[];
  whereToBuyNow: Sector[];
  marketBreadth: {
    advancing: number;
    declining: number;
    unchanged: number;
    total: number;
    advanceDeclineRatio: string;
    breadthScore: string;
  };
  rotationPhase: string;
  recommendation: string;
}

export interface StockData {
  symbol: string;
  companyName?: string;
  industry?: string;
  sector?: string;
  lastPrice?: number;
  change?: number;
  pChange?: number;
  open?: number;
  previousClose?: number;
  volume?: number;
  marketCap?: number;
  fiftyTwoWeekHigh?: number;
  fiftyTwoWeekLow?: number;
  technicalAnalysis?: TechnicalAnalysis;
  insight?: string;
  entryRecommendation?: EntryRecommendation;
  historicalData?: OHLCVData[];
  error?: string;
}

export interface TechnicalAnalysis {
  currentPrice: number;
  ema: {
    ema9: number;
    ema21: number;
    ema50: number;
    ema200: number;
  };
  rsi: number;
  rsiZone: 'OVERBOUGHT' | 'OVERSOLD' | 'NEUTRAL';
  macd: {
    value: number;
    signal: number;
    histogram: number;
    crossover: 'BULLISH' | 'BEARISH';
  };
  bollingerBands: {
    upper: number;
    middle: number;
    lower: number;
    bandwidth: string;
    position: 'ABOVE_UPPER' | 'BELOW_LOWER' | 'INSIDE';
  };
  atr: number;
  vwap: number;
  trend: 'STRONG_BULLISH' | 'BULLISH' | 'NEUTRAL' | 'BEARISH' | 'STRONG_BEARISH';
  supports: number[];
  resistances: number[];
  nearestSupport?: number;
  nearestResistance?: number;
}

export interface EntryRecommendation {
  signal: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  entryCall: 'ENTRY_CALL' | 'ENTRY_PUT' | 'WAIT' | 'AVOID';
  confidence: string;
  bullishFactors: number;
  bearishFactors: number;
  targetPrice?: number;
  stopLoss?: number;
  riskReward?: string;
  summary: string;
}

export interface OHLCVData {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ChartPattern {
  symbol: string;
  companyName: string;
  pattern: string;
  patternType: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  signal: 'CALL' | 'PUT' | 'WAIT';
  confidence: number;
  detectedAt: string;
  currentPrice: number;
  targetPrice?: number;
  stopLoss?: number;
  description: string;
  timeframe: string;
  universe: 'NIFTY100' | 'MIDCAP' | 'SMALLCAP';
}

export interface PatternsData {
  lastScanTime: string;
  totalPatterns: number;
  callSignals: number;
  putSignals: number;
  patterns: ChartPattern[];
  topCalls: ChartPattern[];
  topPuts: ChartPattern[];
}

export interface ScannerCondition {
  indicator: 'EMA' | 'RSI' | 'MACD' | 'VOLUME' | 'PRICE' | 'BOLLINGER';
  period?: number;
  period2?: number;
  operator: 'ABOVE' | 'BELOW' | 'CROSSES_ABOVE' | 'CROSSES_BELOW' | 'BETWEEN';
  value: number;
  value2?: number;
}

export interface Scanner {
  id: string;
  name: string;
  description?: string;
  conditions: ScannerCondition[];
  universe: ('NIFTY100' | 'MIDCAP' | 'SMALLCAP')[];
  createdAt: string;
  updatedAt: string;
}

export interface ScanResult {
  symbol: string;
  companyName: string;
  lastPrice: number;
  change: number;
  pChange: number;
  matchedConditions: string[];
  allConditionsMet: boolean;
  score: number;
}

export interface ScannerRunResult {
  scannerId: string;
  scannerName: string;
  runAt: string;
  totalScanned: number;
  totalMatched: number;
  results: ScanResult[];
}

export interface WhatsAppStatus {
  isConnected: boolean;
  botEnabled: boolean;
  qrCodeAvailable: boolean;
  qrCode?: string;
  messageCount: number;
  lastActivity?: string;
  capabilities: string[];
}

export interface BotMessage {
  message: { from: string; body: string; timestamp: string };
  response: string;
  timestamp: string;
}
