"""Enumeraciones centrales del sistema de trading."""
from __future__ import annotations

from enum import Enum


class SignalType(Enum):
    """Señal direccional que emite cualquier agente o el supervisor."""

    BUY = "BUY"
    SELL = "SELL"
    WAIT = "WAIT"

    @property
    def sign(self) -> int:
        """Signo numérico útil para agregación ponderada.

        BUY -> +1, SELL -> -1, WAIT -> 0.
        """
        return {SignalType.BUY: 1, SignalType.SELL: -1, SignalType.WAIT: 0}[self]

    @classmethod
    def from_sign(cls, value: float, deadband: float = 0.0) -> "SignalType":
        """Convierte una puntuación en [-1, 1] a una señal.

        `deadband` define la zona muerta alrededor de cero que se traduce en WAIT.
        """
        if value > deadband:
            return cls.BUY
        if value < -deadband:
            return cls.SELL
        return cls.WAIT


class TrendDirection(Enum):
    """Dirección de tendencia detectada para el régimen de mercado."""

    UP = "UP"
    DOWN = "DOWN"
    RANGE = "RANGE"


class VolatilityRegime(Enum):
    """Régimen de volatilidad basado en ATR normalizado."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


class Timeframe(Enum):
    """Marcos temporales soportados (etiqueta -> minutos)."""

    M1 = 1
    M5 = 5
    M15 = 15
    M30 = 30
    H1 = 60
    H4 = 240
    D1 = 1440

    @property
    def minutes(self) -> int:
        return self.value
