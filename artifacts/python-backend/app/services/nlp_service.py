"""
NLP pipeline for natural language stock market queries.
Uses spaCy EntityRuler + rule-based intent classification.
Covers Nifty100, Midcap 150, Smallcap 250, Microcap stocks.
"""
from __future__ import annotations
import re
from typing import Optional
import spacy
from spacy.language import Language

from ..lib.universe import ALL_SYMBOLS, NIFTY100, MIDCAP, SMALLCAP, MICROCAP

# Quick lookup set for O(1) membership tests
_ALL_SYMBOLS_SET: set[str] = set(ALL_SYMBOLS)

# ── Sector aliases ────────────────────────────────────────────────────────────
SECTOR_ALIASES: dict[str, str] = {
    "NIFTY IT": "NIFTY IT", "IT": "NIFTY IT", "TECH": "NIFTY IT",
    "TECHNOLOGY": "NIFTY IT", "INFORMATION TECHNOLOGY": "NIFTY IT", "SOFTWARE": "NIFTY IT",
    "NIFTY BANK": "NIFTY BANK", "BANK": "NIFTY BANK", "BANKING": "NIFTY BANK", "BANKEX": "NIFTY BANK",
    "NIFTY AUTO": "NIFTY AUTO", "AUTO": "NIFTY AUTO", "AUTOMOBILE": "NIFTY AUTO",
    "NIFTY PHARMA": "NIFTY PHARMA", "PHARMA": "NIFTY PHARMA", "PHARMACEUTICALS": "NIFTY PHARMA",
    "NIFTY FMCG": "NIFTY FMCG", "FMCG": "NIFTY FMCG", "CONSUMER": "NIFTY FMCG",
    "NIFTY METAL": "NIFTY METAL", "METAL": "NIFTY METAL", "METALS": "NIFTY METAL", "STEEL": "NIFTY METAL",
    "NIFTY REALTY": "NIFTY REALTY", "REALTY": "NIFTY REALTY", "REAL ESTATE": "NIFTY REALTY",
    "NIFTY ENERGY": "NIFTY ENERGY", "ENERGY": "NIFTY ENERGY", "OIL": "NIFTY ENERGY",
    "NIFTY MEDIA": "NIFTY MEDIA", "MEDIA": "NIFTY MEDIA",
    "NIFTY FINANCIAL SERVICES": "NIFTY FINANCIAL SERVICES",
    "FINANCIAL SERVICES": "NIFTY FINANCIAL SERVICES", "NBFC": "NIFTY FINANCIAL SERVICES",
    "FINTECH": "NIFTY FINANCIAL SERVICES",
    "NIFTY PSU BANK": "NIFTY PSU BANK", "PSU BANK": "NIFTY PSU BANK", "PSU": "NIFTY PSU BANK",
    "NIFTY CONSUMER DURABLES": "NIFTY CONSUMER DURABLES",
    "CONSUMER DURABLES": "NIFTY CONSUMER DURABLES", "DURABLES": "NIFTY CONSUMER DURABLES",
    "NIFTY OIL AND GAS": "NIFTY OIL AND GAS", "OIL AND GAS": "NIFTY OIL AND GAS",
    "OIL & GAS": "NIFTY OIL AND GAS",
    "NIFTY HEALTHCARE INDEX": "NIFTY HEALTHCARE INDEX",
    "HEALTHCARE": "NIFTY HEALTHCARE INDEX", "HEALTH": "NIFTY HEALTHCARE INDEX",
    "NIFTY INFRASTRUCTURE": "NIFTY INFRASTRUCTURE",
    "INFRASTRUCTURE": "NIFTY INFRASTRUCTURE", "INFRA": "NIFTY INFRASTRUCTURE",
    "NIFTY CHEMICALS": "NIFTY CHEMICALS", "CHEMICAL": "NIFTY CHEMICALS", "CHEMICALS": "NIFTY CHEMICALS",
    "NIFTY CEMENT": "NIFTY CEMENT", "CEMENT": "NIFTY CEMENT",
    "NIFTY DEFENCE": "NIFTY DEFENCE", "DEFENCE": "NIFTY DEFENCE", "DEFENSE": "NIFTY DEFENCE",
    "NIFTY 50": "NIFTY 50", "NIFTY": "NIFTY 50", "NIFTY50": "NIFTY 50",
}

# ── Company name → NSE symbol mapping (large + mid + small + micro) ───────────
COMPANY_TO_SYMBOL: dict[str, str] = {
    # Large cap
    "RELIANCE": "RELIANCE", "RELIANCE INDUSTRIES": "RELIANCE",
    "TCS": "TCS", "TATA CONSULTANCY": "TCS", "TATA CONSULTANCY SERVICES": "TCS",
    "INFOSYS": "INFY", "INFY": "INFY",
    "HDFC BANK": "HDFCBANK", "HDFCBANK": "HDFCBANK",
    "ICICI BANK": "ICICIBANK", "ICICIBANK": "ICICIBANK",
    "HINDUSTAN UNILEVER": "HINDUNILVR", "HUL": "HINDUNILVR", "HINDUNILVR": "HINDUNILVR",
    "ITC": "ITC",
    "SBI": "SBIN", "STATE BANK": "SBIN", "STATE BANK OF INDIA": "SBIN",
    "AIRTEL": "BHARTIARTL", "BHARTI AIRTEL": "BHARTIARTL",
    "KOTAK BANK": "KOTAKBANK", "KOTAK MAHINDRA": "KOTAKBANK",
    "BAJAJ FINANCE": "BAJFINANCE",
    "AXIS BANK": "AXISBANK",
    "ASIAN PAINTS": "ASIANPAINT",
    "MARUTI": "MARUTI", "MARUTI SUZUKI": "MARUTI",
    "HCL TECH": "HCLTECH", "HCL TECHNOLOGIES": "HCLTECH",
    "WIPRO": "WIPRO", "TITAN": "TITAN", "NTPC": "NTPC",
    "SUN PHARMA": "SUNPHARMA", "SUN PHARMACEUTICAL": "SUNPHARMA",
    "TATA MOTORS": "TATAMOTORS",
    "LARSEN": "LT", "L&T": "LT", "LARSEN AND TOUBRO": "LT",
    "COAL INDIA": "COALINDIA",
    "BAJAJ AUTO": "BAJAJ-AUTO",
    "CIPLA": "CIPLA", "DR REDDY": "DRREDDY", "DR. REDDY": "DRREDDY",
    "TECH MAHINDRA": "TECHM", "HINDALCO": "HINDALCO", "ONGC": "ONGC",
    "POWER GRID": "POWERGRID", "JSW STEEL": "JSWSTEEL",
    "INDUSIND BANK": "INDUSINDBK", "ULTRA CEMENT": "ULTRACEMCO", "ULTRATECH": "ULTRACEMCO",
    "NESTLE": "NESTLEIND", "TATA CONSUMER": "TATACONSUM", "ADANI PORTS": "ADANIPORTS",
    "BRITANNIA": "BRITANNIA", "APOLLO HOSPITALS": "APOLLOHOSP",
    "BPCL": "BPCL", "BHARAT PETROLEUM": "BPCL", "TATA STEEL": "TATASTEEL",
    "ADANI ENTERPRISES": "ADANIENT", "EICHER MOTORS": "EICHERMOT",
    "HERO MOTOCORP": "HEROMOTOCO", "GRASIM": "GRASIM", "HAVELLS": "HAVELLS",
    "SHREE CEMENT": "SHREECEM", "HDFC LIFE": "HDFCLIFE",
    "DABUR": "DABUR", "PIDILITE": "PIDILITE", "SIEMENS": "SIEMENS", "DLF": "DLF",
    "TRENT": "TRENT", "LUPIN": "LUPIN", "GAIL": "GAIL",
    "COLGATE": "COLPAL", "BANK OF BARODA": "BANKBARODA",
    "PNB": "PNB", "PUNJAB NATIONAL": "PNB", "CANARA BANK": "CANBK",
    "FEDERAL BANK": "FEDERALBNK", "YES BANK": "YESBANK",
    "IRCTC": "IRCTC", "ZOMATO": "ZOMATO",
    "PERSISTENT": "PERSISTENT", "COFORGE": "COFORGE", "MPHASIS": "MPHASIS",
    "LIC": "LICI", "LIFE INSURANCE CORPORATION": "LICI",
    "ADANI GREEN": "ADANIGREEN", "ADANI TRANSMISSION": "ADANITRANS",
    "ADANI POWER": "ADANIPOWER", "DMART": "DMART", "AVENUE SUPERMARTS": "DMART",
    "NYKAA": "NYKAA", "FSN ECOMMERCE": "NYKAA",
    "PAYTM": "PAYTM", "ONE97": "PAYTM",
    "POLICY BAZAAR": "POLICYBZR", "MARICO": "MARICO",
    "MAX HEALTHCARE": "MAXHEALTH", "FORTIS": "FORTIS",
    "VOLTAS": "VOLTAS", "CONCOR": "CONCOR",
    "CHOLA": "CHOLAFIN", "CHOLAMANDALAM": "CHOLAFIN",
    "GODREJ PROPERTIES": "GODREJPROP", "OBEROI REALTY": "OBEROIRLTY",
    "PRESTIGE ESTATES": "PRESTIGE",
    # Mid cap
    "AUROBINDO": "AUROPHARMA", "BALKRISHNA": "BALKRISIND", "PAGE INDUSTRIES": "PAGEIND",
    "TORRENT PHARMA": "TORNTPHARM", "PI INDUSTRIES": "PIIND",
    "L&T FINANCE": "LTFH", "LTFH": "LTFH",
    "MRF": "MRF", "POLYCAB": "POLYCAB", "AMBUJA CEMENT": "AMBUJACEM",
    "GLENMARK": "GLENMARK", "ESCORTS": "ESCORTS", "ZYDUS": "ZYDUSLIFE",
    "ALKEM": "ALKEM", "EMAMI": "EMAMI", "JYOTHY": "JYOTHYLAB",
    "NATIONAL ALUMINIUM": "NATIONALUM", "SUZLON": "SUZLON",
    "NHPC": "NHPC", "SJVN": "SJVN", "RVNL": "RVNL", "IRCON": "IRCON",
    "TATA COMMUNICATIONS": "TATACOMM",
    "UNITED SPIRITS": "MCDOWELL-N", "RADICO": "RADICO",
    "JUBILANT FOODWORKS": "JUBLFOOD", "DEVYANI": "DEVYANI",
    "WESTLIFE": "WESTLIFE", "CRISIL": "CRISIL",
    "ICICI PRUDENTIAL": "ICICIPRULI",
    "CAN FIN HOMES": "CANFINHOME", "MANAPPURAM": "MANAPPURAM",
    "SHRIRAM FINANCE": "SHRIRAMFIN",
    "ADITYA BIRLA FASHION": "ABFRL", "RELAXO": "RELAXO",
    "BATA": "BATA", "RAYMOND": "RAYMOND", "V-GUARD": "VGUARD",
    "KANSAI NEROLAC": "KANSAINER", "AKZO NOBEL": "AKZOINDIA",
    "BLUE STAR": "BLUESTARCO", "KAJARIA": "KAJARIACER",
    "SUNDARAM FINANCE": "SUNDARMFIN", "LINDEINDIA": "LINDEINDIA",
    "SOLAR INDUSTRIES": "SOLARINDS", "WHIRLPOOL": "WHIRLPOOL",
    "METROPOLIS": "METROPOLIS", "IEX": "IEX", "CAMS": "CAMS", "CDSL": "CDSL",
    "INFO EDGE": "NAUKRI", "NAUKRI": "NAUKRI", "ASTRAL": "ASTRAL",
    "DEEPAK NITRITE": "DEEPAKNTR", "CROMPTON": "CROMPTON",
    "HAPPIEST MINDS": "HAPPSTMNDS", "AAVAS": "AAVAS", "HFCL": "HFCL",
    "OLECTRA": "OLECTRA", "AMBER ENTERPRISES": "AMBER",
    "DIXON TECHNOLOGIES": "DIXON", "SAFARI": "SAFARI", "V-MART": "VMART",
    "TANLA": "TANLA", "ROUTE MOBILE": "ROUTE", "NAZARA": "NAZARA",
    "LATENT VIEW": "LATENTVIEW", "MASTEK": "MASTEK",
    "BIRLASOFT": "BIRLASOFT", "XCHANGING": "XCHANGING",
    "APTUS": "APTUS", "HOME FIRST": "HOMEFIRST",
    "CREDIT ACCESS": "CREDITACC", "ARMAN": "ARMANFIN", "SPANDANA": "SPANDANA",
    "UJJIVAN": "UJJIVANSFB", "EQUITAS": "EQUITASBNK",
    "KARUR VYSYA": "KARURVYSYA", "DCB BANK": "DCBBANK",
    "SOUTH INDIAN BANK": "SOUTHBANK", "CSB BANK": "CSBBANK",
    "NUVOCO": "NUVOCO", "HEIDELBERG": "HEIDELBERG",
    "BIRLA CORP": "BIRLACORPN", "ORIENT CEMENT": "ORIENTCEM",
    "STAR CEMENT": "STARCEMENT", "JK CEMENT": "JKCEMENT", "RAMCO": "RAMCOCEM",
    "GPIL": "GPIL", "NMDC": "NMDC", "SAIL": "SAIL",
    "WELSPUN": "WELSPUNLIV", "TRIDENT": "TRIDENT", "VARDHMAN": "VARDHMAN",
    "BALRAMPUR CHINI": "BALRAMCHIN", "RENUKA": "RENUKA", "TRIVENI": "TRIVENI",
    "DHANUKA": "DHANUKA", "RALLIS": "RALLIS", "PRAJ": "PRAJIND",
    "GRANULES": "GRANULES", "LAURUS": "LAURUS", "SUVEN": "SUVEN",
    "JB CHEMICALS": "JBCHEPHARM", "SEQUENT": "SEQUENT",
    "KALYAN JEWELLERS": "KALYAN", "SENCO": "SENCO",
    "IIFL": "IIFL", "360 ONE": "360ONE", "ANAND RATHI": "ANANDRAT",
    "INDIABULLS": "INDOSTAR", "PC JEWELLER": "PCJEWELLER",
    "THANGAMAYIL": "THANGAMAYL", "WAAREE": "WAAREEENER",
    "INOX WIND": "INOXWIND",
    # Small cap
    "AARTHI": "AARTIIND", "AARTI": "AARTIIND", "FINE ORGANICS": "FINEORG",
    "SUDARSHANAM": "SUDARSCHEM", "RAILTEL": "RAILTEL", "IREDA": "IREDA",
    "REC": "RECLTD", "PFC": "PFC", "HUDCO": "HUDCO",
    "IRFC": "IRFC", "HINDZINC": "HINDZINC", "VEDANTA": "VEDL",
    "MOIL": "MOIL", "GMR": "GMRINFRA", "IRB": "IRB", "ASHOKA": "ASHOKA",
    "PNBHOUSING": "PNBHOUSING",
    "UCO BANK": "UCOBANK", "IOB": "IOB", "CENTRAL BANK": "CENTRALBNK",
    "MAHARASHTRA BANK": "MAHABANK", "J&K BANK": "JKBANK",
    "SURYODAY": "SURYODAY", "UTKARSH": "UTKARSHBNK",
    "IIFL WEALTH": "IIFLWAM", "MOTILAL": "MOTILALOS",
    "5PAISA": "5PAISA", "ANGEL ONE": "ANGELONE", "GEOJIT": "GEOJIT",
    "JM FINANCIAL": "JMFINANCIL",
    "CERA": "CERA", "SOMANY": "SOMANYCER", "ORIENT BELL": "ORIENTBELL",
    "FIEM": "FIEMIND", "SUBROS": "SUBROS", "SUPRAJIT": "SUPRAJIT",
    "THERMAX": "THERMAX", "BHEL": "BHEL", "BEL": "BEL",
    "HAL": "HAL", "HINDUSTAN AERONAUTICS": "HAL",
    "BEML": "BEML", "COCHIN SHIPYARD": "COCHINSHIP", "GRSE": "GRSE",
    "HONASA": "HONASA", "MAMAEARTH": "MAMAEARTH",
    "SWIGGY": "SWIGGY",
    "LATENTVIEW": "LATENTVIEW", "DATAMATICS": "DATAMATICS",
    "INTELLECT": "INTELLECT", "NEWGEN": "NEWGEN", "NUCLEUS SOFTWARE": "NUCLEUS",
    "NEULAND": "NEULANDLAB", "MARKSANS": "MARKSANS",
    "SHILPA MEDICARE": "SHILPAMED",
    "KRBL": "KRBL", "AVANTI FEEDS": "AVANTIFEED",
    "SUMITOMO CHEMICAL": "SUMITCHEM", "BAYER": "BAYER",
    # Micro cap
    "IDEAFORGE": "IDEAFORGE", "DRONE ACHARYA": "DRONEACHARYA",
    "SANSERA": "SANSERA", "MTAR": "MTAR",
    "STOVEKRAFT": "STOVEKRAFT", "EASY MY TRIP": "EASEMYTRIP",
    "CARTRADE": "CARTRADE", "CHEMPLAST": "CHEMPLAST",
    "TATA INVESTMENT": "TATAINVEST", "TATA TECH": "TATATECH",
    "TATA POWER": "TATAPOWER",
    "KFIN TECHNOLOGIES": "KFINTECH", "MCX": "MCX",
    "GOLDIAM": "GOLDIAM", "RAJESH EXPORTS": "RAJESHEXPO",
    "AJANTA PHARMA": "AJANTPHARM", "IPCA": "IPCA",
    "STRIDES": "STRIDES", "SOLARA": "SOLARA",
    "DEEPAK FERTILISERS": "DEEPAKFERT", "CHAMBAL FERTILISERS": "CHAMBAL",
    "COROMANDEL": "COROMANDEL", "INSECTICIDES": "INSECTICID",
    "HERANBA": "HERANBA", "TATVA CHINTAN": "TATVA",
    "CLEAN SCIENCE": "CLEAN",
    "WELCORP": "WELCORP", "MANALIPETC": "MANALIPETC",
}

INTENT_PATTERNS: dict[str, list[str]] = {
    "help": [
        "help", "commands", "what can you do", "guide", "menu",
        "what can i ask", "how to use", "instructions",
    ],
    "stock_analysis": [
        "analyze", "analysis", "tell me about", "stock price", "price of",
        "how is", "what about", "show me", "check", "performance of",
        "fundamentals", "technical", "chart", "trend", "rsi", "macd",
        "entry", "exit", "buy", "sell", "recommendation",
    ],
    "sector_query": [
        "sector", "sectors", "index", "nifty", "industry",
        "banking sector", "it sector", "pharma sector", "fmcg sector",
        "metal sector", "realty sector", "auto sector", "which sector",
        "sector performance",
    ],
    "rotation_query": [
        "rotation", "focus", "where to invest", "where to buy", "money flowing",
        "outperforming", "underperforming", "best sector", "top sector",
        "breadth", "advance decline", "market phase",
    ],
    "pattern_scan": [
        "pattern", "patterns", "candlestick", "signal", "signals",
        "call signal", "put signal", "bullish pattern", "bearish pattern",
        "hammer", "doji", "engulfing", "morning star", "evening star",
        "scan pattern", "detect",
    ],
    "scanner_run": [
        "scanner", "screen", "screener", "filter", "screen stocks",
        "golden cross", "breakout", "oversold", "momentum", "volume spike",
        "run scanner", "run screen",
    ],
    "analytics": [
        "correlation", "breadth history", "heatmap", "top movers", "gainers",
        "losers", "pattern stats", "statistics", "analytics", "market data",
    ],
}

SIGNAL_WORDS = {
    "bullish": "CALL", "bearish": "PUT", "call": "CALL", "put": "PUT",
    "oversold": "CALL", "overbought": "PUT",
}

# Regex: looks like an NSE symbol — all caps/digits/hyphen, 2-15 chars
_NSE_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9&-]{1,14}$")


def _looks_like_symbol(token: str) -> bool:
    return bool(_NSE_SYMBOL_RE.match(token))


class NlpService:
    def __init__(self) -> None:
        self._nlp: Optional[Language] = None
        self._loaded = False

    def _load(self) -> Language:
        if self._loaded and self._nlp is not None:
            return self._nlp
        nlp = spacy.load("en_core_web_sm", disable=["ner"])
        ruler = nlp.add_pipe("entity_ruler", last=True)
        patterns = []
        # Register every known symbol (all caps)
        for sym in ALL_SYMBOLS:
            patterns.append({"label": "STOCK", "pattern": sym})
            patterns.append({"label": "STOCK", "pattern": sym.lower()})
            patterns.append({"label": "STOCK", "pattern": sym.capitalize()})
        # Register sector aliases
        for alias in SECTOR_ALIASES:
            patterns.append({"label": "SECTOR", "pattern": alias})
            patterns.append({"label": "SECTOR", "pattern": alias.lower()})
            patterns.append({"label": "SECTOR", "pattern": alias.title()})
        # Register company names
        for company in COMPANY_TO_SYMBOL:
            patterns.append({"label": "STOCK", "pattern": company})
            patterns.append({"label": "STOCK", "pattern": company.lower()})
        ruler.add_patterns(patterns)
        self._nlp = nlp
        self._loaded = True
        return nlp

    def _classify_intent(self, text: str) -> str:
        lower = text.lower()
        scores: dict[str, float] = {intent: 0.0 for intent in INTENT_PATTERNS}
        for intent, keywords in INTENT_PATTERNS.items():
            for kw in keywords:
                if kw in lower:
                    scores[intent] += 1.0 + (len(kw.split()) - 1) * 0.5
        # Single-token that looks like an NSE symbol → stock analysis
        clean = lower.strip()
        upper = clean.upper()
        if re.match(r"^[a-z0-9&-]{2,15}$", clean):
            if upper in _ALL_SYMBOLS_SET or upper in COMPANY_TO_SYMBOL:
                scores["stock_analysis"] += 3.0
        best_intent = max(scores, key=lambda k: scores[k])
        return best_intent if scores[best_intent] > 0 else "stock_analysis"

    def _extract_entities(self, text: str) -> dict:
        nlp = self._load()
        doc = nlp(text)
        stocks: list[str] = []
        sectors: list[str] = []

        # 1. spaCy entity ruler hits
        for ent in doc.ents:
            raw = ent.text.upper()
            if ent.label_ == "STOCK":
                sym = COMPANY_TO_SYMBOL.get(raw, raw)
                if sym not in stocks:
                    stocks.append(sym)
            elif ent.label_ == "SECTOR":
                canon = SECTOR_ALIASES.get(raw)
                if canon and canon not in sectors:
                    sectors.append(canon)

        # 2. Token-level fallback — catches symbols entity ruler missed
        if not stocks:
            for token in doc:
                t = token.text.upper()
                if t in _ALL_SYMBOLS_SET and t not in stocks:
                    stocks.append(t)
                elif t in COMPANY_TO_SYMBOL and COMPANY_TO_SYMBOL[t] not in stocks:
                    stocks.append(COMPANY_TO_SYMBOL[t])

        # 3. Regex fallback — accept ANY word that looks like an NSE symbol
        #    (e.g. LAURUS, GPIL, user types an unlisted mid/micro cap)
        if not stocks:
            for token in doc:
                t = token.text
                if _looks_like_symbol(t) and t not in stocks:
                    stocks.append(t)

        signal = None
        lower = text.lower()
        for word, sig in SIGNAL_WORDS.items():
            if word in lower:
                signal = sig
                break
        return {"stocks": stocks, "sectors": sectors, "signal": signal}

    def parse(self, text: str) -> dict:
        intent = self._classify_intent(text)
        entities = self._extract_entities(text)
        return {
            "intent": intent,
            "stocks": entities["stocks"],
            "sectors": entities["sectors"],
            "signal": entities["signal"],
            "originalText": text,
        }
