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
    "PAYTM", "POLICYBZR", "MARICO", "MAXHEALTH", "FORTIS",
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
    "NEULAND", "STRIDES", "SOLARA",
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


# ── Comprehensive Indian Sub-Industry Taxonomy ────────────────────────────────
# Manually curated mapping of NSE sub-industry → constituent symbols.
# Used as a SEED for the synthetic rotation engine: any symbol here gets a
# valid sub_industry tag even if Yahoo profile fetch fails or Yahoo uses a
# different label. The engine merges these seeds with Yahoo-classified rows
# so real Yahoo data always takes precedence for market-cap and pricing.
#
# Admin overrides (stored in sub_industry_overrides DB table) are merged on
# top at query time — admins can add any missing stock without code changes.
#
# Coverage goal: every meaningful Indian equity sub-sector with ≥3 constituents
# across Banking, Finance, Insurance, IT, Pharma, FMCG, Auto, Metals, Energy,
# Chemicals, Capital Goods, Real Estate, Textiles, Media, Diagnostics, QSR,
# Hospitals, Jewellery, Defence, Agrochemicals, Logistics, Retail, etc.

SUBSECTOR_TAXONOMY: dict[str, dict] = {
    # ── Banking ───────────────────────────────────────────────────────────────
    "Banks - Private Large Cap": {
        "industry": "Banks",
        "sector": "Financial Services",
        "symbols": ["HDFCBANK", "ICICIBANK", "AXISBANK", "KOTAKBANK", "INDUSINDBK"],
    },
    "Banks - Private Mid & Small Cap": {
        "industry": "Banks",
        "sector": "Financial Services",
        "symbols": [
            "FEDERALBNK", "IDFCFIRSTB", "BANDHANBNK", "RBLBANK", "YESBANK",
            "KARURVYSYA", "DCBBANK", "SOUTHBANK", "CSBBANK", "JKBANK",
            "UCOBANK", "EQUITASBNK", "UJJIVANSFB", "SURYODAY", "UTKARSHBNK",
            "LAKSHVILAS",
        ],
    },
    "Banks - PSU": {
        "industry": "Banks",
        "sector": "Financial Services",
        "symbols": [
            "SBIN", "BANKBARODA", "PNB", "CANBK", "IOB",
            "CENTRALBNK", "MAHABANK", "UCOBANK",
        ],
    },
    # ── NBFC & Lending ────────────────────────────────────────────────────────
    "NBFC - Consumer Lending": {
        "industry": "NBFC & Lending",
        "sector": "Financial Services",
        "symbols": [
            "BAJFINANCE", "CHOLAFIN", "MUTHOOTFIN", "MANAPPURAM",
            "SHRIRAMFIN", "LTFH", "FIVESTAR", "CREDITACC", "ARMANFIN",
            "SPANDANA", "INDOSTAR", "POONAWALLA",
        ],
    },
    "NBFC - Housing Finance": {
        "industry": "NBFC & Lending",
        "sector": "Financial Services",
        "symbols": [
            "PNBHOUSING", "CANFINHOME", "AAVAS", "HOMEFIRST",
            "APTUS", "REPCO", "AWHCL",
        ],
    },
    "NBFC - Gold Finance": {
        "industry": "NBFC & Lending",
        "sector": "Financial Services",
        "symbols": ["MUTHOOTFIN", "MANAPPURAM", "IIFL"],
    },
    # ── Capital Markets ───────────────────────────────────────────────────────
    "Asset Management": {
        "industry": "Capital Markets",
        "sector": "Financial Services",
        "symbols": ["HDFCAMC", "NIPPINDIA", "IIFLWAM", "360ONE", "ANANDRAT"],
    },
    "Broking & Wealth Management": {
        "industry": "Capital Markets",
        "sector": "Financial Services",
        "symbols": [
            "MOTILALOS", "5PAISA", "ANGELONE", "GEOJIT", "IIFL",
            "JMFINANCIL", "ICICIPRULI",
        ],
    },
    "Exchanges & Depositories": {
        "industry": "Capital Markets",
        "sector": "Financial Services",
        "symbols": ["BSE", "MCX", "CDSL", "CAMS", "IEX", "CRISIL"],
    },
    # ── Insurance ─────────────────────────────────────────────────────────────
    "Insurance - Life": {
        "industry": "Insurance",
        "sector": "Financial Services",
        "symbols": ["LICI", "SBILIFE", "HDFCLIFE", "MAXLIFE", "ICICIPRULI", "BAJAJFINSV", "MFSL"],
    },
    "Insurance - General": {
        "industry": "Insurance",
        "sector": "Financial Services",
        "symbols": ["GENERALINS", "NIACL", "STARHEALTH", "ICICIlombard", "BAJAJFINSV"],
    },
    # ── IT & Technology ───────────────────────────────────────────────────────
    "IT Services - Tier 1": {
        "industry": "IT Services",
        "sector": "Technology",
        "symbols": ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM"],
    },
    "IT Services - Mid Tier": {
        "industry": "IT Services",
        "sector": "Technology",
        "symbols": [
            "LTTS", "PERSISTENT", "COFORGE", "MPHASIS", "KPITTECH",
            "TATAELXSI", "CYIENT", "MASTEK", "BIRLASOFT", "HAPPSTMNDS",
        ],
    },
    "IT Services - Small Cap": {
        "industry": "IT Services",
        "sector": "Technology",
        "symbols": [
            "TANLA", "ROUTE", "LATENTVIEW", "NAZARA", "INTELLECT",
            "NEWGEN", "NUCLEUS", "DATAMATICS", "SAKSOFT", "XCHANGING",
            "ONMOBILE",
        ],
    },
    "Software Products": {
        "industry": "Software",
        "sector": "Technology",
        "symbols": ["INFOEDGE", "ZOMATO", "NAUKRI", "POLICYBZR", "PAYTM", "NYKAA"],
    },
    "IT - Data & Analytics": {
        "industry": "IT Services",
        "sector": "Technology",
        "symbols": ["KFINTECH", "CDSL", "CAMS", "CRISIL"],
    },
    # ── Pharmaceuticals ───────────────────────────────────────────────────────
    "Pharma - Large Cap Formulations": {
        "industry": "Pharmaceuticals",
        "sector": "Healthcare",
        "symbols": [
            "SUNPHARMA", "CIPLA", "DRREDDY", "DIVISLAB", "LUPIN",
            "BIOCON", "AUROPHARMA", "ZYDUSLIFE", "ALKEM", "TORNTPHARM",
        ],
    },
    "Pharma - Mid Cap Formulations": {
        "industry": "Pharmaceuticals",
        "sector": "Healthcare",
        "symbols": [
            "GLENMARK", "GRANULES", "LAURUSLABS", "JBCHEPHARM", "AJANTPHARM",
            "IPCA", "STRIDES", "MARKSANS", "NEULAND", "SOLARA",
            "MORPEN", "INDOCO",
        ],
    },
    "Pharma - APIs & CRAMS": {
        "industry": "Pharmaceuticals",
        "sector": "Healthcare",
        "symbols": [
            "NEULAND", "SUVEN", "SEQUENT", "GLAND", "CAPLIN",
            "LXCHEM", "TATVA", "RPGLIFE",
        ],
    },
    "Pharma - Veterinary & Specialty": {
        "industry": "Pharmaceuticals",
        "sector": "Healthcare",
        "symbols": ["SEQUENT", "HERANBA", "INSECTICID"],
    },
    # ── Healthcare ────────────────────────────────────────────────────────────
    "Hospitals & Healthcare Services": {
        "industry": "Healthcare Services",
        "sector": "Healthcare",
        "symbols": [
            "APOLLOHOSP", "MAXHEALTH", "FORTIS", "NARAYANAH", "ASTER",
            "YATHARTH", "PRISTINE",
        ],
    },
    "Diagnostics & Pathology": {
        "industry": "Healthcare Services",
        "sector": "Healthcare",
        "symbols": [
            "METROPOLIS", "THYROCARE", "KRSNAA", "VIJAYADIAG",
            "REDCLIFFE", "LALPATHLAB",
        ],
    },
    # ── FMCG ──────────────────────────────────────────────────────────────────
    "FMCG - HPC & Personal Care": {
        "industry": "FMCG",
        "sector": "Consumer Goods",
        "symbols": [
            "HINDUNILVR", "GODREJCP", "COLPAL", "MARICO", "EMAMI",
            "JYOTHYLAB", "DABUR",
        ],
    },
    "FMCG - Food & Beverages": {
        "industry": "FMCG",
        "sector": "Consumer Goods",
        "symbols": [
            "NESTLEIND", "BRITANNIA", "TATACONSUM", "ITC", "MARICO",
            "MCDOWELL-N", "RADICO", "BALRAMCHIN", "RENUKA", "TRIVENI",
            "KRBL", "AVANTIFEED",
        ],
    },
    "FMCG - Paints & Adhesives": {
        "industry": "FMCG",
        "sector": "Consumer Goods",
        "symbols": ["ASIANPAINT", "BERGEPAINT", "KANSAINER", "AKZOINDIA", "INDIGO", "PIDILITE"],
    },
    # ── Retail & QSR ──────────────────────────────────────────────────────────
    "Quick Service Restaurants": {
        "industry": "Retail",
        "sector": "Consumer Cyclical",
        "symbols": [
            "JUBLFOOD", "DEVYANI", "WESTLIFE", "SAPPHIRE", "BARBEQUE",
        ],
    },
    "Retail - Specialty": {
        "industry": "Retail",
        "sector": "Consumer Cyclical",
        "symbols": [
            "DMART", "TRENT", "VMART", "SHOPERSTOP", "VLMART",
        ],
    },
    "Food Delivery & Quick Commerce": {
        "industry": "Internet Services",
        "sector": "Consumer Cyclical",
        "symbols": ["ZOMATO", "SWIGGY"],
    },
    # ── Automobiles ───────────────────────────────────────────────────────────
    "Automobiles - Passenger Vehicles": {
        "industry": "Automobiles",
        "sector": "Consumer Cyclical",
        "symbols": ["MARUTI", "TATAMOTORS", "MAHINDRA", "M&M"],
    },
    "Automobiles - Two Wheelers": {
        "industry": "Automobiles",
        "sector": "Consumer Cyclical",
        "symbols": ["BAJAJ-AUTO", "HEROMOTOCO", "EICHERMOT", "TVSMOTORS"],
    },
    "Automobiles - Commercial Vehicles": {
        "industry": "Automobiles",
        "sector": "Consumer Cyclical",
        "symbols": ["TATAMOTORS", "ASHOKLEY", "SML"],
    },
    "Auto Components": {
        "industry": "Auto Components",
        "sector": "Consumer Cyclical",
        "symbols": [
            "BOSCHLTD", "BALKRISIND", "MRF", "ESCORTS", "TIINDIA",
            "SUBROS", "SUPRAJIT", "LUMAXTECH", "ENDURANCE", "SANSERA",
            "LUMAX", "PRICOLLTD", "MOTHERSON", "EXIDEIND", "AMARON",
        ],
    },
    # ── Metals & Mining ───────────────────────────────────────────────────────
    "Steel - Integrated": {
        "industry": "Metals & Mining",
        "sector": "Basic Materials",
        "symbols": ["TATASTEEL", "JSWSTEEL", "SAIL", "GPIL"],
    },
    "Steel - Long Products": {
        "industry": "Metals & Mining",
        "sector": "Basic Materials",
        "symbols": ["JSWSTEEL", "JINDALSAW", "WELCORP", "RATNAMANI", "APLAPOLLO"],
    },
    "Aluminium & Non-Ferrous Metals": {
        "industry": "Metals & Mining",
        "sector": "Basic Materials",
        "symbols": ["HINDALCO", "NATIONALUM", "VEDL", "HINDZINC", "MOIL"],
    },
    "Mining & Minerals": {
        "industry": "Metals & Mining",
        "sector": "Basic Materials",
        "symbols": ["COALINDIA", "NMDC", "MOIL", "GMRINFRA"],
    },
    # ── Chemicals ─────────────────────────────────────────────────────────────
    "Specialty Chemicals": {
        "industry": "Chemicals",
        "sector": "Basic Materials",
        "symbols": [
            "PIDILITE", "DEEPAKNTR", "AARTIIND", "FINEORG", "SUDARSCHEM",
            "NOCIL", "ATUL", "GHCL", "TATVA", "CLEAN", "LXCHEM",
        ],
    },
    "Agrochemicals & Fertilizers": {
        "industry": "Chemicals",
        "sector": "Basic Materials",
        "symbols": [
            "PIIND", "DHANUKA", "RALLIS", "PRAJIND", "BAYER",
            "DEEPAKFERT", "CHAMBAL", "COROMANDEL", "INSECTICID", "HERANBA",
            "SUMITCHEM", "IFFCO",
        ],
    },
    "Petrochemicals": {
        "industry": "Chemicals",
        "sector": "Basic Materials",
        "symbols": ["RELIANCE", "GAIL", "DEEPAKFERT", "BASF", "INDIAGLYCO"],
    },
    # ── Oil & Gas ─────────────────────────────────────────────────────────────
    "Oil & Gas - Upstream": {
        "industry": "Oil & Gas",
        "sector": "Energy",
        "symbols": ["ONGC", "OIL", "CAIRN"],
    },
    "Oil & Gas - Downstream / Refining": {
        "industry": "Oil & Gas",
        "sector": "Energy",
        "symbols": ["RELIANCE", "BPCL", "IOCL", "HPCL", "MRPL", "CPCL"],
    },
    "Oil & Gas - Distribution & City Gas": {
        "industry": "Oil & Gas",
        "sector": "Energy",
        "symbols": ["GAIL", "IGL", "MGL", "GUJS", "ATGL", "GSPL"],
    },
    # ── Power & Utilities ─────────────────────────────────────────────────────
    "Power Generation - Thermal & Hydro": {
        "industry": "Power & Utilities",
        "sector": "Utilities",
        "symbols": ["NTPC", "NHPC", "SJVN", "TATAPOWER", "ADANIPOWER", "TORNTPOWER"],
    },
    "Power Generation - Renewable": {
        "industry": "Power & Utilities",
        "sector": "Utilities",
        "symbols": [
            "ADANIGREEN", "ADANITRANS", "WAAREEENER", "INOXWIND",
            "SUZLON", "GREENKO", "IREDA",
        ],
    },
    "Power Transmission & Distribution": {
        "industry": "Power & Utilities",
        "sector": "Utilities",
        "symbols": ["POWERGRID", "ADANITRANS", "CESC", "BSES", "TORNTPOWER"],
    },
    # ── Capital Goods & Engineering ───────────────────────────────────────────
    "Heavy Engineering & Capital Goods": {
        "industry": "Capital Goods",
        "sector": "Industrials",
        "symbols": [
            "LT", "SIEMENS", "ABB", "BHEL", "THERMAX",
            "ELGIEQUIP", "APARINDS", "TIINDIA",
        ],
    },
    "Defence & Aerospace": {
        "industry": "Defence",
        "sector": "Industrials",
        "symbols": [
            "HAL", "BEL", "BEML", "COCHINSHIP", "GRSE",
            "MTAR", "IDEAFORGE", "PARAS", "DRONEACHARYA", "SANSERA",
            "DYNAMATECH", "SOLARA",
        ],
    },
    "Electronics Manufacturing (EMS)": {
        "industry": "Capital Goods",
        "sector": "Industrials",
        "symbols": ["DIXON", "AMBER", "KAYNES", "SYRMA", "AVALON"],
    },
    "Cables & Wires": {
        "industry": "Capital Goods",
        "sector": "Industrials",
        "symbols": ["POLYCAB", "HAVELLS", "VGUARD", "HFCL", "APAR", "KEI"],
    },
    # ── Infrastructure ────────────────────────────────────────────────────────
    "EPC & Construction": {
        "industry": "Capital Goods",
        "sector": "Industrials",
        "symbols": [
            "LT", "NCC", "PNCINFRA", "RVNL", "IRCON",
            "ASHOKA", "IRB", "CAPACITE", "HGINFRA", "KNRCON",
        ],
    },
    "Ports & Logistics": {
        "industry": "Logistics",
        "sector": "Industrials",
        "symbols": [
            "ADANIPORTS", "CONCOR", "DELHIVERY", "BLUEDART",
            "MAHLOG", "GATI", "ALLCARGO",
        ],
    },
    "Railways & Rail Infrastructure": {
        "industry": "Industrials",
        "sector": "Industrials",
        "symbols": ["IRCTC", "RVNL", "IRCON", "IRFC", "HUDCO", "RAILTEL"],
    },
    "Shipping & Aviation": {
        "industry": "Industrials",
        "sector": "Industrials",
        "symbols": [
            "COCHINSHIP", "GRSE", "GESHIP", "INTERGLOBE", "SPICEJET",
        ],
    },
    # ── Real Estate ───────────────────────────────────────────────────────────
    "Real Estate - Residential": {
        "industry": "Real Estate",
        "sector": "Real Estate",
        "symbols": [
            "DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE", "SOBHA",
            "BRIGADE", "KOLTEPATIL", "MAHINDRACIE", "SUNTECK", "PURVA",
            "LODHA", "MACROTECH",
        ],
    },
    "Real Estate - Commercial": {
        "industry": "Real Estate",
        "sector": "Real Estate",
        "symbols": ["DLF", "MINDSPACE", "BROOKFIELD", "EMBASSY"],
    },
    # ── Consumer Durables & Electronics ──────────────────────────────────────
    "White Goods & Appliances": {
        "industry": "Consumer Durables",
        "sector": "Consumer Cyclical",
        "symbols": [
            "TITAN", "HAVELLS", "VOLTAS", "WHIRLPOOL", "BLUESTARCO",
            "VGUARD", "CROMPTON", "AMBER",
        ],
    },
    "Consumer Electronics": {
        "industry": "Consumer Durables",
        "sector": "Consumer Cyclical",
        "symbols": ["DIXON", "AMBER", "VGUARD", "VIMICRO"],
    },
    # ── Textiles & Apparel ────────────────────────────────────────────────────
    "Textile - Spinning & Yarn": {
        "industry": "Textiles",
        "sector": "Consumer Cyclical",
        "symbols": [
            "WELSPUNLIV", "TRIDENT", "VARDHMAN", "RUPA", "DOLLAR",
            "KPRMILL", "NITIN",
        ],
    },
    "Textile - Technical & Home Furnishing": {
        "industry": "Textiles",
        "sector": "Consumer Cyclical",
        "symbols": ["WELSPUNLIV", "TRIDENT", "GREENPANEL", "CENTURYPLY"],
    },
    "Apparel & Fashion Retail": {
        "industry": "Retail",
        "sector": "Consumer Cyclical",
        "symbols": ["ABFRL", "RAYMOND", "BATA", "RELAXO", "VMART"],
    },
    # ── Building Materials & Cement ───────────────────────────────────────────
    "Cement - Large Cap": {
        "industry": "Construction Materials",
        "sector": "Basic Materials",
        "symbols": [
            "ULTRACEMCO", "SHREECEM", "AMBUJACEM", "GRASIM", "JKCEMENT",
        ],
    },
    "Cement - Mid & Small Cap": {
        "industry": "Construction Materials",
        "sector": "Basic Materials",
        "symbols": [
            "RAMCOCEM", "HEIDELBERG", "BIRLACORPN", "NUVOCO",
            "ORIENTCEM", "STARCEMENT", "KCP",
        ],
    },
    "Building Products - Pipes & Fittings": {
        "industry": "Construction Materials",
        "sector": "Basic Materials",
        "symbols": ["ASTRAL", "SUPREMIND", "FINOLEX", "PRINCE"],
    },
    "Building Products - Tiles & Sanitaryware": {
        "industry": "Construction Materials",
        "sector": "Basic Materials",
        "symbols": [
            "KAJARIA", "CERA", "SOMANYCER", "ORIENTBELL", "ASIANTILES",
            "KAJARIACER",
        ],
    },
    "Wood & Laminates": {
        "industry": "Construction Materials",
        "sector": "Basic Materials",
        "symbols": ["GREENPANEL", "CENTURYPLY", "APLAPOLLO"],
    },
    # ── Jewellery ─────────────────────────────────────────────────────────────
    "Jewellery & Watches": {
        "industry": "Retail",
        "sector": "Consumer Cyclical",
        "symbols": [
            "TITAN", "KALYAN", "SENCO", "THANGAMAYL", "RAJESHEXPO",
            "GOLDIAM", "PCJEWELLER", "TRIBHOVANDAS",
        ],
    },
    # ── Media & Entertainment ─────────────────────────────────────────────────
    "Television Broadcasting": {
        "industry": "Media",
        "sector": "Communication Services",
        "symbols": ["ZEEL", "SUNTV", "PVRINOX"],
    },
    "Digital Media & Gaming": {
        "industry": "Media",
        "sector": "Communication Services",
        "symbols": ["NAZARA", "TIPSINDLTD", "TIPSFILMS", "INDIGOPNTS"],
    },
    # ── Telecom ───────────────────────────────────────────────────────────────
    "Telecom Services": {
        "industry": "Telecom",
        "sector": "Communication Services",
        "symbols": ["BHARTIARTL", "IDEA", "TATACOMM", "HFCL"],
    },
    "Telecom Infrastructure": {
        "industry": "Telecom",
        "sector": "Communication Services",
        "symbols": ["INDUS", "ASTER", "GTLINFRA", "HATHWAY"],
    },
    # ── Sugar & Agri ──────────────────────────────────────────────────────────
    "Sugar Refineries": {
        "industry": "Sugar",
        "sector": "Consumer Goods",
        "symbols": ["BALRAMCHIN", "RENUKA", "TRIVENI", "EIDPARRY", "UGAR"],
    },
    "Aquaculture & Processed Foods": {
        "industry": "Agri & Food",
        "sector": "Consumer Goods",
        "symbols": ["AVANTIFEED", "WATERBASE", "APEX", "KRBL"],
    },
}

# All unique symbols across the taxonomy (used to seed the classifier)
SUBSECTOR_SYMBOLS: list[str] = sorted(set(
    sym
    for entry in SUBSECTOR_TAXONOMY.values()
    for sym in entry["symbols"]
))

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


# ── NSE & BSE Indices (searchable, chartable) ─────────────────────────────────
INDICES: list[str] = [
    # NSE Broad Market
    "NIFTY 50", "NIFTY NEXT 50", "NIFTY 100", "NIFTY 200", "NIFTY 500",
    "NIFTY MIDCAP 50", "NIFTY MIDCAP 100", "NIFTY MIDCAP 150", "NIFTY MIDCAP SELECT",
    "NIFTY SMALLCAP 50", "NIFTY SMALLCAP 100", "NIFTY SMALLCAP 250",
    "NIFTY MICROCAP 250", "NIFTY LARGEMIDCAP 250",
    # NSE Sectoral
    "NIFTY BANK", "NIFTY FIN SERVICE", "NIFTY IT", "NIFTY AUTO",
    "NIFTY PHARMA", "NIFTY FMCG", "NIFTY METAL", "NIFTY REALTY",
    "NIFTY ENERGY", "NIFTY INFRA", "NIFTY PSU BANK", "NIFTY MNC",
    "NIFTY MEDIA", "NIFTY HEALTHCARE", "NIFTY COMMODITIES",
    "NIFTY SERVICES SECTOR", "NIFTY CPSE", "NIFTY PSE",
    "NIFTY OIL & GAS", "NIFTY CONSUMER DURABLES",
    "NIFTY INDIA CONSUMPTION", "NIFTY INDIA DIGITAL", "NIFTY INDIA DEFENCE",
    # NSE Strategy / Thematic
    "INDIA VIX", "NIFTY ALPHA 50", "NIFTY50 VALUE 20",
    # BSE Broad Market
    "SENSEX", "BSE 100", "BSE 200", "BSE 500",
    "BSE MIDCAP", "BSE SMALLCAP", "BSE LARGECAP",
    # BSE Sectoral
    "BANKEX", "BSE IT", "BSE HEALTHCARE", "BSE AUTO", "BSE FMCG",
    "BSE METAL", "BSE REALTY", "BSE ENERGY", "BSE POWER",
    "BSE CAPITAL GOODS", "BSE CONSUMER DURABLES", "BSE TECK",
    "BSE OIL & GAS", "BSE UTILITIES", "BSE FINANCE",
    "BSE INDUSTRIALS", "BSE TELECOM", "BSE COMMODITIES",
]

# Human-readable names for each index (used in search results)
INDICES_COMPANY_MAP: dict[str, str] = {
    "NIFTY 50":                 "Nifty 50 Index (NSE)",
    "NIFTY NEXT 50":            "Nifty Next 50 Index (NSE)",
    "NIFTY 100":                "Nifty 100 Index (NSE)",
    "NIFTY 200":                "Nifty 200 Index (NSE)",
    "NIFTY 500":                "Nifty 500 Index (NSE)",
    "NIFTY MIDCAP 50":          "Nifty Midcap 50 Index (NSE)",
    "NIFTY MIDCAP 100":         "Nifty Midcap 100 Index (NSE)",
    "NIFTY MIDCAP 150":         "Nifty Midcap 150 Index (NSE)",
    "NIFTY MIDCAP SELECT":      "Nifty Midcap Select Index (NSE)",
    "NIFTY SMALLCAP 50":        "Nifty Smallcap 50 Index (NSE)",
    "NIFTY SMALLCAP 100":       "Nifty Smallcap 100 Index (NSE)",
    "NIFTY SMALLCAP 250":       "Nifty Smallcap 250 Index (NSE)",
    "NIFTY MICROCAP 250":       "Nifty Microcap 250 Index (NSE)",
    "NIFTY LARGEMIDCAP 250":    "Nifty LargeMidcap 250 Index (NSE)",
    "NIFTY BANK":               "Nifty Bank Index (NSE)",
    "NIFTY FIN SERVICE":        "Nifty Financial Services Index (NSE)",
    "NIFTY IT":                 "Nifty IT Index (NSE)",
    "NIFTY AUTO":               "Nifty Auto Index (NSE)",
    "NIFTY PHARMA":             "Nifty Pharma Index (NSE)",
    "NIFTY FMCG":               "Nifty FMCG Index (NSE)",
    "NIFTY METAL":              "Nifty Metal Index (NSE)",
    "NIFTY REALTY":             "Nifty Realty Index (NSE)",
    "NIFTY ENERGY":             "Nifty Energy Index (NSE)",
    "NIFTY INFRA":              "Nifty Infrastructure Index (NSE)",
    "NIFTY PSU BANK":           "Nifty PSU Bank Index (NSE)",
    "NIFTY MNC":                "Nifty MNC Index (NSE)",
    "NIFTY MEDIA":              "Nifty Media Index (NSE)",
    "NIFTY HEALTHCARE":         "Nifty Healthcare Index (NSE)",
    "NIFTY COMMODITIES":        "Nifty Commodities Index (NSE)",
    "NIFTY SERVICES SECTOR":    "Nifty Services Sector Index (NSE)",
    "NIFTY CPSE":               "Nifty CPSE Index (NSE)",
    "NIFTY PSE":                "Nifty PSE Index (NSE)",
    "NIFTY OIL & GAS":          "Nifty Oil & Gas Index (NSE)",
    "NIFTY CONSUMER DURABLES":  "Nifty Consumer Durables Index (NSE)",
    "NIFTY INDIA CONSUMPTION":  "Nifty India Consumption Index (NSE)",
    "NIFTY INDIA DIGITAL":      "Nifty India Digital Index (NSE)",
    "NIFTY INDIA DEFENCE":      "Nifty India Defence Index (NSE)",
    "INDIA VIX":                "India Volatility Index (NSE)",
    "NIFTY ALPHA 50":           "Nifty Alpha 50 Index (NSE)",
    "NIFTY50 VALUE 20":         "Nifty 50 Value 20 Index (NSE)",
    "SENSEX":                   "BSE Sensex 30 Index",
    "BSE 100":                  "BSE 100 Index",
    "BSE 200":                  "BSE 200 Index",
    "BSE 500":                  "BSE 500 Index",
    "BSE MIDCAP":               "BSE Midcap Index",
    "BSE SMALLCAP":             "BSE Smallcap Index",
    "BSE LARGECAP":             "BSE Largecap Index",
    "BANKEX":                   "BSE Bankex Index",
    "BSE IT":                   "BSE IT Index",
    "BSE HEALTHCARE":           "BSE Healthcare Index",
    "BSE AUTO":                 "BSE Auto Index",
    "BSE FMCG":                 "BSE FMCG Index",
    "BSE METAL":                "BSE Metal Index",
    "BSE REALTY":               "BSE Realty Index",
    "BSE ENERGY":               "BSE Energy Index",
    "BSE POWER":                "BSE Power Index",
    "BSE CAPITAL GOODS":        "BSE Capital Goods Index",
    "BSE CONSUMER DURABLES":    "BSE Consumer Durables Index",
    "BSE TECK":                 "BSE Teck Index",
    "BSE OIL & GAS":            "BSE Oil & Gas Index",
    "BSE UTILITIES":            "BSE Utilities Index",
    "BSE FINANCE":              "BSE Finance Index",
    "BSE INDUSTRIALS":          "BSE Industrials Index",
    "BSE TELECOM":              "BSE Telecom Index",
    "BSE COMMODITIES":          "BSE Commodities Index",
}

# Pre-populate COMPANY_MAP with index names (stocks will be added from cache later)
COMPANY_MAP: dict[str, str] = dict(INDICES_COMPANY_MAP)

ALL_SYMBOLS: list[str] = INDICES + _merge(NIFTY100, MIDCAP, SMALLCAP, MICROCAP, SUBSECTOR_SYMBOLS)


# Tracks whether the live AMFI / NSE-membership cache was successfully loaded
# at import time. False ⇒ scanners and screener are running on the hardcoded
# fallback universe (potentially months out of date — surfaced in the UI as a
# stale-universe banner so users don't think they're scanning the live market).
is_live_universe: bool = False
universe_loaded_at: str | None = None


def universe_freshness() -> dict:
    """Public freshness contract for the universe — read by /scanners and /stocks endpoints."""
    return {
        "isLiveUniverse":   is_live_universe,
        "loadedAt":         universe_loaded_at,
        "totalSymbols":     len(ALL_SYMBOLS),
        "totalSectors":     len(SECTOR_SYMBOLS),
    }


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

# COMPANY_MAP is initialised above with index names; stock names are merged from cache below

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
            ALL_SYMBOLS = INDICES + _merge(NIFTY100, MIDCAP, SMALLCAP, MICROCAP)

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
        is_live_universe = True
        from datetime import datetime as _dt, timezone as _tz
        universe_loaded_at = _dt.now(_tz.utc).isoformat()
        import logging as _log
        _log.getLogger(__name__).info(
            "universe: loaded live data — %d symbols, %d sectors",
            len(ALL_SYMBOLS), len(SECTOR_SYMBOLS),
        )
    else:
        import logging as _log
        _log.getLogger(__name__).warning(
            "universe: live cache empty — falling back to hardcoded lists "
            "(may be months out of date; users will see stale-universe banner)"
        )
except Exception as _e:
    import logging as _log
    _log.getLogger(__name__).warning("universe: could not load cache: %s", _e)
