"""Ejecución de órdenes: interface y un broker de papel (paper trading)."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..core.enums import SignalType


@dataclass
class Order:
    symbol: str
    direction: SignalType
    volume: float
    price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    ticket: Optional[int] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionBroker(ABC):
    """Contrato de un broker (paper o MT5)."""

    @abstractmethod
    def open(self, order: Order) -> Order: ...

    @abstractmethod
    def close(self, ticket: int, price: float) -> float:
        """Cierra la posición y devuelve el PnL realizado."""

    @abstractmethod
    def open_positions(self) -> List[Order]: ...


class PaperBroker(ExecutionBroker):
    """Broker simulado para backtesting y tests. PnL en dinero de contrato."""

    def __init__(self, contract_size: float = 100.0) -> None:
        self.contract_size = contract_size
        self._positions: Dict[int, Order] = {}
        self._next_ticket = 1
        self.realized_pnl = 0.0
        self.logger = logging.getLogger("broker.paper")

    def open(self, order: Order) -> Order:
        order.ticket = self._next_ticket
        self._next_ticket += 1
        self._positions[order.ticket] = order
        self.logger.info(
            "OPEN #%s %s %s @ %.2f vol=%.2f",
            order.ticket, order.direction.value, order.symbol, order.price, order.volume,
        )
        return order

    def close(self, ticket: int, price: float) -> float:
        order = self._positions.pop(ticket, None)
        if order is None:
            raise KeyError(f"Ticket {ticket} no existe")
        direction = 1 if order.direction is SignalType.BUY else -1
        pnl = (price - order.price) * direction * order.volume * self.contract_size
        self.realized_pnl += pnl
        self.logger.info("CLOSE #%s @ %.2f pnl=%.2f", ticket, price, pnl)
        return pnl

    def open_positions(self) -> List[Order]:
        return list(self._positions.values())
