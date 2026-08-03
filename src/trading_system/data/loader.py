"""Carga de datos históricos OHLCV desde CSV (p. ej. export de MetaTrader 5).

Normaliza distintos formatos de columnas a un DataFrame OHLCV limpio con índice
temporal, listo para el backtester o para `build_market_data`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from ..core.exceptions import DataError

# Alias habituales de nombres de columna (en minúsculas).
_ALIASES = {
    "date": "time", "datetime": "time", "time": "time", "timestamp": "time",
    "open": "open", "high": "high", "low": "low", "close": "close",
    "volume": "volume", "vol": "volume",
    "tick_volume": "tick_volume", "tickvol": "tick_volume", "real_volume": "volume",
}
_REQUIRED = ("time", "open", "high", "low", "close")


def load_ohlcv_csv(
    path: str | Path,
    time_col: Optional[str] = None,
    sep: str = ",",
    tz: Optional[str] = None,
) -> pd.DataFrame:
    """Carga un CSV OHLCV a un DataFrame estándar.

    - Reconoce nombres de columna comunes (Date/Time, Open/High/Low/Close,
      Volume/Tick_Volume) sin distinguir mayúsculas.
    - Si `Volume` está ausente o es todo ceros, usa `Tick_Volume` (típico en
      Forex/CFD de MT5, donde el volumen real no existe).
    - Devuelve columnas open/high/low/close/volume, índice temporal ordenado y
      sin duplicados.
    """
    p = Path(path)
    if not p.exists():
        raise DataError(f"No existe el fichero: {p}")

    if p.suffix.lower() in (".xlsx", ".xls"):
        try:
            df = pd.read_excel(p)
        except ImportError as exc:  # pragma: no cover - depende del entorno
            raise DataError(
                "Leer .xlsx requiere openpyxl (`pip install openpyxl`)."
            ) from exc
    else:
        df = pd.read_csv(p, sep=sep)
    if df.empty:
        raise DataError(f"Fichero vacío: {p}")

    # Normaliza nombres de columna.
    rename = {}
    for col in df.columns:
        key = col.strip().lower()
        if time_col and col == time_col:
            rename[col] = "time"
        elif key in _ALIASES:
            rename[col] = _ALIASES[key]
    df = df.rename(columns=rename)

    missing = [c for c in _REQUIRED if c not in df.columns]
    if missing:
        raise DataError(f"Faltan columnas {missing} en {p.name}. Columnas: {list(df.columns)}")

    # Volumen: usa 'volume' si aporta información; si no, 'tick_volume'.
    if "volume" not in df.columns or df["volume"].fillna(0).abs().sum() == 0:
        if "tick_volume" in df.columns:
            df["volume"] = df["tick_volume"]
        else:
            df["volume"] = 1.0

    df["time"] = pd.to_datetime(df["time"])
    df = df.set_index("time").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    if tz is not None:
        df.index = df.index.tz_localize(tz).tz_convert("UTC").tz_localize(None)

    out = df[["open", "high", "low", "close", "volume"]].astype(float)
    if out.isna().any().any():
        out = out.dropna()
    if len(out) < 2:
        raise DataError("El CSV no contiene suficientes filas OHLCV válidas")
    return out
