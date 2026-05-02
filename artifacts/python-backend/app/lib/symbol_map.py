"""
Shared NSE/BSE index → Yahoo Finance ticker mapping.

Single source of truth — used by routes/stocks.py, services/sectors_service.py,
services/sector_analytics_service.py, and any future callers.

Index symbols (starting with ^) are returned as-is.
NSE equity symbols get the .NS suffix unless already present.
"""

# Map index display names → Yahoo Finance tickers
SYMBOL_MAP: dict[str, str] = {
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
    if sym.startswith("^") or "." in sym:
        return sym
    return f"{sym}.NS"


def yahoo_candidates(symbol: str) -> list[str]:
    """Return ordered Yahoo ticker candidates for fallback lookup."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return []
    if sym in SYMBOL_MAP:
        return [SYMBOL_MAP[sym]]
    if sym.startswith("^"):
        return [sym]
    return [f"{sym}.NS", sym]
