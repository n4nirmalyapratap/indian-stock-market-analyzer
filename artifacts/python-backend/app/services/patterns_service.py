import asyncio
from datetime import datetime
from typing import Optional
from .yahoo_service import YahooService
from .nse_service import NseService
from .indicators import (
    calculate_ema, calculate_sma, calculate_rsi,
    calculate_macd, calculate_bollinger_bands, calculate_atr,
)
from ..lib.universe import NIFTY100, MIDCAP, SMALLCAP

_cached_patterns: list[dict] = []
_last_scan_time: str = ""


def _body(c: dict) -> float:
    return abs(c["close"] - c["open"])

def _upper(c: dict) -> float:
    return c["high"] - max(c["open"], c["close"])

def _lower(c: dict) -> float:
    return min(c["open"], c["close"]) - c["low"]

def _range(c: dict) -> float:
    return c["high"] - c["low"]

def _is_bull(c: dict) -> bool:
    return c["close"] > c["open"]

def _is_bear(c: dict) -> bool:
    return c["close"] < c["open"]

def _is_doji(c: dict) -> bool:
    rng = _range(c)
    return rng > 0 and _body(c) <= rng * 0.1

def _mid(c: dict) -> float:
    return (c["open"] + c["close"]) / 2

def _mk(symbol, universe, pattern, pattern_type, signal, confidence, price, description, category, tgt=None, sl=None):
    return {
        "symbol": symbol, "pattern": pattern, "patternType": pattern_type,
        "signal": signal, "confidence": confidence,
        "detectedAt": datetime.utcnow().isoformat() + "Z",
        "currentPrice": price,
        "targetPrice": tgt, "stopLoss": sl,
        "description": description, "timeframe": "1D",
        "universe": universe, "category": category,
    }


class PatternsService:
    def __init__(self, yahoo: YahooService, nse: NseService):
        self.yahoo = yahoo
        self.nse = nse

    async def get_patterns(self, universe: Optional[str] = None, signal: Optional[str] = None, category: Optional[str] = None) -> dict:
        global _cached_patterns
        patterns = _cached_patterns
        if not patterns:
            patterns = await self.run_scan()
        if universe:
            patterns = [p for p in patterns if p["universe"] == universe.upper()]
        if signal:
            patterns = [p for p in patterns if p["signal"] == signal.upper()]
        if category:
            patterns = [p for p in patterns if category.lower() in (p.get("category") or "").lower()]
        calls = [p for p in patterns if p["signal"] == "CALL"]
        puts  = [p for p in patterns if p["signal"] == "PUT"]
        categories = list({p.get("category") for p in _cached_patterns})
        return {
            "lastScanTime": _last_scan_time or datetime.utcnow().isoformat() + "Z",
            "totalPatterns": len(patterns),
            "callSignals": len(calls),
            "putSignals": len(puts),
            "categories": categories,
            "patterns": patterns[:100],
            "topCalls": calls[:15],
            "topPuts": puts[:15],
        }

    async def trigger_scan(self) -> dict:
        patterns = await self.run_scan()
        calls = [p for p in patterns if p["signal"] == "CALL"]
        puts  = [p for p in patterns if p["signal"] == "PUT"]
        return {
            "message": "Scan complete",
            "totalFound": len(patterns),
            "callSignals": len(calls),
            "putSignals": len(puts),
            "patterns": patterns[:30],
        }

    async def run_scan(self) -> list[dict]:
        global _cached_patterns, _last_scan_time
        all_patterns: list[dict] = []
        universe_map = [
            (NIFTY100[:15], "NIFTY100"),
            (MIDCAP[:8],    "MIDCAP"),
            (SMALLCAP[:5],  "SMALLCAP"),
        ]
        for syms, u in universe_map:
            for sym in syms:
                try:
                    h = await self.yahoo.get_historical_data(sym, 90)
                    if len(h) < 30:
                        continue
                    all_patterns.extend(self._detect(sym, h, u))
                    await asyncio.sleep(0.4)
                except Exception:
                    pass
        _cached_patterns = sorted(all_patterns, key=lambda p: p["confidence"], reverse=True)
        _last_scan_time = datetime.utcnow().isoformat() + "Z"
        return _cached_patterns

    def _detect(self, symbol: str, history: list[dict], universe: str) -> list[dict]:
        ohlcv = history
        n = len(ohlcv)
        closes  = [d["close"] for d in ohlcv]
        highs   = [d["high"]  for d in ohlcv]
        lows    = [d["low"]   for d in ohlcv]
        volumes = [d["volume"] for d in ohlcv]
        price   = closes[-1]

        rsi_arr = calculate_rsi(closes, 14)
        lr      = rsi_arr[-1] if rsi_arr else 50
        rsi_prev= rsi_arr[-2] if len(rsi_arr) >= 2 else lr

        ema9  = calculate_ema(closes, 9)
        ema20 = calculate_ema(closes, 20)
        ema50 = calculate_ema(closes, 50)
        ema200= calculate_ema(closes, 200)

        le9   = ema9[-1]  if ema9  else price
        le20  = ema20[-1] if ema20 else price
        le50  = ema50[-1] if ema50 else price
        le200 = ema200[-1]if ema200 else 0

        pe20  = ema20[-2] if len(ema20) >= 2 else le20
        pe50  = ema50[-2] if len(ema50) >= 2 else le50
        pe200 = ema200[-2]if len(ema200)>= 2 else le200

        macd_data = calculate_macd(closes)
        macd_line = macd_data["macd"]
        sig_line  = macd_data["signal"]
        hist_line = macd_data["histogram"]
        lm = macd_line[-1] if macd_line else 0
        ls = sig_line[-1]  if sig_line  else 0
        pm = macd_line[-2] if len(macd_line) >= 2 else lm
        ps = sig_line[-2]  if len(sig_line)  >= 2 else ls
        lh = hist_line[-1] if hist_line else 0
        ph = hist_line[-2] if len(hist_line) >= 2 else lh

        bb = calculate_bollinger_bands(closes, 20)
        lbbu = bb["upper"][-1]  if bb["upper"]  else price
        lbbm = bb["middle"][-1] if bb["middle"] else price
        lbbl = bb["lower"][-1]  if bb["lower"]  else price
        pbbu = bb["upper"][-2]  if len(bb["upper"]) >= 2  else lbbu
        pbbl = bb["lower"][-2]  if len(bb["lower"]) >= 2  else lbbl

        atr_arr = calculate_atr(ohlcv, 14)
        atr = atr_arr[-1] if atr_arr else price * 0.015

        c0 = ohlcv[n-1]; c1 = ohlcv[n-2]; c2 = ohlcv[n-3]; c3 = ohlcv[n-4]
        avg_vol = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else sum(volumes) / len(volumes)

        out: list[dict] = []
        add = out.append
        mk = _mk

        # ── Single candlestick ────────────────────────────────────────────────
        if _lower(c0) > 2 * _body(c0) and _upper(c0) < 0.5 * _body(c0) and lr < 50:
            add(mk(symbol, universe, "Hammer", "BULLISH", "CALL", 72, price,
                "Long lower wick signals strong buying pressure — bullish reversal likely",
                "Candlestick", price * 1.04, price - atr))

        if _upper(c0) > 2 * _body(c0) and _lower(c0) < 0.5 * _body(c0) and lr < 45 and _is_bull(c0):
            add(mk(symbol, universe, "Inverted Hammer", "BULLISH", "CALL", 65, price,
                "Buyers pushed up after a downtrend — potential bullish reversal",
                "Candlestick", price * 1.03, price - atr))

        if _upper(c0) > 2 * _body(c0) and _lower(c0) < 0.5 * _body(c0) and lr > 55:
            add(mk(symbol, universe, "Shooting Star", "BEARISH", "PUT", 72, price,
                "Long upper wick after rally — sellers overwhelmed buyers, bearish reversal signal",
                "Candlestick", None, price + atr))

        if _lower(c0) > 2 * _body(c0) and _upper(c0) < 0.5 * _body(c0) and lr > 60 and _is_bear(c0):
            add(mk(symbol, universe, "Hanging Man", "BEARISH", "PUT", 68, price,
                "Hammer shape at the top of an uptrend — distribution signal, bearish reversal",
                "Candlestick", None, price + atr))

        if _is_doji(c0) and _range(c0) > atr * 0.5:
            add(mk(symbol, universe, "Doji", "NEUTRAL", "WAIT", 55, price,
                "Open ≈ Close — market indecision. Watch next candle for direction confirmation",
                "Candlestick"))

        if _is_doji(c0) and _lower(c0) > _range(c0) * 0.7:
            add(mk(symbol, universe, "Dragonfly Doji", "BULLISH", "CALL", 70, price,
                "Long lower wick, no upper wick — buyers strongly rejected the lows, bullish",
                "Candlestick", price * 1.03, price - atr))

        if _is_doji(c0) and _upper(c0) > _range(c0) * 0.7:
            add(mk(symbol, universe, "Gravestone Doji", "BEARISH", "PUT", 70, price,
                "Long upper wick, no lower wick — sellers pushed price back from highs, bearish",
                "Candlestick", None, price + atr))

        if not _is_doji(c0) and _body(c0) < _range(c0) * 0.3 and _lower(c0) > _body(c0) and _upper(c0) > _body(c0):
            add(mk(symbol, universe, "Spinning Top", "NEUTRAL", "WAIT", 50, price,
                "Small body with long wicks — indecision between bulls and bears",
                "Candlestick"))

        if _is_bull(c0) and _body(c0) > _range(c0) * 0.9 and _body(c0) > atr * 1.2:
            add(mk(symbol, universe, "Bullish Marubozu", "BULLISH", "CALL", 75, price,
                "Full bull candle, no wicks — complete buyer control, strong momentum",
                "Candlestick", price * 1.03, price - atr))

        if _is_bear(c0) and _body(c0) > _range(c0) * 0.9 and _body(c0) > atr * 1.2:
            add(mk(symbol, universe, "Bearish Marubozu", "BEARISH", "PUT", 75, price,
                "Full bear candle, no wicks — complete seller control, strong downward momentum",
                "Candlestick", None, price + atr))

        if c0["high"] < c1["high"] and c0["low"] > c1["low"] and _body(c0) < _body(c1) * 0.6:
            add(mk(symbol, universe, "Inside Bar", "NEUTRAL", "WAIT", 60, price,
                "Price consolidating inside previous candle range — breakout setup forming",
                "Candlestick"))

        if c0["high"] > c1["high"] and c0["low"] < c1["low"] and _body(c0) > _body(c1) * 1.5:
            add(mk(symbol, universe, "Outside Bar", "NEUTRAL", "WAIT", 58, price,
                "Candle completely engulfs prior range — high volatility, wait for direction",
                "Candlestick"))

        # ── Two candle ───────────────────────────────────────────────────────
        if _is_bear(c1) and _is_bull(c0) and c0["open"] < c1["close"] and c0["close"] > c1["open"]:
            add(mk(symbol, universe, "Bullish Engulfing", "BULLISH", "CALL", 78, price,
                "Green candle fully engulfs previous red candle — strong bullish reversal",
                "Two-Candle", price * 1.04, price - atr))

        if _is_bull(c1) and _is_bear(c0) and c0["open"] > c1["close"] and c0["close"] < c1["open"]:
            add(mk(symbol, universe, "Bearish Engulfing", "BEARISH", "PUT", 78, price,
                "Red candle fully engulfs previous green candle — strong bearish reversal",
                "Two-Candle", None, price + atr))

        if _is_bear(c1) and _is_bull(c0) and c0["open"] > c1["close"] and c0["close"] < c1["open"] and _body(c0) < _body(c1) * 0.6:
            add(mk(symbol, universe, "Bullish Harami", "BULLISH", "CALL", 65, price,
                "Small green candle inside large red candle — bearish momentum slowing",
                "Two-Candle", price * 1.03, price - atr))

        if _is_bull(c1) and _is_bear(c0) and c0["open"] < c1["close"] and c0["close"] > c1["open"] and _body(c0) < _body(c1) * 0.6:
            add(mk(symbol, universe, "Bearish Harami", "BEARISH", "PUT", 65, price,
                "Small red candle inside large green candle — bullish momentum slowing",
                "Two-Candle", None, price + atr))

        if _is_bear(c1) and _is_bull(c0) and c0["open"] < c1["low"] and c0["close"] > _mid(c1) and c0["close"] < c1["open"]:
            add(mk(symbol, universe, "Piercing Line", "BULLISH", "CALL", 70, price,
                "Green candle opens below prior low but closes above its midpoint — bullish reversal",
                "Two-Candle", price * 1.03, price - atr))

        if _is_bull(c1) and _is_bear(c0) and c0["open"] > c1["high"] and c0["close"] < _mid(c1) and c0["close"] > c1["open"]:
            add(mk(symbol, universe, "Dark Cloud Cover", "BEARISH", "PUT", 70, price,
                "Red candle opens above prior high but closes below its midpoint — bearish reversal",
                "Two-Candle", None, price + atr))

        if abs(c0["low"] - c1["low"]) / price < 0.003 and _is_bear(c1) and _is_bull(c0) and lr < 55:
            add(mk(symbol, universe, "Tweezer Bottom", "BULLISH", "CALL", 68, price,
                "Two candles share the same low — strong support confirmed, bullish reversal",
                "Two-Candle", price * 1.03, price - atr))

        if abs(c0["high"] - c1["high"]) / price < 0.003 and _is_bull(c1) and _is_bear(c0) and lr > 55:
            add(mk(symbol, universe, "Tweezer Top", "BEARISH", "PUT", 68, price,
                "Two candles share the same high — strong resistance confirmed, bearish reversal",
                "Two-Candle", None, price + atr))

        # ── Three candle ─────────────────────────────────────────────────────
        if _is_bear(c2) and _body(c1) < _body(c2) * 0.4 and _is_bull(c0) and c0["close"] > _mid(c2) and lr < 55:
            add(mk(symbol, universe, "Morning Star", "BULLISH", "CALL", 82, price,
                "Three-candle bullish reversal: large red → small indecision → strong green",
                "Three-Candle", price * 1.05, price - atr * 1.5))

        if _is_bull(c2) and _body(c1) < _body(c2) * 0.4 and _is_bear(c0) and c0["close"] < _mid(c2) and lr > 55:
            add(mk(symbol, universe, "Evening Star", "BEARISH", "PUT", 82, price,
                "Three-candle bearish reversal: large green → small indecision → strong red",
                "Three-Candle", None, price + atr * 1.5))

        if _is_bear(c2) and _is_doji(c1) and _is_bull(c0) and c0["close"] > _mid(c2):
            add(mk(symbol, universe, "Morning Doji Star", "BULLISH", "CALL", 84, price,
                "Strongest bullish reversal: bearish candle → doji → strong green breakout",
                "Three-Candle", price * 1.05, price - atr * 1.5))

        if _is_bull(c2) and _is_doji(c1) and _is_bear(c0) and c0["close"] < _mid(c2):
            add(mk(symbol, universe, "Evening Doji Star", "BEARISH", "PUT", 84, price,
                "Strongest bearish reversal: bullish candle → doji → strong red breakdown",
                "Three-Candle", None, price + atr * 1.5))

        if (_is_bull(c2) and _is_bull(c1) and _is_bull(c0) and
                c0["close"] > c1["close"] and c1["close"] > c2["close"] and
                _body(c0) > atr * 0.7 and _body(c1) > atr * 0.7 and _body(c2) > atr * 0.7):
            add(mk(symbol, universe, "Three White Soldiers", "BULLISH", "CALL", 80, price,
                "Three consecutive strong green candles — relentless buying, strong bullish trend",
                "Three-Candle", price * 1.05, price - atr * 2))

        if (_is_bear(c2) and _is_bear(c1) and _is_bear(c0) and
                c0["close"] < c1["close"] and c1["close"] < c2["close"] and
                _body(c0) > atr * 0.7 and _body(c1) > atr * 0.7 and _body(c2) > atr * 0.7):
            add(mk(symbol, universe, "Three Black Crows", "BEARISH", "PUT", 80, price,
                "Three consecutive strong red candles — relentless selling, strong bearish trend",
                "Three-Candle", None, price + atr * 2))

        # ── Indicator patterns ────────────────────────────────────────────────
        if lr < 35 and price > le50:
            add(mk(symbol, universe, "RSI Oversold Bounce", "BULLISH", "CALL", 70, price,
                f"RSI {lr:.1f} — deeply oversold while price holds EMA50 support. Bounce likely",
                "Indicator", price * 1.04, price - atr))

        if len(rsi_arr) >= 10:
            price_low1 = min(closes[-10:-5])
            price_low2 = min(closes[-5:])
            rsi_low1   = min(rsi_arr[-10:-5])
            rsi_low2   = min(rsi_arr[-5:])
            if price_low2 < price_low1 and rsi_low2 > rsi_low1 and lr < 50:
                add(mk(symbol, universe, "RSI Bullish Divergence", "BULLISH", "CALL", 80, price,
                    "Price making lower lows but RSI making higher lows — hidden buying strength",
                    "Indicator", price * 1.05, price - atr * 1.5))

        if lr > 72:
            add(mk(symbol, universe, "RSI Overbought", "BEARISH", "PUT", 65, price,
                f"RSI {lr:.1f} — extreme overbought zone. Correction likely",
                "Indicator", None, price + atr))

        if len(rsi_arr) >= 10:
            price_high1 = max(closes[-10:-5])
            price_high2 = max(closes[-5:])
            rsi_high1   = max(rsi_arr[-10:-5])
            rsi_high2   = max(rsi_arr[-5:])
            if price_high2 > price_high1 and rsi_high2 < rsi_high1 and lr > 55:
                add(mk(symbol, universe, "RSI Bearish Divergence", "BEARISH", "PUT", 80, price,
                    "Price making higher highs but RSI making lower highs — weakening momentum",
                    "Indicator", None, price + atr * 1.5))

        if pm < ps and lm > ls:
            add(mk(symbol, universe, "MACD Bullish Crossover", "BULLISH", "CALL", 75, price,
                "MACD line just crossed above Signal line — buy signal, momentum turning bullish",
                "Indicator", price * 1.04, price - atr))

        if pm > ps and lm < ls:
            add(mk(symbol, universe, "MACD Bearish Crossover", "BEARISH", "PUT", 75, price,
                "MACD line just crossed below Signal line — sell signal, momentum turning bearish",
                "Indicator", None, price + atr))

        if lh > 0 and lh > ph and ph != 0 and lh > ph * 1.3:
            add(mk(symbol, universe, "MACD Histogram Expanding (Bull)", "BULLISH", "CALL", 68, price,
                "MACD histogram growing rapidly in positive zone — bullish momentum accelerating",
                "Indicator", price * 1.03, price - atr))

        if lh < 0 and ph != 0 and abs(lh) > abs(ph) * 1.3:
            add(mk(symbol, universe, "MACD Histogram Expanding (Bear)", "BEARISH", "PUT", 68, price,
                "MACD histogram deepening in negative zone — bearish momentum accelerating",
                "Indicator", None, price + atr))

        if pe20 < pe50 and le20 > le50:
            add(mk(symbol, universe, "EMA Golden Cross (20/50)", "BULLISH", "CALL", 82, price,
                "EMA20 just crossed above EMA50 — medium-term trend turning bullish",
                "Indicator", price * 1.05, price - atr * 1.5))

        if pe20 > pe50 and le20 < le50:
            add(mk(symbol, universe, "EMA Death Cross (20/50)", "BEARISH", "PUT", 82, price,
                "EMA20 just crossed below EMA50 — medium-term trend turning bearish",
                "Indicator", None, price + atr * 1.5))

        if len(ema200) >= 2 and pe50 < pe200 and le50 > le200:
            add(mk(symbol, universe, "EMA Golden Cross (50/200)", "BULLISH", "CALL", 88, price,
                "EMA50 just crossed above EMA200 — major trend turning bullish (Golden Cross)",
                "Indicator", price * 1.08, price - atr * 2))

        if len(ema200) >= 2 and pe50 > pe200 and le50 < le200:
            add(mk(symbol, universe, "EMA Death Cross (50/200)", "BEARISH", "PUT", 88, price,
                "EMA50 just crossed below EMA200 — major trend turning bearish (Death Cross)",
                "Indicator", None, price + atr * 2))

        return out
