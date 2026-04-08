from datetime import datetime
from typing import Optional, TYPE_CHECKING
from .sectors_service import SectorsService
from .stocks_service import StocksService
from .patterns_service import PatternsService
from .scanners_service import ScannersService

if TYPE_CHECKING:
    from .nlp_service import NlpService

MAX_LOG = 200
_message_log: list[dict] = []


def _safe(v) -> str:
    """Replace underscores with spaces so WhatsApp bold/italic markers aren't broken."""
    return str(v).replace("_", " ") if v is not None else "N/A"


_bot_enabled = True
_session_qr: Optional[str] = None
_session_status = "DISCONNECTED"


class WhatsappService:
    def __init__(
        self,
        sectors: SectorsService,
        stocks: StocksService,
        patterns: PatternsService,
        scanners: ScannersService,
        nlp: Optional["NlpService"] = None,
    ):
        self.sectors = sectors
        self.stocks = stocks
        self.patterns = patterns
        self.scanners = scanners
        self.nlp = nlp

    def get_bot_status(self) -> dict:
        return {
            "status": _session_status if _bot_enabled else "DISABLED",
            "enabled": _bot_enabled,
            "qrCode": _session_qr,
            "sessionActive": _session_status == "CONNECTED",
            "lastActive": _message_log[-1]["timestamp"] if _message_log else None,
            "totalMessages": len(_message_log),
            "capabilities": [
                "Stock analysis", "Sector rotation", "Pattern scan",
                "Custom scanners", "Entry/exit signals", "Natural language queries",
            ],
            "commands": [
                "!help", "!sectors", "!rotation", "!analyze <SYMBOL>",
                "!patterns", "!scan", "!scanner list", "!scanner run <id>",
                "!entry <SYMBOL>", "!status",
                "Or just type naturally: 'analyze RELIANCE', 'show IT sector', 'where to invest?'",
            ],
        }

    async def process_message(self, body: dict) -> dict:
        from_ = body.get("from") or "unknown-user"
        text = (body.get("message") or body.get("text") or "").strip()
        if not text:
            raise ValueError("No message text provided")

        start = datetime.utcnow()
        try:
            response = await self._route(text)
        except Exception as e:
            response = f"Error processing request: {e}"

        elapsed = int((datetime.utcnow() - start).total_seconds() * 1000)
        entry = {
            "from": from_,
            "text": text,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "response": response,
        }
        _message_log.append(entry)
        if len(_message_log) > MAX_LOG:
            del _message_log[:len(_message_log) - MAX_LOG]

        return {**entry, "processingTime": f"{elapsed}ms"}

    async def _route(self, raw: str) -> str:
        cmd = raw.lower().strip()

        # ── Exact-match commands (backwards-compatible) ───────────────────────
        if cmd in ("!help", "help", "/help"):
            return self._help()
        if cmd in ("!status", "status"):
            return self._status()
        if cmd in ("!sectors", "sectors", "/sectors"):
            return await self._fetch_sectors()
        if cmd in ("!rotation", "rotation", "/rotation"):
            return await self._fetch_rotation()
        if cmd in ("!patterns", "patterns", "/patterns"):
            return await self._fetch_patterns()
        if cmd == "!scan":
            return await self._trigger_scan()
        if cmd == "!scanner list":
            return self._list_scanners()
        if cmd.startswith("!scanner run "):
            sid = raw.split()[2] if len(raw.split()) > 2 else ""
            return await self._run_scanner(sid)
        if cmd.startswith("!analyze ") or cmd.startswith("analyze "):
            parts = raw.split()
            sym = parts[1].upper() if len(parts) > 1 else ""
            if not sym:
                return "Usage: !analyze <SYMBOL>\nExample: !analyze RELIANCE"
            return await self._analyze_stock(sym)
        if cmd.startswith("!entry ") or cmd.startswith("entry "):
            parts = raw.split()
            sym = parts[1].upper() if len(parts) > 1 else ""
            if not sym:
                return "Usage: !entry <SYMBOL>"
            return await self._entry_signal(sym)

        # ── NLP fallback (natural language) ──────────────────────────────────
        if self.nlp:
            return await self._nlp_route(raw)

        # Classic fallback: if text looks like a symbol, analyze it
        upper = raw.upper().strip()
        if 2 <= len(upper) <= 15 and upper.replace("-", "").isalnum():
            return await self._analyze_stock(upper)

        return "I didn't understand that. Type !help to see available commands."

    async def _nlp_route(self, text: str) -> str:
        parsed = self.nlp.parse(text)
        intent  = parsed["intent"]
        stocks  = parsed["stocks"]
        sectors = parsed["sectors"]
        signal  = parsed["signal"]

        # ── PRIORITY: sector + signal combo ──────────────────────────────────
        # "which IT stocks are going down", "bearish pharma", "bank stocks rising"
        if sectors and signal:
            return await self._sector_signal_reply(sectors[0], signal)

        if intent == "help":
            return self._help()
        elif intent == "stock_analysis":
            if stocks:
                return await self._analyze_stock(stocks[0])
            return "Please specify a stock symbol. E.g. 'analyze RELIANCE' or just type 'TCS'."
        elif intent == "sector_query":
            if sectors:
                data = await self.sectors.get_sector_detail(sectors[0])
                if data:
                    pc = data.get("pChange") or 0
                    return (
                        f"*{data['name']}*\n"
                        f"Change: {'+' if pc > 0 else ''}{pc:.2f}%\n"
                        f"Trend: {data.get('focus', 'HOLD')}\n"
                        f"Source: {data.get('source', 'NSE')}"
                    )
            return await self._fetch_sectors()
        elif intent == "rotation_query":
            return await self._fetch_rotation()
        elif intent == "pattern_scan":
            if stocks:
                return await self._analyze_stock(stocks[0])
            if signal:
                d = await self.patterns.get_patterns(signal=signal)
            else:
                d = await self.patterns.get_patterns()
            patterns_list = d.get("patterns") or []
            if not patterns_list:
                return "No patterns detected. Try !scan to refresh."
            lines = [f"*Chart Patterns*"]
            for p in patterns_list[:8]:
                sig_icon = "🟢" if p["signal"] == "CALL" else "🔴"
                lines.append(f"{sig_icon} {p['symbol']} — {_safe(p['pattern'])} ({p['confidence']}%)")
            return "\n".join(lines)
        elif intent == "scanner_run":
            all_s = self.scanners.get_all_scanners()
            query_lower = text.lower()
            matched = None
            for sc in all_s:
                if any(word in query_lower for word in sc["name"].lower().split() if len(word) > 3):
                    matched = sc
                    break
            if matched:
                return await self._run_scanner(matched["id"])
            return self._list_scanners()
        else:
            # last resort: if it looks like a stock symbol, analyze it
            upper = text.upper().strip()
            if 2 <= len(upper) <= 15 and upper.replace("-", "").isalnum():
                return await self._analyze_stock(upper)
            return (
                "I understood your request but couldn't find specific data.\n"
                "Try: !sectors, !rotation, !patterns, !analyze <SYMBOL>\n"
                "Or ask naturally: 'show IT sector', 'where to invest?'"
            )

    async def _sector_signal_reply(self, sector: str, signal: str) -> str:
        """Return bullish/bearish stocks in a specific sector."""
        import asyncio
        from ..lib.universe import SECTOR_SYMBOLS
        sector_stocks = set(SECTOR_SYMBOLS.get(sector, []))
        emoji = "📈" if signal == "CALL" else "📉"
        bias  = "Bullish" if signal == "CALL" else "Bearish"

        # 1) Check cached pattern scan results first
        result = await self.patterns.get_patterns()
        all_pats = result.get("patterns", [])
        sector_pats = [
            p for p in all_pats
            if p.get("symbol") in sector_stocks and p.get("signal") == signal
        ]
        if sector_pats:
            lines = [f"{emoji} *{bias} stocks in {sector}* ({len(sector_pats)} found)\n"]
            for p in sector_pats[:10]:
                lines.append(f"  • *{p['symbol']}* — {_safe(p.get('pattern', '?'))} ({p.get('confidence', 0):.0f}%)")
            lines.append("\nType: !analyze <SYMBOL> for full details")
            return "\n".join(lines)

        # 2) Parallel-fetch sample of sector stocks, filter by today's price direction
        sample = list(sector_stocks)[:15]

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
                sym   = s.get("symbol", "?")
                pc    = s.get("pChange", 0)
                sign  = "+" if pc >= 0 else ""
                ta    = s.get("technicalAnalysis") or {}
                trend = _safe(ta.get("trend", ""))
                hint  = f" ({trend})" if trend else ""
                lines.append(f"  • *{sym}* {sign}{pc:.2f}%{hint}")
            lines.append("\nType: !analyze <SYMBOL> for full details")
            return "\n".join(lines)

        return (
            f"{emoji} No strong *{bias.lower()}* signals found in *{sector}* right now.\n"
            f"Try !scan to refresh pattern data."
        )

    # ── Response formatters ───────────────────────────────────────────────────

    def _help(self) -> str:
        return (
            "🤖 *Indian Stock Market Bot*\n\n"
            "*Commands (or type naturally):*\n"
            "!sectors — Sector performance overview\n"
            "!rotation — Sector rotation analysis\n"
            "!analyze <SYMBOL> — Full stock analysis\n"
            "!entry <SYMBOL> — Entry/exit signal\n"
            "!patterns — Chart patterns (CALL/PUT signals)\n"
            "!scan — Trigger fresh pattern scan\n"
            "!scanner list — List custom scanners\n"
            "!scanner run <id> — Run a scanner\n"
            "!status — Bot status\n"
            "!help — This help message\n\n"
            "*Natural language supported:*\n"
            "_'analyze TCS', 'show me IT sector', 'where to invest?', "
            "'bullish patterns', 'RELIANCE analysis'_\n\n"
            "_End-of-day data from NSE/Yahoo Finance_"
        )

    def _status(self) -> str:
        return (
            f"*Bot Status:* {'✅ Active' if _bot_enabled else '❌ Disabled'}\n"
            f"*Session:* {_session_status}\n"
            f"*Messages Processed:* {len(_message_log)}\n"
            f"*NLP:* {'✅ Enabled' if self.nlp else '❌ Disabled'}"
        )

    async def _fetch_sectors(self) -> str:
        data = await self.sectors.get_all_sectors()
        if not data:
            return "Sector data unavailable right now."
        sorted_data = sorted(data, key=lambda s: s["pChange"], reverse=True)
        msg = "📊 *Sector Overview*\n\n*Top Gainers:*\n"
        for s in sorted_data[:5]:
            pc = s.get("pChange") or 0
            msg += f"• {s['name']}: {'+' if pc > 0 else ''}{pc:.2f}%\n"
        msg += "\n*Laggards:*\n"
        for s in sorted_data[-3:]:
            pc = s.get("pChange") or 0
            msg += f"• {s['name']}: {pc:.2f}%\n"
        return msg

    async def _fetch_rotation(self) -> str:
        r = await self.sectors.get_sector_rotation()
        if not r:
            return "Sector rotation data unavailable right now."
        msg = (
            f"🔄 *Sector Rotation Analysis*\n\n"
            f"*Phase:* {r['rotationPhase']}\n\n"
            f"*Market Breadth:*\n"
            f"• Advancing: {r['marketBreadth']['advancing']}\n"
            f"• Declining: {r['marketBreadth']['declining']}\n\n"
            "*Where to Buy Now:*\n"
        )
        for s in (r.get("whereToBuyNow") or [])[:5]:
            msg += f"• {s['name']}\n"
        msg += f"\n_{r['recommendation']}_"
        return msg

    async def _analyze_stock(self, symbol: str) -> str:
        d = await self.stocks.get_stock_details(symbol)
        if d.get("error"):
            return f"❌ {d['error']}"
        ta = d.get("technicalAnalysis")
        price = d.get("lastPrice") or 0
        pchange = d.get("pChange") or 0
        msg = f"📈 *{d.get('companyName', symbol)}* ({symbol})\n"
        msg += f"💰 Price: ₹{price:.2f}\n"
        msg += f"📊 Change: {'+' if pchange > 0 else ''}{pchange:.2f}%\n"
        if ta:
            msg += "\n*Technical Analysis:*\n"
            msg += f"• Trend: {_safe(ta.get('trend', 'N/A'))}\n"
            msg += f"• RSI(14): {ta['rsi']:.1f} — {_safe(ta.get('rsiZone', ''))}\n"
            msg += f"• MACD: {_safe((ta.get('macd') or {}).get('crossover', 'N/A'))}\n"
            if ta.get("nearestSupport"):
                msg += f"• Support: ₹{ta['nearestSupport']:.2f}\n"
            if ta.get("nearestResistance"):
                msg += f"• Resistance: ₹{ta['nearestResistance']:.2f}\n"
        if d.get("entryRecommendation"):
            er = d["entryRecommendation"]
            msg += f"\n*Entry Signal:* {er['entryCall']}\n_{er['summary']}_"
        return msg

    async def _fetch_patterns(self) -> str:
        d = await self.patterns.get_patterns()
        if not d.get("patterns"):
            return "No patterns detected currently. Try !scan to refresh."
        msg = f"🕯️ *Chart Patterns*\n\n*CALL Signals ({d['callSignals']}):*\n"
        for p in (d.get("topCalls") or [])[:5]:
            msg += f"• {p['symbol']} — {p['pattern']} ({p['confidence']}%)\n"
        msg += f"\n*PUT Signals ({d['putSignals']}):*\n"
        for p in (d.get("topPuts") or [])[:3]:
            msg += f"• {p['symbol']} — {p['pattern']} ({p['confidence']}%)\n"
        return msg

    async def _trigger_scan(self) -> str:
        d = await self.patterns.trigger_scan()
        top = "\n".join(f"• {p['symbol']}: {p['pattern']}" for p in (d.get("patterns") or [])[:5])
        return (
            f"🔍 *Scan Complete*\n"
            f"• Total Patterns: {d['totalFound']}\n"
            f"• CALL Signals: {d['callSignals']}\n"
            f"• PUT Signals: {d['putSignals']}\n\n"
            f"Top results:\n{top or 'None'}"
        )

    def _list_scanners(self) -> str:
        all_s = self.scanners.get_all_scanners()
        if not all_s:
            return "No custom scanners defined."
        msg = "🔎 *Custom Scanners:*\n"
        for s in all_s:
            msg += f"• *{s['id']}:* {s['name']}\n"
        msg += "\nUse: !scanner run <id>"
        return msg

    async def _run_scanner(self, sid: str) -> str:
        if not sid:
            return "Usage: !scanner run <id>"
        r = await self.scanners.run_scanner(sid)
        if "error" in r:
            return f"❌ {r['error']}"
        top = "\n".join(
            f"• {s['symbol']} ₹{s['lastPrice']:.2f}"
            for s in (r.get("results") or [])[:8]
        ) or "No matches found"
        return (
            f"🔎 *{r['scannerName']}*\n"
            f"• Scanned: {r['totalScanned']}\n"
            f"• Matched: {r['totalMatched']}\n\n"
            f"Top results:\n{top}"
        )

    async def _entry_signal(self, symbol: str) -> str:
        d = await self.stocks.get_stock_details(symbol)
        if d.get("error"):
            return f"❌ {d['error']}"
        er = d.get("entryRecommendation")
        if not er:
            return f"Unable to generate entry signal for {symbol}"
        msg = f"🎯 *Entry Signal: {symbol}*\n\n*Signal:* {_safe(er.get('entryCall','N/A'))}\n*Confidence:* {er.get('confidence','N/A')}\n"
        if er.get("targetPrice"):
            msg += f"*Target:* ₹{er['targetPrice']:.2f}\n"
        if er.get("stopLoss"):
            msg += f"*Stop Loss:* ₹{er['stopLoss']:.2f}\n"
        if er.get("riskReward"):
            msg += f"*R:R Ratio:* {er['riskReward']}:1\n"
        msg += f"\n_{er['summary']}_"
        return msg

    def get_message_log(self) -> list[dict]:
        return _message_log[-50:]

    def simulate_qr_code(self) -> dict:
        global _session_qr, _session_status
        _session_qr = f"SIMULATED_QR_{int(datetime.utcnow().timestamp() * 1000)}"
        _session_status = "WAITING_FOR_QR_SCAN"
        return {"qrCode": _session_qr, "status": _session_status, "message": "Scan with WhatsApp to connect"}

    def update_bot_status(self, enabled: bool) -> dict:
        global _bot_enabled
        _bot_enabled = enabled
        return {"enabled": _bot_enabled, "status": _session_status if _bot_enabled else "DISABLED"}
