import random
import string
from datetime import datetime
from typing import Optional
from .yahoo_service import YahooService
from .nse_service import NseService
from .indicators import (
    calculate_ema, calculate_sma, calculate_rsi,
    calculate_macd, calculate_bollinger_bands, calculate_atr,
)
from ..lib.universe import build_universe

VALID_OPERATORS = {"gt", "gte", "lt", "lte", "eq", "crosses_above", "crosses_below"}


def _cid() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=7))


DEFAULT_SCANNERS_DEF = [
    {
        "name": "EMA Golden Cross (20/50)",
        "description": "EMA20 just crossed above EMA50 — classic medium-term buy signal",
        "universe": ["NIFTY100", "MIDCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "EMA", "period": 20}, "operator": "crosses_above", "right": {"type": "indicator", "indicator": "EMA", "period": 50}},
            {"left": {"type": "indicator", "indicator": "RSI", "period": 14}, "operator": "gt",            "right": {"type": "number", "value": 45}},
        ],
    },
    {
        "name": "RSI Oversold + EMA50 Support",
        "description": "RSI below 35 while price is above EMA50 — dip buy setup",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "RSI", "period": 14}, "operator": "lt",  "right": {"type": "number", "value": 35}},
            {"left": {"type": "indicator", "indicator": "CLOSE"},             "operator": "gt",  "right": {"type": "indicator", "indicator": "EMA", "period": 50}},
        ],
    },
    {
        "name": "Momentum Breakout",
        "description": "Price above EMA200, RSI 55-70, volume spike ≥150%",
        "universe": ["NIFTY100"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "CLOSE"},             "operator": "gt",  "right": {"type": "indicator", "indicator": "EMA", "period": 200}},
            {"left": {"type": "indicator", "indicator": "RSI", "period": 14}, "operator": "gte", "right": {"type": "number", "value": 55}},
            {"left": {"type": "indicator", "indicator": "RSI", "period": 14}, "operator": "lte", "right": {"type": "number", "value": 72}},
            {"left": {"type": "indicator", "indicator": "VOLUME_RATIO"},      "operator": "gte", "right": {"type": "number", "value": 150}},
        ],
    },
    {
        "name": "Near 52-Week High (within 5%)",
        "description": "Price within 5% of 52-week high — momentum continuation",
        "universe": ["NIFTY100", "MIDCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "PCT_52W_HIGH"}, "operator": "gte", "right": {"type": "number", "value": -5}},
            {"left": {"type": "indicator", "indicator": "CLOSE"},        "operator": "gt",  "right": {"type": "indicator", "indicator": "EMA", "period": 50}},
        ],
    },
    {
        "name": "Bollinger Band Lower Bounce",
        "description": "Price near/below BB lower, RSI oversold — mean reversion buy",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "CLOSE"},                "operator": "lte", "right": {"type": "indicator", "indicator": "BB_LOWER", "period": 20}},
            {"left": {"type": "indicator", "indicator": "RSI", "period": 14},    "operator": "lt",  "right": {"type": "number", "value": 40}},
        ],
    },
    {
        "name": "MACD Bullish Crossover",
        "description": "MACD line just crossed above signal line — fresh buy signal",
        "universe": ["NIFTY100", "MIDCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "MACD"}, "operator": "crosses_above", "right": {"type": "indicator", "indicator": "MACD_SIGNAL"}},
        ],
    },
    {
        "name": "Superb Momentum (All EMAs aligned)",
        "description": "Price > EMA9 > EMA20 > EMA50 > EMA200 — textbook bull trend",
        "universe": ["NIFTY100"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "CLOSE"},           "operator": "gt", "right": {"type": "indicator", "indicator": "EMA", "period": 9}},
            {"left": {"type": "indicator", "indicator": "EMA", "period": 9}, "operator": "gt", "right": {"type": "indicator", "indicator": "EMA", "period": 20}},
            {"left": {"type": "indicator", "indicator": "EMA", "period": 20},"operator": "gt", "right": {"type": "indicator", "indicator": "EMA", "period": 50}},
            {"left": {"type": "indicator", "indicator": "EMA", "period": 50},"operator": "gt", "right": {"type": "indicator", "indicator": "EMA", "period": 200}},
        ],
    },
    {
        "name": "Volume Spike Breakout",
        "description": "Volume ≥ 300% of 20-day average on a green candle",
        "universe": ["NIFTY100", "MIDCAP", "SMALLCAP"],
        "logic": "AND",
        "conditions": [
            {"left": {"type": "indicator", "indicator": "VOLUME_RATIO"}, "operator": "gte", "right": {"type": "number", "value": 300}},
            {"left": {"type": "indicator", "indicator": "CHANGE_PCT"},   "operator": "gt",  "right": {"type": "number", "value": 0}},
        ],
    },
]


def _compute_value(ohlcv: list[dict], side: dict, shift: int = 0) -> Optional[float]:
    if side.get("type") == "number":
        return side.get("value")
    data = ohlcv[:len(ohlcv) - shift] if shift > 0 else ohlcv
    if len(data) < 2:
        return None
    closes = [d["close"] for d in data]
    n = len(data)

    ind = side.get("indicator", "")
    period = side.get("period")

    if ind == "CLOSE":     return closes[-1]
    if ind == "OPEN":      return data[-1]["open"]
    if ind == "HIGH":      return data[-1]["high"]
    if ind == "LOW":       return data[-1]["low"]
    if ind == "PREV_CLOSE": return closes[-2] if n >= 2 else None
    if ind == "CHANGE_PCT": return ((closes[-1] - closes[-2]) / closes[-2]) * 100 if closes[-2] else None
    if ind == "VOLUME":    return data[-1]["volume"]
    if ind == "AVG_VOLUME":
        p = period or 20
        sl = data[-p:]
        return sum(d["volume"] for d in sl) / len(sl) if sl else None
    if ind == "VOLUME_RATIO":
        avg = sum(d["volume"] for d in data[-20:]) / min(20, n)
        return (data[-1]["volume"] / avg * 100) if avg else None
    if ind == "EMA":
        arr = calculate_ema(closes, period or 20)
        return arr[-1] if arr else None
    if ind == "SMA":
        arr = calculate_sma(closes, period or 20)
        return arr[-1] if arr else None
    if ind == "RSI":
        arr = calculate_rsi(closes, period or 14)
        return arr[-1] if arr else None
    if ind == "MACD":
        m = calculate_macd(closes)
        return m["macd"][-1] if m["macd"] else None
    if ind == "MACD_SIGNAL":
        m = calculate_macd(closes)
        return m["signal"][-1] if m["signal"] else None
    if ind == "MACD_HIST":
        m = calculate_macd(closes)
        return m["histogram"][-1] if m["histogram"] else None
    if ind == "BB_UPPER":
        bb = calculate_bollinger_bands(closes, period or 20)
        return bb["upper"][-1] if bb["upper"] else None
    if ind == "BB_MID":
        bb = calculate_bollinger_bands(closes, period or 20)
        return bb["middle"][-1] if bb["middle"] else None
    if ind == "BB_LOWER":
        bb = calculate_bollinger_bands(closes, period or 20)
        return bb["lower"][-1] if bb["lower"] else None
    if ind == "ATR":
        arr = calculate_atr(data, period or 14)
        return arr[-1] if arr else None
    if ind == "HIGH_52W":  return max(closes[-252:]) if len(closes) >= 1 else None
    if ind == "LOW_52W":   return min(closes[-252:]) if len(closes) >= 1 else None
    if ind == "PCT_52W_HIGH":
        h = max(closes[-252:])
        return ((closes[-1] - h) / h) * 100 if h else None
    if ind == "PCT_52W_LOW":
        l = min(closes[-252:])
        return ((closes[-1] - l) / l) * 100 if l else None
    return None


def _compare(lv: float, op: str, rv: float) -> bool:
    if op == "gt":  return lv > rv
    if op == "gte": return lv >= rv
    if op == "lt":  return lv < rv
    if op == "lte": return lv <= rv
    if op == "eq":  return abs(lv - rv) / (abs(rv) or 1) < 0.001
    return False


def _side_label(s: dict) -> str:
    if s.get("type") == "number":
        return str(s.get("value"))
    p = f"({s['period']})" if s.get("period") else ""
    return f"{s.get('indicator', '')}{p}"


def _eval_condition(ohlcv: list[dict], cond: dict) -> dict:
    lv = _compute_value(ohlcv, cond["left"])
    rv = _compute_value(ohlcv, cond["right"])
    if lv is None or rv is None:
        return {"met": False, "desc": "Insufficient data"}

    ll, rl = _side_label(cond["left"]), _side_label(cond["right"])
    fmt = lambda v: f"{v:.4f}" if abs(v) < 1 else f"{v:.2f}"

    op = cond["operator"]
    if op in ("crosses_above", "crosses_below"):
        lv_prev = _compute_value(ohlcv, cond["left"],  1)
        rv_prev = _compute_value(ohlcv, cond["right"], 1)
        if lv_prev is None or rv_prev is None:
            return {"met": False, "desc": "Insufficient data for crossover"}
        met = (lv_prev <= rv_prev and lv > rv) if op == "crosses_above" else (lv_prev >= rv_prev and lv < rv)
        direction = "crossed above" if op == "crosses_above" else "crossed below"
        return {"met": met, "desc": f"{ll} {direction} {rl} ({fmt(lv)} vs {fmt(rv)})"}

    op_symbols = {"gt": ">", "gte": "≥", "lt": "<", "lte": "≤", "eq": "="}
    met = _compare(lv, op, rv)
    return {"met": met, "desc": f"{ll} {op_symbols.get(op, op)} {rl} ({fmt(lv)} vs {fmt(rv)})"}


_scanners: dict[str, dict] = {}
_id_counter = [1]


def _init_defaults():
    if _scanners:
        return
    for d in DEFAULT_SCANNERS_DEF:
        sid = f"scanner-{_id_counter[0]}"
        _id_counter[0] += 1
        _scanners[sid] = {
            **d,
            "id": sid,
            "conditions": [{**c, "id": c.get("id") or _cid()} for c in d["conditions"]],
            "createdAt": datetime.utcnow().isoformat() + "Z",
            "updatedAt": datetime.utcnow().isoformat() + "Z",
        }


_init_defaults()


class ScannersService:
    def __init__(self, yahoo: YahooService, nse: NseService):
        self.yahoo = yahoo
        self.nse = nse

    def get_all_scanners(self) -> list[dict]:
        return sorted(_scanners.values(), key=lambda s: s["createdAt"], reverse=True)

    def get_scanner_by_id(self, sid: str) -> Optional[dict]:
        return _scanners.get(sid)

    def create_scanner(self, data: dict) -> dict:
        sid = f"scanner-{_id_counter[0]}"
        _id_counter[0] += 1
        scanner = {
            "id": sid,
            "name": data.get("name") or "Untitled Scanner",
            "description": data.get("description") or "",
            "universe": data.get("universe") or ["NIFTY100"],
            "logic": data.get("logic") or "AND",
            "conditions": [{**c, "id": c.get("id") or _cid()} for c in (data.get("conditions") or [])],
            "createdAt": datetime.utcnow().isoformat() + "Z",
            "updatedAt": datetime.utcnow().isoformat() + "Z",
        }
        _scanners[sid] = scanner
        return scanner

    def update_scanner(self, sid: str, data: dict) -> Optional[dict]:
        existing = _scanners.get(sid)
        if not existing:
            return None
        updated = {
            **existing,
            **data,
            "id": sid,
            "conditions": [{**c, "id": c.get("id") or _cid()} for c in (data.get("conditions") or existing["conditions"])],
            "updatedAt": datetime.utcnow().isoformat() + "Z",
        }
        _scanners[sid] = updated
        return updated

    def delete_scanner(self, sid: str) -> bool:
        if sid in _scanners:
            del _scanners[sid]
            return True
        return False

    async def run_scanner(self, sid: str) -> dict:
        scanner = _scanners.get(sid)
        if not scanner:
            return {"error": "Scanner not found"}

        symbols = build_universe(scanner["universe"])
        results = []

        for sym in symbols:
            try:
                h = await self.yahoo.get_historical_data(sym, 90)
                if len(h) < 30:
                    continue
                closes = [d["close"] for d in h if d.get("close")]
                lc = closes[-1]
                pc = closes[-2]
                change = lc - pc
                p_change = (change / pc) * 100 if pc else 0

                cond_results = [_eval_condition(h, c) for c in scanner["conditions"]]
                met_count = sum(1 for r in cond_results if r["met"])
                all_met = (
                    met_count == len(scanner["conditions"])
                    if scanner["logic"] == "AND"
                    else met_count > 0
                )

                if all_met:
                    results.append({
                        "symbol": sym,
                        "lastPrice": lc,
                        "change": round(change, 2),
                        "pChange": round(p_change, 2),
                        "volume": h[-1].get("volume"),
                        "matchedConditions": [r["desc"] for r in cond_results if r["met"]],
                        "failedConditions":  [r["desc"] for r in cond_results if not r["met"]],
                        "conditionsMatched": met_count,
                        "totalConditions": len(scanner["conditions"]),
                        "score": round(met_count / len(scanner["conditions"]) * 100) if scanner["conditions"] else 0,
                    })
                import asyncio
                await asyncio.sleep(0.35)
            except Exception:
                pass

        results.sort(key=lambda r: r["score"], reverse=True)
        _scanners[sid] = {
            **scanner,
            "lastRunAt": datetime.utcnow().isoformat() + "Z",
            "lastResultCount": len(results),
        }

        return {
            "scannerId": sid,
            "scannerName": scanner["name"],
            "logic": scanner["logic"],
            "runAt": datetime.utcnow().isoformat() + "Z",
            "totalScanned": len(symbols),
            "totalMatched": len(results),
            "results": results,
        }

    async def run_adhoc(self, data: dict) -> dict:
        scanner = self.create_scanner(data)
        result = await self.run_scanner(scanner["id"])
        self.delete_scanner(scanner["id"])
        return result
