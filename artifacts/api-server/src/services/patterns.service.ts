import { YahooService } from "./yahoo.service.js";
import { NseService } from "./nse.service.js";
import { calculateEMA, calculateSMA, calculateRSI, calculateMACD, calculateBollingerBands, calculateATR, OHLCV } from "./indicators.js";
import { NIFTY100, MIDCAP, SMALLCAP } from "../lib/universe.js";

export interface ChartPattern {
  symbol: string; pattern: string; patternType: string; signal: string;
  confidence: number; detectedAt: string; currentPrice: number;
  targetPrice?: number; stopLoss?: number; description: string;
  timeframe: string; universe: string; category: string;
}

let cachedPatterns: ChartPattern[] = [];
let lastScanTime = "";

// ─── Helpers ────────────────────────────────────────────────────────────────

function body(c: OHLCV)  { return Math.abs(c.close - c.open); }
function upper(c: OHLCV) { return c.high - Math.max(c.open, c.close); }
function lower(c: OHLCV) { return Math.min(c.open, c.close) - c.low; }
function range(c: OHLCV) { return c.high - c.low; }
function isBull(c: OHLCV){ return c.close > c.open; }
function isBear(c: OHLCV){ return c.close < c.open; }
function isDoji(c: OHLCV){ return body(c) <= range(c) * 0.1; }
function mid(c: OHLCV)   { return (c.open + c.close) / 2; }

function mk(
  symbol: string, universe: string,
  pattern: string, patternType: "BULLISH"|"BEARISH"|"NEUTRAL",
  signal: "CALL"|"PUT"|"WAIT",
  confidence: number, price: number,
  description: string, category: string,
  tgt?: number, sl?: number
): ChartPattern {
  return {
    symbol, pattern, patternType, signal, confidence,
    detectedAt: new Date().toISOString(), currentPrice: price,
    targetPrice: tgt, stopLoss: sl,
    description, timeframe: "1D", universe, category,
  };
}

// Find local pivot highs/lows over a window
function pivots(arr: number[], w = 5) {
  const highs: number[] = [], lows: number[] = [];
  for (let i = w; i < arr.length - w; i++) {
    const seg = arr.slice(i - w, i + w + 1);
    if (arr[i] === Math.max(...seg)) highs.push(arr[i]);
    if (arr[i] === Math.min(...seg)) lows.push(arr[i]);
  }
  return { highs, lows };
}

// Last N pivot highs / lows in order
function lastPivots(arr: number[], w = 5, n = 4) {
  const highs: { i: number; v: number }[] = [];
  const lows:  { i: number; v: number }[] = [];
  for (let i = w; i < arr.length - w; i++) {
    const seg = arr.slice(i - w, i + w + 1);
    if (arr[i] === Math.max(...seg)) highs.push({ i, v: arr[i] });
    if (arr[i] === Math.min(...seg)) lows.push({ i, v: arr[i] });
  }
  return { highs: highs.slice(-n), lows: lows.slice(-n) };
}

export class PatternsService {
  constructor(private yahoo: YahooService, private nse: NseService) {}

  async getPatterns(universe?: string, signal?: string, category?: string): Promise<any> {
    let patterns = cachedPatterns;
    if (patterns.length === 0) patterns = await this.runScan();
    if (universe) patterns = patterns.filter(p => p.universe === universe.toUpperCase());
    if (signal)   patterns = patterns.filter(p => p.signal   === signal.toUpperCase());
    if (category) patterns = patterns.filter(p => p.category?.toLowerCase().includes(category.toLowerCase()));
    const calls = patterns.filter(p => p.signal === "CALL");
    const puts  = patterns.filter(p => p.signal === "PUT");
    const categories = [...new Set(cachedPatterns.map(p => p.category))];
    return {
      lastScanTime: lastScanTime || new Date().toISOString(),
      totalPatterns: patterns.length, callSignals: calls.length, putSignals: puts.length,
      categories, patterns: patterns.slice(0, 100),
      topCalls: calls.slice(0, 15), topPuts: puts.slice(0, 15),
    };
  }

  async triggerScan(): Promise<any> {
    const patterns = await this.runScan();
    return {
      message: "Scan complete", totalFound: patterns.length,
      callSignals: patterns.filter(p => p.signal === "CALL").length,
      putSignals:  patterns.filter(p => p.signal === "PUT").length,
      patterns: patterns.slice(0, 30),
    };
  }

  private async runScan(): Promise<ChartPattern[]> {
    const all: ChartPattern[] = [];
    const universe: [string[], string][] = [
      [NIFTY100.slice(0, 15), "NIFTY100"],
      [MIDCAP.slice(0, 8),    "MIDCAP"],
      [SMALLCAP.slice(0, 5),  "SMALLCAP"],
    ];
    for (const [syms, u] of universe) {
      for (const sym of syms) {
        try {
          const h = await this.yahoo.getHistoricalData(sym, 90);
          if (h.length < 30) continue;
          all.push(...this.detect(sym, h, u));
          await new Promise(r => setTimeout(r, 400));
        } catch (_) {}
      }
    }
    cachedPatterns = all.sort((a, b) => b.confidence - a.confidence);
    lastScanTime = new Date().toISOString();
    return cachedPatterns;
  }

  private detect(symbol: string, history: any[], universe: string): ChartPattern[] {
    const ohlcv: OHLCV[] = history;
    const n = ohlcv.length;
    const closes  = ohlcv.map(d => d.close);
    const highs   = ohlcv.map(d => d.high);
    const lows    = ohlcv.map(d => d.low);
    const volumes = ohlcv.map(d => d.volume);
    const price   = closes[n - 1];

    const rsiArr  = calculateRSI(closes, 14);
    const lr      = rsiArr[rsiArr.length - 1];
    const rsiPrev = rsiArr[rsiArr.length - 2];

    const ema9   = calculateEMA(closes, 9);
    const ema20  = calculateEMA(closes, 20);
    const ema50  = calculateEMA(closes, 50);
    const ema200 = calculateEMA(closes, 200);

    const le9   = ema9[ema9.length - 1];
    const le20  = ema20[ema20.length - 1];
    const le50  = ema50[ema50.length - 1];
    const le200 = ema200.length ? ema200[ema200.length - 1] : 0;

    const pe20  = ema20.length >= 2 ? ema20[ema20.length - 2] : le20;
    const pe50  = ema50.length >= 2 ? ema50[ema50.length - 2] : le50;
    const pe200 = ema200.length >= 2 ? ema200[ema200.length - 2] : le200;

    const macdData = calculateMACD(closes);
    const macd     = macdData.macd;
    const sig      = macdData.signal;
    const hist     = macdData.histogram;
    const lm = macd[macd.length - 1], ls = sig[sig.length - 1];
    const pm = macd[macd.length - 2], ps = sig[sig.length - 2];
    const lh = hist[hist.length - 1], ph = hist[hist.length - 2];

    const bb    = calculateBollingerBands(closes, 20);
    const lbbu  = bb.upper[bb.upper.length - 1];
    const lbbm  = bb.middle[bb.middle.length - 1];
    const lbbl  = bb.lower[bb.lower.length - 1];
    const pbbu  = bb.upper[bb.upper.length - 2];
    const pbbl  = bb.lower[bb.lower.length - 2];

    const atrArr = calculateATR(ohlcv, 14);
    const atr    = atrArr[atrArr.length - 1] || price * 0.015;

    const c0 = ohlcv[n - 1], c1 = ohlcv[n - 2], c2 = ohlcv[n - 3], c3 = ohlcv[n - 4];
    const avgVol = volumes.slice(-20).reduce((a, b) => a + b, 0) / 20;

    const out: ChartPattern[] = [];
    const add = (p: ChartPattern) => out.push(p);

    // ══════════════════════════════════════════════════════════════════
    // CATEGORY 1 — SINGLE CANDLESTICK PATTERNS
    // ══════════════════════════════════════════════════════════════════

    // Hammer (bullish reversal at bottom)
    if (lower(c0) > 2 * body(c0) && upper(c0) < 0.5 * body(c0) && lr < 50) {
      add(mk(symbol, universe, "Hammer", "BULLISH", "CALL", 72, price,
        "Long lower wick signals strong buying pressure — bullish reversal likely",
        "Candlestick", price * 1.04, price - atr));
    }

    // Inverted Hammer (bullish if after downtrend)
    if (upper(c0) > 2 * body(c0) && lower(c0) < 0.5 * body(c0) && lr < 45 && isBull(c0)) {
      add(mk(symbol, universe, "Inverted Hammer", "BULLISH", "CALL", 65, price,
        "Buyers pushed up after a downtrend — potential bullish reversal",
        "Candlestick", price * 1.03, price - atr));
    }

    // Shooting Star (bearish after uptrend)
    if (upper(c0) > 2 * body(c0) && lower(c0) < 0.5 * body(c0) && lr > 55) {
      add(mk(symbol, universe, "Shooting Star", "BEARISH", "PUT", 72, price,
        "Long upper wick after rally — sellers overwhelmed buyers, bearish reversal signal",
        "Candlestick", undefined, price + atr));
    }

    // Hanging Man (bearish after uptrend)
    if (lower(c0) > 2 * body(c0) && upper(c0) < 0.5 * body(c0) && lr > 60 && isBear(c0)) {
      add(mk(symbol, universe, "Hanging Man", "BEARISH", "PUT", 68, price,
        "Hammer shape at the top of an uptrend — distribution signal, bearish reversal",
        "Candlestick", undefined, price + atr));
    }

    // Standard Doji
    if (isDoji(c0) && range(c0) > atr * 0.5) {
      add(mk(symbol, universe, "Doji", "NEUTRAL", "WAIT", 55, price,
        "Open ≈ Close — market indecision. Watch next candle for direction confirmation",
        "Candlestick"));
    }

    // Dragonfly Doji (bullish)
    if (isDoji(c0) && lower(c0) > range(c0) * 0.7) {
      add(mk(symbol, universe, "Dragonfly Doji", "BULLISH", "CALL", 70, price,
        "Long lower wick, no upper wick — buyers strongly rejected the lows, bullish",
        "Candlestick", price * 1.03, price - atr));
    }

    // Gravestone Doji (bearish)
    if (isDoji(c0) && upper(c0) > range(c0) * 0.7) {
      add(mk(symbol, universe, "Gravestone Doji", "BEARISH", "PUT", 70, price,
        "Long upper wick, no lower wick — sellers pushed price back from highs, bearish",
        "Candlestick", undefined, price + atr));
    }

    // Spinning Top (indecision)
    if (!isDoji(c0) && body(c0) < range(c0) * 0.3 && lower(c0) > body(c0) && upper(c0) > body(c0)) {
      add(mk(symbol, universe, "Spinning Top", "NEUTRAL", "WAIT", 50, price,
        "Small body with long wicks — indecision between bulls and bears",
        "Candlestick"));
    }

    // Bullish Marubozu (strong bull candle, no wicks)
    if (isBull(c0) && body(c0) > range(c0) * 0.9 && body(c0) > atr * 1.2) {
      add(mk(symbol, universe, "Bullish Marubozu", "BULLISH", "CALL", 75, price,
        "Full bull candle, no wicks — complete buyer control, strong momentum",
        "Candlestick", price * 1.03, price - atr));
    }

    // Bearish Marubozu
    if (isBear(c0) && body(c0) > range(c0) * 0.9 && body(c0) > atr * 1.2) {
      add(mk(symbol, universe, "Bearish Marubozu", "BEARISH", "PUT", 75, price,
        "Full bear candle, no wicks — complete seller control, strong downward momentum",
        "Candlestick", undefined, price + atr));
    }

    // Inside Bar (consolidation before breakout)
    if (c0.high < c1.high && c0.low > c1.low && body(c0) < body(c1) * 0.6) {
      add(mk(symbol, universe, "Inside Bar", "NEUTRAL", "WAIT", 60, price,
        "Price consolidating inside previous candle range — breakout setup forming",
        "Candlestick"));
    }

    // Outside Bar / Engulfing Range (high volatility)
    if (c0.high > c1.high && c0.low < c1.low && body(c0) > body(c1) * 1.5) {
      add(mk(symbol, universe, "Outside Bar", "NEUTRAL", "WAIT", 58, price,
        "Candle completely engulfs prior range — high volatility, wait for direction",
        "Candlestick"));
    }

    // ══════════════════════════════════════════════════════════════════
    // CATEGORY 2 — TWO-CANDLE PATTERNS
    // ══════════════════════════════════════════════════════════════════

    // Bullish Engulfing
    if (isBear(c1) && isBull(c0) && c0.open < c1.close && c0.close > c1.open) {
      add(mk(symbol, universe, "Bullish Engulfing", "BULLISH", "CALL", 78, price,
        "Green candle fully engulfs previous red candle — strong bullish reversal",
        "Two-Candle", price * 1.04, price - atr));
    }

    // Bearish Engulfing
    if (isBull(c1) && isBear(c0) && c0.open > c1.close && c0.close < c1.open) {
      add(mk(symbol, universe, "Bearish Engulfing", "BEARISH", "PUT", 78, price,
        "Red candle fully engulfs previous green candle — strong bearish reversal",
        "Two-Candle", undefined, price + atr));
    }

    // Bullish Harami
    if (isBear(c1) && isBull(c0) && c0.open > c1.close && c0.close < c1.open && body(c0) < body(c1) * 0.6) {
      add(mk(symbol, universe, "Bullish Harami", "BULLISH", "CALL", 65, price,
        "Small green candle inside large red candle — bearish momentum slowing",
        "Two-Candle", price * 1.03, price - atr));
    }

    // Bearish Harami
    if (isBull(c1) && isBear(c0) && c0.open < c1.close && c0.close > c1.open && body(c0) < body(c1) * 0.6) {
      add(mk(symbol, universe, "Bearish Harami", "BEARISH", "PUT", 65, price,
        "Small red candle inside large green candle — bullish momentum slowing",
        "Two-Candle", undefined, price + atr));
    }

    // Piercing Line (bullish reversal)
    if (isBear(c1) && isBull(c0) && c0.open < c1.low && c0.close > mid(c1) && c0.close < c1.open) {
      add(mk(symbol, universe, "Piercing Line", "BULLISH", "CALL", 70, price,
        "Green candle opens below prior low but closes above its midpoint — bullish reversal",
        "Two-Candle", price * 1.03, price - atr));
    }

    // Dark Cloud Cover (bearish reversal)
    if (isBull(c1) && isBear(c0) && c0.open > c1.high && c0.close < mid(c1) && c0.close > c1.open) {
      add(mk(symbol, universe, "Dark Cloud Cover", "BEARISH", "PUT", 70, price,
        "Red candle opens above prior high but closes below its midpoint — bearish reversal",
        "Two-Candle", undefined, price + atr));
    }

    // Tweezer Bottom (bullish)
    if (Math.abs(c0.low - c1.low) / price < 0.003 && isBear(c1) && isBull(c0) && lr < 55) {
      add(mk(symbol, universe, "Tweezer Bottom", "BULLISH", "CALL", 68, price,
        "Two candles share the same low — strong support confirmed, bullish reversal",
        "Two-Candle", price * 1.03, price - atr));
    }

    // Tweezer Top (bearish)
    if (Math.abs(c0.high - c1.high) / price < 0.003 && isBull(c1) && isBear(c0) && lr > 55) {
      add(mk(symbol, universe, "Tweezer Top", "BEARISH", "PUT", 68, price,
        "Two candles share the same high — strong resistance confirmed, bearish reversal",
        "Two-Candle", undefined, price + atr));
    }

    // ══════════════════════════════════════════════════════════════════
    // CATEGORY 3 — THREE-CANDLE PATTERNS
    // ══════════════════════════════════════════════════════════════════

    // Morning Star (bullish)
    if (isBear(c2) && body(c1) < body(c2) * 0.4 && isBull(c0) && c0.close > mid(c2) && lr < 55) {
      add(mk(symbol, universe, "Morning Star", "BULLISH", "CALL", 82, price,
        "Three-candle bullish reversal: large red → small indecision → strong green",
        "Three-Candle", price * 1.05, price - atr * 1.5));
    }

    // Evening Star (bearish)
    if (isBull(c2) && body(c1) < body(c2) * 0.4 && isBear(c0) && c0.close < mid(c2) && lr > 55) {
      add(mk(symbol, universe, "Evening Star", "BEARISH", "PUT", 82, price,
        "Three-candle bearish reversal: large green → small indecision → strong red",
        "Three-Candle", undefined, price + atr * 1.5));
    }

    // Morning Doji Star (stronger morning star)
    if (isBear(c2) && isDoji(c1) && isBull(c0) && c0.close > mid(c2)) {
      add(mk(symbol, universe, "Morning Doji Star", "BULLISH", "CALL", 84, price,
        "Strongest bullish reversal: bearish candle → doji (indecision) → strong green breakout",
        "Three-Candle", price * 1.05, price - atr * 1.5));
    }

    // Evening Doji Star (stronger evening star)
    if (isBull(c2) && isDoji(c1) && isBear(c0) && c0.close < mid(c2)) {
      add(mk(symbol, universe, "Evening Doji Star", "BEARISH", "PUT", 84, price,
        "Strongest bearish reversal: bullish candle → doji (indecision) → strong red breakdown",
        "Three-Candle", undefined, price + atr * 1.5));
    }

    // Three White Soldiers (bullish continuation)
    if (isBull(c2) && isBull(c1) && isBull(c0) &&
        c0.close > c1.close && c1.close > c2.close &&
        body(c0) > atr * 0.7 && body(c1) > atr * 0.7 && body(c2) > atr * 0.7) {
      add(mk(symbol, universe, "Three White Soldiers", "BULLISH", "CALL", 80, price,
        "Three consecutive strong green candles — relentless buying, strong bullish trend",
        "Three-Candle", price * 1.05, price - atr * 2));
    }

    // Three Black Crows (bearish continuation)
    if (isBear(c2) && isBear(c1) && isBear(c0) &&
        c0.close < c1.close && c1.close < c2.close &&
        body(c0) > atr * 0.7 && body(c1) > atr * 0.7 && body(c2) > atr * 0.7) {
      add(mk(symbol, universe, "Three Black Crows", "BEARISH", "PUT", 80, price,
        "Three consecutive strong red candles — relentless selling, strong bearish trend",
        "Three-Candle", undefined, price + atr * 2));
    }

    // Three Inside Up (bullish, after harami)
    if (isBear(c2) && isBull(c1) && c1.open > c2.close && c1.close < c2.open &&
        isBull(c0) && c0.close > c2.open) {
      add(mk(symbol, universe, "Three Inside Up", "BULLISH", "CALL", 75, price,
        "Bullish harami confirmed by next green candle closing above the initial red — buy signal",
        "Three-Candle", price * 1.04, price - atr));
    }

    // Three Inside Down (bearish)
    if (isBull(c2) && isBear(c1) && c1.open < c2.close && c1.close > c2.open &&
        isBear(c0) && c0.close < c2.open) {
      add(mk(symbol, universe, "Three Inside Down", "BEARISH", "PUT", 75, price,
        "Bearish harami confirmed by next red candle closing below the initial green — sell signal",
        "Three-Candle", undefined, price + atr));
    }

    // Rising Three Methods (bullish continuation)
    if (n >= 5) {
      const c4 = ohlcv[n - 5];
      if (isBull(c4) && body(c4) > atr * 0.8 &&
          isBear(c3) && isBear(c2) && isBear(c1) &&
          c3.close > c4.close && c1.close < c4.close && c1.close > c4.open &&
          isBull(c0) && c0.close > c4.close) {
        add(mk(symbol, universe, "Rising Three Methods", "BULLISH", "CALL", 78, price,
          "Strong green candle, three small pullback candles, then new green breakout — bullish continuation",
          "Three-Candle", price * 1.05, price - atr * 1.5));
      }

      // Falling Three Methods (bearish continuation)
      if (isBear(c4) && body(c4) > atr * 0.8 &&
          isBull(c3) && isBull(c2) && isBull(c1) &&
          c3.close < c4.close && c1.close > c4.close && c1.close < c4.open &&
          isBear(c0) && c0.close < c4.close) {
        add(mk(symbol, universe, "Falling Three Methods", "BEARISH", "PUT", 78, price,
          "Strong red candle, three small pullback candles, then new red breakdown — bearish continuation",
          "Three-Candle", undefined, price + atr * 1.5));
      }
    }

    // ══════════════════════════════════════════════════════════════════
    // CATEGORY 4 — INDICATOR-BASED PATTERNS
    // ══════════════════════════════════════════════════════════════════

    // RSI Oversold Bounce
    if (lr < 35 && price > le50) {
      add(mk(symbol, universe, "RSI Oversold Bounce", "BULLISH", "CALL", 70, price,
        `RSI ${lr?.toFixed(1)} — deeply oversold while price holds EMA50 support. Bounce likely`,
        "Indicator", price * 1.04, price - atr));
    }

    // RSI Bullish Divergence (price lower low, RSI higher low)
    if (rsiArr.length >= 10) {
      const rLen = rsiArr.length;
      const priceLow1 = Math.min(...closes.slice(-10, -5));
      const priceLow2 = Math.min(...closes.slice(-5));
      const rsiLow1   = Math.min(...rsiArr.slice(-10, -5));
      const rsiLow2   = Math.min(...rsiArr.slice(-5));
      if (priceLow2 < priceLow1 && rsiLow2 > rsiLow1 && lr < 50) {
        add(mk(symbol, universe, "RSI Bullish Divergence", "BULLISH", "CALL", 80, price,
          "Price making lower lows but RSI making higher lows — hidden buying strength, reversal likely",
          "Indicator", price * 1.05, price - atr * 1.5));
      }
    }

    // RSI Overbought
    if (lr > 72) {
      add(mk(symbol, universe, "RSI Overbought", "BEARISH", "PUT", 65, price,
        `RSI ${lr?.toFixed(1)} — extreme overbought zone. Correction likely`,
        "Indicator", undefined, price + atr));
    }

    // RSI Bearish Divergence (price higher high, RSI lower high)
    if (rsiArr.length >= 10) {
      const priceHigh1 = Math.max(...closes.slice(-10, -5));
      const priceHigh2 = Math.max(...closes.slice(-5));
      const rsiHigh1   = Math.max(...rsiArr.slice(-10, -5));
      const rsiHigh2   = Math.max(...rsiArr.slice(-5));
      if (priceHigh2 > priceHigh1 && rsiHigh2 < rsiHigh1 && lr > 55) {
        add(mk(symbol, universe, "RSI Bearish Divergence", "BEARISH", "PUT", 80, price,
          "Price making higher highs but RSI making lower highs — weakening momentum, reversal likely",
          "Indicator", undefined, price + atr * 1.5));
      }
    }

    // MACD Bullish Crossover
    if (pm !== undefined && pm < ps && lm > ls) {
      add(mk(symbol, universe, "MACD Bullish Crossover", "BULLISH", "CALL", 75, price,
        "MACD line just crossed above Signal line — buy signal, momentum turning bullish",
        "Indicator", price * 1.04, price - atr));
    }

    // MACD Bearish Crossover
    if (pm !== undefined && pm > ps && lm < ls) {
      add(mk(symbol, universe, "MACD Bearish Crossover", "BEARISH", "PUT", 75, price,
        "MACD line just crossed below Signal line — sell signal, momentum turning bearish",
        "Indicator", undefined, price + atr));
    }

    // MACD Histogram Expanding (momentum acceleration)
    if (ph !== undefined && lh > 0 && lh > ph && lh > ph * 1.3) {
      add(mk(symbol, universe, "MACD Histogram Expanding (Bull)", "BULLISH", "CALL", 68, price,
        "MACD histogram growing rapidly in positive zone — bullish momentum accelerating",
        "Indicator", price * 1.03, price - atr));
    }
    if (ph !== undefined && lh < 0 && Math.abs(lh) > Math.abs(ph) * 1.3) {
      add(mk(symbol, universe, "MACD Histogram Expanding (Bear)", "BEARISH", "PUT", 68, price,
        "MACD histogram deepening in negative zone — bearish momentum accelerating",
        "Indicator", undefined, price + atr));
    }

    // EMA Golden Cross (20/50)
    if (pe20 < pe50 && le20 > le50) {
      add(mk(symbol, universe, "EMA Golden Cross (20/50)", "BULLISH", "CALL", 82, price,
        "EMA20 just crossed above EMA50 — medium-term trend turning bullish",
        "Indicator", price * 1.05, price - atr * 1.5));
    }

    // EMA Death Cross (20/50)
    if (pe20 > pe50 && le20 < le50) {
      add(mk(symbol, universe, "EMA Death Cross (20/50)", "BEARISH", "PUT", 82, price,
        "EMA20 just crossed below EMA50 — medium-term trend turning bearish",
        "Indicator", undefined, price + atr * 1.5));
    }

    // EMA Golden Cross (50/200)
    if (ema200.length >= 2 && pe50 < pe200 && le50 > le200) {
      add(mk(symbol, universe, "EMA Golden Cross (50/200)", "BULLISH", "CALL", 88, price,
        "EMA50 just crossed above EMA200 — major long-term bull market signal",
        "Indicator", price * 1.08, price - atr * 2));
    }

    // EMA Death Cross (50/200)
    if (ema200.length >= 2 && pe50 > pe200 && le50 < le200) {
      add(mk(symbol, universe, "EMA Death Cross (50/200)", "BEARISH", "PUT", 88, price,
        "EMA50 just crossed below EMA200 — major long-term bear market signal",
        "Indicator", undefined, price + atr * 2));
    }

    // Price above all EMAs (strong bull alignment)
    if (le9 && le20 && le50 && le200 && price > le9 && le9 > le20 && le20 > le50 && le50 > le200) {
      add(mk(symbol, universe, "Bull EMA Alignment (9>20>50>200)", "BULLISH", "CALL", 77, price,
        "Price above all EMAs in perfect bullish order — textbook uptrend structure",
        "Indicator", price * 1.04, le50));
    }

    // Price below all EMAs (strong bear alignment)
    if (le9 && le20 && le50 && le200 && price < le9 && le9 < le20 && le20 < le50 && le50 < le200) {
      add(mk(symbol, universe, "Bear EMA Alignment (9<20<50<200)", "BEARISH", "PUT", 77, price,
        "Price below all EMAs in perfect bearish order — textbook downtrend structure",
        "Indicator", undefined, le50));
    }

    // Bollinger Band Lower Bounce
    if (closes[n - 2] <= pbbl && price > lbbl && isBull(c0)) {
      add(mk(symbol, universe, "Bollinger Band Lower Bounce", "BULLISH", "CALL", 72, price,
        "Price bounced off the lower Bollinger Band — mean reversion buy signal",
        "Indicator", lbbm, price - atr));
    }

    // Bollinger Band Upper Rejection
    if (closes[n - 2] >= pbbu && price < lbbu && isBear(c0)) {
      add(mk(symbol, universe, "Bollinger Band Upper Rejection", "BEARISH", "PUT", 72, price,
        "Price rejected at the upper Bollinger Band — mean reversion sell signal",
        "Indicator", undefined, price + atr));
    }

    // Bollinger Band Squeeze (low volatility → breakout setup)
    const bbWidth    = (lbbu - lbbl) / lbbm;
    const bbWidthAvg = bb.upper.slice(-20).map((u, i) => (u - bb.lower[i]) / bb.middle[i]).reduce((a, b) => a + b, 0) / 20;
    if (bbWidth < bbWidthAvg * 0.6) {
      add(mk(symbol, universe, "Bollinger Band Squeeze", "NEUTRAL", "WAIT", 65, price,
        "Bollinger Bands are unusually narrow — low volatility period signals impending explosive breakout",
        "Indicator"));
    }

    // Bollinger Band Breakout (upper, bullish)
    if (price > lbbu && closes[n - 2] < pbbu && c0.volume > avgVol * 1.3) {
      add(mk(symbol, universe, "Bollinger Band Upper Breakout", "BULLISH", "CALL", 74, price,
        "Price broke above upper Bollinger Band with volume — strong bullish momentum",
        "Indicator", price * 1.04, lbbm));
    }

    // Volume Spike (unusual activity)
    if (c0.volume > avgVol * 2.5 && isBull(c0)) {
      add(mk(symbol, universe, "Bullish Volume Spike", "BULLISH", "CALL", 70, price,
        `Volume ${((c0.volume / avgVol)).toFixed(1)}× average on a green candle — institutional accumulation signal`,
        "Indicator", price * 1.04, price - atr));
    }
    if (c0.volume > avgVol * 2.5 && isBear(c0)) {
      add(mk(symbol, universe, "Bearish Volume Spike", "BEARISH", "PUT", 70, price,
        `Volume ${((c0.volume / avgVol)).toFixed(1)}× average on a red candle — institutional distribution signal`,
        "Indicator", undefined, price + atr));
    }

    // ══════════════════════════════════════════════════════════════════
    // CATEGORY 5 — STRUCTURAL / PRICE ACTION PATTERNS
    // ══════════════════════════════════════════════════════════════════

    const { highs: pivH, lows: pivL } = lastPivots(closes, 5, 5);

    // Double Bottom (W pattern — bullish)
    if (pivL.length >= 2) {
      const l1 = pivL[pivL.length - 2], l2 = pivL[pivL.length - 1];
      if (Math.abs(l1.v - l2.v) / l1.v < 0.03 && l2.i > l1.i + 5 && price > l2.v * 1.01 && lr < 60) {
        add(mk(symbol, universe, "Double Bottom", "BULLISH", "CALL", 82, price,
          "Two equal lows separated by a rally — strong support confirmed, W-pattern breakout",
          "Structure", price * 1.06, l2.v * 0.98));
      }
    }

    // Double Top (M pattern — bearish)
    if (pivH.length >= 2) {
      const h1 = pivH[pivH.length - 2], h2 = pivH[pivH.length - 1];
      if (Math.abs(h1.v - h2.v) / h1.v < 0.03 && h2.i > h1.i + 5 && price < h2.v * 0.99 && lr > 50) {
        add(mk(symbol, universe, "Double Top", "BEARISH", "PUT", 82, price,
          "Two equal highs separated by a pullback — strong resistance confirmed, M-pattern breakdown",
          "Structure", undefined, h2.v * 1.02));
      }
    }

    // Triple Bottom (very strong support)
    if (pivL.length >= 3) {
      const [la, lb, lc2] = pivL.slice(-3);
      if (Math.abs(la.v - lb.v) / la.v < 0.03 && Math.abs(lb.v - lc2.v) / lb.v < 0.03 && price > lc2.v * 1.01) {
        add(mk(symbol, universe, "Triple Bottom", "BULLISH", "CALL", 85, price,
          "Three equal lows — extremely strong support zone, high-probability bullish reversal",
          "Structure", price * 1.08, lc2.v * 0.97));
      }
    }

    // Triple Top (very strong resistance)
    if (pivH.length >= 3) {
      const [ha, hb, hc] = pivH.slice(-3);
      if (Math.abs(ha.v - hb.v) / ha.v < 0.03 && Math.abs(hb.v - hc.v) / hb.v < 0.03 && price < hc.v * 0.99) {
        add(mk(symbol, universe, "Triple Top", "BEARISH", "PUT", 85, price,
          "Three equal highs — extremely strong resistance zone, high-probability bearish reversal",
          "Structure", undefined, hc.v * 1.03));
      }
    }

    // Head and Shoulders (bearish)
    if (pivH.length >= 3 && pivL.length >= 2) {
      const [ls2, head, rs] = pivH.slice(-3);
      const [neck1, neck2]  = pivL.slice(-2);
      const neckline = (neck1.v + neck2.v) / 2;
      if (head.v > ls2.v * 1.02 && head.v > rs.v * 1.02 &&
          Math.abs(ls2.v - rs.v) / head.v < 0.06 &&
          head.i > ls2.i && rs.i > head.i &&
          price < neckline * 1.01 && lr > 40) {
        add(mk(symbol, universe, "Head and Shoulders", "BEARISH", "PUT", 85, price,
          `Classic H&S: head (${head.v.toFixed(0)}) higher than both shoulders. Neckline at ${neckline.toFixed(0)} — bearish breakdown`,
          "Structure", neckline - (head.v - neckline), neckline * 1.01));
      }
    }

    // Inverse Head and Shoulders (bullish)
    if (pivL.length >= 3 && pivH.length >= 2) {
      const [ls2, head, rs] = pivL.slice(-3);
      const [neck1, neck2]  = pivH.slice(-2);
      const neckline = (neck1.v + neck2.v) / 2;
      if (head.v < ls2.v * 0.98 && head.v < rs.v * 0.98 &&
          Math.abs(ls2.v - rs.v) / head.v < 0.06 &&
          head.i > ls2.i && rs.i > head.i &&
          price > neckline * 0.99 && lr < 65) {
        add(mk(symbol, universe, "Inverse Head and Shoulders", "BULLISH", "CALL", 85, price,
          `Inverse H&S: head (${head.v.toFixed(0)}) lower than both shoulders. Neckline at ${neckline.toFixed(0)} — bullish breakout`,
          "Structure", neckline + (neckline - head.v), neckline * 0.99));
      }
    }

    // Ascending Triangle (bullish)
    if (pivH.length >= 2 && pivL.length >= 2) {
      const recentHighs = pivH.slice(-3).map(p => p.v);
      const recentLows  = pivL.slice(-3).map(p => p.v);
      const highFlat    = recentHighs.every(h => Math.abs(h - recentHighs[0]) / recentHighs[0] < 0.025);
      const lowRising   = recentLows.length >= 2 && recentLows[recentLows.length - 1] > recentLows[0] * 1.015;
      if (highFlat && lowRising && price >= recentHighs[0] * 0.98) {
        add(mk(symbol, universe, "Ascending Triangle", "BULLISH", "CALL", 78, price,
          "Flat resistance with rising lows — buyers getting more aggressive, bullish breakout imminent",
          "Structure", recentHighs[0] * 1.05, recentLows[recentLows.length - 1] * 0.98));
      }
    }

    // Descending Triangle (bearish)
    if (pivH.length >= 2 && pivL.length >= 2) {
      const recentHighs = pivH.slice(-3).map(p => p.v);
      const recentLows  = pivL.slice(-3).map(p => p.v);
      const lowFlat     = recentLows.every(l => Math.abs(l - recentLows[0]) / recentLows[0] < 0.025);
      const highFalling = recentHighs.length >= 2 && recentHighs[recentHighs.length - 1] < recentHighs[0] * 0.985;
      if (lowFlat && highFalling && price <= recentLows[0] * 1.02) {
        add(mk(symbol, universe, "Descending Triangle", "BEARISH", "PUT", 78, price,
          "Flat support with falling highs — sellers getting more aggressive, bearish breakdown imminent",
          "Structure", undefined, recentLows[0] * 0.95));
      }
    }

    // Symmetrical Triangle (neutral — breakout either way)
    if (pivH.length >= 2 && pivL.length >= 2) {
      const recentHighs  = pivH.slice(-3).map(p => p.v);
      const recentLows   = pivL.slice(-3).map(p => p.v);
      const highFalling2 = recentHighs[recentHighs.length - 1] < recentHighs[0] * 0.985;
      const lowRising2   = recentLows[recentLows.length - 1]  > recentLows[0] * 1.015;
      if (highFalling2 && lowRising2) {
        add(mk(symbol, universe, "Symmetrical Triangle", "NEUTRAL", "WAIT", 65, price,
          "Converging highs and lows — compression building before a decisive breakout",
          "Structure"));
      }
    }

    // Bull Flag (pullback after strong rally)
    if (n >= 15) {
      const poleHigh = Math.max(...closes.slice(-15, -7));
      const poleLow  = Math.min(...closes.slice(-20, -12));
      const poleSize = poleHigh - poleLow;
      const flagLow  = Math.min(...closes.slice(-7));
      const flagHigh = Math.max(...closes.slice(-7));
      if (poleSize > atr * 3 && (flagHigh - flagLow) < poleSize * 0.4 && price > flagLow && flagHigh < poleHigh * 0.97) {
        add(mk(symbol, universe, "Bull Flag", "BULLISH", "CALL", 78, price,
          "Sharp rally (pole) followed by tight sideways pullback (flag) — continuation pattern, breakout expected",
          "Structure", poleHigh + poleSize * 0.5, flagLow * 0.98));
      }
    }

    // Bear Flag (relief bounce after sharp drop)
    if (n >= 15) {
      const poleLow2  = Math.min(...closes.slice(-15, -7));
      const poleHigh2 = Math.max(...closes.slice(-20, -12));
      const poleSize2 = poleHigh2 - poleLow2;
      const flagLow2  = Math.min(...closes.slice(-7));
      const flagHigh2 = Math.max(...closes.slice(-7));
      if (poleSize2 > atr * 3 && (flagHigh2 - flagLow2) < poleSize2 * 0.4 && price < flagHigh2 && flagLow2 > poleLow2 * 0.97) {
        add(mk(symbol, universe, "Bear Flag", "BEARISH", "PUT", 78, price,
          "Sharp drop (pole) followed by tight sideways bounce (flag) — continuation pattern, breakdown expected",
          "Structure", undefined, poleLow2 - poleSize2 * 0.5));
      }
    }

    // Support Bounce
    if (pivL.length >= 1) {
      const nearestSupport = pivL.map(p => p.v).filter(v => v < price).sort((a, b) => b - a)[0];
      if (nearestSupport && Math.abs(price - nearestSupport) / nearestSupport < 0.02 && isBull(c0)) {
        add(mk(symbol, universe, "Support Bounce", "BULLISH", "CALL", 70, price,
          `Price bouncing off key support at ₹${nearestSupport.toFixed(0)} — buy the dip setup`,
          "Structure", price * 1.03, nearestSupport * 0.98));
      }
    }

    // Resistance Breakout
    if (pivH.length >= 1) {
      const nearestRes = pivH.map(p => p.v).filter(v => v < price * 1.01).sort((a, b) => b - a)[0];
      if (nearestRes && price > nearestRes && Math.abs(price - nearestRes) / nearestRes < 0.02 && c0.volume > avgVol * 1.2) {
        add(mk(symbol, universe, "Resistance Breakout", "BULLISH", "CALL", 76, price,
          `Price breaking above resistance at ₹${nearestRes.toFixed(0)} with volume — breakout play`,
          "Structure", price * 1.05, nearestRes * 0.98));
      }
    }

    // 52-Week High Breakout
    const high52 = Math.max(...closes.slice(-252));
    if (price >= high52 * 0.99 && c0.volume > avgVol * 1.3 && isBull(c0)) {
      add(mk(symbol, universe, "52-Week High Breakout", "BULLISH", "CALL", 80, price,
        "Stock at or near 52-week high with strong volume — momentum breakout, new highs likely",
        "Structure", price * 1.06, price - atr * 2));
    }

    // 52-Week Low Breakdown
    const low52 = Math.min(...closes.slice(-252));
    if (price <= low52 * 1.01 && c0.volume > avgVol * 1.3 && isBear(c0)) {
      add(mk(symbol, universe, "52-Week Low Breakdown", "BEARISH", "PUT", 80, price,
        "Stock at or near 52-week low with high volume — bearish momentum, new lows likely",
        "Structure", undefined, price + atr * 2));
    }

    // Cup and Handle (bullish continuation)
    if (n >= 40) {
      const leftRim   = Math.max(...closes.slice(-40, -25));
      const cupBottom = Math.min(...closes.slice(-30, -10));
      const rightRim  = Math.max(...closes.slice(-15, -5));
      const handleLow = Math.min(...closes.slice(-5));
      if (Math.abs(leftRim - rightRim) / leftRim < 0.03 &&
          cupBottom < leftRim * 0.92 &&
          rightRim > cupBottom * 1.05 &&
          handleLow > cupBottom * 0.97 && handleLow < rightRim * 0.98 &&
          price > handleLow * 1.01) {
        add(mk(symbol, universe, "Cup and Handle", "BULLISH", "CALL", 82, price,
          "Rounded cup with small handle consolidation — classic breakout pattern targeting new highs",
          "Structure", rightRim * 1.08, handleLow * 0.97));
      }
    }

    return out;
  }
}
