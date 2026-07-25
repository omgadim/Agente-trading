"""Contenedor de datos de mercado multi-timeframe y régimen."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

import pandas as pd

from .enums import Timeframe, TrendDirection, VolatilityRegime
from .exceptions import DataError

# Columnas OHLCV esperadas en cada DataFrame de timeframe.
OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


@dataclass
class MarketRegime:
    """Contexto de mercado calculado una vez por ciclo."""

    trend: TrendDirection = TrendDirection.RANGE
    volatility: VolatilityRegime = VolatilityRegime.NORMAL
    atr: float = 0.0

    @property
    def key(self) -> str:
        """Clave compacta usada por la ponderación adaptativa."""
        return f"{self.trend.value}:{self.volatility.value}"


@dataclass
class MarketData:
    """Instantánea del mercado en múltiples marcos temporales.

    `frames` mapea cada `Timeframe` a un DataFrame OHLCV ordenado
    cronológicamente (la última fila es la vela más reciente).
    """

    symbol: str
    frames: Dict[Timeframe, pd.DataFrame]
    price: float = 0.0
    spread: float = 0.0
    regime: MarketRegime = field(default_factory=MarketRegime)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.frames:
            raise DataError("MarketData requiere al menos un timeframe")
        for tf, df in self.frames.items():
            missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
            if missing:
                raise DataError(f"{tf.name}: faltan columnas {missing}")
        if not self.price:
            # Precio por defecto: último cierre del timeframe más fino disponible.
            finest = min(self.frames, key=lambda t: t.minutes)
            self.price = float(self.frames[finest]["close"].iloc[-1])

    def frame(self, tf: Timeframe) -> pd.DataFrame:
        """Devuelve el DataFrame de un timeframe o lanza DataError."""
        if tf not in self.frames:
            raise DataError(f"Timeframe {tf.name} no disponible")
        return self.frames[tf]

    def has(self, tf: Timeframe) -> bool:
        return tf in self.frames

    def closes(self, tf: Timeframe) -> pd.Series:
        return self.frame(tf)["close"]

    @property
    def primary_tf(self) -> Timeframe:
        """Timeframe más fino disponible (el operativo por defecto)."""
        return min(self.frames, key=lambda t: t.minutes)
