"""Motor compartido de estructura de mercado y liquidez (Smart Money).

Detecta las primitivas de price action institucional que consumen los agentes de
la Fase 2: swings, estructura (BOS/CHoCH), Fair Value Gaps, Order Blocks, pools de
liquidez, barridos (sweeps) y zonas premium/discount.

Todas las funciones trabajan sobre posiciones enteras (0..n-1) del DataFrame para
ser deterministas y fáciles de testear con velas sintéticas.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from . import indicators as ind


# --------------------------------------------------------------------------- #
#  Estructuras de datos
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Swing:
    """Pivote de mercado."""

    pos: int
    price: float
    kind: str  # 'high' | 'low'


@dataclass(frozen=True)
class FVG:
    """Fair Value Gap (imbalance de 3 velas)."""

    kind: str  # 'bullish' | 'bearish'
    top: float
    bottom: float
    pos: int  # posición de la 3ª vela

    @property
    def mid(self) -> float:
        return (self.top + self.bottom) / 2.0

    @property
    def size(self) -> float:
        return self.top - self.bottom

    def contains(self, price: float) -> bool:
        return self.bottom <= price <= self.top


@dataclass(frozen=True)
class OrderBlock:
    """Order Block: última vela contraria antes de un impulso que rompe estructura."""

    kind: str  # 'bullish' | 'bearish'
    top: float
    bottom: float
    pos: int

    @property
    def mid(self) -> float:
        return (self.top + self.bottom) / 2.0

    def contains(self, price: float) -> bool:
        return self.bottom <= price <= self.top


@dataclass(frozen=True)
class LiquidityPool:
    """Zona de liquidez (máximos/mínimos iguales agrupados)."""

    price: float
    kind: str  # 'buy_side' (sobre el precio) | 'sell_side' (bajo el precio)
    count: int


@dataclass(frozen=True)
class StructureState:
    """Estado estructural resumido."""

    trend: str  # 'bullish' | 'bearish' | 'undefined'
    event: str  # 'BOS' | 'CHoCH' | 'none'
    level: Optional[float] = None


@dataclass(frozen=True)
class Sweep:
    """Barrido de liquidez: mecha que excede un swing y cierra de vuelta."""

    kind: str  # 'bullish' (barre mínimos -> señal de compra) | 'bearish'
    level: float
    pos: int


# --------------------------------------------------------------------------- #
#  Detectores
# --------------------------------------------------------------------------- #
def find_swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> List[Swing]:
    """Devuelve los pivotes (máximos y mínimos) ordenados por posición."""
    highs_mask = ind.swing_highs(df["high"], left, right).to_numpy()
    lows_mask = ind.swing_lows(df["low"], left, right).to_numpy()
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    swings: List[Swing] = []
    for i in range(len(df)):
        if highs_mask[i]:
            swings.append(Swing(i, float(high[i]), "high"))
        if lows_mask[i]:
            swings.append(Swing(i, float(low[i]), "low"))
    swings.sort(key=lambda s: s.pos)
    return swings


def find_fvgs(df: pd.DataFrame, min_atr_frac: float = 0.0) -> List[FVG]:
    """Detecta Fair Value Gaps de 3 velas.

    Bullish: el mínimo de la vela i queda por encima del máximo de la vela i-2
    (hueco alcista). Bearish: el máximo de i queda por debajo del mínimo de i-2.
    `min_atr_frac` filtra huecos menores que esa fracción del ATR.
    """
    n = len(df)
    if n < 3:
        return []
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    atr = float(ind.atr(df, 14).iloc[-1]) if n >= 15 else 0.0
    min_size = min_atr_frac * atr if atr > 0 else 0.0

    fvgs: List[FVG] = []
    for i in range(2, n):
        if low[i] > high[i - 2] and (low[i] - high[i - 2]) >= min_size:
            fvgs.append(FVG("bullish", top=float(low[i]), bottom=float(high[i - 2]), pos=i))
        elif high[i] < low[i - 2] and (low[i - 2] - high[i]) >= min_size:
            fvgs.append(FVG("bearish", top=float(low[i - 2]), bottom=float(high[i]), pos=i))
    return fvgs


def find_order_blocks(
    df: pd.DataFrame, impulse_atr: float = 1.0, lookback: int = 60
) -> List[OrderBlock]:
    """Detecta Order Blocks.

    Bullish OB: última vela bajista antes de un impulso alcista fuerte (cuerpo >
    `impulse_atr` * ATR) cuyo cierre supera el máximo de la vela contraria.
    Simétrico para bearish OB.
    """
    n = len(df)
    if n < 16:
        return []
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    low_ = df["low"].to_numpy()
    c = df["close"].to_numpy()
    atr_series = ind.atr(df, 14).to_numpy()

    obs: List[OrderBlock] = []
    start = max(1, n - lookback)
    for i in range(start, n - 1):
        atr = atr_series[i]
        if np.isnan(atr) or atr <= 0:
            continue
        body_next = c[i + 1] - o[i + 1]
        # Bullish OB
        if c[i] < o[i] and body_next > impulse_atr * atr and c[i + 1] > h[i]:
            obs.append(OrderBlock("bullish", top=float(h[i]), bottom=float(low_[i]), pos=i))
        # Bearish OB
        elif c[i] > o[i] and (-body_next) > impulse_atr * atr and c[i + 1] < low_[i]:
            obs.append(OrderBlock("bearish", top=float(h[i]), bottom=float(low_[i]), pos=i))
    return obs


def market_structure(swings: List[Swing]) -> StructureState:
    """Deriva tendencia y último evento estructural (BOS/CHoCH) desde los swings."""
    highs = [s for s in swings if s.kind == "high"]
    lows = [s for s in swings if s.kind == "low"]
    if len(highs) < 2 or len(lows) < 2:
        return StructureState("undefined", "none", None)

    hh = highs[-1].price > highs[-2].price
    hl = lows[-1].price > lows[-2].price
    lh = highs[-1].price < highs[-2].price
    ll = lows[-1].price < lows[-2].price

    # Orden temporal del último high vs último low para distinguir BOS de CHoCH.
    last_high_first = highs[-1].pos < lows[-1].pos

    if hh and hl:
        return StructureState("bullish", "BOS", highs[-2].price)
    if ll and lh:
        return StructureState("bearish", "BOS", lows[-2].price)
    # Rompe en contra de la secuencia previa -> posible cambio de carácter.
    if hh and ll:
        event = "CHoCH" if last_high_first else "none"
        return StructureState("undefined", event, None)
    return StructureState("undefined", "none", None)


def alternating_swings(swings: List[Swing]) -> List[Swing]:
    """Convierte los swings en un zigzag alternado high/low.

    Si aparecen swings consecutivos del mismo tipo, conserva el más extremo (el
    máximo más alto o el mínimo más bajo). Imprescindible para el conteo de
    patrones armónicos (XABCD).
    """
    result: List[Swing] = []
    for s in swings:
        if not result or result[-1].kind != s.kind:
            result.append(s)
            continue
        prev = result[-1]
        keep_new = (s.kind == "high" and s.price >= prev.price) or (
            s.kind == "low" and s.price <= prev.price
        )
        if keep_new:
            result[-1] = s
    return result


def find_liquidity(swings: List[Swing], tolerance: float) -> List[LiquidityPool]:
    """Agrupa máximos/mínimos "iguales" (dentro de `tolerance`) en pools de liquidez."""

    def cluster(levels: List[float], kind: str) -> List[LiquidityPool]:
        pools: List[LiquidityPool] = []
        levels = sorted(levels)
        i = 0
        while i < len(levels):
            group = [levels[i]]
            j = i
            while j + 1 < len(levels) and abs(levels[j + 1] - levels[i]) <= tolerance:
                j += 1
                group.append(levels[j])
            if len(group) >= 2:
                pools.append(LiquidityPool(sum(group) / len(group), kind, len(group)))
            i = j + 1
        return pools

    highs = [s.price for s in swings if s.kind == "high"]
    lows = [s.price for s in swings if s.kind == "low"]
    return cluster(highs, "buy_side") + cluster(lows, "sell_side")


def detect_sweep(df: pd.DataFrame, swings: List[Swing], tolerance: float) -> Optional[Sweep]:
    """Detecta un barrido de liquidez en la última vela.

    Bearish sweep: la última vela hace un máximo por encima de un swing high previo
    pero cierra por debajo de ese nivel (stop hunt de compradores -> señal SELL).
    Bullish sweep: barre un swing low y cierra por encima (-> señal BUY).
    """
    n = len(df)
    if n < 3 or not swings:
        return None
    last_high = float(df["high"].iloc[-1])
    last_low = float(df["low"].iloc[-1])
    last_close = float(df["close"].iloc[-1])
    last_pos = n - 1

    prior_highs = [s for s in swings if s.kind == "high" and s.pos < last_pos - 1]
    prior_lows = [s for s in swings if s.kind == "low" and s.pos < last_pos - 1]

    # Barrido bajista de máximos.
    for s in reversed(prior_highs):
        if last_high > s.price + tolerance and last_close < s.price:
            return Sweep("bearish", s.price, last_pos)
    # Barrido alcista de mínimos.
    for s in reversed(prior_lows):
        if last_low < s.price - tolerance and last_close > s.price:
            return Sweep("bullish", s.price, last_pos)
    return None


def premium_discount(df: pd.DataFrame, lookback: int = 50) -> Tuple[float, float, float]:
    """Devuelve (máximo, mínimo, equilibrio) del rango reciente.

    Precio > equilibrio = zona *premium* (favorece ventas); precio < equilibrio =
    zona *discount* (favorece compras).
    """
    seg = df.iloc[-lookback:] if len(df) > lookback else df
    hi = float(seg["high"].max())
    lo = float(seg["low"].min())
    return hi, lo, (hi + lo) / 2.0
