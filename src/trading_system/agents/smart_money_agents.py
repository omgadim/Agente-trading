"""Agentes de price action institucional (Smart Money Concepts) — Fase 2.

Todos consumen el motor compartido `data.structure`. Operan sobre un timeframe de
estructura (H1 si está disponible; si no, el primario) para reducir ruido.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from ..core import AgentDecision, BaseAgent, MarketData, SignalType, Timeframe, register_agent
from ..data import structure as st
from .helpers import atr_sl_tp


def _structure_frame(md: MarketData) -> pd.DataFrame:
    """Timeframe preferente para análisis estructural."""
    tf = Timeframe.H1 if md.has(Timeframe.H1) else md.primary_tf
    return md.frame(tf)


def _atr(md: MarketData, df: pd.DataFrame) -> float:
    from ..data import indicators as ind

    if md.regime.atr:
        return md.regime.atr
    return float(ind.atr(df, 14).iloc[-1]) if len(df) >= 16 else 0.0


@register_agent("fair_value_gap")
class FairValueGapAgent(BaseAgent):
    """Opera la mitigación de Fair Value Gaps.

    Si el precio actual está retrocediendo dentro de un FVG alcista reciente, se
    espera que actúe como soporte (BUY); dentro de un FVG bajista, como resistencia
    (SELL). La convicción crece con el tamaño del hueco relativo al ATR.
    """

    category = "smart_money"

    def analyze(self, md: MarketData) -> AgentDecision:
        df = _structure_frame(md)
        if len(df) < 20:
            return self._wait("Datos insuficientes para FVG")
        atr = _atr(md, df)
        fvgs = st.find_fvgs(df, min_atr_frac=float(self.config.get("min_atr_frac", 0.25)))
        if not fvgs:
            return self._wait("Sin FVG relevantes")

        price = md.price
        # FVG no mitigado más reciente que contiene al precio actual.
        active = [f for f in fvgs if f.contains(price)]
        if not active:
            return self._decision(SignalType.WAIT, 15.0, "Precio fuera de FVG",
                                  estimated_risk=40.0)
        fvg = active[-1]
        signal = SignalType.BUY if fvg.kind == "bullish" else SignalType.SELL
        conf = min(90.0, 40.0 + (fvg.size / atr * 40.0 if atr else 0.0))
        sl, tp = atr_sl_tp(price, atr, signal)
        return self._decision(
            signal, conf,
            f"Mitigación de FVG {fvg.kind} [{fvg.bottom:.2f}, {fvg.top:.2f}]",
            estimated_risk=45.0, stop_loss=sl, take_profit=tp,
            fvg_size=fvg.size,
        )


@register_agent("order_blocks")
class OrderBlocksAgent(BaseAgent):
    """Opera el retest de Order Blocks.

    Cuando el precio regresa a un order block alcista (última vela bajista antes de
    un impulso alcista), se busca la continuación (BUY); simétrico para bajistas.
    """

    category = "smart_money"

    def analyze(self, md: MarketData) -> AgentDecision:
        df = _structure_frame(md)
        if len(df) < 20:
            return self._wait("Datos insuficientes para Order Blocks")
        atr = _atr(md, df)
        obs = st.find_order_blocks(df, impulse_atr=float(self.config.get("impulse_atr", 1.0)))
        if not obs:
            return self._wait("Sin Order Blocks detectados")

        price = md.price
        tol = 0.25 * atr if atr else 0.0
        active = [
            ob for ob in obs if ob.bottom - tol <= price <= ob.top + tol
        ]
        if not active:
            return self._decision(SignalType.WAIT, 15.0, "Precio lejos de Order Blocks",
                                  estimated_risk=40.0)
        ob = active[-1]
        signal = SignalType.BUY if ob.kind == "bullish" else SignalType.SELL
        conf = 65.0
        sl, tp = atr_sl_tp(price, atr, signal)
        return self._decision(
            signal, conf,
            f"Retest de Order Block {ob.kind} [{ob.bottom:.2f}, {ob.top:.2f}]",
            estimated_risk=45.0, stop_loss=sl, take_profit=tp,
        )


@register_agent("liquidity_sweep")
class LiquiditySweepAgent(BaseAgent):
    """Detecta barridos de liquidez (stop hunts) y opera la reversión.

    Un barrido bajista (mecha sobre máximos previos que cierra por debajo) sugiere
    trampa de compradores -> SELL. Un barrido alcista de mínimos -> BUY.
    """

    category = "smart_money"

    def analyze(self, md: MarketData) -> AgentDecision:
        df = _structure_frame(md)
        if len(df) < 20:
            return self._wait("Datos insuficientes para liquidez")
        atr = _atr(md, df)
        swings = st.find_swings(df, 2, 2)
        tol = 0.1 * atr if atr else 0.0
        sweep = st.detect_sweep(df, swings, tolerance=tol)
        if sweep is None:
            return self._decision(SignalType.WAIT, 15.0, "Sin barrido de liquidez",
                                  estimated_risk=40.0)
        signal = SignalType.BUY if sweep.kind == "bullish" else SignalType.SELL
        sl, tp = atr_sl_tp(md.price, atr, signal)
        return self._decision(
            signal, 70.0,
            f"Barrido {sweep.kind} de liquidez en {sweep.level:.2f} (reversión)",
            estimated_risk=50.0, stop_loss=sl, take_profit=tp,
            swept_level=sweep.level,
        )


@register_agent("smart_money")
class SmartMoneyConceptsAgent(BaseAgent):
    """Confluencia SMC: estructura (BOS/CHoCH) + zonas premium/discount.

    En estructura alcista y precio en *discount* (bajo el equilibrio del rango) hay
    ventaja compradora; en estructura bajista y precio en *premium*, vendedora.
    """

    category = "smart_money"

    def analyze(self, md: MarketData) -> AgentDecision:
        df = _structure_frame(md)
        if len(df) < 30:
            return self._wait("Datos insuficientes para SMC")
        atr = _atr(md, df)
        swings = st.find_swings(df, 2, 2)
        state = st.market_structure(swings)
        hi, lo, eq = st.premium_discount(df, lookback=int(self.config.get("lookback", 50)))
        price = md.price
        in_discount = price < eq
        in_premium = price > eq

        signal = SignalType.WAIT
        reason = f"Estructura {state.trend}/{state.event}; "
        conf = 30.0
        if state.trend == "bullish" and in_discount:
            signal, conf = SignalType.BUY, 72.0
            reason += "precio en discount -> ventaja compradora"
        elif state.trend == "bearish" and in_premium:
            signal, conf = SignalType.SELL, 72.0
            reason += "precio en premium -> ventaja vendedora"
        else:
            zone = "discount" if in_discount else "premium"
            reason += f"sin confluencia (precio en {zone})"

        sl, tp = atr_sl_tp(price, atr, signal)
        return self._decision(
            signal, conf, reason, estimated_risk=45.0, stop_loss=sl, take_profit=tp,
            equilibrium=eq, trend=state.trend, event=state.event,
        )


@register_agent("wyckoff")
class WyckoffAgent(BaseAgent):
    """Springs (acumulación) y upthrusts (distribución) sobre un rango.

    Detecta un rango de consolidación reciente y opera su ruptura falsa: un spring
    (barrido bajo el rango que recupera) es acumulación -> BUY; un upthrust
    (barrido sobre el rango que falla) es distribución -> SELL.
    """

    category = "smart_money"

    def analyze(self, md: MarketData) -> AgentDecision:
        df = _structure_frame(md)
        lookback = int(self.config.get("lookback", 30))
        if len(df) < lookback + 2:
            return self._wait("Datos insuficientes para Wyckoff")
        atr = _atr(md, df)

        # Rango definido por las velas previas (excluye las 2 últimas).
        window = df.iloc[-(lookback + 2):-2]
        range_hi = float(window["high"].max())
        range_lo = float(window["low"].min())
        last = df.iloc[-1]
        low, high, close = float(last["low"]), float(last["high"]), float(last["close"])
        tol = 0.1 * atr if atr else 0.0

        signal, conf, reason = SignalType.WAIT, 20.0, "Sin evento Wyckoff"
        if low < range_lo - tol and close > range_lo:
            signal, conf, reason = SignalType.BUY, 68.0, f"Spring bajo {range_lo:.2f} (acumulación)"
        elif high > range_hi + tol and close < range_hi:
            signal, conf, reason = SignalType.SELL, 68.0, f"Upthrust sobre {range_hi:.2f} (distribución)"

        sl, tp = atr_sl_tp(md.price, atr, signal)
        return self._decision(
            signal, conf, reason, estimated_risk=50.0, stop_loss=sl, take_profit=tp,
            range_hi=range_hi, range_lo=range_lo,
        )


# Ratios de referencia de los patrones armónicos (retroceso B y punto D sobre XA).
_HARMONIC_PATTERNS = {
    "Gartley": {"b": (0.618, 0.05), "d": (0.786, 0.05)},
    "Bat": {"b": (0.45, 0.09), "d": (0.886, 0.05)},
    "Butterfly": {"b": (0.786, 0.05), "d": (1.41, 0.20)},
    "Crab": {"b": (0.5, 0.12), "d": (1.618, 0.06)},
}


@register_agent("harmonic")
class HarmonicPatternAgent(BaseAgent):
    """Reconoce patrones armónicos XABCD (Gartley/Bat/Butterfly/Crab).

    Usa los últimos 5 pivotes alternados y valida los ratios de Fibonacci
    característicos (retroceso de B y proyección del punto D sobre la pierna XA).
    La finalización en un mínimo -> BUY; en un máximo -> SELL.
    """

    category = "price_action"

    def analyze(self, md: MarketData) -> AgentDecision:
        df = _structure_frame(md)
        if len(df) < 40:
            return self._wait("Datos insuficientes para armónicos")
        atr = _atr(md, df)
        swings = st.alternating_swings(st.find_swings(df, 2, 2))
        if len(swings) < 5:
            return self._wait("Pivotes insuficientes para XABCD")

        x, a, b, c, d = swings[-5:]
        xa = abs(a.price - x.price)
        ab = abs(b.price - a.price)
        ad = abs(d.price - a.price)
        if xa <= 0:
            return self._wait("Pierna XA nula")
        b_ret = ab / xa
        d_ret = ad / xa

        match = self._match_pattern(b_ret, d_ret)
        if match is None:
            return self._decision(
                SignalType.WAIT, 20.0,
                f"Sin patrón armónico (B={b_ret:.2f}, D={d_ret:.2f})",
                estimated_risk=45.0,
            )
        name, err = match
        signal = SignalType.BUY if d.kind == "low" else SignalType.SELL
        conf = max(45.0, 85.0 - err * 300.0)
        sl, tp = atr_sl_tp(md.price, atr, signal)
        return self._decision(
            signal, conf, f"Patrón {name} completado en D={d.price:.2f}",
            estimated_risk=50.0, stop_loss=sl, take_profit=tp,
            pattern=name, b_ret=b_ret, d_ret=d_ret,
        )

    @staticmethod
    def _match_pattern(b_ret: float, d_ret: float) -> Optional[tuple]:
        best: Optional[tuple] = None
        for name, spec in _HARMONIC_PATTERNS.items():
            b_target, b_tol = spec["b"]
            d_target, d_tol = spec["d"]
            if abs(b_ret - b_target) <= b_tol and abs(d_ret - d_target) <= d_tol:
                err = abs(b_ret - b_target) + abs(d_ret - d_target)
                if best is None or err < best[1]:
                    best = (name, err)
        return best
