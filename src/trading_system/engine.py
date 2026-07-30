"""Fachada del sistema: construye agentes/supervisor desde config y orquesta un ciclo."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .core import AgentRegistry, BaseAgent, SupervisorDecision
from .data import DataFeed, SimulatedDataFeed
from .execution import ExecutionBroker, Order, PaperBroker
from .risk import RiskManager, RiskParameters
from .supervisor import (
    AdaptiveWeighting,
    MetaModelWeighting,
    StaticWeighting,
    Supervisor,
    WeightingStrategy,
)

# Importar el paquete de agentes registra todas las clases en el AgentRegistry.
from . import agents as _agents  # noqa: F401  (efecto de registro)


def build_agents(config: Dict[str, Any]) -> List[BaseAgent]:
    """Instancia los agentes declarados en la sección `agents` de la config."""
    built: List[BaseAgent] = []
    for name, agent_cfg in (config.get("agents") or {}).items():
        agent_cfg = agent_cfg or {}
        if agent_cfg.get("enabled", True) is False:
            continue
        built.append(AgentRegistry.create(name, agent_cfg))
    return built


def build_weighting(config: Dict[str, Any]) -> WeightingStrategy:
    sup_cfg = config.get("supervisor", {}) or {}
    mode = sup_cfg.get("weighting", "adaptive")
    if mode == "static":
        return StaticWeighting(sup_cfg.get("weights", {}) or {})
    adaptive = AdaptiveWeighting(
        base=sup_cfg.get("base_weight", 1.0),
        alpha=sup_cfg.get("learning_rate", 0.1),
    )
    if mode == "meta":
        return MetaModelWeighting(
            fallback=adaptive,
            base=sup_cfg.get("base_weight", 1.0),
            warmup=sup_cfg.get("meta_warmup", 30),
        )
    return adaptive


class TradingEngine:
    """Un punto de entrada único: datos → supervisor → (opcional) ejecución."""

    def __init__(
        self,
        config: Dict[str, Any],
        feed: Optional[DataFeed] = None,
        broker: Optional[ExecutionBroker] = None,
    ) -> None:
        self.config = config
        self.symbol = config.get("symbol", "XAUUSD")
        self.feed = feed or SimulatedDataFeed()
        self.broker = broker or PaperBroker()
        self.logger = logging.getLogger("engine")

        risk_cfg = config.get("risk", {}) or {}
        self.risk_manager = RiskManager(RiskParameters(**risk_cfg))

        agents = build_agents(config)
        sup_cfg = config.get("supervisor", {}) or {}
        self.supervisor = Supervisor(
            agents=agents,
            weighting=build_weighting(config),
            risk_manager=self.risk_manager,
            buy_threshold=sup_cfg.get("buy_threshold", 0.15),
            conflict_threshold=sup_cfg.get("conflict_threshold", 0.5),
            regime_switch=config.get("regime_switch"),
        )

    def run_once(self, execute: bool = False) -> SupervisorDecision:
        """Ejecuta un ciclo de decisión. Si `execute`, abre orden en paper/broker."""
        md = self.feed.get_market_data(self.symbol)
        decision = self.supervisor.decide(md)

        if execute and decision.signal.value in ("BUY", "SELL") and not decision.vetoed:
            order = Order(
                symbol=self.symbol,
                direction=decision.signal,
                volume=decision.position_size or self.config.get("risk", {}).get("min_lot", 0.01),
                price=md.price,
                stop_loss=decision.stop_loss,
                take_profit=decision.take_profit,
            )
            self.broker.open(order)
        return decision
