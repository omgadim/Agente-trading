"""Scaffolds de agentes planificados para fases posteriores.

Cada uno se registra (para que el sistema los liste y el Supervisor pueda
ponderarlos en el futuro) pero, honestamente, devuelve WAIT con confianza 0 y una
explicación de su plan. Se implementarán en las fases indicadas del ROADMAP. Esto
mantiene el catálogo completo sin fingir capacidades que aún no existen.

Ya implementados: Smart Money / Price Action (`smart_money_agents.py`, Fase 2),
Machine Learning (`ml_agent.py`, Fase 4), contexto externo — noticias,
correlación, sentimiento (`context_agents.py`, Fase 5) y Elliott (conteo de
ondas, en `smart_money_agents.py`). No quedan scaffolds pendientes; `_PlannedAgent`
se conserva como base por si se añaden agentes futuros.
"""
from __future__ import annotations

from ..core import AgentDecision, BaseAgent, MarketData, SignalType


class _PlannedAgent(BaseAgent):
    """Base de un agente aún no implementado (sin registrar por defecto)."""

    phase: str = "?"
    idea: str = ""

    def analyze(self, md: MarketData) -> AgentDecision:
        return self._decision(
            SignalType.WAIT,
            confidence=0.0,
            explanation=f"[{self.name}] planificado para Fase {self.phase}: {self.idea}",
            estimated_risk=0.0,
            planned=True,
            phase=self.phase,
        )
