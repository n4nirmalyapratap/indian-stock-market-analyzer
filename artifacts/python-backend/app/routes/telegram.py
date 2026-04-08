"""
Telegram bot routes.
  GET  /api/telegram/status       — bot status + webhook info
  GET  /api/telegram/messages     — message log
  POST /api/telegram/webhook      — Telegram webhook (called by Telegram servers)
  POST /api/telegram/set-webhook  — register webhook URL with Telegram
  POST /api/telegram/test         — send a test message through the bot logic
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from typing import Any

from ..services.telegram_service import TelegramService
from ..services.sectors_service import SectorsService
from ..services.stocks_service import StocksService
from ..services.patterns_service import PatternsService
from ..services.scanners_service import ScannersService
from ..services.nse_service import NseService
from ..services.yahoo_service import YahooService
from ..services.nlp_service import NlpService

router = APIRouter(prefix="/telegram", tags=["telegram"])

_nse      = NseService()
_yahoo    = YahooService()
_nlp      = NlpService()
_sectors  = SectorsService(_nse, _yahoo)
_stocks   = StocksService(_nse, _yahoo)
_patterns = PatternsService(_yahoo, _nse)
_scanners = ScannersService(_yahoo, _nse)
_service  = TelegramService(_sectors, _stocks, _patterns, _scanners, _nlp)


@router.get("/status")
async def get_status():
    status = _service.get_status()
    if _service.configured:
        bot_info = await _service.get_bot_info()
        webhook  = await _service.get_webhook_info()
        status["botInfo"]    = bot_info
        status["webhookInfo"] = webhook
    return status


@router.get("/messages")
async def get_messages():
    return _service.get_message_log()


@router.post("/webhook")
async def telegram_webhook(request: Request):
    """Receives updates from Telegram servers."""
    try:
        update = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})
    try:
        await _service.process_update(update)
    except Exception as e:
        # Always return 200 to Telegram so it doesn't keep retrying
        pass
    return {"ok": True}


@router.post("/set-webhook")
async def set_webhook(body: dict[str, Any]):
    url = (body.get("url") or "").strip()
    if not url:
        return JSONResponse(status_code=400, content={"error": "url field is required"})
    if not url.startswith("https://"):
        return JSONResponse(status_code=400, content={"error": "Webhook URL must start with https://"})
    result = await _service.set_webhook(url)
    return result


@router.post("/test")
async def test_message(body: dict[str, Any]):
    text = (body.get("text") or body.get("message") or "").strip()
    if not text:
        return JSONResponse(status_code=400, content={"error": "text field is required"})
    return await _service.test_message(text)
