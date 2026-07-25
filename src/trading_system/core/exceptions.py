"""Excepciones del dominio del sistema de trading."""
from __future__ import annotations


class TradingSystemError(Exception):
    """Excepción base del sistema."""


class AgentError(TradingSystemError):
    """Error producido dentro de un agente durante `analyze`."""


class DataError(TradingSystemError):
    """Datos de mercado ausentes, insuficientes o inconsistentes."""


class ConfigError(TradingSystemError):
    """Configuración inválida o incompleta."""


class ExecutionError(TradingSystemError):
    """Fallo al ejecutar/gestionar una orden en el broker."""


class RegistryError(TradingSystemError):
    """Alta/consulta inválida en el registro de agentes."""
