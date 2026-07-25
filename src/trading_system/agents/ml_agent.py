"""Agente de Machine Learning (Fase 4).

Aprende de la propia serie: construye features backward-looking, entrena un
modelo (logístico por defecto; XGBoost/GB si están disponibles) sobre el histórico
con etiquetas de retorno futuro, y predice la dirección de la última barra. El
reentrenamiento periódico sobre ventana expansiva equivale a walk-forward y no
introduce look-ahead (la etiqueta de la barra predicha nunca se usa).
"""
from __future__ import annotations

import numpy as np

from ..core import AgentDecision, BaseAgent, MarketData, SignalType, Timeframe, register_agent
from ..ml.features import build_dataset, last_feature_vector
from ..ml.model import Model, ModelError, create_model
from .helpers import atr_sl_tp


@register_agent("machine_learning")
class MachineLearningAgent(BaseAgent):
    """Predicción direccional supervisada con reentrenamiento online."""

    category = "ml"

    def __init__(self, name: str, config=None) -> None:
        super().__init__(name, config)
        self.model_name = self.config.get("model", "logistic")
        self.horizon = int(self.config.get("horizon", 5))
        self.margin = float(self.config.get("margin", 0.10))
        self.retrain_every = int(self.config.get("retrain_every", 50))
        self.min_train = int(self.config.get("min_train", 150))
        self._tf_name = self.config.get("timeframe")  # None => primario
        self._model: Model | None = None
        self._calls = 0
        self._n_train = 0

    def _frame(self, md: MarketData):
        if self._tf_name:
            tf = Timeframe[self._tf_name]
            if md.has(tf):
                return md.frame(tf)
        return md.frame(md.primary_tf)

    def analyze(self, md: MarketData) -> AgentDecision:
        df = self._frame(md)
        X, y, _ = build_dataset(df, self.horizon)
        if len(X) < self.min_train or len(np.unique(y)) < 2:
            return self._wait(f"Datos insuficientes para ML (n={len(X)})")

        # (Re)entrenamiento periódico sobre la ventana expansiva disponible.
        if self._model is None or self._calls % self.retrain_every == 0:
            try:
                self._model = create_model(self.model_name).fit(X, y)
                self._n_train = len(X)
            except ModelError as exc:
                return self._wait(f"Entrenamiento ML falló: {exc}")
        self._calls += 1

        prob_up = float(self._model.predict_proba(last_feature_vector(df))[0])

        if prob_up > 0.5 + self.margin:
            signal = SignalType.BUY
            confidence = min(100.0, (prob_up - 0.5) * 200.0)
        elif prob_up < 0.5 - self.margin:
            signal = SignalType.SELL
            confidence = min(100.0, (0.5 - prob_up) * 200.0)
        else:
            return self._decision(
                SignalType.WAIT, 0.0,
                f"ML indeciso (P_subida={prob_up:.2f}, margen ±{self.margin})",
                estimated_risk=50.0, prob_up=prob_up,
            )

        sl, tp = atr_sl_tp(md.price, md.regime.atr, signal)
        return self._decision(
            signal, confidence,
            f"{self.model_name}: P_subida={prob_up:.2f} (n_train={self._n_train}, h={self.horizon})",
            estimated_risk=45.0, stop_loss=sl, take_profit=tp,
            prob_up=prob_up, model=self.model_name,
        )
