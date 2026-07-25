"""Tests de MT5Broker y MT5DataFeed sobre el cliente simulado."""
from __future__ import annotations

import pytest

from trading_system.core import MarketData
from trading_system.core.enums import SignalType, Timeframe
from trading_system.data import SimulatedDataFeed
from trading_system.execution import MT5Broker, MT5DataFeed, Order, SimulatedMT5Client


@pytest.fixture
def client():
    base = SimulatedDataFeed(base_price=2000, drift=0.1, volatility=1.0,
                             bars=1000, seed=8).generate()
    c = SimulatedMT5Client(base, start=500, spread=0.3)
    c.connect()
    return c


def test_feed_builds_market_data(client):
    feed = MT5DataFeed(client, timeframes=(Timeframe.M5, Timeframe.M15, Timeframe.H1), bars=300)
    md = feed.get_market_data("XAUUSD")
    assert isinstance(md, MarketData)
    assert md.has(Timeframe.M5) and md.has(Timeframe.H1)
    assert md.price > 0
    assert md.spread == pytest.approx(0.3, abs=1e-6)
    assert md.regime is not None


def test_broker_open_and_positions(client):
    broker = MT5Broker(client)
    order = Order(symbol="XAUUSD", direction=SignalType.BUY, volume=0.2,
                  price=0.0, stop_loss=1990, take_profit=2020)
    opened = broker.open(order)
    assert opened.ticket is not None
    positions = broker.open_positions()
    assert len(positions) == 1
    assert positions[0].direction is SignalType.BUY


def test_broker_modify_and_close(client):
    broker = MT5Broker(client)
    order = broker.open(Order("XAUUSD", SignalType.SELL, 0.5, 0.0, stop_loss=2100, take_profit=1900))
    assert broker.modify(order.ticket, sl=2050, tp=1950) is True
    pnl = broker.close(order.ticket)
    assert isinstance(pnl, float)
    assert broker.open_positions() == []


def test_broker_open_failure_raises(client):
    client.shutdown()  # cliente desconectado -> send_order falla
    broker = MT5Broker(client)
    from trading_system.core.exceptions import ExecutionError
    with pytest.raises(ExecutionError):
        broker.open(Order("XAUUSD", SignalType.BUY, 0.1, 0.0, stop_loss=1990, take_profit=2020))
