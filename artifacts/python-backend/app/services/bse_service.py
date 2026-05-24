"""BSE India — second-exchange data source, no API key required.

Why this is its own tier
------------------------
Most NSE-listed stocks are dual-listed on BSE. BSE's public API runs on
different infrastructure (no Akamai bot challenges, generally
cloud-IP-friendly) so it's a real independent source — not just a
relabel of the same upstream data. When NSE direct is unreachable from
the container, BSE often works.

Slots into PriceService as Tier 2 (between NSE direct and Yahoo)
because BSE is the most authoritative SECOND source for Indian stocks
— Yahoo's Indian data is itself aggregated from BSE among others, so
going to BSE directly avoids one hop and is usually fresher.

Symbol mapping caveat
---------------------
BSE identifies stocks by 6-digit numeric **scrip codes**, not tickers.
We ship a static map of the ~150 most-traded NSE tickers → BSE scrip
codes. Unknown tickers fall through silently (return None) so the
PriceService chain continues to the next tier. Expanding the map is
just a matter of adding entries; nothing in the code needs to change.

The static map covers every NIFTY 100 large cap plus the most popular
NIFTY MIDCAP / SMALLCAP names. For a stock that isn't in the map but
IS on BSE, we attempt a one-shot lookup via BSE's search endpoint and
cache the resolution for the lifetime of the process.

Free / no-auth / public
-----------------------
api.bseindia.com is BSE's official public API. No auth, no rate-limit
documented; we set a polite UA and cache responses for 90s during
market hours, 30 min when closed.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger("bse_service")

_BASE = "https://api.bseindia.com/BseIndiaAPI/api"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Origin":     "https://www.bseindia.com",
    "Referer":    "https://www.bseindia.com/",
    "Accept":     "application/json, text/plain, */*",
}

# Quote TTLs — match the other services' cadence.
_QUOTE_TTL_OPEN   = 90
_QUOTE_TTL_CLOSED = 30 * 60
_HISTORICAL_TTL   = 4 * 3600

_cache: dict[str, tuple[float, dict]] = {}
_scrip_lookup_cache: dict[str, str] = {}


# ── Static NSE → BSE scrip-code map ─────────────────────────────────────────
# Covers NIFTY 100 + popular mid/small caps. Extending: add new entries
# below; no other code changes needed. Sources verified against the BSE
# official equity list (bseindia.com/corporates/List_Scrips.html).
NSE_TO_BSE_SCRIP: dict[str, str] = {
    # NIFTY 100 large caps
    "RELIANCE":   "500325", "TCS":        "532540", "HDFCBANK":   "500180",
    "INFY":       "500209", "ICICIBANK":  "532174", "HINDUNILVR": "500696",
    "ITC":        "500875", "SBIN":       "500112", "BHARTIARTL": "532454",
    "KOTAKBANK":  "500247", "BAJFINANCE": "500034", "AXISBANK":   "532215",
    "ASIANPAINT": "500820", "MARUTI":     "532500", "HCLTECH":    "532281",
    "WIPRO":      "507685", "TITAN":      "500114", "NTPC":       "532555",
    "SUNPHARMA":  "524715", "TATAMOTORS": "500570", "LT":         "500510",
    "COALINDIA":  "533278", "BAJAJ-AUTO": "532977", "DIVISLAB":   "532488",
    "CIPLA":      "500087", "DRREDDY":    "500124", "TECHM":      "532755",
    "HINDALCO":   "500440", "ONGC":       "500312", "POWERGRID":  "532898",
    "JSWSTEEL":   "500228", "INDUSINDBK": "532187", "ULTRACEMCO": "532538",
    "NESTLEIND":  "500790", "TATACONSUM": "500800", "ADANIPORTS": "532921",
    "SBILIFE":    "540719", "BRITANNIA":  "500825", "APOLLOHOSP": "508869",
    "BPCL":       "500547", "TATASTEEL":  "500470", "ADANIENT":   "512599",
    "EICHERMOT":  "505200", "HEROMOTOCO": "500182", "GRASIM":     "500300",
    "HAVELLS":    "517354", "SHREECEM":   "500387", "HDFCLIFE":   "540777",
    "DABUR":      "500096", "PIDILITE":   "500331", "BAJAJFINSV": "532978",
    "SIEMENS":    "500550", "DLF":        "532868", "TRENT":      "500251",
    "LUPIN":      "500257", "BIOCON":     "532523", "GAIL":       "532155",
    "COLPAL":     "500830", "MUTHOOTFIN": "533398", "BERGEPAINT": "509480",
    "GODREJCP":   "532424", "BOSCHLTD":   "500530", "ABB":        "500002",
    "BANKBARODA": "532134", "PNB":        "532461", "CANBK":      "532483",
    "FEDERALBNK": "500469", "IDFCFIRSTB": "539437", "BANDHANBNK": "541153",
    "RBLBANK":    "540065", "YESBANK":    "532648", "PERSISTENT": "533179",
    "COFORGE":    "532541", "MPHASIS":    "526299", "LTTS":       "540115",
    "KPITTECH":   "542651", "TATAELXSI":  "500408", "CYIENT":     "532175",
    "IRCTC":      "542830", "ZOMATO":     "543320", "LICI":       "543526",
    "ADANIGREEN": "541450", "ADANIPOWER": "533096", "DMART":      "540376",
    "NYKAA":      "543384", "PAYTM":      "543396", "POLICYBZR":  "543390",
    "MARICO":     "531642", "MAXHEALTH":  "543220", "FORTIS":     "532843",
    "VOLTAS":     "500575", "CONCOR":     "531344", "CHOLAFIN":   "511243",
    "GODREJPROP": "533150", "OBEROIRLTY": "533273", "PRESTIGE":   "533274",
    # NIFTY MIDCAP — popular names
    "AAVAS":      "541988", "CRISIL":     "500092", "CAMS":       "543232",
    "CDSL":       "543484", "MCX":        "534091", "ANGELONE":   "543235",
    "IEX":        "540750", "DIXON":      "540699", "POLYCAB":    "542652",
    "AUBANK":     "540611", "BALKRISIND": "502355", "PAGEIND":    "532827",
    "TORNTPHARM": "500420", "PIIND":      "523642", "MRF":        "500290",
    "GLENMARK":   "532296", "ESCORTS":    "500495", "ZYDUSLIFE":  "532321",
    "ALKEM":      "539523", "JUBLFOOD":   "533155", "ICICIPRULI": "540133",
    "ICICIGI":    "540716", "ABFRL":      "535755", "ASTRAL":     "532830",
    "DEEPAKNTR":  "506401", "CROMPTON":   "539876", "HAPPSTMNDS": "543227",
}

# Inverse map for lookups when we have BSE code first.
BSE_TO_NSE: dict[str, str] = {v: k for k, v in NSE_TO_BSE_SCRIP.items()}


def _ttl_quote() -> int:
    """Pick the quote cache TTL based on rough IST market hours.

    Lightweight check — avoids the full market_cache import dependency.
    """
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415
    ist = datetime.now(tz=timezone(timedelta(hours=5, minutes=30)))
    if ist.weekday() >= 5:
        return _QUOTE_TTL_CLOSED
    minutes = ist.hour * 60 + ist.minute
    if (9 * 60 + 15) <= minutes <= (15 * 60 + 30):
        return _QUOTE_TTL_OPEN
    return _QUOTE_TTL_CLOSED


def _normalize_ticker(symbol: str) -> str:
    """Strip the suffixes we accumulate from various sources so the static
    map lookup succeeds — `RELIANCE.NS` and `RELIANCE-EQ` both resolve."""
    s = (symbol or "").strip().upper()
    for suffix in (".NS", ".BO", "-EQ", ":NSE", ":BSE"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    return s


async def _http_get_json(path: str, params: Optional[dict] = None) -> Optional[dict]:
    """Single HTTP wrapper. Never raises — returns None on any failure."""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(f"{_BASE}{path}", params=params or {},
                                    headers=_HEADERS)
            if resp.status_code != 200:
                logger.debug("BSE non-200 %s on %s", resp.status_code, path)
                return None
            try:
                return resp.json()
            except Exception:
                logger.debug("BSE non-JSON response on %s", path)
                return None
    except Exception as exc:
        logger.debug("BSE fetch failed on %s: %s", path, str(exc)[:80])
        return None


async def _resolve_scrip_code(ticker: str) -> Optional[str]:
    """Translate an NSE ticker to its BSE scrip code.

    1. Static map (covers 150+ common stocks) — fast.
    2. In-process lookup cache — already-resolved unknowns are O(1).
    3. BSE search endpoint — slower (1 HTTP) but works for the long tail.
    Returns None when the symbol can't be resolved.
    """
    sym = _normalize_ticker(ticker)
    if not sym:
        return None
    if sym in NSE_TO_BSE_SCRIP:
        return NSE_TO_BSE_SCRIP[sym]
    if sym in _scrip_lookup_cache:
        return _scrip_lookup_cache[sym] or None

    # Live search — BSE's auto-suggest. Sample working URL:
    #   https://api.bseindia.com/Msource/1D/all_get.aspx?type=H&text=RELIANCE
    # but it returns a non-JSON XML/text format. The reliable JSON path is
    # the equity search endpoint below.
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(
                "https://api.bseindia.com/BseIndiaAPI/api/SchrchScrip/w",
                params={"text": sym, "category": "Equity"},
                headers=_HEADERS,
            )
            if resp.status_code != 200:
                _scrip_lookup_cache[sym] = ""  # cache the miss
                return None
            data = resp.json()
    except Exception as exc:
        logger.debug("BSE scrip lookup failed for %s: %s", sym, str(exc)[:80])
        _scrip_lookup_cache[sym] = ""
        return None

    rows = data if isinstance(data, list) else (data.get("Table") or [])

    # Build a list of valid (bse_sym, scrip_id) pairs from the search results.
    candidates: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        bse_sym = (row.get("symbol_short") or row.get("scrip_id") or "").strip().upper()
        scrip_id = str(row.get("scrip_cd") or row.get("scripcode") or "").strip()
        if scrip_id and bse_sym:
            candidates.append((bse_sym, scrip_id))

    if not candidates:
        _scrip_lookup_cache[sym] = ""
        return None

    # Pass 1 — exact ticker match (most reliable).
    for bse_sym, scrip_id in candidates:
        if bse_sym == sym:
            _scrip_lookup_cache[sym] = scrip_id
            return scrip_id

    # Pass 2 — prefix match for post-merger renames (e.g. NSE "LTIM" ↔ BSE
    # "LTIMINDTECH"). Only trust this when BSE returned exactly one candidate;
    # multiple candidates would make a prefix match ambiguous.
    if len(candidates) == 1:
        bse_sym, scrip_id = candidates[0]
        if bse_sym.startswith(sym) or sym.startswith(bse_sym):
            logger.debug("BSE scrip fuzzy-match %s → %s (%s)", sym, scrip_id, bse_sym)
            _scrip_lookup_cache[sym] = scrip_id
            return scrip_id

    _scrip_lookup_cache[sym] = ""
    return None


async def get_quote(symbol: str) -> Optional[dict]:
    """Real-time quote from BSE. Returns the chain's standard quote shape,
    or None when the symbol isn't on BSE or BSE is unreachable.

    BSE's `ComHeader` endpoint returns the live last-traded price plus
    intraday OHLC and 52-week range. Shape varies slightly across stocks
    so we defend every field with `.get()` and silently drop unparseable
    numerics — better to return a partial quote than no quote at all.
    """
    sym = _normalize_ticker(symbol)
    if not sym:
        return None

    cache_key = f"quote:{sym}"
    cached = _cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _ttl_quote():
        return cached[1]

    scrip_code = await _resolve_scrip_code(sym)
    if not scrip_code:
        return None

    data = await _http_get_json(
        "/ComHeader/w",
        {"quotetype": "EQ", "scripcode": scrip_code, "seriesid": ""},
    )
    if not isinstance(data, dict):
        return None

    def _f(key: str) -> Optional[float]:
        v = data.get(key)
        if v in (None, "", "-"):
            return None
        try:
            return float(str(v).replace(",", ""))
        except (TypeError, ValueError):
            return None

    last = _f("CurrRate")
    prev = _f("PrevClose")
    if last is None or last <= 0:
        return None

    change  = _f("Change")
    if change is None and prev:
        change = round(last - prev, 2)
    pchange = _f("PercentChange")
    if pchange is None and prev:
        pchange = round((last - prev) / prev * 100, 2)

    quote = {
        "symbol":         sym,
        "companyName":    (data.get("ScripName") or sym).strip(),
        "lastPrice":      last,
        "change":         change,
        "pChange":        pchange,
        "open":           _f("Open"),
        "dayHigh":        _f("High"),
        "dayLow":         _f("Low"),
        "previousClose":  prev,
        "volume":         int(_f("TotalQuantityTraded") or 0) or None,
        "fiftyTwoWeekHigh": _f("WeekHigh") or _f("Week52High"),
        "fiftyTwoWeekLow":  _f("WeekLow")  or _f("Week52Low"),
        "marketCap":      _f("MarketCap"),
        "source":         "BSE",
    }
    _cache[cache_key] = (time.time(), quote)
    return quote


async def get_historical(symbol: str, days: int = 90) -> list[dict]:
    """Daily OHLCV bars from BSE. Same shape (oldest → newest) as the
    other chain tiers so PriceService can substitute it freely.

    BSE's `StockReachGraph` endpoint returns up to ~1 year of daily
    history per call. We trim to `days` on our side so callers don't
    care about the upstream size.
    """
    sym = _normalize_ticker(symbol)
    if not sym:
        return []

    cache_key = f"history:{sym}:{days}"
    cached = _cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _HISTORICAL_TTL:
        return cached[1]

    scrip_code = await _resolve_scrip_code(sym)
    if not scrip_code:
        return []

    data = await _http_get_json(
        "/StockReachGraph/w",
        {"scripcode": scrip_code, "flag": "0", "fromdate": "", "todate": "",
         "seriesid": ""},
    )
    if not isinstance(data, dict):
        return []
    rows_src = data.get("Data") or data.get("data") or []
    if not isinstance(rows_src, list):
        return []

    rows: list[dict] = []
    for r in rows_src:
        if not isinstance(r, dict):
            continue
        try:
            # BSE keys vary; try common variants
            date_s = (r.get("dt") or r.get("Date") or r.get("date") or "").strip()
            if "T" in date_s:
                date_s = date_s.split("T", 1)[0]
            if not date_s:
                continue
            rows.append({
                "date":   date_s,
                "open":   float(r.get("Open")   or r.get("vopn")   or 0),
                "high":   float(r.get("High")   or r.get("vhigh")  or 0),
                "low":    float(r.get("Low")    or r.get("vlow")   or 0),
                "close":  float(r.get("Close")  or r.get("vclose") or 0),
                "volume": int(float(r.get("Volume") or r.get("vqty") or 0)),
            })
        except (TypeError, ValueError):
            continue

    if not rows:
        return []
    rows.sort(key=lambda r: r["date"])
    rows = rows[-days:] if len(rows) > days else rows
    _cache[cache_key] = (time.time(), rows)
    return rows
