import os
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.routes.health import router as health_router
from app.routes.sectors import router as sectors_router
from app.routes.stocks import router as stocks_router
from app.routes.patterns import router as patterns_router
from app.routes.scanners import router as scanners_router
from app.routes.whatsapp import router as whatsapp_router
from app.routes.nlp import router as nlp_router
from app.routes.analytics import router as analytics_router
from app.routes.telegram import router as telegram_router, get_service as get_telegram_service
from app.routes.universe import router as universe_router

logger = logging.getLogger("telegram-poller")


async def _telegram_polling_loop() -> None:
    """Long-poll Telegram getUpdates in the background."""
    svc = get_telegram_service()
    if not svc.configured:
        logger.info("TELEGRAM_BOT_TOKEN not set — polling disabled.")
        return

    # Remove any existing webhook so polling works
    await svc.delete_webhook()
    logger.info("Telegram polling started (@%s)", (await svc.get_bot_info()).get("username", "?"))

    offset = 0
    while True:
        try:
            updates, offset = await svc.get_updates(offset=offset, timeout=25)
            for update in updates:
                asyncio.create_task(svc.process_update(update))
        except asyncio.CancelledError:
            logger.info("Telegram polling stopped.")
            break
        except Exception as e:
            logger.warning("Telegram polling error: %s — retrying in 5s", e)
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    poll_task = asyncio.create_task(_telegram_polling_loop())
    # Refresh live universe in background — won't block startup
    asyncio.create_task(_refresh_universe())
    try:
        yield
    finally:
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass


async def _refresh_universe() -> None:
    try:
        from app.lib.universe_builder import refresh_in_background
        await refresh_in_background()
        # Re-apply to universe module after fresh cache is saved
        from app.lib.universe import _apply_live_data
        from app.lib.universe_builder import load_cache
        fresh = load_cache()
        if fresh:
            _apply_live_data(fresh)
            logger.info(
                "Universe refreshed from live NSE data — %d symbols",
                len(fresh.get("all_symbols", []))
            )
    except Exception as e:
        logger.warning("Universe refresh failed (hardcoded fallback active): %s", e)


app = FastAPI(
    title="Indian Stock Market Analyzer — Python Backend",
    description=(
        "FastAPI backend for NSE sector rotation, stock analysis, chart patterns, "
        "custom scanners, NLP natural-language queries, analytics, and Telegram bot."
    ),
    version="2.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


app.include_router(health_router,    prefix="/api")
app.include_router(sectors_router,   prefix="/api")
app.include_router(stocks_router,    prefix="/api")
app.include_router(patterns_router,  prefix="/api")
app.include_router(scanners_router,  prefix="/api")
app.include_router(whatsapp_router,  prefix="/api")
app.include_router(nlp_router,       prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(telegram_router,  prefix="/api")
app.include_router(universe_router,  prefix="/api")
