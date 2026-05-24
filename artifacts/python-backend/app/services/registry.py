"""
Service Registry
================
Single shared instances of every core service used by route handlers.

All route files should import from here instead of creating their own instances:

    from ..services import registry as svc
    # then use: svc.sectors, svc.yahoo, svc.stocks, etc.

Why: Each instantiation creates a separate httpx client and, for services
whose caches are instance-level, a separate cache. The module-level caches
in YahooService / NseService / SectorsService are already singletons via
Python's import machinery, but multiple instances is confusing, wastes
memory, and hides the real dependency graph.

Exceptions (intentionally NOT in this registry):
  - admin.py     : creates services per-request (admin needs fresh state)
  - jobs.py      : creates services per background job (isolated context)
  - email_digest : lazy-initialised because the feature may be disabled
  - BotDispatcher / TelegramService / WhatsappService : bot-specific wiring
"""

from .nse_service            import NseService
from .yahoo_service          import YahooService
from .price_service          import PriceService
from .sectors_service        import SectorsService
from .sector_analytics_service import SectorAnalyticsService
from .stocks_service         import StocksService
from .patterns_service       import PatternsService
from .scanners_service       import ScannersService
from .analytics_service      import AnalyticsService
from .nlp_service            import NlpService

nse:              NseService              = NseService()
yahoo:            YahooService            = YahooService()
price:            PriceService            = PriceService(nse, yahoo)
sectors:          SectorsService          = SectorsService(nse, yahoo)
sector_analytics: SectorAnalyticsService  = SectorAnalyticsService(yahoo, price=price)
stocks:           StocksService           = StocksService(nse, yahoo)
patterns:         PatternsService         = PatternsService(yahoo, nse, price)
scanners:         ScannersService         = ScannersService(price)
analytics:        AnalyticsService        = AnalyticsService(yahoo, nse, sectors, patterns)
nlp:              NlpService              = NlpService()
