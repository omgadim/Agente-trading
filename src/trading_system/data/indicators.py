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


def smma(series: pd.Series, period: int) -> pd.Series:
    """Smoothed Moving Average (suavizado de Wilder). Base del Alligator."""
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def williams_r(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Williams %R (Larry Williams): oscilador en [-100, 0]."""
    hh = df["high"].rolling(window=period, min_periods=period).max()
    ll = df["low"].rolling(window=period, min_periods=period).min()
    rng = (hh - ll).replace(0.0, np.nan)
    return -100.0 * (hh - df["close"]) / rng


def bollinger(series: pd.Series, period: int = 20, mult: float = 2.0) -> pd.DataFrame:
    """Bandas de Bollinger: media móvil ± `mult` desviaciones estándar."""
    mid = sma(series, period)
    sd = series.rolling(window=period, min_periods=period).std(ddof=0)
    return pd.DataFrame({"mid": mid, "upper": mid + mult * sd, "lower": mid - mult * sd})


def stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> pd.DataFrame:
    """Oscilador estocástico %K (rápido) y %D (media de %K)."""
    low_min = df["low"].rolling(window=k_period, min_periods=k_period).min()
    high_max = df["high"].rolling(window=k_period, min_periods=k_period).max()
    rng = (high_max - low_min).replace(0.0, np.nan)
    k = 100.0 * (df["close"] - low_min) / rng
    d = k.rolling(window=d_period, min_periods=d_period).mean()
    return pd.DataFrame({"k": k, "d": d})


def supertrend(df: pd.DataFrame, period: int = 10, mult: float = 3.0) -> pd.DataFrame:
    """SuperTrend (ATR): dirección de tendencia (+1 alcista / -1 bajista) y nivel.

    Devuelve columnas `trend` (1/-1) y `level` (la línea del SuperTrend).
    """
    atr_ = atr(df, period).to_numpy()
    hl2 = ((df["high"] + df["low"]) / 2.0).to_numpy()
    close = df["close"].to_numpy()
    n = len(df)
    upper = hl2 + mult * atr_
    lower = hl2 - mult * atr_
    f_upper = np.full(n, np.nan)
    f_lower = np.full(n, np.nan)
    trend = np.ones(n, dtype=int)
    for i in range(1, n):
        f_upper[i] = (upper[i] if (np.isnan(f_upper[i - 1]) or upper[i] < f_upper[i - 1]
                                   or close[i - 1] > f_upper[i - 1]) else f_upper[i - 1])
        f_lower[i] = (lower[i] if (np.isnan(f_lower[i - 1]) or lower[i] > f_lower[i - 1]
                                   or close[i - 1] < f_lower[i - 1]) else f_lower[i - 1])
        if close[i] > f_upper[i - 1]:
            trend[i] = 1
        elif close[i] < f_lower[i - 1]:
            trend[i] = -1
        else:
            trend[i] = trend[i - 1]
    level = np.where(trend == 1, f_lower, f_upper)
    return pd.DataFrame({"trend": trend, "level": level}, index=df.index)


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
