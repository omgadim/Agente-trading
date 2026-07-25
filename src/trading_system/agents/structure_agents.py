"""Agentes de estructura de mercado, S/R, velas y sesión."""
from __future__ import annotations

from datetime import timezone

import numpy as np

from ..core import AgentDecision, BaseAgent, MarketData, SignalType, Timeframe, register_agent
from ..data import indicators as ind
from .helpers import atr_sl_tp


@register_agent("market_structure")
class MarketStructureAgent(BaseAgent):
    """Detecta estructura por swings: HH/HL (alcista) vs LH/LL (bajista).

    Usa pivotes fractales para identificar los dos últimos máximos y mínimos y
    determina si la estructura es de continuación alcista, bajista o rota (posible
    cambio de carácter / CHoCH).
    """

    category = "structure"

    def analyze(self, md: MarketData) -> AgentDecision:
        tf = Timeframe.H1 if md.has(Timeframe.H1) else md.primary_tf
        df = md.frame(tf)
        if len(df) < 30:
            return self._wait("Datos insuficientes para estructura")

        highs_mask = ind.swing_highs(df["high"], 2, 2)
        lows_mask = ind.swing_lows(df["low"], 2, 2)
        swing_highs = df["high"][highs_mask]
        swing_lows = df["low"][lows_mask]

        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return self._wait("Swings insuficientes")

        hh = swing_highs.iloc[-1] > swing_highs.iloc[-2]
        hl = swing_lows.iloc[-1] > swing_lows.iloc[-2]
        lh = swing_highs.iloc[-1] < swing_highs.iloc[-2]
        ll = swing_lows.iloc[-1] < swing_lows.iloc[-2]

        if hh and hl:
            signal, conf, expl = SignalType.BUY, 75.0, "Estructura alcista (HH+HL)"
        elif lh and ll:
            signal, conf, expl = SignalType.SELL, 75.0, "Estructura bajista (LH+LL)"
        elif hh and ll:
            signal, conf, expl = SignalType.WAIT, 30.0, "Estructura en expansión (indecisa)"
        else:
            signal, conf, expl = SignalType.WAIT, 25.0, "Estructura mixta / posible CHoCH"

        sl, tp = atr_sl_tp(md.price, md.regime.atr, signal)
        return self._decision(
            signal, conf, expl, estimated_risk=40.0, stop_loss=sl, take_profit=tp
        )


@register_agent("support_resistance")
class SupportResistanceAgent(BaseAgent):
    """Reacción del precio frente a zonas de soporte/resistencia por swings."""

    category = "structure"

    def analyze(self, md: MarketData) -> AgentDecision:
        tf = Timeframe.H1 if md.has(Timeframe.H1) else md.primary_tf
        df = md.frame(tf)
        if len(df) < 40:
            return self._wait("Datos insuficientes para S/R")

        atr = md.regime.atr or float(ind.atr(df, 14).iloc[-1])
        price = md.price
        highs = df["high"][ind.swing_highs(df["high"], 3, 3)]
        lows = df["low"][ind.swing_lows(df["low"], 3, 3)]
        if highs.empty or lows.empty or atr <= 0:
            return self._wait("Sin niveles S/R válidos")

        nearest_res = highs[highs >= price].min() if (highs >= price).any() else np.nan
        nearest_sup = lows[lows <= price].max() if (lows <= price).any() else np.nan
        tol = 0.5 * atr

        # Rebote en soporte -> BUY; rechazo en resistencia -> SELL.
        if not np.isnan(nearest_sup) and (price - nearest_sup) <= tol:
            signal, expl = SignalType.BUY, f"Precio en soporte {nearest_sup:.2f}"
            conf = 65.0
        elif not np.isnan(nearest_res) and (nearest_res - price) <= tol:
            signal, expl = SignalType.SELL, f"Precio en resistencia {nearest_res:.2f}"
            conf = 65.0
        else:
            return self._decision(
                SignalType.WAIT, 20.0, "Precio lejos de zonas S/R", estimated_risk=40.0
            )

        sl, tp = atr_sl_tp(price, atr, signal)
        return self._decision(
            signal, conf, expl, estimated_risk=45.0, stop_loss=sl, take_profit=tp,
            support=None if np.isnan(nearest_sup) else float(nearest_sup),
            resistance=None if np.isnan(nearest_res) else float(nearest_res),
        )


@register_agent("candlestick")
class CandlestickPatternAgent(BaseAgent):
    """Patrones de vela: engulfing y pin bar sobre el timeframe primario."""

    category = "price_action"

    def analyze(self, md: MarketData) -> AgentDecision:
        df = md.frame(md.primary_tf)
        if len(df) < 3:
            return self._wait("Datos insuficientes para velas")

        o, h, l, c = (df[x] for x in ("open", "high", "low", "close"))
        o1, c1 = o.iloc[-1], c.iloc[-1]
        o2, c2 = o.iloc[-2], c.iloc[-2]
        rng = h.iloc[-1] - l.iloc[-1]
        body = abs(c1 - o1)

        signal, conf, expl = SignalType.WAIT, 0.0, "Sin patrón relevante"

        # Bullish engulfing
        if c2 < o2 and c1 > o1 and c1 >= o2 and o1 <= c2:
            signal, conf, expl = SignalType.BUY, 60.0, "Envolvente alcista"
        # Bearish engulfing
        elif c2 > o2 and c1 < o1 and c1 <= o2 and o1 >= c2:
            signal, conf, expl = SignalType.SELL, 60.0, "Envolvente bajista"
        # Pin bar (mecha larga)
        elif rng > 0 and body / rng < 0.35:
            upper = h.iloc[-1] - max(o1, c1)
            lower = min(o1, c1) - l.iloc[-1]
            if lower > 2 * body and lower > upper:
                signal, conf, expl = SignalType.BUY, 55.0, "Pin bar alcista (mecha inferior)"
            elif upper > 2 * body and upper > lower:
                signal, conf, expl = SignalType.SELL, 55.0, "Pin bar bajista (mecha superior)"

        sl, tp = atr_sl_tp(md.price, md.regime.atr, signal)
        return self._decision(
            signal, conf, expl, estimated_risk=50.0, stop_loss=sl, take_profit=tp
        )


@register_agent("session")
class SessionAgent(BaseAgent):
    """Filtro de sesión: favorece las killzones de Londres/Nueva York.

    El Oro concentra su mejor liquidez y direccionalidad en las sesiones de
    Londres y NY. Fuera de esas ventanas eleva el riesgo (rango asiático).
    """

    category = "context"

    def analyze(self, md: MarketData) -> AgentDecision:
        hour = md.timestamp.astimezone(timezone.utc).hour
        # Ventanas UTC aproximadas.
        london = 7 <= hour < 11
        newyork = 12 <= hour < 16
        if london or newyork:
            zone = "Londres" if london else "Nueva York"
            return self._decision(
                SignalType.WAIT, 0.0, f"Killzone {zone} activa (buena liquidez)",
                estimated_risk=30.0, session=zone, favorable=True,
            )
        return self._decision(
            SignalType.WAIT, 0.0, "Fuera de killzones (liquidez reducida)",
            estimated_risk=65.0, favorable=False,
        )
