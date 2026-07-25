"""Paquete de agentes.

Importar este paquete registra todos los agentes en el `AgentRegistry` (efecto de
los decoradores `@register_agent`). El supervisor los construye por nombre desde
la configuración.
"""
from __future__ import annotations

# Los imports disparan el registro por efecto de los decoradores.
from . import (
    context_agents,
    ml_agent,
    risk_agents,
    scaffold,
    smart_money_agents,
    structure_agents,
    trend_agents,
    volatility_agents,
)

__all__ = [
    "trend_agents",
    "volatility_agents",
    "structure_agents",
    "smart_money_agents",
    "ml_agent",
    "context_agents",
    "risk_agents",
    "scaffold",
]
