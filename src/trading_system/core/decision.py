"""Contrato de decisión: la unidad de comunicación del ecosistema.

Tanto los agentes como el supervisor hablan mediante estas estructuras. Mantener
este contrato estable es lo que permite añadir agentes sin tocar el supervisor.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .enums import SignalType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class AgentDecision:
    """Salida estandarizada de un agente.

    Attributes:
        agent_name: identificador del agente emisor.
        signal: BUY / SELL / WAIT.
        confidence: convicción en [0, 100].
        explanation: motivo legible de la decisión (auditoría / dashboard).
        estimated_risk: riesgo percibido de la operación en [0, 100].
        stop_loss: precio de stop sugerido (opcional).
        take_profit: precio objetivo sugerido (opcional).
        metadata: datos crudos para auditoría o entrenamiento de ML.
        timestamp: momento de emisión (UTC).
    """

    agent_name: str
    signal: SignalType
    confidence: float = 0.0
    explanation: str = ""
    estimated_risk: float = 50.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not isinstance(self.signal, SignalType):
            raise TypeError(f"signal debe ser SignalType, no {type(self.signal)!r}")
        self.confidence = _clamp(float(self.confidence), 0.0, 100.0)
        self.estimated_risk = _clamp(float(self.estimated_risk), 0.0, 100.0)

    @property
    def is_actionable(self) -> bool:
        """True si la señal es direccional (no WAIT)."""
        return self.signal is not SignalType.WAIT

    def to_dict(self) -> Dict[str, Any]:
        """Serializa para logging/persistencia."""
        return {
            "agent_name": self.agent_name,
            "signal": self.signal.value,
            "confidence": round(self.confidence, 2),
            "explanation": self.explanation,
            "estimated_risk": round(self.estimated_risk, 2),
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class SupervisorDecision:
    """Decisión final agregada por el Supervisor Central."""

    signal: SignalType
    confidence: float
    score: float  # puntuación global en [-1, 1]
    explanation: str
    estimated_risk: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size: Optional[float] = None
    conflict: bool = False
    vetoed: bool = False
    veto_reason: Optional[str] = None
    contributing: List[AgentDecision] = field(default_factory=list)
    weights: Dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal": self.signal.value,
            "confidence": round(self.confidence, 2),
            "score": round(self.score, 4),
            "explanation": self.explanation,
            "estimated_risk": round(self.estimated_risk, 2),
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "position_size": self.position_size,
            "conflict": self.conflict,
            "vetoed": self.vetoed,
            "veto_reason": self.veto_reason,
            "weights": {k: round(v, 4) for k, v in self.weights.items()},
            "contributing": [d.to_dict() for d in self.contributing],
            "timestamp": self.timestamp.isoformat(),
        }
