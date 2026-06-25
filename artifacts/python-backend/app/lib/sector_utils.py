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


# ── Supplementary hardcoded symbol → sector map ──────────────────────────────
# Covers stocks NOT in the live NSE index constituent lists (SECTOR_SYMBOLS).
# Live SECTOR_SYMBOLS shrinks to actual index members (~12–25 per index);
# this map ensures top-traded stocks always have a sector regardless.
#
# HOW TO ADD A STOCK — edit ONLY THIS FILE:
#   1. Add  "SYMBOL": "Canonical Sector"  to _EXTRA_SECTOR_MAP below.
#   2. Optionally add  "SYMBOL": "Sub-industry name"  to _EXTRA_SUBSECTOR_MAP
#      (must match the sub_industry string used in the stocks DB / SUBSECTOR_TAXONOMY).
#   3. Restart the backend — the change flows to:
#        • Delivery drawer (sector label)
#        • Sector Rotation Cockpit sector shortlist
#        • Sector Rotation Cockpit sub-industry shortlist (if in _EXTRA_SUBSECTOR_MAP)
#        • Any other caller of classify_sector() / get_sector_symbols()
#
# ── Sub-industry overrides — symbol → exact sub_industry string ───────────────
# Optional.  The sub_industry string must match the value stored in the
# `sub_industry_overrides` / `stocks` DB table (from SUBSECTOR_TAXONOMY or
# Yahoo classification).  Leave blank if you only need the sector label.
_EXTRA_SUBSECTOR_MAP: dict[str, str] = {
    # ── Defence & Aerospace ───────────────────────────────────────────────────
    "HAL":        "Defence & Aerospace",
    "BEL":        "Defence & Aerospace",
    "BEML":       "Defence & Aerospace",
    "GRSE":       "Defence & Aerospace",
    "COCHINSHIP": "Defence & Aerospace",
    "MTAR":       "Defence & Aerospace",
    "BDL":        "Defence & Aerospace",
    "MAZDOCK":    "Defence & Aerospace",
    "MIDHANI":    "Defence & Aerospace",
    "DCXINDIA":   "Defence & Aerospace",
    "ASTRAMICRO": "Defence & Aerospace",
    "PARAS":      "Defence & Aerospace",
    # ── Agrochemicals & Fertilizers ───────────────────────────────────────────
    "DHANUKA":    "Agrochemicals & Fertilizers",
    "RALLIS":     "Agrochemicals & Fertilizers",
    "NFL":        "Agrochemicals & Fertilizers",
    "CHAMBLFERT": "Agrochemicals & Fertilizers",
    "DEEPAKFERT": "Agrochemicals & Fertilizers",
    "BALRAMCHIN": "Agrochemicals & Fertilizers",
    "COROMANDEL": "Agrochemicals & Fertilizers",
    "PARADEEP":   "Agrochemicals & Fertilizers",
    "PIIND":      "Agrochemicals & Fertilizers",
    "SUMICHEM":   "Agrochemicals & Fertilizers",
    # ── Specialty Chemicals ───────────────────────────────────────────────────
    "DEEPAKNTR":  "Specialty Chemicals",
    "PIDILITIND": "Specialty Chemicals",
    "TATACHEM":   "Specialty Chemicals",
    "AARTI":      "Specialty Chemicals",
    "SUDARSCHEM": "Specialty Chemicals",
    "ATUL":       "Specialty Chemicals",
    "VINATI":     "Specialty Chemicals",
    "NAVINFLUOR": "Specialty Chemicals",
    # ── Hospitals & Healthcare Services ──────────────────────────────────────
    "APOLLOHOSP": "Hospitals & Healthcare",
    "MAXHEALTH":  "Hospitals & Healthcare",
    "FORTIS":     "Hospitals & Healthcare",
    "HCG":        "Hospitals & Healthcare",
    "YATHARTH":   "Hospitals & Healthcare",
    "PARKHOSPS":  "Hospitals & Healthcare",
    "KIMS":       "Hospitals & Healthcare",
    "RAINBOW":    "Hospitals & Healthcare",
    # ── Diagnostics & Labs ───────────────────────────────────────────────────
    "METROPOLIS": "Diagnostics & Labs",
    "THYROCARE":  "Diagnostics & Labs",
    "LALPATHLAB": "Diagnostics & Labs",
    "KRSNAA":     "Diagnostics & Labs",
    # ── Power & Utilities ─────────────────────────────────────────────────────
    "NTPC":       "Power & Utilities",
    "POWERGRID":  "Power & Utilities",
    "TATAPOWER":  "Power & Utilities",
    "ADANIGREEN": "Power & Utilities",
    "ADANIENSOL": "Power & Utilities",
    "TORNTPOWER": "Power & Utilities",
    "CESC":       "Power & Utilities",
    "NHPC":       "Power & Utilities",
    # ── Oil & Gas Distribution ────────────────────────────────────────────────
    "BPCL":       "Oil & Gas Distribution",
    "HPCL":       "Oil & Gas Distribution",
    "IOC":        "Oil & Gas Distribution",
    "GAIL":       "Oil & Gas Distribution",
    "MGL":        "Oil & Gas Distribution",
    "IGL":        "Oil & Gas Distribution",
    "PETRONET":   "Oil & Gas Distribution",
    "GUJGASLTD":  "Oil & Gas Distribution",
    # ── NBFCs & Consumer Finance ──────────────────────────────────────────────
    "BAJFINANCE": "NBFCs & Consumer Finance",
    "BAJAJFINSV": "NBFCs & Consumer Finance",
    "MUTHOOTFIN": "NBFCs & Consumer Finance",
    "CHOLAFIN":   "NBFCs & Consumer Finance",
    "LTF":        "NBFCs & Consumer Finance",
    "SHRIRAMFIN": "NBFCs & Consumer Finance",
    "SBICARD":    "NBFCs & Consumer Finance",
    "ABCAPITAL":  "NBFCs & Consumer Finance",
    # ── Life Insurance ────────────────────────────────────────────────────────
    "HDFCLIFE":   "Life Insurance",
    "SBILIFE":    "Life Insurance",
    "ICICIPRULI": "Life Insurance",
    "MAXFINSERV": "Life Insurance",
    # ── Logistics & Ports ─────────────────────────────────────────────────────
    "ADANIPORTS": "Logistics & Ports",
    "CONCOR":     "Logistics & Ports",
    "IRCTC":      "Logistics & Ports",
    "IRCON":      "Logistics & Ports",
    "IRFC":       "Logistics & Ports",
    "RVNL":       "Logistics & Ports",
    "HUDCO":      "Logistics & Ports",
    # ── Cement ────────────────────────────────────────────────────────────────
    "ULTRACEMCO": "Cement",
    "SHREECEM":   "Cement",
    "AMBUJACEM":  "Cement",
    "JKCEMENT":   "Cement",
    "DALMIACEM":  "Cement",
    "RAMCOCEM":   "Cement",
}
# Add new symbols here; use canonical sector names from _RAW_TO_SECTOR values.
# User-specified overrides go at the BOTTOM of each sector block.

_EXTRA_SECTOR_MAP: dict[str, str] = {
    # ── Banking ───────────────────────────────────────────────────────────────
    "HDFCBANK":    "Banking", "ICICIBANK":   "Banking", "AXISBANK":    "Banking",
    "KOTAKBANK":   "Banking", "INDUSINDBK":  "Banking", "SBIN":        "Banking",
    "BANKBARODA":  "Banking", "PNB":         "Banking", "CANBK":       "Banking",
    "FEDERALBNK":  "Banking", "IDFCFIRSTB":  "Banking", "BANDHANBNK":  "Banking",
    "RBLBANK":     "Banking", "YESBANK":     "Banking", "KARURVYSYA":  "Banking",
    "DCBBANK":     "Banking", "SOUTHBANK":   "Banking", "CSBBANK":     "Banking",
    "JKBANK":      "Banking", "UCOBANK":     "Banking", "IOB":         "Banking",
    "CENTRALBNK":  "Banking", "MAHABANK":    "Banking", "UJJIVANSFB":  "Banking",
    "EQUITASBNK":  "Banking", "UTKARSHBNK":  "Banking", "SURYODAY":    "Banking",
    "IDBI":        "Banking", "TMB":         "Banking", "JSFB":        "Banking",
    "LAKSHVILAS":  "Banking",
    # ── Financial Services ────────────────────────────────────────────────────
    "BAJFINANCE":  "Financial Services", "BAJAJFINSV":  "Financial Services",
    "MUTHOOTFIN":  "Financial Services", "SBILIFE":     "Financial Services",
    "HDFCLIFE":    "Financial Services", "CHOLAFIN":    "Financial Services",
    "LTFH":        "Financial Services", "LTF":         "Financial Services",
    "MANAPPURAM":  "Financial Services", "SHRIRAMFIN":  "Financial Services",
    "MFSL":        "Financial Services", "IIFL":        "Financial Services",
    "360ONE":      "Financial Services", "ANANDRAT":    "Financial Services",
    "CAMS":        "Financial Services", "CDSL":        "Financial Services",
    "IEX":         "Financial Services", "CANFINHOME":  "Financial Services",
    "AAVAS":       "Financial Services", "APTUS":       "Financial Services",
    "HOMEFIRST":   "Financial Services", "CREDITACC":   "Financial Services",
    "ARMANFIN":    "Financial Services", "SPANDANA":    "Financial Services",
    "ICICIPRULI":  "Financial Services", "CRISIL":      "Financial Services",
    "IIFLWAM":     "Financial Services", "MOTILALOS":   "Financial Services",
    "5PAISA":      "Financial Services", "ANGELONE":    "Financial Services",
    "JMFINANCIL":  "Financial Services", "PNBHOUSING":  "Financial Services",
    "FIVESTAR":    "Financial Services", "INDOSTAR":    "Financial Services",
    "MCX":         "Financial Services", "BSE":         "Financial Services",
    "PINELABS":    "Financial Services", "GROWW":       "Financial Services",
    "M&MFIN":      "Financial Services", "IFCI":        "Financial Services",
    "TATACAP":     "Financial Services", "ABCAPITAL":   "Financial Services",
    "CHOLAHLDNG":  "Financial Services", "BAJAJHFL":    "Financial Services",
    "FEDFINA":     "Financial Services", "SBFC":        "Financial Services",
    "MANCREDIT":   "Financial Services", "FUSION":      "Financial Services",
    "HDBFS":       "Financial Services", "NORTHARC":    "Financial Services",
    "SATIN":       "Financial Services", "AYE":         "Financial Services",
    "UTIAMC":      "Financial Services", "PRUDENT":     "Financial Services",
    "IIFLCAPS":    "Financial Services", "MUTHOOTMF":   "Financial Services",
    "PAISALO":     "Financial Services", "CHOICEIN":    "Financial Services",
    "EMKAY":       "Financial Services", "SHAREINDIA":  "Financial Services",
    "PROTEAN":     "Financial Services", "CGCL":        "Financial Services",
    "LICI":        "Financial Services", "STARHEALTH":  "Financial Services",
    "HDFCAMC":     "Financial Services", "NIPPINDIA":   "Financial Services",
    "GEOJIT":      "Financial Services", "REPCO":       "Financial Services",
    "ICICIB22":    "Financial Services", "BAJAJST":     "Financial Services",
    "JISLJALEQS":  "Financial Services", "AADHARHFC":   "Financial Services",
    "SBCL":        "Financial Services", "TSFINV":      "Financial Services",
    "GICHSGFIN":   "Financial Services", "MOBIKWIK":    "Financial Services",
    # ── Information Technology ────────────────────────────────────────────────
    "TCS":         "Information Technology", "INFY":    "Information Technology",
    "HCLTECH":     "Information Technology", "WIPRO":   "Information Technology",
    "TECHM":       "Information Technology", "PERSISTENT": "Information Technology",
    "COFORGE":     "Information Technology", "MPHASIS": "Information Technology",
    "LTTS":        "Information Technology", "KPITTECH": "Information Technology",
    "TATAELXSI":   "Information Technology", "CYIENT":  "Information Technology",
    "MASTEK":      "Information Technology", "BIRLASOFT": "Information Technology",
    "HAPPSTMNDS":  "Information Technology", "TANLA":   "Information Technology",
    "ROUTE":       "Information Technology", "LATENTVIEW": "Information Technology",
    "NAZARA":      "Information Technology", "INTELLECT": "Information Technology",
    "NEWGEN":      "Information Technology", "NUCLEUS":  "Information Technology",
    "DATAMATICS":  "Information Technology", "KFINTECH": "Information Technology",
    "RAMCOSYS":    "Information Technology", "NETWEB":   "Information Technology",
    "NAUKRI":      "Information Technology", "ZENSARTECH": "Information Technology",
    "ECLERX":      "Information Technology", "RATEGAIN": "Information Technology",
    "AFFLE":       "Information Technology", "MOSCHIP":  "Information Technology",
    "MAPMYINDIA":  "Information Technology", "NIITLTD":  "Information Technology",
    "SONATSOFTW":  "Information Technology", "AURIONPRO": "Information Technology",
    "SHILCTECH":   "Information Technology", "AXISCADES": "Information Technology",
    "CYIENTDLM":   "Information Technology", "GENESYS":  "Information Technology",
    "FRACTAL":     "Information Technology", "INDIAMART": "Information Technology",
    "IXIGO":       "Information Technology", "BSOFT":    "Information Technology",
    "SASKEN":      "Information Technology", "PACEDIGITK": "Information Technology",
    "RPTECH":      "Information Technology", "TBOTEK":   "Information Technology",
    "BLACKBUCK":   "Information Technology", "SAKSOFT":  "Information Technology",
    "MASTECH":     "Information Technology",
    # ── Telecom ───────────────────────────────────────────────────────────────
    "BHARTIARTL":  "Telecom", "IDEA":        "Telecom", "TATACOMM":    "Telecom",
    "HFCL":        "Telecom", "TEJASNET":    "Telecom", "INDUSTOWER":  "Telecom",
    "VINDHYATEL":  "Telecom", "BHARTIHEXA":  "Telecom", "TTML":        "Telecom",
    # ── Infrastructure & Logistics ────────────────────────────────────────────
    "LT":          "Infrastructure", "ADANIPORTS":  "Infrastructure",
    "CONCOR":      "Infrastructure", "IRCTC":       "Infrastructure",
    "RVNL":        "Infrastructure", "IRCON":       "Infrastructure",
    "IRFC":        "Infrastructure", "HUDCO":       "Infrastructure",
    "IRB":         "Infrastructure", "ASHOKA":      "Infrastructure",
    "PNCINFRA":    "Infrastructure", "GMRINFRA":    "Infrastructure",
    "CAPACITE":    "Infrastructure", "BHEL":        "Infrastructure",
    "GMRAIRPORT":  "Infrastructure", "JSWINFRA":    "Infrastructure",
    "DELHIVERY":   "Infrastructure", "PATELENG":    "Infrastructure",
    "SCI":         "Infrastructure", "NCC":         "Infrastructure",
    "TRANSRAILL":  "Infrastructure", "CEIGALL":     "Infrastructure",
    "DBL":         "Infrastructure", "KNRCON":      "Infrastructure",
    "RAILTEL":     "Infrastructure", "GPPL":        "Infrastructure",
    "JKIL":        "Infrastructure", "POWERMECH":   "Infrastructure",
    "PSPPROJECT":  "Infrastructure", "SPMLINFRA":   "Infrastructure",
    "SIS":         "Infrastructure", "TCIEXP":      "Infrastructure",
    "SANGHVIMOV":  "Infrastructure", "ABINFRA":     "Infrastructure",
    "TEXINFRA":    "Infrastructure", "INDIANHUME":  "Infrastructure",
    "MONTECARLO":  "Infrastructure",
    # ── Capital Goods ─────────────────────────────────────────────────────────
    "SIEMENS":     "Capital Goods",  "ABB":         "Capital Goods",
    "HAVELLS":     "Capital Goods",  "VOLTAS":      "Capital Goods",
    "WHIRLPOOL":   "Capital Goods",  "BLUESTARCO":  "Capital Goods",
    "VGUARD":      "Capital Goods",  "CROMPTON":    "Capital Goods",
    "AMBER":       "Capital Goods",  "DIXON":       "Capital Goods",
    "KIRLOSENG":   "Capital Goods",  "KAYNES":      "Capital Goods",
    "JYOTICNC":    "Capital Goods",  "SHAKTIPUMP":  "Capital Goods",
    "TDPOWERSYS":  "Capital Goods",  "TRITURBINE":  "Capital Goods",
    "CUMMINSIND":  "Capital Goods",  "APARINDS":    "Capital Goods",
    "POLYCAB":     "Capital Goods",  "ELGIEQUIP":   "Capital Goods",
    "GENUSPOWER":  "Capital Goods",  "SYRMA":       "Capital Goods",
    "SCHAEFFLER":  "Capital Goods",  "TIMKEN":      "Capital Goods",
    "KSB":         "Capital Goods",  "SKFINDUS":    "Capital Goods",
    "ELECON":      "Capital Goods",  "UNIMECH":     "Capital Goods",
    "DYNAMATECH":  "Capital Goods",  "GRINDWELL":   "Capital Goods",
    "SUNDRMFAST":  "Capital Goods",  "ACE":         "Capital Goods",
    "JASH":        "Capital Goods",  "ANUP":        "Capital Goods",
    "KIRLOSIND":   "Capital Goods",  "KIRLPNU":     "Capital Goods",
    "INGERRAND":   "Capital Goods",  "WENDT":       "Capital Goods",
    "LINDEINDIA":  "Capital Goods",  "EIMCOELECO":  "Capital Goods",
    "EPACK":       "Capital Goods",  "EPACKPEB":    "Capital Goods",
    "HPL":         "Capital Goods",  "GOODLUCK":    "Capital Goods",
    "KEC":         "Capital Goods",  "SPAL":        "Capital Goods",
    "ROTO":        "Capital Goods",  "BEL":         "Capital Goods",
    "BEML":        "Capital Goods",  "HAL":         "Capital Goods",
    "SKYGOLD":     "Consumer Durables",
    "CARBORUNIV":  "Capital Goods",  "RKFORGE":     "Capital Goods",
    "JTLIND":      "Capital Goods",  "NRBBEARING":  "Capital Goods",
    "CENTUM":      "Capital Goods",  "GNA":         "Capital Goods",
    "HARIOMPIPE":  "Capital Goods",  "PRINCEPIPE":  "Capital Goods",
    "INTERARCH":   "Capital Goods",  "MACPOWER":    "Capital Goods",
    "SURYAROSNI":  "Capital Goods",  "IGARASHI":    "Capital Goods",
    "RPSGVENT":    "Capital Goods",  "RISHABH":     "Capital Goods",
    "ESABINDIA":   "Capital Goods",  "LLOYDSENT":   "Capital Goods",
    "WELENT":      "Capital Goods",  "DATAPATTNS":  "Capital Goods",
    # ── Automobiles ───────────────────────────────────────────────────────────
    "MARUTI":      "Automobiles",    "TATAMOTORS":  "Automobiles",
    "BAJAJ-AUTO":  "Automobiles",    "EICHERMOT":   "Automobiles",
    "HEROMOTOCO":  "Automobiles",    "BOSCHLTD":    "Automobiles",
    "BALKRISIND":  "Automobiles",    "MRF":         "Automobiles",
    "ESCORTS":     "Automobiles",    "TIINDIA":     "Automobiles",
    "OLAELEC":     "Automobiles",    "ATHERENERG":  "Automobiles",
    "APOLLOTYRE":  "Automobiles",    "CEATLTD":     "Automobiles",
    "SMLMAH":      "Automobiles",    "MINDACORP":   "Automobiles",
    "BALUFORGE":   "Automobiles",    "MUNJALAU":    "Automobiles",
    "JKTYRE":      "Automobiles",    "TMCV":        "Automobiles",
    "ZFCVINDIA":   "Automobiles",    "ENDURANCE":   "Automobiles",
    "WHEELS":      "Automobiles",    "JTEKTINDIA":  "Automobiles",
    "FIEMIND":     "Automobiles",    "GABRIEL":     "Automobiles",
    "SANDHAR":     "Automobiles",    "SHRIPISTON":  "Automobiles",
    "JAMNAAUTO":   "Automobiles",    "RICOAUTO":    "Automobiles",
    "SUBROS":      "Automobiles",    "SUPRAJIT":    "Automobiles",
    "LUMAXTECH":   "Automobiles",    "SANSERA":     "Automobiles",
    "LUMAX":       "Automobiles",    "PRICOLLTD":   "Automobiles",
    "CIEINDIA":    "Automobiles",    "SUNDRMFAST":  "Automobiles",
    "MINDAIND":    "Automobiles",    "SHRIRAMFIN":  "Financial Services",
    # ── Pharmaceuticals ───────────────────────────────────────────────────────
    "SUNPHARMA":   "Pharmaceuticals", "CIPLA":      "Pharmaceuticals",
    "DRREDDY":     "Pharmaceuticals", "DIVISLAB":   "Pharmaceuticals",
    "LUPIN":       "Pharmaceuticals", "BIOCON":     "Pharmaceuticals",
    "AUROPHARMA":  "Pharmaceuticals", "GLENMARK":   "Pharmaceuticals",
    "ALKEM":       "Pharmaceuticals", "ZYDUSLIFE":  "Pharmaceuticals",
    "TORNTPHARM":  "Pharmaceuticals", "GRANULES":   "Pharmaceuticals",
    "LAURUSLABS":  "Pharmaceuticals", "SUVEN":      "Pharmaceuticals",
    "JBCHEPHARM":  "Pharmaceuticals", "SEQUENT":    "Pharmaceuticals",
    "AJANTPHARM":  "Pharmaceuticals", "IPCA":       "Pharmaceuticals",
    "STRIDES":     "Pharmaceuticals", "SOLARA":     "Pharmaceuticals",
    "MARKSANS":    "Pharmaceuticals", "NEULANDLAB":  "Pharmaceuticals",
    "NEULAND":     "Pharmaceuticals", "EMCURE":     "Pharmaceuticals",
    "PANACEABIO":  "Pharmaceuticals", "ORCHPHARMA": "Pharmaceuticals",
    "INDSWFTLAB":  "Pharmaceuticals", "AARTIPHARM": "Pharmaceuticals",
    "SUDEEPPHRM":  "Pharmaceuticals", "PGHL":       "Pharmaceuticals",
    "GLAXO":       "Pharmaceuticals", "SANOFI":     "Pharmaceuticals",
    "NOVARTIND":   "Pharmaceuticals", "ERIS":       "Pharmaceuticals",
    "FDC":         "Pharmaceuticals", "HESTERBIO":  "Pharmaceuticals",
    "BLUEJET":     "Pharmaceuticals", "CONCORDBIO": "Pharmaceuticals",
    "VIMTALABS":   "Pharmaceuticals", "ZOTA":       "Pharmaceuticals",
    "AKUMS":       "Pharmaceuticals", "SUPRIYA":    "Pharmaceuticals",
    "ALIVUS":      "Pharmaceuticals", "BAYERCORP":  "Pharmaceuticals",
    "IPCALAB":     "Pharmaceuticals", "SANOFICONR": "Pharmaceuticals",
    "LAURUS":      "Pharmaceuticals", "INDOCO":     "Pharmaceuticals",
    "PGIL":        "Pharmaceuticals",
    # ── Healthcare ────────────────────────────────────────────────────────────
    "APOLLOHOSP":  "Healthcare", "MAXHEALTH":   "Healthcare",
    "FORTIS":      "Healthcare", "METROPOLIS":  "Healthcare",
    "THYROCARE":   "Healthcare", "HCG":         "Healthcare",
    "PARKHOSPS":   "Healthcare", "YATHARTH":    "Healthcare",
    "DENTA":       "Healthcare", "KIMS":        "Healthcare",
    "SHALBY":      "Healthcare", "RAINBOW":     "Healthcare",
    "MEDIASSIST":  "Healthcare", "KRSNAA":      "Healthcare",
    "VIJAYADIAG":  "Healthcare", "ASTER":       "Healthcare",
    "HEALTHCARE":  "Healthcare", "NEPHROPLUS":  "Healthcare",
    "THYROCARE":   "Healthcare", "AARTIPHARMA": "Healthcare",
    "INDIAMART":   "Information Technology",
    # ── FMCG ─────────────────────────────────────────────────────────────────
    "HINDUNILVR":  "FMCG", "ITC":         "FMCG", "BRITANNIA":   "FMCG",
    "NESTLEIND":   "FMCG", "DABUR":       "FMCG", "GODREJCP":    "FMCG",
    "COLPAL":      "FMCG", "TATACONSUM":  "FMCG", "MARICO":      "FMCG",
    "EMAMI":       "FMCG", "JYOTHYLAB":   "FMCG", "RELAXO":      "FMCG",
    "BATA":        "FMCG", "RAYMOND":     "FMCG", "SANSTAR":     "FMCG",
    "BALRAMCHIN":  "FMCG", "RENUKA":      "FMCG", "TRIVENI":     "FMCG",
    "KRBL":        "FMCG", "ZYDUSWELL":   "FMCG", "HERITGFOOD":  "FMCG",
    "LTFOODS":     "FMCG", "VSTIND":      "FMCG", "GODFRYPHLP":  "FMCG",
    "JYOTHYLAB":   "FMCG", "CCL":         "FMCG", "MOREPENLAB":  "FMCG",
    "EVEREADY":    "FMCG", "GILLETTE":    "FMCG", "PGHHH":       "FMCG",
    "PGHH":        "FMCG", "BAJAJCON":    "FMCG", "PATANJALI":   "FMCG",
    "VADILALIND":  "FMCG", "DEVYANI":     "FMCG",
    # ── Metals & Mining ───────────────────────────────────────────────────────
    "TATASTEEL":   "Metals & Mining", "JSWSTEEL":   "Metals & Mining",
    "HINDALCO":    "Metals & Mining", "COALINDIA":  "Metals & Mining",
    "SAIL":        "Metals & Mining", "NMDC":       "Metals & Mining",
    "NATIONALUM":  "Metals & Mining", "VEDL":       "Metals & Mining",
    "HINDZINC":    "Metals & Mining", "MOIL":       "Metals & Mining",
    "GPIL":        "Metals & Mining", "JSWISPL":    "Metals & Mining",
    "RATNAMANI":   "Metals & Mining", "JINDALSAW":  "Metals & Mining",
    "WELCORP":     "Metals & Mining", "ELECTCAST":  "Metals & Mining",
    "GRAPHITE":    "Metals & Mining", "HEG":        "Metals & Mining",
    "IMFA":        "Metals & Mining", "STEELCAS":   "Metals & Mining",
    "SHYAMMETL":   "Metals & Mining", "NELCAST":    "Metals & Mining",
    "WELSPUNSP":   "Metals & Mining", "JSHL":       "Metals & Mining",
    "NSLNISP":     "Metals & Mining",
    # ── Energy ────────────────────────────────────────────────────────────────
    "RELIANCE":    "Energy", "ONGC":       "Energy", "NTPC":        "Energy",
    "POWERGRID":   "Energy", "ADANIGREEN": "Energy", "ADANITRANS":  "Energy",
    "ADANIPOWER":  "Energy", "TATAPOWER":  "Energy", "WAAREEENER":  "Energy",
    "INOXWIND":    "Energy", "SUZLON":     "Energy", "NHPC":        "Energy",
    "SJVN":        "Energy", "IREDA":      "Energy", "RECLTD":      "Energy",
    "PFC":         "Energy", "KPIGREEN":   "Energy", "INOXGREEN":   "Energy",
    "WAAREERTL":   "Energy", "WEBELSOLAR": "Energy", "GKENERGY":    "Energy",
    "RTNPOWER":    "Energy", "ASIANENE":   "Energy", "PTC":         "Energy",
    "CMRGREEN":    "Energy", "CMPDI":      "Energy", "SARDAEN":     "Energy",
    "HINDOILEXP":  "Energy", "HINDOILEXP": "Energy",
    # ── Oil & Gas ─────────────────────────────────────────────────────────────
    "BPCL":        "Oil & Gas", "GAIL":    "Oil & Gas", "DEEPAKFERT": "Oil & Gas",
    "CHAMBAL":     "Oil & Gas", "HPCL":    "Oil & Gas", "IOC":        "Oil & Gas",
    "MRPL":        "Oil & Gas", "CASTROL": "Oil & Gas", "GULFOILLUB": "Oil & Gas",
    "PANAMAPET":   "Oil & Gas",
    # ── Chemicals ─────────────────────────────────────────────────────────────
    "PIDILITE":    "Chemicals", "DEEPAKNTR": "Chemicals", "PIIND":    "Chemicals",
    "AARTIIND":    "Chemicals", "FINEORG":   "Chemicals", "SUDARSCHEM": "Chemicals",
    "NOCIL":       "Chemicals", "ATUL":      "Chemicals", "TATVA":    "Chemicals",
    "CLEAN":       "Chemicals", "INDIAGLYCO": "Chemicals", "GHCL":   "Chemicals",
    "AETHER":      "Chemicals", "FLUOROCHEM": "Chemicals", "BALAMINES": "Chemicals",
    "VINATIORGA":  "Chemicals", "TATACHEM":  "Chemicals", "CAMLINFINE": "Chemicals",
    "HIKAL":       "Chemicals", "KIRIINDUS": "Chemicals", "GNFC":    "Chemicals",
    "GSFC":        "Chemicals", "LXCHEM":    "Chemicals", "YASHO":   "Chemicals",
    "FAIRCHEMOR":  "Chemicals", "GAEL":      "Chemicals", "INDOBORAX": "Chemicals",
    "EPIGRAL":     "Chemicals", "NARMADA":   "Chemicals", "AARTIPHARM": "Chemicals",
    "GUJALKALI":   "Chemicals", "VINDHYATEL": "Telecom",
    # ── Agriculture ───────────────────────────────────────────────────────────
    "CHAMBLFERT":  "Agriculture", "RCF":     "Agriculture", "NFL":    "Agriculture",
    "DHANUKA":     "Agriculture", "RALLIS":  "Agriculture", "PARADEEP": "Agriculture",
    "KSCL":        "Agriculture", "PRAJIND": "Agriculture", "COROMANDEL": "Agriculture",
    "SHARDACROP":  "Agriculture", "EIDPARRY": "Agriculture", "FACT":  "Agriculture",
    "GUJAMBCORP":  "Agriculture", "BALRAMCHIN": "Agriculture",
    # ── Cement ────────────────────────────────────────────────────────────────
    "ULTRACEMCO":  "Cement", "SHREECEM":  "Cement", "AMBUJACEM":   "Cement",
    "GRASIM":      "Cement", "JKCEMENT":  "Cement", "RAMCOCEM":    "Cement",
    "HEIDELBERG":  "Cement", "BIRLACORPN": "Cement", "NUVOCO":     "Cement",
    "ORIENTCEM":   "Cement", "STARCEMENT": "Cement", "CERA":       "Cement",
    "KCP":         "Cement", "ACC":        "Cement", "MANGLMCEM":  "Cement",
    "INDIACEM":    "Cement", "SAGCEM":     "Cement", "JKPAPER":    "Cement",
    "KAJARIACER":  "Cement", "SOMANYCERA": "Cement",
    # ── Real Estate ───────────────────────────────────────────────────────────
    "DLF":         "Real Estate", "GODREJPROP":  "Real Estate",
    "OBEROIRLTY":  "Real Estate", "PRESTIGE":    "Real Estate",
    "SOBHA":       "Real Estate", "BRIGADE":     "Real Estate",
    "MAHINDRACIE": "Real Estate", "KOLTEPATIL":  "Real Estate",
    "SUNTECK":     "Real Estate", "AJMERA":      "Real Estate",
    "ATALREAL":    "Real Estate", "GODREJIND":   "Real Estate",
    "GODAVARIB":   "Real Estate", "JUBLINGREA":  "Real Estate",
    "MAXESTATES":  "Real Estate", "SPAL":        "Real Estate",
    "PURVA":       "Real Estate", "ASHIANA":     "Real Estate",
    # ── Hotels & Hospitality ─────────────────────────────────────────────────
    "INDHOTEL":    "Consumer Durables", "THELEELA":   "Consumer Durables",
    "CHALET":      "Consumer Durables", "SAMHI":      "Consumer Durables",
    "TAJGVK":      "Consumer Durables", "MHRIL":      "Consumer Durables",
    "PARKHOTELS":  "Consumer Durables", "ADVENTHTL":  "Consumer Durables",
    "THOMASCOOK":  "Consumer Durables", "EASEMYTRIP": "Consumer Durables",
    # ── Consumer Durables / Retail ────────────────────────────────────────────
    "TITAN":       "Consumer Durables", "MEESHO":     "Consumer Durables",
    "FIRSTCRY":    "Consumer Durables", "LENSKART":   "Consumer Durables",
    "NYKAA":       "Consumer Durables", "VMART":      "Consumer Durables",
    "SWIGGY":      "Consumer Durables", "SHOPERSTOP": "Consumer Durables",
    "METROBRAND":  "Consumer Durables", "SENCO":      "Consumer Durables",
    "BLUESTONE":   "Consumer Durables", "THANGAMAYL": "Consumer Durables",
    "KALYAN":      "Consumer Durables", "PCJEWELLER": "Consumer Durables",
    "GOLDIAM":     "Consumer Durables", "DPABHUSHAN": "Consumer Durables",
    "MOTISONS":    "Consumer Durables", "V2RETAIL":   "Consumer Durables",
    "SAFARI":      "Consumer Durables", "CELLO":      "Consumer Durables",
    "NILKAMAL":    "Consumer Durables", "KALAMANDIR": "Consumer Durables",
    "DOMS":        "Consumer Durables", "DOLLR":      "Consumer Durables",
    "EVEREADY":    "Consumer Durables", "NITCO":      "Consumer Durables",
    "DMART":       "Consumer Durables", "NYKAA":      "Consumer Durables",
    "TRENT":       "Consumer Durables", "VSTIND":     "Consumer Durables",
    "DOLLAR":      "Consumer Durables", "RUPA":       "Textiles",
    # ── Textiles ─────────────────────────────────────────────────────────────
    "KPRMILL":     "Textiles", "WELSPUNLIV": "Textiles", "HIMATSEIDE":  "Textiles",
    "SANGAMIND":   "Textiles", "AMBIKCO":    "Textiles", "SPORTKING":   "Textiles",
    "ICIL":        "Textiles", "GHCLTEXTIL": "Textiles", "ARVINDFASN":  "Textiles",
    "NITIN":       "Textiles", "VARDHMAN":   "Textiles", "TRIDENT":     "Textiles",
    "ABFRL":       "Textiles", "RAYMOND":    "Textiles", "PAGEIND":     "Consumer Durables",
    "NITINSPIN":   "Textiles", "SSWL":       "Textiles",
    # ── Defence ───────────────────────────────────────────────────────────────
    "HAL":         "Defence",  "BEL":        "Defence",  "BEML":       "Defence",
    "COCHINSHIP":  "Defence",  "GRSE":       "Defence",  "MTAR":       "Defence",
    "IDEAFORGE":   "Defence",  "PARAS":      "Defence",  "BDL":        "Defence",
    "MAZDOCK":     "Defence",  "MIDHANI":    "Defence",  "MODEFENCE":  "Defence",
    "KRISHNADEF":  "Defence",  "DCXINDIA":   "Defence",
    # ── Media & Entertainment ─────────────────────────────────────────────────
    "ZEEL":        "Media & Entertainment", "SUNTV":      "Media & Entertainment",
    "TIPSINDLTD":  "Media & Entertainment", "TIPSFILMS":  "Media & Entertainment",
    "PVRINOX":     "Media & Entertainment", "DEN":        "Media & Entertainment",
    "TVTODAY":     "Media & Entertainment", "HMVL":       "Media & Entertainment",
    "NDTV":        "Media & Entertainment", "NAZARA":     "Media & Entertainment",
    "ROUTE":       "Media & Entertainment",
    # ── PSU Banks (sub-sector of Banking) ────────────────────────────────────
    "UCOBANK":     "Banking",  "IOB":        "Banking",
    # ── Banking — additional ─────────────────────────────────────────────────
    "J&KBANK":     "Banking",  "CUB":        "Banking",  "KTKBANK":    "Banking",
    # ── Financial Services — additional ──────────────────────────────────────
    "RELIGARE":    "Financial Services", "EDELWEISS":  "Financial Services",
    "PIRAMALFIN":  "Financial Services", "NUVAMA":     "Financial Services",
    "ABSLAMC":     "Financial Services", "ANANDRATHI": "Financial Services",
    "BAJAJHLDNG":  "Financial Services", "TFCILTD":    "Financial Services",
    "CARERATING":  "Financial Services", "GICRE":      "Financial Services",
    "NAM-INDIA":   "Financial Services", "MOTILALOFS": "Financial Services",
    "ICICIAMC":    "Financial Services", "ZAGGLE":     "Financial Services",
    "KISSHT":      "Financial Services", "SAMMAANCAP": "Financial Services",
    "ICRA":        "Financial Services", "SGFIN":      "Financial Services",
    "ANANDRATHI":  "Financial Services", "CENTRUM":    "Financial Services",
    "ASHIKA":      "Financial Services", "MMTC":       "Financial Services",
    "CANHLIFE":    "Financial Services", "NIVABUPA":   "Financial Services",
    "GODIGIT":     "Financial Services",
    # ── Information Technology — additional ──────────────────────────────────
    "REDINGTON":   "Information Technology", "TATATECH":   "Information Technology",
    "CARTRADE":    "Information Technology", "E2E":        "Information Technology",
    "DLINKINDIA":  "Information Technology", "MCLOUD":     "Information Technology",
    "OPTIEMUS":    "Information Technology", "ZENTEC":     "Information Technology",
    "ALGOQUANT":   "Information Technology", "VERANDA":    "Information Technology",
    "ONESOURCE":   "Information Technology", "INDGN":      "Information Technology",
    "DSSL":        "Information Technology",
    # ── Capital Goods — additional ────────────────────────────────────────────
    "MTARTECH":    "Capital Goods",  "SOLARINDS":  "Capital Goods",
    "RRKABEL":     "Capital Goods",  "TIMETECHNO": "Capital Goods",
    "SCHNEIDER":   "Capital Goods",  "VOLTAMP":    "Capital Goods",
    "TITAGARH":    "Capital Goods",  "AEROFLEX":   "Capital Goods",
    "KIRLOSBROS":  "Capital Goods",  "KPIL":       "Capital Goods",
    "ARE&M":       "Capital Goods",  "ENGINERSIN": "Capital Goods",
    "SUPREMEIND":  "Capital Goods",  "WALCHANNAG": "Capital Goods",
    "FINCABLES":   "Capital Goods",  "STERTOOLS":  "Capital Goods",
    "UNIVCABLES":  "Capital Goods",  "JAYNECOIND": "Capital Goods",
    "HONAUT":      "Capital Goods",  "AIAENG":     "Capital Goods",
    "DIACABS":     "Capital Goods",  "PARACABLES": "Capital Goods",
    "PRECWIRE":    "Capital Goods",  "VIDYAWIRES": "Capital Goods",
    "SHAILY":      "Capital Goods",  "EIEL":       "Capital Goods",
    "EXICOM":      "Capital Goods",  "POWERICA":   "Capital Goods",
    "NRBBEARING":  "Capital Goods",  "SEDEMAC":    "Capital Goods",
    "EMSLIMITED":  "Capital Goods",  "LLOYDSENGG": "Capital Goods",
    "CRAFTSMAN":   "Capital Goods",  "RATNAVEER":  "Capital Goods",
    "SUNFLAG":     "Metals & Mining", "MAITHANALL": "Metals & Mining",
    "GMDCLTD":     "Metals & Mining", "NACLIND":   "Capital Goods",
    "SUPREMEIND":  "Capital Goods",  "INA":        "Capital Goods",
    "TARIL":       "Capital Goods",  "VOLTAMP":    "Capital Goods",
    "HBLENGINE":   "Capital Goods",  "VASINFRA":   "Infrastructure",
    "VMFINANCE":   "Financial Services", "KDDL":   "Consumer Durables",
    "FLAIR":       "Consumer Durables",
    # ── Automobiles — additional ──────────────────────────────────────────────
    "HYUNDAI":     "Automobiles",    "FORCEMOT":   "Automobiles",
    "OLECTRA":     "Automobiles",    "BELRISE":    "Automobiles",
    "GREAVESCOT":  "Automobiles",    "TALBROAUTO": "Automobiles",
    "JBMA":        "Automobiles",    "LUMAXIND":   "Automobiles",
    "SETL":        "Automobiles",    "SEPC":       "Automobiles",
    # ── Chemicals — additional ────────────────────────────────────────────────
    "NAVINFLUOR":  "Chemicals",  "PCBL":       "Chemicals",
    "SRF":         "Chemicals",  "SUMICHEM":   "Chemicals",
    "IOLCP":       "Chemicals",  "RAIN":       "Chemicals",
    "ROSSARI":     "Chemicals",  "ALKYLAMINE": "Chemicals",
    "GARFIBRES":   "Chemicals",  "TIRUMALCHM": "Chemicals",
    "BEPL":        "Chemicals",  "DCW":        "Chemicals",
    "COSMOFIRST":  "Chemicals",  "IONEXCHANG": "Chemicals",
    "WABAG":       "Chemicals",  "ROSSTECH":   "Chemicals",
    "AARTIDRUGS":  "Chemicals",  "JUBLPHARMA": "Pharmaceuticals",
    "THEMISMED":   "Pharmaceuticals", "NATCOPHARM": "Pharmaceuticals",
    "CAPLIPOINT":  "Pharmaceuticals", "BLISSGVS":  "Pharmaceuticals",
    "SPARC":       "Pharmaceuticals", "PFIZER":    "Pharmaceuticals",
    "WANBURY":     "Pharmaceuticals",
    # ── Healthcare — additional ───────────────────────────────────────────────
    "MEDANTA":     "Healthcare",  "NH":         "Healthcare",
    "ASTERDM":     "Healthcare",  "SAGILITY":   "Healthcare",
    "ENTERO":      "Healthcare",  "SHILPAMED":  "Healthcare",
    "POLYMED":     "Healthcare",  "AGIIL":      "Healthcare",
    # ── Infrastructure — additional ───────────────────────────────────────────
    "HCC":         "Infrastructure", "NBCC":      "Infrastructure",
    "MANINFRA":    "Infrastructure", "AFCONS":    "Infrastructure",
    "NAVKARCORP":  "Infrastructure", "RITES":     "Infrastructure",
    "SHADOWFAX":   "Infrastructure", "MARINE":    "Infrastructure",
    "GARUDA":      "Infrastructure", "AEQUS":     "Infrastructure",
    "AZAD":        "Infrastructure", "SALASAR":   "Infrastructure",
    # ── Energy — additional ───────────────────────────────────────────────────
    "CLEANMAX":    "Energy",     "SWSOLAR":    "Energy",
    "ACMESOLAR":   "Energy",     "EMMVEE":     "Energy",
    "PREMIERENE":  "Energy",     "CONFIPET":   "Oil & Gas",
    "GUJGASLTD":   "Oil & Gas",  "RTNINDIA":   "Energy",
    "SERVOTECH":   "Energy",     "PWL":        "Energy",
    "QUADFUTURE":  "Energy",     "INOXINDIA":  "Capital Goods",
    "UTLSOLAR":    "Energy",
    # ── Oil & Gas — additional ────────────────────────────────────────────────
    "UPL":         "Agriculture", "SUMICHEM":  "Chemicals",
    # ── Agriculture — additional ──────────────────────────────────────────────
    "NACLIND":     "Agriculture",
    # ── Cement — additional ───────────────────────────────────────────────────
    "JSWCEMENT":   "Cement",     "DALBHARAT":  "Cement",
    "JKLAKSHMI":   "Cement",     "CEMPRO":     "Cement",
    # ── Real Estate — additional ──────────────────────────────────────────────
    "HUBTOWN":     "Real Estate", "NESCO":     "Real Estate",
    # ── Hotels / Hospitality ─────────────────────────────────────────────────
    "ORIENTHOT":   "Consumer Durables", "LEMONTREE":  "Consumer Durables",
    "KAMATHOTEL":  "Consumer Durables", "ITCHOTELS":  "Consumer Durables",
    "IMAGICAA":    "Consumer Durables", "MEDPLUS":    "Consumer Durables",
    "WAKEFIT":     "Consumer Durables", "GOCOLORS":   "Consumer Durables",
    "LUXIND":      "Consumer Durables", "PARAGLIDE":  "Consumer Durables",
    # ── Textiles — additional ─────────────────────────────────────────────────
    "KITEX":       "Textiles",   "ARVIND":     "Textiles",
    "BOMDYEING":   "Textiles",   "NITCO":      "Consumer Durables",
    # ── Media & Entertainment — additional ───────────────────────────────────
    "DELTACORP":   "Media & Entertainment", "STAR":  "Media & Entertainment",
    "BBOX":        "Media & Entertainment", "ADSL":  "Media & Entertainment",
    # ── Defence — additional ──────────────────────────────────────────────────
    "ASTRAMICRO":  "Defence",   "KERNEX":     "Defence",
    "COCKERILL":   "Defence",
    "TVTODAY":     "Media & Entertainment", "NDTV": "Media & Entertainment",
    # ── Final batch — identified from live bhavcopy ───────────────────────────
    # FMCG
    "AWL":         "FMCG",          "HONASA":      "FMCG",
    "SKMEGGPROD":  "FMCG",          "PARAGMILK":   "FMCG",
    "AMRUTANJAN":  "FMCG",          "BECTORFOOD":  "FMCG",
    "PIDILITIND":  "Chemicals",
    # Banking
    "SUNDARMFIN":  "Financial Services",
    # Financial Services
    "INDOTHAI":    "Financial Services", "CCAVENUE":   "Financial Services",
    "MSTCLTD":     "Financial Services", "PTCIL":      "Energy",
    "SWANCORP":    "Energy",
    # Information Technology
    "FSL":         "Information Technology", "NELCO":   "Information Technology",
    "AMAGI":       "Information Technology", "BLS":     "Information Technology",
    "CPPLUS":      "Capital Goods",
    # Healthcare
    "CUPID":       "Healthcare",     "IKS":         "Healthcare",
    "VIJAYA":      "Healthcare",     "SAILIFE":     "Pharmaceuticals",
    "CORONA":      "Pharmaceuticals",
    # Automobiles
    "APOLLO":      "Automobiles",    "MSUMI":       "Automobiles",
    # Textiles
    "GOKEX":       "Textiles",       "VTL":         "Textiles",
    "POKARNA":     "Consumer Durables",
    # Metals & Mining
    "MANINDS":     "Metals & Mining", "JSLL":       "Metals & Mining",
    # Capital Goods
    "OSWALPUMPS":  "Capital Goods",  "NIBE":        "Capital Goods",
    "JNKINDIA":    "Capital Goods",  "FINPIPE":     "Capital Goods",
    "TEGA":        "Capital Goods",  "JASH":        "Capital Goods",
    # Energy
    "BORORENEW":   "Energy",         "REFEX":       "Energy",
    # Real Estate
    "HSCL":        "Consumer Durables", "RAYMONDREL": "Real Estate",
    # Chemicals
    "POLYPLEX":    "Chemicals",      "FCL":         "Chemicals",
    "ROSSTECH":    "Chemicals",
    # ── Batch 1 — user-curated ────────────────────────────────────────────────
    # Pharmaceuticals / Healthcare
    "COHANCE":     "Pharmaceuticals", "VIYASH":     "Pharmaceuticals",
    "SENORES":     "Pharmaceuticals", "ANTHEM":     "Pharmaceuticals",
    "SAKAR":       "Pharmaceuticals",
    # Energy
    "BHARATCOAL":  "Energy",
    # Chemicals
    "KRISHANA":    "Chemicals",       "ANURAS":     "Chemicals",
    "GRWRHITECH":  "Chemicals",
    # FMCG
    "RBA":         "FMCG",           "UFBL":       "FMCG",
    "MANORAMA":    "FMCG",
    # Capital Goods
    "VMM":         "Capital Goods",  "JWL":        "Capital Goods",
    "SKIPPER":     "Capital Goods",
    # Infrastructure
    "SHREEJISPG":  "Infrastructure", "KMEW":       "Infrastructure",
    "DREDGECORP":  "Infrastructure",
    # Defence
    "PREMEXPLN":   "Defence",        "SHRINGARMS":  "Defence",
    # Textiles
    "SBC":         "Textiles",       "PDSL":       "Textiles",
    "VINCOFE":     "Textiles",
    # Consumer Durables
    "TIMEX":       "Consumer Durables",
    # Metals & Mining
    "JAINREC":     "Metals & Mining",
}


@lru_cache(maxsize=1)
def _stock_sector_map() -> dict[str, str]:
    """Return {bare_symbol: canonical_sector} from 3 layered sources.

    Priority (first assignment wins):
      1. _EXTRA_SECTOR_MAP  — explicitly curated map, highest authority
      2. SECTOR_SYMBOLS     — live NSE index constituents (fills anything not in Extra)
      3. SUBSECTOR_TAXONOMY — broad sub-industry taxonomy, fills remaining gaps
    """
    out: dict[str, str] = {}

    # ── Layer 1: explicitly curated map (highest priority) ───────────────────
    out.update(_EXTRA_SECTOR_MAP)

    # ── Layer 2: live SECTOR_SYMBOLS ─────────────────────────────────────────
    try:
        from ..lib.universe import SECTOR_SYMBOLS as _SS  # type: ignore
        for index_name, syms in _SS.items():
            if index_name in _INDEX_SKIP:
                continue
            sector = _RAW_TO_SECTOR.get(index_name.lower())
            if not sector:
                continue
            for sym in syms:
                bare = sym.replace(".NS", "").replace(".BO", "")
                if bare not in out:
                    out[bare] = sector
    except Exception:
        pass

    # ── Layer 3: SUBSECTOR_TAXONOMY (hardcoded sub-industry seed) ────────────
    try:
        from ..lib.universe import SUBSECTOR_TAXONOMY as _ST  # type: ignore
        for _grp, data in _ST.items():
            sector = data.get("sector") or ""
            canonical = _RAW_TO_SECTOR.get(sector.lower(), sector)
            for sym in data.get("symbols", []):
                bare = sym.replace(".NS", "").replace(".BO", "")
                if bare not in out and canonical:
                    out[bare] = canonical
    except Exception:
        pass

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


def get_sector_symbols(sector: str) -> list[str]:
    """Return every symbol that belongs to *sector* from the centralized map.

    Accepts both NSE index names ("NIFTY IT", "NIFTY PHARMA") and canonical
    sector names ("Information Technology", "Pharmaceuticals").  The lookup
    normalises via _RAW_TO_SECTOR so both spellings work identically.

    This is the single authoritative query used by:
      • The delivery drawer (label enrichment)
      • sector_rotation_service.shortlist() — sector path
      • Any future consumer that needs "who is in this sector?"
    """
    canonical = _RAW_TO_SECTOR.get(sector.lower(), sector)
    return [sym for sym, sec in _stock_sector_map().items() if sec == canonical]


def get_subsector_symbols(sub_industry: str) -> list[str]:
    """Return every symbol tagged to *sub_industry* in _EXTRA_SUBSECTOR_MAP.

    The sub_industry string must match what is stored in the stocks DB /
    SUBSECTOR_TAXONOMY (e.g. "CDMO / CRAMS", "Software Products").
    Returns an empty list when no curated entries exist yet.

    Used by sector_rotation_service.shortlist() — sub-industry path — to
    surface curated mid/small-caps that Yahoo Finance did not classify.
    """
    return [sym for sym, si in _EXTRA_SUBSECTOR_MAP.items() if si == sub_industry]


def get_all_extra_sectors() -> list[str]:
    """Return the sorted unique set of canonical sector names present in
    _EXTRA_SECTOR_MAP.  Used by sector_rotation_service to auto-inject
    curated sectors into the cockpit leaderboard even when no NSE Yahoo
    ticker exists for them."""
    return sorted(set(_EXTRA_SECTOR_MAP.values()))


def get_all_extra_subsectors() -> list[str]:
    """Return the sorted unique set of sub-industry names present in
    _EXTRA_SUBSECTOR_MAP.  Used by sector_rotation_service to auto-inject
    curated sub-industries into the cockpit leaderboard even before the
    synthetic-index DB has built enough history for an RRG entry."""
    return sorted(set(_EXTRA_SUBSECTOR_MAP.values()))


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
