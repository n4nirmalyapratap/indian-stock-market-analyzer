"""
Centralised logging configuration.

What this does
--------------
1. Sets the root logger level (from env LOG_LEVEL, default INFO).
2. Attaches a stdout StreamHandler so application logs flow into
   `docker logs <container>` alongside uvicorn's access logs.
3. Attaches an in-memory ring-buffer handler so /admin/logs can
   return the last N records as structured JSON.
4. Idempotent — safe to call multiple times; no double-handlers, no
   double-loglines.

Why this exists
---------------
Default behaviour without this module: Python's root logger sits at
WARNING level. Uvicorn configures its OWN loggers (`uvicorn`,
`uvicorn.error`, `uvicorn.access`) to INFO with their own stdout
handlers, so HTTP access lines appear in `docker logs`. But every
application logger (`shareholding`, `auth_store`, `nse`, …) inherits
from root, so their `logger.info(...)` calls get filtered out before
emitting anywhere — making `docker logs` useless for application-side
debugging.

Result before this fix: scanner/shareholding/registry triage required
either guessing or stepping into the admin UI. With this setup, every
`logger.info(...)` across the codebase shows up in `docker logs` AND
the admin /admin/logs endpoint, with a uniform format.

Usage (called once at lifespan startup, see main.py)
----------------------------------------------------
    from app.services.log_buffer import setup_ring_buffer
    setup_ring_buffer()

Env knobs
---------
    LOG_LEVEL        — DEBUG|INFO|WARNING|ERROR (default INFO).
                       Controls what the root logger admits; uvicorn
                       loggers stay at their own configured levels.
"""

import logging
import os
import sys
import threading
from typing import Optional

_CAPACITY = 2000

# Format applied to BOTH the stdout stream and the ring buffer's
# str-form (the ring buffer also stores structured fields separately,
# but having a consistent string for tail-the-stdout grepping helps).
#
# Example: "INFO     shareholding         shareholding NSE TCS: 80 rows upserted"
# The padded fields make `docker logs | grep shareholding` reliable
# and let humans scan column-aligned output.
_LOG_FORMAT = "%(levelname)-8s %(name)-20s %(message)s"


class RingBufferHandler(logging.Handler):
    """In-memory ring of the last `capacity` log records.

    Used by /admin/logs to serve recent structured logs as JSON. Each
    record keeps its level/logger/message/timestamp so callers can
    filter without re-parsing strings.
    """

    def __init__(self, capacity: int = _CAPACITY):
        super().__init__()
        self._buf: list[dict] = []
        self._cap = capacity
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            with self._lock:
                self._buf.append({
                    "ts":     record.created,
                    "level":  record.levelname,
                    "logger": record.name,
                    "msg":    record.getMessage(),
                })
                if len(self._buf) > self._cap:
                    self._buf = self._buf[-self._cap:]
        except Exception:
            pass

    def get_records(
        self,
        limit:  int = 200,
        level:  Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[dict]:
        with self._lock:
            records = list(self._buf)
        if level and level.upper() not in ("ALL", ""):
            records = [r for r in records if r["level"] == level.upper()]
        if search:
            s = search.lower()
            records = [r for r in records if s in r["msg"].lower() or s in r["logger"].lower()]
        return records[-limit:]


# Module-level singletons — guards against re-registration when the
# uvicorn `--reload` watchdog re-imports the module mid-process.
_ring_handler:   Optional[RingBufferHandler]    = None
_stdout_handler: Optional[logging.StreamHandler] = None


# Sentinel attribute we tag our own handlers with, so we can detect
# them on re-import without depending on identity (the module may be
# reloaded but the handler list survives on root logger).
_OUR_HANDLER_ATTR = "_app_logging_owned"


def _level_from_env() -> int:
    """Resolve LOG_LEVEL env var to a logging numeric level. Unknown
    values fall back to INFO (loud-fallback so misconfiguration
    surfaces immediately)."""
    raw = (os.environ.get("LOG_LEVEL") or "INFO").strip().upper()
    return {
        "DEBUG":    logging.DEBUG,
        "INFO":     logging.INFO,
        "WARNING":  logging.WARNING,
        "ERROR":    logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }.get(raw, logging.INFO)


def _has_our_handler(root: logging.Logger, handler_cls: type) -> bool:
    """Check if root already has one of OUR handlers of `handler_cls`.
    We don't claim every handler of that class — uvicorn or third-party
    libs may have added their own — only ones marked with our sentinel."""
    return any(
        isinstance(h, handler_cls) and getattr(h, _OUR_HANDLER_ATTR, False)
        for h in root.handlers
    )


def setup_ring_buffer() -> RingBufferHandler:
    """Configure root logging end-to-end. Idempotent.

    On first call:
      1. Set root logger level to LOG_LEVEL (default INFO).
      2. Attach a stdout StreamHandler with the uniform format.
      3. Attach the ring-buffer handler for /admin/logs.
      4. Reduce yfinance / urllib3 / asyncio noise to WARNING so they
         don't bury our application INFO output.

    On later calls: returns the existing ring buffer without
    re-attaching handlers (so uvicorn's `--reload` doesn't multiply
    output).

    Returns the ring buffer so callers (legacy ones in main.py) can
    keep using the existing reference.
    """
    global _ring_handler, _stdout_handler

    root = logging.getLogger()
    level = _level_from_env()
    root.setLevel(level)

    fmt = logging.Formatter(_LOG_FORMAT)

    # ── stdout handler ────────────────────────────────────────────────
    if _stdout_handler is None and not _has_our_handler(root, logging.StreamHandler):
        h = logging.StreamHandler(sys.stdout)
        h.setLevel(level)
        h.setFormatter(fmt)
        setattr(h, _OUR_HANDLER_ATTR, True)
        root.addHandler(h)
        _stdout_handler = h

    # ── ring buffer handler ───────────────────────────────────────────
    if _ring_handler is None and not _has_our_handler(root, RingBufferHandler):
        h = RingBufferHandler()
        h.setLevel(logging.DEBUG)   # ring keeps DEBUG too for /admin/logs?level=DEBUG
        setattr(h, _OUR_HANDLER_ATTR, True)
        root.addHandler(h)
        _ring_handler = h
    elif _ring_handler is None:
        # Already attached on a prior import that lost the module-level
        # reference. Find it and reuse.
        for h in root.handlers:
            if isinstance(h, RingBufferHandler) and getattr(h, _OUR_HANDLER_ATTR, False):
                _ring_handler = h
                break
        if _ring_handler is None:                # paranoid fallback
            _ring_handler = RingBufferHandler()

    # ── noise control ─────────────────────────────────────────────────
    # Libraries that are chatty at INFO/DEBUG. WARNING keeps real
    # errors visible without per-request HTTP noise burying our signal.
    for noisy in ("urllib3", "asyncio", "peewee", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # yfinance specifically: it ERROR-logs every 404 ("Quote not found
    # for symbol: X") even though our chain handles missing-symbol
    # outcomes via the return-value semantics. These 404s are
    # expected (delisted stocks, BSE-only indices Yahoo doesn't carry,
    # etc.) and would never produce actionable user-facing errors —
    # they only pollute the log when 20+ scan symbols turn out to be
    # Yahoo-unavailable.
    #
    # We filter rather than raise to CRITICAL so a *genuine* yfinance
    # error (network exception, malformed response) still surfaces.
    class _DropYfinance404(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            try:
                msg = record.getMessage()
            except Exception:
                return True
            if "HTTP Error 404" in msg and "Quote not found for symbol" in msg:
                return False
            return True

    yf_logger = logging.getLogger("yfinance")
    # Replace any existing filter we previously installed (idempotent
    # under uvicorn --reload).
    yf_logger.filters = [
        f for f in yf_logger.filters
        if not getattr(f, "_app_drop_yf_404", False)
    ]
    drop_filter = _DropYfinance404()
    drop_filter._app_drop_yf_404 = True   # type: ignore[attr-defined]
    yf_logger.addFilter(drop_filter)

    return _ring_handler


def get_ring_buffer() -> Optional[RingBufferHandler]:
    return _ring_handler
