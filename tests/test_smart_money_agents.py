"""Tests de los agentes Smart Money / Price Action (Fase 2)."""
from __future__ import annotations

import pandas as pd
import pytest

from trading_system.agents.smart_money_agents import HarmonicPatternAgent
from trading_system.core import AgentDecision, AgentRegistry, MarketData, SignalType, Timeframe
from trading_system.core.market_data import MarketRegime

import trading_system.agents  # noqa: F401  (registro)

SMART_MONEY_AGENTS = [
    "smart_money", "order_blocks", "fair_value_gap",
    "liquidity_sweep", "wyckoff", "harmonic",
]


@pytest.mark.parametrize("name", SMART_MONEY_AGENTS)
def test_agent_returns_valid_decision(name, market_data):
    decision = AgentRegistry.create(name, {}).run(market_data)
    assert isinstance(decision, AgentDecision)
    assert decision.agent_name == name
    assert 0.0 <= decision.confidence <= 100.0
    assert decision.signal in (SignalType.BUY, SignalType.SELL, SignalType.WAIT)


@pytest.mark.parametrize("name", SMART_MONEY_AGENTS)
def test_agent_handles_tiny_dataset(name):
    """Con muy pocos datos, el agente responde WAIT sin lanzar excepción."""
    idx = pd.date_range("2024-01-01", periods=5, freq="5min")
    df = pd.DataFrame(
        {"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 1000.0},
        index=idx,
    )
    md = MarketData("XAUUSD", {Timeframe.M5: df}, price=100.0, regime=MarketRegime(atr=1.0))
    decision = AgentRegistry.create(name, {}).run(md)
    assert decision.signal is SignalType.WAIT


def test_fvg_agent_buys_inside_bullish_gap():
    """Precio dentro de un FVG alcista reciente -> BUY."""
    rows = [(100.0, 100.5, 99.5, 100.0)] * 20
    rows += [
        (100.0, 100.5, 99.5, 100.0),
        (100.0, 106.0, 100.0, 105.5),
        (105.0, 106.0, 104.0, 105.5),
    ]
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="5min")
    df = pd.DataFrame(
        {
            "open": [r[0] for r in rows], "high": [r[1] for r in rows],
            "low": [r[2] for r in rows], "close": [r[3] for r in rows],
            "volume": [1000.0] * len(rows),
        },
        index=idx, dtype=float,
    )
    # Precio 102 cae dentro del hueco [100.5, 104].
    md = MarketData("XAUUSD", {Timeframe.M5: df}, price=102.0, regime=MarketRegime(atr=2.0))
    decision = AgentRegistry.create("fair_value_gap", {"min_atr_frac": 0.0}).run(md)
    assert decision.signal is SignalType.BUY


# ---- Reconocedor de patrones armónicos (unidad) -----------------------------
def test_harmonic_matches_gartley_ratios():
    match = HarmonicPatternAgent._match_pattern(b_ret=0.618, d_ret=0.786)
    assert match is not None and match[0] == "Gartley"


def test_harmonic_matches_bat_ratios():
    match = HarmonicPatternAgent._match_pattern(b_ret=0.45, d_ret=0.886)
    assert match is not None and match[0] == "Bat"


def test_harmonic_rejects_unstructured_ratios():
    assert HarmonicPatternAgent._match_pattern(b_ret=0.10, d_ret=0.30) is None
