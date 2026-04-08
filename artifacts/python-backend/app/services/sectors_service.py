from datetime import datetime
from .nse_service import NseService
from .yahoo_service import YahooService

SECTOR_INDICES = [
    {"name": "NIFTY 50",               "symbol": "NIFTY 50",               "category": "Broad Market",         "nseKey": "NIFTY 50"},
    {"name": "Nifty Bank",             "symbol": "NIFTY BANK",             "category": "Banking & Finance",    "nseKey": "NIFTY BANK"},
    {"name": "Nifty IT",               "symbol": "NIFTY IT",               "category": "Technology",           "nseKey": "NIFTY IT"},
    {"name": "Nifty Auto",             "symbol": "NIFTY AUTO",             "category": "Automobile",           "nseKey": "NIFTY AUTO"},
    {"name": "Nifty Pharma",           "symbol": "NIFTY PHARMA",           "category": "Pharmaceuticals",      "nseKey": "NIFTY PHARMA"},
    {"name": "Nifty FMCG",            "symbol": "NIFTY FMCG",            "category": "FMCG",                 "nseKey": "NIFTY FMCG"},
    {"name": "Nifty Metal",            "symbol": "NIFTY METAL",            "category": "Metals & Mining",      "nseKey": "NIFTY METAL"},
    {"name": "Nifty Realty",           "symbol": "NIFTY REALTY",           "category": "Real Estate",          "nseKey": "NIFTY REALTY"},
    {"name": "Nifty Energy",           "symbol": "NIFTY ENERGY",           "category": "Energy & Oil",         "nseKey": "NIFTY ENERGY"},
    {"name": "Nifty Media",            "symbol": "NIFTY MEDIA",            "category": "Media & Entertainment","nseKey": "NIFTY MEDIA"},
    {"name": "Nifty Financial Services","symbol": "NIFTY FINANCIAL SERVICES","category": "Financial Services","nseKey": "NIFTY FINANCIAL SERVICES"},
    {"name": "Nifty PSU Bank",         "symbol": "NIFTY PSU BANK",         "category": "PSU Banking",          "nseKey": "NIFTY PSU BANK"},
    {"name": "Nifty Consumer Durables","symbol": "NIFTY CONSUMER DURABLES","category": "Consumer Durables",   "nseKey": "NIFTY CONSUMER DURABLES"},
    {"name": "Nifty Oil & Gas",        "symbol": "NIFTY OIL AND GAS",      "category": "Oil & Gas",            "nseKey": "NIFTY OIL AND GAS"},
    {"name": "Nifty Healthcare",       "symbol": "NIFTY HEALTHCARE INDEX", "category": "Healthcare",           "nseKey": "NIFTY HEALTHCARE INDEX"},
]


class SectorsService:
    def __init__(self, nse: NseService, yahoo: YahooService):
        self.nse = nse
        self.yahoo = yahoo

    async def get_all_sectors(self) -> list[dict]:
        try:
            nse_data = await self.nse.get_sector_indices()
            if nse_data and nse_data.get("data"):
                parsed = self._parse_nse_sectors(nse_data["data"])
                if parsed:
                    return parsed
        except Exception:
            pass
        return self._get_default_sectors()

    def _parse_nse_sectors(self, data: list[dict]) -> list[dict]:
        results = []
        for sector in SECTOR_INDICES:
            found = next(
                (d for d in data if d.get("index") == sector["nseKey"] or d.get("indexSymbol") == sector["symbol"]),
                None,
            )
            if found:
                p_change = float(found.get("percentChange") or found.get("perChange") or 0)
                results.append({
                    "name": sector["name"],
                    "symbol": sector["symbol"],
                    "category": sector["category"],
                    "lastPrice": found.get("last") or found.get("indexValue") or 0,
                    "change": found.get("variation") or found.get("change") or 0,
                    "pChange": p_change,
                    "open": found.get("open"),
                    "high": found.get("high"),
                    "low": found.get("low"),
                    "previousClose": found.get("previousClose"),
                    "yearHigh": found.get("yearHigh"),
                    "yearLow": found.get("yearLow"),
                    "advances": found.get("advances"),
                    "declines": found.get("declines"),
                    "momentum": 5 if p_change > 3 else 4 if p_change > 1.5 else 3 if p_change > 0 else 2 if p_change > -1.5 else 1,
                    "focus": "BUY" if p_change > 1 else "HOLD" if p_change > -1 else "AVOID",
                    "source": "NSE",
                })
        if not results:
            return []
        return sorted(results, key=lambda s: s["pChange"], reverse=True)

    def _get_default_sectors(self) -> list[dict]:
        return [
            {
                "name": s["name"], "symbol": s["symbol"], "category": s["category"],
                "lastPrice": 0, "change": 0, "pChange": 0,
                "momentum": 3, "focus": "HOLD", "source": "UNAVAILABLE",
            }
            for s in SECTOR_INDICES
        ]

    async def get_sector_rotation(self) -> dict:
        sectors = await self.get_all_sectors()
        sorted_sectors = sorted(sectors, key=lambda s: s["pChange"], reverse=True)
        advancing = sum(1 for s in sectors if s["pChange"] > 0)
        declining = sum(1 for s in sectors if s["pChange"] < 0)
        avg_p = sum(s.get("pChange") or 0 for s in sectors) / len(sectors) if sectors else 0
        if avg_p > 1.5:
            phase = "Bull Run - All sectors rising"
        elif avg_p > 0:
            phase = "Recovery Phase - Select sectors leading"
        elif avg_p > -1.5:
            phase = "Consolidation - Defensive sectors preferred"
        else:
            phase = "Bear Phase - Risk-off mode"
        top3_names = [s["name"] for s in sorted_sectors[:3]]
        return {
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "sectors": sectors,
            "topPerformers": sorted_sectors[:5],
            "laggards": sorted_sectors[-3:],
            "currentlyFocused": top3_names,
            "whereToBuyNow": [s for s in sorted_sectors if s.get("focus") == "BUY"][:5],
            "marketBreadth": {
                "advancing": advancing,
                "declining": declining,
                "unchanged": len(sectors) - advancing - declining,
                "total": len(sectors),
                "advanceDeclineRatio": advancing if declining == 0 else round(advancing / declining, 2),
                "breadthScore": f"{(advancing / len(sectors) * 100):.1f}" if sectors else "0",
            },
            "rotationPhase": phase,
            "recommendation": f"Focus on {', '.join(top3_names)}. Sector rotation favoring these indices.",
        }

    async def get_sector_detail(self, symbol: str) -> dict | None:
        sectors = await self.get_all_sectors()
        return next(
            (s for s in sectors if s["symbol"] == symbol or s["name"].lower() == symbol.lower()),
            None,
        )
