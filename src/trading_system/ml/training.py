"""Entrenamiento y validación walk-forward de los modelos."""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from .features import build_dataset
from .model import Model, ModelError, create_model


def walk_forward_eval(
    df: pd.DataFrame,
    model_name: str = "logistic",
    horizon: int = 5,
    folds: int = 5,
) -> Dict[str, object]:
    """Evaluación *walk-forward* con ventana expansiva (sin look-ahead).

    Divide la serie en `folds`+1 tramos cronológicos; entrena con todo lo anterior
    y evalúa en el tramo siguiente. Devuelve accuracy global, nº de muestras de
    test y accuracy por fold.
    """
    X, y, _ = build_dataset(df, horizon)
    n = len(X)
    if n < (folds + 1) * 30:
        raise ModelError(f"Muestras insuficientes para {folds} folds (n={n})")

    bounds = np.linspace(0, n, folds + 2, dtype=int)
    correct = 0
    total = 0
    fold_acc: List[float] = []

    for k in range(1, folds + 1):
        train_end = bounds[k]
        test_end = bounds[k + 1]
        X_tr, y_tr = X[:train_end], y[:train_end]
        X_te, y_te = X[train_end:test_end], y[train_end:test_end]
        if len(np.unique(y_tr)) < 2 or len(X_te) == 0:
            continue
        model = create_model(model_name).fit(X_tr, y_tr)
        preds = (model.predict_proba(X_te) > 0.5).astype(float)
        c = int(np.sum(preds == y_te))
        correct += c
        total += len(y_te)
        fold_acc.append(round(c / len(y_te), 4))

    accuracy = round(correct / total, 4) if total else 0.0
    return {
        "model": model_name,
        "accuracy": accuracy,
        "n_test": total,
        "fold_accuracy": fold_acc,
        "baseline": round(float(max(np.mean(y), 1 - np.mean(y))), 4),
    }


def train_model(df: pd.DataFrame, model_name: str = "logistic", horizon: int = 5) -> Model:
    """Entrena un modelo con toda la serie disponible."""
    X, y, _ = build_dataset(df, horizon)
    return create_model(model_name).fit(X, y)
