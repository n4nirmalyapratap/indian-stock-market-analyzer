export interface OHLCV { date: string; open: number; high: number; low: number; close: number; volume: number; }

export function calculateEMA(data: number[], period: number): number[] {
  if (data.length < period) return [];
  const k = 2 / (period + 1);
  const ema: number[] = [data.slice(0, period).reduce((a, b) => a + b, 0) / period];
  for (let i = period; i < data.length; i++) ema.push(data[i] * k + ema[ema.length - 1] * (1 - k));
  return ema;
}

export function calculateSMA(data: number[], period: number): number[] {
  const sma: number[] = [];
  for (let i = period - 1; i < data.length; i++) {
    sma.push(data.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0) / period);
  }
  return sma;
}

export function calculateRSI(data: number[], period = 14): number[] {
  if (data.length < period + 1) return [];
  const gains: number[] = [], losses: number[] = [];
  for (let i = 1; i < data.length; i++) {
    const c = data[i] - data[i - 1];
    gains.push(c > 0 ? c : 0);
    losses.push(c < 0 ? Math.abs(c) : 0);
  }
  let ag = gains.slice(0, period).reduce((a, b) => a + b, 0) / period;
  let al = losses.slice(0, period).reduce((a, b) => a + b, 0) / period;
  const rsi: number[] = [];
  for (let i = period; i < gains.length; i++) {
    ag = (ag * (period - 1) + gains[i]) / period;
    al = (al * (period - 1) + losses[i]) / period;
    rsi.push(100 - 100 / (1 + (al === 0 ? 100 : ag / al)));
  }
  return rsi;
}

export function calculateMACD(data: number[], fast = 12, slow = 26, signal = 9) {
  const ef = calculateEMA(data, fast), es = calculateEMA(data, slow);
  const diff = slow - fast;
  const macd = es.map((v, i) => ef[i + diff] - v);
  const sl = calculateEMA(macd, signal);
  return { macd, signal: sl, histogram: sl.map((v, i) => macd[i + signal - 1] - v) };
}

export function calculateBollingerBands(data: number[], period = 20, sd = 2) {
  const middle = calculateSMA(data, period);
  const upper: number[] = [], lower: number[] = [];
  middle.forEach((sma, idx) => {
    const s = data.slice(idx, idx + period);
    const variance = s.reduce((sum, v) => sum + Math.pow(v - sma, 2), 0) / period;
    const std = Math.sqrt(variance);
    upper.push(sma + sd * std);
    lower.push(sma - sd * std);
  });
  return { upper, middle, lower };
}

export function calculateATR(ohlcv: OHLCV[], period = 14): number[] {
  if (ohlcv.length < 2) return [];
  const trs: number[] = [];
  for (let i = 1; i < ohlcv.length; i++) {
    const h = ohlcv[i].high, l = ohlcv[i].low, pc = ohlcv[i - 1].close;
    trs.push(Math.max(h - l, Math.abs(h - pc), Math.abs(l - pc)));
  }
  return calculateSMA(trs, period);
}

export function detectSR(ohlcv: OHLCV[], lookback = 10) {
  const highs = ohlcv.map(d => d.high), lows = ohlcv.map(d => d.low);
  const supports: number[] = [], resistances: number[] = [];
  for (let i = lookback; i < ohlcv.length - lookback; i++) {
    const lh = highs.slice(i - lookback, i + lookback + 1);
    const ll = lows.slice(i - lookback, i + lookback + 1);
    if (highs[i] === Math.max(...lh)) resistances.push(highs[i]);
    if (lows[i] === Math.min(...ll)) supports.push(lows[i]);
  }
  return { supports: [...new Set(supports)].sort((a, b) => a - b), resistances: [...new Set(resistances)].sort((a, b) => a - b) };
}
