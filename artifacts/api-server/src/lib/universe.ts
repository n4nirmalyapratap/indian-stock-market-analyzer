/** Shared stock universe lists — single source of truth for all services */
export const NIFTY100: readonly string[] = Object.freeze([
  "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","ITC","SBIN",
  "BHARTIARTL","KOTAKBANK","BAJFINANCE","AXISBANK","ASIANPAINT","MARUTI","HCLTECH",
  "WIPRO","TITAN","NTPC","SUNPHARMA","TATAMOTORS","LT","COALINDIA","BAJAJ-AUTO",
  "DIVISLAB","CIPLA","DRREDDY","TECHM","HINDALCO",
]);

export const MIDCAP: readonly string[] = Object.freeze([
  "PERSISTENT","COFORGE","MPHASIS","LTTS","KPITTECH","METROPOLIS","IEX","CAMS","CDSL","IRCTC",
]);

export const SMALLCAP: readonly string[] = Object.freeze([
  "TATAELXSI","CYIENT","MASTEK","BIRLASOFT","INFOEDGE",
]);

/** Build a deduplicated symbol list from universe names */
export function buildUniverse(universes: string[]): string[] {
  const out: string[] = [];
  if (universes.includes("NIFTY100"))  out.push(...NIFTY100);
  if (universes.includes("MIDCAP"))    out.push(...MIDCAP);
  if (universes.includes("SMALLCAP"))  out.push(...SMALLCAP);
  return [...new Set(out)];
}

const VALID_UNIVERSE_VALUES = new Set(["NIFTY100", "MIDCAP", "SMALLCAP"]);
export function isValidUniverse(u: unknown): u is string {
  return typeof u === "string" && VALID_UNIVERSE_VALUES.has(u);
}
