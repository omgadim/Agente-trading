"""Ficha de decisión: resumen legible de *por qué* el sistema abre una operación.

Se construye con los datos reales de la `SupervisorDecision` (voto y confianza de
cada agente, score, riesgo, SL/TP y motivo). El `LiveTrader` la registra en el log
y, opcionalmente, la anexa a un archivo para revisarla después. Así queda auditado
cada trade: en quién se apoyó la decisión y con qué convicción.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .core.decision import SupervisorDecision
from .core.enums import SignalType

_LINE = "═" * 47


def _fmt(value: Optional[float], decimals: int = 2) -> str:
    return "—" if value is None else f"{value:.{decimals}f}"


def build_decision_card(
    decision: SupervisorDecision,
    symbol: str,
    regime_key: str = "",
    timestamp: Optional[datetime] = None,
    counter: Optional[int] = None,
    entry: Optional[float] = None,
) -> str:
    """Devuelve la ficha de decisión como texto (multilínea)."""
    ts = timestamp or datetime.now(timezone.utc)
    title = f"DECISIÓN #{counter}" if counter is not None else "DECISIÓN"

    # Agentes ordenados por su aporte (peso × confianza), los accionables primero.
    weights = decision.weights or {}
    contributing = sorted(
        decision.contributing,
        key=lambda d: (d.signal is not SignalType.WAIT,
                       weights.get(d.agent_name, 1.0) * d.confidence),
        reverse=True,
    )
    votes = []
    for d in contributing:
        mark = {"BUY": "✅", "SELL": "🔻"}.get(d.signal.value, "·")
        peso = weights.get(d.agent_name, 1.0)
        votes.append(f"  {mark} {d.agent_name:<20} {d.signal.value:<4} "
                     f"conf={d.confidence:5.1f}  peso={peso:.2f}")

    action = {
        SignalType.BUY: "✅ ABRIR COMPRA",
        SignalType.SELL: "🔻 ABRIR VENTA",
        SignalType.WAIT: "⏸ ESPERAR",
    }[decision.signal]

    lines = [
        _LINE,
        title,
        "",
        f"Activo: {symbol}",
        f"Hora: {ts:%Y-%m-%d %H:%M:%S} UTC",
        f"Régimen: {regime_key or '—'}",
        "",
        "Votos de los agentes (peso × confianza):",
        *votes,
        "",
        f"Score: {decision.score:+.3f}   Confianza: {decision.confidence:.1f}%   "
        f"Riesgo: {decision.estimated_risk:.1f}%",
        f"Conflicto: {'Sí' if decision.conflict else 'No'}   "
        f"Veto: {'Sí' if decision.vetoed else 'No'}",
        "",
        f"Entrada: {_fmt(entry)}",
        f"Stop Loss: {_fmt(decision.stop_loss)}",
        f"Take Profit: {_fmt(decision.take_profit)}",
        f"Tamaño: {_fmt(decision.position_size)} lotes",
        "",
        f"Motivo: {decision.explanation}",
        "",
        f"DECISIÓN FINAL: {action}",
        _LINE,
    ]
    return "\n".join(lines)
