import { describe, it, expect } from "vitest";
import {
  calcEMA,
  calcSMA,
  calcRSI,
  calcMACD,
  calcBollingerBands,
} from "../indicators";

// ─── helpers ────────────────────────────────────────────────────────────────

function range(n: number, start = 100, step = 1): number[] {
  return Array.from({ length: n }, (_, i) => start + i * step);
}

function flat(n: number, value = 100): number[] {
  return Array(n).fill(value);
}

function nonNull<T>(arr: (T | null)[]): T[] {
  return arr.filter((v): v is T => v !== null);
}

// ─── calcSMA ─────────────────────────────────────────────────────────────────

describe("calcSMA", () => {
  it("returns null for first (period - 1) values", () => {
    const result = calcSMA(range(20), 5);
    expect(result.slice(0, 4).every(v => v === null)).toBe(true);
  });

  it("returns a value for index >= period - 1", () => {
    const result = calcSMA(range(20), 5);
    expect(result[4]).not.toBeNull();
  });

  it("computes the correct value for a known window", () => {
    // SMA(5) of [1,2,3,4,5,...] at index 4 = (1+2+3+4+5)/5 = 3
    const result = calcSMA([1, 2, 3, 4, 5, 6, 7], 5);
    expect(result[4]).toBeCloseTo(3, 3);
    expect(result[5]).toBeCloseTo(4, 3);
    expect(result[6]).toBeCloseTo(5, 3);
  });

  it("flat series gives constant SMA equal to the flat value", () => {
    const result = calcSMA(flat(30), 10);
    nonNull(result).forEach(v => expect(v).toBeCloseTo(100, 4));
  });

  it("output length equals input length", () => {
    const prices = range(50);
    const result = calcSMA(prices, 10);
    expect(result).toHaveLength(50);
  });

  it("period 1 returns input values", () => {
    const prices = [10, 20, 30, 40];
    const result = calcSMA(prices, 1);
    prices.forEach((p, i) => expect(result[i]).toBeCloseTo(p, 4));
  });

  it("no NaN in output", () => {
    const result = calcSMA(range(40), 5);
    result.forEach(v => {
      if (v !== null) expect(isNaN(v)).toBe(false);
    });
  });

  it("rising series produces monotonically increasing SMA", () => {
    const result = calcSMA(range(30, 100, 2), 5);
    const vals = nonNull(result);
    for (let i = 1; i < vals.length; i++) {
      expect(vals[i]).toBeGreaterThan(vals[i - 1]);
    }
  });
});

// ─── calcEMA ─────────────────────────────────────────────────────────────────

describe("calcEMA", () => {
  it("returns null for first (period - 1) values", () => {
    const result = calcEMA(range(20), 5);
    expect(result.slice(0, 4).every(v => v === null)).toBe(true);
  });

  it("flat series gives constant EMA equal to the flat value", () => {
    const result = calcEMA(flat(30), 10);
    nonNull(result).forEach(v => expect(v).toBeCloseTo(100, 4));
  });

  it("output length equals input length", () => {
    const result = calcEMA(range(50), 10);
    expect(result).toHaveLength(50);
  });

  it("EMA(period) at first valid index equals SMA(period) at same index", () => {
    const prices = range(20, 100);
    const ema    = calcEMA(prices, 5);
    const sma    = calcSMA(prices, 5);
    // At the seed point (index 4) EMA is initialised to the SMA
    expect(ema[4]).toBeCloseTo(sma[4] as number, 3);
  });

  it("shorter period EMA reacts faster to a price spike", () => {
    const prices = [...flat(20), ...flat(10, 150)];
    const ema5  = nonNull(calcEMA(prices, 5));
    const ema20 = nonNull(calcEMA(prices, 20));
    const last5  = ema5[ema5.length - 1];
    const last20 = ema20[ema20.length - 1];
    expect(last5).toBeGreaterThan(last20); // shorter period is closer to 150
  });

  it("no NaN or Infinity in output", () => {
    const result = calcEMA(range(40), 5);
    result.forEach(v => {
      if (v !== null) {
        expect(isNaN(v)).toBe(false);
        expect(isFinite(v)).toBe(true);
      }
    });
  });

  it("EMA tracks a rising series upward", () => {
    const vals = nonNull(calcEMA(range(30, 100, 1), 5));
    for (let i = 1; i < vals.length; i++) {
      expect(vals[i]).toBeGreaterThan(vals[i - 1]);
    }
  });
});

// ─── calcRSI ─────────────────────────────────────────────────────────────────

describe("calcRSI", () => {
  it("returns null for first period values", () => {
    const result = calcRSI(range(30), 14);
    expect(result.slice(0, 14).every(v => v === null)).toBe(true);
  });

  it("all valid RSI values are in [0, 100]", () => {
    const prices = range(50, 100, 1).map((v, i) => v + Math.sin(i) * 5);
    const result = calcRSI(prices, 14);
    nonNull(result).forEach(v => {
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThanOrEqual(100);
    });
  });

  it("purely rising series produces RSI near 100", () => {
    const prices = range(50, 100, 2); // strictly increasing
    const result = calcRSI(prices, 14);
    const last = nonNull(result).pop()!;
    expect(last).toBeGreaterThan(90);
  });

  it("purely falling series produces RSI near 0", () => {
    const prices = range(50, 200, -2); // strictly decreasing
    const result = calcRSI(prices, 14);
    const last = nonNull(result).pop()!;
    expect(last).toBeLessThan(10);
  });

  it("flat series produces RSI = 50", () => {
    const result = calcRSI(flat(30), 14);
    const last = nonNull(result).pop()!;
    expect(last).toBeCloseTo(50, 1);
  });

  it("output length equals input length", () => {
    expect(calcRSI(range(50)).length).toBe(50);
  });

  it("no NaN or Infinity", () => {
    const result = calcRSI(range(50));
    result.forEach(v => {
      if (v !== null) {
        expect(isNaN(v)).toBe(false);
        expect(isFinite(v)).toBe(true);
      }
    });
  });

  it("too-short input returns all nulls", () => {
    const result = calcRSI([1, 2, 3], 14);
    expect(result.every(v => v === null)).toBe(true);
  });
});

// ─── calcMACD ────────────────────────────────────────────────────────────────

describe("calcMACD", () => {
  it("all three arrays have the same length as input", () => {
    const prices = range(60, 100);
    const { macd, signal, histogram } = calcMACD(prices);
    expect(macd).toHaveLength(60);
    expect(signal).toHaveLength(60);
    expect(histogram).toHaveLength(60);
  });

  it("histogram = MACD line - signal at every non-null point", () => {
    const prices = range(60, 100);
    const { macd, signal, histogram } = calcMACD(prices);
    for (let i = 0; i < prices.length; i++) {
      if (macd[i] !== null && signal[i] !== null && histogram[i] !== null) {
        expect(histogram[i]).toBeCloseTo(macd[i]! - signal[i]!, 3);
      }
    }
  });

  it("flat series produces histogram near 0", () => {
    const prices = flat(60);
    const { histogram } = calcMACD(prices);
    nonNull(histogram).forEach(v => expect(Math.abs(v)).toBeLessThan(0.001));
  });

  it("returns all nulls if input is too short", () => {
    const { macd, signal, histogram } = calcMACD(range(10));
    expect(macd.every(v => v === null)).toBe(true);
    expect(signal.every(v => v === null)).toBe(true);
    expect(histogram.every(v => v === null)).toBe(true);
  });

  it("no NaN or Infinity in non-null values", () => {
    const prices = range(70, 100);
    const { macd, signal, histogram } = calcMACD(prices);
    [...macd, ...signal, ...histogram].forEach(v => {
      if (v !== null) {
        expect(isNaN(v)).toBe(false);
        expect(isFinite(v)).toBe(true);
      }
    });
  });

  it("MACD is positive when prices have been rising sharply", () => {
    const prices = [...flat(30, 100), ...range(40, 100, 3)];
    const { macd } = calcMACD(prices);
    const lastMacd = nonNull(macd).pop()!;
    expect(lastMacd).toBeGreaterThan(0);
  });

  it("MACD is negative when prices have been falling sharply", () => {
    const prices = [...flat(30, 200), ...range(40, 200, -3)];
    const { macd } = calcMACD(prices);
    const lastMacd = nonNull(macd).pop()!;
    expect(lastMacd).toBeLessThan(0);
  });
});

// ─── calcBollingerBands ───────────────────────────────────────────────────────

describe("calcBollingerBands", () => {
  it("all three arrays have the same length as input", () => {
    const prices = range(40);
    const { upper, middle, lower } = calcBollingerBands(prices);
    expect(upper).toHaveLength(40);
    expect(middle).toHaveLength(40);
    expect(lower).toHaveLength(40);
  });

  it("upper > middle > lower at every non-null point", () => {
    const prices = range(40, 100);
    const { upper, middle, lower } = calcBollingerBands(prices);
    for (let i = 0; i < prices.length; i++) {
      if (upper[i] !== null && middle[i] !== null && lower[i] !== null) {
        expect(upper[i]!).toBeGreaterThan(middle[i]!);
        expect(middle[i]!).toBeGreaterThan(lower[i]!);
      }
    }
  });

  it("middle band equals SMA for the given period", () => {
    const prices = range(40, 100);
    const { middle } = calcBollingerBands(prices, 20);
    const sma = calcSMA(prices, 20);
    for (let i = 0; i < prices.length; i++) {
      if (middle[i] !== null && sma[i] !== null) {
        expect(middle[i]).toBeCloseTo(sma[i]!, 3);
      }
    }
  });

  it("flat series produces zero-width bands (upper == middle == lower)", () => {
    const prices = flat(30);
    const { upper, middle, lower } = calcBollingerBands(prices, 20);
    for (let i = 0; i < prices.length; i++) {
      if (upper[i] !== null) {
        expect(upper[i]).toBeCloseTo(middle[i]!, 3);
        expect(lower[i]).toBeCloseTo(middle[i]!, 3);
      }
    }
  });

  it("returns nulls for first (period-1) indices", () => {
    const prices = range(30);
    const { upper } = calcBollingerBands(prices, 20);
    expect(upper.slice(0, 19).every(v => v === null)).toBe(true);
  });

  it("no NaN or Infinity in non-null values", () => {
    const { upper, middle, lower } = calcBollingerBands(range(40));
    [...upper, ...middle, ...lower].forEach(v => {
      if (v !== null) {
        expect(isNaN(v)).toBe(false);
        expect(isFinite(v)).toBe(true);
      }
    });
  });

  it("higher volatility produces wider bands", () => {
    const lowVol  = flat(30, 100);
    const highVol = Array.from({ length: 30 }, (_, i) => 100 + (i % 2 === 0 ? 10 : -10));
    const { upper: u1, lower: l1 } = calcBollingerBands(lowVol, 20);
    const { upper: u2, lower: l2 } = calcBollingerBands(highVol, 20);
    const width1 = nonNull(u1).map((v, i) => v - nonNull(l1)[i]);
    const width2 = nonNull(u2).map((v, i) => v - nonNull(l2)[i]);
    const avg1 = width1.reduce((a, b) => a + b, 0) / width1.length;
    const avg2 = width2.reduce((a, b) => a + b, 0) / width2.length;
    expect(avg2).toBeGreaterThan(avg1);
  });
});
