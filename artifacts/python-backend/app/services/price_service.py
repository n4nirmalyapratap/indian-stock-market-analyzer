"""
PriceService — single source of truth for historical OHLCV data.

Fetch priority:
  1. Disk cache (when market is closed — near-instant, no network)
  2. NSE India historical API (cookies method — official Indian exchange data)
  3. Yahoo Finance (fallback — global, reliable but secondary)

All callers (scanners, stocks, analytics, warmup) use this service.
Never call yahoo_service.get_historical_data() or nse_service.get_historical_data()
directly — always go through PriceService.
"""

from .nse_service import NseService
from .yahoo_service import YahooService
from . import market_cache_service as _disk


class PriceService:
    def __init__(self, nse: NseService, yahoo: YahooService):
        self.nse   = nse
        self.yahoo = yahoo

    async def get_historical_data(self, symbol: str, days: int = 90) -> list[dict]:
        """
        Returns a list of daily OHLCV dicts sorted oldest → newest:
          { date, open, high, low, close, volume }

        Priority: disk cache → NSE India → Yahoo Finance
        """
        # 1. Disk cache (only when market is closed — data won't change anyway)
        if not _disk.is_market_open():
            disk_data = _disk.load_from_disk(symbol, days)
            if disk_data:
                return disk_data

        # 2. NSE India (primary — official exchange data via cookie method)
        try:
            nse_data = await self.nse.get_historical_data(symbol, days)
            if nse_data and len(nse_data) >= 10:
                _disk.save_to_disk(symbol, days, nse_data)
                return nse_data
        except Exception:
            pass

        # 3. Yahoo Finance (fallback)
        yahoo_data = await self.yahoo.get_historical_data(symbol, days)
        if yahoo_data:
            _disk.save_to_disk(symbol, days, yahoo_data)
        return yahoo_data or []

    async def get_quote(self, symbol: str) -> dict | None:
        """
        Real-time quote — NSE primary, Yahoo fallback.
        (Quotes are always live — no disk cache for these.)
        """
        try:
            nse_quote = await self.nse.get_stock_quote(symbol.upper())
            if nse_quote and nse_quote.get("priceInfo"):
                p    = nse_quote["priceInfo"]
                info = nse_quote.get("info") or nse_quote.get("metadata") or {}
                return {
                    "symbol":      symbol.upper(),
                    "companyName": info.get("companyName", symbol),
                    "industry":    info.get("industry"),
                    "sector":      info.get("sector"),
                    "lastPrice":   p.get("lastPrice"),
                    "change":      p.get("change"),
                    "pChange":     p.get("pChange"),
                    "open":        p.get("open"),
                    "previousClose": p.get("previousClose"),
                    "volume":      p.get("totalTradedVolume"),
                    "source":      "NSE",
                }
        except Exception:
            pass

        return await self.yahoo.get_quote(symbol)
