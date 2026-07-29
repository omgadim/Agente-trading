"""Utilidades compartidas por los agentes."""
from __future__ import annotations

from typing import Optional, Tuple

from ..core.enums import SignalType


def atr_sl_tp(
    price: float,
    atr: float,
    signal: SignalType,
    sl_mult: float = 1.0,
    tp_mult: float = 5.0,
) -> Tuple[Optional[float], Optional[float]]:
    """Calcula SL/TP simétricos a la dirección usando múltiplos de ATR.

    Devuelve (stop_loss, take_profit). Para WAIT o ATR no válido -> (None, None).

    Defaults SL=1.0 / TP=5.0 (ratio 1:5). El TP se amplió de 2.5 a 5.0 tras la
    validación fiel CON gestión simulada (break-even 2·ATR + trailing) y aprendizaje
    ON, walk-forward 5 folds sobre XAUUSD M30: al ser un sistema tendencial, dejar
    correr los ganadores subió el neto +73% (417->725), casi HALVED el drawdown
    (22.6%->14.5%) y más que duplicó el recovery (1.28->2.82). El filtro de régimen
    (ADX) se probó a la vez y se DESCARTÓ (sobreajuste). Ver scratchpad/faithful_campaign.
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
