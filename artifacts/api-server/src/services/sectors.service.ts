import { NseService } from "./nse.service.js";
import { YahooService } from "./yahoo.service.js";

const SECTOR_INDICES = [
  { name: "NIFTY 50", symbol: "NIFTY 50", category: "Broad Market", nseKey: "NIFTY 50" },
  { name: "Nifty Bank", symbol: "NIFTY BANK", category: "Banking & Finance", nseKey: "NIFTY BANK" },
  { name: "Nifty IT", symbol: "NIFTY IT", category: "Technology", nseKey: "NIFTY IT" },
  { name: "Nifty Auto", symbol: "NIFTY AUTO", category: "Automobile", nseKey: "NIFTY AUTO" },
  { name: "Nifty Pharma", symbol: "NIFTY PHARMA", category: "Pharmaceuticals", nseKey: "NIFTY PHARMA" },
  { name: "Nifty FMCG", symbol: "NIFTY FMCG", category: "FMCG", nseKey: "NIFTY FMCG" },
  { name: "Nifty Metal", symbol: "NIFTY METAL", category: "Metals & Mining", nseKey: "NIFTY METAL" },
  { name: "Nifty Realty", symbol: "NIFTY REALTY", category: "Real Estate", nseKey: "NIFTY REALTY" },
  { name: "Nifty Energy", symbol: "NIFTY ENERGY", category: "Energy & Oil", nseKey: "NIFTY ENERGY" },
  { name: "Nifty Media", symbol: "NIFTY MEDIA", category: "Media & Entertainment", nseKey: "NIFTY MEDIA" },
  { name: "Nifty Financial Services", symbol: "NIFTY FINANCIAL SERVICES", category: "Financial Services", nseKey: "NIFTY FINANCIAL SERVICES" },
  { name: "Nifty PSU Bank", symbol: "NIFTY PSU BANK", category: "PSU Banking", nseKey: "NIFTY PSU BANK" },
  { name: "Nifty Consumer Durables", symbol: "NIFTY CONSUMER DURABLES", category: "Consumer Durables", nseKey: "NIFTY CONSUMER DURABLES" },
  { name: "Nifty Oil & Gas", symbol: "NIFTY OIL AND GAS", category: "Oil & Gas", nseKey: "NIFTY OIL AND GAS" },
  { name: "Nifty Healthcare", symbol: "NIFTY HEALTHCARE INDEX", category: "Healthcare", nseKey: "NIFTY HEALTHCARE INDEX" },
];

export class SectorsService {
  constructor(private nse: NseService, private yahoo: YahooService) {}

  async getAllSectors(): Promise<any[]> {
    try {
      const nseData: any = await this.nse.getSectorIndices();
      if (nseData?.data?.length > 0) return this.parseNseSectors(nseData.data);
    } catch (_) {}
    return this.getDefaultSectors();
  }

  private parseNseSectors(data: any[]): any[] {
    const results: any[] = [];
    for (const sector of SECTOR_INDICES) {
      const found = data.find((d: any) => d.index === sector.nseKey || d.indexSymbol === sector.symbol);
      if (found) {
        const pChange = parseFloat(found.percentChange || found.perChange || "0");
        results.push({
          name: sector.name, symbol: sector.symbol, category: sector.category,
          lastPrice: found.last || found.indexValue || 0, change: found.variation || found.change || 0,
          pChange, open: found.open, high: found.high, low: found.low,
          previousClose: found.previousClose, yearHigh: found.yearHigh, yearLow: found.yearLow,
          advances: found.advances, declines: found.declines,
          momentum: pChange > 3 ? 5 : pChange > 1.5 ? 4 : pChange > 0 ? 3 : pChange > -1.5 ? 2 : 1,
          focus: pChange > 1 ? "BUY" : pChange > -1 ? "HOLD" : "AVOID",
          source: "NSE",
        });
      }
    }
    if (results.length === 0) return this.getDefaultSectors();
    return results.sort((a, b) => b.pChange - a.pChange);
  }

  private getDefaultSectors(): any[] {
    return SECTOR_INDICES.map(s => ({
      name: s.name, symbol: s.symbol, category: s.category,
      lastPrice: 0, change: 0, pChange: 0, momentum: 3, focus: "HOLD", source: "UNAVAILABLE",
    }));
  }

  async getSectorRotation(): Promise<any> {
    const sectors = await this.getAllSectors();
    const sorted = [...sectors].sort((a, b) => b.pChange - a.pChange);
    const advancing = sectors.filter(s => s.pChange > 0).length;
    const declining = sectors.filter(s => s.pChange < 0).length;
    const avgPChange = sectors.reduce((s, sec) => s + (sec.pChange || 0), 0) / sectors.length;
    const phase = avgPChange > 1.5 ? "Bull Run - All sectors rising" :
      avgPChange > 0 ? "Recovery Phase - Select sectors leading" :
      avgPChange > -1.5 ? "Consolidation - Defensive sectors preferred" : "Bear Phase - Risk-off mode";
    const top3Names = sorted.slice(0, 3).map(s => s.name);
    return {
      date: new Date().toISOString().split("T")[0], timestamp: new Date().toISOString(),
      sectors, topPerformers: sorted.slice(0, 5), laggards: sorted.slice(-3),
      currentlyFocused: top3Names,
      whereToBuyNow: sorted.filter(s => s.focus === "BUY").slice(0, 5),
      marketBreadth: {
        advancing, declining, unchanged: sectors.length - advancing - declining, total: sectors.length,
        advanceDeclineRatio: declining === 0 ? advancing : (advancing / declining).toFixed(2),
        breadthScore: ((advancing / sectors.length) * 100).toFixed(1),
      },
      rotationPhase: phase,
      recommendation: `Focus on ${top3Names.join(", ")}. Sector rotation favoring these indices.`,
    };
  }

  async getSectorDetail(symbol: string): Promise<any | null> {
    const sectors = await this.getAllSectors();
    return sectors.find(s => s.symbol === symbol || s.name.toLowerCase() === symbol.toLowerCase()) || null;
  }
}
