"""Tests de endurecimiento del LiveTrader: conciliación, kill switch, alertas."""
from __future__ import annotations

from trading_system import LiveTrader
from trading_system.alerts import Notifier
from trading_system.core import BaseAgent, SignalType
from trading_system.data import SimulatedDataFeed
from trading_system.execution import MarketGuard, MT5Broker, MT5DataFeed, SimulatedMT5Client
from trading_system.persistence import SqliteRepository
from trading_system.risk import KillSwitch, KillSwitchConfig, RiskManager
from trading_system.supervisor import StaticWeighting, Supervisor


class _Bull(BaseAgent):
    def analyze(self, md):
        p = md.price
        return self._decision(SignalType.BUY, 85, "x", stop_loss=p - 8, take_profit=p + 12)


class _RecordingNotifier(Notifier):
    def __init__(self):
        self.messages = []

    def notify(self, message, subject="Trading System", level="info"):
        self.messages.append((subject, level, message))
        return True


def _trader(**kwargs):
    base = SimulatedDataFeed(base_price=2000, drift=0.05, volatility=1.5,
                             bars=1500, seed=9).generate()
    client = SimulatedMT5Client(base, start=400)
    client.connect()
    sup = Supervisor([_Bull("bull", {})], weighting=StaticWeighting({}),
                     risk_manager=RiskManager())
    trader = LiveTrader(MT5DataFeed(client, bars=300), MT5Broker(client), sup,
                        guard=MarketGuard(allow_weekend=True), **kwargs)
    return trader, client


def test_reconciles_closes_to_repository():
    repo = SqliteRepository(":memory:")
    repo.initialize()
    trader, client = _trader(repository=repo)
    closed_total = 0
    for _ in range(150):
        r = trader.step()
        closed_total += len(r.closed)
        client.advance(3)
    # Los cierres del broker se registran como CLOSED en la BD.
    closed_in_db = [t for t in repo.recent_trades(999) if t["status"] == "CLOSED"]
    assert closed_total > 0
    assert len(closed_in_db) == closed_total


def test_kill_switch_halts_new_entries():
    ks = KillSwitch(KillSwitchConfig(max_consecutive_losses=2))
    trader, client = _trader(kill_switch=ks)
    halted = False
    for _ in range(200):
        r = trader.step()
        if r.halted:
            halted = True
            assert r.opened is None
            break
        client.advance(3)
    assert halted and ks.tripped


def test_notifier_receives_open_and_close_events():
    notifier = _RecordingNotifier()
    trader, client = _trader(notifier=notifier)
    for _ in range(60):
        trader.step()
        client.advance(3)
    subjects = {s for s, _, _ in notifier.messages}
    assert "Operación abierta" in subjects
    assert "Operación cerrada" in subjects


def test_manual_kill_switch_flag(tmp_path):
    flag = tmp_path / "STOP"
    ks = KillSwitch(KillSwitchConfig(flag_file=str(flag)))
    trader, client = _trader(kill_switch=ks)
    flag.write_text("stop")
    result = trader.step()
    assert result.halted is True
    assert result.opened is None
