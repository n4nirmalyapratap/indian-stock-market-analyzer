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
    "GRANULES": "GRANULES", "LAURUS": "LAURUSLABS", "LAURUS LABS": "LAURUSLABS",
    "LAURUSLABS": "LAURUSLABS", "SUVEN": "SUVEN",
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

# Multi-word phrase patterns (high weight — 2+ points each)
INTENT_PHRASES: dict[str, list[str]] = {
    "help": [
        "what can you do", "how to use", "what can i ask",
        "show commands", "show menu",
    ],
    "stock_analysis": [
        "tell me about", "stock price", "price of", "performance of",
        "should i buy", "should i sell", "is it good", "worth buying",
        "entry point", "exit point", "buy or sell",
    ],
    "sector_query": [
        "sector performance", "which sector", "banking sector", "it sector",
        "pharma sector", "fmcg sector", "metal sector", "all sectors",
    ],
    "rotation_query": [
        "where to invest", "where to buy", "where should i invest",
        "what to buy", "money flowing", "best sector to invest",
        "outperforming sector", "underperforming sector",
        "market phase", "advance decline", "market breadth",
    ],
    "pattern_scan": [
        "bullish pattern", "bearish pattern", "call signal", "put signal",
        "morning star", "evening star", "candlestick pattern",
    ],
    "scanner_run": [
        "golden cross", "volume spike", "run scanner", "run screen",
        "screen stocks", "filter stocks",
    ],
    "analytics": [
        "top movers", "top gainers", "top losers", "market data",
        "breadth history", "pattern stats",
    ],
}

# Individual word patterns (lower weight — 1 point each)
INTENT_WORDS: dict[str, list[str]] = {
    "help": ["help", "commands", "guide", "menu", "instructions"],
    "stock_analysis": [
        "analyze", "analysis", "technical", "fundamental",
        "chart", "trend", "rsi", "macd", "ema", "recommendation",
    ],
    "sector_query": ["sector", "sectors", "index", "industry", "nifty"],
    "rotation_query": [
        "invest", "investment", "rotation", "focus",
        "outperform", "outperforming", "underperform",
        "opportunity", "opportunities",
    ],
    "pattern_scan": [
        "pattern", "patterns", "candlestick", "signal", "signals",
        "bullish", "bearish", "hammer", "doji", "engulfing", "detect",
    ],
    "scanner_run": [
        "scanner", "screen", "screener", "filter",
        "breakout", "oversold", "momentum",
    ],
    "analytics": [
        "heatmap", "gainers", "losers", "movers",
        "correlation", "analytics", "statistics",
    ],
}

SIGNAL_WORDS = {
    "bullish": "CALL", "bearish": "PUT", "call": "CALL", "put": "PUT",
    "oversold": "CALL", "overbought": "PUT",
    "buy": "CALL", "positive": "CALL", "uptrend": "CALL", "gaining": "CALL",
    "sell": "PUT", "negative": "PUT", "downtrend": "PUT", "falling": "PUT",
    "green": "CALL", "red": "PUT",
}

# Fuzzy variants for common typos → canonical signal word
_SIGNAL_FUZZY: dict[str, str] = {
    "bulish": "bullish", "bullsh": "bullish", "bullsih": "bullish", "bulllish": "bullish",
    "bulsih": "bullish", "bullissh": "bullish", "builsh": "bullish",
    "bearsih": "bearish", "bearsh": "bearish", "beerish": "bearish", "bearissh": "bearish",
    "bearich": "bearish", "bearsish": "bearish",
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
        all_intents = set(INTENT_PHRASES) | set(INTENT_WORDS)
        scores: dict[str, float] = {intent: 0.0 for intent in all_intents}

        # Pass 1: multi-word phrase matching (2.0 pts + 0.5 per extra word)
        for intent, phrases in INTENT_PHRASES.items():
            for phrase in phrases:
                if phrase in lower:
                    scores[intent] += 2.0 + (len(phrase.split()) - 1) * 0.5

        # Pass 2: individual word matching (1.0 pt each, word-boundary aware)
        words_in_text = set(re.findall(r"\b\w+\b", lower))
        for intent, words in INTENT_WORDS.items():
            for word in words:
                if word in words_in_text:
                    scores[intent] += 1.0

        # Boost: single token that IS a known NSE symbol → stock_analysis
        clean = lower.strip()
        upper = clean.upper()
        if re.match(r"^[a-z0-9&-]{2,15}$", clean):
            if upper in _ALL_SYMBOLS_SET or upper in COMPANY_TO_SYMBOL:
                scores["stock_analysis"] += 3.0

        best_intent = max(scores, key=lambda k: scores[k])
        return best_intent if scores[best_intent] > 0 else "rotation_query"

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
        words_in_text = set(re.findall(r"\b\w+\b", lower))

        # Exact signal word match
        for word, sig in SIGNAL_WORDS.items():
            if word in words_in_text:
                signal = sig
                break

        # Fuzzy typo correction ("bulish" → "bullish" → CALL)
        if signal is None:
            for word in words_in_text:
                canonical = _SIGNAL_FUZZY.get(word)
                if canonical:
                    signal = SIGNAL_WORDS.get(canonical)
                    break

        # difflib fallback for unknown typos (cutoff 0.82 to avoid false positives)
        if signal is None:
            from difflib import get_close_matches
            signal_keys = list(SIGNAL_WORDS.keys())
            for word in words_in_text:
                if len(word) >= 4:
                    matches = get_close_matches(word, signal_keys, n=1, cutoff=0.82)
                    if matches:
                        signal = SIGNAL_WORDS[matches[0]]
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
