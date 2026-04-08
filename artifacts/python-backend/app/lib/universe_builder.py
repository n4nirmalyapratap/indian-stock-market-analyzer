"""
universe_builder.py — Live NSE/BSE universe from official public sources.

Sources (all free, no API key needed):
  1. NSE EQUITY_L.csv      → all NSE symbols + company names
  2. AMFI classification   → Large / Mid / Small cap categories
  3. NiftyIndices CSVs     → sector index constituent lists

Builds universe_cache.json and refreshes it once per day.
universe.py loads from cache; falls back to hardcoded data if anything fails.
"""

import asyncio
import io
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
import pandas as pd

log = logging.getLogger(__name__)

CACHE_FILE = Path(__file__).parent / "universe_cache.json"
CACHE_TTL  = 24 * 3600   # refresh once per day

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

NSE_HEADERS = {
    **HEADERS,
    "Referer": "https://www.nseindia.com/",
    "Host": "nsearchives.nseindia.com",
}

# Nifty Indices constituent CSV base URL
_NI_BASE = "https://www.niftyindices.com/IndexConstituent/"

# sector name → NiftyIndices CSV filename
SECTOR_CSV_MAP: dict[str, str] = {
    "NIFTY 50":                    "ind_nifty50list.csv",
    "NIFTY 100":                   "ind_nifty100list.csv",
    "NIFTY MIDCAP 100":            "ind_niftymidcap100list.csv",
    "NIFTY MIDCAP 150":            "ind_niftymidcap150list.csv",
    "NIFTY SMALLCAP 100":          "ind_niftysmallcap100list.csv",
    "NIFTY SMALLCAP 250":          "ind_niftysmallcap250list.csv",
    "NIFTY IT":                    "ind_niftyitlist.csv",
    "NIFTY BANK":                  "ind_niftybanklist.csv",
    "NIFTY AUTO":                  "ind_niftyautolist.csv",
    "NIFTY PHARMA":                "ind_niftypharmalist.csv",
    "NIFTY FMCG":                  "ind_niftyfmcglist.csv",
    "NIFTY METAL":                 "ind_niftymetallist.csv",
    "NIFTY REALTY":                "ind_niftyrealtylist.csv",
    "NIFTY ENERGY":                "ind_niftyenergylist.csv",
    "NIFTY MEDIA":                 "ind_niftymedialist.csv",
    "NIFTY FINANCIAL SERVICES":    "ind_niftyfinancelist.csv",
    "NIFTY PSU BANK":              "ind_niftypsubanklist.csv",
    "NIFTY CONSUMER DURABLES":     "ind_niftyconsumerdurableslist.csv",
    "NIFTY OIL AND GAS":           "ind_niftyoilgaslist.csv",
    "NIFTY HEALTHCARE INDEX":      "ind_niftyhealthcarelist.csv",
    "NIFTY INFRASTRUCTURE":        "ind_niftyinfrastructurelist.csv",
    "NIFTY MICROCAP 250":          "ind_niftymicrocap250list.csv",
}


# ── helpers ───────────────────────────────────────────────────────────────────

async def _get(
    client: httpx.AsyncClient,
    url: str,
    extra_headers: Optional[dict] = None,
    **kw,
) -> Optional[bytes]:
    hdrs = {**HEADERS, **(extra_headers or {})}
    try:
        r = await client.get(url, headers=hdrs, timeout=20, **kw)
        r.raise_for_status()
        # Reject HTML error pages masquerading as success
        ct = r.headers.get("content-type", "")
        if "text/html" in ct and b"<!DOCTYPE" in r.content[:200].lower():
            log.warning("universe_builder: %s returned HTML page — skipping", url)
            return None
        return r.content
    except Exception as e:
        log.warning("universe_builder: GET %s failed: %s", url, e)
        return None


def _symbols_from_csv(raw: bytes) -> list[str]:
    """
    Parse a NiftyIndices constituent CSV robustly.
    These files have 1-4 metadata rows before the actual header row.
    The real header contains 'Symbol' or 'SYMBOL'.
    """
    try:
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()

        # Find the row index that contains the 'Symbol' column header
        header_idx = None
        for i, line in enumerate(lines):
            low = line.lower()
            if "symbol" in low and ("company" in low or "isin" in low):
                header_idx = i
                break

        if header_idx is None:
            # Fallback: just try reading as-is, skip bad rows
            df = pd.read_csv(io.BytesIO(raw), on_bad_lines="skip")
        else:
            df = pd.read_csv(
                io.StringIO("\n".join(lines[header_idx:])),
                on_bad_lines="skip",
            )

        col = next(
            (c for c in df.columns if c.strip().lower() in ("symbol", "symbols")),
            None,
        )
        if col is None:
            return []
        return [str(s).strip() for s in df[col].dropna()
                if str(s).strip() and str(s).strip() != "nan"]
    except Exception as e:
        log.warning("universe_builder: CSV parse error: %s", e)
        return []


# ── main builder ──────────────────────────────────────────────────────────────

async def fetch_universe() -> dict:
    """
    Download live data and return a universe dict:
    {
      "generated_at": ISO-timestamp,
      "all_symbols": [...],          # all NSE symbols
      "company_map": {sym: name},    # symbol → company name
      "categories": {                # sym → "Large-Cap" / "Mid-Cap" / etc.
          "TCS": "Large-Cap", ...
      },
      "sector_symbols": {            # sector → [sym, ...]
          "NIFTY IT": ["TCS", ...], ...
      }
    }
    """
    log.info("universe_builder: starting live fetch …")
    async with httpx.AsyncClient(follow_redirects=True) as client:

        # ── 1. NSE equity list ────────────────────────────────────────────────
        nse_extra = {
            "Referer": "https://www.nseindia.com/",
            "Host": "nsearchives.nseindia.com",
        }
        nse_raw = await _get(
            client,
            "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
            extra_headers=nse_extra,
        )
        all_symbols: list[str] = []
        company_map: dict[str, str] = {}

        if nse_raw:
            try:
                df_nse = pd.read_csv(io.BytesIO(nse_raw), on_bad_lines="skip")
                sym_col  = next(
                    (c for c in df_nse.columns if "symbol" in c.lower()), None
                )
                name_col = next(
                    (c for c in df_nse.columns
                     if "company" in c.lower() or "name" in c.lower()), None
                )
                if sym_col and name_col:
                    for _, row in df_nse.iterrows():
                        sym  = str(row[sym_col]).strip()
                        name = str(row[name_col]).strip()
                        if sym and sym != "nan":
                            all_symbols.append(sym)
                            company_map[sym] = name
                    log.info("universe_builder: NSE equity list → %d symbols", len(all_symbols))
                else:
                    log.warning("universe_builder: NSE CSV missing Symbol/Name columns")
            except Exception as e:
                log.warning("universe_builder: NSE CSV parse error: %s", e)

        # ── 2. AMFI cap classification ────────────────────────────────────────
        categories: dict[str, str] = {}
        now = datetime.now()
        # Try recent periods in reverse order until one works
        _periods: list[str] = []
        for yr in range(now.year, now.year - 3, -1):
            _periods.append(f"30-Jun-{yr}")
            _periods.append(f"31-Dec-{yr}")
        # Put most-likely-current period first
        if now.month >= 7:
            _periods.insert(0, f"30-Jun-{now.year}")
        else:
            _periods.insert(0, f"31-Dec-{now.year - 1}")

        amfi_raw: Optional[bytes] = None
        for period in _periods:
            amfi_url = (
                "https://www.amfiindia.com/Themes/Theme1/downloads/"
                f"Updated-list-of-large-mid-small-cap-{period}.xlsx"
            )
            amfi_raw = await _get(client, amfi_url)
            if amfi_raw:
                log.info("universe_builder: AMFI file found for period %s", period)
                break

        if amfi_raw:
            try:
                df_amfi = pd.read_excel(io.BytesIO(amfi_raw), header=1)
                ticker_col = next(
                    (c for c in df_amfi.columns
                     if "ticker" in c.lower() or c.strip().lower() == "symbol"),
                    None,
                )
                cat_col = next(
                    (c for c in df_amfi.columns if "category" in c.lower()),
                    None,
                )
                if ticker_col and cat_col:
                    for _, row in df_amfi.iterrows():
                        sym = str(row[ticker_col]).strip()
                        cat = str(row[cat_col]).strip()
                        if sym and cat and sym != "nan" and cat != "nan":
                            categories[sym] = cat
                    log.info("universe_builder: AMFI categories → %d entries", len(categories))
                else:
                    log.warning("universe_builder: AMFI Excel missing Ticker/Category columns")
            except Exception as e:
                log.warning("universe_builder: AMFI parse error: %s", e)

        # ── 3. Sector index constituents ──────────────────────────────────────
        sector_tasks = {
            sector: asyncio.create_task(
                _get(client, _NI_BASE + filename)
            )
            for sector, filename in SECTOR_CSV_MAP.items()
        }
        await asyncio.gather(*sector_tasks.values(), return_exceptions=True)

        sector_symbols: dict[str, list[str]] = {}
        for sector, task in sector_tasks.items():
            raw = task.result() if not task.exception() else None
            if raw:
                syms = _symbols_from_csv(raw)
                if syms:
                    sector_symbols[sector] = syms
                    log.info(
                        "universe_builder: %s → %d symbols", sector, len(syms)
                    )

        # ── 4. Derive cap lists from sector index data ────────────────────────
        # If we didn't get all_symbols from NSE CSV, fall back to sector data
        if not all_symbols:
            seen: set[str] = set()
            for syms in sector_symbols.values():
                for s in syms:
                    if s not in seen:
                        seen.add(s)
                        all_symbols.append(s)

        # Supplement categories from index membership if AMFI failed
        if not categories:
            nifty100 = set(sector_symbols.get("NIFTY 100", []))
            mid100   = set(sector_symbols.get("NIFTY MIDCAP 150", []))
            sm250    = set(sector_symbols.get("NIFTY SMALLCAP 250", []))
            mc250    = set(sector_symbols.get("NIFTY MICROCAP 250", []))
            for s in all_symbols:
                if s in nifty100:
                    categories[s] = "Large-Cap"
                elif s in mid100:
                    categories[s] = "Mid-Cap"
                elif s in sm250:
                    categories[s] = "Small-Cap"
                elif s in mc250:
                    categories[s] = "Micro-Cap"

        result = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "all_symbols":    all_symbols,
            "company_map":    company_map,
            "categories":     categories,
            "sector_symbols": sector_symbols,
        }
        log.info(
            "universe_builder: done — %d symbols, %d sectors",
            len(all_symbols), len(sector_symbols),
        )
        return result


# ── cache helpers ─────────────────────────────────────────────────────────────

def load_cache() -> Optional[dict]:
    """Return cached universe if it exists and is fresh, else None."""
    if not CACHE_FILE.exists():
        return None
    try:
        age = time.time() - CACHE_FILE.stat().st_mtime
        if age > CACHE_TTL:
            return None
        with CACHE_FILE.open() as f:
            return json.load(f)
    except Exception:
        return None


def save_cache(data: dict) -> None:
    try:
        with CACHE_FILE.open("w") as f:
            json.dump(data, f)
        log.info("universe_builder: cache saved to %s", CACHE_FILE)
    except Exception as e:
        log.warning("universe_builder: could not save cache: %s", e)


async def get_or_refresh() -> Optional[dict]:
    """Return fresh cache or fetch live and save."""
    cached = load_cache()
    if cached:
        log.info("universe_builder: using cache (%s)", cached.get("generated_at", "?"))
        return cached
    try:
        data = await fetch_universe()
        if data.get("all_symbols"):
            save_cache(data)
        return data
    except Exception as e:
        log.error("universe_builder: fetch failed: %s", e)
        return None


async def refresh_in_background() -> None:
    """Fire-and-forget background refresh — called from startup."""
    try:
        await get_or_refresh()
    except Exception as e:
        log.warning("universe_builder: background refresh error: %s", e)
