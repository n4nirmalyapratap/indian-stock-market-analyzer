from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, Response
from typing import Any, Optional
from ..services.whatsapp_service import WhatsappService
from ..services.sectors_service import SectorsService
from ..services.stocks_service import StocksService
from ..services.patterns_service import PatternsService
from ..services.scanners_service import ScannersService
from ..services.nse_service import NseService
from ..services.yahoo_service import YahooService
from ..services.nlp_service import NlpService

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

_nse     = NseService()
_yahoo   = YahooService()
_sectors = SectorsService(_nse, _yahoo)
_stocks  = StocksService(_nse, _yahoo)
_patterns= PatternsService(_yahoo, _nse)
_scanners= ScannersService(_yahoo, _nse)
_nlp     = NlpService()
_service = WhatsappService(_sectors, _stocks, _patterns, _scanners, _nlp)


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
    """
    Twilio WhatsApp webhook.
    Twilio sends application/x-www-form-urlencoded with fields:
      From  — sender number, e.g. "whatsapp:+911234567890"
      Body  — message text
      To    — your Twilio number
    Returns TwiML XML so Twilio can send the reply back to the user.
    """
    form = await request.form()
    from_number = form.get("From") or form.get("from") or "whatsapp:+unknown"
    text = form.get("Body") or form.get("body") or ""
    try:
        result = await _service.process_message({"from": str(from_number), "text": str(text)})
        reply = result.get("response") or "Sorry, I could not process your request."
    except Exception as e:
        reply = f"Error: {e}"

    # Escape XML special characters in the reply
    reply_safe = (
        str(reply)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
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
