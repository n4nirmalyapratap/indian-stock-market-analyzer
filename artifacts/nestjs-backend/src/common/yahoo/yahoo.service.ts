import { Injectable, Logger } from '@nestjs/common';
import axios from 'axios';
import NodeCache from 'node-cache';

@Injectable()
export class YahooService {
  private readonly logger = new Logger(YahooService.name);
  private readonly cache: NodeCache;

  constructor() {
    this.cache = new NodeCache({ stdTTL: 300, checkperiod: 60 });
  }

  private toYahooSymbol(nseSymbol: string): string {
    return `${nseSymbol}.NS`;
  }

  async getQuote(symbol: string): Promise<any> {
    const cacheKey = `yahoo-quote-${symbol}`;
    const cached = this.cache.get(cacheKey);
    if (cached) return cached;

    try {
      const yahooSymbol = this.toYahooSymbol(symbol);
      const url = `https://query1.finance.yahoo.com/v8/finance/chart/${yahooSymbol}?interval=1d&range=1d`;
      const response = await axios.get(url, {
        headers: { 'User-Agent': 'Mozilla/5.0' },
        timeout: 10000,
      });

      const result = response.data?.chart?.result?.[0];
      if (!result) return null;

      const meta = result.meta;
      const data = {
        symbol: meta.symbol,
        companyName: meta.longName || symbol,
        lastPrice: meta.regularMarketPrice,
        change: meta.regularMarketPrice - meta.chartPreviousClose,
        pChange: ((meta.regularMarketPrice - meta.chartPreviousClose) / meta.chartPreviousClose) * 100,
        open: meta.regularMarketOpen,
        dayHigh: meta.regularMarketDayHigh,
        dayLow: meta.regularMarketDayLow,
        previousClose: meta.chartPreviousClose,
        volume: meta.regularMarketVolume,
        totalTradedValue: meta.regularMarketVolume * meta.regularMarketPrice,
        fiftyTwoWeekHigh: meta['52WeekHigh'],
        fiftyTwoWeekLow: meta['52WeekLow'],
        marketCap: meta.marketCap,
        currency: meta.currency,
      };

      this.cache.set(cacheKey, data, 300);
      return data;
    } catch (error) {
      this.logger.warn(`Yahoo Finance quote failed for ${symbol}: ${error.message}`);
      return null;
    }
  }

  async getHistoricalData(symbol: string, days: number = 90): Promise<any[]> {
    const cacheKey = `yahoo-history-${symbol}-${days}`;
    const cached = this.cache.get<any[]>(cacheKey);
    if (cached) return cached;

    try {
      const yahooSymbol = this.toYahooSymbol(symbol);
      const range = days <= 30 ? '1mo' : days <= 90 ? '3mo' : days <= 180 ? '6mo' : '1y';
      const url = `https://query1.finance.yahoo.com/v8/finance/chart/${yahooSymbol}?interval=1d&range=${range}`;

      const response = await axios.get(url, {
        headers: { 'User-Agent': 'Mozilla/5.0' },
        timeout: 10000,
      });

      const result = response.data?.chart?.result?.[0];
      if (!result) return [];

      const timestamps = result.timestamp || [];
      const quotes = result.indicators?.quote?.[0] || {};
      const adjClose = result.indicators?.adjclose?.[0]?.adjclose || [];

      const historicalData = timestamps.map((ts: number, idx: number) => ({
        date: new Date(ts * 1000).toISOString().split('T')[0],
        open: quotes.open?.[idx],
        high: quotes.high?.[idx],
        low: quotes.low?.[idx],
        close: quotes.close?.[idx],
        adjClose: adjClose[idx],
        volume: quotes.volume?.[idx],
      })).filter(d => d.close !== null && d.close !== undefined);

      this.cache.set(cacheKey, historicalData, 3600);
      return historicalData;
    } catch (error) {
      this.logger.warn(`Yahoo Finance history failed for ${symbol}: ${error.message}`);
      return [];
    }
  }

  async getMultipleQuotes(symbols: string[]): Promise<Record<string, any>> {
    const yahooSymbols = symbols.map(s => this.toYahooSymbol(s)).join(',');
    try {
      const url = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${yahooSymbols}`;
      const response = await axios.get(url, {
        headers: { 'User-Agent': 'Mozilla/5.0' },
        timeout: 15000,
      });

      const result: Record<string, any> = {};
      const quotes = response.data?.quoteResponse?.result || [];
      quotes.forEach((q: any) => {
        const nseSymbol = q.symbol.replace('.NS', '');
        result[nseSymbol] = {
          symbol: nseSymbol,
          companyName: q.longName || q.shortName || nseSymbol,
          lastPrice: q.regularMarketPrice,
          change: q.regularMarketChange,
          pChange: q.regularMarketChangePercent,
          open: q.regularMarketOpen,
          dayHigh: q.regularMarketDayHigh,
          dayLow: q.regularMarketDayLow,
          previousClose: q.regularMarketPreviousClose,
          volume: q.regularMarketVolume,
          marketCap: q.marketCap,
          fiftyTwoWeekHigh: q.fiftyTwoWeekHigh,
          fiftyTwoWeekLow: q.fiftyTwoWeekLow,
        };
      });
      return result;
    } catch (error) {
      this.logger.warn(`Yahoo bulk quotes failed: ${error.message}`);
      return {};
    }
  }

  async getIndexData(indexSymbol: string): Promise<any> {
    const yahooIndexMap: Record<string, string> = {
      'NIFTY 50': '^NSEI',
      'NIFTY BANK': '^NSEBANK',
      'NIFTY IT': 'NIFTYIT.NS',
      'NIFTY AUTO': 'NIFTYAUTO.NS',
      'NIFTY PHARMA': 'NIFTYPHARMA.NS',
      'NIFTY FMCG': 'NIFTYFMCG.NS',
      'NIFTY METAL': 'NIFTYMETAL.NS',
      'NIFTY REALTY': 'NIFTYREALTY.NS',
      'NIFTY ENERGY': 'NIFTYENERGY.NS',
      'NIFTY MEDIA': 'NIFTYMEDIA.NS',
    };

    const yahooSymbol = yahooIndexMap[indexSymbol] || `^${indexSymbol.replace(/\s+/g, '')}`;
    try {
      const url = `https://query1.finance.yahoo.com/v8/finance/chart/${yahooSymbol}?interval=1d&range=1mo`;
      const response = await axios.get(url, {
        headers: { 'User-Agent': 'Mozilla/5.0' },
        timeout: 10000,
      });
      return response.data?.chart?.result?.[0]?.meta || null;
    } catch (error) {
      this.logger.warn(`Yahoo index data failed for ${indexSymbol}: ${error.message}`);
      return null;
    }
  }
}
