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


def _near(value: float, target: float, tol: float) -> tuple:
    """(ok, desviación_normalizada) respecto a un objetivo puntual."""
    dev = abs(value - target) / target if target else 1.0
    return dev <= tol, dev


def _within(value: float, lo: float, hi: float, tol: float) -> tuple:
    """(ok, desviación) respecto a un rango [lo, hi] con tolerancia en los bordes."""
    ok = lo * (1 - tol) <= value <= hi * (1 + tol)
    if value < lo:
        dev = (lo - value) / lo if lo else 1.0
    elif value > hi:
        dev = (value - hi) / hi if hi else 1.0
    else:
        dev = 0.0
    return ok, dev


@register_agent("harmonic")
class HarmonicPatternAgent(BaseAgent):
    """Reconoce patrones armónicos sobre los últimos pivotes alternados.

    Portado de un escáner Pine basado en el "Manual de patrones armónicos":
    valida los ratios de Fibonacci de las piernas AB, BC y la proyección del
    punto D (XABCD de 5 puntos). Reconoce Gartley, Bat, Butterfly, Crab, Deep
    Crab, 5-0, Shark y AB=CD, en ese orden de prioridad. La finalización en un
    mínimo -> BUY; en un máximo -> SELL.

    A diferencia del escáner de TradingView, aquí NO se repinta: los pivotes se
    confirman con velas ya cerradas (`find_swings` mira a ambos lados), por lo
    que la decisión de la barra i solo usa datos hasta i. SL/TP por ATR (política
    común del sistema, validada en backtest).
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
        tol = float(self.config.get("tolerance", 0.05))
        match = self._classify(x.price, a.price, b.price, c.price, d.price, tol)
        if match is None:
            return self._decision(
                SignalType.WAIT, 20.0, "Sin patrón armónico válido en XABCD",
                estimated_risk=45.0,
            )
        name, err = match
        signal = SignalType.BUY if d.kind == "low" else SignalType.SELL
        conf = max(45.0, min(88.0, 88.0 - err * 250.0))
        sl, tp = atr_sl_tp(md.price, atr, signal)
        return self._decision(
            signal, conf, f"Patrón {name} completado en D={d.price:.2f}",
            estimated_risk=50.0, stop_loss=sl, take_profit=tp,
            pattern=name,
        )

    @staticmethod
    def _classify(x: float, a: float, b: float, c: float, d: float, tol: float) -> Optional[tuple]:
        """Clasifica el XABCD según los ratios del manual. (nombre, error) o None.

        Se evalúan en orden de prioridad; se devuelve el primero que cumple TODAS
        sus restricciones (misma lógica que el escáner Pine).
        """
        xa, ab, bc, cd = abs(a - x), abs(b - a), abs(c - b), abs(d - c)
        if xa <= 0 or ab <= 0 or bc <= 0:
            return None
        ab_r = ab / xa            # AB respecto a XA
        bc_r = bc / ab            # BC respecto a AB
        ad_r = abs(a - d) / xa    # proyección de D sobre XA
        cd_r = cd / bc            # CD respecto a BC (5-0)
        cd_ab = cd / ab           # CD respecto a AB (AB=CD)
        shk_ab = bc / xa          # Shark: convención O-X-A-B-C (x=O, a=X, b=A, c=B, d=C)
        shk_cd = cd / ab
        shk_ext = abs(d - x) / xa

        def check(*constraints) -> Optional[float]:
            """Devuelve el error total si TODAS se cumplen; si no, None."""
            err = 0.0
            for ok, dev in constraints:
                if not ok:
                    return None
                err += dev
            return err

        # Orden de prioridad (idéntico al escáner Pine).
        candidates = [
            ("AB=CD", lambda: check(
                _within(bc_r, 0.618, 0.786, tol),
                _any_near(cd_ab, (1.0, 1.27, 1.618, 2.0), tol))),
            ("Gartley", lambda: check(
                _near(ab_r, 0.618, tol), _within(bc_r, 0.382, 0.886, tol),
                _within(ad_r, 0.786, 0.886, tol))),
            ("Bat", lambda: check(
                _within(ab_r, 0.382, 0.50, tol), _within(bc_r, 0.382, 0.886, tol),
                _near(ad_r, 0.886, tol))),
            ("Butterfly", lambda: check(
                _near(ab_r, 0.786, tol), _within(bc_r, 0.382, 0.886, tol),
                _within(ad_r, 1.27, 1.618, tol))),
            ("Crab", lambda: check(
                _within(ab_r, 0.382, 0.618, tol), _within(bc_r, 0.382, 0.886, tol),
                _near(ad_r, 1.618, tol))),
            ("Deep Crab", lambda: check(
                _near(ab_r, 0.886, tol), _within(bc_r, 0.382, 0.886, tol),
                _near(ad_r, 1.618, tol))),
            ("5-0", lambda: check(
                _within(ab_r, 1.13, 1.618, tol), _within(bc_r, 1.618, 2.24, tol),
                _near(cd_r, 0.50, tol))),
            ("Shark", lambda: check(
                _within(shk_ab, 1.13, 1.618, tol), _within(shk_cd, 1.618, 2.24, tol),
                (shk_ext >= 1.13 * (1 - tol), max(0.0, 1.13 - shk_ext)))),
        ]
        for name, evaluate in candidates:
            err = evaluate()
            if err is not None:
                return name, err
        return None


def _any_near(value: float, targets: tuple, tol: float) -> tuple:
    """(ok, desviación) respecto al más cercano de varios objetivos puntuales."""
    best_dev = min(abs(value - t) / t if t else 1.0 for t in targets)
    return best_dev <= tol, best_dev


@register_agent("elliott")
class ElliottWaveAgent(BaseAgent):
    """Conteo de ondas de Elliott: entrada al completarse la corrección ABC.

    Portado (en su lógica de decisión) del escáner Elliott de LuxAlgo. Sobre los
    últimos 9 pivotes alternados busca un **impulso 1-2-3-4-5** seguido de una
    **corrección ABC** completada, y entra esperando el nuevo impulso:

    - Impulso alcista + ABC bajista terminada -> BUY (se reanuda al alza).
    - Impulso bajista + ABC alcista terminada -> SELL (se reanuda a la baja).

    Reglas del impulso (Elliott clásico): la onda 3 no es la más corta, la onda 4
    no solapa el territorio de la onda 1, y las ondas 3 y 5 superan a la anterior.
    La corrección debe respetar el inicio del impulso (no borrarlo).

    NO dibuja (eso es del Pine de TradingView) y NO repinta: los pivotes se
    confirman con velas cerradas, así la decisión de la barra i solo usa datos
    hasta i. SL/TP por ATR (política común del sistema).
    """

    category = "price_action"

    def analyze(self, md: MarketData) -> AgentDecision:
        df = _structure_frame(md)
        if len(df) < 60:
            return self._wait("Datos insuficientes para Elliott")
        atr = _atr(md, df)
        swings = st.alternating_swings(st.find_swings(df, 3, 3))
        if len(swings) < 9:
            return self._wait("Pivotes insuficientes para conteo Elliott")

        last = swings[-9:]
        tol = float(self.config.get("tolerance", 0.05))
        result = self._detect(last, tol)
        if result is None:
            return self._decision(
                SignalType.WAIT, 20.0, "Sin estructura de Elliott válida (impulso+ABC)",
                estimated_risk=45.0,
            )
        signal, label, conf = result
        sl, tp = atr_sl_tp(md.price, atr, signal)
        return self._decision(
            signal, conf, label, estimated_risk=50.0, stop_loss=sl, take_profit=tp,
            pattern="elliott",
        )

    @classmethod
    def _detect(cls, swings, tol: float) -> Optional[tuple]:
        """Devuelve (señal, etiqueta, confianza) si hay impulso+ABC completado."""
        prices = [s.price for s in swings]
        first = swings[0].kind
        if first == "low":                      # impulso alcista + ABC bajista
            ok, conf = cls._check_bull(prices, tol)
            if ok:
                return SignalType.BUY, "Impulso alcista + ABC completada → nueva onda al alza", conf
        elif first == "high":                   # impulso bajista + ABC alcista (espejo)
            ok, conf = cls._check_bull([-p for p in prices], tol)
            if ok:
                return SignalType.SELL, "Impulso bajista + ABC completada → nueva onda a la baja", conf
        return None

    @staticmethod
    def _check_bull(p, tol: float) -> tuple:
        """Valida un impulso alcista 1-5 (p0..p5) + corrección ABC (p5..p8).

        Trabaja siempre en la orientación alcista; el caso bajista se evalúa con
        los precios negados (espejo). Devuelve (ok, confianza).
        """
        p0, p1, p2, p3, p4, p5, p6, p7, p8 = p

        # --- Impulso 1-2-3-4-5 (piernas al alza en 0-1, 2-3, 4-5) ---
        if not (p1 > p0 and p3 > p2 and p5 > p4):
            return False, 0.0
        if not (p2 > p0):          # onda 2 no rompe el inicio
            return False, 0.0
        if not (p3 > p1):          # onda 3 supera el techo de la onda 1
            return False, 0.0
        if not (p4 > p1):          # onda 4 no solapa el territorio de la onda 1
            return False, 0.0
        if not (p5 > p3):          # onda 5 supera el techo de la onda 3
            return False, 0.0
        w1, w3, w5 = p1 - p0, p3 - p2, p5 - p4
        if w3 < w1 and w3 < w5:    # la onda 3 nunca es la más corta
            return False, 0.0

        # --- Corrección ABC (A abajo 5-6, B arriba 6-7, C abajo 7-8) ---
        if not (p6 < p5 and p7 > p6 and p8 < p7):
            return False, 0.0
        if not (p7 <= p5):         # el rebote B no supera el techo de la onda 5
            return False, 0.0
        if not (p8 < p5):          # C queda por debajo del techo (es una corrección)
            return False, 0.0
        if not (p8 > p0):          # la corrección no borra el impulso
            return False, 0.0

        # --- Confianza: geometría de C vs A y fuerza de la onda 3 ---
        conf = 60.0
        wave_a = p5 - p6
        wave_c = p7 - p8
        if wave_a > 0:
            ratio = wave_c / wave_a
            if 0.85 <= ratio <= 1.15 or 1.5 <= ratio <= 1.75:
                conf += 12.0
        if w3 >= w1 and w3 >= w5:   # onda 3 es la más extensa (impulso sano)
            conf += 8.0
        return True, min(82.0, conf)
