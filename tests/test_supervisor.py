"""Tests del Supervisor y las estrategias de ponderación."""
from __future__ import annotations

import pandas as pd

from trading_system.core import BaseAgent, MarketData, SignalType, Timeframe
from trading_system.core.market_data import MarketRegime
from trading_system.risk import RiskManager
from trading_system.supervisor import AdaptiveWeighting, StaticWeighting, Supervisor


class _FixedAgent(BaseAgent):
    """Agente de prueba que siempre devuelve una señal fija."""

    def __init__(self, name, signal, confidence=80.0, sl=1990.0, tp=2020.0, **cfg):
        super().__init__(name, cfg)
        self._signal = signal
        self._confidence = confidence
        self._sl = sl
        self._tp = tp

    def analyze(self, md):
        return self._decision(
            self._signal, self._confidence, "fijo",
            estimated_risk=30.0, stop_loss=self._sl, take_profit=self._tp,
        )


def _md():
    idx = pd.date_range("2024-01-01", periods=60, freq="5min")
    close = pd.Series(range(2000, 2060), index=idx, dtype=float)
    df = pd.DataFrame({
        "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": 1000.0,
    })
    return MarketData("XAUUSD", {Timeframe.M5: df}, price=2000.0,
                      regime=MarketRegime(atr=5.0))


def test_supervisor_buys_on_consensus():
    agents = [_FixedAgent(f"a{i}", SignalType.BUY) for i in range(3)]
    sup = Supervisor(agents, weighting=StaticWeighting({}), risk_manager=RiskManager())
    decision = sup.decide(_md())
    assert decision.signal is SignalType.BUY
    assert decision.confidence > 0
    assert decision.position_size and decision.position_size > 0


def test_supervisor_waits_on_conflict():
    agents = [
        _FixedAgent("bull1", SignalType.BUY),
        _FixedAgent("bear1", SignalType.SELL),
    ]
    sup = Supervisor(agents, weighting=StaticWeighting({}), risk_manager=RiskManager())
    decision = sup.decide(_md())
    assert decision.conflict is True
    assert decision.signal is SignalType.WAIT


def test_supervisor_respects_veto():
    class VetoAgent(BaseAgent):
        def analyze(self, md):
            d = self._decision(SignalType.WAIT, 0, "veto")
            d.metadata["veto"] = True
            d.metadata["veto_reason"] = "test veto"
            return d

    agents = [_FixedAgent("bull", SignalType.BUY), VetoAgent("risk", {})]
    sup = Supervisor(agents, weighting=StaticWeighting({}), risk_manager=RiskManager())
    decision = sup.decide(_md())
    assert decision.vetoed is True
    assert decision.signal is SignalType.WAIT


def test_supervisor_consolidates_levels():
    agents = [
        _FixedAgent("a", SignalType.BUY, sl=1990.0, tp=2020.0),
        _FixedAgent("b", SignalType.BUY, sl=1994.0, tp=2024.0),
        _FixedAgent("c", SignalType.BUY, sl=1992.0, tp=2022.0),
    ]
    sup = Supervisor(agents, weighting=StaticWeighting({}), risk_manager=RiskManager())
    decision = sup.decide(_md())
    assert decision.stop_loss == 1992.0  # mediana
    assert decision.take_profit == 2022.0


def test_adaptive_weighting_learns():
    w = AdaptiveWeighting(base=1.0, alpha=0.5)
    regime = MarketRegime()
    before = w.weight_for("x", regime)
    for _ in range(5):
        w.update("x", regime, correct=True)
    after = w.weight_for("x", regime)
    assert after > before


def test_static_weighting_default_and_lookup():
    w = StaticWeighting({"trend_mtf": 2.0}, default=1.0)
    regime = MarketRegime()
    assert w.weight_for("trend_mtf", regime) == 2.0
    assert w.weight_for("otro", regime) == 1.0
