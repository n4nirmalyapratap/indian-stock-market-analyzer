import { Injectable, Logger } from '@nestjs/common';
import { Cron, CronExpression } from '@nestjs/schedule';
import { YahooService } from '../../common/yahoo/yahoo.service';
import { NseService } from '../../common/nse/nse.service';
import { calculateEMA, calculateRSI, OHLCV } from '../../common/utils/indicators.util';

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

const NIFTY100_SYMBOLS = [
  'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'HINDUNILVR', 'ITC', 'SBIN', 'BHARTIARTL', 'KOTAKBANK',
  'BAJFINANCE', 'AXISBANK', 'ASIANPAINT', 'MARUTI', 'HCLTECH', 'ULTRACEMCO', 'WIPRO', 'NESTLEIND', 'TITAN',
  'POWERGRID', 'NTPC', 'SUNPHARMA', 'ONGC', 'TATAMOTORS', 'LT', 'M&M', 'ADANIENT', 'TATASTEEL', 'JSWSTEEL',
  'COALINDIA', 'BAJAJFINSV', 'BAJAJ-AUTO', 'DIVISLAB', 'CIPLA', 'DRREDDY', 'TECHM', 'HINDALCO', 'GRASIM',
  'EICHERMOT', 'BPCL', 'INDUSINDBK', 'HEROMOTOCO', 'APOLLOHOSP', 'PIDILITIND', 'DMART', 'SHREECEM',
  'TATACONSUM', 'SBILIFE', 'HDFCLIFE', 'ICICIPRULI',
];

const MIDCAP_SYMBOLS = [
  'PERSISTENT', 'COFORGE', 'MPHASIS', 'LTTS', 'KPITTECH', 'AFFLE', 'TANLA', 'HAPPYMINDS',
  'METROPOLIS', 'THYROCARE', 'KRSNAA', 'VIJAYADIAG', 'LALPATHLAB', 'POLYMED', 'MAXHEALTH',
  'IEX', 'CAMS', 'CDSL', 'MCX', 'BSE', 'ANGELONE', 'MOTILALOFS',
  'ROUTE', 'IRCTC', 'DELHIVERY', 'NUVOCO', 'RAMCOCEM', 'JKCEMENT', 'HEIDELBERG',
];

const SMALLCAP_SYMBOLS = [
  'TATAELXSI', 'CYIENT', 'NIITTECH', 'MASTEK', 'BIRLASOFT', 'MINDTREE', 'INFOEDGE',
  'JUSTDIAL', 'NAUKRI', 'POLICYBZR', 'PAYTM', 'ZOMATO', 'NYKAA', 'CARTRADE',
];

@Injectable()
export class PatternsService {
  private readonly logger = new Logger(PatternsService.name);
  private cachedPatterns: ChartPattern[] = [];
  private lastScanTime: string = '';

  constructor(
    private readonly yahooService: YahooService,
    private readonly nseService: NseService,
  ) {}

  @Cron('0 17 * * 1-5')
  async scheduledScan(): Promise<void> {
    this.logger.log('Running scheduled chart pattern scan after market close...');
    await this.runFullScan();
  }

  async runFullScan(): Promise<ChartPattern[]> {
    this.logger.log('Starting full chart pattern scan...');
    const allPatterns: ChartPattern[] = [];

    const nifty100Patterns = await this.scanUniverse(NIFTY100_SYMBOLS.slice(0, 20), 'NIFTY100');
    const midcapPatterns = await this.scanUniverse(MIDCAP_SYMBOLS.slice(0, 10), 'MIDCAP');
    const smallcapPatterns = await this.scanUniverse(SMALLCAP_SYMBOLS.slice(0, 8), 'SMALLCAP');

    allPatterns.push(...nifty100Patterns, ...midcapPatterns, ...smallcapPatterns);
    this.cachedPatterns = allPatterns.sort((a, b) => b.confidence - a.confidence);
    this.lastScanTime = new Date().toISOString();
    this.logger.log(`Scan complete: found ${allPatterns.length} patterns`);
    return this.cachedPatterns;
  }

  private async scanUniverse(symbols: string[], universe: 'NIFTY100' | 'MIDCAP' | 'SMALLCAP'): Promise<ChartPattern[]> {
    const patterns: ChartPattern[] = [];

    for (const symbol of symbols) {
      try {
        const history = await this.yahooService.getHistoricalData(symbol, 90);
        if (history.length < 20) continue;

        const detected = this.detectPatterns(symbol, history, universe);
        patterns.push(...detected);
        await new Promise(resolve => setTimeout(resolve, 500));
      } catch (err) {
        this.logger.warn(`Pattern scan failed for ${symbol}: ${err.message}`);
      }
    }

    return patterns;
  }

  private detectPatterns(symbol: string, history: any[], universe: 'NIFTY100' | 'MIDCAP' | 'SMALLCAP'): ChartPattern[] {
    const patterns: ChartPattern[] = [];
    const ohlcv: OHLCV[] = history;
    const closes = ohlcv.map(d => d.close);
    const n = ohlcv.length;
    const lastCandle = ohlcv[n - 1];
    const lastClose = closes[n - 1];

    const rsi = calculateRSI(closes, 14);
    const lastRsi = rsi[rsi.length - 1];
    const ema20 = calculateEMA(closes, 20);
    const ema50 = calculateEMA(closes, 50);
    const lastEma20 = ema20[ema20.length - 1];
    const lastEma50 = ema50[ema50.length - 1];

    // Bullish Engulfing
    if (n >= 2) {
      const prev = ohlcv[n - 2];
      const curr = ohlcv[n - 1];
      if (prev.close < prev.open && curr.close > curr.open &&
          curr.open < prev.close && curr.close > prev.open) {
        patterns.push(this.createPattern(symbol, universe, 'Bullish Engulfing', 'BULLISH', 'CALL', 75,
          lastClose, lastClose * 1.03, lastClose * 0.98,
          'Strong reversal signal: current candle completely engulfs previous bearish candle', '1D'));
      }
    }

    // Bearish Engulfing
    if (n >= 2) {
      const prev = ohlcv[n - 2];
      const curr = ohlcv[n - 1];
      if (prev.close > prev.open && curr.close < curr.open &&
          curr.open > prev.close && curr.close < prev.open) {
        patterns.push(this.createPattern(symbol, universe, 'Bearish Engulfing', 'BEARISH', 'PUT', 75,
          lastClose, lastClose * 0.97, lastClose * 1.02,
          'Reversal signal: bears took control, current candle engulfs previous bullish candle', '1D'));
      }
    }

    // Doji (indecision)
    const dojiBody = Math.abs(lastCandle.close - lastCandle.open);
    const dojiRange = lastCandle.high - lastCandle.low;
    if (dojiRange > 0 && dojiBody / dojiRange < 0.1 && dojiRange > 0) {
      const signal = lastClose > lastEma20 ? 'PUT' : 'CALL';
      const type = lastClose > lastEma20 ? 'BEARISH' : 'BULLISH';
      patterns.push(this.createPattern(symbol, universe, 'Doji', type, signal, 60,
        lastClose, undefined, undefined,
        'Indecision candle: buyers and sellers in balance. Watch for next candle direction', '1D'));
    }

    // RSI Oversold Bounce
    if (lastRsi < 35 && lastClose > lastEma50) {
      patterns.push(this.createPattern(symbol, universe, 'RSI Oversold Bounce', 'BULLISH', 'CALL', 70,
        lastClose, lastClose * 1.04, lastClose * 0.97,
        `RSI at ${lastRsi?.toFixed(1)} — oversold but price above EMA50. Bounce opportunity`, '1D'));
    }

    // RSI Overbought Reversal
    if (lastRsi > 72 && lastClose < lastEma20 * 1.05) {
      patterns.push(this.createPattern(symbol, universe, 'RSI Overbought', 'BEARISH', 'PUT', 65,
        lastClose, undefined, lastClose * 1.03,
        `RSI at ${lastRsi?.toFixed(1)} — overbought zone. Potential correction ahead`, '1D'));
    }

    // EMA Crossover Bullish
    if (ema20.length >= 2 && ema50.length >= 2) {
      const prevEma20 = ema20[ema20.length - 2];
      const prevEma50 = ema50[ema50.length - 2];
      if (prevEma20 < prevEma50 && lastEma20 > lastEma50) {
        patterns.push(this.createPattern(symbol, universe, 'EMA Golden Cross (20/50)', 'BULLISH', 'CALL', 80,
          lastClose, lastClose * 1.05, lastClose * 0.97,
          'EMA20 crossed above EMA50 — classic golden cross buy signal', '1D'));
      }
      if (prevEma20 > prevEma50 && lastEma20 < lastEma50) {
        patterns.push(this.createPattern(symbol, universe, 'EMA Death Cross (20/50)', 'BEARISH', 'PUT', 80,
          lastClose, undefined, lastClose * 1.03,
          'EMA20 crossed below EMA50 — death cross sell signal', '1D'));
      }
    }

    // Hammer
    const hammerbody = Math.abs(lastCandle.close - lastCandle.open);
    const hammerLowerShadow = Math.min(lastCandle.open, lastCandle.close) - lastCandle.low;
    const hammerUpperShadow = lastCandle.high - Math.max(lastCandle.open, lastCandle.close);
    if (hammerLowerShadow > 2 * hammerbody && hammerUpperShadow < hammerbody && lastRsi < 50) {
      patterns.push(this.createPattern(symbol, universe, 'Hammer', 'BULLISH', 'CALL', 72,
        lastClose, lastClose * 1.04, lastClose * 0.97,
        'Hammer pattern: sellers tried but buyers pushed price back up. Bullish reversal likely', '1D'));
    }

    // Shooting Star
    const starUpperShadow = lastCandle.high - Math.max(lastCandle.open, lastCandle.close);
    const starBody = Math.abs(lastCandle.close - lastCandle.open);
    const starLowerShadow = Math.min(lastCandle.open, lastCandle.close) - lastCandle.low;
    if (starUpperShadow > 2 * starBody && starLowerShadow < starBody && lastRsi > 55) {
      patterns.push(this.createPattern(symbol, universe, 'Shooting Star', 'BEARISH', 'PUT', 72,
        lastClose, undefined, lastClose * 1.03,
        'Shooting star: buyers pushed high but sellers took over. Bearish reversal likely', '1D'));
    }

    return patterns;
  }

  private createPattern(
    symbol: string,
    universe: 'NIFTY100' | 'MIDCAP' | 'SMALLCAP',
    pattern: string,
    patternType: 'BULLISH' | 'BEARISH' | 'NEUTRAL',
    signal: 'CALL' | 'PUT' | 'WAIT',
    confidence: number,
    currentPrice: number,
    targetPrice?: number,
    stopLoss?: number,
    description: string = '',
    timeframe: string = '1D',
  ): ChartPattern {
    return {
      symbol,
      companyName: symbol,
      pattern,
      patternType,
      signal,
      confidence,
      detectedAt: new Date().toISOString(),
      currentPrice,
      targetPrice,
      stopLoss,
      description,
      timeframe,
      universe,
    };
  }

  async getPatterns(universe?: string, signal?: string): Promise<any> {
    let patterns = this.cachedPatterns;

    if (patterns.length === 0) {
      patterns = await this.runFullScan();
    }

    if (universe) {
      patterns = patterns.filter(p => p.universe === universe.toUpperCase());
    }
    if (signal) {
      patterns = patterns.filter(p => p.signal === signal.toUpperCase());
    }

    const callPatterns = patterns.filter(p => p.signal === 'CALL');
    const putPatterns = patterns.filter(p => p.signal === 'PUT');

    return {
      lastScanTime: this.lastScanTime || new Date().toISOString(),
      totalPatterns: patterns.length,
      callSignals: callPatterns.length,
      putSignals: putPatterns.length,
      patterns: patterns.slice(0, 50),
      topCalls: callPatterns.slice(0, 10),
      topPuts: putPatterns.slice(0, 10),
    };
  }

  async triggerScan(): Promise<any> {
    this.logger.log('Manual scan triggered');
    const patterns = await this.runFullScan();
    return {
      message: 'Scan complete',
      totalFound: patterns.length,
      callSignals: patterns.filter(p => p.signal === 'CALL').length,
      putSignals: patterns.filter(p => p.signal === 'PUT').length,
      patterns: patterns.slice(0, 20),
    };
  }
}
