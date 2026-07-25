"""Indicadores técnicos vectorizados (pandas/numpy).

Implementaciones autónomas para no depender de librerías nativas (TA-Lib) que
complican el despliegue. Cada función recibe Series/DataFrame y devuelve Series.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    """Media móvil exponencial."""
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    """Media móvil simple."""
    return series.rolling(window=period, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (método de Wilder)."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    # Si avg_loss es 0 (solo subidas), RSI = 100.
    out = out.where(avg_loss != 0.0, 100.0)
    return out


def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """MACD, línea de señal e histograma."""
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": hist})


def true_range(df: pd.DataFrame) -> pd.Series:
    """True Range a partir de OHLC."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (suavizado de Wilder)."""
    tr = true_range(df)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index (fuerza de tendencia, 0-100)."""
    high, low = df["high"], df["low"]
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    tr = true_range(df)
    atr_ = tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    atr_safe = atr_.replace(0.0, np.nan)

    plus_di = 100.0 * plus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr_safe
    minus_di = 100.0 * minus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr_safe

    di_sum = (plus_di + minus_di).replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum
    return dx.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def roc(series: pd.Series, period: int = 10) -> pd.Series:
    """Rate of Change en porcentaje."""
    return series.pct_change(periods=period) * 100.0


def swing_highs(series: pd.Series, left: int = 2, right: int = 2) -> pd.Series:
    """Marca pivotes máximos locales (fractal simple). Devuelve bool Series."""
    highs = pd.Series(False, index=series.index)
    n = len(series)
    values = series.to_numpy()
    for i in range(left, n - right):
        window = values[i - left : i + right + 1]
        if values[i] == window.max() and (window.argmax() == left):
            highs.iloc[i] = True
    return highs


def swing_lows(series: pd.Series, left: int = 2, right: int = 2) -> pd.Series:
    """Marca pivotes mínimos locales (fractal simple). Devuelve bool Series."""
    lows = pd.Series(False, index=series.index)
    n = len(series)
    values = series.to_numpy()
    for i in range(left, n - right):
        window = values[i - left : i + right + 1]
        if values[i] == window.min() and (window.argmin() == left):
            lows.iloc[i] = True
    return lows
