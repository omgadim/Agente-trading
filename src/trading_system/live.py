"""LiveTrader: orquestador de operativa en vivo / paper sobre MetaTrader 5.

Un ciclo (`step`) hace: leer mercado -> gestionar posiciones abiertas
(break-even / trailing) -> si hay cupo, pedir decisión al Supervisor y, si el
guardián de mercado lo permite, abrir la operación dimensionada por el
RiskManager. No conoce si el broker es real o simulado (depende de interfaces).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .alerts import Notifier
from .core import AgentDecision, MarketRegime, SupervisorDecision
from .core.enums import SignalType
from .data.feed import DataFeed
from .execution.broker import ExecutionBroker, Order
from .execution.guards import MarketGuard
from .risk import KillSwitch, RiskManager, trailing_actions
from .supervisor import Supervisor

# Clave con la que se persiste el estado de la ponderación del Supervisor.
_WEIGHT_STATE_KEY = "weighting"


@dataclass
class LiveStepResult:
    """Resultado de un ciclo del LiveTrader."""

    decision: Optional[SupervisorDecision] = None
    opened: Optional[Order] = None
    management: List[Dict[str, Any]] = field(default_factory=list)
    closed: List[Any] = field(default_factory=list)
    guard_ok: bool = True
    guard_reason: str = "OK"
    halted: bool = False
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
        repository=None,
        kill_switch: Optional[KillSwitch] = None,
        notifier: Optional[Notifier] = None,
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
        self.repository = repository
        self.kill_switch = kill_switch
        self.notifier = notifier
        self.logger = logging.getLogger("live")
        self._trade_ids: Dict[int, int] = {}  # ticket -> id en la BD
        # ticket -> (decisiones de los agentes, régimen) capturados al abrir. Al
        # cerrar se usan para (1) alimentar el aprendizaje de la ponderación del
        # Supervisor y (2) rellenar la tabla `agent_performance` del dashboard.
        self._trade_context: Dict[int, Tuple[Sequence[AgentDecision], MarketRegime]] = {}
        self._halt_notified = False
        # Restaura la ponderación aprendida (si hay persistencia): así el
        # aprendizaje online sobrevive a los reinicios del runner.
        self._load_weights()

    def step(self) -> LiveStepResult:
        md = self.feed.get_market_data(self.symbol)
        result = LiveStepResult()

        # 0) Conciliar cierres del broker (SL/TP) desde el último ciclo.
        result.closed = self._reconcile_closes()

        # 1) Gestión de posiciones abiertas (break-even / trailing).
        positions = self.broker.open_positions()
        result.management = self._manage(positions, md.price, md.regime.atr)

        # 2) Kill switch: si está disparado, no se abren nuevas operaciones.
        if self.kill_switch is not None:
            ok, reason = self.kill_switch.check()
            if not ok:
                result.halted = True
                result.skipped_reason = reason
                self._notify_halt(reason)
                return result

        # 3) ¿Hay cupo para nuevas entradas?
        if len(positions) >= self.max_positions:
            result.skipped_reason = "Cupo de posiciones alcanzado"
            return result

        # 4) Guardián de mercado (spread / horario).
        ok, reason = self.guard.check(md.spread, md.timestamp)
        result.guard_ok, result.guard_reason = ok, reason
        if not ok:
            result.skipped_reason = reason
            return result

        # 5) Decisión del Supervisor.
        decision = self.supervisor.decide(md)
        result.decision = decision
        if decision.signal is SignalType.WAIT or decision.vetoed:
            result.skipped_reason = decision.veto_reason or "Sin señal accionable"
            return result
        if not (decision.stop_loss and decision.take_profit):
            result.skipped_reason = "Decisión sin SL/TP"
            return result

        # 6) Abrir la operación.
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
        self._persist(decision, md, order)
        self._notify(f"Entrada {decision.signal.value} {self.symbol} @ {order.price:.2f} "
                     f"vol={order.volume} SL={order.stop_loss} TP={order.take_profit}",
                     "Operación abierta")
        return result

    def _reconcile_closes(self) -> List[Any]:
        """Registra los cierres del broker: persistencia, riesgo y kill switch."""
        closed = self.broker.poll_closed_deals()
        for deal in closed:
            ticket = getattr(deal, "ticket", None)
            trade_id = self._trade_ids.pop(ticket, None)
            if self.repository is not None and trade_id is not None:
                self.repository.close_trade(trade_id, deal.exit_price, deal.pnl)
            self._learn_from_close(ticket, deal.pnl)
            self.risk_manager.register_pnl(deal.pnl)
            if self.kill_switch is not None:
                self.kill_switch.record_trade(deal.pnl)
            self._notify(f"Cierre {self.symbol} pnl={deal.pnl:.2f}", "Operación cerrada",
                         level="warning" if deal.pnl < 0 else "info")
        if closed:
            self._save_weights()  # persistir el aprendizaje tras los cierres
        return list(closed)

    def _learn_from_close(self, ticket: Optional[int], pnl: float) -> None:
        """Cierra el bucle de aprendizaje y atribución tras una operación.

        1) Alimenta la ponderación del Supervisor con el resultado real, de modo
           que la estrategia adaptativa aprende también en vivo/paper (antes solo
           se hacía en el backtester).
        2) Actualiza la tabla `agent_performance` que consume el dashboard.
        """
        context = self._trade_context.pop(ticket, None)
        if context is None:
            return
        decisions, regime = context
        profitable = pnl > 0
        # 1) Aprendizaje online de la ponderación (peso que usa el Supervisor).
        self.supervisor.learn(decisions, regime, profitable)
        # 2) Desempeño por agente/régimen para el dashboard.
        if self.repository is not None:
            for d in decisions:
                if d.is_actionable:
                    self.repository.update_agent_performance(d.agent_name, regime.key, profitable)

    def _persist(self, decision, md, order: Order) -> None:
        if self.repository is None:
            return
        decision_id = self.repository.save_decision(decision, self.symbol, md.regime.key)
        trade_id = self.repository.open_trade(
            self.symbol, order.direction.value, order.volume, order.price,
            order.stop_loss, order.take_profit, decision_id=decision_id, ticket=order.ticket,
        )
        if order.ticket is not None:
            self._trade_ids[order.ticket] = trade_id
            # Guarda las decisiones de los agentes y el régimen para, al cerrar,
            # alimentar el aprendizaje de la ponderación y el desempeño por agente.
            self._trade_context[order.ticket] = (decision.contributing, md.regime)

    def _load_weights(self) -> None:
        """Carga la ponderación aprendida desde la persistencia (best-effort)."""
        if self.repository is None:
            return
        try:
            state = self.repository.load_weight_state(_WEIGHT_STATE_KEY)
            if state:
                self.supervisor.weighting.load_state_dict(state)
                self.logger.info("Ponderación restaurada desde la persistencia.")
        except Exception as exc:  # nunca frenar la operativa por esto
            self.logger.warning("No se pudo cargar la ponderación: %s", exc)

    def _save_weights(self) -> None:
        """Persiste la ponderación aprendida (best-effort)."""
        if self.repository is None:
            return
        try:
            self.repository.save_weight_state(
                _WEIGHT_STATE_KEY, self.supervisor.weighting.state_dict())
        except Exception as exc:
            self.logger.warning("No se pudo guardar la ponderación: %s", exc)

    def _notify(self, message: str, subject: str = "Trading System", level: str = "info") -> None:
        if self.notifier is not None:
            try:
                self.notifier.notify(message, subject, level)
            except Exception as exc:  # una alerta caída nunca debe frenar la operativa
                self.logger.warning("Notificación falló: %s", exc)

    def _notify_halt(self, reason: str) -> None:
        if not self._halt_notified:
            self._notify(f"OPERATIVA DETENIDA: {reason}", "Kill switch", level="error")
            self._halt_notified = True

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
