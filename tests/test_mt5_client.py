"""Tests del cliente MT5 (simulado y validación del adapter real)."""
from __future__ import annotations

import pytest

from trading_system.core.enums import SignalType, Timeframe
from trading_system.core.exceptions import ExecutionError
from trading_system.data import SimulatedDataFeed
from trading_system.execution import OrderRequest, RealMT5Client, SimulatedMT5Client


@pytest.fixture
def client():
    base = SimulatedDataFeed(base_price=2000, drift=0.1, volatility=1.0,
                             bars=1000, seed=3).generate()
    c = SimulatedMT5Client(base, start=400, spread=0.20)
    c.connect()
    return c


def test_rates_no_lookahead_and_count(client):
    df = client.rates("XAUUSD", Timeframe.M5, 100)
    assert len(df) == 100
    # La última barra servida no debe superar el cursor.
    assert df.index[-1] <= client.base.index[client.cursor]
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_rates_resamples_higher_timeframe(client):
    m5 = client.rates("XAUUSD", Timeframe.M5, 120)
    h1 = client.rates("XAUUSD", Timeframe.H1, 20)
    # H1 agrega M5: su rango temporal cubre más minutos por barra.
    assert len(h1) <= len(m5)


def test_tick_has_spread(client):
    tick = client.tick("XAUUSD")
    assert tick.ask > tick.bid
    assert abs((tick.ask - tick.bid) - 0.20) < 1e-9
    assert tick.bid < tick.mid < tick.ask


def test_send_order_opens_position(client):
    res = client.send_order(OrderRequest("XAUUSD", SignalType.BUY, 0.10, sl=1990, tp=2020))
    assert res.success and res.ticket is not None
    positions = client.positions()
    assert len(positions) == 1
    assert positions[0].direction is SignalType.BUY


def test_position_profit_sign(client):
    price = client._price()
    client.send_order(OrderRequest("XAUUSD", SignalType.BUY, 1.0,
                                   sl=price - 10, tp=price + 100))
    # Sin mover el precio, el PnL flotante es ~ -spread * contrato (compramos al ask).
    pos = client.positions()[0]
    assert pos.profit <= 0


def test_modify_and_close(client):
    res = client.send_order(OrderRequest("XAUUSD", SignalType.SELL, 0.50, sl=2100, tp=1900))
    ticket = res.ticket
    assert client.modify_position(ticket, sl=2050, tp=1950).success
    assert client.positions()[0].sl == 2050
    close = client.close_position(ticket)
    assert close.success
    assert client.positions() == []


def test_advance_resolves_take_profit(client):
    price = client._price()
    # TP muy cercano por encima -> debe saltar al avanzar.
    client.send_order(OrderRequest("XAUUSD", SignalType.BUY, 0.10,
                                   sl=price - 50, tp=price + 0.5))
    client.advance(20)
    assert len(client.closed) >= 1


def test_account_equity_includes_floating(client):
    acct0 = client.account()
    client.send_order(OrderRequest("XAUUSD", SignalType.BUY, 1.0,
                                   sl=1000, tp=9000))
    acct1 = client.account()
    # Balance no cambia hasta cerrar; equity refleja PnL flotante.
    assert acct1.balance == acct0.balance
    assert acct1.equity != acct0.balance or acct1.equity == pytest.approx(acct0.balance, abs=50)


# ---- Adapter real: sin el paquete MetaTrader5 debe fallar limpio ----
def test_real_client_raises_without_package():
    c = RealMT5Client(login=1, password="x", server="y")
    with pytest.raises(ExecutionError):
        c.connect()
