import hmac
import hashlib
import base64
import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from typing import Any

from ..services.whatsapp_service import WhatsappService
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

logger = logging.getLogger(__name__)


def _verify_twilio_signature(request: Request, form: dict[str, str]) -> bool:
    """Verify the X-Twilio-Signature header against the Twilio auth token.

    Returns True if the signature matches, False otherwise. If TWILIO_AUTH_TOKEN
    is not configured, returns False — fail closed rather than accept any
    payload as if it came from Twilio.

    Algorithm (per Twilio docs): HMAC-SHA1 of (full request URL +
    sorted-key concatenation of form params), base64 encoded.
    """
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    if not auth_token:
        return False
    received = request.headers.get("X-Twilio-Signature", "")
    if not received:
        return False
    # Reconstruct the URL Twilio used. If you sit behind a proxy that
    # rewrites the host/scheme, set TWILIO_WEBHOOK_URL to the public URL.
    url = os.environ.get("TWILIO_WEBHOOK_URL", "").strip()
    if not url:
        url = str(request.url)
    # Concatenate form params sorted by key (Twilio's signing recipe).
    data = url + "".join(f"{k}{form[k]}" for k in sorted(form.keys()))
    digest = hmac.new(
        auth_token.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, received)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

_nse      = NseService()
_yahoo    = YahooService()
_price    = PriceService(_nse, _yahoo)
_sectors  = SectorsService(_nse, _yahoo)
_stocks   = StocksService(_nse, _yahoo)
_patterns = PatternsService(_yahoo, _nse)
_scanners = ScannersService(_price)
_nlp      = NlpService()

try:
    from ..services.hydra_service import HydraEngine
    _hydra = HydraEngine()
except Exception:  # pragma: no cover
    _hydra = None

_dispatcher = BotDispatcher(
    sectors=_sectors, stocks=_stocks, patterns=_patterns, scanners=_scanners,
    nlp=_nlp, hydra=_hydra, news=_news_module,
)
_service = WhatsappService(_sectors, _stocks, _patterns, _scanners, _nlp,
                           dispatcher=_dispatcher)


def get_service() -> WhatsappService:
    return _service


def get_dispatcher() -> BotDispatcher:
    return _dispatcher


@router.get("/status")
async def get_status():
    return _service.get_bot_status()


@router.put("/status")
async def update_status(body: dict[str, Any]):
    enabled = body.get("enabled")
    if enabled is None:
        return JSONResponse(status_code=400, content={"error": "'enabled' field required"})
    return _service.update_bot_status(bool(enabled))


@router.post("/status")
async def set_status(body: dict[str, Any]):
    enabled = body.get("enabled")
    if enabled is None:
        return JSONResponse(status_code=400, content={"error": "'enabled' field required"})
    return _service.update_bot_status(bool(enabled))


@router.post("/message")
async def process_message(body: dict[str, Any]):
    try:
        return await _service.process_message(body)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@router.post("/twilio")
async def twilio_webhook(request: Request):
    form = await request.form()
    # Twilio's form is a Starlette FormData; flatten str values for signing.
    form_dict = {k: str(v) for k, v in form.items() if isinstance(v, (str, bytes))}
    if not _verify_twilio_signature(request, form_dict):
        logger.warning("Twilio webhook: invalid X-Twilio-Signature, rejecting.")
        return JSONResponse(status_code=403, content={"error": "Forbidden"})
    from_number = form.get("From") or form.get("from") or "whatsapp:+unknown"
    text = form.get("Body") or form.get("body") or ""
    try:
        result = await _service.process_message(
            {"from": str(from_number), "text": str(text)}
        )
        reply = result.get("response") or "Sorry, I could not process your request."
    except Exception:
        logger.exception("Twilio webhook: processing failed")
        reply = "Sorry, I could not process your request."
    reply_safe = (
        str(reply)
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Message>{reply_safe}</Message>"
        "</Response>"
    )
    return Response(content=twiml, media_type="application/xml")


@router.get("/messages")
async def get_messages():
    return _service.get_message_log()


@router.post("/qr")
async def generate_qr():
    return _service.simulate_qr_code()
