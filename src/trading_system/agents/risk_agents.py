"""Agentes de gestión: riesgo y control de operaciones abiertas."""
from __future__ import annotations

from ..core import (
    AgentDecision,
    BaseAgent,
    MarketData,
    SignalType,
    VolatilityRegime,
    register_agent,
)
from ..data import indicators as ind
from .helpers import atr_sl_tp


@register_agent("risk_management")
class RiskManagementAgent(BaseAgent):
    """Evalúa el riesgo del entorno y propone SL/TP de referencia por ATR.

    Es un agente de contexto (no direcciona). Su `estimated_risk` sube con la
    volatilidad y aporta niveles de SL/TP que el Supervisor/RiskManager pueden
    consolidar. Además expone en metadata si recomienda vetar la operación.
    """

    category = "risk"

    def analyze(self, md: MarketData) -> AgentDecision:
        df = md.frame(md.primary_tf)
        atr = md.regime.atr or (float(ind.atr(df, 14).iloc[-1]) if len(df) >= 20 else 0.0)

        base_risk = {
            VolatilityRegime.LOW: 30.0,
            VolatilityRegime.NORMAL: 50.0,
            VolatilityRegime.HIGH: 80.0,
        }[md.regime.volatility]

        max_atr_pct = float(self.config.get("max_atr_pct", 2.5))
        atr_pct = (atr / md.price * 100.0) if md.price else 0.0
        veto = atr_pct > max_atr_pct

        # SL/TP de referencia (dirección neutra: se calculan ambos lados fuera).
        sl_buy, tp_buy = atr_sl_tp(md.price, atr, SignalType.BUY,
                                   self.config.get("sl_mult", 1.5),
                                   self.config.get("tp_mult", 2.5))

        expl = (
            f"Riesgo de entorno {base_risk:.0f}/100; ATR%={atr_pct:.2f}"
            + (" — VETO: volatilidad excesiva" if veto else "")
        )
        return self._decision(
            SignalType.WAIT,
            confidence=0.0,
            explanation=expl,
            estimated_risk=base_risk,
            stop_loss=sl_buy,
            take_profit=tp_buy,
            atr=atr,
            atr_pct=atr_pct,
            veto=veto,
            veto_reason="ATR% excede el máximo permitido" if veto else None,
        )


@register_agent("open_trades_control")
class OpenTradesControlAgent(BaseAgent):
    """Gestiona posiciones abiertas: break-even y trailing por ATR.

    Recibe las posiciones abiertas vía `context['open_positions']` (inyectado por
    el motor). En Fase 1 emite recomendaciones de gestión en metadata; en Fase 3
    el `MT5Broker` las aplicará (modificar SL, cierre parcial).
    """

    category = "management"

    def analyze(self, md: MarketData) -> AgentDecision:
        positions = self.config.get("open_positions") or []
        if not positions:
            return self._decision(
                SignalType.WAIT, 0.0, "Sin posiciones abiertas",
                estimated_risk=0.0, actions=[],
            )

        atr = md.regime.atr
        actions = []
        for pos in positions:
            entry = float(pos.get("entry_price", md.price))
            direction = pos.get("direction", "BUY").upper()
            profit_atr = ((md.price - entry) if direction == "BUY" else (entry - md.price))
            profit_in_atr = profit_atr / atr if atr else 0.0
            if profit_in_atr >= 1.0:
                actions.append({
                    "ticket": pos.get("ticket"),
                    "action": "move_to_break_even",
                    "new_sl": entry,
                })
            if profit_in_atr >= 2.0 and atr:
                trail = (md.price - atr) if direction == "BUY" else (md.price + atr)
                actions.append({
                    "ticket": pos.get("ticket"),
                    "action": "trailing_stop",
                    "new_sl": trail,
                })

        expl = (
            f"{len(positions)} posición(es); {len(actions)} acción(es) de gestión"
            if actions else f"{len(positions)} posición(es) sin acción requerida"
        )
        return self._decision(
            SignalType.WAIT, 0.0, expl, estimated_risk=0.0, actions=actions,
        )
