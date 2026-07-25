"""Scaffolds de agentes planificados para fases posteriores.

Cada uno se registra (para que el sistema los liste y el Supervisor pueda
ponderarlos en el futuro) pero, honestamente, devuelve WAIT con confianza 0 y una
explicación de su plan. Se implementarán en las fases indicadas del ROADMAP. Esto
mantiene el catálogo completo sin fingir capacidades que aún no existen.
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


@register_agent("smart_money")
class SmartMoneyConceptsAgent(_PlannedAgent):
    category = "smart_money"; phase = "2"
    idea = "Premium/Discount e imbalance institucional"


@register_agent("order_blocks")
class OrderBlocksAgent(_PlannedAgent):
    category = "smart_money"; phase = "2"
    idea = "Order blocks (última vela contraria antes del impulso)"


@register_agent("fair_value_gap")
class FairValueGapAgent(_PlannedAgent):
    category = "smart_money"; phase = "2"
    idea = "Fair Value Gaps / imbalances de 3 velas"


@register_agent("liquidity_sweep")
class LiquiditySweepAgent(_PlannedAgent):
    category = "smart_money"; phase = "2"
    idea = "Barridos de liquidez (stop hunts) sobre highs/lows"


@register_agent("wyckoff")
class WyckoffAgent(_PlannedAgent):
    category = "smart_money"; phase = "2"
    idea = "Fases de acumulación/distribución, springs/upthrusts"


@register_agent("harmonic")
class HarmonicPatternAgent(_PlannedAgent):
    category = "price_action"; phase = "2"
    idea = "Patrones armónicos (Gartley/Bat/Butterfly) por ratios de Fibonacci"


@register_agent("elliott")
class ElliottWaveAgent(_PlannedAgent):
    category = "price_action"; phase = "2"
    idea = "Conteo de ondas de Elliott (impulsivas/correctivas)"


@register_agent("correlation")
class CorrelationAgent(_PlannedAgent):
    category = "context"; phase = "5"
    idea = "Correlación con DXY, US10Y y SPX"


@register_agent("news")
class NewsAgent(_PlannedAgent):
    category = "context"; phase = "5"
    idea = "Calendario económico de alto impacto (veto/timing)"


@register_agent("machine_learning")
class MachineLearningAgent(_PlannedAgent):
    category = "ml"; phase = "4"
    idea = "LSTM (secuencial) + XGBoost (tabular) sobre features de mercado"
