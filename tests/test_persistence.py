"""Tests de la capa de persistencia (SQLite) e integración con backtester/live."""
from __future__ import annotations

import pytest

from trading_system.core import AgentDecision, AgentRegistry, SignalType, SupervisorDecision
from trading_system.data import SimulatedDataFeed
from trading_system.persistence import SqliteRepository
from trading_system.supervisor import Supervisor, StaticWeighting

import trading_system.agents  # noqa: F401


@pytest.fixture
def repo():
    r = SqliteRepository(":memory:")
    r.initialize()
    return r


def _decision():
    return SupervisorDecision(
        signal=SignalType.BUY, confidence=70, score=0.6, explanation="test",
        estimated_risk=40, stop_loss=1990, take_profit=2020, position_size=0.1,
        contributing=[AgentDecision("trend_mtf", SignalType.BUY, 80, "up")],
        weights={"trend_mtf": 1.5},
    )


def test_save_decision_persists_agents(repo):
    did = repo.save_decision(_decision(), "XAUUSD", "UP:NORMAL")
    assert did == 1
    decisions = repo.recent_decisions()
    assert decisions[0]["signal_type"] == "BUY"
    assert decisions[0]["regime"] == "UP:NORMAL"


def test_open_and_close_trade(repo):
    did = repo.save_decision(_decision(), "XAUUSD", "UP:NORMAL")
    tid = repo.open_trade("XAUUSD", "BUY", 0.1, 2000, 1990, 2020, decision_id=did, ticket=99)
    trades = repo.recent_trades()
    assert trades[0]["status"] == "OPEN"
    repo.close_trade(tid, 2020, 200.0)
    trades = repo.recent_trades()
    assert trades[0]["status"] == "CLOSED"
    assert float(trades[0]["pnl"]) == 200.0
    assert float(trades[0]["exit_price"]) == 2020.0


def test_agent_performance_upsert(repo):
    repo.update_agent_performance("trend_mtf", "UP:NORMAL", True)
    repo.update_agent_performance("trend_mtf", "UP:NORMAL", True)
    repo.update_agent_performance("trend_mtf", "UP:NORMAL", False)
    perf = repo.agent_performance()
    assert len(perf) == 1
    row = perf[0]
    assert row["hits"] == 2 and row["misses"] == 1
    assert abs(float(row["hit_rate"]) - 2 / 3) < 1e-6


def test_pnl_summary(repo):
    did = repo.save_decision(_decision(), "XAUUSD", "UP:NORMAL")
    for exit_price, pnl in [(2020, 200.0), (1980, -200.0), (2010, 100.0)]:
        tid = repo.open_trade("XAUUSD", "BUY", 0.1, 2000, 1990, 2020, decision_id=did)
        repo.close_trade(tid, exit_price, pnl)
    summary = repo.pnl_summary()
    assert summary["trades"] == 3
    assert summary["wins"] == 2
    assert summary["net_pnl"] == 100.0
    assert summary["winrate"] == round(2 / 3 * 100, 2)


def test_recent_limit_and_order(repo):
    for _ in range(5):
        repo.save_decision(_decision(), "XAUUSD", "UP:NORMAL")
    got = repo.recent_decisions(limit=3)
    assert len(got) == 3
    # Orden descendente por id.
    assert got[0]["id"] > got[-1]["id"]


def test_backtester_populates_db():
    from trading_system.backtest import Backtester

    repo = SqliteRepository(":memory:")
    repo.initialize()
    base = SimulatedDataFeed(base_price=2000, drift=0.05, volatility=1.2,
                             bars=1200, seed=5).generate()
    agents = [AgentRegistry.create(n, {}) for n in
              ("trend_mtf", "technical", "market_structure", "risk_management")]
    sup = Supervisor(agents, weighting=StaticWeighting({}))
    result = Backtester(sup, warmup=300, step=8, repository=repo).run(base)

    # Cada trade cerrado en el backtest existe en la BD con su PnL.
    assert repo.pnl_summary()["trades"] == result.metrics["trades"]
    assert abs(repo.pnl_summary()["net_pnl"] - result.metrics["net_pnl"]) < 1.0
    # Se registró desempeño por agente.
    assert len(repo.agent_performance()) >= 1


def test_livetrader_persists_decision_and_open():
    from trading_system.core import BaseAgent
    from trading_system.execution import MarketGuard, MT5Broker, MT5DataFeed, SimulatedMT5Client
    from trading_system.live import LiveTrader
    from trading_system.risk import RiskManager

    class BullAgent(BaseAgent):
        def analyze(self, md):
            p = md.price
            return self._decision(SignalType.BUY, 85.0, "compra",
                                  stop_loss=p - 10, take_profit=p + 20)

    repo = SqliteRepository(":memory:")
    repo.initialize()
    base = SimulatedDataFeed(base_price=2000, drift=0.1, volatility=1.0, bars=900, seed=4).generate()
    client = SimulatedMT5Client(base, start=400)
    client.connect()
    trader = LiveTrader(
        MT5DataFeed(client, bars=300), MT5Broker(client),
        Supervisor([BullAgent("bull", {})], weighting=StaticWeighting({}), risk_manager=RiskManager()),
        guard=MarketGuard(allow_weekend=True), repository=repo,
    )
    result = trader.step()
    assert result.opened is not None
    assert len(repo.recent_decisions()) == 1
    trades = repo.recent_trades()
    assert len(trades) == 1 and trades[0]["status"] == "OPEN"
