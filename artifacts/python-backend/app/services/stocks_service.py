import logging

from .nse_service import NseService
from .yahoo_service import YahooService
from .price_service import PriceService
from .indicators import (
    calculate_ema, calculate_rsi, calculate_macd,
    calculate_bollinger_bands, calculate_atr, detect_sr,
)

logger = logging.getLogger(__name__)


class StocksService:
    def __init__(self, nse: NseService, yahoo: YahooService):
        self.nse   = nse
        self.yahoo = yahoo
        self.price = PriceService(nse, yahoo)

    async def get_stock_details(self, symbol: str) -> dict:
        from . import market_cache_service as _disk

        upper = symbol.upper()
        history = []

        # CLOSE-TRANSITION CONSISTENCY: fetch & seal HISTORY first so that the
        # subsequent quote call sees an EOD-sealed snapshot and overlays the
        # official close. This guarantees `quote.lastPrice` equals
        # `historicalData[-1].close` in the same response, even on the very
        # first request after market close.
        try:
            # PriceService: NSE primary → Yahoo fallback → disk cache when market closed
            h = await self.price.get_historical_data(upper, 300)  # 300 days ≈ 210 trading days — enough for EMA 200
            if h:
                history = h
        except Exception as e:
            logger.warning("Historical data fetch failed for %s: %s", upper, e)

        # Single source of truth for the quote (NSE primary, Yahoo fallback)
        quote_meta = await self.price.get_quote_with_meta(upper)
        if not quote_meta:
            return {"error": f"Stock {upper} not found", "symbol": upper}
        quote_data = quote_meta["quote"]

        closes = [d["close"] for d in history if d.get("close")]
        analysis = self._analyze(history, closes) if len(closes) > 20 else None

        # Pull provenance from disk for the historical block
        hist_meta = _disk.load_with_meta(upper, 300) or {}

        return {
            **quote_data,
            "symbol": upper,
            "technicalAnalysis": analysis,
            "insight": self._build_insight(quote_data, analysis) if analysis else "Insufficient historical data",
            "entryRecommendation": self._build_entry(quote_data, analysis) if analysis else None,
            "historicalData": history[-30:],
            "meta": {
                "source":           quote_meta.get("source"),
                "asOf":             quote_meta.get("asOf"),
                "marketState":      quote_meta.get("marketState"),
                "eodSealed":        bool(quote_meta.get("eodSealed")),
                "eodDate":          quote_meta.get("eodDate"),
                "cacheVersion":     _disk.cache_version(),
                "historySource":    hist_meta.get("source") or "LIVE",
                "historyAsOf":      hist_meta.get("savedAt"),
                "historyEodSealed": bool(hist_meta.get("eodSealed")),
                "historyEodDate":   hist_meta.get("eodDate"),
            },
        }

    def _analyze(self, ohlcv: list[dict], closes: list[float]) -> dict:
        ema9   = calculate_ema(closes, 9)
        ema21  = calculate_ema(closes, 21)
        ema50  = calculate_ema(closes, 50)
        ema200 = calculate_ema(closes, 200)
        rsi    = calculate_rsi(closes, 14)
        macd   = calculate_macd(closes)
        bb     = calculate_bollinger_bands(closes, 20)
        atr    = calculate_atr(ohlcv, 14)
        sr     = detect_sr(ohlcv, 10)

        lc   = closes[-1]
        # When history is too short to compute the indicator, return None so
        # the UI can render "—" instead of pretending the EMA equals 0 (which
        # makes the price look infinitely above the average). Trend defaults
        # to NEUTRAL when EMA50 is missing.
        le9  = ema9[-1]   if ema9   else None
        le21 = ema21[-1]  if ema21  else None
        le50 = ema50[-1]  if ema50  else None
        le200= ema200[-1] if ema200 else None
        lr   = rsi[-1]    if rsi    else None
        lh   = macd["histogram"][-1] if macd["histogram"] else None
        lbu  = bb["upper"][-1]  if bb["upper"]  else None
        lbl  = bb["lower"][-1]  if bb["lower"]  else None
        lbm  = bb["middle"][-1] if bb["middle"] else None
        latr = atr[-1]          if atr          else None

        if le50 is None:
            trend = "NEUTRAL"
        elif lc > le50:
            trend = "STRONG_BULLISH" if (le200 is not None and lc > le200) else "BULLISH"
        elif lc < le50:
            trend = "STRONG_BEARISH" if (le200 is not None and lc < le200) else "BEARISH"
        else:
            trend = "NEUTRAL"

        supports_below    = [s for s in sr["supports"]    if s < lc]
        resistances_above = [r for r in sr["resistances"] if r > lc]
        nearest_support    = supports_below[-1]    if supports_below    else None
        nearest_resistance = resistances_above[0]  if resistances_above else None

        bw = f"{(lbu - lbl) / lbm * 100:.2f}" if (lbm and lbu is not None and lbl is not None) else None
        if lbu is None or lbl is None:
            bb_pos = "UNKNOWN"
        else:
            bb_pos = "ABOVE_UPPER" if lc > lbu else "BELOW_LOWER" if lc < lbl else "INSIDE"

        return {
            "currentPrice": lc,
            "ema": {"ema9": le9, "ema21": le21, "ema50": le50, "ema200": le200},
            "rsi": lr,
            "rsiZone": "OVERBOUGHT" if lr > 70 else "OVERSOLD" if lr < 30 else "NEUTRAL",
            "macd": {
                "value": macd["macd"][-1] if macd["macd"] else 0,
                "signal": macd["signal"][-1] if macd["signal"] else 0,
                "histogram": lh,
                "crossover": "BULLISH" if lh > 0 else "BEARISH",
            },
            "bollingerBands": {
                "upper": lbu, "middle": lbm, "lower": lbl,
                "bandwidth": bw,
                "position": bb_pos,
            },
            "atr": latr,
            "trend": trend,
            "supports": sr["supports"][-3:],
            "resistances": sr["resistances"][:3],
            "nearestSupport": nearest_support,
            "nearestResistance": nearest_resistance,
        }

    def _build_insight(self, quote: dict, analysis: dict) -> str:
        parts = [f"{quote.get('companyName', quote.get('symbol'))} at ₹{analysis['currentPrice']:.2f}"]
        trend_map = {
            "STRONG_BULLISH": "Strong uptrend — above EMA50 and EMA200",
            "BULLISH": "Moderate uptrend — above EMA50",
            "BEARISH": "Downtrend — below EMA50",
            "STRONG_BEARISH": "Strong downtrend — below EMA50 and EMA200",
        }
        if analysis["trend"] in trend_map:
            parts.append(trend_map[analysis["trend"]])
        parts.append(f"RSI at {analysis['rsi']:.1f} — {analysis['rsiZone']}")
        parts.append(f"MACD {analysis['macd']['crossover'].lower()} momentum")
        if analysis.get("nearestSupport"):
            parts.append(f"Support at ₹{analysis['nearestSupport']:.2f}")
        if analysis.get("nearestResistance"):
            parts.append(f"Resistance at ₹{analysis['nearestResistance']:.2f}")
        return ". ".join(parts)

    def _build_entry(self, quote: dict, analysis: dict) -> dict:
        bull = bear = 0
        if "BULL" in analysis["trend"]:
            bull += 1
        else:
            bear += 1
        if analysis["rsi"] < 50:
            bull += 1
        else:
            bear += 1
        if analysis["macd"]["crossover"] == "BULLISH":
            bull += 1
        else:
            bear += 1
        bb_pos = analysis["bollingerBands"]["position"]
        if bb_pos == "BELOW_LOWER":
            bull += 2
        elif bb_pos == "ABOVE_UPPER":
            bear += 2

        total = bull + bear
        signal = "BULLISH" if bull > bear else "BEARISH" if bear > bull else "NEUTRAL"
        confidence = abs(bull - bear) / total * 100 if total else 0

        entry_call = "WAIT"
        if signal == "BULLISH" and confidence > 30 and analysis["rsiZone"] != "OVERBOUGHT":
            entry_call = "ENTRY_CALL"
        elif signal == "BEARISH" and confidence > 30 and analysis["rsiZone"] != "OVERSOLD":
            entry_call = "ENTRY_PUT"

        ns = analysis.get("nearestSupport")
        nr = analysis.get("nearestResistance")
        price = analysis["currentPrice"]
        rr = None
        if nr and ns and (price - ns) > 0:
            rr = f"{(nr - price) / (price - ns):.2f}"

        return {
            "signal": signal,
            "entryCall": entry_call,
            "confidence": f"{confidence:.1f}%",
            "bullishFactors": bull,
            "bearishFactors": bear,
            "targetPrice": nr,
            "stopLoss": ns,
            "riskReward": rr,
            "summary": f"{entry_call.replace('_', ' ')} — {signal} with {confidence:.0f}% confidence",
        }

    async def get_nifty100_stocks(self) -> list[dict]:
        data = await self.nse.get_nifty100()
        if data and data.get("data"):
            return [
                {
                    "symbol": s.get("symbol"),
                    "companyName": (s.get("meta") or {}).get("companyName") or s.get("symbol"),
                    "lastPrice": s.get("lastPrice"),
                    "change": s.get("change"),
                    "pChange": s.get("pChange"),
                    "volume": s.get("totalTradedVolume"),
                    "open": s.get("open"),
                    "dayHigh": s.get("dayHigh"),
                    "dayLow": s.get("dayLow"),
                    "previousClose": s.get("previousClose"),
                }
                for s in data["data"]
            ]
        return []

    async def get_midcap_stocks(self) -> list[dict]:
        data = await self.nse.get_nifty_midcap150()
        if data and data.get("data"):
            return [
                {
                    "symbol": s.get("symbol"),
                    "companyName": (s.get("meta") or {}).get("companyName") or s.get("symbol"),
                    "lastPrice": s.get("lastPrice"),
                    "change": s.get("change"),
                    "pChange": s.get("pChange"),
                    "volume": s.get("totalTradedVolume"),
                }
                for s in data["data"]
            ]
        return []

    async def get_smallcap_stocks(self) -> list[dict]:
        data = await self.nse.get_nifty_smallcap250()
        if data and data.get("data"):
            return [
                {
                    "symbol": s.get("symbol"),
                    "companyName": (s.get("meta") or {}).get("companyName") or s.get("symbol"),
                    "lastPrice": s.get("lastPrice"),
                    "change": s.get("change"),
                    "pChange": s.get("pChange"),
                    "volume": s.get("totalTradedVolume"),
                }
                for s in data["data"]
            ]
        return []
