"""
NLP query endpoint — accepts plain-English questions and routes to appropriate services.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from typing import Any

from ..services.nlp_service import NlpService
from ..services.stocks_service import StocksService
from ..services.sectors_service import SectorsService
from ..services.patterns_service import PatternsService
from ..services.scanners_service import ScannersService
from ..services.nse_service import NseService
from ..services.yahoo_service import YahooService
from ..services.price_service import PriceService
from ..lib.universe import SECTOR_SYMBOLS

router = APIRouter(prefix="/nlp", tags=["nlp"])

_nse      = NseService()
_yahoo    = YahooService()
_price    = PriceService(_nse, _yahoo)
_nlp      = NlpService()
_stocks   = StocksService(_nse, _yahoo)
_sectors  = SectorsService(_nse, _yahoo)
_patterns = PatternsService(_yahoo, _nse)
_scanners = ScannersService(_price)


@router.post("/query")
async def nlp_query(body: dict[str, Any]):
    text = (body.get("query") or body.get("text") or body.get("message") or "").strip()
    if not text:
        return JSONResponse(status_code=400, content={"error": "query field is required"})

    # Guard NLP parsing — OSError if spaCy model missing, etc.
    try:
        parsed = _nlp.parse(text)
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": f"NLP parsing failed: {exc}. Please try again later."},
        )

    intent = parsed["intent"]
    stocks  = parsed["stocks"]
    sectors = parsed["sectors"]
    signal  = parsed["signal"]

    result: dict[str, Any] = {
        "query":  text,
        "parsed": parsed,
        "intent": intent,
        "data":   None,
    }

    try:
        if intent == "help":
            result["data"] = {
                "message": (
                    "I can help you with:\n"
                    "• Stock analysis — 'Analyze RELIANCE' or 'How is TCS doing?'\n"
                    "• Sector queries — 'Show me IT sector' or 'Which sectors are up?'\n"
                    "• Sector rotation — 'Where to invest today?' or 'What is outperforming?'\n"
                    "• Chart patterns — 'Show bullish patterns' or 'Any CALL signals?'\n"
                    "• Custom scanners — 'Run golden cross scanner' or 'Show momentum stocks'\n"
                    "• Analytics — 'Sector correlation' or 'Top gainers today'"
                )
            }

        elif intent == "stock_analysis":
            if stocks:
                details = await _stocks.get_stock_details(stocks[0])
                result["data"] = details
                result["resolvedSymbol"] = stocks[0]
                if len(stocks) > 1:
                    result["otherSymbols"] = stocks[1:]
            else:
                nifty100 = await _stocks.get_nifty100_stocks()
                result["data"] = nifty100[:20]
                result["message"] = "No specific stock symbol detected. Showing Nifty 100 overview."

        elif intent == "sector_query":
            if sectors:
                sector_data = await _sectors.get_sector_detail(sectors[0])
                result["data"] = sector_data
                result["resolvedSector"] = sectors[0]
            else:
                all_sectors = await _sectors.get_all_sectors()
                if signal == "CALL":
                    result["data"] = [s for s in all_sectors if s.get("pChange", 0) > 0]
                    result["message"] = "Sectors with positive performance today"
                elif signal == "PUT":
                    result["data"] = [s for s in all_sectors if s.get("pChange", 0) < 0]
                    result["message"] = "Sectors with negative performance today"
                else:
                    result["data"] = all_sectors

        elif intent == "rotation_query":
            rotation = await _sectors.get_sector_rotation()
            result["data"] = rotation

        elif intent == "pattern_scan":
            patterns_result = await _patterns.get_patterns(signal=signal)
            patterns_list   = patterns_result.get("patterns", [])

            if sectors:
                # Build the set of stock symbols that belong to the requested sectors
                sector_syms: set[str] = set()
                for sec in sectors:
                    sector_syms.update(SECTOR_SYMBOLS.get(sec, []))
                if sector_syms:
                    filtered = [p for p in patterns_list if p.get("symbol") in sector_syms]
                    # Keep original list if filter removes everything (sector has no detected patterns)
                    patterns_list = filtered if filtered else patterns_list
                    result["resolvedSectors"] = sectors
                    result["sectorSymbolCount"] = len(sector_syms)

            patterns_result["patterns"] = patterns_list
            result["data"] = patterns_result

        elif intent == "scanner_run":
            all_scanners = _scanners.get_all_scanners()
            matched = None
            query_lower = text.lower()
            for sc in all_scanners:
                if any(word in query_lower for word in sc["name"].lower().split()):
                    matched = sc
                    break
            if matched:
                run_result = await _scanners.run_scanner(matched["id"])
                result["data"] = run_result
                result["resolvedScanner"] = matched["name"]
            else:
                result["data"] = all_scanners
                result["message"] = "Listed available scanners. Specify a scanner name to run one."

        elif intent == "analytics":
            all_sectors = await _sectors.get_all_sectors()
            result["data"] = {
                "sectors": all_sectors,
                "message": (
                    "Use /api/analytics/sector-correlation, /api/analytics/top-movers, "
                    "/api/analytics/sector-heatmap, /api/analytics/breadth-history, "
                    "or /api/analytics/pattern-stats for full analytics."
                ),
            }

        else:
            result["data"] = {"message": f"Query understood as '{intent}'. No specific data found."}

    except Exception as e:
        result["error"] = f"Error processing query: {e}"

    return result
