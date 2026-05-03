"""
Telegram bot service.

Channel-specific layer: handles Telegram Bot API I/O (send/receive,
webhook/long-polling), tier-aware Markdown rendering for the rotation report,
and inline-keyboard rendering for follow-up actions.

All command logic and NLP routing lives in `bot_dispatcher.BotDispatcher`,
which is shared with the WhatsApp bot. This module simply delegates and
renders the resulting `BotResponse`.
"""
from __future__ import annotations
import os
import re as _re
from datetime import datetime
from typing import Any, Optional
import httpx

from .nlp_service import NlpService
from .stocks_service import StocksService
from .sectors_service import SectorsService
from .patterns_service import PatternsService
from .scanners_service import ScannersService

MAX_LOG = 100
_message_log: list[dict] = []

# ── Tier metadata (used by _format_rotation_message imported by dispatcher) ──
_TIER_META = {
    "DEEP_GREEN":  {"emoji": "🟢", "label": "DEEP GREEN",  "action": "Consider trimming profits"},
    "LIGHT_GREEN": {"emoji": "🟩", "label": "LIGHT GREEN", "action": "← Ideal entry zone"},
    "YELLOW":      {"emoji": "🟡", "label": "NEUTRAL",     "action": "Hold existing positions"},
    "ORANGE":      {"emoji": "🟠", "label": "WEAKENING",   "action": "Reduce / set tighter SL"},
    "DEEP_RED":    {"emoji": "🔴", "label": "DEEP RED",    "action": "Avoid / Exit now"},
}
_TIER_ORDER = ["DEEP_GREEN", "LIGHT_GREEN", "YELLOW", "ORANGE", "DEEP_RED"]


def _breadth_bar(adv: int, total: int, width: int = 16) -> str:
    if total <= 0:
        return "░" * width
    filled = round((adv / total) * width)
    return "▰" * filled + "░" * (width - filled)


def _format_rotation_message(r: dict) -> str:
    """Rich Markdown sector-rotation report. Imported by bot_dispatcher."""
    SEP = "━━━━━━━━━━━━━━━━━━━━"
    date_str = r.get("date", "")
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        date_str = dt.strftime("%d %b %Y")
    except Exception:
        pass
    lines = [
        f"📊 *SECTOR ROTATION REPORT — NSE*",
        f"_{date_str}_",
        SEP,
    ]
    eco = r.get("economicPhase", {}) or {}
    phase = eco.get("phase", "Unknown"); conf = eco.get("confidence", 0)
    chars = eco.get("characteristics", ""); strat = eco.get("strategy", "")
    theory = eco.get("theorySectors", []) or []
    phase_emoji = {"EARLY": "🌱", "MID": "🚀", "LATE": "🌅", "RECESSION": "🛡"}.get(
        eco.get("code", ""), "📍"
    )
    conf_bar = "🔵" * (conf // 20) + "⚪" * (5 - conf // 20)
    lines += [
        f"{phase_emoji} *ECONOMIC CYCLE: {phase.upper()}*",
        f"Confidence: *{conf}%* {conf_bar}",
        f"_{chars}_",
        "",
        f"📌 *Theoretically favored:* {' · '.join(theory)}",
        f"📋 *Strategy:* {strat}",
        SEP,
    ]
    breadth = r.get("marketBreadth", {}) or {}
    adv = breadth.get("advancing", 0); dec = breadth.get("declining", 0)
    flat = breadth.get("unchanged", 0); total = adv + dec + flat or 1
    bar = _breadth_bar(adv, total); pct_adv = round(adv / total * 100)
    lines += [
        f"📊 *MARKET BREADTH*",
        f"🟢 {adv} Rising  🔴 {dec} Falling  ➡️ {flat} Flat",
        f"`{bar}` {pct_adv}%",
        SEP,
    ]
    sectors = r.get("sectors", []) or []
    by_tier: dict[str, list] = {t: [] for t in _TIER_ORDER}
    for s in sectors:
        tier = (s.get("momentum", {}) or {}).get("tier", "YELLOW")
        if tier in by_tier:
            by_tier[tier].append(s)
    lines.append(f"🔢 *SECTOR STRENGTH MATRIX*")
    for tier_key in _TIER_ORDER:
        meta = _TIER_META[tier_key]
        members = by_tier[tier_key]
        if not members:
            continue
        lines.append(
            f"\n{meta['emoji']} *{meta['label']}* ({len(members)})  _{meta['action']}_"
        )
        if tier_key in ("DEEP_GREEN", "LIGHT_GREEN"):
            for s in members:
                ms = s.get("momentum", {}) or {}
                name = s["name"].replace("Nifty ", "")
                rs = ms.get("rs", 0); roc = ms.get("roc_6m", 0)
                b200 = ms.get("pct_above_200", 0); pc = s.get("pChange", 0)
                action_icon = "🔥" if tier_key == "DEEP_GREEN" else "✅"
                lines.append(
                    f"  {action_icon} *{name}*  Today {pc:+.2f}% | "
                    f"RS {rs:+.1f}% | ROC {roc:+.1f}% | {b200:.0f}% >200SMA"
                )
        else:
            names = " · ".join(s["name"].replace("Nifty ", "") for s in members)
            icon = {"YELLOW": "⏸", "ORANGE": "⚠️", "DEEP_RED": "❌"}[tier_key]
            lines.append(f"  {icon} {names}")
    lines.append(SEP)
    ps = r.get("portfolioStrategy", {}) or {}
    picks = ps.get("topPicks", []) or []
    risk = ps.get("riskManagement", {}) or {}
    focused = ps.get("currentlyFocused", []) or []
    lines += [
        f"🎯 *PORTFOLIO STRATEGY — CORE-SATELLITE*",
        f"  🏛 *Core (60-70%):* Nifty 50 ETF (NIFTYBEES / NIFTY50 ETF)",
        f"  🛰 *Satellite (30-40%):* Active sector rotation into momentum leaders",
        f"  💵 *Cash reserve (5-10%):* Held for dip-buying opportunities",
    ]
    if picks:
        lines.append(f"\n🏆 *TOP ENTRY CANDIDATES*")
        for p in picks:
            sector = p.get("sector", "?").replace("Nifty ", "")
            theory_tag = "  ✓ _Theory match_" if p.get("theoryMatch") else ""
            lines += [
                "",
                f"  ➤ *{sector}*{theory_tag}",
                f"    RS {p.get('rs', 0):+.1f}% | ROC {p.get('roc_6m', 0):+.1f}% "
                f"| {p.get('pct_above_200', 0):.0f}% >200SMA",
                f"    Max alloc: _{p.get('maxAllocation', '15-25%')}_",
                f"    Entry: _{p.get('entryReason', '')}_",
                f"    Exit: _{p.get('exitRule', '')}_",
            ]
    elif focused:
        lines.append(f"\n🏆 *CURRENTLY FOCUSED:* {' · '.join(focused)}")
    lines += [
        "",
        f"🔒 *Risk Management Rules*",
        f"  • SL: _{risk.get('stopLoss', '7-10% below entry')}_",
        f"  • Profit: _{risk.get('profitTaking', 'Trim at Deep Green transition')}_",
        f"  • Exit: _{risk.get('exitSignal', 'Full exit on Orange/Red tier')}_",
        f"  • Max/sector: _{risk.get('maxPerSector', '15-25% of total portfolio')}_",
        f"  • Max/stock: _{risk.get('maxPerStock', '5% per individual stock')}_",
        SEP,
        f"_Powered by NSE Analyzer · /sectors for live prices · /analyze SYMBOL_",
    ]
    return "\n".join(lines)


def _log(from_user: str, text: str, response: str) -> None:
    _message_log.append({
        "from": from_user, "text": text, "response": response,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    })
    if len(_message_log) > MAX_LOG:
        _message_log.pop(0)


class TelegramService:
    def __init__(
        self,
        sectors: SectorsService,
        stocks: StocksService,
        patterns: PatternsService,
        scanners: ScannersService,
        nlp: NlpService,
        dispatcher: Optional[Any] = None,
    ) -> None:
        self.sectors = sectors
        self.stocks = stocks
        self.patterns = patterns
        self.scanners = scanners
        self.nlp = nlp
        self.dispatcher = dispatcher  # bot_dispatcher.BotDispatcher
        self._token: Optional[str] = os.environ.get("TELEGRAM_BOT_TOKEN", "")

    def set_dispatcher(self, dispatcher: Any) -> None:
        self.dispatcher = dispatcher

    @property
    def token(self) -> Optional[str]:
        try:
            from app.lib.secrets_store import get_secret  # noqa: PLC0415
            return get_secret("TELEGRAM_BOT_TOKEN", self._token or "")
        except Exception:
            return os.environ.get("TELEGRAM_BOT_TOKEN", self._token or "")

    @property
    def configured(self) -> bool:
        return bool(self.token and len(self.token) > 10)

    # ── Telegram REST helpers ────────────────────────────────────────────────

    async def send_message(self, chat_id: int | str, text: str,
                           reply_markup: Optional[dict] = None) -> bool:
        if not self.configured:
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": chat_id, "text": text, "parse_mode": "Markdown",
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    return True
        except Exception:
            pass
        # Fallback: strip Markdown
        plain = _re.sub(r"[*_`]", "", text)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    json={"chat_id": chat_id, "text": plain,
                          "reply_markup": reply_markup} if reply_markup
                    else {"chat_id": chat_id, "text": plain},
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def get_bot_info(self) -> dict:
        if not self.configured:
            return {"configured": False, "error": "TELEGRAM_BOT_TOKEN not set"}
        try:
            url = f"https://api.telegram.org/bot{self.token}/getMe"
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json().get("result", {})
                    return {
                        "configured": True,
                        "botName": data.get("first_name", "Bot"),
                        "username": data.get("username", ""),
                        "botId": data.get("id"),
                        "canJoinGroups": data.get("can_join_groups", False),
                    }
                return {"configured": True, "error": "Invalid token"}
        except Exception as e:
            return {"configured": True, "error": str(e)}

    async def delete_webhook(self) -> bool:
        if not self.configured:
            return False
        try:
            url = f"https://api.telegram.org/bot{self.token}/deleteWebhook"
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(url, json={"drop_pending_updates": False})
                return resp.status_code == 200
        except Exception:
            return False

    async def get_updates(self, offset: int = 0, timeout: int = 25
                          ) -> tuple[list[dict], int]:
        if not self.configured:
            return [], offset
        try:
            url = f"https://api.telegram.org/bot{self.token}/getUpdates"
            params = {"offset": offset, "timeout": timeout,
                      "allowed_updates": ["message"]}
            async with httpx.AsyncClient(timeout=timeout + 5.0) as client:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    return [], offset
                updates = resp.json().get("result", [])
                next_offset = updates[-1]["update_id"] + 1 if updates else offset
                return updates, next_offset
        except Exception:
            return [], offset

    async def set_webhook(self, webhook_url: str) -> dict:
        if not self.configured:
            return {"success": False, "error": "TELEGRAM_BOT_TOKEN not set"}
        try:
            url = f"https://api.telegram.org/bot{self.token}/setWebhook"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json={"url": webhook_url})
                data = resp.json()
                return {
                    "success": data.get("ok", False),
                    "description": data.get("description", ""),
                    "webhookUrl": webhook_url,
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_webhook_info(self) -> dict:
        if not self.configured:
            return {"configured": False}
        try:
            url = f"https://api.telegram.org/bot{self.token}/getWebhookInfo"
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    info = resp.json().get("result", {})
                    return {
                        "configured": True,
                        "webhookUrl": info.get("url", ""),
                        "hasWebhook": bool(info.get("url")),
                        "pendingUpdates": info.get("pending_update_count", 0),
                        "lastError": info.get("last_error_message", ""),
                    }
        except Exception:
            pass
        return {"configured": True, "webhookUrl": "", "hasWebhook": False}

    # ── Status / logging ─────────────────────────────────────────────────────

    def get_status(self) -> dict:
        registry: list[dict] = []
        counts: dict[str, int] = {}
        if self.dispatcher is not None:
            registry = self.dispatcher.registry()
            counts = self.dispatcher.invocation_counts()
        return {
            "configured": self.configured,
            "enabled": self.configured,
            "totalMessages": len(_message_log),
            "recentMessages": _message_log[-5:] if _message_log else [],
            "commandRegistry": registry,
            "invocationCounts": counts,
            "totalCommands": len(registry),
            "capabilities": [
                "Stock analysis (EMA, RSI, MACD, Bollinger Bands)",
                "Sector rotation & performance",
                "Chart pattern detection (CALL/PUT signals)",
                "Custom scanner execution",
                "Options greeks, payoff & cost",
                "Stateless portfolio P&L and VaR (inline holdings)",
                "Forecast, pairs, backtest, sentiment via Hydra",
                "Per-chat alerts (price / RSI / pattern)",
                "Natural language queries via NLP",
            ],
            # Backwards-compat: simple list for older UI code
            "commands": [f"/{c['name']} — {c['summary']}" for c in registry],
        }

    def get_message_log(self) -> list[dict]:
        return list(reversed(_message_log))

    # ── Convenience helpers used by routes ───────────────────────────────────

    async def test_message(self, text: str) -> dict:
        """Run text through the dispatcher without sending it anywhere."""
        if self.dispatcher is None:
            return {"reply": "Bot dispatcher not initialised", "actions": []}
        resp = await self.dispatcher.dispatch("telegram", "preview", text)
        return {
            "reply": resp.text,
            "error": resp.error,
            "actions": [{"label": a.label, "command": a.command}
                        for a in resp.actions],
        }

    async def get_rotation_message(self) -> dict:
        try:
            r = await self.sectors.get_sector_rotation()
            return {"text": _format_rotation_message(r)}
        except Exception as e:
            return {"error": str(e)}

    async def send_rotation_alert(self, chat_id: str) -> dict:
        msg = await self.get_rotation_message()
        if "error" in msg:
            return {"ok": False, **msg}
        ok = await self.send_message(chat_id, msg["text"])
        return {"ok": ok, "chatId": chat_id}

    # ── Update processing (delegates to dispatcher) ──────────────────────────

    async def process_update(self, update: dict) -> Optional[str]:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return None
        text = (message.get("text") or "").strip()
        chat_id = message.get("chat", {}).get("id")
        from_user = message.get("from", {}) or {}
        username = (from_user.get("username")
                    or from_user.get("first_name") or "user")
        if not text or not chat_id:
            return None

        if self.dispatcher is None:
            reply_text = ("Bot is starting up — please retry in a moment.")
            await self.send_message(chat_id, reply_text)
            return reply_text

        resp = await self.dispatcher.dispatch("telegram", str(chat_id), text)
        markup = _build_inline_keyboard(resp.actions)
        await self.send_message(chat_id, resp.text, reply_markup=markup)
        _log(f"@{username}", text, resp.text)
        return resp.text


def _build_inline_keyboard(actions) -> Optional[dict]:
    """Render a list[BotAction] as a Telegram inline_keyboard markup.

    Each button sends back the literal command text via switch_inline_query_current_chat
    isn't available for plain text replies, so we fall back to the simplest UX:
    each button becomes an inline keyboard with a `callback_data`-less url-style
    button. To keep this working without a callback handler, we use the
    `switch_inline_query_current_chat` field which pre-fills the input box, OR
    just label it so the user knows what to type. We default to pre-filling
    the chat input so a single tap is enough.
    """
    if not actions:
        return None
    rows = []
    cur: list[dict] = []
    for a in actions[:8]:  # cap UI width
        cur.append({
            "text": a.label,
            "switch_inline_query_current_chat": a.command,
        })
        if len(cur) == 2:
            rows.append(cur); cur = []
    if cur:
        rows.append(cur)
    return {"inline_keyboard": rows}
