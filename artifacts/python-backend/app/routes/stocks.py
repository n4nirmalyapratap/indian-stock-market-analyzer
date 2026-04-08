from fastapi import APIRouter
from ..services.stocks_service import StocksService
from ..services.nse_service import NseService
from ..services.yahoo_service import YahooService

router = APIRouter(prefix="/stocks", tags=["stocks"])

_nse = NseService()
_yahoo = YahooService()
_service = StocksService(_nse, _yahoo)


@router.get("/nifty100")
async def get_nifty100():
    return await _service.get_nifty100_stocks()


@router.get("/midcap")
async def get_midcap():
    return await _service.get_midcap_stocks()


@router.get("/smallcap")
async def get_smallcap():
    return await _service.get_smallcap_stocks()


@router.get("/{symbol}")
async def get_stock(symbol: str):
    return await _service.get_stock_details(symbol)
