"""
WhatsApp bot service.

Channel-specific layer: minimal session/QR plumbing plus numbered-menu rendering
for the dispatcher's BotAction lists. All command/NLP logic lives in
`bot_dispatcher.BotDispatcher`, shared with the Telegram bot.

Numeric replies (1, 2, 3 …) re-trigger the corresponding action from the
previous reply, so users don't need to type full commands.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from .nlp_service import NlpService
from .sectors_service import SectorsService
from .stocks_service import StocksService
from .patterns_service import PatternsService
from .scanners_service import ScannersService

MAX_LOG = 200
_message_log: list[dict] = []

_bot_enabled = True
_session_qr: Optional[str] = None
_session_status = "DISCONNECTED"

# Per-chat memory of the last-rendered action menu so numeric replies work
_last_actions: dict[str, list[Any]] = {}


class WhatsappService:
    def __init__(
        self,
        sectors: SectorsService,
        stocks: StocksService,
        patterns: PatternsService,
        scanners: ScannersService,
        nlp: Optional[NlpService] = None,
        dispatcher: Optional[Any] = None,
    ):
        self.sectors = sectors
        self.stocks = stocks
        self.patterns = patterns
        self.scanners = scanners
        self.nlp = nlp
        self.dispatcher = dispatcher

    def set_dispatcher(self, dispatcher: Any) -> None:
        self.dispatcher = dispatcher

    def get_bot_status(self) -> dict:
        registry: list[dict] = []
        counts: dict[str, int] = {}
        if self.dispatcher is not None:
            registry = self.dispatcher.registry()
            counts = self.dispatcher.invocation_counts()
        return {
            "status": _session_status if _bot_enabled else "DISABLED",
            "enabled": _bot_enabled,
            "qrCode": _session_qr,
            "sessionActive": _session_status == "CONNECTED",
            "lastActive": _message_log[-1]["timestamp"] if _message_log else None,
            "totalMessages": len(_message_log),
            "commandRegistry": registry,
            "invocationCounts": counts,
            "totalCommands": len(registry),
            "capabilities": [
                "Stock analysis", "Sector rotation", "Pattern scan",
                "Custom scanners", "Options greeks/payoff/cost",
                "Stateless portfolio P&L & VaR", "Per-chat alerts",
                "Natural language queries",
            ],
            "commands": [f"!{c['name']} — {c['summary']}" for c in registry],
        }

    async def process_message(self, body: dict) -> dict:
        from_ = body.get("from") or "unknown-user"
        text = (body.get("message") or body.get("text") or "").strip()
        if not text:
            raise ValueError("No message text provided")

        start = datetime.utcnow()
        try:
            response = await self._route(from_, text)
        except Exception as e:
            response = f"Error processing request: {e}"
        elapsed = int((datetime.utcnow() - start).total_seconds() * 1000)

        entry = {
            "from": from_, "text": text,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "response": response,
        }
        _message_log.append(entry)
        if len(_message_log) > MAX_LOG:
            del _message_log[:len(_message_log) - MAX_LOG]
        return {**entry, "processingTime": f"{elapsed}ms"}

    async def _route(self, from_: str, raw: str) -> str:
        # Numeric reply → re-issue the Nth previous action
        stripped = raw.strip()
        if stripped.isdigit():
            actions = _last_actions.get(from_, [])
            idx = int(stripped) - 1
            if 0 <= idx < len(actions):
                raw = actions[idx].command  # re-route as the command text
            else:
                return ("That number isn't on the menu — type !help to see "
                        "everything you can do.")

        # Strip leading bang so the dispatcher's `/`-aware splitter matches
        norm = raw
        if norm.startswith("!"):
            norm = "/" + norm[1:]

        if self.dispatcher is None:
            return "Bot is starting up — please retry in a moment."

        resp = await self.dispatcher.dispatch("whatsapp", str(from_), norm)
        text = resp.text
        if resp.actions:
            menu = "\n".join(
                f"{i+1}. {a.label}" for i, a in enumerate(resp.actions[:8])
            )
            text = f"{text}\n\n_Reply with a number:_\n{menu}"
            _last_actions[from_] = list(resp.actions[:8])
        else:
            _last_actions.pop(from_, None)
        return text

    # ── Session/QR ───────────────────────────────────────────────────────────

    def get_message_log(self) -> list[dict]:
        return _message_log[-50:]

    def simulate_qr_code(self) -> dict:
        global _session_qr, _session_status
        _session_qr = f"SIMULATED_QR_{int(datetime.utcnow().timestamp() * 1000)}"
        _session_status = "WAITING_FOR_QR_SCAN"
        return {"qrCode": _session_qr, "status": _session_status,
                "message": "Scan with WhatsApp to connect"}

    def update_bot_status(self, enabled: bool) -> dict:
        global _bot_enabled
        _bot_enabled = enabled
        return {"enabled": _bot_enabled,
                "status": _session_status if _bot_enabled else "DISABLED"}
