"""Fuentes de datos: interface y una implementación simulada.

La `MT5DataFeed` real se implementa en la Fase 3 (adapter sobre MetaTrader5). El
`SimulatedDataFeed` permite desarrollar y testear toda la lógica sin broker.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Iterable, Optional

import numpy as np
import pandas as pd

from ..core.enums import Timeframe, TrendDirection, VolatilityRegime
from ..core.market_data import MarketData, MarketRegime
from . import indicators as ind


class DataFeed(ABC):
    """Contrato de una fuente de datos multi-timeframe."""

    @abstractmethod
    def get_market_data(self, symbol: str) -> MarketData:
        """Devuelve la instantánea de mercado actual."""


def compute_regime(df: pd.DataFrame, atr_period: int = 14) -> MarketRegime:
    """Deriva el régimen (tendencia + volatilidad) desde un DataFrame OHLCV.

    - Tendencia: pendiente de EMA rápida vs lenta + ADX.
    - Volatilidad: ATR relativo al precio comparado con su media histórica.
    """
    if len(df) < atr_period + 2:
        return MarketRegime()

    close = df["close"]
    ema_fast = ind.ema(close, 20)
    ema_slow = ind.ema(close, 50)
    adx_val = ind.adx(df, atr_period).iloc[-1]
    atr_series = ind.atr(df, atr_period)
    atr_val = float(atr_series.iloc[-1])

    # Tendencia
    if np.isnan(adx_val) or adx_val < 20:
        trend = TrendDirection.RANGE
    elif ema_fast.iloc[-1] > ema_slow.iloc[-1]:
        trend = TrendDirection.UP
    else:
        trend = TrendDirection.DOWN

    # Volatilidad: ATR% actual vs mediana de ATR%
    atr_pct = atr_series / close
    med = float(atr_pct.median())
    cur = float(atr_pct.iloc[-1]) if not np.isnan(atr_pct.iloc[-1]) else med
    if med <= 0:
        vol = VolatilityRegime.NORMAL
    elif cur > 1.4 * med:
        vol = VolatilityRegime.HIGH
    elif cur < 0.6 * med:
        vol = VolatilityRegime.LOW
    else:
        vol = VolatilityRegime.NORMAL

    return MarketRegime(trend=trend, volatility=vol, atr=atr_val)


def resample_ohlcv(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Remuestrea un DataFrame OHLCV a un timeframe superior."""
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    return df.resample(f"{minutes}min").agg(agg).dropna()


def build_market_data(
    base_df: pd.DataFrame,
    symbol: str = "XAUUSD",
    base_minutes: int = 5,
    timeframes: Iterable[Timeframe] = (
        Timeframe.M5,
        Timeframe.M15,
        Timeframe.H1,
        Timeframe.H4,
    ),
    spread: float = 0.2,
) -> MarketData:
    """Construye un `MarketData` multi-timeframe desde un DataFrame base.

    El DataFrame base debe tener índice temporal y columnas OHLCV en el timeframe
    más fino (`base_minutes`). Los timeframes superiores se derivan por remuestreo.
    Usado por el backtester para reconstruir el mercado en cada paso.
    """
    frames: Dict[Timeframe, pd.DataFrame] = {}
    for tf in timeframes:
        frames[tf] = base_df.copy() if tf.minutes == base_minutes else resample_ohlcv(base_df, tf.minutes)
    frames = {tf: f for tf, f in frames.items() if not f.empty}

    primary = frames[min(frames, key=lambda t: t.minutes)]
    regime = compute_regime(frames.get(Timeframe.H1, primary))
    return MarketData(
        symbol=symbol,
        frames=frames,
        price=float(primary["close"].iloc[-1]),
        spread=spread,
        regime=regime,
    )


class SimulatedDataFeed(DataFeed):
    """Genera series OHLCV sintéticas reproducibles para tests/backtest.

    Modela un precio con deriva (tendencia) + ruido gaussiano y construye los
    timeframes superiores por remuestreo del más fino.
    """

    def __init__(
        self,
        base_price: float = 2000.0,
        drift: float = 0.02,
        volatility: float = 1.5,
        bars: int = 500,
        seed: Optional[int] = 42,
        timeframes: Iterable[Timeframe] = (
            Timeframe.M5,
            Timeframe.M15,
            Timeframe.H1,
            Timeframe.H4,
        ),
    ) -> None:
        self.base_price = base_price
        self.drift = drift
        self.volatility = volatility
        self.bars = bars
        self.seed = seed
        self.timeframes = tuple(timeframes)

    def _generate_base(self) -> pd.DataFrame:
        rng = np.random.default_rng(self.seed)
        n = self.bars
        returns = rng.normal(self.drift, self.volatility, size=n)
        close = self.base_price + np.cumsum(returns)
        close = np.maximum(close, 1.0)
        open_ = np.concatenate([[self.base_price], close[:-1]])
        noise = np.abs(rng.normal(0.0, self.volatility, size=n))
        high = np.maximum(open_, close) + noise
        low = np.minimum(open_, close) - noise
        volume = rng.integers(500, 5000, size=n).astype(float)

        idx = pd.date_range(
            end=pd.Timestamp.now("UTC").tz_localize(None).floor("min"),
            periods=n,
            freq="5min",
        )
        return pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=idx,
        )

    def generate(self) -> pd.DataFrame:
        """Devuelve la serie base OHLCV (timeframe más fino) generada."""
        return self._generate_base()

    def get_market_data(self, symbol: str = "XAUUSD") -> MarketData:
        base = self._generate_base()
        return build_market_data(base, symbol=symbol, base_minutes=5, timeframes=self.timeframes)
