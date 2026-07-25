"""Tests del contrato núcleo: decisiones, enums y registro."""
from __future__ import annotations

import pytest

from trading_system.core import (
    AgentDecision,
    AgentRegistry,
    BaseAgent,
    MarketData,
    SignalType,
    register_agent,
)
from trading_system.core.exceptions import RegistryError


def test_signal_sign_and_from_sign():
    assert SignalType.BUY.sign == 1
    assert SignalType.SELL.sign == -1
    assert SignalType.WAIT.sign == 0
    assert SignalType.from_sign(0.5, deadband=0.2) is SignalType.BUY
    assert SignalType.from_sign(-0.5, deadband=0.2) is SignalType.SELL
    assert SignalType.from_sign(0.1, deadband=0.2) is SignalType.WAIT


def test_decision_clamps_ranges():
    d = AgentDecision("x", SignalType.BUY, confidence=150, estimated_risk=-10)
    assert d.confidence == 100.0
    assert d.estimated_risk == 0.0
    assert d.is_actionable is True


def test_decision_requires_signal_type():
    with pytest.raises(TypeError):
        AgentDecision("x", "BUY")  # type: ignore[arg-type]


def test_decision_to_dict_roundtrip_keys():
    d = AgentDecision("x", SignalType.SELL, confidence=60, explanation="foo")
    data = d.to_dict()
    assert data["signal"] == "SELL"
    assert data["confidence"] == 60.0
    assert "timestamp" in data


def test_registry_register_and_create():
    @register_agent("dummy_for_test")
    class Dummy(BaseAgent):
        def analyze(self, md: MarketData) -> AgentDecision:
            return self._decision(SignalType.BUY, 50, "ok")

    assert "dummy_for_test" in AgentRegistry.available()
    inst = AgentRegistry.create("dummy_for_test", {})
    assert isinstance(inst, Dummy)


def test_registry_unknown_raises():
    with pytest.raises(RegistryError):
        AgentRegistry.get("no_existe_zzz")
