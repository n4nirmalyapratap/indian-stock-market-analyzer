import { describe, it, expect } from "vitest";
import {
  calcEMA,
  calcSMA,
  calcWMA,
  calcHMA,
  calcVWMA,
  calcDEMA,
  calcTEMA,
  calcRSI,
  calcMACD,
  calcBollingerBands,
  calcDonchian,
  calcKeltner,
  calcATR,
  calcPSAR,
  calcSupertrend,
  calcStochastic,
  calcStochRSI,
  calcCCI,
  calcWilliamsR,
  calcMFI,
  calcOBV,
  calcROC,
  calcAO,
  calcCMF,
  calcTRIX,
  calcADX,
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
// Build OHLC where high = close+1, low = close-1, open = close, given a close series.
function ohlcFromCloses(closes: number[]) {
  return {
    highs:  closes.map(c => c + 1),
    lows:   closes.map(c => c - 1),
    closes: [...closes],
    opens:  [...closes],
  };
}

// ─── calcSMA ────────────────────────────────────────────────────────────────

describe("calcSMA", () => {
  it("returns null for first (period - 1) values", () => {
    expect(calcSMA(range(20), 5).slice(0, 4).every(v => v === null)).toBe(true);
  });
  it("computes the correct value for a known window", () => {
    const result = calcSMA([1, 2, 3, 4, 5, 6, 7], 5);
    expect(result[4]).toBeCloseTo(3, 3);
    expect(result[5]).toBeCloseTo(4, 3);
    expect(result[6]).toBeCloseTo(5, 3);
  });
  it("flat series gives constant SMA equal to the flat value", () => {
    nonNull(calcSMA(flat(30), 10)).forEach(v => expect(v).toBeCloseTo(100, 4));
  });
  it("output length equals input length", () => {
    expect(calcSMA(range(50), 10)).toHaveLength(50);
  });
  it("period 1 returns input values", () => {
    [10, 20, 30, 40].forEach((p, i) => expect(calcSMA([10, 20, 30, 40], 1)[i]).toBeCloseTo(p, 4));
  });
  it("rising series produces monotonically increasing SMA", () => {
    const vals = nonNull(calcSMA(range(30, 100, 2), 5));
    for (let i = 1; i < vals.length; i++) expect(vals[i]).toBeGreaterThan(vals[i - 1]);
  });
});

// ─── calcEMA ────────────────────────────────────────────────────────────────

describe("calcEMA", () => {
  it("returns null for first (period - 1) values", () => {
    expect(calcEMA(range(20), 5).slice(0, 4).every(v => v === null)).toBe(true);
  });
  it("flat series gives constant EMA", () => {
    nonNull(calcEMA(flat(30), 10)).forEach(v => expect(v).toBeCloseTo(100, 4));
  });
  it("EMA at seed point equals SMA at same index", () => {
    const ema = calcEMA(range(20, 100), 5);
    const sma = calcSMA(range(20, 100), 5);
    expect(ema[4]).toBeCloseTo(sma[4] as number, 3);
  });
  it("shorter period EMA reacts faster to a price spike", () => {
    const prices = [...flat(20), ...flat(10, 150)];
    const last5  = nonNull(calcEMA(prices, 5)).pop()!;
    const last20 = nonNull(calcEMA(prices, 20)).pop()!;
    expect(last5).toBeGreaterThan(last20);
  });
  it("no NaN/Infinity", () => {
    calcEMA(range(40), 5).forEach(v => { if (v !== null) expect(Number.isFinite(v)).toBe(true); });
  });
});

// ─── calcWMA ────────────────────────────────────────────────────────────────

describe("calcWMA", () => {
  it("returns null for first (period-1) values", () => {
    expect(calcWMA(range(20), 5).slice(0, 4).every(v => v === null)).toBe(true);
  });
  it("flat series gives constant WMA equal to flat value", () => {
    nonNull(calcWMA(flat(30), 10)).forEach(v => expect(v).toBeCloseTo(100, 4));
  });
  it("known weighted average for [1,2,3,4,5] period 5 = (1+4+9+16+25)/15 = 11/3 ≈ 3.6667", () => {
    expect(calcWMA([1, 2, 3, 4, 5], 5)[4]).toBeCloseTo((1 + 4 + 9 + 16 + 25) / 15, 3);
  });
  it("WMA reacts faster than SMA to a recent change", () => {
    const prices = [...flat(20, 100), 200];
    const wmaLast = nonNull(calcWMA(prices, 5)).pop()!;
    const smaLast = nonNull(calcSMA(prices, 5)).pop()!;
    expect(wmaLast).toBeGreaterThan(smaLast);
  });
  it("output length equals input length", () => {
    expect(calcWMA(range(40), 5)).toHaveLength(40);
  });
});

// ─── calcHMA ────────────────────────────────────────────────────────────────

describe("calcHMA", () => {
  it("output length equals input length", () => {
    expect(calcHMA(range(60), 9)).toHaveLength(60);
  });
  it("flat series gives constant HMA equal to flat value", () => {
    nonNull(calcHMA(flat(60), 9)).forEach(v => expect(v).toBeCloseTo(100, 3));
  });
  it("rising series produces non-decreasing HMA at the tail", () => {
    const vals = nonNull(calcHMA(range(60), 9));
    const tail = vals.slice(-10);
    for (let i = 1; i < tail.length; i++) expect(tail[i]).toBeGreaterThanOrEqual(tail[i - 1] - 0.001);
  });
  it("no NaN/Infinity in non-null values", () => {
    calcHMA(range(60), 9).forEach(v => { if (v !== null) expect(Number.isFinite(v)).toBe(true); });
  });
});

// ─── calcVWMA ───────────────────────────────────────────────────────────────

describe("calcVWMA", () => {
  it("equals SMA when all volumes are equal", () => {
    const closes = range(30, 100, 1);
    const vols = flat(30, 1000);
    const vwma = calcVWMA(closes, vols, 10);
    const sma  = calcSMA(closes, 10);
    for (let i = 0; i < closes.length; i++) {
      if (vwma[i] !== null && sma[i] !== null) expect(vwma[i]).toBeCloseTo(sma[i] as number, 3);
    }
  });
  it("falls back to SMA when total volume is zero", () => {
    const closes = range(20, 100, 1);
    const vols = flat(20, 0);
    const vwma = calcVWMA(closes, vols, 5);
    const sma  = calcSMA(closes, 5);
    for (let i = 4; i < closes.length; i++) {
      expect(vwma[i]).toBeCloseTo(sma[i] as number, 3);
    }
  });
  it("higher volume on extreme bars pulls the VWMA toward those bars", () => {
    const closes = [...flat(9, 100), 200];
    const heavyTail = [...flat(9, 1), 1000];
    const vwma = calcVWMA(closes, heavyTail, 10);
    expect((vwma[9] as number)).toBeGreaterThan(150);
  });
});

// ─── calcDEMA / calcTEMA ────────────────────────────────────────────────────

describe("calcDEMA / calcTEMA", () => {
  it("DEMA flat series stays flat", () => {
    nonNull(calcDEMA(flat(60), 10)).forEach(v => expect(v).toBeCloseTo(100, 3));
  });
  it("TEMA flat series stays flat", () => {
    nonNull(calcTEMA(flat(80), 10)).forEach(v => expect(v).toBeCloseTo(100, 3));
  });
  it("both reach lengths equal to input", () => {
    expect(calcDEMA(range(80), 10)).toHaveLength(80);
    expect(calcTEMA(range(80), 10)).toHaveLength(80);
  });
  it("on a sustained uptrend, DEMA is closer to the latest price than EMA", () => {
    const prices = [...flat(20), ...range(40, 100, 5)];
    const lastEma  = nonNull(calcEMA(prices,  10)).pop()!;
    const lastDema = nonNull(calcDEMA(prices, 10)).pop()!;
    const lastPrice = prices[prices.length - 1];
    expect(Math.abs(lastDema - lastPrice)).toBeLessThanOrEqual(Math.abs(lastEma - lastPrice));
  });
});

// ─── calcRSI ────────────────────────────────────────────────────────────────

describe("calcRSI", () => {
  it("returns null for first period values", () => {
    expect(calcRSI(range(30), 14).slice(0, 14).every(v => v === null)).toBe(true);
  });
  it("all valid values are in [0, 100]", () => {
    calcRSI(range(50, 100, 1).map((v, i) => v + Math.sin(i) * 5), 14).forEach(v => {
      if (v !== null) { expect(v).toBeGreaterThanOrEqual(0); expect(v).toBeLessThanOrEqual(100); }
    });
  });
  it("rising series → RSI near 100", () => {
    expect(nonNull(calcRSI(range(50, 100, 2), 14)).pop()!).toBeGreaterThan(90);
  });
  it("falling series → RSI near 0", () => {
    expect(nonNull(calcRSI(range(50, 200, -2), 14)).pop()!).toBeLessThan(10);
  });
  it("flat series → RSI = 50", () => {
    expect(nonNull(calcRSI(flat(30), 14)).pop()!).toBeCloseTo(50, 1);
  });
  it("too-short input returns all nulls", () => {
    expect(calcRSI([1, 2, 3], 14).every(v => v === null)).toBe(true);
  });
});

// ─── calcMACD ───────────────────────────────────────────────────────────────

describe("calcMACD", () => {
  it("histogram = MACD - signal at every non-null point", () => {
    const { macd, signal, histogram } = calcMACD(range(60, 100));
    for (let i = 0; i < 60; i++) {
      if (macd[i] !== null && signal[i] !== null && histogram[i] !== null) {
        expect(histogram[i]).toBeCloseTo(macd[i]! - signal[i]!, 3);
      }
    }
  });
  it("flat series → histogram near 0", () => {
    nonNull(calcMACD(flat(60)).histogram).forEach(v => expect(Math.abs(v)).toBeLessThan(0.001));
  });
  it("rising sharply → MACD positive", () => {
    expect(nonNull(calcMACD([...flat(30, 100), ...range(40, 100, 3)]).macd).pop()!).toBeGreaterThan(0);
  });
  it("falling sharply → MACD negative", () => {
    expect(nonNull(calcMACD([...flat(30, 200), ...range(40, 200, -3)]).macd).pop()!).toBeLessThan(0);
  });
});

// ─── calcBollingerBands ─────────────────────────────────────────────────────

describe("calcBollingerBands", () => {
  it("upper > middle > lower at every non-null point", () => {
    const { upper, middle, lower } = calcBollingerBands(range(40, 100));
    for (let i = 0; i < 40; i++) {
      if (upper[i] !== null) {
        expect(upper[i]!).toBeGreaterThan(middle[i]!);
        expect(middle[i]!).toBeGreaterThan(lower[i]!);
      }
    }
  });
  it("middle band equals SMA for the same period", () => {
    const { middle } = calcBollingerBands(range(40, 100), 20);
    const sma = calcSMA(range(40, 100), 20);
    for (let i = 0; i < 40; i++) if (middle[i] !== null) expect(middle[i]).toBeCloseTo(sma[i]!, 3);
  });
  it("flat → zero-width bands", () => {
    const { upper, middle, lower } = calcBollingerBands(flat(30), 20);
    for (let i = 19; i < 30; i++) { expect(upper[i]).toBeCloseTo(middle[i]!, 3); expect(lower[i]).toBeCloseTo(middle[i]!, 3); }
  });
  it("higher volatility → wider bands", () => {
    const { upper: u1, lower: l1 } = calcBollingerBands(flat(30, 100), 20);
    const { upper: u2, lower: l2 } = calcBollingerBands(Array.from({ length: 30 }, (_, i) => 100 + (i % 2 === 0 ? 10 : -10)), 20);
    const w1 = nonNull(u1).map((v, i) => v - nonNull(l1)[i]).reduce((a, b) => a + b, 0);
    const w2 = nonNull(u2).map((v, i) => v - nonNull(l2)[i]).reduce((a, b) => a + b, 0);
    expect(w2).toBeGreaterThan(w1);
  });
});

// ─── calcDonchian ───────────────────────────────────────────────────────────

describe("calcDonchian", () => {
  it("upper >= middle >= lower at every non-null point", () => {
    const { highs, lows } = ohlcFromCloses(range(40, 100));
    const { upper, middle, lower } = calcDonchian(highs, lows, 20);
    for (let i = 19; i < 40; i++) {
      expect(upper[i]!).toBeGreaterThanOrEqual(middle[i]!);
      expect(middle[i]!).toBeGreaterThanOrEqual(lower[i]!);
    }
  });
  it("upper equals max(highs) and lower equals min(lows) in window", () => {
    const highs = [10, 20, 15, 25, 12, 18];
    const lows  = [ 5, 12,  8, 18,  6, 10];
    const { upper, lower } = calcDonchian(highs, lows, 3);
    expect(upper[2]).toBe(20); expect(lower[2]).toBe(5);
    expect(upper[3]).toBe(25); expect(lower[3]).toBe(8);
  });
  it("flat highs/lows → bands collapse to that value", () => {
    const { upper, middle, lower } = calcDonchian(flat(30, 50), flat(30, 50), 10);
    for (let i = 9; i < 30; i++) { expect(upper[i]).toBe(50); expect(middle[i]).toBe(50); expect(lower[i]).toBe(50); }
  });
});

// ─── calcKeltner ────────────────────────────────────────────────────────────

describe("calcKeltner", () => {
  it("upper > middle > lower when volatility > 0", () => {
    const closes = range(40, 100, 1);
    const { highs, lows } = ohlcFromCloses(closes);
    const { upper, middle, lower } = calcKeltner(highs, lows, closes);
    for (let i = 0; i < 40; i++) {
      if (upper[i] !== null) {
        expect(upper[i]!).toBeGreaterThan(middle[i]!);
        expect(middle[i]!).toBeGreaterThan(lower[i]!);
      }
    }
  });
  it("middle band equals EMA of closes", () => {
    const closes = range(40, 100, 1);
    const { highs, lows } = ohlcFromCloses(closes);
    const { middle } = calcKeltner(highs, lows, closes, 20, 10, 2);
    const ema = calcEMA(closes, 20);
    for (let i = 0; i < 40; i++) if (middle[i] !== null && ema[i] !== null) expect(middle[i]).toBeCloseTo(ema[i] as number, 3);
  });
});

// ─── calcATR ────────────────────────────────────────────────────────────────

describe("calcATR", () => {
  it("returns null until period is reached", () => {
    const closes = range(20, 100, 1);
    const { highs, lows } = ohlcFromCloses(closes);
    expect(calcATR(highs, lows, closes, 14).slice(0, 13).every(v => v === null)).toBe(true);
  });
  it("flat OHLC → ATR is the constant true range", () => {
    const closes = flat(30, 100);
    const highs = closes.map(c => c + 2), lows = closes.map(c => c - 2);
    nonNull(calcATR(highs, lows, closes, 14)).forEach(v => expect(v).toBeCloseTo(4, 3));
  });
  it("non-negative", () => {
    const closes = range(40, 100, 1);
    const { highs, lows } = ohlcFromCloses(closes);
    nonNull(calcATR(highs, lows, closes, 14)).forEach(v => expect(v).toBeGreaterThanOrEqual(0));
  });
});

// ─── calcPSAR ───────────────────────────────────────────────────────────────

describe("calcPSAR", () => {
  it("output length equals input length", () => {
    const closes = range(40, 100, 1);
    const { highs, lows } = ohlcFromCloses(closes);
    expect(calcPSAR(highs, lows)).toHaveLength(40);
  });
  it("strong uptrend → SAR stays below the lows", () => {
    const closes = range(40, 100, 2);
    const { highs, lows } = ohlcFromCloses(closes);
    const psar = calcPSAR(highs, lows);
    // After an initial bar or two the trend dominates and SAR should sit below lows.
    for (let i = 5; i < 40; i++) expect(psar[i]!).toBeLessThanOrEqual(lows[i] + 0.001);
  });
  it("strong downtrend → SAR stays above the highs", () => {
    const closes = range(40, 200, -2);
    const { highs, lows } = ohlcFromCloses(closes);
    const psar = calcPSAR(highs, lows);
    for (let i = 5; i < 40; i++) expect(psar[i]!).toBeGreaterThanOrEqual(highs[i] - 0.001);
  });
});

// ─── calcSupertrend ─────────────────────────────────────────────────────────

describe("calcSupertrend", () => {
  it("output arrays match input length", () => {
    const closes = range(40, 100, 1);
    const { highs, lows } = ohlcFromCloses(closes);
    const { trend, isUp } = calcSupertrend(highs, lows, closes);
    expect(trend.length).toBe(40); expect(isUp.length).toBe(40);
  });
  it("strong uptrend → final isUp is true and trend stays under price", () => {
    const closes = range(40, 100, 3);
    const { highs, lows } = ohlcFromCloses(closes);
    const { trend, isUp } = calcSupertrend(highs, lows, closes);
    expect(isUp[39]).toBe(true);
    expect(trend[39]!).toBeLessThan(closes[39]);
  });
  it("strong downtrend → final isUp is false and trend stays above price", () => {
    const closes = range(40, 300, -3);
    const { highs, lows } = ohlcFromCloses(closes);
    const { trend, isUp } = calcSupertrend(highs, lows, closes);
    expect(isUp[39]).toBe(false);
    expect(trend[39]!).toBeGreaterThan(closes[39]);
  });
});

// ─── calcStochastic ─────────────────────────────────────────────────────────

describe("calcStochastic", () => {
  it("%K is in [0, 100]", () => {
    const closes = range(40, 100, 1);
    const { highs, lows } = ohlcFromCloses(closes);
    nonNull(calcStochastic(highs, lows, closes).k).forEach(v => {
      expect(v).toBeGreaterThanOrEqual(0); expect(v).toBeLessThanOrEqual(100);
    });
  });
  it("close at the high of the window → %K = 100", () => {
    const closes = [10, 12, 11, 13, 14, 15, 18];
    const highs  = [...closes];
    const lows   = closes.map(c => c - 5);
    const { k } = calcStochastic(highs, lows, closes, 5, 3);
    expect(k[6]).toBeCloseTo(100, 1);
  });
  it("close at the low of the window → %K = 0", () => {
    const closes = [20, 18, 19, 17, 16, 15, 10];
    const highs  = closes.map(c => c + 5);
    const lows   = [...closes];
    const { k } = calcStochastic(highs, lows, closes, 5, 3);
    expect(k[6]).toBeCloseTo(0, 1);
  });
});

// ─── calcStochRSI ───────────────────────────────────────────────────────────

describe("calcStochRSI", () => {
  it("%K and %D in [0, 100] when defined", () => {
    const prices = range(80, 100, 1).map((v, i) => v + Math.sin(i / 3) * 3);
    const { k, d } = calcStochRSI(prices);
    nonNull(k).forEach(v => { expect(v).toBeGreaterThanOrEqual(0); expect(v).toBeLessThanOrEqual(100); });
    nonNull(d).forEach(v => { expect(v).toBeGreaterThanOrEqual(0); expect(v).toBeLessThanOrEqual(100); });
  });
  it("output length equals input length", () => {
    const { k, d } = calcStochRSI(range(80));
    expect(k).toHaveLength(80); expect(d).toHaveLength(80);
  });
});

// ─── calcCCI ────────────────────────────────────────────────────────────────

describe("calcCCI", () => {
  it("flat series → CCI = 0", () => {
    const closes = flat(30, 100);
    const highs = closes.map(c => c + 1), lows = closes.map(c => c - 1);
    nonNull(calcCCI(highs, lows, closes, 20)).forEach(v => expect(v).toBe(0));
  });
  it("rising series → final CCI > 0", () => {
    const closes = range(30, 100, 1);
    const { highs, lows } = ohlcFromCloses(closes);
    expect(nonNull(calcCCI(highs, lows, closes, 20)).pop()!).toBeGreaterThan(0);
  });
});

// ─── calcWilliamsR ──────────────────────────────────────────────────────────

describe("calcWilliamsR", () => {
  it("values are in [-100, 0]", () => {
    const closes = range(40, 100, 1);
    const { highs, lows } = ohlcFromCloses(closes);
    nonNull(calcWilliamsR(highs, lows, closes)).forEach(v => {
      expect(v).toBeGreaterThanOrEqual(-100); expect(v).toBeLessThanOrEqual(0);
    });
  });
  it("close at the high → %R near 0", () => {
    const closes = [10, 11, 12, 13, 14, 15];
    const highs  = [...closes];
    const lows   = closes.map(c => c - 5);
    expect(calcWilliamsR(highs, lows, closes, 5)[5]).toBeCloseTo(0, 1);
  });
  it("close at the low → %R near -100", () => {
    const closes = [10, 9, 8, 7, 6, 5];
    const highs  = closes.map(c => c + 5);
    const lows   = [...closes];
    expect(calcWilliamsR(highs, lows, closes, 5)[5]).toBeCloseTo(-100, 1);
  });
});

// ─── calcMFI ────────────────────────────────────────────────────────────────

describe("calcMFI", () => {
  it("values are in [0, 100]", () => {
    const closes = range(40, 100, 1).map((v, i) => v + Math.sin(i) * 4);
    const { highs, lows } = ohlcFromCloses(closes);
    const vols = flat(40, 1000);
    nonNull(calcMFI(highs, lows, closes, vols, 14)).forEach(v => {
      expect(v).toBeGreaterThanOrEqual(0); expect(v).toBeLessThanOrEqual(100);
    });
  });
  it("strictly rising prices → MFI = 100", () => {
    const closes = range(40, 100, 2);
    const { highs, lows } = ohlcFromCloses(closes);
    const vols = flat(40, 1000);
    expect(nonNull(calcMFI(highs, lows, closes, vols, 14)).pop()!).toBe(100);
  });
});

// ─── calcOBV ────────────────────────────────────────────────────────────────

describe("calcOBV", () => {
  it("output length equals input length", () => {
    expect(calcOBV(range(20), flat(20, 100))).toHaveLength(20);
  });
  it("strictly rising closes → OBV equals sum of volumes from index 1", () => {
    const closes = [10, 11, 12, 13, 14];
    const vols   = [100, 200, 300, 400, 500];
    expect(calcOBV(closes, vols)).toEqual([0, 200, 500, 900, 1400]);
  });
  it("strictly falling closes → OBV equals negative sum from index 1", () => {
    const closes = [10, 9, 8, 7, 6];
    const vols   = [100, 200, 300, 400, 500];
    expect(calcOBV(closes, vols)).toEqual([0, -200, -500, -900, -1400]);
  });
  it("flat closes → OBV stays at 0", () => {
    expect(calcOBV(flat(10, 50), flat(10, 100))).toEqual(Array(10).fill(0));
  });
});

// ─── calcROC ────────────────────────────────────────────────────────────────

describe("calcROC", () => {
  it("returns null for first period values", () => {
    expect(calcROC(range(30, 100, 1), 12).slice(0, 12).every(v => v === null)).toBe(true);
  });
  it("rising series → positive ROC", () => {
    nonNull(calcROC(range(30, 100, 1), 12)).forEach(v => expect(v).toBeGreaterThan(0));
  });
  it("flat series → ROC = 0", () => {
    nonNull(calcROC(flat(30, 100), 12)).forEach(v => expect(v).toBeCloseTo(0, 4));
  });
});

// ─── calcAO ─────────────────────────────────────────────────────────────────

describe("calcAO", () => {
  it("flat series → AO ≈ 0", () => {
    const flat100 = flat(60, 100);
    nonNull(calcAO(flat100, flat100)).forEach(v => expect(Math.abs(v)).toBeLessThan(0.001));
  });
  it("strongly rising → final AO > 0", () => {
    const closes = range(60, 100, 1);
    const { highs, lows } = ohlcFromCloses(closes);
    expect(nonNull(calcAO(highs, lows)).pop()!).toBeGreaterThan(0);
  });
  it("strongly falling → final AO < 0", () => {
    const closes = range(60, 200, -1);
    const { highs, lows } = ohlcFromCloses(closes);
    expect(nonNull(calcAO(highs, lows)).pop()!).toBeLessThan(0);
  });
});

// ─── calcCMF ────────────────────────────────────────────────────────────────

describe("calcCMF", () => {
  it("values are in [-1, 1]", () => {
    const closes = range(40, 100, 1).map((v, i) => v + Math.sin(i) * 2);
    const { highs, lows } = ohlcFromCloses(closes);
    nonNull(calcCMF(highs, lows, closes, flat(40, 1000), 20)).forEach(v => {
      expect(v).toBeGreaterThanOrEqual(-1.0001); expect(v).toBeLessThanOrEqual(1.0001);
    });
  });
  it("close = high every bar → CMF approaches +1", () => {
    const closes = range(40, 100, 1);
    const highs  = [...closes];
    const lows   = closes.map(c => c - 5);
    expect(nonNull(calcCMF(highs, lows, closes, flat(40, 1000), 20)).pop()!).toBeCloseTo(1, 2);
  });
  it("close = low every bar → CMF approaches -1", () => {
    const closes = range(40, 100, 1);
    const lows   = [...closes];
    const highs  = closes.map(c => c + 5);
    expect(nonNull(calcCMF(highs, lows, closes, flat(40, 1000), 20)).pop()!).toBeCloseTo(-1, 2);
  });
});

// ─── calcTRIX ───────────────────────────────────────────────────────────────

describe("calcTRIX", () => {
  it("flat series → TRIX ≈ 0", () => {
    nonNull(calcTRIX(flat(80, 100), 14)).forEach(v => expect(Math.abs(v)).toBeLessThan(0.001));
  });
  it("output length equals input length", () => {
    expect(calcTRIX(range(80), 14)).toHaveLength(80);
  });
  it("rising series → final TRIX > 0", () => {
    expect(nonNull(calcTRIX(range(80, 100, 1), 14)).pop()!).toBeGreaterThan(0);
  });
});

// ─── calcADX ────────────────────────────────────────────────────────────────

describe("calcADX", () => {
  it("output arrays match input length", () => {
    const closes = range(60, 100, 1);
    const { highs, lows } = ohlcFromCloses(closes);
    const { adx, plusDI, minusDI } = calcADX(highs, lows, closes, 14);
    expect(adx).toHaveLength(60); expect(plusDI).toHaveLength(60); expect(minusDI).toHaveLength(60);
  });
  it("uptrend → +DI > -DI at the end", () => {
    const closes = range(60, 100, 2);
    const { highs, lows } = ohlcFromCloses(closes);
    const { plusDI, minusDI } = calcADX(highs, lows, closes, 14);
    expect((plusDI[59] as number)).toBeGreaterThan(minusDI[59] as number);
  });
  it("downtrend → -DI > +DI at the end", () => {
    const closes = range(60, 200, -2);
    const { highs, lows } = ohlcFromCloses(closes);
    const { plusDI, minusDI } = calcADX(highs, lows, closes, 14);
    expect((minusDI[59] as number)).toBeGreaterThan(plusDI[59] as number);
  });
  it("ADX values when present are in [0, 100]", () => {
    const closes = range(80, 100, 1).map((v, i) => v + Math.sin(i) * 5);
    const { highs, lows } = ohlcFromCloses(closes);
    nonNull(calcADX(highs, lows, closes, 14).adx).forEach(v => {
      expect(v).toBeGreaterThanOrEqual(0); expect(v).toBeLessThanOrEqual(100);
    });
  });
});
