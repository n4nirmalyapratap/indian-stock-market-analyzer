import { Injectable, Logger } from '@nestjs/common';
import { NseService } from '../../common/nse/nse.service';
import { YahooService } from '../../common/yahoo/yahoo.service';
import { calculateEMA, calculateRSI } from '../../common/utils/indicators.util';

const SECTOR_INDICES = [
  { name: 'NIFTY 50', symbol: 'NIFTY 50', category: 'Broad Market', nseKey: 'NIFTY 50' },
  { name: 'Nifty Bank', symbol: 'NIFTY BANK', category: 'Banking & Finance', nseKey: 'NIFTY BANK' },
  { name: 'Nifty IT', symbol: 'NIFTY IT', category: 'Technology', nseKey: 'NIFTY IT' },
  { name: 'Nifty Auto', symbol: 'NIFTY AUTO', category: 'Automobile', nseKey: 'NIFTY AUTO' },
  { name: 'Nifty Pharma', symbol: 'NIFTY PHARMA', category: 'Pharmaceuticals', nseKey: 'NIFTY PHARMA' },
  { name: 'Nifty FMCG', symbol: 'NIFTY FMCG', category: 'FMCG', nseKey: 'NIFTY FMCG' },
  { name: 'Nifty Metal', symbol: 'NIFTY METAL', category: 'Metals & Mining', nseKey: 'NIFTY METAL' },
  { name: 'Nifty Realty', symbol: 'NIFTY REALTY', category: 'Real Estate', nseKey: 'NIFTY REALTY' },
  { name: 'Nifty Energy', symbol: 'NIFTY ENERGY', category: 'Energy & Oil', nseKey: 'NIFTY ENERGY' },
  { name: 'Nifty Media', symbol: 'NIFTY MEDIA', category: 'Media & Entertainment', nseKey: 'NIFTY MEDIA' },
  { name: 'Nifty Financial Services', symbol: 'NIFTY FINANCIAL SERVICES', category: 'Financial Services', nseKey: 'NIFTY FINANCIAL SERVICES' },
  { name: 'Nifty PSU Bank', symbol: 'NIFTY PSU BANK', category: 'PSU Banking', nseKey: 'NIFTY PSU BANK' },
  { name: 'Nifty Consumer Durables', symbol: 'NIFTY CONSUMER DURABLES', category: 'Consumer Durables', nseKey: 'NIFTY CONSUMER DURABLES' },
  { name: 'Nifty Oil & Gas', symbol: 'NIFTY OIL AND GAS', category: 'Oil & Gas', nseKey: 'NIFTY OIL AND GAS' },
  { name: 'Nifty Healthcare', symbol: 'NIFTY HEALTHCARE INDEX', category: 'Healthcare', nseKey: 'NIFTY HEALTHCARE INDEX' },
];

@Injectable()
export class SectorsService {
  private readonly logger = new Logger(SectorsService.name);

  constructor(
    private readonly nseService: NseService,
    private readonly yahooService: YahooService,
  ) {}

  async getAllSectors(): Promise<any[]> {
    try {
      const nseData = await this.nseService.getSectorIndices();
      if (nseData && nseData.data) {
        return await this.parseNseSectorData(nseData.data);
      }
    } catch (err) {
      this.logger.warn('NSE sector data failed, using fallback');
    }
    return this.getFallbackSectorData();
  }

  private async parseNseSectorData(data: any[]): Promise<any[]> {
    const sectorData: any[] = [];
    SECTOR_INDICES.forEach(sector => {
      const found = data.find(d => d.index === sector.nseKey || d.indexSymbol === sector.symbol);
      if (found) {
        sectorData.push({
          name: sector.name,
          symbol: sector.symbol,
          category: sector.category,
          lastPrice: found.last || found.indexValue,
          change: found.variation || found.change,
          pChange: found.percentChange || found.perChange,
          open: found.open,
          high: found.high,
          low: found.low,
          previousClose: found.previousClose,
          yearHigh: found.yearHigh,
          yearLow: found.yearLow,
          pe: found.pe,
          pb: found.pb,
          divYield: found.divYield,
          advances: found.advances,
          declines: found.declines,
          unchanged: found.unchanged,
          momentum: this.calculateMomentumScore(found.percentChange || found.perChange),
          focus: this.determineFocus(found.percentChange || found.perChange),
          source: 'NSE',
        });
      }
    });

    if (sectorData.length === 0) return this.getFallbackSectorData();
    return sectorData.sort((a, b) => b.pChange - a.pChange);
  }

  private calculateMomentumScore(pChange: number): number {
    if (pChange > 3) return 5;
    if (pChange > 1.5) return 4;
    if (pChange > 0) return 3;
    if (pChange > -1.5) return 2;
    return 1;
  }

  private determineFocus(pChange: number): 'BUY' | 'HOLD' | 'AVOID' {
    if (pChange > 1) return 'BUY';
    if (pChange > -1) return 'HOLD';
    return 'AVOID';
  }

  private async getFallbackSectorData(): Promise<any[]> {
    const yahooIndexMap: Record<string, string> = {
      'NIFTY BANK': '^NSEBANK',
      'NIFTY 50': '^NSEI',
    };

    const results: any[] = SECTOR_INDICES.map(sector => ({
      name: sector.name,
      symbol: sector.symbol,
      category: sector.category,
      lastPrice: 0,
      change: 0,
      pChange: 0,
      momentum: 3,
      focus: 'HOLD' as const,
      source: 'UNAVAILABLE',
    }));

    return results;
  }

  async getSectorRotation(): Promise<any> {
    const sectors = await this.getAllSectors();
    const topSectors = sectors.filter(s => s.pChange > 0).slice(0, 5);
    const bottomSectors = sectors.filter(s => s.pChange < 0).slice(-5);

    const currentlyFocused = sectors
      .sort((a, b) => b.pChange - a.pChange)
      .slice(0, 3)
      .map(s => s.name);

    const whereToBuyNow = sectors
      .filter(s => s.focus === 'BUY')
      .sort((a, b) => b.momentum - a.momentum)
      .slice(0, 5);

    const marketBreadth = this.calculateMarketBreadth(sectors);

    return {
      date: new Date().toISOString().split('T')[0],
      timestamp: new Date().toISOString(),
      sectors,
      topPerformers: topSectors,
      laggards: bottomSectors,
      currentlyFocused,
      whereToBuyNow,
      marketBreadth,
      rotationPhase: this.determineRotationPhase(sectors),
      recommendation: this.generateSectorRecommendation(sectors),
    };
  }

  private calculateMarketBreadth(sectors: any[]): any {
    const advancing = sectors.filter(s => s.pChange > 0).length;
    const declining = sectors.filter(s => s.pChange < 0).length;
    const unchanged = sectors.filter(s => s.pChange === 0).length;
    const total = sectors.length;

    return {
      advancing,
      declining,
      unchanged,
      total,
      advanceDeclineRatio: declining === 0 ? advancing : (advancing / declining).toFixed(2),
      breadthScore: ((advancing / total) * 100).toFixed(1),
    };
  }

  private determineRotationPhase(sectors: any[]): string {
    const avgPChange = sectors.reduce((s, sec) => s + (sec.pChange || 0), 0) / sectors.length;
    const topSector = sectors.sort((a, b) => b.pChange - a.pChange)[0];

    if (avgPChange > 1.5) return 'Bull Run - All sectors rising';
    if (avgPChange > 0) return 'Recovery Phase - Select sectors leading';
    if (avgPChange > -1.5) return 'Consolidation - Defensive sectors preferred';
    return 'Bear Phase - Risk-off mode';
  }

  private generateSectorRecommendation(sectors: any[]): string {
    const topSectors = sectors.sort((a, b) => b.pChange - a.pChange).slice(0, 3);
    const names = topSectors.map(s => s.name).join(', ');
    const avgChange = (topSectors.reduce((s, sec) => s + sec.pChange, 0) / topSectors.length).toFixed(2);
    return `Focus on ${names}. Average gain of ${avgChange}% today. Sector rotation favoring these indices.`;
  }

  async getSectorDetail(symbol: string): Promise<any> {
    const sectors = await this.getAllSectors();
    return sectors.find(s => s.symbol === symbol || s.name.toLowerCase() === symbol.toLowerCase()) || null;
  }
}
