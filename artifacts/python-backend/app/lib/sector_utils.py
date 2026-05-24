"""Centralized sector classification utilities.

Single source of truth for:
  - NSE / Yahoo raw sector string  →  canonical display sector name
  - Symbol → sector (built from Nifty index constituents at import)
  - Market-cap bucket classification (Large / Mid / Small Cap)
  - Fuzzy sector matching for unrecognised strings

Import from anywhere in the app — never duplicate this logic.
"""
from __future__ import annotations

import difflib
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# ── Raw string → canonical sector display name ────────────────────────────────
# Keys are matched case-insensitively.  Add any new raw string you encounter
# here; do NOT scatter mapping tables across the codebase.

_RAW_TO_SECTOR: dict[str, str] = {
    # Nifty index names (as stored in SECTOR_SYMBOLS keys)
    "nifty it":                   "Information Technology",
    "nifty bank":                 "Banking",
    "nifty psu bank":             "PSU Banks",
    "nifty private bank":         "Banking",
    "nifty auto":                 "Automobiles",
    "nifty pharma":               "Pharmaceuticals",
    "nifty fmcg":                 "FMCG",
    "nifty metal":                "Metals & Mining",
    "nifty realty":               "Real Estate",
    "nifty energy":               "Energy",
    "nifty media":                "Media & Entertainment",
    "nifty financial services":   "Financial Services",
    "nifty consumer durables":    "Consumer Durables",
    "nifty oil and gas":          "Oil & Gas",
    "nifty oil & gas":            "Oil & Gas",
    "nifty healthcare index":     "Healthcare",
    "nifty healthcare":           "Healthcare",
    "nifty infrastructure":       "Infrastructure",
    "nifty chemicals":            "Chemicals",
    "nifty cement":               "Cement",
    "nifty defence":              "Defence",
    # Yahoo Finance sector strings
    "technology":                 "Information Technology",
    "information technology":     "Information Technology",
    "it":                         "Information Technology",
    "software":                   "Information Technology",
    "financial services":         "Financial Services",
    "financial":                  "Financial Services",
    "banking":                    "Banking",
    "banks":                      "Banking",
    "bank":                       "Banking",
    "healthcare":                 "Healthcare",
    "health care":                "Healthcare",
    "pharmaceuticals":            "Pharmaceuticals",
    "pharma":                     "Pharmaceuticals",
    "pharmaceutical":             "Pharmaceuticals",
    "consumer cyclical":          "Consumer Durables",
    "consumer discretionary":     "Consumer Durables",
    "consumer durables":          "Consumer Durables",
    "consumer defensive":         "FMCG",
    "consumer goods":             "FMCG",
    "fast moving consumer goods": "FMCG",
    "fmcg":                       "FMCG",
    "automobiles":                "Automobiles",
    "auto":                       "Automobiles",
    "automobile":                 "Automobiles",
    "automotive":                 "Automobiles",
    "energy":                     "Energy",
    "oil & gas":                  "Oil & Gas",
    "oil and gas":                "Oil & Gas",
    "basic materials":            "Metals & Mining",
    "materials":                  "Metals & Mining",
    "metals & mining":            "Metals & Mining",
    "metals and mining":          "Metals & Mining",
    "metal":                      "Metals & Mining",
    "mining":                     "Metals & Mining",
    "real estate":                "Real Estate",
    "realty":                     "Real Estate",
    "industrials":                "Infrastructure",
    "infrastructure":             "Infrastructure",
    "capital goods":              "Infrastructure",
    "utilities":                  "Energy",
    "power":                      "Energy",
    "communication services":     "Media & Entertainment",
    "communication":              "Media & Entertainment",
    "media":                      "Media & Entertainment",
    "media & entertainment":      "Media & Entertainment",
    "chemicals":                  "Chemicals",
    "specialty chemicals":        "Chemicals",
    "cement":                     "Cement",
    "cement & construction":      "Cement",
    "defence":                    "Defence",
    "defense":                    "Defence",
    "aerospace & defence":        "Defence",
    "insurance":                  "Financial Services",
    "textiles":                   "Textiles",
    "textile":                    "Textiles",
    "agriculture":                "Agriculture",
    "agri":                       "Agriculture",
    "food & beverages":           "FMCG",
    "food processing":            "FMCG",
    "retail":                     "Consumer Durables",
    "telecom":                    "Telecom",
    "telecommunications":         "Telecom",
    "shipping":                   "Infrastructure",
    "logistics":                  "Infrastructure",
    "aviation":                   "Infrastructure",
}

# All canonical sector names — used as fuzzy-match targets
_CANONICAL_SECTORS: list[str] = sorted(set(_RAW_TO_SECTOR.values()))

# Nifty cap-tier indices — NOT sectors, skip when building symbol map
_INDEX_SKIP: set[str] = {
    "NIFTY 50", "NIFTY 100", "NIFTY 200", "NIFTY 500",
    "NIFTY MIDCAP 50", "NIFTY MIDCAP 100", "NIFTY MIDCAP 150",
    "NIFTY MIDCAP SELECT", "NIFTY LARGEMIDCAP 250",
    "NIFTY SMALLCAP 50", "NIFTY SMALLCAP 100", "NIFTY SMALLCAP 250",
    "NIFTY MICROCAP 250",
}

# Pre-built lowercase canonical list for fast fuzzy matching
_CANON_LOWER: list[str] = [s.lower() for s in _CANONICAL_SECTORS]
_LOWER_TO_CANON: dict[str, str] = {s.lower(): s for s in _CANONICAL_SECTORS}


@lru_cache(maxsize=1)
def _stock_sector_map() -> dict[str, str]:
    """Return {bare_symbol: canonical_sector} built from Nifty index constituents."""
    try:
        from ..lib.universe import SECTOR_SYMBOLS as _SS  # type: ignore
    except Exception:
        return {}
    out: dict[str, str] = {}
    for index_name, syms in _SS.items():
        if index_name in _INDEX_SKIP:
            continue
        sector = _RAW_TO_SECTOR.get(index_name.lower())
        if not sector:
            continue
        for sym in syms:
            bare = sym.replace(".NS", "").replace(".BO", "")
            if bare not in out:  # first assignment wins
                out[bare] = sector
    logger.info("sector_utils: %d symbols classified across sectors", len(out))
    return out


def classify_sector(raw: str | None, symbol: str | None = None) -> str:
    """Resolve a raw sector/industry string to a canonical display sector name.

    Resolution order:
      1. Symbol lookup via Nifty-index constituent map (most authoritative)
      2. Exact case-insensitive match in _RAW_TO_SECTOR
      3. Fuzzy match against canonical names (difflib cutoff 0.6)
      4. Title-case of the original raw string (better than "Unknown")
      5. "Other" if everything is empty/None

    Parameters
    ----------
    raw:    Raw sector/industry string from NSE or Yahoo Finance.
    symbol: NSE/BSE bare symbol — enables the most reliable path (index map).
    """
    # 1. Symbol lookup
    if symbol:
        bare = symbol.upper().replace(".NS", "").replace(".BO", "").strip()
        mapped = _stock_sector_map().get(bare)
        if mapped:
            return mapped

    if not raw:
        return "Other"

    cleaned = raw.strip()
    if not cleaned or cleaned.lower() in ("unknown", "none", "n/a", "-"):
        return "Other"

    # 2. Exact lookup (case-insensitive)
    exact = _RAW_TO_SECTOR.get(cleaned.lower())
    if exact:
        return exact

    # 3. Fuzzy match
    matches = difflib.get_close_matches(cleaned.lower(), _CANON_LOWER, n=1, cutoff=0.6)
    if matches:
        return _LOWER_TO_CANON[matches[0]]

    # 4. Title-case the raw value — preserve whatever the data source gave us
    return cleaned.title()


def classify_market_cap(market_cap_inr: float | int | None) -> str:
    """Classify a market cap (raw rupees from Yahoo Finance) into a cap bucket.

    Thresholds (SEBI / NSE convention):
      ≥ ₹50,000 Cr  →  Large Cap
      ≥ ₹10,000 Cr  →  Mid Cap
      >  0           →  Small Cap
      else           →  Unknown
    """
    if not market_cap_inr:
        return "Unknown"
    mc = float(market_cap_inr)
    if mc >= 50_000 * 1e7:
        return "Large Cap"
    if mc >= 10_000 * 1e7:
        return "Mid Cap"
    if mc > 0:
        return "Small Cap"
    return "Unknown"
