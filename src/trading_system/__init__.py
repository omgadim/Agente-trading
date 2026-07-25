"""Sistema de trading institucional multiagente para XAUUSD.

Punto de entrada del paquete. Expone las piezas de alto nivel más usadas.
"""
from __future__ import annotations

__version__ = "0.1.0"

from .core import (  # noqa: E402
    AgentDecision,
    AgentRegistry,
    BaseAgent,
    MarketData,
    SignalType,
    SupervisorDecision,
    register_agent,
)
from .engine import TradingEngine  # noqa: E402
from .supervisor import Supervisor  # noqa: E402

__all__ = [
    "__version__",
    "TradingEngine",
    "Supervisor",
    "BaseAgent",
    "AgentDecision",
    "SupervisorDecision",
    "MarketData",
    "SignalType",
    "AgentRegistry",
    "register_agent",
]
