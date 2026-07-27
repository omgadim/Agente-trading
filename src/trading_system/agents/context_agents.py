"""Agentes de contexto externo (Fase 5): noticias, correlación y sentimiento.

Cada uno consume un *provider* inyectable (ver `trading_system.context`). Sin
proveedor configurado devuelven WAIT de forma honesta (enabled pero inertes). El
proveedor se pasa en `config['provider']` (objeto) al construir el agente; el
`NewsAgent` además puede cargarlo desde un CSV vía `config['calendar_csv']`.
"""
from __future__ import annotations

import os
from datetime import timedelta
from typing import Optional

import numpy as np

from ..context.providers import (
    CorrelationProvider,
    CsvNewsProvider,
    NewsFlowProvider,
    NewsProvider,
    SentimentProvider,
    TheNewsApiProvider,
)
from ..core import AgentDecision, BaseAgent, MarketData, SignalType, register_agent


@register_agent("news")
class NewsAgent(BaseAgent):
    """Bloquea la operativa alrededor de noticias de alto impacto (veto/timing).

    En una ventana de *blackout* antes/después de un evento de alto impacto que
    afecta al Oro (por defecto eventos USD), veta la operación: el spread se
    dispara y el movimiento es errático. Es un agente de contexto (siempre WAIT);
    su poder está en `metadata['veto']`, que el Supervisor respeta.
    """

    category = "context"

    def _provider(self) -> Optional[NewsProvider]:
        provider = self.config.get("provider")
        if provider is not None:
            return provider
        path = self.config.get("calendar_csv")
        if path:
            return CsvNewsProvider(path)
        return None

    def analyze(self, md: MarketData) -> AgentDecision:
        provider = self._provider()
        if provider is None:
            return self._decision(
                SignalType.WAIT, 0.0, "Sin calendario económico configurado",
                estimated_risk=50.0,
            )

        before = int(self.config.get("blackout_before_min", 30))
        after = int(self.config.get("blackout_after_min", 15))
        currencies = {c.upper() for c in self.config.get("currencies", ["USD"])}
        now = md.timestamp

        window = provider.events_between(now - timedelta(minutes=after),
                                         now + timedelta(minutes=before))
        relevant = [
            e for e in window
            if e.is_high and ("ALL" in currencies or e.currency in currencies)
        ]
        if relevant:
            ev = min(relevant, key=lambda e: abs((e.time - now).total_seconds()))
            mins = (ev.time - now).total_seconds() / 60.0
            when = f"en {mins:.0f} min" if mins >= 0 else f"hace {-mins:.0f} min"
            return self._decision(
                SignalType.WAIT, 0.0,
                f"Blackout por noticia de alto impacto: {ev.title} ({ev.currency}) {when}",
                estimated_risk=95.0,
                veto=True,
                veto_reason=f"Noticia de alto impacto ({ev.title}) {when}",
                event_title=ev.title,
            )
        return self._decision(
            SignalType.WAIT, 0.0, "Sin noticias de alto impacto próximas",
            estimated_risk=30.0,
        )


@register_agent("correlation")
class CorrelationAgent(BaseAgent):
    """Deriva un sesgo direccional del Oro desde activos correlacionados.

    Combina, para cada activo con correlación significativa, la correlación
    observada con el retorno reciente del activo: `bias = Σ corr_i · momentum_i`.
    Un DXY al alza (correlación negativa con el Oro) empuja el sesgo a la baja, etc.
    """

    category = "context"

    def _provider(self) -> Optional[CorrelationProvider]:
        return self.config.get("provider")

    def analyze(self, md: MarketData) -> AgentDecision:
        provider = self._provider()
        if provider is None:
            return self._decision(
                SignalType.WAIT, 0.0, "Sin proveedor de correlaciones configurado",
                estimated_risk=50.0,
            )

        lookback = int(self.config.get("lookback", 50))
        min_abs_corr = float(self.config.get("min_abs_corr", 0.3))
        gold = md.closes(md.primary_tf).iloc[-lookback:]
        gold_ret = gold.pct_change().dropna()
        if len(gold_ret) < 10:
            return self._wait("Serie de Oro insuficiente para correlación")

        contributions = []
        detail = []
        for symbol in provider.symbols():
            closes = provider.closes(symbol, lookback)
            if closes is None or len(closes) < 12:
                continue
            rel_ret = closes.pct_change().dropna()
            n = min(len(gold_ret), len(rel_ret))
            if n < 10:
                continue
            g = gold_ret.iloc[-n:].to_numpy()
            r = rel_ret.iloc[-n:].to_numpy()
            if g.std() == 0 or r.std() == 0:
                continue
            corr = float(np.corrcoef(g, r)[0, 1])
            if abs(corr) < min_abs_corr:
                continue
            momentum = float(np.tanh(r[-5:].sum() / (r.std() + 1e-9)))
            contributions.append(corr * momentum)
            detail.append(f"{symbol}(corr={corr:+.2f})")

        if not contributions:
            return self._decision(
                SignalType.WAIT, 20.0, "Sin correlaciones significativas",
                estimated_risk=45.0,
            )

        bias = float(np.mean(contributions))
        threshold = float(self.config.get("threshold", 0.1))
        signal = SignalType.from_sign(bias, deadband=threshold)
        confidence = min(100.0, abs(bias) * 150.0)
        from .helpers import atr_sl_tp
        sl, tp = atr_sl_tp(md.price, md.regime.atr, signal)
        return self._decision(
            signal, confidence,
            f"Sesgo por correlación {bias:+.2f} [{', '.join(detail)}]",
            estimated_risk=45.0, stop_loss=sl, take_profit=tp,
            bias=bias,
        )


@register_agent("sentiment")
class SentimentAgent(BaseAgent):
    """Contrarian sobre el posicionamiento retail.

    Cuando el retail está mayoritariamente largo, el sesgo institucional suele ser
    el contrario: retail muy largo -> SELL; retail muy corto -> BUY.
    """

    category = "context"

    def _provider(self) -> Optional[SentimentProvider]:
        return self.config.get("provider")

    def analyze(self, md: MarketData) -> AgentDecision:
        provider = self._provider()
        if provider is None:
            return self._decision(
                SignalType.WAIT, 0.0, "Sin proveedor de sentimiento configurado",
                estimated_risk=50.0,
            )
        net_long = provider.net_long(md.symbol, md.timestamp)
        if net_long is None:
            return self._wait("Sentimiento no disponible para el símbolo")

        extreme_long = float(self.config.get("extreme_long", 70))
        extreme_short = float(self.config.get("extreme_short", 30))
        from .helpers import atr_sl_tp

        if net_long >= extreme_long:
            signal = SignalType.SELL
            confidence = min(100.0, (net_long - 50) * 2.0)
            reason = f"Retail {net_long:.0f}% largo (extremo) -> contrarian SELL"
        elif net_long <= extreme_short:
            signal = SignalType.BUY
            confidence = min(100.0, (50 - net_long) * 2.0)
            reason = f"Retail {net_long:.0f}% largo (bajo) -> contrarian BUY"
        else:
            return self._decision(
                SignalType.WAIT, 20.0,
                f"Sentimiento neutral (retail {net_long:.0f}% largo)",
                estimated_risk=45.0,
            )

        sl, tp = atr_sl_tp(md.price, md.regime.atr, signal)
        return self._decision(
            signal, confidence, reason, estimated_risk=50.0,
            stop_loss=sl, take_profit=tp, net_long=net_long,
        )


@register_agent("news_flow")
class NewsFlowAgent(BaseAgent):
    """Cautela ante ráfagas de noticias de prensa (TheNewsAPI).

    Complementa al `NewsAgent` (calendario de eventos programados) detectando
    **noticias NO programadas** (geopolítica, declaraciones sorpresa de la Fed...).
    Si en la ventana reciente aparece una ráfaga de titulares relevantes de
    Oro/USD, **veta** de forma preventiva (no apuesta dirección: el sentimiento
    por titulares es ruidoso). Es un agente de contexto **solo-live**: sin
    proveedor/token (p. ej. en backtest) devuelve WAIT inocuo.

    Provider: se inyecta en `config['provider']`, o se construye desde la variable
    de entorno `NEWS_API_TOKEN` (TheNewsAPI). Cachea para respetar el límite del
    plan gratuito.
    """

    category = "context"

    def _provider(self) -> Optional[NewsFlowProvider]:
        provider = self.config.get("provider")
        if provider is not None:
            return provider
        if os.getenv("NEWS_API_TOKEN"):
            return TheNewsApiProvider(
                search=self.config.get("search", "gold OR XAUUSD OR Federal Reserve OR inflation"),
                ttl_sec=int(self.config.get("refresh_sec", 900)),
            )
        return None

    def analyze(self, md: MarketData) -> AgentDecision:
        provider = self._provider()
        if provider is None:
            return self._decision(
                SignalType.WAIT, 0.0, "Sin proveedor de noticias configurado",
                estimated_risk=50.0,
            )
        window = int(self.config.get("window_min", 60))
        min_articles = int(self.config.get("min_articles", 3))
        headlines = provider.recent(window, at=md.timestamp)
        if len(headlines) >= min_articles:
            ejemplo = headlines[0].title[:80] if headlines else ""
            return self._decision(
                SignalType.WAIT, 0.0,
                f"Ráfaga de {len(headlines)} noticias en {window} min → cautela ('{ejemplo}')",
                estimated_risk=90.0, veto=True,
                veto_reason=f"Ráfaga de {len(headlines)} noticias de mercado en {window} min",
                headline_count=len(headlines),
            )
        return self._decision(
            SignalType.WAIT, 0.0,
            f"Flujo de noticias normal ({len(headlines)} en {window} min)",
            estimated_risk=30.0, headline_count=len(headlines),
        )
