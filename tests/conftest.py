"""Fixtures compartidas de los tests."""
from __future__ import annotations

import pytest

from trading_system.data import SimulatedDataFeed


@pytest.fixture
def uptrend_feed():
    """Feed con deriva positiva fuerte (tendencia alcista clara)."""
    return SimulatedDataFeed(base_price=2000.0, drift=0.6, volatility=1.0, bars=400, seed=1)


@pytest.fixture
def downtrend_feed():
    """Feed con deriva negativa fuerte (tendencia bajista clara)."""
    return SimulatedDataFeed(base_price=2000.0, drift=-0.6, volatility=1.0, bars=400, seed=2)


@pytest.fixture
def market_data(uptrend_feed):
    return uptrend_feed.get_market_data("XAUUSD")
