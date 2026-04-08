"""
Centralised NSE stock universe.
  NIFTY100   — Nifty 100 large-caps
  MIDCAP     — Nifty Midcap 150 representative set
  SMALLCAP   — Nifty Smallcap 250 representative set
  MICROCAP   — Popular micro-cap / emerging NSE stocks
  ALL_SYMBOLS — Deduplicated union of all four lists
  SECTOR_SYMBOLS — Canonical sector → constituent mapping
"""

# ── Large Cap (Nifty 100) ─────────────────────────────────────────────────────
NIFTY100 = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC", "SBIN",
    "BHARTIARTL", "KOTAKBANK", "BAJFINANCE", "AXISBANK", "ASIANPAINT", "MARUTI", "HCLTECH",
    "WIPRO", "TITAN", "NTPC", "SUNPHARMA", "TATAMOTORS", "LT", "COALINDIA", "BAJAJ-AUTO",
    "DIVISLAB", "CIPLA", "DRREDDY", "TECHM", "HINDALCO", "ONGC", "POWERGRID",
    "JSWSTEEL", "INDUSINDBK", "ULTRACEMCO", "NESTLEIND", "TATACONSUM", "ADANIPORTS",
    "SBILIFE", "BRITANNIA", "APOLLOHOSP", "BPCL", "TATASTEEL", "ADANIENT",
    "EICHERMOT", "HEROMOTOCO", "GRASIM", "HAVELLS", "SHREECEM", "HDFCLIFE",
    "DABUR", "PIDILITE", "BAJAJFINSV", "SIEMENS", "DLF", "TRENT", "LUPIN",
    "BIOCON", "GAIL", "COLPAL", "MUTHOOTFIN", "BERGEPAINT", "GODREJCP", "BOSCHLTD",
    "ABB", "BANKBARODA", "PNB", "CANBK", "FEDERALBNK", "IDFCFIRSTB",
    "BANDHANBNK", "RBLBANK", "YESBANK", "PERSISTENT", "COFORGE", "MPHASIS",
    "LTTS", "KPITTECH", "TATAELXSI", "CYIENT", "IRCTC", "ZOMATO",
    "LICI", "ADANIGREEN", "ADANITRANS", "ADANIPOWER", "DMART", "NYKAA",
    "PAYTM", "POLICYBZR", "MARICO", "PIDILITE", "MAXHEALTH", "FORTIS",
    "VOLTAS", "CONCOR", "CHOLAFIN", "GODREJPROP", "OBEROIRLTY", "PRESTIGE",
]

# ── Mid Cap (Nifty Midcap 150 representative) ─────────────────────────────────
MIDCAP = [
    "AUROPHARMA", "BALKRISIND", "PAGEIND", "TORNTPHARM", "PIIND", "LTFH",
    "MRF", "POLYCAB", "AMBUJACEM", "GLENMARK", "ESCORTS", "ZYDUSLIFE",
    "ALKEM", "EMAMI", "JYOTHYLAB", "NATIONALUM", "SUZLON", "NHPC",
    "SJVN", "RVNL", "IRCON", "TIINDIA", "MCDOWELL-N", "RADICO",
    "JUBLFOOD", "DEVYANI", "WESTLIFE", "CRISIL", "ICICIPRULI",
    "CANFINHOME", "MANAPPURAM", "SHRIRAMFIN", "ABFRL", "RELAXO",
    "BATA", "RAYMOND", "VGUARD", "KANSAINER", "AKZOINDIA", "BLUESTARCO",
    "KAJARIACER", "SUNDARMFIN", "CHOLAFIN", "MFSL", "LINDEINDIA",
    "SOLARINDS", "WHIRLPOOL", "MAXHEALTH", "METROPOLIS", "IEX",
    "CAMS", "CDSL", "NAUKRI", "ASTRAL", "DEEPAKNTR", "CROMPTON",
    "HAPPSTMNDS", "AAVAS", "HFCL", "OLECTRA",
    "APTUS", "HOMEFIRST", "CREDITACC", "ARMANFIN", "SPANDANA",
    "UJJIVANSFB", "EQUITASBNK", "KARURVYSYA", "DCBBANK", "SOUTHBANK",
    "CSBBANK", "NUVOCO", "HEIDELBERG", "BIRLACORPN", "ORIENTCEM",
    "STARCEMENT", "JKCEMENT", "RAMCOCEM", "GPIL", "NMDC",
    "SAIL", "WELSPUNLIV", "TRIDENT", "VARDHMAN", "BALRAMCHIN",
    "RENUKA", "TRIVENI", "DHANUKA", "RALLIS", "PRAJIND",
    "GRANULES", "LAURUSLABS", "SUVEN", "JBCHEPHARM", "SEQUENT",
    "KALYAN", "SENCO", "IIFL", "360ONE", "ANANDRAT",
    "AMBER", "DIXON", "DIXONS", "SAFARI", "VMART",
    "TATACOMM", "TANLA", "ROUTE", "NAZARA", "LATENTVIEW",
    "MASTEK", "BIRLASOFT", "INFOEDGE", "XCHANGING",
    "APARINDS", "ELGIEQUIP", "PNCINFRA", "KPRMILL",
    "GREENPANEL", "CENTURYPLY", "APLAPOLLO",
    "INDOSTAR", "PCJEWELLER", "THANGAMAYL",
    "WAAREEENER", "INOXWIND", "PREMIER",
    "TIPSINDLTD", "JUBLINGREA", "SAPPHIRE",
]

# ── Small Cap (Nifty Smallcap 250 representative) ─────────────────────────────
SMALLCAP = [
    "HAPPYFORGE", "RATNAMANI", "HBLPOWER", "AARTIIND", "FINEORG",
    "SUDARSCHEM", "VINDHYATEL", "RAILTEL", "IREDA", "RECLTD",
    "PFC", "HUDCO", "IRFC", "MSTCLTD", "MMTC",
    "NATIONALUM", "HINDZINC", "VEDL", "MOIL", "GMRINFRA",
    "IRB", "ASHOKA", "SAMEERA", "CAPACITE", "PEPL",
    "TDPOWERSYS", "JSWISPL", "KCP", "INDIAGLYCO", "EIDPARRY",
    "RUPA", "DOLLAR", "GOKEX", "TEXRAIL",
    "PCJEWELLER", "TIPSFILMS", "NUVOCO",
    "UCOBANK", "IOB", "CENTRALBNK", "MAHABANK", "JKBANK",
    "TMVL", "SURYODAY", "UTKARSHBNK",
    "IIFLWAM", "MOTILALOS", "5PAISA", "ANGELONE", "GEOJIT",
    "JMFINANCIL", "PNBHOUSING",
    "CERA", "SOMANYCER", "ORIENTBELL",
    "FIEMIND", "SUBROS", "SUPRAJIT", "LUMAXTECH", "SETCO",
    "WABAG", "VA-TECH", "THERMAX", "BHEL", "BEL",
    "HAL", "BEML", "COCHINSHIP", "GRSE", "MAZDA",
    "NYKAA", "MAMAEARTH", "HONASA",
    "ZOMATO", "SWIGGY",
    "DRONEACHARYA", "IDEAFORGE",
    "LATENTVIEW", "DATAMATICS", "INTELLECT", "NEWGEN", "NUCLEUS",
    "ONMOBILE", "SAKSOFT", "FIVESTAR",
    "PENTAGOLD", "SUVENPHAR", "NEULANDLAB", "MARKSANS",
    "SHILPAMED", "KRSNAA", "VIJAYADIAG",
    "KRBL", "AVANTIFEED", "WATERBASE", "APEX",
    "GANECOS", "SUMITCHEM", "BAYER", "GHCL",
    "SANDESH", "NAVNETEDUL", "TREEHOUSE",
]

# ── Micro Cap / Emerging ──────────────────────────────────────────────────────
MICROCAP = [
    "IDEAFORGE", "DRONEACHARYA", "SANSERA", "MTAR", "PARAS",
    "GLAND", "STOVEKRAFT", "BARBEQUE", "SPECIALITY", "EASEMYTRIP",
    "CARTRADE", "CHEMPLAST", "TATAINVEST", "TATATECH", "TATAPOWER",
    "TATAELXSI", "KFINTECH", "CDSL", "BSELTD", "MCX",
    "MULTI", "GOLDIAM", "RAJESHEXPO", "PCJEWELLER", "THANGAMAYL",
    "LLOYDSENGG", "LLOYDSME", "HARSHA", "TEXINFRA",
    "VIMTA", "SUPRIYA", "SEQUENT", "DIVI", "INDOCO",
    "LXCHEM", "DMCC", "GUFICBIO", "CAPLIN",
    "PRICOLLTD", "ENDURANCE", "LUMAX", "MNRINDIA",
    "MATRIMONY", "INDIGOPNTS", "ASIANTILES",
    "HEGDE", "HATHWAY", "GTLINFRA", "RCOM",
    "PNGJLTH", "PCBL", "NOCIL", "ATUL",
    "BASF", "DEEPAKFERT", "CHAMBAL", "COROMANDEL",
    "INSECTICID", "HERANBA", "TATVA", "CLEAN",
    "MAZAGSHIP", "GESHIP", "SCHNEIDER",
    "GLAND", "NEULAND", "STRIDES", "SOLARA",
    "RPGLIFE", "MORPEN", "AJANTPHARM", "IPCA",
    "JINDALSAW", "RATNAMANI", "WELCORP", "MANALIPETC",
]

# ── Sector → symbols ──────────────────────────────────────────────────────────
SECTOR_SYMBOLS: dict[str, list[str]] = {
    "NIFTY IT": [
        "TCS", "INFY", "HCLTECH", "WIPRO", "TECHM", "PERSISTENT",
        "COFORGE", "MPHASIS", "LTTS", "KPITTECH", "TATAELXSI", "CYIENT",
        "MASTEK", "BIRLASOFT", "HAPPSTMNDS", "TANLA", "ROUTE",
        "LATENTVIEW", "NAZARA", "INTELLECT", "NEWGEN", "NUCLEUS",
        "DATAMATICS", "SAKSOFT", "KFINTECH",
    ],
    "NIFTY BANK": [
        "HDFCBANK", "ICICIBANK", "AXISBANK", "KOTAKBANK", "INDUSINDBK",
        "SBIN", "BANKBARODA", "PNB", "CANBK", "FEDERALBNK", "IDFCFIRSTB",
        "BANDHANBNK", "RBLBANK", "YESBANK", "KARURVYSYA", "DCBBANK",
        "SOUTHBANK", "CSBBANK", "JKBANK", "UCOBANK", "IOB",
        "CENTRALBNK", "MAHABANK", "UJJIVANSFB", "EQUITASBNK",
        "UTKARSHBNK", "SURYODAY",
    ],
    "NIFTY AUTO": [
        "MARUTI", "TATAMOTORS", "BAJAJ-AUTO", "EICHERMOT", "HEROMOTOCO",
        "BOSCHLTD", "BALKRISIND", "MRF", "ESCORTS", "TIINDIA",
        "SUBROS", "SUPRAJIT", "LUMAXTECH", "ENDURANCE", "SANSERA",
        "LUMAX", "PRICOLLTD",
    ],
    "NIFTY PHARMA": [
        "SUNPHARMA", "CIPLA", "DRREDDY", "DIVISLAB", "LUPIN",
        "BIOCON", "APOLLOHOSP", "AUROPHARMA", "GLENMARK", "ALKEM",
        "ZYDUSLIFE", "TORNTPHARM", "GRANULES", "LAURUSLABS", "SUVEN",
        "JBCHEPHARM", "SEQUENT", "AJANTPHARM", "IPCA", "STRIDES",
        "SOLARA", "NEULAND", "MARKSANS", "KRSNAA", "VIJAYADIAG",
    ],
    "NIFTY FMCG": [
        "HINDUNILVR", "ITC", "BRITANNIA", "NESTLEIND", "DABUR",
        "GODREJCP", "COLPAL", "TATACONSUM", "MARICO", "EMAMI",
        "JYOTHYLAB", "RELAXO", "BATA", "RAYMOND",
    ],
    "NIFTY METAL": [
        "TATASTEEL", "JSWSTEEL", "HINDALCO", "COALINDIA", "SAIL",
        "NMDC", "NATIONALUM", "VEDL", "HINDZINC", "MOIL",
        "GPIL", "JSWISPL", "RATNAMANI", "JINDALSAW", "WELCORP",
    ],
    "NIFTY REALTY": [
        "DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE",
        "SOBHA", "BRIGADE", "MAHINDRACIE", "KOLTEPATIL",
    ],
    "NIFTY ENERGY": [
        "RELIANCE", "ONGC", "BPCL", "GAIL", "NTPC", "POWERGRID",
        "ADANIGREEN", "ADANITRANS", "ADANIPOWER", "TATAPOWER",
        "WAAREEENER", "INOXWIND", "SUZLON", "NHPC", "SJVN",
        "IREDA", "RECLTD", "PFC",
    ],
    "NIFTY MEDIA": [
        "ZEEL", "SUNTV", "NAZARA", "TIPSINDLTD", "TIPSFILMS",
    ],
    "NIFTY FINANCIAL SERVICES": [
        "BAJFINANCE", "BAJAJFINSV", "MUTHOOTFIN", "SBILIFE", "HDFCLIFE",
        "CHOLAFIN", "LTFH", "MANAPPURAM", "SHRIRAMFIN", "MFSL",
        "IIFL", "360ONE", "ANANDRAT", "CAMS", "CDSL", "IEX",
        "CANFINHOME", "AAVAS", "APTUS", "HOMEFIRST", "CREDITACC",
        "ARMANFIN", "SPANDANA", "ICICIPRULI", "CRISIL",
        "IIFLWAM", "MOTILALOS", "5PAISA", "ANGELONE", "JMFINANCIL",
        "PNBHOUSING", "FIVESTAR", "INDOSTAR",
    ],
    "NIFTY PSU BANK": [
        "SBIN", "BANKBARODA", "PNB", "CANBK", "UCOBANK", "IOB",
        "CENTRALBNK", "MAHABANK",
    ],
    "NIFTY CONSUMER DURABLES": [
        "TITAN", "HAVELLS", "SIEMENS", "ABB", "VOLTAS", "WHIRLPOOL",
        "BLUESTARCO", "VGUARD", "CROMPTON", "AMBER", "DIXON",
    ],
    "NIFTY OIL AND GAS": [
        "RELIANCE", "ONGC", "BPCL", "GAIL", "DEEPAKFERT", "CHAMBAL",
    ],
    "NIFTY HEALTHCARE INDEX": [
        "SUNPHARMA", "CIPLA", "DRREDDY", "DIVISLAB", "APOLLOHOSP",
        "LUPIN", "BIOCON", "MAXHEALTH", "FORTIS",
    ],
    "NIFTY INFRASTRUCTURE": [
        "LT", "ADANIPORTS", "CONCOR", "IRCTC", "RVNL", "IRCON",
        "IRFC", "HUDCO", "IRB", "ASHOKA", "PNCINFRA",
        "GMRINFRA", "CAPACITE", "BHEL", "BEL", "HAL", "BEML",
        "COCHINSHIP", "GRSE",
    ],
    "NIFTY CHEMICALS": [
        "PIDILITE", "DEEPAKNTR", "PIIND", "AARTIIND", "FINEORG",
        "SUDARSCHEM", "NOCIL", "ATUL", "BASF", "DEEPAKFERT",
        "CHAMBAL", "COROMANDEL", "DHANUKA", "RALLIS", "PRAJIND",
        "INDIAGLYCO", "GHCL", "TATVA", "CLEAN",
    ],
    "NIFTY CEMENT": [
        "ULTRACEMCO", "SHREECEM", "AMBUJACEM", "GRASIM", "JKCEMENT",
        "RAMCOCEM", "HEIDELBERG", "BIRLACORPN", "NUVOCO",
        "ORIENTCEM", "STARCEMENT", "CERA", "KCP",
    ],
    "NIFTY DEFENCE": [
        "HAL", "BEL", "BEML", "COCHINSHIP", "GRSE",
        "MTAR", "IDEAFORGE", "PARAS", "DRONEACHARYA",
    ],
    "NIFTY 50": NIFTY100[:50],
}


# ── Combined universe ─────────────────────────────────────────────────────────
def _merge(*lists: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for lst in lists:
        for sym in lst:
            if sym not in seen:
                seen.add(sym)
                out.append(sym)
    return out


ALL_SYMBOLS: list[str] = _merge(NIFTY100, MIDCAP, SMALLCAP, MICROCAP)


def build_universe(universes: list[str]) -> list[str]:
    out: list[str] = []
    if "NIFTY100" in universes:
        out.extend(NIFTY100)
    if "MIDCAP" in universes:
        out.extend(MIDCAP)
    if "SMALLCAP" in universes:
        out.extend(SMALLCAP)
    if "MICROCAP" in universes:
        out.extend(MICROCAP)
    if "ALL" in universes:
        return list(ALL_SYMBOLS)
    return list(dict.fromkeys(out))


VALID_UNIVERSES = {"NIFTY100", "MIDCAP", "SMALLCAP", "MICROCAP", "ALL"}

# ── Live data overlay ─────────────────────────────────────────────────────────
# If a fresh universe_cache.json exists (written by universe_builder.py),
# override the hardcoded lists with live NSE data at import time.
# The hardcoded lists above remain as the reliable fallback.

COMPANY_MAP: dict[str, str] = {}   # symbol → company name (populated from cache)

def _apply_live_data(cache: dict) -> None:
    """Merge live cache into module-level dicts/lists (non-destructive)."""
    global ALL_SYMBOLS, SECTOR_SYMBOLS, COMPANY_MAP

    live_syms   = cache.get("all_symbols", [])
    live_secs   = cache.get("sector_symbols", {})
    live_names  = cache.get("company_map", {})
    live_cats   = cache.get("categories", {})

    if live_names:
        COMPANY_MAP.update(live_names)

    if live_syms:
        # Build categorised lists from live AMFI categories + sector index membership
        nifty100_live  = set(live_secs.get("NIFTY 100", []) or live_secs.get("NIFTY100", []))
        mid_live       = set(live_secs.get("NIFTY MIDCAP 150", []))
        small_live     = set(live_secs.get("NIFTY SMALLCAP 250", []))
        micro_live     = set(live_secs.get("NIFTY MICROCAP 250", []))

        new_nifty100  = sorted(set(
            s for s in live_syms
            if live_cats.get(s, "") == "Large-Cap" or s in nifty100_live
        ))
        new_midcap    = sorted(set(
            s for s in live_syms
            if live_cats.get(s, "") == "Mid-Cap" or s in mid_live
        ))
        new_smallcap  = sorted(set(
            s for s in live_syms
            if live_cats.get(s, "") == "Small-Cap" or s in small_live
        ))
        new_microcap  = sorted(set(
            s for s in live_syms
            if live_cats.get(s, "") == "Micro-Cap" or s in micro_live
        ))

        if new_nifty100 or new_midcap:
            global NIFTY100, MIDCAP, SMALLCAP, MICROCAP
            if new_nifty100:  NIFTY100  = new_nifty100
            if new_midcap:    MIDCAP    = new_midcap
            if new_smallcap:  SMALLCAP  = new_smallcap
            if new_microcap:  MICROCAP  = new_microcap
            ALL_SYMBOLS = _merge(NIFTY100, MIDCAP, SMALLCAP, MICROCAP)

        # Supplement ALL_SYMBOLS with any live symbols not in cap categories
        remaining = [s for s in live_syms if s not in set(ALL_SYMBOLS)]
        if remaining:
            ALL_SYMBOLS = ALL_SYMBOLS + remaining

    if live_secs:
        # Overlay sector symbols — keep hardcoded sectors as fallback for missing ones
        for sec, syms in live_secs.items():
            if syms:
                SECTOR_SYMBOLS[sec] = syms
        # Ensure legacy NIFTY 50 alias still works
        if "NIFTY 50" not in SECTOR_SYMBOLS:
            SECTOR_SYMBOLS["NIFTY 50"] = NIFTY100[:50]


# Apply cache immediately at import time (fast: just a JSON read)
try:
    from .universe_builder import load_cache as _load_cache
    _cached = _load_cache()
    if _cached:
        _apply_live_data(_cached)
        import logging as _log
        _log.getLogger(__name__).info(
            "universe: loaded live data — %d symbols, %d sectors",
            len(ALL_SYMBOLS), len(SECTOR_SYMBOLS),
        )
except Exception as _e:
    import logging as _log
    _log.getLogger(__name__).warning("universe: could not load cache: %s", _e)
