"""
Hybrid Sector Rotation Service — 3-Phase Algorithm
===================================================
Phase 1: Macro-Economic Assessment  — detect India economic cycle (Early/Mid/Late/Recession)
Phase 2: Technical Strength Analysis — quantitative momentum score per sector
         • Relative Strength vs Nifty 50  (40%)
         • % Key stocks above 200-day SMA  (25%)
         • 6-month Rate of Change           (20%)
         • Volume Trend                     (15%)
         All indicators z-score normalised then weighted → composite score
         Composite maps to 5-tier colour: Deep Green / Light Green / Yellow / Orange / Deep Red
Phase 3: Portfolio Construction — Core-Satellite model, top picks, risk rules
"""

import asyncio
import logging
import statistics
import time
from datetime import datetime
from typing import Optional

from .nse_service import NseService
from .yahoo_service import YahooService

logger = logging.getLogger(__name__)

# ── NSE Sector Index Definitions ─────────────────────────────────────────────

SECTOR_INDICES = [
    {"name": "Nifty Bank",              "symbol": "NIFTY BANK",              "category": "Banking & Finance",     "nseKey": "NIFTY BANK",              "yahooTicker": "^NSEBANK"},
    {"name": "Nifty IT",                "symbol": "NIFTY IT",                "category": "Technology",            "nseKey": "NIFTY IT",                "yahooTicker": "^CNXIT"},
    {"name": "Nifty Auto",              "symbol": "NIFTY AUTO",              "category": "Automobile",            "nseKey": "NIFTY AUTO",              "yahooTicker": "^CNXAUTO"},
    {"name": "Nifty Pharma",            "symbol": "NIFTY PHARMA",            "category": "Pharmaceuticals",       "nseKey": "NIFTY PHARMA",            "yahooTicker": "^CNXPHARMA"},
    {"name": "Nifty FMCG",             "symbol": "NIFTY FMCG",             "category": "FMCG",                  "nseKey": "NIFTY FMCG",             "yahooTicker": "^CNXFMCG"},
    {"name": "Nifty Metal",             "symbol": "NIFTY METAL",             "category": "Metals & Mining",       "nseKey": "NIFTY METAL",             "yahooTicker": "^CNXMETAL"},
    {"name": "Nifty Realty",            "symbol": "NIFTY REALTY",            "category": "Real Estate",           "nseKey": "NIFTY REALTY",            "yahooTicker": "^CNXREALTY"},
    {"name": "Nifty Energy",            "symbol": "NIFTY ENERGY",            "category": "Energy & Oil",          "nseKey": "NIFTY ENERGY",            "yahooTicker": "^CNXENERGY"},
    {"name": "Nifty Media",             "symbol": "NIFTY MEDIA",             "category": "Media & Entertainment", "nseKey": "NIFTY MEDIA",             "yahooTicker": "^CNXMEDIA"},
    {"name": "Nifty Financial Services","symbol": "NIFTY FINANCIAL SERVICES","category": "Financial Services",    "nseKey": "NIFTY FINANCIAL SERVICES","yahooTicker": "^CNXFIN"},
    {"name": "Nifty PSU Bank",          "symbol": "NIFTY PSU BANK",          "category": "PSU Banking",           "nseKey": "NIFTY PSU BANK",          "yahooTicker": "^CNXPSUBANK"},
    {"name": "Nifty Consumer Durables", "symbol": "NIFTY CONSUMER DURABLES", "category": "Consumer Durables",     "nseKey": "NIFTY CONSUMER DURABLES", "yahooTicker": "^CNXCONDURAB"},
    {"name": "Nifty Oil & Gas",         "symbol": "NIFTY OIL AND GAS",       "category": "Oil & Gas",             "nseKey": "NIFTY OIL AND GAS",       "yahooTicker": "^CNXOILGAS"},
    {"name": "Nifty Healthcare",        "symbol": "NIFTY HEALTHCARE INDEX",  "category": "Healthcare",            "nseKey": "NIFTY HEALTHCARE INDEX",  "yahooTicker": "^CNXHEALTH"},
    {"name": "NIFTY 50",                "symbol": "NIFTY 50",                "category": "Broad Market",          "nseKey": "NIFTY 50",                "yahooTicker": "^NSEI"},
]

# ── Top 5 representative stocks per sector (for SMA breadth calculation) ─────

SECTOR_KEY_STOCKS: dict[str, list[str]] = {
    "NIFTY BANK":              ["HDFCBANK", "ICICIBANK", "AXISBANK", "KOTAKBANK", "SBIN"],
    "NIFTY IT":                ["TCS", "INFY", "HCLTECH", "WIPRO", "TECHM"],
    "NIFTY AUTO":              ["MARUTI", "TATAMOTORS", "BAJAJ-AUTO", "EICHERMOT", "HEROMOTOCO"],
    "NIFTY PHARMA":            ["SUNPHARMA", "CIPLA", "DRREDDY", "DIVISLAB", "LUPIN"],
    "NIFTY FMCG":              ["HINDUNILVR", "ITC", "BRITANNIA", "NESTLEIND", "DABUR"],
    "NIFTY METAL":             ["TATASTEEL", "JSWSTEEL", "HINDALCO", "COALINDIA", "SAIL"],
    "NIFTY REALTY":            ["DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE", "SOBHA"],
    "NIFTY ENERGY":            ["RELIANCE", "ONGC", "BPCL", "GAIL", "NTPC"],
    "NIFTY MEDIA":             ["ZEEL", "SUNTV", "NAZARA", "PVRINOX", "SAREGAMA"],
    "NIFTY FINANCIAL SERVICES":["BAJFINANCE", "BAJAJFINSV", "MUTHOOTFIN", "SBILIFE", "HDFCLIFE"],
    "NIFTY PSU BANK":          ["SBIN", "BANKBARODA", "PNB", "CANBK", "UCOBANK"],
    "NIFTY CONSUMER DURABLES": ["TITAN", "HAVELLS", "SIEMENS", "ABB", "VOLTAS"],
    "NIFTY OIL AND GAS":       ["RELIANCE", "ONGC", "BPCL", "GAIL", "HINDPETRO"],
    "NIFTY HEALTHCARE INDEX":  ["SUNPHARMA", "APOLLOHOSP", "MAXHEALTH", "FORTIS", "CIPLA"],
    "NIFTY 50":                ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"],
}

# ── Economic Cycle Phase Definitions (India / NSE context) ────────────────────

CYCLE_PHASES: dict[str, dict] = {
    "Early Cycle / Recovery": {
        "code": "EARLY",
        "color": "#22c55e",
        "bgColor": "#f0fdf4",
        "leadingSectors": ["NIFTY BANK", "NIFTY FINANCIAL SERVICES", "NIFTY REALTY", "NIFTY AUTO", "NIFTY CONSUMER DURABLES"],
        "characteristics": "RBI easing rates, credit growth picking up, real estate & consumption recovering from trough",
        "theorySectors": ["Banking & Financials", "Real Estate", "Auto & Consumer Durables", "IT"],
        "actionableSectors": ["NIFTY BANK", "NIFTY FINANCIAL SERVICES", "NIFTY AUTO", "NIFTY REALTY"],
        "strategy": "Scale into cyclical leaders. Focus on Light Green sectors in Banking, Financials, Auto.",
    },
    "Mid Cycle / Expansion": {
        "code": "MID",
        "color": "#3b82f6",
        "bgColor": "#eff6ff",
        "leadingSectors": ["NIFTY IT", "NIFTY AUTO", "NIFTY CONSUMER DURABLES", "NIFTY FINANCIAL SERVICES"],
        "characteristics": "GDP above trend, corporate earnings strong, broad market participation, IT exports booming",
        "theorySectors": ["IT & Technology", "Auto", "Consumer Discretionary", "Financials"],
        "actionableSectors": ["NIFTY IT", "NIFTY AUTO", "NIFTY CONSUMER DURABLES"],
        "strategy": "Hold cyclical winners. Rotate from Light Green to Deep Green. Trim if Deep Green turns extreme.",
    },
    "Late Cycle / Slowdown": {
        "code": "LATE",
        "color": "#f59e0b",
        "bgColor": "#fffbeb",
        "leadingSectors": ["NIFTY ENERGY", "NIFTY OIL AND GAS", "NIFTY METAL", "NIFTY PHARMA"],
        "characteristics": "RBI tightening, inflation elevated, commodity & defensive sectors outperform",
        "theorySectors": ["Energy & Commodities", "Metals & Mining", "Pharma & Healthcare"],
        "actionableSectors": ["NIFTY ENERGY", "NIFTY METAL", "NIFTY PHARMA"],
        "strategy": "Rotate to commodities and defensives. Reduce IT and Financials exposure. Tighten stop-losses.",
    },
    "Recession / Contraction": {
        "code": "RECESSION",
        "color": "#ef4444",
        "bgColor": "#fef2f2",
        "leadingSectors": ["NIFTY FMCG", "NIFTY PHARMA", "NIFTY HEALTHCARE INDEX"],
        "characteristics": "GDP slowing, corporate earnings declining, defensive rotation into staples and healthcare",
        "theorySectors": ["FMCG & Staples", "Pharmaceuticals", "Healthcare", "Utilities"],
        "actionableSectors": ["NIFTY FMCG", "NIFTY PHARMA", "NIFTY HEALTHCARE INDEX"],
        "strategy": "Capital preservation mode. Max allocation to defensives. Increase cash to 20-30%.",
    },
}

# ── 5-Tier Strength Classification ───────────────────────────────────────────

TIERS = [
    {"tier": "DEEP_GREEN",  "label": "Deep Green",  "color": "#16a34a", "bg": "#f0fdf4", "description": "Maximum Strength — take profits if overextended"},
    {"tier": "LIGHT_GREEN", "label": "Light Green", "color": "#4ade80", "bg": "#dcfce7", "description": "Building Strength — ideal entry zone"},
    {"tier": "YELLOW",      "label": "Neutral",     "color": "#ca8a04", "bg": "#fefce8", "description": "No clear momentum — wait for direction"},
    {"tier": "ORANGE",      "label": "Weakening",   "color": "#ea580c", "bg": "#fff7ed", "description": "Declining momentum — reduce or avoid"},
    {"tier": "DEEP_RED",    "label": "Deep Red",    "color": "#dc2626", "bg": "#fef2f2", "description": "Maximum Weakness — exit or short only"},
]

TIER_BY_NAME = {t["tier"]: t for t in TIERS}

# ── Momentum cache (4-hour TTL) ───────────────────────────────────────────────
_CACHE: dict = {}


def _get_cache() -> Optional[dict]:
    e = _CACHE.get("rotation")
    if e and time.time() < e["expiry"]:
        return e["data"]
    return None


def _get_stale() -> Optional[dict]:
    e = _CACHE.get("rotation")
    return e["data"] if e else None


def _set_cache(data: dict, ttl: int = 4 * 3600) -> None:
    _CACHE["rotation"] = {"data": data, "expiry": time.time() + ttl}


# ── Z-score helper ────────────────────────────────────────────────────────────

def _z_scores(values: list[float]) -> list[float]:
    if len(values) < 2:
        return [0.0] * len(values)
    try:
        mean = statistics.mean(values)
        stdev = statistics.pstdev(values)
        if stdev < 1e-9:
            return [0.0] * len(values)
        return [(v - mean) / stdev for v in values]
    except Exception:
        return [0.0] * len(values)


# ── Main Service ──────────────────────────────────────────────────────────────

class SectorsService:
    def __init__(self, nse: NseService, yahoo: YahooService):
        self.nse = nse
        self.yahoo = yahoo

    # ── Public endpoints ──────────────────────────────────────────────────────

    async def get_all_sectors(self) -> list[dict]:
        try:
            nse_data = await self.nse.get_sector_indices()
            if nse_data and nse_data.get("data"):
                parsed = self._parse_nse_sectors(nse_data["data"])
                if parsed:
                    return parsed
        except Exception:
            pass
        # NSE unavailable — fall back to Yahoo Finance for live prices
        return await self._get_sectors_from_yahoo()

    async def _get_sectors_from_yahoo(self) -> list[dict]:
        """Fetch sector index prices from Yahoo Finance when NSE is unavailable."""
        tasks = [self.yahoo.get_quote(s["yahooTicker"]) for s in SECTOR_INDICES]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        sectors = []
        for i, sector in enumerate(SECTOR_INDICES):
            quote = results[i] if not isinstance(results[i], Exception) else None
            if quote and quote.get("lastPrice"):
                sectors.append({
                    "name": sector["name"],
                    "symbol": sector["symbol"],
                    "category": sector["category"],
                    "lastPrice": quote.get("lastPrice", 0),
                    "change": quote.get("change", 0),
                    "pChange": quote.get("pChange", 0),
                    "open": quote.get("open"),
                    "high": quote.get("dayHigh"),
                    "low": quote.get("dayLow"),
                    "previousClose": quote.get("previousClose"),
                    "yearHigh": quote.get("fiftyTwoWeekHigh"),
                    "yearLow": quote.get("fiftyTwoWeekLow"),
                    "advances": 0,
                    "declines": 0,
                    "source": "YAHOO",
                    "yahooTicker": sector["yahooTicker"],
                })
            else:
                sectors.append({
                    "name": sector["name"],
                    "symbol": sector["symbol"],
                    "category": sector["category"],
                    "lastPrice": 0, "change": 0, "pChange": 0,
                    "advances": 0, "declines": 0,
                    "source": "UNAVAILABLE", "yahooTicker": sector["yahooTicker"],
                })
        return sorted(sectors, key=lambda s: s["pChange"], reverse=True)

    async def get_sector_rotation(self) -> dict:
        fresh = _get_cache()
        if fresh:
            return fresh

        stale = _get_stale()
        if stale:
            asyncio.create_task(self._compute_rotation())
            return stale

        return await self._compute_rotation()

    async def get_sector_detail(self, symbol: str) -> dict | None:
        sectors = await self.get_all_sectors()
        return next(
            (s for s in sectors if s["symbol"] == symbol or s["name"].lower() == symbol.lower()),
            None,
        )

    # ── NSE parsing ───────────────────────────────────────────────────────────

    def _parse_nse_sectors(self, data: list[dict]) -> list[dict]:
        results = []
        for sector in SECTOR_INDICES:
            found = next(
                (d for d in data if d.get("index") == sector["nseKey"] or d.get("indexSymbol") == sector["symbol"]),
                None,
            )
            if found:
                p_change = float(found.get("percentChange") or found.get("perChange") or 0)
                results.append({
                    "name": sector["name"],
                    "symbol": sector["symbol"],
                    "category": sector["category"],
                    "lastPrice": found.get("last") or found.get("indexValue") or 0,
                    "change": found.get("variation") or found.get("change") or 0,
                    "pChange": p_change,
                    "open": found.get("open"),
                    "high": found.get("high"),
                    "low": found.get("low"),
                    "previousClose": found.get("previousClose"),
                    "yearHigh": found.get("yearHigh"),
                    "yearLow": found.get("yearLow"),
                    "advances": int(found.get("advances") or 0),
                    "declines": int(found.get("declines") or 0),
                    "source": "NSE",
                    "yahooTicker": sector["yahooTicker"],
                })
        return sorted(results, key=lambda s: s["pChange"], reverse=True)

    def _get_default_sectors(self) -> list[dict]:
        return [
            {
                "name": s["name"], "symbol": s["symbol"], "category": s["category"],
                "lastPrice": 0, "change": 0, "pChange": 0,
                "advances": 0, "declines": 0,
                "source": "UNAVAILABLE", "yahooTicker": s["yahooTicker"],
            }
            for s in SECTOR_INDICES
        ]

    # ── Phase 2: Technical Strength (async data fetching) ─────────────────────

    async def _fetch_index_history(self, yahoo_ticker: str) -> dict:
        """Fetch 6-month price/volume history for a sector index ticker."""
        try:
            hist = await self.yahoo.get_historical_data(yahoo_ticker, days=180)
            if not hist or len(hist) < 10:
                return {"roc_6m": 0.0, "roc_3m": 0.0, "vol_trend": 1.0, "closes": []}

            closes = [h["close"] for h in hist if h.get("close")]
            volumes = [h.get("volume") or 0 for h in hist]

            if len(closes) < 2:
                return {"roc_6m": 0.0, "roc_3m": 0.0, "vol_trend": 1.0, "closes": closes}

            roc_6m = ((closes[-1] - closes[0]) / closes[0]) * 100 if closes[0] > 0 else 0.0

            mid = max(1, len(closes) // 2)
            roc_3m = ((closes[-1] - closes[mid]) / closes[mid]) * 100 if closes[mid] > 0 else 0.0

            if len(volumes) >= 40:
                recent_vol = statistics.mean([v for v in volumes[-20:] if v > 0] or [1])
                prior_vol  = statistics.mean([v for v in volumes[-40:-20] if v > 0] or [1])
                vol_trend = recent_vol / prior_vol if prior_vol > 0 else 1.0
            else:
                vol_trend = 1.0

            return {"roc_6m": roc_6m, "roc_3m": roc_3m, "vol_trend": vol_trend, "closes": closes}
        except Exception as e:
            logger.warning("History fetch failed for %s: %s", yahoo_ticker, e)
            return {"roc_6m": 0.0, "roc_3m": 0.0, "vol_trend": 1.0, "closes": []}

    async def _fetch_stock_breadth(self, symbol: str) -> dict:
        """
        Calculate % of key sector stocks above their 50-day and 200-day SMAs.
        Uses 5 representative stocks per sector.
        """
        key_stocks = SECTOR_KEY_STOCKS.get(symbol, [])
        if not key_stocks:
            return {"pct_above_50": 50.0, "pct_above_200": 50.0, "sample_size": 0}

        tasks = [self.yahoo.get_historical_data(s, days=250) for s in key_stocks]
        all_hist = await asyncio.gather(*tasks, return_exceptions=True)

        above_50, above_200, valid = 0, 0, 0
        for hist in all_hist:
            if isinstance(hist, Exception) or not hist:
                continue
            closes = [h["close"] for h in hist if h.get("close")]
            if len(closes) < 50:
                continue
            current = closes[-1]
            sma50 = statistics.mean(closes[-50:])
            above_50 += 1 if current > sma50 else 0
            if len(closes) >= 200:
                sma200 = statistics.mean(closes[-200:])
                above_200 += 1 if current > sma200 else 0
            valid += 1

        if valid == 0:
            return {"pct_above_50": 50.0, "pct_above_200": 50.0, "sample_size": 0}

        return {
            "pct_above_50":  round((above_50  / valid) * 100, 1),
            "pct_above_200": round((above_200  / valid) * 100, 1),
            "sample_size": valid,
        }

    async def _build_momentum_scores(self, sectors: list[dict]) -> dict[str, dict]:
        """
        Phase 2 core: compute composite momentum score for every sector.
        Weights: RS Trend 40% | % above 200-SMA 25% | 6m ROC 20% | Volume 15%
        """
        score_sectors = [s for s in sectors if s["symbol"] != "NIFTY 50"]

        # Fetch Nifty 50 benchmark history concurrently with all sectors
        nifty_task      = self._fetch_index_history("^NSEI")
        index_tasks     = [self._fetch_index_history(s.get("yahooTicker", "^NSEI")) for s in score_sectors]
        breadth_tasks   = [self._fetch_stock_breadth(s["symbol"]) for s in score_sectors]

        nifty_hist, all_index, all_breadth = await asyncio.gather(
            nifty_task,
            asyncio.gather(*index_tasks, return_exceptions=True),
            asyncio.gather(*breadth_tasks, return_exceptions=True),
        )

        nifty_3m = nifty_hist.get("roc_3m", 0.0)

        # Collect raw indicator values per sector
        raw: list[dict] = []
        for i, sector in enumerate(score_sectors):
            idx = all_index[i] if not isinstance(all_index[i], Exception) else {}
            brd = all_breadth[i] if not isinstance(all_breadth[i], Exception) else {}

            rs     = (idx.get("roc_3m", 0.0) - nifty_3m)   # outperformance vs benchmark
            roc_6m = idx.get("roc_6m", 0.0)
            vol    = min(idx.get("vol_trend", 1.0), 3.0)    # cap outliers at 3×
            b200   = brd.get("pct_above_200", 50.0)
            b50    = brd.get("pct_above_50",  50.0)

            raw.append({
                "symbol":         sector["symbol"],
                "rs":             rs,
                "roc_6m":         roc_6m,
                "vol_trend":      vol,
                "pct_above_200":  b200,
                "pct_above_50":   b50,
                "breadth_sample": brd.get("sample_size", 0),
            })

        # Z-score each indicator across all sectors (same scale)
        rs_z    = _z_scores([r["rs"]           for r in raw])
        roc_z   = _z_scores([r["roc_6m"]       for r in raw])
        vol_z   = _z_scores([r["vol_trend"]    for r in raw])
        b200_z  = _z_scores([r["pct_above_200"] for r in raw])

        result: dict[str, dict] = {}
        for i, r in enumerate(raw):
            composite = (
                rs_z[i]   * 0.40 +
                b200_z[i] * 0.25 +
                roc_z[i]  * 0.20 +
                vol_z[i]  * 0.15
            )
            result[r["symbol"]] = {
                "composite":      round(composite, 4),
                "rs":             round(r["rs"], 2),
                "roc_6m":         round(r["roc_6m"], 2),
                "pct_above_50":   round(r["pct_above_50"], 1),
                "pct_above_200":  round(r["pct_above_200"], 1),
                "vol_trend":      round(r["vol_trend"], 3),
                "breadthSample":  r["breadth_sample"],
                # Normalized z-scores for transparency
                "zRS":            round(rs_z[i], 3),
                "zROC":           round(roc_z[i], 3),
                "zBreadth200":    round(b200_z[i], 3),
                "zVolume":        round(vol_z[i], 3),
            }

        return result

    @staticmethod
    def _assign_tier(rank_pct: float) -> dict:
        """Map rank-percentile (0 = best, 100 = worst) to 5-tier label + colour."""
        if rank_pct <= 20:
            tier = TIER_BY_NAME["DEEP_GREEN"]
        elif rank_pct <= 40:
            tier = TIER_BY_NAME["LIGHT_GREEN"]
        elif rank_pct <= 60:
            tier = TIER_BY_NAME["YELLOW"]
        elif rank_pct <= 80:
            tier = TIER_BY_NAME["ORANGE"]
        else:
            tier = TIER_BY_NAME["DEEP_RED"]
        return {k: v for k, v in tier.items()}  # copy

    # ── Phase 1: Economic cycle detection ─────────────────────────────────────

    def _detect_economic_phase(self, momentum: dict[str, dict]) -> dict:
        if not momentum:
            info = CYCLE_PHASES["Mid Cycle / Expansion"]
            return {"phase": "Mid Cycle / Expansion", **info, "confidence": 40, "phaseScores": {}}

        phase_scores: dict[str, float] = {}
        for phase_name, info in CYCLE_PHASES.items():
            scores = [
                momentum[s]["composite"]
                for s in info["leadingSectors"]
                if s in momentum
            ]
            phase_scores[phase_name] = statistics.mean(scores) if scores else -9.0

        best_phase = max(phase_scores, key=lambda k: phase_scores[k])
        best_score = phase_scores[best_phase]
        others = [v for k, v in phase_scores.items() if k != best_phase]
        other_avg = statistics.mean(others) if others else 0.0
        gap = best_score - other_avg
        confidence = min(95, max(35, int(50 + gap * 25)))

        info = CYCLE_PHASES[best_phase]
        return {
            "phase": best_phase,
            **info,
            "confidence": confidence,
            "phaseScores": {k: round(v, 3) for k, v in phase_scores.items()},
        }

    # ── Phase 3: Portfolio logic ───────────────────────────────────────────────

    @staticmethod
    def _focus_label(tier: str) -> str:
        return {
            "DEEP_GREEN":  "STRONG BUY",
            "LIGHT_GREEN": "BUY",
            "YELLOW":      "HOLD",
            "ORANGE":      "REDUCE",
            "DEEP_RED":    "AVOID",
        }.get(tier, "HOLD")

    def _build_top_picks(
        self,
        enriched: list[dict],
        eco_phase: dict,
        theoretically_favored: list[str],
    ) -> list[dict]:
        light_green = [s for s in enriched if s.get("momentum", {}).get("tier") == "LIGHT_GREEN"]
        deep_green  = [s for s in enriched if s.get("momentum", {}).get("tier") == "DEEP_GREEN"]

        # Best entry: Light Green sectors that are theoretically favored in current phase
        ideal = [s for s in light_green if s["symbol"] in theoretically_favored]
        # Fallback: all light green, then deep green
        picks = (ideal or light_green or deep_green)[:3]

        result = []
        for s in picks:
            ms = s.get("momentum", {})
            is_theory = s["symbol"] in theoretically_favored
            result.append({
                "sector":       s["name"],
                "symbol":       s["symbol"],
                "tier":         ms.get("tier"),
                "tierLabel":    ms.get("label"),
                "color":        ms.get("color"),
                "bgColor":      ms.get("bg"),
                "composite":    ms.get("composite"),
                "rs":           ms.get("rs"),
                "roc_6m":       ms.get("roc_6m"),
                "pct_above_200":ms.get("pct_above_200"),
                "maxAllocation":"15-25% of satellite portfolio",
                "theoryMatch":  is_theory,
                "entryReason":  (
                    f"Theoretically favored in {eco_phase['phase']} + {ms.get('label','')} momentum (ideal entry)"
                    if is_theory else
                    f"{ms.get('label','')} quantitative momentum — watch for phase alignment"
                ),
                "exitRule": "Exit if tier downgrades to Orange or Red. Hard stop-loss 7-10% below entry.",
                "profitRule": "Trim 50% when sector transitions from Light Green → Deep Green (extreme greed zone).",
            })
        return result

    # ── Full rotation computation ──────────────────────────────────────────────

    async def _compute_rotation(self) -> dict:
        sectors = await self.get_all_sectors()
        score_sectors = [s for s in sectors if s["symbol"] != "NIFTY 50"]

        # ── Phase 2 ──────────────────────────────────────────────────────────
        try:
            momentum = await self._build_momentum_scores(sectors)
        except Exception as e:
            logger.error("Momentum computation failed: %s", e)
            momentum = {}

        # Rank by composite score (highest = rank 1 = Deep Green)
        ranked = sorted(momentum.keys(), key=lambda s: momentum[s]["composite"], reverse=True)
        n = len(ranked)
        for i, sym in enumerate(ranked):
            pct = (i / n) * 100 if n > 0 else 50
            tier_info = self._assign_tier(pct)
            momentum[sym].update(tier_info)
            momentum[sym]["rank"]    = i + 1
            momentum[sym]["rankPct"] = round(pct, 1)

        # ── Phase 1 ──────────────────────────────────────────────────────────
        eco_phase = self._detect_economic_phase(momentum)
        favored   = eco_phase.get("actionableSectors", [])

        # ── Enrich sector list ────────────────────────────────────────────────
        enriched: list[dict] = []
        for s in score_sectors:
            ms = momentum.get(s["symbol"], {})
            enriched.append({
                **s,
                "momentum": ms,
                "focus":    self._focus_label(ms.get("tier", "YELLOW")),
                "advanceDeclineRatio": (
                    round(s["advances"] / s["declines"], 2) if s.get("declines") else s.get("advances", 0)
                ),
            })
        enriched.sort(key=lambda s: s.get("momentum", {}).get("composite", -99), reverse=True)

        # ── Phase 3 — portfolio picks ──────────────────────────────────────────
        top_picks = self._build_top_picks(enriched, eco_phase, favored)

        # ── Market breadth ────────────────────────────────────────────────────
        advancing = sum(1 for s in score_sectors if s.get("pChange", 0) > 0)
        declining = sum(1 for s in score_sectors if s.get("pChange", 0) < 0)
        total = len(score_sectors)

        # ── Signal counts across tiers ────────────────────────────────────────
        tier_counts: dict[str, int] = {}
        for s in enriched:
            tier = s.get("momentum", {}).get("tier", "YELLOW")
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

        recommendation = (
            f"{eco_phase['phase']} detected. "
            f"Top momentum picks: {', '.join(p['sector'] for p in top_picks)}. "
            f"{eco_phase.get('strategy','')}"
        ) if top_picks else (
            f"{eco_phase['phase']} — no strong momentum sectors. Adopt defensive posture."
        )

        result = {
            "date":      datetime.utcnow().strftime("%Y-%m-%d"),
            "timestamp": datetime.utcnow().isoformat() + "Z",

            # Phase 1 output
            "economicPhase": eco_phase,

            # Phase 2 output
            "sectors":      enriched,
            "tierCounts":   tier_counts,
            "tiers":        TIERS,

            # Phase 3 output
            "portfolioStrategy": {
                "coreSatellite": {
                    "core":      "60-70% Nifty 50 / broad-market index ETFs (diversified base)",
                    "satellite": "30-40% active sector rotation — top 2-3 momentum sectors",
                },
                "topPicks":        top_picks,
                "riskManagement": {
                    "stopLoss":     "7-10% hard stop-loss below entry price",
                    "profitTaking": "Trim 50% position when sector moves Light Green → Deep Green",
                    "exitSignal":   "Full exit if tier degrades to Orange or Deep Red",
                    "cashReserve":  "5-10% cash reserve for flexibility",
                    "maxPerSector": "15-25% of total portfolio per sector",
                    "maxPerStock":  "5% of portfolio per individual stock",
                },
                "trendlessMarket": (
                    "No clear outperformer — rotate into FMCG, Pharma, Healthcare. "
                    "Raise cash allocation to 20-30%."
                ) if not any(
                    s.get("momentum", {}).get("tier") in ("DEEP_GREEN", "LIGHT_GREEN")
                    for s in enriched[:5]
                ) else None,
            },

            # Compatibility fields (used by Dashboard + existing frontend)
            "rotationPhase":   eco_phase["phase"],
            "recommendation":  recommendation,
            "topPerformers":   enriched[:5],
            "laggards":        enriched[-3:],
            "whereToBuyNow":   [p for p in enriched if p.get("momentum", {}).get("tier") in ("DEEP_GREEN", "LIGHT_GREEN")][:5],
            "currentlyFocused":[p["sector"] for p in top_picks],
            "marketBreadth": {
                "advancing":          advancing,
                "declining":          declining,
                "unchanged":          total - advancing - declining,
                "total":              total,
                "advanceDeclineRatio":round(advancing / declining, 2) if declining else advancing,
                "breadthScore":       round((advancing / total) * 100, 1) if total else 0,
            },
            "adRatio": round(advancing / declining, 2) if declining else advancing,
        }

        _set_cache(result)
        return result
