NIFTY100 = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC", "SBIN",
    "BHARTIARTL", "KOTAKBANK", "BAJFINANCE", "AXISBANK", "ASIANPAINT", "MARUTI", "HCLTECH",
    "WIPRO", "TITAN", "NTPC", "SUNPHARMA", "TATAMOTORS", "LT", "COALINDIA", "BAJAJ-AUTO",
    "DIVISLAB", "CIPLA", "DRREDDY", "TECHM", "HINDALCO",
]

MIDCAP = [
    "PERSISTENT", "COFORGE", "MPHASIS", "LTTS", "KPITTECH",
    "METROPOLIS", "IEX", "CAMS", "CDSL", "IRCTC",
]

SMALLCAP = [
    "TATAELXSI", "CYIENT", "MASTEK", "BIRLASOFT", "INFOEDGE",
]


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
