"""
NLP pipeline for natural language stock market queries.
Uses spaCy's EntityRuler + rule-based intent classification.
"""
from __future__ import annotations
import re
from typing import Optional
import spacy
from spacy.language import Language
from spacy.tokens import Doc

# ── symbol / sector vocabulary ───────────────────────────────────────────────

NIFTY100_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC",
    "SBIN", "BHARTIARTL", "KOTAKBANK", "BAJFINANCE", "AXISBANK", "ASIANPAINT",
    "MARUTI", "HCLTECH", "WIPRO", "TITAN", "NTPC", "SUNPHARMA", "TATAMOTORS",
    "LT", "COALINDIA", "BAJAJ-AUTO", "DIVISLAB", "CIPLA", "DRREDDY", "TECHM",
    "HINDALCO", "ONGC", "POWERGRID", "JSWSTEEL", "INDUSINDBK", "ULTRACEMCO",
    "NESTLEIND", "TATACONSUM", "ADANIPORTS", "SBILIFE", "BRITANNIA", "APOLLOHOSP",
    "BPCL", "TATASTEEL", "ADANIENT", "EICHERMOT", "HEROMOTOCO", "GRASIM",
    "HAVELLS", "SHREECEM", "HDFCLIFE", "DABUR", "PIDILITE", "BAJAJFINSV",
    "SIEMENS", "DLF", "TRENT", "LUPIN", "BIOCON", "IPCALAB", "GAIL",
    "MOTHERSON", "COLPAL", "MUTHOOTFIN", "BERGEPAINT", "GODREJCP", "BOSCHLTD",
    "ABB", "MCDOWELL-N", "AMBUJACEM", "ACCLIMITED", "BANKBARODA", "PNB",
    "CANBK", "IDBI", "FEDERALBNK", "IDFCFIRSTB", "BANDHANBNK", "AUBANK",
    "RBLBANK", "YESBANK", "PERSISTENT", "COFORGE", "MPHASIS", "LTTS",
    "KPITTECH", "TATAELXSI", "CYIENT", "MINDTREE", "MFSL", "IRCTC",
    "ZOMATO", "PAYTM", "NYKAA", "PB", "SULA", "DELHIVERY",
]

SECTOR_ALIASES: dict[str, str] = {
    # canonical name → NSE symbol
    "NIFTY IT": "NIFTY IT",
    "IT": "NIFTY IT",
    "TECH": "NIFTY IT",
    "TECHNOLOGY": "NIFTY IT",
    "INFORMATION TECHNOLOGY": "NIFTY IT",
    "SOFTWARE": "NIFTY IT",
    "NIFTY BANK": "NIFTY BANK",
    "BANK": "NIFTY BANK",
    "BANKING": "NIFTY BANK",
    "BANKEX": "NIFTY BANK",
    "NIFTY AUTO": "NIFTY AUTO",
    "AUTO": "NIFTY AUTO",
    "AUTOMOBILE": "NIFTY AUTO",
    "NIFTY PHARMA": "NIFTY PHARMA",
    "PHARMA": "NIFTY PHARMA",
    "PHARMACEUTICALS": "NIFTY PHARMA",
    "NIFTY FMCG": "NIFTY FMCG",
    "FMCG": "NIFTY FMCG",
    "CONSUMER": "NIFTY FMCG",
    "NIFTY METAL": "NIFTY METAL",
    "METAL": "NIFTY METAL",
    "METALS": "NIFTY METAL",
    "STEEL": "NIFTY METAL",
    "NIFTY REALTY": "NIFTY REALTY",
    "REALTY": "NIFTY REALTY",
    "REAL ESTATE": "NIFTY REALTY",
    "NIFTY ENERGY": "NIFTY ENERGY",
    "ENERGY": "NIFTY ENERGY",
    "OIL": "NIFTY ENERGY",
    "NIFTY MEDIA": "NIFTY MEDIA",
    "MEDIA": "NIFTY MEDIA",
    "NIFTY FINANCIAL SERVICES": "NIFTY FINANCIAL SERVICES",
    "FINANCIAL SERVICES": "NIFTY FINANCIAL SERVICES",
    "NBFC": "NIFTY FINANCIAL SERVICES",
    "NIFTY PSU BANK": "NIFTY PSU BANK",
    "PSU BANK": "NIFTY PSU BANK",
    "PSU": "NIFTY PSU BANK",
    "NIFTY CONSUMER DURABLES": "NIFTY CONSUMER DURABLES",
    "CONSUMER DURABLES": "NIFTY CONSUMER DURABLES",
    "DURABLES": "NIFTY CONSUMER DURABLES",
    "NIFTY OIL AND GAS": "NIFTY OIL AND GAS",
    "OIL AND GAS": "NIFTY OIL AND GAS",
    "OIL & GAS": "NIFTY OIL AND GAS",
    "NIFTY HEALTHCARE INDEX": "NIFTY HEALTHCARE INDEX",
    "HEALTHCARE": "NIFTY HEALTHCARE INDEX",
    "HEALTH": "NIFTY HEALTHCARE INDEX",
    "NIFTY 50": "NIFTY 50",
    "NIFTY": "NIFTY 50",
    "NIFTY50": "NIFTY 50",
}

COMPANY_TO_SYMBOL: dict[str, str] = {
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
    "WIPRO": "WIPRO",
    "TITAN": "TITAN",
    "NTPC": "NTPC",
    "SUN PHARMA": "SUNPHARMA", "SUN PHARMACEUTICAL": "SUNPHARMA",
    "TATA MOTORS": "TATAMOTORS",
    "LARSEN": "LT", "L&T": "LT", "LARSEN AND TOUBRO": "LT",
    "COAL INDIA": "COALINDIA",
    "BAJAJ AUTO": "BAJAJ-AUTO",
    "CIPLA": "CIPLA",
    "DR REDDY": "DRREDDY", "DR. REDDY": "DRREDDY",
    "TECH MAHINDRA": "TECHM",
    "HINDALCO": "HINDALCO",
    "ONGC": "ONGC",
    "POWER GRID": "POWERGRID",
    "JSW STEEL": "JSWSTEEL",
    "INDUSIND BANK": "INDUSINDBK",
    "ULTRA CEMENT": "ULTRACEMCO", "ULTRATECH": "ULTRACEMCO",
    "NESTLE": "NESTLEIND",
    "TATA CONSUMER": "TATACONSUM",
    "ADANI PORTS": "ADANIPORTS",
    "BRITANNIA": "BRITANNIA",
    "APOLLO HOSPITALS": "APOLLOHOSP",
    "BPCL": "BPCL", "BHARAT PETROLEUM": "BPCL",
    "TATA STEEL": "TATASTEEL",
    "ADANI ENTERPRISES": "ADANIENT",
    "EICHER MOTORS": "EICHERMOT",
    "HERO MOTOCORP": "HEROMOTOCO",
    "GRASIM": "GRASIM",
    "HAVELLS": "HAVELLS",
    "SHREE CEMENT": "SHREECEM",
    "HDFC LIFE": "HDFCLIFE",
    "DABUR": "DABUR",
    "PIDILITE": "PIDILITE",
    "SIEMENS": "SIEMENS",
    "DLF": "DLF",
    "TRENT": "TRENT",
    "LUPIN": "LUPIN",
    "GAIL": "GAIL",
    "COLGATE": "COLPAL",
    "BERGEPAINT": "BERGEPAINT", "BERGER PAINTS": "BERGEPAINT",
    "BOSCH": "BOSCHLTD",
    "BANK OF BARODA": "BANKBARODA",
    "PNB": "PNB", "PUNJAB NATIONAL": "PNB",
    "CANARA BANK": "CANBK",
    "FEDERAL BANK": "FEDERALBNK",
    "YES BANK": "YESBANK",
    "IRCTC": "IRCTC",
    "ZOMATO": "ZOMATO",
    "PERSISTENT": "PERSISTENT",
    "COFORGE": "COFORGE",
    "MPHASIS": "MPHASIS",
}

# ── intent definitions ────────────────────────────────────────────────────────

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
        "breadth", "advance decline", "market phase", "bull", "bear",
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
    "oversold": "CALL", "overbought": "PUT", "buy": "CALL", "sell": "PUT",
}


class NlpService:
    def __init__(self) -> None:
        self._nlp: Optional[Language] = None
        self._loaded = False

    def _load(self) -> Language:
        if self._loaded and self._nlp is not None:
            return self._nlp
        nlp = spacy.load("en_core_web_sm", disable=["ner"])
        ruler = nlp.add_pipe("entity_ruler", before="senter")
        patterns = []
        for sym in NIFTY100_SYMBOLS:
            patterns.append({"label": "STOCK", "pattern": sym})
            patterns.append({"label": "STOCK", "pattern": sym.lower()})
            patterns.append({"label": "STOCK", "pattern": sym.capitalize()})
        for alias in SECTOR_ALIASES:
            patterns.append({"label": "SECTOR", "pattern": alias})
            patterns.append({"label": "SECTOR", "pattern": alias.lower()})
            patterns.append({"label": "SECTOR", "pattern": alias.title()})
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
        # Boost stock_analysis if text looks like a single upper-case symbol
        clean = lower.strip()
        if re.match(r"^[a-z0-9&-]{2,15}$", clean) and clean.replace("-", "").isalnum():
            upper = clean.upper()
            if upper in NIFTY100_SYMBOLS or upper in COMPANY_TO_SYMBOL:
                scores["stock_analysis"] += 3.0
        best_intent = max(scores, key=lambda k: scores[k])
        return best_intent if scores[best_intent] > 0 else "stock_analysis"

    def _extract_entities(self, text: str) -> dict:
        nlp = self._load()
        doc = nlp(text)
        stocks: list[str] = []
        sectors: list[str] = []
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
        # Fallback: check upper-cased tokens against symbol list
        if not stocks:
            for token in doc:
                t = token.text.upper()
                if t in NIFTY100_SYMBOLS and t not in stocks:
                    stocks.append(t)
                if t in COMPANY_TO_SYMBOL and COMPANY_TO_SYMBOL[t] not in stocks:
                    stocks.append(COMPANY_TO_SYMBOL[t])
        # Detect bias words (bullish/bearish/call/put)
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
