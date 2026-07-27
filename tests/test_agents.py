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
    "risk_management", "open_trades_control", "premium_discount",
    "bollinger_stoch", "supertrend_adx", "williams_r", "alligator", "fibonacci",
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


def _trending_frame(start: float, step: float, n: int = 120) -> pd.DataFrame:
    """DataFrame OHLCV con tendencia lineal (step>0 sube, step<0 baja)."""
    idx = pd.date_range("2024-01-01", periods=n, freq="15min")
    close = [start + step * i for i in range(n)]
    return pd.DataFrame(
        {"open": close, "high": [c + 1 for c in close], "low": [c - 1 for c in close],
         "close": close, "volume": [1000] * n},
        index=idx,
    )


def test_trend_mtf_uses_only_available_timeframes():
    """Solo considera los marcos presentes; los ausentes (D1/H4) no participan."""
    up = _trending_frame(2000.0, 0.5)
    md = MarketData("XAUUSD", {Timeframe.M15: up, Timeframe.H1: up}, price=2060.0,
                    regime=MarketRegime(atr=5.0))
    decision = AgentRegistry.create("trend_mtf", {}).run(md)
    assert decision.signal is SignalType.BUY
    # La explicación solo menciona los marcos realmente disponibles.
    assert "M15" in decision.explanation and "H1" in decision.explanation
    assert "D1" not in decision.explanation and "H4" not in decision.explanation


def test_trend_mtf_ignores_timeframes_without_weight():
    """Un marco sin peso en la escalera (M5) no cuenta para la tendencia."""
    up = _trending_frame(2000.0, 0.5)      # H1 sube
    down = _trending_frame(2100.0, -0.5)   # M5 baja, pero M5 no está en la escalera
    md = MarketData("XAUUSD", {Timeframe.M5: down, Timeframe.H1: up}, price=2060.0,
                    regime=MarketRegime(atr=5.0))
    decision = AgentRegistry.create("trend_mtf", {}).run(md)
    assert decision.signal is SignalType.BUY   # manda H1; M5 se ignora
    assert "M5" not in decision.explanation


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


def test_elliott_is_real_agent(market_data):
    # elliott ya es un agente real (no scaffold): devuelve una decisión válida.
    decision = AgentRegistry.create("elliott", {}).run(market_data)
    assert isinstance(decision, AgentDecision)
    assert decision.signal in (SignalType.BUY, SignalType.SELL, SignalType.WAIT)
    assert decision.metadata.get("planned") is None


def test_premium_discount_buys_in_discount():
    # Rango 90-110; precio a 92 (parte baja = discount) -> sesgo comprador.
    idx = pd.date_range("2024-01-01", periods=60, freq="5min")
    base = [90 + (i % 20) for i in range(60)]  # oscila 90..109
    df = pd.DataFrame(
        {"open": base, "high": [b + 1 for b in base], "low": [b - 1 for b in base],
         "close": base, "volume": [1000.0] * 60},
        index=idx, dtype=float,
    )
    md = MarketData("XAUUSD", {Timeframe.M5: df}, price=92.0,
                    regime=MarketRegime(atr=2.0))
    decision = AgentRegistry.create("premium_discount", {}).run(md)
    assert decision.signal is SignalType.BUY


def test_supertrend_adx_buys_on_strong_uptrend():
    # Tendencia alcista fuerte y sostenida -> SuperTrend alcista + ADX alto -> BUY.
    idx = pd.date_range("2024-01-01", periods=120, freq="1h")
    close = pd.Series([100 + i * 0.8 for i in range(120)], index=idx, dtype=float)
    df = pd.DataFrame(
        {"open": close.shift(1).fillna(close.iloc[0]), "high": close + 0.5,
         "low": close - 0.5, "close": close, "volume": [1000.0] * 120},
        index=idx,
    )
    md = MarketData("XAUUSD", {Timeframe.M5: df}, price=float(close.iloc[-1]),
                    regime=MarketRegime(atr=2.0))
    d = AgentRegistry.create("supertrend_adx", {}).run(md)
    assert d.signal is SignalType.BUY


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


def test_alligator_buys_on_open_uptrend():
    # Tendencia alcista sostenida -> lips>teeth>jaw y precio arriba -> BUY.
    idx = pd.date_range("2024-01-01", periods=80, freq="1h")
    close = pd.Series([100 + i * 1.0 for i in range(80)], index=idx, dtype=float)
    df = pd.DataFrame(
        {"open": close.shift(1).fillna(close.iloc[0]), "high": close + 0.5,
         "low": close - 0.5, "close": close, "volume": [1000.0] * 80},
        index=idx,
    )
    md = MarketData("XAUUSD", {Timeframe.M5: df}, price=float(close.iloc[-1]),
                    regime=MarketRegime(atr=2.0))
    d = AgentRegistry.create("alligator", {}).run(md)
    assert d.signal is SignalType.BUY
