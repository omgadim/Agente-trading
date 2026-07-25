"""Tests de integración de la fachada TradingEngine y el RiskManager."""
from __future__ import annotations

from pathlib import Path

from trading_system import TradingEngine
from trading_system.core import SupervisorDecision
from trading_system.risk import RiskManager, RiskParameters
from trading_system.utils import load_config


def _config():
    root = Path(__file__).resolve().parents[1]
    return load_config(root / "config" / "config.yaml")


def test_engine_runs_full_cycle():
    engine = TradingEngine(_config())
    decision = engine.run_once()
    assert isinstance(decision, SupervisorDecision)
    # Deben haber corrido los agentes reales + scaffolds deshabilitados excluidos.
    names = {d.agent_name for d in decision.contributing}
    assert "trend_mtf" in names
    assert "smart_money" in names       # Fase 2, activo en config
    assert "machine_learning" in names  # Fase 4, activo en config
    assert "news" in names              # Fase 5, activo en config
    assert "elliott" not in names       # scaffold deshabilitado en config


def test_engine_execute_opens_paper_position():
    engine = TradingEngine(_config())
    decision = engine.run_once(execute=True)
    if decision.signal.value in ("BUY", "SELL") and not decision.vetoed:
        assert len(engine.broker.open_positions()) == 1


def test_risk_manager_position_size():
    rm = RiskManager(RiskParameters(account_balance=10000, risk_per_trade_pct=1.0,
                                    contract_size=100.0))
    # Riesgo 100$; distancia 5.0; 5*100=500 por lote -> 0.2 lotes.
    size = rm.position_size(entry=2000.0, stop_loss=1995.0)
    assert abs(size - 0.2) < 1e-9


def test_risk_manager_daily_loss_veto():
    rm = RiskManager(RiskParameters(account_balance=10000, max_daily_loss_pct=5.0))
    rm.register_pnl(-600)  # supera 5% (500)
    from trading_system.core import SignalType
    rd = rm.evaluate(SignalType.BUY, entry=2000.0, stop_loss=1990.0)
    assert rd.approved is False
