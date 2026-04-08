import { NseService } from "./nse.service.js";
import { YahooService } from "./yahoo.service.js";
import { calculateEMA, calculateRSI, calculateMACD, calculateBollingerBands, calculateATR, detectSR, OHLCV } from "./indicators.js";

export class StocksService {
  constructor(private nse: NseService, private yahoo: YahooService) {}

  async getStockDetails(symbol: string): Promise<any> {
    const upper = symbol.toUpperCase();
    let quoteData: any = null;
    let history: OHLCV[] = [];

    try {
      const nseQuote: any = await this.nse.getStockQuote(upper);
      if (nseQuote?.priceInfo) {
        const p = nseQuote.priceInfo;
        const info = nseQuote.info || nseQuote.metadata || {};
        quoteData = {
          symbol: upper, companyName: info.companyName || upper,
          industry: info.industry, sector: info.sector,
          lastPrice: p.lastPrice, change: p.change, pChange: p.pChange,
          open: p.open, previousClose: p.previousClose,
          volume: p.totalTradedVolume, source: "NSE",
        };
      }
    } catch (_) {}

    if (!quoteData) {
      quoteData = await this.yahoo.getQuote(upper);
    }
    if (!quoteData) return { error: `Stock ${upper} not found`, symbol: upper };

    try {
      const h = await this.yahoo.getHistoricalData(upper, 180);
      if (h.length > 0) history = h;
    } catch (_) {}

    const closes = history.map((d: any) => d.close).filter(Boolean);
    const analysis = closes.length > 20 ? this.analyze(history, closes) : null;

    return {
      ...quoteData, symbol: upper,
      technicalAnalysis: analysis,
      insight: analysis ? this.buildInsight(quoteData, analysis) : "Insufficient historical data",
      entryRecommendation: analysis ? this.buildEntry(quoteData, analysis) : null,
      historicalData: history.slice(-30),
    };
  }

  private analyze(ohlcv: OHLCV[], closes: number[]): any {
    const ema9 = calculateEMA(closes, 9), ema21 = calculateEMA(closes, 21);
    const ema50 = calculateEMA(closes, 50), ema200 = calculateEMA(closes, 200);
    const rsi = calculateRSI(closes, 14);
    const macd = calculateMACD(closes);
    const bb = calculateBollingerBands(closes, 20);
    const atr = calculateATR(ohlcv, 14);
    const sr = detectSR(ohlcv, 10);
    const lc = closes[closes.length - 1];
    const le9 = ema9[ema9.length - 1], le21 = ema21[ema21.length - 1];
    const le50 = ema50[ema50.length - 1], le200 = ema200[ema200.length - 1];
    const lr = rsi[rsi.length - 1];
    const lh = macd.histogram[macd.histogram.length - 1];
    const lbu = bb.upper[bb.upper.length - 1], lbl = bb.lower[bb.lower.length - 1];
    const lbm = bb.middle[bb.middle.length - 1];
    const trend = lc > le50 ? (lc > le200 ? "STRONG_BULLISH" : "BULLISH") : lc < le50 ? (lc < le200 ? "STRONG_BEARISH" : "BEARISH") : "NEUTRAL";
    const nearestSupport = sr.supports.filter(s => s < lc).pop() || null;
    const nearestResistance = sr.resistances.find(r => r > lc) || null;
    return {
      currentPrice: lc, ema: { ema9: le9, ema21: le21, ema50: le50, ema200: le200 },
      rsi: lr, rsiZone: lr > 70 ? "OVERBOUGHT" : lr < 30 ? "OVERSOLD" : "NEUTRAL",
      macd: { value: macd.macd[macd.macd.length - 1], signal: macd.signal[macd.signal.length - 1], histogram: lh, crossover: lh > 0 ? "BULLISH" : "BEARISH" },
      bollingerBands: {
        upper: lbu, middle: lbm, lower: lbl,
        bandwidth: lbm ? ((lbu - lbl) / lbm * 100).toFixed(2) : "0",
        position: lc > lbu ? "ABOVE_UPPER" : lc < lbl ? "BELOW_LOWER" : "INSIDE",
      },
      atr: atr[atr.length - 1], trend,
      supports: sr.supports.slice(-3), resistances: sr.resistances.slice(0, 3),
      nearestSupport, nearestResistance,
    };
  }

  private buildInsight(quote: any, analysis: any): string {
    const parts: string[] = [];
    parts.push(`${quote.companyName || quote.symbol} at ₹${analysis.currentPrice?.toFixed(2)}`);
    if (analysis.trend === "STRONG_BULLISH") parts.push("Strong uptrend — above EMA50 and EMA200");
    else if (analysis.trend === "BULLISH") parts.push("Moderate uptrend — above EMA50");
    else if (analysis.trend === "BEARISH") parts.push("Downtrend — below EMA50");
    else if (analysis.trend === "STRONG_BEARISH") parts.push("Strong downtrend — below EMA50 and EMA200");
    parts.push(`RSI at ${analysis.rsi?.toFixed(1)} — ${analysis.rsiZone}`);
    parts.push(`MACD ${analysis.macd?.crossover?.toLowerCase()} momentum`);
    if (analysis.nearestSupport) parts.push(`Support at ₹${analysis.nearestSupport.toFixed(2)}`);
    if (analysis.nearestResistance) parts.push(`Resistance at ₹${analysis.nearestResistance.toFixed(2)}`);
    return parts.join(". ");
  }

  private buildEntry(quote: any, analysis: any): any {
    let bull = 0, bear = 0;
    if (analysis.trend?.includes("BULL")) bull++; else bear++;
    if (analysis.rsi < 50) bull++; else bear++;
    if (analysis.macd?.crossover === "BULLISH") bull++; else bear++;
    if (analysis.bollingerBands?.position === "BELOW_LOWER") bull += 2;
    else if (analysis.bollingerBands?.position === "ABOVE_UPPER") bear += 2;
    const signal = bull > bear ? "BULLISH" : bull < bear ? "BEARISH" : "NEUTRAL";
    const confidence = Math.abs(bull - bear) / (bull + bear) * 100;
    let entryCall = "WAIT";
    if (signal === "BULLISH" && confidence > 30 && analysis.rsiZone !== "OVERBOUGHT") entryCall = "ENTRY_CALL";
    else if (signal === "BEARISH" && confidence > 30 && analysis.rsiZone !== "OVERSOLD") entryCall = "ENTRY_PUT";
    const rr = analysis.nearestResistance && analysis.nearestSupport
      ? ((analysis.nearestResistance - analysis.currentPrice) / (analysis.currentPrice - analysis.nearestSupport)).toFixed(2)
      : null;
    return {
      signal, entryCall, confidence: confidence.toFixed(1) + "%",
      bullishFactors: bull, bearishFactors: bear,
      targetPrice: analysis.nearestResistance, stopLoss: analysis.nearestSupport, riskReward: rr,
      summary: `${entryCall.replace("_", " ")} — ${signal} with ${confidence.toFixed(0)}% confidence`,
    };
  }

  async getNifty100Stocks(): Promise<any[]> {
    const data: any = await this.nse.getNifty100();
    if (data?.data) {
      return data.data.map((s: any) => ({
        symbol: s.symbol, companyName: s.meta?.companyName || s.symbol,
        lastPrice: s.lastPrice, change: s.change, pChange: s.pChange,
        volume: s.totalTradedVolume, open: s.open, dayHigh: s.dayHigh,
        dayLow: s.dayLow, previousClose: s.previousClose,
      }));
    }
    return [];
  }

  async getMidcapStocks(): Promise<any[]> {
    const data: any = await this.nse.getNiftyMidcap150();
    if (data?.data) {
      return data.data.map((s: any) => ({
        symbol: s.symbol, companyName: s.meta?.companyName || s.symbol,
        lastPrice: s.lastPrice, change: s.change, pChange: s.pChange,
        volume: s.totalTradedVolume,
      }));
    }
    return [];
  }

  async getSmallcapStocks(): Promise<any[]> {
    const data: any = await this.nse.getNiftySmallcap250();
    if (data?.data) {
      return data.data.map((s: any) => ({
        symbol: s.symbol, companyName: s.meta?.companyName || s.symbol,
        lastPrice: s.lastPrice, change: s.change, pChange: s.pChange,
        volume: s.totalTradedVolume,
      }));
    }
    return [];
  }
}
