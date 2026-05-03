// ─── Moving Averages ────────────────────────────────────────────────────────

export function calcEMA(closes: number[], period: number): (number | null)[] {
  const k = 2 / (period + 1);
  const out: (number | null)[] = [];
  let ema: number | null = null;
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) { out.push(null); continue; }
    if (i === period - 1) {
      ema = closes.slice(0, period).reduce((a, b) => a + b, 0) / period;
      out.push(+ema.toFixed(4)); continue;
    }
    ema = closes[i] * k + ema! * (1 - k);
    out.push(+ema.toFixed(4));
  }
  return out;
}

export function calcSMA(closes: number[], period: number): (number | null)[] {
  return closes.map((_, i) => {
    if (i < period - 1) return null;
    return +(closes.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0) / period).toFixed(4);
  });
}

// Weighted MA: weights 1..period (most recent gets period weight)
export function calcWMA(closes: number[], period: number): (number | null)[] {
  const out: (number | null)[] = [];
  const denom = (period * (period + 1)) / 2;
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) { out.push(null); continue; }
    let s = 0;
    for (let j = 0; j < period; j++) s += closes[i - period + 1 + j] * (j + 1);
    out.push(+(s / denom).toFixed(4));
  }
  return out;
}

// Hull MA: WMA(2*WMA(n/2) - WMA(n), sqrt(n))
export function calcHMA(closes: number[], period: number): (number | null)[] {
  const halfP = Math.max(1, Math.floor(period / 2));
  const sqrtP = Math.max(1, Math.round(Math.sqrt(period)));
  const wmaHalf = calcWMA(closes, halfP);
  const wmaFull = calcWMA(closes, period);
  // Build raw series at indices where both are defined
  const rawAligned: number[] = [];
  const idxMap: number[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (wmaHalf[i] !== null && wmaFull[i] !== null) {
      rawAligned.push(2 * (wmaHalf[i] as number) - (wmaFull[i] as number));
      idxMap.push(i);
    }
  }
  const wmaRaw = calcWMA(rawAligned, sqrtP);
  const out: (number | null)[] = closes.map(() => null);
  for (let k = 0; k < idxMap.length; k++) {
    if (wmaRaw[k] !== null) out[idxMap[k]] = +(wmaRaw[k] as number).toFixed(4);
  }
  return out;
}

// Volume-Weighted MA. Falls back to SMA when total volume in window is 0.
export function calcVWMA(closes: number[], volumes: number[], period: number): (number | null)[] {
  const out: (number | null)[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) { out.push(null); continue; }
    let num = 0, den = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const v = volumes[j] ?? 0;
      num += closes[j] * v;
      den += v;
    }
    if (den > 0) {
      out.push(+(num / den).toFixed(4));
    } else {
      // Volume-less symbol (some indices) — degrade gracefully to SMA
      const sma = closes.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0) / period;
      out.push(+sma.toFixed(4));
    }
  }
  return out;
}

// DEMA = 2*EMA - EMA(EMA)
export function calcDEMA(closes: number[], period: number): (number | null)[] {
  const e1 = calcEMA(closes, period);
  const out: (number | null)[] = closes.map(() => null);
  const start = e1.findIndex(v => v !== null);
  if (start < 0) return out;
  const sub = e1.slice(start).map(v => v as number);
  const e2 = calcEMA(sub, period);
  for (let i = 0; i < e2.length; i++) {
    if (e2[i] !== null) {
      out[start + i] = +(2 * (e1[start + i] as number) - (e2[i] as number)).toFixed(4);
    }
  }
  return out;
}

// TEMA = 3*EMA - 3*EMA(EMA) + EMA(EMA(EMA))
export function calcTEMA(closes: number[], period: number): (number | null)[] {
  const out: (number | null)[] = closes.map(() => null);
  const e1 = calcEMA(closes, period);
  const start1 = e1.findIndex(v => v !== null);
  if (start1 < 0) return out;
  const e1sub = e1.slice(start1).map(v => v as number);
  const e2 = calcEMA(e1sub, period);
  const start2 = e2.findIndex(v => v !== null);
  if (start2 < 0) return out;
  const e2sub = e2.slice(start2).map(v => v as number);
  const e3 = calcEMA(e2sub, period);
  for (let k = 0; k < e3.length; k++) {
    if (e3[k] === null) continue;
    const e1Idx = start1 + start2 + k;
    const e2Idx = start2 + k;
    const v = 3 * (e1[e1Idx] as number) - 3 * (e2[e2Idx] as number) + (e3[k] as number);
    out[e1Idx] = +v.toFixed(4);
  }
  return out;
}

// ─── Bollinger / Donchian / Keltner Channels ────────────────────────────────

export function calcBollingerBands(closes: number[], period = 20, mult = 2): {
  upper: (number | null)[]; middle: (number | null)[]; lower: (number | null)[];
} {
  const upper: (number | null)[] = [], middle: (number | null)[] = [], lower: (number | null)[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) { upper.push(null); middle.push(null); lower.push(null); continue; }
    const sl = closes.slice(i - period + 1, i + 1);
    const mean = sl.reduce((a, b) => a + b, 0) / period;
    const std = Math.sqrt(sl.reduce((a, b) => a + (b - mean) ** 2, 0) / period);
    upper.push(+(mean + mult * std).toFixed(4));
    middle.push(+mean.toFixed(4));
    lower.push(+(mean - mult * std).toFixed(4));
  }
  return { upper, middle, lower };
}

export function calcDonchian(highs: number[], lows: number[], period = 20): {
  upper: (number | null)[]; middle: (number | null)[]; lower: (number | null)[];
} {
  const upper: (number | null)[] = [], middle: (number | null)[] = [], lower: (number | null)[] = [];
  for (let i = 0; i < highs.length; i++) {
    if (i < period - 1) { upper.push(null); middle.push(null); lower.push(null); continue; }
    let hi = -Infinity, lo = Infinity;
    for (let j = i - period + 1; j <= i; j++) {
      if (highs[j] > hi) hi = highs[j];
      if (lows[j]  < lo) lo = lows[j];
    }
    upper.push(+hi.toFixed(4));
    lower.push(+lo.toFixed(4));
    middle.push(+((hi + lo) / 2).toFixed(4));
  }
  return { upper, middle, lower };
}

export function calcKeltner(
  highs: number[], lows: number[], closes: number[],
  period = 20, atrPeriod = 10, mult = 2,
): { upper: (number | null)[]; middle: (number | null)[]; lower: (number | null)[] } {
  const ema = calcEMA(closes, period);
  const atr = calcATR(highs, lows, closes, atrPeriod);
  const upper: (number | null)[] = [], middle: (number | null)[] = [], lower: (number | null)[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (ema[i] === null || atr[i] === null) {
      upper.push(null); middle.push(null); lower.push(null); continue;
    }
    middle.push(+(ema[i] as number).toFixed(4));
    upper.push(+((ema[i] as number) + mult * (atr[i] as number)).toFixed(4));
    lower.push(+((ema[i] as number) - mult * (atr[i] as number)).toFixed(4));
  }
  return { upper, middle, lower };
}

// ─── Trend / Volatility ─────────────────────────────────────────────────────

// True Range
function calcTR(highs: number[], lows: number[], closes: number[]): number[] {
  const tr: number[] = [];
  for (let i = 0; i < highs.length; i++) {
    if (i === 0) { tr.push(highs[i] - lows[i]); continue; }
    tr.push(Math.max(
      highs[i] - lows[i],
      Math.abs(highs[i] - closes[i - 1]),
      Math.abs(lows[i]  - closes[i - 1]),
    ));
  }
  return tr;
}

// Average True Range (Wilder smoothing)
export function calcATR(highs: number[], lows: number[], closes: number[], period = 14): (number | null)[] {
  const tr = calcTR(highs, lows, closes);
  const out: (number | null)[] = closes.map(() => null);
  if (tr.length < period) return out;
  let atr = 0;
  for (let i = 0; i < period; i++) atr += tr[i];
  atr /= period;
  out[period - 1] = +atr.toFixed(4);
  for (let i = period; i < tr.length; i++) {
    atr = (atr * (period - 1) + tr[i]) / period;
    out[i] = +atr.toFixed(4);
  }
  return out;
}

// Parabolic SAR (classic Wilder)
export function calcPSAR(highs: number[], lows: number[], step = 0.02, max = 0.2): (number | null)[] {
  const n = highs.length;
  const out: (number | null)[] = new Array(n).fill(null);
  if (n < 2) return out;

  let isLong = highs[1] >= highs[0];
  let af  = step;
  let ep  = isLong ? highs[1] : lows[1];
  let sar = isLong ? Math.min(lows[0], lows[1]) : Math.max(highs[0], highs[1]);
  out[1] = +sar.toFixed(4);

  for (let i = 2; i < n; i++) {
    let nextSar = sar + af * (ep - sar);
    if (isLong) {
      // Don't penetrate prior 2 lows
      nextSar = Math.min(nextSar, lows[i - 1], lows[i - 2]);
      if (lows[i] < nextSar) {
        // reversal
        isLong = false;
        nextSar = ep;
        ep = lows[i];
        af = step;
      } else {
        if (highs[i] > ep) { ep = highs[i]; af = Math.min(af + step, max); }
      }
    } else {
      nextSar = Math.max(nextSar, highs[i - 1], highs[i - 2]);
      if (highs[i] > nextSar) {
        isLong = true;
        nextSar = ep;
        ep = highs[i];
        af = step;
      } else {
        if (lows[i] < ep) { ep = lows[i]; af = Math.min(af + step, max); }
      }
    }
    sar = nextSar;
    out[i] = +sar.toFixed(4);
  }
  return out;
}

// Supertrend(period=10, mult=3). Returns trend line and direction (true=uptrend).
export function calcSupertrend(
  highs: number[], lows: number[], closes: number[],
  period = 10, mult = 3,
): { trend: (number | null)[]; isUp: (boolean | null)[] } {
  const n = closes.length;
  const atr = calcATR(highs, lows, closes, period);
  const trend: (number | null)[] = new Array(n).fill(null);
  const isUp: (boolean | null)[] = new Array(n).fill(null);

  let prevUpper = 0, prevLower = 0, prevIsUp = true, started = false;
  for (let i = 0; i < n; i++) {
    if (atr[i] === null) continue;
    const hl2 = (highs[i] + lows[i]) / 2;
    let upper = hl2 + mult * (atr[i] as number);
    let lower = hl2 - mult * (atr[i] as number);
    if (started) {
      if (closes[i - 1] <= prevUpper) upper = Math.min(upper, prevUpper);
      if (closes[i - 1] >= prevLower) lower = Math.max(lower, prevLower);
    }
    let up: boolean;
    if (!started) {
      up = closes[i] > hl2;
    } else if (closes[i] > prevUpper) {
      up = true;
    } else if (closes[i] < prevLower) {
      up = false;
    } else {
      up = prevIsUp;
    }
    trend[i] = +(up ? lower : upper).toFixed(4);
    isUp[i]  = up;
    prevUpper = upper;
    prevLower = lower;
    prevIsUp  = up;
    started   = true;
  }
  return { trend, isUp };
}

// ─── Oscillators ────────────────────────────────────────────────────────────

export function calcRSI(closes: number[], period = 14): (number | null)[] {
  const out: (number | null)[] = [];
  if (closes.length < period + 1) return closes.map(() => null);
  let avgGain = 0, avgLoss = 0;
  for (let i = 1; i <= period; i++) {
    const d = closes[i] - closes[i - 1];
    if (d > 0) avgGain += d; else avgLoss -= d;
  }
  avgGain /= period; avgLoss /= period;
  for (let i = 0; i < closes.length; i++) {
    if (i < period) { out.push(null); continue; }
    if (i > period) {
      const d = closes[i] - closes[i - 1];
      avgGain = (avgGain * (period - 1) + (d > 0 ? d : 0)) / period;
      avgLoss = (avgLoss * (period - 1) + (d < 0 ? -d : 0)) / period;
    }
    let rsi: number;
    if (avgLoss === 0 && avgGain === 0) rsi = 50;
    else if (avgLoss === 0) rsi = 100;
    else if (avgGain === 0) rsi = 0;
    else rsi = 100 - 100 / (1 + avgGain / avgLoss);
    out.push(+rsi.toFixed(2));
  }
  return out;
}

export function calcMACD(closes: number[], fast = 12, slow = 26, sig = 9): {
  macd: (number | null)[]; signal: (number | null)[]; histogram: (number | null)[];
} {
  const nulls = closes.map(() => null as null);
  const emaFast = calcEMA(closes, fast);
  const emaSlow = calcEMA(closes, slow);
  const macdLine = emaFast.map((f, i) =>
    f !== null && emaSlow[i] !== null ? +(f - emaSlow[i]!).toFixed(4) : null,
  );
  const firstNonNull = macdLine.findIndex(v => v !== null);
  if (firstNonNull < 0) return { macd: nulls, signal: nulls, histogram: nulls };

  const macdVals = macdLine.slice(firstNonNull).map(v => v ?? 0);
  const sigLine = calcEMA(macdVals, sig);
  const signal = macdLine.map((m, i) => {
    if (m === null) return null;
    return sigLine[i - firstNonNull] ?? null;
  });
  return {
    macd: macdLine, signal,
    histogram: macdLine.map((m, i) => (m !== null && signal[i] !== null ? +(m - signal[i]!).toFixed(4) : null)),
  };
}

// Stochastic %K / %D
export function calcStochastic(
  highs: number[], lows: number[], closes: number[],
  kPeriod = 14, dPeriod = 3,
): { k: (number | null)[]; d: (number | null)[] } {
  const k: (number | null)[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (i < kPeriod - 1) { k.push(null); continue; }
    let hi = -Infinity, lo = Infinity;
    for (let j = i - kPeriod + 1; j <= i; j++) {
      if (highs[j] > hi) hi = highs[j];
      if (lows[j]  < lo) lo = lows[j];
    }
    if (hi === lo) { k.push(50); continue; }
    k.push(+(((closes[i] - lo) / (hi - lo)) * 100).toFixed(2));
  }
  const d: (number | null)[] = [];
  for (let i = 0; i < k.length; i++) {
    if (i < kPeriod - 1 + dPeriod - 1) { d.push(null); continue; }
    let s = 0;
    for (let j = i - dPeriod + 1; j <= i; j++) s += (k[j] as number);
    d.push(+(s / dPeriod).toFixed(2));
  }
  return { k, d };
}

// Stochastic RSI
export function calcStochRSI(
  closes: number[],
  rsiPeriod = 14, stochPeriod = 14, kSmooth = 3, dSmooth = 3,
): { k: (number | null)[]; d: (number | null)[] } {
  const rsi = calcRSI(closes, rsiPeriod);
  const stochVals: (number | null)[] = [];
  for (let i = 0; i < rsi.length; i++) {
    if (i < rsiPeriod + stochPeriod - 1) { stochVals.push(null); continue; }
    let hi = -Infinity, lo = Infinity, valid = 0;
    for (let j = i - stochPeriod + 1; j <= i; j++) {
      if (rsi[j] === null) continue;
      valid++;
      if ((rsi[j] as number) > hi) hi = rsi[j] as number;
      if ((rsi[j] as number) < lo) lo = rsi[j] as number;
    }
    if (valid < stochPeriod) { stochVals.push(null); continue; }
    if (hi === lo) { stochVals.push(50); continue; }
    stochVals.push(+(((rsi[i] as number) - lo) / (hi - lo) * 100).toFixed(2));
  }
  const sma = (arr: (number | null)[], n: number): (number | null)[] => {
    const out: (number | null)[] = [];
    for (let i = 0; i < arr.length; i++) {
      if (i < n - 1) { out.push(null); continue; }
      const w = arr.slice(i - n + 1, i + 1);
      if (w.some(v => v === null)) { out.push(null); continue; }
      out.push(+((w as number[]).reduce((a, b) => a + b, 0) / n).toFixed(2));
    }
    return out;
  };
  const k = sma(stochVals, kSmooth);
  const d = sma(k, dSmooth);
  return { k, d };
}

// Commodity Channel Index
export function calcCCI(highs: number[], lows: number[], closes: number[], period = 20): (number | null)[] {
  const out: (number | null)[] = [];
  const tp = closes.map((c, i) => (highs[i] + lows[i] + c) / 3);
  for (let i = 0; i < tp.length; i++) {
    if (i < period - 1) { out.push(null); continue; }
    const slice = tp.slice(i - period + 1, i + 1);
    const sma = slice.reduce((a, b) => a + b, 0) / period;
    const md = slice.reduce((a, b) => a + Math.abs(b - sma), 0) / period;
    out.push(md === 0 ? 0 : +((tp[i] - sma) / (0.015 * md)).toFixed(2));
  }
  return out;
}

// Williams %R (range -100 .. 0)
export function calcWilliamsR(highs: number[], lows: number[], closes: number[], period = 14): (number | null)[] {
  const out: (number | null)[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) { out.push(null); continue; }
    let hi = -Infinity, lo = Infinity;
    for (let j = i - period + 1; j <= i; j++) {
      if (highs[j] > hi) hi = highs[j];
      if (lows[j]  < lo) lo = lows[j];
    }
    if (hi === lo) { out.push(-50); continue; }
    out.push(+(((hi - closes[i]) / (hi - lo)) * -100).toFixed(2));
  }
  return out;
}

// Money Flow Index
export function calcMFI(
  highs: number[], lows: number[], closes: number[], volumes: number[], period = 14,
): (number | null)[] {
  const tp = closes.map((c, i) => (highs[i] + lows[i] + c) / 3);
  const mf = tp.map((t, i) => t * (volumes[i] ?? 0));
  const out: (number | null)[] = closes.map(() => null);
  for (let i = period; i < closes.length; i++) {
    let pos = 0, neg = 0;
    for (let j = i - period + 1; j <= i; j++) {
      if (tp[j] > tp[j - 1]) pos += mf[j];
      else if (tp[j] < tp[j - 1]) neg += mf[j];
    }
    if (pos === 0 && neg === 0) { out[i] = 50; continue; }
    if (neg === 0) { out[i] = 100; continue; }
    const mr = pos / neg;
    out[i] = +(100 - 100 / (1 + mr)).toFixed(2);
  }
  return out;
}

// On-Balance Volume
export function calcOBV(closes: number[], volumes: number[]): (number | null)[] {
  const out: (number | null)[] = [];
  let obv = 0;
  for (let i = 0; i < closes.length; i++) {
    if (i === 0) { out.push(0); continue; }
    const v = volumes[i] ?? 0;
    if (closes[i] > closes[i - 1]) obv += v;
    else if (closes[i] < closes[i - 1]) obv -= v;
    out.push(obv);
  }
  return out;
}

// Rate of Change (%)
export function calcROC(closes: number[], period = 12): (number | null)[] {
  const out: (number | null)[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (i < period) { out.push(null); continue; }
    const prev = closes[i - period];
    out.push(prev !== 0 ? +(((closes[i] - prev) / prev) * 100).toFixed(2) : null);
  }
  return out;
}

// Awesome Oscillator: SMA(median, 5) - SMA(median, 34)
export function calcAO(highs: number[], lows: number[]): (number | null)[] {
  const med = highs.map((h, i) => (h + lows[i]) / 2);
  const sma5  = calcSMA(med, 5);
  const sma34 = calcSMA(med, 34);
  return med.map((_, i) =>
    sma5[i] !== null && sma34[i] !== null
      ? +((sma5[i] as number) - (sma34[i] as number)).toFixed(4)
      : null,
  );
}

// Chaikin Money Flow
export function calcCMF(
  highs: number[], lows: number[], closes: number[], volumes: number[], period = 20,
): (number | null)[] {
  const mfm = closes.map((c, i) => {
    const range = highs[i] - lows[i];
    return range === 0 ? 0 : ((c - lows[i]) - (highs[i] - c)) / range;
  });
  const mfv = mfm.map((m, i) => m * (volumes[i] ?? 0));
  const out: (number | null)[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) { out.push(null); continue; }
    let sumMfv = 0, sumV = 0;
    for (let j = i - period + 1; j <= i; j++) { sumMfv += mfv[j]; sumV += (volumes[j] ?? 0); }
    out.push(sumV === 0 ? 0 : +(sumMfv / sumV).toFixed(4));
  }
  return out;
}

// TRIX — 1-period ROC of triple-smoothed EMA, scaled to %
export function calcTRIX(closes: number[], period = 14): (number | null)[] {
  const out: (number | null)[] = closes.map(() => null);
  const e1 = calcEMA(closes, period);
  const start1 = e1.findIndex(v => v !== null);
  if (start1 < 0) return out;
  const e1sub = e1.slice(start1).map(v => v as number);
  const e2 = calcEMA(e1sub, period);
  const start2 = e2.findIndex(v => v !== null);
  if (start2 < 0) return out;
  const e2sub = e2.slice(start2).map(v => v as number);
  const e3 = calcEMA(e2sub, period);
  for (let k = 1; k < e3.length; k++) {
    if (e3[k] === null || e3[k - 1] === null || (e3[k - 1] as number) === 0) continue;
    const v = ((e3[k] as number) - (e3[k - 1] as number)) / (e3[k - 1] as number) * 100;
    out[start1 + start2 + k] = +v.toFixed(4);
  }
  return out;
}

// ADX with +DI / -DI (Wilder)
export function calcADX(
  highs: number[], lows: number[], closes: number[], period = 14,
): { adx: (number | null)[]; plusDI: (number | null)[]; minusDI: (number | null)[] } {
  const n = closes.length;
  const tr: number[] = [], pDM: number[] = [], mDM: number[] = [];
  for (let i = 0; i < n; i++) {
    if (i === 0) { tr.push(highs[i] - lows[i]); pDM.push(0); mDM.push(0); continue; }
    const upMove   = highs[i] - highs[i - 1];
    const downMove = lows[i - 1] - lows[i];
    pDM.push(upMove > downMove   && upMove   > 0 ? upMove   : 0);
    mDM.push(downMove > upMove   && downMove > 0 ? downMove : 0);
    tr.push(Math.max(
      highs[i] - lows[i],
      Math.abs(highs[i] - closes[i - 1]),
      Math.abs(lows[i]  - closes[i - 1]),
    ));
  }
  // Wilder smoothing (running sum, not average)
  const wilder = (arr: number[]): number[] => {
    const out = new Array(arr.length).fill(0);
    if (arr.length < period) return out;
    let s = 0;
    for (let i = 0; i < period; i++) s += arr[i];
    out[period - 1] = s;
    for (let i = period; i < arr.length; i++) {
      out[i] = out[i - 1] - out[i - 1] / period + arr[i];
    }
    return out;
  };
  const trS  = wilder(tr);
  const pDMs = wilder(pDM);
  const mDMs = wilder(mDM);
  const plusDI:  (number | null)[] = closes.map(() => null);
  const minusDI: (number | null)[] = closes.map(() => null);
  const dx:      (number | null)[] = closes.map(() => null);
  for (let i = period - 1; i < n; i++) {
    if (trS[i] === 0) { plusDI[i] = 0; minusDI[i] = 0; dx[i] = 0; continue; }
    const pDi = (pDMs[i] / trS[i]) * 100;
    const mDi = (mDMs[i] / trS[i]) * 100;
    plusDI[i]  = +pDi.toFixed(2);
    minusDI[i] = +mDi.toFixed(2);
    dx[i] = (pDi + mDi) === 0 ? 0 : +(Math.abs(pDi - mDi) / (pDi + mDi) * 100).toFixed(2);
  }
  // ADX = Wilder smoothing of DX over period
  const adx: (number | null)[] = closes.map(() => null);
  const firstDx = dx.findIndex(v => v !== null);
  if (firstDx < 0) return { adx, plusDI, minusDI };
  let acc = 0, count = 0, started = false;
  for (let i = firstDx; i < n; i++) {
    if (dx[i] === null) continue;
    if (!started) {
      acc += dx[i] as number;
      count++;
      if (count === period) {
        acc /= period;
        adx[i] = +acc.toFixed(2);
        started = true;
      }
    } else {
      acc = (acc * (period - 1) + (dx[i] as number)) / period;
      adx[i] = +acc.toFixed(2);
    }
  }
  return { adx, plusDI, minusDI };
}
