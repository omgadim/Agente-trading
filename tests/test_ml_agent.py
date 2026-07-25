"""Tests del MachineLearningAgent."""
from __future__ import annotations

import pandas as pd
import pytest

from trading_system.core import AgentDecision, AgentRegistry, MarketData, SignalType, Timeframe
from trading_system.core.market_data import MarketRegime
from trading_system.data import SimulatedDataFeed

import trading_system.agents  # noqa: F401  (registro)


def test_ml_agent_is_registered_real():
    d = AgentRegistry.create("machine_learning", {"min_train": 100}).run(
        SimulatedDataFeed(base_price=2000, drift=0.15, volatility=0.8,
                          bars=700, seed=1).get_market_data("XAUUSD")
    )
    assert isinstance(d, AgentDecision)
    assert d.metadata.get("planned") is None  # ya no es scaffold
    assert d.signal in (SignalType.BUY, SignalType.SELL, SignalType.WAIT)


def test_ml_agent_waits_on_insufficient_data():
    idx = pd.date_range("2024-01-01", periods=40, freq="5min")
    df = pd.DataFrame(
        {"open": 2000.0, "high": 2001.0, "low": 1999.0, "close": 2000.0, "volume": 1000.0},
        index=idx,
    )
    md = MarketData("XAUUSD", {Timeframe.M5: df}, price=2000.0, regime=MarketRegime(atr=1.0))
    d = AgentRegistry.create("machine_learning", {"min_train": 150}).run(md)
    assert d.signal is SignalType.WAIT


def test_ml_agent_deterministic():
    md = SimulatedDataFeed(base_price=2000, drift=0.2, volatility=0.7,
                           bars=700, seed=5).get_market_data("XAUUSD")
    a1 = AgentRegistry.create("machine_learning", {"min_train": 100}).run(md)
    a2 = AgentRegistry.create("machine_learning", {"min_train": 100}).run(md)
    assert a1.signal == a2.signal
    assert abs(a1.confidence - a2.confidence) < 1e-6


def test_ml_agent_provides_sl_tp_when_actionable():
    md = SimulatedDataFeed(base_price=2000, drift=0.3, volatility=0.6,
                           bars=800, seed=7).get_market_data("XAUUSD")
    d = AgentRegistry.create("machine_learning", {"min_train": 100, "margin": 0.02}).run(md)
    if d.signal in (SignalType.BUY, SignalType.SELL):
        assert d.stop_loss is not None and d.take_profit is not None
        assert "prob_up" in d.metadata
