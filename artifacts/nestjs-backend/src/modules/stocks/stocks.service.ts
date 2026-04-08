import { Injectable, Logger } from '@nestjs/common';
import { NseService } from '../../common/nse/nse.service';
import { YahooService } from '../../common/yahoo/yahoo.service';
import {
  calculateEMA,
  calculateRSI,
  calculateMACD,
  calculateBollingerBands,
  calculateATR,
  calculateVWAP,
  detectSupportsResistances,
  OHLCV,
} from '../../common/utils/indicators.util';

@Injectable()
export class StocksService {
  private readonly logger = new Logger(StocksService.name);

  constructor(
    private readonly nseService: NseService,
    private readonly yahooService: YahooService,
  ) {}

  async getStockDetails(symbol: string): Promise<any> {
    const upperSymbol = symbol.toUpperCase();

    let quoteData = null;
    let historicalData: OHLCV[] = [];

    try {
      const nseQuote = await this.nseService.getStockQuote(upperSymbol);
      if (nseQuote?.priceInfo) {
        quoteData = this.parseNseQuote(nseQuote, upperSymbol);
      }
    } catch (err) {
      this.logger.warn(`NSE quote failed for ${upperSymbol}`);
    }

    if (!quoteData) {
      const yahooQuote = await this.yahooService.getQuote(upperSymbol);
      if (yahooQuote) {
        quoteData = yahooQuote;
      }
    }

    try {
      const yahooHistory = await this.yahooService.getHistoricalData(upperSymbol, 180);
      if (yahooHistory.length > 0) {
        historicalData = yahooHistory;
      }
    } catch (err) {
      this.logger.warn(`Historical data fetch failed for ${upperSymbol}`);
    }

    if (!quoteData) {
      return { error: `Stock ${upperSymbol} not found`, symbol: upperSymbol };
    }

    const closes = historicalData.map(d => d.close).filter(Boolean);
    const analysis = closes.length > 0 ? this.analyzeStock(historicalData, closes) : null;

    return {
      ...quoteData,
      symbol: upperSymbol,
      technicalAnalysis: analysis,
      insight: analysis ? this.generateInsight(quoteData, analysis) : 'Insufficient data for analysis',
      entryRecommendation: analysis ? this.generateEntryRecommendation(quoteData, analysis) : null,
      historicalData: historicalData.slice(-30),
    };
  }

  private parseNseQuote(nseData: any, symbol: string): any {
    const price = nseData.priceInfo;
    const info = nseData.info;
    const metadata = nseData.metadata;

    return {
      symbol,
      companyName: info?.companyName || metadata?.companyName || symbol,
      industry: metadata?.industry || info?.industry,
      sector: metadata?.sector || info?.sector,
      lastPrice: price?.lastPrice,
      change: price?.change,
      pChange: price?.pChange,
      open: price?.open,
      intraDayHighLow: price?.intraDayHighLow,
      weekHighLow: price?.weekHighLow,
      previousClose: price?.previousClose,
      totalTradedVolume: price?.totalTradedVolume,
      totalTradedValue: price?.totalTradedValue,
      deliveryQuantity: price?.deliveryQuantity,
      deliveryToTradedQuantity: price?.deliveryToTradedQuantity,
      marketCap: nseData.marketDeptOrderBook?.tradeInfo?.totalMarketCap,
      pe: nseData.metadata?.pdSectorPe,
      pb: nseData.metadata?.pdSectorPb,
      eps: nseData.industryInfo?.basicIndustry,
      faceValue: nseData.securityInfo?.faceValue,
      source: 'NSE',
    };
  }

  private analyzeStock(ohlcv: OHLCV[], closes: number[]): any {
    const ema9 = calculateEMA(closes, 9);
    const ema21 = calculateEMA(closes, 21);
    const ema50 = calculateEMA(closes, 50);
    const ema200 = calculateEMA(closes, 200);
    const rsi = calculateRSI(closes, 14);
    const macd = calculateMACD(closes);
    const bb = calculateBollingerBands(closes, 20);
    const atr = calculateATR(ohlcv, 14);
    const vwap = calculateVWAP(ohlcv.slice(-5));
    const sr = detectSupportsResistances(ohlcv, 10);

    const lastClose = closes[closes.length - 1];
    const lastEma9 = ema9[ema9.length - 1];
    const lastEma21 = ema21[ema21.length - 1];
    const lastEma50 = ema50[ema50.length - 1];
    const lastEma200 = ema200[ema200.length - 1];
    const lastRsi = rsi[rsi.length - 1];
    const lastMacdHist = macd.histogram[macd.histogram.length - 1];
    const lastBbUpper = bb.upper[bb.upper.length - 1];
    const lastBbLower = bb.lower[bb.lower.length - 1];
    const lastBbMiddle = bb.middle[bb.middle.length - 1];
    const lastAtr = atr[atr.length - 1];

    const trend = lastClose > lastEma50 ? (lastClose > lastEma200 ? 'STRONG_BULLISH' : 'BULLISH') :
                  lastClose < lastEma50 ? (lastClose < lastEma200 ? 'STRONG_BEARISH' : 'BEARISH') : 'NEUTRAL';

    const nearestSupport = sr.supports.filter(s => s < lastClose).pop() || null;
    const nearestResistance = sr.resistances.find(r => r > lastClose) || null;

    return {
      currentPrice: lastClose,
      ema: { ema9: lastEma9, ema21: lastEma21, ema50: lastEma50, ema200: lastEma200 },
      rsi: lastRsi,
      macd: {
        value: macd.macd[macd.macd.length - 1],
        signal: macd.signal[macd.signal.length - 1],
        histogram: lastMacdHist,
        crossover: lastMacdHist > 0 ? 'BULLISH' : 'BEARISH',
      },
      bollingerBands: {
        upper: lastBbUpper,
        middle: lastBbMiddle,
        lower: lastBbLower,
        bandwidth: ((lastBbUpper - lastBbLower) / lastBbMiddle * 100).toFixed(2),
        position: lastClose > lastBbUpper ? 'ABOVE_UPPER' : lastClose < lastBbLower ? 'BELOW_LOWER' : 'INSIDE',
      },
      atr: lastAtr,
      vwap,
      trend,
      supports: sr.supports.slice(-3),
      resistances: sr.resistances.slice(0, 3),
      nearestSupport,
      nearestResistance,
      rsiZone: lastRsi > 70 ? 'OVERBOUGHT' : lastRsi < 30 ? 'OVERSOLD' : 'NEUTRAL',
    };
  }

  private generateInsight(quote: any, analysis: any): string {
    const parts: string[] = [];

    parts.push(`${quote.companyName || quote.symbol} is trading at ₹${analysis.currentPrice?.toFixed(2)}`);

    if (analysis.trend === 'STRONG_BULLISH') {
      parts.push('Stock is in a strong uptrend — trading above both EMA50 and EMA200');
    } else if (analysis.trend === 'BULLISH') {
      parts.push('Stock is in a moderate uptrend — above EMA50 but below EMA200');
    } else if (analysis.trend === 'BEARISH') {
      parts.push('Stock is under pressure — below EMA50');
    } else if (analysis.trend === 'STRONG_BEARISH') {
      parts.push('Stock is in a strong downtrend — below both EMA50 and EMA200');
    }

    if (analysis.rsiZone === 'OVERBOUGHT') {
      parts.push(`RSI at ${analysis.rsi?.toFixed(1)} — overbought zone, caution advised`);
    } else if (analysis.rsiZone === 'OVERSOLD') {
      parts.push(`RSI at ${analysis.rsi?.toFixed(1)} — oversold zone, potential bounce candidate`);
    } else {
      parts.push(`RSI at ${analysis.rsi?.toFixed(1)} — neutral zone`);
    }

    if (analysis.macd?.crossover === 'BULLISH') {
      parts.push('MACD histogram is positive — bullish momentum');
    } else {
      parts.push('MACD histogram is negative — bearish momentum');
    }

    if (analysis.nearestSupport) {
      parts.push(`Nearest support at ₹${analysis.nearestSupport.toFixed(2)}`);
    }
    if (analysis.nearestResistance) {
      parts.push(`Nearest resistance at ₹${analysis.nearestResistance.toFixed(2)}`);
    }

    return parts.join('. ');
  }

  private generateEntryRecommendation(quote: any, analysis: any): any {
    const signals: string[] = [];
    let bullishCount = 0;
    let bearishCount = 0;

    if (analysis.trend === 'STRONG_BULLISH' || analysis.trend === 'BULLISH') bullishCount++;
    else bearishCount++;

    if (analysis.rsi < 50) bullishCount++;
    else bearishCount++;

    if (analysis.macd?.crossover === 'BULLISH') bullishCount++;
    else bearishCount++;

    if (analysis.bollingerBands?.position === 'BELOW_LOWER') bullishCount += 2;
    else if (analysis.bollingerBands?.position === 'ABOVE_UPPER') bearishCount += 2;

    const overallSignal = bullishCount > bearishCount ? 'BULLISH' : bullishCount < bearishCount ? 'BEARISH' : 'NEUTRAL';
    const confidence = Math.abs(bullishCount - bearishCount) / (bullishCount + bearishCount) * 100;

    let entryCall: 'ENTRY_CALL' | 'ENTRY_PUT' | 'WAIT' | 'AVOID';
    if (overallSignal === 'BULLISH' && confidence > 30 && analysis.rsiZone !== 'OVERBOUGHT') {
      entryCall = 'ENTRY_CALL';
    } else if (overallSignal === 'BEARISH' && confidence > 30 && analysis.rsiZone !== 'OVERSOLD') {
      entryCall = 'ENTRY_PUT';
    } else if (analysis.rsiZone === 'OVERBOUGHT' || analysis.rsiZone === 'OVERSOLD') {
      entryCall = 'WAIT';
    } else {
      entryCall = 'WAIT';
    }

    return {
      signal: overallSignal,
      entryCall,
      confidence: confidence.toFixed(1) + '%',
      bullishFactors: bullishCount,
      bearishFactors: bearishCount,
      targetPrice: analysis.nearestResistance,
      stopLoss: analysis.nearestSupport,
      riskReward: analysis.nearestResistance && analysis.nearestSupport
        ? ((analysis.nearestResistance - analysis.currentPrice) / (analysis.currentPrice - analysis.nearestSupport)).toFixed(2)
        : null,
      summary: `${entryCall.replace('_', ' ')} — ${overallSignal} with ${confidence.toFixed(0)}% confidence`,
    };
  }

  async getNifty100Stocks(): Promise<any[]> {
    try {
      const data = await this.nseService.getNifty100Stocks();
      if (data?.data) {
        return data.data.map((stock: any) => ({
          symbol: stock.symbol,
          companyName: stock.meta?.companyName || stock.symbol,
          lastPrice: stock.lastPrice,
          change: stock.change,
          pChange: stock.pChange,
          volume: stock.totalTradedVolume,
          open: stock.open,
          dayHigh: stock.dayHigh,
          dayLow: stock.dayLow,
          previousClose: stock.previousClose,
          series: stock.series,
        }));
      }
    } catch (err) {
      this.logger.warn('Failed to get Nifty 100 stocks');
    }
    return [];
  }

  async getMidcapStocks(): Promise<any[]> {
    try {
      const data = await this.nseService.getNiftyMidcap150();
      if (data?.data) {
        return data.data.map((stock: any) => ({
          symbol: stock.symbol,
          companyName: stock.meta?.companyName || stock.symbol,
          lastPrice: stock.lastPrice,
          change: stock.change,
          pChange: stock.pChange,
          volume: stock.totalTradedVolume,
          open: stock.open,
          dayHigh: stock.dayHigh,
          dayLow: stock.dayLow,
          previousClose: stock.previousClose,
        }));
      }
    } catch (err) {
      this.logger.warn('Failed to get Midcap stocks');
    }
    return [];
  }

  async getSmallcapStocks(): Promise<any[]> {
    try {
      const data = await this.nseService.getNiftySmallcap250();
      if (data?.data) {
        return data.data.map((stock: any) => ({
          symbol: stock.symbol,
          companyName: stock.meta?.companyName || stock.symbol,
          lastPrice: stock.lastPrice,
          change: stock.change,
          pChange: stock.pChange,
          volume: stock.totalTradedVolume,
          open: stock.open,
          dayHigh: stock.dayHigh,
          dayLow: stock.dayLow,
          previousClose: stock.previousClose,
        }));
      }
    } catch (err) {
      this.logger.warn('Failed to get Smallcap stocks');
    }
    return [];
  }
}
