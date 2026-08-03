"""Tests del meta-modelo de ponderación (stacking)."""
from __future__ import annotations

from trading_system.core import AgentDecision, SignalType
from trading_system.core.market_data import MarketRegime
from trading_system.supervisor import AdaptiveWeighting, MetaModelWeighting


def _decision(name, signal, conf=100.0):
    return AgentDecision(name, signal, confidence=conf)


def test_meta_warmup_delegates_to_fallback():
    fallback = AdaptiveWeighting(base=1.0)
    meta = MetaModelWeighting(fallback=fallback, warmup=30)
    regime = MarketRegime()
    # Sin observaciones: debe devolver el peso del respaldo.
    assert meta.weight_for("x", regime) == fallback.weight_for("x", regime)


def test_meta_learns_useful_agent_gets_more_weight():
    meta = MetaModelWeighting(warmup=20, lr=0.1)
    regime = MarketRegime()
    # 'good' vota en la dirección del resultado; 'noise' siempre compra.
    for i in range(300):
        profitable = (i % 2 == 0)
        good = _decision("good", SignalType.BUY if profitable else SignalType.SELL)
        noise = _decision("noise", SignalType.BUY)
        meta.observe([good, noise], regime, profitable)

    w_good = meta.weight_for("good", regime)
    w_noise = meta.weight_for("noise", regime)
    assert w_good > w_noise


def test_meta_weight_is_non_negative():
    meta = MetaModelWeighting(warmup=5)
    regime = MarketRegime()
    for i in range(50):
        meta.observe([_decision("a", SignalType.SELL)], regime, i % 3 == 0)
    assert meta.weight_for("a", regime) >= 0.0


def test_supervisor_feedback_invokes_observe():
    """La retroalimentación del Supervisor alimenta el meta-modelo."""
    from trading_system.core import BaseAgent, MarketData, Timeframe
    import pandas as pd

    class FixedAgent(BaseAgent):
        def analyze(self, md):
            return self._decision(SignalType.BUY, 80.0, "fijo", stop_loss=1990, take_profit=2020)

    from trading_system.supervisor import Supervisor

    idx = pd.date_range("2024-01-01", periods=60, freq="5min")
    close = pd.Series(range(2000, 2060), index=idx, dtype=float)
    df = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                       "close": close, "volume": 1000.0})
    md = MarketData("XAUUSD", {Timeframe.M5: df}, price=2000.0, regime=MarketRegime(atr=5.0))

    meta = MetaModelWeighting(warmup=2)
    sup = Supervisor([FixedAgent("a", {}), FixedAgent("b", {})], weighting=meta)
    decision = sup.decide(md)
    sup.feedback(decision.contributing, md, profitable=True)
    # observe() debe haber registrado una muestra en el régimen.
    assert meta._counts[md.regime.key] == 1
