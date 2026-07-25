"""Proveedores de datos de contexto externo (Adapter + DI).

Cada fuente externa (calendario económico, activos correlacionados, sentimiento
retail) se abstrae tras una interfaz con una implementación en memoria (para
tests/demos, determinista) y adapters prácticos (CSV) para producción. Así los
agentes de contexto no dependen de ninguna API concreta.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .events import EconomicEvent


# --------------------------------------------------------------------------- #
#  Calendario económico
# --------------------------------------------------------------------------- #
class NewsProvider(ABC):
    """Fuente de eventos del calendario económico."""

    @abstractmethod
    def events_between(self, start: datetime, end: datetime) -> List[EconomicEvent]:
        """Eventos con `start <= time <= end` (tiempos en UTC)."""


class InMemoryNewsProvider(NewsProvider):
    """Lista de eventos en memoria (tests/demos)."""

    def __init__(self, events: Optional[List[EconomicEvent]] = None) -> None:
        self._events = sorted(events or [], key=lambda e: e.time)

    def add(self, event: EconomicEvent) -> None:
        self._events.append(event)
        self._events.sort(key=lambda e: e.time)

    def events_between(self, start: datetime, end: datetime) -> List[EconomicEvent]:
        start = _to_utc(start)
        end = _to_utc(end)
        return [e for e in self._events if start <= e.time <= end]


class CsvNewsProvider(InMemoryNewsProvider):
    """Carga el calendario desde un CSV (export de ForexFactory/Investing).

    Columnas esperadas: `time` (ISO 8601), `currency`, `impact`, `title`.
    Opcionales: `actual`, `forecast`, `previous`.
    """

    def __init__(self, path: str | Path) -> None:
        df = pd.read_csv(path)
        events = []
        for _, row in df.iterrows():
            events.append(EconomicEvent(
                time=pd.to_datetime(row["time"]).to_pydatetime(),
                currency=str(row["currency"]),
                impact=str(row["impact"]),
                title=str(row.get("title", "")),
                actual=_opt_float(row.get("actual")),
                forecast=_opt_float(row.get("forecast")),
                previous=_opt_float(row.get("previous")),
            ))
        super().__init__(events)


# --------------------------------------------------------------------------- #
#  Activos correlacionados
# --------------------------------------------------------------------------- #
class CorrelationProvider(ABC):
    """Fuente de series de precios de activos correlacionados con el Oro."""

    @abstractmethod
    def symbols(self) -> List[str]: ...

    @abstractmethod
    def closes(self, symbol: str, lookback: int) -> Optional[pd.Series]:
        """Últimos `lookback` cierres del símbolo, o None si no hay datos."""


class InMemoryCorrelationProvider(CorrelationProvider):
    """Series inyectadas por símbolo (tests/demos/live multi-símbolo)."""

    def __init__(self, series: Optional[Dict[str, pd.Series]] = None) -> None:
        self._series: Dict[str, pd.Series] = dict(series or {})

    def set(self, symbol: str, closes: pd.Series) -> None:
        self._series[symbol] = closes

    def symbols(self) -> List[str]:
        return list(self._series)

    def closes(self, symbol: str, lookback: int) -> Optional[pd.Series]:
        s = self._series.get(symbol)
        if s is None or s.empty:
            return None
        return s.iloc[-lookback:]


# --------------------------------------------------------------------------- #
#  Sentimiento (posicionamiento retail)
# --------------------------------------------------------------------------- #
class SentimentProvider(ABC):
    """Fuente de sentimiento/posicionamiento retail (% neto largo, 0-100)."""

    @abstractmethod
    def net_long(self, symbol: str, at: Optional[datetime] = None) -> Optional[float]: ...


class InMemorySentimentProvider(SentimentProvider):
    """Valor de sentimiento fijo o por símbolo (tests/demos)."""

    def __init__(self, values: Optional[Dict[str, float]] = None, default: Optional[float] = None) -> None:
        self._values = dict(values or {})
        self._default = default

    def set(self, symbol: str, net_long_pct: float) -> None:
        self._values[symbol] = net_long_pct

    def net_long(self, symbol: str, at: Optional[datetime] = None) -> Optional[float]:
        return self._values.get(symbol, self._default)


# --------------------------------------------------------------------------- #
#  Utilidades
# --------------------------------------------------------------------------- #
def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _opt_float(value) -> Optional[float]:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
