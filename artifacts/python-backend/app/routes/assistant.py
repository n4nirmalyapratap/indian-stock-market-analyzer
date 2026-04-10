"""
assistant.py
Global AI chat assistant — rule-based, zero cost, instant responses.
Uses NLP intent+entity parsing, live market data, and pre-written
plain-English explanations to answer any stock market question.
"""
from __future__ import annotations
import re
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from typing import Any

from ..services.nlp_service import NlpService
from ..services.stocks_service import StocksService
from ..services.sectors_service import SectorsService
from ..services.patterns_service import PatternsService
from ..services.scanners_service import ScannersService
from ..services.nse_service import NseService
from ..services.yahoo_service import YahooService
from ..services.price_service import PriceService

router = APIRouter(prefix="/assistant", tags=["assistant"])

_nse      = NseService()
_yahoo    = YahooService()
_price    = PriceService(_nse, _yahoo)
_nlp      = NlpService()
_stocks   = StocksService(_nse, _yahoo)
_sectors  = SectorsService(_nse, _yahoo)
_patterns = PatternsService(_yahoo, _nse)
_scanners = ScannersService(_price)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _fmtp(n, d=2):
    if n is None: return "—"
    return f"{float(n):.{d}f}%"

def _fmtv(n, d=2):
    if n is None: return "—"
    v = abs(float(n))
    if v >= 1e7: return f"₹{v/1e7:.2f} Cr"
    if v >= 1e5: return f"₹{v/1e5:.2f} L"
    return f"₹{v:,.{d}f}"

def _arrow(n):
    if n is None: return ""
    return "▲" if float(n) >= 0 else "▼"

def _signal_word(n):
    if n is None: return "flat"
    f = float(n)
    if f > 2:   return "strongly up"
    if f > 0.5: return "up"
    if f > 0:   return "slightly up"
    if f < -2:  return "strongly down"
    if f < -0.5: return "down"
    return "slightly down"


# ─── plain-English response builders ──────────────────────────────────────────

def _format_stock(d: dict, symbol: str) -> str:
    name  = d.get("name") or symbol
    price = d.get("lastPrice") or d.get("price")
    chg   = d.get("pChange") or d.get("change")
    high  = d.get("dayHigh") or d.get("high52")
    low   = d.get("dayLow")  or d.get("low52")
    vol   = d.get("totalTradedVolume") or d.get("volume")
    cap   = d.get("marketCap")
    rsi   = d.get("rsi")
    ma20  = d.get("ma20") or d.get("sma20")
    ma50  = d.get("ma50") or d.get("sma50")
    trend = d.get("trend") or d.get("signal")
    rec   = d.get("recommendation")
    sector = d.get("sector") or d.get("industry")

    lines = []

    # Core price
    if price:
        direction = _signal_word(chg)
        chg_str = f" ({_arrow(chg)} {_fmtp(chg)})" if chg is not None else ""
        lines.append(f"**{name} ({symbol})** is trading at **{_fmtv(price)}**{chg_str} — {direction} today.")
    else:
        lines.append(f"Here is what I found about **{name} ({symbol})**:")

    if sector:
        lines.append(f"Sector: {sector}")

    # Range
    if high and low:
        lines.append(f"Today's range: {_fmtv(low)} – {_fmtv(high)}")

    # Market cap
    if cap:
        lines.append(f"Market cap: {_fmtv(cap)}")

    # Volume
    if vol:
        lines.append(f"Volume traded today: {int(float(vol)):,} shares")

    # Technical signals (simple language)
    lines.append("")
    if rsi is not None:
        rsi_v = float(rsi)
        if rsi_v >= 70:
            rsi_desc = f"RSI is {rsi_v:.0f} — the stock looks **overbought** (caution, could pull back)."
        elif rsi_v <= 30:
            rsi_desc = f"RSI is {rsi_v:.0f} — the stock looks **oversold** (could bounce up)."
        else:
            rsi_desc = f"RSI is {rsi_v:.0f} — **neutral zone** (no extreme)."
        lines.append(rsi_desc)

    if ma20 and price:
        p, m = float(price), float(ma20)
        if p > m:
            lines.append(f"Price is **above** its 20-day average ({_fmtv(m)}) — short-term trend is up.")
        else:
            lines.append(f"Price is **below** its 20-day average ({_fmtv(m)}) — short-term trend is weak.")

    if ma50 and price:
        p, m = float(price), float(ma50)
        if p > m:
            lines.append(f"Price is **above** its 50-day average ({_fmtv(m)}) — medium-term trend is up.")
        else:
            lines.append(f"Price is **below** its 50-day average ({_fmtv(m)}) — medium-term trend is weak.")

    if trend:
        lines.append(f"Overall trend signal: **{trend}**")

    if rec:
        lines.append(f"Recommendation: **{rec}**")

    if not rsi and not ma20 and not trend:
        lines.append("Technical indicators are not available for this stock right now.")

    lines.append("")
    lines.append("*Note: This is purely informational. Always do your own research before investing.*")
    return "\n".join(lines)


def _format_sector(d: dict, sector_name: str) -> str:
    name  = d.get("name") or sector_name
    chg   = d.get("pChange") or d.get("change")
    price = d.get("lastPrice") or d.get("indexValue")
    stocks = d.get("stocks") or d.get("constituents") or []
    adv   = d.get("advances") or 0
    dec   = d.get("declines") or 0

    lines = []
    direction = _signal_word(chg)
    chg_str = f" ({_arrow(chg)} {_fmtp(chg)})" if chg is not None else ""
    lines.append(f"**{name}** sector is **{direction}** today{chg_str}.")

    if price:
        lines.append(f"Index level: {_fmtv(price, 0)}")

    if adv or dec:
        lines.append(f"{int(adv)} stocks are up, {int(dec)} stocks are down in this sector.")

    if stocks:
        lines.append("\n**Top stocks in this sector:**")
        for s in stocks[:6]:
            sname = s.get("symbol") or s.get("name") or ""
            sc    = s.get("pChange") or s.get("change") or 0
            sp    = s.get("lastPrice") or s.get("price") or ""
            arrow = _arrow(sc)
            pstr  = f" — {_fmtv(sp)}" if sp else ""
            lines.append(f"- {sname}{pstr} {arrow}{_fmtp(sc)}")

    return "\n".join(lines)


def _format_all_sectors(sectors: list) -> str:
    if not sectors:
        return "Could not fetch sector data right now. Please try again in a minute."

    gainers = sorted([s for s in sectors if (s.get("pChange") or 0) > 0],
                     key=lambda x: x.get("pChange", 0), reverse=True)
    losers  = sorted([s for s in sectors if (s.get("pChange") or 0) < 0],
                     key=lambda x: x.get("pChange", 0))

    lines = ["Here is today's **sector overview** at a glance:\n"]
    lines.append("**Sectors doing well today (gainers):**")
    if gainers:
        for s in gainers[:5]:
            lines.append(f"- **{s.get('name','')}** ▲ {_fmtp(s.get('pChange'))}")
    else:
        lines.append("- None in the green today.")

    lines.append("\n**Sectors under pressure today (losers):**")
    if losers:
        for s in losers[:5]:
            lines.append(f"- **{s.get('name','')}** ▼ {_fmtp(s.get('pChange'))}")
    else:
        lines.append("- All sectors are in the green!")

    return "\n".join(lines)


def _format_rotation(data: dict) -> str:
    leaders   = data.get("leaders") or data.get("outperforming") or []
    laggards  = data.get("laggards") or data.get("underperforming") or []
    summary   = data.get("summary") or data.get("insight") or ""
    breadth   = data.get("breadth") or {}

    lines = ["**Sector Rotation — Where is money moving?**\n"]

    if summary:
        lines.append(summary)
        lines.append("")

    if leaders:
        lines.append("**Buy interest / Outperforming sectors:**")
        for s in leaders[:5]:
            n = s.get("name") or s.get("sector") or str(s)
            c = s.get("pChange") or s.get("change")
            lines.append(f"- **{n}** {_arrow(c)} {_fmtp(c)}")
    else:
        lines.append("No clear sector leaders detected today.")

    lines.append("")
    if laggards:
        lines.append("**Selling pressure / Underperforming sectors:**")
        for s in laggards[:5]:
            n = s.get("name") or s.get("sector") or str(s)
            c = s.get("pChange") or s.get("change")
            lines.append(f"- **{n}** {_arrow(c)} {_fmtp(c)}")

    if breadth:
        adv = breadth.get("advances") or breadth.get("advancing")
        dec = breadth.get("declines") or breadth.get("declining")
        if adv and dec:
            lines.append(f"\nMarket breadth: {int(adv)} advancing vs {int(dec)} declining stocks.")

    lines.append("\n*This shows where institutional money tends to flow — rotate into leaders and away from laggards.*")
    return "\n".join(lines)


def _format_patterns(data: dict, signal: str | None) -> str:
    patterns = data.get("patterns") or []
    summary  = data.get("summary") or {}

    direction = "bullish" if signal == "CALL" else "bearish" if signal == "PUT" else "any"
    lines = [f"**Chart Pattern Scan** — looking for {direction} patterns:\n"]

    bullish = [p for p in patterns if p.get("signal") == "CALL" or p.get("type","").lower() in ("bullish","hammer","morning_star","engulfing_bullish")]
    bearish = [p for p in patterns if p.get("signal") == "PUT" or p.get("type","").lower() in ("bearish","shooting_star","evening_star","engulfing_bearish")]

    show_b = bullish if signal in (None, "CALL") else []
    show_bear = bearish if signal in (None, "PUT") else []

    if show_b:
        lines.append("**Bullish patterns detected (possible upward move):**")
        for p in show_b[:8]:
            sym  = p.get("symbol","?")
            pat  = p.get("pattern") or p.get("type") or "pattern"
            conf = p.get("confidence") or p.get("strength") or ""
            conf_str = f" (confidence: {conf})" if conf else ""
            lines.append(f"- **{sym}** — {pat}{conf_str}")

    if show_bear:
        if show_b:
            lines.append("")
        lines.append("**Bearish patterns detected (possible downward move):**")
        for p in show_bear[:8]:
            sym  = p.get("symbol","?")
            pat  = p.get("pattern") or p.get("type") or "pattern"
            lines.append(f"- **{sym}** — {pat}")

    if not show_b and not show_bear and patterns:
        lines.append(f"Found {len(patterns)} patterns — use the Patterns page to explore them in detail.")
    elif not patterns:
        lines.append("No patterns detected at the moment. Try scanning again shortly.")

    if summary:
        total = summary.get("total") or len(patterns)
        lines.append(f"\nTotal patterns scanned: {total}")

    lines.append("\n*Use the Patterns page for the full interactive pattern dashboard.*")
    return "\n".join(lines)


def _format_scanners(data: dict, scanner_name: str | None) -> str:
    if scanner_name:
        stocks  = data.get("stocks") or data.get("results") or []
        desc    = data.get("description") or ""
        lines = [f"**{scanner_name} Scanner Results:**\n"]
        if desc:
            lines.append(desc)
            lines.append("")
        if stocks:
            for s in stocks[:10]:
                sym = s.get("symbol") or s.get("name") or str(s)
                p   = s.get("lastPrice") or s.get("price") or ""
                c   = s.get("pChange") or s.get("change") or ""
                pstr = f" — {_fmtv(p)}" if p else ""
                cstr = f" {_arrow(c)}{_fmtp(c)}" if c != "" else ""
                lines.append(f"- **{sym}**{pstr}{cstr}")
        else:
            lines.append("No stocks matched this scanner's criteria right now.")
        lines.append("\n*Use the Scanners page to run and configure all available scanners.*")
        return "\n".join(lines)

    # list all scanners
    scanners = data if isinstance(data, list) else (data.get("scanners") or [])
    lines = ["**Available Stock Scanners:**\n"]
    lines.append("These are the scanners I can run for you:\n")
    for sc in scanners:
        name = sc.get("name","?")
        desc = sc.get("description","")
        lines.append(f"- **{name}** — {desc}" if desc else f"- **{name}**")
    lines.append("\nJust ask me to run any of them, e.g. *'Run golden cross scanner'* or *'Show momentum stocks'*.")
    return "\n".join(lines)


# ─── General education Q&A (no live data needed) ─────────────────────────────

_EDUCATION: dict[str, tuple[list[str], str]] = {
    "what_is_nse": (
        ["what is nse", "what is bse", "what is stock exchange", "what is sensex",
         "what is nifty", "what is nifty 50", "explain nse", "explain bse"],
        (
            "**NSE (National Stock Exchange)** is India's largest stock exchange by trading volume.\n\n"
            "- **NIFTY 50** is NSE's benchmark index — it tracks the 50 biggest companies.\n"
            "- **BSE (Bombay Stock Exchange)** is the oldest stock exchange in Asia.\n"
            "- **SENSEX** is BSE's benchmark index — it tracks the 30 biggest companies.\n\n"
            "Both exchanges trade the same companies. NSE is more popular for F&O (futures & options)."
        ),
    ),
    "how_market_works": (
        ["how does stock market work", "how does trading work", "how to invest",
         "basics of stock market", "how to buy stocks", "how to buy shares"],
        (
            "**How the stock market works (in simple terms):**\n\n"
            "1. Companies list their shares on NSE/BSE through an **IPO**.\n"
            "2. After listing, anyone can **buy or sell shares** through a broker (Zerodha, Upstox, etc.).\n"
            "3. The price goes **up** when more people want to buy than sell, and **down** when more want to sell.\n"
            "4. You make a profit by buying low and selling high.\n\n"
            "Market timings: **9:15 AM – 3:30 PM IST**, Monday to Friday."
        ),
    ),
    "what_is_rsi": (
        ["what is rsi", "explain rsi", "rsi indicator", "rsi meaning"],
        (
            "**RSI (Relative Strength Index)** tells you how fast a stock is moving.\n\n"
            "- Scale: **0 to 100**\n"
            "- **Above 70** → Overbought — the stock has moved up a lot, might pull back soon.\n"
            "- **Below 30** → Oversold — the stock has fallen a lot, might bounce soon.\n"
            "- **40–60** → Neutral — no extreme.\n\n"
            "RSI doesn't tell you *when* to buy/sell, just whether a stock is stretched."
        ),
    ),
    "what_is_macd": (
        ["what is macd", "explain macd", "macd indicator"],
        (
            "**MACD (Moving Average Convergence Divergence)** is a trend-following indicator.\n\n"
            "It compares a short-term moving average (12-day) vs a longer one (26-day).\n\n"
            "- When MACD line **crosses above** signal line → bullish signal (possible uptrend).\n"
            "- When MACD line **crosses below** signal line → bearish signal (possible downtrend).\n"
            "- The **histogram** shows the strength of the trend.\n\n"
            "Traders use MACD to spot trend changes early."
        ),
    ),
    "what_is_ema": (
        ["what is ema", "what is sma", "what is moving average", "explain moving average",
         "what is 200 ema", "what is 50 ema", "golden cross", "death cross"],
        (
            "**Moving Averages (MA)** smooth out price data to show the overall trend.\n\n"
            "- **SMA** (Simple MA) — average of last N closing prices.\n"
            "- **EMA** (Exponential MA) — gives more weight to recent prices, reacts faster.\n\n"
            "**Common rules:**\n"
            "- Price **above** 50-day MA → medium-term uptrend.\n"
            "- Price **above** 200-day MA → long-term uptrend.\n"
            "- **Golden Cross** — 50-day MA crosses above 200-day MA → very bullish signal.\n"
            "- **Death Cross** — 50-day MA crosses below 200-day MA → very bearish signal."
        ),
    ),
    "what_is_option": (
        ["what is option", "what are options", "call option", "put option",
         "explain options", "what is call", "what is put", "f&o", "futures and options"],
        (
            "**Options** are contracts that give you the *right* (but not obligation) to buy/sell a stock at a fixed price.\n\n"
            "- **Call Option** → Bet the stock will go **UP**. You profit if it rises above your strike price.\n"
            "- **Put Option** → Bet the stock will go **DOWN**. You profit if it falls below your strike price.\n\n"
            "**Key terms:**\n"
            "- **Strike price** — the fixed price agreed in the contract.\n"
            "- **Premium** — the cost you pay to buy the option.\n"
            "- **Expiry** — the date the contract ends (NIFTY options expire every Thursday).\n\n"
            "Options can be used for hedging your portfolio or for directional bets."
        ),
    ),
    "what_is_sector": (
        ["what is sector", "what are sectors", "market sectors", "sector investing", "sector rotation"],
        (
            "The stock market is divided into **sectors** — groups of companies in the same industry.\n\n"
            "**Main Indian market sectors:**\n"
            "- **IT** — Infosys, TCS, Wipro\n"
            "- **Banking** — HDFC Bank, ICICI Bank, SBI\n"
            "- **Pharma** — Sun Pharma, Cipla, Dr Reddy\n"
            "- **Auto** — Maruti, Tata Motors, Hero MotoCorp\n"
            "- **FMCG** — HUL, ITC, Nestle\n"
            "- **Metal** — Tata Steel, JSW Steel, Hindalco\n\n"
            "**Sector rotation** means money moving from weak sectors to strong ones — it's a key indicator of market trends."
        ),
    ),
    "what_is_market_cap": (
        ["market cap", "large cap", "mid cap", "small cap", "what is market cap",
         "market capitalisation", "market capitalization"],
        (
            "**Market Cap** = Share price × Total shares outstanding.\n\n"
            "It tells you how big a company is:\n\n"
            "- **Large Cap** — Market cap > ₹20,000 Cr. Stable, less risky (e.g. TCS, Reliance).\n"
            "- **Mid Cap** — ₹5,000–₹20,000 Cr. More growth potential, moderate risk.\n"
            "- **Small Cap** — < ₹5,000 Cr. High risk, high potential reward.\n\n"
            "Beginners are usually advised to focus on large-cap stocks first."
        ),
    ),
    "what_is_pe": (
        ["pe ratio", "p/e ratio", "price to earnings", "what is pe", "pe meaning"],
        (
            "**P/E Ratio (Price-to-Earnings)** tells you how much you are paying for every ₹1 of a company's profit.\n\n"
            "- **Formula:** Stock price ÷ Earnings per share (EPS)\n"
            "- A P/E of 20 means you pay ₹20 for every ₹1 of annual profit.\n\n"
            "**How to use it:**\n"
            "- **Low P/E** (vs sector average) → Possibly undervalued — could be a bargain.\n"
            "- **High P/E** → Growth expectations are priced in — expensive if growth doesn't come.\n\n"
            "Always compare P/E with the company's historical average and its sector peers."
        ),
    ),
    "what_is_volume": (
        ["what is volume", "trading volume", "high volume", "volume spike", "why volume matters"],
        (
            "**Volume** is the number of shares traded during a time period.\n\n"
            "- **High volume on a price rise** → strong move, buyers are in control (bullish).\n"
            "- **High volume on a price fall** → strong selling, bears are in control (bearish).\n"
            "- **Low volume** → the move may not sustain — not many people agree with it.\n\n"
            "**Volume spikes** often signal breakouts or reversals. Traders always check volume to confirm price moves."
        ),
    ),
    "what_is_ipo": (
        ["what is ipo", "ipo meaning", "how does ipo work", "initial public offering"],
        (
            "**IPO (Initial Public Offering)** is when a private company first sells its shares to the public.\n\n"
            "1. Company decides to list on NSE/BSE.\n"
            "2. It offers shares at a fixed price (the **issue price**).\n"
            "3. You can **apply** for shares during the IPO window (usually 3 days).\n"
            "4. After listing, shares trade freely on the exchange.\n\n"
            "**Grey market premium (GMP)** is the unofficial price before listing — not always accurate.\n"
            "Many IPOs list at a premium (above issue price), but some can list below too."
        ),
    ),
    "help": (
        ["help", "what can you do", "what can you answer", "how to use", "what can i ask",
         "show commands", "what do you know"],
        (
            "I'm your **Indian Stock Market Assistant** — here to answer questions in simple English!\n\n"
            "**What I can help you with:**\n\n"
            "📊 **Stock analysis** — Ask: *'How is Reliance doing?'* or *'Analyse TCS'*\n"
            "🏭 **Sector overview** — Ask: *'Show IT sector'* or *'Which sectors are up today?'*\n"
            "🔄 **Market rotation** — Ask: *'Where is money flowing?'* or *'Best sectors to invest now?'*\n"
            "📈 **Chart patterns** — Ask: *'Show bullish patterns'* or *'Any breakout stocks?'*\n"
            "🔍 **Stock scanners** — Ask: *'Run golden cross scanner'* or *'Show momentum stocks'*\n"
            "📚 **Education** — Ask: *'What is RSI?'* or *'Explain options'* or *'What is P/E ratio?'*\n\n"
            "Just type your question in plain English — no special commands needed!"
        ),
    ),
}


def _check_education(text: str) -> str | None:
    lower = text.lower()
    best_key = None
    best_count = 0
    for key, (triggers, _) in _EDUCATION.items():
        count = sum(1 for t in triggers if t in lower)
        if count > best_count:
            best_count = count
            best_key = key
    if best_key and best_count > 0:
        return _EDUCATION[best_key][1]
    return None


# ─── Main endpoint ────────────────────────────────────────────────────────────

@router.post("/chat")
async def assistant_chat(body: dict[str, Any]):
    text = (body.get("query") or body.get("message") or body.get("text") or "").strip()
    if not text:
        return JSONResponse(status_code=400, content={"error": "message field is required"})

    # 1. Check education Q&A first (instant, no API call)
    edu = _check_education(text)
    if edu:
        return {"reply": edu, "intent": "education"}

    # 2. Parse intent + entities via NLP service
    try:
        parsed = _nlp.parse(text)
    except Exception as exc:
        return {
            "reply": (
                "Sorry, I had trouble understanding that. Could you rephrase?\n\n"
                f"*(Error: {exc})*"
            ),
            "intent": "error",
        }

    intent  = parsed.get("intent", "rotation_query")
    stocks  = parsed.get("stocks") or []
    sectors = parsed.get("sectors") or []
    signal  = parsed.get("signal")

    try:
        # ── Help ───────────────────────────────────────────────────────────────
        if intent == "help":
            return {"reply": _EDUCATION["help"][1], "intent": "help"}

        # ── Stock analysis ─────────────────────────────────────────────────────
        if intent == "stock_analysis" and stocks:
            sym  = stocks[0]
            data = await _stocks.get_stock_details(sym)
            return {"reply": _format_stock(data, sym), "intent": "stock_analysis", "symbol": sym}

        # ── Sector query ───────────────────────────────────────────────────────
        if intent == "sector_query":
            if sectors:
                sec  = sectors[0]
                data = await _sectors.get_sector_detail(sec)
                return {"reply": _format_sector(data, sec), "intent": "sector_query", "sector": sec}
            else:
                all_s = await _sectors.get_all_sectors()
                if signal == "CALL":
                    filtered = [s for s in all_s if (s.get("pChange") or 0) > 0]
                    return {"reply": _format_all_sectors(filtered or all_s), "intent": "sector_query"}
                elif signal == "PUT":
                    filtered = [s for s in all_s if (s.get("pChange") or 0) < 0]
                    return {"reply": _format_all_sectors(filtered or all_s), "intent": "sector_query"}
                return {"reply": _format_all_sectors(all_s), "intent": "sector_query"}

        # ── Sector rotation ────────────────────────────────────────────────────
        if intent == "rotation_query":
            data = await _sectors.get_sector_rotation()
            return {"reply": _format_rotation(data), "intent": "rotation_query"}

        # ── Pattern scan ───────────────────────────────────────────────────────
        if intent == "pattern_scan":
            data = await _patterns.get_patterns(signal=signal)
            return {"reply": _format_patterns(data, signal), "intent": "pattern_scan"}

        # ── Scanner run ────────────────────────────────────────────────────────
        if intent == "scanner_run":
            all_sc = _scanners.get_all_scanners()
            lower  = text.lower()
            matched = None
            for sc in all_sc:
                if any(w in lower for w in sc["name"].lower().split()):
                    matched = sc
                    break
            if matched:
                result = await _scanners.run_scanner(matched["id"])
                return {"reply": _format_scanners(result, matched["name"]), "intent": "scanner_run"}
            return {"reply": _format_scanners(all_sc, None), "intent": "scanner_run"}

        # ── Analytics / fallback with a stock ────────────────────────────────
        if stocks:
            sym  = stocks[0]
            data = await _stocks.get_stock_details(sym)
            return {"reply": _format_stock(data, sym), "intent": "stock_analysis", "symbol": sym}

        # ── General fallback → sector rotation ────────────────────────────────
        data = await _sectors.get_sector_rotation()
        return {"reply": _format_rotation(data), "intent": "rotation_query"}

    except Exception as e:
        return {
            "reply": (
                f"I found a question about **{intent.replace('_',' ')}**, "
                f"but couldn't load the live data right now.\n\n"
                f"Please try again in a moment. *(Error: {e})*"
            ),
            "intent": "error",
        }
