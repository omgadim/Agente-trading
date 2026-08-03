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
    MarketRegime,
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
        regime_switch: Optional[dict] = None,
    ) -> None:
        if not agents:
            raise ValueError("El Supervisor requiere al menos un agente")
        self.agents = list(agents)
        self.weighting = weighting or StaticWeighting({})
        self.risk_manager = risk_manager or RiskManager()
        self.buy_threshold = buy_threshold
        self.conflict_threshold = conflict_threshold
        self.max_workers = max_workers
        # Conmutación por régimen (opcional): en RANGE silencia agentes tendenciales,
        # potencia la reversión, sube el umbral de score y baja el riesgo. Con
        # `enabled: false` (o None) el comportamiento es idéntico al de tendencia.
        self.regime_switch = regime_switch or {}
        self.logger = logging.getLogger("supervisor")

    # ---- Detección robusta de RANGE -------------------------------------
    def _detect_range(self, md: MarketData) -> bool:
        """RANGE robusto: ADX bajo + pendientes de EMA20/EMA50 planas (ATR-normalizadas)."""
        from ..data import indicators as ind
        rs = self.regime_switch
        try:
            df = md.frame(md.primary_tf)
        except Exception:
            return False
        n_slope = int(rs.get("slope_lookback", 10))
        if len(df) < 60:
            return False
        close = df["close"]
        atr = md.regime.atr or float(ind.atr(df, 14).iloc[-1])
        if atr <= 0:
            return False
        adx_val = float(ind.adx(df, 14).iloc[-1])
        if adx_val != adx_val or adx_val >= float(rs.get("adx_max", 20.0)):
            return False
        ema20 = ind.ema(close, 20); ema50 = ind.ema(close, 50)
        slope_max = float(rs.get("slope_max", 0.15))
        slope20 = abs(float(ema20.iloc[-1]) - float(ema20.iloc[-1 - n_slope])) / atr
        slope50 = abs(float(ema50.iloc[-1]) - float(ema50.iloc[-1 - n_slope])) / atr
        return slope20 <= slope_max and slope50 <= slope_max

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

        # Conmutación por régimen: en RANGE (detección robusta) silencia a los
        # agentes tendenciales y potencia la reversión, sube el umbral de score y
        # reduce el riesgo. En TENDENCIA no toca nada (estrategia intacta).
        rs = self.regime_switch
        in_range = bool(rs.get("enabled")) and self._detect_range(md)
        threshold = self.buy_threshold
        if in_range:
            rev = set(rs.get("reversion_agents", ["range_reversion"]))
            trend_damp = float(rs.get("trend_damp", 0.0))
            rev_boost = float(rs.get("reversion_boost", 2.0))
            weights = {name: (w * rev_boost if name in rev else w * trend_damp)
                       for name, w in weights.items()}
            threshold = float(rs.get("buy_threshold", 0.25))

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

        signal = SignalType.from_sign(score, deadband=threshold)
        if conflict:
            signal = SignalType.WAIT

        confidence = min(100.0, abs(score) * 100.0)

        # Riesgo consolidado: media ponderada de estimated_risk de todos.
        risk = self._weighted_risk(decisions, weights)

        # Veto agregado (riesgo/noticias = bloqueo total; correlación = direccional).
        vetoed, veto_reason = self._check_veto(decisions, signal)
        if vetoed:
            signal = SignalType.WAIT

        # SL/TP consolidados a partir de los agentes que coinciden con la señal
        # (solo los que tienen peso: en RANGE excluye a los tendenciales silenciados).
        stop_loss, take_profit = self._consolidate_levels(actionable, signal, weights)

        # Gestión de riesgo: aprueba/veta y dimensiona.
        position_size = None
        if signal is not SignalType.WAIT and not vetoed:
            # En RANGE reduce el riesgo por operación (por defecto 0.5%).
            _saved_risk = self.risk_manager.params.risk_per_trade_pct
            if in_range:
                self.risk_manager.params.risk_per_trade_pct = float(rs.get("risk_pct", 0.5))
            try:
                rd = self.risk_manager.evaluate(
                    signal, md.price, stop_loss, agent_veto=vetoed, veto_reason=veto_reason
                )
            finally:
                self.risk_manager.params.risk_per_trade_pct = _saved_risk
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
        """Retroalimenta la ponderación con el resultado real (desde un `MarketData`)."""
        self.learn(decisions, md.regime, profitable)

    def learn(
        self, decisions: Sequence[AgentDecision], regime: MarketRegime, profitable: bool
    ) -> None:
        """Actualiza la ponderación con el resultado real de una operación.

        Un agente "acertó" si su señal direccional coincidió con el resultado
        (operación ganadora en su dirección). Se separa de `feedback` para poder
        alimentarla en vivo con solo el régimen (sin arrastrar el `MarketData`).
        """
        for d in decisions:
            if not d.is_actionable:
                continue
            self.weighting.update(d.agent_name, regime, profitable)
        # Retroalimentación conjunta para meta-modelos de stacking.
        self.weighting.observe(decisions, regime, profitable)

    # ---- Internos --------------------------------------------------------
    @staticmethod
    def _weighted_risk(decisions: Sequence[AgentDecision], weights: Dict[str, float]) -> float:
        num = sum(weights.get(d.agent_name, 1.0) * d.estimated_risk for d in decisions)
        den = sum(weights.get(d.agent_name, 1.0) for d in decisions)
        return (num / den) if den > 0 else 50.0

    @staticmethod
    def _check_veto(decisions: Sequence[AgentDecision], signal: SignalType = SignalType.WAIT):
        """Veto de bloqueo total (metadata['veto']) o DIRECCIONAL.

        Un agente puede vetar solo una dirección con metadata['veto_signal'] =
        SignalType.BUY/SELL: cancela la operación únicamente si la señal agregada
        coincide con esa dirección (p. ej. correlación que solo frena compras
        cuando la cesta contradice con fuerza, sin bloquear las ventas).
        """
        for d in decisions:
            if d.metadata.get("veto"):
                return True, d.metadata.get("veto_reason") or f"Veto de {d.agent_name}"
            vs = d.metadata.get("veto_signal")
            if vs is not None and signal is not SignalType.WAIT and vs is signal:
                return True, d.metadata.get("veto_reason") or f"Veto direccional de {d.agent_name}"
        return False, None

    @staticmethod
    def _consolidate_levels(actionable: Sequence[AgentDecision], signal: SignalType,
                            weights: Optional[Dict[str, float]] = None):
        if signal is SignalType.WAIT:
            return None, None
        w = weights or {}
        keep = [d for d in actionable if d.signal is signal and w.get(d.agent_name, 1.0) > 1e-6]
        if not keep:  # todos los que coinciden están silenciados: usa todos como respaldo
            keep = [d for d in actionable if d.signal is signal]
        sls = [d.stop_loss for d in keep if d.stop_loss]
        tps = [d.take_profit for d in keep if d.take_profit]
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
