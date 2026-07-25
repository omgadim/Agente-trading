"""Tests de features y modelos de ML."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_system.data import SimulatedDataFeed
from trading_system.ml.features import (
    FEATURE_NAMES,
    build_dataset,
    compute_feature_frame,
    last_feature_vector,
    make_labels,
)
from trading_system.ml.model import (
    LogisticRegressionModel,
    ModelError,
    create_model,
)


@pytest.fixture
def base_df():
    return SimulatedDataFeed(base_price=2000, drift=0.05, volatility=1.0,
                             bars=800, seed=10).generate()


def test_feature_frame_columns(base_df):
    feats = compute_feature_frame(base_df)
    assert list(feats.columns) == FEATURE_NAMES


def test_labels_are_binary_and_future(base_df):
    labels = make_labels(base_df, horizon=5)
    # Las últimas 5 barras no tienen etiqueta (futuro desconocido).
    assert labels.iloc[-5:].isna().all()
    valid = labels.dropna()
    assert set(np.unique(valid)) <= {0.0, 1.0}


def test_build_dataset_no_nan(base_df):
    X, y, names = build_dataset(base_df, horizon=5)
    assert names == FEATURE_NAMES
    assert X.shape[1] == len(FEATURE_NAMES)
    assert not np.isnan(X).any()
    assert len(X) == len(y)


def test_last_feature_vector_no_nan(base_df):
    v = last_feature_vector(base_df)
    assert v.shape == (len(FEATURE_NAMES),)
    assert not np.isnan(v).any()


def test_logistic_learns_separable_problem():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(400, 3))
    # Etiqueta linealmente separable en la primera feature.
    y = (X[:, 0] + 0.2 * rng.normal(size=400) > 0).astype(float)
    model = LogisticRegressionModel(lr=0.5, epochs=800).fit(X, y)
    preds = (model.predict_proba(X) > 0.5).astype(float)
    acc = float(np.mean(preds == y))
    assert acc > 0.85


def test_predict_proba_bounds_and_errors():
    model = LogisticRegressionModel()
    with pytest.raises(ModelError):
        model.predict_proba(np.zeros((1, 3)))  # sin entrenar
    X = np.random.default_rng(1).normal(size=(50, 2))
    with pytest.raises(ModelError):
        model.fit(X, np.ones(50))  # una sola clase
    y = (X[:, 0] > 0).astype(float)
    model.fit(X, y)
    p = model.predict_proba(X)
    assert (p >= 0).all() and (p <= 1).all()


def test_create_model_defaults_to_logistic():
    assert create_model("desconocido").name == "logistic"
    assert create_model("logistic").name == "logistic"


def test_sklearn_and_xgboost_adapters_optional():
    """Si sklearn/xgboost están instalados, entrenan e infieren; si no, se omiten."""
    rng = np.random.default_rng(2)
    X = rng.normal(size=(200, 3))
    y = (X[:, 0] + X[:, 1] > 0).astype(float)
    for name, module in (("gboosting", "sklearn"), ("xgboost", "xgboost")):
        pytest.importorskip(module)
        model = create_model(name).fit(X, y)
        p = model.predict_proba(X)
        assert (p >= 0).all() and (p <= 1).all()
