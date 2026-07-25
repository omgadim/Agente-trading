"""Tests de los agentes: contrato, robustez y coherencia direccional."""
from __future__ import annotations

import pandas as pd
import pytest

from trading_system.core import AgentDecision, AgentRegistry, MarketData, SignalType, Timeframe
from trading_system.core.market_data import MarketRegime

# Importar el paquete registra todos los agentes.
import trading_system.agents  # noqa: F401

REAL_AGENTS = [
    "trend_mtf", "momentum", "technical", "volatility", "volume",
    "market_structure", "support_resistance", "candlestick", "session",
    "risk_management", "open_trades_control",
]


@pytest.mark.parametrize("name", REAL_AGENTS)
def test_agent_returns_valid_decision(name, market_data):
    agent = AgentRegistry.create(name, {})
    decision = agent.run(market_data)
    assert isinstance(decision, AgentDecision)
    assert decision.agent_name == name
    assert 0.0 <= decision.confidence <= 100.0
    assert 0.0 <= decision.estimated_risk <= 100.0
    assert decision.signal in (SignalType.BUY, SignalType.SELL, SignalType.WAIT)


def test_trend_agent_bullish_on_uptrend(uptrend_feed):
    md = uptrend_feed.get_market_data("XAUUSD")
    decision = AgentRegistry.create("trend_mtf", {}).run(md)
    assert decision.signal is SignalType.BUY


def test_trend_agent_bearish_on_downtrend(downtrend_feed):
    md = downtrend_feed.get_market_data("XAUUSD")
    decision = AgentRegistry.create("trend_mtf", {}).run(md)
    assert decision.signal is SignalType.SELL


def test_agent_failure_is_isolated(market_data):
    """Un agente que lanza excepción devuelve WAIT en vez de tumbar el sistema."""
    agent = AgentRegistry.create("technical", {})

    def boom(_md):
        raise RuntimeError("fallo simulado")

    agent.analyze = boom  # type: ignore[assignment]
    decision = agent.run(market_data)
    assert decision.signal is SignalType.WAIT
    assert "Error interno" in decision.explanation


def test_disabled_agent_waits(market_data):
    agent = AgentRegistry.create("momentum", {"enabled": False})
    decision = agent.run(market_data)
    assert decision.signal is SignalType.WAIT


def test_scaffold_agent_is_planned(market_data):
    # news sigue siendo scaffold (Fase 5); machine_learning ya es real (Fase 4).
    decision = AgentRegistry.create("news", {}).run(market_data)
    assert decision.signal is SignalType.WAIT
    assert decision.metadata.get("planned") is True


def test_risk_agent_veto_on_extreme_volatility():
    """Con ATR% por encima del máximo, el agente de riesgo marca veto."""
    idx = pd.date_range("2024-01-01", periods=50, freq="5min")
    # Serie muy volátil (oscila mucho respecto al precio).
    close = pd.Series([2000 + (60 if i % 2 else -60) for i in range(50)], index=idx, dtype=float)
    df = pd.DataFrame({
        "open": close, "high": close + 40, "low": close - 40,
        "close": close, "volume": 1000.0,
    })
    md = MarketData("XAUUSD", {Timeframe.M5: df}, price=2000.0,
                    regime=MarketRegime(atr=80.0))
    decision = AgentRegistry.create("risk_management", {"max_atr_pct": 2.5}).run(md)
    assert decision.metadata.get("veto") is True
