"""Scaffolds de agentes planificados para fases posteriores.

Cada uno se registra (para que el sistema los liste y el Supervisor pueda
ponderarlos en el futuro) pero, honestamente, devuelve WAIT con confianza 0 y una
explicación de su plan. Se implementarán en las fases indicadas del ROADMAP. Esto
mantiene el catálogo completo sin fingir capacidades que aún no existen.

Ya implementados en fases anteriores: Smart Money / Price Action
(`smart_money_agents.py`, Fase 2) y Machine Learning (`ml_agent.py`, Fase 4).
Scaffolds restantes: Elliott (Fase 2+), Correlación y Noticias (Fase 5).
"""
from __future__ import annotations

from ..core import AgentDecision, BaseAgent, MarketData, SignalType, register_agent


class _PlannedAgent(BaseAgent):
    """Base de un agente aún no implementado."""

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


@register_agent("elliott")
class ElliottWaveAgent(_PlannedAgent):
    category = "price_action"; phase = "2+"
    idea = "Conteo de ondas de Elliott (impulsivas/correctivas) — requiere validación"


@register_agent("correlation")
class CorrelationAgent(_PlannedAgent):
    category = "context"; phase = "5"
    idea = "Correlación con DXY, US10Y y SPX"


@register_agent("news")
class NewsAgent(_PlannedAgent):
    category = "context"; phase = "5"
    idea = "Calendario económico de alto impacto (veto/timing)"
