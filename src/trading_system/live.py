"""LiveTrader: orquestador de operativa en vivo / paper sobre MetaTrader 5.

Un ciclo (`step`) hace: leer mercado -> gestionar posiciones abiertas
(break-even / trailing) -> si hay cupo, pedir decisión al Supervisor y, si el
guardián de mercado lo permite, abrir la operación dimensionada por el
RiskManager. No conoce si el broker es real o simulado (depende de interfaces).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .core import SupervisorDecision
from .core.enums import SignalType
from .data.feed import DataFeed
from .execution.broker import ExecutionBroker, Order
from .execution.guards import MarketGuard
from .risk import RiskManager, trailing_actions
from .supervisor import Supervisor


@dataclass
class LiveStepResult:
    """Resultado de un ciclo del LiveTrader."""

    decision: Optional[SupervisorDecision] = None
    opened: Optional[Order] = None
    management: List[Dict[str, Any]] = field(default_factory=list)
    guard_ok: bool = True
    guard_reason: str = "OK"
    skipped_reason: Optional[str] = None


class LiveTrader:
    def __init__(
        self,
        feed: DataFeed,
        broker: ExecutionBroker,
        supervisor: Supervisor,
        risk_manager: Optional[RiskManager] = None,
        guard: Optional[MarketGuard] = None,
        symbol: str = "XAUUSD",
        max_positions: int = 1,
        be_trigger: float = 1.0,
        trail_trigger: float = 2.0,
    ) -> None:
        self.feed = feed
        self.broker = broker
        self.supervisor = supervisor
        self.risk_manager = risk_manager or supervisor.risk_manager
        self.guard = guard or MarketGuard()
        self.symbol = symbol
        self.max_positions = max_positions
        self.be_trigger = be_trigger
        self.trail_trigger = trail_trigger
        self.logger = logging.getLogger("live")

    def step(self) -> LiveStepResult:
        md = self.feed.get_market_data(self.symbol)
        result = LiveStepResult()

        # 1) Gestión de posiciones abiertas (break-even / trailing).
        positions = self.broker.open_positions()
        result.management = self._manage(positions, md.price, md.regime.atr)

        # 2) ¿Hay cupo para nuevas entradas?
        if len(positions) >= self.max_positions:
            result.skipped_reason = "Cupo de posiciones alcanzado"
            return result

        # 3) Guardián de mercado (spread / horario).
        ok, reason = self.guard.check(md.spread, md.timestamp)
        result.guard_ok, result.guard_reason = ok, reason
        if not ok:
            result.skipped_reason = reason
            return result

        # 4) Decisión del Supervisor.
        decision = self.supervisor.decide(md)
        result.decision = decision
        if decision.signal is SignalType.WAIT or decision.vetoed:
            result.skipped_reason = decision.veto_reason or "Sin señal accionable"
            return result
        if not (decision.stop_loss and decision.take_profit):
            result.skipped_reason = "Decisión sin SL/TP"
            return result

        # 5) Abrir la operación.
        order = Order(
            symbol=self.symbol,
            direction=decision.signal,
            volume=decision.position_size or 0.01,
            price=md.price,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
        )
        result.opened = self.broker.open(order)
        self.logger.info("Entrada %s @ %.2f vol=%.2f", decision.signal.value,
                         order.price, order.volume)
        return result

    def _manage(self, positions: List[Order], price: float, atr: float) -> List[Dict[str, Any]]:
        if not positions:
            return []
        as_dicts = [
            {"ticket": p.ticket, "entry_price": p.price, "direction": p.direction.value}
            for p in positions
        ]
        actions = trailing_actions(as_dicts, price, atr, self.be_trigger, self.trail_trigger)
        by_ticket = {p.ticket: p for p in positions}
        applied: List[Dict[str, Any]] = []
        for action in actions:
            pos = by_ticket.get(action["ticket"])
            if pos is None:
                continue
            new_sl = action["new_sl"]
            # Solo apretar el stop en la dirección favorable (nunca aflojarlo).
            if self._is_tighter(pos, new_sl):
                if self.broker.modify(pos.ticket, new_sl, pos.take_profit):
                    pos.stop_loss = new_sl
                    applied.append(action)
        return applied

    @staticmethod
    def _is_tighter(pos: Order, new_sl: float) -> bool:
        if pos.stop_loss is None:
            return True
        if pos.direction is SignalType.BUY:
            return new_sl > pos.stop_loss
        return new_sl < pos.stop_loss
