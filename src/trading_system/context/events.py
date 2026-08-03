"""Modelo de un evento del calendario económico."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class EconomicEvent:
    """Evento macroeconómico programado.

    Attributes:
        time: hora del evento (UTC, tz-aware).
        currency: divisa afectada (p. ej. 'USD').
        impact: 'high' | 'medium' | 'low'.
        title: descripción (p. ej. 'Non-Farm Payrolls').
        actual/forecast/previous: valores (opcionales).
    """

    time: datetime
    currency: str
    impact: str
    title: str
    actual: Optional[float] = None
    forecast: Optional[float] = None
    previous: Optional[float] = None

    def __post_init__(self) -> None:
        # Normaliza a UTC tz-aware para comparaciones consistentes.
        t = self.time
        if t.tzinfo is None:
            object.__setattr__(self, "time", t.replace(tzinfo=timezone.utc))
        else:
            object.__setattr__(self, "time", t.astimezone(timezone.utc))
        object.__setattr__(self, "impact", self.impact.lower())
        object.__setattr__(self, "currency", self.currency.upper())

    @property
    def is_high(self) -> bool:
        return self.impact == "high"
