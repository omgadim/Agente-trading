"""Utilidades compartidas por los agentes."""
from __future__ import annotations

from typing import Optional, Tuple

from ..core.enums import SignalType


def atr_sl_tp(
    price: float,
    atr: float,
    signal: SignalType,
    sl_mult: float = 1.5,
    tp_mult: float = 2.5,
) -> Tuple[Optional[float], Optional[float]]:
    """Calcula SL/TP simétricos a la dirección usando múltiplos de ATR.

    Devuelve (stop_loss, take_profit). Para WAIT o ATR no válido -> (None, None).
    """
    if signal is SignalType.WAIT or atr <= 0 or price <= 0:
        return None, None
    if signal is SignalType.BUY:
        return price - sl_mult * atr, price + tp_mult * atr
    return price + sl_mult * atr, price - tp_mult * atr


def scale_confidence(value: float, lo: float, hi: float) -> float:
    """Escala linealmente `value` de [lo, hi] a [0, 100] con recorte."""
    if hi == lo:
        return 50.0
    pct = (value - lo) / (hi - lo)
    return max(0.0, min(100.0, pct * 100.0))
