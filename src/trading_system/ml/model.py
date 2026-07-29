"""Modelos de clasificación con una interfaz común.

`LogisticRegressionModel` está implementado en numpy puro y es el modelo por
defecto: garantiza que el sistema funcione y se testee sin dependencias pesadas.
`SklearnGBModel` y `XGBoostModel` son adapters opcionales (import perezoso) que se
usan en producción si las librerías están instaladas.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from ..core.exceptions import TradingSystemError


class ModelError(TradingSystemError):
    """Error de entrenamiento o inferencia de un modelo."""


class Model(ABC):
    """Contrato de un clasificador binario probabilístico."""

    name: str = "model"

    @abstractmethod
    def fit(self, X: np.ndarray, y: np.ndarray) -> "Model": ...

    @abstractmethod
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Devuelve P(clase=1) para cada fila de X."""


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


class LogisticRegressionModel(Model):
    """Regresión logística por descenso de gradiente (numpy puro).

    Estandariza las features internamente (media/desv. del entrenamiento) y aplica
    regularización L2. Sin dependencias externas.
    """

    name = "logistic"

    def __init__(self, lr: float = 0.1, epochs: int = 400, l2: float = 1e-3) -> None:
        self.lr = lr
        self.epochs = epochs
        self.l2 = l2
        self._w: np.ndarray | None = None
        self._b: float = 0.0
        self._mu: np.ndarray | None = None
        self._sigma: np.ndarray | None = None

    def _standardize(self, X: np.ndarray) -> np.ndarray:
        return (X - self._mu) / self._sigma

    def fit(self, X: np.ndarray, y: np.ndarray) -> "LogisticRegressionModel":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        if X.ndim != 2 or len(X) != len(y):
            raise ModelError("Dimensiones de X/y inválidas")
        if len(np.unique(y)) < 2:
            raise ModelError("Se requieren ambas clases para entrenar")

        self._mu = X.mean(axis=0)
        self._sigma = X.std(axis=0)
        self._sigma[self._sigma == 0] = 1.0
        Xs = self._standardize(X)

        n, d = Xs.shape
        self._w = np.zeros(d)
        self._b = 0.0
        for _ in range(self.epochs):
            p = _sigmoid(Xs @ self._w + self._b)
            grad_w = Xs.T @ (p - y) / n + self.l2 * self._w
            grad_b = float(np.mean(p - y))
            self._w -= self.lr * grad_w
            self._b -= self.lr * grad_b
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self._w is None:
            raise ModelError("El modelo no está entrenado")
        X = np.atleast_2d(np.asarray(X, dtype=float))
        return _sigmoid(self._standardize(X) @ self._w + self._b)


class SklearnGBModel(Model):
    """Adapter de sklearn.ensemble.GradientBoostingClassifier (opcional)."""

    name = "gboosting"

    def __init__(self, **kwargs) -> None:
        self._kwargs = kwargs or {"n_estimators": 150, "max_depth": 3, "learning_rate": 0.05}
        self._clf = None

    def fit(self, X, y) -> "SklearnGBModel":
        try:
            from sklearn.ensemble import GradientBoostingClassifier
        except ImportError as exc:  # pragma: no cover - depende del entorno
            raise ModelError("scikit-learn no está instalado") from exc
        if len(np.unique(y)) < 2:
            raise ModelError("Se requieren ambas clases para entrenar")
        self._clf = GradientBoostingClassifier(**self._kwargs).fit(X, y)
        return self

    def predict_proba(self, X) -> np.ndarray:
        if self._clf is None:
            raise ModelError("El modelo no está entrenado")
        return self._clf.predict_proba(np.atleast_2d(X))[:, 1]


class XGBoostModel(Model):
    """Adapter de xgboost.XGBClassifier (opcional)."""

    name = "xgboost"

    def __init__(self, **kwargs) -> None:
        self._kwargs = kwargs or {
            "n_estimators": 200, "max_depth": 4, "learning_rate": 0.05,
            "subsample": 0.8, "eval_metric": "logloss",
        }
        self._clf = None

    def fit(self, X, y) -> "XGBoostModel":
        try:
            from xgboost import XGBClassifier
        except ImportError as exc:  # pragma: no cover - depende del entorno
            raise ModelError("xgboost no está instalado") from exc
        if len(np.unique(y)) < 2:
            raise ModelError("Se requieren ambas clases para entrenar")
        self._clf = XGBClassifier(**self._kwargs).fit(X, y)
        return self

    def predict_proba(self, X) -> np.ndarray:
        if self._clf is None:
            raise ModelError("El modelo no está entrenado")
        return self._clf.predict_proba(np.atleast_2d(X))[:, 1]


class LorentzianModel(Model):
    """Clasificación Lorentziana (k-NN con distancia Lorentziana).

    Como el clasificador de TradingView (jdehorty): estandariza las features y usa
    la distancia de Lorentz `d(x,y)=Σ log(1+|x_i-y_i|)`, que "encoge" las grandes
    diferencias y es más robusta al ruido/outliers que la euclídea. La probabilidad
    es la fracción de los `k` vecinos más cercanos que son clase 1. Sin librerías
    externas (numpy puro), ligero para el VPS.
    """

    name = "lorentzian"

    def __init__(self, k: int = 8) -> None:
        self.k = k
        self._X: np.ndarray | None = None
        self._y: np.ndarray | None = None
        self._mu: np.ndarray | None = None
        self._sigma: np.ndarray | None = None

    def fit(self, X, y) -> "LorentzianModel":
        X = np.asarray(X, dtype=float); y = np.asarray(y, dtype=float)
        if X.ndim != 2 or len(X) != len(y):
            raise ModelError("Dimensiones de X/y inválidas")
        if len(np.unique(y)) < 2:
            raise ModelError("Se requieren ambas clases para entrenar")
        self._mu = X.mean(axis=0); self._sigma = X.std(axis=0)
        self._sigma[self._sigma == 0] = 1.0
        self._X = (X - self._mu) / self._sigma
        self._y = y
        return self

    def predict_proba(self, X) -> np.ndarray:
        if self._X is None:
            raise ModelError("El modelo no está entrenado")
        Xs = (np.atleast_2d(np.asarray(X, dtype=float)) - self._mu) / self._sigma
        k = min(self.k, len(self._X))
        out = np.empty(len(Xs))
        for i, x in enumerate(Xs):
            dist = np.log1p(np.abs(self._X - x)).sum(axis=1)
            nn = np.argpartition(dist, k - 1)[:k]
            out[i] = float(self._y[nn].mean())
        return out


_MODELS = {
    "logistic": LogisticRegressionModel,
    "gboosting": SklearnGBModel,
    "xgboost": XGBoostModel,
    "lorentzian": LorentzianModel,
}


def create_model(name: str = "logistic", **kwargs) -> Model:
    """Fábrica de modelos. Ante un nombre desconocido, usa la logística."""
    cls = _MODELS.get(name, LogisticRegressionModel)
    return cls(**kwargs)
