import { Injectable, Logger } from '@nestjs/common';
import { YahooService } from '../../common/yahoo/yahoo.service';
import { NseService } from '../../common/nse/nse.service';
import {
  calculateEMA,
  calculateRSI,
  calculateMACD,
  calculateBollingerBands,
  OHLCV,
} from '../../common/utils/indicators.util';

export interface ScannerConfig {
  id: string;
  name: string;
  description?: string;
  conditions: ScannerCondition[];
  universe: ('NIFTY100' | 'MIDCAP' | 'SMALLCAP')[];
  createdAt: string;
  updatedAt: string;
}

export interface ScannerCondition {
  indicator: 'EMA' | 'RSI' | 'MACD' | 'VOLUME' | 'PRICE' | 'BOLLINGER';
  parameter?: number;
  operator: 'ABOVE' | 'BELOW' | 'CROSSES_ABOVE' | 'CROSSES_BELOW' | 'BETWEEN';
  value: number;
  value2?: number;
  period?: number;
  period2?: number;
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

const NIFTY100_SYMBOLS = [
  'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'HINDUNILVR', 'ITC', 'SBIN', 'BHARTIARTL',
  'KOTAKBANK', 'BAJFINANCE', 'AXISBANK', 'ASIANPAINT', 'MARUTI', 'HCLTECH', 'WIPRO', 'TITAN',
  'POWERGRID', 'NTPC', 'SUNPHARMA', 'ONGC', 'TATAMOTORS', 'LT', 'M&M', 'TATASTEEL', 'JSWSTEEL',
  'COALINDIA', 'BAJAJ-AUTO', 'DIVISLAB', 'CIPLA', 'DRREDDY', 'TECHM', 'HINDALCO', 'GRASIM',
];

const MIDCAP_SYMBOLS = [
  'PERSISTENT', 'COFORGE', 'MPHASIS', 'LTTS', 'KPITTECH', 'AFFLE', 'METROPOLIS',
  'THYROCARE', 'IEX', 'CAMS', 'CDSL', 'MCX', 'ROUTE', 'IRCTC', 'DELHIVERY',
];

const SMALLCAP_SYMBOLS = [
  'TATAELXSI', 'CYIENT', 'NIITTECH', 'MASTEK', 'BIRLASOFT', 'INFOEDGE', 'JUSTDIAL',
];

@Injectable()
export class ScannersService {
  private readonly logger = new Logger(ScannersService.name);
  private scanners: Map<string, ScannerConfig> = new Map();
  private idCounter = 1;

  constructor(
    private readonly yahooService: YahooService,
    private readonly nseService: NseService,
  ) {
    this.initDefaultScanners();
  }

  private initDefaultScanners(): void {
    const defaultScanners: Omit<ScannerConfig, 'id' | 'createdAt' | 'updatedAt'>[] = [
      {
        name: 'RSI Oversold Bounce',
        description: 'Find stocks with RSI below 35 and price above EMA50 — potential bounce candidates',
        universe: ['NIFTY100', 'MIDCAP'],
        conditions: [
          { indicator: 'RSI', period: 14, operator: 'BELOW', value: 35 },
          { indicator: 'EMA', period: 50, operator: 'BELOW', value: 0 },
        ],
      },
      {
        name: 'EMA Breakout',
        description: 'Stocks where EMA9 just crossed above EMA21 — early trend change signal',
        universe: ['NIFTY100'],
        conditions: [
          { indicator: 'EMA', period: 9, operator: 'CROSSES_ABOVE', value: 0, period2: 21 },
          { indicator: 'RSI', period: 14, operator: 'BETWEEN', value: 45, value2: 65 },
        ],
      },
      {
        name: 'Momentum Strong',
        description: 'Stocks with RSI between 55-70 and price above EMA200 — momentum continuation',
        universe: ['NIFTY100', 'MIDCAP'],
        conditions: [
          { indicator: 'RSI', period: 14, operator: 'BETWEEN', value: 55, value2: 70 },
          { indicator: 'EMA', period: 200, operator: 'BELOW', value: 0 },
        ],
      },
      {
        name: 'Bollinger Band Squeeze',
        description: 'Stocks near Bollinger Band lower — potential mean reversion play',
        universe: ['NIFTY100', 'MIDCAP', 'SMALLCAP'],
        conditions: [
          { indicator: 'BOLLINGER', period: 20, operator: 'BELOW', value: 0 },
          { indicator: 'RSI', period: 14, operator: 'BELOW', value: 45 },
        ],
      },
    ];

    defaultScanners.forEach(scanner => {
      const id = `scanner-${this.idCounter++}`;
      this.scanners.set(id, {
        ...scanner,
        id,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      });
    });
  }

  getAllScanners(): ScannerConfig[] {
    return Array.from(this.scanners.values());
  }

  getScannerById(id: string): ScannerConfig | null {
    return this.scanners.get(id) || null;
  }

  createScanner(data: Omit<ScannerConfig, 'id' | 'createdAt' | 'updatedAt'>): ScannerConfig {
    const id = `scanner-${this.idCounter++}`;
    const scanner: ScannerConfig = {
      ...data,
      id,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    this.scanners.set(id, scanner);
    return scanner;
  }

  updateScanner(id: string, data: Partial<ScannerConfig>): ScannerConfig | null {
    const existing = this.scanners.get(id);
    if (!existing) return null;
    const updated = { ...existing, ...data, id, updatedAt: new Date().toISOString() };
    this.scanners.set(id, updated);
    return updated;
  }

  deleteScanner(id: string): boolean {
    return this.scanners.delete(id);
  }

  async runScanner(id: string): Promise<any> {
    const scanner = this.scanners.get(id);
    if (!scanner) return { error: 'Scanner not found' };

    const symbols = this.getSymbolsForUniverse(scanner.universe);
    const results: ScanResult[] = [];

    this.logger.log(`Running scanner "${scanner.name}" on ${symbols.length} symbols...`);

    for (const symbol of symbols.slice(0, 30)) {
      try {
        const history = await this.yahooService.getHistoricalData(symbol, 60);
        if (history.length < 21) continue;

        const result = await this.evaluateConditions(symbol, history, scanner.conditions);
        results.push(result);
        await new Promise(resolve => setTimeout(resolve, 300));
      } catch (err) {
        this.logger.warn(`Scanner error for ${symbol}: ${err.message}`);
      }
    }

    const matched = results.filter(r => r.allConditionsMet);
    return {
      scannerId: id,
      scannerName: scanner.name,
      runAt: new Date().toISOString(),
      totalScanned: results.length,
      totalMatched: matched.length,
      results: matched.sort((a, b) => b.score - a.score),
    };
  }

  private getSymbolsForUniverse(universe: string[]): string[] {
    const symbols: string[] = [];
    if (universe.includes('NIFTY100')) symbols.push(...NIFTY100_SYMBOLS);
    if (universe.includes('MIDCAP')) symbols.push(...MIDCAP_SYMBOLS);
    if (universe.includes('SMALLCAP')) symbols.push(...SMALLCAP_SYMBOLS);
    return [...new Set(symbols)];
  }

  private async evaluateConditions(symbol: string, history: any[], conditions: ScannerCondition[]): Promise<ScanResult> {
    const ohlcv: OHLCV[] = history;
    const closes = ohlcv.map(d => d.close).filter(Boolean);
    const lastClose = closes[closes.length - 1];
    const matchedConditions: string[] = [];
    let conditionsMet = 0;

    for (const condition of conditions) {
      const met = this.checkCondition(ohlcv, closes, condition, lastClose);
      if (met.met) {
        matchedConditions.push(met.description);
        conditionsMet++;
      }
    }

    return {
      symbol,
      companyName: symbol,
      lastPrice: lastClose,
      change: lastClose - closes[closes.length - 2] || 0,
      pChange: closes.length >= 2 ? ((lastClose - closes[closes.length - 2]) / closes[closes.length - 2]) * 100 : 0,
      matchedConditions,
      allConditionsMet: conditionsMet === conditions.length,
      score: (conditionsMet / conditions.length) * 100,
    };
  }

  private checkCondition(ohlcv: OHLCV[], closes: number[], condition: ScannerCondition, lastClose: number): { met: boolean; description: string } {
    const { indicator, period, period2, operator, value, value2 } = condition;

    switch (indicator) {
      case 'RSI': {
        const rsi = calculateRSI(closes, period || 14);
        const lastRsi = rsi[rsi.length - 1];
        if (!lastRsi) return { met: false, description: '' };
        if (operator === 'BELOW') {
          const met = lastRsi < value;
          return { met, description: `RSI(${period}) ${lastRsi.toFixed(1)} < ${value}` };
        }
        if (operator === 'ABOVE') {
          const met = lastRsi > value;
          return { met, description: `RSI(${period}) ${lastRsi.toFixed(1)} > ${value}` };
        }
        if (operator === 'BETWEEN' && value2 !== undefined) {
          const met = lastRsi > value && lastRsi < value2;
          return { met, description: `RSI(${period}) ${lastRsi.toFixed(1)} between ${value}-${value2}` };
        }
        break;
      }

      case 'EMA': {
        const ema = calculateEMA(closes, period || 20);
        const lastEma = ema[ema.length - 1];
        if (!lastEma) return { met: false, description: '' };

        if (operator === 'ABOVE') {
          const met = lastClose > lastEma;
          return { met, description: `Price above EMA${period} (${lastEma.toFixed(2)})` };
        }
        if (operator === 'BELOW') {
          const met = lastClose > lastEma;
          return { met, description: `Price above EMA${period} (${lastEma.toFixed(2)})` };
        }
        if (operator === 'CROSSES_ABOVE' && period2) {
          const ema1 = calculateEMA(closes, period);
          const ema2 = calculateEMA(closes, period2);
          if (ema1.length >= 2 && ema2.length >= 2) {
            const prevDiff = ema1[ema1.length - 2] - ema2[ema2.length - 2];
            const currDiff = ema1[ema1.length - 1] - ema2[ema2.length - 1];
            const met = prevDiff < 0 && currDiff > 0;
            return { met, description: `EMA${period} crossed above EMA${period2}` };
          }
        }
        if (operator === 'CROSSES_BELOW' && period2) {
          const ema1 = calculateEMA(closes, period);
          const ema2 = calculateEMA(closes, period2);
          if (ema1.length >= 2 && ema2.length >= 2) {
            const prevDiff = ema1[ema1.length - 2] - ema2[ema2.length - 2];
            const currDiff = ema1[ema1.length - 1] - ema2[ema2.length - 1];
            const met = prevDiff > 0 && currDiff < 0;
            return { met, description: `EMA${period} crossed below EMA${period2}` };
          }
        }
        break;
      }

      case 'BOLLINGER': {
        const bb = calculateBollingerBands(closes, period || 20);
        const lastLower = bb.lower[bb.lower.length - 1];
        const lastUpper = bb.upper[bb.upper.length - 1];
        if (operator === 'BELOW') {
          const met = lastClose < lastLower;
          return { met, description: `Price below BB lower (${lastLower?.toFixed(2)})` };
        }
        if (operator === 'ABOVE') {
          const met = lastClose > lastUpper;
          return { met, description: `Price above BB upper (${lastUpper?.toFixed(2)})` };
        }
        break;
      }

      case 'MACD': {
        const macd = calculateMACD(closes);
        const lastHist = macd.histogram[macd.histogram.length - 1];
        if (operator === 'ABOVE') {
          const met = lastHist > 0;
          return { met, description: `MACD histogram positive (${lastHist?.toFixed(3)})` };
        }
        if (operator === 'BELOW') {
          const met = lastHist < 0;
          return { met, description: `MACD histogram negative (${lastHist?.toFixed(3)})` };
        }
        break;
      }

      case 'PRICE': {
        if (operator === 'ABOVE') {
          const met = lastClose > value;
          return { met, description: `Price ₹${lastClose.toFixed(2)} > ₹${value}` };
        }
        if (operator === 'BELOW') {
          const met = lastClose < value;
          return { met, description: `Price ₹${lastClose.toFixed(2)} < ₹${value}` };
        }
        break;
      }
    }

    return { met: false, description: '' };
  }
}
