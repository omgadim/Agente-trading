"""Agentes de volatilidad y volumen."""
from __future__ import annotations

import numpy as np

from ..core import (
    AgentDecision,
    BaseAgent,
    MarketData,
    SignalType,
    VolatilityRegime,
    register_agent,
)
from ..data import indicators as ind


@register_agent("volatility")
class VolatilityAgent(BaseAgent):
    """Interpreta el régimen de ATR.

    No genera dirección por sí mismo: informa del régimen de volatilidad y modula
    el riesgo. En volatilidad extrema recomienda esperar (mayor riesgo de ruido).
    """

    category = "volatility"

    def analyze(self, md: MarketData) -> AgentDecision:
        df = md.frame(md.primary_tf)
        if len(df) < 30:
            return self._wait("Datos insuficientes para ATR")

        atr_series = ind.atr(df, 14)
        atr_val = float(atr_series.iloc[-1])
        atr_pct = atr_val / md.price * 100.0 if md.price else 0.0
        regime = md.regime.volatility

        # Es un agente de contexto: siempre WAIT direccional, pero aporta riesgo.
        if regime is VolatilityRegime.HIGH:
            risk = 80.0
            expl = f"Volatilidad ALTA (ATR%={atr_pct:.2f}): operar con cautela"
        elif regime is VolatilityRegime.LOW:
            risk = 30.0
            expl = f"Volatilidad BAJA (ATR%={atr_pct:.2f}): rangos estrechos"
        else:
            risk = 50.0
            expl = f"Volatilidad NORMAL (ATR%={atr_pct:.2f})"

        return self._decision(
            SignalType.WAIT,
            confidence=0.0,
            explanation=expl,
            estimated_risk=risk,
            atr=atr_val,
            atr_pct=atr_pct,
            regime=regime.value,
        )


@register_agent("volume")
class VolumeAgent(BaseAgent):
    """Confirmación por volumen (o tick volume).

    Compara el volumen reciente contra su media. Un impulso de precio con volumen
    por encima de la media refuerza la dirección de la última vela.
    """

    category = "volume"

    def analyze(self, md: MarketData) -> AgentDecision:
        df = md.frame(md.primary_tf)
        if len(df) < 30 or "volume" not in df:
            return self._wait("Datos de volumen insuficientes")

        vol = df["volume"]
        avg = ind.sma(vol, 20).iloc[-1]
        cur = float(vol.iloc[-1])
        if np.isnan(avg) or avg <= 0:
            return self._wait("Media de volumen no disponible")

        ratio = cur / avg
        last_ret = float(df["close"].iloc[-1] - df["open"].iloc[-1])
        if ratio < 1.2 or last_ret == 0:
            return self._decision(
                SignalType.WAIT,
                confidence=20.0,
                explanation=f"Volumen sin confirmación (x{ratio:.2f} de la media)",
                estimated_risk=50.0,
                vol_ratio=ratio,
            )

        signal = SignalType.BUY if last_ret > 0 else SignalType.SELL
        confidence = min(100.0, (ratio - 1.0) * 80.0)
        return self._decision(
            signal,
            confidence,
            f"Volumen x{ratio:.2f} confirma vela {'alcista' if last_ret>0 else 'bajista'}",
            estimated_risk=45.0,
            vol_ratio=ratio,
        )
