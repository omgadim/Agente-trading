"""Clase base de todos los agentes (Template Method + Strategy)."""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from .decision import AgentDecision
from .enums import SignalType
from .exceptions import AgentError
from .market_data import MarketData


class BaseAgent(ABC):
    """Contrato común de un agente especializado.

    Las subclases implementan únicamente `analyze()`. El método público `run()`
    (Template Method) envuelve la ejecución con medición de tiempo y aislamiento
    de fallos: si un agente lanza una excepción, el sistema no cae; se devuelve
    una decisión WAIT con confianza 0 y se registra el error.
    """

    #: Categoría/familia del agente (para ponderación por grupo).
    category: str = "generic"

    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None) -> None:
        self.name = name
        self.config = config or {}
        self.enabled: bool = self.config.get("enabled", True)
        self.logger = logging.getLogger(f"agent.{name}")
        self._last_latency_ms: float = 0.0

    # ---- API pública -----------------------------------------------------
    def run(self, market_data: MarketData) -> AgentDecision:
        """Ejecuta el análisis de forma segura y medida."""
        if not self.enabled:
            return self._wait("Agente deshabilitado")

        start = time.perf_counter()
        try:
            decision = self.analyze(market_data)
            if not isinstance(decision, AgentDecision):
                raise AgentError(
                    f"{self.name}.analyze() devolvió {type(decision)!r}, "
                    "se esperaba AgentDecision"
                )
            return decision
        except Exception as exc:  # aislamiento de fallos por agente
            self.logger.exception("Fallo en %s: %s", self.name, exc)
            return self._wait(f"Error interno: {exc}")
        finally:
            self._last_latency_ms = (time.perf_counter() - start) * 1000.0

    @property
    def last_latency_ms(self) -> float:
        return self._last_latency_ms

    # ---- A implementar por subclases -------------------------------------
    @abstractmethod
    def analyze(self, market_data: MarketData) -> AgentDecision:
        """Analiza el mercado y devuelve una decisión. Debe ser puro/idempotente."""

    # ---- Utilidades para subclases ---------------------------------------
    def _decision(
        self,
        signal: SignalType,
        confidence: float,
        explanation: str,
        estimated_risk: float = 50.0,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        **metadata: Any,
    ) -> AgentDecision:
        """Fábrica interna para construir decisiones con el nombre del agente."""
        return AgentDecision(
            agent_name=self.name,
            signal=signal,
            confidence=confidence,
            explanation=explanation,
            estimated_risk=estimated_risk,
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata=metadata,
        )

    def _wait(self, reason: str, confidence: float = 0.0) -> AgentDecision:
        return self._decision(SignalType.WAIT, confidence, reason, estimated_risk=0.0)

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<{type(self).__name__} name={self.name!r} category={self.category!r}>"
