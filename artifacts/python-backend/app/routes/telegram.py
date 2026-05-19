"""
Telegram bot routes.
  GET  /api/telegram/status       — bot status + webhook info + command registry
  GET  /api/telegram/messages     — message log
  POST /api/telegram/webhook      — Telegram webhook (called by Telegram servers)
  POST /api/telegram/set-webhook  — register webhook URL with Telegram
  POST /api/telegram/test         — preview a reply through the dispatcher
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Any

from ..services.telegram_service import TelegramService
from ..services.sectors_service import SectorsService
from ..services.stocks_service import StocksService
from ..services.patterns_service import PatternsService
from ..services.scanners_service import ScannersService
from ..services.nse_service import NseService
from ..services.yahoo_service import YahooService
from ..services.price_service import PriceService
from ..services.nlp_service import NlpService
from ..services.bot_dispatcher import BotDispatcher
from ..services import news_service as _news_module

router = APIRouter(prefix="/telegram", tags=["telegram"])


def _require_admin(request: Request) -> None:
    """Refuse non-admin callers. set-webhook / send-rotation / test can all
    be abused to hijack the bot or blast messages — admin-only by default."""
    if not bool(getattr(request.state, "is_admin", False)):
        raise HTTPException(status_code=403, detail="Admin privilege required.")


_nse      = NseService()
_yahoo    = YahooService()
_price    = PriceService(_nse, _yahoo)
_nlp      = NlpService()
_sectors  = SectorsService(_nse, _yahoo)
_stocks   = StocksService(_nse, _yahoo)
_patterns = PatternsService(_yahoo, _nse)
_scanners = ScannersService(_price)

# Hydra engine is optional — wrap construction so a failure here doesn't block the bot
try:
    from ..services.hydra_service import HydraEngine
    _hydra = HydraEngine()
except Exception:  # pragma: no cover
    _hydra = None

_dispatcher = BotDispatcher(
    sectors=_sectors, stocks=_stocks, patterns=_patterns, scanners=_scanners,
    nlp=_nlp, hydra=_hydra, news=_news_module,
)
_service = TelegramService(_sectors, _stocks, _patterns, _scanners, _nlp,
                           dispatcher=_dispatcher)


def get_service() -> TelegramService:
    """Return the shared TelegramService instance (used by main.py poller)."""
    return _service


def get_dispatcher() -> BotDispatcher:
    """Shared dispatcher — exposed so the alert tick loop can use it too."""
    return _dispatcher


@router.get("/status")
async def get_status():
    status = _service.get_status()
    status["mode"] = "polling"
    if _service.configured:
        status["botInfo"] = await _service.get_bot_info()
    return status


@router.get("/messages")
async def get_messages():
    return _service.get_message_log()


@router.post("/webhook")
async def telegram_webhook(request: Request):
    # Verify the secret-token header that Telegram echoes back from setWebhook.
    # If TELEGRAM_WEBHOOK_SECRET is unset, we fail closed (403) rather than
    # accept arbitrary updates from any caller — anyone with the public URL
    # could otherwise spoof messages and trigger the bot's logic.
    import os as _os
    expected = _os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    if not expected:
        return JSONResponse(
            status_code=503,
            content={"error": "Telegram webhook is not configured (TELEGRAM_WEBHOOK_SECRET not set)."},
        )
    received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    # Constant-time compare to avoid token-leak via timing.
    import hmac as _hmac
    if not _hmac.compare_digest(received, expected):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})
    try:
        update = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})
    try:
        await _service.process_update(update)
    except Exception:
        pass  # always 200 so Telegram doesn't keep retrying
    return {"ok": True}


@router.post("/set-webhook")
async def set_webhook(body: dict[str, Any], request: Request):
    _require_admin(request)
    url = (body.get("url") or "").strip()
    if not url:
        return JSONResponse(status_code=400, content={"error": "url field is required"})
    if not url.startswith("https://"):
        return JSONResponse(status_code=400, content={"error": "Webhook URL must start with https://"})
    return await _service.set_webhook(url)


@router.post("/test")
async def test_message(body: dict[str, Any], request: Request):
    _require_admin(request)
    text = (body.get("text") or body.get("message") or "").strip()
    if not text:
        return JSONResponse(status_code=400, content={"error": "text field is required"})
    return await _service.test_message(text)


@router.get("/rotation-preview")
async def rotation_preview():
    return await _service.get_rotation_message()


@router.post("/send-rotation")
async def send_rotation(body: dict[str, Any], request: Request):
    _require_admin(request)
    chat_id = body.get("chatId") or body.get("chat_id") or ""
    if not chat_id:
        return JSONResponse(status_code=400, content={"error": "chatId field is required"})
    return await _service.send_rotation_alert(chat_id)
