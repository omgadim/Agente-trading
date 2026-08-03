"""Proveedores de datos de contexto externo (Adapter + DI).

Cada fuente externa (calendario económico, activos correlacionados, sentimiento
retail) se abstrae tras una interfaz con una implementación en memoria (para
tests/demos, determinista) y adapters prácticos (CSV) para producción. Así los
agentes de contexto no dependen de ninguna API concreta.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .events import EconomicEvent

_logger = logging.getLogger("context.news_flow")


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


class MT5CorrelationProvider(CorrelationProvider):
    """Series de activos correlacionados desde MetaTrader 5 (vía `MT5Client`).

    Baja los cierres de cada símbolo (p. ej. USDCHF, AUDUSD, EURUSD) para que el
    `CorrelationAgent` mida su correlación con el Oro y derive un sesgo. Los
    símbolos deben existir en el broker. Tolerante a fallos: si un símbolo no
    está o falla, devuelve None y el agente lo ignora.
    """

    def __init__(self, client, symbols: List[str], timeframe) -> None:
        self.client = client
        self._symbols = list(symbols)
        self.timeframe = timeframe

    def symbols(self) -> List[str]:
        return list(self._symbols)

    def closes(self, symbol: str, lookback: int) -> Optional[pd.Series]:
        try:
            df = self.client.rates(symbol, self.timeframe, lookback)
        except Exception as exc:  # símbolo ausente o error de red
            _logger.warning("Correlación: sin datos de %s: %s", symbol, exc)
            return None
        if df is None or df.empty or "close" not in df.columns:
            return None
        return df["close"].iloc[-lookback:]


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
#  Flujo de noticias (titulares de prensa) — p. ej. TheNewsAPI
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Headline:
    """Titular de prensa con su fecha de publicación (UTC)."""

    title: str
    published_at: datetime


class NewsFlowProvider(ABC):
    """Fuente de titulares recientes (para detectar ráfagas de noticias)."""

    @abstractmethod
    def recent(self, minutes: int, at: Optional[datetime] = None) -> List[Headline]:
        """Titulares publicados en los últimos `minutes` respecto a `at` (o ahora)."""


class InMemoryNewsFlowProvider(NewsFlowProvider):
    """Titulares en memoria (tests/demos)."""

    def __init__(self, headlines: Optional[List[Headline]] = None) -> None:
        self._headlines = list(headlines or [])

    def recent(self, minutes: int, at: Optional[datetime] = None) -> List[Headline]:
        now = _to_utc(at or datetime.now(timezone.utc))
        cutoff = now - timedelta(minutes=minutes)
        return [h for h in self._headlines if cutoff <= _to_utc(h.published_at) <= now]


class TheNewsApiProvider(NewsFlowProvider):
    """Adapter de TheNewsAPI (https://www.thenewsapi.com).

    Baja titulares recientes que coinciden con `search` (Oro/USD/Fed). Como el
    plan gratuito limita a ~100 peticiones/día, **cachea** y solo vuelve a
    consultar cada `ttl_sec` (por defecto 15 min → ~96/día). El token se toma de
    `NEWS_API_TOKEN` (nunca se escribe en el repo). Sin token o sin red, devuelve
    lista vacía sin romper la operativa.
    """

    ENDPOINT = "https://api.thenewsapi.com/v1/news/all"

    def __init__(
        self,
        token: Optional[str] = None,
        search: str = "gold OR XAUUSD OR Federal Reserve OR inflation",
        ttl_sec: int = 900,
        limit: int = 3,
        timeout: float = 8.0,
    ) -> None:
        self.token = token or os.getenv("NEWS_API_TOKEN")
        self.search = search
        self.ttl_sec = ttl_sec
        self.limit = limit
        self.timeout = timeout
        self._cache: List[Headline] = []
        self._last_fetch = 0.0

    def recent(self, minutes: int, at: Optional[datetime] = None) -> List[Headline]:
        self._maybe_refetch()
        now = _to_utc(at or datetime.now(timezone.utc))
        cutoff = now - timedelta(minutes=minutes)
        return [h for h in self._cache if cutoff <= _to_utc(h.published_at) <= now]

    def _maybe_refetch(self) -> None:
        if not self.token:
            return
        if time.time() - self._last_fetch < self.ttl_sec:
            return
        self._last_fetch = time.time()  # marca aunque falle, para no reintentar en bucle
        try:
            self._cache = self._fetch()
        except Exception as exc:  # una API caída nunca frena la operativa
            _logger.warning("TheNewsAPI no disponible: %s", exc)

    def _fetch(self) -> List[Headline]:  # pragma: no cover - requiere red/API
        params = urllib.parse.urlencode({
            "api_token": self.token, "search": self.search,
            "language": "en", "limit": self.limit,
        })
        req = urllib.request.Request(f"{self.ENDPOINT}?{params}",
                                     headers={"User-Agent": "trading-system"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        out: List[Headline] = []
        for art in payload.get("data", []):
            ts = art.get("published_at")
            if not ts:
                continue
            out.append(Headline(title=str(art.get("title", "")),
                                 published_at=pd.to_datetime(ts).to_pydatetime()))
        return out


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
