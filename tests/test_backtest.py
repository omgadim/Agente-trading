"""Tests del backtester y sus métricas."""
from __future__ import annotations

import pytest

from trading_system.backtest import Backtester
from trading_system.backtest.metrics import compute_metrics
from trading_system.core import AgentRegistry
from trading_system.data import SimulatedDataFeed
from trading_system.supervisor import Supervisor, StaticWeighting

import trading_system.agents  # noqa: F401


def test_metrics_basic():
    pnls = [100, -50, 200, -30, 80]
    equity = [10000, 10100, 10050, 10250, 10220, 10300]
    m = compute_metrics(pnls, equity)
    assert m["trades"] == 5
    assert m["wins"] == 3 and m["losses"] == 2
    assert m["winrate"] == 60.0
    assert m["net_pnl"] == 300
    assert m["profit_factor"] == round(380 / 80, 3)
    assert m["max_drawdown"] == 50  # de 10100 a 10050


def test_metrics_empty():
    m = compute_metrics([], [10000])
    assert m["trades"] == 0 and m["profit_factor"] == 0.0


def test_backtester_runs_and_reports():
    base = SimulatedDataFeed(base_price=2000, drift=0.05, volatility=1.2,
                             bars=1200, seed=5).generate()
    agents = [AgentRegistry.create(n, {}) for n in
              ("trend_mtf", "technical", "momentum", "market_structure", "risk_management")]
    sup = Supervisor(agents, weighting=StaticWeighting({}))
    bt = Backtester(sup, warmup=300, step=8)
    result = bt.run(base)

    assert result.metrics["trades"] >= 0
    # La curva de equity empieza en el capital inicial.
    assert result.equity_curve[0] == 10000.0
    # PnL neto coherente con la equity final (suma de PnL de trades sin redondeo).
    raw_net = sum(t.pnl for t in result.trades)
    assert abs((result.equity_curve[-1] - 10000.0) - raw_net) < 1e-6
    # No hay look-ahead: cada trade cierra en una barra >= a su entrada.
    for t in result.trades:
        if t.exit_pos is not None:
            assert t.exit_pos >= t.entry_pos


def test_backtester_rejects_short_series():
    base = SimulatedDataFeed(bars=50, seed=1).generate()
    agents = [AgentRegistry.create("trend_mtf", {})]
    sup = Supervisor(agents, weighting=StaticWeighting({}))
    bt = Backtester(sup, warmup=300, step=5)
    with pytest.raises(ValueError):
        bt.run(base)
