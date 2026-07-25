"""Núcleo del sistema: contratos, enums y framework de agentes."""
from __future__ import annotations

from .base_agent import BaseAgent
from .decision import AgentDecision, SupervisorDecision
from .enums import (
    SignalType,
    Timeframe,
    TrendDirection,
    VolatilityRegime,
)
from .exceptions import (
    AgentError,
    ConfigError,
    DataError,
    ExecutionError,
    RegistryError,
    TradingSystemError,
)
from .market_data import MarketData, MarketRegime, OHLCV_COLUMNS
from .registry import AgentRegistry, register_agent

__all__ = [
    "BaseAgent",
    "AgentDecision",
    "SupervisorDecision",
    "SignalType",
    "Timeframe",
    "TrendDirection",
    "VolatilityRegime",
    "MarketData",
    "MarketRegime",
    "OHLCV_COLUMNS",
    "AgentRegistry",
    "register_agent",
    "TradingSystemError",
    "AgentError",
    "DataError",
    "ConfigError",
    "ExecutionError",
    "RegistryError",
]
