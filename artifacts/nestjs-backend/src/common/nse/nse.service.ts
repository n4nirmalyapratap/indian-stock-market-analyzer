import { Injectable, Logger } from '@nestjs/common';
import axios, { AxiosInstance } from 'axios';
import NodeCache from 'node-cache';

@Injectable()
export class NseService {
  private readonly logger = new Logger(NseService.name);
  private readonly cache: NodeCache;
  private readonly client: AxiosInstance;
  private cookies: string = '';
  private cookieExpiry: number = 0;

  constructor() {
    this.cache = new NodeCache({ stdTTL: 300, checkperiod: 60 });
    this.client = axios.create({
      baseURL: 'https://www.nseindia.com',
      timeout: 15000,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://www.nseindia.com',
        'Connection': 'keep-alive',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'X-Requested-With': 'XMLHttpRequest',
      },
    });
  }

  private async refreshCookies(): Promise<void> {
    try {
      const response = await axios.get('https://www.nseindia.com', {
        timeout: 15000,
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
          'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
          'Accept-Language': 'en-US,en;q=0.9',
        },
      });

      const setCookies = response.headers['set-cookie'];
      if (setCookies) {
        this.cookies = setCookies.map((c: string) => c.split(';')[0]).join('; ');
        this.cookieExpiry = Date.now() + 20 * 60 * 1000;
        this.client.defaults.headers['Cookie'] = this.cookies;
        this.logger.log('NSE cookies refreshed successfully');
      }
    } catch (error) {
      this.logger.warn('Failed to refresh NSE cookies, will use Yahoo Finance fallback');
    }
  }

  private async ensureCookies(): Promise<void> {
    if (!this.cookies || Date.now() > this.cookieExpiry) {
      await this.refreshCookies();
    }
  }

  async fetchNse<T>(path: string, cacheKey?: string, ttl?: number): Promise<T | null> {
    const key = cacheKey || path;
    const cached = this.cache.get<T>(key);
    if (cached !== undefined) return cached;

    await this.ensureCookies();

    try {
      const response = await this.client.get<T>(path);
      const data = response.data;
      this.cache.set(key, data, ttl || 300);
      return data;
    } catch (error) {
      this.logger.warn(`NSE fetch failed for ${path}: ${error.message}`);
      return null;
    }
  }

  async getSectorIndices(): Promise<any> {
    return this.fetchNse('/api/allIndices', 'sector-indices', 300);
  }

  async getIndexQuote(indexSymbol: string): Promise<any> {
    return this.fetchNse(`/api/equity-stockIndices?index=${encodeURIComponent(indexSymbol)}`, `index-${indexSymbol}`, 300);
  }

  async getStockQuote(symbol: string): Promise<any> {
    return this.fetchNse(`/api/quote-equity?symbol=${encodeURIComponent(symbol)}`, `quote-${symbol}`, 120);
  }

  async getStockHistory(symbol: string, series: string = 'EQ'): Promise<any> {
    const from = this.getDateString(-90);
    const to = this.getDateString(0);
    return this.fetchNse(
      `/api/historical/cm/equity?symbol=${encodeURIComponent(symbol)}&series=[%22${series}%22]&from=${from}&to=${to}&csv=false`,
      `history-${symbol}`,
      3600,
    );
  }

  async getNifty100Stocks(): Promise<any> {
    return this.fetchNse('/api/equity-stockIndices?index=NIFTY%20100', 'nifty100', 1800);
  }

  async getNiftyMidcap150(): Promise<any> {
    return this.fetchNse('/api/equity-stockIndices?index=NIFTY%20MIDCAP%20150', 'midcap150', 1800);
  }

  async getNiftySmallcap250(): Promise<any> {
    return this.fetchNse('/api/equity-stockIndices?index=NIFTY%20SMALLCAP%20250', 'smallcap250', 1800);
  }

  async getOptionChain(symbol: string): Promise<any> {
    return this.fetchNse(`/api/option-chain-equities?symbol=${encodeURIComponent(symbol)}`, `options-${symbol}`, 300);
  }

  async getFiiDiiData(): Promise<any> {
    return this.fetchNse('/api/fiidiiTradeReact', 'fii-dii', 3600);
  }

  private getDateString(daysOffset: number): string {
    const date = new Date();
    date.setDate(date.getDate() + daysOffset);
    const dd = String(date.getDate()).padStart(2, '0');
    const mm = String(date.getMonth() + 1).padStart(2, '0');
    const yyyy = date.getFullYear();
    return `${dd}-${mm}-${yyyy}`;
  }

  clearCache(key?: string): void {
    if (key) {
      this.cache.del(key);
    } else {
      this.cache.flushAll();
    }
  }
}
