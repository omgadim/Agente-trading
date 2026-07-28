"""Features v2 para ML: multi-timeframe + etiqueta triple-barrera.

Dos mejoras sobre `features.py`:
  1. Contexto MULTI-TIMEFRAME: además de las features del marco base (M30), añade
     la tendencia de H1 y H4 (EMA20/50, RSI, ADX). Se remuestrea el propio marco
     base y se reindexa con ffill + shift(1) para usar SOLO barras superiores ya
     CERRADAS (sin look-ahead).
  2. Etiqueta TRIPLE-BARRERA alineada al SL/TP real: para cada barra, mira las
     siguientes `horizon` barras y etiqueta 1 si toca antes +tp·ATR (gana) y 0 si
     toca antes -sl·ATR (pierde). Así el modelo aprende lo que de verdad da dinero,
     no un "sube/baja" cualquiera.

Todo backward-looking. La misma función sirve para entrenamiento e inferencia.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd

from ..data import indicators as ind
from .features import FEATURE_NAMES as BASE_FEATURES, compute_feature_frame

# Features añadidas por cada timeframe superior.
_HTF_SUFFIX = ["ema_fs", "rsi", "adx", "dist_ema"]
HTF_RULES = {"H1": "1h", "H4": "4h"}
FEATURE_NAMES_V2: List[str] = list(BASE_FEATURES) + [
    f"{tf.lower()}_{s}" for tf in HTF_RULES for s in _HTF_SUFFIX
]


def _htf_features(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Features de tendencia de un timeframe superior, reindexadas al índice base
    con ffill + shift(1) (solo barras superiores CERRADAS -> sin look-ahead)."""
    o = df["open"].resample(rule, label="right", closed="right").first()
    h = df["high"].resample(rule, label="right", closed="right").max()
    low = df["low"].resample(rule, label="right", closed="right").min()
    c = df["close"].resample(rule, label="right", closed="right").last()
    htf = pd.DataFrame({"open": o, "high": h, "low": low, "close": c}).dropna()
    if len(htf) < 55:
        return pd.DataFrame(index=df.index, columns=_HTF_SUFFIX, dtype=float)
    ema20 = ind.ema(htf["close"], 20); ema50 = ind.ema(htf["close"], 50)
    atr = ind.atr(htf, 14); eps = 1e-9
    f = pd.DataFrame(index=htf.index)
    f["ema_fs"] = ema20 / ema50 - 1.0
    f["rsi"] = ind.rsi(htf["close"], 14) / 100.0
    f["adx"] = ind.adx(htf, 14) / 100.0
    f["dist_ema"] = (htf["close"] - ema20) / (atr + eps)
    f = f.shift(1)  # usar solo la barra superior YA cerrada
    return f.reindex(df.index, method="ffill")


def compute_feature_frame_v2(df: pd.DataFrame) -> pd.DataFrame:
    base = compute_feature_frame(df)
    parts = [base]
    for tf, rule in HTF_RULES.items():
        htf = _htf_features(df, rule)
        htf.columns = [f"{tf.lower()}_{s}" for s in _HTF_SUFFIX]
        parts.append(htf)
    return pd.concat(parts, axis=1)[FEATURE_NAMES_V2]


def triple_barrier_labels(df: pd.DataFrame, horizon: int = 12,
                          barrier_mult: float = 1.5) -> pd.Series:
    """Etiqueta de DIRECCIÓN con barreras SIMÉTRICAS (±barrier·ATR): 1 si el precio
    toca antes la barrera de ARRIBA (movimiento alcista gana), 0 si toca antes la
    de ABAJO. NaN si no toca ninguna dentro de `horizon` (barrera vertical) o falta
    futuro. Simétrica -> clases equilibradas y señal direccional limpia; la relación
    riesgo/beneficio 1:2.5 la aplica el risk manager, no la etiqueta."""
    atr = ind.atr(df, 14).to_numpy()
    high = df["high"].to_numpy(); low = df["low"].to_numpy(); close = df["close"].to_numpy()
    n = len(df); out = np.full(n, np.nan)
    for i in range(n - 1):
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        up = close[i] + barrier_mult * a; dn = close[i] - barrier_mult * a
        end = min(n, i + 1 + horizon)
        lab = np.nan
        for j in range(i + 1, end):
            hit_up = high[j] >= up; hit_dn = low[j] <= dn
            if hit_up and hit_dn:      # ambas en la misma vela: indeciso
                lab = np.nan; break
            if hit_up:
                lab = 1.0; break
            if hit_dn:
                lab = 0.0; break
        out[i] = lab
    return pd.Series(out, index=df.index)


def build_dataset_v2(df: pd.DataFrame, horizon: int = 12,
                     barrier_mult: float = 1.5
                     ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    feats = compute_feature_frame_v2(df)
    labels = triple_barrier_labels(df, horizon, barrier_mult)
    data = feats.copy(); data["_label"] = labels
    data = data.replace([np.inf, -np.inf], np.nan).dropna()
    X = data[FEATURE_NAMES_V2].to_numpy(dtype=float)
    y = data["_label"].to_numpy(dtype=float)
    return X, y, FEATURE_NAMES_V2


def last_feature_vector_v2(df: pd.DataFrame) -> np.ndarray:
    feats = compute_feature_frame_v2(df).replace([np.inf, -np.inf], np.nan)
    return feats[FEATURE_NAMES_V2].iloc[[-1]].fillna(0.0).to_numpy(dtype=float)
