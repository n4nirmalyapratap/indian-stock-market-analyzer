from typing import Optional


def calculate_ema(data: list[float], period: int) -> list[float]:
    if len(data) < period:
        return []
    k = 2.0 / (period + 1)
    ema = [sum(data[:period]) / period]
    for i in range(period, len(data)):
        ema.append(data[i] * k + ema[-1] * (1 - k))
    return ema


def calculate_sma(data: list[float], period: int) -> list[float]:
    sma = []
    for i in range(period - 1, len(data)):
        sma.append(sum(data[i - period + 1:i + 1]) / period)
    return sma


def calculate_rsi(data: list[float], period: int = 14) -> list[float]:
    if len(data) < period + 1:
        return []
    gains = []
    losses = []
    for i in range(1, len(data)):
        change = data[i] - data[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    rsi = []
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
        if al == 0:
            rsi.append(100.0)
        else:
            rsi.append(100 - 100 / (1 + ag / al))
    return rsi


def calculate_macd(data: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    ef = calculate_ema(data, fast)
    es = calculate_ema(data, slow)
    diff = slow - fast
    macd_line = [ef[i + diff] - v for i, v in enumerate(es)]
    signal_line = calculate_ema(macd_line, signal)
    histogram = [macd_line[i + signal - 1] - v for i, v in enumerate(signal_line)]
    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


def calculate_bollinger_bands(data: list[float], period: int = 20, sd: float = 2.0) -> dict:
    middle = calculate_sma(data, period)
    upper = []
    lower = []
    for idx, sma_val in enumerate(middle):
        segment = data[idx:idx + period]
        variance = sum((v - sma_val) ** 2 for v in segment) / period
        std = variance ** 0.5
        upper.append(sma_val + sd * std)
        lower.append(sma_val - sd * std)
    return {"upper": upper, "middle": middle, "lower": lower}


def calculate_atr(ohlcv: list[dict], period: int = 14) -> list[float]:
    if len(ohlcv) < 2:
        return []
    trs = []
    for i in range(1, len(ohlcv)):
        h = ohlcv[i]["high"]
        l = ohlcv[i]["low"]
        pc = ohlcv[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return calculate_sma(trs, period)


def calculate_vwap(ohlcv: list[dict]) -> list[float]:
    vwap = []
    cum_tp_vol = 0.0
    cum_vol = 0.0
    for d in ohlcv:
        tp = (d["high"] + d["low"] + d["close"]) / 3
        vol = d["volume"] or 0
        cum_tp_vol += tp * vol
        cum_vol += vol
        vwap.append(cum_tp_vol / cum_vol if cum_vol > 0 else tp)
    return vwap


def detect_sr(ohlcv: list[dict], lookback: int = 10) -> dict:
    highs = [d["high"] for d in ohlcv]
    lows = [d["low"] for d in ohlcv]
    supports = []
    resistances = []
    for i in range(lookback, len(ohlcv) - lookback):
        seg_h = highs[i - lookback:i + lookback + 1]
        seg_l = lows[i - lookback:i + lookback + 1]
        if highs[i] == max(seg_h):
            resistances.append(highs[i])
        if lows[i] == min(seg_l):
            supports.append(lows[i])
    return {
        "supports": sorted(set(supports)),
        "resistances": sorted(set(resistances)),
    }
