import asyncio
import time
from datetime import datetime
from typing import Optional
from .yahoo_service import YahooService
from .nse_service import NseService
from .price_service import PriceService
from .indicators import (
    calculate_ema, calculate_sma, calculate_rsi,
    calculate_macd, calculate_bollinger_bands, calculate_atr,
)
from ..lib.universe import NIFTY100, MIDCAP, SMALLCAP

# Pattern scans are expensive (~65 symbols × ~400ms each ≈ 26s) and entirely
# derived from daily OHLCV, so a 30-minute TTL is plenty during market
# hours and avoids the previous behaviour where a single scan would
# pin stale results until process restart.
_PATTERN_CACHE_TTL = 30 * 60  # seconds

_cached_patterns: list[dict] = []
_last_scan_time: str = ""
_last_scan_monotonic: float = 0.0
_last_scan_errors: list[dict] = []
_last_scan_universe_size: int = 0
_last_scan_symbols_scanned: int = 0

# Singleflight lock — prevents N concurrent get_patterns() callers from
# all firing run_scan() simultaneously when the cache is empty/expired.
# Lazy-initialised inside the running event loop to avoid binding to the
# wrong loop at import time.
_scan_lock: Optional[asyncio.Lock] = None


def _get_scan_lock() -> asyncio.Lock:
    global _scan_lock
    if _scan_lock is None:
        _scan_lock = asyncio.Lock()
    return _scan_lock


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


def _adj_conf(
    base: int,
    factors: dict,
    *,
    vol_weight: float = 1.0,
    body_weight: float = 1.0,
    extra: float = 0.0,
) -> int:
    """Adjust a pattern's base confidence using *real* signal strength.

    `base` is the pattern's intrinsic reliability weight (e.g. an Engulfing
    is more reliable than a Spinning Top). Real-time modifiers:
      • Volume bonus  — confirms participation. ±8 max.
      • Body bonus    — strong body relative to ATR confirms conviction. ±6 max.
      • `extra`       — caller-supplied (e.g. RSI distance from threshold).
    Result is clamped to [30, 95] so we never display fake certainty.
    """
    vol_bonus  = max(-8.0, min(8.0, (factors["vol_ratio"]      - 1.0) * 8.0 * vol_weight))
    body_bonus = max(-6.0, min(6.0, (factors["body_strength"] - 1.0) * 6.0 * body_weight))
    return int(round(max(30.0, min(95.0, base + vol_bonus + body_bonus + extra))))


def _mk(symbol, universe, pattern, pattern_type, signal, confidence, price, description, category,
        tgt=None, sl=None, *, scanned_at_iso: Optional[str] = None):
    if scanned_at_iso is None:
        scanned_at_iso = datetime.utcnow().isoformat() + "Z"
    return {
        "symbol": symbol, "pattern": pattern, "patternType": pattern_type,
        "signal": signal, "confidence": confidence,
        # `detectedAt` is the actual scan timestamp — NOT request time. Cached
        # results may be up to _PATTERN_CACHE_TTL seconds old; the response also
        # carries `cacheAgeSeconds` so callers can render that honestly.
        "detectedAt": scanned_at_iso,
        "currentPrice": price,
        "targetPrice": tgt, "stopLoss": sl,
        "description": description, "timeframe": "1D",
        "universe": universe, "category": category,
    }


class PatternsService:
    def __init__(self, yahoo: YahooService, nse: NseService, price: Optional[PriceService] = None):
        self.yahoo = yahoo
        self.nse = nse
        self.price = price or PriceService(nse, yahoo)

    async def get_patterns(self, universe: Optional[str] = None, signal: Optional[str] = None, category: Optional[str] = None) -> dict:
        # Re-scan if cache is empty OR has expired. Without the TTL check
        # the first scan would pin its results until the process restarts.
        # Singleflight: serialise refreshes so concurrent callers share
        # one scan. The cheap TTL check is done outside the lock to avoid
        # serialising the hot path when the cache is fresh.
        if self._cache_is_fresh():
            patterns = _cached_patterns
        else:
            async with _get_scan_lock():
                # Double-checked: another waiter may have refreshed it
                # while we were queued behind the lock.
                if self._cache_is_fresh():
                    patterns = _cached_patterns
                else:
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
        cache_age = max(0, int(time.monotonic() - _last_scan_monotonic)) if _last_scan_monotonic else 0
        return {
            "lastScanTime": _last_scan_time or datetime.utcnow().isoformat() + "Z",
            "scannedAt":    _last_scan_time or datetime.utcnow().isoformat() + "Z",
            "cacheAgeSeconds": cache_age,
            "cacheTtlSeconds": _PATTERN_CACHE_TTL,
            "universeScanned": _last_scan_universe_size,
            "symbolsScanned":  _last_scan_symbols_scanned,
            "scanErrors":      list(_last_scan_errors),
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
            "universeScanned": _last_scan_universe_size,
            "symbolsScanned":  _last_scan_symbols_scanned,
            "scanErrors":      list(_last_scan_errors),
            "patterns": patterns[:30],
        }

    @staticmethod
    def _cache_is_fresh() -> bool:
        # Freshness is timestamp-based, not list-based. A legitimate scan that
        # yields zero patterns (or all-symbol errors) must still be honoured —
        # otherwise every request would re-trigger a full 65-symbol rescan.
        return _last_scan_monotonic > 0 and (
            time.monotonic() - _last_scan_monotonic <= _PATTERN_CACHE_TTL
        )

    async def run_scan(self) -> list[dict]:
        global _cached_patterns, _last_scan_time, _last_scan_monotonic
        global _last_scan_errors, _last_scan_universe_size, _last_scan_symbols_scanned
        all_patterns: list[dict] = []
        errors: list[dict] = []

        # Honest universe — meaningful sample of each cap segment. With ~0.4s
        # per symbol this is ~26s per scan, comfortably inside the 30-minute
        # cache TTL. The previous 28-symbol slice was misleadingly tiny.
        universe_map = [
            (NIFTY100[:40], "NIFTY100"),
            (MIDCAP[:15],   "MIDCAP"),
            (SMALLCAP[:10], "SMALLCAP"),
        ]
        universe_size = sum(len(syms) for syms, _ in universe_map)
        scanned = 0
        scanned_at_iso = datetime.utcnow().isoformat() + "Z"

        for syms, u in universe_map:
            for sym in syms:
                try:
                    # Single-source: PriceService (NSE-first daily, EOD-aware
                    # disk overlay when market is closed).
                    h = await self.price.get_historical_data(sym, 180)
                    if len(h) < 30:
                        errors.append({"symbol": sym, "universe": u, "error": f"insufficient history ({len(h)} bars)"})
                        scanned += 1
                        continue
                    all_patterns.extend(self._detect(sym, h, u, scanned_at_iso))
                    scanned += 1
                    await asyncio.sleep(0.4)
                except Exception as e:
                    # Track per-symbol errors so the API can surface them — the
                    # previous bare `pass` made silent failures invisible.
                    errors.append({"symbol": sym, "universe": u, "error": f"{type(e).__name__}: {e}"})
                    # Count attempted symbols (success + insufficient + error)
                    # so symbolsScanned reconciles with universeScanned + scanErrors.
                    scanned += 1

        _cached_patterns = sorted(all_patterns, key=lambda p: p["confidence"], reverse=True)
        _last_scan_time = scanned_at_iso
        _last_scan_monotonic = time.monotonic()
        _last_scan_errors = errors
        _last_scan_universe_size = universe_size
        _last_scan_symbols_scanned = scanned
        return _cached_patterns

    def _detect(self, symbol: str, history: list[dict], universe: str, scanned_at_iso: Optional[str] = None) -> list[dict]:
        if scanned_at_iso is None:
            scanned_at_iso = datetime.utcnow().isoformat() + "Z"
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

        # Real-time signal-strength factors used by _adj_conf().
        # vol_ratio: today's volume vs 20-day average (1.0 = average).
        # body_strength: c0 body size relative to ATR (1.0 = ATR-sized body).
        factors = {
            "vol_ratio":     (c0["volume"] / avg_vol) if avg_vol > 0 else 1.0,
            "body_strength": (_body(c0) / atr) if atr > 0 else 1.0,
        }

        out: list[dict] = []
        add = out.append

        def mk(pattern, pattern_type, signal, base_conf, description, category,
               *, vol_w=1.0, body_w=1.0, extra=0.0,
               target_r: float = 2.0, stop_r: float = 1.0,
               tgt=None, sl=None):
            # Targets & stops are ATR-based (volatility-scaled) by default —
            # `target_r` and `stop_r` are R-multiples on the 14-bar ATR.
            # E.g. target_r=2.0, stop_r=1.0 → 2:1 reward:risk on this
            # symbol's own volatility, which is honest about per-stock risk
            # rather than a hardcoded "price * 1.04". Callers can still
            # pass explicit tgt/sl to override (used by tests).
            # WAIT signals get no target/stop — they're "watch, don't act".
            conf = _adj_conf(base_conf, factors, vol_weight=vol_w, body_weight=body_w, extra=extra)
            if signal == "CALL":
                if tgt is None: tgt = price + atr * target_r
                if sl  is None: sl  = price - atr * stop_r
            elif signal == "PUT":
                if tgt is None: tgt = price - atr * target_r
                if sl  is None: sl  = price + atr * stop_r
            return _mk(symbol, universe, pattern, pattern_type, signal, conf, price,
                       description, category, tgt, sl, scanned_at_iso=scanned_at_iso)

        # ── Single candlestick ────────────────────────────────────────────────
        if _lower(c0) > 2 * _body(c0) and _upper(c0) < 0.5 * _body(c0) and lr < 50:
            # Hammer strength scales with how oversold RSI is and lower-wick dominance.
            wick_dom = _lower(c0) / max(_body(c0), 1e-9)  # ≥ 2 by guard
            add(mk("Hammer", "BULLISH", "CALL", 70,
                "Long lower wick signals strong buying pressure — bullish reversal likely",
                "Candlestick",
                extra=min(8.0, (50 - lr) / 50 * 10) + min(4.0, (wick_dom - 2) * 1.5),
                target_r=2.0, stop_r=1.0))

        if _upper(c0) > 2 * _body(c0) and _lower(c0) < 0.5 * _body(c0) and lr < 45 and _is_bull(c0):
            add(mk("Inverted Hammer", "BULLISH", "CALL", 62,
                "Buyers pushed up after a downtrend — potential bullish reversal",
                "Candlestick",
                extra=min(6.0, (45 - lr) / 45 * 8),
                target_r=1.5, stop_r=1.0))

        if _upper(c0) > 2 * _body(c0) and _lower(c0) < 0.5 * _body(c0) and lr > 55:
            wick_dom = _upper(c0) / max(_body(c0), 1e-9)
            add(mk("Shooting Star", "BEARISH", "PUT", 70,
                "Long upper wick after rally — sellers overwhelmed buyers, bearish reversal signal",
                "Candlestick",
                extra=min(8.0, (lr - 55) / 45 * 10) + min(4.0, (wick_dom - 2) * 1.5),
                target_r=2.0, stop_r=1.0))

        if _lower(c0) > 2 * _body(c0) and _upper(c0) < 0.5 * _body(c0) and lr > 60 and _is_bear(c0):
            add(mk("Hanging Man", "BEARISH", "PUT", 65,
                "Hammer shape at the top of an uptrend — distribution signal, bearish reversal",
                "Candlestick",
                extra=min(6.0, (lr - 60) / 40 * 8),
                target_r=2.0, stop_r=1.0))

        if _is_doji(c0) and _range(c0) > atr * 0.5:
            # Doji is indecision — confidence shouldn't be inflated by body strength.
            add(mk("Doji", "NEUTRAL", "WAIT", 50,
                "Open ≈ Close — market indecision. Watch next candle for direction confirmation",
                "Candlestick", body_w=0.0))

        if _is_doji(c0) and _lower(c0) > _range(c0) * 0.7:
            add(mk("Dragonfly Doji", "BULLISH", "CALL", 68,
                "Long lower wick, no upper wick — buyers strongly rejected the lows, bullish",
                "Candlestick", body_w=0.0,
                target_r=1.5, stop_r=1.0))

        if _is_doji(c0) and _upper(c0) > _range(c0) * 0.7:
            add(mk("Gravestone Doji", "BEARISH", "PUT", 68,
                "Long upper wick, no lower wick — sellers pushed price back from highs, bearish",
                "Candlestick", body_w=0.0, target_r=2.0, stop_r=1.0))

        if not _is_doji(c0) and _body(c0) < _range(c0) * 0.3 and _lower(c0) > _body(c0) and _upper(c0) > _body(c0):
            add(mk("Spinning Top", "NEUTRAL", "WAIT", 48,
                "Small body with long wicks — indecision between bulls and bears",
                "Candlestick", body_w=0.0))

        if _is_bull(c0) and _body(c0) > _range(c0) * 0.9 and _body(c0) > atr * 1.2:
            # Marubozu — body strength IS the signal. Heavy body weighting.
            add(mk("Bullish Marubozu", "BULLISH", "CALL", 72,
                "Full bull candle, no wicks — complete buyer control, strong momentum",
                "Candlestick", body_w=1.5, vol_w=1.2,
                target_r=1.5, stop_r=1.0))

        if _is_bear(c0) and _body(c0) > _range(c0) * 0.9 and _body(c0) > atr * 1.2:
            add(mk("Bearish Marubozu", "BEARISH", "PUT", 72,
                "Full bear candle, no wicks — complete seller control, strong downward momentum",
                "Candlestick", body_w=1.5, vol_w=1.2, target_r=2.0, stop_r=1.0))

        if c0["high"] < c1["high"] and c0["low"] > c1["low"] and _body(c0) < _body(c1) * 0.6:
            add(mk("Inside Bar", "NEUTRAL", "WAIT", 55,
                "Price consolidating inside previous candle range — breakout setup forming",
                "Candlestick", body_w=0.0))

        if c0["high"] > c1["high"] and c0["low"] < c1["low"] and _body(c0) > _body(c1) * 1.5:
            add(mk("Outside Bar", "NEUTRAL", "WAIT", 55,
                "Candle completely engulfs prior range — high volatility, wait for direction",
                "Candlestick", body_w=0.5))

        # ── Two candle ───────────────────────────────────────────────────────
        if _is_bear(c1) and _is_bull(c0) and c0["open"] < c1["close"] and c0["close"] > c1["open"]:
            # Engulfing strength = how much c0 dwarfs c1.
            engulf_ratio = _body(c0) / max(_body(c1), 1e-9)
            add(mk("Bullish Engulfing", "BULLISH", "CALL", 75,
                "Green candle fully engulfs previous red candle — strong bullish reversal",
                "Two-Candle", vol_w=1.3,
                extra=min(6.0, (engulf_ratio - 1.0) * 4),
                target_r=2.0, stop_r=1.0))

        if _is_bull(c1) and _is_bear(c0) and c0["open"] > c1["close"] and c0["close"] < c1["open"]:
            engulf_ratio = _body(c0) / max(_body(c1), 1e-9)
            add(mk("Bearish Engulfing", "BEARISH", "PUT", 75,
                "Red candle fully engulfs previous green candle — strong bearish reversal",
                "Two-Candle", vol_w=1.3,
                extra=min(6.0, (engulf_ratio - 1.0) * 4),
                target_r=2.0, stop_r=1.0))

        if _is_bear(c1) and _is_bull(c0) and c0["open"] > c1["close"] and c0["close"] < c1["open"] and _body(c0) < _body(c1) * 0.6:
            add(mk("Bullish Harami", "BULLISH", "CALL", 62,
                "Small green candle inside large red candle — bearish momentum slowing",
                "Two-Candle", body_w=0.5,
                target_r=1.5, stop_r=1.0))

        if _is_bull(c1) and _is_bear(c0) and c0["open"] < c1["close"] and c0["close"] > c1["open"] and _body(c0) < _body(c1) * 0.6:
            add(mk("Bearish Harami", "BEARISH", "PUT", 62,
                "Small red candle inside large green candle — bullish momentum slowing",
                "Two-Candle", body_w=0.5, target_r=2.0, stop_r=1.0))

        if _is_bear(c1) and _is_bull(c0) and c0["open"] < c1["low"] and c0["close"] > _mid(c1) and c0["close"] < c1["open"]:
            add(mk("Piercing Line", "BULLISH", "CALL", 68,
                "Green candle opens below prior low but closes above its midpoint — bullish reversal",
                "Two-Candle", vol_w=1.2,
                target_r=1.5, stop_r=1.0))

        if _is_bull(c1) and _is_bear(c0) and c0["open"] > c1["high"] and c0["close"] < _mid(c1) and c0["close"] > c1["open"]:
            add(mk("Dark Cloud Cover", "BEARISH", "PUT", 68,
                "Red candle opens above prior high but closes below its midpoint — bearish reversal",
                "Two-Candle", vol_w=1.2, target_r=2.0, stop_r=1.0))

        if abs(c0["low"] - c1["low"]) / price < 0.003 and _is_bear(c1) and _is_bull(c0) and lr < 55:
            add(mk("Tweezer Bottom", "BULLISH", "CALL", 65,
                "Two candles share the same low — strong support confirmed, bullish reversal",
                "Two-Candle", extra=min(4.0, (55 - lr) / 55 * 6),
                target_r=1.5, stop_r=1.0))

        if abs(c0["high"] - c1["high"]) / price < 0.003 and _is_bull(c1) and _is_bear(c0) and lr > 55:
            add(mk("Tweezer Top", "BEARISH", "PUT", 65,
                "Two candles share the same high — strong resistance confirmed, bearish reversal",
                "Two-Candle", extra=min(4.0, (lr - 55) / 45 * 6), target_r=2.0, stop_r=1.0))

        # ── Three candle ─────────────────────────────────────────────────────
        if _is_bear(c2) and _body(c1) < _body(c2) * 0.4 and _is_bull(c0) and c0["close"] > _mid(c2) and lr < 55:
            add(mk("Morning Star", "BULLISH", "CALL", 78,
                "Three-candle bullish reversal: large red → small indecision → strong green",
                "Three-Candle", vol_w=1.3,
                extra=min(5.0, (55 - lr) / 55 * 8),
                target_r=2.5, stop_r=1.5))

        if _is_bull(c2) and _body(c1) < _body(c2) * 0.4 and _is_bear(c0) and c0["close"] < _mid(c2) and lr > 55:
            add(mk("Evening Star", "BEARISH", "PUT", 78,
                "Three-candle bearish reversal: large green → small indecision → strong red",
                "Three-Candle", vol_w=1.3,
                extra=min(5.0, (lr - 55) / 45 * 8),
                target_r=2.5, stop_r=1.5))

        if _is_bear(c2) and _is_doji(c1) and _is_bull(c0) and c0["close"] > _mid(c2):
            add(mk("Morning Doji Star", "BULLISH", "CALL", 80,
                "Strongest bullish reversal: bearish candle → doji → strong green breakout",
                "Three-Candle", vol_w=1.3,
                target_r=2.5, stop_r=1.5))

        if _is_bull(c2) and _is_doji(c1) and _is_bear(c0) and c0["close"] < _mid(c2):
            add(mk("Evening Doji Star", "BEARISH", "PUT", 80,
                "Strongest bearish reversal: bullish candle → doji → strong red breakdown",
                "Three-Candle", vol_w=1.3, target_r=2.5, stop_r=1.5))

        if (_is_bull(c2) and _is_bull(c1) and _is_bull(c0) and
                c0["close"] > c1["close"] and c1["close"] > c2["close"] and
                _body(c0) > atr * 0.7 and _body(c1) > atr * 0.7 and _body(c2) > atr * 0.7):
            add(mk("Three White Soldiers", "BULLISH", "CALL", 76,
                "Three consecutive strong green candles — relentless buying, strong bullish trend",
                "Three-Candle", body_w=1.3, vol_w=1.2,
                target_r=2.5, stop_r=2.0))

        if (_is_bear(c2) and _is_bear(c1) and _is_bear(c0) and
                c0["close"] < c1["close"] and c1["close"] < c2["close"] and
                _body(c0) > atr * 0.7 and _body(c1) > atr * 0.7 and _body(c2) > atr * 0.7):
            add(mk("Three Black Crows", "BEARISH", "PUT", 76,
                "Three consecutive strong red candles — relentless selling, strong bearish trend",
                "Three-Candle", body_w=1.3, vol_w=1.2, target_r=2.5, stop_r=2.0))

        # ── Structure patterns (60-bar lookback) ─────────────────────────────
        # All 20 structural patterns from the reference chart:
        #   Double/Triple Bottom & Top, H&S & Inverse H&S, Cup & Handle &
        #   Inverse C&H, Symmetrical/Ascending/Descending Triangle, Rising/
        #   Falling Wedge, Rectangle, Bull/Bear Flag, Bull/Bear Pennant.

        # 90 trading days ≈ 180 calendar days (scan now requests 180 cal-days).
        # Use last 90 bars for reversal patterns, last 40 for trendline patterns.
        LOOK = min(n, 90)
        _sh = highs[-LOOK:]
        _sl = lows[-LOOK:]

        def _pivots(h_arr, l_arr, order=3):
            """Return (peaks, troughs) as list of (index, price) tuples.
            order=3 gives ~1 pivot per 7 bars — practical minimum for daily charts."""
            pks, trs = [], []
            ln = len(h_arr)
            for i in range(order, ln - order):
                lo_i = max(0, i - order); hi_i = min(ln, i + order + 1)
                if h_arr[i] == max(h_arr[lo_i:hi_i]):
                    pks.append((i, h_arr[i]))
                if l_arr[i] == min(l_arr[lo_i:hi_i]):
                    trs.append((i, l_arr[i]))
            return pks, trs

        def _slope(pts):
            """Slope of least-squares line through (index, price) points."""
            if len(pts) < 2:
                return 0.0
            xs = [float(p[0]) for p in pts]
            ys = [float(p[1]) for p in pts]
            mx = sum(xs) / len(xs); my = sum(ys) / len(ys)
            num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            den = sum((x - mx) ** 2 for x in xs)
            return num / den if abs(den) > 1e-9 else 0.0

        peaks60, troughs60 = _pivots(_sh, _sl, order=3)

        # ── Double Bottom (W) ─────────────────────────────────────────────────
        if len(troughs60) >= 2:
            t1, t2 = troughs60[-2], troughs60[-1]
            if abs(t1[1] - t2[1]) / max(t1[1], 1e-9) < 0.04 and t2[0] > t1[0]:
                mid_high = max(_sh[t1[0]: t2[0] + 1])
                pullback = (mid_high - t1[1]) / max(t1[1], 1e-9)
                if pullback > 0.04 and price > mid_high * 0.99:
                    conf = 70 if lr < 55 else 63
                    add(mk("Double Bottom", "BULLISH", "CALL", conf,
                        f"W-shaped reversal — two lows near ₹{t1[1]:.0f}. Neckline ₹{mid_high:.0f} broken.",
                        "Structure", vol_w=1.2, body_w=0.3,
                        tgt=price + (mid_high - t1[1]),
                        sl=min(t1[1], t2[1]) - atr * 0.5))

        # ── Double Top (M) ────────────────────────────────────────────────────
        if len(peaks60) >= 2:
            p1, p2 = peaks60[-2], peaks60[-1]
            if abs(p1[1] - p2[1]) / max(p1[1], 1e-9) < 0.04 and p2[0] > p1[0]:
                mid_low = min(_sl[p1[0]: p2[0] + 1])
                pullback = (p1[1] - mid_low) / max(p1[1], 1e-9)
                if pullback > 0.04 and price < mid_low * 1.01:
                    conf = 70 if lr > 55 else 63
                    add(mk("Double Top", "BEARISH", "PUT", conf,
                        f"M-shaped reversal — two highs near ₹{p1[1]:.0f}. Neckline ₹{mid_low:.0f} broken.",
                        "Structure", vol_w=1.2, body_w=0.3,
                        tgt=price - (p1[1] - mid_low),
                        sl=max(p1[1], p2[1]) + atr * 0.5))

        # ── Triple Bottom ─────────────────────────────────────────────────────
        if len(troughs60) >= 3:
            t1, t2, t3 = troughs60[-3], troughs60[-2], troughs60[-1]
            avg_low = (t1[1] + t2[1] + t3[1]) / 3
            spread = max(t1[1], t2[1], t3[1]) - min(t1[1], t2[1], t3[1])
            if spread / max(avg_low, 1e-9) < 0.05 and t3[0] > t1[0]:
                neck = max(_sh[t1[0]: t3[0] + 1])
                if price > neck * 0.99:
                    add(mk("Triple Bottom", "BULLISH", "CALL", 73,
                        f"Three lows near ₹{avg_low:.0f} — very strong support. Breakout above ₹{neck:.0f}.",
                        "Structure", vol_w=1.2, body_w=0.3,
                        tgt=price + (neck - avg_low),
                        sl=avg_low - atr * 0.5))

        # ── Triple Top ────────────────────────────────────────────────────────
        if len(peaks60) >= 3:
            p1, p2, p3 = peaks60[-3], peaks60[-2], peaks60[-1]
            avg_high = (p1[1] + p2[1] + p3[1]) / 3
            spread = max(p1[1], p2[1], p3[1]) - min(p1[1], p2[1], p3[1])
            if spread / max(avg_high, 1e-9) < 0.05 and p3[0] > p1[0]:
                neck = min(_sl[p1[0]: p3[0] + 1])
                if price < neck * 1.01:
                    add(mk("Triple Top", "BEARISH", "PUT", 73,
                        f"Three highs near ₹{avg_high:.0f} — very strong resistance. Breakdown below ₹{neck:.0f}.",
                        "Structure", vol_w=1.2, body_w=0.3,
                        tgt=price - (avg_high - neck),
                        sl=avg_high + atr * 0.5))

        # ── Head and Shoulders ────────────────────────────────────────────────
        if len(peaks60) >= 3 and len(troughs60) >= 2:
            ls_pk, hd_pk, rs_pk = peaks60[-3], peaks60[-2], peaks60[-1]
            if hd_pk[1] > ls_pk[1] and hd_pk[1] > rs_pk[1]:
                sh_diff = abs(ls_pk[1] - rs_pk[1]) / max(ls_pk[1], 1e-9)
                if sh_diff < 0.07:
                    t_left  = next((t for t in reversed(troughs60) if ls_pk[0] < t[0] < hd_pk[0]), None)
                    t_right = next((t for t in reversed(troughs60) if hd_pk[0] < t[0] < rs_pk[0]), None)
                    if t_left and t_right:
                        neck = (t_left[1] + t_right[1]) / 2
                        if price < neck * 1.02:
                            add(mk("Head & Shoulders", "BEARISH", "PUT", 75,
                                f"Classic H&S — head ₹{hd_pk[1]:.0f}, neckline ₹{neck:.0f}. Measured target below.",
                                "Structure", vol_w=1.1, body_w=0.3,
                                tgt=neck - (hd_pk[1] - neck),
                                sl=rs_pk[1] + atr * 0.5))

        # ── Inverse Head and Shoulders ────────────────────────────────────────
        if len(troughs60) >= 3 and len(peaks60) >= 2:
            ls_t, hd_t, rs_t = troughs60[-3], troughs60[-2], troughs60[-1]
            if hd_t[1] < ls_t[1] and hd_t[1] < rs_t[1]:
                sh_diff = abs(ls_t[1] - rs_t[1]) / max(ls_t[1], 1e-9)
                if sh_diff < 0.07:
                    p_left  = next((p for p in reversed(peaks60) if ls_t[0] < p[0] < hd_t[0]), None)
                    p_right = next((p for p in reversed(peaks60) if hd_t[0] < p[0] < rs_t[0]), None)
                    if p_left and p_right:
                        neck = (p_left[1] + p_right[1]) / 2
                        if price > neck * 0.98:
                            add(mk("Inverse Head & Shoulders", "BULLISH", "CALL", 75,
                                f"Inverse H&S — head ₹{hd_t[1]:.0f}, neckline ₹{neck:.0f}. Measured target above.",
                                "Structure", vol_w=1.1, body_w=0.3,
                                tgt=neck + (neck - hd_t[1]),
                                sl=rs_t[1] - atr * 0.5))

        # ── Cup and Handle ────────────────────────────────────────────────────
        if n >= 40:
            cup_c  = closes[-40:-10]
            hdl_c  = closes[-10:]
            hdl_l  = lows[-10:]
            cup_l  = cup_c[0]; cup_r = cup_c[-1]
            cup_bot = min(cup_c)
            cup_depth = min(cup_l, cup_r) - cup_bot
            if (abs(cup_l - cup_r) / max(cup_l, 1e-9) < 0.06
                    and cup_depth / max(cup_l, 1e-9) > 0.07):
                hdl_min = min(hdl_l)
                retr = (cup_r - hdl_min) / max(cup_depth, 1e-9)
                if 0.1 < retr < 0.55 and price > cup_r * 0.99:
                    add(mk("Cup & Handle", "BULLISH", "CALL", 72,
                        f"U-shaped base + shallow handle — accumulation complete. Breakout above ₹{cup_r:.0f}.",
                        "Structure", vol_w=1.2, body_w=0.3,
                        tgt=price + cup_depth,
                        sl=hdl_min - atr * 0.5))

        # ── Inverse Cup and Handle ────────────────────────────────────────────
        if n >= 40:
            cup_c   = closes[-40:-10]
            hdl_c   = closes[-10:]
            hdl_h   = highs[-10:]
            cup_l   = cup_c[0]; cup_r = cup_c[-1]
            cup_top  = max(cup_c)
            cup_ht   = cup_top - max(cup_l, cup_r)
            if (abs(cup_l - cup_r) / max(cup_l, 1e-9) < 0.06
                    and cup_ht / max(cup_top, 1e-9) > 0.07):
                hdl_max = max(hdl_h)
                retr = (hdl_max - cup_r) / max(cup_ht, 1e-9)
                if 0.1 < retr < 0.55 and price < cup_r * 1.01:
                    add(mk("Inverse Cup & Handle", "BEARISH", "PUT", 72,
                        f"Inverted U + small bounce handle — distribution. Breakdown below ₹{cup_r:.0f}.",
                        "Structure", vol_w=1.2, body_w=0.3,
                        tgt=price - cup_ht,
                        sl=hdl_max + atr * 0.5))

        # ── Triangles, Wedges, Rectangle (40-bar trendline analysis) ─────────
        # order=2 gives ~1 pivot per 5 bars — more sensitive than order=3,
        # needed because 40 bars only yields ~4-6 pivots at order=3.
        TLINE = min(n, 40)
        _th = highs[-TLINE:]
        _tl = lows[-TLINE:]
        peaks30, troughs30 = _pivots(_th, _tl, order=2)

        if len(peaks30) >= 2 and len(troughs30) >= 2:
            res_slope = _slope(peaks30[-3:] if len(peaks30) >= 3 else peaks30)
            sup_slope = _slope(troughs30[-3:] if len(troughs30) >= 3 else troughs30)
            avg_res = sum(p[1] for p in peaks30[-2:]) / 2
            avg_sup = sum(t[1] for t in troughs30[-2:]) / 2
            spread_pct = (avg_res - avg_sup) / max(avg_res, 1e-9)
            # Minimum slope unit = 0.1% of price per bar (anything smaller = flat)
            su = price * 0.001

            # ── Symmetrical Triangle ──────────────────────────────────────────
            if res_slope < -su and sup_slope > su and spread_pct < 0.12:
                sig = "CALL" if (lr < 55 and le20 > le50) else "PUT" if (lr > 55 and le20 < le50) else "WAIT"
                pt  = "BULLISH" if sig == "CALL" else "BEARISH" if sig == "PUT" else "NEUTRAL"
                add(mk("Symmetrical Triangle", pt, sig, 65,
                    "Converging highs and lows — energy coiling. Breakout follows the prevailing trend.",
                    "Structure", body_w=0.2, vol_w=0.8,
                    target_r=3.0, stop_r=1.5))

            # ── Ascending Triangle ────────────────────────────────────────────
            elif abs(res_slope) < su * 0.6 and sup_slope > su and spread_pct < 0.10:
                add(mk("Ascending Triangle", "BULLISH", "CALL", 68,
                    f"Flat resistance ₹{avg_res:.0f} + rising support — buyers absorbing every dip. Bullish breakout likely.",
                    "Structure", body_w=0.2, vol_w=1.0,
                    tgt=avg_res + (avg_res - avg_sup),
                    sl=avg_sup - atr * 0.5))

            # ── Descending Triangle ───────────────────────────────────────────
            elif res_slope < -su and abs(sup_slope) < su * 0.6 and spread_pct < 0.10:
                add(mk("Descending Triangle", "BEARISH", "PUT", 68,
                    f"Falling resistance + flat support ₹{avg_sup:.0f} — sellers capping every rally. Bearish breakdown likely.",
                    "Structure", body_w=0.2, vol_w=1.0,
                    tgt=avg_sup - (avg_res - avg_sup),
                    sl=avg_res + atr * 0.5))

            # ── Rising Wedge (bearish) ────────────────────────────────────────
            elif res_slope > su and sup_slope > res_slope + su and spread_pct < 0.10:
                add(mk("Rising Wedge", "BEARISH", "PUT", 66,
                    "Both highs and lows rising but converging upward — momentum fading, reversal ahead.",
                    "Structure", body_w=0.2, vol_w=0.8,
                    target_r=2.5, stop_r=1.5))

            # ── Falling Wedge (bullish) ───────────────────────────────────────
            elif res_slope < -su and sup_slope > res_slope + su and sup_slope < 0 and spread_pct < 0.10:
                add(mk("Falling Wedge", "BULLISH", "CALL", 66,
                    "Both highs and lows falling but converging — sellers losing steam, bullish reversal ahead.",
                    "Structure", body_w=0.2, vol_w=0.8,
                    target_r=2.5, stop_r=1.5))

            # ── Rectangle ─────────────────────────────────────────────────────
            elif abs(res_slope) < su * 0.6 and abs(sup_slope) < su * 0.6 and spread_pct < 0.12:
                sig = "CALL" if le20 > le50 else "PUT"
                pt  = "BULLISH" if sig == "CALL" else "BEARISH"
                add(mk("Rectangle", pt, sig, 62,
                    f"Price ranging ₹{avg_sup:.0f}–₹{avg_res:.0f} — consolidation. Breakout follows the trend.",
                    "Structure", body_w=0.2, vol_w=0.8,
                    tgt=(avg_res + (avg_res - avg_sup)) if sig == "CALL" else (avg_sup - (avg_res - avg_sup)),
                    sl=(avg_sup - atr * 0.5) if sig == "CALL" else (avg_res + atr * 0.5)))

        # ── Flag and Pennant (pole + consolidation) ───────────────────────────
        POLE = 10; CONS = 8
        if n >= POLE + CONS:
            pole_start = closes[-(POLE + CONS)]
            pole_end   = closes[-CONS]
            pole_move  = pole_end - pole_start
            abs_pole   = abs(pole_move)
            cons_h = highs[-CONS:]; cons_l = lows[-CONS:]; cons_c = closes[-CONS:]
            cons_range = max(cons_h) - min(cons_l)
            pole_pct = abs_pole / max(abs(pole_start), 1e-9)

            if pole_pct > 0.05 and cons_range < abs_pole * 0.5:
                cpks, ctrs = _pivots(cons_h, cons_l, order=2)
                c_res_slope = _slope(cpks[-2:]) if len(cpks) >= 2 else 0.0
                c_sup_slope = _slope(ctrs[-2:]) if len(ctrs) >= 2 else 0.0
                su2 = price * 0.0005

                if pole_move > 0:   # bullish pole
                    is_pennant = c_res_slope < -su2 and c_sup_slope > su2
                    is_flag    = c_res_slope < -su2 and c_sup_slope < 0          # both drifting down
                    if is_pennant:
                        add(mk("Bullish Pennant", "BULLISH", "CALL", 70,
                            "Strong up-move + contracting triangle consolidation — continuation, breakout expected.",
                            "Structure", vol_w=1.1, body_w=0.3,
                            tgt=price + abs_pole, sl=min(cons_l) - atr * 0.5))
                    elif is_flag:
                        add(mk("Bull Flag", "BULLISH", "CALL", 68,
                            "Sharp rally + shallow parallel pullback — continuation pattern, upside expected.",
                            "Structure", vol_w=1.1, body_w=0.3,
                            tgt=price + abs_pole, sl=min(cons_l) - atr * 0.5))
                    elif sum(volumes[-CONS:]) / CONS < avg_vol * 0.8 and cons_c[-1] < cons_c[0]:
                        add(mk("Bull Flag", "BULLISH", "CALL", 65,
                            "Sharp rally then low-volume drift lower — textbook bull flag.",
                            "Structure", vol_w=0.8, body_w=0.3,
                            tgt=price + abs_pole, sl=min(cons_l) - atr * 0.5))

                else:               # bearish pole
                    is_pennant = c_res_slope < -su2 and c_sup_slope > su2
                    is_flag    = c_res_slope > su2 and c_sup_slope > 0           # both drifting up
                    if is_pennant:
                        add(mk("Bearish Pennant", "BEARISH", "PUT", 70,
                            "Sharp down-move + contracting triangle consolidation — continuation, breakdown expected.",
                            "Structure", vol_w=1.1, body_w=0.3,
                            tgt=price - abs_pole, sl=max(cons_h) + atr * 0.5))
                    elif is_flag:
                        add(mk("Bear Flag", "BEARISH", "PUT", 68,
                            "Sharp drop + shallow parallel bounce — continuation pattern, downside expected.",
                            "Structure", vol_w=1.1, body_w=0.3,
                            tgt=price - abs_pole, sl=max(cons_h) + atr * 0.5))
                    elif sum(volumes[-CONS:]) / CONS < avg_vol * 0.8 and cons_c[-1] > cons_c[0]:
                        add(mk("Bear Flag", "BEARISH", "PUT", 65,
                            "Sharp drop then low-volume bounce — textbook bear flag.",
                            "Structure", vol_w=0.8, body_w=0.3,
                            tgt=price - abs_pole, sl=max(cons_h) + atr * 0.5))

        # ── Indicator patterns ────────────────────────────────────────────────
        if lr < 35 and price > le50:
            # Confidence scales with how oversold RSI is. Body weight reduced
            # because indicator patterns aren't candle-shape dependent.
            add(mk("RSI Oversold Bounce", "BULLISH", "CALL", 65,
                f"RSI {lr:.1f} — deeply oversold while price holds EMA50 support. Bounce likely",
                "Indicator", body_w=0.3,
                extra=min(10.0, (35 - lr) / 35 * 14),
                target_r=2.0, stop_r=1.0))

        if len(rsi_arr) >= 10:
            price_low1 = min(closes[-10:-5])
            price_low2 = min(closes[-5:])
            rsi_low1   = min(rsi_arr[-10:-5])
            rsi_low2   = min(rsi_arr[-5:])
            if price_low2 < price_low1 and rsi_low2 > rsi_low1 and lr < 50:
                # Divergence strength = magnitude of RSI vs price disagreement.
                rsi_gap = rsi_low2 - rsi_low1
                add(mk("RSI Bullish Divergence", "BULLISH", "CALL", 75,
                    "Price making lower lows but RSI making higher lows — hidden buying strength",
                    "Indicator", body_w=0.3,
                    extra=min(8.0, rsi_gap * 0.8),
                    target_r=2.5, stop_r=1.5))

        if lr > 72:
            add(mk("RSI Overbought", "BEARISH", "PUT", 60,
                f"RSI {lr:.1f} — extreme overbought zone. Correction likely",
                "Indicator", body_w=0.3,
                extra=min(10.0, (lr - 72) / 28 * 14),
                target_r=2.0, stop_r=1.0))

        if len(rsi_arr) >= 10:
            price_high1 = max(closes[-10:-5])
            price_high2 = max(closes[-5:])
            rsi_high1   = max(rsi_arr[-10:-5])
            rsi_high2   = max(rsi_arr[-5:])
            if price_high2 > price_high1 and rsi_high2 < rsi_high1 and lr > 55:
                rsi_gap = rsi_high1 - rsi_high2
                add(mk("RSI Bearish Divergence", "BEARISH", "PUT", 75,
                    "Price making higher highs but RSI making lower highs — weakening momentum",
                    "Indicator", body_w=0.3,
                    extra=min(8.0, rsi_gap * 0.8),
                    target_r=2.5, stop_r=1.5))

        if pm < ps and lm > ls:
            # MACD crossover strength = histogram magnitude.
            add(mk("MACD Bullish Crossover", "BULLISH", "CALL", 70,
                "MACD line just crossed above Signal line — buy signal, momentum turning bullish",
                "Indicator", body_w=0.3, vol_w=1.2,
                extra=min(6.0, abs(lm - ls) / max(price * 0.005, 1e-9)),
                target_r=2.0, stop_r=1.0))

        if pm > ps and lm < ls:
            add(mk("MACD Bearish Crossover", "BEARISH", "PUT", 70,
                "MACD line just crossed below Signal line — sell signal, momentum turning bearish",
                "Indicator", body_w=0.3, vol_w=1.2,
                extra=min(6.0, abs(lm - ls) / max(price * 0.005, 1e-9)),
                target_r=2.0, stop_r=1.0))

        if lh > 0 and lh > ph and ph != 0 and lh > ph * 1.3:
            add(mk("MACD Histogram Expanding (Bull)", "BULLISH", "CALL", 64,
                "MACD histogram growing rapidly in positive zone — bullish momentum accelerating",
                "Indicator", body_w=0.3,
                target_r=1.5, stop_r=1.0))

        if lh < 0 and ph != 0 and abs(lh) > abs(ph) * 1.3:
            add(mk("MACD Histogram Expanding (Bear)", "BEARISH", "PUT", 64,
                "MACD histogram deepening in negative zone — bearish momentum accelerating",
                "Indicator", body_w=0.3, target_r=2.0, stop_r=1.0))

        if pe20 < pe50 and le20 > le50:
            add(mk("EMA Golden Cross (20/50)", "BULLISH", "CALL", 78,
                "EMA20 just crossed above EMA50 — medium-term trend turning bullish",
                "Indicator", body_w=0.3, vol_w=1.3,
                target_r=2.5, stop_r=1.5))

        if pe20 > pe50 and le20 < le50:
            add(mk("EMA Death Cross (20/50)", "BEARISH", "PUT", 78,
                "EMA20 just crossed below EMA50 — medium-term trend turning bearish",
                "Indicator", body_w=0.3, vol_w=1.3,
                target_r=2.5, stop_r=1.5))

        if len(ema200) >= 2 and pe50 < pe200 and le50 > le200:
            add(mk("EMA Golden Cross (50/200)", "BULLISH", "CALL", 84,
                "EMA50 just crossed above EMA200 — major trend turning bullish (Golden Cross)",
                "Indicator", body_w=0.3, vol_w=1.3,
                target_r=4.0, stop_r=2.0))

        if len(ema200) >= 2 and pe50 > pe200 and le50 < le200:
            add(mk("EMA Death Cross (50/200)", "BEARISH", "PUT", 84,
                "EMA50 just crossed below EMA200 — major trend turning bearish (Death Cross)",
                "Indicator", body_w=0.3, vol_w=1.3,
                target_r=2.5, stop_r=2.0))

        return out
