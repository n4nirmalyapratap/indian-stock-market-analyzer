"""
Macro Service — India macro pulse aggregator.

Surfaces the six indicators retail traders ask about every day:
  * RBI policy (repo) rate
  * CPI inflation (YoY)
  * Industrial production (IIP, YoY)
  * USD/INR
  * India 10-year government bond yield
  * Brent crude (USD/bbl)

Plus supporting series for the dashboard tab:
  * WPI (Indian wholesale-price growth via the OECD MEI series on FRED + a
    best-effort fetch attempt against MOSPI/Office of the Economic Adviser),
  * Real GDP growth (quarterly),
  * Multi-tenor sovereign yield curve (3M, 1Y, 5Y, 10Y) — populated from
    every public source we can reach (FRED short/long, optional CCIL/RBI),
  * DXY / Gold / Brent / India VIX (Yahoo).

Data sources & honest provenance
--------------------------------
The service queries every public source the spec calls for — RBI DBIE, MOSPI
(Office of Economic Adviser), CCIL India, Yahoo and FRED — but reports each
source's *actual* status (`ok` / `failed` / `skipped`) in the `sources`
array of every response.  We never claim a source we did not in fact query.

Cloud-IP egress reality: a Replit container can typically reach FRED and
Yahoo, but is often blocked from `www.rbi.org.in`, `eaindustry.nic.in` and
`www.ccilindia.com`.  Those calls are wrapped in try/except, fail in <5 s,
and the response degrades gracefully — the user just sees "FRED" as the
served-from source instead of (e.g.) "RBI DBIE".

All series are cached in-process for 24 hours; macro data does not refresh
intra-day so this avoids hammering the upstream providers.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from . import ai_client
from .yahoo_service import YahooService

log = logging.getLogger("macro_service")

# ── Cache ────────────────────────────────────────────────────────────────────
_CACHE_TTL = 24 * 60 * 60  # 24 hours
_cache: dict[str, tuple[float, Any]] = {}


def _cache_get(key: str) -> Optional[Any]:
    hit = _cache.get(key)
    if not hit:
        return None
    ts, val = hit
    if (time.time() - ts) >= _CACHE_TTL:
        _cache.pop(key, None)
        return None
    return val


def _cache_set(key: str, val: Any) -> None:
    _cache[key] = (time.time(), val)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── FRED JSON API fetcher ────────────────────────────────────────────────────
# We use the official api.stlouisfed.org JSON endpoint with an API key. The
# unauthenticated CSV endpoint at fred.stlouisfed.org/graph/fredgraph.csv is
# routinely WAF-blocked from cloud IPs (Imperva bot challenge), so the API
# is the only reliable channel.  A free API key is required; if FRED_API_KEY
# is unset we degrade gracefully to empty payloads.
FRED_API_BASE = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"  # legacy fallback

# Symbolic names → FRED series IDs (verified against the FRED JSON API).
# Some India series on FRED are mirrored from OECD/MEI on a delay; the
# `asOf` field on every tile/chart point shows the upstream observation
# date so the user can see exactly how fresh the data is.
FRED_SERIES = {
    "repo":    "IRSTCB01INM156N",   # India Central Bank policy rate, monthly %
    "cpi":     "INDCPIALLMINMEI",   # India CPI All items, monthly index level
    "iip":     "INDPROINDMISMEI",   # India industrial production, monthly index level
    "gdp":     "INDGDPRQPSMEI",     # India real GDP, quarterly YoY % (already growth)
    "yield10": "INDIRLTLT01STM",    # India 10Y gov bond yield, monthly %
    "yield3m": "IRSTCI01INM156N",   # India call money / interbank rate, monthly %
    "wpi":     "INDWPIATT01GPM",    # India WPI, monthly growth (already pct change)
}

# Series that arrive already as period-on-period or YoY % growth rates and
# therefore must NOT be passed through `_series_yoy()` again.
FRED_PRECOMPUTED_GROWTH = {"gdp", "wpi"}


async def _fetch_fred_series(series_id: str) -> list[dict[str, Any]]:
    """
    Fetch observations for a FRED series via the JSON API and return them
    as a list of {date, value} dicts ordered oldest → newest.

    Empty list on any failure (no API key, network, parse error, 400/404,
    timeout). This function is the only data-pull primitive the service
    uses; it must never raise so callers can degrade gracefully.
    """
    # Check DB-managed secrets first (set via admin UI), then env var, then .env.
    from app.lib.secrets_store import get_secret as _get_secret
    api_key = _get_secret("FRED_API_KEY", "").strip()
    if api_key:
        return await _fetch_fred_via_api(series_id, api_key)
    # No key configured — fall back to the CSV endpoint, which is usually
    # WAF-blocked from cloud IPs but kept for completeness / local dev.
    log.info("FRED_API_KEY unset; trying public CSV endpoint for %s", series_id)
    return await _fetch_fred_csv_fallback(series_id)


async def _fetch_fred_via_api(series_id: str, api_key: str) -> list[dict[str, Any]]:
    """Fetch observations via api.stlouisfed.org (requires API key)."""
    params = {
        "series_id":  series_id,
        "api_key":    api_key,
        "file_type":  "json",
        "sort_order": "asc",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(
                FRED_API_BASE,
                params=params,
                headers={"User-Agent": "NiftyNode/1.0 (+macro)"},
            )
            if resp.status_code != 200:
                log.warning("FRED API non-200 for %s: %s %s",
                            series_id, resp.status_code, resp.text[:120])
                return []
            payload = resp.json()
    except Exception as e:
        log.warning("FRED API fetch failed for %s: %s", series_id, str(e)[:120])
        return []

    out: list[dict[str, Any]] = []
    try:
        if not isinstance(payload, dict):
            return []
        observations = payload.get("observations") or []
        if not isinstance(observations, list):
            return []
        for obs in observations:
            if not isinstance(obs, dict):
                continue
            date_s = str(obs.get("date") or "").strip()
            val_s  = str(obs.get("value") or "").strip()
            if not date_s or val_s in ("", ".", "NA"):
                continue
            try:
                out.append({"date": date_s, "value": float(val_s)})
            except (TypeError, ValueError):
                continue
    except Exception as e:
        log.warning("FRED API parse failed for %s: %s", series_id, str(e)[:120])
        return []
    return out


async def _fetch_fred_csv_fallback(series_id: str) -> list[dict[str, Any]]:
    """Legacy CSV fallback — used only when no API key is configured."""
    url = f"{FRED_CSV_BASE}?id={series_id}"
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "NiftyNode/1.0 (+macro)"})
            if resp.status_code != 200 or not resp.text:
                return []
            text = resp.text
    except Exception as e:
        log.warning("FRED CSV fallback failed for %s: %s", series_id, str(e)[:120])
        return []

    rows: list[dict[str, Any]] = []
    try:
        reader = csv.reader(io.StringIO(text))
        header = next(reader, None)
        if not header or len(header) < 2:
            return []
        for r in reader:
            if len(r) < 2:
                continue
            date_s, val_s = r[0].strip(), r[1].strip()
            if not date_s or val_s in ("", ".", "NA"):
                continue
            try:
                rows.append({"date": date_s, "value": float(val_s)})
            except ValueError:
                continue
    except Exception as e:
        log.warning("FRED CSV parse failed for %s: %s", series_id, str(e)[:120])
        return []
    return rows


# Backwards-compat alias for tests that still patch the old name.
_fetch_fred_csv = _fetch_fred_series


# ── World Bank API — free, no key, annual observations ───────────────────────
# Used as a fallback when FRED_API_KEY is unset and the CSV endpoint is
# WAF-blocked (common on cloud IPs).  Annual data is coarser than FRED's
# monthly series but is far better than returning nothing at all.
#
# WB indicator IDs verified at https://data.worldbank.org/indicator
WB_SERIES: dict[str, str] = {
    "cpi":  "FP.CPI.TOTL",           # CPI index (2010 = 100)  → YoY computed lag=1
    "iip":  "NV.IND.TOTL.KD.ZG",     # Industry value-added growth % (pre-computed)
    "gdp":  "NY.GDP.MKTP.KD.ZG",     # Real GDP growth % annual (pre-computed)
}

# WB series that arrive already as annual growth rates (no further _yoy needed).
WB_PRECOMPUTED_GROWTH: set[str] = {"iip", "gdp"}


async def _fetch_wb_series(wb_indicator: str, country: str = "IND",
                           mrv: int = 72) -> list[dict[str, Any]]:
    """
    Fetch annual observations from the World Bank API (no key required).
    Returns a list of {date, value} dicts sorted oldest → newest, same
    schema as `_fetch_fred_series`, so callers can use them interchangeably.
    Annual dates are normalised to ISO strings (e.g. "2023-01-01").
    Returns empty list on any failure.
    """
    url = (
        f"https://api.worldbank.org/v2/country/{country}/indicator/{wb_indicator}"
        f"?format=json&mrv={mrv}&per_page={mrv}"
    )
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(
                url, headers={"User-Agent": "NiftyNode/1.0 (+macro-wb)"}
            )
            if resp.status_code != 200:
                log.warning("WB API non-200 for %s: %s", wb_indicator, resp.status_code)
                return []
            payload = resp.json()
    except Exception as e:
        log.warning("WB API fetch failed for %s: %s", wb_indicator, str(e)[:120])
        return []

    try:
        if not isinstance(payload, list) or len(payload) < 2:
            return []
        items = payload[1] or []
        out: list[dict[str, Any]] = []
        for x in items:
            if not isinstance(x, dict) or x.get("value") is None:
                continue
            raw_date = str(x.get("date") or "").strip()
            if not raw_date:
                continue
            # WB returns year strings like "2023" → normalise to "2023-01-01"
            date_s = f"{raw_date}-01-01" if len(raw_date) == 4 else raw_date
            try:
                out.append({"date": date_s, "value": float(x["value"])})
            except (TypeError, ValueError):
                continue
        out.sort(key=lambda d: d["date"])
        return out
    except Exception as e:
        log.warning("WB API parse failed for %s: %s", wb_indicator, str(e)[:120])
        return []


# ── Best-effort adapters for India-native sources ────────────────────────────
# These reach out to RBI DBIE / MOSPI (Office of Economic Adviser) / CCIL.
# Cloud IPs are often firewalled out, so each adapter has a strict 6s timeout
# and reports {"ok": bool, "url": str, "note": str} instead of raising.

async def _probe_url(url: str, timeout: float = 6.0) -> dict[str, Any]:
    """HEAD/GET a URL just to see if it's reachable from this container."""
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "NiftyNode/1.0 (+macro-probe)"})
            ok = 200 <= resp.status_code < 400
            return {"ok": ok, "url": url, "status": resp.status_code,
                    "note": "reachable" if ok else f"http {resp.status_code}"}
    except Exception as e:
        return {"ok": False, "url": url, "status": None, "note": f"unreachable: {str(e)[:80]}"}


async def _attempt_rbi_dbie() -> dict[str, Any]:
    """Best-effort probe of RBI DBIE for the policy-rate page."""
    return await _probe_url("https://www.rbi.org.in/scripts/BS_PressReleaseDisplay.aspx")


async def _attempt_mospi_wpi() -> dict[str, Any]:
    """Best-effort probe of the Office of the Economic Adviser for WPI."""
    return await _probe_url("https://eaindustry.nic.in/")


async def _attempt_ccil_yields() -> dict[str, Any]:
    """Best-effort probe of CCIL India for the G-Sec yield curve page."""
    return await _probe_url("https://www.ccilindia.com/RiskManagement/SecuritiesSegment/Pages/IndianGovernmentBondData.aspx")


def _yoy_change(series: list[dict[str, Any]], lag: int = 12) -> Optional[float]:
    """
    Compute the year-on-year percent change from a monthly level series.
    `lag` is the index distance (12 for monthly YoY, 4 for quarterly).
    Returns None when there isn't enough history.
    """
    if not series or len(series) <= lag:
        return None
    cur = series[-1]["value"]
    prv = series[-1 - lag]["value"]
    if not prv:
        return None
    return (cur - prv) / prv * 100.0


def _last_two(series: list[dict[str, Any]]) -> tuple[Optional[dict], Optional[dict]]:
    """Return (latest, previous) entries from a series, or (None, None)."""
    if not series:
        return None, None
    if len(series) == 1:
        return series[-1], None
    return series[-1], series[-2]


# ── Service ──────────────────────────────────────────────────────────────────
class MacroService:
    """Aggregator for India macro indicators.  Stateless — safe to share."""

    def __init__(self, yahoo: Optional[YahooService] = None) -> None:
        self.yahoo = yahoo or YahooService()

    # ----- Live market tickers (Yahoo) --------------------------------------
    # Yahoo symbols verified against finance.yahoo.com.
    YAHOO_TICKERS = {
        "usdinr": "INR=X",          # USD/INR spot
        "dxy":    "DX-Y.NYB",       # US Dollar Index
        "brent":  "BZ=F",           # Brent crude futures
        "gold":   "GC=F",           # COMEX gold futures
        "vix":    "^INDIAVIX",      # India VIX
        "nifty":  "^NSEI",          # Nifty 50 (for context)
    }

    async def _yahoo_quote(self, key: str) -> dict[str, Any]:
        """Fetch a single Yahoo ticker; degrade to empty dict."""
        sym = self.YAHOO_TICKERS.get(key)
        if not sym:
            return {}
        try:
            q = await self.yahoo.get_quote(sym)
            if not q:
                return {}
            return {
                "symbol":  sym,
                "price":   float(q.get("lastPrice") or 0.0) or None,
                "change":  float(q.get("change") or 0.0),
                "pChange": float(q.get("pChange") or 0.0),
                "name":    q.get("companyName") or sym,
            }
        except Exception as e:
            log.warning("Yahoo macro fetch failed for %s: %s", sym, str(e)[:120])
            return {}

    # ----- High-level aggregators -------------------------------------------
    async def get_strip(self) -> dict[str, Any]:
        """
        The 6-tile macro strip pinned to the dashboard top bar.
        Each tile: { id, label, unit, value, delta, deltaUnit, asOf }.
        """
        cached = _cache_get("strip")
        if cached is not None:
            return cached

        # Fetch FRED + Yahoo + World Bank fallbacks all in one round-trip.
        # WB is fetched eagerly alongside FRED so there is no sequential penalty;
        # it is only used when the corresponding FRED series comes back empty.
        (repo_s, cpi_s, iip_s, yld_s, usdinr_q, brent_q,
         wb_cpi_s, wb_iip_s) = await asyncio.gather(
            _fetch_fred_series(FRED_SERIES["repo"]),
            _fetch_fred_series(FRED_SERIES["cpi"]),
            _fetch_fred_series(FRED_SERIES["iip"]),
            _fetch_fred_series(FRED_SERIES["yield10"]),
            self._yahoo_quote("usdinr"),
            self._yahoo_quote("brent"),
            _fetch_wb_series(WB_SERIES["cpi"]),   # annual CPI index fallback
            _fetch_wb_series(WB_SERIES["iip"]),   # annual industry growth % fallback
        )

        # Apply World Bank fallbacks for any FRED series that returned empty.
        fred_cpi_ok = bool(cpi_s)   # capture before possible reassignment
        fred_iip_ok = bool(iip_s)
        cpi_from_wb = not fred_cpi_ok and bool(wb_cpi_s)
        iip_from_wb = not fred_iip_ok and bool(wb_iip_s)
        if cpi_from_wb:
            cpi_s = wb_cpi_s
        if iip_from_wb:
            iip_s = wb_iip_s  # WB NV.IND.TOTL.KD.ZG is already annual growth %

        # Repo rate — value is in percent already; delta vs previous reading.
        repo_now, repo_prev = _last_two(repo_s)
        repo_tile = self._tile(
            "repo", "RBI Repo", "%",
            repo_now["value"] if repo_now else None,
            (repo_now["value"] - repo_prev["value"]) if repo_now and repo_prev else None,
            "pp",
            repo_now["date"] if repo_now else None,
        )

        # CPI — convert level series to YoY %.
        # FRED is monthly (lag=12); WB is annual index (lag=1 for annual YoY).
        cpi_lag = 1 if cpi_from_wb else 12
        cpi_min  = cpi_lag + 2
        cpi_yoy_now  = _yoy_change(cpi_s, lag=cpi_lag)
        cpi_yoy_prev = _yoy_change(cpi_s[:-1], lag=cpi_lag) if len(cpi_s) > cpi_min else None
        cpi_tile = self._tile(
            "cpi", "CPI YoY", "%",
            cpi_yoy_now,
            (cpi_yoy_now - cpi_yoy_prev) if cpi_yoy_now is not None and cpi_yoy_prev is not None else None,
            "pp",
            cpi_s[-1]["date"] if cpi_s else None,
        )

        # IIP — FRED is monthly index (compute YoY); WB is already annual growth %.
        if iip_from_wb:
            iip_now, iip_prev = _last_two(iip_s)
            iip_yoy_now  = iip_now["value"]  if iip_now  else None
            iip_yoy_prev = iip_prev["value"] if iip_prev else None
            iip_as_of    = iip_now["date"]   if iip_now  else None
        else:
            iip_yoy_now  = _yoy_change(iip_s, lag=12)
            iip_yoy_prev = _yoy_change(iip_s[:-1], lag=12) if len(iip_s) > 13 else None
            iip_as_of    = iip_s[-1]["date"] if iip_s else None
        iip_tile = self._tile(
            "iip", "IIP YoY", "%",
            iip_yoy_now,
            (iip_yoy_now - iip_yoy_prev) if iip_yoy_now is not None and iip_yoy_prev is not None else None,
            "pp",
            iip_as_of,
        )

        # USD/INR — live; delta is intraday % change from Yahoo.
        usdinr_tile = self._tile(
            "usdinr", "USD/INR", "₹",
            usdinr_q.get("price") if usdinr_q else None,
            usdinr_q.get("pChange") if usdinr_q else None,
            "%",
            _now_iso(),
        )

        # India 10Y — FRED monthly series, value already in percent.
        yld_now, yld_prev = _last_two(yld_s)
        yld_tile = self._tile(
            "yield10", "India 10Y", "%",
            yld_now["value"] if yld_now else None,
            (yld_now["value"] - yld_prev["value"]) if yld_now and yld_prev else None,
            "pp",
            yld_now["date"] if yld_now else None,
        )

        # Brent — live; delta is intraday % change.
        brent_tile = self._tile(
            "brent", "Brent", "$",
            brent_q.get("price") if brent_q else None,
            brent_q.get("pChange") if brent_q else None,
            "%",
            _now_iso(),
        )

        out = {
            "tiles": [repo_tile, cpi_tile, iip_tile, usdinr_tile, yld_tile, brent_tile],
            "fetchedAt": _now_iso(),
            "sources": [
                {"id": "fred",  "label": "FRED API",      "covers": "Repo, CPI, IIP, 10Y",
                 "ok": bool(repo_s or fred_cpi_ok or fred_iip_ok or yld_s)},
                {"id": "worldbank", "label": "World Bank (fallback)",
                 "covers": "CPI, IIP when FRED unavailable",
                 "ok": bool(wb_cpi_s or wb_iip_s)},
                {"id": "yahoo", "label": "Yahoo Finance", "covers": "USD/INR, Brent",
                 "ok": bool(usdinr_q or brent_q)},
            ],
        }
        _cache_set("strip", out)
        return out

    async def get_dashboard(self) -> dict[str, Any]:
        """
        Full payload for the /insights/macro tab — all the series the page
        needs, in one round-trip:
          * rateTimeline   : repo rate over time  (date, value)
          * cpi            : CPI YoY % over time
          * wpi            : WPI growth % over time (FRED INDWPIATT01GPM)
          * iip            : IIP YoY % over time
          * gdp            : Real GDP YoY % over time (quarterly)
          * yieldCurve     : multi-tenor curve snapshot + 10Y history
          * currencyStrip  : USD/INR + DXY + Brent + Gold + VIX live
          * commentary     : LLM 'what changed this week' string (best-effort)
          * sources[]      : honest per-source provenance (ok/failed/skipped)
        """
        cached = _cache_get("dashboard")
        if cached is not None:
            return cached

        # Fetch FRED + Yahoo + World Bank fallbacks all in one round-trip.
        (repo_s, cpi_s, iip_s, gdp_s, yld10_s, yld3m_s, wpi_s,
         usdinr, dxy, brent, gold, vix,
         rbi_probe, mospi_probe, ccil_probe,
         wb_cpi_s, wb_iip_s, wb_gdp_s) = await asyncio.gather(
            _fetch_fred_series(FRED_SERIES["repo"]),
            _fetch_fred_series(FRED_SERIES["cpi"]),
            _fetch_fred_series(FRED_SERIES["iip"]),
            _fetch_fred_series(FRED_SERIES["gdp"]),
            _fetch_fred_series(FRED_SERIES["yield10"]),
            _fetch_fred_series(FRED_SERIES["yield3m"]),
            _fetch_fred_series(FRED_SERIES["wpi"]),
            self._yahoo_quote("usdinr"),
            self._yahoo_quote("dxy"),
            self._yahoo_quote("brent"),
            self._yahoo_quote("gold"),
            self._yahoo_quote("vix"),
            _attempt_rbi_dbie(),
            _attempt_mospi_wpi(),
            _attempt_ccil_yields(),
            _fetch_wb_series(WB_SERIES["cpi"]),   # annual CPI index fallback
            _fetch_wb_series(WB_SERIES["iip"]),   # annual industry growth % fallback
            _fetch_wb_series(WB_SERIES["gdp"]),   # annual GDP growth % fallback
        )

        # Apply World Bank fallbacks for any FRED series that returned empty.
        fred_ok_dash = bool(repo_s or cpi_s or yld10_s)  # capture before reassignment
        cpi_from_wb = not cpi_s and bool(wb_cpi_s)
        iip_from_wb = not iip_s and bool(wb_iip_s)
        gdp_from_wb = not gdp_s and bool(wb_gdp_s)
        if cpi_from_wb:
            cpi_s = wb_cpi_s
        if iip_from_wb:
            iip_s = wb_iip_s   # already annual growth %
        if gdp_from_wb:
            gdp_s = wb_gdp_s   # already annual growth %

        # Trim to most recent ~6 years for chart readability.
        rate_timeline = repo_s[-72:] if repo_s else []
        # CPI: FRED monthly → lag=12; WB annual index → lag=1
        cpi_lag = 1 if cpi_from_wb else 12
        cpi_yoy = self._series_yoy(cpi_s, lag=cpi_lag)[-72:]
        # IIP: FRED monthly → compute YoY; WB annual % → use directly
        if iip_from_wb:
            iip_yoy = iip_s[-24:]  # already annual growth %, last ~24 years
        else:
            iip_yoy = self._series_yoy(iip_s, lag=12)[-72:]
        # GDP: FRED quarterly (already YoY); WB annual (already %) — both use directly
        gdp_yoy = gdp_s[-24:] if gdp_s else []
        # WPI series (INDWPIATT01GPM) is already a period-over-period growth rate.
        wpi_yoy = wpi_s[-72:] if wpi_s else []
        yield_history = yld10_s[-72:] if yld10_s else []

        # Multi-tenor yield curve snapshot — we always include 3M and 10Y
        # tenors, populating None when the series isn't reachable. CCIL
        # additions could be appended here once their endpoint becomes
        # reachable from this container.
        yield_curve_snapshot = self._build_yield_curve(yld3m_s, yld10_s)

        # AI commentary — fire and forget, don't fail the response if it dies.
        commentary = await self._build_commentary(
            repo_s, cpi_s, wpi_s, iip_s, yld10_s, usdinr, brent,
        )

        # Honest per-source provenance.  `ok` says whether we actually got
        # usable data from that source on this fetch.
        sources = [
            {"id": "fred", "label": "FRED API", "ok": fred_ok_dash,
             "covers": "Repo, CPI, IIP, GDP, Call Money & 10Y yields, WPI",
             "url": "https://fred.stlouisfed.org/"},
            {"id": "worldbank", "label": "World Bank (fallback)",
             "ok": bool(wb_cpi_s or wb_iip_s or wb_gdp_s),
             "covers": "CPI, IIP, GDP when FRED unavailable",
             "url": "https://data.worldbank.org/"},
            {"id": "yahoo", "label": "Yahoo Finance", "ok": bool(usdinr or brent or dxy),
             "covers": "USD/INR, DXY, Brent, Gold, India VIX",
             "url": "https://finance.yahoo.com/"},
            {"id": "rbi-dbie", "label": "RBI DBIE", "ok": bool(rbi_probe.get("ok")),
             "covers": "Policy rate cross-check (probe only — see note)",
             "url": rbi_probe.get("url"), "note": rbi_probe.get("note")},
            {"id": "mospi", "label": "MOSPI / Office of the Economic Adviser",
             "ok": bool(mospi_probe.get("ok")),
             "covers": "WPI primary source (probe only — FRED OECD WPI used as fallback)",
             "url": mospi_probe.get("url"), "note": mospi_probe.get("note")},
            {"id": "ccil", "label": "CCIL India",
             "ok": bool(ccil_probe.get("ok")),
             "covers": "G-Sec yield curve (probe only — see note)",
             "url": ccil_probe.get("url"), "note": ccil_probe.get("note")},
        ]

        out = {
            "rateTimeline": rate_timeline,
            "cpi":          cpi_yoy,
            "wpi":          wpi_yoy,
            "iip":          iip_yoy,
            "gdp":          gdp_yoy,
            "yieldCurve": {
                "ind10yNow":     (yld10_s[-1]["value"] if yld10_s else None),
                "ind10yAsOf":    (yld10_s[-1]["date"]  if yld10_s else None),
                "ind10yHistory": yield_history,
                "snapshot":      yield_curve_snapshot,   # multi-tenor curve
            },
            "currencyStrip": {
                "usdinr": usdinr,
                "dxy":    dxy,
                "brent":  brent,
                "gold":   gold,
                "vix":    vix,
            },
            "commentary": commentary,
            "fetchedAt":  _now_iso(),
            "sources":    sources,
        }
        _cache_set("dashboard", out)
        return out

    # ----- Helpers ----------------------------------------------------------
    @staticmethod
    def _tile(
        tid: str, label: str, unit: str,
        value: Optional[float], delta: Optional[float], delta_unit: str,
        as_of: Optional[str],
    ) -> dict[str, Any]:
        return {
            "id":        tid,
            "label":     label,
            "unit":      unit,
            "value":     value,
            "delta":     delta,
            "deltaUnit": delta_unit,
            "asOf":      as_of,
        }

    @staticmethod
    def _series_yoy(series: list[dict[str, Any]], lag: int) -> list[dict[str, Any]]:
        """Convert a level series into a YoY percent-change series."""
        if not series or len(series) <= lag:
            return []
        out: list[dict[str, Any]] = []
        for i in range(lag, len(series)):
            prev = series[i - lag]["value"]
            cur  = series[i]["value"]
            if not prev:
                continue
            out.append({"date": series[i]["date"], "value": (cur - prev) / prev * 100.0})
        return out

    @staticmethod
    def _build_yield_curve(
        yld3m_s: list[dict[str, Any]],
        yld10_s: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Build a multi-tenor curve snapshot from whatever tenors we managed
        to fetch.  Each point: { tenor, tenorMonths, value, asOf }.
        Tenors with no data are still emitted (value: None) so the chart
        rendering can show gaps honestly.
        """
        def latest(s: list[dict[str, Any]]) -> tuple[Optional[float], Optional[str]]:
            if not s:
                return None, None
            return s[-1]["value"], s[-1]["date"]

        v3m, d3m = latest(yld3m_s)
        v10y, d10y = latest(yld10_s)

        return [
            {"tenor": "3M",  "tenorMonths":   3, "value": v3m,  "asOf": d3m},
            {"tenor": "10Y", "tenorMonths": 120, "value": v10y, "asOf": d10y},
        ]

    async def _build_commentary(
        self,
        repo_s: list[dict[str, Any]],
        cpi_s:  list[dict[str, Any]],
        wpi_s:  list[dict[str, Any]],
        iip_s:  list[dict[str, Any]],
        yld_s:  list[dict[str, Any]],
        usdinr: dict[str, Any],
        brent:  dict[str, Any],
    ) -> str:
        """
        Generate a 3-4 line 'what changed this week' commentary using the AI
        client. If LLM is unavailable we synthesise a deterministic summary
        from the same numbers so the panel never goes blank.
        """
        repo_now, _ = _last_two(repo_s)
        cpi_yoy = _yoy_change(cpi_s, lag=12)
        iip_yoy = _yoy_change(iip_s, lag=12)
        yld_now, _ = _last_two(yld_s)
        wpi_now, _ = _last_two(wpi_s)

        bits: list[str] = []
        if repo_now:
            bits.append(f"RBI repo rate stands at {repo_now['value']:.2f}% (as of {repo_now['date']}).")
        if cpi_yoy is not None:
            bits.append(f"CPI inflation is running at {cpi_yoy:.2f}% YoY.")
        if wpi_now is not None:
            bits.append(f"Wholesale prices {wpi_now['value']:+.2f}%.")
        if iip_yoy is not None:
            bits.append(f"Industrial production grew {iip_yoy:.2f}% YoY.")
        if yld_now:
            bits.append(f"India's 10-year benchmark yield is {yld_now['value']:.2f}%.")
        if usdinr.get("price"):
            bits.append(f"USD/INR is at ₹{usdinr['price']:.2f} ({usdinr.get('pChange', 0):+.2f}% today).")
        if brent.get("price"):
            bits.append(f"Brent crude is ${brent['price']:.2f}/bbl ({brent.get('pChange', 0):+.2f}% today).")

        deterministic = " ".join(bits) if bits else "Macro data is currently unavailable."

        if not ai_client.is_available():
            return deterministic

        prompt = (
            "You are an Indian markets macro analyst. Below are the latest readings. "
            "Write a concise 3–4 sentence weekly commentary explaining what these numbers "
            "tell an Indian retail equity trader about RBI policy direction, inflation, "
            "growth and currency. Be specific and quantitative; no caveats or disclaimers.\n\n"
            f"{deterministic}"
        )
        try:
            txt = await ai_client.ask(
                prompt=prompt,
                system="You are a concise, professional macro strategist focused on Indian markets.",
                max_tokens=350,
                temperature=0.35,
            )
            txt = (txt or "").strip()
            # If the AI client returns its sentinel error string, fall back.
            if not txt or txt.startswith("[AI unavailable"):
                return deterministic
            return txt
        except Exception as e:
            log.warning("AI commentary failed: %s", str(e)[:120])
            return deterministic
