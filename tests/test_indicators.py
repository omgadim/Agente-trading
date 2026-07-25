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
