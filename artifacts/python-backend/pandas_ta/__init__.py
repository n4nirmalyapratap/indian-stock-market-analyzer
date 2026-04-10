"""
pandas_ta compatibility shim — wraps the `ta` (Technical Analysis) library.
Provides the same function signatures used in this project.
"""
import pandas as pd
from ta.trend import EMAIndicator, SMAIndicator, MACD as _MACD
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange

__version__ = "0.3.14b0"


def ema(close: pd.Series, length: int = 20, **kwargs) -> pd.Series:
    return EMAIndicator(close=close.astype(float), window=length, fillna=False).ema_indicator()


def sma(close: pd.Series, length: int = 20, **kwargs) -> pd.Series:
    return SMAIndicator(close=close.astype(float), window=length, fillna=False).sma_indicator()


def rsi(close: pd.Series, length: int = 14, **kwargs) -> pd.Series:
    return RSIIndicator(close=close.astype(float), window=length, fillna=False).rsi()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9, **kwargs) -> pd.DataFrame:
    ind = _MACD(
        close=close.astype(float),
        window_fast=fast,
        window_slow=slow,
        window_sign=signal,
        fillna=False,
    )
    prefix = f"MACD_{fast}_{slow}_{signal}"
    return pd.DataFrame({
        f"MACD_{fast}_{slow}_{signal}":      ind.macd(),
        f"MACDs_{fast}_{slow}_{signal}":     ind.macd_signal(),
        f"MACDh_{fast}_{slow}_{signal}":     ind.macd_diff(),
    })


def bbands(close: pd.Series, length: int = 20, std: float = 2.0, **kwargs) -> pd.DataFrame:
    bb = BollingerBands(close=close.astype(float), window=length, window_dev=std, fillna=False)
    prefix = f"BBL_{length}_{std}"
    return pd.DataFrame({
        f"BBL_{length}_{std}":  bb.bollinger_lband(),
        f"BBM_{length}_{std}":  bb.bollinger_mavg(),
        f"BBU_{length}_{std}":  bb.bollinger_hband(),
        f"BBB_{length}_{std}":  bb.bollinger_wband(),
        f"BBP_{length}_{std}":  bb.bollinger_pband(),
    })


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14, **kwargs) -> pd.Series:
    return AverageTrueRange(
        high=high.astype(float),
        low=low.astype(float),
        close=close.astype(float),
        window=length,
        fillna=False,
    ).average_true_range()
