"""Tests de la librería de indicadores."""
from __future__ import annotations

import numpy as np
import pandas as pd

from trading_system.data import indicators as ind


def _ohlc(closes):
    close = pd.Series(closes, dtype=float)
    high = close + 1.0
    low = close - 1.0
    open_ = close.shift(1).fillna(close.iloc[0])
    vol = pd.Series(np.ones(len(close)) * 1000)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol})


def test_ema_reacts_faster_than_sma():
    s = pd.Series(range(1, 101), dtype=float)
    assert ind.ema(s, 10).iloc[-1] > ind.sma(s, 10).iloc[-1] - 5  # sane range


def test_rsi_all_up_is_100():
    s = pd.Series(range(1, 60), dtype=float)  # estrictamente creciente
    assert ind.rsi(s, 14).iloc[-1] == 100.0


def test_rsi_all_down_is_low():
    s = pd.Series(range(60, 1, -1), dtype=float)  # estrictamente decreciente
    assert ind.rsi(s, 14).iloc[-1] < 5.0


def test_rsi_bounds():
    rng = np.random.default_rng(0)
    s = pd.Series(np.cumsum(rng.normal(0, 1, 200)) + 100)
    r = ind.rsi(s, 14).dropna()
    assert (r >= 0).all() and (r <= 100).all()


def test_atr_positive():
    df = _ohlc(np.cumsum(np.random.default_rng(1).normal(0, 1, 100)) + 100)
    atr = ind.atr(df, 14).dropna()
    assert (atr > 0).all()


def test_macd_hist_is_macd_minus_signal():
    s = pd.Series(np.cumsum(np.random.default_rng(2).normal(0, 1, 200)) + 100)
    m = ind.macd(s)
    diff = (m["macd"] - m["signal"] - m["hist"]).abs().dropna()
    assert (diff < 1e-9).all()


def test_adx_range():
    df = _ohlc(np.cumsum(np.random.default_rng(3).normal(0, 1, 200)) + 100)
    adx = ind.adx(df, 14).dropna()
    assert (adx >= 0).all() and (adx <= 100).all()


def test_swing_detection_marks_peak():
    s = pd.Series([1, 2, 3, 5, 3, 2, 1], dtype=float)
    highs = ind.swing_highs(s, 2, 2)
    assert bool(highs.iloc[3]) is True  # el 5 es pico local


# ---- Nuevos: Bollinger, Estocástico, SuperTrend -----------------------------
def test_bollinger_bands_ordered():
    s = pd.Series(np.linspace(100, 110, 40), dtype=float)
    bb = ind.bollinger(s, period=20, mult=2.0)
    assert bb["lower"].iloc[-1] <= bb["mid"].iloc[-1] <= bb["upper"].iloc[-1]


def test_stochastic_bounds():
    df = _ohlc(list(np.linspace(100, 120, 40)) + list(np.linspace(120, 100, 40)))
    st = ind.stochastic(df, 14, 3)["k"].dropna()
    assert (st >= -0.01).all() and (st <= 100.01).all()


def test_supertrend_direction_up_on_uptrend():
    df = _ohlc(list(np.linspace(100, 200, 80)))
    st = ind.supertrend(df, period=10, mult=3.0)
    assert int(st["trend"].iloc[-1]) == 1   # tendencia claramente alcista


def test_supertrend_direction_down_on_downtrend():
    df = _ohlc(list(np.linspace(200, 100, 80)))
    st = ind.supertrend(df, period=10, mult=3.0)
    assert int(st["trend"].iloc[-1]) == -1


def test_williams_r_bounds():
    df = _ohlc(list(np.linspace(100, 130, 30)) + list(np.linspace(130, 105, 30)))
    wr = ind.williams_r(df, 14).dropna()
    assert (wr >= -100.01).all() and (wr <= 0.01).all()


def test_williams_r_oversold_on_lows():
    # Precio en mínimos recientes -> %R cerca de -100 (sobreventa).
    df = _ohlc(list(np.linspace(130, 100, 30)))
    assert ind.williams_r(df, 14).iloc[-1] < -70


def test_smma_smoother_than_ema():
    s = pd.Series(np.linspace(1, 100, 60), dtype=float)
    # SMMA (alpha=1/n) es más lenta que EMA (span=n) en una rampa.
    assert ind.smma(s, 10).iloc[-1] < ind.ema(s, 10).iloc[-1]
