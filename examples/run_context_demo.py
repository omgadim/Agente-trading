"""Demo: agentes de contexto externo (noticias, correlación, sentimiento).

Muestra dos escenarios con proveedores en memoria:
  A) Noticia de alto impacto inminente -> veto del Supervisor (WAIT).
  B) Sin noticias: correlación (DXY) y sentimiento retail aportan sesgo.

Uso:
    PYTHONPATH=src python -m examples.run_context_demo
"""
from __future__ import annotations

from datetime import timedelta

from trading_system.context import (
    EconomicEvent,
    InMemoryCorrelationProvider,
    InMemoryNewsProvider,
    InMemorySentimentProvider,
)
from trading_system.core import AgentRegistry
from trading_system.data import SimulatedDataFeed
from trading_system.supervisor import StaticWeighting, Supervisor
from trading_system.utils import setup_logging

import trading_system.agents  # noqa: F401


def _supervisor(news_provider, corr_provider, sent_provider):
    directional = [AgentRegistry.create(n, {}) for n in
                   ("trend_mtf", "technical", "market_structure")]
    context = [
        AgentRegistry.create("news", {"provider": news_provider}),
        AgentRegistry.create("correlation", {"provider": corr_provider, "threshold": 0.01}),
        AgentRegistry.create("sentiment", {"provider": sent_provider}),
    ]
    return Supervisor(directional + context, weighting=StaticWeighting({}))


def main() -> None:
    setup_logging("WARNING")
    md = SimulatedDataFeed(base_price=2000, drift=0.2, volatility=1.0,
                           bars=700, seed=5).get_market_data("XAUUSD")

    gold = md.closes(md.primary_tf)
    dxy_inverse = 2 * float(gold.mean()) - gold  # correlación ~ -1 con el Oro
    corr_provider = InMemoryCorrelationProvider({"DXY": dxy_inverse})
    sent_provider = InMemorySentimentProvider(default=78.0)  # retail muy largo

    # --- Escenario A: noticia de alto impacto en +10 min ---
    ev = EconomicEvent(md.timestamp + timedelta(minutes=10), "USD", "high", "Non-Farm Payrolls")
    sup_a = _supervisor(InMemoryNewsProvider([ev]), corr_provider, sent_provider)
    dec_a = sup_a.decide(md)
    print("=== Escenario A: noticia inminente ===")
    print(f"  Decisión: {dec_a.signal.value} | vetoed={dec_a.vetoed} | {dec_a.explanation}")

    # --- Escenario B: sin noticias ---
    sup_b = _supervisor(InMemoryNewsProvider([]), corr_provider, sent_provider)
    dec_b = sup_b.decide(md)
    print("\n=== Escenario B: sin noticias ===")
    print(f"  Decisión: {dec_b.signal.value} | conf={dec_b.confidence:.0f} | {dec_b.explanation}")
    for d in dec_b.contributing:
        if d.agent_name in ("news", "correlation", "sentiment"):
            print(f"    {d.agent_name:12s} {d.signal.value:4s} -> {d.explanation[:60]}")


if __name__ == "__main__":
    main()
