export interface OHLCV {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export function calculateEMA(data: number[], period: number): number[] {
  if (data.length < period) return [];
  const k = 2 / (period + 1);
  const ema: number[] = [];
  let sum = 0;
  for (let i = 0; i < period; i++) sum += data[i];
  ema.push(sum / period);
  for (let i = period; i < data.length; i++) {
    ema.push(data[i] * k + ema[ema.length - 1] * (1 - k));
  }
  return ema;
}

export function calculateSMA(data: number[], period: number): number[] {
  const sma: number[] = [];
  for (let i = period - 1; i < data.length; i++) {
    const slice = data.slice(i - period + 1, i + 1);
    sma.push(slice.reduce((a, b) => a + b, 0) / period);
  }
  return sma;
}

export function calculateRSI(data: number[], period: number = 14): number[] {
  if (data.length < period + 1) return [];
  const rsi: number[] = [];
  const gains: number[] = [];
  const losses: number[] = [];

  for (let i = 1; i < data.length; i++) {
    const change = data[i] - data[i - 1];
    gains.push(change > 0 ? change : 0);
    losses.push(change < 0 ? Math.abs(change) : 0);
  }

  let avgGain = gains.slice(0, period).reduce((a, b) => a + b, 0) / period;
  let avgLoss = losses.slice(0, period).reduce((a, b) => a + b, 0) / period;

  for (let i = period; i < gains.length; i++) {
    avgGain = (avgGain * (period - 1) + gains[i]) / period;
    avgLoss = (avgLoss * (period - 1) + losses[i]) / period;
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    rsi.push(100 - 100 / (1 + rs));
  }

  return rsi;
}

export function calculateMACD(data: number[], fast: number = 12, slow: number = 26, signal: number = 9): {
  macd: number[];
  signal: number[];
  histogram: number[];
} {
  const emaFast = calculateEMA(data, fast);
  const emaSlow = calculateEMA(data, slow);
  const diff = slow - fast;
  const macd = emaSlow.map((v, i) => emaFast[i + diff] - v);
  const signalLine = calculateEMA(macd, signal);
  const histogram = signalLine.map((v, i) => macd[i + signal - 1] - v);
  return { macd, signal: signalLine, histogram };
}

export function calculateBollingerBands(data: number[], period: number = 20, stdDev: number = 2): {
  upper: number[];
  middle: number[];
  lower: number[];
} {
  const middle = calculateSMA(data, period);
  const upper: number[] = [];
  const lower: number[] = [];

  middle.forEach((sma, idx) => {
    const slice = data.slice(idx, idx + period);
    const variance = slice.reduce((sum, val) => sum + Math.pow(val - sma, 2), 0) / period;
    const sd = Math.sqrt(variance);
    upper.push(sma + stdDev * sd);
    lower.push(sma - stdDev * sd);
  });

  return { upper, middle, lower };
}

export function calculateATR(ohlcv: OHLCV[], period: number = 14): number[] {
  if (ohlcv.length < 2) return [];
  const trueRanges: number[] = [];

  for (let i = 1; i < ohlcv.length; i++) {
    const high = ohlcv[i].high;
    const low = ohlcv[i].low;
    const prevClose = ohlcv[i - 1].close;
    const tr = Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose));
    trueRanges.push(tr);
  }

  return calculateSMA(trueRanges, period);
}

export function calculateVWAP(ohlcv: OHLCV[]): number {
  let totalTPV = 0;
  let totalVolume = 0;
  ohlcv.forEach(d => {
    const typicalPrice = (d.high + d.low + d.close) / 3;
    totalTPV += typicalPrice * d.volume;
    totalVolume += d.volume;
  });
  return totalVolume === 0 ? 0 : totalTPV / totalVolume;
}

export function detectSupportsResistances(ohlcv: OHLCV[], lookback: number = 20): {
  supports: number[];
  resistances: number[];
} {
  const highs = ohlcv.map(d => d.high);
  const lows = ohlcv.map(d => d.low);
  const supports: number[] = [];
  const resistances: number[] = [];

  for (let i = lookback; i < ohlcv.length - lookback; i++) {
    const localHighs = highs.slice(i - lookback, i + lookback + 1);
    const localLows = lows.slice(i - lookback, i + lookback + 1);

    if (highs[i] === Math.max(...localHighs)) {
      resistances.push(highs[i]);
    }
    if (lows[i] === Math.min(...localLows)) {
      supports.push(lows[i]);
    }
  }

  return { supports: [...new Set(supports)].sort((a, b) => a - b), resistances: [...new Set(resistances)].sort((a, b) => a - b) };
}
