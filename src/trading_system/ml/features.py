"""Ingeniería de features para los modelos de Machine Learning.

Todas las features son *backward-looking* (usan solo información hasta la barra t)
para evitar look-ahead. La misma función construye la matriz de entrenamiento y el
vector de la última barra para inferencia en vivo.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd

from ..data import indicators as ind

# Nombre estable de las features (orden garantizado).
FEATURE_NAMES: List[str] = [
    "ret_1", "ret_5", "ret_10",
    "rsi_14", "macd_hist_norm", "atr_pct", "adx_14",
    "ema_fast_slow", "dist_ema20_atr", "roc_10",
    "body_pct", "range_pct", "vol_ratio",
]

# Ventana mínima de calentamiento para que la última fila no tenga NaN.
WARMUP = 60


def compute_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Devuelve un DataFrame de features por barra, alineado con `df`."""
    close = df["close"]
    open_ = df["open"]
    high = df["high"]
    low = df["low"]
    eps = 1e-9

    ema20 = ind.ema(close, 20)
    ema50 = ind.ema(close, 50)
    atr = ind.atr(df, 14)
    macd = ind.macd(close)
    vol = df["volume"] if "volume" in df else pd.Series(1.0, index=df.index)

    feats = pd.DataFrame(index=df.index)
    feats["ret_1"] = close.pct_change(1)
    feats["ret_5"] = close.pct_change(5)
    feats["ret_10"] = close.pct_change(10)
    feats["rsi_14"] = ind.rsi(close, 14) / 100.0
    feats["macd_hist_norm"] = macd["hist"] / close
    feats["atr_pct"] = atr / close
    feats["adx_14"] = ind.adx(df, 14) / 100.0
    feats["ema_fast_slow"] = ema20 / ema50 - 1.0
    feats["dist_ema20_atr"] = (close - ema20) / (atr + eps)
    feats["roc_10"] = ind.roc(close, 10) / 100.0
    feats["body_pct"] = (close - open_) / ((high - low) + eps)
    feats["range_pct"] = (high - low) / close
    feats["vol_ratio"] = vol / (ind.sma(vol, 20) + eps)
    return feats[FEATURE_NAMES]


def make_labels(df: pd.DataFrame, horizon: int = 5) -> pd.Series:
    """Etiqueta binaria: 1 si el precio sube tras `horizon` barras, 0 si baja.

    Las últimas `horizon` barras quedan NaN (su futuro es desconocido) y se
    descartan en el entrenamiento — nunca en la inferencia.
    """
    future_ret = df["close"].shift(-horizon) / df["close"] - 1.0
    label = (future_ret > 0).astype(float)
    label[future_ret.isna()] = np.nan
    return label


def build_dataset(
    df: pd.DataFrame, horizon: int = 5
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Construye (X, y, nombres) descartando warmup y cola sin etiqueta."""
    feats = compute_feature_frame(df)
    labels = make_labels(df, horizon)
    data = feats.copy()
    data["_label"] = labels
    data = data.replace([np.inf, -np.inf], np.nan).dropna()
    X = data[FEATURE_NAMES].to_numpy(dtype=float)
    y = data["_label"].to_numpy(dtype=float)
    return X, y, FEATURE_NAMES


def last_feature_vector(df: pd.DataFrame) -> np.ndarray:
    """Vector de features de la última barra (para inferencia). NaN -> 0.0."""
    feats = compute_feature_frame(df)
    row = feats.iloc[-1].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return row.to_numpy(dtype=float)
