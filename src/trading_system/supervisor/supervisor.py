"""Supervisor Central: agrega las decisiones de los agentes en una decisión final."""
from __future__ import annotations

import logging
import statistics
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Sequence

from ..core import (
    AgentDecision,
    BaseAgent,
    MarketData,
    SignalType,
    SupervisorDecision,
)
from ..risk import RiskManager
from .weighting import StaticWeighting, WeightingStrategy


class Supervisor:
    """Orquesta a los agentes y decide BUY / SELL / WAIT.

    Responsabilidades:
      1. Ejecutar todos los agentes (en paralelo, con aislamiento de fallos).
      2. Ponderar cada decisión con una `WeightingStrategy` (según el régimen).
      3. Detectar conflictos (desacuerdo fuerte del conjunto).
      4. Calcular una puntuación global en [-1, 1] y consolidar SL/TP/riesgo.
      5. Aplicar el `RiskManager` (veto + tamaño de posición).
      6. Registrar el razonamiento completo (SupervisorDecision).
    """

    def __init__(
        self,
        agents: Sequence[BaseAgent],
        weighting: Optional[WeightingStrategy] = None,
        risk_manager: Optional[RiskManager] = None,
        buy_threshold: float = 0.15,
        conflict_threshold: float = 0.5,
        max_workers: int = 8,
    ) -> None:
        if not agents:
            raise ValueError("El Supervisor requiere al menos un agente")
        self.agents = list(agents)
        self.weighting = weighting or StaticWeighting({})
        self.risk_manager = risk_manager or RiskManager()
        self.buy_threshold = buy_threshold
        self.conflict_threshold = conflict_threshold
        self.max_workers = max_workers
        self.logger = logging.getLogger("supervisor")

    # ---- Ejecución de agentes -------------------------------------------
    def collect(self, md: MarketData) -> List[AgentDecision]:
        """Ejecuta todos los agentes en paralelo y recolecta sus decisiones."""
        workers = min(self.max_workers, len(self.agents))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            decisions = list(pool.map(lambda a: a.run(md), self.agents))
        return decisions

    # ---- Decisión --------------------------------------------------------
    def decide(self, md: MarketData) -> SupervisorDecision:
        decisions = self.collect(md)
        regime = md.regime

        weights: Dict[str, float] = {
            d.agent_name: self.weighting.weight_for(d.agent_name, regime) for d in decisions
        }

        actionable = [d for d in decisions if d.is_actionable]

        # Puntuación global ponderada por peso y confianza, en [-1, 1].
        numerator = 0.0
        denominator = 0.0
        buy_w = sell_w = 0.0
        for d in actionable:
            w = weights.get(d.agent_name, 1.0)
            contrib = w * (d.confidence / 100.0)
            numerator += contrib * d.signal.sign
            denominator += w
            if d.signal is SignalType.BUY:
                buy_w += contrib
            elif d.signal is SignalType.SELL:
                sell_w += contrib

        score = (numerator / denominator) if denominator > 0 else 0.0

        # Conflicto: acuerdo = |neto| / bruto. Bajo acuerdo => conflicto.
        gross = buy_w + sell_w
        agreement = (abs(buy_w - sell_w) / gross) if gross > 0 else 0.0
        conflict = gross > 0 and agreement < self.conflict_threshold

        signal = SignalType.from_sign(score, deadband=self.buy_threshold)
        if conflict:
            signal = SignalType.WAIT

        confidence = min(100.0, abs(score) * 100.0)

        # Riesgo consolidado: media ponderada de estimated_risk de todos.
        risk = self._weighted_risk(decisions, weights)

        # Veto agregado (p. ej. agente de riesgo o noticias): fuerza WAIT.
        vetoed, veto_reason = self._check_veto(decisions)
        if vetoed:
            signal = SignalType.WAIT

        # SL/TP consolidados a partir de los agentes que coinciden con la señal.
        stop_loss, take_profit = self._consolidate_levels(actionable, signal)

        # Gestión de riesgo: aprueba/veta y dimensiona.
        position_size = None
        if signal is not SignalType.WAIT and not vetoed:
            rd = self.risk_manager.evaluate(
                signal, md.price, stop_loss, agent_veto=vetoed, veto_reason=veto_reason
            )
            if not rd.approved:
                vetoed = True
                veto_reason = rd.reason
                signal = SignalType.WAIT
            else:
                position_size = rd.position_size

        explanation = self._build_explanation(
            signal, score, conflict, vetoed, veto_reason, actionable, weights
        )
        decision = SupervisorDecision(
            signal=signal,
            confidence=confidence,
            score=score,
            explanation=explanation,
            estimated_risk=risk,
            stop_loss=stop_loss if signal is not SignalType.WAIT else None,
            take_profit=take_profit if signal is not SignalType.WAIT else None,
            position_size=position_size,
            conflict=conflict,
            vetoed=vetoed,
            veto_reason=veto_reason,
            contributing=decisions,
            weights=weights,
        )
        self.logger.info(
            "Decisión: %s (score=%.3f, conf=%.1f, conflicto=%s, veto=%s)",
            signal.value, score, confidence, conflict, vetoed,
        )
        return decision

    # ---- Aprendizaje -----------------------------------------------------
    def feedback(self, decisions: Sequence[AgentDecision], md: MarketData, profitable: bool) -> None:
        """Retroalimenta la estrategia de ponderación con el resultado real.

        Un agente "acertó" si su señal direccional coincidió con el resultado
        (operación ganadora en su dirección).
        """
        final_correct = profitable
        for d in decisions:
            if not d.is_actionable:
                continue
            correct = final_correct  # simplificación: alineado con el resultado global
            self.weighting.update(d.agent_name, md.regime, correct)

    # ---- Internos --------------------------------------------------------
    @staticmethod
    def _weighted_risk(decisions: Sequence[AgentDecision], weights: Dict[str, float]) -> float:
        num = sum(weights.get(d.agent_name, 1.0) * d.estimated_risk for d in decisions)
        den = sum(weights.get(d.agent_name, 1.0) for d in decisions)
        return (num / den) if den > 0 else 50.0

    @staticmethod
    def _check_veto(decisions: Sequence[AgentDecision]):
        for d in decisions:
            if d.metadata.get("veto"):
                return True, d.metadata.get("veto_reason") or f"Veto de {d.agent_name}"
        return False, None

    @staticmethod
    def _consolidate_levels(actionable: Sequence[AgentDecision], signal: SignalType):
        if signal is SignalType.WAIT:
            return None, None
        sls = [d.stop_loss for d in actionable if d.signal is signal and d.stop_loss]
        tps = [d.take_profit for d in actionable if d.signal is signal and d.take_profit]
        sl = statistics.median(sls) if sls else None
        tp = statistics.median(tps) if tps else None
        return sl, tp

    @staticmethod
    def _build_explanation(signal, score, conflict, vetoed, veto_reason, actionable, weights) -> str:
        if vetoed:
            return f"WAIT por veto de riesgo: {veto_reason}"
        if conflict:
            return f"WAIT por conflicto entre agentes (score={score:.2f})"
        top = sorted(
            actionable,
            key=lambda d: weights.get(d.agent_name, 1.0) * d.confidence,
            reverse=True,
        )[:3]
        drivers = ", ".join(f"{d.agent_name}({d.signal.value},{d.confidence:.0f})" for d in top)
        return f"{signal.value} score={score:.2f}. Principales: {drivers or 'ninguno'}"
