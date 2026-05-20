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
import json
import logging
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .nse_service import NseService
from .yahoo_service import YahooService
from . import market_cache_service as _disk

logger = logging.getLogger(__name__)

# Persistent rotation-state file (used for phase hysteresis across restarts).
_STATE_FILE: Path = Path(__file__).parent.parent.parent / "market_cache" / "rotation_state.json"


def _load_rotation_state() -> Optional[dict]:
    try:
        with open(_STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _save_rotation_state(state: dict) -> None:
    """Atomically persist rotation state.

    Writes to a temp file in the same directory, then `os.replace` swaps
    it in. Two parallel writes either both succeed (last writer wins) or
    one is replaced by the other — the file never appears half-written or
    truncated to a reader, which would break `json.load` on the next call.
    """
    import os
    import tempfile
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix=".rotation_state.", suffix=".tmp", dir=str(_STATE_FILE.parent)
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f)
            os.replace(tmp, _STATE_FILE)
        except Exception:
            # Make sure we don't leak temp files on a failed write
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError as e:
        logger.warning("rotation_state.json save failed: %s", e)

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
        # Weighted leaders/laggards: leaders should outperform, laggards should
        # underperform.  Phase score = w_avg(leaders.composite) − w_avg(laggards.composite).
        "leadingWeights": {
            "NIFTY BANK": 1.0, "NIFTY FINANCIAL SERVICES": 1.0,
            "NIFTY REALTY": 1.0, "NIFTY AUTO": 0.7, "NIFTY CONSUMER DURABLES": 0.7,
        },
        "laggingWeights": {
            "NIFTY FMCG": 0.6, "NIFTY PHARMA": 0.4, "NIFTY HEALTHCARE INDEX": 0.4,
        },
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
        "leadingWeights": {
            "NIFTY IT": 1.0, "NIFTY AUTO": 0.9, "NIFTY CONSUMER DURABLES": 0.8,
            "NIFTY FINANCIAL SERVICES": 0.8,
        },
        "laggingWeights": {
            "NIFTY FMCG": 0.6, "NIFTY PHARMA": 0.5, "NIFTY ENERGY": 0.4,
            "NIFTY HEALTHCARE INDEX": 0.4,
        },
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
        "leadingWeights": {
            "NIFTY ENERGY": 1.0, "NIFTY OIL AND GAS": 1.0, "NIFTY METAL": 1.0,
            "NIFTY PHARMA": 0.5,
        },
        "laggingWeights": {
            "NIFTY IT": 0.7, "NIFTY REALTY": 0.6, "NIFTY CONSUMER DURABLES": 0.5,
            "NIFTY AUTO": 0.4,
        },
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
        "leadingWeights": {
            "NIFTY FMCG": 1.0, "NIFTY HEALTHCARE INDEX": 1.0, "NIFTY PHARMA": 0.8,
        },
        "laggingWeights": {
            "NIFTY BANK": 1.0, "NIFTY METAL": 1.0, "NIFTY AUTO": 0.8,
            "NIFTY REALTY": 0.8, "NIFTY IT": 0.5, "NIFTY ENERGY": 0.4,
        },
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
_CACHE_VERSION: int = 0


def _flush_if_state_changed() -> None:
    """Drop the rotation cache whenever the market state transitions."""
    global _CACHE_VERSION
    v = _disk.cache_version()
    if v != _CACHE_VERSION:
        _CACHE.clear()
        _CACHE_VERSION = v


def _get_cache() -> Optional[dict]:
    _flush_if_state_changed()
    e = _CACHE.get("rotation")
    if e and time.time() < e["expiry"]:
        return e["data"]
    return None


def _get_stale() -> Optional[dict]:
    _flush_if_state_changed()
    e = _CACHE.get("rotation")
    return e["data"] if e else None


def _set_cache(data: dict, ttl: int = 4 * 3600) -> None:
    _flush_if_state_changed()
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
    def __init__(self, nse: NseService, yahoo: YahooService, price=None):
        self.nse = nse
        self.yahoo = yahoo
        # PriceService is the canonical EOD-overlay source. Imported lazily
        # to avoid a circular import (PriceService → sectors via routes).
        if price is None:
            from .price_service import PriceService
            price = PriceService(nse, yahoo)
        self.price = price

    # ── Public endpoints ──────────────────────────────────────────────────────

    async def get_all_sectors(self) -> list[dict]:
        as_of  = _disk._now_ist().isoformat()
        state  = _disk.current_market_state()
        market_closed = not _disk.is_market_open()

        sectors: list[dict] = []
        disk_by_symbol: dict[str, dict] = {}

        # When the market is closed prefer sealed disk snapshots for the
        # sector indices so we don't re-hit NSE on every page refresh —
        # if NSE is briefly unreachable the sector cards still show the
        # official close, identical to the per-stock and history pages.
        if market_closed:
            sealed_now = 0
            try:
                sealed_now = await self._ensure_sector_index_snapshots()
            except Exception as e:
                logger.debug("Sector index seal-on-read failed: %s", e)
            disk_by_symbol = self._build_sectors_from_disk()
            # Ops visibility: surface how many sector indices ended up
            # served from sealed disk vs needed live fallback.
            logger.info(
                "Sector index seal/disk status: sealed_now=%d disk_ready=%d/%d (state=%s)",
                sealed_now, len(disk_by_symbol), len(SECTOR_INDICES), state,
            )
            if len(disk_by_symbol) == len(SECTOR_INDICES):
                sectors = sorted(
                    disk_by_symbol.values(),
                    key=lambda x: (x["pChange"] is None, -(x["pChange"] or 0)),
                )

        # Live path — open market, or some disk snapshots are missing.
        # Partial-disk merge below replaces any sector that DOES have a
        # sealed disk version with the disk version, so a single missing
        # index doesn't force every sector to re-hit NSE.
        if not sectors:
            try:
                nse_data = await self.nse.get_sector_indices()
                if nse_data and nse_data.get("data"):
                    parsed = self._parse_nse_sectors(nse_data["data"])
                    if parsed:
                        sectors = parsed
            except Exception:
                pass
        if not sectors:
            # NSE unavailable — fall back to Yahoo Finance for live prices
            sectors = await self._get_sectors_from_yahoo()

        # Partial-disk overlay: prefer the sealed NSE close for any sector
        # we already have on disk, even if the rest came from live.
        # Re-sort by updated pChange so ranking reflects post-overlay values.
        if market_closed and disk_by_symbol:
            sectors = [
                disk_by_symbol.get((s.get("symbol") or "").upper(), s)
                if (s.get("symbol") or "").upper() in disk_by_symbol
                else s
                for s in sectors
            ]
            sectors.sort(key=lambda x: x.get("pChange") or 0, reverse=True)

        # NOTE: closed-market disk overlay is handled above by the
        # `disk_by_symbol` partial-merge which enforces the strict
        # sealed-snapshot contract (eodSealed + source==NSE +
        # eodDate==today). We deliberately do NOT run a second lax
        # overlay here — relabeling a Yahoo-sealed payload as
        # source="NSE" would violate the official-close guarantee.

        for s in sectors:
            s.setdefault("asOf", as_of)
            s.setdefault("marketState", state)
            s.setdefault("source", "NSE")
            s.setdefault("servedFrom", "PRICE_SERVICE")
        return sectors

    async def _get_sectors_from_yahoo(self) -> list[dict]:
        """NSE-down fallback. Routed through PriceService.get_quote_with_meta
        so the EOD overlay still applies and provenance is uniform with the
        rest of the app (source=NSE/YAHOO, servedFrom=PRICE_SERVICE/DISK_EOD).
        """
        tasks = [self.price.get_quote_with_meta(s["yahooTicker"]) for s in SECTOR_INDICES]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        sectors = []
        for i, sector in enumerate(SECTOR_INDICES):
            snap = results[i] if not isinstance(results[i], Exception) else None
            quote = (snap or {}).get("quote") if snap else None
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
                    "source":     snap.get("source", "YAHOO"),
                    "servedFrom": snap.get("servedFrom", "PRICE_SERVICE"),
                    "asOf":       snap.get("asOf"),
                    "marketState":snap.get("marketState"),
                    "eodSealed":  snap.get("eodSealed", False),
                    "eodDate":    snap.get("eodDate"),
                    "yahooTicker": sector["yahooTicker"],
                })
            else:
                # Quote unavailable — surface None so the UI renders "—"
                # instead of a misleading "₹0 / 0.00%". Sort failures last.
                sectors.append({
                    "name": sector["name"],
                    "symbol": sector["symbol"],
                    "category": sector["category"],
                    "lastPrice": None, "change": None, "pChange": None,
                    "advances": 0, "declines": 0,
                    "source": "NSE", "servedFrom": "UNAVAILABLE",
                    "yahooTicker": sector["yahooTicker"],
                })
        return sorted(sectors, key=lambda s: (s["pChange"] is None, -(s["pChange"] or 0)))

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
        return sorted(results, key=lambda s: (s["pChange"] is None, -(s["pChange"] or 0)))

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

    # ── Sector-index disk snapshot helpers ────────────────────────────────────

    async def _ensure_sector_index_snapshots(self) -> int:
        """When the market is CLOSED/WEEKEND, seal a daily OHLC snapshot
        for every NIFTY sector index that's still missing one on disk, so
        subsequent /sectors requests can serve the official close from
        disk instead of re-hitting NSE.

        The seal source is **NSE's official `/api/allIndices` payload**
        (one HTTP call covers every index) — never Yahoo. NSE doesn't
        publish a working public endpoint for daily index history, so we
        synthesize a 2-row OHLC snapshot per sector from the index quote:

            row[-2] = { close: previousClose }                # prior session
            row[-1] = { open, high, low, close: last }        # today's EOD

        That's enough for the existing overlay path (which reads
        `rows[-1].close` and `rows[-2].close` to derive change/pChange)
        and for the admin audit (which compares `rows[-1].close` against
        the sector page).

        If NSE is unreachable we leave the disk empty for that index —
        /sectors then keeps using its existing live + Yahoo fallback path
        (cards may show a slightly different Yahoo price, exactly as
        documented in the consistency contract).

        Returns the number of indices that were freshly sealed.
        """
        # Only seal during true post-close states (CLOSED / WEEKEND).
        # During PRE_OPEN there's nothing to seal yet — the previous
        # session is already sealed and today's close doesn't exist —
        # so attempting to write would just churn the cache with a
        # non-canonical row.
        state = _disk.current_market_state()
        if state not in ("CLOSED", "WEEKEND"):
            return 0

        # Skip the round-trip to NSE if every sector already has an
        # NSE-sealed snapshot for today.
        eod_date_now = _disk._eod_date_for(state)
        needs: set[str] = set()
        for s in SECTOR_INDICES:
            payload = _disk.load_with_meta(s["symbol"], 30)
            if not (
                payload
                and payload.get("eodSealed")
                and payload.get("data")
                and (payload.get("source") or "").upper() == "NSE"
                and payload.get("eodDate") == eod_date_now
            ):
                needs.add(s["symbol"])
        if not needs:
            return 0

        try:
            nse_payload = await self.nse.get_sector_indices()
        except Exception as e:
            logger.debug("Sector index seal: NSE all-indices fetch failed: %s", e)
            return 0
        rows = (nse_payload or {}).get("data") or []
        if not rows:
            return 0

        # Map every NSE row by both index name and indexSymbol for robust lookup
        by_key: dict[str, dict] = {}
        for r in rows:
            for k in (r.get("index"), r.get("indexSymbol")):
                if k:
                    by_key[str(k).strip().upper()] = r

        eod_date  = _disk._eod_date_for(_disk.current_market_state())
        prev_date = self._previous_trading_date(eod_date)
        sealed = 0
        for s in SECTOR_INDICES:
            sym = s["symbol"]
            if sym not in needs:
                continue
            row = by_key.get(sym.upper()) or by_key.get((s["nseKey"] or "").upper())
            if not row:
                continue
            try:
                last  = float(row.get("last") or row.get("indexValue") or 0)
                prev  = float(row.get("previousClose") or 0)
                if last <= 0:
                    continue
                open_ = float(row.get("open")  or last)
                high  = float(row.get("high")  or last)
                low   = float(row.get("low")   or last)
            except (TypeError, ValueError):
                continue

            data = []
            if prev > 0:
                data.append({
                    "date":   prev_date,
                    "open":   prev, "high": prev, "low": prev,
                    "close":  prev, "volume": 0,
                })
            data.append({
                "date":   eod_date,
                "open":   open_, "high": high, "low": low,
                "close":  last,  "volume": 0,
            })
            try:
                _disk.save_to_disk(sym, 90, data, source="NSE")
                sealed += 1
            except Exception as e:
                logger.debug("Sector index disk save failed for %s: %s", sym, e)
        return sealed

    @staticmethod
    def _previous_trading_date(eod_date: str) -> str:
        """Return the trading day immediately before `eod_date` (YYYY-MM-DD)."""
        from datetime import datetime, timedelta
        try:
            d = datetime.strptime(eod_date, "%Y-%m-%d").date()
        except Exception:
            d = _disk._now_ist().date()
        d -= timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d.isoformat()

    def _build_sectors_from_disk(self) -> dict[str, dict]:
        """Return `{symbol: sector_dict}` for every sector that has a
        valid NSE-sealed snapshot on disk for today's EOD date.

        Result may be empty or partial — the caller merges any missing
        sectors with live data so a single missing index doesn't force
        every sector to re-hit NSE.

        Eligibility (defensive correctness): payload must be `eodSealed`,
        non-empty `data`, `source == "NSE"`, and `eodDate` must match the
        current trading-day EOD date.
        """
        state    = _disk.current_market_state()
        eod_date = _disk._eod_date_for(state)
        out: dict[str, dict] = {}
        for s in SECTOR_INDICES:
            payload = _disk.load_with_meta(s["symbol"], 30)
            if not (
                payload
                and payload.get("eodSealed")
                and payload.get("data")
                and (payload.get("source") or "").upper() == "NSE"
                and payload.get("eodDate") == eod_date
            ):
                continue
            rows = payload["data"]
            last = rows[-1] if rows else None
            prev = rows[-2] if len(rows) >= 2 else None
            if not last or last.get("close") is None:
                continue

            eod_close = round(float(last["close"]), 2)
            eod_prev  = (
                round(float(prev["close"]), 2)
                if prev and prev.get("close") is not None
                else None
            )
            change  = round(eod_close - eod_prev, 2) if eod_prev is not None else 0
            pchange = round((eod_close - eod_prev) / eod_prev * 100, 4) if eod_prev else 0

            out[s["symbol"]] = {
                "name":          s["name"],
                "symbol":        s["symbol"],
                "category":      s["category"],
                "lastPrice":     eod_close,
                "change":        change,
                "pChange":       pchange,
                "open":          round(float(last["open"]),  2) if last.get("open")  is not None else None,
                "high":          round(float(last["high"]),  2) if last.get("high")  is not None else None,
                "low":           round(float(last["low"]),   2) if last.get("low")   is not None else None,
                "previousClose": eod_prev,
                "advances":      0,
                "declines":      0,
                "source":        "NSE",
                "servedFrom":    "DISK_EOD",
                "eodSealed":     True,
                "eodDate":       payload.get("eodDate") or eod_date,
                "yahooTicker":   s["yahooTicker"],
            }
        return out

    # ── Phase 2: Technical Strength (async data fetching) ─────────────────────

    async def _fetch_index_history(self, yahoo_ticker: str) -> dict:
        """Fetch 6-month price/volume history for a sector index ticker.

        Returns a dict with `data_ok=True` when usable history is present.
        On any failure / insufficient data, returns `data_ok=False` so callers
        can EXCLUDE the sector from z-score ranking instead of treating it
        as a neutral data point (which previously biased rankings).
        """
        empty = {"roc_6m": None, "roc_3m": None, "vol_trend": None, "closes": [], "data_ok": False}
        try:
            hist = await self.yahoo.get_historical_data(yahoo_ticker, days=180)
            if not hist or len(hist) < 10:
                return empty

            closes = [h["close"] for h in hist if h.get("close")]
            volumes = [h.get("volume") or 0 for h in hist]

            if len(closes) < 2 or closes[0] <= 0:
                return empty

            roc_6m = ((closes[-1] - closes[0]) / closes[0]) * 100

            mid = max(1, len(closes) // 2)
            if closes[mid] <= 0:
                return empty
            roc_3m = ((closes[-1] - closes[mid]) / closes[mid]) * 100

            if len(volumes) >= 40:
                recent_vol = statistics.mean([v for v in volumes[-20:] if v > 0] or [1])
                prior_vol  = statistics.mean([v for v in volumes[-40:-20] if v > 0] or [1])
                vol_trend = recent_vol / prior_vol if prior_vol > 0 else 1.0
            else:
                vol_trend = 1.0

            return {
                "roc_6m": roc_6m, "roc_3m": roc_3m, "vol_trend": vol_trend,
                "closes": closes, "data_ok": True,
            }
        except Exception as e:
            logger.warning("History fetch failed for %s: %s", yahoo_ticker, e)
            return empty

    async def _fetch_stock_breadth(self, symbol: str) -> dict:
        """
        Calculate % of key sector stocks above their 50-day and 200-day SMAs.
        Uses 5 representative stocks per sector.

        Bug-fix: previously incremented a single `valid` counter for any stock
        with ≥50 closes, even when 200-SMA was never computed — making the
        denominator wrong and reporting 0% when most stocks simply lacked a
        full 200-bar history. Now tracks `valid_50` and `valid_200` separately
        and returns `None` when a window cannot be measured (caller imputes
        the cross-sector median so missing data doesn't bias the ranking).
        """
        key_stocks = SECTOR_KEY_STOCKS.get(symbol, [])
        if not key_stocks:
            return {"pct_above_50": None, "pct_above_200": None,
                    "sample_size_50": 0, "sample_size_200": 0, "sample_size": 0}

        tasks = [self.yahoo.get_historical_data(s, days=250) for s in key_stocks]
        all_hist = await asyncio.gather(*tasks, return_exceptions=True)

        above_50 = above_200 = valid_50 = valid_200 = 0
        for hist in all_hist:
            if isinstance(hist, Exception) or not hist:
                continue
            closes = [h["close"] for h in hist if h.get("close")]
            if len(closes) >= 50:
                sma50 = statistics.mean(closes[-50:])
                above_50 += 1 if closes[-1] > sma50 else 0
                valid_50 += 1
            if len(closes) >= 200:
                sma200 = statistics.mean(closes[-200:])
                above_200 += 1 if closes[-1] > sma200 else 0
                valid_200 += 1

        return {
            "pct_above_50":   round((above_50  / valid_50)  * 100, 1) if valid_50  else None,
            "pct_above_200":  round((above_200 / valid_200) * 100, 1) if valid_200 else None,
            "sample_size_50":  valid_50,
            "sample_size_200": valid_200,
            "sample_size":     valid_50,  # back-compat alias
        }

    async def _build_momentum_scores(
        self, sectors: list[dict]
    ) -> tuple[dict[str, dict], list[str], dict]:
        """
        Phase 2 core: compute composite momentum score for every sector.
        Weights: RS 35% | %>200-SMA 20% | %>50-SMA 15% | 6m ROC 20% | Volume 10%

        Returns (scored_sectors, excluded_symbols, nifty_hist).

        Bug fixes vs prior version:
          • Sectors whose index history fetch FAILS are excluded entirely
            instead of being injected as neutral zeros (which silently biased
            the ranking — failed sectors would clump around `-nifty_3m`).
          • Missing breadth values are median-imputed (per-window) so a sector
            with too-short stock history doesn't drag its breadth score to 0.
          • `pct_above_50` is now actually used in the composite (was fetched
            but ignored before).
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

        # Benchmark availability — if the Nifty 50 history fetch fails, we
        # CANNOT meaningfully compute relative-strength. Rather than silently
        # using 0.0 (which turns RS into absolute 3-month ROC and biases the
        # ranking), we drop the RS component entirely and redistribute its
        # weight to the remaining indicators. The reliability flag is
        # surfaced on every sector for UI transparency.
        benchmark_ok = bool(nifty_hist.get("data_ok"))
        nifty_3m = nifty_hist.get("roc_3m") if benchmark_ok else 0.0
        if not benchmark_ok:
            logger.warning("Nifty benchmark history unavailable — RS component dropped")

        # Collect raw indicator values per sector — EXCLUDING sectors with
        # no usable index history (no ghost-rank fabrication).
        raw: list[dict] = []
        excluded: list[str] = []
        for i, sector in enumerate(score_sectors):
            idx = all_index[i] if not isinstance(all_index[i], Exception) else None
            brd = all_breadth[i] if not isinstance(all_breadth[i], Exception) else {}

            if not idx or not idx.get("data_ok"):
                excluded.append(sector["symbol"])
                continue

            rs     = idx["roc_3m"] - nifty_3m              # outperformance vs benchmark
            roc_6m = idx["roc_6m"]
            vol    = min(idx["vol_trend"], 3.0)            # cap outliers at 3×

            raw.append({
                "symbol":          sector["symbol"],
                "rs":              rs,
                "roc_6m":          roc_6m,
                "vol_trend":       vol,
                "pct_above_200":   brd.get("pct_above_200"),  # may be None
                "pct_above_50":    brd.get("pct_above_50"),   # may be None
                "breadth_sample":  brd.get("sample_size_50", brd.get("sample_size", 0)),
                "breadth_sample_200": brd.get("sample_size_200", 0),
            })

        if not raw:
            return {}, excluded, nifty_hist

        # Median-impute missing breadth so absent data doesn't bias rank.
        # If a breadth window has too FEW native data points (< MIN_NATIVE),
        # treat the whole indicator as unreliable: zero-weight it and
        # redistribute its weight proportionally to RS + ROC. This stops
        # one outlier sector's breadth from dictating the entire ranking.
        MIN_NATIVE = 3
        b200_present = [r["pct_above_200"] for r in raw if r["pct_above_200"] is not None]
        b50_present  = [r["pct_above_50"]  for r in raw if r["pct_above_50"]  is not None]
        b200_reliable = len(b200_present) >= MIN_NATIVE
        b50_reliable  = len(b50_present)  >= MIN_NATIVE
        b200_med = statistics.median(b200_present) if b200_present else 50.0
        b50_med  = statistics.median(b50_present)  if b50_present  else 50.0
        for r in raw:
            if r["pct_above_200"] is None:
                r["pct_above_200"] = b200_med
                r["b200_imputed"] = True
            else:
                r["b200_imputed"] = False
            if r["pct_above_50"] is None:
                r["pct_above_50"] = b50_med
                r["b50_imputed"] = True
            else:
                r["b50_imputed"] = False

        # Z-score each indicator across all sectors (same scale)
        rs_z    = _z_scores([r["rs"]            for r in raw])
        roc_z   = _z_scores([r["roc_6m"]        for r in raw])
        vol_z   = _z_scores([r["vol_trend"]     for r in raw])
        b200_z  = _z_scores([r["pct_above_200"] for r in raw])
        b50_z   = _z_scores([r["pct_above_50"]  for r in raw])

        # Dynamic weights — drop unreliable breadth and redistribute.
        w_rs, w_b200, w_b50, w_roc, w_vol = 0.35, 0.20, 0.15, 0.20, 0.10
        if not b200_reliable:
            w_rs += w_b200 * 0.7; w_roc += w_b200 * 0.3; w_b200 = 0.0
        if not b50_reliable:
            w_rs += w_b50  * 0.7; w_roc += w_b50  * 0.3; w_b50  = 0.0
        if not benchmark_ok:
            # No benchmark → RS is meaningless. Push its weight onto ROC and
            # the breadth indicators that remain reliable.
            shed = w_rs
            w_rs = 0.0
            w_roc += shed * 0.5
            if w_b200 > 0:
                w_b200 += shed * 0.25
            else:
                w_roc += shed * 0.25
            if w_b50 > 0:
                w_b50 += shed * 0.25
            else:
                w_roc += shed * 0.25

        result: dict[str, dict] = {}
        for i, r in enumerate(raw):
            composite = (
                rs_z[i]   * w_rs +
                b200_z[i] * w_b200 +
                b50_z[i]  * w_b50 +
                roc_z[i]  * w_roc +
                vol_z[i]  * w_vol
            )
            result[r["symbol"]] = {
                "composite":      round(composite, 4),
                "rs":             round(r["rs"], 2),
                "roc_6m":         round(r["roc_6m"], 2),
                "pct_above_50":   round(r["pct_above_50"], 1),
                "pct_above_200":  round(r["pct_above_200"], 1),
                "vol_trend":      round(r["vol_trend"], 3),
                "breadthSample":  r["breadth_sample"],
                "breadthSample200": r["breadth_sample_200"],
                "b200Imputed":    r["b200_imputed"],
                "b50Imputed":     r["b50_imputed"],
                # Normalized z-scores for transparency
                "zRS":            round(rs_z[i], 3),
                "zROC":           round(roc_z[i], 3),
                "zBreadth200":    round(b200_z[i], 3),
                "zBreadth50":     round(b50_z[i], 3),
                "zVolume":        round(vol_z[i], 3),
                "weights": {
                    "rs": w_rs, "breadth200": w_b200, "breadth50": w_b50,
                    "roc6m": w_roc, "volume": w_vol,
                },
                "indicatorReliability": {
                    "breadth200Reliable": b200_reliable,
                    "breadth50Reliable":  b50_reliable,
                    "benchmarkOk":        benchmark_ok,
                    "nativeB200Count":    len(b200_present),
                    "nativeB50Count":     len(b50_present),
                },
            }

        return result, excluded, nifty_hist

    @staticmethod
    def _assign_tier(rank_pct: float, composite: float) -> dict:
        """Map rank-percentile (0 = best, 100 = worst) AND absolute composite
        score to the 5-tier label + colour.

        Bug fix: previously, rank alone determined the tier — so the top 20%
        was ALWAYS "DEEP_GREEN / STRONG BUY" even in a crashing market.
        Now we also require an absolute composite floor for greens / ceiling
        for reds so a sector that's merely "least-bad" can't masquerade as a
        strong buy.
        """
        if rank_pct <= 20 and composite >= 0.30:
            tier = TIER_BY_NAME["DEEP_GREEN"]
        elif rank_pct <= 40 and composite >= 0.0:
            tier = TIER_BY_NAME["LIGHT_GREEN"]
        elif rank_pct >= 80 and composite <= -0.30:
            tier = TIER_BY_NAME["DEEP_RED"]
        elif rank_pct >= 60 and composite <= 0.0:
            tier = TIER_BY_NAME["ORANGE"]
        else:
            tier = TIER_BY_NAME["YELLOW"]
        return {k: v for k, v in tier.items()}  # copy

    # ── Phase 1: Economic cycle detection ─────────────────────────────────────

    @staticmethod
    def _macro_prior(nifty_closes: list[float]) -> dict[str, float]:
        """Macro overlay derived from Nifty 50 trend + slope.

        Returns a dict mapping each phase name to a prior in [0, 1] that
        biases the leading-sector momentum signal. This is what makes the
        phase actually adapt to the regime (bull vs bear) instead of just
        labelling whatever sector basket happens to be leading.
        """
        if not nifty_closes or len(nifty_closes) < 60:
            return {p: 0.0 for p in CYCLE_PHASES}

        last = nifty_closes[-1]
        sma200 = statistics.mean(nifty_closes[-200:]) if len(nifty_closes) >= 200 else statistics.mean(nifty_closes)
        sma50  = statistics.mean(nifty_closes[-50:])  if len(nifty_closes) >= 50  else statistics.mean(nifty_closes)
        # Slope: SMA50 now vs SMA50 ~30 bars ago
        ref_window = nifty_closes[-80:-30] if len(nifty_closes) >= 80 else nifty_closes[: max(1, len(nifty_closes) // 2)]
        slope = sma50 - statistics.mean(ref_window) if ref_window else 0.0

        above = last > sma200
        rising = slope > 0
        if above and rising:
            return {"Mid Cycle / Expansion": 0.60, "Early Cycle / Recovery": 0.30,
                    "Late Cycle / Slowdown": 0.10, "Recession / Contraction": 0.0}
        if above and not rising:
            return {"Late Cycle / Slowdown": 0.60, "Mid Cycle / Expansion": 0.30,
                    "Early Cycle / Recovery": 0.05, "Recession / Contraction": 0.05}
        if not above and rising:
            return {"Early Cycle / Recovery": 0.60, "Mid Cycle / Expansion": 0.20,
                    "Late Cycle / Slowdown": 0.10, "Recession / Contraction": 0.10}
        return {"Recession / Contraction": 0.60, "Late Cycle / Slowdown": 0.30,
                "Early Cycle / Recovery": 0.05, "Mid Cycle / Expansion": 0.05}

    def _detect_economic_phase(
        self,
        momentum: dict[str, dict],
        nifty_closes: Optional[list[float]] = None,
    ) -> dict:
        # No usable momentum at all — surface uncertainty rather than the
        # old silent default of "Mid Cycle / Expansion @ 40%".
        if not momentum:
            return {
                "phase":         "Unknown",
                "code":          "UNKNOWN",
                "color":         "#6b7280",
                "bgColor":       "#f3f4f6",
                "leadingSectors":   [],
                "actionableSectors":[],
                "theorySectors":    [],
                "characteristics": "No sector data available — unable to detect phase.",
                "strategy":      "Defer trading decisions until data is available.",
                "confidence":    0,
                "confidenceLabel":"No Data",
                "phaseScores":   {},
                "macroPrior":    {p: 0.0 for p in CYCLE_PHASES},
                "transitional":  False,
                "stable":        False,
            }

        # Leading − lagging weighted score per phase (de-overlapped).
        phase_scores: dict[str, float] = {}
        for phase_name, info in CYCLE_PHASES.items():
            lead_w = info.get("leadingWeights", {})
            lag_w  = info.get("laggingWeights", {})
            lead_pairs = [(momentum[s]["composite"], w) for s, w in lead_w.items() if s in momentum]
            lag_pairs  = [(momentum[s]["composite"], w) for s, w in lag_w.items()  if s in momentum]

            lead_score = (
                sum(c * w for c, w in lead_pairs) / sum(w for _, w in lead_pairs)
                if lead_pairs else 0.0
            )
            lag_score = (
                sum(c * w for c, w in lag_pairs) / sum(w for _, w in lag_pairs)
                if lag_pairs else 0.0
            )
            phase_scores[phase_name] = lead_score - lag_score

        macro = self._macro_prior(nifty_closes or [])
        # Add macro prior on top of leadership signal. Macro contributes
        # up to ±1.5 z-units of pull; leadership signal is ±2 z-units typical.
        combined = {p: phase_scores[p] + 1.5 * macro.get(p, 0.0) for p in phase_scores}

        best_phase = max(combined, key=lambda k: combined[k])
        best_score = combined[best_phase]
        others = [v for k, v in combined.items() if k != best_phase]
        other_avg = statistics.mean(others) if others else 0.0
        gap = best_score - other_avg

        # ── Hysteresis ───────────────────────────────────────────────────
        # If the previous phase still scores within 0.20 of the new winner,
        # keep the previous phase (markets transition slowly; a one-day
        # ranking flip shouldn't jump the user between Late and Mid).
        prev_state = _load_rotation_state() or {}
        prev_phase = prev_state.get("phase")
        transitional = False
        if (
            prev_phase
            and prev_phase in combined
            and prev_phase != best_phase
            and (best_score - combined[prev_phase]) < 0.20
        ):
            best_phase = prev_phase
            best_score = combined[prev_phase]
            transitional = True

        # Confidence: lower floor (20) so we can honestly say "low conviction".
        confidence = min(95, max(20, int(40 + gap * 25)))
        if confidence >= 70:
            label = "High"
        elif confidence >= 45:
            label = "Medium"
        else:
            label = "Low / Transitional"
        if transitional:
            label = "Transitional (hysteresis hold)"

        info = CYCLE_PHASES[best_phase]
        return {
            "phase":            best_phase,
            **info,
            "confidence":       confidence,
            "confidenceLabel":  label,
            "phaseScores":      {k: round(v, 3) for k, v in combined.items()},
            "phaseScoresRaw":   {k: round(v, 3) for k, v in phase_scores.items()},
            "macroPrior":       {k: round(v, 3) for k, v in macro.items()},
            "transitional":     transitional,
            "stable":           prev_phase == best_phase,
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
        excluded: list[str] = []
        nifty_hist: dict = {}
        try:
            momentum, excluded, nifty_hist = await self._build_momentum_scores(sectors)
        except Exception as e:
            logger.error("Momentum computation failed: %s", e)
            momentum = {}

        # Rank by composite score (highest = rank 1 = Deep Green)
        ranked = sorted(momentum.keys(), key=lambda s: momentum[s]["composite"], reverse=True)
        n = len(ranked)
        for i, sym in enumerate(ranked):
            pct = (i / n) * 100 if n > 0 else 50
            tier_info = self._assign_tier(pct, momentum[sym]["composite"])
            momentum[sym].update(tier_info)
            momentum[sym]["rank"]    = i + 1
            momentum[sym]["rankPct"] = round(pct, 1)

        # ── Phase 1 (with macro overlay + hysteresis) ──────────────────────
        nifty_closes = nifty_hist.get("closes") or []
        eco_phase = self._detect_economic_phase(momentum, nifty_closes)
        favored   = eco_phase.get("actionableSectors", [])

        # Persist phase for hysteresis on the next compute
        if eco_phase.get("phase") and eco_phase["phase"] != "Unknown":
            _save_rotation_state({
                "phase":     eco_phase["phase"],
                "asOf":      datetime.utcnow().isoformat() + "Z",
                "score":     eco_phase.get("phaseScores", {}).get(eco_phase["phase"]),
            })

        # ── Enrich sector list ────────────────────────────────────────────────
        # Sectors excluded from scoring (no data) get a flagged-empty momentum
        # entry so the UI can show them as "Data unavailable" instead of
        # silently treating them as YELLOW/HOLD.
        enriched: list[dict] = []
        for s in score_sectors:
            ms = momentum.get(s["symbol"], {})
            is_excluded = s["symbol"] in excluded
            if is_excluded and not ms:
                ms = {"tier": "UNKNOWN", "label": "Data Unavailable",
                      "color": "#6b7280", "bg": "#f3f4f6",
                      "dataMissing": True, "composite": None}
            focus_tier = ms.get("tier", "YELLOW")
            enriched.append({
                **s,
                "momentum": ms,
                "focus":    self._focus_label(focus_tier) if focus_tier != "UNKNOWN" else "NO DATA",
                # When declines == 0 the ratio is mathematically infinite.
                # Returning the raw advances count silently changes units
                # (a count is not a ratio), so surface None and let the UI
                # render "∞" / "—".
                "advanceDeclineRatio": (
                    round(s["advances"] / s["declines"], 2) if s.get("declines") else None
                ),
            })
        # Sort: scored sectors (with composite) first by composite desc, then unknown
        enriched.sort(
            key=lambda s: (
                0 if s.get("momentum", {}).get("composite") is not None else 1,
                -(s.get("momentum", {}).get("composite") or 0),
            )
        )

        # ── Phase 3 — portfolio picks ──────────────────────────────────────────
        top_picks = self._build_top_picks(enriched, eco_phase, favored)

        # ── Market breadth ────────────────────────────────────────────────────
        advancing = sum(1 for s in score_sectors if (s.get("pChange") or 0) > 0)
        declining = sum(1 for s in score_sectors if (s.get("pChange") or 0) < 0)
        total = len(score_sectors)

        # ── Signal counts across tiers ────────────────────────────────────────
        tier_counts: dict[str, int] = {}
        for s in enriched:
            tier = s.get("momentum", {}).get("tier", "YELLOW")
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

        if not momentum:
            recommendation = (
                "No usable sector data — phase detection unavailable. "
                "Defer trading decisions until data feed is restored."
            )
        elif top_picks:
            recommendation = (
                f"{eco_phase['phase']} detected ({eco_phase.get('confidenceLabel','')}, "
                f"{eco_phase.get('confidence','')}% conf). "
                f"Top momentum picks: {', '.join(p['sector'] for p in top_picks)}. "
                f"{eco_phase.get('strategy','')}"
            )
        else:
            recommendation = (
                f"{eco_phase['phase']} — no sectors meet absolute strength thresholds. "
                "Adopt defensive posture; raise cash."
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
                # See note above — None signals "undefined / infinite",
                # the UI converts that to "∞".
                "advanceDeclineRatio":round(advancing / declining, 2) if declining else None,
                "breadthScore":       round((advancing / total) * 100, 1) if total else 0,
            },
            "adRatio": round(advancing / declining, 2) if declining else None,
        }

        # Canonical provenance contract — same shape as every other route's
        # meta. Frontend (Dashboard, Sectors) reads this directly via
        # pickMeta(rotation), no ad-hoc `timestamp` fallback needed.
        state = _disk.current_market_state()
        result["meta"] = {
            "source":       "NSE",
            "servedFrom":   "ROTATION_ENGINE",
            "asOf":         _disk._now_ist().isoformat(),
            "marketState":  state,
            "eodSealed":    state in ("CLOSED", "WEEKEND"),
            "eodDate":      _disk._eod_date_for(state),
            "cacheVersion": _disk.cache_version(),
        }

        _set_cache(result)
        return result
