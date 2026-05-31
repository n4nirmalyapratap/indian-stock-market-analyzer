"""
Shared NSE/BSE index → Yahoo Finance ticker mapping.

Single source of truth — used by routes/stocks.py, services/sectors_service.py,
services/sector_analytics_service.py, and any future callers.

Index symbols (starting with ^) are returned as-is.
NSE equity symbols get the .NS suffix unless already present.
"""

# Map index display names → Yahoo Finance tickers
SYMBOL_MAP: dict[str, str] = {
    # ── NSE equity overrides — tickers where SYMBOL.NS is broken on Yahoo
    #    but the BSE code (XXXXXX.BO) works correctly. Add here whenever a
    #    merger / rename causes the .NS form to go dark on Yahoo Finance. ──
    "LTIM":        "540005.BO",   # LTIMindtree — LTIM.NS dark post-merger; BSE 540005 works

    # ── NSE Broad Market ──────────────────────────────────────────────────
    "NIFTY 50":                        "^NSEI",
    "NIFTY50":                         "^NSEI",
    "NIFTY":                           "^NSEI",
    "NIFTY NEXT 50":                   "^NSMIDCP",
    "NIFTYNEXT50":                     "^NSMIDCP",
    "NIFTY 100":                       "^CNX100",
    "NIFTY100":                        "^CNX100",
    "NIFTY 200":                       "^CNX200",
    "NIFTY200":                        "^CNX200",
    "NIFTY 500":                       "^CNX500",
    "NIFTY500":                        "^CNX500",
    "NIFTY MIDCAP 50":                 "NIFMID50.NS",
    "NIFTY MIDCAP50":                  "NIFMID50.NS",
    "NIFTY MIDCAP 100":                "^CNXMID",
    "NIFTY MIDCAP100":                 "^CNXMID",
    "NIFTY MIDCAP 150":                "^NIFMDCP150",
    "NIFTY MIDCAP150":                 "^NIFMDCP150",
    "NIFTY MIDCAP SELECT":             "NIFMDCPSEL.NS",
    "NIFTY SMALLCAP 50":               "NIFTYSC50.NS",
    "NIFTY SMALLCAP50":                "NIFTYSC50.NS",
    "NIFTY SMALLCAP 100":              "^CNXSC",
    "NIFTY SMALLCAP100":               "^CNXSC",
    "NIFTY SMALLCAP 250":              "^CNXSMCP250",
    "NIFTY SMALLCAP250":               "^CNXSMCP250",
    "NIFTY MICROCAP 250":              "NIFTYMICRO250.NS",
    "NIFTY LARGEMIDCAP 250":           "^NIFTYLARGMID250",

    # ── NSE Sectoral ──────────────────────────────────────────────────────
    "NIFTY BANK":                      "^NSEBANK",
    "BANKNIFTY":                       "^NSEBANK",
    "BANK NIFTY":                      "^NSEBANK",
    "NIFTY FIN SERVICE":               "^CNXFIN",
    "NIFTY FINANCIAL SERVICES":        "^CNXFIN",
    "FINNIFTY":                        "^CNXFIN",
    "NIFTY IT":                        "^CNXIT",
    "NIFTY AUTO":                      "^CNXAUTO",
    "NIFTY PHARMA":                    "^CNXPHARMA",
    "NIFTY FMCG":                      "^CNXFMCG",
    "NIFTY METAL":                     "^CNXMETAL",
    "NIFTY REALTY":                    "^CNXREALTY",
    "NIFTY ENERGY":                    "^CNXENERGY",
    "NIFTY INFRA":                     "^CNXINFRA",
    "NIFTY INFRASTRUCTURE":            "^CNXINFRA",
    "NIFTY PSU BANK":                  "^CNXPSUBANK",
    "NIFTY MNC":                       "^CNXMNC",
    "NIFTY MEDIA":                     "^CNXMEDIA",
    # Yahoo dropped ^CNXHEALTH in late 2025 (404s on every fetch). We
    # keep the slug in `YAHOO_UNAVAILABLE_TICKERS` below so the chain
    # skips Yahoo entirely and goes NSE-direct for the sector card.
    "NIFTY HEALTHCARE":                "^CNXHEALTH",
    "NIFTY HEALTHCARE INDEX":          "^CNXHEALTH",
    "NIFTY COMMODITIES":               "^CNXCOMDTY",
    "NIFTY SERVICES SECTOR":           "^CNXSERVICE",
    "NIFTY CPSE":                      "^CNXCPSE",
    "NIFTY PSE":                       "^CNXPSE",
    "NIFTY OIL & GAS":                 "^CNXOILGAS",
    "NIFTY OIL AND GAS":               "^CNXOILGAS",
    "NIFTY CONSUMER DURABLES":         "^CNXCONDURAB",
    "NIFTY INDIA CONSUMPTION":         "^CNXCONSUM",
    "NIFTY INDIA DIGITAL":             "^CNXDIGITAL",
    "NIFTY INDIA DEFENCE":             "NIFTYINDDEF.NS",
    "MIDCPNIFTY":                      "^NIFMDCP150",

    # ── NSE Strategy / Thematic ──────────────────────────────────────────
    "INDIA VIX":                       "^NSEVIXY",
    "NIFTY ALPHA 50":                  "^NIFTYALPHA50",
    "NIFTY50 VALUE 20":                "^NIFTVAL20",
    "NIFTY QUALITY LOW-VOLATILITY 30": "^NIFQL30",

    # ── BSE Broad Market ──────────────────────────────────────────────────
    "SENSEX":                          "^BSESN",
    "BSE SENSEX":                      "^BSESN",
    "BSE 100":                         "^BSE100",
    "BSE100":                          "^BSE100",
    "BSE 200":                         "^BSE200",
    "BSE200":                          "^BSE200",
    "BSE 500":                         "^BSE500",
    "BSE500":                          "^BSE500",
    "BSE MIDCAP":                      "^BSEMIDCAP",
    "BSE MID CAP":                     "^BSEMIDCAP",
    "BSE SMALLCAP":                    "^BSESMLCAP",
    "BSE SMALL CAP":                   "^BSESMLCAP",
    "BSE LARGECAP":                    "^BSELCAP",
    "BSE LARGE CAP":                   "^BSELCAP",

    # ── BSE Sectoral ──────────────────────────────────────────────────────
    "BANKEX":                          "^BSEBANKEX",
    "BSE BANKEX":                      "^BSEBANKEX",
    "BSE IT":                          "^BSEIT",
    "BSE HEALTHCARE":                  "^BSEHEALTHCARE",
    "BSE AUTO":                        "^BSEAUTO",
    "BSE FMCG":                        "^BSEFMCG",
    "BSE METAL":                       "^BSEMETAL",
    "BSE REALTY":                      "^BSEREALTY",
    "BSE ENERGY":                      "^BSEENERGY",
    "BSE POWER":                       "^BSEPOWER",
    "BSE CAPITAL GOODS":               "^BSECG",
    "BSE CONSUMER DURABLES":           "^BSECD",
    "BSE TECK":                        "^BSETECK",
    "BSE OIL & GAS":                   "^BSEOILGAS",
    "BSE OIL AND GAS":                 "^BSEOILGAS",
    "BSE UTILITIES":                   "^BSEUTIL",
    "BSE FINANCE":                     "^BSEFINANCE",
    "BSE INDUSTRIALS":                 "^BSEINDUS",
    "BSE TELECOM":                     "^BSETELECOM",
    "BSE COMMODITIES":                 "^BSECOMDTY",
}


def to_yahoo_ticker(symbol: str) -> str:
    """Resolve any NSE / BSE / index symbol to its Yahoo Finance ticker.

    Rules (in order):
      1. Explicit map hit (case-insensitive, normalised whitespace)
      2. Already a Yahoo-style ticker (^... or already has a dot suffix) → as-is
      3. NSE equity → append .NS
    """
    if not symbol:
        return symbol
    sym = symbol.strip().upper()
    if sym in SYMBOL_MAP:
        return SYMBOL_MAP[sym]
    # Already a Yahoo-style ticker — leave it alone.
    #   ^...   → index ticker (e.g. ^NSEI)
    #   X.Y    → already suffixed (e.g. RELIANCE.NS, DX-Y.NYB)
    #   =X     → FX pair (e.g. INR=X)
    #   =F     → futures contract (e.g. BZ=F, GC=F)
    if sym.startswith("^") or "." in sym or "=" in sym:
        return sym
    return f"{sym}.NS"


def is_index_symbol(symbol: str) -> bool:
    """True for NSE/BSE indices (which NSE's equity-history API can't serve).

    Used by PriceService to skip the NSE-equity path for indices and go
    straight to Yahoo, which has full OHLCV history for `^...` tickers.
    """
    if not symbol:
        return False
    sym = symbol.strip().upper()
    if sym.startswith("^"):
        return True
    mapped = SYMBOL_MAP.get(sym)
    return bool(mapped and mapped.startswith("^"))


# Yahoo-side tickers that consistently 404. Adding a slug or its Yahoo
# alias here makes `yahoo_candidates()` return [] and `is_yahoo_unavailable()`
# return True — callers skip Yahoo entirely instead of burning HTTP round-trips
# and polluting logs with `possibly delisted` warnings from yfinance.
#
# Both raw aliases ('^CNXHEALTH') and our slug names ('NIFTY HEALTHCARE')
# are included so the check is one-shot regardless of where in the chain
# we're called.
YAHOO_UNAVAILABLE_TICKERS: set[str] = {
    # NSE Healthcare — Yahoo dropped late 2025
    "^CNXHEALTH",
    "NIFTY HEALTHCARE", "NIFTY HEALTHCARE INDEX",
    # NSE Oil & Gas — Yahoo dropped late 2025
    "^CNXOILGAS",
    "NIFTY OIL & GAS", "NIFTY OIL AND GAS",
}


def is_yahoo_unavailable(symbol: str) -> bool:
    """True when this symbol is known to 404 on Yahoo. Lookups treat it
    as "Yahoo has nothing here" so the chain skips Yahoo and tries the
    next provider (NSE/BSE direct, Twelve Data, Stooq, history-derived).

    Both the canonical slug ('NIFTY HEALTHCARE') and the mapped Yahoo
    ticker ('^CNXHEALTH') match — order doesn't matter.
    """
    if not symbol:
        return False
    sym = symbol.strip().upper()
    if sym in YAHOO_UNAVAILABLE_TICKERS:
        return True
    mapped = SYMBOL_MAP.get(sym)
    return mapped is not None and mapped in YAHOO_UNAVAILABLE_TICKERS


def yahoo_candidates(symbol: str) -> list[str]:
    """Return ordered Yahoo ticker candidates for fallback lookup.
    Empty list when the symbol is on the Yahoo-unavailable list — that
    tells the YahooProvider to short-circuit instead of hitting the API.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return []
    if is_yahoo_unavailable(sym):
        return []
    if sym in SYMBOL_MAP:
        return [SYMBOL_MAP[sym]]
    if sym.startswith("^") or "." in sym or "=" in sym:
        return [sym]
    return [f"{sym}.NS", sym]
