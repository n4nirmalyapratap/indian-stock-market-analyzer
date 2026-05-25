import os
import asyncio
import logging
import datetime as dt
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.middleware.clerk_auth import AppAuthMiddleware
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
from app.routes.jobs import router as jobs_router
from app.routes.insights import router as insights_router
from app.routes.agents import router as agents_router
from app.routes.portfolio import router as portfolio_router
from app.routes.ai_analyst import router as ai_analyst_router
from app.routes.top_movers import router as top_movers_router
from app.routes.user_broker_keys import router as user_broker_keys_router
from app.routes.search import router as search_router
from app.routes.email_digest import router as email_digest_router
from app.routes.logos import router as logos_router
from app.lib.auth_store import ensure_primary_schema
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
    """On startup, warm up disk cache only when market is closed and cache is thin.

    Also runs `seal_eod_for_today_if_overdue()` so any snapshots that were
    saved intraday get re-fetched and rewritten as official EOD closes.
    """
    await asyncio.sleep(5)  # let the server fully start first
    price_service = _PriceService(_NseService(), _YahooService())

    if is_market_open():
        logger.info("Cache warmup skipped — market is open.")
        return

    status = cache_status()
    if status.get("thin", True):
        logger.info("Warming up disk cache (market closed + cache thin)…")
        try:
            result = await _mcs.warmup_cache(price_service)
            logger.info(
                "Cache warmup complete: %d files saved, %d errors (date=%s)",
                result["filesSaved"], result["errors"], result["cacheDate"],
            )
        except Exception as e:
            logger.warning("Cache warmup failed: %s", e)
    else:
        logger.info("Cache warmup skipped — cache is already populated (date=%s).", status.get("cacheDate"))

    # Always seal any intraday snapshots into EOD closes when market is closed
    try:
        seal_result = await _mcs.seal_eod_for_today_if_overdue(price_service)
        logger.info("EOD seal complete: %s", seal_result)
    except Exception as e:
        logger.warning("EOD seal failed: %s", e)


async def _market_state_transition_loop() -> None:
    """
    Watch for NSE market-state transitions every 60s. When the state changes
    (e.g. OPEN → CLOSED at 15:30 IST, CLOSED → OPEN at 09:15 IST, weekend
    rollovers), bump the cache version. For transitions *into* a closed state
    (OPEN → CLOSED, OPEN → WEEKEND, PRE_OPEN → CLOSED, etc.), wait briefly
    for any in-flight intraday quotes to settle then run
    `seal_eod_for_today_if_overdue()` so on-disk snapshots get re-fetched and
    rewritten as the official EOD close — without needing a restart.
    """
    await asyncio.sleep(10)  # let the server settle before the first read
    price_service = _PriceService(_NseService(), _YahooService())

    last_state = _mcs.current_market_state()
    initial_version = _mcs.cache_version()
    logger.info(
        "Market-state watcher started (state=%s, cacheVersion=%d).",
        last_state, initial_version,
    )

    closed_states = {"CLOSED", "WEEKEND"}
    while True:
        try:
            await asyncio.sleep(60)
            state = _mcs.current_market_state()
            if state == last_state:
                continue

            # Transition — `cache_version()` (which calls bump_if_needed)
            # automatically increments on state change.
            new_version = _mcs.cache_version()
            logger.info(
                "Market state transition: %s → %s (cacheVersion=%d).",
                last_state, state, new_version,
            )

            # When entering a closed state, give the upstream feeds ~30s to
            # publish their final official numbers, then seal.
            if state in closed_states and last_state not in closed_states:
                await asyncio.sleep(30)
                try:
                    result = await _mcs.seal_eod_for_today_if_overdue(price_service)
                    logger.info("EOD seal after transition: %s", result)
                except Exception as e:
                    logger.warning("Post-transition EOD seal failed: %s", e)

            last_state = state
        except asyncio.CancelledError:
            logger.info("Market-state watcher stopped.")
            break
        except Exception as e:
            logger.warning("Market-state watcher error: %s — retrying in 60s.", e)
            await asyncio.sleep(60)


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


def _verify_critical_dependencies() -> None:
    """Fail loudly at boot if any data-source-critical package is missing.
    
    History: both `nsepython` (NSE deals/events) and `statsmodels`
    (cointegration p-values for Hydra Pairs) were used inside silent
    try/except blocks. When the packages went missing from requirements,
    the features simply returned empty/weak results without anyone noticing.
    A loud import here is the meta-fix — anything in this list MUST resolve
    or the backend won't start.
    """
    critical = {
        "nsepython":   "NSE bulk/block deals + corporate events feed",
        "statsmodels": "Engle-Granger cointegration for Hydra Pairs",
        "pandas_ta":   "Technical indicators (RSI/MACD/etc)",
        "vaderSentiment": "News sentiment scoring",
        "feedparser":  "RSS news ingestion",
        "yfinance":    "Yahoo price fallback",
        "spacy":       "NER for news entity extraction",
    }
    missing: list[str] = []
    for mod, why in critical.items():
        try:
            __import__(mod)
        except ImportError as e:
            missing.append(f"  - {mod}: {why}  ({e})")
    if missing:
        msg = (
            "FATAL: critical dependencies missing — refusing to start.\n"
            "Add these to requirements.txt:\n" + "\n".join(missing)
        )
        logger.error(msg)
        raise RuntimeError(msg)
    logger.info("Dependency check OK: %d critical packages present", len(critical))


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_primary_schema()

    # Verify all critical data-source packages are importable. Loud failure
    # beats silent fallback — see _verify_critical_dependencies for the why.
    _verify_critical_dependencies()

    # Refuse to start if SESSION_SECRET is missing/weak/a known placeholder.
    # Without this, every JWT is signed with a public string and admin tokens
    # are forgeable. See app/lib/auth_tokens.py for the placeholder list.
    from app.lib.auth_tokens import validate_session_secret
    validate_session_secret()

    # Attach the ring-buffer AFTER uvicorn has configured logging (it resets
    # the root logger on startup, so setup_ring_buffer() in run.py is too early).
    # Also hook uvicorn's own loggers explicitly — they set propagate=False.
    rb = setup_ring_buffer()
    for _uv_logger in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        _l = logging.getLogger(_uv_logger)
        if rb not in _l.handlers:
            _l.addHandler(rb)

    poll_task       = asyncio.create_task(_telegram_polling_loop())
    universe_task   = asyncio.create_task(_universe_scheduler())
    warmup_task     = asyncio.create_task(_cache_warmup_task())
    transition_task = asyncio.create_task(_market_state_transition_loop())
    fixer_task      = asyncio.create_task(_bug_fixer_loop())
    rfr_task        = asyncio.create_task(_risk_free_rate_scheduler())
    bhav_task       = asyncio.create_task(_bhavcopy_refresh_scheduler())
    alerts_task     = asyncio.create_task(_bot_alerts_tick_loop())
    backtest_task   = asyncio.create_task(_ai_backtest_scheduler())
    digest_sched_task  = asyncio.create_task(_email_digest_scheduler())
    digest_worker_task = asyncio.create_task(_email_digest_worker())
    fii_dii_task    = asyncio.create_task(_fii_dii_scheduler())
    dhan_task       = asyncio.create_task(_dhan_scrip_master_preload())
    try:
        yield
    finally:
        for t in (poll_task, universe_task, warmup_task, transition_task,
                  fixer_task, rfr_task, bhav_task, alerts_task, backtest_task,
                  digest_sched_task, digest_worker_task, fii_dii_task, dhan_task):
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass


async def _bot_alerts_tick_loop() -> None:
    """Evaluate per-chat bot alert subscriptions every 5 minutes and dispatch
    fired alerts via the Telegram and WhatsApp send functions.

    Loud-fallback: never raises out of the loop — each tick logs warnings on
    failure so operators can see exactly which subscription/symbol misbehaved.
    """
    from app.services import bot_alerts
    from app.routes.telegram import get_service as _tg_svc
    from app.routes.whatsapp import get_service as _wa_svc

    # Brief warmup delay
    await asyncio.sleep(30)
    while True:
        try:
            tg = _tg_svc()
            wa = _wa_svc()

            async def _quote(symbol: str) -> dict:
                try:
                    return await tg.stocks.get_stock_details(symbol)
                except Exception:
                    return {}

            async def _patterns() -> dict:
                try:
                    return await tg.patterns.get_patterns()
                except Exception:
                    return {}

            async def _send(channel: str, chat_id: str, text: str) -> bool:
                try:
                    if channel == "telegram":
                        return await tg.send_message(chat_id, text)
                    # WhatsApp: log into the in-memory message log so the admin
                    # dashboard surfaces it; real Twilio dispatch happens out
                    # of band when the user replies.
                    wa.get_message_log().append({
                        "from": chat_id, "text": "(alert)",
                        "response": text,
                        "timestamp": dt.datetime.utcnow().isoformat() + "Z",
                    })
                    return True
                except Exception as exc:
                    logger.warning("bot_alerts send failed: %s", exc)
                    return False

            stats = await bot_alerts.evaluate_due_alerts(
                quote_fn=_quote, pattern_fn=_patterns, send_fn=_send,
            )
            if stats.get("fired"):
                logger.info("bot_alerts: tick fired=%d skipped=%d errors=%d",
                            stats["fired"], stats["skipped"], stats["errors"])
        except Exception as exc:
            logger.warning("bot_alerts tick failed: %s", exc)
        try:
            await asyncio.sleep(5 * 60)
        except asyncio.CancelledError:
            logger.info("Bot alerts scheduler stopped.")
            break


async def _risk_free_rate_scheduler() -> None:
    """Refresh the FRED India 10Y G-Sec yield on startup, then once a day.

    Loud-fallback design: every refresh logs at INFO on success and WARNING
    on stale/hard-fallback so operators see exactly which value the pricing
    layer is using.  Never raises — falls back via the standard chain.
    """
    from app.services.risk_free_service import refresh_risk_free_rate_on_startup
    # Brief delay so the rest of the startup logging is grouped first
    await asyncio.sleep(2)
    while True:
        try:
            await refresh_risk_free_rate_on_startup()
        except Exception as exc:
            logger.warning("risk-free scheduler tick failed: %s", exc)
        # 24h refresh — matches the in-memory cache TTL
        try:
            await asyncio.sleep(24 * 3600)
        except asyncio.CancelledError:
            logger.info("Risk-free scheduler stopped.")
            break


async def _bhavcopy_refresh_scheduler() -> None:
    """Refresh the NSE/BSE F&O bhavcopy cache once a day.

    On startup, pulls the last 7 trading days that aren't already cached so
    fresh installs become useful quickly.  Subsequent ticks pull just the
    last 2 days to catch the previous trading session.
    """
    from app.services.nse_bhavcopy_service import refresh_recent
    await asyncio.sleep(5)
    first_run = True
    while True:
        try:
            results = await asyncio.to_thread(refresh_recent, 7 if first_run else 2)
            ok = sum(1 for r in results if r["status"] == "ok")
            logger.info("Bhavcopy scheduler tick: %d new days cached "
                        "(%d attempts)", ok, len(results))
        except Exception as exc:
            logger.warning("Bhavcopy scheduler tick failed: %s", exc)
        first_run = False
        try:
            await asyncio.sleep(24 * 3600)
        except asyncio.CancelledError:
            logger.info("Bhavcopy scheduler stopped.")
            break


async def _fii_dii_scheduler() -> None:
    """Keep the FII/DII history table fresh without depending on anyone
    opening the insights page.

    Schedule:
      * On startup → run once after a brief settle delay, so any gap
        accumulated while the container was down gets healed before the
        first user request.
      * Daily   → run every 24h. The fetch itself is gap-aware (asks for
        the last 30 trading days and upserts whatever PG doesn't already
        have), so the exact tick time doesn't matter — even if a tick is
        missed the next one heals the gap.

    Loud-fallback: never raises out of the loop — every tick logs a
    summary line so operators can see when the data last refreshed.
    """
    from app.services.fii_dii_service import FiiDiiService  # noqa: PLC0415
    svc = FiiDiiService()
    # Brief startup delay so the rest of boot logging settles first.
    await asyncio.sleep(8)
    # We run two cadences in this single coroutine:
    #   * Recent-day F&O healer  — every 4h, last 7 weekdays only
    #   * Full daily tick        — every 24h, 30-day gap-fill across all segments
    # Counter tracks how many 4h ticks have elapsed; the 24h tick triggers
    # every 6 of them (4h × 6 = 24h). Keeps everything in one async task.
    tick_count = 0
    while True:
        try:
            if tick_count % 6 == 0:
                # Full daily tick — every segment, 30-day gap fill.
                result = await svc.scheduled_daily_fetch(gap_days=30)
                segments = result.get("segments", {})
                ok_count = sum(1 for r in segments.values()
                               if r.get("ok") and (r.get("rows") or 0) > 0)
                logger.info("FII/DII daily tick: %d/%d segments populated",
                            ok_count, len(segments))
                for seg, r in segments.items():
                    if r.get("ok"):
                        rows   = r.get("rows") or 0
                        latest = r.get("latest") or "—"
                        flag   = "" if rows > 0 else "  ← EMPTY (upstream blocked?)"
                        logger.info("  %-14s : %4d rows, latest=%s%s",
                                    seg, rows, latest, flag)
                    else:
                        logger.warning("  %-14s : FAILED — %s",
                                       seg, r.get("error", "unknown"))
            else:
                # Aggressive F&O recent-day healer — last 7 weekdays only.
                # Bypasses the 24h HTTP cache for missing dates so a
                # previously-empty body doesn't suppress the retry.
                heal = await svc.heal_recent_fno_gaps(lookback_days=7)
                if heal.get("missing", 0) > 0:
                    logger.info("FII/DII F&O recent-heal: %d/%d days missing → filled %d",
                                heal.get("missing"), heal.get("checked"), heal.get("filled"))
                    for d in heal.get("days", []):
                        flag = "ok" if d.get("ok") else "still missing"
                        logger.info("  %s: %s", d.get("date"), flag)
        except Exception as exc:
            logger.warning("FII/DII scheduler tick failed: %s", exc)
        tick_count += 1
        try:
            await asyncio.sleep(4 * 3600)  # 4 hours between ticks
        except asyncio.CancelledError:
            logger.info("FII/DII scheduler stopped.")
            break


async def _email_digest_scheduler() -> None:
    """Wake every minute and enqueue any digest whose send time has arrived.
    Enqueue is cheap (read N rows, render N digests, insert N queue rows);
    actual SMTP dispatch happens in `_email_digest_worker` below."""
    from app.services import email_digest_service
    await asyncio.sleep(30)  # let the rest of startup settle
    price_service = _PriceService(_NseService(), _YahooService())
    while True:
        try:
            stats = await email_digest_service.enqueue_due_digests(price_service)
            if stats["enqueued"]:
                logger.info("email_digest scheduler: %s", stats)
        except Exception as exc:
            logger.warning("email_digest scheduler error: %s", exc)
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info("Email digest scheduler stopped.")
            break


async def _email_digest_worker() -> None:
    """Drain the queue at the configured burst-cap rate. SMTP send is a
    blocking syscall — we offload it to a thread so the event loop stays
    responsive for the rest of the API."""
    from app.services import email_digest_service
    await asyncio.sleep(45)  # land slightly after the scheduler's first tick
    while True:
        try:
            stats = await asyncio.to_thread(email_digest_service.drain_queue)
            if stats["sent"] or stats["failed"]:
                logger.info("email_digest worker: %s", stats)
        except Exception as exc:
            logger.warning("email_digest worker error: %s", exc)
        try:
            # 60 seconds keeps us comfortably under Gmail's per-minute limits
            # — the burst cap inside drain_queue is what actually enforces the
            # rate; this is just the polling cadence.
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info("Email digest worker stopped.")
            break


async def _ai_backtest_scheduler() -> None:
    """Evaluate every BUY/SELL verdict from the AI Analyst against actual
    price moves at 1d / 5d / 30d horizons. Runs ~6h after startup and then
    every 24h so the post-close prices are settled before we measure.
    """
    from app.services import ai_backtest_service
    # Wait a few hours after startup so the first run lands after market close.
    await asyncio.sleep(6 * 3600)
    price_service = _PriceService(_NseService(), _YahooService())
    while True:
        try:
            logger.info("AI backtest: scheduled run starting…")
            result = await ai_backtest_service.evaluate_pending(price_service)
            logger.info("AI backtest: %s", result)
        except Exception as exc:
            logger.warning("AI backtest scheduler error: %s", exc)
        try:
            await asyncio.sleep(24 * 3600)
        except asyncio.CancelledError:
            logger.info("AI backtest scheduler stopped.")
            break


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


async def _dhan_scrip_master_preload() -> None:
    """Download the Dhan F&O scrip master once per calendar day at startup.

    Priority order in the service:
      1. Hot in-memory cache (noop if already populated).
      2. Today's on-disk CSV in market_cache/ (survives process restarts).
      3. Live download from Dhan CDN (only when today's file is absent/stale).

    This means the HTTP call to Dhan is made at most once per day regardless
    of how many times the server restarts — minimising outbound calls.
    """
    await asyncio.sleep(8)   # let other startup tasks log first
    try:
        from app.services.dhan_scrip_master_service import preload as _preload
        await _preload()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("Dhan scrip master preload failed: %s", exc)


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

app.add_middleware(AppAuthMiddleware)

# ── CORS ───────────────────────────────────────────────────────────────────
# Origins are pinned. We always allow the local-dev hosts so the app keeps
# working in `pnpm dev`, and read additional production origins from the
# CORS_ALLOWED_ORIGINS env var (comma-separated). Setting this to "*" is
# intentionally NOT supported — wildcard CORS combined with token-bearing
# fetches lets any third-party site drive the API on the user's behalf.
# ───────────────────────────────────────────────────────────────────────────
_DEFAULT_DEV_ORIGINS = [
    "http://localhost:3002",   # stock-market-app (per artifact.toml)
    "http://localhost:5000",   # stock-market-app fallback
    "http://localhost:5173",   # admin-dashboard (Vite default)
    "http://localhost:5174",   # alt Vite port
    "http://localhost:8080",   # nginx-frontend
    "http://127.0.0.1:3002",
    "http://127.0.0.1:5000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:8080",
]
_extra_origins = [
    o.strip()
    for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
    if o.strip() and o.strip() != "*"
]
_ALLOWED_ORIGINS = _DEFAULT_DEV_ORIGINS + _extra_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
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
app.include_router(jobs_router,             prefix="/api")
app.include_router(insights_router,         prefix="/api")
app.include_router(agents_router,            prefix="/api")
app.include_router(portfolio_router,         prefix="/api")
app.include_router(ai_analyst_router,         prefix="/api")
app.include_router(top_movers_router,          prefix="/api")
app.include_router(user_broker_keys_router,    prefix="/api")
app.include_router(search_router,              prefix="/api")
app.include_router(email_digest_router,         prefix="/api")
app.include_router(logos_router,                prefix="/api")
