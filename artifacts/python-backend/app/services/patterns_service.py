import os
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
from ..lib.universe import get_scan_universe, cap_label
from ..lib.db_paths import local_db_path
from .scan_runner import ScanJob, KEEP
# Candle-pattern primitives — centralised in app/lib so the scanner DSL
# can use the same definitions (BULLISH_ENGULFING etc. as boolean
# indicators). The underscore-prefixed locals below are kept as thin
# aliases so the rest of this module's detection logic doesn't need
# to be rewritten.
from ..lib import candle_patterns as _cp

# Pattern scans now cover the FULL ~2,000-symbol NSE universe and are entirely
# derived from daily OHLCV. They run cache-first in the background via ScanJob:
# per-symbol pattern lists persist in SQLite, stream in as the scan progresses,
# and report live {done,total} progress — so the large universe never blocks a
# request. The TTL below is only echoed to the UI for display.
_PATTERN_CACHE_TTL = 30 * 60  # seconds (informational)
_PATTERNS_CONCURRENCY = int(os.environ.get("PATTERNS_SCAN_CONCURRENCY", "12"))
# SQLite cache DB on local disk (see app/lib/db_paths.py — never market_cache/,
# which is an SMB mount where SQLite WAL fails with "database is locked").
_PATTERNS_DB = local_db_path("patterns_scan.db")


# Aliases for backward compat with the inline detection blocks below.
# Real definitions live in `app/lib/candle_patterns.py`.
_body   = _cp.body
_upper  = _cp.upper_wick
_lower  = _cp.lower_wick
_range  = _cp.candle_range
_is_bull = _cp.is_bull
_is_bear = _cp.is_bear
_is_doji = _cp.is_doji
_mid    = _cp.midpoint


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
        tgt=None, sl=None, *, scanned_at_iso: Optional[str] = None, geometry: Optional[dict] = None):
    if scanned_at_iso is None:
        scanned_at_iso = datetime.utcnow().isoformat() + "Z"
    out = {
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
    # Date-anchored drawing geometry (Structure patterns only) — pivots + lines
    # the Chart Studio replays as a read-only overlay. Omitted entirely for
    # patterns without geometry so non-structure rows are byte-for-byte unchanged.
    if geometry is not None:
        out["geometry"] = geometry
    return out


class PatternsService:
    def __init__(self, yahoo: YahooService, nse: NseService, price: Optional[PriceService] = None):
        self.yahoo = yahoo
        self.nse = nse
        self.price = price or PriceService(nse, yahoo)
        # Cache-first background scan over the full equity universe.
        self._job = ScanJob(
            name="patterns",
            db_path=_PATTERNS_DB,
            scan_one=self._scan_symbol,
            universe_fn=get_scan_universe,
            concurrency=_PATTERNS_CONCURRENCY,
            # Patterns are daily/EOD — auto-scan once after the close and never
            # during market hours. The "Run Scan Now" button (trigger_scan →
            # force=True) still re-scans on demand at any time.
            eod_only=True,
        )

    def scan_status(self) -> dict:
        """Lightweight scan progress for the nav badge — no pattern payload."""
        return self._job.status()

    async def get_patterns(self, universe: Optional[str] = None, signal: Optional[str] = None, category: Optional[str] = None) -> dict:
        # Cache-first: kick a background scan if stale, then serve whatever is
        # cached right now (results stream in during a scan). Never blocks.
        self._job.maybe_kick()
        rows = self._job.read_all()              # one read; reused below
        all_patterns = self._collect(rows)
        symbols_scanned = len(rows)

        patterns = all_patterns
        if universe:
            patterns = [p for p in patterns if p.get("universe") == universe.upper()]
        if signal:
            patterns = [p for p in patterns if p.get("signal") == signal.upper()]
        if category:
            patterns = [p for p in patterns if category.lower() in (p.get("category") or "").lower()]
        calls = [p for p in patterns if p.get("signal") == "CALL"]
        puts  = [p for p in patterns if p.get("signal") == "PUT"]
        categories = sorted({p.get("category") for p in all_patterns if p.get("category")})

        st = self._job.status()
        last = self._job.last_scan_at()
        cache_age = max(0, int(time.time() - last)) if last else 0
        return {
            "lastScanTime": st["cachedAt"] or datetime.utcnow().isoformat() + "Z",
            "scannedAt":    st["cachedAt"] or datetime.utcnow().isoformat() + "Z",
            "cacheAgeSeconds": cache_age,
            "cacheTtlSeconds": _PATTERN_CACHE_TTL,
            "universeScanned": st["universeSize"],
            "symbolsScanned":  symbols_scanned,
            "scanErrors":      [],
            "totalPatterns": len(patterns),
            "callSignals": len(calls),
            "putSignals": len(puts),
            "categories": categories,
            "patterns": patterns[:100],
            "topCalls": calls[:15],
            "topPuts": puts[:15],
            "scanInProgress": st["scanInProgress"],
            "scanProgress":   st["scanProgress"],
        }

    def all_patterns(self) -> list[dict]:
        """Full flat list of currently-cached patterns (sorted by confidence).

        Kicks a background scan if the cache is stale. Used by AnalyticsService's
        pattern-stats — non-blocking, returns whatever is cached now.
        """
        self._job.maybe_kick()
        return self._collect()

    async def trigger_scan(self) -> dict:
        # Fire-and-forget: force a background re-scan and return immediately.
        # The UI polls get_patterns() for streaming results + live progress.
        self._job.maybe_kick(force=True)
        st = self._job.status()
        return {
            "message": "Scan started",
            "scanInProgress": st["scanInProgress"],
            "scanProgress":   st["scanProgress"],
            "universeScanned": st["universeSize"],
        }

    def _collect(self, rows: Optional[list[dict]] = None) -> list[dict]:
        """Flatten all cached per-symbol pattern lists, sorted by confidence.

        Pass `rows` (from a prior read_all) to avoid a second read; otherwise
        reads the in-memory mirror itself.
        """
        if rows is None:
            rows = self._job.read_all()
        out: list[dict] = []
        for row in rows:
            out.extend(row.get("patterns") or [])
        return sorted(out, key=lambda p: p.get("confidence", 0), reverse=True)

    async def _scan_symbol(self, sym: str) -> Optional[dict]:
        """ScanJob worker: fetch one symbol's history and detect its patterns.

        Returns {"symbol","universe","patterns"} (patterns may be empty, so the
        row is still cached and counts as scanned); None when history is
        insufficient so the symbol is dropped from the cache.
        """
        try:
            h = await self.price.get_historical_data(sym, 180)
        except Exception:
            return KEEP            # transient fetch failure — don't wipe the cached row
        if not h or len(h) < 30:
            return KEEP            # no/too-little data this pass — keep prior row

        cap = cap_label(sym)
        scanned_at_iso = datetime.utcnow().isoformat() + "Z"
        pats = self._detect(sym, h, cap, scanned_at_iso)
        return {"symbol": sym, "universe": cap, "patterns": pats}

    def _detect(self, symbol: str, history: list[dict], universe: str, scanned_at_iso: Optional[str] = None) -> list[dict]:
        if scanned_at_iso is None:
            scanned_at_iso = datetime.utcnow().isoformat() + "Z"
        ohlcv = history
        n = len(ohlcv)
        closes  = [d["close"] for d in ohlcv]
        highs   = [d["high"]  for d in ohlcv]
        lows    = [d["low"]   for d in ohlcv]
        volumes = [d["volume"] for d in ohlcv]
        # Trading-date per bar — the anchor for Structure-pattern drawing geometry.
        # The Chart Studio maps these dates back to its own bars (which may differ
        # in count), exactly like the SMC overlay does.
        dates   = [str(d.get("date") or "")[:10] for d in ohlcv]
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
               tgt=None, sl=None, geometry=None):
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
                       description, category, tgt, sl, scanned_at_iso=scanned_at_iso,
                       geometry=geometry)

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

        # ── Drawing-geometry builders (date-anchored) ────────────────────────
        # Pivots are indexed into a trailing window (last LOOK or TLINE bars);
        # convert that window-relative index back to the bar's absolute date so
        # the chart can replay it regardless of how many bars it loaded.
        def _date_at(abs_i: int) -> str:
            return dates[max(0, min(n - 1, abs_i))]

        def _pt(rel_i: int, p: float, *, look: int = LOOK, label: Optional[str] = None) -> dict:
            d = {"date": _date_at(n - look + rel_i), "price": round(float(p), 2)}
            if label:
                d["label"] = label
            return d

        def _ln(x0: str, y0: float, x1: str, y1: float, kind: str) -> dict:
            return {"x0": x0, "y0": round(float(y0), 2), "x1": x1, "y1": round(float(y1), 2), "kind": kind}

        def _candle_box(abs_idxs: list, label: str) -> dict:
            """Highlight box enclosing the candle(s) a candlestick pattern fired
            on (the latest 1-3 bars) + a label — so candle patterns draw too."""
            idxs = [max(0, min(n - 1, i)) for i in abs_idxs]
            lo = min(lows[i] for i in idxs); hi = max(highs[i] for i in idxs)
            pad = atr * 0.25
            return {
                "markers": [{"date": _date_at(max(idxs)), "price": round(float(hi + pad), 2), "label": label}],
                "lines": [_ln(_date_at(min(idxs)), lo - pad, _date_at(max(idxs)), hi + pad, "candlebox")],
            }

        def _indicator_geo(signal: str, label: str) -> dict:
            """An arrow on the trigger (latest) bar for indicator signals — they
            have no price-shape, so a marker on the signal bar is the honest draw."""
            last = _date_at(n - 1)
            if signal == "CALL":
                m = {"date": last, "price": round(float(lows[-1]), 2), "label": label, "kind": "trigger", "dir": "up"}
            elif signal == "PUT":
                m = {"date": last, "price": round(float(highs[-1]), 2), "label": label, "kind": "trigger", "dir": "down"}
            else:
                m = {"date": last, "price": round(float(closes[-1]), 2), "label": label, "kind": "trigger", "dir": "none"}
            return {"markers": [m], "lines": []}

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

        # ── Reversal patterns: prominence swings + strict gates + dedup ───────
        # The old detectors grabbed the last 2-3 raw local extrema with loose
        # thresholds, so a ~1% wiggle became a "head" and the same pivots were
        # labelled two contradictory patterns far from the current price. Instead:
        # build prominence "swings" (a pivot needs a >= max(ATR, 3%) reversal),
        # keep the single best instance per pattern, gate hard on symmetry /
        # prominence / size / recency, and claim swings once so a region yields a
        # single verdict. _pivots(order=3) stays for the separate trendline block.
        def _swings():
            """Prominence zigzag over the LOOK window → alternating (peaks,
            troughs) as (rel_index, price). Minor wiggles never become pivots."""
            prom = max(atr, price * 0.03)
            pks, trs = [], []
            if LOOK < 5 or prom <= 0:
                return pks, trs
            hi_i, hi_v = 0, _sh[0]
            lo_i, lo_v = 0, _sl[0]
            trend = 0                                     # 0 unknown, 1 up, -1 down
            for i in range(1, LOOK):
                if trend == 1:                            # seeking the next peak
                    if _sh[i] > hi_v: hi_v, hi_i = _sh[i], i
                    if _sl[i] <= hi_v - prom:
                        pks.append((hi_i, hi_v)); trend = -1; lo_v, lo_i = _sl[i], i
                elif trend == -1:                         # seeking the next trough
                    if _sl[i] < lo_v: lo_v, lo_i = _sl[i], i
                    if _sh[i] >= lo_v + prom:
                        trs.append((lo_i, lo_v)); trend = 1; hi_v, hi_i = _sh[i], i
                else:                                     # seed: first prom move sets direction
                    if _sh[i] > hi_v: hi_v, hi_i = _sh[i], i
                    if _sl[i] < lo_v: lo_v, lo_i = _sl[i], i
                    if _sl[i] <= hi_v - prom:
                        pks.append((hi_i, hi_v)); trend = -1; lo_v, lo_i = _sl[i], i
                    elif _sh[i] >= lo_v + prom:
                        trs.append((lo_i, lo_v)); trend = 1; hi_v, hi_i = _sh[i], i
            return pks, trs

        sw_pk, sw_tr = _swings()

        def _relevant(level):
            # Key level must be near the current price — not a played-out
            # structure stranded far behind a big move (the GARFIBRES failure).
            return abs(price - level) / max(price, 1e-9) <= 0.08

        _used: set = set()
        def _claim(*idxs):
            if any(abs(a - b) < 4 for a in idxs for b in _used):
                return False
            _used.update(idxs)
            return True

        def _btw_peak(a, b):
            c = [p for p in sw_pk if a < p[0] < b]
            return max(c, key=lambda p: p[1]) if c else None

        def _btw_trough(a, b):
            c = [t for t in sw_tr if a < t[0] < b]
            return min(c, key=lambda t: t[1]) if c else None

        def _rev_score(asym, asym_max, prom_ratio, depth_ratio, level):
            sym_s  = max(0.0, 1.0 - asym / asym_max)
            prom_s = min(1.0, prom_ratio / 0.06)
            size_s = min(1.0, depth_ratio / 0.12)
            rec_s  = max(0.0, 1.0 - abs(price - level) / (price * 0.08))
            return sym_s + prom_s + size_s + rec_s

        def _neck_proj(a_pt, b_pt):
            # Project the neckline through two pivots to the latest bar so the
            # drawn line reaches the live edge (a clean breakout line).
            aa = n - LOOK + a_pt[0]; ba = n - LOOK + b_pt[0]
            slp = (b_pt[1] - a_pt[1]) / max(1, ba - aa)
            return a_pt[1] + slp * ((n - 1) - aa)

        # ── Head & Shoulders (bearish) ────────────────────────────────────────
        best = None
        for i in range(len(sw_pk) - 2):
            lsh, hed, rsh = sw_pk[i], sw_pk[i + 1], sw_pk[i + 2]
            if hed[1] <= lsh[1] or hed[1] <= rsh[1]:
                continue
            if (hed[1] - lsh[1]) < atr or (hed[1] - rsh[1]) < atr:
                continue
            prl, prr = (hed[1] - lsh[1]) / lsh[1], (hed[1] - rsh[1]) / rsh[1]
            if prl < 0.03 or prr < 0.03:
                continue
            asym = abs(lsh[1] - rsh[1]) / min(lsh[1], rsh[1])
            if asym > 0.05:
                continue
            ntl = _btw_trough(lsh[0], hed[0]); ntr = _btw_trough(hed[0], rsh[0])
            if not ntl or not ntr or abs(ntl[1] - ntr[1]) / min(ntl[1], ntr[1]) > 0.06:
                continue
            neck = (ntl[1] + ntr[1]) / 2
            depth = hed[1] - neck
            if depth < 2 * atr or depth / neck < 0.06:
                continue
            if rsh[0] - lsh[0] < 15 or rsh[0] - lsh[0] > 80 or hed[0] - lsh[0] < 4 or rsh[0] - hed[0] < 4:
                continue
            if rsh[0] != sw_pk[-1][0]:
                continue
            if not _relevant(neck) or not (neck - depth * 1.10 <= price <= neck * 1.02):
                continue
            sc = _rev_score(asym, 0.05, min(prl, prr), depth / neck, neck)
            if sc >= 2.6 and (best is None or sc > best[0]):
                best = (sc, lsh, hed, rsh, ntl, ntr, neck, depth)
        if best and _claim(best[1][0], best[2][0], best[3][0], best[4][0], best[5][0]):
            _, lsh, hed, rsh, ntl, ntr, neck, depth = best
            add(mk("Head & Shoulders", "BEARISH", "PUT", 75,
                f"Classic H&S — head ₹{hed[1]:.0f}, neckline ₹{neck:.0f}. Measured target below.",
                "Structure", vol_w=1.1, body_w=0.3,
                tgt=neck - depth, sl=rsh[1] + atr * 0.5,
                geometry={
                    "markers": [_pt(lsh[0], lsh[1], label="LS"), _pt(hed[0], hed[1], label="H"), _pt(rsh[0], rsh[1], label="RS")],
                    "lines":   [_ln(_date_at(n - LOOK + ntl[0]), ntl[1], _date_at(n - 1), _neck_proj(ntl, ntr), "neckline")],
                }))

        # ── Inverse Head & Shoulders (bullish) ────────────────────────────────
        best = None
        for i in range(len(sw_tr) - 2):
            lsh, hed, rsh = sw_tr[i], sw_tr[i + 1], sw_tr[i + 2]
            if hed[1] >= lsh[1] or hed[1] >= rsh[1]:
                continue
            if (lsh[1] - hed[1]) < atr or (rsh[1] - hed[1]) < atr:
                continue
            prl, prr = (lsh[1] - hed[1]) / lsh[1], (rsh[1] - hed[1]) / rsh[1]
            if prl < 0.03 or prr < 0.03:
                continue
            asym = abs(lsh[1] - rsh[1]) / min(lsh[1], rsh[1])
            if asym > 0.05:
                continue
            pkl = _btw_peak(lsh[0], hed[0]); pkr = _btw_peak(hed[0], rsh[0])
            if not pkl or not pkr or abs(pkl[1] - pkr[1]) / min(pkl[1], pkr[1]) > 0.06:
                continue
            neck = (pkl[1] + pkr[1]) / 2
            depth = neck - hed[1]
            if depth < 2 * atr or depth / neck < 0.06:
                continue
            if rsh[0] - lsh[0] < 15 or rsh[0] - lsh[0] > 80 or hed[0] - lsh[0] < 4 or rsh[0] - hed[0] < 4:
                continue
            if rsh[0] != sw_tr[-1][0]:
                continue
            if not _relevant(neck) or not (neck * 0.98 <= price <= neck + depth * 1.10):
                continue
            sc = _rev_score(asym, 0.05, min(prl, prr), depth / neck, neck)
            if sc >= 2.6 and (best is None or sc > best[0]):
                best = (sc, lsh, hed, rsh, pkl, pkr, neck, depth)
        if best and _claim(best[1][0], best[2][0], best[3][0], best[4][0], best[5][0]):
            _, lsh, hed, rsh, pkl, pkr, neck, depth = best
            add(mk("Inverse Head & Shoulders", "BULLISH", "CALL", 75,
                f"Inverse H&S — head ₹{hed[1]:.0f}, neckline ₹{neck:.0f}. Measured target above.",
                "Structure", vol_w=1.1, body_w=0.3,
                tgt=neck + depth, sl=rsh[1] - atr * 0.5,
                geometry={
                    "markers": [_pt(lsh[0], lsh[1], label="LS"), _pt(hed[0], hed[1], label="H"), _pt(rsh[0], rsh[1], label="RS")],
                    "lines":   [_ln(_date_at(n - LOOK + pkl[0]), pkl[1], _date_at(n - 1), _neck_proj(pkl, pkr), "neckline")],
                }))

        # ── Triple Bottom (bullish) ───────────────────────────────────────────
        best = None
        for i in range(len(sw_tr) - 2):
            t1, t2, t3 = sw_tr[i], sw_tr[i + 1], sw_tr[i + 2]
            lows3 = (t1[1], t2[1], t3[1]); avg_low = sum(lows3) / 3
            if (max(lows3) - min(lows3)) / avg_low > 0.04:
                continue
            pa = _btw_peak(t1[0], t2[0]); pb = _btw_peak(t2[0], t3[0])
            if not pa or not pb:
                continue
            rally = max(1.5 * atr, 0.04 * price)
            if (pa[1] - avg_low) < rally or (pb[1] - avg_low) < rally:
                continue
            neck = max(pa[1], pb[1]); depth = neck - avg_low
            if depth < 2 * atr or depth / neck < 0.06:
                continue
            if t3[0] != sw_tr[-1][0] or t3[0] - t1[0] > 80:
                continue
            if not _relevant(neck) or not (neck * 0.99 <= price <= neck + depth * 1.10):
                continue
            asym = (max(lows3) - min(lows3)) / avg_low
            sc = _rev_score(asym, 0.04, depth / neck, depth / neck, neck)
            if sc >= 2.6 and (best is None or sc > best[0]):
                best = (sc, t1, t2, t3, neck, avg_low, depth)
        if best and _claim(best[1][0], best[2][0], best[3][0]):
            _, t1, t2, t3, neck, avg_low, depth = best
            add(mk("Triple Bottom", "BULLISH", "CALL", 73,
                f"Three lows near ₹{avg_low:.0f} — very strong support. Breakout above ₹{neck:.0f}.",
                "Structure", vol_w=1.2, body_w=0.3,
                tgt=neck + depth, sl=avg_low - atr * 0.5,
                geometry={
                    "markers": [_pt(t1[0], t1[1]), _pt(t2[0], t2[1]), _pt(t3[0], t3[1])],
                    "lines":   [_ln(_date_at(n - LOOK + t1[0]), neck, _date_at(n - 1), neck, "neckline")],
                }))

        # ── Triple Top (bearish) ──────────────────────────────────────────────
        best = None
        for i in range(len(sw_pk) - 2):
            p1, p2, p3 = sw_pk[i], sw_pk[i + 1], sw_pk[i + 2]
            highs3 = (p1[1], p2[1], p3[1]); avg_high = sum(highs3) / 3
            if (max(highs3) - min(highs3)) / avg_high > 0.04:
                continue
            ta = _btw_trough(p1[0], p2[0]); tb = _btw_trough(p2[0], p3[0])
            if not ta or not tb:
                continue
            drop = max(1.5 * atr, 0.04 * price)
            if (avg_high - ta[1]) < drop or (avg_high - tb[1]) < drop:
                continue
            neck = min(ta[1], tb[1]); depth = avg_high - neck
            if depth < 2 * atr or depth / neck < 0.06:
                continue
            if p3[0] != sw_pk[-1][0] or p3[0] - p1[0] > 80:
                continue
            if not _relevant(neck) or not (neck - depth * 1.10 <= price <= neck * 1.01):
                continue
            asym = (max(highs3) - min(highs3)) / avg_high
            sc = _rev_score(asym, 0.04, depth / neck, depth / neck, neck)
            if sc >= 2.6 and (best is None or sc > best[0]):
                best = (sc, p1, p2, p3, neck, avg_high, depth)
        if best and _claim(best[1][0], best[2][0], best[3][0]):
            _, p1, p2, p3, neck, avg_high, depth = best
            add(mk("Triple Top", "BEARISH", "PUT", 73,
                f"Three highs near ₹{avg_high:.0f} — very strong resistance. Breakdown below ₹{neck:.0f}.",
                "Structure", vol_w=1.2, body_w=0.3,
                tgt=neck - depth, sl=avg_high + atr * 0.5,
                geometry={
                    "markers": [_pt(p1[0], p1[1]), _pt(p2[0], p2[1]), _pt(p3[0], p3[1])],
                    "lines":   [_ln(_date_at(n - LOOK + p1[0]), neck, _date_at(n - 1), neck, "neckline")],
                }))

        # ── Double Bottom (bullish) ───────────────────────────────────────────
        best = None
        for i in range(len(sw_tr) - 1):
            t1, t2 = sw_tr[i], sw_tr[i + 1]
            if abs(t1[1] - t2[1]) / min(t1[1], t2[1]) > 0.03:
                continue
            pk = _btw_peak(t1[0], t2[0])
            if not pk:
                continue
            mid_high = pk[1]; lo = min(t1[1], t2[1]); depth = mid_high - lo
            if depth < max(1.5 * atr, 0.04 * price) or depth / mid_high < 0.06:
                continue
            if t2[0] != sw_tr[-1][0] or t2[0] - t1[0] > 80:
                continue
            if not _relevant(mid_high) or not (mid_high * 0.99 <= price <= mid_high + depth * 1.10):
                continue
            asym = abs(t1[1] - t2[1]) / min(t1[1], t2[1])
            sc = _rev_score(asym, 0.03, depth / mid_high, depth / mid_high, mid_high)
            if sc >= 2.4 and (best is None or sc > best[0]):
                best = (sc, t1, t2, mid_high, lo, depth)
        if best and _claim(best[1][0], best[2][0]):
            _, t1, t2, mid_high, lo, depth = best
            conf = 70 if lr < 55 else 63
            add(mk("Double Bottom", "BULLISH", "CALL", conf,
                f"W-shaped reversal — two lows near ₹{lo:.0f}. Neckline ₹{mid_high:.0f}.",
                "Structure", vol_w=1.2, body_w=0.3,
                tgt=mid_high + depth, sl=lo - atr * 0.5,
                geometry={
                    "markers": [_pt(t1[0], t1[1]), _pt(t2[0], t2[1])],
                    "lines":   [_ln(_date_at(n - LOOK + t1[0]), mid_high, _date_at(n - 1), mid_high, "neckline")],
                }))

        # ── Double Top (bearish) ──────────────────────────────────────────────
        best = None
        for i in range(len(sw_pk) - 1):
            p1, p2 = sw_pk[i], sw_pk[i + 1]
            if abs(p1[1] - p2[1]) / min(p1[1], p2[1]) > 0.03:
                continue
            tr0 = _btw_trough(p1[0], p2[0])
            if not tr0:
                continue
            mid_low = tr0[1]; hi = max(p1[1], p2[1]); depth = hi - mid_low
            if depth < max(1.5 * atr, 0.04 * price) or depth / hi < 0.06:
                continue
            if p2[0] != sw_pk[-1][0] or p2[0] - p1[0] > 80:
                continue
            if not _relevant(mid_low) or not (mid_low - depth * 1.10 <= price <= mid_low * 1.01):
                continue
            asym = abs(p1[1] - p2[1]) / min(p1[1], p2[1])
            sc = _rev_score(asym, 0.03, depth / hi, depth / hi, mid_low)
            if sc >= 2.4 and (best is None or sc > best[0]):
                best = (sc, p1, p2, mid_low, hi, depth)
        if best and _claim(best[1][0], best[2][0]):
            _, p1, p2, mid_low, hi, depth = best
            conf = 70 if lr > 55 else 63
            add(mk("Double Top", "BEARISH", "PUT", conf,
                f"M-shaped reversal — two highs near ₹{hi:.0f}. Neckline ₹{mid_low:.0f}.",
                "Structure", vol_w=1.2, body_w=0.3,
                tgt=mid_low - depth, sl=hi + atr * 0.5,
                geometry={
                    "markers": [_pt(p1[0], p1[1]), _pt(p2[0], p2[1])],
                    "lines":   [_ln(_date_at(n - LOOK + p1[0]), mid_low, _date_at(n - 1), mid_low, "neckline")],
                }))

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
                if 0.1 < retr < 0.55 and price > cup_r * 0.99 and _relevant(cup_r):
                    add(mk("Cup & Handle", "BULLISH", "CALL", 72,
                        f"U-shaped base + shallow handle — accumulation complete. Breakout above ₹{cup_r:.0f}.",
                        "Structure", vol_w=1.2, body_w=0.3,
                        tgt=price + cup_depth,
                        sl=hdl_min - atr * 0.5,
                        geometry={
                            "markers": [_pt(cup_c.index(cup_bot), cup_bot, look=40, label="Cup")],
                            "lines":   [_ln(_date_at(n - 40), cup_r, _date_at(n - 1), cup_r, "neckline")],
                        }))

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
                if 0.1 < retr < 0.55 and price < cup_r * 1.01 and _relevant(cup_r):
                    add(mk("Inverse Cup & Handle", "BEARISH", "PUT", 72,
                        f"Inverted U + small bounce handle — distribution. Breakdown below ₹{cup_r:.0f}.",
                        "Structure", vol_w=1.2, body_w=0.3,
                        tgt=price - cup_ht,
                        sl=hdl_max + atr * 0.5,
                        geometry={
                            "markers": [_pt(cup_c.index(cup_top), cup_top, look=40, label="Cap")],
                            "lines":   [_ln(_date_at(n - 40), cup_r, _date_at(n - 1), cup_r, "neckline")],
                        }))

        # ── Triangles, Wedges, Rectangle (40-bar trendline analysis) ─────────
        # order=2 gives ~1 pivot per 5 bars — more sensitive than order=3,
        # needed because 40 bars only yields ~4-6 pivots at order=3.
        TLINE = min(n, 40)
        _th = highs[-TLINE:]
        _tl = lows[-TLINE:]
        peaks30, troughs30 = _pivots(_th, _tl, order=2)

        if len(peaks30) >= 2 and len(troughs30) >= 2:
            _res_pts = peaks30[-3:]   if len(peaks30)   >= 3 else peaks30[-2:]
            _sup_pts = troughs30[-3:] if len(troughs30) >= 3 else troughs30[-2:]
            res_slope = _slope(_res_pts)
            sup_slope = _slope(_sup_pts)
            avg_res = sum(p[1] for p in peaks30[-2:]) / 2
            avg_sup = sum(t[1] for t in troughs30[-2:]) / 2
            spread_pct = (avg_res - avg_sup) / max(avg_res, 1e-9)
            su = price * 0.001                      # min slope unit (0.1%/bar)

            # Resilience gates: a real trendline pattern's two lines must FIT
            # their pivots (not scatter), span a meaningful duration, and sit
            # NEAR the current price — so a wedge/triangle stranded far behind a
            # big move (the stale-pattern bug) is rejected. Lines are projected
            # to the latest bar for both the near-price test and the geometry.
            def _resid_atr(pts, slope):
                if len(pts) < 2:
                    return 0.0
                mx = sum(p[0] for p in pts) / len(pts); my = sum(p[1] for p in pts) / len(pts)
                b = my - slope * mx
                return max(abs(p[1] - (slope * p[0] + b)) for p in pts) / max(atr, 1e-9)
            def _edge(pts, slope):
                last = pts[-1]
                return last[1] + slope * ((TLINE - 1) - last[0])
            res_edge = _edge(_res_pts, res_slope)
            sup_edge = _edge(_sup_pts, sup_slope)
            near_price = min(abs(price - res_edge), abs(price - sup_edge)) / max(price, 1e-9) <= 0.06
            dur_ok = (_res_pts[-1][0] - _res_pts[0][0] >= 12) and (_sup_pts[-1][0] - _sup_pts[0][0] >= 12)
            fit_ok = _resid_atr(_res_pts, res_slope) <= 1.2 and _resid_atr(_sup_pts, sup_slope) <= 1.2
            _tgate = near_price and dur_ok and fit_ok

            # Two trendlines extended to the latest bar + the pivot dots they ride.
            tline_geo = {
                "markers": [_pt(p[0], p[1], look=TLINE) for p in _res_pts]
                         + [_pt(t[0], t[1], look=TLINE) for t in _sup_pts],
                "lines": [
                    _ln(_date_at(n - TLINE + _res_pts[0][0]), _res_pts[0][1],
                        _date_at(n - 1), res_edge, "resistance"),
                    _ln(_date_at(n - TLINE + _sup_pts[0][0]), _sup_pts[0][1],
                        _date_at(n - 1), sup_edge, "support"),
                ],
            }

            # ── Symmetrical Triangle ──────────────────────────────────────────
            if _tgate and res_slope < -su and sup_slope > su and 0.02 < spread_pct < 0.12:
                sig = "CALL" if (lr < 55 and le20 > le50) else "PUT" if (lr > 55 and le20 < le50) else "WAIT"
                pt  = "BULLISH" if sig == "CALL" else "BEARISH" if sig == "PUT" else "NEUTRAL"
                add(mk("Symmetrical Triangle", pt, sig, 65,
                    "Converging highs and lows — energy coiling. Breakout follows the prevailing trend.",
                    "Structure", body_w=0.2, vol_w=0.8,
                    target_r=3.0, stop_r=1.5, geometry=tline_geo))

            # ── Ascending Triangle ────────────────────────────────────────────
            elif _tgate and abs(res_slope) < su * 0.6 and sup_slope > su and spread_pct < 0.10:
                add(mk("Ascending Triangle", "BULLISH", "CALL", 68,
                    f"Flat resistance ₹{avg_res:.0f} + rising support — buyers absorbing every dip. Bullish breakout likely.",
                    "Structure", body_w=0.2, vol_w=1.0,
                    tgt=avg_res + (avg_res - avg_sup),
                    sl=avg_sup - atr * 0.5, geometry=tline_geo))

            # ── Descending Triangle ───────────────────────────────────────────
            elif _tgate and res_slope < -su and abs(sup_slope) < su * 0.6 and spread_pct < 0.10:
                add(mk("Descending Triangle", "BEARISH", "PUT", 68,
                    f"Falling resistance + flat support ₹{avg_sup:.0f} — sellers capping every rally. Bearish breakdown likely.",
                    "Structure", body_w=0.2, vol_w=1.0,
                    tgt=avg_sup - (avg_res - avg_sup),
                    sl=avg_res + atr * 0.5, geometry=tline_geo))

            # ── Rising Wedge (bearish) ────────────────────────────────────────
            elif _tgate and res_slope > su and sup_slope > res_slope + su and spread_pct < 0.10:
                add(mk("Rising Wedge", "BEARISH", "PUT", 66,
                    "Both highs and lows rising but converging upward — momentum fading, reversal ahead.",
                    "Structure", body_w=0.2, vol_w=0.8,
                    target_r=2.5, stop_r=1.5, geometry=tline_geo))

            # ── Falling Wedge (bullish) ───────────────────────────────────────
            elif _tgate and res_slope < -su and sup_slope > res_slope + su and sup_slope < 0 and spread_pct < 0.10:
                add(mk("Falling Wedge", "BULLISH", "CALL", 66,
                    "Both highs and lows falling but converging — sellers losing steam, bullish reversal ahead.",
                    "Structure", body_w=0.2, vol_w=0.8,
                    target_r=2.5, stop_r=1.5, geometry=tline_geo))

            # ── Rectangle ─────────────────────────────────────────────────────
            elif _tgate and abs(res_slope) < su * 0.6 and abs(sup_slope) < su * 0.6 and spread_pct < 0.12:
                sig = "CALL" if le20 > le50 else "PUT"
                pt  = "BULLISH" if sig == "CALL" else "BEARISH"
                add(mk("Rectangle", pt, sig, 62,
                    f"Price ranging ₹{avg_sup:.0f}–₹{avg_res:.0f} — consolidation. Breakout follows the trend.",
                    "Structure", body_w=0.2, vol_w=0.8,
                    tgt=(avg_res + (avg_res - avg_sup)) if sig == "CALL" else (avg_sup - (avg_res - avg_sup)),
                    sl=(avg_sup - atr * 0.5) if sig == "CALL" else (avg_res + atr * 0.5),
                    geometry=tline_geo))

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

                # The impulse pole — the defining leg every flag/pennant below shares.
                pole_geo = {
                    "markers": [],
                    "lines": [_ln(_date_at(n - (POLE + CONS)), pole_start,
                                  _date_at(n - CONS), pole_end, "pole")],
                }

                if pole_move > 0:   # bullish pole
                    is_pennant = c_res_slope < -su2 and c_sup_slope > su2
                    is_flag    = c_res_slope < -su2 and c_sup_slope < 0          # both drifting down
                    if is_pennant:
                        add(mk("Bullish Pennant", "BULLISH", "CALL", 70,
                            "Strong up-move + contracting triangle consolidation — continuation, breakout expected.",
                            "Structure", vol_w=1.1, body_w=0.3,
                            tgt=price + abs_pole, sl=min(cons_l) - atr * 0.5, geometry=pole_geo))
                    elif is_flag:
                        add(mk("Bull Flag", "BULLISH", "CALL", 68,
                            "Sharp rally + shallow parallel pullback — continuation pattern, upside expected.",
                            "Structure", vol_w=1.1, body_w=0.3,
                            tgt=price + abs_pole, sl=min(cons_l) - atr * 0.5, geometry=pole_geo))
                    elif sum(volumes[-CONS:]) / CONS < avg_vol * 0.8 and cons_c[-1] < cons_c[0]:
                        add(mk("Bull Flag", "BULLISH", "CALL", 65,
                            "Sharp rally then low-volume drift lower — textbook bull flag.",
                            "Structure", vol_w=0.8, body_w=0.3,
                            tgt=price + abs_pole, sl=min(cons_l) - atr * 0.5, geometry=pole_geo))

                else:               # bearish pole
                    is_pennant = c_res_slope < -su2 and c_sup_slope > su2
                    is_flag    = c_res_slope > su2 and c_sup_slope > 0           # both drifting up
                    if is_pennant:
                        add(mk("Bearish Pennant", "BEARISH", "PUT", 70,
                            "Sharp down-move + contracting triangle consolidation — continuation, breakdown expected.",
                            "Structure", vol_w=1.1, body_w=0.3,
                            tgt=price - abs_pole, sl=max(cons_h) + atr * 0.5, geometry=pole_geo))
                    elif is_flag:
                        add(mk("Bear Flag", "BEARISH", "PUT", 68,
                            "Sharp drop + shallow parallel bounce — continuation pattern, downside expected.",
                            "Structure", vol_w=1.1, body_w=0.3,
                            tgt=price - abs_pole, sl=max(cons_h) + atr * 0.5, geometry=pole_geo))
                    elif sum(volumes[-CONS:]) / CONS < avg_vol * 0.8 and cons_c[-1] > cons_c[0]:
                        add(mk("Bear Flag", "BEARISH", "PUT", 65,
                            "Sharp drop then low-volume bounce — textbook bear flag.",
                            "Structure", vol_w=0.8, body_w=0.3,
                            tgt=price - abs_pole, sl=max(cons_h) + atr * 0.5, geometry=pole_geo))

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

        # ── Drawing geometry for candle & indicator rows ──────────────────────
        # Structure patterns already carry geometry; candle patterns highlight
        # their bar(s) and indicator signals get a trigger arrow on the latest
        # bar — so EVERY screener row draws something when opened in the chart.
        _candle_bars = {"Candlestick": 1, "Two-Candle": 2, "Three-Candle": 3}
        for p in out:
            if p.get("geometry"):
                continue
            cat = p.get("category")
            if cat in _candle_bars:
                k = _candle_bars[cat]
                p["geometry"] = _candle_box(list(range(n - k, n)), p["pattern"])
            elif cat == "Indicator":
                p["geometry"] = _indicator_geo(p.get("signal"), p["pattern"])

        # ── Collapse overlapping Structure patterns ───────────────────────────
        # Per-pattern dedup already prevents same-pivot duplicates, but a
        # trendline pattern and a reversal can still land on one region. Keep the
        # single highest-confidence structure verdict per overlapping price/time
        # zone (ISO dates compare chronologically as strings).
        def _span(p):
            g = p.get("geometry") or {}
            ds = [m["date"] for m in g.get("markers", [])] \
               + [l["x0"] for l in g.get("lines", [])] + [l["x1"] for l in g.get("lines", [])]
            ps = [m["price"] for m in g.get("markers", [])] \
               + [l["y0"] for l in g.get("lines", [])] + [l["y1"] for l in g.get("lines", [])]
            return (min(ds), max(ds), min(ps), max(ps)) if ds and ps else None
        _kept = []
        _drop = set()
        for p in sorted((q for q in out if q.get("category") == "Structure" and _span(q)),
                        key=lambda q: q.get("confidence", 0), reverse=True):
            d0, d1, lo, hi = _span(p)
            if any(min(d1, k1) >= max(d0, k0) and min(hi, khi) >= max(lo, klo)
                   for (k0, k1, klo, khi) in _kept):
                _drop.add(id(p))
            else:
                _kept.append((d0, d1, lo, hi))
        if _drop:
            out = [p for p in out if id(p) not in _drop]

        return out
