"""Demo: sesión live en modo *paper* usando el cliente MT5 simulado.

Corre en cualquier SO (no requiere el terminal MetaTrader 5). Sustituyendo
`SimulatedMT5Client` por `RealMT5Client` (y llamando `connect()`), el mismo código
opera en una cuenta demo/real de MT5.

Uso:
    PYTHONPATH=src python -m examples.run_live_paper
"""
from __future__ import annotations

from pathlib import Path

from trading_system import LiveTrader
from trading_system.data import SimulatedDataFeed
from trading_system.engine import build_agents, build_weighting
from trading_system.execution import MarketGuard, MT5Broker, MT5DataFeed, SimulatedMT5Client
from trading_system.risk import RiskManager, RiskParameters
from trading_system.supervisor import Supervisor
from trading_system.utils import load_config, setup_logging


def main() -> None:
    setup_logging("WARNING")
    config = load_config(Path(__file__).resolve().parents[1] / "config" / "config.yaml")

    # --- Cliente MT5 simulado sobre una serie histórica generada ---
    base = SimulatedDataFeed(base_price=2000.0, drift=0.06, volatility=1.2,
                             bars=3000, seed=777).generate()
    client = SimulatedMT5Client(base, symbol="XAUUSD", start=500, spread=0.20)
    client.connect()

    feed = MT5DataFeed(client, bars=400)
    broker = MT5Broker(client)

    risk = RiskManager(RiskParameters(**(config.get("risk") or {})))
    supervisor = Supervisor(
        agents=build_agents(config),
        weighting=build_weighting(config),
        risk_manager=risk,
    )
    # NOTA: la serie es sintética (timestamps continuos, incl. noches/fines de
    # semana), así que relajamos los filtros de calendario del guardián para que
    # el demo sea ilustrativo. En producción se usa la sección `guards:` de la
    # config (ver run_live_paper con RealMT5Client). El control de spread sí aplica.
    guard_cfg = config.get("guards", {}) or {}
    guard = MarketGuard(
        max_spread=guard_cfg.get("max_spread"),
        trading_hours=[],
        allow_weekend=True,
    )
    trader = LiveTrader(feed, broker, supervisor, risk_manager=risk, guard=guard)

    opened = managed = 0
    while client.has_next():
        result = trader.step()
        opened += 1 if result.opened else 0
        managed += len(result.management)
        client.advance(6)  # el "terminal" avanza 6 barras (resuelve SL/TP)

    acct = client.account()
    wins = [p for p in client.closed if p.profit > 0]
    print("\n=== SESIÓN PAPER (MT5 simulado) ===")
    print(f"Operaciones abiertas:   {opened}")
    print(f"Cerradas por SL/TP:     {len(client.closed)}")
    print(f"Ganadoras:              {len(wins)}/{len(client.closed)}")
    print(f"Acciones de gestión:    {managed}")
    print(f"Balance final:          {acct.balance:.2f}")
    print(f"Equity (con flotante):  {acct.equity:.2f}")
    print(f"PnL realizado:          {client.realized_pnl:.2f}")


if __name__ == "__main__":
    main()
