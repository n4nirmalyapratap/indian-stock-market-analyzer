"""
In-memory ring-buffer log handler.

Captures the last N log records from all Python loggers so the admin
/api/admin/logs endpoint can return structured, filterable log data
without needing a log file on disk.

Usage (call once at startup, before uvicorn is started):
    from app.services.log_buffer import setup_ring_buffer
    setup_ring_buffer()
"""

import logging
import threading
from typing import Optional

_CAPACITY = 2000


class RingBufferHandler(logging.Handler):
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
        limit: int = 200,
        level: Optional[str] = None,
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


_handler: Optional[RingBufferHandler] = None


def setup_ring_buffer() -> RingBufferHandler:
    """Attach the ring buffer to the root logger. Safe to call multiple times."""
    global _handler
    if _handler is not None:
        return _handler
    _handler = RingBufferHandler()
    _handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    root.addHandler(_handler)
    return _handler


def get_ring_buffer() -> Optional[RingBufferHandler]:
    return _handler
