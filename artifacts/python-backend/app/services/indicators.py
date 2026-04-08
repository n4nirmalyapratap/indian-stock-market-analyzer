"""
Technical indicator calculations using the `ta` library (pandas-based).
Falls back to manual numpy implementations if needed.
"""
import pandas as pd
import ta
from ta.trend import EMAIndicator, SMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange


def _closes_series(data: list[float]) -> pd.Series:
    return pd.Series(data, dtype=float)


def _ohlcv_df(ohlcv: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(ohlcv)


def calculate_ema(data: list[float], period: int) -> list[float]:
    if len(data) < period:
        return []
    s = _closes_series(data)
    ema_ind = EMAIndicator(close=s, window=period, fillna=False)
    result = ema_ind.ema_indicator().dropna().tolist()
    return result


def calculate_sma(data: list[float], period: int) -> list[float]:
    if len(data) < period:
        return []
    s = _closes_series(data)
    sma_ind = SMAIndicator(close=s, window=period, fillna=False)
    result = sma_ind.sma_indicator().dropna().tolist()
    return result


def calculate_rsi(data: list[float], period: int = 14) -> list[float]:
    if len(data) < period + 1:
        return []
    s = _closes_series(data)
    rsi_ind = RSIIndicator(close=s, window=period, fillna=False)
    result = rsi_ind.rsi().dropna().tolist()
    return result


def calculate_macd(data: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    s = _closes_series(data)
    macd_ind = MACD(close=s, window_slow=slow, window_fast=fast, window_sign=signal, fillna=False)
    macd_line   = macd_ind.macd().dropna().tolist()
    signal_line = macd_ind.macd_signal().dropna().tolist()
    histogram   = macd_ind.macd_diff().dropna().tolist()
    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


def calculate_bollinger_bands(data: list[float], period: int = 20, sd: float = 2.0) -> dict:
    s = _closes_series(data)
    bb = BollingerBands(close=s, window=period, window_dev=sd, fillna=False)
    upper  = bb.bollinger_hband().dropna().tolist()
    middle = bb.bollinger_mavg().dropna().tolist()
    lower  = bb.bollinger_lband().dropna().tolist()
    return {"upper": upper, "middle": middle, "lower": lower}


def calculate_atr(ohlcv: list[dict], period: int = 14) -> list[float]:
    if len(ohlcv) < period + 1:
        return []
    df = _ohlcv_df(ohlcv)
    atr_ind = AverageTrueRange(
        high=df["high"].astype(float),
        low=df["low"].astype(float),
        close=df["close"].astype(float),
        window=period,
        fillna=False,
    )
    return atr_ind.average_true_range().dropna().tolist()


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
