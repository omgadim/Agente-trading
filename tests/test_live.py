"""Tests del orquestador LiveTrader (con broker/feed simulados)."""
from __future__ import annotations

import pytest

from trading_system import LiveTrader
from trading_system.core import BaseAgent, SignalType
from trading_system.data import SimulatedDataFeed
from trading_system.execution import (
    MarketGuard,
    MT5Broker,
    MT5DataFeed,
    Order,
    SimulatedMT5Client,
)
from trading_system.risk import RiskManager
from trading_system.supervisor import StaticWeighting, Supervisor


class _FixedAgent(BaseAgent):
    def __init__(self, name, signal, price):
        super().__init__(name, {})
        self._signal = signal
        self._price = price

    def analyze(self, md):
        if self._signal is SignalType.WAIT:
            return self._wait("fijo wait")
        sl = self._price - 15 if self._signal is SignalType.BUY else self._price + 15
        tp = self._price + 30 if self._signal is SignalType.BUY else self._price - 30
        return self._decision(self._signal, 80.0, "fijo", estimated_risk=30.0,
                              stop_loss=sl, take_profit=tp)


def _make(base_kwargs, agents, guard=None, start=400, spread=0.2, max_positions=1):
    base = SimulatedDataFeed(**base_kwargs).generate()
    client = SimulatedMT5Client(base, start=start, spread=spread)
    client.connect()
    feed = MT5DataFeed(client, bars=300)
    broker = MT5Broker(client)
    price = client._price()
    sup = Supervisor(agents(price), weighting=StaticWeighting({}), risk_manager=RiskManager())
    trader = LiveTrader(feed, broker, sup,
                        guard=guard or MarketGuard(allow_weekend=True),
                        max_positions=max_positions)
    return trader, client, broker


def test_livetrader_opens_on_consensus():
    trader, client, broker = _make(
        dict(base_price=2000, drift=0.1, volatility=1.0, bars=1000, seed=4),
        lambda p: [_FixedAgent("a", SignalType.BUY, p), _FixedAgent("b", SignalType.BUY, p)],
    )
    result = trader.step()
    assert result.opened is not None
    assert len(broker.open_positions()) == 1


def test_livetrader_respects_max_positions():
    trader, client, broker = _make(
        dict(base_price=2000, drift=0.1, volatility=1.0, bars=1000, seed=5),
        lambda p: [_FixedAgent("a", SignalType.BUY, p)],
        max_positions=1,
    )
    trader.step()
    second = trader.step()
    assert second.opened is None
    assert second.skipped_reason == "Cupo de posiciones alcanzado"
    assert len(broker.open_positions()) == 1


def test_livetrader_guard_blocks_wide_spread():
    trader, client, broker = _make(
        dict(base_price=2000, drift=0.1, volatility=1.0, bars=1000, seed=6),
        lambda p: [_FixedAgent("a", SignalType.BUY, p)],
        guard=MarketGuard(max_spread=0.01, allow_weekend=True),
        spread=0.5,
    )
    result = trader.step()
    assert result.opened is None
    assert result.guard_ok is False
    assert "spread" in result.guard_reason.lower()


def test_livetrader_manages_open_position():
    # Tendencia alcista fuerte y poco ruido: el precio sube muchos ATR.
    trader, client, broker = _make(
        dict(base_price=2000, drift=0.5, volatility=0.4, bars=1500, seed=7),
        lambda p: [_FixedAgent("wait", SignalType.WAIT, p)],
    )
    entry = client._price()
    order = broker.open(Order("XAUUSD", SignalType.BUY, 0.1, entry,
                              stop_loss=entry - 50, take_profit=entry + 100000))
    original_sl = order.stop_loss

    client.advance(250)  # el precio sube con fuerza
    result = trader.step()

    assert result.management, "debería haber acciones de gestión"
    new_sl = broker.open_positions()[0].stop_loss
    assert new_sl > original_sl  # el stop se apretó al alza
