import os
import asyncio
import logging
import datetime as dt
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.middleware.clerk_auth import ClerkAuthMiddleware
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
from app.routes.hydra import router as hydra_router
from app.routes.cache import router as cache_router
from app.routes.options import router as options_router
from app.routes.chat import router as chat_router
from app.routes.assistant import router as assistant_router
from app.routes.sector_analytics import router as sector_analytics_router
from app.routes.news import router as news_router
from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.sentiment import router as sentiment_router
from app.services.log_buffer import setup_ring_buffer
from app.services.market_cache_service import is_market_open, cache_status
from app.services import market_cache_service as _mcs
from app.services.yahoo_service import YahooService as _YahooService
from app.services.nse_service import NseService as _NseService
from app.services.price_service import PriceService as _PriceService

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


async def _cache_warmup_task() -> None:
    """On startup, warm up disk cache only when market is closed and cache is thin."""
    await asyncio.sleep(5)  # let the server fully start first
    if is_market_open():
        logger.info("Cache warmup skipped — market is open.")
        return
    status = cache_status()
    if not status.get("thin", True):
        logger.info("Cache warmup skipped — cache is already populated (date=%s).", status.get("cacheDate"))
        return
    logger.info("Warming up disk cache (market closed + cache thin)…")
    try:
        result = await _mcs.warmup_cache(_PriceService(_NseService(), _YahooService()))
        logger.info(
            "Cache warmup complete: %d files saved, %d errors (date=%s)",
            result["filesSaved"], result["errors"], result["cacheDate"],
        )
    except Exception as e:
        logger.warning("Cache warmup failed: %s", e)


async def _bug_fixer_loop() -> None:
    """
    Run the AI bug analyser every 10 minutes.
    Analysis only — reads open bugs, uses AI to diagnose root cause and suggest
    fix steps, stores the analysis in the bug description. Does NOT apply any
    code changes, run tests, or push to GitHub. Humans decide when to fix/close.
    """
    await asyncio.sleep(120)  # let server fully start first
    while True:
        try:
            logger.info("Bug analyser: starting scheduled run…")
            import sys as _sys  # noqa: PLC0415
            import pathlib as _pl  # noqa: PLC0415
            _sys.path.insert(0, str(_pl.Path(__file__).parent))
            from scripts.bug_fixer import run_all  # noqa: PLC0415
            results = await run_all()
            logger.info("Bug analyser: done — %s", results)
        except Exception as exc:
            logger.warning("Bug analyser loop error: %s", exc)
        await asyncio.sleep(600)  # 10 minutes


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Attach the ring-buffer AFTER uvicorn has configured logging (it resets
    # the root logger on startup, so setup_ring_buffer() in run.py is too early).
    # Also hook uvicorn's own loggers explicitly — they set propagate=False.
    rb = setup_ring_buffer()
    for _uv_logger in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        _l = logging.getLogger(_uv_logger)
        if rb not in _l.handlers:
            _l.addHandler(rb)

    poll_task    = asyncio.create_task(_telegram_polling_loop())
    universe_task = asyncio.create_task(_universe_scheduler())
    warmup_task  = asyncio.create_task(_cache_warmup_task())
    fixer_task   = asyncio.create_task(_bug_fixer_loop())
    try:
        yield
    finally:
        for t in (poll_task, universe_task, warmup_task, fixer_task):
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass


async def _universe_scheduler() -> None:
    """
    Refresh the stock universe once per day at 16:05 IST (10:35 UTC)
    — just after NSE market close (15:30 IST).
    On first startup, load from cache if it exists; only fetch live if cache is stale.
    """
    from app.lib.universe_builder import load_cache, get_or_refresh
    from app.lib.universe import _apply_live_data

    # Apply whatever is already cached so the server starts with live data
    cached = load_cache()
    if cached:
        _apply_live_data(cached)
        logger.info(
            "Universe loaded from cache — %d symbols (generated %s)",
            len(cached.get("all_symbols", [])),
            cached.get("generated_at", "?"),
        )

    while True:
        try:
            # Calculate seconds until next 10:35 UTC (= 16:05 IST)
            now_utc = dt.datetime.utcnow()
            target   = now_utc.replace(hour=10, minute=35, second=0, microsecond=0)
            if now_utc >= target:
                # Already past today's window — schedule for tomorrow
                target += dt.timedelta(days=1)
            wait_s = (target - now_utc).total_seconds()
            logger.info(
                "Universe scheduler: next refresh in %.0f s (at %s UTC)",
                wait_s, target.strftime("%Y-%m-%d %H:%M"),
            )
            await asyncio.sleep(wait_s)

            # Force a fresh fetch (ignore cache — this is the scheduled daily refresh)
            from app.lib.universe_builder import fetch_universe, save_cache
            data = await fetch_universe()
            if data and data.get("all_symbols"):
                save_cache(data)
                _apply_live_data(data)
                logger.info(
                    "Universe refreshed — %d symbols, %d sectors",
                    len(data.get("all_symbols", [])),
                    len(data.get("sector_symbols", {})),
                )
        except asyncio.CancelledError:
            logger.info("Universe scheduler stopped.")
            break
        except Exception as e:
            logger.warning("Universe scheduler error: %s — retrying tomorrow", e)
            await asyncio.sleep(3600)   # back-off 1 h on unexpected error


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

app.add_middleware(ClerkAuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Token"],
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
app.include_router(hydra_router,     prefix="/api")
app.include_router(cache_router,     prefix="/api")
app.include_router(options_router,   prefix="/api")
app.include_router(chat_router,      prefix="/api")
app.include_router(assistant_router,        prefix="/api")
app.include_router(sector_analytics_router, prefix="/api")
app.include_router(news_router,             prefix="/api")
app.include_router(admin_router,            prefix="/api")
app.include_router(auth_router,             prefix="/api")
app.include_router(sentiment_router,        prefix="/api")
