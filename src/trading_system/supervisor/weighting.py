"""Estrategias de ponderación de agentes (Strategy pattern).

El Supervisor delega en una `WeightingStrategy` el cálculo del peso de cada agente
según el régimen de mercado. Esto es lo que permite que "cada agente pese más en
la condición donde acierta".
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Dict, Sequence

import numpy as np

from ..core.enums import SignalType
from ..core.market_data import MarketRegime


class WeightingStrategy(ABC):
    """Contrato de una estrategia de ponderación."""

    @abstractmethod
    def weight_for(self, agent_name: str, regime: MarketRegime) -> float:
        """Peso (>=0) del agente en el régimen dado."""

    def update(self, agent_name: str, regime: MarketRegime, correct: bool) -> None:
        """Retroalimentación por-agente (estrategias adaptativas)."""

    def observe(self, decisions: Sequence, regime: MarketRegime, profitable: bool) -> None:
        """Retroalimentación conjunta del ciclo (para meta-modelos de stacking)."""


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


class _OnlineLogistic:
    """Regresión logística online (SGD + L2) para el meta-modelo."""

    def __init__(self, dim: int, lr: float = 0.05, l2: float = 1e-4) -> None:
        self.w = np.zeros(dim)
        self.b = 0.0
        self.lr = lr
        self.l2 = l2

    def predict(self, x: np.ndarray) -> float:
        z = float(np.dot(x, self.w) + self.b)
        return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))

    def update(self, x: np.ndarray, y: float) -> None:
        error = self.predict(x) - y
        self.w -= self.lr * (error * x + self.l2 * self.w)
        self.b -= self.lr * error


class MetaModelWeighting(WeightingStrategy):
    """Meta-modelo de *stacking* que aprende el peso de cada agente por régimen.

    Por cada régimen mantiene una regresión logística online cuyas *features* son
    los votos con signo de todos los agentes (signo de la señal × confianza) y cuya
    etiqueta es si la operación resultó ganadora. El coeficiente aprendido para un
    agente mide cuánto aporta su voto a un resultado rentable en ese régimen; el
    peso del agente es proporcional a la magnitud de ese coeficiente.

    A diferencia de `AdaptiveWeighting` (que solo cuenta aciertos por agente), aquí
    el ajuste es conjunto: penaliza agentes redundantes y premia a los que aportan
    información única. Durante el *warmup* (pocas muestras en un régimen) delega en
    una estrategia de respaldo.
    """

    def __init__(
        self,
        fallback: WeightingStrategy | None = None,
        base: float = 1.0,
        lr: float = 0.05,
        warmup: int = 30,
    ) -> None:
        self.fallback = fallback or AdaptiveWeighting()
        self.base = base
        self.lr = lr
        self.warmup = warmup
        self._models: Dict[str, _OnlineLogistic] = {}
        self._counts: Dict[str, int] = defaultdict(int)
        self._agent_index: Dict[str, int] | None = None

    def _ensure_index(self, decisions: Sequence) -> None:
        if self._agent_index is None:
            names = sorted({d.agent_name for d in decisions})
            self._agent_index = {name: i for i, name in enumerate(names)}

    def _vector(self, decisions: Sequence) -> np.ndarray:
        assert self._agent_index is not None
        x = np.zeros(len(self._agent_index))
        for d in decisions:
            i = self._agent_index.get(d.agent_name)
            if i is not None:
                x[i] = d.signal.sign * (d.confidence / 100.0)
        return x

    def observe(self, decisions: Sequence, regime: MarketRegime, profitable: bool) -> None:
        self._ensure_index(decisions)
        key = regime.key
        model = self._models.get(key)
        if model is None:
            model = _OnlineLogistic(len(self._agent_index), lr=self.lr)
            self._models[key] = model
        model.update(self._vector(decisions), 1.0 if profitable else 0.0)
        self._counts[key] += 1
        # Mantener el respaldo "caliente" para el warmup.
        for d in decisions:
            if d.signal is not SignalType.WAIT:
                self.fallback.update(d.agent_name, regime, profitable)

    def weight_for(self, agent_name: str, regime: MarketRegime) -> float:
        key = regime.key
        if (
            self._agent_index is None
            or self._counts[key] < self.warmup
            or key not in self._models
            or agent_name not in self._agent_index
        ):
            return self.fallback.weight_for(agent_name, regime)
        coef = abs(self._models[key].w[self._agent_index[agent_name]])
        return max(0.0, self.base * (0.5 + coef))

    def update(self, agent_name: str, regime: MarketRegime, correct: bool) -> None:
        # La retroalimentación real llega por observe(); mantenemos el respaldo.
        self.fallback.update(agent_name, regime, correct)
