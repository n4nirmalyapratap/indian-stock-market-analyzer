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
]

MIDCAP = [
    "METROPOLIS", "IEX", "CAMS", "CDSL", "NAUKRI", "ASTRAL", "DEEPAKNTR",
    "CROMPTON", "CLEAN", "AAVAS", "HFCL", "OLECTRA", "HAPPSTMNDS",
]

SMALLCAP = [
    "MASTEK", "BIRLASOFT", "INFOEDGE", "TANLA", "ROUTE",
    "NAZARA", "LATENTVIEW", "XCHANGING",
]

# Canonical sector → constituent symbols mapping (best-effort NSE sector alignment)
SECTOR_SYMBOLS: dict[str, list[str]] = {
    "NIFTY IT": [
        "TCS", "INFY", "HCLTECH", "WIPRO", "TECHM", "PERSISTENT",
        "COFORGE", "MPHASIS", "LTTS", "KPITTECH", "TATAELXSI", "CYIENT",
    ],
    "NIFTY BANK": [
        "HDFCBANK", "ICICIBANK", "AXISBANK", "KOTAKBANK", "INDUSINDBK",
        "SBIN", "BANKBARODA", "PNB", "CANBK", "FEDERALBNK", "IDFCFIRSTB",
        "BANDHANBNK", "RBLBANK", "YESBANK",
    ],
    "NIFTY AUTO": [
        "MARUTI", "TATAMOTORS", "BAJAJ-AUTO", "EICHERMOT", "HEROMOTOCO",
        "BOSCHLTD",
    ],
    "NIFTY PHARMA": [
        "SUNPHARMA", "CIPLA", "DRREDDY", "DIVISLAB", "LUPIN",
        "BIOCON", "APOLLOHOSP",
    ],
    "NIFTY FMCG": [
        "HINDUNILVR", "ITC", "BRITANNIA", "NESTLEIND", "DABUR",
        "GODREJCP", "COLPAL", "TATACONSUM",
    ],
    "NIFTY METAL": [
        "TATASTEEL", "JSWSTEEL", "HINDALCO", "COALINDIA",
    ],
    "NIFTY REALTY": [
        "DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE",
    ],
    "NIFTY ENERGY": [
        "RELIANCE", "ONGC", "BPCL", "GAIL", "NTPC", "POWERGRID",
    ],
    "NIFTY MEDIA": [
        "ZEEL", "SUNTV", "NAZARA",
    ],
    "NIFTY FINANCIAL SERVICES": [
        "BAJFINANCE", "BAJAJFINSV", "MUTHOOTFIN", "SBILIFE", "HDFCLIFE",
    ],
    "NIFTY PSU BANK": [
        "SBIN", "BANKBARODA", "PNB", "CANBK",
    ],
    "NIFTY CONSUMER DURABLES": [
        "TITAN", "HAVELLS", "SIEMENS", "ABB",
    ],
    "NIFTY OIL AND GAS": [
        "RELIANCE", "ONGC", "BPCL", "GAIL",
    ],
    "NIFTY HEALTHCARE INDEX": [
        "SUNPHARMA", "CIPLA", "DRREDDY", "DIVISLAB", "APOLLOHOSP",
        "LUPIN", "BIOCON",
    ],
    "NIFTY 50": NIFTY100[:50],
}


def build_universe(universes: list[str]) -> list[str]:
    out: list[str] = []
    if "NIFTY100" in universes:
        out.extend(NIFTY100)
    if "MIDCAP" in universes:
        out.extend(MIDCAP)
    if "SMALLCAP" in universes:
        out.extend(SMALLCAP)
    return list(dict.fromkeys(out))


VALID_UNIVERSES = {"NIFTY100", "MIDCAP", "SMALLCAP"}
