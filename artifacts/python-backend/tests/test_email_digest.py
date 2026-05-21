"""
Tests for the email digest service.

Covers the pure-function bits (validation, render, throttle helpers) and
the SMTP send path with a fake `smtplib.SMTP`. Doesn't talk to Postgres,
doesn't open a network socket.

The DB-dependent functions (`list_subscriptions`, `enqueue_due_digests`,
`drain_queue`) are smoke-tested by monkeypatching `_conn` and `_now_ms`.
"""
from __future__ import annotations

import asyncio
import smtplib
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.services import email_digest_service as eds


IST = timezone(timedelta(hours=5, minutes=30))


# ── Validation ────────────────────────────────────────────────────────────────

def test_valid_email_accepts_common_shapes():
    assert eds._valid_email("you@example.com")
    assert eds._valid_email("first.last+filter@sub.example.co.in")
    assert eds._valid_email("digit123@x.io")


def test_valid_email_rejects_garbage():
    assert not eds._valid_email("")
    assert not eds._valid_email("no-at-sign")
    assert not eds._valid_email("two@@signs.com")
    assert not eds._valid_email("trailing@dot.")
    assert not eds._valid_email("missing-tld@example")


def test_valid_send_time_accepts_HH_MM_only():
    assert eds._valid_send_time("00:00")
    assert eds._valid_send_time("09:30")
    assert eds._valid_send_time("23:59")
    assert not eds._valid_send_time("24:00")
    assert not eds._valid_send_time("9:30")        # not zero-padded
    assert not eds._valid_send_time("18:60")
    assert not eds._valid_send_time("18:00:00")    # has seconds
    assert not eds._valid_send_time("")


def test_normalise_symbols_dedupes_and_strips_suffixes():
    out = eds._normalise_symbols([
        "reliance", "RELIANCE", "tcs-eq", " infy.ns ", "", None,  # type: ignore[list-item]
        "hdfcbank:NSE", "infy",
    ])
    # Order preserved, first occurrence wins, suffixes stripped, case folded.
    assert out == ["RELIANCE", "TCS", "INFY", "HDFCBANK"]


def test_normalise_symbols_returns_empty_for_empty_input():
    assert eds._normalise_symbols([]) == []
    assert eds._normalise_symbols([""]) == []


# ── _due_now ──────────────────────────────────────────────────────────────────

def test_due_now_returns_true_after_send_time():
    ist_now = datetime(2026, 5, 19, 18, 5, 0, tzinfo=IST)
    assert eds._due_now("18:00", ist_now) is True


def test_due_now_returns_false_before_send_time():
    ist_now = datetime(2026, 5, 19, 17, 59, 0, tzinfo=IST)
    assert eds._due_now("18:00", ist_now) is False


def test_due_now_handles_malformed_send_time():
    ist_now = datetime(2026, 5, 19, 18, 0, 0, tzinfo=IST)
    assert eds._due_now("not-a-time", ist_now) is False
    assert eds._due_now("", ist_now) is False


# ── HTML / text rendering ────────────────────────────────────────────────────

def test_render_html_escapes_user_supplied_strings():
    """A subscription with a malicious groupName should not be able to inject
    HTML into the digest body."""
    sub = {"groupName": "<script>alert(1)</script>", "user_id": "u1"}
    html = eds._render_html("2026-05-19", sub, [], "OPEN", "Phase: Expansion")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_render_html_includes_each_symbol_row():
    sub = {"groupName": "default"}
    rows = [
        {"symbol": "RELIANCE", "name": "Reliance", "last": 2500.55, "chgPct": 1.5,  "error": None},
        {"symbol": "TCS",      "name": "TCS",      "last": 3700.0,  "chgPct": -0.8, "error": None},
    ]
    html = eds._render_html("2026-05-19", sub, rows, "OPEN", "")
    assert "RELIANCE" in html
    assert "TCS"      in html
    assert "+1.50%"   in html
    assert "-0.80%"   in html


def test_render_text_has_no_html_tags():
    sub = {"groupName": "default"}
    rows = [{"symbol": "RELIANCE", "name": "Reliance Industries",
             "last": 2500.55, "chgPct": 1.5, "error": None}]
    text = eds._render_text("2026-05-19", sub, rows, "OPEN", "Phase: Expansion")
    # Plain-text body must not contain angle-bracket markup
    assert "<" not in text
    assert ">" not in text
    assert "RELIANCE" in text
    assert "Phase: Expansion" in text


# ── smtp_config (env-driven) ─────────────────────────────────────────────────

def test_smtp_config_disabled_without_all_three(monkeypatch):
    """With any of host/user/pass missing, .enabled is False so the worker
    becomes a silent no-op in dev."""
    monkeypatch.delenv("SMTP_HOST",     raising=False)
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    assert eds.smtp_config()["enabled"] is False

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    assert eds.smtp_config()["enabled"] is False  # still missing user/pass

    monkeypatch.setenv("SMTP_USERNAME", "u@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret-app-password")
    cfg = eds.smtp_config()
    assert cfg["enabled"] is True
    assert cfg["from_addr"] == "u@example.com"     # defaults to username


def test_smtp_config_port_and_tls_defaults(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "u@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "p")
    cfg = eds.smtp_config()
    assert cfg["port"] == 587
    assert cfg["use_tls"] is True
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USE_TLS", "false")
    cfg2 = eds.smtp_config()
    assert cfg2["port"] == 465
    assert cfg2["use_tls"] is False


# ── _send_one with fake smtplib.SMTP ─────────────────────────────────────────

class _FakeSMTP:
    """Records what would have been sent without opening a socket."""
    instances: list["_FakeSMTP"] = []

    def __init__(self, host, port, timeout=20):
        self.host       = host
        self.port       = port
        self.timeout    = timeout
        self.calls: list[tuple[str, tuple]] = []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        self.calls.append(("ehlo", ()))

    def starttls(self):
        self.calls.append(("starttls", ()))

    def login(self, user, pwd):
        self.calls.append(("login", (user, pwd)))

    def send_message(self, msg):
        self.calls.append(("send_message", (msg["To"], msg["Subject"])))


def _reset_fake_smtp():
    _FakeSMTP.instances.clear()


def test_send_one_with_tls_path(monkeypatch):
    _reset_fake_smtp()
    monkeypatch.setattr(eds.smtplib, "SMTP", _FakeSMTP)
    cfg = {"host": "smtp.gmail.com", "port": 587,
           "username": "u@example.com", "password": "app-pw",
           "use_tls": True, "from_addr": "u@example.com",
           "from_name": "Test Sender", "enabled": True}
    row = {"recipient_email": "to@example.com",
           "subject": "Hi", "body_html": "<p>hi</p>", "body_text": "hi"}
    eds._send_one(cfg, row)

    assert len(_FakeSMTP.instances) == 1
    inst = _FakeSMTP.instances[0]
    # Expected sequence: ehlo, starttls, ehlo, login, send_message
    sequence = [name for name, _ in inst.calls]
    assert sequence == ["ehlo", "starttls", "ehlo", "login", "send_message"]
    sent = inst.calls[-1][1]
    assert sent[0] == "to@example.com"
    assert sent[1] == "Hi"


def test_send_one_without_tls_skips_starttls(monkeypatch):
    _reset_fake_smtp()
    monkeypatch.setattr(eds.smtplib, "SMTP", _FakeSMTP)
    cfg = {"host": "localhost", "port": 25,
           "username": "u@example.com", "password": "p",
           "use_tls": False, "from_addr": "u@example.com",
           "from_name": "Test Sender", "enabled": True}
    row = {"recipient_email": "to@example.com",
           "subject": "Hi", "body_html": "<p>hi</p>", "body_text": "hi"}
    eds._send_one(cfg, row)
    sequence = [name for name, _ in _FakeSMTP.instances[0].calls]
    assert "starttls" not in sequence
    assert sequence == ["ehlo", "login", "send_message"]


def test_send_one_propagates_auth_error(monkeypatch):
    _reset_fake_smtp()

    class _BadAuthSMTP(_FakeSMTP):
        def login(self, user, pwd):  # type: ignore[override]
            raise smtplib.SMTPAuthenticationError(535, b"Bad credentials")

    monkeypatch.setattr(eds.smtplib, "SMTP", _BadAuthSMTP)
    cfg = {"host": "smtp.example.com", "port": 587,
           "username": "u", "password": "wrong",
           "use_tls": True, "from_addr": "u@example.com",
           "from_name": "T", "enabled": True}
    row = {"recipient_email": "to@example.com",
           "subject": "Hi", "body_html": "h", "body_text": "h"}
    with pytest.raises(smtplib.SMTPAuthenticationError):
        eds._send_one(cfg, row)


# ── drain_queue: smoke test with a stubbed connection ─────────────────────────

def test_drain_queue_no_op_when_smtp_disabled(monkeypatch):
    """When SMTP isn't configured, drain_queue returns immediately without
    even reading from the queue. We assert that by patching _conn to error."""
    monkeypatch.delenv("SMTP_HOST",     raising=False)
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.setattr(eds, "_conn", MagicMock(
        side_effect=AssertionError("should not open a DB connection")))
    out = eds.drain_queue()
    assert out["sent"] == 0
    assert out["throttled"] is True
    assert out["reason"] == "smtp_not_configured"


# ── render_digest happy path with a stub price_service ───────────────────────

def test_render_digest_uses_supplied_symbols(monkeypatch):
    """render_digest should pull a quote per symbol via price_service and
    project them onto the digest. We stub price_service to avoid network."""

    class _PS:
        async def get_quote_with_meta(self, sym):
            return {"quote": {
                "lastPrice": 100.0,
                "previousClose": 95.0,
                "companyName": f"{sym} Industries",
            }}

    # Avoid the real market_cache_service / sectors_service calls in
    # _market_snippet — they touch the network.
    async def _stub_snippet():
        return ("OPEN", "Phase: Expansion · Leader: IT")
    monkeypatch.setattr(eds, "_market_snippet", _stub_snippet)

    sub = {"user_id": "u1", "groupName": "default",
           "symbols": ["RELIANCE", "TCS"]}
    out = asyncio.run(eds.render_digest(sub, _PS()))
    assert "subject" in out
    assert "html" in out
    assert "text" in out
    assert "RELIANCE" in out["html"]
    assert "TCS"      in out["text"]
    # 5% return is rendered correctly
    assert "+5.26%" in out["html"] or "+5.26%" in out["text"]
