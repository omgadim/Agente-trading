"""Tests de los agentes de contexto externo (Fase 5)."""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from trading_system.context import (
    EconomicEvent,
    Headline,
    InMemoryCorrelationProvider,
    InMemoryNewsFlowProvider,
    InMemoryNewsProvider,
    InMemorySentimentProvider,
)
from trading_system.core import AgentRegistry, SignalType
from trading_system.data import SimulatedDataFeed

import trading_system.agents  # noqa: F401


@pytest.fixture
def md():
    return SimulatedDataFeed(base_price=2000, drift=0.15, volatility=1.0,
                             bars=600, seed=5).get_market_data("XAUUSD")


CONTEXT_AGENTS = ["news", "correlation", "sentiment"]


@pytest.mark.parametrize("name", CONTEXT_AGENTS)
def test_context_agent_waits_without_provider(name, md):
    d = AgentRegistry.create(name, {}).run(md)
    assert d.signal is SignalType.WAIT
    assert d.metadata.get("planned") is None  # ya no son scaffolds


# ---- News -------------------------------------------------------------------
def test_news_vetoes_on_high_impact_usd(md):
    ev = EconomicEvent(md.timestamp + timedelta(minutes=10), "USD", "high", "NFP")
    d = AgentRegistry.create("news", {"provider": InMemoryNewsProvider([ev])}).run(md)
    assert d.metadata.get("veto") is True
    assert "NFP" in d.explanation


def test_news_vetoes_from_calendar_csv(md, tmp_path):
    # Verifica la vía real: NewsAgent leyendo un calendario CSV (como en producción).
    ts = md.timestamp
    ev_time = (ts + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    csv = tmp_path / "cal.csv"
    csv.write_text("time,currency,impact,title\n"
                   f"{ev_time},USD,high,Non-Farm Payrolls\n")
    d = AgentRegistry.create("news", {"calendar_csv": str(csv)}).run(md)
    assert d.metadata.get("veto") is True
    assert "Non-Farm Payrolls" in d.explanation


def test_news_ignores_far_and_low_impact(md):
    evs = [
        EconomicEvent(md.timestamp + timedelta(hours=5), "USD", "high", "far"),
        EconomicEvent(md.timestamp + timedelta(minutes=5), "USD", "low", "minor"),
        EconomicEvent(md.timestamp + timedelta(minutes=5), "JPY", "high", "otra divisa"),
    ]
    d = AgentRegistry.create("news", {"provider": InMemoryNewsProvider(evs)}).run(md)
    assert d.metadata.get("veto") is not True


# ---- News flow (ráfaga de titulares) ----------------------------------------
def test_news_flow_vetoes_on_burst(md):
    now = md.timestamp
    heads = [Headline(f"Gold spikes {i}", now - timedelta(minutes=5 * i)) for i in range(4)]
    prov = InMemoryNewsFlowProvider(heads)
    d = AgentRegistry.create("news_flow", {"provider": prov, "window_min": 60,
                                           "min_articles": 3}).run(md)
    assert d.metadata.get("veto") is True
    assert d.metadata.get("headline_count") >= 3


def test_news_flow_calm_does_not_veto(md):
    now = md.timestamp
    heads = [Headline("Gold steady", now - timedelta(minutes=10))]  # solo 1 titular
    prov = InMemoryNewsFlowProvider(heads)
    d = AgentRegistry.create("news_flow", {"provider": prov, "window_min": 60,
                                           "min_articles": 3}).run(md)
    assert d.metadata.get("veto") is not True


def test_news_flow_waits_without_provider(md):
    d = AgentRegistry.create("news_flow", {}).run(md)
    assert d.signal is SignalType.WAIT
    assert d.metadata.get("veto") is not True


def test_supervisor_respects_news_veto(md):
    from trading_system.core import BaseAgent
    from trading_system.supervisor import StaticWeighting, Supervisor

    class BullAgent(BaseAgent):
        def analyze(self, m):
            return self._decision(SignalType.BUY, 90.0, "compra", stop_loss=1990, take_profit=2020)

    ev = EconomicEvent(md.timestamp + timedelta(minutes=10), "USD", "high", "FOMC")
    news = AgentRegistry.create("news", {"provider": InMemoryNewsProvider([ev])})
    sup = Supervisor([BullAgent("bull", {}), news], weighting=StaticWeighting({}))
    decision = sup.decide(md)
    assert decision.vetoed is True
    assert decision.signal is SignalType.WAIT


# ---- Correlation ------------------------------------------------------------
def test_correlation_actionable_with_strong_corr(md):
    gold = md.closes(md.primary_tf)
    # Activo inversamente correlacionado (corr ~ -1).
    inverse = 2 * float(gold.mean()) - gold
    prov = InMemoryCorrelationProvider({"DXY": inverse})
    d = AgentRegistry.create(
        "correlation", {"provider": prov, "threshold": 0.01, "min_abs_corr": 0.3}
    ).run(md)
    assert d.signal in (SignalType.BUY, SignalType.SELL)
    assert "bias" in d.metadata


def test_correlation_waits_without_significant_corr(md):
    rng = np.random.default_rng(0)
    noise = pd.Series(rng.normal(100, 1, len(md.closes(md.primary_tf))),
                      index=md.closes(md.primary_tf).index)
    prov = InMemoryCorrelationProvider({"NOISE": noise})
    d = AgentRegistry.create("correlation", {"provider": prov, "min_abs_corr": 0.6}).run(md)
    assert d.signal is SignalType.WAIT


# ---- Sentiment --------------------------------------------------------------
def test_sentiment_contrarian_sell_when_retail_long(md):
    prov = InMemorySentimentProvider(default=82.0)
    d = AgentRegistry.create("sentiment", {"provider": prov}).run(md)
    assert d.signal is SignalType.SELL
    assert d.metadata.get("net_long") == 82.0


def test_sentiment_contrarian_buy_when_retail_short(md):
    prov = InMemorySentimentProvider(default=18.0)
    d = AgentRegistry.create("sentiment", {"provider": prov}).run(md)
    assert d.signal is SignalType.BUY


def test_sentiment_neutral_waits(md):
    prov = InMemorySentimentProvider(default=52.0)
    d = AgentRegistry.create("sentiment", {"provider": prov}).run(md)
    assert d.signal is SignalType.WAIT
