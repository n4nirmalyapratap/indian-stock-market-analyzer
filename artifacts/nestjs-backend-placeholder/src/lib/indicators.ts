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
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    out.push(+(100 - 100 / (1 + rs)).toFixed(2));
  }
  return out;
}

export function calcMACD(closes: number[], fast = 12, slow = 26, sig = 9): {
  macd: (number | null)[]; signal: (number | null)[]; histogram: (number | null)[];
} {
  const emaFast = calcEMA(closes, fast);
  const emaSlow = calcEMA(closes, slow);
  const macdLine = emaFast.map((f, i) =>
    f !== null && emaSlow[i] !== null ? +(f - emaSlow[i]!).toFixed(4) : null
  );
  const firstNonNull = macdLine.findIndex(v => v !== null);
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
