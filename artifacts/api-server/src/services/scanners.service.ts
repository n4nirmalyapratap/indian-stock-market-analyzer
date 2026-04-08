import { YahooService } from "./yahoo.service.js";
import { NseService } from "./nse.service.js";
import {
  calculateEMA, calculateSMA, calculateRSI,
  calculateMACD, calculateBollingerBands, calculateATR, OHLCV,
} from "./indicators.js";
import { buildUniverse } from "../lib/universe.js";

// ─── Schema ─────────────────────────────────────────────────────────────────

export type IndicatorName =
  | "CLOSE" | "OPEN" | "HIGH" | "LOW" | "PREV_CLOSE"
  | "CHANGE_PCT" | "VOLUME" | "AVG_VOLUME" | "VOLUME_RATIO"
  | "EMA" | "SMA" | "RSI"
  | "MACD" | "MACD_SIGNAL" | "MACD_HIST"
  | "BB_UPPER" | "BB_MID" | "BB_LOWER"
  | "ATR"
  | "HIGH_52W" | "LOW_52W" | "PCT_52W_HIGH" | "PCT_52W_LOW"
  | "NUMBER";

export type Operator = "gt" | "gte" | "lt" | "lte" | "eq" | "crosses_above" | "crosses_below";

export interface ConditionSide {
  type: "indicator" | "number";
  indicator?: IndicatorName;
  period?: number;
  value?: number;
}

export interface Condition {
  id: string;
  left: ConditionSide;
  operator: Operator;
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

// Stock universe is centralised in lib/universe.ts

// ─── Indicator Computation ───────────────────────────────────────────────────

function computeValue(ohlcv: OHLCV[], side: ConditionSide, shift = 0): number | null {
  if (side.type === "number") return side.value ?? null;

  // For shifted (previous) values, work on a truncated slice
  const data = shift > 0 ? ohlcv.slice(0, ohlcv.length - shift) : ohlcv;
  if (data.length < 2) return null;

  const closes  = data.map(d => d.close);
  const n       = data.length;

  switch (side.indicator) {
    case "CLOSE":       return closes[n - 1];
    case "OPEN":        return data[n - 1].open;
    case "HIGH":        return data[n - 1].high;
    case "LOW":         return data[n - 1].low;
    case "PREV_CLOSE":  return closes[n - 2] ?? null;
    case "CHANGE_PCT":  return closes[n - 2] ? ((closes[n - 1] - closes[n - 2]) / closes[n - 2]) * 100 : null;
    case "VOLUME":      return data[n - 1].volume;
    case "AVG_VOLUME": {
      const p = side.period || 20;
      const slice = data.slice(-p);
      return slice.reduce((a, d) => a + d.volume, 0) / slice.length;
    }
    case "VOLUME_RATIO": {
      const avgVol = data.slice(-20).reduce((a, d) => a + d.volume, 0) / Math.min(20, data.length);
      return avgVol ? (data[n - 1].volume / avgVol) * 100 : null;
    }
    case "EMA": {
      const arr = calculateEMA(closes, side.period || 20);
      return arr.length ? arr[arr.length - 1] : null;
    }
    case "SMA": {
      const arr = calculateSMA(closes, side.period || 20);
      return arr.length ? arr[arr.length - 1] : null;
    }
    case "RSI": {
      const arr = calculateRSI(closes, side.period || 14);
      return arr.length ? arr[arr.length - 1] : null;
    }
    case "MACD": {
      const m = calculateMACD(closes);
      return m.macd.length ? m.macd[m.macd.length - 1] : null;
    }
    case "MACD_SIGNAL": {
      const m = calculateMACD(closes);
      return m.signal.length ? m.signal[m.signal.length - 1] : null;
    }
    case "MACD_HIST": {
      const m = calculateMACD(closes);
      return m.histogram.length ? m.histogram[m.histogram.length - 1] : null;
    }
    case "BB_UPPER": {
      const bb = calculateBollingerBands(closes, side.period || 20);
      return bb.upper.length ? bb.upper[bb.upper.length - 1] : null;
    }
    case "BB_MID": {
      const bb = calculateBollingerBands(closes, side.period || 20);
      return bb.middle.length ? bb.middle[bb.middle.length - 1] : null;
    }
    case "BB_LOWER": {
      const bb = calculateBollingerBands(closes, side.period || 20);
      return bb.lower.length ? bb.lower[bb.lower.length - 1] : null;
    }
    case "ATR": {
      const arr = calculateATR(data, side.period || 14);
      return arr.length ? arr[arr.length - 1] : null;
    }
    case "HIGH_52W":     return Math.max(...closes.slice(-252));
    case "LOW_52W":      return Math.min(...closes.slice(-252));
    case "PCT_52W_HIGH": {
      const h = Math.max(...closes.slice(-252));
      return ((closes[n - 1] - h) / h) * 100;
    }
    case "PCT_52W_LOW": {
      const l = Math.min(...closes.slice(-252));
      return ((closes[n - 1] - l) / l) * 100;
    }
    default: return null;
  }
}

function compare(lv: number, op: Operator, rv: number): boolean {
  switch (op) {
    case "gt":  return lv > rv;
    case "gte": return lv >= rv;
    case "lt":  return lv < rv;
    case "lte": return lv <= rv;
    case "eq":  return Math.abs(lv - rv) / (Math.abs(rv) || 1) < 0.001;
    default:    return false;
  }
}

function evalCondition(ohlcv: OHLCV[], c: Condition): { met: boolean; desc: string } {
  const lv  = computeValue(ohlcv, c.left);
  const rv  = computeValue(ohlcv, c.right);

  if (lv === null || rv === null) return { met: false, desc: "Insufficient data" };

  function sideLabel(s: ConditionSide) {
    if (s.type === "number") return `${s.value}`;
    const period = s.period ? `(${s.period})` : "";
    return `${s.indicator}${period}`;
  }

  const ll = sideLabel(c.left),  rl = sideLabel(c.right);
  const fmt = (v: number) => Math.abs(v) < 1 ? v.toFixed(4) : v.toFixed(2);

  if (c.operator === "crosses_above" || c.operator === "crosses_below") {
    const lvPrev = computeValue(ohlcv, c.left,  1);
    const rvPrev = computeValue(ohlcv, c.right, 1);
    if (lvPrev === null || rvPrev === null) return { met: false, desc: "Insufficient data for crossover" };
    const met = c.operator === "crosses_above"
      ? lvPrev <= rvPrev && lv > rv
      : lvPrev >= rvPrev && lv < rv;
    const dir = c.operator === "crosses_above" ? "crossed above" : "crossed below";
    return { met, desc: `${ll} ${dir} ${rl} (${fmt(lv)} vs ${fmt(rv)})` };
  }

  const opSymbols: Record<Operator, string> = { gt: ">", gte: "≥", lt: "<", lte: "≤", eq: "=", crosses_above: "↗", crosses_below: "↘" };
  const met = compare(lv, c.operator, rv);
  return { met, desc: `${ll} ${opSymbols[c.operator]} ${rl} (${fmt(lv)} vs ${fmt(rv)})` };
}

// ─── Default Scanners ────────────────────────────────────────────────────────

function cid() { return Math.random().toString(36).slice(2, 9); }

const DEFAULT_SCANNERS: Omit<Scanner, "id" | "createdAt" | "updatedAt">[] = [
  {
    name: "EMA Golden Cross (20/50)",
    description: "EMA20 just crossed above EMA50 — classic medium-term buy signal",
    universe: ["NIFTY100", "MIDCAP"],
    logic: "AND",
    conditions: [
      { id: cid(), left: { type: "indicator", indicator: "EMA", period: 20 }, operator: "crosses_above", right: { type: "indicator", indicator: "EMA", period: 50 } },
      { id: cid(), left: { type: "indicator", indicator: "RSI", period: 14 }, operator: "gt",            right: { type: "number", value: 45 } },
    ],
  },
  {
    name: "RSI Oversold + EMA50 Support",
    description: "RSI below 35 while price is above EMA50 — dip buy setup",
    universe: ["NIFTY100", "MIDCAP", "SMALLCAP"],
    logic: "AND",
    conditions: [
      { id: cid(), left: { type: "indicator", indicator: "RSI",   period: 14 }, operator: "lt",  right: { type: "number", value: 35 } },
      { id: cid(), left: { type: "indicator", indicator: "CLOSE"              }, operator: "gt",  right: { type: "indicator", indicator: "EMA", period: 50 } },
    ],
  },
  {
    name: "Momentum Breakout",
    description: "Price above EMA200, RSI 55-70, volume spike ≥150%",
    universe: ["NIFTY100"],
    logic: "AND",
    conditions: [
      { id: cid(), left: { type: "indicator", indicator: "CLOSE"              }, operator: "gt",  right: { type: "indicator", indicator: "EMA", period: 200 } },
      { id: cid(), left: { type: "indicator", indicator: "RSI",   period: 14 }, operator: "gte", right: { type: "number", value: 55 } },
      { id: cid(), left: { type: "indicator", indicator: "RSI",   period: 14 }, operator: "lte", right: { type: "number", value: 72 } },
      { id: cid(), left: { type: "indicator", indicator: "VOLUME_RATIO"       }, operator: "gte", right: { type: "number", value: 150 } },
    ],
  },
  {
    name: "Near 52-Week High (within 5%)",
    description: "Price within 5% of 52-week high — momentum continuation",
    universe: ["NIFTY100", "MIDCAP"],
    logic: "AND",
    conditions: [
      { id: cid(), left: { type: "indicator", indicator: "PCT_52W_HIGH" }, operator: "gte", right: { type: "number", value: -5 } },
      { id: cid(), left: { type: "indicator", indicator: "CLOSE"        }, operator: "gt",  right: { type: "indicator", indicator: "EMA", period: 50 } },
    ],
  },
  {
    name: "Bollinger Band Lower Bounce",
    description: "Price near/below BB lower, RSI oversold — mean reversion buy",
    universe: ["NIFTY100", "MIDCAP", "SMALLCAP"],
    logic: "AND",
    conditions: [
      { id: cid(), left: { type: "indicator", indicator: "CLOSE"               }, operator: "lte", right: { type: "indicator", indicator: "BB_LOWER", period: 20 } },
      { id: cid(), left: { type: "indicator", indicator: "RSI",    period: 14  }, operator: "lt",  right: { type: "number", value: 40 } },
    ],
  },
  {
    name: "MACD Bullish Crossover",
    description: "MACD line just crossed above signal line — fresh buy signal",
    universe: ["NIFTY100", "MIDCAP"],
    logic: "AND",
    conditions: [
      { id: cid(), left: { type: "indicator", indicator: "MACD" }, operator: "crosses_above", right: { type: "indicator", indicator: "MACD_SIGNAL" } },
    ],
  },
  {
    name: "Superb Momentum (All EMAs aligned)",
    description: "Price > EMA9 > EMA20 > EMA50 > EMA200 — textbook bull trend",
    universe: ["NIFTY100"],
    logic: "AND",
    conditions: [
      { id: cid(), left: { type: "indicator", indicator: "CLOSE"            }, operator: "gt", right: { type: "indicator", indicator: "EMA", period: 9   } },
      { id: cid(), left: { type: "indicator", indicator: "EMA", period: 9   }, operator: "gt", right: { type: "indicator", indicator: "EMA", period: 20  } },
      { id: cid(), left: { type: "indicator", indicator: "EMA", period: 20  }, operator: "gt", right: { type: "indicator", indicator: "EMA", period: 50  } },
      { id: cid(), left: { type: "indicator", indicator: "EMA", period: 50  }, operator: "gt", right: { type: "indicator", indicator: "EMA", period: 200 } },
    ],
  },
  {
    name: "Volume Spike Breakout",
    description: "Volume ≥ 300% of 20-day average on a green candle",
    universe: ["NIFTY100", "MIDCAP", "SMALLCAP"],
    logic: "AND",
    conditions: [
      { id: cid(), left: { type: "indicator", indicator: "VOLUME_RATIO" }, operator: "gte", right: { type: "number", value: 300 } },
      { id: cid(), left: { type: "indicator", indicator: "CHANGE_PCT"   }, operator: "gt",  right: { type: "number", value: 0   } },
    ],
  },
];

// ─── Storage ─────────────────────────────────────────────────────────────────

let idCounter = 1;
const scanners: Map<string, Scanner> = new Map();

function initDefaults() {
  if (scanners.size > 0) return;
  for (const d of DEFAULT_SCANNERS) {
    const id = `scanner-${idCounter++}`;
    scanners.set(id, { ...d, id, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() });
  }
}

// ─── Service ─────────────────────────────────────────────────────────────────

export class ScannersService {
  constructor(private yahoo: YahooService, private nse: NseService) {
    initDefaults();
  }

  getAllScanners(): Scanner[] {
    return Array.from(scanners.values()).sort(
      (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
    );
  }

  getScannerById(id: string): Scanner | null {
    return scanners.get(id) ?? null;
  }

  createScanner(data: any): Scanner {
    const id = `scanner-${idCounter++}`;
    const s: Scanner = {
      id,
      name:        data.name        || "Untitled Scanner",
      description: data.description || "",
      universe:    data.universe    || ["NIFTY100"],
      logic:       data.logic       || "AND",
      conditions:  (data.conditions || []).map((c: any) => ({ ...c, id: c.id || cid() })),
      createdAt:   new Date().toISOString(),
      updatedAt:   new Date().toISOString(),
    };
    scanners.set(id, s);
    return s;
  }

  updateScanner(id: string, data: any): Scanner | null {
    const existing = scanners.get(id);
    if (!existing) return null;
    const updated: Scanner = {
      ...existing,
      ...data,
      id,
      conditions: (data.conditions || existing.conditions).map((c: any) => ({ ...c, id: c.id || cid() })),
      updatedAt: new Date().toISOString(),
    };
    scanners.set(id, updated);
    return updated;
  }

  deleteScanner(id: string): boolean {
    return scanners.delete(id);
  }

  async runScanner(id: string): Promise<any> {
    const scanner = scanners.get(id);
    if (!scanner) return { error: "Scanner not found" };

    const uniq = buildUniverse(scanner.universe);

    const results: any[] = [];
    for (const sym of uniq) {
      try {
        const h = await this.yahoo.getHistoricalData(sym, 90);
        if (h.length < 30) continue;

        const closes  = h.map((d: any) => d.close).filter(Boolean);
        const lc      = closes[closes.length - 1];
        const pc      = closes[closes.length - 2];
        const change  = lc - pc;
        const pChange = (change / pc) * 100;

        const condResults = scanner.conditions.map(c => evalCondition(h, c));
        const metCount    = condResults.filter(r => r.met).length;
        const allMet      = scanner.logic === "AND"
          ? metCount === scanner.conditions.length
          : metCount > 0;

        if (allMet) {
          results.push({
            symbol:            sym,
            lastPrice:         lc,
            change:            parseFloat(change.toFixed(2)),
            pChange:           parseFloat(pChange.toFixed(2)),
            volume:            h[h.length - 1]?.volume,
            matchedConditions: condResults.filter(r => r.met).map(r => r.desc),
            failedConditions:  condResults.filter(r => !r.met).map(r => r.desc),
            conditionsMatched: metCount,
            totalConditions:   scanner.conditions.length,
            score:             Math.round((metCount / scanner.conditions.length) * 100),
          });
        }
        await new Promise(r => setTimeout(r, 350));
      } catch (_) {}
    }

    results.sort((a, b) => b.score - a.score);

    // Update last run info
    const updated = { ...scanner, lastRunAt: new Date().toISOString(), lastResultCount: results.length };
    scanners.set(id, updated);

    return {
      scannerId:      id,
      scannerName:    scanner.name,
      logic:          scanner.logic,
      runAt:          new Date().toISOString(),
      totalScanned:   uniq.length,
      totalMatched:   results.length,
      results,
    };
  }

  // Run an ad-hoc scanner (not saved) — used by the "Test" button
  async runAdHoc(data: any): Promise<any> {
    const created = this.createScanner(data);
    const res = await this.runScanner(created.id);
    scanners.delete(created.id);
    return res;
  }
}
