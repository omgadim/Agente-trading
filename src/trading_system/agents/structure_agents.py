"""Agentes de estructura de mercado, S/R, velas y sesión."""
from __future__ import annotations

from datetime import timezone

import numpy as np

from ..core import AgentDecision, BaseAgent, MarketData, SignalType, Timeframe, register_agent
from ..data import indicators as ind
from ..data import structure as st
from .helpers import atr_sl_tp


@register_agent("market_structure")
class MarketStructureAgent(BaseAgent):
    """Estructura de mercado con seguimiento de tendencia (BOS / CHoCH).

    Portado del método Smart Money de LuxAlgo: mantiene un sesgo y detecta la
    ruptura del último swing. **CHoCH** (giro de tendencia) pesa más que **BOS**
    (continuación). Combina dos escalas —estructura *swing* (largo plazo) e
    *interna* (corto plazo)— y refuerza la confianza cuando ambas coinciden.
    """

    category = "structure"

    def analyze(self, md: MarketData) -> AgentDecision:
        tf = Timeframe.H1 if md.has(Timeframe.H1) else md.primary_tf
        df = md.frame(tf)
        if len(df) < 30:
            return self._wait("Datos insuficientes para estructura")

        swing_len = int(self.config.get("swing_length", 5))
        internal_len = int(self.config.get("internal_length", 2))
        swing_state = st.market_structure(st.find_swings(df, swing_len, swing_len))
        internal_state = st.market_structure(st.find_swings(df, internal_len, internal_len))

        # La estructura swing manda; si es indefinida, se usa la interna.
        state = swing_state if swing_state.trend != "undefined" else internal_state
        if state.trend == "undefined":
            return self._wait("Estructura sin definir")

        signal = SignalType.BUY if state.trend == "bullish" else SignalType.SELL
        conf = 80.0 if state.event == "CHoCH" else 70.0   # el giro pesa más
        # Confluencia entre escalas.
        if internal_state.trend == swing_state.trend and swing_state.trend != "undefined":
            conf = min(90.0, conf + 8.0)
        elif internal_state.trend != "undefined" and swing_state.trend != "undefined" \
                and internal_state.trend != swing_state.trend:
            conf = max(45.0, conf - 15.0)

        expl = (f"Estructura {state.trend} {state.event} "
                f"(swing={swing_state.trend}/{swing_state.event}, "
                f"interna={internal_state.trend}/{internal_state.event})")
        sl, tp = atr_sl_tp(md.price, md.regime.atr, signal)
        return self._decision(
            signal, conf, expl, estimated_risk=40.0, stop_loss=sl, take_profit=tp,
            event=state.event, trend=state.trend,
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

        o, hi, lo, c = (df[x] for x in ("open", "high", "low", "close"))
        o1, c1 = o.iloc[-1], c.iloc[-1]
        o2, c2 = o.iloc[-2], c.iloc[-2]
        rng = hi.iloc[-1] - lo.iloc[-1]
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
            upper = hi.iloc[-1] - max(o1, c1)
            lower = min(o1, c1) - lo.iloc[-1]
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


@register_agent("premium_discount")
class PremiumDiscountAgent(BaseAgent):
    """Sesgo por zona premium/discount del rango (Smart Money, LuxAlgo).

    Divide el rango reciente en tres zonas: *discount* (parte baja) favorece
    compras, *premium* (parte alta) favorece ventas, y *equilibrio* (centro) no
    aporta señal. La convicción crece cuanto más profundo esté el precio en la
    zona. Es un sesgo contextual, no un gatillo por sí solo.
    """

    category = "structure"

    def analyze(self, md: MarketData) -> AgentDecision:
        tf = Timeframe.H1 if md.has(Timeframe.H1) else md.primary_tf
        df = md.frame(tf)
        if len(df) < 20:
            return self._wait("Datos insuficientes para premium/discount")

        lookback = int(self.config.get("lookback", 50))
        hi, lo, _eq = st.premium_discount(df, lookback=lookback)
        rng = hi - lo
        if rng <= 0:
            return self._wait("Rango nulo")

        price = md.price
        pos = (price - lo) / rng  # 0 (mínimo) .. 1 (máximo)
        disc_thr = float(self.config.get("discount", 0.25))
        prem_thr = float(self.config.get("premium", 0.75))
        atr = md.regime.atr or float(ind.atr(df, 14).iloc[-1])

        if pos <= disc_thr:
            signal = SignalType.BUY
            conf = 40.0 + (disc_thr - pos) / disc_thr * 30.0
            expl = f"Precio en discount ({pos * 100:.0f}% del rango) → sesgo comprador"
        elif pos >= prem_thr:
            signal = SignalType.SELL
            conf = 40.0 + (pos - prem_thr) / (1.0 - prem_thr) * 30.0
            expl = f"Precio en premium ({pos * 100:.0f}% del rango) → sesgo vendedor"
        else:
            return self._decision(
                SignalType.WAIT, 20.0,
                f"Precio en equilibrio ({pos * 100:.0f}% del rango)", estimated_risk=40.0,
            )

        sl, tp = atr_sl_tp(price, atr, signal)
        return self._decision(
            signal, min(70.0, conf), expl, estimated_risk=45.0,
            stop_loss=sl, take_profit=tp, zone_pos=round(pos, 3),
        )


@register_agent("fibonacci")
class FibonacciAgent(BaseAgent):
    """Retrocesos de Fibonacci del último impulso (entrada a favor de tendencia).

    Toma la última pierna de impulso (dos pivotes alternados) y opera la
    continuación cuando el precio retrocede a una zona clave (0.5 / 0.618 /
    0.786): en un impulso alcista, compra en el pullback; en uno bajista, vende.
    El 0.618 (golden ratio) pesa más. No entra si el retroceso ya rompió el
    origen del impulso (estructura invalidada).
    """

    category = "structure"

    def analyze(self, md: MarketData) -> AgentDecision:
        tf = Timeframe.H1 if md.has(Timeframe.H1) else md.primary_tf
        df = md.frame(tf)
        if len(df) < 40:
            return self._wait("Datos insuficientes para Fibonacci")
        atr = md.regime.atr or float(ind.atr(df, 14).iloc[-1])
        if atr <= 0:
            return self._wait("ATR no válido")

        swings = st.alternating_swings(st.find_swings(df, 3, 3))
        if len(swings) < 2:
            return self._wait("Sin impulso para Fibonacci")
        a, b = swings[-2], swings[-1]           # a = origen, b = fin del impulso
        leg = b.price - a.price
        if abs(leg) < atr:
            return self._wait("Impulso demasiado pequeño")

        price = md.price
        up = b.kind == "high"                   # impulso alcista si termina en máximo
        tol = float(self.config.get("tol_atr", 0.5)) * atr
        near, best = None, tol + 1
        for level in (0.5, 0.618, 0.786):
            lvl_price = b.price - level * leg    # zona de retroceso
            dist = abs(price - lvl_price)
            if dist <= tol and dist < best:
                near, best = level, dist
        if near is None:
            return self._decision(SignalType.WAIT, 20.0, "Precio fuera de zonas Fibonacci",
                                  estimated_risk=40.0)

        # Continuación en la dirección del impulso, si no se rompió el origen.
        if up and price > a.price:
            signal = SignalType.BUY
        elif (not up) and price < a.price:
            signal = SignalType.SELL
        else:
            return self._decision(SignalType.WAIT, 20.0, "Retroceso invalidó el impulso",
                                  estimated_risk=45.0)

        conf = 62.0 + (12.0 if abs(near - 0.618) < 1e-6 else 0.0)
        sl, tp = atr_sl_tp(md.price, atr, signal)
        return self._decision(
            signal, conf, f"Retroceso {near:.3f} de Fibonacci (continuación {'alcista' if up else 'bajista'})",
            estimated_risk=45.0, stop_loss=sl, take_profit=tp, fib_level=near,
        )


@register_agent("coast")
class CoastAgent(BaseAgent):
    """"Trading in the Coast" (Ferran Font) — SOLO la señal de entrada.

    Porta la lógica de entrada del sistema: rotura *con decisión* de un nivel S/R
    (cuerpo > body_mult×ATR) seguida de un **retest** del nivel roto, con refuerzo
    por *Auction Market Theory* (varios intentos fallidos en el nivel antes de
    romperlo → convicción de rotura del "canal").

    Se DESCARTA por diseño la gestión del sistema original (sin stop, scale-in,
    aguantar la perdedora): aquí el agente solo VOTA y el risk manager del sistema
    le impone SL/TP (ATR 1.0/2.5) y el 1% de riesgo como a cualquier otro agente.
    """

    category = "structure"

    def analyze(self, md: MarketData) -> AgentDecision:
        tf = Timeframe.H1 if md.has(Timeframe.H1) else md.primary_tf
        df = md.frame(tf)
        if len(df) < 60:
            return self._wait("Datos insuficientes para Coast")

        pivot = int(self.config.get("pivot", 8))
        body_mult = float(self.config.get("body_mult", 1.3))
        retest_max = int(self.config.get("retest_max_bars", 20))
        tol = float(self.config.get("retest_tol_pct", 0.10)) / 100.0
        fail_threshold = int(self.config.get("fail_threshold", 3))
        window = int(self.config.get("lookback", 120))

        atr = md.regime.atr
        if atr <= 0:
            return self._wait("ATR no válido")

        d = df.iloc[-window:] if len(df) > window else df
        o = d["open"].to_numpy(); c = d["close"].to_numpy()
        h = d["high"].to_numpy(); low = d["low"].to_numpy()
        n = len(d)
        swings = st.find_swings(d, pivot, pivot)
        res = [(s.pos, s.price) for s in swings if s.kind == "high"]
        sup = [(s.pos, s.price) for s in swings if s.kind == "low"]

        best = None  # (signal, level, decisiveness, fails)
        lo_b = max(1, n - retest_max - 1)
        # Rotura+retest alcista: cierre cruza una resistencia previa con cuerpo decisivo
        for b in range(n - 1, lo_b - 1, -1):
            if abs(c[b] - o[b]) <= body_mult * atr:
                continue
            for pos, R in res:
                if pos >= b - pivot or R <= 0:
                    continue
                if c[b] > R and c[b - 1] <= R and c[-1] > R and low[b:].min() <= R * (1 + tol):
                    fails = sum(1 for p, pr in res if p < b and abs(pr - R) / R <= tol)
                    best = (SignalType.BUY, R, abs(c[b] - o[b]) / atr, fails)
                    break
            if best:
                break
        if best is None:  # rotura+retest bajista
            for b in range(n - 1, lo_b - 1, -1):
                if abs(c[b] - o[b]) <= body_mult * atr:
                    continue
                for pos, S in sup:
                    if pos >= b - pivot or S <= 0:
                        continue
                    if c[b] < S and c[b - 1] >= S and c[-1] < S and h[b:].max() >= S * (1 - tol):
                        fails = sum(1 for p, pr in sup if p < b and abs(pr - S) / S <= tol)
                        best = (SignalType.SELL, S, abs(c[b] - o[b]) / atr, fails)
                        break
                if best:
                    break

        if best is None:
            return self._wait("Sin rotura+retest de nivel")

        signal, level, decisiveness, fails = best
        conf = 45.0 + min(25.0, (decisiveness - 1.0) * 20.0)
        if fails >= fail_threshold:      # Auction Market Theory: 3+ intentos fallidos
            conf = min(85.0, conf + 15.0)
        amt = f" +AMT({fails})" if fails >= fail_threshold else ""
        expl = (f"Coast: rotura+retest {'alcista' if signal is SignalType.BUY else 'bajista'} "
                f"de {level:.2f} (cuerpo {decisiveness:.1f}×ATR{amt})")
        sl, tp = atr_sl_tp(md.price, atr, signal)
        return self._decision(
            signal, conf, expl, estimated_risk=42.0, stop_loss=sl, take_profit=tp,
            level=level, fails=fails,
        )
