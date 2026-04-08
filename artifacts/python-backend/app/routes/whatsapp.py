from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from typing import Any
from ..services.whatsapp_service import WhatsappService
from ..services.sectors_service import SectorsService
from ..services.stocks_service import StocksService
from ..services.patterns_service import PatternsService
from ..services.scanners_service import ScannersService
from ..services.nse_service import NseService
from ..services.yahoo_service import YahooService

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

_nse     = NseService()
_yahoo   = YahooService()
_sectors = SectorsService(_nse, _yahoo)
_stocks  = StocksService(_nse, _yahoo)
_patterns= PatternsService(_yahoo, _nse)
_scanners= ScannersService(_yahoo, _nse)
_service = WhatsappService(_sectors, _stocks, _patterns, _scanners)


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
async def twilio_webhook(body: dict[str, Any]):
    from_number = body.get("From") or body.get("from") or "whatsapp:+unknown"
    text = body.get("Body") or body.get("body") or body.get("message") or ""
    try:
        result = await _service.process_message({"from": from_number, "text": text})
        reply = result.get("response") or ""
    except ValueError as e:
        reply = f"Error: {e}"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Message>{reply}</Message>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


@router.get("/messages")
async def get_messages():
    return _service.get_message_log()


@router.post("/qr")
async def generate_qr():
    return _service.simulate_qr_code()
