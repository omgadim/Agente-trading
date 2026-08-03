"""Demo: backtest walk-forward del sistema multiagente con datos simulados.

Uso:
    PYTHONPATH=src python -m examples.run_backtest
"""
from __future__ import annotations

from pathlib import Path

from trading_system.backtest import Backtester
from trading_system.data import SimulatedDataFeed
from trading_system.engine import build_agents, build_weighting
from trading_system.supervisor import Supervisor
from trading_system.utils import load_config, setup_logging


def main() -> None:
    setup_logging("WARNING")  # silencioso: el backtest hace muchas decisiones
    config = load_config(Path(__file__).resolve().parents[1] / "config" / "config.yaml")

    # Serie histórica simulada (sustituible por datos reales de MT5/CSV).
    base = SimulatedDataFeed(base_price=2000.0, drift=0.05, volatility=1.3,
                             bars=3000, seed=2025).generate()

    supervisor = Supervisor(
        agents=build_agents(config),
        weighting=build_weighting(config),
    )
    backtester = Backtester(supervisor, warmup=400, step=6, learn=True)
    result = backtester.run(base)

    print("\n=== RESULTADO DEL BACKTEST ===")
    print(result.summary())
    print(f"Capital inicial: {result.initial_equity:.2f}")
    print(f"Capital final:   {result.equity_curve[-1]:.2f}")
    print("\nDetalle de métricas:")
    for k, v in result.metrics.items():
        print(f"  {k:15s}: {v}")

    print("\nPrimeras operaciones:")
    for t in result.trades[:8]:
        print(f"  {t.direction.value:4s} entrada={t.entry_price:8.2f} "
              f"salida={t.exit_price:8.2f} pnl={t.pnl:8.2f} ({t.reason})")


if __name__ == "__main__":
    main()
