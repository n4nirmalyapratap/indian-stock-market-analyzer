import asyncio
import logging
import math
import time as _time
from typing import Optional

from .nse_service import NseService
from .yahoo_service import YahooService
from .price_service import PriceService
from .indicators import (
    calculate_ema, calculate_rsi, calculate_macd,
    calculate_bollinger_bands, calculate_atr, detect_sr,
)

logger = logging.getLogger(__name__)

# marketCap / trailing P/E / dividend yield aren't on Yahoo's chart-API quote
# (same limitation that made `open` 0), and P/E + div yield aren't on the Quote
# model at all — so enrich the detail payload from yfinance `.info`. These move
# daily at most → cache a few hours. Best-effort: a miss leaves the fields
# absent (the UI hides those rows). dividendYield is kept as the raw fraction to
# match the Financials tab (both multiply ×100 at display, so they agree).
_KEYSTATS_CACHE: dict[str, tuple[float, dict]] = {}
_KEYSTATS_TTL = 6 * 3600


class StocksService:
    def __init__(self, nse: NseService, yahoo: YahooService):
        self.nse   = nse
        self.yahoo = yahoo
        self.price = PriceService(nse, yahoo)

    async def get_stock_details(self, symbol: str) -> dict:
        from . import market_cache_service as _disk

        upper = symbol.upper()
        history: list[dict] = []
        history_error: Optional[str] = None

        # CLOSE-TRANSITION CONSISTENCY: fetch & seal HISTORY first so that the
        # subsequent quote call sees an EOD-sealed snapshot and overlays the
        # official close. This guarantees `quote.lastPrice` equals
        # `historicalData[-1].close` in the same response, even on the very
        # first request after market close.
        try:
            # PriceService: NSE primary → Yahoo fallback → disk cache when market closed
            # 500 calendar days ≈ 350 trading days — comfortable head-room for
            # EMA-200 plus the ~10 bars of look-back the entry-recommendation
            # uses for crossover confirmation. 300 was the bare minimum and
            # left no slack when Yahoo dropped a few non-trading days.
            h = await self.price.get_historical_data(upper, 500)
            if h:
                history = h
            else:
                history_error = "Provider returned no historical bars"
        except Exception as e:
            logger.warning("Historical data fetch failed for %s: %s", upper, e)
            history_error = f"{type(e).__name__}: {e}"

        # Single source of truth for the quote (NSE primary, Yahoo fallback)
        quote_meta = await self.price.get_quote_with_meta(upper)
        if not quote_meta:
            return {"error": f"Stock {upper} not found", "symbol": upper}
        quote_data = quote_meta["quote"]

        closes = [d["close"] for d in history if d.get("close")]
        analysis = self._analyze(history, closes) if len(closes) > 20 else None

        # Honest analysis-availability surface. The previous payload silently
        # collapsed "fetch failed" and "stock too new" into the same string —
        # callers had no way to distinguish a transient provider outage from
        # a structurally insufficient history.
        if analysis is not None:
            analysis_available  = True
            analysis_error: Optional[str] = None
            insight             = self._build_insight(quote_data, analysis)
            entry_rec           = self._build_entry(quote_data, analysis)
        else:
            analysis_available  = False
            if history_error:
                analysis_error = f"Historical data fetch failed — {history_error}"
            elif len(closes) <= 20:
                analysis_error = f"Insufficient history ({len(closes)} bars; need >20 for EMA/RSI/MACD)"
            else:
                analysis_error = "Insufficient historical data"
            insight   = analysis_error
            entry_rec = None

        # Pull provenance from disk for the historical block
        hist_meta = _disk.load_with_meta(upper, 300) or {}

        return {
            **quote_data,
            "symbol": upper,
            "technicalAnalysis": analysis,
            "analysisAvailable": analysis_available,
            "analysisError":     analysis_error,
            "insight": insight,
            "entryRecommendation": entry_rec,
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

    async def get_key_stats(self, symbol: str) -> dict:
        """Best-effort fundamentals from yfinance `.info` that the chart-API
        quote can't supply: marketCap, trailing P/E, dividend yield and the
        52-week range. Cached a few hours; returns {} on any failure so the
        detail panel simply hides those rows. Served via its own endpoint so
        this (often slow, 2-10s) lookup never blocks the price display.
        dividendYield is the raw fraction to match the Financials tab (both
        ×100 at display time)."""
        sym = symbol.upper()
        cached = _KEYSTATS_CACHE.get(sym)
        if cached and (_time.time() - cached[0]) < _KEYSTATS_TTL:
            return cached[1]

        def _clean(v):
            try:
                if v is None:
                    return None
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    return None
                return v
            except Exception:
                return None

        def _fetch() -> dict:
            import yfinance as yf
            from ..lib.symbol_map import yahoo_candidates
            for tick in yahoo_candidates(sym):
                try:
                    info = yf.Ticker(tick).info or {}
                except Exception:
                    continue
                out = {
                    "marketCap":        _clean(info.get("marketCap")),
                    "trailingPE":       _clean(info.get("trailingPE")),
                    "dividendYield":    _clean(info.get("dividendYield")),
                    "fiftyTwoWeekHigh": _clean(info.get("fiftyTwoWeekHigh")),
                    "fiftyTwoWeekLow":  _clean(info.get("fiftyTwoWeekLow")),
                }
                if any(v is not None for v in out.values()):
                    return out
            return {}

        try:
            stats = await asyncio.to_thread(_fetch)
        except Exception:
            stats = {}
        if stats:
            _KEYSTATS_CACHE[sym] = (_time.time(), stats)
        return stats

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

        # RSI/MACD None-guards — when history is too short to compute the
        # indicator we surface UNKNOWN instead of fabricating an OVERBOUGHT
        # zone from a None comparison (Python 3 raises TypeError on None>70).
        if lr is None:
            rsi_zone = "UNKNOWN"
        else:
            rsi_zone = "OVERBOUGHT" if lr > 70 else "OVERSOLD" if lr < 30 else "NEUTRAL"
        if lh is None:
            macd_cross = "UNKNOWN"
        else:
            macd_cross = "BULLISH" if lh > 0 else "BEARISH"

        return {
            "currentPrice": lc,
            "ema": {"ema9": le9, "ema21": le21, "ema50": le50, "ema200": le200},
            "rsi": round(lr, 2) if lr is not None else None,
            "rsiZone": rsi_zone,
            "macd": {
                "value": macd["macd"][-1] if macd["macd"] else None,
                "signal": macd["signal"][-1] if macd["signal"] else None,
                "histogram": lh,
                "crossover": macd_cross,
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
        # Honest copy when the indicator couldn't be computed — say so instead
        # of crashing with a NoneType format error or printing "RSI at None".
        if analysis.get("rsi") is not None:
            parts.append(f"RSI at {analysis['rsi']:.1f} — {analysis['rsiZone']}")
        else:
            parts.append("RSI unavailable (insufficient history)")
        cross = analysis["macd"]["crossover"]
        if cross != "UNKNOWN":
            parts.append(f"MACD {cross.lower()} momentum")
        if analysis.get("nearestSupport"):
            parts.append(f"Support at ₹{analysis['nearestSupport']:.2f}")
        if analysis.get("nearestResistance"):
            parts.append(f"Resistance at ₹{analysis['nearestResistance']:.2f}")
        return ". ".join(parts)

    def _build_entry(self, quote: dict, analysis: dict) -> dict:
        bull = bear = 0
        if "BULL" in analysis["trend"]:
            bull += 1
        elif "BEAR" in analysis["trend"]:
            bear += 1
        # else NEUTRAL — score neither side rather than silently counting it as bearish

        rsi_val = analysis.get("rsi")
        if rsi_val is not None:
            if rsi_val < 50:
                bull += 1
            else:
                bear += 1
        if analysis["macd"]["crossover"] == "BULLISH":
            bull += 1
        elif analysis["macd"]["crossover"] == "BEARISH":
            bear += 1
        bb_pos = analysis["bollingerBands"]["position"]
        # Bollinger contributes weight 2 — explicitly documented because its
        # vote effectively double-counts vs the EMA / RSI / MACD legs above.
        if bb_pos == "BELOW_LOWER":
            bull += 2
        elif bb_pos == "ABOVE_UPPER":
            bear += 2

        total = bull + bear
        signal = "BULLISH" if bull > bear else "BEARISH" if bear > bull else "NEUTRAL"
        confidence = abs(bull - bear) / total * 100 if total else 0

        entry_call = "WAIT"
        if signal == "BULLISH" and confidence > 30 and analysis["rsiZone"] not in ("OVERBOUGHT", "UNKNOWN"):
            entry_call = "ENTRY_CALL"
        elif signal == "BEARISH" and confidence > 30 and analysis["rsiZone"] not in ("OVERSOLD", "UNKNOWN"):
            entry_call = "ENTRY_PUT"

        ns = analysis.get("nearestSupport")
        nr = analysis.get("nearestResistance")
        price = analysis["currentPrice"]
        rr: Optional[str] = None
        # R/R is only meaningful when the resistance sits *above* the price AND
        # the support sits *below* it. The previous guard only checked the
        # support side, so a resistance that was already breached (nr ≤ price)
        # would yield a zero or negative reward leg dressed up as a real ratio.
        if nr is not None and ns is not None and nr > price > ns:
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
