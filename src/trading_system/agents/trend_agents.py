"""Agentes de tendencia y momentum."""
from __future__ import annotations

import numpy as np

from ..core import AgentDecision, BaseAgent, MarketData, SignalType, Timeframe, register_agent
from ..data import indicators as ind
from .helpers import atr_sl_tp


@register_agent("trend_mtf")
class TrendMultiTimeframeAgent(BaseAgent):
    """Alineación de EMAs en múltiples marcos temporales.

    Vota BUY si la EMA rápida está sobre la lenta en los timeframes disponibles
    (con más peso a los superiores). La convicción crece con el grado de
    alineación entre timeframes.
    """

    category = "trend"

    def analyze(self, md: MarketData) -> AgentDecision:
        tfs = [Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1]
        weights = {Timeframe.M15: 1.0, Timeframe.H1: 1.5, Timeframe.H4: 2.0, Timeframe.D1: 2.5}
        fast = int(self.config.get("ema_fast", 20))
        slow = int(self.config.get("ema_slow", 50))

        score = 0.0
        total = 0.0
        detail = []
        for tf in tfs:
            if not md.has(tf):
                continue
            df = md.frame(tf)
            if len(df) < slow + 2:
                continue
            ema_f = ind.ema(df["close"], fast).iloc[-1]
            ema_s = ind.ema(df["close"], slow).iloc[-1]
            w = weights[tf]
            total += w
            if ema_f > ema_s:
                score += w
                detail.append(f"{tf.name}:up")
            else:
                score -= w
                detail.append(f"{tf.name}:down")

        if total == 0:
            return self._wait("Datos insuficientes para tendencia")

        norm = score / total  # [-1, 1]
        confidence = min(100.0, abs(norm) * 100.0)
        signal = SignalType.from_sign(norm, deadband=0.2)
        sl, tp = atr_sl_tp(md.price, md.regime.atr, signal)
        risk = 40.0 if signal is SignalType.WAIT else 30.0 + (1 - abs(norm)) * 40.0
        return self._decision(
            signal,
            confidence,
            f"Alineación EMA {fast}/{slow} multi-TF ({', '.join(detail)}) norm={norm:.2f}",
            estimated_risk=risk,
            stop_loss=sl,
            take_profit=tp,
            norm=norm,
        )


@register_agent("momentum")
class MomentumAgent(BaseAgent):
    """Fuerza direccional reciente vía ROC del timeframe primario."""

    category = "momentum"

    def analyze(self, md: MarketData) -> AgentDecision:
        period = int(self.config.get("roc_period", 10))
        df = md.frame(md.primary_tf)
        if len(df) < period + 2:
            return self._wait("Datos insuficientes para momentum")

        roc = ind.roc(df["close"], period).iloc[-1]
        if np.isnan(roc):
            return self._wait("ROC no disponible")

        # Umbral relativo a la volatilidad (ATR% aproximado).
        threshold = float(self.config.get("threshold_pct", 0.15))
        signal = SignalType.from_sign(roc, deadband=threshold)
        confidence = min(100.0, abs(roc) / (threshold * 4) * 100.0)
        sl, tp = atr_sl_tp(md.price, md.regime.atr, signal)
        return self._decision(
            signal,
            confidence,
            f"ROC({period})={roc:.2f}% (umbral ±{threshold}%)",
            estimated_risk=45.0,
            stop_loss=sl,
            take_profit=tp,
            roc=float(roc),
        )


@register_agent("technical")
class TechnicalIndicatorAgent(BaseAgent):
    """Composite de RSI + MACD + ADX + cruce EMA sobre el timeframe primario."""

    category = "technical"

    def analyze(self, md: MarketData) -> AgentDecision:
        df = md.frame(md.primary_tf)
        if len(df) < 60:
            return self._wait("Datos insuficientes para indicadores")

        close = df["close"]
        rsi = ind.rsi(close, 14).iloc[-1]
        macd_df = ind.macd(close)
        macd_hist = macd_df["hist"].iloc[-1]
        adx = ind.adx(df, 14).iloc[-1]
        ema_f = ind.ema(close, 20).iloc[-1]
        ema_s = ind.ema(close, 50).iloc[-1]

        votes = 0.0
        reasons = []

        # RSI
        if not np.isnan(rsi):
            if rsi < 35:
                votes += 1; reasons.append(f"RSI={rsi:.0f}<35 (sobreventa)")
            elif rsi > 65:
                votes -= 1; reasons.append(f"RSI={rsi:.0f}>65 (sobrecompra)")
        # MACD
        if not np.isnan(macd_hist):
            if macd_hist > 0:
                votes += 1; reasons.append("MACD hist>0")
            else:
                votes -= 1; reasons.append("MACD hist<0")
        # EMA cross
        if ema_f > ema_s:
            votes += 1; reasons.append("EMA20>EMA50")
        else:
            votes -= 1; reasons.append("EMA20<EMA50")

        norm = votes / 3.0
        # ADX modula la confianza (tendencia fuerte => más convicción).
        adx_factor = 0.5 if np.isnan(adx) else min(1.0, adx / 40.0)
        confidence = min(100.0, abs(norm) * 100.0 * (0.5 + 0.5 * adx_factor))
        signal = SignalType.from_sign(norm, deadband=0.34)
        sl, tp = atr_sl_tp(md.price, md.regime.atr, signal)
        return self._decision(
            signal,
            confidence,
            "; ".join(reasons) + f"; ADX={0 if np.isnan(adx) else adx:.0f}",
            estimated_risk=40.0,
            stop_loss=sl,
            take_profit=tp,
            rsi=float(rsi) if not np.isnan(rsi) else None,
        )
