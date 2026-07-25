"""Adapter de MetaTrader 5 (implementación completa en Fase 3).

Aísla la API concreta del paquete `MetaTrader5` (solo disponible en Windows con
el terminal instalado). Se importa de forma perezosa para que el resto del
sistema funcione y se testee sin MT5. En la Fase 3 se completan `open`/`close` y
la obtención de datos en vivo, y se añade `MT5DataFeed`.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from ..core.enums import SignalType
from ..core.exceptions import ExecutionError
from .broker import ExecutionBroker, Order


class MT5Broker(ExecutionBroker):
    """Broker real sobre MetaTrader 5. Requiere el paquete `MetaTrader5`."""

    def __init__(
        self,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        magic: int = 20250725,
    ) -> None:
        self.login = login
        self.password = password
        self.server = server
        self.magic = magic
        self._mt5 = None
        self.logger = logging.getLogger("broker.mt5")

    def connect(self) -> None:
        try:
            import MetaTrader5 as mt5  # import perezoso
        except ImportError as exc:  # pragma: no cover - depende del entorno
            raise ExecutionError(
                "El paquete MetaTrader5 no está instalado (solo Windows). "
                "Instálalo en el entorno de producción para el modo live."
            ) from exc

        if not mt5.initialize(login=self.login, password=self.password, server=self.server):
            raise ExecutionError(f"initialize() falló: {mt5.last_error()}")
        self._mt5 = mt5
        self.logger.info("Conectado a MT5 (server=%s)", self.server)

    # Los métodos siguientes se implementan por completo en la Fase 3.
    def open(self, order: Order) -> Order:  # pragma: no cover - Fase 3
        raise NotImplementedError("MT5Broker.open se implementa en la Fase 3")

    def close(self, ticket: int, price: float) -> float:  # pragma: no cover - Fase 3
        raise NotImplementedError("MT5Broker.close se implementa en la Fase 3")

    def open_positions(self) -> List[Order]:  # pragma: no cover - Fase 3
        raise NotImplementedError("MT5Broker.open_positions se implementa en la Fase 3")
