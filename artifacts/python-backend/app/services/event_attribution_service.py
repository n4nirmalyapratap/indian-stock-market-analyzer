"""
Event Attribution Service
Detects significant price peaks and troughs in a stock's history,
then uses the LLM to explain the cause of each move.
Results are cached in-process for 7 days (historical data rarely changes).
"""

import json
import time
import logging

log = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 7 * 86_400   # 7 days


# ── Swing detection ────────────────────────────────────────────────────────────

def _detect_swings(closes: list[float], dates: list[str], min_pct: float = 0.15) -> list[dict]:
    """
    Zigzag-style swing detector.
    Walks through the weekly price series tracking the current trend direction.
    Emits a confirmed peak/trough whenever the reversal exceeds `min_pct`.
    """
    if len(closes) < 4:
        return []

    events: list[dict] = []

    # Bootstrap direction from the first few bars
    direction = "up" if closes[min(3, len(closes) - 1)] >= closes[0] else "down"
    extreme_price = closes[0]
    extreme_idx   = 0

    for i in range(1, len(closes)):
        p = closes[i]

        if direction == "up":
            if p >= extreme_price:
                extreme_price = p
                extreme_idx   = i
            elif extreme_price > 0 and (extreme_price - p) / extreme_price >= min_pct:
                # Peak confirmed
                prev = events[-1]["price"] if events else closes[0]
                move = (extreme_price - prev) / prev * 100 if prev else 0
                events.append({
                    "idx":       extreme_idx,
                    "date":      dates[extreme_idx],
                    "price":     round(extreme_price, 2),
                    "direction": "peak",
                    "move_pct":  round(move, 1),
                })
                direction     = "down"
                extreme_price = p
                extreme_idx   = i

        else:  # direction == "down"
            if p <= extreme_price:
                extreme_price = p
                extreme_idx   = i
            elif extreme_price > 0 and (p - extreme_price) / extreme_price >= min_pct:
                # Trough confirmed
                prev = events[-1]["price"] if events else closes[0]
                move = (extreme_price - prev) / prev * 100 if prev else 0
                events.append({
                    "idx":       extreme_idx,
                    "date":      dates[extreme_idx],
                    "price":     round(extreme_price, 2),
                    "direction": "trough",
                    "move_pct":  round(move, 1),
                })
                direction     = "up"
                extreme_price = p
                extreme_idx   = i

    return events[:20]   # cap at 20 events


# ── LLM attribution ────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are an expert Indian equity market historian. "
    "You know Indian corporate events, RBI/SEBI actions, government schemes, "
    "global macro events (Fed, geopolitics, oil), and sector dynamics well. "
    "Be concise, factual, and specific to dates."
)

async def _llm_attribute(
    symbol: str,
    company_name: str,
    sector: str,
    events: list[dict],
) -> list[dict]:
    """
    Single batched LLM call: given all events, return a category + reason for each.
    Returns the enriched events list.
    """
    from .ai_client import ask

    events_json = json.dumps(
        [
            {
                "index":     i,
                "date":      ev["date"],
                "direction": ev["direction"],
                "price_inr": ev["price"],
                "move_pct":  ev["move_pct"],
            }
            for i, ev in enumerate(events)
        ],
        indent=2,
    )

    prompt = f"""Stock: {symbol} | Company: {company_name} | Sector: {sector} | Exchange: NSE India

Significant weekly price swings detected (5-year lookback):
{events_json}

For EACH swing, identify the most likely real-world cause.

Category definitions:
- "Earnings"    — quarterly results, guidance change, analyst upgrade/downgrade, management commentary
- "Macro"       — RBI rate decisions, Union Budget, Fed tightening, geopolitical shock (Russia-Ukraine, COVID),
                  FII outflows/inflows, rupee depreciation, crude oil spike
- "Regulatory"  — SEBI order, government scheme (PLI, BharatNet, spectrum auction, PTC policy, import duty),
                  policy announcement directly affecting the company or sector
- "Sector"      — sector-wide re-rating, supply-chain disruption, competitor collapse/win, commodity cycle turn
- "Technical"   — profit-booking after extended rally, stop-loss cascade, support break, holiday thin volumes

Return a JSON ARRAY — one object per event, indexed by "index":
[
  {{
    "index": 0,
    "category": "<one of the five above>",
    "reason": "<2–3 sentences referencing specific events near that date — be factual>"
  }},
  ...
]

Return ONLY the JSON array, no markdown fences, no preamble."""

    raw = await ask(prompt, system=_SYSTEM_PROMPT, max_tokens=2500, temperature=0.2)

    # Parse, tolerating markdown fences
    raw = raw.strip()
    if raw.startswith("```"):
        start = raw.find("[")
        end   = raw.rfind("]") + 1
        raw   = raw[start:end] if start != -1 else "[]"

    try:
        attributions = json.loads(raw)
    except Exception as exc:
        log.warning("event_attribution LLM parse error: %s | raw=%s", exc, raw[:200])
        attributions = []

    attr_map = {a.get("index"): a for a in attributions if isinstance(a, dict)}

    result = []
    for i, ev in enumerate(events):
        attr = attr_map.get(i, {})
        result.append({
            **ev,
            "category": attr.get("category", "Technical"),
            "reason":   attr.get("reason",   "Attribution unavailable."),
        })

    return result


# ── Public entry point ─────────────────────────────────────────────────────────

async def get_event_attribution(
    symbol: str,
    company_name: str = "",
    sector:       str = "",
    min_swing_pct: float = 0.15,
) -> dict:
    """
    Main entry point.
    Returns cached result (7-day TTL) or computes fresh.
    Response shape:
      {
        symbol: str,
        events: [ {date, price, move_pct, direction, category, reason} ],
        prices: [ {date, close} ],
      }
    """
    import yfinance as yf

    cache_key = symbol.upper()
    now = time.time()

    if cache_key in _CACHE:
        cached_at, data = _CACHE[cache_key]
        if now - cached_at < _CACHE_TTL:
            log.debug("event_attribution cache hit: %s", symbol)
            return data

    # ── Fetch weekly history (blocking — run in thread) ────────────────────────
    ticker_sym = symbol.upper()
    if not ticker_sym.endswith(".NS") and not ticker_sym.endswith(".BO"):
        ticker_sym += ".NS"

    def _fetch():
        t    = yf.Ticker(ticker_sym)
        hist = t.history(period="5y", interval="1wk")
        if hist.empty:
            return None, None
        closes = [float(c) for c in hist["Close"].tolist()]
        dates  = [d.strftime("%Y-%m-%d") for d in hist.index]
        return closes, dates

    import asyncio
    closes, dates = await asyncio.to_thread(_fetch)

    if closes is None:
        return {"symbol": symbol, "events": [], "prices": [], "error": "No price history"}

    prices = [{"date": d, "close": round(c, 2)} for d, c in zip(dates, closes)]

    # ── Detect swings ──────────────────────────────────────────────────────────
    events = _detect_swings(closes, dates, min_pct=min_swing_pct)

    if not events:
        result = {"symbol": symbol, "events": [], "prices": prices}
        _CACHE[cache_key] = (now, result)
        return result

    # ── LLM attribution ────────────────────────────────────────────────────────
    try:
        events_attributed = await _llm_attribute(
            symbol,
            company_name or symbol,
            sector or "Unknown",
            events,
        )
    except Exception as exc:
        log.error("event_attribution LLM error for %s: %s", symbol, exc)
        events_attributed = [
            {**ev, "category": "Technical", "reason": "LLM attribution unavailable."}
            for ev in events
        ]

    result = {
        "symbol": symbol,
        "events": events_attributed,
        "prices": prices,
    }

    _CACHE[cache_key] = (now, result)
    return result
