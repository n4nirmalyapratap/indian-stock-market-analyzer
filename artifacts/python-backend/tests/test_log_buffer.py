"""
Unit tests for the in-memory ring buffer log system.
"""
import logging
import pytest

from app.services.log_buffer import RingBufferHandler, setup_ring_buffer, get_ring_buffer


class TestRingBufferHandler:

    def _make_handler(self, capacity=100):
        return RingBufferHandler(capacity=capacity)

    def _emit(self, handler, level, msg, logger_name="test"):
        record = logging.LogRecord(
            name=logger_name,
            level=getattr(logging, level.upper()),
            pathname="test.py",
            lineno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        handler.emit(record)

    def test_records_are_stored(self):
        h = self._make_handler()
        self._emit(h, "INFO", "hello world")
        records = h.get_records(limit=10)
        assert len(records) == 1
        assert records[0]["msg"] == "hello world"
        assert records[0]["level"] == "INFO"

    def test_ring_buffer_capacity_limit(self):
        """Buffer should never exceed capacity."""
        h = self._make_handler(capacity=10)
        for i in range(20):
            self._emit(h, "INFO", f"msg {i}")
        records = h.get_records(limit=100)
        assert len(records) <= 10, "Ring buffer exceeded capacity"

    def test_ring_buffer_keeps_latest_records(self):
        """After overflow, the latest records are retained."""
        h = self._make_handler(capacity=5)
        for i in range(10):
            self._emit(h, "INFO", f"msg {i}")
        records = h.get_records(limit=100)
        messages = [r["msg"] for r in records]
        assert "msg 9" in messages, "Latest message should be retained"
        assert "msg 0" not in messages, "Oldest message should have been evicted"

    def test_filter_by_level(self):
        h = self._make_handler()
        self._emit(h, "INFO",    "info message")
        self._emit(h, "ERROR",   "error message")
        self._emit(h, "WARNING", "warning message")
        errors = h.get_records(level="ERROR")
        assert all(r["level"] == "ERROR" for r in errors)
        assert len(errors) == 1

    def test_filter_by_search(self):
        h = self._make_handler()
        self._emit(h, "INFO", "stock price updated for RELIANCE")
        self._emit(h, "INFO", "cache warmed up for TCS")
        self._emit(h, "INFO", "sector rotation computed")
        results = h.get_records(search="RELIANCE")
        assert len(results) == 1
        assert "RELIANCE" in results[0]["msg"]

    def test_filter_by_search_case_insensitive(self):
        h = self._make_handler()
        self._emit(h, "INFO", "Fetching data for NIFTY50")
        results = h.get_records(search="nifty50")
        assert len(results) == 1

    def test_limit_respected(self):
        h = self._make_handler()
        for i in range(50):
            self._emit(h, "INFO", f"msg {i}")
        results = h.get_records(limit=10)
        assert len(results) <= 10

    def test_records_have_required_fields(self):
        h = self._make_handler()
        self._emit(h, "INFO", "test message", logger_name="myapp.service")
        record = h.get_records()[0]
        assert "ts" in record,     "Record must have timestamp"
        assert "level" in record,  "Record must have level"
        assert "logger" in record, "Record must have logger name"
        assert "msg" in record,    "Record must have message"

    def test_timestamp_is_numeric(self):
        h = self._make_handler()
        self._emit(h, "INFO", "test")
        record = h.get_records()[0]
        assert isinstance(record["ts"], float), "Timestamp must be a float (Unix epoch)"
        assert record["ts"] > 1_700_000_000, "Timestamp looks too old — sanity check"

    def test_thread_safety_no_crash(self):
        """Concurrent writes from multiple threads should not crash or corrupt data."""
        import threading
        h = self._make_handler(capacity=1000)
        errors = []

        def write_logs(thread_id):
            try:
                for i in range(50):
                    self._emit(h, "INFO", f"thread {thread_id} msg {i}", logger_name=f"t{thread_id}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=write_logs, args=(i,)) for i in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()

        assert len(errors) == 0, f"Thread safety errors: {errors}"
        # All records should be valid
        records = h.get_records(limit=1000)
        for r in records:
            assert "msg" in r and "level" in r

    def test_empty_buffer_returns_empty_list(self):
        h = self._make_handler()
        assert h.get_records() == []

    def test_level_filter_all_returns_everything(self):
        h = self._make_handler()
        self._emit(h, "INFO", "a")
        self._emit(h, "ERROR", "b")
        all_records = h.get_records(level="ALL")
        assert len(all_records) == 2

    def test_level_filter_empty_string_returns_everything(self):
        h = self._make_handler()
        self._emit(h, "WARNING", "a")
        self._emit(h, "DEBUG", "b")
        all_records = h.get_records(level="")
        assert len(all_records) == 2
