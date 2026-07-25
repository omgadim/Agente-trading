"""Reglas de gestión de posiciones abiertas (break-even y trailing por ATR).

Compartido entre `OpenTradesControlAgent` (recomendación) y `LiveTrader`
(aplicación real vía broker), para tener una única fuente de verdad.
"""
from __future__ import annotations

from typing import Any, Dict, List


def trailing_actions(
    positions: List[Dict[str, Any]],
    price: float,
    atr: float,
    be_trigger: float = 1.0,
    trail_trigger: float = 2.0,
) -> List[Dict[str, Any]]:
    """Calcula acciones de gestión para cada posición abierta.

    - A partir de `be_trigger` * ATR de beneficio: mover el stop a break-even.
    - A partir de `trail_trigger` * ATR: trailing stop a un ATR del precio.

    `positions` es una lista de dicts con al menos: `ticket`, `entry_price`,
    `direction` ('BUY'|'SELL'). Devuelve una lista de acciones
    `{ticket, action, new_sl}`.
    """
    actions: List[Dict[str, Any]] = []
    if atr <= 0:
        return actions

    for pos in positions:
        entry = float(pos.get("entry_price", price))
        direction = str(pos.get("direction", "BUY")).upper()
        ticket = pos.get("ticket")
        profit = (price - entry) if direction == "BUY" else (entry - price)
        profit_in_atr = profit / atr

        if profit_in_atr >= be_trigger:
            actions.append({"ticket": ticket, "action": "move_to_break_even", "new_sl": entry})
        if profit_in_atr >= trail_trigger:
            new_sl = (price - atr) if direction == "BUY" else (price + atr)
            actions.append({"ticket": ticket, "action": "trailing_stop", "new_sl": new_sl})
    return actions
