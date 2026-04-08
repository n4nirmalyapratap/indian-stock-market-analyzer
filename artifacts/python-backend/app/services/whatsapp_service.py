from datetime import datetime
from typing import Optional
from .sectors_service import SectorsService
from .stocks_service import StocksService
from .patterns_service import PatternsService
from .scanners_service import ScannersService

MAX_LOG = 200
_message_log: list[dict] = []
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
    ):
        self.sectors = sectors
        self.stocks = stocks
        self.patterns = patterns
        self.scanners = scanners

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
                "Custom scanners", "Entry/exit signals",
            ],
            "commands": [
                "!help", "!sectors", "!rotation", "!analyze <SYMBOL>",
                "!patterns", "!scan", "!scanner list", "!scanner run <id>",
                "!entry <SYMBOL>", "!status",
            ],
        }

    async def process_message(self, body: dict) -> dict:
        from_ = body.get("from") or "unknown-user"
        text = (body.get("message") or body.get("text") or "").strip()
        if not text:
            raise ValueError("No message text provided")

        start = datetime.utcnow()
        try:
            response = await self._route(text.lower(), text)
        except Exception as e:
            response = f"Error processing command: {e}"

        elapsed = int((datetime.utcnow() - start).total_seconds() * 1000)
        entry = {"from": from_, "text": text, "timestamp": datetime.utcnow().isoformat() + "Z", "response": response}
        _message_log.append(entry)
        if len(_message_log) > MAX_LOG:
            del _message_log[:len(_message_log) - MAX_LOG]

        return {**entry, "processingTime": f"{elapsed}ms"}

    async def _route(self, cmd: str, raw: str) -> str:
        if cmd in ("!help", "help"):
            return self._help()
        if cmd in ("!status", "status"):
            return self._status()
        if cmd.startswith("!analyze ") or cmd.startswith("analyze "):
            sym = raw.split()[1].upper() if len(raw.split()) > 1 else ""
            if not sym:
                return "Usage: !analyze <SYMBOL>\nExample: !analyze RELIANCE"
            return await self._analyze_stock(sym)
        if cmd in ("!sectors", "sectors"):
            return await self._fetch_sectors()
        if cmd in ("!rotation", "rotation"):
            return await self._fetch_rotation()
        if cmd in ("!patterns", "patterns"):
            return await self._fetch_patterns()
        if cmd == "!scan":
            return await self._trigger_scan()
        if cmd == "!scanner list":
            return self._list_scanners()
        if cmd.startswith("!scanner run "):
            sid = raw.split()[2] if len(raw.split()) > 2 else ""
            return await self._run_scanner(sid)
        if cmd.startswith("!entry ") or cmd.startswith("entry "):
            sym = raw.split()[1].upper() if len(raw.split()) > 1 else ""
            if not sym:
                return "Usage: !entry <SYMBOL>"
            return await self._entry_signal(sym)
        return "Unknown command. Type !help for available commands."

    def _help(self) -> str:
        return (
            "🤖 *Indian Stock Market Bot*\n\n*Commands:*\n"
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
            "_End-of-day data. Not real-time._"
        )

    def _status(self) -> str:
        return (
            f"*Bot Status:* {'✅ Active' if _bot_enabled else '❌ Disabled'}\n"
            f"*Session:* {_session_status}\n"
            f"*Messages Processed:* {len(_message_log)}"
        )

    async def _fetch_sectors(self) -> str:
        data = await self.sectors.get_all_sectors()
        if not data:
            return "Sector data unavailable right now."
        sorted_data = sorted(data, key=lambda s: s["pChange"], reverse=True)
        top5 = sorted_data[:5]
        bottom3 = sorted_data[-3:][::-1]
        msg = "📊 *Sector Overview*\n\n*Top Gainers:*\n"
        for s in top5:
            pc = s.get("pChange") or 0
            msg += f"• {s['name']}: {'+' if pc > 0 else ''}{pc:.2f}%\n"
        msg += "\n*Laggards:*\n"
        for s in bottom3:
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
            msg += f"• Trend: {ta['trend']}\n"
            msg += f"• RSI(14): {ta['rsi']:.1f} — {ta['rsiZone']}\n"
            msg += f"• MACD: {ta['macd']['crossover']}\n"
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
        scan_time = datetime.fromisoformat(d["lastScanTime"].rstrip("Z")).strftime("%d %b %Y")
        msg = f"🕯️ *Chart Patterns* ({scan_time})\n\n*CALL Signals ({d['callSignals']}):*\n"
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
        msg = f"🎯 *Entry Signal: {symbol}*\n\n*Signal:* {er['entryCall']}\n*Confidence:* {er['confidence']}\n"
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
