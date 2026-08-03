"""Guardianes de ejecución: spread y horario de trading.

Filtran cuándo es aceptable operar en vivo, con independencia de la señal. El Oro
tiene spreads que se disparan fuera de las sesiones líquidas y en el rollover; y
conviene no operar en fin de semana ni en ventanas de baja liquidez.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Tuple


@dataclass
class MarketGuard:
    """Valida condiciones de mercado antes de ejecutar.

    Attributes:
        max_spread: spread máximo aceptable (en precio). 0 o None => sin límite.
        trading_hours: lista de ventanas horarias UTC permitidas [(inicio, fin)],
            en horas [0, 24). Vacía => sin restricción horaria.
        allow_weekend: si False, bloquea sábado y domingo.
    """

    max_spread: Optional[float] = None
    trading_hours: List[Tuple[int, int]] = field(default_factory=list)
    allow_weekend: bool = False

    def check(self, spread: float, now: Optional[datetime] = None) -> Tuple[bool, str]:
        """Devuelve (permitido, motivo)."""
        now = now or datetime.now(timezone.utc)
        now = now.astimezone(timezone.utc)

        if not self.allow_weekend and now.weekday() >= 5:
            return False, "Fin de semana: mercado cerrado"

        if self.trading_hours and not self._in_hours(now.hour):
            return False, f"Fuera de horario permitido (hora UTC={now.hour})"

        if self.max_spread and spread > self.max_spread:
            return False, f"Spread {spread:.2f} supera el máximo {self.max_spread:.2f}"

        return True, "OK"

    def _in_hours(self, hour: int) -> bool:
        for start, end in self.trading_hours:
            if start <= end:
                if start <= hour < end:
                    return True
            else:  # ventana que cruza medianoche
                if hour >= start or hour < end:
                    return True
        return False
