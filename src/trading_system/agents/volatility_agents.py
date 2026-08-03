"""Agentes de volatilidad y volumen."""
from __future__ import annotations

import numpy as np

from ..core import (
    AgentDecision,
    BaseAgent,
    MarketData,
    SignalType,
    Timeframe,
    VolatilityRegime,
    register_agent,
)
from ..data import indicators as ind
from ..data import structure as st
from .helpers import atr_sl_tp


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


@register_agent("bollinger_stoch")
class BollingerStochasticAgent(BaseAgent):
    """Reversión en rango: Bandas de Bollinger + Estocástico.

    Opera reversiones de alta calidad (donde el sistema, sesgado a tendencia, es
    flojo): compra cuando el precio toca/perfora la banda INFERIOR y el
    estocástico está sobrevendido y **girando al alza**; vende en la banda
    superior con estocástico sobrecomprado girando a la baja. Para no pelear con
    tendencias fuertes, solo actúa si el ADX es bajo (mercado en rango).
    """

    category = "technical"

    def analyze(self, md: MarketData) -> AgentDecision:
        df = md.frame(md.primary_tf)
        period = int(self.config.get("bb_period", 20))
        if len(df) < period + 5:
            return self._wait("Datos insuficientes para Bollinger/Estocástico")

        bb = ind.bollinger(df["close"], period, float(self.config.get("bb_mult", 2.0)))
        st = ind.stochastic(df, int(self.config.get("k_period", 14)),
                            int(self.config.get("d_period", 3)))
        adx = float(ind.adx(df, 14).iloc[-1])
        upper, lower = bb["upper"].iloc[-1], bb["lower"].iloc[-1]
        k, d = st["k"].iloc[-1], st["d"].iloc[-1]
        k_prev, d_prev = st["k"].iloc[-2], st["d"].iloc[-2]
        price = float(df["close"].iloc[-1])
        atr = md.regime.atr or float(ind.atr(df, 14).iloc[-1])

        if np.isnan(upper) or np.isnan(k) or atr <= 0:
            return self._wait("Indicadores no disponibles")

        # Solo reversión en rango (ADX bajo); en tendencia fuerte no interfiere.
        max_adx = float(self.config.get("max_adx", 25.0))
        os_level = float(self.config.get("oversold", 20.0))
        ob_level = float(self.config.get("overbought", 80.0))
        turning_up = k > d and k_prev <= d_prev
        turning_down = k < d and k_prev >= d_prev

        signal, conf, reason = SignalType.WAIT, 20.0, "Sin señal de reversión"
        if not np.isnan(adx) and adx <= max_adx:
            if price <= lower and k < os_level and turning_up:
                signal, conf = SignalType.BUY, 68.0
                reason = f"Banda inferior + estocástico {k:.0f} girando (reversión al alza)"
            elif price >= upper and k > ob_level and turning_down:
                signal, conf = SignalType.SELL, 68.0
                reason = f"Banda superior + estocástico {k:.0f} girando (reversión a la baja)"

        sl, tp = atr_sl_tp(md.price, atr, signal)
        return self._decision(
            signal, conf, reason, estimated_risk=50.0, stop_loss=sl, take_profit=tp,
            adx=round(adx, 1) if not np.isnan(adx) else None,
        )


@register_agent("williams_r")
class WilliamsRAgent(BaseAgent):
    """Williams %R (Larry Williams): reversión por sobrecompra/sobreventa.

    Compra cuando %R sale de sobreventa (cruza al alza -80); vende cuando sale de
    sobrecompra (cruza a la baja -20). Nota: es primo del Estocástico, así que su
    aporte puede ser redundante; se valida con backtest.
    """

    category = "technical"

    def analyze(self, md: MarketData) -> AgentDecision:
        df = md.frame(md.primary_tf)
        period = int(self.config.get("period", 14))
        if len(df) < period + 3:
            return self._wait("Datos insuficientes para Williams %R")
        wr = ind.williams_r(df, period)
        w, w_prev = wr.iloc[-1], wr.iloc[-2]
        atr = md.regime.atr or float(ind.atr(df, 14).iloc[-1])
        if np.isnan(w) or np.isnan(w_prev) or atr <= 0:
            return self._wait("Williams %R no disponible")

        oversold = float(self.config.get("oversold", -80.0))
        overbought = float(self.config.get("overbought", -20.0))
        signal, conf, reason = SignalType.WAIT, 20.0, f"Williams %R={w:.0f} (neutral)"
        if w_prev <= oversold and w > oversold:
            signal, conf, reason = SignalType.BUY, 62.0, f"%R sale de sobreventa ({w:.0f})"
        elif w_prev >= overbought and w < overbought:
            signal, conf, reason = SignalType.SELL, 62.0, f"%R sale de sobrecompra ({w:.0f})"

        sl, tp = atr_sl_tp(md.price, atr, signal)
        return self._decision(
            signal, conf, reason, estimated_risk=50.0, stop_loss=sl, take_profit=tp,
            williams_r=round(float(w), 1),
        )


@register_agent("rsi_divergence")
class RsiDivergenceAgent(BaseAgent):
    """Divergencia precio/RSI en los pivotes (idea del indicador de divergencia).

    Divergencia REGULAR (reversión), con las definiciones estándar corregidas:
      - Bajista (SELL): precio hace un máximo más alto pero el RSI un máximo más bajo.
      - Alcista (BUY):  precio hace un mínimo más bajo pero el RSI un mínimo más alto.

    Es una señal CONTRARIAN: el meta-modelo aprende dónde pesarla y el risk manager
    le impone SL/TP (ATR 1.0/2.5) y el 1%. Con `max_adx` opcional solo opera en
    rango (ADX bajo), donde las reversiones rinden mejor que en tendencia.
    """

    category = "momentum"

    def analyze(self, md: MarketData) -> AgentDecision:
        tf = Timeframe.H1 if md.has(Timeframe.H1) else md.primary_tf
        df = md.frame(tf)
        if len(df) < 60:
            return self._wait("Datos insuficientes para divergencia")

        pivot = int(self.config.get("pivot", 5))
        rsi_period = int(self.config.get("rsi_period", 14))
        min_gap = float(self.config.get("min_rsi_gap", 3.0))
        max_bars = int(self.config.get("max_bars", 8))
        max_adx = self.config.get("max_adx")

        if max_adx is not None:
            adx = ind.adx(df, 14).to_numpy()
            if len(adx) and not np.isnan(adx[-1]) and adx[-1] > float(max_adx):
                return self._wait(f"ADX {adx[-1]:.0f}: sin reversión en tendencia")

        rsi = ind.rsi(df["close"], rsi_period).to_numpy()
        swings = st.find_swings(df, pivot, pivot)
        highs = [s for s in swings if s.kind == "high"]
        lows = [s for s in swings if s.kind == "low"]
        n = len(df)

        signal = SignalType.WAIT; conf = 0.0; expl = ""
        if len(highs) >= 2:
            h1, h2 = highs[-2], highs[-1]
            r1, r2 = rsi[h1.pos], rsi[h2.pos]
            if n - 1 - h2.pos <= max_bars and h2.price > h1.price and r2 < r1 - min_gap:
                signal = SignalType.SELL
                conf = 45.0 + min(30.0, r1 - r2)
                if r1 >= 65.0:
                    conf = min(85.0, conf + 8.0)
                expl = f"Divergencia bajista: precio HH, RSI {r1:.0f}->{r2:.0f}"
        if signal is SignalType.WAIT and len(lows) >= 2:
            l1, l2 = lows[-2], lows[-1]
            r1, r2 = rsi[l1.pos], rsi[l2.pos]
            if n - 1 - l2.pos <= max_bars and l2.price < l1.price and r2 > r1 + min_gap:
                signal = SignalType.BUY
                conf = 45.0 + min(30.0, r2 - r1)
                if r1 <= 35.0:
                    conf = min(85.0, conf + 8.0)
                expl = f"Divergencia alcista: precio LL, RSI {r1:.0f}->{r2:.0f}"

        if signal is SignalType.WAIT:
            return self._wait("Sin divergencia precio/RSI")
        sl, tp = atr_sl_tp(md.price, md.regime.atr, signal)
        return self._decision(signal, conf, expl, estimated_risk=48.0,
                              stop_loss=sl, take_profit=tp)
