"""
Technical indicator calculations using pandas_ta.
"""
import sys
import os
# Ensure the pandas_ta shim (which wraps the `ta` library) is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pandas as pd
import pandas_ta as pta


def _s(data: list[float]) -> pd.Series:
    return pd.Series(data, dtype=float)


def _ohlcv_df(ohlcv: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(ohlcv)


def calculate_ema(data: list[float], period: int) -> list[float]:
    if len(data) < period:
        return []
    result = pta.ema(close=_s(data), length=period)
    return result.dropna().tolist()


def calculate_sma(data: list[float], period: int) -> list[float]:
    if len(data) < period:
        return []
    result = pta.sma(close=_s(data), length=period)
    return result.dropna().tolist()


def calculate_rsi(data: list[float], period: int = 14) -> list[float]:
    if len(data) < period + 1:
        return []
    result = pta.rsi(close=_s(data), length=period)
    return result.dropna().tolist()


def calculate_macd(data: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    df = pta.macd(close=_s(data), fast=fast, slow=slow, signal=signal)
    prefix = f"MACD_{fast}_{slow}_{signal}"
    macd_line   = df[prefix].dropna().tolist()
    signal_line = df[f"MACDs_{fast}_{slow}_{signal}"].dropna().tolist()
    histogram   = df[f"MACDh_{fast}_{slow}_{signal}"].dropna().tolist()
    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


def calculate_bollinger_bands(data: list[float], period: int = 20, sd: float = 2.0) -> dict:
    df = pta.bbands(close=_s(data), length=period, std=sd)
    upper  = df[f"BBU_{period}_{sd}"].dropna().tolist()
    middle = df[f"BBM_{period}_{sd}"].dropna().tolist()
    lower  = df[f"BBL_{period}_{sd}"].dropna().tolist()
    return {"upper": upper, "middle": middle, "lower": lower}


def calculate_atr(ohlcv: list[dict], period: int = 14) -> list[float]:
    if len(ohlcv) < period + 1:
        return []
    df = _ohlcv_df(ohlcv)
    result = pta.atr(
        high=df["high"].astype(float),
        low=df["low"].astype(float),
        close=df["close"].astype(float),
        length=period,
    )
    return result.dropna().tolist()


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
    supports: list[float] = []
    resistances: list[float] = []
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
