"""
bot_alerts.py — Per-chat alert subscriptions for Telegram & WhatsApp bots.

Stateless w.r.t. user accounts: keyed only by (channel, chat_id). Persisted to
a JSON file so subscriptions survive restarts. The alert tick loop (driven from
main.py lifespan) calls `evaluate_due_alerts` periodically.

Alert types:
  - price_above / price_below      — trigger when stock price crosses a threshold
  - pct_change                     — trigger when |day pChange| >= threshold
  - rsi_above / rsi_below          — trigger when RSI crosses
  - pattern                        — trigger when a CALL/PUT pattern appears
  - sector_rotation                — daily sector rotation digest
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(os.environ.get("MARKET_CACHE_DIR", "market_cache"))
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_STORE = _CACHE_DIR / "bot_alerts.json"

# In-memory cache of subscriptions (loaded at first access)
_lock = asyncio.Lock()
_loaded = False
_subs: list[dict] = []


def _load() -> None:
    global _loaded, _subs
    if _loaded:
        return
    if _STORE.exists():
        try:
            _subs = json.loads(_STORE.read_text())
        except Exception as e:
            logger.warning("bot_alerts: failed to load %s: %s", _STORE, e)
            _subs = []
    _loaded = True


def _save() -> None:
    try:
        _STORE.write_text(json.dumps(_subs, indent=2, default=str))
    except Exception as e:
        logger.warning("bot_alerts: failed to save %s: %s", _STORE, e)


def list_alerts(channel: str, chat_id: str) -> list[dict]:
    _load()
    return [s for s in _subs if s["channel"] == channel and str(s["chat_id"]) == str(chat_id)]


def add_alert(channel: str, chat_id: str, alert: dict) -> dict:
    """alert: {kind, symbol?, threshold?, signal?}"""
    _load()
    sub = {
        "id": f"{int(time.time() * 1000)}-{len(_subs)}",
        "channel": channel,
        "chat_id": str(chat_id),
        "createdAt": int(time.time()),
        "lastFiredAt": 0,
        **alert,
    }
    _subs.append(sub)
    _save()
    return sub


def remove_alert(channel: str, chat_id: str, alert_id: str) -> bool:
    _load()
    before = len(_subs)
    _subs[:] = [
        s for s in _subs
        if not (s["channel"] == channel and str(s["chat_id"]) == str(chat_id) and s["id"] == alert_id)
    ]
    if len(_subs) != before:
        _save()
        return True
    return False


def clear_alerts(channel: str, chat_id: str) -> int:
    _load()
    before = len(_subs)
    _subs[:] = [
        s for s in _subs
        if not (s["channel"] == channel and str(s["chat_id"]) == str(chat_id))
    ]
    n = before - len(_subs)
    if n:
        _save()
    return n


def all_subscriptions() -> list[dict]:
    _load()
    return list(_subs)


def _mark_fired(sub_id: str) -> None:
    _load()
    for s in _subs:
        if s["id"] == sub_id:
            s["lastFiredAt"] = int(time.time())
    _save()


# Re-fire throttle (same alert fires at most once per N seconds)
_FIRE_COOLDOWN_S = 6 * 3600  # 6 hours


async def evaluate_due_alerts(
    quote_fn: Callable[[str], Awaitable[dict]],
    pattern_fn: Optional[Callable[[], Awaitable[dict]]],
    send_fn: Callable[[str, str, str], Awaitable[bool]],
) -> dict:
    """
    Evaluate every active subscription and dispatch a message via send_fn for any
    that fire. Designed to be called every few minutes from the bot scheduler.

    quote_fn(symbol)    -> {lastPrice, pChange, technicalAnalysis: {rsi}}
    pattern_fn()        -> {patterns: [{symbol, signal, pattern, confidence}]}
    send_fn(channel, chat_id, text) -> bool
    """
    _load()
    now = int(time.time())
    fired = 0
    skipped = 0
    errors = 0

    # Group by symbol so we only fetch each quote once
    needed_symbols = {s["symbol"] for s in _subs if s.get("symbol")}
    quotes: dict[str, dict] = {}
    for sym in needed_symbols:
        try:
            quotes[sym] = await quote_fn(sym)
        except Exception as e:
            logger.warning("bot_alerts: quote(%s) failed: %s", sym, e)
            quotes[sym] = {}

    pat_data: dict = {}
    if pattern_fn and any(s["kind"] == "pattern" for s in _subs):
        try:
            pat_data = await pattern_fn()
        except Exception as e:
            logger.warning("bot_alerts: pattern fetch failed: %s", e)

    for sub in list(_subs):
        if sub.get("lastFiredAt", 0) and (now - sub["lastFiredAt"]) < _FIRE_COOLDOWN_S:
            skipped += 1
            continue
        try:
            msg = _eval_one(sub, quotes, pat_data)
            if msg:
                ok = await send_fn(sub["channel"], sub["chat_id"], msg)
                if ok:
                    _mark_fired(sub["id"])
                    fired += 1
        except Exception as e:
            logger.warning("bot_alerts: eval %s failed: %s", sub.get("id"), e)
            errors += 1

    return {"fired": fired, "skipped": skipped, "errors": errors,
            "total": len(_subs)}


def _eval_one(sub: dict, quotes: dict, pat_data: dict) -> Optional[str]:
    kind = sub["kind"]
    sym = sub.get("symbol", "")
    q = quotes.get(sym, {}) if sym else {}
    last = q.get("lastPrice")

    if kind == "price_above" and last is not None:
        if float(last) >= float(sub["threshold"]):
            return f"🔔 {sym}: price ₹{last:.2f} ≥ ₹{sub['threshold']:.2f}"
    elif kind == "price_below" and last is not None:
        if float(last) <= float(sub["threshold"]):
            return f"🔔 {sym}: price ₹{last:.2f} ≤ ₹{sub['threshold']:.2f}"
    elif kind == "pct_change" and q.get("pChange") is not None:
        if abs(float(q["pChange"])) >= float(sub["threshold"]):
            return f"🔔 {sym}: day change {q['pChange']:+.2f}% (|chg| ≥ {sub['threshold']}%)"
    elif kind == "rsi_above":
        rsi = (q.get("technicalAnalysis") or {}).get("rsi")
        if rsi is not None and float(rsi) >= float(sub["threshold"]):
            return f"🔔 {sym}: RSI {rsi:.1f} ≥ {sub['threshold']:.0f}"
    elif kind == "rsi_below":
        rsi = (q.get("technicalAnalysis") or {}).get("rsi")
        if rsi is not None and float(rsi) <= float(sub["threshold"]):
            return f"🔔 {sym}: RSI {rsi:.1f} ≤ {sub['threshold']:.0f}"
    elif kind == "pattern":
        signal = sub.get("signal")  # "CALL" | "PUT" | None
        for p in (pat_data.get("patterns") or []):
            if sym and p.get("symbol") != sym:
                continue
            if signal and p.get("signal") != signal:
                continue
            return (f"🔔 Pattern alert: {p.get('symbol')} — "
                    f"{p.get('pattern')} ({p.get('signal')}, "
                    f"{p.get('confidence', 0):.0f}%)")
    return None
