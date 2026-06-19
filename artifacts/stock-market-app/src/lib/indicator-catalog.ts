export interface IndicatorMeta {
  key: string;
  label: string;
  pillColor: string;
  group: string;
  paneOwn: boolean;
  needsVolume?: boolean;
}

export const INDICATOR_CATALOG: IndicatorMeta[] = [
  { key: "ema9",       label: "EMA 9",             pillColor: "#f59e0b", group: "Moving Averages",   paneOwn: false },
  { key: "ema21",      label: "EMA 21",             pillColor: "#6366f1", group: "Moving Averages",   paneOwn: false },
  { key: "ema50",      label: "EMA 50",             pillColor: "#10b981", group: "Moving Averages",   paneOwn: false },
  { key: "ema200",     label: "EMA 200",            pillColor: "#ef4444", group: "Moving Averages",   paneOwn: false },
  { key: "sma20",      label: "SMA 20",             pillColor: "#22d3ee", group: "Moving Averages",   paneOwn: false },
  { key: "sma50",      label: "SMA 50",             pillColor: "#a78bfa", group: "Moving Averages",   paneOwn: false },
  { key: "wma20",      label: "WMA 20",             pillColor: "#facc15", group: "Moving Averages",   paneOwn: false },
  { key: "hma20",      label: "HMA 20",             pillColor: "#a3e635", group: "Moving Averages",   paneOwn: false },
  { key: "vwma20",     label: "VWMA 20",            pillColor: "#fb7185", group: "Moving Averages",   paneOwn: false, needsVolume: true },
  { key: "dema21",     label: "DEMA 21",            pillColor: "#f472b6", group: "Moving Averages",   paneOwn: false },
  { key: "tema21",     label: "TEMA 21",            pillColor: "#fdba74", group: "Moving Averages",   paneOwn: false },
  { key: "bb",         label: "BB (20,2)",          pillColor: "#3b82f6", group: "Channels & Bands",  paneOwn: false },
  { key: "donchian",   label: "Donchian (20)",      pillColor: "#0ea5e9", group: "Channels & Bands",  paneOwn: false },
  { key: "keltner",    label: "Keltner (20)",       pillColor: "#22c55e", group: "Channels & Bands",  paneOwn: false },
  { key: "psar",       label: "PSAR",               pillColor: "#eab308", group: "Trend / Volatility", paneOwn: false },
  { key: "supertrend", label: "Supertrend (10,3)",  pillColor: "#a855f7", group: "Trend / Volatility", paneOwn: false },
  { key: "rsi",        label: "RSI (14)",           pillColor: "#f59e0b", group: "Oscillators",       paneOwn: true },
  { key: "macd",       label: "MACD (12,26,9)",     pillColor: "#2962ff", group: "Oscillators",       paneOwn: true },
  { key: "stoch",      label: "Stoch (14,3)",       pillColor: "#06b6d4", group: "Oscillators",       paneOwn: true },
  { key: "stochrsi",   label: "Stoch RSI",          pillColor: "#84cc16", group: "Oscillators",       paneOwn: true },
  { key: "cci",        label: "CCI (20)",           pillColor: "#c084fc", group: "Oscillators",       paneOwn: true },
  { key: "willr",      label: "Williams %R",        pillColor: "#fb923c", group: "Oscillators",       paneOwn: true },
  { key: "atr",        label: "ATR (14)",           pillColor: "#94a3b8", group: "Oscillators",       paneOwn: true },
  { key: "adx",        label: "ADX (14)",           pillColor: "#f43f5e", group: "Oscillators",       paneOwn: true },
  { key: "mfi",        label: "MFI (14)",           pillColor: "#14b8a6", group: "Oscillators",       paneOwn: true, needsVolume: true },
  { key: "roc",        label: "ROC (12)",           pillColor: "#7dd3fc", group: "Oscillators",       paneOwn: true },
  { key: "trix",       label: "TRIX (14)",          pillColor: "#bef264", group: "Oscillators",       paneOwn: true },
  { key: "ao",         label: "Awesome Osc.",       pillColor: "#e879f9", group: "Oscillators",       paneOwn: true },
  { key: "cmf",        label: "CMF (20)",           pillColor: "#fcd34d", group: "Oscillators",       paneOwn: true, needsVolume: true },
  { key: "obv",        label: "OBV",                pillColor: "#fda4af", group: "Volume",            paneOwn: true },
  // Smart Money Concepts — drawn as chart overlays (zones), not a series. The
  // chart renderer skips this key (it has no compute entry in ChartPanel's
  // IND_CATALOG); ChartPanel watches indicators.has("smc_fvg") to fetch + draw
  // the Fair Value Gap boxes. Daily timeframe only.
  { key: "smc_fvg",       label: "Fair Value Gaps (1D)",    pillColor: "#22c55e", group: "Smart Money",  paneOwn: false },
  { key: "smc_structure", label: "Market Structure (1D)",   pillColor: "#3b82f6", group: "Smart Money",  paneOwn: false },
  { key: "smc_ob",        label: "Order Blocks (1D)",       pillColor: "#f59e0b", group: "Smart Money",  paneOwn: false },
  { key: "smc_pd",        label: "Premium / Discount (1D)", pillColor: "#a855f7", group: "Smart Money",  paneOwn: false },
  { key: "smc_liq",       label: "Liquidity (1D)",          pillColor: "#06b6d4", group: "Smart Money",  paneOwn: false },
];
