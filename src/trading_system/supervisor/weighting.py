"""Estrategias de ponderación de agentes (Strategy pattern).

El Supervisor delega en una `WeightingStrategy` el cálculo del peso de cada agente
según el régimen de mercado. Esto es lo que permite que "cada agente pese más en
la condición donde acierta".
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Dict

from ..core.enums import SignalType
from ..core.market_data import MarketRegime


class WeightingStrategy(ABC):
    """Contrato de una estrategia de ponderación."""

    @abstractmethod
    def weight_for(self, agent_name: str, regime: MarketRegime) -> float:
        """Peso (>=0) del agente en el régimen dado."""

    def update(self, agent_name: str, regime: MarketRegime, correct: bool) -> None:
        """Retroalimentación opcional del resultado (para estrategias adaptativas)."""


class StaticWeighting(WeightingStrategy):
    """Pesos fijos por agente desde configuración (fallback y punto de partida)."""

    def __init__(self, weights: Dict[str, float], default: float = 1.0) -> None:
        self._weights = dict(weights)
        self._default = default

    def weight_for(self, agent_name: str, regime: MarketRegime) -> float:
        return max(0.0, self._weights.get(agent_name, self._default))


class AdaptiveWeighting(WeightingStrategy):
    """Peso proporcional al desempeño reciente del agente por régimen.

    Mantiene un hit-rate suavizado (EMA) por (agente, régimen). El peso es
    `base * (0.5 + hit_rate)`, de modo que un agente que acierta mucho en un
    régimen pesa más ahí, y uno que falla, menos. Es aprendizaje online,
    explicable y barato — antesala del meta-modelo de ML de la Fase 4.
    """

    def __init__(self, base: float = 1.0, alpha: float = 0.1, prior: float = 0.5) -> None:
        self.base = base
        self.alpha = alpha
        self.prior = prior
        self._hit: Dict[str, float] = defaultdict(lambda: prior)

    @staticmethod
    def _key(agent_name: str, regime: MarketRegime) -> str:
        return f"{agent_name}@{regime.key}"

    def weight_for(self, agent_name: str, regime: MarketRegime) -> float:
        hit = self._hit[self._key(agent_name, regime)]
        return max(0.0, self.base * (0.5 + hit))

    def update(self, agent_name: str, regime: MarketRegime, correct: bool) -> None:
        key = self._key(agent_name, regime)
        prev = self._hit[key]
        self._hit[key] = (1 - self.alpha) * prev + self.alpha * (1.0 if correct else 0.0)

    def hit_rate(self, agent_name: str, regime: MarketRegime) -> float:
        return self._hit[self._key(agent_name, regime)]


class MetaModelWeighting(WeightingStrategy):
    """Placeholder del meta-modelo de ML (Fase 4).

    En la Fase 4 se sustituye por un modelo entrenado (p. ej. gradient boosting)
    que toma como features las decisiones+confianzas de todos los agentes y el
    contexto de mercado, y predice qué combinación maximiza la probabilidad de
    éxito. Hasta entonces delega en una estrategia de respaldo.
    """

    def __init__(self, fallback: WeightingStrategy) -> None:
        self.fallback = fallback

    def weight_for(self, agent_name: str, regime: MarketRegime) -> float:
        return self.fallback.weight_for(agent_name, regime)

    def update(self, agent_name: str, regime: MarketRegime, correct: bool) -> None:
        self.fallback.update(agent_name, regime, correct)
