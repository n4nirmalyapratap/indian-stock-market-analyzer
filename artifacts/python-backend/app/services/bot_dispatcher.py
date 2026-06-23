"""
bot_dispatcher.py — Channel-agnostic command dispatcher shared by Telegram &
WhatsApp bots.

Design goals
------------
* One command spec, one set of handlers — both bots delegate here.
* NLP-first: every channel routes free-form text through the NLP service before
  falling back to "I don't understand". The dispatcher then maps NLP intents to
  the same handlers the slash/bang commands use.
* Stateless inline holdings: `RELIANCE:10@2400 TCS:5` is parsed wherever a
  portfolio op needs holdings, no DB lookup required.
* Per-chat alert subscriptions keyed by chat_id (no account linking).
* Tracks per-command invocation counts so the admin dashboard can show usage.

Channels render the result themselves:
  - Telegram: BotResponse.text (Markdown) + actions → InlineKeyboardMarkup
  - WhatsApp: BotResponse.text + actions → numbered list ("Reply 1, 2…")
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from . import bot_alerts
from .nlp_service import NlpService
from .sectors_service import SectorsService
from .stocks_service import StocksService
from .patterns_service import PatternsService
from .scanners_service import ScannersService

logger = logging.getLogger(__name__)


# ── Response types ────────────────────────────────────────────────────────────

@dataclass
class BotAction:
    """A suggested follow-up the user can pick. Each channel renders it differently."""
    label: str
    command: str  # the literal command text the user would re-send


@dataclass
class BotResponse:
    text: str
    actions: list[BotAction] = field(default_factory=list)
    error: bool = False


# ── Command registry ──────────────────────────────────────────────────────────

@dataclass
class CommandSpec:
    name: str               # canonical, no slash/bang
    aliases: list[str]      # additional names (lowercase)
    category: str
    summary: str
    usage: str              # e.g. "/analyze SYMBOL"
    handler_name: str       # method on BotDispatcher


COMMAND_REGISTRY: list[CommandSpec] = [
    # ── Help / bootstrap ──
    CommandSpec("start", [], "Help", "Welcome message",
                "/start", "_h_start"),
    CommandSpec("help", ["?", "menu", "commands"], "Help",
                "Show this command list", "/help", "_h_help"),
    CommandSpec("status", [], "Help",
                "Bot status & subscription count", "/status", "_h_status"),

    # ── Market overview ──
    CommandSpec("sectors", [], "Market",
                "Sector performance overview", "/sectors", "_h_sectors"),
    CommandSpec("rotation", [], "Market",
                "Sector rotation report (where to invest)",
                "/rotation", "_h_rotation"),
    CommandSpec("movers", ["gainers", "losers"], "Market",
                "Top gainers & losers", "/movers", "_h_movers"),
    CommandSpec("heatmap", [], "Market",
                "Sector % change heatmap", "/heatmap", "_h_heatmap"),
    CommandSpec("news", [], "Market",
                "Latest market news headlines", "/news [SYMBOL]", "_h_news"),

    # ── Per-stock analysis ──
    CommandSpec("analyze", ["a", "stock"], "Stock",
                "Full technical analysis", "/analyze SYMBOL", "_h_analyze"),
    CommandSpec("entry", [], "Stock",
                "Entry/exit signal with target & stop-loss",
                "/entry SYMBOL", "_h_entry"),
    CommandSpec("dcf", ["intrinsic"], "Stock",
                "Intrinsic-value (DCF) snapshot",
                "/dcf SYMBOL", "_h_dcf"),
    CommandSpec("sentiment", [], "Stock",
                "Price-action sentiment score",
                "/sentiment SYMBOL", "_h_sentiment"),
    CommandSpec("forecast", [], "Stock",
                "N-day price forecast (Hydra)",
                "/forecast SYMBOL [days]", "_h_forecast"),

    # ── Patterns / scanners ──
    CommandSpec("patterns", [], "Signals",
                "CALL/PUT chart-pattern signals", "/patterns", "_h_patterns"),
    CommandSpec("scan", [], "Signals",
                "Trigger a fresh pattern scan", "/scan", "_h_scan"),
    CommandSpec("scanners", ["scanner"], "Signals",
                "List or run custom scanners",
                "/scanners [list|run ID]", "_h_scanners"),

    # ── Pairs / backtest / VaR ──
    CommandSpec("pairs", [], "Quant",
                "Cointegrated pairs analysis",
                "/pairs SYMBOL_A SYMBOL_B", "_h_pairs"),
    CommandSpec("backtest", [], "Quant",
                "Pairs-trading backtest",
                "/backtest SYMBOL_A SYMBOL_B", "_h_backtest"),
    CommandSpec("var", [], "Quant",
                "Portfolio Value-at-Risk (uses /portfolio holdings)",
                "/var SYM:qty[@avg] …", "_h_var"),
    CommandSpec("portfolio", ["pnl", "pf"], "Quant",
                "Stateless P&L from inline holdings",
                "/portfolio SYM:qty@avg …", "_h_portfolio"),

    # ── Options ──
    CommandSpec("greeks", [], "Options",
                "Black-Scholes greeks for a single option",
                "/greeks SYM CALL|PUT STRIKE DAYS [IV%]", "_h_greeks"),
    CommandSpec("payoff", [], "Options",
                "Strategy payoff (max profit/loss/breakevens)",
                "/payoff SYM STRATEGY STRIKE [WIDTH]", "_h_payoff"),
    CommandSpec("cost", [], "Options",
                "Per-trade cost breakdown (premium × lot + fees)",
                "/cost SYM CALL|PUT STRIKE QTY PREMIUM", "_h_cost"),

    # ── Sector rotation cockpit ──
    CommandSpec("cockpit", ["srr", "rotation-cockpit"], "Market",
                "Sector rotation cockpit — leading sectors & winning stocks",
                "/cockpit [SECTOR]", "_h_cockpit"),

    # ── Extended per-stock ──
    CommandSpec("council", ["investors", "verdict", "personas"], "Stock",
                "Investor council verdict from 16 legendary investors",
                "/council SYMBOL", "_h_council"),
    CommandSpec("holders", ["shareholding", "ownership", "stake"], "Stock",
                "Shareholding pattern — Promoter / FII / DII / Public",
                "/holders SYMBOL", "_h_holders"),
    CommandSpec("fundas", ["fundamentals", "fins", "financials"], "Stock",
                "Key fundamental ratios & valuation metrics",
                "/fundas SYMBOL", "_h_fundas"),

    # ── Alerts ──
    CommandSpec("alerts", ["alert"], "Alerts",
                "List, add or remove price/pattern alerts",
                "/alerts list|add SYM TYPE VAL|remove ID|clear", "_h_alerts"),
]

REGISTRY_BY_NAME: dict[str, CommandSpec] = {}
for _c in COMMAND_REGISTRY:
    REGISTRY_BY_NAME[_c.name] = _c
    for _a in _c.aliases:
        REGISTRY_BY_NAME[_a] = _c


# ── Helpers ──────────────────────────────────────────────────────────────────

_HOLDING_RE = re.compile(
    r"\b([A-Z][A-Z0-9&-]{1,14}):([\d.]+)(?:@([\d.]+))?", re.IGNORECASE,
)


def parse_inline_holdings(text: str) -> list[dict]:
    """Extract `SYMBOL:qty[@avg]` tokens from arbitrary text.

    Returns list of {symbol, qty, avg?} — avg is None when not supplied.
    """
    out: list[dict] = []
    for m in _HOLDING_RE.finditer(text):
        sym = m.group(1).upper()
        try:
            qty = float(m.group(2))
        except ValueError:
            continue
        avg = float(m.group(3)) if m.group(3) else None
        if qty > 0:
            out.append({"symbol": sym, "qty": qty, "avg": avg})
    return out


def _fmt_price(v: Any) -> str:
    try:
        return f"₹{float(v):,.2f}"
    except Exception:
        return str(v) if v is not None else "N/A"


def _fmt_pct(v: Any) -> str:
    try:
        f = float(v)
        return f"{'+' if f >= 0 else ''}{f:.2f}%"
    except Exception:
        return str(v) if v is not None else "N/A"


def _safe(v: Any) -> str:
    return str(v).replace("_", " ") if v is not None else "N/A"


# ── Dispatcher ───────────────────────────────────────────────────────────────

class BotDispatcher:
    """Single source of truth for both Telegram & WhatsApp bots."""

    def __init__(
        self,
        sectors: SectorsService,
        stocks: StocksService,
        patterns: PatternsService,
        scanners: ScannersService,
        nlp: NlpService,
        hydra: Optional[Any] = None,
        news: Optional[Any] = None,
    ) -> None:
        self.sectors = sectors
        self.stocks = stocks
        self.patterns = patterns
        self.scanners = scanners
        self.nlp = nlp
        self.hydra = hydra
        self.news = news
        self._counts: dict[str, int] = {c.name: 0 for c in COMMAND_REGISTRY}
        # Last-context cache per chat for stateful follow-ups
        self._ctx: dict[str, dict] = {}

    # ── Public entry points ──────────────────────────────────────────────────

    def invocation_counts(self) -> dict[str, int]:
        return dict(self._counts)

    def registry(self) -> list[dict]:
        return [
            {
                "name": c.name,
                "aliases": c.aliases,
                "category": c.category,
                "summary": c.summary,
                "usage": c.usage,
                "invocations": self._counts.get(c.name, 0),
            }
            for c in COMMAND_REGISTRY
        ]

    async def dispatch(
        self,
        channel: str,
        chat_id: str,
        raw_text: str,
    ) -> BotResponse:
        """Main entry: route a user message through commands → NLP fallback."""
        text = (raw_text or "").strip()
        if not text:
            return BotResponse("Type /help to see what I can do.", error=True)

        # 1) Try slash- / bang-prefixed command
        cmd, args = _split_command(text)
        if cmd and cmd in REGISTRY_BY_NAME:
            spec = REGISTRY_BY_NAME[cmd]
            return await self._invoke(spec, channel, chat_id, args, text)

        # 2) NLP-first fallback for natural language
        try:
            return await self._nlp_dispatch(channel, chat_id, text)
        except Exception as e:
            logger.warning("dispatcher.nlp failed: %s", e, exc_info=True)
            return BotResponse(
                "Sorry — I had trouble understanding that. Try /help.",
                error=True,
            )

    # ── Internal: invoke a registered command ────────────────────────────────

    async def _invoke(
        self,
        spec: CommandSpec,
        channel: str,
        chat_id: str,
        args: list[str],
        raw: str,
    ) -> BotResponse:
        self._counts[spec.name] = self._counts.get(spec.name, 0) + 1
        handler: Callable[..., Awaitable[BotResponse]] = getattr(self, spec.handler_name)
        try:
            return await handler(channel, chat_id, args, raw)
        except Exception as e:
            logger.warning("dispatcher.%s failed: %s", spec.name, e, exc_info=True)
            return BotResponse(
                f"⚠️ {spec.name} failed: {e.__class__.__name__}. Try again shortly.",
                error=True,
            )

    # ── NLP fallback ─────────────────────────────────────────────────────────

    async def _nlp_dispatch(self, channel: str, chat_id: str, text: str) -> BotResponse:
        parsed = self.nlp.parse(text)
        intent = parsed["intent"]
        stocks = parsed["stocks"]
        sectors = parsed["sectors"]
        signal = parsed["signal"]

        # Inline holdings detection — auto-route to portfolio
        if parse_inline_holdings(text):
            return await self._h_portfolio(channel, chat_id, [], text)

        if intent == "help":
            return await self._h_help(channel, chat_id, [], text)
        if intent == "stock_analysis":
            if stocks:
                return await self._h_analyze(channel, chat_id, [stocks[0]], text)
            return BotResponse(
                "Please name a stock — e.g. _analyze RELIANCE_ or just _TCS_.",
                actions=[BotAction("Analyze RELIANCE", "/analyze RELIANCE")],
            )
        if intent == "sector_query":
            return await self._h_sectors(channel, chat_id, [], text)
        if intent == "rotation_query":
            return await self._h_rotation(channel, chat_id, [], text)
        if intent == "pattern_scan":
            self._counts["patterns"] += 1
            return await self._h_patterns(channel, chat_id, [], text)
        if intent == "scanner_run":
            return await self._h_scanners(channel, chat_id, ["list"], text)
        if intent == "analytics":
            return await self._h_movers(channel, chat_id, [], text)
        if intent == "cockpit_query":
            return await self._h_cockpit(channel, chat_id, [], text)
        if intent == "council_query":
            if stocks:
                return await self._h_council(channel, chat_id, [stocks[0]], text)
            return BotResponse(
                "Which stock should the council evaluate? E.g. _`/council RELIANCE`_",
                actions=[BotAction("Council RELIANCE", "/council RELIANCE")],
            )
        if intent == "holders_query":
            if stocks:
                return await self._h_holders(channel, chat_id, [stocks[0]], text)
            return BotResponse(
                "Which stock's shareholding do you want? E.g. _`/holders RELIANCE`_",
                actions=[BotAction("Holders RELIANCE", "/holders RELIANCE")],
            )
        if intent == "fundas_query":
            if stocks:
                return await self._h_fundas(channel, chat_id, [stocks[0]], text)
            return BotResponse(
                "Which stock's fundamentals? E.g. _`/fundas RELIANCE`_",
                actions=[BotAction("Fundas RELIANCE", "/fundas RELIANCE")],
            )

        # Bare symbol fallback
        upper = text.strip().upper()
        if 2 <= len(upper) <= 15 and upper.replace("-", "").isalnum():
            return await self._h_analyze(channel, chat_id, [upper], text)

        return BotResponse(
            "I didn't catch that. Try /help, or ask naturally — _\"analyze TCS\"_, "
            "_\"which sectors are up?\"_, _\"bullish patterns\"_.",
            actions=[
                BotAction("Help", "/help"),
                BotAction("Sectors", "/sectors"),
                BotAction("Rotation", "/rotation"),
            ],
        )

    # ── Handlers ─────────────────────────────────────────────────────────────

    async def _h_start(self, *_a, **_k) -> BotResponse:
        return BotResponse(
            "🤖 *Indian Stock Market Bot*\n\n"
            "Real-time NSE analysis, options, portfolio P&L, alerts and more.\n"
            "Type /help to see the full menu, or just ask naturally:\n"
            "_\"analyze RELIANCE\"_, _\"where to invest?\"_, _\"bullish patterns\"_.",
            actions=[
                BotAction("Help", "/help"),
                BotAction("Sectors", "/sectors"),
                BotAction("Rotation", "/rotation"),
                BotAction("Top movers", "/movers"),
            ],
        )

    async def _h_help(self, *_a, **_k) -> BotResponse:
        # Group by category
        by_cat: dict[str, list[CommandSpec]] = {}
        for c in COMMAND_REGISTRY:
            by_cat.setdefault(c.category, []).append(c)
        lines = ["🤖 *Indian Stock Market Bot — Commands*"]
        for cat, items in by_cat.items():
            lines.append(f"\n*{cat}:*")
            for c in items:
                lines.append(f"  `{c.usage}` — {c.summary}")
        lines.append(
            "\n*Tip:* natural-language works too — _\"analyze TCS\"_, "
            "_\"forecast INFY 7d\"_, _\"bullish IT\"_."
        )
        lines.append(
            "\n*Inline holdings:* paste `SYM:qty@avg` (e.g. `RELIANCE:10@2400 TCS:5`) "
            "to get P&L or VaR — no account needed."
        )
        return BotResponse("\n".join(lines))

    async def _h_status(self, channel: str, chat_id: str, *_a, **_k) -> BotResponse:
        subs = bot_alerts.list_alerts(channel, chat_id)
        return BotResponse(
            f"*Bot status*\n"
            f"• Channel: `{channel}`\n"
            f"• Chat ID: `{chat_id}`\n"
            f"• Active alerts: *{len(subs)}*\n"
            f"• Commands available: *{len(COMMAND_REGISTRY)}*\n"
            f"• Use /alerts list to see your subscriptions."
        )

    # ── Market ──

    async def _h_sectors(self, *_a, **_k) -> BotResponse:
        sectors = await self.sectors.get_all_sectors()
        if not sectors:
            return BotResponse("⚠️ Sector data unavailable right now.", error=True)
        sectors_sorted = sorted(sectors, key=lambda s: s.get("pChange") or 0, reverse=True)
        lines = ["📊 *Sector Performance*\n"]
        for s in sectors_sorted[:12]:
            pc = s.get("pChange") or 0
            emoji = "📈" if pc > 0 else "📉" if pc < 0 else "➡️"
            lines.append(f"{emoji} *{s.get('name', '?')}*: {_fmt_pct(pc)}")
        return BotResponse(
            "\n".join(lines),
            actions=[
                BotAction("Rotation", "/rotation"),
                BotAction("Heatmap", "/heatmap"),
                BotAction("Top movers", "/movers"),
            ],
        )

    async def _h_rotation(self, *_a, **_k) -> BotResponse:
        # Telegram service has its own rich Markdown formatter — re-use via wrapper
        from .telegram_service import _format_rotation_message  # noqa: PLC0415
        try:
            r = await self.sectors.get_sector_rotation()
            text = _format_rotation_message(r)
        except Exception:
            return BotResponse("⚠️ Rotation data unavailable. Try again shortly.",
                               error=True)
        return BotResponse(text, actions=[
            BotAction("Sectors", "/sectors"),
            BotAction("Heatmap", "/heatmap"),
        ])

    async def _h_movers(self, *_a, **_k) -> BotResponse:
        try:
            data = await self.sectors.get_top_movers()  # type: ignore[attr-defined]
        except AttributeError:
            data = None
        if not data:
            sectors = await self.sectors.get_all_sectors()
            data = {
                "gainers": sorted(sectors, key=lambda s: s.get("pChange") or 0,
                                  reverse=True)[:5],
                "losers": sorted(sectors, key=lambda s: s.get("pChange") or 0)[:5],
            }
        lines = ["🚀 *Top Gainers*"]
        for s in (data.get("gainers") or [])[:5]:
            name = s.get("symbol") or s.get("name", "?")
            lines.append(f"  • *{name}* {_fmt_pct(s.get('pChange'))}")
        lines.append("\n📉 *Top Losers*")
        for s in (data.get("losers") or [])[:5]:
            name = s.get("symbol") or s.get("name", "?")
            lines.append(f"  • *{name}* {_fmt_pct(s.get('pChange'))}")
        return BotResponse("\n".join(lines))

    async def _h_heatmap(self, *_a, **_k) -> BotResponse:
        sectors = await self.sectors.get_all_sectors()
        if not sectors:
            return BotResponse("⚠️ Heatmap unavailable.", error=True)
        lines = ["🗺 *Sector Heatmap*\n"]
        for s in sorted(sectors, key=lambda x: x.get("pChange") or 0, reverse=True):
            pc = s.get("pChange") or 0
            cell = "🟩" if pc > 1 else "🟢" if pc > 0 else "⬛" if pc == 0 else "🔴" if pc > -1 else "🟥"
            lines.append(f"{cell} {s.get('name', '?')}: {_fmt_pct(pc)}")
        return BotResponse("\n".join(lines))

    async def _h_news(self, channel: str, chat_id: str, args: list[str],
                      raw: str) -> BotResponse:
        if self.news is None:
            try:
                from . import news_service as _ns  # noqa: PLC0415
                self.news = _ns
            except Exception:
                return BotResponse("⚠️ News module not available.", error=True)
        try:
            symbol = args[0].upper() if args else ""
            feed = await self.news.get_news_feed(search=symbol, limit=8)
        except Exception as e:
            return BotResponse(f"⚠️ News fetch failed: {e}", error=True)
        items = (feed.get("articles") or feed.get("items")
                 or feed.get("news") or [])[:6]
        if not items:
            return BotResponse("No fresh news right now.")
        lines = [f"📰 *Latest news* {f'· {symbol}' if args else ''}\n"]
        for it in items:
            t = it.get("title") or "?"
            src = it.get("source") or it.get("publisher") or ""
            sent = it.get("sentiment") or ""
            sent_emoji = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}.get(sent, "")
            lines.append(f"{sent_emoji} *{t[:120]}*\n   _{src}_")
        return BotResponse("\n".join(lines))

    # ── Stock ──

    def _resolve_symbol(self, args: list[str], raw: str) -> Optional[str]:
        if args:
            joined = " ".join(args)
            parsed = self.nlp.parse(joined)
            if parsed["stocks"]:
                return parsed["stocks"][0]
            return joined.split()[0].upper()
        parsed = self.nlp.parse(raw)
        return parsed["stocks"][0] if parsed["stocks"] else None

    async def _h_analyze(self, channel, chat_id, args, raw) -> BotResponse:
        symbol = self._resolve_symbol(args, raw)
        if not symbol:
            return BotResponse("Usage: `/analyze SYMBOL`", error=True)
        d = await self.stocks.get_stock_details(symbol)
        if d.get("error"):
            return BotResponse(f"⚠️ {d['error']}", error=True)
        ta = d.get("technicalAnalysis") or {}
        entry = d.get("entryRecommendation") or {}
        price_dir = "📈" if (d.get("pChange") or 0) >= 0 else "📉"
        lines = [
            f"{price_dir} *{d.get('companyName', symbol)}* ({symbol})",
            f"Price: *{_fmt_price(d.get('lastPrice'))}* ({_fmt_pct(d.get('pChange'))})",
            f"Trend: *{_safe(ta.get('trend', 'N/A'))}*",
        ]
        if ta.get("rsi") is not None:
            lines.append(f"RSI(14): *{ta['rsi']:.1f}* {_safe(ta.get('rsiZone',''))}")
        macd_x = (ta.get("macd") or {}).get("crossover")
        if macd_x:
            lines.append(f"MACD: *{_safe(macd_x)}*")
        if ta.get("nearestSupport"):
            lines.append(f"Support: {_fmt_price(ta['nearestSupport'])}")
        if ta.get("nearestResistance"):
            lines.append(f"Resistance: {_fmt_price(ta['nearestResistance'])}")
        if entry.get("entryCall"):
            lines.append(f"\n🎯 *Signal:* {_safe(entry.get('entryCall'))}")
            if entry.get("summary"):
                lines.append(f"_{entry['summary']}_")
        self._ctx[chat_id] = {"symbol": symbol}
        return BotResponse(
            "\n".join(lines),
            actions=[
                BotAction(f"Council {symbol}",  f"/council {symbol}"),
                BotAction(f"Fundas {symbol}",   f"/fundas {symbol}"),
                BotAction(f"Entry {symbol}",    f"/entry {symbol}"),
                BotAction(f"Forecast {symbol}", f"/forecast {symbol}"),
                BotAction(f"Holders {symbol}",  f"/holders {symbol}"),
                BotAction(f"News {symbol}",     f"/news {symbol}"),
            ],
        )

    async def _h_entry(self, channel, chat_id, args, raw) -> BotResponse:
        symbol = self._resolve_symbol(args, raw)
        if not symbol:
            return BotResponse("Usage: `/entry SYMBOL`", error=True)
        d = await self.stocks.get_stock_details(symbol)
        if d.get("error"):
            return BotResponse(f"⚠️ {d['error']}", error=True)
        er = d.get("entryRecommendation") or {}
        if not er:
            return BotResponse(f"No entry signal for *{symbol}* right now.")
        lines = [
            f"🎯 *Entry Signal: {symbol}*\n",
            f"Signal: *{_safe(er.get('entryCall', 'N/A'))}*",
            f"Confidence: *{er.get('confidence', 'N/A')}*",
        ]
        if er.get("targetPrice"):
            lines.append(f"Target: {_fmt_price(er['targetPrice'])}")
        if er.get("stopLoss"):
            lines.append(f"Stop Loss: {_fmt_price(er['stopLoss'])}")
        if er.get("riskReward"):
            lines.append(f"R:R: *{er['riskReward']}:1*")
        if er.get("summary"):
            lines.append(f"\n_{er['summary']}_")
        return BotResponse("\n".join(lines))

    async def _h_dcf(self, channel, chat_id, args, raw) -> BotResponse:
        symbol = self._resolve_symbol(args, raw)
        if not symbol:
            return BotResponse("Usage: `/dcf SYMBOL`", error=True)
        from . import dcf_service
        try:
            res = await dcf_service.compute_dcf(symbol)
        except Exception as exc:
            logger.exception("dcf failed for %s", symbol)
            return BotResponse(
                f"⚠️ DCF failed for {symbol}: {exc}", error=True,
                actions=[BotAction(f"Analyze {symbol}", f"/analyze {symbol}")],
            )
        if res.get("error"):
            return BotResponse(
                f"⚠️ {res['error']}", error=True,
                actions=[BotAction(f"Analyze {symbol}", f"/analyze {symbol}")],
            )

        a = res["assumptions"]
        iv  = res["intrinsicValue"]
        cp  = res.get("currentPrice")
        mos = res.get("marginOfSafety")
        verdict = res.get("verdict", "UNKNOWN")
        verdict_emoji = {"UNDERVALUED": "🟢", "FAIR": "🟡",
                         "OVERVALUED": "🔴"}.get(verdict, "⚪")

        lines = [
            f"📐 *DCF intrinsic value: {symbol}*",
            f"_{res.get('companyName', symbol)}_\n",
            f"Intrinsic value: *₹{iv:,.2f}* / share",
        ]
        if cp:
            lines.append(f"Current price:   ₹{cp:,.2f}")
        if mos is not None:
            lines.append(
                f"Margin of safety: *{mos*100:+.1f}%*  {verdict_emoji} {verdict}"
            )
        lines.append("")
        lines.append("*Assumptions*")
        lines.append(f"• Base FCF: ₹{a['baseFcfCr']:,.0f} Cr (avg of last positives)")
        lines.append(f"• Growth Y1-5: {a['growthYears1to5Pct']:.1f}%  ·  "
                     f"Y6-10: {a['growthYears6to10Pct']:.1f}%  ·  "
                     f"Terminal: {a['terminalGrowthPct']:.1f}%")
        lines.append(f"• WACC: {a['waccPct']:.2f}%  "
                     f"(rf {a['riskFreePct']:.2f}% + β {a['beta']} × ERP "
                     f"{a['equityRiskPremiumPct']:.0f}%)")
        net_debt = a['netDebtCr']
        nd_label = (f"net cash ₹{-net_debt:,.0f} Cr" if net_debt < 0
                    else f"net debt ₹{net_debt:,.0f} Cr")
        lines.append(f"• Shares: {a['sharesOutstandingCr']:,.2f} Cr  ·  {nd_label}")
        lines.append(f"• Horizon: {a['horizonYears']}y explicit + Gordon terminal")
        lines.append(f"\n_Source: {res.get('source','yahoo+fred')} · "
                     "growth from {gs}_".format(gs=a.get("growthSource", "n/a")))

        return BotResponse(
            "\n".join(lines),
            actions=[
                BotAction(f"Forecast {symbol}", f"/forecast {symbol}"),
                BotAction(f"Analyze {symbol}",  f"/analyze {symbol}"),
                BotAction(f"Sentiment {symbol}", f"/sentiment {symbol}"),
            ],
        )

    async def _h_sentiment(self, channel, chat_id, args, raw) -> BotResponse:
        symbol = self._resolve_symbol(args, raw)
        if not symbol:
            return BotResponse("Usage: `/sentiment SYMBOL`", error=True)
        if not self.hydra:
            return BotResponse("⚠️ Sentiment engine unavailable.", error=True)
        try:
            res = await self.hydra._run_sentiment(symbol)
        except Exception as e:
            return BotResponse(f"⚠️ Sentiment failed: {e}", error=True)
        return BotResponse(f"💬 {res.get('plain_english') or res.get('summary')}")

    async def _h_forecast(self, channel, chat_id, args, raw) -> BotResponse:
        symbol = self._resolve_symbol(args, raw)
        if not symbol:
            return BotResponse("Usage: `/forecast SYMBOL [days]`", error=True)
        days = 5
        for a in args:
            m = re.match(r"^(\d+)d?$", a)
            if m:
                days = max(1, min(30, int(m.group(1))))
                break
        if not self.hydra:
            return BotResponse("⚠️ Forecast engine unavailable.", error=True)
        try:
            res = await self.hydra._run_forecast(symbol, days, raw)
        except Exception as e:
            return BotResponse(f"⚠️ Forecast failed: {e}", error=True)
        if "error" in (res.get("result") or {}):
            return BotResponse(f"⚠️ {res['result']['error']}", error=True)
        return BotResponse(
            f"🔮 *Forecast {symbol} · {days}d*\n\n"
            f"{res.get('plain_english') or res.get('summary')}",
            actions=[
                BotAction(f"Analyze {symbol}", f"/analyze {symbol}"),
                BotAction(f"Sentiment {symbol}", f"/sentiment {symbol}"),
            ],
        )

    # ── Patterns / scanners ──

    async def _h_patterns(self, *_a, **_k) -> BotResponse:
        d = await self.patterns.get_patterns()
        if not d.get("patterns"):
            return BotResponse("No patterns detected. Try /scan to refresh.")
        lines = [f"🕯️ *Chart Patterns*",
                 f"\n📈 *CALL signals ({d.get('callSignals', 0)}):*"]
        for p in (d.get("topCalls") or [])[:5]:
            lines.append(f"  • *{p['symbol']}* — {_safe(p.get('pattern'))} "
                         f"({p.get('confidence', 0):.0f}%)")
        lines.append(f"\n📉 *PUT signals ({d.get('putSignals', 0)}):*")
        for p in (d.get("topPuts") or [])[:3]:
            lines.append(f"  • *{p['symbol']}* — {_safe(p.get('pattern'))} "
                         f"({p.get('confidence', 0):.0f}%)")
        return BotResponse("\n".join(lines), actions=[
            BotAction("Refresh scan", "/scan"),
        ])

    async def _h_scan(self, *_a, **_k) -> BotResponse:
        # Scans now run cache-first in the background over the full universe.
        # Kick it and return immediately; results stream into /patterns.
        r = await self.patterns.trigger_scan()
        return BotResponse(
            f"🔍 *Scan started* across *{r.get('universeScanned', 0)}* stocks.\n"
            "It runs in the background — use /patterns in a minute for results.",
            actions=[BotAction("View patterns", "/patterns")],
        )

    async def _h_scanners(self, channel, chat_id, args, raw) -> BotResponse:
        sub = (args[0].lower() if args else "list")
        if sub == "list" or not args:
            all_s = self.scanners.get_all_scanners()
            if not all_s:
                return BotResponse("No custom scanners defined.")
            lines = ["🔎 *Custom Scanners*"]
            for s in all_s[:20]:
                lines.append(f"  • `{s['id']}` — {s['name']}")
            lines.append("\nRun with `/scanners run <id>`")
            return BotResponse("\n".join(lines), actions=[
                BotAction(f"Run {s['id']}", f"/scanners run {s['id']}")
                for s in all_s[:4]
            ])
        if sub == "run":
            sid = args[1] if len(args) > 1 else ""
            if not sid:
                return BotResponse("Usage: `/scanners run <id>`", error=True)
            r = await self.scanners.run_scanner(sid)
            if r.get("error"):
                return BotResponse(f"⚠️ {r['error']}", error=True)
            top = "\n".join(
                f"  • {s['symbol']} {_fmt_price(s.get('lastPrice'))}"
                for s in (r.get("results") or [])[:8]
            ) or "  (no matches)"
            return BotResponse(
                f"🔎 *{r['scannerName']}*\n"
                f"Scanned: *{r.get('totalScanned', 0)}* · "
                f"Matched: *{r.get('totalMatched', 0)}*\n\n"
                f"{top}"
            )
        return BotResponse("Usage: `/scanners list` or `/scanners run <id>`",
                           error=True)

    # ── Quant: pairs, backtest, var, portfolio ──

    async def _h_pairs(self, channel, chat_id, args, raw) -> BotResponse:
        if not self.hydra:
            return BotResponse("⚠️ Pairs engine unavailable.", error=True)
        parsed = self.nlp.parse(" ".join(args) if args else raw)
        syms = parsed.get("stocks") or [a.upper() for a in args[:2]]
        if len(syms) < 2:
            return BotResponse("Usage: `/pairs SYMBOL_A SYMBOL_B`", error=True)
        try:
            res = await self.hydra._run_pair_analysis(syms[0], syms[1])
        except Exception as e:
            return BotResponse(f"⚠️ Pairs analysis failed: {e}", error=True)
        return BotResponse(
            f"🔗 *Pairs {syms[0]} / {syms[1]}*\n\n"
            f"{res.get('plain_english') or res.get('summary')}",
            actions=[BotAction(f"Backtest {syms[0]} {syms[1]}",
                               f"/backtest {syms[0]} {syms[1]}")],
        )

    async def _h_backtest(self, channel, chat_id, args, raw) -> BotResponse:
        if not self.hydra:
            return BotResponse("⚠️ Backtest engine unavailable.", error=True)
        parsed = self.nlp.parse(" ".join(args) if args else raw)
        syms = parsed.get("stocks") or [a.upper() for a in args[:2]]
        if len(syms) < 2:
            return BotResponse("Usage: `/backtest SYMBOL_A SYMBOL_B`", error=True)
        try:
            res = await self.hydra._run_backtest(syms[0], syms[1])
        except Exception as e:
            return BotResponse(f"⚠️ Backtest failed: {e}", error=True)
        if res.get("error"):
            return BotResponse(f"⚠️ {res['error']}", error=True)
        return BotResponse(
            f"📈 *Backtest {syms[0]}/{syms[1]}*\n\n"
            f"{res.get('plain_english') or res.get('summary')}"
        )

    async def _h_var(self, channel, chat_id, args, raw) -> BotResponse:
        holdings = parse_inline_holdings(raw)
        if not holdings:
            # Fall back to symbol-only equal-weight VaR via Hydra
            if not self.hydra:
                return BotResponse("Usage: `/var RELIANCE:10@2400 TCS:5`",
                                   error=True)
            parsed = self.nlp.parse(raw)
            syms = parsed.get("stocks") or [a.upper() for a in args]
            if not syms:
                return BotResponse("Usage: `/var SYM:qty[@avg] …`", error=True)
            try:
                res = await self.hydra._run_var(syms[:5])
            except Exception as e:
                return BotResponse(f"⚠️ VaR failed: {e}", error=True)
            return BotResponse(
                f"📉 *VaR (equal-weight)*\n\n"
                f"{res.get('plain_english') or res.get('summary')}"
            )

        # Stateless VaR from inline holdings — fetch quotes, build closes_map
        from . import hydra_var_service as hv  # noqa: PLC0415
        from . import hydra_db_service as hdb  # noqa: PLC0415

        syms = [h["symbol"] for h in holdings]
        await asyncio.gather(*[hdb.update_ticker(s) for s in syms],
                             return_exceptions=True)

        closes_map: dict[str, list[float]] = {}
        for s in syms:
            rows = hdb.get_history(s, days=365)
            closes_map[s] = [r["close"] for r in rows if r.get("close")]

        # Use last close as price proxy for weighting
        weights: list[float] = []
        portfolio_value = 0.0
        valid_syms: list[str] = []
        for h in holdings:
            closes = closes_map.get(h["symbol"]) or []
            if not closes:
                continue
            last = closes[-1]
            mv = last * h["qty"]
            portfolio_value += mv
            valid_syms.append(h["symbol"])
            weights.append(mv)
        if not valid_syms:
            return BotResponse("⚠️ Could not load price history for those symbols.",
                               error=True)
        weights = [w / portfolio_value for w in weights]

        result = hv.portfolio_var(
            symbols=valid_syms, closes_map=closes_map, weights=weights,
            confidence=0.95, horizon_days=1, portfolio_value=portfolio_value,
        )
        if result.get("error"):
            return BotResponse(f"⚠️ {result['error']}", error=True)
        return BotResponse(
            f"📉 *Portfolio VaR (95%, 1d)*\n\n"
            f"Holdings: {', '.join(valid_syms)}\n"
            f"Market value: ₹{portfolio_value:,.0f}\n"
            f"VaR: *{result.get('portfolioVarPct', '?')}%* "
            f"(₹{float(result.get('portfolioVarAbs') or 0):,.0f})"
        )

    async def _h_portfolio(self, channel, chat_id, args, raw) -> BotResponse:
        holdings = parse_inline_holdings(raw)
        if not holdings:
            return BotResponse(
                "Paste your holdings inline:\n"
                "`/portfolio RELIANCE:10@2400 TCS:5@3500`",
                error=True,
            )
        # Pull spot prices in parallel
        async def _q(h: dict) -> dict:
            try:
                d = await self.stocks.get_stock_details(h["symbol"])
                return {**h, "lastPrice": d.get("lastPrice"),
                        "pChange": d.get("pChange")}
            except Exception:
                return {**h, "lastPrice": None, "pChange": None}

        rows = await asyncio.gather(*[_q(h) for h in holdings])
        total_mv = 0.0
        total_cost = 0.0
        lines = ["💼 *Portfolio P&L*\n"]
        lines.append("`Symbol      Qty   Avg     LTP     P&L`")
        for r in rows:
            sym, qty = r["symbol"], r["qty"]
            ltp = r.get("lastPrice")
            avg = r.get("avg")
            if ltp is None:
                lines.append(f"`{sym:<10} {qty:>5}  {(avg or 0):>6.2f}  N/A      —`")
                continue
            mv = ltp * qty
            total_mv += mv
            if avg is not None:
                cost = avg * qty
                total_cost += cost
                pnl = mv - cost
                pnl_pct = (pnl / cost * 100) if cost else 0
                lines.append(
                    f"`{sym:<10} {qty:>5}  {avg:>6.2f}  {ltp:>6.2f}  "
                    f"{pnl:>+8.0f} ({pnl_pct:+.1f}%)`"
                )
            else:
                lines.append(
                    f"`{sym:<10} {qty:>5}     —    {ltp:>6.2f}  "
                    f"MV ₹{mv:,.0f}`"
                )
        total_pnl = total_mv - total_cost if total_cost else 0
        lines.append(f"\n*Market value:* ₹{total_mv:,.0f}")
        if total_cost:
            lines.append(
                f"*Cost basis:* ₹{total_cost:,.0f}  *P&L:* ₹{total_pnl:+,.0f} "
                f"({total_pnl / total_cost * 100:+.2f}%)"
            )
        sym_list = " ".join(f"{r['symbol']}:{r['qty']}" for r in rows)
        return BotResponse(
            "\n".join(lines),
            actions=[BotAction("Compute VaR", f"/var {sym_list}")],
        )

    # ── Options ──

    async def _h_greeks(self, channel, chat_id, args, raw) -> BotResponse:
        # Usage: /greeks SYM CALL|PUT STRIKE DAYS [IV%]
        if len(args) < 4:
            return BotResponse(
                "Usage: `/greeks SYM CALL|PUT STRIKE DAYS [IV%]`\n"
                "Example: `/greeks NIFTY CALL 22000 7 14`",
                error=True,
            )
        from .options_service import bs_greeks, RISK_FREE_RATE  # noqa: PLC0415
        from ..routes.options import _fetch_spot_and_hv  # noqa: PLC0415
        symbol = args[0].upper()
        opt_type = args[1].lower()
        try:
            K = float(args[2]); days = int(args[3])
        except ValueError:
            return BotResponse("Strike & days must be numeric.", error=True)
        if opt_type not in ("call", "put"):
            return BotResponse("Option type must be CALL or PUT.", error=True)
        try:
            spot = await _fetch_spot_and_hv(symbol)
        except Exception as e:
            return BotResponse(f"⚠️ Spot fetch failed: {e}", error=True)
        S = spot["spot"]
        try:
            sigma = float(args[4]) / 100 if len(args) > 4 else spot["hv30"]
        except ValueError:
            sigma = spot["hv30"]
        T = max(1, days) / 365.0
        g = bs_greeks(S, K, T, RISK_FREE_RATE, sigma, opt_type)
        return BotResponse(
            f"🧮 *Greeks · {symbol} {opt_type.upper()} {K} · {days}d*\n\n"
            f"Spot: ₹{S:.2f}  IV: {sigma*100:.1f}%\n"
            f"Δ Delta: *{g.get('delta', 0):.4f}*\n"
            f"Γ Gamma: *{g.get('gamma', 0):.6f}*\n"
            f"Θ Theta: *{g.get('theta', 0):.4f}*/day\n"
            f"V Vega:  *{g.get('vega', 0):.4f}*\n"
            f"ρ Rho:   *{g.get('rho', 0):.4f}*",
            actions=[
                BotAction(f"Payoff {symbol}",
                          f"/payoff {symbol} long_{opt_type} {K:.0f}"),
            ],
        )

    async def _h_payoff(self, channel, chat_id, args, raw) -> BotResponse:
        # /payoff SYM STRATEGY STRIKE [WIDTH]
        if len(args) < 3:
            return BotResponse(
                "Usage: `/payoff SYM STRATEGY STRIKE [WIDTH]`\n"
                "Strategies: long_call, long_put, straddle, strangle, "
                "bull_call, bear_put, iron_condor",
                error=True,
            )
        from .options_service import strategy_payoff_curve  # noqa: PLC0415
        from ..routes.options import _fetch_spot_and_hv, _build_synthetic_legs  # noqa: PLC0415
        symbol = args[0].upper()
        strategy = args[1].lower()
        try:
            lots = int(float(args[3])) if len(args) > 3 else 1
        except ValueError:
            lots = 1
        try:
            spot = await _fetch_spot_and_hv(symbol)
        except Exception as e:
            return BotResponse(f"⚠️ Spot fetch failed: {e}", error=True)
        S = spot["spot"]; lot_size = spot["lot_size"]
        legs = _build_synthetic_legs(strategy, S, symbol, lots)
        if not legs:
            return BotResponse(
                f"⚠️ Strategy `{strategy}` not recognised. Try long_call, "
                "long_put, long_straddle, short_straddle, bull_call_spread, "
                "bear_put_spread, iron_condor, covered_call.",
                error=True,
            )
        for leg in legs:
            leg.setdefault("lot_size", lot_size)
        curve = strategy_payoff_curve(legs, spot_min=S * 0.85, spot_max=S * 1.15)
        bes = curve.get("breakevens") or []
        max_p = curve.get("max_profit")
        max_l = curve.get("max_loss")
        return BotResponse(
            f"🪙 *Payoff · {symbol} {strategy.upper()} × {lots} lot*\n\n"
            f"Spot: ₹{S:.2f}  Lot size: {lot_size}\n"
            f"Net premium: ₹{curve.get('net_premium', 0):,.0f}\n"
            f"Max profit: *{'unlimited' if max_p is None else f'₹{max_p:,.0f}'}*\n"
            f"Max loss:   *{'unlimited' if max_l is None else f'₹{max_l:,.0f}'}*\n"
            f"Breakevens: {', '.join(f'{b:.0f}' for b in bes) or '—'}"
        )

    async def _h_cost(self, channel, chat_id, args, raw) -> BotResponse:
        # /cost SYM CALL|PUT STRIKE QTY PREMIUM
        if len(args) < 5:
            return BotResponse(
                "Usage: `/cost SYM CALL|PUT STRIKE QTY PREMIUM`\n"
                "Returns gross cost + brokerage + STT + GST estimate.",
                error=True,
            )
        from .options_service import get_lot_size  # noqa: PLC0415
        symbol = args[0].upper()
        opt = args[1].lower()
        try:
            K = float(args[2]); qty = int(args[3]); prem = float(args[4])
        except ValueError:
            return BotResponse("Strike/qty/premium must be numeric.", error=True)
        lot = get_lot_size(symbol)
        contracts = max(1, qty // lot if qty >= lot else 1)
        units = contracts * lot
        gross = prem * units
        # Indicative discount-broker fee schedule (Zerodha-style)
        brokerage = min(20, 0.0003 * gross) * 2  # entry + exit
        stt = 0.0005 * gross  # 0.05% premium STT on sell
        gst = 0.18 * brokerage
        exch = 0.00053 * gross
        sebi = 0.000001 * gross
        stamp = 0.00003 * gross
        total = brokerage + stt + gst + exch + sebi + stamp
        net = gross + total
        return BotResponse(
            f"💸 *Cost · {symbol} {opt.upper()} {K:.0f} × {contracts} lot ({units})*\n\n"
            f"Premium gross: ₹{gross:,.0f}\n"
            f"Brokerage:     ₹{brokerage:,.2f}\n"
            f"STT:           ₹{stt:,.2f}\n"
            f"GST (18%):     ₹{gst:,.2f}\n"
            f"Exch + SEBI + stamp: ₹{exch + sebi + stamp:,.2f}\n"
            f"*Total fees:   ₹{total:,.2f}*\n"
            f"*Net outflow:  ₹{net:,.0f}*"
        )

    # ── Sector rotation cockpit ──

    async def _h_cockpit(self, channel, chat_id, args, raw) -> BotResponse:
        from . import sector_rotation_service as _srs  # noqa: PLC0415
        sector_arg = " ".join(args).strip() if args else None

        try:
            data = await _srs.funnel("short")
        except Exception as e:
            return BotResponse(f"⚠️ Cockpit unavailable: {e}", error=True)

        sectors = data.get("sectors", [])
        Q_ORDER   = ["Leading", "Improving", "Weakening", "Lagging"]
        Q_EMOJI   = {"Leading": "🟢", "Improving": "🔵", "Weakening": "🟠", "Lagging": "🔴"}
        Q_LABEL   = {"Leading": "Strong & Rising", "Improving": "Turning Up",
                     "Weakening": "Fading", "Lagging": "Weak"}
        by_quad: dict[str, list] = {q: [] for q in Q_ORDER}
        for s in sectors:
            q = s.get("quadrant", "Lagging")
            if q in by_quad:
                by_quad[q].append(s)

        timeframe = data.get("timeframe", "short").capitalize()
        lines = [f"🧭 *Sector Rotation Cockpit* _({timeframe}-term)_\n"]

        for quad in Q_ORDER:
            items = by_quad[quad]
            if not items:
                continue
            emoji = Q_EMOJI[quad]
            desc  = Q_LABEL[quad]
            lines.append(f"{emoji} *{quad}* — _{desc}_")
            for s in items[:6]:
                name = (s.get("name") or "?").replace("Nifty ", "")
                rs   = s.get("rsPct") or 0
                dl   = " 📦" if s.get("deliveryBuildup") else ""
                lines.append(f"  · {name}: RS {rs:+.1f}%{dl}")
            lines.append("")

        # If a sector arg was given, drill into its winning stocks
        if sector_arg:
            try:
                sl     = await _srs.shortlist(sector=sector_arg)
                stocks = sl.get("stocks", [])
                if stocks:
                    lines.append(f"🏆 *Top Picks — {sector_arg}*")
                    for st in stocks[:8]:
                        sym    = st.get("symbol", "?")
                        rs_v   = st.get("rs") or 0
                        dv     = st.get("delivPct") or 0
                        trend  = "▲" if st.get("aboveTrend") else "▼"
                        score  = st.get("score") or 0
                        lines.append(
                            f"  {trend} *{sym}*  RS {rs_v:+.1f}%  Del {dv:.0f}%  Score {score:.0f}"
                        )
                else:
                    lines.append(f"_No constituents found for: {sector_arg}_")
            except Exception as e:
                lines.append(f"_Could not load stocks for {sector_arg}: {e}_")
        else:
            leading = by_quad.get("Leading", [])
            if leading:
                top = leading[0].get("name", "").replace("Nifty ", "").upper()
                lines.append(f"_Tip: `/cockpit {top}` for winning stocks in the top sector_")

        actions = [BotAction("Rotation", "/rotation"), BotAction("Sectors", "/sectors")]
        if by_quad.get("Leading"):
            top_name = by_quad["Leading"][0].get("name", "").replace("Nifty ", "").upper()
            actions.insert(0, BotAction(f"Picks: {top_name[:10]}", f"/cockpit {top_name}"))
        self._ctx[chat_id] = {"last_cockpit": sector_arg}
        return BotResponse("\n".join(lines), actions=actions)

    # ── Investor council ──

    async def _h_council(self, channel, chat_id, args, raw) -> BotResponse:
        symbol = self._resolve_symbol(args, raw)
        if not symbol:
            return BotResponse("Usage: `/council SYMBOL`", error=True)

        from . import agents_service as _ag  # noqa: PLC0415

        d = await self.stocks.get_stock_details(symbol)
        if d.get("error"):
            return BotResponse(f"⚠️ {d['error']}", error=True)

        try:
            result = _ag.run_council(d)
        except Exception as e:
            return BotResponse(f"⚠️ Council evaluation failed: {e}", error=True)

        council     = result.get("council", {})
        verdict     = council.get("verdict", "HOLD")
        avg_score   = (council.get("avgScore") or 0) * 100
        buy_cnt     = council.get("buyCount", 0)
        avoid_cnt   = council.get("avoidCount", 0)
        hold_cnt    = council.get("holdCount", 0)
        n_total     = buy_cnt + avoid_cnt + hold_cnt or 1

        V_EMOJI = {
            "STRONG_BUY": "🟢🟢", "BUY": "🟢",
            "HOLD": "🟡",
            "AVOID": "🔴", "STRONG_AVOID": "🔴🔴",
        }
        v_emoji  = V_EMOJI.get(verdict, "⚪")
        v_label  = verdict.replace("_", " ")
        buy_bar  = "🟩" * buy_cnt + "⬜" * hold_cnt + "🟥" * avoid_cnt

        price_dir = "📈" if (d.get("pChange") or 0) >= 0 else "📉"
        name      = d.get("companyName", symbol)

        lines = [
            f"{price_dir} *{name}* ({symbol})",
            f"Price: *{_fmt_price(d.get('lastPrice'))}*  {_fmt_pct(d.get('pChange'))}",
            "",
            f"⚖️ *Council Verdict: {v_emoji} {v_label}*",
            f"Avg Score: *{avg_score:.0f}/100*",
            f"{buy_bar}  {buy_cnt}🟢 {hold_cnt}🟡 {avoid_cnt}🔴 / {n_total} legends",
            "",
        ]

        personas = result.get("personas", [])
        buys     = [p for p in personas if p["verdict"] in ("BUY", "STRONG_BUY")]
        avoids   = [p for p in personas if p["verdict"] in ("AVOID", "STRONG_AVOID")]
        holds    = [p for p in personas if p["verdict"] == "HOLD"]

        def _first(name_str): return name_str.split()[0]

        if buys:
            lines.append("🟢 *Backing it:*  " + "  ·  ".join(_first(p["name"]) for p in buys))
        if holds:
            lines.append("🟡 *Watching:*    " + "  ·  ".join(_first(p["name"]) for p in holds))
        if avoids:
            lines.append("🔴 *Avoiding it:* " + "  ·  ".join(_first(p["name"]) for p in avoids))

        # Highlight the most bullish and most cautious voice
        if buys:
            tb = max(buys, key=lambda p: p["score"])
            lines.append(f"\n🏆 *Most bullish:* {tb['name']}  _{tb['firm']}_  —  {tb['score']*100:.0f}/100")
            top_check = next((c for c in tb.get("checklist", []) if c.get("pass")), None)
            if top_check:
                lines.append(f"   ✅ _{top_check['label']}_")
        if avoids:
            ta_ = max(avoids, key=lambda p: p["score"])
            lines.append(f"\n⚠️ *Most cautious:* {ta_['name']}  _{ta_['firm']}_  —  {ta_['score']*100:.0f}/100")
            fail_check = next((c for c in ta_.get("checklist", []) if not c.get("pass")), None)
            if fail_check:
                lines.append(f"   ❌ _{fail_check['label']}_")

        self._ctx[chat_id] = {"symbol": symbol}
        return BotResponse(
            "\n".join(lines),
            actions=[
                BotAction(f"Fundas {symbol}",  f"/fundas {symbol}"),
                BotAction(f"DCF {symbol}",     f"/dcf {symbol}"),
                BotAction(f"Holders {symbol}", f"/holders {symbol}"),
                BotAction(f"Analyze {symbol}", f"/analyze {symbol}"),
            ],
        )

    # ── Shareholding / holders ──

    async def _h_holders(self, channel, chat_id, args, raw) -> BotResponse:
        symbol = self._resolve_symbol(args, raw)
        if not symbol:
            return BotResponse("Usage: `/holders SYMBOL`", error=True)

        try:
            from . import shareholding_service as _shp  # noqa: PLC0415
            data = await _shp.get_shareholding(symbol, quarters=5)
        except Exception as e:
            return BotResponse(f"⚠️ Shareholding fetch failed: {e}", error=True)

        rows = data.get("rows", [])
        if not rows:
            return BotResponse(f"No shareholding data available for *{symbol}*.")

        latest = rows[0]
        prev   = rows[1] if len(rows) > 1 else {}

        def _pct(row, key):
            return row.get(key)

        def _bar(pct, width=10):
            if pct is None:
                return "░" * width
            filled = round(min(max(pct, 0), 100) / 100 * width)
            return "▰" * filled + "░" * (width - filled)

        def _trend(cur_v, prev_v):
            if cur_v is None or prev_v is None:
                return ""
            diff = cur_v - prev_v
            if abs(diff) < 0.05:
                return " ➡️"
            sign = "▲" if diff > 0 else "▼"
            return f" {sign}{abs(diff):.1f}pp"

        def _fmt(v): return f"{v:.1f}%" if v is not None else "N/A"

        date_str = latest.get("asOnDate", "")[:10]
        promoter = _pct(latest, "promoterPct")
        fii      = _pct(latest, "fiiPct")
        dii      = _pct(latest, "diiPct")
        public_  = _pct(latest, "publicPct")
        govt     = _pct(latest, "govtPct")
        pledge   = _pct(latest, "promoterPledgePct") or 0

        p_pr = _pct(prev, "promoterPct")
        p_fi = _pct(prev, "fiiPct")
        p_di = _pct(prev, "diiPct")
        p_pu = _pct(prev, "publicPct")

        lines = [
            f"🏦 *Shareholding Pattern — {symbol}*",
            f"_Quarter ending: {date_str}_",
            "",
        ]
        if promoter is not None:
            lines.append(
                f"🏢 *Promoter:* {_fmt(promoter)}{_trend(promoter, p_pr)}  `{_bar(promoter)}`"
            )
        if fii is not None:
            lines.append(
                f"🌍 *FII / FPI:* {_fmt(fii)}{_trend(fii, p_fi)}  `{_bar(fii)}`"
            )
        if dii is not None:
            lines.append(
                f"🏛 *DII:*       {_fmt(dii)}{_trend(dii, p_di)}  `{_bar(dii)}`"
            )
        if public_ is not None:
            lines.append(
                f"👥 *Public:*   {_fmt(public_)}{_trend(public_, p_pu)}  `{_bar(public_)}`"
            )
        if govt is not None and govt > 0:
            lines.append(f"🏛 *Govt:*      {_fmt(govt)}")

        if pledge > 0:
            risk_tag = ("  ⚠️ *HIGH RISK*" if pledge > 20
                        else ("  ⚠️ Elevated" if pledge > 10 else ""))
            lines.append(f"\n🔒 *Promoter Pledge:* {pledge:.1f}%{risk_tag}")

        # 4-quarter mini table
        if len(rows) >= 3:
            lines.append("\n*Last 4 quarters (Promoter / FII / DII):*")
            for r in rows[:4]:
                dt = str(r.get("asOnDate", ""))[:7]
                pr = r.get("promoterPct"); fi = r.get("fiiPct"); di = r.get("diiPct")
                def _s(v): return f"{v:.0f}" if v is not None else "—"
                lines.append(f"  `{dt}`  {_s(pr)}% / {_s(fi)}% / {_s(di)}%")

        sources = data.get("sources", [])
        if sources:
            lines.append(f"\n_Sources: {', '.join(sources)}_")

        self._ctx[chat_id] = {"symbol": symbol}
        return BotResponse(
            "\n".join(lines),
            actions=[
                BotAction(f"Council {symbol}",  f"/council {symbol}"),
                BotAction(f"Fundas {symbol}",   f"/fundas {symbol}"),
                BotAction(f"Analyze {symbol}",  f"/analyze {symbol}"),
            ],
        )

    # ── Fundamentals ──

    async def _h_fundas(self, channel, chat_id, args, raw) -> BotResponse:
        symbol = self._resolve_symbol(args, raw)
        if not symbol:
            return BotResponse("Usage: `/fundas SYMBOL`", error=True)

        from . import agents_service as _ag  # noqa: PLC0415

        d = await self.stocks.get_stock_details(symbol)
        if d.get("error"):
            return BotResponse(f"⚠️ {d['error']}", error=True)

        # get_key_stats gives us a few extra fields (marketCap, 52-week range)
        try:
            ks = await self.stocks.get_key_stats(symbol)
        except Exception:
            ks = {}

        # Build the enriched context the agent personas use — gives us clean
        # normalised ratios (fractions to %, D/E scaling, FCF yield, ROCE etc.)
        merged_d = {**d, **ks}
        ctx = _ag.build_context(merged_d)

        def _r(v, pct=False, dp=2):
            if v is None:
                return "N/A"
            if pct:
                return f"{v * 100:.{dp}f}%"
            return f"{v:.{dp}f}"

        def _cr(v, dp=1):
            """For values already in ratio/pct form (e.g. debtToEquity = 50.0 for 0.5x)."""
            if v is None:
                return "N/A"
            return f"{v:.{dp}f}"

        def _mcap(v):
            if v is None:
                return "N/A"
            cr = v / 1e7
            if cr >= 10000:
                return f"₹{cr/100:.0f}K Cr"
            return f"₹{cr:.0f} Cr"

        name    = d.get("companyName", symbol)
        sector  = ctx.get("sector") or "—"
        price   = ctx.get("lastPrice")
        h52     = ctx.get("high52")
        l52     = ctx.get("low52")
        off_hi  = ctx.get("pctOffHigh")

        lines = [
            f"📋 *Fundamentals — {name}* ({symbol})",
            f"Sector: _{sector}_",
            f"Price: *{_fmt_price(price)}*  ({_fmt_pct(d.get('pChange'))})",
        ]
        if h52 or l52:
            lines.append(
                f"52W: ₹{l52:.0f} — ₹{h52:.0f}"
                + (f"  _{off_hi:+.1f}% from high_" if off_hi is not None else "")
            )
        if ctx.get("marketCap"):
            lines.append(f"Market Cap: *{_mcap(ctx['marketCap'])}*")

        lines.append("\n*— Valuation —*")
        lines.append(f"Trailing P/E: *{_cr(ctx.get('trailingPE'), 1)}x*  |  "
                     f"Forward P/E: {_cr(ctx.get('forwardPE'), 1)}x")
        lines.append(f"P/B: *{_cr(ctx.get('priceToBook'), 2)}x*  |  "
                     f"P/S: {_cr(ctx.get('priceToSales'), 2)}x  |  "
                     f"PEG: {_cr(ctx.get('pegRatio'), 2)}")
        lines.append(f"EV/EBITDA: *{_cr(ctx.get('evToEbitda'), 1)}x*  |  "
                     f"EV/Rev: {_cr(ctx.get('evToRevenue'), 2)}x")

        lines.append("\n*— Profitability —*")
        lines.append(f"ROE: *{_r(ctx.get('returnOnEquity'), pct=True, dp=1)}*  |  "
                     f"ROA: {_r(ctx.get('returnOnAssets'), pct=True, dp=1)}  |  "
                     f"ROCE: {_r(ctx.get('roce'), pct=True, dp=1)}")
        lines.append(f"Gross Margin: *{_r(ctx.get('grossMargin'), pct=True, dp=1)}*  |  "
                     f"Op Margin: {_r(ctx.get('operatingMargin'), pct=True, dp=1)}")
        lines.append(f"Net Margin: *{_r(ctx.get('profitMargin'), pct=True, dp=1)}*  |  "
                     f"FCF Yield: {_r(ctx.get('fcfYield'), dp=1) if ctx.get('fcfYield') else 'N/A'}%")

        lines.append("\n*— Financial Health —*")
        de = ctx.get("debtToEquity")
        de_str = f"{de/100:.2f}x" if de is not None else "N/A"
        lines.append(f"Debt/Equity: *{de_str}*  |  "
                     f"Current Ratio: {_cr(ctx.get('currentRatio'), 2)}  |  "
                     f"Quick: {_cr(ctx.get('quickRatio'), 2)}")
        lines.append(f"Dividend Yield: *{_r(ctx.get('dividendYield'), pct=True, dp=2)}*  |  "
                     f"Beta: {_cr(ctx.get('beta'), 2)}")

        lines.append("\n*— Growth —*")
        lines.append(f"EPS Growth (TTM): *{_r(ctx.get('earningsGrowth'), pct=True, dp=1)}*  |  "
                     f"Rev Growth: {_r(ctx.get('revenueGrowth'), pct=True, dp=1)}")
        lines.append(f"EPS Growth (QoQ): {_r(ctx.get('earningsQuarterlyGrowth'), pct=True, dp=1)}")

        if ctx.get("targetMeanPrice"):
            upside = ((ctx["targetMeanPrice"] / price) - 1) * 100 if price else None
            upside_str = f"  ({'▲' if upside and upside > 0 else '▼'}{abs(upside):.0f}% upside)" \
                if upside is not None else ""
            lines.append(f"\n🎯 *Analyst Target:* {_fmt_price(ctx['targetMeanPrice'])}{upside_str}")

        self._ctx[chat_id] = {"symbol": symbol}
        return BotResponse(
            "\n".join(lines),
            actions=[
                BotAction(f"Council {symbol}",  f"/council {symbol}"),
                BotAction(f"DCF {symbol}",      f"/dcf {symbol}"),
                BotAction(f"Holders {symbol}",  f"/holders {symbol}"),
                BotAction(f"Analyze {symbol}",  f"/analyze {symbol}"),
            ],
        )

    # ── Alerts ──

    async def _h_alerts(self, channel, chat_id, args, raw) -> BotResponse:
        sub = args[0].lower() if args else "list"
        chat_id = str(chat_id)

        if sub == "list":
            subs = bot_alerts.list_alerts(channel, chat_id)
            if not subs:
                return BotResponse(
                    "🔕 No alerts active for this chat.\n"
                    "Add one with `/alerts add SYMBOL TYPE VALUE`\n"
                    "Types: `price_above`, `price_below`, `pct_change`, "
                    "`rsi_above`, `rsi_below`, `pattern`."
                )
            lines = ["🔔 *Active alerts*"]
            for s in subs:
                desc = _describe_alert(s)
                lines.append(f"  • `{s['id'][:8]}` · {desc}")
            lines.append("\nRemove with `/alerts remove <id>` or `/alerts clear`.")
            return BotResponse("\n".join(lines))

        if sub == "add":
            # /alerts add SYMBOL TYPE VALUE
            if len(args) < 4:
                return BotResponse(
                    "Usage: `/alerts add SYMBOL TYPE VALUE`\n"
                    "Example: `/alerts add RELIANCE price_above 2900`",
                    error=True,
                )
            symbol = args[1].upper()
            kind = args[2].lower()
            valid = {"price_above", "price_below", "pct_change",
                     "rsi_above", "rsi_below", "pattern"}
            if kind not in valid:
                return BotResponse(
                    f"⚠️ Unknown alert type. Choose: {', '.join(sorted(valid))}.",
                    error=True,
                )
            payload: dict[str, Any] = {"kind": kind, "symbol": symbol}
            if kind == "pattern":
                payload["signal"] = args[3].upper() if args[3].upper() in (
                    "CALL", "PUT") else None
            else:
                try:
                    payload["threshold"] = float(args[3])
                except ValueError:
                    return BotResponse("Value must be numeric.", error=True)
            sub_obj = bot_alerts.add_alert(channel, chat_id, payload)
            return BotResponse(
                f"✅ Alert added: {_describe_alert(sub_obj)}\nID `{sub_obj['id'][:8]}`"
            )

        if sub == "remove":
            if len(args) < 2:
                return BotResponse("Usage: `/alerts remove <id>`", error=True)
            target = args[1]
            # Allow short ID prefix
            subs = bot_alerts.list_alerts(channel, chat_id)
            match = next((s for s in subs if s["id"].startswith(target)), None)
            if not match:
                return BotResponse("⚠️ No alert with that ID.", error=True)
            bot_alerts.remove_alert(channel, chat_id, match["id"])
            return BotResponse(f"🗑️ Removed alert `{match['id'][:8]}`.")

        if sub == "clear":
            n = bot_alerts.clear_alerts(channel, chat_id)
            return BotResponse(f"🗑️ Removed *{n}* alert(s).")

        return BotResponse(
            "Usage: `/alerts list|add SYM TYPE VAL|remove ID|clear`",
            error=True,
        )


def _describe_alert(s: dict) -> str:
    kind = s["kind"]
    if kind in ("price_above", "price_below"):
        op = "≥" if kind.endswith("above") else "≤"
        return f"{s['symbol']} price {op} ₹{s['threshold']:.2f}"
    if kind == "pct_change":
        return f"{s['symbol']} day |chg| ≥ {s['threshold']}%"
    if kind in ("rsi_above", "rsi_below"):
        op = "≥" if kind.endswith("above") else "≤"
        return f"{s['symbol']} RSI {op} {s['threshold']:.0f}"
    if kind == "pattern":
        sig = s.get("signal") or "any"
        return f"{s['symbol']} pattern ({sig})"
    return str(s)


def _split_command(text: str) -> tuple[Optional[str], list[str]]:
    """Return (command, args) for slash- or bang-prefixed text. Strips @botname."""
    parts = text.split()
    if not parts:
        return None, []
    head = parts[0]
    if not head.startswith(("/", "!")):
        return None, []
    cmd = head[1:].split("@", 1)[0].lower()
    return cmd, parts[1:]


# ── Doc generator ────────────────────────────────────────────────────────────

def render_command_reference() -> str:
    """Render BOT_COMMANDS.md from the registry."""
    by_cat: dict[str, list[CommandSpec]] = {}
    for c in COMMAND_REGISTRY:
        by_cat.setdefault(c.category, []).append(c)
    lines = [
        "# Bot Command Reference",
        "",
        "_Auto-generated from `app/services/bot_dispatcher.py`._",
        "",
        "Both Telegram and WhatsApp share this command spec. Telegram uses "
        "`/command`, WhatsApp uses `!command`. Either bot also accepts plain "
        "natural language — the NLP layer routes intents to the same handlers.",
        "",
        "All bots are **stateless** with respect to your trading account: "
        "portfolio P&L and VaR commands accept inline holdings of the form "
        "`SYMBOL:qty[@avg]` (e.g. `RELIANCE:10@2400 TCS:5`). Alerts are keyed "
        "only by chat ID — no account linking required.",
        "",
    ]
    for cat, items in by_cat.items():
        lines.append(f"## {cat}")
        lines.append("")
        lines.append("| Command | Aliases | Usage | Description |")
        lines.append("|---------|---------|-------|-------------|")
        for c in items:
            aliases = ", ".join(f"`{a}`" for a in c.aliases) or "—"
            lines.append(
                f"| `/{c.name}` | {aliases} | `{c.usage}` | {c.summary} |"
            )
        lines.append("")
    lines.append("## Inline holdings syntax")
    lines.append("")
    lines.append("```")
    lines.append("RELIANCE:10@2400  → 10 shares of RELIANCE bought at ₹2400")
    lines.append("TCS:5             → 5 shares of TCS, no cost basis")
    lines.append("```")
    lines.append("")
    lines.append("Use this with `/portfolio` (P&L) or `/var` (Value-at-Risk).")
    lines.append("")
    return "\n".join(lines)
