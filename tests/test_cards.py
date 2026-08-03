"""Tests de la ficha de decisión."""
from __future__ import annotations

from trading_system.cards import build_decision_card
from trading_system.core import AgentDecision, SignalType, SupervisorDecision


def _decision() -> SupervisorDecision:
    contributing = [
        AgentDecision("trend_mtf", SignalType.BUY, 100.0, "up"),
        AgentDecision("market_structure", SignalType.BUY, 75.0, "BOS"),
        AgentDecision("machine_learning", SignalType.SELL, 40.0, "ml"),
        AgentDecision("session", SignalType.WAIT, 0.0, "killzone"),
    ]
    return SupervisorDecision(
        signal=SignalType.BUY, confidence=72.0, score=0.72,
        explanation="BUY score=0.72. Principales: trend_mtf(BUY,100)",
        estimated_risk=43.0, stop_loss=2342.0, take_profit=2370.0, position_size=0.01,
        contributing=contributing, weights={"trend_mtf": 1.5, "market_structure": 1.4},
    )


def test_card_contains_key_fields():
    card = build_decision_card(_decision(), "XAUUSD", "UP:NORMAL", counter=42, entry=2350.0)
    assert "DECISIÓN #42" in card
    assert "XAUUSD" in card and "UP:NORMAL" in card
    assert "trend_mtf" in card and "machine_learning" in card
    assert "Entrada: 2350.00" in card
    assert "Stop Loss: 2342.00" in card
    assert "Take Profit: 2370.00" in card
    assert "ABRIR COMPRA" in card
    assert "Score: +0.720" in card


def test_card_orders_actionable_before_wait():
    card = build_decision_card(_decision(), "XAUUSD", "UP:NORMAL", entry=2350.0)
    # Los agentes accionables aparecen antes que los WAIT (session).
    assert card.index("trend_mtf") < card.index("session")


def test_card_sell_and_wait_labels():
    sell = SupervisorDecision(
        signal=SignalType.SELL, confidence=60.0, score=-0.6, explanation="SELL",
        estimated_risk=40.0, stop_loss=2360.0, take_profit=2330.0, position_size=0.02,
        contributing=[AgentDecision("trend_mtf", SignalType.SELL, 80.0, "down")],
    )
    card = build_decision_card(sell, "XAUUSD", "DOWN:HIGH", entry=2350.0)
    assert "ABRIR VENTA" in card and "DOWN:HIGH" in card
