"""
Analytics layer: sector correlation, breadth history, pattern stats, top movers, sector heatmap.
All data is computed on-demand and cached in memory with TTLs.
"""
from __future__ import annotations
import asyncio
import math
import time
from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd

from .yahoo_service import YahooService
from .nse_service import NseService
from .sectors_service import SectorsService
from .patterns_service import PatternsService, _cached_patterns
from ..lib.universe import NIFTY100 as NIFTY100_SYMBOLS

# Yahoo Finance index tickers for Indian sector indices
SECTOR_YAHOO_TICKERS: dict[str, str] = {
    "NIFTY 50":                  "^NSEI",
    "NIFTY BANK":                "^NSEBANK",
    "NIFTY IT":                  "^CNXIT",
    "NIFTY AUTO":                "^CNXAUTO",
    "NIFTY PHARMA":              "^CNXPHARMA",
    "NIFTY FMCG":                "^CNXFMCG",
    "NIFTY METAL":               "^CNXMETAL",
    "NIFTY REALTY":              "^CNXREALTY",
    "NIFTY ENERGY":              "^CNXENERGY",
    "NIFTY MEDIA":               "^CNXMEDIA",
    "NIFTY FINANCIAL SERVICES":  "^CNXFINANCE",
    "NIFTY PSU BANK":            "^CNXPSUBANK",
    "NIFTY CONSUMER DURABLES":   "^CNXCONSUMERDURAB",
    "NIFTY OIL AND GAS":         "^CNXOILANDGAS",
    "NIFTY HEALTHCARE INDEX":    "^CNXHEALTH",
}

_CACHE: dict[str, dict] = {}
MAX_CACHE = 50


def _get_cache(key: str) -> Optional[Any]:
    e = _CACHE.get(key)
    if e and time.time() < e["expiry"]:
        return e["data"]
    if e:
        del _CACHE[key]
    return None


def _set_cache(key: str, data: Any, ttl: int) -> None:
    if len(_CACHE) >= MAX_CACHE:
        oldest = next(iter(_CACHE))
        del _CACHE[oldest]
    _CACHE[key] = {"data": data, "expiry": time.time() + ttl}


class AnalyticsService:
    def __init__(
        self,
        yahoo: YahooService,
        nse: NseService,
        sectors: SectorsService,
        patterns: PatternsService,
    ) -> None:
        self.yahoo = yahoo
        self.nse = nse
        self.sectors = sectors
        self.patterns = patterns

    # ── Sector correlation ────────────────────────────────────────────────────

    async def get_sector_correlation(self, days: int = 30) -> dict:
        cache_key = f"sector-corr-{days}"
        cached = _get_cache(cache_key)
        if cached:
            return cached

        sector_data: dict[str, list[float]] = {}
        fetch_errors: list[dict] = []
        skipped_short: list[str] = []

        for name, ticker in SECTOR_YAHOO_TICKERS.items():
            try:
                # ticker is e.g. "^NSEI" — YahooService now handles ^ prefix correctly
                hist = await self.yahoo.get_historical_data(ticker, days)
                if len(hist) < 5:
                    skipped_short.append(name)
                    continue
                closes = [d["close"] for d in hist if d.get("close")]
                # Log returns are statistically additive and the standard input
                # for return-correlation analysis. The previous simple-return
                # implementation produced subtly biased correlations, especially
                # on volatile sector indices.
                returns = [
                    math.log(closes[i] / closes[i - 1])
                    for i in range(1, len(closes))
                    if closes[i - 1] > 0 and closes[i] > 0
                ]
                if len(returns) >= 2:
                    sector_data[name] = returns
                else:
                    skipped_short.append(name)
                await asyncio.sleep(0.15)
            except Exception as e:
                # Track per-sector failures honestly. The previous bare `pass`
                # made provider outages indistinguishable from missing tickers.
                fetch_errors.append({"sector": name, "error": f"{type(e).__name__}: {e}"})

        # Single-point pChange fallback removed — it produced a "correlation"
        # over a single day, which is mathematically meaningless. Returning
        # `available: false` is more honest than fabricating a matrix.

        min_len = min(len(v) for v in sector_data.values()) if sector_data else 0
        if min_len < 2:
            result = {
                "available": False,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "days": days,
                "sectors": list(sector_data.keys()),
                "correlationMatrix": [],
                "topCorrelations": [],
                "topDivergences": [],
                "fetchErrors":     fetch_errors,
                "skippedSectors":  skipped_short,
                "message": "Insufficient historical data for any sector; try again during market hours",
            }
            _set_cache(cache_key, result, 1800)
            return result

        df = pd.DataFrame({k: v[-min_len:] for k, v in sector_data.items()})
        corr = df.corr()
        sectors_list = corr.columns.tolist()
        matrix = corr.values.tolist()

        pairs = []
        for i, s1 in enumerate(sectors_list):
            for j, s2 in enumerate(sectors_list):
                if j <= i:
                    continue
                pairs.append({
                    "sector1": s1, "sector2": s2,
                    "correlation": round(float(corr.loc[s1, s2]), 3),
                })
        pairs_sorted = sorted(pairs, key=lambda p: abs(p["correlation"]), reverse=True)

        result = {
            "available": True,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "days": days,
            "returnsMethod":   "log",
            "observationsPerSector": min_len,
            "sectors": sectors_list,
            "correlationMatrix": [[round(float(v), 3) for v in row] for row in matrix],
            "topCorrelations": [p for p in pairs_sorted if p["correlation"] >= 0.6][:10],
            "topDivergences":  [p for p in pairs_sorted if p["correlation"] <= -0.2][:5],
            "fetchErrors":     fetch_errors,
            "skippedSectors":  skipped_short,
        }
        _set_cache(cache_key, result, 3600)
        return result

    # ── Breadth history ───────────────────────────────────────────────────────

    async def get_breadth_history(self, days: int = 30) -> dict:
        cache_key = f"breadth-{days}"
        cached = _get_cache(cache_key)
        if cached:
            return cached

        # Use a broad sample of Nifty100 for advance/decline tracking
        sample = NIFTY100_SYMBOLS[:40]
        history_by_sym: dict[str, list[dict]] = {}
        for sym in sample:
            try:
                h = await self.yahoo.get_historical_data(sym, days + 5)
                if len(h) >= 2:
                    history_by_sym[sym] = h[-(days):]
                await asyncio.sleep(0.12)
            except Exception:
                pass

        if not history_by_sym:
            result = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "days": days,
                "stocksTracked": 0,
                "breadthSeries": [],
                "summary": {"avgAdvances": 0, "avgDeclines": 0, "bullishDays": 0, "bearishDays": 0},
            }
            _set_cache(cache_key, result, 3600)
            return result

        min_len = min(len(v) for v in history_by_sym.values())
        breadth_series = []
        for day_idx in range(1, min_len):
            date = list(history_by_sym.values())[0][day_idx]["date"]
            advances = declines = unchanged = 0
            for h in history_by_sym.values():
                prev_close = h[day_idx - 1]["close"]
                curr_close = h[day_idx]["close"]
                if curr_close > prev_close:
                    advances += 1
                elif curr_close < prev_close:
                    declines += 1
                else:
                    unchanged += 1
            total = advances + declines + unchanged
            # When declines == 0 the ratio is undefined (division by zero).
            # The old code returned `float(advances)` here, which silently
            # mixed a *count* into a *ratio* — a 25-advance day looked like
            # a "25:1" breadth ratio. Returning None and a separate flag
            # is honest.
            ad_ratio: Optional[float] = round(advances / declines, 2) if declines > 0 else None
            breadth_series.append({
                "date": date,
                "advances": advances,
                "declines": declines,
                "unchanged": unchanged,
                "total": total,
                "adRatio": ad_ratio,
                "oneSidedAdvance": declines == 0 and advances > 0,
                "breadthScore": round(advances / total * 100, 1) if total > 0 else 0,
            })

        avg_adv = sum(b["advances"] for b in breadth_series) / len(breadth_series) if breadth_series else 0
        avg_dec = sum(b["declines"] for b in breadth_series) / len(breadth_series) if breadth_series else 0
        result = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "days": days,
            "stocksTracked": len(history_by_sym),
            "breadthSeries": breadth_series,
            "summary": {
                "avgAdvances": round(avg_adv, 1),
                "avgDeclines": round(avg_dec, 1),
                "bullishDays": sum(1 for b in breadth_series if b["advances"] > b["declines"]),
                "bearishDays": sum(1 for b in breadth_series if b["advances"] < b["declines"]),
            },
        }
        _set_cache(cache_key, result, 3600)
        return result

    # ── Top movers ────────────────────────────────────────────────────────────

    # Momentum-score weighting: 60% on |%change|, 40% on volume scaled to
    # millions of shares. Tuned so a typical mid-cap +3% move on 2M volume
    # scores ~2.6, comparable to a +2% move on 5M volume — i.e. the score
    # ranks intensity of activity, not direction. The weights are surfaced
    # in the API response so callers can show the formula and the user
    # isn't left guessing at magic numbers.
    _MOMENTUM_PRICE_W = 0.60
    _MOMENTUM_VOL_W = 0.40
    _MOMENTUM_VOL_DIVISOR = 1_000_000  # volume scaled to "millions of shares"

    async def get_top_movers(self) -> dict:
        cache_key = "top-movers"
        cached = _get_cache(cache_key)
        if cached:
            return cached

        # Pull quotes for full Nifty100
        movers = []
        for sym in NIFTY100_SYMBOLS:
            try:
                q = await self.yahoo.get_quote(sym)
                if q:
                    pc = q.get("pChange") or 0
                    vol = q.get("volume") or 0
                    price = q.get("lastPrice") or 0
                    score = (
                        abs(pc) * self._MOMENTUM_PRICE_W
                        + (vol / self._MOMENTUM_VOL_DIVISOR) * self._MOMENTUM_VOL_W
                    )
                    movers.append({
                        "symbol": sym,
                        "companyName": q.get("companyName", sym),
                        "lastPrice": price,
                        "change": round(q.get("change") or 0, 2),
                        "pChange": round(pc, 2),
                        "volume": vol,
                        "momentumScore": round(score, 2),
                    })
                await asyncio.sleep(0.12)
            except Exception:
                pass

        gainers = sorted(movers, key=lambda s: s["pChange"], reverse=True)[:10]
        losers  = sorted(movers, key=lambda s: s["pChange"])[:10]
        most_active = sorted(movers, key=lambda s: s.get("volume") or 0, reverse=True)[:10]
        momentum_meta = {
            "priceWeight":     self._MOMENTUM_PRICE_W,
            "volumeWeight":    self._MOMENTUM_VOL_W,
            "volumeDivisor":   self._MOMENTUM_VOL_DIVISOR,
            "formula":         "abs(pChange) * priceWeight + (volume / volumeDivisor) * volumeWeight",
        }
        result = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "totalScanned": len(movers),
            "gainers": gainers,
            "losers": losers,
            "mostActive": most_active,
            "momentumWeights": momentum_meta,
        }
        _set_cache(cache_key, result, 1800)
        return result

    # ── Pattern stats ─────────────────────────────────────────────────────────

    async def get_pattern_stats(self) -> dict:
        cache_key = "pattern-stats"
        cached = _get_cache(cache_key)
        if cached:
            return cached

        patterns = _cached_patterns
        if not patterns:
            patterns = await self.patterns.run_scan()

        stats_by_pattern: dict[str, dict] = {}
        for p in patterns:
            name = p["pattern"]
            if name not in stats_by_pattern:
                stats_by_pattern[name] = {
                    "pattern": name,
                    "category": p.get("category", "Unknown"),
                    "signal": p.get("signal", "NEUTRAL"),
                    "detections": 0,
                    "avgConfidence": 0.0,
                    "symbols": [],
                    "successCount": 0,
                    "totalChecked": 0,
                    "successRate": None,
                }
            entry = stats_by_pattern[name]
            entry["detections"] += 1
            entry["avgConfidence"] += p.get("confidence") or 0
            if p.get("symbol") and p["symbol"] not in entry["symbols"]:
                entry["symbols"].append(p["symbol"])

        for name, entry in stats_by_pattern.items():
            entry["avgConfidence"] = round(
                entry["avgConfidence"] / entry["detections"], 1
            ) if entry["detections"] > 0 else 0
            hits = 0
            checked = 0
            for sym in entry["symbols"][:5]:
                try:
                    h = await self.yahoo.get_historical_data(sym, 15)
                    if len(h) < 6:
                        continue
                    price_at_detection = h[-6]["close"]
                    price_5d_later     = h[-1]["close"]
                    expected_up = entry["signal"] == "CALL"
                    actual_up   = price_5d_later > price_at_detection
                    if expected_up == actual_up:
                        hits += 1
                    checked += 1
                    await asyncio.sleep(0.1)
                except Exception:
                    pass
            if checked > 0:
                entry["successCount"] = hits
                entry["totalChecked"] = checked
                entry["successRate"]  = round(hits / checked * 100, 1)

        stats_list = sorted(
            stats_by_pattern.values(), key=lambda s: s["avgConfidence"], reverse=True
        )
        call_stats = [s for s in stats_list if s["signal"] == "CALL"]
        put_stats  = [s for s in stats_list if s["signal"] == "PUT"]
        best_rate  = sorted(
            [s for s in stats_list if s.get("successRate") is not None],
            key=lambda s: s["successRate"], reverse=True,
        )[:5]

        result = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "totalPatternsTracked": len(stats_list),
            "stats": stats_list,
            "callPatterns": call_stats,
            "putPatterns":  put_stats,
            "highestSuccessRate": best_rate,
        }
        _set_cache(cache_key, result, 7200)
        return result

    # ── Sector heatmap ────────────────────────────────────────────────────────

    async def get_sector_heatmap(self) -> dict:
        cache_key = "sector-heatmap"
        cached = _get_cache(cache_key)
        if cached:
            return cached

        live_sectors = await self.sectors.get_all_sectors()
        heatmap: list[dict] = []

        for s in live_sectors:
            ticker = SECTOR_YAHOO_TICKERS.get(s["symbol"])
            weekly: list[dict] = []
            if ticker:
                try:
                    h = await self.yahoo.get_historical_data(ticker, 10)
                    closes = [d["close"] for d in h if d.get("close")]
                    dates  = [d["date"]  for d in h if d.get("close")]
                    for i in range(1, min(6, len(closes))):
                        pc = (closes[i] - closes[i - 1]) / closes[i - 1] * 100
                        weekly.append({"date": dates[i], "pChange": round(pc, 2)})
                    await asyncio.sleep(0.12)
                except Exception:
                    pass

            pc_today = round(s.get("pChange") or 0, 2)
            heatmap.append({
                "name": s["name"],
                "symbol": s["symbol"],
                "category": s.get("category", ""),
                "todayPChange": pc_today,
                "lastPrice": s.get("lastPrice"),
                "trend": s.get("focus", "HOLD"),
                "weeklyChanges": weekly,
                "color": (
                    "green"  if pc_today > 1.5  else
                    "lime"   if pc_today > 0     else
                    "salmon" if pc_today > -1.5  else
                    "red"
                ),
            })

        advancing = sum(1 for h in heatmap if h["todayPChange"] > 0)
        result = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "sectors": heatmap,
            "overallBias": "BULLISH" if advancing > len(heatmap) // 2 else "BEARISH",
            "advancing": advancing,
            "declining": len(heatmap) - advancing,
        }
        _set_cache(cache_key, result, 1800)
        return result
