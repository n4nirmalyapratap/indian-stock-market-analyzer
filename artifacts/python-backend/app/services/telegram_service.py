"""
Telegram bot service.
Uses Telegram Bot API via httpx (no extra library needed).
Supports NLP for natural language queries.
"""
from __future__ import annotations
import os
import time
import html
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


def _log(from_user: str, text: str, response: str) -> None:
    _message_log.append({
        "from": from_user,
        "text": text,
        "response": response,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    })
    if len(_message_log) > MAX_LOG:
        _message_log.pop(0)


def _fmt_price(v: Any) -> str:
    try:
        return f"₹{float(v):,.2f}"
    except Exception:
        return str(v) if v is not None else "N/A"


def _fmt_pct(v: Any) -> str:
    try:
        f = float(v)
        sign = "+" if f >= 0 else ""
        return f"{sign}{f:.2f}%"
    except Exception:
        return str(v) if v is not None else "N/A"


def _safe(v: Any) -> str:
    """Convert value to string safe for Telegram Markdown v1.
    Replaces underscores (italic markers) with spaces."""
    return str(v).replace("_", " ") if v is not None else "N/A"


class TelegramService:
    def __init__(
        self,
        sectors: SectorsService,
        stocks: StocksService,
        patterns: PatternsService,
        scanners: ScannersService,
        nlp: NlpService,
    ) -> None:
        self.sectors = sectors
        self.stocks = stocks
        self.patterns = patterns
        self.scanners = scanners
        self.nlp = nlp
        self._token: Optional[str] = os.environ.get("TELEGRAM_BOT_TOKEN", "")

    @property
    def token(self) -> Optional[str]:
        return os.environ.get("TELEGRAM_BOT_TOKEN", self._token or "")

    @property
    def configured(self) -> bool:
        return bool(self.token and len(self.token) > 10)

    async def send_message(self, chat_id: int | str, text: str) -> bool:
        if not self.configured:
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        # Attempt 1: Markdown mode
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                })
                if resp.status_code == 200:
                    return True
                # Markdown parse failed → strip and retry as plain text
        except Exception:
            pass
        # Attempt 2: plain text (strip common Markdown markers)
        import re as _re
        plain = _re.sub(r"[*_`]", "", text)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json={
                    "chat_id": chat_id,
                    "text": plain,
                })
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
        """Remove any existing webhook so long-polling works."""
        if not self.configured:
            return False
        try:
            url = f"https://api.telegram.org/bot{self.token}/deleteWebhook"
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(url, json={"drop_pending_updates": False})
                return resp.status_code == 200
        except Exception:
            return False

    async def get_updates(self, offset: int = 0, timeout: int = 25) -> tuple[list[dict], int]:
        """Long-poll Telegram for new updates. Returns (updates, next_offset)."""
        if not self.configured:
            return [], offset
        try:
            url = f"https://api.telegram.org/bot{self.token}/getUpdates"
            params = {"offset": offset, "timeout": timeout, "allowed_updates": ["message"]}
            async with httpx.AsyncClient(timeout=timeout + 5.0) as client:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    return [], offset
                data = resp.json()
                updates = data.get("result", [])
                if updates:
                    next_offset = updates[-1]["update_id"] + 1
                else:
                    next_offset = offset
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

    def get_status(self) -> dict:
        return {
            "configured": self.configured,
            "enabled": self.configured,
            "totalMessages": len(_message_log),
            "recentMessages": _message_log[-5:] if _message_log else [],
            "capabilities": [
                "Stock analysis (EMA, RSI, MACD, Bollinger Bands)",
                "Sector rotation & performance",
                "Chart pattern detection (CALL/PUT signals)",
                "Custom scanner execution",
                "Natural language queries via NLP",
                "Analytics: sector correlation, top movers, heatmap",
            ],
            "commands": [
                "/start — Welcome message",
                "/help — All commands",
                "/sectors — Sector overview",
                "/rotation — Sector rotation analysis",
                "/analyze SYMBOL — Full stock analysis",
                "/entry SYMBOL — Entry/exit signal",
                "/patterns — Chart patterns (CALL/PUT)",
                "/scan — Trigger fresh pattern scan",
                "/movers — Top gainers & losers",
                "/heatmap — Sector heatmap",
            ],
        }

    def get_message_log(self) -> list[dict]:
        return list(reversed(_message_log))

    async def process_update(self, update: dict) -> Optional[str]:
        """Process a Telegram update dict. Returns reply text or None."""
        message = update.get("message") or update.get("edited_message")
        if not message:
            return None

        text = (message.get("text") or "").strip()
        chat_id = message.get("chat", {}).get("id")
        from_user = message.get("from", {})
        username = from_user.get("username") or from_user.get("first_name") or "user"

        if not text or not chat_id:
            return None

        reply = await self._build_reply(text)
        _log(f"@{username}", text, reply)
        await self.send_message(chat_id, reply)
        return reply

    async def _build_reply(self, text: str) -> str:
        cmd = text.split()[0].lower().lstrip("/")
        args = text.split()[1:] if len(text.split()) > 1 else []

        # ── Exact command handlers ─────────────────────────────────────────────
        if cmd in ("start",):
            return (
                "🤖 *Indian Stock Market Bot*\n\n"
                "I provide real-time NSE market data with NLP support.\n\n"
                "Type /help to see all commands, or just ask me naturally:\n"
                "_'analyze RELIANCE'_, _'which sectors are up?'_, _'bullish patterns'_"
            )

        if cmd in ("help",):
            return (
                "🤖 *Indian Stock Market Bot — Commands*\n\n"
                "*Stock Analysis:*\n"
                "/analyze `SYMBOL` — Full technical analysis\n"
                "/entry `SYMBOL` — Entry/exit recommendation\n\n"
                "*Market Overview:*\n"
                "/sectors — All sector performance\n"
                "/rotation — Sector rotation & where to buy\n"
                "/movers — Top gainers & losers\n"
                "/heatmap — Sector % change heatmap\n\n"
                "*Signals & Scanners:*\n"
                "/patterns — CALL/PUT chart patterns\n"
                "/scan — Trigger fresh pattern scan\n\n"
                "*Natural Language (just type):*\n"
                "_'analyze TCS'_, _'IT sector'_, _'where to invest?'_\n"
                "_'bullish stocks'_, _'RELIANCE analysis'_"
            )

        if cmd == "sectors":
            return await self._sectors_reply()

        if cmd == "rotation":
            return await self._rotation_reply()

        if cmd in ("analyze", "a") and args:
            raw_sym = " ".join(args)
            parsed  = self.nlp.parse(raw_sym)
            symbol  = parsed["stocks"][0] if parsed["stocks"] else raw_sym.upper()
            return await self._analyze_reply(symbol)

        if cmd == "entry" and args:
            raw_sym = " ".join(args)
            parsed  = self.nlp.parse(raw_sym)
            symbol  = parsed["stocks"][0] if parsed["stocks"] else raw_sym.upper()
            return await self._entry_reply(symbol)

        if cmd == "patterns":
            return await self._patterns_reply()

        if cmd == "scan":
            try:
                result = await self.patterns.run_scan()
                total = result.get("totalFound", 0)
                calls = result.get("callSignals", 0)
                puts = result.get("putSignals", 0)
                return (
                    f"🔍 *Pattern Scan Complete*\n\n"
                    f"Found *{total}* patterns\n"
                    f"📈 CALL signals: *{calls}*\n"
                    f"📉 PUT signals: *{puts}*\n\n"
                    "Use /patterns to see details."
                )
            except Exception:
                return "⚠️ Could not complete scan. Try again shortly."

        if cmd == "movers":
            return await self._movers_reply()

        if cmd == "heatmap":
            return await self._heatmap_reply()

        # ── NLP fallback for natural language ─────────────────────────────────
        return await self._nlp_reply(text)

    async def _sectors_reply(self) -> str:
        try:
            sectors = await self.sectors.get_all_sectors()
            if not sectors:
                return "⚠️ Could not fetch sector data right now."
            lines = ["📊 *Sector Performance*\n"]
            for s in sectors[:12]:
                pc = s.get("pChange") or 0
                emoji = "📈" if pc > 0 else "📉" if pc < 0 else "➡️"
                lines.append(f"{emoji} *{s.get('name','?')}*: {_fmt_pct(pc)}")
            return "\n".join(lines)
        except Exception:
            return "⚠️ Could not fetch sectors."

    async def _rotation_reply(self) -> str:
        try:
            r = await self.sectors.get_sector_rotation()
            phase = r.get("rotationPhase", "Unknown")
            rec = r.get("recommendation", "")
            breadth = r.get("marketBreadth", {})
            adv = breadth.get("advancing", 0)
            dec = breadth.get("declining", 0)
            buy = r.get("whereToBuyNow", [])
            lines = [
                f"🔄 *Sector Rotation Analysis*\n",
                f"Phase: *{phase}*",
                f"Market: 📈 {adv} up · 📉 {dec} down",
                f"\n_{rec}_",
            ]
            if buy:
                lines.append("\n🎯 *Where to buy now:*")
                for s in buy[:5]:
                    lines.append(f"  • {s.get('name','?')} ({_fmt_pct(s.get('pChange',0))})")
            return "\n".join(lines)
        except Exception:
            return "⚠️ Could not fetch rotation data."

    async def _analyze_reply(self, symbol: str) -> str:
        try:
            d = await self.stocks.get_stock_details(symbol)
            if "error" in d:
                return f"⚠️ Could not find data for *{symbol}*. Check the symbol and try again."
            ta = d.get("technicalAnalysis") or {}
            entry = d.get("entryRecommendation") or {}
            price = _fmt_price(d.get("lastPrice"))
            pc = _fmt_pct(d.get("pChange"))
            rsi = ta.get("rsi")
            trend = _safe(ta.get("trend", "N/A"))
            signal = _safe(entry.get("signal", "N/A"))
            confidence = entry.get("confidence", "N/A")
            ema = ta.get("ema") or {}
            price_dir = "📈" if (d.get("pChange") or 0) >= 0 else "📉"
            lines = [
                f"{price_dir} *{d.get('companyName', symbol)}* ({symbol})\n",
                f"Price: *{price}* ({pc})",
                f"Trend: *{trend}*",
            ]
            if rsi:
                rsi_zone = _safe(ta.get("rsiZone", ""))
                lines.append(f"RSI: *{rsi:.1f}* {rsi_zone}")
            if ema.get("ema9"):
                lines.append(f"EMA9: {_fmt_price(ema['ema9'])} | EMA21: {_fmt_price(ema.get('ema21'))}")
            if ema.get("ema50"):
                lines.append(f"EMA50: {_fmt_price(ema['ema50'])}")
            macd = ta.get("macd") or {}
            if macd.get("crossover"):
                lines.append(f"MACD: *{_safe(macd['crossover'])}*")
            lines.append(f"\n🎯 Signal: *{signal}* (Confidence: {confidence})")
            if entry.get("entryCall"):
                lines.append(f"Entry: {_safe(entry['entryCall'])}")
            if entry.get("targetPrice"):
                lines.append(f"Target: {_fmt_price(entry['targetPrice'])} | SL: {_fmt_price(entry.get('stopLoss'))}")
            return "\n".join(lines)
        except Exception:
            return f"⚠️ Analysis failed for *{symbol}*. Try again shortly."

    async def _entry_reply(self, symbol: str) -> str:
        try:
            d = await self.stocks.get_stock_details(symbol)
            entry = d.get("entryRecommendation") or {}
            if not entry:
                return f"⚠️ No entry data for *{symbol}*."
            lines = [
                f"🎯 *Entry Signal — {symbol}*\n",
                f"Signal: *{_safe(entry.get('signal','N/A'))}*",
                f"Confidence: {entry.get('confidence','N/A')}",
            ]
            if entry.get("entryCall"):
                lines.append(f"Entry: {_safe(entry['entryCall'])}")
            if entry.get("targetPrice"):
                lines.append(f"Target: {_fmt_price(entry['targetPrice'])}")
            if entry.get("stopLoss"):
                lines.append(f"Stop Loss: {_fmt_price(entry['stopLoss'])}")
            if entry.get("riskReward"):
                lines.append(f"Risk:Reward = 1:{entry['riskReward']}")
            if entry.get("summary"):
                lines.append(f"\n{_safe(entry['summary'])}")
            return "\n".join(lines)
        except Exception:
            return f"⚠️ Could not get entry data for *{symbol}*."

    async def _sector_signal_reply(self, sector: str, signal: str) -> str:
        """Return bullish/bearish stocks within a specific sector."""
        try:
            from ..lib.universe import SECTOR_SYMBOLS
            sector_stocks = set(SECTOR_SYMBOLS.get(sector, []))
            emoji = "📈" if signal == "CALL" else "📉"
            bias  = "Bullish" if signal == "CALL" else "Bearish"

            # 1) Try pattern scan results first (fast, cached)
            result = await self.patterns.get_patterns()
            all_pats = result.get("patterns", [])
            sector_pats = [
                p for p in all_pats
                if p.get("symbol") in sector_stocks and p.get("signal") == signal
            ]
            if sector_pats:
                lines = [f"{emoji} *{bias} stocks in {sector}* ({len(sector_pats)} found)\n"]
                for p in sector_pats[:10]:
                    conf = p.get("confidence", 0)
                    lines.append(f"  • *{p['symbol']}* — {_safe(p.get('pattern','?'))} ({conf:.0f}%)")
                lines.append("\nType a symbol for full analysis, e.g. /analyze RELIANCE")
                return "\n".join(lines)

            # 2) Fallback: fetch a sample of sector stocks in parallel, filter by pChange
            import asyncio
            sample = list(sector_stocks)[:15]   # limit to avoid being slow

            async def _get(sym: str):
                try:
                    return await asyncio.wait_for(
                        self.stocks.get_stock_details(sym), timeout=3.0
                    )
                except Exception:
                    return None

            results = await asyncio.gather(*[_get(s) for s in sample])
            stock_data = [r for r in results if r and r.get("lastPrice")]

            if signal == "CALL":
                filtered = sorted(
                    [s for s in stock_data if (s.get("pChange") or 0) > 0],
                    key=lambda x: x.get("pChange", 0), reverse=True
                )
            else:
                filtered = sorted(
                    [s for s in stock_data if (s.get("pChange") or 0) < 0],
                    key=lambda x: x.get("pChange", 0)
                )

            if filtered:
                lines = [f"{emoji} *{bias} stocks in {sector}*\n"]
                for s in filtered[:8]:
                    sym = s.get("symbol", "?")
                    pc  = _fmt_pct(s.get("pChange", 0))
                    ta  = s.get("technicalAnalysis") or {}
                    trend = _safe(ta.get("trend", ""))
                    hint  = f" ({trend})" if trend else ""
                    lines.append(f"  • *{sym}* {pc}{hint}")
                lines.append("\nType a symbol for full analysis, e.g. /analyze TCS")
                return "\n".join(lines)

            return (
                f"{emoji} No strong *{bias.lower()}* signals found in *{sector}* right now.\n"
                f"Run /scan to refresh pattern data."
            )
        except Exception as e:
            return f"⚠️ Could not fetch sector signals: {e}"

    async def _patterns_reply(self) -> str:
        try:
            result = await self.patterns.get_patterns()
            patterns = result.get("patterns", [])
            if not patterns:
                return "🔍 No patterns detected right now. Try /scan to run a fresh scan."
            calls = [p for p in patterns if p.get("signal") == "CALL"][:5]
            puts  = [p for p in patterns if p.get("signal") == "PUT"][:5]
            lines = [f"🕯 *Chart Patterns* ({result.get('totalPatterns',0)} found)\n"]
            if calls:
                lines.append("📈 *CALL Signals:*")
                for p in calls:
                    lines.append(f"  • *{p['symbol']}* — {p['pattern']} ({p.get('confidence',0):.0f}%)")
            if puts:
                lines.append("📉 *PUT Signals:*")
                for p in puts:
                    lines.append(f"  • *{p['symbol']}* — {p['pattern']} ({p.get('confidence',0):.0f}%)")
            return "\n".join(lines)
        except Exception:
            return "⚠️ Could not fetch patterns."

    async def _movers_reply(self) -> str:
        try:
            from .analytics_service import AnalyticsService
            from .nse_service import NseService
            from .yahoo_service import YahooService
            nse = NseService()
            yahoo = YahooService()
            analytics = AnalyticsService(yahoo, nse, self.sectors, self.patterns)
            data = await analytics.get_top_movers()
            gainers = data.get("gainers", [])[:5]
            losers  = data.get("losers", [])[:5]
            lines = [f"🏆 *Top Movers — Nifty 100*\n"]
            if gainers:
                lines.append("📈 *Top Gainers:*")
                for s in gainers:
                    lines.append(f"  • *{s['symbol']}* {_fmt_pct(s['pChange'])} @ {_fmt_price(s['lastPrice'])}")
            if losers:
                lines.append("📉 *Top Losers:*")
                for s in losers:
                    lines.append(f"  • *{s['symbol']}* {_fmt_pct(s['pChange'])} @ {_fmt_price(s['lastPrice'])}")
            return "\n".join(lines)
        except Exception:
            return "⚠️ Could not fetch top movers."

    async def _heatmap_reply(self) -> str:
        try:
            from .analytics_service import AnalyticsService
            from .nse_service import NseService
            from .yahoo_service import YahooService
            nse = NseService()
            yahoo = YahooService()
            analytics = AnalyticsService(yahoo, nse, self.sectors, self.patterns)
            data = await analytics.get_sector_heatmap()
            sectors = data.get("sectors", [])
            bias = data.get("overallBias", "")
            adv  = data.get("advancing", 0)
            dec  = data.get("declining", 0)
            lines = [f"🌡 *Sector Heatmap* — {bias}\n📈 {adv} up · 📉 {dec} down\n"]
            for s in sectors[:12]:
                pc = s.get("todayPChange", 0)
                bar = "🟢" if pc > 1.5 else "🟡" if pc > 0 else "🔴" if pc < -1.5 else "🟠"
                lines.append(f"{bar} *{s['name'][:18]}*: {_fmt_pct(pc)}")
            return "\n".join(lines)
        except Exception:
            return "⚠️ Could not fetch heatmap."

    async def _nlp_reply(self, text: str) -> str:
        try:
            parsed = self.nlp.parse(text)
            intent  = parsed["intent"]
            stocks  = parsed["stocks"]
            sectors = parsed["sectors"]
            signal  = parsed["signal"]

            # ── PRIORITY: Sector + Signal combo ──────────────────────────────
            # e.g. "which IT stocks are bullish", "pharma bearish stocks"
            if sectors and signal:
                return await self._sector_signal_reply(sectors[0], signal)

            # ── Help ────────────────────────────────────────────────────────
            if intent == "help":
                return await self._build_reply("/help")

            # ── Stock analysis ───────────────────────────────────────────────
            if intent == "stock_analysis":
                if stocks:
                    return await self._analyze_reply(stocks[0])
                # "analyze" intent but no symbol extracted → ask rotation
                return await self._rotation_reply()

            # ── Sector query ─────────────────────────────────────────────────
            if intent == "sector_query":
                if sectors:
                    try:
                        sector_data = await self.sectors.get_sector_detail(sectors[0])
                        name = sector_data.get("name", sectors[0])
                        pc   = _fmt_pct(sector_data.get("pChange"))
                        adv  = sector_data.get("advances", "N/A")
                        dec  = sector_data.get("declines", "N/A")
                        top  = sector_data.get("topStocks", [])[:3]
                        lines = [
                            f"📊 *{name}*",
                            f"Change: *{pc}*",
                            f"Advancing: {adv} · Declining: {dec}",
                        ]
                        if top:
                            lines.append("\n*Top stocks:*")
                            for s in top:
                                lines.append(f"  • *{s.get('symbol','?')}* {_fmt_pct(s.get('pChange',0))}")
                        return "\n".join(lines)
                    except Exception:
                        pass
                return await self._sectors_reply()

            # ── Rotation / where to invest ───────────────────────────────────
            if intent == "rotation_query":
                return await self._rotation_reply()

            # ── Pattern scan ─────────────────────────────────────────────────
            if intent == "pattern_scan":
                if stocks:
                    # "bullish RELIANCE" → analyze specific stock
                    return await self._analyze_reply(stocks[0])
                if signal:
                    # "show bullish patterns" → patterns filtered by signal
                    result = await self.patterns.get_patterns()
                    pats   = [p for p in result.get("patterns", []) if p.get("signal") == signal][:8]
                    emoji  = "📈" if signal == "CALL" else "📉"
                    if not pats:
                        return f"{emoji} No *{signal}* patterns right now. Try /scan to refresh."
                    lines = [f"{emoji} *{signal} Signals* ({len(pats)} found)\n"]
                    for p in pats:
                        lines.append(f"  • *{p['symbol']}* — {p['pattern']} ({p.get('confidence',0):.0f}%)")
                    return "\n".join(lines)
                return await self._patterns_reply()

            # ── Analytics ────────────────────────────────────────────────────
            if intent == "analytics":
                lower = text.lower()
                if "heatmap" in lower:
                    return await self._heatmap_reply()
                return await self._movers_reply()

            # ── Scanner ──────────────────────────────────────────────────────
            if intent == "scanner_run":
                all_scanners = self.scanners.get_all_scanners()
                query_lower  = text.lower()
                matched = next(
                    (s for s in all_scanners if any(
                        w in query_lower for w in s["name"].lower().split()
                    )), None
                )
                if matched:
                    result = await self.scanners.run_scanner(matched["id"])
                    count  = result.get("totalMatched", 0)
                    name   = matched["name"]
                    top    = result.get("results", [])[:5]
                    lines  = [f"🔍 *{name}* — {count} matches\n"]
                    for s in top:
                        lines.append(f"  • *{s['symbol']}* {_fmt_pct(s.get('pChange'))}")
                    return "\n".join(lines)
                return (
                    "📡 *Available scanners:*\n"
                    + "\n".join(f"  • {s['name']}" for s in all_scanners)
                )

            # ── Fallback ─────────────────────────────────────────────────────
            return (
                "🤔 Not sure what you mean. Try:\n"
                "• `/analyze RELIANCE` — stock analysis\n"
                "• `/sectors` — sector overview\n"
                "• `/rotation` — where to invest\n"
                "• `/patterns` — chart signals\n"
                "• `/help` for full list"
            )
        except Exception:
            return (
                "⚠️ Could not process your request.\n"
                "Type /help for available commands."
            )

    async def test_message(self, text: str) -> dict:
        reply = await self._build_reply(text)
        _log("test", text, reply)
        return {"text": text, "response": reply, "timestamp": datetime.utcnow().isoformat() + "Z"}
