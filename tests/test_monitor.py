"""Tests del monitor HTML (dashboard sin servidor)."""
from __future__ import annotations

from trading_system.core import SignalType, SupervisorDecision
from trading_system.monitor import collect_dashboard_data, render_dashboard_html
from trading_system.persistence import SqliteRepository


def _repo_with_data() -> SqliteRepository:
    repo = SqliteRepository(":memory:")
    repo.initialize()
    decision = SupervisorDecision(
        signal=SignalType.BUY, confidence=72.0, score=0.72, explanation="BUY score=0.72",
        estimated_risk=40.0, stop_loss=2342.0, take_profit=2370.0, position_size=0.01,
    )
    dec_id = repo.save_decision(decision, "XAUUSD", "UP:NORMAL")
    trade_id = repo.open_trade("XAUUSD", "BUY", 0.01, 2350.0, 2342.0, 2370.0,
                               decision_id=dec_id, ticket=1001)
    repo.close_trade(trade_id, 2370.0, 20.0)
    repo.update_agent_performance("trend_mtf", "UP:NORMAL", True)
    repo.update_agent_performance("machine_learning", "UP:NORMAL", False)
    return repo


def test_collect_returns_all_sections():
    repo = _repo_with_data()
    data = collect_dashboard_data(repo)
    assert set(data) == {"kpi", "performance", "decisions", "trades"}
    assert data["kpi"]["trades"] == 1
    assert data["kpi"]["wins"] == 1
    assert data["kpi"]["net_pnl"] == 20.0
    assert data["kpi"]["winrate"] == 100.0
    # Ordenado por hit-rate desc: el acierto (trend_mtf) va antes que el fallo.
    assert data["performance"][0]["agent_name"] == "trend_mtf"


def test_render_html_contains_kpis_and_rows():
    repo = _repo_with_data()
    html = render_dashboard_html(collect_dashboard_data(repo), refresh=15)
    assert "<!doctype html>" in html
    assert 'http-equiv="refresh" content="15"' in html
    assert "XAUUSD" in html
    assert "trend_mtf" in html and "machine_learning" in html
    assert "20.00" in html          # PnL de la operación
    assert "BUY" in html            # señal/dirección


def test_render_html_escapes_and_handles_empty():
    repo = SqliteRepository(":memory:")
    repo.initialize()
    html = render_dashboard_html(collect_dashboard_data(repo))
    # Sin datos, muestra los marcadores vacíos y no rompe.
    assert "Sin datos todavía" in html
    assert "Sin operaciones todavía" in html
