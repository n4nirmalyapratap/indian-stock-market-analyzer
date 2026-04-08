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


def get_service() -> TelegramService:
    """Return the shared TelegramService instance (used by main.py poller)."""
    return _service


@router.get("/status")
async def get_status():
    status = _service.get_status()
    status["mode"] = "polling"
    if _service.configured:
        bot_info = await _service.get_bot_info()
        status["botInfo"] = bot_info
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


@router.get("/rotation-preview")
async def rotation_preview():
    """Return the pre-formatted sector rotation Telegram message for UI preview."""
    return await _service.get_rotation_message()


@router.post("/send-rotation")
async def send_rotation(body: dict[str, Any]):
    """Send the sector rotation alert to a Telegram chat.
    Body: { "chatId": "<chat_id>" }
    """
    chat_id = body.get("chatId") or body.get("chat_id") or ""
    if not chat_id:
        return JSONResponse(status_code=400, content={"error": "chatId field is required"})
    return await _service.send_rotation_alert(chat_id)
