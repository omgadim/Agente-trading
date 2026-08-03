"""Demo: backtest con persistencia en SQLite y consultas para el dashboard.

Genera una base de datos SQLite (`data/trading_demo.db`) con decisiones,
operaciones y desempeño por agente — las mismas tablas que consume el dashboard.
En producción se usa `MySQLRepository` con idéntica interfaz.

Uso:
    PYTHONPATH=src python -m examples.run_persistence_demo
"""
from __future__ import annotations

from pathlib import Path

from trading_system.data import SimulatedDataFeed
from trading_system.engine import build_agents, build_weighting
from trading_system.persistence import SqliteRepository
from trading_system.supervisor import Supervisor
from trading_system.utils import load_config, setup_logging

import trading_system.agents  # noqa: F401


def main() -> None:
    setup_logging("WARNING")
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config" / "config.yaml")

    data_dir = root / "data"
    data_dir.mkdir(exist_ok=True)
    db_path = data_dir / "trading_demo.db"
    if db_path.exists():
        db_path.unlink()

    repo = SqliteRepository(str(db_path))
    repo.initialize()

    base = SimulatedDataFeed(base_price=2000.0, drift=0.06, volatility=1.2,
                             bars=3000, seed=2025).generate()
    from trading_system.backtest import Backtester
    supervisor = Supervisor(agents=build_agents(config), weighting=build_weighting(config))
    result = Backtester(supervisor, warmup=400, step=6, learn=True, repository=repo).run(base)

    print("=== Persistencia poblada (SQLite) ===")
    print(f"BD: {db_path}")
    print(result.summary())
    print(f"\nDecisiones: {len(repo.recent_decisions(9999))}  "
          f"Operaciones: {len(repo.recent_trades(9999))}")
    print("PnL:", repo.pnl_summary())

    print("\nDesempeño por agente/régimen (top 8 por hit-rate):")
    for p in repo.agent_performance()[:8]:
        print(f"  {p['agent_name']:18s} {p['regime']:14s} "
              f"hits={p['hits']:2d} misses={p['misses']:2d} rate={float(p['hit_rate']):.2f}")

    repo.close()
    print("\nDashboard PHP (MySQL) en integrations/dashboard/ consume estas mismas tablas.")


if __name__ == "__main__":
    main()
